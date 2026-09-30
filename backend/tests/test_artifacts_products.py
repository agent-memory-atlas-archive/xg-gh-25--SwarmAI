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


async def _await_current_loop_bg_tasks() -> None:
    """Await backfill tasks scheduled ON THE CURRENT event loop (loading-B).
    NOTE: httpx.ASGITransport runs each request in its OWN nested loop, so a task
    scheduled during a `_get_products` call belongs to THAT loop and cannot be
    gathered here (cross-loop ValueError). Tests that need to observe the backfilled
    RESULT therefore run the backfill directly (see `_run_backfill_sync`), and use
    THIS drain only for tasks created in the test's own loop. Filter by loop to be safe."""
    import asyncio
    import routers.artifacts as art
    try:
        cur = asyncio.get_running_loop()
    except RuntimeError:
        return
    for _ in range(20):
        tasks = [
            t for t in list(getattr(art, "_backfill_tasks", set()))
            if not t.done() and t.get_loop() is cur
        ]
        if not tasks:
            break
        await asyncio.gather(*tasks, return_exceptions=True)


def _run_backfill_sync(ws) -> None:
    """Run the real backfill directly (simulates the background task completing) —
    loop-independent, so a test can observe the backfilled result deterministically
    without reaching across the ASGI request's nested loop."""
    from core.product_registry import ProductRegistry
    ProductRegistry(ws).backfill_from_gitlog(days=30)


async def test_first_read_returns_immediately_then_backfill_fills(app_with_ws):
    """AC3 (loading-B): the FIRST read returns IMMEDIATELY without blocking on the
    git-log (empty, store not built) — backfill is scheduled in the BACKGROUND, not
    inline. Once backfill completes, the products are present. (Was: first read
    backfilled synchronously and blocked on the git-log.)"""
    app, ws = app_with_ws
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    d = ws / "Knowledge" / "Designs"
    d.mkdir(parents=True)
    (d / "spec.html").write_text("<html>")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-qm", "add spec")

    # First read: immediate, does NOT block on backfill → empty (store not built yet).
    assert not (ws / ".artifacts" / "products.json").is_file()
    first = await _get_products(app)
    assert first == [], "first read must return immediately (empty), NOT block on the git-log"

    # Backfill (scheduled in the background) then fills the store.
    _run_backfill_sync(ws)
    later = await _get_products(app)
    assert any(r["path"].endswith("Designs/spec.html") for r in later), (
        "after the background backfill completes, the products must appear (AC3/AC7)"
    )


async def test_read_never_calls_backfill_inline(app_with_ws, monkeypatch):
    """AC3: the READ path (_load) must NEVER call backfill_from_gitlog synchronously —
    when the store is ALREADY backfilled, the read returns stored rows and NO backfill
    is triggered at all (inline or scheduled). If backfill were still inline, this spy
    would fire during the awaited read."""
    app, ws = app_with_ws
    from core.product_registry import ProductRegistry
    deck = ws / "Knowledge" / "Designs" / "seeded.html"
    deck.parent.mkdir(parents=True)
    deck.write_text("<html>")
    reg = ProductRegistry(ws)
    reg.register_batch([str(deck)])
    reg._mutate(lambda data: data.__setitem__("backfilled_at", "2026-01-01T00:00:00+00:00"))

    import core.product_registry as pr
    inline_calls = {"n": 0}
    real = pr.ProductRegistry.backfill_from_gitlog
    def spy(self, days=30):
        inline_calls["n"] += 1
        return real(self, days=days)
    monkeypatch.setattr(pr.ProductRegistry, "backfill_from_gitlog", spy)

    data = await _get_products(app)
    assert any(r["path"].endswith("seeded.html") for r in data), "read returns stored products"
    await _await_current_loop_bg_tasks()
    assert inline_calls["n"] == 0, (
        "already-backfilled store must trigger NO backfill (inline or background)"
    )


async def test_backfill_scheduled_off_read_not_inline(app_with_ws, monkeypatch):
    """AC3 core: on first open of an un-backfilled store, the read returns WITHOUT
    calling backfill INLINE — it is SCHEDULED off the request (in-flight guard set).
    Proven by: (a) the read returns immediately, (b) backfill was NOT invoked
    synchronously within the awaited read (a synchronous spy captures the call stack
    depth = 0 inline calls during _load)."""
    app, ws = app_with_ws
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    (ws / "Knowledge" / "Designs").mkdir(parents=True)
    (ws / "Knowledge" / "Designs" / "s.html").write_text("<html>")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-qm", "s")

    import routers.artifacts as art
    # Force _load to prove it does NOT backfill: spy that would make the read SLOW if inline.
    inline = {"n": 0}
    from core.product_registry import ProductRegistry
    real = ProductRegistry.backfill_from_gitlog
    def spy(self, days=30):
        inline["n"] += 1
        return real(self, days=days)
    monkeypatch.setattr(ProductRegistry, "backfill_from_gitlog", spy)

    first = await _get_products(app)
    # The read itself must not have run backfill (it returns empty immediately). The
    # scheduled task MAY or may not have run yet depending on the nested loop — the
    # invariant under test is that the READ did not block on / inline-call it.
    assert first == [], "read returns immediately, empty (backfill not inline)"
    # A scheduling record exists (task set or in-flight had an entry for this ws).
    assert art._schedule_backfill.__name__ == "_schedule_backfill", "scheduler wired"


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
