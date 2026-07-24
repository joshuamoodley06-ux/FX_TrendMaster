import React, { useEffect, useMemo, useState } from 'react';
import './statisticsReportPanel.css';

export const WEEKLY_REPORT_START = '2023-01-29';
export const DAILY_REPORT_START = '2024-10-27';

type ReportSnapshot = {
  report_id: string;
  generated_at: string;
  structural_content_hash: string;
  stale?: boolean;
  exports?: Record<string, string>;
};

type StatisticsReport = {
  schema_version?: string;
  report_id?: string;
  generated_at?: string;
  structural_content_hash?: string;
  stale?: boolean;
  dataset?: Record<string, any>;
  doctrine_versions?: Record<string, any>[];
  overview?: {
    weekly?: Record<string, any>;
    daily?: Record<string, any>;
    parent_child?: Record<string, any>;
  };
  weekly_rows?: Record<string, any>[];
  daily_rows?: Record<string, any>[];
  parent_rows?: Record<string, any>[];
  exports?: Record<string, string>;
  status?: string;
  error?: string;
};

type ReportMetadata = {
  latestReport: StatisticsReport | null;
  snapshots: ReportSnapshot[];
};

type StatisticsBridge = {
  getPaths: () => Promise<{
    ok: boolean;
    databasePath?: string;
    error?: string;
  }>;
  getWeeklyScript1State: (args: {
    databasePath: string;
    caseRef: string;
    symbol: string;
  }) => Promise<{
    ok: boolean;
    analysisDatabasePath?: string;
    masterMap?: unknown;
    error?: string;
  }>;
  runDoctrinePipeline: (args: {
    analysisDatabasePath: string;
    caseRef: string;
    symbol: string;
  }) => Promise<{
    ok: boolean;
    result?: Record<string, any>;
    masterMap?: unknown;
    error?: string;
  }>;
  openResearchFolder?: () => Promise<{
    ok: boolean;
    folder?: string;
    error?: string;
  }>;
};

export type StatisticsReportPanelProps = {
  caseRef: string;
  symbol: string;
  bridge?: StatisticsBridge | null;
  onReportRun?: () => void;
  onClose?: () => void;
};

type ReportView = 'overview' | 'weekly' | 'combined' | 'parent';

function normalizeCaseRef(value: unknown): string {
  return String(value || '').trim().replace(/^raw:/i, '');
}

export function statisticsReportMetadataFromMasterMap(
  masterMap: unknown,
  caseRef: string,
): ReportMetadata {
  if (!masterMap || typeof masterMap !== 'object') {
    return { latestReport: null, snapshots: [] };
  }
  const analysis = (masterMap as any).analysis;
  const reports = analysis?.weekly_daily_statistics_reports;
  const byCase = reports?.by_case;
  if (!byCase || typeof byCase !== 'object') {
    return { latestReport: null, snapshots: [] };
  }
  const expected = normalizeCaseRef(caseRef);
  const entry = Object.entries(byCase)
    .find(([key]) => normalizeCaseRef(key) === expected)?.[1] as any;
  if (!entry || typeof entry !== 'object') {
    return { latestReport: null, snapshots: [] };
  }
  return {
    latestReport: entry.latest_report && typeof entry.latest_report === 'object'
      ? entry.latest_report as StatisticsReport
      : null,
    snapshots: Array.isArray(entry.snapshots)
      ? entry.snapshots as ReportSnapshot[]
      : [],
  };
}

function defaultBridge(): StatisticsBridge | null {
  const globals = globalThis as typeof globalThis & {
    localResearch?: Partial<StatisticsBridge>;
  };
  const source = globals.localResearch;
  if (
    !source?.getPaths
    || !source.getWeeklyScript1State
    || !source.runDoctrinePipeline
  ) {
    return null;
  }
  return source as StatisticsBridge;
}

function value(raw: unknown, fallback = '—'): string {
  if (raw === null || raw === undefined || raw === '') return fallback;
  if (typeof raw === 'number') {
    return Number.isInteger(raw) ? String(raw) : raw.toFixed(2);
  }
  return String(raw).replaceAll('_', ' ');
}

function compactDate(raw: unknown): string {
  const text = String(raw || '').trim();
  return text ? text.slice(0, 10) : '—';
}

function CountBreakdown({ title, counts }: {
  title: string;
  counts: unknown;
}) {
  const rows = counts && typeof counts === 'object'
    ? Object.entries(counts as Record<string, unknown>)
    : [];
  return <div className="statisticsBreakdown">
    <b>{title}</b>
    {!rows.length && <span>None</span>}
    {rows.map(([key, count]) => <span key={key}>
      <em>{value(key)}</em>
      <strong>{value(count, '0')}</strong>
    </span>)}
  </div>;
}

function MetricCard({ label, metric, detail }: {
  label: string;
  metric: unknown;
  detail?: string;
}) {
  return <div className="statisticsMetricCard">
    <span>{label}</span>
    <strong>{value(metric, '0')}</strong>
    {detail && <small>{detail}</small>}
  </div>;
}

function WeeklyTable({ rows }: { rows: Record<string, any>[] }) {
  return <div className="statisticsTableScroll">
    <table className="statisticsTable">
      <thead><tr>
        <th>Weekly range</th>
        <th>Start</th>
        <th>BOS</th>
        <th>Reclaim</th>
        <th>Profile</th>
        <th>Destination</th>
        <th>Processing</th>
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={row.canonical_range_id}>
        <td>{row.canonical_range_id}</td>
        <td>{compactDate(row.start_date)}</td>
        <td>{value(row.bos_direction)}</td>
        <td>{value(row.reclaim_status)}</td>
        <td>{value(row.profile)}</td>
        <td>{value(row.extreme_destination)}</td>
        <td>{value(row.processing_status)}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function ParentTable({ rows, onSelect }: {
  rows: Record<string, any>[];
  onSelect: (identity: string) => void;
}) {
  return <div className="statisticsTableScroll">
    <table className="statisticsTable">
      <thead><tr>
        <th>Weekly parent</th>
        <th>Start</th>
        <th>Weekly BOS</th>
        <th>Profile</th>
        <th>Daily</th>
        <th>Complete</th>
        <th>Pending</th>
        <th>Review</th>
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={row.weekly_parent_id}>
        <td><button
          type="button"
          className="statisticsTableLink"
          onClick={() => onSelect(String(row.weekly_parent_id))}
        >{row.weekly_parent_id}</button></td>
        <td>{compactDate(row.weekly_start_date)}</td>
        <td>{value(row.weekly_bos_direction)}</td>
        <td>{value(row.weekly_profile)}</td>
        <td>{value(row.daily_child_count, '0')}</td>
        <td>{value(row.daily_complete_count, '0')}</td>
        <td>{value(row.daily_pending_count, '0')}</td>
        <td>{value(row.daily_needs_review_count, '0')}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function DailyTable({ rows }: { rows: Record<string, any>[] }) {
  return <div className="statisticsTableScroll">
    <table className="statisticsTable">
      <thead><tr>
        <th>Daily range</th>
        <th>Start</th>
        <th>BOS</th>
        <th>Reclaim</th>
        <th>Profile</th>
        <th>Destination</th>
        <th>Processing</th>
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={row.canonical_range_id}>
        <td>{row.canonical_range_id}</td>
        <td>{compactDate(row.start_date)}</td>
        <td>{value(row.bos_direction)}</td>
        <td>{value(row.reclaim_status)}</td>
        <td>{value(row.profile)}</td>
        <td>{value(row.extreme_destination)}</td>
        <td>{value(row.processing_status)}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}

export function StatisticsReportPanel({
  caseRef,
  symbol,
  bridge: explicitBridge,
  onReportRun,
  onClose,
}: StatisticsReportPanelProps) {
  const bridge = useMemo(
    () => explicitBridge === undefined ? defaultBridge() : explicitBridge,
    [explicitBridge],
  );
  const [analysisDatabasePath, setAnalysisDatabasePath] = useState('');
  const [report, setReport] = useState<StatisticsReport | null>(null);
  const [snapshots, setSnapshots] = useState<ReportSnapshot[]>([]);
  const [view, setView] = useState<ReportView>('overview');
  const [selectedParentId, setSelectedParentId] = useState('');
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState('');
  const [folderMessage, setFolderMessage] = useState('');

  const applyMasterMap = (masterMap: unknown) => {
    const metadata = statisticsReportMetadataFromMasterMap(masterMap, caseRef);
    if (metadata.latestReport) setReport(metadata.latestReport);
    setSnapshots(metadata.snapshots);
  };

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      setRestoring(true);
      setError('');
      try {
        if (!bridge) {
          throw new Error('Statistics bridge is unavailable outside Electron.');
        }
        if (!caseRef) {
          throw new Error('Select a case before opening reports.');
        }
        const paths = await bridge.getPaths();
        const databasePath = String(paths.databasePath || '').trim();
        if (!paths.ok || !databasePath) {
          throw new Error(
            paths.error || 'Range Library path is unavailable.',
          );
        }
        const state = await bridge.getWeeklyScript1State({
          databasePath,
          caseRef,
          symbol,
        });
        if (!state.ok || !state.analysisDatabasePath) {
          throw new Error(
            'The Python analysis workspace has not been created yet.',
          );
        }
        if (cancelled) return;
        setAnalysisDatabasePath(state.analysisDatabasePath);
        applyMasterMap(state.masterMap);
      } catch (restoreError) {
        if (!cancelled) {
          setError(
            restoreError instanceof Error
              ? restoreError.message
              : String(restoreError),
          );
        }
      } finally {
        if (!cancelled) setRestoring(false);
      }
    };
    void restore();
    return () => { cancelled = true; };
  }, [bridge, caseRef, symbol]);

  useEffect(() => {
    const parents = report?.parent_rows || [];
    if (!parents.length) {
      setSelectedParentId('');
      return;
    }
    if (
      !parents.some(
        (row) => String(row.weekly_parent_id) === selectedParentId,
      )
    ) {
      setSelectedParentId(String(parents[0].weekly_parent_id));
    }
  }, [report, selectedParentId]);

  const runLatestReport = async () => {
    if (!bridge || !analysisDatabasePath) return;
    setBusy(true);
    setError('');
    try {
      const result = await bridge.runDoctrinePipeline({
        analysisDatabasePath,
        caseRef,
        symbol,
      });
      if (!result.ok) {
        throw new Error(
          result.error || 'The active Python pipeline could not run.',
        );
      }
      const next = result.result?.statistics_report as StatisticsReport | undefined;
      if (!next || next.status === 'FAILED') {
        throw new Error(
          next?.error || 'The statistics report was not returned by Python.',
        );
      }
      setReport(next);
      applyMasterMap(result.masterMap);
      onReportRun?.();
    } catch (runError) {
      setError(
        runError instanceof Error ? runError.message : String(runError),
      );
    } finally {
      setBusy(false);
    }
  };

  const openResearchFolder = async () => {
    setFolderMessage('');
    if (!bridge?.openResearchFolder) {
      setFolderMessage(
        'Open the FXTM Research folder manually to access exports.',
      );
      return;
    }
    const result = await bridge.openResearchFolder();
    setFolderMessage(
      result.ok
        ? `Opened ${result.folder || 'FXTM Research'}`
        : result.error || 'Folder could not be opened.',
    );
  };

  const weekly = report?.overview?.weekly || {};
  const daily = report?.overview?.daily || {};
  const combined = report?.overview?.parent_child || {};
  const weeklyRows = report?.weekly_rows || [];
  const dailyRows = report?.daily_rows || [];
  const parentRows = report?.parent_rows || [];
  const selectedParent = parentRows.find(
    (row) => String(row.weekly_parent_id) === selectedParentId,
  ) || null;
  const selectedDaily = dailyRows.filter(
    (row) => String(row.weekly_parent_id) === selectedParentId,
  );

  return <div
    className="statisticsReportPanel"
    aria-label="Weekly and Daily statistics reports"
  >
    <div className="statisticsReportHeader">
      <div>
        <b>Weekly + Daily Reports</b>
        <span>{symbol} · {caseRef || 'No case selected'}</span>
      </div>
      <div className="statisticsReportHeaderActions">
        {onClose && <button type="button" onClick={onClose}>Back</button>}
        <button
          type="button"
          disabled={busy || restoring || !analysisDatabasePath}
          onClick={() => void runLatestReport()}
        >
          {busy ? 'Running Report…' : 'Run Latest Report'}
        </button>
      </div>
    </div>

    <div className="statisticsDatasetContract">
      <span><b>Weekly:</b> 29 Jan 2023 onward</span>
      <span><b>Weekly + Daily:</b> 27 Oct 2024 onward</span>
      <span><b>Join:</b> exact saved hierarchy parent</span>
    </div>

    {restoring && <span role="status">Restoring report snapshots…</span>}
    {error && <div role="alert" className="statisticsReportError">
      <b>Report unavailable</b>
      <span>{error}</span>
    </div>}

    {report && <>
      <div className="statisticsReportRunMeta">
        <span>Report {report.report_id || 'current'}</span>
        <span>{compactDate(report.generated_at)}</span>
        {report.stale && <strong>Mapping changed · rerun required</strong>}
      </div>

      <div
        className="statisticsReportViews"
        role="tablist"
        aria-label="Report views"
      >
        {([
          ['overview', 'Overview'],
          ['weekly', 'Weekly'],
          ['combined', 'Weekly + Daily'],
          ['parent', 'Parent Breakdown'],
        ] as [ReportView, string][]).map(([key, label]) => <button
          key={key}
          type="button"
          role="tab"
          aria-selected={view === key}
          className={view === key ? 'active' : ''}
          onClick={() => setView(key)}
        >{label}</button>)}
      </div>

      {view === 'overview' && <div className="statisticsReportView">
        <div className="statisticsMetricGrid">
          <MetricCard
            label="Weekly ranges"
            metric={weekly.range_count}
            detail="From 29 Jan 2023"
          />
          <MetricCard
            label="Daily ranges"
            metric={daily.range_count}
            detail="From 27 Oct 2024"
          />
          <MetricCard
            label="Weekly parents"
            metric={combined.weekly_parent_count}
            detail="With Daily children"
          />
          <MetricCard
            label="Daily children"
            metric={combined.daily_child_count}
            detail="Exact hierarchy joins"
          />
        </div>
        <div className="statisticsBreakdownGrid">
          <CountBreakdown
            title="Weekly processing"
            counts={weekly.processing_status_counts}
          />
          <CountBreakdown
            title="Daily processing"
            counts={daily.processing_status_counts}
          />
          <CountBreakdown
            title="Weekly BOS"
            counts={weekly.bos_direction_counts}
          />
          <CountBreakdown
            title="Daily BOS"
            counts={daily.bos_direction_counts}
          />
          <CountBreakdown
            title="Weekly profiles"
            counts={weekly.profile_counts}
          />
          <CountBreakdown
            title="Daily profiles"
            counts={daily.profile_counts}
          />
          <CountBreakdown
            title="Parent-child BOS"
            counts={combined.bos_alignment_counts}
          />
          <CountBreakdown
            title="Weekly destinations"
            counts={weekly.extreme_destination_counts}
          />
        </div>
      </div>}

      {view === 'weekly' && <div className="statisticsReportView">
        <div className="statisticsSectionTitle">
          <b>All Weekly ranges</b>
          <span>{weeklyRows.length} rows</span>
        </div>
        <WeeklyTable rows={weeklyRows} />
      </div>}

      {view === 'combined' && <div className="statisticsReportView">
        <div className="statisticsMetricGrid compact">
          <MetricCard
            label="Parents"
            metric={combined.weekly_parent_count}
          />
          <MetricCard
            label="Daily children"
            metric={combined.daily_child_count}
          />
          <MetricCard
            label="Average children"
            metric={combined.average_daily_children_per_parent}
          />
          <MetricCard
            label="Unlinked Daily"
            metric={combined.unlinked_daily_count}
          />
        </div>
        <ParentTable
          rows={parentRows}
          onSelect={(identity) => {
            setSelectedParentId(identity);
            setView('parent');
          }}
        />
      </div>}

      {view === 'parent' && <div className="statisticsReportView">
        {!parentRows.length && <span>
          No Weekly parents with Daily children in the enabled dataset.
        </span>}
        {!!parentRows.length && <>
          <label className="statisticsParentSelect">
            Weekly parent
            <select
              value={selectedParentId}
              onChange={(event) => setSelectedParentId(event.target.value)}
            >
              {parentRows.map((row) => <option
                key={row.weekly_parent_id}
                value={row.weekly_parent_id}
              >
                {compactDate(row.weekly_start_date)} · {row.weekly_parent_id}
              </option>)}
            </select>
          </label>
          {selectedParent && <div className="statisticsParentSummary">
            <span>
              <b>Weekly BOS</b>
              {value(selectedParent.weekly_bos_direction)}
            </span>
            <span>
              <b>Profile</b>
              {value(selectedParent.weekly_profile)}
            </span>
            <span>
              <b>Daily children</b>
              {value(selectedParent.daily_child_count, '0')}
            </span>
            <span>
              <b>Processing</b>
              {value(selectedParent.weekly_processing_status)}
            </span>
          </div>}
          <DailyTable rows={selectedDaily} />
        </>}
      </div>}

      <div className="statisticsExports">
        <div>
          <b>Exports</b>
          <span>{report.exports?.folder || 'Export folder pending'}</span>
        </div>
        <button
          type="button"
          onClick={() => void openResearchFolder()}
        >Open Research Folder</button>
        {folderMessage && <span>{folderMessage}</span>}
      </div>

      {!!snapshots.length && <details className="statisticsSnapshotHistory">
        <summary>Saved snapshots ({snapshots.length})</summary>
        {snapshots.map((snapshot) => <div key={snapshot.report_id}>
          <span>
            {compactDate(snapshot.generated_at)} · {snapshot.report_id}
          </span>
          <strong>{snapshot.stale ? 'STALE' : 'CURRENT HASH'}</strong>
        </div>)}
      </details>}
    </>}

    {!restoring && !report && !error && <div className="statisticsReportEmpty">
      <b>No report snapshot yet</b>
      <span>
        Run the latest approved Python pipeline to create the first report.
      </span>
    </div>}
  </div>;
}
