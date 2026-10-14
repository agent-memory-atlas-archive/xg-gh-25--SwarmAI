---
title: "SwarmAI Autonomous Pipeline — the whole thing on one page"
created: 2026-10-14
updated: 2026-10-14
status: published
category: Show and tell
---
<!-- GitHub Discussion #111: https://github.com/xg-gh-25/SwarmAI/discussions/111 -->

# SwarmAI Autonomous Pipeline — the whole thing on one page

> One requirement in → PR-ready delivery out. Here is the entire pipeline on a single page: **9 stages · 3 gates · 2 modes · 6 profiles · 16 review/adversarial roles.**

![SwarmAI Autonomous Pipeline — one-page panorama](https://github.com/xg-gh-25/SwarmAI/raw/main/docs/assets/discussions/2026-10-14-pipeline-panorama.png)

Every number on this page is read from live source (`pipeline_profiles.py` + the `s_autonomous-pipeline` skill), not from memory and not rounded for the slide.

## How to read it, top to bottom

**INTENT → 5 phases (9 stages).** A one-line natural-language intent feeds **Frame** (Evaluate → Think — turns intent into a concrete requirement + acceptance criteria), then **Plan**, **Build** (Build → Review → Test), **Deliver** (Deliver + the embedded Adversarial stage), **Reflect**. That's the 9 canonical stages collapsed into 5 phases. Three gates sit at the moments that matter — Gate 0 guards *framing*, Gate 1 guards *the plan*, Gate 2 guards *the build* (adversarial review, blocking, right before commit). Reflect's lessons flow back into the knowledge stores, so the next run judges better — value compounds across sessions.

**2 modes fork at Build.** `full`/`bugfix` run build→review→test once (one-shot). `goal` loops build+test until a measurable Definition-of-Done is met. Everything else is identical — the fork is only at Phase 2.

**What Deliver actually ships.** Completion-audit → package → commit. The deliverables: a push-ready **commit** (plus an optional **PR / CR** with auto-merge — a GitHub PR on an open repo, a CR on an internal Amazon repo); a **REPORT.md** (delivery report + decision log, under `.artifacts/runs/<id>/`); and **METRICS.json** (run metrics). The Push-Ready Gate is binary — `run-commit` refuses unless it passes.

**6 profiles — one core, cut to the scenario.** STRICT (`full` / `bugfix` / `goal`) runs the full adversarial pass; RELAXED (`trivial` / `docs` / `research`) relaxes the gates for low-risk work. The profile is fixed at EVALUATE and **immutable after** — so the pipeline can't quietly downgrade itself to skip the adversarial gate.

**Multi-skills orchestration.** The main skill `s_autonomous-pipeline` is the orchestrator; it dispatches a specialist skill per stage and reuses its capability rather than reinventing it — `s_evaluate`, `s_deep-research`, `s_code-review`, `s_qa`, `s_deliver`, DDD cultivation.

**Spawn sub-agents.** A "sub-agent" is a separate process spawned via the Agent tool — **fresh context, zero memory of the build or the main conversation.** The point is to break the author-reviews-own-work bias: the one who wrote the code doesn't get to be the judge. Prompts are emitted by code with a mandatory scope cap (an uncapped prompt is refused); parallel groups spawn in one message; at `SubagentStop` the reviewed paths are captured from `git diff HEAD` and matched against the commit. 16 roles total = 3 gate skeptics + 4 parallel reviewers + 9 scope-gated adversarial specialists.

## The DDD layer — what closes the loop

The whole pipeline sits on a **DDD layer** (the project's domain brain) and reads *and* writes it — that's what makes the feedback a real loop, not a slogan. Four markdown docs, each with a role and a wired read/write path (verified against each stage's references):

| Doc | Role | READ (feeds judgment) | WRITE (Reflect flows back) |
|---|---|---|---|
| `PRODUCT.md` | vision · non-goals | EVALUATE / THINK / PLAN | cultivation |
| `TECH.md` | conventions · architecture | all stages | cultivation |
| `IMPROVEMENT.md` | failures · anti-patterns | all stages | REFLECT |
| `PROJECT.md` | progress · decision log | — | REFLECT |

The loop: the front stages **read** the DDD for judgment → Reflect **writes** the new lessons back into the DDD (plus MEMORY / EVOLUTION) → the next pipeline reads a sharper DDD and judges better. The pipeline sits on its domain brain, reads and writes it, and compounds across sessions.

## The architecture, stated

**single-orchestrator, ephemeral adversarial sub-agents** — *not* multi-resident-agent collaboration.

It looks like multi-agent because many sub-agents run per pipeline. But the backbone is **one orchestrator holding the full context the whole time**; the sub-agents are throwaway adversarial probes spawned at checkpoints — they don't persist, don't talk to each other, don't hand context back (only a verdict + the paths they reviewed). The difference matters:

- **Who holds context** — one backbone, zero hand-offs. Not a team of peers passing state around.
- **Why "multi"** — their multi is *division of labor*; ours is *adversarial de-biasing* (fresh context to attack the work).
- **Hand-off cost** — their core cost is passing context between agents (quadratic channels). Ours is near-zero: a sub-agent hands back a verdict, not state.

You get the upside of multi-agent (parallelism, independent perspectives, de-biasing) without its disease (hand-off tax, context fragmentation, coordination overhead).

*(Related: [#43 Why we chose single-agent](https://github.com/xg-gh-25/SwarmAI/discussions/43) · [#44 The three cracks in multi-agent](https://github.com/xg-gh-25/SwarmAI/discussions/44) · [#12 Multi-agent is a coordination tax](https://github.com/xg-gh-25/SwarmAI/discussions/12).)*
