import { describe, expect, it } from 'vitest';
import {
  parseStructuralTimeMs,
  candleIndexAtOrBefore,
  candleIndexNearest,
  buildCandleWindowFit,
  clampFitTimesToCandles,
  isPlausibleMarketTimeMs,
  candleDataExtent
} from './cameraUtils';
import { Candle } from '../types';

describe('cameraUtils', () => {
  const mockCandles: Candle[] = [
    { time: '2024-01-01T00:00:00.000Z', open: 1, high: 2, low: 0, close: 1.5 },
    { time: '2024-01-02T00:00:00.000Z', open: 1, high: 3, low: 0.5, close: 2 },
    { time: '2024-01-03T00:00:00.000Z', open: 2, high: 4, low: 1, close: 3 },
  ];

  it('parseStructuralTimeMs parses valid dates and MT5 format', () => {
    expect(parseStructuralTimeMs('2024-01-01')).toBe(new Date('2024-01-01T00:00:00.000Z').getTime());
    expect(parseStructuralTimeMs('2024-01-01T12:00:00.000Z')).toBe(new Date('2024-01-01T12:00:00.000Z').getTime());
    expect(parseStructuralTimeMs('2024.11.04 08:00')).toBe(1730707200000);
    expect(parseStructuralTimeMs('2024-11-04 08:00')).toBe(new Date('2024-11-04T08:00:00Z').getTime());
    expect(parseStructuralTimeMs('2024-11-04T08:00:00Z')).toBe(new Date('2024-11-04T08:00:00Z').getTime());
    expect(parseStructuralTimeMs('?')).toBeNull();
  });

  it('candleDataExtent calculates correct extent', () => {
    const ext = candleDataExtent(mockCandles);
    expect(ext?.start).toBe('2024-01-01T00:00:00.000Z');
    expect(ext?.end).toBe('2024-01-03T00:00:00.000Z');
  });

  it('isPlausibleMarketTimeMs handles plausible and implausible times', () => {
    const t1 = new Date('2024-01-02T00:00:00.000Z').getTime();
    const t2 = new Date('1980-01-01T00:00:00.000Z').getTime();
    expect(isPlausibleMarketTimeMs(t1, mockCandles)).toBe(true);
    expect(isPlausibleMarketTimeMs(t2, mockCandles)).toBe(false);
  });

  it('candleIndexAtOrBefore finds exact or previous index', () => {
    expect(candleIndexAtOrBefore(mockCandles, '2024-01-02T00:00:00.000Z')).toBe(1);
    expect(candleIndexAtOrBefore(mockCandles, '2024-01-02T12:00:00.000Z')).toBe(1);
    expect(candleIndexAtOrBefore(mockCandles, '2023-01-01T00:00:00.000Z')).toBe(0);
    expect(candleIndexAtOrBefore(mockCandles, '2025-01-01T00:00:00.000Z')).toBe(2);
  });

  it('candleIndexNearest finds closest index', () => {
    expect(candleIndexNearest(mockCandles, '2024-01-02T00:00:00.000Z')).toBe(1);
  });

  it('buildCandleWindowFit calculates correct fit window', () => {
    const fit = buildCandleWindowFit(mockCandles, '2024-01-02T00:00:00.000Z', 1);
    expect(fit?.start).toBe('2024-01-01T00:00:00.000Z');
    expect(fit?.end).toBe('2024-01-03T00:00:00.000Z');
    expect(fit?.low).toBe(0);
    expect(fit?.high).toBe(4);
  });

  it('clampFitTimesToCandles clamps times correctly', () => {
    const clamped = clampFitTimesToCandles('2023-01-01', '2025-01-01', mockCandles);
    expect(clamped.start).toBe('2024-01-01T00:00:00.000Z');
    expect(clamped.end).toBe('2024-01-03T00:00:00.000Z');
  });
});
