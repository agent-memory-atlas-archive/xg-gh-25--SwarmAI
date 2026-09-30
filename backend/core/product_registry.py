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
from enum import Enum
from pathlib import Path
from typing import Optional

from core.needs_human_review import _classify_kind, _owning_tree
from utils.file_lock import flock_exclusive, flock_unlock

logger = logging.getLogger(__name__)


# Roles (the overlay's grouping axis — §8 of the redesign design doc). Run 2 AC3:
# a FROZEN enum, not a bare `Role = str` alias — the role set is closed, so an
# invalid role can never be stored or projected. str-subclass so existing JSON
# round-trips unchanged (asdict → the member's str value; a stored "Deliverables"
# rehydrates identically) and every `role == "Deliverables"` comparison still holds.
class Role(str, Enum):
    DELIVERABLES = "Deliverables"
    KNOWLEDGE = "Knowledge"
    PIPELINE = "Pipeline"
    ACTIVITY = "Activity"
    OTHER = "Other"


_STORE_VERSION = 1

# Run 2 AC4: bounded store. Registering past this cap evicts the OLDEST entries by
# last_touched inside the same flock-guarded _upsert (never a parallel writer, P8).
# Generous but finite — the overlay is a recent-products view, not an archive.
MAX_PRODUCTS = 2000

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
        return Role.PIPELINE

    # Activity: automated per-day logs.
    if "DailyActivity" in parts or "Signals" in parts or "DailyBriefs" in parts:
        return Role.ACTIVITY

    # Deliverables: an explicit product dir (decks/attachments), OR a design/report
    # authoring dir. These are the things a user makes and reopens.
    if _under_product_dir(rel_path):
        return Role.DELIVERABLES
    if "Designs" in parts or "Reports" in parts:
        return Role.DELIVERABLES

    # Otherwise fall back to the delegated content-kind.
    kind = _classify_kind(rel_path, repo)
    if kind == "knowledge":
        return Role.KNOWLEDGE
    if kind in ("content",):
        # Bare content with no product/activity path signal → treat as Knowledge-
        # adjacent only if it is a knowledge dir; else Other.
        if "Knowledge" in parts:
            return Role.KNOWLEDGE
        return Role.OTHER

    # source / source-final / process with no product-dir short-circuit → not a
    # user product surface → Other (the catch-all; never dropped).
    return Role.OTHER


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

    def has_backfilled(self) -> bool:
        """True once backfill_from_gitlog has run (regardless of whether it produced
        rows). The endpoint gates day-one backfill on THIS, not on an empty product
        list — otherwise a workspace whose recent git-log has no products (a code-only
        or brand-new tree) would re-run the 30s git-log on EVERY overlay open, occupying
        a shared thread-pool worker each time (Gate-2 meta-review MED / RP53-adjacent).
        The marker makes backfill fire at most once."""
        return bool(self._read().get("backfilled_at"))

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

    def _resolve(self, abs_path: str):
        """Resolve a raw path to (tree_root, rel_path, repo) or None if external.

        Split out of _classify so register_batch can group rel_paths by owning tree
        and run ONE check-ignore per tree (AC5) before classifying.
        """
        try:
            abs_resolved = Path(os.path.expanduser(abs_path)).resolve()
        except (OSError, RuntimeError):
            return None
        owning = _owning_tree(abs_resolved, self.workspace_root)
        if owning is None:
            return None  # external / $HOME / tmp — not our product (AC4)
        tree_root, rel_path, repo = owning
        return tree_root, rel_path.replace("\\", "/"), repo

    def _classify(
        self,
        tree_root: Path,
        rel_path: str,
        repo: Optional[str],
        ignored: Optional[bool],
    ) -> Optional[Product]:
        """Classify an already-resolved path into a Product, or None if not a product.

        INDEPENDENT of the surface verdict (the Gate-1 fix): a gitignored deck is
        review_worthy=False/process at needs_human_review, but its PRODUCT status is
        decided HERE. ``ignored`` is the PRE-COMPUTED tri-state git verdict (True /
        False / None-unknown) from the batched check-ignore — the per-path subprocess
        is gone (AC5). Returns None for non-product content (AC3 secret guard).
        """
        role = derive_role(rel_path, repo)

        # GUARD 1 — the store holds PRODUCTS only. `Other` is the classification
        # model's exhaustiveness catch-all (§8) — a real file that is NOT a user
        # product (a tracked config, a random dotfile, a secret that slipped the
        # gitignore check). Never surface it. This is the PRIMARY secret guard: a
        # Projects/*/.env is kind=process → role Other → dropped here regardless of
        # what git check-ignore reported (RP50 fail-open defense that does not depend
        # on the gitignore subprocess succeeding).
        if role == Role.OTHER:
            return None

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

    def _batch_gitignored(
        self, tree_root: Path, rel_paths: list[str]
    ) -> dict[str, Optional[bool]]:
        """ONE ``git check-ignore --stdin`` for ALL rel_paths in a tree (AC5).

        Replaces the per-path subprocess. Returns a {rel_path: True|False|None} map.
        --stdin --verbose prints one line PER IGNORED path (``<source>:<line>:<pat>\\t<path>``);
        a non-ignored path prints nothing. Exit 0 = at least one match, 1 = none, other
        = git error → EVERY path is UNKNOWN (None), so the caller fails CLOSED (RP55) —
        a couldn't-check never silently becomes not-ignored.
        """
        if not rel_paths:
            return {}
        try:
            r = subprocess.run(
                # -c core.quotepath=false: emit paths as raw UTF-8, NOT git's default
                # C-style octal-escaped + double-quote-wrapped form for non-ASCII names.
                # WITHOUT it, a CJK-named product (e.g. `assets/中概互联ETF.md`) comes back
                # as `"assets/\344\270\255..."` in --verbose output — that token never
                # matches the raw rel_path key, so `rp in ignored_set` is False → the file
                # is recorded gitignored=False (wrong) and a gitignored non-product-dir CJK
                # path could slip GUARD-2. The sibling /artifacts/recent uses the same flag
                # for exactly this reason (artifacts.py). (Gate-2 Correctness HIGH.)
                # Index-AWARE by default (do NOT pass the ignore-the-index flag): a
                # TRACKED file matching a broad ignore pattern (e.g. a committed
                # Designs/*.html under an `*.html` rule) correctly reports NOT-ignored,
                # because tracking overrides gitignore. Ignoring the index would falsely
                # mark that committed product gitignored=True → GUARD-2 would DROP a real
                # committed product. The gitignored DECK we DO want (AC3) is UNtracked, so
                # the default still reports it ignored. (Gate-2 Red-Team, verified.)
                ["git", "-c", "core.quotepath=false", "check-ignore",
                 "--stdin", "--verbose"],
                cwd=str(tree_root),
                input="\n".join(rel_paths) + "\n",
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return {rp: None for rp in rel_paths}  # git unavailable → all UNKNOWN
        # returncode 0 (some ignored) / 1 (none ignored) are both valid, parseable
        # results. Anything else (128 not-a-repo, etc.) → all UNKNOWN, fail closed.
        if r.returncode not in (0, 1):
            return {rp: None for rp in rel_paths}
        ignored_set: set[str] = set()
        for line in r.stdout.splitlines():
            # --verbose format: "<source>:<line>:<pattern>\t<path>". The path is
            # after the LAST tab; git delimits with the tab, so do NOT .strip() the
            # tab-present branch (a filename with a legit trailing space would be
            # corrupted and miss the key match). Only the no-tab fallback strips
            # the trailing newline splitlines already removed. (Gate-2 F2.)
            if "\t" in line:
                path = line.rsplit("\t", 1)[-1]
            else:
                path = line.strip()
            if path:
                ignored_set.add(path)
        return {rp: (rp in ignored_set) for rp in rel_paths}

    # ── write (public, sync — callable from an off-loop seam, AC6) ─────────────

    def register_product(self, abs_path: str) -> None:
        """Register ONE product path (no-op if not a product)."""
        self.register_batch([abs_path])

    def register_batch(self, paths: list[str]) -> None:
        """Register a batch of RAW paths. Classifies each independently of any
        surface verdict (the Gate-1 fix), then upserts under one flock.

        AC5: resolve all paths first, GROUP by owning tree, run ONE check-ignore
        --stdin per tree (not one subprocess per path), then classify. Keyed by
        relative path: re-registering refreshes ``last_touched`` (+role/kind/
        gitignored) but never duplicates. AC4: eviction inside the same flock.
        """
        # 1. Resolve every raw path to (tree_root, rel_path, repo); drop externals.
        resolved = []  # (tree_root, rel_path, repo)
        for a in paths:
            r = self._resolve(a)
            if r is not None:
                resolved.append(r)
        if not resolved:
            return

        # 2. Group rel_paths per owning tree → ONE batched check-ignore per tree (AC5).
        by_tree: dict[Path, list[str]] = {}
        for tree_root, rel_path, _repo in resolved:
            by_tree.setdefault(tree_root, []).append(rel_path)
        ignore_maps: dict[Path, dict[str, Optional[bool]]] = {
            tree_root: self._batch_gitignored(tree_root, rels)
            for tree_root, rels in by_tree.items()
        }

        # 3. Classify each with its pre-computed gitignore verdict.
        classified = []
        for tree_root, rel_path, repo in resolved:
            ignored = ignore_maps.get(tree_root, {}).get(rel_path)
            prod = self._classify(tree_root, rel_path, repo, ignored)
            if prod is not None:
                classified.append(prod)
        if not classified:
            return

        def _upsert(data: dict) -> None:
            products = data.setdefault("products", [])
            by_path = {e["path"]: e for e in products}
            for prod in classified:
                existing = by_path.get(prod.path)
                if existing is not None:
                    # Refresh mutable fields; PRESERVE first_produced.
                    existing["role"] = prod.role.value
                    existing["kind"] = prod.kind
                    existing["gitignored"] = prod.gitignored
                    existing["last_touched"] = prod.last_touched
                else:
                    row = asdict(prod)
                    row["role"] = prod.role.value  # store the enum VALUE, not the member
                    products.append(row)
                    by_path[prod.path] = row
            # AC4: bounded store — evict OLDEST by last_touched past the cap. Runs
            # inside the SAME flock (P8: no parallel writer). A just-refreshed live
            # product has the newest last_touched, so eviction removes only genuinely
            # stale rows; a re-touched or backfilled product re-enters on next write.
            if len(products) > MAX_PRODUCTS:
                products.sort(key=lambda e: e.get("last_touched", ""))
                del products[: len(products) - MAX_PRODUCTS]

        self._mutate(_upsert)

    # ── backfill (AC5) ─────────────────────────────────────────────────────────

    def backfill_from_gitlog(self, days: int = 30) -> None:
        """Seed the store from the last ``days`` of git-log products (idempotent).

        Enumerates files touched in recent commits (the same source the Artifacts
        overlay uses today), classifies each, and upserts. Keyed by path → running
        twice adds no duplicate (AC5). Only tracked files appear in git-log, so a
        gitignored deck is NOT backfilled here — it registers live via the watcher
        hook (AC3). Fail-safe: any git error → no-op (never raises).

        On a SUCCESSFUL git-log run (even if it produced zero products) sets a
        ``backfilled_at`` marker so the endpoint never re-runs the 30s git-log on a
        product-less workspace (Gate-2 meta-review MED). A git ERROR does NOT set the
        marker — that stays retryable.
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
        # Mark backfill DONE (git-log succeeded) even when zero products were found,
        # so has_backfilled() is True and the endpoint won't re-run the git-log on the
        # next open of a product-less workspace.
        self._mutate(lambda data: data.__setitem__("backfilled_at", datetime.now(timezone.utc).isoformat()))
