import { useCallback, useState } from 'react';
import { TradingViewChart } from './TradingViewChart';
import type {
  FxtmCandleRow,
  TradingViewFitRequest,
  TradingViewOverlayMode,
  TradingViewOverlaySet,
  TradingViewSelectedCandle,
  TradingViewSelectedCandleMode,
} from './types';

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
  selectionMode?: TradingViewSelectedCandleMode;
  selectedCandle?: TradingViewSelectedCandle | null;
  crosshairCandle?: TradingViewSelectedCandle | null;
  selectionWarning?: string | null;
  onCrosshairCandle?: (candle: TradingViewSelectedCandle | null) => void;
  onCandleClick?: (candle: TradingViewSelectedCandle) => void;
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
  selectionMode = 'off',
  selectedCandle,
  crosshairCandle,
  selectionWarning,
  onCrosshairCandle,
  onCandleClick,
}: LiveViewPanelProps) {
  const [stats, setStats] = useState({ rendered: 0, dropped: 0 });
  const handleStats = useCallback((next: { rendered: number; dropped: number }) => setStats(next), []);
  const loadedMatches = !loadedTimeframe || String(loadedTimeframe).toUpperCase() === String(timeframe).toUpperCase();
  const empty = candles.length === 0 || stats.rendered === 0;
  const overlaySummary = overlayMode === 'readonly' && overlays?.priceLines.length
    ? overlays.priceLines.slice(0, 4).map((line) => `${line.label} ${line.price.toFixed(2)}`).join(' · ')
    : '';
  const displayCandle = selectionMode === 'readonly' ? (crosshairCandle || selectedCandle || null) : null;
  const displayIsSelected = !!(selectedCandle && displayCandle && selectedCandle.time === displayCandle.time && selectedCandle.chartTimeframe === displayCandle.chartTimeframe);

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
          {overlayMode === 'readonly' ? ` · overlays ${(overlays?.priceLines.length || 0) + (overlays?.markers.length || 0)}` : ' · overlays off'}
        </div>
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
      <TradingViewChart
        candles={candles}
        timeframe={timeframe}
        revision={revision}
        overlays={overlayMode === 'readonly' ? overlays : undefined}
        fitRequest={overlayMode === 'readonly' ? fitRequest : null}
        symbol={symbol}
        sourceTimeframe={sourceTimeframe}
        selectedCandle={selectionMode === 'readonly' ? selectedCandle : null}
        selectionBridgeEnabled={selectionMode === 'readonly'}
        onCrosshairCandle={selectionMode === 'readonly' ? onCrosshairCandle : undefined}
        onCandleClick={selectionMode === 'readonly' ? onCandleClick : undefined}
        onStats={handleStats}
      />
    </section>
  );
}
