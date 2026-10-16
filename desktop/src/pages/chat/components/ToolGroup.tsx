/**
 * ToolGroup — collapsed summary row for a run of CONSECUTIVE same-category
 * tool_use blocks (streaming simplification, Run 1).
 *
 * Renders ONE quiet line ("Read 5 files") in place of N individual tool rows;
 * clicking expands to the original per-tool MergedToolBlock children (passed in).
 * The grouping decision + mixed-state downgrade lives in `groupConsecutiveTools`
 * (utils.ts) — this component only renders a group it was TOLD is a clean,
 * groupable run, so it never has to reason about errors/pending (those were
 * downgraded to individual blocks upstream, per the Gate-1 adversarial review).
 *
 * Design (per s_frontend-design design-judgment): no border — whitespace +
 * one hover bg separates it; the ONLY emphasis is the count; detail on demand.
 *
 * Default COLLAPSED. Expansion state is lifted to the caller (keyed by group id)
 * so a tab-switch + remount does not snap an expanded group shut (M4 anti-jump).
 *
 * @exports ToolGroup
 * @exports CATEGORY_LABELS — category to human-friendly verb ("read" -> "Read")
 */
import type { ReactNode } from 'react';
import { getToolIcon } from './MergedToolBlock';

/**
 * Category to a PLAIN verb for the collapsed summary ("read" -> "Read").
 * A verb here must NOT embed its noun — summaryText appends the CATEGORY_NOUN,
 * so a verb like "Ran skill" + noun "skills" would double up ("Ran skill 2
 * skills"). The verb says the action; the noun says what was acted on.
 */
export const CATEGORY_LABELS: Record<string, string> = {
  read: 'Read',
  write: 'Edited',
  search: 'Searched',
  bash: 'Ran',
  web_fetch: 'Fetched',
  web_search: 'Searched',
  tool_search: 'Searched',
  list_dir: 'Listed',
  skill: 'Ran',
  agent: 'Ran',
  todowrite: 'Updated',
};

/** Noun for the item count, by category ("read" -> "files"). */
const CATEGORY_NOUN: Record<string, string> = {
  read: 'files',
  write: 'files',
  search: 'searches',
  bash: 'commands',
  list_dir: 'directories',
  web_fetch: 'pages',
  web_search: 'web searches',
  tool_search: 'tool searches',
  skill: 'skills',
  agent: 'agents',
  todowrite: 'todos',
};

/**
 * Build the collapsed summary line ("Read 5 files"). Exported for unit testing
 * the unknown/MCP-category fallback (no "Did Nx" dead-end) and the verb+noun
 * grammar (never a double noun like "Ran skill 2 skills").
 */
export function summaryText(category: string, count: number): string {
  // Unmapped category (an unknown or MCP-derived one) → a human "Ran N tools"
  // instead of the uninformative "Did Nx". getToolIcon has a matching safe
  // fallback icon, so an unknown category still renders a sensible row.
  const verb = CATEGORY_LABELS[category] ?? 'Ran';
  const noun = CATEGORY_NOUN[category] ?? 'tools';
  return `${verb} ${count} ${noun}`;
}

interface ToolGroupProps {
  category: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}

export function ToolGroup({ category, count, expanded, onToggle, children }: ToolGroupProps) {
  return (
    <div className="rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-[var(--color-hover)] cursor-pointer hover:brightness-95 transition-colors"
        onClick={onToggle}
        onKeyDown={(e) => {
          // Keyboard parity with the mouse click: a div[role=button] is not
          // natively focus/Enter/Space-activatable, so wire it explicitly.
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
      >
        <span className="material-symbols-outlined text-primary text-sm">
          {getToolIcon(category)}
        </span>
        <span className="text-sm text-[var(--color-text-muted)] flex-1">
          {summaryText(category, count)}
        </span>
        <span className="material-symbols-outlined text-sm text-[var(--color-text-muted)]">
          {expanded ? 'expand_less' : 'expand_more'}
        </span>
      </div>

      {expanded && (
        <div className="ml-7 mt-1 flex flex-col gap-1">
          {children}
        </div>
      )}
    </div>
  );
}
