#!/usr/bin/env node
/**
 * smoke-commands.mjs — AC6 strangler-fig contract smoke.
 * Launches a CDP chromium, writes the state file the CLI expects, then shells
 * each old command (navigate/read/click/wait/screenshot) against a local
 * data:URL fixture and asserts each exits 0 with the expected output shape.
 * NO external network. Proves the readiness-engine refactor didn't regress the
 * command contract.
 */
import { spawnSync, execSync } from 'child_process';
import { writeFileSync, existsSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(join(__dirname, 'node_modules', 'playwright', 'index.mjs'));
const EXEC = '/Users/gawan/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const CDP_PORT = 9222;
const STATE_FILE = '/tmp/.browser-agent-state.json';
const CLI = join(__dirname, 'browser-agent.mjs');

let passed = 0, failed = 0;
const ok = (c, m) => { if (c) { passed++; console.log(`  ✓ ${m}`); } else { failed++; console.log(`  ✗ FAIL: ${m}`); } };

function run(cmdArgs) {
  const r = spawnSync('node', [CLI, ...cmdArgs], { encoding: 'utf8', timeout: 30000 });
  let json = null;
  try { json = JSON.parse(r.stdout); } catch {}
  return { code: r.status, stdout: r.stdout, stderr: r.stderr, json };
}

const FIXTURE = 'data:text/html,' + encodeURIComponent(`
  <html><head><title>Smoke Fixture</title></head><body>
    <h1>Hello</h1>
    <button id="btn" onclick="document.getElementById('out').textContent='clicked'">Click Me</button>
    <div id="out"></div>
    <input id="inp" placeholder="type here" />
  </body></html>
`);

// clean any stale port
try { execSync(`lsof -ti:${CDP_PORT} | xargs kill -9 2>/dev/null`, { stdio: 'ignore' }); } catch {}

const browser = await chromium.launch({
  headless: true, executablePath: EXEC,
  args: ['--no-sandbox', `--remote-debugging-port=${CDP_PORT}`],
});
writeFileSync(STATE_FILE, JSON.stringify({ cdpUrl: `http://localhost:${CDP_PORT}`, ts: Date.now() }));
// ensure a page exists
const cdp = await chromium.connectOverCDP(`http://localhost:${CDP_PORT}`);
const ctx = cdp.contexts()[0] || await cdp.newContext();
if (ctx.pages().length === 0) await ctx.newPage();

try {
  console.log('[navigate]');
  const nav = run(['navigate', FIXTURE]);
  ok(nav.code === 0, `navigate exits 0 (got ${nav.code})`);
  ok(nav.json && nav.json.status === 'ok', 'navigate returns status:ok');
  ok(nav.json && typeof nav.json.dom === 'string' && nav.json.dom.includes('Click Me'), 'navigate DOM contains button text');
  ok(nav.json && 'newElements' in nav.json, 'navigate reports newElements (diff engine wired)');

  console.log('[read]');
  const rd = run(['read']);
  ok(rd.code === 0, `read exits 0 (got ${rd.code})`);
  ok(rd.json && rd.json.dom.includes('type here'), 'read DOM contains input placeholder');

  console.log('[click]');
  // find the button index from read output
  const m = rd.json.dom.match(/\*?\[(\d+)\]<button/);
  ok(!!m, `found button index in DOM (${m ? m[1] : 'none'})`);
  if (m) {
    const clk = run(['click', m[1]]);
    ok(clk.code === 0, `click exits 0 (got ${clk.code})`);
    ok(clk.json && clk.json.status === 'ok', 'click returns status:ok');
    ok(clk.json && 'settled' in clk.json, 'click reports settled flag (waitForCompletion wired)');
  }

  console.log('[wait — bare ms back-compat]');
  const w1 = run(['wait', '100']);
  ok(w1.code === 0 && w1.json.status === 'ok', 'wait 100 (bare ms) exits 0');
  ok(w1.json.waited === '100ms', `wait reports waited=100ms (got ${w1.json && w1.json.waited})`);

  console.log('[wait — semantic --text]');
  const w2 = run(['wait', '--text', 'Hello', '--max-ms', '3000']);
  ok(w2.code === 0 && w2.json.status === 'ok', 'wait --text Hello exits 0 (semantic condition)');

  console.log('[wait — semantic --selector-state]');
  const w3 = run(['wait', '--selector-state', '#inp:visible', '--max-ms', '3000']);
  ok(w3.code === 0 && w3.json.status === 'ok', 'wait --selector-state #inp:visible exits 0');

  console.log('[wait — --selector-state with pseudo-class selector (Gate-2 MED)]');
  const wps = run(['wait', '--selector-state', 'button:first-of-type', '--max-ms', '2000']);
  ok(wps.code === 0 && wps.json.status === 'ok', 'wait --selector-state button:first-of-type (pseudo, no explicit state) exits 0');
  ok(wps.json.waited === 'selector-state:button:first-of-type:visible', `pseudo-selector preserved + default state (got ${wps.json && wps.json.waited})`);

  console.log('[wait — semantic --text-gone (already absent = gone)]');
  const w4 = run(['wait', '--text-gone', 'NonexistentText12345', '--max-ms', '2000']);
  ok(w4.code === 0 && w4.json.status === 'ok', 'wait --text-gone (absent text) exits 0');

  console.log('[wait — semantic --aria-busy-clear (no aria-busy attr = clear)]');
  const w5 = run(['wait', '--aria-busy-clear', '#out', '--max-ms', '2000']);
  ok(w5.code === 0 && w5.json.status === 'ok', 'wait --aria-busy-clear on non-busy element exits 0');

  console.log('[wait-reply — usage guard]');
  const wr = run(['wait-reply']);
  ok(wr.code !== 0, 'wait-reply with no selectors exits non-zero (usage guard)');

  console.log('[screenshot]');
  const ss = run(['screenshot', '/tmp/smoke-shot.png']);
  ok(ss.code === 0 && ss.json.status === 'ok', 'screenshot exits 0');
  ok(existsSync('/tmp/smoke-shot.png'), 'screenshot file created');

  console.log('[extract]');
  const ex = run(['extract', 'h1']);
  ok(ex.code === 0 && ex.json.status === 'ok', 'extract h1 exits 0');

} finally {
  await browser.close();
  try { execSync(`lsof -ti:${CDP_PORT} | xargs kill -9 2>/dev/null`, { stdio: 'ignore' }); } catch {}
}

console.log(`\n${'='.repeat(50)}\nSMOKE: ${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
