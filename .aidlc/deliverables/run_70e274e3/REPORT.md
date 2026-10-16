# Autonomous Pipeline Report: 修 EXPERT-ID marker 归属脆弱: _read_subagent_prompt_head content-block join ' '→'\n'

**Run ID:** run_70e274e3 | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 18:30 UTC | **Duration:** 26.8 min (in progress) | **Tokens:** 170,000
**Gate 1:** PASS | **Files:** 2 | **Tests:** True/1

## TL;DR
修复 EXPERT-ID marker 归属脆弱: Gate-2 对抗专家 marker 在 D7 commit-gate 处因 expert_id 提取 fallback 成 None/general-purpose 被误判为该专家没 review

## 1. Requirement
修复 EXPERT-ID marker 归属脆弱: Gate-2 对抗专家 marker 在 D7 commit-gate 处因 expert_id 提取 fallback 成 None/general-purpose 被误判为该专家没 review

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 修复 EXPERT-ID marker 归属脆弱: Gate-2 对抗专家 marker 在 D7 commit-gate 处因 expert_id 提取 fallback 成 None/general-purpose 被误判为该专家没 review

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: 让 expert_id 从 SDK 不会前缀污染/漂移的锚点形态可靠提取,使 D7 gate 不再 false-block | confirmed | ● | Given 一个 spawn prompt 首行是 'EXPERT-ID: correctness',SDK 把它和下一行拆成两个 text block, when _read_subagent_prompt_head + _extract_expert_id 运行, then 返回 'correctness',不是 None |
| FR-2 | bug | ddd-derived: runtime_hooks.py 现有设计: 绑定首个 EXPERT-ID 行,拒绝 attacker-influenced 的 injected 行 | confirmed | ● | Given 首行是未填充占位符 'EXPERT-ID: <EXPERT_ID>' 或下方 injected 内容带 'EXPERT-ID: evil', when 提取运行, then 返回 None(不被下方 injected 行覆盖) |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 根因是提取正则过严,还是 _read_subagent_prompt_head 的 ' '.join 把换行吃掉? | 两者是同一机制的两端 — ' '.join(runtime_hooks.py:1182)把 content-block 间换行变空格,正则 \\s*$ 行尾锚点随之失配。修任一端断链;fix 目标留 THINK/PLAN 定。 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: 两者是同一机制的两端 — ' '.join(runtime_hooks.py:1182)把 content-block 间换行变空格,正则 \\s*$ 行尾锚点随之失配。修任一端断链;fix 目标留 THINK/PLAN 定。 (🧠 AI 替你拍的板 — resolution: 实证: 直接跑 _extract_expert_id 对 space-joined 输入返回 None(Case2);跨 113 transcript 实测 11 个首条 user 消息是多-text-block,SDK 确实多块 → ' '.join 空格粘连真实发生。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 9.00 | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. 一个 spawn-prompt head 的 EXPERT-ID 锚点被 SDK 切成多个 content-block(block 边界落在锚点行后)时,expert_id 仍能正确提取(不再因空格粘连返回 None)
2. 单块、CRLF、首行即锚点的既有成功 case 回归不破
3. 一个真正 malformed/缺失的锚点仍返回 None(fail-safe 不被削弱 — 不能为了宽松而把 attacker-influenced 的 injected EXPERT-ID 行提成功)
4. D7 gate 对一个真实完成的对抗专家不再 false-refuse(端到端: marker 写对 expert_id → completed 集含该专家 → declared ⊆ completed)


## 3. Design & Approach
**Research Findings (THINK):**
- 根因是单一机制两端: _read_subagent_prompt_head 的 ' '.join(:1182) 把 SDK 多-block 间换行折成空格, _EXPERT_ID_LINE 的 \s*$ 行尾锚点随之失配 → None。修任一端断链。
- prompt_head 被两个消费者共用: _extract_expert_id(本 bug) 和 _is_adversarial_intent(对抗意图分类)。_is_adversarial_intent 的部分正则含 [^.\n]{0,40}(换行敏感), 所以改 join 会改变第二个消费者看到的 blob — 更大 blast radius。
- 候选宽松正则 ^EXPERT-ID:[ \t]*([a-z][a-z0-9-]*)(?:\s|$) 实测: single-nl/space-joined/bare 都提对, leading-space/injected-midline 仍返回 None(fail-safe 保全)。只改一个消费者。

**Alternatives Evaluated:**
- SIMPLICITY — effort: XS, 1 session
- QUALITY — effort: S, 1 session
- FLEXIBILITY — effort: S

**Chosen Approach:** 修 _read_subagent_prompt_head 的 content-block join: ' '.join → '\n'.join(runtime_hooks.py:1182)。正则 _EXPERT_ID_LINE 不动。THINK 原推荐 A(放宽正则)在 PLAN 的 spike 被自我证伪: 放宽正则会破坏既有 fail-safe 测试(test_expert_id_contract.py:63 'EXPERT-ID:correctness extra words'→必须 None),因为正则无法区分'多-block 空格粘连 seam'和'authored 行尾 junk'(都是 <id> <words>)。改 join 保留真实换行, 让 seam 成为真 \n(多-block→correctness✓), 同时 authored 行尾 junk 仍 junk(line63→None✓), 正则零改动。

**Success Criteria:**
- test_expert_id_contract.py 全绿 + 新多-block case 绿 + mutation-proof(revert join → 新 case RED)
- D7 gate 对真实完成的对抗专家不再 false-refuse(端到端 marker→completed→declared⊆completed)

**Always:**
- 正则 _EXPERT_ID_LINE 零改动(只改 join)
- mutation-proof 新 multi-block 测试(revert join → RED)
- 既有 fail-safe case 全绿

**Never:**
- 不放宽 _EXPERT_ID_LINE 正则(会破坏 line63 fail-safe)
- 不为 _extract_expert_id 单独造第二份 head 读取(过度, 真实 prompt 无 seam 问题)
- 不回退到 SDK agent_type(方案 Z 零耦合)


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| think | 选 A 放宽正则而非改 join | taste | 最小正确 diff, 单消费者, 不触碰 _is_adversarial_intent 的输入 |
| plan | THINK 推荐 A(放宽正则)在 spike 被证伪 → 改为 B(修 join) | judgment | 放宽正则破坏 test line63 fail-safe; 改 join 保 fail-safe 且 |
| review | single-pass review (2 files <50 lines, 不触 auth/data/infra) | mechanical | fan-out 阈值 >3 files OR >100 lines 未达; spec-complia |

**Summary:** 1 mechanical, 1 taste, 1 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**1 findings** (verdict: ?)
- [LOW] backend/core/runtime_hooks.py _extract_expert_id (925-949): security 专家指出 anchor

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/core/runtime_hooks.py`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/tests/test_expert_id_contract.py`

## 9. Lessons
- [pitfall] 一个把 SDK content-block list 用 ' '.join 拼接的 head-reader,会把 block 间换行折成空格 —— 任何依赖'锚点行以行尾结束'(正则 \s*$)的下游提取都会间歇失败,取决于 SDK 是否把该 message 切成多块。修法是 '\n'.join 保留行边界,而非放宽正则(放宽会同时吃掉真正的行尾-junk fail-safe)。
- [decision] 当一个 bug 的因果链是'join 制造粘连 → 正则因粘连失配',修 join 端优于修正则端:join 是单消费者改动,正则放宽会削弱 fail-safe 且无法区分'多块粘连'与'authored 行尾 junk'(两者都是 <id> <words>)。THINK 原推荐被 PLAN-spike 自我证伪 —— spike 一个候选正则对既有 fail-safe 测试的影响,比只在新 case 上验证更能暴露错误方向。
- [principle] 一个被两个消费者共享的解析输入(prompt_head 同时喂 _extract_expert_id 和 _is_adversarial_intent),改它的 join 必须对两个消费者都验证回归 —— 本例 '\n'.join 对分类器的唯一 delta(find...in... 跨 seam)方向是 fail-closed(更保守,永不误放行 commit),因为分类正则的 [^.\n]{0,40} 显式禁止换行,所以插入换行只会让匹配变少。改共享输入前先问'谁还读它'。
- [guideline] 一个 fail-safe 若靠'顺序'成立(绑定首个 EXPERT-ID 行)而非'来源认证',它对 block-0 本身被污染的情形无防御 —— 这是 anchor-trust 模型的 pre-existing 边界,与 join 修法正交(两种 join 下都存在),记为 known-boundary 不夹带。


## 10. Known Gaps & Attention Flags
- Validator blocked 2 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 18:30 UTC*
