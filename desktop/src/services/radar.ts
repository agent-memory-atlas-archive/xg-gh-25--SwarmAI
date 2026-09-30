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

/** The closed role set (mirrors backend product_registry.Role — Artifacts B′ Run 2).
 *  `Other` is dropped at write time so it never reaches the frontend, but keep it in
 *  the union so an unexpected value stays typed (defensive render fallback). */
export type ProductRole = 'Deliverables' | 'Knowledge' | 'Pipeline' | 'Activity' | 'Other';

/** One product from the workspace product registry (Artifacts B′ Run 2, AC1).
 *  The role-typed source the Artifacts overlay projects from — replaces the git-log
 *  RadarArtifact view so gitignored decks surface. ROLE is computed ONCE in the backend
 *  (product_registry.derive_role); the frontend renders it, NEVER re-derives (run_4de279ca).
 *  Backend ProductResponse already emits camelCase, so this is a typed passthrough — no
 *  snake→camel mapper (unlike artifactToCamelCase, which only maps modified_at). */
export interface Product {
  path: string;
  role: ProductRole;
  kind: string;
  gitignored: boolean;
  firstProduced: string;
  lastTouched: string;
  /** Run-3 AC8: human label — task name for Pipeline rows, basename otherwise.
   *  OPTIONAL by type (Gate-2 meta Finding 3): the current backend always emits it,
   *  but the overlay handles its absence defensively (`p.displayLabel || fallback`),
   *  so an old-backend / rolled-back response degrades gracefully. The type matches
   *  that runtime contract rather than lying about a hard requirement. */
  displayLabel?: string;
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

  /** Fetch the workspace PRODUCT registry, role-typed (Artifacts B′ Run 2, AC1).
   *  The overlay's source — includes gitignored decks the git-log view could not see.
   *  Backend already emits camelCase; response is a typed passthrough. */
  async fetchProducts(workspaceId: string): Promise<Product[]> {
    const params = new URLSearchParams();
    params.append('workspace_id', workspaceId);
    const response = await api.get(`/artifacts/products?${params.toString()}`);
    return response.data as Product[];
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
