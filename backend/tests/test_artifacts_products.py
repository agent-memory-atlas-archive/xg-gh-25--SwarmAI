"""Tests for ``GET /artifacts/products`` (Artifacts B′ Run 2, AC1).

WHAT IS TESTED
    The read projection over the workspace-level product registry
    (``.artifacts/products.json``). Response = a list of
    ``{path, role, kind, gitignored, firstProduced, lastTouched}`` (camelCase),
    the ROLE-typed source the Artifacts overlay projects from — replacing the
    git-log ``/artifacts/recent`` view that could not see gitignored decks.

METHODOLOGY
    Real ASGI (httpx.ASGITransport over the FastAPI app). ``_get_workspace_path``
    is monkeypatched to a tmp workspace so the endpoint reads a controlled store.

KEY PROPERTIES / INVARIANTS (AC1)
    - a populated store → its rows, role-typed, camelCase
    - a gitignored deck (role=Deliverables, gitignored=true) IS returned
      (the blind-spot fix — /artifacts/recent structurally could not)
    - an empty / missing store → [] (never 500)
    - first read of an empty store runs backfill_from_gitlog (AC7) so day-one
      is not empty when the git tree has recent products
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, timeout=10)


async def _get_products(app) -> list[dict]:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/artifacts/products", params={"workspace_id": "default"})
        assert resp.status_code == 200, resp.text
        return resp.json()


@pytest.fixture()
def app_with_ws(tmp_path, monkeypatch):
    """FastAPI app with _get_workspace_path pinned to a tmp workspace."""
    from fastapi import FastAPI
    import routers.artifacts as art

    async def _fake_ws() -> str:
        return str(tmp_path)

    monkeypatch.setattr(art, "_get_workspace_path", _fake_ws)
    app = FastAPI()
    app.include_router(art.router)
    return app, tmp_path


async def test_empty_store_returns_empty_list(app_with_ws):
    """A missing/empty store → [] not 500 (no git tree to backfill either)."""
    app, ws = app_with_ws
    # Not a git repo → backfill is a no-op; store is empty.
    data = await _get_products(app)
    assert data == []


async def test_populated_store_projects_rows(app_with_ws):
    """A populated products.json → its rows, camelCase, role-typed."""
    app, ws = app_with_ws
    from core.product_registry import ProductRegistry

    deck = ws / "Projects" / "AIDLC" / "assets" / "deck.html"
    deck.parent.mkdir(parents=True)
    deck.write_text("<html>")
    report = ws / "Projects" / "SwarmAI" / ".artifacts" / "runs" / "run_x" / "REPORT.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report")
    ProductRegistry(ws).register_batch([str(deck), str(report)])

    data = await _get_products(app)
    by_role = {r["role"]: r for r in data}
    assert "Deliverables" in by_role, "the deck must project as Deliverables"
    assert "Pipeline" in by_role, "the REPORT.md must project as Pipeline"
    # camelCase contract (frontend expects it)
    row = by_role["Deliverables"]
    assert "firstProduced" in row and "lastTouched" in row
    assert "gitignored" in row and "kind" in row and "path" in row


async def test_gitignored_deck_is_returned(app_with_ws):
    """The blind-spot fix: a gitignored deck (role=Deliverables) IS returned —
    /artifacts/recent structurally could not surface it."""
    app, ws = app_with_ws
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    (ws / ".gitignore").write_text("Projects/*\n!Projects/SwarmAI/\n")
    from core.product_registry import ProductRegistry

    deck = ws / "Projects" / "AIDLC" / "assets" / "deck.html"
    deck.parent.mkdir(parents=True)
    deck.write_text("<html>")
    ProductRegistry(ws).register_batch([str(deck)])

    data = await _get_products(app)
    decks = [r for r in data if r["path"].endswith("assets/deck.html")]
    assert len(decks) == 1, "the gitignored deck must be returned by the products endpoint"
    assert decks[0]["role"] == "Deliverables"
    assert decks[0]["gitignored"] is True


async def test_first_read_backfills_from_gitlog(app_with_ws):
    """AC7: an empty store on first read backfills from recent git-log so the
    overlay is not empty day-one when the tree has recent tracked products."""
    app, ws = app_with_ws
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    d = ws / "Knowledge" / "Designs"
    d.mkdir(parents=True)
    (d / "spec.html").write_text("<html>")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-qm", "add spec")

    # Store does NOT exist yet → the endpoint must backfill on first read.
    assert not (ws / ".artifacts" / "products.json").is_file()
    data = await _get_products(app)
    assert any(r["path"].endswith("Designs/spec.html") for r in data), (
        "first read of an empty store must backfill recent git-log products (AC7)"
    )


async def test_product_less_workspace_backfills_at_most_once(app_with_ws, monkeypatch):
    """Gate-2 meta-review MED: a workspace whose recent git-log has NO products must
    NOT re-run the 30s git-log on every overlay open. After the first read sets the
    backfilled marker, subsequent reads skip backfill even though the store is empty."""
    app, ws = app_with_ws
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    # A tracked SOURCE file — classified as source/process → NOT a product → store empty.
    code = ws / "backend" / "core" / "x.py"
    code.parent.mkdir(parents=True)
    code.write_text("x = 1\n")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-qm", "add code")

    import core.product_registry as pr

    calls = {"backfill": 0}
    real_backfill = pr.ProductRegistry.backfill_from_gitlog

    def counting_backfill(self, days=30):
        calls["backfill"] += 1
        return real_backfill(self, days=days)

    monkeypatch.setattr(pr.ProductRegistry, "backfill_from_gitlog", counting_backfill)

    first = await _get_products(app)
    second = await _get_products(app)
    third = await _get_products(app)
    assert first == [] and second == [] and third == [], "no products in a code-only tree"
    assert calls["backfill"] == 1, (
        f"backfill must run at most once (product-less workspace), ran {calls['backfill']}× — "
        "re-running the git-log on every open is the RP53-adjacent cost bug"
    )


# ── Layer 4: Cross-Boundary E2E (cross_boundary=true, kind=frontend↔backend contract) ──
# The seam: backend ProductResponse fields ↔ frontend `Product` interface (radar.ts). A
# divergence (backend renames/drops a field the overlay reads) would silently break the
# gallery. This binds the frontend field set to the backend SSOT so a divergence is RED —
# driving the REAL endpoint response shape (not a mock of ProductResponse).


class TestLayer4CrossBoundaryContract:
    async def test_response_field_set_matches_frontend_product_type(self, app_with_ws):
        """The backend ProductResponse field set MUST equal the frontend `Product`
        interface's fields (radar.ts). Drives the REAL endpoint (not a mocked shape):
        register a product, GET it, assert the emitted keys are EXACTLY the camelCase
        set the frontend consumes. Divergence (a renamed/added/dropped backend field)
        → RED, before it reaches the overlay."""
        app, ws = app_with_ws
        from core.product_registry import ProductRegistry

        deck = ws / "Knowledge" / "Designs" / "deck.html"
        deck.parent.mkdir(parents=True)
        deck.write_text("<html>")
        ProductRegistry(ws).register_batch([str(deck)])

        data = await _get_products(app)
        assert data, "the registered product must be returned"
        row = data[0]

        # The frontend `Product` interface (desktop/src/services/radar.ts) declares
        # EXACTLY these fields. This is the SSOT the frontend renders — the backend
        # ProductResponse must emit the same set (camelCase). Parsed from source so the
        # test tracks the real frontend type, not a hand-copy that could drift.
        radar_ts = (
            Path(__file__).resolve().parents[2]
            / "desktop" / "src" / "services" / "radar.ts"
        )
        text = radar_ts.read_text(encoding="utf-8")
        # Extract the `export interface Product { ... }` block field names.
        import re

        m = re.search(r"export interface Product \{(.*?)\}", text, re.DOTALL)
        assert m, "could not find `export interface Product` in radar.ts"
        frontend_fields = set(re.findall(r"^\s*(\w+)\s*[?:]", m.group(1), re.MULTILINE))

        backend_fields = set(row.keys())
        assert backend_fields == frontend_fields, (
            f"backend/frontend Product contract DIVERGED: backend emits {backend_fields}, "
            f"frontend `Product` declares {frontend_fields}. Update radar.ts OR ProductResponse."
        )
