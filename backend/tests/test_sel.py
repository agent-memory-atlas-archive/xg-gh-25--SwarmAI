"""Tests for core/sel.py — the Security Event Log (persistent tool-audit trail).

SEL fills the C050 gap: tool/gate decisions had NO persistent structured audit —
pre_tool_logger wrote one logger.info line into the 20MB-rotating daemon log, so
"which tools were invoked when" was unrecoverable after rotation. SEL is an
append-only JSONL at ~/.swarm-ai/security_events.jsonl — deliberately OUTSIDE
data.db and OUTSIDE the workspace, so it survives both a DB wipe and log rotation.

Scope of THIS build (narrowed per Gate-0): tool-invocation flow (outcome from the
pre_tool_logger埋点, always "allow"); downstream gate deny-emission is Phase 2.
HMAC tamper-chain is OUT (C050's pain is "not lost", not "tampered").
"""
import json
import os
import pytest
from pathlib import Path


@pytest.fixture
def sel_dir(tmp_path, monkeypatch):
    """Point SEL at an isolated temp app-data dir."""
    import core.sel as sel
    monkeypatch.setattr(sel, "_app_data_dir", lambda: tmp_path)
    return tmp_path


class TestAppendEvent:
    def test_append_writes_one_json_line(self, sel_dir):
        import core.sel as sel
        sel.append_event(event_type="tool_invocation", caller="session:abc",
                         operation="Bash", outcome="allow", resource="ls")
        log = sel_dir / "security_events.jsonl"
        assert log.exists()
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 1
        ev = json.loads(lines[0])
        assert ev["event_type"] == "tool_invocation"
        assert ev["caller"] == "session:abc"
        assert ev["operation"] == "Bash"
        assert ev["outcome"] == "allow"
        assert "ts" in ev and "event_id" in ev

    def test_multiple_appends_preserve_order(self, sel_dir):
        import core.sel as sel
        for i in range(5):
            sel.append_event(event_type="tool_invocation", caller="s", operation=f"op{i}", outcome="allow")
        lines = (sel_dir / "security_events.jsonl").read_text().strip().splitlines()
        ops = [json.loads(x)["operation"] for x in lines]
        assert ops == [f"op{i}" for i in range(5)]

    def test_fail_soft_never_raises(self, sel_dir, monkeypatch):
        """AC7/R28: a write failure must NOT raise — tool execution continues.
        Force the write to fail and assert append_event swallows it."""
        import core.sel as sel

        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(sel, "_write_line", boom)
        # Must not raise:
        sel.append_event(event_type="tool_invocation", caller="s", operation="x", outcome="allow")


class TestNoPayload:
    def test_tool_input_values_never_stored(self, sel_dir):
        """AC3: the SEL records operation + outcome + a resource SUMMARY, never
        the raw tool_input payload values (secrets/content must not leak into audit)."""
        import core.sel as sel
        secret = "SUPER_SECRET_TOKEN_VALUE_12345"
        sel.append_event(event_type="tool_invocation", caller="s", operation="Bash",
                         outcome="allow", resource=sel.summarize_resource({"command": secret}))
        body = (sel_dir / "security_events.jsonl").read_text()
        assert secret not in body, "raw payload value leaked into SEL"

    def test_resource_summary_truncated(self, sel_dir):
        import core.sel as sel
        huge = "x" * 5000
        s = sel.summarize_resource({"path": huge})
        assert len(s) <= 500

    def test_summary_records_key_name_and_size_not_value(self, sel_dir):
        """Gate-2 run_7ada39d6 KEY-boundary lock: summarize_resource records the KEY
        NAME + the value SIZE (that IS the audit value — which params a tool got),
        but NEVER the value itself. Pins the exact contract the docstring promises."""
        import core.sel as sel
        s = sel.summarize_resource({"command": "rm -rf /tmp/x", "cwd": "/home"})
        # key names present (audit value); value SIZES present (measured: 13 and 5)
        assert "command(13)" in s and "cwd(5)" in s
        # the actual value content is NOT present
        assert "rm -rf" not in s and "/home" not in s


class TestStorageLocation:
    def test_sel_path_is_outside_db_and_workspace(self, sel_dir):
        """AC2: SEL must live at app-data root, NOT inside data.db's bytes and NOT
        inside the git workspace — so a DB wipe or workspace reset cannot take it."""
        import core.sel as sel
        p = sel.sel_log_path()
        assert p.name == "security_events.jsonl"
        assert p.parent == sel_dir
        # not the db file, not under a 'SwarmWS' workspace dir
        assert "data.db" not in str(p)
        assert "SwarmWS" not in str(p)


class TestRotation:
    def test_rotation_seals_segment_and_events_still_readable(self, sel_dir, monkeypatch):
        """AC5/AC6: over the size threshold the live log seals into
        security_events.d/, a rotation boundary event starts the new live log,
        and read_events() still returns the sealed events."""
        import core.sel as sel
        monkeypatch.setattr(sel, "_MAX_SEGMENT_BYTES", 500)  # tiny threshold for test
        for i in range(50):
            sel.append_event(event_type="tool_invocation", caller="s",
                             operation=f"op{i}", outcome="allow", resource="r" * 20)
        seg_dir = sel_dir / "security_events.d"
        assert seg_dir.exists() and any(seg_dir.iterdir()), "no sealed segment"
        # a rotation boundary event exists
        all_events = sel.read_events()
        assert any(e.get("event_type") == "sel_rotation" for e in all_events)
        # every op survived across the rotation(s)
        ops = {e.get("operation") for e in all_events}
        for i in range(50):
            assert f"op{i}" in ops, f"op{i} lost across rotation"

    def test_read_events_merges_sealed_and_live(self, sel_dir):
        import core.sel as sel
        sel.append_event(event_type="tool_invocation", caller="s", operation="live1", outcome="allow")
        events = sel.read_events()
        assert any(e.get("operation") == "live1" for e in events)


class TestPreToolLoggerIntegration:
    """The pre_tool_logger埋点: every tool call lands a SEL event, gate behavior
    is unchanged (still approves), and the payload never leaks.

    CRITICAL (Gate-2 run_7ada39d6): these drive the hook THROUGH the factory
    (create_pre_tool_logger) with a closure-injected session_key, and pass the hook
    the REAL SDK context shape ({"signal": None}, which carries NO identity). The
    earlier version injected a fabricated {"session_key": ...} context the SDK never
    produces — a vacuous test that stayed green while production caller was always
    "unknown". The caller MUST come from the closure, verified below."""

    # The exact context the SDK hands every hook callback (query.py:448). No identity.
    SDK_CONTEXT = {"signal": None}

    @pytest.mark.asyncio
    async def test_pre_tool_logger_appends_sel_and_still_approves(self, sel_dir):
        from core.security_hooks import create_pre_tool_logger
        import core.sel as sel

        hook = create_pre_tool_logger("session:xyz", {"sdk_session_id": "session:xyz"})
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
            "tuid-1",
            self.SDK_CONTEXT,  # real SDK context — carries NO session identity
        )
        # AC4: gate behavior zero-regression — still approves.
        assert result == {"decision": "approve"}
        # Durable SEL event written.
        events = sel.read_events()
        tool_events = [e for e in events if e.get("event_type") == "tool_invocation"]
        assert len(tool_events) == 1
        ev = tool_events[0]
        assert ev["operation"] == "Bash"
        assert ev["outcome"] == "allow"
        # caller came from the CLOSURE, not the (identity-less) SDK context.
        assert ev["caller"] == "session:xyz"

    @pytest.mark.asyncio
    async def test_caller_from_closure_not_sdk_context(self, sel_dir):
        """The HIGH-finding lock: with the REAL empty SDK context, caller is STILL
        the closure's session_key — never 'unknown'. Mutating the factory to read
        caller from the context arg (the old bug) makes this RED."""
        from core.security_hooks import create_pre_tool_logger
        import core.sel as sel

        hook = create_pre_tool_logger("agent-7", None)
        await hook({"tool_name": "Read", "tool_input": {"file_path": "/x"}},
                   "t", {"signal": None})
        ev = [e for e in sel.read_events() if e.get("event_type") == "tool_invocation"][-1]
        assert ev["caller"] == "agent-7"
        assert ev["caller"] != "unknown"

    @pytest.mark.asyncio
    async def test_caller_falls_back_to_unknown_when_no_identity(self, sel_dir):
        """No session_key available → caller is an honest 'unknown' (the default),
        not a crash and not a fabricated value."""
        from core.security_hooks import create_pre_tool_logger
        import core.sel as sel

        hook = create_pre_tool_logger()  # no identity at all
        await hook({"tool_name": "Glob", "tool_input": {"pattern": "*.py"}},
                   "t", {"signal": None})
        ev = [e for e in sel.read_events() if e.get("event_type") == "tool_invocation"][-1]
        assert ev["caller"] == "unknown"

    @pytest.mark.asyncio
    async def test_pre_tool_logger_does_not_leak_payload(self, sel_dir):
        from core.security_hooks import create_pre_tool_logger
        secret = "ghp_SECRETTOKEN999"
        hook = create_pre_tool_logger("s1")
        await hook(
            {"tool_name": "Bash", "tool_input": {"command": f"echo {secret}"}},
            "tuid-2",
            {"signal": None},
        )
        body = (sel_dir / "security_events.jsonl").read_text()
        assert secret not in body, "tool_input value leaked into SEL"

    @pytest.mark.asyncio
    async def test_pre_tool_logger_sel_failure_does_not_break_approve(self, sel_dir, monkeypatch):
        """R28: if SEL append raises, pre_tool_logger must STILL approve (hot path
        must never be blocked by a broken audit)."""
        import core.sel as sel
        from core.security_hooks import create_pre_tool_logger

        def boom(*a, **k):
            raise RuntimeError("sel exploded")
        monkeypatch.setattr(sel, "append_event", boom)
        hook = create_pre_tool_logger("s1")
        result = await hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/x"}}, "t", {"signal": None})
        assert result == {"decision": "approve"}
