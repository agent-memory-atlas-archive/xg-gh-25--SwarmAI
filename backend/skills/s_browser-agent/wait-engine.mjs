/**
 * wait-engine.mjs — event-driven readiness/wait engine for browser-agent.
 *
 * Replaces the fixed-`waitForTimeout` sleeps + message-count polling that made
 * multi-turn streaming-SPA automation unreliable. Design doctrine + industry
 * survey: Knowledge/Library/2026-09-23-browser-computer-use-agent-architecture.md.
 *
 * Readiness detection priority (that doc §4, Playwright-team + MDN consensus):
 *   1. assert a specific element state (caller's job, via `wait` semantic conditions)
 *   2. waitForCompletion — post-action barrier (settle → nav load-state OR outstanding
 *      request drain), everything raced against a hard hang-guard cap
 *   3. semantic done-signal (send-button re-enable / stop-button gone / aria-busy clear)
 *   4. MutationObserver quiescence (debounce); textContent-stable as the FALLBACK
 *      when the observer can't be injected (Gate-1 WARN: not a parallel 3rd race leg)
 *
 * HANG-GUARD CONTRACT (STEERING #2): every wait races against `maxMs`. The cap is a
 * TRUE hang-guard — it bounds a signal that may never fire (a never-settling request,
 * a never-quiet stream). On cap it RESOLVES a non-completion result; it NEVER throws
 * and NEVER truncates in-progress work (the action already happened; we only report
 * whether the page settled). No cost/budget semantics anywhere.
 *
 * MECHANISM DECLARATIONS (build.md Step 1.7):
 *   - Outstanding-request tracking: Playwright `request`/`requestfinished`/`requestfailed`
 *     page events. ASSUMPTION: a request in-flight fires `request` and later exactly one
 *     of finished/failed. VERIFY: Playwright docs + fixture test (never-settling IP).
 *   - MutationObserver: injected via `page.waitForFunction` running in-page. ASSUMPTION:
 *     observer fires on childList/characterData/subtree mutations; debounce timer in-page.
 *     VERIFY: MDN + fixture test (streaming container).
 *   - page.waitForLoadState('load'): Playwright standard. Used only on `navigated:true`.
 */

// ─── Post-action readiness barrier ──────────────────────────────────
/**
 * Wait until the page has settled after an action.
 *   navigated: true  → await load-state (a navigation was triggered)
 *   navigated: false → drain outstanding document/xhr/fetch requests
 * Always bounded by maxMs (hang-guard). Returns {settled:boolean, reason}.
 * NEVER throws — an action barrier must not fail the action it follows.
 */
export async function waitForCompletion(page, opts = {}) {
  const settleMs = opts.settleMs ?? 400;
  const maxMs = opts.maxMs ?? 8000;
  const navigated = opts.navigated ?? false;
  const start = Date.now();

  // Short settle so a synchronous DOM update / microtask lands before we inspect.
  await sleep(Math.min(settleMs, maxMs));

  const remaining = () => maxMs - (Date.now() - start);

  try {
    if (navigated) {
      // A navigation was triggered — wait for the document 'load' event, capped.
      const cap = Math.max(remaining(), 0);
      const won = await race(
        page.waitForLoadState('load', { timeout: cap }).then(() => 'load').catch(() => null),
        cap,
      );
      if (won === 'load') return { settled: true, reason: 'load-state' };
      return { settled: false, reason: 'load-timeout' };
    }

    // Non-navigation: drain outstanding network requests (filtered). drainRequests
    // self-caps via its own capTimer + always page.off()s its listeners in finish(),
    // so call it DIRECTLY — wrapping it in an outer race() of ~equal duration would
    // let the outer timeout win nondeterministically and orphan the listeners for a
    // window (they'd only detach when drainRequests's own capTimer later fired).
    const drained = await drainRequests(page, Math.max(remaining(), 0));
    if (drained === true) return { settled: true, reason: 'requests-drained' };
    if (drained === 'idle') return { settled: true, reason: 'no-pending' };
    return { settled: false, reason: 'drain-timeout' };
  } catch (e) {
    // Defensive: never let the barrier throw. Report unsettled.
    return { settled: false, reason: 'error:' + (e?.message || 'unknown').slice(0, 60) };
  }
}

/**
 * Resolve when the count of in-flight (non-ignorable) requests reaches 0 and
 * stays 0 for a brief grace window; or when the cap elapses. Returns true when
 * genuinely drained, 'idle' if nothing was ever pending, false on cap.
 */
function drainRequests(page, capMs) {
  return new Promise((resolve) => {
    if (capMs <= 0) { resolve('idle'); return; }
    let pending = 0;
    let sawAny = false;
    let graceTimer = null;
    let capTimer = null;
    let settled = false;

    const IGNORE = /google-analytics|googletagmanager|doubleclick|hotjar|segment|sentry|fullstory|\.png|\.jpg|\.gif|\.woff|\.woff2|beacon|analytics|telemetry/i;

    const ignorable = (url) => IGNORE.test(url || '');

    const finish = (val) => {
      if (settled) return;
      settled = true;
      page.off('request', onReq);
      page.off('requestfinished', onDone);
      page.off('requestfailed', onDone);
      if (graceTimer) clearTimeout(graceTimer);
      if (capTimer) clearTimeout(capTimer);
      resolve(val);
    };

    const armGrace = () => {
      if (graceTimer) clearTimeout(graceTimer);
      // 250ms of zero-pending = drained. Short: this is a post-action settle, not networkidle.
      graceTimer = setTimeout(() => finish(sawAny ? true : 'idle'), 250);
    };

    const onReq = (req) => {
      if (ignorable(req.url())) return;
      sawAny = true;
      pending++;
      if (graceTimer) { clearTimeout(graceTimer); graceTimer = null; }
    };
    const onDone = (req) => {
      if (ignorable(req.url())) return;
      pending = Math.max(0, pending - 1);
      if (pending === 0) armGrace();
    };

    page.on('request', onReq);
    page.on('requestfinished', onDone);
    page.on('requestfailed', onDone);

    // If nothing is pending right now, start the grace clock immediately.
    armGrace();
    capTimer = setTimeout(() => finish(false), capMs);
  });
}

// ─── Streaming-reply completion detection ───────────────────────────
/**
 * Detect that a streamed reply finished. Multi-signal, priority-ordered:
 *   (A) semantic done-signal — send button re-enabled / stop button gone / aria-busy clear
 *   (B) MutationObserver quiescence on the reply container (debounce `quietMs`)
 *   (C) FALLBACK (observer injection failed) — textContent stable N consecutive polls
 * All raced against `maxMs` (hang-guard). Returns {done, signal?, timedOut?}.
 * NEVER throws.
 */
export async function waitForReplyComplete(page, opts = {}) {
  const maxMs = opts.maxMs ?? 60000;
  const quietMs = opts.quietMs ?? 800;
  const { sendBtnSel, stopBtnSel, busyContainerSel } = opts;
  const start = Date.now();
  const remaining = () => Math.max(maxMs - (Date.now() - start), 0);

  const signals = [];

  // (A) Semantic signals — whichever the caller provided.
  // ⚠️ require-TRANSIENT-first (symmetric with the aria-busy leg below): a reply
  // completion is a STATE TRANSITION (send disabled→enabled, stop shown→hidden). If
  // we only wait for the terminal state, it is ALREADY satisfied in the window BEFORE
  // streaming starts — on a cold turn with a "think delay" the Stop button hasn't
  // mounted yet, so waitFor({hidden}) resolves INSTANTLY and reports done before a
  // single token. So each button signal first waits for the ACTIVE state (send
  // disabled / stop visible) to confirm the reply STARTED, THEN for the terminal
  // state. If the active state never appears, the leg never fires and quiescence /
  // the other legs decide — never a false-instant-complete.
  if (sendBtnSel) {
    signals.push(
      page.waitForFunction(
        (sel) => { const el = document.querySelector(sel); return el && (el.disabled || el.getAttribute('aria-disabled') === 'true'); },
        sendBtnSel, { timeout: remaining(), polling: 150 },
      )
        .then(() => page.waitForFunction(
          (sel) => { const el = document.querySelector(sel); return el && !el.disabled && el.getAttribute('aria-disabled') !== 'true'; },
          sendBtnSel, { timeout: remaining(), polling: 150 },
        ))
        .then(() => 'send-enabled').catch(() => null),
    );
  }
  if (stopBtnSel) {
    signals.push(
      page.locator(stopBtnSel).first().waitFor({ state: 'visible', timeout: remaining() })
        .then(() => page.locator(stopBtnSel).first().waitFor({ state: 'hidden', timeout: remaining() }))
        .then(() => 'stop-gone').catch(() => null),
    );
  }
  if (busyContainerSel) {
    // aria-busy true→false — ONLY valid if the element actually USES aria-busy.
    // An element with no aria-busy attribute would trivially satisfy "!= 'true'"
    // and fire instantly (false-complete), so we first require it to be busy=true,
    // THEN wait for the clear. If it's never busy, this signal simply never fires
    // and the MutationObserver-quiescence signal below decides completion.
    signals.push(
      page.waitForFunction(
        (sel) => { const el = document.querySelector(sel); return el && el.getAttribute('aria-busy') === 'true'; },
        busyContainerSel, { timeout: remaining(), polling: 150 },
      )
        .then(() => page.waitForFunction(
          (sel) => { const el = document.querySelector(sel); return el && el.getAttribute('aria-busy') !== 'true'; },
          busyContainerSel, { timeout: remaining(), polling: 150 },
        ))
        .then(() => 'aria-busy-clear').catch(() => null),
    );
    // (B) MutationObserver quiescence on the container, with (C) textContent fallback.
    // A per-call nonce forces a fresh `last` baseline: the observer node is reused
    // across calls, so without re-baselining, call N+1 would read call N's stale
    // last-mutation time and report quiet INSTANTLY (false-complete before stream N+1
    // emits). start (a per-call ms stamp) is a sufficient nonce.
    signals.push(quiescence(page, busyContainerSel, quietMs, remaining(), start).catch(() => null));
  }

  if (signals.length === 0) {
    // No signal to key on — degrade to a bounded settle so we never hang.
    await sleep(Math.min(quietMs, maxMs));
    return { done: false, signal: null, timedOut: false, reason: 'no-signal-selectors' };
  }

  // Race all provided signals against the hang-guard cap.
  const winner = await race(firstNonNull(signals), remaining());
  if (winner && winner !== '__timeout__') {
    return { done: true, signal: winner };
  }
  return { done: false, timedOut: true, signal: null };
}

/**
 * Resolve when the container's subtree has been silent for `quietMs`, using an
 * in-page MutationObserver. If the observer cannot be injected (waitForFunction
 * throws), fall back to polling textContent for N consecutive equal reads.
 */
async function quiescence(page, selector, quietMs, capMs, nonce = 0) {
  try {
    // In-page: install (once) an observer that stamps last-mutation time; resolve
    // waitForFunction when (now - lastMutation) >= quietMs. The observer node is
    // REUSED across waitForReplyComplete calls, so a per-call `nonce` re-baselines
    // `last` exactly once per call — otherwise call N+1 reads call N's stale
    // timestamp and returns quiet before stream N+1 emits (false-complete). The
    // observer itself is installed once and left attached (cheap; re-baselining,
    // not re-attaching, is what prevents the stale-read).
    await page.waitForFunction(
      ([sel, quiet, n]) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        const KEY = '__wa_quiesce__';
        if (!el[KEY]) {
          el[KEY] = { last: Date.now(), nonce: n };
          const obs = new MutationObserver(() => { el[KEY].last = Date.now(); });
          obs.observe(el, { childList: true, characterData: true, subtree: true });
          el[KEY].obs = obs;
        } else if (el[KEY].nonce !== n) {
          // New call on a reused node: re-baseline once so a prior idle gap can't
          // instantly satisfy the quiet window for this call.
          el[KEY].nonce = n;
          el[KEY].last = Date.now();
        }
        return (Date.now() - el[KEY].last) >= quiet;
      },
      [selector, quietMs, nonce],
      { timeout: capMs, polling: 100 },
    );
    return 'mutation-quiet';
  } catch (e) {
    // FALLBACK: observer path unavailable / timed out inside cap — poll textContent.
    return await textStable(page, selector, quietMs, capMs);
  }
}

/** Fallback: resolve when textContent is unchanged across enough consecutive polls to span quietMs. */
async function textStable(page, selector, quietMs, capMs) {
  const interval = 150;
  const need = Math.max(2, Math.ceil(quietMs / interval));
  const start = Date.now();
  let last = null, stable = 0;
  while (Date.now() - start < capMs) {
    let cur = null;
    try { cur = await page.locator(selector).first().textContent({ timeout: 500 }); } catch { /* transient */ }
    if (cur !== null && cur === last) { stable++; if (stable >= need) return 'text-stable'; }
    else { stable = 0; last = cur; }
    await sleep(interval);
  }
  throw new Error('textStable cap');
}

// ─── Element signature + diff (AC5 — stable-signature indexing) ─────
/**
 * Deterministic signature for an element record. Stable across reads for the
 * same element (unlike the per-read browser-order `index`). NOT a CDP
 * backend_node_id (the in-page evaluate DOM build can't reach one) — a scoped
 * degrade that satisfies "page-local change must not reindex everything".
 */
export function computeSig(el) {
  const tag = el.tag || '';
  const selector = el.selector || '';
  const text = (el.text || '').slice(0, 40).replace(/\s+/g, ' ').trim();
  // buildSelector's CSS-path fallback (`div > button:nth-of-type(1)`) is NOT
  // globally unique — two sibling-structured buttons with the same visible text
  // collide on (tag|selector|text). Fold in the element's bounding box so
  // distinct on-screen elements get distinct sigs (position is stable within a
  // read; layout shift across reads is the same false-new the diff already tolerates).
  const r = el.rect || {};
  const geo = [r.x, r.y, r.w, r.h].map((n) => (n == null ? '' : Math.round(n))).join(',');
  return `${tag}|${selector}|${text}|${geo}`;
}

/**
 * Given the previous and current element maps, return the current map with each
 * element tagged `isNew` (true if its signature was absent from prev). No prev
 * (first read) → every element isNew:true (a fresh page, correctly "all new").
 */
export function diffElementMap(prev, cur) {
  const prevSigs = new Set((prev || []).map(computeSig));
  return (cur || []).map((el) => ({ ...el, sig: computeSig(el), isNew: !prevSigs.has(computeSig(el)) }));
}

// ─── small helpers ──────────────────────────────────────────────────
function sleep(ms) { return new Promise((r) => setTimeout(r, Math.max(0, ms))); }

/** Race a promise against a hang-guard timeout. On timeout resolves '__timeout__'. */
function race(promise, capMs) {
  return Promise.race([
    Promise.resolve(promise),
    sleep(Math.max(0, capMs)).then(() => '__timeout__'),
  ]);
}

/** Resolve with the first non-null result among promises, or null if all null. */
function firstNonNull(promises) {
  return new Promise((resolve) => {
    let remaining = promises.length;
    let resolved = false;
    for (const p of promises) {
      Promise.resolve(p).then((v) => {
        if (resolved) return;
        if (v !== null && v !== undefined) { resolved = true; resolve(v); return; }
        remaining--;
        if (remaining === 0) resolve(null);
      }).catch(() => {
        if (resolved) return;
        remaining--;
        if (remaining === 0) resolve(null);
      });
    }
    if (promises.length === 0) resolve(null);
  });
}
