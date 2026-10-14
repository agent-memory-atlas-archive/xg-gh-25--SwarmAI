# Autonomous Pipeline Report: Tool-call-leak cleaning: keep persist chokepoint, fix losslessness (2a) + persist/yield fork (2d) + inline-not-to_thread

**Run ID:** run_719886ee | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 06:36 UTC | **Duration:** 65.0 min (in progress) | **Tokens:** 124,000
**Gate 1:** N/A | **Files:** 3 | **Tests:** 0/0

## TL;DR
根 ①:根治用有损文本清洗事后修补模型 tool-call 泄漏这一类——从检测-修补挪到边界阻止(kill+retry prevention + 单一读出口保守无损 strip),删除无条件落库前宽清洗;修 2d(UNCONDITIONAL persist-side clean 腐蚀 data.db + UI/DB 字节分叉)、2a(反引号跨fence配对→代码块丢失+NUL)、2b(宽stri

## 1. Requirement
根 ①:根治用有损文本清洗事后修补模型 tool-call 泄漏这一类——从检测-修补挪到边界阻止(kill+retry prevention + 单一读出口保守无损 strip),删除无条件落库前宽清洗;修 2d(UNCONDITIONAL persist-side clean 腐蚀 data.db + UI/DB 字节分叉)、2a(反引号跨fence配对→代码块丢失+NUL)、2b(宽strip误删正常prose)、统一 detect/clean matcher、#4a(strip 同步占用event loop)

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 根 ①:根治用有损文本清洗事后修补模型 tool-call 泄漏这一类——从检测-修补挪到边界阻止(kill+retry prevention + 单一读出口保守无损 strip),删除无条件落库前宽清洗;修 2d(UNCONDITIONAL persist-side clean 腐蚀 data.db + UI/DB 字节分叉)、2a(反引号跨fence配对→代码块丢失+NUL)、2b(宽strip误删正常prose)、统一 detect/clean matcher、#4a(strip 同步占用event loop)

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | enabler-story | user-stated: 用户:要系统化解决方案不是打地鼠 / 从检测-修补挪到边界阻止 | confirmed | ● | Given 一条含泄漏文本的 assistant 消息被 persist, when 写入 data.db, then DB content == stream yield 的原文字节(无分叉) |
| FR-2 | enabler-story | ddd-derived: Gate-0 skeptic:截断形态落库残留只有宽 strip 能清,kill+retry 够不到;这是宽 strip 的本职用途 | confirmed | ● | Given DB 中有历史截断形态泄漏残留, when 组装 resume-context 或 recall 读回, then 泄漏被无损清除,不喂回模型 |
| FR-3 | bug | user-stated: 早先 5-agent 核验实测复现 2a(\\x00)+2b(prose 误删) | confirmed | ● | Given 含反引号/代码块/讨论性 prose 的文本, when 经过 strip, then 代码块保留、零 \\x00、prose 不被改写 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 是否删除宽清洗(原始 framing)? | B. 保留但挪位置+修无损 | 🧠 self |
| Q2 | persist 存原文后,UI reload 可能显示罕见泄漏文本,可接受吗? | A. 可接受 | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: B. 保留但挪位置+修无损 (🧠 AI 替你拍的板 — resolution: Gate-0 skeptic WRONG-FRAME 证伪了 A:截断形态落库残留(session_utils.py:466-475 注释 + 实测 session a0f04b00)窄 detect RE 看不见、kill+retry 够不到,只有宽 strip 能清。故 re-frame 为 B。)
- [SELF-ANSWERED] Q2: A. 可接受 (🧠 AI 替你拍的板 — resolution: taste 级:存原文消除 2d 的 UI/DB 分叉(数据完整性优先);泄漏文本仅在模型泄漏且无真 tool-use 且窄 detect 未 kill 时出现,极罕见且无害,渲染层清洗是另一个 run 的范围。)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Strategic | 9.00 | |
| Priority | 9.00 | |
| Feasibility | 8.00 | |

**Acceptance Criteria:**
1. AC1(2d消除): persist 写路径不再无条件跑有损宽清洗;DB 存的 assistant text 与 stream yield 的字节一致 —— 构造一条含泄漏文本的消息,断言 persist 的 content == event 原文(同字节),reload 与实时显示一致。
2. AC2(2a修复): strip_tool_call_leak 对『单反引号 + 代码块 + 泄漏』输入必须保留代码块且输出零 \x00 —— 喂 Don`t ... ```python\nx=1\n``` ... <invoke name=Bash> ... that`s it,断言代码块原样保留、输出不含 \x00。
3. AC3(2b修复): strip 不得改写『仅讨论该语法的正常 prose』—— 喂一句纯文本讨论 <invoke name=...>/<parameter name=...> 的 prose(无真泄漏上下文),断言输出 == 输入(不出现 [tool-call omitted])。
4. AC4(统一matcher+读出口): 所有喂回模型的读出口(context_injector.build_resume_context + session_recall 读回)都经过同一个修好的无损 strip;re-induction loop 的两个通道都被切断 —— grep 确认两处都调用 strip,且各有一个 RED-on-revert 测试。
5. AC5(#4a): strip 不再同步占用 asyncio event loop(to_thread 或 size-cap);注意 review 的『312KB→6.9s 平方』已实测证伪(~15ms 线性),只去掉同步占用,不去优化不存在的平方。
6. AC6(meta/P7): 本 run 新增测试用 from core.… 导入、能在裸 checkout 自验的进 bvt_manifest.txt;NUL/无损加固必须有一个 mutation-proof 用例(revert 加固代码→测试 RED)。


## 3. Design & Approach
**Research Findings (THINK):**
- matcher 窄/宽分叉是刻意且正确的(session_utils.py:461-481):窄 _TOOL_CALL_LEAK_RE 用于 KILL 决策(要求 <invoke> 后紧跟 <parameter/</invoke>,窄=不误杀讨论该语法的正常轮次);宽 _TOOL_CALL_LEAK_STRIP_RE 用于清洗(后继可选,宽=抓 mid-stream SIGKILL 落库的截断残留)。清洗比 kill 破坏性小→对模糊输入『不 kill 但清洗』是正确非对称。⇒ EVALUATE AC4『统一 matcher』撤销:保留分叉。
- 2b 不是正则 bug,是宽 anchor 的固有歧义:截断泄漏 `court\n<invoke name="Bash">` 与未加 fence 的 prose 讨论 `<invoke name="Bash">` 词法完全相同,regex 无法区分。宽 strip 必然误削这类 prose。⇒ 不能靠『改好正则』消除 2b,只能控制 blast radius(把有损变换放在可恢复的消费边界,不放永久存储)。
- 2a 是真 bug:_mask_doc_contexts(session_utils.py:510/517-518)先 mask fence(```)再 mask inline-code(`...`),单反引号跨 \x00 sentinel 配对→代码块恢复失败+残留 \x00。实测复现(早先 agent):输出含 \x000\x00、代码块消失。
- 2d 真 bug:_persist_assistant_blocks(session_router.py:1846)persist 写 cleaned,但 streaming handler yield event['content'] 原文→同一消息 UI 显原文、reload 显清洗版,字节分叉。
- 调用点穷举(agent 核验,R27):WRITE=1(session_router.py:1846 无条件);READ/喂模型=2(context_injector.py:146 _format_message + :215 _extract_text,resume-context,已设防);STREAM/KILL=1 处 2 调用(streaming_orchestrator.py:1088 detect-gated kill + :1117 MIXED 分支 per-block strip);UNGUARDED GAP=1(session_recall.py:440 recall_about 读 DB 原文无 strip)。
- 截断形态 detect 返回 False(窄 RE 要求后继 token)⇒ kill+retry 结构上够不到截断残留。⇒ EVALUATE FR-1『新写入靠 kill+retry 阻止』对截断形态不成立:截断残留必须靠清洗(在读出口),不是 kill。

**Alternatives Evaluated:**
- QUALITY — effort: M / 1 session
- SIMPLICITY — effort: M / 1 session

**Chosen Approach:** Arch-3 保留 persist-side 单一 chokepoint + 修无损(XG-chosen A,Gate-1 BLOCK 后修正):Gate-1 证明删 persist-strip 会漏 memory_extractor.py + summarization.py 两条 re-induction 通道(都读持久化 content 喂 Bedrock,都不 strip),故 persist-side strip 是唯一覆盖全部 4+ 下游 reader 的单写入 chokepoint——保留它(撤销原 PLAN 的删除),只修:(1) 2a 无损——_mask_doc_contexts fence/inline 改单遍 alternation(fence 优先),消除单反引号跨 NUL sentinel 配对;(2) 2d 无分叉——strip 一次并把 cleaned blocks 写回 event['content'] IN PLACE,再 persist+yield 用同一份→UI==DB;(3) #4a——strip 挪 to_thread(或确认已不在热路径同步大输入)。保留窄/宽 matcher 分叉。2b(宽 anchor 对裸 prose 讨论的固有误削)记为 known-limitation(词法不可区分,修好 2a 后至少代码块无损,只影响模型吐裸<invoke> opener 的极罕见轮次)。

**Success Criteria:**
- strip 对代码块/反引号输入无损(零 NUL、代码块保留)mutation-proof
- persist 写入 DB 的 content 与 yield 给 UI 的 event content 逐字节一致
- persist-side 单 chokepoint 保留,下游 4+ reader 免费获得清洗(不各自改)
- 新测试在 CI/BVT 真能跑(from core.… + bvt_manifest)

**Always:**
- 保留 persist-side strip 单一 chokepoint(Gate-1 证实下游依赖)
- 保留窄/宽 matcher 分叉
- strip 修复 mutation-proof(revert→RED)
- 新测试 from core.… 导入
- persist 与 yield 必须同一份 cleaned 字节

**Never:**
- 不删 persist 清洗(Gate-1 BLOCK + XG-chosen A:删了漏 memory_extractor+summarization)
- 不统一窄/宽 matcher
- 不手术改 data.db 已存用户内容(STEERING #20)
- 不优化不存在的平方复杂度
- 不改 streaming kill 边界


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_1ddd5711 | 9,000 |  |
| think | completed | art_023c8c24 | 14,000 |  |
| plan | completed | art_1c6f685a | 16,000 |  |
| build | completed | art_127dad57 | 45,000 |  |
| review | completed | art_8ae3955f | 15,000 |  |
| test | completed | art_1ce38cca | 25,000 |  |
| deliver | recorded | art_a0e88b49 | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 124,000 | **Stages:** 6/8 completed | **Validation blocks:** 1

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 05:39:03 | - |
| think | 05:45:38 | 6.6 min |
| plan | 05:57:01 | 11.4 min |
| build | 06:15:47 | 18.8 min |
| review | 06:18:52 | 3.1 min |
| test | 06:23:58 | 5.1 min |
| deliver | 06:36:34 | 12.6 min |
| reflect | - | - |

Slowest stage: `build` at 18.8 min (33% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

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
| evaluate | 原始framing删宽清洗被Gate-0证伪,re-frame为挪位置+修无损 | judgment | skeptic WRONG-FRAME + 我读源码确认截断形态残留只有宽strip能清 |
| think | 撤销EVALUATE AC4统一matcher:窄/宽分叉刻意正确 | judgment | 窄detect防误杀、宽strip抓截断,统一会误杀或漏清 |
| think | 推荐Arch-2读出口清洗而非persist-chokepoint | judgment | 固有有损变换(2b歧义)应挂可恢复的消费边界,非永久存储chokepoint;解C044张力 |
| plan | Gate-1 round1 BLOCK→XG chose A(Arch-3保留chokepoint);round2 PA | judgment | Gate-1证实删persist-strip漏memory_extractor+summarizat |
| plan | 2d必须改_persist_assistant_blocks返回cleaned blocks(当前返bool),call | mechanical | Gate-1 CLAIM B required amendment:in-place写回需retur |
| review | HF3: -> bool 注解未随 body 改,自动修为 list[dict] | mechanical | R7 注解=行为声明 |
| test | Layer 2 scoped to change-relevant importers not all 40 sessi | taste | full set hits known xdist/aiosqlite hang (STEERING |

**Summary:** 2 mechanical, 1 taste, 4 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 1 findings (?) |
| TEST (suite) | 0/0 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**6 findings** (verdict: ?)
- [HIGH] test_assistant_client_id_correlation.py: 7 `assert ok is True` on _persist_assis
- [MEDIUM] session_router.py _persist_assistant_blocks: #4a used asyncio.to_thread for a ~1
- [LOW] Layer-4 E2E test_persist_bytes_equal_yield_bytes_e2e: `returned == captured` was
- [LOW] session_utils.py: _TOOL_CALL_FENCE_RE + _TOOL_CALL_INLINE_CODE_RE dead after sin
- [LOW] 2a inline branch narrowed `[^`]*`→`[^`\n]*`: a multi-line single-backtick span i

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/session_utils.py`
- `backend/core/session_router.py`
- `backend/tests/test_tool_call_leak_guard.py`

**+0 / -0 lines** | 3 files

## 9. Lessons
- [correction] 改函数返回类型(bool→list)时,R27 grep 全部消费方必须含 TEST 文件:我 BUILD 时断言『无 caller 用 bool 返回』只 grep 了生产代码,漏了 test_assistant_client_id_correlation.py 的 7 个 assert ok is True,Gate-2 对抗(+pytest 实测)才抓到。契约变更的消费方枚举=生产+测试,缺一不可。
- [pitfall] 把一个 sync-fast(~15ms 纯 Python regex)操作丢进 asyncio.to_thread 是反模式而非优化:GIL 让 to_thread 对纯 Python CPU 工作零并行收益,而占用 SHARED 默认 executor 正是 COE run_b36c7880 的 16-worker 饱和根因(data_safety.py 明确『run inline, NOT via to_thread』,尤其 send/streaming 热路径)。sync-fast 该 inline;只有真正阻塞的 I/O 才 offload,且要用专用 executor 不是默认池。
- [decision] 一个固有有损的变换(2b:截断泄漏与讨论该语法的 prose 词法不可区分,regex 无法分辨)应挂在可恢复的消费边界——但当消费边界有 4+ 个且无公共 helper 时(C044-fragile),Gate-1 证明保留单一写入 chokepoint + 修无损 才是 root,而非删 chokepoint 分散到每个 reader。write-chokepoint 适用于能做到无损的不变量;读边界清洗只作老数据的 defense-in-depth。
- [pitfall] cross-boundary E2E 测试断言 returned==captured 是同一对象时为 tautology——必须复刻真实调用点的 write-back 模式(event[content]=await ...)并断言 YIELDED event[content]==DB content,才能同时抓住 (a)bool-return 回退 和 (b)删除 write-back 赋值 两种 mutation。只断言方法返回值会漏 (b)。


## 10. Known Gaps & Attention Flags
- Validator blocked 1 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 06:36 UTC*
