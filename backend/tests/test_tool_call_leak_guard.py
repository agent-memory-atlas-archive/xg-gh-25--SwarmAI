"""Tests for tool-call XML leak detection + orchestrator guard.

What is tested
--------------
1. ``detect_tool_call_leak`` (pure fn) — the double-condition matcher that
   distinguishes a real leak (``call`` line + line-start ``<invoke name=``) from
   prose that merely discusses the syntax inline. Table-driven, including the
   exact shapes observed in the messages DB on 2026-06-24.
2. The StreamingOrchestrator TextBlock guard — a leaked text block is NOT
   appended/yielded as assistant content, ``kill()`` is awaited, and a
   RuntimeError matching a retriable pattern is raised (→ send() --resume retry).

Key properties / invariants
----------------------------
- INV1: every DB-confirmed leak shape (call+invoke) → True
- INV2: inline-discussion + fenced-code-block mention → False (false-positive
  safety on the hottest path — every assistant text block)
- INV3: a detected leak is retriable (``_is_retriable_error`` recognizes the
  raised message) so the existing retry loop resumes the turn
- INV4: the guard fires INSIDE the TextBlock branch, before persist — the
  leaked block never reaches a yielded ``assistant`` event
"""

from __future__ import annotations

import asyncio
import types

import pytest

import json
from pathlib import Path

from core.session_utils import (
    detect_tool_call_leak,
    strip_tool_call_leak,
    _is_retriable_error,
)


# ── 1. Pure detector — table-driven ────────────────────────────────────────

# Real leak shapes — RAW <invoke> body in text (the durable harm). Detection
# keys on the BODY (<invoke name="X"> + <parameter / </invoke>), NOT the optional
# "call" prefix, so leaks without "call", with CRLF, or appearing late all match.
LEAK_CASES = [
    # Classic harness shape with a "call" line (DB rowid 204014/203549 shape)
    'some text\n\ncall\n<invoke name="Bash">\n<parameter name="command">cd /x</parameter>',
    # Skill invocation variant
    'output:\n\ncall\n<invoke name="Skill">\n<parameter name="skill">foo</parameter>',
    # Leak at the very start of the block
    'call\n<invoke name="Bash">\n<parameter name="command">ls</parameter>',
    # NO "call" prefix at all (the 8th DB case + future variants) — MUST match
    '<invoke name="Bash">\n<parameter name="command">ls</parameter>',
    # CRLF line endings — must still match
    'text\r\ncall\r\n<invoke name="Bash">\r\n<parameter name="command">ls</parameter>',
    # Self-closing / empty invoke body
    'doing the thing now\n<invoke name="Read"></invoke>',
    # Leak AFTER 4000 chars (no scan-limit truncation) — MUST match
    "x" * 4100 + '\n<invoke name="Bash">\n<parameter name="command">ls</parameter>',
]

# Non-leak: prose / documentation discussing the syntax (must NOT trigger).
NON_LEAK_CASES = [
    # Inline backtick mention (the rowid 204050 shape that must be rejected)
    '看两张截图,我的回复每次都在 `<invoke name="Bash">` 那一刻停了',
    # Inline mention mid-sentence, backtick-wrapped
    'The harness emits `<invoke name="Bash">` as the tool-call format.',
    # FENCED code block documenting the syntax — the critical false-positive
    # the first design missed. A meta-heavy turn explaining THIS bug.
    'Example of the leak:\n```\ncall\n<invoke name="Bash">\n<parameter name="command">x</parameter>\n```\nThat is what we guard against.',
    # Fenced block WITHOUT a language tag, full body inside
    '```\n<invoke name="Skill">\n<parameter name="skill">foo</parameter>\n</invoke>\n```',
    # Self-explanation referencing the shape but backtick-wrapped
    'My previous reply stopped at `<invoke name="Bash">` — that was a leak.',
    # The word "call" as its own line but NO <invoke body follows
    'call\nthe function and see what happens',
    # Mentions <invoke but never a real body (no <parameter, no close)
    'the <invoke tag is interesting to discuss in the abstract',
    # Different casing — harness emits lowercase only; this is prose, not a leak
    'Prose: <INVOKE name="Bash"><PARAMETER name="command">ls</PARAMETER>',
    # Empty / trivial
    '',
    'just a normal assistant reply with no tool syntax at all',
]


@pytest.mark.parametrize("text", LEAK_CASES)
def test_detector_flags_real_leaks(text):
    """INV1: every raw-body leak shape is detected (with/without call prefix,
    CRLF, late in block, case-variant)."""
    assert detect_tool_call_leak(text) is True


@pytest.mark.parametrize("text", NON_LEAK_CASES)
def test_detector_ignores_discussion(text):
    """INV2: prose mentioning the syntax inline / in fenced code is NOT flagged
    (false-positive safety on the hottest path)."""
    assert detect_tool_call_leak(text) is False


def test_detector_handles_large_text_without_truncation():
    """No scan-limit truncation: a leak anywhere in a large block is detected;
    a huge clean block returns False (and the fast-path '<invoke' check keeps
    it cheap)."""
    big_leak = "x" * 100_000 + '\n<invoke name="Bash">\n<parameter name="command">ls</parameter>'
    assert detect_tool_call_leak(big_leak) is True
    big_clean = "z" * 500_000
    assert detect_tool_call_leak(big_clean) is False


def test_detected_leak_is_retriable():
    """INV3: the RuntimeError message the guard raises is recognized as
    retriable, so send() routes it to the --resume retry path."""
    assert _is_retriable_error("Tool-call XML leaked into text channel (session_id=x)") is True


# ── 1b. strip_tool_call_leak — the WRITE-side cleaner ───────────────────────
#
# Difference from the detector: it must remove the TRUNCATED residue a mid-stream
# kill persists (<invoke name="Bash"> with NO following <parameter/</invoke>),
# AND it must preserve legitimate fenced/inline references byte-for-byte
# (per-MATCH, not per-line — the IMPROVEMENT.md 2026-08-31 false-negative class).

# Raw leaks the cleaner MUST remove (incl. the truncated persisted shape).
STRIP_LEAK_CASES = [
    # Truncated persisted shape — the dominant data.db form (kill mid-stream)
    'court\n<invoke name="Bash">',
    'ToDo bar 都是红色、一致。\n\ncourt\n<invoke name="Bash">',
    'court\n<invoke name="Edit">\n\ncourt替换:',
    # Complete body — removed whole
    'analysis\ncall\n<invoke name="Bash">\n<parameter name="command">ls</parameter>',
    # Self-closing
    'doing the thing\n<invoke name="Read"></invoke>',
    # Leak at the very start
    '<invoke name="Bash">\n<parameter name="command">cd /x</parameter>',
]

# Legitimate references the cleaner MUST preserve byte-for-byte (all in code spans).
STRIP_PRESERVE_CASES = [
    '看两张截图,我的回复每次都在 `<invoke name="Bash">` 那一刻停了',
    'The harness emits `<invoke name="Bash">` as the tool-call format.',
    'Example:\n```\ncall\n<invoke name="Bash">\n<parameter name="command">x</parameter>\n```\nguarded.',
    '```\n<invoke name="Skill">\n<parameter name="skill">foo</parameter>\n</invoke>\n```',
    'My reply stopped at `<invoke name="Bash">` — that was a leak.',
    'just a normal assistant reply with no tool syntax at all',
    '',
]


@pytest.mark.parametrize("text", STRIP_LEAK_CASES)
def test_strip_removes_raw_leak(text):
    """A raw leak fragment (incl. the truncated persisted shape) is removed, and
    the result no longer contains a <invoke name= body outside code spans."""
    cleaned = strip_tool_call_leak(text)
    assert "<invoke name=" not in cleaned
    assert cleaned != text  # something was actually stripped


@pytest.mark.parametrize("text", STRIP_PRESERVE_CASES)
def test_strip_preserves_legit_references(text):
    """A fenced/inline reference to the syntax is preserved BYTE-FOR-BYTE — 0
    false-strip (the RP42 orthogonal signal + per-MATCH, not per-line)."""
    assert strip_tool_call_leak(text) == text


def test_strip_per_match_not_per_line():
    """The decisive per-MATCH case: a text block carrying BOTH a legitimate inline
    reference AND a raw leak keeps the reference and strips ONLY the raw leak. A
    per-line grep -v exclusion would drop the whole line and lose the reference
    (IMPROVEMENT.md 2026-08-31 run_de417612)."""
    text = 'As I said `<invoke name="Bash">` is the format.\n\ncourt\n<invoke name="Edit">\n\ncourt done'
    cleaned = strip_tool_call_leak(text)
    # legit inline reference preserved
    assert '`<invoke name="Bash">`' in cleaned
    # raw leak removed
    assert '<invoke name="Edit">' not in cleaned


def test_strip_is_idempotent():
    """Cleaning already-clean text (or already-cleaned text) is a no-op."""
    once = strip_tool_call_leak('court\n<invoke name="Bash">\n\ntext')
    assert strip_tool_call_leak(once) == once


def test_strip_against_real_corpus():
    """Ground-truth double-direction: against the real data.db corpus, every
    robust-RAW sample has its <invoke body removed, every robust-FENCED sample is
    preserved byte-for-byte (0 false-strip, 0 miss). The corpus 'label' field is
    NOT trusted — it is re-derived here with the robust predicate (restore \\n
    escaping, mask code spans, then a residual bare <invoke => RAW)."""
    corpus_path = Path(
        "/Users/gawan/.swarm-ai/SwarmWS/Projects/SwarmAI/.artifacts/"
        "leak-feedback-corpus/corpus.json"
    )
    if not corpus_path.exists():
        pytest.skip("leak-feedback corpus not present (workspace-local artifact)")
    rows = json.loads(corpus_path.read_text())

    import re as _re
    _fence = _re.compile(r"```.*?```", _re.DOTALL)
    _inline = _re.compile(r"`[^`]*`")

    def robust_is_raw(text: str) -> bool:
        if not text or "<invoke" not in text:
            return False
        norm = text.replace("\\n", "\n").replace("\\t", "\t")
        residual = _inline.sub("", _fence.sub("", norm))
        return "<invoke" in residual

    raw_total = raw_cleaned = fenced_total = fenced_preserved = 0
    for row in rows:
        text = row.get("text", "")
        if "<invoke" not in text:
            continue
        if robust_is_raw(text):
            raw_total += 1
            if "<invoke name=" not in strip_tool_call_leak(text):
                raw_cleaned += 1
        else:
            fenced_total += 1
            if strip_tool_call_leak(text) == text:
                fenced_preserved += 1

    assert raw_total > 0, "corpus has no RAW samples — predicate or data drift"
    assert raw_cleaned == raw_total, f"RAW not fully cleaned: {raw_cleaned}/{raw_total}"
    assert fenced_preserved == fenced_total, (
        f"FENCED false-stripped: {fenced_preserved}/{fenced_total} preserved"
    )


# ── 1b. Lossless masking (bug 2a) + persist==yield (bug 2d) ──────────────────
#
# These guard the run_719886ee refactor (root ①): the persist-side strip is the
# SINGLE write chokepoint (Gate-1 confirmed memory_extractor/summarization inherit
# it), so it is KEPT — but it must be LOSSLESS and must not fork UI vs DB.


def test_strip_lossless_on_backtick_fence_and_leak():
    """Bug 2a: a lone backtick must NOT pair across a fence sentinel and destroy
    a code block or leave a NUL. Input mixes a lone backtick, a fenced code
    block, a raw leak, and another lone backtick. The code block must survive
    byte-for-byte and NO \\x00 may remain in the output.

    Mutation proof: revert _mask_doc_contexts to the two-pass fence-then-inline
    form → this test goes RED (code block dropped + \\x00 residue)."""
    code_body = "important_code = 1"
    text = (
        "Don`t panic here is a raw leak <invoke name=\"Bash\"> and a block\n"
        "```python\n" + code_body + "\n```\n"
        "then that`s it"
    )
    out = strip_tool_call_leak(text)
    # The fenced code block must be preserved verbatim.
    assert code_body in out, f"code block lost: {out!r}"
    assert "```python" in out, f"fence lost: {out!r}"
    # No NUL sentinel may leak into the output.
    assert "\x00" not in out, f"NUL residue in output: {out!r}"
    # The raw leak IS removed (chokepoint still cleans).
    assert '<invoke name="Bash">' not in out, f"leak not stripped: {out!r}"


def test_strip_lossless_preserves_many_inline_and_fence_spans():
    """Reinforce 2a: multiple inline-code spans with odd backtick counts around
    a fence must all round-trip. Mutation proof: two-pass mask → RED."""
    text = (
        "Use `a` and `b` and a stray ` tick, then\n"
        "```js\nconst x = `template`;\n```\n"
        "and `c` after. Leak: <invoke name=\"X\">"
    )
    out = strip_tool_call_leak(text)
    assert "\x00" not in out
    assert "const x = `template`;" in out, f"fenced template lost: {out!r}"
    assert "`a`" in out and "`b`" in out and "`c`" in out
    assert '<invoke name="X">' not in out


def test_mask_doc_contexts_round_trips_lone_backtick_with_fence():
    """Directly exercise the mask/restore round-trip (the 2a locus). A lone
    backtick + a fence must restore the fence span verbatim and leave no NUL.
    Mutation proof: two-pass mask → the fence span is corrupted → RED."""
    from core.session_utils import _mask_doc_contexts, _restore_doc_contexts

    text = "a ` lone tick\n```py\nZZZ=9\n```\n tail `x`"
    masked, spans = _mask_doc_contexts(text)
    restored = _restore_doc_contexts(masked, spans)
    assert "\x00" not in restored, f"NUL in restored: {restored!r}"
    assert "ZZZ=9" in restored, f"fence body lost in round-trip: {restored!r}"
    assert "```py" in restored


def test_persist_strip_returns_cleaned_blocks_no_fork():
    """Bug 2d (contract half): the persist-side clean must EXPOSE the cleaned
    blocks so the caller can write them back into event['content'] — persist and
    yield must carry the SAME bytes (no UI≠DB fork).

    This asserts the mechanism Gate-1 required: _clean_blocks_for_persist is the
    single clean that returns the cleaned list. Mutation proof: if the helper
    returns the original blocks unchanged (fork reintroduced), the leak remains
    in the 'persisted' copy → RED."""
    from core.session_router import _clean_blocks_for_persist

    blocks = [
        {"type": "text", "text": "hi <invoke name=\"Bash\"> leak"},
        {"type": "text", "text": "clean line"},
    ]
    cleaned = _clean_blocks_for_persist(blocks)
    # cleaned is a NEW list with the leak removed from the first block.
    assert '<invoke name="Bash">' not in cleaned[0]["text"], cleaned
    assert cleaned[1]["text"] == "clean line"
    # The SAME cleaned list is what both persist and yield must use — the caller
    # writes it back to event['content']. Verify it is a usable blocks list.
    assert all(isinstance(b, dict) and "text" in b for b in cleaned)


def test_persist_strip_preserves_non_text_and_clean_blocks():
    """2d contract: non-text blocks and already-clean text pass through
    unchanged (clean must not corrupt clean content)."""
    from core.session_router import _clean_blocks_for_persist

    blocks = [
        {"type": "text", "text": "just discussing it, no leak"},
        {"type": "image", "source": {"x": 1}},
        {"type": "text", "text": "code: ```py\nk=1\n``` done"},
    ]
    cleaned = _clean_blocks_for_persist(blocks)
    assert cleaned[0]["text"] == "just discussing it, no leak"
    assert cleaned[1] == {"type": "image", "source": {"x": 1}}
    assert "k=1" in cleaned[2]["text"] and "\x00" not in cleaned[2]["text"]


def test_persist_bytes_equal_yield_bytes_e2e():
    """Layer-4 cross-boundary E2E (bug 2d seam = persist-writer bytes ==
    stream-yield bytes). Drives the REAL SessionRouter._persist_assistant_blocks
    (the actual write path — only the LEAF db.messages.put is mocked to capture
    what hit the DB; the strip + return-contract are NOT mocked).

    This test replicates the EXACT call-site pattern the 3 stream loops use:
        event = {..., "content": <original>}
        event["content"] = await self._persist_assistant_blocks(..., event["content"], ...)
        yield event                      # the UI sees event["content"]
    and asserts the YIELDED event["content"] (what the UI gets) == the content the
    DB received. This is the real 2d seam — NOT a tautology on the method's own
    return value.

    Two mutation proofs this catches (both reproduced in the DELIVER adversarial
    pass → RED):
      (a) revert the contract to `return True` (bool) → the write-back sets
          event["content"]=True while the DB got the cleaned list → yielded != DB.
      (b) delete the `event["content"] = ` assignment at the call site (keep the
          original) → event["content"] still holds the raw leak while the DB got
          the cleaned list → yielded != DB. (The prior version of this test asserted
          only the method's return and MISSED (b) — red-team finding, now fixed.)
    """
    import asyncio
    from unittest.mock import patch
    from core.session_router import SessionRouter

    captured = {}

    async def _fake_put(row):
        # Deep-ish copy so a later in-place mutation of the blocks can't retro-
        # change what we recorded as "what the DB received".
        captured["content"] = [dict(b) for b in row["content"]]

    fake_db = types.SimpleNamespace(messages=types.SimpleNamespace(put=_fake_put))

    router = SessionRouter.__new__(SessionRouter)  # no __init__ — pure method call

    # The event object exactly as the stream loop holds it, with a raw leak.
    event = {
        "type": "assistant",
        "content": [
            {"type": "text", "text": "answer <invoke name=\"Bash\"> leaked here"},
            {"type": "text", "text": "and a clean trailing line"},
        ],
    }

    async def _run():
        with patch("database.db", fake_db):
            # REPLICATE the real call-site write-back (session_router.py:3544/3790/3821).
            event["content"] = await router._persist_assistant_blocks(
                "sess-e2e", event["content"], "test-model", client_id="cid",
            )
            # `yield event` happens here in production — the UI reads event["content"].

    asyncio.run(_run())

    # DB actually received cleaned content (leak gone).
    assert captured.get("content") is not None, "db.put was never called"
    assert '<invoke name="Bash">' not in captured["content"][0]["text"]
    # THE SEAM: what the UI gets (yielded event["content"]) == what the DB got.
    # Catches both (a) bool-return reversion and (b) a deleted write-back.
    assert event["content"] == captured["content"], (
        "yielded event['content'] != persisted DB content — the 2d fork is back"
    )
    assert isinstance(event["content"], list), "event['content'] must stay a blocks list"
    assert '<invoke name="Bash">' not in event["content"][0]["text"]


# ── 2. Orchestrator guard (integration) ─────────────────────────────────────


def _make_assistant_message(text, model="test-model"):
    """Build a REAL claude_agent_sdk.AssistantMessage so the orchestrator's
    isinstance(block, TextBlock) / isinstance(message, AssistantMessage) checks
    match — a fake duck-typed object would be silently ignored and the test
    would pass for the wrong reason (the zombie detector, not the leak guard)."""
    from claude_agent_sdk import AssistantMessage, TextBlock

    return AssistantMessage(content=[TextBlock(text=text)], model=model)


def _make_result_message():
    """A clean end-of-turn ResultMessage so the normal (non-zombie) result path
    runs after a clean text block."""
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=10,
        duration_api_ms=10,
        is_error=False,
        num_turns=1,
        session_id="sdk-test",
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 5},
        total_cost_usd=0.0,
    )


async def _drive(orchestrator, messages):
    """Run _read_formatted_response against a stream of messages and collect
    yielded events. Returns (events, raised_exc)."""

    async def _stream():
        for m in messages:
            yield m

    class _Client:
        def receive_response(self):
            return _stream()

    orchestrator._parent._client = _Client()

    events = []
    raised = None
    try:
        async for ev in orchestrator._read_formatted_response():
            events.append(ev)
    except RuntimeError as e:
        raised = e
    return events, raised


def _make_orchestrator():
    """Build a StreamingOrchestrator with a minimal stubbed parent SessionUnit."""
    from core.streaming_orchestrator import StreamingOrchestrator

    from core.session_unit import SessionState

    parent = types.SimpleNamespace()
    parent.session_id = "sess-test"
    parent._client = None
    parent._sdk_session_id = "sdk-test"  # is_resume=True path
    # State machine stubs — the no-ResultMessage stream-end path reads .state
    # and calls _transition()/last_used (clean-text test exercises this).
    parent.state = SessionState.STREAMING
    parent.last_used = 0.0

    def _transition(new_state):
        parent.state = new_state

    parent._transition = _transition
    parent._content_emitted = False
    parent._streaming_start_time = None
    parent._interrupted = False
    parent._active_agent_tools = {}
    parent._open_tool_uses = {}
    parent._pending_file_changes = {}
    parent._tool_hang_interrupted = False
    parent._tool_hang_interrupt_at = None
    parent._tool_hang_episodes = 0
    parent._model_name = "test-model"
    parent._configured_mcps = []
    parent._mcp_health_checked = True
    parent._lifecycle_response_count = 0
    parent._retry_count = 0
    parent.pid = None
    parent._peak_tree_rss_bytes = 0
    parent._interrupted = False
    # Normal result-path stubs (clean-text test reaches ResultMessage handling)
    from core.compaction_guard import EscalationLevel

    parent._compaction_guard = types.SimpleNamespace(
        record_tool_call=lambda *a, **k: None,
        check=lambda: EscalationLevel.MONITORING,
    )
    parent._open_tool_uses = {}
    parent._active_agent_tools = {}
    parent._emit_post_stream_metadata = lambda *a, **k: iter(())

    async def _noop_async(*a, **k):
        return None

    parent._check_rss_and_proactive_restart = _noop_async
    # (_check_context_soft_compact stub removed — method deleted run_2b1957f8)

    # Health sensor stub
    parent._health_sensor = types.SimpleNamespace(
        record_activity=lambda: None,
        record_turn=lambda **k: None,
    )
    parent._last_event_time = 0.0
    parent._maybe_build_elapsed_heartbeat = lambda: None
    parent._compute_message_timeout = lambda: 300.0
    # orchestrator's first-message timeout now calls _compute_init_timeout
    # (run_4b74b764, Part B) — mock parent must provide it (fresh-session 180s).
    parent._compute_init_timeout = lambda: 180.0

    # kill() must be awaitable + record invocation
    kill_calls = {"n": 0}

    async def _kill():
        kill_calls["n"] += 1

    parent.kill = _kill
    parent._kill_calls = kill_calls

    orch = StreamingOrchestrator(parent)
    return orch


def test_orchestrator_blocks_leaked_block_and_kills():
    """INV4: a leaked TextBlock is not yielded as assistant content; kill() is
    awaited and a retriable RuntimeError is raised."""
    orch = _make_orchestrator()
    orch._parent._streaming_start_time = 0.0
    leak = 'analysis text\n\ncall\n<invoke name="Bash">\n<parameter name="command">cd /x</parameter>'
    msg = _make_assistant_message(leak)

    events, raised = asyncio.run(_drive(orch, [msg]))

    # kill was invoked
    assert orch._parent._kill_calls["n"] == 1
    # a retriable RuntimeError was raised — and specifically the LEAK guard's
    # error, not the unrelated zombie detector (proves the right path fired)
    assert raised is not None
    assert "Tool-call XML leaked into text channel" in str(raised)
    assert _is_retriable_error(str(raised)) is True
    # the leaked XML never reached a yielded assistant content event
    for ev in events:
        if ev.get("type") == "assistant":
            for block in ev.get("content", []):
                assert "<invoke name=" not in block.get("text", "")


def test_orchestrator_passes_clean_text_block():
    """A normal text block (even one mentioning <invoke name= inline) is
    yielded as assistant content and does NOT kill the session."""
    orch = _make_orchestrator()
    orch._parent._streaming_start_time = 0.0
    clean = "The harness emits <invoke name=\"Bash\"> as the tool-call format inline."
    msg = _make_assistant_message(clean)

    # Include a trailing ResultMessage so the turn ends via the normal result
    # path (not the zombie detector, which is unrelated to the leak guard).
    events, raised = asyncio.run(_drive(orch, [msg, _make_result_message()]))

    assert orch._parent._kill_calls["n"] == 0
    assert raised is None
    # the clean text was yielded as assistant content
    assert any(
        ev.get("type") == "assistant"
        and any(b.get("text") == clean for b in ev.get("content", []))
        for ev in events
    )


def test_orchestrator_does_not_fire_when_real_tool_use_present():
    """Third signal: if the message ALSO contains a real ToolUseBlock, the turn
    is legitimate (the model DID invoke a tool) — the guard must NOT kill. But
    the leak-feedback fix (run_da39669c) additionally requires the raw <invoke>
    text be STRIPPED from the persisted content, so it cannot re-seed the loop on
    resume (the mixed-message gap, data.db session a0f04b00)."""
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

    orch = _make_orchestrator()
    orch._parent._streaming_start_time = 0.0
    # Text that WOULD match the body matcher on its own ...
    text_with_body = 'Here is what I ran:\n<invoke name="Bash">\n<parameter name="command">ls</parameter>'
    msg = AssistantMessage(
        content=[
            TextBlock(text=text_with_body),
            ToolUseBlock(id="toolu_1", name="Bash", input={"command": "ls"}),
        ],
        model="test-model",
    )

    events, raised = asyncio.run(_drive(orch, [msg, _make_result_message()]))

    # ... because a REAL tool_use is present, the guard must NOT kill (killing
    # would abort legitimate in-flight tool execution).
    assert orch._parent._kill_calls["n"] == 0
    assert raised is None
    # ... AND the raw leak text must be stripped from every yielded assistant
    # content block (the mixed-message persist gap this fix closes).
    for ev in events:
        if ev.get("type") == "assistant":
            for block in ev.get("content", []):
                assert "<invoke name=" not in block.get("text", "")


def test_orchestrator_strips_leak_but_keeps_prose_in_mixed_message():
    """The mixed-message strip is per-MATCH: legitimate text around the leak is
    preserved while only the raw <invoke> body is removed — the turn's real
    content survives, the leak does not."""
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

    orch = _make_orchestrator()
    orch._parent._streaming_start_time = 0.0
    mixed = 'Rendering now.\n<invoke name="Edit">\n<parameter name="x">y</parameter>'
    msg = AssistantMessage(
        content=[
            TextBlock(text=mixed),
            ToolUseBlock(id="toolu_2", name="Edit", input={"x": "y"}),
        ],
        model="test-model",
    )

    events, raised = asyncio.run(_drive(orch, [msg, _make_result_message()]))

    assert raised is None
    assert orch._parent._kill_calls["n"] == 0
    # The real prose survived; the leak body did not.
    asst_texts = [
        b.get("text", "")
        for ev in events
        if ev.get("type") == "assistant"
        for b in ev.get("content", [])
    ]
    joined = "\n".join(asst_texts)
    assert "Rendering now." in joined
    assert "<invoke name=" not in joined


# ── 4. user-side persist strip (run_67250d95) ──────────────────────────────
# The ONLY path a RAW <invoke> body persists to data.db is a USER message:
# assistant-persist funnels through _clean_blocks_for_persist, but user-persist
# did not. Two user-content write doors (R27 + Gate-1): session_router's
# db.messages.put (production) and session_pending._payload_json (the raw-INSERT
# second door). Both must strip. Verified harm: data.db had 2 raw rows, both
# role=user — a user re-fed a prior turn's on-screen leak remnant.

def _decode_payload_text(payload: str) -> str:
    """Reconstruct the human-readable text from a _payload_json result.

    MUST decode (not substring-match the raw JSON): dumps_json escapes `"` →
    `\\"`, so a raw `<invoke name="Bash">` in the text serializes to
    `<invoke name=\\"Bash\\">` and a naive `'<invoke name="Bash">' in payload`
    is ALWAYS False — a vacuous assertion that passes with OR without the strip
    (RP47 theater, caught at BUILD). Decoding back to the real text restores the
    bytes detect_tool_call_leak actually judges."""
    import json
    blocks = json.loads(payload)
    return "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict))


def test_payload_json_strips_user_message_leak():
    """session_pending._payload_json (the 2nd write door, raw INSERT) must strip
    a raw <invoke> body from a user_message. Mutation proof: without the strip,
    the DECODED payload text contains the raw <invoke> → detect fires → RED."""
    from core.session_pending import _payload_json
    leak = 'why does this keep happening \'core\n<invoke name="Bash">\n<parameter name="command">ls</parameter>'
    text = _decode_payload_text(_payload_json(leak, None))
    assert '<invoke name="Bash">' not in text, text
    assert detect_tool_call_leak(text) is False, text


def test_payload_json_strips_user_content_leak():
    """Same door, content (multimodal) path: a raw <invoke> body in a content
    block must be stripped (judged on the DECODED text, not the escaped JSON)."""
    from core.session_pending import _payload_json
    content = [{"type": "text", "text": 'look:\n<invoke name="Bash">\n<parameter name="command">rm</parameter>'}]
    text = _decode_payload_text(_payload_json(None, content))
    assert '<invoke name="Bash">' not in text, text
    assert detect_tool_call_leak(text) is False, text


def test_payload_json_preserves_clean_and_fenced():
    """No over-reach: clean text + a fenced <invoke discussion survive intact."""
    from core.session_pending import _payload_json
    # clean
    assert "hello world" in _decode_payload_text(_payload_json("hello world", None))
    # fenced discussion must be preserved (strip only removes RAW leaks)
    fenced = 'the leak looks like ```\n<invoke name="Bash">\n```'
    text = _decode_payload_text(_payload_json(fenced, None))
    assert "<invoke" in text, "fenced discussion wrongly stripped: " + text


def test_session_router_user_persist_calls_clean():
    """session_router's user-persist path must pass user_content through
    _clean_blocks_for_persist before db.messages.put. Asserts the call-site wiring
    by source inspection (the production db.messages.put at the user-persist guard
    is fed a cleaned list). Mutation proof: remove the _clean_blocks_for_persist
    call from the user-persist block → this assertion RED."""
    import inspect
    from core import session_router
    src = inspect.getsource(session_router)
    # The user-persist block (role:"user") must clean user_content. Narrow to the
    # region around the user put and assert the clean call is present there.
    idx = src.find('"role": "user"')
    assert idx != -1, "user-persist put not found"
    window = src[max(0, idx - 800):idx]
    assert "_clean_blocks_for_persist(user_content)" in window, (
        "user_content is persisted WITHOUT _clean_blocks_for_persist — the raw-leak "
        "user-persist gap (run_67250d95) is open"
    )
