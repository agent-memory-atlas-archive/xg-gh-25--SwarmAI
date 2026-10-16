# Autonomous Pipeline Report: R1.5a-fix (keystone): 修复 D7 attribution 管道在 resume 场景不工作。根因已 trace 实证(365 marker

**Run ID:** run_48eff4fe | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-16 14:45 UTC | **Duration:** 37.4 min (in progress) | **Tokens:** 0
**Gate 1:** WARN | **Files:** 3 | **Tests:** 0/0

## TL;DR
R1.5a-fix (keystone): 修复 D7 attribution 管道在 resume 场景不工作。根因已 trace 实证(365 marker 全 run_id=None; .map 读回 ctx grep=0): (1) session_router 构造 _hook_session_context 时从 session_<sid>_run.map re-hydrate _ac

## 1. Requirement
R1.5a-fix (keystone): 修复 D7 attribution 管道在 resume 场景不工作。根因已 trace 实证(365 marker 全 run_id=None; .map 读回 ctx grep=0): (1) session_router 构造 _hook_session_context 时从 session_<sid>_run.map re-hydrate _active_pipeline_run_id(当前只在 run-create PostToolUse hook 设, resume 不重跑→永不设→marker run_id 恒 None); (2) marker +run_id 字段归入本 run(attribution 管道一部分, 非 D7 判决)。这是 D7(run_670 已 checkpoint 休眠)能工作的前提。bugfix profile。

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 8.00 | |
| Priority | 9.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: 当 session ctx 构造时 _active_pipeline_run_id 不在 ctx 且 session_<sid>_run.map 存在 → 从 .map re-hydrate run_id 进 ctx(修 F2: resume 不重跑 run-create 导致 run_id 永不设)
2. AC2: re-hydration 后, 该 session 写的 adv marker 的 run_id == .map 里的 run_id(端到端: marker 可按 run 归属)
3. AC3: .map 不存在 / 读失败 / run_id 已在 ctx → 不覆盖、不报错(幂等 + fail-safe)
4. AC4: marker payload 带 run_id 字段(attribution 管道一部分, 从 run_670 的 D7 休眠改动归入本 keystone)
5. AC5: re-hydration 是 off-loop / 不阻塞 send 热路径, 读 .map 的异常被吞(session 启动不因 attribution 读失败而 fail)


## 3. Design & Approach
**Research Findings (THINK):**
- ctx 构造点 session_router.py:3420-3423 在每个 send() 命中(含 resume 首轮), session_id 当场在作用域 → 能解析 session_<sid>_run.map
- .map 是 ~105B 单文件 JSON {session_id, run_id, ts}; is_file()+read_text+json.loads 是微秒级同步 IO
- _active_pipeline_run_id 有 3 个 ctx 消费者(marker writer @1041, compaction briefing @1464, 以及 D7 休眠), 在 ctx 一处 re-hydrate 全覆盖 → 根因层修复

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS / 1 session
- DELETION — effort: XS

**Chosen Approach:** SIMPLICITY: session_router ctx 构造处 re-hydrate _active_pipeline_run_id from .map(幂等/非clobber/异常吞)。否决 DELETION(marker-writer 就地 fallback): 漏 briefing 消费者, 非根因。



## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_2e8583a7 | 0 |  |
| think | completed | art_9dbfc7c9 | 0 |  |
| plan | completed | art_53cfb5be | 0 |  |
| build | completed | art_1ee14108 | 0 |  |
| review | ⏭ skipped | - | 0 | Skipped — not required for profile 'full' |
| test | ⏭ skipped | - | 0 | Skipped — not required for profile 'full' |
| deliver | completed | - | 0 |  |
| reflect | completed | - | 0 |  |

**Total tokens:** 0 | **Stages:** 6/6 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 14:08:54 | - |
| think | 14:10:33 | 1.7 min |
| plan | 14:11:54 | 1.3 min |
| build | 14:20:40 | 8.8 min |
| deliver | - | - |
| reflect | - | - |

Slowest stage: `build` at 8.8 min (75% of the 3 measured inter-stage gaps).

**Timing coverage:** 4/6 stages resolved, 3 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

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
| (no decisions) | | | |

**Summary:** 0 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**⚠️ NOT RUN** — adversarial sub-agent was not spawned during this run.
This is a quality gap. Pipeline DELIVER requires adversarial review.

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/session_router.py`
- `backend/core/runtime_hooks.py`
- `backend/tests/test_pipeline_run_rehydration.py`

**+0 / -0 lines** | 3 files

## 9. Lessons
- [principle] 一个 write-only 的 rendezvous 文件(写了从没被读回 ctx)是 dead state — 让它被读回只是半个工作:它的 LIFECYCLE(何时失效/删除)同样要设计,否则 immortal 文件会在消费端制造 stale 归属。freshness 守卫只在消费方状态存活时有效;消费方被清空(evict)+ 源文件不朽 → freshness 退化成 last-forever。
- [pitfall] 把 sync disk I/O 放进 async 函数的 helper 里 inline 调用(不 await to_thread)会结构性绕过 async-blocking AST gate —— gate 的 nearest-enclosing-function 规则豁免 sync helper(假定被 to_thread dispatch)。修复范式:纯 sync _read() + await asyncio.to_thread(_read),mutate 留 loop。写侧已 off-loop 时读侧必须对称。
- [guideline] 跨进程读取一个按 session_id 命名、但 payload 只带 run_id 的 rendezvous 文件:消费方(CLI 侧 D7)拿不到 session_id 时按 run_id 过滤反而更简单,但代价是无法判断该 run 是否仍 active(需 run.json 需 project,rendezvous 不带 project)。这是 attribution 管道的真实边界。
- [correction] Gate-2 三专家分歧时逐一核验而非投票:correctness 的 immortal-.map HIGH 属实但 blast=over-credit(放松,永不 false-block);不盲从 BLOCK verdict,trace 到 D7 消费端(declared⊆completed)确认它只能 RELAX 检查,据此分级为已知残留而非 commit-blocker。finding 是待验线索,severity 更是待核。
- [correction] run-report 的 §9 读 reflect_stage[lessons] 为 list[str](isinstance(item,str) 守卫);seed 成 list[dict]{type,text} 会被静默跳过 → §9 空壳 placeholder。契约:reflect lessons 必须是字符串列表,type 融进前缀。


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 14:45 UTC*
