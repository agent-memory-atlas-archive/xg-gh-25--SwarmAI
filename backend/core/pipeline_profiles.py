"""Pipeline profile definitions — shared between CLI, routers, and skills.

Single source of truth for which stages each pipeline profile includes.
Imported by artifact_cli.py, routers/pipelines.py, and any future
component that needs to know pipeline stage sequences.

NOTE: The external architecture defines 9 stages (EVALUATE → THINK → PLAN →
BUILD → REVIEW → TEST → ADVERSARIAL → DELIVER → REFLECT). ADVERSARIAL is
architecturally stage 7, but in execution it is embedded inside the DELIVER
stage as a blocking gate (spawn fresh-context sub-agent before packaging).
This is why the profile lists below show 8 entries for "full" — ADVERSARIAL
is not a separate orchestration step, it's a mandatory sub-step of DELIVER.
All docs, READMEs, and external communications say "9 stages."
"""

PIPELINE_PROFILES: dict[str, list[str]] = {
    "full": ["evaluate", "think", "plan", "build", "review", "test", "deliver", "reflect"],
    "trivial": ["evaluate", "think", "build", "review", "test", "deliver", "reflect"],
    "research": ["evaluate", "think", "reflect"],
    "docs": ["evaluate", "think", "plan", "deliver", "reflect"],
    "bugfix": ["evaluate", "think", "plan", "build", "review", "test", "deliver", "reflect"],
    "goal": ["evaluate", "think", "plan", "goal_cycle", "deliver", "reflect"],
}


# Profiles whose gates run at RELAXED rigor (no adversarial-enforcement, no
# understanding/REPRO block required). EVERYTHING ELSE — full, bugfix, goal, the
# legacy "standard" alias, AND any unknown/variant value — is STRICT. This is the
# single source of truth for the relaxed/strict decision; see is_relaxed_profile.
_RELAXED_PROFILES: frozenset[str] = frozenset({"trivial", "docs", "research"})

# Legacy / spelling aliases → canonical profile name. "standard" is the historical
# rank-4 alias of "full" (same stage set). Keep this the ONLY place aliases live.
_PROFILE_ALIASES: dict[str, str] = {"standard": "full"}


# ─────────────────────────────────────────────────────────────────────────────
# Depth axis (SRS design §5.2 — Phase 3 块C) — ORTHOGONAL to profile.
#
# Depth tunes ONLY non-safety rigor (REVIEW specialist count, adversarial vote
# count, M3 skeptic on/off, test layers). It NEVER touches the hard gates
# (adversarial_commit_gate / dangerous_command_gate / security) — those are
# code-enforced PreToolUse hooks that do not read depth or profile, so they are
# immune by construction (verified by test_depth_immunity.py / R28).
#
# Two tiers to start (§5.2 "约束版 Option A — 2 档起步"): a third `deep` tier is
# deliberately deferred until a real need appears (P6 — don't pre-build knobs).
#   standard = the old STRICT rigor (full/bugfix/goal default)
#   light    = the old RELAXED rigor (trivial/docs/research default)
# This mirrors is_relaxed_profile's existing strict/relaxed split exactly, so
# depth is a user-facing re-expression of a distinction the system already made —
# it adds a DIAL, not a new behavior class.
DEPTH_TIERS: tuple[str, ...] = ("standard", "light")

# Each profile's DEFAULT depth. Derived from the SAME strict/relaxed split as
# _RELAXED_PROFILES so the two can never silently disagree: relaxed → light,
# everything else → standard. Keyed by canonical profile name (post-normalize).
DEPTH_DEFAULTS: dict[str, str] = {
    "full": "standard",
    "bugfix": "standard",
    "goal": "standard",
    "trivial": "light",
    "docs": "light",
    "research": "light",
}


def normalize_depth(depth: str | None) -> str | None:
    """Canonicalize a raw --depth value, or None if it is absent/invalid.

    Returns None for None/empty/whitespace (= "no override, use the profile
    default") AND for any value not in DEPTH_TIERS. The unknown→None rule is
    FAIL-SAFE by design: a typo'd `--depth deap` must fall back to the profile
    default (resolve_depth), never invent a tier and never silently weaken rigor.
    Unlike normalize_profile (which passes an unknown profile through so the
    relaxed-check can fail-closed to STRICT), an unknown DEPTH has no safe
    passthrough — the only safe fallback is "use the profile default", which
    None signals to resolve_depth.
    """
    if depth is None:
        return None
    key = depth.strip().lower()
    if key not in DEPTH_TIERS:
        return None
    return key


def resolve_depth(profile: str | None, override: str | None) -> str:
    """Resolve the effective depth for a run: a valid override wins, else the
    profile's default. ALWAYS returns a valid tier (never None).

    - override is a valid tier → use it (user explicitly chose, e.g. a strict
      `full` run forced to `light` to go faster, or a `trivial` forced to
      `standard` for a security-critical one-liner — both §5.2 real use cases).
    - override is None / invalid → the profile default. An unknown/variant
      profile resolves (via normalize_profile) to its canonical name, or to
      `full` → standard; i.e. an unknown profile is STRICT→standard, never
      silently light (AC8 strangler, matching is_relaxed_profile fail-closed).

    This never mutates PIPELINE_PROFILES or affects get_profile_stages — depth is
    strictly orthogonal to the stage list.
    """
    valid_override = normalize_depth(override)
    if valid_override is not None:
        return valid_override
    canonical = normalize_profile(profile)
    return DEPTH_DEFAULTS.get(canonical, "standard")


def normalize_profile(profile: str | None) -> str:
    """Canonicalize a raw profile value to its comparison key — the C3 SSOT.

    Every strict/relaxed gate decision MUST compare against this, never a raw
    field value. Root cause of C3: a variant like ``"Full"`` received full's
    stage list (get_profile_stages fallback) yet slipped past deliver's hardcoded
    ``profile in ("full","bugfix","")`` adversarial-enforcement literals, silently
    skipping the gate. Normalizing at every source removes that asymmetry.

    Rules (all lower + strip first):
      - ``None`` / empty / whitespace-only → ``"full"`` (matches the historical
        ``profile or "full"`` fallback AND the ``""``-in-strict-set semantics).
      - a known alias (``"standard"``) → its canonical name (``"full"``).
      - an unknown value → its lowercased/stripped form UNCHANGED (NOT remapped to
        full) so is_relaxed_profile can fail-closed to STRICT on it. (The stage-list
        fallback to full lives separately in get_profile_stages.)
    """
    if profile is None:
        return "full"
    key = profile.strip().lower()
    if not key:
        return "full"
    return _PROFILE_ALIASES.get(key, key)


def is_relaxed_profile(profile: str | None) -> bool:
    """True iff this profile runs gates at RELAXED rigor. FAIL-CLOSED: anything not
    explicitly in _RELAXED_PROFILES (including unknown/variant/typo profiles) is
    STRICT. This is the C3 fix — replaces the scattered, fail-OPEN
    ``profile in ("full","bugfix","")`` literals whose inconsistency let a variant
    skip adversarial enforcement. Normalizes first, so ``"DOCS"`` == ``"docs"``."""
    return normalize_profile(profile) in _RELAXED_PROFILES


def get_profile_stages(profile: str | None) -> list[str]:
    """Get the ordered stage list for a pipeline profile.

    Normalizes first (so 'Full'/'FULL'/'standard' resolve to full's stages), then
    falls back to 'full' if the normalized profile is still unknown or None.
    """
    return PIPELINE_PROFILES.get(normalize_profile(profile), PIPELINE_PROFILES["full"])
