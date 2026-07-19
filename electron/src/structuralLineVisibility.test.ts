import { describe, expect, it } from 'vitest';
import {
  setAllStructuralLines,
  setNoStructuralLines,
  toggleStructuralLine,
  visibleStructuralLineIds,
} from './structuralLineVisibility';

const ids = ['a:RH', 'a:RL', 'b:RH', 'b:RL'];

describe('structural line visibility', () => {
  it('shows and hides all deterministically', () => {
    expect([...visibleStructuralLineIds(setAllStructuralLines(ids), ids)]).toEqual(ids);
    expect([...visibleStructuralLineIds(setNoStructuralLines(), ids)]).toEqual([]);
  });

  it('toggles exactly one stable line and derives CUSTOM/ALL/NONE', () => {
    const allMinusOne = toggleStructuralLine(setAllStructuralLines(ids), 'a:RH', ids);
    expect(allMinusOne.globalMode).toBe('CUSTOM');
    expect([...visibleStructuralLineIds(allMinusOne, [...ids].reverse())].sort()).toEqual(['a:RL', 'b:RH', 'b:RL']);
    const allAgain = toggleStructuralLine(allMinusOne, 'a:RH', ids);
    expect(allAgain.globalMode).toBe('ALL');
    const one = toggleStructuralLine(setNoStructuralLines(), 'b:RL', ids);
    expect(one).toMatchObject({ globalMode: 'CUSTOM', visibleLineIds: ['b:RL'] });
    expect(toggleStructuralLine(one, 'b:RL', ids).globalMode).toBe('NONE');
  });

  it('applies the documented new-line rule for each mode', () => {
    const next = [...ids, 'c:RH', 'c:RL'];
    expect(visibleStructuralLineIds(setAllStructuralLines(ids), next).has('c:RH')).toBe(true);
    expect(visibleStructuralLineIds(setNoStructuralLines(), next).has('c:RH')).toBe(false);
    const custom = { globalMode: 'CUSTOM' as const, visibleLineIds: ['a:RH'], knownLineIds: ids };
    expect(visibleStructuralLineIds(custom, next).has('c:RH')).toBe(false);
    expect(visibleStructuralLineIds(custom, next, 'c').has('c:RH')).toBe(true);
  });
});
