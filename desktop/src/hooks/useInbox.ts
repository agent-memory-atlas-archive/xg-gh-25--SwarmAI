/**
 * useInbox — poll the unified inbox API for inbound messages.
 *
 * Polls `GET /api/channels/inbox` at a configurable interval (default 30s)
 * and exposes:
 *   - items[]        — newest-first inbox messages (with display metadata)
 *   - unreadCount    — messages newer than the read-watermark
 *   - isLoading      — first fetch in progress
 *   - error          — last fetch error (null on success)
 *   - markAllRead()  — advance watermark to newest item
 *   - refetch()      — force an immediate refetch
 *
 * Design:
 * - Uses react-query for caching + background refetch + window-focus refetch.
 * - Read state uses a **timestamp watermark** (not an ID Set) — O(1), never
 *   grows, survives item rotation.
 * - Polling pauses when the window is backgrounded (refetchIntervalInBackground).
 *
 * Inbox message shape (from backend GET /api/channels/inbox):
 *   { id, channel_session_id, direction, external_message_id,
 *     content, content_type, metadata, status, error_message,
 *     created_at, updated_at, channel_id, external_chat_id }
 */

import { useQuery } from '@tanstack/react-query';
import { useState, useCallback, useRef, useMemo } from 'react';
import api from '../services/api';

/** Shape of a single inbox row returned by the backend. */
export interface InboxItem {
  id: string;
  channel_session_id: string;
  direction: 'inbound' | 'outbound';
  external_message_id: string | null;
  content: string;
  content_type: string;
  metadata: string | null; // JSON-encoded, may be null
  status: string;
  error_message: string | null;
  created_at: string; // ISO-8601
  updated_at: string;
  channel_id: string;
  external_chat_id: string;
}

/** Parsed metadata for display. */
export interface InboxDisplayItem {
  id: string;
  source: 'slack' | 'outlook' | string;
  sender: string;
  preview: string;
  subject: string;
  timestamp: string;  // ISO-8601
  isRead: boolean;
  raw: InboxItem;
}

const INBOX_POLL_MS = 30_000;
const INBOX_QUERY_KEY = ['channels', 'inbox'] as const;
const INBOX_LIMIT = 50;

function parseMetadata(raw: string | null | undefined): Record<string, unknown> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function toDisplayItem(item: InboxItem, readWatermark: string): InboxDisplayItem {
  const meta = parseMetadata(item.metadata);
  // Determine source from metadata heuristics
  const source = (meta.platform as string) || (meta.channel_type as string) || 'unknown';
  const sender = (meta.sender_display_name as string)
    || (meta.senders as string)
    || (meta.from as string)
    || '';
  const subject = (meta.subject as string) || (meta.topic as string) || '';
  const preview = item.content?.slice(0, 120) || '';

  return {
    id: item.id,
    source,
    sender,
    preview,
    subject,
    timestamp: item.created_at,
    // An item is "read" if its timestamp <= the watermark
    isRead: readWatermark !== '' && item.created_at <= readWatermark,
    raw: item,
  };
}

export function useInbox(enabled = true) {
  // Watermark: ISO-8601 timestamp — items with created_at <= this are "read".
  // O(1) memory, never grows, survives item rotation.
  const [readWatermark, setReadWatermark] = useState('');
  const prevNewestIdRef = useRef<string | null>(null);

  const { data: rawItems = [], isLoading, error, refetch } = useQuery({
    queryKey: [...INBOX_QUERY_KEY],
    queryFn: async (): Promise<InboxItem[]> => {
      const resp = await api.get<InboxItem[]>('/channels/inbox', {
        params: { limit: INBOX_LIMIT },
      });
      return resp.data;
    },
    enabled,
    staleTime: INBOX_POLL_MS,
    refetchInterval: INBOX_POLL_MS,
    refetchIntervalInBackground: false, // pause when window is hidden
    refetchOnWindowFocus: true,
    retry: 2,
  });

  const items = useMemo(
    () => rawItems.map((item) => toDisplayItem(item, readWatermark)),
    [rawItems, readWatermark],
  );

  const unreadCount = useMemo(
    () => items.filter((i) => !i.isRead).length,
    [items],
  );

  const markAllRead = useCallback(() => {
    // Advance watermark to the newest item's timestamp
    if (rawItems.length > 0) {
      // rawItems is ordered newest-first from the backend
      setReadWatermark(rawItems[0].created_at);
    }
  }, [rawItems]);

  // Track if genuinely new content arrived (by checking newest ID)
  const newestId = rawItems.length > 0 ? rawItems[0].id : null;
  const hasNew = newestId !== null && newestId !== prevNewestIdRef.current;
  prevNewestIdRef.current = newestId;

  return {
    items,
    rawItems,
    unreadCount,
    isLoading,
    error: error as Error | null,
    hasNew,
    markAllRead,
    refetch,
  };
}
