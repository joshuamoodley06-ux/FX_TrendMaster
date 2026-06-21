/** Continue Mapping campaign — delegates to campaign manager. */

import { getNextMappingTask, type MappingTaskType } from './mappingCampaignManager';
import type { MappingGap } from './mappingWorkflow';

export function isChildMappingGap(gap: MappingGap): boolean {
  return (
    (gap.parentLayer === 'WEEKLY' && gap.expectedChildLayer === 'DAILY')
    || (gap.parentLayer === 'DAILY' && gap.expectedChildLayer === 'INTRADAY')
    || (gap.parentLayer === 'INTRADAY' && gap.expectedChildLayer === 'MICRO')
  );
}

/** @deprecated Use getNextMappingTask() — kept for existing imports. */
export function nextMappingCampaignGap(ranges: Record<string, unknown>[]): MappingGap | null {
  return getNextMappingTask(ranges).gap;
}

export function campaignGapSummary(gap: MappingGap | null): string {
  if (!gap) return 'Campaign complete — no Weekly→Daily, Daily→Intraday, or Intraday→Micro gaps.';
  return gap.label;
}

export type { MappingTaskType };
