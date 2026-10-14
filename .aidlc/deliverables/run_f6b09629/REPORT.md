# Autonomous Pipeline Report: EVALUATE 需求理解实时可见(_display_block)

**Run ID:** run_f6b09629 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 | **Status:** PUSH-READY

## TL;DR
The pipeline's "需求理解" clarification block — the FR/assumption summary a user should
see in the streaming chat during EVALUATE — had no backend producer: it was a pure
`[MUST]` instruction telling the agent to hand-type it, so attention decay meant it
almost never appeared. This change makes the structurally-mandatory `publish --stage
evaluate` CLI step return that block already CLI-rendered (as a `_display_block` field in
its result JSON, reusing the same `render_audit_trail_md` the run-end REPORT §4.6 uses).
The agent now relays a ready-made block instead of recalling-and-retyping — eliminating
the "only-by-discipline" exception while keeping preview and archive on one render source.

## 1. Requirement
让 pipeline 的「需求理解澄清」(EVALUATE 产出的 requirements[]/clarifications[]:什么被确认、
什么是 AI 替用户拍板的假设)在 streaming response 里实时可见,从靠 agent 自觉手敲升级为结构性可靠机制。

## 2. Evaluation
→ GO | profile: full | work_type: existing-feature
**Gate 0 (Understanding):** PASS — SUPPORTED by independent skeptic. Current-state
code-trace: streaming side has ZERO backend code vs REPORT side mechanically rendered —
a presentation-reliability asymmetry. Anti-repetition hit a POSITIVE precedent
(IMPROVEMENT.md F004 fix = eliminate-the-exception, not remind-harder).

## 3. Methodology: DDD + SDD + TDD
### DDD Knowledge Applied
| Stage | Doc | Insight | Decision Impact |
|-------|-----|---------|-----------------|
| EVALUATE | IMPROVEMENT.md (F004) | "fix = make it identical to the other mechanisms, not remind harder" | Chose to move render into the mandatory CLI step rather than strengthen the `[MUST]` prose |

### Approach
Approach A (SIMPLICITY): the mandatory `publish --stage evaluate` returns the rendered
block as a `_display_block` result field (non-quiet only); gate matches the REPORT §4.6
condition exactly so preview/archive share one render source and cannot drift.

### TDD Cycle
RED (1 tracer test fails — no `_display_block`) → GREEN (implement gated best-effort
block) → VERIFY. 9 AC-driven tests, all green.

## 4. Pipeline Execution
| Stage | Status | Artifact | Key Output |
|---|---|---|---|
| EVALUATE | done | art_5fe67dff | GO, full, existing-feature |
| THINK | done | art_fc071d4b | 3 alternatives, recommend A; "verify-emit is a non-sequitur, CLI-render is the ceiling" |
| PLAN | done | art_a0625410 | A1 (_display_block field) after Gate-1 BLOCK#3 fixed A2→A1 |
| BUILD | done | art_8ccbd75d | 1 code file + 2 docs + 1 test, TDD 1 red/green |
| REVIEW | done | art_d4981480 | spec PASS (fresh sub-agent, 7/7 AC), 0 findings |
| TEST | done | art_32a60ce7 | L1 9/9 + L2 80/80 + L3 smoke 2/2, 0 regr |
| DELIVER | done | (this) | adversarial 3 specialists, meta-review, PUSH-READY |

## 5. TDD Results
| Metric | Value |
|---|---|
| Acceptance criteria | 7 |
| Tests generated | 9 |
| Bugs caught (RED) | 1 (missing field) |
| Smoke tests | 1 (in-process, real render path) |
| Regressions | 0 |
| Total | 9 new + 80 dependency-scoped, all passing |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|---|---|---|---|
| PLAN | A1 result-field vs A2 appended-markdown | taste | A2 breaks stdout single-JSON contract (Gate-1 BLOCK#3) |
| BUILD | gate mirrors REPORT bare-truthy (not isinstance-list) | mechanical | zero-drift; render_audit_trail_md degrades non-list itself |

## 7. Quality Gates
| Gate | Result |
|---|---|
| REVIEW (spec) | PASS — fresh sub-agent, 7/7 AC IMPLEMENTED |
| REVIEW (integration/litmus) | PASS, 0 findings |
| TEST (3 layers) | 9/9 + 80/80 + 2/2, 0 regressions |
| VALIDATOR | all stages valid |
| Push-Ready | ✅ PUSH-READY |

## 7.5 Adversarial Review (Multi-Specialist)
| Specialist | Dispatched | Findings | Fixed | Noted |
|-----------|-----------|----------|-------|-------|
| Correctness | ✓ | 0 HIGH/MED (mutation-proved non-vacuous) | 0 | 1 LOW (dup gate logic) |
| Integration | ✓ | 1 HIGH + 1 MED | 2 | 0 |
| API Contract | ✓ | 0 HIGH/MED | 0 | 1 LOW (docstring) |

**Key findings fixed:**
| ID | Specialist | Finding | Fix |
|----|-----------|---------|-----|
| I-1 | Integration (HIGH) | INSTRUCTIONS.md "ALWAYS --quiet in pipeline" contradicted the new relay instruction (quiet suppresses `_display_block`, hand-type fallback removed → user sees nothing) | Carved out the evaluate publish on desktop/direct runs from the blanket --quiet rule |
| I-2 | Integration (MED) | Gate not the "VERBATIM" mirror the comment claimed — publish used `isinstance(...,list)`, REPORT uses bare truthy → drift on non-list requirements | Aligned publish gate to REPORT bare-truthy; drift verified 0/7 shapes; corrected the comment |
| A-1 | API (LOW) | cmd_publish docstring didn't declare `_display_block` | Added contract line to docstring |

**Gate value:** HIGH — the Integration HIGH (I-1) would have shipped a feature that is
UNREACHABLE for any agent following the standing --quiet rule. Self-review missed it;
fresh-context adversarial caught it.

## 7.6 Meta-Review (Pipeline Blind Spot Analysis)
| Category | Verdict | Detail |
|----------|---------|--------|
| Deployment context | CLEAR | inline import inherits the proven `__file__`-abs sys.path; try/except adds a fail-open guard |
| Operational scaling | LOW | block size grows with requirements[] count, uncapped — bounded in practice; REPORT path is the real stress case, unchanged |
| Cross-boundary format | CLEAR | CJK round-trips cleanly via json default ensure_ascii; standard for the file |
| First-run vs steady-state | LOW→addressed | one evaluate publish/run; the publish(data) vs REPORT(archived) source gap pinned by a new round-trip drift test |
| Architecture (no-patch) | CLEAR | root-cause fix: reuses existing renderer, eliminates the discipline exception, zero duplication |
| Cross-fix interaction | CLEAR | the 3 fixes compose; gate-alignment PREVENTS drift rather than causing it |

**Overall:** RISKS_IDENTIFIED (6 LOW, 0 HIGH) — 1 acted on (drift round-trip test added),
rest accepted as documented LOW tech-debt.

## 7.7 Completion Audit
| # | Acceptance Criterion | Evidence | Verified |
|---|---------------------|----------|----------|
| 1 | non-quiet evaluate+reqs → `_display_block` | test_ac1 | ✅ |
| 2 | stdout single JSON; quiet clean | test_ac2 | ✅ |
| 3 | stage≠evaluate → no block | test_ac3 | ✅ |
| 4 | no reqs / legacy schema → no block | test_ac4 ×2 | ✅ |
| 5 | verbatim render_audit_trail_md reuse | test_ac5 + drift round-trip | ✅ |
| 6 | render-fail best-effort, visible degrade | test_ac6 | ✅ |
| 7 | docs relay (not hand-type) | test_ac7 | ✅ |

**Gaps:** 0 | **Fixed:** 0 | **Attention flags:** 0

## 8. Files Changed
- `backend/scripts/artifact_cli.py` (modified, +53 — cmd_publish `_display_block` + docstring)
- `backend/skills/s_autonomous-pipeline/stages/evaluate.md` (modified — §4.6.4 relay instruction)
- `backend/skills/s_autonomous-pipeline/INSTRUCTIONS.md` (modified — Phase-2 relay + --quiet carve-out)
- `backend/tests/test_publish_display_block.py` (created, 9 tests)

## 9. Lessons (from REFLECT)
- A `[MUST]` instruction with no code backing is an F004 time bomb; the fix is to move
  the effect into a mechanically-mandatory step, not to word the instruction harder.
- A "mirror" comment claiming VERBATIM must actually be verbatim — a stricter check on
  one side than the mirrored side silently reintroduces the drift the mirror forbids.
- When one doc states a blanket rule ("ALWAYS --quiet") and a feature needs the opposite,
  the blanket rule must be amended with the carve-out — leaving them in contradiction
  makes the feature unreachable for anyone following the blanket rule.

## 10. Known Gaps & Attention Flags
- LOW (accepted): `_display_block` size uncapped — if ever needed, cap in
  `render_audit_trail_md` so BOTH consumers inherit it (never only at the publish site).
- LOW (accepted): publish gate logic is hand-duplicated with the REPORT §4.6 gate; a
  comment warns to keep them in lockstep if `render_audit_trail_md` is ever hardened.

## 11. Methodology Impact
| Concept | Decision Point | Impact | Counterfactual |
|---------|---------------|--------|----------------|
| DDD Knowledge | EVALUATE anti-repetition hit F004 precedent | Shaped the whole approach toward eliminate-the-exception | Would have strengthened the `[MUST]` prose — the proven-ineffective path |
| Gate-1 Skeptic | PLAN: BLOCK#3 on stdout contract | Flipped A2 (appended markdown) → A1 (result field) before any code | Would have shipped a stdout-contract break that fails the pipeline's own json.load parse habit |
| Adversarial Review | DELIVER: Integration HIGH I-1 | Caught the --quiet contradiction that made the feature unreachable | Would have shipped a feature no pipeline-following agent could ever trigger |

---
Generated by SwarmAI Autonomous Pipeline | 2026-10-14
