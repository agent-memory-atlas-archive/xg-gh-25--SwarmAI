"""Outlook email polling adapter for the unified inbox.

Bridges ``aws-outlook-mcp`` to poll for new emails at a configurable interval.
Each new email becomes an :class:`InboundMessage` routed through the gateway's
``handle_inbound_message`` pipeline (inheriting the pushworthy/authorization
gates from Run 1).

Config keys:
    poll_interval_seconds:  seconds between polls (default 60)

Phase 2 limitation: ``send_message`` is a no-op stub — email reply requires
a separate design (threading, CC, rich-text) deferred to Phase 3.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import uuid4

from channels.base import ChannelAdapter, InboundMessage, OutboundMessage
from channels.registry import register_adapter

logger = logging.getLogger(__name__)


class OutlookChannelAdapter(ChannelAdapter):
    """Polling adapter that fetches emails via aws-outlook-mcp.

    Lifecycle:
        1. __init__ — parse config, set up state
        2. start() — launch async polling task
        3. _poll_once() — one fetch-and-emit cycle
        4. stop() — cancel polling, set _stopped
        5. send_message() — stub (Phase 3)
    """

    def __init__(self, channel_id: str, config: dict, on_message) -> None:
        super().__init__(channel_id, config, on_message)
        self._poll_interval: int = config.get("poll_interval_seconds", 60)
        self._connection_mode: str = "polling"
        self._stopped: bool = False
        self._poll_task: Optional[asyncio.Task] = None
        # Track seen email IDs to avoid re-emitting (insertion-ordered)
        self._seen_ids: dict[str, None] = {}  # OrderedDict-like (dict is insertion-ordered since 3.7)
        # Cap seen IDs to prevent unbounded growth
        self._seen_ids_max: int = 500

    @property
    def channel_type(self) -> str:
        """Return the channel type identifier."""
        return "outlook"

    async def validate_config(self) -> tuple[bool, str | None]:
        """Validate adapter configuration.

        For Phase 2, only checks that poll_interval is positive.
        """
        if self._poll_interval <= 0:
            return False, "poll_interval_seconds must be positive"
        return True, None

    async def start(self) -> None:
        """Start the polling loop as an async task."""
        self._stopped = False
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Outlook adapter started for channel %s (interval=%ds)",
                     self.channel_id, self._poll_interval)

    async def stop(self) -> None:
        """Cancel the polling task and clean up."""
        self._stopped = True
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Outlook adapter stopped for channel %s", self.channel_id)

    async def send_message(self, message: OutboundMessage) -> Optional[str]:
        """Stub — email reply deferred to Phase 3.

        Returns None (no external message ID).
        """
        logger.warning("Outlook send_message called but not implemented (Phase 3)")
        return None

    # ------------------------------------------------------------------
    # Polling internals
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Run _poll_once at the configured interval until stopped."""
        while not self._stopped:
            try:
                await self._poll_once()
            except Exception:
                logger.exception("Outlook poll cycle failed (non-fatal)")
            # Sleep interruptibly
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def _poll_once(self) -> None:
        """Fetch emails and emit new ones as InboundMessage."""
        try:
            emails = await self._fetch_emails()
        except Exception:
            logger.exception("Outlook fetch_emails failed")
            return

        for email in emails:
            email_id = email.get("id", "")
            if not email_id or email_id in self._seen_ids:
                continue

            # Track this email (dict preserves insertion order since Python 3.7)
            self._seen_ids[email_id] = None
            # Evict oldest if over cap — drop the first (oldest) entries
            if len(self._seen_ids) > self._seen_ids_max:
                excess = len(self._seen_ids) - self._seen_ids_max // 2
                keys_to_drop = list(self._seen_ids.keys())[:excess]
                for k in keys_to_drop:
                    del self._seen_ids[k]

            # Build InboundMessage
            sender = email.get("from", {})
            sender_name = sender.get("name", "Unknown")
            sender_addr = sender.get("address", "")
            subject = email.get("subject", "(no subject)")
            preview = email.get("body_preview", "")
            text = f"📧 {subject}\n{preview}" if preview else f"📧 {subject}"

            msg = InboundMessage(
                channel_id=self.channel_id,
                external_chat_id=sender_addr or email_id,
                external_sender_id=sender_addr,
                external_thread_id=email_id,  # thread = email conversation
                external_message_id=email_id,
                text=text,
                sender_display_name=sender_name,
                attachments=[],
                metadata={
                    "chat_type": "im",  # emails are always DM-equivalent → pushworthy
                    "source": "outlook",
                    "subject": subject,
                    "sender_address": sender_addr,
                    "received_at": email.get("received_at", ""),
                },
            )

            try:
                await self._on_message(msg)
            except Exception:
                logger.exception("Failed to deliver Outlook email %s", email_id)

    async def _fetch_emails(self) -> list[dict]:
        """Fetch recent emails via aws-outlook-mcp.

        Override this in tests to mock the MCP boundary.
        In production, this will call the MCP tool via ToolSearch.
        For Phase 2, this is a placeholder that returns [] — the real
        MCP integration requires the MCP server to be connected at runtime.
        """
        # Phase 2: placeholder — real MCP integration in a follow-up
        # when the adapter is actually connected to a running MCP server.
        # The test suite mocks this method at the boundary.
        logger.debug("Outlook _fetch_emails: no MCP integration yet (placeholder)")
        return []


# Self-register on import (same pattern as slack.py)
register_adapter("outlook", OutlookChannelAdapter)
