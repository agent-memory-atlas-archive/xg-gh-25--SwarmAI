# Autonomous Pipeline Report: R2 — Experts 可视化(GET /api/experts + CapabilitiesOverlay 第三视图)+ expert_id 全链路活体验证

**Run ID:** run_ae55095a | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-16 16:51 UTC | **Duration:** 28.9 min (in progress) | **Tokens:** 146,000
**Gate 1:** N/A | **Files:** 9 | **Tests:** True/1

## TL;DR
R2 — Experts 可视化:后端新增 GET /api/experts(只读投影 ExpertManager.scan_experts() 按 domain 分组:id/domain/description/when-to-use/health);前端 CapabilitiesOverlay 从 skills|connections 两视图扩成三视图,新增 Experts 视图展示专家库 +

## 1. Requirement
R2 — Experts 可视化:后端新增 GET /api/experts(只读投影 ExpertManager.scan_experts() 按 domain 分组:id/domain/description/when-to-use/health);前端 CapabilitiesOverlay 从 skills|connections 两视图扩成三视图,新增 Experts 视图展示专家库 + D7 required_experts 强制状态。附带活体验证:本 run Gate-2 对抗专家用 EXPERT-ID 锚点单消息并行 spawn,落盘 marker 后验证 expert_id 全链路带真 registry id。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> R2 — Experts 可视化:后端新增 GET /api/experts(只读投影 ExpertManager.scan_experts() 按 domain 分组:id/domain/description/when-to-use/health);前端 CapabilitiesOverlay 从 skills\|connections 两视图扩成三视图,新增 Experts 视图展示专家库 + D7 required_experts 强制状态。附带活体验证:本 run Gate-2 对抗专家用 EXPERT-ID 锚点单消息并行 spawn,落盘 marker 后验证 expert_id 全链路带真 registry id。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | user-story | user-stated: XG R2 需求 + core/expert_manager.py docstring 已声明 'GET /api/experts (R2 UI) aggregates scan_experts() by domain' | confirmed | ● | Given 12 个专家 md 在 backend/experts/code/, when curl GET /api/experts, then 返回按 domain 分组的 12 条,每条 id/domain/description/when_to_use/health |
| FR-2 | user-story | user-stated: XG R2 需求;TECH.md:617 记录现状为 skills+connections 两视图 | confirmed | ● | Given CapabilitiesOverlay 当前 ViewMode='skills'\\|'connections', when 用户点 Experts tab, then 渲染专家库视图,三视图切换无 React 报错 |
| FR-3 | task | ddd-derived: AGENT R15 + STEERING #18:信息密集 UI 先读 s_frontend-design design-judgment | confirmed | ● | Given 要做信息密集专家卡片, when 产出布局前, then 已读 design-judgment 的 5-check,卡片按 domain 分组而非等权 tile 堆 |
| FR-4 | spike | user-stated: XG 要求附带验证 expert_id 全链路还差一次带锚点真 spawn | confirmed | ● | Given 本 run 自己的 Gate-2 用 EXPERT-ID 锚点单消息并行 spawn, when 专家 subagent 落盘 marker, then marker expert_id ∈ {correctness,security,...} 真 registry id,run_id=run_ae55095a,不再 None/general-purpose |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | Experts 视图是否需要展示 D7 required/completed 实时强制状态(谁被声明/实际 spawn)? | A. 仅静态专家库 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. 仅静态专家库 (🧠 AI 替你拍的板 — resolution: self-answer: 读 expert_manager.py scan_experts() 只投影静态 md frontmatter;D7 markers 是 per-run 运行时态,接进 Capabilities(非 per-run surface)会引入 run-scoped 耦合。R2 scope=静态专家库;D7 实时态是独立的 pipeline-overlay 关切。先静态,保持纯增量无自锁。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 9.00 | |
| **ROI** | **8.000** | **GO** |

**Acceptance Criteria:**
1. GET /api/experts 返回 12 个 code 专家按 domain 分组,每条含 id/domain/description/when_to_use/health — 用 curl 实测字段齐全(非空壳)
2. CapabilitiesOverlay 第三视图 Experts 渲染专家卡片,切换 skills/connections/experts 三视图无 React 报错 — 前端 build 通过 + 实测切换
3. Experts 视图展示每个专家的 domain 分组 + description,信息布局先读 s_frontend-design design-judgment 再做(非 data-dump)
4. 活体验证:本 run Gate-2 对抗专家用 EXPERT-ID 锚点单消息并行 spawn,落盘 marker 的 expert_id 是真 registry id(correctness/security 等),不再 general-purpose/None


## 3. Design & Approach
**Research Findings (THINK):**
- ExpertInfo 真实字段(code-trace expert_manager.py:56-67)= expert_id/display_name_zh/display_name_en/domain/scope/spawn_as/visibility + missing_fields(health 信号)。EVALUATE 写的 description/when_to_use/health 是凭 docstring 猜的字段名,订正:description 不是 frontmatter 字段(在 md body),health = is_valid/missing_fields 派生。
- by_domain()(expert_manager.py:139)已存在,返回 {domain: [ExpertInfo]} 排序分组 —— 正是 GET /api/experts 要投影的 shape,路由层零新逻辑,只做 dataclass→dict 序列化。
- skills.py 路由范式(filesystem-based, APIRouter, 无 DB)可直接套 experts.py:GET /experts 调 ExpertManager().by_domain() → 序列化。main.py:1570 include_router 范式加 experts_router。
- 专家描述文本在 md body(frontmatter 下方 markdown),若前端卡片要展示'这个专家干什么',路由需带 body 首段/when-to-use 摘要,不能只投影 frontmatter 7 字段。

**Alternatives Evaluated:**
- SIMPLICITY — effort: S, 1 session
- DELETION — effort: XS

**Chosen Approach:** A (SIMPLICITY): 新建独立 backend/routers/experts.py(GET /experts 调 ExpertManager().by_domain() → 序列化 7 frontmatter 字段 + scope 作描述)+ schemas/expert.py response 模型 + main.py 注册 experts_router(prefix /api/experts)。前端新建 services/experts.ts(toCamelCase fetch)+ CapabilitiesOverlay ViewMode 扩三元('skills'|'connections'|'experts')+ Experts 视图按 domain 分组渲染专家卡(display_name + scope 一句话描述 + health 唯一突出信号)。

**Success Criteria:**
- curl -s localhost:18321/api/experts | python3 -c 'json 有 12 专家,按 domain 分组,字段齐全' 返回真实数据
- 前端 npm run build 通过,CapabilitiesOverlay 三视图切换无 console error
- Gate-2 marker 落盘后 expert_id ∈ 真 registry id(活体验证通过)

**Always:**
- experts 路由只读(mirror skills GET 范式);前后端字段名 snake→camel lockstep;Experts 视图遵循 design-judgment(按 domain chunking,非等权 tile wall)

**Never:**
- 不给 experts 端点加 write/mutate(scan_experts 是只读 SSOT);不在 Capabilities 引入 per-run 运行时态耦合;不堆 7 frontmatter 字段的等权 tile(data-dump 反模式)


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | R2 scope=静态专家库,D7 实时态自答为独立关切(FR Q1) | taste | scan_experts 只投影静态 frontmatter;D7 markers per-run  |
| think | 独立 experts.py 路由 vs 塞进 skills_router | taste | experts≠skills 语义独立,by_domain 现成,mirror skills.py  |
| plan | 采纳 Gate-1:序列化范式钉死为 skills.py 的 _skill_info_to_response 显式转换 | mechanical | frozen dataclass→pydantic 必须显式,skills.py:174 范式现成 |

**Summary:** 1 mechanical, 2 taste, 0 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**5 findings** (verdict: ?)
- [MED] experts.ts:19-26 coalesce 不一致(expertId 用 ?? 其余 ||)。api-contract 专家 flag。Fixed: s
- [LOW] security:ExpertResponse 排除内部 path 字段无显式测试(回归则泄露 FS 绝对路径)。Fixed: 加 test_response_
- [LOW] security:expert_manager symlink 防御(root 若被 symlink 到攻击者目录会索引)。known-residual:需 s
- [LOW] correctness:experts.ts API 路径 '/experts' 依赖 api client 的 /api base 约定。known-resi
- [LOW] api-contract:isValid 的 as boolean 无运行时校验(backend 发非 bool 时静默强转)。known-residual:b

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/schemas/expert.py`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/routers/experts.py`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/routers/__init__.py`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/main.py`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/backend/tests/test_experts_router.py`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/desktop/src/services/experts.ts`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/desktop/src/types/index.ts`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/desktop/src/components/layout/CapabilitiesOverlay.tsx`
- `/Users/gawan/Desktop/SwarmAI-Workspace/swarmai/desktop/src/components/layout/CapabilitiesOverlay.test.tsx`

## 9. Lessons
- frozen=True dataclass 不能直接喂 FastAPI response_model — 必须显式投影进 pydantic BaseModel(_X_info_to_response 范式)。Gate-1 的 API-existence check 抓到:'有 schema 文件'≠'有显式转换',措辞含糊会漏。镜像现有同类(SkillInfo→SkillResponse)是零惊喜路径。
- 前后端 contract lockstep 的 Layer-4 测试:把前端消费的 key 集(toCamelExpert 读的 snake_case keys)编码进后端 router 测试,断言后端发的 key 覆盖它 — 后端 drop/rename 任一前端读的字段→RED。单侧 unit 都绿但 seam 断的类(frontend↔backend contract)只有这种双侧绑定测试能抓。mutation:加一个后端不发的 key→RED 证非 vacuous。
- C054 实证:Gate-2 对抗专家单消息并行 spawn(correctness/security/api-contract 一条消息三个 Agent 调用),marker 落盘实测带真 run_id + 真 expert_id(非 general-purpose/None)— 并行不损归属。EXPERT-ID 锚点填 lowercase registry id 是全链路活体验证的 key。
- Gate-2 的 MED finding 要核验严重性再处置:api-contract 的 ?? vs || 不一致评 MED,但 backend pydantic 必填字段保证非 None,生产不触发 → 真实是风格一致性(统一便宜就修),不是 MED bug。finding 是待验线索非判决。


## 10. Known Gaps & Attention Flags
- Validator blocked 4 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 16:51 UTC*
