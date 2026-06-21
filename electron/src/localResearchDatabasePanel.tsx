import React, { useCallback, useEffect, useState } from 'react';
import {
  getLocalResearchDatabaseStatus,
  openLocalResearchFolder,
  pickLocalResearchDatabaseFile,
  pullVpsCandlesLocal,
  type LocalResearchDatabaseStatus,
} from './localResearchClient';

type Props = {
  symbol: string;
  timeframe?: string;
  onStatusChange?: (status: LocalResearchDatabaseStatus | null) => void;
  compact?: boolean;
};

function shortPath(fullPath: string): string {
  if (!fullPath) return '—';
  if (fullPath.length <= 72) return fullPath;
  return `…${fullPath.slice(-68)}`;
}

export function LocalResearchDatabasePanel({
  symbol,
  timeframe = 'W1',
  onStatusChange,
  compact = false,
}: Props) {
  const [status, setStatus] = useState<LocalResearchDatabaseStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [pullError, setPullError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const next = await getLocalResearchDatabaseStatus({ symbol, timeframe });
      setStatus(next);
      onStatusChange?.(next);
    } finally {
      setBusy(false);
    }
  }, [onStatusChange, symbol, timeframe]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onPickFile = async () => {
    setBusy(true);
    try {
      const next = await pickLocalResearchDatabaseFile();
      if (!next.canceled) {
        setStatus(next);
        onStatusChange?.(next);
      }
    } finally {
      setBusy(false);
    }
  };

  const onOpenFolder = async () => {
    await openLocalResearchFolder();
  };

  const onPullFromVps = async () => {
    setBusy(true);
    setPullError(null);
    try {
      const result = await pullVpsCandlesLocal({ symbol, timeframes: 'W1,D1,H4,H1,M15,M5' });
      if (!result.ok) {
        setPullError(result.error || result.stderr?.trim() || 'VPS candle pull failed.');
        return;
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const ready = Boolean(status?.readyForWeeklyScan);
  const badge = ready ? 'Ready' : status?.exists ? 'Needs candles' : 'No database';

  return (
    <div className={`weeklyResearchDbPanel${compact ? ' is-compact' : ''}`}>
      <div className="weeklyResearchDbHeader">
        <strong>Local database</strong>
        <span className={`weeklyResearchDbBadge${ready ? ' is-ready' : ''}`}>{badge}</span>
      </div>
      <div className="weeklyResearchDbPath" title={status?.databasePath || ''}>
        {shortPath(status?.databasePath || '')}
      </div>
      {!compact && (
        <p className="mutedSmall weeklyResearchDbHint">
          Database files are not in git — they live on the VPS. Use <strong>Pull from VPS</strong> to download candles into your local research database.
        </p>
      )}
      <div className="weeklyResearchDbStats">
        <span>W1 candles: <strong>{status?.w1Candles ?? '—'}</strong></span>
        <span>Total candles: <strong>{status?.totalCandles ?? '—'}</strong></span>
        <span>Suggestions: <strong>{status?.suggestions ?? '—'}</strong></span>
      </div>
      {pullError ? (
        <p className="weeklyResearchWarnLine">{pullError}</p>
      ) : null}
      {status?.error && !ready ? (
        <p className="weeklyResearchWarnLine">{status.error}</p>
      ) : null}
      <div className="weeklyResearchActionRow">
        <button type="button" className="primaryBtn" disabled={busy} onClick={() => void onPullFromVps()}>Pull from VPS</button>
        <button type="button" disabled={busy} onClick={() => void onPickFile()}>Choose database file</button>
        <button type="button" disabled={busy} onClick={() => void onOpenFolder()}>Open research folder</button>
        <button type="button" disabled={busy} onClick={() => void refresh()}>Refresh</button>
      </div>
    </div>
  );
}
