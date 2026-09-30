/**
 * Radar artifact API service layer.
 *
 * Provides read access to recently modified workspace artifacts for the Radar
 * sidebar's Artifacts section. (Todo operations live in services/todos.ts —
 * the single canonical Todo service.)
 *
 * Exports:
 * - radarService              — Object with the artifact fetch method
 * - artifactToCamelCase       — Converts backend snake_case artifact to RadarArtifact
 */

import api from './api';
import type { RadarArtifact } from '../pages/chat/components/RightSidebar/types';

// ---------------------------------------------------------------------------
// Artifact conversion helper (Spec — Right Sidebar Redesign)
// ---------------------------------------------------------------------------

/** Convert backend snake_case artifact response to frontend camelCase RadarArtifact. */
export function artifactToCamelCase(a: Record<string, unknown>): RadarArtifact {
  return {
    path: a.path as string,
    title: a.title as string,
    type: a.type as RadarArtifact['type'],
    modifiedAt: a.modified_at as string,
  };
}

/** Drift verdict for a Canvas/Artifacts row's backing file (Artifact-Lifecycle P0, ②). */
export interface DriftResult {
  dirty: boolean;
  reason: 'git-changed' | 'mtime-newer' | 'missing' | 'clean';
  currentRef?: string;
}

export const radarService = {
  /** Fetch recently modified artifacts from the workspace git tree. */
  async fetchRecentArtifacts(workspaceId: string, limit?: number): Promise<RadarArtifact[]> {
    const params = new URLSearchParams();
    params.append('workspace_id', workspaceId);
    params.append('limit', String(limit ?? 20));
    const response = await api.get(`/artifacts/recent?${params.toString()}`);
    return response.data.map(artifactToCamelCase);
  },

  /**
   * Check whether a row's backing file drifted since it was first seen (②).
   *
   * Pass the row's `baseRef` (sinceRef, for git-tracked rows) and/or `firstSeen`
   * (sinceMs, for untracked files). The backend is FAIL-SAFE — a git error or
   * uncomputable comparison returns `{dirty:false, reason:'clean'}`, never a false
   * dirty/missing. The caller MUST treat a rejected promise as "clean" too and
   * NEVER block opening the row on this check.
   */
  async fetchDrift(
    path: string,
    sinceRef?: string,
    sinceMs?: number,
  ): Promise<DriftResult> {
    const params = new URLSearchParams();
    params.append('path', path);
    if (sinceRef) params.append('since_ref', sinceRef);
    if (sinceMs != null) params.append('since_ms', String(sinceMs));
    const response = await api.get(`/artifacts/drift?${params.toString()}`);
    const d = response.data as Record<string, unknown>;
    return {
      dirty: Boolean(d.dirty),
      reason: d.reason as DriftResult['reason'],
      currentRef: (d.current_ref as string | null) ?? undefined,
    };
  },
};
