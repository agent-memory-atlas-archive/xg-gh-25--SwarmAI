# Autonomous Pipeline Report: Action 3b — delete dead legacy-compat (flat-run read path #11, name-fallbacks #9, verify #10 no-op)

**Run ID:** run_6a51bbb6 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-12 15:58 UTC | **Duration:** 46.4 min (in progress) | **Tokens:** 176,000
**Gate 1:** N/A | **Files:** 8 | **Tests:** True/1

## TL;DR
Action 3b (delete legacy dead code, Kiro #9/#10/#11): remove the legacy flat-run read path (pipeline-run-*.json) from _resolve_run_file + pipelines.py/cmd_run_history/cmd_run_status/cmd_run_analytics 

## 1. Requirement
Action 3b (delete legacy dead code, Kiro #9/#10/#11): remove the legacy flat-run read path (pipeline-run-*.json) from _resolve_run_file + pipelines.py/cmd_run_history/cmd_run_status/cmd_run_analytics globs (#11); collapse s.get('stage', s.get('name','?')) -> s.get('stage','?') at the name-fallback sites OUTSIDE cmd_run_report (B already did the inside ones) (#9); remove the artifact_id=='changeset' sentinel read path (#10). All three legacy forms have ZERO live data (verified). R27: re-grep ALL consumers fresh (v1 list was 60% short). R26 strangler-fig. XG decision: FULL DELETE incl read path.

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 6.00 | |
| Priority | 5.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: #11 legacy flat-run read path fully removed — _resolve_run_file legacy branch (1086-1089) + 4 pipeline-run-*.json globs (728/1667/3785/4369) deleted; _resolve_run_file stays fail-closed sys.exit(1); all 11 callers unaffected
2. AC2: #9 20 persisted-side name-fallback sites collapsed s.get('stage', s.get('name',...)) -> s.get('stage', '?'); EXCLUDED by Gate-0 skeptic verification: 2527 (_incoming = raw --stage-json INPUT, name fallback is LIVE input-tolerance, mirrors the 2623-2624 normalizer), 3716 (x.get('name')=='CI' CI-check name), 5661 (rec.get('stage') or rec.get('name') or-idiom -> collapsed separately to rec.get('stage') or '?')
3. AC3: #10 verified a no-op — the artifact_id=='changeset' sentinel does NOT exist in current code (5818/5819 are _STAGE_ARTIFACT_TYPE map, legitimate); documented, no edit
4. AC4: 0 behavior change — flat-run data verified 0 across workspace; name-collapse preserves default; a regression test asserts _resolve_run_file still fail-closes and name-less stage still yields '?'
5. AC5: no cmd_run_report overlap with Action B (B collapsed 4547/4586/4634 inside cmd_run_report; 3b touches only sites outside it)


## 3. Design & Approach
**Research Findings (THINK):**
- No runtime writer of pipeline-run-*.json exists anywhere in backend (grep for write_text/dump/open-w = 0; the only writer is a test fixture test_pipelines_router.py:190). Skeptic(D) 'reader deleted but writer alive = silent data loss' is REFUTED.
- R27 full consumer sweep found a site the design's list only implied: routers/pipelines.py:169-178 ALSO carries the legacy pipeline-run-*.json glob in the HTTP /api/pipelines read path — must be deleted too. (schemas/pipeline_run.py:4 is a docstring-only mention, no code.)
- test_pipelines_router.py:186 test_corrupt_json_skipped uses a pipeline-run-run_corrupt.json fixture; removing the legacy glob makes that fixture dead → migrate the test to a corrupt NEW-path file so the corrupt-skip behavior stays covered.
- name-fallback: both persisted-write paths normalize name->stage (cmd_run_update 2623-2624->2676; _append_stage_to_run 606 constructs {'stage':...}). 20 reader sites read persisted stages -> name dead -> collapse. 2527 reads RAW --stage-json input -> LIVE -> exclude.

**Alternatives Evaluated:**
- ? — effort: medium
- ? — effort: higher

**Chosen Approach:** Full-delete all legacy flat-run read paths + collapse dead name-fallbacks. 3 source files, test migration included.

**Success Criteria:**
- AC1: artifact_cli.py _resolve_run_file legacy branch (1086-1089) removed; fail-closed sys.exit(1) preserved; the 728 legacy candidate tuple-entry removed
- AC2: artifact_cli.py 3 legacy globs removed (1664-1667 cmd_run_history, 3783-3785, 4368-4369) — delete the legacy-path loop blocks, keep the new-path scan
- AC3: routers/pipelines.py legacy glob (169-178) removed from /api/pipelines read path; new-path scan intact
- AC4: 20 persisted-side name-fallbacks collapsed s.get('stage', s.get('name',...)) -> s.get('stage', <same default>); 5661 or-idiom -> rec.get('stage') or '?'
- AC5: EXCLUDED untouched: 2527 (_incoming raw input), 3716 (CI name), 2623-2624 (the normalizer itself)
- AC6: test_pipelines_router.py::test_corrupt_json_skipped migrated to a corrupt NEW-path file (runs/<id>/run.json) so corrupt-skip stays covered
- AC7: #10 documented no-op (sentinel does not exist); 0 behavior change — regression suite green + a test asserts _resolve_run_file still fail-closes on a missing run


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_c1da2568 | 9,000 |  |
| think | completed | art_09ecd0cc | 7,000 |  |
| plan | completed | art_022b16d4 | 7,000 |  |
| build | completed | art_c944b753 | 55,000 |  |
| review | completed | art_43a82ee1 | 30,000 |  |
| test | completed | art_030573c8 | 20,000 |  |
| deliver | completed | art_d0b40185 | 40,000 |  |
| reflect | completed | - | 8,000 |  |

**Total tokens:** 176,000 | **Stages:** 8/8 completed | **Validation blocks:** 2

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 15:23:06 | - |
| think | 15:24:33 | 1.5 min |
| plan | 15:25:15 | 0.7 min |
| build | 15:41:16 | 16.0 min |
| review | 15:46:16 | 5.0 min |
| test | 15:47:27 | 1.2 min |
| deliver | 15:57:28 | 10.0 min |
| reflect | - | - |

Slowest stage: `build` at 16.0 min (47% of the 6 measured inter-stage gaps).

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
| think |  | ? |  |
| think |  | ? |  |

**Summary:** 0 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 1 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**6 findings** (verdict: ?)
- [LOW] artifact_cli.py _auto_validate_before_advance: collapse to s.get('stage','?') fl
- [LOW] artifact_cli.py _stage_publish_times: or-idiom collapse edge on stage=='' — disp
- [MED] Meta#1 deploy: source change, commit != deployed; daemon runs old confidence_sco
- [MED] Meta#2 engine copy: Projects/SwarmAI/4-capabilities/s_ddd-pipeline/engine/artifa
- [LOW] Meta#3 data-migration: None->'?' default drift only fires on key-less (corrupt) 

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/scripts/artifact_cli.py`
- `backend/scripts/pipeline_validator.py`
- `backend/skills/s_autonomous-pipeline/scripts/confidence_score.py`
- `backend/schemas/pipeline_run.py`
- `backend/routers/pipelines.py`
- `backend/tests/test_advance_continuation.py`
- `backend/tests/test_confidence_score.py`
- `backend/tests/test_pipelines_router.py`

**+0 / -0 lines** | 8 files

## 9. Lessons
(REFLECT stage did not record lessons for this run)


## 10. Known Gaps & Attention Flags
- Validator blocked 2 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-12 15:58 UTC*
