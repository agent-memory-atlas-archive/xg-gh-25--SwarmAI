"""§4.9 Phase 3 块A — the FOUR boundary cases of review-deliverable check-in (AC3).

Each boundary is a design §4.9 边界 that must behave correctly, and R28 requires
each recovery/boundary path to have a FORCED execution test (not just "compiles"):

  边界① gitignore conflict → WARN + skip B, NEVER edit the user's .gitignore (P4)
  边界② non-git / workspace-only → degrade to ledger A, no B (covered in
          test_artifact_cli_run_commit.py::TestReviewDeliverableCheckin too; the
          generator-level non-git case is here)
  边界③ sealed-only → B carries ONLY the sealed definition (REPORT.md +
          requirements.json + run-ref.txt), NOT every per-stage snapshot
  边界④ multi-git-root → B lands in the MOST-MODIFIED root only, never duplicated

These drive `_generate_review_deliverable` directly (unit) where the boundary is a
property of B generation, and through `cmd_run_commit` (integration) where it is a
property of root selection.

Design canon: Knowledge/Designs/2026-10-12-pipeline-requirement-spec-and-scope-depth-design.md §4.9
"""
import json
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "Projects" / "TestProject" / ".artifacts" / "runs").mkdir(parents=True)
    return tmp_path


def _write_run_with_report(workspace, run_id, files_touched, *, report="# Report\n## Intent → Requirement 溯源\nFR-1\n",
                           eval_artifact=None):
    run_dir = workspace / "Projects" / "TestProject" / ".artifacts" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stages = [{"stage": "deliver", "status": "completed", "push_ready": True}]
    if eval_artifact is not None:
        stages.insert(0, {"stage": "evaluate", "status": "completed", "artifact_id": "art_eval1"})
    data = {
        "id": run_id, "project": "TestProject", "requirement": "Phase3 thing",
        "profile": "goal", "status": "running", "stages": stages,
        "created_at": "2026-10-12T00:00:00+00:00", "updated_at": "2026-10-12T00:00:00+00:00",
        "files_touched": files_touched,
    }
    (run_dir / "run.json").write_text(json.dumps(data), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(report)
    return run_dir


def _src_repo(tmp_path, name, gitignore=None):
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.co")
    _git(repo, "config", "user.name", "t")
    if gitignore is not None:
        (repo / ".gitignore").write_text(gitignore)
    (repo / "f.py").write_text("v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    (repo / "f.py").write_text("v2\n")
    return repo


def _run_commit(workspace, run_id, force=False):
    from scripts.artifact_cli import cmd_run_commit
    from unittest.mock import patch
    args = Namespace(project="TestProject", run_id=run_id, force=force)
    captured = {}
    with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
        try:
            cmd_run_commit(args, reg=None)
        except SystemExit as e:
            captured["exit"] = e.code
    return captured


class TestBoundary1GitignoreConflict:
    """边界①: .aidlc/deliverables/ gitignored → WARN + skip B, never edit .gitignore."""

    def test_gitignored_dest_skips_B_and_does_not_edit_gitignore(self, workspace, tmp_path, capsys):
        repo = _src_repo(tmp_path, "ignrepo", gitignore=".aidlc/\n")
        gitignore_before = (repo / ".gitignore").read_text()
        _write_run_with_report(workspace, "run_ign", [str(repo / "f.py")])

        _run_commit(workspace, "run_ign")
        capsys.readouterr()

        # B dir NOT created (would never be committed anyway).
        assert not (repo / ".aidlc" / "deliverables" / "run_ign").exists(), \
            "B must be skipped when its dest is gitignored"
        # The user's .gitignore is UNTOUCHED (P4 — never silently edit the user's file).
        assert (repo / ".gitignore").read_text() == gitignore_before, \
            "must NOT edit the user's .gitignore"
        # The code commit still happened (B skip never blocks the code).
        head = _git(repo, "show", "--name-only", "--format=", "HEAD").stdout
        assert "f.py" in head, "code commit must still proceed when B is skipped"


class TestBoundary2NonGit:
    """边界②: a non-git project (STEERING #5: only SwarmAI DDD is in git) → the run's
    files resolve to NO git repo → B is NOT generated (deliver via ledger A), and the
    run-commit does not crash. This is the REAL boundary behavior, exercised through
    cmd_run_commit (where the git-root gating lives), not just the generator."""

    def test_non_git_files_produce_no_B_and_no_crash(self, workspace, tmp_path, capsys):
        # A plain (non-git) dir holding the run's touched file — like an internal
        # project that is pure local disk, never a git repo.
        plain = tmp_path / "plaindir"
        plain.mkdir()
        (plain / "f.py").write_text("x=1\n")
        _write_run_with_report(workspace, "run_ng", [str(plain / "f.py")])

        cap = _run_commit(workspace, "run_ng")
        capsys.readouterr()

        # No B anywhere under the non-git dir (there is no repo to check it into).
        assert not (plain / ".aidlc").exists(), \
            "a non-git project must get NO B (deliver via ledger A, §4.9 边界②)"
        # run-commit refused cleanly (no git repo for the file → nothing committed),
        # NOT a crash/traceback. exit code is a controlled refusal (2) or clean return.
        assert cap.get("exit") in (None, 2), f"expected clean refusal, got {cap}"
        # Ledger A still intact (the deliverable lives there for audit).
        run_dir = workspace / "Projects/TestProject/.artifacts/runs/run_ng"
        assert (run_dir / "REPORT.md").is_file(), "ledger A REPORT.md must remain for audit"


class TestBoundary3SealedOnly:
    """边界③: B carries ONLY the sealed definition, never per-stage snapshots."""

    def test_B_contains_only_sealed_files(self, workspace, tmp_path, capsys):
        repo = _src_repo(tmp_path, "sealedrepo")
        run_dir = _write_run_with_report(workspace, "run_seal", [str(repo / "f.py")])
        # Litter ledger A with per-stage snapshot files that must NOT leak into B.
        (run_dir / "checkpoint-plan.json").write_text("{}")
        (run_dir / "evaluation-20261012-art_x.json").write_text("{}")
        (run_dir / "METRICS.json").write_text("{}")

        _run_commit(workspace, "run_seal")
        capsys.readouterr()

        bdir = repo / ".aidlc" / "deliverables" / "run_seal"
        got = sorted(p.name for p in bdir.iterdir()) if bdir.exists() else []
        # ONLY the sealed trio (requirements.json present only if an eval artifact
        # existed — this run has none, so just REPORT.md + run-ref.txt).
        assert set(got) <= {"REPORT.md", "requirements.json", "run-ref.txt"}, \
            f"B must contain ONLY sealed files, got {got}"
        assert "checkpoint-plan.json" not in got
        assert "METRICS.json" not in got
        assert "evaluation-20261012-art_x.json" not in got


class TestBoundary4MultiRoot:
    """边界④: B lands in the MOST-MODIFIED root only, never duplicated across roots."""

    def test_B_lands_in_most_modified_root_only(self, workspace, tmp_path, capsys):
        repo_big = _src_repo(tmp_path, "bigrepo")
        repo_small = _src_repo(tmp_path, "smallrepo")
        # big has 2 touched files, small has 1 → big is most-modified → B there only.
        (repo_big / "g.py").write_text("v2\n")
        _write_run_with_report(
            workspace, "run_multi",
            [str(repo_big / "f.py"), str(repo_big / "g.py"), str(repo_small / "f.py")],
        )
        _run_commit(workspace, "run_multi")
        capsys.readouterr()

        assert (repo_big / ".aidlc" / "deliverables" / "run_multi").exists(), \
            "B must land in the most-modified root (bigrepo)"
        assert not (repo_small / ".aidlc" / "deliverables" / "run_multi").exists(), \
            "B must NOT be duplicated into the less-modified root (smallrepo)"


class TestContentSafetyScan:
    """§4.9 边界③ FR-4 (AC4): B carries verbatim intent/clarifications and lands in a
    possibly-public repo. A content-safety scan (reused from ddd_packager — the SAME
    fail-closed scan s_ddd-distribute runs) must flag sensitive content BEFORE check-in
    so the human reviews before pushing. Never auto-redact (don't mutate the audit
    record); never block the LOCAL commit (push is the separate human gate)."""

    def test_sensitive_report_triggers_content_safety_warning(self, workspace, tmp_path):
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "sensrepo")
        # A's REPORT.md carries a secret (verbatim user intent could contain one).
        _write_run_with_report(
            workspace, "run_sens", [str(repo / "f.py")],
            report='# Report\n## Intent 溯源\n用户说: token = "hunter2secret"\n',
        )
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_sens", str(repo))

        # B was still generated (we never block the LOCAL commit)...
        assert any("REPORT.md" in c for c in created)
        # ...but a LOUD content-safety warning fired naming the sensitive finding.
        joined = " ".join(warnings)
        assert "CONTENT-SAFETY" in joined, f"must warn on sensitive content, got {warnings}"
        assert "sensitive finding" in joined or "finding" in joined

    def test_clean_report_no_content_safety_warning(self, workspace, tmp_path):
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "cleanrepo")
        _write_run_with_report(
            workspace, "run_clean", [str(repo / "f.py")],
            report="# Report\n## Intent 溯源\n用户要加一个 depth 轴到 pipeline。\n",
        )
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_clean", str(repo))

        assert any("REPORT.md" in c for c in created)
        assert not any("CONTENT-SAFETY" in w for w in warnings), \
            f"clean content must not trigger a false content-safety warning, got {warnings}"
