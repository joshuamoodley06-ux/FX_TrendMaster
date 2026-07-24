import { describe, expect, it } from 'vitest';
import {
  captureStructuralRangeDraftSnapshot,
  createStructuralRangeDraftSession,
  structuralRangeDraftSaveBlockReason,
  structuralRangeDraftSessionMatchesScope,
  touchStructuralRangeDraftSession,
} from './structuralRangeDraftSession';

const layerCases = [
  ['MACRO', 'MN1'],
  ['WEEKLY', 'W1'],
  ['DAILY', 'D1'],
  ['INTRADAY', 'H1'],
  ['MICRO', 'M15'],
] as const;

describe('structuralRangeDraftSession', () => {
  for (const [layer, sourceTimeframe] of layerCases) {
    describe(`${layer} draft integrity`, () => {
      it('blocks a new RH from reusing an older RL', () => {
        let session = createStructuralRangeDraftSession({
          sessionId: `${layer}-1`,
          structureLayer: layer,
          sourceTimeframe,
        });
        session = touchStructuralRangeDraftSession(session, 'RH');
        expect(structuralRangeDraftSaveBlockReason({
          session,
          structureLayer: layer,
          sourceTimeframe,
          rh: { price: 2500, time: '2026-01-02T00:00:00Z' },
          rl: { price: 2400, time: '2025-12-01T00:00:00Z' },
        })).toContain('older RL cannot be reused');
      });

      it('blocks a new RL from reusing an older RH', () => {
        let session = createStructuralRangeDraftSession({
          sessionId: `${layer}-2`,
          structureLayer: layer,
          sourceTimeframe,
        });
        session = touchStructuralRangeDraftSession(session, 'RL');
        expect(structuralRangeDraftSaveBlockReason({
          session,
          structureLayer: layer,
          sourceTimeframe,
          rh: { price: 2500, time: '2025-12-01T00:00:00Z' },
          rl: { price: 2400, time: '2026-01-02T00:00:00Z' },
        })).toContain('older RH cannot be reused');
      });

      it('accepts H then L and L then H only after both are touched in the same session', () => {
        let session = createStructuralRangeDraftSession({
          sessionId: `${layer}-3`,
          structureLayer: layer,
          sourceTimeframe,
        });
        session = touchStructuralRangeDraftSession(session, 'RH');
        session = touchStructuralRangeDraftSession(session, 'RL');
        expect(structuralRangeDraftSaveBlockReason({
          session,
          structureLayer: layer,
          sourceTimeframe,
          rh: { price: 2500, time: '2026-01-02T00:00:00Z' },
          rl: { price: 2400, time: '2026-01-03T00:00:00Z' },
        })).toBeNull();

        let reverse = createStructuralRangeDraftSession({
          sessionId: `${layer}-4`,
          structureLayer: layer,
          sourceTimeframe,
        });
        reverse = touchStructuralRangeDraftSession(reverse, 'RL');
        reverse = touchStructuralRangeDraftSession(reverse, 'RH');
        expect(structuralRangeDraftSaveBlockReason({
          session: reverse,
          structureLayer: layer,
          sourceTimeframe,
          rh: { price: 2500, time: '2026-01-02T00:00:00Z' },
          rl: { price: 2400, time: '2026-01-03T00:00:00Z' },
        })).toBeNull();
      });
    });
  }

  it('rejects layer and source-timeframe leakage', () => {
    const session = createStructuralRangeDraftSession({
      sessionId: 'scope',
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      rhTouched: true,
      rlTouched: true,
    });
    expect(structuralRangeDraftSessionMatchesScope(session, 'INTRADAY', 'D1')).toBe(false);
    expect(structuralRangeDraftSessionMatchesScope(session, 'DAILY', 'H4')).toBe(false);
    expect(structuralRangeDraftSaveBlockReason({
      session,
      structureLayer: 'INTRADAY',
      sourceTimeframe: 'H4',
      rh: { price: 2500, time: '2026-01-02T00:00:00Z' },
      rl: { price: 2400, time: '2026-01-03T00:00:00Z' },
    })).toContain('Draft scope changed');
  });

  it('binds edit mode to one exact saved range while retaining its untouched side', () => {
    const edit = createStructuralRangeDraftSession({
      sessionId: 'edit',
      mode: 'EDIT',
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      targetRangeId: '693',
      rhTouched: true,
      rlTouched: true,
    });
    expect(structuralRangeDraftSaveBlockReason({
      session: edit,
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      activeRangeId: '693',
      rh: { price: 2501, time: '2026-01-02T00:00:00Z' },
      rl: { price: 2400, time: '2026-01-03T00:00:00Z' },
    })).toBeNull();
    expect(structuralRangeDraftSaveBlockReason({
      session: edit,
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      activeRangeId: '697',
      rh: { price: 2501, time: '2026-01-02T00:00:00Z' },
      rl: { price: 2400, time: '2026-01-03T00:00:00Z' },
    })).toContain('Edit target changed');
  });

  it('captures an immutable anchor snapshot before async save work starts', () => {
    let session = createStructuralRangeDraftSession({
      sessionId: 'snapshot',
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
    });
    session = touchStructuralRangeDraftSession(touchStructuralRangeDraftSession(session, 'RH'), 'RL');
    const rh = { price: '2500', time: '2026-01-02T00:00:00Z', candle: { id: 'rh' } };
    const rl = { price: '2400', time: '2026-01-03T00:00:00Z', candle: { id: 'rl' } };
    const captured = captureStructuralRangeDraftSnapshot({
      session,
      structureLayer: 'DAILY',
      sourceTimeframe: 'D1',
      rh,
      rl,
    });
    expect(captured.ok).toBe(true);
    if (!captured.ok) return;
    rh.price = '9999';
    rl.price = '1';
    expect(captured.snapshot.rh.price).toBe('2500');
    expect(captured.snapshot.rl.price).toBe('2400');
  });
});
