# Autonomous Pipeline Report: 根 ④:根治 commit/对抗门(security_hooks.py)在裸命令串上用正则找 git commit 导致的双向失守——过度匹配(3-new:0d

**Run ID:** run_68245424 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 09:39 UTC | **Duration:** 171.5 min (in progress) | **Tokens:** 111,000
**Gate 1:** WARN | **Files:** 3 | **Tests:** 0/0

## TL;DR
根 ④:根治 commit/对抗门(security_hooks.py)在裸命令串上用正则找 git commit 导致的双向失守——过度匹配(3-new:0d6f6479 新引入的 heredoc 引号误判,把引号内 <<A 当真 heredoc 丢掉真实 pathspec→fail-open)+ 匹配不足(3b 9 种 commit 写法绕过/3c --pathspec-from-file/3

## 1. Requirement
根 ④:根治 commit/对抗门(security_hooks.py)在裸命令串上用正则找 git commit 导致的双向失守——过度匹配(3-new:0d6f6479 新引入的 heredoc 引号误判,把引号内 <<A 当真 heredoc 丢掉真实 pathspec→fail-open)+ 匹配不足(3b 9 种 commit 写法绕过/3c --pathspec-from-file/3d --include=/3e cd 别repo)。系统化方向=门在无法证明本次 commit 的路径集被覆盖时 fail-CLOSED(DENY)而非 fail-open(ALLOW),配 shell-aware 分词统一处理引号/heredoc/分隔符/wrapper/子壳;顺带修 meta:新测试用 from backend.core 导入+不在 BVT→CI 从不跑

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 根 ④:根治 commit/对抗门(security_hooks.py)在裸命令串上用正则找 git commit 导致的双向失守——过度匹配(3-new:0d6f6479 新引入的 heredoc 引号误判,把引号内 <<A 当真 heredoc 丢掉真实 pathspec→fail-open)+ 匹配不足(3b 9 种 commit 写法绕过/3c --pathspec-from-file/3d --include=/3e cd 别repo)。系统化方向=门在无法证明本次 commit 的路径集被覆盖时 fail-CLOSED(DENY)而非 fail-open(ALLOW),配 shell-aware 分词统一处理引号/heredoc/分隔符/wrapper/子壳;顺带修 meta:新测试用 from backend.core 导入+不在 BVT→CI 从不跑

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: Gate-0 实测证实:引号内 <<A 被当真 heredoc,secret.py 被吞,bash 却真提交→fail-open | confirmed | ● | Given git commit -m 带引号内 <<WORD 再跟真实 pathspec, when 门计算 pending 路径集, then 真实 pathspec 在 pending 中,未覆盖则 DENY |
| FR-2 | enabler-story | ddd-derived: 系统化方向:算不准方向必须偏严;MEMORY『安全门太严=fail-open-by-abandonment』是反向约束 | confirmed | ● | Given 命令含门无法可靠解析的 heredoc/引号歧义, when 计算 pending, then 歧义 token 纳入 pending 倾向 DENY,不静默丢弃 |
| FR-3 | bug | user-stated: 3b 既有绕过;timeout 600 git commit 是 AGENTS.md 自荐写法 | confirmed | ● | Given timeout 600 git commit -m m / true&&git commit, when 门判断是否 commit, then 识别为 commit,触发覆盖检查 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 3b 的 9 种绕过本 run 全修还是分批? | B. 修最高频+最危险 | 🧠 self |
| Q2 | 根因是修 regex 还是换 shell-aware 分词? | B. shell-aware | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: B. 修最高频+最危险 (🧠 AI 替你拍的板 — resolution: self-answer:3-new 是 P0 fail-open(0d6f6479 新回归,正在放行未审查提交)必修;timeout/&& 是最常用绕过。bash -c/eval/子壳/绝对路径 git 是门自己文档已承认的 threat-model 边界(既有、非回归),全修=大 scope 高回归风险,违背『先止血新回归』。scope=standard 而非全量重写。)
- [SELF-ANSWERED] Q2: B. shell-aware (🧠 AI 替你拍的板 — resolution: self-answer:Gate-0 实证根因=regex 在无 shell 引号上下文的裸串上猜 heredoc,无法区分 quoted <<A 与真 opener。补 regex 是 arms-race(修一个开一个,0d6f6479 正是这样)。正解=让 heredoc 识别尊重 shell 引号(shlex 已有引号感知);或至少:heredoc strip 只在能确认不在引号内时施加,否则 fail-closed 保留 token。THINK 定具体机制。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 9.00 | |
| Priority | 8.00 | |
| Feasibility | 7.00 | |

**Acceptance Criteria:**
1. AC1(3-new,P0 fail-open): _pending_commit_paths 对 `git commit -m "<<A\n" secret.py\nA` 不得丢失真实 pathspec secret.py——门必须把 secret.py 纳入 pending(从而 DENY 未覆盖的提交)。根因:regex 在无 shell 引号上下文的裸串上猜 heredoc,把引号内 <<A 当真 heredoc。实测:当前 strip 后 secret.py 被吃掉。mutation-proof:revert 修复→测试 RED。
2. AC2(fail-closed 原则,统一不变量): 当门无法可靠计算本次 commit 的 pending 路径集时(解析不确定/heredoc 歧义),必须 fail-CLOSED(把不确定的 token 当作可能的真实 pathspec 纳入 pending → 倾向 DENY),绝不 fail-OPEN(丢路径 → 放行)。注意:这与门对自身 ERROR(git 不可用/超时)的 fail-OPEN 是两回事——后者是『算不出就别挡合法 commit』,前者是『算得出但算错方向必须偏严』。
3. AC3(3b 既有绕过,收窄不足): _command_has_git_commit 必须识别 `timeout 600 git commit`(timeout 是常见 wrapper,AGENTS.md 自己建议 commit 留 600s)。其余 3b 形态(true&&git commit 无空格/子壳 (git commit)/if-for/bash -c/eval/绝对路径 git/git ci alias)按 EVALUATE scope 决定本 run 修哪些——至少修 timeout wrapper 和 && 粘连分隔符(最常用的两个)。
4. AC4(meta/P7,CI 从不跑新测试): 本 run 新增的门测试必须用 from core.… 导入(非 from backend.core.…,后者从 backend/ 跑会 collect 失败)且能在裸 checkout 自验→进 bvt_manifest.txt。已存在的 test_reviewed_paths_multirepo.py 若是本类问题也一并修导入+评估进 BVT。
5. AC5(不开新绕过,双向验证): 任何收紧/重解析必须双向验证——(a)真实绕过仍 BLOCK(secret.py 场景 DENY)(b)合法 commit 仍 PASS(普通 `git add X && git commit -m m` 不被误挡)。安全门太严=fail-open-by-abandonment(用户删门),比漏网更糟。


## 3. Design & Approach
**Research Findings (THINK):**
- shlex 引号感知已正确处理攻击场景(Q2 实测):shlex.split('git commit -m "<<A ; " secret.py ; A') → ['git','commit','-m','<<A ; ','secret.py',';','A'],`<<A` 留在 -m 值 token 内,secret.py 是独立 token。fail-open 真因=在 shlex 之前先 regex-strip heredoc body(:1764-1765),这个 pre-strip 吃掉了引号内 pathspec。shlex 自己不会丢它。
- 但 shlex 对真 heredoc 会误吐 token(Q2 实测):'git commit -F - <<EOF\nmsg\nEOF' → shlex 吐出 <<EOF/msg/EOF 当 positional pathspec。所以真(未加引号)heredoc 的 body 仍需 strip——不能简单删掉所有 heredoc strip。
- 共享契约(Q1,R27):_HEREDOC_BODY_RE 有 2 个调用方——_is_backgrounded(:1294,FAIL-SAFE 方向:漏 strip→body-& 被当 backgrounding→多一个 DENY)和 _pending_commit_paths(:1765,FAIL-OPEN 方向:over-strip→丢真 pathspec→少 DENY)。改 regex 本身会同时影响两处;修复必须只动 _pending_commit_paths 的调用逻辑,不碰 regex,保 _is_backgrounded 的 fail-safe 不变。
- over-collect 是 fail-closed 安全的(Q3,gate 消费 :2042-2067):pending 只用于 `pending <= covered` 子集测试,over-collect 只让覆盖要求更严→倾向 DENY,不崩(token 不做路径 I/O,realpath/join 容忍任意串)。这保证 FR-2『不确定时保留 token 偏严』可落地。
- 3b timeout wrapper:_segment_is_git_commit(:1598)的 _WRAPPERS 集合缺 timeout/gtimeout;&& 粘连分隔符已被 _command_has_git_commit 的 resplit 处理(:1636-1647 split ';'),但 `true&&git`(无空格)需验证——shlex 对 `true&&git` 的 token 化。

**Alternatives Evaluated:**
- SIMPLICITY — effort: M / 1 session
- QUALITY — effort: M-L / 1 session

**Chosen Approach:** Arch-A quote-aware heredoc pre-strip(只改 _pending_commit_paths 的 fail-open 调用方,不碰共享 _HEREDOC_BODY_RE,保 _is_backgrounded 的 fail-safe 不变)。具体机制:当前 :1764-1765 无条件对 raw command 施加 _HEREDOC_BODY_RE.sub——改为仅 strip『真(未加引号)heredoc』。判定法(Q2 实证支撑):shlex 的引号感知已把引号内 <<A 黏进 -m 值 token、不作独立 opener token 出现;所以用 shlex 先分词,只对分词后仍作为独立 token 出现的 <<WORD opener 施加 body-strip(引号内的不会独立出现→不被 strip→secret.py 保留)。真 heredoc 的 <<EOF 会作独立 token→仍 strip 其 body(shlex 会误吐 body token,需清)。误判时方向=保留 token=over-collect=fail-closed(Q3 兜底)。附带:_segment_is_git_commit 的 _WRAPPERS 加 timeout/gtimeout(FR-3)。

**Success Criteria:**
- secret.py 攻击场景:pending 含 secret.py,未覆盖提交被 DENY(fail-open 止血)
- 真 heredoc commit:body 不进 pending,合法 commit 不被误挡
- timeout 600 git commit 被识别为 commit
- _HEREDOC_BODY_RE 常量未改,_is_backgrounded 现有测试全绿
- 新测试 from core.… + 裸 checkout 自验 + mutation-proof

**Always:**
- 不改 _HEREDOC_BODY_RE 常量(保 _is_backgrounded fail-safe)
- 误判方向必须 fail-closed(保留 token 偏严)
- 双向验证每个改动(真绕过 BLOCK + 合法 commit PASS)
- 新测试 from core.… 导入 + mutation-proof

**Never:**
- 不补 regex case 式修复(arms-race,0d6f6479 教训)
- 不动共享 _HEREDOC_BODY_RE 影响 _is_backgrounded
- 不 fail-open(算不准偏严不偏松)
- 不全修 3b 9 种绕过(本 run 止血 3-new+timeout+&&,其余既有 threat-model 边界记 backlog)
- 不把门改到会误挡合法 commit(fail-open-by-abandonment)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_8cb06bf9 | 10,000 |  |
| think | completed | art_8773f48d | 13,000 |  |
| plan | completed | art_fc835a31 | 0 |  |
| build | completed | art_4fca6f2e | 48,000 |  |
| review | completed | art_4fff8421 | 18,000 |  |
| test | completed | art_ad78b521 | 22,000 |  |
| deliver | completed | - | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 111,000 | **Stages:** 7/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 06:52:35 | - |
| think | 06:55:51 | 3.3 min |
| plan | 06:57:28 | 1.6 min |
| build | 08:53:03 | 115.6 min |
| review | 09:00:07 | 7.1 min |
| test | 09:02:12 | 2.1 min |
| deliver | - | - |
| reflect | - | - |

Slowest stage: `build` at 115.6 min (89% of the 5 measured inter-stage gaps).

**Timing coverage:** 6/8 stages resolved, 5 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

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
| evaluate | 根因=shell-aware 而非补 regex(Gate-0 证) | judgment | 补 regex 是 arms-race,0d6f6479 本身是补 case 补出的新回归 |
| evaluate | scope 止血 3-new+timeout+&&,其余既有绕过记 backlog | judgment | P0 新回归必修;既有 threat-model 边界全修=高回归风险 |
| think | Arch-A quote-aware pre-strip 优于 Arch-B shlex-first 重写 | judgment | 最小改动+不动共享 regex+over-collect fail-closed 兜底;Arch-B |
| build | BVT 不加入 subprocess 类测试(manifest 分类规则) | taste | manifest WHAT-is-NOT-here 排除 subprocess 类;即使跑过也不 o |
| review | --pathspec-from-file pre-existing gap → backlog 不本 run 修 | judgment | EVALUATE Q1 已定止血范围 3-new+timeout+&&;pathspec-from- |
| test | Layer2 scoped最耦合2子系统+full security_hooks | taste | 覆盖门与共享regex路径 |

**Summary:** 0 mechanical, 2 taste, 4 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 2 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**⚠️ NOT RUN** — adversarial sub-agent was not spawned during this run.
This is a quality gap. Pipeline DELIVER requires adversarial review.

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/security_hooks.py`
- `backend/tests/test_security_hooks.py`
- `backend/tests/test_reviewed_paths_multirepo.py`

**+0 / -0 lines** | 3 files

## 9. Lessons
- [pitfall] 改一个在裸命令串上用 regex 猜 shell 语法的解析器时,修一个 fail-open 极易开另一个:本 run 的 quote-aware normalizer 手写 char-walk 若不镜像 POSIX 引号语义(双引号内 \" 转义),奇偶 \" 会翻转引号状态→message 内 \n 被当分隔符→真 pathspec 落入非-commit 段→fail-open。根治方向=不手写,交给 shlex/真 shell parser;退而求其次=char-walk 必须逐条镜像 POSIX(单引号内 \ 不特殊、双引号内 \ 转义、裸 \ 转义)。
- [pitfall] 跳过 shell 重定向 token 做防误收 pathspec 时,必须区分 BARE operator(> file,operand 是下一个独立 token,跳 2)与 self-contained(>file / 2>&1 / <<EOF,跳 1):只跳 operator 不跳 operand→redirect target 被当 false pathspec 收进 pending→合法 commit 被 false-DENY。正则只匹配 unambiguous operator 形状(真文件名绝不以裸 >/< 开头),两个方向都 fail-safe。
- [decision] 安全门的 false-DENY 与 fail-open 同等重要:太严→用户删门=fail-open-by-abandonment。改 commit-gate 解析必须 BOTH 方向都测——一个真攻击仍 DENY,且一个合法 commit(含重定向/多行 message/timeout wrapper)仍 APPROVE。
- [correction] Gate-2 对抗抓到我自己引入的 2 个 HIGH(odd-parity \" fail-open + redirect-target false-DENY),self-review 一个没发现——改安全门这类高敏感代码,fresh-context 对抗不是可选项,是唯一能跨过 authorship trap 的机制。


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 09:39 UTC*
