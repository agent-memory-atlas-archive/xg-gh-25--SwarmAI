"""R1.5b-i — expert_id 来源契约测试(方案 Z,零 Claude 耦合).

坐实 adversarial marker 的 `expert_id` 填值来源:从 sub-agent spawn prompt 的 head
里一个结构化锚点行 `EXPERT-ID: <id>` 提取(我们自己写入的契约),而非从 SDK 回传的
`agent_type`(恒 general-purpose)。

两端自契约:
  * 注入端 = `data/gate-prompts/gate2-adversarial.md` 的 `EXPERT-ID: <EXPERT_ID>` 行
    + `stages/deliver.md` 指示用 lowercase registry id 填充。
  * 提取端 = `runtime_hooks._extract_expert_id` 的锚定正则。

测试覆盖(forced-execution + mutation-proven):
  1. 契约:注入 `EXPERT-ID: correctness` head → 提取 `correctness`.
  2. mutation:注入行格式变 / 大小写变 → 提取失败(证明两端 lockstep,非 vacuous).
  3. 负路径:head 无 EXPERT-ID 行 → None(fail-safe,不回退 agent_type).
  4. drift:gate2 模板确实含占位行于早期行 + deliver.md 指示 lowercase id(Gate-1 Check6).
  5. E2E:真实 JSONL transcript fixture(user head 含 EXPERT-ID: correctness)
     → `_read_subagent_prompt_head` 读 → `_extract_expert_id` → `correctness`.
"""

import json
from pathlib import Path

import pytest

import core.runtime_hooks as rh

_REPO_ROOT = Path(__file__).resolve().parents[1]  # backend/
_GATE2 = (
    _REPO_ROOT
    / "skills/s_autonomous-pipeline/data/gate-prompts/gate2-adversarial.md"
)
_DELIVER = _REPO_ROOT / "skills/s_autonomous-pipeline/stages/deliver.md"


# ---- 1. Contract: inject → extract ----------------------------------------
@pytest.mark.parametrize(
    "head,expected",
    [
        ("EXPERT-ID: correctness\nYou are a specialist...", "correctness"),
        ("EXPERT-ID: api-contract\nYou are a specialist...", "api-contract"),
        ("EXPERT-ID: red-team\n...", "red-team"),
        ("EXPERT-ID: state-machine\n...", "state-machine"),
        # tolerate leading/trailing whitespace on the value
        ("EXPERT-ID:   security  \n...", "security"),
        # the line may sit on the 2nd line of the head (front-loaded, not line 1)
        ("You are a reviewer\nEXPERT-ID: performance\n...", "performance"),
    ],
)
def test_extract_expert_id_from_head(head, expected):
    assert rh._extract_expert_id(head) == expected


# ---- 2. Mutation: a drifted inject format must NOT extract -----------------
@pytest.mark.parametrize(
    "head",
    [
        "EXPERT-ID: Correctness\n...",  # Title-case → fails [a-z] anchor (fail-safe)
        "EXPERT ID: correctness\n...",  # space not hyphen in the key
        "expert-id: correctness\n...",  # lowercase key (anchor is ^EXPERT-ID:)
        "# EXPERT-ID: correctness\n...",  # prefixed → not at line start
        "the EXPERT-ID: correctness is foo",  # embedded in prose, not anchored
        "EXPERT-ID:correctness extra words\n...",  # trailing words after id → not a bare id line
    ],
)
def test_extract_expert_id_rejects_drifted_format(head):
    # A mutation on the inject side (wrong case / wrong key / not anchored /
    # trailing junk) must NOT silently resolve to a wrong id — it returns None.
    # This is what makes the contract test non-vacuous: if the regex were
    # loosened to \S+ or dropped the anchor, these would wrongly pass.
    assert rh._extract_expert_id(head) is None


# ---- 2b. First-anchor-binding: a malformed line 1 is NOT overridden by a -----
#         well-formed EXPERT-ID line in the injected review content below it.
@pytest.mark.parametrize(
    "head,expected",
    [
        # Unfilled placeholder on line 1 + an injected EXPERT-ID line in the review
        # content below (a changed-file path / requirement text an author influences).
        # Must bind to the malformed FIRST EXPERT-ID line → None, NOT scan forward.
        (
            "EXPERT-ID: <EXPERT_ID>\n"
            "You are a specialist reviewer.\n"
            "some diff line\n"
            "EXPERT-ID: red-team\n",
            None,
        ),
        # Malformed first anchor (Title-case) + well-formed one below → still None.
        ("EXPERT-ID: Correctness\n...\nEXPERT-ID: security\n", None),
        # Well-formed first anchor wins even if more follow (normal case, defensive).
        ("EXPERT-ID: correctness\n...\nEXPERT-ID: security\n", "correctness"),
    ],
)
def test_extract_binds_to_first_anchor_not_injected_content(head, expected):
    # Guards the MED Gate-2 finding: a `re.search` for the WELL-FORMED pattern would
    # skip an unfilled/malformed line 1 and match an injected EXPERT-ID line below →
    # wrong attribution. Binding to the FIRST EXPERT-ID-prefixed line closes it.
    assert rh._extract_expert_id(head) == expected


# ---- 3. Negative path: no EXPERT-ID line → None (fail-safe) ----------------
@pytest.mark.parametrize(
    "head",
    [
        "",
        "You are a specialist code reviewer focused exclusively on Correctness.",
        "find bugs in the diff\nadversarially review this changeset",
    ],
)
def test_extract_expert_id_absent_returns_none(head):
    # head with no EXPERT-ID line → None. Must NOT fall back to agent_type
    # (that is the rejected SDK-coupling path — 方案 Z).
    assert rh._extract_expert_id(head) is None


# ---- 4. Drift: template carries the placeholder, deliver.md teaches id -----
def test_gate2_template_carries_expert_id_placeholder():
    """The inject end must contain the EXPERT-ID contract line near the top
    (within the first-read window the extractor sees). Guards against someone
    removing/renaming the placeholder, silently breaking the contract."""
    assert _GATE2.exists(), f"gate2 template missing: {_GATE2}"
    text = _GATE2.read_text(encoding="utf-8")
    # placeholder present
    assert "EXPERT-ID: <EXPERT_ID>" in text, (
        "gate2-adversarial.md must carry the 'EXPERT-ID: <EXPERT_ID>' contract line"
    )
    # and it must be front-loaded (within the first few lines — the extractor
    # only sees _read_subagent_prompt_head's content[:2000], and the orchestrator
    # fills real content below, so the placeholder must lead)
    head_lines = text.splitlines()[:3]
    assert any(ln.startswith("EXPERT-ID:") for ln in head_lines), (
        "EXPERT-ID line must be in the first 3 lines of the template (front-loaded)"
    )


def test_deliver_instructs_lowercase_registry_id():
    """deliver.md must instruct the orchestrator to fill <EXPERT_ID> with the
    lowercase registry id (not the Title-case <DOMAIN> name). Closes the
    free-form drift gap (Gate-1 Check 6, fix a)."""
    assert _DELIVER.exists()
    text = _DELIVER.read_text(encoding="utf-8")
    assert "<EXPERT_ID>" in text, "deliver.md must reference the <EXPERT_ID> placeholder"
    # the instruction must mention the registry id source (experts/code/<id>.md path)
    assert "EXPERT_ID" in text and "registry id" in text.lower(), (
        "deliver.md must instruct filling <EXPERT_ID> with the lowercase registry id"
    )


# ---- 5. E2E: real transcript fixture → marker expert_id --------------------
def test_e2e_expert_id_from_real_transcript_head(tmp_path):
    """Forced-execution E2E: write a real JSONL transcript whose first user
    record (the spawn prompt) carries `EXPERT-ID: correctness`, read it through
    the REAL _read_subagent_prompt_head, extract, and assert correctness —
    proving the on-disk → extract path yields the registry id, not
    general-purpose/None."""
    transcript = tmp_path / "subagent_transcript.jsonl"
    spawn_prompt = (
        "EXPERT-ID: correctness\n"
        "You are a specialist code reviewer focused exclusively on Correctness.\n"
        "Adversarially review this changeset — hunt for bugs in the diff."
    )
    lines = [
        json.dumps({"type": "user", "message": {"content": spawn_prompt}}),
        json.dumps({"type": "assistant", "message": {"content": "ok"}}),
    ]
    transcript.write_text("\n".join(lines), encoding="utf-8")

    head = rh._read_subagent_prompt_head(str(transcript))
    assert head, "head read must return the spawn prompt"
    assert rh._extract_expert_id(head) == "correctness"


def test_e2e_content_block_array_transcript(tmp_path):
    """Same E2E but the user record uses a content-block ARRAY (the SDK's other
    shape) — _read_subagent_prompt_head joins block texts, extractor still works."""
    transcript = tmp_path / "t2.jsonl"
    spawn_prompt = "EXPERT-ID: security\nYou are a specialist reviewer."
    rec = {"type": "user", "message": {"content": [{"text": spawn_prompt}]}}
    transcript.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    head = rh._read_subagent_prompt_head(str(transcript))
    assert rh._extract_expert_id(head) == "security"
