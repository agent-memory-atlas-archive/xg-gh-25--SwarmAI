"""Remove tool-call leak text from a Claude CLI session transcript.

A "leak" is the model writing its tool call as text (``count\\n<invoke ...>``)
instead of a real tool_use. The CLI keeps that text in its own session
transcript, and ``--resume`` replays it to the model on every later turn, which
primes more leaks (observed: 6-8 leaks per session within 20 minutes). Cleaning
the transcript before a ``--resume`` removes the priming.

Public symbols:
- ``find_transcript(sdk_session_id)`` — path of the CLI transcript, or None.
- ``clean_transcript_leaks(path)``    — strip leak text from assistant text
  blocks in place (atomic replace); returns the number of blocks changed.

Only ASSISTANT text blocks whose text starts a line with a raw ``<invoke``
outside code spans are touched (the same signal the live stream uses); prose
that discusses the syntax, tool results, and user messages are left alone.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from .session_utils import find_stream_leak_onset, strip_tool_call_leak

logger = logging.getLogger(__name__)

# The API rejects an empty text block in conversation history, so a block that
# was nothing but a leak keeps a neutral word (no tool-call markup).
EMPTY_FILLER = "(retrying)"

# SDK session ids are UUIDs; anything else is refused so the id can never act
# as a glob pattern or a path component.
_SID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def _projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "projects"


def find_transcript(sdk_session_id: Optional[str]) -> Optional[Path]:
    """Return ``<projects>/<encoded-cwd>/<sid>.jsonl`` if it exists, else None."""
    if not sdk_session_id or not _SID_RE.match(sdk_session_id):
        return None
    root = _projects_dir()
    if not root.is_dir():
        return None
    matches = [p for p in root.glob(f"*/{sdk_session_id}.jsonl") if p.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _clean_line(line: str) -> tuple[str, int]:
    """Return (line, n_blocks_changed) for one transcript record."""
    if "<invoke" not in line or '"assistant"' not in line:
        return line, 0
    try:
        rec = json.loads(line)
    except (ValueError, TypeError):
        return line, 0  # a torn last line from a killed writer stays as-is
    if not isinstance(rec, dict) or rec.get("type") != "assistant":
        return line, 0
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return line, 0
    n = 0
    for block in content:
        if not (isinstance(block, dict) and block.get("type") == "text"):
            continue
        text = block.get("text")
        if not isinstance(text, str) or find_stream_leak_onset(text) == -1:
            continue
        cleaned = strip_tool_call_leak(text)
        if cleaned != text:
            block["text"] = cleaned if cleaned.strip() else EMPTY_FILLER
            n += 1
    if not n:
        return line, 0
    newline = "\n" if line.endswith("\n") else ""
    return json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + newline, n


def clean_transcript_leaks(path: Path) -> int:
    """Strip leak text from ``path`` in place; return blocks changed.

    Blocking file I/O — call via ``asyncio.to_thread``. Must only run while no
    CLI process is writing the file (the caller kills it first). Never raises:
    a cleaning failure must not block the restart, which still --resumes.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        out, total = [], 0
        for line in lines:
            new_line, n = _clean_line(line)
            out.append(new_line)
            total += n
        if not total:
            return 0
        tmp = path.with_name(path.name + ".leakclean.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(out)
        os.replace(tmp, path)
        return total
    except Exception as exc:  # noqa: BLE001 — fail-soft by contract
        logger.warning("leak_transcript.clean_failed path=%s: %s", path, exc)
        return 0
