## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Action B (artifact-subsystem systemic fix): single read contract for the artifact registry — _load_artifact_for_metrics verifies entry.run_id==expected_run_id + expected_artifact_type (Kiro #4), changeset read maps by profile build-vs-goal_cycle schema (#6), three-state available/unavailable/not_run instead of None->0 (#7), Artifact dataclass/_entry_to_artifact/PipelineArtifactResponse carry run_id so discover() can filter by run (#14). Folds cmd_run_report name-collapse sites per design v2.

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | enabler-story | user-stated: Kiro #4 — cross-run contamination via blind manifest-id trust | confirmed | ● | Given a run A stage whose artifact_id points at run B's artifact, when cmd_run_report loads it, then load returns not-found (ownership mismatch), foreign artifact NOT rendered |
| FR-2 | enabler-story | user-stated: Kiro #7 — missing artifact rendered as 0 findings | confirmed | ● | Given a stage artifact_id that does not resolve, when REPORT renders that section, then it shows 'unavailable', distinct from a real 0 |
| FR-3 | enabler-story | user-stated: Kiro #6 — goal_cycle changeset not read | confirmed | ● | Given a goal-profile run, when REPORT Section 8 renders the changeset, then it reads goal_cycle's own fields, not build's absent names |
| FR-4 | enabler-story | user-stated: Kiro #14 — discover cannot filter by run | confirmed | ● | Given two runs with artifacts in one project, when discover(run_id=X) is called, then only run X's artifacts return |

### 澄清问答 (Clarifications — who decided what)
_(无澄清记录 / no clarifications)_

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
✅ 无未闭合问题 (no leftover — all requirements closed, no AI assumptions)