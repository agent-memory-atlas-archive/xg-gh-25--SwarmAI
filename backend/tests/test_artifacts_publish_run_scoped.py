"""Tests for POST /artifacts/pipeline/publish run-scoping (finding #4, Run 1 tail-2).

WHAT IS TESTED
    The publish endpoint must NOT be a run-blind writer. Before the fix,
    PublishRequest had no run_id field and the handler called reg.publish()
    WITHOUT run_id → a bare top-level {type}-{date}.json file (the run-blind
    contamination source that fed the deleted date-fallback). The fix adds a
    run_id field, passes it through, and FAILS CLOSED (400) when it is absent —
    matching the CLI's `--stage publish without --run-id` protection.

METHODOLOGY
    Real ASGI (httpx.ASGITransport over the FastAPI app). `_get_registry` is
    monkeypatched to an ArtifactRegistry on a tmp workspace (NOT _get_workspace_path
    — the publish path resolves the registry via swarm_workspace_manager). The
    project dir is pre-created so publish does not 404.

KEY PROPERTIES
    - WITH run_id → artifact lands RUN-SCOPED (runs/<run_id>/<type>-<date>-<id>.json),
      manifest entry carries run_id. NOT a bare top-level file.
    - WITHOUT run_id → 400 fail-closed, nothing written.
    Mutation: revert the fail-closed (let run_id-absent fall through to
    reg.publish(run_id=None)) → the no-run_id test flips RED (bare write + 200).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport


@pytest.fixture()
def app_with_reg(tmp_path, monkeypatch):
    """FastAPI app with _get_registry pinned to a tmp-workspace registry."""
    from fastapi import FastAPI
    import routers.artifacts as art
    from core.artifact_registry import ArtifactRegistry

    # pre-create the project dir so publish does not 404
    proj = tmp_path / "Projects" / "TestProj"
    proj.mkdir(parents=True)
    for name in ("PRODUCT.md", "TECH.md", "IMPROVEMENT.md", "PROJECT.md"):
        (proj / name).write_text("# T\n")

    reg = ArtifactRegistry(tmp_path)
    monkeypatch.setattr(art, "_get_registry", lambda: reg)
    app = FastAPI()
    app.include_router(art.router)
    return app, tmp_path


async def _post_publish(app, body: dict) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/artifacts/pipeline/publish", json=body)


async def test_publish_with_run_id_lands_run_scoped(app_with_reg):
    """WITH run_id → artifact under runs/<run_id>/, manifest carries run_id, NOT bare."""
    app, ws = app_with_reg
    run_id = "run_scopetest1"
    resp = await _post_publish(app, {
        "project": "TestProj", "artifact_type": "evaluation",
        "data": {"recommendation": "GO"}, "producer": "test",
        "summary": "scoped", "run_id": run_id,
    })
    assert resp.status_code == 200, resp.text
    art_id = resp.json()["artifact_id"]

    artifacts_dir = ws / "Projects" / "TestProj" / ".artifacts"
    # run-scoped file exists under runs/<run_id>/
    run_files = list((artifacts_dir / "runs" / run_id).glob(f"evaluation-*-{art_id}.json"))
    assert run_files, f"artifact must land under runs/{run_id}/ (got: {list((artifacts_dir / 'runs' / run_id).glob('*')) if (artifacts_dir / 'runs' / run_id).exists() else 'no run dir'})"
    # NO bare top-level evaluation-<date>.json
    bare = list(artifacts_dir.glob("evaluation-*.json"))
    assert not bare, f"a run-scoped publish must NOT write a bare top-level file (got: {bare})"
    # manifest entry carries run_id
    manifest = json.loads((artifacts_dir / "manifest.json").read_text())
    entry = next((e for e in manifest.get("artifacts", []) if e.get("id") == art_id), None)
    assert entry and entry.get("run_id") == run_id, f"manifest entry must carry run_id={run_id}: {entry}"


async def test_publish_without_run_id_422_openapi_honest(app_with_reg):
    """AC6 (run_44a06138, Kiro #13): run_id is a REQUIRED str on the model, so an
    ABSENT run_id is a Pydantic 422 (the schema predicts it) — NOT a runtime 400
    the OpenAPI contract hid. Either way nothing is written."""
    app, ws = app_with_reg
    resp = await _post_publish(app, {
        "project": "TestProj", "artifact_type": "evaluation",
        "data": {"recommendation": "GO"}, "producer": "test",
        "summary": "no-run-id",
    })
    assert resp.status_code == 422, (
        f"absent run_id must be a schema-level 422 (OpenAPI-honest), got {resp.status_code}: {resp.text}")
    # nothing written (no bare top-level file)
    artifacts_dir = ws / "Projects" / "TestProj" / ".artifacts"
    bare = list(artifacts_dir.glob("evaluation-*.json")) if artifacts_dir.exists() else []
    assert not bare, f"a rejected publish must write nothing (got: {bare})"


async def test_publish_traversal_run_id_fails_closed(app_with_reg):
    """A ..-bearing run_id must be rejected (400 from the registry trust boundary)
    and write NOTHING into any sibling project."""
    app, ws = app_with_reg
    (ws / "Projects" / "Victim").mkdir(parents=True, exist_ok=True)
    resp = await _post_publish(app, {
        "project": "TestProj", "artifact_type": "evaluation",
        "data": {"recommendation": "GO"}, "producer": "attacker",
        "summary": "traversal", "run_id": "../../../Victim/.artifacts/runs/run_x",
    })
    assert resp.status_code == 400, f"traversal run_id must fail closed (got {resp.status_code}: {resp.text})"
    victim = list((ws / "Projects" / "Victim").rglob("*.json"))
    assert not victim, f"traversal escaped into sibling project: {victim}"


async def test_publish_traversal_project_fails_closed(app_with_reg):
    """A ..-bearing project (Kiro #1b) must be rejected and escape nothing outside Projects/."""
    app, ws = app_with_reg
    (ws / "Knowledge").mkdir(parents=True, exist_ok=True)
    resp = await _post_publish(app, {
        "project": "../Knowledge", "artifact_type": "evaluation",
        "data": {"recommendation": "GO"}, "producer": "attacker",
        "summary": "project traversal", "run_id": "run_legit",
    })
    assert resp.status_code in (400, 404), f"project traversal must fail (got {resp.status_code}: {resp.text})"
    escaped = list((ws / "Knowledge").rglob("*.json"))
    assert not escaped, f"project traversal escaped to sibling dir: {escaped}"


async def test_publish_whitespace_run_id_fails_closed(app_with_reg):
    """A whitespace-only run_id is not a real run — must also fail closed (not create
    a run dir literally named '   '). Guards the `.strip()` in the fail-closed check."""
    app, ws = app_with_reg
    resp = await _post_publish(app, {
        "project": "TestProj", "artifact_type": "evaluation",
        "data": {"recommendation": "GO"}, "producer": "test",
        "summary": "ws", "run_id": "   ",
    })
    assert resp.status_code == 400, f"whitespace run_id must fail closed (got {resp.status_code})"
    artifacts_dir = ws / "Projects" / "TestProj" / ".artifacts"
    # no run dir named with whitespace, no bare file
    runs_dir = artifacts_dir / "runs"
    ws_dirs = [p for p in runs_dir.iterdir() if not p.name.strip()] if runs_dir.exists() else []
    assert not ws_dirs, f"must not create a whitespace-named run dir (got: {ws_dirs})"
