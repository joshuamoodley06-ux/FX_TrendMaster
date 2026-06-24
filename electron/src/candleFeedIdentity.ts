/** Candle feed identity — mapping layer/timeframe must match loaded candles before marking. */

export type StructureLayerId = 'MACRO' | 'WEEKLY' | 'DAILY' | 'INTRADAY' | 'MICRO';

export type LoadedCandleContext = {
  requestId: number;
  symbol: string;
  caseId: string;
  chartTimeframe: string;
  sourceTimeframe: string;
  structureLayer: StructureLayerId;
  candleCount: number;
  loadedAt: string;
};

export type ActiveMappingFeedSnapshot = {
  symbol: string;
  caseId: string;
  chartTimeframe: string;
  sourceTimeframe: string;
  structureLayer: StructureLayerId;
  candleLoadInFlight: boolean;
  candleCount: number;
};

export type CandleFeedGuardResult = {
  ready: boolean;
  message: string;
  reloadChartTimeframe?: string;
  mismatch?: 'loading' | 'empty' | 'loaded-tf' | 'source-tf' | 'layer' | 'chart-tab';
};

const LAYER_ORDER: StructureLayerId[] = ['MACRO', 'WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'];

export function normalizeStructureLayerId(value: unknown): StructureLayerId | null {
  const raw = String(value || '').toUpperCase();
  const aliases: Record<string, StructureLayerId> = {
    MN1: 'MACRO',
    MACRO: 'MACRO',
    W1: 'WEEKLY',
    WEEKLY: 'WEEKLY',
    D1: 'DAILY',
    DAILY: 'DAILY',
    H4: 'INTRADAY',
    H1: 'INTRADAY',
    INTRADAY: 'INTRADAY',
    M15: 'MICRO',
    M5: 'MICRO',
    MICRO: 'MICRO',
  };
  const layer = aliases[raw] || (raw as StructureLayerId);
  return LAYER_ORDER.includes(layer) ? layer : null;
}

export function allowedChartTimeframesForLayer(layer: StructureLayerId): string[] {
  if (layer === 'MACRO') return ['MN1', 'W1'];
  if (layer === 'WEEKLY') return ['W1'];
  if (layer === 'DAILY') return ['D1'];
  if (layer === 'INTRADAY') return ['H4', 'H1'];
  return ['M15', 'M5'];
}

export function defaultSourceTimeframeForLayer(layer: StructureLayerId): string {
  return ({
    MACRO: 'MN1',
    WEEKLY: 'W1',
    DAILY: 'D1',
    INTRADAY: 'H1',
    MICRO: 'M15',
  } as Record<StructureLayerId, string>)[layer];
}

export function defaultChartTimeframeForLayer(layer: StructureLayerId): string {
  return defaultSourceTimeframeForLayer(layer);
}

export function isChartTimeframeAllowedForLayer(chartTf: string, layer: StructureLayerId): boolean {
  return allowedChartTimeframesForLayer(layer).includes(String(chartTf || '').toUpperCase());
}

export function buildLoadedCandleContext(args: {
  requestId: number;
  symbol: string;
  caseId: string;
  chartTimeframe: string;
  sourceTimeframe: string;
  structureLayer: string;
  candleCount: number;
  loadedAt?: string;
}): LoadedCandleContext | null {
  const layer = normalizeStructureLayerId(args.structureLayer);
  if (!layer) return null;
  return {
    requestId: args.requestId,
    symbol: String(args.symbol || '').toUpperCase(),
    caseId: String(args.caseId || ''),
    chartTimeframe: String(args.chartTimeframe || '').toUpperCase(),
    sourceTimeframe: String(args.sourceTimeframe || '').toUpperCase(),
    structureLayer: layer,
    candleCount: Math.max(0, Number(args.candleCount) || 0),
    loadedAt: args.loadedAt || new Date().toISOString(),
  };
}

/** TV Map preserve keeps visible candles but may skip reload that normally stamps loaded context. */
export function rehydrateLoadedCandleContextForVisibleFeed(args: {
  loaded: LoadedCandleContext | null;
  requestId: number;
  symbol: string;
  caseId: string;
  chartTimeframe: string;
  sourceTimeframe: string;
  structureLayer: string;
  candleCount: number;
}): LoadedCandleContext | null {
  const chartTf = String(args.chartTimeframe || '').toUpperCase();
  if (args.candleCount <= 0 || !chartTf) return args.loaded;
  if (
    args.loaded
    && args.loaded.chartTimeframe === chartTf
    && args.loaded.candleCount > 0
  ) {
    return args.loaded;
  }
  return buildLoadedCandleContext({
    requestId: args.requestId,
    symbol: args.symbol,
    caseId: args.caseId,
    chartTimeframe: chartTf,
    sourceTimeframe: args.sourceTimeframe,
    structureLayer: args.structureLayer,
    candleCount: args.candleCount,
  });
}

export function isStaleCandleLoadResult(args: {
  startedRequestId: number;
  startedTf: string;
  latestRequestId: number;
  activeChartTf: string;
}): boolean {
  const activeTf = String(args.activeChartTf || '').toUpperCase();
  const startedTf = String(args.startedTf || '').toUpperCase();
  return args.startedRequestId !== args.latestRequestId || startedTf !== activeTf;
}

export function evaluateCandleFeedGuard(
  active: ActiveMappingFeedSnapshot,
  loaded: LoadedCandleContext | null,
): CandleFeedGuardResult {
  const chartTf = String(active.chartTimeframe || '').toUpperCase();
  const sourceTf = String(active.sourceTimeframe || '').toUpperCase();
  const layer = normalizeStructureLayerId(active.structureLayer);
  if (!layer) {
    return { ready: false, message: 'Unknown mapping layer — cannot plot yet.' };
  }
  if (!isChartTimeframeAllowedForLayer(chartTf, layer)) {
    const expected = allowedChartTimeframesForLayer(layer).join(' or ');
    return {
      ready: false,
      mismatch: 'chart-tab',
      message: `Chart tab is ${chartTf} but mapping layer is ${layer}. Switch chart to ${expected}.`,
      reloadChartTimeframe: defaultChartTimeframeForLayer(layer),
    };
  }
  if (active.candleLoadInFlight) {
    return {
      ready: false,
      mismatch: 'loading',
      message: `Loading ${layer === 'MICRO' ? 'Micro' : layer} candles (${chartTf || defaultChartTimeframeForLayer(layer)})…`,
    };
  }
  if (!loaded || loaded.candleCount <= 0 || active.candleCount <= 0) {
    return {
      ready: false,
      mismatch: 'empty',
      message: `No ${chartTf || defaultChartTimeframeForLayer(layer)} candles loaded yet.`,
      reloadChartTimeframe: chartTf || defaultChartTimeframeForLayer(layer),
    };
  }
  if (loaded.chartTimeframe !== chartTf) {
    return {
      ready: false,
      mismatch: 'loaded-tf',
      message: `Candle feed mismatch: expected ${chartTf} for ${layer}, loaded ${loaded.chartTimeframe}. Reloading ${chartTf}…`,
      reloadChartTimeframe: chartTf,
    };
  }
  if (loaded.structureLayer !== layer) {
    return {
      ready: false,
      mismatch: 'layer',
      message: `Candle feed mismatch: UI layer ${layer}, loaded feed is ${loaded.structureLayer}. Reloading ${chartTf}…`,
      reloadChartTimeframe: chartTf,
    };
  }
  const allowedSources = allowedChartTimeframesForLayer(layer);
  if (!allowedSources.includes(sourceTf)) {
    return {
      ready: false,
      mismatch: 'source-tf',
      message: `Source timeframe ${sourceTf} is invalid for ${layer}. Use ${allowedSources.join(' or ')}.`,
    };
  }
  if (loaded.sourceTimeframe !== sourceTf) {
    return {
      ready: false,
      mismatch: 'source-tf',
      message: `Candle feed mismatch: source ${sourceTf}, loaded source ${loaded.sourceTimeframe}. Reloading ${chartTf}…`,
      reloadChartTimeframe: chartTf,
    };
  }
  if (loaded.symbol && active.symbol && loaded.symbol !== String(active.symbol).toUpperCase()) {
    return {
      ready: false,
      message: `Candle feed mismatch: loaded ${loaded.symbol}, active ${active.symbol}. Reloading ${chartTf}…`,
      reloadChartTimeframe: chartTf,
    };
  }
  return { ready: true, message: '' };
}

export function buildCandleFeedStatusLine(args: {
  structureLayer: string;
  sourceTimeframe: string;
  chartTimeframe: string;
  loaded: LoadedCandleContext | null;
  loading: boolean;
  candleCount: number;
}): string {
  const layer = normalizeStructureLayerId(args.structureLayer) || String(args.structureLayer || '?');
  const chartTf = String(args.chartTimeframe || '').toUpperCase();
  const sourceTf = String(args.sourceTimeframe || '').toUpperCase();
  const loadedTf = args.loaded?.chartTimeframe || '—';
  const count = args.loaded?.candleCount ?? args.candleCount ?? 0;
  const guard = evaluateCandleFeedGuard(
    {
      symbol: args.loaded?.symbol || '',
      caseId: args.loaded?.caseId || '',
      chartTimeframe: chartTf,
      sourceTimeframe: sourceTf,
      structureLayer: layer as StructureLayerId,
      candleLoadInFlight: args.loading,
      candleCount: count,
    },
    args.loaded,
  );
  const base = `Layer ${layer} · Source ${sourceTf} · Tab ${chartTf} · Loaded ${loadedTf} · ${count} bars`;
  if (args.loading) return `${base} · loading…`;
  if (!guard.ready) return `${base} · FEED MISMATCH`;
  return base;
}

export function childLayerAfterTransition(parentLayer: StructureLayerId): StructureLayerId | null {
  const idx = LAYER_ORDER.indexOf(parentLayer);
  return idx >= 0 && idx < LAYER_ORDER.length - 1 ? LAYER_ORDER[idx + 1] : null;
}
