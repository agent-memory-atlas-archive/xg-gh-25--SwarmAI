# Autonomous Pipeline Report: context_compacted → persistent in-stream notice

**Run ID:** run_d83f22d3 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 | **Status:** PUSH-READY

## TL;DR
The `/compact` (and auto-compact) notice used to be a 5-second toast that vanished before the user could read it — "做没做、做完没有 都没有信息". It is now a **persistent system message in the conversation stream** (a divider showing "Conversation above has been summarized…") that stays put and is reviewable later. The change also deletes three pieces of now-dead toast machinery, making the code simpler than before.

## 1. Requirement
前端 context_compacted 事件改为对话流内持久 system 通知（替换一次性 5s toast）：压缩完成后在 streaming 消息流里插入一条留痕、可回看的 system 消息（文案复用后端 COMPACT_NOTICE_TEXT），active+background tab 都正确，保持 MessageStore 单写者 + per-tab 隔离 + 无 last-write-wins 竞态。

## 2. Evaluation
| Dimension | Score | Rationale |
|---|---|---|
| Strategic | 7/5-scale | Fixes a real, user-reported visibility gap on a core session event |
| Feasibility | 9 | Mirrors the proven resume-boundary store-append path |
| ROI | GO | Small, bounded, high-certainty frontend change |

**Scope:** standard | **work_type:** existing-feature
**Acceptance Criteria:** 7 (AC1 active-append · AC2 verbatim content · AC3 background-tab · AC4 dedup · AC5 TabView divider + no-dim · AC6 toast/slice/types removed · AC7 no regression)

## 3. Methodology: DDD + SDD + TDD

### Approach
Approach A (SIMPLICITY): mirror the resume-boundary frontend-synthetic store-append path — append a `role=system` message (id `compact-<ts>-<rand>`) to the originating tab's MessageStore; TabView renders a new `compact-` divider variant showing the notice text; session-scoped (no backend DB row, per clarification Q1=A). Approach B (backend DB persistence for cold-reload durability) was explicitly deferred as out-of-scope.

### TDD Cycle
RED (4 behavioral tests failed against the toast code) → GREEN (store-append handler) → VERIFY (0 regressions). Mutation-proven: disabling the append turned 4 tests RED.

## 4. Pipeline Execution
| Stage | Status | Artifact | Key Output |
|---|---|---|---|
| EVALUATE | done | art_ae84abdd | GO, full, Gate-0 PASS (skeptic SUPPORTED) |
| THINK | done | art_abc4cec6 | 3 approaches, approach A, reconcile-survival verified |
| PLAN | done | art_b378ba67 | 7 AC, 6-file change spec, Gate-1 PASS |
| BUILD | done | art_66f37e30 | TDD 4R→GREEN, 8 tests, 8 files |
| REVIEW | done | art_15e91c09 | GO, spec PASS, 0 RP violations, id-collision fixed |
| TEST | done | art_af37663a | 290/290, L4 cross-boundary mutation-proven, WTF 2 |
| DELIVER | done | (this) | Gate-2 PASS 0 confirmed, meta CLEAR, PUSH-READY |
| REFLECT | — | — | lessons → DDD |

## 5. TDD Results
| Metric | Value |
|---|---|
| Acceptance criteria | 7 |
| Tests generated | 8 (5 stream-hook + 3 TabView) |
| Bugs caught (RED) | 4 behavioral tests RED pre-impl |
| Regressions | 0 |
| Affected suite | 290 tests pass |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|---|---|---|---|
| EVALUATE | Q1 persistence = session-only (A) | taste | XG said 针对当前session; backend compact not persisted; DB-persist deferred |
| PLAN | `compact-` id prefix (not resume-boundary) | mechanical | avoid wrongly dimming prior messages; mirror refresh- exclusion |
| PLAN | remove compactionNotice slice + restore blocks | taste | dead after store-append; good fixes delete code (R25) |
| REVIEW | id random-suffix | mechanical | 1-line collision defense matching evolution-message precedent |

## 7. Quality Gates
| Gate | Result |
|---|---|
| REVIEW (code quality) | spec PASS (fresh sub-agent 7/7 AC), 0 RP violations |
| REVIEW (integration) | 3 symbols checked, store-append wired, 0 dangling refs (tsc 0) |
| TEST (TDD) | L1 8 · L2 290 · L3 tsc0 · L4 cross-boundary mutation-proven |
| Push-Ready | ✅ PUSH-READY |

## 7.5 Adversarial Review (Multi-Specialist)
| Specialist | Dispatched | Findings | Fixed | Noted |
|-----------|-----------|----------|-------|-------|
| Correctness | ✓ | 1 (MED) | 0 | refuted (false positive — read is inside the `if(compactStore)` guard) |
| Integration | ✓ | 0 | 0 | 0 |
| Red Team | ✓ (>200 lines) | 1 (HIGH) | 0 | refuted (one PreCompact fire = one notice, flag cleared same-tail; reconnect replays buffer, does not re-fire the hook) |

**Confidence gating:** 2 raised → 0 confirmed (both refuted against source per R2).
**Gate value:** HIGH — Red Team's reconnect-double-notice hypothesis forced verifying the backend fire-once mechanism; confirmed one compaction = one notice.

## 7.6 Meta-Review (Pipeline Blind Spot Analysis)
| Category | Verdict | Detail |
|----------|---------|--------|
| Deployment context | CLEAR (LOW) | newline render via whitespace-pre-wrap; RP60 real-machine smoke covers it |
| Operational scaling | RISK (MED) | unbounded compact- dividers in a very-long session — accepted: each real compaction legitimately deserves a marker; typical session 0-3; not fixed (P9) |
| Cross-boundary format | CLEAR | pure projection of backend constant, no encoding assumption |
| First-run vs steady-state | CLEAR | session-scoped synthetic message, no persist/backfill path |
| Architecture integrity | CLEAR | removes net complexity (3 types + slice + 2 restore blocks); right layer |
| Cross-fix interaction | CLEAR | single fix (id suffix), isolated |

**Overall:** CLEAR (1 MED accepted as tech-debt-awareness, 5 LOW)

## 7.7 Completion Audit
All 7 ACs verified with passing tests (see §5 + the 8 test functions). all_green = true, 0 gaps.

## 8. Files Changed
- `desktop/src/hooks/useChatStreamingLifecycle.ts` (modified — context_compacted branch → store-append)
- `desktop/src/pages/chat/components/TabView.tsx` (modified — compact- divider variant + dimming exclusion)
- `desktop/src/pages/ChatPage.tsx` (modified — removed 2 restore blocks + dead import)
- `desktop/src/hooks/useUnifiedTabState.ts` (modified — removed compactionNotice slice)
- `desktop/src/types/index.ts` (modified — removed CompactionNotice + compactionToastPayload)
- `desktop/src/__tests__/useChatStreamingLifecycle.test.ts` (modified — in-stream assertions)
- `desktop/src/__tests__/helpers/streamingTestUtils.ts` (modified — removed slice init)
- `desktop/src/pages/chat/components/__tests__/TabView.compactNotice.test.tsx` (created — AC5 render tests)

## 9. Lessons (from REFLECT)
_(see REFLECT stage)_

## 10. Known Gaps & Attention Flags
- **RP60 real-machine smoke pending** — jsdom cannot verify the multi-line divider's wrapping/overflow/icon alignment. Ship instruction: `cd desktop && npm run build:all` → relaunch the .app → trigger `/compact` → confirm the two-line notice renders in-stream, legibly, and prior messages are not dimmed. (Frontend changes are embedded in the .app at build time; a daemon restart does NOT show them.)
- **Session-scoped by design** — the notice does not survive a cold reload (no backend DB row, per Q1=A). If cold-reload durability is later wanted, approach B (backend persist, like resume_boundary) is a clean follow-up run.
- **Unbounded compact- dividers (MED, accepted)** — a pathologically long session with many real compactions accumulates many dividers; not fixed (each real compaction deserves a marker; typical session 0-3).

## 11. Methodology Impact
| Concept | Decision Point | Impact | Counterfactual |
|---------|---------------|--------|----------------|
| DDD/precedent | THINK found resume-boundary + _applyMerge Pass 2 | reused a proven store-append path instead of inventing a mechanism | would have risked a new reconcile-survival bug |
| TDD RED→GREEN | BUILD, 4 tests RED on toast code | proved the new behavior is actually exercised, not just added | tests-after would have passed by construction |
| Adversarial Review | Red Team HIGH on reconnect double-notice | forced verifying the backend fire-once mechanism — confirmed safe | might have added unnecessary turn-id dedup complexity for a non-problem |
| Gate-1 SSA | verified store-append is root-layer, not a patch | confirmed the right layer before coding | — |

---
Generated by SwarmAI Autonomous Pipeline | 2026-10-14
