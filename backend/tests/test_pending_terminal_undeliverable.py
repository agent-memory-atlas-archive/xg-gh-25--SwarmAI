"""Permanent-error terminal-undeliverable drain tests (run_29959bcd).

ROOT FIX for the frequent-session-teardown engine: a PERMANENT SDK error (e.g. the
400 "unsupported countries" geo-block, which `_is_retriable_error` already classifies
non-retriable) used to be rolled back to pending on every drain → re-drained on the
next IDLE edge → the SAME 400 → rolled back → forever (poison_guard_recycle fires once
per re-drive as a downstream symptom, 764× over 26h on one real session).

The fix threads a `terminal: True` flag from the orchestrator's permanent-error branch
(which already KNOWS the error is non-retriable, having passed `_is_retriable_error`)
through the error event, to `_finalize_pending_delivery`, which treats a terminal error
as TERMINALLY-UNDELIVERABLE: mark_sent + loud log (NOT rolled back), cutting the
re-drive engine. This mirrors the existing degenerate-empty-payload guard
(session_router.py:2978) that already does mark_sent + loud log to avoid an identical
infinite drain loop.

These are STEERING #11 recovery-path tests — they FORCE the finalize decision to execute
against real SQLite (session_pending primitives), not assert-it-compiles.

Methodology: real SQLite + a MagicMock unit in IDLE, same `wired` pattern as
test_session_drain.py. The drain's run_conversation is stubbed to a capturing
async-generator that yields the exact error-event shape under test.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from database.sqlite import SQLiteDatabase
from core.session_router import SessionRouter
from core.session_unit import SessionState


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
async def wired(db_path: Path, monkeypatch):
    """Migrated DB + SessionRouter with session_pending pointed at the tmp DB."""
    db = SQLiteDatabase(db_path=db_path)
    await db.initialize()
    import database
    import core.session_pending as sp
    monkeypatch.setattr(database, "db", db, raising=False)
    monkeypatch.setattr(sp, "_db_path_override", str(db_path), raising=False)
    sp._SEQ_LOCKS.clear()

    router = SessionRouter(prompt_builder=MagicMock())
    yield router, sp
    task = router._drain_worker_task
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (Exception, BaseException):
            pass


def _make_idle_unit(session_id: str) -> MagicMock:
    unit = MagicMock()
    unit.session_id = session_id
    unit.agent_id = "agent-1"
    unit.is_alive = True
    unit.state = SessionState.IDLE
    unit.has_outstanding_tool_use = False
    unit._last_drained_seqs = []
    return unit


@pytest.mark.asyncio
async def test_drain_marks_sent_on_terminal_permanent_error(wired):
    """AC1: a PERMANENT error event (terminal=True) is terminally-undeliverable —
    the row is marked sent (NOT rolled back), so it is NEVER re-drained. This is
    what cuts the infinite re-drive engine.

    RED against pre-fix code: the old `else` branch rolled ANY error back, so the
    row would stay pending (count==1) → re-drive forever. GREEN: count==0."""
    router, sp = wired
    sid = "sess-terminal-perm"
    router._units[sid] = _make_idle_unit(sid)
    await sp.persist_pending(sid, user_message="geo-blocked message", content=None, agent_id="a")
    assert await sp.count_pending(sid) == 1

    def _permanent_error_run_conversation(**kwargs):
        async def _agen():
            # The orchestrator's permanent-error branch tags terminal=True on a
            # non-retriable error (400 unsupported-countries). It is ALSO yielded
            # to the user (code+message preserved) — surfaced, not silently dropped.
            yield {
                "type": "error",
                "code": "SDK_ERROR",
                "message": "Access to Anthropic models is not allowed from unsupported countries",
                "terminal": True,
            }
        return _agen()

    router.run_conversation = _permanent_error_run_conversation  # type: ignore[assignment]

    await router.drain_pending(sid)  # must not raise

    # Terminally-undeliverable: marked sent, NOT rolled back → no re-drive.
    assert await sp.count_pending(sid) == 0, (
        "terminal permanent error was rolled back to pending — the re-drive engine "
        "is NOT cut (this is the 764x-recycle bug)"
    )


@pytest.mark.asyncio
async def test_drain_marks_sent_on_terminal_error_followed_by_result(wired):
    """AC4 fidelity (Gate-2 LOW): the REAL orchestrator permanent branch yields the
    terminal error event AND a trailing `type:"result"` frame (streaming_orchestrator
    yields the error, then the turn completes with a result). The error-only shape in
    the first test lands via the `delivered_ok=False` arm; this shape lands via
    `delivered_ok=True` — so BOTH `saw_terminal` must survive the result and the
    finalize must STILL mark_sent, not treat the trailing result as a clean delivery
    that re-drives or mis-accounts. Guards the terminal-threading on the result arm:
    if the capture ever stopped carrying `terminal` through to the result-driven
    finalize, this goes RED (row rolled back / re-drivable)."""
    router, sp = wired
    sid = "sess-terminal-then-result"
    router._units[sid] = _make_idle_unit(sid)
    await sp.persist_pending(sid, user_message="geo-blocked, then result", content=None, agent_id="a")
    assert await sp.count_pending(sid) == 1

    def _terminal_then_result_run_conversation(**kwargs):
        async def _agen():
            # Mirror the real orchestrator non-retriable branch: error event (terminal)
            # THEN a result frame as the turn completes.
            yield {
                "type": "error",
                "code": "SDK_ERROR",
                "message": "Access to Anthropic models is not allowed from unsupported countries",
                "terminal": True,
            }
            yield {"type": "result", "subtype": "sdk_error"}
        return _agen()

    router.run_conversation = _terminal_then_result_run_conversation  # type: ignore[assignment]

    await router.drain_pending(sid)  # must not raise

    # Even with a trailing result frame, the terminal error wins → mark_sent, no re-drive.
    assert await sp.count_pending(sid) == 0, (
        "terminal error followed by a result frame was rolled back / left pending — "
        "the terminal flag did not survive to the result-driven finalize"
    )


@pytest.mark.asyncio
async def test_drain_rolls_back_on_transient_coded_error(wired):
    """AC2 / IMPROVEMENT.md #215 BOUNDARY NEGATIVE CONTROL: a TRANSIENT error
    (a real error CODE present, but NO terminal flag) must STILL roll back to
    pending so the existing exponential-retry behavior is preserved. This drives a
    real transient-coded error (SDK_ERROR, terminal absent), NOT the degenerate
    saw_error=None case — so if the terminal branch is ever loosened to swallow
    non-terminal errors, this test goes RED."""
    router, sp = wired
    sid = "sess-transient"
    router._units[sid] = _make_idle_unit(sid)
    await sp.persist_pending(sid, user_message="transient-failed message", content=None, agent_id="a")

    def _transient_error_run_conversation(**kwargs):
        async def _agen():
            # A transient error (throttle/5xx/timeout) that the orchestrator would
            # normally RAISE for retry; if it ever surfaces as a yielded error event
            # it carries NO terminal flag → must roll back, never terminally-drop.
            yield {"type": "error", "code": "SDK_ERROR", "message": "overloaded, try again"}
        return _agen()

    router.run_conversation = _transient_error_run_conversation  # type: ignore[assignment]

    await router.drain_pending(sid)  # must not raise

    # Non-terminal error → rolled back, row survives + re-claimable (retry preserved).
    assert await sp.count_pending(sid) == 1, (
        "transient (non-terminal) error was wrongly terminally-dropped — retry lost"
    )
    reclaim = await sp.claim_pending_batch(sid)
    assert len(reclaim) == 1
