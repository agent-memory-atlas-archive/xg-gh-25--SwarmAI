"""Outlook polling adapter — MCP-bridged email fetch for unified inbox.

Tests AC1-AC4 of run_f430f0d5 (Unified Inbox Phase 2) +
AC1-AC5 of run_b39f7756 (real aws-outlook-mcp fetch).
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.base import ChannelAdapter, InboundMessage


# ===================================================================
# Fake asyncio subprocess for driving OutlookMcpBridge without a real MCP
# ===================================================================
class _FakeStream:
    """Minimal stand-in for asyncio StreamReader/Writer."""
    def __init__(self):
        self._responses = []   # queued response bytes (for stdout.readline)
        self.written = []      # bytes written by the bridge (stdin)

    def queue_response(self, obj):
        self._responses.append((json.dumps(obj) + "\n").encode())

    # StreamWriter side (stdin)
    def write(self, data: bytes):
        self.written.append(data)

    async def drain(self):
        return None

    # StreamReader side (stdout)
    async def readline(self):
        if self._responses:
            return self._responses.pop(0)
        return b""  # EOF


class _FakeProc:
    """Stand-in for asyncio.subprocess.Process."""
    def __init__(self, stdin: _FakeStream, stdout: _FakeStream):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = _FakeStream()
        self.returncode = None
        self.pid = 4321
        self._killed = False

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self._killed = True
        self.returncode = -9

    async def wait(self):
        self.returncode = self.returncode or 0
        return self.returncode


# ===================================================================
# AC1: OutlookChannelAdapter exists, extends ChannelAdapter, has config
# ===================================================================
class TestOutlookAdapterInit:
    def test_adapter_exists_and_extends_base(self):
        """OutlookChannelAdapter is importable and extends ChannelAdapter."""
        from channels.adapters.outlook import OutlookChannelAdapter
        assert issubclass(OutlookChannelAdapter, ChannelAdapter)

    def test_config_defaults(self):
        """Adapter parses config with default poll_interval_seconds=60."""
        from channels.adapters.outlook import OutlookChannelAdapter
        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        assert adapter._poll_interval == 60
        assert adapter._connection_mode == "polling"

    def test_config_custom_interval(self):
        """Custom poll_interval_seconds is respected."""
        from channels.adapters.outlook import OutlookChannelAdapter
        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {"poll_interval_seconds": 120}, on_msg)
        assert adapter._poll_interval == 120


# ===================================================================
# AC2: start() launches poll, poll fetches via MCP, emits InboundMessage
# ===================================================================
class TestOutlookAdapterPoll:
    @pytest.mark.asyncio
    async def test_poll_creates_inbound_message(self):
        """A mock MCP email result triggers _on_message with InboundMessage."""
        from channels.adapters.outlook import OutlookChannelAdapter

        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)

        # Mock the MCP call to return one email
        mock_email = {
            "id": "email-123",
            "subject": "Test email",
            "from": {"name": "Bob", "address": "bob@example.com"},
            "body_preview": "Hello from Outlook",
            "received_at": "2026-10-23T10:00:00Z",
        }
        adapter._fetch_emails = AsyncMock(return_value=[mock_email])
        adapter._primed = True  # steady-state: skip first-poll priming

        # Run one poll cycle
        await adapter._poll_once()

        # Verify _on_message was called with an InboundMessage
        on_msg.assert_awaited_once()
        msg = on_msg.await_args.args[0]
        assert isinstance(msg, InboundMessage)
        assert msg.channel_id == "ch1"
        assert "Test email" in msg.text
        assert msg.sender_display_name == "Bob"
        assert msg.metadata.get("chat_type") == "im"  # emails are always DM-equivalent

    @pytest.mark.asyncio
    async def test_poll_skips_already_seen_emails(self):
        """Emails already processed (by ID) are not re-emitted."""
        from channels.adapters.outlook import OutlookChannelAdapter

        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)

        mock_email = {
            "id": "email-123",
            "subject": "Test",
            "from": {"name": "Bob", "address": "bob@example.com"},
            "body_preview": "Hello",
            "received_at": "2026-10-23T10:00:00Z",
        }
        adapter._fetch_emails = AsyncMock(return_value=[mock_email])
        adapter._primed = True  # steady-state: skip first-poll priming

        await adapter._poll_once()
        assert on_msg.await_count == 1

        # Second poll with same email — should NOT emit again
        await adapter._poll_once()
        assert on_msg.await_count == 1  # still 1, not 2

    @pytest.mark.asyncio
    async def test_poll_handles_fetch_error_gracefully(self):
        """A fetch error logs but does not crash the adapter."""
        from channels.adapters.outlook import OutlookChannelAdapter

        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        adapter._fetch_emails = AsyncMock(side_effect=RuntimeError("MCP down"))

        # Should not raise
        await adapter._poll_once()
        on_msg.assert_not_awaited()


# ===================================================================
# AC3: stop() cancels polling task
# ===================================================================
class TestOutlookAdapterLifecycle:
    @pytest.mark.asyncio
    async def test_stop_sets_stopped_flag(self):
        """stop() sets _stopped = True."""
        from channels.adapters.outlook import OutlookChannelAdapter

        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        adapter._fetch_emails = AsyncMock(return_value=[])

        # Start and immediately stop
        await adapter.start()
        await asyncio.sleep(0.05)  # let the task start
        await adapter.stop()
        assert adapter._stopped is True

    @pytest.mark.asyncio
    async def test_send_message_returns_none(self):
        """send_message is a stub for Phase 2 — returns None."""
        from channels.adapters.outlook import OutlookChannelAdapter

        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        result = await adapter.send_message(MagicMock())
        assert result is None


# ===================================================================
# AC4: Registry includes outlook adapter
# ===================================================================
class TestOutlookRegistration:
    def test_outlook_in_registry(self):
        """After load_adapters, 'outlook' is in the adapter registry."""
        from channels.registry import load_adapters, get_adapter_class
        load_adapters()
        cls = get_adapter_class("outlook")
        assert cls is not None
        assert cls.__name__ == "OutlookChannelAdapter"

    def test_outlook_in_supported_types(self):
        """list_supported_types includes outlook entry."""
        from channels.registry import load_adapters, list_supported_types
        load_adapters()
        types = list_supported_types()
        outlook_types = [t for t in types if t["id"] == "outlook"]
        assert len(outlook_types) == 1
        assert outlook_types[0]["available"] is True


# ===================================================================
# AC1: _normalize_email maps real Graph-API shape → _poll_once snake_case
# ===================================================================
class TestNormalizeEmail:
    def test_graph_api_shape_maps_to_poll_once_shape(self):
        """A real Graph-API email object normalizes to the exact dict
        shape _poll_once consumes (id/from.{name,address}/subject/
        body_preview/received_at)."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())

        # Real aws-outlook-mcp / Graph-API camelCase shape
        raw = {
            "id": "AAMkAGI2-graph-id",
            "subject": "Q3 Planning",
            "bodyPreview": "Here is the agenda for Q3 planning...",
            "receivedDateTime": "2026-10-26T08:30:00Z",
            "from": {"emailAddress": {"name": "Alice Chen", "address": "alice@amazon.com"}},
            "isRead": False,
        }
        out = adapter._normalize_email(raw)

        assert out is not None
        assert out["id"] == "AAMkAGI2-graph-id"
        assert out["subject"] == "Q3 Planning"
        assert out["body_preview"] == "Here is the agenda for Q3 planning..."
        assert out["received_at"] == "2026-10-26T08:30:00Z"
        # from must be the snake_case {name,address} shape _poll_once reads
        assert out["from"]["name"] == "Alice Chen"
        assert out["from"]["address"] == "alice@amazon.com"

    def test_missing_id_returns_none(self):
        """An email object with no id → None (can't dedup → skip)."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        raw = {"subject": "no id", "bodyPreview": "x",
               "from": {"emailAddress": {"name": "N", "address": "a@b.com"}}}
        assert adapter._normalize_email(raw) is None

    def test_already_snake_case_shape_passes_through(self):
        """Defensive: if the MCP ever returns snake_case already, normalize
        still yields the consumer shape (don't double-map to empty)."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        raw = {
            "id": "snake-1",
            "subject": "S",
            "body_preview": "preview text",
            "received_at": "2026-10-26T09:00:00Z",
            "from": {"name": "Bob", "address": "bob@b.com"},
        }
        out = adapter._normalize_email(raw)
        assert out is not None
        assert out["id"] == "snake-1"
        assert out["body_preview"] == "preview text"
        assert out["received_at"] == "2026-10-26T09:00:00Z"
        assert out["from"]["name"] == "Bob"
        assert out["from"]["address"] == "bob@b.com"

    @pytest.mark.asyncio
    async def test_poll_once_consumes_normalized_output_end_to_end(self):
        """The normalized dict feeds _poll_once and produces a correct
        InboundMessage — proves the shape contract end-to-end (not just
        the mock boundary the existing tests use)."""
        from channels.adapters.outlook import OutlookChannelAdapter

        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        raw = {
            "id": "e2e-1", "subject": "Hi", "bodyPreview": "body",
            "receivedDateTime": "2026-10-26T10:00:00Z",
            "from": {"emailAddress": {"name": "Carol", "address": "carol@b.com"}},
        }
        normalized = adapter._normalize_email(raw)
        adapter._fetch_emails = AsyncMock(return_value=[normalized])
        adapter._primed = True  # skip first-poll priming for this content check
        await adapter._poll_once()

        on_msg.assert_awaited_once()
        msg = on_msg.await_args.args[0]
        assert msg.sender_display_name == "Carol"
        assert "Hi" in msg.text
        # NON-VACUITY (red-team catch): body_preview + received_at must actually
        # reach the message, not just be normalized. A distinct preview value
        # proves _poll_once reads the normalized key, so a drift to a raw Graph
        # key (bodyPreview) would blank the body and FAIL here.
        assert "body" in msg.text  # the bodyPreview content "body" surfaced into text
        assert msg.metadata.get("received_at") == "2026-10-26T10:00:00Z"
        assert msg.metadata.get("sender_address") == "carol@b.com"


# ===================================================================
# First-poll priming — no backlog flood on startup / restart
# ===================================================================
class TestFirstPollPriming:
    @pytest.mark.asyncio
    async def test_first_poll_primes_without_emitting(self):
        """First poll records existing inbox ids but emits NOTHING (no flood)."""
        from channels.adapters.outlook import OutlookChannelAdapter
        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        existing = [
            {"id": "old-1", "subject": "A", "body_preview": "a", "received_at": "t", "from": {"name": "X", "address": "x@b.com"}},
            {"id": "old-2", "subject": "B", "body_preview": "b", "received_at": "t", "from": {"name": "Y", "address": "y@b.com"}},
        ]
        adapter._fetch_emails = AsyncMock(return_value=existing)
        await adapter._poll_once()
        on_msg.assert_not_awaited()          # nothing emitted on prime
        assert adapter._primed is True
        assert "old-1" in adapter._seen_ids and "old-2" in adapter._seen_ids

    @pytest.mark.asyncio
    async def test_new_email_after_priming_emits(self):
        """After priming, only genuinely new mail surfaces."""
        from channels.adapters.outlook import OutlookChannelAdapter
        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        existing = [{"id": "old-1", "subject": "A", "body_preview": "a", "received_at": "t", "from": {"name": "X", "address": "x@b.com"}}]
        adapter._fetch_emails = AsyncMock(return_value=existing)
        await adapter._poll_once()           # prime
        on_msg.assert_not_awaited()

        # Next poll: old-1 still present + a new one
        adapter._fetch_emails = AsyncMock(return_value=existing + [
            {"id": "new-1", "subject": "NEW", "body_preview": "fresh", "received_at": "t2", "from": {"name": "Z", "address": "z@b.com"}},
        ])
        await adapter._poll_once()
        on_msg.assert_awaited_once()         # only new-1
        msg = on_msg.await_args.args[0]
        assert "NEW" in msg.text

    @pytest.mark.asyncio
    async def test_empty_or_failed_first_poll_does_not_prime(self):
        """A transient empty first fetch (MCP warming up) must NOT prime an
        empty set — otherwise the first REAL fetch would flood."""
        from channels.adapters.outlook import OutlookChannelAdapter
        on_msg = AsyncMock()
        adapter = OutlookChannelAdapter("ch1", {}, on_msg)
        adapter._fetch_emails = AsyncMock(return_value=[])
        await adapter._poll_once()
        assert adapter._primed is False      # did NOT prime on empty
        on_msg.assert_not_awaited()

        # Now the real inbox arrives → it primes (not floods)
        adapter._fetch_emails = AsyncMock(return_value=[
            {"id": "real-1", "subject": "R", "body_preview": "r", "received_at": "t", "from": {"name": "X", "address": "x@b.com"}},
        ])
        await adapter._poll_once()
        assert adapter._primed is True
        on_msg.assert_not_awaited()          # primed, not emitted


# ===================================================================
# AC2: OutlookMcpBridge — spawn, initialize handshake, call_tool
# ===================================================================
class TestOutlookMcpBridge:
    @pytest.mark.asyncio
    async def test_call_tool_handshake_and_request_format(self):
        """Bridge spawns, performs initialize handshake, sends a correctly
        formatted tools/call for email_inbox, and parses the result."""
        from channels.adapters.outlook import OutlookMcpBridge

        stdin, stdout = _FakeStream(), _FakeStream()
        proc = _FakeProc(stdin, stdout)
        # Queue: initialize result, then tools/call result (MCP envelope:
        # content[0].text holds a JSON string).
        stdout.queue_response({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
        inner = {"success": True, "items": [{"id": "x"}]}
        stdout.queue_response({
            "jsonrpc": "2.0", "id": 2,
            "result": {"content": [{"type": "text", "text": json.dumps(inner)}]},
        })

        bridge = OutlookMcpBridge()
        bridge._command = "/fake/aws-outlook-mcp"  # pretend config found a binary

        async def _fake_exec(*args, **kwargs):
            return proc

        with patch("asyncio.create_subprocess_exec", _fake_exec), \
             patch("pathlib.Path.is_file", return_value=True):
            result = await bridge.call_tool("email_inbox", {"limit": 25, "unreadOnly": False})

        # Handshake happened: first write is an initialize request
        first = json.loads(stdin.written[0].decode())
        assert first["method"] == "initialize"
        # A tools/call for email_inbox was sent with our args
        calls = [json.loads(w.decode()) for w in stdin.written]
        tool_calls = [c for c in calls if c.get("method") == "tools/call"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["params"]["name"] == "email_inbox"
        assert tool_calls[0]["params"]["arguments"]["limit"] == 25
        assert tool_calls[0]["params"]["arguments"]["unreadOnly"] is False
        # Result is the raw MCP result dict (envelope parsing is the adapter's job)
        assert result is not None
        assert "content" in result

    @pytest.mark.asyncio
    async def test_call_tool_returns_none_when_no_binary(self):
        """No configured binary → available False → call_tool returns None,
        never raises."""
        from channels.adapters.outlook import OutlookMcpBridge
        bridge = OutlookMcpBridge()
        bridge._command = ""  # no binary
        assert bridge.available is False
        result = await bridge.call_tool("email_inbox", {})
        assert result is None

    @pytest.mark.asyncio
    async def test_call_tool_timeout_returns_none(self):
        """A hung MCP (readline never returns) → wait_for timeout → None,
        no raise. Proves the poll loop can't be frozen by a stuck MCP."""
        from channels.adapters.outlook import OutlookMcpBridge

        stdin = _FakeStream()

        class _HangStdout(_FakeStream):
            async def readline(self):
                await asyncio.sleep(10)  # longer than the bridge timeout
                return b""

        proc = _FakeProc(stdin, _HangStdout())
        bridge = OutlookMcpBridge()
        bridge._command = "/fake/aws-outlook-mcp"

        async def _fake_exec(*args, **kwargs):
            return proc

        with patch("asyncio.create_subprocess_exec", _fake_exec), \
             patch("pathlib.Path.is_file", return_value=True):
            # Drive with a tiny timeout so the test is fast
            result = await bridge.call_tool("email_inbox", {}, timeout=0.05)
        assert result is None


# ===================================================================
# AC3: _fetch_emails degradation — any failure → [] without raising
# ===================================================================
class TestFetchEmailsDegradation:
    @pytest.mark.asyncio
    async def test_no_bridge_available_returns_empty(self):
        """Bridge unavailable (no binary) → [] not raise."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        with patch.object(adapter, "_get_bridge") as get_bridge:
            fake = MagicMock()
            fake.available = False
            get_bridge.return_value = fake
            out = await adapter._fetch_emails()
        assert out == []

    @pytest.mark.asyncio
    async def test_call_tool_none_returns_empty(self):
        """call_tool returns None (spawn/handshake failed) → []."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        fake = MagicMock()
        fake.available = True
        fake.call_tool = AsyncMock(return_value=None)
        with patch.object(adapter, "_get_bridge", return_value=fake):
            out = await adapter._fetch_emails()
        assert out == []

    @pytest.mark.asyncio
    async def test_inner_error_envelope_returns_empty(self):
        """MCP returned a business error envelope {success:false} → []."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        fake = MagicMock()
        fake.available = True
        fake.call_tool = AsyncMock(return_value={
            "content": [{"type": "text",
                         "text": json.dumps({"success": False, "error": {"message": "Error"}})}]
        })
        with patch.object(adapter, "_get_bridge", return_value=fake):
            out = await adapter._fetch_emails()
        assert out == []

    @pytest.mark.asyncio
    async def test_non_json_content_returns_empty(self):
        """content[0].text is not JSON → [] not raise."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        fake = MagicMock()
        fake.available = True
        fake.call_tool = AsyncMock(return_value={
            "content": [{"type": "text", "text": "not json at all <<<"}]
        })
        with patch.object(adapter, "_get_bridge", return_value=fake):
            out = await adapter._fetch_emails()
        assert out == []

    @pytest.mark.asyncio
    async def test_call_tool_raises_returns_empty(self):
        """call_tool raises → _fetch_emails swallows → [] (poll loop lives)."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        fake = MagicMock()
        fake.available = True
        fake.call_tool = AsyncMock(side_effect=RuntimeError("MCP crashed"))
        with patch.object(adapter, "_get_bridge", return_value=fake):
            out = await adapter._fetch_emails()
        assert out == []

    @pytest.mark.asyncio
    async def test_array_key_drift_warns_once(self, caplog):
        """If the success payload carries emails under an UNRECOGNIZED key,
        _fetch_emails returns [] but logs a one-time key-drift WARNING so the
        silent-empty failure mode is visible (meta-review catch)."""
        import logging
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        # 'records' is NOT in the known key list (items/value/emails/messages/data)
        inner = {"success": True, "records": [{"id": "z1", "subject": "S"}]}
        fake = MagicMock()
        fake.available = True
        fake.call_tool = AsyncMock(return_value={
            "content": [{"type": "text", "text": json.dumps(inner)}]
        })
        with patch.object(adapter, "_get_bridge", return_value=fake):
            with caplog.at_level(logging.WARNING):
                out1 = await adapter._fetch_emails()
                out2 = await adapter._fetch_emails()
        assert out1 == [] and out2 == []
        drift_warnings = [r for r in caplog.records if "array-key drift" in r.message or "unrecognized key" in r.message]
        assert len(drift_warnings) == 1  # warned once, not twice
        # the warning names the key but never email content
        assert "records" in drift_warnings[0].message
        assert "S" not in drift_warnings[0].message  # no subject content leaked

    @pytest.mark.asyncio
    async def test_success_envelope_returns_normalized_emails(self):
        """Happy path: valid two-layer envelope with Graph emails →
        normalized snake_case dicts ready for _poll_once."""
        from channels.adapters.outlook import OutlookChannelAdapter
        adapter = OutlookChannelAdapter("ch1", {}, AsyncMock())
        inner = {
            "success": True,
            "items": [
                {"id": "m1", "subject": "A", "bodyPreview": "pa",
                 "receivedDateTime": "2026-10-26T08:00:00Z",
                 "from": {"emailAddress": {"name": "X", "address": "x@b.com"}}},
                {"subject": "no-id drop", "bodyPreview": "pb",
                 "from": {"emailAddress": {"name": "Y", "address": "y@b.com"}}},
            ],
        }
        fake = MagicMock()
        fake.available = True
        fake.call_tool = AsyncMock(return_value={
            "content": [{"type": "text", "text": json.dumps(inner)}]
        })
        with patch.object(adapter, "_get_bridge", return_value=fake):
            out = await adapter._fetch_emails()
        # one valid email, the no-id one dropped by normalize
        assert len(out) == 1
        assert out[0]["id"] == "m1"
        assert out[0]["body_preview"] == "pa"
        assert out[0]["received_at"] == "2026-10-26T08:00:00Z"
        assert out[0]["from"]["address"] == "x@b.com"
