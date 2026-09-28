/**
 * Tests for ArtifactsOverlay — the recent-artifacts SELECTOR (History's twin).
 *
 * Focus (the acceptance contract):
 *  - AC2: single-column, time-grouped rows (icon + name + dir + relative time), NO preview pane.
 *  - AC3: a row click dispatches swarm:open-file {detail:{path}} AND calls close().
 *  - AC4: search filters by filename; type chips filter by type; empty-data and
 *         empty-result both render a friendly empty state (no crash).
 *  - Pure helpers: groupArtifactsByTime buckets by modifiedAt; relativeTimeFromNow.
 *
 * The fetch is injected via the `fetchArtifacts` test seam (boundary mock).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, cleanup, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import type { RadarArtifact } from '../../pages/chat/components/RightSidebar/types';
import {
  ArtifactsContent,
  groupArtifactsByTime,
  relativeTimeFromNow,
  OPEN_FILE_EVENT,
} from './ArtifactsOverlay';

// A Thursday, so week-start (Monday) is 3 days back → 2-days-ago lands in `thisWeek`
// and a 10-days-ago item lands in `older`, letting us exercise all four buckets.
const NOW = new Date('2026-10-01T12:00:00'); // Thursday

function iso(daysAgo: number, h = 10): string {
  const d = new Date(NOW.getTime() - daysAgo * 24 * 60 * 60 * 1000);
  d.setHours(h, 0, 0, 0);
  return d.toISOString();
}

const FIXTURE: RadarArtifact[] = [
  { path: 'Knowledge/Reports/account-360.html', title: 'account-360', type: 'document', modifiedAt: iso(0) },
  { path: 'backend/routers/artifacts.py', title: 'artifacts', type: 'code', modifiedAt: iso(0, 9) },
  { path: 'Knowledge/Reports/weekly.xlsx', title: 'weekly', type: 'config', modifiedAt: iso(1) },
  { path: 'Attachments/banner.png', title: 'banner', type: 'image', modifiedAt: iso(1, 8) },
  { path: 'Projects/SwarmAI/TECH.md', title: 'TECH', type: 'document', modifiedAt: iso(2) },
  { path: 'Knowledge/Notes/old.md', title: 'old', type: 'document', modifiedAt: iso(10) },
];

// Render-test fixtures use REAL-now-relative timestamps (the component calls the
// real `new Date()` internally — it has no `now` injection seam), so today/yesterday
// buckets resolve regardless of the wall-clock date the suite runs on.
function isoReal(daysAgo: number, h = 10): string {
  const d = new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000);
  d.setHours(h, 0, 0, 0);
  return d.toISOString();
}
const RENDER_FIXTURE: RadarArtifact[] = [
  { path: 'Knowledge/Reports/account-360.html', title: 'account-360', type: 'document', modifiedAt: isoReal(0) },
  { path: 'backend/routers/artifacts.py', title: 'artifacts', type: 'code', modifiedAt: isoReal(0, 9) },
  { path: 'Knowledge/Reports/weekly.xlsx', title: 'weekly', type: 'config', modifiedAt: isoReal(1) },
  { path: 'Attachments/banner.png', title: 'banner', type: 'image', modifiedAt: isoReal(1, 8) },
  { path: 'Projects/SwarmAI/TECH.md', title: 'TECH', type: 'document', modifiedAt: isoReal(1, 7) },
];

function renderWithClient(node: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

afterEach(() => cleanup());

describe('groupArtifactsByTime (pure)', () => {
  it('buckets by modifiedAt into today/yesterday/thisWeek/older, non-empty groups only, in order', () => {
    const groups = groupArtifactsByTime(FIXTURE, NOW);
    const labels = groups.map((g) => g.group);
    expect(labels).toEqual(['today', 'yesterday', 'thisWeek', 'older']);
    expect(groups[0].artifacts).toHaveLength(2); // two today
    expect(groups[1].artifacts).toHaveLength(2); // two yesterday
    expect(groups[2].artifacts).toHaveLength(1); // 2d-ago (Thu → week-start Mon)
    expect(groups[3].artifacts).toHaveLength(1); // 10d-ago
  });

  it('puts an unparseable modifiedAt into older, never drops it', () => {
    const bad: RadarArtifact[] = [{ path: 'x.md', title: 'x', type: 'document', modifiedAt: 'not-a-date' }];
    const groups = groupArtifactsByTime(bad, NOW);
    expect(groups).toHaveLength(1);
    expect(groups[0].group).toBe('older');
  });

  it('returns [] for empty input', () => {
    expect(groupArtifactsByTime([], NOW)).toEqual([]);
  });
});

describe('relativeTimeFromNow (pure)', () => {
  it('formats minutes / hours / days and falls back to a date stamp', () => {
    expect(relativeTimeFromNow(new Date(NOW.getTime() - 5 * 60000).toISOString(), NOW)).toBe('5m');
    expect(relativeTimeFromNow(new Date(NOW.getTime() - 3 * 3600000).toISOString(), NOW)).toBe('3h');
    expect(relativeTimeFromNow(new Date(NOW.getTime() - 2 * 86400000).toISOString(), NOW)).toBe('2d');
    expect(relativeTimeFromNow('not-a-date', NOW)).toBe('');
  });
});

describe('ArtifactsContent', () => {
  let fetchArtifacts: ReturnType<typeof vi.fn>;
  let closeSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchArtifacts = vi.fn().mockResolvedValue(RENDER_FIXTURE);
    closeSpy = vi.fn();
  });

  it('AC2: renders time-grouped rows and has NO preview pane', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
    await waitFor(() => expect(screen.getAllByTestId('artifacts-row').length).toBeGreaterThan(0));
    // Group headers present
    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(screen.getByText('Yesterday')).toBeInTheDocument();
    // No preview pane / diff affordance (selector only)
    expect(screen.queryByTestId('artifacts-preview')).toBeNull();
    expect(screen.queryByText(/show diff/i)).toBeNull();
    // Row shows filename + parent dir
    expect(screen.getByText('account-360.html')).toBeInTheDocument();
    expect(screen.getAllByText('Knowledge/Reports').length).toBeGreaterThan(0);
  });

  it('AC3: clicking a row dispatches swarm:open-file with the path AND calls close()', async () => {
    const onOpen = vi.fn();
    document.addEventListener(OPEN_FILE_EVENT, onOpen as EventListener);
    try {
      renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
      await waitFor(() => expect(screen.getAllByTestId('artifacts-row').length).toBeGreaterThan(0));
      fireEvent.click(screen.getByText('account-360.html'));
      expect(onOpen).toHaveBeenCalledTimes(1);
      const ev = onOpen.mock.calls[0][0] as CustomEvent;
      expect(ev.detail).toEqual({ path: 'Knowledge/Reports/account-360.html' });
      expect(closeSpy).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener(OPEN_FILE_EVENT, onOpen as EventListener);
    }
  });

  it('AC4: type chip filters by type', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
    await waitFor(() => expect(screen.getAllByTestId('artifacts-row').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByTestId('artifacts-chip-code'));
    await waitFor(() => {
      const rows = screen.getAllByTestId('artifacts-row');
      expect(rows).toHaveLength(1); // only artifacts.py is code
    });
    expect(screen.getByText('artifacts.py')).toBeInTheDocument();
    expect(screen.queryByText('account-360.html')).toBeNull();
  });

  it("AC4: an 'other'-typed artifact is reachable under All but hidden under a specific chip (never silently lost)", async () => {
    const withOther: RadarArtifact[] = [
      ...RENDER_FIXTURE,
      { path: 'Knowledge/Reports/sheet.xlsx', title: 'sheet', type: 'other', modifiedAt: isoReal(0, 6) },
    ];
    fetchArtifacts.mockResolvedValue(withOther);
    renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
    // Under All: the 'other' file is visible.
    await waitFor(() => expect(screen.getByText('sheet.xlsx')).toBeInTheDocument());
    // Under a specific chip (Code): the 'other' file is hidden (but nothing crashes).
    fireEvent.click(screen.getByTestId('artifacts-chip-code'));
    await waitFor(() => expect(screen.queryByText('sheet.xlsx')).toBeNull());
    // Back to All: it returns (not permanently lost).
    fireEvent.click(screen.getByTestId('artifacts-chip-all'));
    await waitFor(() => expect(screen.getByText('sheet.xlsx')).toBeInTheDocument());
  });

  it('AC4: search filters by filename (debounced)', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
    await waitFor(() => expect(screen.getAllByTestId('artifacts-row').length).toBeGreaterThan(0));
    fireEvent.change(screen.getByTestId('artifacts-search'), { target: { value: 'TECH' } });
    await waitFor(() => {
      const rows = screen.getAllByTestId('artifacts-row');
      expect(rows).toHaveLength(1);
    });
    expect(screen.getByText('TECH.md')).toBeInTheDocument();
  });

  it('AC4: empty data renders the friendly empty state (no crash)', async () => {
    fetchArtifacts.mockResolvedValue([]);
    renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-empty')).toBeInTheDocument());
    expect(screen.getByText(/No artifacts in the last 30 days/i)).toBeInTheDocument();
  });

  it('AC4: search with no match renders the no-match empty state', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchArtifacts={fetchArtifacts} />);
    await waitFor(() => expect(screen.getAllByTestId('artifacts-row').length).toBeGreaterThan(0));
    fireEvent.change(screen.getByTestId('artifacts-search'), { target: { value: 'zzzznomatch' } });
    await waitFor(() => expect(screen.getByTestId('artifacts-empty')).toBeInTheDocument());
    expect(screen.getByText(/No artifacts match your search/i)).toBeInTheDocument();
  });
});
