import { useEffect, useMemo, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import {
  isMappingEventsScopeHydrated,
  mappingEventsScopeKey,
  readMappingEventsForContainer,
  writeMappingEventsForContainer,
} from '../mappingEventsPersistence';

export type ReactiveMappingEventsArgs<TEvent = unknown> = {
  symbol: string;
  caseId?: string | null;
  eventsByTf: Record<string, TEvent[]>;
  setEventsByTf: Dispatch<SetStateAction<Record<string, TEvent[]>>>;
  eventsByTfRef: MutableRefObject<Record<string, TEvent[]>>;
};

export type ReactiveMappingEventsResult = {
  /** Stable `symbol|caseId` key — computed before hydrate/persist effects run. */
  mappingEventsScopeKey: string;
  isScopeHydrated: boolean;
};

/**
 * Reactive localStorage mirror for mapping events.
 * Scope key is memoized first; hydrate sets hydratedScopeRef to the exact key string
 * before persist writes are allowed.
 */
export function useReactiveMappingEventsPersistence<TEvent = unknown>({
  symbol,
  caseId,
  eventsByTf,
  setEventsByTf,
  eventsByTfRef,
}: ReactiveMappingEventsArgs<TEvent>): ReactiveMappingEventsResult {
  const scopeKey = useMemo(
    () => mappingEventsScopeKey(symbol, caseId ?? null),
    [symbol, caseId],
  );
  const hydratedScopeRef = useRef<string | null>(null);

  useEffect(() => {
    const stored = readMappingEventsForContainer(scopeKey) as Record<string, TEvent[]>;
    if (stored && Object.keys(stored).length) {
      setEventsByTf(stored);
      eventsByTfRef.current = stored;
    } else {
      setEventsByTf({});
      eventsByTfRef.current = {};
    }
    hydratedScopeRef.current = scopeKey;
  }, [scopeKey, setEventsByTf, eventsByTfRef]);

  useEffect(() => {
    if (!isMappingEventsScopeHydrated(hydratedScopeRef, scopeKey)) return;
    writeMappingEventsForContainer(scopeKey, eventsByTf);
  }, [scopeKey, eventsByTf]);

  return {
    mappingEventsScopeKey: scopeKey,
    isScopeHydrated: isMappingEventsScopeHydrated(hydratedScopeRef, scopeKey),
  };
}

export { mappingEventsScopeKey };
