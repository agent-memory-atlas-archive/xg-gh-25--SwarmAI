# Autonomous Pipeline Report: tool_call_leak 去容灾化:detect→strip+keep,终止权归模型

**Run ID:** run_63464c2c | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 14:38 UTC | **Duration:** 111.3 min (in progress) | **Tokens:** 107,000
**Gate 1:** N/A | **Files:** 4 | **Tests:** True/1

## TL;DR
tool_call_leak 去容灾化:检测到 leak 时不再 kill/respawn/强制终止,终止权归模型,turn 照常 yield 到自然结束。统一 PURE-LEAK 与 MIXED 两个分支为单一 strip 分支——两种情况都只 best-effort 减污染(strip <invoke> 字面,不落 DB、resume 不回灌),保留 turn,模型自主决定下一步。删除 str

## 1. Requirement
tool_call_leak 去容灾化:检测到 leak 时不再 kill/respawn/强制终止,终止权归模型,turn 照常 yield 到自然结束。统一 PURE-LEAK 与 MIXED 两个分支为单一 strip 分支——两种情况都只 best-effort 减污染(strip <invoke> 字面,不落 DB、resume 不回灌),保留 turn,模型自主决定下一步。删除 streaming_orchestrator.py 的 _has_real_tool_use leak-fork(kill()+raise RuntimeError 路径)。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> tool_call_leak 去容灾化:检测到 leak 时不再 kill/respawn/强制终止,终止权归模型,turn 照常 yield 到自然结束。统一 PURE-LEAK 与 MIXED 两个分支为单一 strip 分支——两种情况都只 best-effort 减污染(strip <invoke> 字面,不落 DB、resume 不回灌),保留 turn,模型自主决定下一步。删除 streaming_orchestrator.py 的 _has_real_tool_use leak-fork(kill()+raise RuntimeError 路径)。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG 指令:终止权归模型,先解决这个 | confirmed | ● | Given 模型把 tool-call XML 当纯文本吐出(pure-leak,无真实 tool_use), when detect_tool_call_leak 命中, then 不调用 kill()、不 raise,strip 后保留 block,turn 继续到自然结束 |
| FR-2 | bug | user-stated: XG 指令 + run_0db67a43 THINK taste decision | confirmed | ● | Given detect 命中, when 无论是否有真实 tool_use, then 都走 strip+keep,无 _has_real_tool_use 二分 |
| FR-3 | task | assumption: code-trace 证实不可达;skeptic SUPPORTED;R25 好的修复删代码 | assumed | ● | Given PURE-LEAK 不再 raise 'Tool-call XML leaked into text channel', when grep 全仓生产代码, then session_unit leak-catch 段 + retry_manager._handle_tool_call_leak + _dispatch_leak_recovery 不可达,予以删除 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | '尽力减污染' 是否需要新 strip 机制? | A. 复用现有 strip_tool_call_leak | 🧠 self |
| Q2 | 放弃 respawn 是否可接受(subprocess 跑偏状态继续)? | A. 可接受,终止权归模型 | 👤 user |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [ASSUMPTION] FR-3: R27 契约迁移:清除 kill 消失后不可达的下游死代码
- [SELF-ANSWERED] Q1: A. 复用现有 strip_tool_call_leak (🧠 AI 替你拍的板 — resolution: 现有 strip 对 clean 文本无损且已是三层 persist 的既有实现;FR-2 的减污染=复用它,非新机制(C042:别一遇问题就造机制)。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 8.00 | |
| Priority | 8.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: streaming_orchestrator.py 的 PURE-LEAK 分支不再调用 kill() 也不再 raise RuntimeError('Tool-call XML leaked into text channel') — 改为与 MIXED 分支一致:strip_tool_call_leak 清洗后保留该 block,turn 继续 yield 到自然结束(观察:grep 该文件无 kill()+raise 的 leak 分支;单测断言 pure-leak 输入下无 kill 调用且 content_blocks 含清洗后文本)
2. AC2: 两个分支(PURE-LEAK / MIXED)统一为单一 strip 路径,_has_real_tool_use 的 leak-fork 删除(观察:detect 命中后无 if not _has_real_tool_use 的二分)
3. AC3: R27 契约迁移——删 kill+raise 后不可达的消费方全部清除:session_unit.py 捕获 'Tool-call XML leaked into text channel' 的整段(~2582-2630)、_dispatch_leak_recovery、retry_manager._handle_tool_call_leak、相关 per-message 状态 _tool_call_leak_recovery(观察:grep 全仓无生产代码 raise 该字符串;grep 这些符号仅剩 test 引用或 0 引用)
4. AC4: 污染不回归——persist 三层无条件 strip(_clean_blocks_for_persist / session_pending / context_injector)保持不变仍生效(观察:这三处未被本次改动触及;单测断言 pure-leak 文本经 persist 路径后 DB 不含 raw <invoke> body)
5. AC5: R27 消费方含测试——删除/改写行为后,断言旧 kill 行为的测试(test_tool_call_leak_recovery.py 等)迁移或删除,不留红;新增单测锁定新契约(detect→strip+keep+不 kill)


## 3. Design & Approach
**Research Findings (THINK):**
- F1: strip 污染防线独立于 detect 且覆盖范围 ⊋ detect —— _clean_blocks_for_persist(session_router.py:107)对每个 text block 无条件 strip,docstring 自述是 'the ONE place assistant content is cleaned before data.db,所有下游 reader 继承干净 DB'。且 strip 用更宽 anchor(_TOOL_CALL_LEAK_STRIP_RE)能清截断的 <invoke(detect 的窄 full-body regex 本来就漏)。结论:去 kill 不削弱污染防线,strip 本来就独立站住。
- F2: 唯一生产 raise 源是 streaming_orchestrator.py:1111。grep 全 backend/core 确认:删它后 session_utils.py:411 retriable 正则、session_unit.py:2582-2630 leak-catch 段、_dispatch_leak_recovery、_handle_tool_call_leak(stub+retry_manager 实现)、_tool_call_leak_recovery 状态(656/2185)全部不可达。
- F3: 既往决策 TECH.md:22(run_2bdec5c0)印证而非冲突本需求——它明确写 'kill-and-resume 会把安静半成品升级成 interrupted+重跑,正是本线要消除的痛点',且回灌环已被 persist 写端切断、截断形态基率仅 0.15%。anti-repetition:本需求是那条决策逻辑的下一步落地,非重蹈已失败路径。

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS / 0.3 session
- QUALITY+DELETION — effort: S / 1 session
- DELETION-conservative — effort: S / 0.8 session

**Chosen Approach:** Approach B(QUALITY+DELETION):把 streaming_orchestrator.py 的 PURE-LEAK 分支从 kill()+raise 改为与 MIXED 分支一致的 strip+keep(统一为单一 strip 路径),然后 R27 契约迁移删尽因 raise 消失而不可达的全部下游死代码(session_unit leak-catch 段 + _dispatch_leak_recovery + _handle_tool_call_leak stub + retry_manager._handle_tool_call_leak + session_utils retriable backstop + _tool_call_leak_recovery 状态),迁移/删除断言旧 kill 行为的测试。persist 三层无条件 strip 保持不变(仅验证仍生效)。

**Success Criteria:**
- detect_tool_call_leak 命中(pure-leak)时:无 kill() 调用、无 RuntimeError raise、content_blocks 含 strip 后文本、turn 正常 yield 结束
- grep -rn 'Tool-call XML leaked into text channel' backend/core 生产代码 0 命中(仅 test)
- grep _dispatch_leak_recovery / _handle_tool_call_leak / _tool_call_leak_recovery backend/core 0 命中
- 受影响测试全绿(迁移后)

**Always:**
- 保留 strip_tool_call_leak 复用(不新建机制)
- persist 三层 strip 原样保留
- 删代码前 grep 确认全仓无生产消费方(R27)

**Never:**
- 不新增任何 kill/respawn/强制终止 leak 的逻辑(去容灾化核心)
- 不新建更强 strip 机制(C042:别一遇问题就造机制)
- 不保留 '以防万一' 的死分支(容灾残留)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_a0822a59 | 9,000 |  |
| think | completed | art_ce2489f0 | 12,000 |  |
| plan | completed | art_293baa4c | 11,000 |  |
| build | completed | art_f1052111 | 42,000 |  |
| review | completed | art_d4757d3e | 16,000 |  |
| test | completed | art_09c0e568 | 17,000 |  |
| deliver | recorded | art_08f33605 | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 107,000 | **Stages:** 6/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 12:52:20 | - |
| think | 12:54:14 | 1.9 min |
| plan | 12:55:27 | 1.2 min |
| build | 14:18:13 | 82.8 min |
| review | 14:20:57 | 2.7 min |
| test | 14:27:41 | 6.7 min |
| deliver | 14:38:03 | 10.4 min |
| reflect | - | - |

Slowest stage: `build` at 82.8 min (78% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

## 5. TDD Results
| Metric | Value |
|--------|-------|
| Tests total | 1 |
| Tests passed | True |
| Tests failed | 0 |
| New tests added | 0 |
| Duration | 0s |
| Regressions | 0 |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| think | 删除边界取 Approach B(删尽死代码)而非 C(保留 retriable backstop) | taste | 保留 backstop 以防万一是容灾残留,与去容灾化需求自相矛盾;grep 确认 streamin |
| review | Fixed LOW stale test docstring in same change (R7 docstring  | mechanical | docstring described removed kill/respawn behavior  |

**Summary:** 1 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 1 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**3 findings** (verdict: ?)
- [LOW] session_router.py:3789 RP48 stale comment — cites a 'TOOL_CALL_LEAK_UNRECOVERED 
- [MED] streaming_orchestrator.py:1071 unbounded-leak: no circuit-breaker if a model lea
- [LOW] red-team confirmed removing the retriable pattern from _is_retriable_error is SA

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/streaming_orchestrator.py`
- `backend/core/session_unit.py`
- `backend/core/retry_manager.py`
- `backend/core/session_utils.py`

**+0 / -0 lines** | 4 files

## 9. Lessons
- [decision] 去容灾化一个 kill/respawn 恢复路径时,正确形态是 R27 契约迁移 + R25 删代码:删掉触发点(kill+raise)后,所有因它不可达的下游(catch 块、dispatcher、recovery 机制、retriable backstop、per-message 状态)构成一个封闭集,一次性全删——grep 全仓 0 production ref + import smoke 验证封闭性,而非留死代码或保留 as-if-might-recur 的 backstop(保留=容灾残留,与去容灾化自相矛盾)。
- [pitfall] 共享工作树多 session 并行时,pytest 全量跑的失败多数不是本次改动:判据=本次 diff 的 +/- 增量。本例 test_silent_except_baseline 22 文件超标,但本次 diff ADD 0 broad-except、REMOVE 3,数学上不可能导致超标;abandon_continuation 2 失败是另一 session 改了 resume-preamble 格式留的 stale test。先用 git diff 增量 + git log -S 定位 symbol 引入点,再判归属(R29),别把别人的未提交改动算进自己的回归。
- [pitfall] detect-gated 的 live-stream 清洗(strip)不是污染防线的全部也不是必需:真正的 durable 防线是 3 层无条件 persist strip(_clean_blocks_for_persist / session_pending / context_injector),它们与 detect 无关且用更宽 anchor(覆盖 detect 漏的截断形态)。所以去掉 detect 门控的 kill 不削弱污染防御——判断一个清洗动作能否删,先 trace 它下游是否还有无条件的 durable 层兜底。
- [decision] adversarial/meta finding 是 lead 不是 verdict:meta-review 报 HIGH observability gap(重复 strip 无 counter/escalation),但对照 XG 显式 scope(先解决这个问题)+ C042/STEERING#21(proposed fix 是 net-new mechanism 且 risk 再加容灾式 circuit-breaker)+ 实证已有 per-event WARN log,判为 out-of-scope follow-up 而非 blocker。严重度标签要对照需求边界核验,不是见 HIGH 就 fix 或就 block。


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 14:38 UTC*
