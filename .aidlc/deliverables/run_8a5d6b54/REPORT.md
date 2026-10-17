# Autonomous Pipeline Report: Opus 5.5 加入 model registry(候选,非 flagship)+ thinking-mode guard

**Run ID:** run_8a5d6b54 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-17 06:23 UTC | **Duration:** 19.0 min (in progress) | **Tokens:** 146,000
**Gate 1:** PASS | **Files:** 4 | **Tests:** 0/0

## TL;DR
在 backend/model_registry.py 的 MODEL_REGISTRY 加 claude-opus-5-5:us.anthropic.claude-opus-5-5,插在 claude-opus-4-8 之后(绝不占 index 0,否则 settings.py:409 auto-reset 会把 default 静默换成 5-5);并加 config guard:当 resol

## 1. Requirement
在 backend/model_registry.py 的 MODEL_REGISTRY 加 claude-opus-5-5:us.anthropic.claude-opus-5-5,插在 claude-opus-4-8 之后(绝不占 index 0,否则 settings.py:409 auto-reset 会把 default 静默换成 5-5);并加 config guard:当 resolved model 是 opus-5-5(或任何拒绝 thinking disabled/enabled 的 5.x+ 模型)且 thinking_mode∈{disabled,enabled} 时,映射到 adaptive 或拦住 settings 写入(5.5 对 thinking disabled/enabled 返回 400)。已坐实前提(research run_d0eef2be):Bedrock 授权实证通过(us.anthropic.claude-opus-5-5 ACTIVE,us-east-1+us-west-2);registry 族系推导函数对 5-5 零改动(model_version/is_large_context_model/supports_custom_temperature/context_window_for 全绿);forced-tool-use 生产代码零消费方;前端 OT01 风险不成立(prompt_builder.py:1822 已送 summarized)。default 维持 opus-4-8 不变,只加可选+guard,不提 flagship。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 在 backend/model_registry.py 的 MODEL_REGISTRY 加 claude-opus-5-5:us.anthropic.claude-opus-5-5,插在 claude-opus-4-8 之后(绝不占 index 0,否则 settings.py:409 auto-reset 会把 default 静默换成 5-5);并加 config guard:当 resolved model 是 opus-5-5(或任何拒绝 thinking disabled/enabled 的 5.x+ 模型)且 thinking_mode∈{disabled,enabled} 时,映射到 adaptive 或拦住 settings 写入(5.5 对 thinking disabled/enabled 返回 400)。已坐实前提(research run_d0eef2be):Bedrock 授权实证通过(us.anthropic.claude-opus-5-5 ACTIVE,us-east-1+us-west-2);registry 族系推导函数对 5-5 零改动(model_version/is_large_context_model/supports_custom_temperature/context_window_for 全绿);forced-tool-use 生产代码零消费方;前端 OT01 风险不成立(prompt_builder.py:1822 已送 summarized)。default 维持 opus-4-8 不变,只加可选+guard,不提 flagship。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | enabler-story | user-stated: XG:起 full pipeline 落地 registry | confirmed | ● | Given registry 加 5-5 后, when settings 读 available_models, then 5-5 可选且 FLAGSHIP 仍是 4-8 |
| FR-2 | enabler-story | ddd-derived: 5.5 对 thinking disabled/enabled 返回 400;需防用户手动切后 400 | confirmed | ● | Given model=opus-5-5 且 thinking_mode=disabled, when 构建 thinking_config, then 得到 adaptive 不是 disabled |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | guard 落 prompt_builder(改 thinking_config 签名收 model)还是 settings 写入侧(:320 已有 thinking_mode 校验)? | 自答:倾向 prompt_builder 运行时降级为主(覆盖所有读 config 路径,含既存已存 disabled 的 config),settings 侧可加友好提示;最终形态 PLAN 定 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: 自答:倾向 prompt_builder 运行时降级为主(覆盖所有读 config 路径,含既存已存 disabled 的 config),settings 侧可加友好提示;最终形态 PLAN 定 (🧠 AI 替你拍的板 — resolution: settings 侧拦只防新写入,挡不住 config 里已存的 disabled;prompt_builder 运行时降级覆盖面全(_build_thinking_config:1706 是所有 session 的必经点))

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | high | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. MODEL_REGISTRY 含 claude-opus-5-5:us.anthropic.claude-opus-5-5,位于 claude-opus-4-8 之后、非 index0;FLAGSHIP_MODEL 仍=claude-opus-4-8
2. 加族系函数 supports_disabled_thinking(与 supports_custom_temperature 同形):opus>=5 返回 False;config guard 在该函数判定下,model 拒 disabled 时把 thinking_mode disabled/enabled 映射 adaptive(或 settings 写入侧拦)
3. test_model_registry 加 opus-5-5 的 available-not-flagship + bedrock-id 解析断言;guard 有强制执行的测试(拒 disabled model + disabled mode → 得到 adaptive)
4. registry SSOT 全部派生消费方不含硬编码镜像(grep config.py/app_config_manager/eval_runner/prompt_builder/hive seed/前端 fallback 常量)


## 3. Design & Approach
**Research Findings (THINK):**
- Gate-0 更正后设计:guard 在 build_options 调用点注入(model:2109 与 thinking_config:2159 同 scope,实证),不改 _build_thinking_config 签名——不污染热路径
- registry 派生消费方全部从 MODEL_REGISTRY/default_*() 派生(config.py:102 dict(MODEL_REGISTRY)、app_config_manager:78-79、hive/release.sh:231-232),无硬编码 opus 镜像;前端 FALLBACK_FLAGSHIP_MODEL=opus-4-8 是 flagship fallback,本次不改 flagship 故不动——R27 清
- 新增族系函数 supports_disabled_thinking(与 supports_custom_temperature:278 同形,opus>=5→False),是补齐族系能力表,非造重复机制(C042)

**Alternatives Evaluated:**
- SIMPLICITY — effort: S(1行registry + ~10行函数 + ~5行调用点 + 测试)
- DELETION — effort: XS

**Chosen Approach:** 3 atomic changes: (1) MODEL_REGISTRY 加 claude-opus-5-5 插 opus-4-8 后; (2) 新增族系函数 supports_disabled_thinking(model) 与 supports_custom_temperature 同形,opus>=5 返回 False; (3) prompt_builder.build_options 调用点:resolve 出 model 后,若 not supports_disabled_thinking(model) 且 thinking_config.type 属于 disabled/enabled 则覆写 adaptive + log

**Success Criteria:**
- opus-5-5 可在 Settings 选中且 FLAGSHIP 仍 4-8
- 手动把 model 切 opus-5-5 + thinking disabled 后不会向 Bedrock 发 disabled(400)——运行时降级 adaptive
- registry 全派生消费方零硬编码镜像(已 THINK 实证)

**Always:**
- registry 新 key 插 opus-4-8 之后非 index0(settings.py:409 auto-reset)
- 族系函数是补齐能力表非造重复(与 supports_custom_temperature 同形)
- guard 覆写要 fail-loud 一行 log,不静默

**Never:**
- 把 disabled-thinking 判断塞进 is_large_context_model(职责混淆)
- 只在 settings 侧拦(挡不住既存 config 的 disabled)
- 误伤 opus-4-8/sonnet-4-6 的合法 disabled


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | Gate-0 skeptic WRONG-FRAME 更正:guard 落点不需改 _build_thinking_co | judgment | Gate-0 抓到 framing 错误,正是 EVALUATE gate 的价值;修正后设计更干净 |

**Summary:** 0 mechanical, 0 taste, 1 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**⚠️ NOT RUN** — adversarial sub-agent was not spawned during this run.
This is a quality gap. Pipeline DELIVER requires adversarial review.

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/model_registry.py`
- `backend/core/prompt_builder.py`
- `backend/tests/test_model_registry.py`
- `backend/tests/test_prompt_builder_thinking_guard.py`

## 9. Lessons
- [principle] 给一个被某些模型拒绝的运行时能力(如 opus>=5 拒 thinking disabled)加 guard,落点应是 model 与该能力配置「唯一已同时 resolved」的调用点,而非把 model 塞进本该与 model 解耦的 helper 签名——Gate-0 的 WRONG-FRAME 正是抓这个:先假设「helper 拿不到 model 要改签名」,实证调用点上游 3 行就有 resolved model。改签名污染所有 session 热路径,调用点注入零污染。
- [decision] 新模型能力判定一律用族系比较(version >= threshold)而非 allowlist:allowlist 对下一个 opus 静默答错(把 opus-6 读成「支持 disabled」→ 400 на wire)。本次 supports_disabled_thinking 复刻 supports_custom_temperature 的族系形态,是补齐同一张族系能力表,不是造重复机制。
- [pitfall] registry SSOT 加 key 时,派生消费方(config.ANTHROPIC_TO_BEDROCK_MODEL_MAP=dict(MODEL_REGISTRY)、default_available_models、hive seed)全自动跟随——但 flagship fallback 常量(前端 FALLBACK_FLAGSHIP_MODEL)是派生够不到的硬编码镜像;本次不改 flagship 故不受影响,但改 flagship 时必须同步它(R27)。cross-boundary Layer-4 用「删 registry key→派生映射丢它」的 mutation 证明派生真跟随 SSOT(非 vacuous)。


## 10. Known Gaps & Attention Flags
- Validator blocked 1 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-17 06:23 UTC*
