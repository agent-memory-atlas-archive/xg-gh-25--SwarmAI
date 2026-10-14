# Autonomous Pipeline Report: Compaction tuning: window-derived autocompact threshold (0.75×) + enriched post-compact continuation

**Run ID:** run_4f312c3c | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 04:08 UTC | **Duration:** 24.8 min (in progress) | **Tokens:** 109,000
**Gate 1:** N/A | **Files:** 4 | **Tests:** 0/0

## TL;DR
Compaction 调优:(1) autocompact task_budget 从硬编码 800K 改为 0.75×模型context窗口(绑定窗口,1M→750K);(2) post_compact_injection 续接内容做厚(task目标+最近决定+未完成项,fire-once+不污染R19)

## 1. Requirement
Compaction 调优:(1) autocompact task_budget 从硬编码 800K 改为 0.75×模型context窗口(绑定窗口,1M→750K);(2) post_compact_injection 续接内容做厚(task目标+最近决定+未完成项,fire-once+不污染R19)

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Compaction 调优:(1) autocompact task_budget 从硬编码 800K 改为 0.75×模型context窗口(绑定窗口,1M→750K);(2) post_compact_injection 续接内容做厚(task目标+最近决定+未完成项,fire-once+不污染R19)

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | task | user-stated: XG: '阀值只能比800k 小才合理 基本75% context window其实就应该触发' — 更早压缩让 context 常年精简,降低每轮 prefill 延迟+成本 | confirmed | ● | Given a desktop session on a 1M-window model, when task_budget is computed, then it equals round(0.75*window)=750K, derived not literal, with a safe fallback for unknown windows |
| FR-2 | user-story | user-stated: XG: '把 post_compact_injection 的续接内容做厚一点' | confirmed | ● | Given a compaction fires with session_context carrying observation/test/commit signal, when the next UserPromptSubmit injects post-compact context, then the additionalContext includes those real signals (not just files), fire-once preserved |
| NFR-1 | enabler-story | ddd-derived: R19 (runtime_hooks additionalContext 独立于 user prompt 分类通道); STEERING #2 (task_budget 是触发线非容灾 cap); R7/C052 (注释与新行为一致) | confirmed | ● | Given the enriched injection + lowered threshold, when R19 classifies a message and the comment is read, then classification unaffected (additionalContext channel), and the :2108 comment no longer calls task_budget a cost cap |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | channel 的 400K 要不要也改成 0.75×窗口,还是保持 400K? | A. 保持 400K | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. 保持 400K (🧠 AI 替你拍的板 — resolution: XG 的指令针对 desktop 的 800K('比800k小')。channel 400K 是无人值守场景的独立安全线(配合 max_turns=100),rationale 不同于 desktop 的'减少 prefill 税';无指令改它,保持 400K 最小惊讶。THINK 会复核 400K 是否恰好是某窗口比例可统一;默认不动。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 7.00 | |
| Priority | 7.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: desktop task_budget == round(0.75 * get_model_context_window(model)), NOT a hardcoded 800K; for a 1M model this is 750K. No 750000 literal — derived from the window.
2. AC2: a safe fallback — if the window is unknown/zero/tiny, task_budget falls back to a sane floor (never 0, never a value below the old working range) so a mis-resolved model can't disable autocompact or set an absurd budget.
3. AC3: channel task_budget behavior is a deliberate decision (default: keep 400K unattended-safety line, documented why it is NOT the 0.75 formula — or unify if 400K is coincidentally a window fraction); EVALUATE/THINK decides, no silent change.
4. AC4: post_compact_injection enriches the continuation context with REAL session_context signal — recent activity (dominant tool / recent intents from the _observations ring), test status (_ran_tests / pytest pass signal), recent git commits, correction count, active pipeline run — in addition to the files-touched list. NO fabricated data (only fields genuinely present in session_context).
5. AC5: post_compact_injection stays fire-once (_compacted reset after injection) and returns via hookSpecificOutput.additionalContext (unchanged channel).
6. AC6: R19 language classification is provably unaffected — the enriched injection rides the additionalContext channel, which never enters the string _classify_message_language sees (verified: user prompt is stripped+classified separately).
7. AC7: the stale comment at prompt_builder.py:2108 ('task_budget ... is the independent cost cap') is corrected — task_budget is the autocompact TRIGGER line, not a cost cap (STEERING #2); co-update the comment in the same diff (R7/C052).
8. AC8: tests cover — threshold derivation (1M→750K, fallback on unknown window), enrichment presence (new fields appear when signal present, absent when not), fire-once, and an R19 non-pollution assertion.


## 3. Design & Approach
**Research Findings (THINK):**
- task_budget site: prompt_builder.py:2149-2155, inside build_options; `model = self.resolve_model(agent_config)` is in scope at ~2031; PromptBuilder.get_model_context_window(model) (~:820 → model_registry.context_window_for) returns the window. So 0.75×window is a 1-line derivation, no new plumbing.
- Fallback need is REAL: get_model_context_window returns model_registry.DEFAULT_CONTEXT_WINDOW for unknown models (deliberately kept above the L1 threshold), so it never returns 0 — but a defensive max(floor, round(0.75*window)) guards against a future tiny-window model making task_budget absurdly small (which would thrash autocompact). Floor chosen so a 1M model → 750K and a conservative/unknown model still gets a workable budget.
- channel 400K: keep (Q1=A). It is an unattended-safety line paired with max_turns=100, a different rationale from desktop's prefill-tax reduction. 400K is NOT a clean fraction of any standard window, so unifying would be a semantic change XG didn't ask for. Leave the channel branch literal, document why.
- post_compact_injection enrichment signal is REAL and already read in a SIBLING hook: create_pre_compact_checkpoint (runtime_hooks.py:598-616) reads the _observations ring via ring.snapshot(last_n) + ring.all_completed() → dominant tool, test_runs/pass_rate; also _files_touched, _corrections_count, _ran_tests, git commits (derivable), _active_pipeline_run_id. The enrichment WIRES this same real signal into post_compact_injection — it invents nothing.
- R19 safety is STRUCTURAL, not best-effort: _classify_message_language reads only _extract_field(input_data,'prompt') (the user prompt). post_compact_injection returns via hookSpecificOutput.additionalContext — a separate SDK channel that never enters the classified string. Enriching the injection text CANNOT reach R19. Verified runtime_hooks.py:1355-1367.
- fire-once: post_compact_injection gates on ctx['_compacted'] and resets it to False after building (runtime_hooks.py:1203,1216). Enrichment must stay INSIDE that gate and keep the reset — add fields, don't restructure the gate.
- stale comment: prompt_builder.py:2108 calls task_budget 'the independent cost cap' — wrong per STEERING #2 (it's the autocompact TRIGGER line; autocompact summarizes+continues, it does not truncate work). Co-update the comment (R7/C052) in the same diff.

**Alternatives Evaluated:**
- SIMPLICITY — effort: S (1 session)
- FLEXIBILITY — effort: S-M
- DELETION — effort: XS

**Chosen Approach:** Two targeted backend edits + comment fix + test updates. (1) prompt_builder.py build_options: replace desktop literal task_budget {'total':800_000} with a window-derived value using a named module constant AUTOCOMPACT_WINDOW_FRACTION=0.75 and a FLOOR guard: total = max(FLOOR, round(0.75 * get_model_context_window(model))). model is already in scope (~:2031). channel branch keeps {'total':400_000} + a why-comment. Fix the :2108 stale 'independent cost cap' comment → 'autocompact trigger line (STEERING #2: not a cost cap; autocompact summarizes+continues, never truncates work)'. (2) runtime_hooks.py post_compact_injection: inside the existing _compacted fire-once gate, append extra additionalContext lines from REAL session_context signal — recent activity (dominant tool + recent intents from the _observations ring), test status (_ran_tests / pytest pass), recent git commits, _corrections_count, _active_pipeline_run_id — each line guarded to appear only when its signal is present. Keep the files-touched line, the fire-once reset, and the hookSpecificOutput.additionalContext channel.

**Success Criteria:**
- A 1M-model desktop session computes task_budget=750_000 (verified by a unit test calling build_options or the extracted helper).
- An unknown/small-window model computes a workable floor-guarded budget, never 0.
- A compaction injects an enriched continuation block carrying real recent-activity/test/commit signal; a bare session (no signal) injects only the base + files line.
- R19 classification test passes unchanged with the enriched injection active.

**Always:**
- task_budget direction is DOWN/window-bound (0.75×, ≤ old 800K)
- post_compact_injection fire-once + additionalContext channel preserved
- enrichment uses only real session_context fields (no fabricated data)
- run affected backend tests before commit

**Never:**
- re-introduce task_budget as a 'cost cap' that truncates in-flight work (STEERING #2 / O030)
- let enriched injection pollute R19 classification
- fabricate task/decision data the agent doesn't actually have
- raise the threshold above 800K


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_d9c3ba2a | 9,000 |  |
| think | completed | art_e6623741 | 11,000 |  |
| plan | completed | art_24ef516d | 9,000 |  |
| build | completed | art_98896740 | 40,000 |  |
| review | completed | art_df43e512 | 15,000 |  |
| test | completed | art_f810a670 | 25,000 |  |
| deliver | recorded | art_036a4b71 | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 109,000 | **Stages:** 6/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 03:46:24 | - |
| think | 03:47:50 | 1.4 min |
| plan | 03:49:34 | 1.7 min |
| build | 03:57:46 | 8.2 min |
| review | 04:00:06 | 2.3 min |
| test | 04:02:18 | 2.2 min |
| deliver | 04:08:47 | 6.5 min |
| reflect | - | - |

Slowest stage: `build` at 8.2 min (37% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

## 5. TDD Results
| Metric | Value |
|--------|-------|
| Tests total | 0 |
| Tests passed | 0 |
| Tests failed | 0 |
| New tests added | 0 |
| Duration | 0s |
| Regressions | 0 |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | profile=full (existing-feature, 2-file backend, not iterativ | mechanical | size/bug gates ruled out trivial/bugfix/goal |
| evaluate | channel 400K kept (Q1=A) | taste | unattended safety line, different rationale from d |
| think | A + named-constant AUTOCOMPACT_WINDOW_FRACTION=0.75 (not a s | taste | self-documenting + one-line retune, no config-plum |
| plan | FLOOR = old CLI default 128K as safe lower bound | taste | never let a tiny-window model disable autocompact; |
| build | extracted _compute_desktop_task_budget pure helper for unit- | mechanical | skeptic-friendly; isolates the derivation from bui |
| review | single-pass review (backend-only, <100 code lines, not auth/ | mechanical | below fan-out threshold; spec sub-agent still mand |
| test | Layer 4 skipped (cross_boundary=false) | mechanical | no seam; ruled_out attestation in EVALUATE |

**Summary:** 4 mechanical, 3 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**2 findings** (verdict: ?)
- [HIGH] prompt_builder.py max_turns-block 'Safety:' comment still called task_budget 'th
- [MED] prompt_builder.py channel max_turns comment 'Real safety comes from task_budget=

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/prompt_builder.py`
- `backend/core/runtime_hooks.py`
- `backend/tests/test_compaction_tuning.py`
- `backend/tests/test_compact_notice.py`

**+0 / -0 lines** | 4 files

## 9. Lessons
- [principle] A threshold that reads as a 'cost cap' comment but is really a trigger-with-continue (autocompact summarizes+continues, never truncates) is NOT governed by the no-cost-cap rule — the distinguishing test is whether crossing it DESTROYS in-flight work or just SUMMARIZES-and-continues. Lowering such a trigger to reduce per-turn resident-context cost is a legitimate tuning direction, not a banned cap.
- [pitfall] Changing a hardcoded value to a derived expression leaves STALE COMMENTS in SIBLING blocks that referenced the old literal — here two comments in the max_turns block still called task_budget an '800K cost cap' after it became window-derived. A diff-local review misses them; grep the OLD literal + its DESCRIPTION ('cost cap', '800K') across the whole file, not just the changed lines (C052 + R30#6 whole-file re-read).
- [decision] Bind a magic threshold to the resource it tracks (0.75 × context window) via a named constant rather than a frozen number — it then follows the model automatically on the next model change, and a floor guard (set to the old known-working lower bound) prevents a future tiny-window model from disabling the mechanism. Prefer a named module constant over a settings knob when the value is fixed by directive (YAGNI on the config surface).


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 04:08 UTC*
