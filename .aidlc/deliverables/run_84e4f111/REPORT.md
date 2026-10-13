# Autonomous Pipeline Report: 下线死功能:pipeline scope-depth 轴(#5)— symmetric atomic deletion

**Run ID:** run_84e4f111 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-13 09:23 UTC | **Duration:** 149.4 min (in progress) | **Tokens:** 0
**Gate 1:** N/A | **Files:** 9 | **Tests:** True/1

## TL;DR
下线死功能:pipeline scope-depth 轴(#5)。P9 已验证整条 cosmetic、端到端从未工作:后端 PipelineRunDetail 无 depth 字段(前端永远 standard)、无代码读 run.json 的 depth 调 rigor、--depth CLI flag 文档 0 次、拼错静默降级、sdm-* CSS 类未定义、depth 免疫测试设的 env v

## 1. Requirement
下线死功能:pipeline scope-depth 轴(#5)。P9 已验证整条 cosmetic、端到端从未工作:后端 PipelineRunDetail 无 depth 字段(前端永远 standard)、无代码读 run.json 的 depth 调 rigor、--depth CLI flag 文档 0 次、拼错静默降级、sdm-* CSS 类未定义、depth 免疫测试设的 env var 无代码读。整个回退/删除该功能(ScopeDepthMatrix 组件 + --depth flag + resolve_depth + depth schema 字段 + 两个 depth 测试文件 + 相关 skill 文档措辞),而非补全。关键:精确区分 scope-depth-axis 死码 vs 无关的 depth 用法(VirtualizedTree 树深度、Ousterhout Depth&Seam、think_depth)——只删前者。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 下线死功能:pipeline scope-depth 轴(#5)。P9 已验证整条 cosmetic、端到端从未工作:后端 PipelineRunDetail 无 depth 字段(前端永远 standard)、无代码读 run.json 的 depth 调 rigor、--depth CLI flag 文档 0 次、拼错静默降级、sdm-* CSS 类未定义、depth 免疫测试设的 env var 无代码读。整个回退/删除该功能(ScopeDepthMatrix 组件 + --depth flag + resolve_depth + depth schema 字段 + 两个 depth 测试文件 + 相关 skill 文档措辞),而非补全。关键:精确区分 scope-depth-axis 死码 vs 无关的 depth 用法(VirtualizedTree 树深度、Ousterhout Depth&Seam、think_depth)——只删前者。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | task | user-stated: XG: #5 depth 整个回退/下线,P9 该不该存在的答案是删 | confirmed | ● | Given scope-depth 从未工作(无 production 消费方), when 删除 DEPTH_TIERS/DEPTH_DEFAULTS/normalize_depth/resolve_depth + --depth arg + run.json 写入, then grep 0 剩余消费方,import 不断 |
| FR-2 | task | user-stated: XG #5 | confirmed | ● | Given 后端永不发 depth 字段 → 前端永远 standard + sdm-* CSS 未定义, when 删除组件 + import + render + 字段, then 前端 build clean,无悬空 depth 读取 |
| FR-3 | task | ddd-derived: 两个 code-trace agent 分离出 60+ 无关 depth 用法 | confirmed | ● | Given 'depth' 一词在 60+ 处有无关含义(树深/hop/schema 校验/thinking), when 只删 scope-depth-axis, then KEEP 清单的测试删后仍全绿 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 补全还是删除死功能? | A. 删除/下线 | 👤 user |
| Q2 | _check_depth / _check_semantic_depth 是不是 scope-depth 的一部分要删? | B. 否,是 schema 校验器,KEEP | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q2: B. 否,是 schema 校验器,KEEP (🧠 AI 替你拍的板 — resolution: code-trace + DDD(IMPROVEMENT line 2231/959)确认 _check_depth 是 artifact 结构完整性校验,与 scope-depth-axis 无关)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 4.00 | |
| Feasibility | 5.00 | |
| **ROI** | **4.500** | **GO** |

**Acceptance Criteria:**
1. AC1: 后端 scope-depth 死码删除——pipeline_profiles.py 的 DEPTH_TIERS/DEPTH_DEFAULTS/normalize_depth/resolve_depth,artifact_cli.py 的 --depth argparse + run.json depth 写入 + resolve_depth import。grep 确认 0 剩余 production 消费方。
2. AC2: 前端 scope-depth 死码删除——ScopeDepthMatrix.tsx + .test.tsx 整文件,PipelineOverlay.tsx 的 import + render block,pipelines.ts 的 depth 字段 + camelCase 提取。
3. AC3: 两个 depth 测试文件删除(test_depth_axis.py 验死 resolve_depth,test_depth_immunity.py 设无人读的 env var)。
4. AC4: KEEP 清单零触碰——workspace-tree depth、graph/blast-radius hop depth、validate_depth nesting、think_depth 遥测、Ousterhout 'Depth & Seam' review 词汇、_check_depth/_check_semantic_depth schema 校验器、Bedrock thinking-effort。删除后这些的测试仍全绿。
5. AC5: 删除后 backend + frontend build/import clean,受影响测试套件 0 回归;前端不再读一个后端不写的字段(对称删除,无悬空契约)。


## 3. Design & Approach
**Chosen Approach:** Approach A — symmetric atomic deletion of the end-to-end-dead scope-depth axis, in ONE changeset (backend + frontend together). The write→read loop is already severed at the PipelineRunDetail boundary, so there is no live contract; delete both sides atomically. Delete ONLY the 4 DEPTH symbols from pipeline_profiles (not the module); drop ONLY resolve_depth from the artifact_cli:58 import.

**Success Criteria:**
- grep resolve_depth|normalize_depth|DEPTH_TIERS|DEPTH_DEFAULTS across backend/ (excl deleted files) = 0 hits.
- grep ScopeDepthMatrix across desktop/src = 0 hits.
- backend/tests full suite exit 0; frontend `npm run build` (or tsc) exit 0.
- PipelineRunDetail response model byte-unchanged (it never had depth) — no API contract regression.

**Always:**
- Delete ONLY the 4 DEPTH symbols from pipeline_profiles.py:37-107, leaving normalize_profile/get_profile_stages/is_relaxed_profile/PIPELINE_PROFILES intact (Gate-0 caveat 1).
- Drop ONLY resolve_depth from the artifact_cli.py:58 import line (Gate-0 caveat 2).
- Run full backend suite + frontend typecheck after deletion to prove no dangling reference.

**Never:**
- Do NOT delete pipeline_validator._check_depth / _check_semantic_depth (schema structure validators, NOT the scope-depth axis — the exact KEEP trap).
- Do NOT touch VirtualizedTree row.depth, Ousterhout Depth&Seam review vocab, or think_depth telemetry.
- Do NOT backfill or migrate pre-existing run.json files — the stray `depth` key is inert residue, left as-is.


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_2800feee | 0 |  |
| think | completed | art_538ea074 | 0 |  |
| plan | completed | art_27630d87 | 0 |  |
| build | completed | art_3f78a503 | 0 |  |
| review | completed | art_3146b614 | 0 |  |
| test | completed | art_1dcd1804 | 0 |  |
| deliver | ? | art_413dc10f | 0 |  |
| reflect | ⏭ skipped | - | 0 | Not executed — pipeline completed before REFLECT |

**Total tokens:** 0 | **Stages:** 6/7 completed | **Validation blocks:** 1

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 07:01:15 | - |
| think | 07:44:42 | 43.5 min |
| plan | 07:46:24 | 1.7 min |
| build | 09:11:50 | 85.4 min |
| review | 09:14:38 | 2.8 min |
| test | 09:16:46 | 2.1 min |
| deliver | 09:23:52 | 7.1 min |

Slowest stage: `build` at 85.4 min (60% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/7 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

## 5. TDD Results
| Metric | Value |
|--------|-------|
| Tests total | 1 |
| Tests passed | True |
| Tests failed | 0 |
| New tests added | 0 |
| Duration | 0s |
| Regressions | 0 |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| (no decisions) | | | |

**Summary:** 0 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**⚠️ NOT RUN** — adversarial sub-agent was not spawned during this run.
This is a quality gap. Pipeline DELIVER requires adversarial review.

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/pipeline_profiles.py`
- `backend/scripts/artifact_cli.py`
- `backend/tests/test_pipeline_profiles.py`
- `backend/tests/test_depth_axis.py (deleted — already landed by parallel a532ed9f)`
- `backend/tests/test_depth_immunity.py (deleted — already landed by parallel a532ed9f)`
- `desktop/src/components/layout/ScopeDepthMatrix.tsx (deleted — already landed by parallel a532ed9f)`
- `desktop/src/components/layout/ScopeDepthMatrix.test.tsx (deleted — already landed by parallel a532ed9f)`
- `desktop/src/components/layout/PipelineOverlay.tsx`
- `desktop/src/services/pipelines.ts`

**+0 / -0 lines** | 9 files

## 9. Lessons
**⏭ Skipped** — Not executed — pipeline completed before REFLECT


## 10. Known Gaps & Attention Flags
- Validator blocked 1 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-13 09:23 UTC*
