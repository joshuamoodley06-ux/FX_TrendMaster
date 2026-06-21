import type { RangeAuditSample } from './reviewCandidateClient';
import type { WeeklyScanSummary } from './localResearchWorkflow';

export type WeeklyResearchSession = {
  label: string;
  symbol: string;
  year: string;
  sourceTimeframe: string;
  structureLayer: string;
  detectionRunId: string;
  summary: WeeklyScanSummary;
  samples: RangeAuditSample[];
  /** Current review cursor — survives panel close/reopen */
  reviewIndex?: number;
};

export function buildWeeklyResearchSession(args: {
  symbol: string;
  year?: string;
  sourceTimeframe?: string;
  structureLayer?: string;
  summary: WeeklyScanSummary;
  samples: RangeAuditSample[];
}): WeeklyResearchSession | null {
  const runId = args.summary.detectionRunId;
  if (!runId) return null;
  const year = args.year || '2025';
  const tf = args.sourceTimeframe || 'W1';
  const layer = args.structureLayer || 'WEEKLY';
  return {
    label: `${args.symbol} · ${year} · ${tf}`,
    symbol: args.symbol,
    year,
    sourceTimeframe: tf,
    structureLayer: layer,
    detectionRunId: runId,
    summary: args.summary,
    samples: args.samples,
  };
}
