# Autonomous Pipeline Report: Content-keyed LRU cache for BM25 doc tokenization in recall

**Run ID:** run_e2aaee43 | **Project:** SwarmAI | **Profile:** bugfix
**Date:** 2026-10-14 06:59 UTC | **Duration:** 80.7 min | **Tokens:** 200,000
**Gate 1:** N/A | **Files:** 2 | **Tests:** True/1

## TL;DR
修复 recall 读路径本地延迟回归:index-free body-BM25(f0f62d65)+ archive 全扫(579d4a7b)使 recall_leg 升到 median 700ms/max 2219ms,抬高 session-start 首问延迟。根治方向(待 EVALUATE/THINK 判定,不预设):会话级 recall 缓存 和/或 archive 惰性扫描。约束:召回

## 1. Requirement
修复 recall 读路径本地延迟回归:index-free body-BM25(f0f62d65)+ archive 全扫(579d4a7b)使 recall_leg 升到 median 700ms/max 2219ms,抬高 session-start 首问延迟。根治方向(待 EVALUATE/THINK 判定,不预设):会话级 recall 缓存 和/或 archive 惰性扫描。约束:召回质量不可退化(不回退到索引),不引入截断式 cost cap(STEERING #2)。涉及 context_recall.py/recall_multi.py/session_router.py recall 注入段。

## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> 修复 recall 读路径本地延迟回归:index-free body-BM25(f0f62d65)+ archive 全扫(579d4a7b)使 recall_leg 升到 median 700ms/max 2219ms,抬高 session-start 首问延迟。根治方向(待 EVALUATE/THINK 判定,不预设):会话级 recall 缓存 和/或 archive 惰性扫描。约束:召回质量不可退化(不回退到索引),不引入截断式 cost cap(STEERING #2)。涉及 context_recall.py/recall_multi.py/session_router.py recall 注入段。

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: XG: session start/中间追问/resume 响应变慢,起 bugfix 修 recall 腿回归 | confirmed | ● | Given 同一 session 同一 query 第二次 recall, when 命中缓存, then 该腿耗时下降>=70% 且结果逐字节一致 |
| FR-2 | bug | ddd-derived: PRI01 召回质量不可退化 + R30 不存陈旧值 | confirmed | ● | Given 语料文件 mtime/内容变化, when 下次同 query recall, then 重新计算,不命中旧缓存 |

### 澄清问答 (Clarifications — who decided what)
| Q | 问题 (question) | 回答 (answer) | 答者 (answered_by) |
|---|------------------|---------------|---------------------|
| Q1 | 根因是不是我需求里原写的 index-free BM25 扫 MEMORY + archive 全扫? | B. 否,是 ddd/session/library leg 无缓存 | 🧠 self |
| Q2 | 缓存该放哪层? | X. Other | 🧠 self |

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
- [SELF-ANSWERED] Q1: B. 否,是 ddd/session/library leg 无缓存 (🧠 AI 替你拍的板 — resolution: 实测隔离各腿:context_files(MEMORY)仅60ms,archive 不在 _recall_context_files 路径;真瓶颈 session 603ms/ddd 834-1186ms/library 288ms,且 Gate-0 skeptic 暖机重测确认零 per-query 结果缓存(ddd warm 仍1137ms))
- [SELF-ANSWERED] Q2: X. Other (🧠 AI 替你拍的板 — resolution: 待 THINK/PLAN 定;倾向在最贵且纯函数的 leg(ddd 的语料读+BM25、session FTS5)加,或 recall_all 层按 (query指纹,语料指纹,domains) 缓存——THINK 比较)

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| Feasibility | high | |
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. 重复首问同一 query:第二次 recall 的 ddd/session/library leg 命中缓存,实测耗时较首次下降 >=70%(警惕:只测缓存,不测模型侧)
2. 召回正确性零退化:缓存命中返回的 hits 与无缓存路径逐字节相同(同 query+同语料指纹→同结果)
3. 语料变更即失效:MEMORY/DDD/Knowledge 文件 mtime 或内容变化后,下次 recall 不得返回陈旧缓存结果
4. 不同 query 不串味:缓存 key 含归一化 query,query 变化必不命中他 query 的缓存
5. 无 STEERING#2 式截断 cost cap:缓存是降重算,TTL/容量上限(若有)只为降内存,绝不截断在算的 recall


## 3. Design & Approach
**Research Findings (THINK):**
- ddd leg ~834ms 分解:file read 66ms + tokenize 376ms(query无关,CJK bigram 展开 26 万 token)+ BM25 score 436ms(其内部 _bm25_tokenize 对每个 doc 再 tokenize 一遍,memory_index.py:290)。
- 关键:tokenize 是 query-无关、纯 corpus 内容函数,却在每次 query 都重算(standalone 一次 + _bm25_scores 内再一次)。per-query 结果缓存只救重复 query;缓存 tokenized corpus(按内容指纹)救每个 query 且内容变即自然失效。
- session leg 603ms = FTS5 recall.recall_about(max_sessions=2);library 288ms = knowledge_fts;两者是 sqlite FTS5,非 Python 重算,缓存收益低且 FTS5 自带索引——优先级低于 ddd tokenize。
- 现有唯一缓存 memory_index.py:376 _session_recall_cache 是 db_path 键的 SessionRecall 对象复用,非结果/中间缓存。

**Alternatives Evaluated:**
- SIMPLICITY — effort: S / 1 run
- QUALITY — effort: M / 1 run
- DELETION — effort: S / 1 run

**Chosen Approach:** 在 memory_index.py 增加按-文本内容的有界 LRU 缓存 _DOC_TOKEN_CACHE + helper _bm25_tokenize_doc(text),把 _bm25_scores:290 的 per-doc tokenize 改走缓存。_bm25_tokenize 本体(query 路径 line 286 + 全部 cjk 测试契约)完全不动。缓存 key=文本内容(len+hash 组合规避碰撞),value=token list;内容变→key 变→自动 miss 重算(满足 FR-2,无需手写 mtime 失效)。OrderedDict 有界(容量上限仅为控内存,move_to_end LRU 淘汰,绝不截断在算的 recall——STEERING#2)。

**Success Criteria:**
- ddd leg 重复 corpus 第二次 tokenize 开销 ->~0,leg 总耗时下降显著(实测 >=70% on tokenize 部分)
- 全部既有 recall + cjk 测试 green(零召回退化)
- 新测试覆盖:对拍一致/内容失效/有界/query未缓存/加速 全 green

**Always:**
- _bm25_tokenize 本体零改动(保 cjk 测试契约)
- 缓存命中返回逐字节一致的 token list
- key 含内容→内容变必失效
- BUILD 用 cached==uncached golden 对拍断言非 vacuous

**Never:**
- 不引入截断式 cost cap(STEERING#2):容量上限仅淘汰缓存项降内存,绝不截断在算的 recall
- 不缓存 query tokenize(line 286,varies 且廉价,缓存反伤)
- 不回退到预建索引换速度(PRI01 召回质量不可退化)
- 不用 mtime 做失效判据(内容 hash 更强,覆盖 mtime 不变但内容变的边角)


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_90a5a85a | 9,000 |  |
| think | completed | art_c56dbd32 | 11,000 |  |
| plan | completed | art_89fba707 | 12,000 |  |
| build | completed | art_dda7357d | 28,000 |  |
| review | completed | art_b2282065 | 22,000 |  |
| test | completed | art_c4fa30b1 | 18,000 |  |
| deliver | completed | art_4f78e93a | 0 |  |
| reflect | completed | - | 100,000 |  |

**Total tokens:** 200,000 | **Stages:** 8/8 completed

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 05:43:31 | - |
| think | 05:46:14 | 2.7 min |
| plan | 05:48:11 | 1.9 min |
| build | 05:58:59 | 10.8 min |
| review | 06:02:30 | 3.5 min |
| test | 06:05:22 | 2.9 min |
| deliver | 06:55:51 | 50.5 min |
| reflect | - | - |

Slowest stage: `deliver` at 50.5 min (70% of the 6 measured inter-stage gaps).

**Timing coverage:** 7/8 stages resolved, 6 with an elapsed number. The earliest resolved stage has no predecessor, so it never carries a number — `resolved` is therefore always one higher than the count of durations (true on 462/462 real runs; stating it here so the gap does not read as a bug). Elapsed is the gap between consecutive artifact publishes, so it includes the inter-stage gap (agent reasoning, gates, sub-agent spawns), not just in-stage work. The run's `created_at` -> first publish is NOT counted. A stage with no published artifact cannot be timed and shows `-`.

## 5. TDD Results
| Metric | Value |
|--------|-------|
| Tests total | 1 |
| Tests passed | True |
| Tests failed | 0 |
| New tests added | 0 |
| Duration | 0s |
| Regressions | 0 |

## 6. Decision Log
| Stage | Decision | Classification | Reasoning |
|-------|----------|---------------|-----------|
| evaluate | 根因从需求原写的 MEMORY+archive 全扫,纠正为 ddd/session/library leg 无 per | judgment | 隔离实测+Gate-0 skeptic 暖机重测证伪原假设 |
| think | 选 tokenize 内容指纹记忆化(A+B)而非 recall_all 结果缓存(C) | judgment | 实测 tokenize 376ms 是 query无关最大单块,缓存它救每个 query;结果缓存只 |
| plan | 缓存放 doc-tokenize 层(新 _bm25_tokenize_doc),不动本体/query/结果层 | taste | 最小正确面:本体零改保 cjk 测试契约,内容 key 自动失效,所有 BM25 消费方间接受益 |
| build | cap 512→16384 | judgment | SMOKE 实测单次 recall 工作集 2751 fragment,512 cap 抖动零命中; |
| review | REVIEW 内补 AC1 成本回归测试(spec WARNING) | mechanical | REVIEW 阶段无 follow-up:deferred finding = shipped bu |

**Summary:** 1 mechanical, 1 taste, 3 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 1 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**1 findings** (verdict: ?)
- [HIGH] memory_index.py _bm25_tokenize_doc: lock-free global OrderedDict + _doc_cache_sa

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `backend/core/memory_index.py`
- `backend/tests/test_recall_tokenize_cache.py`

**+0 / -0 lines** | 2 files

## 9. Lessons
- [correction] I claimed a concurrency test was 'mutation-sound: remove the lock -> flakes', but the no-op-lock mutation ran clean 3x. Under CPython the GIL makes each OrderedDict C-op (get/move_to_end/popitem) individually atomic, so the cross-thread crash window is far narrower than an adversarial reviewer's conf-9 implied. The test is a concurrency SMOKE, not a race-regression guard. Durable tell: before writing 'mutation-sound' on a CONCURRENCY test, actually run the no-lock mutation N times; GIL-atomicity of C-level container ops defeats the obvious race, so the honest claim is usually 'smoke + defensive' not 'proven'.
- [pitfall] An adversarial finding's SEVERITY is a lead to verify, not a verdict to obey (C041 family). The operational reviewer rated the lock-free cache a HIGH conf-9 crash risk; the mechanism (concurrent recall from io-pool + to_thread) was REAL and verified against source (session_router dispatch + recall_metrics._LOCK precedent), so the lock fix was correct AND defensive — but the CRASH severity was overstated because GIL-atomicity narrows the window. Fix the real thing (lock, matches precedent, future-proofs no-GIL), but down-rate the severity honestly in the report rather than inheriting conf-9.
- [decision] For a daemon cache mutated from multiple threads, guard ONLY the O(1) structural ops (get/move_to_end/insert/popitem/flag) with a threading.Lock and keep the expensive pure computation (tokenize) OUTSIDE the lock via release-compute-reacquire-recheck. A rare duplicate compute of the same new input is harmless (pure fn, identical result) and costs far less than serializing every recall leg. Mirror the existing recall_metrics._LOCK precedent rather than inventing a new mechanism (C042).
- [principle] A content-keyed cache (key = len+hash of the input) gives automatic invalidation for free: changed input -> different key -> fresh compute, so a long-running daemon never serves stale results after an on-disk edit, with no mtime/path/TTL invalidation hook to get wrong. Prefer content-keying over path/mtime-keying whenever the keyed value is a pure function of content.
- [pitfall] A fixed cache cap below one operation's working set THRASHES silently (evicts entries before reuse) and delivers ~0 speedup while looking fine — measured here as 8% instead of 65% at a 512 cap vs a ~2.7K fragment working set. SMOKE-measure the real speedup end-to-end, never trust 'tests green' as proof a perf change WORKS; and size the cap above one operation's working set, with a loud WARN (not a silent cost cap) when it saturates.


## 10. Known Gaps & Attention Flags
None identified.


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 06:59 UTC*
