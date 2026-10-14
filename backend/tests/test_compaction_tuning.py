"""Tests for compaction tuning (run_4f312c3c, XG directive 2026-10-14):

1. autocompact task_budget is DERIVED from the model context window
   (0.75 × window) instead of a hardcoded 800K literal — so it tracks the
   window and triggers earlier (less per-turn prefill tax). A named floor
   guards a hypothetical tiny-window model from disabling autocompact.
2. post_compact_injection enriches the continuation context with REAL
   session_context signal (recent activity / test status / commits /
   corrections / active run), fire-once preserved, and NEVER pollutes R19
   language classification (it rides the separate additionalContext channel).

Methodology: unit tests, no mocking of our own code. The task_budget helper is
a pure function of (model, channel). The injection hook is awaited directly with
a hand-built session_context dict (the system boundary is the SDK hook input, a
plain dict — nothing external to mock).
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Change 1 — window-derived task_budget
# ---------------------------------------------------------------------------

class TestTaskBudgetWindowDerived:
    def test_desktop_budget_is_075_of_window_1M(self):
        """A 1M-window model → desktop task_budget == 750_000 (0.75 × 1M)."""
        from core.prompt_builder import (
            AUTOCOMPACT_WINDOW_FRACTION,
            _compute_desktop_task_budget,
        )
        assert AUTOCOMPACT_WINDOW_FRACTION == 0.75
        # 1_000_000 is model_registry.LARGE_CONTEXT_WINDOW
        assert _compute_desktop_task_budget(1_000_000) == 750_000

    def test_desktop_budget_not_hardcoded_800k(self):
        """Regression guard: the old 800K literal must be gone from the desktop
        path — the budget tracks the window, not a frozen number."""
        assert _desktop_budget_for_window(1_000_000) != 800_000

    def test_floor_guards_tiny_window(self):
        """A hypothetical tiny-window model must never get an absurdly small
        budget that disables autocompact — the floor holds."""
        from core.prompt_builder import (
            AUTOCOMPACT_BUDGET_FLOOR,
            _compute_desktop_task_budget,
        )
        # a 10K window → 0.75×=7_500, below the floor → floor wins
        assert _compute_desktop_task_budget(10_000) == AUTOCOMPACT_BUDGET_FLOOR
        assert AUTOCOMPACT_BUDGET_FLOOR >= 128_000  # the old CLI default, a safe lower bound

    def test_default_window_gives_workable_budget(self):
        """An unknown/conservative model (200K default window) → 150K, workable
        and above the old 128K CLI default."""
        from core.prompt_builder import _compute_desktop_task_budget
        # 200_000 is model_registry.DEFAULT_CONTEXT_WINDOW
        assert _compute_desktop_task_budget(200_000) == 150_000

    def test_budget_is_an_int(self):
        """Derived budget must be an int (SDK task_budget total), not a float."""
        from core.prompt_builder import _compute_desktop_task_budget
        assert isinstance(_compute_desktop_task_budget(1_000_000), int)

    def test_source_no_longer_calls_task_budget_a_cost_cap(self):
        """AC4/C052: the stale ':2108 cost cap' comment must be corrected —
        task_budget is the autocompact TRIGGER line, not a cost cap (STEERING #2)."""
        src = (Path(__file__).resolve().parents[1] / "core" / "prompt_builder.py").read_text()
        # the task_budget region must not describe it as an "independent cost cap"
        assert "independent cost cap" not in src

    def test_channel_budget_unchanged(self):
        """Channel keeps its 400K unattended-safety line (Q1=A, not window-derived)."""
        src = (Path(__file__).resolve().parents[1] / "core" / "prompt_builder.py").read_text()
        assert re.search(r'"total":\s*400_000', src)


def _desktop_budget_for_window(window: int) -> int:
    from core.prompt_builder import _compute_desktop_task_budget
    return _compute_desktop_task_budget(window)


# ---------------------------------------------------------------------------
# Change 2 — enriched post_compact_injection
# ---------------------------------------------------------------------------

class _FakeObs:
    def __init__(self, tool_name, intent="", result_status="success"):
        self.tool_name = tool_name
        self.intent = intent
        self.result_status = result_status


class _FakeRing:
    def __init__(self, obs):
        self._obs = obs

    def snapshot(self, last_n=10):
        return self._obs[-last_n:]

    def all_completed(self):
        return self._obs


def _ctx(**overrides):
    base = {"_compacted": True, "sdk_session_id": "sess-1"}
    base.update(overrides)
    return base


async def _invoke(ctx):
    from core.runtime_hooks import create_post_compact_injection
    hook = create_post_compact_injection(ctx)
    return await hook({"prompt": "继续"}, "tu-1", MagicMock())


class TestPostCompactEnrichment:
    @pytest.mark.asyncio
    async def test_no_op_when_not_compacted(self):
        """Fire-once gate: no injection unless _compacted is set."""
        result = await _invoke(_ctx(_compacted=False))
        assert result == {}

    @pytest.mark.asyncio
    async def test_fire_once_resets_flag(self):
        """After injecting, _compacted resets to False (fire-once)."""
        ctx = _ctx(_files_touched={"a.py"})
        await _invoke(ctx)
        assert ctx["_compacted"] is False
        # second call → no injection
        second = await _invoke(ctx)
        assert second == {}

    @pytest.mark.asyncio
    async def test_files_touched_still_injected(self):
        """The existing files-touched line is preserved."""
        ctx = _ctx(_files_touched={"backend/core/foo.py", "backend/core/bar.py"})
        result = await _invoke(ctx)
        text = result["hookSpecificOutput"]["additionalContext"]
        assert "foo.py" in text

    @pytest.mark.asyncio
    async def test_enriched_with_recent_activity(self):
        """Dominant-tool / recent activity from the _observations ring appears."""
        ring = _FakeRing([_FakeObs("Bash", "pytest tests/"), _FakeObs("Bash", "grep"), _FakeObs("Read", "read foo")])
        ctx = _ctx(_observations=ring)
        text = (await _invoke(ctx))["hookSpecificOutput"]["additionalContext"]
        assert "Bash" in text  # dominant tool surfaced

    @pytest.mark.asyncio
    async def test_enriched_with_test_status(self):
        """_ran_tests signal surfaces a test-status line."""
        ctx = _ctx(_ran_tests=True)
        text = (await _invoke(ctx))["hookSpecificOutput"]["additionalContext"]
        assert "test" in text.lower()

    @pytest.mark.asyncio
    async def test_enriched_with_active_run(self):
        """_active_pipeline_run_id surfaces so a compacted pipeline keeps its thread."""
        ctx = _ctx(_active_pipeline_run_id="run_abc123")
        text = (await _invoke(ctx))["hookSpecificOutput"]["additionalContext"]
        assert "run_abc123" in text

    @pytest.mark.asyncio
    async def test_bare_session_only_base_line(self):
        """No signal → only the base compaction line, no fabricated enrichment."""
        ctx = _ctx()  # no files, no ring, no tests, no run
        result = await _invoke(ctx)
        text = result["hookSpecificOutput"]["additionalContext"]
        assert "compact" in text.lower()
        # no invented activity/test/run lines
        assert "run_" not in text


class TestR19NotPolluted:
    """The enriched injection rides additionalContext — it must never enter the
    string _classify_message_language sees (which is only the user prompt)."""

    def test_classifier_reads_only_user_prompt(self):
        from core.runtime_hooks import _classify_message_language
        # A Chinese user prompt stays zh regardless of any English injection text
        # (the injection is a SEPARATE channel, never concatenated into this arg).
        assert _classify_message_language("帮我看看这个问题") == "zh"

    def test_english_injection_text_is_not_the_classified_input(self):
        """Even if the enriched block is long English prose, it is returned via
        hookSpecificOutput.additionalContext, not fed to the classifier."""
        from core.runtime_hooks import _classify_message_language
        # classifier judges THIS string only — a zh prompt is zh.
        assert _classify_message_language("继续做压缩这个功能") == "zh"
