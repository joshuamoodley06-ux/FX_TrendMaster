/** Chart viewport ownership — manual fits win over late async refreshes. */

export type CameraViewOwner =
  | 'AUTO'
  | 'USER_PAN_ZOOM'
  | 'FIT_ALL'
  | 'FIT_RANGE'
  | 'FIT_REPLAY'
  | 'FIT_CASE'
  | 'USER_LOCKED'
  | 'CAMPAIGN_CONTINUE'
  | 'TIMEFRAME_SWITCH'
  | 'SESSION_RESTORE';

/** Owners that block automatic camera refits from overlays, quiet reloads, readable zoom, etc. */
export const STABLE_CAMERA_OWNERS: ReadonlySet<CameraViewOwner> = new Set([
  'USER_PAN_ZOOM',
  'FIT_ALL',
  'FIT_RANGE',
  'FIT_REPLAY',
  'FIT_CASE',
  'USER_LOCKED',
  'TIMEFRAME_SWITCH',
]);

/** Fraction of inner chart width reserved as empty future space (8–15%). */
export const CHART_FUTURE_PAD_RATIO = 0.12;

/** Horizontal anchor for latest-bar fits: 1 = right edge, minus future pad. */
export const CHART_LATEST_ANCHOR_RATIO = 1 - CHART_FUTURE_PAD_RATIO * 0.5;

export function targetVisibleBarsForTimeframe(tf: string): number {
  const t = String(tf || 'D1').toUpperCase();
  if (t === 'M15' || t === 'M5') return 220;
  if (t === 'H1') return 180;
  if (t === 'H4') return 120;
  if (t === 'D1') return 80;
  if (t === 'W1') return 30;
  if (t === 'MN1') return 36;
  return 96;
}

export function readablePadBarsForTimeframe(tf: string): number {
  return Math.max(12, Math.round(targetVisibleBarsForTimeframe(tf) * 0.18));
}

export function shouldBlockAutomaticCameraRefit(owner: CameraViewOwner | null | undefined): boolean {
  if (!owner) return false;
  return STABLE_CAMERA_OWNERS.has(owner);
}

/** Phase 1: replay/hierarchy must never auto-fitContent — camera moves only via explicit fit tokens. */
export function shouldBlockTradingViewFitContent(chartMode: string | null | undefined): boolean {
  const mode = String(chartMode || '').toLowerCase();
  return mode === 'replay' || mode === 'hierarchy';
}

export type TradingViewFitAppliedDetail = {
  token: number;
  kind: 'hierarchy' | 'replay' | 'routine-memory' | 'range' | 'target';
};

export type TradingViewCameraBridge = {
  owner: CameraViewOwner;
  pendingFitReason: string | null;
  pendingCameraIntentActive: boolean;
  routineAnchorSource: string | null;
  onFitApplied: ((detail: TradingViewFitAppliedDetail) => void) | null;
  onVisibleRangeChange: ((domain: { start: string; end: string; visibleBars: number }) => void) | null;
  onUserPanZoom: (() => void) | null;
};

/** Main ↔ TradingView camera ownership bridge (LiveViewPanel stays a thin shell). */
export const tradingViewCameraBridge: { current: TradingViewCameraBridge } = {
  current: {
    owner: 'AUTO',
    pendingFitReason: null,
    pendingCameraIntentActive: false,
    routineAnchorSource: null,
    onFitApplied: null,
    onVisibleRangeChange: null,
    onUserPanZoom: null,
  },
};

export type RoutineFitLockState = {
  active: boolean;
  timeframe: string | null;
  untilMs: number;
};

/** Blocks post-routine-fit fitContent / display re-slice until TTL or user pan. */
export const routineFitLockBridge: { current: RoutineFitLockState } = {
  current: { active: false, timeframe: null, untilMs: 0 },
};

export function activateRoutineFitLock(timeframe: string, ttlMs = 20000): void {
  routineFitLockBridge.current = {
    active: true,
    timeframe: String(timeframe || '').toUpperCase(),
    untilMs: Date.now() + Math.max(5000, ttlMs),
  };
}

export function clearRoutineFitLock(): void {
  routineFitLockBridge.current.active = false;
  routineFitLockBridge.current.timeframe = null;
  routineFitLockBridge.current.untilMs = 0;
}

export function isRoutineFitLockActive(timeframe?: string | null): boolean {
  const lock = routineFitLockBridge.current;
  if (!lock.active) return false;
  if (Date.now() > lock.untilMs) {
    clearRoutineFitLock();
    return false;
  }
  const tf = String(timeframe || '').toUpperCase();
  if (tf && lock.timeframe && lock.timeframe !== tf) return false;
  return true;
}

export type PostRoutineSettleState = {
  active: boolean;
  untilMs: number;
};

/** Blocks layout/resize AUTO until ~500ms after routine memory fit settles. */
export const postRoutineSettleBridge: { current: PostRoutineSettleState } = {
  current: { active: false, untilMs: 0 },
};

export function activatePostRoutineSettle(ttlMs = 500): void {
  postRoutineSettleBridge.current = {
    active: true,
    untilMs: Date.now() + Math.max(200, ttlMs),
  };
}

export function clearPostRoutineSettle(): void {
  postRoutineSettleBridge.current.active = false;
  postRoutineSettleBridge.current.untilMs = 0;
}

export function isPostRoutineSettleActive(): boolean {
  const state = postRoutineSettleBridge.current;
  if (!state.active) return false;
  if (Date.now() > state.untilMs) {
    clearPostRoutineSettle();
    return false;
  }
  return true;
}

/** Block TradingView fitContent during stable owners, pending fits, and routine TF memory. */
export function shouldBlockTradingViewAutoFit(args: {
  owner?: CameraViewOwner | null;
  chartMode?: string | null;
  pendingFitReason?: string | null;
  hasPendingFitToken?: boolean;
  pendingCameraIntentActive?: boolean;
  postRoutineSettle?: boolean;
}): boolean {
  if (shouldBlockTradingViewFitContent(args.chartMode)) return true;
  if (args.hasPendingFitToken) return true;
  if (args.pendingCameraIntentActive) return true;
  if (args.postRoutineSettle ?? isPostRoutineSettleActive()) return true;
  if (isRoutineFitLockActive()) return true;
  const owner = args.owner || 'AUTO';
  if (owner !== 'AUTO') return true;
  const reason = String(args.pendingFitReason || '').toLowerCase();
  if (isRoutineTfMemoryReason(reason)) return true;
  if (reason.includes('timeframe-switch')) return true;
  return false;
}

/** Block fullscreen layout refit while routine TF switch / pending fit / settle is active. */
export function shouldBlockFullscreenLayoutRefit(args: {
  owner?: CameraViewOwner | null;
  pendingCameraIntentActive?: boolean;
  hasPendingFitToken?: boolean;
  pendingFitReason?: string | null;
}): boolean {
  if (shouldBlockAutomaticCameraRefit(args.owner)) return true;
  if (args.pendingCameraIntentActive) return true;
  if (args.hasPendingFitToken) return true;
  if (isRoutineFitLockActive()) return true;
  if (isPostRoutineSettleActive()) return true;
  const reason = String(args.pendingFitReason || '').toLowerCase();
  if (isRoutineTfMemoryReason(reason)) return true;
  if (reason.includes('timeframe-switch')) return true;
  return false;
}

export function isReplayCameraOwner(owner?: CameraViewOwner | null): boolean {
  return owner === 'FIT_REPLAY';
}

export function isStructuralFitCameraOwner(owner?: CameraViewOwner | null): boolean {
  return owner === 'FIT_RANGE' || owner === 'FIT_CASE' || owner === 'FIT_ALL';
}

export function inferViewOwnerFromCameraReason(
  reason?: string | null,
  intent?: string | null,
): CameraViewOwner {
  const r = String(reason || '').toLowerCase();
  const i = String(intent || '').toUpperCase();
  if (r.includes('lock-view') || r.includes('locked-load') || i === 'RESTORE_LOCKED') return 'USER_LOCKED';
  if (r.includes('fit-all') || i === 'FIT_ALL') return 'FIT_ALL';
  if (r.includes('fit-range') || (i === 'FIT_STRUCTURAL_RANGE' && r.includes('fit-range'))) return 'FIT_RANGE';
  if (r.includes('fit-replay') || (i === 'FIT_STRUCTURAL_RANGE' && r.includes('fit-replay'))) return 'FIT_REPLAY';
  if (r.includes('fit-case') || i === 'CASE') return 'FIT_CASE';
  if (r.includes('routine-tf-memory')) return 'TIMEFRAME_SWITCH';
  if (r.includes('timeframe-switch') || r.includes('tf-switch')) return 'TIMEFRAME_SWITCH';
  if (r.includes('continue-campaign') || r.includes('campaign')) return 'CAMPAIGN_CONTINUE';
  if (r.includes('session-restore') || r.includes('auto-resume') || r.includes('open-saved-case') || r.includes('open-raw-case')) {
    return 'SESSION_RESTORE';
  }
  if (r.includes('manual-w') || r.includes('manual-h') || r.includes('user-pan') || r.includes('user-zoom')) {
    return 'USER_PAN_ZOOM';
  }
  if (i === 'HORIZONTAL_STRETCH' || i === 'VERTICAL_STRETCH') return 'USER_PAN_ZOOM';
  return 'AUTO';
}

/** Routine TF chip switch — restore saved viewport memory, not structural range fit. */
export function isRoutineTfMemoryReason(reason?: string | null): boolean {
  return String(reason || '').toLowerCase().includes('routine-tf-memory');
}

/** Explicit hierarchy / Event Browser / audit navigation — structural fit allowed. */
export function isStructuralNavigationReason(reason?: string | null): boolean {
  const r = String(reason || '').toLowerCase();
  if (!r) return false;
  if (isRoutineTfMemoryReason(r)) return false;
  return (
    r.includes('explorer-jump')
    || r.includes('explorer-parent')
    || r.includes('navigatestructural')
    || r.includes('tradingview-hierarchy-range-fit')
    || r.includes('audit-jump')
    || r.includes('timeframe-switch-structural')
  );
}

/** Reasons allowed to move camera while a stable owner is active. */
export function isExplicitCameraNavigationReason(reason?: string | null): boolean {
  const r = String(reason || '').toLowerCase();
  if (!r) return false;
  if (isRoutineTfMemoryReason(r)) return true;
  return (
    r.includes('fit-all')
    || r.includes('fit-range')
    || r.includes('fit-replay')
    || r.includes('fit-case')
    || r.includes('lock-view')
    || isStructuralNavigationReason(r)
    || r.includes('continue-campaign')
    || r.includes('campaign-continue')
    || r.includes('drill-down')
    || r.includes('open-saved-case')
    || r.includes('open-raw-case')
    || r.includes('manual-w')
    || r.includes('manual-h')
    || (r.includes('jump') && !r.includes('routine-tf-memory'))
  );
}

export function logCameraUpdate(reason: string, source: string, enabled = false): void {
  if (!enabled) return;
  console.log(`camera update: reason=${reason} source=${source}`);
}

export function autoCandleBodyWidthPx(barSpacingPx: number, manualWidthScale = 1): number {
  const slot = Math.max(2, Number(barSpacingPx) || 10);
  const scale = Number(manualWidthScale) || 1;
  const useManual = Math.abs(scale - 1) > 0.04;
  const ratio = useManual ? 0.8 * Math.max(0.35, Math.min(4, scale)) : 0.74;
  return Math.max(2, Math.min(48, Math.round(slot * ratio)));
}
