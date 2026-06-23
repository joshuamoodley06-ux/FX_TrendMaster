/** Temporary candle load tracing — request/response pairs for TF switch debugging. */

export type CandleLoadDebugRequest = {
  id: number;
  source: string;
  tf: string;
  symbol?: string;
  caseId?: string;
  layer?: string;
  sourceTf?: string;
  chartTf?: string;
  window?: string;
  activeRangeId?: string;
};

export type CandleLoadDebugResponse = {
  id: number;
  tf: string;
  count: number;
  first?: string;
  last?: string;
  applied: boolean;
  reason?: string;
  loadedContext?: string;
};

function fmtWindow(start?: string, end?: string): string {
  if (!start && !end) return 'full';
  return `${start || '?'}→${end || '?'}`;
}

export function logCandleLoadRequest(args: CandleLoadDebugRequest): void {
  const parts = [
    `candle load request id=${args.id}`,
    `source=${args.source}`,
    `tf=${args.tf}`,
  ];
  if (args.symbol) parts.push(`symbol=${args.symbol}`);
  if (args.caseId) parts.push(`case=${args.caseId}`);
  if (args.layer) parts.push(`layer=${args.layer}`);
  if (args.sourceTf) parts.push(`source_tf=${args.sourceTf}`);
  if (args.chartTf) parts.push(`chart_tf=${args.chartTf}`);
  if (args.window) parts.push(`window=${args.window}`);
  if (args.activeRangeId) parts.push(`range=${args.activeRangeId}`);
  console.info(`[candle-load] ${parts.join(' ')}`);
}

export function logCandleLoadResponse(args: CandleLoadDebugResponse): void {
  const parts = [
    `candle load response id=${args.id}`,
    `tf=${args.tf}`,
    `count=${args.count}`,
  ];
  if (args.first) parts.push(`first=${args.first}`);
  if (args.last) parts.push(`last=${args.last}`);
  parts.push(`applied=${args.applied ? 'true' : 'false'}`);
  if (args.reason) parts.push(`reason=${args.reason}`);
  if (args.loadedContext) parts.push(`loadedContext=${args.loadedContext}`);
  console.info(`[candle-load] ${parts.join(' ')}`);
}

export function formatCandleLoadWindowLabel(start?: string, end?: string): string {
  return fmtWindow(start, end);
}

export function formatLoadedCandleContextSummary(args: {
  chartTimeframe?: string;
  sourceTimeframe?: string;
  structureLayer?: string;
  candleCount?: number;
}): string {
  return [
    args.chartTimeframe || '?',
    args.sourceTimeframe ? `src=${args.sourceTimeframe}` : '',
    args.structureLayer ? `layer=${args.structureLayer}` : '',
    Number.isFinite(args.candleCount) ? `${args.candleCount}bars` : '',
  ].filter(Boolean).join('/');
}
