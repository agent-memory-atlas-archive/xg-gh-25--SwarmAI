"""Cross-repo coverage for the adversarial marker's reviewed_paths (run_a5999658).

The bug: `_reviewed_paths_at_head(hook_cwd)` computed a SINGLE-repo `git diff HEAD`
of the sub-agent's cwd repo (the pipeline launch repo = swarmai). When BUILD wrote
files into the SEPARATE SwarmWS workspace repo, the marker recorded nothing about
them, so the adversarial commit gate could never diff-bind the SwarmWS pending paths
→ a permanent DENY for any workspace-resident pipeline.

The fix: scan a UNION of candidate repos {repo(hook_cwd), get_app_data_dir()/SwarmWS},
so BUILD's changed files are captured wherever they landed. Tri-state preserved:
None only if EVERY candidate repo is git-unavailable; [] if all reachable-and-clean;
else the union of absolute realpaths.

These tests stand up TWO real temp git repos to model launch-repo vs workspace-repo,
pointing get_app_data_dir() at the workspace via SWARM_DATA_DIR.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from backend.core.runtime_hooks import _reviewed_paths_at_head


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "seed.txt").write_text("seed\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")


@pytest.fixture
def two_repos(tmp_path, monkeypatch):
    """launch repo (the sub-agent's cwd) + workspace repo (SwarmWS via SWARM_DATA_DIR)."""
    launch = tmp_path / "swarmai"
    data_dir = tmp_path / "data"          # get_app_data_dir() → here
    workspace = data_dir / "SwarmWS"       # the workspace repo
    _init_repo(launch)
    _init_repo(workspace)
    # point config.get_app_data_dir() at our scratch data dir (escape-hatch)
    monkeypatch.setenv("SWARM_DATA_DIR", str(data_dir))
    return launch, workspace


def _abs(root: Path, rel: str) -> str:
    return os.path.realpath(str(root / rel))


def test_workspace_change_is_captured_when_cwd_is_launch_repo(two_repos):
    """THE BUG: hook_cwd = launch repo, but the changed file is in the workspace repo.
    The marker's reviewed_paths MUST include the workspace file."""
    launch, workspace = two_repos
    # BUILD wrote a file into the WORKSPACE repo (not the launch repo)
    (workspace / "agentcore-data-agent-handson" / "lambdas").mkdir(parents=True)
    wfile = workspace / "agentcore-data-agent-handson" / "lambdas" / "handler.py"
    wfile.write_text("# new handler\n")

    # hook_cwd is the LAUNCH repo (the sub-agent inherited swarmai cwd)
    reviewed = _reviewed_paths_at_head(str(launch))

    assert reviewed is not None, "must not be unbounded when repos are reachable"
    assert _abs(workspace, "agentcore-data-agent-handson/lambdas/handler.py") in reviewed, (
        f"workspace change not captured: {reviewed}"
    )


def test_launch_repo_change_still_captured(two_repos):
    """A change in the launch repo itself is still captured (no regression)."""
    launch, workspace = two_repos
    (launch / "backend").mkdir()
    (launch / "backend" / "mod.py").write_text("# edit\n")
    reviewed = _reviewed_paths_at_head(str(launch))
    assert reviewed is not None
    assert _abs(launch, "backend/mod.py") in reviewed


def test_both_repos_unioned(two_repos):
    """Changes in BOTH repos appear in the union."""
    launch, workspace = two_repos
    (launch / "a.py").write_text("# a\n")
    (workspace / "b.py").write_text("# b\n")
    reviewed = _reviewed_paths_at_head(str(launch))
    assert reviewed is not None
    assert _abs(launch, "a.py") in reviewed
    assert _abs(workspace, "b.py") in reviewed


def test_all_clean_returns_empty_not_none(two_repos):
    """Tri-state: all reachable repos clean → [] (bounded-empty), NOT None (unbounded).
    This is the fail-open red-line — a clean review bounds coverage to nothing, it
    does NOT unlock every commit."""
    launch, workspace = two_repos  # both seeded + clean
    reviewed = _reviewed_paths_at_head(str(launch))
    assert reviewed == [], f"clean repos must yield [] (bounded), got {reviewed!r}"


def test_non_repo_cwd_still_scans_workspace(two_repos, tmp_path):
    """If hook_cwd is NOT a git repo but the workspace repo is reachable + dirty,
    the workspace change is still captured (candidate-union, not cwd-only)."""
    launch, workspace = two_repos
    (workspace / "c.py").write_text("# c\n")
    non_repo = tmp_path / "not_a_repo"
    non_repo.mkdir()
    reviewed = _reviewed_paths_at_head(str(non_repo))
    assert reviewed is not None
    assert _abs(workspace, "c.py") in reviewed


def test_path_with_space_not_quote_mangled(two_repos):
    """A changed file whose name contains a SPACE must appear as a RAW path (no git
    C-quoting), so it matches the gate's `git diff --name-only` PENDING side byte-for-
    byte. Regression for the Gate-2 HIGH: `git status --porcelain` quotes `"my file.py"`
    while `git diff` does not → the reviewed path never covered the pending path → a
    genuinely-reviewed commit was falsely DENIED. The -z flag emits raw unquoted paths."""
    launch, workspace = two_repos
    spaced = workspace / "my file.py"
    spaced.write_text("# spaced\n")
    reviewed = _reviewed_paths_at_head(str(launch))
    assert reviewed is not None
    # the entry must be the RAW path (with a literal space), NOT quote-wrapped
    expected = os.path.realpath(str(spaced))
    assert expected in reviewed, f"raw-space path not captured cleanly: {reviewed}"
    # and NO entry may carry embedded quote characters (the quoting bug's signature)
    assert not any('"' in p for p in reviewed), f"quote-mangled path present: {reviewed}"


def test_dedup_when_cwd_is_the_workspace(two_repos):
    """If hook_cwd IS the workspace repo, candidates de-dupe by realpath (scan once,
    no doubled entries)."""
    launch, workspace = two_repos
    (workspace / "d.py").write_text("# d\n")
    reviewed = _reviewed_paths_at_head(str(workspace))
    assert reviewed is not None
    d_abs = _abs(workspace, "d.py")
    assert reviewed.count(d_abs) == 1, f"duplicate entry: {reviewed}"
