import { describe, expect, it } from 'vitest';
import {
  buildBaseTimeDomain,
  buildFitWindowFromViewConfig,
  clampSpanToCandleExtent,
  createDefaultViewConfig,
  filterGuidedModeRangeOverlays,
  isExplicitViewportMove,
  isPlaybackOutsideParentWindow,
  markExplicitViewportMove,
  overlaySpanMs,
  expandCandleLoadWindowForContext,
  preserveCenterOnTimeframeSwitch,
  rangeSpanPx,
  shouldPreserveViewport,
  shouldSuppressAutoViewportFit,
  updateViewConfigFromVisibleDomain,
} from './viewportController';

describe('viewportController', () => {
  it('timeframe switch preserves center_time_ms', () => {
    const prev = {
      ...createDefaultViewConfig('D1'),
      center_time_ms: Date.parse('2025-02-15T00:00:00.000Z'),
      visible_start_ms: Date.parse('2025-01-01T00:00:00.000Z'),
      visible_end_ms: Date.parse('2025-03-01T00:00:00.000Z'),
      last_user_controlled_view: true,
    };
    const next = preserveCenterOnTimeframeSwitch(prev, 'H1');
    expect(next.center_time_ms).toBe(prev.center_time_ms);
    expect(next.timeframe).toBe('H1');
    expect(next.visible_start_ms).not.toBeNull();
    expect(next.visible_end_ms).not.toBeNull();
  });

  it('save range action preserves viewport', () => {
    expect(shouldPreserveViewport('save-range')).toBe(true);
    expect(shouldPreserveViewport('save-bos')).toBe(true);
    expect(isExplicitViewportMove('save-range')).toBe(false);
  });

  it('panel toggle preserves viewport', () => {
    expect(shouldPreserveViewport('toggle-child-panel')).toBe(true);
    expect(shouldPreserveViewport('toggle-explorer')).toBe(true);
  });

  it('explicit Fit Parent changes viewport intent', () => {
    expect(isExplicitViewportMove('fit-parent')).toBe(true);
    const cfg = createDefaultViewConfig();
    expect(shouldSuppressAutoViewportFit({
      ...cfg,
      last_user_controlled_view: true,
      last_move_reason: 'fit-parent',
    })).toBe(true);
  });

  it('parent overlay spans parent start/end', () => {
    const span = overlaySpanMs({
      range_start_time: '2025-01-01T00:00:00.000Z',
      range_end_time: '2025-03-01T00:00:00.000Z',
    });
    expect(span?.startMs).toBe(Date.parse('2025-01-01T00:00:00.000Z'));
    expect(span?.endMs).toBe(Date.parse('2025-03-01T00:00:00.000Z'));
  });

  it('child overlay spans child start/end', () => {
    const span = overlaySpanMs({
      range_start_time: '2025-01-10T00:00:00.000Z',
      range_end_time: '2025-01-20T00:00:00.000Z',
    });
    expect(span?.startMs).toBe(Date.parse('2025-01-10T00:00:00.000Z'));
    expect(span?.endMs).toBe(Date.parse('2025-01-20T00:00:00.000Z'));
  });

  it('unrelated ranges hidden during guided mode', () => {
    const overlays = [
      { rangeId: '1', structureLayer: 'WEEKLY', start: 'a', end: 'b' },
      { rangeId: '10', structureLayer: 'DAILY', start: 'c', end: 'd' },
      { rangeId: '99', structureLayer: 'DAILY', start: 'e', end: 'f' },
    ];
    const filtered = filterGuidedModeRangeOverlays(overlays, {
      guidedActive: true,
      showAllRanges: false,
      parentRangeId: '1',
      savedChildIds: ['10'],
      activeRangeId: null,
      ancestorIds: [],
    });
    expect(filtered.map((r) => r.rangeId)).toEqual(['1', '10']);
  });

  it('Show all ranges restores hidden ranges', () => {
    const overlays = [
      { rangeId: '1', structureLayer: 'WEEKLY' },
      { rangeId: '99', structureLayer: 'DAILY' },
    ];
    const filtered = filterGuidedModeRangeOverlays(overlays, {
      guidedActive: true,
      showAllRanges: true,
      parentRangeId: '1',
      savedChildIds: [],
      activeRangeId: null,
      ancestorIds: [],
    });
    expect(filtered.length).toBe(2);
  });

  it('playback outside parent warning condition', () => {
    const parentStart = Date.parse('2025-01-01T00:00:00.000Z');
    const parentEnd = Date.parse('2025-03-01T00:00:00.000Z');
    expect(isPlaybackOutsideParentWindow(
      Date.parse('2025-04-01T00:00:00.000Z'),
      parentStart,
      parentEnd,
    )).toBe(true);
    expect(isPlaybackOutsideParentWindow(
      Date.parse('2025-02-01T00:00:00.000Z'),
      parentStart,
      parentEnd,
    )).toBe(false);
  });

  it('guided playback uses cursor working segment', () => {
    const cursorMs = Date.parse('2025-01-08T00:00:00.000Z');
    const parentStart = Date.parse('2025-01-10T00:00:00.000Z');
    const parentEnd = Date.parse('2025-03-01T00:00:00.000Z');
    expect(isPlaybackOutsideParentWindow(
      cursorMs,
      parentStart,
      parentEnd,
      { cursor_time_ms: cursorMs, coverage_gap_end_ms: null },
    )).toBe(false);
    expect(isPlaybackOutsideParentWindow(
      Date.parse('2025-01-01T00:00:00.000Z'),
      parentStart,
      parentEnd,
      { cursor_time_ms: cursorMs, coverage_gap_end_ms: null },
    )).toBe(true);
  });

  it('explicit fit suppresses auto viewport refit', () => {
    const cfg = markExplicitViewportMove(createDefaultViewConfig(), 'fit-active');
    expect(shouldSuppressAutoViewportFit(cfg)).toBe(true);
  });

  it('strict range span returns null without times', () => {
    const span = rangeSpanPx(null, null, (ms) => ms / 1e6, 72, 800, { strict: true });
    expect(span).toBeNull();
  });

  it('user controlled view suppresses auto fit until explicit move', () => {
    const cfg = updateViewConfigFromVisibleDomain(createDefaultViewConfig(), {
      start: '2025-01-01T00:00:00.000Z',
      end: '2025-02-01T00:00:00.000Z',
      visibleBars: 48,
    }, { userControlled: true });
    expect(cfg.last_user_controlled_view).toBe(true);
    expect(shouldSuppressAutoViewportFit(cfg)).toBe(true);
  });

  it('buildBaseTimeDomain centers on preserved anchor', () => {
    const candles = Array.from({ length: 100 }, (_, i) => ({
      time: new Date(Date.parse('2025-01-01T00:00:00.000Z') + i * 3600000).toISOString(),
    }));
    const center = Date.parse('2025-01-03T12:00:00.000Z');
    const cfg = preserveCenterOnTimeframeSwitch(
      { ...createDefaultViewConfig('H1'), center_time_ms: center },
      'H1',
    );
    const domain = buildBaseTimeDomain(cfg, candles);
    expect(domain).not.toBeNull();
    expect(domain!.start.getTime()).toBeLessThanOrEqual(center);
    expect(domain!.end.getTime()).toBeGreaterThanOrEqual(center);
  });

  it('buildFitWindowFromViewConfig returns clamped ISO window', () => {
    const candles = Array.from({ length: 80 }, (_, i) => ({
      time: new Date(Date.parse('2025-01-01T00:00:00.000Z') + i * 86400000).toISOString(),
    }));
    const center = Date.parse('2025-02-15T00:00:00.000Z');
    const cfg = preserveCenterOnTimeframeSwitch(
      { ...createDefaultViewConfig('D1'), center_time_ms: center },
      'D1',
    );
    const fit = buildFitWindowFromViewConfig(cfg, candles);
    expect(fit?.start).toBeTruthy();
    expect(fit?.end).toBeTruthy();
    expect(Date.parse(fit!.end)).toBeGreaterThan(Date.parse(fit!.start));
  });

  it('clampSpanToCandleExtent shifts window inside loaded candles', () => {
    const candles = [{ time: '2025-01-10T00:00:00.000Z' }, { time: '2025-01-20T00:00:00.000Z' }];
    const start = Date.parse('2025-01-01T00:00:00.000Z');
    const end = Date.parse('2025-01-05T00:00:00.000Z');
    const clamped = clampSpanToCandleExtent(start, end, candles);
    expect(clamped.startMs).toBeGreaterThanOrEqual(Date.parse('2025-01-10T00:00:00.000Z'));
  });
});
