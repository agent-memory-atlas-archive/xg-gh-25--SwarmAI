/**
 * Tests for errorFields.ts — errorFieldsFromEvent pure helper.
 *
 * Methodology: pure-function unit tests. The bug this guards (the amber
 * "Interrupted" chip for EVERY backend error) was caused by the frontend
 * NEVER writing a message's `errorCode` field — so `ChatErrorMessage` always
 * fell to `error.code ?? 'Interrupted'` + `!error.code` → amber, regardless of
 * the coded error the backend actually sent (e.g. TOOL_CALL_LEAK_UNRECOVERED).
 *
 * The load-bearing assertions:
 * - a CODED error event maps `code` → `errorCode` (so the real coded label +
 *   non-amber styling render), and
 * - a genuinely CODE-LESS event yields `errorCode === undefined` (so the amber
 *   "Interrupted" fallback is preserved — FR-2).
 *
 * Also pins the snake/camel reality: the backend emits `suggested_action`
 * (snake, via `_build_error_event`) while the StreamEvent type carries
 * `suggestedAction` (camel) — the helper must read BOTH so neither source is
 * dropped at the SSE→message seam.
 */
import { describe, it, expect } from 'vitest';
import { errorFieldsFromEvent } from '../errorFields';
import type { StreamEvent } from '../../types';

describe('errorFieldsFromEvent', () => {
  it('CODED error event (the leak terminal) → errorCode is set (NOT amber Interrupted)', () => {
    const event = {
      type: 'error',
      code: 'TOOL_CALL_LEAK_UNRECOVERED',
      message: 'The AI repeatedly emitted a tool call as text…',
      detail: 'tool_call_leak: 2nd consecutive leak after corrective resume',
      suggested_action: 'Re-send the message (a fresh turn starts clean).',
    } as unknown as StreamEvent;

    const fields = errorFieldsFromEvent(event);

    expect(fields.errorCode).toBe('TOOL_CALL_LEAK_UNRECOVERED');
    expect(fields.errorDetail).toBe('tool_call_leak: 2nd consecutive leak after corrective resume');
    expect(fields.suggestedAction).toBe('Re-send the message (a fresh turn starts clean).');
  });

  it('CODE-LESS error event → errorCode undefined (amber "Interrupted" fallback preserved — FR-2)', () => {
    const event = {
      type: 'error',
      message: 'Connection interrupted — send your message again to continue.',
    } as unknown as StreamEvent;

    const fields = errorFieldsFromEvent(event);

    expect(fields.errorCode).toBeUndefined();
  });

  it('reads camelCase suggestedAction when the event carries it', () => {
    const event = {
      type: 'error',
      code: 'AGENT_TIMEOUT',
      suggestedAction: 'Your conversation is saved. Send your message again.',
    } as unknown as StreamEvent;

    const fields = errorFieldsFromEvent(event);

    expect(fields.errorCode).toBe('AGENT_TIMEOUT');
    expect(fields.suggestedAction).toBe('Your conversation is saved. Send your message again.');
  });

  it('prefers camelCase suggestedAction over snake suggested_action when both present', () => {
    const event = {
      type: 'error',
      code: 'SERVICE_UNAVAILABLE',
      suggestedAction: 'camel-wins',
      suggested_action: 'snake-loses',
    } as unknown as StreamEvent;

    const fields = errorFieldsFromEvent(event);
    expect(fields.suggestedAction).toBe('camel-wins');
  });

  it('a non-error event with no code yields no errorCode (defensive)', () => {
    const event = { type: 'assistant' } as unknown as StreamEvent;
    const fields = errorFieldsFromEvent(event);
    expect(fields.errorCode).toBeUndefined();
    expect(fields.errorDetail).toBeUndefined();
    expect(fields.suggestedAction).toBeUndefined();
  });
});
