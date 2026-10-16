"""Daily metrics for the model's tool-call glitch (read-only, zero cost).

The glitch: at a text -> tool_use transition the model corrupts the call
opener into a word ("count", "core", ...) and either writes the whole call as
text (a "leak") or leaves the word in front of a narration line. It lands in
text written right before a tool call, and is copied once it is in history.
AGENT R20 ("Tool calls are silent") targets exactly that channel; this script
shows whether the rule is followed and whether the glitch rate moves.

Per day it reports:
- calls:      API responses that made a tool call (real or leaked)
- pre_text%:  share of those with text before the call (R20 compliance; the
              stage-landmark exception keeps this above 0)
- leaks:      daemon log lines `tool_call_leak_stripped` (transcripts get
              cleaned by the restart path, so logs are the source of truth)
- prefix:     narration lines starting with a glitch word right before a call
- glitch%:    (leaks + prefix) / calls

Sources: CLI transcripts (~/.claude/projects/**/*.jsonl, or CLAUDE_CONFIG_DIR)
and ~/.swarm-ai/logs/backend-daemon.log*.

Usage: python scripts/tool_call_glitch_metrics.py [--days N]

Public symbols:
- ``classify_response(blocks)`` — (made_call, pre_text, prefix) for one response
- ``daily_metrics(days)``       — {date: counters}
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
from pathlib import Path

# Glitch words seen so far; a word must be followed by a CJK character or a
# line ending in ':' to count, so ordinary English ("count the files") is not.
_PREFIX_RE = re.compile(
    r"(?m)^(?:count|court|core|card|care|call|coute)[ \t]*[:：,，]?[ \t]*(?=[\u4e00-\u9fff])"
)
# A bare glitch word as the LAST line of the text right before the call.
_BARE_LAST_RE = re.compile(r"(?:^|\n)[ \t]*(?:count|court|core|card|care|coute)[ \t]*\s*\Z")
_LEAK_LINE_RE = re.compile(r"(?m)^[ \t]*<invoke\s+name=")
# Older daemons logged `_detected` (kill path), newer ones `_stripped`.
_LOG_LEAK_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) .*session_unit\.tool_call_leak_(?:stripped|detected)"
)


def classify_response(blocks: list) -> tuple[bool, bool, bool, bool]:
    """Return (made_call, pre_text, prefix, leaked) for one API response."""
    texts = [b.get("text") or "" for b in blocks if b.get("type") == "text"]
    leaked = any(_LEAK_LINE_RE.search(t) for t in texts)
    made_call = leaked or any(b.get("type") == "tool_use" for b in blocks)
    if not made_call:
        return False, False, False, False
    pre_text = any(t.strip() for t in texts)
    prefix = not leaked and any(
        _PREFIX_RE.search(t) or _BARE_LAST_RE.search(t) for t in texts
    )
    return True, pre_text, prefix, leaked


def _local_day(ts: str) -> str:
    """Transcript timestamps are UTC ('...Z'); daemon logs are local time."""
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date().isoformat()
    except ValueError:
        return ts[:10]


def _transcript_files() -> list[str]:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return glob.glob(os.path.join(base, "projects", "**", "*.jsonl"), recursive=True)


def _responses(path: str, since: str):
    """Yield (date, blocks) per main-thread API response (blocks are split
    across records sharing one message id)."""
    groups: dict[str, tuple[str, list]] = {}
    seen: set = set()
    try:
        fh = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return
    with fh:
        for line in fh:
            if '"assistant"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "assistant" or rec.get("isSidechain"):
                continue
            day = _local_day(rec.get("timestamp") or "")
            if day < since or rec.get("uuid") in seen:
                continue
            seen.add(rec.get("uuid"))
            msg = rec.get("message") or {}
            key = msg.get("id") or rec.get("uuid")
            blocks = [b for b in msg.get("content") or [] if isinstance(b, dict)]
            groups.setdefault(key, (day, []))[1].extend(blocks)
    yield from groups.values()


def daily_metrics(days: int) -> dict[str, collections.Counter]:
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for path in _transcript_files():
        for day, blocks in _responses(path, since):
            made_call, pre_text, prefix, leaked = classify_response(blocks)
            if made_call:
                c = out[day]
                c["calls"] += 1
                c["pre_text"] += pre_text
                c["prefix"] += prefix
                c["leaks_tx"] += leaked
    logs = glob.glob(str(Path.home() / ".swarm-ai" / "logs" / "backend-daemon.log*"))
    for log in logs:
        try:
            with open(log, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    m = _LOG_LEAK_RE.match(line)
                    if m and m.group(1) >= since:
                        out[m.group(1)]["leaks_log"] += 1
        except OSError:
            continue
    return dict(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    rows = daily_metrics(args.days)
    print(f"{'date':10s} {'calls':>6s} {'pre_text%':>9s} {'leaks':>5s} {'prefix':>6s} {'glitch%':>7s}")
    for day in sorted(rows):
        c = rows[day]
        calls = c["calls"]
        # Logs survive transcript cleaning but rotate; transcripts keep old
        # days but lose cleaned leaks — take the larger count per day.
        leaks = max(c["leaks_log"], c["leaks_tx"])
        if not calls and not leaks:
            continue
        pre = 100 * c["pre_text"] / calls if calls else 0.0
        glitch = 100 * (leaks + c["prefix"]) / calls if calls else 0.0
        print(f"{day:10s} {calls:6d} {pre:8.1f}% {leaks:5d} {c['prefix']:6d} {glitch:6.2f}%")


if __name__ == "__main__":
    main()
