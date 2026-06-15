// Data Collection Statistics — Python Analyst page.
// Workflow: select VPS cases -> build local input package -> run local
// Python -> display the files Python wrote. Electron computes nothing.

import React, { useEffect, useRef, useState } from 'react';
import { Database, MessageSquare, Play, RefreshCw, Square } from 'lucide-react';
import {
  buildAnalystPackage,
  listAnalystCases,
  CaseListItem,
  sanitizeAnalystLabel,
} from './analystClient';
import { AnalystResearchView } from './analystResearchView';
import { AskAnalystPanel } from './askAnalystPanel';
import { parseCsv } from './analystUtils';

type AnalystPaths = {
  ok: boolean;
  analystRoot: string;
  workspaceDir: string;
  inputDir: string;
  analystScript: string;
  fixtureInput: string;
  scriptExists: boolean;
  fixtureExists: boolean;
};

type LogEntry = { stream: 'stdout' | 'stderr' | 'system'; text: string; at: number };

type RunResult = {
  ok: boolean;
  exitCode?: number | null;
  error?: string;
  outputDir?: string;
  reportsDir?: string;
  summaryPath?: string;
  reportPath?: string;
};

type WorkspaceYear = { year: string; dir: string; hasStats: boolean; reportsDir: string; reports: string[] };
type WorkspaceSymbol = {
  symbol: string;
  dir: string;
  years: WorkspaceYear[];
  combined: { dir: string; files: string[] } | null;
};

type AnalystBridge = {
  getPaths: () => Promise<AnalystPaths>;
  checkPython: (pythonPath: string) => Promise<{ ok: boolean; version?: string; error?: string }>;
  writeInput: (fileName: string, content: string) => Promise<{ ok: boolean; path?: string; error?: string }>;
  run: (options: { pythonPath: string; inputPath: string; symbol: string; year: string }) => Promise<RunResult>;
  rebuildCombined: (options: { pythonPath: string; symbol: string }) => Promise<RunResult & { combinedDir?: string }>;
  cancel: () => Promise<{ ok: boolean; error?: string }>;
  listWorkspace: () => Promise<{ ok: boolean; workspaceDir: string; symbols: WorkspaceSymbol[] }>;
  readReport: (filePath: string) => Promise<{ ok: boolean; path?: string; content?: string; error?: string }>;
  runQuery?: (options: { pythonPath: string; queryPath: string }) => Promise<RunResult & { queryResult?: unknown; resultPath?: string }>;
  writeMediatorQuery?: (query: Record<string, unknown>) => Promise<{ ok: boolean; path?: string; query?: Record<string, unknown>; error?: string }>;
  getMediatorSettings?: () => Promise<{ ok: boolean; settings?: { apiBaseUrl: string; model: string; hasApiKey: boolean } }>;
  saveMediatorSettings?: (payload: { settings: Record<string, unknown> }) => Promise<{ ok: boolean; hasApiKey?: boolean; settingsPath?: string }>;
  buildMediatorQuery?: (payload: Record<string, unknown>) => Promise<{ ok: boolean; action?: string; query?: Record<string, unknown>; clarification?: string; error?: string }>;
  explainMediatorResult?: (payload: { question?: string; result?: unknown }) => Promise<{ ok: boolean; explanation?: string; error?: string }>;
  onLog: (callback: (entry: LogEntry) => void) => () => void;
};

declare global {
  interface Window {
    analyst?: AnalystBridge;
  }
}

const ANALYST_SYMBOLS = ['XAUUSD', 'US500.cash'];
const LOG_LIMIT = 800;
const CSV_ROW_DISPLAY_LIMIT = 300;

const logPaneStyle: React.CSSProperties = {
  background: '#05070d',
  border: '1px solid #1d2738',
  borderRadius: 8,
  padding: 12,
  height: 230,
  overflowY: 'auto',
  fontFamily: 'Consolas, monospace',
  fontSize: 12,
  whiteSpace: 'pre-wrap',
  lineHeight: 1.5,
};

const reportPaneStyle: React.CSSProperties = {
  ...logPaneStyle,
  height: 420,
  fontSize: 13,
};

const chipStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '4px 10px',
  marginRight: 8,
  marginBottom: 8,
  borderRadius: 999,
  border: '1px solid #1d2738',
  background: '#0b1220',
  fontSize: 12,
};

const tableWrapStyle: React.CSSProperties = {
  border: '1px solid #1d2738',
  borderRadius: 8,
  maxHeight: 420,
  overflow: 'auto',
  marginTop: 8,
};

const cellStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderBottom: '1px solid #131c2c',
  fontSize: 12,
  whiteSpace: 'nowrap',
  textAlign: 'left',
};

function logColor(stream: LogEntry['stream']): string {
  if (stream === 'stderr') return '#ff4d67';
  if (stream === 'system') return '#7b8794';
  return '#dbeafe';
}

function Badge({ ok, label }: { ok: boolean | null; label: string }) {
  const color = ok === null ? '#7b8794' : ok ? '#39d98a' : '#ff4d67';
  return <span style={{ ...chipStyle, borderColor: color, color }}>{label}</span>;
}

export function AnalystPage() {
  const bridge = window.analyst;
  const [paths, setPaths] = useState<AnalystPaths | null>(null);
  const [pythonPath, setPythonPath] = useState(() => localStorage.getItem('analyst.pythonPath') || 'python');
  const [pythonCheck, setPythonCheck] = useState<{ ok: boolean; text: string } | null>(null);

  const [symbol, setSymbol] = useState('XAUUSD');
  const [year, setYear] = useState(() => String(new Date().getUTCFullYear()));
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [caseErrors, setCaseErrors] = useState<string[]>([]);
  const [casesLoading, setCasesLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedRefs, setSelectedRefs] = useState<Set<string>>(new Set());

  const [paddingDays, setPaddingDays] = useState('30');
  const [building, setBuilding] = useState(false);
  const [buildLog, setBuildLog] = useState<string[]>([]);
  const [buildWarnings, setBuildWarnings] = useState<string[]>([]);
  const [packageCounts, setPackageCounts] = useState<Record<string, unknown> | null>(null);

  const [inputPath, setInputPath] = useState('');
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [exitCode, setExitCode] = useState<number | null | undefined>(undefined);
  const [runError, setRunError] = useState<string | null>(null);

  const [summary, setSummary] = useState<any>(null);
  const [reportMd, setReportMd] = useState<string | null>(null);
  const [resultsLabel, setResultsLabel] = useState<string | null>(null);
  const [reportFiles, setReportFiles] = useState<{ dir: string; files: string[] } | null>(null);
  const [activeCsv, setActiveCsv] = useState<{ name: string; columns: string[]; rows: string[][] } | null>(null);

  const [workspace, setWorkspace] = useState<WorkspaceSymbol[]>([]);
  const [viewMode, setViewMode] = useState<'research' | 'developer'>(() => {
    const saved = localStorage.getItem('analyst.viewMode');
    return saved === 'developer' ? 'developer' : 'research';
  });
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!bridge) return;
    bridge.getPaths().then((p) => {
      setPaths(p);
      setInputPath((current) => current || p.fixtureInput);
    });
    refreshWorkspace();
    const unsubscribe = bridge.onLog((entry) => {
      setLog((rows) => [...rows.slice(-LOG_LIMIT), entry]);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  useEffect(() => {
    localStorage.setItem('analyst.viewMode', viewMode);
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem('analyst.pythonPath', pythonPath);
  }, [pythonPath]);

  if (!bridge) {
    return (
      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Python Analyst</h3>
            <p>Analyst bridge unavailable.</p>
          </div>
          <Database className="blueIcon" size={22} />
        </div>
        <p className="emptyText">
          This page needs the Electron preload bridge. Start the desktop app (npm run dev / npm run start
          in the electron folder) instead of opening the renderer in a plain browser.
        </p>
      </div>
    );
  }

  const refreshWorkspace = () => {
    window.analyst?.listWorkspace().then((res) => {
      if (res.ok) setWorkspace(res.symbols);
    });
  };

  const checkPython = async () => {
    setPythonCheck(null);
    const res = await bridge.checkPython(pythonPath);
    setPythonCheck(res.ok ? { ok: true, text: res.version || 'ok' } : { ok: false, text: res.error || 'failed' });
  };

  const loadCases = async () => {
    setCasesLoading(true);
    setCaseErrors([]);
    try {
      const result = await listAnalystCases(symbol);
      setCases(result.cases);
      setCaseErrors(result.errors);
    } catch (err) {
      setCases([]);
      setCaseErrors([String((err as Error).message || err)]);
    }
    setCasesLoading(false);
  };

  const toggleRef = (ref: string) => {
    setSelectedRefs((current) => {
      const next = new Set(current);
      if (next.has(ref)) next.delete(ref); else next.add(ref);
      return next;
    });
  };

  const buildPackage = async () => {
    if (selectedRefs.size === 0) return;
    setBuilding(true);
    setBuildLog([]);
    setBuildWarnings([]);
    setPackageCounts(null);
    const appendBuild = (line: string) => setBuildLog((rows) => [...rows, line]);
    try {
      const result = await buildAnalystPackage({
        symbol,
        year,
        caseRefs: Array.from(selectedRefs),
        paddingDays: Math.max(0, Number(paddingDays) || 0),
        onProgress: appendBuild,
      });
      setBuildWarnings(result.warnings);
      setPackageCounts(result.counts as any);
      const written = await bridge.writeInput(result.fileName, result.json);
      if (written.ok && written.path) {
        setInputPath(written.path);
        appendBuild(`package written: ${written.path}`);
      } else {
        appendBuild(`package write FAILED: ${written.error || 'unknown error'}`);
      }
    } catch (err) {
      appendBuild(`build FAILED: ${String((err as Error).message || err)}`);
    }
    setBuilding(false);
  };

  const findYearReports = async (sym: string, yr: string) => {
    const res = await bridge.listWorkspace();
    if (!res.ok) return null;
    const symEntry = res.symbols.find((s) => s.symbol.toUpperCase() === sym.toUpperCase());
    const yearEntry = symEntry?.years.find((y) => y.year === yr);
    return yearEntry ? { dir: yearEntry.reportsDir, files: yearEntry.reports } : null;
  };

  const loadResults = async (
    summaryPath: string,
    reportPath: string,
    label: string,
    reports: { dir: string; files: string[] } | null
  ) => {
    setSummary(null);
    setReportMd(null);
    setActiveCsv(null);
    setResultsLabel(label);
    setReportFiles(reports);
    const [summaryRes, reportRes] = await Promise.all([
      bridge.readReport(summaryPath),
      bridge.readReport(reportPath),
    ]);
    if (summaryRes.ok && summaryRes.content) {
      try {
        setSummary(JSON.parse(summaryRes.content));
      } catch {
        setSummary({ parse_error: true, raw: summaryRes.content });
      }
    } else {
      setSummary({ error: summaryRes.error || 'analyst_summary.json not readable' });
    }
    setReportMd(reportRes.ok ? reportRes.content || '' : `Could not read report: ${reportRes.error}`);
  };

  const openCsv = async (fileName: string) => {
    if (!reportFiles) return;
    const res = await bridge.readReport(`${reportFiles.dir}/${fileName}`);
    if (res.ok && res.content !== undefined) {
      const parsed = parseCsv(res.content);
      setActiveCsv({ name: fileName, columns: parsed.columns, rows: parsed.rows });
    } else {
      setActiveCsv({ name: fileName, columns: ['error'], rows: [[res.error || 'unreadable']] });
    }
  };

  const run = async () => {
    setRunning(true);
    setRunError(null);
    setExitCode(undefined);
    setLog([]);
    setSummary(null);
    setReportMd(null);
    setActiveCsv(null);
    const batchLabel = sanitizeAnalystLabel(year);
    const result = await bridge.run({ pythonPath, inputPath, symbol, year: batchLabel });
    setRunning(false);
    setExitCode(result.exitCode);
    if (result.error) setRunError(result.error);
    if (result.ok && result.summaryPath && result.reportPath) {
      const reports = await findYearReports(symbol, batchLabel);
      await loadResults(
        result.summaryPath,
        result.reportPath,
        `${symbol.toUpperCase()} ${batchLabel} (fresh run)`,
        reports
      );
    }
    refreshWorkspace();
  };

  const rebuildCombined = async () => {
    setRunning(true);
    setRunError(null);
    setExitCode(undefined);
    const result = await bridge.rebuildCombined({ pythonPath, symbol });
    setRunning(false);
    setExitCode(result.exitCode);
    if (result.error) setRunError(result.error);
    refreshWorkspace();
  };

  const cancel = () => bridge.cancel();

  const loadYear = (sym: WorkspaceSymbol, yr: WorkspaceYear) => {
    loadResults(
      `${yr.reportsDir}/analyst_summary.json`,
      `${yr.reportsDir}/analyst_report.md`,
      `${sym.symbol} ${yr.year} (saved)`,
      { dir: yr.reportsDir, files: yr.reports }
    );
  };

  const counts = summary?.counts || {};
  const filteredCases = cases.filter((row) => {
    const needle = search.trim().toLowerCase();
    if (!needle) return true;
    return `${row.name} ${row.case_ref} ${row.timeframe}`.toLowerCase().includes(needle);
  });
  const csvFiles = (reportFiles?.files || []).filter((f) => f.endsWith('.csv'));
  const yearLabelsForSymbol =
    workspace.find((s) => s.symbol.toUpperCase() === symbol.toUpperCase())?.years.map((y) => y.year) || [];
  const symbolWorkspace = workspace.find((s) => s.symbol.toUpperCase() === symbol.toUpperCase());
  const yearsForSymbol = symbolWorkspace?.years || [];
  const combinedDir = symbolWorkspace?.combined?.dir ?? null;

  const mapDataSection = (
    <>
      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Case Selection</h3>
            <p>Saved cases from the VPS. Only explicitly selected cases are analyzed.</p>
          </div>
          <button className="primaryBtn" onClick={loadCases} disabled={casesLoading}>
            <RefreshCw size={12} /> {casesLoading ? 'Loading…' : 'Refresh cases'}
          </button>
        </div>
        <div className="formSection">
          <div className="scenarioForm">
            <label>
              Symbol
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {ANALYST_SYMBOLS.map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <label>
              Search
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="filter by name / ref / timeframe" />
            </label>
          </div>
          {caseErrors.map((err, i) => <p key={i} style={{ color: '#ff4d67' }}>{err}</p>)}
          <div style={{ marginBottom: 8 }}>
            <span style={chipStyle}>{selectedRefs.size} selected</span>
            <span style={chipStyle}>{filteredCases.length} shown / {cases.length} loaded</span>
            {selectedRefs.size > 0 && (
              <button className="primaryBtn" onClick={() => setSelectedRefs(new Set())}>Clear selection</button>
            )}
          </div>
          <div style={{ ...tableWrapStyle, maxHeight: 280 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={cellStyle}></th>
                  <th style={cellStyle}>Name</th>
                  <th style={cellStyle}>case_ref</th>
                  <th style={cellStyle}>Kind</th>
                  <th style={cellStyle}>TF</th>
                  <th style={cellStyle}>Updated</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.length === 0 && (
                  <tr><td style={cellStyle} colSpan={6}>No cases loaded. Click Refresh cases.</td></tr>
                )}
                {filteredCases.map((row) => (
                  <tr key={row.case_ref}>
                    <td style={cellStyle}>
                      <input
                        type="checkbox"
                        checked={selectedRefs.has(row.case_ref)}
                        onChange={() => toggleRef(row.case_ref)}
                      />
                    </td>
                    <td style={cellStyle}>{row.name}</td>
                    <td style={{ ...cellStyle, fontFamily: 'Consolas, monospace' }}>{row.case_ref}</td>
                    <td style={cellStyle}>{row.kind}</td>
                    <td style={cellStyle}>{row.timeframe}</td>
                    <td style={cellStyle}>{row.updated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Build Package</h3>
            <p>Fetches ranges, events, candles and raw ledgers for the selected cases into one local package.</p>
          </div>
        </div>
        <div className="formSection">
          <div className="scenarioForm">
            <label>
              Year label
              <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="e.g. 2020 or 2019_Q3-2021_Q1" />
            </label>
            <label>
              Candle padding (days)
              <input value={paddingDays} onChange={(e) => setPaddingDays(e.target.value)} />
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="primaryBtn" onClick={buildPackage} disabled={building || selectedRefs.size === 0}>
              {building ? 'Building…' : `Fetch + Build ${symbol.toUpperCase()}_${sanitizeAnalystLabel(year)}.json`}
            </button>
            {packageCounts && (
              <>
                <Badge ok={true} label={`ranges: ${String((packageCounts as any).ranges)}`} />
                <Badge ok={true} label={`events: ${String((packageCounts as any).events)}`} />
                <Badge ok={true} label={`ledgers: ${String((packageCounts as any).ledgers)}`} />
                <Badge
                  ok={true}
                  label={`candles: ${Object.entries(((packageCounts as any).candles || {}) as Record<string, number>).map(([tf, n]) => `${tf}:${n}`).join(' ') || 'none'}`}
                />
              </>
            )}
          </div>
          {buildWarnings.map((warning, i) => (
            <p key={i} style={{ color: '#ffbf2f', margin: '4px 0' }}>warning: {warning}</p>
          ))}
          {buildLog.length > 0 && (
            <div style={{ ...logPaneStyle, height: 160, marginTop: 8 }}>
              {buildLog.map((line, i) => <span key={i}>{line}{'\n'}</span>)}
            </div>
          )}
        </div>
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Run Analyst</h3>
            <p>Runs analyst_v1.py on one input package and writes reports into workspace/SYMBOL/YEAR.</p>
          </div>
          <Play className="blueIcon" size={22} />
        </div>
        <div className="formSection">
          <div className="scenarioForm">
            <label>
              Input package (.json)
              <input value={inputPath} onChange={(e) => setInputPath(e.target.value)} />
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="primaryBtn" onClick={() => paths && setInputPath(paths.fixtureInput)}>Use fixture package</button>
            <button className="primaryBtn" onClick={run} disabled={running}>{running ? 'Running…' : 'Run Analyst'}</button>
            <button className="primaryBtn" onClick={rebuildCombined} disabled={running}>Rebuild Combined</button>
            <button className="primaryBtn" onClick={cancel} disabled={!running}><Square size={12} /> Cancel</button>
            {exitCode !== undefined && (
              <Badge ok={exitCode === 0} label={`exit code: ${exitCode === null ? 'killed' : exitCode}`} />
            )}
          </div>
          {runError && <p style={{ color: '#ff4d67' }}>{runError}</p>}
          <div ref={logRef} style={{ ...logPaneStyle, marginTop: 10 }}>
            {log.length === 0 && <span style={{ color: '#7b8794' }}>Process log appears here.</span>}
            {log.map((entry, i) => (
              <span key={i} style={{ color: logColor(entry.stream) }}>{entry.text}{entry.text.endsWith('\n') ? '' : '\n'}</span>
            ))}
          </div>
        </div>
      </div>
    </>
  );

  return (
    <>
      <div className="analystModeBar">
        <button
          type="button"
          className={`analystModeBtn${viewMode === 'research' ? ' active' : ''}`}
          onClick={() => setViewMode('research')}
        >
          Research View
        </button>
        <button
          type="button"
          className={`analystModeBtn${viewMode === 'developer' ? ' active' : ''}`}
          onClick={() => setViewMode('developer')}
        >
          Developer View
        </button>
        <span className="emptyText" style={{ marginLeft: 8 }}>
          {viewMode === 'research' ? 'Validate & learn — CSVs live under Advanced' : 'Full engine debug surface'}
        </span>
      </div>

      {viewMode === 'research' && (
        <>
          <details className="card largeCard mapDataFold">
            <summary style={{ cursor: 'pointer', fontWeight: 900, color: '#dbeafe', padding: 4 }}>
              Map data — fetch cases, build package, run analyst
            </summary>
            <div style={{ marginTop: 12 }}>
              <div className="card largeCard" style={{ marginBottom: 12 }}>
                <div className="cardHeader tight">
                  <div>
                    <h3>Local Python Runtime</h3>
                    <p>Python path and workspace (expand only if Run Analyst fails).</p>
                  </div>
                  <Database className="blueIcon" size={22} />
                </div>
                <div className="formSection">
                  <div className="scenarioForm">
                    <label>
                      Python executable
                      <input value={pythonPath} onChange={(e) => setPythonPath(e.target.value)} />
                    </label>
                  </div>
                  <button className="primaryBtn" onClick={checkPython}>Check Python</button>
                  <div style={{ marginTop: 10 }}>
                    {pythonCheck && <Badge ok={pythonCheck.ok} label={pythonCheck.text} />}
                    {paths && <Badge ok={paths.scriptExists} label={paths.scriptExists ? 'analyst_v1.py found' : 'analyst_v1.py missing'} />}
                  </div>
                </div>
              </div>
              {mapDataSection}
            </div>
          </details>

          <AnalystResearchView
            symbol={symbol}
            pythonPath={pythonPath}
            yearLabels={yearLabelsForSymbol}
            years={yearsForSymbol}
            combinedDir={combinedDir}
            onRefreshWorkspace={refreshWorkspace}
          />
        </>
      )}

      {viewMode === 'developer' && (
        <>
      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Local Python Runtime</h3>
            <p>The analyst engine runs locally and only reads/writes the analyst workspace.</p>
          </div>
          <Database className="blueIcon" size={22} />
        </div>
        <div className="formSection">
          <div className="scenarioForm">
            <label>
              Python executable
              <input value={pythonPath} onChange={(e) => setPythonPath(e.target.value)} />
            </label>
          </div>
          <button className="primaryBtn" onClick={checkPython}>Check Python</button>
          <div style={{ marginTop: 10 }}>
            {pythonCheck && <Badge ok={pythonCheck.ok} label={pythonCheck.text} />}
            {paths && <Badge ok={paths.scriptExists} label={paths.scriptExists ? 'analyst_v1.py found' : 'analyst_v1.py missing'} />}
          </div>
          {paths && (
            <p className="emptyText" style={{ marginTop: 6 }}>Workspace: {paths.workspaceDir}</p>
          )}
        </div>
      </div>

      {mapDataSection}

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Ask Analyst</h3>
            <p>Natural-language questions → AI query JSON → Python calculates → AI explains (numbers from Python only).</p>
          </div>
          <MessageSquare className="blueIcon" size={22} />
        </div>
        <AskAnalystPanel symbol={symbol} pythonPath={pythonPath} yearLabels={yearLabelsForSymbol} researchMode={false} />
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Results{resultsLabel ? ` — ${resultsLabel}` : ''}</h3>
            <p>Summary, markdown report, and rule-model CSVs exactly as Python wrote them.</p>
          </div>
        </div>
        {!summary && !reportMd && <p className="emptyText">Run the analyst or load a saved year below.</p>}
        {summary && (
          <div className="formSection">
            <div>
              <span style={chipStyle}>label: {summary.label ?? '-'}</span>
              <span style={chipStyle}>engine: {summary.engine_version ?? '-'}</span>
              <span style={chipStyle}>cases: {counts.cases ?? '-'}</span>
              <span style={chipStyle}>ranges: {counts.ranges ?? '-'}</span>
              <span style={chipStyle}>events: {counts.events ?? '-'}</span>
              <span style={chipStyle}>warnings: {counts.warnings ?? '-'}</span>
            </div>
            <details>
              <summary style={{ cursor: 'pointer', color: '#7b8794' }}>analyst_summary.json (raw)</summary>
              <pre style={{ ...logPaneStyle, height: 300, marginTop: 8 }}>{JSON.stringify(summary, null, 2)}</pre>
            </details>
          </div>
        )}
        {csvFiles.length > 0 && (
          <div className="formSection">
            <h4>Report files</h4>
            <div>
              {csvFiles.map((file) => (
                <button
                  key={file}
                  className="primaryBtn"
                  style={{ marginRight: 6, marginBottom: 6, opacity: activeCsv?.name === file ? 1 : 0.75 }}
                  onClick={() => openCsv(file)}
                >
                  {file.replace('.csv', '')}
                </button>
              ))}
            </div>
            {activeCsv && (
              <>
                <p className="emptyText">
                  {activeCsv.name} — {activeCsv.rows.length} rows
                  {activeCsv.rows.length > CSV_ROW_DISPLAY_LIMIT ? ` (showing first ${CSV_ROW_DISPLAY_LIMIT})` : ''}
                </p>
                <div style={tableWrapStyle}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>{activeCsv.columns.map((col) => <th key={col} style={{ ...cellStyle, position: 'sticky', top: 0, background: '#0b1220' }}>{col}</th>)}</tr>
                    </thead>
                    <tbody>
                      {activeCsv.rows.length === 0 && (
                        <tr><td style={cellStyle} colSpan={Math.max(1, activeCsv.columns.length)}>No rows.</td></tr>
                      )}
                      {activeCsv.rows.slice(0, CSV_ROW_DISPLAY_LIMIT).map((row, i) => (
                        <tr key={i}>{row.map((cell, j) => <td key={j} style={cellStyle}>{cell}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
        {reportMd !== null && (
          <div className="formSection">
            <h4>analyst_report.md</h4>
            <pre style={reportPaneStyle}>{reportMd}</pre>
          </div>
        )}
      </div>

      <div className="card largeCard">
        <div className="cardHeader tight">
          <div>
            <h3>Workspace</h3>
            <p>Analyzed years saved under the analyst workspace.</p>
          </div>
          <button className="primaryBtn" onClick={refreshWorkspace}><RefreshCw size={12} /> Refresh</button>
        </div>
        {workspace.length === 0 && <p className="emptyText">No analyzed years yet.</p>}
        {workspace.map((sym) => (
          <div className="formSection" key={sym.symbol}>
            <h4>{sym.symbol}</h4>
            {sym.years.map((yr) => (
              <div key={yr.year} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 6 }}>
                <span style={chipStyle}>{yr.year}</span>
                <Badge ok={yr.hasStats} label={yr.hasStats ? 'yearly_stats saved' : 'incomplete'} />
                <span style={{ color: '#7b8794', fontSize: 12 }}>{yr.reports.length} report files</span>
                <button className="primaryBtn" onClick={() => loadYear(sym, yr)}>Load reports</button>
              </div>
            ))}
            {sym.combined && (
              <p className="emptyText">combined: {sym.combined.files.join(', ') || 'empty'}</p>
            )}
          </div>
        ))}
      </div>
        </>
      )}
    </>
  );
}
