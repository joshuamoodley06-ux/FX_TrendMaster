/** Saved / context range line styling — active full opacity, context ghost at 0.3. */

export const ACTIVE_RANGE_LINE_OPACITY = 1;
export const CONTEXT_RANGE_LINE_OPACITY = 0.3;

export type RangeLineStyle = {
  opacity: number;
  dash: string;
  width: number;
};

export type SavedRangeLineStyleOpts = {
  isActive?: boolean;
  isParentContext?: boolean;
  isGuidedParentContext?: boolean;
  rangeScope?: string;
  structureLayer?: string;
};

const PRIMARY_GUIDE_LAYERS = new Set(['WEEKLY', 'DAILY']);

function isPrimaryGuideLayer(layer: unknown): boolean {
  return PRIMARY_GUIDE_LAYERS.has(String(layer || '').toUpperCase());
}

function isBrokenStatus(status: string): boolean {
  const s = String(status || 'ACTIVE').toUpperCase();
  return s === 'BROKEN' || s === 'ABANDONED' || s === 'INACTIVE' || s === 'REPLACED';
}

export function savedRangeLineStyle(
  status: string,
  opts?: SavedRangeLineStyleOpts,
): RangeLineStyle {
  const broken = isBrokenStatus(status);
  const isMinor = opts?.rangeScope === 'MINOR';

  if (opts?.isActive && !broken) {
    return {
      opacity: ACTIVE_RANGE_LINE_OPACITY,
      dash: isMinor ? '5 4' : '',
      width: isMinor ? 3.4 : 4.2,
    };
  }

  const primaryGuide = isPrimaryGuideLayer(opts?.structureLayer);
  return {
    opacity: primaryGuide ? 0.9 : CONTEXT_RANGE_LINE_OPACITY,
    dash: broken ? '5 5' : (isMinor ? '4 5' : primaryGuide ? '' : '4 6'),
    width: primaryGuide ? 3.2 : (isMinor ? 2.2 : 2.4),
  };
}

export function draftRangeLineStyle(anchorsComplete = false): RangeLineStyle {
  if (anchorsComplete) {
    return { opacity: ACTIVE_RANGE_LINE_OPACITY, dash: '', width: 4.2 };
  }
  return { opacity: 0.85, dash: '4 6', width: 3.2 };
}
