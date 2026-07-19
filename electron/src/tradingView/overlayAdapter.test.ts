import { describe, expect, it } from 'vitest';
import { adaptFitRequestForTradingView, adaptOverlaysForTradingView, TRADINGVIEW_LAYER_COLORS } from './overlayAdapter';

const LAYER_COLORS = TRADINGVIEW_LAYER_COLORS;
const LAYERS = ['MACRO', 'WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'] as const;
const ROLES = [
  { name: 'selected', isActive: true },
  { name: 'saved', isActive: false },
  { name: 'parent', isParentContext: true },
] as const;

describe('adaptOverlaysForTradingView', () => {
  it.each([
    ['RL first', '2024.11.04 12:00', '2024.11.04 08:00'],
    ['RH first', '2024.11.04 08:00', '2024.11.04 12:00'],
  ])('bounds both RH/RL to the ordered factual anchors when %s', (_name, rhTime, rlTime) => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      savedRangeOverlays: [{ rangeId: 'r1', high: 2500, low: 2400, start: rhTime, end: rlTime }],
    });
    expect(result.priceLines).toHaveLength(2);
    expect(result.priceLines.every((line) => line.renderMode === 'SEGMENT')).toBe(true);
    expect(new Set(result.priceLines.map((line) => line.startTime))).toEqual(new Set([Date.UTC(2024, 10, 4, 8) / 1000]));
    expect(new Set(result.priceLines.map((line) => line.endTime))).toEqual(new Set([Date.UTC(2024, 10, 4, 12) / 1000]));
  });

  it('keeps invalid anchor levels as explicit fallbacks with debug IDs', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      savedRangeOverlays: [{ rangeId: 'bad', high: 2500, low: 2400, start: 'bad', end: null }],
    });
    expect(result.priceLines.every((line) => line.renderMode === 'PRICE_LINE_FALLBACK')).toBe(true);
    expect(result.debug?.priceLineFallbackIds).toEqual(['bad:RH', 'bad:RL']);
  });
  it.each(LAYERS.flatMap((layer) => ROLES.map((role) => ({ layer, role }))))(
    'uses layer hue for $layer $role.name lines',
    ({ layer, role }) => {
      const result = adaptOverlaysForTradingView({
        timeframe: 'H1',
        savedRangeOverlays: [{
          rangeId: `r-${layer}-${role.name}`,
          structureLayer: layer,
          rangeScope: 'MAJOR',
          status: 'ACTIVE',
          high: 2500,
          low: 2400,
          isActive: 'isActive' in role ? role.isActive : false,
          isParentContext: 'isParentContext' in role ? role.isParentContext : false,
        }],
      });

      expect(result.priceLines).toHaveLength(2);
      expect(result.priceLines.every((line) => line.color === LAYER_COLORS[layer])).toBe(true);
    },
  );

  it('active DAILY selected is green, not white', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      selectedRange: { range_id: 'r1' },
      savedRangeOverlays: [{
        rangeId: 'r1',
        structureLayer: 'DAILY',
        rangeScope: 'MAJOR',
        status: 'ACTIVE',
        high: 2420.25,
        low: 2388.5,
        isActive: true,
      }],
    });

    expect(result.priceLines.every((line) => line.role === 'selected')).toBe(true);
    expect(result.priceLines.every((line) => line.color === LAYER_COLORS.DAILY)).toBe(true);
    expect(result.priceLines.every((line) => line.color !== '#f8fafc')).toBe(true);
    expect(result.priceLines.find((line) => line.kind === 'RH')?.lineWidth).toBe(3);
  });

  it('parent WEEKLY lines are red, not orange', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      parentRangeOverlays: [
        { rangeId: 'p1', structureLayer: 'WEEKLY', kind: 'high', price: 2500, label: 'Parent WEEKLY RH' },
        { rangeId: 'p1', structureLayer: 'WEEKLY', kind: 'low', price: 2300, label: 'Parent WEEKLY RL' },
      ],
    });

    expect(result.priceLines).toHaveLength(2);
    expect(result.priceLines.every((line) => line.role === 'parent')).toBe(true);
    expect(result.priceLines.every((line) => line.color === LAYER_COLORS.WEEKLY)).toBe(true);
    expect(result.priceLines.every((line) => line.color !== '#f59e0b')).toBe(true);
    expect(result.priceLines.every((line) => line.lineStyle === 'dashed')).toBe(true);
    expect(result.priceLines.every((line) => line.lineWidth === 2)).toBe(true);
  });

  it('mirrors selected range RH/RL as read-only price lines', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      selectedRange: { range_id: 'r1' },
      savedRangeOverlays: [{
        rangeId: 'r1',
        structureLayer: 'DAILY',
        rangeScope: 'MAJOR',
        status: 'ACTIVE',
        high: 2420.25,
        low: 2388.5,
        isActive: true,
      }],
    });

    expect(result.priceLines).toHaveLength(2);
    expect(result.priceLines.map((line) => line.kind).sort()).toEqual(['RH', 'RL']);
    expect(result.priceLines.every((line) => line.role === 'selected')).toBe(true);
    expect(result.priceLines.every((line) => line.color === LAYER_COLORS.DAILY)).toBe(true);
    expect(result.priceLines.find((line) => line.kind === 'RH')?.price).toBe(2420.25);
    expect(result.markers).toHaveLength(0);
  });

  it('uses canonical weekly labels and exact canonical prices when provided by the selected overlay', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'W1',
      savedRangeOverlays: [{
        rangeId: 'mm:range:weekly-455',
        structureLayer: 'WEEKLY',
        rangeScope: 'MAJOR',
        status: 'BROKEN',
        customLabelPrefix: 'CANONICAL WEEKLY',
        high: 3418.42,
        low: 2955.1,
        isActive: true,
      }],
    });

    expect(result.priceLines).toHaveLength(2);
    expect(result.priceLines.find((line) => line.kind === 'RH')).toMatchObject({
      label: 'CANONICAL WEEKLY RH',
      price: 3418.42,
      role: 'selected',
    });
    expect(result.priceLines.find((line) => line.kind === 'RL')).toMatchObject({
      label: 'CANONICAL WEEKLY RL',
      price: 2955.1,
      role: 'selected',
    });
  });

  it('adds parent range overlays without duplicating identical lines', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      savedRangeOverlays: [{
        rangeId: 'p1',
        structureLayer: 'WEEKLY',
        rangeScope: 'MAJOR',
        status: 'ACTIVE',
        high: 2500,
        low: 2300,
        isParentContext: true,
      }],
      parentRangeOverlays: [
        { rangeId: 'p1', structureLayer: 'WEEKLY', kind: 'high', price: 2500, label: 'Weekly RH' },
        { rangeId: 'p1', structureLayer: 'WEEKLY', kind: 'low', price: 2300, label: 'Weekly RL' },
      ],
    });

    expect(result.priceLines).toHaveLength(2);
    expect(result.priceLines.every((line) => line.role === 'parent')).toBe(true);
    expect(result.priceLines.every((line) => line.color === LAYER_COLORS.WEEKLY)).toBe(true);
  });

  it('falls back to selected saved range prices when overlay list is empty', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      selectedRange: {
        range_id: 'selected-only',
        structure_layer: 'WEEKLY',
        range_scope: 'MAJOR',
        status: 'ACTIVE',
        range_high_price: 2790.01,
        range_low_price: 2602.55,
      },
      savedRangeOverlays: [],
    });

    expect(result.priceLines).toHaveLength(2);
    expect(result.priceLines.every((line) => line.role === 'selected')).toBe(true);
    expect(result.priceLines.every((line) => line.color === LAYER_COLORS.WEEKLY)).toBe(true);
    expect(result.priceLines.map((line) => line.price).sort()).toEqual([2602.55, 2790.01]);
  });

  it('converts BOS events into sorted TradingView markers', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      visibleEvents: [
        { id: 'b2', event_type: 'BOS_DOWN', time: '2024.11.04 10:00', price: 2390 },
        { id: 'x', event_type: 'RANGE_HIGH', time: '2024.11.04 09:00', price: 2410 },
        { id: 'b1', event_type: 'BOS_UP', time: '2024.11.04 08:00', price: 2420 },
      ],
    });

    expect(result.markers).toHaveLength(2);
    expect(result.markers.map((marker) => marker.id)).toEqual(['b1', 'b2']);
    expect(result.markers[0]).toMatchObject({ shape: 'arrowUp', position: 'atPriceTop', text: 'BOS UP' });
    expect(result.markers[1]).toMatchObject({ shape: 'arrowDown', position: 'atPriceBottom', text: 'BOS DOWN' });
  });

  it('drops BOS events without valid time or price', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      visibleEvents: [
        { id: 'bad-time', event_type: 'BOS_UP', time: 'bad', price: 1 },
        { id: 'bad-price', event_type: 'BOS_DOWN', time: '2024.11.04 08:00', price: Number.NaN },
      ],
    });

    expect(result.markers).toHaveLength(0);
  });

  it('suppresses all RH/RL guide lines when suppressRangeGuideLines is set', () => {
    const result = adaptOverlaysForTradingView({
      timeframe: 'H1',
      suppressRangeGuideLines: true,
      selectedRange: {
        range_id: 'selected-only',
        structure_layer: 'WEEKLY',
        range_high_price: 2790.01,
        range_low_price: 2602.55,
      },
      savedRangeOverlays: [{
        rangeId: 'r1',
        structureLayer: 'DAILY',
        high: 2420.25,
        low: 2388.5,
        isActive: true,
      }],
      parentRangeOverlays: [
        { rangeId: 'p1', structureLayer: 'WEEKLY', kind: 'high', price: 2500, label: 'Weekly RH' },
      ],
      draftRangeOverlay: {
        high: 2410.5,
        low: 2388.25,
        structureLayer: 'DAILY',
        visible: true,
      },
      visibleEvents: [
        { id: 'b1', event_type: 'BOS_UP', time: '2024.11.04 08:00', price: 2420 },
      ],
    });

    expect(result.priceLines).toHaveLength(0);
    expect(result.debug.rhRlLineCount).toBe(0);
    expect(result.debug.selectedRangeFallbackUsed).toBe(false);
    expect(result.markers).toHaveLength(1);
  });

  it('emits draft RH/RL price lines from draft overlay and anchor fallbacks', () => {
    const partial = adaptOverlaysForTradingView({
      timeframe: 'H1',
      draftRangeOverlay: {
        high: 2410.5,
        low: null,
        structureLayer: 'DAILY',
        visible: true,
        start: '2024.11.04 09:00',
        end: '2024.11.04 09:00',
      },
    });
    expect(partial.priceLines).toHaveLength(1);
    expect(partial.priceLines[0]).toMatchObject({
      id: 'draft:RH',
      kind: 'RH',
      price: 2410.5,
      color: LAYER_COLORS.DAILY,
      lineStyle: 'dashed',
      label: 'Draft DAILY RH',
      renderMode: 'PRICE_LINE_FALLBACK',
    });

    const complete = adaptOverlaysForTradingView({
      timeframe: 'H1',
      draftRhAnchor: { price: '2410.50', time: '2024.11.04 09:00' },
      draftRlAnchor: { price: '2388.25', time: '2024.11.04 08:00' },
      draftRangeOverlay: {
        high: 2410.5,
        low: 2388.25,
        structureLayer: 'DAILY',
        visible: true,
        start: '2024.11.04 09:00',
        end: '2024.11.04 08:00',
      },
    });
    expect(complete.priceLines.map((line) => line.id).sort()).toEqual(['draft:RH', 'draft:RL']);
    expect(complete.priceLines.every((line) => line.lineStyle === 'solid')).toBe(true);
    expect(complete.priceLines.every((line) => line.renderMode === 'SEGMENT')).toBe(true);
  });
});

describe('adaptFitRequestForTradingView', () => {
  it('adapts explicit structural fit camera commands only', () => {
    const ignored = adaptFitRequestForTradingView({
      token: 1,
      intent: 'FIT_ALL',
      timeframe: 'H1',
      fitWindow: { start: '2024.11.04 08:00', end: '2024.11.04 12:00' },
    });

    const fit = adaptFitRequestForTradingView({
      token: 2,
      intent: 'FIT_STRUCTURAL_RANGE',
      timeframe: 'H1',
      fitWindow: { start: '2024.11.04 08:00', end: '2024.11.04 12:00' },
      targetTime: '2024.11.04 09:00',
    });

    expect(ignored).toBeNull();
    expect(fit?.token).toBe(2);
    expect(typeof fit?.from).toBe('number');
    expect(typeof fit?.to).toBe('number');
  });

  it('uses business-day fit times for weekly and daily chart windows', () => {
    const weekly = adaptFitRequestForTradingView({
      token: 3,
      intent: 'FIT_STRUCTURAL_RANGE',
      timeframe: 'W1',
      fitWindow: { start: '2024-11-04T00:00:00.000Z', end: '2024-12-02T00:00:00.000Z' },
    });
    const daily = adaptFitRequestForTradingView({
      token: 4,
      intent: 'FIT_STRUCTURAL_RANGE',
      timeframe: 'D1',
      fitWindow: { start: '2024.11.04 00:00', end: '2024.11.08 00:00' },
    });

    expect(weekly?.from).toEqual({ year: 2024, month: 11, day: 4 });
    expect(weekly?.to).toEqual({ year: 2024, month: 12, day: 2 });
    expect(daily?.from).toEqual({ year: 2024, month: 11, day: 4 });
    expect(daily?.to).toEqual({ year: 2024, month: 11, day: 8 });
  });

  it('uses Unix-second fit times for intraday chart windows', () => {
    const fit = adaptFitRequestForTradingView({
      token: 5,
      intent: 'FIT_STRUCTURAL_RANGE',
      timeframe: 'M15',
      fitWindow: { start: '2024.11.04 08:15', end: '2024.11.04 12:45' },
    });

    expect(fit?.from).toBe(Date.UTC(2024, 10, 4, 8, 15, 0) / 1000);
    expect(fit?.to).toBe(Date.UTC(2024, 10, 4, 12, 45, 0) / 1000);
  });
});
