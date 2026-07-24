// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  StatisticsReportPanel,
  statisticsReportMetadataFromMasterMap,
} from './statisticsReportPanel';

const CASE = 'case:stats';

function report() {
  return {
    schema_version: 'weekly_daily_statistics_v1',
    report_id: 'report-1',
    generated_at: '2026-07-24T13:00:00Z',
    structural_content_hash: 'hash-1',
    dataset: {
      weekly_start: '2023-01-29',
      daily_enabled_start: '2024-10-27',
      parent_join_rule: 'EXACT_MASTER_MAP_HIERARCHY',
    },
    overview: {
      weekly: {
        range_count: 84,
        processing_status_counts: { COMPLETE: 80, PENDING: 4 },
        bos_direction_counts: { BOS_UP: 44, BOS_DOWN: 40 },
        profile_counts: { 'S&R': 48, 'S&D': 36 },
        extreme_destination_counts: { FAIR_PRICE: 32 },
      },
      daily: {
        range_count: 271,
        processing_status_counts: { COMPLETE: 250, NEEDS_REVIEW: 21 },
        bos_direction_counts: { BOS_UP: 150, BOS_DOWN: 121 },
        profile_counts: { 'S&R': 161, 'S&D': 110 },
      },
      parent_child: {
        weekly_parent_count: 46,
        daily_child_count: 271,
        average_daily_children_per_parent: 5.89,
        unlinked_daily_count: 0,
        bos_alignment_counts: {
          BOS_ALIGNED: 170,
          BOS_COUNTER: 80,
          UNRESOLVED: 21,
        },
      },
    },
    weekly_rows: [{
      canonical_range_id: 'weekly-1',
      start_date: '2023-01-29',
      bos_direction: 'BOS_UP',
      reclaim_status: 'RECLAIMED',
      profile: 'S&R',
      extreme_destination: 'FAIR_PRICE',
      processing_status: 'COMPLETE',
    }],
    daily_rows: [{
      canonical_range_id: 'daily-1',
      weekly_parent_id: 'weekly-1',
      start_date: '2024-10-27',
      bos_direction: 'BOS_UP',
      reclaim_status: 'RECLAIMED',
      profile: 'S&R',
      extreme_destination: 'OPPOSITE_EXTREME',
      processing_status: 'COMPLETE',
    }],
    parent_rows: [{
      weekly_parent_id: 'weekly-1',
      weekly_start_date: '2023-01-29',
      weekly_bos_direction: 'BOS_UP',
      weekly_profile: 'S&R',
      weekly_processing_status: 'COMPLETE',
      daily_child_count: 1,
      daily_complete_count: 1,
      daily_pending_count: 0,
      daily_needs_review_count: 0,
    }],
    exports: {
      folder: 'C:/FXTM Research/statistics-reports/report-1',
    },
  };
}

function masterMapWithReport() {
  const value = report();
  return {
    analysis: {
      weekly_daily_statistics_reports: {
        by_case: {
          [CASE]: {
            latest_report: value,
            snapshots: [{
              report_id: 'report-1',
              generated_at: value.generated_at,
              structural_content_hash: 'hash-1',
              stale: false,
            }],
          },
        },
      },
    },
  };
}

describe('StatisticsReportPanel', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
  });

  it('restores a snapshot and runs the approved pipeline to refresh the report', async () => {
    const bridge = {
      getPaths: vi.fn().mockResolvedValue({
        ok: true,
        databasePath: 'C:/live.sqlite3',
      }),
      getWeeklyScript1State: vi.fn().mockResolvedValue({
        ok: true,
        analysisDatabasePath: 'C:/analysis.sqlite3',
        masterMap: masterMapWithReport(),
      }),
      runDoctrinePipeline: vi.fn().mockResolvedValue({
        ok: true,
        result: { statistics_report: report() },
        masterMap: masterMapWithReport(),
      }),
      openResearchFolder: vi.fn().mockResolvedValue({
        ok: true,
        folder: 'C:/FXTM Research',
      }),
    };
    const onReportRun = vi.fn();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => root!.render(createElement(StatisticsReportPanel, {
      caseRef: CASE,
      symbol: 'XAUUSD',
      bridge,
      onReportRun,
    })));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain('Weekly ranges');
    expect(container.textContent).toContain('84');
    expect(container.textContent).toContain('Daily ranges');
    expect(container.textContent).toContain('271');
    expect(container.textContent).toContain('29 Jan 2023 onward');
    expect(container.textContent).toContain('27 Oct 2024 onward');

    const run = Array.from(container.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent === 'Run Latest Report')!;
    await act(async () => {
      run.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(bridge.runDoctrinePipeline).toHaveBeenCalledWith({
      analysisDatabasePath: 'C:/analysis.sqlite3',
      caseRef: CASE,
      symbol: 'XAUUSD',
    });
    expect(onReportRun).toHaveBeenCalledTimes(1);

    const combined = Array.from(
      container.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    ).find((button) => button.textContent === 'Weekly + Daily')!;
    await act(async () => combined.click());
    expect(container.textContent).toContain('weekly-1');
    expect(container.textContent).toContain('5.89');
  });

  it('extracts report history by normalized case reference', () => {
    const metadata = statisticsReportMetadataFromMasterMap(
      masterMapWithReport(),
      'raw:case:stats',
    );
    expect(metadata.latestReport?.report_id).toBe('report-1');
    expect(metadata.snapshots).toHaveLength(1);
  });
});
