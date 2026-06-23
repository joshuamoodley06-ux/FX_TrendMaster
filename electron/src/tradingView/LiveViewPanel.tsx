import { useCallback, useEffect, useState } from 'react';
import {
  DEFAULT_TRADINGVIEW_DEBUG_MODE,
  normalizeTradingViewDebugMode,
  TRADINGVIEW_DEBUG_STORAGE_KEY,
} from '../chartRendererConfig';
import { TradingViewChart } from './TradingViewChart';
import type {
  FxtmCandleRow,
  TradingViewChartMode,
  TradingViewFitRequest,
  TradingViewOverlayMode,
  TradingViewOverlaySet,
  TradingViewSelectedCandle,
  TradingViewSelectedCandleMode,
  TradingViewSelectionDebugEvent,
} from './types';

const emptySelectionDebug: Required<TradingViewSelectionDebugEvent> = {
  clickHandlerAttached: false,
  crosshairReceived: false,
  pointerOverChart: false,
  chartContainerPointerEvents: '',
  overlayPointerEvents: '',
  lastClickEventObject: '',
  clickReceived: false,
  rawTvTime: '',
  normalizedClickTime: '',
  displayCandleCount: 0,
  matchedCandle: false,
  matchedCandleTime: '',
  markerCount: 0,
  selMarkerPresent: false,
};

type LiveViewPanelProps = {
  candles: FxtmCandleRow[];
  symbol: string;
  timeframe: string;
  sourceTimeframe: string;
  loadedTimeframe?: string | null;
  revision?: number;
  statusMessage?: string;
  overlayMode?: TradingViewOverlayMode;
  overlays?: TradingViewOverlaySet;
  fitRequest?: TradingViewFitRequest | null;
  chartMode?: TradingViewChartMode;
  selectionMode?: TradingViewSelectedCandleMode;
  selectedCandle?: TradingViewSelectedCandle | null;
  crosshairCandle?: TradingViewSelectedCandle | null;
  selectionWarning?: string | null;
  onCrosshairCandle?: (candle: TradingViewSelectedCandle | null) => void;
  onCandleClick?: (candle: TradingViewSelectedCandle) => void;
  onOverlayModeChange?: (mode: TradingViewOverlayMode) => void;
  onSelectionModeChange?: (mode: TradingViewSelectedCandleMode) => void;
};

export function LiveViewPanel({
  candles,
  symbol,
  timeframe,
  sourceTimeframe,
  loadedTimeframe,
  revision,
  statusMessage,
  overlayMode = 'off',
  overlays,
  fitRequest,
  chartMode = 'latest',
  selectionMode = 'off',
  selectedCandle,
  crosshairCandle,
  selectionWarning,
  onCrosshairCandle,
  onCandleClick,
  onOverlayModeChange,
  onSelectionModeChange,
}: LiveViewPanelProps) {
  const [debugMode] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_TRADINGVIEW_DEBUG_MODE;
    return normalizeTradingViewDebugMode(window.localStorage.getItem(TRADINGVIEW_DEBUG_STORAGE_KEY));
  });
  const [stats, setStats] = useState({ rendered: 0, dropped: 0 });
  const [selectionDebug, setSelectionDebug] = useState<Required<TradingViewSelectionDebugEvent>>(emptySelectionDebug);
  const handleStats = useCallback((next: { rendered: number; dropped: number }) => setStats(next), []);
  const handleSelectionDebug = useCallback((event: TradingViewSelectionDebugEvent) => {
    setSelectionDebug((prev) => ({ ...prev, ...event }));
  }, []);
  useEffect(() => {
    setSelectionDebug(emptySelectionDebug);
  }, [timeframe, chartMode, selectionMode, revision]);
  const loadedMatches = !loadedTimeframe || String(loadedTimeframe).toUpperCase() === String(timeframe).toUpperCase();
  const empty = candles.length === 0 || stats.rendered === 0;
  const overlaySummary = overlayMode === 'readonly' && overlays?.priceLines.length
    ? overlays.priceLines.slice(0, 4).map((line) => `${line.label} ${line.price.toFixed(2)}`).join(' · ')
    : '';
  const displayCandle = selectionMode === 'readonly' ? (crosshairCandle || selectedCandle || null) : null;
  const displayIsSelected = !!(selectedCandle && displayCandle && selectedCandle.time === displayCandle.time && selectedCandle.chartTimeframe === displayCandle.chartTimeframe);
  const overlayCount = (overlays?.priceLines.length || 0) + (overlays?.markers.length || 0);
  const rangeOverlayCount = overlays?.debug?.rangeOverlayCount ?? (overlays?.priceLines.filter((line) => line.role !== 'parent').length || 0);
  const rhRlLineCount = overlays?.debug?.rhRlLineCount ?? (overlays?.priceLines.filter((line) => line.kind === 'RH' || line.kind === 'RL').length || 0);
  const bosMarkerCount = overlays?.debug?.bosMarkerCount ?? (overlays?.markers.length || 0);
  const selectedRangeFallbackUsed = overlays?.debug?.selectedRangeFallbackUsed ?? false;
  const selMarkerPresent = selectionDebug.selMarkerPresent;
  const selectionState = selectionMode === 'readonly'
    ? selectedCandle ? 'selected' : crosshairCandle ? 'preview' : 'ready'
    : 'off';
  const cycleOverlayMode = () => {
    onOverlayModeChange?.(overlayMode === 'readonly' ? 'off' : 'readonly');
  };
  const cycleSelectionMode = () => {
    onSelectionModeChange?.(selectionMode === 'readonly' ? 'off' : 'readonly');
  };
  const selectionBridgeArmed = selectionMode === 'readonly';

  return (
    <section className="tradingViewLivePanel" aria-label="TradingView Live View">
      <div className="tradingViewLiveHeader">
        <div>
          <b>TradingView Live View</b>
          <span>{symbol} · tab {timeframe} · source {sourceTimeframe} · loaded {loadedTimeframe || '—'}</span>
        </div>
        <div className={`tradingViewLiveStatus${loadedMatches ? '' : ' warning'}`}>
          {loadedMatches ? `${stats.rendered} bars` : 'Feed mismatch'}
          {stats.dropped ? ` · ${stats.dropped} dropped` : ''}
          {` · renderer tradingview · mode ${chartMode} · overlays ${overlayMode}${overlayMode === 'readonly' ? ` (${overlayCount})` : ''}`}
          {` · selection ${selectionMode}${selectionMode === 'readonly' ? ` (${selectionState})` : ''}`}
        </div>
      </div>
      <div className="tradingViewVisibleStatus" aria-label="TradingView visible overlay and selection status">
        <span>Renderer: tradingview</span>
        <span>Display mode: {chartMode}</span>
        <button
          type="button"
          className={`tradingViewStatusChip ${overlayMode === 'readonly' ? 'active' : ''}`}
          onClick={cycleOverlayMode}
          title="Toggle TradingView readonly overlays"
        >
          Overlays: {overlayMode === 'readonly' ? 'Readonly' : 'Off'}
        </button>
        <span>Range overlays: {rangeOverlayCount}</span>
        <span>RH/RL lines: {rhRlLineCount}</span>
        <span>BOS markers: {bosMarkerCount}</span>
        <button
          type="button"
          className={`tradingViewStatusChip ${selectionMode === 'readonly' ? 'active' : ''}`}
          onClick={cycleSelectionMode}
          title="Toggle TradingView readonly candle selection"
        >
          Selection: {selectionMode === 'readonly' ? 'Readonly' : 'Off'}
        </button>
        <span>Selected candle: {selectedCandle?.time || 'none'}</span>
        <span>SEL marker: {selMarkerPresent ? 'yes' : 'no'}</span>
      </div>
      {!loadedMatches && (
        <div className="tradingViewLiveNotice warning">
          Loaded candle timeframe does not match the selected tab. Live View is read-only and will not enable mapping input.
        </div>
      )}
      {empty && (
        <div className="tradingViewLiveNotice">
          {statusMessage || `No valid ${timeframe} candles available for Live View.`}
        </div>
      )}
      {overlaySummary && (
        <div className="tradingViewLiveNotice readonlyOverlaySummary">
          {overlaySummary}{overlays?.markers.length ? ` · BOS ${overlays.markers.length}` : ''}
        </div>
      )}
      {selectionWarning && (
        <div className="tradingViewLiveNotice warning">
          {selectionWarning}
        </div>
      )}
      {selectionMode === 'readonly' && (
        <div className={`tradingViewSelectionStrip${selectedCandle ? ' hasSelection' : ''}`}>
          {displayCandle ? (
            <>
              <b>{displayIsSelected ? 'Selected' : 'Preview'} {displayCandle.chartTimeframe}</b>
              <span>{displayCandle.time}</span>
              <span>O {displayCandle.open.toFixed(2)}</span>
              <span>H {displayCandle.high.toFixed(2)}</span>
              <span>L {displayCandle.low.toFixed(2)}</span>
              <span>C {displayCandle.close.toFixed(2)}</span>
            </>
          ) : (
            <span>TradingView selection bridge ready. Crosshair previews; click commits TV-only selection.</span>
          )}
        </div>
      )}
      <div
        className={`tradingViewSelectionDebug${debugMode === 'dev' ? '' : ' debugHidden'}`}
        aria-label="TradingView selection debug"
        aria-hidden={debugMode === 'dev' ? 'false' : 'true'}
        data-debug-mode={debugMode}
        data-click-received={selectionDebug.clickReceived ? 'yes' : 'no'}
        data-raw-tv-time={selectionDebug.rawTvTime}
        data-normalized-click-time={selectionDebug.normalizedClickTime}
        data-matched-candle={selectionDebug.matchedCandle ? 'yes' : 'no'}
        data-matched-candle-time={selectionDebug.matchedCandleTime}
        data-selected-time={selectedCandle?.time || ''}
        data-visible-candles={selectionDebug.displayCandleCount || stats.rendered}
        data-display-mode={chartMode}
        data-marker-count={selectionDebug.markerCount}
        data-sel-marker-present={selectionDebug.selMarkerPresent ? 'yes' : 'no'}
        data-overlay-mode={overlayMode}
        data-range-overlay-count={rangeOverlayCount}
        data-rh-rl-line-count={rhRlLineCount}
        data-bos-marker-count={bosMarkerCount}
        data-selected-range-fallback-used={selectedRangeFallbackUsed ? 'yes' : 'no'}
        data-click-handler-attached={selectionDebug.clickHandlerAttached ? 'yes' : 'no'}
        data-crosshair-received={selectionDebug.crosshairReceived ? 'yes' : 'no'}
        data-pointer-over-chart={selectionDebug.pointerOverChart ? 'yes' : 'no'}
        data-chart-container-pointer-events={selectionDebug.chartContainerPointerEvents}
        data-overlay-pointer-events={selectionDebug.overlayPointerEvents}
        data-last-click-event-object={selectionDebug.lastClickEventObject}
        data-selection-bridge={selectionBridgeArmed ? 'armed' : 'off'}
      >
        <span>TV selection debug</span>
        <span>Renderer: tradingview</span>
        <span>Selection bridge: {selectionBridgeArmed ? 'armed' : 'off'}</span>
        <span>Click handler attached: {selectionBridgeArmed ? (selectionDebug.clickHandlerAttached ? 'yes' : 'no') : 'bridge off'}</span>
        <span>Crosshair received: {selectionBridgeArmed ? (selectionDebug.crosshairReceived ? 'yes' : 'no') : 'bridge off'}</span>
        <span>Pointer over chart: {selectionBridgeArmed ? (selectionDebug.pointerOverChart ? 'yes' : 'no') : 'bridge off'}</span>
        <span>Chart container pointer-events: {selectionDebug.chartContainerPointerEvents || 'unknown'}</span>
        <span>Overlay pointer-events: {selectionDebug.overlayPointerEvents || 'unknown'}</span>
        <span>Last click event object: {selectionDebug.lastClickEventObject || 'none'}</span>
        <span>Selection mode: {selectionMode}</span>
        <span>Display mode: {chartMode}</span>
        <span>Visible/display candles: {selectionDebug.displayCandleCount || stats.rendered}</span>
        <span>Click received: {selectionBridgeArmed ? (selectionDebug.clickReceived ? 'yes' : 'no') : 'bridge off'}</span>
        <span>Raw tv click time: {selectionDebug.rawTvTime || 'none'}</span>
        <span>Normalized click time: {selectionDebug.normalizedClickTime || 'none'}</span>
        <span>Matched candle: {selectionBridgeArmed ? (selectionDebug.matchedCandle ? 'yes' : 'no') : 'bridge off'}</span>
        <span>Matched candle time: {selectionDebug.matchedCandleTime || 'none'}</span>
        <span>Selected candle state: {selectedCandle?.time || 'none'}</span>
        <span>Marker count: {selectionDebug.markerCount}</span>
        <span>SEL marker present: {selectionDebug.selMarkerPresent ? 'yes' : 'no'}</span>
        <span>Overlay mode: {overlayMode}</span>
        <span>Range overlay count: {rangeOverlayCount}</span>
        <span>RH/RL line count: {rhRlLineCount}</span>
        <span>BOS marker count: {bosMarkerCount}</span>
        <span>Selected range fallback used: {selectedRangeFallbackUsed ? 'yes' : 'no'}</span>
      </div>
      <TradingViewChart
        candles={candles}
        timeframe={timeframe}
        chartMode={chartMode}
        revision={revision}
        overlays={overlayMode === 'readonly' ? overlays : undefined}
        fitRequest={fitRequest}
        symbol={symbol}
        sourceTimeframe={sourceTimeframe}
        selectedCandle={selectionMode === 'readonly' ? selectedCandle : null}
        selectionBridgeEnabled={selectionMode === 'readonly'}
        onCrosshairCandle={selectionMode === 'readonly' ? onCrosshairCandle : undefined}
        onCandleClick={selectionMode === 'readonly' ? onCandleClick : undefined}
        onSelectionDebug={selectionMode === 'readonly' ? handleSelectionDebug : undefined}
        onStats={handleStats}
      />
    </section>
  );
}
