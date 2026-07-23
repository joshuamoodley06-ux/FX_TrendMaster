export type DailyHierarchyAuditLayer = 'MACRO' | 'WEEKLY' | 'DAILY' | 'INTRADAY' | 'MICRO' | string;

export type DailyHierarchyAuditRowInput = {
  rangeId: string;
  layer: DailyHierarchyAuditLayer;
  depth: number;
  orphan?: boolean;
};

export type DailyHierarchyLinkStatus = 'VALID' | 'INVALID';

export type DailyHierarchyAuditDecoration = {
  rangeId: string;
  layer: string;
  parentWeeklyRangeId: string | null;
  dailySequenceNumber: number | null;
  linkStatus: DailyHierarchyLinkStatus | null;
  linkReason: string | null;
};

export type DailyHierarchyWeeklySummary = {
  weeklyRangeId: string;
  dailyCount: number;
  invalidCount: number;
};

export type DailyHierarchyAuditLayout = {
  rows: DailyHierarchyAuditDecoration[];
  weeklySummaries: DailyHierarchyWeeklySummary[];
};

function normalizedLayer(value: unknown): string {
  return String(value || '').trim().toUpperCase();
}

function safeDepth(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
}

/**
 * Decorate the already-rendered hierarchy without rebuilding or re-parenting it.
 *
 * Daily numbering follows the visible saved hierarchy order and resets beneath
 * every Weekly parent. A Daily row is VALID only when it is visibly nested under
 * a Weekly row and is not in the hierarchy orphan group.
 */
export function buildDailyHierarchyAuditLayout(
  sourceRows: DailyHierarchyAuditRowInput[],
): DailyHierarchyAuditLayout {
  const rows: DailyHierarchyAuditDecoration[] = [];
  const weeklySummaries = new Map<string, DailyHierarchyWeeklySummary>();

  let currentWeeklyRangeId: string | null = null;
  let currentWeeklyDepth = -1;
  let dailySequenceNumber = 0;

  const clearWeeklyScope = () => {
    currentWeeklyRangeId = null;
    currentWeeklyDepth = -1;
    dailySequenceNumber = 0;
  };

  for (const source of sourceRows) {
    const rangeId = String(source.rangeId || '').trim();
    const layer = normalizedLayer(source.layer);
    const depth = safeDepth(source.depth);
    const orphan = source.orphan === true;

    if (!rangeId) continue;

    if (layer === 'WEEKLY' && !orphan) {
      currentWeeklyRangeId = rangeId;
      currentWeeklyDepth = depth;
      dailySequenceNumber = 0;
      if (!weeklySummaries.has(rangeId)) {
        weeklySummaries.set(rangeId, {
          weeklyRangeId: rangeId,
          dailyCount: 0,
          invalidCount: 0,
        });
      }
      rows.push({
        rangeId,
        layer,
        parentWeeklyRangeId: null,
        dailySequenceNumber: null,
        linkStatus: null,
        linkReason: null,
      });
      continue;
    }

    if (orphan || (currentWeeklyRangeId && depth <= currentWeeklyDepth)) {
      clearWeeklyScope();
    }

    if (layer !== 'DAILY') {
      rows.push({
        rangeId,
        layer,
        parentWeeklyRangeId: currentWeeklyRangeId,
        dailySequenceNumber: null,
        linkStatus: null,
        linkReason: null,
      });
      continue;
    }

    const nestedUnderWeekly = !!currentWeeklyRangeId && depth > currentWeeklyDepth;
    const valid = nestedUnderWeekly && !orphan;
    const parentWeeklyRangeId = valid ? currentWeeklyRangeId : null;
    const sequence = valid ? ++dailySequenceNumber : null;

    if (parentWeeklyRangeId) {
      const summary = weeklySummaries.get(parentWeeklyRangeId) || {
        weeklyRangeId: parentWeeklyRangeId,
        dailyCount: 0,
        invalidCount: 0,
      };
      summary.dailyCount += 1;
      weeklySummaries.set(parentWeeklyRangeId, summary);
    }

    rows.push({
      rangeId,
      layer,
      parentWeeklyRangeId,
      dailySequenceNumber: sequence,
      linkStatus: valid ? 'VALID' : 'INVALID',
      linkReason: valid
        ? 'Saved Daily child is nested under this Weekly parent.'
        : orphan
          ? 'Daily range is unlinked or orphaned in the saved hierarchy.'
          : 'Daily range is not nested under a Weekly parent in the saved hierarchy.',
    });
  }

  return {
    rows,
    weeklySummaries: Array.from(weeklySummaries.values()),
  };
}
