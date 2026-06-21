/** Purge structural mapping UI when Sync Architect blocks stale cache rehydration.
 *  Does NOT touch nav chrome (navOverlayPanelOpen, inspector tab, ribbon collapse) —
 *  layout chrome must stay independent of the candle-load guard.
 */

export const STALE_CACHE_BLOCKED = 'STALE_CACHE_BLOCKED';

export type StructuralAnchorDraft = {
  price?: string;
  time?: string;
  candle?: unknown | null;
};

export type ClearAllUIAnchorsHandlers = {
  setActiveStructuralRangeId: (value: string) => void;
  setSelectedParentRangeId: (value: string) => void;
  setStructuralRanges: (rows: unknown[]) => void;
  setSavedStructuralRanges: (rows: unknown[]) => void;
  setStructuralAnchorsByLayer: (value: Record<string, unknown>) => void;
  setSessionEventIds: (value: Set<string>) => void;
  setEventsByTf: (value: Record<string, unknown[]>) => void;
  clearEventsByTfRef: () => void;
  setRangeByTf: (value: Record<string, { high?: string; low?: string }>) => void;
  setRangeWindowByTf: (value: Record<string, { start?: string; end?: string }>) => void;
  setMeasurementRangeByTf: (value: Record<string, unknown>) => void;
  setRhAnchor: (value: StructuralAnchorDraft) => void;
  setRlAnchor: (value: StructuralAnchorDraft) => void;
  setStructuralRangeDraftDirty: (value: boolean) => void;
  clearMappingEventsBucket?: (scopeKey: string) => void;
  mappingEventsScopeKey?: string;
};

/** localStorage keys for nav chrome — excluded from stale-cache structural purge. */
export const NAV_CHROME_STORAGE_KEYS = [
  'fx_tm_inspector_tab_v1',
  'fx_tm_top_ribbon_collapsed_v087_24',
] as const;

export type NavChromeHandlerKeys =
  | 'setNavOverlayPanelOpen'
  | 'setChartFullscreen'
  | 'setRightDeckTab';

type AssertNavChromeExcluded = NavChromeHandlerKeys extends keyof ClearAllUIAnchorsHandlers ? never : true;
export const navChromeExcludedFromClearHandlers: AssertNavChromeExcluded = true;

export function clearAllUIAnchors(handlers: ClearAllUIAnchorsHandlers): void {
  handlers.setActiveStructuralRangeId('');
  handlers.setSelectedParentRangeId('');
  handlers.setStructuralRanges([]);
  handlers.setSavedStructuralRanges([]);
  handlers.setStructuralAnchorsByLayer({});
  handlers.setSessionEventIds(new Set());
  handlers.clearEventsByTfRef();
  handlers.setEventsByTf({});
  if (handlers.mappingEventsScopeKey && handlers.clearMappingEventsBucket) {
    handlers.clearMappingEventsBucket(handlers.mappingEventsScopeKey);
  }
  handlers.setRangeByTf({});
  handlers.setRangeWindowByTf({});
  handlers.setMeasurementRangeByTf({});
  handlers.setRhAnchor({ price: '', time: '', candle: null });
  handlers.setRlAnchor({ price: '', time: '', candle: null });
  handlers.setStructuralRangeDraftDirty(false);
}
