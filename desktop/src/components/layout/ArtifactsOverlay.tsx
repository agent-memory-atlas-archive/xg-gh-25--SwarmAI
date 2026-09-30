/**
 * ArtifactsOverlay — the left-nav "Artifacts" surface: a ROLE-grouped product gallery.
 *
 * Artifacts B′ Run 2: the overlay now projects the workspace PRODUCT registry
 * (`GET /artifacts/products` → products.json), NOT the old git-log `/artifacts/recent`
 * view. The load-bearing win: a gitignored deck (under a project assets dir) — which the
 * git-log projection structurally could NOT see — now surfaces. The ROLE is computed once
 * in the backend (`product_registry.derive_role`); this component renders it, never
 * re-derives (run_4de279ca — no second classifier in the frontend).
 *
 * Spatial form (design-judgment Surface-2 + Von Restorff): ONE thing dominant — the
 * **Deliverables** card grid (the products you actually reopen: decks, reports, images).
 * Knowledge / Pipeline / Activity are DEMOTED to collapsible sections below (Pipeline +
 * Activity collapsed by default — they are the "everything looks the same" system files
 * the redesign exists to get out of the way). Whitespace separates role groups, not boxes.
 * Pipeline REPORT.md rows read the same-name problem: labeled by their parent run dir.
 *
 * Still a pure SELECTOR (History's twin): no preview pane, no diff — a row click dispatches
 * `swarm:open-file` (→ current-tab Canvas) then closes. Canvas is the sole file viewer.
 *
 * @exports ArtifactsContent
 * @exports groupByRole — pure role-bucketer (unit-tested)
 * @exports parentRunLabel — pure Pipeline-row label (unit-tested)
 * @exports OPEN_FILE_EVENT — the swarm:open-file event name (shared with the row-click contract)
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { radarService } from '../../services/radar';
import type { Product, ProductRole } from '../../services/radar';
import { fileIcon, fileIconColor } from '../../utils/fileUtils';

/** The window CustomEvent that opens a file in the current tab's Canvas.
 *  Same name LibraryOverlay/BrainHub dispatch — do NOT rename (proprioception contract). */
export const OPEN_FILE_EVENT = 'swarm:open-file';

/** Debounce for the filename filter (mirrors HistoryOverlay's search debounce feel). */
const SEARCH_DEBOUNCE_MS = 200;

/** loading-B poll: while the store is still empty (day-one backfill running in the
 *  background), re-fetch every POLL_MS so the products appear on their own — but stop
 *  after POLL_MAX_MS so a genuinely product-less workspace does not poll forever. */
const BACKFILL_POLL_MS = 2500;
const BACKFILL_POLL_MAX_MS = 45_000;

/** The backend ignores workspace_id (resolves the single workspace from DB config);
 *  a non-empty placeholder satisfies the required query param. */
const WS_PLACEHOLDER = 'default';

// ── Role grouping ──────────────────────────────────────────────────────────────
// The 4 RENDERED roles in display order. `Other` is dropped at write time (never
// reaches the frontend); if one ever arrives it is grouped under Knowledge as a
// defensive fallback (see groupByRole) — never silently lost.
export interface RoleGroup {
  role: ProductRole;
  label: string;
  products: Product[];
}

const ROLE_ORDER: ProductRole[] = ['Deliverables', 'Knowledge', 'Pipeline', 'Activity'];
const ROLE_LABEL: Record<ProductRole, string> = {
  Deliverables: 'Deliverables',
  Knowledge: 'Knowledge',
  Pipeline: 'Pipeline reports',
  Activity: 'Activity',
  Other: 'Other',
};
/** Sections collapsed by default — the demoted "system files" the redesign hides. */
const COLLAPSED_BY_DEFAULT: ReadonlySet<ProductRole> = new Set<ProductRole>(['Pipeline', 'Activity']);

/** Per-role dot color for the filter chips (mockup .rolefilter .dot). Uses theme
 *  vars with sensible fallbacks so it tracks light/dark. */
const ROLE_DOT: Record<ProductRole, string> = {
  Deliverables: 'var(--color-primary)',
  Knowledge: 'var(--color-git-added, #4a9)',
  Pipeline: 'var(--color-git-modified, #d59a26)',
  Activity: 'var(--color-text-faint, #889)',
  Other: 'var(--color-text-faint, #889)',
};

/**
 * Relative "time ago" for a card/row (mockup .ms/.lt: now/Nm/Nh/Nd, else a date).
 * Pure — `now` injectable for tests. An unparseable ISO → "" (the row still renders).
 * <1min→"now"; <60min→"Nm"; <24h→"Nh"; <7d→"Nd"; else a local YYYY-MM-DD stamp.
 */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diff = now - ts;
  if (diff < 0) return 'now';
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'now';
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d`;
  const d = new Date(ts);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/**
 * AC6: absolute local timestamp `YYYY-MM-DD HH:MM` — the primary display (XG asked
 * for a real timestamp, not "2h"). relativeTime is demoted to the hover title.
 * Unparseable → '' (a row must never crash on a bad date).
 */
export function absoluteTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const d = new Date(ts);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd} ${hh}:${mi}`;
}

/**
 * AC7: directory display — the LAST TWO dir segments, eliding any deeper prefix
 * with a leading `…/`. `Projects/SwarmAI/.artifacts/runs/run_x/REPORT.md` →
 * `…/runs/run_x`; a two-level path shows both with no ellipsis; a bare filename → ''.
 */
export function elideDir(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  const dirs = parts.slice(0, -1); // drop the filename
  if (dirs.length === 0) return '';
  if (dirs.length <= 2) return dirs.join('/');
  return `…/${dirs.slice(-2).join('/')}`;
}

/**
 * Bucket products by role into the fixed display order, newest (lastTouched) first
 * within each group. Returns only non-empty groups. An unexpected role (`Other`, or a
 * future value) folds into Knowledge so it is never dropped (exhaustiveness). Pure.
 */
export function groupByRole(products: Product[]): RoleGroup[] {
  const buckets: Record<ProductRole, Product[]> = {
    Deliverables: [], Knowledge: [], Pipeline: [], Activity: [], Other: [],
  };
  for (const p of products) {
    (buckets[p.role] ?? buckets.Knowledge).push(p);
  }
  // Fold any stray Other/unknown into Knowledge (never lost).
  if (buckets.Other.length) {
    buckets.Knowledge.push(...buckets.Other);
    buckets.Other = [];
  }
  const byNewest = (a: Product, b: Product) =>
    (b.lastTouched || '').localeCompare(a.lastTouched || '');
  return ROLE_ORDER
    .filter((r) => buckets[r].length > 0)
    .map((r) => ({ role: r, label: ROLE_LABEL[r], products: [...buckets[r]].sort(byNewest) }));
}

/** basename of a workspace-relative path. */
function baseName(path: string): string {
  const i = path.lastIndexOf('/');
  return i >= 0 ? path.slice(i + 1) : path;
}

/**
 * AC4: a human-friendly card title derived from the filename — strip a leading
 * YYYY-MM-DD(-) date, strip ONLY the last extension (dots mid-name survive),
 * de-slug [-_] to spaces, collapse + title-case. Falls back to the raw basename if
 * the result is empty (an all-date name like `2026-09-30.md` — Gate-1 F2), so a card
 * never renders a blank title.
 */
export function friendlyTitle(name: string): string {
  const base = baseName(name);
  if (!base) return '';
  const noDate = base.replace(/^\d{4}-\d{2}-\d{2}-?/, '');
  const noExt = noDate.replace(/\.[^.]+$/, ''); // strip ONLY the last extension
  // de-slug, drop any leftover leading/trailing dot or space (e.g. `report..md`→`Report`)
  const words = noExt.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').replace(/^[.\s]+|[.\s]+$/g, '').trim();
  if (!words) return base; // degenerate (all-date) → basename, never empty
  return words.replace(/\b\w/g, (c) => c.toUpperCase());
}

/** A coarse product KIND for the thumbnail faux-preview + type badge (AC2). */
export type ThumbKind = 'deck' | 'report' | 'image' | 'pdf' | 'html' | 'doc';
/**
 * Classify a product path into a thumbnail kind + badge label. ORDERED — deck wins
 * over pdf/html for a Pollinate/deck path (Pollinate = a content-package deck, a
 * deliberate call, Gate-1 #3). Defaults to `doc` (never undefined).
 */
export function thumbKind(path: string): { kind: ThumbKind; badge: string } {
  const p = path.replace(/\\/g, '/').toLowerCase();
  const ext = (p.match(/\.([a-z0-9]+)$/)?.[1]) ?? '';
  if (['pptx', 'ppt', 'key'].includes(ext) || /\/(deck|pollinate)\b/.test(p) || p.includes('-deck'))
    return { kind: 'deck', badge: 'DECK' };
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'avif'].includes(ext))
    return { kind: 'image', badge: 'IMG' };
  if (ext === 'pdf') return { kind: 'pdf', badge: 'PDF' };
  if (['html', 'htm'].includes(ext)) return { kind: 'html', badge: 'HTML' };
  // Word-boundary match (Gate-2 MED): a bare includes('report') mis-badges `preport.md`
  // / `reporter-bio.md`. Match the Reports/ dir OR `report` as a whole hyphen/underscore
  // -delimited token, never an arbitrary substring.
  if (/\/reports\//.test(p) || /\breport\b/.test(p.replace(/[-_]/g, ' '))) return { kind: 'report', badge: 'REPORT' };
  return { kind: 'doc', badge: 'DOC' };
}

/**
 * Label a Pipeline REPORT.md row by its parent run dir, not the bare "REPORT.md" —
 * the same-name problem the redesign calls out (3 runs all show "REPORT.md"). Pure.
 * `.../.artifacts/runs/run_2274b401/REPORT.md` → "run_2274b401". Falls back to the
 * basename if the path has no recognizable run segment.
 */
export function parentRunLabel(path: string): string {
  const norm = path.replace(/\\/g, '/');
  const parts = norm.split('/').filter(Boolean);
  const runsIdx = parts.lastIndexOf('runs');
  if (runsIdx >= 0 && runsIdx + 1 < parts.length) return parts[runsIdx + 1];
  return baseName(path);
}

/** Open a file in the current tab's Canvas (same contract as LibraryOverlay). */
export function dispatchOpenFile(path: string): void {
  document.dispatchEvent(new CustomEvent(OPEN_FILE_EVENT, { detail: { path } }));
}

export interface ArtifactsContentProps {
  /** Host-owned close — called after a row opens a file (return to chat/Canvas). */
  close: () => void;
  /** Test seam: override the fetch (defaults to radarService.fetchProducts). */
  fetchProducts?: (wsId: string) => Promise<Product[]>;
}

/**
 * The Artifacts product-gallery body (the host wraps it in scrim + panel + header chrome).
 */
export function ArtifactsContent({ close, fetchProducts }: ArtifactsContentProps) {
  const fetcher = fetchProducts ?? radarService.fetchProducts;

  const { data, isLoading, isError } = useQuery({
    queryKey: ['workspace-products'],
    queryFn: () => fetcher(WS_PLACEHOLDER),
    staleTime: 30_000,
    // loading-B day-one: the endpoint returns immediately + backfills in the BACKGROUND,
    // so a fresh workspace's first read is []. Without this, the overlay would show the
    // empty state until a manual reopen (Gate-2 meta-review HIGH). Poll while the store
    // is still empty so the backfilled products appear on their own — BOUNDED: stop once
    // any product arrives, and cap the poll window (POLL_MAX_MS) so a genuinely
    // product-less workspace does not poll forever.
    refetchInterval: (query) => {
      const rows = query.state.data as Product[] | undefined;
      if (rows && rows.length > 0) return false; // filled → stop polling
      const firstFetch = query.state.dataUpdatedAt || Date.now();
      if (Date.now() - firstFetch > BACKFILL_POLL_MAX_MS) return false; // give up (empty ws)
      return BACKFILL_POLL_MS;
    },
  });

  const [searchRaw, setSearchRaw] = useState('');
  const [search, setSearch] = useState('');
  // Active role filter (null = show all). Clicking the active chip clears it.
  const [activeRole, setActiveRole] = useState<ProductRole | null>(null);
  // Per-role collapse state; seeded from COLLAPSED_BY_DEFAULT, user-toggleable.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // Debounce the filename filter.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchRaw.trim().toLowerCase()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchRaw]);

  const groups = useMemo(() => {
    // Defense in depth: the boundary (radar.fetchProducts) already guarantees an array,
    // but a non-array `data` must NEVER crash this .filter — `?? []` only catches
    // null/undefined, so an unexpected object would slip through. Array.isArray is total.
    const all = Array.isArray(data) ? data : [];
    const filtered = all.filter((p) => {
      if (activeRole && p.role !== activeRole) return false;
      if (search) {
        // Match the VISIBLE text (filename OR the displayLabel a Pipeline row shows)
        // so a search over the label the user actually sees never misses a row.
        const hay = `${baseName(p.path)} ${p.displayLabel ?? ''}`.toLowerCase();
        if (!hay.includes(search)) return false;
      }
      return true;
    });
    return groupByRole(filtered);
  }, [data, search, activeRole]);

  const isCollapsed = (role: ProductRole): boolean => {
    // An explicit user toggle always wins.
    if (role in collapsed) return collapsed[role];
    // Filtering TO a role means the user asked to see it → force-expand, even if it is
    // collapsed-by-default (Pipeline/Activity). Otherwise clicking the Pipeline chip
    // would show only a collapsed header + count — a dead end (Gate-2 API-Contract).
    if (activeRole === role) return false;
    return COLLAPSED_BY_DEFAULT.has(role);
  };

  const toggle = (role: ProductRole) =>
    setCollapsed((c) => ({ ...c, [role]: !isCollapsed(role) }));

  const openRow = (p: Product) => {
    dispatchOpenFile(p.path);
    close();
  };

  const totalShown = groups.reduce((n, g) => n + g.products.length, 0);

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="artifacts-overlay">
      {/* Search + role-filter chips */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <input
          type="text"
          value={searchRaw}
          onChange={(e) => setSearchRaw(e.target.value)}
          placeholder="Search products…"
          data-testid="artifacts-search"
          className="w-full px-3 py-2 rounded-lg bg-[var(--color-input-bg,var(--color-bg-secondary))] border border-[var(--color-border)] text-[12.5px] text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] outline-none focus:border-[var(--color-primary)]"
        />
        {/* Role filter chips (mockup .rolefilter): click to filter to one role,
            click the active chip again to clear. Colored dot per role. */}
        <div className="flex gap-1.5 mt-2 flex-wrap" data-testid="artifacts-rolefilter">
          {ROLE_ORDER.map((role) => {
            const on = activeRole === role;
            return (
              <button
                key={role}
                onClick={() => setActiveRole(on ? null : role)}
                data-testid={`artifacts-chip-${role}`}
                aria-pressed={on}
                className={`flex items-center gap-1.5 text-[10.5px] px-2.5 py-1 rounded-full border transition-colors ${
                  on
                    ? 'border-[var(--color-primary)] text-[var(--color-primary)] bg-[color-mix(in_srgb,var(--color-primary)_12%,transparent)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                <span
                  aria-hidden="true"
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: ROLE_DOT[role] }}
                />
                {ROLE_LABEL[role]}
              </button>
            );
          })}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-3 pb-4" data-testid="artifacts-list">
        {isLoading ? (
          <div className="flex flex-col gap-1 px-1 py-3" data-testid="artifacts-loading">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-9 rounded-md bg-[var(--color-hover)] animate-pulse" />
            ))}
          </div>
        ) : isError ? (
          <div
            className="flex flex-col items-center justify-center gap-2 px-3 py-10 text-center"
            data-testid="artifacts-error"
          >
            <span className="text-[22px]" aria-hidden="true">🐝</span>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              Couldn't load products. Try again in a moment.
            </p>
          </div>
        ) : totalShown === 0 ? (
          <div
            className="flex flex-col items-center justify-center gap-2 px-3 py-10 text-center"
            data-testid="artifacts-empty"
          >
            <span className="text-[22px]" aria-hidden="true">🐝</span>
            <p className="text-[11px] text-[var(--color-text-muted)] max-w-[240px]">
              {(Array.isArray(data) ? data : []).length === 0
                ? 'No products yet. Decks, reports, and files you create show up here.'
                : 'No products match your search.'}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {groups.map((g) =>
              g.role === 'Deliverables' ? (
                <DeliverablesGallery key={g.role} group={g} onOpen={openRow} />
              ) : (
                <RoleSection
                  key={g.role}
                  group={g}
                  collapsed={isCollapsed(g.role)}
                  onToggle={() => toggle(g.role)}
                  onOpen={openRow}
                />
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Deliverables — the PRIMARY, dominant card grid ──────────────────────────────
function DeliverablesGallery({
  group,
  onOpen,
}: {
  group: RoleGroup;
  onOpen: (p: Product) => void;
}) {
  return (
    <section data-testid="artifacts-group-Deliverables">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)] font-semibold px-0.5 pb-2">
        {group.label}
      </div>
      {/* run_fe228bc0: 4-column gallery (was 3) — denser tile wall scans faster. */}
      <div className="grid grid-cols-4 gap-3">
        {group.products.map((p) => {
          const { kind, badge } = thumbKind(p.path);
          const title = friendlyTitle(p.path);
          return (
            <button
              key={p.path}
              onClick={() => onOpen(p)}
              title={p.path}
              data-testid="artifacts-card"
              className="group flex flex-col rounded-[10px] overflow-hidden border border-transparent bg-[var(--color-bg-secondary,var(--color-hover))] hover:border-[var(--color-primary)]/50 hover:bg-[var(--color-hover)] transition-colors text-left"
            >
              {/* AC1/AC2: flatter 16:7 thumbnail zone (was 16:10) — shorter card, denser wall */}
              <span
                data-testid="artifacts-card-thumb"
                className="relative block aspect-[16/7] w-full overflow-hidden"
                style={{ background: 'linear-gradient(135deg,#232838,#1a1e28)' }}
              >
                <ThumbPreview kind={kind} name={baseName(p.path)} />
                <span
                  data-testid="artifacts-card-badge"
                  className="absolute top-1.5 left-1.5 text-[8.5px] font-bold tracking-wide px-1.5 py-0.5 rounded bg-black/45 text-[var(--color-primary)] leading-none z-10"
                >
                  {badge}
                </span>
                {p.gitignored && (
                  <span
                    className="absolute top-1.5 right-1.5 text-[8px] px-1 py-px rounded bg-[var(--color-git-modified,#d59a26)]/25 text-[var(--color-git-modified,#d59a26)] font-medium leading-none z-10"
                    title="Not in git (local-only product) — surfaced anyway"
                    data-testid="artifacts-gitignored-badge"
                  >
                    local
                  </span>
                )}
              </span>
              {/* AC4: meta zone — friendly title + (dir·kind left, absolute time right) */}
              <span className="flex flex-col gap-0.5 px-2.5 py-2">
                <span className="text-[12px] font-medium text-[var(--color-text)] truncate leading-tight">
                  {title}
                </span>
                <span className="flex items-center justify-between gap-2 text-[9.5px] text-[var(--color-text-faint)] leading-tight">
                  <span className="opacity-[0.72] truncate" title={p.path}>
                    {elideDir(p.path)} · {kind}
                  </span>
                  <span
                    className="shrink-0"
                    data-testid="artifacts-card-time"
                    title={relativeTime(p.lastTouched)}
                  >
                    {absoluteTime(p.lastTouched)}
                  </span>
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** CSS-only faux thumbnail preview by kind (AC2, Approach A — no real asset/screenshot). */
function ThumbPreview({ kind, name }: { kind: ThumbKind; name: string }) {
  if (kind === 'image') {
    return (
      <span
        className="absolute inset-0 block"
        style={{ background: 'conic-gradient(from 210deg,#2b3f6b,#6b3f5f,#3f6b52,#2b3f6b)' }}
        aria-hidden="true"
      />
    );
  }
  if (kind === 'report') {
    return (
      <span className="absolute inset-3 rounded-[5px] bg-[#11151d] p-2.5 flex flex-col gap-1.5" aria-hidden="true">
        <span className="h-[7px] w-1/2 rounded-[2px] bg-[#5b8def]/80" />
        <span className="grid grid-cols-2 gap-[5px] mt-0.5">
          <span className="h-5 rounded-[3px] bg-[#1c2637]" />
          <span className="h-5 rounded-[3px] bg-[#1c2637]" />
          <span className="h-5 rounded-[3px] bg-[#1c2637]" />
          <span className="h-5 rounded-[3px] bg-[#1c2637]" />
        </span>
      </span>
    );
  }
  if (kind === 'deck') {
    // faux slide: title bar + text lines + a row of chips (mockup .slide)
    return (
      <span className="absolute inset-3 rounded-[5px] bg-[#11151d] px-2.5 py-2.5 flex flex-col gap-[5px]" aria-hidden="true">
        <span className="h-2 w-[62%] rounded-[2px] bg-[var(--color-primary)]/85" />
        <span className="h-[5px] w-[88%] rounded-[2px] bg-[#33445f]" />
        <span className="h-[5px] w-[70%] rounded-[2px] bg-[#33445f]" />
        <span className="h-[5px] w-[80%] rounded-[2px] bg-[#33445f]" />
        <span className="flex gap-1 mt-auto">
          <span className="h-3.5 flex-1 rounded-[3px] bg-[#232c3d]" />
          <span className="h-3.5 flex-1 rounded-[3px] bg-[#232c3d]" />
          <span className="h-3.5 flex-1 rounded-[3px] bg-[#232c3d]" />
        </span>
      </span>
    );
  }
  // pdf / html / doc — a centered type-tinted icon block (color block per mockup)
  const tint = kind === 'pdf' ? '#e5484d' : kind === 'html' ? '#e0982a' : '#5b8def';
  return (
    <span className="absolute inset-0 flex items-center justify-center" aria-hidden="true">
      <span
        className="material-symbols-outlined text-[30px] leading-none opacity-90"
        style={{ color: tint }}
      >
        {fileIcon(name)}
      </span>
    </span>
  );
}

// ── Knowledge / Pipeline / Activity — DEMOTED collapsible sections ──────────────
function RoleSection({
  group,
  collapsed,
  onToggle,
  onOpen,
}: {
  group: RoleGroup;
  collapsed: boolean;
  onToggle: () => void;
  onOpen: (p: Product) => void;
}) {
  const isPipeline = group.role === 'Pipeline';
  return (
    <section data-testid={`artifacts-group-${group.role}`}>
      <button
        onClick={onToggle}
        aria-expanded={!collapsed}
        data-testid={`artifacts-section-toggle-${group.role}`}
        className="w-full flex items-center gap-1.5 px-0.5 pb-1.5 text-left"
      >
        <span
          className="material-symbols-outlined text-[15px] leading-none text-[var(--color-text-faint)] transition-transform"
          style={{ transform: collapsed ? 'rotate(-90deg)' : 'none' }}
          aria-hidden="true"
        >
          expand_more
        </span>
        <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)] font-semibold">
          {group.label}
        </span>
        <span className="text-[9.5px] text-[var(--color-text-faint)] font-normal">
          {group.products.length}
        </span>
      </button>
      {!collapsed && (
        <div className="flex flex-col">
          {group.products.map((p) => {
            // AC8: the server-resolved displayLabel (Pipeline = task name, not run-id;
            // everything else = basename). Falls back to the client label if a row
            // predates the field (defensive; the backend always emits it now).
            const label = p.displayLabel || (isPipeline ? parentRunLabel(p.path) : baseName(p.path));
            return (
              <button
                key={p.path}
                onClick={() => onOpen(p)}
                title={p.path}
                data-testid="artifacts-row"
                className="group w-full flex items-center gap-2.5 h-9 px-2 rounded-lg hover:bg-[var(--color-hover)] transition-colors text-left"
              >
                <span
                  data-testid={`artifacts-row-icon-${p.path}`}
                  className="material-symbols-outlined shrink-0 text-[15px] leading-none"
                  style={{ color: fileIconColor(baseName(p.path)) }}
                  aria-hidden="true"
                >
                  {fileIcon(baseName(p.path))}
                </span>
                <span className="flex items-center gap-1.5 min-w-0 flex-1">
                  <span className="text-[12px] text-[var(--color-text)] truncate leading-tight">
                    {label}
                  </span>
                  {p.gitignored && (
                    <span
                      className="shrink-0 text-[8.5px] px-1 py-px rounded bg-[var(--color-git-modified,#d59a26)]/20 text-[var(--color-git-modified,#d59a26)] font-medium leading-none"
                      title="Not in git (local-only) — surfaced anyway"
                    >
                      local
                    </span>
                  )}
                </span>
                {/* absolute time, right-aligned (relative on hover) — mockup .lt */}
                <span
                  className="shrink-0 text-[9.5px] text-[var(--color-text-faint)] leading-none"
                  data-testid="artifacts-row-time"
                  title={relativeTime(p.lastTouched)}
                >
                  {absoluteTime(p.lastTouched)}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
