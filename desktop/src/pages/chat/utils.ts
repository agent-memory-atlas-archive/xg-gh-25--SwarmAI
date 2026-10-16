import type { ChatSession, Message, ContentBlock } from '../../types';
// (ToolUseContent fields accessed via narrowed ContentBlock — no extra import needed)
import { MS_PER_DAY, type TimeGroup } from './constants';
import type { PendingQuestion } from './types';

/**
 * Convert a DB-loaded message row into a display `Message`.
 *
 * Shared by ChatPage (session load / pagination / restore) AND the History
 * overlay's read-only preview — extracted here so both use one mapping.
 *
 * Marks DB-loaded text/thinking blocks as `_confirmed`: they are authoritative
 * history, and without the flag a subsequent streaming assistant event would
 * treat them as provisional and WIPE them (structural reconciliation replaces
 * unconfirmed blocks).
 */
export function toDisplayMessage(
  msg: { id: string; role: string; content: ContentBlock[]; createdAt: string; model?: string;
         metadata?: { client_id?: string; [key: string]: unknown } },
): Message {
  return {
    id: msg.id,
    role: msg.role as 'user' | 'assistant' | 'system',
    content: (msg.content as ContentBlock[]).map((block) =>
      (block.type === 'text' || block.type === 'thinking')
        ? { ...block, _confirmed: true }
        : block,
    ),
    timestamp: msg.createdAt,
    model: msg.model,
    // Preserve the backend correlation key. toMessageCamelCase already carries
    // metadata.client_id on every DB fetch; this converter is the ONE seam that
    // used to DROP it — so an initial-load / load-older bubble arrived KEYLESS and
    // a later mid-turn-cut reconcile (whose merged DB id differs from this bubble's
    // id — the backend uses the first-in-tail row id) could not correlate → a
    // DUPLICATE half-bubble. Carrying client_id here closes that entrance at the
    // single chokepoint every DB-load path funnels through (run_03d6ee38). The
    // display id stays the canonical DB id (pagination `before_id` cursor unaffected).
    ...(msg.metadata ? { metadata: msg.metadata } : {}),
  };
}

/**
 * Concatenate a page of older messages in front of the current messages,
 * merging the page boundary when both sides are assistant messages.
 *
 * The backend persists each agentic turn as a separate DB row and merges
 * consecutive assistant rows per-fetch (see `_merge_consecutive_assistant_messages`).
 * But a single agent response whose rows straddle a pagination boundary is
 * split across two fetches — the backend cannot merge across fetches. Without
 * this seam merge, "load older" would render the response as two bubbles.
 *
 * Rule: if the LAST message of `older` and the FIRST message of `current` are
 * both assistant, their content blocks are concatenated into one message that
 * keeps the older message's id/timestamp (stable anchor for the cursor) and
 * the newer message's model (most recent attribution).
 *
 * Pure function — does not mutate either input array or their messages.
 */
export function mergeOlderMessages(
  older: Message[],
  current: Message[],
): Message[] {
  if (older.length === 0) return current;
  if (current.length === 0) return older;

  const lastOlder = older[older.length - 1];
  const firstCurrent = current[0];

  if (lastOlder.role === 'assistant' && firstCurrent.role === 'assistant') {
    const mergedBoundary: Message = {
      ...lastOlder,
      content: [
        ...(lastOlder.content as ContentBlock[]),
        ...(firstCurrent.content as ContentBlock[]),
      ],
      // Newer message's model wins (most recent attribution).
      model: firstCurrent.model ?? lastOlder.model,
    };
    return [
      ...older.slice(0, -1),
      mergedBoundary,
      ...current.slice(1),
    ];
  }

  return [...older, ...current];
}

export interface GroupedSessions {
  group: TimeGroup;
  sessions: ChatSession[];
}

/**
 * Groups chat sessions by time periods (today, yesterday, this week, this month, older)
 */
export const groupSessionsByTime = (sessions: ChatSession[]): GroupedSessions[] => {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - MS_PER_DAY);

  // Week starts on Monday
  const dayOfWeek = now.getDay();
  const mondayOffset = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  const weekStart = new Date(today.getTime() - mondayOffset * MS_PER_DAY);

  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);

  const groups: Record<TimeGroup, ChatSession[]> = {
    today: [],
    yesterday: [],
    thisWeek: [],
    thisMonth: [],
    older: [],
  };

  for (const session of sessions) {
    const date = new Date(session.lastAccessedAt);
    const sessionDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    if (sessionDay.getTime() === today.getTime()) {
      groups.today.push(session);
    } else if (sessionDay.getTime() === yesterday.getTime()) {
      groups.yesterday.push(session);
    } else if (sessionDay >= weekStart) {
      groups.thisWeek.push(session);
    } else if (sessionDay >= monthStart) {
      groups.thisMonth.push(session);
    } else {
      groups.older.push(session);
    }
  }

  // Return only non-empty groups in order
  const order: TimeGroup[] = ['today', 'yesterday', 'thisWeek', 'thisMonth', 'older'];
  return order
    .filter((group) => groups[group].length > 0)
    .map((group) => ({ group, sessions: groups[group] }));
};

/**
 * Format a session timestamp for the History list as an absolute LOCAL time
 * `YYYY-MM-DD HH:MM` (24-hour, no timezone conversion, no relative "Xh ago").
 *
 * Rationale (XG, 2026-08-02): History is a scan surface — a stable, sortable,
 * unambiguous absolute stamp beats a drifting relative one. Uses local getters
 * (getFullYear/getMonth/getDate/getHours/getMinutes) so it reflects the user's
 * wall clock, matching every other absolute timestamp shown in the app.
 * Sole caller: HistoryView.
 */
export const formatTimestamp = (timestamp: string | undefined): string => {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return '';

  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

/**
 * Resolve the toolUseId of the question the active tab should render as
 * answerable (Root 3 / 3A — AskUserQuestion surfacing fix).
 *
 * Background: `ContentBlockRenderer` enables the AskUserQuestion submit only
 * when `pendingToolUseId === block.toolUseId`. That prop was sourced ONLY from
 * React `pendingQuestion` state, which is null on background tabs and during the
 * mid-stream stale-ref window (`setPendingQuestion` is gated by `isActiveTab` in
 * useChatStreamingLifecycle). The per-tab cache (`tabState.pendingQuestion`) is
 * populated regardless, so we fall back to it — the question stays answerable.
 *
 * PIT71/PIT74 cross-tab-leak guard: the caller MUST pass ONLY the ACTIVE tab's
 * cache as `activeTabPending`. ChatPage renders only the active tab's messages,
 * so a question from a different tab is never an input here and can never leak.
 *
 * Pure function. Returns `undefined` (never `''`) when there is no live question.
 */
export function resolvePendingToolUseId(
  reactPending: PendingQuestion | null | undefined,
  activeTabPending: PendingQuestion | null | undefined,
): string | undefined {
  const id = reactPending?.toolUseId || activeTabPending?.toolUseId;
  return id ? id : undefined;
}

/**
 * A render unit emitted by {@link groupConsecutiveTools}: either a single
 * content block (rendered as-is) or a GROUP of consecutive same-category
 * tool_use blocks (rendered as one collapsed summary row).
 */
export type RenderUnit =
  | { kind: 'block'; block: ContentBlock; index: number }
  | {
      kind: 'tool-group';
      category: string;
      blocks: ToolUseInGroup[];
      startIndex: number;
      /**
       * CONTENT-STABLE identity for expansion state (the first member's tool_use
       * id). Keying expansion by this instead of positional `startIndex` means a
       * content shift (load-older prepend, stream-end reconcile) can't re-point a
       * user's expanded group at a DIFFERENT run — the Gate-2 correctness finding.
       */
      groupId: string;
    };

export interface ToolUseInGroup {
  block: ContentBlock;      // the tool_use block (type: 'tool_use')
  index: number;            // original position in message.content (stable key)
}

/**
 * Normalize a tool_use category for GROUPING + summary. The backend emits two
 * distinct non-empty "I don't know" values — `'unknown'` (no tool-summarizer
 * branch) and `'fallback'` (get_tool_category's MCP/unknown default) — plus a
 * missing field reads as `''`. Collapsing all three to one sentinel keeps two
 * adjacent runs of unknown tools from rendering as two identical "Ran N tools"
 * rows that refuse to merge (the Gate-2 integration finding).
 */
function normalizeToolCategory(raw: string | undefined): string {
  const c = raw ?? '';
  if (c === '' || c === 'unknown' || c === 'fallback') return '';
  return c;
}

/**
 * Group CONSECUTIVE same-category `tool_use` blocks into one render unit so the
 * UI can show a single collapsed summary ("read 5 files") instead of five rows.
 * The streaming-UX simplification (Run 1): main stream stays quiet, detail on demand.
 *
 * Rules (each earned from the Gate-1 adversarial review):
 * - **Consecutive only.** A non-tool_use block, or a tool_use of a DIFFERENT
 *   category, breaks the run — time order is preserved, never reordered.
 * - **Mixed-state DOWNGRADE (H3/H2).** A group is emitted ONLY if EVERY member
 *   is a clean, resolved success. If ANY member is an error, pending, or has no
 *   result yet, the whole run is emitted as individual `block` units instead —
 *   so an error/spinner is never hidden inside a collapsed summary, and the
 *   1:1 tool_use↔result / key / permission wiring is untouched.
 * - **Singletons stay blocks.** A run of length 1 is a plain `block` (no group
 *   wrapper for a lone tool call).
 * - **tool_result blocks pass through as blocks** — ContentBlockRenderer already
 *   skips the ones consumed by a tool_use; grouping does not touch that path.
 *
 * Pure function (no React, no state) → unit-testable. `resultMap` keys are
 * toolUseId; a tool is "clean success" iff it HAS a result and that result is
 * not an error.
 *
 * @param blocks  message.content, in order
 * @param resultMap  toolUseId → { isError } (result presence = resolved)
 * @param isStreaming  when true, a tool_use with no result yet is "pending"
 */
export function groupConsecutiveTools(
  blocks: ContentBlock[],
  resultMap: Map<string, { isError?: boolean } | undefined>,
  isStreaming: boolean,
): RenderUnit[] {
  const units: RenderUnit[] = [];
  let i = 0;

  const isCleanSuccess = (b: ContentBlock): boolean => {
    if (b.type !== 'tool_use') return false;
    const result = resultMap.get(b.id);
    if (!result) return false;        // no result yet → pending, not clean
    return !result.isError;           // error → not clean
  };

  while (i < blocks.length) {
    const block = blocks[i];

    // Non-tool_use block → emit as-is, advance one.
    if (block.type !== 'tool_use') {
      units.push({ kind: 'block', block, index: i });
      i += 1;
      continue;
    }

    // Start of a potential run: gather consecutive SAME-category tool_use.
    // Normalize so 'unknown'/'fallback'/'' are one category (no split rows).
    const category = normalizeToolCategory(block.category);
    let j = i;
    while (
      j < blocks.length &&
      blocks[j].type === 'tool_use' &&
      normalizeToolCategory((blocks[j] as { category?: string }).category) === category
    ) {
      j += 1;
    }
    const run = blocks.slice(i, j);

    // Emit as a GROUP only if length>1 AND every member is a clean success.
    // Otherwise emit each member as an individual block (mixed-state downgrade).
    const everyClean = run.every(isCleanSuccess);
    if (run.length > 1 && everyClean && !isStreaming) {
      units.push({
        kind: 'tool-group',
        category,
        blocks: run.map((b, k) => ({ block: b, index: i + k })),
        startIndex: i,
        // Content-stable id: first member's tool_use id (falls back to startIndex
        // only if an id is somehow absent). Used as the expansion key.
        groupId: `tg-${(run[0] as { id?: string }).id || i}`,
      });
    } else {
      run.forEach((b, k) => units.push({ kind: 'block', block: b, index: i + k }));
    }
    i = j;
  }

  return units;
}
