// Preset mediator queries + natural-language Ask chips (Research View).

export type AskPreset = {
  id: string;
  label: string;
  question: string;
  query: Record<string, unknown>;
};

export function buildRangeListQuery(options: {
  symbol: string;
  yearLabels: string[];
  layer: string;
  rowLimit?: number;
  randomSeed?: number;
  queryId?: string;
}): Record<string, unknown> {
  const layer = options.layer.toUpperCase();
  return {
    schema_version: 'mediator_query_v1',
    query_id: options.queryId || `sampler_${layer.toLowerCase()}_${options.randomSeed ?? Date.now()}`,
    symbol: options.symbol.toUpperCase(),
    year_labels: options.yearLabels,
    structure_layer: layer,
    question_type: 'range_list',
    row_limit: options.rowLimit ?? 1,
    random_sample: true,
    random_seed: options.randomSeed ?? Math.floor(Math.random() * 1_000_000),
    include_source_rows: true,
    metrics: ['sample_size'],
  };
}

export function buildContinuationQuery(options: {
  symbol: string;
  yearLabels: string[];
  childLayer: string;
  retracementClass: string;
  queryId?: string;
}): Record<string, unknown> {
  return {
    schema_version: 'mediator_query_v1',
    query_id: options.queryId || `insight_${options.childLayer}_${options.retracementClass}`,
    symbol: options.symbol.toUpperCase(),
    year_labels: options.yearLabels,
    child_layer: options.childLayer.toUpperCase(),
    retracement_class: options.retracementClass.toUpperCase(),
    question_type: 'continuation_rate',
    include_source_rows: false,
    metrics: [
      'sample_size',
      'continued_count',
      'failed_count',
      'abandoned_count',
      'unresolved_count',
      'continuation_rate',
      'failure_rate',
      'abandon_rate',
      'average_retracement',
      'median_retracement',
    ],
  };
}

export function buildImpulsePairQuery(options: {
  symbol: string;
  yearLabels: string[];
  childLayer?: string;
  rowLimit?: number;
  randomSeed?: number;
}): Record<string, unknown> {
  return {
    schema_version: 'mediator_query_v1',
    query_id: options.queryId || `impulse_up_${options.randomSeed ?? Date.now()}`,
    symbol: options.symbol.toUpperCase(),
    year_labels: options.yearLabels,
    child_layer: (options.childLayer || 'DAILY').toUpperCase(),
    bos_direction: 'UP',
    question_type: 'impulse_pair_audit',
    row_limit: options.rowLimit ?? 2,
    random_sample: true,
    random_seed: options.randomSeed ?? Math.floor(Math.random() * 1_000_000),
    include_source_rows: true,
    metrics: ['sample_size', 'average_retracement', 'median_retracement'],
  };
}

export const ASK_PRESETS: AskPreset[] = [
  {
    id: 'random_weekly',
    label: '5 random Weekly ranges',
    question: 'Show me 5 random Weekly ranges with high and low',
    query: {
      schema_version: 'mediator_query_v1',
      structure_layer: 'WEEKLY',
      question_type: 'range_list',
      row_limit: 5,
      random_sample: true,
      include_source_rows: true,
      metrics: ['sample_size'],
    },
  },
  {
    id: 'deep_daily_continuation',
    label: 'Deep Daily retracements',
    question: 'How often did deep Daily retracements continue?',
    query: {
      schema_version: 'mediator_query_v1',
      child_layer: 'DAILY',
      retracement_class: 'DEEP',
      question_type: 'continuation_rate',
      metrics: [
        'sample_size',
        'continued_count',
        'failed_count',
        'abandoned_count',
        'continuation_rate',
        'failure_rate',
      ],
    },
  },
  {
    id: 'shallow_vs_deep_reclaim',
    label: 'Shallow vs deep reclaim',
    question: 'Compare shallow vs deep reclaim continuation',
    query: {
      schema_version: 'mediator_query_v1',
      child_layer: 'DAILY',
      question_type: 'reclaim_compare',
      group_by: ['reclaim_class'],
      metrics: ['sample_size', 'continuation_rate', 'failure_rate', 'reclaim_rate'],
    },
  },
  {
    id: 'failed_daily_bos',
    label: 'Failed Daily BOS examples',
    question: 'Show failed Daily BOS continuation examples',
    query: {
      schema_version: 'mediator_query_v1',
      child_layer: 'DAILY',
      outcome: 'FAILED',
      question_type: 'continuation_rate',
      row_limit: 10,
      include_source_rows: true,
      metrics: ['sample_size'],
    },
  },
  {
    id: 'bos_up_retrace_bos_up',
    label: 'BOS up → retrace → BOS up',
    question: 'Two examples of BOS up, retrace, then next BOS up with range highs and lows',
    query: {
      schema_version: 'mediator_query_v1',
      child_layer: 'DAILY',
      bos_direction: 'UP',
      question_type: 'impulse_pair_audit',
      row_limit: 2,
      random_sample: true,
      include_source_rows: true,
      metrics: ['sample_size', 'average_retracement', 'median_retracement'],
    },
  },
];

export function hydratePreset(
  preset: AskPreset,
  symbol: string,
  yearLabels: string[],
  randomSeed?: number
): Record<string, unknown> {
  const q: Record<string, unknown> = {
    ...preset.query,
    symbol: symbol.toUpperCase(),
    year_labels: yearLabels,
    query_id: `${preset.id}_${randomSeed ?? Date.now()}`,
  };
  if (q.random_sample && randomSeed !== undefined) {
    q.random_seed = randomSeed;
  }
  return q;
}

/** Apply year/batch follow-ups without AI (e.g. "2019", "2020 only", batch folder name). */
export function applyFollowUpToQuery(
  priorQuery: Record<string, unknown>,
  followUp: string,
  availableYearLabels: string[],
): { query: Record<string, unknown>; note: string } | null {
  const text = followUp.trim();
  if (!text) return null;

  const next: Record<string, unknown> = {
    ...priorQuery,
    query_id: `${String(priorQuery.query_id || 'query')}_f_${Date.now()}`,
  };

  const lower = text.toLowerCase();
  if (/^(all|everything|all batches|reset|clear filter)$/i.test(lower)) {
    next.year_labels = [...availableYearLabels];
    next.years = [];
    return { query: next, note: `All batches (${availableYearLabels.length})` };
  }

  const yearMatches = [...text.matchAll(/\b(19|20)\d{2}\b/g)].map((m) => Number(m[0]));
  if (yearMatches.length > 0) {
    const uniqueYears = [...new Set(yearMatches)];
    next.years = uniqueYears;
    next.year_labels = [];
    return {
      query: next,
      note:
        uniqueYears.length === 1
          ? `Calendar year ${uniqueYears[0]} (matches batches whose yearly_stats year equals ${uniqueYears[0]})`
          : `Calendar years ${uniqueYears.join(', ')}`,
    };
  }

  const batchMatch = availableYearLabels.find(
    (label) => label.toLowerCase() === lower || label.toLowerCase().includes(lower),
  );
  if (batchMatch) {
    next.year_labels = [batchMatch];
    next.years = [];
    return { query: next, note: `Batch folder ${batchMatch}` };
  }

  return null;
}

export function pctText(rate: number | null | undefined, digits = 0): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return '—';
  return `${(rate * 100).toFixed(digits)}%`;
}

export function pctFromRatio(n: number, d: number, digits = 0): string {
  if (!d) return '—';
  return pctText(n / d, digits);
}

export function msToDate(ms: number | null | undefined): string {
  if (!ms || !Number.isFinite(ms)) return '—';
  return new Date(ms).toISOString().slice(0, 10);
}

export function retracementPctDisplay(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}
