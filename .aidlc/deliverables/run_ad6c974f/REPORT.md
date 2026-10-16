# Autonomous Pipeline Report: Stop *-archive*.md files (overflow/decay sediment: IMPROVEMENT-archive.md, TECH-

**Run ID:** run_ad6c974f | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 21:26 UTC | **Duration:** 22.8 min (in progress) | **Tokens:** 106,000
**Gate 1:** BLOCK | **Files:** 2 | **Tests:** True/1

## TL;DR
Stop *-archive*.md files (overflow/decay sediment: IMPROVEMENT-archive.md, TECH-archive.md, MEMORY-archive-*.md, EVOLUTION-archive.md) from surfacing to the Canvas outputs rail. Root cause: needs_huma

## 1. Requirement
Stop *-archive*.md files (overflow/decay sediment: IMPROVEMENT-archive.md, TECH-archive.md, MEMORY-archive-*.md, EVOLUTION-archive.md) from surfacing to the Canvas outputs rail. Root cause: needs_human_review.py (the single git-based surface authority) classifies git-tracked Projects/SwarmAI/2-understanding/*-archive.md as kind=knowledge -> review_worthy=True -> frontend auto-pops to Canvas. Fix: add archive-basename detection (reuse knowledge_store.py SSOT pattern) to both needs_human_review and needs_human_review_batch, returning review_worthy=False kind=process, overriding the knowledge classification.

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Stop *-archive*.md files (overflow/decay sediment: IMPROVEMENT-archive.md, TECH-archive.md, MEMORY-archive-*.md, EVOLUTION-archive.md) from surfacing to the Canvas outputs rail. Root cause: needs_human_review.py (the single git-based surface authority) classifies git-tracked Projects/SwarmAI/2-understanding/*-archive.md as kind=knowledge -> review_worthy=True -> frontend auto-pops to Canvas. Fix: add archive-basename detection (reuse knowledge_store.py SSOT pattern) to both needs_human_review and needs_human_review_batch, returning review_worthy=False kind=process, overriding the knowledge classification.

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: do not surface IMPROVEMENT-archived.md and other -archived.md to Canvas | confirmed | ● | Given a tracked Projects/SwarmAI/2-understanding/IMPROVEMENT-archive.md change, when needs_human_review runs, then review_worthy=False, kind=process - not surfaced |
| FR-2 | bug | ddd-derived: regression guard - archive check must not demote real deliverables | confirmed | ● | Given Projects/SwarmAI/2-understanding/IMPROVEMENT.md, when needs_human_review runs, then review_worthy=True, kind=knowledge |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | Fix layer: backend authority vs frontend AUTO_POP_KINDS? | A. needs_human_review | 🧠 self |
| Q2 | Which archive pattern to match? | A. reuse SSOT | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. needs_human_review (🧠 AI 替你拍的板 — resolution: needs_human_review is the SSOT surface authority (Artifacts list + Canvas rail both read it). Frontend fix would leave archives in kind=knowledge for every other consumer. Fix the authority, not one consumer.)
- [SELF-ANSWERED] Q2: A. reuse SSOT (🧠 AI 替你拍的板 — resolution: P8 cross-door consistency: the archive-detection door in knowledge_store (chunking) and this surface door must agree on what -archive means. Reuse the exact predicate.)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | high | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. Projects/SwarmAI/2-understanding/IMPROVEMENT-archive.md and TECH-archive.md -> needs_human_review review_worthy=False kind=process (both single + batch functions)
2. Live DDD docs IMPROVEMENT.md/TECH.md/PRODUCT.md still -> review_worthy=True kind=knowledge (no over-match on IMPROVEMENT.md)
3. .context/MEMORY-archive-2026-10.md still -> False process (unchanged)
4. A non-suffix incidental like design-archive-notes.md surfacing decision is deliberately decided
5. Tests added for both single + batch covering archive-leak + live-doc-preserved cases, RED before fix GREEN after


## 3. Design & Approach
**Research Findings (THINK):**
- needs_human_review.py is the SOLE surface authority (13 callers incl. workspace_api Artifacts list + streaming_orchestrator Canvas rail); fixing here fixes every consumer at once. A frontend AUTO_POP_KINDS fix would only patch one consumer and leave archives as kind=knowledge everywhere else.
- Two functions share identical layered precedence: needs_human_review (single, :382-407) and needs_human_review_batch (:465-495). Both reach _classify_kind -> knowledge for 2-understanding/*-archive.md. A fix must touch BOTH or the batch surface path keeps leaking; shared helper prevents drift.
- SSOT archive predicate already exists at knowledge_store.py:92: `'-archive' in _base and _base.endswith('.md')`. Reusing it keeps the two archive-detection doors (chunking vs surfacing) consistent (P8).
- False-positive surface measured across the live SwarmWS tree: ALL 14 distinct -archive*.md basenames are genuine DDD/context overflow archives (IMPROVEMENT/TECH/MEMORY/EVOLUTION-archive). Zero live deliverables carry -archive in the basename. The knowledge_store.py:92 comment worries about a hypothetical 'design-archive-notes.md' but none exists.
- Insertion point: the archive check must run BEFORE _classify_kind returns knowledge, and must override _is_surfaceable_knowledge too (so an archived knowledge basename can never surface). Earliest-correct point is right after owning-tree resolution, alongside the dot-segment layer, applied to the tree-relative basename.

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS, 1 session
- FLEXIBILITY — effort: S

**Chosen Approach:** Add a module-level helper _is_overflow_archive(rel_path) in needs_human_review.py that reuses the knowledge_store.py:92 SSOT predicate ('-archive' in basename and basename endswith '.md'). Call it in BOTH needs_human_review (single) and needs_human_review_batch, placed AFTER owning-tree resolution and AFTER _is_surfaceable_knowledge (so it overrides the knowledge allowlist), returning ReviewVerdict(False,'process',repo). This makes an overflow archive never surface regardless of tracked/knowledge/2-understanding status.

**Success Criteria:**
- pytest test_needs_human_review.py -k archive passes (new tests GREEN after fix)
- The 4 pre-existing archive leaks (IMPROVEMENT-archive.md, TECH-archive.md both via single + batch) all return process
- No regression: existing test_needs_human_review.py suite stays green

**Always:**
- Reuse the knowledge_store.py:92 SSOT predicate verbatim (P8 cross-door consistency)
- Fix BOTH single + batch via a shared helper
- Add tests RED-before-fix for both leak + preserve cases

**Never:**
- Do NOT fix in frontend AUTO_POP_KINDS (would patch one consumer, leave archives=knowledge everywhere else)
- Do NOT use a bespoke regex that diverges from the knowledge_store SSOT
- Do NOT demote the live knowledge basenames (MEMORY/EVOLUTION/KNOWLEDGE.md) — they carry no -archive


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| review | anchored regex diverges from knowledge_store loose predicate | taste | P8 door-appropriate |

**Summary:** 0 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**⏭ NOT RUN** — deliver stage was skipped (profile: bugfix)

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/needs_human_review.py`
- `backend/tests/test_needs_human_review.py`

## 9. Lessons
- [decision] A surface/visibility classifier must anchor its archive/overflow pattern on filename STRUCTURE (regex -archive(-YYYY-MM)?.md$), not a loose substring (-archive in base) — a surface false-positive HIDES a real deliverable, a strictly worse blast radius than the sibling chunking door where a loose substring is harmless. Same concept, door-appropriate strictness (P8).
- [pitfall] needs_human_review resolves its owning tree via get_swarmws()=~/.swarm-ai/SwarmWS, whose .gitignore un-ignores Projects/SwarmAI/ — so a git check-ignore run in the SOURCE repo (where Projects/* blankets all DDDs) gives the OPPOSITE verdict. A Gate-0 skeptic that measured the source tree reached WRONG-FRAME; the authority must be probed in the tree it actually resolves. Verify a classifier by executing it, not by reasoning about a different git tree.
- [guideline] A classification authority with single + batch twin functions must get an identical check at an identical precedence point in BOTH, factored into one shared helper — a fix to only one leaves the other surface path leaking; pin it with a batch-parity test.


## 10. Known Gaps & Attention Flags
- Validator blocked 4 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 21:26 UTC*
