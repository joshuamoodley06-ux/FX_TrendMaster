/** Hierarchy row jump helpers — chart TF, candle window target, range span fields. */

const LAYER_DEFAULT_TF: Record<string, string> = {
  MACRO: 'MN1',
  WEEKLY: 'W1',
  DAILY: 'D1',
  INTRADAY: 'H1',
  MICRO: 'M15',
};

export function normalizeNavLayer(value: unknown): string | null {
  const layer = String(value || '').trim().toUpperCase();
  if (layer === 'MACRO' || layer === 'WEEKLY' || layer === 'DAILY' || layer === 'INTRADAY' || layer === 'MICRO') {
    return layer;
  }
  return null;
}

export function isIntradayNavTimeframe(tf: string): boolean {
  const t = String(tf || '').toUpperCase();
  return t === 'H4' || t === 'H1' || t === 'M15' || t === 'M5';
}

export function resolveRangeChartTimeframe(range: any, fallbackTf: string): string {
  const layer = normalizeNavLayer(range?.structure_layer || range?.layer);
  const explicit = String(range?.chart_timeframe || range?.source_timeframe || range?.timeframe || '').toUpperCase();
  if (explicit && layer) {
    if (layer === 'INTRADAY' && (explicit === 'H4' || explicit === 'H1')) return explicit;
    if (layer === 'MICRO' && (explicit === 'M15' || explicit === 'M5')) return explicit;
    if (layer === 'WEEKLY' && explicit === 'W1') return explicit;
    if (layer === 'DAILY' && explicit === 'D1') return explicit;
    if (layer === 'MACRO' && (explicit === 'MN1' || explicit === 'W1')) return explicit;
  }
  if (explicit && !layer) return explicit;
  if (layer) return LAYER_DEFAULT_TF[layer] || 'D1';
  return String(fallbackTf || 'D1').toUpperCase();
}

export function rangeWindowFieldsFromSavedRange(range: any): { start: string; end: string } {
  const start = String(
    range?.range_start_time || range?.range_high_time || range?.active_from_time || '',
  );
  const end = String(
    range?.range_end_time || range?.range_low_time || start || '',
  );
  return { start, end: end || start };
}

/** Prefer the active range for candle window loading; fall back to parent context chain. */
export function resolveCandleWindowTargetRange(
  targetTf: string,
  savedRanges: any[],
  activeStructuralRangeId: string,
  selectedParentRangeId: string,
): any | null {
  const find = (id: string) => savedRanges.find((r) => String(r.range_id || r.id) === String(id)) || null;

  if (activeStructuralRangeId) {
    const active = find(activeStructuralRangeId);
    const activeLayer = normalizeNavLayer(active?.structure_layer || active?.layer);
    if (active && isIntradayNavTimeframe(targetTf) && (activeLayer === 'INTRADAY' || activeLayer === 'MICRO')) {
      return active;
    }
    if (active && isIntradayNavTimeframe(targetTf) && (activeLayer === 'DAILY' || activeLayer === 'WEEKLY' || activeLayer === 'MACRO')) {
      return active;
    }
    if (active && !isIntradayNavTimeframe(targetTf) && (activeLayer === 'DAILY' || activeLayer === 'WEEKLY' || activeLayer === 'MACRO')) {
      return active;
    }
  }

  if (selectedParentRangeId) {
    const parent = find(selectedParentRangeId);
    if (parent) return parent;
  }

  if (activeStructuralRangeId) {
    const active = find(activeStructuralRangeId);
    const activeLayer = normalizeNavLayer(active?.structure_layer || active?.layer);
    if (active && (activeLayer === 'INTRADAY' || activeLayer === 'MICRO')) {
      const pid = active.parent_range_id;
      if (pid !== null && pid !== undefined && String(pid) !== '') {
        return find(String(pid));
      }
    }
  }

  return null;
}

export const MIN_SAVED_RANGE_LINE_SPAN_PX = 96;

export function expandRangeSpanX(x1: number, x2: number, plotLeft: number, plotRight: number): { x1: number; x2: number } {
  const clampX = (x: number) => Math.max(plotLeft, Math.min(plotRight, x));
  const left = clampX(Math.min(x1, x2));
  const right = clampX(Math.max(x1, x2));
  if (right - left >= MIN_SAVED_RANGE_LINE_SPAN_PX) {
    return { x1: left, x2: right };
  }
  const mid = (left + right) / 2;
  const half = MIN_SAVED_RANGE_LINE_SPAN_PX / 2;
  return { x1: clampX(mid - half), x2: clampX(mid + half) };
}
