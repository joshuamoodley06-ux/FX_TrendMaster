import { DEFAULT_VPS_BASE_URL } from './vpsConfig';

export type CockpitSyncSnapshot = {
  state: any;
  activeTrade: any;
  journal: any[];
  status: any;
  brain: any;
  journalSummary: any;
  structuredJournal: any;
  detailedJournal: any;
  ohlcStatus: any;
  apiOnline: boolean | null;
  error: string;
};

/** Kill-switch: background polling off until render loop is resolved. Use refresh() manually. */
export const COCKPIT_SYNC_AUTO_POLL_ENABLED = false;

export const COCKPIT_SYNC_INTERVAL_MS = 7000;

async function fetchJson(url: string): Promise<any> {
  const res = await fetch(url);
  return res.json();
}

export async function fetchCockpitSnapshot(
  symbol: string,
  baseUrl = DEFAULT_VPS_BASE_URL,
): Promise<CockpitSyncSnapshot> {
  try {
    const [
      state,
      activeTrade,
      journal,
      status,
      brain,
      journalSummary,
      structuredJournal,
      detailedJournal,
      candleStatus,
    ] = await Promise.all([
      fetchJson(`${baseUrl}/state?symbol=${encodeURIComponent(symbol)}`),
      fetchJson(`${baseUrl}/trade/active?symbol=${encodeURIComponent(symbol)}&account=challenge`).catch(() => null),
      fetchJson(`${baseUrl}/sql/trades/recent?limit=12`).catch(() => ({ trades: [] })),
      fetchJson(`${baseUrl}/sql/status`).catch(() => null),
      fetchJson(`${baseUrl}/api/v1/lifecycle/brain?symbol=${encodeURIComponent(symbol)}`).catch(() => null),
      fetchJson(`${baseUrl}/api/v1/journal/report/summary?symbol=${encodeURIComponent(symbol)}`).catch(() => null),
      fetchJson(`${baseUrl}/api/v1/journal/report/recent?symbol=${encodeURIComponent(symbol)}&limit=50`).catch(() => null),
      fetchJson(`${baseUrl}/api/v1/journal/trades/detailed?symbol=${encodeURIComponent(symbol)}&limit=50`).catch(() => null),
      fetchJson(`${baseUrl}/api/v1/candles/status`).catch(() => null),
    ]);

    const apiOnline = !!(candleStatus?.ok || state?.symbol);
    return {
      state,
      activeTrade,
      journal: journal?.trades || journal?.rows || [],
      status,
      brain,
      journalSummary,
      structuredJournal,
      detailedJournal,
      ohlcStatus: candleStatus?.ok ? candleStatus : null,
      apiOnline,
      error: '',
    };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Could not reach backend';
    return {
      state: null,
      activeTrade: null,
      journal: [],
      status: null,
      brain: null,
      journalSummary: null,
      structuredJournal: null,
      detailedJournal: null,
      ohlcStatus: null,
      apiOnline: false,
      error: message,
    };
  }
}
