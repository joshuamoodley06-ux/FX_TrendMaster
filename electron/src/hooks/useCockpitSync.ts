import { useCallback, useState } from 'react';
import {
  fetchCockpitSnapshot,
  type CockpitSyncSnapshot,
} from '../cockpitSyncService';
import { resolveVpsBaseUrl } from '../vpsConfig';

const EMPTY_SNAPSHOT: CockpitSyncSnapshot = {
  state: null,
  activeTrade: null,
  journal: [],
  status: null,
  brain: null,
  journalSummary: null,
  structuredJournal: null,
  detailedJournal: null,
  ohlcStatus: null,
  apiOnline: null,
  error: '',
};

/** Manual VPS snapshot sync — no mount fetch, no interval (see COCKPIT_SYNC_AUTO_POLL_ENABLED). */
export function useCockpitSync(symbol: string, baseUrl = resolveVpsBaseUrl()) {
  const [snapshot, setSnapshot] = useState<CockpitSyncSnapshot>(EMPTY_SNAPSHOT);
  const [lastRefresh, setLastRefresh] = useState('');

  const refresh = useCallback(async () => {
    const next = await fetchCockpitSnapshot(symbol, baseUrl);
    setSnapshot(next);
    if (!next.error) setLastRefresh(new Date().toLocaleTimeString());
    return next;
  }, [symbol, baseUrl]);

  return { ...snapshot, lastRefresh, refresh };
}
