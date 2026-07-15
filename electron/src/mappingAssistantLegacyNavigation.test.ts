import { describe, expect, it } from 'vitest';

import { adaptMasterMapOutput } from './masterMapAdapter';
import { masterMapRangeToStructuralRangeRecord } from './masterMapNavigationIntegration';
import { normalizeStructuralRangeTarget } from './structuralJumpTarget';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('Mapping Assistant legacy main navigation compatibility', () => {
  it('recovers GAP reason and exact visual window when main normalizes as HIERARCHY', () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const range = document.trustedRoot.children[0];
    const record = masterMapRangeToStructuralRangeRecord({
      canonicalRangeId: range.canonicalRangeId,
      layer: 'WEEKLY',
      sourceTimeframe: 'W1',
      mode: 'all',
      range,
      reason: 'GAP',
      eventId: 'mm:event:formation-bos',
      preferredAnchorTime: '2025-12-28T00:00:00Z',
      visibleStart: '2025-10-01T00:00:00Z',
      visibleEnd: '2026-02-02T00:00:00Z',
    });

    expect(record).toMatchObject({
      range_start_time: '2025-10-01T00:00:00Z',
      range_end_time: '2026-02-02T00:00:00Z',
      structural_jump_source: 'GAP',
      mapping_assistant_gap: true,
    });

    const target = normalizeStructuralRangeTarget(record, 'HIERARCHY', {
      fallbackSymbol: 'XAUUSD',
      fallbackTimeframe: 'W1',
    });
    expect(target).toMatchObject({
      reason: 'GAP',
      eventId: 'mm:event:formation-bos',
      preferredAnchorTime: '2025-12-28T00:00:00.000Z',
      visibleWindow: {
        start: '2025-10-01T00:00:00.000Z',
        end: '2026-02-02T00:00:00.000Z',
      },
    });
  });

  it('does not rewrite ordinary hierarchy navigation as GAP', () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const range = document.trustedRoot.children[0];
    const record = masterMapRangeToStructuralRangeRecord({
      canonicalRangeId: range.canonicalRangeId,
      layer: 'WEEKLY',
      sourceTimeframe: 'W1',
      mode: 'trusted',
      range,
      reason: 'HIERARCHY',
    });
    expect(normalizeStructuralRangeTarget(record, 'HIERARCHY')?.reason).toBe('HIERARCHY');
  });
});
