---
inclusion: fileMatch
fileMatchPattern: ["backend/skills/s_self-evolution/*", "backend/context/EVOLUTION.md", "backend/context/EVOLUTION_CHANGELOG.jsonl", "backend/core/evolution_optimizer.py", "backend/core/evolution/*.py", "backend/hooks/evolution_maintenance_hook.py", "backend/hooks/evolution_trigger_hook.py", "backend/jobs/run_evolution.py", "backend/jobs/system_jobs.py"]
---

# Self-Evolution Guardrails

## Core Invariant: Evolution Improves Stability, Not Complexity

Priority ordering (ADL Protocol): Stability > Interpretability > Reusability > Extensibility > Novelty.
The model proposes; code gates. Nothing in the evolution system may auto-write the
governed judgment files (SOUL / AGENT / STEERING) — it writes proposals for a human.

## The Three Evolution Paths (current)

| Path | Trigger | Code | Writes |
|------|---------|------|--------|
| Skill-optimization cycle (MINE→ASSESS→ACT→AUDIT) | Weekly system job `evolution-cycle` (Thu 07:00, 1800s timeout) — the ONLY trigger | `evolution_optimizer.run_evolution_cycle` via `jobs/run_evolution.py` | skill_health.json, `.evolution_proposals.json`, EVOLUTION.md + changelog |
| EVOLUTION.md maintenance | Session close (`EvolutionMaintenanceHook`, post-session hook) | `hooks/evolution_maintenance_hook.py` | EVOLUTION.md, monthly archive shard, changelog |
| Governance lifecycle | Prompt-driven | `s_self-evolution` skill (CLASSIFY/CAPTURE/PROMOTE/REFINE/RETIRE/COMPRESS) | EVOLUTION.md via Read + Edit, changelog |

Never put the cycle back on the session-close hook: it takes ~5 min against a 180s hook
budget and re-fired every session (run_6ac3fc0b).

## Cycle Guardrails (code-enforced, evolution_optimizer.py)

- Process flock on `.evolution_cycle.lock` (non-blocking, stale-lock break) — one cycle at a time.
- LLM cost cap: `evolution.max_llm_skills_per_cycle` (default 5), highest confidence first.
- Confidence tiers: HIGH → proposal/deploy, MED → recommendation, LOW → log only.
  HIGH needs ≥2 corrections, else it is demoted to MED.
- Regression gate: a deployed skill whose fitness dropped >0.1 is auto-reverted from
  `SKILL.md.bak`. Deploys are atomic (tmp + `os.replace` + verify + rollback).
- Freshness re-read before applying changes (the skill may have changed since MINE).
- Thresholds: `HIGH_CONFIDENCE = 0.15`, `MED_CONFIDENCE = 0.08` in `evolution_optimizer.py`
  are the ONLY source (not configurable; a test guards against a second source).
  Recalibrate them there, with data.

## Maintenance Hook Order (EvolutionMaintenanceHook.execute)

1. `_quality_gate` — drops garbage Competence entries (<3 words / commit-hash text), fixes duplicate C-IDs.
2. `_fold_corrections` — folds data-point families over the cap (`_FOLD_CAP = 2`) into
   `EVOLUTION-archive-YYYY-MM.md`. The whitelist lives in `data_point_folding._FOLDABLE_MARKERS`.
3. `_size_evict` — size valve: above 20K tokens, evict lowest-value whole `###` blocks down
   to 15K, into the monthly shard (recall-backed, not deletion). Marker-bearing blocks
   (`**Pattern**`, `**Durable tell**`, CAPSTONE, METHOD FIX, …) go last; recent (≤14 days) next.
4. E/K lifecycle — `Capabilities Built` and `Competence Learned` only: active + idle >30d +
   usage 0 → deprecated; deprecated + usage 0 + >30d → removed.
5. Promotion threshold check (3x rule), correction-class auto-resolve (30 days quiet),
   correction classifier, escalation ladder (proposals to `.evolution_proposals.json` only).

Every step is error-isolated and runs under the EVOLUTION.md flock; on lock timeout it
skips rather than clobbering. All mutations log to `EVOLUTION_CHANGELOG.jsonl`
(`rotate_jsonl_if_oversized`). Run order matters: fold before the valve, or the valve
over-archives.

## Write Rules

- The skill writes EVOLUTION.md with Read + Edit and must NOT shell out to
  `locked_write.py` (PyInstaller crash). A changelog append after every mutation is mandatory.
- Backend code uses `scripts.locked_write` functions as a library under the flock.
- EVOLUTION.md stays at P8 in `CONTEXT_FILES`, `user_customized=True` (copy-if-missing).

## Configuration Boundaries

`config.json["evolution"]`, read via `AppConfigManager.get("evolution")`.

- NEVER change `auto_approve_skills/scripts/installs` defaults to `true`.
- `max_llm_skills_per_cycle` is meant to be read by the cycle, but its read uses the same
  non-existent `app_config_manager` import as several other sites, so it is always 5.
- `max_triggers_per_session`, `max_retries`, `max_active_entries`,
  `same_type_cooldown_seconds` are NOT read by backend code. They are prompt-level limits
  only, and `deprecation_days` is not wired into the hook (it uses its constructor default
  of 30). Don't describe them as code-enforced.

## Dead Code (don't build on it)

- The `<!-- EVOLUTION_EVENT -->` SSE marker chain was REMOVED on 2026-10-17 (no producer
  since 39756bd5). Don't reintroduce markers in agent text as a UI channel.
- `ToolFailureTracker` (`hooks/evolution_trigger_hook.py`) is never instantiated. The live
  repeated-failure hint is `create_error_pattern_detector` + `create_failure_tracker_reset`
  in `core/runtime_hooks.py` (per-session `session_context["_failure_tracker"]`).

Remove these in a dedicated change, or revive them deliberately — don't patch around them.

## Regression Checklist

- [ ] The cycle is triggered only by the scheduled job, never by a session hook
- [ ] Cycle lock, LLM cap, regression revert, and atomic deploy still in place
- [ ] Maintenance order: quality gate → fold → size valve → lifecycle → governance
- [ ] Size valve still archives to the monthly shard (never deletes)
- [ ] Escalation writes proposals only; never SOUL/AGENT/STEERING
- [ ] `auto_approve_*` defaults remain `false`
- [ ] EVOLUTION.md still P8, `user_customized=True`
