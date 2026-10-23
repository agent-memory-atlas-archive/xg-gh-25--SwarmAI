"""Outlook polling adapter — MCP-bridged email fetch for unified inbox.

Tests AC1-AC4 of run_f430f0d5 (Unified Inbox Phase 2).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.base import ChannelAdapter, InboundMessage


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
