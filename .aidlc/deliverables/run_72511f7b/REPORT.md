# Autonomous Pipeline Report: Bugfix: eliminate the spurious amber 'Interrupted' chip emitted during the tool_

**Run ID:** run_72511f7b | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-14 17:01 UTC | **Duration:** 42.7 min (in progress) | **Tokens:** 81,000
**Gate 1:** PASS | **Files:** 4 | **Tests:** 0/0

## TL;DR
Bugfix: eliminate the spurious amber 'Interrupted' chip emitted during the tool_call_leak kill+--resume recovery cycle. User should see a soft 'recovering/reconnecting' state during a recoverable back

## 1. Requirement
Bugfix: eliminate the spurious amber 'Interrupted' chip emitted during the tool_call_leak kill+--resume recovery cycle. User should see a soft 'recovering/reconnecting' state during a recoverable backend-initiated kill, and a clear coded terminal only on genuinely-unrecoverable (2nd consecutive leak). Must NOT change the data-safety behavior (refusing to persist leaked tool XML).

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Bugfix: eliminate the spurious amber 'Interrupted' chip emitted during the tool_call_leak kill+--resume recovery cycle. User should see a soft 'recovering/reconnecting' state during a recoverable backend-initiated kill, and a clear coded terminal only on genuinely-unrecoverable (2nd consecutive leak). Must NOT change the data-safety behavior (refusing to persist leaked tool XML).

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: frequently seeing Interrupted amber chip | confirmed | ● | Given backend emits an error event with code=TOOL_CALL_LEAK_UNRECOVERED, when frontend error-event handler applies it to the message, then msg.errorCode === TOOL_CALL_LEAK_UNRECOVERED and ChatErrorMessage shows the coded label, not amber Interrupted |
| FR-2 | bug | ddd-derived: preserve existing fallback for genuine connection drops | confirmed | ● | Given an error event or stream death with no code, when rendered, then amber Interrupted shown (unchanged) |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | Is the amber chip from the backend or the frontend? | B. frontend drops the code | 🧠 self |
| Q2 | Should the fix touch the backend data-safety / kill path? | B. no, frontend-only wiring | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: B. frontend drops the code (🧠 AI 替你拍的板 — resolution: Gate-0 skeptic + code-trace: _build_error_event always sets code; grep -rn errorCode desktop/src = zero writes, only TabView.tsx:543 read. event.code never copied to msg.errorCode in useChatStreamingLifecycle.ts error handler.)
- [SELF-ANSWERED] Q2: B. no, frontend-only wiring (🧠 AI 替你拍的板 — resolution: Backend already emits correct coded events; the defect is purely the frontend not reading event.code. Data-safety kill+resume unchanged.)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 5.00 | |

**Acceptance Criteria:**
1. A backend error event carrying a non-null code (e.g. TOOL_CALL_LEAK_UNRECOVERED, AGENT_TIMEOUT) renders with that code in ChatErrorMessage (NOT the amber Interrupted fallback) — verified by a test that drives the error-event handler and asserts msg.errorCode is set.
2. A genuinely code-less error (true connection drop with no backend code) still renders amber Interrupted (fallback preserved).
3. Data-safety behavior (backend refusing to persist leaked tool XML; kill+--resume) is unchanged — no backend edit in this fix.


## 3. Design & Approach
**Research Findings (THINK):**
- errorCode is NEVER written in desktop/src (grep=0 writes); only READ at TabView.tsx:543 -> all coded backend errors render amber Interrupted.
- 1st-leak corrective resume is already transparent; the amber chip is the 2nd-leak TERMINAL event TOOL_CALL_LEAK_UNRECOVERED (coded) whose code the frontend drops.
- Message interface has isError but no errorCode/errorDetail/suggestedAction; TabView reads them via untyped cast so no type error masked the gap.
- Handler already normalizes event.suggestedAction||event.suggested_action; reuse that var + event.code directly.
- CONTEXT_TOO_LARGE/SESSION_BUSY early-return before applyError; leak-terminal/AGENT_TIMEOUT/QUEUE_TIMEOUT reach applyError (single fix point).

**Alternatives Evaluated:**
- SIMPLICITY — effort: S / 1 session
- QUALITY — effort: M / 1 session

**Chosen Approach:** Extract a pure helper errorFieldsFromEvent(event) -> {errorCode?,errorDetail?,suggestedAction?,retryAfter?} into a testable sibling module. In the SSE error-event handler applyError (useChatStreamingLifecycle.ts ~3442), spread the helper output onto the error message so a CODED backend error (e.g. TOOL_CALL_LEAK_UNRECOVERED) carries its code. Add the 4 optional fields to the Message interface. TabView.tsx already reads msg.errorCode -> ChatErrorMessage shows the real coded label; a genuinely code-less event yields errorCode=undefined -> amber Interrupted (fallback preserved).

**Success Criteria:**
- A 2nd-consecutive tool_call_leak renders a RED coded TOOL_CALL_LEAK_UNRECOVERED label with its suggested action, not amber Interrupted.
- Genuine connection drops still show amber Interrupted.
- git diff touches only desktop/src frontend files.

**Always:**
- Preserve amber Interrupted fallback for genuinely code-less errors (FR-2)
- Pure helper has no side effects — testable in isolation

**Never:**
- Do NOT modify any backend file (data-safety kill+--resume must stay unchanged)
- Do NOT change the 1st-leak transparent-resume path (already invisible, correct)
- Do NOT touch the SSE-reader-catch stream-death path (code-less = amber is correct there)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_8663b5bd | 9,000 |  |
| think | completed | art_b583b375 | 8,000 |  |
| plan | completed | art_9e4b7db6 | 9,000 |  |
| build | completed | art_57d366bb | 22,000 |  |
| review | completed | art_7f8feeaf | 16,000 |  |
| test | completed | art_c88ac202 | 17,000 |  |
| deliver | ⏭ skipped | - | 0 | Skipped — not required for profile 'bugfix' |
| reflect | recorded | - | 0 |  |

**Total tokens:** 81,000 | **Stages:** 6/7 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 16:24:53 | - |
| think | 16:28:21 | 3.5 min |
| plan | 16:29:55 | 1.6 min |
| build | 16:38:16 | 8.3 min |
| review | 16:43:48 | 5.5 min |
| test | 16:56:30 | 12.7 min |
| reflect | - | - |

Slowest stage: `test` at 12.7 min (40% of the 5 measured inter-stage gaps).

**Timing coverage:** 6/7 stages resolved, 5 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

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
| evaluate | Root cause is frontend-only (errorCode never written); no ba | judgment | Gate-0 skeptic confirmed SUPPORTED; backend alread |
| plan | Extract pure errorFieldsFromEvent helper for testability vs  | taste | Matches existing pure-fn pattern (blockKey/streami |
| build | Adopted Gate-1 correction: dropped phantom retryAfter field | mechanical | event.retryAfter does not exist on StreamEvent; re |
| review | Single-pass review (4 files <40 lines, no auth/data/infra) + | mechanical | Below fan-out threshold; spec compliance never ski |
| test | Layer-4 E2E renders real ChatErrorMessage within required pr | mechanical | cross_boundary=true mandates Layer 4; mutation RED |

**Summary:** 3 mechanical, 1 taste, 1 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**⏭ NOT RUN** — deliver stage was skipped (profile: bugfix)

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `desktop/src/hooks/errorFields.ts`
- `desktop/src/hooks/__tests__/errorFields.test.ts`
- `desktop/src/types/index.ts`
- `desktop/src/hooks/useChatStreamingLifecycle.ts`

**+0 / -0 lines** | 4 files

## 9. Lessons
- [pitfall] A frontend field that is READ via an untyped cast (msg as Record).errorCode) has NO compiler signal when nothing WRITES it — the amber-for-every-error bug lived because TabView read msg.errorCode while zero code paths set it, and the untyped cast suppressed the type error that would have flagged the missing writer. Typing the field surfaces the write-gap.
- [decision] For a cross-boundary (SSE wire) UI-data fix, the honest Layer-4 E2E renders the REAL component fed by the REAL mapping helper (no mock of the seam) and PROVES non-vacuity by live mutation: revert the one mapping line and confirm the coded-label assertions go RED. A green-on-revert E2E is theater.
- [pitfall] A frontend-only fix embedded in a Tauri .app at build time is NOT delivered by a daemon-only restart — it needs npm run build:all + .app relaunch, else the user sees the stale bundle and reports still-broken. Meta-reviews fire-highest exactly here (code correct, deployment-context wrong).


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 17:01 UTC*
