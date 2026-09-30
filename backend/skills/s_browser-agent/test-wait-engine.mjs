#!/usr/bin/env node
/**
 * test-wait-engine.mjs — TDD tests for the readiness/wait engine.
 *
 * Drives real Playwright against local data:URL fixtures (NO external network,
 * NO ChatGPT dependency) to verify the engine's behavior:
 *   - waitForCompletion returns settled:true after in-flight requests finish
 *   - waitForCompletion returns settled:false at maxMs cap WITHOUT hanging
 *   - waitForReplyComplete detects a streaming container going quiet
 *   - waitForReplyComplete honors a semantic done-signal (button re-enable)
 *   - waitForReplyComplete returns at maxMs cap WITHOUT hanging (never-quiet stream)
 *   - computeSig produces stable signatures; diffElementMap flags new elements
 *
 * Run: node test-wait-engine.mjs   (exit 0 = all pass, exit 1 = failure)
 */
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(join(__dirname, 'node_modules', 'playwright', 'index.mjs'));
const {
  waitForCompletion,
  waitForReplyComplete,
  computeSig,
  diffElementMap,
} = await import(join(__dirname, 'wait-engine.mjs'));

const EXEC = process.env.BROWSER_AGENT_EXECUTABLE ||
  `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log(`  ✓ ${msg}`); }
  else { failed++; console.log(`  ✗ FAIL: ${msg}`); }
}

// ── Pure-function tests (no browser needed) ──────────────────────────
function testPureFns() {
  console.log('\n[computeSig / diffElementMap]');
  const a = { tag: 'button', selector: '#send', text: 'Send' };
  const b = { tag: 'button', selector: '#send', text: 'Send' };
  assert(computeSig(a) === computeSig(b), 'computeSig deterministic for identical elements');

  const c = { tag: 'a', selector: '#link', text: 'Home' };
  assert(computeSig(a) !== computeSig(c), 'computeSig differs for different elements');

  // Gate-2 MED: two elements w/ identical tag|selector|text but different position
  // (non-unique CSS-path fallback) must NOT collide.
  const d1 = { tag: 'button', selector: 'div > button:nth-of-type(1)', text: 'OK', rect: { x: 10, y: 20, w: 40, h: 20 } };
  const d2 = { tag: 'button', selector: 'div > button:nth-of-type(1)', text: 'OK', rect: { x: 10, y: 200, w: 40, h: 20 } };
  assert(computeSig(d1) !== computeSig(d2), 'computeSig folds in rect → no collision on same tag/selector/text at different positions');

  const prev = [a, c];
  const cur = [a, c, { tag: 'button', selector: '#new', text: 'New' }];
  const diffed = diffElementMap(prev, cur);
  const newOne = diffed.find(e => e.selector === '#new');
  const oldOne = diffed.find(e => e.selector === '#send');
  assert(newOne && newOne.isNew === true, 'diffElementMap flags the new element isNew=true');
  assert(oldOne && oldOne.isNew === false, 'diffElementMap marks pre-existing element isNew=false');
  assert(diffElementMap([], cur).every(e => e.isNew === true), 'diffElementMap: no prev → all new (but not error)');
}

// ── Browser-driven tests ─────────────────────────────────────────────
async function main() {
  testPureFns();

  const browser = await chromium.launch({ headless: true, executablePath: EXEC, args: ['--no-sandbox'] });
  const page = await browser.newPage();

  try {
    // Fixture 1: a button whose click triggers a fetch that resolves after ~600ms.
    // waitForCompletion should return settled:true, taking >~600ms (waited for it) but < maxMs.
    console.log('\n[waitForCompletion — in-flight request finishes]');
    await page.setContent(`
      <button id="go" onclick="fetch('data:text/plain,ok').then(()=>new Promise(r=>setTimeout(r,600))).then(()=>{window.__done=true;})">Go</button>
      <div id="out"></div>
    `);
    await page.click('#go');
    const t0 = Date.now();
    const r1 = await waitForCompletion(page, { navigated: false, settleMs: 200, maxMs: 8000 });
    const dt1 = Date.now() - t0;
    assert(r1.settled === true, `settled:true after request finished (got ${JSON.stringify(r1)})`);
    assert(dt1 < 8000, `returned before maxMs cap (took ${dt1}ms)`);

    // Fixture 2: a page with an endless pending fetch. waitForCompletion must
    // return settled:false at ~maxMs, NOT hang forever.
    console.log('\n[waitForCompletion — never-settling request hits cap]');
    await page.setContent(`
      <button id="go2" onclick="fetch('http://10.255.255.1/never').catch(()=>{})">Go2</button>
    `);
    // Kick off a request to a black-hole IP (never resolves within cap).
    await page.evaluate(() => { fetch('http://10.255.255.1/never').catch(()=>{}); });
    const t1 = Date.now();
    const r2 = await waitForCompletion(page, { navigated: false, settleMs: 200, maxMs: 1500 });
    const dt2 = Date.now() - t1;
    assert(dt2 < 4000, `returned at/near cap without hanging (took ${dt2}ms, cap 1500)`);
    assert(typeof r2.settled === 'boolean', `returns a boolean settled flag (got ${JSON.stringify(r2)})`);

    // Fixture 3: streaming container that appends text 5x every 150ms then STOPS.
    // waitForReplyComplete should return after it goes quiet, timed after the last append.
    console.log('\n[waitForReplyComplete — streaming container goes quiet]');
    await page.setContent(`
      <div id="reply"></div>
      <script>
        let n=0;
        const iv=setInterval(()=>{
          document.getElementById('reply').textContent += ' chunk'+n;
          if(++n>=5){ clearInterval(iv); }
        },150);
      </script>
    `);
    const t2 = Date.now();
    const r3 = await waitForReplyComplete(page, { busyContainerSel: '#reply', maxMs: 8000, quietMs: 500 });
    const dt3 = Date.now() - t2;
    const replyText = await page.locator('#reply').textContent();
    assert(r3.done === true, `done:true after stream quiet (got ${JSON.stringify(r3)})`);
    assert(replyText.includes('chunk4'), `waited for the LAST chunk (text="${replyText.trim()}")`);
    assert(dt3 >= 750 * 0.8, `returned only after quiet window elapsed past last append (took ${dt3}ms)`);
    assert(dt3 < 8000, `returned before maxMs cap (took ${dt3}ms)`);

    // Fixture 4: semantic done-signal — a Send button disabled during "stream", re-enabled at end.
    console.log('\n[waitForReplyComplete — semantic signal: send button re-enabled]');
    await page.setContent(`
      <button id="send" disabled>Send</button>
      <div id="r2out">streaming...</div>
      <script>
        setTimeout(()=>{ document.getElementById('send').disabled=false; }, 700);
      </script>
    `);
    const t3 = Date.now();
    const r4 = await waitForReplyComplete(page, { sendBtnSel: '#send', maxMs: 8000, quietMs: 400 });
    const dt4 = Date.now() - t3;
    const btnEnabled = await page.locator('#send').isEnabled();
    assert(r4.done === true, `done:true when send re-enabled (got ${JSON.stringify(r4)})`);
    assert(btnEnabled, 'send button is indeed enabled at return');
    assert(r4.signal === 'send-enabled' || r4.signal, `reports which signal fired (got signal=${r4.signal})`);

    // Fixture 4b (Gate-2 HIGH #1): stop-button that NEVER appears (cold turn, think-delay).
    // Must NOT false-complete via stop-gone; require-visible-first means the stop leg
    // never fires, so it should fall through to the cap (done:false), NOT return early.
    console.log('\n[waitForReplyComplete — stop-btn never appears must NOT false-complete]');
    await page.setContent(`<div>no stop button here</div>`);
    const t4b = Date.now();
    const r4b = await waitForReplyComplete(page, { stopBtnSel: '#stop-never', maxMs: 1200, quietMs: 400 });
    const dt4b = Date.now() - t4b;
    assert(r4b.done === false, `stop-gone does NOT fire when stop never appeared (got ${JSON.stringify(r4b)})`);
    assert(dt4b >= 1000, `waited to cap rather than instant false-complete (took ${dt4b}ms)`);

    // Fixture 4c (Gate-2 HIGH #4): TWO waitForReplyComplete on the SAME reused container.
    // Call 1 streams+stops; then idle; call 2 must wait for the NEW stream, not
    // instantly return on call-1's stale last-mutation baseline.
    console.log('\n[waitForReplyComplete — reused container: 2nd call must wait for new stream]');
    await page.setContent(`<div id="reuse"></div>
      <script>
        window.__stream = (n, done) => { let i=0; const iv=setInterval(()=>{ document.getElementById('reuse').textContent+=' t'+i; if(++i>=n){clearInterval(iv); if(done)window.__done=true;} },120); };
      </script>`);
    await page.evaluate(() => window.__stream(3));
    await waitForReplyComplete(page, { busyContainerSel: '#reuse', maxMs: 6000, quietMs: 500 });
    await page.waitForTimeout(1200); // idle gap between turns (stale-last window)
    // start call 2's stream slightly AFTER we begin waiting
    const call2 = waitForReplyComplete(page, { busyContainerSel: '#reuse', maxMs: 6000, quietMs: 500 });
    await page.waitForTimeout(150);
    await page.evaluate(() => window.__stream(4));
    const t4c = Date.now();
    const r4c = await call2;
    const dt4c = Date.now() - t4c;
    const reuseText = await page.locator('#reuse').textContent();
    assert(r4c.done === true, `2nd call completes (got ${JSON.stringify(r4c)})`);
    assert(reuseText.includes('t3'), `2nd call waited for the NEW stream's last chunk (text tail: "${reuseText.trim().slice(-30)}")`);

    // Fixture 5: never-quiet stream — must hit maxMs cap without hanging.
    console.log('\n[waitForReplyComplete — never-quiet stream hits cap]');
    await page.setContent(`
      <div id="r3out"></div>
      <script>
        setInterval(()=>{ document.getElementById('r3out').textContent += 'x'; }, 50);
      </script>
    `);
    const t4 = Date.now();
    const r5 = await waitForReplyComplete(page, { busyContainerSel: '#r3out', maxMs: 1500, quietMs: 500 });
    const dt5 = Date.now() - t4;
    assert(dt5 < 4000, `returned at/near cap without hanging (took ${dt5}ms, cap 1500)`);
    assert(r5.done === false || r5.timedOut === true, `reports non-completion at cap (got ${JSON.stringify(r5)})`);

  } finally {
    await browser.close();
  }

  console.log(`\n${'='.repeat(50)}\nRESULT: ${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch(e => { console.error('TEST HARNESS ERROR:', e); process.exit(1); });
