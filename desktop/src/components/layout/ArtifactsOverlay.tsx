/**
 * ArtifactsOverlay — the left-nav "Artifacts" surface: a recent-artifacts SELECTOR.
 *
 * The twin of History: History browses past CONVERSATIONS, Artifacts browses recent
 * FILES (git-derived recent user artifacts from /artifacts/recent). Because a file's
 * sole viewer is the Canvas, this surface is a pure SELECTOR — it has NO right-side
 * preview pane and NO diff button (both deliberately rejected: Canvas is the one place
 * a file is viewed/diffed). Clicking a row dispatches `swarm:open-file` (→ opens in the
 * CURRENT tab's Canvas, exactly like LibraryOverlay/BrainHub) and then closes the overlay.
 *
 * Layout (single column): a debounced filename search box + type chips
 * (all/document/code/data/image) + a time-grouped list (today/yesterday/this-week/older).
 * Each row = a material-symbols file icon (fileIcon) + filename + parent dir + a relative
 * "time ago". No A/M git-status badge in v1 — RadarArtifact carries no new/upd field
 * (that lives in a separate useChangeStatus hook, deferred to keep this a thin selector).
 *
 * Data comes from radarService.fetchRecentArtifacts; the backend resolves the single
 * workspace from DB config and ignores the workspace_id param, so a placeholder id
 * satisfies the required query param. Backend-primary — invents no data (R30).
 *
 * @exports ArtifactsContent
 * @exports groupArtifactsByTime — pure time-bucketer (unit-tested)
 * @exports relativeTimeFromNow — pure relative-time formatter (unit-tested)
 * @exports OPEN_FILE_EVENT — the swarm:open-file event name (shared with the row-click contract)
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { radarService } from '../../services/radar';
import type { RadarArtifact } from '../../pages/chat/components/RightSidebar/types';
import { fileIcon } from '../../utils/fileUtils';

/** The window CustomEvent that opens a file in the current tab's Canvas.
 *  Same name LibraryOverlay/BrainHub dispatch — do NOT rename (proprioception contract). */
export const OPEN_FILE_EVENT = 'swarm:open-file';

/** Debounce for the filename filter (mirrors HistoryOverlay's search debounce feel). */
const SEARCH_DEBOUNCE_MS = 200;

/** The backend ignores workspace_id (resolves the single workspace from DB config);
 *  a non-empty placeholder satisfies the required query param. */
const WS_PLACEHOLDER = 'default';

const MS_PER_DAY = 24 * 60 * 60 * 1000;

// ── Time bucketing ────────────────────────────────────────────────────────────
export type ArtifactTimeGroup = 'today' | 'yesterday' | 'thisWeek' | 'older';

export interface GroupedArtifacts {
  group: ArtifactTimeGroup;
  label: string;
  artifacts: RadarArtifact[];
}

const GROUP_LABEL: Record<ArtifactTimeGroup, string> = {
  today: 'Today',
  yesterday: 'Yesterday',
  thisWeek: 'This Week',
  older: 'Older',
};

/**
 * Bucket artifacts by their modifiedAt into today / yesterday / this-week / older.
 * Pure (except reading `now` — injectable for tests). Preserves input order within a
 * group (the service already returns newest-first). Returns only non-empty groups,
 * in fixed order. An unparseable/absent modifiedAt falls into `older` (never dropped).
 */
export function groupArtifactsByTime(
  artifacts: RadarArtifact[],
  now: Date = new Date(),
): GroupedArtifacts[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - MS_PER_DAY);
  const dayOfWeek = now.getDay();
  const mondayOffset = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  const weekStart = new Date(today.getTime() - mondayOffset * MS_PER_DAY);

  const buckets: Record<ArtifactTimeGroup, RadarArtifact[]> = {
    today: [],
    yesterday: [],
    thisWeek: [],
    older: [],
  };

  for (const a of artifacts) {
    const ts = Date.parse(a.modifiedAt);
    if (Number.isNaN(ts)) {
      buckets.older.push(a);
      continue;
    }
    const d = new Date(ts);
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if (day.getTime() === today.getTime()) buckets.today.push(a);
    else if (day.getTime() === yesterday.getTime()) buckets.yesterday.push(a);
    else if (day >= weekStart) buckets.thisWeek.push(a);
    else buckets.older.push(a);
  }

  const order: ArtifactTimeGroup[] = ['today', 'yesterday', 'thisWeek', 'older'];
  return order
    .filter((g) => buckets[g].length > 0)
    .map((g) => ({ group: g, label: GROUP_LABEL[g], artifacts: buckets[g] }));
}

/**
 * Relative "time ago" string for the row's right edge — a scannable reference point.
 * <1min → "now"; <1h → "Nm"; <24h → "Nh"; <7d → "Nd"; else a local YYYY-MM-DD stamp.
 * Pure (now injectable). An unparseable timestamp → "" (row still renders).
 */
export function relativeTimeFromNow(iso: string, now: Date = new Date()): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diffMs = now.getTime() - ts;
  if (diffMs < 0) return 'now';
  const min = Math.floor(diffMs / 60000);
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

// ── Type chips ──────────────────────────────────────────────────────────────
type ChipKey = 'all' | 'document' | 'code' | 'data' | 'image';

const CHIPS: { key: ChipKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'document', label: 'Docs' },
  { key: 'code', label: 'Code' },
  { key: 'data', label: 'Data' },
  { key: 'image', label: 'Images' },
];

/**
 * Map a chip to the RadarArtifact.type values it includes. The backend enum is exactly
 * {code, document, config, image, other} (backend `EXTENSION_TYPE_MAP` + an `other`
 * fallback — verified against artifacts.py). Two deliberate mappings:
 *  - Data folds `config` (json/yaml/toml/…) into the "Data" chip.
 *  - `other` (anything unclassified — e.g. .xlsx/.csv spreadsheets, which the backend
 *    map does NOT cover) is shown under the All chip but HIDDEN under every specific
 *    chip (it belongs to no type category). It is therefore always reachable (All is
 *    the default view) but is not surfaced by a narrowing chip — by design.
 * The switch is exhaustive with an explicit `default: false`, so a future enum value
 * that is not handled hides under specific chips (never crashes) and All still shows it.
 */
function chipMatches(chip: ChipKey, t: RadarArtifact['type']): boolean {
  switch (chip) {
    case 'all':
      return true;
    case 'document':
      return t === 'document';
    case 'code':
      return t === 'code';
    case 'data':
      return t === 'config';
    case 'image':
      return t === 'image';
    default:
      return false;
  }
}

/** Parent directory of a workspace-relative path ("" for a bare filename). */
function parentDir(path: string): string {
  const i = path.lastIndexOf('/');
  return i > 0 ? path.slice(0, i) : '';
}
function baseName(path: string): string {
  const i = path.lastIndexOf('/');
  return i >= 0 ? path.slice(i + 1) : path;
}

/** Open a file in the current tab's Canvas (same contract as LibraryOverlay). */
export function dispatchOpenFile(path: string): void {
  document.dispatchEvent(new CustomEvent(OPEN_FILE_EVENT, { detail: { path } }));
}

export interface ArtifactsContentProps {
  /** Host-owned close — called after a row opens a file (return to chat/Canvas). */
  close: () => void;
  /** Test seam: override the fetch (defaults to radarService.fetchRecentArtifacts). */
  fetchArtifacts?: (wsId: string, limit?: number) => Promise<RadarArtifact[]>;
}

/**
 * The Artifacts selector body (the host wraps it in scrim + panel + header chrome).
 */
export function ArtifactsContent({ close, fetchArtifacts }: ArtifactsContentProps) {
  const fetcher = fetchArtifacts ?? radarService.fetchRecentArtifacts;

  const { data, isLoading, isError } = useQuery({
    queryKey: ['recent-artifacts'],
    queryFn: () => fetcher(WS_PLACEHOLDER, 50),
    staleTime: 30_000,
  });

  const [searchRaw, setSearchRaw] = useState('');
  const [search, setSearch] = useState('');
  const [chip, setChip] = useState<ChipKey>('all');

  // Debounce the filename filter.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchRaw.trim().toLowerCase()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchRaw]);

  const groups = useMemo(() => {
    const all = data ?? [];
    const filtered = all.filter((a) => {
      if (!chipMatches(chip, a.type)) return false;
      if (search && !baseName(a.path).toLowerCase().includes(search)) return false;
      return true;
    });
    return groupArtifactsByTime(filtered);
  }, [data, search, chip]);

  const openRow = (a: RadarArtifact) => {
    dispatchOpenFile(a.path);
    close();
  };

  const totalShown = groups.reduce((n, g) => n + g.artifacts.length, 0);

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="artifacts-overlay">
      {/* Search + chips */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <input
          type="text"
          value={searchRaw}
          onChange={(e) => setSearchRaw(e.target.value)}
          placeholder="Search filename…"
          data-testid="artifacts-search"
          className="w-full px-3 py-2 rounded-lg bg-[var(--color-input-bg,var(--color-bg-secondary))] border border-[var(--color-border)] text-[12.5px] text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] outline-none focus:border-[var(--color-primary)]"
        />
        <div className="flex gap-1.5 mt-2 flex-wrap" data-testid="artifacts-chips">
          {CHIPS.map((c) => (
            <button
              key={c.key}
              onClick={() => setChip(c.key)}
              data-testid={`artifacts-chip-${c.key}`}
              aria-pressed={chip === c.key}
              className={`text-[10.5px] px-2.5 py-1 rounded-full border transition-colors ${
                chip === c.key
                  ? 'bg-[var(--color-active,var(--color-hover))] text-[var(--color-text)] border-transparent'
                  : 'text-[var(--color-text-muted)] border-[var(--color-border)] hover:text-[var(--color-text)]'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-3" data-testid="artifacts-list">
        {isLoading ? (
          <div className="flex flex-col gap-1 px-2 py-3" data-testid="artifacts-loading">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-8 rounded-md bg-[var(--color-hover)] animate-pulse" />
            ))}
          </div>
        ) : isError ? (
          <div
            className="flex flex-col items-center justify-center gap-2 px-3 py-10 text-center"
            data-testid="artifacts-error"
          >
            <span className="text-[22px]" aria-hidden="true">🐝</span>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              Couldn't load recent artifacts. Try again in a moment.
            </p>
          </div>
        ) : totalShown === 0 ? (
          <div
            className="flex flex-col items-center justify-center gap-2 px-3 py-10 text-center"
            data-testid="artifacts-empty"
          >
            <span className="text-[22px]" aria-hidden="true">🐝</span>
            <p className="text-[11px] text-[var(--color-text-muted)] max-w-[240px]">
              {(data ?? []).length === 0
                ? 'No artifacts in the last 30 days. Files you create or edit will show up here.'
                : 'No artifacts match your search.'}
            </p>
          </div>
        ) : (
          groups.map((g) => (
            <div key={g.group}>
              <div className="text-[9.5px] uppercase tracking-wide text-[var(--color-text-faint)] font-semibold px-2 pt-3 pb-1">
                {g.label}
              </div>
              {g.artifacts.map((a) => (
                <button
                  key={a.path}
                  onClick={() => openRow(a)}
                  title={a.path}
                  data-testid="artifacts-row"
                  className="group w-full flex items-center gap-2.5 h-9 px-2.5 rounded-lg hover:bg-[var(--color-hover)] transition-colors text-left"
                >
                  <span
                    className="material-symbols-outlined shrink-0 text-[16px] leading-none text-[var(--color-text-muted)]"
                    aria-hidden="true"
                  >
                    {fileIcon(baseName(a.path))}
                  </span>
                  <span className="flex flex-col min-w-0 flex-1">
                    <span className="text-[12.5px] text-[var(--color-text)] truncate">
                      {baseName(a.path)}
                    </span>
                    {parentDir(a.path) && (
                      <span className="text-[9.5px] text-[var(--color-text-faint)] truncate">
                        {parentDir(a.path)}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 text-[9.5px] text-[var(--color-text-faint)]">
                    {relativeTimeFromNow(a.modifiedAt)}
                  </span>
                </button>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
