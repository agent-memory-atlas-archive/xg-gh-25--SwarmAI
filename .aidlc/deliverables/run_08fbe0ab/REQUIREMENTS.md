## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> §4.9 deliverable check-in 系统化修订:把派生物 B 的内容契约从'终版 REPORT.md(REFLECT 产出)'解耦为'REQUIREMENTS.md 需求溯源快照(从 EVALUATE 的 requirements 机械渲染,DELIVER 时即齐全)',根除 B 依赖 REFLECT 产物导致的 commit-vs-report 时序错配;删除'仅当 ledger A 有 REPORT.md 才生成 B'的伪门槛;同步修订正典 §4.9/§4.6.1 的内容契约措辞。终版 REPORT 仍只落底账 A。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | task | user-stated: XG:系统化方案非打补丁;删 cycle4 伪门槛 | confirmed | ● | Given 一个 push-ready run 有 evaluate requirements 但 A 无终版 REPORT(真实 DELIVER 时序), when cmd_run_commit 调 _generate_review_deliverable, then B 被生成(created 非空) |
| FR-2 | task | user-stated: XG 选方案A:解耦评审上下文与终版报告 | confirmed | ● | Given run 有 requirements[], when 生成 B, then B 的 REQUIREMENTS.md 含 §4.6 溯源(原始意图+派生表+澄清+遗留),源是 render_audit_trail_md,与 REPORT 无耦合 |
| FR-3 | enabler-story | ddd-derived: 正典 §4.9 双存储:A=全保真审计,B=就地评审上下文 | confirmed | ● | Given 修订后, when 审查 B 内容, then B 不含 lessons/metrics;那些仅在 A 的终版 REPORT |
| FR-4 | task | user-stated: XG:同步修订正典;R7 doc-code 一致 | confirmed | ● | Given 代码改完, when 读正典 §4.9 B 内容定义 + §4.6.1, then 措辞描述'B=从 requirements 渲染的溯源快照',与代码一致,无悬空旧契约 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | B 的产物名用 REQUIREMENTS.md 还是保留 REPORT.md? | A. REQUIREMENTS.md | 🧠 self |
| Q2 | 根因是时序错配(我上一 run 的框定)还是内容契约错配? | A. 内容契约错配 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: A. REQUIREMENTS.md (🧠 AI 替你拍的板 — resolution: self-answer:正典 §4.9 B 内容=§4.6 溯源(非终版 REPORT),REQUIREMENTS.md 名实相符;但 THINK 需评估 pipeline_pr.py 的 PR body 引用路径随之改)
- [SELF-ANSWERED] Q2: A. 内容契约错配 (🧠 AI 替你拍的板 — resolution: code-trace:B 的审计内容可从 requirements 机械渲染(render_audit_trail_md 已存在),DELIVER 时 requirements 已齐全;'等 REPORT' 是 cycle4 自引入的伪门槛,正典从无此约束。改时序(方案B/C/D)是在错误前提上缝补,已被 Gate-1 推翻)