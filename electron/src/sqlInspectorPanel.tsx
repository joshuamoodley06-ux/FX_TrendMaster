// SQL Inspector — Ollama generates read-only DuckDB SQL; Python executes.

import React, { useState } from 'react';
import { Play, Sparkles } from 'lucide-react';

type SqlResult = {
  status?: string;
  row_count?: number;
  columns?: string[];
  rows?: Record<string, unknown>[];
  sql?: string;
  error?: string;
  warnings?: string[];
};

type Props = {
  symbol: string;
  pythonPath: string;
  yearLabels: string[];
};

const paneStyle: React.CSSProperties = {
  background: '#05070d',
  border: '1px solid #1d2738',
  borderRadius: 8,
  padding: 12,
  fontFamily: 'Consolas, monospace',
  fontSize: 12,
  whiteSpace: 'pre-wrap',
  lineHeight: 1.5,
};

const SQL_PRESETS = [
  'Show 5 random Weekly ranges with high and low',
  'Daily ranges in discount that later had BOS up',
  'Deep daily retracements with outcome and percent',
  'Weekly ranges with more than 3 child daily ranges',
];

export function SqlInspectorPanel({ symbol, pythonPath, yearLabels }: Props) {
  const bridge = window.analyst;
  const [question, setQuestion] = useState('');
  const [sql, setSql] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clarification, setClarification] = useState<string | null>(null);
  const [result, setResult] = useState<SqlResult | null>(null);
  const [aiNote, setAiNote] = useState<string | null>(null);

  if (!bridge?.buildMediatorSql || !bridge.runSqlInspector) {
    return <p className="emptyText">SQL Inspector requires the desktop app bridge.</p>;
  }

  const generateSql = async () => {
    const text = question.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    setClarification(null);
    setAiNote(null);
    try {
      const res = await bridge.buildMediatorSql!({
        question: text,
        symbol,
        yearLabels,
        priorSql: sql || undefined,
        followUp: sql ? text : undefined,
      });
      if (!res.ok) {
        setError(res.error || 'SQL generation failed');
        return;
      }
      if (res.action === 'clarify') {
        setClarification(res.clarification || 'Please clarify.');
        return;
      }
      if (res.sql) {
        setSql(res.sql);
        setAiNote(res.explanation || null);
      }
    } finally {
      setBusy(false);
    }
  };

  const runSql = async () => {
    if (!sql.trim()) {
      setError('Generate or paste SQL first.');
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const run = await bridge.runSqlInspector!({
        pythonPath,
        sqlPayload: {
          sql,
          symbol,
          year_labels: yearLabels,
        },
      });
      if (run.error) setError(run.error);
      if (run.sqlResult) setResult(run.sqlResult as SqlResult);
      else if (!run.ok) setError(run.error || 'SQL execution failed');
    } finally {
      setBusy(false);
    }
  };

  const askAndRun = async () => {
    const text = question.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    setClarification(null);
    setAiNote(null);
    setResult(null);
    try {
      const res = await bridge.buildMediatorSql!({
        question: text,
        symbol,
        yearLabels,
        priorSql: sql || undefined,
        followUp: sql ? text : undefined,
      });
      if (!res.ok) {
        setError(res.error || 'SQL generation failed');
        return;
      }
      if (res.action === 'clarify') {
        setClarification(res.clarification || 'Please clarify.');
        return;
      }
      const generated = res.sql || '';
      if (!generated) {
        setError('AI did not return SQL.');
        return;
      }
      setSql(generated);
      setAiNote(res.explanation || null);
      const run = await bridge.runSqlInspector!({
        pythonPath,
        sqlPayload: { sql: generated, symbol, year_labels: yearLabels },
      });
      if (run.error) setError(run.error);
      if (run.sqlResult) setResult(run.sqlResult as SqlResult);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="formSection">
      <p className="emptyText">
        Free local AI via Ollama. Ask in plain English → SQL → Python runs read-only DuckDB on your workspace.
      </p>

      <div className="presetChips" style={{ marginBottom: 10 }}>
        {SQL_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            className="presetChip"
            disabled={busy}
            onClick={() => setQuestion(preset)}
          >
            {preset}
          </button>
        ))}
      </div>

      <label style={{ display: 'block', marginBottom: 8 }}>
        Your curiosity
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          style={{ width: '100%', marginTop: 4, fontFamily: 'inherit' }}
          placeholder="e.g. Show all Daily ranges inside Weekly discount that later became Weekly BOS"
        />
      </label>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <button className="primaryBtn" type="button" disabled={busy} onClick={generateSql}>
          <Sparkles size={12} /> {busy ? 'Working…' : 'Generate SQL (Ollama)'}
        </button>
        <button className="primaryBtn" type="button" disabled={busy} onClick={runSql}>
          <Play size={12} /> Run SQL
        </button>
        <button className="primaryBtn" type="button" disabled={busy || !question.trim()} onClick={askAndRun}>
          Ask + Run
        </button>
      </div>

      {clarification && <p style={{ color: '#ffbf2f' }}>Clarify: {clarification}</p>}
      {error && <p style={{ color: '#ff4d67' }}>{error}</p>}
      {aiNote && <p className="emptyText" style={{ color: '#7b8794' }}>{aiNote}</p>}

      <label style={{ display: 'block', marginBottom: 8 }}>
        SQL (read-only SELECT)
        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          rows={5}
          style={{ ...paneStyle, width: '100%', marginTop: 4 }}
        />
      </label>

      {result && (
        <div className="humanResultCard">
          <b>
            {result.status === 'OK'
              ? `${result.row_count ?? 0} rows`
              : `Error: ${result.error || result.status}`}
          </b>
          {result.rows && result.rows.length > 0 && (
            <div style={{ overflow: 'auto', maxHeight: 280, marginTop: 8 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr>
                    {(result.columns || Object.keys(result.rows[0])).map((col) => (
                      <th key={col} style={{ padding: 4, borderBottom: '1px solid #1e2c3b', textAlign: 'left' }}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.slice(0, 50).map((row, i) => (
                    <tr key={i}>
                      {(result.columns || Object.keys(row)).map((col) => (
                        <td key={col} style={{ padding: 4, borderBottom: '1px solid #131c2c' }}>
                          {String(row[col] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.rows.length > 50 && (
                <p className="emptyText">Showing first 50 of {result.rows.length} rows.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
