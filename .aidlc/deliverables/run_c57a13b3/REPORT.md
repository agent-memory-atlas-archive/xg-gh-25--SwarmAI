# Autonomous Pipeline Report: 修 #4:pipeline 自生成的派生物 B 被误判为人工 codefix,污染自主度指标

**Run ID:** run_c57a13b3 | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-13 13:14 UTC | **Duration:** 189.4 min (in progress) | **Tokens:** 0
**Gate 1:** SUPPORTED | **Files:** 2 | **Tests:** True/1

## TL;DR
修复 #4:run-commit 把 pipeline 自己生成的派生物 B(.aidlc/deliverables/<run_id>/ 下的 REPORT.md/requirements.json/run-ref.txt)误判为人工 codefix,污染自主度指标。根因:_generate_review_deliverable 返回的 _b_paths 被加进 by_repo 本地 commit

## 1. Requirement
修复 #4:run-commit 把 pipeline 自己生成的派生物 B(.aidlc/deliverables/<run_id>/ 下的 REPORT.md/requirements.json/run-ref.txt)误判为人工 codefix,污染自主度指标。根因:_generate_review_deliverable 返回的 _b_paths 被加进 by_repo 本地 commit 分组(:3295)→ 进 committed[].files,但从未写回 run.json 的 files_touched → _infer_codefix_from_commits(:3467)对比时 B 不在 files_touched → 判为 avoidable=True 的 human-edit codefix(每个 pipeline run 都自触发,run_44a06138 两次 run-commit 记了 2 条)。修法:B 的派生物是系统已知生成物,必须从 codefix 推断中排除 —— 它们不是未自报的人工编辑。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 修复 #4:run-commit 把 pipeline 自己生成的派生物 B(.aidlc/deliverables/<run_id>/ 下的 REPORT.md/requirements.json/run-ref.txt)误判为人工 codefix,污染自主度指标。根因:_generate_review_deliverable 返回的 _b_paths 被加进 by_repo 本地 commit 分组(:3295)→ 进 committed[].files,但从未写回 run.json 的 files_touched → _infer_codefix_from_commits(:3467)对比时 B 不在 files_touched → 判为 avoidable=True 的 human-edit codefix(每个 pipeline run 都自触发,run_44a06138 两次 run-commit 记了 2 条)。修法:B 的派生物是系统已知生成物,必须从 codefix 推断中排除 —— 它们不是未自报的人工编辑。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG 反馈 #4:3 个真实 run 各多一条 codefix 记录,run_44a06138 两次 run-commit 记 2 条,每个 pipeline run 自触发 | confirmed | ● | Given 一个只生成了 B 派生物、无人工改码的 run, when run-commit 跑 codefix 推断, then 0 条 codefix intervention(B 被排除) |
| FR-2 | task | ddd-derived: MEMORY principle: gate 不能从防御退化为 fail-open;这里是加一个精确排除集,不是删推断 | confirmed | ● | Given 一个 committed、不在 files_touched、也不是 B 的文件, when codefix 推断, then 仍被判为 codefix |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 修法是把 B 从 codefix 推断中排除,还是把 B 写回 files_touched? | A. 把 B 作为已知系统生成物排除集传给 _infer_codefix_from_commits | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. 把 B 作为已知系统生成物排除集传给 _infer_codefix_from_commits (🧠 AI 替你拍的板 — resolution: B 是 pipeline 生成的交付物投影(_generate_review_deliverable 的 verbatim copy),不是 agent 编辑的源码。写进 files_touched 会误导下游(暗示 '这个 run 改了这 3 个文件',而它是 '生成' 非 '改')—— files_touched 的语义是 BUILD 自报改了哪些源码。排除集语义更准:B 既不是人工 codefix 也不是 agent 源码编辑,它是系统 deliverable,本就该在 codefix 推断之外。_b_paths 已在 cmd_run_commit 同一作用域可见(:3274 定义,:3467 使用),传入零额外成本。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 3.00 | |
| Feasibility | 5.00 | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. AC1: run-commit 后,B 的派生物(.aidlc/deliverables/<run_id>/ 下 REPORT.md/requirements.json/run-ref.txt)不再被 _infer_codefix_from_commits 判为 codefix intervention —— 它们是系统生成物,不是未自报的人工编辑。
2. AC2: 真正的人工 codefix(一个 committed 但既不在 files_touched、也不是 B 派生物的文件)仍被正确识别为 codefix —— 排除只针对 B,不削弱整个推断成 fail-open。
3. AC3: 路径形态对齐 —— B 排除在 committed[].files 的 repo-relative 形态下生效(B 的 _b_paths 是 absolute,须经同一 normalizer 归一后比较,与现有 files_touched 对齐机制一致)。
4. AC4: files_touched=None(legacy)仍返回 honest lower-bound(无推断),B 排除不改变这个语义。
5. AC5: run-commit 的 warning 通道不再对纯 B-deliverable 的 run 冒出 'codefix intervention inferred' —— 本 run 自己 dogfood 验证(它自己也生成 B)。


## 3. Design & Approach
**Research Findings (THINK):**
- _infer_codefix_from_commits(commits, files_touched, *, normalizer=None) 是纯函数(normalizer 注入),已经把 absolute↔repo-rel 对齐问题解决了 —— B 的排除必须复用同一 normalizer,否则 absolute _b_paths vs repo-rel committed[].files 排不掉(=没修)。
- _b_paths 与调用点(:3467)在同一函数 cmd_run_commit 作用域内,传入零 plumbing 成本(Gate-0 point 2 确认)。
- 排除法是对的层:files_touched 有 completion_gate/ui_actions/autonomous_rate/daily_activity_hook 多消费方;把 B 写进去会把系统生成物误报成 agent 源码工作,污染全部(Gate-0 point 4)。B 是 DELIVER-time 投影,既非人工 codefix 亦非 agent 编辑。
- docstring :3043 说 caller 'appends to files_touched' —— 实际只 extend 进 by_repo 本地分组,从没写 files_touched(Gate-0 point 1)。R7:修法同时订正这个失实 docstring。

**Alternatives Evaluated:**
- SIMPLICITY — effort: S
- QUALITY — effort: ?

**Chosen Approach:** Approach A — give _infer_codefix_from_commits an optional `known_generated` param (absolute paths of system-generated deliverables). Inside the per-repo loop, normalize known_generated via the SAME injected normalizer and MERGE it into that repo's `tracked` set, so B is treated as already-known and never enters `extra`. cmd_run_commit passes `_b_paths`. Default None → empty → behavior unchanged. Also R7: fix the _generate_review_deliverable docstring (:3043) that falsely claims the caller appends to files_touched.

**Success Criteria:**
- A pure-B run-commit emits 0 'codefix intervention inferred' warnings; interventions[] has no codefix entry for B.
- A run with a REAL unreported human edit still flags that edit as codefix.
- _infer_codefix_from_commits unit tests: known_generated excludes B, non-member still flagged, None=unchanged, path-form normalized.
- _generate_review_deliverable docstring describes actual behavior (stages via by_repo + passes to codefix exclusion), not the false files_touched append.

**Always:**
- Normalize known_generated through the SAME injected normalizer as files_touched (per-repo), reusing the loop's cache idiom.
- Keep the exclusion a precise set of THIS run's actual _b_paths — never a path-prefix wildcard (a real human file under .aidlc/deliverables/ must still be catchable).
- Default known_generated=None → zero behavior change for existing callers + unit tests.

**Never:**
- Do NOT write B into files_touched (THINK-rejected B: pollutes completion_gate/ui_actions/autonomous_rate — B is system-generated, not agent-edited source).
- Do NOT weaken the inference to fail-open — only B members are removed from extra; a genuine unreported human edit still flags.
- Do NOT prefix-match .aidlc/deliverables/ — use the exact _b_paths set (pre-mortem risk: a real human file in that dir would be wrongly excluded).


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_489aab3f | 0 |  |
| think | completed | art_7fe958ae | 0 |  |
| plan | completed | art_c1d848c7 | 0 |  |
| build | completed | art_2cefdc67 | 0 |  |
| review | completed | art_b03a5693 | 0 |  |
| test | completed | art_703801be | 0 |  |
| deliver | recorded | art_df827882 | 0 |  |
| reflect | ⏭ skipped | - | 0 | Skipped — not required for profile 'bugfix' |

**Total tokens:** 0 | **Stages:** 6/7 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 10:06:16 | - |
| think | 10:09:31 | 3.2 min |
| plan | 10:10:43 | 1.2 min |
| build | 10:46:03 | 35.3 min |
| review | 10:48:28 | 2.4 min |
| test | 10:49:25 | 1.0 min |
| deliver | 13:14:10 | 144.8 min |

Slowest stage: `deliver` at 144.8 min (77% of the 6 measured inter-stage gaps).

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
- `backend/scripts/artifact_cli.py`
- `backend/scripts/autonomous_rate_test.py`

**+0 / -0 lines** | 2 files

## 9. Lessons
**⏭ Skipped** — Skipped — not required for profile 'bugfix'


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-13 13:14 UTC*
