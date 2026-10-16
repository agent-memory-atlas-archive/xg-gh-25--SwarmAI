# Autonomous Pipeline Report: pipeline 自愈改进: preflight 字段聚合 + 对抗专家并行合并

**Run ID:** run_84a7215c | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 17:03 UTC | **Duration:** 44.0 min (in progress) | **Tokens:** 0
**Gate 1:** N/A | **Files:** 3 | **Tests:** True/1

## TL;DR
两个 pipeline 自愈改进:(A) 新建 pipeline_preflight.py — 在 publish/complete 前,对给定 stage 一次性列出全部必填字段及其正确落点(stage顶层/run顶层/data),对照当前 run.json 报全部缺失项,消除 validator 挤牙膏式试错(根因:字段契约散落在 validator+run-commit+schema 三处,

## 1. Requirement
两个 pipeline 自愈改进:(A) 新建 pipeline_preflight.py — 在 publish/complete 前,对给定 stage 一次性列出全部必填字段及其正确落点(stage顶层/run顶层/data),对照当前 run.json 报全部缺失项,消除 validator 挤牙膏式试错(根因:字段契约散落在 validator+run-commit+schema 三处,无单一入口);(B) DELIVER dispatch 前把实际对抗专家集合算成 union(profile-tier 默认, PLAN.required_experts),一批并行派全,消除 D7 gate 事后拦截导致的分批串行。顺带修 deliver.md publish 示例补齐 push_ready/convergence/files_touched 的落点说明。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 两个 pipeline 自愈改进:(A) 新建 pipeline_preflight.py — 在 publish/complete 前,对给定 stage 一次性列出全部必填字段及其正确落点(stage顶层/run顶层/data),对照当前 run.json 报全部缺失项,消除 validator 挤牙膏式试错(根因:字段契约散落在 validator+run-commit+schema 三处,无单一入口);(B) DELIVER dispatch 前把实际对抗专家集合算成 union(profile-tier 默认, PLAN.required_experts),一批并行派全,消除 D7 gate 事后拦截导致的分批串行。顺带修 deliver.md publish 示例补齐 push_ready/convergence/files_touched 的落点说明。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | task | user-stated: XG:系统化消除 validator 挤牙膏式试错 | confirmed | ● | Given 一个 deliver stage 的 run.json, when 跑 preflight --stage deliver, then 列出 push_ready/convergence/meta_review/files_touched/outputs_surfaced/evidence 等全部 BLOCK 字段及落点,标出缺失 |
| FR-2 | task | user-stated: XG:确保对抗专家并行 | confirmed | ● | Given PLAN 声明了 required_experts 超过 bugfix tier 默认集, when DELIVER dispatch 前, then 实际 spawn 集是两者 union,一条消息并行,不再事后被 D7 拦导致分批 |

### 澄清问答 (Clarifications — who decided what)
_(无澄清记录 / no clarifications)_

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
✅ 无未闭合问题 (no leftover — all requirements closed, no AI assumptions)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 7.00 | |
| Priority | 7.00 | |
| Feasibility | 8.00 | |

**Acceptance Criteria:**
1. AC1: 一个新只读脚本(如 pipeline_preflight.py --stage deliver --run-id X)运行后,列出该 stage 当前会 BLOCK 的 ALL 字段,每个标注其落点(artifact-data / stage-record-top / run-top)+ 当前 run.json 里缺失哪些 —— 覆盖至少 push_ready(stage-record-top)、convergence.all_pass(artifact)、meta_review(artifact)、files_touched(run-top)、outputs_surfaced(stage-record-top)、adversarial_review.evidence(artifact)这 6 个我撞墙过的字段。
2. AC2: 该脚本是纯只读 —— 不改 run.json、不改任何 enforcement 逻辑、不新增一个第四真源;它从现有三个站点(validator deliver 硬编码块 + run-commit push_ready/files_touched + completion-gate outputs_surfaced)READ 并聚合,是它们的投影,不是副本。verify:删掉任一 enforcement 站点的某字段检查,脚本的输出相应少一项(派生性,非硬编码镜像)。
3. AC3: deliver.md dispatch 段显式写明:spawn 对抗专家前,实际集 = union(profile-tier 默认, 当时 run.json 的 required_experts),一条消息并行派全;并说明 BUILD 中途追加 required_experts 仍会合法触发 re-dispatch(union 只消除 PLAN-声明的错配)。
4. AC4: AC3 的改动是 doc(deliver.md)+ 可选一个 helper 把 union 算出来给 agent;不改 D7 gate(_d7_missing_required_experts 保持 append-only 语义不变)。verify:D7 的 append-only 行为(artifact_cli.py:3004-3022)字节不变。


## 3. Design & Approach
**Research Findings (THINK):**
- Fix1 根因: deliver 会 BLOCK 的字段分散在三个 enforcement 站点,无单一只读聚合视图。(a) validator deliver 硬编码块 (pipeline_validator.py validate_artifact_data stage==deliver): runtime_patterns/quality.push_ready/convergence.all_pass/meta_review/adversarial_review.profile_tier/completion_audit.all_green/evidence; (b) run-commit (artifact_cli.py:2722/2798/3000): deliver stage-record 顶层 push_ready + run.json 顶层 files_touched + outputs_surfaced(2739 读 deliver 的 outputs_surfaced/local_pr_surfaced); (c) completion gate (--status completed, :2166): 所有 profile stage done + cross_boundary E2E。字段按生命周期正确分层(artifact-time vs run-state vs completion),Gate-0 已证伪'塞进 STAGE_SCHEMAS'方案(category-error)。
- Fix1 形态: 一个只读 pipeline_preflight.py --stage deliver --run-id,聚合这三站点,报出 CURRENT run.json 对该 stage 会被哪些字段 BLOCK + 各字段落点(artifact.data / stage-record顶层 / run.json顶层)+ 当前缺失项。零写、零改 enforcement 逻辑 → 零回归面。
- Fix2 根因: deliver.md:407 'For bugfix profile: Only dispatch Correctness + Security' 完全不读 PLAN 声明的 required_experts; 而 run-commit 的 D7 gate (_d7_missing_required_experts :3575) 按 required_experts 全集 BLOCK。两套逻辑脱节 → dispatch 窄集 → D7 事后拦 → 补派第二批(串行+额外 wall-clock)。
- Fix2 形态: deliver.md dispatch 规则改为 '实际集 = union(profile-tier 默认, 当时的 required_experts)',一批并行派全。required_experts 是 append-only (D7-SAFETY③, artifact_cli.py:3004-3022),所以 union 取'dispatch 时'的当前值; BUILD 晚追加仍合法触发 re-dispatch(union 只消除 PLAN-声明的错配,不是全部)。
- 两个 fix 都是'让已有机制自洽/透明',不是造新机制: Fix1 把隐性契约变可执行只读视图(非改 enforcement), Fix2 让 dispatch 读已存在的 required_experts(非新 gate)。符合 C042(机制本来就有)+ P9(不镀金)。

**Alternatives Evaluated:**
- SIMPLICITY — effort: S
- QUALITY — effort: L

**Chosen Approach:** 两个独立 fix,一个 PLAN。Fix1: 新建只读 backend/scripts/pipeline_preflight.py,子命令 --stage deliver --run-id <r> --project <p>,聚合三个 enforcement 站点(validator deliver 硬编码块的 artifact-time 字段 / run-commit 的 run-state 字段 push_ready+files_touched+outputs_surfaced / completion-gate 的 stage-done+cross_boundary),读 CURRENT run.json,报出该 stage 会被哪些字段 BLOCK + 每个字段的落点(artifact.data vs stage-record顶层 vs run.json顶层)+ 当前是否缺失。只读: 不 import 进任何 enforcement 路径,不改 validate_artifact_data/run-commit/completion-gate。Fix2: 改 deliver.md dispatch 规则,把 'For bugfix profile: Only dispatch Correctness + Security' 改为 '实际 dispatch 集 = union(profile-tier 默认集, 当时 run.json 的 required_experts)',并在 Step2 显式要求一批(单条消息)并行派全。

**Success Criteria:**
- preflight 能一次性报出 deliver 的全部 BLOCK 字段+落点,消除挤牙膏试错
- deliver.md dispatch 读 required_experts,新 run 不再分批补派
- 本 run 自身 Gate-2 一批并行派全(第一个验证)

**Always:**
- preflight 只读
- deliver.md 改 dispatch 文档规则
- Gate-2 一批并行验证

**Never:**
- 不改 validate_artifact_data/run-commit/completion-gate 任何 enforcement 代码(零回归面)
- 不把 required_experts 约束到 tier(会重开 D7 skip channel)
- 不收敛三站点为单一 schema(Gate-0 已证伪为 category-error)


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| (no decisions) | | | |

**Summary:** 0 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**5 findings** (verdict: ?)
- [MED] 
- [HIGH] 
- [LOW] 
- [MED] 
- [MED] 

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/scripts/pipeline_preflight.py`
- `backend/tests/test_pipeline_preflight.py`
- `backend/skills/s_autonomous-pipeline/stages/deliver.md`

## 9. Lessons
- 一个只读聚合报告类工具的价值前提是 COMPLETENESS——漏报一个真实 BLOCK 字段就从'消除挤牙膏'退化成'给假信心'(false-clean),比没有更糟。durable tell: 做'聚合 N 方真相'的只读视图时先问'这 N 方我枚举全了吗',漏一个方向=false-clean。
- drift-tripwire(断言镜像字段名出现在真源)若 scan 范围太宽则 VACUOUS: leaf 'evidence' 在 validator 全文件出现 16× 多为无关 gate,全文件 scan 删掉 deliver-block 检查仍 green。真锁定要 scan 到最小相关区域(if stage==deliver 块内);non-vacuity 必须实证: 重命名真源那处字面量→tripwire 必须 RED。
- 契约字段散在 N 个不均匀可机读的 enforcement 站点时,正确形态不是收敛成单一 schema(category-error 跨生命周期层)也不是抄一份(第4个漂移源),而是'可 import 的 live-read + 不可 import 的 mirror+drift-tripwire 锁定'混合——各字段按其真源可机读性选策略。
- 对抗专家一批并行 = union(profile-tier 默认, PLAN 声明的 required_experts),单条消息多个 Agent call。根因修法是让 dispatch 读 required_experts(已存在声明)而非 D7 事后拦。
- 吃狗粮验证: 工具做好立刻在'本 run 自己的 deliver'上跑它,用它的输出当 payload checklist——工具的第一个用户是造它的 run。


## 10. Known Gaps & Attention Flags
- Validator blocked 3 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 17:03 UTC*
