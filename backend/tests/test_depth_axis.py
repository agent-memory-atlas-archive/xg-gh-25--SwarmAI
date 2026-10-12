"""Tests for the pipeline depth axis (SRS design §5.2 — Phase 3 块C).

Depth is an ORTHOGONAL axis to profile: it tunes only non-safety rigor
(REVIEW specialist count, adversarial vote count, M3 skeptic, test layers),
NEVER the hard gates. Two tiers to start: standard (= old strict rigor) and
light (= old relaxed rigor). Each profile carries a default depth; the user
can override with --depth.

Design canon: Knowledge/Designs/2026-10-12-pipeline-requirement-spec-and-scope-depth-design.md §5.2
Covers: AC5 (depth axis resolution), AC8 (strangler — unknown/None safe).
The hard-gate-immunity R28 test (AC6) lives in test_depth_immunity.py (it
needs the hook layer, not just this pure module).
"""

import pytest

from core.pipeline_profiles import (
    DEPTH_DEFAULTS,
    DEPTH_TIERS,
    normalize_depth,
    resolve_depth,
    get_profile_stages,
    PIPELINE_PROFILES,
)


class TestDepthTiers:
    def test_two_tiers_to_start(self):
        # §5.2: start with exactly 2 tiers (standard/light); deep deferred.
        assert DEPTH_TIERS == ("standard", "light")

    def test_every_profile_has_a_default_depth(self):
        # Every canonical profile must map to a default depth, else resolve_depth
        # would KeyError on a legit profile.
        for prof in PIPELINE_PROFILES:
            assert prof in DEPTH_DEFAULTS, f"{prof} missing a default depth"

    def test_strict_profiles_default_standard(self):
        # full/bugfix/goal are strict → default standard (= old strict rigor).
        assert DEPTH_DEFAULTS["full"] == "standard"
        assert DEPTH_DEFAULTS["bugfix"] == "standard"
        assert DEPTH_DEFAULTS["goal"] == "standard"

    def test_relaxed_profiles_default_light(self):
        # trivial/docs/research are relaxed → default light (= old relaxed rigor).
        assert DEPTH_DEFAULTS["trivial"] == "light"
        assert DEPTH_DEFAULTS["docs"] == "light"
        assert DEPTH_DEFAULTS["research"] == "light"


class TestNormalizeDepth:
    def test_canonical_passthrough(self):
        assert normalize_depth("standard") == "standard"
        assert normalize_depth("light") == "light"

    def test_case_and_whitespace(self):
        assert normalize_depth("  STANDARD ") == "standard"
        assert normalize_depth("Light") == "light"

    def test_none_is_none(self):
        # None = "no override" — resolve_depth will fall back to the profile default.
        assert normalize_depth(None) is None

    def test_unknown_depth_rejected(self):
        # An unknown tier must NOT silently pass (that would let a typo weaken rigor
        # unnoticed). Fail-closed to None (= use profile default), never invent a tier.
        assert normalize_depth("deep") is None
        assert normalize_depth("garbage") is None


class TestResolveDepth:
    def test_no_override_uses_profile_default(self):
        assert resolve_depth("full", None) == "standard"
        assert resolve_depth("docs", None) == "light"

    def test_valid_override_wins(self):
        # A strict profile explicitly set to light (design §5.2 "full + light = 赶时间").
        assert resolve_depth("full", "light") == "light"
        # A relaxed profile explicitly set to standard (security-critical trivial).
        assert resolve_depth("trivial", "standard") == "standard"

    def test_invalid_override_falls_back_to_default(self):
        # A typo'd override must fall back to the profile default, never crash,
        # never weaken (strict stays standard).
        assert resolve_depth("full", "deep") == "standard"
        assert resolve_depth("full", "garbage") == "standard"

    def test_unknown_profile_defaults_standard(self):
        # AC8 strangler: an unknown/variant profile is STRICT (is_relaxed_profile
        # fail-closed semantics) → its depth default is standard (never silently light).
        assert resolve_depth("Full", None) == "standard"  # alias → full → standard
        assert resolve_depth("totally-unknown", None) == "standard"
        assert resolve_depth(None, None) == "standard"


class TestOrthogonality:
    def test_depth_does_not_change_stage_list(self):
        # The whole point: depth is orthogonal to profile. get_profile_stages must
        # be identical regardless of depth (depth is not even a param to it).
        full_stages = get_profile_stages("full")
        assert full_stages == PIPELINE_PROFILES["full"]
        # resolve_depth must not have mutated PIPELINE_PROFILES as a side effect.
        resolve_depth("full", "light")
        assert get_profile_stages("full") == full_stages


class TestRunCreateDepthWiring:
    """AC5 end-to-end: `run-create --depth` resolves + persists depth into run.json
    (the CLI→run.json half; TestResolveDepth covers the pure logic). The Pipeline-card
    matrix badge (ScopeDepthMatrix) reads this field, so an unwired --depth = a badge
    that always shows the default = a silent gap. This test closes it."""

    def test_depth_override_persisted_to_run_json(self, tmp_path, monkeypatch):
        import io, json, contextlib
        from argparse import Namespace
        from scripts import artifact_cli as cli
        monkeypatch.setenv("SWARM_DATA_DIR", str(tmp_path))

        args = Namespace(project="TP", requirement="depth wire test", profile="full", depth="light")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.cmd_run_create(args, reg=None)
        run_file = json.loads(buf.getvalue())["file"]
        data = json.loads(open(run_file).read())
        assert data["depth"] == "light", f"--depth light must persist, got {data.get('depth')}"

    def test_depth_defaults_from_profile_when_omitted(self, tmp_path, monkeypatch):
        import io, json, contextlib
        from argparse import Namespace
        from scripts import artifact_cli as cli
        monkeypatch.setenv("SWARM_DATA_DIR", str(tmp_path))

        args = Namespace(project="TP", requirement="depth default test", profile="goal", depth=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.cmd_run_create(args, reg=None)
        data = json.loads(open(json.loads(buf.getvalue())["file"]).read())
        assert data["depth"] == "standard", f"goal default depth=standard, got {data.get('depth')}"
