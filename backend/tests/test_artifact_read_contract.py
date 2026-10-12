"""Read-contract tests for the artifact registry loader (Action B).

Verifies the single read contract added in Action B of the artifact-subsystem
systemic fix:
  - _load_artifact_for_metrics enforces run_id OWNERSHIP (conditionally — only
    when the manifest entry carries a run_id; the ~2169 legacy run_id-less entries
    must still load) and artifact TYPE.
  - It returns a 3-state result (available / unavailable / not_run) so a caller
    can distinguish "artifact missing" from "a real 0".
  - _changeset_stage_for_profile maps the changeset source by profile
    (build for full/bugfix, goal_cycle for goal).
  - Artifact dataclass + _entry_to_artifact + discover() carry/filter run_id.

Methodology: real temp workspace + manifest (no mocks of our own code — mock only
the _get_workspace boundary). Each ownership/type/state branch has a test that goes
RED when the branch is removed (mutation-proven in BUILD).
"""
import json
from pathlib import Path

import pytest

from core.artifact_registry import ArtifactRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — a real workspace with a hand-built manifest + data files
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "Projects").mkdir()
    return tmp_path


def _seed_artifact(workspace: Path, project: str, *, art_id: str, art_type: str,
                   run_id: str | None, payload: dict) -> None:
    """Write a data file + append a manifest entry (mimics the write side)."""
    arts_dir = workspace / "Projects" / project / ".artifacts"
    arts_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{art_type}-20261012-{art_id}.json"
    (arts_dir / fname).write_text(json.dumps(payload), encoding="utf-8")
    manifest_file = arts_dir / "manifest.json"
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    else:
        manifest = {"project": project, "pipeline_state": "build", "artifacts": []}
    entry = {"id": art_id, "type": art_type, "producer": "s_autonomous-pipeline",
             "created": "2026-10-12T00:00:00+00:00", "file": fname,
             "summary": "test", "superseded_by": None}
    if run_id is not None:
        entry["run_id"] = run_id
    manifest["artifacts"].append(entry)
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# AC1 — conditional ownership (tracer bullet)
# ─────────────────────────────────────────────────────────────────────────────
class TestOwnership:
    def test_cross_run_entry_rejected(self, workspace, monkeypatch):
        """An entry owned by run B must NOT load under run A's run_id."""
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        _seed_artifact(workspace, "P", art_id="art_foreign", art_type="evaluation",
                       run_id="run_B", payload={"v": 1})
        res = cli._load_artifact_for_metrics("P", "run_A", "art_foreign", "evaluation")
        assert res.state == "unavailable"
        assert res.data is None

    def test_same_run_entry_loads(self, workspace, monkeypatch):
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        _seed_artifact(workspace, "P", art_id="art_mine", art_type="evaluation",
                       run_id="run_A", payload={"v": 42})
        res = cli._load_artifact_for_metrics("P", "run_A", "art_mine", "evaluation")
        assert res.state == "available"
        assert res.data == {"v": 42}

    def test_legacy_no_run_id_entry_still_loads(self, workspace, monkeypatch):
        """The ~2169 legacy entries lacking run_id MUST pass (conditional ownership)."""
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        _seed_artifact(workspace, "P", art_id="art_legacy", art_type="evaluation",
                       run_id=None, payload={"v": 7})
        res = cli._load_artifact_for_metrics("P", "run_whatever", "art_legacy", "evaluation")
        assert res.state == "available"
        assert res.data == {"v": 7}


# ─────────────────────────────────────────────────────────────────────────────
# AC2 — type check
# ─────────────────────────────────────────────────────────────────────────────
class TestTypeCheck:
    def test_wrong_type_rejected(self, workspace, monkeypatch):
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        _seed_artifact(workspace, "P", art_id="art_x", art_type="research",
                       run_id="run_A", payload={"v": 1})
        res = cli._load_artifact_for_metrics("P", "run_A", "art_x", "evaluation")
        assert res.state == "unavailable"

    def test_expected_type_none_skips_type_check(self, workspace, monkeypatch):
        """expected_type=None → no type enforcement (back-compat for callers that don't know)."""
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        _seed_artifact(workspace, "P", art_id="art_y", art_type="research",
                       run_id="run_A", payload={"v": 9})
        res = cli._load_artifact_for_metrics("P", "run_A", "art_y", None)
        assert res.state == "available"
        assert res.data == {"v": 9}


# ─────────────────────────────────────────────────────────────────────────────
# AC3 — three-state (available / unavailable / not_run)
# ─────────────────────────────────────────────────────────────────────────────
class TestThreeState:
    def test_missing_artifact_is_unavailable_not_zero(self, workspace, monkeypatch):
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        (workspace / "Projects" / "P" / ".artifacts").mkdir(parents=True)
        (workspace / "Projects" / "P" / ".artifacts" / "manifest.json").write_text(
            json.dumps({"project": "P", "artifacts": []}), encoding="utf-8")
        res = cli._load_artifact_for_metrics("P", "run_A", "art_absent", "evaluation")
        assert res.state == "unavailable"
        assert res.data is None
        assert not res  # falsy — back-compat with `if loaded:` callers

    def test_not_run_when_art_id_is_none(self, workspace, monkeypatch):
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        res = cli._load_artifact_for_metrics("P", "run_A", None, "evaluation")
        assert res.state == "not_run"
        assert not res

    def test_available_is_truthy(self, workspace, monkeypatch):
        import scripts.artifact_cli as cli
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        _seed_artifact(workspace, "P", art_id="art_ok", art_type="evaluation",
                       run_id="run_A", payload={"v": 1})
        res = cli._load_artifact_for_metrics("P", "run_A", "art_ok", "evaluation")
        assert bool(res) is True
        assert res.data == {"v": 1}


# ─────────────────────────────────────────────────────────────────────────────
# AC4 — profile-aware changeset stage
# ─────────────────────────────────────────────────────────────────────────────
class TestChangesetStageForProfile:
    def test_full_profile_reads_build(self):
        import scripts.artifact_cli as cli
        assert cli._changeset_stage_for_profile("full") == "build"

    def test_bugfix_profile_reads_build(self):
        import scripts.artifact_cli as cli
        assert cli._changeset_stage_for_profile("bugfix") == "build"

    def test_goal_profile_reads_goal_cycle(self):
        import scripts.artifact_cli as cli
        assert cli._changeset_stage_for_profile("goal") == "goal_cycle"

    def test_unknown_profile_defaults_build(self):
        import scripts.artifact_cli as cli
        assert cli._changeset_stage_for_profile("mystery") == "build"


class TestGoalChangesetRendersFromRecord:
    """REVIEW MED edge: an artifactless goal_cycle (no artifact_id, 'commits
    incrementally') must still surface files_changed from the STAGE RECORD into
    the report header, not render a hard 0 (the old build-only read)."""

    def test_goal_run_without_cycle_artifact_renders_record_files(self, workspace, monkeypatch):
        import scripts.artifact_cli as cli
        from argparse import Namespace
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        project, run_id = "P", "run_goal"
        run_dir = workspace / "Projects" / project / ".artifacts" / "runs" / run_id
        run_dir.mkdir(parents=True)
        # goal_cycle stage: completed, NO artifact_id, files_changed on the RECORD
        run_state = {
            "id": run_id, "project": project, "profile": "goal",
            "requirement": "goal thing", "status": "completed",
            "created_at": "2026-10-12T00:00:00+00:00",
            "completed_at": "2026-10-12T01:00:00+00:00",
            "stages": [
                {"stage": "goal_cycle", "status": "completed", "token_cost": 1,
                 "files_changed": ["a.py", "b.py", "c.py"], "cycles_run": 4,
                 "dod_met": 3, "adversarial_review": {"spawned": True, "findings": []}},
                {"stage": "deliver", "status": "completed", "token_cost": 1},
                {"stage": "reflect", "status": "completed", "token_cost": 1,
                 "lessons": ["[guideline] a sufficiently long reflect lesson here."]},
            ],
        }
        (run_dir / "run.json").write_text(json.dumps(run_state), encoding="utf-8")
        (workspace / "Projects" / project / ".artifacts" / "manifest.json").write_text(
            json.dumps({"project": project, "artifacts": []}), encoding="utf-8")
        cli.cmd_run_report(Namespace(project=project, run_id=run_id), None)
        report = (run_dir / "REPORT.md").read_text(encoding="utf-8")
        # header `Files:` must reflect the 3 files from the goal_cycle RECORD, not 0
        assert "**Files:** 3" in report, f"goal files not surfaced from record: {report[:400]}"

    def test_full_run_files_unaffected(self, workspace, monkeypatch):
        """Guard: the common full-profile path still reads build, unaffected."""
        import scripts.artifact_cli as cli
        from argparse import Namespace
        monkeypatch.setattr(cli, "_get_workspace", lambda: workspace)
        project, run_id = "P", "run_full"
        run_dir = workspace / "Projects" / project / ".artifacts" / "runs" / run_id
        run_dir.mkdir(parents=True)
        run_state = {
            "id": run_id, "project": project, "profile": "full",
            "requirement": "full thing", "status": "completed",
            "created_at": "2026-10-12T00:00:00+00:00",
            "completed_at": "2026-10-12T01:00:00+00:00",
            "stages": [
                {"stage": "build", "status": "completed", "token_cost": 1,
                 "files_changed": ["x.py", "y.py"]},
                {"stage": "deliver", "status": "completed", "token_cost": 1},
                {"stage": "reflect", "status": "completed", "token_cost": 1,
                 "lessons": ["[guideline] a sufficiently long reflect lesson here."]},
            ],
        }
        (run_dir / "run.json").write_text(json.dumps(run_state), encoding="utf-8")
        (workspace / "Projects" / project / ".artifacts" / "manifest.json").write_text(
            json.dumps({"project": project, "artifacts": []}), encoding="utf-8")
        cli.cmd_run_report(Namespace(project=project, run_id=run_id), None)
        report = (run_dir / "REPORT.md").read_text(encoding="utf-8")
        assert "**Files:** 2" in report


# ─────────────────────────────────────────────────────────────────────────────
# AC5 — Artifact.run_id + discover() run_id filter
# ─────────────────────────────────────────────────────────────────────────────
class TestDiscoverRunIdFilter:
    def test_artifact_carries_run_id(self, workspace):
        reg = ArtifactRegistry(workspace)
        (workspace / "Projects" / "P").mkdir(parents=True)
        reg.publish("P", "research", data={"k": 1}, producer="x", summary="s",
                    run_id="run_A")
        arts = reg.discover("P", "research")
        assert len(arts) == 1
        assert arts[0].run_id == "run_A"

    def test_discover_filters_by_run_id(self, workspace):
        reg = ArtifactRegistry(workspace)
        (workspace / "Projects" / "P").mkdir(parents=True)
        reg.publish("P", "research", data={"k": 1}, producer="x", summary="A",
                    run_id="run_A")
        reg.publish("P", "research", data={"k": 2}, producer="x", summary="B",
                    run_id="run_B")
        only_a = reg.discover("P", "research", run_id="run_A")
        assert len(only_a) == 1
        assert only_a[0].run_id == "run_A"

    def test_discover_no_filter_returns_all(self, workspace):
        reg = ArtifactRegistry(workspace)
        (workspace / "Projects" / "P").mkdir(parents=True)
        reg.publish("P", "research", data={"k": 1}, producer="x", summary="A",
                    run_id="run_A")
        reg.publish("P", "research", data={"k": 2}, producer="x", summary="B",
                    run_id="run_B")
        assert len(reg.discover("P", "research")) == 2

    def test_discover_run_id_filter_excludes_legacy_no_run_id(self, workspace, monkeypatch):
        """A run-scoped discover must NOT leak a run_id-less legacy entry."""
        import scripts.artifact_cli as cli
        reg = ArtifactRegistry(workspace)
        _seed_artifact(workspace, "P", art_id="art_legacy", art_type="research",
                       run_id=None, payload={"k": 1})
        legacy_only = reg.discover("P", "research", run_id="run_A")
        assert legacy_only == []
