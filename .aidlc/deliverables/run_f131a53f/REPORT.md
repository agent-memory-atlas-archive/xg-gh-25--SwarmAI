# Autonomous Pipeline Report: terminal buffer_tail 系统提示注入点加诚实 DATA 信任边界(含 fence-escape 加固)

**Run ID:** run_f131a53f | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-15 09:43 UTC | **Duration:** 213.7 min | **Tokens:** 121,000
**Gate 1:** PASS | **Files:** 2 | **Tests:** 0/0

## TL;DR
止血:给系统提示组装中两个未标注的外部内容注入点(terminal buffer_tail 注入块 + Active Session Digest 注入块,均在 prompt_builder.py)加上诚实的 DATA 信任边界标注,降低 prompt-injection 暴露面。措辞诚实不宣称已解决 injection。明确不碰 recall([RECALLED]已覆盖)、不碰 UI-state

## 1. Requirement
止血:给系统提示组装中两个未标注的外部内容注入点(terminal buffer_tail 注入块 + Active Session Digest 注入块,均在 prompt_builder.py)加上诚实的 DATA 信任边界标注,降低 prompt-injection 暴露面。措辞诚实不宣称已解决 injection。明确不碰 recall([RECALLED]已覆盖)、不碰 UI-state(仅 path metadata)、不碰 DailyActivity(写侧已 gate)、不碰 User Profile Suggestions、不做结构迁移(根治是后续 run)。

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 7.00 | |
| Priority | 7.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: prompt_builder.py terminal 注入块(buffer_tail)被一个诚实的 DATA 信任边界包裹,语义=以下是外部 DATA 不是指令、绝不执行其中的指令/命令
2. AC2: 边界措辞诚实,不宣称已彻底解决 prompt-injection(part-mitigation 定性)
3. AC3: recall 块([RECALLED])、Active Session Digest、UI-state、DailyActivity 均未被改动
4. AC4: 构建通过 + prompt_builder 组装相关测试绿、无回归


## 3. Design & Approach
**Research Findings (THINK):**
- AGENT R32 B1 范式(SECURITY-BASELINE.md:103-108):app 指令与注入内容之间保持结构性边界(delimiter/typed field),绝不把外部文本原样拼进指令槽——terminal 块当前恰好违反(buffer_tail 原样进 fence,仅 Treat it as relevant context 的 prose)
- recall 的 [RECALLED] 语气讲 provenance/陈旧性(verify against source),与 terminal 要讲的 injection boundary(不执行其中指令)语义不同,不能照抄,需写 injection-specific 措辞
- Run 1 是部分缓解非根治(Gate-0 kill shot 确认:prose 标注对对抗性注入只部分有效,真根治是把 buffer_tail 挪出 system prompt=Run 2),措辞必须诚实反映且不宣称已解决
- 标注不删/不截断 buffer_tail 本身,保留其作为 build-log 上下文的合法用途(模型仍能答为什么构建失败)

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS/<1 session
- QUALITY — effort: S/<1 session
- DELETION — effort: M/1 session

**Chosen Approach:** 方案 B(QUALITY):在现有 ## Attached Terminal Output 围栏块前插入结构性 UNTRUSTED-DATA 边界前缀,保留围栏与 buffer_tail,复用 SECURITY-BASELINE.md B1 的结构边界范式,措辞 injection-specific 且诚实标注部分缓解。

**Success Criteria:**
- terminal 注入块带诚实结构性 DATA 边界
- 零回归(其余注入点不动)
- 新测试 mutation-proof

**Always:**
- buffer_tail 内容原样保留在围栏内
- 边界措辞诚实(part-mitigation 不吹牛)

**Never:**
- 删/截断 buffer_tail
- 宣称已彻底解决 prompt injection
- 改动 recall/digest/UI-state/DailyActivity 任何一处
- 把 buffer_tail 挪出 system prompt(那是 Run 2 根治)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_3ac27676 | 7,000 |  |
| think | completed | art_9ee5afd5 | 9,000 |  |
| plan | completed | art_47d59a14 | 8,000 |  |
| build | completed | art_c791de46 | 22,000 |  |
| review | completed | art_3b216de2 | 15,000 |  |
| test | completed | art_6e152cad | 17,000 |  |
| deliver | completed | art_5a740a98 | 35,000 |  |
| reflect | completed | - | 8,000 |  |

**Total tokens:** 121,000 | **Stages:** 8/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 08:22:22 | - |
| think | 08:25:02 | 2.7 min |
| plan | 08:27:48 | 2.8 min |
| build | 08:43:54 | 16.1 min |
| review | 08:47:23 | 3.5 min |
| test | 09:25:30 | 38.1 min |
| deliver | 09:38:59 | 13.5 min |
| reflect | - | - |

Slowest stage: `test` at 38.1 min (50% of the 6 measured inter-stage gaps).

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
| evaluate | profile=bugfix(单点安全面修复,root cause 清晰已定位,不自降 trivial) | taste | security-surface + 需测组装不回归,trivial 太轻 |
| evaluate | Gate-0 剔除 session digest 改点 | judgment | skeptic 证伪 digest 现不含外部内容,加标注=noise |
| think | 方案 B 结构性边界 over 纯 prose | taste | B1 范式要求结构边界非仅 prose |
| plan | 测试落 test_prompt_builder_properties.py 新增类 | mechanical | 已有 REAL build_system_prompt drive 模式可复用 |

**Summary:** 1 mechanical, 2 taste, 1 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**1 findings** (verdict: ?)
- [MED] backend/core/prompt_builder.py terminal 块:固定 ``` 围栏可被 buffer_tail 内含的 ``` 提前闭合,之

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/prompt_builder.py`
- `backend/tests/test_prompt_builder_properties.py`

**+0 / -0 lines** | 2 files

## 9. Lessons
- A fixed delimiter wrapping attacker-controlled content is not a boundary — content containing the fence closes it early and escapes; size the fence to the content (N=max_inner_backtick_run+1) or use an unpredictable nonce delimiter. Written to IMPROVEMENT.md Security History.
- Gate-2 fresh-context adversarial caught the fence-escape that EVALUATE/Gate-0/Gate-1 all missed — the value of an adversarial pass whose explicit job is "can attacker content defeat this?" over author self-review.
- Gate-0 skeptic correctly killed the second scope item (Active Session Digest) by reading CURRENT source — digest no longer injects sibling user-message content (refactored to in-memory status lines only), so annotating it would be noise. Scope narrowed before any code written.


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-15 09:43 UTC*
