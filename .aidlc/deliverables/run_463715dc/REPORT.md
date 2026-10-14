# Autonomous Pipeline Report: 修复 adversarial_commit_gate pending-path 解析(heredoc/-F -/多行脚本)+ 多commit链 fail-open

**Run ID:** run_463715dc | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-14 01:36 UTC | **Duration:** 26.9 min (in progress) | **Tokens:** 129,000
**Gate 1:** N/A | **Files:** 2 | **Tests:** 0/0

## TL;DR
修复 adversarial_commit_gate 的 pending-path 解析缺陷:heredoc/-F -/多行 Bash 脚本中的 git commit,其 message 正文被 _pending_commit_paths 误判为 positional pathspec,导致已对抗审查过的合法 commit 被误 DENY。security_hooks.py。必须 fail-saf

## 1. Requirement
修复 adversarial_commit_gate 的 pending-path 解析缺陷:heredoc/-F -/多行 Bash 脚本中的 git commit,其 message 正文被 _pending_commit_paths 误判为 positional pathspec,导致已对抗审查过的合法 commit 被误 DENY。security_hooks.py。必须 fail-safe 不新增 fail-open 漏洞。

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 7.00 | |
| Priority | 7.00 | |
| Feasibility | 9.00 | |

**Acceptance Criteria:**
1. AC1: heredoc/-F - 的 commit(message 正文含类路径词)+ 覆盖真实 staged 路径的 adversarial marker → gate approve(不再误 DENY)
2. AC2: 多行 Bash 脚本(含 ;/&&/换行 + 其它命令)里的 git commit → 只有真实 staged/pathspec 进 pending,其它命令的 token 不泄漏
3. AC3: fail-safe 不变量保持:真实的 positional pathspec(git commit -- path) 仍被正确收集;一个真未审查的 path 绝不能因新解析被漏掉而蒙混 approve
4. AC4: 已有安全测试全绿(cross-repo DENY、-S secret.py pathspec、-a sweep 等不回归)


## 3. Design & Approach
**Research Findings (THINK):**
- 同文件已有 Gate-2 加固的 _HEREDOC_BODY_RE(:1240,带 ReDoS cap+终止符锚定)和 _SEPARATORS(:1268);backgrounding gate 用 replace(\n, ; )+分段隔离子命令。_pending_commit_paths 完全没复用这些 → 修复 = 复用而非新造(C042)。
- fail-safe 关键:真实 positional pathspec(git commit -- path)在 commit segment 内、不在 heredoc 正文、不跨分隔符,所以 strip+截断不碰它;但这是 AC3 承重假设,BUILD 必须有测试守住。

**Alternatives Evaluated:**
- SIMPLICITY/复用 — effort: S ~10 行,复用已测工具
- QUALITY/独立 — effort: M,新解析器+测试负担

**Chosen Approach:** 在 _pending_commit_paths 的 shlex.split 前插入预处理:(a) _HEREDOC_BODY_RE.sub 删 heredoc 正文(带 _HEREDOC_MAX_OPENERS ReDoS cap);(b) 换行→;、分词、按 _SEPARATORS 分段,只保留含 commit token 的 segment;(c) 对该 segment 做原有 flag/pathspec walk。复用已加固工具,不造新 tokenizer。

**Success Criteria:**
- AC1-4 全有测试
- mutation-verify:删预处理→heredoc/多行测试变 RED
- 三个相关测试文件全绿

**Always:**
- 复用已加固 _HEREDOC_BODY_RE + _HEREDOC_MAX_OPENERS ReDoS cap
- 保留 except ValueError 兜底
- 真实 positional pathspec 必须仍被收集

**Never:**
- 不放宽 gate 安全不变量(covered⊇pending 才 approve)
- 不新增 fail-open 路径
- 不碰消费方 _session_adversarial_coverage/create_adversarial_commit_gate
- 不造新 tokenizer(C042)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_b50d0b81 | 9,000 |  |
| think | completed | art_63ab2f47 | 9,000 |  |
| plan | completed | art_9b48c864 | 9,000 |  |
| build | completed | art_93499926 | 30,000 |  |
| review | completed | art_1287aa43 | 12,000 |  |
| test | completed | art_3ef2328c | 15,000 |  |
| deliver | completed | art_a8fe52da | 40,000 |  |
| reflect | completed | - | 5,000 |  |

**Total tokens:** 129,000 | **Stages:** 8/8 completed | **Validation blocks:** 1

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 01:11:47 | - |
| think | 01:12:53 | 1.1 min |
| plan | 01:14:27 | 1.6 min |
| build | 01:22:40 | 8.2 min |
| review | 01:24:33 | 1.9 min |
| test | 01:26:32 | 2.0 min |
| deliver | 01:35:33 | 9.0 min |
| reflect | - | - |

Slowest stage: `deliver` at 9.0 min (38% of the 6 measured inter-stage gaps).

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
| evaluate | profile=bugfix | mechanical | clear bug, known root cause via repro, single-func |
| think | approach A reuse _HEREDOC_BODY_RE over B new tokenizer | taste | B builds a mechanism already in the file (C042); A |
| build | AC2 命令改为 trailing && 命令(原 echo/status 版本 vacuous) | mechanical | 原 AC2 在旧代码也 pass=vacuous(RP47);改为 commit && cp evi |
| deliver | Gate-2 HIGH fail-open 修复:单→多 commit segment union | mechanical | 对抗发现的真 fail-open,必修;修复方向是 adversarial 推荐的 union-al |

**Summary:** 3 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**1 findings** (verdict: ?)
- [HIGH] security_hooks.py::_pending_commit_paths — 单 commit segment 选择丢弃链式第二个 commit 的 p

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/security_hooks.py`
- `backend/tests/test_reviewed_paths_multirepo.py`

**+0 / -0 lines** | 2 files

## 9. Lessons
- [correction] authorship trap 又一次(CLASS A):我给 _pending_commit_paths 的修复写了明确的 fail-safe 注释(只缩假路径不丢真路径),却没想到多 commit 链(git commit A && git commit B)——我的单 segment 选择把第二个 commit 的 positional pathspec 丢出 pending,正是我声称不可能的 fail-open。对抗 sub-agent 抓的,不是我。教训:当一个安全解析函数的输入是整条 shell 命令时,先枚举输入的所有合法形态(单命令/链式多命令/heredoc/wrapper),再写 fail-safe 断言;『我理解它』≠『它对所有输入正确』。
- [principle] 修复一个解析 bug 时,收敛的方向是『正确识别全部目标形态并 union』,不是『选第一个匹配』。选第一个在单实例测试里永远 GREEN,但对 N>1 的输入 silently under-collect——而 under-collect 在安全 gate 里就是 fail-open。任何『pending/covered 集合』的计算,少收永远比多收危险。
- [pitfall] security gate 的 pending-path 计算必须对整条命令的 ALL commit segments 生效,不能只认第一段:链式命令是一次 PreToolUse 调用,gate 只算一次 pending;遗漏任何一段 = 那段提交的未审查文件蒙混过关。复用已有 _segment_is_git_commit + segment-split 时,要 union 所有匹配段,不是 next(first)。
- [decision] 复用同文件已加固的 _HEREDOC_BODY_RE + _segment_is_git_commit + segment-split(而非新写 tokenizer)是对的——它让 _pending_commit_paths 与 _command_has_git_commit 的命令解析口径统一,ReDoS cap 等加固自动继承。C042:一遇问题先查机制是否已存在。
- authorship-trap-recurred
- union-all-segments-not-first
- gate-pending-must-cover-all-commit-segments


## 10. Known Gaps & Attention Flags
- Validator blocked 1 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 01:36 UTC*
