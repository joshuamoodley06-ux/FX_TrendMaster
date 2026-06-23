import { describe, expect, it } from 'vitest';
import { adaptFitRequestForTradingView, adaptOverlaysForTradingView } from './overlayAdapter';

describe('adaptOverlaysForTradingView', () => {
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
    expect(result.priceLines.find((line) => line.kind === 'RH')?.price).toBe(2420.25);
    expect(result.markers).toHaveLength(0);
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
});
