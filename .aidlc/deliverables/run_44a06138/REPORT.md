# Autonomous Pipeline Report: Artifact subsystem trust boundary (P0 path-traversal fix)

**Run ID:** run_44a06138 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-12 13:52 UTC | **Duration:** 40.8 min (in progress) | **Tokens:** 232,000
**Gate 1:** N/A | **Files:** 6 | **Tests:** True/1

## TL;DR
P0 security: single trust boundary for ALL caller-supplied path identifiers (project + run_id + entry.file) in the artifact subsystem. Fix path traversal (Kiro #1 run_id + #1b project), fail-closed pu

## 1. Requirement
P0 security: single trust boundary for ALL caller-supplied path identifiers (project + run_id + entry.file) in the artifact subsystem. Fix path traversal (Kiro #1 run_id + #1b project), fail-closed publish order (#2), phantom-run existence check (#3), OpenAPI run_id honesty (#13). Containment via Path.is_relative_to (macOS case-insensitive). Files: artifact_registry.py, artifact_cli.py cmd_publish+_load_artifact_for_metrics, routers/artifacts.py.

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> P0 security: single trust boundary for ALL caller-supplied path identifiers (project + run_id + entry.file) in the artifact subsystem. Fix path traversal (Kiro #1 run_id + #1b project), fail-closed publish order (#2), phantom-run existence check (#3), OpenAPI run_id honesty (#13). Containment via Path.is_relative_to (macOS case-insensitive). Files: artifact_registry.py, artifact_cli.py cmd_publish+_load_artifact_for_metrics, routers/artifacts.py.

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: pipeline is primary deliver engine, must be clean; Kiro #1 + adversarial #1b | confirmed | ● | Given a .. or absolute or sibling-escaping identifier, when publish or read is called, then it raises before any mkdir/write/read and nothing lands outside the project |
| FR-2 | bug | user-stated: Kiro #2 | confirmed | ● | Given an invalid identifier at CLI cmd_publish, when publish runs, then exit non-zero AND zero artifact files created |
| FR-3 | bug | user-stated: Kiro #3 | confirmed | ● | Given run_id with no runs/<id>/run.json, when stage-linked publish, then raises/404; no runs/<id>/ dir minted |
| FR-4 | bug | user-stated: Kiro #13 | confirmed | ● | Given a publish request with absent run_id, when validated by Pydantic, then 422, and the schema shows run_id required |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | run_id format contract? | A. ^run_[A-Za-z0-9_]+$ | 🧠 self |
| Q2 | Does fixing project traversal risk breaking legit multi-project publishes? | A. no — all real projects are direct children of Projects/ | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. ^run_[A-Za-z0-9_]+$ (🧠 AI 替你拍的板 — resolution: self-answer: scanned 831 live run dirs, 100% match ^run_[A-Za-z0-9_]+$; _gen_run_id emits run_<8hex>, strictly narrower)
- [SELF-ANSWERED] Q2: A. no — all real projects are direct children of Projects/ (🧠 AI 替你拍的板 — resolution: self-answer: all 9 live projects are direct children of Projects/; is_relative_to(projects_root) passes every one)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 5.00 | |
| Priority | 5.00 | |
| Feasibility | 4.00 | |

**Acceptance Criteria:**
1. AC1: publish(project='../Knowledge', run_id='run_legit') RAISES and writes NO file outside Projects/ (repro B blocked)
2. AC2: publish(run_id='../../../Victim/...') RAISES and writes NO file outside the project's runs/ (repro A blocked)
3. AC3: a legit project 'SwarmAI' + run_id 'run_<8hex>' + a bare entry.file 'evaluation-20261012.json' all PASS (RP50: 461 live bare artifacts not false-killed)
4. AC4: CLI cmd_publish with an invalid run_id/project writes NOTHING before refusing (fail-closed order, exit non-zero)
5. AC5: a stage-linked publish to a non-existent run RAISES/404 (phantom-run fix); run.json.project and .id must match
6. AC6: PublishRequest.run_id is a required str (OpenAPI 422 on absent, not a runtime 400)
7. AC7: _entry_to_artifact + _load_artifact_for_metrics reject a ../-escaping entry.file but allow bare AND runs/<id>/ shapes


## 3. Design & Approach
**Research Findings (THINK):**
- The 3 path-building sinks are: artifact_registry.publish() (project+run_id → mkdir+write), _entry_to_artifact() (project+entry.file → read), and artifact_cli._load_artifact_for_metrics() (project+entry.file → read). All take caller strings verbatim.
- A single containment primitive on resolved paths covers all 3: target.resolve().is_relative_to(base.resolve()). Must use Path.is_relative_to (py3.9+) NOT str.startswith — macOS FS is case-insensitive (SwarmAI/swarmai share one inode), so a prefix compare on resolved output is unsound.
- run_id contract is ^run_[A-Za-z0-9_]+$ — verified against all 831 live run dirs (0 misses); _gen_run_id emits run_<8hex>, strictly narrower.
- project containment base is projects_root; all 9 live projects are direct children → is_relative_to(projects_root) passes every one. The is_dir()-only guard is the hole (returns True for ../Knowledge).
- entry.file has TWO legit shapes — bare 'evaluation-20261012.json' AND run-scoped 'runs/<id>/foo.json' (461 bare live). Containment base = artifacts_dir; both shapes resolve inside it, only ../ escapes fail. A startswith('runs/') check would false-kill all 461 bare (RP50).
- cmd_publish currently calls reg.publish() (write) BEFORE the stage-link ownership check (fail-closed order bug #2). The security validation needs only project+run_id (available pre-publish), so moving it earlier has no dependency on the returned artifact_id.

**Alternatives Evaluated:**
- QUALITY — effort: S, 1 session
- SPEED — effort: S, <1 session

**Chosen Approach:** Add ArtifactRegistry._validate_path_identifiers(project, run_id=None) as the single trust boundary, called inside publish() (before mkdir), _entry_to_artifact() (before read), and artifact_cli._load_artifact_for_metrics() (before read). Containment via Path.is_relative_to on resolved paths. Fix cmd_publish fail-closed order; add phantom-run existence check; make PublishRequest.run_id required.

**Success Criteria:**
- Both live traversal repros (A run_id, B project) raise and leave nothing outside the project
- All 831 live run_ids + 461 bare artifacts still validate as legit (no regression)
- cmd_publish writes nothing on rejection

**Always:**
- Use Path.is_relative_to on resolved paths, never str.startswith (macOS case-insensitive)
- Validation runs BEFORE any mkdir/write/read
- run_id regex ^run_[A-Za-z0-9_]+$

**Never:**
- str prefix compare for containment
- false-killing the 461 live bare artifacts
- a timeout/catch that swallows a traversal attempt silently (fail-loud raise)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_1fc998ed | 9,000 |  |
| think | completed | art_07cfa61f | 9,000 |  |
| plan | completed | art_de22b814 | 11,000 |  |
| build | completed | art_c8adeb3c | 42,000 |  |
| review | completed | art_6b6b5530 | 18,000 |  |
| test | completed | art_3547df85 | 25,000 |  |
| deliver | completed | art_cb44dc39 | 0 |  |
| reflect | completed | - | 118,000 |  |

**Total tokens:** 232,000 | **Stages:** 8/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 13:12:29 | - |
| think | 13:13:37 | 1.1 min |
| plan | 13:15:03 | 1.4 min |
| build | 13:23:28 | 8.4 min |
| review | 13:26:28 | 3.0 min |
| test | 13:31:43 | 5.2 min |
| deliver | 13:50:39 | 18.9 min |
| reflect | - | - |

Slowest stage: `deliver` at 18.9 min (50% of the 6 measured inter-stage gaps).

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
| evaluate | profile=full (security-surface + new mechanism + cross-file  | taste | bugfix work_type but full profile for max review c |

**Summary:** 0 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 1 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**4 findings** (verdict: ?)
- [HIGH] artifact_registry.py read path (_read_manifest/discover/get_artifact via HTTP GE
- [MEDIUM] artifact_registry.py _RUN_ID_RE used `$` which matches before a trailing \n -> r
- [LOW] test_artifact_registry.py traversal test asserted only that no file escaped, not
- [LOW] _entry_to_artifact silently degraded a containment-escaping entry.file to data={

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/artifact_registry.py`
- `backend/scripts/artifact_cli.py`
- `backend/routers/artifacts.py`
- `backend/tests/test_artifact_registry.py`
- `backend/tests/test_artifact_cli_lifecycle.py`
- `backend/tests/test_artifacts_publish_run_scoped.py`

**+0 / -0 lines** | 6 files

## 9. Lessons
- [principle] A path-containment trust boundary must enumerate EVERY caller-supplied identifier concatenated into the path, not just the one in focus. This fix validated run_id but a fresh-context skeptic reproduced project='../Knowledge' escaping the same way, and a Gate-2 Security specialist found entry.file as a third vector — three identifiers, one path. The orthogonal-blindness that caused the original 14 bugs recurred inside the FIX itself (SOUL P1 authorship trap). Durable tell: when hardening input->path, grep for every segment that builds the path and ask what ELSE is interpolated, before declaring the boundary complete.
- [pitfall] Containment on the WRITE path with the READ path left open is a half-fix of the same class. publish() (write) was validated but _read_manifest/get_artifact/discover (read, untrusted project from HTTP query) had none — a read-side traversal existence-oracle. A security property on a path identifier must cover BOTH directions; the adversarial Security reviewer caught the read side, I did not.
- [decision] For a validator covering HTTP + CLI + direct + test callers, put it as an idempotent chokepoint on the core object the method lives on (Registry._validate_path_identifiers inside publish()/_read_manifest()), NOT scattered at each entry point. publish() is directly callable so per-entry validation cannot cover it. Idempotent pure-predicate means double/triple validation across layers is correctness-neutral defense-in-depth.
- [pitfall] A regex anchored with $ (not \Z) accepts a trailing newline (run_id='run_x\n' matched) — a garbage-dir / log-injection surface even when containment still holds. For any identifier format gate use fullmatch / \Z, never $.
- enumerate all path identifiers not just the focused one
- write+read both need containment
- chokepoint on core object not per-entry
- fullmatch not $ anchor


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-12 13:52 UTC*
