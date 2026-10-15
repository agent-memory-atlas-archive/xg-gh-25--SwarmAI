# Autonomous Pipeline Report: user-side 消息入库 leak-strip 对称化(切断 raw tool-call body 进 data.db)

**Run ID:** run_67250d95 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-15 04:10 UTC | **Duration:** 61.9 min (in progress) | **Tokens:** 82,000
**Gate 1:** N/A | **Files:** 3 | **Tests:** True/1

## TL;DR
user-side 消息入库零 leak-strip:根因已 verified——assistant 持久化走 _clean_blocks_for_persist(session_router.py:1887)过 strip_tool_call_leak,但 user message 持久化(session_router.py:3014 db.messages.put role=user)直接写入

## 1. Requirement
user-side 消息入库零 leak-strip:根因已 verified——assistant 持久化走 _clean_blocks_for_persist(session_router.py:1887)过 strip_tool_call_leak,但 user message 持久化(session_router.py:3014 db.messages.put role=user)直接写入、不过任何清洗。后果实证:全库仅 2 条 raw-leak 残留(data.db,detect_tool_call_leak=True),两条 role 全是 user——用户把上一轮模型 leak 流式显示在屏幕上的裸 <invoke><parameter> body 连同自己的问话一起回灌(样本:ceeb87b7 user msg = '为什么老出这种错误 '+裸invoke body'),user_content 无 strip 直接入库 → resume 时经 context_injector 带回 system prompt → 可能再诱导 leak。模型自己吐的 raw-leak 零条进库(PURE-LEAK 已 kill+drop)。修复:user_content 持久化前过 _clean_blocks_for_persist(与 assistant 路径对称),切断唯一的 raw-leak 进库路径。承重前提 verified:_clean_blocks_for_persist 仅在 1887 assistant 路径调用、3014 user 路径裸 put;strip 对 clean text 无损(run_719886ee)。NON-GOAL(本 run 不做):前端 kill 时撤回已 text_delta 显示的 leak partial(热路径 OT01 家族,独立评估)。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> user-side 消息入库零 leak-strip:根因已 verified——assistant 持久化走 _clean_blocks_for_persist(session_router.py:1887)过 strip_tool_call_leak,但 user message 持久化(session_router.py:3014 db.messages.put role=user)直接写入、不过任何清洗。后果实证:全库仅 2 条 raw-leak 残留(data.db,detect_tool_call_leak=True),两条 role 全是 user——用户把上一轮模型 leak 流式显示在屏幕上的裸 <invoke><parameter> body 连同自己的问话一起回灌(样本:ceeb87b7 user msg = '为什么老出这种错误 '+裸invoke body'),user_content 无 strip 直接入库 → resume 时经 context_injector 带回 system prompt → 可能再诱导 leak。模型自己吐的 raw-leak 零条进库(PURE-LEAK 已 kill+drop)。修复:user_content 持久化前过 _clean_blocks_for_persist(与 assistant 路径对称),切断唯一的 raw-leak 进库路径。承重前提 verified:_clean_blocks_for_persist 仅在 1887 assistant 路径调用、3014 user 路径裸 put;strip 对 clean text 无损(run_719886ee)。NON-GOAL(本 run 不做):前端 kill 时撤回已 text_delta 显示的 leak partial(热路径 OT01 家族,独立评估)。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: 把真正的问题搞清楚+修;根因 verified = user 入库唯一无 strip 缺口 | confirmed | ● | Given 一个 user message content 含裸 <invoke name=X><parameter> body, when 持久化到 data.db, then stored content 的 detect_tool_call_leak=False(body 被 strip) |
| FR-2 | bug | ddd-derived: strip_tool_call_leak run_719886ee 已保证 clean text 字节无损 + fenced 保留 | confirmed | ● | Given 一个无 leak 或仅含 fenced <invoke 讨论的 user message, when 持久化, then content byte-for-byte 不变 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 修 user-side strip 还是也修前端撤回已显示 leak partial? | A. 只修 user-side strip | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. 只修 user-side strip (🧠 AI 替你拍的板 — resolution: 前端撤回碰 streaming 热路径(OT01 家族 33x patch 高危区)且仅体验改善;user-side strip 已切断污染进库这唯一 durable 后果。前端撤回记为独立 known gap(C044/P9 不塞进本 run))

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 5.00 | |

**Acceptance Criteria:**
1. user_content 持久化前经 _clean_blocks_for_persist,一个含裸 <invoke><parameter> body 的 user message 入库后 detect_tool_call_leak(stored)=False
2. clean 的 user message(无 leak)入库 byte-for-byte 不变(strip 无损)
3. fenced/inline 的 <invoke 讨论在 user message 里被保留(不误伤合法讨论)


## 3. Design & Approach
(No design artifact data captured for this run)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_86fff7a4 | 9,000 |  |
| think | completed | art_f78ba19e | 8,000 |  |
| plan | completed | art_2dcacb88 | 0 |  |
| build | completed | art_5ff4d3c1 | 30,000 |  |
| review | completed | art_0937324c | 15,000 |  |
| test | completed | art_5eb62fbe | 20,000 |  |
| deliver | in_progress | art_2dbc71c1 | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 82,000 | **Stages:** 6/8 completed | **Validation blocks:** 2

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 03:11:25 | - |
| think | 03:14:05 | 2.7 min |
| plan | 03:14:51 | 0.8 min |
| build | 04:01:08 | 46.3 min |
| review | 04:03:35 | 2.4 min |
| test | 04:03:51 | 0.3 min |
| deliver | 04:10:12 | 6.3 min |
| reflect | - | - |

Slowest stage: `build` at 46.3 min (79% of the 6 measured inter-stage gaps).

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
| (no decisions) | | | |

**Summary:** 0 mechanical, 0 taste, 0 judgment

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
- `backend/core/session_router.py`
- `backend/core/session_pending.py`
- `backend/tests/test_tool_call_leak_guard.py`

**+0 / -0 lines** | 3 files

## 9. Lessons
- [pitfall] R27 全枚举消费方必须按 MECHANISM 枚举,不是按 API 字面:grep db.messages.put + role:user 漏掉了 session_pending 的 raw INSERT 第二写门(Gate-1 抓到)。一个表的写入可能有绕过 ORM chokepoint 的 raw-INSERT 旁路,枚举要问「谁写这张表」而非「谁调这个方法」。
- [pitfall] 断言含转义的序列化输出会 vacuous:_payload_json 用 dumps_json 把 " 转义成 \",所以 assert '<invoke name="X">' not in payload 恒真(payload 里是 <invoke name=\"X\">),与 strip 是否生效无关(RP47 test-theater)。判定序列化结果要先 decode 回原文再 assert,BUILD 阶段 RED-first 才暴露了它。
- [decision] 污染根因的因果链是 model-leak→text_delta 先上屏→detect 在完整 block 才判→kill 只 drop DB 不撤屏→用户把屏幕残片回灌成 user message→user 入库零 strip→进库。全库 2 条 raw 全是 role=user 回灌实证。fix 选 user-side 入库 strip(切断进库),前端撤回 partial 判为独立 known gap(热路径 OT01 家族,不塞进本 run)。
- [decision] 读门 context_injector 已 strip,所以本 fix 的准确定位是纵深防御+存储层干净,不是唯一路径。但仍有价值:脏数据不该入库,且 data.db 消费方不止 context_injector 一个。


## 10. Known Gaps & Attention Flags
- Validator blocked 2 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-15 04:10 UTC*
