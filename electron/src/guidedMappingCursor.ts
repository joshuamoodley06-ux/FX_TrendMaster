/** Guided hierarchy mapping cursor — sequential child walk inside a parent range. */

import type { RangeAuditSample } from './reviewCandidateClient';

export type GuidedCursorStatus =
  | 'MAPPING_CHILD'
  | 'WAITING_FOR_BOS'
  | 'PARENT_COMPLETE'
  | 'MOVE_NEXT_SIBLING';

export type GuidedPendingBos = {
  direction: 'UP' | 'DOWN';
  time: string;
  price: number;
  candle?: Record<string, unknown> | null;
};

export type GuidedMappingCursor = {
  active: boolean;
  campaign_year: string;
  active_parent_range_id: string;
  active_parent_layer: string;
  active_child_layer: string;
  cursor_time_ms: number;
  parent_start_time_ms: number;
  parent_end_time_ms: number;
  parent_rh: number | null;
  parent_rl: number | null;
  current_child_range_id: string | null;
  current_child_index: number;
  cursor_status: GuidedCursorStatus;
  pending_bos: GuidedPendingBos | null;
  saved_child_ids: string[];
  /** When launched from a coverage gap, cap research window at this time. */
  coverage_gap_end_ms?: number | null;
};

export type GuidedResearchWindow = {
  start: string;
  end: string;
  dateFrom: string;
  dateTo: string;
};

function normalizeLayer(value: unknown): string {
  return String(value || '').trim().toUpperCase();
}

function parseTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : null;
}

function isoDay(value: unknown): string {
  const ms = parseTimeMs(value);
  if (ms === null) return '';
  return new Date(ms).toISOString().slice(0, 10);
}

function isMajorRange(range: Record<string, unknown>): boolean {
  return String(range.range_scope || 'MAJOR').toUpperCase() !== 'MINOR';
}

function isMappingActiveRange(range: Record<string, unknown>): boolean {
  const status = String(range.status || '').toUpperCase();
  return status !== 'ABANDONED' && status !== 'ARCHIVED';
}

function rangeStartSortKey(range: Record<string, unknown>): number {
  const ms = parseTimeMs(
    range.range_start_time || range.active_from_time || range.range_high_time || 0,
  );
  return ms ?? 0;
}

export function buildGuidedCursorFromParent(
  parentRange: Record<string, unknown>,
  campaignYear = 'all',
  cursorTimeMs?: number | null,
  coverageGapEndMs?: number | null,
): GuidedMappingCursor {
  const parentId = String(parentRange.range_id || parentRange.id || '').trim();
  const parentLayer = normalizeLayer(parentRange.structure_layer || parentRange.layer);
  const childLayer = ({
    MACRO: 'WEEKLY',
    WEEKLY: 'DAILY',
    DAILY: 'INTRADAY',
    INTRADAY: 'MICRO',
  } as Record<string, string>)[parentLayer] || 'DAILY';

  const startMs = parseTimeMs(
    parentRange.range_start_time || parentRange.active_from_time || parentRange.range_high_time,
  ) ?? 0;
  const endMs = parseTimeMs(
    parentRange.range_end_time || parentRange.range_low_time || parentRange.inactive_from_time,
  ) ?? startMs;

  const hi = Number(parentRange.range_high_price ?? parentRange.range_high);
  const lo = Number(parentRange.range_low_price ?? parentRange.range_low);

  const cursorMs = Number.isFinite(cursorTimeMs) && cursorTimeMs != null
    ? Math.max(startMs, Number(cursorTimeMs))
    : startMs;

  return {
    active: true,
    campaign_year: campaignYear,
    active_parent_range_id: parentId,
    active_parent_layer: parentLayer,
    active_child_layer: childLayer,
    cursor_time_ms: cursorMs,
    parent_start_time_ms: startMs,
    parent_end_time_ms: endMs,
    parent_rh: Number.isFinite(hi) ? hi : null,
    parent_rl: Number.isFinite(lo) ? lo : null,
    current_child_range_id: null,
    current_child_index: 0,
    cursor_status: 'MAPPING_CHILD',
    pending_bos: null,
    saved_child_ids: [],
    coverage_gap_end_ms: coverageGapEndMs ?? null,
  };
}

export function guidedCursorResearchWindow(cursor: GuidedMappingCursor): GuidedResearchWindow {
  const startMs = Math.max(cursor.parent_start_time_ms, cursor.cursor_time_ms);
  const cappedEnd = cursor.coverage_gap_end_ms != null
    ? Math.min(cursor.parent_end_time_ms, cursor.coverage_gap_end_ms)
    : cursor.parent_end_time_ms;
  const endMs = Math.max(cappedEnd, startMs);
  const start = new Date(startMs).toISOString();
  const end = new Date(Math.max(endMs, startMs)).toISOString();
  return {
    start,
    end,
    dateFrom: isoDay(start) || isoDay(end),
    dateTo: isoDay(end) || isoDay(start),
  };
}

export function isGuidedParentComplete(cursor: GuidedMappingCursor): boolean {
  return cursor.cursor_time_ms >= cursor.parent_end_time_ms;
}

export function formatGuidedCursorDate(cursor: GuidedMappingCursor): string {
  if (!cursor.cursor_time_ms) return '—';
  return new Date(cursor.cursor_time_ms).toISOString().slice(0, 10);
}

export function formatGuidedParentEndDate(cursor: GuidedMappingCursor): string {
  if (!cursor.parent_end_time_ms) return '—';
  return new Date(cursor.parent_end_time_ms).toISOString().slice(0, 10);
}

export function filterCandidatesAfterCursor(
  samples: RangeAuditSample[],
  cursorMs: number,
): RangeAuditSample[] {
  return samples.filter((sample) => {
    const raw = sample.range_start_time
      || sample.replay_until_time
      || sample.candle_time
      || sample.range_end_time
      || sample.suggested_rh_time;
    const ms = parseTimeMs(raw);
    return ms !== null && ms >= cursorMs;
  });
}

export function advanceGuidedCursorAfterChildSave(
  cursor: GuidedMappingCursor,
  saved: {
    rangeId: string;
    rangeEndTime?: string | null;
    bosTime?: string | null;
  },
): GuidedMappingCursor {
  const endMs = parseTimeMs(saved.rangeEndTime);
  const bosMs = parseTimeMs(saved.bosTime);
  const nextCursorMs = Math.max(
    cursor.cursor_time_ms,
    endMs ?? 0,
    bosMs ?? 0,
  );
  const parentComplete = nextCursorMs >= cursor.parent_end_time_ms;
  return {
    ...cursor,
    current_child_range_id: saved.rangeId,
    current_child_index: cursor.current_child_index + 1,
    cursor_time_ms: nextCursorMs,
    cursor_status: parentComplete ? 'PARENT_COMPLETE' : 'MAPPING_CHILD',
    pending_bos: null,
    saved_child_ids: [...cursor.saved_child_ids, saved.rangeId],
  };
}

export function skipGuidedCursorGap(cursor: GuidedMappingCursor, skipMs?: number): GuidedMappingCursor {
  const bump = skipMs ?? (24 * 3600 * 1000);
  const next = Math.min(cursor.parent_end_time_ms, cursor.cursor_time_ms + bump);
  const parentComplete = next >= cursor.parent_end_time_ms;
  return {
    ...cursor,
    cursor_time_ms: next,
    cursor_status: parentComplete ? 'PARENT_COMPLETE' : 'MAPPING_CHILD',
    pending_bos: null,
  };
}

export function markGuidedParentComplete(cursor: GuidedMappingCursor): GuidedMappingCursor {
  return {
    ...cursor,
    cursor_time_ms: cursor.parent_end_time_ms,
    cursor_status: 'PARENT_COMPLETE',
    pending_bos: null,
  };
}

export function withGuidedPendingBos(
  cursor: GuidedMappingCursor,
  bos: GuidedPendingBos | null,
): GuidedMappingCursor {
  return {
    ...cursor,
    pending_bos: bos,
    cursor_status: bos ? 'WAITING_FOR_BOS' : 'MAPPING_CHILD',
  };
}

export function findNextSiblingParent(
  currentParentId: string,
  parentLayer: string,
  ranges: Record<string, unknown>[],
): Record<string, unknown> | null {
  const layer = normalizeLayer(parentLayer);
  const siblings = ranges
    .filter((r) => normalizeLayer(r.structure_layer || r.layer) === layer && isMajorRange(r) && isMappingActiveRange(r))
    .sort(
      (a, b) =>
        rangeStartSortKey(a) - rangeStartSortKey(b)
        || String(a.range_id || a.id).localeCompare(String(b.range_id || b.id)),
    );
  const idx = siblings.findIndex((s) => String(s.range_id || s.id) === String(currentParentId));
  if (idx < 0) return null;

  const current = siblings[idx];
  const grandParentId = current.parent_range_id != null && String(current.parent_range_id) !== ''
    ? String(current.parent_range_id)
    : null;

  for (let i = idx + 1; i < siblings.length; i += 1) {
    const candidate = siblings[i];
    if (!grandParentId) return candidate;
    const pid = candidate.parent_range_id != null ? String(candidate.parent_range_id) : '';
    if (pid === grandParentId) return candidate;
  }
  return null;
}

export function bosDirectionFromCandidate(sample: RangeAuditSample | null): 'UP' | 'DOWN' | null {
  if (!sample) return null;
  const meta = sample.meta_json as Record<string, unknown> | undefined;
  const dir = String(
    sample.break_direction
    || sample.bos_direction
    || meta?.break_direction
    || meta?.bos_direction
    || '',
  ).toUpperCase();
  if (dir.includes('UP') || dir === 'HIGH') return 'UP';
  if (dir.includes('DOWN') || dir === 'LOW') return 'DOWN';
  return null;
}

export function guidedParentLineColor(parentLayer: string): string {
  const map: Record<string, string> = {
    WEEKLY: '#7f1d1d',
    DAILY: '#14532d',
    INTRADAY: '#1e3a8a',
    MACRO: '#581c87',
  };
  return map[normalizeLayer(parentLayer)] || '#475569';
}

export function guidedCursorToSessionFields(cursor: GuidedMappingCursor | null) {
  if (!cursor?.active) {
    return {
      guidedCursorActive: false,
      guidedCampaignYear: null,
      guidedParentRangeId: null,
      guidedParentLayer: null,
      guidedChildLayer: null,
      guidedCursorTimeMs: null,
      guidedParentStartMs: null,
      guidedParentEndMs: null,
      guidedParentRh: null,
      guidedParentRl: null,
      guidedCurrentChildRangeId: null,
      guidedCurrentChildIndex: 0,
      guidedCursorStatus: null,
      guidedPendingBosDirection: null,
      guidedPendingBosTime: null,
      guidedPendingBosPrice: null,
      guidedSavedChildIds: [] as string[],
    };
  }
  return {
    guidedCursorActive: true,
    guidedCampaignYear: cursor.campaign_year,
    guidedParentRangeId: cursor.active_parent_range_id,
    guidedParentLayer: cursor.active_parent_layer,
    guidedChildLayer: cursor.active_child_layer,
    guidedCursorTimeMs: cursor.cursor_time_ms,
    guidedParentStartMs: cursor.parent_start_time_ms,
    guidedParentEndMs: cursor.parent_end_time_ms,
    guidedParentRh: cursor.parent_rh,
    guidedParentRl: cursor.parent_rl,
    guidedCurrentChildRangeId: cursor.current_child_range_id,
    guidedCurrentChildIndex: cursor.current_child_index,
    guidedCursorStatus: cursor.cursor_status,
    guidedPendingBosDirection: cursor.pending_bos?.direction ?? null,
    guidedPendingBosTime: cursor.pending_bos?.time ?? null,
    guidedPendingBosPrice: cursor.pending_bos?.price ?? null,
    guidedSavedChildIds: cursor.saved_child_ids,
  };
}

export function guidedCursorFromSessionFields(stored: {
  guided_cursor_active?: boolean;
  guided_campaign_year?: string | null;
  guided_parent_range_id?: string | null;
  guided_parent_layer?: string | null;
  guided_child_layer?: string | null;
  guided_cursor_time_ms?: number | null;
  guided_parent_start_ms?: number | null;
  guided_parent_end_ms?: number | null;
  guided_parent_rh?: number | null;
  guided_parent_rl?: number | null;
  guided_current_child_range_id?: string | null;
  guided_current_child_index?: number;
  guided_cursor_status?: GuidedCursorStatus | null;
  guided_pending_bos_direction?: 'UP' | 'DOWN' | null;
  guided_pending_bos_time?: string | null;
  guided_pending_bos_price?: number | null;
  guided_saved_child_ids?: string[];
}): GuidedMappingCursor | null {
  if (!stored.guided_cursor_active || !stored.guided_parent_range_id) return null;
  const pending = stored.guided_pending_bos_direction && stored.guided_pending_bos_time
    ? {
      direction: stored.guided_pending_bos_direction,
      time: stored.guided_pending_bos_time,
      price: Number(stored.guided_pending_bos_price ?? 0),
    }
    : null;
  return {
    active: true,
    campaign_year: stored.guided_campaign_year || 'all',
    active_parent_range_id: String(stored.guided_parent_range_id),
    active_parent_layer: String(stored.guided_parent_layer || 'WEEKLY'),
    active_child_layer: String(stored.guided_child_layer || 'DAILY'),
    cursor_time_ms: Number(stored.guided_cursor_time_ms || 0),
    parent_start_time_ms: Number(stored.guided_parent_start_ms || 0),
    parent_end_time_ms: Number(stored.guided_parent_end_ms || 0),
    parent_rh: stored.guided_parent_rh ?? null,
    parent_rl: stored.guided_parent_rl ?? null,
    current_child_range_id: stored.guided_current_child_range_id
      ? String(stored.guided_current_child_range_id)
      : null,
    current_child_index: Number(stored.guided_current_child_index || 0),
    cursor_status: stored.guided_cursor_status || 'MAPPING_CHILD',
    pending_bos: pending,
    saved_child_ids: Array.isArray(stored.guided_saved_child_ids)
      ? stored.guided_saved_child_ids.map(String)
      : [],
  };
}
