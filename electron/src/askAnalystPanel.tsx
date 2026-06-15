// Ask Analyst — AI Stats Mediator UI (M2/M3/M4).
// Research mode: preset chips + human-readable results. Developer: raw JSON.

import React, { useEffect, useState } from 'react';
import { MessageSquare, Play, Sparkles } from 'lucide-react';
import {
  ASK_PRESETS,
  applyFollowUpToQuery,
  hydratePreset,
  pctText,
  retracementPctDisplay,
} from './analystPresets';

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

type MediatorSession = {
  question: string;
  query: Record<string, unknown>;
  result: Record<string, unknown>;
};

type Props = {
  symbol: string;
  pythonPath: string;
  yearLabels: string[];
  researchMode?: boolean;
  randomSeed?: number;
};

function isQuotaOrBillingError(message: string): boolean {
  const m = message.toLowerCase();
  return m.includes('quota') || m.includes('billing') || m.includes('insufficient') || m.includes('exceeded your current');
}

function findPresetForQuestion(text: string): typeof ASK_PRESETS[number] | undefined {
  const n = text.toLowerCase();
  if (n.includes('deep') && n.includes('daily') && n.includes('retracement')) {
    return ASK_PRESETS.find((p) => p.id === 'deep_daily_continuation');
  }
  if (n.includes('shallow') && n.includes('deep') && n.includes('reclaim')) {
    return ASK_PRESETS.find((p) => p.id === 'shallow_vs_deep_reclaim');
  }
  if (n.includes('failed') && n.includes('daily')) {
    return ASK_PRESETS.find((p) => p.id === 'failed_daily_bos');
  }
  if (n.includes('random') && n.includes('weekly')) {
    return ASK_PRESETS.find((p) => p.id === 'random_weekly');
  }
  if (n.includes('bos') && n.includes('retrace') && n.includes('bos')) {
    return ASK_PRESETS.find((p) => p.id === 'bos_up_retrace_bos_up');
  }
  return undefined;
}

function humanResultSummary(result: Record<string, unknown>): string[] {
  const lines: string[] = [];
  const metrics = (result.metrics as Record<string, unknown>) || {};
  const sample = metrics.sample_size ?? result.sample_size;
  if (sample !== undefined) lines.push(`Sample size: ${sample}`);

  if (metrics.continuation_rate !== undefined || metrics.continued_count !== undefined) {
    lines.push(`Continuation: ${pctText(metrics.continuation_rate as number)}`);
    if (metrics.failed_count !== undefined) lines.push(`Failed: ${metrics.failed_count}`);
    if (metrics.abandoned_count !== undefined) lines.push(`Abandoned: ${metrics.abandoned_count}`);
    if (metrics.unresolved_count !== undefined) lines.push(`Unresolved: ${metrics.unresolved_count}`);
  }
  if (metrics.average_retracement !== undefined) {
    lines.push(`Average retracement: ${retracementPctDisplay(metrics.average_retracement as number)}`);
  }

  const grouped = result.grouped as Array<{ group?: Record<string, unknown>; metrics?: Record<string, unknown> }>;
  if (grouped?.length) {
    grouped.forEach((row) => {
      const label = Object.values(row.group || {}).join(' / ') || 'group';
      const m = row.metrics || {};
      lines.push(`${label}: continuation ${pctText(m.continuation_rate as number)} (n=${m.sample_size})`);
    });
  }

  const sourceRows = result.source_rows as Record<string, unknown>[] | undefined;
  if (sourceRows?.length) {
    const qtype = result.question_type;
    if (qtype === 'range_list') {
      sourceRows.slice(0, 5).forEach((row) => {
        lines.push(
          `#${row.range_id} ${row.structure_layer}: H ${row.range_high_price} / L ${row.range_low_price}`
        );
      });
      if (sourceRows.length > 5) lines.push(`… and ${sourceRows.length - 5} more rows`);
    } else if (qtype === 'impulse_pair_audit') {
      sourceRows.forEach((row) => {
        lines.push(
          `Range ${row.first_range_id}: H ${row.first_range_high} L ${row.first_range_low} → BOS UP → ` +
            `${retracementPctDisplay(row.retracement_percent as number)} retrace → Range ${row.impulse_range_id}: ` +
            `H ${row.impulse_range_high} L ${row.impulse_range_low}`
        );
      });
    } else {
      lines.push(`${sourceRows.length} matching rows (open Advanced for details).`);
    }
  }

  const warnings = result.warnings as string[] | undefined;
  if (warnings?.length) lines.push(`Note: ${warnings[0]}`);

  const labelsUsed = result.year_labels_used as string[] | undefined;
  if (labelsUsed?.length) {
    lines.push(`Batches: ${labelsUsed.join(', ')}`);
  }
  const filters = result.filters_applied as Record<string, unknown> | undefined;
  if (filters?.years && Array.isArray(filters.years) && filters.years.length) {
    lines.push(`Years filter: ${(filters.years as number[]).join(', ')}`);
  }

  return lines.length ? lines : ['Query completed — open Advanced for raw JSON.'];
}

export function AskAnalystPanel({
  symbol,
  pythonPath,
  yearLabels,
  researchMode = false,
  randomSeed,
}: Props) {
  const bridge = window.analyst;
  const [question, setQuestion] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [queryJson, setQueryJson] = useState('');
  const [clarification, setClarification] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<Record<string, unknown> | null>(null);
  const [humanLines, setHumanLines] = useState<string[]>([]);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [filterNote, setFilterNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<MediatorSession | null>(null);

  const [provider, setProvider] = useState<'ollama' | 'openai'>('ollama');
  const [apiBaseUrl, setApiBaseUrl] = useState('http://127.0.0.1:11434/v1');
  const [model, setModel] = useState('llama3.2');
  const [apiKey, setApiKey] = useState('');
  const [hasApiKey, setHasApiKey] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<string | null>(null);
  const [modelList, setModelList] = useState<string[]>([]);

  useEffect(() => {
    if (!bridge?.getMediatorSettings) return;
    bridge.getMediatorSettings().then((res) => {
      if (res.ok && res.settings) {
        const p = (res.settings as { provider?: string }).provider === 'openai' ? 'openai' : 'ollama';
        setProvider(p);
        setApiBaseUrl(
          res.settings.apiBaseUrl || (p === 'ollama' ? 'http://127.0.0.1:11434/v1' : 'https://api.openai.com/v1')
        );
        setModel(res.settings.model || (p === 'ollama' ? 'llama3.2' : 'gpt-4o-mini'));
        setHasApiKey(Boolean(res.settings.hasApiKey));
      }
    });
  }, []);

  const applyProvider = (next: 'ollama' | 'openai') => {
    setProvider(next);
    if (next === 'ollama') {
      setApiBaseUrl('http://127.0.0.1:11434/v1');
      setModel((m) => m || 'llama3.2');
    } else {
      setApiBaseUrl('https://api.openai.com/v1');
      setModel((m) => m || 'gpt-4o-mini');
    }
  };

  const settingsPayload = () => ({
    settings: {
      provider,
      apiBaseUrl,
      model,
      apiKey: provider === 'ollama' ? (apiKey.trim() || 'ollama') : apiKey.trim() || undefined,
      clearApiKey: provider === 'openai' && !apiKey.trim() && hasApiKey,
    },
  });

  if (!bridge?.writeMediatorQuery || !bridge?.runQuery) {
    return (
      <p className="emptyText">Ask Analyst requires the Electron mediator bridge (desktop app).</p>
    );
  }

  const saveSettings = async () => {
    setError(null);
    setSettingsSaved(null);
    if (provider === 'openai' && !apiKey.trim() && !hasApiKey) {
      setError('Paste your OpenAI API key before saving.');
      return;
    }
    const res = await bridge.saveMediatorSettings!(settingsPayload());
    if (res.ok) {
      setHasApiKey(Boolean(res.hasApiKey));
      setApiKey('');
      if (provider === 'ollama' || res.hasApiKey) {
        setSettingsSaved(
          typeof (res as { settingsPath?: string }).settingsPath === 'string'
            ? `AI settings saved (${(res as { settingsPath?: string }).settingsPath})`
            : `AI settings saved — ${provider === 'ollama' ? 'Ollama' : 'OpenAI'} configured`
        );
      } else {
        setError('Settings file written but API key is empty. Paste sk-... and save again.');
      }
    } else {
      setError('Failed to save mediator settings');
    }
  };

  const testConnection = async () => {
    setConnectionStatus(null);
    setError(null);
    await bridge.saveMediatorSettings!(settingsPayload());
    const res = await bridge.testAiConnection!(settingsPayload().settings);
    if (res.ok) {
      setConnectionStatus(`Connected (${res.model || model})`);
    } else {
      setError(res.error || 'Connection failed — is Ollama running? Try: ollama serve');
    }
  };

  const fetchModels = async () => {
    setError(null);
    await bridge.saveMediatorSettings!(settingsPayload());
    const res = await bridge.listAiModels!(settingsPayload().settings);
    if (res.ok && res.models) {
      setModelList(res.models);
      if (res.models.length && !res.models.includes(model)) {
        setModel(res.models[0]);
      }
    } else {
      setError(res.error || 'Could not list models — start Ollama first');
    }
  };

  const switchToOllama = async () => {
    applyProvider('ollama');
    setError(null);
    await bridge.saveMediatorSettings!(settingsPayload());
    setHasApiKey(true);
    setSettingsSaved('Switched to Ollama — click Test connection, then Save.');
  };

  const runPreset = async (presetId: string) => {
    const preset = ASK_PRESETS.find((p) => p.id === presetId);
    if (!preset || yearLabels.length === 0) {
      setError('No workspace batches — run the analyst on at least one batch first.');
      return;
    }
    const seed = randomSeed ?? Date.now();
    const q = hydratePreset(preset, symbol, yearLabels, seed);
    setQuestion(preset.question);
    setQueryJson(JSON.stringify(q, null, 2));
    await runPythonWithQuery(q);
  };

  const runPythonWithQuery = async (parsed: Record<string, unknown>) => {
    setBusy('run');
    setError(null);
    setQueryResult(null);
    setHumanLines([]);
    setExplanation(null);
    try {
      const written = await bridge.writeMediatorQuery!(parsed);
      if (!written.ok || !written.path) {
        setError(written.error || 'Could not write query file');
        return;
      }
      if (written.query) {
        setQueryJson(JSON.stringify(written.query, null, 2));
      }
      const run = await bridge.runQuery!({ pythonPath, queryPath: written.path });
      if (run.error && !run.queryResult) setError(run.error);
      if (run.queryResult) {
        const result = run.queryResult as Record<string, unknown>;
        setQueryResult(result);
        setHumanLines(humanResultSummary(result));
        setSession({
          question: question.trim() || String(parsed.query_id || 'Query'),
          query: written.query || parsed,
          result,
        });
      } else if (!run.ok) {
        setError(run.error || `Python failed (exit ${run.exitCode ?? 'unknown'}). See Run Analyst log in Developer View.`);
      } else {
        setError(
          run.error ||
            `Query finished but no result was returned. Workspace: ${(run as { workspaceDir?: string }).workspaceDir || 'unknown'}`
        );
      }
    } finally {
      setBusy(null);
    }
  };

  const buildQuery = async (isFollowUp = false) => {
    const text = isFollowUp ? followUp.trim() : question.trim();
    if (!text) return;

    if (isFollowUp && session?.query) {
      const local = applyFollowUpToQuery(session.query, text, yearLabels);
      if (local) {
        setBusy('run');
        setError(null);
        setClarification(null);
        setExplanation(null);
        setFilterNote(local.note);
        setQueryJson(JSON.stringify(local.query, null, 2));
        try {
          await runPythonWithQuery(local.query);
        } finally {
          setBusy(null);
        }
        return;
      }
    }

    if (!bridge.buildMediatorQuery) {
      setError(
        'Could not parse that filter. Try a year (2019, 2020) or batch name (2019_Q3-2021_Q1), or configure Ollama in Advanced.'
      );
      return;
    }
    setBusy('build');
    setError(null);
    setClarification(null);
    setExplanation(null);
    try {
      const res = await bridge.buildMediatorQuery!({
        question: isFollowUp ? session?.question || question : text,
        symbol,
        yearLabels,
        followUp: isFollowUp ? text : undefined,
        priorQuestion: session?.question,
        priorQuery: session?.query,
        priorResult: session?.result,
      });
      if (!res.ok) {
        const errText = res.error || 'Build query failed';
        if (isQuotaOrBillingError(errText)) {
          const match = findPresetForQuestion(text);
          if (match) {
            setError(
              'OpenAI quota exceeded. Use the matching preset below (no AI), or switch to Ollama (free).'
            );
            return;
          }
          setError(
            'OpenAI quota exceeded — no billing plan. Open AI provider settings → choose Ollama → Test connection → Save.'
          );
        } else {
          setError(errText);
        }
        return;
      }
      if (res.action === 'clarify') {
        setClarification(res.clarification || 'Please clarify your question.');
        return;
      }
      if (res.query) {
        setQueryJson(JSON.stringify(res.query, null, 2));
        if (!isFollowUp) setQuestion(text);
        await runPythonWithQuery(res.query);
      }
    } finally {
      setBusy(null);
    }
  };

  const runPython = async () => {
    if (!queryJson.trim()) {
      setError('Build or paste a query JSON first.');
      return;
    }
    try {
      const parsed = JSON.parse(queryJson);
      await runPythonWithQuery(parsed);
    } catch {
      setError('Query JSON is invalid.');
    }
  };

  const explainResult = async () => {
    if (!queryResult || !bridge.explainMediatorResult) {
      setError('Run a query first (Explain needs API key).');
      return;
    }
    setBusy('explain');
    setError(null);
    try {
      const res = await bridge.explainMediatorResult!({
        question: session?.question || question,
        result: queryResult,
      });
      if (!res.ok) {
        setError(res.error || 'Explanation failed');
        return;
      }
      setExplanation(res.explanation || '');
    } finally {
      setBusy(null);
    }
  };

  const clearSession = () => {
    setSession(null);
    setFollowUp('');
    setClarification(null);
    setHumanLines([]);
    setQueryResult(null);
    setExplanation(null);
    setFilterNote(null);
  };

  return (
    <div className="formSection">
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span
          style={{
            ...chipStyle,
            borderColor: provider === 'ollama' ? '#39d98a' : '#ffbf2f',
            color: provider === 'ollama' ? '#39d98a' : '#ffbf2f',
          }}
        >
          AI: {provider === 'ollama' ? 'Ollama (local)' : 'OpenAI cloud'}
        </span>
        {provider === 'openai' && (
          <button className="primaryBtn" type="button" onClick={switchToOllama}>
            Switch to Ollama (free)
          </button>
        )}
      </div>

      <div style={{ marginBottom: 14 }}>
        <p className="emptyText" style={{ marginBottom: 8 }}>
          Quick asks — Python only, no OpenAI billing:
        </p>
        <div className="presetChips">
          {ASK_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="presetChip"
              disabled={busy !== null || yearLabels.length === 0}
              onClick={() => runPreset(preset.id)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        {!session && question.trim() && findPresetForQuestion(question) && (
          <button
            className="primaryBtn solo"
            type="button"
            style={{ marginTop: 8 }}
            disabled={busy !== null}
            onClick={() => runPreset(findPresetForQuestion(question)!.id)}
          >
            <Play size={12} /> Run matching preset (no AI)
          </button>
        )}
      </div>

      <details style={{ marginBottom: 12 }} open={provider === 'openai'}>
        <summary style={{ cursor: 'pointer', color: '#7b8794' }}>
          {researchMode ? 'Advanced — AI provider (Ollama default)' : 'AI provider settings'}
        </summary>
        <div className="scenarioForm" style={{ marginTop: 8 }}>
          <label>
            Provider
            <select
              value={provider}
              onChange={(e) => applyProvider(e.target.value as 'ollama' | 'openai')}
            >
              <option value="ollama">Ollama (local, free)</option>
              <option value="openai">OpenAI-compatible cloud</option>
            </select>
          </label>
          <label>
            API base URL
            <input value={apiBaseUrl} onChange={(e) => setApiBaseUrl(e.target.value)} />
          </label>
          <label>
            Model
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="llama3.2" />
          </label>
          {provider === 'openai' && (
            <label>
              API key {hasApiKey ? '(saved — enter to replace)' : '(required)'}
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={hasApiKey ? '••••••••' : 'sk-...'}
              />
            </label>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          <button className="primaryBtn" type="button" onClick={saveSettings}>Save AI settings</button>
          <button className="primaryBtn" type="button" onClick={testConnection}>Test connection</button>
          {provider === 'ollama' && (
            <button className="primaryBtn" type="button" onClick={fetchModels}>List Ollama models</button>
          )}
        </div>
        {provider === 'ollama' && (
          <p className="emptyText" style={{ marginTop: 8 }}>
            Install Ollama, run <code>ollama pull llama3.2</code>, then Test connection.
          </p>
        )}
        {connectionStatus && <p className="emptyText" style={{ color: '#39d98a', marginTop: 8 }}>{connectionStatus}</p>}
        {modelList.length > 0 && (
          <p className="emptyText" style={{ marginTop: 4 }}>Models: {modelList.slice(0, 8).join(', ')}{modelList.length > 8 ? '…' : ''}</p>
        )}
        {settingsSaved && <p className="emptyText" style={{ color: '#39d98a', marginTop: 8 }}>{settingsSaved}</p>}
      </details>

      {session && (
        <div style={{ marginBottom: 8 }}>
          <span style={chipStyle}>session active</span>
          <button className="primaryBtn" type="button" onClick={clearSession}>New question</button>
        </div>
      )}

      {!researchMode && !session && (
        <label style={{ display: 'block', marginBottom: 8 }}>
          Your question
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            style={{ width: '100%', marginTop: 4, fontFamily: 'inherit' }}
            placeholder="e.g. How often did deep Daily retracements continue?"
          />
        </label>
      )}

      {researchMode && !session && (
        <label style={{ display: 'block', marginBottom: 8 }}>
          Or type a custom question (needs API key)
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            style={{ width: '100%', marginTop: 4, fontFamily: 'inherit' }}
            placeholder="e.g. Show me all Daily ranges inside Weekly discount…"
          />
        </label>
      )}

      {session && (
        <label style={{ display: 'block', marginBottom: 8 }}>
          Follow-up — filter by year or batch (no AI needed)
          <textarea
            value={followUp}
            onChange={(e) => setFollowUp(e.target.value)}
            rows={2}
            style={{ width: '100%', marginTop: 4, fontFamily: 'inherit' }}
            placeholder="e.g. 2019  |  2020  |  2019_Q3-2021_Q1  |  all"
          />
          <div className="presetChips" style={{ marginTop: 8 }}>
            {['2019', '2020', '2026', 'all'].map((chip) => (
              <button
                key={chip}
                type="button"
                className="presetChip"
                disabled={busy !== null}
                onClick={() => setFollowUp(chip === 'all' ? 'all batches' : chip)}
              >
                {chip}
              </button>
            ))}
            {yearLabels.map((label) => (
              <button
                key={label}
                type="button"
                className="presetChip"
                disabled={busy !== null}
                onClick={() => setFollowUp(label)}
              >
                {label}
              </button>
            ))}
          </div>
        </label>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        {!session && question.trim() && (
          <button className="primaryBtn" type="button" onClick={() => buildQuery(false)} disabled={busy !== null}>
            <Sparkles size={12} /> {busy === 'build' ? 'Building…' : `Build + Run (${provider === 'ollama' ? 'Ollama' : 'OpenAI'})`}
          </button>
        )}
        {session && (
          <button className="primaryBtn" type="button" onClick={() => buildQuery(true)} disabled={busy !== null}>
            <Play size={12} /> {busy === 'run' ? 'Running…' : 'Apply filter & Run'}
          </button>
        )}
        {!researchMode && (
          <button className="primaryBtn" type="button" onClick={runPython} disabled={busy !== null}>
            <Play size={12} /> {busy === 'run' ? 'Running…' : 'Run Python'}
          </button>
        )}
        <button className="primaryBtn" type="button" onClick={explainResult} disabled={busy !== null || !queryResult}>
          <MessageSquare size={12} /> {busy === 'explain' ? 'Explaining…' : 'Explain (AI)'}
        </button>
      </div>

      {filterNote && (
        <p className="emptyText" style={{ color: '#7b8794', marginBottom: 8 }}>Filter: {filterNote}</p>
      )}

      {clarification && (
        <p style={{ color: '#ffbf2f', marginBottom: 8 }}>
          Clarification needed: {clarification}
        </p>
      )}
      {error && (
        <div style={{ marginBottom: 8 }}>
          <p style={{ color: '#ff4d67' }}>{error}</p>
          {isQuotaOrBillingError(error) && (
            <button className="primaryBtn" type="button" onClick={switchToOllama} style={{ marginTop: 6 }}>
              Switch to Ollama (free) and save settings
            </button>
          )}
        </div>
      )}

      {humanLines.length > 0 && (
        <div className="humanResultCard">
          <b>Result</b>
          {humanLines.map((line) => (
            <p key={line} className="insightLine">{line}</p>
          ))}
        </div>
      )}

      {explanation && (
        <div style={{ marginTop: 12 }}>
          <h4>AI explanation</h4>
          <pre style={{ ...paneStyle, fontSize: 13, maxHeight: 420, overflow: 'auto' }}>{explanation}</pre>
        </div>
      )}

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: 'pointer', color: '#7b8794' }}>
          {researchMode ? 'Developer — query JSON & raw result' : 'Query JSON (inspect / edit before Run Python)'}
        </summary>
        <textarea
          value={queryJson}
          onChange={(e) => setQueryJson(e.target.value)}
          rows={8}
          style={{ ...paneStyle, width: '100%', marginTop: 8, height: 180 }}
        />
        {queryResult && (
          <pre style={{ ...paneStyle, maxHeight: 280, overflow: 'auto', marginTop: 8 }}>
            {JSON.stringify(queryResult, null, 2)}
          </pre>
        )}
      </details>
    </div>
  );
}
