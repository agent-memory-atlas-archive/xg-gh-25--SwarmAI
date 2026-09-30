/**
 * radar service — HTTP-boundary array contract.
 *
 * Why this file exists (regression guard, CI-red 2026-09-30): the Artifacts overlay
 * crashed `all.filter is not a function` in the OverlayHost E2E because
 * `fetchProducts` did `return response.data as Product[]` — a bare TS cast with NO
 * runtime validation. When `api.get` resolved to a NON-array body (the E2E mocks it
 * to `{ data: {} }`), `data` became `{}`, the consumer's `data ?? []` guard did not
 * fire (an object is not null), and `{}.filter(...)` threw. `fetchRecentArtifacts`
 * had the identical latent bug (`response.data.map`).
 *
 * These tests pin the boundary contract: both fetchers MUST return an array even when
 * the backend/mock returns a non-array — honoring their `Promise<T[]>` signature so no
 * consumer can be handed a non-iterable. This is the "serialization boundary = runtime
 * validation, never trust the TS cast across an HTTP boundary" class (O023/COE10/LL22).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import api from '../api';
import { radarService } from '../radar';

const mockApi = api as unknown as { get: ReturnType<typeof vi.fn> };

describe('radarService — HTTP-boundary array contract', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('fetchProducts honors Promise<Product[]> on a non-array body', () => {
    it('returns [] when the response body is an object ({})', async () => {
      mockApi.get.mockResolvedValue({ data: {} });
      const out = await radarService.fetchProducts('ws');
      expect(Array.isArray(out)).toBe(true);
      expect(out).toEqual([]);
    });

    it('returns [] when the response body is null', async () => {
      mockApi.get.mockResolvedValue({ data: null });
      const out = await radarService.fetchProducts('ws');
      expect(Array.isArray(out)).toBe(true);
    });

    it('passes a real array through unchanged', async () => {
      const rows = [{ path: 'a/b.html', role: 'Deliverables' }];
      mockApi.get.mockResolvedValue({ data: rows });
      const out = await radarService.fetchProducts('ws');
      expect(out).toEqual(rows);
    });
  });

  describe('fetchRecentArtifacts honors Promise<RadarArtifact[]> on a non-array body', () => {
    it('returns [] when the response body is an object ({})', async () => {
      mockApi.get.mockResolvedValue({ data: {} });
      const out = await radarService.fetchRecentArtifacts('ws');
      expect(Array.isArray(out)).toBe(true);
      expect(out).toEqual([]);
    });

    it('returns [] when the response body is null', async () => {
      mockApi.get.mockResolvedValue({ data: null });
      const out = await radarService.fetchRecentArtifacts('ws');
      expect(Array.isArray(out)).toBe(true);
    });
  });
});
