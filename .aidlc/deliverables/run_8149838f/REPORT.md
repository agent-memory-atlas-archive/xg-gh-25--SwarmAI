# Autonomous Pipeline Report: TTFT cold-turn spawn attribution fix

**Run ID:** run_8149838f | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-15 08:24 UTC | **Duration:** 160.4 min (in progress) | **Tokens:** 63,000
**Gate 1:** N/A | **Files:** 3 | **Tests:** 0/0

## TL;DR
TTFT 观测日志在 cold turn 把 subprocess spawn 时间错误归入 send+infer(模型推理)段。根因:session_router.py 的 _ttft_presend_ms 在 unit.send() 之前测量,而 cold turn 的 spawn 发生在 unit.send() 内部,所以 spawn(13-20s) 落入 send+infer 残差,使 B

## 1. Requirement
TTFT 观测日志在 cold turn 把 subprocess spawn 时间错误归入 send+infer(模型推理)段。根因:session_router.py 的 _ttft_presend_ms 在 unit.send() 之前测量,而 cold turn 的 spawn 发生在 unit.send() 内部,所以 spawn(13-20s) 落入 send+infer 残差,使 Bedrock 看起来慢。修复:把 spawn 时间拆为独立观测段,使 send+infer 只反映真正的模型推理时间。纯观测/归因修复,不改运行时控制流,绝不阻塞 request path。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> TTFT 观测日志在 cold turn 把 subprocess spawn 时间错误归入 send+infer(模型推理)段。根因:session_router.py 的 _ttft_presend_ms 在 unit.send() 之前测量,而 cold turn 的 spawn 发生在 unit.send() 内部,所以 spawn(13-20s) 落入 send+infer 残差,使 Bedrock 看起来慢。修复:把 spawn 时间拆为独立观测段,使 send+infer 只反映真正的模型推理时间。纯观测/归因修复,不改运行时控制流,绝不阻塞 request path。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: B 修 TTFT 测量,352s/275s 实为 spawn 混入 send+infer | confirmed | ● | Given 一个 cold turn(unit 为 COLD,spawn 在 unit.send() 内发生), when 首 token 到达触发 TTFT 打点, then 日志行含独立 spawn=<ms> 段,send+infer 残差不再包含该 spawn 时间 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | spawn 时间从哪里取? | A. 从 session_unit 的 spawn_perf total_ms 回传给 router | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. 从 session_unit 的 spawn_perf total_ms 回传给 router (🧠 AI 替你拍的板 — resolution: self-answer: session_unit.py:3414-3442 已测 spawn 的 _total_ms,复用它桥接给 router 避免重复测量;THINK 确认回传机制)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 6.00 | |
| Feasibility | 9.00 | |
| **ROI** | **8.000** | **GO** |

**Acceptance Criteria:**
1. cold turn 的 TTFT 日志行把 spawn 时间显示为独立段(如 spawn=Nms),send+infer 不再含 spawn
2. warm turn 行为不变(无 spawn 段或 spawn=0),无回归
3. 纯观测:不改任何运行时控制流,不新增阻塞,request path 零影响
4. 新增测试:构造 cold turn(spawn 在 send 内)断言 spawn 段被拆出,且 send+infer = ttft - pre_send - spawn


## 3. Design & Approach
**Research Findings (THINK):**
- spawn 发生在 unit.send() 内部的 _ensure_spawned(session_unit.py:2243/2647),而 router 的 _ttft_t0(:2914)包住整个 send() 调用——所以 spawn ms 已隐含在 ttft 总量里,只是没从 send+infer 残差中减出
- _spawn 已测 _total_ms(session_unit.py:3437)但仅用于 log,是局部变量,未暴露给 router
- send() 有 SessionBusyError 并发守卫(:167)+ _client_io 锁(:527)——单 unit 单 turn 严格串行,故实例属性回传无并发竞态
- router 持有 unit 引用(调 unit.send() at :3487),可直接读 unit 的实例属性
- TECH.md S2(:890):spawn=SDK __aenter__ 握手 ~10-12s,非模型推理;本修复让这一事实在 cold turn 的 TTFT 日志里可见

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS, 1 session
- DELETION — effort: S, 1 session

**Chosen Approach:** 方案A(实例属性回传). _spawn 把已测的 _total_ms 存为 per-turn 实例属性; send() 入口 reset 该属性为 None(标记本 turn 未 spawn); router 在 _format_ttft_line 新增 spawn_ms 参数, send+infer = ttft - pre_send - spawn. 纯观测, 零控制流改动.

**Success Criteria:**
- cold turn 日志行三段清晰: slot / recall / pre_send / spawn / send+infer, send+infer 只含 Bedrock 推理
- warm turn 日志行与现在逐字节一致(spawn_ms=None 向后兼容)
- TestFormatTtftLine 全绿(新 3 + 旧 7)

**Always:**
- 纯观测: 新属性只被赋值(spawn)+读取(router), 不参与任何控制流判断
- warm/cold 两条路径都测

**Never:**
- 绝不在 send()/spawn 的控制流里基于 spawn_ms 做分支或阻塞
- 绝不新增 timeout/budget 截断(STEERING #2)
- 不改 spawn 本身的逻辑, 只读它已测的 _total_ms


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_b259c6d3 | 9,000 |  |
| think | completed | art_51fb176e | 8,000 |  |
| plan | completed | art_e750ff30 | 8,000 |  |
| build | completed | art_9421d7fd | 18,000 |  |
| review | completed | art_945ce634 | 12,000 |  |
| test | completed | art_5436e551 | 8,000 |  |
| deliver | recorded | art_f5cbe2a0 | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 63,000 | **Stages:** 6/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 05:49:34 | - |
| think | 05:52:14 | 2.7 min |
| plan | 05:54:11 | 1.9 min |
| build | 06:01:39 | 7.5 min |
| review | 06:03:13 | 1.6 min |
| test | 06:12:32 | 9.3 min |
| deliver | 08:24:06 | 131.6 min |
| reflect | - | - |

Slowest stage: `deliver` at 131.6 min (85% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

## 5. TDD Results
| Metric | Value |
|--------|-------|
| Tests total | 0 |
| Tests passed | 0 |
| Tests failed | 0 |
| New tests added | 0 |
| Duration | 0s |
| Regressions | 0 |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | scope=bugfix:根因已坐实、单文件观测修复、无迭代 | mechanical |  |
| think | 选方案A实例属性回传(vs B stream事件):A零控制流改动满足纯观测约束 | taste |  |
| plan | 6步change spec, 3文件, 实例属性_last_turn_spawn_ms | mechanical |  |
| build | Gate-1 WARN(lifecycle fragility)采纳:reset 放入既有 per-turn admis | taste |  |
| review | single-pass review(3文件<100行非auth/data/infra);0 findings | mechanical |  |
| test | 105/105 green (4 new AC + full regression); ac_driven run=tr | mechanical |  |

**Summary:** 4 mechanical, 2 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**3 findings** (verdict: ?)
- [MEDIUM] session_router.py _format_ttft_line: on a RETRIED cold turn only the LAST spawn 
- [LOW] session_router.py _format_ttft_line: send+infer could render NEGATIVE on the ret
- [LOW] test_session_router_pure.py: no retried-turn test (2 of 4 new tests not mutation

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/session_router.py`
- `backend/core/session_unit.py`
- `backend/tests/test_session_router_pure.py`

**+0 / -0 lines** | 3 files

## 9. Lessons
- [pitfall] A residual-subtraction observability formula (X = total - measured_parts) is only valid when the measured part is captured EXACTLY ONCE per total; on a retry/loop path where total spans N attempts but only the LAST attempt is stored, the subtraction over-attributes and can render negative — gate it on the single-attempt precondition (retry_count==0) rather than claiming it holds universally.
- [decision] When a bugfix strengthens a docstring to assert a stronger invariant (ALONE / nothing can contradict it), that claim itself becomes a reviewable surface: an adversarial reviewer correctly flags the overclaim on the edge path even when the arithmetic is right on the happy path. Soften the claim to its true validity domain in the same diff.
- [pitfall] Mutation-proof every new regression test by reverting the fix and confirming RED — two of four initially-added tests were backward-compat guards that stayed GREEN under revert (vacuous as provers of the new logic); the retry-path test was added specifically because no existing test exercised the failing case the adversarial review found.


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-15 08:24 UTC*
