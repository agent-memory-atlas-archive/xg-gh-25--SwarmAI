"""Tests for ``core.artifact_source.classify_source``.

WHAT IS TESTED
    ``classify_source(abs_path, swarmws_root=None) -> (Literal['link','copy'], reason)``
    — the Artifact-Lifecycle P0 source classifier. A path owned by a known tree
    (SwarmWS or a bound worktree) is a ``link`` (live pointer, diffable); anything
    else is a ``copy`` candidate (a byte snapshot, if a version store ever captures it).

METHODOLOGY
    Real filesystem (tmp_path fixtures) + the real SwarmWS root — NO mocking. The
    whole point of the classifier is agreement with the canonical resolver
    ``needs_human_review._owning_tree``; a mock would defeat the test.

KEY PROPERTIES / INVARIANTS
    - AC1: classify_source AGREES with _owning_tree on every owned path (link) — it
      is a THIN WRAPPER over the single source, never a re-implemented tree-walk.
    - AC2: a disposable-root path (``/tmp/...``) is ``copy`` even when the dir itself
      contains a ``.git`` — because _owning_tree never walks to an external ``.git``,
      so tmp precedence is satisfied structurally (is_noise_path catches it).
    - AC3: ``/`` and ``$HOME`` are NEVER link roots (security case ported from
      KiroCrew) — a link root authorizes later reads, so a root that broad is refused.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from core.artifact_source import classify_source
from core.needs_human_review import _owning_tree
from core.project_registry import get_swarmws


# ── AC1: agreement with _owning_tree on owned paths (link) ──────────────────
def test_swarmws_file_is_link_and_agrees_with_owning_tree():
    ws = Path(get_swarmws()).resolve()
    target = ws / "MEMORY.md"
    verdict, reason = classify_source(str(target))
    owning = _owning_tree(target, ws)
    assert owning is not None, "precondition: MEMORY.md is inside SwarmWS"
    assert verdict == "link", f"owned path must be link, got {verdict} ({reason})"


def test_swarmws_root_itself_is_link():
    ws = Path(get_swarmws()).resolve()
    verdict, _reason = classify_source(str(ws))
    assert verdict == "link"


def test_nested_swarmws_path_is_link():
    ws = Path(get_swarmws()).resolve()
    nested = ws / "Projects" / "SwarmAI" / "PRODUCT.md"
    verdict, _ = classify_source(str(nested))
    # Agreement is what matters — both agree it's owned regardless of file existence,
    # because _owning_tree keys on relative_to, not on-disk presence.
    owning = _owning_tree(nested, ws)
    if owning is not None:
        assert verdict == "link"


def test_classify_agrees_with_owning_tree_across_sample_paths():
    """The core AC1 assertion: classify_source is a faithful wrapper — for every
    sampled path, (verdict == 'link') iff (_owning_tree is not None)."""
    ws = Path(get_swarmws()).resolve()
    samples = [
        ws,
        ws / "MEMORY.md",
        ws / "Projects" / "SwarmAI",
        Path("/tmp"),
        Path("/etc/hosts"),
        Path(os.path.expanduser("~")),
    ]
    for p in samples:
        p = p.resolve()
        verdict, reason = classify_source(str(p))
        owned = _owning_tree(p, ws) is not None
        assert (verdict == "link") == owned, (
            f"{p}: classify_source said {verdict} but _owning_tree owned={owned} ({reason})"
        )


# ── AC2: disposable-root precedence — tmp clone with its own .git is still copy ──
def test_tmp_path_is_copy(tmp_path):
    # tmp_path is under the OS temp root → is_noise_path → copy.
    f = tmp_path / "scratch.txt"
    f.write_text("hi")
    verdict, reason = classify_source(str(f))
    assert verdict == "copy", f"tmp path must be copy, got {verdict} ({reason})"


def test_tmp_cloned_repo_is_copy_despite_own_dotgit(tmp_path):
    """A cloned repo sitting in a disposable dir is STILL copy — the disposable
    root wins over the repo's own .git. _owning_tree returns None (it only knows
    SwarmWS + bound worktrees, never an external /tmp/.git), so the fallback's
    is_noise_path(tmp) catches it → copy."""
    repo = tmp_path / "cloned_repo"
    repo.mkdir()
    # give it a real .git so a naive .git walk-up would wrongly call it link
    subprocess.run(["git", "init", "-q"], cwd=str(repo), timeout=10, check=False)
    f = repo / "file.py"
    f.write_text("x = 1\n")
    verdict, reason = classify_source(str(f))
    assert verdict == "copy", (
        f"tmp-cloned repo must be copy (disposable precedence), got {verdict} ({reason})"
    )


# ── AC3: security — / and $HOME are never link roots ─────────────────────────
def test_root_is_not_a_link():
    verdict, _ = classify_source("/")
    assert verdict == "copy", "'/' must never be a link root"


def test_home_is_not_a_link():
    home = os.path.expanduser("~")
    verdict, _ = classify_source(home)
    assert verdict == "copy", "$HOME must never be a link root"


# ── robustness: never raises, declines non-absolute / empty / NUL ────────────
@pytest.mark.parametrize("bad", ["", "relative/path", "has\x00nul"])
def test_bad_input_is_copy_never_raises(bad):
    verdict, _ = classify_source(bad)
    assert verdict == "copy"
