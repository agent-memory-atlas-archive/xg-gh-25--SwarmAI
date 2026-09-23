/**
 * aria-perceive.mjs — Playwright-native accessibility-tree perception layer.
 *
 * WHY: replaces the self-built `compressDOM` in-page `page.evaluate` DOM traversal
 * (the CDP-DOM-synthesis school that Amazon-internal real-world use retired as "the
 * single most brittle path" — see Knowledge/Library/2026-09-23-browser-computer-use-
 * agent-architecture.md §1,§5.5) with Playwright's library-native `ariaSnapshot()`
 * a11y tree (the accessibility-tree school). NO @playwright/mcp needed: ariaSnapshot
 * is a PUBLIC library API; the ref-bearing `_snapshotForAI` is MCP-server-only and
 * unnecessary here.
 *
 * WHAT ariaPerceive(page) returns — a shape COMPATIBLE with the old compressDOM
 * (so readDOM's diff/*-mark wrapper + click/type consumers are unchanged):
 *   { title, url, body, elementMap:[{index, role, name, tag, text, selector, rect}],
 *     underParsed, stats }
 * where for every interactive node:
 *   - role/name  : the a11y role + accessible name (perception + locator key)
 *   - tag        : role→tag mapping (backward-compat with click/type Strategy logic)
 *   - text       : = name (backward-compat: old elementMap.text)
 *   - selector   : a STRUCTURED role-locator descriptor (JSON) resolved by
 *                  resolveAriaLocator() — carries {role, name, nth, total} so a
 *                  duplicate role+name stays distinct AND the nth is only trusted
 *                  when the live getByRole count still matches `total`.
 *                  Non-empty is a HARD constraint: wait-engine computeSig consumes it.
 *   - rect       : boundingBox() {x,y,w,h} — computeSig geo field + click/type
 *                  Strategy-3 coordinate fallback (zero rect ⇒ that node has none).
 *
 * MECHANISM: ariaSnapshot() emits an indented YAML a11y tree, one node per line as
 *   `- {role} "{name}"[: inline]` (states/url appear as `[state]` / child `/url:`).
 * ASSUMPTION: interactive nodes are parseable by role+quoted-name; duplicate
 *   role+name resolve by DOM order via getByRole(role,{name}).nth(i).
 * VERIFY: empirically confirmed on playwright 1.63 / chromium-1228 (round-trip probe:
 *   every a11y node → getByRole hit; contenteditable→textbox; dup "Send"→count 2).
 * KNOWN LIMIT (Gate-2): a11y perception drops interactive nodes with NO accessible
 *   name (icon-only buttons, empty links). The `underParsed` signal detects a
 *   significant shortfall vs the YAML's interactive-role lines so readDOM falls back
 *   to compressDOM (which catches unnamed nodes) rather than perceive a partial set.
 */

// a11y roles that are actionable (click/type/select targets). Mirrors the old
// compressDOM INTERACTIVE set, expressed in a11y-role vocabulary.
const INTERACTIVE_ROLES = new Set([
  'button', 'link', 'textbox', 'searchbox', 'checkbox', 'radio', 'switch',
  'combobox', 'listbox', 'option', 'menuitem', 'menuitemcheckbox',
  'menuitemradio', 'tab', 'slider', 'spinbutton', 'gridcell',
]);

// role → HTML tag, for backward-compat with click/type Strategy branches that
// still key off el.tag (e.g. click Strategy-1 chose 'link' vs 'button').
const ROLE_TO_TAG = {
  link: 'a', button: 'button', textbox: 'input', searchbox: 'input',
  checkbox: 'input', radio: 'input', combobox: 'select', option: 'option',
  menuitem: 'button', tab: 'button', switch: 'button', slider: 'input',
  spinbutton: 'input',
};

/**
 * Parse an ariaSnapshot YAML line into {role, name} if it is an interactive node.
 * Line shapes handled:
 *   `- button "Send"`            -> {role:'button', name:'Send'}
 *   `- button "Attach": +`       -> {role:'button', name:'Attach'}
 *   `- textbox "Search"`         -> {role:'textbox', name:'Search'}
 *   `- link "Docs":`             -> {role:'link', name:'Docs'}
 *   `- button [disabled]`        -> unnamed, skipped (no reliable name locator)
 * Returns null for non-interactive / unnamed nodes.
 */
function parseAriaLine(line) {
  // strip leading indent + "- "
  const m = line.match(/^\s*-\s+([a-z]+)\s+"((?:[^"\\]|\\.)*)"/);
  if (!m) return null;
  const role = m[1];
  const name = m[2].replace(/\\"/g, '"');
  if (!INTERACTIVE_ROLES.has(role)) return null;
  if (!name) return null; // unnamed interactive node — no stable a11y locator
  return { role, name };
}

/**
 * Resolve a stored role-locator descriptor back to a Playwright Locator.
 * `descriptor` is the JSON string stored in elementMap[i].selector.
 * Used by click/type to act on a perceived node (Strategy-1 = a11y role locator).
 * ASYNC: it may verify the live getByRole count before trusting the nth index.
 */
export async function resolveAriaLocator(page, descriptor) {
  let d;
  try { d = typeof descriptor === 'string' ? JSON.parse(descriptor) : descriptor; }
  catch { return null; }
  if (!d || d.kind !== 'aria' || !d.role) return null;
  const base = page.getByRole(d.role, d.name ? { name: d.name, exact: true } : undefined);
  // nth-disambiguation is only SAFE if the live getByRole count matches what
  // ariaPerceive saw when it assigned the nth index. parseAriaLine can skip a node
  // (unnamed/wrapped) that getByRole still counts -> the stored nth would then bind
  // to the WRONG element (off-by-one). Guard: use nth ONLY when live count ==
  // the recorded total; on divergence fall back to .first() (safe: same role+name,
  // and a mismatch means our index space is untrustworthy anyway).
  if (typeof d.nth === 'number' && d.nth >= 0) {
    try {
      const liveCount = await base.count();
      if (typeof d.total === 'number' && liveCount === d.total) return base.nth(d.nth);
    } catch { /* count failed — fall through to first() */ }
    return base.first();
  }
  return base.first();
}

/**
 * ariaPerceive(page, sel='body') — the a11y perception entry point.
 * Produces the compressDOM-compatible perception object from the a11y tree.
 */
export async function ariaPerceive(page, sel = 'body') {
  const yaml = await page.locator(sel).ariaSnapshot();
  const lines = yaml.split('\n');

  // First pass: collect interactive (role,name) nodes in document order.
  const parsed = [];
  for (const line of lines) {
    const node = parseAriaLine(line);
    if (node) parsed.push(node);
  }

  // Count occurrences per (role|name) so duplicates get nth-disambiguated.
  const seen = new Map(); // key -> running index
  const total = new Map(); // key -> total count
  for (const n of parsed) {
    const key = `${n.role} ${n.name}`;
    total.set(key, (total.get(key) || 0) + 1);
  }

  // Phase 1: assign index/nth/locator per node (no I/O). Phase 2 fetches all rects
  // in PARALLEL — boundingBox calls are independent, so Promise.all collapses N
  // sequential awaits (a latency cliff on every read/click, Gate-2 perf finding)
  // into ~one round-trip.
  const nodes = parsed.map((n, i) => {
    const key = `${n.role} ${n.name}`;
    const dupCount = total.get(key);
    const nth = dupCount > 1 ? (seen.get(key) || 0) : -1;
    seen.set(key, (seen.get(key) || 0) + 1);
    let loc = page.getByRole(n.role, { name: n.name, exact: true });
    loc = nth >= 0 ? loc.nth(nth) : loc.first();
    return { n, index: i + 1, nth, dupCount, loc };
  });

  const rects = await Promise.all(nodes.map(async ({ loc }) => {
    // Short timeout (NOT 1000ms): a hidden/detached node makes boundingBox wait the
    // FULL timeout before throwing (measured ~1006ms). A visible node resolves in
    // ~50ms; 200ms caps the dead-node cost. Parallel + capped = bounded latency.
    // A zero rect disables coordinate fallback for that node (role locator still works).
    try {
      const bb = await loc.boundingBox({ timeout: 200 });
      if (bb) return { x: Math.round(bb.x), y: Math.round(bb.y), w: Math.round(bb.width), h: Math.round(bb.height) };
    } catch { /* off-screen / detached / timed out */ }
    return { x: 0, y: 0, w: 0, h: 0 };
  }));

  const elementMap = [];
  const bodyLines = [];
  for (let i = 0; i < nodes.length; i++) {
    const { n, index, nth, dupCount } = nodes[i];
    // `total` lets resolveAriaLocator verify the live getByRole count still matches
    // what we saw here before trusting the nth index (guards the off-by-one when a
    // sibling node was skipped by the parser — see resolveAriaLocator).
    const selector = JSON.stringify({ kind: 'aria', role: n.role, name: n.name, nth, total: dupCount });
    elementMap.push({
      index,
      role: n.role,
      name: n.name,
      tag: ROLE_TO_TAG[n.role] || n.role,
      text: n.name, // backward-compat: old elementMap.text
      selector,     // structured aria descriptor (computeSig field, non-empty)
      rect: rects[i], // boundingBox (computeSig field + coord fallback)
    });
    const nthLabel = nth >= 0 ? ` (#${nth + 1})` : '';
    bodyLines.push(`[${index}] ${n.role} "${n.name}"${nthLabel}`);
  }

  // Body = the raw a11y YAML tree (full structural context for the model) + an
  // indexed interactive summary (so click/type <idx> maps to a node, like before).
  const body = yaml + '\n\n--- Interactive elements ---\n' + bodyLines.join('\n');

  // Under-parse signal — the caller (readDOM) falls back to compressDOM when
  // a11y perception would drop interactive elements. Two miss modes, both measured
  // against the number of interactive-role LINES the YAML contains:
  //   (a) UNNAMED interactive nodes — ariaSnapshot lists an interactive role with NO
  //       accessible name (icon-only button, empty link, role=button div). parseAriaLine
  //       requires a quoted name, so these are dropped; old compressDOM caught them via
  //       tag/role/tabindex/contenteditable. Many unnamed -> a11y silently loses them.
  //   (b) WRAPPED names — ariaSnapshot can wrap a long accessible name across lines
  //       (YAML block scalar) which the single-line regex misses.
  // Count interactive-role lines (named OR unnamed) and compare to how many we parsed.
  const interactiveRoleLines = (yaml.match(/^\s*-\s+(button|link|textbox|searchbox|checkbox|radio|combobox|menuitem|menuitemcheckbox|menuitemradio|tab|switch|slider|spinbutton|option)\b/gm) || []).length;
  // Under-parsed if the YAML names interactive roles but we captured < 60% of them
  // (unnamed/wrapped drops), or captured zero while interactive roles are present.
  const underParsed = interactiveRoleLines > 0 &&
    (elementMap.length === 0 || elementMap.length < interactiveRoleLines * 0.6);

  return {
    title: await page.title().catch(() => ''),
    url: page.url(),
    body,
    elementMap,
    underParsed,
    stats: {
      interactiveElements: elementMap.length,
      compressedLength: body.length,
      perception: 'aria', // marks which perception layer produced this
    },
  };
}
