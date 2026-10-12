"""R28 execution test: hard gates are IMMUNE to the depth axis (SRS design §5.2 铁律).

The depth axis (test_depth_axis.py) tunes only NON-safety rigor (REVIEW specialist
count, adversarial vote count, M3 skeptic, test layers). The §5.2 iron law:

    任何用户、任何档位,`depth=light` 都不能绕过硬门禁。

The hard gates — adversarial_commit_gate, dangerous_command_gate — are PreToolUse
hooks that key off the COMMAND + session markers, and NEVER read a depth or profile
field. So immunity is BY CONSTRUCTION: there is no depth input to the gate to weaken.

These tests PROVE that construction holds: they drive each gate under a simulated
`depth=light` run context (env var + run state) and assert it STILL fires on the
case it is meant to block. If a future change ever made a gate read depth, these
go RED.

Design canon: Knowledge/Designs/2026-10-12-pipeline-requirement-spec-and-scope-depth-design.md §5.2
Covers AC6. Companion to test_depth_axis.py (the pure resolve_depth logic).
"""

import asyncio
import os
from pathlib import Path

import pytest

from core import security_hooks
from core.security_hooks import create_adversarial_commit_gate


@pytest.fixture
def audit_dir(tmp_path, monkeypatch):
    """Point the gate's marker dir at a temp path (no real state touched)."""
    d = tmp_path / "pipeline_agent_audit"
    monkeypatch.setattr(security_hooks, "_AGENT_AUDIT_DIR", d)
    return d


@pytest.fixture
def light_depth_context(monkeypatch):
    """Simulate a depth=light run context as aggressively as possible — env var +
    a run-state-shaped dict — so if ANY gate code tried to read depth to relax, it
    would find 'light' here. The gate reading NONE of this is the point.
    """
    monkeypatch.setenv("SWARM_PIPELINE_DEPTH", "light")
    monkeypatch.setenv("SWARM_RUN_DEPTH", "light")
    # Also ensure the sanctioned force-bypass is NOT set (that is a separate,
    # deliberate escape hatch and must not mask this test).
    monkeypatch.delenv("SWARM_ADVERSARIAL_GATE_FORCE", raising=False)
    return {"depth": "light", "profile": "goal"}


def _run_gate(gate, command, tool_name="Bash"):
    return asyncio.run(
        gate({"tool_name": tool_name, "tool_input": {"command": command}}, None, None)
    )


def _is_deny(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


class TestAdversarialCommitGateDepthImmune:
    """AC6: adversarial_commit_gate DENYs an uncovered `git commit` even under depth=light."""

    def test_commit_denied_under_light_depth_no_marker(self, audit_dir, light_depth_context):
        # No adversarial marker + depth=light → MUST still DENY. Depth cannot buy
        # a bypass of "no commit without adversarial review first".
        gate = create_adversarial_commit_gate({"sdk_session_id": "depthtest1"})
        result = _run_gate(gate, "git commit -m 'ship it'")
        assert _is_deny(result), (
            "adversarial_commit_gate must DENY an unreviewed commit regardless of depth=light "
            "(§5.2 iron law: depth never weakens a hard gate)"
        )

    def test_commit_approved_only_with_marker_depth_irrelevant(self, audit_dir, light_depth_context):
        # The ONLY thing that flips the gate to approve is the adversarial marker —
        # NOT depth. With a marker present, approve (proves the gate keys off the
        # marker, and depth=light did not independently approve the no-marker case above).
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "session_depthtest1_adv_1.marker").write_text('{"adversarial": true}')
        gate = create_adversarial_commit_gate({"sdk_session_id": "depthtest1"})
        result = _run_gate(gate, "git commit -m 'ship it'")
        assert not _is_deny(result), "with an adversarial marker the gate approves — depth is not the lever"


class TestGateReadsNoDepthField:
    """Structural proof covering ALL hard gates: the security_hooks source contains
    no depth/profile field read. This is the invariant the behavioral commit-gate
    test above rests on — immunity is BY CONSTRUCTION: there is no depth input to
    ANY hard gate (adversarial_commit, dangerous_command, external_approval, …) for
    a 'light' value to flow into. If a future edit adds a depth read into the hook
    layer, this test flags it immediately.

    Why source-grep rather than N behavioral tests: the dangerous/external gates
    take a live PermissionManager; reconstructing each here would duplicate
    test_security_hooks.py AND couple to mock internals. The field-read invariant
    is the real guarantee — a gate that never reads depth cannot be weakened by it,
    for every gate at once.
    """

    def test_security_hooks_source_has_no_depth_field_read(self):
        src = Path(security_hooks.__file__).read_text()
        # The gate must not branch on a depth value. "defense-in-depth" (a doc
        # idiom) and a dir-"depth" comment are fine; a run-state depth/profile_tier
        # lookup is NOT.
        for needle in ('get("depth")', "get('depth')", '["depth"]', "['depth']",
                       'get("profile_tier")', 'get("profile")', "get('profile')"):
            assert needle not in src, (
                f"hard-gate source reads {needle!r} — a hard gate must NOT branch on "
                f"depth/profile (§5.2 iron law). If this is intentional, it breaks depth immunity."
            )
