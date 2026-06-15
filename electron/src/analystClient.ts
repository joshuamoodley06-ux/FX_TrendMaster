// Analyst data client: read-only VPS fetchers + analyst_input_v1 package builder.
//
// Electron stays brainless here. This module only:
// - lists saved cases,
// - fetches ranges/events/candles/raw ledgers verbatim for selected case_refs,
// - derives the mechanical fetch plan (which timeframes, which time window),
// - assembles the package JSON the Python analyst consumes offline.
// No interpretation, no writes to the VPS.

import { exportRawCaseEvents, listRawCases } from './rawMapping';

export const VPS_BASE_URL = 'https://api01.apexcoastalrentals.co.za';

const RANGE_FETCH_LIMIT = 2000;
const EVENT_FETCH_LIMIT = 5000;
const CANDLE_FETCH_LIMIT = 20000;
const DAY_MS = 86_400_000;

export type CaseListItem = {
  case_ref: string;
  kind: 'raw' | 'legacy';
  symbol: string;
  name: string;
  timeframe: string;
  updated: string;
};

export type PackageBuildResult = {
  label: string;
  fileName: string;
  json: string;
  counts: {
    cases: number;
    ranges: number;
    events: number;
    ledgers: number;
    candles: Record<string, number>;
  };
  warnings: string[];
};

type ProgressFn = (line: string) => void;

/** Folder-safe batch label (spaces -> underscores). Matches main.cjs sanitizer. */
export function sanitizeAnalystLabel(raw: string): string {
  const text = String(raw || '').trim();
  const sanitized = text
    .replace(/\s+/g, '_')
    .replace(/[^a-zA-Z0-9._-]/g, '')
    .replace(/_+/g, '_')
    .replace(/^\.+/, '')
    .slice(0, 48);
  return sanitized || 'batch';
}

/** First 4-digit calendar year in a label, for analyst_input_v1 year field. */
export function parsePackageYear(label: string): number | null {
  const match = label.match(/\b(19|20)\d{2}\b/);
  if (!match) return null;
  const year = Number(match[0]);
  return year >= 1970 && year <= 2200 ? year : null;
}

async function fetchJson(url: string): Promise<any> {
  const response = await fetch(url);
  const body = await response.json().catch(() => null);
  if (!response.ok || !body || body.ok === false) {
    const detail = body?.error || body?.detail || `HTTP ${response.status}`;
    throw new Error(`${detail} (${url.split('?')[0]})`);
  }
  return body;
}

export async function listAnalystCases(
  symbol: string
): Promise<{ cases: CaseListItem[]; errors: string[] }> {
  const errors: string[] = [];
  const cases: CaseListItem[] = [];

  const [rawResult, legacyResult] = await Promise.allSettled([
    listRawCases(VPS_BASE_URL, symbol, 200),
    fetchJson(`${VPS_BASE_URL}/api/v1/mos/seed-ideas?symbol=${encodeURIComponent(symbol)}&limit=100`),
  ]);

  if (rawResult.status === 'fulfilled' && rawResult.value.ok) {
    for (const row of rawResult.value.cases || []) {
      cases.push({
        case_ref: `raw:${row.case_id}`,
        kind: 'raw',
        symbol: row.symbol,
        name: row.case_name || `Raw ${String(row.case_id).slice(0, 8)}`,
        timeframe: row.base_timeframe || '-',
        updated: msToDateText(row.updated_at_utc_ms ?? row.created_at_utc_ms),
      });
    }
  } else {
    errors.push(
      `raw cases: ${rawResult.status === 'rejected' ? String(rawResult.reason) : 'list failed'}`
    );
  }

  if (legacyResult.status === 'fulfilled') {
    const ideas = legacyResult.value.ideas || legacyResult.value.cases || [];
    for (const row of ideas) {
      if (row?.id === null || row?.id === undefined) continue;
      cases.push({
        case_ref: `case:${row.id}`,
        kind: 'legacy',
        symbol: row.symbol || symbol,
        name: row.seed_name || row.name || `Case ${row.id}`,
        timeframe: row.case_timeframe || row.timeframe || '-',
        updated: String(row.updated_at || row.created_at || '-'),
      });
    }
  } else {
    errors.push(`legacy cases: ${String(legacyResult.reason)}`);
  }

  return { cases, errors };
}

export async function buildAnalystPackage(options: {
  symbol: string;
  year: string;
  caseRefs: string[];
  paddingDays: number;
  extraTimeframes?: string[];
  onProgress?: ProgressFn;
}): Promise<PackageBuildResult> {
  const { symbol, year, caseRefs, paddingDays } = options;
  const progress: ProgressFn = options.onProgress || (() => undefined);
  const warnings: string[] = [];

  const allRanges: any[] = [];
  const allEvents: any[] = [];
  const rawLedgers: Record<string, any> = {};

  for (const caseRef of caseRefs) {
    progress(`fetching ${caseRef} ...`);
    try {
      const rangesRes = await fetchJson(
        `${VPS_BASE_URL}/api/v1/map/ranges?symbol=${encodeURIComponent(symbol)}&case_ref=${encodeURIComponent(caseRef)}&limit=${RANGE_FETCH_LIMIT}`
      );
      const ranges = rangesRes.ranges || [];
      allRanges.push(...ranges);

      const eventsRes = await fetchJson(
        `${VPS_BASE_URL}/api/v1/map/events?symbol=${encodeURIComponent(symbol)}&case_ref=${encodeURIComponent(caseRef)}&limit=${EVENT_FETCH_LIMIT}`
      );
      const events = eventsRes.events || [];
      allEvents.push(...events);

      progress(`  ${caseRef}: ${ranges.length} ranges, ${events.length} events`);
      if (ranges.length === 0) warnings.push(`${caseRef}: no ranges on VPS`);
    } catch (err) {
      warnings.push(`${caseRef}: fetch failed - ${String((err as Error).message || err)}`);
      progress(`  ${caseRef}: FAILED (${String((err as Error).message || err)})`);
      continue;
    }

    if (caseRef.startsWith('raw:')) {
      try {
        const ledger = await exportRawCaseEvents(VPS_BASE_URL, caseRef.slice(4));
        rawLedgers[caseRef] = ledger;
        progress(`  ${caseRef}: raw ledger ${ledger?.meta?.total_records ?? '?'} records (hash ${String(ledger?.meta?.ledger_hash || '').slice(0, 12)}...)`);
      } catch (err) {
        warnings.push(`${caseRef}: raw ledger export failed - ${String((err as Error).message || err)}`);
      }
    }
  }

  // Mechanical fetch plan: timeframes actually referenced + padded time window.
  const timeframes = new Set<string>(options.extraTimeframes || []);
  for (const row of allRanges) {
    for (const key of ['source_timeframe', 'chart_timeframe', 'timeframe']) {
      if (row?.[key]) timeframes.add(String(row[key]));
    }
  }
  for (const row of allEvents) {
    for (const key of ['timeframe', 'source_timeframe']) {
      if (row?.[key]) timeframes.add(String(row[key]));
    }
  }

  const times: number[] = [];
  for (const row of allRanges) {
    for (const key of [
      'range_high_time', 'range_low_time', 'range_start_time', 'range_end_time',
      'active_from_time', 'inactive_from_time',
    ]) {
      const ms = toMs(row?.[key]);
      if (ms !== null) times.push(ms);
    }
  }
  for (const row of allEvents) {
    const ms = toMs(row?.event_time ?? row?.time ?? row?.candle_time);
    if (ms !== null) times.push(ms);
  }

  const candles: Record<string, any[]> = {};
  if (times.length === 0) {
    warnings.push('no usable times found in ranges/events; skipping candle fetch');
  } else {
    const start = fmtUtc(Math.min(...times) - paddingDays * DAY_MS);
    const end = fmtUtc(Math.max(...times) + paddingDays * DAY_MS);
    progress(`candle window ${start} .. ${end} (padding ${paddingDays}d)`);
    for (const timeframe of Array.from(timeframes).sort()) {
      try {
        const url =
          `${VPS_BASE_URL}/api/v1/candles?symbol=${encodeURIComponent(symbol)}` +
          `&timeframe=${encodeURIComponent(timeframe)}&limit=${CANDLE_FETCH_LIMIT}` +
          `&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
        const res = await fetchJson(url);
        const rows = res.candles || [];
        candles[timeframe] = rows;
        progress(`  candles ${timeframe}: ${rows.length}`);
        if (rows.length === 0) warnings.push(`candles ${timeframe}: none in window`);
        if (rows.length >= CANDLE_FETCH_LIMIT) warnings.push(`candles ${timeframe}: hit fetch limit ${CANDLE_FETCH_LIMIT}, window may be truncated`);
      } catch (err) {
        warnings.push(`candles ${timeframe}: fetch failed - ${String((err as Error).message || err)}`);
        progress(`  candles ${timeframe}: FAILED`);
      }
    }
  }

  const batchLabel = sanitizeAnalystLabel(year);
  const label = `${symbol.toUpperCase()}_${batchLabel}`;
  const pkg = {
    schema_version: 'analyst_input_v1',
    symbol: symbol.toUpperCase(),
    year: parsePackageYear(year),
    label,
    case_refs: caseRefs,
    generated_at_utc_ms: Date.now(),
    source: { base_url: VPS_BASE_URL, fetched_at: new Date().toISOString() },
    data: {
      ranges: allRanges,
      events: allEvents,
      candles,
      raw_ledgers: rawLedgers,
    },
  };

  return {
    label,
    fileName: `${label}.json`,
    json: JSON.stringify(pkg, null, 2),
    counts: {
      cases: caseRefs.length,
      ranges: allRanges.length,
      events: allEvents.length,
      ledgers: Object.keys(rawLedgers).length,
      candles: Object.fromEntries(Object.entries(candles).map(([tf, rows]) => [tf, rows.length])),
    },
    warnings,
  };
}

function toMs(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1e11 ? value : value * 1000;
  }
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text) return null;
  const num = Number(text);
  if (Number.isFinite(num)) return num > 1e11 ? num : num * 1000;
  const iso = text.includes('T') ? text : text.replace(' ', 'T');
  const withZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const parsed = new Date(withZone);
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
}

function fmtUtc(ms: number): string {
  return new Date(ms).toISOString().slice(0, 19).replace('T', ' ');
}

function msToDateText(ms: number | null | undefined): string {
  if (!ms || !Number.isFinite(ms)) return '-';
  return new Date(ms).toISOString().slice(0, 10);
}
