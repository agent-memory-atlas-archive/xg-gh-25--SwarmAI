# Autonomous Pipeline Report: 修 resume preamble 的假上下文自信:三处 preamble 加 COMPRESSED-summary + re-fetch-from-source caveat

**Run ID:** run_6010f022 | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-13 16:00 UTC | **Duration:** 26.3 min (in progress) | **Tokens:** 76,000
**Gate 1:** PASS | **Files:** 4 | **Tests:** True/1

## TL;DR
修复 resume preamble 制造『假上下文自信』：session_router._RESUME_QUERY_HEADER 的『Treat it as background you already know』+ context_injector._CHECKPOINT_PREAMBLE 都暗示 resume 摘要=完整上下文，诱导 agent 对『更早定义过的 finding/编号/决策』

## 1. Requirement
修复 resume preamble 制造『假上下文自信』：session_router._RESUME_QUERY_HEADER 的『Treat it as background you already know』+ context_injector._CHECKPOINT_PREAMBLE 都暗示 resume 摘要=完整上下文，诱导 agent 对『更早定义过的 finding/编号/决策』凭摘要下结论而不先 recall/读 DDD 文档。根因=assistant 把压缩摘要误当完整上下文（EVOLUTION C050/C051 家族第3次复发，SELF.md 已记载的自我系统问题类）。修法=两处 preamble 都显式声明『这是压缩摘要非完整上下文；任何早于本session的 finding/编号/清单/决策的权威源是工作区文档+transcript+recall，不是本摘要；下结论前先 recall/读源』。R27：3个消费点（session_router 常量、retry_manager 复用、context_injector 独立常量）。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 修复 resume preamble 制造『假上下文自信』：session_router._RESUME_QUERY_HEADER 的『Treat it as background you already know』+ context_injector._CHECKPOINT_PREAMBLE 都暗示 resume 摘要=完整上下文，诱导 agent 对『更早定义过的 finding/编号/决策』凭摘要下结论而不先 recall/读 DDD 文档。根因=assistant 把压缩摘要误当完整上下文（EVOLUTION C050/C051 家族第3次复发，SELF.md 已记载的自我系统问题类）。修法=两处 preamble 都显式声明『这是压缩摘要非完整上下文；任何早于本session的 finding/编号/清单/决策的权威源是工作区文档+transcript+recall，不是本摘要；下结论前先 recall/读源』。R27：3个消费点（session_router 常量、retry_manager 复用、context_injector 独立常量）。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG：『不是上下文丢了，是我没去取』是更严重的问题，怎么解决 —— 根因是 preamble 制造假自信 | confirmed | ● | Given cold-resume 走 query 通道, when agent 读到 _RESUME_QUERY_HEADER, then 不再被告知摘要=已知全部，而是被告知先查源 |
| FR-2 | bug | user-stated: XG 直指的根因 + Gate-0 skeptic 发现第三处 _LEGACY_PREAMBLE 同缺 | confirmed | ● | Given 任意一条 resume 路径, when agent 要对早于本session的事下结论, then preamble 已指示先 recall/读源，不凭摘要 |
| NFR-1 | task | ddd-derived: cross_boundary=false：preamble 是拼进 prompt 的字符串常量，无 seam | confirmed | ● | Given 改完, when 跑现有 resume 测试, then 全绿，无回归 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 改一处(_RESUME_QUERY_HEADER)还是全部三处? | B. 三处 preamble 全改 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: B. 三处 preamble 全改 (🧠 AI 替你拍的板 — resolution: self-answer: R27 全消费方 —— grep 出 3 个 resume preamble 常量(_RESUME_QUERY_HEADER / _CHECKPOINT_PREAMBLE / _LEGACY_PREAMBLE)，同一认知缺陷在三条路径都存在，只改一处会在另两条路径复发)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 8.00 | |
| Priority | 8.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: _RESUME_QUERY_HEADER 删去/改写『Treat it as background you already know』这句制造假自信的措辞，改为显式声明『这是压缩摘要非完整上下文』
2. AC2: _RESUME_QUERY_HEADER + _CHECKPOINT_PREAMBLE + _LEGACY_PREAMBLE 三处都新增一条明确指令：任何早于本session的 finding/编号/清单/决策，权威源是工作区文档+transcript+recall，不是本摘要；下结论前先 recall/读源
3. AC3: 不改任何 payload shape/事件/wire/schema —— 纯 preamble 文本措辞变更，现有 resume 行为（provenance 框定、anti-re-execution、END-marker 边界）全部保留
4. AC4: 现有 resume 测试全绿（test_cold_start_resume / test_session_router_pure / test_session_unit_abandon_continuation），新增一条 regression test 断言三处 preamble 都含 completeness/re-fetch caveat


## 3. Design & Approach
**Research Findings (THINK):**
- 三处 preamble 语境不同：_RESUME_QUERY_HEADER 是 query 通道的行内段(provenance+END marker)，_CHECKPOINT_PREAMBLE/_LEGACY_PREAMBLE 是 system-prompt 的 RULES 列表 —— caveat 要贴合各自格式
- 现有 resume 测试断言的是行为(prefix 是否发生、END marker 边界)不是 preamble 精确措辞(grep 三测试文件对 preamble 字符串零命中)—— 改措辞不会红现有测试，但应新增 regression 锁住 caveat 的存在
- _LEGACY_PREAMBLE 在 context_injector.py:1060 的 fallback 分支真实在用(## Previous Conversation Context)，R27 必须同改，否则 fallback 路径复发

**Alternatives Evaluated:**
- SIMPLICITY — effort: S / 1 session
- FLEXIBILITY — effort: S / 1 session

**Chosen Approach:** 三处 resume preamble 各加一句贴合语境的 completeness/re-fetch caveat；_RESUME_QUERY_HEADER 同时替换『Treat it as background you already know』假自信措辞。纯文本常量变更，零行为/契约改动。新增 regression test 断言三处常量都含 caveat（锁住 R27 三处不漏）

**Success Criteria:**
- grep 三处常量，每处都含 re-fetch-from-source caveat 关键词
- _RESUME_QUERY_HEADER 不再 grep 命中『background you already know』
- pytest 三个 resume 测试文件 + 新 regression 全绿

**Always:**
- 保留每处 preamble 现有的 anti-confabulation/anti-re-execution 作用
- 三处同改(R27 全消费方)

**Never:**
- 不改任何 payload shape/事件名/schema
- 不删 END RESUMED HISTORY marker 或 provenance 行
- 不抽共享常量(THINK 落选变体 B，过度工程)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_1f3d1e59 | 9,000 |  |
| think | completed | art_5a1a3181 | 7,000 |  |
| plan | completed | art_cf3883a0 | 8,000 |  |
| build | completed | art_c22e2506 | 15,000 |  |
| review | completed | art_c7921889 | 9,000 |  |
| test | completed | art_5fa518dc | 10,000 |  |
| deliver | completed | art_8f1a0501 | 18,000 |  |
| reflect | ⏭ skipped | - | 0 | Skipped — not required for profile 'bugfix' |

**Total tokens:** 76,000 | **Stages:** 7/7 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 15:36:52 | - |
| think | 15:38:08 | 1.3 min |
| plan | 15:39:13 | 1.1 min |
| build | 15:51:03 | 11.8 min |
| review | 15:53:56 | 2.9 min |
| test | 15:55:55 | 2.0 min |
| deliver | 16:00:17 | 4.4 min |

Slowest stage: `build` at 11.8 min (50% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/7 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

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
| evaluate | work_type=bugfix (改措辞修已引发的认知缺陷，非重构结构) | mechanical |  |
| evaluate | scope 从1处扩到3处 preamble (R27 全消费方) | mechanical | grep 出3个 resume preamble 常量，同缺陷同根 |
| build | session_router 改动被并行 session commit 9c16ec68 原样扫入(R29 verifi | mechanical | grep HEAD 确认 preamble 改动一字不差已提交，非破坏 |
| build | test_session_unit_abandon_continuation 2 个 fail 是我 shell 泄漏  | mechanical | env unset 下 exit=0；这2个旧 test 缺 monkeypatch.delenv  |

**Summary:** 4 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**⚠️ NOT RUN** — adversarial sub-agent was not spawned during this run.
This is a quality gap. Pipeline DELIVER requires adversarial review.

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/session_router.py (in 9c16ec68)`
- `backend/core/context_injector.py`
- `backend/tests/test_session_router_pure.py`
- `backend/tests/test_context_injector.py`

**+0 / -0 lines** | 4 files

## 9. Lessons
**⏭ Skipped** — Skipped — not required for profile 'bugfix'


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-13 16:00 UTC*
