# Self-Evolution Engine — Supplementary Reference

This file provides additional detail beyond SKILL.md. SKILL.md is self-contained
and sufficient for all operations. Read this only when you need deeper context
on VFM scoring or entry revision operations.

## VFM Scoring Detail

Score across four dimensions (each 0-10):

| Dimension | Weight | Question |
|-----------|--------|----------|
| Reusability | 3x | Will future tasks leverage this repeatedly? |
| Error Prevention | 3x | Does this prevent a recurring failure? |
| Analysis Quality | 2x | Does this improve output depth or accuracy? |
| Efficiency Gain | 2x | Does this save time or reduce tool calls? |

**Formula:** `VFM = (Reusability*3 + ErrorPrevention*3 + AnalysisQuality*2 + EfficiencyGain*2) / 10`

| VFM Score | Action |
|-----------|--------|
| >=70 | Promote immediately |
| 50-69 | Promote if 3+ occurrences confirm the pattern |
| <50 | Keep in EVOLUTION.md, do not promote |

## Entry Revision Operations

Beyond basic add, entries can be revised:

- **`supersede`**: Replace an entry with a better one. Set `Status: superseded by E{NNN}`.
- **`fork`**: Create a variant for a different context. Reference parent.
- **`contest`**: Mark conflicting evidence against an entry. Add note.

Log all revisions to JSONL changelog.
