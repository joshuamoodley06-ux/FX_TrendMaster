export type TradeIdeaPickKind = 'entry' | 'sl' | 'tp1' | 'tp2' | 'tp3';

export type ChartTradeIdeaPoint = {
  price: number;
  time: string;
};

export type ChartTradeIdea = {
  id: string;
  symbol: string;
  timeframe: string;
  direction: 'LONG' | 'SHORT';
  entry: ChartTradeIdeaPoint;
  sl: ChartTradeIdeaPoint | null;
  tp1: ChartTradeIdeaPoint | null;
  tp2: ChartTradeIdeaPoint | null;
  tp3: ChartTradeIdeaPoint | null;
  rangeId?: string | null;
  rangeScope?: string | null;
  structureLayer?: string | null;
  caseRef?: string | null;
  caseLabel?: string | null;
  notes?: string;
  status: 'saved';
  createdAt: string;
  updatedAt: string;
  analystExport: {
    schemaVersion: 'trade_idea_v1';
    rrTp1: number | null;
    rrTp2: number | null;
    rrTp3: number | null;
    riskPoints: number | null;
    rewardTp1Points: number | null;
    rewardTp2Points: number | null;
    rewardTp3Points: number | null;
  };
};

export type ChartTradeIdeaDraft = {
  entry: ChartTradeIdeaPoint | null;
  sl: ChartTradeIdeaPoint | null;
  tp1: ChartTradeIdeaPoint | null;
  tp2: ChartTradeIdeaPoint | null;
  tp3: ChartTradeIdeaPoint | null;
};

export const TRADE_IDEA_COLORS = {
  entry: '#ffffff',
  sl: '#ff5b6e',
  tp: '#35e783',
  riskFill: 'rgba(255,91,110,.14)',
  rewardFill: 'rgba(53,231,131,.12)',
  longEntry: '#60a5fa',
  shortEntry: '#f472b6',
} as const;

const STORE_KEY = 'fx_tm_chart_trade_ideas_v1';

function safeParseStore(raw: string | null): Record<string, ChartTradeIdea[]> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as Record<string, ChartTradeIdea[]> : {};
  } catch {
    return {};
  }
}

export function newTradeIdeaId(): string {
  return `ti_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function tradeIdeasStorageKey(symbol: string, timeframe: string, caseRef: string): string {
  return `${String(symbol || 'XAUUSD').toUpperCase()}_${String(timeframe || 'D1').toUpperCase()}_${caseRef || 'global'}`;
}

export function loadChartTradeIdeas(storageKey: string): ChartTradeIdea[] {
  if (typeof window === 'undefined' || !storageKey) return [];
  const store = safeParseStore(window.localStorage.getItem(STORE_KEY));
  return Array.isArray(store[storageKey]) ? store[storageKey] : [];
}

export function saveChartTradeIdeas(storageKey: string, ideas: ChartTradeIdea[]): void {
  if (typeof window === 'undefined' || !storageKey) return;
  const store = safeParseStore(window.localStorage.getItem(STORE_KEY));
  store[storageKey] = ideas;
  window.localStorage.setItem(STORE_KEY, JSON.stringify(store));
}

export function emptyTradeIdeaDraft(): ChartTradeIdeaDraft {
  return { entry: null, sl: null, tp1: null, tp2: null, tp3: null };
}

export function inferTradeDirection(entry: ChartTradeIdeaPoint | null, sl: ChartTradeIdeaPoint | null): 'LONG' | 'SHORT' {
  if (!entry || !sl) return 'LONG';
  return entry.price >= sl.price ? 'LONG' : 'SHORT';
}

export function computeTradeIdeaMetrics(
  direction: 'LONG' | 'SHORT',
  entry: ChartTradeIdeaPoint,
  sl: ChartTradeIdeaPoint | null,
  tp1: ChartTradeIdeaPoint | null,
  tp2: ChartTradeIdeaPoint | null,
  tp3: ChartTradeIdeaPoint | null,
) {
  const risk = sl ? Math.abs(entry.price - sl.price) : null;
  const reward = (tp: ChartTradeIdeaPoint | null) => {
    if (!tp || !risk || risk <= 0) return null;
    const raw = direction === 'LONG' ? tp.price - entry.price : entry.price - tp.price;
    return raw / risk;
  };
  const rewardPts = (tp: ChartTradeIdeaPoint | null) => {
    if (!tp) return null;
    return direction === 'LONG' ? tp.price - entry.price : entry.price - tp.price;
  };
  return {
    riskPoints: risk,
    rewardTp1Points: rewardPts(tp1),
    rewardTp2Points: rewardPts(tp2),
    rewardTp3Points: rewardPts(tp3),
    rrTp1: reward(tp1),
    rrTp2: reward(tp2),
    rrTp3: reward(tp3),
  };
}

export function draftHasAnyPoint(draft: ChartTradeIdeaDraft): boolean {
  return !!(draft.entry || draft.sl || draft.tp1 || draft.tp2 || draft.tp3);
}

export function draftReadyToSave(draft: ChartTradeIdeaDraft): boolean {
  return !!(draft.entry && draft.sl && draft.tp1);
}

export function buildTradeIdeaFromDraft(args: {
  draft: ChartTradeIdeaDraft;
  symbol: string;
  timeframe: string;
  rangeId?: string | null;
  rangeScope?: string | null;
  structureLayer?: string | null;
  caseRef?: string | null;
  caseLabel?: string | null;
  notes?: string;
}): ChartTradeIdea | null {
  const { draft } = args;
  if (!draft.entry || !draft.sl || !draft.tp1) return null;
  const direction = inferTradeDirection(draft.entry, draft.sl);
  const metrics = computeTradeIdeaMetrics(direction, draft.entry, draft.sl, draft.tp1, draft.tp2, draft.tp3);
  const now = new Date().toISOString();
  return {
    id: newTradeIdeaId(),
    symbol: args.symbol,
    timeframe: args.timeframe,
    direction,
    entry: draft.entry,
    sl: draft.sl,
    tp1: draft.tp1,
    tp2: draft.tp2,
    tp3: draft.tp3,
    rangeId: args.rangeId || null,
    rangeScope: args.rangeScope || null,
    structureLayer: args.structureLayer || null,
    caseRef: args.caseRef || null,
    caseLabel: args.caseLabel || null,
    notes: args.notes || '',
    status: 'saved',
    createdAt: now,
    updatedAt: now,
    analystExport: {
      schemaVersion: 'trade_idea_v1',
      ...metrics,
    },
  };
}

export function exportTradeIdeasBundle(storageKey: string, ideas: ChartTradeIdea[]) {
  return {
    schemaVersion: 'trade_ideas_export_v1',
    storageKey,
    exportedAt: new Date().toISOString(),
    count: ideas.length,
    ideas,
  };
}

export function tradeIdeaEndDate(
  entry: ChartTradeIdeaPoint,
  tps: (ChartTradeIdeaPoint | null)[],
  defaultBarMs: number,
): Date {
  const entryMs = new Date(entry.time).getTime();
  let latest = entryMs;
  for (const tp of tps) {
    if (!tp?.time) continue;
    const ms = new Date(tp.time).getTime();
    if (Number.isFinite(ms) && ms > latest) latest = ms;
  }
  if (latest <= entryMs) return new Date(entryMs + Math.max(defaultBarMs, 3600000) * 28);
  return new Date(latest);
}

export type TradeIdeaOverlaySpec = {
  id?: string;
  direction: 'LONG' | 'SHORT';
  entry: ChartTradeIdeaPoint;
  sl: ChartTradeIdeaPoint | null;
  tp1: ChartTradeIdeaPoint | null;
  tp2: ChartTradeIdeaPoint | null;
  tp3: ChartTradeIdeaPoint | null;
  draft?: boolean;
  selected?: boolean;
  analystExport?: ChartTradeIdea['analystExport'];
};

export function overlaySpecFromDraft(draft: ChartTradeIdeaDraft, draftFlag = true): TradeIdeaOverlaySpec | null {
  if (!draft.entry) return null;
  return {
    direction: inferTradeDirection(draft.entry, draft.sl),
    entry: draft.entry,
    sl: draft.sl,
    tp1: draft.tp1,
    tp2: draft.tp2,
    tp3: draft.tp3,
    draft: draftFlag,
  };
}

export function overlaySpecFromIdea(idea: ChartTradeIdea, selected = false): TradeIdeaOverlaySpec {
  return {
    id: idea.id,
    direction: idea.direction,
    entry: idea.entry,
    sl: idea.sl,
    tp1: idea.tp1,
    tp2: idea.tp2,
    tp3: idea.tp3,
    selected,
    analystExport: idea.analystExport,
  };
}

export function downloadTradeIdeasJson(storageKey: string, ideas: ChartTradeIdea[]) {
  const payload = exportTradeIdeasBundle(storageKey, ideas);
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `trade_ideas_${storageKey.replace(/[^a-zA-Z0-9_-]+/g, '_')}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
