import { describe, expect, it } from 'vitest';
import {
  autoCandleBodyWidthPx,
  inferViewOwnerFromCameraReason,
  isExplicitCameraNavigationReason,
  shouldBlockAutomaticCameraRefit,
  targetVisibleBarsForTimeframe,
} from './chartViewportPolicy';

describe('chartViewportPolicy', () => {
  it('uses readable default bar counts per timeframe', () => {
    expect(targetVisibleBarsForTimeframe('W1')).toBeGreaterThanOrEqual(20);
    expect(targetVisibleBarsForTimeframe('W1')).toBeLessThanOrEqual(40);
    expect(targetVisibleBarsForTimeframe('M15')).toBeGreaterThanOrEqual(150);
  });

  it('blocks automatic refit for manual fit owners', () => {
    expect(shouldBlockAutomaticCameraRefit('FIT_ALL')).toBe(true);
    expect(shouldBlockAutomaticCameraRefit('FIT_RANGE')).toBe(true);
    expect(shouldBlockAutomaticCameraRefit('USER_PAN_ZOOM')).toBe(true);
    expect(shouldBlockAutomaticCameraRefit('USER_LOCKED')).toBe(true);
    expect(shouldBlockAutomaticCameraRefit('TIMEFRAME_SWITCH')).toBe(true);
    expect(shouldBlockAutomaticCameraRefit('AUTO')).toBe(false);
  });

  it('maps camera reasons to view owners', () => {
    expect(inferViewOwnerFromCameraReason('fit-all', 'FIT_ALL')).toBe('FIT_ALL');
    expect(inferViewOwnerFromCameraReason('fit-range', 'FIT_STRUCTURAL_RANGE')).toBe('FIT_RANGE');
    expect(inferViewOwnerFromCameraReason('timeframe-switch:W1->D1')).toBe('TIMEFRAME_SWITCH');
    expect(inferViewOwnerFromCameraReason('lock-view', 'RESTORE_LOCKED')).toBe('USER_LOCKED');
  });

  it('allows explicit navigation during stable view', () => {
    expect(isExplicitCameraNavigationReason('fit-all')).toBe(true);
    expect(isExplicitCameraNavigationReason('quiet-refresh')).toBe(false);
    expect(isExplicitCameraNavigationReason('confirmed-candle-load')).toBe(false);
  });

  it('derives candle body width from bar spacing', () => {
    expect(autoCandleBodyWidthPx(14)).toBeGreaterThanOrEqual(2);
    expect(autoCandleBodyWidthPx(4)).toBeGreaterThanOrEqual(2);
    expect(autoCandleBodyWidthPx(80)).toBeLessThanOrEqual(48);
  });
});
