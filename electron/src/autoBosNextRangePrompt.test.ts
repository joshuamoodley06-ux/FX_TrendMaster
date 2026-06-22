import { describe, expect, it } from 'vitest';
import {
  bosNextRangePromptKey,
  evaluateBosNextRangePrompt,
  findNextChainedRange,
  promptTextForStructureLayer,
} from './autoBosNextRangePrompt';

const weeklyParent = {
  range_id: 1,
  structure_layer: 'WEEKLY',
  range_scope: 'MAJOR',
  status: 'ACTIVE',
};

const dailyBroken = {
  range_id: 10,
  structure_layer: 'DAILY',
  range_scope: 'MAJOR',
  status: 'BROKEN',
  parent_range_id: 1,
  broken_by_event_id: 501,
};

describe('autoBosNextRangePrompt', () => {
  it('prompts for next Daily after BOS when mapping inside Weekly parent', () => {
    const result = evaluateBosNextRangePrompt({
      brokenRange: dailyBroken,
      ranges: [weeklyParent, dailyBroken],
      bosEventId: 501,
    });
    expect(result.status).toBe('PROMPT');
    expect(result.promptMessage).toBe('Set new Daily range?');
  });

  it('does not prompt when next range is linked via new_range_id', () => {
    const result = evaluateBosNextRangePrompt({
      brokenRange: { ...dailyBroken, new_range_id: 11 },
      ranges: [
        dailyBroken,
        { range_id: 11, structure_layer: 'DAILY', old_range_id: 10, parent_range_id: 1 },
      ],
      bosEventId: 501,
    });
    expect(result.status).toBe('ALREADY_EXISTS');
    expect(result.existingNextRangeId).toBe('11');
  });

  it('detects next range via created_by_event_id', () => {
    const match = findNextChainedRange('10', 501, [
      dailyBroken,
      {
        range_id: 12,
        structure_layer: 'DAILY',
        created_by_event_id: 501,
        parent_range_id: 1,
      },
    ], 'DAILY');
    expect(match.matchKind).toBe('created_by_event_id');
    expect(match.range?.range_id).toBe(12);
  });

  it('returns uncertain when multiple successor ranges match', () => {
    const result = evaluateBosNextRangePrompt({
      brokenRange: dailyBroken,
      ranges: [
        dailyBroken,
        { range_id: 11, structure_layer: 'DAILY', old_range_id: 10 },
        { range_id: 12, structure_layer: 'DAILY', old_range_id: 10 },
      ],
      bosEventId: 501,
    });
    expect(result.status).toBe('UNCERTAIN');
  });

  it('returns NO_PROMPT without parent when parent context required', () => {
    const orphan = { ...dailyBroken, parent_range_id: null };
    const result = evaluateBosNextRangePrompt({
      brokenRange: orphan,
      ranges: [orphan],
      bosEventId: 501,
    });
    expect(result.status).toBe('NO_PROMPT');
  });

  it('prompts Intraday inside Daily parent', () => {
    expect(promptTextForStructureLayer('INTRADAY')).toBe('Set new Intraday range?');
    const result = evaluateBosNextRangePrompt({
      brokenRange: {
        range_id: 20,
        structure_layer: 'INTRADAY',
        parent_range_id: 10,
        broken_by_event_id: 900,
      },
      ranges: [{ range_id: 10, structure_layer: 'DAILY' }],
      bosEventId: 900,
    });
    expect(result.status).toBe('PROMPT');
    expect(result.promptMessage).toBe('Set new Intraday range?');
  });

  it('builds stable prompt keys', () => {
    expect(bosNextRangePromptKey({ brokenRangeId: '10', bosEventId: 501 })).toBe('10:501');
  });
});
