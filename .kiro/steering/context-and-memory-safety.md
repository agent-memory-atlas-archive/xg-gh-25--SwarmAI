---
inclusion: fileMatch
fileMatchPattern: ["backend/core/context_directory_loader.py", "backend/core/context_injector.py", "backend/core/system_prompt.py", "backend/core/prompt_builder.py", "backend/core/memory_extractor.py", "backend/core/daily_activity_writer.py", "backend/hooks/*.py", "backend/scripts/locked_write.py", "backend/context/*.md"]
---

# Context and Memory Safety Principles

The file list, priorities, and budgets are summarized in AGENTS.md "Context and Memory
System". The source of truth is `CONTEXT_FILES` and `compute_token_budget` in
`backend/core/context_directory_loader.py`. This file covers the invariants that are easy
to break.

## Core Invariant: Context Loading Never Blocks Agent Startup

The assembly pipeline (`ContextDirectoryLoader.load_all()` →
`PromptBuilder.build_system_prompt()` in `prompt_builder.py` → `SystemPromptBuilder.build()`)
must degrade gracefully. A failure at any stage starts the agent with reduced context; it
never crashes the session.

## Ownership and Two-Mode Copy (ensure_directory)

These rules are the user trust model. Violating them destroys user customizations.

1. System files (`user_customized=False`: SWARMAI, IDENTITY, SOUL, AGENT) are ALWAYS
   overwritten from the template, only when the bytes changed, and set to 0o444.
2. Everything with `user_customized=True` (SELF, USER, STEERING, TOOLS, MEMORY, EVOLUTION,
   KNOWLEDGE) is copied ONLY if missing and never overwritten (0o644). SELF.md is
   runtime-owned: the live `.context/SELF.md` is authoritative, so a template edit does not
   reach an existing install.
3. New context files go into `CONTEXT_FILES` with an explicit priority and ownership.
   PROJECTS.md was removed (2026-08-14); don't reintroduce an auto-generated index file.

## Token Budget: Warn, Never Truncate

- Budget tiers (`compute_token_budget`): ≥500K window → 150K, ≥200K → 50K, ≥64K → 30K,
  <64K → instance default (L0 compact path). Below 32K, KNOWLEDGE.md is skipped.
- The read-line NEVER truncates. Over budget, `_enforce_token_budget` logs an
  `over_budget` warning and returns full content. `_truncate_section` was deleted on
  2026-08-14; the `truncatable`/`direction` fields are legacy and inert.
- Size is bounded WRITE-side: MEMORY distillation + size-valve archival, and the
  EVOLUTION size valve (20K high / 15K low watermark → monthly archive shard). If a file
  is too big, fix the write-side valve, not the loader.
- Don't flip `truncatable` to False on MEMORY/EVOLUTION: `core_section_names()` treats
  `truncatable is False` as "conceptual core".

## L0/L1 Cache Correctness

- L1 cache (`L1_SYSTEM_PROMPTS.md`) carries a `<!-- budget:NNNNN -->` header. If the cached
  budget ≠ the current session budget (model switch), the cache is STALE and must be
  reassembled.
- L1 freshness: git-first check (`git status --porcelain`), mtime fallback.
- L0 is the compact cache for <64K models, separate from L1.
- Never edit a cache file. It is derived — edit the source `.context/*.md` files.

## Memory Lifecycle — Code-Enforced Path

```
Conversation → DailyActivity (hook) → Distillation (hook) → MEMORY.md → next session
```

- Post-session hooks are registered in `main.py` lifespan (the authoritative list and
  order — don't enumerate them elsewhere). They run through `BackgroundHookExecutor`: one
  serial worker, error-isolated, 180s per hook. They never block chat.
- MEMORY.md / EVOLUTION.md load via `CONTEXT_FILES`. DailyActivity: the 2 most recent
  files are injected ephemerally by `build_system_prompt` (2K token cap each, skipped for
  channel sessions, disk never modified).
- Resume: `context_injector.build_resume_context()` on cold resume.
- Prompt-dependent by design: distillation-flag fallback (`.needs_distillation` →
  prompt injection) and user-invoked skills (save-memory, save-activity).

## File Locking Rules

- MEMORY.md: ALWAYS write through `locked_write.py` (flock on a `.md.lock` sidecar).
- EVOLUTION.md: backend code uses `locked_write` internals
  (`locked_read_modify_write`); the s_self-evolution skill uses Read + Edit (it must not
  shell out to `locked_write.py` — PyInstaller crash).
- DailyActivity: append-only with `O_APPEND`, no lock.
- L1 cache: single writer (ContextDirectoryLoader), no lock; stale reads are harmless.
- Never write untrusted external text into MEMORY.md as a standing directive
  (security baseline B5).

## BOOTSTRAP.md — Ephemeral Onboarding

- NOT in `CONTEXT_FILES` and never cached in L1. Created only when USER.md is an unfilled
  template (`_is_empty_template()`), injected ephemerally, gone once USER.md is filled.
- Test the first-run experience before changing its detection logic.

## Regression Checklist

When modifying context or memory code:

- [ ] `ensure_directory()` still respects two-mode copy (system=overwrite, user=copy-if-missing)
- [ ] System files still get 0o444 after write; user files keep 0o644
- [ ] `compute_token_budget` tiers unchanged, or AGENTS.md updated with them
- [ ] Nothing truncates on the read-line; over-budget only warns
- [ ] L1 cache includes the budget header and validates it on load
- [ ] DailyActivity files are never modified on disk during loading
- [ ] All MEMORY.md writes go through `locked_write.py`
- [ ] Hooks stay fire-and-forget through `BackgroundHookExecutor` and error-isolated
- [ ] `build_resume_context()` still drops the last assistant message
- [ ] New context files have correct priority and ownership in `CONTEXT_FILES`
