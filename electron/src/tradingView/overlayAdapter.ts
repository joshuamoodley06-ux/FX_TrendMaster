import type { Time } from 'lightweight-charts';
import { fxtmTimeToTradingViewTime, timeSortKey } from './candleAdapter';
import type { TradingViewBosMarker, TradingViewFitRequest, TradingViewOverlaySet, TradingViewRangeLine } from './types';

type SavedRangeOverlayInput = {
  rangeId?: string | number | null;
  structureLayer?: string;
  rangeScope?: string;
  status?: string;
  high?: number;
  low?: number;
  start?: string | null;
  end?: string | null;
  isActive?: boolean;
  isParentContext?: boolean;
};

type ParentRangeOverlayInput = {
  rangeId?: string | number | null;
  structureLayer?: string;
  kind?: 'high' | 'low' | string;
  price?: number;
  label?: string;
};

type EventOverlayInput = {
  id?: string | number;
  event_type?: string;
  event_name?: string;
  derived_event_code?: string;
  time?: string;
  price?: number;
};

export type TradingViewOverlayAdapterInput = {
  timeframe: string;
  selectedRange?: unknown | null;
  savedRangeOverlays?: SavedRangeOverlayInput[];
  parentRangeOverlays?: ParentRangeOverlayInput[];
  visibleEvents?: EventOverlayInput[];
};

export type TradingViewFitAdapterInput = {
  token?: number;
  intent?: string;
  reason?: string;
  fitWindow?: { start?: string; end?: string } | null;
  targetTime?: string | null;
  timeframe: string;
};

const LAYER_COLORS: Record<string, string> = {
  MACRO: '#a855f7',
  WEEKLY: '#ef4444',
  DAILY: '#22c55e',
  INTRADAY: '#3b82f6',
  MICRO: '#facc15',
};

function finitePrice(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function rangeIdOf(value: any): string {
  return String(value?.rangeId ?? value?.range_id ?? value?.id ?? '');
}

function selectedRangeIds(selectedRange: unknown | null | undefined): Set<string> {
  const id = rangeIdOf(selectedRange);
  return id ? new Set([id]) : new Set<string>();
}

function lineStyleFor(range: SavedRangeOverlayInput): TradingViewRangeLine['lineStyle'] {
  const status = String(range.status || '').toUpperCase();
  if (status === 'BROKEN' || status === 'ABANDONED' || status === 'INACTIVE' || status === 'REPLACED') return 'dashed';
  if (String(range.rangeScope || '').toUpperCase() === 'MINOR') return 'dotted';
  return 'solid';
}

function rangeRole(range: SavedRangeOverlayInput, selectedIds: Set<string>): TradingViewRangeLine['role'] {
  const id = rangeIdOf(range);
  if ((id && selectedIds.has(id)) || range.isActive) return 'selected';
  if (range.isParentContext) return 'parent';
  return 'saved';
}

function rangeLineColor(layer: string | undefined, role: TradingViewRangeLine['role']): string {
  if (role === 'selected') return '#f8fafc';
  if (role === 'parent') return '#f59e0b';
  return LAYER_COLORS[String(layer || '').toUpperCase()] || '#94a3b8';
}

function addRangeLines(
  out: TradingViewRangeLine[],
  range: SavedRangeOverlayInput,
  selectedIds: Set<string>,
) {
  const high = finitePrice(range.high);
  const low = finitePrice(range.low);
  const id = rangeIdOf(range);
  const role = rangeRole(range, selectedIds);
  const layer = String(range.structureLayer || '').toUpperCase();
  const color = rangeLineColor(layer, role);
  const lineWidth = role === 'selected' ? 3 : role === 'parent' ? 2 : 1;
  const lineStyle = lineStyleFor(range);

  if (high !== null) {
    out.push({
      id: `${id || 'saved'}:RH`,
      rangeId: id || null,
      kind: 'RH',
      role,
      label: `${role === 'parent' ? 'Parent ' : ''}${layer || 'Range'} RH`,
      price: high,
      color,
      lineWidth,
      lineStyle,
    });
  }
  if (low !== null) {
    out.push({
      id: `${id || 'saved'}:RL`,
      rangeId: id || null,
      kind: 'RL',
      role,
      label: `${role === 'parent' ? 'Parent ' : ''}${layer || 'Range'} RL`,
      price: low,
      color,
      lineWidth,
      lineStyle,
    });
  }
}

function addParentLine(out: TradingViewRangeLine[], overlay: ParentRangeOverlayInput, index: number) {
  const price = finitePrice(overlay.price);
  if (price === null) return;
  const kind = String(overlay.kind || '').toLowerCase() === 'low' ? 'RL' : 'RH';
  const layer = String(overlay.structureLayer || '').toUpperCase();
  out.push({
    id: `parent:${rangeIdOf(overlay) || index}:${kind}`,
    rangeId: overlay.rangeId ?? null,
    kind,
    role: 'parent',
    label: overlay.label || `${layer || 'Parent'} ${kind}`,
    price,
    color: '#f59e0b',
    lineWidth: 2,
    lineStyle: 'dashed',
  });
}

function bosKind(event: EventOverlayInput): 'UP' | 'DOWN' | null {
  const raw = String(event.event_type || event.event_name || event.derived_event_code || '').toUpperCase();
  if (!raw.includes('BOS')) return null;
  if (raw.includes('DOWN')) return 'DOWN';
  if (raw.includes('UP')) return 'UP';
  return null;
}

function adaptBosMarker(event: EventOverlayInput, timeframe: string, index: number): TradingViewBosMarker | null {
  const direction = bosKind(event);
  if (!direction) return null;
  const time = fxtmTimeToTradingViewTime(event.time, timeframe);
  const price = finitePrice(event.price);
  if (!time || price === null) return null;
  return {
    id: String(event.id || `bos:${index}:${event.time}`),
    time,
    price,
    position: direction === 'UP' ? 'atPriceTop' : 'atPriceBottom',
    shape: direction === 'UP' ? 'arrowUp' : 'arrowDown',
    color: direction === 'UP' ? '#22c55e' : '#ef4444',
    text: `BOS ${direction}`,
    size: 1,
  };
}

export function adaptOverlaysForTradingView(input: TradingViewOverlayAdapterInput): TradingViewOverlaySet {
  const selectedIds = selectedRangeIds(input.selectedRange);
  const priceLines: TradingViewRangeLine[] = [];
  const lineIds = new Set<string>();

  for (const range of input.savedRangeOverlays || []) {
    addRangeLines(priceLines, range, selectedIds);
  }
  for (const [index, overlay] of (input.parentRangeOverlays || []).entries()) {
    addParentLine(priceLines, overlay, index);
  }

  const dedupedLines = priceLines.filter((line) => {
    const key = `${line.role}:${line.rangeId ?? ''}:${line.kind}:${line.price}`;
    if (lineIds.has(key)) return false;
    lineIds.add(key);
    return true;
  });

  const markers = (input.visibleEvents || [])
    .map((event, index) => adaptBosMarker(event, input.timeframe, index))
    .filter((marker): marker is TradingViewBosMarker => !!marker)
    .sort((a, b) => timeSortKey(a.time) - timeSortKey(b.time));

  return { priceLines: dedupedLines, markers };
}

export function adaptFitRequestForTradingView(input: TradingViewFitAdapterInput): TradingViewFitRequest | null {
  if (input.intent !== 'FIT_STRUCTURAL_RANGE') return null;
  const token = Number(input.token || 0);
  if (!Number.isFinite(token) || token <= 0) return null;
  const from = fxtmTimeToTradingViewTime(input.fitWindow?.start, input.timeframe);
  const to = fxtmTimeToTradingViewTime(input.fitWindow?.end, input.timeframe);
  const target = fxtmTimeToTradingViewTime(input.targetTime, input.timeframe);
  if (from && to) return { token, from, to, target: target || undefined };
  if (target) return { token, target };
  return null;
}
