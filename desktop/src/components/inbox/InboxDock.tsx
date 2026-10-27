/**
 * InboxDock — collapsible right-side panel showing unified inbox messages.
 *
 * Layout (inside ChatPage's flex row, to the RIGHT of Canvas):
 *
 *  ┌─ InboxDock ────────────────────────┐
 *  │  Inbox            [mark read] [×]  │  ← header
 *  │ ─── connection status ──────────── │  ← optional: warning bar
 *  │ ┌──────────────────────────────┐   │
 *  │ │ mail sender — subject         │   │  ← message card
 *  │ │    preview text… 5m ago       │   │
 *  │ ├──────────────────────────────┤   │
 *  │ │ chat sender — #channel        │   │
 *  │ │    message preview… 12m ago   │   │
 *  │ └──────────────────────────────┘   │
 *  │         empty state / loading      │
 *  └────────────────────────────────────┘
 *
 * Width: 320px (fixed). Mounts/unmounts via `isOpen` prop.
 * Follows the same pattern as FileViewerPanel (Canvas): a flex sibling
 * of the main chat area, sliding in from the right.
 */

import { memo, useRef } from 'react';
import type { InboxDisplayItem } from '../../hooks/useInbox';

// ---------------------------------------------------------------------------
// Tiny relative-time formatter (no external dep)
// ---------------------------------------------------------------------------
function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  if (isNaN(diff)) return '';
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return 'just now';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(isoDate).toLocaleDateString();
}

// Source → Material Symbol icon name
function sourceIconName(source: string): string {
  switch (source) {
    case 'slack': return 'chat';
    case 'outlook': return 'mail';
    default: return 'mail';
  }
}

function sourceLabel(source: string): string {
  switch (source) {
    case 'slack': return 'Slack';
    case 'outlook': return 'Outlook';
    default: return source;
  }
}

// ---------------------------------------------------------------------------
// InboxItem card
// ---------------------------------------------------------------------------
interface InboxCardProps {
  item: InboxDisplayItem;
}

const InboxCard = memo(function InboxCard({ item }: InboxCardProps) {
  return (
    <li
      role="article"
      aria-label={`${item.isRead ? '' : 'Unread '}message from ${item.sender || 'unknown'}: ${item.subject || item.preview}`}
      className={`
        px-3 py-2.5 border-b border-[var(--color-border)]
        hover:bg-[var(--color-bg-hover)] transition-colors cursor-default
        ${!item.isRead ? 'bg-[var(--color-bg-subtle)]' : ''}
      `}
    >
      {/* Row 1: source icon + sender + time */}
      <div className="flex items-center gap-1.5 mb-0.5">
        <span className="material-symbols-outlined text-[14px] flex-shrink-0 text-[var(--color-text-muted)]">
          {sourceIconName(item.source)}
        </span>
        <span className="text-xs font-medium text-[var(--color-text)] truncate flex-1">
          {item.sender || 'Unknown'}
        </span>
        <span className="text-[10px] text-[var(--color-text-muted)] flex-shrink-0 tabular-nums">
          {timeAgo(item.timestamp)}
        </span>
      </div>

      {/* Row 2: subject (if present) */}
      {item.subject && (
        <div className="text-xs font-medium text-[var(--color-text)] truncate pl-5 mb-0.5">
          {item.subject}
        </div>
      )}

      {/* Row 3: preview */}
      <div className="text-xs text-[var(--color-text-muted)] truncate pl-5">
        {item.preview || '(no content)'}
      </div>

      {/* Source badge + unread dot */}
      <div className="flex items-center gap-1 mt-1 pl-5">
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
          {sourceLabel(item.source)}
        </span>
        {!item.isRead && (
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 flex-shrink-0" aria-label="Unread" />
        )}
      </div>
    </li>
  );
}, (prev, next) => prev.item.id === next.item.id && prev.item.isRead === next.item.isRead);

// ---------------------------------------------------------------------------
// InboxDock
// ---------------------------------------------------------------------------
export interface InboxDockProps {
  isOpen: boolean;
  items: InboxDisplayItem[];
  unreadCount: number;
  isLoading: boolean;
  error: Error | null;
  onClose: () => void;
  onMarkAllRead: () => void;
}

const DOCK_WIDTH = 320;

export const InboxDock = memo(function InboxDock({
  isOpen,
  items,
  unreadCount,
  isLoading,
  error,
  onClose,
  onMarkAllRead,
}: InboxDockProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // Track newest item to only auto-scroll when genuinely new content arrives
  const prevNewestRef = useRef<string | null>(null);
  const newestId = items.length > 0 ? items[0].id : null;
  if (newestId && newestId !== prevNewestRef.current && scrollRef.current) {
    scrollRef.current.scrollTop = 0;
  }
  prevNewestRef.current = newestId;

  if (!isOpen) return null;

  return (
    <div
      role="complementary"
      aria-label="Inbox"
      className="flex flex-col border-l border-[var(--color-border)] bg-[var(--color-bg)] overflow-hidden flex-shrink-0"
      style={{ width: DOCK_WIDTH, minWidth: DOCK_WIDTH }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] text-[var(--color-text-muted)]">inbox</span>
          <span className="text-sm font-semibold text-[var(--color-text)]">Inbox</span>
          {unreadCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500 text-white font-medium min-w-[18px] text-center">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {unreadCount > 0 && (
            <button
              onClick={onMarkAllRead}
              className="p-1 rounded hover:bg-[var(--color-bg-hover)] transition-colors"
              title="Mark all as read"
              aria-label="Mark all messages as read"
            >
              <span className="material-symbols-outlined text-[16px] text-[var(--color-text-muted)]">done_all</span>
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--color-bg-hover)] transition-colors"
            title="Close inbox"
            aria-label="Close inbox panel"
          >
            <span className="material-symbols-outlined text-[16px] text-[var(--color-text-muted)]">close</span>
          </button>
        </div>
      </div>

      {/* Error bar */}
      {error && (
        <div role="alert" className="px-3 py-1.5 text-xs bg-yellow-500/10 text-yellow-600 border-b border-yellow-500/20">
          <span className="material-symbols-outlined text-[12px] mr-1 align-middle">warning</span>
          {error.message || 'Failed to fetch inbox'}
        </div>
      )}

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isLoading && items.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--color-text-muted)]">
            <div className="text-center">
              <span className="material-symbols-outlined text-2xl animate-spin">progress_activity</span>
              <p className="text-xs mt-2">Loading inbox…</p>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-[var(--color-text-muted)]">
            <div className="text-center">
              <span className="material-symbols-outlined text-3xl mb-2">inbox</span>
              <p className="text-xs">No messages yet</p>
              <p className="text-[10px] mt-1 opacity-60">
                New Slack &amp; Outlook messages will appear here
              </p>
            </div>
          </div>
        ) : (
          <ul role="list" className="list-none m-0 p-0">
            {items.map((item) => <InboxCard key={item.id} item={item} />)}
          </ul>
        )}
      </div>

      {/* Footer — item count */}
      {items.length > 0 && (
        <div className="px-3 py-1.5 border-t border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)] text-center">
          {items.length} message{items.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
});

// ---------------------------------------------------------------------------
// InboxToggle — the button that opens the dock (lives in ChatHeader)
// ---------------------------------------------------------------------------
export interface InboxToggleProps {
  unreadCount: number;
  isOpen: boolean;
  onClick: () => void;
}

export const InboxToggle = memo(function InboxToggle({
  unreadCount,
  isOpen,
  onClick,
}: InboxToggleProps) {
  return (
    <button
      onClick={onClick}
      aria-label={isOpen ? 'Close inbox' : `Inbox${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      className={`
        relative p-1.5 rounded-md transition-colors
        ${isOpen
          ? 'bg-[var(--color-bg-active)] text-[var(--color-text)]'
          : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}
      `}
      title={isOpen ? 'Close inbox' : `Inbox${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
    >
      <span className="material-symbols-outlined text-[18px]">inbox</span>
      {unreadCount > 0 && !isOpen && (
        <span
          className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-blue-500 text-white text-[9px] font-bold flex items-center justify-center"
          aria-hidden="true"
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      )}
    </button>
  );
});
