const STRUCTURE_LAYER_ORDER = ['MACRO', 'WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'] as const;

const STRUCTURE_LAYER_TITLE: Record<string, string> = {
  MACRO: 'Macro',
  WEEKLY: 'Weekly',
  DAILY: 'Daily',
  INTRADAY: 'Intraday',
  MICRO: 'Micro',
};

export const STRUCTURE_SCOPE_CHART_TIMEFRAMES: Record<string, readonly string[]> = {
  MACRO: ['MN1', 'W1'],
  WEEKLY: ['W1'],
  DAILY: ['D1'],
  INTRADAY: ['H4', 'H1'],
  MICRO: ['M15', 'M5'],
};

export function allowedChartTimeframesForStructureLayer(structureLayer: string): string[] {
  const layer = String(structureLayer || '').toUpperCase();
  return [...(STRUCTURE_SCOPE_CHART_TIMEFRAMES[layer] || [])];
}

export function isChartTimeframeAllowedForStructureLayer(chartTf: string, structureLayer: string): boolean {
  return allowedChartTimeframesForStructureLayer(structureLayer)
    .includes(String(chartTf || '').toUpperCase());
}

export function structureLayersForChartTimeframe(chartTf: string): string[] {
  const chart = String(chartTf || '').toUpperCase();
  return STRUCTURE_LAYER_ORDER.filter((layer) =>
    (STRUCTURE_SCOPE_CHART_TIMEFRAMES[layer] || []).includes(chart),
  ).map((layer) => structureLayerDisplayTitle(layer));
}

export function evaluateStructureScopeTimeframeBlockReason(
  layer: string,
  _sourceTf: string,
  chartTf: string,
): string | null {
  const layerKey = String(layer || '').toUpperCase();
  const chart = String(chartTf || '').toUpperCase();
  if (!layerKey || !chart) return null;
  if (isChartTimeframeAllowedForStructureLayer(chart, layerKey)) return null;

  const layerTitle = structureLayerDisplayTitle(layerKey);
  const chartOptions = allowedChartTimeframesForStructureLayer(layerKey).join(' or ');
  const layerOptions = structureLayersForChartTimeframe(chart);
  const layerCorrection = layerOptions.length
    ? layerOptions.join(' or ')
    : layerTitle;

  return `${chart} cannot be saved as ${layerTitle}. Switch layer to ${layerCorrection} or switch chart to ${chartOptions}.`;
}

export function structureLayerDisplayTitle(structureLayer: string): string {
  const key = String(structureLayer || '').toUpperCase();
  return STRUCTURE_LAYER_TITLE[key] || key || structureLayer;
}

export function structureLayerRangeConfirmLabel(structureLayer: string): string {
  return `Confirm ${structureLayerDisplayTitle(structureLayer)} Range`;
}

export function structureLayerRangeConfirmNextLabel(structureLayer: string): string {
  return `Confirm Next ${structureLayerDisplayTitle(structureLayer)} Range`;
}

export function expectedParentStructureLayerForContext(structureLayer: string): string | null {
  const idx = STRUCTURE_LAYER_ORDER.indexOf(String(structureLayer || '').toUpperCase() as typeof STRUCTURE_LAYER_ORDER[number]);
  return idx > 0 ? STRUCTURE_LAYER_ORDER[idx - 1] : null;
}

export function expectedChildStructureLayerForContext(structureLayer: string): string | null {
  const idx = STRUCTURE_LAYER_ORDER.indexOf(String(structureLayer || '').toUpperCase() as typeof STRUCTURE_LAYER_ORDER[number]);
  if (idx < 0 || idx >= STRUCTURE_LAYER_ORDER.length - 1) return null;
  return STRUCTURE_LAYER_ORDER[idx + 1];
}

export function responsibleChildConfirmLabel(childLayer: string): string {
  return `Confirm responsible ${structureLayerDisplayTitle(childLayer)} Range`;
}

export function responsibleChildBosBlockReason(parentLayer: string, childLayer: string): string {
  return `Confirm responsible ${structureLayerDisplayTitle(childLayer)} Range before ${structureLayerDisplayTitle(parentLayer)} BOS`;
}

export function hasUnsavedStructuralDraft(args: {
  rhSet: boolean;
  rlSet: boolean;
  structuralRangeDraftDirty: boolean;
  rangeDraftSynced: boolean;
  activeRangeId: string;
  anchorsMatchActiveSavedRow?: boolean;
}): boolean {
  if (args.structuralRangeDraftDirty) return true;
  if (!args.rhSet || !args.rlSet) return false;
  return args.rangeDraftSynced === false && args.anchorsMatchActiveSavedRow !== true;
}

export function evaluateRangeDraftSynced(args: {
  structuralRangeDraftDirty: boolean;
  activeRangeId: string;
  structureLayer: string;
  savedRow: {
    structure_layer?: string;
    layer?: string;
    status?: string | null;
    range_high_price?: string | number | null;
    range_high?: string | number | null;
    range_low_price?: string | number | null;
    range_low?: string | number | null;
  } | null;
  rhPrice: number | null;
  rlPrice: number | null;
  priceMatches: (a: number, b: number) => boolean;
  isBrokenStatus: (status: string | null | undefined) => boolean;
}): boolean {
  if (args.structuralRangeDraftDirty) return false;
  if (!args.savedRow || !args.activeRangeId) return false;
  const rowLayer = String(args.savedRow.structure_layer || args.savedRow.layer || '').toUpperCase();
  if (rowLayer !== String(args.structureLayer || '').toUpperCase()) return false;
  const hi = Number(args.savedRow.range_high_price ?? args.savedRow.range_high);
  const lo = Number(args.savedRow.range_low_price ?? args.savedRow.range_low);
  return args.priceMatches(hi, args.rhPrice!) && args.priceMatches(lo, args.rlPrice!);
}

export function anchorsMatchSavedRangeRow(args: {
  savedRow: {
    range_high_price?: string | number | null;
    range_high?: string | number | null;
    range_low_price?: string | number | null;
    range_low?: string | number | null;
  } | null;
  rhPrice: number | null;
  rlPrice: number | null;
  priceMatches: (a: number, b: number) => boolean;
}): boolean {
  if (!args.savedRow) return false;
  if (!Number.isFinite(args.rhPrice) || !Number.isFinite(args.rlPrice)) return false;
  const hi = Number(args.savedRow.range_high_price ?? args.savedRow.range_high);
  const lo = Number(args.savedRow.range_low_price ?? args.savedRow.range_low);
  return args.priceMatches(hi, args.rhPrice!) && args.priceMatches(lo, args.rlPrice!);
}

export type DiscardStructuralDraftPlan = {
  clearRhRl: boolean;
  clearLayerCacheKey: string | null;
  clearDraftDirty: boolean;
  clearChainDraftMode: boolean;
};

export function buildDiscardStructuralDraftPlan(args: {
  structureLayer: string;
  chainDraftMode: boolean;
  chainDraftBelongsToDraftLayer: boolean;
}): DiscardStructuralDraftPlan {
  return {
    clearRhRl: true,
    clearLayerCacheKey: String(args.structureLayer || '').toUpperCase() || null,
    clearDraftDirty: true,
    clearChainDraftMode: !!(args.chainDraftMode && args.chainDraftBelongsToDraftLayer),
  };
}

export type StructuralNavigationGuardDecision =
  | 'proceed'
  | 'prompt-save'
  | 'prompt-discard-only'
  | 'parent_context_only';

export function evaluateStructuralNavigationGuard(args: {
  hasUnsavedDraft: boolean;
  targetRangeId: string;
  activeRangeId: string;
  targetIsParentOnly: boolean;
  structuralRangeDraftDirty: boolean;
  confirmSaveEligible: boolean;
}): StructuralNavigationGuardDecision {
  if (args.targetIsParentOnly) return 'parent_context_only';
  if (!args.hasUnsavedDraft) return 'proceed';
  if (args.targetRangeId && args.activeRangeId && args.targetRangeId === args.activeRangeId) return 'proceed';
  if (args.structuralRangeDraftDirty || args.confirmSaveEligible) return 'prompt-save';
  return 'prompt-discard-only';
}

export type DraftNavConfirmAction = 'navigate-only' | 'save-required';

export function evaluateDraftNavConfirmAction(args: {
  rangeDraftSynced: boolean;
  anchorsMatchActiveSavedRow: boolean;
}): DraftNavConfirmAction {
  if (args.rangeDraftSynced || args.anchorsMatchActiveSavedRow) return 'navigate-only';
  return 'save-required';
}

export function layersForDeletedRangeIds(
  savedRanges: Array<{ range_id?: string | number; id?: string | number; structure_layer?: string; layer?: string }>,
  deletedIds: Set<string>,
): string[] {
  const layers = new Set<string>();
  for (const row of savedRanges) {
    const id = String(row.range_id || row.id || '');
    if (!id || !deletedIds.has(id)) continue;
    const layer = String(row.structure_layer || row.layer || '').toUpperCase();
    if (layer) layers.add(layer);
  }
  return Array.from(layers);
}

export function purgeStructuralAnchorsByLayer<T extends Record<string, unknown>>(
  anchors: T,
  layersToClear: string[],
): T {
  if (!layersToClear.length) return anchors;
  const next = { ...anchors } as T;
  for (const layer of layersToClear) {
    delete (next as Record<string, unknown>)[layer];
  }
  return next;
}

export function findMatchingSavedChildRange(args: {
  savedRanges: Array<{
    range_id?: string | number;
    id?: string | number;
    structure_layer?: string;
    layer?: string;
    parent_range_id?: string | number | null;
    range_high_price?: string | number | null;
    range_high?: string | number | null;
    range_low_price?: string | number | null;
    range_low?: string | number | null;
    status?: string | null;
  }>;
  childLayer: string;
  parentRangeId: string;
  rhPrice: number | null;
  rlPrice: number | null;
  priceMatches: (a: number, b: number) => boolean;
}): string | null {
  const layer = String(args.childLayer || '').toUpperCase();
  const parentId = String(args.parentRangeId || '');
  if (!layer || !parentId) return null;
  if (!Number.isFinite(args.rhPrice) || !Number.isFinite(args.rlPrice)) return null;
  const match = args.savedRanges.find((row) => {
    const rowLayer = String(row.structure_layer || row.layer || '').toUpperCase();
    if (rowLayer !== layer) return false;
    if (String(row.parent_range_id || '') !== parentId) return false;
    if (String(row.status || '').toUpperCase() === 'BROKEN') return false;
    const hi = Number(row.range_high_price ?? row.range_high);
    const lo = Number(row.range_low_price ?? row.range_low);
    return args.priceMatches(hi, args.rhPrice!) && args.priceMatches(lo, args.rlPrice!);
  });
  if (!match) return null;
  return String(match.range_id || match.id || '');
}

export function evaluateUnsavedResponsibleChildDraft(args: {
  parentLayer: string;
  parentRangeId: string;
  childLayer: string | null;
  childRhSet: boolean;
  childRlSet: boolean;
  childRhPrice: number | null;
  childRlPrice: number | null;
  activeRangeLayer?: string | null;
  mappingOnChildLayer?: boolean;
  childConfirmEligible?: boolean;
  childNextConfirmEligible?: boolean;
  chainDraftMode?: boolean;
  forParentBosOnly?: boolean;
  savedRanges: Array<{
    range_id?: string | number;
    id?: string | number;
    structure_layer?: string;
    layer?: string;
    parent_range_id?: string | number | null;
    range_high_price?: string | number | null;
    range_high?: string | number | null;
    range_low_price?: string | number | null;
    range_low?: string | number | null;
    status?: string | null;
  }>;
  priceMatches: (a: number, b: number) => boolean;
}): {
  blocked: boolean;
  blockReason: string | null;
  confirmLabel: string | null;
  childLayer: string | null;
  parentRangeId: string | null;
} {
  const parentLayer = String(args.parentLayer || '').toUpperCase();
  const parentRangeId = String(args.parentRangeId || '');
  const childLayer = args.childLayer ? String(args.childLayer).toUpperCase() : null;
  const inactive = {
    blocked: false,
    blockReason: null as string | null,
    confirmLabel: null as string | null,
    childLayer,
    parentRangeId: parentRangeId || null,
  };
  if (args.forParentBosOnly === false) return inactive;
  if (!parentRangeId || !childLayer) return inactive;
  if (args.mappingOnChildLayer) return inactive;
  if (args.childConfirmEligible || args.childNextConfirmEligible) return inactive;
  const activeRangeLayer = args.activeRangeLayer ? String(args.activeRangeLayer).toUpperCase() : null;
  if (activeRangeLayer && activeRangeLayer !== parentLayer) return inactive;
  if (!args.chainDraftMode && parentLayer !== 'WEEKLY' && parentLayer !== 'MACRO') return inactive;
  if (!args.childRhSet || !args.childRlSet) return inactive;
  const matchingSavedChildId = findMatchingSavedChildRange({
    savedRanges: args.savedRanges,
    childLayer,
    parentRangeId,
    rhPrice: args.childRhPrice,
    rlPrice: args.childRlPrice,
    priceMatches: args.priceMatches,
  });
  if (matchingSavedChildId) return inactive;
  return {
    blocked: true,
    blockReason: responsibleChildBosBlockReason(parentLayer, childLayer),
    confirmLabel: responsibleChildConfirmLabel(childLayer),
    childLayer,
    parentRangeId,
  };
}

export function hasParentStructureLayer(structureLayer: string): boolean {
  const idx = STRUCTURE_LAYER_ORDER.indexOf(String(structureLayer || '').toUpperCase() as typeof STRUCTURE_LAYER_ORDER[number]);
  return idx > 0;
}

export type StructuralRangeConfirmKind = 'child' | 'next';

export function evaluateChildStructuralRangeConfirm(args: {
  hasCase: boolean;
  structureLayer: string;
  rhSet: boolean;
  rlSet: boolean;
  parentRangeId: string;
  activeRangeId: string;
  activeRangeLayer: string | null;
  activeRangeBroken: boolean;
  rangeDraftSynced: boolean;
  structuralRangeDraftDirty: boolean;
  chainDraftMode: boolean;
  saveNextRangeEligible: boolean;
}): {
  eligible: boolean;
  kind: StructuralRangeConfirmKind;
  label: string;
  saveBlockHint: string | null;
  sameLayerChainContinuation: boolean;
  useSaveNextPath: boolean;
} {
  const layer = String(args.structureLayer || '').toUpperCase();
  const childLabel = structureLayerRangeConfirmLabel(layer);
  const nextLabel = structureLayerRangeConfirmNextLabel(layer);
  const childHint = `Confirm ${structureLayerDisplayTitle(layer)} Range before BOS`;
  const nextHint = `Confirm next ${structureLayerDisplayTitle(layer)} Range before BOS`;
  const inactive = {
    eligible: false as const,
    kind: 'child' as StructuralRangeConfirmKind,
    label: childLabel,
    saveBlockHint: null as string | null,
    sameLayerChainContinuation: false,
    useSaveNextPath: false,
  };

  if (!args.hasCase || !args.rhSet || !args.rlSet) return inactive;

  const activeLayer = args.activeRangeLayer ? String(args.activeRangeLayer).toUpperCase() : null;
  const sameLayerChainContinuation = !!(
    args.chainDraftMode
    && args.saveNextRangeEligible
    && activeLayer === layer
  );
  const sameLayerBrokenNext = !!(
    activeLayer === layer
    && args.activeRangeBroken
    && (args.chainDraftMode || args.saveNextRangeEligible)
  );

  if (sameLayerBrokenNext) {
    return {
      eligible: true,
      kind: 'next',
      label: nextLabel,
      saveBlockHint: nextHint,
      sameLayerChainContinuation: true,
      useSaveNextPath: true,
    };
  }

  if (sameLayerChainContinuation) {
    return {
      eligible: false,
      kind: 'next',
      label: nextLabel,
      saveBlockHint: null,
      sameLayerChainContinuation: true,
      useSaveNextPath: true,
    };
  }

  const hasSavedActiveForLayer = !!(
    args.activeRangeId
    && activeLayer === layer
    && !args.activeRangeBroken
    && args.rangeDraftSynced
    && !args.structuralRangeDraftDirty
  );
  if (hasSavedActiveForLayer) return inactive;

  if (activeLayer === layer && args.activeRangeBroken) return inactive;

  if (!hasParentStructureLayer(layer) || !args.parentRangeId) return inactive;

  const crossLayerChainDraft = args.chainDraftMode && !args.saveNextRangeEligible;
  const needsChildConfirm = crossLayerChainDraft
    || !args.activeRangeId
    || activeLayer !== layer
    || args.structuralRangeDraftDirty
    || !args.rangeDraftSynced;

  if (!needsChildConfirm) return inactive;

  return {
    eligible: true,
    kind: 'child',
    label: childLabel,
    saveBlockHint: childHint,
    sameLayerChainContinuation: false,
    useSaveNextPath: false,
  };
}

export function shouldSuppressDraftRangeOverlay(args: {
  hasHigh: boolean;
  hasLow: boolean;
  structuralRangeDraftDirty: boolean;
  activeRangeLayer: string | null;
  activeRangeBroken: boolean;
  structureLayer: string;
  draftHigh: number;
  draftLow: number;
  savedHigh: number;
  savedLow: number;
  priceMatches: (a: number, b: number) => boolean;
}): boolean {
  if (!args.hasHigh || !args.hasLow) return true;
  if (args.structuralRangeDraftDirty) return false;
  if (!args.activeRangeLayer || args.activeRangeLayer !== String(args.structureLayer).toUpperCase()) return false;
  if (args.activeRangeBroken) return false;
  return args.priceMatches(args.savedHigh, args.draftHigh) && args.priceMatches(args.savedLow, args.draftLow);
}

export type StructuralParentRangeRow = {
  range_id?: string | number;
  id?: string | number;
  structure_layer?: string;
  layer?: string;
  range_scope?: string | null;
  parent_range_id?: string | number | null;
  status?: string | null;
  active_from_time?: string | null;
  range_start_time?: string | null;
  range_end_time?: string | null;
  inactive_from_time?: string | null;
  range_high_time?: string | null;
  range_low_time?: string | null;
};

export function parseStructuralTimeMs(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const raw = String(value).trim();
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : null;
}

export function normalizeStructureLayerId(value: unknown): string | null {
  const raw = String(value || '').toUpperCase();
  const aliases: Record<string, string> = {
    MN1: 'MACRO',
    MACRO: 'MACRO',
    W1: 'WEEKLY',
    WEEKLY: 'WEEKLY',
    D1: 'DAILY',
    DAILY: 'DAILY',
    H4: 'INTRADAY',
    H1: 'INTRADAY',
    INTRADAY: 'INTRADAY',
    M15: 'MICRO',
    M5: 'MICRO',
    MICRO: 'MICRO',
  };
  const layer = aliases[raw] || raw;
  return STRUCTURE_LAYER_ORDER.includes(layer as typeof STRUCTURE_LAYER_ORDER[number]) ? layer : null;
}

export function isSavedRangeMajor(row: StructuralParentRangeRow): boolean {
  return String(row?.range_scope || 'MAJOR').toUpperCase() !== 'MINOR';
}

export function findSavedRangeRowById(
  savedRanges: StructuralParentRangeRow[],
  rangeId: string,
): StructuralParentRangeRow | null {
  if (!rangeId) return null;
  return savedRanges.find((row) => String(row.range_id || row.id) === String(rangeId)) || null;
}

export function expectedParentLayerForChildSave(structureLayer: string, rangeScope: string): string | null {
  const layer = String(structureLayer || '').toUpperCase();
  const scope = String(rangeScope || 'MAJOR').toUpperCase();
  if (scope === 'MINOR') return layer;
  return expectedParentStructureLayerForContext(layer);
}

export function isValidCommitParentRow(
  row: StructuralParentRangeRow | null | undefined,
  structureLayer: string,
  rangeScope: string,
): boolean {
  if (!row) return false;
  const neededParent = expectedParentLayerForChildSave(structureLayer, rangeScope);
  if (!neededParent) return false;
  const rowLayer = normalizeStructureLayerId(row.structure_layer || row.layer);
  if (!rowLayer) return false;
  return rowLayer === neededParent && isSavedRangeMajor(row);
}

export type StructuralCommitParentSource = 'lock' | 'selected' | 'auto' | 'none';

export function resolveStructuralCommitParentId(args: {
  structureLayer: string;
  rangeScope: string;
  lockedChildMappingParentId: string;
  selectedParentRangeId: string;
  autoResolvedParentId: string | null;
  savedRanges: StructuralParentRangeRow[];
}): { parentId: string | null; source: StructuralCommitParentSource } {
  const lockId = String(args.lockedChildMappingParentId || '');
  if (lockId) {
    return { parentId: lockId, source: 'lock' };
  }

  const selectedId = String(args.selectedParentRangeId || '');
  if (selectedId) {
    const selectedRow = findSavedRangeRowById(args.savedRanges, selectedId);
    if (isValidCommitParentRow(selectedRow, args.structureLayer, args.rangeScope)) {
      return { parentId: selectedId, source: 'selected' };
    }
  }

  const autoId = args.autoResolvedParentId ? String(args.autoResolvedParentId) : '';
  if (autoId) {
    return { parentId: autoId, source: 'auto' };
  }

  return { parentId: null, source: 'none' };
}

export function childDraftAnchorTimesMs(childSpan?: {
  range_high_time?: string | null;
  range_low_time?: string | null;
  active_from_time?: string | null;
  range_start_time?: string | null;
  range_end_time?: string | null;
}): number[] {
  const values = [
    childSpan?.range_high_time,
    childSpan?.range_low_time,
    childSpan?.active_from_time,
    childSpan?.range_start_time,
    childSpan?.range_end_time,
  ];
  return values.map(parseStructuralTimeMs).filter((x): x is number => x !== null);
}

export function parentLifecycleStartMs(parent: StructuralParentRangeRow): number | null {
  const values = [parent?.active_from_time, parent?.range_start_time]
    .map(parseStructuralTimeMs)
    .filter((x): x is number => x !== null);
  return values.length ? Math.min(...values) : null;
}

function isDateOnlyOrMidnightBoundary(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  const raw = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return true;
  const ms = parseStructuralTimeMs(value);
  if (ms === null) return false;
  const d = new Date(ms);
  return d.getUTCHours() === 0
    && d.getUTCMinutes() === 0
    && d.getUTCSeconds() === 0
    && d.getUTCMilliseconds() === 0;
}

export function parentLifecycleEndMs(parent: StructuralParentRangeRow): number | null {
  const status = String(parent?.status || 'ACTIVE').toUpperCase();
  if (!['BROKEN', 'ABANDONED', 'ARCHIVED'].includes(status)) return null;
  const endMs = parseStructuralTimeMs(parent?.inactive_from_time);
  if (endMs === null) return null;
  const parentLayer = normalizeStructureLayerId(parent?.structure_layer || parent?.layer);
  if (parentLayer === 'DAILY' && isDateOnlyOrMidnightBoundary(parent?.inactive_from_time)) {
    const day = new Date(endMs);
    return Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate() + 1) - 1;
  }
  return endMs;
}

export function parentContainsChildByLifecycle(
  parent: StructuralParentRangeRow,
  childTimesMs: number[],
): boolean {
  if (!childTimesMs.length) return true;
  const pStart = parentLifecycleStartMs(parent);
  const pEnd = parentLifecycleEndMs(parent);
  const cMin = Math.min(...childTimesMs);
  const cMax = Math.max(...childTimesMs);
  if (pStart !== null && cMin < pStart) return false;
  if (pEnd !== null && cMax > pEnd) return false;
  return true;
}

export function shouldSuppressAutoParentRewrite(lockedChildMappingParentId: string): boolean {
  return !!String(lockedChildMappingParentId || '');
}

export function shouldRetainChildMappingLock(args: {
  lockedChildMappingParentId: string;
  structureLayer: string;
  savedRanges: StructuralParentRangeRow[];
}): boolean {
  const lockId = String(args.lockedChildMappingParentId || '');
  if (!lockId) return false;
  const neededParent = expectedParentLayerForChildSave(args.structureLayer, 'MAJOR');
  if (!neededParent) return false;
  const lockRow = findSavedRangeRowById(args.savedRanges, lockId);
  const lockLayer = normalizeStructureLayerId(lockRow?.structure_layer || lockRow?.layer);
  return lockLayer === neededParent;
}

export function evaluateChildMappingParentBlockReason(args: {
  structureLayer: string;
  rangeScope: string;
  lockedChildMappingParentId: string;
  childSpan: {
    range_high_time?: string | null;
    range_low_time?: string | null;
    active_from_time?: string | null;
    range_start_time?: string | null;
    range_end_time?: string | null;
  };
  savedRanges: StructuralParentRangeRow[];
  resolvedParentId: string | null;
  activeRangeParentId?: string | null;
  allowOrphanOverride?: boolean;
}): string | null {
  const layer = String(args.structureLayer || '').toUpperCase();
  const parentLayer = expectedParentLayerForChildSave(layer, args.rangeScope);
  if (!parentLayer) return null;

  const lockId = String(args.lockedChildMappingParentId || '');
  const childTimesMs = childDraftAnchorTimesMs(args.childSpan);
  const childTitle = structureLayerDisplayTitle(layer);

  if (lockId && args.activeRangeParentId && String(args.activeRangeParentId) !== lockId) {
    const parentTitle = structureLayerDisplayTitle(parentLayer);
    return `Active range parent #${args.activeRangeParentId} does not match locked ${parentTitle} #${lockId}.`;
  }

  if (lockId && args.resolvedParentId && String(args.resolvedParentId) !== lockId) {
    const parentTitle = structureLayerDisplayTitle(parentLayer);
    return `${childTitle} save must use locked parent #${lockId}. Latest ${parentTitle} substitution blocked.`;
  }

  if (lockId && !args.resolvedParentId) {
    return `Locked parent #${lockId} required for ${childTitle} save.`;
  }

  const parentIdForContainment = lockId || (args.resolvedParentId ? String(args.resolvedParentId) : '');
  if (parentIdForContainment && childTimesMs.length) {
    const parentRow = findSavedRangeRowById(args.savedRanges, parentIdForContainment);
    if (parentRow && !parentContainsChildByLifecycle(parentRow, childTimesMs)) {
      const parentTitle = structureLayerDisplayTitle(
        normalizeStructureLayerId(parentRow.structure_layer || parentRow.layer) || parentLayer,
      );
      return `${childTitle} window is not inside ${parentTitle} #${parentIdForContainment}. Select the correct ${parentTitle} or move RH/RL.`;
    }
  }

  if (!args.allowOrphanOverride && !lockId && childTimesMs.length && !args.resolvedParentId) {
    return `${childTitle} save needs a ${structureLayerDisplayTitle(parentLayer)} parent or explicit orphan override.`;
  }

  return null;
}

export function allowsBoundaryCorrectionForParentBlock(reason: string | null | undefined): boolean {
  return !!reason && reason.includes('move RH/RL');
}

export function evaluateStructuralBosBlockReason(args: {
  hasCase: boolean;
  structureLayer: string;
  chartTimeframe: string;
  resolvedRangeId: string;
  activeRangeBroken: boolean;
  needsRangeConfirm: boolean;
  responsibleChildDraftBlocked?: boolean;
  responsibleChildDraftReason?: string | null;
  childMappingParentBlockReason?: string | null;
  candleFeedReady: boolean;
  admittedMappingCandle: boolean;
  candleFeedMessage?: string | null;
}): string | null {
  if (!args.hasCase) return 'Create or select a mapping case first (Case tab).';
  if (args.childMappingParentBlockReason) return args.childMappingParentBlockReason;
  if (args.responsibleChildDraftBlocked && args.responsibleChildDraftReason) {
    return args.responsibleChildDraftReason;
  }
  const layerTitle = structureLayerDisplayTitle(args.structureLayer);
  const tf = String(args.chartTimeframe || '').toUpperCase();
  if (!args.resolvedRangeId || args.activeRangeBroken || args.needsRangeConfirm) {
    return `Confirm next ${layerTitle} Range before BOS`;
  }
  if (!args.candleFeedReady) return args.candleFeedMessage || 'Candle feed mismatch — marking blocked';
  if (!args.admittedMappingCandle) return `Re-click visible ${tf} candle for BOS`;
  return null;
}

export function hasMappingSkeletonContext(args: {
  hasCase: boolean;
  activeStructuralRangeId: string;
  selectedParentRangeId: string;
  guidedCursorActive: boolean;
  childMappingSessionActive: boolean;
}): boolean {
  if (!args.hasCase) return false;
  return !!(
    args.activeStructuralRangeId
    || args.selectedParentRangeId
    || args.guidedCursorActive
    || args.childMappingSessionActive
  );
}

export function buildSkeletonMappingStatusLine(args: {
  selectedTimeLabel: string | null;
  timeframe: string;
  structureLayer: string;
  activeRangeId: string;
  parentRangeId: string;
  rhSet: boolean;
  rlSet: boolean;
  chainDraftMode: boolean;
  childRangeConfirmPending?: boolean;
  childRangeConfirmNextPending?: boolean;
  rangeSynced: boolean;
  lastMessage: string;
  structuralSaving: boolean;
}): string {
  if (args.structuralSaving) return 'Syncing range to backend…';
  if (args.selectedTimeLabel) {
    const keys = 'H = RH · L = RL · ↑/↓ = BOS · ←/→ = replay · U = undo · Esc = clear';
    return `Selected: ${args.selectedTimeLabel} ${args.timeframe} · ${keys}`;
  }
  if (args.childRangeConfirmNextPending && args.rhSet && args.rlSet) {
    return `${args.structureLayer} RH/RL set · ${structureLayerRangeConfirmNextLabel(args.structureLayer)} before BOS`;
  }
  if (args.childRangeConfirmPending && args.rhSet && args.rlSet) {
    return `${args.structureLayer} RH/RL set · ${structureLayerRangeConfirmLabel(args.structureLayer)} before BOS`;
  }
  if (args.chainDraftMode && args.rhSet && args.rlSet) {
    return `${args.structureLayer} next range RH/RL set · syncing chain…`;
  }
  if (args.activeRangeId && args.rhSet && args.rlSet && args.rangeSynced) {
    const parent = args.parentRangeId ? ` · parent #${args.parentRangeId}` : '';
    return `${args.structureLayer} #${args.activeRangeId}${parent} · RH/RL set · range synced`;
  }
  if (args.activeRangeId && args.rhSet && args.rlSet) {
    return `${args.structureLayer} #${args.activeRangeId} · RH/RL set · syncing…`;
  }
  if (!args.activeRangeId && !args.parentRangeId) {
    return 'Select campaign or hierarchy context first · then click a candle';
  }
  return args.lastMessage || 'Click a candle · H/L for RH/RL · ↑/↓ for BOS';
}
