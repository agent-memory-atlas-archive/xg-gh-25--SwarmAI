// Feature: in-stream persistent compaction notice (run_d83f22d3, AC5)
/**
 * TabView compact-notice render tests.
 *
 * A `context_compacted` SSE event is now surfaced as a PERSISTENT in-stream
 * system message (role=system, id prefix 'compact-'), appended to the tab's
 * MessageStore by useChatStreamingLifecycle. TabView renders it as an
 * informational divider that:
 *  - shows the FULL backend notice TEXT (not a one-line label), and
 *  - does NOT dim prior messages (a compaction is a current-session event, not a
 *    session boundary — only true resume boundaries dim prior context).
 *
 * This is distinct from the 'refresh-' (Context Refreshed) and bare resume
 * ('Session Resumed') system dividers.
 *
 * MessageBubble is mocked (the compact/system divider is rendered by TabView
 * itself, not MessageBubble), so a mock is harmless and keeps the test fast.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { messageStoreRegistry } from '../../../../stores/MessageStore';
import type { Message } from '../../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));
vi.mock('../MessageBubble', () => ({
  MessageBubble: ({ message }: { message: Message }) => (
    <div data-testid={`bubble-${message.id}`}>{message.id}</div>
  ),
}));
vi.mock('../WelcomeScreen', () => ({ WelcomeScreen: () => <div data-testid="welcome" /> }));
vi.mock('../../../../components/chat', () => ({
  ChatErrorMessage: () => <div />,
}));
vi.mock('../../../../components/common', () => ({ Spinner: () => <div /> }));

import { TabView } from '../TabView';

const noop = () => {};
function props(tabId: string, messagesProp: Message[]) {
  return {
    tabId,
    messages: messagesProp,
    isActive: true,
    isStreaming: false,
    pendingQuestion: null,
    activeTabPendingQuestion: null,
    pendingPermissionRequestId: null,
    contextWarning: null,
    isWaitingForBusy: false,
    onCancelBusyWait: noop,
    hasMoreMessages: false,
    isLoadingOlderMessages: false,
    onLoadOlder: noop,
    onAnswerQuestion: noop,
    onPermissionDecision: noop,
    onEscalationSelect: noop,
    onCancelQueued: noop,
    onContinue: noop,
    onFocusClick: noop,
    onItemClick: noop,
    onRetryQueueTimeout: noop,
  };
}

const asst = (id: string, text: string): Message =>
  ({ id, role: 'assistant', content: [{ type: 'text', text }], timestamp: new Date().toISOString() });
const compact = (id: string, text: string): Message =>
  ({ id, role: 'system', content: [{ type: 'text', text }], timestamp: new Date().toISOString() });

const NOTICE = 'Conversation above has been summarized\nThe conversation reached the agent context limit.';

describe('TabView — compact-notice in-stream divider (AC5)', () => {
  beforeEach(() => {
    (Element.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = vi.fn();
    messageStoreRegistry.clear();
  });
  afterEach(() => {
    cleanup();
    messageStoreRegistry.clear();
  });

  it('renders the full compaction notice TEXT (not a one-line label)', () => {
    messageStoreRegistry.getOrCreate('A').replace([
      asst('a1', 'earlier reply'),
      compact('compact-123', NOTICE),
    ]);
    const { getByText } = render(<TabView {...props('A', [])} />);
    // The notice text renders verbatim (whitespace-pre-wrap preserves the newline;
    // getByText with a matcher tolerant of the normalized whitespace).
    expect(getByText(/Conversation above has been summarized/)).not.toBeNull();
    expect(getByText(/reached the agent context limit/)).not.toBeNull();
  });

  it('does NOT dim prior messages (compact- is excluded from resume-boundary dimming)', () => {
    // A compact- system message followed by a real assistant message. If compact-
    // were treated as a resume boundary, 'a1' (before it) would get opacity-50.
    messageStoreRegistry.getOrCreate('A').replace([
      asst('a1', 'before compaction'),
      compact('compact-123', NOTICE),
      asst('a2', 'after compaction'),
    ]);
    const { getByTestId } = render(<TabView {...props('A', [])} />);
    const before = getByTestId('bubble-a1');
    // Walk up: the dimming wrapper is the bubble's parent div (opacity-50 when dimmed).
    const wrapper = before.parentElement;
    expect(wrapper?.className ?? '').not.toContain('opacity-50');
  });

  it('a TRUE resume boundary STILL dims prior messages (control — exclusion is compact-specific)', () => {
    // Sanity: the dimming mechanism still works for a real resume boundary, proving
    // the AC5 fix narrowed the exclusion to compact-/refresh- and did not disable dimming.
    messageStoreRegistry.getOrCreate('A').replace([
      asst('a1', 'prior session'),
      compact('resume-boundary-9', 'Session resumed'), // non-refresh, non-compact → dims
      asst('a2', 'current session'),
    ]);
    const { getByTestId } = render(<TabView {...props('A', [])} />);
    const prior = getByTestId('bubble-a1');
    expect(prior.parentElement?.className ?? '').toContain('opacity-50');
  });
});
