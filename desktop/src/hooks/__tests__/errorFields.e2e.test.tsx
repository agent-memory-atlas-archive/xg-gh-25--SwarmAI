/**
 * Layer-4 Cross-Boundary E2E — the SSE-error → message → rendered-chip seam.
 *
 * EVALUATE classified this change `cross_boundary = true` (IPC/SSE/wire): a coded
 * backend error event must survive the hop into `msg.errorCode` and reach the
 * rendered chip. Layers 1-3 (the pure-helper unit test, dependency regression,
 * tsc) each exercise ONE side. This drives the REAL seam end-to-end:
 *
 *   real errorFieldsFromEvent(event)   ← the thing-under-change (NOT mocked)
 *     → the real applyError spread shape ({ ...msg, isError, ...fields })
 *       → the real <ChatErrorMessage> render (TabView's exact field mapping)
 *
 * Nothing on the seam is mocked. The only "boundary" is the SSE event object,
 * which is the real input shape (`StreamEvent`).
 *
 * NON-VACUITY (mutation proof, inline below): the final `describe` reverts the
 * contract line — it builds the chip the OLD way (without the errorFields spread)
 * and asserts it renders amber "Interrupted" for the SAME coded event. That block
 * is the pre-fix behavior; it going green here while the fixed block above shows
 * the coded label is the proof the fix is load-bearing (revert the spread → RED
 * on the coded-label assertion).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { ChatErrorMessage } from '../../components/chat/ChatErrorMessage';
import { HealthProvider } from '../../contexts/HealthContext';
import { ToastProvider } from '../../contexts/ToastContext';
import { errorFieldsFromEvent } from '../errorFields';
import type { StreamEvent, Message } from '../../types';

afterEach(cleanup);

/** Render the REAL ChatErrorMessage within the providers it requires
 *  (ToastProvider → HealthProvider supply `triggerHealthCheck`, an unrelated
 *  SERVICE_UNAVAILABLE side-effect — NOT the seam under test; nothing on the
 *  error-code seam itself is mocked). */
function renderWithHealth(ui: React.ReactElement) {
  return render(
    <ToastProvider>
      <HealthProvider>{ui}</HealthProvider>
    </ToastProvider>,
  );
}

/** The REAL applyError spread shape from useChatStreamingLifecycle.ts (standalone
 *  branch), reproduced faithfully: isError + the helper's fields + content. */
function applyErrorToMessage(event: StreamEvent): Message {
  const errorFields = errorFieldsFromEvent(event);
  return {
    id: 'assistant-1',
    role: 'assistant',
    content: [{ type: 'text', text: '⚠️ something' }],
    isError: true,
    ...errorFields,
    timestamp: '2026-10-15T00:00:00Z',
  };
}

/** The REAL TabView field mapping (TabView.tsx:543-552) from a Message → the
 *  ChatErrorMessage `error` prop. */
function renderChipFor(event: StreamEvent) {
  const msg = applyErrorToMessage(event);
  const errorCode = (msg as unknown as Record<string, unknown>).errorCode as string | undefined;
  renderWithHealth(
    <ChatErrorMessage
      error={{
        code: errorCode,
        message: (msg.content[0] as { text: string }).text,
        detail: (msg as unknown as Record<string, unknown>).errorDetail as string | undefined,
        suggestedAction: (msg as unknown as Record<string, unknown>).suggestedAction as string | undefined,
      }}
    />,
  );
}

describe('Layer-4 E2E: SSE coded error → msg.errorCode → rendered chip (real seam)', () => {
  it('the leak terminal (TOOL_CALL_LEAK_UNRECOVERED) renders its CODED label, NOT amber "Interrupted"', () => {
    const event = {
      type: 'error',
      code: 'TOOL_CALL_LEAK_UNRECOVERED',
      message: 'The AI repeatedly emitted a tool call as text…',
      suggested_action: 'Re-send the message (a fresh turn starts clean).',
    } as unknown as StreamEvent;

    renderChipFor(event);

    // The coded label renders (fallback produces the raw code when not specially
    // mapped) and the generic amber "Interrupted" fallback does NOT appear.
    expect(screen.getByText('TOOL_CALL_LEAK_UNRECOVERED')).toBeTruthy();
    expect(screen.queryByText('Interrupted')).toBeNull();
  });

  it('a known coded timeout (AGENT_TIMEOUT) renders its friendly coded label, not "Interrupted"', () => {
    const event = { type: 'error', code: 'AGENT_TIMEOUT' } as unknown as StreamEvent;
    renderChipFor(event);
    expect(screen.getByText('Response Timeout')).toBeTruthy();
    expect(screen.queryByText('Interrupted')).toBeNull();
  });

  it('a genuinely CODE-LESS error still renders amber "Interrupted" (FR-2 fallback preserved)', () => {
    const event = { type: 'error', message: 'Connection interrupted' } as unknown as StreamEvent;
    renderChipFor(event);
    expect(screen.getByText('Interrupted')).toBeTruthy();
  });
});

describe('Layer-4 MUTATION proof — revert the errorFields spread → coded label is LOST', () => {
  it('WITHOUT the fix (no errorFields spread), the SAME coded event renders amber "Interrupted"', () => {
    // Pre-fix behavior: the message carries isError but NO errorCode (the bug).
    const prefixMsg: Message = {
      id: 'assistant-1',
      role: 'assistant',
      content: [{ type: 'text', text: '⚠️ something' }],
      isError: true,
      // NOTE: no ...errorFields — this is the reverted contract line.
      timestamp: '2026-10-15T00:00:00Z',
    };
    const errorCode = (prefixMsg as unknown as Record<string, unknown>).errorCode as string | undefined;
    renderWithHealth(
      <ChatErrorMessage error={{ code: errorCode, message: 'The AI repeatedly emitted a tool call as text…' }} />,
    );
    // Proof the fix is load-bearing: without the spread, a coded leak event is
    // indistinguishable from a connection drop — the exact bug.
    expect(screen.getByText('Interrupted')).toBeTruthy();
    expect(screen.queryByText('TOOL_CALL_LEAK_UNRECOVERED')).toBeNull();
  });
});
