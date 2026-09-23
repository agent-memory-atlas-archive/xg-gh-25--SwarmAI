# Browser Agent


## Scripts & Entry Points

**Available scripts:**
- `browser-agent.mjs` [ENTRY]: browser-agent.mjs — DOM-based browser automation for SwarmAI (exists)


Accessibility-tree web automation: navigate websites, read page content as a
Playwright-native a11y tree, click elements, fill forms, extract data, and take
screenshots using Playwright.

## Perception model

This skill uses **Playwright's library-native accessibility tree** (`ariaSnapshot()`)
for perception — the same a11y-tree approach a screen reader (and Playwright MCP) uses,
but WITHOUT any MCP server. `ariaSnapshot` is a public Playwright API; there is no need
to mount `@playwright/mcp` (its ref-bearing snapshot is an MCP-server wrapper the
library does not require). This skill is self-contained: it owns tab management,
persistent CDP sessions, `extract`/`eval`, and screenshots — capabilities the MCP does
not provide — on top of the same stable, token-efficient a11y perception.

---

**Why?** Automate real browser interactions: navigate sites, read page content as compressed DOM,
click buttons/links by element index, fill forms, extract data, and take screenshots.
Uses Playwright with DOM compression (not screenshot/coordinate based) for reliable, token-efficient
web automation.

**Key advantage over WebFetch:** Full browser with JavaScript execution, cookies, sessions, tabs,
and interactive element manipulation.

---

## Quick Start

```
"Go to example.com and find the pricing page"
"Fill in the contact form on their website"
"Extract all product names from this page"
"Take a screenshot of the dashboard"
```

---

## Setup

### Prerequisites

Playwright must be installed with browsers:

```bash
# Check if available
npx playwright --version

# Install browsers if needed (one-time)
npx playwright install chromium
```

### Script Location

```
.claude/skills/s_browser-agent/browser-agent.mjs
```

All commands run via:
```bash
node .claude/skills/s_browser-agent/browser-agent.mjs <action> [args...]
```

For convenience in examples below, we use `BA` as shorthand for the full path.

---

## Core Workflow: Launch → Read → Act → Verify

### Step 1: Launch Browser (background)

```bash
# Start browser server in background
node .claude/skills/s_browser-agent/browser-agent.mjs launch &

# Or launch and navigate immediately
node .claude/skills/s_browser-agent/browser-agent.mjs launch https://example.com &
```

> The `launch` command runs in background (use `&` or run_in_background).
> It stays alive until `close` is called.

### Step 2: Navigate + Read DOM

```bash
# Navigate to a URL — returns compressed DOM with element indices
node .claude/skills/s_browser-agent/browser-agent.mjs navigate https://example.com
```

Output shows compressed DOM like:
```
<header>
  <nav>
    [1]<a href="/home">Home</a>
    [2]<a href="/about">About</a>
    [3]<a href="/pricing">Pricing</a>
  </nav>
</header>
<main>
  <h1>Welcome to Example</h1>
  <p>Some content here...</p>
  [4]<button>Get Started</button>
  <form action="/search">
    [5]<input type="text" placeholder="Search...">
    [6]<button type="submit">Search</button>
  </form>
</main>
```

Elements with `[N]` indices are interactive — use these indices for click/type/etc.

### Step 3: Interact

```bash
# Click a link by index
node .claude/skills/s_browser-agent/browser-agent.mjs click 3

# Type into an input
node .claude/skills/s_browser-agent/browser-agent.mjs type 5 "search query"

# Press Enter
node .claude/skills/s_browser-agent/browser-agent.mjs press Enter
```

### Step 4: Verify (re-read DOM)

After each interaction, the `click` command automatically returns the updated DOM.
For other actions, explicitly read:

```bash
node .claude/skills/s_browser-agent/browser-agent.mjs read
```

### Step 5: Close When Done

```bash
node .claude/skills/s_browser-agent/browser-agent.mjs close
```

---

## Command Reference

### Session Management

| Command | Description |
|---------|-------------|
| `launch [url] [--headed]` | Start browser in background. `--headed` for visible window |
| `close` | Stop browser and clean up |

### Navigation

| Command | Description |
|---------|-------------|
| `navigate <url>` | Go to URL, returns compressed DOM |
| `back` | Browser back |
| `forward` | Browser forward |
| `scroll <up\|down> [amount]` | Scroll page (default: 3 units) |

### Reading Page Content

| Command | Description |
|---------|-------------|
| `read [--max-depth N]` | Get compressed DOM (default depth: 15) |
| `screenshot [path] [--full]` | Screenshot (default: /tmp/browser-screenshot.png) |
| `extract <css-selector>` | Get text from all matching elements |

### Interacting with Elements

| Command | Description |
|---------|-------------|
| `click <index>` | Click element by [N] index. Returns updated DOM |
| `type <index> <text>` | Clear field + type text into element |
| `select <index> <value>` | Select dropdown option |
| `hover <index>` | Hover over element. Returns updated DOM |
| `press <key>` | Press keyboard key (Enter, Tab, Escape, ArrowDown...) |
| `submit <index>` | Submit a form |

### Tab Management

| Command | Description |
|---------|-------------|
| `tabs` | List all open tabs |
| `tab <index>` | Switch to tab by index |
| `newtab [url]` | Open new tab |
| `closetab` | Close current tab |

### Advanced

| Command | Description |
|---------|-------------|
| `eval <js-expression>` | Execute JavaScript in page |
| `wait <ms\|selector>` | Wait for time (bare ms) or element (bare selector) — back-compat |
| `wait --text <t>` | Wait until text becomes visible (semantic, event-driven) |
| `wait --text-gone <t>` | Wait until text disappears (e.g. a "Loading…" spinner) |
| `wait --aria-busy-clear <sel>` | Wait until `aria-busy` clears on an element |
| `wait --selector-state <sel:state>` | Wait for element state (`visible`/`hidden`/`attached`), e.g. `#send:visible` |
| `wait-reply --busy <sel> \| --send-btn <sel> \| --stop-btn <sel>` | **Detect a streaming reply finished** (chat SPAs) — multi-signal, capped |
| `pdf [path]` | Save page as PDF |

All `wait*` semantic conditions accept `--max-ms N` (default 10000 for `wait`, 60000
for `wait-reply`); `wait-reply` also takes `--quiet-ms N` (MutationObserver debounce
window, default 800).

---

## Readiness / Waiting — Event-Driven Engine (READ THIS for dynamic SPAs)

**The tool no longer relies on fixed `sleep` between actions.** After every
`click`/`type`/`submit`/`navigate`/`press`, the tool runs an **event-driven
readiness barrier** (`waitForCompletion`): it detects whether the action triggered
a navigation (→ waits for the `load` event) or an in-page fetch (→ drains
outstanding requests), everything bounded by a hard hang-guard cap so it can never
hang. Action responses now carry a `settled` flag.

**For streaming chat SPAs (ChatGPT, Claude, etc.) — use `wait-reply`, NOT a fixed
sleep and NOT counting messages.** After sending a message, call:

```bash
# ChatGPT: the Stop button appears while streaming and disappears when done.
node .claude/skills/s_browser-agent/browser-agent.mjs wait-reply \
  --stop-btn '[data-testid="stop-button"]' --send-btn '[data-testid="send-button"]' \
  --max-ms 90000 --quiet-ms 1200
```

`wait-reply` races multiple completion signals (priority order):
1. **Semantic signal** — send-button re-enabled (`--send-btn`) / stop-button gone
   (`--stop-btn`) / `aria-busy` cleared (`--busy`). Most reliable when the site
   exposes it.
2. **MutationObserver quiescence** — the reply container (`--busy <sel>`) goes
   silent for `--quiet-ms`. Fallback when no semantic signal exists.
3. **textContent-stable** — internal fallback if the observer can't be injected.

Returns `{done, signal, timedOut}`. `done:true` + a `signal` = reliably complete.
On a never-quiet stream it returns `done:false, timedOut:true` at the cap — never hangs.

**New-element marking:** `read`/`navigate`/`click` output now prefixes newly-appeared
interactive elements with `*` (e.g. `*[7]<button>`) and reports a `newElements` count,
so you can see what an action changed without re-reading the whole DOM.

### ChatGPT field notes (learned 2026-09-23)
- **Login wall for uploads:** anonymous mode blocks file upload ("Add files. Log in
  to use."). Use a persistent profile (`launchPersistentContext`) + manual login.
- **File upload path:** `setInputFiles` on the hidden input does NOT work. Open the
  `+` menu → "Add photos & files" → intercept the system file chooser
  (`page.on('filechooser')` → `fc.setFiles(path)`). Chip renders on success.
- **Composer** is a ProseMirror `div[contenteditable]`, not the visible `textarea`
  (that's a hidden fallback). Click it, `Ctrl/Cmd+A` → `Backspace` → type.
- **Free tier rate-limits** long multi-turn sessions ("Chat paused until HH:MM").

---

## DOM Compression

The `read` and `navigate` commands return a **Playwright-native accessibility-tree**
representation (via `ariaSnapshot()` — the a11y-tree perception school, NOT a self-built
DOM traversal, and NOT @playwright/mcp). Perception is Playwright's own accessibility tree.

### Body format
```
- main:
  - heading "Welcome" [level=1]
  - button "Send"
  - textbox "Message"      ← contenteditable composers surface as textbox (name = aria-label)
  - link "Docs": /url: /docs

--- Interactive elements ---
[1] button "Send"
[2] textbox "Message"
[3] link "Docs"
```
The top block is the raw a11y YAML tree (full structural context: role + accessible
name + state + level + url). The `--- Interactive elements ---` block lists the
actionable nodes with `[N]` indices for `click <N>` / `type <N>`.

### Why a11y perception
- **role + accessible name** is BOTH the perception representation AND the locator key.
  `click`/`type` resolve a node via `getByRole(role, {name})` (Playwright auto-wait),
  falling back to CSS/coordinate only when needed.
- **contenteditable rich-text composers** (e.g. ChatGPT's ProseMirror) surface cleanly
  as `textbox` and are typed via the role locator — no hand-built CSS selector needed.
- Duplicate role+name nodes are disambiguated by occurrence order (nth) internally.
- New elements since the last read are still `*`-prefixed (`*[N] button "..."`).

### Element Index Rules
- Indices `[1], [2], [3]...` are assigned to interactive a11y nodes in document order
- Indices are **ephemeral** — they reset on each `read`/`navigate`/`click`/`scroll`
- Always use the most recent indices from the last read
- If an action changes the page, the response includes refreshed indices

### Fallback
If `ariaSnapshot` throws or yields no interactive nodes, perception falls back to the
legacy self-built DOM traversal (`stats.perception` reports `compressDOM-fallback`).
This is a strangler-fig safety net, not the default path.

---

## Common Patterns

### Browse and Navigate

```bash
# Launch, go to site, find and click a link
node BA launch &
sleep 2
node BA navigate https://example.com
# See [3] link "Pricing" in the interactive-elements list
node BA click 3
# Now on pricing page with a fresh a11y read
```

### Fill a Form

```bash
node BA navigate https://example.com/contact
# a11y read shows: [5] textbox "Email"  [6] textbox "Name"  [7] textbox "Message"  [8] button "Send"
node BA type 5 "user@example.com"
node BA type 6 "John Doe"
node BA type 7 "Hello, I have a question about..."
node BA click 8
```

### Search a Site

```bash
node BA navigate https://example.com
# Find search input [5]<input placeholder="Search...">
node BA type 5 "my search query"
node BA press Enter
# Read search results
node BA read
```

### Extract Data

```bash
node BA navigate https://example.com/products
# Extract all product names
node BA extract "h3.product-name"
# Or extract from table
node BA extract "table tbody td:first-child"
```

### Multi-Tab Workflow

```bash
node BA navigate https://site-a.com
node BA newtab https://site-b.com
node BA tabs          # list both
node BA tab 0         # switch back to site-a
```

### Screenshot for Verification

```bash
node BA navigate https://example.com
node BA screenshot /tmp/page.png
# Then use Read tool to view the screenshot
```

---

## Workflow Rules

1. **Always launch first** — run `launch` in background before any other command
2. **Read before acting** — use `navigate` or `read` to see current DOM before clicking
3. **Use indices from latest read** — indices are ephemeral, always use the most recent ones
4. **Verify after important actions** — `click` auto-returns DOM; for `type`, follow with `read`
5. **Close when done** — always run `close` to free resources
6. **Handle errors gracefully** — if element not found, `read` to refresh indices
7. **Scroll for hidden content** — if target element not in DOM, scroll down and re-read
8. **Use extract for data** — for bulk text extraction, `extract` with CSS selector is more efficient than parsing DOM

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No browser session" | Run `launch` in background first |
| Element [N] not found | Run `read` to refresh element indices |
| Click didn't work | Element may have changed. `read` and try new index |
| Page not loading | Check URL starts with http/https. Increase wait time |
| Too much DOM output | Use `--max-depth 4` to reduce depth, or `extract` for specific data |
| Browser crashed | Run `close` then `launch` again |
| Can't see browser | Add `--headed` to `launch` command |
| Need login/cookies | Use `--headed` to manually log in, then automate from there |

---

## Testing Scenarios

| Scenario | Commands | Expected |
|----------|----------|----------|
| Basic navigation | `launch &` → `navigate https://example.com` | Returns compressed DOM with title |
| Click a link | `navigate` → find [N] → `click N` | New page DOM returned |
| Fill form | `navigate` → `type N text` → `click submit` | Form submitted |
| Extract data | `navigate` → `extract "h2"` | Array of h2 texts |
| Screenshot | `navigate` → `screenshot /tmp/test.png` | PNG file created |
| Multi-tab | `newtab url` → `tabs` → `tab 0` | Tab switching works |
| Scroll + read | `scroll down` → auto DOM refresh | New content visible |
| Cleanup | `close` | Browser process killed |

