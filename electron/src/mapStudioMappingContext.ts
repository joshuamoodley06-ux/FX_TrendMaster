export function hasMappingSkeletonContext(args: {
  hasCase: boolean;
  activeStructuralRangeId: string;
  selectedParentRangeId: string;
  guidedCursorActive: boolean;
  childMappingSessionActive: boolean;
}): boolean {
  if (!args.hasCase) return false;
  return !!(
    args.activeStructuralRangeId
    || args.selectedParentRangeId
    || args.guidedCursorActive
    || args.childMappingSessionActive
  );
}

export function buildSkeletonMappingStatusLine(args: {
  selectedTimeLabel: string | null;
  timeframe: string;
  structureLayer: string;
  activeRangeId: string;
  parentRangeId: string;
  rhSet: boolean;
  rlSet: boolean;
  chainDraftMode: boolean;
  rangeSynced: boolean;
  lastMessage: string;
  structuralSaving: boolean;
}): string {
  if (args.structuralSaving) return 'Syncing range to backend…';
  if (args.selectedTimeLabel) {
    const keys = 'H = RH · L = RL · ↑/↓ = BOS · ←/→ = replay · U = undo · Esc = clear';
    return `Selected: ${args.selectedTimeLabel} ${args.timeframe} · ${keys}`;
  }
  if (args.chainDraftMode && args.rhSet && args.rlSet) {
    return `${args.structureLayer} next range RH/RL set · syncing chain…`;
  }
  if (args.activeRangeId && args.rhSet && args.rlSet && args.rangeSynced) {
    const parent = args.parentRangeId ? ` · parent #${args.parentRangeId}` : '';
    return `${args.structureLayer} #${args.activeRangeId}${parent} · RH/RL set · range synced`;
  }
  if (args.activeRangeId && args.rhSet && args.rlSet) {
    return `${args.structureLayer} #${args.activeRangeId} · RH/RL set · syncing…`;
  }
  if (!args.activeRangeId && !args.parentRangeId) {
    return 'Select campaign or hierarchy context first · then click a candle';
  }
  return args.lastMessage || 'Click a candle · H/L for RH/RL · ↑/↓ for BOS';
}
