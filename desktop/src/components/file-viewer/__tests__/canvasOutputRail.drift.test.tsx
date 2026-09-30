/**
 * CanvasOutputRail drift signal (Artifact-Lifecycle P0, ②).
 *
 * A row whose backing file changed / went missing since it was first seen shows a
 * subtle inline drift badge (data-testid="canvas-output-drift"), fed by a debounced
 * GET /artifacts/drift check that runs OFF the render hot path. The badge is a
 * LIGHTWEIGHT signal — it must NEVER gate opening the row.
 *
 * These tests lock the LOGIC (badge renders iff drift, open still fires on a failed
 * drift check). The visual/geometry is verified on the real machine (jsdom has no CSS).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import type { ReferencedFile } from '../../../hooks/useReferencedFiles';

// Mock the drift service — we own the verdict per test.
const fetchDrift = vi.fn();
vi.mock('../../../services/radar', () => ({
  radarService: { fetchDrift: (...a: unknown[]) => fetchDrift(...a) },
}));
vi.mock('../../../hooks/useChangeStatus', () => ({ useChangeStatus: () => new Map() }));

import { CanvasOutputRail } from '../CanvasOutputRail';

const mkFile = (name: string, over: Partial<ReferencedFile> = {}): ReferencedFile => ({
  path: `src/${name}`,
  absolutePath: `/ws/src/${name}`,
  fileName: name,
  operation: 'written',
  firstSeen: Date.now() - 10_000,
  count: 1,
  baseRef: 'abc123^',
  ...over,
});

beforeEach(() => {
  vi.useFakeTimers();
  fetchDrift.mockReset();
});
afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

describe('CanvasOutputRail — drift badge (②)', () => {
  it('shows NO drift badge for a clean file', async () => {
    fetchDrift.mockResolvedValue({ dirty: false, reason: 'clean' });
    render(<CanvasOutputRail files={{ written: [mkFile('clean.ts')] }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); }); // pass the 400ms debounce
    expect(screen.queryByTestId('canvas-output-drift')).toBeNull();
  });

  it('shows a drift badge when the file changed on disk (dirty/git-changed)', async () => {
    fetchDrift.mockResolvedValue({ dirty: true, reason: 'git-changed', currentRef: 'def456' });
    render(<CanvasOutputRail files={{ written: [mkFile('changed.ts')] }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(screen.getByTestId('canvas-output-drift')).toBeTruthy();
    expect(screen.getByTestId('canvas-output-drift').getAttribute('title')).toContain('Changed');
  });

  it('shows a "gone" badge when the file is missing', async () => {
    fetchDrift.mockResolvedValue({ dirty: true, reason: 'missing' });
    render(<CanvasOutputRail files={{ written: [mkFile('gone.ts')] }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(screen.getByTestId('canvas-output-drift').textContent).toBe('gone');
  });

  it('does NOT block opening the row when the drift check REJECTS (fail-safe)', async () => {
    fetchDrift.mockRejectedValue(new Error('network down'));
    const dispatch = vi.spyOn(document, 'dispatchEvent');
    render(<CanvasOutputRail files={{ written: [mkFile('openable.ts')] }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    // No badge (rejection → treated as clean).
    expect(screen.queryByTestId('canvas-output-drift')).toBeNull();
    // The row still opens on click.
    const row = screen.getByText('openable.ts').closest('[data-testid="canvas-output-row"]')!;
    fireEvent.click(row);
    expect(dispatch).toHaveBeenCalled();
    dispatch.mockRestore();
  });

  it('does NOT drift-check a deleted row', async () => {
    fetchDrift.mockResolvedValue({ dirty: true, reason: 'missing' });
    render(<CanvasOutputRail files={{ written: [mkFile('del.ts', { deleted: true })] }} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(fetchDrift).not.toHaveBeenCalled();
    expect(screen.queryByTestId('canvas-output-drift')).toBeNull();
  });
});
