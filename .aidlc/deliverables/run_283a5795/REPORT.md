# Autonomous Pipeline Report: CLI-native autocompact user-visible notice

**Run ID:** run_283a5795 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 | **Status:** PUSH-READY

## TL;DR
SwarmAI's CLI-native autocompact fired silently — the user never knew the conversation
had been summarized. This adds a one-shot `context_compacted` SSE event (mirroring the
existing `context_warning` path) that surfaces a fixed "conversation was summarized"
toast when the SDK compacts, then the agent continues the task. Pure visibility: no
threshold change, no re-added proactive soft-compact.

## 1. Requirement
让 CLI 原生 autocompact 对用户可见 + 可续接(方案 A 纯可见化):PreCompact 触发时透传 SSE
UI 事件到前端显示提示,compact 完成后展示固定文案告知用户上下文已压缩,agent 自动续接
(post_compact_injection 已有不改)。严禁改 task_budget/阈值,严禁加回被删的主动 soft-compact。

## 2. Evaluation
| Dimension | Score | Rationale |
|---|---|---|
| Strategic | 8/10 | Closes a real UX gap — users confused when history silently changes |
| Priority | 7/10 | Dormant until long sessions, but high-value when it fires |
| Feasibility | 9/10 | Mirrors a proven existing path (context_warning) |

**Scope:** standard | **work_type:** existing-feature | **cross_boundary:** true (SSE/wire + FE↔BE)

## 3. Methodology: DDD + SDD + TDD

### DDD Knowledge Applied
| Stage | Doc | Insight | Decision Impact |
|-------|-----|---------|-----------------|
| THINK | IMPROVEMENT.md | run_2b1957f8 deleted proactive soft-compact (held `_client_io` 300s → froze streaming) | Chose a REACTIVE visibility event, never a proactive compact — avoided repeating the deleted anti-pattern |
| PLAN | TECH.md:73 | "N independent judges must consume ONE authoritative signal" north-star | Backend flag is the sole judge; frontend is pure projection (no 2nd source of truth) |

### Approach
Mirror the `context_warning` SSE path: PreCompact hook sets an independent flag →
`_emit_post_stream_metadata` emits a `context_compacted` event at turn-end → frontend
renders a one-shot info toast. The compaction-completion observable point is the next
result-tail (SDK has no PostCompact callback).

### TDD Cycle
RED (2 failures: method absent) → GREEN → VERIFY. Backend 11 tests + frontend 5 tests
(incl. 3 for the Gate-2 fix). Layer-4 cross-boundary E2E mutation-verified (revert the
`events.append(notice_evt)` contract line → test RED; restore → GREEN).

## 4. Pipeline Execution
| Stage | Status | Key Output |
|---|---|---|
| EVALUATE | done | GO, full, work_type=existing-feature, Gate-0 skeptic SUPPORTED |
| THINK | done | 2 approaches, 5 probes; recommend A (mirror context_warning) |
| PLAN | done | 7 sub-changes → 6 (Gate-1 defer tab-restore); Gate-1 PASS 5/5 |
| BUILD | done | TDD 2R→14G, 8 files, 2 smoke |
| REVIEW | done | Litmus PASS, spec 6/6 IMPLEMENTED, streamGen-guard risk cleared |
| TEST | done | Layer1 AC 14/14, Layer4 E2E mutation-verified, 0 regression |
| DELIVER | done | Gate-2 full tier: 3 findings fixed, 2 LOW accepted; PUSH-READY |

## 5. TDD Results
| Metric | Value |
|---|---|
| Acceptance criteria | 6 |
| Backend tests | 11 (all pass) |
| Frontend tests | 162 (all pass, +5 new for this feature) |
| Smoke tests | 2 (in-process real-object) |
| Layer-4 mutation | revert contract → RED, restore → GREEN ✓ |
| Regressions | 0 |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|---|---|---|---|
| THINK | Approach A over heartbeat path | taste | A matches compaction-completion timing + lowest risk |
| BUILD | compact event at PreCompact-turn, not next-turn | taste | compact completes same turn; result-tail can emit immediately |
| DELIVER | info toast + autoDismiss | taste | compaction is a normal transient event, not an error |
| DELIVER | single-slot race accepted as LOW known limitation | judgment | queue adds complexity to a dormant triple-rare edge (R25); single-slot is accepted codebase convention — surfaced for XG override |

## 7. Quality Gates
| Gate | Result |
|---|---|
| Gate 0 (Understanding) | PASS — skeptic SUPPORTED |
| Gate 1 (Skeptic+SSA) | PASS 5/5 |
| REVIEW | Litmus PASS, spec 6/6, 7 RP checked 0 violations |
| TEST | AC 14/14, Layer4 mutation-verified, 0 regression |
| Gate 2 (Adversarial) | full tier, 5 findings → 3 fixed / 2 LOW accepted |
| Push-Ready | ✅ PUSH-READY |

## 7.5 Adversarial Review (Multi-Specialist)
| Specialist | Dispatched | Findings |
|-----------|-----------|----------|
| Correctness | ✓ | NO FINDINGS (read all files) |
| Integration | ✓ | NO FINDINGS (dict-identity chain verified end-to-end) |
| API Contract | ✓ | NO FINDINGS (field names + enum verified both sides) |
| Operational | ✓ | 1 MED (background-drop) + 1 LOW (fixed-toast-id) |
| Delta review (Gate-2 fix) | ✓ | 1 MED→LOW (single-slot race) + confirmed 6 risks hold |
| Meta-review | ✓ | 1 cross-fix MED (6b active-tab re-fire) → FIXED |

**Findings fixed (3):** background-tab dropped notification; active-tab toast re-fire on
switch-back (6b); fixed-toast-id dedup-merge.
**Accepted (2 LOW):** single-slot React-state race (triple-rare, R25 — queue not worth it);
feature dormancy (intended, mirrors context_warning).

## 7.6 Meta-Review
| Category | Verdict |
|----------|---------|
| Deployment context | LOW — dormant until long session (intended) |
| Operational scaling | CLEAR — O(1) per-turn flag read, 1 nullable per-tab field |
| First-run vs steady | CLEAR — runtime-only, excluded from serialization |
| Architecture (No-Patch) | CLEAR — per-tab persist is the right layer (established pattern) |
| Cross-fix interaction | 1 MED FIXED (6b), 1 LOW accepted (single-slot race) |

## 7.7 Completion Audit
all_green: true | 6/6 ACs IMPLEMENTED + verified | 0 gaps

## 8. Files Changed (10)
- `backend/core/prompt_builder.py` — `build_compact_notice()` + `COMPACT_NOTICE_TEXT`
- `backend/core/hook_builder.py` — PreCompact hook sets independent flag + trigger
- `backend/core/session_unit.py` — `_emit_post_stream_metadata` emits `context_compacted`
- `backend/tests/test_compact_notice.py` — 11 tests (new)
- `desktop/src/types/index.ts` — `CompactionNotice` interface
- `desktop/src/hooks/useChatStreamingLifecycle.ts` — `context_compacted` branch + state
- `desktop/src/hooks/useUnifiedTabState.ts` — per-tab `compactionNotice` field
- `desktop/src/pages/ChatPage.tsx` — info toast useEffect + tab-switch restore consume
- `desktop/src/__tests__/useChatStreamingLifecycle.test.ts` — 5 tests
- `desktop/src/__tests__/helpers/streamingTestUtils.ts` — mock field

## 9. Lessons (REFLECT)
_(populated in REFLECT)_

## 10. Known Gaps & Attention Flags
- **LOW — single-slot React-state race (accepted):** `compactionNotice` is one shared React
  slot (same as `context_warning`/`compaction_guard`). A triple-rare timing (dormant × 2
  concurrent-tab compactions × same-render-batch switch) could drop one INFO toast. Fix =
  a notice queue; deferred per R25 (net complexity for a dormant edge). XG can request the queue.
- **LOW — dormancy:** fires only on real CLI autocompact (rare at 800K budget). Intended.

## 11. Methodology Impact
| Concept | Decision Point | Impact | Counterfactual |
|---------|---------------|--------|----------------|
| DDD (IMPROVEMENT.md) | THINK: run_2b1957f8 lesson | chose reactive event, not proactive compact | would have risked re-introducing the `_client_io` freeze |
| Gate-0 skeptic | EVALUATE | found `_compacted` fire-once race + FE orphan declaration | would have built on a shared flag → dropped signal |
| Gate-2 adversarial | DELIVER | caught background-tab dropped notification (MED) | silent-drop would ship for the exact long-session case the feature targets |
| Meta-review | DELIVER | caught cross-fix 6b active-tab re-fire the Gate-2 fix introduced | duplicate toast on every switch-back |

---
Generated by SwarmAI Autonomous Pipeline | 2026-10-14
