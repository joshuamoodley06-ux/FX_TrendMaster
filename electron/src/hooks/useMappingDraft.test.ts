import { describe, expect, it } from 'vitest';
import { createEmptyMappingDraft } from './useMappingDraft';

describe('createEmptyMappingDraft', () => {
  it('builds an empty draft scoped to symbol and timeframe', () => {
    const draft = createEmptyMappingDraft({ symbol: 'xauusd', timeframe: 'h4', caseId: 'case-1' });
    expect(draft.symbol).toBe('XAUUSD');
    expect(draft.timeframe).toBe('H4');
    expect(draft.caseId).toBe('case-1');
    expect(draft.points).toEqual([]);
  });
});

describe('multi-timeframe draft keys', () => {
  it('uses distinct timeframes without resetting symbol scope', () => {
    const w1 = createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'W1', caseId: 'case-1' });
    const d1 = createEmptyMappingDraft({ symbol: 'XAUUSD', timeframe: 'D1', caseId: 'case-1' });
    expect(w1.timeframe).toBe('W1');
    expect(d1.timeframe).toBe('D1');
    expect(w1.id).not.toBe(d1.id);
  });
});
