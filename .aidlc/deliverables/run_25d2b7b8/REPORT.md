# Autonomous Pipeline Report: 后端 pending-drain TOCTOU 根治(方向B:cold-spawn coalesce)

**Run ID:** run_25d2b7b8 | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 08:38 UTC | **Duration:** 88.5 min | **Tokens:** 132,000
**Gate 1:** N/A | **Files:** 2 | **Tests:** 165/165

## TL;DR
Backend: a user message queued (server-side pending queue, session_pending.py sent=0) while a session is non-IDLE is stranded forever when the session reaches COLD without passing through a clean IDLE

## 1. Requirement
Backend: a user message queued (server-side pending queue, session_pending.py sent=0) while a session is non-IDLE is stranded forever when the session reaches COLD without passing through a clean IDLE edge (e.g. after a TOOL_CALL_LEAK_UNRECOVERED terminal: streaming→dead→cold). Root cause (Gate-0 SUPPORTED, 3-way: DB 19 stuck rows + code-trace + skeptic): drain_pending fires ONLY on a SessionState.IDLE transition (session_router.py:2813), and the self-heal path (next send re-spawns COLD→IDLE→STREAMING) is a TOCTOU race — the IDLE edge enqueues a drain via put_nowait, but the serial drain worker runs AFTER send() has already advanced the unit to STREAMING, so drain_pending's state!=IDLE guard no-ops and the row is never re-enqueued. Fix (direction B, user-approved): when send() cold-spawns a session that has pending rows, COALESCE the pending set into THIS send's own turn at spawn time (consume them as part of the arriving turn) instead of relying on a transient IDLE edge the serial worker loses the race to. Must respect F1 (no inline re-entrant send/recursion), P4 (exactly-once — claim/mark_sent/rollback), and FIFO-coalesce ordering (combine_pending). Not the frontend drain gap (that was the mis-scoped prior run).

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Backend: a user message queued (server-side pending queue, session_pending.py sent=0) while a session is non-IDLE is stranded forever when the session reaches COLD without passing through a clean IDLE edge (e.g. after a TOOL_CALL_LEAK_UNRECOVERED terminal: streaming→dead→cold). Root cause (Gate-0 SUPPORTED, 3-way: DB 19 stuck rows + code-trace + skeptic): drain_pending fires ONLY on a SessionState.IDLE transition (session_router.py:2813), and the self-heal path (next send re-spawns COLD→IDLE→STREAMING) is a TOCTOU race — the IDLE edge enqueues a drain via put_nowait, but the serial drain worker runs AFTER send() has already advanced the unit to STREAMING, so drain_pending's state!=IDLE guard no-ops and the row is never re-enqueued. Fix (direction B, user-approved): when send() cold-spawns a session that has pending rows, COALESCE the pending set into THIS send's own turn at spawn time (consume them as part of the arriving turn) instead of relying on a transient IDLE edge the serial worker loses the race to. Must respect F1 (no inline re-entrant send/recursion), P4 (exactly-once — claim/mark_sent/rollback), and FIFO-coalesce ordering (combine_pending). Not the frontend drain gap (that was the mis-scoped prior run).

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG picked direction B after root cause confirmed | confirmed | ● | Given a session with N pending sent=0 rows, currently COLD, when a user sends a new message that cold-spawns it, then the N pending rows + the new message are delivered as one FIFO-coalesced turn and flipped sent=1 on success |
| FR-2 | enabler-story | ddd-derived: session_pending F4/P4 contract | confirmed | ● | Given the coalesced turn errors or never reaches a result, when delivery fails, then the set rolls back to pending (sent=0), nothing marked sent, nothing double-sent |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | fix direction among A/B/C | B. coalesce into send turn | 👤 user |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
✅ 无未闭合问题 (no leftover — all requirements closed, no AI assumptions)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 9.00 | |
| Priority | 9.00 | |
| Feasibility | 7.00 | |

**Acceptance Criteria:**
1. AC1: a user message persisted sent=0 while a session is non-IDLE is DELIVERED (combined into one turn, FIFO latest-last) when the next send cold-spawns that session WITHOUT waiting for a later clean IDLE edge; verified by a test that enqueues pending, drives a cold-spawn send, asserts the pending text reaches run_conversation AND is flipped sent=1.
2. AC2: exactly-once preserved - a pending set delivered via the new cold-spawn coalesce path is mark_sent only on an observed result + no error event; a failed/aborted turn rolls back to pending (sent=0); claim/mark_sent/rollback reused, not reimplemented.
3. AC3: no F1 regression - the new coalesce is NOT a re-entrant send()/run_conversation recursion; proven by a test that the drain worker + cold-spawn path do not both deliver the same seqs (no double-drain, claim atomicity).
4. AC4: the existing IDLE-edge drain path still works for the normal case (msg queued during an active turn, drained when that turn completes to IDLE) - regression test stays green.


## 3. Design & Approach
**Research Findings (THINK):**
- The drain orchestration layer is session_router.run_conversation (2968), NOT session_unit. run_conversation builds user_content (3087), persists it (3095), acquires slot, then delegates to unit.send() (3599). All pending primitives (claim_pending_batch / combine_pending / mark_sent_batch / rollback_claim_batch) live in session_router and session_pending. So direction B is orchestrated in run_conversation at the router layer with NO layering violation (the pre-mortem risk is REFUTED).
- drain_pending (2864) already encapsulates the full claim->combine->deliver->mark_sent/rollback lifecycle with F1/P4/F4 handling (2886-2964). Direction B reuses these SAME primitives from a reliable trigger point (the cold-spawn send path) instead of the serial worker that loses the IDLE-edge race.
- claim_pending_batch (session_pending.py:405) is atomic under the per-session seq lock and only takes sent=0 AND claimed_at IS NULL rows; a concurrent claimer (the serial drain worker) that loses the race gets an empty set. This is the exactly-once guard preventing double-delivery.
- combine_pending (session_pending.py:498) merges FIFO latest-last (text joined, multimodal flattened). The arriving user message must be appended AFTER the pending set so a correction reads most-salient-last; existing drain semantics, reused verbatim.

**Alternatives Evaluated:**
- QUALITY — effort: M / 1 session
- SIMPLICITY — effort: S / 1 session

**Chosen Approach:** Direction B: coalesce the server-side pending set into the cold-spawn send turn, in session_router.run_conversation, reusing the existing session_pending primitives. Insertion point: after is_cold_resume is computed (session_router.py:3231, which keys on unit.state==COLD) and BEFORE unit.send() (3599). When the turn will cold-spawn (unit.state==COLD) AND there are pending rows, atomically claim_pending_batch; if non-empty, combine_pending(claimed) and PREPEND the pending payload to query_content (pending FIFO first, the arriving user message last so a correction reads most-salient-last); remember the claimed seqs; after unit.send() streams, mark_sent_batch on an observed terminal result + no error event, else rollback_claim_batch. Extract the claim->combine->deliver-observe->mark/rollback body into ONE shared helper used by BOTH drain_pending (the serial worker) and this new cold-spawn path (one lifecycle, two triggers). Double-delivery with the serial worker is prevented by claim_pending_batch atomicity (only sent=0 AND claimed_at IS NULL; the loser gets []).

**Success Criteria:**
- A pending message queued while a session is non-IDLE is delivered on the next cold-spawn send without needing a later clean IDLE edge (the 19-stuck-rows class cannot recur).
- Exactly-once holds: no message lost (rollback on failure) and none double-sent (claim atomicity vs the serial worker).
- The IDLE-edge drain path is unchanged for the in-turn-queue normal case.

**Always:**
- reuse claim/combine/mark_sent/rollback (never reimplement the lifecycle)
- mark_sent ONLY on observed result + no error (F4 no-loss)
- pending FIFO order preserved, arriving msg last (combine_pending semantics)

**Never:**
- do NOT re-enter run_conversation/send recursively from the coalesce path (F1)
- do NOT delete/overwrite pending rows except via mark_sent/rollback (STEERING #20 data-safety)
- do NOT mark_sent before an observed terminal result


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_e3aac158 | 9,000 |  |
| think | completed | art_b18663c3 | 11,000 |  |
| plan | completed | art_30528c56 | 12,000 |  |
| build | completed | art_71d614a2 | 40,000 |  |
| review | completed | art_4bfa8dc9 | 15,000 |  |
| test | completed | art_35803139 | 25,000 |  |
| deliver | completed | art_809e6880 | 20,000 |  |
| reflect | completed | - | 0 |  |

**Total tokens:** 132,000 | **Stages:** 8/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 06:54:08 | - |
| think | 07:29:38 | 35.5 min |
| plan | 07:31:33 | 1.9 min |
| review | 07:46:06 | 14.6 min |
| deliver | 08:14:26 | 28.3 min |
| test | 08:18:15 | 3.8 min |
| build | 08:38:35 | 20.3 min |
| reflect | - | - |

Slowest stage: `think` at 35.5 min (34% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

## 5. TDD Results
| Metric | Value |
|--------|-------|
| Tests total | 165 |
| Tests passed | 165 |
| Tests failed | 0 |
| New tests added | 10 |
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
| TEST (suite) | 165/165 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**4 findings** (verdict: ?)
- [HIGH] session_router.py run_conversation: claim-send-finalize span had only try/except
- [HIGH] session_router.py run_conversation: 2nd adversarial round -- delivered set final
- [MEDIUM] session_router.py run_conversation: arriving msg block-to-path-hint converted BE
- [MEDIUM] session_router.py: comment claimed the coalesce path skips channel/client_id tur

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/session_router.py`
- `backend/tests/test_session_drain.py`

**+626 / -22 lines** | 2 files

## 9. Lessons
- [pitfall] 给异步生成器加 claim->deliver->finalize 恰好一次生命周期时,finalize 必须挂在交付被确认的那一刻(观察到 result 立即 mark_sent),绝不能挂在循环结束之后:生成器可能在 result 帧下游 yield 处被 SSE 断连关闭(GeneratorExit),循环后 finalize 永不执行,而 finally 会把已交付集合回滚->下次重发双投。disconnect-after-result 与 abandoned-generator 是同一 try/finally 的两张脸,finally 治了后者却给前者开新口子。
- [principle] 修一个对抗发现的 bug 之后必须对修复本身再发一轮对抗——修 bug 极常引入新 bug:本 run 第一轮对抗发现 GeneratorExit 数据丢失 HIGH,加 finally 修掉;第二轮对抗立刻发现这 finally 在 result-after-disconnect 场景制造双投 HIGH。self-review 不会发现自己刚写的东西的问题(authorship trap),只有 fresh-context 对抗会。
- [pitfall] 当一个值在流水线某步被规范化(arriving message 的 block->path-hint conversion),而后续步骤把未经该步的新数据合并进来(coalesce 把 pending blocks 并进 query_content),被合并数据绕过规范化。规则:任何先转换后合并的序,合并后必须对合并结果重跑转换(幂等即安全)。
- [correction] R7:注释声称了代码没有的行为(skip channel/client_id turns 但 guard 只有 if not _drained_pending)。对抗把它当 scope-creep 嫌疑揪出。修法是让注释说真话,不是改代码——因为代码行为(channel 也 coalesce)本就正确。
- [decision] exactly-once 恢复路径分层:同步可达窗口(claim 到 send 间无 await)无需 finally;await 边界的 BaseException(GeneratorExit/CancelledError)必须 finally 兜底;await-in-finally 自身被 cancel 的极端残留交给 startup reopen_dangling_claims 最终兜底,不在热路径追求绝对闭合。
- finalize-on-result not after-loop
- adversarial-after-fix mandatory
- convert-after-merge


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 08:38 UTC*
