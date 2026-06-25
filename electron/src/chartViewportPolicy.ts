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

/** Reasons allowed to move camera while a stable owner is active. */
export function isExplicitCameraNavigationReason(reason?: string | null): boolean {
  const r = String(reason || '').toLowerCase();
  if (!r) return false;
  return (
    r.includes('fit-all')
    || r.includes('fit-range')
    || r.includes('fit-replay')
    || r.includes('fit-case')
    || r.includes('lock-view')
    || r.includes('timeframe-switch')
    || r.includes('continue-campaign')
    || r.includes('campaign-continue')
    || r.includes('explorer-jump')
    || r.includes('audit-jump')
    || r.includes('drill-down')
    || r.includes('open-saved-case')
    || r.includes('open-raw-case')
    || r.includes('manual-w')
    || r.includes('manual-h')
    || r.includes('jump')
    || r.includes('fullscreen-layout-ready')
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
