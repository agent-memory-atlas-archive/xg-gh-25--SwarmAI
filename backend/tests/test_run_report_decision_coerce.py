"""Regression: run-report must survive string-shaped stage `decisions`.

DoD0a (run_e346b8ed). Pipeline stages write decisions as list[dict]
({classification, description, ...}), but session/DailyActivity-sourced
decisions are list[str]. Three sites in cmd_run_report consumed decisions
assuming dict shape (`**d`, `d.get(...)`), crashing with TypeError/AttributeError
on a bare string. This drove a real mid-pipeline crash (run_4261f1a3) that
blocked completion until the deliver decisions were hand-coerced to dicts.

The test builds a run.json with a STRING decision in BOTH a normal stage and
the reflect stage, then asserts run-report renders without raising.
Mutation check: revert any of the three coerces → this test raises.
"""

import json
from pathlib import Path


def _write_run(workspace: Path, run_id: str, stages: list, profile="full") -> Path:
    run_dir = workspace / "Projects" / "SwarmAI" / ".artifacts" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_data = {
        "id": run_id,
        "project": "SwarmAI",
        "requirement": "coerce regression",
        "profile": profile,
        "status": "completed",
        "stages": stages,
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
    }
    (run_dir / "run.json").write_text(json.dumps(run_data, indent=2))
    return run_dir


class _Args:
    def __init__(self, project, run_id, force=True):
        self.project = project
        self.run_id = run_id
        self.force = force


def test_string_decision_does_not_crash_report(tmp_path, monkeypatch):
    """String decisions at all 3 collection sites must not crash run-report."""
    monkeypatch.setenv("SWARM_WORKSPACE", str(tmp_path))
    from core.artifact_registry import ArtifactRegistry
    from scripts.artifact_cli import cmd_run_report

    stages = [
        {"stage": "evaluate", "status": "completed",
         "decisions": ["a bare string decision"]},
        {"stage": "build", "status": "completed",
         "decisions": [{"classification": "mechanical", "description": "dict decision"},
                       "mixed-in string decision"]},
        {"stage": "reflect", "status": "completed",
         "lessons": ["real lesson"],
         "decisions": ["reflect string decision"]},
    ]
    _write_run(tmp_path, "run_coerce01", stages)
    reg = ArtifactRegistry(tmp_path)

    # Must not raise — the coerce turns str → {"description": str} at all sites.
    cmd_run_report(_Args("SwarmAI", "run_coerce01"), reg)

    report = (tmp_path / "Projects" / "SwarmAI" / ".artifacts" / "runs"
              / "run_coerce01" / "REPORT.md")
    assert report.exists(), "report should be written despite string decisions"
    assert report.stat().st_size > 0


def test_dict_decisions_still_render(tmp_path, monkeypatch):
    """Coerce must not regress the normal dict path (classification counts)."""
    monkeypatch.setenv("SWARM_WORKSPACE", str(tmp_path))
    from core.artifact_registry import ArtifactRegistry
    from scripts.artifact_cli import cmd_run_report

    stages = [
        {"stage": "build", "status": "completed",
         "decisions": [
             {"classification": "taste", "description": "chose X"},
             {"classification": "mechanical", "description": "used pytest"},
         ]},
        {"stage": "reflect", "status": "completed", "lessons": ["l"], "decisions": []},
    ]
    _write_run(tmp_path, "run_coerce02", stages)
    reg = ArtifactRegistry(tmp_path)

    cmd_run_report(_Args("SwarmAI", "run_coerce02"), reg)
    report = (tmp_path / "Projects" / "SwarmAI" / ".artifacts" / "runs"
              / "run_coerce02" / "REPORT.md")
    assert report.exists() and report.stat().st_size > 0


def _publish_run_scoped_eval(workspace: Path, run_id: str, data: dict):
    """Publish a run-scoped evaluation artifact (manifest + runs/<id>/ file) and
    return its artifact_id — mirrors the real --run-id publish path so cmd_run_report
    loads it via _load_artifact_for_metrics (the artifact_id/manifest path)."""
    from core.artifact_registry import ArtifactRegistry
    reg = ArtifactRegistry(workspace)
    return reg.publish(
        project="SwarmAI", artifact_type="evaluation", data=data,
        producer="evaluate", summary="run-scoped eval", run_id=run_id,
    )


def test_report_does_not_cross_contaminate_from_bare_date_file(tmp_path, monkeypatch):
    """#4 (Kiro, HIGH): cmd_run_report must NOT overwrite this run's correctly-loaded
    (artifact_id) evaluate artifact with a run-blind bare top-level {type}-{date}.json
    just because the loaded artifact lacks a recommended field (scores). The deleted
    date-fallback block (artifact_cli.py:4255-4285) did exactly that.

    Fixture: run-A's evaluate artifact is published run-scoped and GENUINELY OMITS
    `scores` (so the old trigger `not get("scores")` would fire), carrying a unique
    RUN_A marker in acceptance_criteria. A bare top-level evaluation-<run_date>.json
    (a DIFFERENT run's leftover) carries scores + a POLLUTION marker. The report must
    show RUN_A's marker and NEVER the POLLUTION marker.

    Mutation: restore the date-fallback block → POLLUTION marker leaks into REPORT.md
    AND RUN_A's marker is displaced → this test goes RED (proven by Gate-1)."""
    monkeypatch.setenv("SWARM_WORKSPACE", str(tmp_path))
    from core.artifact_registry import ArtifactRegistry
    from scripts.artifact_cli import cmd_run_report

    run_id = "run_contam01"
    # project dir must exist for publish — _write_run creates runs/<id>/; also seed the
    # minimal DDD docs cmd_run_report / registry expect at the project root.
    run_dir = _write_run(tmp_path, run_id, [
        {"stage": "evaluate", "status": "completed"},
    ])
    proj = tmp_path / "Projects" / "SwarmAI"
    for name in ("PRODUCT.md", "TECH.md", "IMPROVEMENT.md", "PROJECT.md"):
        (proj / name).write_text("# T\n")

    # run-A's REAL evaluate artifact: run-scoped, NO scores key, unique marker.
    eval_data = {
        "recommendation": "GO", "scope": "standard",
        "acceptance_criteria": ["RUN_A_UNIQUE_ACCEPTANCE_abc123"],
        # NOTE: deliberately NO "scores" key.
    }
    art_id = _publish_run_scoped_eval(tmp_path, run_id, eval_data)

    # wire the artifact_id into run.json's evaluate stage (the manifest-load path)
    run_json = run_dir / "run.json"
    rj = json.loads(run_json.read_text())
    for s in rj["stages"]:
        if s["stage"] == "evaluate":
            s["artifact_id"] = art_id
    run_json.write_text(json.dumps(rj))

    # the POLLUTION source: a bare top-level evaluation-<run_date>.json from a DIFFERENT
    # run — carries scores (so it looks "more complete") + a distinct marker.
    artifacts_dir = proj / ".artifacts"
    bare = artifacts_dir / "evaluation-20260707.json"  # run_date = created_at[:10] → 20260707
    bare.write_text(json.dumps({
        "recommendation": "GO", "scope": "standard",
        "scores": {"roi": "high"},
        "acceptance_criteria": ["POLLUTION_FROM_OTHER_RUN_xyz789"],
    }))

    cmd_run_report(_Args("SwarmAI", run_id), ArtifactRegistry(tmp_path))
    report = (run_dir / "REPORT.md").read_text(encoding="utf-8")

    assert "RUN_A_UNIQUE_ACCEPTANCE_abc123" in report, \
        "this run's own acceptance must appear in the report"
    assert "POLLUTION_FROM_OTHER_RUN_xyz789" not in report, \
        "a different run's bare date-file must NEVER contaminate this run's report (#4)"
