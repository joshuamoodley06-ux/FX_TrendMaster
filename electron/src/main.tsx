import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { createRoot } from 'react-dom/client';
import { AlertTriangle, BookOpen, CheckCircle2, ChevronLeft, ChevronRight, CircleDot, Database, FileText, RefreshCw, Save, Settings, Target } from 'lucide-react';
import { buildRawPayloadJson, clearRawCases, createRawCase, exportRawCaseEvents, groupRawDisplayEventsByTimeframe, listRawCases, saveRawEvent } from './rawMapping';
import { inspectorCommit, inspectorCommitOrThrow, type InspectorCommitSource } from './inspectorCommit';
import { AnalystPage } from './analystPage';
import {
  buildMasterCaseName,
  computeMappingGaps,
  filterRangesForExplorerMode,
  type ExplorerMappingMode,
  type MappingGap,
} from './mappingWorkflow';
import {
  CHART_DRAWING_COLORS,
  type ChartDrawTool,
  type ChartDrawing,
  loadChartDrawings,
  loadReplayCursorForKey,
  loadStructuralReplayCursorForScope,
  newDrawingId,
  normalizeHLineDrawing,
  normalizeVLineDrawing,
  saveChartDrawings,
  saveReplayCursorForKey,
  saveStructuralReplayCursorForScope,
} from './chartDrawings';
import {
  type ChartTradeIdea,
  type ChartTradeIdeaDraft,
  type TradeIdeaPickKind,
  TRADE_IDEA_COLORS,
  buildTradeIdeaFromDraft,
  downloadTradeIdeasJson,
  emptyTradeIdeaDraft,
  loadChartTradeIdeas,
  overlaySpecFromDraft,
  overlaySpecFromIdea,
  saveChartTradeIdeas,
  tradeIdeasStorageKey,
  tradeIdeaEndDate,
  type TradeIdeaOverlaySpec,
} from './chartTradeIdeas';
import {
  clearAllUIAnchors,
  clearMappingEventsForContainer,
  resolveActiveCaseDisplayId,
  STALE_CACHE_BLOCKED,
} from './syncService';
import { MapTradeIdeaPanel } from './mapTradeIdeaPanel';
import { InspectorPanel, type InspectorTabId, normalizeInspectorTabId } from './inspectorPanel';
import { NavRail, MAP_STUDIO_SHELL_CLASS, MAP_STUDIO_SHELL_GRID, MAP_STUDIO_SHELL_STYLE } from './appShell';
import { useLocalStorage } from './useLocalStorage';
import {
  buildCandleSelectionHint,
  buildRangeSelectionHint,
  routeInspectorForCandleSelection,
  routeInspectorForRangeSelection,
  type InspectorContextHint,
} from './inspectorContext';
import {
  inspectorFormCacheKey,
  readInspectorFormCache,
  writeInspectorFormCache,
} from './inspectorFormCache';
import { draftRangeLineStyle, savedRangeLineStyle } from './rangeLineStyle';
import { CockpitOverviewProvider } from './cockpitOverviewContext';
import { InspectorOverviewDashboard } from './inspectorOverviewDashboard';
import { ReviewCandidatePanel } from './reviewCandidatePanel';
import type { RangeAuditSample, RangeAuditViewTarget } from './reviewCandidateClient';
import { auditSampleToViewTarget } from './reviewCandidateClient';
import { ChildMappingPanel } from './childMappingPanel';
import {
  openChildMappingSetup,
  restoreChildMappingSession,
  type ChildMappingSession,
} from './childMappingWorkflow';
import {
  advanceGuidedCursorAfterChildSave,
  buildGuidedCursorFromParent,
  guidedCursorFromSessionFields,
  guidedCursorResearchWindow,
  guidedCursorToSessionFields,
  markGuidedParentComplete,
  skipGuidedCursorGap,
  type GuidedMappingCursor,
} from './guidedMappingCursor';
import { getLocalResearchBridge } from './localResearchClient';
import {
  bosNextRangePromptKey,
  evaluateBosNextRangePrompt,
  type BosNextRangePromptResult,
} from './autoBosNextRangePrompt';
import {
  applyReplaySeedPlan,
  buildStructuralReplayScopeKey,
  replayPlayForwardStatusMessage,
  replayRestoreStatusMessage,
  resolveStructuralReplayRestore,
  resolveStructuralReplaySeedPlan,
  type StructuralReplayScope,
} from './replayCursorSeed';
import { useMappingDraft } from './hooks/useMappingDraft';
import {
  activeStructuralRangeStatusFields,
  isStructuralRangeBrokenStatusValue,
  structuralRangeStatusFieldsForSave,
} from './structuralRangeLifecycle';
import { useReactiveMappingEventsPersistence } from './hooks/useReactiveMappingEventsPersistence';
import { useFingerErrorStack } from './fingerErrorStack';
import { createDebouncedResizeHandler } from './chartResizeDebounce';
import { createLayoutResizeGuard } from './chartLayoutResizeGuard';
import { useViewportClamping } from './hooks/useViewportClamping';
import { normalizeChartTf } from './mappingDraftBoundary';
import { MappingCampaignPanel } from './mappingCampaignPanel';
import { computeCampaignStatus } from './mappingCampaignManager';
import {
  buildSkeletonMappingStatusLine,
  hasMappingSkeletonContext,
} from './mapStudioMappingContext';
import {
  isTypingInEditableField,
  resolveMapStudioKeyAction,
} from './mapStudioKeyboard';
import { MappingViewContextSwitcher } from './mappingViewContextSwitcher';
import {
  mappingViewContextAvailable,
  resolveChildChartTimeframe,
  resolveMappingViewChartTimeframe,
  resolveParentChartTimeframe,
  type MappingViewContext,
} from './mappingViewContext';
import {
  expandRangeSpanX,
  rangeWindowFieldsFromSavedRange,
  resolveCandleWindowTargetRange,
  resolveRangeChartTimeframe,
} from './hierarchyRangeNavigation';
import {
  addIsoDays,
  extendStructuralDataLoadWindow,
  formatCandleLoadDiagnostic,
  filterCandlesToLoadWindow,
  isCurrentCandleLoadRequest,
  loadWindowKey,
  maxBarsForStructuralWindow,
  mergeCandleSeriesByTime,
  resolveStructuralCandleLoadWindow,
  resolveStructuralContextAndReplayWindows,
  resolveStructuralDataLoadWindow,
  resolveTimeframeSwitchDataLoadWindow,
  shouldApplyParsedCandles,
  shouldBlockQuietFullHistoryReload,
  shouldClearCandlesOnLoadStart,
  shouldPreserveTradingViewMappingCandleUniverse,
  shouldUseWindowedCandleLoad,
  structuralReplayChunkDays,
  trimStructuralCandlesToHorizon,
  trimStructuralCandlesToMaxBars,
  type CandleLoadContext,
  type CandleLoadDiagnostics,
  type CandleLoadWindow,
} from './candleLoadPolicy';
import {
  annotateOverlayFocusTiers,
  filterFocusModeOverlays,
  focusYExtentsWithParent,
  overlayLineStyleWithFocus,
  shouldUseCandleOnlyYScale,
  type FocusOverlayTier,
} from './chartFocusMode';
import {
  buildTradingViewMemoryFitRequest,
  chartMemoryKey,
  globalReplayCursorKey,
  isCrossTfH1Entry,
  legacyChartMemoryKey,
  memoryFitWindowFromChartMemory,
  minimumRoutineVisibleBarsForTimeframe,
  parseRoutineTfMemoryReason,
  purgePoisonedH1MemoryKeys,
  readChartMemoryFromStore,
  resolveNearestCandle,
  resolveRoutineTfSwitchCameraPlan,
  routineTfMemoryReason,
  sanitizeRoutineMemoryCameraAfterLoad,
  shouldPersistChartMemory,
  shouldPersistH1ChartMemory,
  snapshotMemoryFromVisibleDomain,
  type MemoryFitWindow,
  type RoutineAnchorSource,
} from './chartMemory';
import {
  activateRoutineFitLock,
  activatePostRoutineSettle,
  autoCandleBodyWidthPx,
  CHART_FUTURE_PAD_RATIO,
  CHART_LATEST_ANCHOR_RATIO,
  clearPostRoutineSettle,
  clearRoutineFitLock,
  type CameraViewOwner,
  inferViewOwnerFromCameraReason,
  isExplicitCameraNavigationReason,
  isPostRoutineSettleActive,
  isRoutineTfMemoryReason,
  isStructuralNavigationReason,
  logCameraUpdate,
  readablePadBarsForTimeframe,
  shouldBlockAutomaticCameraRefit,
  shouldBlockFullscreenLayoutRefit,
  shouldBlockTradingViewAutoFit,
  targetVisibleBarsForTimeframe,
  tradingViewCameraBridge,
  type TradingViewFitAppliedDetail,
} from './chartViewportPolicy';
import {
  buildCandleFeedStatusLine,
  buildLoadedCandleContext,
  evaluateCandleFeedGuard,
  rehydrateLoadedCandleContextForVisibleFeed,
  type ActiveMappingFeedSnapshot,
  type CandleFeedGuardResult,
  type LoadedCandleContext,
  type StructureLayerId,
} from './candleFeedIdentity';
import {
  formatCandleLoadWindowLabel,
  formatLoadedCandleContextSummary,
  logCandleLoadRequest,
  logCandleLoadResponse,
} from './candleLoadDebug';
import {
  clampChartTransformToTimeBounds,
  intersectClampSpanWithCandles,
  resolveChartPanBounds,
} from './viewportClamping';
import { writeAutoResumeSession } from './autoResumeStorage';
import { useAutoResume } from './hooks/useAutoResume';
import {
  deriveLayerActiveIdsFromRanges,
  executeMappingSessionResume,
  findSavedRangeById,
  isMappingSessionOrchestrating,
  readMappingSessionForSymbol,
  useMappingSessionPersistence,
} from './hooks/useMappingSessionPersistence';
import { MappingSessionResumeModal } from './mappingSessionResumeModal';
import { ghostRangeUiClearMessage } from './rangeRehydrationService';
import {
  persistRemoteCandlesToCache,
  readLocalCacheBarCount,
  syncSymbolAllTimeframesToCache,
} from './candleBootService';
import {
  DEFAULT_RESYNC_INTERVAL_MS,
  getSyncService,
  initBackgroundCandleSync,
} from './syncService';
import { type AppPage } from './appNavigation';
import { NavSidebar, useAppPageNavigation } from './navSidebar';
import { useCockpitSync } from './hooks/useCockpitSync';
import { resolveVpsBaseUrl } from './vpsConfig';
import { createChartRenderGate } from './chartRenderGate';
import {
  CHART_RENDERER_STORAGE_KEY,
  DEFAULT_CHART_RENDERER,
  DEFAULT_TRADINGVIEW_OVERLAY_MODE,
  DEFAULT_TRADINGVIEW_SELECTED_CANDLE_MODE,
  DEFAULT_TRADINGVIEW_MAPPING_INPUT,
  isTradingViewMappingInputEnabled,
  normalizeChartRendererMode,
  normalizeTradingViewOverlayMode,
  normalizeTradingViewSelectedCandleMode,
  normalizeTradingViewMappingInputMode,
  TRADINGVIEW_MAPPING_INPUT_STORAGE_KEY,
  TRADINGVIEW_SELECTED_CANDLE_STORAGE_KEY,
  TRADINGVIEW_OVERLAYS_STORAGE_KEY,
} from './chartRendererConfig';
import {
  adaptFitRequestForTradingView,
  adaptOverlaysForTradingView,
} from './tradingView/overlayAdapter';
import { applyChartModeWindow, fxtmTimeToTradingViewTime, isReplaySelectableCandle, usesTradingViewTailSliceForTimeframe } from './tradingView/candleAdapter';
import { LiveViewPanel } from './tradingView/LiveViewPanel';
import { EventBrowserPanel } from './eventBrowserPanel';
import {
  admitTradingViewSelection,
  clearTvMappingSelection,
  commitTvMappingSelection,
  resolveMappingInputCandle,
  resolveVisualTradingViewSelectedCandle,
  type MappingInputCandle,
} from './tradingView/selectedCandleBridge';
import type { ChartRendererMode, TradingViewChartMode, TradingViewFitRequest, TradingViewOverlayMode, TradingViewSelectedCandle, TradingViewSelectedCandleMode } from './tradingView/types';
import {
  buildLocalLibraryStatusLine,
  candlesChanged,
  formatMissingCandleMessage,
  loadChartCandlesLocalFirst,
  mergeParsedCandleRowsForChart,
  runBackgroundDeltaSync,
  type LocalLibraryDebugStatus,
} from './localCandleLibrary';
import {
  isStaleRehydrationLoad,
  purgeGhostMappingLocalStorage,
} from './mapStudioStaleRehydration';
import './styles.css';

const BASE_URL = resolveVpsBaseUrl();
const DEBUG_CAMERA = false;
const SYMBOLS = ['XAUUSD', 'US500.cash'];
const ZONES = ['Ext L', 'DD', 'D', 'Fair', 'P', 'DP', 'Ext H'];
const LAYERS = ['weekly', 'daily', 'intraday'] as const;
type LayerKey = typeof LAYERS[number];
type Page = AppPage;
type CameraIntent = 'LATEST' | 'FIT_ALL' | 'CASE' | 'REPLAY' | 'RANGE' | 'FIT_STRUCTURAL_RANGE' | 'RESTORE_LOCKED' | 'PRESERVE_OR_NEAREST_TIME' | 'HORIZONTAL_STRETCH' | 'VERTICAL_STRETCH' | 'NONE';
type StructuralFitWindow = { start: string; end: string; low: number; high: number; padRatio?: number };
type CameraCommand = { intent: CameraIntent; token: number; targetTime?: string | null; reason?: string; scaleFactor?: number; fitWindow?: StructuralFitWindow | null; priceDomain?: { low: number; high: number } | null };
type VisibleCameraDomain = { start:string; end:string; priceLow:number; priceHigh:number; visibleBars?:number; barSpacingPx?:number };

type Layer = {
  layer: string;
  auto_location?: string;
  location?: string;
  position_percent?: number;
  trajectory?: string;
  objective?: string;
  discount_mitigation?: string;
  premium_mitigation?: string;
  external_low_mitigation?: string;
  external_high_mitigation?: string;
};

type TradeIdea = {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  setupType: string;
  status: string;
  weekly: string;
  daily: string;
  objective: string;
  waitingFor: string;
  invalidationPrice: string;
  riskMode: string;
  notes: string;
  createdAt: string;
};

type AnchorStatus = 'INTACT' | 'BROKEN' | 'BROKEN_RECLAIMED' | 'FAILED_RECLAIM' | 'TARGETED' | 'MITIGATED' | 'FAILED' | 'CONFIRMED';
type GraphPoint = { id: string; label: string; anchorKey?: string; zone: string; x: number; sequenceColumn?: number; price?: string; live?: boolean; status?: AnchorStatus | string; role?: string };
type MitigationLevels = Record<'discount' | 'fair_price' | 'premium', Record<'m1' | 'm2' | 'm3', { price: string; status: string; role?: string }>>;

type MapMeta = {
  profile?: string;
  deliveryState?: string;
  reactionState?: string;
  continuationState?: string;
  phaseState?: string;
  entryModel?: string;
  objective1?: string;
  objective2?: string;
  parentWeeklyMapId?: string;
  parentDailyMapId?: string;
};
type VisualLayer = {
  narrative: string;
  mapBias: 'bullish' | 'bearish' | 'manual';
  rangeHigh: string;
  rangeLow: string;
  currentZone: string;
  objectiveZone: string;
  tickStep: number;
  brokenExternal: 'EXT_H' | 'EXT_L' | 'NONE';
  brokenExternalPrice: string;
  useLiveCurrent: boolean;
  projectionX: number;
  projectionPrice: string;
  liquidityCleanUpPrice?: string;
  showLiquidityCleanUp?: boolean;
  mitigation: { extL: string; discount: string; premium: string; extH: string };
  mitigationLevels?: MitigationLevels;
  mitigationSequence?: string[];
  path: GraphPoint[];
  meta?: MapMeta;
};
type VisualStore = Record<LayerKey, VisualLayer>;

const makePoint = (label: string, zone: string, x: number, price = '', anchorKey = label.toUpperCase().replace(/[^A-Z0-9]+/g, '_')): GraphPoint => ({ id: cryptoId(), label, anchorKey, zone, x, sequenceColumn: 1, price, status: 'INTACT', role: '' });

const emptyMitigationLevels = (): MitigationLevels => ({
  discount: { m1: { price: '', status: 'WAITING' }, m2: { price: '', status: 'WAITING' }, m3: { price: '', status: 'WAITING' } },
  fair_price: { m1: { price: '', status: 'WAITING' }, m2: { price: '', status: 'WAITING' }, m3: { price: '', status: 'WAITING' } },
  premium: { m1: { price: '', status: 'WAITING' }, m2: { price: '', status: 'WAITING' }, m3: { price: '', status: 'WAITING' } },
});

const defaultVisual: VisualStore = {
  weekly: {
    narrative: 'Bullish From External Low', mapBias: 'bullish',
    rangeHigh: '5425', rangeLow: '4109', currentZone: 'D', objectiveZone: 'P', tickStep: 200, brokenExternal: 'EXT_L', brokenExternalPrice: '', useLiveCurrent: false, projectionX: 90, projectionPrice: '',
    mitigation: { extL: 'Fresh', discount: 'Fresh', premium: 'Fresh', extH: 'Fresh' },
    mitigationLevels: emptyMitigationLevels(),
    meta: { profile: 'SND_DEEP_RETRACE', deliveryState: 'TO_FAIR_PRICE', reactionState: 'FULL_RECLAIM', continuationState: 'CONTINUE_BULLISH', objective1: 'FAIR_PRICE', objective2: 'PREMIUM_M1' },
    path: [makePoint('EXT_L', 'Ext L', 10, '', 'EXT_L'), makePoint('PREV_L', 'Fair', 28, '', 'PREV_L'), makePoint('CURRENT', 'D', 44, '', 'CURRENT'), makePoint('OBJECTIVE_1', 'Fair', 72, '', 'OBJECTIVE_1'), makePoint('OBJECTIVE_2', 'P', 88, '', 'OBJECTIVE_2')],
  },
  daily: {
    narrative: 'Bearish From Deep Premium', mapBias: 'bearish',
    rangeHigh: '4778', rangeLow: '3865', currentZone: 'D', objectiveZone: 'DD', tickStep: 100, brokenExternal: 'EXT_H', brokenExternalPrice: '', useLiveCurrent: false, projectionX: 90, projectionPrice: '',
    mitigation: { extL: 'Fresh', discount: 'Fresh', premium: 'Fresh', extH: 'Fresh' },
    mitigationLevels: emptyMitigationLevels(),
    meta: { profile: 'SND_TO_SR_CONTINUATION', deliveryState: 'TO_FAIR_PRICE', reactionState: 'STRONG_REACTION', continuationState: 'CONTINUE_BEARISH', phaseState: 'P2_ACTIVE', objective1: 'FAIR_PRICE', objective2: 'DISCOUNT_M1' },
    path: [makePoint('EXT_H', 'Ext H', 10, '', 'EXT_H'), makePoint('PREV_H', 'Fair', 28, '', 'PREV_H'), makePoint('CURRENT', 'D', 56, '', 'CURRENT'), makePoint('OBJECTIVE_1', 'Fair', 72, '', 'OBJECTIVE_1'), makePoint('OBJECTIVE_2', 'DD', 88, '', 'OBJECTIVE_2')],
  },
  intraday: {
    narrative: 'Manual Intraday Delivery', mapBias: 'manual',
    rangeHigh: '4595', rangeLow: '4366', currentZone: 'Fair', objectiveZone: 'D', tickStep: 50, brokenExternal: 'NONE', brokenExternalPrice: '', useLiveCurrent: false, projectionX: 90, projectionPrice: '', liquidityCleanUpPrice: '4452.10', showLiquidityCleanUp: true,
    mitigation: { extL: 'Fresh', discount: 'Fresh', premium: 'Fresh', extH: 'Fresh' },
    mitigationLevels: emptyMitigationLevels(),
    meta: { profile: 'IMMEDIATE_CONTINUATION', phaseState: 'IMMEDIATE_ENTRY_ACTIVE', entryModel: 'IMMEDIATE_CONTINUATION_ENTRY', objective1: 'OPPOSITE_INTRADAY_EXTREME', objective2: 'RUNNER_TARGET' },
    path: [makePoint('CHOCH_HIGH', 'P', 12, '', 'CHOCH_HIGH'), makePoint('CHOCH_BREAK', 'Fair', 12, '', 'CHOCH_BREAK'), makePoint('CHOCH_LOW', 'D', 12, '', 'CHOCH_LOW'), makePoint('IMMEDIATE_ENTRY', 'D', 28, '', 'IMMEDIATE_ENTRY'), makePoint('MICRO_BOS', 'Fair', 44, '', 'MICRO_BOS'), makePoint('MICRO_BOS_SWEEP', 'D', 60, '', 'MICRO_BOS_SWEEP'), makePoint('REF_CONFIRMATION', 'Fair', 72, '', 'REF_CONFIRMATION'), makePoint('ADD_RISK_ENTRY', 'D', 82, '', 'ADD_RISK_ENTRY'), makePoint('RUNNER_TARGET', 'P', 92, '', 'RUNNER_TARGET')],
  },
};

const WEEKLY_DAILY_ANCHORS = ['EXT_H','EXT_L','PREV_H','PREV_L','FAIR_PRICE','CURRENT','OBJECTIVE_1','OBJECTIVE_2','INVALIDATION'];
const DAILY_EXTRA_ANCHORS = ['CHOCH','P1','P2','P3','P3_FAIL','NEW_P1'];
const INTRADAY_ANCHORS = ['CHOCH_HIGH','CHOCH_BREAK','CHOCH_LOW','IMMEDIATE_ENTRY','P1','P1_BOS','P2','P2_BOS','P3','P3_FAIL','NEW_P1','INTERNAL_SWEEP_LEVEL','MICRO_BOS','MICRO_BOS_SWEEP','REF_CONFIRMATION','ADD_RISK_ENTRY','SL','ADD_RISK_SL','TP1','TP2','RUNNER_TARGET','CURRENT','INVALIDATION'];
const ANCHOR_STATUS = ['INTACT','BROKEN','BROKEN_RECLAIMED','FAILED_RECLAIM','TARGETED','MITIGATED','FAILED','CONFIRMED','INVALIDATED','HELD_VALID','BROKEN_CONFIRMED'];
const WEEKLY_PROFILES = ['SND_DEEP_RETRACE','SR_SHALLOW_RETRACE','COMPRESSION','EXPANSION_NO_RETRACE','FAILED_RETRACE'];
const DAILY_PROFILES = ['SND_DEEP_RETRACE','SR_SHALLOW_RETRACE','SND_TO_SR_CONTINUATION','SR_TO_SND_CONTINUATION','SND_TO_SR_REVERSAL','SR_TO_SND_REVERSAL','FAILED_PROFILE_FLIP'];
const INTRADAY_PROFILES = ['WAITING','SND_DEEP_RETRACE_ENTRY','SR_SHALLOW_RETRACE_ENTRY','IMMEDIATE_CONTINUATION','CONFIRMED_CONTINUATION_ADD_RISK','P3_FAIL_REVERSAL','NEW_P1_PROFILE_FLIP_CONTINUATION','FAILED_PROFILE_FLIP'];
const DELIVERY_STATES = ['TO_FAIR_PRICE','TO_PREMIUM','TO_DEEP_PREMIUM','TO_DISCOUNT','TO_DEEP_DISCOUNT','TO_EXTERNAL'];
const REACTION_STATES = ['NO_REACTION','WEAK_REACTION','STRONG_REACTION','FULL_RECLAIM','FAILED_REACTION','PROFILE_FLIP'];
const CONTINUATION_STATES = ['CONTINUE_BULLISH','CONTINUE_BEARISH','ROTATE_RANGE','EXPAND_RANGE','REVERSE_RANGE'];
const PHASE_STATES = ['PRE_CHOCH','CHOCH_CONFIRMED','IMMEDIATE_ENTRY_ACTIVE','P1_ACTIVE','P1_BOS_CONFIRMED','P2_ACTIVE','P2_BOS_CONFIRMED','P3_ACTIVE','P3_FAILED','NEW_P1_ACTIVE','INTERNAL_SWEEP_CLEANUP','REF_CONFIRMATION_ACTIVE','ADD_RISK_READY','EXECUTED','INVALIDATED'];
const ENTRY_MODELS = ['IMMEDIATE_CONTINUATION_ENTRY','CONFIRMED_CONTINUATION_ADD_RISK','SND_618_PULLBACK','SR_SECOND_CANDLE','BREAKOUT_ENTRY','DAILY_OPEN_ENTRY','P3_FAIL_RECLAIM_ENTRY'];
const MITIGATION_TARGETS = ['DISCOUNT_M1','DISCOUNT_M2','DISCOUNT_M3','FAIR_PRICE_M1','FAIR_PRICE_M2','FAIR_PRICE_M3','PREMIUM_M1','PREMIUM_M2','PREMIUM_M3'];
const OBJECTIVE_TYPES = [...MITIGATION_TARGETS,'FAIR_PRICE','EXT_H','EXT_L','NEXT_HTF_OBJECTIVE','OPPOSITE_INTRADAY_EXTREME','RUNNER_TARGET','EXTENSION_ONLY'];

function anchorsForLayer(layer: LayerKey) {
  if (layer === 'intraday') return INTRADAY_ANCHORS;
  if (layer === 'daily') return [...WEEKLY_DAILY_ANCHORS, ...DAILY_EXTRA_ANCHORS];
  return WEEKLY_DAILY_ANCHORS;
}
function profilesForLayer(layer: LayerKey) {
  if (layer === 'intraday') return INTRADAY_PROFILES;
  if (layer === 'daily') return DAILY_PROFILES;
  return WEEKLY_PROFILES;
}
function matrixXFor(index: number, total: number) {
  const safeTotal = Math.max(2, total || 2);
  return clamp(10 + index * (80 / (safeTotal - 1)), 8, 92);
}
function matrixLabelFor(layer: LayerKey, index: number) {
  const labels = layer === 'intraday'
    ? ['CHOCH RANGE','ENTRY','MICRO BOS','SWEEP','REF / ADD RISK','TARGET']
    : ['EXT RANGE','PREV LEVEL','RECLAIM / REACTION','CURRENT','OBJECTIVE 1','OBJECTIVE 2'];
  return labels[Math.min(index, labels.length - 1)] || `COL ${index + 1}`;
}
function anchorColumnIndex(point: GraphPoint, index: number, total: number, layer: LayerKey) {
  const key = String(point.anchorKey || point.label || '').toUpperCase();
  if (layer === 'intraday') {
    if (key.startsWith('CHOCH')) return 0;
    if (['IMMEDIATE_ENTRY','ENTRY','SL','ADD_RISK_SL'].includes(key)) return 1;
    if (key.includes('P1') || key === 'MICRO_BOS') return 2;
    if (key.includes('P2') || key.includes('SWEEP')) return 3;
    if (key.includes('P3') || key.includes('REF') || key.includes('ADD_RISK')) return 4;
    if (key.includes('TP') || key.includes('RUNNER') || key.includes('OBJECTIVE')) return 5;
    if (key === 'CURRENT') return 4;
  }
  return Math.min(index, 5);
}
function matrixXForPoint(point: GraphPoint, index: number, total: number, layer: LayerKey) {
  return matrixXFor(anchorColumnIndex(point, index, total, layer), 6);
}
function journalReadyMap(layer: LayerKey, visual: VisualLayer) {
  return {
    timeframe: layer.toUpperCase(),
    bias: visual.mapBias,
    profile: visual.meta?.profile || '',
    delivery_state: visual.meta?.deliveryState || '',
    reaction_state: visual.meta?.reactionState || '',
    continuation_state: visual.meta?.continuationState || '',
    phase_state: visual.meta?.phaseState || '',
    entry_model: visual.meta?.entryModel || '',
    objective_1: visual.meta?.objective1 || '',
    objective_2: visual.meta?.objective2 || '',
    liquidity_cleanup_price: visual.liquidityCleanUpPrice || '',
    show_liquidity_cleanup: !!visual.showLiquidityCleanUp,
    range_high: visual.rangeHigh || '',
    range_low: visual.rangeLow || '',
    anchors: (visual.path || []).map((p, idx) => ({
      timeframe: layer.toUpperCase(),
      anchor_key: p.anchorKey || p.label || '',
      label: p.label || p.anchorKey || '',
      price: p.price || '',
      zone: p.zone || '',
      sequence_column: idx + 1,
      status: p.status || 'INTACT',
      role: p.role || ''
    }))
  };
}

function telemetryForMap(layer: LayerKey, visual: VisualLayer, livePrice?: number | null) {
  const prices = (visual.path || [])
    .map((p) => parseNum(p.price))
    .filter((n) => Number.isFinite(n)) as number[];
  const current = Number.isFinite(Number(livePrice)) ? Number(livePrice) : parseNum((visual.path || []).find(p => String(p.anchorKey || p.label || '').toUpperCase() === 'CURRENT')?.price);
  const all = Number.isFinite(current) ? [...prices, current] : prices;
  return {
    timeframe: layer.toUpperCase(),
    live_current_price: Number.isFinite(current) ? Math.round(current * 100) / 100 : null,
    live_high_watermark: all.length ? Math.round(Math.max(...all) * 100) / 100 : null,
    live_low_watermark: all.length ? Math.round(Math.min(...all) * 100) / 100 : null,
    liquidity_cleanup_price: visual.liquidityCleanUpPrice || null,
    updated_at: new Date().toISOString(),
  };
}

function App() {
  const [symbol, setSymbol] = useLocalStorage('fx_tm_symbol', 'XAUUSD');
  const { page, setPage } = useAppPageNavigation();
  const {
    state,
    activeTrade: active,
    journal,
    status,
    brain,
    journalSummary,
    structuredJournal,
    detailedJournal,
    apiOnline,
    error,
    lastRefresh,
    refresh,
  } = useCockpitSync(symbol, BASE_URL);
  const [ideas, setIdeas] = useLocalStorage<TradeIdea[]>('fx_tm_trade_ideas', []);
  const [selectedIdea, setSelectedIdea] = useState<string | null>(null);
  const [visuals, rawSetVisuals] = useLocalStorage<VisualStore>('fx_tm_visual_layers_v027', defaultVisual);
  const visualsSafe = useMemo(() => normalizeVisuals(visuals), [visuals]);
  const setVisuals = (v: VisualStore) => rawSetVisuals(normalizeVisuals(v));
  const [saveMsg, setSaveMsg] = useState('');

  const engine = state?.engine?.htf_map || {};
  const pickedIdea = ideas.find(x => x.id === selectedIdea) || ideas[0];
  const livePrice = extractLivePrice(state, active);
  const updateVisual = (key: LayerKey, patch: Partial<VisualLayer>) => setVisuals({ ...visualsSafe, [key]: { ...visualsSafe[key], ...patch } });
  const mapStatePayload = () => {
    const telemetry = {
      weekly: telemetryForMap('weekly', visualsSafe.weekly, livePrice),
      daily: telemetryForMap('daily', visualsSafe.daily, livePrice),
      intraday: telemetryForMap('intraday', visualsSafe.intraday, livePrice),
    };
    return {
      symbol,
      version: 'electron_v032_map_derived_lifecycle' ,
      updated_by: 'electron',
      updated_from_device: 'electron',
      visual_state: visualsSafe,
      telemetry,
      layers: {
        weekly: { visual: visualsSafe.weekly, anchors: journalReadyMap('weekly', visualsSafe.weekly).anchors, meta: journalReadyMap('weekly', visualsSafe.weekly), telemetry: telemetry.weekly },
        daily: { visual: visualsSafe.daily, anchors: journalReadyMap('daily', visualsSafe.daily).anchors, meta: journalReadyMap('daily', visualsSafe.daily), telemetry: telemetry.daily },
        intraday: { visual: visualsSafe.intraday, anchors: journalReadyMap('intraday', visualsSafe.intraday).anchors, meta: journalReadyMap('intraday', visualsSafe.intraday), telemetry: telemetry.intraday },
      },
      journal_ready: {
        weekly: journalReadyMap('weekly', visualsSafe.weekly),
        daily: journalReadyMap('daily', visualsSafe.daily),
        intraday: journalReadyMap('intraday', visualsSafe.intraday),
      }
    };
  };
  const localSave = () => { localStorage.setItem('fx_tm_visual_layers_v027', JSON.stringify(visualsSafe)); localStorage.setItem('fx_tm_trade_ideas', JSON.stringify(ideas)); setSaveMsg(`Saved local draft ${new Date().toLocaleTimeString()}`); setTimeout(() => setSaveMsg(''), 2600); };
  const saveMapsToBackend = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/maps/state`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(mapStatePayload()) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `Backend save failed ${r.status}`);
      setSaveMsg(`Saved to backend ${new Date().toLocaleTimeString()}`);
    } catch (e:any) { setSaveMsg(`Backend save failed: ${e?.message || e}`); }
    setTimeout(() => setSaveMsg(''), 4200);
  };
  const loadMapsFromBackend = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/maps/state?symbol=${encodeURIComponent(symbol)}`);
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `Backend load failed ${r.status}`);
      const next = data?.state?.visual_state || data?.visual_state || data?.state?.visuals || null;
      if (!next) { setSaveMsg('No backend map state found yet'); setTimeout(() => setSaveMsg(''), 3200); return; }
      setVisuals(normalizeVisuals(next));
      setSaveMsg(`Loaded backend state ${new Date().toLocaleTimeString()}`);
    } catch (e:any) { setSaveMsg(`Backend load failed: ${e?.message || e}`); }
    setTimeout(() => setSaveMsg(''), 4200);
  };

  const overviewMaps = useMemo(() => (
    <>
      <div className="mapPair topContextPair">
        <XYTrajectoryPanel title="Weekly Map" layerKey="weekly" layer={engine.weekly} visual={visualsSafe.weekly} updateVisual={updateVisual} accent="gold" livePrice={livePrice} readOnly compact />
        <XYTrajectoryPanel title="Daily Map" layerKey="daily" layer={engine.daily} visual={visualsSafe.daily} updateVisual={updateVisual} accent="blue" livePrice={livePrice} readOnly compact />
      </div>
      <div className="intradayHero">
        <XYTrajectoryPanel title="Intraday Execution Map" layerKey="intraday" layer={engine.macro || engine.weekly} visual={visualsSafe.intraday} updateVisual={updateVisual} accent="cyan" intraday={state?.intraday || state?.mobile_intraday} livePrice={livePrice} readOnly compact />
      </div>
    </>
  ), [engine.weekly, engine.daily, engine.macro, visualsSafe.weekly, visualsSafe.daily, visualsSafe.intraday, state?.intraday, state?.mobile_intraday, livePrice, updateVisual]);

  const overviewPlanning = useMemo(() => (
    <div className="overviewPlanningStrip">
      <TradeIdeaPanel ideas={ideas} setIdeas={setIdeas} selectedIdea={selectedIdea} setSelectedIdea={setSelectedIdea} state={state} brain={brain} currentSymbol={symbol} />
    </div>
  ), [ideas, selectedIdea, state, brain, symbol, setIdeas]);

  const cockpitOverviewValue = useMemo(() => ({
    overviewMaps,
    overviewPlanning,
    brain,
    symbol,
  }), [overviewMaps, overviewPlanning, brain, symbol]);

  return <CockpitOverviewProvider value={cockpitOverviewValue}><div className="appShell">
    <NavSidebar page={page} apiOnline={apiOnline} onNavigate={setPage} onRefresh={() => void refresh()} />
    <main className={`workspaceMain ${page === 'mapstudio' ? 'workspaceMainMapStudio' : ''}`}>
      {page !== 'mapstudio' && <header className="topbar">
        <div><h2>{pageTitle(page)}</h2><p>{pageSubtitle(page)}</p></div>
        <div className="topActions"><select value={symbol} onChange={e => setSymbol(e.target.value)}>{SYMBOLS.map(s => <option key={s}>{s}</option>)}</select><button onClick={() => void refresh()}><RefreshCw size={16}/> Refresh</button>{page === 'settings' && <button onClick={localSave}><Save size={16}/> Save Local</button>}<span className="timePill">{saveMsg || lastRefresh || '-'}</span></div>
      </header>}
      {error && page !== 'mapstudio' && <div className="errorBox"><AlertTriangle size={16}/>{error}</div>}

      {page === 'mapstudio' && <MapStudio symbol={symbol} onSymbolChange={setSymbol} />}

      {page === 'ideas' && <section className="singlePage"><TradeIdeaPanel large ideas={ideas} setIdeas={setIdeas} selectedIdea={pickedIdea} setSelectedIdea={setSelectedIdea} state={state} brain={brain} currentSymbol={symbol}/></section>}
      {page === 'brain' && <section className="singlePage"><LifecycleCatchUpWizard symbol={symbol} onSaved={() => void refresh()} /></section>}
      {page === 'journal' && <section className="singlePage"><JournalPage rows={journal} summary={journalSummary} structured={structuredJournal} detailed={detailedJournal}/></section>}
      {page === 'data' && <section className="singlePage"><AnalystPage /></section>}
      {page === 'historical' && <section className="singlePage"><HistoricalLifecycleBuilder symbol={symbol} visuals={visualsSafe} /></section>}
      {page === 'sql' && <section className="singlePage"><SqlPage status={status} journal={journal} summary={journalSummary} structured={structuredJournal}/></section>}
      {page === 'settings' && <section className="singlePage"><GraphSettings visuals={visualsSafe} setVisuals={setVisuals} updateVisual={updateVisual} localSave={localSave} saveMapsToBackend={saveMapsToBackend} loadMapsFromBackend={loadMapsFromBackend}/></section>}
    </main>
    <aside className="inspectorPanel" id="pilot-inspector-root" aria-label="Inspector">
      {page !== 'mapstudio' && (
        <div className="inspectorPlaceholder">
          <b>Inspector</b>
          <span>Open Map Studio for Dashboard, Narrative, GPS, Mark, Case Manager, and Trade Idea panels.</span>
        </div>
      )}
    </aside>
  </div></CockpitOverviewProvider>;
}

type Candle = { symbol:string; timeframe:string; time:string; open:number; high:number; low:number; close:number; volume?:number };
type MapEvent = { id:string; event_type:string; event_name?:string; time?:string; price:number; zone?:string; zone_percent?:number; notes?:string; candle_open?:number; candle_high?:number; candle_low?:number; candle_close?:number; source?:'map'|'seed'|'auto'|'candidate'|'manual'; primitive?:string; derived_event_code?:string; movement_rule?:string; range_status_after?:string; engine_source?:string; logic_version?:string; candidate_id?:string; confidence?:string; candidate_status?:'ACCEPTED'|'REJECTED'|'EDITED'|'CANDIDATE'; meta_json?:any; structural_event?:string; layer?:string; parent_timeframe?:string; range_id?:any; active_range_id?:any; parent_range_id?:any; old_range_id?:any; new_range_id?:any; raw_event_id?:string };

type StructureLayer = 'MACRO'|'WEEKLY'|'DAILY'|'INTRADAY'|'MICRO';
type RangeScope = 'MAJOR' | 'MINOR';
const STRUCTURE_LAYERS: StructureLayer[] = ['MACRO', 'WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'];
const RANGE_SCOPES: RangeScope[] = ['MAJOR', 'MINOR'];
const STRUCTURE_LAYER_CHIP: Record<StructureLayer, string> = {
  MACRO: 'M', WEEKLY: 'W', DAILY: 'D', INTRADAY: 'I', MICRO: 'µ',
};
function defaultSourceTimeframeForStructureLayer(layer: StructureLayer): string {
  return ({ MACRO:'MN1', WEEKLY:'W1', DAILY:'D1', INTRADAY:'H1', MICRO:'M15' } as Record<StructureLayer,string>)[layer] || 'D1';
}
function defaultChartTimeframeForStructureLayer(layer: StructureLayer): string {
  return defaultSourceTimeframeForStructureLayer(layer);
}
function allowedChartTimeframesForStructureLayer(layer: StructureLayer): string[] {
  if (layer === 'MACRO') return ['MN1', 'W1'];
  if (layer === 'WEEKLY') return ['W1'];
  if (layer === 'DAILY') return ['D1'];
  if (layer === 'INTRADAY') return ['H4', 'H1'];
  return ['M15', 'M5'];
}
function isChartTimeframeAllowedForLayer(chartTf: string, layer: StructureLayer): boolean {
  return allowedChartTimeframesForStructureLayer(layer).includes(String(chartTf || '').toUpperCase());
}
function expectedParentStructureLayer(layer: StructureLayer): StructureLayer | null {
  const idx = STRUCTURE_LAYERS.indexOf(layer);
  return idx > 0 ? STRUCTURE_LAYERS[idx - 1] : null;
}
function expectedChildStructureLayer(layer: StructureLayer): StructureLayer | null {
  const idx = STRUCTURE_LAYERS.indexOf(layer);
  return idx >= 0 && idx < STRUCTURE_LAYERS.length - 1 ? STRUCTURE_LAYERS[idx + 1] : null;
}
function directChildCountLabel(parentLayer: StructureLayer): string | null {
  return ({ MACRO: 'Weekly', WEEKLY: 'Daily', DAILY: 'Intraday', INTRADAY: 'Micro', MICRO: null } as Record<StructureLayer, string | null>)[parentLayer];
}
function hierarchyChildCountLabel(parent: any, children: any[]): string | null {
  if (!children.length) return null;
  const pLayer = normalizeStructureLayer(parent?.structure_layer || parent?.layer);
  const first = children[0];
  const cLayer = normalizeStructureLayer(first?.structure_layer || first?.layer);
  if (cLayer === pLayer && !isRangeMajor(first)) return 'Minor';
  return directChildCountLabel(pLayer);
}
function directHierarchyChildren(parent: any, nodes: any[]): any[] {
  const pid = String(parent?.range_id || parent?.id || '');
  if (!pid) return [];
  const linked = nodes.filter((c:any) => String(c.parent_range_id || '') === pid);
  const pLayer = normalizeStructureLayer(parent.structure_layer || parent.layer);
  const pMajor = isRangeMajor(parent);

  if (pMajor) {
    const minors = linked.filter((c:any) =>
      normalizeStructureLayer(c.structure_layer || c.layer) === pLayer && !isRangeMajor(c),
    );
    if (minors.length) return minors.sort(compareRangesByStartDate);

    const nextLayer = expectedChildStructureLayer(pLayer);
    if (nextLayer) {
      return linked.filter((c:any) =>
        normalizeStructureLayer(c.structure_layer || c.layer) === nextLayer && isRangeMajor(c),
      ).sort(compareRangesByStartDate);
    }
    return [];
  }

  const nextLayer = expectedChildStructureLayer(pLayer);
  if (!nextLayer) return [];
  return linked.filter((c:any) =>
    normalizeStructureLayer(c.structure_layer || c.layer) === nextLayer && isRangeMajor(c),
  ).sort(compareRangesByStartDate);
}
function rangeYearBucket(range: any): number | null {
  const activeFrom = parseStructuralTimeMs(range?.active_from_time);
  if (activeFrom !== null) return new Date(activeFrom).getUTCFullYear();
  const start = parseStructuralTimeMs(range?.range_start_time);
  if (start !== null) return new Date(start).getUTCFullYear();
  const rh = parseStructuralTimeMs(range?.range_high_time);
  const rl = parseStructuralTimeMs(range?.range_low_time);
  const span = [rh, rl].filter((x): x is number => x !== null);
  if (span.length) return new Date(Math.min(...span)).getUTCFullYear();
  return null;
}
function rangeCrossYearSpanNote(range: any): string | null {
  const times = [
    range?.active_from_time,
    range?.range_start_time,
    range?.range_high_time,
    range?.range_low_time,
    range?.inactive_from_time,
    range?.range_end_time,
  ].map(parseStructuralTimeMs).filter((x): x is number => x !== null);
  if (times.length < 2) return null;
  const yMin = new Date(Math.min(...times)).getUTCFullYear();
  const yMax = new Date(Math.max(...times)).getUTCFullYear();
  return yMin !== yMax ? `spans ${yMin} → ${yMax}` : null;
}
function formatExplorerCompactDate(value: string): string {
  if (!value || value === '?' || value === 'ACTIVE') return value;
  const ms = parseStructuralTimeMs(value);
  if (ms === null) return value.length > 10 ? value.slice(0, 10) : value;
  const d = new Date(ms);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()} ${d.getUTCFullYear()}`;
}
function formatExplorerRangeSpan(range: any): string {
  const start = formatExplorerCompactDate(rangeLabelStartDate(range));
  const endRaw = rangeLabelEndDate(range);
  const end = endRaw === 'ACTIVE' ? 'ACTIVE' : formatExplorerCompactDate(endRaw);
  if (end === 'ACTIVE') return `${start} → ACTIVE`;
  return `${start} → ${end}`;
}
function normalizeRangeScope(value: any): RangeScope {
  const scope = String(value || 'MAJOR').toUpperCase();
  return scope === 'MINOR' ? 'MINOR' : 'MAJOR';
}
function isRangeMajor(range: any): boolean {
  return normalizeRangeScope(range?.range_scope) === 'MAJOR';
}
function formatRangeLayerScopeLabel(range: any): string {
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || '?';
  const scope = normalizeRangeScope(range?.range_scope);
  const id = range?.range_id || range?.id || '?';
  return `${layer} ${scope} #${id}`;
}
function formatExplorerRowLines(
  range: any,
  directChildCount: number,
  childCountLabel?: string | null,
): { line1: string; line2: string; spanNote: string | null } {
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || '?';
  const scope = normalizeRangeScope(range?.range_scope);
  const id = range?.range_id || range?.id || '?';
  const statusPart = rangeStatusDirectionLabel(range);
  const childLabel = scope === 'MAJOR' && directChildCount > 0
    ? (childCountLabel || directChildCountLabel(layer as StructureLayer))
    : null;
  const high = Number(range?.range_high_price ?? range?.range_high);
  const low = Number(range?.range_low_price ?? range?.range_low);
  const rh = Number.isFinite(high) ? high.toFixed(2) : '?';
  const rl = Number.isFinite(low) ? low.toFixed(2) : '?';
  return {
    line1: childLabel ? `${layer} ${scope} #${id} · ${directChildCount} ${childLabel}` : `${layer} ${scope} #${id}`,
    line2: `${formatExplorerRangeSpan(range)} | ${statusPart} · RH ${rh} / RL ${rl}`,
    spanNote: rangeCrossYearSpanNote(range),
  };
}
function formatExplorerCompactRowLabel(
  range: any,
  directChildCount: number,
  childCountLabel?: string | null,
): { label: string; title: string } {
  const lines = formatExplorerRowLines(range, directChildCount, childCountLabel);
  return {
    label: [lines.line1, lines.line2].filter(Boolean).join(' · '),
    title: [lines.line1, lines.line2, lines.spanNote].filter(Boolean).join('\n'),
  };
}
function filterRangesForExplorerYear(ranges: any[], yearFilter: string): any[] {
  if (!yearFilter || yearFilter === 'all') return safeArray(ranges);
  const year = Number(yearFilter);
  if (!Number.isFinite(year)) return safeArray(ranges);
  return safeArray(ranges).filter((r:any) => rangeYearBucket(r) === year);
}
function parentRangeIdForStructureLayer(layer: StructureLayer, rangeScope: RangeScope, selectedParentRangeId: string): string | null {
  if (rangeScope === 'MAJOR' && layer === 'MACRO') return null;
  if (rangeScope === 'MINOR') return selectedParentRangeId || null;
  if (layer === 'MACRO') return null;
  return selectedParentRangeId || null;
}

function parentLayerCandidates(layer: StructureLayer, savedRanges: any[], rangeScope: RangeScope = 'MAJOR'): any[] {
  if (rangeScope === 'MINOR') {
    return safeArray(savedRanges).filter((r:any) =>
      normalizeStructureLayer(r.structure_layer || r.layer) === layer && isRangeMajor(r),
    );
  }
  const parentLayer = expectedParentStructureLayer(layer);
  if (!parentLayer) return [];
  return safeArray(savedRanges).filter((r:any) =>
    normalizeStructureLayer(r.structure_layer || r.layer) === parentLayer && isRangeMajor(r),
  );
}

function parentTargetLayerLabel(layer: StructureLayer, rangeScope: RangeScope): string {
  if (rangeScope === 'MINOR') return `${layer} MAJOR`;
  return expectedParentStructureLayer(layer) || 'none';
}

type ParentResolveMode =
  | 'none'
  | 'manual'
  | 'date_containment'
  | 'single_candidate'
  | 'multiple_matches'
  | 'no_match';

type ParentResolveResult = {
  parentId: string | null;
  error: string | null;
  autoSelected: boolean;
  mode: ParentResolveMode;
  matchIds: string[];
  orphanWarning: string | null;
};

function parseStructuralTimeMs(value: any): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const raw = String(value).trim();
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }
  const ms = candleTimeMs(raw);
  return Number.isFinite(ms) ? ms : null;
}

function resolveEffectiveStructuralAnchorTimes(
  rhAnchor: { price?: string; time?: string },
  rlAnchor: { price?: string; time?: string },
  rangeWindow?: { start?: string; end?: string } | null,
  fallbackCandleTime?: string | null,
): { range_high_time: string | null; range_low_time: string | null } {
  const winStart = rangeWindow?.start ? String(rangeWindow.start) : '';
  const winEnd = rangeWindow?.end ? String(rangeWindow.end) : '';
  const fallback = fallbackCandleTime ? String(fallbackCandleTime) : '';
  const rhTime = rhAnchor.time || winEnd || fallback || null;
  const rlTime = rlAnchor.time || winStart || fallback || null;
  return { range_high_time: rhTime, range_low_time: rlTime };
}

function childDraftAnchorTimesMs(childSpan?: {
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

function parentLifecycleStartMs(parent: any): number | null {
  const values = [parent?.active_from_time, parent?.range_start_time].map(parseStructuralTimeMs).filter((x): x is number => x !== null);
  return values.length ? Math.min(...values) : null;
}

function parentLifecycleEndMs(parent: any): number | null {
  const status = String(parent?.status || 'ACTIVE').toUpperCase();
  if (!['BROKEN', 'ABANDONED', 'ARCHIVED'].includes(status)) return null;
  return parseStructuralTimeMs(parent?.inactive_from_time);
}

function parentContainsChildByLifecycle(parent: any, childTimesMs: number[]): boolean {
  if (!childTimesMs.length) return true;
  const pStart = parentLifecycleStartMs(parent);
  const pEnd = parentLifecycleEndMs(parent);
  const cMin = Math.min(...childTimesMs);
  const cMax = Math.max(...childTimesMs);
  if (pStart !== null && cMin < pStart) return false;
  if (pEnd !== null && cMax > pEnd) return false;
  return true;
}

function rangeLabelStartDate(range: any): string {
  const values = [range?.range_high_time, range?.range_low_time, range?.active_from_time, range?.range_start_time];
  const ms = values.map(parseStructuralTimeMs).filter((x): x is number => x !== null);
  if (!ms.length) return '?';
  return new Date(Math.min(...ms)).toISOString().slice(0, 10);
}

function rangeLabelEndDate(range: any): string {
  const status = String(range?.status || 'ACTIVE').toUpperCase();
  if (status === 'ACTIVE') return 'ACTIVE';
  if (['BROKEN', 'ABANDONED', 'ARCHIVED'].includes(status) && range?.inactive_from_time) {
    const ms = parseStructuralTimeMs(range.inactive_from_time);
    if (ms !== null) return new Date(ms).toISOString().slice(0, 10);
  }
  const values = [range?.range_high_time, range?.range_low_time, range?.range_end_time];
  const ms = values.map(parseStructuralTimeMs).filter((x): x is number => x !== null);
  if (!ms.length) return status === 'ACTIVE' ? 'ACTIVE' : '?';
  return new Date(Math.max(...ms)).toISOString().slice(0, 10);
}

function rangeStatusDirectionLabel(range: any): string {
  const status = String(range?.status || 'ACTIVE').toUpperCase();
  const dir = String(range?.direction_of_break || '').toUpperCase();
  if (status === 'BROKEN' && (dir === 'UP' || dir === 'DOWN')) return `BROKEN ${dir}`;
  if (status === 'ACTIVE') return 'ACTIVE';
  return status;
}

function formatStructuralRangeOptionLabel(range: any): string {
  const id = range?.range_id || range?.id || '?';
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || '?';
  const scope = normalizeRangeScope(range?.range_scope);
  const start = rangeLabelStartDate(range);
  const end = rangeLabelEndDate(range);
  const statusPart = rangeStatusDirectionLabel(range);
  const low = range?.range_low_price ?? range?.range_low ?? '?';
  const high = range?.range_high_price ?? range?.range_high ?? '?';
  const lowN = Number(low);
  const highN = Number(high);
  const pricePart = Number.isFinite(lowN) && Number.isFinite(highN)
    ? `${lowN.toFixed(2)} → ${highN.toFixed(2)}`
    : `${low} → ${high}`;
  return `#${id} ${layer} ${scope} | ${start} → ${end} | ${statusPart} | ${pricePart}`;
}

function formatStructuralRangeDisplayLines(range: any, savedRanges: any[]): { line1: string; line2: string; parentLine?: string } {
  const id = range?.range_id || range?.id || '?';
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || '?';
  const scope = normalizeRangeScope(range?.range_scope);
  const start = rangeLabelStartDate(range);
  const end = rangeLabelEndDate(range);
  const statusPart = rangeStatusDirectionLabel(range);
  const low = Number(range?.range_low_price ?? range?.range_low);
  const high = Number(range?.range_high_price ?? range?.range_high);
  const pricePart = Number.isFinite(low) && Number.isFinite(high)
    ? `${low.toFixed(2)} → ${high.toFixed(2)}`
    : '—';
  const line1 = `#${id} ${layer} ${scope} | ${start} → ${end} | ${statusPart}`;
  const line2 = pricePart;
  let parentLine: string | undefined;
  const parentId = range?.parent_range_id;
  if (parentId !== null && parentId !== undefined && String(parentId) !== '') {
    const parent = safeArray(savedRanges).find((r:any) => String(r.range_id || r.id) === String(parentId));
    const parentLayer = parent ? (normalizeStructureLayer(parent.structure_layer || parent.layer) || 'Parent') : 'Parent';
    const parentScope = parent ? normalizeRangeScope(parent.range_scope) : 'MAJOR';
    parentLine = `Parent: ${parentLayer} ${parentScope} #${parentId}`;
  }
  return { line1, line2, parentLine };
}

function formatHierarchyTreeRowLabel(range: any): string {
  const { line1, line2 } = formatHierarchyTreeRowLines(range);
  return `${line1} | ${line2.replace(' · ', ' | ')}`;
}

function formatHierarchyTreeRowLines(range: any): { line1: string; line2: string } {
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || '?';
  const scope = normalizeRangeScope(range?.range_scope);
  const id = range?.range_id || range?.id || '?';
  const start = rangeLabelStartDate(range);
  const end = rangeLabelEndDate(range);
  const statusPart = rangeStatusDirectionLabel(range);
  const high = Number(range?.range_high_price ?? range?.range_high);
  const low = Number(range?.range_low_price ?? range?.range_low);
  const rh = Number.isFinite(high) ? high.toFixed(2) : '?';
  const rl = Number.isFinite(low) ? low.toFixed(2) : '?';
  const parentId = range?.parent_range_id;
  const parentSuffix = parentId !== null && parentId !== undefined && String(parentId) !== ''
    ? ` · Parent #${parentId}`
    : '';
  return {
    line1: `${layer} ${scope} #${id} | ${start} → ${end} | ${statusPart}`,
    line2: `RH ${rh} / RL ${rl}${parentSuffix}`,
  };
}

function collectHierarchyBranchIds(nodes: CaseHierarchyTreeNode[]): string[] {
  const ids: string[] = [];
  const walk = (list: CaseHierarchyTreeNode[]) => {
    for (const node of list) {
      const id = String(node.range?.range_id || node.range?.id || '');
      if (id && node.children.length) ids.push(id);
      walk(node.children);
    }
  };
  walk(nodes);
  return ids;
}

type CaseHierarchyTreeNode = { range: any; depth: number; children: CaseHierarchyTreeNode[]; childCountLabel?: string | null };

function compareRangesByStartDate(a: any, b: any): number {
  const aMs = parseStructuralTimeMs(rangeLabelStartDate(a) === '?' ? null : rangeLabelStartDate(a)) ?? 0;
  const bMs = parseStructuralTimeMs(rangeLabelStartDate(b) === '?' ? null : rangeLabelStartDate(b)) ?? 0;
  return aMs - bMs || String(a?.range_id || a?.id).localeCompare(String(b?.range_id || b?.id));
}

function visibleStructuralRanges(rows: any[]): any[] {
  return safeArray(rows).filter((r:any) => String(r.status || '').toUpperCase() !== 'ARCHIVED');
}

function latestSavedRangeForLayer(layer: StructureLayer, ranges: any[], preferredId?: string, majorOnly = false): any | null {
  const all = safeArray(ranges);
  const layerMatch = (r: any) => {
    if (normalizeStructureLayer(r.structure_layer || r.layer) !== layer) return false;
    return !majorOnly || isRangeMajor(r);
  };
  if (preferredId) {
    const preferred = all.find((r:any) => String(r.range_id || r.id) === String(preferredId));
    if (preferred && layerMatch(preferred)) return preferred;
  }
  const layerRanges = all.filter(layerMatch).sort(compareRangesByStartDate);
  return layerRanges.length ? layerRanges[layerRanges.length - 1] : null;
}

function buildCaseHierarchyForest(ranges: any[]): { roots: CaseHierarchyTreeNode[]; orphans: any[] } {
  const nodes = safeArray(ranges);
  const byId = new Map(nodes.map((r:any) => [String(r.range_id || r.id), r]));
  const macroMajors = nodes.filter((r:any) =>
    normalizeStructureLayer(r.structure_layer || r.layer) === 'MACRO' && isRangeMajor(r),
  );
  const hasMacro = macroMajors.length > 0;
  const visited = new Set<string>();

  const buildTree = (r: any, depth: number): CaseHierarchyTreeNode => {
    const id = String(r.range_id || r.id);
    visited.add(id);
    const childRanges = directHierarchyChildren(r, nodes);
    const children = childRanges.map((c:any) => buildTree(c, depth + 1));
    return { range: r, depth, children, childCountLabel: hierarchyChildCountLabel(r, childRanges) };
  };

  const rootCandidates = hasMacro
    ? macroMajors
    : nodes.filter((r:any) => {
        const pid = r.parent_range_id;
        const isOrphanLink = pid === null || pid === undefined || String(pid) === '' || !byId.has(String(pid));
        return isOrphanLink && isRangeMajor(r);
      });

  const roots = rootCandidates.sort(compareRangesByStartDate).map((r:any) => buildTree(r, 0));
  const orphans = nodes.filter((r:any) => !visited.has(String(r.range_id || r.id))).sort(compareRangesByStartDate);
  return { roots, orphans };
}

function collectHierarchyPathIds(selectedId: string, allRanges: any[]): string[] {
  return collectParentContextChain(selectedId, allRanges).reverse();
}

/** Selected range + all ancestors up to root. */
function getContextStack(selectedRangeId: string, ranges: any[]): Set<string> {
  const path = new Set<string>();
  if (!selectedRangeId) return path;
  const byId = new Map<string, any>();
  for (const r of ranges) {
    const id = String(r.range_id || r.id || '');
    if (id) byId.set(id, r);
  }
  let current = byId.get(String(selectedRangeId));
  while (current) {
    const id = String(current.range_id || current.id || '');
    if (!id) break;
    path.add(id);
    const parentId = current.parent_range_id;
    current = parentId !== null && parentId !== undefined && String(parentId) !== ''
      ? byId.get(String(parentId))
      : null;
  }
  return path;
}

function getContextStackPathIds(selectedRangeId: string, ranges: any[]): string[] {
  if (!selectedRangeId) return [];
  return collectHierarchyPathIds(selectedRangeId, ranges);
}

function fallbackContextPathIds(allRanges: any[]): string[] {
  const rows = safeArray(allRanges);
  if (!rows.length) return [];
  const macros = rows
    .filter((r:any) => normalizeStructureLayer(r.structure_layer || r.layer) === 'MACRO')
    .sort(compareRangesByStartDate);
  if (macros.length) {
    const macro = macros[macros.length - 1];
    return collectHierarchyPathIds(String(macro.range_id || macro.id), rows);
  }
  const weeklies = rows
    .filter((r:any) => normalizeStructureLayer(r.structure_layer || r.layer) === 'WEEKLY')
    .sort(compareRangesByStartDate);
  if (weeklies.length) {
    const weekly = weeklies[weeklies.length - 1];
    return collectHierarchyPathIds(String(weekly.range_id || weekly.id), rows);
  }
  return [];
}

function structuralRangePaddingCandles(layer: StructureLayer | null, chartTf?: string): { before: number; after: number } {
  const base = (() => {
    if (layer === 'MACRO' || layer === 'WEEKLY') return 20;
    if (layer === 'DAILY') return 15;
    if (layer === 'INTRADAY') return 10;
    if (layer === 'MICRO') return 8;
    return 15;
  })();
  const tf = String(chartTf || 'D1').toUpperCase();
  if (tf === 'H1' || tf === 'H4') return { before: Math.max(base * 3, 36), after: Math.max(base, 12) };
  if (tf === 'M15' || tf === 'M5') return { before: Math.max(base * 2, 28), after: Math.max(base, 10) };
  return { before: Math.max(base * 2, 24), after: Math.max(base, 10) };
}

function structuralRangeFitPadRatio(layer: StructureLayer | null): number {
  if (layer === 'MACRO' || layer === 'WEEKLY') return 0.16;
  if (layer === 'DAILY') return 0.12;
  return 0.1;
}

function structuralRangeFitDomain(range: any, candles: Candle[], chartTf?: string): StructuralFitWindow | null {
  const hi = Number(range?.range_high_price ?? range?.range_high);
  const lo = Number(range?.range_low_price ?? range?.range_low);
  if (!Number.isFinite(hi) || !Number.isFinite(lo) || hi <= lo) return null;
  const layer = normalizeStructureLayer(range?.structure_layer || range?.layer);
  const status = String(range?.status || '').toUpperCase();
  const broken = status.includes('BROKEN');

  const timeCandidates = [
    range?.range_start_time,
    range?.active_from_time,
    range?.range_high_time,
    range?.range_low_time,
  ].map(parseStructuralTimeMs).filter((x): x is number => x !== null);
  let startMs = parseStructuralTimeMs(range?.range_start_time || range?.active_from_time || range?.range_high_time);
  let endMs = parseStructuralTimeMs(range?.range_end_time || range?.range_low_time);
  if (broken) {
    const inactiveMs = parseStructuralTimeMs(range?.inactive_from_time);
    if (inactiveMs !== null) endMs = endMs === null ? inactiveMs : Math.max(endMs, inactiveMs);
  }
  if (startMs === null && timeCandidates.length) startMs = Math.min(...timeCandidates);
  if (endMs === null && timeCandidates.length) endMs = Math.max(...timeCandidates);
  if (startMs === null) return null;
  if (endMs === null || endMs < startMs) {
    endMs = startMs + (layer === 'INTRADAY' || layer === 'MICRO' ? 6 * 3600 * 1000 : 7 * 24 * 3600 * 1000);
  }

  const pad = structuralRangePaddingCandles(layer, chartTf);
  let priceLow = lo;
  let priceHigh = hi;
  let startTime = new Date(startMs).toISOString();
  let endTime = new Date(endMs).toISOString();

  if (candles.length) {
    const startIdx = candleIndexAtOrBefore(candles, startTime);
    const endIdx = candleIndexAtOrAfter(candles, endTime);
    const padStart = Math.max(0, startIdx - pad.before);
    const padEnd = Math.min(candles.length - 1, endIdx + pad.after);
    startTime = candles[padStart]?.time || startTime;
    endTime = candles[padEnd]?.time || endTime;
    for (let i = padStart; i <= padEnd; i++) {
      const c = candles[i];
      if (!c) continue;
      priceLow = Math.min(priceLow, c.low);
      priceHigh = Math.max(priceHigh, c.high);
    }
  } else {
    const spanMs = Math.max(endMs - startMs, 1);
    const leftPadMs = Math.max(spanMs * 0.42, 3600 * 1000);
    const rightPadMs = Math.max(spanMs * 0.14, 3600 * 1000);
    startTime = new Date(startMs - leftPadMs).toISOString();
    endTime = new Date(endMs + rightPadMs).toISOString();
  }

  return {
    start: startTime,
    end: endTime,
    low: priceLow,
    high: priceHigh,
    padRatio: structuralRangeFitPadRatio(layer),
  };
}

function isIntradayChartTimeframe(tf: string): boolean {
  const t = String(tf || '').toUpperCase();
  return t === 'H4' || t === 'H1' || t === 'M15' || t === 'M5';
}

function resolveMappingContextRange(
  savedRanges: any[],
  selectedParentRangeId: string,
  activeStructuralRangeId: string,
): any | null {
  const all = safeArray(savedRanges);
  const byId = (id: string) => all.find((r:any) => String(r.range_id || r.id) === String(id)) || null;

  if (selectedParentRangeId) {
    const parent = byId(selectedParentRangeId);
    if (parent) return parent;
  }

  if (activeStructuralRangeId) {
    const active = byId(activeStructuralRangeId);
    const activeLayer = normalizeStructureLayer(active?.structure_layer || active?.layer);
    if (active) {
      if (activeLayer === 'DAILY' || activeLayer === 'WEEKLY' || activeLayer === 'MACRO') return active;
      if (activeLayer === 'INTRADAY' || activeLayer === 'MICRO') {
        const pid = active.parent_range_id;
        if (pid !== null && pid !== undefined && String(pid) !== '') {
          const parent = byId(String(pid));
          if (parent) return parent;
        }
      }
    }
    const pathIds = getContextStackPathIds(activeStructuralRangeId, all);
    for (let i = pathIds.length - 1; i >= 0; i--) {
      const row = byId(pathIds[i]);
      if (normalizeStructureLayer(row?.structure_layer || row?.layer) === 'DAILY') return row;
    }
    for (let i = pathIds.length - 1; i >= 0; i--) {
      const row = byId(pathIds[i]);
      if (normalizeStructureLayer(row?.structure_layer || row?.layer) === 'WEEKLY') return row;
    }
  }
  return null;
}

function structuralContextTargetTime(range: any): string | null {
  if (!range) return null;
  return String(
    range.range_start_time
    || range.active_from_time
    || range.range_high_time
    || range.range_low_time
    || '',
  ) || null;
}

function isoDay(value?: string | null): string | null {
  if (!value) return null;
  const d = new Date(String(value));
  if (!Number.isFinite(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

function todayIsoDay(): string {
  return new Date().toISOString().slice(0, 10);
}

function parseMt5TimeMs(value?: string | null): number | null {
  const ms = candleTimeMs(value);
  return Number.isFinite(ms) ? ms : null;
}

function resolveCandleLoadWindow(
  targetTf: string,
  savedRanges: any[],
  selectedParentRangeId: string,
  activeStructuralRangeId: string,
  rangeWindow: { start?: string; end?: string },
  options?: { liveTail?: boolean; preferredWindow?: { start?: string | null; end?: string | null } | null },
): { start: string; end: string; label: string } | null {
  const contextRange = resolveCandleWindowTargetRange(
    targetTf,
    savedRanges,
    activeStructuralRangeId,
    selectedParentRangeId,
  ) || resolveMappingContextRange(savedRanges, selectedParentRangeId, activeStructuralRangeId);
  if (contextRange) {
    const span = rangeWindowFieldsFromSavedRange(contextRange);
    const windows = resolveStructuralContextAndReplayWindows({
      rangeSpan: { start: span.start || span.end, end: span.end || span.start },
      chartTf: targetTf,
      structureLayer: contextRange?.structure_layer || contextRange?.layer,
      label: `${formatStructuralRangeOptionLabel(contextRange)} context`,
    });
    if (windows?.dataLoad) return windows.dataLoad;
  }
  return resolveStructuralCandleLoadWindow({
    rangeWindow,
    preferredWindow: options?.preferredWindow,
    liveTail: options?.liveTail,
    pinStructuralEnd: !!contextRange,
    contextFit: null,
  });
}

function candleWindowOverlapsRange(candles: Candle[], startRaw?: string | null, endRaw?: string | null): boolean {
  const ext = candleDataExtent(candles);
  if (!ext) return false;
  if (!startRaw || !endRaw) return true;
  const startMs = parseStructuralTimeMs(startRaw);
  const endMs = parseStructuralTimeMs(endRaw);
  if (startMs === null || endMs === null) return true;
  return endMs >= ext.startMs && startMs <= ext.endMs;
}

function normalizeCandleTime(raw: any): string {
  if (raw === null || raw === undefined) return '';
  const s = String(raw).trim();
  const mt5 = s.match(/^(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})/);
  if (mt5) return `${mt5[1]}-${mt5[2]}-${mt5[3]}T${mt5[4]}:${mt5[5]}:00.000Z`;
  if (/^\d{10,13}$/.test(s)) {
    const n = Number(s);
    const ms = n < 1e12 ? n * 1000 : n;
    return new Date(ms).toISOString();
  }
  if (s.includes('T')) return s.endsWith('Z') ? s : `${s}Z`;
  return s.replace(' ', 'T') + (s.includes('Z') ? '' : 'Z');
}

function candleTimeMs(value?: string | null): number {
  if (!value) return NaN;
  const iso = normalizeCandleTime(value);
  const ms = new Date(iso).getTime();
  return Number.isFinite(ms) ? ms : NaN;
}

function candleTimeDate(value?: string | null): Date {
  const ms = candleTimeMs(value);
  return Number.isFinite(ms) ? new Date(ms) : new Date(String(value || ''));
}

function buildCandleFetchUrl(symbol: string, tf: string, window?: { start?: string; end?: string } | null, refresh = false) {
  const params = new URLSearchParams({ symbol, timeframe: tf, limit: '8000' });
  if (window?.start) params.set('start', window.start);
  // Do not pass date-only end — SQL string compare treats 2026.06.04 as > 2026.06.12.
  // History tail is bounded by limit DESC; replay trims client-side.
  if (refresh) params.set('refresh', '1');
  return `${BASE_URL}/api/v1/candles?${params.toString()}`;
}

async function fetchJsonWithTimeout(url: string, timeoutMs = 45000): Promise<any> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

function parseCandleRows(raw: any[]): Candle[] {
  return safeArray(raw)
    .map((c:any)=>({
      ...c,
      time: normalizeCandleTime(c.time),
      open:Number(c.open),
      high:Number(c.high),
      low:Number(c.low),
      close:Number(c.close),
      volume:Number(c.volume||0),
    }))
    .filter((c:Candle)=>Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low) && Number.isFinite(c.close) && !!c.time);
}

function collectDirectChildRangeIds(selectedId: string, allRanges: any[]): string[] {
  return allRanges
    .filter((r:any) => String(r.parent_range_id || '') === String(selectedId))
    .map((r:any) => String(r.range_id || r.id));
}

function collectSiblingRangeIds(selectedId: string, allRanges: any[]): string[] {
  const row = allRanges.find((r:any) => String(r.range_id || r.id) === String(selectedId));
  if (!row) return [];
  const parentId = row.parent_range_id;
  if (parentId === null || parentId === undefined || String(parentId) === '') {
    const layer = normalizeStructureLayer(row.structure_layer || row.layer);
    return allRanges
      .filter((r:any) => normalizeStructureLayer(r.structure_layer || r.layer) === layer && String(r.range_id || r.id) !== String(selectedId))
      .map((r:any) => String(r.range_id || r.id));
  }
  return allRanges
    .filter((r:any) => String(r.parent_range_id || '') === String(parentId) && String(r.range_id || r.id) !== String(selectedId))
    .map((r:any) => String(r.range_id || r.id));
}

function countRangeDescendants(rangeId: string, allRanges: any[]): number {
  const direct = allRanges.filter((r:any) => String(r.parent_range_id || '') === String(rangeId));
  return direct.length + direct.reduce((sum, child) => sum + countRangeDescendants(String(child.range_id || child.id), allRanges), 0);
}

function parentLinkModeLabel(mode: ParentResolveMode): string {
  if (mode === 'date_containment') return 'Auto-linked by date containment';
  if (mode === 'single_candidate') return 'Auto-linked by date containment';
  if (mode === 'manual') return 'Parent from explorer';
  if (mode === 'multiple_matches') return 'Multiple parents — click one in Explorer';
  if (mode === 'no_match') return 'No parent linked yet';
  return 'No parent required';
}

function isRootStructuralLayer(layer: StructureLayer, rangeScope: RangeScope): boolean {
  return rangeScope === 'MAJOR' && (layer === 'MACRO' || layer === 'WEEKLY');
}

function structuralRangeDateFields(
  rhTime: string,
  rlTime: string,
  options?: { activeFromTime?: string | null },
) {
  const rhMs = parseStructuralTimeMs(rhTime);
  const rlMs = parseStructuralTimeMs(rlTime);
  const spanMs = [rhMs, rlMs].filter((x): x is number => x !== null);
  const start = spanMs.length ? new Date(Math.min(...spanMs)).toISOString() : null;
  const end = spanMs.length ? new Date(Math.max(...spanMs)).toISOString() : null;
  return {
    range_high_time: rhTime || null,
    range_low_time: rlTime || null,
    range_start_time: start,
    range_end_time: end,
    active_from_time: options?.activeFromTime || start,
  };
}

function resolveParentRangeIdForSave(
  layer: StructureLayer,
  rangeScope: RangeScope,
  selectedParentRangeId: string,
  savedRanges: any[],
  childSpan?: {
    range_high_time?: string | null;
    range_low_time?: string | null;
    active_from_time?: string | null;
    range_start_time?: string | null;
    range_end_time?: string | null;
  },
): ParentResolveResult {
  const parentLayer = rangeScope === 'MINOR' ? layer : expectedParentStructureLayer(layer);
  if (!parentLayer) {
    return { parentId: null, error: null, autoSelected: false, mode: 'none', matchIds: [], orphanWarning: null };
  }

  const candidates = parentLayerCandidates(layer, savedRanges, rangeScope);
  if (!candidates.length) {
    const orphanWarning = layer === 'WEEKLY' && rangeScope === 'MAJOR'
      ? null
      : `No ${parentLayer} MAJOR ranges in case. ${layer} ${rangeScope} will save as orphan.`;
    return { parentId: null, error: null, autoSelected: false, mode: 'no_match', matchIds: [], orphanWarning };
  }

  if (selectedParentRangeId && candidates.some((r:any) => String(r.range_id || r.id) === String(selectedParentRangeId))) {
    return {
      parentId: String(selectedParentRangeId),
      error: null,
      autoSelected: false,
      mode: 'manual',
      matchIds: [String(selectedParentRangeId)],
      orphanWarning: null,
    };
  }

  const childTimesMs = childDraftAnchorTimesMs(childSpan);
  const dateMatches = childTimesMs.length
    ? candidates.filter((p:any) => parentContainsChildByLifecycle(p, childTimesMs))
    : [];

  if (childTimesMs.length && dateMatches.length === 1) {
    const id = String(dateMatches[0].range_id || dateMatches[0].id);
    return { parentId: id, error: null, autoSelected: true, mode: 'date_containment', matchIds: [id], orphanWarning: null };
  }

  if (childTimesMs.length && dateMatches.length > 1) {
    return {
      parentId: null,
      error: `Multiple ${parentLayer} MAJOR parents match this date span. Select parent manually.`,
      autoSelected: false,
      mode: 'multiple_matches',
      matchIds: dateMatches.map((r:any) => String(r.range_id || r.id)),
      orphanWarning: null,
    };
  }

  if (childTimesMs.length && dateMatches.length === 0) {
    const orphanWarning = layer === 'WEEKLY' && rangeScope === 'MAJOR'
      ? `No ${parentLayer} MAJOR parent contains this date span. Weekly may save as orphan.`
      : `No ${parentLayer} MAJOR parent contains this date span. ${layer} ${rangeScope} orphan requires confirmation.`;
    return { parentId: null, error: null, autoSelected: false, mode: 'no_match', matchIds: [], orphanWarning };
  }

  if (!childTimesMs.length && candidates.length === 1) {
    const id = String(candidates[0].range_id || candidates[0].id);
    return { parentId: id, error: null, autoSelected: true, mode: 'single_candidate', matchIds: [id], orphanWarning: null };
  }

  if (!childTimesMs.length && candidates.length > 1) {
    return {
      parentId: null,
      error: `Set RH/RL dates or select ${parentLayer} MAJOR parent before saving ${layer} ${rangeScope} range.`,
      autoSelected: false,
      mode: 'multiple_matches',
      matchIds: candidates.map((r:any) => String(r.range_id || r.id)),
      orphanWarning: null,
    };
  }

  return {
    parentId: null,
    error: `Select ${parentLayer} MAJOR parent before saving ${layer} ${rangeScope} range.`,
    autoSelected: false,
    mode: 'multiple_matches',
    matchIds: candidates.map((r:any) => String(r.range_id || r.id)),
    orphanWarning: null,
  };
}

function structuralMappingScopeFields(structureLayer: StructureLayer, sourceTimeframe: string, chartTimeframe: string) {
  return {
    structure_layer: structureLayer,
    source_timeframe: sourceTimeframe,
    chart_timeframe: chartTimeframe,
  };
}

const STRUCTURAL_CHART_EVENT_TYPES = new Set([
  'BOS_UP',
  'BOS_DOWN',
  'RANGE_HIGH_SELECTED',
  'RANGE_LOW_SELECTED',
  'BREAK_HIGH_SELECTED',
  'BREAK_LOW_SELECTED',
]);

function isStructuralChartEventType(eventType: unknown): boolean {
  return STRUCTURAL_CHART_EVENT_TYPES.has(String(eventType || '').toUpperCase());
}

function mapStructuralEventRowToChartEvent(e: any): MapEvent | null {
  const eventType = String(e?.event_type || e?.structural_event || '').toUpperCase();
  const time = e?.event_time || e?.time || e?.candle_time;
  const price = parseNum(e?.event_price ?? e?.price ?? e?.break_level_price);
  if (!eventType || !time || !Number.isFinite(price)) return null;
  let meta_json = e?.meta_json;
  if (typeof meta_json === 'string') {
    try { meta_json = JSON.parse(meta_json); } catch { /* keep raw string */ }
  }
  return {
    id: String(e?.event_id || e?.client_event_id || e?.id),
    event_type: eventType,
    event_name: e?.event_name || eventType,
    time: String(time),
    price,
    notes: e?.notes || '',
    meta_json,
    case_id: e?.case_id,
    raw_case_id: e?.raw_case_id,
    case_ref: e?.case_ref,
  };
}

function mergeChartEventsById(existing: MapEvent[], incoming: MapEvent[]): MapEvent[] {
  const byId = new Map<string, MapEvent>();
  for (const row of existing) byId.set(String(row.id), row);
  for (const row of incoming) {
    const id = String(row.id);
    if (!byId.has(id)) byId.set(id, row);
  }
  return Array.from(byId.values());
}

function normalizeStructureLayer(value: any): StructureLayer | null {
  const raw = String(value || '').toUpperCase();
  const aliases: Record<string, StructureLayer> = {
    MN1:'MACRO', MACRO:'MACRO', W1:'WEEKLY', WEEKLY:'WEEKLY', D1:'DAILY', DAILY:'DAILY',
    H4:'INTRADAY', H1:'INTRADAY', INTRADAY:'INTRADAY', M15:'MICRO', M5:'MICRO', MICRO:'MICRO',
  };
  const layer = (aliases[raw] || raw) as StructureLayer;
  return STRUCTURE_LAYERS.includes(layer) ? layer : null;
}
function sourceTimeframeOptionsForLayer(layer: StructureLayer): string[] {
  if (layer === 'MACRO') return ['MN1', 'W1'];
  if (layer === 'WEEKLY') return ['W1'];
  if (layer === 'DAILY') return ['D1'];
  if (layer === 'INTRADAY') return ['H1', 'H4', 'H8'];
  return ['M15', 'M5'];
}
function chartLayerMismatchWarning(chartTf: string, mappingLayer: StructureLayer, sourceTimeframe?: string): string {
  const chartTfUpper = String(chartTf || '').toUpperCase();
  const sourceTfUpper = String(sourceTimeframe || '').toUpperCase();
  if (mappingLayer === 'MACRO') {
    const macroSources = sourceTimeframeOptionsForLayer('MACRO');
    if (macroSources.includes(sourceTfUpper) && chartTfUpper === sourceTfUpper) return '';
    if (isChartTimeframeAllowedForLayer(chartTfUpper, 'MACRO')) return '';
  }
  if (isChartTimeframeAllowedForLayer(chartTfUpper, mappingLayer)) return '';
  const expected = allowedChartTimeframesForStructureLayer(mappingLayer).join(' or ');
  return `Chart is ${chartTfUpper} but scope is ${mappingLayer}. Switch chart to ${expected} to plot RH/RL.`;
}
function chartStructureForTimeframeStatic(tfRaw:string) {
  const tf = String(tfRaw || 'D1').toUpperCase();
  if (tf === 'MN1') return { structure_layer:'MACRO' as StructureLayer, source_timeframe:'MN1' };
  if (tf === 'W1') return { structure_layer:'WEEKLY' as StructureLayer, source_timeframe:'W1' };
  if (tf === 'D1') return { structure_layer:'DAILY' as StructureLayer, source_timeframe:'D1' };
  if (tf === 'H4') return { structure_layer:'INTRADAY' as StructureLayer, source_timeframe:'H4' };
  if (tf === 'H1') return { structure_layer:'INTRADAY' as StructureLayer, source_timeframe:'H1' };
  if (tf === 'M15' || tf === 'M5') return { structure_layer:'MICRO' as StructureLayer, source_timeframe: tf };
  return { structure_layer:'WEEKLY' as StructureLayer, source_timeframe:tf };
}

type SavedRangeChartLine = {
  rangeId: string;
  structureLayer: StructureLayer;
  rangeScope: RangeScope;
  status: string;
  high: number;
  low: number;
  start?: string | null;
  end?: string | null;
  isActive?: boolean;
  isParentContext?: boolean;
  focusTier?: FocusOverlayTier;
};

type DraftRangeChartLine = {
  high: number | null;
  low: number | null;
  structureLayer: StructureLayer;
  visible: boolean;
  start?: string | null;
  end?: string | null;
};

function collectParentContextChain(startRangeId: string, allRanges: any[]): string[] {
  const ids: string[] = [];
  const seen = new Set<string>();
  let currentId = startRangeId ? String(startRangeId) : '';
  while (currentId) {
    if (seen.has(currentId)) break;
    seen.add(currentId);
    ids.push(currentId);
    const row = allRanges.find((r:any) => String(r.range_id || r.id) === currentId);
    if (!row) break;
    const parentId = row.parent_range_id;
    if (parentId === null || parentId === undefined || String(parentId) === '') break;
    currentId = String(parentId);
  }
  return ids;
}

/** Chart overlays: active range + direct parent only — hide grandparent chain when mapping child. */
function chartVisibleRangeIds(
  allRanges: any[],
  activeStructuralRangeId: string,
  selectedParentRangeId: string,
): Set<string> {
  const allowed = new Set<string>();
  const activeId = String(activeStructuralRangeId || '');
  const parentId = String(selectedParentRangeId || '');
  if (activeId) allowed.add(activeId);
  if (parentId) allowed.add(parentId);
  if (activeId && !parentId) {
    const row = allRanges.find((r:any) => String(r.range_id || r.id) === activeId);
    const pid = row?.parent_range_id;
    if (pid !== null && pid !== undefined && String(pid) !== '') allowed.add(String(pid));
  }
  return allowed;
}

function structuralRangeToChartLine(
  r: any,
  activeStructuralRangeId: string,
  opts?: { isParentContext?: boolean },
): SavedRangeChartLine | null {
  const hi = Number(r.range_high_price ?? r.range_high);
  const lo = Number(r.range_low_price ?? r.range_low);
  const rangeId = String(r.range_id || r.id || '');
  const layer = normalizeStructureLayer(r.structure_layer || r.layer);
  if (!rangeId || !layer || !Number.isFinite(hi) || !Number.isFinite(lo) || hi <= lo) return null;
  return {
    rangeId,
    structureLayer: layer,
    rangeScope: normalizeRangeScope(r.range_scope),
    status: String(r.status || 'ACTIVE').toUpperCase(),
    high: hi,
    low: lo,
    start: r.range_start_time || r.range_high_time || null,
    end: r.range_end_time || r.range_low_time || null,
    isActive: rangeId === String(activeStructuralRangeId),
    isParentContext: !!opts?.isParentContext,
  };
}

function structureLayerRank(layer: StructureLayer): number {
  return STRUCTURE_LAYERS.indexOf(layer);
}

type StructuralAnchor = { price:string; time:string; candle?:Candle|null };
type LayerAnchorPair = { rh: StructuralAnchor; rl: StructuralAnchor };
type StructuralRange = {
  range_id?:number|string;
  id?:number|string;
  case_id?:number|string|null;
  symbol?:string;
  structure_layer?:string;
  chart_timeframe?:string;
  source_timeframe?:string;
  parent_range_id?:number|string|null;
  range_scope?:string;
  parent_link_status?:string;
  range_high_price?:number|string|null;
  range_low_price?:number|string|null;
  range_high_time?:string;
  range_low_time?:string;
  range_start_time?:string;
  range_end_time?:string;
  status?:string;
};

type HTFCandidate = { id:string; event_type:string; label:string; price:number; time:string; candle:Candle; priceMode:'high'|'low'|'close'; confidence:'LOW'|'MEDIUM'|'HIGH'; reason:string; primitive:string; derived_event_code:string; movement_rule:string; range_status_after?:string; meta:any; status?:'CANDIDATE'|'ACCEPTED'|'REJECTED'|'EDITED' };

type GpsCoordinates = { story_anchor:string; anchor_class?:string; chapter:string; parent_context_mode?:string; daily_range_status?:string; lifecycle_state?:string; phase:string; phase_part:string; profile_type?:string; objective:string; current_zone:string; last_updated?:string };
type TimelineNode = { kind:string; label:string; anchor_class?:string; timeframe?:string; phase?:string; phase_part?:string; direction?:string; objective?:string; current_zone?:string; time?:string; price?:number; active?:boolean };
type GpsPayload = { ok?:boolean; status?:string; symbol?:string; timeframe?:string; coordinates?:GpsCoordinates|null };
type PlaybackFrame = { frame_index:number; id:number; story_id:number; frame_timestamp:string; parent_context_mode:string; daily_range_status:string; lifecycle_state:string; phase:string; profile_type:string; objective_code:string; current_zone:string; established_price:number; trigger_event:string; expected_next_event:string; invalidation_condition:string; lookahead_result?:string };
const MAP_TIMEFRAMES = ['MN1','W1','D1','H4','H1','M15'];
const CHART_TIMEFRAME_ORDER = ['MN1', 'W1', 'D1', 'H4', 'H1', 'M15', 'M5'] as const;

function chartTimeframeRank(tf: string): number {
  const i = CHART_TIMEFRAME_ORDER.indexOf(String(tf || '').toUpperCase() as typeof CHART_TIMEFRAME_ORDER[number]);
  return i >= 0 ? i : CHART_TIMEFRAME_ORDER.length;
}

function isDrillingDownTimeframe(fromTf: string, toTf: string): boolean {
  return chartTimeframeRank(toTf) > chartTimeframeRank(fromTf);
}

type CaseScope = 'MACRO'|'WEEKLY'|'DAILY'|'INTRADAY'|'MICRO';
function scopeToTimeframe(scope: CaseScope) { return ({ MACRO:'MN1', WEEKLY:'W1', DAILY:'D1', INTRADAY:'H1', MICRO:'M15' } as Record<CaseScope,string>)[scope] || 'D1'; }
function timeframeToScope(tf:string): CaseScope { const t=String(tf||'').toUpperCase(); if (t==='MN1') return 'MACRO'; if (t==='W1') return 'WEEKLY'; if (t==='D1') return 'DAILY'; if (t==='M15') return 'MICRO'; return 'INTRADAY'; }
function scopeLabel(scope: CaseScope) { return ({ MACRO:'Macro', WEEKLY:'Weekly', DAILY:'Daily', INTRADAY:'Intraday', MICRO:'Micro / 15m' } as Record<CaseScope,string>)[scope] || scope; }
const MAP_EVENT_TYPES = ['BOS_UP','BOS_DOWN','CHOCH_UP','CHOCH_DOWN','P1_RETEST','P1_BOS','P2_RETEST','P2_BOS','INTERNAL_SWEEP','EXTERNAL_SWEEP','INTERNAL_REJECTION_LOW','INTERNAL_REJECTION_HIGH','EXTREME_DISCOUNT_LOW','BELOW_FAIR_PRICE_LOW','ABOVE_FAIR_PRICE_HIGH','EXTREME_PREMIUM_HIGH','RECLAIM_HIGH','RECLAIM_LOW','SFD','DFS','INDUCEMENT','OBJECTIVE_HIT','RANGE_ABANDONED','NEW_RANGE','CUSTOM_INTERNAL'];

const MARKER_LIBRARY = {
  macro: [
    { title: 'Macro Range Anchors', items: [
      ['SET_MACRO_RANGE_HIGH','Set M High'], ['SET_MACRO_RANGE_LOW','Set M Low'],
    ]},
    { title: 'Macro Locations', items: [
      ['MACRO_EXTERNAL_HIGH','M Ext H'], ['MACRO_EXTERNAL_LOW','M Ext L'],
      ['MACRO_EXTREME_PREMIUM','M Ex Prem'], ['MACRO_EXTREME_DISCOUNT','M Ex Disc'],
      ['MACRO_ABOVE_FP','M Above FP'], ['MACRO_FAIR_PRICE','M FP'], ['MACRO_BELOW_FP','M Below FP'],
    ]},
  ],
  weekly: [
    { title: 'Weekly Range Anchors', items: [
      ['SET_WEEKLY_RANGE_HIGH','Set W High'], ['SET_WEEKLY_RANGE_LOW','Set W Low'],
    ]},
    { title: 'Weekly Locations', items: [
      ['WEEKLY_EXTERNAL_HIGH','W Ext H'], ['WEEKLY_EXTERNAL_LOW','W Ext L'],
      ['WEEKLY_EXTREME_PREMIUM','W Ex Prem'], ['WEEKLY_EXTREME_DISCOUNT','W Ex Disc'],
      ['WEEKLY_ABOVE_FP','W Above FP'], ['WEEKLY_FAIR_PRICE','W FP'], ['WEEKLY_BELOW_FP','W Below FP'],
    ]},
    { title: 'Weekly Reference Liquidity', items: [
      ['WEEKLY_PWH_REFERENCE','PWH Ref'], ['WEEKLY_PWL_REFERENCE','PWL Ref'],
      ['WEEKLY_PWH_SWEEP_REF_CANDLE','PWH Sweep Ref'], ['WEEKLY_PWL_SWEEP_REF_CANDLE','PWL Sweep Ref'],
      ['WEEKLY_NO_SWEEP_REF_CANDLE','W No Sweep Ref'],
    ]},
    { title: 'Weekly Events', items: [
      ['WEEKLY_REF_HIGH_ACTIVE','W Ref H'], ['WEEKLY_REF_LOW_ACTIVE','W Ref L'],
      ['WEEKLY_BOS_UP','W BOS ↑'], ['WEEKLY_BOS_DOWN','W BOS ↓'],
      ['WEEKLY_RECLAIM_REF_HIGH','W Rec Ref H'], ['WEEKLY_RECLAIM_REF_LOW','W Rec Ref L'],
      ['WEEKLY_RANGE_CONFIRMED_AFTER_BOS_UP','W Range ↑'], ['WEEKLY_RANGE_CONFIRMED_AFTER_BOS_DOWN','W Range ↓'],
      ['WEEKLY_RANGE_ABANDONED_UP','W Aband ↑'], ['WEEKLY_RANGE_ABANDONED_DOWN','W Aband ↓'],
      ['WEEKLY_CURRENT_HIGH_FORMED','W Cur H'], ['WEEKLY_CURRENT_LOW_FORMED','W Cur L'],
      ['WEEKLY_EXTERNAL_REVERSAL_ZONE','W Ext Rev Zone'], ['WEEKLY_EXTREME_REVERSAL_ZONE','W Extreme Rev Zone'],
    ]},
    { title: 'Weekly Profile', items: [
      ['PROFILE_SD_DEEP','S&D Deep'], ['PROFILE_SR_SHALLOW','S&R Shallow'], ['PROFILE_ABANDON_NO_RECLAIM','Abandon / No Reclaim'],
    ]},
    { title: 'Weekly Retracement', items: [
      ['RETRACEMENT_0_MINUS','0-'], ['RETRACEMENT_0_25','0-25'], ['RETRACEMENT_25_50','25-50'],
      ['RETRACEMENT_50_75','50-75'], ['RETRACEMENT_75_100','75-100'], ['RETRACEMENT_100_PLUS','100+'],
    ]},
  ],
  daily: [
    { title: 'Daily Range Anchors', items: [
      ['SET_DAILY_RANGE_HIGH','Set D High'], ['SET_DAILY_RANGE_LOW','Set D Low'],
    ]},
    { title: 'Daily Locations', items: [
      ['DAILY_EXTERNAL_HIGH','D Ext H'], ['DAILY_EXTERNAL_LOW','D Ext L'],
      ['DAILY_EXTREME_PREMIUM','D Ex Prem'], ['DAILY_EXTREME_DISCOUNT','D Ex Disc'],
      ['DAILY_ABOVE_FP','D Above FP'], ['DAILY_FAIR_PRICE','D FP'], ['DAILY_BELOW_FP','D Below FP'],
    ]},
    { title: 'Daily Reference Structure', items: [
      ['DAILY_REF_HIGH_ACTIVE','D Ref H'], ['DAILY_REF_LOW_ACTIVE','D Ref L'],
    ]},
    { title: 'A+ Reference Liquidity', items: [
      ['DAILY_PDH_REFERENCE','PDH Ref'], ['DAILY_PDL_REFERENCE','PDL Ref'],
      ['DAILY_PDH_SWEEP_REF_CANDLE','PDH Sweep Ref'], ['DAILY_PDL_SWEEP_REF_CANDLE','PDL Sweep Ref'],
      ['DAILY_NO_SWEEP_REF_CANDLE','No Sweep Ref'],
    ]},
    { title: 'Daily Phase', items: [
      ['PRE_CHOCH','Pre-CHoCH'], ['CHOCH_UP','CHoCH ↑'], ['CHOCH_DOWN','CHoCH ↓'],
      ['P1_RETEST','P1 Retest'], ['P1_BOS','P1 BOS'],
      ['P2_RETEST','P2 Retest'], ['P2_BOS','P2 BOS'],
      ['P3_RETEST','P3 Retest'], ['P3_FAIL','P3 Fail'],
      ['PC_CONTINUATION','PC Continuation'], ['CONTINUATION','Continuation'], ['RANGE_ABANDONED','Range Abandoned'],
    ]},
    { title: 'Daily Profile', items: [
      ['PROFILE_SD_DEEP','S&D Deep'], ['PROFILE_SR_SHALLOW','S&R Shallow'], ['PROFILE_ABANDON_NO_RECLAIM','Abandon / No Reclaim'], ['DAILY_PROFILE_CHANGE','Profile Change'],
    ]},
    { title: 'Responsible Point', items: [
      ['RESPONSIBLE_HIGH','Responsible H'], ['RESPONSIBLE_LOW','Responsible L'],
    ]},
    { title: 'Daily Range State', items: [
      ['DAILY_RANGE_CONFIRMED_AFTER_BOS_UP','D Range ↑'], ['DAILY_RANGE_CONFIRMED_AFTER_BOS_DOWN','D Range ↓'],
      ['DAILY_RANGE_ABANDONED_UP','D Aband ↑'], ['DAILY_RANGE_ABANDONED_DOWN','D Aband ↓'], ['DAILY_CURRENT_HIGH_FORMED','D Cur H'], ['DAILY_CURRENT_LOW_FORMED','D Cur L'], ['DAILY_OBJECTIVE_COMPLETE','Objective Done'],
    ]},
  ],
} as const;

const MARKER_LABELS: Record<string,string> = Object.fromEntries(
  Object.values(MARKER_LIBRARY).flat().flatMap((group:any)=>group.items.map(([code,label]:any)=>[code,label]))
);

function markerLabel(type?: string) {
  const key = String(type || '').toUpperCase();
  return MARKER_LABELS[key] || key.replace(/_/g, ' ');
}




function isExplicitRangeHighCommand(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['SET_MACRO_RANGE_HIGH', 'SET_WEEKLY_RANGE_HIGH', 'SET_DAILY_RANGE_HIGH', 'RANGE_HIGH'].includes(t);
}

function isExplicitRangeLowCommand(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['SET_MACRO_RANGE_LOW', 'SET_WEEKLY_RANGE_LOW', 'SET_DAILY_RANGE_LOW', 'RANGE_LOW'].includes(t);
}

function isRangeHighMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  // v086.11: Fib anchors must be explicit anchor commands only.
  // Structure/location events can describe the candle, but they must not steal the fib range.
  // This prevents old W/D current-high/current-low events from dragging the active fibs away
  // from the exact selected-candle high/low Josh just marked. Precision over cleverness.
  return [
    'RANGE_HIGH',
    'SET_MACRO_RANGE_HIGH', 'SET_WEEKLY_RANGE_HIGH', 'SET_DAILY_RANGE_HIGH'
  ].includes(t);
}

function isRangeLowMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  // Explicit only. If a current low/high should become the active range anchor, queue
  // Set M/W/D Low or Set M/W/D High on that same candle. No silent range theft.
  return [
    'RANGE_LOW',
    'SET_MACRO_RANGE_LOW', 'SET_WEEKLY_RANGE_LOW', 'SET_DAILY_RANGE_LOW'
  ].includes(t);
}

function isRefHighMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['REF_HIGH_TAKEN','WEEKLY_REF_HIGH_ACTIVE','WEEKLY_PWH_REFERENCE','DAILY_REF_HIGH_ACTIVE','DAILY_PDH_REFERENCE'].includes(t);
}

function isRefLowMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['REF_LOW_TAKEN','WEEKLY_REF_LOW_ACTIVE','WEEKLY_PWL_REFERENCE','DAILY_REF_LOW_ACTIVE','DAILY_PDL_REFERENCE'].includes(t);
}

function isRangeAnchorMarker(type?: string) {
  return isRangeHighMarker(type) || isRangeLowMarker(type);
}


function eventMs(ev?: MapEvent) {
  const ms = ev?.time ? new Date(String(ev.time)).getTime() : 0;
  return Number.isFinite(ms) ? ms : 0;
}

function latestByEventTime(items: MapEvent[]) {
  if (!items.length) return undefined;
  return [...items].sort((a:any,b:any) => eventMs(b) - eventMs(a) || String(b.id || '').localeCompare(String(a.id || '')))[0];
}

function latestRangeHighEvent(events: MapEvent[] = []) {
  const list = safeArray<MapEvent>(events);
  const explicit = list.filter(e => ['SET_MACRO_RANGE_HIGH','SET_WEEKLY_RANGE_HIGH','SET_DAILY_RANGE_HIGH'].includes(String(e?.event_type || '').toUpperCase()));
  if (explicit.length) return latestByEventTime(explicit);
  return latestByEventTime(list.filter(e => isRangeHighMarker(e?.event_type)));
}

function latestRangeLowEvent(events: MapEvent[] = []) {
  const list = safeArray<MapEvent>(events);
  const explicit = list.filter(e => ['SET_MACRO_RANGE_LOW','SET_WEEKLY_RANGE_LOW','SET_DAILY_RANGE_LOW'].includes(String(e?.event_type || '').toUpperCase()));
  if (explicit.length) return latestByEventTime(explicit);
  return latestByEventTime(list.filter(e => isRangeLowMarker(e?.event_type)));
}

function markerPriceMode(type:string): 'high'|'low'|'close' {
  const t = String(type || '').toUpperCase();
  if (t.includes('LOW') || t.includes('DISCOUNT') || t.includes('BELOW') || t.includes('PDL') || t.includes('DOWN') || t.includes('RESPONSIBLE_LOW')) return 'low';
  if (t.includes('HIGH') || t.includes('PREMIUM') || t.includes('ABOVE') || t.includes('PDH') || t.includes('UP') || t.includes('RESPONSIBLE_HIGH')) return 'high';
  return 'close';
}

function safeArray<T = any>(value: any): T[] {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}


function markerGroupsForTimeframe(tf:string) {
  const t = String(tf || '').toUpperCase();
  if (t === 'MN1') return [{ title:'Macro Context', defaultOpen:true, groups: MARKER_LIBRARY.macro }];
  if (t === 'W1') return [
    { title:'Macro Context', defaultOpen:false, groups: MARKER_LIBRARY.macro },
    { title:'Weekly Structure', defaultOpen:true, groups: MARKER_LIBRARY.weekly },
  ];
  if (t === 'D1') return [
    { title:'Macro Context', defaultOpen:false, groups: MARKER_LIBRARY.macro },
    { title:'Weekly Context', defaultOpen:false, groups: MARKER_LIBRARY.weekly },
    { title:'Daily Narrative', defaultOpen:true, groups: MARKER_LIBRARY.daily },
  ];
  return [
    { title:'Daily Narrative', defaultOpen:true, groups: MARKER_LIBRARY.daily },
  ];
}
const STORY_ANCHOR_OPTIONS = [
  'WEEKLY_REF_LOW_TAKEN','WEEKLY_REF_HIGH_TAKEN',
  'WEEKLY_DISCOUNT_REJECTION','WEEKLY_EXTREME_DISCOUNT_REJECTION','WEEKLY_EXTERNAL_LOW_REJECTION',
  'WEEKLY_PREMIUM_REJECTION','WEEKLY_EXTREME_PREMIUM_REJECTION','WEEKLY_EXTERNAL_HIGH_REJECTION',
  'DAILY_REF_LOW_TAKEN','DAILY_REF_HIGH_TAKEN','WEEKLY_CHOCH_UP','WEEKLY_CHOCH_DOWN'
];
function anchorClassLabel(anchor?: string) {
  const txt = String(anchor || '').toUpperCase();
  if (txt.includes('REF_') && txt.includes('TAKEN')) return 'LIQUIDITY';
  if (txt.includes('REJECTION')) return 'REJECTION';
  if (txt.includes('CHOCH') || txt.includes('BOS')) return 'STRUCTURE';
  return 'MANUAL';
}



function shortTime(value: any, timeframe?: string): string {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const tf = String(timeframe || '').toUpperCase();
  const y = date.getFullYear();
  const mo = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  if (tf === 'MN1') return `${y}-${mo}`;
  if (tf === 'W1' || tf === 'D1') return `${y}-${mo}-${day}`;
  const h = String(date.getHours()).padStart(2, '0');
  const mi = String(date.getMinutes()).padStart(2, '0');
  return `${y}-${mo}-${day} ${h}:${mi}`;
}


function eventMeta(ev:any) {
  try { return typeof ev?.meta_json === 'string' ? JSON.parse(ev.meta_json) : (ev?.meta_json || {}); } catch { return ev?.meta_json || {}; }
}
function isRejectedCandidateEvent(ev:any) {
  const m = eventMeta(ev);
  return String(m?.candidate_status || ev?.candidate_status || '').toUpperCase() === 'REJECTED'
    || String(ev?.event_type || '').toUpperCase().includes('REJECTED')
    || String(ev?.event_name || '').toUpperCase().startsWith('REJECTED:');
}
function isAcceptedCandidateEvent(ev:any) {
  const m = eventMeta(ev);
  return !!m?.accepted_from_candidate || String(ev?.engine_source || '').toUpperCase().includes('HTF');
}
function caseIdOfEvent(ev:any) {
  const m = eventMeta(ev);
  return ev?.case_id ?? m?.case_id ?? null;
}
function eventInWindow(ev:any, start?:string, end?:string) {
  if (!ev?.time || !start || !end) return false;
  const ms = new Date(String(ev.time)).getTime();
  const a = new Date(String(start)).getTime();
  const b = new Date(String(end)).getTime();
  if (![ms,a,b].every(Number.isFinite)) return false;
  return ms >= Math.min(a,b) && ms <= Math.max(a,b);
}

function zonePercent(price:number, low:number, high:number) {
  if (!Number.isFinite(price) || !Number.isFinite(low) || !Number.isFinite(high) || high === low) return null;
  return ((price - low) / (high - low)) * 100;
}
function zoneLabel(percent:number|null) {
  if (percent === null || !Number.isFinite(percent)) return '-';
  // Josh range language v059:
  // <0 = External Low, 0-25 = Extreme Discount, 25-35 = Discount,
  // 35-48 = Below Fair Price, 48-56 = Fair Price,
  // 56-75 = Premium, 75-100 = Extreme Premium, >100 = External High.
  if (percent < 0) return 'External Low';
  if (percent <= 25) return 'Extreme Discount';
  if (percent <= 35) return 'Discount';
  if (percent < 48) return 'Below Fair Price';
  if (percent <= 56) return 'Fair Price';
  if (percent < 75) return 'Premium';
  if (percent <= 100) return 'Extreme Premium';
  return 'External High';
}

function prefixForTimeframe(tf:string) {
  const t = String(tf || '').toUpperCase();
  if (t === 'MN1') return 'MACRO';
  if (t === 'W1') return 'WEEKLY';
  if (t === 'D1') return 'DAILY';
  return 'HTF';
}
function isHTFTimeframe(tf:string) {
  return ['MN1','W1','D1'].includes(String(tf || '').toUpperCase());
}
function candleDirection(c?:Candle|null) {
  if (!c) return 'NONE';
  if (Number(c.close) > Number(c.open)) return 'BULLISH';
  if (Number(c.close) < Number(c.open)) return 'BEARISH';
  return 'DOJI';
}
function candleBodyPct(c:Candle) {
  const r = Math.max(0.000001, Number(c.high) - Number(c.low));
  return Math.abs(Number(c.close) - Number(c.open)) / r;
}
function candidateIdFor(tf:string, c:Candle, code:string) {
  return `${tf}_${String(c.time).replace(/[^0-9A-Za-z]+/g,'')}_${code}`;
}
function htfRangeFingerprint(tf:string, rangeLow:number, rangeHigh:number) {
  const lo = Number.isFinite(rangeLow) ? Number(rangeLow).toFixed(2) : 'NA';
  const hi = Number.isFinite(rangeHigh) ? Number(rangeHigh).toFixed(2) : 'NA';
  return `${String(tf || '').toUpperCase()}_${lo}_${hi}`;
}
function htfSuggestionLockKey(tf:string, rangeLow:number, rangeHigh:number, movementRule?:string, side?:string) {
  return `${htfRangeFingerprint(tf, rangeLow, rangeHigh)}_${String(movementRule || 'UNKNOWN').toUpperCase()}_${String(side || 'ANY').toUpperCase()}`;
}
function htfCandidateLockKey(cand:Pick<HTFCandidate,'movement_rule'|'meta'|'derived_event_code'>, tf:string, rangeLow:number, rangeHigh:number) {
  const meta:any = cand?.meta || {};
  const side = meta?.breach_side || meta?.reclaim_side || meta?.sweep_side || meta?.ref_direction || meta?.point_role || meta?.rebase_direction || cand?.derived_event_code || 'ANY';
  return htfSuggestionLockKey(tf, rangeLow, rangeHigh, cand?.movement_rule, side);
}
function latestPriorZoneCandle(candles:Candle[], idx:number, side:'HIGH'|'LOW', low:number, high:number, lookback=8) {
  const start = Math.max(0, idx - lookback);
  for (let i = idx - 1; i >= start; i--) {
    const c = candles[i];
    const pct = side === 'HIGH' ? zonePercent(c.high, low, high) : zonePercent(c.low, low, high);
    if (pct === null) continue;
    if (side === 'HIGH' && pct >= 75) return { candle:c, index:i, pct };
    if (side === 'LOW' && pct <= 25) return { candle:c, index:i, pct };
  }
  return null;
}
function eventRangeMatches(e:any, rangeLow:number, rangeHigh:number, tolerancePct=0.0025) {
  const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
  const eh = Number(meta?.range_high);
  const el = Number(meta?.range_low);
  if (!Number.isFinite(eh) || !Number.isFinite(el)) return true; // legacy/manual event: do not falsely ignore it
  const tol = Math.max(0.01, Math.abs(rangeHigh - rangeLow) * tolerancePct);
  return Math.abs(eh - rangeHigh) <= tol && Math.abs(el - rangeLow) <= tol;
}
function acceptedEventHas(events:any[], rangeLow:number, rangeHigh:number, tester:(e:any, meta:any)=>boolean) {
  return safeArray<any>(events).some((e:any) => {
    const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
    const hydrated = { ...meta, movement_rule:e?.movement_rule || meta?.movement_rule, derived_event_code:e?.derived_event_code || meta?.derived_event_code, range_status_after:e?.range_status_after || meta?.range_status_after, primitive:e?.primitive || meta?.primitive };
    return eventRangeMatches(e, rangeLow, rangeHigh) && tester(e, hydrated);
  });
}
function eventRangeMatchesStrict(e:any, rangeLow:number, rangeHigh:number, tolerancePct=0.0025) {
  const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
  const eh = Number(meta?.range_high);
  const el = Number(meta?.range_low);
  // v087.13: structural chains must be ledger-backed HTF events, not legacy/manual ghosts.
  if (!Number.isFinite(eh) || !Number.isFinite(el)) return false;
  const tol = Math.max(0.01, Math.abs(rangeHigh - rangeLow) * tolerancePct);
  return Math.abs(eh - rangeHigh) <= tol && Math.abs(el - rangeLow) <= tol;
}
function acceptedHTFEventHas(events:any[], rangeLow:number, rangeHigh:number, tester:(e:any, meta:any)=>boolean) {
  return safeArray<any>(events).some((e:any) => {
    const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
    const hydrated = { ...meta, movement_rule:e?.movement_rule || meta?.movement_rule, derived_event_code:e?.derived_event_code || meta?.derived_event_code, range_status_after:e?.range_status_after || meta?.range_status_after, primitive:e?.primitive || meta?.primitive };
    const src = String(e?.engine_source || hydrated?.engine_source || '').toUpperCase();
    const hasRule = !!String(e?.movement_rule || hydrated?.movement_rule || '').trim();
    return eventRangeMatchesStrict(e, rangeLow, rangeHigh) && (src.includes('HTF') || hasRule) && tester(e, hydrated);
  });
}
function zoneWatchActive(candles:Candle[], idx:number, side:'HIGH'|'LOW', low:number, high:number, lookback=24) {
  const start = Math.max(0, idx - lookback);
  let watchStart = -1;
  for (let i = start; i < idx; i++) {
    const c = candles[i];
    const pct = side === 'HIGH' ? zonePercent(c.high, low, high) : zonePercent(c.low, low, high);
    if (pct === null) continue;
    if (side === 'HIGH' && (pct >= 75 || c.high > high)) watchStart = watchStart < 0 ? i : watchStart;
    if (side === 'LOW' && (pct <= 25 || c.low < low)) watchStart = watchStart < 0 ? i : watchStart;
  }
  if (watchStart < 0) return null;
  const active = candles[idx];
  // Pre-ref/setup candle increments forward while the zone cycle remains active.
  // For bearish confirmation, use the latest non-bearish setup candle since the premium watch started.
  // For bullish confirmation, use the latest non-bullish setup candle since the discount watch started.
  let pre:any = null, preIdx = -1;
  for (let i = watchStart; i < idx; i++) {
    const c = candles[i];
    const dir = candleDirection(c);
    if (side === 'HIGH' && dir !== 'BEARISH') { pre = c; preIdx = i; }
    if (side === 'LOW' && dir !== 'BULLISH') { pre = c; preIdx = i; }
  }
  // Fallback to immediate prior if all candles in the watch are already the confirmation colour.
  if (!pre && idx > 0) { pre = candles[idx - 1]; preIdx = idx - 1; }
  return pre ? { candle:pre, index:preIdx, watchStart } : null;
}
function acceptedEventByRule(events:any[], rangeLow:number, rangeHigh:number, rule:string) {
  const wanted = String(rule || '').toUpperCase();
  return acceptedEventHas(events, rangeLow, rangeHigh, (e,m) => String(e?.movement_rule || m?.movement_rule || '').toUpperCase() === wanted);
}
function acceptedEventByDerived(events:any[], rangeLow:number, rangeHigh:number, derived:string) {
  const wanted = String(derived || '').toUpperCase();
  return acceptedEventHas(events, rangeLow, rangeHigh, (e,m) => String(e?.derived_event_code || e?.event_type || m?.derived_event_code || '').toUpperCase() === wanted);
}
function eventRule(e:any, m:any) { return String(e?.movement_rule || m?.movement_rule || '').toUpperCase(); }
function eventDerived(e:any, m:any) { return String(e?.derived_event_code || e?.event_type || m?.derived_event_code || '').toUpperCase(); }
function findFirstBreachIndex(candles:Candle[], endIdx:number, side:'UP'|'DOWN', rangeLow:number, rangeHigh:number) {
  for (let i = 0; i <= endIdx; i++) {
    const c = candles[i];
    if (side === 'UP' && c.high > rangeHigh) return i;
    if (side === 'DOWN' && c.low < rangeLow) return i;
  }
  return -1;
}
function computeRangeRebase(args:{candles:Candle[]; activeCandle:Candle; rangeLow:number; rangeHigh:number; direction:'UP'|'DOWN'; rangeWindow?:{start?:string;end?:string}}) {
  const {candles, activeCandle, rangeLow, rangeHigh, direction, rangeWindow} = args;
  const activeIdx = candles.findIndex(c => String(c.time) === String(activeCandle.time));
  if (activeIdx < 0) return null;
  const breachIdx = findFirstBreachIndex(candles, activeIdx, direction, rangeLow, rangeHigh);
  if (breachIdx < 0) return null;
  const startMs = rangeWindow?.start ? new Date(String(rangeWindow.start)).getTime() : NaN;
  const windowStartIdx = Number.isFinite(startMs) ? Math.max(0, candles.findIndex(c => new Date(c.time).getTime() >= startMs)) : 0;
  const startIdx = Math.max(0, Math.min(windowStartIdx < 0 ? 0 : windowStartIdx, breachIdx));
  const slice = candles.slice(startIdx, activeIdx + 1);
  if (!slice.length) return null;
  if (direction === 'DOWN') {
    let responsible = slice[0], newLow = slice[0];
    slice.forEach(c => { if (c.high > responsible.high) responsible = c; if (c.low < newLow.low) newLow = c; });
    return {
      rebase_direction:'DOWN',
      new_range_high:Number(responsible.high.toFixed(2)),
      new_range_high_time:responsible.time,
      new_range_low:Number(newLow.low.toFixed(2)),
      new_range_low_time:newLow.time,
      responsible_high_time:responsible.time,
      current_low_time:newLow.time,
      measurement_old_range:{ high:rangeHigh, low:rangeLow },
      first_breach_time:candles[breachIdx]?.time,
    };
  }
  let responsible = slice[0], newHigh = slice[0];
  slice.forEach(c => { if (c.low < responsible.low) responsible = c; if (c.high > newHigh.high) newHigh = c; });
  return {
    rebase_direction:'UP',
    new_range_high:Number(newHigh.high.toFixed(2)),
    new_range_high_time:newHigh.time,
    new_range_low:Number(responsible.low.toFixed(2)),
    new_range_low_time:responsible.time,
    responsible_low_time:responsible.time,
    current_high_time:newHigh.time,
    measurement_old_range:{ high:rangeHigh, low:rangeLow },
    first_breach_time:candles[breachIdx]?.time,
  };
}
function analyseHTFSemiAuto(args:{timeframe:string; candles:Candle[]; activeCandle:Candle|null; rangeHigh:number; rangeLow:number; rangeWindow?:{start?:string;end?:string}; events?:MapEvent[]; activeCaseId?:number|null; acceptedLocks?:string[]}) {
  const {timeframe, candles, activeCandle, rangeHigh, rangeLow} = args;
  const rawAcceptedEvents = safeArray<MapEvent>(args.events || []);
  const activeCaseId = args.activeCaseId;
  const eventCaseId = (e:any) => { try { const m = typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); return e?.case_id ?? m?.case_id ?? null; } catch { return e?.case_id ?? null; } };
  const acceptedEvents = activeCaseId != null ? rawAcceptedEvents.filter((e:any) => String(eventCaseId(e)) === String(activeCaseId)) : [];
  const acceptedLockSet = new Set<string>(safeArray<string>(args.acceptedLocks || []));
  const prefix = prefixForTimeframe(timeframe);
  const out:{candidates:HTFCandidate[]; state:any} = { candidates:[], state:{} };
  const tfUpper = String(timeframe || '').toUpperCase();
  const canScanBos = ['MN1','W1','D1','H4','H1','M15'].includes(tfUpper);
  if (!activeCandle || !canScanBos || !Number.isFinite(rangeHigh) || !Number.isFinite(rangeLow) || rangeHigh <= rangeLow || !candles.length) {
    out.state = { status:'WAITING_FOR_RANGE', next_watch:'Set range high and low first. Engine only watches BOS up/down.' };
    return out;
  }
  const idx = candles.findIndex(c => String(c.time) === String(activeCandle.time));
  const pctClose = zonePercent(activeCandle.close, rangeLow, rangeHigh);
  const pctHigh = zonePercent(activeCandle.high, rangeLow, rangeHigh);
  const pctLow = zonePercent(activeCandle.low, rangeLow, rangeHigh);
  const location = zoneLabel(pctClose);
  const add = (partial:Omit<HTFCandidate,'id'|'time'|'candle'|'status'> & { idCode:string }) => {
    out.candidates.push({ id: candidateIdFor(timeframe, activeCandle, partial.idCode), time: activeCandle.time, candle: activeCandle, status:'CANDIDATE', ...partial } as HTFCandidate);
  };
  const hasSessionLock = (rule:string, side:string) => acceptedLockSet.has(htfSuggestionLockKey(timeframe, rangeLow, rangeHigh, rule, side));
  const hasBosUpAccepted = acceptedHTFEventHas(acceptedEvents, rangeLow, rangeHigh, (e,m) => String(e.derived_event_code || e.event_type || '').toUpperCase() === `${prefix}_BOS_UP` || m?.movement_rule === 'STRUCTURE_BOS_UP') || hasSessionLock('STRUCTURE_BOS_UP','HIGH');
  const hasBosDownAccepted = acceptedHTFEventHas(acceptedEvents, rangeLow, rangeHigh, (e,m) => String(e.derived_event_code || e.event_type || '').toUpperCase() === `${prefix}_BOS_DOWN` || m?.movement_rule === 'STRUCTURE_BOS_DOWN') || hasSessionLock('STRUCTURE_BOS_DOWN','LOW');
  const rangeStartMs = args.rangeWindow?.start ? new Date(String(args.rangeWindow.start)).getTime() : null;
  const rangeStartIndex = rangeStartMs && Number.isFinite(rangeStartMs) ? candles.findIndex(c => new Date(c.time).getTime() >= rangeStartMs) : 0;
  const activeCandleCount = idx >= 0 ? (idx - Math.max(0, rangeStartIndex) + 1) : candles.length;
  const legalState = hasBosUpAccepted ? 'BOS_UP_SAVED' : hasBosDownAccepted ? 'BOS_DOWN_SAVED' : 'ACTIVE_RANGE';
  out.state = {
    status: legalState,
    timeframe,
    prefix,
    location,
    close_pct: pctClose === null ? null : Number(pctClose.toFixed(2)),
    high_pct: pctHigh === null ? null : Number(pctHigh.toFixed(2)),
    low_pct: pctLow === null ? null : Number(pctLow.toFixed(2)),
    candle_count: activeCandleCount,
    last_candle: activeCandle.time,
    next_watch: 'Structure-only engine: autosave BOS up/down. Sweeps, retraces, profiles and phases are analytics work later.',
    memory_locks:{ bos_up:hasBosUpAccepted, bos_down:hasBosDownAccepted }
  };
  const isM15 = tfUpper === 'M15';
  const breaksHigh = isM15 ? activeCandle.close > rangeHigh : activeCandle.high > rangeHigh;
  const breaksLow = isM15 ? activeCandle.close < rangeLow : activeCandle.low < rangeLow;
  const upRule = isM15 ? 'M15_BODY_CLOSE_BOS_UP' : 'HTF_WICK_BOS_UP';
  const downRule = isM15 ? 'M15_BODY_CLOSE_BOS_DOWN' : 'HTF_WICK_BOS_DOWN';
  if (breaksHigh && !hasBosUpAccepted) {
    add({ idCode:'BOS_UP', event_type:`${prefix}_BOS_UP`, label:`${prefix} BOS Up`, price:isM15 ? activeCandle.close : activeCandle.high, priceMode:isM15 ? 'close':'high', confidence:'HIGH', primitive:'BREACH', derived_event_code:`${prefix}_BOS_UP`, movement_rule:'STRUCTURE_BOS_UP', range_status_after:'BOS_UP_SAVED', reason:`${isM15 ? 'M15 body close' : 'Wick'} broke Range High ${rangeHigh.toFixed(2)}. Structure-only autosave.`, meta:{ breach_side:'HIGH', break_rule:upRule, range_high:rangeHigh, pct_high:pctHigh } });
  }
  if (breaksLow && !hasBosDownAccepted) {
    add({ idCode:'BOS_DOWN', event_type:`${prefix}_BOS_DOWN`, label:`${prefix} BOS Down`, price:isM15 ? activeCandle.close : activeCandle.low, priceMode:isM15 ? 'close':'low', confidence:'HIGH', primitive:'BREACH', derived_event_code:`${prefix}_BOS_DOWN`, movement_rule:'STRUCTURE_BOS_DOWN', range_status_after:'BOS_DOWN_SAVED', reason:`${isM15 ? 'M15 body close' : 'Wick'} broke Range Low ${rangeLow.toFixed(2)}. Structure-only autosave.`, meta:{ breach_side:'LOW', break_rule:downRule, range_low:rangeLow, pct_low:pctLow } });
  }
  return out;
}


function yForMapPrice(price:number, low:number, high:number) {
  if (!Number.isFinite(price) || !Number.isFinite(low) || !Number.isFinite(high) || high === low) return 50;
  return clamp(100 - ((price-low)/(high-low))*100, -18, 118);
}
const TRAJECTORY_ZONE_ORDER:any = {
  'External Low': 0,
  'Extreme Discount': 1,
  'Discount': 2,
  'Below Fair Price': 3,
  'Fair Price': 4,
  'Premium': 5,
  'Extreme Premium': 6,
  'External High': 7,
};

function autoTrajectory(candles:Candle[], low:number, high:number) {
  // Build route from actual candle travel, then COMPRESS it into meaningful route checkpoints.
  // We do NOT want one SQL/database point per candle. That creates a candle landfill.
  // Logic:
  // 1) Read intrabar travel using wick extremes.
  // 2) Convert price into Josh zone bands.
  // 3) Keep only directional milestones and major reversals.
  // Example: External Low -> Extreme Discount -> Discount -> Fair Price -> Premium -> Fair Price -> Discount.
  const raw:{time:string; price:number; zone:string; pct:number; idx:number}[] = [];
  let lastZone = '';
  const pushRaw = (time:string, price:number) => {
    const p = zonePercent(price, low, high);
    const z = zoneLabel(p);
    const idx = TRAJECTORY_ZONE_ORDER[z];
    if (z === '-' || idx === undefined || !Number.isFinite(Number(p))) return;
    if (z !== lastZone) {
      raw.push({ time, price:Number(price.toFixed(2)), zone:z, pct:Number((p ?? 0).toFixed(2)), idx });
      lastZone = z;
    }
  };

  for (const c of candles) {
    const bullish = c.close >= c.open;
    const path = bullish ? [c.low, c.high, c.close] : [c.high, c.low, c.close];
    for (const price of path) pushRaw(c.time, Number(price));
  }

  if (raw.length <= 2) return raw.map(({idx, ...p}) => p);

  const compressed:{time:string; price:number; zone:string; pct:number; idx:number}[] = [raw[0]];
  let dir = 0; // 1 = climbing through zones, -1 = falling through zones
  let extreme = raw[0].idx;

  for (let i = 1; i < raw.length; i++) {
    const p = raw[i];
    if (p.idx === extreme) continue;

    if (dir === 0) {
      dir = p.idx > extreme ? 1 : -1;
      compressed.push(p);
      extreme = p.idx;
      continue;
    }

    if (dir === 1) {
      // In an up-leg, only record new higher zones.
      if (p.idx > extreme) {
        compressed.push(p);
        extreme = p.idx;
        continue;
      }
      // Ignore tiny one-zone wiggles; start a down-leg only after a proper reversal.
      if (p.idx <= extreme - 2) {
        compressed.push(p);
        extreme = p.idx;
        dir = -1;
      }
      continue;
    }

    if (dir === -1) {
      // In a down-leg, only record new lower zones.
      if (p.idx < extreme) {
        compressed.push(p);
        extreme = p.idx;
        continue;
      }
      // Ignore tiny one-zone wiggles; start an up-leg only after a proper reversal.
      if (p.idx >= extreme + 2) {
        compressed.push(p);
        extreme = p.idx;
        dir = 1;
      }
    }
  }

  return compressed.map(({idx, ...p}) => p);
}


function candleIndexAtOrBefore(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  let idx = -1;
  for (let i=0; i<candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    if (Number.isFinite(t) && t <= cut) idx = i;
    if (Number.isFinite(t) && t > cut) break;
  }
  return Math.max(0, idx >= 0 ? idx : 0);
}

function candleIndexAtOrAfter(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  for (let i = 0; i < candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    if (Number.isFinite(t) && t >= cut) return i;
  }
  return candles.length - 1;
}

function candleDataExtent(candles: Candle[]): { startMs: number; endMs: number; start: string; end: string } | null {
  if (!candles.length) return null;
  const startMs = new Date(String(candles[0].time)).getTime();
  const endMs = new Date(String(candles[candles.length - 1].time)).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return { startMs, endMs, start: candles[0].time, end: candles[candles.length - 1].time };
}

function isPlausibleMarketTimeMs(ms: number | null, candles?: Candle[]): boolean {
  if (ms === null || !Number.isFinite(ms)) return false;
  const year = new Date(ms).getUTCFullYear();
  if (year < 1990 || year > 2035) return false;
  const ext = candles?.length ? candleDataExtent(candles) : null;
  if (ext) {
    const pad = Math.max((ext.endMs - ext.startMs) * 0.2, 86400000 * 14);
    return ms >= ext.startMs - pad && ms <= ext.endMs + pad;
  }
  return true;
}

function clampFitTimesToCandles(startRaw: string, endRaw: string, candles: Candle[]): { start: string; end: string } {
  const ext = candleDataExtent(candles);
  if (!ext) return { start: startRaw, end: endRaw || startRaw };
  let startMs = parseStructuralTimeMs(startRaw);
  let endMs = parseStructuralTimeMs(endRaw);
  if (!isPlausibleMarketTimeMs(startMs, candles)) startMs = ext.startMs;
  if (!isPlausibleMarketTimeMs(endMs, candles)) endMs = ext.endMs;
  if (startMs === null) startMs = ext.startMs;
  if (endMs === null) endMs = ext.endMs;
  if (endMs < startMs) endMs = startMs;
  startMs = Math.max(ext.startMs, Math.min(ext.endMs, startMs));
  endMs = Math.max(startMs, Math.min(ext.endMs, endMs));
  return { start: new Date(startMs).toISOString(), end: new Date(endMs).toISOString() };
}

function buildCandleWindowFit(candles: Candle[], centerTime: string, padBars = 40): StructuralFitWindow | null {
  if (!candles.length || !centerTime) return null;
  const centerMs = parseStructuralTimeMs(centerTime);
  if (!isPlausibleMarketTimeMs(centerMs, candles)) return null;
  const idx = candleIndexAtOrBefore(candles, centerTime);
  const pad = Math.max(8, padBars);
  const i0 = Math.max(0, idx - pad);
  const i1 = Math.min(candles.length - 1, idx + pad);
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = i0; i <= i1; i++) {
    lo = Math.min(lo, candles[i].low);
    hi = Math.max(hi, candles[i].high);
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  return { start: candles[i0].time, end: candles[i1].time, low: lo, high: hi, padRatio: 0.1 };
}

function candleIndexNearest(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  let best = 0;
  let dist = Math.abs(new Date(String(candles[0].time)).getTime() - cut);
  for (let i=1; i<candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    const d = Math.abs(t - cut);
    if (Number.isFinite(d) && d < dist) { best = i; dist = d; }
  }
  return best;
}

function eventAbbrev(type:any) {
  const t = String(type || '').toUpperCase();
  const map:any = { RANGE_HIGH:'RH', RANGE_LOW:'RL', REF_HIGH_TAKEN:'RHT', REF_LOW_TAKEN:'RLT', BOS_UP:'B+', BOS_DOWN:'B-', CHOCH_UP:'C+', CHOCH_DOWN:'C-', INTERNAL_SWEEP_HIGH:'ISH', INTERNAL_SWEEP_LOW:'ISL', EXTERNAL_SWEEP_HIGH:'ESH', EXTERNAL_SWEEP_LOW:'ESL', INTERNAL_REJECTION_LOW:'IRL', INTERNAL_REJECTION_HIGH:'IRH', EXTREME_DISCOUNT_LOW:'EDL', BELOW_FAIR_PRICE_LOW:'BFL', ABOVE_FAIR_PRICE_HIGH:'AFH', EXTREME_PREMIUM_HIGH:'EPH', RECLAIM_HIGH:'RHc', RECLAIM_LOW:'RLc' };
  if (map[t]) return map[t];
  if (/^P[123]$/.test(t)) return t;
  return t.split('_').map(x=>x[0]).join('').slice(0,4) || 'EV';
}

function MapStudio({ symbol, onSymbolChange }: { symbol: string; onSymbolChange?: (symbol: string) => void }) {
  // Inspector form fields — hoisted to avoid TDZ with cache hydrate/persist effects.
  const [seedNotes, setSeedNotes] = useState('');
  const [tradeIdeaNotes, setTradeIdeaNotes] = useState('');
  const [markWorkspaceMode, setMarkWorkspaceMode] = useLocalStorage<'htf'|'manual'|'case'>('fx_tm_mark_workspace_mode_v087_9', 'htf');
  const [inspectorFormReady, setInspectorFormReady] = useState(false);
  const inspectorFormHydratedScopeRef = useRef<string | null>(null);

  const [timeframe, setTimeframe] = useState('D1');
  const activeTimeframeRef = useRef('D1');
  useEffect(()=>{ activeTimeframeRef.current = timeframe; }, [timeframe]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [candleDataRevision, setCandleDataRevision] = useState(0);
  const setChartCandles = (next: Candle[] | ((prev: Candle[]) => Candle[])) => {
    setCandles(next);
    setCandleDataRevision((v) => v + 1);
  };
  // v086.13: Persist explicit range anchors locally. Without this, restart/replay can
  // fall back to old backend/default ranges and move the fibs away from Josh's
  // candle-selected anchors. The chart is not allowed to develop amnesia.
  const [rangeByTf, setRangeByTf] = useLocalStorage<Record<string,{high:string;low:string}>>('fx_tm_range_by_tf_v087_29b', {});
  const [rangeWindowByTf, setRangeWindowByTf] = useLocalStorage<Record<string,{start?:string;end?:string}>>('fx_tm_range_window_by_tf_v087_29b', {});
  // v087.16: active fib range and measurement range are separate.
  // Active range drives the visible fib/zone %. Measurement range preserves the old range
  // for retracement-depth/profile stats after a rebase. Do not let these two goblins swap hats.
  const [measurementRangeByTf, setMeasurementRangeByTf] = useLocalStorage<Record<string,{high:number;low:number;start?:string;end?:string;rebase_candidate_id?:string;preserved_for?:string}>>('fx_tm_measurement_range_by_tf_v087_16', {});
  const rangeWindow = rangeWindowByTf[timeframe] || {};
  const measurementRange = measurementRangeByTf[timeframe] || null;
  const setRangeWindow = (patch:{start?:string;end?:string}) => setRangeWindowByTf(prev=>({ ...prev, [timeframe]: { ...(prev[timeframe] || {}), ...patch }}));
  const rangeHigh = rangeByTf[timeframe]?.high || '';
  const rangeLow = rangeByTf[timeframe]?.low || '';
  const setRangeHigh = (v:string) => setRangeByTf(prev=>({ ...prev, [timeframe]: { high:v, low: prev[timeframe]?.low || '' }}));
  const setRangeLow = (v:string) => setRangeByTf(prev=>({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low:v }}));
  const timesToWindow = (times:any[]) => {
    const ms = times
      .filter(Boolean)
      .map((x:any) => new Date(String(x)).getTime())
      .filter((x:number) => Number.isFinite(x));
    if (!ms.length) return null;
    return { start: new Date(Math.min(...ms)).toISOString(), end: new Date(Math.max(...ms)).toISOString() };
  };
  const [eventType, setEventType] = useState('INTERNAL_SWEEP');
  const [eventName, setEventName] = useState('');
  const [eventsByTf, setEventsByTf] = useState<Record<string,MapEvent[]>>({});
  const eventsByTfRef = useRef<Record<string,MapEvent[]>>({});
  const events = safeArray<MapEvent>(eventsByTf?.[timeframe]);
  useEffect(()=>{ eventsByTfRef.current = eventsByTf; }, [eventsByTf]);
  const setEventsForTf = (updater: MapEvent[] | ((prev:MapEvent[])=>MapEvent[])) => setEventsByTf(prev=>{
    const current = safeArray<MapEvent>(prev?.[timeframe]);
    const next = typeof updater === 'function' ? (updater as any)(current) : updater;
    const all = { ...prev, [timeframe]: next };
    eventsByTfRef.current = all;
    return all;
  });
  const [message, setMessage] = useState('D3 Map Canvas ready. Click Candle mode lets you mark Range H/L, reference highs/lows, BOS and sweeps without wrestling tiny handles.');
  const [loading, setLoading] = useState(false);
  const [candleLoadState, setCandleLoadState] = useState<string | null>(null);
  const [candleFeedStatus, setCandleFeedStatus] = useState<any>(null);
  const [toolMode, setToolMode] = useState<'inspect'|'plot'|'drag'|'range'|'select'|'scrub'>('select');
  const [scaleMode, setScaleMode] = useState<'auto'|'range'>('auto');
  const [autoscaleToken, setAutoscaleToken] = useState(0);
  const [cursor, setCursor] = useState<{time?:string; price?:number; zone?:string; pct?:number; ohlc?:Candle|null}|null>(null);
  const [candleMenu, setCandleMenu] = useState<{x:number;y:number;candle:Candle;price:number}|null>(null);
  const [selectedCandle, setSelectedCandle] = useState<Candle|null>(null);
  const [selectedCandlePoint, setSelectedCandlePoint] = useState<{price:number; clientX?:number; clientY?:number}|null>(null);
  const [pendingMarkerRoles, setPendingMarkerRoles] = useState<string[]>([]);
  const [jumpDate, setJumpDate] = useState('');
  const [jumpToken, setJumpToken] = useState(0);
  const [fitToken, setFitToken] = useState(0);
  const [gpsMode, setGpsMode] = useState<'mock'|'active'>('active');
  const [gps, setGps] = useState<GpsPayload|null>(null);
  const [gpsTimeline, setGpsTimeline] = useState<TimelineNode[]>([]);
  const [gpsStoryAnchor, setGpsStoryAnchor] = useState('WEEKLY_REF_LOW_TAKEN');
  const [gpsChapter, setGpsChapter] = useState('DAILY_BOS_UP');
  const [gpsPhaseNumber, setGpsPhaseNumber] = useState('P1');
  const [gpsPhasePart, setGpsPhasePart] = useState('RETEST');
  const [gpsObjective, setGpsObjective] = useState('DAILY_PREMIUM');
  const [gpsCurrentZone, setGpsCurrentZone] = useState('DAILY_DISCOUNT');
  const [gpsParentMode, setGpsParentMode] = useState('WEEKLY_ACTIVE_PARENT');
  const [gpsDailyRangeStatus, setGpsDailyRangeStatus] = useState('DAILY_RANGE_ACTIVE');
  const [gpsLifecycleState, setGpsLifecycleState] = useState('EXPANSION');
  const [gpsProfileType, setGpsProfileType] = useState('NO_RECLAIM_CONTINUATION_PROFILE');
  const [gpsTriggerEvent, setGpsTriggerEvent] = useState('DAILY_BOS_UP_RECLAIM');
  const [gpsExpectedNextEvent, setGpsExpectedNextEvent] = useState('PENDING_MARKET_DELIVERY');
  const [gpsInvalidationCondition, setGpsInvalidationCondition] = useState('MANUAL_INVALIDATION_REQUIRED');
  const [gpsStoryId, setGpsStoryId] = useState('');
  const [gpsChapterId, setGpsChapterId] = useState('');
  const [playbackStoryId, setPlaybackStoryId] = useState('3');
  const [playbackFrames, setPlaybackFrames] = useState<PlaybackFrame[]>([]);
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [replayMode, setReplayMode] = useState(false);
  const [playbackPlaying, setPlaybackPlaying] = useState(false);
  const [rightDeckTabRaw, setRightDeckTabRaw] = useLocalStorage<InspectorTabId>('fx_tm_inspector_tab_v1', 'campaign');
  const rightDeckTab = normalizeInspectorTabId(rightDeckTabRaw);
  const setRightDeckTab = (tab: InspectorTabId) => setRightDeckTabRaw(normalizeInspectorTabId(tab));
  const [inspectorContextHint, setInspectorContextHint] = useState<InspectorContextHint | null>(null);

  const applyInspectorRoute = (route: ReturnType<typeof routeInspectorForCandleSelection>, hint: InspectorContextHint | null) => {
    setRightDeckTab(route.tab);
    if (route.markWorkspaceMode) setMarkWorkspaceMode(route.markWorkspaceMode);
    setInspectorContextHint(hint);
  };

  const handleInspectorTabChange = (tab: InspectorTabId) => {
    setRightDeckTab(tab);
    if (tab === 'tools' || tab === 'mark') setToolMode('select');
    if (tab === 'trade') setChartDrawTool('off');
  };
  const [topRibbonCollapsed, setTopRibbonCollapsed] = useLocalStorage<boolean>('fx_tm_top_ribbon_collapsed_v087_24', true);
  const [chartRendererRaw, setChartRendererRaw] = useLocalStorage<ChartRendererMode>(CHART_RENDERER_STORAGE_KEY, DEFAULT_CHART_RENDERER);
  const chartRenderer = normalizeChartRendererMode(chartRendererRaw);
  const chartRendererRef = useRef(chartRenderer);
  useEffect(() => { chartRendererRef.current = chartRenderer; }, [chartRenderer]);
  const [tradingViewOverlayModeRaw, setTradingViewOverlayModeRaw] = useLocalStorage<TradingViewOverlayMode>(TRADINGVIEW_OVERLAYS_STORAGE_KEY, DEFAULT_TRADINGVIEW_OVERLAY_MODE);
  const tradingViewOverlayMode = normalizeTradingViewOverlayMode(tradingViewOverlayModeRaw);
  const [tradingViewSelectedCandleModeRaw, setTradingViewSelectedCandleModeRaw] = useLocalStorage<TradingViewSelectedCandleMode>(TRADINGVIEW_SELECTED_CANDLE_STORAGE_KEY, DEFAULT_TRADINGVIEW_SELECTED_CANDLE_MODE);
  const tradingViewSelectedCandleMode = normalizeTradingViewSelectedCandleMode(tradingViewSelectedCandleModeRaw);
  const [tradingViewMappingInputRaw, setTradingViewMappingInputRaw] = useLocalStorage<string>(TRADINGVIEW_MAPPING_INPUT_STORAGE_KEY, DEFAULT_TRADINGVIEW_MAPPING_INPUT);
  const tradingViewMappingInputMode = normalizeTradingViewMappingInputMode(tradingViewMappingInputRaw);
  const tradingViewMappingInputEnabled = isTradingViewMappingInputEnabled(tradingViewMappingInputRaw);
  const tradingViewMappingInputEnabledRef = useRef(tradingViewMappingInputEnabled);
  useEffect(() => { tradingViewMappingInputEnabledRef.current = tradingViewMappingInputEnabled; }, [tradingViewMappingInputEnabled]);
  const [tradingViewSelectedCandle, setTradingViewSelectedCandle] = useState<TradingViewSelectedCandle | null>(null);
  const tradingViewSelectedCandleRef = useRef<TradingViewSelectedCandle | null>(null);
  useEffect(() => { tradingViewSelectedCandleRef.current = tradingViewSelectedCandle; }, [tradingViewSelectedCandle]);
  const admittedMappingInputCandleRef = useRef<MappingInputCandle | null>(null);
  const [admittedMappingInputCandle, setAdmittedMappingInputCandle] = useState<MappingInputCandle | null>(null);
  const applyTvMappingSelectionClear = () => {
    const cleared = clearTvMappingSelection();
    admittedMappingInputCandleRef.current = cleared.mappingInputCandle;
    setAdmittedMappingInputCandle(cleared.mappingInputCandle);
    setTradingViewSelectedCandle(cleared.tradingViewSelectedCandle);
  };
  const applyTvMappingSelectionCommit = (row: MappingInputCandle): boolean => {
    const committed = commitTvMappingSelection({ row, sourceTimeframe: sourceTimeframeRef.current });
    if (!committed) {
      applyTvMappingSelectionClear();
      return false;
    }
    admittedMappingInputCandleRef.current = committed.mappingInputCandle;
    setAdmittedMappingInputCandle(committed.mappingInputCandle);
    setTradingViewSelectedCandle(committed.tradingViewSelectedCandle);
    return true;
  };
  const selectedCandleRef = useRef<Candle | null>(null);
  useEffect(() => { selectedCandleRef.current = selectedCandle; }, [selectedCandle]);
  const [tradingViewCrosshairCandle, setTradingViewCrosshairCandle] = useState<TradingViewSelectedCandle | null>(null);
  const [tradingViewSelectionWarning, setTradingViewSelectionWarning] = useState<string | null>(null);
  const [tradingViewHierarchyFitCommand, setTradingViewHierarchyFitCommand] = useState<CameraCommand | null>(null);
  const [tradingViewExplicitReplayMode, setTradingViewExplicitReplayMode] = useState(false);
  const [tradingViewReplayStepFitRequest, setTradingViewReplayStepFitRequest] = useState<TradingViewFitRequest | null>(null);
  const tradingViewReplayFitTokenRef = useRef(0);
  const tradingViewExplicitReplayModeRef = useRef(false);
  useEffect(() => { tradingViewExplicitReplayModeRef.current = tradingViewExplicitReplayMode; }, [tradingViewExplicitReplayMode]);
  const tradingViewHierarchyFitKeyRef = useRef('');
  const tradingViewSuppressedHierarchyRangeIdRef = useRef('');
  const tradingViewSelectionBridgeActive = chartRenderer === 'tradingview' && tradingViewSelectedCandleMode === 'readonly';
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [navOverlayPanelOpen, setNavOverlayPanelOpen] = useState(false);
  /** Pilot layout: O-N-G-M-C-T rail lives in the fixed 60px grid column; inspector toggles column 3 only. */
  const useLeftInspectorPanel = true;
  const handleNavOverlayTabChange = (tab: InspectorTabId) => {
    if (rightDeckTab === tab && navOverlayPanelOpen) {
      setNavOverlayPanelOpen(false);
      return;
    }
    handleInspectorTabChange(tab);
    setNavOverlayPanelOpen(true);
  };
  // v087.27: camera state is now user-owned. Timeframe toggles should not throw the chart around like a shopping trolley.
  const [cameraMode, setCameraMode] = useLocalStorage<'AUTO'|'LOCKED'|'CASE'|'REPLAY'>('fx_tm_camera_mode_v087_27', 'CASE');
  const [cameraDomainByCaseTf, setCameraDomainByCaseTf] = useLocalStorage<Record<string,{start:string;end:string}>>('fx_tm_camera_domain_v087_27', {});
  const [cameraPriceDomainByCaseTf, setCameraPriceDomainByCaseTf] = useLocalStorage<Record<string,{low:number;high:number}>>('fx_tm_camera_price_domain_v087_31', {});
  const [candleWidthScale, setCandleWidthScale] = useLocalStorage<number>('fx_tm_candle_width_scale_v087_27', 1);
  const [priceZoomScale, setPriceZoomScale] = useLocalStorage<number>('fx_tm_price_zoom_scale_v087_27', 1);
  const candleLoadSeqRef = useRef(0);
  const candleLoadContextRef = useRef<CandleLoadContext>({ requestId: 0, symbol: '', caseId: '', tf: '', activeRangeId: '', loadWindowKey: 'full' });
  const loadedCandleContextRef = useRef<LoadedCandleContext | null>(null);
  const [loadedCandleContext, setLoadedCandleContext] = useState<LoadedCandleContext | null>(null);
  const localLibraryDebugRef = useRef<LocalLibraryDebugStatus | null>(null);
  const [localLibraryDebug, setLocalLibraryDebug] = useState<LocalLibraryDebugStatus | null>(null);
  const [candleFeedLoading, setCandleFeedLoading] = useState(false);
  const candleFeedLoadInFlightRef = useRef(false);
  const candleFeedReloadKeyRef = useRef('');
  const tradingViewDisplayCandlesRef = useRef<Candle[]>([]);
  const structureLayerRef = useRef<StructureLayer>('WEEKLY');
  const sourceTimeframeRef = useRef<string>('W1');
  const candleCountRef = useRef(0);
  const candlesRef = useRef<Candle[]>([]);
  candlesRef.current = candles;
  const chartBootstrapSeqRef = useRef(0);
  const deferredCameraRef = useRef<{
    intent: CameraIntent;
    targetTime?: string | null;
    reason?: string;
    fitWindow?: StructuralFitWindow | null;
    priceDomain?: { low: number; high: number } | null;
  } | null>(null);
  const [deferredCameraToken, setDeferredCameraToken] = useState(0);
  const [candleLoadDiagnostics, setCandleLoadDiagnostics] = useState<CandleLoadDiagnostics | null>(null);
  useEffect(() => { candleCountRef.current = candles.length; }, [candles.length]);
  const pendingCameraIntentRef = useRef<{intent:CameraIntent; targetTime?:string|null; reason?:string; fitWindow?: StructuralFitWindow | null; priceDomain?: { low: number; high: number } | null; contextRangeId?: string | null; anchorSource?: RoutineAnchorSource | null}>({ intent:'LATEST', reason:'initial-load' });
  const pendingCameraIntentAwaitingTvFitRef = useRef(false);
  const routineSettleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fullHistoryChartTfsRef = useRef<Set<string>>(new Set());
  const visibleCameraDomainRef = useRef<VisibleCameraDomain|null>(null);
  const cameraKeyRef = useRef('');
  const saveCameraTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [visibleBarCount, setVisibleBarCount] = useState(0);
  const [cameraCommand, setCameraCommand] = useState<CameraCommand>({ intent:'NONE', token:0 });
  const [cameraViewOwner, setCameraViewOwner] = useState<CameraViewOwner>('AUTO');
  const cameraViewOwnerRef = useRef<CameraViewOwner>('AUTO');
  const setCameraViewOwnerWithLog = (owner: CameraViewOwner, source: string, reason?: string) => {
    const ownerBefore = cameraViewOwnerRef.current;
    cameraViewOwnerRef.current = owner;
    setCameraViewOwner(owner);
    console.info(
      `camera update: reason=${reason || owner} source=${source} ownerBefore=${ownerBefore} ownerAfter=${owner} candleCount=${candleCountRef.current}`,
    );
    logCameraUpdate(reason || owner, source, DEBUG_CAMERA);
  };
  const cameraLog = (...args:any[]) => { if (DEBUG_CAMERA) console.log('[camera]', ...args); };
  const clampScale = (v:number) => Math.max(0.35, Math.min(4, Number(v) || 1));
  const bumpCandleWidth = (delta:number) => {
    const factor = delta > 0 ? 1.18 : 1 / 1.18;
    setCandleWidthScale(v => Number(clampScale((Number(v)||1) + delta).toFixed(2)));
    applyCameraCommand('HORIZONTAL_STRETCH', null, delta > 0 ? 'manual-W-plus' : 'manual-W-minus', factor);
  };
  const bumpPriceZoom = (delta:number) => {
    const factor = delta > 0 ? 1.18 : 1 / 1.18;
    setPriceZoomScale(v => Number(clampScale((Number(v)||1) + delta).toFixed(2)));
    applyCameraCommand('VERTICAL_STRETCH', null, delta > 0 ? 'manual-H-plus' : 'manual-H-minus', factor);
  };
  const resetCameraScale = () => { setCandleWidthScale(1); setPriceZoomScale(1); setFitToken(x=>x+1); };
  const autoSavedBosIdsRef = useRef<Set<string>>(new Set());

  // v087.26: Full Chart is a real workspace mode. Re-fit after the DOM changes so the camera does not
  // inherit the smaller board dimensions like a cursed little postage stamp.
  useEffect(()=>{
    if (!chartFullscreen) return;
    if (cameraMode === 'LOCKED') return;
    const pendingReason = pendingCameraIntentRef.current.intent !== 'NONE'
      ? pendingCameraIntentRef.current.reason
      : cameraCommand.reason;
    if (shouldBlockFullscreenLayoutRefit({
      owner: cameraViewOwnerRef.current,
      pendingCameraIntentActive: pendingCameraIntentRef.current.intent !== 'NONE'
        || pendingCameraIntentAwaitingTvFitRef.current,
      hasPendingFitToken: pendingCameraIntentAwaitingTvFitRef.current,
      pendingFitReason: pendingReason,
    })) return;
    if (shouldBlockAutomaticCameraRefit(cameraViewOwnerRef.current)) return;
    const intent:CameraIntent = cameraMode === 'CASE' ? 'CASE' : cameraMode === 'REPLAY' ? 'REPLAY' : 'PRESERVE_OR_NEAREST_TIME';
    const targetTime = selectedCandle?.time || (candleReplayMode ? (candleReplayCursorTime || replayCandle?.time || null) : null);
    const t = window.setTimeout(()=>applyCameraCommand(intent, targetTime, 'fullscreen-layout-ready'), 120);
    return () => window.clearTimeout(t);
  }, [chartFullscreen]);

  const inspectorRailHidden = useLeftInspectorPanel && !navOverlayPanelOpen;

  useEffect(() => {
    document.body.classList.add('mapStudioPilot');
    document.body.classList.toggle('chartHideInspectorRail', true);
    document.body.classList.toggle('chartFocusMode', chartFullscreen);
    document.body.classList.toggle('chartLeftInspectorOpen', navOverlayPanelOpen);
    return () => {
      document.body.classList.remove('mapStudioPilot', 'chartHideInspectorRail', 'chartFocusMode', 'chartLeftInspectorOpen');
    };
  }, [chartFullscreen, navOverlayPanelOpen]);

  // Full candle-by-candle replay: this is separate from MOS playback_frames.
  // It rewinds the actual candle stream so Josh can mark HTF/Daily anchors at the correct historical point.
  const [candleReplayMode, setCandleReplayMode] = useState(false);
  const [candleReplayIndex, setCandleReplayIndex] = useState(0);
  // v087.22: one master replay cursor time drives every timeframe. W1 back one candle should
  // hide all D1/H1/M15 candles newer than that weekly timestamp, otherwise replay leaks future data.
  const [replayCursorByKey, setReplayCursorByKey] = useLocalStorage<Record<string, string>>('fx_tm_replay_cursor_by_case_v1', {});
  const [candleReplayPlaying, setCandleReplayPlaying] = useState(false);
  const [candleReplaySpeedMs, setCandleReplaySpeedMs] = useState(550);
  const [replayStartMenuOpen, setReplayStartMenuOpen] = useState(false);
  const [replaySelectBarMode, setReplaySelectBarMode] = useState(false);
  const REPLAY_SPEED_OPTIONS = [
    { label: '1x', ms: 550 },
    { label: '2x', ms: 275 },
    { label: '3x', ms: 183 },
    { label: '5x', ms: 110 },
    { label: '10x', ms: 55 },
  ];
  const replaySpeedLabel = REPLAY_SPEED_OPTIONS.find((o) => o.ms === candleReplaySpeedMs)?.label ?? '1x';
  const [seedName, setSeedName] = useState('XAUUSD Case');
  const [seedAnchors, setSeedAnchors] = useState<any>({});
  const [seedIdeas, setSeedIdeas] = useState<any[]>([]);
  const [caseLoadStatus, setCaseLoadStatus] = useState('');
  const [caseSaving, setCaseSaving] = useState(false);
  const [caseSavedNotice, setCaseSavedNotice] = useState('');
  const [activeCaseId, setActiveCaseId] = useLocalStorage<number|null>('fx_tm_active_case_id_v087_29b', null);
  // v087.29c: raw mapping cases are UUID strings stored in raw_mapping_cases.
  // Keep this separate from legacy MOS numeric case ids so Case Save stops dragging old event bundles along.
  const [rawActiveCaseId, setRawActiveCaseId] = useLocalStorage<string>('fx_tm_raw_active_case_id_v087_29c', '');
  const [activeCaseLabel, setActiveCaseLabel] = useLocalStorage<string>('fx_tm_active_case_label_v086_16', '');
  const activeCaseDisplayId = resolveActiveCaseDisplayId(rawActiveCaseId, activeCaseId);
  const activeCaseDisplayIdRef = useRef(activeCaseDisplayId);
  useEffect(() => { activeCaseDisplayIdRef.current = activeCaseDisplayId; }, [activeCaseDisplayId]);
  const { mappingEventsScopeKey } = useReactiveMappingEventsPersistence({
    symbol,
    caseId: activeCaseDisplayId || null,
    eventsByTf,
    setEventsByTf,
    eventsByTfRef,
  });

  const inspectorFormScopeKey = useMemo(
    () => inspectorFormCacheKey(symbol, timeframe, activeCaseDisplayId || undefined),
    [symbol, timeframe, activeCaseDisplayId],
  );
  useEffect(() => {
    setInspectorFormReady(false);
    const cached = readInspectorFormCache(inspectorFormScopeKey);
    if (cached.seedNotes !== undefined) setSeedNotes(cached.seedNotes);
    if (cached.tradeIdeaNotes !== undefined) setTradeIdeaNotes(cached.tradeIdeaNotes);
    if (cached.markWorkspaceMode) setMarkWorkspaceMode(cached.markWorkspaceMode);
    inspectorFormHydratedScopeRef.current = inspectorFormScopeKey;
    setInspectorFormReady(true);
  }, [inspectorFormScopeKey, setMarkWorkspaceMode]);
  useEffect(() => {
    if (!inspectorFormReady || inspectorFormHydratedScopeRef.current !== inspectorFormScopeKey) return;
    const t = window.setTimeout(() => {
      writeInspectorFormCache(inspectorFormScopeKey, {
        seedNotes,
        tradeIdeaNotes,
        markWorkspaceMode,
      });
    }, 250);
    return () => window.clearTimeout(t);
  }, [inspectorFormReady, inspectorFormScopeKey, seedNotes, tradeIdeaNotes, markWorkspaceMode]);
  const getCurrentMappingCaseRef = () => {
    const rawId = String(rawActiveCaseId || '').trim();
    if (rawId) {
      return {
        case_id: null as number | null,
        raw_case_id: rawId,
        case_ref: `raw:${rawId}`,
        label: activeCaseLabel || `Raw ${rawId.slice(0, 8)}`,
        hasCase: true,
      };
    }
    const numericId = activeCaseId === null || activeCaseId === undefined ? null : Number(activeCaseId);
    if (Number.isFinite(numericId) && numericId !== null) {
      return {
        case_id: numericId,
        raw_case_id: null as string | null,
        case_ref: `case:${numericId}`,
        label: activeCaseLabel || `Case #${numericId}`,
        hasCase: true,
      };
    }
    return {
      case_id: null as number | null,
      raw_case_id: null as string | null,
      case_ref: null as string | null,
      label: null as string | null,
      hasCase: false,
    };
  };
  const appendMappingCaseParams = (params: URLSearchParams, ref = getCurrentMappingCaseRef()) => {
    if (ref.case_id !== null) params.set('case_id', String(ref.case_id));
    if (ref.raw_case_id) params.set('raw_case_id', ref.raw_case_id);
    if (ref.case_ref) params.set('case_ref', ref.case_ref);
    return params;
  };
  const skipSelectionClearForTfSwitchRef = useRef(false);
  const cameraKey = chartMemoryKey(activeCaseDisplayId || 'global', symbol, timeframe);
  const legacyCameraKey = legacyChartMemoryKey(activeCaseDisplayId || 'global', timeframe);
  cameraKeyRef.current = cameraKey;
  const globalReplayKey = globalReplayCursorKey(activeCaseDisplayId || 'global', symbol);
  const persistVisibleCameraDomain = (dom: VisibleCameraDomain) => {
    visibleCameraDomainRef.current = dom;
    const next = Number(dom.visibleBars || 0);
    setVisibleBarCount(prev => (prev === next ? prev : next));
    if (cameraMode === 'LOCKED') return;
    if (!dom?.start || !dom?.end) return;
    if (!Number.isFinite(new Date(dom.start).getTime()) || !Number.isFinite(new Date(dom.end).getTime())) return;
    if (saveCameraTimeoutRef.current) clearTimeout(saveCameraTimeoutRef.current);
    saveCameraTimeoutRef.current = setTimeout(() => {
      const tf = String(activeTimeframeRef.current || 'D1').toUpperCase();
      if (!shouldPersistChartMemory({
        start: dom.start,
        end: dom.end,
        priceLow: dom.priceLow,
        priceHigh: dom.priceHigh,
        visibleBars: dom.visibleBars,
      }, tf)) {
        return;
      }
      const key = cameraKeyRef.current;
      const legacy = legacyChartMemoryKey(activeCaseDisplayIdRef.current || 'global', activeTimeframeRef.current);
      setCameraDomainByCaseTf(prev => ({
        ...prev,
        [key]: { start: dom.start, end: dom.end },
        [legacy]: { start: dom.start, end: dom.end },
      }));
      if (Number.isFinite(dom.priceLow) && Number.isFinite(dom.priceHigh) && dom.priceHigh > dom.priceLow) {
        setCameraPriceDomainByCaseTf(prev => ({
          ...prev,
          [key]: { low: dom.priceLow, high: dom.priceHigh },
          [legacy]: { low: dom.priceLow, high: dom.priceHigh },
        }));
      }
    }, 350);
  };
  const handleTradingViewVisibleRangeChange = useCallback((dom: { start: string; end: string; visibleBars: number }) => {
    if (cameraViewOwnerRef.current === 'TIMEFRAME_SWITCH') return;
    if (pendingCameraIntentAwaitingTvFitRef.current) return;
    if (isPostRoutineSettleActive()) return;
    visibleCameraDomainRef.current = {
      start: dom.start,
      end: dom.end,
      visibleBars: dom.visibleBars,
    };
    const next = Number(dom.visibleBars || 0);
    setVisibleBarCount((prev) => (prev === next ? prev : next));
    if (cameraMode === 'LOCKED') return;
    const activeTf = String(activeTimeframeRef.current || timeframe).toUpperCase();
    if (activeTf === 'H1') {
      if (!shouldPersistH1ChartMemory(dom, candlesRef.current)) return;
    } else if (!shouldPersistChartMemory(dom, activeTf)) {
      return;
    }
    const key = cameraKeyRef.current;
    const legacy = legacyChartMemoryKey(activeCaseDisplayIdRef.current || 'global', activeTimeframeRef.current);
    setCameraDomainByCaseTf((prev) => ({
      ...prev,
      [key]: { start: dom.start, end: dom.end, visibleBars: dom.visibleBars },
      [legacy]: { start: dom.start, end: dom.end, visibleBars: dom.visibleBars },
    }));
  }, [cameraMode, timeframe]);
  const handleTradingViewFitApplied = useCallback((detail: TradingViewFitAppliedDetail) => {
    const awaitingTvFit = pendingCameraIntentAwaitingTvFitRef.current;
    if (detail.kind !== 'routine-memory' && !awaitingTvFit) return;
    pendingCameraIntentRef.current = { intent: 'NONE' };
    pendingCameraIntentAwaitingTvFitRef.current = false;
    if (detail.kind === 'routine-memory') {
      activatePostRoutineSettle(500);
      if (routineSettleTimerRef.current) window.clearTimeout(routineSettleTimerRef.current);
      routineSettleTimerRef.current = window.setTimeout(() => {
        routineSettleTimerRef.current = null;
        activateRoutineFitLock(String(activeTimeframeRef.current || timeframe));
        setCameraViewOwnerWithLog('AUTO', 'TradingViewChart.routineSettle', 'routine-tf-memory-settled');
      }, 520);
      return;
    }
  }, [timeframe]);
  const restoreLiveMemoryCameraAfterReplay = useCallback(() => {
    if (chartRendererRef.current !== 'tradingview') return;
    const caseId = String(activeCaseDisplayIdRef.current || 'global');
    const tf = String(activeTimeframeRef.current || timeframe).toUpperCase();
    const rows = candlesRef.current;
    if (!rows.length) return;
    const mem = readChartMemoryFromStore(
      cameraDomainByCaseTf,
      caseId,
      symbol,
      tf,
      cameraPriceDomainByCaseTf,
    );
    const dom = visibleCameraDomainRef.current;
    const centerFromDom = dom?.start && dom?.end
      && Number.isFinite(new Date(dom.start).getTime())
      && Number.isFinite(new Date(dom.end).getTime())
      ? new Date((new Date(dom.start).getTime() + new Date(dom.end).getTime()) / 2).toISOString()
      : null;
    const memKey = chartMemoryKey(caseId, symbol, tf);
    const sanitized = sanitizeRoutineMemoryCameraAfterLoad({
      intent: 'PRESERVE_OR_NEAREST_TIME',
      reason: `routine-tf-memory-replay-exit:${tf}`,
      targetTime: centerFromDom || mem?.start || rows[rows.length - 1]?.time || null,
      fitWindow: memoryFitWindowFromChartMemory(mem),
      priceDomain: cameraPriceDomainByCaseTf[memKey] || null,
    }, rows, tf);
    pendingCameraIntentAwaitingTvFitRef.current = true;
    pendingCameraIntentRef.current = {
      intent: sanitized.intent as CameraIntent,
      targetTime: sanitized.targetTime,
      reason: sanitized.reason,
      fitWindow: sanitized.fitWindow,
      priceDomain: sanitized.priceDomain,
    };
    applyCameraCommand(
      sanitized.intent as CameraIntent,
      sanitized.targetTime,
      sanitized.reason,
      undefined,
      sanitized.fitWindow,
      sanitized.priceDomain,
    );
  }, [cameraDomainByCaseTf, cameraPriceDomainByCaseTf, symbol, timeframe]);
  useEffect(() => {
    tradingViewCameraBridge.current.owner = cameraViewOwner;
    tradingViewCameraBridge.current.pendingFitReason = pendingCameraIntentRef.current.intent !== 'NONE'
      ? (pendingCameraIntentRef.current.reason || null)
      : (isRoutineTfMemoryReason(cameraCommand.reason) ? cameraCommand.reason : null);
    tradingViewCameraBridge.current.pendingCameraIntentActive = pendingCameraIntentRef.current.intent !== 'NONE'
      || pendingCameraIntentAwaitingTvFitRef.current;
    tradingViewCameraBridge.current.routineAnchorSource = pendingCameraIntentRef.current.anchorSource
      || (isRoutineTfMemoryReason(cameraCommand.reason) ? tradingViewCameraBridge.current.routineAnchorSource : null);
    tradingViewCameraBridge.current.onFitApplied = handleTradingViewFitApplied;
    tradingViewCameraBridge.current.onVisibleRangeChange = handleTradingViewVisibleRangeChange;
    tradingViewCameraBridge.current.onUserPanZoom = () => {
      if (routineSettleTimerRef.current) {
        window.clearTimeout(routineSettleTimerRef.current);
        routineSettleTimerRef.current = null;
      }
      clearPostRoutineSettle();
      clearRoutineFitLock();
      setCameraViewOwnerWithLog('USER_PAN_ZOOM', 'TradingViewChart.userPan', 'user-pan-zoom');
    };
  }, [cameraViewOwner, cameraCommand, handleTradingViewFitApplied, handleTradingViewVisibleRangeChange]);
  const chartDrawingsKey = legacyCameraKey;
  const candleReplayCursorTime = replayCursorByKey[globalReplayKey]
    ?? replayCursorByKey[legacyCameraKey]
    ?? null;
  const candleReplayCursorTimeRef = useRef<string | null>(null);
  const candleReplayIndexRef = useRef(0);
  const candleReplayModeRef = useRef(false);
  useEffect(() => { candleReplayCursorTimeRef.current = candleReplayCursorTime; }, [candleReplayCursorTime]);
  useEffect(() => { candleReplayIndexRef.current = candleReplayIndex; }, [candleReplayIndex]);
  useEffect(() => { candleReplayModeRef.current = candleReplayMode; }, [candleReplayMode]);
  const setCandleReplayCursorTime = (time: string | null) => {
    setReplayCursorByKey((prev) => {
      const next = { ...prev };
      if (time) next[globalReplayKey] = time;
      else delete next[globalReplayKey];
      return next;
    });
    if (time) saveReplayCursorForKey(globalReplayKey, time);
    else saveReplayCursorForKey(globalReplayKey, null);
    const structuralRangeId = activeStructuralRangeIdRef.current;
    if (time && structuralRangeId) {
      const tf = String(timeframe).toUpperCase();
      const win = rangeWindowByTf[tf] || rangeWindow;
      saveStructuralReplayCursorForScope(
        buildStructuralReplayScopeKey({
          symbol: String(symbol).toUpperCase(),
          caseId: String(activeCaseDisplayId || 'global'),
          timeframe: tf,
          rangeId: structuralRangeId,
          loadWindowStart: win?.start || '',
          loadWindowEnd: win?.end || win?.start || '',
        }),
        time,
      );
    }
  };
  const [chartDrawings, setChartDrawings] = useState<ChartDrawing[]>([]);
  const [chartDrawTool, setChartDrawTool] = useState<ChartDrawTool>('off');
  const [chartDrawColor, setChartDrawColor] = useState<string>(CHART_DRAWING_COLORS[0]);
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const tradeIdeasKey = tradeIdeasStorageKey(symbol, timeframe, activeCaseDisplayId || 'global');
  const [chartTradeIdeas, setChartTradeIdeas] = useState<ChartTradeIdea[]>([]);
  const [tradeIdeaDraft, setTradeIdeaDraft] = useState<ChartTradeIdeaDraft>(() => emptyTradeIdeaDraft());
  const [tradePickMode, setTradePickMode] = useState<TradeIdeaPickKind | null>(null);
  const [selectedTradeIdeaId, setSelectedTradeIdeaId] = useState<string | null>(null);
  const [tradeIdeaSaving, setTradeIdeaSaving] = useState(false);
  const lockedCameraDomain = cameraDomainByCaseTf[cameraKey] || null;
  const caseSaveInFlightRef = useRef<Set<string>>(new Set());
  const [bundleSaving, setBundleSaving] = useState(false);
  const [rawMarkSaving, setRawMarkSaving] = useState(false);
  const [structureLayer, setStructureLayer] = useLocalStorage<StructureLayer>('fx_tm_structure_layer_phase3', 'WEEKLY');
  useEffect(() => {
    if (skipSelectionClearForTfSwitchRef.current) return;
    setSelectedCandle(null);
    setSelectedCandlePoint(null);
    setTradingViewCrosshairCandle(null);
    setTradingViewSelectionWarning(null);
    applyTvMappingSelectionClear();
    setRhAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
    setRlAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
    setBhAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
    setBlAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
  }, [symbol, timeframe, structureLayer, chartRenderer, tradingViewSelectedCandleMode]);

  useEffect(() => {
    if (chartRenderer !== 'tradingview' || !tradingViewMappingInputEnabled) {
      applyTvMappingSelectionClear();
      return;
    }
    const admitted = admittedMappingInputCandleRef.current;
    if (!admitted?.time) return;
    const stillLoaded = candles.some((c) => String(c?.time || '') === String(admitted.time));
    if (stillLoaded) return;
    applyTvMappingSelectionClear();
    setTradingViewSelectionWarning('Admitted candle left the loaded feed — click a visible bar again.');
  }, [chartRenderer, tradingViewMappingInputEnabled, symbol, timeframe, candles]);
  const [mappingViewContext, setMappingViewContext] = useState<MappingViewContext>('child');
  const mappingViewContextSyncRef = useRef(false);
  const campaignParentChartTf = useMemo(
    () => resolveParentChartTimeframe(structureLayer),
    [structureLayer],
  );
  const campaignChildChartTf = useMemo(
    () => resolveChildChartTimeframe(structureLayer, timeframe),
    [structureLayer, timeframe],
  );
  const campaignViewContextEnabled = mappingViewContextAvailable(structureLayer);
  const {
    pointCountForTimeframe: mappingDraftPointCountForTimeframe,
    parentDraft: mappingParentDraft,
    childDraft: mappingChildDraft,
  } = useMappingDraft({
    symbol,
    timeframe,
    caseId: activeCaseDisplayId || null,
    parentTimeframe: campaignParentChartTf,
    childTimeframe: campaignChildChartTf,
  });
  const activeMappingContainerDraft = mappingViewContext === 'parent' ? mappingParentDraft : mappingChildDraft;
  const activeMappingContainerTf = mappingViewContext === 'parent' ? campaignParentChartTf : campaignChildChartTf;
  const viewportClampStoreKey = `${String(symbol).toUpperCase()}|${activeCaseDisplayId || ''}|${structureLayer}`;
  const {
    isClamped: viewportIsClamped,
    activeClamp: viewportActiveClamp,
    canDrillDown: viewportCanDrillDown,
    drillDown: drillDownViewport,
    unlockGlobalView,
  } = useViewportClamping({
    storeKey: viewportClampStoreKey,
    containerStartTime: activeMappingContainerDraft?.startTime,
    containerEndTime: activeMappingContainerDraft?.endTime,
    containerTimeframe: activeMappingContainerTf,
    viewContext: mappingViewContext,
    chartTimeframe: timeframe,
  });
  useEffect(() => {
    setMappingViewContext('child');
    unlockGlobalView();
  }, [structureLayer]);
  const [rangeScope, setRangeScope] = useLocalStorage<RangeScope>('fx_tm_range_scope_v1', 'MAJOR');
  const [sourceTimeframe, setSourceTimeframe] = useLocalStorage<string>('fx_tm_structure_source_tf_phase3', 'W1');
  useEffect(() => { structureLayerRef.current = structureLayer; }, [structureLayer]);
  useEffect(() => { sourceTimeframeRef.current = sourceTimeframe; }, [sourceTimeframe]);
  const [structuralSaving, setStructuralSaving] = useState(false);
  const [inspectorCommitFlash, setInspectorCommitFlash] = useState<'idle' | 'success'>('idle');
  const inspectorCommitFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [structuralRanges, setStructuralRanges] = useState<StructuralRange[]>([]);
  const [savedStructuralRanges, setSavedStructuralRanges] = useState<StructuralRange[]>([]);
  const [lastSavedRangeConfirmation, setLastSavedRangeConfirmation] = useState<any>(null);
  const [selectedParentRangeId, setSelectedParentRangeId] = useLocalStorage<string>('fx_tm_selected_parent_range_id_phase3', '');
  const [activeStructuralRangeId, setActiveStructuralRangeId] = useState<string>('');
  const activeStructuralRangeIdRef = useRef('');
  const selectedParentRangeIdRef = useRef('');
  const skipSavedReplayHydrateRef = useRef(false);
  const structuralDataLoadWindowRef = useRef<CandleLoadWindow | null>(null);
  const structuralVisualContextRef = useRef<{ start: string; end: string } | null>(null);
  const structuralReplayExtendInFlightRef = useRef(false);
  const replayStepInFlightRef = useRef(false);
  activeStructuralRangeIdRef.current = activeStructuralRangeId;
  selectedParentRangeIdRef.current = selectedParentRangeId;
  const [rhAnchor, setRhAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [rlAnchor, setRlAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const rhAnchorRef = useRef(rhAnchor);
  const rlAnchorRef = useRef(rlAnchor);
  rhAnchorRef.current = rhAnchor;
  rlAnchorRef.current = rlAnchor;
  const [structuralAnchorsByLayer, setStructuralAnchorsByLayer] = useLocalStorage<Partial<Record<StructureLayer, LayerAnchorPair>>>(
    'fx_tm_structural_anchors_by_layer_v1',
    {},
  );
  const [bhAnchor, setBhAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [blAnchor, setBlAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [quickEventSaving, setQuickEventSaving] = useState(false);
  const fingerErrorStackKey = useMemo(
    () => `fx_tm_finger_error_stack_v1|${String(symbol).toUpperCase()}|${String(rawActiveCaseId || activeCaseId || '')}|${timeframe}`,
    [symbol, rawActiveCaseId, activeCaseId, timeframe],
  );
  const {
    stack: quickEventHistory,
    setStack: setQuickEventHistory,
    push: pushQuickEvent,
    undo: popQuickEventFromStack,
    canUndo: canUndoQuickEvent,
    peek: lastSavedQuickEvent,
  } = useFingerErrorStack<any>(fingerErrorStackKey);
  const [structuralRangeDraftDirty, setStructuralRangeDraftDirty] = useState(false);
  const [structuralBosDraftDirty, setStructuralBosDraftDirty] = useState(false);
  const [lastRangeLifecyclePatchWarning, setLastRangeLifecyclePatchWarning] = useState<string | null>(null);
  const [chainDraftMode, setChainDraftMode] = useState(false);
  const [bosNextRangePrompt, setBosNextRangePrompt] = useState<BosNextRangePromptResult | null>(null);
  const bosPromptHandledKeysRef = useRef<Set<string>>(new Set());
  const [guidedCursor, setGuidedCursor] = useState<GuidedMappingCursor | null>(null);
  const [childMappingSession, setChildMappingSession] = useState<ChildMappingSession | null>(null);
  const lastGuidedChildSaveRef = useRef<{
    rangeId: string;
    rangeEndTime?: string | null;
    bosTime?: string | null;
  } | null>(null);
  const guidedCursorRef = useRef<GuidedMappingCursor | null>(null);
  guidedCursorRef.current = guidedCursor;

  const applyStructuralReplayRestore = (
    candleRows: Candle[],
    args: {
      range?: any;
      chartTf?: string;
      loadWindowStart?: string | null;
      loadWindowEnd?: string | null;
      reason: string;
    },
  ) => {
    if (chartRendererRef.current === 'tradingview' && tradingViewMappingInputEnabledRef.current) {
      return null;
    }
    if (!candleRows.length) {
      setMessage(replayPlayForwardStatusMessage('no-candles'));
      return null;
    }
    const chartTf = String(args.chartTf || timeframe).toUpperCase();
    const caseTfKey = `${activeCaseDisplayId || 'global'}_${chartTf}`;
    const rangeId = String(args.range?.range_id || args.range?.id || activeStructuralRangeIdRef.current || '');
    const loadStart = args.loadWindowStart
      || structuralDataLoadWindowRef.current?.start
      || rangeWindowFieldsFromSavedRange(args.range || {}).start
      || '';
    const loadEnd = args.loadWindowEnd
      || structuralDataLoadWindowRef.current?.end
      || rangeWindowFieldsFromSavedRange(args.range || {}).end
      || loadStart;
    const horizonExtendAvailable = !!(
      (activeStructuralRangeIdRef.current || selectedParentRangeIdRef.current)
      && structuralDataLoadWindowRef.current?.end
    );
    const scope: StructuralReplayScope = {
      symbol: String(symbol).toUpperCase(),
      caseId: String(activeCaseDisplayId || 'global'),
      timeframe: chartTf,
      rangeId,
      loadWindowStart: loadStart,
      loadWindowEnd: loadEnd,
    };
    const scopeKey = buildStructuralReplayScopeKey(scope);
    const activeGuided = guidedCursorRef.current;
    const scopedCursor = loadStructuralReplayCursorForScope(scopeKey);
    const sessionCursor = replayCursorByKey[globalReplayCursorKey(String(activeCaseDisplayId || 'global'), String(symbol).toUpperCase())]
      ?? replayCursorByKey[caseTfKey]
      ?? null;
    const decision = resolveStructuralReplayRestore({
      candles: candleRows,
      scope,
      scopedCursorTime: scopedCursor,
      sessionCursorTime: sessionCursor,
      range: args.range,
      guidedCursorTimeMs: activeGuided?.active ? activeGuided.cursor_time_ms : null,
      horizonExtendAvailable,
    });
    skipSavedReplayHydrateRef.current = true;
    setCandleReplayPlaying(false);
    setCandleReplayMode(true);
    setCandleReplayIndex(decision.index);
    if (decision.time) {
      setCandleReplayCursorTime(decision.time);
      saveStructuralReplayCursorForScope(scopeKey, decision.time);
    }
    if (
      decision.action === 'initialize'
      && (decision.reason === 'blocked_at_last_bar' || decision.reason === 'outside_window')
      && sessionCursor
    ) {
      setReplayCursorByKey((prev) => {
        const next = { ...prev };
        delete next[globalReplayCursorKey(String(activeCaseDisplayId || 'global'), String(symbol).toUpperCase())];
        return next;
      });
      saveReplayCursorForKey(globalReplayCursorKey(String(activeCaseDisplayId || 'global'), String(symbol).toUpperCase()), null);
    }
    const c = candleRows[decision.index];
    if (c) {
      setSelectedCandle(c);
      setSelectedCandlePoint({ price: Number(c.close.toFixed(2)) });
    }
    const restoreMsg = replayRestoreStatusMessage(decision);
    const blockMsg = replayPlayForwardStatusMessage(decision.playForwardReason);
    const actionLabel = decision.action === 'preserve' ? 'Resumed' : 'Initialized';
    setMessage(
      [
        `${actionLabel} replay at ${shortTime(decision.time || '', chartTf)} (${decision.index + 1}/${candleRows.length})`,
        restoreMsg,
        blockMsg,
        decision.action === 'preserve' ? '' : args.reason,
      ].filter(Boolean).join(' · '),
    );
    cameraLog('structural replay restore', {
      action: decision.action,
      reason: decision.reason,
      candidateSource: decision.candidateSource,
      scopeKey,
      chartTf,
      index: decision.index,
      playForwardEnabled: decision.playForwardEnabled,
      seedAdjusted: decision.seedAdjusted,
    });
    return decision;
  };

  const [autoChainSave, setAutoChainSave] = useLocalStorage<boolean>('fx_tm_auto_chain_save_v1', true);
  const autoChainSaveAttemptRef = useRef<string>('');
  const autoRangeSaveAttemptRef = useRef<string>('');
  const [toolsPanelSection, setToolsPanelSection] = useState<'correction' | 'dashboard' | 'narrative' | 'trade' | 'admin'>('correction');
  const [hierarchyPathOnly, setHierarchyPathOnly] = useLocalStorage<boolean>('fx_tm_hierarchy_path_only_v1', true);
  const [hierarchyShowSiblings, setHierarchyShowSiblings] = useLocalStorage<boolean>('fx_tm_hierarchy_show_siblings_v1', false);
  const [hierarchyShowChildren, setHierarchyShowChildren] = useLocalStorage<boolean>('fx_tm_hierarchy_show_children_v1', false);
  const [hierarchyShowAll, setHierarchyShowAll] = useLocalStorage<boolean>('fx_tm_hierarchy_show_all_v1', false);
  const [hierarchyCollapsedIds, setHierarchyCollapsedIds] = useState<string[]>([]);
  const [eventBrowserOpen, setEventBrowserOpen] = useState(false);
  const chartMapStageRef = useRef<HTMLDivElement>(null);
  const [rangeLineHiddenByCase, setRangeLineHiddenByCase] = useLocalStorage<Record<string, string[]>>('fx_tm_range_line_hidden_v1', {});
  const [allRangeGuideLinesHiddenByCase, setAllRangeGuideLinesHiddenByCase] = useLocalStorage<Record<string, boolean>>('fx_tm_all_range_guide_lines_hidden_v1', {});
  const caseLineHiddenKey = activeCaseDisplayId || 'global';
  const allRangeGuideLinesHidden = !!allRangeGuideLinesHiddenByCase[caseLineHiddenKey];
  const [chartMappingFocusMode, setChartMappingFocusMode] = useLocalStorage<boolean>('fx_tm_chart_mapping_focus_v1', false);
  const [chartFocusShowAllRanges, setChartFocusShowAllRanges] = useLocalStorage<boolean>('fx_tm_chart_focus_show_all_v1', false);
  const prevStructureLayerForFocusRef = useRef<StructureLayer | null>(null);
  useEffect(() => {
    if (prevStructureLayerForFocusRef.current === structureLayer) return;
    prevStructureLayerForFocusRef.current = structureLayer;
    if (structureLayer === 'INTRADAY' || structureLayer === 'MICRO') {
      setChartMappingFocusMode(true);
    } else {
      setChartMappingFocusMode(false);
      setChartFocusShowAllRanges(false);
    }
  }, [structureLayer, setChartMappingFocusMode, setChartFocusShowAllRanges]);
  const [explorerMappingMode, setExplorerMappingMode] = useLocalStorage<ExplorerMappingMode>(
    'fx_tm_explorer_mapping_mode_v1',
    'htf',
  );
  const [gapQueueOpen, setGapQueueOpen] = useLocalStorage<boolean>('fx_tm_gap_queue_open_v1', true);
  const [explorerYearFilter, setExplorerYearFilter] = useLocalStorage<string>('fx_tm_explorer_year_v1', 'all');
  const [caseMetadataOpen, setCaseMetadataOpen] = useState(false);
  const [hierarchyAudit, setHierarchyAudit] = useState<any>(null);
  const [caseScope, setCaseScope] = useState<CaseScope>(() => timeframeToScope(timeframe));
  useEffect(()=>{ setCaseScope(timeframeToScope(timeframe)); }, [timeframe]);
  const [historyMarkMode, setHistoryMarkMode] = useLocalStorage<string>('fx_tm_history_mark_mode_v087_17', 'OFF');
  const [showRejectedMarks, setShowRejectedMarks] = useLocalStorage<boolean>('fx_tm_show_rejected_candidate_marks_v087_17', false);
  const [sessionEventIds, setSessionEventIds] = useState<Set<string>>(() => new Set());
  const [htfCandidates, setHtfCandidates] = useState<HTFCandidate[]>([]);
  const [htfRejectedCandidateIds, setHtfRejectedCandidateIds] = useLocalStorage<string[]>('fx_tm_htf_rejected_candidates_v087_8', []);
  const [htfAcceptedSuggestionLocks, setHtfAcceptedSuggestionLocks] = useLocalStorage<string[]>('fx_tm_htf_accepted_suggestion_locks_v087_16', []);
  const [htfStateNotes, setHtfStateNotes] = useLocalStorage<Record<string,any>>('fx_tm_htf_state_notes_v087_8', {});

  const currentPlaybackFrame = playbackFrames[playbackIndex] || null;
  const effectiveReplayIndex = useMemo(() => {
    if (!candles.length) return 0;
    if (candleReplayMode && candleReplayCursorTime) return candleIndexAtOrBefore(candles, candleReplayCursorTime);
    return clamp(candleReplayIndex, 0, candles.length - 1);
  }, [candles, candleReplayMode, candleReplayCursorTime, candleReplayIndex]);
  const replayCandle = candles.length ? candles[clamp(effectiveReplayIndex, 0, candles.length - 1)] : null;
  const mappingInputCandle = useMemo((): Candle | null => (
    resolveMappingInputCandle({
      chartRenderer,
      mappingInputEnabled: tradingViewMappingInputEnabled,
      admittedMappingInputCandle,
      selectedCandle,
      replayCandle,
      candleReplayMode,
    }) as Candle | null
  ), [
    chartRenderer,
    tradingViewMappingInputEnabled,
    admittedMappingInputCandle,
    selectedCandle,
    replayCandle,
    candleReplayMode,
  ]);
  const tradingViewAdmittedSelectedCandle = useMemo((): TradingViewSelectedCandle | null => {
    if (chartRenderer !== 'tradingview' || !tradingViewMappingInputEnabled || !admittedMappingInputCandle) return null;
    return commitTvMappingSelection({
      row: admittedMappingInputCandle,
      sourceTimeframe,
    })?.tradingViewSelectedCandle ?? null;
  }, [chartRenderer, tradingViewMappingInputEnabled, admittedMappingInputCandle, sourceTimeframe]);
  const canStructuralReplayExtendHorizon = !!(
    (activeStructuralRangeId || selectedParentRangeId)
    && structuralDataLoadWindowRef.current?.end
  );
  const replayForwardBlocked = !candles.length
    || (effectiveReplayIndex >= candles.length - 1 && !canStructuralReplayExtendHorizon);
  const activeReplayCandle = selectedCandle || replayCandle;
  const detectorContextCandle = (candleReplayMode && replayCandle) ? replayCandle : (selectedCandle || replayCandle);
  const visibleCandles = useMemo(() => {
    if (!candleReplayMode || !candles.length || !replayCandle) return candles;
    const cut = new Date(String(replayCandle.time)).getTime();
    return candles.filter(c => new Date(String(c.time)).getTime() <= cut);
  }, [candles, candleReplayMode, replayCandle?.time]);
  const mapEventsVisibleToReplay = useMemo(() => {
    if (!candleReplayMode || !replayCandle) return events;
    const cut = new Date(replayCandle.time).getTime();
    return events.filter(e => !e.time || new Date(String(e.time)).getTime() <= cut);
  }, [events, candleReplayMode, replayCandle?.time]);



  const seedIdeaEvents = useMemo<MapEvent[]>(() => {
    const out:MapEvent[] = [];
    const cut = candleReplayMode && replayCandle ? new Date(replayCandle.time).getTime() : null;
    const pushAnchor = (idea:any, key:string, label:string) => {
      const price = parseNum(idea?.[key]);
      if (!Number.isFinite(price)) return;
      const t = idea?.[`${key}_time`] || idea?.replay_candle_time;
      if (!t) return;
      const ms = new Date(String(t)).getTime();
      if (cut && Number.isFinite(cut) && Number.isFinite(ms) && ms > cut) return;
      out.push({
        id: `seed_${idea.id}_${key}`,
        source: 'seed',
        event_type: label,
        event_name: label,
        time: String(t),
        price: Number(price),
        notes: idea?.seed_name || 'Case',
      });
    };
    for (const idea of seedIdeas || []) {
      pushAnchor(idea, 'weekly_high', 'SEED_WH');
      pushAnchor(idea, 'weekly_low', 'SEED_WL');
      pushAnchor(idea, 'daily_high', 'SEED_DH');
      pushAnchor(idea, 'daily_low', 'SEED_DL');
    }
    return out;
  }, [seedIdeas, candleReplayMode, replayCandle?.time]);

  const structuralDraftEvents = useMemo<MapEvent[]>(() => {
    const out:MapEvent[] = [];
    const pushDraft = (anchor:StructuralAnchor, type:'BH'|'BL', name:string) => {
      if (!anchor.price || !anchor.time) return;
      out.push({
        id: `structural_draft_${type}_${timeframe}`,
        source: 'candidate',
        event_type: type,
        event_name: `${name} Draft`,
        time: anchor.time,
        price: Number(anchor.price),
        notes: 'Unsaved structural draft marker',
        candidate_status: 'CANDIDATE',
        meta_json: {
          draft_only: true,
          structure_layer: structureLayer,
          source_timeframe: sourceTimeframe,
          chart_timeframe: timeframe,
        },
      });
    };
    pushDraft(bhAnchor, 'BH', 'Break High');
    pushDraft(blAnchor, 'BL', 'Break Low');
    return out;
  }, [bhAnchor.price, bhAnchor.time, blAnchor.price, blAnchor.time, structureLayer, sourceTimeframe, timeframe]);

  const visibleEvents = useMemo(() => {
    // v087.17: Stored does not mean displayed. The database can remember everything;
    // the chart should only show the slice that helps the current mapping decision.
    const mapRows = safeArray<MapEvent>(mapEventsVisibleToReplay);
    const mode = String(historyMarkMode || 'ACTIVE_RANGE').toUpperCase();
    const selectedMs = (selectedCandle?.time || replayCandle?.time) ? new Date(String(selectedCandle?.time || replayCandle?.time)).getTime() : NaN;
    const nearbyStart = Number.isFinite(selectedMs) ? selectedMs - 1000 * 60 * 60 * 24 * 7 * 12 : NaN; // broad enough for W1/D1 replay without needing candle indexes here
    const nearbyEnd = Number.isFinite(selectedMs) ? selectedMs + 1000 * 60 * 60 * 24 * 7 * 12 : NaN;
    const filtered = mapRows.filter((e:any) => {
      if (!showRejectedMarks && isRejectedCandidateEvent(e)) return false;
      if (mode === 'OFF') return isStructuralChartEventType(e?.event_type || e?.event_name);
      if (mode === 'SESSION') return sessionEventIds.has(String(e?.id));
      if (mode === 'ACTIVE_RANGE') return !rangeWindow.start || !rangeWindow.end ? sessionEventIds.has(String(e?.id)) : eventInWindow(e, rangeWindow.start, rangeWindow.end);
      if (mode === 'ACTIVE_CASE') {
        // v087.18b reload-safe guard: visibleEvents is computed before the case ledger memo is declared.
        // Do not reference activeCaseLedger here or the renderer can crash on cold boot.
        const eventCase = caseIdOfEvent(e);
        return !!(activeCaseId && eventCase != null && String(eventCase) === String(activeCaseId));
      }
      if (mode === 'NEARBY') {
        const ms = new Date(String(e?.time || '')).getTime();
        return Number.isFinite(ms) && Number.isFinite(nearbyStart) && ms >= nearbyStart && ms <= nearbyEnd;
      }
      return true; // ALL
    });
    return [...filtered, ...structuralDraftEvents];
  }, [mapEventsVisibleToReplay, structuralDraftEvents, historyMarkMode, showRejectedMarks, sessionEventIds, rangeWindow.start, rangeWindow.end, activeCaseId, selectedCandle?.time, replayCandle?.time]);
  const narrativeFacts = useMemo(() => {
    return (visibleEvents || [])
      .filter((e:any) => e?.source !== 'seed' && e?.event_type)
      .map((e:any) => ({
        ...e,
        _ms: e.time ? new Date(String(e.time)).getTime() : 0,
        _label: markerLabel(e.event_type || e.event_name),
      }))
      .sort((a:any,b:any) => (a._ms || 0) - (b._ms || 0) || String(a.id).localeCompare(String(b.id)));
  }, [visibleEvents]);


  const eventLedgerRows = useMemo(() => {
    const rows = safeArray<MapEvent>(eventsByTf?.[timeframe])
      .filter((e:any) => e?.event_type && e?.time)
      .map((e:any) => ({
        ...e,
        _ms: new Date(String(e.time)).getTime(),
        _label: markerLabel(e.event_type || e.event_name),
      }))
      .sort((a:any,b:any) => (a._ms || 0) - (b._ms || 0) || String(a.id).localeCompare(String(b.id)));
    return rows;
  }, [eventsByTf, timeframe]);

  const rangeCompilerPreview = useMemo(() => {
    const tfRange = rangeByTf[timeframe] || {};
    const tfWindow = rangeWindowByTf[timeframe] || {};
    const rows = safeArray<MapEvent>(eventLedgerRows);
    const rangeHighEvents = rows.filter((e:any)=>isExplicitRangeHighCommand(e?.event_type));
    const rangeLowEvents = rows.filter((e:any)=>isExplicitRangeLowCommand(e?.event_type));
    const latestHigh = rangeHighEvents[rangeHighEvents.length - 1];
    const latestLow = rangeLowEvents[rangeLowEvents.length - 1];
    return {
      high: tfRange.high || (latestHigh ? Number(latestHigh.price).toFixed(2) : ''),
      highTime: latestHigh?.time || tfWindow.end || '',
      low: tfRange.low || (latestLow ? Number(latestLow.price).toFixed(2) : ''),
      lowTime: latestLow?.time || tfWindow.start || '',
      eventCount: rows.length,
      highCount: rangeHighEvents.length,
      lowCount: rangeLowEvents.length,
    };
  }, [eventLedgerRows, rangeByTf, rangeWindowByTf, timeframe]);

  const jumpToLedgerEvent = (ev:any) => {
    if (!ev?.time) return;
    const idx = candles.findIndex(c => String(c.time) === String(ev.time));
    if (idx >= 0) {
      setCandleReplayFrame(idx);
      setSelectedCandle(candles[idx]);
      setSelectedCandlePoint({ price: Number(ev.price) || Number(candles[idx].close) });
      setMessage(`Jumped to ${markerLabel(ev.event_type)} · ${shortTime(ev.time, timeframe)}. Tiny miracle: the ledger knows where it lives.`);
    } else {
      setJumpDate(String(ev.time).slice(0,10));
      setJumpToken(x=>x+1);
      setMessage(`Jumping near ${shortTime(ev.time, timeframe)} from ledger row.`);
    }
  };

  const autoCaseAnchors = useMemo(() => {
    const all = Object.values(eventsByTf || {}).flatMap((v:any)=>safeArray<MapEvent>(v)).filter(Boolean) as MapEvent[];
    const latest = (patterns: RegExp[]) => [...all]
      .filter((e:any) => patterns.some(rx => rx.test(String(e.event_type || e.event_name || '').toUpperCase())))
      .sort((a:any,b:any) => new Date(String(b.time || 0)).getTime() - new Date(String(a.time || 0)).getTime())[0];
    const priceOf = (ev?:MapEvent) => ev && Number.isFinite(Number(ev.price)) ? Number(ev.price).toFixed(2) : '';
    return {
      macro_high: rangeByTf.MN1?.high || priceOf(latest([/MACRO_.*HIGH/, /MACRO_EXTREME_PREMIUM/, /MACRO_ABOVE_FP/, /^RANGE_HIGH$/])),
      macro_low: rangeByTf.MN1?.low || priceOf(latest([/MACRO_.*LOW/, /MACRO_EXTREME_DISCOUNT/, /MACRO_BELOW_FP/, /^RANGE_LOW$/])),
      weekly_high: rangeByTf.W1?.high || priceOf(latest([/SET_WEEKLY_RANGE_HIGH/, /WEEKLY_.*HIGH/, /WEEKLY_EXTREME_PREMIUM/, /WEEKLY_ABOVE_FP/, /^RANGE_HIGH$/])),
      weekly_low: rangeByTf.W1?.low || priceOf(latest([/SET_WEEKLY_RANGE_LOW/, /WEEKLY_.*LOW/, /WEEKLY_EXTREME_DISCOUNT/, /WEEKLY_BELOW_FP/, /^RANGE_LOW$/])),
      daily_high: rangeByTf.D1?.high || priceOf(latest([/SET_DAILY_RANGE_HIGH/, /DAILY_.*HIGH/, /DAILY_EXTREME_PREMIUM/, /DAILY_ABOVE_FP/, /DAILY_PDH_REFERENCE/, /^RANGE_HIGH$/])),
      daily_low: rangeByTf.D1?.low || priceOf(latest([/SET_DAILY_RANGE_LOW/, /DAILY_.*LOW/, /DAILY_EXTREME_DISCOUNT/, /DAILY_BELOW_FP/, /DAILY_PDL_REFERENCE/, /^RANGE_LOW$/])),
    };
  }, [eventsByTf, rangeByTf]);

  const mergedCaseAnchors = useMemo(() => ({ ...autoCaseAnchors, ...Object.fromEntries(Object.entries(seedAnchors).filter(([,v]) => String(v ?? '').trim() !== '')) }), [autoCaseAnchors, seedAnchors]);

  const autoFillCaseAnchors = () => {
    setSeedAnchors((prev:any) => ({ ...autoCaseAnchors, ...prev }));
    setMessage('Auto-filled Case anchors from plotted map points/range memory. The form finally does less pretending.');
  };

  const caseTimeframe = scopeToTimeframe(caseScope);
  const caseRange = rangeByTf[caseTimeframe] || {};
  const caseWindow = rangeWindowByTf[caseTimeframe] || {};
  const caseHighKey = `${caseScope.toLowerCase()}_high`;
  const caseLowKey = `${caseScope.toLowerCase()}_low`;
  const caseHigh = seedAnchors.case_high || seedAnchors[caseHighKey] || caseRange.high || (autoCaseAnchors as any)[caseHighKey] || '';
  const caseLow = seedAnchors.case_low || seedAnchors[caseLowKey] || caseRange.low || (autoCaseAnchors as any)[caseLowKey] || '';
  // v087.29c: Do not show legacy /api/v1/map event counts here. Those old event bundles
  // are not the raw mapping ledger and they were making fresh cases look like they had
  // 81 inherited events. Case Manager now treats raw ledger writes as the source of truth.
  const caseEvents = [] as MapEvent[];
  const caseAnchorWindow = useMemo(() => {
    const scopeKey = String(caseScope || '').toLowerCase();
    const highTime = seedAnchors.case_high_time || seedAnchors[`${scopeKey}_high_time`] || '';
    const lowTime = seedAnchors.case_low_time || seedAnchors[`${scopeKey}_low_time`] || '';
    return timesToWindow([highTime, lowTime]) || { start:'', end:'' };
  }, [caseScope, seedAnchors.case_high_time, seedAnchors.case_low_time, seedAnchors.weekly_high_time, seedAnchors.weekly_low_time, seedAnchors.daily_high_time, seedAnchors.daily_low_time, seedAnchors.macro_high_time, seedAnchors.macro_low_time]);
  const caseWindowStartDisplay = seedAnchors.range_start_date || caseAnchorWindow.start || '';
  const caseWindowEndDisplay = seedAnchors.range_end_date || caseAnchorWindow.end || '';

  const activeCaseRecord = useMemo(() => {
    return safeArray<any>(seedIdeas).find((idea:any) => Number(idea?.id) === Number(activeCaseId)) || null;
  }, [seedIdeas, activeCaseId]);
  const activeRawCaseRecord = useMemo(() => {
    if (!rawActiveCaseId) return null;
    return safeArray<any>(seedIdeas).find((idea:any) => String(idea?.raw_case_id || idea?.id || '') === String(rawActiveCaseId)) || null;
  }, [seedIdeas, rawActiveCaseId]);
  const activeMappingCaseContainer = rawActiveCaseId ? activeRawCaseRecord : activeCaseRecord;

  const activeCaseLedger = useMemo(() => {
    const idea:any = activeCaseRecord;
    if (!idea) return { timeframe: caseTimeframe, scope: caseScope, rows: [] as any[], hasWindow: false, start: '', end: '', high: '', low: '', highSource: '', lowSource: '', windowSource: '' };
    const payload = idea?.mos_payload || {};
    const anchors = idea?.anchors || payload?.anchors || {};
    const tf = String(idea?.case_timeframe || payload?.case_timeframe || idea?.replay_timeframe || caseTimeframe || timeframe).toUpperCase();
    const scope = String(idea?.case_scope || payload?.case_scope || timeframeToScope(tf) || caseScope).toUpperCase();
    const savedHigh = idea?.case_high || anchors?.case_high || anchors?.[`${scope.toLowerCase()}_high`] || anchors?.weekly_high || anchors?.daily_high || anchors?.macro_high || '';
    const savedLow = idea?.case_low || anchors?.case_low || anchors?.[`${scope.toLowerCase()}_low`] || anchors?.weekly_low || anchors?.daily_low || anchors?.macro_low || '';
    const times = [
      anchors?.range_start_date,
      anchors?.range_end_date,
      anchors?.case_high_time,
      anchors?.case_low_time,
      anchors?.weekly_high_time,
      anchors?.weekly_low_time,
      anchors?.daily_high_time,
      anchors?.daily_low_time,
      anchors?.macro_high_time,
      anchors?.macro_low_time,
      idea?.replay_candle_time,
      payload?.timestamp,
    ].filter(Boolean).map((x:any)=>String(x));
    const validTimes = times
      .map((t:string)=>({ t, ms: new Date(t).getTime() }))
      .filter((x:any)=>Number.isFinite(x.ms))
      .sort((a:any,b:any)=>a.ms-b.ms);
    const savedStart = anchors?.range_start_date || validTimes[0]?.t || '';
    const savedEnd = anchors?.range_end_date || validTimes[validTimes.length-1]?.t || '';
    const startMs = savedStart ? new Date(String(savedStart)).getTime() : NaN;
    const endMs = savedEnd ? new Date(String(savedEnd)).getTime() : NaN;
    const hasSavedWindow = Number.isFinite(startMs) && Number.isFinite(endMs) && Math.abs(endMs - startMs) > 0;
    const sourceRows = safeArray<MapEvent>(eventsByTf?.[tf]);
    const rows = sourceRows
      .filter((ev:any)=>{
        if (!ev?.time) return false;
        if (!hasSavedWindow) return true;
        const ms = new Date(String(ev.time)).getTime();
        const lo = Math.min(startMs, endMs);
        const hi = Math.max(startMs, endMs);
        return Number.isFinite(ms) && ms >= lo && ms <= hi;
      })
      .map((ev:any)=>({ ...ev, _ms:new Date(String(ev.time)).getTime(), _label: markerLabel(ev.event_type || ev.event_name) }))
      .sort((a:any,b:any)=>(a._ms||0)-(b._ms||0) || String(a.id).localeCompare(String(b.id)));

    // v087.5: Case is a container. If the old case row did not persist a summary
    // high/low/window, derive the summary from the linked event ledger rows instead
    // of showing the user a useless "not saved" box. The ledger remains truth;
    // this is a read-only summary, not a second source of fib anchors.
    const price = (ev:any) => Number.isFinite(Number(ev?.price)) ? Number(ev.price) : NaN;
    const fmt = (n:any) => Number.isFinite(Number(n)) ? Number(n).toFixed(2) : '';
    const explicitHighs = rows.filter((ev:any)=>isExplicitRangeHighCommand(ev?.event_type || ev?.event_name) && Number.isFinite(price(ev)));
    const explicitLows = rows.filter((ev:any)=>isExplicitRangeLowCommand(ev?.event_type || ev?.event_name) && Number.isFinite(price(ev)));
    const latestExplicitHigh = explicitHighs[explicitHighs.length - 1];
    const latestExplicitLow = explicitLows[explicitLows.length - 1];
    const allPriced = rows.filter((ev:any)=>Number.isFinite(price(ev)));
    const maxEvent = allPriced.reduce((best:any, ev:any)=>!best || price(ev) > price(best) ? ev : best, null);
    const minEvent = allPriced.reduce((best:any, ev:any)=>!best || price(ev) < price(best) ? ev : best, null);
    const high = savedHigh ? fmt(savedHigh) : latestExplicitHigh ? fmt(latestExplicitHigh.price) : maxEvent ? fmt(maxEvent.price) : '';
    const low = savedLow ? fmt(savedLow) : latestExplicitLow ? fmt(latestExplicitLow.price) : minEvent ? fmt(minEvent.price) : '';
    const highSource = savedHigh ? 'saved on case' : latestExplicitHigh ? `derived from ${markerLabel(latestExplicitHigh.event_type)}` : maxEvent ? 'derived from highest linked event' : '';
    const lowSource = savedLow ? 'saved on case' : latestExplicitLow ? `derived from ${markerLabel(latestExplicitLow.event_type)}` : minEvent ? 'derived from lowest linked event' : '';
    const firstRow = rows[0];
    const lastRow = rows[rows.length - 1];
    const start = savedStart || firstRow?.time || '';
    const end = savedEnd || lastRow?.time || '';
    const derivedStartMs = start ? new Date(String(start)).getTime() : NaN;
    const derivedEndMs = end ? new Date(String(end)).getTime() : NaN;
    const hasWindow = Number.isFinite(derivedStartMs) && Number.isFinite(derivedEndMs) && (Math.abs(derivedEndMs - derivedStartMs) > 0 || rows.length > 0);
    const windowSource = hasSavedWindow ? 'saved on case' : rows.length ? 'derived from linked ledger rows' : '';

    return { timeframe: tf, scope, rows, hasWindow, start, end, high, low, highSource, lowSource, windowSource };
  }, [activeCaseRecord, eventsByTf, caseTimeframe, caseScope, timeframe]);

  const activeCaseCandidateAudit = useMemo(() => {
    const rows = safeArray<any>(activeCaseLedger?.rows || []);
    const rejected = rows.filter(isRejectedCandidateEvent);
    const accepted = rows.filter((ev:any) => !isRejectedCandidateEvent(ev) && isAcceptedCandidateEvent(ev));
    const edited = rows.filter((ev:any) => !!eventMeta(ev)?.user_edited_price);
    return { accepted, rejected, edited };
  }, [activeCaseLedger?.rows]);

  const parentTimeframeFor = (tf:string) => {
    const t = String(tf || '').toUpperCase();
    if (t === 'D1' || t === 'H4' || t === 'H1') return 'W1';
    if (t === 'M15' || t === 'M5') return 'H1';
    return '';
  };

  const activeParentRangeOverlay = useMemo<ParentRangeOverlayLine[]>(() => {
    if (allRangeGuideLinesHidden) return [];
    const parentLayer = expectedParentStructureLayer(structureLayer);
    if (!parentLayer) return [];
    const parentRange = latestSavedRangeForLayer(
      parentLayer,
      savedStructuralRanges,
      selectedParentRangeId || undefined,
    );
    let hi = NaN;
    let lo = NaN;
    let start = '';
    let end = '';
    let parentTf = defaultSourceTimeframeForStructureLayer(parentLayer);
    if (parentRange) {
      hi = Number(parentRange.range_high_price ?? parentRange.range_high);
      lo = Number(parentRange.range_low_price ?? parentRange.range_low);
      start = String(parentRange.range_start_time || parentRange.range_high_time || '');
      end = String(parentRange.range_end_time || parentRange.range_low_time || '');
      parentTf = String(parentRange.chart_timeframe || parentRange.source_timeframe || parentTf).toUpperCase();
    } else {
      const anchors = structuralAnchorsByLayer[parentLayer];
      hi = parseNum(anchors?.rh?.price);
      lo = parseNum(anchors?.rl?.price);
      start = String(anchors?.rh?.time || '');
      end = String(anchors?.rl?.time || '');
    }
    if (!Number.isFinite(hi) || !Number.isFinite(lo)) {
      const chartParentTf = parentTimeframeFor(timeframe);
      if (chartParentTf && chartParentTf !== timeframe) {
        const parentRangeByTf = rangeByTf[chartParentTf] || {};
        const parentWindow = rangeWindowByTf[chartParentTf] || {};
        hi = parseNum(parentRangeByTf.high || (chartParentTf === 'W1' ? seedAnchors.case_high || seedAnchors.weekly_high : ''));
        lo = parseNum(parentRangeByTf.low || (chartParentTf === 'W1' ? seedAnchors.case_low || seedAnchors.weekly_low : ''));
        start = start || String(parentWindow.start || '');
        end = end || String(parentWindow.end || '');
        parentTf = chartParentTf;
      }
    }
    const direction = safeArray<any>(eventsByTf[parentTf] || [])
      .map((e:any)=>String(e?.event_type || e?.derived_event_code || '').toUpperCase())
      .find((x:string)=>x.includes('BOS_UP') || x.includes('BOS_DOWN') || x === 'BOS_UP' || x === 'BOS_DOWN') || '';
    const out:ParentRangeOverlayLine[] = [];
    if (Number.isFinite(hi)) out.push({ timeframe:parentTf, structureLayer:parentLayer, kind:'high', price:Number(hi), label:`${parentLayer} RH`, direction, start, end, rangeId: parentRange ? (parentRange.range_id || parentRange.id) : null });
    if (Number.isFinite(lo)) out.push({ timeframe:parentTf, structureLayer:parentLayer, kind:'low', price:Number(lo), label:`${parentLayer} RL`, direction, start, end, rangeId: parentRange ? (parentRange.range_id || parentRange.id) : null });
    return out;
  }, [allRangeGuideLinesHidden, structureLayer, selectedParentRangeId, savedStructuralRanges, structuralAnchorsByLayer, timeframe, rangeByTf, rangeWindowByTf, seedAnchors.case_high, seedAnchors.case_low, seedAnchors.weekly_high, seedAnchors.weekly_low, eventsByTf]);

  const jumpToParentRangeStart = () => {
    const parentTf = parentTimeframeFor(timeframe);
    const w = rangeWindowByTf[parentTf] || {};
    const start = w.start || seedAnchors.range_start_date || activeCaseRecord?.range_start_date || activeCaseRecord?.anchors?.range_start_date || '';
    if (!start) { setMessage('No parent range start found yet. Save/open the Weekly case range first, then drop to Daily.'); return; }
    setJumpDate(String(start).slice(0,10));
    setFitToken(x=>x+1);
    setMessage(`Jumped to ${parentTf} parent start ${String(start).slice(0,10)}. The chart finally remembers where the story began.`);
  };

  const startChildReplayFromParentStart = () => {
    const parentTf = parentTimeframeFor(timeframe);
    const w = rangeWindowByTf[parentTf] || {};
    const start = w.start || seedAnchors.range_start_date || activeCaseRecord?.range_start_date || activeCaseRecord?.anchors?.range_start_date || '';
    if (!start) { setMessage('No parent range start found for child replay. Save/open the Weekly range first.'); return; }
    setCandleReplayFrameByTime(String(start));
    setJumpDate(String(start).slice(0,10));
    setMessage(`Started ${timeframe} replay from ${parentTf} parent start ${String(start).slice(0,10)}. Map forward without future candles cheating.`);
  };

  const jumpToCaseLedgerEvent = (ev:any) => {
    const tf = String(activeCaseLedger.timeframe || timeframe).toUpperCase();
    if (tf !== timeframe) {
      pendingCameraIntentRef.current = { intent:'PRESERVE_OR_NEAREST_TIME', targetTime:ev?.time || null, reason:'case-ledger-timeframe-switch' };
      activeTimeframeRef.current = tf;
      setTimeframe(tf);
      setRightDeckTab('narrative');
      setMessage(`Switched to ${tf} for Case #${activeCaseId} ledger row. If the candle is shy, hit the row again after candles load.`);
      return;
    }
    jumpToLedgerEvent(ev);
  };


  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const cleanCaseDisplayName = (value?: string | null) => String(value || '').replace(/\s+·\s+[a-f0-9-]+$/i, '').trim();
  const quarterFromTime = (value?: string | null) => {
    const d = new Date(String(value || ''));
    if (!Number.isFinite(d.getTime())) return null;
    return { year: d.getFullYear(), quarter: Math.floor(d.getMonth() / 3) + 1 };
  };
  const formatQuarterCaseName = (year: number, quarter: number) => `${String(symbol || 'XAUUSD').toUpperCase()} ${year} Q${quarter}`;
  const buildQuarterCaseNameFromCandle = () => {
    const q = quarterFromTime(selectedCandle?.time || replayCandle?.time || activeReplayCandle?.time);
    return q ? formatQuarterCaseName(q.year, q.quarter) : `${String(symbol || 'XAUUSD').toUpperCase()} Case`;
  };
  const applyQuarterCaseName = () => {
    const name = buildQuarterCaseNameFromCandle();
    setSeedName(name);
    setMessage(`Case name set to "${name}". Click Create Case when ready.`);
  };
  const applyQuarterCaseNameFor = (year: number, quarter: number) => {
    const name = formatQuarterCaseName(year, quarter);
    setSeedName(name);
    setMessage(`Case name set to "${name}".`);
  };
  const monthYearLabel = (v:any) => {
    const d = new Date(String(v || ''));
    if (!Number.isFinite(d.getTime())) return '';
    return `${monthNames[d.getMonth()]}${d.getFullYear()}`;
  };
  const inferCaseWindow = () => {
    const start = seedAnchors.range_start_date || caseWindow.start || rangeWindowByTf.W1?.start || seedAnchors.case_high_time || seedAnchors.case_low_time || activeReplayCandle?.time;
    const end = seedAnchors.range_end_date || caseWindow.end || rangeWindowByTf.W1?.end || activeReplayCandle?.time;
    return { start, end };
  };
  const inferCaseNameFromWindow = () => {
    const { start, end } = inferCaseWindow();
    const a = monthYearLabel(start);
    const b = monthYearLabel(end);
    const suffix = a && b ? `${a}_${b}` : monthYearLabel(activeReplayCandle?.time) || 'Current';
    return `${String(symbol || 'XAUUSD')}_HTF_${suffix}`;
  };
  const buildCaseNameFromWindow = () => {
    const { start, end } = inferCaseWindow();
    const name = inferCaseNameFromWindow();
    setSeedName(name);
    setSeedAnchors((prev:any)=>({ ...prev, case_scope: caseScope, case_timeframe: caseTimeframe, range_start_date: start || prev.range_start_date || null, range_end_date: end || prev.range_end_date || null }));
    setMessage(`Case named ${name}. Boring name, clean database. A rare win.`);
  };
  const buildYtdCaseName = () => {
    const d = activeReplayCandle?.time ? new Date(String(activeReplayCandle.time)) : new Date();
    const name = `${String(symbol || 'XAUUSD')}_HTF_Jan${d.getFullYear()}_Current`;
    setSeedName(name);
    // v087.29c: Name YTD is only a naming helper. It must not mutate the case window,
    // because one naming click was stretching fresh 2026 anchor windows back to Jan/current.
    setSeedAnchors((prev:any)=>({ ...prev, case_scope: caseScope, case_timeframe: caseTimeframe }));
    setMessage(`Case named ${name}. Window left untouched; anchor candles remain the truth.`);
  };
  const applyMasterCaseName = () => {
    const name = buildMasterCaseName(symbol, 2019, 2026);
    setSeedName(name);
    setCaseScope('WEEKLY');
    setSeedAnchors((prev:any) => ({ ...prev, case_scope: 'WEEKLY', case_timeframe: 'W1' }));
    setMessage(`Master case name set: "${name}". Create Case — map Macro→Weekly→Daily first, LTF later.`);
  };

  const exportActiveCaseAuditJson = async () => {
    if (!activeCaseId || !activeCaseRecord) { setMessage('No active case selected. The JSON goblin needs a case first.'); return; }
    let backendAudit:any = null;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${activeCaseId}/audit`).then(x=>x.json());
      if (r?.ok) backendAudit = r;
    } catch { /* frontend export still works */ }
    const payload = {
      generated_at: new Date().toISOString(),
      audit_source: backendAudit ? 'backend_db_plus_frontend_case_view' : 'frontend_case_view_only',
      backend_audit: backendAudit,
      frontend_case: activeCaseRecord,
      active_case_id: activeCaseId,
      symbol,
      active_timeframe: timeframe,
      case_ledger: activeCaseLedger,
      candidate_audit: activeCaseCandidateAudit,
      range: { high: hasRange ? high : null, low: hasRange ? low : null, window: rangeWindow },
      measurement_range: measurementRange,
      visible_events_in_case: activeCaseLedger.rows,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type:'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `case_${activeCaseId}_db_audit_${String(symbol||'SYMBOL')}_${String(activeCaseLedger.timeframe||timeframe)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 500);
    setMessage(`Exported Case #${activeCaseId} audit JSON. Now we can inspect the itemized bill instead of trusting the pretty counter.`);
  };

  const deleteActiveCase = async () => {
    if (!activeCaseId) { setMessage('No active case selected to delete. Even deletion needs a target, sadly.'); return; }
    if (!window.confirm(`Delete Case #${activeCaseId}? This removes the case container, snapshots, and objectives. Raw map events are kept.`)) return;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${activeCaseId}`, { method:'DELETE' }).then(x=>x.json());
      if (!r?.ok) throw new Error(r?.error || r?.detail || 'Delete failed');
      setActiveCaseId(null); setActiveCaseLabel(''); setCaseSavedNotice('');
      await loadSavedCasesFromBackend();
      setMessage(`Deleted Case #${r.id}. Raw events kept; because deleting receipts by accident is how databases become crime scenes.`);
    } catch (err:any) { setMessage(`Delete case failed: ${err?.message || err}`); }
  };
  const clearAllCases = async () => {
    if (!window.confirm(`Clear ALL ${symbol} case containers? Raw map events are kept.`)) return;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/seed-ideas?symbol=${encodeURIComponent(symbol)}`, { method:'DELETE' }).then(x=>x.json());
      if (!r?.ok) throw new Error(r?.error || r?.detail || 'Clear cases failed');
      setActiveCaseId(null); setActiveCaseLabel(''); setSeedIdeas([]); setCaseSavedNotice('');
      await loadSavedCasesFromBackend();
      setMessage(`Cleared ${r.deleted_cases || 0} ${symbol} case containers. Raw event ledger remains.`);
    } catch (err:any) { setMessage(`Clear cases failed: ${err?.message || err}`); }
  };
  const resetResearchMappingDb = async () => {
    const wipeSymbols = Array.from(new Set([symbol, ...SYMBOLS].map((s) => String(s || '').trim().toUpperCase()).filter(Boolean)));
    if (!window.confirm(`HARD RESET mapping for ${wipeSymbols.join(', ')}? Deletes ALL legacy + raw mapping cases/events, structural ranges, map events, HTF snapshots, objectives, and route memory. Raw OHLC candles stay.`)) return;
    if (window.prompt('Type RESET to confirm the mapping wipe') !== 'RESET') { setMessage('Reset cancelled. The database lives another day.'); return; }
    try {
      const results = await Promise.all(wipeSymbols.map(async (sym) => {
        const [r, rawClear] = await Promise.all([
          fetch(`${BASE_URL}/api/v1/mos/research-reset`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ symbol: sym, confirm:'RESET' }) }).then(x=>x.json()),
          clearRawCases(BASE_URL, sym, 'RESET'),
        ]);
        return { sym, r, rawClear };
      }));
      const failed = results.find(({ r }) => !r?.ok);
      if (failed) throw new Error(failed.r?.error || failed.r?.detail || `Research reset failed for ${failed.sym}`);
      const rawFail = results.find(({ rawClear }) => !rawClear.ok && rawClear.httpStatus !== 404 && rawClear.httpStatus !== 405);
      if (rawFail) throw new Error(rawFail.rawClear.error || `Raw mapping clear failed for ${rawFail.sym}`);

      setActiveCaseId(null);
      setRawActiveCaseId('');
      setActiveCaseLabel('');
      setSeedIdeas([]);
      setSessionEventIds(new Set());
      setActiveStructuralRangeId('');
      setSelectedParentRangeId('');
      setStructuralRanges([]);
      setSavedStructuralRanges([]);
      setStructuralAnchorsByLayer({});
      setReplayCursorByKey({});
      setChartDrawings([]);
      setSelectedDrawingId(null);
      setChartTradeIdeas([]);
      setTradeIdeaDraft(emptyTradeIdeaDraft());
      setSelectedTradeIdeaId(null);
      setTradePickMode(null);
      setRangeByTf({});
      setRangeWindowByTf({});
      setMeasurementRangeByTf({});
      setCameraDomainByCaseTf({});
      setCameraPriceDomainByCaseTf({});
      eventsByTfRef.current = {};
      setEventsByTf({});
      clearMappingEventsForContainer(mappingEventsScopeKey);
      setQuickEventHistory([]);
      try { localStorage.removeItem('fx_tm_chart_drawings_v1'); } catch { /* ignore */ }
      try { localStorage.removeItem('fx_tm_chart_trade_ideas_v1'); } catch { /* ignore */ }
      try { localStorage.removeItem('fx_tm_replay_cursor_time_v087_22'); } catch { /* ignore */ }

      await loadSavedCasesFromBackend();
      await loadMapMemory(timeframe);
      const summary = results.map(({ sym, r, rawClear }) => {
        const deleted = r?.deleted || {};
        const ranges = Number(deleted.map_ranges || 0);
        const events = Number(deleted.map_events || 0) + Number(deleted.raw_mapping_events || 0) + Number(rawClear.deleted_events || 0);
        const cases = Number(deleted.raw_mapping_cases || 0) + Number(deleted.mos_seed_ideas || 0) + Number(rawClear.deleted_cases || 0);
        return `${sym}: ${cases} case(s), ${ranges} range(s), ${events} event(s)`;
      }).join(' · ');
      setMessage(`Mapping wipe complete. Candles preserved. ${summary}`);
    } catch (err:any) { setMessage(`Research reset failed: ${err?.message || err}`); }
  };

  const captureCaseAnchor = (side:'high'|'low') => {
    const c = selectedCandle || replayCandle;
    if (!c) { setMessage('Select a candle first. Case anchors still need candles, shocking development.'); return; }
    const price = side === 'high' ? c.high : c.low;
    const value = Number(price.toFixed(2));
    const key = side === 'high' ? 'case_high' : 'case_low';
    const nextTf = caseTimeframe;
    setSeedAnchors((prev:any)=>{
      const next = { ...prev, [key]: value, [`${key}_time`]: c.time, case_timeframe: nextTf, case_scope: caseScope };
      // v087.29b: Case draft windows are rebuilt only from the current selected anchors.
      // Never merge old rangeWindowByTf values here, because cancelled cases were dragging
      // ancient 2019 windows into fresh 2026 selections like a very committed ghost.
      const win = timesToWindow([next.case_high_time, next.case_low_time].filter(Boolean));
      setRangeWindowByTf((rp:any)=>({ ...rp, [nextTf]: win || { start: c.time, end: c.time } }));
      return next;
    });
    if (caseTimeframe === timeframe) {
      if (side === 'high') setRangeHigh(String(value));
      if (side === 'low') setRangeLow(String(value));
    }
    setMessage(`Captured ${scopeLabel(caseScope)} case ${side.toUpperCase()} at ${value.toFixed(2)} from ${shortTime(c.time, timeframe)}.`);
  };


  const low = parseNum(rangeLow);
  const high = parseNum(rangeHigh);
  const hasRange = Number.isFinite(low) && Number.isFinite(high) && high > low;

  const chartSavedRangeOverlays = useMemo<SavedRangeChartLine[]>(() => {
    if (allRangeGuideLinesHidden) return [];
    const allRanges = safeArray<any>(savedStructuralRanges);
    const hiddenIds = new Set(rangeLineHiddenByCase[caseLineHiddenKey] || []);
    const overlays: SavedRangeChartLine[] = [];
    const selectedId = String(activeStructuralRangeId || '');
    const parentId = String(selectedParentRangeId || '');
    const chain = selectedId ? collectParentContextChain(selectedId, allRanges) : [];
    const resolvedParentId = parentId || String(chain[1] || '');
    const ancestorIds = chain.slice(2);
    const visibleIds = chartMappingFocusMode
      ? null
      : chartVisibleRangeIds(allRanges, selectedId, resolvedParentId);

    for (const r of allRanges) {
      const id = String(r?.range_id || r?.id || '');
      if (!id) continue;
      if (hiddenIds.has(id)) continue;
      if (visibleIds && !visibleIds.has(id)) continue;
      const isParentContext = id === resolvedParentId && id !== selectedId;
      const line = structuralRangeToChartLine(r, activeStructuralRangeId, { isParentContext });
      if (!line) continue;
      line.isActive = id === selectedId;
      overlays.push(line);
    }

    if (!chartMappingFocusMode) return overlays;

    const hasDraft = structuralRangeDraftDirty
      || !!String(rhAnchor.price || '').trim()
      || !!String(rlAnchor.price || '').trim();
    const annotated = annotateOverlayFocusTiers(overlays, {
      activeMappingLayer: structureLayer,
      parentRangeId: resolvedParentId || null,
      ancestorIds,
      hasDraft,
    });
    return filterFocusModeOverlays(annotated, {
      focusMode: true,
      showAllRanges: chartFocusShowAllRanges,
      activeMappingLayer: structureLayer,
    });
  }, [
    allRangeGuideLinesHidden,
    savedStructuralRanges,
    activeStructuralRangeId,
    selectedParentRangeId,
    activeCaseDisplayId,
    rangeLineHiddenByCase,
    chartMappingFocusMode,
    chartFocusShowAllRanges,
    structureLayer,
    structuralRangeDraftDirty,
    rhAnchor.price,
    rlAnchor.price,
  ]);

  const chartDraftRangeOverlay = useMemo<DraftRangeChartLine | null>(() => {
    if (allRangeGuideLinesHidden) return null;
    const draftHigh = parseNum(rhAnchor.price);
    const draftLow = parseNum(rlAnchor.price);
    const hasHigh = Number.isFinite(draftHigh);
    const hasLow = Number.isFinite(draftLow);
    if (!hasHigh && !hasLow) return null;
    if (hasHigh && hasLow && draftHigh <= draftLow) return null;
    const activeRange = activeStructuralRangeId
      ? safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(activeStructuralRangeId))
      : null;
    const savedHigh = parseNum(activeRange?.range_high_price ?? activeRange?.range_high);
    const savedLow = parseNum(activeRange?.range_low_price ?? activeRange?.range_low);
    const priceMatches = (a: number, b: number) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 0.005;
    const matchesSaved = !!activeRange && hasHigh && hasLow && priceMatches(savedHigh, draftHigh) && priceMatches(savedLow, draftLow) && !structuralRangeDraftDirty;
    if (matchesSaved) return null;
    return {
      high: hasHigh ? draftHigh : null,
      low: hasLow ? draftLow : null,
      structureLayer: structureLayer,
      visible: true,
      start: rhAnchor.time || rlAnchor.time || null,
      end: rlAnchor.time || rhAnchor.time || null,
    };
  }, [allRangeGuideLinesHidden, rhAnchor.price, rlAnchor.time, rlAnchor.price, rhAnchor.time, structureLayer, activeStructuralRangeId, savedStructuralRanges, structuralRangeDraftDirty]);

  const linkedTradeRangeLabel = useMemo(() => {
    if (!activeStructuralRangeId) return 'No range selected — pick a range in Structural Map to link context';
    const r = safeArray<any>(savedStructuralRanges).find((x) => String(x.range_id || x.id) === String(activeStructuralRangeId));
    const scope = String(r?.range_scope || rangeScope || 'MAJOR');
    return `#${activeStructuralRangeId} · ${structureLayer} · ${scope}`;
  }, [activeStructuralRangeId, savedStructuralRanges, structureLayer, rangeScope]);

  const htfSemiAuto = useMemo(() => analyseHTFSemiAuto({
    timeframe,
    candles: visibleCandles,
    activeCandle: activeReplayCandle,
    rangeHigh: high,
    rangeLow: low,
    rangeWindow,
    events,
    activeCaseId,
    acceptedLocks: htfAcceptedSuggestionLocks,
  }), [timeframe, visibleCandles, activeReplayCandle?.time, high, low, rangeWindow.start, rangeWindow.end, events.length, activeCaseId, htfAcceptedSuggestionLocks.join('|')]);

  const htfVisibleCandidates = useMemo(() => {
    const rejected = new Set(htfRejectedCandidateIds || []);
    const acceptedLocks = new Set(htfAcceptedSuggestionLocks || []);
    return safeArray<HTFCandidate>(htfCandidates).filter(c => {
      if (rejected.has(c.id)) return false;
      const lk = hasRange ? htfCandidateLockKey(c, timeframe, low, high) : '';
      return !lk || !acceptedLocks.has(lk);
    });
  }, [htfCandidates, htfRejectedCandidateIds, htfAcceptedSuggestionLocks, hasRange, timeframe, low, high]);

  useEffect(() => {
    // Auto-refresh suggestions as replay/selection moves. They remain suggestions until accepted.
    // v087.16: core state contract. Range -> BOS -> reclaim -> rebase. Ref candle is separate.
    const rejected = new Set(htfRejectedCandidateIds || []);
    const acceptedLocks = new Set(htfAcceptedSuggestionLocks || []);
    setHtfCandidates(safeArray<HTFCandidate>(htfSemiAuto.candidates).filter(c => {
      if (rejected.has(c.id)) return false;
      const lk = hasRange ? htfCandidateLockKey(c, timeframe, low, high) : '';
      return !lk || !acceptedLocks.has(lk);
    }));
  }, [htfSemiAuto.state?.last_candle, htfSemiAuto.candidates.map(c=>c.id).join('|'), htfRejectedCandidateIds.join('|'), htfAcceptedSuggestionLocks.join('|'), hasRange, timeframe, low, high]);
  const rangeWindowCandles = useMemo(() => {
    if (!visibleCandles.length || (!rangeWindow.start && !rangeWindow.end)) return visibleCandles;
    const start = rangeWindow.start ? new Date(rangeWindow.start) : null;
    const end = rangeWindow.end ? new Date(rangeWindow.end) : null;
    return visibleCandles.filter(c => { const d = new Date(c.time); return (!start || d >= start) && (!end || d <= end); });
  }, [visibleCandles, rangeWindow.start, rangeWindow.end]);

  const trajectoryStartInfo = useMemo(() => {
    const getTimes = (types:string[]) => visibleEvents
      .filter(e => types.includes(String(e.event_type || e.event_name || '').toUpperCase()) && e.time)
      .map(e => ({ type:String(e.event_type || e.event_name || '').toUpperCase(), ms:new Date(String(e.time)).getTime(), time:String(e.time) }))
      .filter(e => Number.isFinite(e.ms));

    const firstOf = (items:{type:string;ms:number;time:string}[]) => items.length ? items.reduce((a,b)=> a.ms <= b.ms ? a : b) : null;
    const latestOf = (items:{type:string;ms:number;time:string}[]) => items.length ? items.reduce((a,b)=> a.ms >= b.ms ? a : b) : null;

    const bosDown = getTimes(['BOS_DOWN']);
    const reclaimLow = getTimes(['RECLAIM_LOW']);
    const bosUp = getTimes(['BOS_UP']);
    const reclaimHigh = getTimes(['RECLAIM_HIGH']);

    // Josh logic: once BOS + reclaim exists, the active story starts there.
    // Do NOT let older Ref H/L Taken events drag auto trajectory backwards.
    if (bosDown.length && reclaimLow.length) {
      const start = firstOf([...bosDown, ...reclaimLow]);
      return { time:start?.time, reason:'BOS Down + Reclaim Low' };
    }
    if (bosUp.length && reclaimHigh.length) {
      const start = firstOf([...bosUp, ...reclaimHigh]);
      return { time:start?.time, reason:'BOS Up + Reclaim High' };
    }

    // If no pair exists, prioritize the latest structural event over reference events.
    const structural = getTimes(['BOS_DOWN','BOS_UP','CHOCH_DOWN','CHOCH_UP','RECLAIM_LOW','RECLAIM_HIGH']);
    const latestStructural = latestOf(structural);
    if (latestStructural) return { time:latestStructural.time, reason:latestStructural.type };

    // Fall back to selected range window, then reference events.
    if (rangeWindow.start) return { time:rangeWindow.start, reason:'Range Start' };
    const refs = getTimes(['REF_LOW_TAKEN','REF_HIGH_TAKEN','RANGE_LOW','RANGE_HIGH']);
    const firstRef = firstOf(refs);
    if (firstRef) return { time:firstRef.time, reason:firstRef.type };

    return { time:undefined, reason:'Visible candles' };
  }, [visibleEvents, rangeWindow.start]);

  const trajectoryCandles = useMemo(() => {
    if (!visibleCandles.length) return visibleCandles;
    if (!trajectoryStartInfo.time) return rangeWindowCandles;
    const start = new Date(String(trajectoryStartInfo.time));
    if (Number.isNaN(start.getTime())) return rangeWindowCandles;
    // Let the route continue to the newest candle. Start is chosen by active structure math, not old ref history.
    return visibleCandles.filter(c => new Date(c.time) >= start);
  }, [visibleCandles, trajectoryStartInfo.time, rangeWindowCandles]);

  const traj = hasRange ? autoTrajectory(trajectoryCandles, low, high) : [];

  const loadMapMemory = async (requestedTf = timeframe, requestId = candleLoadSeqRef.current) => {
    const isCurrentLoad = () => requestId === candleLoadSeqRef.current && activeTimeframeRef.current === requestedTf;
    try {
      const localRangeBeforeLoad = rangeByTf[requestedTf] || {};
      const hasLocalExplicitHigh = !!String(localRangeBeforeLoad.high || '').trim();
      const hasLocalExplicitLow = !!String(localRangeBeforeLoad.low || '').trim();

      // v087.25: if a case is active, load ONLY rows explicitly linked to that case.
      // The old global map/event feed can still exist, but it must not vomit legacy marks into a clean workspace.
      if (activeCaseId) {
        const payload = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${activeCaseId}/payload`).then(r=>r.json()).catch(()=>null);
        if (!isCurrentLoad()) { cameraLog('map memory ignored as stale', { requestId, requestedTf, activeTf:activeTimeframeRef.current }); return false; }
        if (payload?.ok) {
          const caseEvents = safeArray<any>(payload.events)
            .filter((raw:any)=>String(raw?.timeframe || raw?.meta?.timeframe || '').toUpperCase() === String(requestedTf).toUpperCase())
            .map(normalizeBackendEvent)
            .filter(Boolean) as MapEvent[];
          let mergedEvents = caseEvents;
          const mappingCase = getCurrentMappingCaseRef();
          if (mappingCase.hasCase) {
            try {
              const eventParams = appendMappingCaseParams(
                new URLSearchParams({ symbol, timeframe: requestedTf, limit: '2000' }),
                mappingCase,
              );
              const structuralRes = await fetch(`${BASE_URL}/api/v1/map/events?${eventParams.toString()}`).then(r=>r.json()).catch(()=>null);
              if (structuralRes?.ok && Array.isArray(structuralRes.events)) {
                const structuralEvents = structuralRes.events
                  .map((row:any) => mapStructuralEventRowToChartEvent(row))
                  .filter(Boolean) as MapEvent[];
                mergedEvents = mergeChartEventsById(caseEvents, structuralEvents);
              }
            } catch {
              // Keep seed payload events if structural fetch fails.
            }
          }
          setEventsByTf(prev => ({ ...prev, [requestedTf]: mergedEvents }));

          const caseRanges = safeArray<any>(payload.ranges)
            .filter((r:any)=>String(r?.timeframe || '').toUpperCase() === String(requestedTf).toUpperCase());
          const latestRange = caseRanges[caseRanges.length - 1];
          if (latestRange) {
            if (!hasLocalExplicitHigh && Number(latestRange.range_high)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:String(Number(latestRange.range_high).toFixed(2)), low:prev[requestedTf]?.low || '' } }));
            if (!hasLocalExplicitLow && Number(latestRange.range_low)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:prev[requestedTf]?.high || '', low:String(Number(latestRange.range_low).toFixed(2)) } }));
            const ms = [latestRange.range_high_time, latestRange.range_low_time, latestRange.active_from_time, latestRange.inactive_from_time].filter(Boolean).map((x:string)=>new Date(x).getTime()).filter(Number.isFinite);
            if (ms.length >= 2 && (!rangeWindowByTf[requestedTf]?.start || !rangeWindowByTf[requestedTf]?.end)) {
              setRangeWindowByTf(prev=>({ ...prev, [requestedTf]: { start:new Date(Math.min(...ms)).toISOString(), end:new Date(Math.max(...ms)).toISOString() }}));
            }
          } else if ((!hasLocalExplicitHigh || !hasLocalExplicitLow) && caseEvents.length) {
            syncRangeFromEvents(caseEvents, false, requestedTf);
          }
          return true;
        }
      }

      const [rangeRes, eventsRes] = await Promise.all([
        fetch(`${BASE_URL}/api/v1/map/range?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(requestedTf)}&range_key=active`).then(r=>r.json()).catch(()=>null),
        fetch(`${BASE_URL}/api/v1/map/events?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(requestedTf)}&limit=2000${(() => {
          const mappingCase = getCurrentMappingCaseRef();
          if (!mappingCase.hasCase) return '';
          const p = appendMappingCaseParams(new URLSearchParams(), mappingCase);
          return `&${p.toString()}`;
        })()}`).then(r=>r.json()).catch(()=>null)
      ]);
      if (!isCurrentLoad()) { cameraLog('map memory ignored as stale', { requestId, requestedTf, activeTf:activeTimeframeRef.current }); return false; }

      if (rangeRes?.ok && rangeRes.range) {
        const rg = rangeRes.range;
        if (!hasLocalExplicitHigh && Number(rg.range_high)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:String(Number(rg.range_high).toFixed(2)), low:prev[requestedTf]?.low || '' } }));
        if (!hasLocalExplicitLow && Number(rg.range_low)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:prev[requestedTf]?.high || '', low:String(Number(rg.range_low).toFixed(2)) } }));
        const startCandidates = [rg.range_high_time, rg.range_low_time].filter(Boolean).map((x:string)=>new Date(x).getTime()).filter(Number.isFinite);
        if (startCandidates.length >= 2 && (!rangeWindowByTf[requestedTf]?.start || !rangeWindowByTf[requestedTf]?.end)) {
          setRangeWindowByTf(prev=>({ ...prev, [requestedTf]: { start:new Date(Math.min(...startCandidates)).toISOString(), end:new Date(Math.max(...startCandidates)).toISOString() }}));
        }
      }

      if (eventsRes?.ok && Array.isArray(eventsRes.events)) {
        const loaded = eventsRes.events.map((e:any)=>({
          id: String(e.client_event_id || e.id),
          event_type: e.event_type,
          event_name: e.event_name || e.event_type,
          time: e.time,
          price: Number(e.price),
          zone: e.zone,
          zone_percent: e.zone_percent === null || e.zone_percent === undefined ? undefined : Number(e.zone_percent),
          notes: e.notes || '',
          primitive: e.primitive || undefined,
          derived_event_code: e.derived_event_code || undefined,
          movement_rule: e.movement_rule || undefined,
          range_status_after: e.range_status_after || undefined,
          engine_source: e.engine_source || undefined,
          logic_version: e.logic_version || undefined,
          candidate_id: e.candidate_id || undefined,
          confidence: e.confidence || undefined,
          meta_json: (() => { try { return typeof e.meta_json === 'string' ? JSON.parse(e.meta_json) : e.meta_json; } catch { return e.meta_json; } })(),
          candle_open: e.candle_open === null || e.candle_open === undefined ? undefined : Number(e.candle_open),
          candle_high: e.candle_high === null || e.candle_high === undefined ? undefined : Number(e.candle_high),
          candle_low: e.candle_low === null || e.candle_low === undefined ? undefined : Number(e.candle_low),
          candle_close: e.candle_close === null || e.candle_close === undefined ? undefined : Number(e.candle_close),
        })).filter((e:any)=>e.event_type && Number.isFinite(e.price));
        setEventsByTf(prev => ({ ...prev, [requestedTf]: loaded }));
        if (!hasLocalExplicitHigh || !hasLocalExplicitLow) syncRangeFromEvents(loaded, false, requestedTf);
      }
      return true;
    } catch {
      // Map memory failing should never block candle display. That would be dramatic and unhelpful.
      return false;
    }
  };

  const resolveLoadCameraIntent = (requestedTf:string, fallbackTime?:string|null) => {
    const pending = pendingCameraIntentRef.current;
    if (pending.intent && pending.intent !== 'NONE') return pending;
    if (isRoutineTfMemoryReason(pending.reason)) return pending;
    if (cameraMode === 'LOCKED') return { intent:'RESTORE_LOCKED' as CameraIntent, targetTime:fallbackTime, reason:'locked-load' };
    const contextRange = resolveCandleWindowTargetRange(
      requestedTf,
      savedStructuralRanges,
      activeStructuralRangeId,
      selectedParentRangeId,
    ) || resolveMappingContextRange(savedStructuralRanges, selectedParentRangeId, activeStructuralRangeId);
    if (contextRange) {
      const ctxTime = structuralContextTargetTime(contextRange) || fallbackTime;
      return {
        intent:'FIT_STRUCTURAL_RANGE' as CameraIntent,
        targetTime: ctxTime,
        reason:`${requestedTf}-context-load`,
        contextRangeId: String(contextRange.range_id || contextRange.id),
        fitWindow: structuralRangeFitDomain(contextRange, [], requestedTf) || null,
      };
    }
    if (cameraMode === 'CASE' && !rawActiveCaseId && (activeCaseId === null || activeCaseId === undefined)) {
      return { intent:'LATEST' as CameraIntent, targetTime:fallbackTime, reason:'no-active-case' };
    }
    if (cameraMode === 'CASE') return { intent:'CASE' as CameraIntent, targetTime:fallbackTime, reason:'case-load' };
    if (cameraMode === 'REPLAY') return { intent:'REPLAY' as CameraIntent, targetTime:fallbackTime, reason:'replay-load' };
    return { intent:'PRESERVE_OR_NEAREST_TIME' as CameraIntent, targetTime:fallbackTime, reason:`${requestedTf}-load` };
  };

  const applyCameraCommand = (intent:CameraIntent, targetTime?:string|null, reason?:string, scaleFactor?:number, fitWindow?: StructuralFitWindow | null, priceDomain?: { low: number; high: number } | null) => {
    setCameraViewOwnerWithLog(inferViewOwnerFromCameraReason(reason, intent), 'applyCameraCommand', reason || intent);
    cameraLog('camera intent applied', { intent, targetTime, reason, scaleFactor, fitWindow, priceDomain });
    setCameraCommand(prev => ({ intent, targetTime: targetTime || null, reason, scaleFactor, fitWindow: fitWindow || null, priceDomain: priceDomain || null, token: prev.token + 1 }));
  };

  const scheduleDeferredCamera = (
    intent: CameraIntent,
    targetTime?: string | null,
    reason?: string,
    fitWindow?: StructuralFitWindow | null,
    priceDomain?: { low: number; high: number } | null,
  ) => {
    if (shouldBlockAutomaticCameraRefit(cameraViewOwnerRef.current) && !isExplicitCameraNavigationReason(reason)) {
      cameraLog('deferred camera suppressed', { reason, owner: cameraViewOwnerRef.current, intent });
      return;
    }
    deferredCameraRef.current = { intent, targetTime, reason, fitWindow, priceDomain };
    setDeferredCameraToken((t) => t + 1);
  };

  const recordCandleLoadDiagnostic = (diag: CandleLoadDiagnostics) => {
    setCandleLoadDiagnostics(diag);
    cameraLog('candle load diagnostic', diag);
    if (DEBUG_CAMERA) console.log('[candle-load]', formatCandleLoadDiagnostic(diag), diag);
  };

  useEffect(() => {
    const pending = deferredCameraRef.current;
    if (!pending || !candles.length) return;
    if (shouldBlockAutomaticCameraRefit(cameraViewOwnerRef.current) && !isExplicitCameraNavigationReason(pending.reason)) {
      deferredCameraRef.current = null;
      cameraLog('deferred camera dropped', { pending, owner: cameraViewOwnerRef.current });
      return;
    }
    deferredCameraRef.current = null;
    const frame = window.requestAnimationFrame(() => {
      applyCameraCommand(
        pending.intent,
        pending.targetTime || null,
        pending.reason || 'deferred-camera-fit',
        undefined,
        pending.fitWindow || null,
        pending.priceDomain || null,
      );
      cameraLog('deferred camera applied', pending);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [deferredCameraToken, candles.length]);

  const fitRangeView = () => {
    const hi = parseNum(rhAnchor.price);
    const lo = parseNum(rlAnchor.price);
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) {
      setMessage('Set Range High and Range Low before Fit Range.');
      return;
    }
    const t0 = String(rhAnchor.time || rangeWindow.start || selectedCandle?.time || replayCandle?.time || '');
    const t1 = String(rlAnchor.time || rangeWindow.end || t0);
    if (!candles.length) {
      setMessage('Load candles before Fit Range.');
      return;
    }
    const clamped = clampFitTimesToCandles(t0 || candles[0].time, t1 || t0 || candles[0].time, candles);
    const fit = buildCandleWindowFit(candles, clamped.start, readablePadBarsForTimeframe(timeframe))
      || structuralRangeFitDomain({ range_high: hi, range_low: lo, range_start_time: clamped.start, range_end_time: clamped.end }, candles);
    if (!fit) {
      setMessage('Could not fit range view.');
      return;
    }
    fit.low = Math.min(lo, fit.low);
    fit.high = Math.max(hi, fit.high);
    setCameraViewOwnerWithLog('FIT_RANGE', 'fitRangeView', 'fit-range');
    applyCameraCommand('FIT_STRUCTURAL_RANGE', clamped.start, 'fit-range', undefined, fit);
    setMessage(`Fit range · ${shortTime(clamped.start, timeframe)} → ${shortTime(clamped.end, timeframe)}`);
  };

  const fitReplayView = () => {
    const targetTime = selectedCandle?.time || replayCandle?.time || candleReplayCursorTime || null;
    if (!targetTime || !candles.length) {
      setMessage('No selected/replay candle to fit.');
      return;
    }
    const fit = buildCandleWindowFit(candles, targetTime, readablePadBarsForTimeframe(timeframe));
    if (!fit) {
      setMessage('Could not fit replay view.');
      return;
    }
    setCameraViewOwnerWithLog('FIT_REPLAY', 'fitReplayView', 'fit-replay');
    applyCameraCommand('FIT_STRUCTURAL_RANGE', targetTime, 'fit-replay', undefined, fit);
    setMessage(`Fit replay · ${shortTime(targetTime, timeframe)}`);
  };

  const fitCaseView = () => {
    if (!candles.length) {
      setMessage('Load candles before Fit Case.');
      return;
    }
    const startRaw = String(activeCaseLedger?.start || caseWindowStartDisplay || rangeWindow.start || '');
    const endRaw = String(activeCaseLedger?.end || caseWindowEndDisplay || rangeWindow.end || startRaw);
    const center = startRaw || selectedCandle?.time || replayCandle?.time || candles[Math.floor(candles.length / 2)].time;
    const clamped = clampFitTimesToCandles(startRaw || center, endRaw || center, candles);
    const caseLo = parseNum(activeCaseLedger?.low || caseLow);
    const caseHi = parseNum(activeCaseLedger?.high || caseHigh);
    let fit = buildCandleWindowFit(candles, clamped.start, 50);
    if (!fit) {
      fit = { start: clamped.start, end: clamped.end, low: caseLo, high: caseHi, padRatio: 0.14 };
    }
    if (Number.isFinite(caseLo) && Number.isFinite(caseHi) && caseHi > caseLo) {
      fit.low = Math.min(fit.low, caseLo);
      fit.high = Math.max(fit.high, caseHi);
    }
    setCameraViewOwnerWithLog('FIT_CASE', 'fitCaseView', 'fit-case');
    applyCameraCommand('FIT_STRUCTURAL_RANGE', clamped.start, 'fit-case', undefined, fit);
    setMessage(`Fit case · ${shortTime(clamped.start, timeframe)} → ${shortTime(clamped.end, timeframe)}`);
  };

  const fitAllView = () => {
    setCameraViewOwnerWithLog('FIT_ALL', 'fitAllView', 'fit-all');
    applyCameraCommand('FIT_ALL', null, 'fit-all');
  };

  const lockCurrentView = () => {
    const dom = visibleCameraDomainRef.current;
    if (!dom || !dom.start || !dom.end || !Number.isFinite(dom.priceLow) || !Number.isFinite(dom.priceHigh) || dom.priceHigh <= dom.priceLow) {
      setMessage('Cannot lock view yet: no valid visible camera domain.');
      return;
    }
    setCameraDomainByCaseTf(prev => ({ ...prev, [cameraKey]: { start:dom.start, end:dom.end } }));
    setCameraPriceDomainByCaseTf(prev => ({ ...prev, [cameraKey]: { low:dom.priceLow, high:dom.priceHigh } }));
    setCameraMode('LOCKED');
    setCameraViewOwnerWithLog('USER_LOCKED', 'lockCurrentView', 'lock-view');
    applyCameraCommand('RESTORE_LOCKED', null, 'lock-view');
    setMessage(`Locked view for ${timeframe}: ${shortTime(dom.start, timeframe)} → ${shortTime(dom.end, timeframe)}`);
  };

  const applyStaleCacheBlockedUiClear = (targetTf: string) => {
    // Structural purge only — nav rail / inspector panel chrome is out of scope.
    purgeGhostMappingLocalStorage(symbol, activeCaseDisplayId || null);
    purgeStructuralUiAnchors();
    clearStructuralRangeDraft();
    setBhAnchor({ price: '', time: '' });
    setBlAnchor({ price: '', time: '' });
    setStructuralBosDraftDirty(false);
    setCandleLoadState(STALE_CACHE_BLOCKED);
    setChartCandles([]);
    setSelectedCandle(null);
    setSelectedCandlePoint(null);
    setCandleReplayIndex(0);
    pendingCameraIntentRef.current = { intent: 'NONE' };
    setMessage(ghostRangeUiClearMessage(symbol, targetTf));
  };

  const purgeStructuralUiAnchors = useCallback(() => {
    clearAllUIAnchors({
      setActiveStructuralRangeId,
      setSelectedParentRangeId,
      setStructuralRanges,
      setSavedStructuralRanges,
      setStructuralAnchorsByLayer,
      setSessionEventIds,
      setEventsByTf,
      clearEventsByTfRef: () => { eventsByTfRef.current = {}; },
      setRangeByTf,
      setRangeWindowByTf,
      setMeasurementRangeByTf,
      setRhAnchor,
      setRlAnchor,
      setStructuralRangeDraftDirty,
      clearMappingEventsBucket: clearMappingEventsForContainer,
      mappingEventsScopeKey,
    });
  }, [mappingEventsScopeKey]);

  const loadCandles = async (requestedTf = timeframe, opts?: {
    quiet?: boolean;
    skipCamera?: boolean;
    deferCamera?: boolean;
    cacheFullHistory?: boolean;
    structuralNavigation?: boolean;
    timeframeSwitch?: boolean;
    localOnly?: boolean;
    loadWindow?: { start: string; end: string; label?: string } | null;
    reason?: string;
    navigationPath?: string;
  }) => {
    const targetTf = String(requestedTf || timeframe).toUpperCase();
    const quiet = !!opts?.quiet;
    if (!quiet && tradingViewMappingPreserveLoad(targetTf, opts)) {
      const chartTf = String(targetTf).toUpperCase();
      const rehydrated = rehydrateLoadedCandleContextForVisibleFeed({
        loaded: loadedCandleContextRef.current,
        requestId: candleLoadSeqRef.current,
        symbol: String(symbol),
        caseId: String(activeCaseDisplayId || ''),
        chartTimeframe: chartTf,
        sourceTimeframe: sourceTimeframeRef.current,
        structureLayer: structureLayerRef.current,
        candleCount: candleCountRef.current,
      });
      if (rehydrated && rehydrated !== loadedCandleContextRef.current) {
        loadedCandleContextRef.current = rehydrated;
        setLoadedCandleContext(rehydrated);
      }
      cameraLog('tv mapping preserve — skipped structural candle reload', {
        targetTf,
        reason: opts?.reason,
        navigationPath: opts?.navigationPath,
      });
      return;
    }
    const activeRangeIdNow = String(activeStructuralRangeIdRef.current || '');
    const parentRangeIdNow = String(selectedParentRangeIdRef.current || '');
    if (quiet && candleLoadInFlightRef.current) return;
    if (shouldBlockQuietFullHistoryReload({
      quiet,
      forceFullHistory: opts?.cacheFullHistory,
      activeRangeId: activeRangeIdNow,
      selectedParentRangeId: parentRangeIdNow,
      incomingWindowKey: loadWindowKey(opts?.loadWindow ?? null),
    })) {
      cameraLog('quiet full-history reload blocked during structural mapping', { targetTf, activeRangeId: activeRangeIdNow });
      return;
    }
    if (quiet) candleLoadInFlightRef.current = true;
    if (!quiet) deferredCameraRef.current = null;
    candleFeedLoadInFlightRef.current = true;
    setCandleFeedLoading(true);
    const priorLoadedChartTf = loadedCandleContextRef.current?.chartTimeframe || null;
    if (!quiet) {
      loadedCandleContextRef.current = null;
      setLoadedCandleContext(null);
    }
    const requestId = candleLoadSeqRef.current + 1;
    candleLoadSeqRef.current = requestId;
    const capturedPending = !quiet && pendingCameraIntentRef.current.intent !== 'NONE'
      ? { ...pendingCameraIntentRef.current }
      : null;
    const preservedTime = selectedCandle?.time
      || (candleReplayMode ? (candleReplayCursorTime || replayCandle?.time || null) : null);
    const pendingIntent = quiet
      ? { intent: 'PRESERVE_OR_NEAREST_TIME' as CameraIntent, targetTime: preservedTime, reason: 'quiet-refresh' }
      : (capturedPending || resolveLoadCameraIntent(targetTf, preservedTime));
    const preferredWindow = opts?.timeframeSwitch
      ? null
      : (capturedPending?.fitWindow?.start && capturedPending?.fitWindow?.end
        ? { start: capturedPending.fitWindow.start, end: capturedPending.fitWindow.end }
        : null);
    const preserveStructuralContext = !!(
      opts?.structuralNavigation
      || capturedPending?.contextRangeId
      || (!opts?.cacheFullHistory && opts?.loadWindow)
      || (!opts?.timeframeSwitch && (activeRangeIdNow || parentRangeIdNow))
    );
    const liveTail = !candleReplayMode && !preserveStructuralContext;
    const wantsFullHistory = !!opts?.cacheFullHistory;
    const loadWindow = wantsFullHistory
      ? null
      : (opts?.loadWindow ?? (opts?.timeframeSwitch
        ? (resolveTimeframeSwitchDataLoadWindow({
          targetTf,
          contextRange: (() => {
            const ctx = resolveCandleWindowTargetRange(
              targetTf,
              savedStructuralRanges,
              activeRangeIdNow,
              parentRangeIdNow,
            ) || resolveMappingContextRange(savedStructuralRanges, parentRangeIdNow, activeRangeIdNow);
            if (!ctx) return null;
            const span = rangeWindowFieldsFromSavedRange(ctx);
            return {
              start: span.start || span.end,
              end: span.end || span.start,
              structure_layer: ctx?.structure_layer,
              layer: ctx?.layer,
            };
          })(),
          caseWindow: rangeWindowByTf[targetTf] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
        }) ?? resolveCandleLoadWindow(
          targetTf,
          savedStructuralRanges,
          parentRangeIdNow,
          activeRangeIdNow,
          rangeWindowByTf[targetTf] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
          { liveTail, preferredWindow: null },
        ))
        : resolveCandleLoadWindow(
          targetTf,
          savedStructuralRanges,
          parentRangeIdNow,
          activeRangeIdNow,
          rangeWindowByTf[targetTf] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
          { liveTail, preferredWindow },
        )));
    const useWindowedLoad = !wantsFullHistory && shouldUseWindowedCandleLoad(loadWindow);
    const candleLoadMayMoveCamera = !!(
      opts?.timeframeSwitch
      || opts?.structuralNavigation
      || isExplicitCameraNavigationReason(opts?.reason || pendingIntent.reason)
    );
    const loadContext: CandleLoadContext = {
      requestId,
      symbol: String(symbol).toUpperCase(),
      caseId: String(activeCaseDisplayId || ''),
      tf: targetTf,
      activeRangeId: activeRangeIdNow,
      loadWindowKey: loadWindowKey(loadWindow),
    };
    candleLoadContextRef.current = loadContext;
    const previousCount = candleCountRef.current;
    const navigationPath = opts?.navigationPath || opts?.reason || 'loadCandles';
    const isCurrentLoad = () => isCurrentCandleLoadRequest(
      loadContext,
      candleLoadContextRef.current,
      activeTimeframeRef.current,
    );
    const diagBase: CandleLoadDiagnostics = {
      at: new Date().toISOString(),
      rangeId: activeRangeIdNow,
      parentRangeId: parentRangeIdNow,
      layer: String(structureLayer || ''),
      requestedTf: targetTf,
      windowStart: loadWindow?.start || '',
      windowEnd: loadWindow?.end || '',
      mode: useWindowedLoad ? 'windowed' as const : 'full' as const,
      liveTail,
      navigationPath,
      previousCount,
      reason: opts?.reason || pendingIntent.reason || 'loadCandles',
      cameraIntent: pendingIntent.intent,
      returnedCount: 0,
      filteredCount: 0,
      accepted: false,
      replayIndex: 0,
      playForwardEnabled: false,
      playForwardReason: 'pending',
    };
    logCandleLoadRequest({
      id: requestId,
      source: navigationPath,
      tf: targetTf,
      symbol: String(symbol).toUpperCase(),
      caseId: String(activeCaseDisplayId || ''),
      layer: String(structureLayer || ''),
      sourceTf: String(sourceTimeframeRef.current || sourceTimeframe).toUpperCase(),
      chartTf: String(activeTimeframeRef.current || targetTf).toUpperCase(),
      window: formatCandleLoadWindowLabel(loadWindow?.start, loadWindow?.end),
      activeRangeId: activeRangeIdNow || parentRangeIdNow || undefined,
    });
    if (shouldClearCandlesOnLoadStart({
      quiet,
      timeframeSwitch: opts?.timeframeSwitch,
      targetTf,
      loadedChartTf: priorLoadedChartTf,
    })) {
      setChartCandles([]);
      candleCountRef.current = 0;
    }
    cameraLog('candle load start', { requestId, targetTf, intent: pendingIntent.intent, targetTime: pendingIntent.targetTime, loadWindow, liveTail, preserveStructuralContext, useWindowedLoad, quiet, loadContext, navigationPath });
    if (!quiet) {
      setLoading(true);
      setMessage(loadWindow
        ? `Loading ${targetTf} candles for ${loadWindow.start} → ${loadWindow.end}...`
        : `Loading ${targetTf} candles from backend...`);
    }
    try {
      const sessionRange = useWindowedLoad && loadWindow
        ? { start: loadWindow.start, end: loadWindow.end }
        : null;
      const mappingCase = getCurrentMappingCaseRef();
      const chartWindow = sessionRange ?? (loadWindow ? { start: loadWindow.start, end: loadWindow.end } : null);
      const libraryLoad = await loadChartCandlesLocalFirst({
        symbol,
        timeframe: targetTf,
        window: chartWindow,
        caseId: mappingCase.caseRef || activeCaseDisplayId || null,
        localOnly: !!opts?.localOnly,
      });
      if (!isCurrentLoad()) {
        logCandleLoadResponse({ id: requestId, tf: targetTf, count: 0, applied: false, reason: 'stale-local' });
        cameraLog('candle load ignored as stale (local library)', { requestId, targetTf, activeTf: activeTimeframeRef.current });
        return;
      }
      if (libraryLoad.should_clear_ui && isStaleRehydrationLoad(libraryLoad)) {
        applyStaleCacheBlockedUiClear(targetTf);
        if (!quiet) setLoading(false);
        recordCandleLoadDiagnostic({ ...diagBase, returnedCount: 0, accepted: false, detail: 'stale-cache-blocked', cameraIntent: 'NONE' });
        cameraLog('stale cache blocked chart load', { requestId, targetTf, rehydration: libraryLoad.rehydration, state: STALE_CACHE_BLOCKED });
        return;
      }
      setLocalLibraryDebug(libraryLoad.debug);
      localLibraryDebugRef.current = libraryLoad.debug;
      if (libraryLoad.ok) setCandleLoadState(null);

      let parsed: Candle[] = [];
      if (libraryLoad.candles.length) {
        parsed = parseCandleRows(libraryLoad.candles);
        if (!quiet) {
          setMessage(`Loaded ${parsed.length} ${targetTf} candles from local library…`);
        }
      } else if (!quiet) {
        setMessage(libraryLoad.statusMessage || formatMissingCandleMessage(targetTf, chartWindow));
      }
      const rawCount = parsed.length;
      const trimContextRangeId = pendingIntent.contextRangeId || activeRangeIdNow;
      const trimContextRange = trimContextRangeId
        ? safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(trimContextRangeId))
        : null;
      if (useWindowedLoad && loadWindow && parsed.length) {
        const visualContext = trimContextRange
          ? rangeWindowFieldsFromSavedRange(trimContextRange)
          : structuralVisualContextRef.current;
        parsed = filterCandlesToLoadWindow(parsed, {
          start: loadWindow.start,
          end: loadWindow.end,
          label: loadWindow.label || 'structural context',
        });
        const maxBars = maxBarsForStructuralWindow(targetTf);
        if (parsed.length > maxBars) {
          parsed = trimStructuralCandlesToHorizon(parsed, maxBars, visualContext, targetTf);
        }
        if (preserveStructuralContext && loadWindow) {
          structuralDataLoadWindowRef.current = loadWindow;
          const span = trimContextRange ? rangeWindowFieldsFromSavedRange(trimContextRange) : null;
          structuralVisualContextRef.current = span?.start || span?.end
            ? { start: span.start || span.end || '', end: span.end || span.start || '' }
            : null;
        }
      }
      let contextMiss = false;
      if (useWindowedLoad && loadWindow && parsed.length && !candleWindowOverlapsRange(parsed, loadWindow.start, loadWindow.end)) {
        contextMiss = true;
      }
      if (!isCurrentLoad()) {
        logCandleLoadResponse({ id: requestId, tf: targetTf, count: parsed.length, applied: false, reason: 'stale-parse' });
        cameraLog('candle load ignored as stale after parse', { requestId, targetTf, activeTf:activeTimeframeRef.current });
        return;
      }
      const applyDecision = shouldApplyParsedCandles({
        parsedCount: parsed.length,
        previousCount,
        hadLoadWindow: useWindowedLoad,
        requestedTf: targetTf,
        windowStart: loadWindow?.start,
        windowEnd: loadWindow?.end,
      });
      if (!applyDecision.apply || (useWindowedLoad && !parsed.length)) {
        const detail = applyDecision.detail || (useWindowedLoad && !parsed.length ? 'empty-window-load' : 'rejected');
        recordCandleLoadDiagnostic({
          ...diagBase,
          returnedCount: parsed.length,
          accepted: false,
          detail,
          cameraIntent: 'NONE',
        });
        deferredCameraRef.current = null;
        pendingCameraIntentRef.current = { intent: 'NONE' };
        if (!quiet) {
          if (tradingViewMappingPreserveLoad(targetTf, opts)) {
            const chartTf = String(targetTf).toUpperCase();
            const rehydrated = rehydrateLoadedCandleContextForVisibleFeed({
              loaded: loadedCandleContextRef.current,
              requestId: candleLoadSeqRef.current,
              symbol: String(symbol),
              caseId: String(activeCaseDisplayId || ''),
              chartTimeframe: chartTf,
              sourceTimeframe: sourceTimeframeRef.current,
              structureLayer: structureLayerRef.current,
              candleCount: candleCountRef.current,
            });
            if (rehydrated && rehydrated !== loadedCandleContextRef.current) {
              loadedCandleContextRef.current = rehydrated;
              setLoadedCandleContext(rehydrated);
            }
            recordCandleLoadDiagnostic({
              ...diagBase,
              returnedCount: parsed.length,
              accepted: false,
              detail: 'tv-mapping-preserve-rejected-load',
              cameraIntent: 'NONE',
            });
            cameraLog('tv mapping preserve — kept candles after rejected structural load', {
              requestId,
              targetTf,
              parsed: parsed.length,
              loadWindow,
              detail,
            });
            return;
          }
          setChartCandles([]);
          candleCountRef.current = 0;
          loadedCandleContextRef.current = null;
          setLoadedCandleContext(null);
          setMessage(applyDecision.statusMessage || `No valid ${targetTf} candles for selected window — chart cleared.`);
        }
        logCandleLoadResponse({
          id: requestId,
          tf: targetTf,
          count: parsed.length,
          first: parsed[0]?.time,
          last: parsed[parsed.length - 1]?.time,
          applied: false,
          reason: detail,
        });
        cameraLog('candle load rejected', { requestId, targetTf, parsed: parsed.length, previousCount, loadWindow, contextMiss, detail });
        return;
      }
      setChartCandles(parsed);
      candleCountRef.current = parsed.length;
      if (wantsFullHistory) {
        fullHistoryChartTfsRef.current.add(String(targetTf).toUpperCase());
      }
      const loadedCtx = buildLoadedCandleContext({
        requestId,
        symbol: String(symbol),
        caseId: String(activeCaseDisplayId || ''),
        chartTimeframe: targetTf,
        sourceTimeframe: sourceTimeframeRef.current,
        structureLayer: structureLayerRef.current,
        candleCount: parsed.length,
      });
      if (loadedCtx) {
        loadedCandleContextRef.current = loadedCtx;
        setLoadedCandleContext(loadedCtx);
      }
      logCandleLoadResponse({
        id: requestId,
        tf: targetTf,
        count: parsed.length,
        first: parsed[0]?.time,
        last: parsed[parsed.length - 1]?.time,
        applied: true,
        loadedContext: loadedCtx
          ? formatLoadedCandleContextSummary(loadedCtx)
          : undefined,
      });
      if (!quiet) {
        void runBackgroundDeltaSync({
          symbol,
          timeframe: targetTf,
          window: chartWindow,
          previousCandles: libraryLoad.candles,
        }).then((bg) => {
          if (!isCurrentLoad()) return;
          setLocalLibraryDebug(bg.debug);
          localLibraryDebugRef.current = bg.debug;
          if (!bg.changed || !bg.candles.length) return;
          let refreshed = mergeParsedCandleRowsForChart(parsed, parseCandleRows(bg.candles));
          if (useWindowedLoad && loadWindow && refreshed.length) {
            refreshed = filterCandlesToLoadWindow(refreshed, {
              start: loadWindow.start,
              end: loadWindow.end,
              label: loadWindow.label || 'structural context',
            });
            const maxBars = maxBarsForStructuralWindow(targetTf);
            if (refreshed.length > maxBars) {
              refreshed = trimStructuralCandlesToHorizon(
                refreshed,
                maxBars,
                trimContextRange ? rangeWindowFieldsFromSavedRange(trimContextRange) : structuralVisualContextRef.current,
                targetTf,
              );
            }
          }
          if (!isCurrentLoad() || !refreshed.length) return;
          setChartCandles(refreshed);
          setCandleDataRevision((v) => v + 1);
          candleCountRef.current = refreshed.length;
          if (loadedCtx) {
            const nextCtx = { ...loadedCtx, candleCount: refreshed.length };
            loadedCandleContextRef.current = nextCtx;
            setLoadedCandleContext(nextCtx);
          }
          cameraLog('candle chart refreshed from background delta without camera move', {
            requestId,
            targetTf,
            count: refreshed.length,
            owner: cameraViewOwnerRef.current,
            stableOwner: shouldBlockAutomaticCameraRefit(cameraViewOwnerRef.current),
          });
        }).catch(() => {});
      }
      writeAutoResumeSession(symbol, targetTf);
      const contextRangeId = pendingIntent.contextRangeId || activeRangeIdNow;
      const contextRange = contextRangeId
        ? safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(contextRangeId))
        : null;
      const shouldRestoreReplay = !quiet
        && (preserveStructuralContext || opts?.structuralNavigation)
        && !tradingViewMappingPreserveLoad(targetTf, opts);
      let replaySeedResult = null;
      if (shouldRestoreReplay) {
        replaySeedResult = applyStructuralReplayRestore(parsed, {
          range: contextRange,
          chartTf: targetTf,
          loadWindowStart: loadWindow?.start ?? null,
          loadWindowEnd: loadWindow?.end ?? null,
          reason: opts?.navigationPath || opts?.reason || 'structural-load',
        });
      } else if (!quiet) {
        const preservedIdx = preservedTime
          ? clamp(candleIndexAtOrBefore(parsed, preservedTime), 0, parsed.length - 1)
          : 0;
        setCandleReplayIndex(preservedIdx);
        const nearest = parsed[preservedIdx];
        if (nearest && (candleReplayMode || pendingIntent.intent === 'REPLAY')) {
          setCandleReplayCursorTime(nearest.time);
        }
      }
      const playForwardEnabled = replaySeedResult?.playForwardEnabled
        ?? (parsed.length > 1 && (
          (replaySeedResult?.index ?? candleReplayIndex) < parsed.length - 1
          || !!((activeRangeIdNow || parentRangeIdNow) && structuralDataLoadWindowRef.current?.end)
        ));
      const playForwardReason = replaySeedResult?.playForwardReason
        ?? (playForwardEnabled ? 'ok' : (parsed.length <= 1 ? 'single-bar-window' : 'at-last-bar-no-ahead'));
      const replayIndexForDiag = replaySeedResult?.index
        ?? (preservedTime ? clamp(candleIndexAtOrBefore(parsed, preservedTime), 0, parsed.length - 1) : 0);
      if (!quiet && replaySeedResult) {
        cameraLog('structural replay seed', {
          requestId,
          targetTf,
          seedTime: replaySeedResult.time,
          safeIdx: replaySeedResult.index,
          playForwardEnabled,
          playForwardReason,
        });
      }
      if (!quiet) setLoading(false);
      void loadMapMemory(targetTf, requestId);
      if (!isCurrentLoad()) {
        logCandleLoadResponse({ id: requestId, tf: targetTf, count: parsed.length, applied: false, reason: 'stale-after-memory' });
        cameraLog('candle load ignored as stale after memory', { requestId, targetTf, activeTf:activeTimeframeRef.current });
        return;
      }
      if (
        opts?.skipCamera
        || !candleLoadMayMoveCamera
        || (shouldBlockAutomaticCameraRefit(cameraViewOwnerRef.current) && !isExplicitCameraNavigationReason(pendingIntent.reason))
      ) {
        pendingCameraIntentRef.current = { intent:'NONE' };
        pendingCameraIntentAwaitingTvFitRef.current = false;
        recordCandleLoadDiagnostic({
          ...diagBase,
          returnedCount: parsed.length,
          accepted: true,
          cameraIntent: 'NONE',
          detail: !candleLoadMayMoveCamera ? 'candle-load-preserve-camera' : 'skip-camera',
        });
        if (!quiet) {
          const ext = candleDataExtent(parsed);
          setMessage(`Loaded ${parsed.length} ${targetTf} candles${ext ? ` · latest ${shortTime(ext.end, targetTf)}` : ''}.`);
        }
        return;
      }
      const commandTargetTime = pendingIntent.targetTime || structuralContextTargetTime(contextRange) || preservedTime || null;
      let fitWindow = pendingIntent.fitWindow || null;
      let cameraIntent: CameraIntent = pendingIntent.intent === 'NONE' ? 'PRESERVE_OR_NEAREST_TIME' : pendingIntent.intent;
      const routineMemorySwitch = isRoutineTfMemoryReason(pendingIntent.reason);
      const hasInheritedPrice = !!(pendingIntent.priceDomain
        && Number.isFinite(pendingIntent.priceDomain.low)
        && Number.isFinite(pendingIntent.priceDomain.high)
        && pendingIntent.priceDomain.high > pendingIntent.priceDomain.low);
      if (!routineMemorySwitch) {
        if (contextRangeId && contextRange) {
          fitWindow = structuralRangeFitDomain(contextRange, parsed, targetTf) || fitWindow;
        }
        if (cameraIntent !== 'FIT_STRUCTURAL_RANGE' && fitWindow && contextRangeId) {
          cameraIntent = 'FIT_STRUCTURAL_RANGE';
        }
      }
      let useStructuralPrice = !!(fitWindow
        && Number.isFinite(fitWindow.low)
        && Number.isFinite(fitWindow.high)
        && fitWindow.high > fitWindow.low
        && !hasInheritedPrice);
      if (!routineMemorySwitch && contextMiss) {
        if (!fitWindow && contextRangeId) {
          const contextRange = safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(contextRangeId));
          if (contextRange) fitWindow = structuralRangeFitDomain(contextRange, parsed, targetTf) || fitWindow;
        }
        cameraIntent = fitWindow ? 'FIT_STRUCTURAL_RANGE' : (commandTargetTime ? 'PRESERVE_OR_NEAREST_TIME' : 'LATEST');
        if (!fitWindow) useStructuralPrice = false;
      }
      const destMemoryKeyForLock = chartMemoryKey(String(activeCaseDisplayId || 'global'), symbol, targetTf);
      const lockedDom = cameraMode === 'LOCKED'
        ? (cameraDomainByCaseTf[destMemoryKeyForLock] || cameraDomainByCaseTf[legacyChartMemoryKey(String(activeCaseDisplayId || 'global'), targetTf)])
        : null;
      if (!routineMemorySwitch && lockedDom?.start && lockedDom?.end && !candleWindowOverlapsRange(parsed, lockedDom.start, lockedDom.end)) {
        cameraIntent = 'LATEST';
        fitWindow = null;
        useStructuralPrice = false;
      } else if (cameraIntent === 'CASE' && !commandTargetTime) {
        cameraIntent = 'LATEST';
      }
      let resolvedTargetTime = cameraIntent === 'LATEST'
        ? (parsed[parsed.length - 1]?.time || commandTargetTime)
        : commandTargetTime;
      let resolvedFitWindow = fitWindow;
      let resolvedPriceDomain = useStructuralPrice ? null : (pendingIntent.priceDomain || null);
      if (routineMemorySwitch) {
        const sanitized = sanitizeRoutineMemoryCameraAfterLoad({
          intent: cameraIntent === 'RESTORE_LOCKED' ? 'RESTORE_LOCKED' : cameraIntent === 'LATEST' ? 'LATEST' : 'PRESERVE_OR_NEAREST_TIME',
          reason: pendingIntent.reason || routineTfMemoryReason(String(timeframe).toUpperCase(), targetTf),
          targetTime: resolvedTargetTime,
          fitWindow: resolvedFitWindow as MemoryFitWindow | null,
          priceDomain: resolvedPriceDomain,
          anchorSource: pendingIntent.anchorSource || null,
        }, parsed, targetTf);
        cameraIntent = sanitized.intent as CameraIntent;
        resolvedTargetTime = sanitized.targetTime;
        resolvedFitWindow = sanitized.fitWindow;
        resolvedPriceDomain = sanitized.priceDomain;
        if (sanitized.anchorSource) {
          tradingViewCameraBridge.current.routineAnchorSource = sanitized.anchorSource;
          pendingCameraIntentRef.current = {
            ...pendingCameraIntentRef.current,
            anchorSource: sanitized.anchorSource,
          };
        }
      }
      const cameraPayload = {
        intent: cameraIntent,
        targetTime: resolvedTargetTime,
        reason: pendingIntent.reason || opts?.reason || 'confirmed-candle-load',
        fitWindow: resolvedFitWindow,
        priceDomain: resolvedPriceDomain,
      };
      if (routineMemorySwitch && opts?.timeframeSwitch) {
        const restoreTime = selectedCandle?.time || preservedTime || pendingIntent.targetTime || null;
        const nearest = restoreTime ? resolveNearestCandle(parsed, restoreTime) : null;
        if (nearest) {
          setSelectedCandle(nearest);
          setSelectedCandlePoint(null);
        }
        skipSelectionClearForTfSwitchRef.current = false;
      }
      if (opts?.deferCamera !== false) {
        scheduleDeferredCamera(
          cameraPayload.intent,
          cameraPayload.targetTime,
          cameraPayload.reason,
          cameraPayload.fitWindow,
          cameraPayload.priceDomain,
        );
      } else {
        applyCameraCommand(
          cameraPayload.intent,
          cameraPayload.targetTime,
          cameraPayload.reason,
          undefined,
          cameraPayload.fitWindow,
          cameraPayload.priceDomain,
        );
      }
      const deferPendingClearForTvRoutine =
        chartRendererRef.current === 'tradingview'
        && isRoutineTfMemoryReason(cameraPayload.reason);
      if (deferPendingClearForTvRoutine) {
        pendingCameraIntentAwaitingTvFitRef.current = true;
      } else {
        pendingCameraIntentRef.current = { intent:'NONE' };
        pendingCameraIntentAwaitingTvFitRef.current = false;
      }
      recordCandleLoadDiagnostic({
        ...diagBase,
        returnedCount: rawCount,
        filteredCount: parsed.length,
        accepted: true,
        cameraIntent: cameraPayload.intent,
        replayIndex: replayIndexForDiag,
        playForwardEnabled,
        playForwardReason,
        detail: contextMiss ? 'context-miss-fit-range' : (rawCount !== parsed.length ? 'client-window-filter' : undefined),
      });
      const ext = candleDataExtent(parsed);
      if (!quiet) {
        const diagLine = formatCandleLoadDiagnostic({
          ...diagBase,
          returnedCount: rawCount,
          filteredCount: parsed.length,
          accepted: true,
          cameraIntent: cameraPayload.intent,
          replayIndex: replayIndexForDiag,
          playForwardEnabled,
          playForwardReason,
        });
        if (contextMiss && ext && loadWindow) {
          setMessage(
            `${diagLine} · Partial ${targetTf} cache for ${loadWindow.label} (${loadWindow.start} → ${loadWindow.end}). `
            + `Showing ${shortTime(ext.start, targetTf)} → ${shortTime(ext.end, targetTf)} (${parsed.length} bars).`,
          );
        } else {
          setMessage(`${diagLine}${loadWindow ? '' : ''}${ext ? ` · latest ${shortTime(ext.end, targetTf)}` : ''}.`);
        }
      }
      cameraLog('candle load applied', { requestId, targetTf, intent:cameraPayload.intent, commandTargetTime, contextMiss, loadWindow, quiet, loadContext });
    } catch(e:any) {
      if (!isCurrentLoad()) { cameraLog('candle load error ignored as stale', { requestId, targetTf, error:e?.message || e }); return; }
      recordCandleLoadDiagnostic({ ...diagBase, returnedCount: 0, accepted: false, detail: e?.message || String(e), cameraIntent: 'NONE' });
      if (!quiet) setMessage(`Load ${targetTf} failed: ${e?.name === 'AbortError' ? 'timed out — check VPS connection and click Reload' : (e?.message || e)}`);
    }
    finally {
      if (quiet) candleLoadInFlightRef.current = false;
      candleFeedLoadInFlightRef.current = false;
      setCandleFeedLoading(false);
      if (!quiet) setLoading(false);
    }
  };

  const tradingViewMappingPreserveLoad = (
    requestedTf: string,
    opts?: {
      quiet?: boolean;
      timeframeSwitch?: boolean;
      structuralNavigation?: boolean;
      reason?: string;
      navigationPath?: string;
    },
  ) => {
    const targetTf = String(requestedTf || timeframe).toUpperCase();
    const activeTf = String(activeTimeframeRef.current).toUpperCase();
    if (
      chartRendererRef.current === 'tradingview'
      && tradingViewMappingInputEnabledRef.current
      && candleCountRef.current > 0
      && !opts?.timeframeSwitch
      && targetTf === activeTf
      && (opts?.quiet || opts?.structuralNavigation || opts?.reason === 'feed-mismatch-reload')
    ) {
      return true;
    }
    return shouldPreserveTradingViewMappingCandleUniverse({
      chartRenderer: chartRendererRef.current,
      mappingInputEnabled: tradingViewMappingInputEnabledRef.current,
      timeframeSwitch: opts?.timeframeSwitch,
      targetTf,
      activeChartTf: activeTf,
      candleCount: candleCountRef.current,
      structuralNavigation: opts?.structuralNavigation,
      reason: opts?.reason,
      navigationPath: opts?.navigationPath,
    });
  };

  const resolveReplayCandleAtAction = (): Candle | null => {
    const rows = candlesRef.current;
    if (!rows.length) return null;
    if (candleReplayModeRef.current && candleReplayCursorTimeRef.current) {
      const idx = candleIndexAtOrBefore(rows, candleReplayCursorTimeRef.current);
      return rows[clamp(idx, 0, rows.length - 1)] || null;
    }
    return rows[clamp(candleReplayIndexRef.current, 0, rows.length - 1)] || null;
  };

  const resolveMappingInputCandleAtAction = (): Candle | null => (
    resolveMappingInputCandle({
      chartRenderer: chartRendererRef.current,
      mappingInputEnabled: tradingViewMappingInputEnabledRef.current,
      admittedMappingInputCandle: admittedMappingInputCandleRef.current,
      selectedCandle: selectedCandleRef.current,
      replayCandle: resolveReplayCandleAtAction(),
      candleReplayMode: candleReplayModeRef.current,
    }) as Candle | null
  );

  const buildActiveCandleFeedSnapshot = (): ActiveMappingFeedSnapshot => ({
    symbol: String(symbol).toUpperCase(),
    caseId: String(activeCaseDisplayId || ''),
    chartTimeframe: String(timeframe).toUpperCase(),
    sourceTimeframe: String(sourceTimeframe).toUpperCase(),
    structureLayer: structureLayer as StructureLayerId,
    candleLoadInFlight: candleFeedLoadInFlightRef.current || loading,
    candleCount: candleCountRef.current,
  });

  const stampVisibleLoadedCandleContext = (chartTimeframe = timeframe): LoadedCandleContext | null => {
    const chartTf = String(chartTimeframe).toUpperCase();
    const rehydrated = rehydrateLoadedCandleContextForVisibleFeed({
      loaded: loadedCandleContextRef.current,
      requestId: candleLoadSeqRef.current,
      symbol: String(symbol),
      caseId: String(activeCaseDisplayId || ''),
      chartTimeframe: chartTf,
      sourceTimeframe: sourceTimeframeRef.current,
      structureLayer: structureLayerRef.current,
      candleCount: candleCountRef.current,
    });
    if (rehydrated && rehydrated !== loadedCandleContextRef.current) {
      loadedCandleContextRef.current = rehydrated;
      setLoadedCandleContext(rehydrated);
    }
    return rehydrated;
  };

  const getCandleFeedGuard = (): CandleFeedGuardResult =>
    evaluateCandleFeedGuard(buildActiveCandleFeedSnapshot(), loadedCandleContextRef.current);

  const getTradingViewSelectionFeedGuard = (): CandleFeedGuardResult => {
    const loaded = loadedCandleContextRef.current;
    const active = buildActiveCandleFeedSnapshot();
    const chartStructure = chartStructureForTimeframeStatic(timeframe);
    const chartTf = String(timeframe).toUpperCase();
    const tvLayer = (chartStructure.structure_layer || loaded?.structureLayer || active.structureLayer) as StructureLayerId;
    const tvSourceTf = String(chartStructure.source_timeframe || loaded?.chartTimeframe || chartTf).toUpperCase();
    const tvLoaded = loaded
      ? {
        ...loaded,
        chartTimeframe: String(loaded.chartTimeframe || '').toUpperCase(),
        sourceTimeframe: tvSourceTf,
        structureLayer: tvLayer,
      }
      : null;
    return evaluateCandleFeedGuard({
      ...active,
      chartTimeframe: chartTf,
      sourceTimeframe: tvSourceTf,
      structureLayer: tvLayer,
      candleCount: candleCountRef.current,
    }, tvLoaded);
  };

  const handleTradingViewCandleClick = (candidate: TradingViewSelectedCandle) => {
    const admission = admitTradingViewSelection({
      candidate,
      displayedCandles: tradingViewDisplayCandlesRef.current,
      symbol: String(symbol).toUpperCase(),
      chartTimeframe: activeTimeframeRef.current,
      candleReplayMode: candleReplayModeRef.current,
      replayCutTime: candleReplayCursorTimeRef.current,
    });
    if (!admission.admitted || !admission.mappingInputCandle) {
      applyTvMappingSelectionClear();
      setTradingViewSelectionWarning(admission.message);
      setMessage(admission.message);
      return;
    }
    if (tradingViewMappingInputEnabled) {
      if (!assertCandleFeedReady('TradingView selection')) return;
    } else {
      const guard = getTradingViewSelectionFeedGuard();
      if (!guard.ready) {
        const warning = guard.message || 'TradingView selection blocked — candle feed not aligned.';
        applyTvMappingSelectionClear();
        setTradingViewSelectionWarning(warning);
        setMessage(warning);
        return;
      }
    }
    if (tradingViewMappingInputEnabled) {
      if (!applyTvMappingSelectionCommit(admission.mappingInputCandle)) {
        setTradingViewSelectionWarning('Selection blocked — invalid admitted candle row.');
        setMessage('Selection blocked — invalid admitted candle row.');
        return;
      }
      const row = admission.mappingInputCandle!;
      setSelectedCandle({
        time: row.time,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        symbol: row.symbol,
        timeframe: row.timeframe,
      } as Candle);
      setSelectedCandlePoint({ price: Number(row.close.toFixed(2)) });
    } else {
      applyTvMappingSelectionClear();
      setTradingViewSelectedCandle(candidate);
    }
    setTradingViewSelectionWarning(null);
    setMessage(tradingViewMappingInputEnabled
      ? `TradingView selected ${shortTime(admission.mappingInputCandle.time, admission.mappingInputCandle.timeframe)} · C ${admission.mappingInputCandle.close.toFixed(2)} · H/L/↑/↓ ready.`
      : `TradingView selected ${shortTime(candidate.time, candidate.chartTimeframe)} · C ${candidate.close.toFixed(2)}. Read-only bridge; mapping keys remain D3-only.`);
  };

  const assertCandleFeedReady = (actionLabel = 'Marking'): boolean => {
    if (
      chartRendererRef.current === 'tradingview'
      && tradingViewMappingInputEnabledRef.current
      && candleCountRef.current > 0
    ) {
      stampVisibleLoadedCandleContext();
      return true;
    }
    const guard = getCandleFeedGuard();
    if (guard.ready) return true;
    setMessage(guard.message || `${actionLabel} blocked — candle feed not aligned.`);
    if (guard.reloadChartTimeframe) {
      const reloadKey = `${guard.mismatch || 'reload'}:${guard.reloadChartTimeframe}:${structureLayerRef.current}:${sourceTimeframeRef.current}`;
      if (candleFeedReloadKeyRef.current !== reloadKey && !candleFeedLoadInFlightRef.current) {
        candleFeedReloadKeyRef.current = reloadKey;
        void loadCandles(guard.reloadChartTimeframe, {
          reason: 'feed-mismatch-reload',
          structuralNavigation: true,
          deferCamera: true,
        }).finally(() => {
          candleFeedReloadKeyRef.current = '';
        });
      }
    }
    return false;
  };

  const assertAdmittedMappingInputCandle = (actionLabel = 'Marking'): boolean => {
    if (chartRendererRef.current !== 'tradingview' || !tradingViewMappingInputEnabledRef.current) return true;
    if (resolveMappingInputCandleAtAction()) return true;
    setMessage(`${actionLabel} blocked — click a visible TradingView candle first.`);
    setTradingViewSelectionWarning('No admitted TradingView candle for mapping.');
    return false;
  };

  const fetchCandleFeedStatus = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/candles/status`).then(x => x.json());
      if (r?.ok) setCandleFeedStatus(r);
      return r;
    } catch {
      return null;
    }
  };

  const syncCandlesFromMt5 = async (forceBackfill = false) => {
    if (candleSyncInFlightRef.current) return { ok: false, skipped: true };
    candleSyncInFlightRef.current = true;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/candles/sync-mt5`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: [symbol], force_backfill: forceBackfill }),
      }).then(x => x.json());
      await fetchCandleFeedStatus();
      return r;
    } catch (e: any) {
      return { ok: false, error: e?.message || String(e) };
    } finally {
      candleSyncInFlightRef.current = false;
    }
  };

  const bootstrapCandleFeed = async () => {
    const status = await fetchCandleFeedStatus();
    const groups = safeArray<any>(status?.groups);
    const row = groups.find((g: any) => String(g.symbol) === symbol && String(g.timeframe).toUpperCase() === 'M15');
    const count = Number(row?.count || 0);
    const lastMs = parseMt5TimeMs(row?.last_time);
    const staleMs = Date.now() - (3 * 60 * 60 * 1000);
    const needsBackfill = count < 500 || lastMs === null || lastMs < staleMs;
    if (!needsBackfill) return;
    setMessage(`Refreshing ${symbol} OHLC from MT5...`);
    const sync = await syncCandlesFromMt5(true);
    if (sync?.ok) {
      setMessage('MT5 sync finished. Loading candles...');
      return;
    }
    // VPS may not have sync-mt5 yet — GET /api/v1/candles?refresh=1 triggers inline MT5 upsert after deploy.
    if (sync?.error?.includes('404') || sync?.error?.includes('Not Found') || String(sync?.error || '').includes('unavailable')) {
      setMessage(`MT5 sync endpoint not deployed — requesting inline MT5 refresh on next candle load.`);
    } else if (sync?.error) {
      setMessage(`MT5 sync: ${sync.error}`);
    }
  };

  const importCommon = async () => {
    setLoading(true); setMessage('Importing EA CSV files from Common\\Files...');
    try {
      const r = await fetch(`${BASE_URL}/api/v1/candles/import-common-files`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ symbol, timeframes: MAP_TIMEFRAMES })}).then(x=>x.json());
      if (r.ok) {
        await fetchCandleFeedStatus();
        await loadCandles(timeframe);
        setMessage('EA CSV import finished and chart reloaded.');
      } else {
        setMessage(`Import failed: ${r.error || 'unknown'}`);
      }
    } catch(e:any) { setMessage(`Import failed: ${e?.message || e}`); }
    finally { setLoading(false); }
  };

  const syncMt5Now = async () => {
    setLoading(true);
    setMessage(`Syncing ${symbol} OHLC from MT5...`);
    try {
      const r = await syncCandlesFromMt5(true);
      if (r?.ok) {
        setMessage('MT5 sync finished. Reloading chart...');
        await loadCandles(timeframe);
      } else {
        setMessage(`MT5 sync failed: ${r?.error || r?.reason || 'endpoint unavailable'}. Deploy candle_sync.py on VPS and restart uvicorn.`);
      }
    } catch (e: any) {
      setMessage(`MT5 sync failed: ${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const skipBootstrapOnceRef = useRef(false);
  const deferAutoResumeForMappingSessionRef = useRef<boolean | null>(null);
  if (deferAutoResumeForMappingSessionRef.current === null) {
    deferAutoResumeForMappingSessionRef.current = readMappingSessionForSymbol(symbol) !== null;
  }
  const candleSyncInFlightRef = useRef(false);
  const candleLoadInFlightRef = useRef(false);

  const saveEvent = async (ev:MapEvent, source: InspectorCommitSource = 'manual_mark') => {
    // v087.29 keylogger mode: persist only the raw click/action ledger.
    // Local markers remain for the chart; backend relational map_events/ranges are intentionally bypassed.
    setSessionEventIds(prev => { const next = new Set(prev); next.add(String(ev.id)); return next; });
    await postRawMappingEvent(ev, source);
  };



  const saveHTFStateSnapshot = async (_patch:any = {}) => {
    // v087.29: no live HTF state snapshots during mapping. Python compiler owns derived state later.
    return;
  };


  const acceptHTFCandidate = async (cand:HTFCandidate) => {
    if (!cand?.candle) return;
    const ev:MapEvent = {
      id: cand.id,
      event_type: cand.event_type,
      event_name: cand.label,
      time: cand.time,
      price: Number(cand.price.toFixed(2)),
      zone: zoneLabel(zonePercent(cand.price, low, high)),
      zone_percent: (() => { const p = zonePercent(cand.price, low, high); return p === null ? undefined : Number(p.toFixed(2)); })(),
      notes: cand.reason,
      source: 'auto',
      candle_open: cand.candle.open,
      candle_high: cand.candle.high,
      candle_low: cand.candle.low,
      candle_close: cand.candle.close,
      primitive: cand.primitive,
      derived_event_code: cand.derived_event_code,
      movement_rule: cand.movement_rule,
      range_status_after: cand.range_status_after,
      engine_source: 'HTF_SEMI_AUTO_STATE_ENGINE',
      logic_version: 'htf_core_state_contract_v087_16',
      candidate_id: cand.id,
      confidence: cand.confidence,
      meta_json: { ...cand.meta, case_id: activeCaseId || null, range_high: high, range_low: low, timeframe, accepted_from_candidate:true },
    };
    const lifecycleLock = htfCandidateLockKey(cand, timeframe, low, high);
    if (lifecycleLock) setHtfAcceptedSuggestionLocks(prev => Array.from(new Set([...(prev || []), lifecycleLock])));
    upsertMarkerIntoEvents(ev);
    await saveEvent(ev, 'htf_candidate');
    await saveHTFStateSnapshot({ last_transition:cand.derived_event_code, last_candidate:cand.id, range_status_after:cand.range_status_after });
    if (cand.primitive === 'RANGE_REBASE' && cand.meta) {
      const oldSnapshot = { high, low, start:rangeWindow.start, end:rangeWindow.end, preserved_for:'RETRACEMENT_DEPTH_PROFILE_STATS', rebase_candidate_id:cand.id };
      const mh = Number(cand.meta.new_range_high);
      const ml = Number(cand.meta.new_range_low);
      if (Number.isFinite(mh) && Number.isFinite(ml) && mh > ml) {
        const highTime = cand.meta.new_range_high_time || cand.meta.responsible_high_time || cand.time;
        const lowTime = cand.meta.new_range_low_time || cand.meta.responsible_low_time || cand.time;
        const ms = [highTime, lowTime].map((t:string)=>new Date(String(t)).getTime()).filter(Number.isFinite);
        const nextWindow = ms.length >= 2
          ? { start:new Date(Math.min(...ms)).toISOString(), end:new Date(Math.max(...ms)).toISOString() }
          : { start: lowTime || highTime || cand.time, end: highTime || lowTime || cand.time };
        setMeasurementRangeByTf(prev => ({ ...prev, [timeframe]: oldSnapshot }));
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high:String(Number(mh.toFixed(2))), low:String(Number(ml.toFixed(2))) } }));
        setRangeWindowByTf(prev => ({ ...prev, [timeframe]: nextWindow }));
        await saveActiveRangeDirect({ high:mh, low:ml, high_time:highTime, low_time:lowTime, source:'electron-htf-visible-rebase-v087_16' });
        await saveHTFStateSnapshot({
          __range_override:{ high:mh, low:ml, start:nextWindow.start, end:nextWindow.end },
          last_transition:'RANGE_REBASED_VISIBLE_FIB',
          previous_range_snapshot:oldSnapshot,
          active_range_rebased_to:{ high:mh, low:ml, high_time:highTime, low_time:lowTime },
          measurement_range_preserved:true,
          measurement_old_range:oldSnapshot,
          active_fib_range_is_new_range:true,
        });
      }
    }
    setHtfCandidates(prev => prev.filter(x => x.id !== cand.id));
    setMessage(cand.primitive === 'RANGE_REBASE' ? `Accepted ${cand.label}. Visible fib rebased; old range preserved for retracement stats.` : `Accepted ${cand.label}. Stored primitive + derived event + HTF state metadata. The machine did its paperwork, for once.`);
  };

  useEffect(() => {
    if (!hasRange || !activeCaseId) return;
    const bos = htfVisibleCandidates.find(c => c.primitive === 'BREACH' && (String(c.derived_event_code || c.event_type).includes('BOS_UP') || String(c.derived_event_code || c.event_type).includes('BOS_DOWN')));
    if (!bos || autoSavedBosIdsRef.current.has(bos.id)) return;
    autoSavedBosIdsRef.current.add(bos.id);
    acceptHTFCandidate(bos).catch(err => setMessage(`BOS autosave failed: ${err?.message || err}`));
  }, [htfVisibleCandidates.map(c=>c.id).join('|'), hasRange, activeCaseId]);

  const rejectHTFCandidate = async (cand:HTFCandidate) => {
    if (!cand?.candle) return;
    setHtfRejectedCandidateIds(prev => Array.from(new Set([...(prev || []), cand.id])));
    const ev:MapEvent = {
      id: `${cand.id}_REJECTED`,
      event_type: 'HTF_CANDIDATE_REJECTED',
      event_name: `Rejected: ${cand.label}`,
      time: cand.time,
      price: Number(cand.price.toFixed(2)),
      zone: zoneLabel(zonePercent(cand.price, low, high)),
      zone_percent: (() => { const p = zonePercent(cand.price, low, high); return p === null ? undefined : Number(p.toFixed(2)); })(),
      notes: cand.reason,
      source: 'candidate',
      candle_open: cand.candle.open,
      candle_high: cand.candle.high,
      candle_low: cand.candle.low,
      candle_close: cand.candle.close,
      primitive: cand.primitive,
      derived_event_code: cand.derived_event_code,
      movement_rule: cand.movement_rule,
      range_status_after: cand.range_status_after,
      engine_source: 'HTF_SEMI_AUTO_STATE_ENGINE',
      logic_version: 'candidate_audit_v087_18',
      candidate_id: cand.id,
      candidate_status: 'REJECTED',
      confidence: cand.confidence,
      meta_json: { ...cand.meta, case_id: activeCaseId || null, range_high: high, range_low: low, timeframe, candidate_status:'REJECTED', rejected_from_candidate:true, rejected_at:new Date().toISOString(), original_event_type:cand.event_type, original_label:cand.label, rejected_reason:'USER_REJECTED_SEMI_AUTO_CANDIDATE', price_location_pct: (() => { const p = zonePercent(cand.price, low, high); return p === null ? null : Number(p.toFixed(2)); })() },
    };
    upsertMarkerIntoEvents(ev);
    await saveEvent(ev, 'htf_candidate');
    await saveHTFStateSnapshot({ last_rejected_candidate:cand.id, rejected_candidate_type:cand.event_type, rejected_candidate_rule:cand.movement_rule });
    setHtfCandidates(prev => prev.filter(x => x.id !== cand.id));
    setMessage(`Rejected ${cand.label} and saved it to the Candidate Audit log. Even bad suggestions now have a job.`);
  };

  const editHTFCandidatePrice = async (cand:HTFCandidate) => {
    const raw = window.prompt('Edit candidate price before saving:', String(cand.price));
    if (raw === null) return;
    const n = Number(raw);
    if (!Number.isFinite(n)) { setMessage('That price is not a number. Humanity remains undefeated by input boxes.'); return; }
    await acceptHTFCandidate({ ...cand, price:n, status:'EDITED', meta:{ ...cand.meta, user_edited_price:true, original_price:cand.price }});
  };

  const buildRangePayloadFromEvents = (sourceEvents:MapEvent[]) => {
    const source = safeArray<MapEvent>(sourceEvents);
    const lastRangeHigh = latestRangeHighEvent(source);
    const lastRangeLow = latestRangeLowEvent(source);
    const lastRefHigh = [...source].reverse().find(e => isRefHighMarker(e?.event_type));
    const lastRefLow = [...source].reverse().find(e => isRefLowMarker(e?.event_type));
    const ms = [lastRangeHigh?.time, lastRangeLow?.time].filter(Boolean).map((t:any)=>new Date(String(t)).getTime()).filter(Number.isFinite);
    const rangeStart = ms.length ? new Date(Math.min(...ms)).toISOString() : undefined;
    const rangeEnd = ms.length ? new Date(Math.max(...ms)).toISOString() : undefined;
    return {
      symbol,
      timeframe,
      case_id: activeCaseId || null,
      layer: timeframe,
      parent_timeframe: parentTimeframeFor(timeframe) || null,
      range_key: activeCaseId ? `case_${activeCaseId}_${timeframe}_active` : 'active',
      range_high_price: lastRangeHigh?.price,
      range_high_time: lastRangeHigh?.time,
      range_low_price: lastRangeLow?.price,
      range_low_time: lastRangeLow?.time,
      active_from_time: rangeStart,
      inactive_from_time: rangeEnd,
      range_start_time: rangeStart,
      range_end_time: rangeEnd,
      ref_high_price: lastRefHigh?.price,
      ref_high_time: lastRefHigh?.time,
      ref_low_price: lastRefLow?.price,
      ref_low_time: lastRefLow?.time,
      source: 'electron-map-studio-structure-only',
      structure_version: 'STRUCTURE_ONLY_V2'
    };
  };

  // v087.29 KEYLOGGER MODE:
  // Electron is now a visual interpreter + raw event emitter only.
  // Parent links, zones, profiles, phases, objectives and features are compiled later by the local processor.
  const rawCandleTimeMs = (time:any) => {
    const ms = new Date(String(time || '')).getTime();
    return Number.isFinite(ms) ? ms : Date.now();
  };

  const rawEventSideFor = (type:string):'HIGH'|'LOW'|'NONE' => {
    const t = String(type || '').toUpperCase();
    if (t.includes('HIGH') || t.includes('BOS_UP') || t.includes('CHOCH_UP')) return 'HIGH';
    if (t.includes('LOW') || t.includes('BOS_DOWN') || t.includes('CHOCH_DOWN')) return 'LOW';
    return 'NONE';
  };

  const rawEventTypeFor = (type:string, source?:string):string => {
    const t = String(type || '').toUpperCase();
    const isAuto = String(source || '').toLowerCase() === 'auto';
    if (t === 'RANGE_HIGH' || t === 'RANGE_LOW') return 'SET_ANCHOR';
    if (t.includes('BOS')) return isAuto ? 'AUTO_BOS' : 'MANUAL_BOS';
    if (t.includes('RECLAIM')) return 'RECLAIM';
    if (t.includes('ABANDON') || t.includes('INVALID')) return 'ABANDON_RANGE';
    return 'NOTE';
  };

  const rawPriceModeFor = (ev:MapEvent):number|null => {
    const n = Number(ev?.price);
    return Number.isFinite(n) ? n : null;
  };

  const sortCaseRows = (rows:any[]) => [...safeArray<any>(rows)].sort((a:any,b:any) => {
    const timeOf = (x:any) => {
      const raw = x?.updated_at || x?.created_at || x?.updated_at_utc_ms || x?.created_at_utc_ms || 0;
      const n = Number(raw);
      if (Number.isFinite(n) && n > 100000000000) return n;
      const ms = new Date(String(raw || '')).getTime();
      return Number.isFinite(ms) ? ms : 0;
    };
    return timeOf(b) - timeOf(a) || String(a?.seed_name || '').localeCompare(String(b?.seed_name || ''), undefined, { numeric: true }) || String(b?.id || '').localeCompare(String(a?.id || ''));
  });

  const rawCaseRecentRow = (caseId:string, rawCase?:any) => {
    const tf = String(rawCase?.base_timeframe || caseTimeframe || timeframe || 'W1').toUpperCase();
    const scope = timeframeToScope(tf);
    const name = String(rawCase?.case_name || seedName || activeCaseLabel || `${symbol}_${tf}_Raw_Case`).replace(/\s+·\s+[a-f0-9-]+$/i, '');
    const now = new Date().toISOString();
    const created = rawCase?.created_at_utc_ms ? new Date(Number(rawCase.created_at_utc_ms)).toISOString() : now;
    const updated = rawCase?.updated_at_utc_ms ? new Date(Number(rawCase.updated_at_utc_ms)).toISOString() : created;
    return {
      id: caseId,
      raw_case_id: caseId,
      is_raw_mapping_case: true,
      seed_name: name,
      symbol: rawCase?.symbol || symbol,
      replay_timeframe: tf,
      case_timeframe: tf,
      case_scope: scope,
      replay_candle_time: updated,
      created_at: created,
      updated_at: updated,
      raw_case: rawCase || null,
      notes: rawCase?.notes || '',
    };
  };

  const rawCaseRowFromBackend = (rawCase:any) => rawCaseRecentRow(String(rawCase?.case_id || ''), rawCase);

  const loadRawCaseLedgerIntoWorkspace = async (rawId:string, preferredTf?:string) => {
    if (!rawId) return 0;
    try {
      const exported = await exportRawCaseEvents(BASE_URL, rawId);
      const grouped = groupRawDisplayEventsByTimeframe(safeArray<any>(exported?.sequence_by_intent));
      const tfKeys = Object.keys(grouped);
      if (tfKeys.length) {
        setEventsByTf(prev => ({ ...prev, ...grouped }));
        setRangeByTf(prev => {
          const out:any = { ...prev };
          for (const [tf, rows] of Object.entries(grouped)) {
            const highs = safeArray<MapEvent>(rows).filter((e:any) => String(e?.event_type || '').toUpperCase().includes('RANGE_HIGH') || String(e?.meta_json?.candle_role || '').toUpperCase() === 'HIGH');
            const lows = safeArray<MapEvent>(rows).filter((e:any) => String(e?.event_type || '').toUpperCase().includes('RANGE_LOW') || String(e?.meta_json?.candle_role || '').toUpperCase() === 'LOW');
            const latestHigh = highs[highs.length - 1];
            const latestLow = lows[lows.length - 1];
            if (latestHigh || latestLow) {
              out[tf] = {
                high: latestHigh ? String(Number(latestHigh.price).toFixed(2)) : (out[tf]?.high || ''),
                low: latestLow ? String(Number(latestLow.price).toFixed(2)) : (out[tf]?.low || ''),
              };
            }
          }
          return out;
        });
      }
      const nextTf = String(preferredTf || exported?.meta?.case?.base_timeframe || caseTimeframe || timeframe).toUpperCase();
      if (nextTf) activeTimeframeRef.current = nextTf;
      return tfKeys.reduce((sum, tf) => sum + safeArray<MapEvent>(grouped[tf]).length, 0);
    } catch (err:any) {
      setMessage(`Failed to load raw case ledger from VPS: ${err?.message || err}`);
      return 0;
    }
  };

  const mergeSavedCases = (rows:any[], extra?:any) => {
    const merged = new globalThis.Map<string, any>();
    for (const row of safeArray<any>(rows)) {
      const key = String(row?.raw_case_id || row?.id || '');
      if (key) merged.set(key, row);
    }
    if (extra) {
      const key = String(extra?.raw_case_id || extra?.id || '');
      if (key) merged.set(key, { ...(merged.get(key) || {}), ...extra });
    }
    return sortCaseRows(Array.from(merged.values()));
  };

  const caseMatchesContext = (idea:any) => {
    const isActive = String(idea?.raw_case_id || idea?.id || '') === String(activeCaseDisplayId || '');
    if (isActive) return true;
    if (String(idea?.symbol || symbol).toUpperCase() !== String(symbol).toUpperCase()) return false;
    const tf = String(idea?.case_timeframe || idea?.replay_timeframe || idea?.raw_case?.base_timeframe || '').toUpperCase();
    const scope = String(idea?.case_scope || (tf ? timeframeToScope(tf) : '') || '').toUpperCase();
    return !tf || tf === String(caseTimeframe).toUpperCase() || scope === String(caseScope).toUpperCase();
  };

  const ensureRawCase = async (opts?: { forceNew?: boolean }) => {
    const caseName = cleanCaseDisplayName(seedName) || cleanCaseDisplayName(activeCaseLabel) || `${String(symbol).toUpperCase()} Case`;
    const existingId = opts?.forceNew ? '' : String(rawActiveCaseId || '').trim();
    try {
      const payload = {
        symbol,
        case_name: caseName,
        base_timeframe: caseTimeframe || timeframe || 'W1',
        price_scale_default: String(symbol).toUpperCase().includes('XAU') ? 100 : 100000,
        notes: seedNotes || 'Created from Electron raw mapping contract',
        ...(existingId ? { case_id: existingId } : {}),
      };
      const r = await createRawCase(BASE_URL, payload);
      const id = String(r?.case?.case_id || r?.case_id || existingId || '');
      if (!id) throw new Error('Raw case create returned no case_id');
      setRawActiveCaseId(id);
      setActiveCaseId(null);
      setActiveCaseLabel(caseName);
      setSeedName(caseName);
      setSeedIdeas(prev => mergeSavedCases(prev, rawCaseRecentRow(id, r?.case)));
      return id;
    } catch (err: any) {
      setMessage(`Raw case save failed: ${err?.message || err}`);
      return null;
    }
  };

  const postRawMappingEvent = async (ev:MapEvent, source: InspectorCommitSource = 'manual_mark') => {
    const rawCaseId = await ensureRawCase();
    if (!rawCaseId) { setMessage('Save/open a case before mapping raw events. The paper needs a folder, tragically.'); return null; }
    const candleIdx = candles.findIndex(c => c.time === ev.time);
    const eventSource = String(ev.source || '').toLowerCase() === 'auto' ? 'auto' : 'manual';
    const payload = {
      event_id: String(ev.id || markerIdForCandle({ time: ev.time || new Date().toISOString(), open:0, high:Number(ev.price||0), low:Number(ev.price||0), close:Number(ev.price||0), volume:0 } as any, ev.event_type || 'NOTE')),
      case_id: rawCaseId,
      symbol,
      timeframe,
      candle_time_utc_ms: rawCandleTimeMs(ev.time),
      candle_index: candleIdx >= 0 ? candleIdx : null,
      price: rawPriceModeFor(ev),
      event_type: rawEventTypeFor(ev.event_type, eventSource),
      event_side: rawEventSideFor(ev.event_type),
      source: eventSource,
      supersedes_event_id: null,
      notes: ev.notes || ev.event_name || '',
      raw_payload_json: {
        legacy_event_type: ev.event_type,
        legacy_event_name: ev.event_name,
        candle_open: ev.candle_open,
        candle_high: ev.candle_high,
        candle_low: ev.candle_low,
        candle_close: ev.candle_close,
        electron_version: 'v087.29_keylogger_mode'
      }
    };
    const r = await inspectorCommit({
      baseUrl: BASE_URL,
      kind: 'raw_mapping_event',
      source,
      payload,
    });
    if (!r.ok) setMessage(`Raw ledger save failed: ${r.error || 'unknown backend tantrum'}`);
    return r.data ?? { ok: false, error: r.error };
  };

  const saveActiveRange = async (_sourceEvents:MapEvent[]) => {
    // v087.29: no live range persistence during mapping. Raw events are the only input truth.
    return;
  };

  const saveActiveRangeDirect = async (_rg:{ high:number; low:number; high_time?:string; low_time?:string; source?:string }) => {
    // v087.29: disabled. The local processor rebuilds ranges from raw_mapping_events later.
    return;
  };

  const syncRangeFromEvents = (nextEvents:MapEvent[], persist:boolean = true, targetTf = timeframe) => {
    const source = safeArray<MapEvent>(nextEvents);
    const lastRangeHigh = latestRangeHighEvent(source);
    const lastRangeLow = latestRangeLowEvent(source);

    setRangeByTf(prev => ({
      ...prev,
      [targetTf]: {
        high: lastRangeHigh ? String(Number(lastRangeHigh.price).toFixed(2)) : (prev[targetTf]?.high || ''),
        low: lastRangeLow ? String(Number(lastRangeLow.price).toFixed(2)) : (prev[targetTf]?.low || '')
      }
    }));

    const anchorTimes = [lastRangeHigh?.time, lastRangeLow?.time].filter(Boolean) as string[];
    if (anchorTimes.length >= 2) {
      const ms = anchorTimes.map(t => new Date(t).getTime()).filter(Number.isFinite);
      if (ms.length >= 2) {
        setRangeWindowByTf(prev => ({
          ...prev,
          [targetTf]: {
            start: new Date(Math.min(...ms)).toISOString(),
            end: new Date(Math.max(...ms)).toISOString()
          }
        }));
      }
    } else {
      setRangeWindowByTf(prev => ({ ...prev, [targetTf]: {} }));
    }
    if (persist) saveActiveRange(source);
  };

  const deleteEvent = async (id:string) => {
    setEventsForTf(prev=>{
      const next = prev.filter(e=>e.id!==id);
      syncRangeFromEvents(next);
      return next;
    });
    try {
      const rawId = rawActiveCaseId || (activeCaseId ? String(activeCaseId) : '');
      if (rawId) {
        await inspectorCommit({
          baseUrl: BASE_URL,
          kind: 'raw_mapping_event_delete',
          source: 'raw_delete',
          payload: { case_id: rawId, event_id: id, notes: 'Deleted from Electron v087.29 UI' },
        });
      }
    } catch { /* local delete still counts */ }
    setMessage('Deleted local marker and appended DELETE_RECORD to raw ledger. No relational swamp involved.');
  };

  const clearSelectedCandleEvents = async () => {
    if (!selectedCandle) return;
    const t = selectedCandle.time;
    let nextEvents:MapEvent[] = [];
    setEventsForTf(prev=>{
      const next = prev.filter(e=>e.time !== t);
      nextEvents = next;
      syncRangeFromEvents(next);
      return next;
    });
    // v087.29: bulk clear is local only unless individual event handles are deleted. Raw ledger remains append-only.
    setMessage(`Cleared local events on ${shortTime(t, timeframe)}. Use event-handle delete for permanent DELETE_RECORD entries.`);
  };

  const markerIdForCandle = (candle:Candle, type:string) => {
    const safeSymbol = String(symbol || 'SYMBOL').toUpperCase().replace(/[^A-Z0-9]+/g, '');
    const safeTf = String(timeframe || 'TF').toUpperCase().replace(/[^A-Z0-9]+/g, '');
    const safeType = String(type || 'EVENT').toUpperCase().replace(/[^A-Z0-9_]+/g, '_');
    const candleIndex = candles.findIndex(c => c.time === candle.time);
    const idx = candleIndex >= 0 ? candleIndex : new Date(candle.time).getTime();
    return `${safeSymbol}_${safeTf}_${idx}_${safeType}`;
  };

  const upsertMarkerIntoEvents = (ev:MapEvent, replaceType?:string) => {
    // Important: bundle saves can add multiple tags before React gets a chance to re-render.
    // Use a live ref, update it immediately, then commit state. Otherwise Set W High/Low
    // markers draw as dots but the fib engine never receives both anchors. Delightful little trap.
    const currentTf = timeframe;
    const prevEvents = safeArray<MapEvent>(eventsByTfRef.current?.[currentTf]);
    const base = replaceType ? prevEvents.filter(e=>e.event_type !== replaceType) : prevEvents;
    const existingIdx = base.findIndex(e => e.id === ev.id);
    const nextEvents = existingIdx >= 0 ? base.map((e,i)=>i===existingIdx ? ev : e) : [...base, ev];
    eventsByTfRef.current = { ...eventsByTfRef.current, [currentTf]: nextEvents };
    setEventsByTf(prev => ({ ...prev, [currentTf]: nextEvents }));
    return nextEvents;
  };

  const upsertCandleEvent = async (candle:Candle, type:string, priceMode:'high'|'low'|'close'='close', customName?:string, replaceType?:string) => {
    const price = priceMode === 'high' ? candle.high : priceMode === 'low' ? candle.low : candle.close;
    const activeLow = parseNum(rangeByTf[timeframe]?.low || rangeLow);
    const activeHigh = parseNum(rangeByTf[timeframe]?.high || rangeHigh);
    const pct = (Number.isFinite(activeLow) && Number.isFinite(activeHigh) && activeHigh > activeLow) ? zonePercent(price, activeLow, activeHigh) : null;
    const ev:MapEvent = {
      id: markerIdForCandle(candle, type), event_type: type, event_name: customName || type, time: candle.time, price: Number(price.toFixed(2)),
      zone: zoneLabel(pct), zone_percent: pct === null ? undefined : Number(pct.toFixed(2)), notes: '', candle_open: candle.open, candle_high: candle.high, candle_low: candle.low, candle_close: candle.close
    };
    const nextEvents = upsertMarkerIntoEvents(ev, replaceType);
    await saveEvent(ev);
    if (isRangeAnchorMarker(type)) {
      // v086.12: explicit anchor saves update ONLY the chosen side.
      // Do not resync both high+low from the full event ledger here, because an older
      // backend/legacy low can hijack the range when Josh later saves the high. Evil little goblin.
      if (isRangeHighMarker(type)) {
        const nextHigh = String(Number(candle.high).toFixed(2));
        setRangeHigh(nextHigh);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: nextHigh, low: prev[timeframe]?.low || '' } }));
        mergeRangeWindowTime(candle.time);
      }
      if (isRangeLowMarker(type)) {
        const nextLow = String(Number(candle.low).toFixed(2));
        setRangeLow(nextLow);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low: nextLow } }));
        mergeRangeWindowTime(candle.time);
      }
      await saveActiveRange(nextEvents);
    } else if (isRefHighMarker(type) || isRefLowMarker(type)) {
      await saveActiveRange(nextEvents);
    }
    setMessage(`Marked ${ev.event_name} at ${ev.price} · ${shortTime(ev.time, timeframe)} · saved to backend`);
  };

  const addEventAt = async (info:{time?:string; price:number; candle?:Candle|null}) => {
    if (!hasRange) { setMessage('Mark Range High and Low first. Yes, even the map needs coordinates.'); return; }
    const pct = zonePercent(info.price, low, high);
    const ev:MapEvent = {
      id: info.candle ? markerIdForCandle(info.candle, eventType) : `${symbol}_${timeframe}_${new Date(info.time || Date.now()).getTime()}_${eventType}`,
      event_type: eventType,
      event_name: eventName || eventType,
      time: info.time,
      price: Number(info.price.toFixed(2)),
      zone: zoneLabel(pct),
      zone_percent: Number((pct ?? 0).toFixed(2)),
      notes: ''
    };
    upsertMarkerIntoEvents(ev);
    await saveEvent(ev, 'chart_click');
    setMessage(`Saved ${ev.event_name} at ${ev.price} (${ev.zone}) · ${shortTime(ev.time, timeframe)}`);
  };


  const mergeRangeWindowTime = (time:string) => {
    setRangeWindowByTf(prev => {
      const current = prev[timeframe] || {};
      const times = [current.start, current.end, time].filter(Boolean).map(x => new Date(String(x)).getTime()).filter(Number.isFinite);
      if (!times.length) return prev;
      const start = new Date(Math.min(...times)).toISOString();
      const end = new Date(Math.max(...times)).toISOString();
      return { ...prev, [timeframe]: { start, end } };
    });
  };

  const saveRawMarker = async (side: 'HIGH' | 'LOW' | 'REF', candle: Candle, source: InspectorCommitSource = 'manual_mark') => {
    if (rawMarkSaving) return;
    setRawMarkSaving(true);

    const localType = side === 'HIGH' ? 'RANGE_HIGH' : side === 'LOW' ? 'RANGE_LOW' : 'SET_ANCHOR_REF';
    const displayMarkerId = markerIdForCandle(candle, localType);
    const eventId = crypto.randomUUID();

    try {
      const caseId = rawActiveCaseId || await ensureRawCase();
      if (!caseId) throw new Error('No raw case id. Save or create a raw case first.');

      const price = side === 'HIGH' ? candle.high : side === 'LOW' ? candle.low : candle.close;
      const candleIdx = candles.findIndex(c => c.time === candle.time);
      const payload = buildRawPayloadJson({
        event_id: eventId,
        case_id: caseId,
        symbol,
        timeframe,
        candle_time_utc_ms: rawCandleTimeMs(candle.time),
        candle_index: candleIdx >= 0 ? candleIdx : null,
        price: Number(price.toFixed(2)),
        event_type: 'SET_ANCHOR',
        semantic_side: side,
        source: 'manual',
        notes: side === 'REF' ? 'Set REF anchor' : `Set ${side} anchor`,
        extra_payload: {
          display_marker_id: displayMarkerId,
          candle_role: side,
          candle_open: candle.open,
          candle_high: candle.high,
          candle_low: candle.low,
          candle_close: candle.close,
          electron_version: 'v087.30_raw_mapping_contract',
        },
      });

      await saveRawEvent(BASE_URL, payload, source);

      const replaceType = side === 'HIGH' ? 'RANGE_HIGH' : side === 'LOW' ? 'RANGE_LOW' : 'SET_ANCHOR_REF';
      const ev: MapEvent = {
        id: displayMarkerId,
        raw_event_id: eventId,
        event_type: localType,
        event_name: side === 'REF' ? 'Set REF' : localType,
        time: candle.time,
        price: Number(price.toFixed(2)),
        notes: '',
        source: 'manual',
        candle_open: candle.open,
        candle_high: candle.high,
        candle_low: candle.low,
        candle_close: candle.close,
        meta_json: { raw_event_id: eventId, display_marker_id: displayMarkerId, candle_role: side },
      };
      upsertMarkerIntoEvents(ev, replaceType);

      if (side === 'HIGH') {
        const nextHigh = String(Number(candle.high).toFixed(2));
        setRangeHigh(nextHigh);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: nextHigh, low: prev[timeframe]?.low || '' } }));
        mergeRangeWindowTime(candle.time);
      }
      if (side === 'LOW') {
        const nextLow = String(Number(candle.low).toFixed(2));
        setRangeLow(nextLow);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low: nextLow } }));
        mergeRangeWindowTime(candle.time);
      }

      setSessionEventIds(prev => {
        const next = new Set(prev);
        next.add(eventId);
        return next;
      });
      setMessage(`Saved SET_ANCHOR ${side} at ${Number(price).toFixed(2)} · ${shortTime(candle.time, timeframe)}`);
    } catch (err: any) {
      setMessage(`Raw marker save failed: ${err?.message || err}`);
      throw err;
    } finally {
      setRawMarkSaving(false);
    }
  };

  const parentStructureLayer = useMemo(() => (
    rangeScope === 'MINOR' ? structureLayer : expectedParentStructureLayer(structureLayer)
  ), [structureLayer, rangeScope]);

  const macroRangesInCase = useMemo(() => {
    return safeArray<StructuralRange>(savedStructuralRanges).filter((r:any) =>
      normalizeStructureLayer(r.structure_layer || r.layer) === 'MACRO' && isRangeMajor(r),
    );
  }, [savedStructuralRanges]);

  const parentCandidatesForScope = useMemo(() => {
    return parentLayerCandidates(structureLayer, savedStructuralRanges, rangeScope);
  }, [structureLayer, rangeScope, savedStructuralRanges]);

  const structuralPricesMatch = (a: number, b: number) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 0.005;

  const hydrateStructuralAnchorsFromRange = (range: any, opts?: { force?: boolean; markDraft?: boolean }) => {
    if (!range) return;
    const high = range.range_high_price ?? range.range_high;
    const low = range.range_low_price ?? range.range_low;
    const nextRh = { price: String(high ?? ''), time: String(range.range_high_time || ''), candle: null as Candle | null };
    const nextRl = { price: String(low ?? ''), time: String(range.range_low_time || ''), candle: null as Candle | null };
    const layer = normalizeStructureLayer(range.structure_layer || range.layer);
    const shouldReplaceRh = opts?.force || !rhAnchorRef.current.price || structuralPricesMatch(parseNum(rhAnchorRef.current.price), parseNum(high));
    const shouldReplaceRl = opts?.force || !rlAnchorRef.current.price || structuralPricesMatch(parseNum(rlAnchorRef.current.price), parseNum(low));
    if (high !== undefined && high !== null && high !== '' && shouldReplaceRh) {
      rhAnchorRef.current = nextRh;
      setRhAnchor(nextRh);
      setRangeHigh(String(high));
    }
    if (low !== undefined && low !== null && low !== '' && shouldReplaceRl) {
      rlAnchorRef.current = nextRl;
      setRlAnchor(nextRl);
      setRangeLow(String(low));
    }
    if (layer && (nextRh.price || nextRl.price)) {
      setStructuralAnchorsByLayer(prev => ({
        ...prev,
        [layer]: { rh: nextRh, rl: nextRl },
      }));
    }
    setRangeWindowByTf(prev => ({
      ...prev,
      [timeframe]: {
        ...(prev[timeframe] || {}),
        start: range.range_start_time || range.range_high_time || prev[timeframe]?.start || '',
        end: range.range_end_time || range.range_low_time || prev[timeframe]?.end || '',
      },
    }));
    if (opts?.markDraft === true) setStructuralRangeDraftDirty(true);
    else if (opts?.markDraft === false) setStructuralRangeDraftDirty(false);
  };

  const resolveActiveRangeIdForAnchors = () => {
    const isBrokenRange = (r: any) => String(r?.status || '').toUpperCase() === 'BROKEN';
    const layerRows = safeArray<any>(savedStructuralRanges).filter(
      (r:any) => normalizeStructureLayer(r.structure_layer || r.layer) === structureLayer,
    );
    const rowById = (id: string) => layerRows.find((r:any) => String(r.range_id || r.id) === String(id));
    if (activeStructuralRangeId) {
      const activeRow = rowById(activeStructuralRangeId);
      if (activeRow && !isBrokenRange(activeRow)) return String(activeStructuralRangeId);
    }
    const rh = parseNum(rhAnchorRef.current.price);
    const rl = parseNum(rlAnchorRef.current.price);
    if (Number.isFinite(rh) && Number.isFinite(rl)) {
      const match = layerRows.find((r:any) => {
        if (isBrokenRange(r)) return false;
        const hi = parseNum(r.range_high_price ?? r.range_high);
        const lo = parseNum(r.range_low_price ?? r.range_low);
        return structuralPricesMatch(hi, rh) && structuralPricesMatch(lo, rl);
      });
      if (match) return String(match.range_id || match.id || '');
    }
    const latestActive = layerRows.filter((r:any) => !isBrokenRange(r)).sort(compareRangesByStartDate).slice(-1)[0];
    return latestActive ? String(latestActive.range_id || latestActive.id || '') : '';
  };

  const drillToChildMapping = async (parentRange: any, opts?: { clearDraft?: boolean }): Promise<boolean> => {
    const parentId = String(parentRange?.range_id || parentRange?.id || '');
    const parentLayer = normalizeStructureLayer(parentRange?.structure_layer || parentRange?.layer);
    const childLayer = parentLayer ? expectedChildStructureLayer(parentLayer) : null;
    if (!parentId || !parentLayer || !childLayer) {
      setMessage('No child mapping layer below this range.');
      return false;
    }
    const childSourceTf = defaultSourceTimeframeForStructureLayer(childLayer);
    structureLayerRef.current = childLayer;
    sourceTimeframeRef.current = childSourceTf;
    selectedParentRangeIdRef.current = parentId;
    activeStructuralRangeIdRef.current = '';
    setStructureLayer(childLayer);
    setSourceTimeframe(childSourceTf);
    setSelectedParentRangeId(parentId);
    setActiveStructuralRangeId('');
    if (opts?.clearDraft !== false) {
      clearStructuralRangeDraft();
    }
    setChainDraftMode(false);
    const childChartTf = defaultChartTimeframeForStructureLayer(childLayer);
    await switchTimeframePreserveCase(childChartTf);
    if (!assertCandleFeedReady('Drill to child')) return false;
    setMessage(`Drill to ${childLayer} under ${parentLayer} #${parentId} — plot child RH/RL on ${childChartTf}.`);
    return true;
  };

  const closeGuidedChildMapping = () => {
    setChildMappingSession(null);
    setGuidedCursor(null);
    lastGuidedChildSaveRef.current = null;
  };

  const applyGuidedCursorAdvance = (next: GuidedMappingCursor) => {
    setGuidedCursor(next);
    setChildMappingSession((prev) => {
      if (!prev) return prev;
      const win = guidedCursorResearchWindow(next);
      return {
        ...prev,
        researchWindow: {
          start: win.start,
          end: win.end,
          dateFrom: win.dateFrom,
          dateTo: win.dateTo,
        },
        phase: 'scanning',
        candidates: [],
        candidateIndex: 0,
        detectionRunId: null,
      };
    });
    if (next.cursor_time_ms) {
      setCandleReplayFrameByTime(new Date(next.cursor_time_ms).toISOString());
    }
  };

  const startGuidedChildMapping = async (
    parentRange: Record<string, unknown>,
    opts?: { coverage?: MappingGap['coverage'] },
  ): Promise<boolean> => {
    skipSavedReplayHydrateRef.current = true;
    const parentId = String(parentRange?.range_id || parentRange?.id || '').trim();
    if (!parentId) {
      setMessage('Cannot start guided mapping — parent range id missing.');
      return false;
    }
    const gapStartMs = opts?.coverage?.first_gap_start_ms ?? null;
    const gapEndMs = opts?.coverage?.first_gap_end_ms ?? null;
    const cursor = buildGuidedCursorFromParent(
      parentRange,
      explorerYearFilter,
      gapStartMs,
      gapEndMs,
    );
    const setup = openChildMappingSetup(parentRange);
    if (!setup) {
      setMessage('No child mapping layer below this range.');
      return false;
    }
    const researchWin = guidedCursorResearchWindow(cursor);
    const session: ChildMappingSession = {
      ...setup.session,
      researchWindow: {
        start: researchWin.start,
        end: researchWin.end,
        dateFrom: researchWin.dateFrom,
        dateTo: researchWin.dateTo,
      },
      phase: 'scanning',
      candidates: [],
      candidateIndex: 0,
      detectionRunId: null,
    };
    setGuidedCursor(cursor);
    setChildMappingSession(session);
    lastGuidedChildSaveRef.current = null;
    structureLayerRef.current = session.childLayer;
    sourceTimeframeRef.current = session.childSourceTf;
    selectedParentRangeIdRef.current = parentId;
    activeStructuralRangeIdRef.current = '';
    setStructureLayer(session.childLayer);
    setRangeScope('MAJOR');
    setSourceTimeframe(session.childSourceTf);
    setSelectedParentRangeId(parentId);
    setActiveStructuralRangeId('');
    clearStructuralRangeDraft();
    setRhAnchor({ price: '', time: '', candle: null });
    setRlAnchor({ price: '', time: '', candle: null });
    setStructuralRangeDraftDirty(false);
    const childChartTf = setup.chartTimeframe;
    if (childChartTf !== String(timeframe).toUpperCase()) {
      activeTimeframeRef.current = childChartTf;
      setTimeframe(childChartTf);
    }
    jumpToStructuralRange(parentRange);
    await loadCandles(childChartTf, {
      cacheFullHistory: true,
      reason: 'guided-child-mapping',
      structuralNavigation: true,
      deferCamera: true,
    });
    if (!assertCandleFeedReady('Guided child mapping')) return false;
    setMessage(`Guided mapping: ${cursor.active_child_layer} under ${cursor.active_parent_layer} #${parentId}.`);
    return true;
  };

  const handleGuidedNextChild = () => {
    if (!guidedCursor?.active) return;
    const saved = lastGuidedChildSaveRef.current;
    if (saved?.rangeId) {
      applyGuidedCursorAdvance(advanceGuidedCursorAfterChildSave(guidedCursor, saved));
      lastGuidedChildSaveRef.current = null;
      void refreshSavedRangesForCurrentCase().catch(() => {});
      void refreshHierarchyAudit().catch(() => {});
      return;
    }
    applyGuidedCursorAdvance(skipGuidedCursorGap(guidedCursor));
  };

  const handleGuidedSkipGap = () => {
    if (!guidedCursor?.active) return;
    applyGuidedCursorAdvance(skipGuidedCursorGap(guidedCursor));
    setMessage('Skipped guided mapping gap — cursor advanced.');
  };

  const handleGuidedParentComplete = () => {
    if (!guidedCursor?.active) return;
    setGuidedCursor(markGuidedParentComplete(guidedCursor));
    setMessage('Parent marked complete for guided mapping.');
  };

  const handleChildMappingSave = async (): Promise<{
    ok: boolean;
    rangeId?: string;
    rangeEndTime?: string | null;
    bosWarning?: string | null;
  }> => {
    const ok = await saveStructuralRange();
    if (!ok) return { ok: false };
    const rangeId = String(activeStructuralRangeId || lastSavedRangeConfirmation?.range_id || '').trim();
    const rangeEndTime = rlAnchor.time || rhAnchor.time || null;
    if (rangeId) {
      lastGuidedChildSaveRef.current = { rangeId, rangeEndTime };
    }
    return { ok: true, rangeId: rangeId || undefined, rangeEndTime };
  };

  const handleApplyChildCandidate = (sample: RangeAuditSample) => {
    const target = auditSampleToViewTarget(sample);
    if (target) loadRangeAuditOnChart(target);
  };

  const handleChildManualCreate = () => {
    setRhAnchor({ price: '', time: '', candle: null });
    setRlAnchor({ price: '', time: '', candle: null });
    setActiveStructuralRangeId('');
    clearStructuralRangeDraft();
  };

  useEffect(() => {
    if (!activeStructuralRangeId) return;
    const row = safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(activeStructuralRangeId));
    if (!row) return;
    const rowLayer = normalizeStructureLayer(row.structure_layer || row.layer);
    if (rowLayer && rowLayer !== structureLayer) {
      const expectedParent = expectedParentStructureLayer(structureLayer);
      if (expectedParent && rowLayer === expectedParent && isRangeMajor(row)) {
        setSelectedParentRangeId(String(activeStructuralRangeId));
      }
      setActiveStructuralRangeId('');
      activeStructuralRangeIdRef.current = '';
      setLastSavedRangeConfirmation(null);
      return;
    }
    if (chainDraftMode) return;
    hydrateStructuralAnchorsFromRange(row, { markDraft: false });
  }, [structureLayer, activeStructuralRangeId, savedStructuralRanges, chainDraftMode, timeframe]);

  useEffect(() => {
    if (structureLayer === 'MACRO' && rangeScope === 'MAJOR') return;
    const childSpan = { range_high_time: rhAnchor.time, range_low_time: rlAnchor.time };
    const resolve = resolveParentRangeIdForSave(structureLayer, rangeScope, selectedParentRangeId, savedStructuralRanges, childSpan);
    if (resolve.autoSelected && resolve.parentId && String(resolve.parentId) !== String(selectedParentRangeId)) {
      setSelectedParentRangeId(String(resolve.parentId));
    }
  }, [structureLayer, rangeScope, rhAnchor.time, rlAnchor.time, savedStructuralRanges, selectedParentRangeId]);

  useEffect(() => {
    const allowed = sourceTimeframeOptionsForLayer(structureLayer);
    if (!allowed.includes(String(sourceTimeframe).toUpperCase())) setSourceTimeframe(defaultSourceTimeframeForStructureLayer(structureLayer));
  }, [structureLayer]);

  const structuralFetchJson = async (url:string, options?:RequestInit) => {
    const res = await fetch(url, options);
    const data = await res.json().catch(()=>({ ok:false, error:`Invalid backend response ${res.status}` }));
    if (!res.ok || data?.ok === false) throw new Error(data?.error || data?.detail || `Backend request failed ${res.status}`);
    return data;
  };

  const resolveStructuralEventRef = (data:any, payload:{ event_id?:string }) => {
    const numericId = data?.id ?? data?.event?.id;
    if (numericId !== undefined && numericId !== null && String(numericId) !== '') {
      const parsed = Number(numericId);
      if (Number.isFinite(parsed)) {
        return {
          broken_by_event_id: parsed as number,
          event_uuid: String(data?.event_id || data?.event?.event_id || payload.event_id || ''),
        };
      }
    }
    const eventUuid = String(data?.event_id || data?.event?.event_id || payload.event_id || '');
    if (!eventUuid) throw new Error('BOS saved but backend returned no event id for lifecycle patch.');
    return { broken_by_event_id: eventUuid, event_uuid: eventUuid };
  };

  const patchActiveRangeBroken = async (
    rangeId: string,
    patch: { direction_of_break:'UP'|'DOWN'; broken_by_event_id:number|string; inactive_from_time:string },
  ) => {
    return inspectorCommitOrThrow({
      baseUrl: BASE_URL,
      kind: 'structural_range_patch',
      source: 'range_lifecycle_patch',
      pathParams: { rangeId },
      payload: {
        status: 'BROKEN',
        direction_of_break: patch.direction_of_break,
        broken_by_event_id: patch.broken_by_event_id,
        inactive_from_time: patch.inactive_from_time,
      },
    });
  };

  const patchActiveRangeRestored = async (rangeId: string) => {
    return inspectorCommitOrThrow({
      baseUrl: BASE_URL,
      kind: 'structural_range_patch',
      source: 'range_lifecycle_patch',
      pathParams: { rangeId },
      payload: {
        status: 'ACTIVE',
        direction_of_break: null,
        broken_by_event_id: null,
        inactive_from_time: null,
      },
    });
  };

  const isBosBreakQuickEventRole = (role: any) => {
    const r = String(role || '').toUpperCase();
    return ['BH', 'BL', 'BREAK_UP', 'BREAK_DOWN', 'BOS_UP', 'BOS_DOWN', 'BREAK_HIGH_SELECTED', 'BREAK_LOW_SELECTED'].includes(r);
  };

  const findSavedRangeRowById = (rangeId: string) => {
    return safeArray<any>([...savedStructuralRanges, ...structuralRanges]).find(
      (r:any) => String(r.range_id || r.id) === String(rangeId),
    ) || null;
  };

  const rangeHasKnownChainLinks = (range: any) => {
    if (!range) return null;
    return !!(range.old_range_id || range.new_range_id || range.created_by_event_id);
  };

  const isStructuralRangeBrokenStatus = (status: any) => String(status || '').toUpperCase() === 'BROKEN';

  const findBreakEventForBrokenRange = (rangeId: string) => {
    const id = String(rangeId);
    if (
      lastSavedQuickEvent?.range_lifecycle_patched &&
      String(lastSavedQuickEvent.broken_range_id) === id &&
      isBosBreakQuickEventRole(lastSavedQuickEvent.role)
    ) {
      return lastSavedQuickEvent;
    }
    for (let i = quickEventHistory.length - 1; i >= 0; i--) {
      const ev = quickEventHistory[i];
      if (isBosBreakQuickEventRole(ev?.role) && ev?.range_lifecycle_patched && String(ev.broken_range_id) === id) {
        return ev;
      }
    }
    return null;
  };

  const resolveCreatedByEventIdForChain = (brokenRange: any, breakEvent: any) => {
    const fromRange = brokenRange?.broken_by_event_id;
    if (fromRange !== null && fromRange !== undefined && String(fromRange) !== '') {
      const parsed = Number(fromRange);
      return Number.isFinite(parsed) ? parsed : fromRange;
    }
    const dbId = breakEvent?.db_id;
    if (dbId !== null && dbId !== undefined && String(dbId) !== '') {
      const parsed = Number(dbId);
      return Number.isFinite(parsed) ? parsed : dbId;
    }
    return breakEvent?.event_id || null;
  };

  const resolveParentRangeIdForNextRange = (brokenRange: any) => {
    const brokenParentId = brokenRange?.parent_range_id ?? null;
    const brokenParentStr = brokenParentId !== null && brokenParentId !== undefined && String(brokenParentId) !== ''
      ? String(brokenParentId)
      : '';
    const selectedStr = String(selectedParentRangeId || '');
    const explicitChange = !!selectedStr && selectedStr !== brokenParentStr;
    if (explicitChange) return parentRangeIdForStructureLayer(structureLayer, rangeScope, selectedParentRangeId);
    if (brokenParentStr) return brokenParentId;
    return parentRangeIdForStructureLayer(structureLayer, rangeScope, selectedParentRangeId);
  };

  const clearStructuralRangeDraft = () => {
    setRhAnchor({ price:'', time:'', candle:null });
    setRlAnchor({ price:'', time:'', candle:null });
    setRangeHigh('');
    setRangeLow('');
    setRangeByTf((prev:any) => ({ ...prev, [timeframe]: { high:'', low:'' } }));
    setRangeWindowByTf((prev:any) => ({ ...prev, [timeframe]: { start:'', end:'' } }));
    setStructuralRangeDraftDirty(false);
    autoRangeSaveAttemptRef.current = '';
  };

  const clearMappingDraftSelection = () => {
    clearStructuralRangeDraft();
    setBhAnchor({ price:'', time:'', candle:null });
    setBlAnchor({ price:'', time:'', candle:null });
    setStructuralBosDraftDirty(false);
    setSelectedCandle(null);
    setSelectedCandlePoint(null);
    setPendingMarkerRoles([]);
    setMessage('Draft cleared · click a candle to continue');
  };

  const patchOldRangeNewRangeId = async (oldRangeId: string, newRangeId: string) => {
    return inspectorCommitOrThrow({
      baseUrl: BASE_URL,
      kind: 'structural_range_patch',
      source: 'range_chain_link',
      pathParams: { rangeId: oldRangeId },
      payload: { new_range_id: Number(newRangeId) },
    });
  };

  const enterChainDraftAfterBos = (
    rangeId: string,
    activeRange: any,
    bosType: string,
  ) => {
    clearStructuralRangeDraft();
    setChainDraftMode(true);
    setBosNextRangePrompt(null);
    if (activeRange && isRangeMajor(activeRange)) {
      setSelectedParentRangeId(String(rangeId));
    }
    autoChainSaveAttemptRef.current = '';
    if (activeRange && isRangeMajor(activeRange)) {
      setRangeScope('MAJOR');
    } else if (activeRange) {
      setRangeScope('MINOR');
    }
    const scopeHint = activeRange && isRangeMajor(activeRange) ? 'MAJOR' : 'MINOR';
    setMessage(`BOS saved · ${structureLayer} #${rangeId} broken · waiting for next RH/RL (${scopeHint})`);
  };

  const applyBosNextRangePromptAfterSave = async (
    rangeId: string,
    activeRange: any,
    bosType: string,
    bosEventId: string | number | null | undefined,
  ) => {
    let refreshed = savedStructuralRanges;
    try {
      refreshed = await refreshSavedRangesForCurrentCase();
    } catch {
      /* use local snapshot */
    }
    const patchedBroken = findSavedRangeRowById(String(rangeId))
      || refreshed.find((r: any) => String(r.range_id || r.id) === String(rangeId))
      || activeRange;
    const promptResult = evaluateBosNextRangePrompt({
      brokenRange: {
        ...(patchedBroken || {}),
        range_id: rangeId,
        id: rangeId,
        status: 'BROKEN',
        broken_by_event_id: patchedBroken?.broken_by_event_id ?? bosEventId ?? null,
      },
      ranges: refreshed,
      bosEventId: patchedBroken?.broken_by_event_id ?? bosEventId ?? null,
    });
    const promptKey = bosNextRangePromptKey(promptResult);
    if (promptResult.status === 'ALREADY_EXISTS') {
      setBosNextRangePrompt(null);
      setChainDraftMode(false);
      setMessage(`BOS saved. ${promptResult.message}`);
      return;
    }
    if (promptResult.status === 'UNCERTAIN') {
      setBosNextRangePrompt(null);
      setChainDraftMode(false);
      setMessage(`BOS saved. ${promptResult.message}`);
      return;
    }
    if (promptResult.status === 'PROMPT') {
      setBosNextRangePrompt(null);
      enterChainDraftAfterBos(rangeId, activeRange, bosType);
      return;
    }
    enterChainDraftAfterBos(rangeId, activeRange, bosType);
  };

  const acceptBosNextRangePrompt = () => {
    if (!bosNextRangePrompt) return;
    bosPromptHandledKeysRef.current.add(bosNextRangePromptKey(bosNextRangePrompt));
    const brokenId = String(bosNextRangePrompt.brokenRangeId || activeStructuralRangeId || '');
    const brokenRange = findSavedRangeRowById(brokenId);
    setBosNextRangePrompt(null);
    enterChainDraftAfterBos(brokenId, brokenRange, 'BOS');
  };

  const dismissBosNextRangePrompt = () => {
    if (!bosNextRangePrompt) return;
    bosPromptHandledKeysRef.current.add(bosNextRangePromptKey(bosNextRangePrompt));
    setBosNextRangePrompt(null);
    setChainDraftMode(false);
    setMessage('Next-range mapping deferred.');
  };

  const selectedSavedRange = useMemo(() => {
    if (!activeStructuralRangeId) return null;
    return safeArray<StructuralRange>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(activeStructuralRangeId)) || null;
  }, [savedStructuralRanges, activeStructuralRangeId]);

  const tradingViewHierarchyFitRange = useMemo(() => {
    if (selectedSavedRange) return selectedSavedRange;
    if (!selectedParentRangeId) return null;
    return safeArray<StructuralRange>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(selectedParentRangeId)) || null;
  }, [savedStructuralRanges, selectedParentRangeId, selectedSavedRange]);

  useEffect(() => {
    if (chartRenderer !== 'tradingview' || !tradingViewHierarchyFitRange) return;
    if (tradingViewMappingInputEnabled) return;
    const rangeId = String((tradingViewHierarchyFitRange as any).range_id || (tradingViewHierarchyFitRange as any).id || '');
    if (!rangeId) return;
    if (tradingViewSuppressedHierarchyRangeIdRef.current === rangeId) return;
    const targetTf = String(resolveRangeChartTimeframe(tradingViewHierarchyFitRange, timeframe)).toUpperCase();
    const fitWindow = structuralRangeFitDomain(tradingViewHierarchyFitRange, [], targetTf);
    if (!fitWindow?.start || !fitWindow?.end) return;
    const targetTime = structuralContextTargetTime(tradingViewHierarchyFitRange) || fitWindow.start;
    const fitKey = `${rangeId}:${targetTf}:${fitWindow.start}:${fitWindow.end}`;
    if (tradingViewHierarchyFitKeyRef.current === fitKey) return;
    tradingViewHierarchyFitKeyRef.current = fitKey;
    setTradingViewHierarchyFitCommand((prev) => ({
      intent: 'FIT_STRUCTURAL_RANGE',
      token: (prev?.token || 0) + 1,
      targetTime,
      reason: 'tradingview-hierarchy-range-fit',
      fitWindow,
    }));
    if (targetTf !== String(timeframe).toUpperCase()) {
      skipBootstrapOnceRef.current = true;
      activeTimeframeRef.current = targetTf;
      setTimeframe(targetTf);
      void loadCandles(targetTf, {
        cacheFullHistory: true,
        timeframeSwitch: true,
        reason: 'tradingview-hierarchy-range-fit',
        navigationPath: 'tradingview-hierarchy-range-fit',
        deferCamera: true,
      });
    }
  }, [chartRenderer, timeframe, tradingViewHierarchyFitRange, tradingViewMappingInputEnabled]);

  const effectiveStructuralAnchors = useMemo(
    () => {
      const tvAnchorTimesOnly = chartRenderer === 'tradingview' && tradingViewMappingInputEnabled;
      return resolveEffectiveStructuralAnchorTimes(
        rhAnchor,
        rlAnchor,
        tvAnchorTimesOnly ? null : (rangeWindowByTf[timeframe] || rangeWindow),
        tvAnchorTimesOnly ? null : (selectedCandle?.time || replayCandle?.time || null),
      );
    },
    [chartRenderer, tradingViewMappingInputEnabled, rhAnchor, rlAnchor, rangeWindowByTf, timeframe, rangeWindow, selectedCandle?.time, replayCandle?.time],
  );

  const childDraftSpan = useMemo(() => ({
    range_high_time: effectiveStructuralAnchors.range_high_time,
    range_low_time: effectiveStructuralAnchors.range_low_time,
  }), [effectiveStructuralAnchors.range_high_time, effectiveStructuralAnchors.range_low_time]);

  const resolveParentSelectionForSave = () => {
    const neededParentLayer = rangeScope === 'MINOR' ? structureLayer : expectedParentStructureLayer(structureLayer);
    if (!neededParentLayer) return selectedParentRangeId || '';
    const parentRowMatches = (row: any) => {
      const rowLayer = normalizeStructureLayer(row.structure_layer || row.layer);
      if (rangeScope === 'MINOR') return rowLayer === structureLayer && isRangeMajor(row);
      return rowLayer === neededParentLayer && isRangeMajor(row);
    };
    if (selectedParentRangeId) {
      const selectedRow = safeArray<any>(savedStructuralRanges).find(
        (r:any) => String(r.range_id || r.id) === String(selectedParentRangeId),
      );
      if (selectedRow && parentRowMatches(selectedRow)) return String(selectedParentRangeId);
    }
    if (activeStructuralRangeId) {
      const activeRow = findSavedRangeRowById(activeStructuralRangeId);
      if (activeRow && parentRowMatches(activeRow)) return String(activeStructuralRangeId);
    }
    if (chainDraftMode && activeStructuralRangeId) {
      const brokenRow = findSavedRangeRowById(activeStructuralRangeId);
      if (brokenRow && parentRowMatches(brokenRow)) return String(activeStructuralRangeId);
    }
    return selectedParentRangeId || '';
  };

  const resolveParentIdForStructuralSave = () => {
    const resolved = resolveParentRangeIdForSave(
      structureLayer,
      rangeScope,
      parentSelectionForSave,
      savedStructuralRanges,
      childDraftSpan,
    );
    if (resolved.parentId) return resolved;
    const neededParentLayer = rangeScope === 'MINOR' ? structureLayer : expectedParentStructureLayer(structureLayer);
    if (!neededParentLayer) return resolved;
    const manualParentId = selectedParentRangeId || parentSelectionForSave;
    if (!manualParentId) return resolved;
    const parentRow = safeArray<any>(savedStructuralRanges).find(
      (r:any) => String(r.range_id || r.id) === String(manualParentId),
    );
    if (!parentRow) return resolved;
    const parentLayer = normalizeStructureLayer(parentRow.structure_layer || parentRow.layer);
    const layerOk = rangeScope === 'MINOR'
      ? parentLayer === structureLayer && isRangeMajor(parentRow)
      : parentLayer === neededParentLayer && isRangeMajor(parentRow);
    if (!layerOk) return resolved;
    return {
      ...resolved,
      parentId: String(manualParentId),
      autoSelected: false,
      mode: 'manual' as const,
      matchIds: [String(manualParentId)],
      error: null,
      orphanWarning: null,
    };
  };

  const parentSelectionForSave = useMemo(
    () => resolveParentSelectionForSave(),
    [structureLayer, rangeScope, selectedParentRangeId, activeStructuralRangeId, savedStructuralRanges, chainDraftMode],
  );

  const parentLinkResolve = useMemo(
    () => resolveParentIdForStructuralSave(),
    [structureLayer, rangeScope, parentSelectionForSave, savedStructuralRanges, childDraftSpan, selectedParentRangeId, chainDraftMode, activeStructuralRangeId],
  );

  const resolvedParentRange = useMemo(() => {
    const pid = parentLinkResolve.parentId;
    if (!pid) return null;
    return safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(pid)) || null;
  }, [parentLinkResolve.parentId, savedStructuralRanges]);

  const parentLinkContextLabel = useMemo(() => {
    if (structureLayer === 'MACRO' && rangeScope === 'MAJOR') return null;
    const mode = parentLinkModeLabel(parentLinkResolve.mode);
    if (!resolvedParentRange) {
      const expectedParent = parentStructureLayer;
      const rootOk = isRootStructuralLayer(structureLayer, rangeScope);
      const orphanHint = rootOk && expectedParent
        ? `${structureLayer} root · optional ${expectedParent} parent not in case`
        : (parentLinkResolve.orphanWarning || mode);
      return {
        mappingLine: `Mapping: ${structureLayer} ${rangeScope} | Source: ${sourceTimeframe} | Chart: ${timeframe}`,
        parentLine: `Parent: none · ${orphanHint}`,
        mode,
      };
    }
    return {
      mappingLine: `Mapping: ${structureLayer} ${rangeScope} | Source: ${sourceTimeframe} | Chart: ${timeframe}`,
      parentLine: `Parent: ${formatStructuralRangeOptionLabel(resolvedParentRange)}`,
      mode,
    };
  }, [structureLayer, rangeScope, sourceTimeframe, timeframe, parentLinkResolve, resolvedParentRange]);

  const savePreview = useMemo(() => {
    const mappingCase = getCurrentMappingCaseRef();
    const parentResolve = resolveParentIdForStructuralSave();
    const parentId = parentResolve.parentId;
    const macroW1ValidNote = structureLayer === 'MACRO' && String(sourceTimeframe).toUpperCase() === 'W1' && String(timeframe).toUpperCase() === 'W1'
      ? 'Macro structural layer from W1 source — valid. Saves as MACRO / W1 with chart_timeframe W1.'
      : structureLayer === 'MACRO' && String(sourceTimeframe).toUpperCase() === 'W1'
        ? `Macro layer from W1 source — valid. chart_timeframe will record as ${timeframe}.`
        : '';
    const activeRangeLayer = selectedSavedRange
      ? normalizeStructureLayer(selectedSavedRange.structure_layer || selectedSavedRange.layer)
      : null;
    const isLayerMatchedUpdate = !!(activeStructuralRangeId && activeRangeLayer === structureLayer);
    const selectedIsBroken = !!(isLayerMatchedUpdate && selectedSavedRange && isStructuralRangeBrokenStatus(selectedSavedRange.status));
    const actionLabel = isLayerMatchedUpdate
      ? (selectedIsBroken ? 'Update Broken Range' : 'Update Selected Range')
      : 'Save New Range';
    return {
      chart_timeframe: timeframe,
      structure_layer: structureLayer,
      source_timeframe: sourceTimeframe,
      source_timeframe_note: structureLayer === 'MACRO' && String(sourceTimeframe).toUpperCase() === 'W1'
        ? 'Macro layer · W1 structural source'
        : 'structural truth',
      preview_note: macroW1ValidNote,
      case_ref: mappingCase.case_ref,
      raw_case_id: mappingCase.raw_case_id,
      case_id: mappingCase.case_id,
      hasCase: mappingCase.hasCase,
      parent_range_id: parentId,
      parent_layer: parentStructureLayer,
      parent_link_mode: parentResolve.mode,
      range_high_price: rhAnchor.price || null,
      range_high_time: rhAnchor.time || null,
      range_low_price: rlAnchor.price || null,
      range_low_time: rlAnchor.time || null,
      action: isLayerMatchedUpdate ? 'UPDATE_SELECTED_RANGE' : 'SAVE_NEW_RANGE',
      actionLabel,
      selectedIsBroken,
    };
  }, [timeframe, structureLayer, sourceTimeframe, activeCaseId, rawActiveCaseId, activeCaseLabel, parentSelectionForSave, rhAnchor.price, rhAnchor.time, rlAnchor.price, rlAnchor.time, activeStructuralRangeId, savedStructuralRanges, parentStructureLayer, selectedSavedRange, childDraftSpan]);

  const saveBlockReason = useMemo(() => {
    if (!getCurrentMappingCaseRef().hasCase) return 'Create or select a mapping case first (Case tab).';
    const hasRh = !!String(rhAnchor.price || '').trim();
    const hasRl = !!String(rlAnchor.price || '').trim();
    if (chainDraftMode) {
      if (!hasRh && !hasRl) return 'Range is BROKEN — set RH/RL for the next range, then Save Next.';
      if (!hasRh) return 'Set Range High for the next range (Sel → candle → RH).';
      if (!hasRl) return 'Set Range Low for the next range (Sel → candle → RL).';
    } else {
      if (!hasRh && !hasRl) return 'Set Range High and Range Low first.';
      if (!hasRh) return 'RL is set — select a candle and click RH for Range High.';
      if (!hasRl) return 'RH is set — select a candle and click RL for Range Low.';
    }
    const draftHigh = parseNum(rhAnchor.price);
    const draftLow = parseNum(rlAnchor.price);
    if (Number.isFinite(draftHigh) && Number.isFinite(draftLow) && draftHigh <= draftLow) {
      return 'Range High must be above Range Low.';
    }
    if (parentLinkResolve.error) return `${parentLinkResolve.error} (Save will continue as orphan.)`;
    if (parentLinkResolve.orphanWarning) return parentLinkResolve.orphanWarning;
    return null;
  }, [rhAnchor.price, rlAnchor.price, activeCaseId, rawActiveCaseId, chainDraftMode, parentLinkResolve.error, parentLinkResolve.orphanWarning]);

  const hasStructuralAnchorPrice = (anchor: StructuralAnchor) => !!String(anchor.price || '').trim();

  const mappingSkeletonContextReady = useMemo(() => hasMappingSkeletonContext({
    hasCase: getCurrentMappingCaseRef().hasCase,
    activeStructuralRangeId: String(activeStructuralRangeId || ''),
    selectedParentRangeId: String(selectedParentRangeId || ''),
    guidedCursorActive: !!guidedCursor?.active,
    childMappingSessionActive: !!childMappingSession,
  }), [activeCaseId, rawActiveCaseId, activeStructuralRangeId, selectedParentRangeId, guidedCursor?.active, childMappingSession]);

  const mappingRhRlDraftBlockMessage = useMemo(() => {
    if (parentLinkResolve.error) return parentLinkResolve.error;
    return 'Select campaign or hierarchy context first.';
  }, [parentLinkResolve.error]);

  const orphanRangeDraftAllowed = useMemo(() => {
    if (!getCurrentMappingCaseRef().hasCase) return false;
    if (parentLinkResolve.error) return false;
    if (isRootStructuralLayer(structureLayer, rangeScope)) return true;
    if (parentLinkResolve.mode === 'none' || parentLinkResolve.mode === 'no_match') return true;
    return false;
  }, [structureLayer, rangeScope, parentLinkResolve.error, parentLinkResolve.mode, activeCaseId, rawActiveCaseId]);

  const canSetRhRlStructuralDraft = mappingSkeletonContextReady || orphanRangeDraftAllowed;

  const rangeDraftSynced = useMemo(() => {
    if (!activeStructuralRangeId || structuralRangeDraftDirty) return false;
    const row = selectedSavedRange;
    if (!row) return false;
    const hi = parseNum(row.range_high_price ?? row.range_high);
    const lo = parseNum(row.range_low_price ?? row.range_low);
    const drh = parseNum(rhAnchor.price);
    const drl = parseNum(rlAnchor.price);
    return Number.isFinite(hi) && Number.isFinite(lo) && Number.isFinite(drh) && Number.isFinite(drl)
      && Math.abs(hi - drh) < 0.005 && Math.abs(lo - drl) < 0.005;
  }, [activeStructuralRangeId, selectedSavedRange, rhAnchor.price, rlAnchor.price, structuralRangeDraftDirty]);

  const chartStatusLine = useMemo(() => {
    const targetBars = targetVisibleBarsForTimeframe(timeframe);
    const zoomHint = visibleBarCount > targetBars * 1.35
      ? ` · ${visibleBarCount} bars visible (try Fit or W+)`
      : visibleBarCount > 0
        ? ` · ${visibleBarCount} bars`
        : '';
    const feedLine = buildCandleFeedStatusLine({
      structureLayer,
      sourceTimeframe,
      chartTimeframe: timeframe,
      loaded: loadedCandleContext,
      loading: candleFeedLoading,
      candleCount: candles.length,
    });
    const libraryLine = buildLocalLibraryStatusLine(localLibraryDebug);
    const skeletonLine = buildSkeletonMappingStatusLine({
      selectedTimeLabel: selectedCandle ? shortTime(selectedCandle.time, timeframe) : null,
      timeframe,
      structureLayer,
      activeRangeId: String(activeStructuralRangeId || ''),
      parentRangeId: String(selectedParentRangeId || savePreview.parent_range_id || ''),
      rhSet: hasStructuralAnchorPrice(rhAnchor),
      rlSet: hasStructuralAnchorPrice(rlAnchor),
      chainDraftMode,
      rangeSynced: rangeDraftSynced,
      lastMessage: message,
      structuralSaving,
    });
    return `${feedLine} · ${libraryLine} · ${skeletonLine}${zoomHint}`;
  }, [
    selectedCandle,
    timeframe,
    message,
    visibleBarCount,
    structureLayer,
    sourceTimeframe,
    loadedCandleContext,
    localLibraryDebug,
    candleFeedLoading,
    candles.length,
    activeStructuralRangeId,
    selectedParentRangeId,
    savePreview.parent_range_id,
    rhAnchor.price,
    rlAnchor.price,
    chainDraftMode,
    rangeDraftSynced,
    structuralSaving,
  ]);

  const saveNextRangeEligible = useMemo(() => {
    if (!activeStructuralRangeId) {
      return { eligible:false, reason:'Select the broken range as active first.', oldRangeId:null as string|null, parentRangeId:null as string|number|null, createdByEventId:null as string|number|null };
    }
    const brokenRange = selectedSavedRange || findSavedRangeRowById(activeStructuralRangeId);
    const brokenLayer = brokenRange ? normalizeStructureLayer(brokenRange.structure_layer || brokenRange.layer) : null;
    if (brokenLayer && brokenLayer !== structureLayer) {
      return {
        eligible:false,
        reason:`Save Next Range chains the same layer. To map ${structureLayer} inside ${brokenLayer}, select ${brokenLayer} parent and use Save Range.`,
        oldRangeId:String(activeStructuralRangeId),
        parentRangeId:null,
        createdByEventId:null,
      };
    }
    const statusBroken = brokenRange && isStructuralRangeBrokenStatus(brokenRange.status);
    if (!statusBroken) {
      return { eligible:false, reason:'Active range must be BROKEN before Save Next Range.', oldRangeId:String(activeStructuralRangeId), parentRangeId:null, createdByEventId:null };
    }
    if (brokenRange?.new_range_id) {
      return { eligible:false, reason:`Range #${activeStructuralRangeId} already chained to #${brokenRange.new_range_id}.`, oldRangeId:String(activeStructuralRangeId), parentRangeId:null, createdByEventId:null };
    }
    if (!rhAnchor.price || !rlAnchor.price) {
      return { eligible:false, reason:'Set new RH and RL after retrace before Save Next Range.', oldRangeId:String(activeStructuralRangeId), parentRangeId:null, createdByEventId:null };
    }
    const breakEvent = findBreakEventForBrokenRange(activeStructuralRangeId);
    const createdByEventId = resolveCreatedByEventIdForChain(brokenRange, breakEvent);
    if (!createdByEventId) {
      return { eligible:false, reason:'BOS event reference missing for chain. Break the range again or refresh audit.', oldRangeId:String(activeStructuralRangeId), parentRangeId:null, createdByEventId:null };
    }
    const inheritedParent = brokenRange?.parent_range_id ?? null;
    return {
      eligible:true,
      reason:'',
      oldRangeId:String(activeStructuralRangeId),
      parentRangeId: inheritedParent !== null && inheritedParent !== undefined && String(inheritedParent) !== '' ? inheritedParent : null,
      createdByEventId,
      brokenRange,
      breakEvent,
    };
  }, [activeStructuralRangeId, selectedSavedRange, savedStructuralRanges, structuralRanges, lastSavedQuickEvent, quickEventHistory, rhAnchor.price, rlAnchor.price, structureLayer]);

  const refreshSavedRangesForCurrentCase = async () => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setSavedStructuralRanges([]);
      return [] as StructuralRange[];
    }
    const params = appendMappingCaseParams(new URLSearchParams({ symbol, limit:'5000' }), mappingCase);
    const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/ranges?${params.toString()}`);
    const rows = visibleStructuralRanges(safeArray<StructuralRange>(data.ranges));
    setSavedStructuralRanges(rows);
    return rows;
  };

  const refreshStructuralMapEventsForChart = async (requestedTf = timeframe) => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) return;
    const params = appendMappingCaseParams(
      new URLSearchParams({ symbol, timeframe: requestedTf, limit: '2000' }),
      mappingCase,
    );
    try {
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/events?${params.toString()}`);
      const structural = safeArray<any>(data.events)
        .map((row:any) => mapStructuralEventRowToChartEvent(row))
        .filter(Boolean) as MapEvent[];
      if (!structural.length) return;
      setEventsByTf(prev => ({
        ...prev,
        [requestedTf]: mergeChartEventsById(safeArray(prev[requestedTf]), structural),
      }));
    } catch {
      // Chart refresh must not block mapping saves.
    }
  };

  const autoResume = useAutoResume({
    symbol,
    timeframe,
    deferInitialResume: deferAutoResumeForMappingSessionRef.current === true,
    onSymbolChange,
    onTimeframeChange: (tf) => {
      activeTimeframeRef.current = tf;
      setTimeframe(tf);
    },
    onResume: async (session) => {
      skipBootstrapOnceRef.current = true;
      setMessage(`Resuming ${session.symbol} · ${session.timeframe}…`);
      if (getCurrentMappingCaseRef().hasCase) {
        try { await refreshSavedRangesForCurrentCase(); } catch {}
        try { await refreshStructuralMapEventsForChart(session.timeframe); } catch {}
      }
      await loadCandles(session.timeframe, (() => {
        const tf = String(session.timeframe).toUpperCase();
        const loadWindow = resolveCandleLoadWindow(
          tf,
          savedStructuralRanges,
          selectedParentRangeId,
          activeStructuralRangeId,
          rangeWindowByTf[tf] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
        );
        return { loadWindow, cacheFullHistory: !shouldUseWindowedCandleLoad(loadWindow) };
      })());
    },
  });

  const selectSavedStructuralRange = (range:any, opts?: { routeInspector?: boolean }) => {
    const id = String(range?.range_id || range?.id || '');
    if (!id) return;
    skipSavedReplayHydrateRef.current = true;
    activeStructuralRangeIdRef.current = id;
    setActiveStructuralRangeId(id);
    const nextLayer = normalizeStructureLayer(range.structure_layer || range.layer) || structureLayer;
    setStructureLayer(nextLayer);
    setRangeScope(normalizeRangeScope(range.range_scope));
    if (range.source_timeframe || range.timeframe) setSourceTimeframe(String(range.source_timeframe || range.timeframe).toUpperCase());
    if (range.parent_range_id !== undefined && range.parent_range_id !== null) setSelectedParentRangeId(String(range.parent_range_id));
    const high = range.range_high_price ?? range.range_high;
    const low = range.range_low_price ?? range.range_low;
    const broken = isStructuralRangeBrokenStatus(range.status);
    if (broken) {
      const promptResult = evaluateBosNextRangePrompt({
        brokenRange: range,
        ranges: savedStructuralRanges,
        bosEventId: range.broken_by_event_id,
      });
      const promptKey = bosNextRangePromptKey(promptResult);
      if (promptResult.status === 'ALREADY_EXISTS') {
        setChainDraftMode(false);
        setBosNextRangePrompt(null);
        setMessage(`Selected BROKEN range #${id}. ${promptResult.message}`);
      } else if (promptResult.status === 'UNCERTAIN') {
        setChainDraftMode(false);
        setBosNextRangePrompt(null);
        setMessage(`Selected BROKEN range #${id}. ${promptResult.message}`);
      } else if (promptResult.status === 'PROMPT' && !bosPromptHandledKeysRef.current.has(promptKey)) {
        setChainDraftMode(false);
        clearStructuralRangeDraft();
        setBosNextRangePrompt(promptResult);
        setMessage(`Selected BROKEN range #${id}. ${promptResult.promptMessage}`);
      } else {
        setChainDraftMode(true);
        clearStructuralRangeDraft();
        setMessage(`Selected BROKEN range #${id}. Set RH/RL for the next ${nextLayer} range, then Save Next.`);
      }
    } else {
      setChainDraftMode(false);
      setBosNextRangePrompt(null);
      hydrateStructuralAnchorsFromRange(range, { force: true, markDraft: false });
    }
    setRangeLineHiddenByCase(prev => {
      const key = activeCaseDisplayId || 'global';
      const current = new Set(prev[key] || []);
      current.delete(id);
      return { ...prev, [key]: Array.from(current) };
    });
    const hint = buildRangeSelectionHint({
      rangeId: id,
      structureLayer: nextLayer,
      rangeScope: normalizeRangeScope(range.range_scope),
      rangeHigh: high,
      rangeLow: low,
    });
    if (opts?.routeInspector === false) {
      setInspectorContextHint(hint);
    } else {
      applyInspectorRoute(routeInspectorForRangeSelection(), hint);
    }
    setMessage(broken
      ? `Selected BROKEN range #${id}. Set RH/RL for the next ${nextLayer} range, then Save Next.`
      : `Selected saved range #${id}. RH/RL loaded — use ↑/↓ for BOS after range is active.`);
    if (candles.length) {
      const chartTf = String(resolveRangeChartTimeframe(range, timeframe)).toUpperCase();
      const span = rangeWindowFieldsFromSavedRange(range);
      const layer = normalizeStructureLayer(range?.structure_layer || range?.layer);
      const dataWindow = resolveStructuralContextAndReplayWindows({
        rangeSpan: { start: span.start || span.end, end: span.end || span.start },
        chartTf,
        structureLayer: layer,
        label: `${formatStructuralRangeOptionLabel(range)} context`,
      })?.dataLoad;
      if (dataWindow) {
        structuralDataLoadWindowRef.current = dataWindow;
        structuralVisualContextRef.current = {
          start: span.start || span.end || '',
          end: span.end || span.start || '',
        };
      }
      applyStructuralReplayRestore(candles, {
        range,
        chartTf,
        loadWindowStart: dataWindow?.start ?? null,
        loadWindowEnd: dataWindow?.end ?? null,
        reason: 'range-select',
      });
    }
  };

  const mappingSessionLayerIds = useMemo(
    () => deriveLayerActiveIdsFromRanges(savedStructuralRanges, activeStructuralRangeId),
    [savedStructuralRanges, activeStructuralRangeId],
  );

  const mappingSessionSnapshot = useMemo(() => {
    const mappingCase = getCurrentMappingCaseRef();
    const guidedFields = guidedCursorToSessionFields(guidedCursor);
    const childResearchWindow = childMappingSession?.researchWindow;
    return {
      symbol,
      caseId: mappingCase.case_id,
      rawCaseId: mappingCase.raw_case_id,
      caseRef: mappingCase.case_ref,
      year: explorerYearFilter,
      structureLayer,
      ...mappingSessionLayerIds,
      selectedParentRangeId,
      activeStructuralRangeId,
      chartTimeframe: timeframe,
      sourceTimeframe,
      rangeScope,
      researchWindowStart: childResearchWindow?.start ?? rangeWindow.start ?? null,
      researchWindowEnd: childResearchWindow?.end ?? rangeWindow.end ?? null,
      currentCandidateIndex: childMappingSession?.candidateIndex ?? 0,
      childMappingActive: !!childMappingSession,
      childMappingDetectionRunId: childMappingSession?.detectionRunId ?? null,
      childMappingPhase: childMappingSession?.phase ?? null,
      ...guidedFields,
    };
  }, [
    symbol,
    activeCaseId,
    rawActiveCaseId,
    activeCaseLabel,
    explorerYearFilter,
    structureLayer,
    mappingSessionLayerIds,
    selectedParentRangeId,
    activeStructuralRangeId,
    timeframe,
    sourceTimeframe,
    rangeScope,
    rangeWindow.start,
    rangeWindow.end,
    guidedCursor,
    childMappingSession,
  ]);

  const {
    pendingResume: pendingMappingSession,
    orchestrationRef: mappingSessionOrchestrationRef,
    beginResumeFlow: beginMappingSessionResume,
    completeResumeFlow: completeMappingSessionResume,
    startNewSession: startNewMappingSession,
  } = useMappingSessionPersistence(mappingSessionSnapshot, {
    bootDelayMs: 300,
  });

  const blockMappingBootEffects = () =>
    isMappingSessionOrchestrating(mappingSessionOrchestrationRef)
    || pendingMappingSession !== null;

  const handleMappingSessionResume = useCallback(async () => {
    if (!pendingMappingSession) return;
    beginMappingSessionResume();
    skipBootstrapOnceRef.current = true;
    try {
      const result = await executeMappingSessionResume({
        stored: pendingMappingSession,
        hasCase: () => getCurrentMappingCaseRef().hasCase,
        scopeActions: {
          setStructureLayer,
          setRangeScope,
          setSourceTimeframe,
          setTimeframe: (tf: string) => {
            activeTimeframeRef.current = tf;
            setTimeframe(tf);
          },
          setSelectedParentRangeId,
          setActiveStructuralRangeId,
          setExplorerYearFilter,
          setRawActiveCaseId,
          onSymbolChange,
        },
        refreshSavedRanges: refreshSavedRangesForCurrentCase,
        refreshMapEvents: refreshStructuralMapEventsForChart,
        loadCandles: (tf) => {
          const targetTf = String(tf).toUpperCase();
          const loadWindow = resolveCandleLoadWindow(
            targetTf,
            savedStructuralRanges,
            selectedParentRangeId,
            activeStructuralRangeId,
            rangeWindowByTf[targetTf] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
          );
          return loadCandles(targetTf, {
            loadWindow,
            cacheFullHistory: !shouldUseWindowedCandleLoad(loadWindow),
          });
        },
        selectSavedStructuralRange,
      });
      writeAutoResumeSession(symbol, result.chartTimeframe);
      skipBootstrapOnceRef.current = true;
      const stored = pendingMappingSession;
      const restoredCursor = guidedCursorFromSessionFields(stored);
      if (restoredCursor) setGuidedCursor(restoredCursor);
      if (stored.child_mapping_active && stored.current_parent_range_id) {
        try {
          const ranges = await refreshSavedRangesForCurrentCase();
          const parentRow = findSavedRangeById(ranges, stored.current_parent_range_id);
          if (parentRow) {
            const bridge = getLocalResearchBridge();
            const dbStatus = bridge
              ? await bridge.getDatabaseStatus({ symbol, timeframe: stored.source_timeframe })
              : null;
            const session = await restoreChildMappingSession({
              parentRange: parentRow,
              detectionRunId: stored.child_mapping_detection_run_id,
              candidateIndex: stored.current_candidate_index,
              phase: stored.child_mapping_phase,
              symbol,
              databasePath: dbStatus?.databasePath,
            });
            if (session) {
              if (restoredCursor) {
                const win = guidedCursorResearchWindow(restoredCursor);
                session.researchWindow = {
                  start: win.start,
                  end: win.end,
                  dateFrom: win.dateFrom,
                  dateTo: win.dateTo,
                };
              }
              setChildMappingSession(session);
            }
          }
        } catch {
          /* non-blocking */
        }
      }
      completeMappingSessionResume();
      setMessage(result.message);
    } catch (err: any) {
      skipBootstrapOnceRef.current = true;
      completeMappingSessionResume();
      setMessage(`Mapping session resume failed: ${err?.message || err}`);
    }
  }, [
    pendingMappingSession,
    symbol,
    onSymbolChange,
    beginMappingSessionResume,
    completeMappingSessionResume,
    selectSavedStructuralRange,
  ]);

  const handleMappingSessionStartNew = useCallback(() => {
    startNewMappingSession();
    closeGuidedChildMapping();
    skipBootstrapOnceRef.current = false;
  }, [startNewMappingSession]);

  const handleMappingSessionOpenExplorer = useCallback(() => {
    setRightDeckTab('gps');
    setNavOverlayPanelOpen(true);
  }, []);

  const explorerYearOptions = useMemo(() => {
    const years = new Set<number>();
    for (const r of savedStructuralRanges) {
      const y = rangeYearBucket(r);
      if (y !== null) years.add(y);
    }
    return Array.from(years).sort((a, b) => b - a);
  }, [savedStructuralRanges]);

  const explorerFilteredRanges = useMemo(
    () => filterRangesForExplorerYear(savedStructuralRanges, explorerYearFilter),
    [savedStructuralRanges, explorerYearFilter],
  );

  const explorerTreeRanges = explorerFilteredRanges;

  const gapQueueRanges = useMemo(
    () => filterRangesForExplorerMode(explorerFilteredRanges as Record<string, unknown>[], explorerMappingMode),
    [explorerFilteredRanges, explorerMappingMode],
  );

  const mappingGaps = useMemo(
    () => computeMappingGaps(gapQueueRanges, explorerMappingMode),
    [gapQueueRanges, explorerMappingMode],
  );

  const campaignStatus = useMemo(
    () => computeCampaignStatus(savedStructuralRanges, explorerYearFilter),
    [savedStructuralRanges, explorerYearFilter],
  );

  const caseHierarchyForest = useMemo(
    () => buildCaseHierarchyForest(explorerTreeRanges),
    [explorerTreeRanges],
  );

  const eventBrowserFormatRowLabel = useCallback((range: any, directChildCount: number, childCountLabel?: string | null) => {
    const lines = formatExplorerRowLines(range, directChildCount, childCountLabel);
    return [lines.line1, lines.line2, lines.spanNote].filter(Boolean).join(' · ');
  }, []);

  const eventBrowserRowHighlight = useCallback((range: any) => {
    const id = String(range?.range_id || range?.id || '');
    const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || 'WEEKLY';
    const isActive = id === String(activeStructuralRangeId);
    const isParentContext = id === String(selectedParentRangeId) && (
      (rangeScope === 'MINOR' && normalizeStructureLayer(range?.structure_layer || range?.layer) === structureLayer && isRangeMajor(range))
      || (rangeScope === 'MAJOR' && expectedParentStructureLayer(structureLayer) === layer)
    );
    return { isActive, isParentContext };
  }, [activeStructuralRangeId, selectedParentRangeId, rangeScope, structureLayer]);

  useEffect(() => {
    if (explorerMappingMode !== 'htf') return;
    setHierarchyPathOnly(true);
    setHierarchyShowSiblings(false);
    setHierarchyShowChildren(false);
    setHierarchyShowAll(false);
  }, [explorerMappingMode]);

  const refreshStructuralRanges = async () => {
    const params = new URLSearchParams({ symbol });
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setStructuralRanges([]);
      setSelectedParentRangeId('');
      setMessage('Create or select a mapping case before loading structural ranges.');
      return;
    }
    appendMappingCaseParams(params, mappingCase);
    const loadParentLayer = expectedParentStructureLayer(structureLayer);
    if (loadParentLayer) {
      params.set('structure_layer', loadParentLayer);
      params.set('source_timeframe', defaultSourceTimeframeForStructureLayer(loadParentLayer));
    } else {
      params.set('structure_layer', structureLayer);
      params.set('source_timeframe', sourceTimeframe);
    }
    try {
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/ranges?${params.toString()}`);
      const rows = visibleStructuralRanges(safeArray<StructuralRange>(data.ranges));
      setStructuralRanges(rows);
      const parentLayer = expectedParentStructureLayer(structureLayer);
      if (parentLayer && rows.length) {
        const validSelected = rows.some(r => String(r.range_id || r.id) === String(selectedParentRangeId));
        if (!validSelected && rows.length === 1) {
          setSelectedParentRangeId(String(rows[0].range_id || rows[0].id || ''));
        }
      }
    } catch (err:any) {
      setMessage(`Load structural ranges failed: ${err?.message || err}`);
    }
  };

  const refreshHierarchyAudit = async () => {
    const params = new URLSearchParams({ symbol });
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setHierarchyAudit(null);
      setMessage('Create or select a mapping case before refreshing audit.');
      return null;
    }
    appendMappingCaseParams(params, mappingCase);
    try {
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/hierarchy-audit?${params.toString()}`);
      setHierarchyAudit(data);
      const s = data?.summary || {};
      const hasErrors = Number(s.invalid_parent_links || 0) > 0 || Number(s.ranges_missing_rh_rl || 0) > 0 || Number(s.bos_events_missing_bh_bl || 0) > 0;
      const hasWarn = Number(s.orphan_daily_ranges || 0) > 0 || Number(s.orphan_intraday_ranges || 0) > 0;
      setMessage(`Hierarchy audit ${hasErrors ? 'FAIL' : hasWarn ? 'WARN' : 'PASS'} · M ${s.macro_ranges || 0} / W ${s.weekly_ranges || 0} / D ${s.daily_ranges || 0} · W→M ${s.weekly_ranges_linked_to_macro || 0} · D→W ${s.daily_ranges_linked_to_weekly || 0}`);
      return data;
    } catch (err:any) {
      setMessage(`Hierarchy audit failed: ${err?.message || err}`);
      return null;
    }
  };

  const restoreCaseWorkspaceFromVps = async (rawId: string, preferredTf?: string) => {
    const tf = String(preferredTf || caseTimeframe || timeframe).toUpperCase();
    const eventCount = await loadRawCaseLedgerIntoWorkspace(rawId, tf);
    if (tf && tf !== timeframe) {
      activeTimeframeRef.current = tf;
      setTimeframe(tf);
    }
    try {
      const rows = await refreshSavedRangesForCurrentCase();
      await refreshStructuralMapEventsForChart(tf);
      await refreshStructuralRanges().catch(() => {});
      return { eventCount, rangeCount: rows.length };
    } catch (err: any) {
      setMessage(`Case ledger restored (${eventCount} events); structural ranges failed: ${err?.message || err}`);
      return { eventCount, rangeCount: 0 };
    }
  };

  useEffect(() => {
    if (rightDeckTab === 'seed') {
      refreshSavedRangesForCurrentCase().catch(() => {});
    }
  }, [rightDeckTab, activeCaseId, rawActiveCaseId]);

  useEffect(() => {
    if (rightDeckTab === 'mark' && markWorkspaceMode === 'htf') {
      refreshStructuralRanges();
      refreshSavedRangesForCurrentCase().catch((err:any)=>setMessage(`Load saved ranges failed: ${err?.message || err}`));
    }
  }, [rightDeckTab, markWorkspaceMode, structureLayer, sourceTimeframe, symbol, activeCaseId, rawActiveCaseId]);

  useEffect(() => {
    if (!chartFullscreen && !(rightDeckTab === 'mark' && markWorkspaceMode === 'htf')) return;
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) return;
    refreshSavedRangesForCurrentCase().catch(() => {});
    refreshStructuralRanges().catch(() => {});
  }, [chartFullscreen, rightDeckTab, markWorkspaceMode, symbol, activeCaseId, rawActiveCaseId, structureLayer, sourceTimeframe]);

  const chartStructureForTimeframe = (tfRaw:string) => chartStructureForTimeframeStatic(tfRaw);

  const applyStructuralDraftPoint = (kind:'RH'|'RL'|'BH'|'BL', candle:Candle, next:{price:string; time:string; candle:Candle|null}) => {
    if (kind === 'RH') {
      rhAnchorRef.current = next;
      setRhAnchor(next);
      setRangeHigh(next.price);
      setRangeWindowByTf(prev => {
        const window = timesToWindow([rlAnchor.time, candle.time]);
        return { ...prev, [timeframe]: { ...(prev[timeframe] || {}), ...(window || { start:candle.time, end:candle.time }) }};
      });
      setStructuralRangeDraftDirty(true);
      setStructuralAnchorsByLayer(prev => ({
        ...prev,
        [structureLayer]: {
          rh: next,
          rl: prev[structureLayer]?.rl || rlAnchor,
        },
      }));
    }
    if (kind === 'RL') {
      rlAnchorRef.current = next;
      setRlAnchor(next);
      setRangeLow(next.price);
      setRangeWindowByTf(prev => {
        const window = timesToWindow([rhAnchor.time, candle.time]);
        return { ...prev, [timeframe]: { ...(prev[timeframe] || {}), ...(window || { start:candle.time, end:candle.time }) }};
      });
      setStructuralRangeDraftDirty(true);
      setStructuralAnchorsByLayer(prev => ({
        ...prev,
        [structureLayer]: {
          rh: prev[structureLayer]?.rh || rhAnchor,
          rl: next,
        },
      }));
    }
    if (kind === 'BH') {
      setBhAnchor(next);
      setStructuralBosDraftDirty(true);
    }
    if (kind === 'BL') {
      setBlAnchor(next);
      setStructuralBosDraftDirty(true);
    }
    const label = kind === 'RH' ? 'Range High' : kind === 'RL' ? 'Range Low' : kind === 'BH' ? 'Break High' : 'Break Low';
    const viewNote = kind === 'RH' || kind === 'RL' ? 'visible fib range updated; not saved yet' : 'draft marker only; fib range unchanged';
    return { label, viewNote };
  };

  const persistStructuralQuickMarker = async (
    kind: 'RH' | 'RL',
    candle: Candle,
    next: { price: string; time: string; candle: Candle | null },
    previous: Record<string, unknown>,
  ) => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) return;
    const eventTypeByRole: Record<'RH' | 'RL', string> = {
      RH: 'RANGE_HIGH_SELECTED',
      RL: 'RANGE_LOW_SELECTED',
    };
    const eventId = crypto.randomUUID();
    const parentForEvent = (() => {
      const resolved = resolveParentIdForStructuralSave();
      const raw = resolved.parentId || selectedParentRangeId || null;
      if (raw === null || raw === undefined || String(raw) === '') return null;
      const parentRow = findSavedRangeRowById(String(raw));
      if (!parentRow) return null;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : null;
    })();
    const payload: Record<string, unknown> = {
      event_id: eventId,
      case_id: mappingCase.case_id,
      raw_case_id: mappingCase.raw_case_id,
      case_ref: mappingCase.case_ref,
      symbol,
      ...structuralMappingScopeFields(structureLayer, sourceTimeframe, timeframe),
      active_range_id: activeStructuralRangeId ? Number(activeStructuralRangeId) || activeStructuralRangeId : null,
      parent_range_id: parentForEvent,
      event_type: eventTypeByRole[kind],
      structural_event: eventTypeByRole[kind],
      event_time: candle.time,
      event_price: Number(next.price),
      candle_time: candle.time,
      candle_open: candle.open,
      candle_high: candle.high,
      candle_low: candle.low,
      candle_close: candle.close,
      meta_json: {
        role: kind,
        quick_button: true,
        mapping_layer_authority: true,
      },
    };
    const data = await inspectorCommitOrThrow({
      baseUrl: BASE_URL,
      kind: 'structural_event',
      source: 'structural_quick_button',
      payload,
    });
    const saved = {
      role: kind,
      event_id: data.event_id || data.event?.event_id || eventId,
      db_id: data.id || data.event?.id || null,
      timeframe,
      structure_layer: structureLayer,
      source_timeframe: sourceTimeframe,
      candle_time: candle.time,
      event_price: Number(next.price),
      previous,
      payload,
      saved_at: new Date().toISOString(),
    };
    pushQuickEvent(saved);
  };

  const commitStructuralRangeWhenReady = async (
    draftRh: StructuralAnchor,
    draftRl: StructuralAnchor,
    sourceKind: 'RH' | 'RL',
  ) => {
    if (!hasStructuralAnchorPrice(draftRh) || !hasStructuralAnchorPrice(draftRl)) return;
    const attemptKey = chainDraftMode
      ? `chain:${activeStructuralRangeId}:${draftRh.time}:${draftRl.time}`
      : `range:${activeStructuralRangeId || 'new'}:${draftRh.time}:${draftRl.time}`;
    if (autoRangeSaveAttemptRef.current === attemptKey) return;
    autoRangeSaveAttemptRef.current = attemptKey;
    if (chainDraftMode && saveNextRangeEligible.eligible) {
      const ok = await saveNextStructuralRange({ auto: true, anchors: { rh: draftRh, rl: draftRl } });
      if (ok) {
        setMessage(`${structureLayer} range synced · chain linked · set next RH/RL or continue Campaign`);
      }
      return;
    }
    if (chainDraftMode) return;
    const ok = await saveStructuralRange({ anchors: { rh: draftRh, rl: draftRl } });
    if (ok) {
      const id = activeStructuralRangeId || lastSavedRangeConfirmation?.range_id || '?';
      setMessage(`${structureLayer} #${id} · RH/RL synced · range lines updated`);
    }
  };

  const setStructuralPoint = async (kind:'RH'|'RL'|'BH'|'BL') => {
    if (chartRenderer === 'tradingview' && !tradingViewMappingInputEnabled) {
      setMessage('TradingView mapping input disabled.');
      setTradingViewSelectionWarning('TradingView mapping input disabled.');
      return;
    }
    if (structuralSaving) {
      setMessage('Wait for the current range save to finish.');
      return;
    }
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setMessage('Open a case first (Folder tab).');
      return;
    }
    if ((kind === 'RH' || kind === 'RL') && !canSetRhRlStructuralDraft) {
      setMessage(mappingRhRlDraftBlockMessage);
      return;
    }
    if (!assertCandleFeedReady(`${kind} mark`)) return;
    if (!assertAdmittedMappingInputCandle(`${kind} mark`)) return;
    if (kind === 'BH') { await saveStructuralBos('UP', { quickButton:true }); return; }
    if (kind === 'BL') { await saveStructuralBos('DOWN', { quickButton:true }); return; }
    const candle = resolveMappingInputCandleAtAction();
    if (!candle) {
      if (chartRenderer === 'tradingview' && tradingViewMappingInputEnabled) {
        setMessage('Click a TradingView candle first · then H = RH · L = RL');
        setTradingViewSelectionWarning('No TradingView candle selected.');
      } else {
        setMessage('Click a candle first · then H = RH · L = RL');
      }
      return;
    }
    const anchorPrice = kind === 'RL' ? candle.low : candle.high;
    const next = { price: Number(anchorPrice).toFixed(2), time: candle.time, candle };
    const nextNum = parseNum(next.price);
    if (kind === 'RH' && hasStructuralAnchorPrice(rlAnchorRef.current)) {
      const rlNum = parseNum(rlAnchorRef.current.price);
      if (Number.isFinite(rlNum) && Number.isFinite(nextNum) && nextNum <= rlNum) {
        setMessage(`RH must be above RL (${rlNum.toFixed(2)}). Pick a candle with a higher high.`);
        return;
      }
    }
    if (kind === 'RL' && hasStructuralAnchorPrice(rhAnchorRef.current)) {
      const rhNum = parseNum(rhAnchorRef.current.price);
      if (Number.isFinite(rhNum) && Number.isFinite(nextNum) && nextNum >= rhNum) {
        setMessage(`RL must be below RH (${rhNum.toFixed(2)}). Pick a candle with a lower low.`);
        return;
      }
    }
    const previous = {
      RH: rhAnchor,
      RL: rlAnchor,
      BH: bhAnchor,
      BL: blAnchor,
      range: rangeByTf[timeframe] || null,
      window: rangeWindowByTf[timeframe] || null,
    };
    applyStructuralDraftPoint(kind, candle, next);
    const draftRh = kind === 'RH' ? next : rhAnchorRef.current;
    const draftRl = kind === 'RL' ? next : rlAnchorRef.current;
    const bothReady = hasStructuralAnchorPrice(draftRh) && hasStructuralAnchorPrice(draftRl);
    if (kind === 'RH' && !hasStructuralAnchorPrice(draftRl)) {
      setToolMode('select');
      setChartDrawTool('off');
      setMessage(`RH set · pick RL candle · press L`);
    } else if (kind === 'RL' && !hasStructuralAnchorPrice(draftRh)) {
      setMessage(`RL set · pick RH candle · press H`);
    } else if (bothReady) {
      setMessage(`${kind} set · syncing ${structureLayer} range…`);
      await commitStructuralRangeWhenReady(draftRh, draftRl, kind);
    } else {
      setMessage(`${kind} set at ${shortTime(candle.time, timeframe)} · ${next.price}`);
    }
    void persistStructuralQuickMarker(kind, candle, next, previous).catch(() => {
      // Range save is authoritative; marker events are audit-only.
    });
  };

  const applyQuickEventPreviousSnapshot = (ev: any) => {
    const prev = ev?.previous || {};
    if (ev.role === 'RH') {
      setRhAnchor(prev.RH || { price: '', time: '' });
      if (prev.range) setRangeByTf((p: any) => ({ ...p, [ev.timeframe || timeframe]: prev.range }));
      else setRangeHigh(prev.RH?.price || '');
      setRangeWindowByTf((p: any) => ({ ...p, [ev.timeframe || timeframe]: prev.window || {} }));
    }
    if (ev.role === 'RL') {
      setRlAnchor(prev.RL || { price: '', time: '' });
      if (prev.range) setRangeByTf((p: any) => ({ ...p, [ev.timeframe || timeframe]: prev.range }));
      else setRangeLow(prev.RL?.price || '');
      setRangeWindowByTf((p: any) => ({ ...p, [ev.timeframe || timeframe]: prev.window || {} }));
    }
    if (ev.role === 'BH' || ev.role === 'BREAK_UP') setBhAnchor(prev.BH || { price: '', time: '' });
    if (ev.role === 'BL' || ev.role === 'BREAK_DOWN') setBlAnchor(prev.BL || { price: '', time: '' });
    if (ev.role === 'RH' || ev.role === 'RL') setStructuralRangeDraftDirty(!!(prev.RH?.price || prev.RL?.price));
    if (isBosBreakQuickEventRole(ev.role)) setStructuralBosDraftDirty(!!(prev.BH?.price || prev.BL?.price));
  };

  const undoLastQuickEvent = () => {
    if (!canUndoQuickEvent || quickEventSaving) return;
    const ev = popQuickEventFromStack();
    if (!ev) return;
    applyQuickEventPreviousSnapshot(ev);
    if (ev.event_id) {
      const eventId = String(ev.event_id);
      const dbId = ev.db_id != null ? String(ev.db_id) : '';
      setEventsForTf((prev) => prev.filter((e) => {
        const id = String(e.id || '');
        const rawId = String(e.raw_event_id || '');
        return id !== eventId && rawId !== eventId && (!dbId || id !== dbId);
      }));
    }
    setLastRangeLifecyclePatchWarning(null);
    setMessage(`Undid ${ev.role} on ${ev.timeframe || timeframe} ${shortTime(ev.candle_time, ev.timeframe || timeframe)}.`);
  };

  const structuralWindow = (rh: StructuralAnchor = rhAnchor, rl: StructuralAnchor = rlAnchor) => {
    const dateFields = structuralRangeDateFields(rh.time, rl.time);
    const rhMs = parseStructuralTimeMs(rh.time);
    const rlMs = parseStructuralTimeMs(rl.time);
    const spanMs = [rhMs, rlMs].filter((x): x is number => x !== null);
    const duration = spanMs.length
      ? Math.round(Math.abs(Math.max(...spanMs) - Math.min(...spanMs)) / 60000)
      : null;
    return { ...dateFields, duration };
  };

  const saveStructuralRange = async (options?: { anchors?: { rh: StructuralAnchor; rl: StructuralAnchor } }): Promise<boolean> => {
    if (structuralSaving) {
      setMessage('Range save already in progress…');
      return false;
    }
    const rh = options?.anchors?.rh ?? rhAnchorRef.current;
    const rl = options?.anchors?.rl ?? rlAnchorRef.current;
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before saving a range.'); return false; }
    if (!assertCandleFeedReady('Range save')) return false;
    if (!rh.price || !rl.price) { setMessage('Set Range High and Range Low before saving a structural range.'); return false; }
    const draftHigh = parseNum(rh.price);
    const draftLow = parseNum(rl.price);
    if (Number.isFinite(draftHigh) && Number.isFinite(draftLow) && draftHigh <= draftLow) {
      setMessage('Range High must be above Range Low before saving.');
      return false;
    }
    const activeRangeForSave = activeStructuralRangeId
      ? (selectedSavedRange || findSavedRangeRowById(activeStructuralRangeId))
      : null;
    const activeRangeLayer = activeRangeForSave
      ? normalizeStructureLayer(activeRangeForSave.structure_layer || activeRangeForSave.layer)
      : null;
    const activeRangeScope = activeRangeForSave ? normalizeRangeScope(activeRangeForSave.range_scope) : null;
    const existsInLedger = !!activeRangeForSave;
    const isUpdate = !!(existsInLedger && activeStructuralRangeId && activeRangeLayer === structureLayer && activeRangeScope === rangeScope);
    const isBrokenUpdate = !!(isUpdate && activeRangeForSave && isStructuralRangeBrokenStatusValue(activeRangeForSave.status));
    if (activeStructuralRangeId && !existsInLedger) {
      setMessage(`Active range #${activeStructuralRangeId} is not in this case — saving as a new range.`);
    } else if (activeStructuralRangeId && activeRangeLayer && activeRangeLayer !== structureLayer) {
      setMessage(`Active range #${activeStructuralRangeId} is ${activeRangeLayer}. Saving new ${structureLayer} range instead.`);
    }
    const parentResolve = resolveParentIdForStructuralSave();
    if (parentResolve.autoSelected && parentResolve.parentId) {
      setSelectedParentRangeId(String(parentResolve.parentId));
    }
    setStructuralSaving(true);
    let savedRangeId = '';
    try {
      const win = structuralWindow(rh, rl);
      const tvSaveAnchorTimesOnly = chartRendererRef.current === 'tradingview' && tradingViewMappingInputEnabledRef.current;
      const anchorTimes = resolveEffectiveStructuralAnchorTimes(
        rh,
        rl,
        tvSaveAnchorTimesOnly ? null : (rangeWindowByTf[timeframe] || rangeWindow),
        tvSaveAnchorTimesOnly ? null : (selectedCandleRef.current?.time || resolveReplayCandleAtAction()?.time || null),
      );
      const dateFields = structuralRangeDateFields(anchorTimes.range_high_time, anchorTimes.range_low_time);
      const safeCaseKey = String(mappingCase.case_ref || mappingCase.raw_case_id || mappingCase.case_id || 'case').replace(/[^0-9A-Za-z_-]+/g, '_');
      const parentRangeIdForSave = parentResolve.parentId ? Number(parentResolve.parentId) : null;
      const payload = {
        ...(isUpdate ? { range_id: activeStructuralRangeId } : { range_key: `${safeCaseKey}_${structureLayer}_${sourceTimeframe}_${Date.now()}` }),
        case_id: mappingCase.case_id,
        raw_case_id: mappingCase.raw_case_id,
        case_ref: mappingCase.case_ref,
        symbol,
        range_scope: rangeScope,
        ...structuralMappingScopeFields(structureLayer, sourceTimeframe, timeframe),
        parent_range_id: parentRangeIdForSave,
        range_high_price: Number(rh.price),
        range_low_price: Number(rl.price),
        range_high_time: anchorTimes.range_high_time || win.range_high_time,
        range_low_time: anchorTimes.range_low_time || win.range_low_time,
        range_start_time: dateFields.range_start_time || win.range_start_time,
        range_end_time: dateFields.range_end_time || win.range_end_time,
        active_from_time: dateFields.active_from_time || win.active_from_time,
        duration_minutes: win.duration,
        ...structuralRangeStatusFieldsForSave(isBrokenUpdate, activeRangeForSave),
        meta_json: { phase:'electron_phase3_structural_mapping', proof_target:'WEEKLY_DAILY', parent_link_mode: parentResolve.mode },
      };
      const targetRangeId = isUpdate ? String(activeStructuralRangeId) : '';
      const data = await inspectorCommitOrThrow({
        baseUrl: BASE_URL,
        kind: 'structural_range',
        source: 'structural_range_save',
        payload,
      });
      const id = String(data.range_id || data.id || data.range?.range_id || data.range?.id || '');
      savedRangeId = id;
      setActiveStructuralRangeId(id);
      setStructuralRangeDraftDirty(false);
      setRhAnchor({ price: String(rh.price), time: String(rh.time || ''), candle: rh.candle || null });
      setRlAnchor({ price: String(rl.price), time: String(rl.time || ''), candle: rl.candle || null });
      setRangeHigh(String(rh.price));
      setRangeLow(String(rl.price));
      const confirmation = {
        range_id: id || null,
        mode: isUpdate ? 'updated' : 'created',
        structure_layer: data.range?.structure_layer || structureLayer,
        source_timeframe: data.range?.source_timeframe || sourceTimeframe,
        parent_range_id: data.range?.parent_range_id ?? payload.parent_range_id,
        raw_case_id: data.range?.raw_case_id || mappingCase.raw_case_id,
        case_ref: data.range?.case_ref || mappingCase.case_ref,
        range_high_price: data.range?.range_high_price ?? payload.range_high_price,
        range_low_price: data.range?.range_low_price ?? payload.range_low_price,
      };
      setLastSavedRangeConfirmation(confirmation);
      setStructuralAnchorsByLayer(prev => ({
        ...prev,
        [structureLayer]: {
          rh: { price: String(rh.price), time: String(rh.time || ''), candle: rh.candle || null },
          rl: { price: String(rl.price), time: String(rl.time || ''), candle: rl.candle || null },
        },
      }));
      if (savedRangeId) {
        const mergedRange = {
          ...(data.range || {}),
          range_id: Number(savedRangeId) || savedRangeId,
          id: Number(savedRangeId) || savedRangeId,
          structure_layer: confirmation.structure_layer,
          source_timeframe: confirmation.source_timeframe,
          range_high_price: confirmation.range_high_price,
          range_low_price: confirmation.range_low_price,
          range_high_time: payload.range_high_time,
          range_low_time: payload.range_low_time,
          range_scope: rangeScope,
          parent_range_id: confirmation.parent_range_id,
          case_ref: confirmation.case_ref,
          raw_case_id: confirmation.raw_case_id,
        };
        setSavedStructuralRanges(prev => {
          const idx = prev.findIndex((r: any) => String(r.range_id || r.id) === savedRangeId);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = { ...next[idx], ...mergedRange };
            return next;
          }
          return [...prev, mergedRange as StructuralRange];
        });
        if (isBrokenUpdate && targetRangeId) {
          console.info('[Update Broken Range]', {
            targetRangeId,
            payload,
            backendResponse: data,
            refreshedRangeRow: data.range || mergedRange,
          });
        }
      }
      setMessage(`${isUpdate ? 'Updated selected' : 'Saved new'} ${confirmation.structure_layer} range #${id || '?'} · ${confirmation.source_timeframe} · parent ${confirmation.parent_range_id || 'none'} · RH ${confirmation.range_high_price} / RL ${confirmation.range_low_price}${isBrokenUpdate ? ' · BROKEN lifecycle preserved' : ''}`);
      if (savedRangeId) {
        try {
          await refreshSavedRangesForCurrentCase();
          await refreshHierarchyAudit();
        } catch (refreshErr: any) {
          setMessage(`Saved range #${savedRangeId}; refresh failed: ${refreshErr?.message || refreshErr}`);
        }
        void refreshStructuralRanges().catch(() => {});
      }
      return !!savedRangeId;
    } catch (err:any) {
      setMessage(`Range save failed: ${err?.message || err}`);
      return false;
    } finally {
      setStructuralSaving(false);
    }
  };

  const saveNextStructuralRange = async (options?: { auto?: boolean; anchors?: { rh: StructuralAnchor; rl: StructuralAnchor } }) => {
    if (structuralSaving) return false;
    if (!saveNextRangeEligible.eligible) {
      setMessage(saveNextRangeEligible.reason || 'Save Next Range is not available yet.');
      return false;
    }
    const rh = options?.anchors?.rh ?? rhAnchorRef.current;
    const rl = options?.anchors?.rl ?? rlAnchorRef.current;
    if (!rh.price || !rl.price) {
      setMessage('Set Range High and Range Low before saving the next range.');
      return false;
    }
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before saving the next range.'); return false; }
    if (!assertCandleFeedReady('Save next range')) return false;
    const oldRangeId = String(saveNextRangeEligible.oldRangeId || activeStructuralRangeId);
    const createdByEventId = saveNextRangeEligible.createdByEventId;
    const brokenRange = saveNextRangeEligible.brokenRange as any;
    const nextScope = normalizeRangeScope(rangeScope);
    let parentRangeId: string | number | null = saveNextRangeEligible.parentRangeId;
    if (nextScope === 'MAJOR') {
      const parentResolve = resolveParentRangeIdForSave(
        structureLayer,
        'MAJOR',
        parentSelectionForSave,
        savedStructuralRanges,
        childDraftSpan,
      );
      if (parentResolve.parentId) {
        parentRangeId = parentResolve.parentId;
      } else if (brokenRange && isRangeMajor(brokenRange) && brokenRange.parent_range_id != null && String(brokenRange.parent_range_id) !== '') {
        parentRangeId = brokenRange.parent_range_id;
      }
    } else {
      const brokenScope = normalizeRangeScope(brokenRange?.range_scope);
      if (brokenScope === 'MINOR') {
        parentRangeId = brokenRange?.parent_range_id ?? parentRangeId;
      } else if (brokenRange && isRangeMajor(brokenRange)) {
        parentRangeId = String(brokenRange.range_id || brokenRange.id);
      } else {
        const parentResolve = resolveParentRangeIdForSave(
          structureLayer,
          'MINOR',
          parentSelectionForSave,
          savedStructuralRanges,
          childDraftSpan,
        );
        if (parentResolve.parentId) parentRangeId = parentResolve.parentId;
      }
    }
    if (!createdByEventId) { setMessage('BOS event reference missing for chain. Break the range again or refresh audit.'); return false; }
    setStructuralSaving(true);
    try {
      const win = structuralWindow(rh, rl);
      const safeCaseKey = String(mappingCase.case_ref || mappingCase.raw_case_id || mappingCase.case_id || 'case').replace(/[^0-9A-Za-z_-]+/g, '_');
      const activeFromTime = win.active_from_time || win.range_start_time || rh.time || rl.time || null;
      const payload = {
        range_key: `${safeCaseKey}_${structureLayer}_${sourceTimeframe}_next_${oldRangeId}_${Date.now()}`,
        case_id: mappingCase.case_id,
        raw_case_id: mappingCase.raw_case_id,
        case_ref: mappingCase.case_ref,
        symbol,
        range_scope: nextScope,
        ...structuralMappingScopeFields(structureLayer, sourceTimeframe, timeframe),
        parent_range_id: parentRangeId,
        old_range_id: Number(oldRangeId),
        created_by_event_id: createdByEventId,
        range_high_price: Number(rh.price),
        range_low_price: Number(rl.price),
        range_high_time: win.range_high_time,
        range_low_time: win.range_low_time,
        range_start_time: win.range_start_time,
        range_end_time: win.range_end_time,
        duration_minutes: win.duration,
        ...activeStructuralRangeStatusFields(),
        active_from_time: activeFromTime,
        new_range_id: null,
        meta_json: { phase:'electron_phase3c_range_chain', chain_from_range_id: oldRangeId, chain_from_bos_event_id: createdByEventId, auto_chain_save: !!options?.auto },
      };
      const data = await inspectorCommitOrThrow({
        baseUrl: BASE_URL,
        kind: 'structural_range',
        source: 'structural_range_next',
        payload,
      });
      const newRangeId = String(data.range_id || data.id || data.range?.range_id || data.range?.id || '');
      if (!newRangeId) throw new Error('Next range saved but backend returned no range id.');

      let chainLinkFailed = false;
      try {
        const linkData = await patchOldRangeNewRangeId(oldRangeId, newRangeId);
        const linkedRange = linkData?.range || {};
        setSavedStructuralRanges(prev => prev.map((r:any) => {
          if (String(r.range_id || r.id) !== oldRangeId) return r;
          return { ...r, new_range_id: linkedRange.new_range_id ?? Number(newRangeId) };
        }));
      } catch (linkErr:any) {
        chainLinkFailed = true;
        setMessage(`Next range saved as #${newRangeId}, but linking old range #${oldRangeId} failed. Refresh audit. ${linkErr?.message || linkErr}`);
      }

      setActiveStructuralRangeId(newRangeId);
      clearStructuralRangeDraft();
      setChainDraftMode(false);
      autoChainSaveAttemptRef.current = '';
      const confirmation = {
        range_id: newRangeId,
        mode: 'chained_next' as const,
        structure_layer: data.range?.structure_layer || structureLayer,
        source_timeframe: data.range?.source_timeframe || sourceTimeframe,
        parent_range_id: data.range?.parent_range_id ?? parentRangeId,
        old_range_id: data.range?.old_range_id ?? Number(oldRangeId),
        created_by_event_id: data.range?.created_by_event_id ?? createdByEventId,
        raw_case_id: data.range?.raw_case_id || mappingCase.raw_case_id,
        case_ref: data.range?.case_ref || mappingCase.case_ref,
        range_high_price: data.range?.range_high_price ?? payload.range_high_price,
        range_low_price: data.range?.range_low_price ?? payload.range_low_price,
      };
      setLastSavedRangeConfirmation(confirmation);
      if (!chainLinkFailed) {
        const prefix = options?.auto ? 'Auto chain save complete. ' : '';
        setMessage(`${prefix}Next range saved. Range ${oldRangeId} → BOS ${createdByEventId} → Range ${newRangeId}.`);
        const childLayer = expectedChildStructureLayer(structureLayer);
        if (childLayer) {
          await drillToChildMapping({
            ...(data.range || {}),
            range_id: newRangeId,
            id: newRangeId,
            structure_layer: structureLayer,
          });
        }
      }
      void refreshSavedRangesForCurrentCase().catch(() => {});
      void refreshStructuralRanges().catch(() => {});
      void refreshHierarchyAudit().catch(() => {});
      return true;
    } catch (err:any) {
      setMessage(`Save Next Range failed: ${err?.message || err}`);
      return false;
    } finally {
      setStructuralSaving(false);
    }
  };

  useEffect(() => {
    if (!autoChainSave || !chainDraftMode || structuralSaving) return;
    if (!saveNextRangeEligible.eligible) return;
    if (!rhAnchor.price || !rlAnchor.price) return;
    const attemptKey = `${activeStructuralRangeId}:${rhAnchor.time}:${rlAnchor.time}:${structureLayer}`;
    if (autoChainSaveAttemptRef.current === attemptKey) return;
    autoChainSaveAttemptRef.current = attemptKey;
    void saveNextStructuralRange({ auto: true });
  }, [autoChainSave, chainDraftMode, structuralSaving, saveNextRangeEligible.eligible, rhAnchor.price, rhAnchor.time, rlAnchor.price, rlAnchor.time, activeStructuralRangeId, structureLayer]);

  const saveStructuralBos = async (direction:'UP'|'DOWN', options?:{ quickButton?:boolean }): Promise<boolean> => {
    if (structuralSaving) {
      setMessage('Wait for the current range save to finish before saving BOS.');
      return false;
    }
    if (quickEventSaving) {
      setMessage('Wait for the current quick event save to finish before saving BOS.');
      return false;
    }
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Open a case first (Folder tab).'); return false; }
    if (!mappingSkeletonContextReady) {
      setMessage('Select campaign or hierarchy context first.');
      return false;
    }
    if (!assertCandleFeedReady('BOS save')) return false;
    if (!assertAdmittedMappingInputCandle('BOS save')) return false;
    const candle = resolveMappingInputCandleAtAction();
    const quickAnchor = candle && options?.quickButton
      ? { price: Number(direction === 'UP' ? candle.high : candle.low).toFixed(2), time: candle.time, candle }
      : null;
    const anchor = quickAnchor || (direction === 'UP' ? bhAnchor : blAnchor);
    if (!anchor.price) { setMessage(`Select a candle, then click ${direction === 'UP' ? '↑ Break Up' : '↓ Break Down'}.`); return false; }
    let rangeId = resolveActiveRangeIdForAnchors();
    if (!rangeId) {
      setMessage(`Save or select a ${structureLayer} range first (Hierarchy tree or Save Range), then break it with ↑/↓.`);
      return false;
    }
    if (String(rangeId) !== String(activeStructuralRangeId)) {
      setActiveStructuralRangeId(String(rangeId));
    }
    const activeRange = findSavedRangeRowById(String(rangeId)) || null;
    if (activeRange && isStructuralRangeBrokenStatus(activeRange.status)) {
      setMessage(`Range #${rangeId} is already BROKEN. Set RH/RL for the next ${structureLayer} range, then Save Next.`);
      return false;
    }
    const activeRangeLayer = normalizeStructureLayer(activeRange?.structure_layer || activeRange?.layer);
    if (activeRangeLayer && activeRangeLayer !== structureLayer) {
      setMessage(`Active range is ${activeRangeLayer} but mapping scope is ${structureLayer}. Select a matching range or change scope.`);
      return false;
    }
    const activeRangeParentId = activeRange?.parent_range_id ?? null;
    const hasActiveRangeParent = activeRangeParentId !== null && activeRangeParentId !== undefined && String(activeRangeParentId) !== '';
    const parentResolve = resolveParentRangeIdForSave(
      structureLayer,
      normalizeRangeScope(activeRange?.range_scope) || rangeScope,
      parentSelectionForSave,
      savedStructuralRanges,
      childDraftSpan,
    );
    if (!hasActiveRangeParent && parentResolve.error) {
      setMessage(`${parentResolve.error} BOS will save without parent link.`);
    }
    setStructuralSaving(true);
    try {
      const candle = anchor.candle || resolveMappingInputCandleAtAction();
      if (!candle) { throw new Error(`Select a candle, then click ${direction === 'UP' ? '↑ Break Up' : '↓ Break Down'}.`); }
      const sourceBreakRole = direction === 'UP' ? 'BREAK_UP' : 'BREAK_DOWN';
      const legacyBreakRole = direction === 'UP' ? 'BH' : 'BL';
      const sourceBreakEvent = [...quickEventHistory].reverse().find((ev:any) =>
        [sourceBreakRole, legacyBreakRole].includes(String(ev?.role || '')) &&
        String(ev?.candle_time || '') === String(anchor.time || candle.time || '') &&
        String(ev?.source_timeframe || '') === String(sourceTimeframe)
      ) || ([sourceBreakRole, legacyBreakRole].includes(String(lastSavedQuickEvent?.role || '')) ? lastSavedQuickEvent : null);
      const refPrice = direction === 'UP'
        ? (activeRange?.range_high_price ?? activeRange?.range_high ?? null)
        : (activeRange?.range_low_price ?? activeRange?.range_low ?? null);
      const refTime = direction === 'UP'
        ? (activeRange?.range_high_time ?? null)
        : (activeRange?.range_low_time ?? null);
    const parentRangeIdForBos = (() => {
      const raw = hasActiveRangeParent
        ? activeRangeParentId
        : (parentResolve.parentId || selectedParentRangeId || null);
      if (raw === null || raw === undefined || String(raw) === '') return null;
      const parentRow = findSavedRangeRowById(String(raw));
      if (!parentRow) return null;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : null;
    })();
      const breakInactiveTime = anchor.time || candle.time || null;
      const payload = {
        event_id: crypto.randomUUID(),
        case_id: mappingCase.case_id,
        raw_case_id: mappingCase.raw_case_id,
        case_ref: mappingCase.case_ref,
        symbol,
        ...structuralMappingScopeFields(structureLayer, sourceTimeframe, timeframe),
        active_range_id: Number(rangeId) || rangeId,
        parent_range_id: parentRangeIdForBos,
        event_type: direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN',
        structural_event: direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN',
        break_level_type: direction === 'UP' ? 'BH' : 'BL',
        break_level_price: Number(anchor.price),
        break_level_time: anchor.time || null,
        event_time: anchor.time || candle?.time || new Date().toISOString(),
        event_price: Number(anchor.price),
        candle_time: candle?.time || anchor.time || null,
        candle_open: candle?.open ?? null,
        candle_high: candle?.high ?? null,
        candle_low: candle?.low ?? null,
        candle_close: candle?.close ?? null,
        direction,
        meta_json: {
          phase:'electron_phase3_structural_mapping',
          role: direction === 'UP' ? 'BREAK_UP' : 'BREAK_DOWN',
          formal_bos: true,
          formal_bos_event: true,
          quick_button: !!options?.quickButton,
          mapping_layer_authority: true,
          quick_marker_role_source: direction === 'UP' ? 'BREAK_UP' : 'BREAK_DOWN',
          created_from_break_marker_event_id: sourceBreakEvent?.event_id || null,
          ref_source: direction === 'UP' ? 'active_range.range_high_price' : 'active_range.range_low_price',
          ref_price: refPrice,
          ref_time: refTime,
          ref_derivation: direction === 'UP'
            ? 'BOS_UP reference is derived from active_range.range_high_price'
            : 'BOS_DOWN reference is derived from active_range.range_low_price',
          parent_break_not_updated: true,
          parent_break_note: 'Weekly parent BH/BL is updated only by the later Parent Break action.',
        },
      };
      const data = await inspectorCommitOrThrow({
        baseUrl: BASE_URL,
        kind: 'structural_event',
        source: 'structural_bos',
        payload,
      });
      const returned = data?.event || data || {};
      const expectedType = direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN';
      const returnedType = String(returned.event_type || '').toUpperCase();
      const returnedStructural = String(returned.structural_event || returned.event_type || '').toUpperCase();
      if (returnedType !== expectedType && returnedStructural !== expectedType) {
        throw new Error(`Backend saved BOS with wrong event type: ${returned.event_type || returned.structural_event || 'missing'}`);
      }
      const returnedLayer = normalizeStructureLayer(returned.structure_layer || returned.layer);
      if (returnedLayer && returnedLayer !== structureLayer) {
        setMessage(`BOS saved on ${returnedLayer}; mapping scope is ${structureLayer}. Check hierarchy if this looks wrong.`);
      }

      const bosType = direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN';
      const chartEvent = mapStructuralEventRowToChartEvent({
        ...returned,
        event_id: data.event_id || returned.event_id || payload.event_id,
        id: data.id || returned.id || data.event?.id,
        event_type: expectedType,
        event_time: payload.event_time,
        event_price: payload.event_price,
        case_id: mappingCase.case_id,
        raw_case_id: mappingCase.raw_case_id,
        case_ref: mappingCase.case_ref,
      });
      if (chartEvent) {
        setEventsForTf(prev => mergeChartEventsById(safeArray(prev), [chartEvent]));
        setSessionEventIds(prev => new Set([...prev, chartEvent.id]));
      }
      let lifecyclePatchData: any = null;
      let lifecyclePatchFailed = false;
      try {
        const eventRef = resolveStructuralEventRef(data, payload);
        if (!breakInactiveTime) throw new Error('Break candle time missing; cannot patch range lifecycle.');
        lifecyclePatchData = await patchActiveRangeBroken(String(rangeId), {
          direction_of_break: direction,
          broken_by_event_id: eventRef.broken_by_event_id,
          inactive_from_time: String(breakInactiveTime),
        });
        setLastRangeLifecyclePatchWarning(null);
      } catch (patchErr:any) {
        lifecyclePatchFailed = true;
        const patchMessage = `BOS saved, but range lifecycle patch failed. Refresh audit. ${patchErr?.message || patchErr}`;
        setLastRangeLifecyclePatchWarning(patchMessage);
        setMessage(patchMessage);
      }

      const nextBreakAnchor = { price:String(anchor.price), time:String(anchor.time || candle.time), candle };
      const previous = {
        RH: rhAnchor,
        RL: rlAnchor,
        BH: bhAnchor,
        BL: blAnchor,
        range: rangeByTf[timeframe] || null,
        window: rangeWindowByTf[timeframe] || null,
      };
      if (direction === 'UP') setBhAnchor(nextBreakAnchor);
      if (direction === 'DOWN') setBlAnchor(nextBreakAnchor);
      if (options?.quickButton) {
        const saved = {
          role: direction === 'UP' ? 'BREAK_UP' : 'BREAK_DOWN',
          event_id: data.event_id || data.event?.event_id || payload.event_id,
          db_id: data.id || data.event?.id || null,
          timeframe,
          structure_layer: structureLayer,
          source_timeframe: sourceTimeframe,
          candle_time: candle.time,
          event_price: Number(anchor.price),
          previous,
          payload,
          range_lifecycle_patched: !!lifecyclePatchData,
          broken_range_id: lifecyclePatchData ? rangeId : null,
          saved_at: new Date().toISOString(),
        };
        pushQuickEvent(saved);
      }
      setStructuralBosDraftDirty(false);
      if (lifecyclePatchData) {
        const patchedRange = lifecyclePatchData?.range || {};
        setSavedStructuralRanges(prev => prev.map((r:any) => {
          if (String(r.range_id || r.id) !== String(rangeId)) return r;
          return {
            ...r,
            status: patchedRange.status || 'BROKEN',
            direction_of_break: patchedRange.direction_of_break || direction,
            broken_by_event_id: patchedRange.broken_by_event_id ?? data.id ?? data.event?.id ?? null,
            inactive_from_time: patchedRange.inactive_from_time || breakInactiveTime,
          };
        }));
        const eventRef = resolveStructuralEventRef(data, payload);
        if (activeRange && isRangeMajor(activeRange)) {
          setSelectedParentRangeId(String(rangeId));
        }
        if (activeRange && isRangeMajor(activeRange)) {
          setRangeScope('MAJOR');
        } else if (activeRange) {
          setRangeScope('MINOR');
        }
        await applyBosNextRangePromptAfterSave(
          String(rangeId),
          activeRange,
          bosType,
          eventRef.broken_by_event_id,
        );
      } else if (!lifecyclePatchFailed) {
        setMessage(`Saved ${direction === 'UP' ? 'Break Up' : 'Break Down'} as ${bosType} · range #${rangeId} · ref ${refPrice ?? 'derived later'}`);
      }
      try { await refreshStructuralMapEventsForChart(timeframe); } catch {}
      try { await refreshHierarchyAudit(); } catch {}
      return true;
    } catch (err:any) {
      setMessage(`BOS_${direction} save failed: ${err?.message || err}`);
      return false;
    } finally {
      setStructuralSaving(false);
    }
  };

  const downloadJsonFile = (payload:any, filename:string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type:'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 500);
  };

  const fetchCurrentMappingSnapshot = async () => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setMessage('Create or select a mapping case before exporting mapping JSON.');
      return null;
    }
    const baseParams = appendMappingCaseParams(new URLSearchParams({ symbol, limit:'5000' }), mappingCase);
    const [rangesData, treeData, auditData] = await Promise.all([
      structuralFetchJson(`${BASE_URL}/api/v1/map/ranges?${baseParams.toString()}`),
      structuralFetchJson(`${BASE_URL}/api/v1/map/range-tree?${appendMappingCaseParams(new URLSearchParams({ symbol }), mappingCase).toString()}`),
      structuralFetchJson(`${BASE_URL}/api/v1/map/hierarchy-audit?${appendMappingCaseParams(new URLSearchParams({ symbol }), mappingCase).toString()}`),
    ]);
    const refreshedSavedRanges = visibleStructuralRanges(safeArray<StructuralRange>(rangesData.ranges));
    setSavedStructuralRanges(refreshedSavedRanges);
    const eventParams = appendMappingCaseParams(new URLSearchParams({ symbol, limit:'5000' }), mappingCase);
    const eventsData = await structuralFetchJson(`${BASE_URL}/api/v1/map/events?${eventParams.toString()}`);
    const savedEvents = safeArray<any>(eventsData.events);
    const rangesById = new globalThis.Map<string, any>();
    refreshedSavedRanges.forEach((r:any)=>rangesById.set(String(r.range_id || r.id || ''), r));
    const formalBosTypeFor = (ev:any) => {
      const t = String(ev.event_type || ev.structural_event || '').toUpperCase();
      if (t === 'BREAK_HIGH_SELECTED') return 'BOS_UP';
      if (t === 'BREAK_LOW_SELECTED') return 'BOS_DOWN';
      if (t === 'BOS_UP' || t === 'BOS_DOWN') return t;
      return '';
    };
    const formalBosEvents = savedEvents
      .filter((ev:any)=>!!formalBosTypeFor(ev))
      .map((ev:any) => {
        const range = rangesById.get(String(ev.active_range_id || ''));
        const normalizedType = formalBosTypeFor(ev);
        const isUp = normalizedType === 'BOS_UP';
        return {
          ...ev,
          normalized_structural_event: normalizedType,
          derived_ref_price: range ? (isUp ? (range.range_high_price ?? range.range_high ?? null) : (range.range_low_price ?? range.range_low ?? null)) : null,
          derived_ref_time: range ? (isUp ? (range.range_high_time ?? null) : (range.range_low_time ?? null)) : null,
          derived_ref_source: isUp ? 'active_range.range_high_price' : 'active_range.range_low_price',
          ref_derivation: isUp ? 'BOS_UP reference is derived from active_range.range_high_price' : 'BOS_DOWN reference is derived from active_range.range_low_price',
        };
      });
    const quickMarkerEvents = savedEvents.filter((ev:any)=>['RANGE_HIGH_SELECTED','RANGE_LOW_SELECTED'].includes(String(ev.event_type || ev.structural_event || '').toUpperCase()));
    const eventsTodo = null;
    return { mappingCase, rangesData, refreshedSavedRanges, treeData, auditData, eventsData, formalBosEvents, quickMarkerEvents, eventsTodo };
  };

  const exportAuditJson = async () => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before exporting audit JSON.'); return; }
    const audit = hierarchyAudit || await refreshHierarchyAudit();
    if (!audit) return;
    downloadJsonFile({
      generated_at: new Date().toISOString(),
      symbol,
      timeframe,
      structure_layer: structureLayer,
      source_timeframe: sourceTimeframe,
      active_case_ref: mappingCase,
      hierarchy_audit: audit,
      note: 'Audit export reads backend state only; it does not save drafts.',
    }, `hierarchy_audit_${String(symbol)}_${String(mappingCase.case_ref || 'case').replace(/[^a-zA-Z0-9_-]+/g,'_')}.json`);
    setMessage('Exported hierarchy audit JSON. Export does not save drafts.');
  };

  const exportCurrentMappingJson = async () => {
    try {
      const snapshot = await fetchCurrentMappingSnapshot();
      if (!snapshot) return;
      const payload = {
        generated_at: new Date().toISOString(),
        symbol,
        timeframe,
        structure_layer: structureLayer,
        source_timeframe: sourceTimeframe,
        active_case_ref: snapshot.mappingCase,
        current_case_container: activeMappingCaseContainer,
        draft_anchors: {
          RH: rhAnchor,
          RL: rlAnchor,
          BH: bhAnchor,
          BL: blAnchor,
        },
        saved_structural_ranges: snapshot.rangesData,
        saved_ranges_for_current_case: snapshot.refreshedSavedRanges,
        saved_structural_events: snapshot.eventsData,
        saved_structural_events_todo: snapshot.eventsTodo,
        formal_bos_events: snapshot.formalBosEvents,
        quick_marker_events: snapshot.quickMarkerEvents,
        last_saved_quick_event: lastSavedQuickEvent,
        quick_events_tracked_this_session: quickEventHistory,
        range_tree: snapshot.treeData,
        hierarchy_audit: snapshot.auditData,
        chart_context: {
          selected_candle: selectedCandle,
          replay_candle: replayCandle,
          replay_index: effectiveReplayIndex,
          replay_time: candleReplayCursorTime,
          camera_mode: cameraMode,
          parent_range_id: selectedParentRangeId || null,
          active_structural_range_id: activeStructuralRangeId || null,
        },
        note: 'Current Mapping export writes a JSON file only; it does not save RH/RL/BH/BL drafts.',
      };
      downloadJsonFile(payload, `current_mapping_${String(symbol)}_${String(snapshot.mappingCase.case_ref || 'case').replace(/[^a-zA-Z0-9_-]+/g,'_')}.json`);
      setHierarchyAudit(snapshot.auditData);
      setMessage('Exported current mapping JSON. Export does not save drafts.');
    } catch (err:any) {
      setMessage(`Current mapping export failed: ${err?.message || err}`);
    }
  };

  const addTypedEventFromCandle = async (
    candle:Candle,
    type:string,
    priceMode:'high'|'low'|'close'='close',
    customName?:string,
    source: InspectorCommitSource = 'manual_mark',
  ) => {
    const price = priceMode === 'high' ? candle.high : priceMode === 'low' ? candle.low : candle.close;
    const activeLow = parseNum(rangeByTf[timeframe]?.low || rangeLow);
    const activeHigh = parseNum(rangeByTf[timeframe]?.high || rangeHigh);
    const pct = (Number.isFinite(activeLow) && Number.isFinite(activeHigh) && activeHigh > activeLow) ? zonePercent(price, activeLow, activeHigh) : null;
    const ev:MapEvent = {
      id: markerIdForCandle(candle, type),
      event_type: type,
      event_name: customName || type,
      time: candle.time,
      price: Number(price.toFixed(2)),
      zone: zoneLabel(pct),
      zone_percent: pct === null ? undefined : Number(pct.toFixed(2)),
      notes: ''
    };
    const nextEvents = upsertMarkerIntoEvents(ev);
    await saveEvent(ev, source);
    if (isRangeAnchorMarker(type)) {
      // v086.12: explicit anchor saves update ONLY the chosen side.
      // Do not resync both high+low from the full event ledger here, because an older
      // backend/legacy low can hijack the range when Josh later saves the high. Evil little goblin.
      if (isRangeHighMarker(type)) {
        const nextHigh = String(Number(candle.high).toFixed(2));
        setRangeHigh(nextHigh);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: nextHigh, low: prev[timeframe]?.low || '' } }));
        mergeRangeWindowTime(candle.time);
      }
      if (isRangeLowMarker(type)) {
        const nextLow = String(Number(candle.low).toFixed(2));
        setRangeLow(nextLow);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low: nextLow } }));
        mergeRangeWindowTime(candle.time);
      }
      await saveActiveRange(nextEvents);
    } else if (isRefHighMarker(type) || isRefLowMarker(type)) {
      await saveActiveRange(nextEvents);
    }
    setMessage(`Marked ${ev.event_name} at ${ev.price} · ${shortTime(ev.time, timeframe)} · saved to backend`);
  };


  const togglePendingMarkerRole = (role:string) => {
    if (!selectedCandle) { setMessage('Click a candle first, then choose events. Revolutionary sequence, apparently.'); return; }
    setPendingMarkerRoles(prev => prev.includes(role) ? prev.filter(x => x !== role) : [...prev, role]);
  };

  const clearPendingMarkerSelection = () => {
    setPendingMarkerRoles([]);
  };

  const savePendingMarkersToNarrative = async () => {
    const candle = selectedCandle;
    if (bundleSaving) { setMessage('Bundle save already running. Double-click ignored.'); return; }
    if (!candle) { setMessage('No candle selected. The machine cannot save air.'); return; }
    if (!pendingMarkerRoles.length) { setMessage('Select at least one event before saving. The save button is not a fortune teller.'); return; }
    setBundleSaving(true);
    const rolesToSave = [...pendingMarkerRoles];
    try {
      for (const role of rolesToSave) {
        await markCandleRole(role, candle, { keepSelection: true, commitSource: 'marker_bundle' });
      }
      setMessage(`Saved ${rolesToSave.length} event${rolesToSave.length === 1 ? '' : 's'} to event ledger · ${shortTime(candle.time, timeframe)}.`);
      setPendingMarkerRoles([]);
    } finally {
      setBundleSaving(false);
    }
  };

  const markCandleRole = async (role:string, candle:Candle, opts?:{keepSelection?:boolean; commitSource?: InspectorCommitSource}) => {
    const commitSource = opts?.commitSource ?? 'manual_mark';
    setCandleMenu(null);
    if (!opts?.keepSelection) setSelectedCandle(candle);
    if (role === 'NONE') { clearSelectedCandleEvents(); return; }
    if (role === 'RANGE_HIGH') return saveRawMarker('HIGH', candle, commitSource);
    if (role === 'RANGE_LOW') return saveRawMarker('LOW', candle, commitSource);
    if (role === 'REF_HIGH_TAKEN' || role === 'REF_LOW_TAKEN') return saveRawMarker('REF', candle, commitSource);
    if (role === 'INTERNAL_SWEEP_HIGH') return addTypedEventFromCandle(candle, 'INTERNAL_SWEEP_HIGH', 'high', undefined, commitSource);
    if (role === 'INTERNAL_SWEEP_LOW') return addTypedEventFromCandle(candle, 'INTERNAL_SWEEP_LOW', 'low', undefined, commitSource);
    if (role === 'EXTERNAL_SWEEP_HIGH') return addTypedEventFromCandle(candle, 'EXTERNAL_SWEEP_HIGH', 'high', undefined, commitSource);
    if (role === 'EXTERNAL_SWEEP_LOW') return addTypedEventFromCandle(candle, 'EXTERNAL_SWEEP_LOW', 'low', undefined, commitSource);
    if (role === 'INTERNAL_REJECTION_HIGH') return addTypedEventFromCandle(candle, 'INTERNAL_REJECTION_HIGH', 'high', undefined, commitSource);
    if (role === 'INTERNAL_REJECTION_LOW') return addTypedEventFromCandle(candle, 'INTERNAL_REJECTION_LOW', 'low', undefined, commitSource);
    if (role === 'EXTREME_DISCOUNT_LOW') return addTypedEventFromCandle(candle, 'EXTREME_DISCOUNT_LOW', 'low', undefined, commitSource);
    if (role === 'BELOW_FAIR_PRICE_LOW') return addTypedEventFromCandle(candle, 'BELOW_FAIR_PRICE_LOW', 'low', undefined, commitSource);
    if (role === 'ABOVE_FAIR_PRICE_HIGH') return addTypedEventFromCandle(candle, 'ABOVE_FAIR_PRICE_HIGH', 'high', undefined, commitSource);
    if (role === 'EXTREME_PREMIUM_HIGH') return addTypedEventFromCandle(candle, 'EXTREME_PREMIUM_HIGH', 'high', undefined, commitSource);
    if (role === 'RECLAIM_HIGH') return addTypedEventFromCandle(candle, 'RECLAIM_HIGH', 'close', undefined, commitSource);
    if (role === 'RECLAIM_LOW') return addTypedEventFromCandle(candle, 'RECLAIM_LOW', 'close', undefined, commitSource);
    if (role === 'BOS_UP') return addTypedEventFromCandle(candle, 'BOS_UP', 'close', undefined, commitSource);
    if (role === 'BOS_DOWN') return addTypedEventFromCandle(candle, 'BOS_DOWN', 'close', undefined, commitSource);
    if (role === 'CHOCH_UP') return addTypedEventFromCandle(candle, 'CHOCH_UP', 'close', undefined, commitSource);
    if (role === 'CHOCH_DOWN') return addTypedEventFromCandle(candle, 'CHOCH_DOWN', 'close', undefined, commitSource);
    if (role === 'P1') return addTypedEventFromCandle(candle, 'P1', 'close', undefined, commitSource);
    if (role === 'P2') return addTypedEventFromCandle(candle, 'P2', 'close', undefined, commitSource);
    if (role === 'P3') return addTypedEventFromCandle(candle, 'P3', 'close', undefined, commitSource);
    if (role === 'CUSTOM') return addTypedEventFromCandle(candle, eventType, 'close', eventName || eventType, commitSource);
    return addTypedEventFromCandle(candle, role, markerPriceMode(role), markerLabel(role), commitSource);
  };

  const updateEvent = (id:string, patch:Partial<MapEvent>) => {
    setEventsForTf(prev=>prev.map(e=>e.id===id ? { ...e, ...patch } : e));
  };

  const finishEventDrag = async (ev:MapEvent) => {
    await saveEvent(ev, 'event_drag');
    setMessage(`Updated ${ev.event_name} · ${ev.price} · ${ev.zone} · ${shortTime(ev.time, timeframe)}`);
  };

  const goToDate = () => {
    if (!jumpDate) { setMessage('Pick a date first. Time travel needs a destination, tragically.'); return; }
    setFitToken(x=>x+1);
  };

  const loadTimeline = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/market-gps/W1/timeline?symbol=${encodeURIComponent(symbol)}`);
      const data = await res.json();
      setGpsTimeline(Array.isArray(data?.nodes) ? data.nodes : []);
    } catch (err) {
      setGpsTimeline([]);
    }
  };

  const applyPlaybackFrame = (frame: PlaybackFrame | null, index = playbackIndex) => {
    if (!frame) return;
    const [phaseNum, ...partBits] = String(frame.phase || 'P1_RETEST').split('_');
    const phasePart = partBits.join('_') || 'RETEST';
    setReplayMode(true);
    setPlaybackIndex(index);
    setGpsMode('active');
    setGpsStoryId(String(frame.story_id || playbackStoryId || ''));
    setGpsParentMode(frame.parent_context_mode || 'WEEKLY_ACTIVE_PARENT');
    setGpsDailyRangeStatus(frame.daily_range_status || 'DAILY_RANGE_ACTIVE');
    setGpsLifecycleState(frame.lifecycle_state || 'EXPANSION');
    setGpsPhaseNumber(phaseNum || 'P1');
    setGpsPhasePart(phasePart);
    setGpsProfileType(frame.profile_type || 'NO_RECLAIM_CONTINUATION_PROFILE');
    setGpsObjective(frame.objective_code || 'DAILY_PREMIUM');
    setGpsCurrentZone(frame.current_zone || 'DAILY_DISCOUNT');
    setGpsTriggerEvent(frame.trigger_event || 'PLAYBACK_FRAME');
    setGpsExpectedNextEvent(frame.expected_next_event || 'PENDING_MARKET_DELIVERY');
    setGpsInvalidationCondition(frame.invalidation_condition || 'MANUAL_INVALIDATION_REQUIRED');
    setGps({
      ok: true,
      status: `PLAYBACK_FRAME_${index + 1}`,
      symbol,
      timeframe: 'W1',
      coordinates: {
        story_anchor: `PLAYBACK_STORY_${frame.story_id}`,
        anchor_class: 'PLAYBACK',
        chapter: frame.trigger_event,
        parent_context_mode: frame.parent_context_mode,
        daily_range_status: frame.daily_range_status,
        lifecycle_state: frame.lifecycle_state,
        phase: phaseNum || 'P1',
        phase_part: phasePart,
        profile_type: frame.profile_type,
        objective: frame.objective_code,
        current_zone: frame.current_zone,
        last_updated: frame.frame_timestamp,
      }
    });
    setMessage(`Replay frame ${index + 1}/${playbackFrames.length || '?'} · ${frame.lookahead_result || 'RAW'} · ${frame.trigger_event}`);
  };

  const setPlaybackFrameIndex = (index:number) => {
    const safe = clamp(index, 0, Math.max(0, playbackFrames.length - 1));
    applyPlaybackFrame(playbackFrames[safe] || null, safe);
  };

  const loadPlayback = async (storyId = playbackStoryId) => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mos/playback/${encodeURIComponent(storyId)}?evaluate=true`);
      const data = await res.json();
      const frames = Array.isArray(data?.frames) ? data.frames : [];
      setPlaybackFrames(frames);
      setPlaybackIndex(0);
      setPlaybackPlaying(false);
      setReplayMode(true);
      if (frames[0]) setTimeout(()=>applyPlaybackFrame(frames[0], 0), 0);
      setMessage(frames.length ? `Loaded ${frames.length} replay frames for story ${storyId}.` : `No replay frames for story ${storyId}.`);
    } catch (err:any) {
      setPlaybackFrames([]);
      setPlaybackIndex(0);
      setPlaybackPlaying(false);
      setMessage(`Playback load failed: ${err?.message || err}`);
    }
  };

  const seedCase03Frames = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mos/seed/case-03-frames`, { method:'POST' });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || data?.detail || 'Seed failed');
      setPlaybackStoryId('3');
      await loadPlayback('3');
      setMessage(`Seeded Case 03 with ${data.frames || 0} frames. The ledger has rent money now.`);
    } catch (err:any) {
      setMessage(`Case 03 seed failed: ${err?.message || err}`);
    }
  };

  const extendStructuralReplayHorizon = async (
    targetTf = String(timeframe).toUpperCase(),
  ): Promise<{ merged: Candle[]; added: number } | null> => {
    const baseWindow = structuralDataLoadWindowRef.current;
    if (!baseWindow?.end || structuralReplayExtendInFlightRef.current) return null;
    const chunkDays = structuralReplayChunkDays(targetTf);
    const chunkStart = addIsoDays(baseWindow.end, 1);
    const nextWindow = extendStructuralDataLoadWindow(baseWindow, chunkDays);
    if (!nextWindow) return null;
    structuralReplayExtendInFlightRef.current = true;
    try {
      const fetchWindow = { start: chunkStart, end: nextWindow.end };
      let incoming: Candle[] = [];
      const r = await fetchJsonWithTimeout(buildCandleFetchUrl(symbol, targetTf, fetchWindow, false));
      if (r?.ok && r.candles?.length) {
        incoming = parseCandleRows(r.candles);
        void persistRemoteCandlesToCache(symbol, targetTf, r, 'replay_extend').catch(() => {});
      }
      incoming = filterCandlesToLoadWindow(incoming, {
        start: chunkStart,
        end: nextWindow.end,
        label: 'replay-extend',
      });
      if (!incoming.length) return null;
      const merged = mergeCandleSeriesByTime(candlesRef.current, incoming);
      structuralDataLoadWindowRef.current = nextWindow;
      setChartCandles(merged);
      candleCountRef.current = merged.length;
      return { merged, added: incoming.length };
    } finally {
      structuralReplayExtendInFlightRef.current = false;
    }
  };

  const requestTradingViewReplayStepFit = (cursorTime: string | null | undefined) => {
    if (chartRendererRef.current !== 'tradingview') return;
    if (!tradingViewMappingInputEnabledRef.current && !candleReplayModeRef.current) return;
    if (!cursorTime) return;
    const rows = candlesRef.current;
    if (!rows.length) return;
    const tf = activeTimeframeRef.current;
    const target = fxtmTimeToTradingViewTime(cursorTime, tf);
    if (!target) return;
    tradingViewReplayFitTokenRef.current += 1;
    setTradingViewReplayStepFitRequest({
      token: tradingViewReplayFitTokenRef.current,
      target,
    });
  };

  const stepReplayBackOne = (): boolean => {
    const rows = candlesRef.current;
    if (!rows.length) return false;
    const idx = candleReplayMode && candleReplayCursorTime
      ? candleIndexAtOrBefore(rows, candleReplayCursorTime)
      : clamp(candleReplayIndex, 0, rows.length - 1);
    if (idx <= 0) {
      setMessage('Already at first loaded candle.');
      return false;
    }
    const prevIdx = idx - 1;
    const c = rows[prevIdx];
    setCandleReplayMode(true);
    setCandleReplayIndex(prevIdx);
    setCandleReplayCursorTime(c.time);
    setSelectedCandle(c);
    setSelectedCandlePoint({ price: Number(c.close.toFixed(2)) });
    setPendingMarkerRoles([]);
    setMessage(`Replay ${prevIdx + 1}/${rows.length} · ${shortTime(c.time, timeframe)}`);
    requestTradingViewReplayStepFit(c.time);
    return true;
  };

  const stepReplayForwardOne = async (): Promise<boolean> => {
    const rows = candlesRef.current;
    if (!rows.length) return false;
    const idx = candleReplayMode && candleReplayCursorTime
      ? candleIndexAtOrBefore(rows, candleReplayCursorTime)
      : clamp(candleReplayIndex, 0, rows.length - 1);
    if (idx < rows.length - 1) {
      const nextIdx = idx + 1;
      const c = rows[nextIdx];
      setCandleReplayMode(true);
      setCandleReplayIndex(nextIdx);
      setCandleReplayCursorTime(c.time);
      setSelectedCandle(c);
      setSelectedCandlePoint({ price: Number(c.close.toFixed(2)) });
      setPendingMarkerRoles([]);
      setReplaySelectBarMode(false);
      setReplayStartMenuOpen(false);
      setMessage(`Candle replay ${nextIdx + 1}/${rows.length} · ${shortTime(c.time, timeframe)} · H ${c.high.toFixed(2)} L ${c.low.toFixed(2)}`);
      requestTradingViewReplayStepFit(c.time);
      return true;
    }
    const hasStructural = !!(activeStructuralRangeIdRef.current || selectedParentRangeIdRef.current);
    if (!hasStructural || !structuralDataLoadWindowRef.current) {
      setMessage(replayPlayForwardStatusMessage('no-loaded-candles-ahead'));
      return false;
    }
    setMessage(replayPlayForwardStatusMessage('loading-ahead'));
    const result = await extendStructuralReplayHorizon();
    if (!result?.added) {
      setMessage(replayPlayForwardStatusMessage('no-loaded-candles-ahead'));
      return false;
    }
    const nextIdx = Math.min(idx + 1, result.merged.length - 1);
    const c = result.merged[nextIdx];
    setCandleReplayMode(true);
    setCandleReplayIndex(nextIdx);
    if (c) {
      setCandleReplayCursorTime(c.time);
      setSelectedCandle(c);
      setSelectedCandlePoint({ price: Number(c.close.toFixed(2)) });
    }
    setMessage(`Replay extended · ${nextIdx + 1}/${result.merged.length} · ${shortTime(c?.time || '', timeframe)}`);
    if (c?.time) requestTradingViewReplayStepFit(c.time);
    return true;
  };

  const setCandleReplayFrame = (index:number) => {
    if (!candles.length) return;
    const safe = clamp(index, 0, candles.length - 1);
    setCandleReplayMode(true);
    setCandleReplayIndex(safe);
    const c = candles[safe];
    setCandleReplayCursorTime(c.time);
    setSelectedCandle(c);
    setPendingMarkerRoles([]);
    setReplaySelectBarMode(false);
    setReplayStartMenuOpen(false);
    // v082: replay stepping must NOT mutate jumpDate or fitToken.
    // Those controls intentionally reset/recenter the map, which made every replay step zoom out.
    // Replay cursor is data state; chart camera is user state. Keep them decoupled.
    setMessage(`Candle replay ${safe + 1}/${candles.length} · ${shortTime(c.time, timeframe)} · H ${c.high.toFixed(2)} L ${c.low.toFixed(2)}`);
    requestTradingViewReplayStepFit(c.time);
  };

  // v087.22b: chart scrub passes a candle timestamp, not an index.
  // Keep this wrapper separate so MapStudio never crashes if the callback is invoked from the chart.
  const setCandleReplayFrameByTime = (time:string) => {
    if (!candles.length || !time) return;
    const idx = candleIndexAtOrBefore(candles, time);
    const safe = clamp(idx, 0, candles.length - 1);
    const c = candles[safe];
    if (!c) return;
    setCandleReplayMode(true);
    setCandleReplayIndex(safe);
    setCandleReplayCursorTime(c.time);
    setSelectedCandle(c);
    setPendingMarkerRoles([]);
    setReplaySelectBarMode(false);
    setReplayStartMenuOpen(false);
    setMessage(`Replay scrubbed to ${shortTime(c.time, timeframe)} · ${safe + 1}/${candles.length}`);
  };

  const applyExplorerRowSelection = (range: any, opts?: { routeInspector?: boolean }) => {
    const id = String(range?.range_id || range?.id || '');
    if (!id) return;
    tradingViewSuppressedHierarchyRangeIdRef.current = '';
    const rangeLayer = normalizeStructureLayer(range?.structure_layer || range?.layer);
    const neededParentLayer = expectedParentStructureLayer(structureLayer);

    if (rangeLayer && neededParentLayer && rangeLayer === neededParentLayer && rangeLayer !== structureLayer) {
      setSelectedParentRangeId(id);
      setRangeLineHiddenByCase((prev) => {
        const key = activeCaseDisplayId || 'global';
        const current = new Set(prev[key] || []);
        current.delete(id);
        return { ...prev, [key]: Array.from(current) };
      });
      const high = range.range_high_price ?? range.range_high;
      const low = range.range_low_price ?? range.range_low;
      const hint = buildRangeSelectionHint({
        rangeId: id,
        structureLayer: rangeLayer,
        rangeScope: normalizeRangeScope(range?.range_scope),
        rangeHigh: high,
        rangeLow: low,
      });
      if (opts?.routeInspector === false) {
        setInspectorContextHint(hint);
      } else {
        applyInspectorRoute(routeInspectorForRangeSelection(), hint);
      }
      setMessage(`Parent context: ${rangeLayer} #${id} → mapping ${structureLayer}.`);
      return;
    }

    selectSavedStructuralRange(range, opts);
  };

  const jumpToStructuralRange = (range: any) => {
    const id = String(range?.range_id || range?.id || '');
    if (!id) return;
    tradingViewSuppressedHierarchyRangeIdRef.current = '';
    skipSavedReplayHydrateRef.current = true;
    const rangeLayer = normalizeStructureLayer(range?.structure_layer || range?.layer);
    const neededParentLayer = expectedParentStructureLayer(structureLayer);
    const isParentOnlyPick = !!(
      rangeLayer && neededParentLayer && rangeLayer === neededParentLayer && rangeLayer !== structureLayer
    );
    const { start: startRaw } = rangeWindowFieldsFromSavedRange(range);
    const startStr = startRaw || '';
    const chartTf = resolveRangeChartTimeframe(range, timeframe);

    applyExplorerRowSelection(range, { routeInspector: false });

    if (isParentOnlyPick) {
      if (chartRenderer === 'tradingview') {
        void navigateStructuralChartContext({
          targetTf: chartTf,
          range,
          reason: 'tradingview-explorer-parent-jump-fit',
        }).then(() => {
          if (startStr) setJumpDate(startStr.slice(0, 10));
        });
        return;
      }
      const fitWindow = structuralRangeFitDomain(range, candles);
      pendingCameraIntentRef.current = {
        intent: 'FIT_STRUCTURAL_RANGE',
        targetTime: startStr || selectedCandle?.time || candleReplayCursorTime || replayCandle?.time || null,
        reason: 'explorer-parent-context',
        fitWindow,
        contextRangeId: id,
      };
      if (startStr) {
        setCandleReplayFrameByTime(startStr);
        setJumpDate(startStr.slice(0, 10));
      }
      scheduleDeferredCamera('FIT_STRUCTURAL_RANGE', startStr || null, 'explorer-parent-context', fitWindow);
      return;
    }

    void navigateStructuralChartContext({
      targetTf: chartTf,
      range,
      reason: 'explorer-jump-fit',
    }).then(() => {
      if (startStr) setJumpDate(startStr.slice(0, 10));
    });
  };

  const loadRangeAuditOnChart = (target: RangeAuditViewTarget) => {
    const chartTf = String(target.chart_timeframe || target.source_timeframe || timeframe).toUpperCase();
    const layer = normalizeStructureLayer(target.structure_layer) || structureLayer;
    const srcTf = String(target.source_timeframe || sourceTimeframe).toUpperCase();
    const startStr = String(target.range_start_time || target.replay_until_time || '');
    const endStr = String(target.range_end_time || target.replay_until_time || startStr || '');
    const rhText = String(Number(target.rh.toFixed(2)));
    const rlText = String(Number(target.rl.toFixed(2)));

    if (layer && layer !== structureLayer) setStructureLayer(layer);
    if (srcTf && srcTf !== sourceTimeframe) setSourceTimeframe(srcTf);

    setRhAnchor({ price: rhText, time: startStr || endStr || '', candle: null });
    setRlAnchor({ price: rlText, time: endStr || startStr || '', candle: null });
    setRangeHigh(rhText);
    setRangeLow(rlText);
    if (startStr || endStr) {
      setRangeWindow({ start: startStr || endStr, end: endStr || startStr });
      setRangeWindowByTf(prev => ({
        ...prev,
        [chartTf]: { start: startStr || endStr, end: endStr || startStr },
      }));
    }

    const fitRange = {
      range_high_price: target.rh,
      range_low_price: target.rl,
      range_high: target.rh,
      range_low: target.rl,
      range_start_time: startStr || null,
      range_end_time: endStr || null,
      range_high_time: startStr || null,
      range_low_time: endStr || null,
      structure_layer: layer,
    };
    const needsTfSwitch = chartTf !== String(timeframe).toUpperCase();
    const fitWindow = structuralRangeFitDomain(fitRange, needsTfSwitch ? [] : candles);

    if (needsTfSwitch) {
      pendingCameraIntentRef.current = {
        intent: 'FIT_STRUCTURAL_RANGE',
        targetTime: startStr || selectedCandle?.time || candleReplayCursorTime || replayCandle?.time || null,
        reason: 'audit-jump-fit',
        fitWindow,
      };
      activeTimeframeRef.current = chartTf;
      setTimeframe(chartTf);
    } else {
      if (startStr) {
        setCandleReplayFrameByTime(startStr);
        setJumpDate(startStr.slice(0, 10));
      }
      if (fitWindow) {
        applyCameraCommand('FIT_STRUCTURAL_RANGE', startStr || null, 'audit-jump-fit', undefined, fitWindow);
      } else if (startStr) {
        applyCameraCommand('PRESERVE_OR_NEAREST_TIME', startStr, 'audit-jump');
      }
    }

    const label = [
      target.kind === 'suggestion' ? 'Range candidate' : 'Confirmed range',
      `RH ${rhText}`,
      `RL ${rlText}`,
      target.detector_version || '—',
      target.replay_until_time || '—',
      target.lifecycle_state || '—',
      target.boundary_selection_reason || '—',
    ].join(' · ');
    setMessage(`Audit view loaded · ${label}`);
  };

  const activateMappingGap = (gap: MappingGap) => {
    void startGuidedChildMapping(gap.parentRange, { coverage: gap.coverage });
  };

  const handleCampaignContinue = async () => {
    const task = campaignStatus.nextTask;
    if (task.task === 'CAMPAIGN_COMPLETE' || !task.gap) {
      setMessage('Campaign complete for the selected year scope.');
      return;
    }
    const ok = await startGuidedChildMapping(task.gap.parentRange, { coverage: task.gap.coverage });
    if (!ok) return;
    setMarkWorkspaceMode('htf');
    setRightDeckTab('campaign');
    setNavOverlayPanelOpen(true);
    setToolMode('select');
    setChartDrawTool('off');
    autoRangeSaveAttemptRef.current = '';
  };

  const editStructuralRangeFromTree = (range: any) => {
    selectSavedStructuralRange(range);
    setMessage(`Editing range #${range?.range_id || range?.id} in Structural Map.`);
  };

  const relinkStructuralRange = async (range: any) => {
    const id = String(range?.range_id || range?.id || '');
    if (!id) return;
    const layer = normalizeStructureLayer(range.structure_layer || range.layer);
    const scope = normalizeRangeScope(range.range_scope);
    const parentLayer = layer ? (scope === 'MINOR' ? layer : expectedParentStructureLayer(layer)) : null;
    if (!layer || (scope === 'MAJOR' && !parentLayer)) return;
    const candidates = parentLayerCandidates(layer, savedStructuralRanges, scope);
    const hint = candidates.slice(0, 8).map(formatStructuralRangeOptionLabel).join('\n');
    const raw = window.prompt(
      `Relink #${id} ${layer} ${scope} to ${parentLayer} MAJOR parent id.\n\nCandidates:\n${hint || '(none)'}\n\nEnter parent range id or leave empty for orphan:`,
      String(range?.parent_range_id || ''),
    );
    if (raw === null) return;
    const trimmed = raw.trim();
    const parentId = trimmed ? Number(trimmed) : null;
    if (trimmed && !Number.isFinite(parentId)) {
      setMessage('Parent id must be a number.');
      return;
    }
    try {
      await inspectorCommitOrThrow({
        baseUrl: BASE_URL,
        kind: 'structural_range_reparent',
        source: 'range_reparent',
        payload: { child_range_id: Number(id), parent_range_id: parentId },
      });
      await refreshSavedRangesForCurrentCase();
      try { await refreshHierarchyAudit(); } catch {}
      setMessage(`Relinked #${id} → parent ${parentId ?? 'none'}.`);
    } catch (err: any) {
      setMessage(`Relink failed: ${err?.message || err}`);
    }
  };

  const archiveStructuralRange = async (range: any) => {
    const id = String(range?.range_id || range?.id || '');
    if (!id) return;
    const childCount = countRangeDescendants(id, savedStructuralRanges);
    const ok = window.confirm(
      childCount > 0
        ? 'This range has child ranges. Archiving may orphan or hide children.\n\nArchive anyway?'
        : `Archive range #${id}?`,
    );
    if (!ok) return;
    try {
      await inspectorCommitOrThrow({
        baseUrl: BASE_URL,
        kind: 'structural_range_patch',
        source: 'range_archive',
        pathParams: { rangeId: id },
        payload: { status: 'ABANDONED' },
      });
      if (String(activeStructuralRangeId) === id) setActiveStructuralRangeId('');
      await refreshSavedRangesForCurrentCase();
      try { await refreshHierarchyAudit(); } catch {}
      setMessage(`Archived range #${id}.`);
    } catch (err: any) {
      setMessage(`Archive failed: ${err?.message || err}`);
    }
  };

  const hiddenRangeLineIdSet = useMemo(
    () => new Set(rangeLineHiddenByCase[caseLineHiddenKey] || []),
    [rangeLineHiddenByCase, caseLineHiddenKey],
  );
  const isRangeLineVisible = (rangeId: string) => !allRangeGuideLinesHidden && !hiddenRangeLineIdSet.has(String(rangeId));
  const toggleRangeLineVisibility = (rangeId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const id = String(rangeId);
    setRangeLineHiddenByCase((prev) => {
      const current = new Set(prev[caseLineHiddenKey] || []);
      if (current.has(id)) {
        current.delete(id);
        setAllRangeGuideLinesHiddenByCase((gate) => ({ ...gate, [caseLineHiddenKey]: false }));
      } else {
        current.add(id);
      }
      return { ...prev, [caseLineHiddenKey]: Array.from(current) };
    });
  };
  const showAllRangeLines = () => {
    setAllRangeGuideLinesHiddenByCase((prev) => ({ ...prev, [caseLineHiddenKey]: false }));
    setRangeLineHiddenByCase((prev) => ({ ...prev, [caseLineHiddenKey]: [] }));
  };
  const hideAllRangeLines = () => {
    const ids = savedStructuralRanges.map((r:any) => String(r.range_id || r.id)).filter(Boolean);
    setAllRangeGuideLinesHiddenByCase((prev) => ({ ...prev, [caseLineHiddenKey]: true }));
    setRangeLineHiddenByCase((prev) => ({ ...prev, [caseLineHiddenKey]: ids }));
  };

  const renderExplorerActiveActions = (range: any) => (
    <details
      className="explorerTreeActionMenu"
      onClick={(event) => event.stopPropagation()}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <summary className="explorerTreeActionMenuBtn" aria-label="Row actions">⋯</summary>
      <div className="explorerTreeActionMenuPanel" role="menu">
        <button type="button" role="menuitem" onClick={() => editStructuralRangeFromTree(range)}>Edit</button>
        <button type="button" role="menuitem" onClick={() => void relinkStructuralRange(range)}>Relink</button>
        <button type="button" role="menuitem" className="dangerTiny" onClick={() => void archiveStructuralRange(range)}>Archive</button>
      </div>
    </details>
  );

  const renderExplorerTreeNodes = (nodes: CaseHierarchyTreeNode[]): React.ReactNode => nodes.flatMap((node) => {
    const range = node.range;
    const id = String(range?.range_id || range?.id || '');
    if (!id) return [];
    const layer = normalizeStructureLayer(range?.structure_layer || range?.layer) || 'WEEKLY';
    const layerKey = layer.toLowerCase();
    const isActive = id === String(activeStructuralRangeId);
    const isParentContext = id === String(selectedParentRangeId) && (
      (rangeScope === 'MINOR' && normalizeStructureLayer(range?.structure_layer || range?.layer) === structureLayer && isRangeMajor(range))
      || (rangeScope === 'MAJOR' && expectedParentStructureLayer(structureLayer) === layer)
    );
    const lines = formatExplorerCompactRowLabel(range, node.children.length, node.childCountLabel);
    const hasChildren = node.children.length > 0;
    const collapsed = hierarchyCollapsedIds.includes(id);
    const lineVisible = isRangeLineVisible(id);
    const toggleCollapsed = (e: React.MouseEvent) => {
      e.stopPropagation();
      setHierarchyCollapsedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    };
    return [
      <div
        key={id}
        className={`explorerTreeRow ${isActive ? 'active' : ''} ${isParentContext ? 'parentContext' : ''} ${node.depth > 0 ? 'isChild' : ''}`}
        style={{ ['--tree-depth' as string]: node.depth }}
      >
        {hasChildren ? (
          <button type="button" className="explorerTreeToggle" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? '▶' : '▼'}
          </button>
        ) : <span className="explorerTreeToggle spacer" />}
        <button
          type="button"
          className={`explorerLineToggle${lineVisible ? ' on' : ' off'}`}
          title={lineVisible ? 'Hide RH/RL guide lines on chart' : 'Show RH/RL guide lines on chart'}
          onClick={(e) => toggleRangeLineVisibility(id, e)}
        >
          {lineVisible ? 'Lines' : 'Hide'}
        </button>
        <span className={`explorerLayerDot explorerLayerDot-${layerKey}`} title={layer} />
        <button type="button" className="explorerTreeRowMain" title={lines.title} onClick={() => jumpToStructuralRange(range)}>
          <span className={`explorerTreeLine1 hierarchyLayer-${layerKey}`}>{lines.label}</span>
        </button>
        {isActive && renderExplorerActiveActions(range)}
      </div>,
      ...(collapsed ? [] : renderExplorerTreeNodes(node.children)),
    ];
  });

  const renderExplorerOrphanRows = () => caseHierarchyForest.orphans.map((range:any) => {
    const id = String(range.range_id || range.id);
    const layer = normalizeStructureLayer(range.structure_layer || range.layer) || 'WEEKLY';
    const layerKey = layer.toLowerCase();
    const isActive = id === String(activeStructuralRangeId);
    const lines = formatExplorerCompactRowLabel(range, 0);
    const lineVisible = isRangeLineVisible(id);
    return (
      <div key={`orphan-${id}`} className={`explorerTreeRow orphan ${isActive ? 'active' : ''}`}>
        <span className="explorerTreeToggle spacer" />
        <button
          type="button"
          className={`explorerLineToggle${lineVisible ? ' on' : ' off'}`}
          title={lineVisible ? 'Hide RH/RL guide lines on chart' : 'Show RH/RL guide lines on chart'}
          onClick={(e) => toggleRangeLineVisibility(id, e)}
        >
          {lineVisible ? 'Lines' : 'Hide'}
        </button>
        <span className={`explorerLayerDot explorerLayerDot-${layerKey}`} title={layer} />
        <button type="button" className="explorerTreeRowMain" title={lines.title} onClick={() => jumpToStructuralRange(range)}>
          <span className={`explorerTreeLine1 hierarchyLayer-${layerKey}`}>{lines.label}</span>
        </button>
        {isActive && renderExplorerActiveActions(range)}
      </div>
    );
  });

  const hierarchyBranchIds = useMemo(
    () => collectHierarchyBranchIds(caseHierarchyForest.roots),
    [caseHierarchyForest.roots],
  );

  const structuralExplorerPanelEl = (scrollClass = 'explorerTreeScroll') => (
    <div className="structuralExplorerPanel">
      <div className="structuralExplorerHeader">
        <b>Market Memory Navigator</b>
        <span>{explorerTreeRanges.length} shown · {savedStructuralRanges.length} total</span>
      </div>
      <div className="explorerModeRow">
        <span className="explorerOverlayLabel">Mode</span>
        <button
          type="button"
          className={`explorerModeBtn ${explorerMappingMode === 'htf' ? 'active' : ''}`}
          onClick={() => setExplorerMappingMode('htf')}
        >
          HTF Memory
        </button>
        <button
          type="button"
          className={`explorerModeBtn ${explorerMappingMode === 'ltf' ? 'active' : ''}`}
          onClick={() => setExplorerMappingMode('ltf')}
        >
          LTF Fill
        </button>
      </div>
      <p className="explorerModeHint mutedSmall">
        {explorerMappingMode === 'htf'
          ? 'Full hierarchy tree (Macro → Micro). Gap queue lists missing HTF MAJOR children only.'
          : 'Full hierarchy tree. Gap queue lists missing Intraday / Micro MAJOR children.'}
      </p>
      <div className="explorerYearFilterRow">
        <label className="explorerYearLabel">Year
          <select value={explorerYearFilter} onChange={e => setExplorerYearFilter(e.target.value)}>
            <option value="all">All</option>
            {explorerYearOptions.map(y => <option key={y} value={String(y)}>{y}</option>)}
          </select>
        </label>
      </div>
      {mappingGaps.length > 0 && (
        <div className={`explorerGapQueue ${gapQueueOpen ? 'open' : 'collapsed'}`}>
          <button
            type="button"
            className="explorerGapHeader"
            onClick={() => setGapQueueOpen(!gapQueueOpen)}
            aria-expanded={gapQueueOpen}
          >
            <span className="explorerGapHeaderMain">
              <span className="explorerGapToggle" aria-hidden="true">{gapQueueOpen ? '▼' : '▶'}</span>
              <b>Gap queue</b>
            </span>
            <span>{mappingGaps.length} missing</span>
          </button>
          {gapQueueOpen && (
            <div className="explorerGapList">
              {mappingGaps.slice(0, 12).map((gap) => (
                <button
                  key={`${gap.parentLayer}-${gap.parentId}-${gap.expectedChildLayer}`}
                  type="button"
                  className="explorerGapBtn"
                  onClick={() => activateMappingGap(gap)}
                >
                  {gap.label}
                </button>
              ))}
              {mappingGaps.length > 12 && (
                <span className="mutedSmall">+ {mappingGaps.length - 12} more in tree</span>
              )}
            </div>
          )}
        </div>
      )}
      <div className="explorerTreeControls">
        <button type="button" className="hierarchyCtrlBtn" onClick={() => refreshSavedRangesForCurrentCase().catch((err:any)=>setMessage(`Load saved ranges failed: ${err?.message || err}`))}>Refresh</button>
        <button type="button" className="hierarchyCtrlBtn" onClick={() => setHierarchyCollapsedIds([])}>Expand All</button>
        <button type="button" className="hierarchyCtrlBtn" onClick={() => setHierarchyCollapsedIds(hierarchyBranchIds)}>Collapse All</button>
        <button type="button" className="hierarchyCtrlBtn" onClick={showAllRangeLines} title="Show RH/RL guide lines for all ranges">Lines All</button>
        <button type="button" className="hierarchyCtrlBtn" onClick={hideAllRangeLines} title="Hide all range guide lines on chart">Lines None</button>
        <button
          type="button"
          className={`hierarchyCtrlBtn${chartMappingFocusMode ? ' active' : ''}`}
          onClick={() => setChartMappingFocusMode((v) => !v)}
          title="Focus Mode: candle-first Y-scale with ghost parent/ancestor RH/RL"
        >
          Focus {chartMappingFocusMode ? 'ON' : 'OFF'}
        </button>
        {chartMappingFocusMode && (
          <button
            type="button"
            className={`hierarchyCtrlBtn${chartFocusShowAllRanges ? ' active' : ''}`}
            onClick={() => setChartFocusShowAllRanges((v) => !v)}
            title="Show all structural layers while keeping candle-first Y-scale"
          >
            All Layers
          </button>
        )}
      </div>
      <div className={scrollClass}>
        {!explorerTreeRanges.length && <div className="caseLedgerEmpty">{savedStructuralRanges.length ? 'No ranges match this filter.' : 'No saved structural ranges for this case yet.'}</div>}
        {!!caseHierarchyForest.roots.length && renderExplorerTreeNodes(caseHierarchyForest.roots)}
        {!!caseHierarchyForest.orphans.length && <>
          <div className="hierarchyOrphanHeader">Unlinked / Orphans</div>
          {renderExplorerOrphanRows()}
        </>}
      </div>
    </div>
  );

  const jumpCandleReplayLatest = () => {
    if (!candles.length) return;
    setCandleReplayFrame(candles.length - 1);
  };

  const toggleBarReplay = () => {
    if (chartRenderer === 'tradingview' && !tradingViewExplicitReplayMode) {
      setTradingViewExplicitReplayMode(true);
      setCandleReplayMode(true);
      setCandleReplayPlaying(false);
      setToolMode('scrub');
      setReplaySelectBarMode(true);
      if (!candleReplayCursorTime && candles.length) {
        const ctxTime = rhAnchor.time || rlAnchor.time || tradingViewSelectedCandle?.time || selectedCandle?.time || null;
        if (ctxTime) setCandleReplayFrameByTime(ctxTime);
        else setCandleReplayFrame(0);
      }
      setMessage('TradingView Bar Replay on — visible candles stop at the replay cursor.');
      return;
    }
    if (candleReplayMode) {
      setCandleReplayPlaying(false);
      setCandleReplayMode(false);
      setTradingViewExplicitReplayMode(false);
      setTradingViewReplayStepFitRequest(null);
      setReplaySelectBarMode(false);
      setReplayStartMenuOpen(false);
      if (chartRendererRef.current === 'tradingview') {
        restoreLiveMemoryCameraAfterReplay();
      }
      setMessage('Bar Replay off.');
      return;
    }
    setCandleReplayMode(true);
    setTradingViewExplicitReplayMode(chartRenderer === 'tradingview');
    setCandleReplayPlaying(false);
    setToolMode('scrub');
    setReplaySelectBarMode(true);
    if (!candleReplayCursorTime && candles.length) {
      const ctxTime = rhAnchor.time || rlAnchor.time || selectedCandle?.time || null;
      if (ctxTime) setCandleReplayFrameByTime(ctxTime);
      else setCandleReplayFrame(0);
    }
    setMessage('Bar Replay on — click a candle or use Select bar to scrub.');
  };

  const pickRandomReplayBar = () => {
    if (!candles.length) return;
    const idx = Math.floor(Math.random() * candles.length);
    setCandleReplayFrame(idx);
    setReplaySelectBarMode(false);
    setReplayStartMenuOpen(false);
  };

  const jumpReplayToDate = () => {
    if (!jumpDate || !candles.length) {
      setMessage('Pick a date first (Case panel or navigator).');
      return;
    }
    const target = candles.find((c) => String(c.time).slice(0, 10) >= jumpDate) || candles[candles.length - 1];
    setCandleReplayFrameByTime(target.time);
    setReplaySelectBarMode(false);
    setReplayStartMenuOpen(false);
  };

  const exitBarReplayToLive = () => {
    setCandleReplayPlaying(false);
    setCandleReplayMode(false);
    setTradingViewExplicitReplayMode(false);
    setTradingViewReplayStepFitRequest(null);
    setReplaySelectBarMode(false);
    setReplayStartMenuOpen(false);
    if (chartRendererRef.current === 'tradingview') {
      restoreLiveMemoryCameraAfterReplay();
      setMessage('Replay ended — restored timeframe memory.');
    } else if (candles.length) {
      jumpCandleReplayLatest();
      setMessage('Replay ended — showing latest candles.');
    } else {
      setMessage('Replay ended.');
    }
  };

  const toggleCandleReplayPlay = async () => {
    if (!candles.length) return;
    if (candleReplayPlaying) {
      setCandleReplayPlaying(false);
      return;
    }
    if (effectiveReplayIndex >= candles.length - 1) {
      if (!canStructuralReplayExtendHorizon) {
        setMessage(replayPlayForwardStatusMessage('no-loaded-candles-ahead'));
        return;
      }
      const advanced = await stepReplayForwardOne();
      if (!advanced) return;
    }
    setCandleReplayMode(true);
    setCandleReplayPlaying(true);
  };

  const captureSeedAnchor = (key:string, mode:'high'|'low') => {
    const c = selectedCandle || replayCandle;
    if (!c) { setMessage('Select a candle first. The machine cannot mark ghosts, sadly.'); return; }
    const price = mode === 'high' ? c.high : c.low;
    setSeedAnchors((prev:any)=>({ ...prev, [key]: Number(price.toFixed(2)), [`${key}_time`]: c.time }));
    if (key === 'weekly_high' || key === 'daily_high') setRangeHigh(String(Number(price.toFixed(2))));
    if (key === 'weekly_low' || key === 'daily_low') setRangeLow(String(Number(price.toFixed(2))));
    setMessage(`Captured ${key.replace('_',' ').toUpperCase()} at ${price.toFixed(2)} from ${shortTime(c.time, timeframe)}.`);
  };

  const samePrice = (a:any,b:any) => {
    const x = parseNum(a); const y = parseNum(b);
    return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x-y) < 0.01;
  };

  const caseDedupeKey = () => {
    const c = selectedCandle || replayCandle;
    const parts = [
      symbol, caseScope, caseTimeframe,
      c?.time || 'NO_CANDLE',
      String(caseHigh || '').trim() || 'NO_HIGH',
      String(caseLow || '').trim() || 'NO_LOW',
      String(seedName || '').trim().toUpperCase() || 'NO_NAME'
    ];
    return parts.join('|');
  };

  const resetActiveCase = () => {
    const tf = caseTimeframe || timeframe;
    setActiveCaseId(null);
    setRawActiveCaseId('');
    setActiveCaseLabel('');
    setCaseSavedNotice('');
    // v087.29b: Clear the entire local case draft, not only the case id.
    // Old range windows must not survive Cancel/Clear and anchor the next box to stale history.
    setSeedAnchors((prev:any)=>{
      const next = { ...prev };
      [
        'case_high','case_low','case_high_time','case_low_time',
        'range_start_date','range_end_date',
        'weekly_high','weekly_low','weekly_high_time','weekly_low_time',
        'daily_high','daily_low','daily_high_time','daily_low_time',
        'macro_high','macro_low','macro_high_time','macro_low_time'
      ].forEach(k => { delete next[k]; });
      next.case_scope = caseScope;
      next.case_timeframe = tf;
      return next;
    });
    setRangeByTf((prev:any)=>({ ...prev, [tf]: { high:'', low:'' } }));
    setRangeWindowByTf((prev:any)=>({ ...prev, [tf]: {} }));
    setCameraDomainByCaseTf((prev:any)=>{
      const next = { ...(prev || {}) };
      Object.keys(next).forEach(k => { if (String(k).includes(`_${tf}`) || String(k).startsWith('global_')) delete next[k]; });
      return next;
    });
    setMessage('Active case cleared. Use New Case to start the next quarter.');
  };

  const startNewCase = () => {
    resetActiveCase();
    const name = buildQuarterCaseNameFromCandle();
    setSeedName(name);
    setMessage(`New case draft: "${name}". Map your anchors, then Create Case.`);
  };

  const saveSeedIdea = async (saveAsNew = false) => {
    if (caseSaving) return;
    if (!cleanCaseDisplayName(seedName)) {
      setMessage('Enter a case name first (e.g. XAUUSD 2020 Q1).');
      return;
    }
    setCaseSaving(true);
    setCaseSavedNotice('');
    try {
      if (saveAsNew) {
        setRawActiveCaseId('');
        setActiveCaseId(null);
        setActiveCaseLabel('');
      }
      const rawId = await ensureRawCase({ forceNew: saveAsNew });
      if (!rawId) throw new Error('No raw case id returned');
      const savedName = cleanCaseDisplayName(seedName);
      const savedMsg = `Case saved: ${savedName}`;
      setCaseSavedNotice(savedMsg);
      await loadSavedCasesFromBackend();
      setSeedIdeas(prev => mergeSavedCases(prev, rawCaseRecentRow(rawId)));
      setMessage(`${savedMsg} — pick it anytime from Saved cases below.`);
      setTimeout(()=>setCaseSavedNotice(''), 6000);
    } catch (err:any) {
      setMessage(`Raw case save failed: ${err?.message || err}`);
    } finally {
      setCaseSaving(false);
    }
  };

  const loadSavedCasesFromBackend = async () => {
    setCaseLoadStatus('Loading saved cases from VPS…');
    try {
      const [legacyData, rawList] = await Promise.all([
        fetch(`${BASE_URL}/api/v1/mos/seed-ideas?symbol=${encodeURIComponent(symbol)}&limit=50`).then(r => r.json()).catch(() => ({ ideas: [] })),
        listRawCases(BASE_URL, symbol, 200),
      ]);
      const legacyRows = Array.isArray(legacyData?.ideas) ? legacyData.ideas : [];
      const rawRows = safeArray<any>(rawList?.cases).map((c:any) => rawCaseRowFromBackend(c));
      const merged = mergeSavedCases([...legacyRows, ...rawRows]);
      setSeedIdeas(merged);

      const hasActiveRaw = rawActiveCaseId && merged.some((idea:any) => String(idea?.raw_case_id || idea?.id || '') === String(rawActiveCaseId));
      const hasActiveLegacy = activeCaseId != null && merged.some((idea:any) => Number(idea?.id) === Number(activeCaseId));
      if (rawList.ok && rawActiveCaseId && !hasActiveRaw) setRawActiveCaseId('');
      if (Array.isArray(legacyData?.ideas) && activeCaseId != null && !hasActiveLegacy) setActiveCaseId(null);
      if (rawActiveCaseId && !hasActiveRaw && !rawList.ok) {
        setSeedIdeas((prev) => mergeSavedCases(prev, rawCaseRecentRow(String(rawActiveCaseId))));
      }

      const rawCount = rawRows.length;
      const legacyCount = legacyRows.length;
      if (rawList.ok) {
        setCaseLoadStatus(`${merged.length} saved case${merged.length === 1 ? '' : 's'} loaded from VPS (${rawCount} raw, ${legacyCount} legacy).`);
      } else if (rawList.httpStatus === 405 || rawList.httpStatus === 404) {
        setCaseLoadStatus(`${legacyCount} legacy case${legacyCount === 1 ? '' : 's'} loaded. VPS still needs backend update for raw case list (GET /api/v1/raw-mapping/cases).`);
      } else {
        setCaseLoadStatus(`${legacyCount} legacy case${legacyCount === 1 ? '' : 's'} loaded. Raw case list unavailable: ${rawList.error || 'backend error'}.`);
      }
    } catch (err:any) {
      setSeedIdeas(mergeSavedCases([]));
      setCaseLoadStatus(`Could not load cases from VPS: ${err?.message || err}`);
    }
  };


  const savedCaseWindow = (idea:any) => {
    const anchors = idea?.anchors || idea?.mos_payload?.anchors || {};
    const start = idea?.range_start_date || anchors?.range_start_date || idea?.case_high_time || anchors?.case_high_time || idea?.replay_candle_time || '';
    const end = idea?.range_end_date || anchors?.range_end_date || idea?.case_low_time || anchors?.case_low_time || idea?.replay_candle_time || '';
    return { start: start || '', end: end || '' };
  };

  const normalizeBackendEvent = (e:any): MapEvent | null => {
    const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta || e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
    const price = Number(e?.price);
    const event_type = String(e?.event_type || e?.event_name || '').toUpperCase();
    if (!event_type || !Number.isFinite(price)) return null;
    return {
      id: String(e?.id || e?.client_event_id || cryptoId()),
      event_type,
      event_name: e?.event_name || markerLabel(event_type),
      time: e?.time || meta?.time || new Date().toISOString(),
      price,
      zone: e?.zone || '',
      zone_percent: e?.zone_percent === null || e?.zone_percent === undefined ? undefined : Number(e.zone_percent),
      notes: e?.notes || '',
      source: e?.source || 'backend_case_payload',
      primitive: e?.primitive || undefined,
      derived_event_code: e?.derived_event_code || undefined,
      movement_rule: e?.movement_rule || undefined,
      range_status_after: e?.range_status_after || undefined,
      engine_source: e?.engine_source || undefined,
      logic_version: e?.logic_version || undefined,
      candidate_id: e?.candidate_id || undefined,
      confidence: e?.confidence || undefined,
      meta_json: meta,
      candle_open: e?.candle_open === null || e?.candle_open === undefined ? undefined : Number(e.candle_open),
      candle_high: e?.candle_high === null || e?.candle_high === undefined ? undefined : Number(e.candle_high),
      candle_low: e?.candle_low === null || e?.candle_low === undefined ? undefined : Number(e.candle_low),
      candle_close: e?.candle_close === null || e?.candle_close === undefined ? undefined : Number(e.candle_close),
    } as any;
  };

  const buildStructuralNavigationPlan = (range: any, chartTf: string) => {
    const span = rangeWindowFieldsFromSavedRange(range);
    const layer = normalizeStructureLayer(range?.structure_layer || range?.layer);
    const tf = String(chartTf).toUpperCase();
    const windows = resolveStructuralContextAndReplayWindows({
      rangeSpan: { start: span.start || span.end, end: span.end || span.start },
      chartTf: tf,
      structureLayer: layer,
      label: `${formatStructuralRangeOptionLabel(range)} context`,
    });
    const loadWindow = windows?.dataLoad || (() => {
      const startDay = isoDay(span.start || span.end);
      const endDay = isoDay(span.end || span.start);
      if (!startDay || !endDay) return null;
      return resolveStructuralDataLoadWindow({
        rangeSpan: { start: startDay, end: endDay },
        chartTf: tf,
        structureLayer: layer,
        label: `${formatStructuralRangeOptionLabel(range)} fallback`,
      });
    })();
    const fitWindow = structuralRangeFitDomain(range, [], tf);
    return {
      rangeId: String(range?.range_id || range?.id || ''),
      startStr: span.start || span.end || '',
      endStr: span.end || span.start || '',
      chartTf: tf,
      fitWindow,
      loadWindow,
      visualContext: windows?.visualContext || null,
      targetTime: structuralContextTargetTime(range) || span.start || null,
    };
  };

  const navigateStructuralChartContext = (args: {
    targetTf: string;
    range: any;
    reason: string;
  }) => {
    skipSavedReplayHydrateRef.current = true;
    const plan = buildStructuralNavigationPlan(args.range, args.targetTf);
    if (plan.startStr || plan.endStr) {
      setRangeWindowByTf((prev) => ({
        ...prev,
        [plan.chartTf]: { start: plan.startStr || plan.endStr, end: plan.endStr || plan.startStr },
      }));
      structuralVisualContextRef.current = {
        start: plan.startStr || plan.endStr || '',
        end: plan.endStr || plan.startStr || '',
      };
    }
    skipBootstrapOnceRef.current = true;
    pendingCameraIntentRef.current = {
      intent: 'FIT_STRUCTURAL_RANGE',
      targetTime: plan.targetTime,
      reason: args.reason,
      fitWindow: plan.fitWindow,
      contextRangeId: plan.rangeId,
    };
    setCameraViewOwnerWithLog('TIMEFRAME_SWITCH', 'navigateStructuralChartContext', args.reason);
    activeTimeframeRef.current = plan.chartTf;
    setTimeframe(plan.chartTf);
    if (plan.loadWindow) {
      structuralDataLoadWindowRef.current = plan.loadWindow;
    }
    return loadCandles(plan.chartTf, {
      cacheFullHistory: true,
      structuralNavigation: true,
      timeframeSwitch: true,
      reason: args.reason,
      navigationPath: `navigateStructural:${args.reason}`,
      deferCamera: true,
    });
  };

  const switchTimeframePreserveCase = (nextTf:string): Promise<void> => {
    const tf = String(nextTf || timeframe).toUpperCase();
    const sourceTf = String(timeframe).toUpperCase();
    if (tf === sourceTf) return Promise.resolve();
    const caseId = String(activeCaseDisplayId || 'global');
    cameraLog('chart tf switch requested (routine memory)', { from: sourceTf, to: tf, layer: structureLayer });
    setCameraViewOwnerWithLog('TIMEFRAME_SWITCH', 'switchTimeframePreserveCase', routineTfMemoryReason(sourceTf, tf));

    const dom = visibleCameraDomainRef.current;
    const validDomTime = !!(dom?.start && dom?.end
      && Number.isFinite(new Date(dom.start).getTime())
      && Number.isFinite(new Date(dom.end).getTime()));
    const sourceDomSnap = validDomTime
      ? snapshotMemoryFromVisibleDomain({
        start: dom!.start,
        end: dom!.end,
        priceLow: dom!.priceLow,
        priceHigh: dom!.priceHigh,
        visibleBars: dom!.visibleBars,
      })
      : null;
    const sourceDomPersistable = sourceDomSnap
      ? shouldPersistChartMemory(sourceDomSnap, sourceTf)
      : false;
    const sourceMemoryKey = chartMemoryKey(caseId, symbol, sourceTf);
    const sourceLegacyKey = legacyChartMemoryKey(caseId, sourceTf);
    const destMemoryKey = chartMemoryKey(caseId, symbol, tf);
    const destLegacyKey = legacyChartMemoryKey(caseId, tf);
    if (validDomTime && sourceDomPersistable) {
      const snap = sourceDomSnap!;
      if (shouldPersistChartMemory(snap, sourceTf)) {
        setCameraDomainByCaseTf((prev) => ({
          ...prev,
          [sourceMemoryKey]: { start: snap.start, end: snap.end },
          [sourceLegacyKey]: { start: snap.start, end: snap.end },
        }));
        if (Number.isFinite(dom!.priceLow) && Number.isFinite(dom!.priceHigh) && dom!.priceHigh > dom!.priceLow) {
          setCameraPriceDomainByCaseTf((prev) => ({
            ...prev,
            [sourceMemoryKey]: { low: dom!.priceLow!, high: dom!.priceHigh! },
            [sourceLegacyKey]: { low: dom!.priceLow!, high: dom!.priceHigh! },
          }));
        }
      }
    }

    const selectedTimeForRestore = selectedCandle?.time
      || tradingViewSelectedCandle?.time
      || tradingViewAdmittedSelectedCandle?.time
      || null;
    skipSelectionClearForTfSwitchRef.current = true;

    const crossTfH1 = isCrossTfH1Entry(sourceTf, tf);
    if (crossTfH1) {
      const purge = purgePoisonedH1MemoryKeys(cameraDomainByCaseTf, caseId, symbol);
      if (purge) {
        setCameraDomainByCaseTf((prev) => {
          const next = { ...prev };
          delete next[purge.key];
          delete next[purge.legacy];
          return next;
        });
        setCameraPriceDomainByCaseTf((prev) => {
          const next = { ...prev };
          delete next[purge.key];
          delete next[purge.legacy];
          return next;
        });
      }
    }

    const savedDestMemory = crossTfH1
      ? null
      : readChartMemoryFromStore(
        cameraDomainByCaseTf,
        caseId,
        symbol,
        tf,
        cameraPriceDomainByCaseTf,
      );
    const sourceViewport = validDomTime && sourceDomPersistable
      ? sourceDomSnap
      : readChartMemoryFromStore(cameraDomainByCaseTf, caseId, symbol, sourceTf, cameraPriceDomainByCaseTf);
    const savedDestPrice = cameraPriceDomainByCaseTf[destMemoryKey]
      || cameraPriceDomainByCaseTf[destLegacyKey]
      || null;

    const plan = resolveRoutineTfSwitchCameraPlan({
      cameraMode,
      sourceTf,
      destTf: tf,
      savedDestMemory,
      sourceViewport,
      globalReplayTime: candleReplayMode ? candleReplayCursorTime : null,
      selectedCandleTime: selectedTimeForRestore,
      savedDestPrice,
      explicitReplayMode: candleReplayMode,
      replayMode: candleReplayMode,
    });

    activateRoutineFitLock(tf);

    tradingViewCameraBridge.current.routineAnchorSource = plan.anchorSource || null;

    pendingCameraIntentRef.current = {
      intent: plan.intent,
      targetTime: plan.targetTime,
      reason: plan.reason,
      fitWindow: plan.fitWindow,
      priceDomain: plan.priceDomain,
      anchorSource: plan.anchorSource || null,
    };

    if (chartRenderer === 'tradingview') {
      tradingViewSuppressedHierarchyRangeIdRef.current = String(activeStructuralRangeIdRef.current || selectedParentRangeIdRef.current || '');
      tradingViewHierarchyFitKeyRef.current = '';
      setTradingViewHierarchyFitCommand(null);
    }

    skipBootstrapOnceRef.current = true;
    activeTimeframeRef.current = tf;
    setTimeframe(tf);
    if (autoResume.isWelcome) autoResume.markSessionActive(symbol, tf);
    return loadCandles(tf, {
      cacheFullHistory: true,
      timeframeSwitch: true,
      reason: plan.reason,
      navigationPath: 'switchTimeframePreserveCase',
    }).then(() => undefined);
  };

  const handleMappingViewContextChange = (next: MappingViewContext) => {
    unlockGlobalView();
    setMappingViewContext(next);
    const targetTf = resolveMappingViewChartTimeframe(next, structureLayer, timeframe);
    if (targetTf && targetTf !== String(timeframe).toUpperCase()) {
      mappingViewContextSyncRef.current = true;
      switchTimeframePreserveCase(targetTf);
    }
  };

  const handleDrillDownViewport = () => {
    const start = activeMappingContainerDraft?.startTime;
    const end = activeMappingContainerDraft?.endTime;
    if (!drillDownViewport() || !start || !end || !candles.length) {
      setMessage('Drill down needs a mapped container with start and end times.');
      return;
    }
    const clamped = clampFitTimesToCandles(start, end, candles);
    applyCameraCommand('FIT_STRUCTURAL_RANGE', clamped.start, 'drill-down-container', undefined, {
      start: clamped.start,
      end: clamped.end,
      low: 0,
      high: 0,
      padRatio: 0.06,
    });
    setMessage(`Drill down · ${shortTime(clamped.start, timeframe)} → ${shortTime(clamped.end, timeframe)}`);
  };

  const handleUnlockGlobalView = () => {
    unlockGlobalView();
    setMessage('Global view unlocked — chart pan/zoom is no longer clamped to the container.');
  };

  useEffect(() => {
    if (!mappingViewContextSyncRef.current) return;
    mappingViewContextSyncRef.current = false;
  }, [timeframe]);

  useEffect(() => {
    if (!campaignViewContextEnabled) return;
    const parentTf = campaignParentChartTf;
    if (mappingViewContext === 'parent' && parentTf && normalizeChartTf(timeframe) !== normalizeChartTf(parentTf)) {
      setMappingViewContext('child');
    }
  }, [timeframe, structureLayer, campaignViewContextEnabled, campaignParentChartTf, mappingViewContext]);

  const showStructuralMappingRibbon = chartFullscreen || mappingSkeletonContextReady;
  const mappingAllowedChartTfs = useMemo(
    () => allowedChartTimeframesForStructureLayer(structureLayer),
    [structureLayer],
  );

  useEffect(() => {
    if (blockMappingBootEffects()) return;
    if (chartRenderer === 'tradingview') return;
    if (!showStructuralMappingRibbon) return;
    if (isChartTimeframeAllowedForLayer(timeframe, structureLayer)) return;
    switchTimeframePreserveCase(defaultChartTimeframeForStructureLayer(structureLayer));
  }, [showStructuralMappingRibbon, structureLayer, timeframe, pendingMappingSession, chartRenderer]);

  const handleChartTfSwitch = (nextTf: string) => {
    const tf = String(nextTf || timeframe).toUpperCase();
    cameraLog('chart tf chip clicked', { tf, activeRangeId: activeStructuralRangeIdRef.current, parentRangeId: selectedParentRangeIdRef.current, layer: structureLayer });
    if (chartRenderer === 'd3' && showStructuralMappingRibbon && !mappingAllowedChartTfs.includes(tf)) {
      setMessage(`Chart ${tf} is blocked while mapping ${structureLayer}. Use ${mappingAllowedChartTfs.join(' or ')} — or change scope first.`);
      return;
    }
    switchTimeframePreserveCase(tf);
  };

  const openSavedCase = async (idea:any, preferredTf?:string) => {
    if (!idea?.id) return;
    if (idea?.is_raw_mapping_case || idea?.raw_case_id) {
      const rawId = String(idea.raw_case_id || idea.id || '');
      if (!rawId) return;
      const nextTf = String(preferredTf || idea.case_timeframe || idea.replay_timeframe || idea?.raw_case?.base_timeframe || caseTimeframe || timeframe).toUpperCase();
      const nextScope = String(idea.case_scope || timeframeToScope(nextTf) || caseScope).toUpperCase() as CaseScope;
      setRawActiveCaseId(rawId);
      setActiveCaseId(null);
      setActiveCaseLabel(cleanCaseDisplayName(idea.seed_name) || 'Raw Case');
      setSeedName(cleanCaseDisplayName(idea.seed_name) || seedName);
      setSeedNotes(idea.notes || '');
      setCaseScope(nextScope);
      setSeedAnchors((prev:any)=>({ ...prev, case_scope: nextScope, case_timeframe: nextTf }));
      setHistoryMarkMode('ACTIVE_CASE');
      pendingCameraIntentRef.current = { intent: cameraMode === 'LOCKED' ? 'RESTORE_LOCKED' : 'PRESERVE_OR_NEAREST_TIME', targetTime: idea.replay_candle_time || selectedCandle?.time || candleReplayCursorTime || null, reason:'open-raw-case' };
      skipBootstrapOnceRef.current = true;
      activeTimeframeRef.current = nextTf;
      setTimeframe(nextTf);
      setSeedIdeas(prev => mergeSavedCases(prev, rawCaseRecentRow(rawId, idea.raw_case)));
      const { eventCount, rangeCount } = await restoreCaseWorkspaceFromVps(rawId, nextTf);
      const caseWindow = rangeWindowByTf[nextTf] || { start: seedAnchors.range_start_date || '', end: seedAnchors.range_end_date || '' };
      const loadWindow = resolveStructuralCandleLoadWindow({ rangeWindow: caseWindow });
      await loadCandles(nextTf, {
        loadWindow,
        cacheFullHistory: !shouldUseWindowedCandleLoad(loadWindow),
      });
      setMessage(`Opened raw Case ${rawId.slice(0,8)} from VPS${eventCount ? ` · ${eventCount} ledger event${eventCount===1?'':'s'}` : ''}${rangeCount ? ` · ${rangeCount} structural range${rangeCount===1?'':'s'}` : ''}.`);
      return;
    }
    const id = Number(idea.id);
    setRawActiveCaseId('');
    setActiveCaseId(id);
    setActiveCaseLabel(cleanCaseDisplayName(idea.seed_name) || `Case #${id}`);
    setSeedName(cleanCaseDisplayName(idea.seed_name) || seedName);
    setSeedNotes(idea.notes || '');
    const anchors = { ...(idea.anchors || {}) };
    const w = savedCaseWindow(idea);
    const nextScope = String(idea.case_scope || idea?.mos_payload?.case_scope || caseScope).toUpperCase() as CaseScope;
    const nextTf = String(preferredTf || idea.case_timeframe || idea.replay_timeframe || idea?.mos_payload?.case_timeframe || scopeToTimeframe(nextScope)).toUpperCase();
    const high = idea.case_high ?? anchors.case_high ?? anchors.weekly_high ?? anchors.daily_high ?? '';
    const low = idea.case_low ?? anchors.case_low ?? anchors.weekly_low ?? anchors.daily_low ?? '';
    setCaseScope(nextScope);
    setSeedAnchors((prev:any)=>({ ...prev, ...anchors, case_scope: nextScope, case_timeframe: nextTf, case_high: high || prev.case_high || '', case_low: low || prev.case_low || '', range_start_date: w.start || prev.range_start_date || '', range_end_date: w.end || prev.range_end_date || '' }));
    if (high || low) setRangeByTf(prev => ({ ...prev, [nextTf]: { high: String(high || prev[nextTf]?.high || ''), low: String(low || prev[nextTf]?.low || '') } }));
    if (w.start || w.end) setRangeWindowByTf(prev => ({ ...prev, [nextTf]: { ...(prev[nextTf] || {}), start: w.start || prev[nextTf]?.start || '', end: w.end || prev[nextTf]?.end || '' } }));
    setHistoryMarkMode('ACTIVE_CASE');
    pendingCameraIntentRef.current = { intent: cameraMode === 'LOCKED' ? 'RESTORE_LOCKED' : 'CASE', targetTime: w.start || idea.replay_candle_time || selectedCandle?.time || candleReplayCursorTime || null, reason:'open-saved-case' };
    skipBootstrapOnceRef.current = true;
    activeTimeframeRef.current = nextTf;
    setTimeframe(nextTf);
    try {
      const payload = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${id}/payload`).then(r=>r.json());
      if (payload?.ok) {
        const grouped:Record<string,MapEvent[]> = {};
        safeArray<any>(payload.events).forEach((raw:any)=>{
          const ev = normalizeBackendEvent(raw);
          if (!ev) return;
          const tf = String(raw?.timeframe || ev?.meta_json?.timeframe || nextTf).toUpperCase();
          grouped[tf] = [...(grouped[tf] || []), ev];
        });
        if (Object.keys(grouped).length) setEventsByTf(prev => ({ ...prev, ...grouped }));
        const ranges = safeArray<any>(payload.ranges);
        if (ranges.length) {
          setRangeByTf(prev => {
            const out:any = { ...prev };
            for (const r of ranges) {
              const tf = String(r.timeframe || nextTf).toUpperCase();
              if (!out[tf]) out[tf] = {};
              if (r.range_high !== null && r.range_high !== undefined) out[tf].high = String(r.range_high);
              if (r.range_low !== null && r.range_low !== undefined) out[tf].low = String(r.range_low);
            }
            return out;
          });
          setRangeWindowByTf(prev => {
            const out:any = { ...prev };
            for (const r of ranges) {
              const tf = String(r.timeframe || nextTf).toUpperCase();
              out[tf] = { ...(out[tf] || {}), start: r.active_from_time || r.range_high_time || w.start || out[tf]?.start || '', end: r.inactive_from_time || r.range_low_time || w.end || out[tf]?.end || '' };
            }
            if (w.start || w.end) out[nextTf] = { ...(out[nextTf] || {}), start: w.start || out[nextTf]?.start || '', end: w.end || out[nextTf]?.end || '' };
            return out;
          });
        }
      }
    } catch { /* payload is helpful but not mandatory */ }
    const loadWindow = resolveStructuralCandleLoadWindow({ rangeWindow: w });
    await loadCandles(nextTf, {
      loadWindow,
      cacheFullHistory: !shouldUseWindowedCandleLoad(loadWindow),
    });
    setMessage(`Opened Case #${id}. Restored ${nextTf} workspace and case camera ${w.start ? String(w.start).slice(0,10) : 'start?'} → ${w.end ? String(w.end).slice(0,10) : 'end?'}. Switch W1/D1 and the camera stays in this case window.`);
  };

  const savedCaseIdeas = useMemo(() => {
    return sortCaseRows(safeArray<any>(seedIdeas)).filter((idea:any) =>
      String(idea?.symbol || symbol).toUpperCase() === String(symbol).toUpperCase()
    );
  }, [seedIdeas, symbol]);

  const rawCaseRestoreRef = useRef('');
  useEffect(() => {
    if (!rawActiveCaseId) {
      rawCaseRestoreRef.current = '';
      return;
    }
    if (rawCaseRestoreRef.current === rawActiveCaseId) return;
    rawCaseRestoreRef.current = rawActiveCaseId;
    const row = safeArray<any>(seedIdeas).find((x:any) => String(x?.raw_case_id || x?.id || '') === String(rawActiveCaseId));
    const tf = String(row?.case_timeframe || row?.replay_timeframe || row?.raw_case?.base_timeframe || caseTimeframe || timeframe).toUpperCase();
    void restoreCaseWorkspaceFromVps(String(rawActiveCaseId), tf).then(({ eventCount, rangeCount }) => {
      if (eventCount || rangeCount) {
        setMessage(`Restored case ${String(rawActiveCaseId).slice(0, 8)} · ${eventCount} events · ${rangeCount} ranges from VPS.`);
      }
    }).catch((err: any) => {
      setMessage(`Case restore failed: ${err?.message || err}`);
    });
  }, [rawActiveCaseId, seedIdeas]);

  useEffect(()=>{ loadSavedCasesFromBackend(); }, [symbol]);

  useEffect(() => {
    if (rightDeckTab === 'seed') loadSavedCasesFromBackend();
  }, [rightDeckTab]);

  useEffect(()=>{
    if (!candles.length) return;
    if (candleReplayCursorTime) {
      const idx = candleIndexAtOrBefore(candles, candleReplayCursorTime);
      if (idx !== candleReplayIndex) setCandleReplayIndex(idx);
    }
  }, [candles, candleReplayCursorTime]);

  useEffect(() => {
    setChartDrawings(loadChartDrawings(chartDrawingsKey));
    setSelectedDrawingId(null);
    if (skipSavedReplayHydrateRef.current) {
      skipSavedReplayHydrateRef.current = false;
      return;
    }
    const structuralContextActive = !!(
      activeStructuralRangeIdRef.current
      || selectedParentRangeIdRef.current
      || guidedCursorRef.current?.active
    );
    if (structuralContextActive) return;
    const savedReplay = loadReplayCursorForKey(globalReplayKey, { allowLegacy: true })
      ?? loadReplayCursorForKey(chartDrawingsKey, { allowLegacy: false });
    if (savedReplay && !replayCursorByKey[globalReplayKey]) {
      setReplayCursorByKey((prev) => ({ ...prev, [globalReplayKey]: savedReplay }));
    }
  }, [chartDrawingsKey, globalReplayKey]);

  useEffect(() => {
    saveChartDrawings(chartDrawingsKey, chartDrawings);
  }, [chartDrawingsKey, chartDrawings]);

  useEffect(() => {
    setChartTradeIdeas(loadChartTradeIdeas(tradeIdeasKey));
    setSelectedTradeIdeaId(null);
    setTradeIdeaDraft(emptyTradeIdeaDraft());
    setTradePickMode(null);
  }, [tradeIdeasKey]);

  useEffect(() => {
    saveChartTradeIdeas(tradeIdeasKey, chartTradeIdeas);
  }, [tradeIdeasKey, chartTradeIdeas]);

  useEffect(() => {
    if (rightDeckTab === 'trade') setChartDrawTool('off');
  }, [rightDeckTab]);

  useEffect(() => {
    if (tradePickMode) setChartDrawTool('off');
  }, [tradePickMode]);

  useEffect(() => {
    const onKeyDown = (evt: KeyboardEvent) => {
      const tag = String((evt.target as HTMLElement | null)?.tagName || '').toUpperCase();
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (!selectedDrawingId) return;
      if (evt.key === 'Delete' || evt.key === 'Backspace') {
        setChartDrawings((prev) => prev.filter((d) => d.id !== selectedDrawingId));
        setSelectedDrawingId(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedDrawingId]);

  useEffect(() => {
    const onSkeletonKeyDown = (evt: KeyboardEvent) => {
      if (isTypingInEditableField(evt.target)) return;
      const action = resolveMapStudioKeyAction(evt.key);
      if (!action) return;
      if (chartRenderer === 'tradingview' && !tradingViewMappingInputEnabled && ['set-rh', 'set-rl', 'bos-up', 'bos-down'].includes(action)) {
        evt.preventDefault();
        const warning = 'TradingView mapping input disabled.';
        setTradingViewSelectionWarning(warning);
        setMessage(warning);
        return;
      }
      if (['set-rh', 'set-rl', 'bos-up', 'bos-down'].includes(action) && !getCurrentMappingCaseRef().hasCase) return;
      if (['set-rh', 'set-rl', 'bos-up', 'bos-down'].includes(action) && !assertCandleFeedReady('Keyboard mark')) return;
      evt.preventDefault();
      if (action === 'set-rh') void setStructuralPoint('RH');
      else if (action === 'set-rl') void setStructuralPoint('RL');
      else if (action === 'bos-up') void setStructuralPoint('BH');
      else if (action === 'bos-down') void setStructuralPoint('BL');
      else if (action === 'replay-back') stepReplayBackOne();
      else if (action === 'replay-forward') void stepReplayForwardOne();
      else if (action === 'undo') undoLastQuickEvent();
      else if (action === 'escape') clearMappingDraftSelection();
    };
    window.addEventListener('keydown', onSkeletonKeyDown);
    return () => window.removeEventListener('keydown', onSkeletonKeyDown);
  }, [
    mappingSkeletonContextReady,
    selectedCandle,
    replayCandle,
    structuralSaving,
    chainDraftMode,
    timeframe,
    structureLayer,
    chartRenderer,
    tradingViewMappingInputEnabled,
    tradingViewSelectedCandle,
  ]);

  const updateChartDrawings = (updater: ChartDrawing[] | ((prev: ChartDrawing[]) => ChartDrawing[])) => {
    setChartDrawings((prev) => (typeof updater === 'function' ? updater(prev) : updater));
  };

  const handleTradeLevelPick = (payload: { kind: TradeIdeaPickKind; time: string; price: number }) => {
    setTradeIdeaDraft((prev) => ({ ...prev, [payload.kind]: { time: payload.time, price: payload.price } }));
    setTradePickMode(null);
    setMessage(`Trade ${payload.kind.toUpperCase()} set at ${payload.price.toFixed(2)} · ${shortTime(payload.time, timeframe)}`);
  };

  const handleSaveTradeIdea = async () => {
    const idea = buildTradeIdeaFromDraft({
      draft: tradeIdeaDraft,
      symbol,
      timeframe,
      rangeId: activeStructuralRangeId || null,
      rangeScope,
      structureLayer,
      caseRef: activeCaseDisplayId || null,
      caseLabel: seedName || activeCaseLabel || null,
      notes: tradeIdeaNotes,
    });
    if (!idea) {
      setMessage('Entry, SL, and TP1 are required before saving a trade idea.');
      return;
    }
    setTradeIdeaSaving(true);
    try {
      const next = [idea, ...chartTradeIdeas];
      setChartTradeIdeas(next);
      saveChartTradeIdeas(tradeIdeasKey, next);
      setTradeIdeaDraft(emptyTradeIdeaDraft());
      setTradeIdeaNotes('');
      setSelectedTradeIdeaId(idea.id);
      try {
        await fetch(`${BASE_URL}/api/v1/trade-ideas/quick`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: idea.id,
            symbol,
            direction: idea.direction === 'LONG' ? 'BUY' : 'SELL',
            setup_type: `Chart Trade Idea · ${structureLayer}`,
            sl_price: idea.sl?.price,
            notes: JSON.stringify({ chartTradeIdea: idea, range_id: idea.rangeId, analystExport: idea.analystExport }),
            source: 'map_studio_chart',
          }),
        });
      } catch { /* local save is source of truth for chart ideas */ }
      const rr = idea.analystExport.rrTp1 != null ? `${idea.analystExport.rrTp1.toFixed(2)}R TP1` : 'saved';
      setMessage(`Trade idea saved · ${idea.direction} ${idea.entry.price.toFixed(2)} · ${rr}`);
    } finally {
      setTradeIdeaSaving(false);
    }
  };

  const handleDeleteTradeIdea = (id: string) => {
    setChartTradeIdeas((prev) => {
      const next = prev.filter((x) => x.id !== id);
      saveChartTradeIdeas(tradeIdeasKey, next);
      return next;
    });
    if (selectedTradeIdeaId === id) setSelectedTradeIdeaId(null);
  };

  const handleExportTradeIdeas = () => {
    downloadTradeIdeasJson(tradeIdeasKey, chartTradeIdeas);
    setMessage(`Exported ${chartTradeIdeas.length} trade idea(s) for analyst.`);
  };

  useEffect(()=>{
    if (!candleReplayPlaying || !candleReplayMode || candles.length === 0) return;
    const id = window.setInterval(() => {
      if (replayStepInFlightRef.current) return;
      replayStepInFlightRef.current = true;
      void stepReplayForwardOne().then((advanced) => {
        replayStepInFlightRef.current = false;
        if (!advanced) setCandleReplayPlaying(false);
      });
    }, candleReplaySpeedMs);
    return () => window.clearInterval(id);
  }, [candleReplayPlaying, candleReplayMode, candles.length, candleReplaySpeedMs]);

  useEffect(()=>{
    if (!playbackPlaying || !replayMode || playbackFrames.length === 0) return;
    const id = window.setInterval(() => {
      setPlaybackIndex(prev => {
        const next = prev + 1;
        if (next >= playbackFrames.length) {
          window.clearInterval(id);
          setPlaybackPlaying(false);
          return prev;
        }
        setTimeout(()=>applyPlaybackFrame(playbackFrames[next], next), 0);
        return next;
      });
    }, 1100);
    return () => window.clearInterval(id);
  }, [playbackPlaying, replayMode, playbackFrames]);

  const loadGps = async (mode: 'mock'|'active' = gpsMode) => {

    try {
      const params = new URLSearchParams({
        symbol,
        timeframe: 'W1',
        story_anchor: gpsStoryAnchor,
        chapter: gpsChapter,
        phase: gpsPhaseNumber,
        phase_part: gpsPhasePart,
        objective: gpsObjective,
        current_zone: gpsCurrentZone,
      });
      const endpoint = mode === 'mock'
        ? `${BASE_URL}/api/v1/market-gps/mock?${params.toString()}`
        : `${BASE_URL}/api/v1/mos/coordinates/${encodeURIComponent(symbol)}`;
      const res = await fetch(endpoint);
      const data = await res.json();
      setGps(data);
      if (mode === 'active') await loadTimeline();
    } catch (err:any) {
      setGps({ ok:false, status:'GPS_FETCH_FAILED', coordinates:null } as any);
    }
  };

  const saveGpsState = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mos/build-state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          story_id: gpsStoryId ? Number(gpsStoryId) : undefined,
          chapter_id: gpsChapterId ? Number(gpsChapterId) : undefined,
          story_timeframe: 'W1',
          chapter_timeframe: 'D1',
          story_anchor: gpsStoryAnchor,
          anchor_class: anchorClassLabel(gpsStoryAnchor),
          chapter: gpsChapter,
          lifecycle_state: gpsLifecycleState,
          parent_context_mode: gpsParentMode,
          daily_range_status: gpsDailyRangeStatus,
          phase_number: Number(String(gpsPhaseNumber).replace('P','')) || 1,
          phase_part: gpsPhasePart,
          objective_code: gpsObjective,
          current_zone: gpsCurrentZone,
          established_price: activeReplayCandle ? Number(activeReplayCandle.close.toFixed(2)) : 0,
          trigger_event: gpsTriggerEvent,
          expected_next_event: gpsExpectedNextEvent,
          invalidation_condition: gpsInvalidationCondition,
          timeframe: 'D1',
          bos_direction: gpsChapter.includes('DOWN') ? 'DOWN' : 'UP',
          bos_price: activeReplayCandle ? Number(activeReplayCandle.close.toFixed(2)) : 0,
          profile_type: gpsProfileType,
          timestamp: activeReplayCandle?.time || new Date().toISOString(),
        })
      });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || data?.detail || 'Save failed');
      setGpsMode('active');
      setGps({ ok:true, status:data.status || 'TRACKING_ACTIVE', symbol, timeframe:'W1', coordinates:data.coordinates });
      setMessage(`Saved MOS state: ${data.coordinates?.phase} ${data.coordinates?.phase_part}. Playback ledger has entered the chat.`);
      if (data?.story_id) { setPlaybackStoryId(String(data.story_id)); await loadPlayback(String(data.story_id)); }
    } catch (err:any) {
      setMessage(`GPS save failed: ${err?.message || err}`);
    }
  };

  useEffect(()=>{ loadGps(gpsMode); }, [symbol, gpsMode]);
  useEffect(()=>{ if (gpsMode === 'mock') loadGps('mock'); }, [gpsStoryAnchor, gpsChapter, gpsPhaseNumber, gpsPhasePart, gpsObjective, gpsCurrentZone]);

  const markerSections = useMemo(() => markerGroupsForTimeframe(timeframe), [timeframe]);

  useEffect(() => {
    if (blockMappingBootEffects()) return;
    if (autoResume.phase !== 'welcome' || candles.length) return;
    if (candleFeedLoadInFlightRef.current) return;
    let cancelled = false;
    void (async () => {
      const cacheCount = await readLocalCacheBarCount(symbol, timeframe);
      if (cancelled || cacheCount <= 0) return;
      const loadWindow = resolveCandleLoadWindow(
        timeframe,
        savedStructuralRanges,
        selectedParentRangeId,
        activeStructuralRangeId,
        rangeWindowByTf[timeframe] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
      );
      await loadCandles(timeframe, {
        loadWindow,
        cacheFullHistory: !shouldUseWindowedCandleLoad(loadWindow),
      });
      if (!cancelled) autoResume.markSessionActive(symbol, timeframe);
    })();
    return () => { cancelled = true; };
  }, [pendingMappingSession, autoResume.phase, symbol, timeframe, candles.length]);

  useEffect(() => {
    if (blockMappingBootEffects()) return;
    if (autoResume.phase === 'booting' || autoResume.isAutoResuming) return;
    if (candleFeedLoadInFlightRef.current) return;
    let cancelled = false;
    const bootId = chartBootstrapSeqRef.current + 1;
    chartBootstrapSeqRef.current = bootId;
    (async () => {
      if (skipBootstrapOnceRef.current) {
        skipBootstrapOnceRef.current = false;
        return;
      }
      if (getCurrentMappingCaseRef().hasCase) {
        try { await refreshSavedRangesForCurrentCase(); } catch {}
        try { await refreshStructuralMapEventsForChart(timeframe); } catch {}
      }
      if (cancelled || bootId !== chartBootstrapSeqRef.current) return;
      const loadWindow = resolveCandleLoadWindow(
        timeframe,
        savedStructuralRanges,
        selectedParentRangeId,
        activeStructuralRangeId,
        rangeWindowByTf[timeframe] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
      );
      const windowed = shouldUseWindowedCandleLoad(loadWindow);
      const cacheCount = await readLocalCacheBarCount(symbol, timeframe);
      if (cancelled || bootId !== chartBootstrapSeqRef.current) return;
      if (cacheCount > 0 || windowed) {
        await loadCandles(timeframe, { loadWindow, cacheFullHistory: !windowed });
      } else {
        await loadCandles(timeframe);
      }
      if (cancelled || bootId !== chartBootstrapSeqRef.current) return;
      if (windowed || activeStructuralRangeId || selectedParentRangeId) return;
      void syncSymbolAllTimeframesToCache(symbol, { reason: 'boot_sync', baseUrl: BASE_URL }).then(async (sync) => {
        if (cancelled || bootId !== chartBootstrapSeqRef.current) return;
        if (sync.ok) {
          await loadCandles(timeframe, { quiet: true, skipCamera: true, cacheFullHistory: true });
          return;
        }
        await bootstrapCandleFeed();
        if (!cancelled && bootId === chartBootstrapSeqRef.current) {
          await loadCandles(timeframe, { quiet: true, skipCamera: true });
        }
      });
    })();
    return () => { cancelled = true; };
  }, [symbol, timeframe, autoResume.phase, autoResume.isAutoResuming, pendingMappingSession]);

  useEffect(() => {
    if (blockMappingBootEffects()) return;
    if (autoResume.phase === 'booting' || autoResume.isAutoResuming) return;
    let cancelled = false;
    const stopBackgroundSync = initBackgroundCandleSync({
      baseUrl: BASE_URL,
      resyncIntervalMs: DEFAULT_RESYNC_INTERVAL_MS,
      onStatus: (status) => {
        if (cancelled || status.phase !== 'ready') return;
        if (status.symbol && status.symbol !== symbol) return;
        if (candleLoadInFlightRef.current) return;
        const loadWindow = resolveCandleLoadWindow(
          timeframe,
          savedStructuralRanges,
          selectedParentRangeId,
          activeStructuralRangeId,
          rangeWindowByTf[timeframe] || rangeWindowByTf.D1 || rangeWindowByTf.W1 || rangeWindow,
        );
        const tfUpper = String(timeframe).toUpperCase();
        const keepFullHistory = fullHistoryChartTfsRef.current.has(tfUpper);
        void loadCandles(timeframe, {
          quiet: true,
          skipCamera: true,
          loadWindow: keepFullHistory ? null : loadWindow,
          cacheFullHistory: keepFullHistory || !shouldUseWindowedCandleLoad(loadWindow),
        });
      },
    });
    getSyncService().onSymbolSelected(symbol);
    return () => {
      cancelled = true;
      stopBackgroundSync();
    };
  }, [symbol, timeframe, autoResume.phase, autoResume.isAutoResuming, pendingMappingSession]);

  const selectStructureLayer = (layer: StructureLayer) => {
    const nextAnchorsByLayer: Partial<Record<StructureLayer, LayerAnchorPair>> = {
      ...structuralAnchorsByLayer,
      [structureLayer]: { rh: rhAnchor, rl: rlAnchor },
    };
    setStructuralAnchorsByLayer(nextAnchorsByLayer);

    const nextParentLayer = expectedParentStructureLayer(layer);
    if (nextParentLayer) {
      const activeRow = activeStructuralRangeId ? findSavedRangeRowById(activeStructuralRangeId) : null;
      const activeRowLayer = activeRow ? normalizeStructureLayer(activeRow.structure_layer || activeRow.layer) : null;
      if (activeRow && activeRowLayer === nextParentLayer && isRangeMajor(activeRow)) {
        setSelectedParentRangeId(String(activeStructuralRangeId));
      } else {
        const selectedRow = selectedParentRangeId
          ? safeArray<any>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(selectedParentRangeId))
          : null;
        const selectedRowLayer = selectedRow ? normalizeStructureLayer(selectedRow.structure_layer || selectedRow.layer) : null;
        const parentRange = latestSavedRangeForLayer(nextParentLayer, savedStructuralRanges, selectedParentRangeId || activeStructuralRangeId || undefined);
        if (parentRange) {
          setSelectedParentRangeId(String(parentRange.range_id || parentRange.id));
        } else if (selectedRowLayer && selectedRowLayer !== nextParentLayer) {
          setSelectedParentRangeId('');
        }
      }
    } else {
      setSelectedParentRangeId('');
    }

    const stored = nextAnchorsByLayer[layer];
    if (stored?.rh?.price || stored?.rl?.price) {
      setRhAnchor(stored.rh || { price:'', time:'', candle:null });
      setRlAnchor(stored.rl || { price:'', time:'', candle:null });
      setRangeHigh(stored.rh?.price || '');
      setRangeLow(stored.rl?.price || '');
      const layerSavedRange = latestSavedRangeForLayer(layer, savedStructuralRanges, activeStructuralRangeId || undefined);
      const priceMatches = (a: number, b: number) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 0.005;
      const rhMatch = layerSavedRange && priceMatches(parseNum(stored.rh?.price), parseNum(layerSavedRange.range_high_price ?? layerSavedRange.range_high));
      const rlMatch = layerSavedRange && priceMatches(parseNum(stored.rl?.price), parseNum(layerSavedRange.range_low_price ?? layerSavedRange.range_low));
      setStructuralRangeDraftDirty(!!(stored.rh?.price && stored.rl?.price) && !(rhMatch && rlMatch));
    } else {
      setRhAnchor({ price:'', time:'', candle:null });
      setRlAnchor({ price:'', time:'', candle:null });
      setRangeHigh('');
      setRangeLow('');
      setStructuralRangeDraftDirty(false);
    }

    setStructureLayer(layer);
    setSourceTimeframe(defaultSourceTimeframeForStructureLayer(layer));
    const targetChartTf = defaultChartTimeframeForStructureLayer(layer);
    if (String(timeframe).toUpperCase() !== targetChartTf) {
      switchTimeframePreserveCase(targetChartTf);
      setMessage(`Scope ${layer}: chart locked to ${targetChartTf}. Parent HTF ranges stay visible as context lines.`);
    }
  };
  const selectRangeScope = (scope: RangeScope) => {
    setRangeScope(scope);
    if (scope === 'MINOR') {
      const major = latestSavedRangeForLayer(structureLayer, savedStructuralRanges, selectedParentRangeId, true);
      if (major) setSelectedParentRangeId(String(major.range_id || major.id));
    } else {
      const parentLayer = expectedParentStructureLayer(structureLayer);
      if (parentLayer) {
        const parent = latestSavedRangeForLayer(parentLayer, savedStructuralRanges, selectedParentRangeId, true);
        if (parent) setSelectedParentRangeId(String(parent.range_id || parent.id));
      } else {
        setSelectedParentRangeId('');
      }
    }
  };
  const chainScopeMismatch = useMemo(() => {
    if (!chainDraftMode || !activeStructuralRangeId) return null;
    const broken = selectedSavedRange || findSavedRangeRowById(activeStructuralRangeId);
    if (!broken) return null;
    const brokenScope = normalizeRangeScope(broken.range_scope);
    if (brokenScope === 'MINOR' && rangeScope === 'MAJOR') {
      return 'Broken range is MINOR but Role is MAJOR — Save Next creates a new major sibling. Break the weekly MAJOR itself if that was the intent.';
    }
    if (brokenScope === 'MAJOR' && rangeScope === 'MINOR') {
      return 'Broken range is MAJOR but Role is MINOR — switch to MAJOR to chain the next weekly major.';
    }
    return null;
  }, [chainDraftMode, activeStructuralRangeId, selectedSavedRange, savedStructuralRanges, rangeScope]);

  useEffect(() => () => {
    if (inspectorCommitFlashTimerRef.current) clearTimeout(inspectorCommitFlashTimerRef.current);
  }, []);

  const triggerInspectorCommitSuccess = () => {
    if (inspectorCommitFlashTimerRef.current) clearTimeout(inspectorCommitFlashTimerRef.current);
    setInspectorCommitFlash('success');
    inspectorCommitFlashTimerRef.current = setTimeout(() => {
      setInspectorCommitFlash('idle');
      inspectorCommitFlashTimerRef.current = null;
    }, 500);
  };

  const inspectorCommitAction = useMemo(() => {
    if (chainDraftMode && saveNextRangeEligible.eligible && rhAnchor.price && rlAnchor.price) {
      return { kind: 'next_range' as const, label: 'Commit Next Range' };
    }
    if (structuralBosDraftDirty && (bhAnchor.price || blAnchor.price) && activeStructuralRangeId) {
      const direction: 'UP' | 'DOWN' = bhAnchor.price ? 'UP' : 'DOWN';
      return {
        kind: 'bos' as const,
        label: direction === 'UP' ? 'Commit Break Up' : 'Commit Break Down',
        direction,
      };
    }
    return { kind: 'range' as const, label: savePreview.actionLabel };
  }, [
    chainDraftMode,
    saveNextRangeEligible.eligible,
    rhAnchor.price,
    rlAnchor.price,
    structuralBosDraftDirty,
    bhAnchor.price,
    blAnchor.price,
    activeStructuralRangeId,
    savePreview.actionLabel,
  ]);

  const inspectorCommitDisabled = useMemo(() => {
    if (structuralSaving || quickEventSaving) return true;
    if (!getCurrentMappingCaseRef().hasCase) return true;
    if (inspectorCommitAction.kind === 'next_range') {
      return !saveNextRangeEligible.eligible || !rhAnchor.price || !rlAnchor.price;
    }
    if (inspectorCommitAction.kind === 'bos') {
      return !activeStructuralRangeId || (!bhAnchor.price && !blAnchor.price);
    }
    return !rhAnchor.price || !rlAnchor.price;
  }, [
    structuralSaving,
    quickEventSaving,
    inspectorCommitAction.kind,
    saveNextRangeEligible.eligible,
    rhAnchor.price,
    rlAnchor.price,
    bhAnchor.price,
    blAnchor.price,
    activeStructuralRangeId,
    activeCaseId,
    rawActiveCaseId,
  ]);

  const tradingViewOverlays = useMemo(() => {
    if (chartRenderer !== 'tradingview' || tradingViewOverlayMode !== 'readonly') {
      return { priceLines: [], markers: [] };
    }
    return adaptOverlaysForTradingView({
      timeframe,
      selectedRange: selectedSavedRange,
      savedRangeOverlays: chartSavedRangeOverlays,
      parentRangeOverlays: activeParentRangeOverlay,
      visibleEvents,
      draftRangeOverlay: chartDraftRangeOverlay,
      draftRhAnchor: rhAnchor,
      draftRlAnchor: rlAnchor,
      suppressRangeGuideLines: allRangeGuideLinesHidden,
    });
  }, [
    chartRenderer,
    tradingViewOverlayMode,
    timeframe,
    selectedSavedRange,
    chartSavedRangeOverlays,
    activeParentRangeOverlay,
    visibleEvents,
    chartDraftRangeOverlay,
    allRangeGuideLinesHidden,
    rhAnchor.price,
    rhAnchor.time,
    rlAnchor.price,
    rlAnchor.time,
  ]);

  const tradingViewFitRequest = useMemo(() => {
    if (chartRenderer !== 'tradingview') return null;
    const hierarchyCmd = tradingViewHierarchyFitCommand;
    if (hierarchyCmd && (hierarchyCmd.fitWindow?.start && hierarchyCmd.fitWindow?.end || isStructuralNavigationReason(hierarchyCmd.reason))) {
      return adaptFitRequestForTradingView({
        token: hierarchyCmd.token,
        intent: hierarchyCmd.intent,
        reason: hierarchyCmd.reason,
        fitWindow: hierarchyCmd.fitWindow,
        targetTime: hierarchyCmd.targetTime,
        timeframe,
      });
    }
    if (candleReplayMode && tradingViewReplayStepFitRequest) {
      return tradingViewReplayStepFitRequest;
    }
    const fitCommand = cameraCommand;
    if (isStructuralNavigationReason(fitCommand.reason) && fitCommand.fitWindow?.start && fitCommand.fitWindow?.end) {
      return adaptFitRequestForTradingView({
        token: fitCommand.token,
        intent: fitCommand.intent,
        reason: fitCommand.reason,
        fitWindow: fitCommand.fitWindow,
        targetTime: fitCommand.targetTime,
        timeframe,
      });
    }
    if (isRoutineTfMemoryReason(fitCommand.reason)) {
      const parsed = parseRoutineTfMemoryReason(fitCommand.reason);
      const requireFitRange = parsed
        ? isCrossTfH1Entry(parsed.sourceTf, parsed.destTf)
        : String(timeframe).toUpperCase() === 'H1';
      const memoryReq = buildTradingViewMemoryFitRequest({
        token: fitCommand.token,
        timeframe,
        fitWindow: fitCommand.fitWindow,
        targetTime: fitCommand.targetTime,
        requireFitRange,
      });
      if (memoryReq) return memoryReq;
      if (requireFitRange && fitCommand.targetTime) {
        return buildTradingViewMemoryFitRequest({
          token: fitCommand.token,
          timeframe,
          fitWindow: fitCommand.fitWindow,
          targetTime: fitCommand.targetTime,
          requireFitRange: false,
        });
      }
      return null;
    }
    return adaptFitRequestForTradingView({
      token: fitCommand.token,
      intent: fitCommand.intent,
      reason: fitCommand.reason,
      fitWindow: fitCommand.fitWindow,
      targetTime: fitCommand.targetTime,
      timeframe,
    });
  }, [chartRenderer, cameraCommand, timeframe, tradingViewHierarchyFitCommand, tradingViewMappingInputEnabled, tradingViewReplayStepFitRequest, candleReplayMode]);

  const tradingViewChartMode: TradingViewChartMode = candleReplayMode && replayCandle
    ? 'replay'
    : tradingViewMappingInputEnabled
      ? 'full'
      : tradingViewHierarchyFitCommand?.fitWindow
        ? 'hierarchy'
        : usesTradingViewTailSliceForTimeframe(timeframe)
          ? 'latest'
          : 'full';

  const tradingViewDisplayCandles = useMemo(() => applyChartModeWindow(candles, {
    mode: tradingViewChartMode,
    timeframe,
    hierarchyStart: tradingViewHierarchyFitCommand?.fitWindow?.start || null,
    hierarchyEnd: tradingViewHierarchyFitCommand?.fitWindow?.end || null,
    replayCutTime: candleReplayMode && replayCandle ? replayCandle.time : null,
  }), [
    candles,
    candleReplayMode,
    replayCandle?.time,
    timeframe,
    tradingViewChartMode,
    tradingViewHierarchyFitCommand,
  ]);
  tradingViewDisplayCandlesRef.current = tradingViewDisplayCandles;

  const tradingViewChartSelectedCandle = useMemo((): TradingViewSelectedCandle | null => (
    resolveVisualTradingViewSelectedCandle({
      mappingInputEnabled: chartRenderer === 'tradingview' && tradingViewMappingInputEnabled,
      candleReplayMode,
      replayCandle,
      displayedCandles: tradingViewDisplayCandles,
      admittedSelectedCandle: tradingViewAdmittedSelectedCandle,
      fallbackSelectedCandle: tradingViewSelectedCandle,
      symbol,
      chartTimeframe: timeframe,
      sourceTimeframe,
    })
  ), [
    chartRenderer,
    tradingViewMappingInputEnabled,
    candleReplayMode,
    replayCandle,
    tradingViewDisplayCandles,
    tradingViewAdmittedSelectedCandle,
    tradingViewSelectedCandle,
    symbol,
    timeframe,
    sourceTimeframe,
  ]);

  useEffect(() => {
    if (chartRenderer !== 'tradingview' || tradingViewMappingInputEnabled) return;
    setSelectedCandle(null);
    setSelectedCandlePoint(null);
    setTradingViewSelectedCandle(null);
    setTradingViewCrosshairCandle(null);
    setTradingViewSelectionWarning(null);
    setRhAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
    setRlAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
    setBhAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
    setBlAnchor((prev) => (prev.candle ? { ...prev, candle: null } : prev));
  }, [
    chartRenderer,
    tradingViewMappingInputEnabled,
    tradingViewChartMode,
    tradingViewHierarchyFitCommand?.token,
    candleReplayMode,
    replayCandle?.time,
    tradingViewExplicitReplayMode,
  ]);

  useEffect(() => {
    if (chartRenderer !== 'tradingview' || !tradingViewMappingInputEnabled) return;
    if (!tradingViewHierarchyFitCommand?.token) return;
    applyTvMappingSelectionClear();
    setTradingViewCrosshairCandle(null);
    setTradingViewSelectionWarning(null);
  }, [chartRenderer, tradingViewMappingInputEnabled, tradingViewHierarchyFitCommand?.token]);

  const handleInspectorStructuralCommit = async () => {
    let ok = false;
    if (inspectorCommitAction.kind === 'next_range') {
      ok = await saveNextStructuralRange();
    } else if (inspectorCommitAction.kind === 'bos' && inspectorCommitAction.direction) {
      ok = await saveStructuralBos(inspectorCommitAction.direction);
    } else {
      ok = await saveStructuralRange();
    }
    if (ok) triggerInspectorCommitSuccess();
  };

  const structuralMappingRibbonEl = (
    <div className={`structuralMappingRibbon ${chartFullscreen ? 'ribbonDocked ribbonCompact' : 'ribbonInline'}`} aria-label="Structural mapping scope">
      {!chartFullscreen && <div className="ribbonScopeRow">
        <span className="ribbonLabel">Layer</span>
        <div className="markModeStrip compact ribbonScopeStrip">
          {STRUCTURE_LAYERS.map(layer => (
            <button key={layer} type="button" className={structureLayer === layer ? 'active' : ''} onClick={() => selectStructureLayer(layer)}>{layer}</button>
          ))}
        </div>
      </div>}
      {!chartFullscreen && <div className="ribbonScopeRow">
        <span className="ribbonLabel">Role</span>
        <div className="markModeStrip compact ribbonScopeStrip">
          {RANGE_SCOPES.map(scope => (
            <button key={scope} type="button" className={rangeScope === scope ? 'active' : ''} onClick={() => selectRangeScope(scope)}>{scope}</button>
          ))}
        </div>
      </div>}
      {chartFullscreen && <div className="ribbonScopeStrip ribbonScopeChips" role="group" aria-label="Mapping scope">
        {STRUCTURE_LAYERS.map(layer => (
          <button key={layer} type="button" className={`scopeChip ${structureLayer === layer ? 'active' : ''}`} title={layer} onClick={() => selectStructureLayer(layer)}>{STRUCTURE_LAYER_CHIP[layer]}</button>
        ))}
        {RANGE_SCOPES.map(scope => (
          <button key={scope} type="button" className={`scopeChip ${rangeScope === scope ? 'active' : ''}`} title={scope} onClick={() => selectRangeScope(scope)}>{scope === 'MAJOR' ? 'Maj' : 'Min'}</button>
        ))}
      </div>}
      <label className="ribbonSourceTf" title="Structural source timeframe">{chartFullscreen ? '' : 'Source TF '}
        <select value={sourceTimeframe} onChange={e => setSourceTimeframe(e.target.value)}>
          {sourceTimeframeOptionsForLayer(structureLayer).map(tf => <option key={tf} value={tf}>{tf}</option>)}
        </select>
      </label>
      {parentStructureLayer && parentLinkContextLabel && (
        <span
          className="ribbonParentChip"
          title={`${parentLinkContextLabel.mappingLine}\n${parentLinkContextLabel.parentLine}\n${parentLinkContextLabel.mode}\nClick parent row in Structural Explorer to change.`}
        >
          {parentLinkContextLabel.parentLine.replace(/^Parent:\s*/, '')}
        </span>
      )}
      <span className="ribbonChartLock" title={`RH/RL plotting locked to ${mappingAllowedChartTfs.join('/')} chart for ${structureLayer} scope`}>
        {chartFullscreen ? `Plot ${mappingAllowedChartTfs.join('/')}` : `Plot chart: ${mappingAllowedChartTfs.join(' / ')}`}
      </span>
      {saveBlockReason && (
        <span className="ribbonSaveHint" title={saveBlockReason}>{saveBlockReason}</span>
      )}
      <span className="ribbonStatus" title={`${structureLayer} · source ${sourceTimeframe} · chart ${timeframe}${activeStructuralRangeId ? ` · active #${activeStructuralRangeId}` : ''}${candleLoadDiagnostics ? `\n${formatCandleLoadDiagnostic(candleLoadDiagnostics)}${candleLoadDiagnostics.detail ? `\n${candleLoadDiagnostics.detail}` : ''}` : ''}`}>
        {chartFullscreen
          ? `${STRUCTURE_LAYER_CHIP[structureLayer]}/${sourceTimeframe}/${timeframe}${activeStructuralRangeId ? ` · #${activeStructuralRangeId}` : ''}`
          : `Status: ${structureLayer} · source ${sourceTimeframe} · chart ${timeframe}${activeStructuralRangeId ? ` · active #${activeStructuralRangeId}` : ''}`}
      </span>
      {candleLoadDiagnostics && !chartFullscreen && (
        <span className="ribbonLoadDiag" title={candleLoadDiagnostics.detail || candleLoadDiagnostics.reason}>
          {formatCandleLoadDiagnostic(candleLoadDiagnostics)}
        </span>
      )}
      {chainDraftMode && (
        <div className="chainDraftBanner">
          <span>{chainScopeMismatch || `BROKEN · set next RH/RL on chart (H/L keys)`}</span>
          {expectedChildStructureLayer(structureLayer) && selectedSavedRange && !chainScopeMismatch && (
            <button
              type="button"
              className="chainDrillBtn"
              onClick={() => drillToChildMapping(selectedSavedRange)}
              title={`Switch to ${expectedChildStructureLayer(structureLayer)} and plot child range under #${activeStructuralRangeId}`}
            >
              Drill {expectedChildStructureLayer(structureLayer)}
            </button>
          )}
        </div>
      )}
    </div>
  );
  const compactQuickSaveLabel = chainDraftMode && saveNextRangeEligible.eligible
    ? 'Next'
    : savePreview.actionLabel
      .replace('Update Broken Range (confirm)', 'Upd Broken')
      .replace('Update Selected Range', 'Update')
      .replace('Save New Range', 'Save');

  const handleQuickRangeSave = () => {
    if (chainDraftMode && saveNextRangeEligible.eligible) void saveNextStructuralRange();
    else void saveStructuralRange();
  };
  const tvMappingVisibleFeedReady = chartRenderer === 'tradingview'
    && tradingViewMappingInputEnabled
    && candles.length > 0;
  const candleFeedGuard = useMemo((): CandleFeedGuardResult => {
    if (tvMappingVisibleFeedReady) {
      const chartTf = String(timeframe).toUpperCase();
      const rehydrated = rehydrateLoadedCandleContextForVisibleFeed({
        loaded: loadedCandleContext,
        requestId: candleLoadSeqRef.current,
        symbol: String(symbol),
        caseId: String(activeCaseDisplayId || ''),
        chartTimeframe: chartTf,
        sourceTimeframe: String(sourceTimeframe).toUpperCase(),
        structureLayer: String(structureLayer),
        candleCount: candles.length,
      });
      return evaluateCandleFeedGuard({
        symbol: String(symbol).toUpperCase(),
        caseId: String(activeCaseDisplayId || ''),
        chartTimeframe: chartTf,
        sourceTimeframe: String(sourceTimeframe).toUpperCase(),
        structureLayer: structureLayer as StructureLayerId,
        candleLoadInFlight: candleFeedLoading || loading,
        candleCount: candles.length,
      }, rehydrated);
    }
    return getCandleFeedGuard();
  }, [
    tvMappingVisibleFeedReady,
    symbol,
    activeCaseDisplayId,
    timeframe,
    sourceTimeframe,
    structureLayer,
    candleFeedLoading,
    loading,
    loadedCandleContext,
    candles.length,
  ]);
  const tvMappingSelectionReady = chartRenderer !== 'tradingview'
    || !tradingViewMappingInputEnabled
    || !!admittedMappingInputCandle;
  const structuralQuickAnchorDisabled = structuralSaving || quickEventSaving || candleFeedLoading || !candleFeedGuard.ready
    || (chartRenderer === 'tradingview' && !tradingViewMappingInputEnabled)
    || (chartRenderer === 'tradingview' && tradingViewMappingInputEnabled ? !tvMappingSelectionReady : !mappingInputCandle);
  const structuralQuickAnchorHint = candleFeedLoading
    ? 'Loading candle feed…'
    : chartRenderer === 'tradingview' && !tradingViewMappingInputEnabled
      ? 'TradingView mapping input disabled.'
    : !candleFeedGuard.ready
      ? (candleFeedGuard.message || 'Candle feed mismatch — marking blocked')
      : chartRenderer === 'tradingview' && tradingViewMappingInputEnabled && !tvMappingSelectionReady
        ? 'Click a TradingView candle first'
      : !canSetRhRlStructuralDraft && (chartRenderer === 'tradingview' && tradingViewMappingInputEnabled ? tvMappingSelectionReady : !!mappingInputCandle)
        ? mappingRhRlDraftBlockMessage
      : !mappingInputCandle
        ? (chartRenderer === 'tradingview' && tradingViewMappingInputEnabled
          ? 'Click a TradingView candle first'
          : 'Select a candle on the chart first (Sel tool)')
        : structuralSaving
          ? 'Saving range…'
          : quickEventSaving
            ? 'Saving event…'
            : '';
  const structuralQuickAnchorBarEl = (
    <div className="quickAnchorBar quickAnchorBarCompact skeletonMapBar" aria-label="Skeleton mapping — H/L/↑/↓ or buttons">
      <button type="button" className={`structuralQuickBtn chipBtn ${rhAnchor.price ? 'active' : ''}`} disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('RH')} title="H · Range High"><span>RH</span></button>
      <button type="button" className={`structuralQuickBtn chipBtn ${rlAnchor.price ? 'active' : ''}`} disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('RL')} title="L · Range Low"><span>RL</span></button>
      <button type="button" className="structuralQuickBtn chipBtn" disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('BH')} title="↑ · BOS Up"><span>↑</span></button>
      <button type="button" className="structuralQuickBtn chipBtn" disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('BL')} title="↓ · BOS Down"><span>↓</span></button>
      <button type="button" className="quickSaveBtn secondary" onClick={undoLastQuickEvent} disabled={!canUndoQuickEvent || quickEventSaving} title="U · Undo">Undo</button>
      {(structuralRangeDraftDirty || structuralBosDraftDirty || structuralSaving) && (
        <span className="quickDraftStatus dirty" title={structuralSaving ? 'Syncing…' : 'Draft'}>{structuralSaving ? 'sync…' : 'draft'}</span>
      )}
      {chartFullscreen && <>
        <span className="quickAnchorDivider" />
        <button type="button" onClick={() => setChartFullscreen(false)} title="Exit fullscreen">Exit</button>
      </>}
    </div>
  );

  const structuralMarkToolbarEl = (
    <div className="structuralMarkToolbar" aria-label="Structural mapping toolbar">
      <button type="button" className="structuralMarkBtn" disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('RH')} title="Range High">RH</button>
      <button type="button" className="structuralMarkBtn" disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('RL')} title="Range Low">RL</button>
      <button type="button" className="structuralMarkBtn" disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('BH')} title="Break Up">↑</button>
      <button type="button" className="structuralMarkBtn" disabled={structuralQuickAnchorDisabled} onClick={() => setStructuralPoint('BL')} title="Break Down">↓</button>
      <span className="structuralMarkDivider" />
      <button type="button" className={`structuralMarkBtn primary ${chainDraftMode ? 'emph' : savePreview.selectedIsBroken ? '' : 'emph'}`} onClick={handleQuickRangeSave} disabled={structuralSaving || !rhAnchor.price || !rlAnchor.price || !getCurrentMappingCaseRef().hasCase} title={saveBlockReason || (chainDraftMode ? 'Save next range in chain' : savePreview.actionLabel)}>{structuralSaving ? '…' : compactQuickSaveLabel}</button>
      <button type="button" className="structuralMarkBtn" onClick={saveNextStructuralRange} disabled={structuralSaving || !saveNextRangeEligible.eligible} title={saveNextRangeEligible.reason || 'Save next range'}>Next</button>
      <button type="button" className="structuralMarkBtn" onClick={refreshHierarchyAudit} title="Refresh audit">Audit</button>
      <button type="button" className="structuralMarkBtn" onClick={exportCurrentMappingJson} title="Export mapping JSON">Export</button>
      <button type="button" className="structuralMarkBtn" onClick={undoLastQuickEvent} disabled={!canUndoQuickEvent || quickEventSaving} title="Undo last event (LIFO)">Undo</button>
      {(structuralRangeDraftDirty || structuralBosDraftDirty) && (
        <span className="structuralDraftBadge" title="Unsaved draft — use Commit in Inspector footer">draft</span>
      )}
    </div>
  );

  const tradingViewHudCandle = tradingViewSelectionBridgeActive
    ? (tradingViewCrosshairCandle || tradingViewChartSelectedCandle)
    : null;
  const chartHudCandleTime = tradingViewSelectionBridgeActive
    ? (tradingViewHudCandle?.time || null)
    : (cursor?.time || (candleReplayMode && replayCandle?.time) || selectedCandle?.time || null);
  const chartHudPrice = tradingViewSelectionBridgeActive
    ? (tradingViewHudCandle?.close ?? null)
    : (cursor?.price ?? cursor?.ohlc?.close ?? replayCandle?.close ?? selectedCandlePoint?.price ?? null);
  const chartDrawToolbarEl = (
    <div className="chartDrawToolbar" aria-label="Chart drawing tools">
      <button type="button" className={chartDrawTool === 'off' && toolMode === 'inspect' ? 'active' : ''} onClick={() => { setChartDrawTool('off'); setToolMode('inspect'); }} title="Pan chart">Pan</button>
      <button type="button" className={toolMode === 'select' && chartDrawTool === 'off' ? 'active' : ''} onClick={() => { setChartDrawTool('off'); setToolMode('select'); }} title="Select candle">Sel</button>
      <button type="button" className={toolMode === 'scrub' && chartDrawTool === 'off' ? 'active' : ''} onClick={() => { setChartDrawTool('off'); setToolMode('scrub'); }} disabled={!candleReplayMode} title="Scrub replay bar">Scrub</button>
      <span className="chartDrawDivider" />
      <button type="button" className={chartDrawTool === 'hline' ? 'active' : ''} onClick={() => setChartDrawTool('hline')} title="Horizontal line (resize width in Edit mode)">H</button>
      <button type="button" className={chartDrawTool === 'vline' ? 'active' : ''} onClick={() => setChartDrawTool('vline')} title="Vertical line (resize in Edit mode)">V</button>
      <button type="button" className={chartDrawTool === 'text' ? 'active' : ''} onClick={() => setChartDrawTool('text')} title="Text label">Txt</button>
      <button type="button" className={chartDrawTool === 'edit' ? 'active' : ''} onClick={() => setChartDrawTool('edit')} title="Move / resize drawings">Edit</button>
      <span className="chartDrawDivider" />
      {CHART_DRAWING_COLORS.map((c) => (
        <button key={c} type="button" className={`drawColorSwatch${chartDrawColor === c ? ' active' : ''}`} style={{ background: c }} onClick={() => setChartDrawColor(c)} title={`Color ${c}`} aria-label={`Color ${c}`} />
      ))}
      <button type="button" className="chartDrawClearBtn" disabled={!chartDrawings.length} onClick={() => { setChartDrawings([]); setSelectedDrawingId(null); }} title="Clear drawings for this case/timeframe">Clear</button>
    </div>
  );

  return <div className={`mapStudioShell d3MapStudio ${chartFullscreen ? 'chartFullscreenActive' : ''}${!inspectorFormReady ? ' mapStudioBooting' : ''}`}>
    <div className="panelHeader mapStudioHeader">
      <div><h2>Map Studio</h2><p>D3 candle canvas with locked vertical scale, horizontal pan, precision crosshair, and backend candle memory.</p></div>
      <div className="studioControls"><button onClick={loadCandles} disabled={loading}><RefreshCw size={18}/> Reload</button></div>
    </div>

    <div className={`mapStudioToolbar compactMapToolbar ${topRibbonCollapsed ? 'collapsedRibbon' : ''}`}>
      <button className="ribbonToggle" onClick={()=>setTopRibbonCollapsed(v=>!v)}>{topRibbonCollapsed ? 'Show ribbon' : 'Hide ribbon'}</button>
      <div className="tfTabs">{MAP_TIMEFRAMES.map(tf=>{
        const locked = chartRenderer === 'd3' && showStructuralMappingRibbon && !mappingAllowedChartTfs.includes(tf);
        return <button key={tf} type="button" className={`${timeframe===tf?'active':''}${locked?' tfLocked':''}`} disabled={locked} title={locked ? `Blocked while mapping ${structureLayer}. Change scope or use ${mappingAllowedChartTfs.join('/')}.` : `Switch to ${tf}`} onClick={()=>handleChartTfSwitch(tf)}>{tf}</button>;
      })}</div>
      {!topRibbonCollapsed && <>
      <button className={scaleMode==='auto'?'active':''} onClick={()=>{ setScaleMode('auto'); setAutoscaleToken(x=>x+1); }}>Auto</button>
      <button className={scaleMode==='range'?'active':''} onClick={()=>setScaleMode('range')}>Range</button>
      <button className={gpsMode==='active'?'active':''} onClick={()=>setGpsMode('active')}>GPS</button>
      <button className={candleReplayMode?'active replayActiveBtn':''} onClick={toggleBarReplay} title="TradingView-style bar replay">Bar Replay</button>
      <button className={chartFullscreen?'active':''} onClick={()=>setChartFullscreen(v=>!v)}>{chartFullscreen ? 'Exit Full' : 'Full Chart'}</button>
      <div className="chartRendererToggle" role="group" aria-label="Chart renderer">
        <button type="button" className={chartRenderer==='d3'?'active':''} onClick={()=>setChartRendererRaw('d3')}>D3 Map</button>
        <button type="button" className={chartRenderer==='tradingview'?'active':''} onClick={()=>setChartRendererRaw('tradingview')}>Live View</button>
      </div>
      <button
        type="button"
        className={`eventBrowserPanelToggle eventBrowserPanelToolbarToggle${eventBrowserOpen ? ' open' : ''}`}
        onClick={() => setEventBrowserOpen((open) => !open)}
        aria-pressed={eventBrowserOpen}
        title="Event Browser"
      >
        Events
      </button>
      <select className="cameraModeSelect" value={cameraMode} onChange={e=>setCameraMode(e.target.value as any)} title="Camera mode"><option value="AUTO">Auto cam</option><option value="LOCKED">Locked cam</option><option value="CASE">Case cam</option><option value="REPLAY">Replay cam</option></select>
      <div className="scaleNudges"><button onClick={()=>bumpCandleWidth(-0.15)}>W−</button><span>{Number(candleWidthScale).toFixed(2)}x</span><button onClick={()=>bumpCandleWidth(0.15)}>W+</button><button onClick={()=>bumpPriceZoom(-0.15)}>H−</button><span>{Number(priceZoomScale).toFixed(2)}x</span><button onClick={()=>bumpPriceZoom(0.15)}>H+</button><button onClick={resetCameraScale}>Reset</button></div>
      <div className="scaleNudges fitNudges"><button onClick={fitRangeView}>Fit Range</button><button onClick={fitReplayView}>Fit Replay</button><button onClick={fitCaseView}>Fit Case</button><button onClick={fitAllView}>Fit All</button><button onClick={lockCurrentView}>Lock View</button></div>
      <span className="loadedPill compactStatus">{candles.length ? `${candles.length} ${timeframe}` : 'No candles'}{candleFeedStatus?.sync?.last_finished_at ? ` · sync ${String(candleFeedStatus.sync.last_finished_at).slice(11, 16)}Z` : ''}</span>
      <label className="historyMarksControl" title="Filter stored chart marks without deleting ledger records">History
        <select value={historyMarkMode} onChange={e=>setHistoryMarkMode(e.target.value)}>
          <option value="OFF">OFF</option>
          <option value="SESSION">Session</option>
          <option value="ACTIVE_RANGE">Active Range</option>
          <option value="ACTIVE_CASE">Active Case</option>
          <option value="NEARBY">Nearby</option>
          <option value="ALL">All</option>
        </select>
      </label>
      <button className={showRejectedMarks ? 'active historyMarksBtn' : 'historyMarksBtn'} onClick={()=>setShowRejectedMarks(v=>!v)} title="Rejected candidates stay stored for ML, but stay off the chart unless you ask for the mess.">Rejected {showRejectedMarks ? 'ON' : 'OFF'}</button>
      <details className="toolsMenu"><summary>Tools ▾</summary><div className="toolsMenuPanel">
        <button onClick={syncMt5Now} disabled={loading}><RefreshCw size={18}/> Sync MT5 Now</button>
        <button onClick={importCommon} disabled={loading}><Database size={18}/> Import EA CSV</button>
        <button onClick={()=>setJumpToken(x=>x+1)}>Jump latest</button>
        <button onClick={fitAllView}>Fit all</button>
        <button onClick={()=>loadGps(gpsMode)}>Refresh GPS</button>
        <button className={gpsMode==='mock'?'active':''} onClick={()=>setGpsMode('mock')}>GPS Mock</button>
        <span className="loadedPill">Backend memory ON</span>
      </div></details>
      </>}
    </div>

    {cursor && !chartFullscreen && <div className="crosshairReadout">
      <b>{shortTime(cursor.time, timeframe)}</b>
      <span>{cursor.ohlc ? `C ${cursor.ohlc.close.toFixed(2)}` : `Price ${cursor.price?.toFixed(2)}`}</span>
      <span>{cursor.zone || 'No range'}{cursor.pct !== undefined ? ` · ${cursor.pct.toFixed(2)}%` : ''}</span>
    </div>}

      <div
        className={`${MAP_STUDIO_SHELL_CLASS}${navOverlayPanelOpen ? ' inspectorDockOpen' : ''}`}
        style={{
          ...MAP_STUDIO_SHELL_STYLE,
          gridTemplateColumns: navOverlayPanelOpen
            ? '60px 350px minmax(0, 1fr)'
            : MAP_STUDIO_SHELL_GRID,
        }}
      >
        <NavRail
          activeTab={rightDeckTab}
          onTabChange={handleNavOverlayTabChange}
          panelOpen={navOverlayPanelOpen}
        />

      <div className={`map-studio-inspector${navOverlayPanelOpen ? ' open' : ''}`} aria-hidden={!navOverlayPanelOpen}>
        {navOverlayPanelOpen && (
      <InspectorPanel
        className="inspectorPanelLeftDock"
        activeTab={rightDeckTab}
        onTabChange={handleInspectorTabChange}
        onClosePanel={() => setNavOverlayPanelOpen(false)}
        symbol={symbol}
        timeframe={timeframe}
        contextHint={inspectorContextHint}
        renderTab={function inspectorRenderTab(tab) {
          if (tab === 'dashboard') {
            return (
              <div className="rightTabPanel dashboardTabPanel">
                <InspectorOverviewDashboard variant="inspector" />
              </div>
            );
          }
          if (tab === 'narrative') {
            return (
        <div className="rightTabPanel narrativeTabPanel ledgerViewerPanel">
          <h3>Event Ledger</h3>
          <p className="mutedSmall">Raw saved facts for the active timeframe. This is the brain food. Narrative comes after the compiler understands the bones.</p>
          <div className="caseBadge">LEDGER · {symbol} {timeframe} · {eventLedgerRows.length} saved event{eventLedgerRows.length===1?'':'s'}</div>
          <div className="compilerPreviewCard">
            <b>Range Compiler Preview</b>
            <div><span>High</span><strong>{rangeCompilerPreview.high || 'not set'}</strong><em>{rangeCompilerPreview.highTime ? shortTime(rangeCompilerPreview.highTime, timeframe) : '—'}</em></div>
            <div><span>Low</span><strong>{rangeCompilerPreview.low || 'not set'}</strong><em>{rangeCompilerPreview.lowTime ? shortTime(rangeCompilerPreview.lowTime, timeframe) : '—'}</em></div>
            <div><span>Anchor events</span><strong>{rangeCompilerPreview.highCount}H / {rangeCompilerPreview.lowCount}L</strong><em>explicit Set M/W/D only</em></div>
          </div>
          <div className="htfLiteCard">
            <div className="htfLiteHeader"><b>HTF Engine Lite</b><span>{htfSemiAuto.state?.status || 'waiting'} · {htfSemiAuto.state?.candle_count || 0} candles</span></div>
            <div className="htfLiteGrid">
              <div><span>Location</span><strong>{htfSemiAuto.state?.location || '—'}</strong><em>{fmtPctOrDash(htfSemiAuto.state?.close_pct)}</em></div>
              <div><span>Range</span><strong>{hasRange ? `${low.toFixed(2)} → ${high.toFixed(2)}` : 'not set'}</strong><em>official anchors only</em></div>
              <div><span>Next Watch</span><strong>{htfSemiAuto.state?.next_watch || '—'}</strong><em>{timeframe}</em></div>
            </div>
            <div className="htfLiteNote">Overview stays lite. Objectives and ML fields are stored quietly for stats, because the chart is not a filing cabinet.</div>
          </div>
          <div className="ledgerRows">
            {eventLedgerRows.length === 0 && <div className="emptyNarrative"><b>No ledger rows yet</b><span>Click a candle, open Mark, save a bundle. The machine refuses to narrate air.</span></div>}
            {eventLedgerRows.map((ev:any, idx:number)=><button key={ev.id || `${ev.event_type}_${idx}`} className="ledgerRowButton" onClick={()=>jumpToLedgerEvent(ev)}>
              <b>#{idx + 1}</b>
              <span>{ev._label}</span>
              <em>{shortTime(ev.time, timeframe)} · {Number(ev.price).toFixed(2)}{ev.zone ? ` · ${ev.zone}` : ''}</em>
            </button>)}
          </div>
          <div className="narrativeHint">Click a ledger row to jump replay/camera to that candle. Range Compiler Preview is read-only for now. No mystical narrator yet, calm down humanity.</div>
        </div>
            );
          }
          if (tab === 'gps') {
            return (
        <div className="rightTabPanel gpsHierarchyTabPanel">
          {structuralExplorerPanelEl('explorerTreeScroll explorerTreeScrollGps')}
        </div>
            );
          }
          if (tab === 'campaign') {
            return (
        <div className="rightTabPanel campaignTabPanel">
          <label className="campaignYearRow">
            Campaign year
            <select value={explorerYearFilter} onChange={(e) => setExplorerYearFilter(e.target.value)}>
              <option value="all">All</option>
              {explorerYearOptions.map((y) => <option key={y} value={String(y)}>{y}</option>)}
            </select>
          </label>
          <MappingCampaignPanel
            status={campaignStatus}
            onContinue={handleCampaignContinue}
          />
          {mappingGaps.length > 0 && !campaignStatus.campaignComplete && (
            <p className="mappingCampaignHint mutedSmall">
              {mappingGaps.length} open gap{mappingGaps.length === 1 ? '' : 's'} in Hierarchy Tree queue
            </p>
          )}
        </div>
            );
          }
          if (tab === 'audit') {
            return (
        <div className="rightTabPanel auditTabPanel">
          <p className="mutedSmall">Backend-derived hierarchy proof. Mapping checkpoints refresh this automatically.</p>
          <div className="htfLiteGrid compactStateGrid miniPreviewGrid">
            <div><span>Macro</span><strong>{hierarchyAudit?.summary?.macro_ranges ?? '—'}</strong></div>
            <div><span>Weekly</span><strong>{hierarchyAudit?.summary?.weekly_ranges ?? '—'}</strong></div>
            <div><span>W→M</span><strong>{hierarchyAudit?.summary?.weekly_ranges_linked_to_macro ?? '—'}</strong></div>
            <div><span>Daily</span><strong>{hierarchyAudit?.summary?.daily_ranges ?? '—'}</strong></div>
            <div><span>D→W</span><strong>{hierarchyAudit?.summary?.daily_ranges_linked_to_weekly ?? '—'}</strong></div>
            <div><span>Invalid links</span><strong>{hierarchyAudit?.summary?.invalid_parent_links ?? '—'}</strong></div>
          </div>
          <div className="caseActionRow compactActionRow">
            <button type="button" className="gpsSaveBtn primary" onClick={refreshHierarchyAudit}>Refresh Audit</button>
            <button type="button" className="gpsSaveBtn secondary" onClick={exportCurrentMappingJson}>Export Mapping JSON</button>
            <button type="button" className="gpsSaveBtn secondary" onClick={exportAuditJson}>Export Audit JSON</button>
          </div>
          {hierarchyAudit && (
            <div className="caseBadge">{((hierarchyAudit.errors || []).length ? 'FAIL' : (hierarchyAudit.warnings || []).length ? 'WARN' : 'PASS')} · backend truth</div>
          )}
        </div>
            );
          }
          if (tab === 'tools') {
            return (
        <div className="rightTabPanel toolsTabPanel">
          <div className="toolsSectionNav markModeStrip compact">
            <button type="button" className={toolsPanelSection === 'correction' ? 'active' : ''} onClick={() => setToolsPanelSection('correction')}>Correction</button>
            <button type="button" className={toolsPanelSection === 'dashboard' ? 'active' : ''} onClick={() => setToolsPanelSection('dashboard')}>Dashboard</button>
            <button type="button" className={toolsPanelSection === 'narrative' ? 'active' : ''} onClick={() => setToolsPanelSection('narrative')}>Narrative</button>
            <button type="button" className={toolsPanelSection === 'trade' ? 'active' : ''} onClick={() => setToolsPanelSection('trade')}>Trade</button>
            <button type="button" className={toolsPanelSection === 'admin' ? 'active' : ''} onClick={() => setToolsPanelSection('admin')}>Admin</button>
          </div>
          {toolsPanelSection === 'correction' && (
            <div className="toolsCorrectionPane">
              <p className="mutedSmall">Manual save/correction — primary path is candle + keyboard (H/L/↑/↓).</p>
              <div className="caseActionRow compactActionRow">
                <button type="button" className="gpsSaveBtn" onClick={handleQuickRangeSave} disabled={structuralSaving || !rhAnchor.price || !rlAnchor.price}>{structuralSaving ? '…' : compactQuickSaveLabel}</button>
                <button type="button" className="gpsSaveBtn secondary" onClick={saveNextStructuralRange} disabled={structuralSaving || !saveNextRangeEligible.eligible}>Save Next Range</button>
                <button type="button" className="gpsSaveBtn secondary" onClick={() => void handleInspectorStructuralCommit()} disabled={inspectorCommitDisabled}>Force Commit</button>
              </div>
              <details className="structuralPanelDetails">
                <summary>Layer / source</summary>
                <div className="structuralScopeCompact">
                  <div className="markModeStrip compact structuralScopeStrip">
                    {STRUCTURE_LAYERS.map(layer => (
                      <button key={layer} type="button" className={structureLayer === layer ? 'active' : ''} onClick={() => selectStructureLayer(layer)}>{layer}</button>
                    ))}
                  </div>
                </div>
              </details>
            </div>
          )}
          {toolsPanelSection === 'dashboard' && (
            <div className="dashboardTabPanel"><InspectorOverviewDashboard variant="inspector" /></div>
          )}
          {toolsPanelSection === 'narrative' && inspectorRenderTab('narrative')}
          {toolsPanelSection === 'trade' && inspectorRenderTab('trade')}
          {toolsPanelSection === 'admin' && tab === 'tools' && (
            <div className="toolsAdminPane">
              <p className="mutedSmall">Case metadata and danger zone — not part of primary skeleton mapping.</p>
              <button type="button" className="gpsSaveBtn" onClick={() => saveSeedIdea(false)} disabled={caseSaving}>{caseSaving ? 'Saving…' : 'Update Case'}</button>
              <button type="button" className="gpsSaveBtn danger" onClick={deleteActiveCase} disabled={!activeCaseId}>Delete Active Case</button>
              <button type="button" className="gpsSaveBtn danger" onClick={resetResearchMappingDb}>Wipe Mapping Data</button>
            </div>
          )}
        </div>
            );
          }
          if (tab === 'mark') {
            return (
        <div className="rightTabPanel markTabPanel markPanelModern markWorkspaceV0879">
          <div className="markWorkspaceModeTabs">
            <button className={markWorkspaceMode==='htf'?'active':''} onClick={()=>setMarkWorkspaceMode('htf')}>Structural Map</button>
            <button className={markWorkspaceMode==='manual'?'active':''} onClick={()=>setMarkWorkspaceMode('manual')}>Manual Events</button>
            <button className={markWorkspaceMode==='case'?'active':''} onClick={()=>setMarkWorkspaceMode('case')}>Case Save</button>
          </div>

          {markWorkspaceMode === 'htf' && <div className="markModePane htfEnginePane structuralMapClean structuralMapWithCommitFooter">
            <div className="structuralMapScroll">
            {structuralMarkToolbarEl}

            <div className="structuralScopeCompact">
              <div className="markModeStrip compact structuralScopeStrip">
                {STRUCTURE_LAYERS.map(layer => (
                  <button key={layer} type="button" className={structureLayer === layer ? 'active' : ''} onClick={() => selectStructureLayer(layer)}>{layer}</button>
                ))}
              </div>
              <label className="structuralSourceTfLabel">Source
                <select value={sourceTimeframe} onChange={e => setSourceTimeframe(e.target.value)}>
                  {sourceTimeframeOptionsForLayer(structureLayer).map(tf => <option key={tf} value={tf}>{tf}</option>)}
                </select>
              </label>
            </div>

            {structureLayer === 'MACRO' && <div className="caseBadge compactBadge">Macro root · no parent required</div>}

            <section className="structuralReviewSection">
              <ReviewCandidatePanel
                apiBase={BASE_URL}
                symbol={symbol}
                structureLayer={structureLayer}
                sourceTimeframe={sourceTimeframe}
                parentRangeId={savePreview.parent_range_id != null ? Number(savePreview.parent_range_id) : null}
                activeRangeId={activeStructuralRangeId ? Number(activeStructuralRangeId) : null}
                caseRef={savePreview.case_ref || null}
                rangeHigh={activeStructuralRangeId ? (parseNum(rhAnchor.price) ?? parseNum(rangeHigh) ?? null) : null}
                rangeLow={activeStructuralRangeId ? (parseNum(rlAnchor.price) ?? parseNum(rangeLow) ?? null) : null}
                rangeScale={rangeScope}
                rangeRole={
                  selectedSavedRange
                    ? String(
                        selectedSavedRange.range_role
                        || (String(selectedSavedRange.range_scope || rangeScope).toUpperCase() === 'MINOR'
                          ? 'INTERNAL_LEG'
                          : 'ACTIVE_CONTAINER'),
                      )
                    : null
                }
                activeCandleTimeMs={detectorContextCandle?.time ? candleTimeMs(detectorContextCandle.time) : null}
                activeCandleTimeLabel={detectorContextCandle?.time ? shortTime(detectorContextCandle.time, sourceTimeframe) : null}
                replayMode={candleReplayMode}
                onPromoted={async () => {
                  try { await refreshSavedRangesForCurrentCase(); } catch {}
                  try { await refreshStructuralRanges(); } catch {}
                  try { await refreshHierarchyAudit(); } catch {}
                }}
                onViewOnChart={loadRangeAuditOnChart}
                setMessage={setMessage}
              />
            </section>

            {childMappingSession && (
              <section className="structuralReviewSection">
                <ChildMappingPanel
                  symbol={symbol}
                  session={childMappingSession}
                  guidedCursor={guidedCursor}
                  onSessionChange={setChildMappingSession}
                  onViewOnChart={loadRangeAuditOnChart}
                  onApplyCandidate={handleApplyChildCandidate}
                  onManualCreate={handleChildManualCreate}
                  onRequestSave={handleChildMappingSave}
                  onSkipGap={guidedCursor?.active ? handleGuidedSkipGap : undefined}
                  onParentComplete={guidedCursor?.active ? handleGuidedParentComplete : undefined}
                  onNextChild={guidedCursor?.active ? handleGuidedNextChild : undefined}
                  onClose={closeGuidedChildMapping}
                  setMessage={setMessage}
                />
              </section>
            )}

            <details className="structuralPanelDetails collapsedSection">
              <summary>Save Preview · {savePreview.actionLabel}</summary>
              <div className="htfLiteGrid compactStateGrid miniPreviewGrid">
                <div><span>Will Save</span><strong>{savePreview.structure_layer}</strong></div>
                <div><span>Source</span><strong>{savePreview.source_timeframe}</strong></div>
                <div><span>Parent</span><strong>{savePreview.parent_range_id ? `#${savePreview.parent_range_id}` : 'none'}</strong></div>
                <div><span>RH / RL</span><strong>{savePreview.range_high_price || '—'} / {savePreview.range_low_price || '—'}</strong></div>
                <div><span>Selected</span><strong>{activeStructuralRangeId || 'new'}</strong></div>
              </div>
              {!saveNextRangeEligible.eligible && saveNextRangeEligible.oldRangeId && activeStructuralRangeId && <div className="caseBadge">{saveNextRangeEligible.reason}</div>}
            </details>

            <details className="structuralPanelDetails collapsedSection">
              <summary>Anchor Draft · RH/RL/BH/BL</summary>
              <div className="htfLiteGrid compactStateGrid miniPreviewGrid">
                <div><span>RH</span><strong>{rhAnchor.price || 'not set'}</strong></div>
                <div><span>RL</span><strong>{rlAnchor.price || 'not set'}</strong></div>
                <div><span>Break Up</span><strong>{bhAnchor.price || 'not set'}</strong></div>
                <div><span>Break Down</span><strong>{blAnchor.price || 'not set'}</strong></div>
              </div>
              <div className="caseActionRow compactActionRow">
                <button type="button" onClick={() => setStructuralPoint('RH')} disabled={!selectedCandle && !replayCandle}>Range High</button>
                <button type="button" onClick={() => setStructuralPoint('RL')} disabled={!selectedCandle && !replayCandle}>Range Low</button>
                <button type="button" onClick={() => setStructuralPoint('BH')} disabled={!selectedCandle && !replayCandle}>Break Up</button>
                <button type="button" onClick={() => setStructuralPoint('BL')} disabled={!selectedCandle && !replayCandle}>Break Down</button>
                <button type="button" className="gpsSaveBtn secondary" onClick={undoLastQuickEvent} disabled={!canUndoQuickEvent || quickEventSaving}>Undo Last Event</button>
              </div>
              {lastRangeLifecyclePatchWarning && <div className="caseBadge warningBadge">{lastRangeLifecyclePatchWarning}</div>}
              {lastSavedQuickEvent && <div className="htfCandidateState mini"><span>Last: {lastSavedQuickEvent.role} · {lastSavedQuickEvent.structure_layer}/{lastSavedQuickEvent.source_timeframe}</span></div>}
            </details>

            <details className="structuralPanelDetails collapsedSection">
              <summary>Hierarchy Audit {hierarchyAudit ? `· ${((hierarchyAudit.errors || []).length ? 'FAIL' : (hierarchyAudit.warnings || []).length ? 'WARN' : 'PASS')}` : ''}</summary>
              <div className="htfLiteGrid compactStateGrid miniPreviewGrid">
                <div><span>Macro</span><strong>{hierarchyAudit?.summary?.macro_ranges ?? '—'}</strong></div>
                <div><span>Weekly</span><strong>{hierarchyAudit?.summary?.weekly_ranges ?? '—'}</strong></div>
                <div><span>W→M</span><strong>{hierarchyAudit?.summary?.weekly_ranges_linked_to_macro ?? '—'}</strong></div>
                <div><span>Daily</span><strong>{hierarchyAudit?.summary?.daily_ranges ?? '—'}</strong></div>
                <div><span>D→W</span><strong>{hierarchyAudit?.summary?.daily_ranges_linked_to_weekly ?? '—'}</strong></div>
                <div><span>Invalid</span><strong>{hierarchyAudit?.summary?.invalid_parent_links ?? '—'}</strong></div>
              </div>
              <div className="caseActionRow compactActionRow">
                <button type="button" className="gpsSaveBtn secondary" onClick={refreshHierarchyAudit}>Refresh Audit</button>
                <button type="button" className="gpsSaveBtn secondary" onClick={exportAuditJson}>Export Audit JSON</button>
              </div>
            </details>
            </div>
            <footer className="inspectorStructuralCommitFooter markCommitFooter">
              <div>
                <b>{inspectorCommitAction.label}</b>
                <span>{saveBlockReason || `${structureLayer} · ${sourceTimeframe} · RH ${rhAnchor.price || '—'} / RL ${rlAnchor.price || '—'}`}</span>
              </div>
              <button
                type="button"
                className={`inspectorCommitBtn${inspectorCommitFlash === 'success' ? ' inspectorCommitBtnSuccess' : ''}`}
                onClick={() => void handleInspectorStructuralCommit()}
                disabled={inspectorCommitDisabled}
                title={saveBlockReason || inspectorCommitAction.label}
              >
                {structuralSaving ? 'Committing…' : 'Commit'}
              </button>
            </footer>
          </div>}

          {markWorkspaceMode === 'manual' && <div className="markModePane manualEventsPane">
            <div className="markWorkbench manualMarkWorkbench">
              <aside className="markWorkbenchLeft">
                <div className="markPanelTitleRow"><div><h3>Manual Events</h3><p className="mutedSmall">Overrides, anchors, and special judgement. The event jungle is contained here, like it deserves.</p></div></div>
                <div className="markSelectedCard">
                  <b>Selected Candle</b>
                  <span>{selectedCandle ? `${shortTime(selectedCandle.time, timeframe)} · H ${selectedCandle.high.toFixed(2)} · L ${selectedCandle.low.toFixed(2)} · anchor ${selectedCandlePoint?.price?.toFixed?.(2) || 'n/a'}` : 'Click a candle to populate capture tools.'}</span>
                </div>
                <div className="markModeStrip compact">
                  <button className={toolMode==='inspect'?'active':''} onClick={()=>setToolMode('inspect')}>Pan</button>
                  <button className={toolMode==='select'?'active':''} onClick={()=>setToolMode('select')}>Click Candle</button>
                  <button className={toolMode==='scrub'?'active':''} onClick={()=>setToolMode('scrub')} disabled={!candleReplayMode}>Scrub Replay</button>
                </div>
                <div className="markQueueChips">
                  <b>Queue</b>
                  <div>{pendingMarkerRoles.length ? pendingMarkerRoles.map(role=><button key={role} onClick={()=>togglePendingMarkerRole(role)} title="Click to remove">{markerLabel(role)}</button>) : <span>Queue empty. Select events on the right.</span>}</div>
                </div>
                <div className="markCommitFooter modernMarkFooter">
                  <button className="clearQueueBtn" onClick={clearPendingMarkerSelection} disabled={!pendingMarkerRoles.length}>Cancel</button>
                  <button className="saveNarrativeBtn" onClick={savePendingMarkersToNarrative} disabled={bundleSaving || !pendingMarkerRoles.length || !selectedCandle}>{bundleSaving ? 'Saving...' : 'Save'}</button>
                </div>
              </aside>
              <section className="markEventTaxonomy">
                {selectedCandle ? <div className="markQuickGroups timeframeAwareGroups modernEventGroups">
                  {markerSections.map((section:any)=><details className="markerSection" key={section.title} open={section.defaultOpen}>
                    <summary>{section.title}</summary>
                    {section.groups.map((group:any)=><div className="markQuickGroup" key={group.title}>
                      <small>{group.title}</small>
                      <div>{group.items.map(([role,label]:any)=><button key={role} className={pendingMarkerRoles.includes(role) ? 'queued' : ''} onClick={()=>togglePendingMarkerRole(role)}>{label}</button>)}</div>
                    </div>)}
                  </details>)}
                  <div className="markQuickGroup dangerGroup"><small>Fix</small><div><button onClick={()=>{ clearPendingMarkerSelection(); clearSelectedCandleEvents(); }}>Clear Candle Events</button><button onClick={()=>{setSelectedCandle(null); setSelectedCandlePoint(null); setPendingMarkerRoles([]);}}>Close Selection</button></div></div>
                </div> : <div className="markEmptyState">Select a candle on the chart first. The app cannot mark imaginary candles, despite humanity’s best efforts.</div>}
              </section>
            </div>
          </div>}

          {markWorkspaceMode === 'case' && <div className="markModePane caseQuickPane">
            <div className="caseQuickHeader"><div><h3>Case Save</h3><p className="mutedSmall">Update Case saves the container only. Use Save Range for RH/RL.</p></div></div>
            <div className="activeCaseCard"><span>Active Case</span><b>{activeCaseDisplayId ? (cleanCaseDisplayName(seedName) || cleanCaseDisplayName(activeCaseLabel)) : 'None'}</b><button onClick={resetActiveCase} disabled={!activeCaseDisplayId}>Clear Active</button></div>
            <div className="caseActionRow">
              <button className="gpsSaveBtn" onClick={startNewCase}>New Case</button>
              <button className="gpsSaveBtn" onClick={()=>saveSeedIdea(false)} disabled={caseSaving}>{caseSaving ? 'Saving...' : (getCurrentMappingCaseRef().hasCase ? 'Update Case' : 'Create Case')}</button>
              <button className="gpsSaveBtn danger" onClick={deleteActiveCase} disabled={!activeCaseId}>Delete Active</button>
            </div>
            {caseSavedNotice && <div className="caseSavedNotice">✓ {caseSavedNotice}</div>}
            <div className="caseScopeStrip">
              {(['MACRO','WEEKLY','DAILY','INTRADAY','MICRO'] as CaseScope[]).map(scope=><button key={scope} className={caseScope===scope?'active':''} onClick={()=>setCaseScope(scope)}>{scopeLabel(scope)}</button>)}
            </div>
            <div className="seedGrid compactCaseGrid">
              <label>Case Name<input value={seedName} onChange={e=>setSeedName(e.target.value)} placeholder="XAUUSD 2020 Q1" /></label>
              <label>Replay Candle<input readOnly value={activeReplayCandle ? `${shortTime(activeReplayCandle.time, timeframe)} · C ${activeReplayCandle.close.toFixed(2)}` : 'No candle selected'} /></label>
              <label>Case High<input value={caseHigh || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_high:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
              <label>Case Low<input value={caseLow || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_low:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
              <label>Window Start<input value={caseWindowStartDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_start_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
              <label>Window End<input value={caseWindowEndDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_end_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
            </div>
            <div className="seedAnchorBtns compactCaseBtns">
              <button onClick={autoFillCaseAnchors}>Auto-fill All HTF Marks</button>
              <button onClick={()=>captureCaseAnchor('high')}>Use Candle High as Case H</button>
              <button onClick={()=>captureCaseAnchor('low')}>Use Candle Low as Case L</button>
              <button onClick={applyQuarterCaseName}>Name Quarter</button>
              <button onClick={buildCaseNameFromWindow}>Name From Window</button>
              <button onClick={buildYtdCaseName}>Name YTD</button>
            </div>
            <label className="seedNotes">Notes<textarea value={seedNotes} onChange={e=>setSeedNotes(e.target.value)} placeholder="What this case shows, what was marked, and what the expected/actual path was." /></label>
            {activeCaseRecord && <div className="caseLedgerDetail compactCaseLedger">
              <div className="caseLedgerHeader"><b>Case Ledger Preview</b><span>{activeCaseLedger.scope} · {activeCaseLedger.timeframe} · {activeCaseLedger.rows.length} linked</span></div><div className="caseActionRow miniAuditRow"><button className="gpsSaveBtn secondary" onClick={exportActiveCaseAuditJson}>Export Case JSON</button></div>
              <div className="caseLedgerRows">
                {activeCaseLedger.rows.length === 0 && <div className="caseLedgerEmpty">No linked event rows yet.</div>}
                {activeCaseLedger.rows.slice(0,18).map((ev:any, idx:number)=><button key={ev.id || `${ev.event_type}_${idx}`} onClick={()=>jumpToCaseLedgerEvent(ev)}><b>#{idx + 1}</b><span>{ev._label}</span><em>{shortTime(ev.time, String(activeCaseLedger.timeframe))} · {Number(ev.price).toFixed(2)}</em></button>)}
              </div>
            </div>}
          </div>}
        </div>
            );
          }
          if (tab === 'seed') {
            return (
        <div className="rightTabPanel seedTabPanel">
        <div className="seedIdeaPanel sideSeedPanel caseManagerCompact">
      <div className="seedHeader caseManagerHeader compactCaseHeader">
        <div><b>Case Manager</b><span>Active case · hierarchy · navigation</span></div>
      </div>

      <div className="activeCaseCard compactActiveCase">
        <div className="activeCaseMain">
          <span>Active Case</span>
          <b>{activeCaseDisplayId ? (cleanCaseDisplayName(seedName) || cleanCaseDisplayName(activeCaseLabel) || activeCaseDisplayId.slice(0, 8)) : 'None — start below'}</b>
        </div>
        <label className="caseNameField">Case name
          <input value={seedName} onChange={e=>setSeedName(e.target.value)} placeholder="XAUUSD 2020 Q1" />
        </label>
        <div className="caseNameQuickRow">
          <button type="button" className="caseToolbarBtn caseToolbarBtnMaster" onClick={applyMasterCaseName} title="One master tree 2019–2026">
            Master 2019–2026
          </button>
          <button type="button" className="caseToolbarBtn" onClick={applyQuarterCaseName} title="Name from selected/replay candle quarter">Name Quarter</button>
          {[1, 2, 3, 4].map((q) => {
            const anchor = quarterFromTime(selectedCandle?.time || replayCandle?.time || activeReplayCandle?.time);
            const year = anchor?.year || new Date().getFullYear();
            return (
              <button key={q} type="button" className="caseToolbarBtn caseQuarterChip" onClick={() => applyQuarterCaseNameFor(year, q)}>{year} Q{q}</button>
            );
          })}
        </div>
        <div className="caseManagerToolbar">
          <button type="button" className="caseToolbarBtn" onClick={startNewCase}>New Case</button>
          <button type="button" className="caseToolbarBtn" onClick={resetActiveCase} disabled={!activeCaseDisplayId && !cleanCaseDisplayName(seedName)}>Clear Active</button>
          <button type="button" className="caseToolbarBtn primary" onClick={()=>saveSeedIdea(false)} disabled={caseSaving}>{caseSaving ? '…' : (getCurrentMappingCaseRef().hasCase ? 'Update Case' : 'Create Case')}</button>
        </div>
      </div>

      {caseLoadStatus && <div className="caseBadge">{caseLoadStatus}</div>}
      {caseSavedNotice && <div className="caseSavedNotice">✓ {caseSavedNotice}</div>}

      <div className="seedIdeaList compactCaseList savedCasesPanel">
        <div className="savedCasesHeader">
          <b>Saved cases (from VPS)</b>
          <button type="button" className="caseToolbarBtn" onClick={() => loadSavedCasesFromBackend()}>Refresh</button>
        </div>
        {savedCaseIdeas.length === 0 && (
          <div className="caseLedgerEmpty">No saved cases for {symbol} yet. Create one below, or click Refresh after saving on another device.</div>
        )}
        {savedCaseIdeas.map((x:any) => {
          const caseKey = String(x.raw_case_id || x.id || '');
          const isActive = caseKey === String(activeCaseDisplayId || '');
          const displayName = cleanCaseDisplayName(x.seed_name || x.raw_case?.case_name) || 'Unnamed case';
          const tf = String(x.case_timeframe || x.replay_timeframe || x.raw_case?.base_timeframe || 'W1').toUpperCase();
          return (
            <button key={caseKey} type="button" className={`savedCaseRow ${isActive ? 'active' : ''}`} onClick={() => openSavedCase(x)}>
              <span className="savedCaseName">{displayName}</span>
              <span className="savedCaseMeta">{tf}{x.replay_candle_time ? ` · ${shortTime(x.replay_candle_time, tf)}` : ''}</span>
            </button>
          );
        })}
      </div>

      <details className="caseMetadataDetails" open={caseMetadataOpen} onToggle={e => setCaseMetadataOpen((e.target as HTMLDetailsElement).open)}>
        <summary>Case Metadata</summary>
        <div className="caseScopeStrip compactScopeStrip">
          {(['MACRO','WEEKLY','DAILY','INTRADAY','MICRO'] as CaseScope[]).map(scope=><button key={scope} type="button" className={caseScope===scope?'active':''} onClick={()=>setCaseScope(scope)}>{scopeLabel(scope)}</button>)}
        </div>
        <div className="seedGrid compactSeedGrid">
          <label>Case Name<input value={seedName} onChange={e=>setSeedName(e.target.value)} /></label>
          <label>Case Timeframe<input readOnly value={`${scopeLabel(caseScope)} · ${caseTimeframe}`} /></label>
          <label>Replay Candle<input readOnly value={activeReplayCandle ? `${shortTime(activeReplayCandle.time, timeframe)} · C ${activeReplayCandle.close.toFixed(2)}` : 'No candle selected'} /></label>
          <label>Case High<input value={caseHigh || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_high:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
          <label>Case Low<input value={caseLow || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_low:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
          <label>Window Start<input value={caseWindowStartDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_start_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
          <label>Window End<input value={caseWindowEndDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_end_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
        </div>
        <div className="seedAnchorBtns compactAnchorBtns">
          <button type="button" onClick={autoFillCaseAnchors}>Auto-fill HTF</button>
          <button type="button" onClick={()=>captureCaseAnchor('high')}>Case H</button>
          <button type="button" onClick={()=>captureCaseAnchor('low')}>Case L</button>
          <button type="button" onClick={applyQuarterCaseName}>Name Quarter</button>
          <button type="button" onClick={buildCaseNameFromWindow}>Name Window</button>
          <button type="button" onClick={buildYtdCaseName}>Name YTD</button>
        </div>
        <label className="seedNotes">Notes<textarea value={seedNotes} onChange={e=>setSeedNotes(e.target.value)} placeholder="What this case shows, what was marked, and what the expected/actual path was." /></label>
      </details>

      <details className="dangerZoneDetails">
        <summary>Danger Zone</summary>
        <div className="dangerZoneBox">
          <button type="button" className="caseToolbarBtn danger" onClick={deleteActiveCase} disabled={!activeCaseId}>Delete Active Case</button>
          <button type="button" className="caseToolbarBtn danger" onClick={clearAllCases}>Clear All Cases</button>
          <span>Wipe Mapping Research Data deletes legacy + raw mapping cases/events, structural ranges, map events, HTF snapshots, objectives, and route memory for all symbols. Raw candles stay. Also clears local replay, drawings, and case selection.</span>
          <button type="button" className="caseToolbarBtn danger" onClick={resetResearchMappingDb}>Wipe All Mapping Data</button>
        </div>
      </details>
    </div>
        </div>
            );
          }
          if (tab === 'trade') {
            return (
        <MapTradeIdeaPanel
          symbol={symbol}
          timeframe={timeframe}
          draft={tradeIdeaDraft}
          pickMode={tradePickMode}
          setPickMode={setTradePickMode}
          savedIdeas={chartTradeIdeas}
          selectedIdeaId={selectedTradeIdeaId}
          setSelectedIdeaId={setSelectedTradeIdeaId}
          linkedRangeLabel={linkedTradeRangeLabel}
          notes={tradeIdeaNotes}
          setNotes={setTradeIdeaNotes}
          onClearDraft={() => { setTradeIdeaDraft(emptyTradeIdeaDraft()); setTradePickMode(null); }}
          onSave={handleSaveTradeIdea}
          onDelete={handleDeleteTradeIdea}
          onExport={handleExportTradeIdeas}
          saving={tradeIdeaSaving}
          shortTime={shortTime}
        />
            );
          }
          return null;
        }}
      />
        )}
      </div>

    <div className={`map-studio-chart${chartFullscreen ? ' chartFullscreenMode' : ''}`}>
      <div className={`d3ChartCard ${chartFullscreen ? 'chartFullscreenCard' : ''}`}>
        <div className="chartTitleRow chartTitleRowMap compactChartTitle">
          <h3>{symbol} {timeframe}</h3>
          <span>{chartStatusLine}</span>
          {campaignViewContextEnabled && (
            <MappingViewContextSwitcher
              viewContext={mappingViewContext}
              parentTimeframe={campaignParentChartTf}
              childTimeframe={campaignChildChartTf}
              parentPointCount={campaignParentChartTf ? mappingDraftPointCountForTimeframe(campaignParentChartTf) : 0}
              childPointCount={mappingDraftPointCountForTimeframe(campaignChildChartTf)}
              onChange={handleMappingViewContextChange}
              isClamped={viewportIsClamped}
              canDrillDown={viewportCanDrillDown}
              onDrillDown={handleDrillDownViewport}
              onUnlockGlobalView={handleUnlockGlobalView}
            />
          )}
          <div className="chartTitleRowEventBrowserDock">
            <button
              type="button"
              className={`eventBrowserPanelToggle${eventBrowserOpen ? ' open' : ''}`}
              onClick={() => setEventBrowserOpen((open) => !open)}
              aria-pressed={eventBrowserOpen}
              title="Event Browser"
            >
              Events
            </button>
          </div>
        </div>
        {replayMode && currentPlaybackFrame && <div className={`replayFrameBanner ${String(currentPlaybackFrame.lookahead_result || '').toLowerCase()}`}>
          <div><b>Replay Frame {playbackIndex + 1}/{playbackFrames.length}</b><span>{currentPlaybackFrame.frame_timestamp}</span></div>
          <div><strong>{currentPlaybackFrame.phase}</strong><span>{currentPlaybackFrame.lifecycle_state} · {currentPlaybackFrame.parent_context_mode}</span></div>
          <div><strong>{currentPlaybackFrame.current_zone}</strong><span>{currentPlaybackFrame.objective_code} · {currentPlaybackFrame.profile_type}</span></div>
          <div><strong>{currentPlaybackFrame.lookahead_result || 'RAW'}</strong><span>{currentPlaybackFrame.trigger_event}</span></div>
        </div>}
        {candleReplayMode && replayCandle && <div className="chartReplayOverlay">
          <b>Bar Replay · {timeframe}</b>
          <span>{effectiveReplayIndex + 1}/{candles.length} · {shortTime(replayCandle.time, timeframe)}</span>
          <span>{replaySelectBarMode ? 'Scrub tool: click chart to set replay bar' : candleReplayPlaying ? 'Playing…' : 'Use Scrub tool to move replay cursor'}</span>
        </div>}
        {activeParentRangeOverlay.length > 0 && <div className="parentRangeMiniBar" title="Parent range reference only. Jump/replay controls moved out of the chart body because apparently buttons enjoy standing in front of candles.">
          <b>{activeParentRangeOverlay[0]?.structureLayer || activeParentRangeOverlay[0]?.timeframe} parent</b>
          <span>{activeParentRangeOverlay.map(x=>`${x.kind.toUpperCase()} ${Number(x.price).toFixed(2)}`).join(' · ')}</span>
        </div>}
        {!chartFullscreen && showStructuralMappingRibbon && structuralMappingRibbonEl}
        {!chartFullscreen && inspectorRailHidden && showStructuralMappingRibbon && (
          <div className="structuralMappingDock compact chartQuickDock">
            {structuralQuickAnchorBarEl}
          </div>
        )}
        {chartFullscreen && <div className="structuralMappingDock compact">
          {showStructuralMappingRibbon && structuralMappingRibbonEl}
          {chartDrawToolbarEl}
          {structuralQuickAnchorBarEl}
        </div>}
        {chartFullscreen && <div className="fullscreenTfDock" aria-label="Fullscreen timeframe controls">
          {(['MN1','W1','D1','H4','H1','M15'] as string[]).map(tf => {
            const locked = chartRenderer === 'd3' && showStructuralMappingRibbon && !mappingAllowedChartTfs.includes(tf);
            return <button key={tf} type="button" className={`${timeframe===tf?'active':''}${locked?' tfLocked':''}`} disabled={locked} title={locked ? `Blocked while mapping ${structureLayer}` : tf} onClick={()=>handleChartTfSwitch(tf)}>{tf}</button>;
          })}
          <select value={cameraMode} onChange={e=>setCameraMode(e.target.value as any)}><option value="AUTO">Auto</option><option value="LOCKED">Lock</option><option value="CASE">Case</option><option value="REPLAY">Replay</option></select>
        </div>}
        <div ref={chartMapStageRef} className="chartMapStage chartPilotLayer chart-parent-wrapper">
        {autoResume.isWelcome && !candles.length && (
          <div className="mapStudioWelcome" aria-live="polite">
            <h3>Welcome to Map Studio</h3>
            <p>Choose a symbol and timeframe, then start your first mapping session. Your last chart context will resume automatically next time.</p>
            <button type="button" className="mapStudioWelcomeBtn" onClick={() => void autoResume.beginFirstSession()}>
              Start mapping
            </button>
          </div>
        )}
        {chartHudCandleTime && <div className="chartCrosshairHud" aria-live="polite">
          <b>{shortTime(chartHudCandleTime, timeframe)}</b>
          {chartHudPrice != null && Number.isFinite(Number(chartHudPrice)) && <span>{Number(chartHudPrice).toFixed(2)}</span>}
        </div>}
        {eventBrowserOpen && (
          <EventBrowserPanel
            forest={caseHierarchyForest}
            resolveRowHighlight={eventBrowserRowHighlight}
            onRowClick={jumpToStructuralRange}
            onClose={() => setEventBrowserOpen(false)}
            formatRowLabel={eventBrowserFormatRowLabel}
            emptyMessage={savedStructuralRanges.length ? 'No ranges match this filter.' : 'No saved structural ranges for this case yet.'}
            boundsRef={chartMapStageRef}
          />
        )}
        {!chartFullscreen && chartRenderer === 'd3' && <div className="chartGestureHint" aria-hidden="true">Sel: one click picks a candle · Pan: drag chart · Scroll to zoom · Double-click resets price view</div>}
        {!chartFullscreen && chartRenderer === 'd3' && chartDrawToolbarEl}
        <div className="chartMapCanvas chart-canvas">
        {chartRenderer === 'tradingview' ? (
          <LiveViewPanel
            candles={tradingViewDisplayCandles}
            symbol={symbol}
            timeframe={timeframe}
            sourceTimeframe={sourceTimeframe}
            loadedTimeframe={loadedCandleContext?.chartTimeframe || null}
            revision={candleDataRevision}
            statusMessage={message}
            overlayMode={tradingViewOverlayMode}
            overlays={tradingViewOverlays}
            fitRequest={tradingViewFitRequest}
            chartMode={tradingViewChartMode}
            selectionMode={tradingViewSelectedCandleMode}
            selectedCandle={tradingViewChartSelectedCandle}
            crosshairCandle={tradingViewCrosshairCandle}
            selectionWarning={tradingViewSelectionWarning}
            onCrosshairCandle={setTradingViewCrosshairCandle}
            onCandleClick={handleTradingViewCandleClick}
            onOverlayModeChange={setTradingViewOverlayModeRaw}
            onSelectionModeChange={setTradingViewSelectedCandleModeRaw}
            mappingInputMode={tradingViewMappingInputMode}
            onMappingInputModeChange={setTradingViewMappingInputRaw}
          />
        ) : (
        <D3CandleMap
          candles={candles}
          candleDataRevision={candleDataRevision}
          replayCutTime={candleReplayMode && replayCandle ? replayCandle.time : null}
          timeframe={timeframe}
          rangeHigh={high}
          rangeLow={low}
          rangeStart={rangeWindow.start}
          rangeEnd={rangeWindow.end}
          hasRange={hasRange}
          caseStart={activeCaseLedger?.start || ''}
          caseEnd={activeCaseLedger?.end || ''}
          caseHigh={activeCaseLedger?.high || ''}
          caseLow={activeCaseLedger?.low || ''}
          parentOverlays={activeParentRangeOverlay}
          savedRangeOverlays={chartSavedRangeOverlays}
          draftRangeOverlay={chartDraftRangeOverlay}
          focusMode={chartMappingFocusMode}
          guidedCursorTimeMs={guidedCursor?.active ? guidedCursor.cursor_time_ms : null}
          guidedParentEndMs={guidedCursor?.active ? guidedCursor.parent_end_time_ms : null}
          showFibOverlays={false}
          events={visibleEvents}
          selectedCandleTime={selectedCandle?.time || null}
          selectedCandlePrice={selectedCandlePoint?.price ?? null}
          eventType={eventType}
          toolMode={toolMode}
          chartDrawings={chartDrawings}
          chartDrawTool={chartDrawTool}
          chartDrawColor={chartDrawColor}
          selectedDrawingId={selectedDrawingId}
          onDrawingsChange={updateChartDrawings}
          onSelectedDrawingChange={setSelectedDrawingId}
          chartTradeIdeas={chartTradeIdeas}
          tradeIdeaDraft={tradeIdeaDraft}
          tradePickMode={tradePickMode}
          selectedTradeIdeaId={selectedTradeIdeaId}
          onTradeLevelPick={handleTradeLevelPick}
          autoscaleToken={autoscaleToken}
          scaleMode={scaleMode}
          jumpLatestToken={jumpToken}
          fitAllToken={fitToken}
          goDate={jumpDate}
          replayCursorEnabled={candleReplayMode && toolMode === 'scrub'}
          onReplayCursorChange={setCandleReplayFrameByTime}
          onCursor={setCursor}
          onAddEvent={addEventAt}
          onUpdateEvent={updateEvent}
          onFinishEventDrag={finishEventDrag}
          onCandleSelect={(payload)=>{
            if (candleReplayMode && replayCandle?.time
              && !isReplaySelectableCandle(payload.candle.time, replayCandle.time, true)) {
              return;
            }
            setSelectedCandle(payload.candle);
            setPendingMarkerRoles([]);
            setSelectedCandlePoint({ price: Number(payload.price.toFixed(2)), clientX: payload.clientX, clientY: payload.clientY });
            const hasRh = !!String(rhAnchor.price || '').trim();
            const hasRl = !!String(rlAnchor.price || '').trim();
            if (hasRh && !hasRl) {
              setMessage(`Selected ${shortTime(payload.candle.time, timeframe)} for RL · L ${payload.candle.low.toFixed(2)}. Click RL.`);
            } else if (!hasRh && hasRl) {
              setMessage(`Selected ${shortTime(payload.candle.time, timeframe)} for RH · H ${payload.candle.high.toFixed(2)}. Click RH.`);
            } else if (!hasRh) {
              setMessage(`Selected ${shortTime(payload.candle.time, timeframe)} · H ${payload.candle.high.toFixed(2)} · L ${payload.candle.low.toFixed(2)}. Click RH or RL.`);
            } else {
              setMessage(`Selected ${shortTime(payload.candle.time, timeframe)} · anchor ${payload.price.toFixed(2)}.`);
            }
          }}
          cameraMode={cameraMode}
          cameraCommand={cameraCommand}
          lockedCameraDomain={lockedCameraDomain}
          lockedPriceDomain={cameraPriceDomainByCaseTf[cameraKey] || null}
          cameraKey={cameraKey}
          cameraViewOwner={cameraViewOwner}
          onCameraViewOwnerChange={setCameraViewOwnerWithLog}
          candleWidthScale={candleWidthScale}
          priceZoomScale={priceZoomScale}
          onCameraDomainChange={(dom)=>{ if (cameraMode === 'LOCKED') setCameraDomainByCaseTf(prev=>({ ...prev, [cameraKey]: dom })); }}
          onVisibleDomainChange={persistVisibleCameraDomain}
          viewportClamp={viewportIsClamped && viewportActiveClamp ? viewportActiveClamp : null}
          chartEmptyState={autoResume.isAutoResuming ? 'loading' : autoResume.isWelcome && !candles.length ? 'welcome' : 'empty'}
          isInspectorOpen={navOverlayPanelOpen}
          onRangeChange={({high, low, start, end})=>{
            if (typeof high === 'number' && Number.isFinite(high)) setRangeHigh(String(Number(high.toFixed(2))));
            if (typeof low === 'number' && Number.isFinite(low)) setRangeLow(String(Number(low.toFixed(2))));
            if (typeof start === 'string') setRangeWindow({ start });
            if (typeof end === 'string') setRangeWindow({ end });
          }}
        />
        )}
        </div>
        </div>
      </div>
      {chartFullscreen && <div className="fullscreenBottomBar" aria-label="Fullscreen chart controls">
        <div className="fullscreenChromeDock" aria-label="Fullscreen layout chrome">
          <button type="button" className="active" onClick={() => setChartFullscreen(false)} title="Exit full chart mode">
            Exit Full
          </button>
        </div>
        <div className="fullscreenReplayDock" aria-label="Fullscreen replay controls">
          <button onClick={()=>setCandleReplayFrame(effectiveReplayIndex - 1)} disabled={!candles.length || effectiveReplayIndex <= 0}>◀</button>
          <button className={candleReplayPlaying?'active':''} onClick={() => void toggleCandleReplayPlay()} disabled={!candles.length || (!candleReplayPlaying && replayForwardBlocked)}>{candleReplayPlaying ? 'Pause' : 'Play'}</button>
          <button onClick={() => void stepReplayForwardOne()} disabled={!candles.length || replayForwardBlocked}>▶</button>
          <button onClick={jumpToParentRangeStart} disabled={!activeParentRangeOverlay.length}>Parent</button>
          <button onClick={startChildReplayFromParentStart} disabled={!activeParentRangeOverlay.length}>Child Replay</button>
          <span>{candles.length ? `${Math.min(effectiveReplayIndex + 1, candles.length)}/${candles.length}` : 'No candles'}{replayCandle ? ` · ${shortTime(replayCandle.time, timeframe)} · C ${replayCandle.close.toFixed(2)}` : ''}</span>
        </div>
        <div className="fullscreenCameraDock" aria-label="Fullscreen zoom and fit controls">
          <div className="fullscreenScaleDock">
            <button onClick={()=>bumpCandleWidth(-0.15)}>W−</button><span>{Number(candleWidthScale).toFixed(2)}</span><button onClick={()=>bumpCandleWidth(0.15)}>W+</button>
            <button onClick={()=>bumpPriceZoom(-0.15)}>H−</button><span>{Number(priceZoomScale).toFixed(2)}</span><button onClick={()=>bumpPriceZoom(0.15)}>H+</button>
            <button onClick={resetCameraScale}>Reset</button>
          </div>
          <div className="fullscreenFitDock">
            <button onClick={fitRangeView}>Fit Range</button>
            <button onClick={fitReplayView}>Fit Replay</button>
            <button onClick={fitCaseView}>Fit Case</button>
            <button onClick={fitAllView}>Fit All</button>
            <button onClick={lockCurrentView}>Lock View</button>
          </div>
        </div>
      </div>}
    </div>
    </div>

    {candleReplayMode && <div className="fixedBottomReplayDock tvReplayDock" aria-label="Bar replay controls">
      <div className="tvReplayStartGroup">
        <button
          type="button"
          className={`tvReplaySelectBar${replaySelectBarMode ? ' active' : ''}`}
          onClick={() => { setReplayStartMenuOpen((o) => !o); setReplaySelectBarMode(true); }}
          disabled={!candles.length}
          title="Select starting point"
        >
          Select bar {replayStartMenuOpen ? '▾' : '▴'}
        </button>
        {replayStartMenuOpen && <div className="tvReplayStartMenu" role="menu">
          <button type="button" role="menuitem" onClick={() => { setReplaySelectBarMode(true); setReplayStartMenuOpen(false); setMessage('Click any candle on the chart to set replay start.'); }}>Bar — click chart</button>
          <button type="button" role="menuitem" onClick={jumpReplayToDate}>Date… (use jump date)</button>
          <button type="button" role="menuitem" onClick={() => { setCandleReplayFrame(0); setReplayStartMenuOpen(false); }}>First available date</button>
          <button type="button" role="menuitem" onClick={pickRandomReplayBar}>Random bar</button>
        </div>}
      </div>
      <button type="button" onClick={() => setCandleReplayFrame(effectiveReplayIndex - 1)} disabled={!candles.length || effectiveReplayIndex <= 0} title="Step back one bar">⏮</button>
      <button type="button" className={candleReplayPlaying ? 'active' : ''} onClick={() => void toggleCandleReplayPlay()} disabled={!candles.length || (!candleReplayPlaying && replayForwardBlocked)} title={replayForwardBlocked && !candleReplayPlaying ? replayPlayForwardStatusMessage('no-loaded-candles-ahead') : 'Play / pause'}>{candleReplayPlaying ? 'Pause' : 'Play'}</button>
      <button type="button" onClick={() => void stepReplayForwardOne()} disabled={!candles.length || replayForwardBlocked} title="Step forward one bar">⏭</button>
      <select
        className="tvReplaySpeed"
        value={replaySpeedLabel}
        onChange={(e) => {
          const opt = REPLAY_SPEED_OPTIONS.find((o) => o.label === e.target.value);
          if (opt) setCandleReplaySpeedMs(opt.ms);
        }}
        title="Playback speed"
      >
        {REPLAY_SPEED_OPTIONS.map((o) => <option key={o.label} value={o.label}>{o.label}</option>)}
      </select>
      <span className="tvReplayTf">{timeframe}</span>
      <input
        className="replaySlider dockReplaySlider tvReplaySlider"
        type="range"
        min={0}
        max={Math.max(0, candles.length - 1)}
        value={Math.min(effectiveReplayIndex, Math.max(0, candles.length - 1))}
        onChange={(e) => setCandleReplayFrame(Number(e.target.value))}
        disabled={!candles.length}
        title="Scrub replay cursor"
      />
      <span className="dockMetaText">{candles.length ? `${Math.min(effectiveReplayIndex + 1, candles.length)}/${candles.length}` : 'No candles'}{replayCandle ? ` · ${shortTime(replayCandle.time, timeframe)}` : ''}</span>
      <button type="button" className="tvReplayExit" onClick={exitBarReplayToLive} disabled={!candles.length} title="Exit replay and jump to latest">⏩|</button>
    </div>}
    {pendingMappingSession && (
      <MappingSessionResumeModal
        session={pendingMappingSession}
        onResume={() => void handleMappingSessionResume()}
        onStartNew={handleMappingSessionStartNew}
        onOpenExplorer={handleMappingSessionOpenExplorer}
      />
    )}
  </div>;
}

type ParentRangeOverlayLine = { timeframe:string; structureLayer?:StructureLayer; kind:'high'|'low'; price:number; label:string; rangeId?:string|number|null; direction?:string; start?:string; end?:string; };

function structureLayerLineColor(layer: StructureLayer): string {
  const map: Record<StructureLayer, string> = {
    MACRO: '#a855f7',
    WEEKLY: '#ef4444',
    DAILY: '#22c55e',
    INTRADAY: '#3b82f6',
    MICRO: '#facc15',
  };
  return map[layer] || '#94a3b8';
}

function savedRangeLineStyle(status: string, opts?: { isParentContext?: boolean; isActive?: boolean; rangeScope?: RangeScope; structureLayer?: StructureLayer | string }) {
  const s = String(status || 'ACTIVE').toUpperCase();
  const broken = s === 'BROKEN' || s === 'ABANDONED' || s === 'INACTIVE' || s === 'REPLACED';
  const isMinor = opts?.rangeScope === 'MINOR';
  const layer = String(opts?.structureLayer || '').toUpperCase();
  const primaryGuide = layer === 'WEEKLY' || layer === 'DAILY';

  if (opts?.isParentContext) {
    return {
      opacity: broken ? 0.88 : (primaryGuide ? 0.98 : 0.96),
      dash: broken ? '8 5' : (isMinor ? '4 4' : ''),
      width: primaryGuide ? 3.6 : (isMinor ? 2.8 : 3.4),
    };
  }
  if (opts?.isActive && !broken) {
    return { opacity: 0.98, dash: isMinor ? '5 4' : '', width: isMinor ? 3.4 : 4.2 };
  }
  if (broken) {
    return { opacity: 0.55, dash: '5 5', width: 2.2 };
  }
  if (isMinor) {
    return { opacity: 0.88, dash: '4 5', width: 2.6 };
  }
  return {
    opacity: primaryGuide ? 0.94 : 0.9,
    dash: primaryGuide ? '' : '3 6',
    width: primaryGuide ? 3.4 : 3.0,
  };
}

function draftRangeLineStyle(anchorsComplete = false) {
  if (anchorsComplete) return { opacity: 1, dash: '', width: 4.2 };
  return { opacity: 0.78, dash: '4 6', width: 3.2 };
}

function paintChartTradeIdea(
  plot: d3.Selection<SVGGElement, unknown, null, undefined>,
  spec: TradeIdeaOverlaySpec,
  zx: d3.ScaleTime<number, number>,
  y: d3.ScaleLinear<number, number>,
  defaultBarMs: number,
) {
  if (!spec.entry) return;
  const entryDate = candleTimeDate(spec.entry.time);
  if (!Number.isFinite(entryDate.getTime())) return;
  const x1 = snapChartStrokePx(zx(entryDate));
  const endDate = tradeIdeaEndDate(spec.entry, [spec.tp1, spec.tp2, spec.tp3], defaultBarMs);
  const x2 = snapChartStrokePx(zx(endDate));
  if (!Number.isFinite(x1) || !Number.isFinite(x2) || x2 <= x1) return;

  const entryY = y(spec.entry.price);
  const opacity = spec.draft ? 0.72 : spec.selected ? 1 : 0.9;
  const dash = spec.draft ? '6 4' : undefined;
  const g = plot.append('g')
    .attr('class', `chartTradeIdea${spec.draft ? ' draft' : ''}${spec.selected ? ' selected' : ''}`)
    .attr('data-id', spec.id || 'draft')
    .attr('pointer-events', 'none');

  if (spec.sl) {
    const slY = y(spec.sl.price);
    const yTop = Math.min(entryY, slY);
    const yBot = Math.max(entryY, slY);
    g.append('rect')
      .attr('x', x1).attr('y', yTop)
      .attr('width', Math.max(2, x2 - x1))
      .attr('height', Math.max(1, yBot - yTop))
      .attr('fill', TRADE_IDEA_COLORS.riskFill)
      .attr('opacity', opacity);
  }

  const tpPrices = [spec.tp1, spec.tp2, spec.tp3].filter(Boolean).map((tp) => tp!.price);
  if (tpPrices.length) {
    const rewardEdge = spec.direction === 'LONG'
      ? Math.max(spec.entry.price, ...tpPrices)
      : Math.min(spec.entry.price, ...tpPrices);
    const yA = y(rewardEdge);
    const yB = y(spec.entry.price);
    const yTop = Math.min(yA, yB);
    const yBot = Math.max(yA, yB);
    g.append('rect')
      .attr('x', x1).attr('y', yTop)
      .attr('width', Math.max(2, x2 - x1))
      .attr('height', Math.max(1, yBot - yTop))
      .attr('fill', TRADE_IDEA_COLORS.rewardFill)
      .attr('opacity', opacity * 0.9);
  }

  const line = (price: number, color: string, label: string, rr?: string | null) => {
    const py = y(price);
    g.append('line')
      .attr('x1', x1).attr('x2', x2)
      .attr('y1', py).attr('y2', py)
      .attr('stroke', color)
      .attr('stroke-width', spec.selected ? 2.2 : 1.6)
      .attr('stroke-dasharray', dash || null)
      .attr('opacity', opacity);
    g.append('text')
      .attr('x', x2 + 4).attr('y', py + 4)
      .attr('fill', color)
      .attr('font-size', 10)
      .attr('font-weight', 800)
      .text(rr ? `${label} ${price.toFixed(2)} (${rr})` : `${label} ${price.toFixed(2)}`);
  };

  line(
    spec.entry.price,
    spec.direction === 'LONG' ? TRADE_IDEA_COLORS.longEntry : TRADE_IDEA_COLORS.shortEntry,
    'Entry',
  );
  if (spec.sl) line(spec.sl.price, TRADE_IDEA_COLORS.sl, 'SL');
  if (spec.tp1) {
    line(
      spec.tp1.price,
      TRADE_IDEA_COLORS.tp,
      'TP1',
      spec.analystExport?.rrTp1 != null ? `${spec.analystExport.rrTp1.toFixed(2)}R` : null,
    );
  }
  if (spec.tp2) {
    line(
      spec.tp2.price,
      TRADE_IDEA_COLORS.tp,
      'TP2',
      spec.analystExport?.rrTp2 != null ? `${spec.analystExport.rrTp2.toFixed(2)}R` : null,
    );
  }
  if (spec.tp3) {
    line(
      spec.tp3.price,
      TRADE_IDEA_COLORS.tp,
      'TP3',
      spec.analystExport?.rrTp3 != null ? `${spec.analystExport.rrTp3.toFixed(2)}R` : null,
    );
  }
}

type D3CandleMapProps = {
  candles:Candle[];
  candleDataRevision?: number;
  replayCutTime?:string|null;
  timeframe:string;
  rangeHigh:number;
  rangeLow:number;
  rangeStart?:string;
  rangeEnd?:string;
  hasRange:boolean;
  caseStart?:string;
  caseEnd?:string;
  caseHigh?:string|number;
  caseLow?:string|number;
  parentOverlays?:ParentRangeOverlayLine[];
  savedRangeOverlays?:SavedRangeChartLine[];
  draftRangeOverlay?:DraftRangeChartLine|null;
  focusMode?:boolean;
  guidedCursorTimeMs?:number|null;
  guidedParentEndMs?:number|null;
  showFibOverlays?:boolean;
  events:MapEvent[];
  selectedCandleTime?:string|null;
  selectedCandlePrice?:number|null;
  eventType:string;
  toolMode:'inspect'|'plot'|'drag'|'range'|'select'|'scrub';
  chartDrawings?:ChartDrawing[];
  chartDrawTool?:ChartDrawTool;
  chartDrawColor?:string;
  selectedDrawingId?:string|null;
  onDrawingsChange?:(drawings:ChartDrawing[])=>void;
  onSelectedDrawingChange?:(id:string|null)=>void;
  chartTradeIdeas?:ChartTradeIdea[];
  tradeIdeaDraft?:ChartTradeIdeaDraft|null;
  tradePickMode?:TradeIdeaPickKind|null;
  selectedTradeIdeaId?:string|null;
  onTradeLevelPick?:(payload:{kind:TradeIdeaPickKind; time:string; price:number})=>void;
  scaleMode:'auto'|'range';
  autoscaleToken?:number;
  jumpLatestToken:number;
  fitAllToken:number;
  goDate:string;
  onCursor:(v:{time?:string; price?:number; zone?:string; pct?:number; ohlc?:Candle|null}|null)=>void;
  onAddEvent:(info:{time?:string; price:number; candle?:Candle|null})=>void;
  onCandleSelect?:(info:{candle:Candle; price:number; clientX:number; clientY:number})=>void;
  replayCursorEnabled?:boolean;
  onReplayCursorChange?:(time:string)=>void;
  onUpdateEvent:(id:string, patch:Partial<MapEvent>)=>void;
  onFinishEventDrag:(ev:MapEvent)=>void;
  onRangeChange?:(patch:{high?:number; low?:number; start?:string; end?:string})=>void;
  cameraMode?:'AUTO'|'LOCKED'|'CASE'|'REPLAY';
  cameraCommand?:CameraCommand;
  lockedCameraDomain?:{start:string;end:string}|null;
  lockedPriceDomain?:{low:number;high:number}|null;
  candleWidthScale?:number;
  priceZoomScale?:number;
  cameraKey?:string;
  cameraViewOwner?: CameraViewOwner;
  onCameraViewOwnerChange?:(owner: CameraViewOwner, source: string, reason?: string)=>void;
  onCameraDomainChange?:(domain:{start:string;end:string})=>void;
  onVisibleDomainChange?:(domain:VisibleCameraDomain)=>void;
  viewportClamp?:{start:string;end:string}|null;
  chartEmptyState?: 'empty' | 'loading' | 'welcome';
  /** Inspector overlay open — layout resize from toggle should not tear down chart. */
  isInspectorOpen?: boolean;
};

function snapChartPx(value: number): number {
  return Math.round(value);
}

function snapChartStrokePx(value: number): number {
  return Math.round(value) + 0.5;
}

function medianBarSpacingPx(candles: Candle[], zx: d3.ScaleTime<number, number>, maxSamples = 28): number {
  if (candles.length < 2) return 10;
  const gaps: number[] = [];
  const step = Math.max(1, Math.floor(candles.length / maxSamples));
  for (let i = step; i < candles.length; i += step) {
    const a = zx(candleTimeDate(candles[i - 1].time));
    const b = zx(candleTimeDate(candles[i].time));
    const gap = Math.abs(b - a);
    if (Number.isFinite(gap) && gap > 0.5) gaps.push(gap);
  }
  if (!gaps.length) return 10;
  gaps.sort((x, y) => x - y);
  return gaps[Math.floor(gaps.length / 2)] || 10;
}

const CHART_MARGIN = { top: 24, right: 20, bottom: 42, left: 72 };

type ChartSurfaceMetrics = {
  width: number;
  height: number;
  dpr: number;
  margin: typeof CHART_MARGIN;
  innerW: number;
  innerH: number;
};

function chartDevicePixelRatio(): number {
  return Math.max(1, Math.min(3, window.devicePixelRatio || 1));
}

/** Logical CSS-pixel chart size used for scales, zoom, and pointer mapping. */
function getChartSurfaceMetrics(svgEl: SVGSVGElement | null): ChartSurfaceMetrics | null {
  if (!svgEl) return null;
  const rect = svgEl.getBoundingClientRect();
  const width = snapChartPx(Math.max(280, rect.width || 0));
  const height = snapChartPx(Math.max(220, rect.height || 0));
  if (width <= 0 || height <= 0) return null;
  const margin = CHART_MARGIN;
  return {
    width,
    height,
    dpr: chartDevicePixelRatio(),
    margin,
    innerW: width - margin.left - margin.right,
    innerH: height - margin.top - margin.bottom,
  };
}

function applyChartSurfaceSize(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  metrics: ChartSurfaceMetrics,
) {
  svg
    .style('width', `${metrics.width}px`)
    .style('height', `${metrics.height}px`)
    .attr('width', snapChartPx(metrics.width * metrics.dpr))
    .attr('height', snapChartPx(metrics.height * metrics.dpr))
    .attr('viewBox', `0 0 ${metrics.width} ${metrics.height}`);
}

/** Pointer/touch → viewBox coordinates (CSS pixel space, matches y/x scales). */
function chartPointer(event: any, svgEl: SVGSVGElement): [number, number] {
  const source = event?.sourceEvent ?? event;
  try {
    const pt = d3.pointer(source, svgEl);
    if (Number.isFinite(pt[0]) && Number.isFinite(pt[1])) return pt;
  } catch {
    /* d3.pointer can throw on some touch synthetic events */
  }
  const rect = svgEl.getBoundingClientRect();
  if (!rect.width || !rect.height) return [NaN, NaN];
  const touch = source?.touches?.[0] || source?.changedTouches?.[0];
  const clientX = touch?.clientX ?? source?.clientX;
  const clientY = touch?.clientY ?? source?.clientY;
  if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return [NaN, NaN];
  const vb = svgEl.viewBox.baseVal;
  const vw = vb.width || rect.width;
  const vh = vb.height || rect.height;
  return [
    ((clientX - rect.left) / rect.width) * vw,
    ((clientY - rect.top) / rect.height) * vh,
  ];
}

function clampChartPlotXY(mx: number, my: number, metrics: ChartSurfaceMetrics): { x: number; y: number } {
  return {
    x: Math.max(metrics.margin.left, Math.min(metrics.margin.left + metrics.innerW, mx)),
    y: Math.max(metrics.margin.top, Math.min(metrics.margin.top + metrics.innerH, my)),
  };
}

type CrosshairSnap = {
  cx: number;
  cy: number;
  candle: Candle;
  price: number;
  priceTag: string;
  dateText: string;
};

function nearestVisibleCandle(date: Date, candles: Candle[]): Candle | null {
  if (!candles.length) return null;
  const t = date.getTime();
  let best = candles[0];
  let dist = Math.abs(candleTimeMs(best.time) - t);
  for (const c of candles) {
    const d = Math.abs(candleTimeMs(c.time) - t);
    if (d < dist) { best = c; dist = d; }
  }
  return best;
}

function pickCandleAtPoint(
  mx: number,
  my: number,
  visible: Candle[],
  renderData: Candle[],
  zx: d3.ScaleTime<number, number>,
  y: d3.ScaleLinear<number, number>,
  metrics: ChartSurfaceMetrics,
  barSpacingPx: number,
): Candle | null {
  const { x: sx, y: sy } = clampChartPlotXY(mx, my, metrics);
  const pool = visible.length ? visible : renderData;
  if (!pool.length) return null;
  const hitHalfW = Math.max(5, Math.min(28, barSpacingPx * 0.55));
  let best: Candle | null = null;
  let bestScore = Infinity;
  for (const c of pool) {
    const cx = zx(candleTimeDate(c.time));
    if (!Number.isFinite(cx)) continue;
    const dx = Math.abs(sx - cx);
    if (dx > hitHalfW) continue;
    const yHigh = y(c.high);
    const yLow = y(c.low);
    const top = Math.min(yHigh, yLow) - 8;
    const bottom = Math.max(yHigh, yLow) + 8;
    if (sy < top || sy > bottom) {
      if (dx > hitHalfW * 0.65) continue;
    }
    const score = dx + Math.min(Math.abs(sy - yHigh), Math.abs(sy - yLow)) * 0.12;
    if (score < bestScore) {
      best = c;
      bestScore = score;
    }
  }
  if (best) return best;
  const date = zx.invert(sx);
  const plotRight = metrics.margin.left + metrics.innerW;
  if (pool.length && sx >= plotRight - Math.max(12, hitHalfW * 2)) {
    return pool[pool.length - 1];
  }
  return nearestVisibleCandle(date, pool);
}

function snapCrosshairToCandle(
  mx: number,
  my: number,
  visible: Candle[],
  renderData: Candle[],
  zx: d3.ScaleTime<number, number>,
  y: d3.ScaleLinear<number, number>,
  metrics: ChartSurfaceMetrics,
  timeframe: string,
  barSpacingPx = 12,
): CrosshairSnap | null {
  const { x: sx, y: sy } = clampChartPlotXY(mx, my, metrics);
  const c = pickCandleAtPoint(mx, my, visible, renderData, zx, y, metrics, barSpacingPx);
  if (!c) return null;
  const cx = snapChartStrokePx(zx(candleTimeDate(c.time)));
  const rawPrice = y.invert(sy);
  const candidates = [
    { price: c.close, tag: 'C' },
    { price: c.open, tag: 'O' },
    { price: c.high, tag: 'H' },
    { price: c.low, tag: 'L' },
  ];
  const pick = candidates.reduce((best, cur) =>
    Math.abs(cur.price - rawPrice) < Math.abs(best.price - rawPrice) ? cur : best,
  );
  return {
    cx,
    cy: snapChartPx(y(pick.price)),
    candle: c,
    price: pick.price,
    priceTag: pick.tag,
    dateText: shortTime(c.time, timeframe),
  };
}

function priceLineY(yScale: d3.ScaleLinear<number, number>, price: number): number {
  return snapChartStrokePx(yScale(Number(price)));
}

function rangeSpanX(
  zx: d3.ScaleTime<number, number>,
  start: string | null | undefined,
  end: string | null | undefined,
  margin: typeof CHART_MARGIN,
  innerW: number,
): { x1: number; x2: number } {
  const plotLeft = margin.left;
  const plotRight = margin.left + innerW;
  const full = { x1: plotLeft, x2: plotRight };
  const clampX = (x: number) => Math.max(plotLeft, Math.min(plotRight, x));
  const a = start ? candleTimeDate(start) : null;
  const b = end ? candleTimeDate(end) : null;
  const aOk = !!a && Number.isFinite(a.getTime());
  const bOk = !!b && Number.isFinite(b.getTime());
  if (aOk && bOk) {
    const xA = zx(a!);
    const xB = zx(b!);
    if (Number.isFinite(xA) && Number.isFinite(xB)) {
      return expandRangeSpanX(xA, xB, plotLeft, plotRight);
    }
  }
  if (aOk) {
    const xA = zx(a!);
    if (Number.isFinite(xA)) {
      const x1 = clampX(xA - innerW * 0.2);
      const x2 = clampX(xA + innerW * 0.2);
      if (x2 - x1 >= 24) return { x1, x2 };
    }
  }
  if (bOk) {
    const xB = zx(b!);
    if (Number.isFinite(xB)) {
      const x1 = clampX(xB - innerW * 0.2);
      const x2 = clampX(xB + innerW * 0.2);
      if (x2 - x1 >= 24) return { x1, x2 };
    }
  }
  return full;
}

function chartXScaleFromData(data: Candle[], metrics: ChartSurfaceMetrics) {
  const dates = data.map((d) => new Date(d.time));
  return d3.scaleTime()
    .domain(d3.extent(dates) as [Date, Date])
    .range([metrics.margin.left, metrics.margin.left + metrics.innerW]);
}

function chartScreenXRatio(metrics: ChartSurfaceMetrics, ratio: number): number {
  return metrics.margin.left + metrics.innerW * ratio;
}

/** Place `timeRaw` at a horizontal screen ratio while preserving zoom scale `k`. */
function translateTransformToCenterTime(
  x0: d3.ScaleTime<number, number>,
  timeRaw: string,
  k: number,
  metrics: ChartSurfaceMetrics,
  screenRatio = 0.5,
): d3.ZoomTransform | null {
  const t = new Date(String(timeRaw));
  if (!Number.isFinite(t.getTime())) return null;
  const px = x0(t);
  if (!Number.isFinite(px)) return null;
  const tx = chartScreenXRatio(metrics, screenRatio) - k * px;
  return d3.zoomIdentity.translate(tx, 0).scale(k);
}

function D3CandleMap(props:D3CandleMapProps) {
  const svgRef = useRef<SVGSVGElement|null>(null);
  const transformRef = useRef<any>(d3.zoomIdentity);
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<SVGRectElement, unknown> | null>(null);
  const suppressZoomDrawRef = useRef(false);
  const drawRafRef = useRef<number | null>(null);
  const yPanPxRef = useRef(0);
  const yZoomRef = useRef(1);
  const yDragSnapRef = useRef<{ startX: number; startY: number; startPan: number } | null>(null);
  const yDragActiveRef = useRef(false);
  const overlayPanMovedRef = useRef(false);
  const selectTapRef = useRef<{ mx: number; my: number } | null>(null);
  const lastYDomainRef = useRef<[number, number] | null>(null);
  const lastYBaseRef = useRef<{baseLo:number;baseHi:number;innerH:number}|null>(null);
  const latestProps = useRef(props);
  latestProps.current = props;
  const readableZoomKeyRef = useRef('');
  const layoutMetricsRef = useRef<ChartSurfaceMetrics | null>(null);
  const cursorRafRef = useRef<number | null>(null);
  const latestCursorPayloadRef = useRef<any>(null);
  const hoverActiveRef = useRef(false);
  const hoverPointerRef = useRef<{ mx: number; my: number } | null>(null);
  const lastCursorNotifyKeyRef = useRef('');
  const manualZoomRef = useRef(false);
  const renderGateRef = useRef(createChartRenderGate());
  const layoutResizeGuardRef = useRef(createLayoutResizeGuard());

  const nearestCandle = (date:Date, data:Candle[]) => nearestVisibleCandle(date, data);

  type DrawScheduleReason = 'data' | 'resize';

  const scheduleDraw = (reason: DrawScheduleReason = 'data') => {
    if (drawRafRef.current != null) return;
    drawRafRef.current = window.requestAnimationFrame(() => {
      drawRafRef.current = null;
      if (reason === 'resize') {
        const svgEl = svgRef.current;
        if (svgEl) {
          const rect = svgEl.getBoundingClientRect();
          if (!renderGateRef.current.shouldRedraw(rect.width, rect.height)) return;
        }
      }
      draw();
    });
  };

  const applyOverlayZoomTransform = (overlay: d3.Selection<SVGRectElement, unknown, null, undefined>) => {
    const node = overlay.node();
    if (!node) return;
    suppressZoomDrawRef.current = true;
    try {
      overlay.property('__zoom', transformRef.current);
    } finally {
      suppressZoomDrawRef.current = false;
    }
  };

  const draw = () => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    const metrics = getChartSurfaceMetrics(svgEl);
    if (!metrics) {
      scheduleDraw('data');
      return;
    }
    layoutMetricsRef.current = metrics;
    renderGateRef.current.noteDimensions(metrics.width, metrics.height);
    const p = latestProps.current;
    const data = p.candles || [];
    const replayCutMs = p.replayCutTime ? candleTimeMs(p.replayCutTime) : null;
    const renderData = replayCutMs && Number.isFinite(replayCutMs)
      ? data.filter(d => candleTimeMs(d.time) <= replayCutMs)
      : data;
    const svg = d3.select(svgEl);
    const { width, height, margin, innerW, innerH } = metrics;
    applyChartSurfaceSize(svg, metrics);
    svg.selectAll('*').remove();
    svg.append('rect').attr('width', width).attr('height', height).attr('fill', '#000');
    if (!data.length) {
      if (p.chartEmptyState === 'welcome') return;
      const emptyLabel = p.chartEmptyState === 'loading' ? 'Loading…' : 'No candles loaded yet';
      const emptyClass = p.chartEmptyState === 'loading' ? 'chart-empty chart-empty-loading' : 'chart-empty';
      svg.append('text')
        .attr('class', emptyClass)
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#94a3b8')
        .attr('font-size', p.chartEmptyState === 'loading' ? 20 : 22)
        .text(emptyLabel);
      if (p.chartEmptyState === 'loading') {
        svg.append('text')
          .attr('class', 'chart-empty-spinner')
          .attr('x', width / 2)
          .attr('y', height / 2 + 28)
          .attr('text-anchor', 'middle')
          .attr('fill', '#7dd3fc')
          .attr('font-size', 12)
          .text('Sync Architect · local cache');
      }
      return;
    }

    if (!renderData.length) {
      svg.append('text').attr('x', width/2).attr('y', height/2).attr('text-anchor','middle').attr('fill','#94a3b8').attr('font-size',18).text('Replay cursor is before available candles');
      return;
    }

    const dateDomainSource = renderData;
    const dates = dateDomainSource.map(d => candleTimeDate(d.time)).filter(d => Number.isFinite(d.getTime()));
    const clampSpan = p.viewportClamp ? intersectClampSpanWithCandles(p.viewportClamp, renderData) : null;
    const panBounds = resolveChartPanBounds(renderData, clampSpan);
    let extent = d3.extent(dates) as [Date, Date];
    if (panBounds) {
      extent = [new Date(panBounds.start), new Date(panBounds.end)];
    }
    const x0 = d3.scaleTime().domain(extent).range([margin.left, margin.left+innerW]);
    let zx = transformRef.current.rescaleX(x0);
    let domain = zx.domain();
    const inDomain = (d: any) => {
      const dt = candleTimeDate(d.time);
      return Number.isFinite(dt.getTime()) && dt >= domain[0] && dt <= domain[1];
    };
    let visible = renderData.filter(inDomain);
    if (!visible.length && renderData.length && panBounds && manualZoomRef.current) {
      transformRef.current = clampChartTransformToTimeBounds(
        transformRef.current,
        x0,
        panBounds,
        margin.left,
        innerW,
      );
      zx = transformRef.current.rescaleX(x0);
      domain = zx.domain();
      visible = renderData.filter(inDomain);
    }
    const v = visible;
    const freezePriceSpan = manualZoomRef.current && lastYBaseRef.current && p.scaleMode === 'auto';
    const autoscaleLookback = Math.min(v.length, 72);
    const autoScaleSource = p.scaleMode === 'auto' ? v.slice(Math.max(0, v.length - autoscaleLookback)) : v;
    const priorY = lastYDomainRef.current;
    let baseLo: number;
    let baseHi: number;
    if (freezePriceSpan && lastYBaseRef.current) {
      baseLo = lastYBaseRef.current.baseLo;
      baseHi = lastYBaseRef.current.baseHi;
    } else {
      const hiData = d3.max(autoScaleSource, d=>d.high) ?? (priorY ? priorY[1] : (d3.max(renderData.slice(-120), d=>d.high) ?? 1));
      const loData = d3.min(autoScaleSource, d=>d.low) ?? (priorY ? priorY[0] : (d3.min(renderData.slice(-120), d=>d.low) ?? 0));
      const visibleHi = d3.max(v, d=>d.high) ?? hiData;
      const visibleLo = d3.min(v, d=>d.low) ?? loData;
      const parentOverlayPrices = safeArray<any>(p.parentOverlays || []).map((x:any)=>Number(x.price)).filter(Number.isFinite);
      const savedOverlayPrices = safeArray<SavedRangeChartLine>(p.savedRangeOverlays || [])
        .filter((r) => !p.focusMode && (r.isActive || r.isParentContext))
        .flatMap((r)=>[r.high, r.low])
        .filter(Number.isFinite);
      const draftOverlayPrices = p.draftRangeOverlay?.visible ? [p.draftRangeOverlay.high, p.draftRangeOverlay.low].filter(Number.isFinite) : [];
      const parentHi = parentOverlayPrices.length ? Math.max(...parentOverlayPrices) : undefined;
      const parentLo = parentOverlayPrices.length ? Math.min(...parentOverlayPrices) : undefined;
      const savedHi = savedOverlayPrices.length ? Math.max(...savedOverlayPrices) : undefined;
      const savedLo = savedOverlayPrices.length ? Math.min(...savedOverlayPrices) : undefined;
      const useCandleOnlyY = shouldUseCandleOnlyYScale(!!p.focusMode);
      let yHi = hiData, yLo = loData;
      if (useCandleOnlyY && v.length) {
        const candleY = focusYExtentsWithParent(
          v.map((d) => ({ time: d.time, high: d.high, low: d.low })),
          parentHi,
          parentLo,
        );
        if (candleY) {
          yHi = candleY.high;
          yLo = candleY.low;
        }
      } else {
        if (p.hasRange && p.scaleMode === 'range' && v.length) { yHi = Math.max(p.rangeHigh, visibleHi); yLo = Math.min(p.rangeLow, visibleLo); }
        if (Number.isFinite(parentHi as any)) yHi = Math.max(yHi, Number(parentHi));
        if (Number.isFinite(parentLo as any)) yLo = Math.min(yLo, Number(parentLo));
        if (Number.isFinite(savedHi as any)) yHi = Math.max(yHi, Number(savedHi));
        if (Number.isFinite(savedLo as any)) yLo = Math.min(yLo, Number(savedLo));
        if (draftOverlayPrices.length) {
          yHi = Math.max(yHi, ...draftOverlayPrices);
          yLo = Math.min(yLo, ...draftOverlayPrices);
        }
      }
      const padRatio = useCandleOnlyY ? 0.1 : 0.18;
      const pad = Math.max((yHi-yLo)*padRatio, 1);
      baseLo = yLo - pad;
      baseHi = yHi + pad;
      lastYBaseRef.current = { baseLo, baseHi, innerH };
    }
    const zoomY = Math.max(0.25, Math.min(32, (yZoomRef.current || 1)));
    const baseSpan = Math.max(1e-9, baseHi - baseLo);
    const span = baseSpan / zoomY;
    const pricePerPx = span / Math.max(1, innerH);
    const center = ((baseLo + baseHi) / 2) + ((yPanPxRef.current || 0) * pricePerPx);
    const yDomain: [number, number] = [center - span/2, center + span/2];
    if (v.length) lastYDomainRef.current = yDomain;
    const barSpacingPx = v.length >= 2 ? medianBarSpacingPx(v, zx) : innerW / Math.max(8, v.length);
    p.onVisibleDomainChange?.({
      start: domain[0].toISOString(),
      end: domain[1].toISOString(),
      priceLow: yDomain[0],
      priceHigh: yDomain[1],
      visibleBars: v.length,
      barSpacingPx,
    });
    const y = d3.scaleLinear().domain(yDomain).range([margin.top+innerH, margin.top]).nice();

    const plot = svg.append('g').attr('class','plot');
    const grid = plot.append('g');
    grid.selectAll('line.ygrid').data(y.ticks(7)).join('line')
      .attr('x1', margin.left).attr('x2', margin.left+innerW).attr('y1', d=>snapChartStrokePx(y(d))).attr('y2', d=>snapChartStrokePx(y(d))).attr('stroke','rgba(255,255,255,.08)').attr('shape-rendering','crispEdges');
    grid.selectAll('text.ytick').data(y.ticks(7)).join('text')
      .attr('x', 10).attr('y', d=>y(d)+4).attr('fill','rgba(226,232,240,.65)').attr('font-size',13).text(d=>Number(d).toFixed(2));

    const savedRanges = safeArray<SavedRangeChartLine>(p.savedRangeOverlays || []);
    if (savedRanges.length) {
      const sg = plot.append('g').attr('class','savedRangeLines').attr('pointer-events','none');
      const savedRows = savedRanges.flatMap((r) => {
        const baseStyle = savedRangeLineStyle(r.status, {
          isParentContext: r.isParentContext,
          isActive: r.isActive,
          rangeScope: r.rangeScope,
          structureLayer: r.structureLayer,
        });
        const style = p.focusMode
          ? overlayLineStyleWithFocus(
            baseStyle,
            true,
            r.focusTier || (r.isActive ? 'active' : r.isParentContext ? 'parent' : undefined),
            { structureLayer: r.structureLayer },
          )
          : baseStyle;
        const color = structureLayerLineColor(r.structureLayer);
        const prefix = r.isParentContext ? 'ctx ' : '';
        const scopeLabel = r.rangeScope === 'MINOR' ? ' MINOR' : '';
        const span = rangeSpanX(zx, r.start, r.end, margin, innerW);
        const rowBase = { color, style, rangeId: r.rangeId, x1: span.x1, x2: span.x2, start: r.start, end: r.end };
        return [
          { kind:'high' as const, price:r.high, label:`${prefix}#${r.rangeId} ${r.structureLayer}${scopeLabel} RH`, ...rowBase },
          { kind:'low' as const, price:r.low, label:`${prefix}#${r.rangeId} ${r.structureLayer}${scopeLabel} RL`, ...rowBase },
        ];
      });
      sg.selectAll('line.savedRangeLine').data(savedRows).join('line')
        .attr('class','savedRangeLine')
        .attr('x1', (d:any)=>Number(d.x1))
        .attr('x2', (d:any)=>Number(d.x2))
        .attr('y1', (d:any)=>priceLineY(y, Number(d.price)))
        .attr('y2', (d:any)=>priceLineY(y, Number(d.price)))
        .attr('stroke', (d:any)=>d.color)
        .attr('stroke-opacity', (d:any)=>d.style.opacity)
        .attr('stroke-width', (d:any)=>d.style.width)
        .attr('stroke-dasharray', (d:any)=>d.style.dash || null);
    }

    const parentOverlayLines = safeArray<ParentRangeOverlayLine>(p.parentOverlays || []);
    if (parentOverlayLines.length) {
      const pg = plot.append('g').attr('class','parentRangeLines').attr('pointer-events','none');
      const savedPriceKeys = new Set(
        savedRanges.flatMap((r) => [Number(r.high).toFixed(2), Number(r.low).toFixed(2)]),
      );
      const parentRows = parentOverlayLines
        .filter((x) => !savedPriceKeys.has(Number(x.price).toFixed(2)))
        .map((x) => {
          const layer = x.structureLayer || 'WEEKLY';
          const color = structureLayerLineColor(layer);
          const baseStyle = savedRangeLineStyle('ACTIVE', { isParentContext: true, structureLayer: layer });
          const style = p.focusMode
            ? overlayLineStyleWithFocus(baseStyle, true, 'parent', { structureLayer: layer })
            : baseStyle;
          return {
            kind: x.kind,
            price: x.price,
            label: x.label,
            color,
            style,
            ...rangeSpanX(zx, x.start, x.end, margin, innerW),
          };
        });
      if (parentRows.length) {
        pg.selectAll('line.parentRangeLine').data(parentRows).join('line')
          .attr('class','parentRangeLine')
          .attr('x1', (d:any)=>Number(d.x1))
          .attr('x2', (d:any)=>Number(d.x2))
          .attr('y1', (d:any)=>priceLineY(y, Number(d.price)))
          .attr('y2', (d:any)=>priceLineY(y, Number(d.price)))
          .attr('stroke', (d:any)=>d.color)
          .attr('stroke-opacity', (d:any)=>d.style.opacity)
          .attr('stroke-width', (d:any)=>d.style.width)
          .attr('stroke-dasharray', (d:any)=>d.style.dash || null);
      }
    }

    if (p.draftRangeOverlay?.visible) {
      const draft = p.draftRangeOverlay;
      const anchorsComplete = Number.isFinite(draft.high) && Number.isFinite(draft.low);
      const draftStyle = draftRangeLineStyle(anchorsComplete);
      const draftColor = structureLayerLineColor(draft.structureLayer);
      const draftSpan = rangeSpanX(zx, draft.start, draft.end, margin, innerW);
      const dg = plot.append('g').attr('class','draftRangeLines').attr('pointer-events','none');
      const draftRows: Array<{ kind: 'high' | 'low'; price: number; label: string; color: string; style: typeof draftStyle; x1: number; x2: number }> = [];
      if (Number.isFinite(draft.high)) {
        draftRows.push({ kind:'high', price:Number(draft.high), label:`Draft ${draft.structureLayer} RH`, color:draftColor, style:draftStyle, x1: draftSpan.x1, x2: draftSpan.x2 });
      }
      if (Number.isFinite(draft.low)) {
        draftRows.push({ kind:'low', price:Number(draft.low), label:`Draft ${draft.structureLayer} RL`, color:draftColor, style:draftStyle, x1: draftSpan.x1, x2: draftSpan.x2 });
      }
      dg.selectAll('line.draftRangeLine').data(draftRows).join('line')
        .attr('class','draftRangeLine')
        .attr('x1', (d:any)=>Number(d.x1))
        .attr('x2', (d:any)=>Number(d.x2))
        .attr('y1', (d:any)=>priceLineY(y, Number(d.price)))
        .attr('y2', (d:any)=>priceLineY(y, Number(d.price)))
        .attr('stroke', draftColor)
        .attr('stroke-opacity', draftStyle.opacity)
        .attr('stroke-width', draftStyle.width)
        .attr('stroke-dasharray', draftStyle.dash);
    }

    const guidedLines: Array<{ id: string; x: number; stroke: string; width: number; opacity?: number; dash: string }> = [];
    if (p.guidedCursorTimeMs && Number.isFinite(p.guidedCursorTimeMs)) {
      const cx = snapChartStrokePx(zx(new Date(p.guidedCursorTimeMs)));
      if (Number.isFinite(cx) && cx >= margin.left && cx <= margin.left + innerW) {
        guidedLines.push({ id: 'guided-cursor', x: cx, stroke: '#38bdf8', width: 1.5, dash: '4 4' });
      }
    }
    if (p.guidedParentEndMs && Number.isFinite(p.guidedParentEndMs)) {
      const ex = snapChartStrokePx(zx(new Date(p.guidedParentEndMs)));
      if (Number.isFinite(ex) && ex >= margin.left && ex <= margin.left + innerW) {
        guidedLines.push({
          id: 'guided-parent-end',
          x: ex,
          stroke: '#f59e0b',
          width: p.focusMode ? 1.1 : 1.25,
          opacity: p.focusMode ? 0.35 : 1,
          dash: '6 3',
        });
      }
    }
    if (guidedLines.length) {
      const gg = plot.append('g').attr('class', 'guidedMappingLines').attr('pointer-events', 'none');
      gg.selectAll('line.guidedVLine').data(guidedLines).join('line')
        .attr('class', (d) => d.id === 'guided-cursor' ? 'guidedCursorVLine guidedVLine' : 'guidedParentEndVLine guidedVLine')
        .attr('x1', (d) => d.x)
        .attr('x2', (d) => d.x)
        .attr('y1', margin.top)
        .attr('y2', margin.top + innerH)
        .attr('stroke', (d) => d.stroke)
        .attr('stroke-width', (d) => d.width)
        .attr('stroke-opacity', (d) => d.opacity ?? 1)
        .attr('stroke-dasharray', (d) => d.dash)
        .attr('shape-rendering', 'crispEdges');
    }

    const slotW = barSpacingPx;
    const candleW = autoCandleBodyWidthPx(slotW, Number(p.candleWidthScale || 1));

    let restoreCrosshairSnap: CrosshairSnap | null = null;
    if (hoverActiveRef.current && hoverPointerRef.current) {
      restoreCrosshairSnap = snapCrosshairToCandle(
        hoverPointerRef.current.mx,
        hoverPointerRef.current.my,
        v,
        renderData,
        zx,
        y,
        metrics,
        p.timeframe,
        barSpacingPx,
      );
    }

    if (!v.length) {
      svg.append('text')
        .attr('x', margin.left + innerW / 2)
        .attr('y', margin.top + 34)
        .attr('text-anchor','middle')
        .attr('fill','rgba(255,191,47,.75)')
        .attr('font-size',12)
        .attr('font-weight',900)
        .text('Replay cursor is outside the current camera view. Pan left/right or click Latest.');
    }

    if (p.showFibOverlays && p.hasRange) {
      const fibs = [-25,0,25,50,75,100,125];
      const fib = plot.append('g').attr('class','fibs');
      const closestHigh = renderData.reduce((best:any, c:any) => Math.abs(c.high - p.rangeHigh) < Math.abs(best.high - p.rangeHigh) ? c : best, renderData[0]);
      const closestLow = renderData.reduce((best:any, c:any) => Math.abs(c.low - p.rangeLow) < Math.abs(best.low - p.rangeLow) ? c : best, renderData[0]);
      const startTime = p.rangeStart || closestHigh.time;
      const endTime = p.rangeEnd || closestLow.time;
      const xA = zx(new Date(startTime));
      const xB = zx(new Date(endTime));
      const rawX0 = Math.min(xA, xB);
      const rawX1 = Math.max(xA, xB);
      const boxPad = Math.max(8, candleW * 0.8);
      const boxX0 = Math.max(margin.left, rawX0 - boxPad);
      const boxX1 = Math.min(margin.left + innerW, rawX1 + boxPad);
      const boxVisible = Number.isFinite(boxX0) && Number.isFinite(boxX1) && boxX1 > boxX0 + 10;
      const y0 = y(p.rangeHigh), y1 = y(p.rangeLow);
      if (Number.isFinite(y0) && Number.isFinite(y1) && boxVisible) {
        fib.append('rect')
          .attr('x', boxX0).attr('y', Math.min(y0,y1))
          .attr('width', boxX1-boxX0).attr('height', Math.abs(y1-y0))
          .attr('fill','rgba(255,191,47,.035)')
          .attr('stroke','rgba(255,191,47,.28)')
          .attr('stroke-width',1.3)
          .attr('stroke-dasharray','8 8')
          .attr('pointer-events', p.toolMode === 'range' ? 'all' : 'none');
      }
      fib.selectAll('line').data(fibs).join('line')
        .attr('x1', boxVisible ? boxX0 : margin.left)
        .attr('x2', boxVisible ? boxX1 : margin.left+innerW)
        .attr('y1', pct=>y(p.rangeLow + (p.rangeHigh-p.rangeLow)*(pct/100)))
        .attr('y2', pct=>y(p.rangeLow + (p.rangeHigh-p.rangeLow)*(pct/100)))
        .attr('stroke', pct=>pct===50?'rgba(255,255,255,.22)':'rgba(255,191,47,.16)')
        .attr('stroke-dasharray', pct=>pct===50?'8 6':'3 9');
      fib.selectAll('text').data(fibs).join('text')
        .attr('x', (boxVisible ? boxX1 : margin.left+innerW) + 8)
        .attr('y', pct=>y(p.rangeLow + (p.rangeHigh-p.rangeLow)*(pct/100))+4)
        .attr('fill','rgba(255,223,118,.75)').attr('font-size',11).text(pct=>`${pct}%`);
    }

    const candlesG = plot.append('g').attr('class','candles').attr('shape-rendering','crispEdges');
    candlesG.selectAll('g.candle').data(v, (d:any)=>d.time).join('g')
      .attr('class','candle')
      .each(function(d:any){
        const g = d3.select(this);
        const up = d.close >= d.open;
        const color = up ? '#35e783' : '#ff5b6e';
        const xCenter = snapChartStrokePx(zx(candleTimeDate(d.time)));
        const yHigh = snapChartPx(y(d.high));
        const yLow = snapChartPx(y(d.low));
        const yOpen = snapChartPx(y(d.open));
        const yClose = snapChartPx(y(d.close));
        const bodyTop = Math.min(yOpen, yClose);
        const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
        const bodyLeft = snapChartPx(xCenter - candleW / 2);
        g.append('line')
          .attr('x1', xCenter).attr('x2', xCenter)
          .attr('y1', yHigh).attr('y2', yLow)
          .attr('stroke', color)
          .attr('stroke-width', slotW >= 6 ? 1.25 : 1)
          .attr('vector-effect', 'non-scaling-stroke');
        g.append('rect')
          .attr('x', bodyLeft)
          .attr('y', bodyTop)
          .attr('width', candleW)
          .attr('height', bodyHeight)
          .attr('fill', color);
      });

    if (replayCutMs && Number.isFinite(replayCutMs) && p.replayCutTime) {
      const replayCandle = renderData.find((d) => candleTimeMs(d.time) === replayCutMs) || renderData[renderData.length - 1];
      if (replayCandle) {
        const cutDate = candleTimeDate(p.replayCutTime);
        if (Number.isFinite(cutDate.getTime()) && cutDate >= domain[0] && cutDate <= domain[1]) {
          const cutX = snapChartStrokePx(zx(cutDate));
          const yHigh = snapChartPx(y(replayCandle.high));
          const yLow = snapChartPx(y(replayCandle.low));
          plot.append('rect')
            .attr('class', 'replayCandleHighlight')
            .attr('pointer-events', 'none')
            .attr('x', snapChartPx(cutX - candleW / 2 - 3))
            .attr('y', yHigh - 3)
            .attr('width', candleW + 6)
            .attr('height', Math.max(4, yLow - yHigh + 6))
            .attr('fill', 'rgba(0,212,170,.08)')
            .attr('stroke', '#00d4aa')
            .attr('stroke-width', 2);
        }
      }
    }

    // Auto trajectory line intentionally hidden in v048. Route paths should be plotted/refined as saved map coordinates, not drawn as a giant spaghetti noodle.

    const xAxis = d3.axisBottom(zx).ticks(8).tickFormat((d:any)=>shortTime(d.toISOString?.() || d, p.timeframe) as any);
    svg.append('g').attr('transform',`translate(0,${height-margin.bottom})`).call(xAxis as any).selectAll('text').attr('fill','rgba(226,232,240,.7)').attr('font-size',12);
    svg.selectAll('.domain,.tick line').attr('stroke','rgba(226,232,240,.18)');

    if (p.selectedCandleTime) {
      const selectedDate = candleTimeDate(p.selectedCandleTime);
      const isReplayBar = !!(p.replayCutTime && p.selectedCandleTime === p.replayCutTime);
      if (selectedDate >= domain[0] && selectedDate <= domain[1]) {
        const sx = zx(selectedDate);
        const sy = Number.isFinite(Number(p.selectedCandlePrice)) ? y(Number(p.selectedCandlePrice)) : margin.top + innerH / 2;
        const selG = plot.append('g').attr('class','selectedCandleMarker').attr('pointer-events','none');
        if (!isReplayBar) {
          selG.append('circle').attr('cx', sx).attr('cy', sy).attr('r',5).attr('fill','#ffbf2f').attr('stroke','#020308').attr('stroke-width',2);
        }
      }
    }

    const defaultBarMs = renderData.length >= 2
      ? Math.max(3600000, Math.abs(candleTimeMs(renderData[1].time) - candleTimeMs(renderData[0].time)))
      : 86400000;
    const savedTradeIdeas = safeArray<ChartTradeIdea>(p.chartTradeIdeas || []);
    const draftTradeSpec = p.tradeIdeaDraft ? overlaySpecFromDraft(p.tradeIdeaDraft, true) : null;
    if (savedTradeIdeas.length || draftTradeSpec) {
      const tiG = plot.append('g').attr('class', 'chartTradeIdeas').attr('pointer-events', 'none');
      for (const idea of savedTradeIdeas) {
        paintChartTradeIdea(tiG, overlaySpecFromIdea(idea, idea.id === (p.selectedTradeIdeaId || '')), zx, y, defaultBarMs);
      }
      if (draftTradeSpec) paintChartTradeIdea(tiG, draftTradeSpec, zx, y, defaultBarMs);
    }

    const chartDrawings = safeArray<ChartDrawing>(p.chartDrawings || []);
    const drawTool = p.chartDrawTool || 'off';
    const drawColor = p.chartDrawColor || CHART_DRAWING_COLORS[0];
    const selectedDrawId = p.selectedDrawingId || null;
    if (chartDrawings.length) {
      const dg = plot.append('g').attr('class', 'userChartDrawings');
      const plotTop = margin.top;
      const plotBottom = margin.top + innerH;
      const plotH = innerH;
      const yFromRatio = (ratio: number) => plotTop + Math.max(0, Math.min(1, ratio)) * plotH;
      const xFromRatio = (ratio: number) => margin.left + Math.max(0, Math.min(1, ratio)) * innerW;

      chartDrawings.forEach((raw) => {
        if (raw.kind === 'hline') {
          const hd = normalizeHLineDrawing(raw);
          const py = priceLineY(y, Number(hd.price));
          const x1 = xFromRatio(hd.xLeftRatio ?? 0);
          const x2 = xFromRatio(hd.xRightRatio ?? 1);
          const sel = hd.id === selectedDrawId;
          const g = dg.append('g').attr('class', 'userDrawing hline').attr('data-id', hd.id);
          g.append('line')
            .attr('x1', x1).attr('x2', x2)
            .attr('y1', py).attr('y2', py)
            .attr('stroke', hd.color).attr('stroke-width', sel ? 3.2 : 2.6)
            .attr('stroke-opacity', sel ? 1 : 0.88);
          g.append('text')
            .attr('x', x1 + 6).attr('y', py - 4)
            .attr('fill', hd.color).attr('font-size', 10).attr('font-weight', 800)
            .text(Number(hd.price).toFixed(2));
          if (sel && drawTool === 'edit') {
            g.append('rect').attr('class', 'hlineHandle left')
              .attr('x', x1 - 5).attr('y', py - 5).attr('width', 10).attr('height', 10)
              .attr('fill', hd.color).attr('stroke', '#020308').attr('stroke-width', 1);
            g.append('rect').attr('class', 'hlineHandle right')
              .attr('x', x2 - 5).attr('y', py - 5).attr('width', 10).attr('height', 10)
              .attr('fill', hd.color).attr('stroke', '#020308').attr('stroke-width', 1);
          }
        } else if (raw.kind === 'vline') {
          const vd = normalizeVLineDrawing(raw);
          const t = candleTimeDate(vd.time);
          if (!Number.isFinite(t.getTime()) || t < domain[0] || t > domain[1]) return;
          const vx = snapChartStrokePx(zx(t));
          const y1 = yFromRatio(vd.yTopRatio);
          const y2 = yFromRatio(vd.yBottomRatio);
          const sel = vd.id === selectedDrawId;
          const g = dg.append('g').attr('class', 'userDrawing vline').attr('data-id', vd.id);
          g.append('line')
            .attr('x1', vx).attr('x2', vx)
            .attr('y1', y1).attr('y2', y2)
            .attr('stroke', vd.color).attr('stroke-width', sel ? 3.2 : 2.6)
            .attr('stroke-opacity', sel ? 1 : 0.88);
          if (sel && drawTool === 'edit') {
            g.append('rect').attr('class', 'vlineHandle top')
              .attr('x', vx - 5).attr('y', y1 - 5).attr('width', 10).attr('height', 10)
              .attr('fill', vd.color).attr('stroke', '#020308').attr('stroke-width', 1);
            g.append('rect').attr('class', 'vlineHandle bottom')
              .attr('x', vx - 5).attr('y', y2 - 5).attr('width', 10).attr('height', 10)
              .attr('fill', vd.color).attr('stroke', '#020308').attr('stroke-width', 1);
          }
        } else if (raw.kind === 'text') {
          const t = candleTimeDate(raw.time);
          if (!Number.isFinite(t.getTime())) return;
          const tx = zx(t);
          const ty = y(Number(raw.price));
          const sel = raw.id === selectedDrawId;
          const g = dg.append('g').attr('class', 'userDrawing textbox').attr('data-id', raw.id);
          const label = String(raw.text || '');
          const boxW = Math.max(48, label.length * 6.8 + 16);
          g.append('rect')
            .attr('x', tx + 4).attr('y', ty - 18)
            .attr('width', boxW).attr('height', 22).attr('rx', 5)
            .attr('fill', 'rgba(2,6,23,.82)')
            .attr('stroke', raw.color)
            .attr('stroke-width', sel ? 2 : 1.2);
          g.append('text')
            .attr('x', tx + 12).attr('y', ty - 3)
            .attr('fill', raw.color).attr('font-size', 11).attr('font-weight', 800)
            .text(label);
        }
      });

      dg.attr('pointer-events', 'none');
    }

    const eventG = plot.append('g').attr('class','events');
    const visibleEvents = p.events.filter(ev=>ev.time && new Date(ev.time) >= domain[0] && new Date(ev.time) <= domain[1]);
    const evNodes = eventG.selectAll('g.ev').data(visibleEvents, (d:any)=>d.id).join('g').attr('class','ev').attr('cursor', p.toolMode==='drag'?'grab':'pointer');
    evNodes.attr('transform', d=>`translate(${zx(new Date(d.time || ''))},${y(d.price)})`);
    evNodes.append('line').attr('x1',0).attr('x2',16).attr('y1',0).attr('y2',0).attr('stroke',(d:any)=>d.source==='seed'?'rgba(255,191,47,.55)':'rgba(0,255,208,.45)').attr('stroke-width',1.5).attr('stroke-dasharray','4 4');
    evNodes.append('circle').attr('r',(d:any)=>d.source==='seed'?3.5:4).attr('fill',(d:any)=>d.source==='seed'?'#ffbf2f':'#00ffd0').attr('stroke','#001b18').attr('stroke-width',1.5);
    evNodes.append('text').attr('x',8).attr('y',-6).attr('fill','#e8eef7').attr('font-size',8).attr('font-weight',800).text(d=>eventAbbrev(d.event_type || d.event_name));
    evNodes.append('title').text(d=>`${d.event_name || d.event_type}
Price: ${d.price}
Zone: ${d.zone}
Date: ${shortTime(d.time,p.timeframe)}`);
    evNodes.call(d3.drag<any,MapEvent>()
      .on('drag', function(event, d){
        if (latestProps.current.toolMode !== 'drag' || d.source === 'seed') return;
        const m = layoutMetricsRef.current;
        if (!m) return;
        const [mx, my] = chartPointer(event.sourceEvent || event, svgEl);
        const { x: px, y: py } = clampChartPlotXY(mx, my, m);
        const date = zx.invert(px);
        const c = nearestCandle(date, renderData);
        const price = y.invert(py);
        const pct = latestProps.current.hasRange ? zonePercent(price, latestProps.current.rangeLow, latestProps.current.rangeHigh) : null;
        d.time = c?.time || date.toISOString(); d.price = Number(price.toFixed(2)); d.zone = zoneLabel(pct); d.zone_percent = Number((pct ?? 0).toFixed(2));
        d3.select(this).attr('transform',`translate(${zx(new Date(d.time || ''))},${y(d.price)})`);
        latestProps.current.onUpdateEvent(d.id, { time:d.time, price:d.price, zone:d.zone, zone_percent:d.zone_percent });
      })
      .on('end', function(event, d){ if (latestProps.current.toolMode === 'drag') latestProps.current.onFinishEventDrag(d); }) as any);

    const resetPricePan = () => {
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
      scheduleDraw();
    };
    const chartAllowsDragPan = () => {
      const pp = latestProps.current;
      if (pp.tradePickMode) return false;
      const dt = pp.chartDrawTool || 'off';
      if (dt === 'hline' || dt === 'vline' || dt === 'text' || dt === 'edit') return false;
      const mode = pp.toolMode;
      if (mode === 'range' || mode === 'drag' || mode === 'scrub' || mode === 'plot') return false;
      return mode === 'inspect' || mode === 'select';
    };

    const overlay = svg.append('rect').attr('class','chartPanSurface').attr('x',margin.left).attr('y',margin.top).attr('width',innerW).attr('height',innerH).attr('fill','transparent').attr('cursor', (() => {
      const dt = p.chartDrawTool || 'off';
      if (dt === 'hline' || dt === 'vline' || dt === 'text') return 'crosshair';
      if (dt === 'edit') return 'default';
      if (p.toolMode==='scrub') return 'crosshair';
      if (p.toolMode==='plot') return 'crosshair';
      if (p.toolMode==='select') return 'pointer';
      return 'grab';
    })()).attr('pointer-events', (() => {
      if (drawTool === 'edit') return 'none';
      return (p.toolMode==='range' || p.toolMode==='drag') ? 'none' : 'all';
    })());
    const crossG = svg.append('g').attr('class','chartCrosshair').attr('pointer-events','none').style('display','none');
    crossG.append('line').attr('class','cx').attr('y1',margin.top).attr('y2',margin.top+innerH).attr('stroke','rgba(255,255,255,.55)').attr('stroke-width',1).attr('stroke-dasharray','4 6');
    crossG.append('line').attr('class','cy').attr('x1',margin.left).attr('x2',margin.left+innerW).attr('stroke','rgba(0,255,208,.55)').attr('stroke-width',1).attr('stroke-dasharray','4 6');
    const priceBubble = crossG.append('g').attr('class','priceBubble');
    priceBubble.append('rect').attr('x',4).attr('width',88).attr('height',26).attr('rx',7).attr('fill','rgba(2,6,23,.92)').attr('stroke','rgba(0,255,208,.65)').attr('stroke-width',1.2);
    priceBubble.append('text').attr('x',48).attr('y',17).attr('text-anchor','middle').attr('fill','#00ffd0').attr('font-size',12).attr('font-weight',900);
    const dateBubble = crossG.append('g').attr('class','dateBubble');
    dateBubble.append('rect').attr('y',height-margin.bottom+18).attr('width',118).attr('height',26).attr('rx',7).attr('fill','rgba(2,6,23,.92)').attr('stroke','rgba(255,191,47,.65)').attr('stroke-width',1.2);
    dateBubble.append('text').attr('y',height-margin.bottom+35).attr('text-anchor','middle').attr('fill','#ffdf76').attr('font-size',12).attr('font-weight',900);
    const candleDateBubble = crossG.append('g').attr('class','candleDateBubble');
    candleDateBubble.append('rect').attr('width',160).attr('height',26).attr('rx',7).attr('fill','rgba(2,6,23,.92)').attr('stroke','rgba(255,191,47,.65)').attr('stroke-width',1.2);
    candleDateBubble.append('text').attr('x',80).attr('y',17).attr('text-anchor','middle').attr('fill','#ffdf76').attr('font-size',12).attr('font-weight',900);

    const paintCrosshair = (snap: CrosshairSnap) => {
      const c = snap.candle;
      crossG.style('display', null);
      crossG.selectAll('.hoverCandleHighlight').remove();
      const yHigh = snapChartPx(y(c.high));
      const yLow = snapChartPx(y(c.low));
      crossG.insert('rect', '.cx')
        .attr('class', 'hoverCandleHighlight')
        .attr('x', snapChartPx(snap.cx - candleW / 2 - 2))
        .attr('y', yHigh - 2)
        .attr('width', candleW + 4)
        .attr('height', Math.max(4, yLow - yHigh + 4))
        .attr('fill', 'none')
        .attr('stroke', 'rgba(255,191,47,.85)')
        .attr('stroke-width', 1.5);
      crossG.select('.cx').attr('x1', snap.cx).attr('x2', snap.cx);
      crossG.select('.cy').attr('y1', snap.cy).attr('y2', snap.cy);
      crossG.select('.priceBubble').attr('transform', `translate(0,${snap.cy - 13})`);
      crossG.select('.priceBubble text').text(`${snap.priceTag} ${snap.price.toFixed(2)}`);
      const dateW = Math.max(118, snap.dateText.length * 7.2 + 18);
      const dateX = Math.max(margin.left + dateW / 2, Math.min(margin.left + innerW - dateW / 2, snap.cx));
      crossG.select('.dateBubble rect').attr('width', dateW);
      crossG.select('.dateBubble').attr('transform', `translate(${dateX - dateW / 2}, 0)`);
      crossG.select('.dateBubble text').attr('x', dateW / 2).text(snap.dateText);
      const topDateW = Math.max(140, snap.dateText.length * 7.4 + 20);
      crossG.select('.candleDateBubble rect').attr('width', topDateW);
      crossG.select('.candleDateBubble').attr('transform', `translate(${Math.max(margin.left + 6, Math.min(margin.left + innerW - topDateW - 6, snap.cx - topDateW / 2))}, ${margin.top + 8})`);
      crossG.select('.candleDateBubble text').attr('x', topDateW / 2).text(snap.dateText);
    };

    const notifyCrosshair = (snap: CrosshairSnap) => {
      const key = `${snap.candle.time}:${snap.priceTag}:${snap.price.toFixed(2)}`;
      if (key === lastCursorNotifyKeyRef.current) return;
      lastCursorNotifyKeyRef.current = key;
      const pct = p.hasRange ? zonePercent(snap.price, p.rangeLow, p.rangeHigh) : null;
      latestCursorPayloadRef.current = {
        time: snap.candle.time,
        price: snap.price,
        zone: zoneLabel(pct),
        pct: pct ?? undefined,
        ohlc: snap.candle,
      };
      if (cursorRafRef.current == null) {
        cursorRafRef.current = window.requestAnimationFrame(() => {
          cursorRafRef.current = null;
          latestProps.current.onCursor(latestCursorPayloadRef.current);
        });
      }
    };

    const handleCrosshairPointer = (mx: number, my: number) => {
      if (!Number.isFinite(mx) || !Number.isFinite(my)) return;
      const snap = snapCrosshairToCandle(mx, my, v, renderData, zx, y, metrics, p.timeframe, barSpacingPx);
      if (!snap) {
        hoverActiveRef.current = false;
        hoverPointerRef.current = null;
        crossG.style('display', 'none');
        return;
      }
      hoverActiveRef.current = true;
      hoverPointerRef.current = { mx, my };
      paintCrosshair(snap);
      notifyCrosshair(snap);
    };

    const clearCrosshair = () => {
      hoverActiveRef.current = false;
      hoverPointerRef.current = null;
      lastCursorNotifyKeyRef.current = '';
      crossG.style('display', 'none');
      latestProps.current.onCursor(null);
    };

    const handleOverlayTap = (event: any, mx: number, my: number) => {
      const snap = snapCrosshairToCandle(mx, my, v, renderData, zx, y, metrics, p.timeframe, barSpacingPx);
      const drawTool = latestProps.current.chartDrawTool || 'off';
      const tradePick = latestProps.current.tradePickMode;
      const drawColorNow = latestProps.current.chartDrawColor || CHART_DRAWING_COLORS[0];
      const { x: px, y: py } = clampChartPlotXY(mx, my, metrics);
      const price = snap?.price ?? y.invert(py);
      const c = snap?.candle || nearestCandle(zx.invert(px), renderData);

      if (tradePick && latestProps.current.onTradeLevelPick) {
        if (!c) return;
        latestProps.current.onTradeLevelPick({ kind: tradePick, time: c.time, price: Number(price.toFixed(2)) });
        return;
      }

      if (drawTool === 'edit') {
        return;
      }
      if (drawTool === 'hline' && latestProps.current.onDrawingsChange) {
        const xRatio = Math.max(0, Math.min(1, (px - margin.left) / innerW));
        latestProps.current.onDrawingsChange([
          ...safeArray<ChartDrawing>(latestProps.current.chartDrawings || []),
          { id: newDrawingId(), kind: 'hline', price: Number(price.toFixed(2)), xLeftRatio: Math.max(0, xRatio - 0.35), xRightRatio: Math.min(1, xRatio + 0.35), color: drawColorNow },
        ]);
        return;
      }
      if (drawTool === 'vline' && latestProps.current.onDrawingsChange && c) {
        latestProps.current.onDrawingsChange([
          ...safeArray<ChartDrawing>(latestProps.current.chartDrawings || []),
          { id: newDrawingId(), kind: 'vline', time: c.time, yTopRatio: 0.15, yBottomRatio: 0.85, color: drawColorNow },
        ]);
        return;
      }
      if (drawTool === 'text' && latestProps.current.onDrawingsChange && c) {
        const text = window.prompt('Label text', '')?.trim();
        if (!text) return;
        latestProps.current.onDrawingsChange([
          ...safeArray<ChartDrawing>(latestProps.current.chartDrawings || []),
          { id: newDrawingId(), kind: 'text', time: c.time, price: Number(price.toFixed(2)), text, color: drawColorNow },
        ]);
        return;
      }

      const scrubActive = latestProps.current.replayCursorEnabled && latestProps.current.toolMode === 'scrub';
      if (scrubActive && latestProps.current.onReplayCursorChange) {
        if (c) {
          latestProps.current.onReplayCursorChange(c.time);
          return;
        }
      }
      if (latestProps.current.toolMode === 'select' && snap?.candle && latestProps.current.onCandleSelect) {
        const cut = latestProps.current.replayCutTime;
        if (cut && !isReplaySelectableCandle(snap.candle.time, cut, true)) {
          return;
        }
        latestProps.current.onCandleSelect({
          candle: snap.candle,
          price,
          clientX: event.clientX,
          clientY: event.clientY,
        });
        return;
      }
      if (latestProps.current.toolMode !== 'plot') return;
      latestProps.current.onAddEvent({ time:c?.time || '', price, candle:c });
    };

    overlay
      .on('pointerdown', (event:any) => {
        overlayPanMovedRef.current = false;
        const mode = latestProps.current.toolMode;
        if ((mode === 'select' || mode === 'scrub') && event.button === 0) {
          const [mx, my] = chartPointer(event, svgEl);
          if (Number.isFinite(mx) && Number.isFinite(my)) {
            selectTapRef.current = { mx, my };
          }
          event.stopPropagation();
        }
        if (!chartAllowsDragPan() || event.button !== 0) return;
        const [mx, my] = chartPointer(event, svgEl);
        if (!Number.isFinite(my)) return;
        yDragActiveRef.current = true;
        yDragSnapRef.current = { startX: mx, startY: my, startPan: yPanPxRef.current || 0 };
      })
      .on('pointermove', (event:any) => {
        const [mx, my] = chartPointer(event, svgEl);
        if (yDragActiveRef.current && yDragSnapRef.current && Number.isFinite(my)) {
          const snap = yDragSnapRef.current;
          const dy = my - snap.startY;
          const dx = mx - snap.startX;
          if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
            overlayPanMovedRef.current = true;
            manualZoomRef.current = true;
            latestProps.current.onCameraViewOwnerChange?.('USER_PAN_ZOOM', 'D3CandleMap.yPan', 'user-pan-zoom');
          }
          yPanPxRef.current = snap.startPan + dy;
          scheduleDraw();
        }
        handleCrosshairPointer(mx, my);
      })
      .on('pointerup', (event:any) => {
        const mode = latestProps.current.toolMode;
        const tapStart = selectTapRef.current;
        selectTapRef.current = null;
        if ((mode === 'select' || mode === 'scrub') && tapStart && event.button === 0) {
          const [mx, my] = chartPointer(event, svgEl);
          if (Number.isFinite(mx) && Number.isFinite(my)) {
            const moved = Math.hypot(mx - tapStart.mx, my - tapStart.my);
            if (moved < 8) {
              handleOverlayTap(event, mx, my);
            }
          }
        }
        yDragActiveRef.current = false;
        yDragSnapRef.current = null;
      })
      .on('pointerleave', () => {
        selectTapRef.current = null;
        yDragActiveRef.current = false;
        yDragSnapRef.current = null;
        clearCrosshair();
      })
      .on('pointercancel', () => {
        selectTapRef.current = null;
        yDragActiveRef.current = false;
        yDragSnapRef.current = null;
        clearCrosshair();
      })
      .on('dblclick', (event:any) => {
        if (!chartAllowsDragPan()) return;
        event.preventDefault();
        resetPricePan();
      })
      .on('click', (event:any)=>{
        const mode = latestProps.current.toolMode;
        if (mode === 'select' || mode === 'scrub') return;
        if (overlayPanMovedRef.current) {
          overlayPanMovedRef.current = false;
          return;
        }
        const [mx, my] = chartPointer(event, svgEl);
        handleOverlayTap(event, mx, my);
      });

    const zoomed = (event:any) => {
      if (suppressZoomDrawRef.current) return;
      const next = event.transform;
      transformRef.current = d3.zoomIdentity.translate(next.x, 0).scale(next.k);
      manualZoomRef.current = true;
      latestProps.current.onCameraViewOwnerChange?.('USER_PAN_ZOOM', 'D3CandleMap.zoomed', 'user-pan-zoom');
      try {
        const pp = latestProps.current;
        const dataNow = pp.replayCutTime
          ? safeArray(pp.candles).filter((d:any)=>new Date(d.time).getTime() <= new Date(String(pp.replayCutTime)).getTime())
          : safeArray(pp.candles);
        const clampSpanNow = pp.viewportClamp?.start && pp.viewportClamp?.end
          ? intersectClampSpanWithCandles(pp.viewportClamp, dataNow)
          : null;
        const panBoundsNow = resolveChartPanBounds(dataNow, clampSpanNow);
        if (panBoundsNow && svgRef.current && dataNow.length) {
          const m = getChartSurfaceMetrics(svgRef.current);
          if (m) {
            const xBase = d3.scaleTime()
              .domain([new Date(panBoundsNow.start), new Date(panBoundsNow.end)])
              .range([m.margin.left, m.margin.left + m.innerW]);
            transformRef.current = clampChartTransformToTimeBounds(
              transformRef.current,
              xBase,
              panBoundsNow,
              m.margin.left,
              m.innerW,
            );
          }
        }
        if (pp.cameraMode === 'LOCKED') {
          const dataNow = pp.replayCutTime ? safeArray(pp.candles).filter((d:any)=>new Date(d.time).getTime() <= new Date(String(pp.replayCutTime)).getTime()) : safeArray(pp.candles);
          if (dataNow.length && svgRef.current) {
            const m = getChartSurfaceMetrics(svgRef.current);
            if (!m) return;
            const xBase = d3.scaleTime().domain(d3.extent(dataNow.map((d:any)=>new Date(d.time))) as [Date,Date]).range([m.margin.left, m.margin.left + m.innerW]);
            const dom = transformRef.current.rescaleX(xBase).domain();
            pp.onCameraDomainChange?.({ start: dom[0].toISOString(), end: dom[1].toISOString() });
          }
        }
      } catch {}
      scheduleDraw();
    };
    if (!zoomBehaviorRef.current) {
      zoomBehaviorRef.current = d3.zoom<SVGRectElement, unknown>()
        .scaleExtent([0.35, Math.max(120, data.length / 8)])
        .wheelDelta((event:any)=> {
          const delta = event.deltaMode === 1 ? event.deltaY * 120 : event.deltaY;
          return -delta * 0.0025;
        })
        .filter((event:any) => {
          const tradePick = latestProps.current.tradePickMode;
          if (tradePick) {
            if (event.type === 'wheel') return true;
            return false;
          }
          const drawTool = latestProps.current.chartDrawTool || 'off';
          if (drawTool === 'hline' || drawTool === 'vline' || drawTool === 'text' || drawTool === 'edit') {
            if (event.type === 'wheel') return true;
            return false;
          }
          const mode = latestProps.current.toolMode;
          if (event.type === 'wheel') return true;
          if (mode === 'scrub' || mode === 'range' || mode === 'drag' || mode === 'plot') return false;
          if (mode === 'select' || mode === 'inspect') {
            if (event.type.startsWith('touch')) return true;
            return event.button === 0;
          }
          if (event.type.startsWith('touch')) return true;
          return event.button === 0;
        })
        .on('zoom', zoomed);
    }
    const zoom = zoomBehaviorRef.current;
    let translateExtentLeft = margin.left - innerW * 0.08;
    let translateExtentRight = margin.left + innerW + innerW * 0.08;
    if (panBounds) {
      const boundsX0 = d3.scaleTime()
        .domain([new Date(panBounds.start), new Date(panBounds.end)])
        .range([margin.left, margin.left + innerW]);
      translateExtentLeft = boundsX0(new Date(panBounds.start)) - innerW * 0.1;
      translateExtentRight = boundsX0(new Date(panBounds.end)) + innerW * 0.58;
    }
    zoom
      .scaleExtent([0.35, Math.max(120, data.length / 8)])
      .translateExtent([[translateExtentLeft, 0], [translateExtentRight, height]])
      .extent([[margin.left, margin.top], [margin.left + innerW, margin.top + innerH]]);
    overlay.call(zoom as any);
    svg.call(zoom as any);
    applyOverlayZoomTransform(overlay);
    crossG.raise();

    if (drawTool === 'edit' && chartDrawings.length && p.onDrawingsChange) {
      const plotTop = margin.top;
      const plotH = innerH;
      const yFromRatio = (ratio: number) => plotTop + Math.max(0, Math.min(1, ratio)) * plotH;
      const xFromRatio = (ratio: number) => margin.left + Math.max(0, Math.min(1, ratio)) * innerW;
      const ig = svg.append('g').attr('class', 'userChartDrawingsInteractive').attr('pointer-events', 'all');
      chartDrawings.forEach((raw) => {
        if (raw.kind === 'hline') {
          const hd = normalizeHLineDrawing(raw);
          const py = priceLineY(y, Number(hd.price));
          const x1 = xFromRatio(hd.xLeftRatio ?? 0);
          const x2 = xFromRatio(hd.xRightRatio ?? 1);
          const g = ig.append('g').attr('data-id', hd.id);
          g.append('line')
            .attr('x1', x1).attr('x2', x2)
            .attr('y1', py).attr('y2', py)
            .attr('stroke', 'transparent').attr('stroke-width', 14);
          if (raw.id === selectedDrawId) {
            g.append('rect').attr('class', 'hlineHandle left')
              .attr('x', x1 - 6).attr('y', py - 6).attr('width', 12).attr('height', 12)
              .attr('fill', hd.color).attr('stroke', '#020308').attr('stroke-width', 1);
            g.append('rect').attr('class', 'hlineHandle right')
              .attr('x', x2 - 6).attr('y', py - 6).attr('width', 12).attr('height', 12)
              .attr('fill', hd.color).attr('stroke', '#020308').attr('stroke-width', 1);
          }
        } else if (raw.kind === 'vline') {
          const vd = normalizeVLineDrawing(raw);
          const t = candleTimeDate(vd.time);
          if (!Number.isFinite(t.getTime()) || t < domain[0] || t > domain[1]) return;
          const vx = snapChartStrokePx(zx(t));
          const y1 = yFromRatio(vd.yTopRatio);
          const y2 = yFromRatio(vd.yBottomRatio);
          const g = ig.append('g').attr('data-id', vd.id);
          g.append('line')
            .attr('x1', vx).attr('x2', vx)
            .attr('y1', y1).attr('y2', y2)
            .attr('stroke', 'transparent').attr('stroke-width', 14);
          if (raw.id === selectedDrawId) {
            g.append('rect').attr('class', 'vlineHandle top')
              .attr('x', vx - 6).attr('y', y1 - 6).attr('width', 12).attr('height', 12)
              .attr('fill', vd.color).attr('stroke', '#020308').attr('stroke-width', 1);
            g.append('rect').attr('class', 'vlineHandle bottom')
              .attr('x', vx - 6).attr('y', y2 - 6).attr('width', 12).attr('height', 12)
              .attr('fill', vd.color).attr('stroke', '#020308').attr('stroke-width', 1);
          }
        } else if (raw.kind === 'text') {
          const t = candleTimeDate(raw.time);
          if (!Number.isFinite(t.getTime())) return;
          const tx = zx(t);
          const ty = y(Number(raw.price));
          const label = String(raw.text || '');
          const boxW = Math.max(48, label.length * 6.8 + 16);
          ig.append('rect')
            .attr('data-id', raw.id)
            .attr('x', tx + 4).attr('y', ty - 18)
            .attr('width', boxW).attr('height', 22)
            .attr('fill', 'transparent');
        }
      });
      ig.selectAll<SVGGElement, unknown>('g[data-id]').each(function () {
        const node = d3.select(this);
        const id = String(node.attr('data-id') || '');
        node.style('cursor', 'grab');
        node.call(d3.drag<any, unknown>()
          .on('start', () => { latestProps.current.onSelectedDrawingChange?.(id); })
          .on('drag', (event: any) => {
            const pp = latestProps.current;
            if (!pp.onDrawingsChange) return;
            const [mx, my] = chartPointer(event.sourceEvent || event, svgEl);
            const { x: px, y: py } = clampChartPlotXY(mx, my, metrics);
            const price = y.invert(py);
            const date = zx.invert(px);
            const c = nearestCandle(date, renderData);
            pp.onDrawingsChange(safeArray<ChartDrawing>(pp.chartDrawings || []).map((d) => {
              if (d.id !== id) return d;
              if (d.kind === 'hline') return { ...normalizeHLineDrawing(d), price: Number(price.toFixed(2)) };
              if (d.kind === 'vline') return { ...d, time: c?.time || date.toISOString() };
              if (d.kind === 'text') return { ...d, time: c?.time || date.toISOString(), price: Number(price.toFixed(2)) };
              return d;
            }));
          }) as any);
      });
      ig.selectAll<SVGRectElement, unknown>('rect[data-id]').each(function () {
        const node = d3.select(this);
        const id = String(node.attr('data-id') || '');
        node.style('cursor', 'grab');
        node.call(d3.drag<any, unknown>()
          .on('start', () => { latestProps.current.onSelectedDrawingChange?.(id); })
          .on('drag', (event: any) => {
            const pp = latestProps.current;
            if (!pp.onDrawingsChange) return;
            const [mx, my] = chartPointer(event.sourceEvent || event, svgEl);
            const { x: px, y: py } = clampChartPlotXY(mx, my, metrics);
            const price = y.invert(py);
            const date = zx.invert(px);
            const c = nearestCandle(date, renderData);
            pp.onDrawingsChange(safeArray<ChartDrawing>(pp.chartDrawings || []).map((d) => {
              if (d.id !== id) return d;
              if (d.kind === 'text') return { ...d, time: c?.time || date.toISOString(), price: Number(price.toFixed(2)) };
              return d;
            }));
          }) as any);
      });
      ig.selectAll('rect.vlineHandle').each(function () {
        const handle = d3.select(this);
        const parent = d3.select((this as SVGRectElement).parentNode as SVGGElement);
        const id = String(parent.attr('data-id') || '');
        const isTop = handle.classed('top');
        handle.style('cursor', 'ns-resize').call(d3.drag<any, unknown>()
          .on('drag', (event: any) => {
            const pp = latestProps.current;
            if (!pp.onDrawingsChange) return;
            const [, my] = chartPointer(event.sourceEvent || event, svgEl);
            const ratio = Math.max(0, Math.min(1, (my - plotTop) / plotH));
            pp.onDrawingsChange(safeArray<ChartDrawing>(pp.chartDrawings || []).map((d) => {
              if (d.id !== id || d.kind !== 'vline') return d;
              const next = normalizeVLineDrawing(d);
              return isTop ? { ...next, yTopRatio: ratio } : { ...next, yBottomRatio: ratio };
            }));
          }) as any);
      });
      ig.selectAll('rect.hlineHandle').each(function () {
        const handle = d3.select(this);
        const parent = d3.select((this as SVGRectElement).parentNode as SVGGElement);
        const id = String(parent.attr('data-id') || '');
        const isLeft = handle.classed('left');
        handle.style('cursor', 'ew-resize').call(d3.drag<any, unknown>()
          .on('drag', (event: any) => {
            const pp = latestProps.current;
            if (!pp.onDrawingsChange) return;
            const [mx] = chartPointer(event.sourceEvent || event, svgEl);
            const ratio = Math.max(0, Math.min(1, (mx - margin.left) / innerW));
            pp.onDrawingsChange(safeArray<ChartDrawing>(pp.chartDrawings || []).map((d) => {
              if (d.id !== id || d.kind !== 'hline') return d;
              const next = normalizeHLineDrawing(d);
              return isLeft ? { ...next, xLeftRatio: ratio } : { ...next, xRightRatio: ratio };
            }));
          }) as any);
      });
      ig.raise();
    }
    if (restoreCrosshairSnap) paintCrosshair(restoreCrosshairSnap);
    svg.on('wheel.priceZoom', null);
  };

  const viewportClampKey = props.viewportClamp ? `${props.viewportClamp.start}|${props.viewportClamp.end}` : '';
  const savedOverlaysKey = (props.savedRangeOverlays || []).map((r) => `${r.rangeId}:${r.high}:${r.low}:${r.start}:${r.end}:${r.isActive}:${r.isParentContext}`).join('|');
  const draftOverlayKey = props.draftRangeOverlay?.visible ? `${props.draftRangeOverlay.high}:${props.draftRangeOverlay.low}:${props.draftRangeOverlay.start}:${props.draftRangeOverlay.end}:${props.draftRangeOverlay.structureLayer}` : '';
  const guidedCursorKey = `${props.guidedCursorTimeMs ?? ''}|${props.guidedParentEndMs ?? ''}|${props.focusMode ? 1 : 0}`;
  const drawingsKey = (props.chartDrawings || []).map((d) => `${d.id}:${d.kind}`).join('|');
  const tradeIdeasRenderKey = (props.chartTradeIdeas || []).map((i) => `${i.id}:${i.updatedAt}`).join('|')
    + '|draft:' + JSON.stringify(props.tradeIdeaDraft || null)
    + '|sel:' + String(props.selectedTradeIdeaId || '')
    + '|pick:' + String(props.tradePickMode || '');

  useEffect(() => {
    const svgEl = svgRef.current;
    const triggerChartRedraw = createDebouncedResizeHandler(() => scheduleDraw('resize'));

    const onLayoutResize = () => {
      const isInspectorOpen = latestProps.current.isInspectorOpen ?? false;
      if (layoutResizeGuardRef.current.shouldIgnoreRedraw(isInspectorOpen)) {
        triggerChartRedraw.cancel();
        if (svgEl) {
          const rect = svgEl.getBoundingClientRect();
          renderGateRef.current.noteDimensions(rect.width, rect.height);
        }
        return;
      }
      triggerChartRedraw();
    };

    if (svgEl && typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(onLayoutResize);
      ro.observe(svgEl);
      window.addEventListener('resize', onLayoutResize);
      return () => {
        ro.disconnect();
        window.removeEventListener('resize', onLayoutResize);
        triggerChartRedraw.cancel();
      };
    }

    window.addEventListener('resize', onLayoutResize);
    return () => {
      window.removeEventListener('resize', onLayoutResize);
      triggerChartRedraw.cancel();
    };
  }, []);

  useEffect(() => {
    if (!props.autoscaleToken) return;
    if (shouldBlockAutomaticCameraRefit(props.cameraViewOwner)) { scheduleDraw(); return; }
    manualZoomRef.current = false;
    lastYBaseRef.current = null;
    scheduleDraw();
  }, [props.autoscaleToken, props.cameraViewOwner]);

  useEffect(() => {
    draw();
  }, [props.cameraKey, props.candles.length, props.candleDataRevision, props.replayCutTime, props.events, props.rangeHigh, props.rangeLow, props.rangeStart, props.rangeEnd, props.toolMode, props.scaleMode, props.timeframe, props.candleWidthScale, props.priceZoomScale, savedOverlaysKey, draftOverlayKey, guidedCursorKey, props.showFibOverlays, drawingsKey, tradeIdeasRenderKey, props.chartDrawTool, props.selectedDrawingId, props.chartDrawColor, props.tradePickMode, viewportClampKey, props.chartEmptyState, props.cameraViewOwner]);

  useEffect(()=>{
    if (!svgRef.current || !props.candles.length || props.cameraMode !== 'LOCKED' || !props.lockedCameraDomain?.start || !props.lockedCameraDomain?.end) { return; }
    if (props.cameraViewOwner !== 'USER_LOCKED') return;
    const a = new Date(String(props.lockedCameraDomain.start));
    const b = new Date(String(props.lockedCameraDomain.end));
    if (!Number.isFinite(a.getTime()) || !Number.isFinite(b.getTime()) || Math.abs(b.getTime()-a.getTime()) < 1) { draw(); return; }
    const svgEl = svgRef.current;
    const metrics = getChartSurfaceMetrics(svgEl);
    if (!metrics) { draw(); return; }
    const cutMs = props.replayCutTime ? new Date(String(props.replayCutTime)).getTime() : null;
    const data = cutMs && Number.isFinite(cutMs) ? safeArray(props.candles).filter((d:any)=>new Date(d.time).getTime() <= cutMs) : safeArray(props.candles);
    if (!data.length) { draw(); return; }
    const x0 = chartXScaleFromData(data, metrics);
    const pxA = x0(a); const pxB = x0(b);
    if (Number.isFinite(pxA) && Number.isFinite(pxB) && Math.abs(pxB-pxA) > 4) {
      const lo = Math.min(pxA, pxB);
      const span = Math.abs(pxB-pxA);
      const k = Math.max(0.35, Math.min(180, (metrics.innerW * 0.84) / span));
      const tx = (metrics.margin.left + metrics.innerW * 0.08) - k * lo;
      transformRef.current = d3.zoomIdentity.translate(tx, 0).scale(k);
    }
    draw();
  }, [props.cameraMode, props.lockedCameraDomain?.start, props.lockedCameraDomain?.end, props.candles.length, props.replayCutTime, props.cameraViewOwner, props.cameraCommand?.token]);

  useEffect(() => {
    if (!svgRef.current || !props.viewportClamp?.start || !props.viewportClamp?.end) return;
    if (manualZoomRef.current || shouldBlockAutomaticCameraRefit(props.cameraViewOwner)) { draw(); return; }
    const cutMs = props.replayCutTime ? new Date(String(props.replayCutTime)).getTime() : null;
    const data = cutMs && Number.isFinite(cutMs)
      ? safeArray(props.candles).filter((d:any)=>new Date(d.time).getTime() <= cutMs)
      : safeArray(props.candles);
    const span = intersectClampSpanWithCandles(props.viewportClamp, data);
    if (!span || !data.length) { draw(); return; }
    const svgEl = svgRef.current;
    const metrics = getChartSurfaceMetrics(svgEl);
    if (!metrics) { draw(); return; }
    const a = new Date(span.start);
    const b = new Date(span.end);
    if (!Number.isFinite(a.getTime()) || !Number.isFinite(b.getTime()) || Math.abs(b.getTime()-a.getTime()) < 1) { draw(); return; }
    const x0 = d3.scaleTime()
      .domain([a, b])
      .range([metrics.margin.left, metrics.margin.left + metrics.innerW]);
    const pxA = x0(a);
    const pxB = x0(b);
    if (Number.isFinite(pxA) && Number.isFinite(pxB) && Math.abs(pxB-pxA) > 4) {
      const lo = Math.min(pxA, pxB);
      const spanPx = Math.abs(pxB-pxA);
      const k = Math.max(0.35, Math.min(180, (metrics.innerW * 0.92) / spanPx));
      const tx = (metrics.margin.left + metrics.innerW * 0.04) - k * lo;
      transformRef.current = d3.zoomIdentity.translate(tx, 0).scale(k);
    }
    draw();
  }, [viewportClampKey, props.candles.length, props.replayCutTime, props.timeframe]);

  useEffect(()=>{
    if (!svgRef.current || !props.candles.length) return;
    manualZoomRef.current = false;
    const svg = d3.select(svgRef.current);
    const metrics = getChartSurfaceMetrics(svgRef.current);
    if (!metrics) return;
    const bars = targetVisibleBarsForTimeframe(props.timeframe);
    const k = Math.max(1, props.candles.length / Math.max(1, bars));
    const targetRight = metrics.margin.left + metrics.innerW * CHART_LATEST_ANCHOR_RATIO;
    const tx = targetRight - k * (metrics.margin.left + metrics.innerW);
    const t = d3.zoomIdentity.translate(tx,0).scale(k);
    transformRef.current = t;
    latestProps.current.onCameraViewOwnerChange?.('AUTO', 'D3CandleMap.jumpLatest', 'jump-latest');
    svg.call((d3.zoom() as any).transform, t);
    draw();
  }, [props.jumpLatestToken]);

  useEffect(() => {
    if (!svgRef.current || !props.candles.length) return;
    const key = `${props.timeframe}:${props.candles.length}:${props.replayCutTime || ''}:${props.cameraKey || ''}`;
    if (readableZoomKeyRef.current === key) return;
    if (shouldBlockAutomaticCameraRefit(props.cameraViewOwner)) {
      readableZoomKeyRef.current = key;
      return;
    }
    // Do not refit camera on each replay tick — manual pan/zoom only during bar replay.
    if (props.replayCutTime) {
      readableZoomKeyRef.current = key;
      return;
    }
    if (manualZoomRef.current) {
      readableZoomKeyRef.current = key;
      return;
    }
    const currentK = Number(transformRef.current?.k || 1);
    if (currentK > 1.12) {
      readableZoomKeyRef.current = key;
      return;
    }
    const targetBars = targetVisibleBarsForTimeframe(props.timeframe);
    if (props.candles.length <= targetBars) {
      readableZoomKeyRef.current = key;
      return;
    }
    readableZoomKeyRef.current = key;
    const metrics = getChartSurfaceMetrics(svgRef.current);
    if (!metrics) return;
    const cutMs = props.replayCutTime ? new Date(String(props.replayCutTime)).getTime() : null;
    const data = cutMs && Number.isFinite(cutMs)
      ? safeArray(props.candles).filter((d:any) => new Date(d.time).getTime() <= cutMs)
      : safeArray(props.candles);
    if (!data.length) return;
    const centerTime = props.replayCutTime || props.selectedCandleTime || data[data.length - 1]?.time;
    const fit = centerTime ? buildCandleWindowFit(data, String(centerTime), readablePadBarsForTimeframe(props.timeframe)) : null;
    const x0 = chartXScaleFromData(data, metrics);
    if (fit) {
      const a = x0(new Date(fit.start));
      const b = x0(new Date(fit.end));
      if (Number.isFinite(a) && Number.isFinite(b) && Math.abs(b - a) > 10) {
        const span = Math.max(10, Math.abs(b - a));
        const k = Math.max(1, Math.min(160, (metrics.innerW * 0.84) / span));
        const replayCenterTime = props.replayCutTime || centerTime;
        const centered = replayCenterTime
          ? translateTransformToCenterTime(x0, String(replayCenterTime), k, metrics, 0.5)
          : null;
        transformRef.current = centered || d3.zoomIdentity.translate(
          (metrics.margin.left + metrics.innerW * 0.08) - k * Math.min(a, b),
          0,
        ).scale(k);
        draw();
        return;
      }
    }
    const k = Math.max(1, data.length / targetBars);
    const targetRight = metrics.margin.left + metrics.innerW * CHART_LATEST_ANCHOR_RATIO;
    transformRef.current = d3.zoomIdentity.translate(targetRight - k * (metrics.margin.left + metrics.innerW), 0).scale(k);
    draw();
  }, [props.candles.length, props.timeframe, props.replayCutTime, props.cameraKey, props.selectedCandleTime, props.cameraViewOwner]);

  useEffect(()=>{
    const command = props.cameraCommand;
    const hasCommand = !!command && command.token > 0 && command.intent !== 'NONE';
    const hasManualFit = props.fitAllToken > 0 || !!props.goDate;
    if (!hasCommand && !hasManualFit) return;
    if (
      hasCommand
      && shouldBlockAutomaticCameraRefit(props.cameraViewOwner)
      && !isExplicitCameraNavigationReason(command!.reason)
    ) {
      logCameraUpdate(command!.reason || command!.intent, 'D3CandleMap.cameraCommand:blocked', DEBUG_CAMERA);
      return;
    }
    if (hasCommand && command!.intent !== 'PRESERVE_OR_NEAREST_TIME') manualZoomRef.current = false;
    if (props.cameraMode === 'LOCKED' && props.lockedCameraDomain?.start && props.lockedCameraDomain?.end && !hasCommand && !hasManualFit) return;
    const rawData = props.candles || [];
    const cutMs = props.replayCutTime ? new Date(String(props.replayCutTime)).getTime() : null;
    const data = cutMs && Number.isFinite(cutMs) ? rawData.filter((d:any)=>new Date(d.time).getTime() <= cutMs) : rawData;
    if (!svgRef.current || !data.length) {
      transformRef.current = d3.zoomIdentity;
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
      draw();
      return;
    }
    const metrics = getChartSurfaceMetrics(svgRef.current);
    if (!metrics) { draw(); return; }
    const dateDomainSource = data.length ? data : rawData;
    const x0 = chartXScaleFromData(dateDomainSource, metrics);
    const { margin, innerW } = metrics;
    const fitLatest = () => {
      const bars = targetVisibleBarsForTimeframe(props.timeframe);
      const k = Math.max(1, data.length / Math.max(1, bars));
      const targetRight = margin.left + innerW * CHART_LATEST_ANCHOR_RATIO;
      const tx = targetRight - k * (margin.left + innerW);
      transformRef.current = d3.zoomIdentity.translate(tx,0).scale(k);
    };
    const fitAll = () => {
      const first = data[0];
      const last = data[data.length - 1];
      if (!first || !last) return false;
      const a = x0(candleTimeDate(first.time));
      const b = x0(candleTimeDate(last.time));
      if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
      const span = Math.max(10, Math.abs(b - a));
      const usableW = innerW * (1 - CHART_FUTURE_PAD_RATIO);
      const k = Math.max(0.35, Math.min(180, usableW / span));
      const targetRight = margin.left + innerW * CHART_LATEST_ANCHOR_RATIO;
      transformRef.current = d3.zoomIdentity.translate(targetRight - k * Math.max(a, b), 0).scale(k);
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
      return true;
    };
    const fitWindow = (startRaw?:string|null, endRaw?:string|null, singleSpan = 0.35, centerTimeRaw?: string | null, centerScreenRatio = 0.08) => {
      const start = startRaw ? new Date(String(startRaw)) : null;
      const end = endRaw ? new Date(String(endRaw)) : null;
      let validStart = !!start && Number.isFinite(start.getTime());
      let validEnd = !!end && Number.isFinite(end.getTime()) && validStart && end!.getTime() > start!.getTime();
      if (validStart && data.length) {
        const startMs = start!.getTime();
        const ext = candleDataExtent(data);
        if (ext && (startMs < ext.startMs - 86400000 * 365 || startMs > ext.endMs + 86400000 * 365 || start!.getUTCFullYear() > 2035)) {
          validStart = false;
        }
      }
      if (!validStart && data.length && startRaw) {
        const around = buildCandleWindowFit(data, String(startRaw), 42);
        if (around) return fitWindow(around.start, around.end, singleSpan, centerTimeRaw, centerScreenRatio);
      }
      if (!validStart) return false;
      const a = x0(start as Date);
      const b = validEnd ? x0(end as Date) : a + innerW * singleSpan;
      if (!Number.isFinite(a) || !Number.isFinite(b) || Math.abs(b-a) < 10) {
        return false;
      }
      const span = Math.max(10, Math.abs(b-a));
      const k = Math.max(1, Math.min(160, (innerW * 0.82) / span));
      let tx: number;
      if (centerTimeRaw) {
        const centerDate = new Date(String(centerTimeRaw));
        const centerPx = Number.isFinite(centerDate.getTime()) ? x0(centerDate) : Math.min(a, b);
        tx = (margin.left + innerW * centerScreenRatio) - k * centerPx;
      } else {
        tx = (margin.left + innerW * centerScreenRatio) - k * Math.min(a, b);
      }
      transformRef.current = d3.zoomIdentity.translate(tx,0).scale(k);
      return true;
    };
    const fitAroundTime = (timeRaw?: string | null, padBars = 42) => {
      if (!timeRaw || !data.length) return false;
      const fit = buildCandleWindowFit(data, String(timeRaw), padBars);
      if (!fit) return false;
      const ok = fitWindow(fit.start, fit.end);
      if (ok) applyPriceDomain(fit.low, fit.high, fit.padRatio ?? 0.1);
      return ok;
    };
    const fitAroundTimeHorizontalOnly = (timeRaw?: string | null, padBars = 42) => {
      if (!timeRaw || !data.length) return false;
      const fit = buildCandleWindowFit(data, String(timeRaw), padBars);
      if (!fit) return false;
      return fitWindow(fit.start, fit.end);
    };
    const resolveCommandPriceDomain = (): { low: number; high: number } | null => {
      const pd = command?.priceDomain;
      if (pd && Number.isFinite(pd.low) && Number.isFinite(pd.high) && pd.high > pd.low) return pd;
      if (String(command?.reason || '').includes('timeframe-switch') && props.lockedPriceDomain) {
        const lp = props.lockedPriceDomain;
        if (Number.isFinite(lp.low) && Number.isFinite(lp.high) && lp.high > lp.low) return lp;
      }
      return null;
    };
    const applyPreservedPriceDomain = () => {
      const pd = resolveCommandPriceDomain();
      if (!pd) return false;
      return applyPriceDomain(pd.low, pd.high, 0);
    };
    const syncZoomTransform = () => {
      const svgElNow = svgRef.current;
      if (!svgElNow) return;
      const overlaySel = d3.select(svgElNow).select<SVGRectElement>('rect.chartPanSurface');
      if (overlaySel.node()) applyOverlayZoomTransform(overlaySel);
    };
    const visibleTimeCenter = () => {
      const dom = transformRef.current.rescaleX(x0).domain();
      const mid = (dom[0].getTime() + dom[1].getTime()) / 2;
      return Number.isFinite(mid) ? new Date(mid) : null;
    };
    const applyHorizontalStretch = (factor:number) => {
      const currentCenter = command?.targetTime ? new Date(String(command.targetTime)) : visibleTimeCenter();
      if (!currentCenter || !Number.isFinite(currentCenter.getTime())) return false;
      const maxK = Math.max(120, data.length / 8);
      const currentK = Number(transformRef.current?.k || 1);
      const nextK = Math.max(0.35, Math.min(maxK, currentK * (Number(factor) || 1)));
      const centerPx = margin.left + innerW / 2;
      const centerBasePx = x0(currentCenter);
      if (!Number.isFinite(centerBasePx)) return false;
      transformRef.current = d3.zoomIdentity.translate(centerPx - nextK * centerBasePx, 0).scale(nextK);
      return true;
    };
    const applyPriceDomain = (lowRaw:any, highRaw:any, padRatio = 0.14) => {
      const low = Number(lowRaw);
      const high = Number(highRaw);
      const base = lastYBaseRef.current;
      if (!base || !Number.isFinite(low) || !Number.isFinite(high) || high <= low) return false;
      const desiredPad = Math.max((high - low) * padRatio, 1);
      const desiredLow = low - desiredPad;
      const desiredHigh = high + desiredPad;
      const desiredSpan = Math.max(1e-9, desiredHigh - desiredLow);
      const desiredCenter = (desiredLow + desiredHigh) / 2;
      const baseSpan = Math.max(1e-9, base.baseHi - base.baseLo);
      const baseCenter = (base.baseLo + base.baseHi) / 2;
      const nextZoom = Math.max(0.25, Math.min(32, baseSpan / desiredSpan));
      const pricePerPx = desiredSpan / Math.max(1, base.innerH);
      yZoomRef.current = nextZoom;
      yPanPxRef.current = (desiredCenter - baseCenter) / pricePerPx;
      return true;
    };
    const applyVerticalStretch = (factor:number) => {
      const base = lastYBaseRef.current;
      const current = lastYDomainRef.current;
      if (!base || !current) return false;
      const currentCenter = (current[0] + current[1]) / 2;
      const nextZoom = Math.max(0.25, Math.min(32, (Number(yZoomRef.current) || 1) * (Number(factor) || 1)));
      const baseSpan = Math.max(1e-9, base.baseHi - base.baseLo);
      const span = baseSpan / nextZoom;
      const pricePerPx = span / Math.max(1, base.innerH);
      const baseCenter = (base.baseLo + base.baseHi) / 2;
      yZoomRef.current = nextZoom;
      yPanPxRef.current = (currentCenter - baseCenter) / pricePerPx;
      return true;
    };
    const fitLocked = () => {
      if (!props.lockedCameraDomain?.start || !props.lockedCameraDomain?.end) return false;
      const ok = fitWindow(props.lockedCameraDomain.start, props.lockedCameraDomain.end);
      if (props.lockedPriceDomain) applyPriceDomain(props.lockedPriceDomain.low, props.lockedPriceDomain.high, 0);
      return ok;
    };
    const intent = hasCommand ? command!.intent : (props.goDate ? 'PRESERVE_OR_NEAREST_TIME' : 'LATEST');
    const targetTime = hasCommand ? command!.targetTime : props.goDate;
    let applied = false;
    if (intent === 'HORIZONTAL_STRETCH') applied = applyHorizontalStretch(command?.scaleFactor || 1) || true;
    if (intent === 'VERTICAL_STRETCH') applied = applyVerticalStretch(command?.scaleFactor || 1) || true;
    if (intent === 'RESTORE_LOCKED') applied = fitLocked();
    if (!applied && intent === 'CASE') {
      const start = props.caseStart || props.rangeStart;
      const end = props.caseEnd || props.rangeEnd;
      if (start && data.length) {
        const clamped = clampFitTimesToCandles(String(start), String(end || start), data);
        applied = fitWindow(clamped.start, clamped.end);
      } else {
        applied = resolveCommandPriceDomain()
          ? fitAroundTimeHorizontalOnly(targetTime || props.goDate, readablePadBarsForTimeframe(props.timeframe))
          : fitAroundTime(targetTime || props.goDate, readablePadBarsForTimeframe(props.timeframe));
      }
      if (applied) {
        if (!applyPreservedPriceDomain()) {
          applyPriceDomain(props.caseLow || props.rangeLow, props.caseHigh || props.rangeHigh);
        }
      }
    }
    if (!applied && intent === 'RANGE') {
      if (props.rangeStart && data.length) {
        const clamped = clampFitTimesToCandles(String(props.rangeStart), String(props.rangeEnd || props.rangeStart), data);
        applied = fitWindow(clamped.start, clamped.end);
      }
      if (applied) {
        if (!applyPreservedPriceDomain()) {
          applyPriceDomain(props.rangeLow, props.rangeHigh);
        }
      }
    }
    if (!applied && intent === 'FIT_STRUCTURAL_RANGE' && command?.fitWindow) {
      const fw = command.fitWindow;
      if (data.length) {
        const clamped = clampFitTimesToCandles(fw.start, fw.end, data);
        const centerReplay = String(command?.reason || '').includes('fit-replay') && targetTime;
        const centerAnchor = targetTime || clamped.start;
        applied = centerReplay
          ? fitWindow(clamped.start, clamped.end, 0.35, targetTime, 0.5)
          : fitWindow(clamped.start, clamped.end, 0.35, centerAnchor, 0.42);
        if (applied) {
          if (Number.isFinite(fw.low) && Number.isFinite(fw.high) && fw.high > fw.low) {
            applyPriceDomain(fw.low, fw.high, fw.padRatio ?? 0.12);
          } else {
            applyPreservedPriceDomain();
          }
        }
      }
    }
    if (!applied && intent === 'REPLAY') {
      applied = resolveCommandPriceDomain()
        ? fitAroundTimeHorizontalOnly(targetTime || props.goDate, readablePadBarsForTimeframe(props.timeframe))
        : fitAroundTime(targetTime || props.goDate, readablePadBarsForTimeframe(props.timeframe));
      if (applied) applyPreservedPriceDomain();
    }
    if (!applied && (intent === 'PRESERVE_OR_NEAREST_TIME' || intent === 'RESTORE_LOCKED') && command?.fitWindow && String(command?.reason || '').includes('routine-tf-memory')) {
      const fw = command.fitWindow;
      if (data.length && fw.start && fw.end) {
        const clamped = clampFitTimesToCandles(fw.start, fw.end, data);
        applied = fitWindow(clamped.start, clamped.end, 0.08);
        if (!applied && targetTime) {
          applied = fitAroundTime(targetTime, Math.max(
            readablePadBarsForTimeframe(props.timeframe),
            Math.floor(minimumRoutineVisibleBarsForTimeframe(props.timeframe) / 2),
          ));
        }
        if (applied) {
          if (command.priceDomain && Number.isFinite(command.priceDomain.low) && Number.isFinite(command.priceDomain.high) && command.priceDomain.high > command.priceDomain.low) {
            applyPriceDomain(command.priceDomain.low, command.priceDomain.high, 0);
          } else {
            applyPreservedPriceDomain();
          }
        }
      }
    }
    if (!applied && (intent === 'PRESERVE_OR_NEAREST_TIME' || intent === 'RESTORE_LOCKED')) {
      applied = targetTime
        ? (resolveCommandPriceDomain()
          ? fitAroundTimeHorizontalOnly(targetTime, readablePadBarsForTimeframe(props.timeframe))
          : fitAroundTime(targetTime, readablePadBarsForTimeframe(props.timeframe)))
        : false;
      if (applied) applyPreservedPriceDomain();
    }
    if (!applied && intent === 'LATEST') { fitLatest(); applied = true; }
    if (!applied && intent === 'FIT_ALL') applied = fitAll();
    if (!applied) {
      fitLatest();
    } else if (intent === 'LATEST') {
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
    }
    syncZoomTransform();
    draw();
    if (applied && hasCommand && command!.intent !== 'PRESERVE_OR_NEAREST_TIME') {
      manualZoomRef.current = true;
    }
    if (hasCommand) {
      logCameraUpdate(command!.reason || command!.intent, 'D3CandleMap.cameraCommand', DEBUG_CAMERA);
    }
  }, [props.fitAllToken, props.goDate, props.cameraCommand?.token, props.cameraViewOwner]);

  return <svg ref={svgRef} className="d3CandleSvg" />;
}

function pageTitle(p: Page) { return ({ mapstudio:'Map Studio', ideas:'Trade Ideas', brain:'Lifecycle Catch-Up', journal:'Journal Reports', sql:'SQL / Backend', settings:'Display Settings', data:'Data Collection Statistics', historical:'Historical Lifecycle Builder' } as Record<Page, string>)[p]; }
function pageSubtitle(p: Page) { return ({ mapstudio:'OHLC candles, range overlay, trajectory path, and event coordinates. Finally, candles with memory.', ideas:'Pre-plan the narrative before the market starts whispering nonsense.', brain:'Manually catch the machine up with Macro → Weekly → Daily → Intraday → Micro lifecycle state.', journal:'Historical live trades and future data collection view.', sql:'Backend status and recent records.', settings:'Set ranges, mitigation states, tick intervals, and editable map paths.', data:'Run the local Python analyst on selected packages and review structural statistics.', historical:'Create date-aware Weekly/Daily/Intraday lifecycle bundles. The machine links context by symbol + date.' } as Record<Page, string>)[p]; }

function XYTrajectoryPanel({ title, layerKey, layer, visual, updateVisual, accent, intraday, livePrice, readOnly = false, compact = false }: { title: string; layerKey: LayerKey; layer?: Layer; visual: VisualLayer; updateVisual: (k: LayerKey, p: Partial<VisualLayer>) => void; accent: string; intraday?: any; livePrice?: number | null; readOnly?: boolean; compact?: boolean }) {
  const currentZone = visual.currentZone || layer?.auto_location || layer?.location || (intraday?.phase_label || 'Fair');
  const objective = visual.objectiveZone || layer?.objective || intraday?.trade_type || 'Objective';
  const trajectory = visual.narrative || layer?.trajectory || intraday?.current_state || 'Manual trajectory';
  const path = visual.path || [];
  const low = parseNum(visual.rangeLow), high = parseNum(visual.rangeHigh);
  const hasRange = Number.isFinite(low) && Number.isFinite(high) && high > low;
  const tickStep = Number(visual.tickStep || (layerKey === 'intraday' ? 50 : 200));
  const ticks = hasRange ? buildPriceTicks(low, high, tickStep) : [];
  const liveCurrentEnabled = !!visual.useLiveCurrent;
  const displayPoint = (p: GraphPoint) => {
    const isCurrent = String(p.label || '').toLowerCase().includes('current') || !!p.live;
    if (liveCurrentEnabled && isCurrent && livePrice && hasRange) return { ...p, price: String(Math.round(livePrice * 100) / 100), live: true };
    return p;
  };
  const displayPath = path.map(displayPoint);
  const currentIndex = Math.max(0, displayPath.findIndex(p => String(p.label || '').toLowerCase().includes('current') || !!p.live));
  const currentPoint = displayPath[currentIndex >= 0 ? currentIndex : Math.max(0, displayPath.length - 1)];
  const yPoint = (p: GraphPoint) => hasRange && p.price ? yForPrice(parseNum(p.price), low, high) : yForZone(p.zone);
  const yObjective = hasRange ? yForPrice(priceForZone(objective, low, high), low, high) : yForZone(objective);
  const yLive = hasRange && livePrice ? yForPrice(livePrice, low, high) : null;
  const yCurrentGuide = currentPoint ? yPoint(currentPoint) : yLive;
  const liveStatus = liveCurrentEnabled ? (livePrice ? 'LIVE' : 'STALE') : 'MANUAL';
  const pointX = (p: GraphPoint, i: number) => matrixXForPoint(p, i, displayPath.length, layerKey);
  const projectionX = readOnly && layerKey === 'intraday' ? 92 : (readOnly && currentPoint ? Math.max(92, pointX(currentPoint, currentIndex)) : clamp(Number(visual.projectionX ?? 90), 10, 96));
  const projectionPrice = parseNum(visual.projectionPrice);
  const yProjection = hasRange && Number.isFinite(projectionPrice) ? yForPrice(projectionPrice, low, high) : yObjective;
  const brokenExternal = visual.brokenExternal || 'NONE';
  const brokenExternalPrice = parseNum(visual.brokenExternalPrice);
  const brokenY = brokenExternal === 'NONE' ? null : (hasRange && Number.isFinite(brokenExternalPrice) ? yForPrice(brokenExternalPrice, low, high) : brokenExternal === 'EXT_H' ? 8 : 92);
  const liquidityCleanUpPrice = parseNum(visual.liquidityCleanUpPrice);
  const liquidityCleanUpY = layerKey === 'intraday' && hasRange && Number.isFinite(liquidityCleanUpPrice) ? yForPrice(liquidityCleanUpPrice, low, high) : null;
  const showLiquidityCleanUp = layerKey === 'intraday' && visual.showLiquidityCleanUp !== false && liquidityCleanUpY !== null;
  const biasFlow = getExtFlow(visual.mapBias, trajectory);
  const rightFlowLabel = biasFlow === 'bearish' ? 'EXT H → EXT L' : biasFlow === 'bullish' ? 'EXT L → EXT H' : 'EXT L ↔ EXT H';

  const updatePoint = (id: string, patch: Partial<GraphPoint>) => updateVisual(layerKey, { path: path.map(p => p.id === id ? { ...p, ...patch } : p) });
  const addPoint = () => updateVisual(layerKey, { path: [...path, makePoint(anchorsForLayer(layerKey)[0] || 'NEW_ANCHOR', currentZone, 50, hasRange ? String(Math.round(priceForZone(currentZone, low, high) * 100) / 100) : '', anchorsForLayer(layerKey)[0] || 'NEW_ANCHOR')] });
  const removePoint = (id: string) => updateVisual(layerKey, { path: path.filter(p => p.id !== id) });
  const movePoint = (id: string, dir: -1 | 1) => { const idx = path.findIndex(p => p.id === id); const next = idx + dir; if (idx < 0 || next < 0 || next >= path.length) return; const copy = [...path]; [copy[idx], copy[next]] = [copy[next], copy[idx]]; updateVisual(layerKey, { path: copy }); };
  const clearPath = () => updateVisual(layerKey, { path: [makePoint('Origin', currentZone, 12), makePoint('Current', currentZone, 48)] });
  const structuralMetrics = getStructuralMetrics(layerKey, displayPath, low, high, hasRange, currentPoint, visual);
  const narrativeInvalidated = String(visual.meta?.phaseState || '').toUpperCase() === 'INVALIDATED' || displayPath.some(p => String(p.status || '').toUpperCase() === 'INVALIDATED');

  const dragPoint = (id: string, e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const graph = (e.currentTarget.closest('.xyGraph') as HTMLDivElement); if (!graph) return;
    const updateFromEvent = (ev: PointerEvent | React.PointerEvent) => {
      const r = graph.getBoundingClientRect();
      const yPct = clamp(((ev.clientY - r.top) / r.height) * 100, 4, 96);
      const patch: Partial<GraphPoint> = {}; // v0.20: X position is matrix-sequenced; dragging adjusts price only.
      if (hasRange) patch.price = String(Math.round(priceFromY(yPct, low, high) * 100) / 100); else patch.zone = zoneFromY(yPct);
      updatePoint(id, patch);
    };
    updateFromEvent(e);
    const move = (ev: PointerEvent) => updateFromEvent(ev);
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };



  const dragProjection = (e: React.PointerEvent<HTMLDivElement>) => {
    if (readOnly) return;
    e.preventDefault();
    const graph = (e.currentTarget.closest('.xyGraph') as HTMLDivElement); if (!graph) return;
    const updateFromEvent = (ev: PointerEvent | React.PointerEvent) => {
      const r = graph.getBoundingClientRect();
      const x = clamp(((ev.clientX - r.left) / r.width) * 100, 10, 96);
      const yPct = clamp(((ev.clientY - r.top) / r.height) * 100, 4, 96);
      const patch: Partial<VisualLayer> = { projectionX: x };
      if (hasRange) patch.projectionPrice = String(Math.round(priceFromY(yPct, low, high) * 100) / 100);
      else patch.objectiveZone = zoneFromY(yPct);
      updateVisual(layerKey, patch);
    };
    updateFromEvent(e);
    const move = (ev: PointerEvent) => updateFromEvent(ev);
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };

  return <div className={`trajectoryCard xy layer-${layerKey} ${accent} ${visual.mapBias || 'manual'}Bias ${readOnly ? 'readOnlyMap' : 'editableMap'} ${compact ? 'compactMap' : ''}`}>
    <div className="cardHeader"><div><h3>{title}</h3><p>{trajectory}</p></div><div className="headerBadges"><div className="locationBadge">Current: {currentZone}</div><div className="objectiveBadge">Objective: {objective}</div></div></div>
    {!readOnly && <div className="rangeInputs compact"><label>Low<input value={visual.rangeLow || ''} onChange={e => updateVisual(layerKey, { rangeLow: e.target.value })} placeholder="range low" /></label><label>High<input value={visual.rangeHigh || ''} onChange={e => updateVisual(layerKey, { rangeHigh: e.target.value })} placeholder="range high" /></label><label>Tick<select value={String(tickStep)} onChange={e => updateVisual(layerKey, { tickStep: Number(e.target.value) })}><option value="50">$50</option><option value="100">$100</option><option value="200">$200</option><option value="500">$500</option></select></label><label>Objective<select value={objective} onChange={e => updateVisual(layerKey, { objectiveZone: e.target.value })}>{ZONES.map(z => <option key={z}>{z}</option>)}</select></label><label>Broken External<select value={visual.brokenExternal || 'NONE'} onChange={e => updateVisual(layerKey, { brokenExternal: e.target.value as any })}><option value="NONE">None</option><option value="EXT_H">Broken EXT H</option><option value="EXT_L">Broken EXT L</option></select></label><label>Broken Ref Price<input value={visual.brokenExternalPrice || ''} onChange={e => updateVisual(layerKey, { brokenExternalPrice: e.target.value })} placeholder="broken level price" /></label><label>Projection Price<input value={visual.projectionPrice || ''} onChange={e => updateVisual(layerKey, { projectionPrice: e.target.value })} placeholder="drag blue endpoint" /></label><label className="checkLabel"><input type="checkbox" checked={!!visual.useLiveCurrent} onChange={e => updateVisual(layerKey, { useLiveCurrent: e.target.checked })}/> Current uses live price</label></div>}
    <div className={`xyGraph boxedGraph cleanMapGraph matrixRailGraph ${narrativeInvalidated ? 'invalidatedGraph' : ''}`}>
      <div className="fibBackdrop"><div className="fibPremium"><span>Premium</span></div><div className="fibFair"><span>Fair price</span></div><div className="fibDiscount"><span>Discount</span></div></div>
      <div className="matrixRails">{[0,1,2,3,4,5].map(i => <span key={i} style={{ left: `${matrixXFor(i,6)}%` }}><b>{matrixLabelFor(layerKey, i)}</b></span>)}</div>
      {structuralMetrics.length > 0 && <div className="metricOverlay">{structuralMetrics.map((m, i) => <span key={i}>{m}</span>)}</div>}
      {narrativeInvalidated && <div className="invalidatedCloak"><b>STRUCTURE INVALIDATED</b><span>Future columns muted. Narrative dead.</span></div>}
      {hasRange && <div className="priceAxis clean leftPriceAxis">{ticks.map(t => <span key={t.price} style={{ top: `${t.y}%` }}>{t.price}</span>)}</div>}
      {!hasRange && <div className="priceAxis clean leftPriceAxis zoneFallback"><span style={{top:'8%'}}>Ext H</span><span style={{top:'50%'}}>Fair</span><span style={{top:'92%'}}>Ext L</span></div>}
      <div className="axisX"><span>Origin</span><span>Reaction</span><span>Current</span><span>Objective</span></div>
      <div className="rangeBoundaryLine high"></div>
      <div className="rangeBoundaryLine low"></div>
      <div className="objectiveGlow" style={{ top: `${yObjective}%` }}><span>{objective}</span></div>
      {brokenY !== null && <div className={`brokenExternalLine ${brokenExternal === 'EXT_H' ? 'high' : 'low'}`} style={{ top: `${brokenY}%` }}><span>{brokenExternal === 'EXT_H' ? 'Broken EXT H / BOS ref' : 'Broken EXT L / BOS ref'}</span></div>}
      {yCurrentGuide !== null && <div className={`currentGuideLine ${liveStatus.toLowerCase()}`} style={{ top: `${yCurrentGuide}%` }}><span>Current {currentPoint?.price ? currentPoint.price : currentZone} · {liveStatus}</span></div>}
      {yLive !== null && <div className="livePriceLine" style={{ top: `${yLive}%` }}><span>Live {livePrice?.toFixed(2)}</span></div>}
      {showLiquidityCleanUp && <div className="liquidityCleanUpLine" style={{ top: `${liquidityCleanUpY}%` }}><span>Liquidity Clean Up: {visual.liquidityCleanUpPrice}</span></div>}
      <svg className="xySvg" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline className="pricePath" points={displayPath.map((p, i) => `${pointX(p, i)},${yPoint(p)}`).join(' ')} />{path.length > 0 && <polyline className="ghostPath" points={`${pointX(currentPoint || displayPath[displayPath.length-1], currentIndex >= 0 ? currentIndex : displayPath.length-1)},${yPoint(currentPoint || displayPath[displayPath.length-1])} ${projectionX},${yProjection}`} />}</svg>
      {path.length > 0 && !readOnly && <div onPointerDown={dragProjection} className="projectionHandle" style={{ left: `${projectionX}%`, top: `${yProjection}%` }}><span>Drag projection</span></div>}
      {displayPath.map((p, i) => { const isCurrentPoint = i === currentIndex || String(p.label || '').toLowerCase().includes('current') || !!p.live; return <div key={p.id} onPointerDown={readOnly ? undefined : (e) => dragPoint(p.id, e)} className={`graphNode ${isCurrentPoint ? 'currentNode liveDominantNode' : ''} ${readOnly ? 'lockedNode' : ''}`} style={{ left: `${pointX(p, i)}%`, top: `${yPoint(p)}%` }}><span>{p.label}{hasRange && p.price ? ` • ${p.price}` : ''}</span></div>; })}
    </div>
    {!readOnly && <div className="pathEditor"><div className="editorTitle"><b>Plot map path</b><div className="btnRow"><button onClick={addPoint}>+ Add swing</button><button onClick={clearPath}>Reset</button></div></div>{path.map((p, idx) => <PointRow key={p.id} point={p} index={idx} total={path.length} layerKey={layerKey} hasRange={hasRange} low={low} high={high} updatePoint={updatePoint} removePoint={removePoint} movePoint={movePoint}/>)}</div>}
    <div className="legendRow"><Mini label="Range" value={`${visual.rangeLow || 'Low'} → ${visual.rangeHigh || 'High'}`} /><Mini label="Path" value={path.map(p => p.label || p.zone).join(' → ')} /><Mini label="Next draw" value={objective} highlight /></div>
    <div className="mitigationRow"><Pill label="Ext L" value={visual.mitigation.extL || layer?.external_low_mitigation || 'Fresh'} /><Pill label="Disc" value={visual.mitigation.discount || layer?.discount_mitigation || 'Fresh'} /><Pill label="Prem" value={visual.mitigation.premium || layer?.premium_mitigation || 'Fresh'} /><Pill label="Ext H" value={visual.mitigation.extH || layer?.external_high_mitigation || 'Fresh'} /></div>
  </div>;
}

function PointRow({ point, index, total, layerKey, hasRange, low, high, updatePoint, removePoint, movePoint }: any) {
  const anchorOptions = anchorsForLayer(layerKey || 'daily');
  return <div className="pointRow pointRowV6">
    <div className="orderButtons"><button disabled={index === 0} onClick={() => movePoint(point.id, -1)}>↑</button><button disabled={index >= total - 1} onClick={() => movePoint(point.id, 1)}>↓</button></div>
    <select value={point.anchorKey || point.label || anchorOptions[0]} onChange={e => updatePoint(point.id, { anchorKey: e.target.value, label: e.target.value })}>{anchorOptions.map((z:string) => <option key={z}>{z}</option>)}</select>
    <select value={point.status || 'INTACT'} onChange={e => updatePoint(point.id, { status: e.target.value })}>{ANCHOR_STATUS.map(z => <option key={z}>{z}</option>)}</select>
    <select value={point.zone} onChange={e => updatePoint(point.id, { zone: e.target.value, price: hasRange ? String(Math.round(priceForZone(e.target.value, low, high) * 100) / 100) : point.price })}>{ZONES.map(z => <option key={z}>{z}</option>)}</select>
    <input value={point.price || ''} onChange={e => updatePoint(point.id, { price: e.target.value, live: false })} placeholder="price" />
    <input value={point.role || ''} onChange={e => updatePoint(point.id, { role: e.target.value })} placeholder="role / note" />
    <span className="matrixCol">COL {anchorColumnIndex(point, index, total, layerKey || 'daily') + 1}</span>
    <label className="pointLiveToggle"><input type="checkbox" checked={!!point.live} onChange={e => updatePoint(point.id, { live: e.target.checked })}/> live</label>
    <button className="smallDanger" onClick={() => removePoint(point.id)}>×</button>
  </div>;
}


const MACRO_STATES = ['MACRO_CONTEXT_MANUAL','MACRO_RANGE_ACTIVE','MACRO_LOW_ABANDONED','MACRO_HIGH_ABANDONED','MACRO_EXPANSION_ACTIVE','NEW_MACRO_RANGE_CONFIRMED','MACRO_DEMAND_INTERACTION','MACRO_SUPPLY_INTERACTION','MACRO_TRAJECTORY_FLIP'];
const WEEKLY_STATES_V130 = ['WEEKLY_CONTEXT_ACTIVE','WEEKLY_RANGE_ACTIVE','WEEKLY_EXPANSION_ACTIVE','WEEKLY_PULLBACK_TO_MACRO_FAIR_PRICE','WEEKLY_INDUCEMENT_SWING_FORMED','WEEKLY_BOS_DOWN_RECLAIM','WEEKLY_BOS_UP_RECLAIM','WEEKLY_BULLISH_BIAS_ACTIVE','WEEKLY_BEARISH_BIAS_ACTIVE','WEEKLY_RANGE_ABANDONED','WEEKLY_OLD_RANGE_RETEST_PENDING'];
const DAILY_STATES_V130 = ['DAILY_PRE_CHOCH','DAILY_CHOCH_CONFIRMED','DAILY_CHOCH_RANGE_MARKED','DAILY_P1_ACTIVE','DAILY_P1_BOS_CONFIRMED','DAILY_P2_ACTIVE','DAILY_P2_BOS_CONFIRMED','DAILY_P3_ACTIVE','DAILY_P3_FAILED','DAILY_NEW_P1_ACTIVE','DAILY_PROFILE_FLIP_ACTIVE','DAILY_INDUCEMENT_SWING_FORMED','DAILY_CONTINUATION_RESUMED','DAILY_INVALIDATED'];
const DAILY_STRUCTURE_EVENTS_V130 = ['WAITING','BOS_UP_RECLAIM','BOS_DOWN_RECLAIM','MOMENTUM_BOS_UP','MOMENTUM_BOS_DOWN','SUPPLY_FLIP_DEMAND','DEMAND_FLIP_SUPPLY','BULLISH_CONTINUATION','BEARISH_CONTINUATION'];
const INTRADAY_STATES_V130 = ['PRE_CHOCH','CHOCH_CONFIRMED','CHOCH_RANGE_MARKED','IMMEDIATE_ENTRY_ACTIVE','P1_ACTIVE','P1_BOS_CONFIRMED','P2_ACTIVE','P2_RETEST_ACTIVE','P2_RETEST_COMPLETE','P2_BOS_CONFIRMED','INTERNAL_SWEEP_CLEANUP','REF_CONFIRMATION_ACTIVE','ADD_RISK_READY','P3_ACTIVE','P3_FAILED','NEW_P1_ACTIVE','PROFILE_FLIP_ACTIVE','INVALIDATED'];
const BIAS_OPTIONS_V130 = ['WATCHING','BULLISH','BEARISH'];
const INDUCEMENT_OPTIONS_V130 = ['NOT_TAGGED','INDUCEMENT_SWING_BULLISH','INDUCEMENT_SWING_BEARISH'];
const RETEST_OPTIONS_V130 = ['WAITING','RETEST_PENDING','RETEST_ACTIVE','RETEST_COMPLETE','RETEST_FAILED','PROFILE_SHIFT'];
const FAV_TRADE_OPTIONS_V130 = ['NO_FAVOURABLE_TRADE','IMMEDIATE_CONTINUATION','P1_DEVELOPMENT','P2_CONTINUATION','P3_FAILURE_REVERSAL','NEW_P1_PROFILE_FLIP_CONTINUATION','CONFIRMED_CONTINUATION_ADD_RISK'];
const MICRO_OPTIONS_V130 = ['WAITING','CONFIRMED','READY','REF_CANDLE_CONFIRMED','MICRO_ENTRY_APPROVED','INVALIDATED'];

function LifecycleCatchUpWizard({ symbol, onSaved }: { symbol: string; onSaved?: () => void }) {
  const [snap, setSnap] = useState<any>(null);
  const [msg, setMsg] = useState('');
  const loadSnap = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/lifecycle/snapshot?symbol=${encodeURIComponent(symbol)}`);
      const j = await r.json();
      setSnap(j?.snapshot || null);
      setMsg(`Loaded ${new Date().toLocaleTimeString()}`);
    } catch (e:any) { setMsg(`Load failed: ${e?.message || e}`); }
  };
  useEffect(() => { loadSnap(); }, [symbol]);
  const update = (section: string, key: string, value: any) => setSnap((prev:any) => ({ ...(prev || { symbol }), [section]: { ...((prev || {})[section] || {}), [key]: value }}));
  const save = async () => {
    try {
      const payload = { ...(snap || {}), symbol, updated_by: 'electron', updated_from_device: 'electron_catch_up_wizard' };
      const r = await fetch(`${BASE_URL}/api/v1/lifecycle/snapshot`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const j = await r.json();
      if (!r.ok || j?.ok === false) throw new Error(j?.error || `Save failed ${r.status}`);
      setSnap(j.snapshot);
      setMsg(`Saved ${new Date().toLocaleTimeString()}`);
      onSaved?.();
    } catch (e:any) { setMsg(`Save failed: ${e?.message || e}`); }
  };
  const macro = snap?.macro || {}, weekly = snap?.weekly || {}, daily = snap?.daily || {}, intraday = snap?.intraday || {}, micro = snap?.micro || {};
  return <div className="card largeCard catchUpWizard">
    <div className="cardHeader tight"><div><h3>Lifecycle Catch-Up Wizard</h3><p>Tell the machine the current family-tree story. Backend stores this and Android/Electron both read it.</p></div><Target className="goldIcon" size={24}/></div>
    <div className="settingsActionRow"><button onClick={loadSnap}>Load Snapshot</button><button className="primaryBtn" onClick={save}>Save To Backend</button><span>{msg || 'Backend lifecycle memory, not execution.'}</span></div>
    <div className="catchGrid">
      <CatchCard title="Macro / Grandparent"><SelectLine label="State" value={macro.macro_state} options={MACRO_STATES} onChange={(v:any)=>update('macro','macro_state',v)}/><InputLine label="Abandoned Low" value={macro.abandoned_macro_low} onChange={(v:any)=>update('macro','abandoned_macro_low',v)}/><InputLine label="Abandoned High" value={macro.abandoned_macro_high} onChange={(v:any)=>update('macro','abandoned_macro_high',v)}/><InputLine label="New Macro High" value={macro.new_macro_swing_high} onChange={(v:any)=>update('macro','new_macro_swing_high',v)}/><InputLine label="Macro Low" value={macro.macro_low} onChange={(v:any)=>update('macro','macro_low',v)}/><InputLine label="Macro High" value={macro.macro_high} onChange={(v:any)=>update('macro','macro_high',v)}/></CatchCard>
      <CatchCard title="Weekly / Parent"><SelectLine label="State" value={weekly.weekly_state} options={WEEKLY_STATES_V130} onChange={(v:any)=>update('weekly','weekly_state',v)}/><SelectLine label="Bias" value={weekly.weekly_bias} options={BIAS_OPTIONS_V130} onChange={(v:any)=>update('weekly','weekly_bias',v)}/><SelectLine label="Inducement" value={weekly.inducement_swing} options={INDUCEMENT_OPTIONS_V130} onChange={(v:any)=>update('weekly','inducement_swing',v)}/><SelectLine label="Objective 1" value={weekly.objective_1} options={OBJECTIVE_TYPES} onChange={(v:any)=>update('weekly','objective_1',v)}/><SelectLine label="Objective 2" value={weekly.objective_2} options={OBJECTIVE_TYPES} onChange={(v:any)=>update('weekly','objective_2',v)}/></CatchCard>
      <CatchCard title="Daily / Tradeable Route"><SelectLine label="State" value={daily.daily_state} options={DAILY_STATES_V130} onChange={(v:any)=>update('daily','daily_state',v)}/><SelectLine label="Profile" value={daily.daily_profile} options={DAILY_PROFILES} onChange={(v:any)=>update('daily','daily_profile',v)}/><SelectLine label="Structure Event" value={daily.structure_event} options={DAILY_STRUCTURE_EVENTS_V130} onChange={(v:any)=>update('daily','structure_event',v)}/><SelectLine label="PD Sweep" value={daily.previous_day_sweep} options={['NONE','PDH','PDL']} onChange={(v:any)=>update('daily','previous_day_sweep',v)}/><SelectLine label="Inducement" value={daily.inducement_swing} options={INDUCEMENT_OPTIONS_V130} onChange={(v:any)=>update('daily','inducement_swing',v)}/><SelectLine label="Retest" value={daily.retest_status} options={RETEST_OPTIONS_V130} onChange={(v:any)=>update('daily','retest_status',v)}/></CatchCard>
      <CatchCard title="Intraday / Execution"><SelectLine label="State" value={intraday.phase_state || intraday.intraday_state} options={INTRADAY_STATES_V130} onChange={(v:any)=>update('intraday','phase_state',v)}/><SelectLine label="Profile" value={intraday.intraday_profile} options={INTRADAY_PROFILES} onChange={(v:any)=>update('intraday','intraday_profile',v)}/><SelectLine label="Favourable Trade" value={intraday.favourable_trade} options={FAV_TRADE_OPTIONS_V130} onChange={(v:any)=>update('intraday','favourable_trade',v)}/><SelectLine label="Retest" value={intraday.retest_status} options={RETEST_OPTIONS_V130} onChange={(v:any)=>update('intraday','retest_status',v)}/><InputLine label="CHOCH High" value={intraday.choch_high} onChange={(v:any)=>update('intraday','choch_high',v)}/><InputLine label="CHOCH Break" value={intraday.choch_break} onChange={(v:any)=>update('intraday','choch_break',v)}/><InputLine label="CHOCH Low" value={intraday.choch_low} onChange={(v:any)=>update('intraday','choch_low',v)}/><InputLine label="Liquidity Cleanup" value={intraday.liquidity_cleanup_price} onChange={(v:any)=>update('intraday','liquidity_cleanup_price',v)}/></CatchCard>
      <CatchCard title="Micro / 15m Confirmation"><SelectLine label="Confirmation" value={micro.confirmation} options={MICRO_OPTIONS_V130} onChange={(v:any)=>update('micro','confirmation',v)}/><InputLine label="Trigger TF" value={micro.trigger_timeframe} onChange={(v:any)=>update('micro','trigger_timeframe',v)}/><InputLine label="Trigger Model" value={micro.trigger_model} onChange={(v:any)=>update('micro','trigger_model',v)}/></CatchCard>
    </div>
  </div>;
}
function CatchCard({ title, children }: any) { return <div className="catchCard"><h4>{title}</h4>{children}</div>; }
function SelectLine({ label, value, options, onChange }: any) { return <label className="fieldLine"><span>{label}</span><select value={value || options?.[0] || ''} onChange={e=>onChange(e.target.value)}>{(options || []).map((o:any)=><option key={o}>{o}</option>)}</select></label>; }
function InputLine({ label, value, onChange }: any) { return <label className="fieldLine"><span>{label}</span><input value={value ?? ''} onChange={e=>onChange(e.target.value)} /></label>; }

function TradeIdeaPanel({ ideas, setIdeas, selectedIdea, setSelectedIdea, state, brain, currentSymbol, large }: any) {
  const [form, setForm] = useState<Partial<TradeIdea>>({ symbol: 'XAUUSD', direction: 'SELL', setupType: 'Continuation', status: 'Watching', riskMode: 'Feeler Risk 0.5%' });
  const addIdea = () => {
    const idea: TradeIdea = { id: `idea_${Date.now()}`, symbol: form.symbol || 'XAUUSD', direction: (form.direction as any) || 'SELL', setupType: form.setupType || 'Continuation', status: form.status || 'Watching', weekly: form.weekly || state?.engine_gate?.summary?.weekly_trajectory || '', daily: form.daily || state?.engine_gate?.summary?.daily_trajectory || '', objective: form.objective || state?.engine_gate?.summary?.daily_objective || '', waitingFor: form.waitingFor || '15m sweep + CHOCH/reclaim confirmation', invalidationPrice: form.invalidationPrice || '', riskMode: form.riskMode || 'Feeler Risk 0.5%', notes: form.notes || '', createdAt: new Date().toISOString() };
    setIdeas([idea, ...ideas]); setSelectedIdea(idea.id); setForm({ symbol: idea.symbol, direction: idea.direction, setupType: idea.setupType, status: 'Watching', riskMode: idea.riskMode });
  };
  const updateIdea = (id: string, patch: Partial<TradeIdea>) => setIdeas(ideas.map((x: TradeIdea) => x.id === id ? { ...x, ...patch } : x));
  const removeIdea = (id: string) => setIdeas(ideas.filter((x: TradeIdea) => x.id !== id));
  const addQuickIdeaFromBrain = async () => {
    const participation = brain?.participation || {};
    const daily = brain?.daily || {};
    const direction = participation.suggested_direction && participation.suggested_direction !== 'NONE' ? participation.suggested_direction : (form.direction || 'BUY');
    const setupType = participation.participation_status === 'EXECUTE_ALLOWED' ? 'Quick Ready Trade' : 'Quick Trade Idea';
    const localIdea: TradeIdea = {
      id: `idea_${Date.now()}`,
      symbol: currentSymbol || form.symbol || 'XAUUSD',
      direction: direction === 'SELL' ? 'SELL' : 'BUY',
      setupType,
      status: participation.participation_status || 'Watching',
      weekly: brain?.weekly?.weekly_state || '',
      daily: `${daily.daily_bias || 'WATCHING'} / ${daily.context || ''}`,
      objective: (daily.objective_ladder || []).join(' → ') || form.objective || '',
      waitingFor: participation.next_required_step || 'Wait for lifecycle confirmation',
      invalidationPrice: form.invalidationPrice || '',
      riskMode: participation.risk_permission || form.riskMode || 'Feeler Risk 0.5%',
      notes: participation.machine_message || '',
      createdAt: new Date().toISOString(),
    };
    setIdeas([localIdea, ...ideas]);
    setSelectedIdea(localIdea.id);
    try {
      await fetch(`${BASE_URL}/api/v1/trade-ideas/quick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: localIdea.symbol,
          direction: localIdea.direction,
          setup_type: setupType,
          lifecycle_state: localIdea.status,
          risk_percent: localIdea.riskMode.includes('1') ? 1 : localIdea.riskMode.includes('0.25') ? 0.25 : 0.5,
          sl_price: localIdea.invalidationPrice,
          objective: localIdea.objective,
          waiting_for: localIdea.waitingFor,
          notes: localIdea.notes,
          source: 'electron_quick_idea'
        })
      });
    } catch {
      // Local idea still saved. Backend will get over itself on the next save.
    }
  };
  return <div className={`card tradeIdeaCard ${large ? 'largeCard' : ''}`}><div className="cardHeader tight"><div><h3>Live Trade Idea</h3><p>Idea matures across sessions before execution.</p></div><CircleDot className="blueIcon" size={20}/></div><div className="ideaForm"><select value={form.symbol || 'XAUUSD'} onChange={e => setForm({ ...form, symbol: e.target.value })}><option>XAUUSD</option><option>US500.cash</option></select><select value={form.direction || 'SELL'} onChange={e => setForm({ ...form, direction: e.target.value as any })}><option>SELL</option><option>BUY</option></select><select value={form.setupType || 'Continuation'} onChange={e => setForm({ ...form, setupType: e.target.value })}><option>A+ Reversal</option><option>A Reversal</option><option>Continuation</option><option>Speculative Probe</option></select><select value={form.riskMode || 'Feeler Risk 0.5%'} onChange={e => setForm({ ...form, riskMode: e.target.value })}><option>Feeler Risk 0.25%</option><option>Feeler Risk 0.5%</option><option>Full Risk 1%</option><option>Additional Risk 0.5%</option></select><input placeholder="Invalidation / SL price" value={form.invalidationPrice || ''} onChange={e => setForm({ ...form, invalidationPrice: e.target.value })}/><input placeholder="Objective" value={form.objective || ''} onChange={e => setForm({ ...form, objective: e.target.value })}/><textarea placeholder="Waiting for..." value={form.waitingFor || ''} onChange={e => setForm({ ...form, waitingFor: e.target.value })}/><textarea placeholder="Notes / session expectation" value={form.notes || ''} onChange={e => setForm({ ...form, notes: e.target.value })}/><button className="primaryBtn" onClick={addIdea}>Add Trade Idea</button><button onClick={addQuickIdeaFromBrain}>Quick Idea From Lifecycle Brain</button></div><div className="ideaList">{ideas.map((idea: TradeIdea) => <div key={idea.id} className={`ideaItem ${selectedIdea?.id === idea.id ? 'picked' : ''}`} onClick={() => setSelectedIdea(idea.id)}><div><b>{idea.symbol} {idea.direction}</b><span>{idea.setupType} • <select value={idea.status} onChange={(e) => updateIdea(idea.id, { status: e.target.value })} onClick={e=>e.stopPropagation()}><option>Watching</option><option>Waiting for Sweep</option><option>Confirmation Forming</option><option>Ready</option><option>Executed</option><option>Invalidated</option><option>Archived</option></select></span></div><em>{idea.objective || 'Objective not set'}</em><button className="tinyDelete" onClick={(e)=>{e.stopPropagation(); removeIdea(idea.id)}}>×</button></div>)}{ideas.length === 0 && <p className="emptyText">No trade ideas yet. Narrative first, button-smashing later.</p>}</div></div>;
}

function GraphSettings({ visuals, setVisuals, updateVisual, localSave, saveMapsToBackend, loadMapsFromBackend }: any) {
  const [activeLayer, setActiveLayer] = useState<LayerKey>('weekly');
  const v: VisualLayer = visuals[activeLayer];
  return <div className="card largeCard mapSettingsPage displaySettingsPage">
    <div className="cardHeader tight"><div><h3>Display Settings</h3><p>Visual controls only. Mapping stores structure; analytics derives sweeps, P2, OBs, mitigation and objectives later.</p></div><Settings className="goldIcon" size={22}/></div>
    <div className="structuralDoctrineCard"><b>Structure-only doctrine</b><span>Use Map Studio / Case Manager to save ranges, BOS up/down, active range changes and parent-child range links. Do not manually label sweep, phase, OB, profile or objective here. Apparently restraint is now a feature.</span></div>
    <div className="layerTabs">{LAYERS.map(l => <button className={activeLayer===l ? 'active' : ''} onClick={() => setActiveLayer(l)} key={l}>{l.toUpperCase()} DISPLAY</button>)}</div>

    <div className="settingsSectionTitle">Range display references</div>
    <div className="settingsGrid">
      <label>Display Range Low<input value={v.rangeLow} onChange={e=>updateVisual(activeLayer,{rangeLow:e.target.value})}/></label>
      <label>Display Range High<input value={v.rangeHigh} onChange={e=>updateVisual(activeLayer,{rangeHigh:e.target.value})}/></label>
      <label>Tick Interval<select value={String(v.tickStep)} onChange={e=>updateVisual(activeLayer,{tickStep:Number(e.target.value)})}><option value="50">$50</option><option value="100">$100</option><option value="200">$200</option><option value="500">$500</option></select></label>
      <label className="settingsCheck"><input type="checkbox" checked={!!v.useLiveCurrent} onChange={e=>updateVisual(activeLayer,{useLiveCurrent:e.target.checked})}/> Current marker uses live price</label>
      <label>Projection Price<input value={v.projectionPrice || ''} onChange={e=>updateVisual(activeLayer,{projectionPrice:e.target.value})} placeholder="optional visual guide" /></label>
    </div>

    <div className="settingsSectionTitle">Visibility notes</div>
    <div className="settingsGrid">
      <label>Current Zone<select value={v.currentZone} onChange={e=>updateVisual(activeLayer,{currentZone:e.target.value})}>{ZONES.map(z=><option key={z}>{z}</option>)}</select></label>
      <label>Objective Zone<select value={v.objectiveZone} onChange={e=>updateVisual(activeLayer,{objectiveZone:e.target.value})}>{ZONES.map(z=><option key={z}>{z}</option>)}</select></label>
      <label>Broken External Ref<select value={v.brokenExternal || 'NONE'} onChange={e=>updateVisual(activeLayer,{brokenExternal:e.target.value as any})}><option value="NONE">Hide</option><option value="EXT_H">Show broken high guide</option><option value="EXT_L">Show broken low guide</option></select></label>
      <label>Broken Ref Price<input value={v.brokenExternalPrice || ''} onChange={e=>updateVisual(activeLayer,{brokenExternalPrice:e.target.value})} placeholder="visual guide only"/></label>
    </div>

    <div className="settingsActionRow"><button className="primaryBtn" onClick={() => { setVisuals(visuals); localSave?.(); }}>Save Local Display Draft</button><button onClick={saveMapsToBackend}>Save Display To Backend</button><button onClick={loadMapsFromBackend}>Load Display From Backend</button><span>These settings are visual helpers. Structural truth is saved through range/event mapping, because the chart is not a confession booth.</span></div>
    <XYTrajectoryPanel title={`${activeLayer.toUpperCase()} Display Preview`} layerKey={activeLayer} visual={v} updateVisual={updateVisual} accent={activeLayer==='weekly'?'gold':activeLayer==='daily'?'blue':'cyan'} livePrice={null}/>
    <div className="jsonPreview"><b>Display payload only</b><pre>{JSON.stringify({ layer: activeLayer, rangeLow: v.rangeLow, rangeHigh: v.rangeHigh, tickStep: v.tickStep, currentZone: v.currentZone, objectiveZone: v.objectiveZone }, null, 2)}</pre></div>
  </div>;
}

function narrativeOptions(){return ['Bullish From External Low','Bullish From Deep Discount','Bullish From Discount','Bearish From External High','Bearish From Deep Premium','Bearish From Premium','Manual / Custom'].map(x=><option key={x}>{x}</option>)}
function applyNarrative(narrative: string, v: VisualLayer): Partial<VisualLayer> {
  const patch: Partial<VisualLayer> = { narrative };
  if (narrative.toLowerCase().startsWith('bullish')) patch.mapBias = 'bullish';
  if (narrative.toLowerCase().startsWith('bearish')) patch.mapBias = 'bearish';
  if (narrative.includes('External Low')) patch.currentZone = v.currentZone || 'D';
  if (narrative.includes('External High')) patch.currentZone = v.currentZone || 'P';
  if (narrative.includes('Deep Premium')) patch.objectiveZone = v.objectiveZone || 'DD';
  if (narrative.includes('Deep Discount')) patch.objectiveZone = v.objectiveZone || 'DP';
  if (narrative === 'Manual / Custom') patch.mapBias = 'manual';
  return patch;
}

function mitOptions(){return ['Fresh','M1','M2','Mitigated','Failed'].map(x=><option key={x}>{x}</option>)}
function MitigationLevelEditor({ value, onChange }: { value?: MitigationLevels; onChange: (v: MitigationLevels) => void }) {
  const levels = normalizeMitigationLevels(value);
  const setCell = (zone: 'discount'|'fair_price'|'premium', level: 'm1'|'m2'|'m3', key: 'price'|'status', val: string) => {
    onChange({ ...levels, [zone]: { ...levels[zone], [level]: { ...levels[zone][level], [key]: val } } });
  };
  const zones: Array<['discount'|'fair_price'|'premium', string]> = [['discount','Discount'], ['fair_price','Fair Price'], ['premium','Premium']];
  return <div className="mitigationMatrix">
    {zones.map(([zone,label]) => <div className="mitigationZone" key={zone}><h4>{label}</h4>{(['m1','m2','m3'] as const).map(level => <div className="mLevelRow" key={`${zone}_${level}`}><b>{level.toUpperCase()}</b><input placeholder="price" value={levels[zone][level].price} onChange={e=>setCell(zone, level, 'price', e.target.value)} /><select value={levels[zone][level].status} onChange={e=>setCell(zone, level, 'status', e.target.value)}>{['WAITING','FRESH','MITIGATED','HELD','FAILED','USED'].map(x=><option key={x}>{x}</option>)}</select></div>)}</div>)}
  </div>;
}
function MitigationSequenceEditor({ value, onChange }: { value?: string[]; onChange: (v: string[]) => void }) {
  const seq = Array.isArray(value) ? value : [];
  const set = (i:number, val:string) => { const next = [...seq]; next[i] = val; onChange(next.filter((_,idx)=>idx < 5)); };
  return <div className="sequenceRow">{[0,1,2,3,4].map(i=><label key={i}>Step {i+1}<select value={seq[i] || ''} onChange={e=>set(i,e.target.value)}><option value="">-</option>{[...MITIGATION_TARGETS,'NEW_BOS_UP','NEW_BOS_DOWN','PROFILE_FLIP','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label>)}</div>;
}


function HistoricalLifecycleBuilder({ symbol, visuals }: { symbol: string; visuals: VisualStore }) {
  const today = new Date().toISOString().slice(0,10);
  const [form, setForm] = useState<any>({
    symbol,
    friendly_name: `${symbol} | Historical lifecycle`,
    mode: 'HTF_ONLY',
    date_start: today,
    date_end: '',
    weekly_start: today,
    weekly_end: '',
    daily_start: today,
    daily_end: '',
    intraday_start: today,
    intraday_end: today,
    outcome_label: '',
    fair_price_reached: false,
    premium_reached: false,
    discount_reached: false,
    external_reached: false,
    notes: '',
  });
  const [result, setResult] = useState<any>(null);
  const [resolved, setResolved] = useState<any>(null);
  const update = (k:string,v:any)=>setForm((x:any)=>({...x,[k]:v}));
  useEffect(()=>setForm((x:any)=>({...x,symbol})),[symbol]);
  const layerPayload = (layer: LayerKey, start: string, end: string) => ({
    date_start: start,
    date_end: end,
    visual: visuals[layer],
    state: journalReadyMap(layer, visuals[layer]),
    meta: journalReadyMap(layer, visuals[layer]),
    range_low: visuals[layer].rangeLow,
    range_high: visuals[layer].rangeHigh,
  });
  const payload = () => ({
    symbol: form.symbol,
    friendly_name: form.friendly_name,
    mode: form.mode,
    date_start: form.date_start,
    date_end: form.date_end,
    weekly: layerPayload('weekly', form.weekly_start || form.date_start, form.weekly_end || form.date_end),
    daily: layerPayload('daily', form.daily_start || form.date_start, form.daily_end || form.date_end),
    intraday: form.mode === 'FULL' ? layerPayload('intraday', form.intraday_start || form.date_start, form.intraday_end || form.intraday_start || form.date_start) : {},
    outcome: {
      outcome_label: form.outcome_label,
      fair_price_reached: !!form.fair_price_reached,
      premium_reached: !!form.premium_reached,
      discount_reached: !!form.discount_reached,
      external_reached: !!form.external_reached,
    },
    notes: form.notes,
    updated_from_device: 'electron_historical_builder',
  });
  const save = async()=>{
    const r = await fetch(`${BASE_URL}/api/v1/historical/lifecycle-bundle`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())}).then(x=>x.json());
    setResult(r);
  };
  const resolve = async()=>{
    const d = form.intraday_start || form.daily_start || form.date_start;
    const r = await fetch(`${BASE_URL}/api/v1/historical/resolve-context?symbol=${encodeURIComponent(form.symbol)}&sample_date=${encodeURIComponent(d)}`).then(x=>x.json());
    setResolved(r);
  };
  return <div className="card largeCard journalClean">
    <div className="cardHeader tight"><div><h3>Historical Lifecycle Builder</h3><p>Save one linked lifecycle by date. Weekly/Daily first, Intraday only for recent/current regimes. No ID memorisation, because we are not database monks.</p></div><BookOpen className="goldIcon" size={22}/></div>
    <div className="dataSteps"><div><b>1</b><span>Pick symbol + period</span></div><div><b>2</b><span>Choose HTF or FULL</span></div><div><b>3</b><span>Use current maps</span></div><div><b>4</b><span>Save bundle</span></div><div><b>5</b><span>Future intraday auto-links by date</span></div></div>
    <div className="scenarioForm">
      <label>Lifecycle Label<input value={form.friendly_name} onChange={e=>update('friendly_name', e.target.value)} /></label>
      <label>Symbol<select value={form.symbol} onChange={e=>update('symbol', e.target.value)}>{SYMBOLS.map(x=><option key={x}>{x}</option>)}</select></label>
      <label>Mode<select value={form.mode} onChange={e=>update('mode', e.target.value)}><option value="HTF_ONLY">HTF ONLY — Weekly + Daily</option><option value="FULL">FULL — Weekly + Daily + Intraday</option></select></label>
      <label>Bundle Start<input type="date" value={form.date_start} onChange={e=>update('date_start', e.target.value)} /></label>
      <label>Bundle End<input type="date" value={form.date_end} onChange={e=>update('date_end', e.target.value)} /></label>
      <label>Weekly Start<input type="date" value={form.weekly_start} onChange={e=>update('weekly_start', e.target.value)} /></label>
      <label>Weekly End<input type="date" value={form.weekly_end} onChange={e=>update('weekly_end', e.target.value)} /></label>
      <label>Daily Start<input type="date" value={form.daily_start} onChange={e=>update('daily_start', e.target.value)} /></label>
      <label>Daily End<input type="date" value={form.daily_end} onChange={e=>update('daily_end', e.target.value)} /></label>
      {form.mode === 'FULL' && <><label>Intraday Date<input type="date" value={form.intraday_start} onChange={e=>update('intraday_start', e.target.value)} /></label><label>Intraday End<input type="date" value={form.intraday_end} onChange={e=>update('intraday_end', e.target.value)} /></label></>}
      <label>Outcome Label<input value={form.outcome_label} onChange={e=>update('outcome_label', e.target.value)} placeholder="Reached Fair Price / Profile Flip / Failed at Discount" /></label>
      <label className="checkboxLine"><input type="checkbox" checked={form.fair_price_reached} onChange={e=>update('fair_price_reached', e.target.checked)} /> Fair price reached</label>
      <label className="checkboxLine"><input type="checkbox" checked={form.premium_reached} onChange={e=>update('premium_reached', e.target.checked)} /> Premium reached</label>
      <label className="checkboxLine"><input type="checkbox" checked={form.discount_reached} onChange={e=>update('discount_reached', e.target.checked)} /> Discount reached</label>
      <label className="checkboxLine"><input type="checkbox" checked={form.external_reached} onChange={e=>update('external_reached', e.target.checked)} /> External reached</label>
      <label className="wide">Notes<textarea value={form.notes} onChange={e=>update('notes', e.target.value)} placeholder="What did the range do? What did the machine need to remember?" /></label>
    </div>
    <div className="buttonRow"><button className="primaryBtn" onClick={save}>Save Historical Lifecycle Bundle</button><button onClick={resolve}>Resolve Parent Context By Date</button></div>
    <div className="splitGrid journalSplit">
      <div className="miniPanel"><h4>Current Map Snapshot Used</h4><InfoLine label="Weekly" value={`${visuals.weekly.rangeLow || '-'} → ${visuals.weekly.rangeHigh || '-'}`} /><InfoLine label="Daily" value={`${visuals.daily.rangeLow || '-'} → ${visuals.daily.rangeHigh || '-'}`} /><InfoLine label="Intraday" value={form.mode === 'FULL' ? `${visuals.intraday.rangeLow || '-'} → ${visuals.intraday.rangeHigh || '-'}` : 'Skipped in HTF ONLY'} /></div>
      <div className="miniPanel"><h4>Backend Result</h4>{!result && !resolved && <p className="emptyText">Save or resolve context to see backend response.</p>}{result && <><InfoLine label="Saved" value={result.ok ? 'YES' : 'NO'} /><InfoLine label="Bundle ID" value={result.id || '-'} /><InfoLine label="Ranges" value={result.context_ranges?.length ?? 0} /><p className="machineText">{result.error || result.friendly_name || result.message || ''}</p></>}{resolved && <><InfoLine label="Resolve Date" value={resolved.sample_date || '-'} /><InfoLine label="Weekly Match" value={resolved.matched?.weekly?.friendly_name || 'None'} /><InfoLine label="Daily Match" value={resolved.matched?.daily?.friendly_name || 'None'} /><InfoLine label="Intraday Match" value={resolved.matched?.intraday?.friendly_name || 'None'} /></>}</div>
    </div>
  </div>;
}

function JournalPreview({ rows }: any) { return <div className="card"><div className="cardHeader tight"><div><h3>Journal Preview</h3><p>Recent SQL trades</p></div><BookOpen className="blueIcon" size={20}/></div>{rows.length === 0 && <p className="emptyText">No SQL trades logged yet.</p>}{rows.slice(0,5).map((r: any, i: number) => <div className="journalItem" key={i}><b>{r.symbol || 'XAUUSD'} {r.direction || ''}</b><span>{r.status || 'OPENED'} • {r.risk_percent ?? '-'}%</span></div>)}</div>; }
function JournalPage({ rows, summary, structured, detailed }: any) {
  const metrics = summary?.metrics || {};
  const counts = summary?.counts || {};
  const lifecycle = structured?.lifecycle || [];
  const ideas = structured?.ideas || [];
  const maps = structured?.maps || [];
  const scenarios = structured?.scenario_tests || [];
  const richTrades = detailed?.trades || [];
  const [tab, setTab] = useState<'trades'|'ideas'|'scenarios'|'lifecycle'|'maps'>('trades');
  const [selected, setSelected] = useState<any>(richTrades[0] || null);
  const [edit, setEdit] = useState<any>(richTrades[0] || {});
  const [saveState, setSaveState] = useState('');
  useEffect(()=>{ if (!selected && richTrades[0]) { setSelected(richTrades[0]); setEdit(richTrades[0]); } }, [richTrades.length]);
  const pick = (r:any) => { setSelected(r); setEdit({...r}); setSaveState(''); };
  const setField = (k:string, v:any) => setEdit((x:any)=>({ ...x, [k]: v }));
  const saveTrade = async () => {
    if (!edit?.id && !selected?.id) return;
    setSaveState('Saving...');
    const id = edit.id || selected.id;
    const payload = { id, symbol: edit.symbol || selected.symbol || 'XAUUSD', fields: edit };
    const r = await fetch(`${BASE_URL}/api/v1/journal/trade/update`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(x=>x.json()).catch(e=>({ok:false,error:e.message}));
    setSaveState(r.ok ? 'Saved to SQL memory' : `Save failed: ${r.error || 'unknown'}`);
  };
  return <div className="card largeCard journalClean"><div className="cardHeader tight"><div><h3>Journal Command Centre</h3><p>Clean trade memory, lifecycle snapshots and scenario stress tests. Less JSON swamp, more usable truth.</p></div><BookOpen className="blueIcon" size={22}/></div>
    <div className="kpiGrid"><Kpi label="Trades" value={metrics.total_trades ?? rows.length ?? 0}/><Kpi label="Trade Memory" value={counts.trade_memory_records ?? richTrades.length ?? 0}/><Kpi label="Maps" value={counts.map_states ?? maps.length ?? 0}/><Kpi label="Lifecycle" value={counts.lifecycle_snapshots ?? lifecycle.length ?? 0}/><Kpi label="Data Score" value={`${metrics.data_readiness_score ?? 0}%`}/></div>
    <div className="journalTabs">
      {[
        ['trades','Trade History'],['ideas','Idea History'],['scenarios','Scenario Tests'],['lifecycle','Lifecycle'],['maps','Map Saves']
      ].map(([k,l])=><button key={k} className={tab===k?'active':''} onClick={()=>setTab(k as any)}>{l}</button>)}
    </div>
    {tab === 'trades' && <div className="splitGrid journalSplit"><div className="miniPanel"><h4>Trade History</h4>{richTrades.length===0 && <p className="emptyText">No rich trade memory yet. Execute or create quick ideas after maps/lifecycle are saved.</p>}{richTrades.slice(0,30).map((r:any)=><button className={`tradeMemoryRow ${selected?.id===r.id?'picked':''}`} key={String(r.id)} onClick={()=>pick(r)}><b>{String(r.created_at || '').slice(0,16)} • {r.symbol} {r.direction || ''}</b><span>{r.status || r.lifecycle_state || '-'} • Risk {r.risk_percent ?? '-'}% • {r.daily_bias || '-'} → {r.daily_objective_1 || '-'}</span><em>{r.intraday_state || '-'} • {r.favourable_trade || '-'} • TP {r.tp1_hit?'1':''}{r.tp2_hit?'2':''}{r.tp3_hit?'3':'' || '-'}</em></button>)}</div>
      <div className="miniPanel"><h4>Selected Trade Detail + Edit</h4>{!edit?.id && <p className="emptyText">Select a trade to inspect and fill missing fields.</p>}{edit?.id && <div className="editTradeForm">
        <label>Date / Time<input value={edit.created_at || ''} onChange={e=>setField('created_at', e.target.value)} /></label>
        <label>Session<select value={edit.session || ''} onChange={e=>setField('session', e.target.value)}>{['','ASIA','LONDON','NEW_YORK','POST_NY','SWING'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Direction<select value={edit.direction || ''} onChange={e=>setField('direction', e.target.value)}>{['','BUY','SELL'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Status<select value={edit.status || ''} onChange={e=>setField('status', e.target.value)}>{['OPENED','TP1_HIT','TP2_HIT','RUNNER_ACTIVE','CLOSED','STOPPED_OUT','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Risk %<input value={edit.risk_percent ?? ''} onChange={e=>setField('risk_percent', e.target.value)} /></label>
        <label>Entry<input value={edit.entry_price ?? ''} onChange={e=>setField('entry_price', e.target.value)} /></label>
        <label>SL<input value={edit.sl_price ?? ''} onChange={e=>setField('sl_price', e.target.value)} /></label>
        <label>Weekly Bias<select value={edit.weekly_bias || ''} onChange={e=>setField('weekly_bias', e.target.value)}>{['','BULLISH','BEARISH','WATCHING'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Weekly State<input value={edit.weekly_state || ''} onChange={e=>setField('weekly_state', e.target.value)} /></label>
        <label>Daily Bias<select value={edit.daily_bias || ''} onChange={e=>setField('daily_bias', e.target.value)}>{['','BULLISH','BEARISH','WATCHING'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Profile<select value={edit.daily_profile || ''} onChange={e=>setField('daily_profile', e.target.value)}>{['',...DAILY_PROFILES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Position %<input value={edit.daily_position_pct ?? ''} onChange={e=>setField('daily_position_pct', e.target.value)} /></label>
        <label>Daily Objective 1<select value={edit.daily_objective_1 || ''} onChange={e=>setField('daily_objective_1', e.target.value)}>{['',...OBJECTIVE_TYPES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Objective 2<select value={edit.daily_objective_2 || ''} onChange={e=>setField('daily_objective_2', e.target.value)}>{['',...OBJECTIVE_TYPES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Objective 3<select value={edit.daily_objective_3 || ''} onChange={e=>setField('daily_objective_3', e.target.value)}>{['',...OBJECTIVE_TYPES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Intraday State<input value={edit.intraday_state || ''} onChange={e=>setField('intraday_state', e.target.value)} /></label>
        <label>Favourable Trade<select value={edit.favourable_trade || ''} onChange={e=>setField('favourable_trade', e.target.value)}>{['','NO_FAVOURABLE_TRADE','P1_CONTINUATION','P2_CONTINUATION','P3_FAILURE_REVERSAL','NEW_P1_PROFILE_FLIP'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Retest Status<select value={edit.retest_status || ''} onChange={e=>setField('retest_status', e.target.value)}>{['','WAITING','RETEST_PENDING','RETEST_ACTIVE','RETEST_COMPLETE','RETEST_FAILED'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Micro Confirmation<select value={edit.micro_confirmation || ''} onChange={e=>setField('micro_confirmation', e.target.value)}>{['','WAITING','CONFIRMED','REF_CANDLE_CONFIRMED','INVALID'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>TP1<select value={edit.tp1_hit ? '1':'0'} onChange={e=>setField('tp1_hit', e.target.value === '1')}>{['0','1'].map(x=><option key={x} value={x}>{x==='1'?'HIT':'-'}</option>)}</select></label>
        <label>TP2<select value={edit.tp2_hit ? '1':'0'} onChange={e=>setField('tp2_hit', e.target.value === '1')}>{['0','1'].map(x=><option key={x} value={x}>{x==='1'?'HIT':'-'}</option>)}</select></label>
        <label>TP3<select value={edit.tp3_hit ? '1':'0'} onChange={e=>setField('tp3_hit', e.target.value === '1')}>{['0','1'].map(x=><option key={x} value={x}>{x==='1'?'HIT':'-'}</option>)}</select></label>
        <label>MFE R<input value={edit.mfe_r ?? ''} onChange={e=>setField('mfe_r', e.target.value)} /></label>
        <label>MAE R<input value={edit.mae_r ?? ''} onChange={e=>setField('mae_r', e.target.value)} /></label>
        <label>Final R<input value={edit.final_r ?? ''} onChange={e=>setField('final_r', e.target.value)} /></label>
        <label className="wide">Machine Message<textarea value={edit.machine_message || ''} onChange={e=>setField('machine_message', e.target.value)} /></label>
        <button className="primaryBtn solo" onClick={saveTrade}>Save Trade Memory</button>{saveState && <p className="saveNote">{saveState}</p>}
      </div>}</div></div>}
    {tab === 'ideas' && <div className="cleanList">{ideas.length===0 ? <p className="emptyText">No structured ideas saved yet.</p> : ideas.map((r:any)=><div className="journalItem" key={r.id}><b>{r.created_at} • {r.symbol} {r.direction || ''}</b><span>{r.lifecycle_state || 'WATCHING'} • {r.setup_type || '-'} • Risk {r.risk_percent ?? '-'}% • Objective {r.objective || '-'}</span></div>)}</div>}
    {tab === 'scenarios' && <div className="cleanList"><p className="emptyText">Run new scenario tests from Data Collection. History appears here.</p>{scenarios.length===0 ? <p className="emptyText">No scenario tests yet.</p> : scenarios.map((r:any)=><div className="journalItem" key={r.id}><b>{r.scenario_name || 'Scenario'} {r.pass_flag === 1 ? '✅' : r.pass_flag === 0 ? '⚠️' : ''}</b><span>{r.created_at} • Expected {r.expected_status || '-'} → Actual {r.actual_status || '-'}</span></div>)}</div>}
    {tab === 'lifecycle' && <div className="cleanList">{lifecycle.length===0 ? <p className="emptyText">No lifecycle snapshots saved yet.</p> : lifecycle.map((r:any)=><div className="journalItem" key={r.id}><b>{r.symbol} lifecycle v{r.snapshot_version}</b><span>{r.created_at} • Daily {r.daily?.daily_state || r.daily?.daily_profile || '-'} • Intraday {r.intraday?.intraday_state || r.intraday?.phase_state || '-'}</span></div>)}</div>}
    {tab === 'maps' && <div className="cleanList">{maps.length===0 ? <p className="emptyText">No map saves yet. Save maps from Map Settings.</p> : maps.map((r:any)=><div className="journalItem" key={r.id}><b>{r.symbol} map v{r.state_version}</b><span>{r.updated_at || r.created_at} • {r.source || 'unknown'}</span></div>)}</div>}
  </div>;
}
function InfoLine({label,value}:any){return <div className="infoLine"><span>{label}</span><b>{String(value ?? '-')}</b></div>}
function Kpi({label,value}:any){return <div className="kpiCard"><span>{label}</span><b>{String(value)}</b></div>}
function SqlPage({ status, journal, summary, structured }: any) { return <div className="card largeCard"><h3>SQL Status</h3><pre className="jsonBox">{JSON.stringify({ status, journalSummary: summary, structuredRecent: structured, recentCount: journal?.length || 0 }, null, 2)}</pre></div>; }
function getStructuralMetrics(layer: LayerKey, path: GraphPoint[], low: number, high: number, hasRange: boolean, currentPoint: GraphPoint | undefined, visual: VisualLayer) {
  const out: string[] = [];
  const priceOf = (key: string) => { const p = path.find(x => String(x.anchorKey || x.label || '').toUpperCase() === key); const n = parseNum(p?.price); return Number.isFinite(n) ? n : null; };
  if (layer === 'intraday') {
    const ch = priceOf('CHOCH_HIGH'), cl = priceOf('CHOCH_LOW'), cb = priceOf('CHOCH_BREAK');
    if (ch != null && cl != null) out.push(`CHOCH Δ ${Math.abs(ch - cl).toFixed(2)} pts`);
    if (ch != null && cl != null && cb != null && ch !== cl) out.push(`Break ${(Math.abs(cb - cl) / Math.abs(ch - cl) * 100).toFixed(0)}% of CHOCH range`);
  }
  if (hasRange) {
    const cp = parseNum(currentPoint?.price);
    if (Number.isFinite(cp)) {
      const pct = ((cp - low) / Math.max(1e-9, high - low)) * 100;
      out.push(`Current ${pct.toFixed(1)}% of range`);
    }
    const objPrice = priceForZone(visual.objectiveZone, low, high);
    const cur = parseNum(currentPoint?.price);
    if (Number.isFinite(cur) && Number.isFinite(objPrice)) out.push(`Objective distance ${Math.abs(objPrice - cur).toFixed(2)} pts`);
  }
  return out.slice(0, 3);
}
function fmtPct(v:any){ const n = parseNum(v); return Number.isFinite(n) ? `${n.toFixed(2)}%` : '-'; }
function fmtPctOrDash(v:any){ const n = parseNum(v); return Number.isFinite(n) ? `${n.toFixed(2)}%` : 'Map range required'; }
function Metric({ label, value, color = '#e5e7eb' }: any) { return <div className="metric"><span>{label}</span><b style={{ color }}>{String(value)}</b></div>; }
function Mini({ label, value, highlight }: any) { return <div className="mini"><span>{label}</span><b className={highlight ? 'goldText' : ''}>{value}</b></div>; }
function Pill({ label, value }: any) { return <div className="pill"><span>{label}</span><b>{value}</b></div>; }
function Check({ label, active }: any) { return <div className={`check ${active ? 'on' : ''}`}><CheckCircle2 size={15}/>{label}</div>; }
function truthy(v: any) { return v === true || v === 'true' || v === 1 || v === '1' || v === 'YES'; }
function clamp(n: number, min: number, max: number) { return Math.max(min, Math.min(max, Number.isFinite(n) ? n : 50)); }
function parseNum(v:any){ return parseFloat(String(v ?? '').replace(',', '.')); }
function extractLivePrice(state: any, active: any): number | null { const candidates = [active?.raw_status?.current_price, active?.current_price, state?.price?.bid, state?.price?.last, state?.live_price, state?.current_price]; for (const c of candidates) { const n = parseNum(c); if (Number.isFinite(n) && n > 0) return n; } return null; }
function getExtFlow(mapBias: any, narrative: any): 'bullish' | 'bearish' | 'manual' {
  const b = String(mapBias || '').toLowerCase();
  const n = String(narrative || '').toLowerCase();
  if (b.includes('bear') || n.includes('bear') || n.includes('bos up')) return 'bearish';
  if (b.includes('bull') || n.includes('bull') || n.includes('bos down')) return 'bullish';
  return 'manual';
}
function yForPrice(price: number, low: number, high: number) { if (!Number.isFinite(price) || high <= low) return 50; return clamp(92 - ((price - low) / (high - low)) * 84, 6, 94); }
function priceFromY(y: number, low: number, high: number) { return low + ((92 - y) / 84) * (high - low); }
function priceForZone(z: any, low: number, high: number) { const pct = zoneToRangePct(z); return low + (pct / 100) * (high - low); }
function zoneToRangePct(z: any) { const s = String(z || '').toLowerCase(); if (s.includes('ext l') || s.includes('external low')) return 0; if (s === 'dd' || s.includes('deep discount')) return 14; if (s === 'd' || s.includes('discount')) return 32; if (s.includes('fair')) return 50; if (s === 'p' || s.includes('premium')) return 68; if (s === 'dp' || s.includes('deep premium')) return 86; if (s.includes('ext h') || s.includes('external high')) return 100; return 50; }
function zoneFromY(y: number) { if (y < 15) return 'Ext H'; if (y < 29) return 'DP'; if (y < 43) return 'P'; if (y < 57) return 'Fair'; if (y < 71) return 'D'; if (y < 85) return 'DD'; return 'Ext L'; }
function buildPriceTicks(low: number, high: number, step = 200) { const out: { price: number; y: number }[] = []; const start = Math.ceil(low / step) * step; let lastY = -999; for (let p = start; p <= high; p += step) { const y = yForPrice(p, low, high); if (Math.abs(y - lastY) >= 12) { out.push({ price: p, y }); lastY = y; } } return out; }
function yForZone(z: any) { const s = String(z || '').toLowerCase(); if (s.includes('ext h') || s.includes('external high')) return 8; if (s === 'dp' || s.includes('deep premium')) return 22; if (s === 'p' || s.includes('premium')) return 35; if (s.includes('fair')) return 50; if (s === 'd' || s.includes('discount')) return 65; if (s === 'dd' || s.includes('deep discount')) return 78; if (s.includes('ext l') || s.includes('external low')) return 92; return 50; }
function cryptoId(){ try { return crypto.randomUUID(); } catch { return `p_${Date.now()}_${Math.random().toString(16).slice(2)}`; } }

function normalizeMitigationLevels(raw: any): MitigationLevels {
  const base = emptyMitigationLevels();
  const src = raw || {};
  (['discount','fair_price','premium'] as const).forEach(zone => {
    const zd = src?.[zone] || src?.[zone.toUpperCase()] || src?.[zone.replace('_','')] || {};
    (['m1','m2','m3'] as const).forEach(level => {
      const val = zd?.[level] || zd?.[level.toUpperCase()] || {};
      base[zone][level] = typeof val === 'object' ? { price: val.price ?? '', status: val.status ?? 'WAITING', role: val.role ?? '' } : { price: String(val || ''), status: 'WAITING' };
    });
  });
  return base;
}

function normalizeVisuals(raw: any): VisualStore { const out: any = {}; for (const k of LAYERS) { const base = defaultVisual[k]; const v = raw?.[k] || base; out[k] = { ...base, ...v, narrative: v.narrative || base.narrative || '', mapBias: v.mapBias || base.mapBias || 'manual', meta: { ...(base.meta || {}), ...(v.meta || {}) }, brokenExternal: v.brokenExternal || base.brokenExternal || 'NONE', brokenExternalPrice: v.brokenExternalPrice || base.brokenExternalPrice || '', useLiveCurrent: Boolean(v.useLiveCurrent ?? base.useLiveCurrent ?? false), projectionX: Number(v.projectionX ?? base.projectionX ?? 90), projectionPrice: v.projectionPrice || base.projectionPrice || '', liquidityCleanUpPrice: v.liquidityCleanUpPrice ?? base.liquidityCleanUpPrice ?? '', showLiquidityCleanUp: Boolean(v.showLiquidityCleanUp ?? base.showLiquidityCleanUp ?? false), mitigation: { ...base.mitigation, ...(v.mitigation || {}) }, mitigationLevels: normalizeMitigationLevels(v.mitigationLevels || v.mitigation_levels || base.mitigationLevels), mitigationSequence: Array.isArray(v.mitigationSequence || v.mitigation_sequence) ? (v.mitigationSequence || v.mitigation_sequence) : [], path: (v.path || base.path).map((p: any, idx: number) => ({ id: p.id || cryptoId(), label: p.label || p.anchorKey || '', anchorKey: p.anchorKey || p.label || '', status: p.status || 'INTACT', role: p.role || '', sequenceColumn: Number(p.sequenceColumn ?? idx + 1), zone: p.zone || 'Fair', x: Number(p.x ?? 50), price: p.price || '', live: Boolean(p.live) })) }; } return out; }

const rootEl = document.getElementById('root')!;
const fxRoot = window as Window & { __FX_TM_ROOT__?: ReturnType<typeof createRoot> };
if (!fxRoot.__FX_TM_ROOT__) fxRoot.__FX_TM_ROOT__ = createRoot(rootEl);
fxRoot.__FX_TM_ROOT__.render(<App />);
