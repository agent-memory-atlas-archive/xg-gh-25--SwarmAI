/**
 * errorFields.ts — pure mapping from an SSE error StreamEvent to the error-code
 * fields a Message carries for rendering.
 *
 * Why this exists: the amber "Interrupted" chip rendered for EVERY backend error
 * because the SSE error-event handler set `isError: true` + text content but
 * NEVER copied the backend's `code`/`detail`/`suggested_action` onto the message.
 * `TabView` reads `msg.errorCode` → it was always `undefined` → `ChatErrorMessage`
 * fell to `error.code ?? 'Interrupted'` with `!error.code` forcing amber styling,
 * so a coded terminal like TOOL_CALL_LEAK_UNRECOVERED looked identical to a
 * generic connection drop.
 *
 * This helper is the single, testable mapping used by `applyError` in the error
 * handler. It mirrors the pure-function convention of `streaming-guards.ts` /
 * `blockKey` so it can be unit-tested in isolation (the handler itself lives in a
 * ~4000-line hook closure that is not directly testable).
 *
 * SNAKE/CAMEL REALITY (do not "simplify" away): `parseSSEEvent` camelCases only
 * `content` blocks, NOT top-level fields — so the backend's `_build_error_event`
 * `suggested_action` (snake) arrives as-is, while the StreamEvent type also
 * declares `suggestedAction` (camel). Read BOTH, camel first. `code`/`detail` have
 * no snake twin (the backend emits those keys verbatim).
 *
 * NOTE: there is deliberately NO `retryAfter` here — the generic error StreamEvent
 * carries no such field (it lives only on the separate RATE_LIMIT_EXCEEDED shape),
 * so reading `event.retryAfter` would be the exact always-undefined read this fix
 * exists to eliminate. QUEUE_TIMEOUT retry rides `event.retryPayload`, a separate
 * path handled elsewhere.
 */
import type { StreamEvent } from '../types';

export interface MessageErrorFields {
  errorCode?: string;
  errorDetail?: string;
  suggestedAction?: string;
}

/**
 * Extract the renderable error-code fields from an SSE error event.
 *
 * A genuinely code-less event yields `errorCode: undefined`, which preserves the
 * amber "Interrupted" fallback for real connection drops (FR-2). A coded event
 * surfaces its real code so `ChatErrorMessage` renders the correct label/severity.
 */
export function errorFieldsFromEvent(event: StreamEvent): MessageErrorFields {
  const snakeSuggested = (event as unknown as Record<string, unknown>)
    .suggested_action as string | undefined;
  return {
    errorCode: event.code,
    errorDetail: event.detail,
    suggestedAction: event.suggestedAction || snakeSuggested,
  };
}
