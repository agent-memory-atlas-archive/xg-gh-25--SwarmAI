/**
 * test-aria-perceive.mjs — unit tests for the a11y-tree perception layer.
 *
 * WHAT: verifies ariaPerceive(page) produces an a11y-tree body + a compatible
 * elementMap where EVERY interactive node carries role+name+index AND the
 * computeSig-required fields selector+rect (Gate-1 hard constraint: wait-engine's
 * computeSig consumes tag|selector|text|rect — drop selector/rect and the diff
 * signature collapses + coordinate fallback dies).
 * METHODOLOGY: real chromium (headless=false + full-chrome binary, matching the
 * skill's launch), data:/setContent fixtures, assert on the returned structure.
 * KEY INVARIANTS: (1) elementMap non-empty for an interactive page; (2) each node
 * has role, name, index, selector (non-empty), rect (non-null); (3) duplicate
 * role+name nodes get distinct nth-disambiguated locators; (4) contenteditable
 * surfaces as textbox (the ChatGPT composer case); (5) body is a11y text (role+name),
 * not the old [idx]<tag> self-built DOM string.
 */
import { chromium } from 'playwright';
import { ariaPerceive, resolveAriaLocator } from './aria-perceive.mjs';

const CHROME = process.env.BROWSER_AGENT_EXECUTABLE ||
  `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

let passed = 0, failed = 0;
function ok(cond, msg) { if (cond) { passed++; console.log(`  ✓ ${msg}`); } else { failed++; console.log(`  ✗ FAIL: ${msg}`); } }

async function withPage(html, fn) {
  const b = await chromium.launch({ executablePath: CHROME, headless: false });
  try {
    const p = await b.newPage();
    await p.setContent(html);
    await fn(p);
  } finally { await b.close(); }
}

const FIXTURE = `<main>
  <h1>Title</h1>
  <button>Send</button>
  <button aria-label="Attach file">+</button>
  <a href="/docs">Docs</a>
  <input aria-label="Search" placeholder="q">
  <div contenteditable="true" role="textbox" aria-label="Message"></div>
  <button>Send</button>
  <ul><li>item A</li><li>item B</li></ul>
</main>`;

console.log('=== ariaPerceive perception layer ===');

await withPage(FIXTURE, async (p) => {
  const dom = await ariaPerceive(p);

  // T1: returns compatible shape {body, elementMap, stats, title, url}
  ok(dom && typeof dom.body === 'string', 'T1: returns body string');
  ok(Array.isArray(dom.elementMap), 'T1: returns elementMap array');
  ok(dom.stats && typeof dom.stats.interactiveElements === 'number', 'T1: returns stats.interactiveElements');

  // T2: elementMap non-empty for an interactive page
  ok(dom.elementMap.length >= 5, `T2: elementMap has interactive nodes (got ${dom.elementMap.length})`);

  // T3: EVERY node carries role + name + index (a11y perception)
  const allHaveRoleName = dom.elementMap.every(e => e.role && typeof e.name === 'string' && Number.isInteger(e.index));
  ok(allHaveRoleName, 'T3: every node has role + name + integer index');

  // T4 (Gate-1 HARD CONSTRAINT): every node has non-empty selector + non-null rect
  //     (computeSig consumes tag|selector|text|rect — must not collapse)
  const allHaveSelector = dom.elementMap.every(e => e.selector && e.selector.length > 0);
  const allHaveRect = dom.elementMap.every(e => e.rect && typeof e.rect.x === 'number' && typeof e.rect.w === 'number');
  ok(allHaveSelector, 'T4: every node has non-empty selector (computeSig field)');
  ok(allHaveRect, 'T4: every node has non-null rect{x,w} (computeSig field + coord fallback)');

  // T5: contenteditable surfaces as textbox (ChatGPT composer case)
  const composer = dom.elementMap.find(e => e.role === 'textbox' && e.name === 'Message');
  ok(composer, 'T5: contenteditable[role=textbox] "Message" is perceived as a textbox node');

  // T6: duplicate role+name ("Send" ×2) get DISTINCT locators (nth-disambiguated)
  const sends = dom.elementMap.filter(e => e.role === 'button' && e.name === 'Send');
  ok(sends.length === 2, `T6: both duplicate "Send" buttons perceived (got ${sends.length})`);
  const distinctSelectors = new Set(sends.map(e => e.selector)).size === sends.length;
  ok(distinctSelectors, 'T6: duplicate-name nodes have DISTINCT selectors (nth-disambiguated)');

  // T7: body is a11y text (contains role+name), NOT the old [idx]<tag> string
  ok(/button|textbox|link/.test(dom.body), 'T7: body contains a11y roles (button/textbox/link)');

  // T8: tag field present for backward-compat with click/type (role→tag mapping)
  const link = dom.elementMap.find(e => e.role === 'link');
  ok(link && link.tag === 'a', 'T8: role=link maps to tag=a (click Strategy compat)');
});

// T9 (#4 latency-cliff guard): a page with hidden role+name nodes must NOT burn
// full boundingBox timeout per node. ariaPerceive over a page with several hidden
// buttons should finish well under the old N×1000ms worst case.
await withPage(`<main>${Array.from({length:6},(_,i)=>`<button style="display:none">Hidden ${i}</button>`).join('')}<button>Real</button></main>`, async (p) => {
  const t0 = Date.now();
  const dom = await ariaPerceive(p);
  const dt = Date.now() - t0;
  ok(dt < 3000, `T9: 6 hidden + 1 visible node perceived in ${dt}ms (< 3s — 200ms cap, not 1000ms×N cliff)`);
  ok(dom.elementMap.length >= 1, 'T9: still perceives the nodes (hidden ones just get zero rect)');
});

// T10 (Gate-2 #4/#5): a page with many UNNAMED interactive nodes must flag
// underParsed so readDOM falls back to compressDOM (which catches unnamed elements)
// rather than silently perceiving only the named subset.
await withPage(`<main><button>Named</button><button></button><button aria-label=""></button><div role="button" tabindex="0"></div><a href="/x"></a></main>`, async (p) => {
  const dom = await ariaPerceive(p);
  ok(dom.underParsed === true, `T10: unnamed-heavy page flags underParsed (parsed ${dom.elementMap.length} of ~5 interactive → fallback)`);
});

// T11 (Gate-2 #4/#5): a normal page where a11y names everything must NOT falsely
// flag underParsed (guard against over-triggering the fallback).
await withPage(FIXTURE, async (p) => {
  const dom = await ariaPerceive(p);
  ok(dom.underParsed === false, 'T11: fully-named page does NOT falsely flag underParsed');
});

// T12 (Gate-2 #2): resolveAriaLocator is async + count-guards the nth index; a
// duplicate-name node resolves to exactly one element (nth bound when count matches).
await withPage(`<main><button>Go</button><button>Go</button></main>`, async (p) => {
  const dom = await ariaPerceive(p);
  const go = dom.elementMap.find(e => e.name === 'Go' && e.selector.includes('"nth":1'));
  ok(!!go, 'T12: duplicate "Go" nodes get nth-tagged selectors with total');
  const loc = await resolveAriaLocator(p, go.selector);
  ok(loc && (await loc.count()) === 1, 'T12: resolveAriaLocator (async, count-guarded) resolves nth to exactly 1 element');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
