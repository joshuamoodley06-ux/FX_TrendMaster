import { describe, expect, it } from 'vitest';
import {
  ACTIVE_RANGE_LINE_OPACITY,
  CONTEXT_RANGE_LINE_OPACITY,
  savedRangeLineStyle,
} from './rangeLineStyle';

describe('rangeLineStyle', () => {
  it('active range uses full opacity', () => {
    const style = savedRangeLineStyle('ACTIVE', { isActive: true, rangeScope: 'MAJOR' });
    expect(style.opacity).toBe(ACTIVE_RANGE_LINE_OPACITY);
  });

  it('non-active parent context uses ghost opacity', () => {
    const style = savedRangeLineStyle('ACTIVE', { isParentContext: true, isActive: false });
    expect(style.opacity).toBe(CONTEXT_RANGE_LINE_OPACITY);
  });

  it('Weekly/Daily context lines stay stronger than generic ghost lines', () => {
    const weekly = savedRangeLineStyle('ACTIVE', { isActive: false, structureLayer: 'WEEKLY' });
    const generic = savedRangeLineStyle('ACTIVE', { isActive: false, structureLayer: 'INTRADAY' });
    expect(weekly.opacity).toBeGreaterThan(generic.opacity);
  });

  it('non-active sibling range uses ghost opacity', () => {
    const style = savedRangeLineStyle('ACTIVE', { isActive: false });
    expect(style.opacity).toBe(CONTEXT_RANGE_LINE_OPACITY);
  });

  it('broken active range still ghosts when not active', () => {
    const style = savedRangeLineStyle('BROKEN', { isActive: false });
    expect(style.opacity).toBe(CONTEXT_RANGE_LINE_OPACITY);
    expect(style.dash).toBe('5 5');
  });
});
