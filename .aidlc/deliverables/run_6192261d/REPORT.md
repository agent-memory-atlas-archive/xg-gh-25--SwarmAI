# Autonomous Pipeline Report: Run A — artifact_cli.py CLI 工具摩擦修复 (G1/G2/G3)

**Run ID:** run_6192261d | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-16 17:38 UTC | **Duration:** 27.0 min (in progress) | **Tokens:** 124,000
**Gate 1:** PASS | **Files:** 2 | **Tests:** 0/0

## TL;DR
Run A (bugfix) — artifact_cli.py 三个 CLI 工具摩擦: G2 抽共享 helper _read_json_arg 让 run-update --stage-json 支持 @file(对齐 publish --data); G3 advance 加 --quiet 精简输出(丢大 next_stage_doc)+ 被拦时返回明确 {advanced:false,

## 1. Requirement
Run A (bugfix) — artifact_cli.py 三个 CLI 工具摩擦: G2 抽共享 helper _read_json_arg 让 run-update --stage-json 支持 @file(对齐 publish --data); G3 advance 加 --quiet 精简输出(丢大 next_stage_doc)+ 被拦时返回明确 {advanced:false,reason}; G1 cmd_schema 输出让 template 更显眼。单文件 backend/scripts/artifact_cli.py。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Run A (bugfix) — artifact_cli.py 三个 CLI 工具摩擦: G2 抽共享 helper _read_json_arg 让 run-update --stage-json 支持 @file(对齐 publish --data); G3 advance 加 --quiet 精简输出(丢大 next_stage_doc)+ 被拦时返回明确 {advanced:false,reason}; G1 cmd_schema 输出让 template 更显眼。单文件 backend/scripts/artifact_cli.py。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: 这些必须修 G2 — run-update --stage-json 不支持 @file 但 publish --data 支持, 不一致, 每次 deliver/reflect 都踩 | confirmed | ● | Given 一个含 CJK 的 stage-json 文件 /tmp/x.json, when run-update --stage-json @/tmp/x.json, then 正确读文件并解析, 与内联 JSON 等价 |
| FR-2 | task | user-stated: XG G2 + R25 删重复/P8 统一入口 | confirmed | ● | Given 两个读 JSON 参数的入口, when 各自解析 --data/--stage-json, then 都调用同一个 _read_json_arg, 无两份拷贝 |
| FR-3 | bug | user-stated: XG G3 — advance 输出(大 next_stage_doc)被显示截断, 迫使 grep pipeline_state 绕过; 诊断订正: 本就纯 JSON, 真因是 payload 大 | confirmed | ● | Given advance --state think --quiet, when 推进成功, then 输出精简 {project,pipeline_state,advanced:true}, 无大字段 |
| FR-4 | task | user-stated: XG G1 — schema 命令承诺'先跑它避免往返'但 depth 只给浅字段名, 消费者漏看 template; 诊断订正: schema 与 validator 同源无分歧, template 本就含完整结构 | confirmed | ● | Given schema --stage test, when 读输出, then template 显眼可见其 layers.ac_driven:{run,pass} 嵌套结构, 现有 ['required'] 消费不破 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | G1/G3 是真工具 bug 还是我上个 session 的未核实诊断? | 诊断订正: G1(schema/validator 无分歧, template 本就全)+ G3(advance 本就纯 JSON)均非工具 bug, 真因是 §二 我没读全 template + payload 大被截断; 处置改为'让 template 更显眼 + --quiet 丢大字段', 不修不存在的分歧 | 🧠 self |
| Q2 | cross_boundary? | false | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: 诊断订正: G1(schema/validator 无分歧, template 本就全)+ G3(advance 本就纯 JSON)均非工具 bug, 真因是 §二 我没读全 template + payload 大被截断; 处置改为'让 template 更显眼 + --quiet 丢大字段', 不修不存在的分歧 (🧠 AI 替你拍的板 — resolution: code-trace 核实: cmd_schema:872-883 reuse get_stage_schema(SSOT), 输出已含 template; cmd_advance:1062 成功路径仅一句 print(json.dumps(payload)) 纯 JSON — 子 agent + 本 session 二次核实一致)
- [SELF-ANSWERED] Q2: false (🧠 AI 替你拍的板 — resolution: 纯 CLI 本地逻辑: _read_json_arg 是 inputs->outputs 纯函数, advance --quiet 是输出格式, cmd_schema 是键序 — 无 event-bus/IPC-wire/schema-migration/multi-subsystem/fe-be-contract/act-sense seam; 全在 artifact_cli.py 单文件, 消费方在同仓同进程)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | 9.00 | |
| **ROI** | **8.000** | **GO** |

**Acceptance Criteria:**
1. AC1: run-update --stage-json '@/path/file.json' 从文件读 JSON 并正确解析(与 publish --data @file 行为一致); 内联 JSON 字符串仍原样工作(向后兼容)。两处 json.loads(args.stage_json)(deliver-ack 预检 + 主解析)都走共享 helper。
2. AC2: _read_json_arg 是单一共享 helper, cmd_publish 的 --data 与 cmd_run_update 的 --stage-json 都调用它(R25 删重复, 不是两份拷贝); @- 读 stdin, @path 读文件, 其余原样返回。
3. AC3: advance --quiet 输出精简 {project, pipeline_state, advanced:true}, 不含大 next_stage_doc; 不带 --quiet 时保持现有完整 payload(向后兼容, 续作合约仍能读 next_action/next_stage_doc)。
4. AC4: advance 在 reg.advance_pipeline 抛 ValueError(非法 state 转移/被拦)时, 返回明确的 {advanced:false, reason:<msg>} 到 stderr+exit1, 调用方据此区分'被拦'与'解析失败', 不再 grep 绕过。
5. AC5: cmd_schema 输出调整让 template 更显眼(例如把 template 放在键序最前, 或加一个 hint 字段指向它), 不改 get_stage_schema 的任何 schema/validator 逻辑; 现有 json.load(stdout)['required'] 等消费方不被破坏(additive)。


## 3. Design & Approach
**Research Findings (THINK):**
- G2 共享 helper 的正确边界: publish 的 @file 块(:540-556)做两件事 — (a) 把 @path/@-/inline 解析成 raw string, (b) 之后 json.loads。helper 只应承担 (a) '解析 raw string 来源', 不碰 json.loads。因为两个调用点的 JSON 解析异常语义不同: run_update :2749 预检包在 try/except(ValueError,TypeError):pass(best-effort 吞掉), :2844 主解析裸 json.loads 无 try(让它自然抛)。若 helper 把 json.loads 也包进去, 会抹掉这个差异。
- G2 error 消息必须参数化: publish 块的 OSError 处理硬编码 'Could not read --data source' + exit(1)。helper 必须接受 argname 参数(--data / --stage-json), 否则 run-update 的文件读取失败会报错说 '--data', 误导用户。
- G3 诊断订正已 Gate-0 确认: cmd_advance:1062 成功路径仅 print(json.dumps(payload)) 本就纯 JSON; 真因是 payload['next_stage_doc'](:1056)内嵌整篇 stage doc 导致大。--quiet 丢大字段即可, 不碰纯度。
- G1 诊断订正已 Gate-0 确认: cmd_schema:881-883 reuse get_stage_schema(SSOT), 输出已含完整 template(validator 同源 STAGE_TEMPLATES:633)。无分歧; 让 template 更显眼即可。

**Alternatives Evaluated:**
- SIMPLICITY — effort: S / 1 session
- FLEXIBILITY — effort: S / 1 session

**Chosen Approach:** A (SIMPLICITY): 新增单一共享 helper _read_json_arg(raw, argname)->str 解析 @path/@-/inline → raw string; publish 的 --data 和 run_update 的两处 --stage-json 都先调它读 raw, 再各自 json.loads(保留原异常语义)。advance 加 --quiet(丢大 next_stage_doc)+ 被拦返回明确 {advanced:false,reason}。cmd_schema 让 template 更显眼。

**Success Criteria:**
- run-update --stage-json @/tmp/x.json(含CJK)成功解析, 等价内联
- grep '_read_json_arg' 显示单一定义 + 3 处调用(publish 1 + run_update 2)
- advance --quiet stdout 不含 'next_stage_doc' 字符串; advance(无quiet)stdout 仍含它
- advance 非法 state 转移 --quiet 返回含 'advanced': false 的结构
- schema --stage test 输出首键是 template(或含 hint); json.load(out)['required'] 仍可取

**Always:**
- helper 只解析 raw-string 来源, json.loads 留调用点(保留 run_update :2749 预检吞错 vs :2844 主解析裸抛的差异)
- publish --data 的现有行为字节级不变(@- stdin / @path / inline + 原 OSError 处理)
- TDD RED→GREEN, 每个 AC 有通过测试

**Never:**
- 不把 json.loads 合并进 helper(会抹掉两处不对称异常语义 = 契约漂移)
- 不改 advance 默认(非 quiet)payload(破坏 orchestrator 续作合约)
- 不删 cmd_schema 任何现有输出键(破坏现有消费方)


## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| think | helper 只解析 raw-string 来源, json.loads 留调用点 — 保留两处 run_update  | taste | R25 删 @file 解析重复, 不合并 json 解析 — 避免抹掉 :2749 预检吞错 vs |
| build | R1.5a fixture 债(add_required_expert Namespace缺属性)致 test_arti | mechanical | git -S 证引入者=efb7e6c6 R1.5a, 我diff grep=0; R29 非我引入 |

**Summary:** 1 mechanical, 1 taste, 0 judgment

## 7. Quality Gates
### 7.5 Adversarial Review
**3 findings** (verdict: ?)
- [MED] deliver-ack 预检经 _read_json_arg 时, 其 OSError→sys.exit(1) 抛 SystemExit, 穿透预检的 exce
- [LOW] @- stdin 在预检 + 主解析被读两次: 预检读到 EOF, 主解析读空 stdin → JSONDecodeError。Fixed: _resolve_
- [LOW] security 0 findings(helper 对 publish 行为字节级一致, 无新攻击面); api-contract 确认 advance er

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/scripts/artifact_cli.py`
- `backend/tests/test_artifact_cli_cli_ergonomics.py`

## 9. Lessons
- 抽取一个'共享 helper'做契约统一(R25 删重复)时, 必须核对该 helper 新引入的异常类是否穿透现有调用点的 except: _read_json_arg 的 sys.exit(SystemExit) 穿透了 deliver-ack 预检的 except(ValueError,TypeError) swallow — 两处原本语义不同的调用点, '保留 json.loads 在调用点'不足以保留全部语义, 新 helper 自己的 SystemExit 是第三种异常类。契约迁移(R27)要枚举 helper 的全部异常出口 vs 每个调用点的 except 覆盖。
- 深埋在多重 sys.exit gate 之后的逻辑, 回归测试要抽成可直接调用的纯 helper 来测, 不要用 subprocess 驱动整条 gate: 第一版 Gate-2 回归锁驱 cmd_run_update 走 completion-gate, 但预检在 REPORT.md/stages-complete 等 gate 的 sys.exit 之后, 测试在触达预检前就被提前 exit → green-because-not-reached(C044 false-green)。mutation 当场证伪(撤修复仍 green)。抽 _resolve_precheck_stage_json 后 mutation 立刻变红 = 真非 vacuous。
- best-effort 预检对一个 @file/@- 来源, 读失败应返回'跳过'哨兵(None)而非 sys.exit; 且 @- 在预检阶段绝不消费 stdin(否则主解析读空), stdin 这种一次性资源的多次读取是跨调用点的隐藏 bug — 把'资源消费'留给单一权威读取点。
- 并行 session 共享一个 git repo 时, 一个 session 的 run-commit files_touched 若误列了另一 session 正在改的共享文件, 会把对方未提交的改动吞进自己的 commit(R29 的反向: 不是我扫走别人, 是别人扫走我)。防御: run-commit 的 files_touched 必须严格是本 run WRITTEN 的文件; 发现自己的改动已在别人 commit 里时, 代码没丢(在 git 历史), 不碰对方 commit, 只 commit 自己的剩余增量。


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-16 17:38 UTC*
