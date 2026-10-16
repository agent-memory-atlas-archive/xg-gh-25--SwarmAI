"""Tests for the repeated-leak poison restart.

What is tested
--------------
1. ``core.leak_transcript`` — locating the CLI transcript for an SDK session id
   and stripping leak text from it in place (real files in tmp_path).
2. The orchestrator trigger — the 2nd leak in one SDK session raises the
   restart marker, but only on the primary send() stream, only without a real
   tool call in flight, and never after a user Stop.
3. ``RetryManager._handle_leak_poison_restart`` on a REAL SessionUnit, mocking
   only the SDK boundary (_crash_to_cold_async, _spawn, stream_query).

Key invariants
--------------
- INV1: only assistant text blocks with a line-start raw ``‹invoke`` change;
  fenced examples, tool results and user messages are byte-identical.
- INV2: a block that was only a leak keeps a non-empty filler (the API rejects
  empty text blocks in history).
- INV3: the restart kills BEFORE cleaning (the live CLI owns the file), resumes
  the SAME sdk session id, sends the continuation prompt (not the user's
  message), and runs at most once per user message.
"""
from __future__ import annotations

from tests._tool_markup import tc
import asyncio
import json

import pytest

from core.leak_transcript import EMPTY_FILLER, clean_transcript_leaks, find_transcript
from core.session_utils import LEAK_RESTART_MARKER
from tests.test_tool_call_leak_guard import (
    _DEADEND_LEAK,
    _drive,
    _make_assistant_message,
    _make_orchestrator,
    _make_result_message,
    _make_tool_use_message,
)

SID = "0b5f7b2d-1111-2222-3333-444455556666"


def _asst(text, msg_id="m1"):
    return {"type": "assistant", "uuid": msg_id,
            "message": {"id": msg_id, "role": "assistant",
                        "content": [{"type": "text", "text": text}]}}


def _write_transcript(tmp_path, monkeypatch, records, tail=""):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    d = tmp_path / "projects" / "-Users-x-proj"
    d.mkdir(parents=True)
    p = d / f"{SID}.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records) + tail)
    return p


def _texts(path):
    out = []
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            out.append(("torn", line))
            continue
        for b in (rec.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append((rec["type"], b["text"]))
    return out


# ── 1. transcript cleaner ──────────────────────────────────────────────────

def test_find_transcript_by_sid(tmp_path, monkeypatch):
    p = _write_transcript(tmp_path, monkeypatch, [_asst("hi")])
    assert find_transcript(SID) == p
    assert find_transcript("ffffffff-0000-0000-0000-000000000000") is None


@pytest.mark.parametrize("bad", ["", None, "*", "../etc/passwd", "a/b", "x" * 10])
def test_find_transcript_rejects_non_uuid(tmp_path, monkeypatch, bad):
    _write_transcript(tmp_path, monkeypatch, [_asst("hi")])
    assert find_transcript(bad) is None


def test_clean_strips_assistant_leak_only(tmp_path, monkeypatch):
    fenced = tc('Example:\n```\ncount\n‹invoke name="Bash">\n‹parameter name="command">x‹/parameter>\n```\n')
    user_paste = {"type": "user", "uuid": "u1",
                  "message": {"role": "user", "content": _DEADEND_LEAK}}
    tool_result = {"type": "user", "uuid": "u2", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": _DEADEND_LEAK}]}}
    p = _write_transcript(tmp_path, monkeypatch, [
        _asst(_DEADEND_LEAK, "m1"),
        _asst(tc('count\n‹invoke name="Read">\n‹parameter name="file_path">/x‹/parameter>\n‹/invoke>'), "m2"),
        _asst(fenced, "m3"),
        user_paste,
        tool_result,
    ])
    before = p.read_text().splitlines()

    assert clean_transcript_leaks(p) == 2

    after = p.read_text().splitlines()
    assert json.loads(after[0])["message"]["content"][0]["text"] == "跑测试(GREEN 验证)。\n\n"
    assert json.loads(after[1])["message"]["content"][0]["text"] == EMPTY_FILLER
    assert after[2:] == before[2:], "fenced example, user text, tool_result unchanged"
    assert clean_transcript_leaks(p) == 0  # idempotent


def test_clean_keeps_torn_last_line_and_no_write_when_clean(tmp_path, monkeypatch):
    p = _write_transcript(tmp_path, monkeypatch, [_asst(_DEADEND_LEAK)],
                          tail='{"type":"assistant","message":{"content":[{"type":"te')
    assert clean_transcript_leaks(p) == 1
    assert p.read_text().endswith('{"type":"te')  # torn tail preserved

    clean = tmp_path / "clean.jsonl"
    clean.write_text(json.dumps(_asst("no leak here")) + "\n")
    mtime = clean.stat().st_mtime_ns
    assert clean_transcript_leaks(clean) == 0
    assert clean.stat().st_mtime_ns == mtime


def test_clean_is_fail_soft(tmp_path):
    assert clean_transcript_leaks(tmp_path / "missing.jsonl") == 0


# ── 2. orchestrator trigger ────────────────────────────────────────────────

def _orch(eligible=True, prior_leaks=1):
    orch = _make_orchestrator()
    orch._parent._streaming_start_time = 0.0
    orch._parent._leak_restart_eligible = eligible
    orch._parent._leak_sid = orch._parent._sdk_session_id
    orch._parent._leak_count = prior_leaks
    return orch


def _leak_round():
    return [_make_assistant_message(_DEADEND_LEAK), _make_result_message()]


def test_second_leak_raises_restart_after_yielding_cleaned_text():
    orch = _orch()
    events, raised = asyncio.run(_drive(orch, _leak_round()))
    assert raised is not None and LEAK_RESTART_MARKER in str(raised)
    assert orch._parent._leak_restart_eligible is False  # one-shot
    assert orch._parent._client.queries == []  # no in-process retry first
    texts = [b["text"] for ev in events if ev.get("type") == "assistant"
             for b in ev["content"]]
    assert texts == ["跑测试(GREEN 验证)。\n\n"], "prose shown, leak not"
    assert not [ev for ev in events if ev.get("type") == "result"]


def test_first_leak_does_not_restart():
    orch = _orch(prior_leaks=0)
    events, raised = asyncio.run(_drive(
        orch, _leak_round(), followups=[[_make_tool_use_message(), _make_result_message()]],
    ))
    assert raised is None
    assert orch._parent._leak_count == 1
    assert len(orch._parent._client.queries) == 1  # in-process continuation


def test_new_sdk_session_resets_count():
    orch = _orch(prior_leaks=5)
    orch._parent._leak_sid = "some-older-session"
    events, raised = asyncio.run(_drive(
        orch, _leak_round(), followups=[[_make_tool_use_message(), _make_result_message()]],
    ))
    assert raised is None
    assert orch._parent._leak_count == 1


@pytest.mark.parametrize("setup", ["not_eligible", "user_stopped", "open_tool", "no_sid"])
def test_restart_gated(setup):
    orch = _orch()
    p = orch._parent
    if setup == "not_eligible":
        p._leak_restart_eligible = False
    elif setup == "user_stopped":
        p._user_stopped_current_turn = True
    elif setup == "open_tool":
        p._open_tool_uses = {"toolu_x": (0.0, "Bash")}
    elif setup == "no_sid":
        p._sdk_session_id = None
        p._leak_sid = None
    events, raised = asyncio.run(_drive(orch, _leak_round()))
    assert raised is None or LEAK_RESTART_MARKER not in str(raised)


def test_leak_with_real_tool_use_in_message_does_not_restart():
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

    orch = _orch()
    msg = AssistantMessage(content=[
        TextBlock(text=_DEADEND_LEAK),
        ToolUseBlock(id="toolu_1", name="Bash", input={"command": "ls"}),
    ], model="test-model")
    events, raised = asyncio.run(_drive(orch, [msg, _make_result_message()]))
    assert raised is None


# ── 3. restart handler on a real SessionUnit ───────────────────────────────

def _unit_with_boundary_mocks(calls, stream_events=(), stream_exc=None, spawn_exc=None):
    from core.session_unit import SessionState, SessionUnit

    u = SessionUnit(session_id="test-leak-restart", agent_id="default")
    u._sdk_session_id = SID
    u._leak_sid = SID
    u._leak_count = 2

    async def _crash(*a, clear_identity=False, **k):
        calls.append(("crash", clear_identity))
        u.state = SessionState.COLD
        if clear_identity:
            u._sdk_session_id = None

    async def _spawn(options, config=None):
        calls.append(("spawn", options.resume))
        if spawn_exc:
            raise spawn_exc
        u.state = SessionState.STREAMING

    async def _stream(query):
        calls.append(("query", query))
        for ev in stream_events:
            yield ev
        if stream_exc:
            raise stream_exc

    u._crash_to_cold_async = _crash
    u._spawn = _spawn
    u._streaming_orchestrator.stream_query = _stream
    return u


def _opts():
    from claude_agent_sdk import ClaudeAgentOptions

    return ClaudeAgentOptions()


async def _collect(agen):
    return [ev async for ev in agen]


async def test_restart_kills_cleans_resumes_and_continues(tmp_path, monkeypatch):
    from core.streaming_orchestrator import StreamingOrchestrator

    p = _write_transcript(tmp_path, monkeypatch, [_asst(_DEADEND_LEAK)])
    calls = []
    u = _unit_with_boundary_mocks(calls, stream_events=[{"type": "assistant", "content": []}])
    order = []
    real_clean = clean_transcript_leaks

    def _spy_clean(path):
        order.append(("clean", [c[0] for c in calls]))
        return real_clean(path)

    monkeypatch.setattr("core.leak_transcript.clean_transcript_leaks", _spy_clean)

    events = await _collect(u._retry_manager._handle_leak_poison_restart(_opts(), None))

    assert order == [("clean", ["crash"])], "kill must happen BEFORE the file is cleaned"
    assert calls[0] == ("crash", False), "identity kept for --resume"
    assert calls[1] == ("spawn", SID), "resumes the SAME sdk session"
    assert calls[2] == ("query", StreamingOrchestrator._LEAK_CONTINUATION_PROMPT)
    assert events[-1] == {"_recovered": True}
    assert u._leak_restart_done is True and u._leak_count == 0
    assert tc("‹invoke") not in p.read_text()


async def test_restart_without_transcript_still_resumes(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))  # no projects dir
    calls = []
    u = _unit_with_boundary_mocks(calls)
    events = await _collect(u._retry_manager._handle_leak_poison_restart(_opts(), None))
    assert [c[0] for c in calls] == ["crash", "spawn", "query"]
    assert events[-1] == {"_recovered": True}


async def test_restart_spawn_failure_aborts_with_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    calls = []
    u = _unit_with_boundary_mocks(calls, spawn_exc=RuntimeError("boom"))
    events = await _collect(u._retry_manager._handle_leak_poison_restart(_opts(), None))
    assert events[-1] == {"_abort": True}
    assert events[-2].get("type") == "error"
    assert ("crash", True) in calls  # poisoned identity dropped on give-up


async def test_restart_stream_failure_falls_through(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    calls = []
    u = _unit_with_boundary_mocks(calls, stream_exc=RuntimeError("Retriable SDK error: x"))
    events = await _collect(u._retry_manager._handle_leak_poison_restart(_opts(), None))
    assert "Retriable SDK error" in events[-1]["_fallthrough_error"]


def test_restart_marker_is_not_a_retriable_pattern():
    from core.session_utils import _is_retriable_error

    assert not _is_retriable_error(f"{LEAK_RESTART_MARKER} (session_id=x)")
