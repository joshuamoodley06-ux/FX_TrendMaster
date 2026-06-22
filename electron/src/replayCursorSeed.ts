/** Structural replay cursor validation + conditional restore (not blind seed). */

import { rangeWindowFieldsFromSavedRange } from './hierarchyRangeNavigation';
import { replayBootstrapIndex } from './mappingTrainingReplay';

export type ReplaySeedSource =
  | 'range_start'
  | 'guided_cursor'
  | 'load_window'
  | 'fallback_first';

export type ReplaySeedPlan = {
  seedTime: string | null;
  source: ReplaySeedSource;
  rangeId?: string | null;
};

export type ReplaySeedApplyResult = {
  index: number;
  time: string | null;
  playForwardEnabled: boolean;
  playForwardReason: string;
  source: ReplaySeedSource;
  seedAdjusted: boolean;
};

export type StructuralReplayScope = {
  symbol: string;
  caseId: string;
  timeframe: string;
  rangeId: string;
  loadWindowStart: string;
  loadWindowEnd: string;
};

export type ReplayCursorCandidateSource = 'scoped' | 'session' | 'none';

export type ReplayCursorValidationReason =
  | 'missing'
  | 'outside_window'
  | 'blocked_at_last_bar'
  | 'valid';

export type ReplayCursorRestoreDecision = {
  action: 'preserve' | 'initialize';
  reason: ReplayCursorValidationReason;
  candidateSource: ReplayCursorCandidateSource;
  scopeKey: string;
  index: number;
  time: string | null;
  playForwardEnabled: boolean;
  playForwardReason: string;
  seedPlan: ReplaySeedPlan;
  seedAdjusted: boolean;
};

function parseTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : null;
}

export function buildStructuralReplayScopeKey(scope: StructuralReplayScope): string {
  const sym = String(scope.symbol || '').toUpperCase();
  const caseId = String(scope.caseId || 'global');
  const tf = String(scope.timeframe || '').toUpperCase();
  const rangeId = String(scope.rangeId || '');
  const ws = String(scope.loadWindowStart || '');
  const we = String(scope.loadWindowEnd || '');
  return `${sym}|${caseId}|${tf}|${rangeId}|${ws}|${we}`;
}

/** True range start only — never RH/RL anchor times or range end. */
export function resolveStructuralReplayStartTime(
  range: Record<string, unknown> | null | undefined,
): string | null {
  if (!range) return null;
  const raw = range.range_start_time || range.active_from_time || '';
  const text = String(raw || '').trim();
  if (text) return text;
  const span = rangeWindowFieldsFromSavedRange(range);
  const start = String(span.start || '').trim();
  return start || null;
}

export function structuralRangeStartTime(range: Record<string, unknown> | null | undefined): string | null {
  return resolveStructuralReplayStartTime(range);
}

export function resolveStructuralReplaySeedPlan(args: {
  range?: Record<string, unknown> | null;
  guidedCursorTimeMs?: number | null;
  loadWindowStart?: string | null;
}): ReplaySeedPlan {
  if (args.guidedCursorTimeMs != null && Number.isFinite(args.guidedCursorTimeMs)) {
    return {
      seedTime: new Date(Number(args.guidedCursorTimeMs)).toISOString(),
      source: 'guided_cursor',
    };
  }
  const rangeStart = resolveStructuralReplayStartTime(args.range ?? null);
  if (rangeStart) {
    return {
      seedTime: rangeStart,
      source: 'range_start',
      rangeId: args.range ? String(args.range.range_id || args.range.id || '') : null,
    };
  }
  if (args.loadWindowStart) {
    const day = String(args.loadWindowStart).includes('T')
      ? String(args.loadWindowStart)
      : `${args.loadWindowStart}T00:00:00.000Z`;
    return { seedTime: day, source: 'load_window' };
  }
  return { seedTime: null, source: 'fallback_first' };
}

export function candleIndexAtOrBefore<T extends { time: string }>(
  candles: T[],
  time?: string | null,
): number {
  if (!candles.length || !time) return 0;
  const cut = parseTimeMs(time);
  if (cut === null) return 0;
  let idx = 0;
  for (let i = 0; i < candles.length; i += 1) {
    const ms = parseTimeMs(candles[i].time);
    if (ms !== null && ms <= cut) idx = i;
    if (ms !== null && ms > cut) break;
  }
  return idx;
}

export function isReplayCursorOutsideLoadedWindow<T extends { time: string }>(
  candles: T[],
  cursorTime: string | null | undefined,
): boolean {
  if (!cursorTime || !candles.length) return true;
  const ms = parseTimeMs(cursorTime);
  const first = parseTimeMs(candles[0].time);
  const last = parseTimeMs(candles[candles.length - 1].time);
  if (ms === null || first === null || last === null) return true;
  return ms < first || ms > last;
}

export function replayPlayForwardState<T extends { time: string }>(
  candles: T[],
  index: number,
  horizonExtendAvailable = false,
): { enabled: boolean; reason: string } {
  if (!candles.length) return { enabled: false, reason: 'no-candles' };
  const safe = Math.max(0, Math.min(index, candles.length - 1));
  const atLastLoaded = safe >= candles.length - 1;
  const enabled = candles.length > 1 && (!atLastLoaded || horizonExtendAvailable);
  return {
    enabled,
    reason: enabled
      ? 'ok'
      : (candles.length <= 1 ? 'single-bar-window' : 'at-last-bar-no-ahead'),
  };
}

/** When seed lands on the last bar, walk back so forward play is available. */
export function ensureReplayIndexAllowsForwardPlay<T extends { time: string }>(
  candles: T[],
  preferredIndex: number,
): { index: number; adjusted: boolean; reason: string } {
  if (!candles.length) return { index: 0, adjusted: false, reason: 'no-candles' };
  const safe = Math.max(0, Math.min(preferredIndex, candles.length - 1));
  const preferred = replayPlayForwardState(candles, safe);
  if (preferred.enabled) return { index: safe, adjusted: false, reason: 'ok' };
  if (candles.length <= 1) return { index: safe, adjusted: false, reason: 'single-bar-window' };
  for (let i = 0; i < candles.length - 1; i += 1) {
    const probe = replayPlayForwardState(candles, i);
    if (probe.enabled) return { index: i, adjusted: i !== safe, reason: 'seed-walkback' };
  }
  return { index: 0, adjusted: safe !== 0, reason: 'seed-walkback' };
}

export function validateReplayCursorForStructuralContext<T extends { time: string }>(
  candles: T[],
  cursorTime: string | null | undefined,
  candidateSource: ReplayCursorCandidateSource,
  horizonExtendAvailable = false,
): { valid: boolean; reason: ReplayCursorValidationReason; index: number } {
  if (!cursorTime || candidateSource === 'none') {
    return { valid: false, reason: 'missing', index: 0 };
  }
  if (isReplayCursorOutsideLoadedWindow(candles, cursorTime)) {
    return { valid: false, reason: 'outside_window', index: 0 };
  }
  const index = candleIndexAtOrBefore(candles, cursorTime);
  const { enabled, reason } = replayPlayForwardState(candles, index, horizonExtendAvailable);
  if (!enabled && reason === 'at-last-bar-no-ahead' && !horizonExtendAvailable) {
    return { valid: false, reason: 'blocked_at_last_bar', index };
  }
  void candidateSource;
  return { valid: true, reason: 'valid', index };
}

export function applyReplaySeedPlan<T extends { time: string }>(
  candles: T[],
  plan: ReplaySeedPlan,
): ReplaySeedApplyResult {
  if (!candles.length) {
    return {
      index: 0,
      time: null,
      playForwardEnabled: false,
      playForwardReason: 'no-candles',
      source: plan.source,
      seedAdjusted: false,
    };
  }
  const rawIndex = plan.seedTime
    ? replayBootstrapIndex(candles, plan.seedTime)
    : 0;
  const ensured = ensureReplayIndexAllowsForwardPlay(candles, rawIndex);
  const safe = ensured.index;
  const time = candles[safe]?.time ?? null;
  const play = replayPlayForwardState(candles, safe);
  return {
    index: safe,
    time,
    playForwardEnabled: play.enabled,
    playForwardReason: play.reason,
    source: plan.source,
    seedAdjusted: ensured.adjusted,
  };
}

export function resolveStructuralReplayRestore<T extends { time: string }>(args: {
  candles: T[];
  scope: StructuralReplayScope;
  scopedCursorTime?: string | null;
  sessionCursorTime?: string | null;
  range?: Record<string, unknown> | null;
  guidedCursorTimeMs?: number | null;
  /** Structural mapping may fetch the next chunk when replay reaches loaded horizon. */
  horizonExtendAvailable?: boolean;
}): ReplayCursorRestoreDecision {
  const horizonExtendAvailable = !!args.horizonExtendAvailable;
  const scopeKey = buildStructuralReplayScopeKey(args.scope);
  const seedPlan = resolveStructuralReplaySeedPlan({
    range: args.range,
    guidedCursorTimeMs: args.guidedCursorTimeMs,
    loadWindowStart: args.scope.loadWindowStart || null,
  });

  const candidates: Array<{ time: string | null; source: ReplayCursorCandidateSource }> = [];
  if (args.scopedCursorTime) {
    candidates.push({ time: args.scopedCursorTime, source: 'scoped' });
  }
  if (
    args.sessionCursorTime
    && args.sessionCursorTime !== args.scopedCursorTime
  ) {
    candidates.push({ time: args.sessionCursorTime, source: 'session' });
  }
  if (!candidates.length) {
    candidates.push({ time: null, source: 'none' });
  }

  for (const candidate of candidates) {
    const check = validateReplayCursorForStructuralContext(
      args.candles,
      candidate.time,
      candidate.source,
      horizonExtendAvailable,
    );
    if (check.valid && candidate.time) {
      const play = replayPlayForwardState(args.candles, check.index, horizonExtendAvailable);
      return {
        action: 'preserve',
        reason: 'valid',
        candidateSource: candidate.source,
        scopeKey,
        index: check.index,
        time: candidate.time,
        playForwardEnabled: play.enabled,
        playForwardReason: play.reason,
        seedPlan,
        seedAdjusted: false,
      };
    }
  }

  const invalidReason = candidates.length === 1 && candidates[0].source === 'none'
    ? 'missing'
    : (validateReplayCursorForStructuralContext(
      args.candles,
      candidates[0]?.time,
      candidates[0]?.source || 'none',
      horizonExtendAvailable,
    ).reason);

  const seeded = applyReplaySeedPlan(args.candles, seedPlan);
  return {
    action: 'initialize',
    reason: invalidReason,
    candidateSource: candidates[0]?.source || 'none',
    scopeKey,
    index: seeded.index,
    time: seeded.time,
    playForwardEnabled: seeded.playForwardEnabled,
    playForwardReason: seeded.playForwardReason,
    seedPlan,
    seedAdjusted: seeded.seedAdjusted,
  };
}

export function replayPlayForwardStatusMessage(reason: string): string {
  if (reason === 'ok') return '';
  if (reason === 'no-candles') return 'Replay blocked — no candles loaded.';
  if (reason === 'single-bar-window') return 'Play Forward blocked — only one candle in the loaded window.';
  if (reason === 'at-last-bar-no-ahead') return 'Play Forward blocked — replay is at the last loaded bar.';
  if (reason === 'no-loaded-candles-ahead') {
    return 'Play Forward blocked — no candles loaded ahead. Sync cache or step forward to fetch the next chunk.';
  }
  if (reason === 'loading-ahead') return 'Loading next replay chunk…';
  if (reason === 'seed-walkback') return '';
  return `Play Forward blocked — ${reason}.`;
}

export function replayRestoreStatusMessage(
  decision: Pick<ReplayCursorRestoreDecision, 'action' | 'reason' | 'candidateSource' | 'seedAdjusted'>,
): string {
  if (decision.action === 'preserve') return '';
  if (decision.reason === 'missing') return 'Replay initialized — no saved cursor for this range window.';
  if (decision.reason === 'outside_window') {
    return 'Replay initialized — prior cursor was outside the loaded candle window.';
  }
  if (decision.reason === 'blocked_at_last_bar') {
    return decision.candidateSource === 'scoped'
      ? 'Replay initialized — saved cursor was at the last bar with no forward play.'
      : 'Replay initialized — stale tail cursor at last bar replaced with range start.';
  }
  if (decision.seedAdjusted) return 'Replay initialized — seed adjusted so forward play is available.';
  return 'Replay initialized for structural mapping.';
}

/** @deprecated Prefer scoped validation; kept for tests migrating off naive tail checks. */
export function isStaleStoredReplayCursor(
  storedTime: string | null | undefined,
  seedTime: string | null | undefined,
): boolean {
  if (!storedTime) return false;
  if (!seedTime) return true;
  const storedMs = Date.parse(String(storedTime));
  const seedMs = Date.parse(String(seedTime));
  if (!Number.isFinite(storedMs) || !Number.isFinite(seedMs)) return true;
  return storedMs > seedMs;
}
