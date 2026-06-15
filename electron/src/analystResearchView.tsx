// Research View — human-readable analyst dashboard (Validate + Learn).

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { AskAnalystPanel } from './askAnalystPanel';
import { SqlInspectorPanel } from './sqlInspectorPanel';
import {
  buildContinuationQuery,
  buildRangeListQuery,
  hydratePreset,
  msToDate,
  pctFromRatio,
  pctText,
  retracementPctDisplay,
} from './analystPresets';
import { csvRowsToObjects, pickRandom } from './analystUtils';
import {
  journalCounts,
  loadValidationJournal,
  saveValidationEntry,
  ValidationEntry,
} from './validationJournal';

type WorkspaceYear = {
  year: string;
  dir: string;
  hasStats: boolean;
  reportsDir: string;
  reports: string[];
};

type YearlyStats = {
  label?: string;
  counts?: { cases?: number; ranges?: number; warnings?: number };
  rule_stats?: {
    range_metrics?: { by_layer?: Record<string, { count?: number }> };
    retracement?: { class_counts?: Record<string, number> };
    outcomes?: { counts?: Record<string, number> };
    bos_reclaim?: { reclaim_rate?: number };
  };
};

type WeeklySample = {
  range_id: string;
  range_high_price: number;
  range_low_price: number;
  range_high_time_ms?: number;
  range_low_time_ms?: number;
  status?: string;
  year_label?: string;
};

type RetracementSample = {
  range_id: string;
  direction_of_break: string;
  retracement_class: string;
  retracement_percent: string;
  retracement_price: string;
  retracement_time: string;
  outcome: string;
  parent_range_id: string;
};

type InsightCard = {
  title: string;
  sampleSize: number | string;
  lines: string[];
};

type Props = {
  symbol: string;
  pythonPath: string;
  yearLabels: string[];
  years: WorkspaceYear[];
  combinedDir: string | null;
  onRefreshWorkspace: () => void;
};

const sectionTitle: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 900,
  color: '#dbeafe',
  margin: '0 0 8px',
};

const statBlock: React.CSSProperties = {
  background: '#060b12',
  border: '1px solid #1e2c3b',
  borderRadius: 14,
  padding: 14,
};

const labelStyle: React.CSSProperties = {
  color: '#7b8794',
  fontSize: 11,
  fontWeight: 900,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const valueStyle: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 900,
  color: '#e8eef7',
  marginTop: 4,
};

export function AnalystResearchView({
  symbol,
  pythonPath,
  yearLabels,
  years,
  combinedDir,
  onRefreshWorkspace,
}: Props) {
  const bridge = window.analyst;
  const [batch, setBatch] = useState(yearLabels[0] || '');
  const [stats, setStats] = useState<YearlyStats | null>(null);
  const [combinedStats, setCombinedStats] = useState<Record<string, unknown> | null>(null);
  const [insights, setInsights] = useState<InsightCard[]>([]);
  const [weeklySample, setWeeklySample] = useState<WeeklySample | null>(null);
  const [weeklyStatus, setWeeklyStatus] = useState<string | null>(null);
  const [retrSample, setRetrSample] = useState<RetracementSample | null>(null);
  const [retrStatus, setRetrStatus] = useState<string | null>(null);
  const [samplerBusy, setSamplerBusy] = useState(false);
  const [journal, setJournal] = useState<ValidationEntry[]>([]);
  const [randomSeed, setRandomSeed] = useState(() => Date.now());

  const counts = useMemo(() => journalCounts(symbol), [journal, symbol]);

  const loadStats = useCallback(async () => {
    if (!bridge || !batch) return;
    const yr = years.find((y) => y.year === batch);
    if (!yr) return;
    const res = await bridge.readReport(`${yr.dir}/yearly_stats.json`);
    if (res.ok && res.content) {
      try {
        setStats(JSON.parse(res.content));
      } catch {
        setStats(null);
      }
    }
  }, [bridge, batch, years]);

  const loadCombined = useCallback(async () => {
    if (!bridge || !combinedDir) return;
    const res = await bridge.readReport(`${combinedDir}/${symbol.toUpperCase()}_combined_stats.json`);
    if (res.ok && res.content) {
      try {
        setCombinedStats(JSON.parse(res.content));
      } catch {
        setCombinedStats(null);
      }
    }
  }, [bridge, combinedDir, symbol]);

  const loadInsights = useCallback(async () => {
    if (!bridge || yearLabels.length === 0) return;
    const cards: InsightCard[] = [];

    const runInsight = async (title: string, layer: string, retrClass: string) => {
      const q = buildContinuationQuery({
        symbol,
        yearLabels,
        childLayer: layer,
        retracementClass: retrClass,
        queryId: `insight_${layer}_${retrClass}`,
      });
      const written = await bridge.writeMediatorQuery!(q);
      if (!written.ok || !written.path) return;
      const run = await bridge.runQuery!({ pythonPath, queryPath: written.path });
      const m = (run.queryResult as { metrics?: Record<string, number> })?.metrics;
      if (!m) return;
      const sample = m.sample_size ?? 0;
      const continued = m.continued_count ?? 0;
      const failed = m.failed_count ?? 0;
      const abandoned = m.abandoned_count ?? 0;
      const unresolved = m.unresolved_count ?? 0;
      const resolved = continued + failed + abandoned;
      cards.push({
        title,
        sampleSize: sample,
        lines: [
          `Continuation: ${pctFromRatio(continued, resolved, 0)}`,
          `Failure: ${pctFromRatio(failed, resolved, 0)}`,
          `Abandon: ${pctFromRatio(abandoned, resolved, 0)}`,
          unresolved > 0 ? `Unresolved: ${unresolved}` : '',
        ].filter(Boolean),
      });
    };

    try {
      await runInsight('Deep Daily Retracements', 'DAILY', 'DEEP');
      await runInsight('Shallow Daily Retracements', 'DAILY', 'SHALLOW');
      await runInsight('Deep Weekly Retracements', 'WEEKLY', 'DEEP');
    } catch {
      // non-fatal
    }
    setInsights(cards);
  }, [bridge, symbol, yearLabels, pythonPath]);

  useEffect(() => {
    if (yearLabels.length && !batch) setBatch(yearLabels[0]);
    else if (batch && !yearLabels.includes(batch) && yearLabels[0]) setBatch(yearLabels[0]);
  }, [yearLabels, batch]);

  useEffect(() => {
    loadStats();
    loadCombined();
    setJournal(loadValidationJournal());
  }, [loadStats, loadCombined]);

  useEffect(() => {
    if (yearLabels.length > 0) loadInsights();
  }, [yearLabels.join(','), symbol]);

  const auditScore = useMemo(() => {
    const warnings = stats?.counts?.warnings ?? 0;
    const ranges = stats?.counts?.ranges ?? 0;
    if (!ranges) return null;
    const score = Math.max(0, Math.min(100, Math.round(100 - (warnings / ranges) * 100)));
    return score;
  }, [stats]);

  const layerCounts = stats?.rule_stats?.range_metrics?.by_layer || {};

  const nextWeekly = async () => {
    if (!bridge?.runQuery || !bridge.writeMediatorQuery || yearLabels.length === 0) return;
    setSamplerBusy(true);
    setWeeklyStatus(null);
    const seed = Date.now();
    setRandomSeed(seed);
    try {
      const q = buildRangeListQuery({
        symbol,
        yearLabels,
        layer: 'WEEKLY',
        rowLimit: 1,
        randomSeed: seed,
      });
      const written = await bridge.writeMediatorQuery(q);
      if (!written.ok || !written.path) return;
      const run = await bridge.runQuery({ pythonPath, queryPath: written.path });
      const rows = (run.queryResult as { source_rows?: WeeklySample[] })?.source_rows;
      if (rows?.[0]) setWeeklySample(rows[0]);
    } finally {
      setSamplerBusy(false);
    }
  };

  const nextRetracement = async () => {
    if (!bridge) return;
    setSamplerBusy(true);
    setRetrStatus(null);
    try {
      const pool: RetracementSample[] = [];
      for (const yr of years) {
        const path = `${yr.reportsDir}/retracement_stats.csv`;
        const res = await bridge.readReport(path);
        if (!res.ok || !res.content) continue;
        const rows = csvRowsToObjects(res.content);
        for (const row of rows) {
          if (row.structure_layer?.toUpperCase() !== 'DAILY') continue;
          if (!row.retracement_class) continue;
          pool.push({
            range_id: row.range_id,
            direction_of_break: row.direction_of_break,
            retracement_class: row.retracement_class,
            retracement_percent: row.retracement_percent,
            retracement_price: row.retracement_price,
            retracement_time: row.retracement_time,
            outcome: row.outcome,
            parent_range_id: row.parent_range_id,
          });
        }
      }
      const pick = pickRandom(pool);
      setRetrSample(pick);
    } finally {
      setSamplerBusy(false);
    }
  };

  const markWeekly = (status: 'PASS' | 'REVIEW') => {
    if (!weeklySample) return;
    saveValidationEntry({
      symbol,
      batch,
      kind: 'weekly_range',
      subjectId: weeklySample.range_id,
      status,
      snapshot: weeklySample as unknown as Record<string, unknown>,
    });
    setWeeklyStatus(status);
    setJournal(loadValidationJournal());
  };

  const markRetracement = (status: 'PASS' | 'REVIEW') => {
    if (!retrSample) return;
    saveValidationEntry({
      symbol,
      batch,
      kind: 'daily_retracement',
      subjectId: retrSample.range_id,
      status,
      snapshot: retrSample as unknown as Record<string, unknown>,
    });
    setRetrStatus(status);
    setJournal(loadValidationJournal());
  };

  const combinedTotals = (combinedStats?.totals as Record<string, number>) || {};

  return (
    <div className="researchStack">
      <div className="researchHero card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Research View</h3>
            <p>Map → Validate → Learn. Numbers come from Python; you stay on the chart.</p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              value={batch}
              onChange={(e) => setBatch(e.target.value)}
              style={{ background: '#050b12', border: '1px solid #203040', color: '#e8eef7', borderRadius: 12, padding: '8px 12px' }}
            >
              {yearLabels.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <button className="primaryBtn solo" type="button" onClick={() => { onRefreshWorkspace(); loadStats(); loadCombined(); }}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>
        <div className="researchFlow">
          <span>Map</span>
          <ChevronRight size={14} />
          <span>Validate</span>
          <ChevronRight size={14} />
          <span>Learn</span>
          <ChevronRight size={14} />
          <span className="mutedFlow">Sleep</span>
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: '#7b8794' }}>
          Session notes: {counts.pass} passed · {counts.review} flagged for review
        </div>
      </div>

      <div className="card largeCard">
        <h4 style={sectionTitle}>Dataset Health</h4>
        <p className="emptyText" style={{ marginBottom: 12 }}>Batch: {batch || '—'}</p>
        <div className="metricGrid">
          <div style={statBlock}>
            <span style={labelStyle}>Weekly ranges</span>
            <div style={valueStyle}>{layerCounts.WEEKLY?.count ?? '—'}</div>
          </div>
          <div style={statBlock}>
            <span style={labelStyle}>Daily ranges</span>
            <div style={valueStyle}>{layerCounts.DAILY?.count ?? '—'}</div>
          </div>
          <div style={statBlock}>
            <span style={labelStyle}>Intraday ranges</span>
            <div style={valueStyle}>{layerCounts.INTRADAY?.count ?? layerCounts.MICRO?.count ?? 0}</div>
          </div>
          <div style={statBlock}>
            <span style={labelStyle}>Audit score</span>
            <div style={{ ...valueStyle, color: auditScore !== null && auditScore >= 90 ? '#42e68a' : '#ffbf2f' }}>
              {auditScore !== null ? `${auditScore}%` : '—'}
            </div>
          </div>
        </div>
        <div className="mitigationRow" style={{ marginTop: 12 }}>
          <div className="pill"><span>Warnings</span><b>{stats?.counts?.warnings ?? '—'}</b></div>
          <div className="pill"><span>Total ranges</span><b>{stats?.counts?.ranges ?? combinedTotals.ranges ?? '—'}</b></div>
          <div className="pill"><span>Cases</span><b>{stats?.counts?.cases ?? combinedTotals.cases ?? '—'}</b></div>
          <div className="pill"><span>Batches</span><b>{yearLabels.length}</b></div>
        </div>
      </div>

      <div className="researchSamplerGrid">
        <div className="card largeCard">
          <h4 style={sectionTitle}>Random Validation — Weekly</h4>
          <p className="emptyText">Spot-check a weekly range against TradingView. High and low with dates.</p>
          {!weeklySample && (
            <p className="emptyText">Click below to pull a random weekly range from your workspace.</p>
          )}
          {weeklySample && (
            <div className="validationCard">
              <div className="validationTitle">Weekly Range #{weeklySample.range_id}</div>
              <div className="validationRow">
                <span style={labelStyle}>High</span>
                <b>{weeklySample.range_high_price}</b>
                <em>{msToDate(weeklySample.range_high_time_ms)}</em>
              </div>
              <div className="validationRow">
                <span style={labelStyle}>Low</span>
                <b>{weeklySample.range_low_price}</b>
                <em>{msToDate(weeklySample.range_low_time_ms)}</em>
              </div>
              <div className="validationRow">
                <span style={labelStyle}>Status</span>
                <b>{weeklyStatus || weeklySample.status || 'CHECK CHART'}</b>
              </div>
            </div>
          )}
          <div className="btnRow" style={{ marginTop: 12 }}>
            <button className="primaryBtn solo" type="button" disabled={samplerBusy} onClick={nextWeekly}>
              {samplerBusy ? 'Loading…' : 'Next Random Weekly'}
            </button>
            {weeklySample && (
              <>
                <button className="primaryBtn solo passBtn" type="button" onClick={() => markWeekly('PASS')}>
                  <CheckCircle2 size={14} /> PASS
                </button>
                <button className="primaryBtn solo reviewBtn" type="button" onClick={() => markWeekly('REVIEW')}>
                  <HelpCircle size={14} /> REVIEW
                </button>
              </>
            )}
          </div>
        </div>

        <div className="card largeCard">
          <h4 style={sectionTitle}>Retracement Validation — Daily</h4>
          <p className="emptyText">BOS direction, retracement depth, price, and outcome — no column decoding.</p>
          {!retrSample && (
            <p className="emptyText">Pull a random classified daily retracement from saved reports.</p>
          )}
          {retrSample && (
            <div className="validationCard">
              <div className="validationTitle">Daily Range #{retrSample.range_id}</div>
              <div className="validationRow">
                <span style={labelStyle}>BOS</span>
                <b>{retrSample.direction_of_break}</b>
              </div>
              <div className="validationRow">
                <span style={labelStyle}>Retracement</span>
                <b>{retrSample.retracement_class}</b>
                <em>{retracementPctDisplay(Number(retrSample.retracement_percent))}</em>
              </div>
              <div className="validationRow">
                <span style={labelStyle}>Price</span>
                <b>{retrSample.retracement_price}</b>
                <em>{retrSample.retracement_time?.slice(0, 10) || '—'}</em>
              </div>
              <div className="validationRow">
                <span style={labelStyle}>Outcome</span>
                <b>{retrSample.outcome}</b>
              </div>
              <div className="validationRow">
                <span style={labelStyle}>Marked</span>
                <b>{retrStatus || '—'}</b>
              </div>
            </div>
          )}
          <div className="btnRow" style={{ marginTop: 12 }}>
            <button className="primaryBtn solo" type="button" disabled={samplerBusy} onClick={nextRetracement}>
              {samplerBusy ? 'Loading…' : 'Next Random Daily Retrace'}
            </button>
            {retrSample && (
              <>
                <button className="primaryBtn solo passBtn" type="button" onClick={() => markRetracement('PASS')}>
                  <CheckCircle2 size={14} /> PASS
                </button>
                <button className="primaryBtn solo reviewBtn" type="button" onClick={() => markRetracement('REVIEW')}>
                  <HelpCircle size={14} /> REVIEW
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h4 style={sectionTitle}>Knowledge Discovered</h4>
            <p className="emptyText">Human-readable stats from your saved workspace (Python-calculated).</p>
          </div>
          <Sparkles className="goldIcon" size={20} />
        </div>
        {insights.length === 0 && <p className="emptyText">Loading insights from workspace batches…</p>}
        <div className="insightGrid">
          {insights.map((card) => (
            <div key={card.title} className="insightCard">
              <b>{card.title}</b>
              <span style={labelStyle}>Sample size</span>
              <div style={{ fontSize: 20, fontWeight: 900 }}>{card.sampleSize}</div>
              {card.lines.map((line) => (
                <p key={line} className="insightLine">{line}</p>
              ))}
            </div>
          ))}
          {stats?.rule_stats?.bos_reclaim?.reclaim_rate !== undefined && (
            <div className="insightCard">
              <b>Daily BOS Reclaim</b>
              <span style={labelStyle}>Reclaim rate (batch)</span>
              <div style={{ fontSize: 20, fontWeight: 900 }}>
                {pctText(stats.rule_stats.bos_reclaim.reclaim_rate, 0)}
              </div>
              <p className="insightLine">After reclaim, continuation signals in reclaim report.</p>
            </div>
          )}
        </div>
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>SQL Inspector</h3>
            <p>11pm rabbit-hole mode — Ollama writes SQL, Python answers from your workspace.</p>
          </div>
        </div>
        <SqlInspectorPanel symbol={symbol} pythonPath={pythonPath} yearLabels={yearLabels} />
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Ask Analyst</h3>
            <p>Preset queries + Ollama for custom questions. JSON stays under Advanced.</p>
          </div>
        </div>
        <AskAnalystPanel
          symbol={symbol}
          pythonPath={pythonPath}
          yearLabels={yearLabels}
          researchMode
          randomSeed={randomSeed}
        />
      </div>
    </div>
  );
}
