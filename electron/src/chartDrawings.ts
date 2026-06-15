export type ChartDrawTool = 'off' | 'hline' | 'vline' | 'text' | 'edit';

export type ChartHLineDrawing = {
  id: string;
  kind: 'hline';
  price: number;
  /** 0 = plot left edge, 1 = plot right edge */
  xLeftRatio?: number;
  xRightRatio?: number;
  color: string;
};

export type ChartVLineDrawing = {
  id: string;
  kind: 'vline';
  time: string;
  /** 0 = plot top, 1 = plot bottom */
  yTopRatio: number;
  yBottomRatio: number;
  color: string;
};

export type ChartTextDrawing = {
  id: string;
  kind: 'text';
  time: string;
  price: number;
  text: string;
  color: string;
};

export type ChartDrawing = ChartHLineDrawing | ChartVLineDrawing | ChartTextDrawing;

export const CHART_DRAWING_COLORS = [
  '#00d4aa',
  '#ffbf2f',
  '#ff5b6e',
  '#35e783',
  '#60a5fa',
  '#c084fc',
  '#f472b6',
  '#ffffff',
] as const;

const DRAWINGS_STORE_KEY = 'fx_tm_chart_drawings_v1';
const REPLAY_CURSOR_STORE_KEY = 'fx_tm_replay_cursor_by_case_v1';
const LEGACY_REPLAY_CURSOR_KEY = 'fx_tm_replay_cursor_time_v087_22';

function safeParseRecord(raw: string | null): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as Record<string, string> : {};
  } catch {
    return {};
  }
}

function safeParseDrawings(raw: string | null): Record<string, ChartDrawing[]> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as Record<string, ChartDrawing[]> : {};
  } catch {
    return {};
  }
}

export function newDrawingId(): string {
  return `dr_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function loadChartDrawings(storageKey: string): ChartDrawing[] {
  if (typeof window === 'undefined' || !storageKey) return [];
  const store = safeParseDrawings(window.localStorage.getItem(DRAWINGS_STORE_KEY));
  return Array.isArray(store[storageKey]) ? store[storageKey] : [];
}

export function saveChartDrawings(storageKey: string, drawings: ChartDrawing[]): void {
  if (typeof window === 'undefined' || !storageKey) return;
  const store = safeParseDrawings(window.localStorage.getItem(DRAWINGS_STORE_KEY));
  store[storageKey] = drawings;
  window.localStorage.setItem(DRAWINGS_STORE_KEY, JSON.stringify(store));
}

export function loadReplayCursorForKey(storageKey: string): string | null {
  if (typeof window === 'undefined' || !storageKey) return null;
  const store = safeParseRecord(window.localStorage.getItem(REPLAY_CURSOR_STORE_KEY));
  if (store[storageKey]) return store[storageKey];
  const legacy = window.localStorage.getItem(LEGACY_REPLAY_CURSOR_KEY);
  return legacy || null;
}

export function saveReplayCursorForKey(storageKey: string, time: string | null): void {
  if (typeof window === 'undefined' || !storageKey) return;
  const store = safeParseRecord(window.localStorage.getItem(REPLAY_CURSOR_STORE_KEY));
  if (time) store[storageKey] = time;
  else delete store[storageKey];
  window.localStorage.setItem(REPLAY_CURSOR_STORE_KEY, JSON.stringify(store));
  if (time) window.localStorage.setItem(LEGACY_REPLAY_CURSOR_KEY, time);
}

export function normalizeVLineDrawing(d: ChartVLineDrawing): ChartVLineDrawing {
  const top = Math.max(0, Math.min(1, Number(d.yTopRatio)));
  const bottom = Math.max(0, Math.min(1, Number(d.yBottomRatio)));
  return {
    ...d,
    yTopRatio: Math.min(top, bottom),
    yBottomRatio: Math.max(top, bottom),
  };
}

export function normalizeHLineDrawing(d: ChartHLineDrawing): ChartHLineDrawing {
  const leftRaw = d.xLeftRatio;
  const rightRaw = d.xRightRatio;
  const hasRatios = Number.isFinite(Number(leftRaw)) && Number.isFinite(Number(rightRaw));
  const left = hasRatios ? Math.max(0, Math.min(1, Number(leftRaw))) : 0;
  const right = hasRatios ? Math.max(0, Math.min(1, Number(rightRaw))) : 1;
  return {
    ...d,
    xLeftRatio: Math.min(left, right),
    xRightRatio: Math.max(left, right),
  };
}
