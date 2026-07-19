import { describe, expect, it } from 'vitest';
import {
  adaptMasterMapOutput,
  flattenMasterMapRanges,
  masterMapRootForMode,
  MasterMapAdapterError,
} from './masterMapAdapter';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('masterMapAdapter', () => {
  it('adapts Python range nodes without replacing the canonical range identity', () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const weekly = document.trustedRoot.children[0];
    const daily = weekly.children[0];
    const intraday = daily.children[0];

    expect(document.symbol).toBe('XAUUSD');
    expect([weekly.layer, daily.layer, intraday.layer]).toEqual([
      'WEEKLY',
      'DAILY',
      'INTRADAY',
    ]);
    expect(weekly.canonicalRangeId).toBe('mm:range:weekly-trusted');
    expect(weekly.status).toBe('BROKEN');
    expect(weekly.directionOfBreak).toBe('DOWN');
    expect(weekly.navigationStatus).toBe('TRUSTED');
    expect(weekly.statisticsStatus).toBe('ELIGIBLE');
    expect(weekly.script1Chronology).toBe('RL_TO_RH');
    expect(weekly.script1BosDirection).toBe('BOS_UP');
    expect(weekly.script1BosTime).toBe('2026-02-01T00:00:00Z');
    expect(weekly.script1ProcessingStatus).toBe('COMPLETE');
    expect(weekly.sourceRefs[0]).toMatchObject({
      caseRef: 'case:live',
      sourceRecordId: 'mm:range:weekly-trusted',
    });
  });

  it('selects trusted_root for normal, review_root for review, and root only for explicit all mode', () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const trustedIds = new Set(
      flattenMasterMapRanges(masterMapRootForMode(document, 'trusted'))
        .map((node) => node.canonicalRangeId),
    );
    const reviewNodes = flattenMasterMapRanges(masterMapRootForMode(document, 'review'));
    const reviewIds = new Set(reviewNodes.map((node) => node.canonicalRangeId));
    const allIds = new Set(
      flattenMasterMapRanges(masterMapRootForMode(document, 'all'))
        .map((node) => node.canonicalRangeId),
    );

    expect(document.trustedRoot.canonicalRootId).toBe('symbol:XAUUSD:trusted');
    expect(document.reviewRoot.canonicalRootId).toBe('symbol:XAUUSD:review');
    expect(document.allNavigationRoot.canonicalRootId).toBe('symbol:XAUUSD');
    expect(trustedIds).toContain('mm:range:daily-trusted');
    expect(trustedIds).not.toContain('mm:range:daily-review');
    expect(reviewIds).toContain('mm:range:daily-review');
    expect(reviewIds).not.toContain('mm:range:daily-trusted');
    expect(allIds).toContain('mm:range:daily-trusted');
    expect(allIds).toContain('mm:range:daily-review');
    expect(
      reviewNodes
        .filter((node) => node.navigationStatus === 'REVIEW')
        .every((node) => node.statisticsStatus === 'EXCLUDED'),
    ).toBe(true);
  });

  it('rejects a review node that claims statistics eligibility', () => {
    const fixture = masterMapFixture();
    const reviewRoot = fixture.review_root as Record<string, unknown>;
    const weekly = (reviewRoot.children as Record<string, unknown>[])[0];
    const daily = (weekly.children as Record<string, unknown>[])[0];
    daily.statistics_status = 'ELIGIBLE';

    expect(() => adaptMasterMapOutput(fixture)).toThrow(MasterMapAdapterError);
    expect(() => adaptMasterMapOutput(fixture)).toThrow(/must be EXCLUDED from statistics/);
  });

  it('rejects reviewed content leaking into trusted_root', () => {
    const fixture = masterMapFixture();
    const trustedRoot = fixture.trusted_root as Record<string, unknown>;
    const weekly = (trustedRoot.children as Record<string, unknown>[])[0];
    weekly.navigation_status = 'REVIEW';
    weekly.statistics_status = 'EXCLUDED';

    expect(() => adaptMasterMapOutput(fixture)).toThrow(/trusted_root contains non-trusted range/);
  });
});
