import type { InspectorTabId } from './inspectorPanel';

export type InspectorContextHint = {
  kind: 'candle' | 'range';
  title: string;
  detail: string;
};

export type InspectorContextRoute = {
  tab: InspectorTabId;
  markWorkspaceMode?: 'htf' | 'manual' | 'case';
  reason: string;
};

export function routeInspectorForCandleSelection(): InspectorContextRoute {
  return {
    tab: 'campaign',
    reason: 'candle-selected',
  };
}

export function routeInspectorForRangeSelection(): InspectorContextRoute {
  return {
    tab: 'gps',
    reason: 'range-selected',
  };
}

export function buildCandleSelectionHint(args: {
  timeLabel: string;
  price: number;
  timeframe: string;
}): InspectorContextHint {
  return {
    kind: 'candle',
    title: 'Candle selected',
    detail: `${args.timeLabel} · ${args.price.toFixed(2)} · ${args.timeframe}`,
  };
}

export function buildRangeSelectionHint(args: {
  rangeId: string;
  structureLayer: string;
  rangeScope?: string;
  rangeHigh?: string | number | null;
  rangeLow?: string | number | null;
}): InspectorContextHint {
  const hi = args.rangeHigh != null && args.rangeHigh !== '' ? String(args.rangeHigh) : '—';
  const lo = args.rangeLow != null && args.rangeLow !== '' ? String(args.rangeLow) : '—';
  const scope = args.rangeScope ? ` ${args.rangeScope}` : '';
  return {
    kind: 'range',
    title: `Range #${args.rangeId}`,
    detail: `${args.structureLayer}${scope} · RH ${hi} · RL ${lo}`,
  };
}
