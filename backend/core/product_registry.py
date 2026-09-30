"""Shared PRODUCT registry — the workspace-level source both the Artifacts overlay
and the Canvas rail will project from (Artifacts B′ Run 1; design_doc art_5c8787b5).

WHAT THIS OWNS
    A durable, WORKSPACE-LEVEL store of user-facing PRODUCTS (decks, reports,
    images, design docs) at ``<SwarmWS>/.artifacts/products.json`` — distinct from
    the PER-PROJECT pipeline-stage artifacts ``artifact_registry.py`` holds. Both
    the Artifacts overlay (today: git-log projection) and the Canvas rail (today:
    per-tab sessionStorage) will, in Run 2, read from this ONE store instead of
    their two lossy derived views.

WHY A NEW CLASS, NOT A SUBCLASS (THINK-stage decision, Gate-1 confirmed)
    ``ArtifactRegistry`` threads a ``project`` arg through every method — its
    keyspace is PER-PROJECT (``Projects/<p>/.artifacts/``). A product can land
    ANYWHERE (``Knowledge/``, any ``Projects/*``, or be gitignored), so the store
    must be FLAT + workspace-level. Subclassing would pass a sentinel project into
    every base method and pollute the base semantics. Instead this reuses the
    PRIMITIVES ``ArtifactRegistry`` is built on — ``utils.file_lock`` (flock) + an
    atomic write-temp+rename — never the class.

THE GATE-1 FIX (the load-bearing design point)
    ``register_batch`` classifies RAW paths INDEPENDENTLY of the surface verdict.
    A gitignored deck (``Projects/AIDLC/assets/deck.html``) is
    ``needs_human_review`` → ``review_worthy=False, kind=process`` (the git-ignore
    Layer-1 drop), so it is filtered OUT of ``workspace_surface_watcher``'s
    ``verdicts.items()`` emit loop before ``abs_path`` is even assigned. If the
    product write rode that loop, gitignored decks — exactly the products that must
    surface — would NEVER register. So the write hook feeds ``register_batch`` the
    RAW batch paths, and this module does its OWN classification via a small
    positive PRODUCT_DIR_ALLOWLIST that short-circuits the gitignore drop, WITHOUT
    un-gating secrets/scratch (the allowlist is narrow: product dirs only).

DELEGATION (never a parallel walk — run_847ed9f9 / run_4de279ca)
    Location (owned vs external) → ``artifact_source.classify_source`` /
    ``needs_human_review._owning_tree``. Content-kind → ``needs_human_review.
    _classify_kind``. This module adds only the PRODUCT-role mapping + the store.

CONCURRENCY & DURABILITY
    Every ``products.json`` mutation runs under an exclusive flock on a
    ``.products.lock`` sidecar (read-modify-write serialized across processes), and
    the write is atomic (temp file + ``os.replace``). Same guarantees as
    ``ArtifactRegistry._mutate_manifest`` / ``_write_manifest``, same primitives.

    MECHANISM: flock is advisory + bound to the fd/inode (NOT the path — never
    unlink the lock to "release" it). Atomic replace is same-directory rename.
    VERIFY: mirrors artifact_registry.py:411 (flock) + :446 (mkstemp+replace),
    both production-verified; utils.file_lock carries the Windows byte-range branch.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.needs_human_review import _classify_kind, _owning_tree
from utils.file_lock import flock_exclusive, flock_unlock

logger = logging.getLogger(__name__)

# Roles (the overlay's grouping axis — §8 of the redesign design doc).
Role = str  # one of: Deliverables | Knowledge | Pipeline | Activity | Other

_STORE_VERSION = 1

# ── PRODUCT-dir allowlist (AC3) ──────────────────────────────────────────────
# A NARROW positive list: dirs whose gitignored contents are still user PRODUCTS
# and must surface despite the git-ignore drop. Matched on the SwarmWS-relative
# path. Deliberately small — widening this to un-gate secrets/scratch under
# Projects/* is the exact risk the PLAN security boundary escalated. A path is a
# product-dir member iff it lives UNDER one of these (never a bare prefix match on
# a sibling like "assets-backup").
_PRODUCT_DIR_SEGMENTS: tuple[str, ...] = (
    "assets",        # Projects/*/assets/** — decks, generated media
    "Attachments",   # Attachments/** — user-attached / produced images
)

# Dependency / vendor trees whose nested ``assets/`` dirs are NOT user products
# (a package ships its own ``assets/`` media/creds). If any of these segments
# appears in the path, the product-dir allowlist does NOT apply — 3rd-party
# content, not a SwarmAI product. (Gate-2 Claim 3 + Red-Team.)
_DEPENDENCY_SEGMENTS: frozenset[str] = frozenset({
    "node_modules", "vendor", ".venv", "venv", "site-packages", "dist", "build",
    "__pycache__", "target", ".next", ".nuxt", "bower_components", "Pods",
    ".gradle", ".tox", ".mypy_cache", "out", "coverage",
})

# POSITIVE product-extension allowlist — the Red-Team fix (a deny-based secret
# filter guarding an allowlist is inherently leaky: aws_credentials / token.txt /
# passwords.md / config.yaml all escaped a denylist). Under assets/Attachments,
# ONLY these known media/document product extensions surface as a Deliverable;
# everything else (no-extension, .txt, .yaml, .env, .key, a markdown secret dump)
# falls through to normal kind classification (→ usually Other → dropped). This
# closes the WHOLE secret-leak class positively instead of chasing filenames.
_PRODUCT_EXTENSIONS: frozenset[str] = frozenset({
    ".html", ".htm", ".pdf", ".pptx", ".ppt", ".key",  # NOTE: .key excluded below
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif",
    ".mp4", ".mov", ".webm", ".gif",
    ".docx", ".xlsx", ".csv",
})
# .key is an Apple-Keynote extension BUT also an SSH/TLS private-key extension —
# the collision is a secret risk, so it is EXCLUDED from products (a Keynote deck
# is exported to .pptx/.pdf for surfacing). Remove it from the set explicitly.
_PRODUCT_EXTENSIONS = _PRODUCT_EXTENSIONS - {".key"}


def _under_product_dir(rel_path: str) -> bool:
    """True iff rel_path is a real PRODUCT under an allowlisted dir.

    Three gates, ALL must hold: (1) a whitelisted product SEGMENT (``assets`` /
    ``Attachments``) appears in the path; (2) NO dependency/vendor segment appears
    (``node_modules/.../assets/...`` is 3rd-party — Gate-2 Claim 3); (3) the basename
    has a known PRODUCT EXTENSION (media/document — the Red-Team positive-allowlist
    fix). A secret/config/no-extension file under assets/ fails gate 3 → NOT a
    product-dir file → falls to normal kind classification → dropped as Other. This
    is case-insensitive on the extension. The allowlist surfaces media/decks, never
    secrets or vendored files, by CONSTRUCTION (positive list), not by chasing
    secret filenames (a denylist, which Red-Team proved leaky).
    """
    parts = [p for p in Path(rel_path).parts if p not in (".", "")]
    # Case-insensitive segment match (macOS/APFS is case-insensitive; Assets==assets).
    lower_parts = {p.lower() for p in parts}
    if {d.lower() for d in _DEPENDENCY_SEGMENTS}.intersection(lower_parts):
        return False
    if not {s.lower() for s in _PRODUCT_DIR_SEGMENTS}.intersection(lower_parts):
        return False
    ext = Path(rel_path).suffix.lower()
    return ext in _PRODUCT_EXTENSIONS


# ── role derivation (AC2) — kind (delegated) + path sub-map ──────────────────


def derive_role(rel_path: str, repo: Optional[str]) -> Role:
    """Map a SwarmWS-relative path to its PRODUCT role.

    Two axes (design §8): CONTENT-ROLE (kind, DELEGATED to needs_human_review) +
    a PATH sub-map. Extension is only a tiebreaker WITHIN a path. Every path lands
    in exactly one role; ``Other`` is the exhaustiveness catch-all (never dropped).

    ``repo`` is the owning bound-repo name (or None for SwarmWS content) — passed
    straight to ``_classify_kind`` so a DDD ``.md`` inside a bound worktree is
    classified as knowledge, not source (matches _classify_kind's own precedence).
    """
    parts = [p for p in Path(rel_path).parts if p not in (".", "")]

    # Pipeline: a run REPORT under .artifacts/runs/ — check BEFORE kind, because the
    # dot-segment (.artifacts) would make _classify_kind return "process".
    if ".artifacts" in parts and "runs" in parts and parts[-1] == "REPORT.md":
        return "Pipeline"

    # Activity: automated per-day logs.
    if "DailyActivity" in parts or "Signals" in parts or "DailyBriefs" in parts:
        return "Activity"

    # Deliverables: an explicit product dir (decks/attachments), OR a design/report
    # authoring dir. These are the things a user makes and reopens.
    if _under_product_dir(rel_path):
        return "Deliverables"
    if "Designs" in parts or "Reports" in parts:
        return "Deliverables"

    # Otherwise fall back to the delegated content-kind.
    kind = _classify_kind(rel_path, repo)
    if kind == "knowledge":
        return "Knowledge"
    if kind in ("content",):
        # Bare content with no product/activity path signal → treat as Knowledge-
        # adjacent only if it is a knowledge dir; else Other.
        if "Knowledge" in parts:
            return "Knowledge"
        return "Other"

    # source / source-final / process with no product-dir short-circuit → not a
    # user product surface → Other (the catch-all; never dropped).
    return "Other"


# ── the store ────────────────────────────────────────────────────────────────


@dataclass
class Product:
    """One registered product (a row projected by the overlay + Canvas rail)."""

    path: str            # SwarmWS-relative, forward-slashed
    role: Role
    kind: str            # the delegated needs_human_review kind
    gitignored: bool
    first_produced: str  # ISO 8601
    last_touched: str    # ISO 8601


class ProductRegistry:
    """Workspace-level product store. Reads are lock-free; every mutation is
    flock-serialized + atomically written."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    # ── paths ──────────────────────────────────────────────────────────────

    def _store_path(self) -> Path:
        return self.workspace_root / ".artifacts" / "products.json"

    def _lock_path(self) -> Path:
        return self.workspace_root / ".artifacts" / ".products.lock"

    # ── read ─────────────────────────────────────────────────────────────────

    def _read(self) -> dict:
        path = self._store_path()
        if not path.is_file():
            return {"version": _STORE_VERSION, "products": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("ProductRegistry: unreadable store %s: %s", path, exc)
            return {"version": _STORE_VERSION, "products": []}

    def list_products(self) -> list[Product]:
        return [Product(**e) for e in self._read().get("products", [])]

    # ── atomic write (temp + replace) ─────────────────────────────────────────

    def _atomic_write_json(self, data: dict) -> None:
        path = self._store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, default=str)
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=".products-"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, path)  # atomic same-dir rename
        except BaseException:
            try:
                Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _mutate(self, mutator) -> None:
        """flock-guarded read-modify-write (mirrors ArtifactRegistry._mutate_manifest).

        The default store is constructed INSIDE the lock so two processes seeing
        "no store" cannot each seed a fresh empty one and lose the other's write.
        """
        lock_path = self._lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")
        try:
            flock_exclusive(lock_fd)
            data = self._read()
            mutator(data)
            self._atomic_write_json(data)
        finally:
            flock_unlock(lock_fd)
            lock_fd.close()

    # ── classification (delegated) ────────────────────────────────────────────

    def _classify(self, abs_path: str) -> Optional[Product]:
        """Classify a RAW path into a Product, or None if it is not a product.

        INDEPENDENT of the surface verdict (the Gate-1 fix): a gitignored deck is
        review_worthy=False/process at needs_human_review, but its PRODUCT status is
        decided HERE. Returns None for external/disposable paths (AC4) and for
        non-product content under Projects/* that is not in the product allowlist
        (AC3 secret guard).
        """
        # Location: must be owned by SwarmWS or a bound tree. External → skip (AC4).
        try:
            abs_resolved = Path(os.path.expanduser(abs_path)).resolve()
        except (OSError, RuntimeError):
            return None
        owning = _owning_tree(abs_resolved, self.workspace_root)
        if owning is None:
            return None  # external / $HOME / tmp — not our product (AC4)
        tree_root, rel_path, repo = owning
        rel_path = rel_path.replace("\\", "/")

        role = derive_role(rel_path, repo)

        # GUARD 1 — the store holds PRODUCTS only. `Other` is the classification
        # model's exhaustiveness catch-all (§8) — a real file that is NOT a user
        # product (a tracked config, a random dotfile, a secret that slipped the
        # gitignore check). Never surface it. This is the PRIMARY secret guard: a
        # Projects/*/.env is kind=process → role Other → dropped here regardless of
        # what git check-ignore reported (RP50 fail-open defense that does not depend
        # on the gitignore subprocess succeeding).
        if role == "Other":
            return None

        ignored = self._is_gitignored(tree_root, rel_path)  # True | False | None(unknown)

        # GUARD 2 — a CONFIRMED-gitignored product surfaces ONLY under an explicit
        # PRODUCT dir (AC3: a deck under Projects/*/assets YES; a gitignored draft
        # elsewhere NO — git-ignore says "not committed", only the assets/Attachments
        # allowlist overrides that). RP55 tri-state: only a DEFINITE True gates here;
        # UNKNOWN (None, git errored / non-repo) does NOT drop a legit product-role
        # file — GUARD 1 already dropped the secret/Other class independent of git, so
        # a couldn't-check on a genuine product (Designs/Reports in a non-git tree or a
        # transient error) must not lose the deliverable.
        if ignored is True and not _under_product_dir(rel_path):
            return None
        gitignored = ignored is True

        kind = _classify_kind(rel_path, repo)
        now = datetime.now(timezone.utc).isoformat()
        return Product(
            path=rel_path,
            role=role,
            kind=kind,
            gitignored=gitignored,
            first_produced=now,
            last_touched=now,
        )

    def _is_gitignored(self, tree_root: Path, rel_path: str) -> Optional[bool]:
        """git check-ignore in the owning tree — TRI-STATE (RP55).

        Returns True (ignored), False (not-ignored), or None (git errored / couldn't
        check). The caller must NOT collapse None into False: a couldn't-check is
        absence-of-evidence, and for a path that might be a gitignored secret the safe
        side is fail-CLOSED (don't surface), not fail-open.
        """
        try:
            r = subprocess.run(
                ["git", "check-ignore", "-q", "--", rel_path],
                cwd=str(tree_root),
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None  # couldn't check → UNKNOWN (caller fails closed, RP55)
        if r.returncode == 0:
            return True   # ignored
        if r.returncode == 1:
            return False  # not ignored
        return None       # 128 etc → git error → UNKNOWN

    # ── write (public, sync — callable from an off-loop seam, AC6) ─────────────

    def register_product(self, abs_path: str) -> None:
        """Register ONE product path (no-op if not a product)."""
        self.register_batch([abs_path])

    def register_batch(self, paths: list[str]) -> None:
        """Register a batch of RAW paths. Classifies each independently of any
        surface verdict (the Gate-1 fix), then upserts under one flock.

        Keyed by relative path: re-registering an existing product refreshes its
        ``last_touched`` (and role/kind/gitignored, in case they changed) but never
        duplicates the row.
        """
        classified = [p for p in (self._classify(a) for a in paths) if p is not None]
        if not classified:
            return

        def _upsert(data: dict) -> None:
            products = data.setdefault("products", [])
            by_path = {e["path"]: e for e in products}
            for prod in classified:
                existing = by_path.get(prod.path)
                if existing is not None:
                    # Refresh mutable fields; PRESERVE first_produced.
                    existing["role"] = prod.role
                    existing["kind"] = prod.kind
                    existing["gitignored"] = prod.gitignored
                    existing["last_touched"] = prod.last_touched
                else:
                    row = asdict(prod)
                    products.append(row)
                    by_path[prod.path] = row

        self._mutate(_upsert)

    # ── backfill (AC5) ─────────────────────────────────────────────────────────

    def backfill_from_gitlog(self, days: int = 30) -> None:
        """Seed the store from the last ``days`` of git-log products (idempotent).

        Enumerates files touched in recent commits (the same source the Artifacts
        overlay uses today), classifies each, and upserts. Keyed by path → running
        twice adds no duplicate (AC5). Only tracked files appear in git-log, so a
        gitignored deck is NOT backfilled here — it registers live via the watcher
        hook (AC3). Fail-safe: any git error → no-op (never raises).
        """
        try:
            r = subprocess.run(
                [
                    "git", "log", f"--since={days}.days", "--diff-filter=ACMR",
                    "--name-only", "--pretty=format:",
                ],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ProductRegistry.backfill: git log failed: %s", exc)
            return
        if r.returncode != 0:
            return

        rels = {line.strip() for line in r.stdout.splitlines() if line.strip()}
        abs_paths = [
            str(self.workspace_root / rel)
            for rel in rels
            if (self.workspace_root / rel).is_file()
        ]
        if abs_paths:
            self.register_batch(abs_paths)
