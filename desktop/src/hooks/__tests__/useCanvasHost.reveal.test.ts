/**
 * useCanvasHost.reveal — the resident empty-state rail's "open Canvas" action
 * (Canvas 默认常驻 rail 入口, run_a263e967).
 *
 * `reveal()` is what the FileViewerPanel resident rail (isOpen=false branch)
 * calls on click. It must:
 *  - flip isOpen true by setting manuallyOpen (AC2), via the SAME per-tab patch()
 *    chokepoint as swarm:open-canvas — so it lands on the ACTIVE tab only (AC4),
 *  - NOT change isOpen's semantics (still file || manuallyOpen), so getCanvasSnapshot
 *    keeps reporting open honestly (AC4),
 *  - be referentially STABLE across re-renders (FileViewerPanel is memo'd — an
 *    unstable reveal would re-introduce keystroke input lag).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCanvasHost } from '../useCanvasHost';

vi.mock('../../services/api', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: { resolved_path: 'resolved.md' } }) },
}));

describe('useCanvasHost — reveal() (resident rail open action)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('AC2: reveal() flips isOpen true via manuallyOpen (empty tab, no file)', () => {
    const { result } = renderHook(() =>
      useCanvasHost({ activeTabId: 'A', sessionId: 's-A', isStreaming: false }),
    );
    expect(result.current.isOpen).toBe(false);
    act(() => result.current.reveal());
    expect(result.current.isOpen).toBe(true);
    // No file was set — isOpen is true purely because manuallyOpen flipped.
    expect(result.current.file).toBeNull();
  });

  it('AC4: reveal() lands on the ACTIVE tab only — no cross-tab bleed', () => {
    let tabId = 'A';
    const { result, rerender } = renderHook(
      ({ t }) => useCanvasHost({ activeTabId: t, sessionId: 's-' + t, isStreaming: false }),
      { initialProps: { t: tabId } },
    );
    // Reveal on tab A.
    act(() => result.current.reveal());
    expect(result.current.isOpen).toBe(true);

    // Switch to tab B → B is still closed (reveal did NOT bleed).
    tabId = 'B';
    rerender({ t: tabId });
    expect(result.current.isOpen).toBe(false);

    // Switch back to A → A is still open (its slice was preserved).
    tabId = 'A';
    rerender({ t: tabId });
    expect(result.current.isOpen).toBe(true);
  });

  it('AC3-adjacent: close() after reveal() returns to closed (isOpen=false → resident rail)', () => {
    const { result } = renderHook(() =>
      useCanvasHost({ activeTabId: 'A', sessionId: 's-A', isStreaming: false }),
    );
    act(() => result.current.reveal());
    expect(result.current.isOpen).toBe(true);
    act(() => result.current.close());
    // Back to closed — ChatPage still mounts the panel → resident rail shows.
    expect(result.current.isOpen).toBe(false);
  });

  it('AC4: getCanvasSnapshot().open reflects reveal() (SENSE semantics unchanged)', () => {
    const { result } = renderHook(() =>
      useCanvasHost({ activeTabId: 'A', sessionId: 's-A', isStreaming: false }),
    );
    // Closed + no outputs → snapshot is null (truly-empty-and-closed).
    expect(result.current.getCanvasSnapshot()).toBeNull();
    act(() => result.current.reveal());
    // After reveal, open must be reported true.
    expect(result.current.getCanvasSnapshot()?.open).toBe(true);
  });

  it('reveal is referentially stable across re-renders (memo safety)', () => {
    const { result, rerender } = renderHook(
      ({ t }) => useCanvasHost({ activeTabId: t, sessionId: 's', isStreaming: false }),
      { initialProps: { t: 'A' } },
    );
    const first = result.current.reveal;
    rerender({ t: 'A' });
    expect(result.current.reveal).toBe(first);
  });
});
