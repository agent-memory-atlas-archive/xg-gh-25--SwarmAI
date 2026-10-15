"""Tests for core/verdict.py — the ordered Verdict value object.

Phase 1 of the gate-governance refactor: a single ordered disposition
(ALLOW < WARN < HITL < DENY) + a severity-max merge + a dict<->Verdict adapter,
so hook_builder._build_chain stops hand-merging three inconsistent dict carriers.

The adapter must be LOSSLESS at the SDK boundary: from_sdk(d) carries the original
dict in `sdk_payload`, and to_sdk round-trips it back byte-for-byte. This is what
lets _build_chain reproduce the legacy merge semantics exactly (proven by the
back-to-back equivalence tests in test_hook_builder.py).
"""
import pytest


class TestDispositionOrdering:
    """Disposition is an ordered scale: ALLOW < WARN < HITL < DENY."""

    def test_disposition_strictly_ordered(self):
        from core.verdict import Disposition
        assert Disposition.ALLOW < Disposition.WARN < Disposition.HITL < Disposition.DENY

    def test_disposition_max_picks_strictest(self):
        from core.verdict import Disposition
        assert max(Disposition.ALLOW, Disposition.DENY) is Disposition.DENY
        assert max(Disposition.WARN, Disposition.HITL) is Disposition.HITL


class TestMergeVerdicts:
    """merge_verdicts = strictest disposition wins; ties keep the FIRST
    (reproduces the legacy 'earlier guard wins' clobber fix, run_6af22b0d)."""

    def test_empty_is_allow(self):
        from core.verdict import merge_verdicts, Disposition
        assert merge_verdicts([]).disposition is Disposition.ALLOW

    def test_single_passthrough(self):
        from core.verdict import merge_verdicts, Verdict, Disposition
        v = Verdict(Disposition.WARN, reason="r")
        assert merge_verdicts([v]) is v

    def test_strictest_wins(self):
        from core.verdict import merge_verdicts, Verdict, Disposition
        vs = [Verdict(Disposition.ALLOW), Verdict(Disposition.DENY), Verdict(Disposition.WARN)]
        assert merge_verdicts(vs).disposition is Disposition.DENY

    def test_tie_keeps_first(self):
        """A later equal-severity verdict must NOT clobber an earlier one — this
        is the run_6af22b0d CRITICAL (a later allow must not overwrite an earlier
        deny) generalized: at the SAME disposition, first wins."""
        from core.verdict import merge_verdicts, Verdict, Disposition
        first = Verdict(Disposition.DENY, reason="first-deny")
        second = Verdict(Disposition.DENY, reason="second-deny")
        assert merge_verdicts([first, second]) is first

    def test_earlier_deny_survives_later_allow(self):
        """The concrete clobber case: deny before allow → deny wins."""
        from core.verdict import merge_verdicts, Verdict, Disposition
        deny = Verdict(Disposition.DENY, reason="guard says no")
        allow = Verdict(Disposition.ALLOW)
        assert merge_verdicts([deny, allow]) is deny


class TestFromSdkToSdk:
    """The adapter maps the 6 real gate dict carriers → Verdict and back,
    LOSSLESSLY (sdk_payload round-trip). from_sdk never UPGRADES an unknown
    carrier to deny/hitl (no false-block) nor DOWNGRADES a deny to allow."""

    def test_block_decision_maps_to_deny(self):
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"decision": "block", "reason": "dangerous"})
        assert v.disposition is Disposition.DENY

    def test_permission_deny_maps_to_deny(self):
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": "no",
        }})
        assert v.disposition is Disposition.DENY

    def test_permission_ask_defer_map_to_hitl(self):
        from core.verdict import from_sdk, Disposition
        for t in ("ask", "defer"):
            v = from_sdk({"hookSpecificOutput": {"permissionDecision": t}})
            assert v.disposition is Disposition.HITL, t

    def test_behavior_deny_is_NOT_terminal_matches_legacy_chain(self):
        """The legacy _build_chain never inspected a top-level `behavior` key —
        {"behavior":"deny"} fell through to its merge branch and contributed
        nothing (ALLOW/no-op). from_sdk must preserve that exactly: `behavior` is
        NOT a DENY carrier for the chain. (Gate-2 adversarial caught an earlier
        version that mapped it to DENY — an out-of-scope behavior change.)"""
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"behavior": "deny", "message": "nope"})
        assert v.disposition is Disposition.ALLOW

    def test_advisory_additional_context_maps_to_warn(self):
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"decision": "approve", "additionalContext": "REMEMBER"})
        assert v.disposition is Disposition.WARN

    def test_plain_approve_maps_to_allow(self):
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"decision": "approve"})
        assert v.disposition is Disposition.ALLOW

    def test_allow_with_updated_input_is_allow(self):
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"hookSpecificOutput": {
            "permissionDecision": "allow", "updatedInput": {"answered": True},
        }})
        assert v.disposition is Disposition.ALLOW

    def test_empty_dict_is_allow(self):
        from core.verdict import from_sdk, Disposition
        assert from_sdk({}).disposition is Disposition.ALLOW

    def test_unknown_dict_is_allow_never_upgraded(self):
        """An unrecognized carrier must be conservative: ALLOW (never silently
        promoted to deny/hitl, which would false-block a legit tool)."""
        from core.verdict import from_sdk, Disposition
        v = from_sdk({"someFutureKey": "value"})
        assert v.disposition is Disposition.ALLOW

    @pytest.mark.parametrize("d", [
        {"decision": "block", "reason": "dangerous"},
        {"decision": "approve"},
        {"decision": "approve", "additionalContext": "ctx"},
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                "permissionDecisionReason": "no"}},
        {"hookSpecificOutput": {"permissionDecision": "allow", "updatedInput": {"x": 1}}},
        {"behavior": "deny", "message": "nope"},
        {},
    ])
    def test_round_trip_is_byte_identical(self, d):
        """to_sdk(from_sdk(d)) == d — the lossless-passthrough invariant that lets
        _build_chain's terminal short-circuit return the ORIGINAL dict verbatim
        (reason/systemMessage/permissionDecisionReason bypass fields preserved)."""
        from core.verdict import from_sdk, to_sdk
        assert to_sdk(from_sdk(d)) == d
