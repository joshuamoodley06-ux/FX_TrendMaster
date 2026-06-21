import { useCallback, useEffect, useMemo, useState } from 'react';
import type { MappingViewContext } from '../mappingViewContext';
import {
  normalizeViewportClampSpan,
  type StoredViewportClamp,
  type ViewportClampSpan,
} from '../viewportClamping';

export type UseViewportClampingArgs = {
  storeKey: string;
  containerStartTime?: string | null;
  containerEndTime?: string | null;
  containerTimeframe?: string | null;
  viewContext?: MappingViewContext;
  chartTimeframe?: string;
};

export type UseViewportClampingResult = {
  isClamped: boolean;
  activeClamp: ViewportClampSpan | null;
  canDrillDown: boolean;
  drillDown: () => boolean;
  unlockGlobalView: () => void;
};

const STORAGE_KEY = 'fx_tm_viewport_clamp_v1';

function emptyClamp(): StoredViewportClamp {
  return {
    enabled: false,
    startTime: null,
    endTime: null,
    containerTimeframe: null,
    viewContext: null,
  };
}

function readStored(): Record<string, StoredViewportClamp> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Record<string, StoredViewportClamp> : {};
  } catch {
    return {};
  }
}

function writeStored(next: Record<string, StoredViewportClamp>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* ignore quota / private mode */
  }
}

export function useViewportClamping(args: UseViewportClampingArgs): UseViewportClampingResult {
  const [byKey, setByKey] = useState<Record<string, StoredViewportClamp>>(() => readStored());

  useEffect(() => {
    writeStored(byKey);
  }, [byKey]);

  const containerSpan = useMemo(
    () => normalizeViewportClampSpan(args.containerStartTime, args.containerEndTime),
    [args.containerStartTime, args.containerEndTime],
  );

  const canDrillDown = containerSpan != null;

  const stored = byKey[args.storeKey] ?? emptyClamp();

  const activeClamp = useMemo(() => {
    if (!stored.enabled) return null;
    const span = normalizeViewportClampSpan(stored.startTime, stored.endTime);
    if (!span) return null;
    const chartTf = String(args.chartTimeframe || '').toUpperCase();
    const containerTf = String(stored.containerTimeframe || '').toUpperCase();
    if (chartTf && containerTf && chartTf !== containerTf) return null;
    return span;
  }, [stored.enabled, stored.startTime, stored.endTime, stored.containerTimeframe, args.chartTimeframe]);

  const isClamped = activeClamp != null;

  const drillDown = useCallback((): boolean => {
    if (!containerSpan) return false;
    setByKey((prev) => ({
      ...prev,
      [args.storeKey]: {
        enabled: true,
        startTime: containerSpan.start,
        endTime: containerSpan.end,
        containerTimeframe: args.containerTimeframe ? String(args.containerTimeframe).toUpperCase() : null,
        viewContext: args.viewContext ?? null,
      },
    }));
    return true;
  }, [args.storeKey, args.containerTimeframe, args.viewContext, containerSpan]);

  const unlockGlobalView = useCallback(() => {
    setByKey((prev) => ({
      ...prev,
      [args.storeKey]: emptyClamp(),
    }));
  }, [args.storeKey]);

  return {
    isClamped,
    activeClamp,
    canDrillDown,
    drillDown,
    unlockGlobalView,
  };
}
