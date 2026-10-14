# Autonomous Pipeline Report: 根⑤ 远程图 exfil 边界收口: resolveImageSrc drop remote + CSP img-src belt

**Run ID:** run_5e604f45 | **Project:** SwarmAI | **Profile:** full
**Date:** 2026-10-14 14:12 UTC | **Duration:** 46.5 min (in progress) | **Tokens:** 0
**Gate 1:** N/A | **Files:** 3 | **Tests:** True/1

## TL;DR
根⑤ 远程内容 exfil 边界收口(carry-over from abandoned run_98272468, EVALUATE/THINK/PLAN 已 fresh-context 证伪):chat markdown 远程图(![](https://…))在 CSP=null webview 无 sanitizer 实时渲染→打开即请求外部 URL(exfil)。Arch-A:resolv

## 1. Requirement
根⑤ 远程内容 exfil 边界收口(carry-over from abandoned run_98272468, EVALUATE/THINK/PLAN 已 fresh-context 证伪):chat markdown 远程图(![](https://…))在 CSP=null webview 无 sanitizer 实时渲染→打开即请求外部 URL(exfil)。Arch-A:resolveImageSrc drop remote(return undefined,非'')+ base img:850 走它(载重,覆盖 desktop+Hive)+ Tauri CSP img-src-only belt(desktop)。sanitizer 砍(v10 无 rehype-raw)。AC6 根①读侧不并入(异主题)。

## 2. Evaluation
| Dimension | Score | Recommendation |
|---|---|---|
| **ROI** | **high** | **GO** |

**Acceptance Criteria:**
1. AC1: resolveImageSrc DROPS remote http(s) image src instead of pass-through; local workspace (localhost/api/workspace) + data: still resolve.
2. AC2: base img component (MarkdownRenderer.tsx:850, chat path) routes src through hardened resolveImageSrc (currently passes raw, bypassing filtering).
3. AC3: a markdown remote image in chat triggers NO external fetch (rendered img has no external src).
4. AC4: Tauri CSP img-src desktop belt — does not break local images, mermaid PNG export, Hive same-origin.
5. AC5: legitimate local workspace images (basePath doc preview) still render.
6. AC6 (root① backlog, conditional): memory_extractor + summarization strip tool-call leaks from historical rows before Bedrock — close 2 re-induction channels.


## 3. Design & Approach
**Research Findings (THINK):**
- img component has exactly 2 sites: base :850 (chat, basePath undefined, passes src RAW — the exfil bypass) + override :899 (file-preview, already calls resolveImageSrc). resolveImageSrc 1 definition :703.
- DROP must return undefined, NOT '' — WebKit self-fetches an empty src against the page URL; React omits the attr for undefined → zero fetch. Signature already string|undefined.
- Local/remote discrimination nuance: Hive legit local image is a BARE-RELATIVE path (VITE_API_URL='' → /api/...), so a host==localhost check alone MISSES it. Correct: http(s) branch uses new URL() → keep only host localhost/127.0.0.1; relative/absolute-path branch falls through unchanged (covers Hive).
- Ordering: the remote-drop MUST run at the http branch (:706) BEFORE the basePath-undefined early return (:711).
- CSP: set img-src ONLY, never default-src (default-src 'self' would break KaTeX/highlight.js/material-symbols font/daemon fetch). img-src 'self' http://localhost:* http://127.0.0.1:* data: blob: asset: tauri:. Desktop-only belt; Hive has no Tauri CSP so component fix is its sole protection.
- AC6 (root① read-side leak strip) is a DIFFERENT theme (tool-call leak, not image exfil) — NOT folded in (scope creep, R5). Stays root① backlog.
- Blast radius: both chat + file-preview route through img component; blocking both is recommended (workspace .md is also an injection carrier). Human-authored remote image in a previewed doc gets a broken-img slot — accepted tradeoff.

**Alternatives Evaluated:**
- ? — effort: S
- ? — effort: XS
- ? — effort: M

**Chosen Approach:** Arch-A (Gate-0/Gate-1 confirmed root): 3 edits. (1) resolveImageSrc:706 — replace blanket http(s) pass-through with new URL() host check: localhost/127.0.0.1 keep, else undefined; data:/blob: keep. Must run BEFORE the basePath-undefined early-return. (2) base img :850-851 — route src through resolveImageSrc(src). (3) tauri.conf.json:15 — img-src-only CSP (no default-src, which would break KaTeX/hljs/material-symbols/daemon-fetch). Return undefined not '' (WebKit self-fetches empty src). Covers desktop+Hive via component; CSP is desktop belt. Sanitizer dropped (v10 no rehype-raw). AC6 root① read-side NOT in scope (different theme).

**Success Criteria:**
- Remote image in chat → no external fetch (resolveImageSrc returns undefined for non-local host).
- Local workspace image (relative + pre-resolved localhost) still renders.
- CSP img-src-only, no default-src; JSON valid; mermaid PNG-export data: path unaffected.
- Unit test: resolveImageSrc drops https://evil, keeps localhost + relative + data:; mutation-proof (revert → remote kept → RED).


## 4. Pipeline Execution
| Stage | Status | Artifact | Tokens | Summary |
|-------|--------|----------|--------|---------|
| evaluate | completed | art_96aeefa4 | 0 |  |
| think | completed | art_14f4bd17 | 0 |  |
| plan | completed | art_477781c2 | 0 |  |
| build | completed | art_3f2d3a8b | 0 |  |
| review | completed | art_c2720dfb | 0 |  |
| test | completed | art_636e8153 | 0 |  |
| deliver | completed | art_4a41875e | 0 |  |
| reflect | recorded | - | 0 |  |

**Total tokens:** 0 | **Stages:** 7/8 completed | **Validation blocks:** 3

### 4.1 Per-Stage Elapsed (derived from artifact publish times)
| Stage | Published | Elapsed since previous |
|-------|-----------|------------------------|
| evaluate | 13:26:29 | - |
| think | 13:26:31 | 0.0 min |
| plan | 13:26:33 | 0.0 min |
| build | 13:45:58 | 19.4 min |
| review | 13:54:47 | 8.8 min |
| test | 13:58:12 | 3.4 min |
| deliver | 14:12:24 | 14.2 min |
| reflect | - | - |

Slowest stage: `build` at 19.4 min (42% of the 6 measured inter-stage gaps).

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
| (no decisions) | | | |

**Summary:** 0 mechanical, 0 taste, 0 judgment

## 7. Quality Gates
| Gate | Result |
|------|--------|
| REVIEW (code quality) | 2 findings (?) |
| TEST (suite) | True/1 pass |
| Confidence | 0/10 |

### 7.5 Adversarial Review
**1 findings** (verdict: ?)
- [LOW] ![](http://localhost:<anyport>) kept → local-only port-probe surface (no remote 

### 7.6 Completion Audit
(No completion audit data)


## 8. Files Changed
- `{'path': 'desktop/src/components/common/MarkdownRenderer.tsx', 'change': 'resolveImageSrc drop remote host (exact localhost/127.0.0.1, fail-closed try/catch) + base img routes through it (was raw — chat exfil bypass)'}`
- `{'path': 'desktop/src-tauri/tauri.conf.json', 'change': 'csp null→img-src-only belt (no default-src)'}`
- `{'path': 'desktop/src/components/common/__tests__/resolveImageSrc.security.test.ts', 'change': 'new: 18 security tests'}`

**+0 / -0 lines** | 3 files

## 9. Lessons
- [pitfall] 一个把远程 URL pass-through 给 <img> 的 markdown renderer 在 CSP=null 的 webview 里是 tracking-pixel/exfil 向量:图片是 DISPLAY 时自动 fetch(无需点击),比 <a> 链接更隐蔽。载重修复在 component 层 drop remote src(覆盖 desktop+web),CSP img-src 只是 desktop belt——react-markdown v10 无 rehype-raw 时 ![](url)→img 是唯一向量,sanitizer 冗余。
- [pitfall] 判别 local-vs-remote host 必须用 new URL(src).hostname 的 EXACT 等于(=== localhost/127.0.0.1),绝不 startsWith/includes:否则 https://localhost.evil.com / https://localhost@evil.com(userinfo→host 是 evil.com)/ http://127.0.0.1.evil.com 全部绕过。new URL() 对 malformed(https:// 带空格)会 throw,必须 try/catch→drop(fail-closed),否则 throw 冒泡进 img render 白屏整个 chat tab(variant=tab ErrorBoundary)。
- [decision] 阻断 src 应 return undefined 而非 空字符串:空 src 让 WebKit self-fetch 当前页 URL;undefined 让 React 省略 attribute → 零请求。
- [decision] 从 csp:null 改成非-null CSP 是整个 webview 的行为变更(Tauri v2 会 merge 自己的 nonce/protocol 指令),vitest/tsc 测不到——首次生效前必须 packaged-build smoke test 看 DevTools 0 条 CSP refusal(SSE/mermaid/KaTeX/fonts/highlight.js)。只设 img-src 不设 default-src 以避免约束 script/style/connect。


## 10. Known Gaps & Attention Flags
- Validator blocked 3 time(s) during execution


---
*Generated by SwarmAI Autonomous Pipeline | 2026-10-14 14:12 UTC*
