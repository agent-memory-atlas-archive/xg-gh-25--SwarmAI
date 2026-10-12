/**
 * ScopeDepthMatrix — SRS design §5.3: the scope×depth matrix for the Pipeline card.
 *
 * Shows, for the CURRENT run, "what will this run do" as a small-multiples grid:
 * rows = the 9 canonical stages, columns = the 6 profiles, each cell = EXECUTE /
 * SKIP / CONDITIONAL. The current profile's column is the ONE dominant element
 * (Von Restorff); every other column is muted ambient reference. A depth badge
 * (standard | light) sits beside the active profile.
 *
 * Design-judgment compliance (data/design-judgment.md, read per R15):
 *  - A card answers a DECISION: here = "which stages run for MY run, at what depth".
 *    The answer is the highlighted column; the rest is detail-on-demand context.
 *  - Von Restorff: exactly ONE column dominant (the active profile); others muted.
 *  - Tufte small-multiples: all 54 cells on a SHARED 3-value scale (EXECUTE/SKIP/
 *    CONDITIONAL) — a legitimate comparison grid, NOT an equal-weight tile dump.
 *  - Fewer borders / whitespace grouping: no per-cell box; a glyph on a shared grid.
 *  - "Compared to what": the whole point is comparing the active profile to the others.
 *
 * The grid MIRRORS backend core/pipeline_profiles.PIPELINE_PROFILES. It is a static
 * reference (which stages a profile runs never varies per run), so it is a frontend
 * constant, not a fetched payload — kept in lockstep with the backend by
 * ScopeDepthMatrix.test.tsx (a drift there is a test failure).
 */

// The 9 canonical stages (architecture order). ADVERSARIAL rides inside DELIVER
// (not its own orchestration row) — shown as a stage because §5.3 says "9 stages".
export const MATRIX_STAGES = [
  'evaluate', 'think', 'plan', 'build', 'review', 'test', 'adversarial', 'deliver', 'reflect',
] as const;

export const MATRIX_PROFILES = [
  'full', 'bugfix', 'goal', 'trivial', 'docs', 'research',
] as const;

export type MatrixProfile = (typeof MATRIX_PROFILES)[number];
export type MatrixCell = 'EXECUTE' | 'SKIP' | 'CONDITIONAL';

/**
 * Per-profile stage disposition. Mirrors PIPELINE_PROFILES (backend SSOT):
 *  - a stage in the profile's list → EXECUTE
 *  - a stage absent → SKIP
 *  - 'adversarial' is CONDITIONAL everywhere it runs: it executes INSIDE deliver as
 *    a blocking gate (so it's EXECUTE wherever deliver runs), except relaxed profiles
 *    where it is the lite/skipped tier → CONDITIONAL (depth-tunable, never fully off
 *    on a profile that delivers code).
 * goal replaces build+review+test with goal_cycle (loops them) → those three are
 * CONDITIONAL for goal (they run, but inside the cycle, not as standalone stages).
 */
export const SCOPE_DEPTH_GRID: Record<MatrixProfile, Record<string, MatrixCell>> = {
  full:     { evaluate: 'EXECUTE', think: 'EXECUTE', plan: 'EXECUTE', build: 'EXECUTE', review: 'EXECUTE', test: 'EXECUTE', adversarial: 'EXECUTE', deliver: 'EXECUTE', reflect: 'EXECUTE' },
  bugfix:   { evaluate: 'EXECUTE', think: 'EXECUTE', plan: 'EXECUTE', build: 'EXECUTE', review: 'EXECUTE', test: 'EXECUTE', adversarial: 'EXECUTE', deliver: 'EXECUTE', reflect: 'EXECUTE' },
  goal:     { evaluate: 'EXECUTE', think: 'EXECUTE', plan: 'EXECUTE', build: 'CONDITIONAL', review: 'CONDITIONAL', test: 'CONDITIONAL', adversarial: 'EXECUTE', deliver: 'EXECUTE', reflect: 'EXECUTE' },
  trivial:  { evaluate: 'EXECUTE', think: 'EXECUTE', plan: 'SKIP', build: 'EXECUTE', review: 'EXECUTE', test: 'EXECUTE', adversarial: 'CONDITIONAL', deliver: 'EXECUTE', reflect: 'EXECUTE' },
  docs:     { evaluate: 'EXECUTE', think: 'EXECUTE', plan: 'EXECUTE', build: 'SKIP', review: 'SKIP', test: 'SKIP', adversarial: 'SKIP', deliver: 'EXECUTE', reflect: 'EXECUTE' },
  research: { evaluate: 'EXECUTE', think: 'EXECUTE', plan: 'SKIP', build: 'SKIP', review: 'SKIP', test: 'SKIP', adversarial: 'SKIP', deliver: 'SKIP', reflect: 'EXECUTE' },
};

const CELL_GLYPH: Record<MatrixCell, string> = {
  EXECUTE: '●',       // filled = runs
  CONDITIONAL: '◐',   // half = runs conditionally (inside a loop / depth-tunable)
  SKIP: '·',          // dot = skipped (minimal ink — Tufte)
};

export interface ScopeDepthMatrixProps {
  /** The current run's profile — its column is the ONE dominant element. */
  activeProfile?: string | null;
  /** The current run's resolved depth (standard | light) — shown as a badge. */
  activeDepth?: string | null;
}

function norm(p: string | null | undefined): MatrixProfile | null {
  if (!p) return null;
  const k = p.trim().toLowerCase();
  if (k === 'standard') return 'full'; // alias (matches backend normalize_profile)
  return (MATRIX_PROFILES as readonly string[]).includes(k) ? (k as MatrixProfile) : null;
}

/**
 * The scope×depth matrix. Pure, presentational, no fetch — the active column is
 * emphasized; all others are muted ambient reference (Von Restorff / deference).
 */
export function ScopeDepthMatrix({ activeProfile, activeDepth }: ScopeDepthMatrixProps) {
  const active = norm(activeProfile);
  const depth = activeDepth?.trim().toLowerCase() === 'light' ? 'light' : 'standard';

  return (
    <div className="scope-depth-matrix" data-testid="scope-depth-matrix">
      <table className="sdm-table">
        <thead>
          <tr>
            <th className="sdm-corner" scope="col">stage</th>
            {MATRIX_PROFILES.map((p) => (
              <th
                key={p}
                scope="col"
                data-profile={p}
                data-active={active === p ? 'true' : 'false'}
                className={active === p ? 'sdm-col-active' : 'sdm-col-muted'}
              >
                {p}
                {active === p && (
                  <span className="sdm-depth-badge" data-testid="sdm-depth-badge"> · {depth}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {MATRIX_STAGES.map((stage) => (
            <tr key={stage}>
              <th scope="row" className="sdm-row-label">{stage}</th>
              {MATRIX_PROFILES.map((p) => {
                const cell = SCOPE_DEPTH_GRID[p][stage] ?? 'SKIP';
                const isActiveCol = active === p;
                return (
                  <td
                    key={p}
                    data-profile={p}
                    data-stage={stage}
                    data-cell={cell}
                    data-active={isActiveCol ? 'true' : 'false'}
                    className={isActiveCol ? 'sdm-cell-active' : 'sdm-cell-muted'}
                    title={`${p} · ${stage}: ${cell}`}
                  >
                    {CELL_GLYPH[cell]}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
