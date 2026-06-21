import { describe, expect, it } from 'vitest';
import {
  childSpanExceedsParentCampaign,
  isAutoChainSameParentCampaign,
  isParentActiveForChildMapping,
  validateHierarchyIntegrity,
  validateParentEligibleForChildMapping,
} from './hierarchyIntegrity';
import { buildGuidedCursorFromParent, markGuidedParentComplete } from './guidedMappingCursor';

describe('hierarchyIntegrity', () => {
  const weekly = {
    range_id: 7,
    structure_layer: 'WEEKLY',
    range_scope: 'MAJOR',
    status: 'ACTIVE',
    range_start_time: '2025-03-01T00:00:00.000Z',
    range_end_time: '2025-06-15T00:00:00.000Z',
  };

  it('detects child span outside weekly campaign window', () => {
    const exceeds = childSpanExceedsParentCampaign(weekly, {
      range_start_time: '2025-02-01T00:00:00.000Z',
      range_end_time: '2025-03-10T00:00:00.000Z',
    });
    expect(exceeds).toBe(true);
  });

  it('allows child exceeding weekly window (soft validation in campaignFlexibility)', () => {
    const result = validateHierarchyIntegrity({
      childLayer: 'DAILY',
      rangeScope: 'MAJOR',
      parentId: 7,
      savedRanges: [weekly],
      childSpan: {
        range_start_time: '2025-07-01T00:00:00.000Z',
        range_end_time: '2025-07-05T00:00:00.000Z',
      },
    });
    expect(result.ok).toBe(true);
  });

  it('allows child inside parent window', () => {
    const result = validateHierarchyIntegrity({
      childLayer: 'DAILY',
      rangeScope: 'MAJOR',
      parentId: 7,
      savedRanges: [weekly],
      childSpan: {
        range_start_time: '2025-03-10T00:00:00.000Z',
        range_end_time: '2025-03-20T00:00:00.000Z',
      },
    });
    expect(result.ok).toBe(true);
  });

  it('exempts auto-chain when same parent campaign', () => {
    expect(isAutoChainSameParentCampaign({
      autoChain: true,
      chainDraftMode: true,
      parentId: 7,
      chainParentCampaignId: 7,
    })).toBe(true);

    const result = validateHierarchyIntegrity({
      childLayer: 'DAILY',
      rangeScope: 'MAJOR',
      parentId: 7,
      savedRanges: [weekly],
      autoChain: true,
      chainDraftMode: true,
      chainParentCampaignId: 7,
      childSpan: {
        range_start_time: '2025-07-01T00:00:00.000Z',
        range_end_time: '2025-07-05T00:00:00.000Z',
      },
    });
    expect(result.ok).toBe(true);
  });

  it('rejects inactive parents for child mapping', () => {
    expect(isParentActiveForChildMapping({ ...weekly, status: 'BROKEN' })).toBe(false);
    const result = validateParentEligibleForChildMapping({ ...weekly, status: 'ARCHIVED' });
    expect(result.ok).toBe(false);
  });

  it('rejects child work when guided parent campaign is closed', () => {
    const cursor = markGuidedParentComplete(buildGuidedCursorFromParent(weekly, '2025'));
    const result = validateParentEligibleForChildMapping(weekly, cursor);
    expect(result.ok).toBe(false);
  });
});
