# Autonomous Pipeline Report: eval OS: add non-gate-eligible 'live' tier (runtime-state-dependent cases don't flap the BVT release gate)

**Run ID:** run_4976929a | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-15 02:19 UTC | **Duration:** 583.7 min (in progress) | **Tokens:** 85,000
**Gate 1:** N/A | **Files:** 6 | **Tests:** 0/0

## TL;DR
Add a non-gate-eligible eval tier (e.g. 'live'/'integration') for deterministic golden cases that depend on runtime state (a built code_intel.db / live workspace) rather than being self-verifiable in 

## 1. Requirement
Add a non-gate-eligible eval tier (e.g. 'live'/'integration') for deterministic golden cases that depend on runtime state (a built code_intel.db / live workspace) rather than being self-verifiable in a bare git checkout; exclude it from compute_bvt's _GATE_TIERS so such cases stay in the corpus and run post-deploy/manually but do NOT flap the BVT release gate; reclassify GS_COD010 into it. Must keep P8 consistency across ALL tier-set sites (compute_bvt._GATE_TIERS, eval_service get_golden_set / affected_by / promote), which the code notes are deliberately non-unified.

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Add a non-gate-eligible eval tier (e.g. 'live'/'integration') for deterministic golden cases that depend on runtime state (a built code_intel.db / live workspace) rather than being self-verifiable in a bare git checkout; exclude it from compute_bvt's _GATE_TIERS so such cases stay in the corpus and run post-deploy/manually but do NOT flap the BVT release gate; reclassify GS_COD010 into it. Must keep P8 consistency across ALL tier-set sites (compute_bvt._GATE_TIERS, eval_service get_golden_set / affected_by / promote), which the code notes are deliberately non-unified.

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | enabler-story | user-stated: XG chose option B: root-cause fix = structural tier, not per-case patch | confirmed | ● | Given a golden case tier=live that FAILS at runtime, when ci_eval_gate runs, then gate_rc=0 (live failure does not block release) |
| FR-2 | enabler-story | self-answered: code-trace: tier consumed at eval_runner _GATE_TIERS/report-buckets + eval_service get_golden_set/promote/affected_by/behavior; each differs | confirmed | ● | Given a live case, when get_golden_set / report / promote run, then returned+runnable, surfaced in report with reconcile intact, not auto-promotable |
| FR-3 | task | self-answered: diagnosis: GS_COD010 depends on built code_intel.db (git-untracked, continuously rebuilt), flaps BVT | confirmed | ● | Given GS_COD010 tier=live, when programmatic BVT runs, then gate green; case present in corpus but not gated |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | New tier value name? | A. live | 🧠 self |
| Q2 | Should live cases be promotable to public? | B. no, keep private/corpus-only | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. live (🧠 AI 替你拍的板 — resolution: self-answer: live best names runtime-state dependence; THINK may reconsider vs integration (taste, non-blocking))
- [SELF-ANSWERED] Q2: B. no, keep private/corpus-only (🧠 AI 替你拍的板 — resolution: self-answer: a runtime-state case cannot self-verify in a bare checkout, so exclude from promote like stable/draft)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 4.00 | |
| Priority | 4.00 | |
| Feasibility | 4.00 | |

**Acceptance Criteria:**
1. A new tier value live is defined with a single documented SSOT (a named frozenset/const), NOT a bare string literal scattered across sites
2. compute_bvt EXCLUDES live from the release gate (verified: a live case that FAILS does not flip bvt green=false / gate_rc stays 0)
3. get_golden_set STILL RETURNS a live case (verified: it remains runnable manually/post-deploy, not dropped like archived)
4. report bucketing surfaces live cases without breaking the reconcile-to-golden_size invariant (no double-count, not silently merged into a misleading Other)
5. GS_COD010 tier is changed active to live and the BVT gate goes green with GS_COD010 present-but-not-gated
6. promote/affected_by/behavior-subset sites treat live correctly (live is not promotable to public without a decision; not counted in behavior subset)


## 3. Design & Approach
**Research Findings (THINK):**
- The _GATE_TIERS exclusion (eval_runner.py:208) is already fail-closed: an unknown tier like live is NOT gated. So the gate half needs NO code change.
- THE LOAD-BEARING TRAP: promote_stable_cases (eval_service.py:854) excludes archived/stable/draft but NOT live. A live case with 10+ consecutive passes would auto-promote to stable, which IS gate-eligible, silently re-entering the BVT gate. live MUST be added to this exclusion.
- get_golden_set has NO tier filter: a live case is returned and runnable (manual/post-deploy) - the desired behavior.
- affected_by (eval_service.py:840) excludes archived+stable; live is INCLUDED, so a live case still runs when its affected_by file changes - desirable.
- report bucketing (eval_runner.py:2392-2395) routes live into the other catch-all; the reconcile-to-golden_size invariant holds (disjoint lists). A dedicated card is cosmetic/optional.
- behavior-subset (eval_service.py:228) requires eval_method==behavior; GS_COD010 is programmatic, so live is naturally excluded there.
- golden_case_validator.py enforces NO tier enum, so a live value is schema-accepted; adding an explicit tier allowlist in the validator is an OPTIONAL hardening (guards typos).

**Alternatives Evaluated:**
- SIMPLICITY — effort: S (1 session)
- QUALITY — effort: M (1-2 sessions)
- DELETION — effort: S

**Chosen Approach:** Add a LIVE_TIER='live' constant + a _NON_PROMOTABLE tier set as a single SSOT in eval_runner.py (next to _GATE_TIERS; eval_service already imports from eval_runner, so one-directional dep is safe). The ONE load-bearing change: add live to promote_stable_cases' exclusion so a passing live case cannot auto-promote to stable and re-enter the gate. Gate half (_GATE_TIERS) needs NO change (fail-closed already excludes live). Add a tier-enum allowlist to golden_case_validator.py (fail-closed on a typo'd tier). Reclassify GS_COD010 active->live in the tracked golden_set.yaml. Report bucketing left as-is (other catch-all reconciles).

**Success Criteria:**
- The full `eval_runner.py run --programmatic-only` gate returns rc=0 with GS_COD010 reclassified and present
- A forced-failing live case cannot turn the gate red (unit test proves it)
- A live case cannot auto-promote into a gate-eligible tier (unit test proves it)
- An unknown/typo'd tier is rejected by the validator (fail-closed)

**Always:**
- Reuse a single named const for the live tier (no scattered literals) - the pre_mortem drift risk
- Verify each consumer-site change against the observed tier-consumer map, not by assumption (P8 cross-door consistency)
- Run the programmatic BVT end-to-end after the change to confirm gate green

**Never:**
- Do NOT add live to _GATE_TIERS (that would gate it - the opposite of the goal)
- Do NOT fix GS_COD010 by patching its verification instead of the structural tier (rejected option A)
- Do NOT silently delete/retire GS_COD010 (the capability it tests is real; it just needs the right tier)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_481f136c | 9,000 |  |
| think | completed | art_8758476f | 10,000 |  |
| plan | completed | art_1bd72205 | 9,000 |  |
| build | completed | art_c018b388 | 42,000 |  |
| review | completed | art_47a155e2 | 15,000 |  |
| test | recorded | art_060d78e5 | 0 |  |
| deliver | in_progress | art_5ff7d2e1 | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 85,000 | **Stages:** 5/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 10-14 16:41:51 | - |
| think | 10-14 16:43:31 | 1.7 min |
| plan | 10-14 16:46:10 | 2.6 min |
| build | 10-14 17:12:20 | 26.2 min |
| review | 10-14 17:16:36 | 4.3 min |
| test | 10-14 17:31:42 | 15.1 min |
| deliver | 10-15 02:19:35 | 527.9 min |
| reflect | - | - |

Slowest stage: `deliver` at 527.9 min (91% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

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
| evaluate | work_type=existing-feature; profile=full | mechanical | adds a tier category + consumer-site handling acro |
| think | Recommend A (SIMPLICITY) + validator tier-enum; defer report | taste | promote-exclusion is the one load-bearing fix; tie |
| plan | SSOT const in eval_runner (eval_service already imports it); | mechanical | consumer map fully traced; one-directional import  |
| review | single-pass review (backend-only, tight scope); spec via fre | mechanical | 6 files but all eval-infra tier logic, spec sub-ag |

**Summary:** 3 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**2 findings** (verdict: ?)
- [MEDIUM] eval_service.py get_affected_cases() line 843: did not exclude 'live' tier → cha
- [MEDIUM] eval_runner.py compute_redline() line 253: tier-blind by Gate-1 design → a live+

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/scripts/eval_runner.py`
- `backend/core/eval_service.py`
- `backend/scripts/golden_case_validator.py`
- `backend/tests/test_bvt_admission.py`
- `backend/tests/test_eval_hooks.py`
- `backend/scripts/golden_case_validator_test.py`

**+0 / -0 lines** | 6 files

## 9. Lessons
- [decision] eval OS needs a 'live'/non-gate tier for deterministic golden cases that depend on runtime state (a built code_intel.db / live workspace): they are NOT self-verifiable in a bare git checkout, so they flap the BVT release gate on a rebuild-window miss. The fix is a tier that stays in the corpus + runs post-deploy but is excluded from compute_bvt's _GATE_TIERS — NOT deleting the case (the capability it tests is real).
- [pitfall] P8 'tier is read at N independent sites' is a trap: a new non-gate tier must be handled at EVERY tier-set site, not just the obvious gate. compute_bvt (fail-closed allowlist — no change needed), promote_stable_cases (MUST exclude or a passing live case auto-promotes to gate-eligible stable), get_affected_cases (MUST exclude or the change-hook auto-fires a flap-prone live case), AND compute_redline (tier-BLIND by Gate-1 design — guard at ADMISSION via validator, never by making redline tier-aware). Enumerate ALL readers of the field before claiming 'only one site needs changing'.
- [pitfall] When two subsystems encode DELIBERATELY-different intents over the same field (promotable vs redline-eligible vs auto-triggerable tiers), the right structure is N named constants each at its own site, NOT one unified SSOT — unifying them would couple independent policies. But a hardcoded literal tuple (get_affected_cases) can silently drift from its named siblings; prefer a named const even when the set is site-specific.
- [pitfall] A deployment-ordering split-brain hides in any change that edits BOTH a live-read data file (effective instantly) AND the code that interprets it (effective only after rebuild+restart): in the window, OLD code reads the NEW data. Here a reclassified live case could be auto-promoted back into the gate by un-deployed promote code. Verify the trigger's distance from firing (consecutive-pass streak vs threshold) to grade the real severity, and state the deploy-order constraint in delivery.


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-15 02:19 UTC*
