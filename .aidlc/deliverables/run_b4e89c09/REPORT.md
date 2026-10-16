# Autonomous Pipeline Report: active_run_commit_gate — code + REPORT.md structurally forced into ONE commit

**Run ID:** run_b4e89c09 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-16 10:08 UTC | **Duration:** 59.0 min (in progress) | **Tokens:** 157,000
**Gate 1:** N/A | **Files:** 4 | **Tests:** True/1

## TL;DR
从机制上根治 pipeline run 代码与 REPORT.md 被分成两个 commit:扩展 adversarial_commit_gate 拦截手动 git commit——若提交路径属于某未 COMPLETE 的 active run 的 files_touched 则 DENY 引导走 run-commit。bugfix cross_boundary.

## 1. Requirement
从机制上根治 pipeline run 代码与 REPORT.md 被分成两个 commit:扩展 adversarial_commit_gate 拦截手动 git commit——若提交路径属于某未 COMPLETE 的 active run 的 files_touched 则 DENY 引导走 run-commit。bugfix cross_boundary.

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 从机制上根治 pipeline run 代码与 REPORT.md 被分成两个 commit:扩展 adversarial_commit_gate 拦截手动 git commit——若提交路径属于某未 COMPLETE 的 active run 的 files_touched 则 DENY 引导走 run-commit。bugfix cross_boundary.

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | enabler-story | user-stated: XG: 从机制上确保不可能再发生 — 代码与 REPORT 必须同一 commit for review purpose | confirmed | ● | Given an active run with files_touched=[X], when the agent runs `git commit -- X`, then the PreToolUse gate DENIES it and names run-commit as the route |
| FR-2 | task | ddd-derived: Gate-0 skeptic: build.md:313 is a second split-trigger via identical mechanism | confirmed | ● | Given BUILD stage, when a green cycle completes, then the instruction stages/leaves changes uncommitted, not `git commit` |
| FR-3 | enabler-story | assumption: R29 parallel-session safety + run-commit uses subprocess not Bash tool | confirmed | ● | Given a commit of a path NOT in any active run's files_touched, when the agent commits, then the gate APPROVES |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | Fix via gate (structural) or prose-only build.md change? | A. Gate + build.md change (structural, P7) | 🧠 self |
| Q2 | Delete _lookup_already_committed as a split-patch? | B. Keep it | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [ASSUMPTION] FR-3: The gate must not false-block parallel sessions, run-commit's own commit, or post-COMPLETE commits
- [SELF-ANSWERED] Q1: A. Gate + build.md change (structural, P7) (🧠 AI 替你拍的板 — resolution: self-answer: the prose 'let run-commit commit' was already ignored twice (manual commit this run + build.md:313 standing instruction) — SOUL P7 says when prose fails repeatedly, build a gate. Prose-only (B) leaves the exact hole open.)
- [SELF-ANSWERED] Q2: B. Keep it (🧠 AI 替你拍的板 — resolution: self-answer: Gate-0 skeptic read its docstring+caller (artifact_cli.py:3066/3595) — it is independent gate-reconciliation (credits per-cycle commits so completion gate doesn't mis-flag uncommitted_source), not a split-patch. Deleting it re-breaks the BUILD-vs-gate contract.)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 8.00 | |
| Priority | 9.00 | |
| Feasibility | 8.00 | |

**Acceptance Criteria:**
1. AC1: A PreToolUse gate DENIES an agent `git commit` whose pathspec intersects any active (status != completed/abandoned) pipeline run's files_touched, with a message routing to run-commit. Verified by a unit test: a commit of an active-run file → deny; a commit of an unrelated/parallel-session file → approve.
2. AC2: The gate NEVER false-blocks: (a) run-commit's own subprocess commit (not a Bash tool call, bypasses PreToolUse); (b) a parallel session's commit of ITS files; (c) a commit after the owning run reached COMPLETE. Verified by tests for each.
3. AC3: build.md step 9 no longer instructs a per-cycle `git commit`; it instructs stage-only (or nothing), so the sole commit point is run-commit. Verified by reading the changed instruction.
4. AC4: `_lookup_already_committed` is NOT deleted (Gate-0 proved it independent). Verified by its presence + its tests still green.
5. AC5: After the fix, a full pipeline run that touches code produces exactly ONE commit containing BOTH code and REPORT.md. Verified by an integration test or a documented manual trace.


## 3. Design & Approach
**Research Findings (THINK):**
- The split's sole trigger is: the run's CODE is committed before run-commit runs (manual commit in COMPLETE, OR build.md:313 per-cycle commit). Then run-commit's `git commit -- *real_files` carries only the new REPORT.md. Git-reflog + Gate-0 skeptic both confirm.
- The gate can REUSE existing infra: `_pending_commit_paths(cwd, command)` (security_hooks.py:1915) already returns the absolute path set a commit will touch (heredoc/pathspec-hardened); `_command_has_git_commit` (1811) already detects git commit; the adversarial_commit_gate factory pattern (2169) is the template.
- run.json carries `files_touched` (absolute paths) + `status`. Active runs = glob ~/.swarm-ai/SwarmWS/Projects/*/.artifacts/runs/*/run.json where status not in (completed/abandoned). Union their files_touched = the protected set.
- run-commit commits via Python subprocess, NOT the agent Bash tool → it bypasses PreToolUse entirely → the gate never blocks the legitimate commit path.
- `_lookup_already_committed` (artifact_cli.py:3066) is independent gate-reconciliation (Gate-0 confirmed) — NOT a split-patch — so it stays.

**Alternatives Evaluated:**
- QUALITY — effort: M, 1 session
- SIMPLICITY — effort: S, same session
- DELETION — effort: M

**Chosen Approach:** Add a PreToolUse Bash gate `active_run_commit_gate` (security_hooks.py, factory pattern mirroring adversarial_commit_gate). On an agent `git commit`: compute the pending commit path-set via the EXISTING `_pending_commit_paths(cwd, command)`; glob active (status not in completed/abandoned) pipeline runs' run.json and union their `files_touched`; if any pending path is in that union AND the owning run is NOT completed, DENY with a message routing to `run-commit` (which bundles REPORT.md into the same commit). Fail-open on any infra error / uncomputable pending (same discipline as adversarial_commit_gate). SEPARATELY, change build.md step 9 from 'Commit after each green cycle' to 'Stage after each green cycle (do NOT git commit — run-commit is the sole commit point so code + REPORT land together)'. Do NOT touch _lookup_already_committed (independent gate-reconciliation).

**Success Criteria:**
- An agent `git commit` of an active run's code is DENIED with a run-commit route message.
- A commit unrelated to any active run, or belonging to a completed run, is APPROVED.
- build.md no longer instructs a per-cycle git commit.
- A full pipeline run touching code yields exactly ONE commit with code + REPORT.md.

**Always:**
- Fail-open on ANY gate infra error (parse error, timeout, uncomputable pending) — a gate that false-blocks real work is worse than the split it prevents (adversarial_commit_gate discipline).
- Bind ownership to EXACT absolute path (not basename) so a parallel session's same-named file in another run is never caught (R29).

**Never:**
- Never block run-commit's own commit (it is a subprocess, not a Bash tool — structurally bypasses PreToolUse; do not add any path that would catch it).
- Never delete _lookup_already_committed (Gate-0 proved it independent).
- Never gate a non-Bash tool.
- Never raise from the gate (always return a decision dict).


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_b8ca1a0e | 9,000 |  |
| think | completed | art_14cd26b1 | 11,000 |  |
| plan | completed | art_6514bfdd | 12,000 |  |
| build | completed | art_ee105901 | 40,000 |  |
| review | completed | art_a7bf7c45 | 15,000 |  |
| test | completed | art_b28be7be | 25,000 |  |
| deliver | completed | art_14ddbb51 | 45,000 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 157,000 | **Stages:** 7/8 completed | **Validation blocks:** 3

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 09:39:43 | - |
| think | 09:41:06 | 1.4 min |
| plan | 09:49:06 | 8.0 min |
| build | 09:53:13 | 4.1 min |
| review | 09:54:59 | 1.8 min |
| test | 09:56:38 | 1.6 min |
| deliver | 10:08:20 | 11.7 min |
| reflect | - | - |

Slowest stage: `deliver` at 11.7 min (41% of the 6 measured inter-stage gaps).

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
| plan | status allowlist {running,paused} not denylist | mechanical | Gate-1: denylist rots, live data confirms 2 non-te |

**Summary:** 1 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**4 findings** (verdict: ?)
- [HIGH] security_hooks.py _active_run_owned_paths: owned kept files_touched as raw strin
- [MEDIUM] security_hooks.py _canonicalize_owned_path used os.getcwd() as a relative-base —
- [LOW] Dual-candidate realpath (SwarmWS + source-repo bases) could in theory over-DENY 
- [MEDIUM] Unbounded glob of all historical run.json (hundreds+, growing) on every git comm

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/security_hooks.py`
- `backend/core/hook_builder.py`
- `backend/skills/s_autonomous-pipeline/stages/build.md`
- `backend/tests/test_active_run_commit_gate.py`

**+0 / -0 lines** | 4 files

## 9. Lessons
- [principle] When a gate reads a stored path set to intersect with a computed one, BOTH sides must be canonicalized to the SAME form (os.path.realpath absolute) at the seam — a raw-string vs realpath mismatch makes the intersection silently empty, so the gate fails OPEN exactly where it must act. The test suite masked it because every fixture pre-normalized paths; only live mixed-form data (abs + repo-relative) exposed it.
- [pitfall] A hook that resolves a relative path with os.getcwd() is broken in the launchd daemon, where cwd is the backend dir, not any user repo — local tests pass (cwd==repo) while production fails open. Derive deterministic bases from __file__ / a known workspace root, never cwd, for any path logic that runs in the daemon.
- [decision] Fix-strength ladder (SOUL P7): the code/REPORT split had failed twice under a prose rule (build.md step 9 + the manual-commit habit). The right fix was a PreToolUse gate that makes the wrong move structurally impossible, PLUS removing the per-cycle-commit instruction — closing BOTH trigger paths, not just the one that bit most recently.
- [pitfall] A status DENYLIST rots: enumerate the ALLOWLIST of non-terminal states ({running,paused}) instead, so a newly-added terminal status is treated as terminal by default rather than wrongly held active forever.
- [principle] A pipeline run that FIXES the pipeline must not self-deadlock: run-commit commits via a Python subprocess, not the agent Bash tool, so a PreToolUse Bash gate never sees it — the sole sanctioned commit path is structurally exempt from a gate that blocks the agent manual-commit path.


## 10. Known Gaps & Attention Flags
- Validator blocked 3 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 10:08 UTC*
