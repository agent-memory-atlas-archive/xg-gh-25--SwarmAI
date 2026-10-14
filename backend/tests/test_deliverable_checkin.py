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


def _write_run_with_report(workspace, run_id, files_touched,
                           *, report=("# Report\n## Intent → Requirement 溯源\nFR-1\n"
                                      "## 9. Lessons\n- [note] a real projected report always carries §9\n"),
                           eval_artifact=None, requirements="default"):
    # Default report carries a SUBSTANTIVE §9 (a '- ' lesson bullet) because a real
    # cmd_run_report projection ALWAYS renders §9 — the §9-degenerate B-copy gate
    # (run_7c30c517) would otherwise correctly skip B for a stub report missing §9,
    # which is not what tests of OTHER contracts (sealed-only, content-safety) mean to
    # exercise. Degeneracy is tested explicitly in TestSection9DegenerateGate.
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


class TestContentContractCopyReport:
    """AC1-AC4 回退(run_1d663ea0): B's audit content is a verbatim COPY of ledger A's
    terminal REPORT.md — which ALREADY contains the §4.6 '需求溯源审计' (Intent→Requirement)
    section (rendered into it by cmd_run_report via render_audit_trail_md). B carries a
    single REPORT.md (NOT a separate REQUIREMENTS.md). The generation threshold is
    'A has REPORT.md on disk' — which IS satisfied at run-commit time because deliver.md
    generates REPORT.md (Pipeline Report step) BEFORE run-commit. run_44a06138 is the
    known-good proof: its B is a verbatim copy of A's terminal REPORT.md incl. §9 Lessons."""

    def test_B_is_a_copy_of_terminal_report(self, workspace, tmp_path):
        """AC1+AC2 (tracer): A has a terminal REPORT.md containing the §需求溯源审计
        section → B copies it verbatim as REPORT.md (NOT a separate REQUIREMENTS.md)."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "reprepo")
        report_body = ("# Autonomous Pipeline Report: thing\n## TL;DR\ndone\n"
                       "## 需求溯源审计 (Requirement Provenance Audit)\n"
                       "### 原始意图 (Original Intent)\n> add depth axis\nFR-1\n"
                       "## 9. Lessons\n- learned X\n")
        _write_run_with_report(workspace, "run_rep", [str(repo / "f.py")], report=report_body)

        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_rep", str(repo))

        assert created, f"B must generate when A has REPORT.md; got {warnings}"
        names = {Path(c).name for c in created}
        # B carries a single terminal REPORT.md (the §4.6 provenance section lives INSIDE it),
        # NOT a separate REQUIREMENTS.md.
        assert "REPORT.md" in names, f"B must carry REPORT.md, got {names}"
        assert "REQUIREMENTS.md" not in names, f"B must NOT carry a separate REQUIREMENTS.md, got {names}"
        # The copy is verbatim — identical bytes to ledger A's terminal REPORT.md.
        b_report = next(c for c in created if Path(c).name == "REPORT.md")
        a_report = workspace / "Projects" / "TestProject" / ".artifacts" / "runs" / "run_rep" / "REPORT.md"
        assert Path(b_report).read_text(encoding="utf-8") == a_report.read_text(encoding="utf-8"), \
            "B's REPORT.md must be a verbatim copy of ledger A's terminal REPORT.md"

    def test_copied_report_carries_provenance_section(self, workspace, tmp_path):
        """AC2: the copied REPORT.md carries the §4.6 需求溯源审计 section (Intent→
        Requirement) — the whole point of copying the terminal report (it has the
        provenance section baked in by cmd_run_report)."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "provrepo2")
        report_body = ("# Report\n## 需求溯源审计 (Requirement Provenance Audit)\n"
                       "### 原始意图\n> the original intent verbatim\n"
                       "### 需求推导\nFR-1: add depth\n## 9. Lessons\n- lesson\n")
        _write_run_with_report(workspace, "run_prov2", [str(repo / "f.py")], report=report_body)

        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, _ = _generate_review_deliverable("TestProject", "run_prov2", str(repo))

        b_report = next((c for c in created if Path(c).name == "REPORT.md"), None)
        assert b_report, f"B REPORT.md must exist, got {created}"
        body = Path(b_report).read_text(encoding="utf-8")
        assert "需求溯源审计" in body, "copied REPORT.md must carry the §4.6 provenance section"
        assert "the original intent verbatim" in body, "provenance section must carry the original intent"
        assert "FR-1" in body, "provenance section must carry the requirement derivation"

    def test_no_report_no_B_warns_loudly(self, workspace, tmp_path):
        """AC3 + meta-review MED: when A has NO terminal REPORT.md on disk, B is not
        generated (nothing to copy) AND a LOUD warning is returned (NOT a silent no-op).
        The report-before-commit ordering is agent-discipline prose, so an ordering
        violation must surface in run-commit's WARN channel — else B silently never
        generates (the exact bug this saga reverts). deliver.md's Pipeline Report step
        normally guarantees REPORT.md exists before run-commit; this is the loud guard
        if it somehow does not."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "noreprepo")
        # _write_run_with_requirements writes NO REPORT.md by default (write_report=False)
        _write_run_with_requirements(workspace, "run_norep", [str(repo / "f.py")], write_report=False)
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_norep", str(repo))
        assert created == [], f"no terminal REPORT.md → no B; got {created}"
        # NOT a silent no-op — the ordering-violation case must warn loudly.
        assert warnings and any("no terminal REPORT.md" in w for w in warnings), \
            f"missing REPORT.md must WARN loudly (not silent), got {warnings}"


class TestReportIsLedgerProjectionNotPlaceholder:
    """AC1+AC4 (anti-drift guard): the audit copy B a reviewer sees in git must carry the
    run's REAL §9 REFLECT lessons — never the `_(populated in REFLECT)_` placeholder that
    the deleted hand-written template produced. B is a verbatim copy of ledger A; A is the
    deterministic ledger projection (`cmd_run_report`). This test goes RED if anyone
    re-introduces a hand-written template whose §9 is a frozen placeholder, OR if B is
    frozen before the lessons are seeded into the reflect record. It is the executable
    form of NFR-1 (completeness-as-contract: §9 shows truth, never a lying placeholder)."""

    def test_B_report_carries_real_lessons_not_placeholder(self, workspace, tmp_path):
        """A's terminal REPORT.md (projected with real §9 lessons present) → B copies it
        verbatim, so B's §9 carries the real lessons and NOT the removed placeholder."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "lessonsrepo")
        # A terminal report as cmd_run_report would project it with §9 FILLED (lessons
        # seeded into the reflect record at DELIVER-tail, before run-commit).
        report_body = (
            "# Report\n## 需求溯源审计\nFR-1\n"
            "## 9. Lessons\n"
            "- [pitfall] a one-shot event modeled as shared state is a race source\n"
            "- [decision] root-fix deletes the competing renderer, not patches it\n"
        )
        _write_run_with_report(workspace, "run_les", [str(repo / "f.py")], report=report_body)
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, _ = _generate_review_deliverable("TestProject", "run_les", str(repo))
        b_report = next((c for c in created if Path(c).name == "REPORT.md"), None)
        assert b_report, f"B REPORT.md must exist, got {created}"
        body = Path(b_report).read_text(encoding="utf-8")
        # The real lessons are present …
        assert "a one-shot event modeled as shared state" in body, \
            "B's §9 must carry the run's REAL reflect lessons (projected from the ledger)"
        # … and the removed hand-written-template placeholder is NOT.
        assert "_(populated in REFLECT)_" not in body, \
            "B must NEVER carry the §9 placeholder — that was the two-renderer drift this fix removes"

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


class TestSection9DegenerateGate:
    """run_7c30c517 — the structural gate that turns the DELIVER ordering invariant
    (seed-lessons → run-report → run-commit) from agent-discipline PROSE into CODE.

    The gap: B is copied from A/REPORT.md verbatim at run-commit. If a run calls
    run-commit BEFORE seeding lessons, A's §9 is DEGENERATE (no real lesson bullets)
    and B freezes it; the completion gate inspects only ledger A, never B → permanent
    A/B drift undetected. §9 has TWO degenerate forms, both must be caught:
      • 5178: '(REFLECT stage did not record lessons for this run)' — reflect empty
      • 5176: '**⏭ Skipped** — …'                                  — reflect ABSENT (the
        DEFAULT at a pre-REFLECT run-commit — Gate-1 caught v1 missing this one)
    The check is §9-SLICE-scoped (not a whole-doc literal match), so §3/§8 '⏭ Skipped'
    cannot false-positive, and a real lesson bullet in §9 passes."""

    _DEGEN_5178 = (
        "# Report\n## 需求溯源审计\nFR-1\n"
        "## 9. Lessons\n(REFLECT stage did not record lessons for this run)\n"
        "## 10. Known Gaps & Attention Flags\nNone identified.\n"
    )
    _DEGEN_5176 = (
        "# Report\n## 需求溯源审计\nFR-1\n"
        "## 9. Lessons\n**⏭ Skipped** — Not executed — pipeline completed before REFLECT\n"
        "## 10. Known Gaps & Attention Flags\nNone identified.\n"
    )
    # Real §9 lessons, BUT §3/§8 legitimately carry '⏭ Skipped' — the whole-doc-match
    # false-positive trap. §9-slice-scoping must let this through.
    _REAL_WITH_SKIPPED_SIBLINGS = (
        "# Report\n"
        "## 3. Methodology\n**⏭ Skipped** — profile 'bugfix' uses direct fix path\n"
        "## 8. Files Changed\n**⏭ Skipped** — profile omits build\n"
        "## 9. Lessons\n- [pitfall] a real durable lesson that earns its place in §9\n"
        "## 10. Known Gaps & Attention Flags\nNone identified.\n"
    )

    def test_degenerate_5178_no_lessons_skips_B_and_warns(self, workspace, tmp_path):
        """§9 = the empty-reflect placeholder (5178) → B is NOT written + a LOUD
        ordering warning is returned (the exact A/B drift this gate prevents)."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "degen5178")
        _write_run_with_report(workspace, "run_d78", [str(repo / "f.py")],
                               report=self._DEGEN_5178)
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_d78", str(repo))
        assert created == [], f"degenerate §9 → no B; got {created}"
        assert not (repo / ".aidlc" / "deliverables" / "run_d78" / "REPORT.md").exists(), \
            "a §9-placeholder REPORT.md must NEVER be written into git-committed B"
        assert warnings and any("§9" in w or "lessons" in w.lower() for w in warnings), \
            f"degenerate §9 must WARN loudly (ordering violation), got {warnings}"

    def test_degenerate_5176_skipped_reflect_skips_B_and_warns(self, workspace, tmp_path):
        """§9 = the reflect-SKIPPED form (5176) — the DEFAULT at a pre-REFLECT
        run-commit, which v1 missed. Must ALSO skip B + warn."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "degen5176")
        _write_run_with_report(workspace, "run_d76", [str(repo / "f.py")],
                               report=self._DEGEN_5176)
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_d76", str(repo))
        assert created == [], f"skipped-reflect §9 → no B; got {created}"
        assert warnings and any("§9" in w or "lessons" in w.lower() for w in warnings), \
            f"skipped-reflect §9 must WARN loudly, got {warnings}"

    def test_real_lessons_with_skipped_siblings_generates_B_no_false_positive(self, workspace, tmp_path):
        """§9 carries a REAL lesson bullet while §3/§8 legitimately show '⏭ Skipped'
        → B generates normally, NO ordering warning. Proves the check is §9-slice-
        scoped, not a whole-document '⏭ Skipped' match (the false-positive trap)."""
        from scripts.artifact_cli import _generate_review_deliverable
        from unittest.mock import patch
        repo = _src_repo(tmp_path, "realskip")
        _write_run_with_report(workspace, "run_rsk", [str(repo / "f.py")],
                               report=self._REAL_WITH_SKIPPED_SIBLINGS)
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_rsk", str(repo))
        assert created, f"real §9 lessons → B must generate even with §3/§8 skipped; got {warnings}"
        body = Path(next(c for c in created if Path(c).name == "REPORT.md")).read_text()
        assert "a real durable lesson" in body, "B must carry the real §9 lessons"
        assert not any("§9" in w or "lesson" in w.lower() for w in warnings), \
            f"a §9 WITH real lessons must NOT trigger the ordering warning, got {warnings}"

    def test_predicate_calls_both_degenerate_forms_degenerate(self):
        """AC3: the predicate catches BOTH degenerate §9 forms (empty-reflect 5178 +
        reflect-skipped 5176) and passes a real-lessons §9 — regardless of §3/§8 skips."""
        from scripts.artifact_cli import _report_section9_is_degenerate
        assert _report_section9_is_degenerate(self._DEGEN_5178) is True
        assert _report_section9_is_degenerate(self._DEGEN_5176) is True
        assert _report_section9_is_degenerate(self._REAL_WITH_SKIPPED_SIBLINGS) is False

    def test_degenerate_fixture_uses_renderer_constant_not_a_hardcoded_copy(self):
        """AC3 anti-drift: the empty-§9 degenerate case is built from the renderer's OWN
        constant `_NO_LESSONS_PLACEHOLDER` (not a hardcoded second copy of the string),
        and the predicate STILL calls it degenerate. This is the honest form of the
        'single source' claim: the renderer owns the string (one constant); the gate is
        STRUCTURAL ('- '-bullet convention) so it catches degeneracy even if that string
        drifts. If someone changes the renderer's placeholder, this test's fixture changes
        with it and the structural predicate still fires — no silent drift (Gate-2 MED)."""
        from scripts.artifact_cli import _report_section9_is_degenerate, _NO_LESSONS_PLACEHOLDER
        report = f"# Report\n## 9. Lessons\n{_NO_LESSONS_PLACEHOLDER}\n## 10. Known Gaps\nNone.\n"
        assert _report_section9_is_degenerate(report) is True, \
            "a §9 carrying ONLY the renderer's no-lessons placeholder must be degenerate"
        # And the renderer's placeholder is NOT itself a '- ' bullet (else the structural
        # gate would false-pass it) — the convention the gate relies on.
        assert not _NO_LESSONS_PLACEHOLDER.startswith("- "), \
            "the no-lessons placeholder must not look like a real lesson bullet"


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
        # B carries EXACTLY ONE file: a verbatim copy of ledger A's terminal
        # REPORT.md. The §4.6 需求溯源审计 (Intent→Requirement) provenance + §9
        # Lessons live INSIDE that single report (rendered by cmd_run_report), so
        # the old orphan sidecars (requirements.json machine-SRS + run-ref.txt
        # back-pointer) are gone — a reviewer resolves everything from the ONE
        # human-readable REPORT the ledger projects. Never a per-stage snapshot.
        assert set(got) == {"REPORT.md"}, \
            f"B must contain ONLY the projected REPORT.md, got {got}"
        assert "requirements.json" not in got, \
            "orphan requirements.json removed — provenance lives inside REPORT.md §4.6"
        assert "run-ref.txt" not in got, \
            "orphan run-ref.txt removed — a cross-machine reader cannot resolve its ledger path"
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
        # B is now a verbatim COPY of A's terminal REPORT.md — so a secret anywhere in
        # that report (its 需求溯源审计 section carries the verbatim original intent)
        # reaches B. Put the secret in the copied report body.
        _write_run_with_report(
            workspace, "run_sens", [str(repo / "f.py")],
            report=('# Report\n## 需求溯源审计\n### 原始意图\n'
                    '> add retry; user pasted token = "hunter2secret" by mistake\n'
                    '## 9. Lessons\n- [note] substantive §9 so the B-copy gate lets B through\n'),
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
        )
        with patch("scripts.artifact_cli._get_workspace", return_value=workspace):
            created, warnings = _generate_review_deliverable("TestProject", "run_clean", str(repo))

        assert any("REPORT.md" in c for c in created)
        assert not any("CONTENT-SAFETY" in w for w in warnings), \
            f"clean content must not trigger a false content-safety warning, got {warnings}"
