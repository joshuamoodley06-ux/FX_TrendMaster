import { describe, expect, it } from 'vitest';
import {
  assessCampaignBoundaryCrossing,
  findAlternateParentCampaign,
  formatParentCampaignLabel,
  mergeCampaignFlexMeta,
} from './campaignFlexibility';

describe('campaignFlexibility', () => {
  const weeklyA = {
    range_id: 10,
    structure_layer: 'WEEKLY',
    range_scope: 'MAJOR',
    status: 'ACTIVE',
    range_start_time: '2025-03-01T00:00:00.000Z',
    range_end_time: '2025-03-07T00:00:00.000Z',
  };
  const weeklyB = {
    range_id: 11,
    structure_layer: 'WEEKLY',
    range_scope: 'MAJOR',
    status: 'ACTIVE',
    range_start_time: '2025-03-08T00:00:00.000Z',
    range_end_time: '2025-03-14T00:00:00.000Z',
  };

  it('formats parent campaign labels', () => {
    expect(formatParentCampaignLabel(weeklyA)).toContain('WEEKLY #10');
    expect(formatParentCampaignLabel(weeklyA)).toContain('2025-03-01');
  });

  it('finds next weekly when child overflows current parent end', () => {
    const alt = findAlternateParentCampaign({
      currentParent: weeklyA,
      childSpan: {
        range_start_time: '2025-03-05T00:00:00.000Z',
        range_end_time: '2025-03-10T00:00:00.000Z',
      },
      savedRanges: [weeklyA, weeklyB],
      childLayer: 'DAILY',
    });
    expect(alt).not.toBeNull();
    expect(String(alt?.range_id)).toBe('11');
  });

  it('assesses boundary crossing for daily major child', () => {
    const assessment = assessCampaignBoundaryCrossing({
      childLayer: 'DAILY',
      rangeScope: 'MAJOR',
      parentId: 10,
      savedRanges: [weeklyA, weeklyB],
      childSpan: {
        range_start_time: '2025-03-05T00:00:00.000Z',
        range_end_time: '2025-03-10T00:00:00.000Z',
      },
    });
    expect(assessment?.crosses).toBe(true);
    expect(assessment?.exceedsEnd).toBe(true);
    expect(String(assessment?.alternateParent?.range_id)).toBe('11');
  });

  it('returns null when child stays inside parent window', () => {
    const assessment = assessCampaignBoundaryCrossing({
      childLayer: 'DAILY',
      rangeScope: 'MAJOR',
      parentId: 10,
      savedRanges: [weeklyA, weeklyB],
      childSpan: {
        range_start_time: '2025-03-02T00:00:00.000Z',
        range_end_time: '2025-03-06T00:00:00.000Z',
      },
    });
    expect(assessment).toBeNull();
  });

  it('exempts auto-chain same parent campaign', () => {
    const assessment = assessCampaignBoundaryCrossing({
      childLayer: 'DAILY',
      rangeScope: 'MAJOR',
      parentId: 10,
      savedRanges: [weeklyA, weeklyB],
      autoChain: true,
      chainDraftMode: true,
      chainParentCampaignId: 10,
      childSpan: {
        range_start_time: '2025-03-05T00:00:00.000Z',
        range_end_time: '2025-03-10T00:00:00.000Z',
      },
    });
    expect(assessment).toBeNull();
  });

  it('merges campaign flexibility meta into payload meta_json', () => {
    const merged = mergeCampaignFlexMeta(
      { phase: 'test' },
      { extend_campaign: true, confirmed_at: '2025-01-01T00:00:00.000Z' },
    );
    expect(merged.phase).toBe('test');
    expect((merged as any).campaign_flexibility.extend_campaign).toBe(true);
  });
});
