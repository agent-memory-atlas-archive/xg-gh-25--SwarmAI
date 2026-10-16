# Autonomous Pipeline Report: Run B (G5) — content-safety host-path matcher scan_context fix

**Run ID:** run_03c40277 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-16 18:47 UTC | **Duration:** 52.7 min (in progress) | **Tokens:** 40,000
**Gate 1:** PASS_WARN | **Files:** 3 | **Tests:** True/1

## TL;DR
Run B (G5, bugfix) — 修 content_safety_scan host-path matcher 的 context 误报/漏报。backend/core/ddd_packager.py 的 _HOST_PATH_PATTERNS 第 91 行 backend/(skills|scripts)/ 对 DDD 包是正确 dev-command 泄漏检测(run_aaa50c5

## 1. Requirement
Run B (G5, bugfix) — 修 content_safety_scan host-path matcher 的 context 误报/漏报。backend/core/ddd_packager.py 的 _HOST_PATH_PATTERNS 第 91 行 backend/(skills|scripts)/ 对 DDD 包是正确 dev-command 泄漏检测(run_aaa50c56),但对 run-commit 提交进源码仓的 REPORT-B 是误报(repo 本身就是 backend/)。方案A:给 content_safety_scan/_scan_text 加 scan_context 参数(package|source-repo),第91行只在 package context 生效;run-commit 传 source-repo,package_ddd 传 package。改完双向 counter-test:真 /Users/<user> 绝对路径两 context 都 BLOCK,backend/skills/ 只在 package context flag。安全面 matcher,不放松 package publish 检测。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Run B (G5, bugfix) — 修 content_safety_scan host-path matcher 的 context 误报/漏报。backend/core/ddd_packager.py 的 _HOST_PATH_PATTERNS 第 91 行 backend/(skills\|scripts)/ 对 DDD 包是正确 dev-command 泄漏检测(run_aaa50c56),但对 run-commit 提交进源码仓的 REPORT-B 是误报(repo 本身就是 backend/)。方案A:给 content_safety_scan/_scan_text 加 scan_context 参数(package\|source-repo),第91行只在 package context 生效;run-commit 传 source-repo,package_ddd 传 package。改完双向 counter-test:真 /Users/<user> 绝对路径两 context 都 BLOCK,backend/skills/ 只在 package context flag。安全面 matcher,不放松 package publish 检测。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG Run B 方案 A — Run A 现场实测该 pattern 对 REPORT-B 误报 | confirmed | ● | Given REPORT.md 含 repo-relative backend/scripts/artifact_cli.py, when run-commit 以 scan_context=source-repo 扫描, then 无 host-path finding(误报消除) |
| FR-2 | bug | ddd-derived: ddd_packager.py:88-91 注释 — 消费者机器无 backend/ 树 | confirmed | ● | Given DDD 包含 backend/skills/foo 路径, when package_ddd 以 scan_context=package 扫描, then host-path finding 仍产生,publish 仍 BLOCK |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | scan_context 的默认值该是什么? | A. package(保守默认) | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. package(保守默认) (🧠 AI 替你拍的板 — resolution: self-answer:默认 package 保留最严行为,只有 run-commit 这个明确知道目的地是源码仓的 call site 显式传 source-repo。新 call site 若忘传参数 → 默认全查,fail-safe(宁可误报不可漏报,安全面)。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | high | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. content_safety_scan/_scan_text 接受 scan_context 参数(枚举 package|source-repo),第91行 backend/(skills|scripts)/ pattern 只在 context=package 时产生 host-path finding
2. run-commit (artifact_cli.py:3586) 传 scan_context=source-repo,package_ddd (ddd_packager.py:1908) 传 scan_context=package
3. 双向 counter-test:(a) 真 /Users/<user> 绝对路径在 package 和 source-repo 两种 context 下都仍被 flag 为 host-path(其他4个 pattern 不受 context 影响);(b) backend/skills/foo 在 package context 被 flag、在 source-repo context 放行
4. run_aaa50c56 的包泄漏检测完整保留:package context 下 backend/skills/ 仍 BLOCK publish


## 3. Design & Approach
**Research Findings (THINK):**
- 第91行 pattern 在 _HOST_PATH_PATTERNS tuple 里和前4个真 host-path pattern(.swarm-ai/SwarmWS、/Users|home/.../.swarm-ai、SwarmAI-Workspace)混在一起,全部在 _scan_text:285-288 的一个循环里无条件 fire,kind 都标 host-path。要 context 条件化第91行,必须把它从前4个分离出来(否则条件会误伤真 host-path pattern)
- 两个唯一 call site 消费语义不同但根因同一:package_ddd:1908 是真 BLOCK(publish raise PackagingError),run-commit artifact_cli.py:3586 是 WARNING(cry-wolf,本地 commit 照常进)。两者都传 external=True,external flag 无法区分目的地有无 backend/ 树
- run-commit 的 warning detail 用 f.kind 渲染([{f.kind}]),package_ddd 的 blocking 过滤也 key on f.kind=='host-path'/'secret' —— 所以新增一个 kind 值会牵动这两个 .kind 消费者(skeptic 指出的点),方案 B 的 blast radius 更大
- scan_context 默认值 = package(保守 fail-safe):新 call site 忘传 → 默认全查,宁可误报不可漏报(安全面)。只有 run-commit 这个明确知道目的地是源码仓的 call site 显式传 source-repo

**Alternatives Evaluated:**
- SIMPLICITY — effort: S / 1 session
- FLEXIBILITY — effort: M / 1 session

**Chosen Approach:** A (SIMPLICITY):给 content_safety_scan + _scan_text 加 scan_context: str 参数(默认 'package',fail-safe)。把 _HOST_PATH_PATTERNS 第91行 backend/(skills|scripts)/ 分离成模块级独立常量 _DEV_COMMAND_PATH_PATTERN。_scan_text 循环:前4个真 host-path pattern 保持无条件 fire;第91行(_DEV_COMMAND_PATH_PATTERN)仅当 scan_context=='package' 时 fire,kind 仍标 host-path(不动 ScanFinding.kind 枚举=零 .kind 消费者 blast radius)。两个 call site:artifact_cli.py:3586 run-commit 传 scan_context='source-repo',ddd_packager.py:1908 package_ddd 显式传 scan_context='package'

**Success Criteria:**
- pytest backend/tests/test_ddd_packager.py 全绿(含新 counter-test + 现有 host-path/secret 测试零回归)
- 真 host-path 两 context 都 BLOCK(mutation:删 context gate 不影响前4个 pattern)
- backend/skills/ 只在 package context flag(mutation:把 scan_context gate 改成无条件 → source-repo counter-test RED)

**Always:**
- 前4个真 host-path pattern 保持无条件 fire(两 context 都查)
- scan_context 默认 'package'(最严,fail-safe)
- mutation-prove 双向 counter-test 非 vacuous

**Never:**
- 不删第91行(会 regress run_aaa50c56 包泄漏检测)
- 不动 ScanFinding.kind 枚举(避免 .kind 下游消费者 blast radius)
- 不放松 package context 下的任何检测(安全面只收严不放松)
- 不把 scan_context 默认设成 source-repo(新 call site 忘传=漏报)


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| think | 方案A SIMPLICITY:分离第91行+scan_context参数+kind不变 | taste | 方案B精确分类收益不值其漏报风险;A零.kind消费者blast radius+保住run_aaa5 |

**Summary:** 0 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**1 findings** (verdict: ?)
- [LOW] backend/core/ddd_packager.py _scan_text() line 306: the dev-command scan gate wa

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/ddd_packager.py`
- `backend/scripts/artifact_cli.py`
- `backend/tests/test_ddd_packager.py`

## 9. Lessons
- 一个安全-matcher 的 context gate 写成正向 allowlist (`if ctx == "strict-value"`) 会在 typo/未知值上静默 fail-OPEN(跳过严格扫描)——与它承诺的 fail-safe 默认自相矛盾。正解是反转成 fail-CLOSED:`if ctx != "<唯一已知安全值>"`,只有那个值抑制,其余(默认/typo/未来新值)全走严格路径。判据:gate 的两个方向哪个是'漏检',就让未知值落到'多检'那边(RP46/RP49)。
- 两个 fresh 对抗专家(correctness + security)单消息并行 spawn(C054),独立抓到同一个 fail-open 发现——这就是对抗审查相对自审的价值证明:同一份代码我 THINK/PLAN 自信'fail-safe 默认 package'已足够,但没验未知值路径。并行不损归属,且双专家交叉确认把一个 LOW-conf 发现的可信度顶起来。
- 并行 session 共享一个 git repo 时,`git add <file>` 会把别人在途的 unstaged 改动一起 stage。R29 的精确分离法:`git reset HEAD <file>` → `git diff <file> > all.patch` → python 按 hunk header 文本(函数名)提取只属于本 run 的 hunk → `git apply --cached <mine.patch>`。比 `git add -p`(不可交互)可靠,比整文件 add 安全。
- 改一个被 docstring/定义注释/gate 三处引用的常量语义时(R7/RP48),三处注释都要同步——本 run 的 scan_context gate 措辞在 _scan_text 签名 docstring、gate 行注释、_DEV_COMMAND_PATH_PATTERN 定义注释三处都写了'== package',反转成 fail-closed 后必须三处一起改,否则留下与代码矛盾的 stale comment。


## 10. Known Gaps & Attention Flags
- Validator blocked 5 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 18:47 UTC*
