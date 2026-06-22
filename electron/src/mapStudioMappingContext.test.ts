import { describe, expect, it } from 'vitest';
import { buildSkeletonMappingStatusLine, hasMappingSkeletonContext } from './mapStudioMappingContext';

describe('mapStudioMappingContext', () => {
  it('requires case plus hierarchy/campaign context', () => {
    expect(hasMappingSkeletonContext({
      hasCase: false,
      activeStructuralRangeId: '1',
      selectedParentRangeId: '',
      guidedCursorActive: false,
      childMappingSessionActive: false,
    })).toBe(false);
    expect(hasMappingSkeletonContext({
      hasCase: true,
      activeStructuralRangeId: '',
      selectedParentRangeId: '394',
      guidedCursorActive: false,
      childMappingSessionActive: false,
    })).toBe(true);
  });

  it('builds candle-first status line', () => {
    const line = buildSkeletonMappingStatusLine({
      selectedTimeLabel: '2024-11-14',
      timeframe: 'D1',
      structureLayer: 'DAILY',
      activeRangeId: '399',
      parentRangeId: '394',
      rhSet: true,
      rlSet: true,
      chainDraftMode: false,
      rangeSynced: true,
      lastMessage: '',
      structuralSaving: false,
    });
    expect(line).toContain('2024-11-14');
    expect(line).toContain('H = RH');
  });
});
