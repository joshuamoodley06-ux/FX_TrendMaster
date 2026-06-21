export function parseHistoricalScanOutput(stdout: string): Record<string, string | number | null> {
  const out: Record<string, string | number | null> = {};
  const patterns: Array<[string, RegExp]> = [
    ['candles_scanned', /candles_scanned:\s+(\d+)/],
    ['suggestions_created', /suggestions_created:\s+(\d+)/],
    ['range_candidate_count', /RANGE_CANDIDATE:\s+(\d+)/],
    ['chain_candidates', /chain_candidates:\s+(\d+)/],
    ['no_valid_range_count', /NO_VALID_RANGE:\s+(\d+)/],
    ['no_minor_structure_count', /NO_MINOR_STRUCTURE:\s+(\d+)/],
    ['first_suggestion', /first_suggestion:\s+(.+)/],
    ['last_suggestion', /last_suggestion:\s+(.+)/],
    ['detection_run_id', /detection_run_id:\s+(\S+)/],
  ];
  for (const [key, re] of patterns) {
    const match = stdout.match(re);
    if (!match) continue;
    const raw = match[1].trim();
    out[key] = /^\d+$/.test(raw) ? Number(raw) : raw === '—' ? null : raw;
  }
  return out;
}

export function parseJsonOutput(stdout: string): unknown {
  const trimmed = stdout.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    const jsonStart = trimmed.indexOf('{');
    if (jsonStart >= 0) {
      try {
        return JSON.parse(trimmed.slice(jsonStart));
      } catch {
        return { raw: trimmed };
      }
    }
    return { raw: trimmed };
  }
}

export function parseBatchPromoteOutput(stdout: string): unknown {
  return parseJsonOutput(stdout);
}

export function parseDetectorPerformanceOutput(stdout: string): unknown {
  return parseJsonOutput(stdout);
}

export function parseRandomAuditOutput(stdout: string): {
  ok?: boolean;
  count?: number;
  pool_size?: number;
  samples?: unknown[];
} | null {
  const parsed = parseJsonOutput(stdout);
  if (!parsed || typeof parsed !== 'object') return null;
  return parsed as {
    ok?: boolean;
    count?: number;
    pool_size?: number;
    samples?: unknown[];
  };
}
