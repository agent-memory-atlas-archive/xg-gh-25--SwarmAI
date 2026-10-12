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
                           eval_artifact=None, requirements="default"):
    """Write a run with a terminal REPORT.md on disk (ledger A). Since B's content
    契约 is now the EVALUATE requirements[] (NOT the REPORT.md), B generation needs a
    RESOLVABLE evaluate artifact — so by default this also lands a real evaluate
    artifact file + manifest entry (so cmd_run_commit's _load_artifact_for_metrics
    resolves it). Pass requirements=None to omit it (the 'no requirements → no B' case)."""
    run_dir = workspace / "Projects" / "TestProject" / ".artifacts" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    reqs = ([{"id": "FR-1", "statement": "ship a thing", "work_class": "task",
              "source": {"kind": "user-stated", "ref": "test"}, "status": "confirmed",
              "acceptance": [{"given": "g", "when": "w", "then": "t"}]}]
            if requirements == "default" else requirements)
    stages = [{"stage": "deliver", "status": "completed", "push_ready": True}]
    if reqs or eval_artifact is not None:
        stages.insert(0, {"stage": "evaluate", "status": "completed", "artifact_id": "art_eval1"})
        # Land a REAL evaluate artifact file + manifest entry so the cmd_run_commit
        # path's _load_artifact_for_metrics(project, "art_eval1") resolves requirements.
        art_dir = workspace / "Projects" / "TestProject" / ".artifacts"
        art_file = art_dir / f"evaluation-20261012-art_eval1.json"
        art_file.write_text(json.dumps({"schema_version": 1, "requirements": reqs or [],
                                         "clarifications": []}), encoding="utf-8")
        manifest_file = art_dir / "manifest.json"
        manifest = {"artifacts": []}
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest = {"artifacts": []}
        manifest.setdefault("artifacts", []).append(
            {"id": "art_eval1", "file": art_file.name, "type": "evaluation"})
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
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


def _write_run_with_requirements(workspace, run_id, files_touched, *, write_report=False,
                                 requirements=None, clarifications=None):
    """AC3 契约迁移 fixture: a run whose B-generation substance is the EVALUATE
    `requirements[]` (NOT a terminal REPORT.md). By default write_report=False —
    this reproduces the REAL DELIVER-time sequence where run-commit runs BEFORE
    REFLECT writes REPORT.md. B must still generate from requirements."""
    run_dir = workspace / "Projects" / "TestProject" / ".artifacts" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stages = [
        {"stage": "evaluate", "status": "completed", "artifact_id": "art_eval1"},
        {"stage": "deliver", "status": "completed", "push_ready": True},
    ]
    data = {
        "id": run_id, "project": "TestProject",
        "requirement": "把 depth 轴加到 pipeline(需求溯源快照内容来源)",
        "profile": "full", "status": "running", "stages": stages,
        "created_at": "2026-10-12T00:00:00+00:00", "updated_at": "2026-10-12T00:00:00+00:00",
        "files_touched": files_touched,
    }
    (run_dir / "run.json").write_text(json.dumps(data), encoding="utf-8")
    if write_report:
        (run_dir / "REPORT.md").write_text("# Report\n## 9. Lessons\n- learned X\n")
    reqs = requirements if requirements is not None else [
        {"id": "FR-1", "statement": "加 depth 正交轴", "work_class": "task",
         "source": {"kind": "user-stated", "ref": "XG 要求"}, "status": "confirmed",
         "acceptance": [{"given": "a run", "when": "set depth", "then": "rigor adjusts"}]},
    ]
    eval_art = {
        "schema_version": 1, "requirements": reqs,
        "clarifications": clarifications if clarifications is not None else [],
    }
    return run_dir, eval_art


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


class TestContentContractFromRequirements:
    """AC1-AC4 系统化修订: B's audit content is a REQUIREMENTS.md rendered from the
    EVALUATE requirements[], NOT a copy of A's terminal REPORT.md. The generation
    threshold is 'run has sealed requirements', NOT 'A has REPORT.md on disk'. This
    reproduces the REAL DELIVER-time sequence (run-commit at DELIVER, BEFORE REFLECT
    writes REPORT.md) under which the OLD report-gate made B never generate."""

    def test_B_generates_from_requirements_without_report(self, workspace, tmp_path):
        """AC3 (tracer): no REPORT.md on disk (true DELIVER timing) + sealed
        requirements present → B generates REQUIREMENTS.md. Under the OLD report-gate
        this returned [] (B never generated) — the bug this run fixes."""
        from scripts.artifact_cli import _generate_review_deliverable, LoadResult
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "reqrepo")
        _run_dir, eval_art = _write_run_with_requirements(
            workspace, "run_req", [str(repo / "f.py")], write_report=False)

        with patch("scripts.artifact_cli._get_workspace", return_value=workspace), \
             patch("scripts.artifact_cli._load_artifact_for_metrics",
                   return_value=LoadResult("available", eval_art)):
            created, warnings = _generate_review_deliverable("TestProject", "run_req", str(repo))

        # B WAS generated despite no REPORT.md (the whole point of the fix).
        assert created, f"B must generate from requirements with no REPORT.md; got {warnings}"
        # The audit file is REQUIREMENTS.md (name matches content — the §4.6 provenance),
        # NOT REPORT.md (which would imply a full terminal report).
        names = {Path(c).name for c in created}
        assert "REQUIREMENTS.md" in names, f"B must carry REQUIREMENTS.md, got {names}"
        assert "REPORT.md" not in names, f"B must NOT carry a terminal REPORT.md, got {names}"

    def test_REQUIREMENTS_md_has_provenance_not_lessons(self, workspace, tmp_path):
        """AC2+AC4: REQUIREMENTS.md carries the §4.6 provenance (intent + derivation),
        and does NOT carry REFLECT-stage process sections (§9 Lessons / §2 Evaluation)
        which the design canon assigns to ledger A only."""
        from scripts.artifact_cli import _generate_review_deliverable, LoadResult
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "provrepo")
        # write_report=True puts a '## 9. Lessons' in A's REPORT — proving B does NOT
        # copy it (B renders from requirements, independent of A's terminal report).
        _run_dir, eval_art = _write_run_with_requirements(
            workspace, "run_prov", [str(repo / "f.py")], write_report=True)

        with patch("scripts.artifact_cli._get_workspace", return_value=workspace), \
             patch("scripts.artifact_cli._load_artifact_for_metrics",
                   return_value=LoadResult("available", eval_art)):
            created, _ = _generate_review_deliverable("TestProject", "run_prov", str(repo))

        req_md = next((c for c in created if Path(c).name == "REQUIREMENTS.md"), None)
        assert req_md, f"REQUIREMENTS.md must exist, got {created}"
        body = Path(req_md).read_text(encoding="utf-8")
        # provenance present (rendered from requirements)
        assert "FR-1" in body, "REQUIREMENTS.md must render the requirements derivation"
        # REFLECT process noise absent (lives in ledger A only)
        assert "9. Lessons" not in body and "learned X" not in body, \
            "B must NOT carry REFLECT lessons (ledger A only — §4.9 双存储)"

    def test_no_requirements_no_B(self, workspace, tmp_path):
        """AC1: when NO sealed requirements can be resolved, B is not generated
        (nothing to deliver) — the new threshold's negative case."""
        from scripts.artifact_cli import _generate_review_deliverable, LoadResult
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "norepo")
        _write_run_with_requirements(workspace, "run_noreq", [str(repo / "f.py")])
        # Artifact does not resolve (not_run / unavailable) → .data is None → no B.
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace), \
             patch("scripts.artifact_cli._load_artifact_for_metrics",
                   return_value=LoadResult("not_run", None)):
            created, _ = _generate_review_deliverable("TestProject", "run_noreq", str(repo))
        assert created == [], f"no sealed requirements → no B; got {created}"


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
        assert set(got) <= {"REQUIREMENTS.md", "requirements.json", "run-ref.txt"}, \
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
        # B's content is now the §4.6 provenance rendered from requirements — the
        # VERBATIM original intent (run.requirement) is rendered PLAINTEXT into
        # REQUIREMENTS.md's "原始意图" section, so a secret in the intent reaches B.
        _write_run_with_report(workspace, "run_sens", [str(repo / "f.py")])
        # Inject a secret into the run's requirement (the verbatim intent B renders).
        rf = workspace / "Projects/TestProject/.artifacts/runs/run_sens/run.json"
        rd = json.loads(rf.read_text())
        rd["requirement"] = 'add retry; user pasted token = "hunter2secret" by mistake'
        rf.write_text(json.dumps(rd))
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_sens", str(repo))

        # B was still generated (we never block the LOCAL commit)...
        assert any("REQUIREMENTS.md" in c for c in created)
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
        )
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_clean", str(repo))

        assert any("REQUIREMENTS.md" in c for c in created)
        assert not any("CONTENT-SAFETY" in w for w in warnings), \
            f"clean content must not trigger a false content-safety warning, got {warnings}"
