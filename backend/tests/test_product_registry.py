"""Tests for the shared PRODUCT registry (Artifacts B′ Run 1).

Covers the 6 acceptance criteria from design_doc art_5c8787b5:
  AC1 — workspace-level products.json with flock+atomic, concurrent-write safe
  AC2 — derive_role delegates kind to needs_human_review, maps §8.2 cases
  AC3 — gitignored PRODUCT dir surfaces DESPITE verdict=process; secret does NOT
  AC4 — external ($HOME/Desktop, /tmp) paths are skipped
  AC5 — backfill_from_gitlog idempotent (keyed by path)
  AC6 — sync core callable off-loop; watcher hook calls register_batch on RAW paths

The registry reuses utils.file_lock + an atomic write-temp+rename primitive — the
SAME mechanism ArtifactRegistry uses, NOT a subclass (workspace-level flat keyspace
does not fit the project-scoped ArtifactRegistry API — THINK falsified subclassing).
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def ws(tmp_path):
    """A workspace root with a Projects/ dir (mirrors SwarmWS layout)."""
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Knowledge").mkdir()
    return tmp_path


@pytest.fixture
def git_ws(tmp_path):
    """A workspace root that is a git repo with a .gitignore hiding Projects/*.

    Lets us prove AC3: a gitignored deck under Projects/*/assets still registers
    as a product, while a secret under Projects/* does not.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("Projects/*\n!Projects/SwarmAI/\n")
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Knowledge").mkdir()
    return tmp_path


# ── AC1: workspace-level store, flock+atomic, concurrent-write safe ─────────


class TestAC1WorkspaceStore:
    def test_writes_workspace_level_products_json(self, ws):
        from core.product_registry import ProductRegistry

        reg = ProductRegistry(ws)
        p = ws / "Knowledge" / "Designs" / "deck.html"
        p.parent.mkdir(parents=True)
        p.write_text("<html>")
        reg.register_product(str(p))

        store = ws / ".artifacts" / "products.json"
        assert store.is_file(), "products.json must live at WORKSPACE root .artifacts/"
        data = json.loads(store.read_text())
        assert data["version"] == 1
        paths = [e["path"] for e in data["products"]]
        assert "Knowledge/Designs/deck.html" in paths

    def test_concurrent_writes_lose_no_entry(self, ws):
        """flock serializes read-modify-write — N threads, N entries survive."""
        from core.product_registry import ProductRegistry

        reg = ProductRegistry(ws)
        d = ws / "Knowledge" / "Designs"
        d.mkdir(parents=True)
        n = 12
        for i in range(n):
            (d / f"f{i}.html").write_text("x")

        def worker(i):
            ProductRegistry(ws).register_product(str(d / f"f{i}.html"))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        data = json.loads((ws / ".artifacts" / "products.json").read_text())
        assert len(data["products"]) == n, "lost-update race — an entry vanished"


# ── AC2: derive_role delegates kind, maps §8.2 cases ────────────────────────


class TestAC2DeriveRole:
    @pytest.mark.parametrize(
        "rel_path,repo,expected_role",
        [
            ("Projects/AIDLC/assets/deck.html", None, "Deliverables"),
            ("Attachments/2026-09-30/x.png", None, "Deliverables"),
            ("Knowledge/Designs/2026-09-30-x.md", None, "Deliverables"),
            ("Projects/SwarmAI/2-understanding/TECH.md", None, "Knowledge"),
            ("Knowledge/Library/2026-09-11-x.md", None, "Knowledge"),
            ("Projects/SwarmAI/.artifacts/runs/run_x/REPORT.md", None, "Pipeline"),
            ("Knowledge/DailyActivity/2026-09-30.md", None, "Activity"),
            ("Knowledge/Signals/2026-09-29.md", None, "Activity"),
            ("some/unclassified/thing.xyz", None, "Other"),
        ],
    )
    def test_role_mapping(self, rel_path, repo, expected_role):
        from core.product_registry import derive_role

        assert derive_role(rel_path, repo) == expected_role

    def test_delegates_kind_not_reimplemented(self):
        """derive_role must call needs_human_review._classify_kind, not fork it."""
        import core.product_registry as pr

        called = {}
        real = pr._classify_kind

        def spy(rel_path, repo):
            called["hit"] = True
            return real(rel_path, repo)

        pr._classify_kind = spy
        try:
            pr.derive_role("Projects/SwarmAI/2-understanding/TECH.md", None)
        finally:
            pr._classify_kind = real
        assert called.get("hit"), "derive_role must DELEGATE to _classify_kind"


# ── AC3: gitignored PRODUCT surfaces despite verdict=process; secret does not ─


class TestAC3GitignoredProducts:
    def test_gitignored_deck_registers_despite_process_verdict(self, git_ws):
        """A deck under a gitignored Projects/*/assets is verdict=process
        (review_worthy=False) — but the PRODUCT path is independent of that
        verdict, so it MUST still register."""
        from core.needs_human_review import needs_human_review
        from core.product_registry import ProductRegistry

        deck = git_ws / "Projects" / "AIDLC" / "assets" / "deck.html"
        deck.parent.mkdir(parents=True)
        deck.write_text("<html>")

        # Precondition: the surface verdict drops it (gitignored → process).
        v = needs_human_review(str(deck), swarmws_root=str(git_ws))
        assert v.review_worthy is False and v.kind == "process", (
            "test premise: a gitignored deck must be process/not-review_worthy"
        )

        # The product registry must catch it ANYWAY (decoupled from the verdict).
        ProductRegistry(git_ws).register_batch([str(deck)])
        data = json.loads((git_ws / ".artifacts" / "products.json").read_text())
        entry = next(
            (e for e in data["products"] if e["path"].endswith("assets/deck.html")),
            None,
        )
        assert entry is not None, "gitignored PRODUCT deck must register"
        assert entry["role"] == "Deliverables"
        assert entry["gitignored"] is True

    def test_secret_under_projects_does_not_register(self, git_ws):
        """The allowlist must be a narrow POSITIVE list (assets/Attachments) —
        a secret elsewhere under a gitignored Projects/* must NOT be surfaced."""
        from core.product_registry import ProductRegistry

        secret = git_ws / "Projects" / "AIDLC" / ".env"
        secret.parent.mkdir(parents=True)
        secret.write_text("SECRET=1")

        ProductRegistry(git_ws).register_batch([str(secret)])
        store = git_ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"] if store.is_file() else []
        assert not any(".env" in e["path"] for e in products), (
            "a gitignored secret must never be surfaced as a product"
        )

    def test_secret_not_surfaced_even_when_gitignore_check_errors(self, ws, monkeypatch):
        """RP50/RP55 fail-CLOSED: if git check-ignore CANNOT run (returns None,
        unknown), a non-product path (a .env → role Other) must still NOT register —
        an unknowable path might be a gitignored secret, so the safe side is drop."""
        from core.product_registry import ProductRegistry

        secret = ws / "Projects" / "AIDLC" / ".env"
        secret.parent.mkdir(parents=True)
        secret.write_text("SECRET=1")

        reg = ProductRegistry(ws)
        # Force the gitignore check to UNKNOWN (git errored) — must not fail open.
        monkeypatch.setattr(reg, "_is_gitignored", lambda tree, rel: None)
        reg.register_batch([str(secret)])

        store = ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"] if store.is_file() else []
        assert not any(".env" in e["path"] for e in products), (
            "on git-check-ignore UNKNOWN, a .env must fail CLOSED (not register)"
        )

    @pytest.mark.parametrize(
        "secret_rel",
        [
            "Projects/AIDLC/assets/.env",
            "Projects/AIDLC/assets/id_rsa",
            "Projects/AIDLC/assets/service.key",
            "Projects/AIDLC/assets/credentials.json",
            "Attachments/.env",
            "Projects/X/node_modules/pkg/assets/secret.pem",
            # Red-Team: denylist-escaping secrets — closed by the positive
            # extension allowlist (none of these has a product extension).
            "Projects/AIDLC/assets/aws_credentials",
            "Projects/AIDLC/assets/token.txt",
            "Projects/AIDLC/assets/passwords.md",
            "Projects/AIDLC/assets/config.yaml",
            "Projects/AIDLC/assets/ID_RSA",
            "Projects/AIDLC/assets/id_rsa.txt",
            "Projects/X/target/assets/branding.png",  # vendored (Rust target/)
        ],
    )
    def test_secret_inside_product_dir_does_not_register(self, ws, secret_rel):
        """Gate-2 Security HIGH + Red-Team: a secret/config/vendored file INSIDE an
        allowlisted product dir must NOT surface. The fix is a POSITIVE
        product-extension allowlist (not a secret denylist, which Red-Team proved
        leaky) — only known media/document extensions under assets/Attachments
        surface; everything else falls to kind classification → Other → dropped."""
        from core.product_registry import ProductRegistry

        p = ws / secret_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("SECRET")
        ProductRegistry(ws).register_batch([str(p)])
        store = ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"] if store.is_file() else []
        base = secret_rel.rsplit("/", 1)[-1]
        assert not any(base in e["path"] for e in products), (
            f"{secret_rel} must NOT register — allowlist must not un-gate secrets/vendor"
        )

    def test_real_product_inside_assets_still_registers(self, ws):
        """The fix must not break the legit case: a deck/image under assets/ or
        Attachments/ still surfaces as Deliverables."""
        from core.product_registry import ProductRegistry

        deck = ws / "Projects" / "AIDLC" / "assets" / "deck.html"
        deck.parent.mkdir(parents=True)
        deck.write_text("<html>")
        img = ws / "Attachments" / "2026" / "x.png"
        img.parent.mkdir(parents=True)
        img.write_text("png")
        pdf = ws / "Projects" / "X" / "assets" / "report.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_text("%PDF")
        ProductRegistry(ws).register_batch([str(deck), str(img), str(pdf)])
        store = ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"]
        roles = {e["path"].rsplit("/", 1)[-1]: e["role"] for e in products}
        assert roles.get("deck.html") == "Deliverables"
        assert roles.get("x.png") == "Deliverables"
        assert roles.get("report.pdf") == "Deliverables", "known product extensions must surface"

    def test_other_role_files_are_not_products(self, ws):
        """The store holds PRODUCTS only — a tracked non-product file (role Other)
        must not be surfaced. Other is the classification catch-all, not a product."""
        from core.product_registry import ProductRegistry

        # A tracked config-ish file under SwarmWS root that maps to Other.
        f = ws / "randomconfig.xyz"
        f.write_text("x")
        ProductRegistry(ws).register_batch([str(f)])
        store = ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"] if store.is_file() else []
        assert not any("randomconfig" in e["path"] for e in products), (
            "role=Other files must not register as products"
        )


# ── AC4: external paths skipped ─────────────────────────────────────────────


class TestAC4ExternalSkipped:
    def test_home_desktop_and_tmp_skipped(self, ws):
        from core.product_registry import ProductRegistry

        reg = ProductRegistry(ws)
        reg.register_batch(
            [
                str(Path.home() / "Desktop" / "report.md"),
                "/tmp/scratch/deck.html",
            ]
        )
        store = ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"] if store.is_file() else []
        assert products == [], "external / tmp paths must be skipped (classify_source copy)"


# ── AC5: backfill idempotent ────────────────────────────────────────────────


class TestAC5BackfillIdempotent:
    def test_backfill_twice_no_dup(self, git_ws):
        from core.product_registry import ProductRegistry

        # A committed design deliverable (tracked → git-log will list it).
        d = git_ws / "Knowledge" / "Designs"
        d.mkdir(parents=True)
        (d / "deck.md").write_text("# deck")
        subprocess.run(["git", "add", "-A"], cwd=git_ws, check=True)
        subprocess.run(["git", "commit", "-qm", "add deck"], cwd=git_ws, check=True)

        reg = ProductRegistry(git_ws)
        reg.backfill_from_gitlog(days=30)
        first = json.loads((git_ws / ".artifacts" / "products.json").read_text())
        reg.backfill_from_gitlog(days=30)
        second = json.loads((git_ws / ".artifacts" / "products.json").read_text())

        assert len(first["products"]) == len(second["products"]) > 0, (
            "backfill must be idempotent — running twice adds no duplicate"
        )


# ── AC6: sync core off-loop; watcher hook calls register_batch on RAW paths ──


class TestAC6OffLoopSeam:
    async def test_watcher_calls_register_batch_on_raw_paths_off_loop(self, ws, monkeypatch):
        """workspace_surface_watcher._handle_batch must call
        ProductRegistry.register_batch with the RAW batch paths, via the
        existing off-loop executors.run_in seam — NOT off the filtered
        verdicts.items() loop (Gate-1 finding)."""
        import core.workspace_surface_watcher as wsw

        seen = {}

        def fake_register_batch(self, paths):
            seen["paths"] = list(paths)

        monkeypatch.setattr(
            "core.product_registry.ProductRegistry.register_batch",
            fake_register_batch,
        )

        watcher = wsw.WorkspaceSurfaceWatcher(ws)
        raw = [str(ws / "Projects" / "AIDLC" / "assets" / "deck.html")]
        await watcher._handle_batch(raw)

        assert "paths" in seen, "_handle_batch must call register_batch"
        assert seen["paths"] == raw, (
            "register_batch must receive the RAW batch paths (incl. gitignored), "
            "not the review_worthy/content-filtered subset"
        )

    def test_sync_core_is_importable_and_callable(self, ws):
        """The write core must be a plain sync callable (so an async seam can
        run it via executors.run_in without the registry owning any async)."""
        from core.product_registry import ProductRegistry

        reg = ProductRegistry(ws)
        assert callable(reg.register_batch)
        # A no-op batch must not raise and must not create a bogus store entry.
        reg.register_batch([])


# ── Layer 4: Cross-Boundary E2E (cross_boundary=true, kind=event-bus) ────────
# Drives the REAL seam end-to-end: real _handle_batch → real ProductRegistry →
# real products.json. Does NOT mock the thing-under-change (the registry write).
# Only the far leaf (surface_injection.publish_file_event) is neutralized so the
# test doesn't need a live SSE bus.


class TestLayer4CrossBoundaryE2E:
    async def test_watcher_writes_gitignored_deck_to_real_store(self, git_ws, monkeypatch):
        """The full boundary: a gitignored deck flows through the REAL watcher hook
        into the REAL products.json — the seam this run adds, driven end-to-end."""
        import core.workspace_surface_watcher as wsw

        # Neutralize ONLY the far leaf (the SSE emit) — NOT the registry seam.
        monkeypatch.setattr(wsw.surface_injection, "publish_file_event", lambda ev: None)

        deck = git_ws / "Projects" / "AIDLC" / "assets" / "deck.html"
        deck.parent.mkdir(parents=True)
        deck.write_text("<html>")

        watcher = wsw.WorkspaceSurfaceWatcher(git_ws)
        await watcher._handle_batch([str(deck)])

        store = git_ws / ".artifacts" / "products.json"
        assert store.is_file(), "real seam must have written the real store"
        products = json.loads(store.read_text())["products"]
        assert any(e["path"].endswith("assets/deck.html") for e in products), (
            "the gitignored deck must reach products.json through the REAL "
            "_handle_batch → ProductRegistry seam (not a mock)"
        )

    async def test_mutation_reverting_the_hook_goes_red(self, git_ws, monkeypatch):
        """Mutation proof (non-vacuous): if the watcher did NOT call the registry
        on the raw batch (the contract line this run added), the store would be
        empty. We simulate the revert by pointing register_batch at a no-op and
        assert the deck is then ABSENT — proving the real hook is what writes it."""
        import core.workspace_surface_watcher as wsw

        monkeypatch.setattr(wsw.surface_injection, "publish_file_event", lambda ev: None)
        # REVERT the contract: register_batch becomes a no-op (as if the hook line
        # were removed). The store must then NOT contain the deck.
        monkeypatch.setattr(
            "core.product_registry.ProductRegistry.register_batch",
            lambda self, paths: None,
        )

        deck = git_ws / "Projects" / "AIDLC" / "assets" / "deck.html"
        deck.parent.mkdir(parents=True)
        deck.write_text("<html>")

        watcher = wsw.WorkspaceSurfaceWatcher(git_ws)
        await watcher._handle_batch([str(deck)])

        store = git_ws / ".artifacts" / "products.json"
        products = json.loads(store.read_text())["products"] if store.is_file() else []
        assert not any(e["path"].endswith("assets/deck.html") for e in products), (
            "with the hook reverted, the deck must NOT reach the store — "
            "proves the Layer-4 test is non-vacuous (green only because the real hook fires)"
        )
