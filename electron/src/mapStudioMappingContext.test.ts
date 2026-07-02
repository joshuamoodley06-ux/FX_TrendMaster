import { describe, expect, it } from 'vitest';
import {
  allowsBoundaryCorrectionForParentBlock,
  buildDiscardStructuralDraftPlan,
  buildSkeletonMappingStatusLine,
  evaluateChildMappingParentBlockReason,
  evaluateChildStructuralRangeConfirm,
  evaluateDraftNavConfirmAction,
  evaluateRangeDraftSynced,
  evaluateStructureScopeTimeframeBlockReason,
  evaluateStructuralBosBlockReason,
  evaluateStructuralNavigationGuard,
  evaluateUnsavedResponsibleChildDraft,
  hasMappingSkeletonContext,
  hasUnsavedStructuralDraft,
  isChartTimeframeAllowedForStructureLayer,
  layersForDeletedRangeIds,
  parentContainsChildByLifecycle,
  purgeStructuralAnchorsByLayer,
  resolveStructuralCommitParentId,
  shouldRetainChildMappingLock,
  shouldSuppressAutoParentRewrite,
  shouldSuppressDraftRangeOverlay,
  structureLayerRangeConfirmLabel,
  structureLayerRangeConfirmNextLabel,
} from './mapStudioMappingContext';

const priceMatches = (a: number, b: number) => Math.abs(a - b) < 0.005;
const isBroken = (status: string | null | undefined) => String(status || '').toUpperCase() === 'BROKEN';

describe('mapStudioMappingContext', () => {
  it('requires case plus hierarchy/campaign context', () => {
    expect(hasMappingSkeletonContext({
      hasCase: false,
      activeStructuralRangeId: '1',
      selectedParentRangeId: '',
      guidedCursorActive: false,
      childMappingSessionActive: false,
    })).toBe(false);
    expect(hasMappingSkeletonContext({
      hasCase: true,
      activeStructuralRangeId: '',
      selectedParentRangeId: '394',
      guidedCursorActive: false,
      childMappingSessionActive: false,
    })).toBe(true);
  });

  it('builds candle-first status line', () => {
    const line = buildSkeletonMappingStatusLine({
      selectedTimeLabel: '2024-11-14',
      timeframe: 'D1',
      structureLayer: 'DAILY',
      activeRangeId: '399',
      parentRangeId: '394',
      rhSet: true,
      rlSet: true,
      chainDraftMode: false,
      rangeSynced: true,
      lastMessage: '',
      structuralSaving: false,
    });
    expect(line).toContain('2024-11-14');
    expect(line).toContain('H = RH');
  });

  it('labels child and next range confirm actions', () => {
    expect(structureLayerRangeConfirmLabel('DAILY')).toBe('Confirm Daily Range');
    expect(structureLayerRangeConfirmNextLabel('DAILY')).toBe('Confirm Next Daily Range');
    expect(structureLayerRangeConfirmLabel('INTRADAY')).toBe('Confirm Intraday Range');
    expect(structureLayerRangeConfirmLabel('MICRO')).toBe('Confirm Micro Range');
    expect(structureLayerRangeConfirmNextLabel('INTRADAY')).toBe('Confirm Next Intraday Range');
    expect(structureLayerRangeConfirmNextLabel('MICRO')).toBe('Confirm Next Micro Range');
  });

  describe('layer-generic confirm eligibility', () => {
    it('requires child confirm for INTRADAY draft under DAILY parent', () => {
      const result = evaluateChildStructuralRangeConfirm({
        hasCase: true,
        structureLayer: 'INTRADAY',
        rhSet: true,
        rlSet: true,
        parentRangeId: '501',
        activeRangeId: '501',
        activeRangeLayer: 'DAILY',
        activeRangeBroken: false,
        rangeDraftSynced: false,
        structuralRangeDraftDirty: true,
        chainDraftMode: false,
        saveNextRangeEligible: false,
      });
      expect(result.eligible).toBe(true);
      expect(result.kind).toBe('child');
      expect(result.label).toBe('Confirm Intraday Range');
      expect(result.saveBlockHint).toBe('Confirm Intraday Range before BOS');
      expect(result.useSaveNextPath).toBe(false);
    });

    it('requires child confirm for MICRO draft under INTRADAY parent', () => {
      const result = evaluateChildStructuralRangeConfirm({
        hasCase: true,
        structureLayer: 'MICRO',
        rhSet: true,
        rlSet: true,
        parentRangeId: '601',
        activeRangeId: '601',
        activeRangeLayer: 'INTRADAY',
        activeRangeBroken: false,
        rangeDraftSynced: false,
        structuralRangeDraftDirty: true,
        chainDraftMode: false,
        saveNextRangeEligible: false,
      });
      expect(result.eligible).toBe(true);
      expect(result.kind).toBe('child');
      expect(result.label).toBe('Confirm Micro Range');
      expect(result.saveBlockHint).toBe('Confirm Micro Range before BOS');
      expect(result.useSaveNextPath).toBe(false);
    });

    it('uses next confirm for BROKEN INTRADAY same-layer continuation', () => {
      const result = evaluateChildStructuralRangeConfirm({
        hasCase: true,
        structureLayer: 'INTRADAY',
        rhSet: true,
        rlSet: true,
        parentRangeId: '501',
        activeRangeId: '510',
        activeRangeLayer: 'INTRADAY',
        activeRangeBroken: true,
        rangeDraftSynced: false,
        structuralRangeDraftDirty: true,
        chainDraftMode: true,
        saveNextRangeEligible: true,
      });
      expect(result.eligible).toBe(true);
      expect(result.kind).toBe('next');
      expect(result.label).toBe('Confirm Next Intraday Range');
      expect(result.saveBlockHint).toBe('Confirm next Intraday Range before BOS');
      expect(result.useSaveNextPath).toBe(true);
      expect(result.sameLayerChainContinuation).toBe(true);
    });

    it('uses next confirm for BROKEN MICRO same-layer continuation', () => {
      const result = evaluateChildStructuralRangeConfirm({
        hasCase: true,
        structureLayer: 'MICRO',
        rhSet: true,
        rlSet: true,
        parentRangeId: '601',
        activeRangeId: '610',
        activeRangeLayer: 'MICRO',
        activeRangeBroken: true,
        rangeDraftSynced: false,
        structuralRangeDraftDirty: true,
        chainDraftMode: true,
        saveNextRangeEligible: true,
      });
      expect(result.eligible).toBe(true);
      expect(result.kind).toBe('next');
      expect(result.label).toBe('Confirm Next Micro Range');
      expect(result.saveBlockHint).toBe('Confirm next Micro Range before BOS');
      expect(result.useSaveNextPath).toBe(true);
      expect(result.sameLayerChainContinuation).toBe(true);
    });
  });

  it('requires manual confirm for cross-layer child draft while chain draft blocks auto-save', () => {
    const result = evaluateChildStructuralRangeConfirm({
      hasCase: true,
      structureLayer: 'DAILY',
      rhSet: true,
      rlSet: true,
      parentRangeId: '433',
      activeRangeId: '433',
      activeRangeLayer: 'WEEKLY',
      activeRangeBroken: true,
      rangeDraftSynced: false,
      structuralRangeDraftDirty: true,
      chainDraftMode: true,
      saveNextRangeEligible: false,
    });
    expect(result.eligible).toBe(true);
    expect(result.kind).toBe('child');
    expect(result.label).toBe('Confirm Daily Range');
    expect(result.useSaveNextPath).toBe(false);
    expect(result.sameLayerChainContinuation).toBe(false);
  });

  it('excludes broken same-layer active from child confirm and uses next confirm instead', () => {
    const childAttempt = evaluateChildStructuralRangeConfirm({
      hasCase: true,
      structureLayer: 'DAILY',
      rhSet: true,
      rlSet: true,
      parentRangeId: '433',
      activeRangeId: '435',
      activeRangeLayer: 'DAILY',
      activeRangeBroken: true,
      rangeDraftSynced: false,
      structuralRangeDraftDirty: true,
      chainDraftMode: true,
      saveNextRangeEligible: true,
    });
    expect(childAttempt.kind).toBe('next');
    expect(childAttempt.eligible).toBe(true);
    expect(childAttempt.label).toBe('Confirm Next Daily Range');
    expect(childAttempt.useSaveNextPath).toBe(true);
    expect(childAttempt.sameLayerChainContinuation).toBe(true);
  });

  it('shows next confirm status before chain sync line', () => {
    const line = buildSkeletonMappingStatusLine({
      selectedTimeLabel: null,
      timeframe: 'D1',
      structureLayer: 'DAILY',
      activeRangeId: '435',
      parentRangeId: '433',
      rhSet: true,
      rlSet: true,
      chainDraftMode: true,
      childRangeConfirmNextPending: true,
      rangeSynced: false,
      lastMessage: '',
      structuralSaving: false,
    });
    expect(line).toContain('Confirm Next Daily Range before BOS');
    expect(line).not.toContain('syncing chain');
  });

  it('suppresses draft overlay when synced to saved non-broken range', () => {
    const suppressed = shouldSuppressDraftRangeOverlay({
      hasHigh: true,
      hasLow: true,
      structuralRangeDraftDirty: false,
      activeRangeLayer: 'DAILY',
      activeRangeBroken: false,
      structureLayer: 'DAILY',
      draftHigh: 2400,
      draftLow: 2300,
      savedHigh: 2400,
      savedLow: 2300,
      priceMatches: (a, b) => Math.abs(a - b) < 0.005,
    });
    expect(suppressed).toBe(true);

    const draftVisible = shouldSuppressDraftRangeOverlay({
      hasHigh: true,
      hasLow: true,
      structuralRangeDraftDirty: true,
      activeRangeLayer: 'DAILY',
      activeRangeBroken: false,
      structureLayer: 'DAILY',
      draftHigh: 2400,
      draftLow: 2300,
      savedHigh: 2400,
      savedLow: 2300,
      priceMatches: (a, b) => Math.abs(a - b) < 0.005,
    });
    expect(draftVisible).toBe(false);
  });

  it('orders BOS block reason with saved range before admitted candle', () => {
    expect(evaluateStructuralBosBlockReason({
      hasCase: true,
      structureLayer: 'DAILY',
      chartTimeframe: 'D1',
      resolvedRangeId: '',
      activeRangeBroken: false,
      needsRangeConfirm: true,
      candleFeedReady: true,
      admittedMappingCandle: false,
    })).toBe('Confirm next Daily Range before BOS');

    expect(evaluateStructuralBosBlockReason({
      hasCase: true,
      structureLayer: 'DAILY',
      chartTimeframe: 'D1',
      resolvedRangeId: '436',
      activeRangeBroken: false,
      needsRangeConfirm: false,
      candleFeedReady: true,
      admittedMappingCandle: false,
    })).toBe('Re-click visible D1 candle for BOS');
  });

  describe('draft lifecycle v2', () => {
    const priceMatches = (a: number, b: number) => Math.abs(a - b) < 0.005;

    it('blocks Weekly BOS when unsaved Daily child draft exists under parent', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'WEEKLY',
        parentRangeId: '433',
        childLayer: 'DAILY',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2400,
        childRlPrice: 2300,
        activeRangeLayer: 'WEEKLY',
        chainDraftMode: false,
        savedRanges: [],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(true);
      expect(childDraft.blockReason).toBe('Confirm responsible Daily Range before Weekly BOS');
      expect(childDraft.confirmLabel).toBe('Confirm responsible Daily Range');

      expect(evaluateStructuralBosBlockReason({
        hasCase: true,
        structureLayer: 'WEEKLY',
        chartTimeframe: 'W1',
        resolvedRangeId: '433',
        activeRangeBroken: false,
        needsRangeConfirm: false,
        responsibleChildDraftBlocked: childDraft.blocked,
        responsibleChildDraftReason: childDraft.blockReason,
        candleFeedReady: true,
        admittedMappingCandle: true,
      })).toBe('Confirm responsible Daily Range before Weekly BOS');
    });

    it('does not block parent BOS when matching saved child range exists', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'WEEKLY',
        parentRangeId: '433',
        childLayer: 'DAILY',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2400,
        childRlPrice: 2300,
        activeRangeLayer: 'WEEKLY',
        savedRanges: [{
          range_id: '434',
          structure_layer: 'DAILY',
          parent_range_id: '433',
          range_high_price: 2400,
          range_low_price: 2300,
          status: 'ACTIVE',
        }],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(false);

      expect(evaluateStructuralBosBlockReason({
        hasCase: true,
        structureLayer: 'WEEKLY',
        chartTimeframe: 'W1',
        resolvedRangeId: '433',
        activeRangeBroken: false,
        needsRangeConfirm: false,
        responsibleChildDraftBlocked: childDraft.blocked,
        responsibleChildDraftReason: childDraft.blockReason,
        candleFeedReady: true,
        admittedMappingCandle: true,
      })).toBeNull();
    });

    it('evaluates navigation guard for confirm, discard, cancel, and parent-only paths', () => {
      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: false,
        targetRangeId: '399',
        activeRangeId: '435',
        targetIsParentOnly: false,
        structuralRangeDraftDirty: false,
        confirmSaveEligible: false,
      })).toBe('proceed');

      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: true,
        targetRangeId: '435',
        activeRangeId: '435',
        targetIsParentOnly: false,
        structuralRangeDraftDirty: false,
        confirmSaveEligible: false,
      })).toBe('proceed');

      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: true,
        targetRangeId: '399',
        activeRangeId: '435',
        targetIsParentOnly: false,
        structuralRangeDraftDirty: true,
        confirmSaveEligible: false,
      })).toBe('prompt-save');

      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: true,
        targetRangeId: '399',
        activeRangeId: '435',
        targetIsParentOnly: false,
        structuralRangeDraftDirty: false,
        confirmSaveEligible: false,
      })).toBe('prompt-discard-only');

      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: true,
        targetRangeId: '433',
        activeRangeId: '435',
        targetIsParentOnly: true,
        structuralRangeDraftDirty: true,
        confirmSaveEligible: false,
      })).toBe('parent_context_only');
    });

    it('detects unsaved draft and builds discard plan for layer cache and chain draft', () => {
      expect(hasUnsavedStructuralDraft({
        rhSet: true,
        rlSet: true,
        structuralRangeDraftDirty: false,
        rangeDraftSynced: true,
        activeRangeId: '435',
      })).toBe(false);

      expect(hasUnsavedStructuralDraft({
        rhSet: true,
        rlSet: true,
        structuralRangeDraftDirty: false,
        rangeDraftSynced: false,
        activeRangeId: '',
      })).toBe(true);

      expect(hasUnsavedStructuralDraft({
        rhSet: false,
        rlSet: false,
        structuralRangeDraftDirty: true,
        rangeDraftSynced: false,
        activeRangeId: '',
      })).toBe(true);

      expect(hasUnsavedStructuralDraft({
        rhSet: false,
        rlSet: false,
        structuralRangeDraftDirty: false,
        rangeDraftSynced: false,
        activeRangeId: '',
      })).toBe(false);

      expect(buildDiscardStructuralDraftPlan({
        structureLayer: 'DAILY',
        chainDraftMode: true,
        chainDraftBelongsToDraftLayer: true,
      })).toEqual({
        clearRhRl: true,
        clearLayerCacheKey: 'DAILY',
        clearDraftDirty: true,
        clearChainDraftMode: true,
      });

      expect(buildDiscardStructuralDraftPlan({
        structureLayer: 'DAILY',
        chainDraftMode: true,
        chainDraftBelongsToDraftLayer: false,
      }).clearChainDraftMode).toBe(false);
    });

    it('prioritizes responsible child draft over next-range and admitted-candle BOS blocks', () => {
      expect(evaluateStructuralBosBlockReason({
        hasCase: true,
        structureLayer: 'WEEKLY',
        chartTimeframe: 'W1',
        resolvedRangeId: '',
        activeRangeBroken: true,
        needsRangeConfirm: true,
        responsibleChildDraftBlocked: true,
        responsibleChildDraftReason: 'Confirm responsible Daily Range before Weekly BOS',
        candleFeedReady: false,
        admittedMappingCandle: false,
      })).toBe('Confirm responsible Daily Range before Weekly BOS');
    });

    it('does not block Confirm Intraday Range child save workflow', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'DAILY',
        parentRangeId: '501',
        childLayer: 'INTRADAY',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2410,
        childRlPrice: 2405,
        activeRangeLayer: 'DAILY',
        childConfirmEligible: true,
        chainDraftMode: false,
        savedRanges: [],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(false);
    });

    it('does not block Confirm Next Intraday Range same-layer continuation', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'INTRADAY',
        parentRangeId: '601',
        childLayer: 'MICRO',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2408.5,
        childRlPrice: 2407.2,
        activeRangeLayer: 'INTRADAY',
        childNextConfirmEligible: true,
        chainDraftMode: true,
        savedRanges: [],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(false);
    });

    it('does not block normal child mapping under saved Daily without chain draft', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'DAILY',
        parentRangeId: '501',
        childLayer: 'INTRADAY',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2410,
        childRlPrice: 2405,
        activeRangeLayer: 'DAILY',
        chainDraftMode: false,
        savedRanges: [],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(false);
    });

    it('does not block when mapping on child layer under parent context', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'INTRADAY',
        parentRangeId: '501',
        childLayer: 'MICRO',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2410,
        childRlPrice: 2405,
        activeRangeLayer: 'DAILY',
        mappingOnChildLayer: false,
        chainDraftMode: false,
        savedRanges: [],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(false);
    });

    it('clears Weekly BOS block after responsible child is saved', () => {
      const childDraft = evaluateUnsavedResponsibleChildDraft({
        parentLayer: 'WEEKLY',
        parentRangeId: '433',
        childLayer: 'DAILY',
        childRhSet: true,
        childRlSet: true,
        childRhPrice: 2400,
        childRlPrice: 2300,
        activeRangeLayer: 'WEEKLY',
        savedRanges: [{
          range_id: '434',
          structure_layer: 'DAILY',
          parent_range_id: '433',
          range_high_price: 2400,
          range_low_price: 2300,
          status: 'ACTIVE',
        }],
        priceMatches,
      });
      expect(childDraft.blocked).toBe(false);
      expect(evaluateStructuralBosBlockReason({
        hasCase: true,
        structureLayer: 'WEEKLY',
        chartTimeframe: 'W1',
        resolvedRangeId: '433',
        activeRangeBroken: false,
        needsRangeConfirm: false,
        responsibleChildDraftBlocked: childDraft.blocked,
        responsibleChildDraftReason: childDraft.blockReason,
        candleFeedReady: true,
        admittedMappingCandle: true,
      })).toBeNull();
    });
  });

  describe('structure scope timeframe compatibility', () => {
    it('blocks H4 chart with MICRO layer', () => {
      const reason = evaluateStructureScopeTimeframeBlockReason('MICRO', 'M15', 'H4');
      expect(reason).toContain('H4 cannot be saved as Micro');
      expect(reason).toContain('Switch layer to Intraday');
      expect(reason).toMatch(/switch chart to M15 or M5/);
    });

    it('blocks H1 chart with MICRO layer', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('MICRO', 'M5', 'H1')).toContain('H1 cannot be saved as Micro');
    });

    it('allows M15 and M5 with MICRO layer', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('MICRO', 'M15', 'M15')).toBeNull();
      expect(evaluateStructureScopeTimeframeBlockReason('MICRO', 'M5', 'M5')).toBeNull();
    });

    it('allows H4 and H1 with INTRADAY layer', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('INTRADAY', 'H4', 'H4')).toBeNull();
      expect(evaluateStructureScopeTimeframeBlockReason('INTRADAY', 'H1', 'H1')).toBeNull();
      expect(isChartTimeframeAllowedForStructureLayer('H4', 'INTRADAY')).toBe(true);
    });

    it('allows D1 with DAILY and W1 with WEEKLY', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('DAILY', 'D1', 'D1')).toBeNull();
      expect(evaluateStructureScopeTimeframeBlockReason('WEEKLY', 'W1', 'W1')).toBeNull();
    });

    it('allows MN1 and W1 with MACRO layer', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('MACRO', 'MN1', 'MN1')).toBeNull();
      expect(evaluateStructureScopeTimeframeBlockReason('MACRO', 'W1', 'W1')).toBeNull();
    });

    it('blocks D1 chart with INTRADAY layer and M15 with DAILY', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('INTRADAY', 'H1', 'D1')).toContain('D1 cannot be saved as Intraday');
      expect(evaluateStructureScopeTimeframeBlockReason('DAILY', 'D1', 'M15')).toContain('M15 cannot be saved as Daily');
    });

    it('validates responsible child save layer against chart timeframe', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('DAILY', 'D1', 'H4')).toContain('H4 cannot be saved as Daily');
      expect(evaluateStructureScopeTimeframeBlockReason('INTRADAY', 'H4', 'H4')).toBeNull();
    });

    it('returns null when layer and chart timeframe are compatible regardless of H8 source', () => {
      expect(evaluateStructureScopeTimeframeBlockReason('INTRADAY', 'H8', 'H4')).toBeNull();
    });
  });

  describe('child mapping parent lock', () => {
    const daily434 = {
      range_id: '434',
      structure_layer: 'DAILY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      active_from_time: '2026-02-01T00:00:00.000Z',
      range_start_time: '2026-02-01T00:00:00.000Z',
      inactive_from_time: null,
    };
    const daily437 = {
      range_id: '437',
      structure_layer: 'DAILY',
      range_scope: 'MAJOR',
      status: 'ACTIVE',
      active_from_time: '2026-03-17T00:00:00.000Z',
      range_start_time: '2026-03-17T00:00:00.000Z',
      inactive_from_time: null,
    };
    const savedRanges = [daily434, daily437];

    it('locks parent id via resolveStructuralCommitParentId priority', () => {
      const locked = resolveStructuralCommitParentId({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '434',
        selectedParentRangeId: '437',
        autoResolvedParentId: '437',
        savedRanges,
      });
      expect(locked).toEqual({ parentId: '434', source: 'lock' });
    });

    it('uses selected parent when no lock and ignores auto latest substitution input', () => {
      const selected = resolveStructuralCommitParentId({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '',
        selectedParentRangeId: '434',
        autoResolvedParentId: '437',
        savedRanges,
      });
      expect(selected).toEqual({ parentId: '434', source: 'selected' });
    });

    it('allows safe auto-parent only when no lock exists', () => {
      const auto = resolveStructuralCommitParentId({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '',
        selectedParentRangeId: '',
        autoResolvedParentId: '434',
        savedRanges,
      });
      expect(auto).toEqual({ parentId: '434', source: 'auto' });
    });

    it('suppresses RH/RL auto-parent rewrite when lock exists', () => {
      expect(shouldSuppressAutoParentRewrite('434')).toBe(true);
      expect(shouldSuppressAutoParentRewrite('')).toBe(false);
    });

    it('blocks child window outside locked Daily parent before save', () => {
      const reason = evaluateChildMappingParentBlockReason({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '437',
        childSpan: {
          range_high_time: '2026-02-24T12:00:00.000Z',
          range_low_time: '2026-02-24T08:00:00.000Z',
        },
        savedRanges,
        resolvedParentId: '437',
        allowOrphanOverride: false,
      });
      expect(reason).toContain('Intraday window is not inside Daily #437');
      expect(reason).toContain('Select the correct Daily or move RH/RL');
      expect(allowsBoundaryCorrectionForParentBlock(reason)).toBe(true);
    });

    it('allows child window inside locked Daily parent', () => {
      const reason = evaluateChildMappingParentBlockReason({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '434',
        childSpan: {
          range_high_time: '2026-02-24T12:00:00.000Z',
          range_low_time: '2026-02-24T08:00:00.000Z',
        },
        savedRanges,
        resolvedParentId: '434',
        allowOrphanOverride: false,
      });
      expect(reason).toBeNull();
    });

    it('blocks latest/active parent substitution when lock exists', () => {
      const reason = evaluateChildMappingParentBlockReason({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '434',
        childSpan: {
          range_high_time: '2026-02-24T12:00:00.000Z',
          range_low_time: '2026-02-24T08:00:00.000Z',
        },
        savedRanges,
        resolvedParentId: '437',
        allowOrphanOverride: false,
      });
      expect(reason).toContain('must use locked parent #434');
    });

    it('blocks BOS when active range parent does not match lock', () => {
      const parentBlock = evaluateChildMappingParentBlockReason({
        structureLayer: 'INTRADAY',
        rangeScope: 'MAJOR',
        lockedChildMappingParentId: '434',
        childSpan: { range_high_time: null, range_low_time: null },
        savedRanges,
        resolvedParentId: '434',
        activeRangeParentId: '437',
        allowOrphanOverride: false,
      });
      expect(parentBlock).toContain('does not match locked Daily #434');
      expect(allowsBoundaryCorrectionForParentBlock(parentBlock)).toBe(false);
      expect(evaluateStructuralBosBlockReason({
        hasCase: true,
        structureLayer: 'INTRADAY',
        chartTimeframe: 'H4',
        resolvedRangeId: '439',
        activeRangeBroken: false,
        needsRangeConfirm: false,
        childMappingParentBlockReason: parentBlock,
        candleFeedReady: true,
        admittedMappingCandle: true,
      })).toBe(parentBlock);
    });

    it('retains lock only while mapping layer still expects the locked parent layer', () => {
      expect(shouldRetainChildMappingLock({
        lockedChildMappingParentId: '434',
        structureLayer: 'INTRADAY',
        savedRanges,
      })).toBe(true);
      expect(shouldRetainChildMappingLock({
        lockedChildMappingParentId: '434',
        structureLayer: 'DAILY',
        savedRanges,
      })).toBe(false);
    });

    it('validates lifecycle containment helper used by commit gate', () => {
      expect(parentContainsChildByLifecycle(daily434, [
        Date.parse('2026-02-24T08:00:00.000Z'),
        Date.parse('2026-02-24T12:00:00.000Z'),
      ])).toBe(true);
      expect(parentContainsChildByLifecycle(daily437, [
        Date.parse('2026-02-24T08:00:00.000Z'),
        Date.parse('2026-02-24T12:00:00.000Z'),
      ])).toBe(false);
    });

    it('allows child anchors on the inactive day for ended Daily parents with midnight boundary', () => {
      const endedDaily = {
        ...daily434,
        status: 'BROKEN',
        inactive_from_time: '2026-03-03T00:00:00.000Z',
      };
      expect(parentContainsChildByLifecycle(endedDaily, [
        Date.parse('2026-03-03T14:00:00.000Z'),
      ])).toBe(true);
    });

    it('rejects child anchors after the inactive day for ended Daily parents', () => {
      const endedDaily = {
        ...daily434,
        status: 'BROKEN',
        inactive_from_time: '2026-03-03T00:00:00.000Z',
      };
      expect(parentContainsChildByLifecycle(endedDaily, [
        Date.parse('2026-03-04T00:00:00.000Z'),
      ])).toBe(false);
    });

    it('preserves explicit intraday cutoff for ended Daily parents', () => {
      const endedDaily = {
        ...daily434,
        status: 'BROKEN',
        inactive_from_time: '2026-03-03T10:00:00.000Z',
      };
      expect(parentContainsChildByLifecycle(endedDaily, [
        Date.parse('2026-03-03T14:00:00.000Z'),
      ])).toBe(false);
    });

    it('does not expand midnight lifecycle end for non-Daily parents', () => {
      const endedIntraday = {
        range_id: '439',
        structure_layer: 'INTRADAY',
        range_scope: 'MAJOR',
        status: 'BROKEN',
        active_from_time: '2026-03-02T00:00:00.000Z',
        range_start_time: '2026-03-02T00:00:00.000Z',
        inactive_from_time: '2026-03-03T00:00:00.000Z',
      };
      expect(parentContainsChildByLifecycle(endedIntraday, [
        Date.parse('2026-03-03T14:00:00.000Z'),
      ])).toBe(false);
    });
  });

  describe('draft identity guard', () => {
    const savedIntraday435 = {
      range_id: '435',
      structure_layer: 'INTRADAY',
      range_high_price: 2410,
      range_low_price: 2405,
      status: 'ACTIVE',
    };
    const savedIntraday399 = {
      range_id: '399',
      structure_layer: 'INTRADAY',
      range_high_price: 2408,
      range_low_price: 2402,
      status: 'ACTIVE',
    };

    it('RH+RL without dirty and synced to saved range is not unsaved', () => {
      const synced = evaluateRangeDraftSynced({
        structuralRangeDraftDirty: false,
        activeRangeId: '435',
        structureLayer: 'INTRADAY',
        savedRow: savedIntraday435,
        rhPrice: 2410,
        rlPrice: 2405,
        priceMatches,
        isBrokenStatus: isBroken,
      });
      expect(synced).toBe(true);
      expect(hasUnsavedStructuralDraft({
        rhSet: true,
        rlSet: true,
        structuralRangeDraftDirty: false,
        rangeDraftSynced: synced,
        activeRangeId: '435',
      })).toBe(false);
    });

    it('saved Intraday selection does not create dirty draft when synced', () => {
      expect(evaluateRangeDraftSynced({
        structuralRangeDraftDirty: false,
        activeRangeId: '399',
        structureLayer: 'INTRADAY',
        savedRow: savedIntraday399,
        rhPrice: 2408,
        rlPrice: 2402,
        priceMatches,
        isBrokenStatus: isBroken,
      })).toBe(true);
    });

    it('BROKEN saved Intraday rows still count as saved identity', () => {
      expect(evaluateRangeDraftSynced({
        structuralRangeDraftDirty: false,
        activeRangeId: '435',
        structureLayer: 'INTRADAY',
        savedRow: { ...savedIntraday435, status: 'BROKEN' },
        rhPrice: 2410,
        rlPrice: 2405,
        priceMatches,
        isBrokenStatus: isBroken,
      })).toBe(true);
    });

    it('switching saved Intradays does not trigger Confirm/Discard', () => {
      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: false,
        targetRangeId: '399',
        activeRangeId: '435',
        targetIsParentOnly: false,
        structuralRangeDraftDirty: false,
        confirmSaveEligible: false,
      })).toBe('proceed');
    });

    it('synced RH/RL anchors navigate-only on confirm', () => {
      expect(evaluateDraftNavConfirmAction({
        rangeDraftSynced: true,
        anchorsMatchActiveSavedRow: true,
      })).toBe('navigate-only');
    });

    it('handleDraftNavConfirm path does not save synced saved range', () => {
      expect(evaluateDraftNavConfirmAction({
        rangeDraftSynced: true,
        anchorsMatchActiveSavedRow: false,
      })).toBe('navigate-only');
      expect(evaluateDraftNavConfirmAction({
        rangeDraftSynced: false,
        anchorsMatchActiveSavedRow: true,
      })).toBe('navigate-only');
      expect(evaluateDraftNavConfirmAction({
        rangeDraftSynced: false,
        anchorsMatchActiveSavedRow: false,
      })).toBe('save-required');
    });

    it('clean anchors matching active saved row are not treated as unsaved draft', () => {
      expect(hasUnsavedStructuralDraft({
        rhSet: true,
        rlSet: true,
        structuralRangeDraftDirty: false,
        rangeDraftSynced: false,
        activeRangeId: '435',
        anchorsMatchActiveSavedRow: true,
      })).toBe(false);
    });

    it('dirty RH/RL draft still prompts save/discard', () => {
      expect(hasUnsavedStructuralDraft({
        rhSet: true,
        rlSet: true,
        structuralRangeDraftDirty: true,
        rangeDraftSynced: false,
        activeRangeId: '',
      })).toBe(true);
      expect(evaluateStructuralNavigationGuard({
        hasUnsavedDraft: true,
        targetRangeId: '399',
        activeRangeId: '435',
        targetIsParentOnly: false,
        structuralRangeDraftDirty: true,
        confirmSaveEligible: true,
      })).toBe('prompt-save');
    });

    it('discard clears draft only via discard plan', () => {
      expect(buildDiscardStructuralDraftPlan({
        structureLayer: 'INTRADAY',
        chainDraftMode: false,
        chainDraftBelongsToDraftLayer: false,
      })).toEqual({
        clearRhRl: true,
        clearLayerCacheKey: 'INTRADAY',
        clearDraftDirty: true,
        clearChainDraftMode: false,
      });
    });

    it('deleted_range_ids purge local anchors and layers', () => {
      const savedRanges = [savedIntraday435, savedIntraday399];
      const deletedIds = new Set(['435']);
      expect(layersForDeletedRangeIds(savedRanges, deletedIds)).toEqual(['INTRADAY']);
      expect(purgeStructuralAnchorsByLayer({
        INTRADAY: { rh: { price: '2410' }, rl: { price: '2405' } },
        DAILY: { rh: { price: '1' }, rl: { price: '2' } },
      }, ['INTRADAY'])).toEqual({
        DAILY: { rh: { price: '1' }, rl: { price: '2' } },
      });
    });
  });
});
