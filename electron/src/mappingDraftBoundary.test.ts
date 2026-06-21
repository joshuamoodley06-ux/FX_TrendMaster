import { describe, expect, it } from 'vitest';
import { createEmptyMappingDraft } from './hooks/useMappingDraft';
import {
  detectBoundaryOverflow,
  findRelinkCandidateTimeframes,
  withDraftBoundary,
} from './mappingDraftBoundary';

describe('detectBoundaryOverflow', () => {
  it('flags overflow when child end exceeds parent end', () => {
    const parent = withDraftBoundary({
      ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'W1' }),
      points: [{ id: '1', time: '2024-01-01T00:00:00.000Z', price: 2000, kind: 'pivot', createdAt: '' }],
    });
    const child = withDraftBoundary({
      ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'D1' }),
      points: [{ id: '2', time: '2024-06-01T00:00:00.000Z', price: 2100, kind: 'pivot', createdAt: '' }],
    });
    expect(detectBoundaryOverflow(child, parent)).toBe(true);
  });

  it('is false when child stays inside parent span', () => {
    const parent = withDraftBoundary({
      ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'W1' }),
      points: [{ id: '1', time: '2024-12-01T00:00:00.000Z', price: 2000, kind: 'pivot', createdAt: '' }],
    });
    const child = withDraftBoundary({
      ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'D1' }),
      points: [{ id: '2', time: '2024-06-01T00:00:00.000Z', price: 2100, kind: 'pivot', createdAt: '' }],
    });
    expect(detectBoundaryOverflow(child, parent)).toBe(false);
  });
});

describe('findRelinkCandidateTimeframes', () => {
  it('returns higher timeframes whose draft end covers child end', () => {
    const drafts = {
      W1: withDraftBoundary({
        ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'W1' }),
        points: [{ id: '1', time: '2024-12-31T00:00:00.000Z', price: 2000, kind: 'pivot', createdAt: '' }],
      }),
      D1: withDraftBoundary({
        ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'D1' }),
        points: [{ id: '2', time: '2024-08-01T00:00:00.000Z', price: 2100, kind: 'pivot', createdAt: '' }],
      }),
    };
    expect(findRelinkCandidateTimeframes(drafts, 'D1', drafts.D1.endTime)).toEqual(['W1']);
  });
});

describe('withDraftBoundary', () => {
  it('preserves manually extended endTime beyond point span', () => {
    const extended = withDraftBoundary({
      ...createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'W1' }),
      points: [{ id: '1', time: '2024-01-01T00:00:00.000Z', price: 2000, kind: 'pivot', createdAt: '' }],
      endTime: '2024-12-31T00:00:00.000Z',
    });
    expect(extended.endTime).toBe('2024-12-31T00:00:00.000Z');
  });
});
