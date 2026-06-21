import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CONFIRM_PROMOTE_PHRASE,
  DEFAULT_W1_2025,
  buildDryRunStamp,
  dryRunMatchesScope,
  getLocalResearchBridge,
  promoteScopeFromArgs,
  type DryRunStamp,
  type LocalResearchRunResult,
  runBatchRangePromoteLocal,
  runDetectorPerformanceLocal,
  runHistoricalRangeScanLocal,
} from './localResearchClient';

const mono: React.CSSProperties = {
  fontFamily: 'Consolas, monospace',
  fontSize: 12,
  whiteSpace: 'pre-wrap',
  lineHeight: 1.45,
};

const box: React.CSSProperties = {
  border: '1px solid #1d2738',
  borderRadius: 8,
  padding: 10,
  background: '#05070d',
  maxHeight: 180,
  overflowY: 'auto',
  ...mono,
};

type Props = {
  compact?: boolean;
  seedPolicy?: 'reviewed_truth_only';
};

export function LocalResearchControls({ compact = false, seedPolicy }: Props) {
  const bridge = getLocalResearchBridge();
  const [backendDir, setBackendDir] = useState('');
  const [databasePath, setDatabasePath] = useState('');
  const [running, setRunning] = useState<string | null>(null);
  const [last, setLast] = useState<LocalResearchRunResult | null>(null);
  const [lastDryRun, setLastDryRun] = useState<DryRunStamp | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');

  const baseArgs = useMemo(() => ({ ...DEFAULT_W1_2025 }), []);
  const promoteScope = useMemo(() => promoteScopeFromArgs(baseArgs), [baseArgs]);
  const dryRunReady = dryRunMatchesScope(lastDryRun, promoteScope, databasePath);
  const confirmPhraseOk = confirmText.trim() === CONFIRM_PROMOTE_PHRASE;

  useEffect(() => {
    bridge?.getPaths().then((res) => {
      setBackendDir(res.backendDir);
      setDatabasePath(res.databasePath);
    }).catch(() => {
      setBackendDir('paths unavailable');
      setDatabasePath('');
    });
  }, [bridge]);

  const runJob = useCallback(async (
    label: string,
    task: () => Promise<LocalResearchRunResult>,
    options?: { onDryRunSuccess?: (result: LocalResearchRunResult) => void },
  ) => {
    if (running) return;
    setRunning(label);
    if (label !== 'dry-run promote') setLast(null);
    try {
      const result = await task();
      setLast(result);
      options?.onDryRunSuccess?.(result);
    } finally {
      setRunning(null);
    }
  }, [running]);

  const onDryRunPromote = () => runJob('dry-run promote', () =>
    runBatchRangePromoteLocal({ ...baseArgs, confirm: false, json: true }),
    {
      onDryRunSuccess: (result) => {
        setLastDryRun(buildDryRunStamp(promoteScope, databasePath, result));
        setConfirmOpen(false);
        setConfirmText('');
      },
    },
  );

  const onOpenConfirmPromote = () => {
    if (!dryRunReady) return;
    setConfirmOpen(true);
    setConfirmText('');
  };

  const onConfirmPromote = () => {
    if (!dryRunReady || !confirmPhraseOk) return;
    setConfirmOpen(false);
    setConfirmText('');
    runJob('confirm promote', () =>
      runBatchRangePromoteLocal({ ...baseArgs, confirm: true, userConfirmed: true, json: true }),
    );
  };

  const onHistoricalScan = () => runJob('historical scan', () =>
    runHistoricalRangeScanLocal({ ...baseArgs, ...(seedPolicy ? { seedPolicy } : {}) }),
  );

  const onDetectorPerformance = () => runJob('detector performance', () =>
    runDetectorPerformanceLocal({
      symbol: baseArgs.symbol,
      structureLayer: baseArgs.layer,
      sourceTimeframe: baseArgs.timeframe,
      json: true,
    }),
  );

  if (!bridge) {
    return <p className="mutedSmall">Local research tools unavailable.</p>;
  }

  return (
    <div>
      {!compact && (
        <>
          <h4 style={{ margin: '0 0 6px' }}>Developer tools</h4>
          <p className="mutedSmall">Manual local script runners for troubleshooting.</p>
        </>
      )}
      {!compact && (
        <pre className="mutedSmall" style={{ ...mono, marginBottom: 8 }}>
          {`backend: ${backendDir || '—'}\nDATABASE_PATH: ${databasePath || '—'}`}
        </pre>
      )}
      {!compact && (
        <div style={{ border: '1px solid #8a5a00', borderRadius: 8, padding: 10, marginBottom: 10, background: '#1a1205' }}>
          <div className="mutedSmall">Confirm promote requires a matching dry-run on the current database.</div>
          <div className="mutedSmall">would_promote: {dryRunReady ? lastDryRun?.wouldPromote : '—'}</div>
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
        <button type="button" disabled={!!running} onClick={onDryRunPromote}>Dry-run promote</button>
        <button type="button" disabled={!!running || !dryRunReady} onClick={onOpenConfirmPromote}>Confirm promote</button>
        <button type="button" disabled={!!running} onClick={onHistoricalScan}>Historical scan</button>
        <button type="button" disabled={!!running} onClick={onDetectorPerformance}>Detector performance</button>
        {running ? <span className="mutedSmall">Running…</span> : null}
      </div>
      {confirmOpen && !compact && (
        <div style={{ border: '1px solid #b42318', borderRadius: 8, padding: 10, marginBottom: 10 }}>
          <div className="mutedSmall" style={{ marginBottom: 6 }}>Type <code>{CONFIRM_PROMOTE_PHRASE}</code></div>
          <input
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            style={{ width: '100%', maxWidth: 360, marginBottom: 8, padding: '8px 10px', borderRadius: 6, border: '1px solid #3a2a2a', background: '#05070d', color: '#f3f4f6' }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" disabled={!!running || !confirmPhraseOk} onClick={onConfirmPromote}>Run confirm</button>
            <button type="button" disabled={!!running} onClick={() => { setConfirmOpen(false); setConfirmText(''); }}>Cancel</button>
          </div>
        </div>
      )}
      {!compact && last && (
        <pre style={box}>{last.ok ? 'OK' : 'FAILED'} · exit {last.exitCode ?? '—'}</pre>
      )}
    </div>
  );
}
