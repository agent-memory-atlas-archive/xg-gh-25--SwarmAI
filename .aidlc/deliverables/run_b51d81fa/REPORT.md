# Autonomous Pipeline Report: 根修 B-copy REPORT §8 host-path 泄漏: _render_review_files_section relativize 路径

**Run ID:** run_b51d81fa | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 19:10 UTC | **Duration:** 30.6 min (in progress) | **Tokens:** 164,000
**Gate 1:** PASS | **Files:** 2 | **Tests:** True/1

## TL;DR
根修 B-copy REPORT §8 host-path 泄漏: _render_review_files_section 把路径原样渲染, caller 传的绝对路径(run-commit 需要)被原样写进公开 repo 的 B-copy。在渲染时 relativize 到 git repo root。

## 1. Requirement
根修 B-copy REPORT §8 host-path 泄漏: _render_review_files_section 把路径原样渲染, caller 传的绝对路径(run-commit 需要)被原样写进公开 repo 的 B-copy。在渲染时 relativize 到 git repo root。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 根修 B-copy REPORT §8 host-path 泄漏: _render_review_files_section 把路径原样渲染, caller 传的绝对路径(run-commit 需要)被原样写进公开 repo 的 B-copy。在渲染时 relativize 到 git repo root。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: pipeline 根修 A — 根上解决 host-path 来回折腾 | confirmed | ● | Given source_files 含绝对路径 /ABS/repo/backend/core/x.py, target_repo_root=/ABS/repo, when _render_review_files_section 渲染 §8, then 输出 '- `backend/core/x.py`', 无绝对前缀 |
| FR-2 | bug | ddd-derived: by_repo staging list 与报告渲染是两条路径, relativize 只碰渲染 | confirmed | ● | Given run-commit 运行, when git add staging, then 仍用 by_repo 原始(绝对)路径, 不受 §8 relativize 影响 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | fix 该放 renderer 还是让 caller/build.md 改成传相对路径? | 放 renderer。caller 传绝对是对的(run-commit 的 git add 跨 repo 需要绝对, build.md 有意如此), 两个需求(commit 要绝对 vs 报告要相对)在 renderer 这个唯一分叉点调和最干净 —— renderer 已能拿到 target_repo_root(_generate_review_deliverable 签名已有), 只需 thread 进去。改 build.md 传相对会破坏 run-commit 的跨 repo staging。 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: 放 renderer。caller 传绝对是对的(run-commit 的 git add 跨 repo 需要绝对, build.md 有意如此), 两个需求(commit 要绝对 vs 报告要相对)在 renderer 这个唯一分叉点调和最干净 —— renderer 已能拿到 target_repo_root(_generate_review_deliverable 签名已有), 只需 thread 进去。改 build.md 传相对会破坏 run-commit 的跨 repo staging。 (🧠 AI 替你拍的板 — resolution: 实证: _generate_review_deliverable(.., target_repo_root, source_files) 签名已含 repo root(:3450); by_repo staging(:3897)与报告渲染(:3930→383→316)是两条独立路径, relativize 渲染侧不碰 staging。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 9.00 | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. B-copy REPORT.md §8 Files Changed 渲染出的路径是相对 git repo root 的 (如 backend/core/x.py), 不含任何绝对/机器本地前缀
2. 绝对路径输入被 relativize; 已是相对的路径原样保留; repo root 外或无法 relativize 的路径 fail-safe 保留原值(不崩不丢)
3. run-commit 的 git add staging 路径不受影响(仍用 by_repo 的原始路径, relativize 只作用于报告渲染输出)
4. 空 source_files 的既有诚实渲染('无 committed 文件')不破


## 3. Design & Approach
**Research Findings (THINK):**
- 方案被 Gate-0 锁定: 在 _render_review_files_section relativize, thread target_repo_root 从 _generate_review_deliverable(已有该参数) → _project_report_for_review → renderer。改 by_repo 会破坏跨 repo git add。
- relativize 方法有真实抉择: Path.relative_to 对 outside-root 和 already-relative 都抛 ValueError → try/except 保留原值; os.path.relpath 不抛但对这两种 case 产出 '../..' 垃圾路径(更糟, 一个 resolve 错的路径)。实测两者行为。
- 正解 = Path.relative_to + try/except 保留原值: 它的两个失败 case(outside-root / already-relative)恰好就是'应保留原值'的 case —— already-relative 原样透传, outside-root 无法 relativize 保留原样。os.path.relpath 的 ../.. 输出是静默错误, 必须避免。

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS
- QUALITY-alt — effort: XS

**Chosen Approach:** 给 _render_review_files_section + _project_report_for_review 加可选 repo_root 参数(默认 None = 不 relativize, 保持既有测试行为)。renderer 对每个路径 try Path(f).relative_to(repo_root) → 成功用相对, ValueError(outside-root / already-relative)保留原值。production 调用链(_generate_review_deliverable 的 target_repo_root → _project_report_for_review → _render_review_files_section)thread repo_root。by_repo staging 不碰。

**Success Criteria:**
- test_deliverable_checkin.py 全绿 + 新 relativize test 绿 + mutation-proof(去 relativize → 绝对 case RED)
- 一个带绝对 files_touched 的 run, 其 B-copy §8 渲染相对路径(端到端)

**Always:**
- repo_root 默认 None 保持既有调用兼容
- ValueError fail-safe 保留原值(不崩不产 ../..)
- mutation-proof 新 test(去 relativize → 绝对 case RED)

**Never:**
- 不用 os.path.relpath(对 already-rel 产 ../.. 垃圾)
- 不改 by_repo/files_touched 的路径格式(破坏跨 repo git add)
- 不改 source-A REPORT 的渲染(它另一条路径, 已是相对)


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | fix 放 renderer 而非 by_repo/build.md | judgment | commit 要绝对 vs 报告要相对, renderer 是唯一调和分叉点; 改 by_repo  |
| review | symlink test 平台无关化 (REVIEW spec caught Linux-vacuous) | taste | 显式构造 symlink 比依赖平台 /tmp 更鲁棒, R7 本 run 修 |

**Summary:** 0 mechanical, 1 taste, 1 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**2 findings** (verdict: ?)
- [MED] backend/scripts/artifact_cli.py _generate_review_deliverable: 我按 line-range 切 pa
- [LOW] [KNOWN-BOUNDARY, note-only, out-of-scope] backend/scripts/artifact_cli.py _proje

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/scripts/artifact_cli.py`
- `backend/tests/test_deliverable_checkin.py`

## 9. Lessons
- [pitfall] 一个把路径原样 f-string 渲染进「要提交进公开 repo」的报告的 renderer, 若它的输入来自 by_repo/files_touched(绝对路径, 为 run-commit 的跨 repo git add 而存)就会泄漏机器本地路径(R30#7)。根修在 renderer relativize, 不在数据源 —— commit 要绝对 vs 报告要相对是两个需求, 在渲染这个唯一消费分叉点调和。
- [pitfall] relativize 用 Path.relative_to 必须对 BOTH sides 先 .resolve(): git rev-parse --show-toplevel 把 symlink 规范化(macOS /tmp→/private/tmp, Linux CI /tmp 不是 symlink), 而 files_touched 可能是未规范化形式, 裸 relative_to 会抛 ValueError → fail-safe 保留绝对 → 泄漏在恰恰最该防的 temp/CI 环境存活。Gate-1 对抗抓到, self-review 没抓到。
- [decision] 测试一个'symlink 规范化不匹配'的 bug, 不能依赖平台的 /tmp 恰好是 symlink(Linux 上不是 → 测试 vacuous)。要用 tmp_path 显式构造 symlink(link→canonical, repo_root 用 canonical, 文件走 link), 才跨平台 mutation-proof。REVIEW spec-compliance 发现这个 vacuous 风险。
- [correction] 共享工作树多 session 并行时, 从一个被别的 session 污染的文件里按行号范围切 patch 隔离自己的改动, 粗粒度 line-range 会误把相邻的 foreign hunk(同函数区域的 content_safety_scan 改动)当成自己的。正解: 切 patch 后按 hunk 内容(grep foreign 符号)过滤, 别只按行号; 且 Gate-2 correctness 对抗是最后一道能抓到'diff 里混入了 brief 没列的改动'的网。


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 19:10 UTC*
