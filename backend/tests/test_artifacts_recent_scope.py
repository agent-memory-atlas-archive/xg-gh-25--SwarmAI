"""Tests for /artifacts/recent SCOPE — membership must match the Canvas OUTPUTS rail.

The Artifacts list is the human-facing product list; it must decide membership with the
SAME source-of-truth as the Canvas rail — the ``needs_human_review`` ``kind`` verdict
(keep ``content``/``knowledge``, drop ``source``/``process``) — NOT its own directory
allowlist. These tests pin that contract:

- a ``content`` or ``knowledge`` path is KEPT
- a ``source`` path (a bound-worktree code file — what the Canvas rail suppresses) is DROPPED
- a ``process`` path (dot-dir / machine noise) is DROPPED
- the 30-day dedup + mtime-desc sort + extension->type classification are preserved

The classifier (``needs_human_review_batch``) is monkeypatched to return known verdicts
so the test is deterministic and does not depend on a real git worktree.
"""
import pytest

from routers import artifacts as art
from core.needs_human_review import ReviewVerdict


# A synthetic `git log --format=%aI --name-only` stream: each ISO line is followed by
# a blank separator then its file paths. Newest first.
_GIT_LOG = """2026-09-28T10:00:00+08:00

Knowledge/Reports/account-360.html
Projects/acme/src/main.py

2026-09-27T09:00:00+08:00

Projects/SwarmAI/2-understanding/TECH.md
.context/MEMORY.md

2026-09-20T08:00:00+08:00

Knowledge/Notes/old.md
"""


# The kind each path should be classified as (what needs_human_review_batch returns).
_KINDS = {
    "Knowledge/Reports/account-360.html": "content",     # SwarmWS user doc  -> KEEP
    "Projects/acme/src/main.py": "source",               # bound-worktree code -> DROP
    "Projects/SwarmAI/2-understanding/TECH.md": "knowledge",  # DDD doc      -> KEEP
    ".context/MEMORY.md": "process",                     # dot-dir noise    -> DROP
    "Knowledge/Notes/old.md": "content",                 # older content    -> KEEP
}


@pytest.fixture
def _patched_classifier(monkeypatch):
    """Monkeypatch needs_human_review_batch to return the fixed _KINDS verdicts."""
    def fake_batch(paths, operation="written", *, swarmws_root=None, deadline=None):
        return {
            p: ReviewVerdict(review_worthy=(_KINDS.get(p) in ("content", "knowledge")),
                             kind=_KINDS.get(p, "process"))
            for p in paths
        }
    monkeypatch.setattr(art, "needs_human_review_batch", fake_batch)
    return fake_batch


def test_scope_keeps_content_and_knowledge_drops_source_and_process(_patched_classifier):
    rows = art._parse_git_log(_GIT_LOG, "/fake/workspace")
    paths = {r["path"] for r in rows}
    # content + knowledge kept
    assert "Knowledge/Reports/account-360.html" in paths
    assert "Projects/SwarmAI/2-understanding/TECH.md" in paths
    assert "Knowledge/Notes/old.md" in paths
    # source (bound-worktree code) + process (dot-dir) dropped — the Canvas-rail alignment
    assert "Projects/acme/src/main.py" not in paths
    assert ".context/MEMORY.md" not in paths


def test_scope_preserves_mtime_desc_sort_and_type(_patched_classifier):
    rows = art._parse_git_log(_GIT_LOG, "/fake/workspace")
    # sorted newest-first
    stamps = [r["modified_at"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)
    # extension -> type classification preserved (chip mapping)
    by_path = {r["path"]: r for r in rows}
    # .html is not in EXTENSION_TYPE_MAP -> classified 'other' (visible under All chip)
    assert by_path["Knowledge/Reports/account-360.html"]["type"] == "other"  # .html
    assert by_path["Projects/SwarmAI/2-understanding/TECH.md"]["type"] == "document"  # .md
    # title is the basename
    assert by_path["Knowledge/Notes/old.md"]["title"] == "old.md"


def test_scope_empty_log_returns_empty(_patched_classifier):
    assert art._parse_git_log("", "/fake/workspace") == []


# ── run_d25d72be: CJK-named job output must be dropped end-to-end (NO mock) ───
# The real bug SMOKE caught: git log C-style-quotes a non-ASCII path
# (`"Services/…\346…"`), and the leading quote made the kind classifier's
# first-segment `Services` match fail → the file leaked back as `content`. The
# fix is `-c core.quotepath=false` on the git command. This test builds a REAL
# git repo with a CJK-named Services/ file and runs the REAL classifier (no mock)
# so it locks BOTH the quotepath flag and the job-output → process rule.
def test_cjk_named_services_job_output_dropped_end_to_end(tmp_path):
    import subprocess
    from core.project_registry import get_swarmws  # noqa: F401 (import parity)

    root = tmp_path / ".swarm-ai" / "SwarmWS"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / ".gitignore").write_text("*.db\n", encoding="utf-8")
    # a CJK-named automated job report + a real human deliverable
    job = root / "Services" / "stock-analysis" / "reports" / "2026-09-28-000002-歌尔股份.md"
    job.parent.mkdir(parents=True)
    job.write_text("machine output", encoding="utf-8")
    human = root / "Knowledge" / "Reports" / "weekly.md"
    human.parent.mkdir(parents=True)
    human.write_text("human report", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)

    # Same command shape as _run_git_log — INCLUDING the quotepath flag under test.
    raw = subprocess.run(
        ["git", "-c", "core.quotepath=false", "log", "--diff-filter=ACMR",
         "--name-only", "--format=%aI", "--since=30.days", "-n50", "--no-merges"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout
    # Guard: the flag actually produced a raw-UTF-8 (unquoted) path.
    assert "歌尔股份" in raw and '"Services' not in raw, \
        "quotepath=false must emit raw UTF-8, not a C-quoted path"

    rows = art._parse_git_log(raw, str(root))  # REAL classifier, no mock
    paths = {r["path"] for r in rows}
    assert not any("stock-analysis" in p for p in paths), \
        "CJK-named Services/ job output must be dropped (process), not surfaced"
    assert "Knowledge/Reports/weekly.md" in paths, "human deliverable must survive"


def test_no_directory_allowlist_authority_remains():
    """The 5-dir allowlist must no longer be the membership authority (defect fix)."""
    assert not hasattr(art, "_is_artifact_file"), "_is_artifact_file should be removed"
    assert not hasattr(art, "_ARTIFACT_DIRS"), "_ARTIFACT_DIRS should be removed"
