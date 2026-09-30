/**
 * Tests for ArtifactsOverlay — the ROLE-grouped product gallery (Artifacts B′ Run 2).
 *
 * Focus (the acceptance contract):
 *  - AC2: role grouping — Deliverables as a dominant card grid; Knowledge/Pipeline/
 *         Activity as collapsible sections (Pipeline/Activity collapsed by default).
 *  - AC2: a gitignored deck (role=Deliverables, gitignored=true) surfaces with a `local` badge.
 *  - AC2: a row/card click dispatches swarm:open-file {detail:{path}} AND calls close().
 *  - AC2: Pipeline REPORT.md rows are labeled by their parent run dir (same-name fix).
 *  - AC6: search filters by filename; empty-data + no-match render a friendly empty state.
 *  - Pure helpers: groupByRole buckets + orders; parentRunLabel derives the run label.
 *
 * The fetch is injected via the `fetchProducts` test seam (boundary mock).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import type { Product } from '../../services/radar';
import {
  ArtifactsContent,
  groupByRole,
  parentRunLabel,
  relativeTime,
  absoluteTime,
  elideDir,
  friendlyTitle,
  thumbKind,
  OPEN_FILE_EVENT,
} from './ArtifactsOverlay';

function prod(path: string, role: Product['role'], extra: Partial<Product> = {}): Product {
  const base = path.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? path;
  return {
    path,
    role,
    kind: 'content',
    gitignored: false,
    firstProduced: '2026-09-30T00:00:00+00:00',
    lastTouched: '2026-09-30T00:00:00+00:00',
    displayLabel: base,
    ...extra,
  };
}

const FIXTURE: Product[] = [
  prod('Projects/AIDLC/assets/deck.html', 'Deliverables', { gitignored: true, lastTouched: '2026-09-30T10:00:00+00:00' }),
  prod('Knowledge/Reports/weekly.html', 'Deliverables', { lastTouched: '2026-09-30T09:00:00+00:00' }),
  prod('Projects/SwarmAI/2-understanding/TECH.md', 'Knowledge', { kind: 'knowledge' }),
  prod('Projects/SwarmAI/.artifacts/runs/run_2274b401/REPORT.md', 'Pipeline', { kind: 'knowledge', displayLabel: 'Artifacts data root-fix' }),
  prod('Projects/SwarmAI/.artifacts/runs/run_91cddb8f/REPORT.md', 'Pipeline', { kind: 'knowledge', displayLabel: 'Shared product registry backend' }),
  prod('Knowledge/DailyActivity/2026-09-30.md', 'Activity'),
];

function renderWithClient(node: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

afterEach(() => cleanup());

describe('groupByRole (pure)', () => {
  it('buckets by role in fixed order, non-empty only, newest-first within a group', () => {
    const groups = groupByRole(FIXTURE);
    expect(groups.map((g) => g.role)).toEqual(['Deliverables', 'Knowledge', 'Pipeline', 'Activity']);
    // Deliverables newest-first: deck (10:00) before weekly (09:00)
    expect(groups[0].products[0].path).toContain('deck.html');
    expect(groups[0].products).toHaveLength(2);
    expect(groups[2].products).toHaveLength(2); // two REPORT.md
  });

  it('folds a stray Other into Knowledge, never drops it', () => {
    const groups = groupByRole([prod('x.weird', 'Other' as Product['role'])]);
    expect(groups).toHaveLength(1);
    expect(groups[0].role).toBe('Knowledge');
  });

  it('returns [] for empty input', () => {
    expect(groupByRole([])).toEqual([]);
  });
});

describe('parentRunLabel (pure)', () => {
  it('labels a REPORT.md by its parent run dir', () => {
    expect(parentRunLabel('Projects/SwarmAI/.artifacts/runs/run_2274b401/REPORT.md')).toBe('run_2274b401');
  });
  it('falls back to basename when no run segment', () => {
    expect(parentRunLabel('Knowledge/Reports/weekly.html')).toBe('weekly.html');
  });
});

describe('ArtifactsContent', () => {
  let fetchProducts: ReturnType<typeof vi.fn>;
  let closeSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchProducts = vi.fn().mockResolvedValue(FIXTURE);
    closeSpy = vi.fn();
  });

  it('AC2: renders Deliverables as a card grid + demoted collapsible sections, no preview pane', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getAllByTestId('artifacts-card').length).toBeGreaterThan(0));
    // Deliverables dominant (cards)
    expect(screen.getByTestId('artifacts-group-Deliverables')).toBeInTheDocument();
    expect(screen.getByText('Deck')).toBeInTheDocument();
    expect(screen.getByText('Weekly')).toBeInTheDocument();
    // Demoted sections present
    expect(screen.getByTestId('artifacts-group-Knowledge')).toBeInTheDocument();
    expect(screen.getByTestId('artifacts-group-Pipeline')).toBeInTheDocument();
    // No preview pane / diff (selector only)
    expect(screen.queryByTestId('artifacts-preview')).toBeNull();
    expect(screen.queryByText(/show diff/i)).toBeNull();
  });

  it('AC2: a gitignored deck surfaces with a `local` badge (the blind-spot fix)', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
    expect(screen.getByTestId('artifacts-gitignored-badge')).toBeInTheDocument();
  });

  it('AC2: Pipeline + Activity are collapsed by default; Knowledge is expanded', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-group-Pipeline')).toBeInTheDocument());
    // Pipeline collapsed → its REPORT rows are NOT rendered until toggled
    expect(screen.queryByText('Artifacts data root-fix')).toBeNull();
    // Knowledge expanded → its row IS rendered
    expect(screen.getByText('TECH.md')).toBeInTheDocument();
    // Expand Pipeline → REPORT rows appear, labeled by run dir (same-name fix)
    fireEvent.click(screen.getByTestId('artifacts-section-toggle-Pipeline'));
    await waitFor(() => expect(screen.getByText('Artifacts data root-fix')).toBeInTheDocument());
    expect(screen.getByText('Shared product registry backend')).toBeInTheDocument();
  });

  it('AC2: clicking a deliverable card dispatches swarm:open-file with the path AND calls close()', async () => {
    const onOpen = vi.fn();
    document.addEventListener(OPEN_FILE_EVENT, onOpen as EventListener);
    try {
      renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
      await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Deck'));
      expect(onOpen).toHaveBeenCalledTimes(1);
      const ev = onOpen.mock.calls[0][0] as CustomEvent;
      expect(ev.detail).toEqual({ path: 'Projects/AIDLC/assets/deck.html' });
      expect(closeSpy).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener(OPEN_FILE_EVENT, onOpen as EventListener);
    }
  });

  it('AC6: search filters by filename (debounced)', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('artifacts-search'), { target: { value: 'weekly' } });
    await waitFor(() => expect(screen.queryByText('Deck')).toBeNull());
    expect(screen.getByText('Weekly')).toBeInTheDocument();
  });

  it('AC6: empty data renders the friendly empty state (no crash)', async () => {
    fetchProducts.mockResolvedValue([]);
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-empty')).toBeInTheDocument());
    expect(screen.getByText(/No products yet/i)).toBeInTheDocument();
  });

  it('AC6: search with no match renders the no-match empty state', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('artifacts-search'), { target: { value: 'zzzznomatch' } });
    await waitFor(() => expect(screen.getByTestId('artifacts-empty')).toBeInTheDocument());
    expect(screen.getByText(/No products match your search/i)).toBeInTheDocument();
  });
});

// ── run_7220ff2a: mockup alignment — role-filter chips + relative timestamps ──
describe('relativeTime (pure)', () => {
  const NOW = new Date('2026-09-30T12:00:00Z').getTime();
  it('buckets now / minutes / hours / days, else a date', () => {
    expect(relativeTime(new Date(NOW - 20 * 1000).toISOString(), NOW)).toBe('now');
    expect(relativeTime(new Date(NOW - 5 * 60000).toISOString(), NOW)).toBe('5m');
    expect(relativeTime(new Date(NOW - 3 * 3600000).toISOString(), NOW)).toBe('3h');
    expect(relativeTime(new Date(NOW - 2 * 86400000).toISOString(), NOW)).toBe('2d');
    // >7d → a YYYY-MM-DD date stamp (not "60d")
    expect(relativeTime(new Date(NOW - 60 * 86400000).toISOString(), NOW)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
  it('unparseable → empty string (never crashes a row)', () => {
    expect(relativeTime('not-a-date', NOW)).toBe('');
  });
});

describe('ArtifactsContent — role chips + timestamps', () => {
  let fetchProducts: ReturnType<typeof vi.fn>;
  let closeSpy: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchProducts = vi.fn().mockResolvedValue(FIXTURE);
    closeSpy = vi.fn();
  });

  it('AC1: renders a role-filter chip row (4 canonical roles)', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-rolefilter')).toBeInTheDocument());
    for (const role of ['Deliverables', 'Knowledge', 'Pipeline', 'Activity']) {
      expect(screen.getByTestId(`artifacts-chip-${role}`)).toBeInTheDocument();
    }
  });

  it('AC1: clicking a chip filters to that role; clicking it again clears', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
    // Filter to Knowledge → Deliverables cards gone, Knowledge shown
    fireEvent.click(screen.getByTestId('artifacts-chip-Knowledge'));
    await waitFor(() => expect(screen.queryByText('Deck')).toBeNull());
    expect(screen.getByText('TECH.md')).toBeInTheDocument();
    // Click active chip again → all roles back
    fireEvent.click(screen.getByTestId('artifacts-chip-Knowledge'));
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
  });

  it('AC2: a deliverable card renders a relative timestamp', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
    // The card for deck.html must contain a time element (data-testid).
    const times = screen.getAllByTestId('artifacts-card-time');
    expect(times.length).toBeGreaterThan(0);
    // Each has non-empty text (a relative time or date).
    expect(times[0].textContent && times[0].textContent.length).toBeGreaterThan(0);
  });

  it('AC1: filtering to a collapsed-by-default role (Pipeline) auto-expands it (no dead end)', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('Deck')).toBeInTheDocument());
    // Pipeline is collapsed by default → its run rows are NOT visible initially.
    expect(screen.queryByText('Artifacts data root-fix')).toBeNull();
    // Click the Pipeline chip → filter to Pipeline AND force-expand it → rows visible.
    fireEvent.click(screen.getByTestId('artifacts-chip-Pipeline'));
    await waitFor(() => expect(screen.getByText('Artifacts data root-fix')).toBeInTheDocument());
    expect(screen.getByText('Shared product registry backend')).toBeInTheDocument();
  });
});

describe('absoluteTime (pure) — AC6', () => {
  it('renders YYYY-MM-DD HH:MM in local time', () => {
    // A fixed instant; assert the shape, not a tz-specific value.
    const out = absoluteTime('2026-06-04T01:13:16+00:00');
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });
  it('unparseable → empty string (never crashes a row)', () => {
    expect(absoluteTime('not-a-date')).toBe('');
    expect(absoluteTime('')).toBe('');
  });
});

describe('elideDir (pure) — AC7', () => {
  it('shows the last two dirs, eliding deeper prefixes with …/', () => {
    expect(elideDir('Projects/SwarmAI/.artifacts/runs/run_x/REPORT.md'))
      .toBe('…/runs/run_x');
  });
  it('two-level path shows both, no ellipsis', () => {
    expect(elideDir('Knowledge/Library/deck.html')).toBe('Knowledge/Library');
  });
  it('one-level path shows the single dir', () => {
    expect(elideDir('Knowledge/deck.html')).toBe('Knowledge');
  });
  it('bare filename → empty', () => {
    expect(elideDir('deck.html')).toBe('');
  });
});

describe('Pipeline rows use server displayLabel — AC8', () => {
  it('renders the task-name displayLabel, not the raw run-id', async () => {
    const fetchProducts = vi.fn().mockResolvedValue([
      prod('Projects/SwarmAI/.artifacts/runs/run_abc12345/REPORT.md', 'Pipeline', {
        kind: 'knowledge',
        displayLabel: 'Fix the artifacts overlay timestamps',
      }),
    ]);
    renderWithClient(<ArtifactsContent close={() => {}} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-group-Pipeline')).toBeInTheDocument());
    // Pipeline is collapsed by default — expand it.
    fireEvent.click(screen.getByTestId('artifacts-section-toggle-Pipeline'));
    await waitFor(() =>
      expect(screen.getByText('Fix the artifacts overlay timestamps')).toBeInTheDocument(),
    );
    expect(screen.queryByText('run_abc12345')).not.toBeInTheDocument();
  });
});

describe('friendlyTitle (pure) — AC4', () => {
  it('strips a leading YYYY-MM-DD date + extension, de-slugs, title-cases', () => {
    expect(friendlyTitle('2026-08-30-ai-native-ee-oe-deck.html')).toBe('Ai Native Ee Oe Deck');
  });
  it('no date prefix: just de-slug + title-case', () => {
    expect(friendlyTitle('SecDLC-flywheel.png')).toBe('SecDLC Flywheel'); // preserves acronym caps
  });
  it('strips ONLY the last extension (dots in the middle survive)', () => {
    expect(friendlyTitle('v1.2-deck.html')).toBe('V1.2 Deck');
  });
  it('all-date name → falls back to the basename, never empty (Gate-1 F2)', () => {
    expect(friendlyTitle('2026-09-30.md')).toBe('2026-09-30.md');
  });
  it('degenerate empty → basename fallback', () => {
    expect(friendlyTitle('')).toBe('');
  });
});

describe('thumbKind (pure) — AC2', () => {
  it('classifies deck / image / pdf / html / report / doc', () => {
    expect(thumbKind('Projects/AIDLC/assets/x.pptx').kind).toBe('deck');
    expect(thumbKind('Knowledge/Pollinate/y/index.html').kind).toBe('deck'); // Pollinate = content package deck (deliberate)
    expect(thumbKind('Knowledge/Designs/pic.png').kind).toBe('image');
    expect(thumbKind('Knowledge/Library/report.pdf').kind).toBe('pdf');
    expect(thumbKind('Knowledge/Library/page.html').kind).toBe('html');
    expect(thumbKind('Knowledge/Reports/weekly.md').kind).toBe('report');
    expect(thumbKind('Knowledge/Notes/whatever.md').kind).toBe('doc'); // default
  });
  it('every kind carries a non-empty badge label', () => {
    for (const p of ['a.pptx', 'b.png', 'c.pdf', 'd.html', 'Reports/e.md', 'f.txt']) {
      expect(thumbKind(p).badge.length).toBeGreaterThan(0);
    }
  });
});

describe('Deliverables tile — AC1/AC2/AC3 render', () => {
  it('renders a thumbnail zone + type badge + friendly title (not the raw filename)', async () => {
    const fetchProducts = vi.fn().mockResolvedValue([
      prod('Knowledge/Library/2026-08-30-ai-native-ee-oe-deck.html', 'Deliverables'),
    ]);
    renderWithClient(<ArtifactsContent close={() => {}} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-card')).toBeInTheDocument());
    expect(screen.getByTestId('artifacts-card-thumb')).toBeInTheDocument();
    // friendly title shown, raw filename NOT the visible label
    expect(screen.getByText('Ai Native Ee Oe Deck')).toBeInTheDocument();
    expect(screen.queryByText('2026-08-30-ai-native-ee-oe-deck.html')).toBeNull();
    // type badge (HTML for a .html)
    expect(screen.getByTestId('artifacts-card-badge')).toHaveTextContent(/DECK/i); // name has -deck
  });
});

describe('Gate-2 adversarial fixes', () => {
  it('thumbKind: report matches only a whole token, not a substring (preport.md → doc)', () => {
    expect(thumbKind('Knowledge/Notes/preport.md').kind).toBe('doc');
    expect(thumbKind('Knowledge/Notes/reporter-bio.md').kind).toBe('doc');
    expect(thumbKind('Knowledge/Reports/x.md').kind).toBe('report'); // Reports/ dir
    expect(thumbKind('Knowledge/Notes/weekly-report.md').kind).toBe('report'); // token
  });
  it('friendlyTitle: no trailing dot from a double-extension (report..md → Report)', () => {
    expect(friendlyTitle('report..md')).toBe('Report');
  });
});
