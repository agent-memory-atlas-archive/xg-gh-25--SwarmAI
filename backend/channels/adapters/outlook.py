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
import json
import logging
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

from channels.base import ChannelAdapter, InboundMessage, OutboundMessage
from channels.registry import register_adapter

try:
    from config import get_app_data_dir
except Exception:  # pragma: no cover - config always present in daemon
    get_app_data_dir = None  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP config discovery + stdio bridge (mirrors SlackMcpBridge in slack.py).
# A dedicated function/class keeps the live Slack path untouched (zero
# regression) while reusing the proven daemon→MCP stdio JSON-RPC pattern.
# ---------------------------------------------------------------------------

def _find_outlook_mcp_config() -> Optional[dict]:
    """Find the aws-outlook-mcp server config from mcp-dev.json.

    Returns ``{"command": str, "args": list, "env": dict}`` or None.
    Mirrors ``slack.py:_find_slack_mcp_config`` but matches the outlook
    server id. The config path is the owner's own machine (never network
    input), so the spawned command is always operator-controlled.
    """
    if get_app_data_dir is None:
        return None
    mcp_dev = get_app_data_dir() / "SwarmWS" / ".claude" / "mcps" / "mcp-dev.json"
    if not mcp_dev.is_file():
        return None
    try:
        entries = json.loads(mcp_dev.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return None
        for entry in entries:
            eid = (entry.get("id", "") or entry.get("name", "")).lower()
            if "outlook" in eid and entry.get("enabled", True):
                config = entry.get("config", {})
                cmd = config.get("command", "")
                if cmd:
                    return {
                        "command": cmd,
                        "args": config.get("args", []),
                        "env": config.get("env", {}),
                    }
    except Exception:
        logger.debug("Failed to read aws-outlook-mcp config", exc_info=True)
    return None


class OutlookMcpBridge:
    """Async stdio JSON-RPC 2.0 bridge to the aws-outlook-mcp binary.

    Mirrors ``SlackMcpBridge`` (slack.py): spawn on first use, perform the
    MCP initialize handshake, reuse the connection for subsequent calls,
    concurrency-safe via ``asyncio.Lock``. Line-delimited JSON framing to
    match the working Slack bridge against the same MCP server family.

    Every failure mode (no binary, spawn error, handshake failure, timeout)
    degrades to ``None`` — the caller (``_fetch_emails``) maps that to ``[]``
    so a dead/slow MCP can never crash or freeze the polling loop.
    """

    def __init__(self) -> None:
        config = _find_outlook_mcp_config()
        if config:
            self._command: str = config["command"]
            self._args: list = config["args"]
            self._env: dict = config["env"]
        else:
            self._command = ""
            self._args = []
            self._env = {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._initialized = False
        self._request_id = 0
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        """True if an aws-outlook-mcp binary was found in config."""
        return bool(self._command)

    def _build_request(self, tool_name: str, arguments: dict) -> dict:
        self._request_id += 1
        return {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

    async def _spawn(self) -> bool:
        if self._process and self._process.returncode is None:
            return True
        if not self._command:
            return False
        if not Path(self._command).is_file():
            logger.warning("aws-outlook-mcp binary not found")
            return False
        env = {**os.environ, **self._env}
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._command, *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._initialized = False
            return True
        except Exception:
            logger.debug("Failed to spawn aws-outlook-mcp process", exc_info=True)
            self._process = None
            return False

    async def _send_receive(self, request: dict, timeout: float = 15.0) -> Optional[dict]:
        proc = self._process
        if not proc or proc.returncode is not None:
            return None
        line = json.dumps(request) + "\n"
        try:
            proc.stdin.write(line.encode())
            await proc.stdin.drain()
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not raw:
                return None
            return json.loads(raw)
        except asyncio.TimeoutError:
            logger.warning("aws-outlook-mcp response timed out after %.1fs", timeout)
            return None
        except Exception:
            logger.debug("aws-outlook-mcp send/receive failed", exc_info=True)
            return None

    async def _ensure_initialized(self, timeout: float = 15.0) -> bool:
        if self._initialized:
            return True
        if not await self._spawn():
            return False
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "swarm-outlook-adapter", "version": "1.0"},
            },
        }
        self._request_id = 1
        resp = await self._send_receive(init_req, timeout=timeout)
        if not resp or "result" not in resp:
            logger.warning("aws-outlook-mcp initialize handshake failed")
            await self.close()
            return False
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        proc = self._process
        if proc and proc.returncode is None:
            try:
                proc.stdin.write((json.dumps(notif) + "\n").encode())
                await proc.stdin.drain()
            except Exception:
                pass
        self._initialized = True
        return True

    async def call_tool(self, tool_name: str, arguments: dict,
                        timeout: float = 15.0) -> Optional[dict]:
        """Call an MCP tool; return the ``result`` dict or None on any error."""
        if not self._command:
            return None
        async with self._lock:
            if not await self._ensure_initialized(timeout=timeout):
                return None
            request = self._build_request(tool_name, arguments)
            resp = await self._send_receive(request, timeout=timeout)
            if resp and "result" in resp:
                return resp["result"]
            if resp and "error" in resp:
                logger.warning("aws-outlook-mcp tool error (type=%s)",
                               type(resp.get("error")).__name__)
            return None

    async def close(self) -> None:
        proc = self._process
        if proc:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except (asyncio.TimeoutError, Exception):
                try:
                    proc.kill()
                except Exception:
                    pass
            self._process = None
            self._initialized = False


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
        # How many recent emails to request per poll (Graph default ~10).
        self._fetch_limit: int = config.get("fetch_limit", 25)
        self._connection_mode: str = "polling"
        self._stopped: bool = False
        self._poll_task: Optional[asyncio.Task] = None
        # Track seen email IDs to avoid re-emitting (insertion-ordered)
        self._seen_ids: dict[str, None] = {}  # OrderedDict-like (dict is insertion-ordered since 3.7)
        # Cap seen IDs to prevent unbounded growth
        self._seen_ids_max: int = 500
        # One-time guard so the array-key-drift WARNING (in _fetch_emails)
        # fires once, not every 60s poll.
        self._warned_key_drift: bool = False
        # First-poll priming: the inbox already holds history when the adapter
        # starts. Without this guard, the first poll (and EVERY daemon restart,
        # since _seen_ids is in-memory) would emit all existing emails as "new"
        # and flood the dock. The first poll records their ids WITHOUT emitting;
        # only mail arriving after startup surfaces. (Polling has no live-event
        # stream like Slack's socket mode, so it must self-prime.)
        self._primed: bool = False
        # Lazy MCP bridge — created on first fetch so construction (and the
        # whole test suite) never spawns a subprocess.
        self._bridge: Optional[OutlookMcpBridge] = None

    def _get_bridge(self) -> OutlookMcpBridge:
        """Return the lazily-created MCP bridge (one per adapter)."""
        if self._bridge is None:
            self._bridge = OutlookMcpBridge()
        return self._bridge

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
        # Release the MCP subprocess so stop() leaves no orphan.
        if self._bridge is not None:
            try:
                await self._bridge.close()
            except Exception:
                logger.debug("Outlook bridge close failed", exc_info=True)
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

        # First successful poll: prime the seen-id set from existing inbox
        # history WITHOUT emitting, so startup/restart never floods the dock
        # with pre-existing mail. Only emails arriving after this surface.
        # Guard on a non-empty fetch so a transient empty/failed first poll
        # (e.g. MCP auth still warming up) doesn't "prime" an empty set and
        # then flood on the first REAL fetch.
        if not self._primed:
            if emails:
                for email in emails:
                    eid = email.get("id", "")
                    if eid:
                        self._seen_ids[eid] = None
                self._primed = True
                logger.info("Outlook adapter primed %d existing email(s) for channel %s (not emitted)",
                            len(self._seen_ids), self.channel_id)
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
            # Thread grouping: real Outlook senders have no address, so prefer
            # the conversation id (stable per-thread) over the sender address or
            # the per-message id — otherwise every email keys its own chat.
            conv_id = email.get("conversation_id", "")
            chat_id = sender_addr or conv_id or email_id

            msg = InboundMessage(
                channel_id=self.channel_id,
                external_chat_id=chat_id,
                external_sender_id=sender_addr or sender_name,
                external_thread_id=conv_id or email_id,  # thread = email conversation
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

    @staticmethod
    def _normalize_email(raw: dict) -> Optional[dict]:
        """Map one raw email object to the shape ``_poll_once`` consumes.

        The REAL aws-outlook-mcp email_inbox object (observed live 2026-10-26)
        uses: ``itemIds[0].id`` (id), ``topic`` (subject), ``preview``
        (body), ``lastDeliveryTime`` (received), ``senders`` (a list of plain
        display-name STRINGS, no email address). ``_poll_once`` consumes a
        snake_case shape (``id`` / ``subject`` / ``body_preview`` /
        ``received_at`` / ``from.{name,address}``). This bridges the two.

        Each field tries the REAL key first, then falls back to the older
        Graph camelCase / snake_case spellings so a future shape change (or
        the existing fallback-shaped tests) still parses. ``senders`` carry
        no address, so ``from.address`` is "" for the real shape.

        Returns ``None`` when the email has no id — without a stable id the
        dedup cache (``_seen_ids``) cannot work, so such a record would be
        re-delivered every poll. Dropping it is safer than looping it.
        """
        if not isinstance(raw, dict):
            return None

        # id: real = itemIds[0].id; fallbacks = top-level id / message_id
        email_id = ""
        item_ids = raw.get("itemIds")
        if isinstance(item_ids, list) and item_ids and isinstance(item_ids[0], dict):
            email_id = item_ids[0].get("id") or ""
        if not email_id:
            email_id = raw.get("id") or raw.get("message_id") or ""
        if not email_id:
            return None

        # sender: real = senders[] (plain-string display names, no address);
        # fallbacks = Graph from.emailAddress.{name,address} / from.{name,address}
        sender_name = ""
        sender_addr = ""
        senders = raw.get("senders")
        if isinstance(senders, list) and senders:
            first = senders[0]
            sender_name = first if isinstance(first, str) else ""
        if not sender_name:
            sender_obj = raw.get("from") or {}
            if not isinstance(sender_obj, dict):
                sender_obj = {}
            email_addr_obj = sender_obj.get("emailAddress")
            if isinstance(email_addr_obj, dict):
                sender_name = email_addr_obj.get("name", "")
                sender_addr = email_addr_obj.get("address", "")
            else:
                sender_name = sender_obj.get("name", "")
                sender_addr = sender_obj.get("address", "")

        return {
            "id": email_id,
            "subject": raw.get("topic") or raw.get("subject") or "",
            "body_preview": raw.get("preview") or raw.get("bodyPreview") or raw.get("body_preview") or "",
            "received_at": raw.get("lastDeliveryTime") or raw.get("receivedDateTime") or raw.get("received_at") or "",
            "from": {"name": sender_name, "address": sender_addr},
            # Stable per-thread grouping key. Real Outlook senders carry no email
            # address, so without this every message would key its own
            # conversation at the gateway (external_chat_id falls back to the
            # unique message id). conversationId groups a thread like a chat.
            "conversation_id": raw.get("conversationId") or raw.get("conversation_id") or "",
        }

    @staticmethod
    def _unwrap_mcp_result(result: dict) -> Optional[dict]:
        """Unwrap the two-layer aws-outlook-mcp response.

        Layer 1 — MCP envelope: ``{"content": [{"type": "text",
        "text": "<json-string>"}]}``. The real payload is a JSON STRING
        inside ``content[0].text`` (same shape slack.py parses).
        Layer 2 — business envelope: the decoded payload is
        ``{"success": bool, ...}``; a ``success: false`` (or an ``error``
        key) means the MCP call itself failed server-side.

        Returns the decoded inner payload dict on success, else ``None``.
        All content is treated as untrusted DATA — only structural keys are
        read, never executed or interpreted as instructions.
        """
        if not isinstance(result, dict):
            return None
        content = result.get("content")
        if not isinstance(content, list) or not content:
            return None
        text = None
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                break
        if not isinstance(text, str) or not text:
            return None
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("success") is False or "error" in payload:
            return None
        return payload

    @staticmethod
    def _extract_email_list(payload: dict) -> list:
        """Pull the email array out of the inner payload.

        The REAL aws-outlook-mcp email_inbox response (observed live
        2026-10-26) nests the array under ``content.emails`` — the business
        payload is ``{"success": true, "content": {"message": ..,
        "emails": [...]}}``. Check that nested path FIRST, then fall back to
        the top-level keys various Graph/MCP shapes might use. Returns ``[]``
        if no known location holds a list.
        """
        _keys = ("emails", "items", "value", "messages", "data")
        # Real shape nests the array under ``content`` (a dict). Check the known
        # keys there FIRST, then fall back to the same keys at top level.
        content = payload.get("content")
        if isinstance(content, dict):
            for key in _keys:
                arr = content.get(key)
                if isinstance(arr, list):
                    return arr
        for key in _keys:
            arr = payload.get(key)
            if isinstance(arr, list):
                return arr
        return []

    async def _fetch_emails(self) -> list[dict]:
        """Fetch recent emails via aws-outlook-mcp, normalized for _poll_once.

        Returns a list of snake_case email dicts. Returns ``[]`` on EVERY
        failure (no binary, spawn/handshake fail, timeout, server-side error
        envelope, non-JSON content, unexpected shape) — never raises — so a
        dead or slow MCP cannot crash or freeze the polling loop.

        Email content is untrusted external DATA: nothing here logs a body,
        subject, or address, and nothing interprets email text as an
        instruction. Downstream delivery goes through the gateway's existing
        owner-only authorization path (unchanged by this adapter).
        """
        try:
            bridge = self._get_bridge()
            if not bridge.available:
                logger.debug("Outlook MCP bridge unavailable (no binary configured)")
                return []
            result = await bridge.call_tool(
                "email_inbox",
                {"limit": self._fetch_limit, "unreadOnly": False},
            )
            if result is None:
                return []
            payload = self._unwrap_mcp_result(result)
            if payload is None:
                logger.debug("Outlook MCP returned error/empty envelope")
                return []
            raw_list = self._extract_email_list(payload)
            # Key-drift detector: a success payload that carries a non-empty list
            # under some OTHER key (one _extract_email_list doesn't know) would
            # make every poll silently return [] and the adapter would look
            # healthy while emitting nothing. The live email_inbox shape could
            # not be observed at build time (auth down), so surface the drift
            # loudly ONCE instead of failing invisibly. Logs only the KEY NAME,
            # never email content.
            if not raw_list and not self._warned_key_drift:
                _known = ("items", "value", "emails", "messages", "data")
                other_list_keys = [
                    k for k, v in payload.items()
                    if isinstance(v, list) and v and k not in _known
                ]
                # Mirror _extract_email_list's search DEPTH: the real shape nests
                # the array one level under ``content`` (a dict). A drift of the
                # nested key (content.messages instead of content.emails) would
                # be invisible to a top-level-only scan — which is exactly the
                # shape this detector must catch. So scan one level into content.
                content = payload.get("content")
                if isinstance(content, dict):
                    other_list_keys += [
                        "content." + k for k, v in content.items()
                        if isinstance(v, list) and v and k not in _known
                    ]
                if other_list_keys:
                    logger.warning(
                        "Outlook fetch: success payload had no email list under a known key, "
                        "but found list(s) under unrecognized key(s) %s — array-key drift? "
                        "_extract_email_list may need updating.", other_list_keys)
                    self._warned_key_drift = True
            normalized = []
            for raw in raw_list:
                item = self._normalize_email(raw)
                if item is not None:
                    normalized.append(item)
            logger.debug("Outlook fetch: %d email(s) normalized", len(normalized))
            return normalized
        except Exception:
            logger.exception("Outlook _fetch_emails failed (non-fatal)")
            return []


# Self-register on import (same pattern as slack.py)
register_adapter("outlook", OutlookChannelAdapter)
