import { describe, expect, it } from 'vitest';
import {
  activateRoutineFitLock,
  autoCandleBodyWidthPx,
  clearRoutineFitLock,
  inferViewOwnerFromCameraReason,
  isExplicitCameraNavigationReason,
  isRoutineFitLockActive,
  isRoutineTfMemoryReason,
  isStructuralNavigationReason,
  shouldBlockAutomaticCameraRefit,
  shouldBlockTradingViewAutoFit,
  shouldBlockTradingViewFitContent,
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
    expect(isExplicitCameraNavigationReason('routine-tf-memory:W1->D1')).toBe(true);
    expect(isExplicitCameraNavigationReason('explorer-jump-fit')).toBe(true);
    expect(isExplicitCameraNavigationReason('quiet-refresh')).toBe(false);
    expect(isExplicitCameraNavigationReason('confirmed-candle-load')).toBe(false);
  });

  it('splits routine TF memory from structural navigation', () => {
    expect(isRoutineTfMemoryReason('routine-tf-memory:W1->D1')).toBe(true);
    expect(isStructuralNavigationReason('explorer-jump-fit')).toBe(true);
    expect(isStructuralNavigationReason('routine-tf-memory:W1->D1')).toBe(false);
  });

  it('blocks fitContent for replay and hierarchy chart modes', () => {
    expect(shouldBlockTradingViewFitContent('replay')).toBe(true);
    expect(shouldBlockTradingViewFitContent('hierarchy')).toBe(true);
    expect(shouldBlockTradingViewFitContent('latest')).toBe(false);
  });

  it('blocks TradingView auto fit while routine fit lock is active', () => {
    activateRoutineFitLock('H4', 60000);
    expect(isRoutineFitLockActive('H4')).toBe(true);
    expect(shouldBlockTradingViewAutoFit({
      owner: 'AUTO',
      chartMode: 'full',
    })).toBe(true);
    clearRoutineFitLock();
    expect(isRoutineFitLockActive('H4')).toBe(false);
  });

  it('blocks TradingView auto fit during stable owners and routine TF memory', () => {
    clearRoutineFitLock();
    expect(shouldBlockTradingViewAutoFit({
      owner: 'AUTO',
      chartMode: 'latest',
      pendingFitReason: 'routine-tf-memory:W1->D1',
    })).toBe(true);
    expect(shouldBlockTradingViewAutoFit({
      owner: 'TIMEFRAME_SWITCH',
      chartMode: 'latest',
    })).toBe(true);
    expect(shouldBlockTradingViewAutoFit({
      owner: 'AUTO',
      chartMode: 'latest',
      hasPendingFitToken: true,
    })).toBe(true);
    expect(shouldBlockTradingViewAutoFit({
      owner: 'AUTO',
      chartMode: 'latest',
    })).toBe(false);
  });

  it('derives candle body width from bar spacing', () => {
    expect(autoCandleBodyWidthPx(14)).toBeGreaterThanOrEqual(2);
    expect(autoCandleBodyWidthPx(4)).toBeGreaterThanOrEqual(2);
    expect(autoCandleBodyWidthPx(80)).toBeLessThanOrEqual(48);
  });
});
