# Autonomous Pipeline Report: R1.5b-i 坐实 expert_id 值(方案 Z,零 Claude 耦合):① deliver.md spawn 每个专家时在 prompt head 注

**Run ID:** run_e44668a9 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-16 11:41 UTC | **Duration:** 36.3 min (in progress) | **Tokens:** 110,000
**Gate 1:** N/A | **Files:** 5 | **Tests:** 0/0

## TL;DR
R1.5b-i 坐实 expert_id 值(方案 Z,零 Claude 耦合):① deliver.md spawn 每个专家时在 prompt head 注入固定行 EXPERT-ID: <id>;② runtime_hooks 把 marker expert_id 来源从 _expert_id_from_agent_type(agent_type) 改为从 transcript head 用

## 1. Requirement
R1.5b-i 坐实 expert_id 值(方案 Z,零 Claude 耦合):① deliver.md spawn 每个专家时在 prompt head 注入固定行 EXPERT-ID: <id>;② runtime_hooks 把 marker expert_id 来源从 _expert_id_from_agent_type(agent_type) 改为从 transcript head 用锚定正则提取 EXPERT-ID: 标记;③ 注入↔提取契约测试。不碰 .claude/agents、不碰 SDK agents=、不碰 subagent_type、不改任何 gate 判决。验收:真跑一个专家 marker expert_id=correctness 而非 general-purpose。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> R1.5b-i 坐实 expert_id 值(方案 Z,零 Claude 耦合):① deliver.md spawn 每个专家时在 prompt head 注入固定行 EXPERT-ID: <id>;② runtime_hooks 把 marker expert_id 来源从 _expert_id_from_agent_type(agent_type) 改为从 transcript head 用锚定正则提取 EXPERT-ID: 标记;③ 注入↔提取契约测试。不碰 .claude/agents、不碰 SDK agents=、不碰 subagent_type、不改任何 gate 判决。验收:真跑一个专家 marker expert_id=correctness 而非 general-purpose。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | enabler-story | user-stated: design §4 R1.5b-i + 来源契约节(XG 2026-10-16 定方案 Z) | confirmed | ● | Given 一个 correctness 专家被 spawn,其 prompt head 含 EXPERT-ID: correctness, when SubagentStop 写 adversarial marker, then marker.expert_id == 'correctness' |
| FR-2 | enabler-story | user-stated: XG 2026-10-16:别跟 .claude 耦合太紧 | confirmed | ● | Given R1.5b-i 的 diff, when grep .claude/agents / agents= / subagent_type 改动, then 零命中(仅注入+提取两端是我们自己的契约) |
| NFR-1 | task | ddd-derived: design §5 风险表:自然语言承载机器判据的脆弱性(deliver.md:461 血泪表) | confirmed | ● | Given 注入端换一种自然语言措辞, when 提取, then 锚定正则仍只认 EXPERT-ID: 行,不受散文措辞影响 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | expert 身份注册走 .claude/agents(X) / SDK agents=(Y) / 自有 prompt 标记(Z)? | Z. 自有 EXPERT-ID: 标记 | 👤 user |
| Q2 | 提取端是否需要新读 transcript? | B. 复用已有 head 读 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q2: B. 复用已有 head 读 (🧠 AI 替你拍的板 — resolution: self-answer:runtime_hooks.py:1040 已在 off-loop 读 _read_subagent_prompt_head(前2000字符)做 adversarial 分类,同一次读里多提取 EXPERT-ID,零新增读)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 4.00 | |
| Feasibility | 4.50 | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. deliver.md/gate2-adversarial.md spawn prompt head 含固定行 EXPERT-ID: <expert_id>(由 orchestrator 替换 <DOMAIN> 时同步注入)
2. runtime_hooks marker 的 expert_id 来源改为从 transcript head 用锚定正则 ^EXPERT-ID:\s*([a-z][a-z0-9-]*)$ 提取,不再调 _expert_id_from_agent_type(agent_type)
3. 契约测试:注入格式 ↔ 提取正则 lockstep(注入一个 EXPERT-ID: correctness 的 head → 提取出 correctness;mutation:改任一端 → RED)
4. 负路径:prompt head 无 EXPERT-ID: 行 → expert_id=None(back-compat,不崩)
5. 不碰 .claude/agents、不碰 SDK agents=、不碰 subagent_type、security_hooks 的任何 gate 判决零改动
6. Layer-4 E2E:真跑一个 adversarial 专家(或 fixture 模拟真实 transcript),marker expert_id=correctness 而非 general-purpose/None


## 3. Design & Approach
**Research Findings (THINK):**
- registry id 是 lowercase-hyphen(correctness/api-contract/red-team),<DOMAIN> 散文名是 Title-case(Correctness/API Contract)—— EXPERT-ID: 必须注入 registry id 不是散文名,orchestrator 从 dispatch 表的 experts/code/<id>.md 路径取 id
- 12 个 registry id(api-contract code-quality concurrency correctness integration operational performance red-team security spec-compliance state-machine ux-test)全 match [a-z][a-z0-9-]*
- 承重实现约束(P3):prompt_head 当前只在 `if not adversarial` 分支内读(runtime_hooks.py:1040)—— adversarial 第一次就 True 时根本没读 head。R1.5b-i 的 EXPERT-ID 提取必须 UNCONDITIONALLY 读一次 head(把读提到分支外或独立读),否则 adversarial 专家的 expert_id 永远提取不到 → 自锁风险的根

**Alternatives Evaluated:**
- SIMPLICITY — effort: S,1 session
- FLEXIBILITY — effort: M

**Chosen Approach:** 方案 Z 单行锚点(Gate-1 修订版):注入端 gate2-adversarial.md 模板首行加 'EXPERT-ID: <EXPERT_ID>' 契约行,orchestrator 替换 <DOMAIN>(Title名)时同步填 <EXPERT_ID>=lowercase registry id(从 dispatch 表路径 experts/code/<id>.md 取)。提取端 runtime_hooks 把 _read_subagent_prompt_head 读提到 adversarial 分支外(无条件读一次,保持在 _classify_and_write 的 off-loop thread 内),加锚定 multiline 正则 ^EXPERT-ID:\s*([a-z][a-z0-9-]*)\s*$ 提取,替换+删除 _expert_id_from_agent_type。head 无 EXPERT-ID → None(fail-safe,不回退 agent_type)。

**Success Criteria:**
- 真实专家 spawn → marker.expert_id = registry id(非 general-purpose/None)
- 契约+drift测试证两端lockstep(mutation→RED)
- security_hooks diff 空

**Always:**
- 注入↔提取 lockstep(契约+drift测试锁)
- head读提到分支外但保持off-loop thread内
- EXPERT-ID值=lowercase registry id

**Never:**
- 不碰 .claude/agents / agents= / subagent_type
- 不改 security_hooks gate判决
- head无EXPERT-ID不回退agent_type
- 不为fail-safe edge case造占位符替换子系统(P9)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_a8d58e34 | 9,000 |  |
| think | completed | art_02c4485a | 10,000 |  |
| plan | completed | art_f171f378 | 9,000 |  |
| build | completed | art_105c049c | 42,000 |  |
| review | completed | art_63558574 | 15,000 |  |
| test | completed | art_c0b26dee | 25,000 |  |
| deliver | completed | - | 0 | R1.5b-i 坐实 expert_id 值 (方案 Z, 零 Claude 耦合): EXPERT |
| reflect | recorded | - | 0 |  |

**Total tokens:** 110,000 | **Stages:** 7/8 completed | **Validation blocks:** 1

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 11:08:30 | - |
| think | 11:10:04 | 1.6 min |
| plan | 11:15:01 | 4.9 min |
| build | 11:21:00 | 6.0 min |
| review | 11:22:55 | 1.9 min |
| test | 11:27:06 | 4.2 min |
| deliver | - | - |
| reflect | - | - |

Slowest stage: `build` at 6.0 min (32% of the 5 measured inter-stage gaps).

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
| evaluate | work_type=existing-feature (改填值来源,bounded,非 restructure) | mechanical |  |
| evaluate | cross_boundary=true (注入↔提取两端契约) | mechanical |  |
| think | 方案A SIMPLICITY:单行EXPERT-ID锚点+无条件head读+锚定正则 | taste | 宏观Z已由XG定,此为实施层选择 |
| think | head读必须提到adversarial分支外(P3 falsified修正) | mechanical |  |
| plan | Gate-1 Check6 drift gap 采修法a(契约+drift测试)非修法b(spawn_prompt su | taste | 修法b是scope creep(P9);洞fail-safe(手填错→None非dangerous) |
| review | 单遍review(5文件<100行不碰auth/data/infra);spec compliance仍spawn fr | mechanical |  |
| test | 2 L2 失败是 plugin_manager pre-existing baseline 漂移(非我文件),记 Kno | mechanical |  |

**Summary:** 5 mechanical, 2 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 0 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**⚠️ NOT RUN** — adversarial sub-agent was not spawned during this run.
This is a quality gap. Pipeline DELIVER requires adversarial review.

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/runtime_hooks.py`
- `backend/skills/s_autonomous-pipeline/data/gate-prompts/gate2-adversarial.md`
- `backend/skills/s_autonomous-pipeline/stages/deliver.md`
- `backend/tests/test_pipeline_run_mapping.py`
- `backend/tests/test_expert_id_contract.py`

**+0 / -0 lines** | 5 files

## 9. Lessons
- 方案 Z (零 Claude 耦合) 的正确形态是用一个结构化锚点行 (EXPERT-ID: <id>) 承载身份,而非自然语言句子——expert 身份是我们自己的信息,从自己写入的 prompt head 提取,不绕 SDK agent-registry。但锚点提取必须绑定到 FIRST EXPERT-ID 行并只验证它:用 re.search 找 WELL-FORMED 模式会跳过一个 malformed 的 line-1 占位符、继续扫到下方 review 内容里 author-influenced 的 EXPERT-ID 行 → 错误归属。Gate-2 对抗抓到,self-review 没抓到——同一类 authorship trap。
- 改一个函数的填值来源 (SDK agent_type → prompt-head 提取) 是契约变更:R27 要求 grep 所有消费方含测试文件。test_pipeline_run_mapping.py 直接 assert 被删 helper 的行为,PLAN 阶段就识别并一并处理 (删测试 + 迁移到新契约测试文件),避免 BUILD 后才发现红测试。
- 一个 fail-safe 的 edge case (手填 EXPERT_ID 写错大小写 → None 不归属) 不该升级成一个新机制 (把 substitution 移进 spawn_prompt.py)——Gate-1 建议的 fix b 是 scope creep (P9),强化版 fix a (契约+drift 测试锁模板占位行) 是对的最小修。但 Gate-2 之后证明 fix a 还漏了 first-match-wins 的注入面,说明'fail-safe'的判断要覆盖 search 语义本身,不只是单行格式。


## 10. Known Gaps & Attention Flags
- Validator blocked 1 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 11:41 UTC*
