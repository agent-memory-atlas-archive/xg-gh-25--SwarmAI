"""Tests for ensure_project_metadata — the single project-registration primitive.

Root fix for the "pseudo-DDD" class: a Projects/<name>/ dir minted without a
.project.json is invisible to Brain Hub (list_brains → _list_project_dirs). This
primitive guarantees the registry file exists, only-if-absent + non-destructive.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.swarm_workspace_manager import ensure_project_metadata


def test_writes_project_json_when_absent(tmp_path):
    pdir = tmp_path / "Projects" / "MyProj"
    wrote = ensure_project_metadata(pdir, "MyProj")
    assert wrote is True
    meta = pdir / ".project.json"
    assert meta.exists(), "must create .project.json"
    d = json.loads(meta.read_text())
    # schema parity with create_project / migrate output (R27 — readers depend on these)
    assert d["id"] == "myproj-ddd"
    assert d["name"] == "MyProj"
    assert d["status"] == "active"
    assert "schema_version" in d and "ddd_spec_version" in d
    assert d["update_history"][0]["action"] == "created"


def test_noop_when_already_registered(tmp_path):
    """Idempotent + NON-DESTRUCTIVE: a 2nd call must NOT overwrite existing metadata."""
    pdir = tmp_path / "Projects" / "MyProj"
    ensure_project_metadata(pdir, "MyProj")
    meta = pdir / ".project.json"
    # simulate accrued history/edits a real project would have
    original = json.loads(meta.read_text())
    original["update_history"].append({"version": 2, "action": "edited"})
    original["description"] = "hand-edited"
    meta.write_text(json.dumps(original, indent=2))
    before = meta.read_text()

    wrote = ensure_project_metadata(pdir, "MyProj")
    assert wrote is False, "must be a no-op when already registered"
    assert meta.read_text() == before, "must NOT overwrite existing metadata/history byte-for-byte"


def test_creates_dir_if_missing(tmp_path):
    """The primitive mkdir(parents=True)s the dir — safe even if the caller hasn't yet."""
    pdir = tmp_path / "Projects" / "Deep" / "NestedProj"
    assert not pdir.exists()
    wrote = ensure_project_metadata(pdir, "NestedProj")
    assert wrote is True
    assert (pdir / ".project.json").exists()
