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
  OPEN_FILE_EVENT,
} from './ArtifactsOverlay';

function prod(path: string, role: Product['role'], extra: Partial<Product> = {}): Product {
  return {
    path,
    role,
    kind: 'content',
    gitignored: false,
    firstProduced: '2026-09-30T00:00:00+00:00',
    lastTouched: '2026-09-30T00:00:00+00:00',
    ...extra,
  };
}

const FIXTURE: Product[] = [
  prod('Projects/AIDLC/assets/deck.html', 'Deliverables', { gitignored: true, lastTouched: '2026-09-30T10:00:00+00:00' }),
  prod('Knowledge/Reports/weekly.html', 'Deliverables', { lastTouched: '2026-09-30T09:00:00+00:00' }),
  prod('Projects/SwarmAI/2-understanding/TECH.md', 'Knowledge', { kind: 'knowledge' }),
  prod('Projects/SwarmAI/.artifacts/runs/run_2274b401/REPORT.md', 'Pipeline', { kind: 'knowledge' }),
  prod('Projects/SwarmAI/.artifacts/runs/run_91cddb8f/REPORT.md', 'Pipeline', { kind: 'knowledge' }),
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
    expect(screen.getByText('deck.html')).toBeInTheDocument();
    expect(screen.getByText('weekly.html')).toBeInTheDocument();
    // Demoted sections present
    expect(screen.getByTestId('artifacts-group-Knowledge')).toBeInTheDocument();
    expect(screen.getByTestId('artifacts-group-Pipeline')).toBeInTheDocument();
    // No preview pane / diff (selector only)
    expect(screen.queryByTestId('artifacts-preview')).toBeNull();
    expect(screen.queryByText(/show diff/i)).toBeNull();
  });

  it('AC2: a gitignored deck surfaces with a `local` badge (the blind-spot fix)', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('deck.html')).toBeInTheDocument());
    expect(screen.getByTestId('artifacts-gitignored-badge')).toBeInTheDocument();
  });

  it('AC2: Pipeline + Activity are collapsed by default; Knowledge is expanded', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-group-Pipeline')).toBeInTheDocument());
    // Pipeline collapsed → its REPORT rows are NOT rendered until toggled
    expect(screen.queryByText('run_2274b401')).toBeNull();
    // Knowledge expanded → its row IS rendered
    expect(screen.getByText('TECH.md')).toBeInTheDocument();
    // Expand Pipeline → REPORT rows appear, labeled by run dir (same-name fix)
    fireEvent.click(screen.getByTestId('artifacts-section-toggle-Pipeline'));
    await waitFor(() => expect(screen.getByText('run_2274b401')).toBeInTheDocument());
    expect(screen.getByText('run_91cddb8f')).toBeInTheDocument();
  });

  it('AC2: clicking a deliverable card dispatches swarm:open-file with the path AND calls close()', async () => {
    const onOpen = vi.fn();
    document.addEventListener(OPEN_FILE_EVENT, onOpen as EventListener);
    try {
      renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
      await waitFor(() => expect(screen.getByText('deck.html')).toBeInTheDocument());
      fireEvent.click(screen.getByText('deck.html'));
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
    await waitFor(() => expect(screen.getByText('deck.html')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('artifacts-search'), { target: { value: 'weekly' } });
    await waitFor(() => expect(screen.queryByText('deck.html')).toBeNull());
    expect(screen.getByText('weekly.html')).toBeInTheDocument();
  });

  it('AC6: empty data renders the friendly empty state (no crash)', async () => {
    fetchProducts.mockResolvedValue([]);
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByTestId('artifacts-empty')).toBeInTheDocument());
    expect(screen.getByText(/No products yet/i)).toBeInTheDocument();
  });

  it('AC6: search with no match renders the no-match empty state', async () => {
    renderWithClient(<ArtifactsContent close={closeSpy} fetchProducts={fetchProducts} />);
    await waitFor(() => expect(screen.getByText('deck.html')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('artifacts-search'), { target: { value: 'zzzznomatch' } });
    await waitFor(() => expect(screen.getByTestId('artifacts-empty')).toBeInTheDocument());
    expect(screen.getByText(/No products match your search/i)).toBeInTheDocument();
  });
});
