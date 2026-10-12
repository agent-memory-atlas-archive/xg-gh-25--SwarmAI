/**
 * Tests for ScopeDepthMatrix (SRS design §5.3).
 *
 * Covers AC7:
 *  - 9×6 matrix renders (9 stage rows × 6 profile columns).
 *  - Von Restorff: EXACTLY ONE profile column is "active" (dominant) — the current
 *    run's profile; every other column is muted. If the matrix lit up every column
 *    it would be the equal-weight data-dump design-judgment forbids.
 *  - The depth badge shows beside the active profile only.
 *  - DRIFT GUARD: the frontend grid's EXECUTE cells for the stable profiles mirror
 *    backend core/pipeline_profiles.PIPELINE_PROFILES — a divergence is a test fail
 *    (the frontend↔backend contract, read-side of the cross_boundary seam).
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  ScopeDepthMatrix,
  MATRIX_STAGES,
  MATRIX_PROFILES,
  SCOPE_DEPTH_GRID,
} from './ScopeDepthMatrix';

afterEach(cleanup);

describe('ScopeDepthMatrix', () => {
  it('renders a 9×6 matrix (9 stage rows, 6 profile columns)', () => {
    render(<ScopeDepthMatrix activeProfile="goal" activeDepth="standard" />);
    const matrix = screen.getByTestId('scope-depth-matrix');
    // 6 profile column headers.
    const colHeaders = within(matrix).getAllByRole('columnheader');
    // 1 corner + 6 profiles = 7 column headers.
    expect(colHeaders).toHaveLength(7);
    // 9 stage row headers.
    const rowHeaders = within(matrix).getAllByRole('rowheader');
    expect(rowHeaders).toHaveLength(9);
    expect(MATRIX_STAGES).toHaveLength(9);
    expect(MATRIX_PROFILES).toHaveLength(6);
  });

  it('Von Restorff: EXACTLY ONE column is active (the current run profile)', () => {
    render(<ScopeDepthMatrix activeProfile="goal" activeDepth="standard" />);
    const matrix = screen.getByTestId('scope-depth-matrix');
    const activeHeaders = within(matrix)
      .getAllByRole('columnheader')
      .filter((th) => th.getAttribute('data-active') === 'true');
    expect(activeHeaders).toHaveLength(1);
    expect(activeHeaders[0]).toHaveAttribute('data-profile', 'goal');
  });

  it('no column is active when the profile is unknown (no false dominance)', () => {
    render(<ScopeDepthMatrix activeProfile={null} activeDepth={null} />);
    const matrix = screen.getByTestId('scope-depth-matrix');
    const activeHeaders = within(matrix)
      .getAllByRole('columnheader')
      .filter((th) => th.getAttribute('data-active') === 'true');
    expect(activeHeaders).toHaveLength(0);
  });

  it('shows the depth badge beside the active profile only', () => {
    render(<ScopeDepthMatrix activeProfile="full" activeDepth="light" />);
    const badges = screen.getAllByTestId('sdm-depth-badge');
    expect(badges).toHaveLength(1);
    expect(badges[0].textContent).toContain('light');
  });

  it("'standard' profile alias resolves to full (backend normalize parity)", () => {
    render(<ScopeDepthMatrix activeProfile="standard" activeDepth="standard" />);
    const matrix = screen.getByTestId('scope-depth-matrix');
    const active = within(matrix)
      .getAllByRole('columnheader')
      .filter((th) => th.getAttribute('data-active') === 'true');
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveAttribute('data-profile', 'full');
  });

  it('DRIFT GUARD: EXECUTE cells mirror backend PIPELINE_PROFILES', () => {
    // Read the backend SSOT and parse its profile→stages lists.
    const src = readFileSync(
      resolve(__dirname, '../../../../backend/core/pipeline_profiles.py'),
      'utf-8',
    );
    // Extract the PIPELINE_PROFILES dict body.
    const block = src.slice(src.indexOf('PIPELINE_PROFILES'), src.indexOf('}', src.indexOf('PIPELINE_PROFILES')) + 1);
    const backend: Record<string, string[]> = {};
    for (const m of block.matchAll(/"(\w+)":\s*\[([^\]]*)\]/g)) {
      const prof = m[1];
      const stages = [...m[2].matchAll(/"(\w+)"/g)].map((s) => s[1]);
      backend[prof] = stages;
    }
    // For profiles with a 1:1 stage list (NOT goal — it replaces build/review/test
    // with goal_cycle, represented as CONDITIONAL), every backend-listed stage must
    // be EXECUTE in the frontend grid, and every non-listed concrete stage SKIP.
    const concreteStages = MATRIX_STAGES.filter((s) => s !== 'adversarial');
    for (const prof of ['full', 'bugfix', 'trivial', 'docs', 'research'] as const) {
      const listed = new Set(backend[prof] ?? []);
      expect(listed.size, `backend must define ${prof}`).toBeGreaterThan(0);
      for (const stage of concreteStages) {
        const cell = SCOPE_DEPTH_GRID[prof][stage];
        if (listed.has(stage)) {
          expect(cell, `${prof}.${stage} is in backend list → EXECUTE`).toBe('EXECUTE');
        } else {
          expect(cell, `${prof}.${stage} absent from backend list → SKIP`).toBe('SKIP');
        }
      }
    }
  });
});
