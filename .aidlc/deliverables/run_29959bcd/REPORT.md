# Autonomous Pipeline Report: drain-rollback permanent-error terminal-drop — cut the 764x re-drive engine

**Run ID:** run_29959bcd | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-16 16:06 UTC | **Duration:** 40.3 min (in progress) | **Tokens:** 28,000
**Gate 1:** N/A | **Files:** 0 | **Tests:** 3/3

## TL;DR
修复 poison_guard_recycle 无上限循环(频繁 session teardown 主因)。研究 run_f77cb510 实证:病态 session 零进展 turn(永不产 ResultMessage)→ _last_turn_clean=False → 复用前无限 poison_guard recycle(kill+respawn),单 session 764 次/26h。方

## 1. Requirement
修复 poison_guard_recycle 无上限循环(频繁 session teardown 主因)。研究 run_f77cb510 实证:病态 session 零进展 turn(永不产 ResultMessage)→ _last_turn_clean=False → 复用前无限 poison_guard recycle(kill+respawn),单 session 764 次/26h。方向(待 Gate-0 证伪):给 poison_guard 加 loop-breaker,连续 N 次零进展 recycle 后彻底 evict 而非无限 recycle。Gate-0 必查:加 breaker 治根还是治标?为何 turn 永不产 ResultMessage?evict-after-N 是新容灾还是修复现有容灾(poison_guard 本身)的无上限缺陷?

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 修复 poison_guard_recycle 无上限循环(频繁 session teardown 主因)。研究 run_f77cb510 实证:病态 session 零进展 turn(永不产 ResultMessage)→ _last_turn_clean=False → 复用前无限 poison_guard recycle(kill+respawn),单 session 764 次/26h。方向(待 Gate-0 证伪):给 poison_guard 加 loop-breaker,连续 N 次零进展 recycle 后彻底 evict 而非无限 recycle。Gate-0 必查:加 breaker 治根还是治标?为何 turn 永不产 ResultMessage?evict-after-N 是新容灾还是修复现有容灾(poison_guard 本身)的无上限缺陷?

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: 修复频繁 session teardown 主因;Gate-0 证伪 poison_guard breaker 为治标,真根因在 drain-rollback 未分类 permanent error | confirmed | ● | Given 一个 claimed pending set 投递后收到 permanent error event(_is_retriable_error=False, 如 400 unsupported countries), when _finalize_pending_delivery 处理 outcome, then 该 set 被 mark_sent(terminally-undeliverable)+ loud log,NOT rolled back → 无 re-drive |
| FR-2 | task | ddd-derived: IMPROVEMENT.md:431 一个 symptom 多根因 + line 215 whitelist boundary — 必须保留 transient 的正确路径 | confirmed | ● | Given 一个 transient error event(_is_retriable_error=True), when _finalize_pending_delivery 处理, then 仍 rollback_claim_batch → 下个 IDLE 重投(不变) |
| FR-3 | user-story | assumption: 用户发了消息因地理封锁没发出,必须知道;degenerate-guard 先例是 loud log 但那是空消息(无用户内容),permanent error 有真实用户消息所以要 surface 给前端 | assumed | ● | Given 一条真实用户消息因 permanent error 无法投递, when terminally-undeliverable 处理, then 错误事件到达前端(用户可见),消息不被静默 mark_sent-and-forgotten |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | poison_guard 要不要加 loop-breaker(原始需求方向)? | B. 修上游 drain-rollback 分类(治根) | 🧠 self |
| Q2 | permanent error 终止投递后,要不要 surface 给用户? | B. surface 可见错误给前端 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [ASSUMPTION] FR-3: permanent-error turn 对用户可见,不静默吞
- [SELF-ANSWERED] Q1: B. 修上游 drain-rollback 分类(治根) (🧠 AI 替你拍的板 — resolution: Gate-0 fresh-context skeptic code-trace 证实:poison_guard_recycle 是 re-drive 引擎的症状(每次重投前 recycle 一次);breaker 只压 recycle,permanent-error 行仍 pending 仍每个 IDLE 边沿重投;真引擎在 _finalize_pending_delivery:3078 对任何 error 一律 rollback、不咨询现成的 _is_retriable_error)
- [SELF-ANSWERED] Q2: B. surface 可见错误给前端 (🧠 AI 替你拍的板 — resolution: degenerate guard 静默是因为那是空/损坏消息(无用户内容可丢);permanent error 承载真实用户消息,静默=消息黑洞。用户必须知道因地理封锁没发出。THINK 阶段定具体 surface 机制)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 8.00 | |
| **ROI** | **9.000** | **GO** |

**Acceptance Criteria:**
1. AC1: _finalize_pending_delivery 的 rollback 分支对一个 permanent(_is_retriable_error=False)的 saw_error 不再 rollback-to-pending,而是像 degenerate-guard 一样 terminally-undeliverable 处理(mark_sent + loud log),终止 re-drive 循环
2. AC2: 一个 transient error(_is_retriable_error=True,如 throttle/5xx/timeout)仍然 rollback-to-pending(保留现有正确的瞬时重试行为,不回归)
3. AC3: 单测驱动真实的 permanent vs transient 分叉 —— mock 一个 400-unsupported-countries saw_error 断言 mark_sent(不 rollback);mock 一个 throttle saw_error 断言 rollback。revert 分类调用 → permanent 测试变 RED(非 vacuous)
4. AC4: poison_guard_recycle 不新增 breaker(方向被 Gate-0 证伪为治标)—— 验证:修 drain 后,permanent-error session 不再被 re-drive,因此 poison_guard 自然不再 fire(症状随根因消失)
5. AC5: terminally-undeliverable 的 permanent error 必须 surface 给用户(可见错误),不能静默 drop —— 用户要知道消息因地理封锁没发出去,不是黑洞


## 3. Design & Approach
**Research Findings (THINK):**
- 根因三层(code-trace 实证):orchestrator:1578 已用 _is_retriable_error 正确区分 — transient→raise→retry_manager,permanent(400 geo)→不 raise→yield code='SDK_ERROR' error event + return(turn 非 clean)。这层行为正确。
- 信息丢失层:drain-finalize:3078 收到的 saw_error 只是泛化的 code='SDK_ERROR'(两处捕获点 3017+3870 都只取 event['code']),无法区分 permanent vs transient → 一律 rollback_claim_batch → 回 pending。
- re-drive 引擎:pending 行下个 IDLE 边沿重投 → 又 permanent → 又 rollback,无限。poison_guard_recycle 每次重投 fire 一次(症状)。
- PROBE3 实测 _is_retriable_error:400-geo=False, throttle/exit-9/overloaded=True — 分类器已正确,复用它即可,无需新分类逻辑(C042:机制本来就有)。
- _finalize_pending_delivery 是唯一 mark/rollback 决策点(两条路径都调它)— R27 消费方收敛到一处 + 两处 error-event 捕获点。
- surface 现成满足:permanent error event(orchestrator:1599)本就 yield 给前端,用户已可见 400 错误 — FR-3/AC5 不需新 surface 机制。
- degenerate-guard 先例(drain_pending:2978):空 payload 已做 terminally-undeliverable(mark_sent+loud log,不 rollback)来避免同类 drain loop — permanent error 要的是同一处理形态。

**Alternatives Evaluated:**
- SIMPLICITY — effort: S / 1 session
- QUALITY — effort: S / 1 session
- DELETION — effort: S

**Chosen Approach:** orchestrator 在已知 permanent(non-retriable)的 error 分支给 error event 加 terminal:true 标志;两处 error-event 捕获点读取 terminal 并透传;_finalize_pending_delivery 收到 terminal=True 时走 terminally-undeliverable(mark_sent + loud log,像 degenerate guard),否则保持现有 delivered_ok/saw_error 决策不变。切断 permanent-error 的无限 re-drive 引擎,不碰 poison_guard。

**Success Criteria:**
- 一个 permanent-error(400 geo)的 pending 行投递失败后不再回 pending,不再被 re-drive,poison_guard_recycle 不再因它 fire
- transient error 的 rollback→重试行为逐测试证明不变
- mutation test:移除 orchestrator terminal=True → permanent 测试 RED

**Always:**
- 复用现成 _is_retriable_error 分类(SSOT 在 orchestrator:1578),不新写分类逻辑
- terminal 标志只在 orchestrator 已判定 non-retriable 的分支设置
- transient 的 rollback-重试路径保持不变

**Never:**
- 不给 poison_guard 加 breaker(Gate-0 证伪=治标+新容灾)
- 不静默吞 permanent error(必须 surface 给用户)
- 不改 error 文本传递链(方案A,blast radius 大)
- 不改 transient 的分类或重试行为


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | root-cause reframe: poison_guard breaker (治标) → drain-rollba | judgment | Gate-0 skeptic SUPPORTED; code-trace confirmed poi |
| think | 方案 B(QUALITY): orchestrator 在已知 permanent 分支给 error event 打  | taste | 分类 SSOT 留在 orchestrator:1578 已有的 _is_retriable_err |
| plan | R27 消费方枚举:2 处 error-event 捕获(3018/3870)+ 唯一决策函数 _finalize_pe | mechanical | grep 实证收敛 |

**Summary:** 1 mechanical, 1 taste, 1 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**5 findings** (verdict: ?)
- [LOW] state-machine reported HIGH 'poison_guard not stopped / comment overclaims'. VER
- [LOW] correctness: test stub yielded error-only, not the real orchestrator error-then-
- [LOW] meta-review: auth/401-403 errors are also classified non-retriable → terminal → 
- [LOW] meta-review + security: retry_manager ALL_RETRIES_EXHAUSTED/SPAWN_FAILED non-ret
- [LOW] integration: terminal is presence-encoded (only written when True) + log does no

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/session_router.py`
- `backend/core/session_utils.py`
- `backend/core/streaming_orchestrator.py`
- `backend/tests/test_pending_terminal_undeliverable.py`

## 9. Lessons
- [decision] 当一个 recovery/retry/rollback 机制对 ALL errors 一视同仁,根因常是它没咨询系统里 EXISTING 的 permanent-vs-transient 分类器 —— 修复是把已有分类信号 THREAD 到决策点(DRY),而不是在决策层 re-derive(会 drift,且下游常只有降级后的信息如 error code 而非 raw text)。
- [pitfall] 一个 symptom(poison_guard 764x recycle)可能是另一个机制(drain-rollback re-drive)的下游后果 —— 修 symptom(加 breaker)是治标,修 engine(permanent error 不再 rollback)是治根。Gate-0 的价值就是拦住'给症状加机制'的 C042 反射,把方向逼回真 engine。
- [pitfall] 给一个决策函数加分支时,R27 消费方枚举必须覆盖 ALL 调用点 + ALL 捕获点,尤其一个信号有两条并行消费路径(serial drain + cold-spawn coalesce)时 —— 漏一个 finalize 调用点透传新标志 = 那条路径静默退回旧行为。本 run 的 Step-4 coalesce 半边(1 捕获 + 3 调用点)正是 teardown 打断后最易漏的部分。
- [pitfall] 一个 adversarial finding 报 HIGH 不等于它 severity 对:state-machine expert 的 HIGH(poison_guard 未修)事实成立但混淆了两个场景——764x unbounded loop(本 fix 切断)vs 单次 next-turn bounded recycle(poison_guard 既有设计,非本 scope)。verify against source 后降为 LOW scope-boundary,并精确化 comment 消除 overclaim 歧义(P1:finding 是 lead 不是定论)。
- [decision] 一个只在 True 时才写入 dict 的 presence-encoded 标志(if terminal: event['terminal']=True),配合所有消费方用 .get() 读 —— 是跨边界(SSE/多消费路径)加字段的安全契约:flag-off 事件 byte-identical 于加字段前(天然 regression lock),且不会 KeyError。


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 16:06 UTC*
