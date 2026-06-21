/** Mapping campaign training replay — no future candles (closed-book mapping). */

export type MappingTrainingReplayStart = {
  startTime: string;
  source: 'parent_start' | 'guided_cursor';
};

export function isMappingTrainingReplayActive(
  childMappingSession: unknown | null,
  guidedCursor: { active?: boolean } | null,
): boolean {
  return !!childMappingSession || !!guidedCursor?.active;
}

export function resolveParentRangeStartTime(parent: Record<string, unknown>): string {
  const raw = parent.range_start_time
    || parent.active_from_time
    || parent.range_high_time
    || parent.range_low_time
    || '';
  return String(raw || '').trim();
}

export function resolveMappingTrainingReplayStart(
  parent: Record<string, unknown>,
  guidedCursor?: { cursor_time_ms?: number | null } | null,
): MappingTrainingReplayStart | null {
  const parentStart = resolveParentRangeStartTime(parent);
  if (parentStart) {
    return { startTime: parentStart, source: 'parent_start' };
  }
  if (guidedCursor?.cursor_time_ms != null && Number.isFinite(guidedCursor.cursor_time_ms)) {
    return {
      startTime: new Date(guidedCursor.cursor_time_ms).toISOString(),
      source: 'guided_cursor',
    };
  }
  return null;
}

function parseTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const raw = String(value).trim();
  const ms = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : null;
}

const DEFAULT_RESEARCH_LOOKBACK_BARS = 100;

/** Keep candles for mapping — preserve left context; allow modest extension past parent end. */
export function trimCandlesToResearchWindow<T extends { time: string }>(
  candles: T[],
  startDay: string,
  endDay: string,
  timeframe = 'D1',
): T[] {
  if (!candles.length || !startDay) return candles;
  const startMs = parseTimeMs(startDay.includes('T') ? startDay : `${startDay}T00:00:00.000Z`);
  const endMsRaw = parseTimeMs((endDay || startDay).includes('T') ? (endDay || startDay) : `${endDay || startDay}T23:59:59.000Z`);
  if (startMs === null) return candles;
  const endMs = endMsRaw ?? startMs;
  const tf = String(timeframe || 'D1').toUpperCase();
  const barMs = tf === 'M15' || tf === 'M5' ? 15 * 60 * 1000
    : tf === 'H1' ? 60 * 60 * 1000
      : tf === 'H4' ? 4 * 60 * 60 * 1000
        : tf === 'W1' ? 7 * 24 * 60 * 60 * 1000
          : 24 * 60 * 60 * 1000;
  const lo = startMs - DEFAULT_RESEARCH_LOOKBACK_BARS * barMs;
  const hi = endMs + 14 * 24 * 3600 * 1000;
  return candles.filter((c) => {
    const ms = parseTimeMs(c.time);
    return ms !== null && ms >= lo && ms <= hi;
  });
}

/** Bootstrap replay at parent start — never snap forward to latest when history starts later. */
export function replayBootstrapIndex<T extends { time: string }>(
  candles: T[],
  targetTime: string | null | undefined,
): number {
  if (!candles.length) return 0;
  if (!targetTime) return 0;
  const cut = parseTimeMs(targetTime);
  if (cut === null) return 0;
  let idx = -1;
  for (let i = 0; i < candles.length; i += 1) {
    const ms = parseTimeMs(candles[i].time);
    if (ms !== null && ms <= cut) idx = i;
    if (ms !== null && ms > cut) break;
  }
  return Math.max(0, idx >= 0 ? idx : 0);
}

export function filterCandlesToReplayCut<T extends { time: string }>(
  candles: T[],
  replayTime: string | null | undefined,
): T[] {
  if (!replayTime || !candles.length) return candles;
  const cut = Date.parse(String(replayTime));
  if (!Number.isFinite(cut)) return candles;
  return candles.filter((c) => {
    const ms = Date.parse(String(c.time));
    return Number.isFinite(ms) && ms <= cut;
  });
}

export function filterEventsToReplayCut<T extends { time?: string | null }>(
  events: T[],
  replayTime: string | null | undefined,
): T[] {
  if (!replayTime) return events;
  const cut = Date.parse(String(replayTime));
  if (!Number.isFinite(cut)) return events;
  return events.filter((e) => {
    if (!e.time) return true;
    const ms = Date.parse(String(e.time));
    return !Number.isFinite(ms) || ms <= cut;
  });
}
