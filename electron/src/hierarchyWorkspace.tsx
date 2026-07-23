import React, { useMemo, useState, type ReactNode } from 'react';
import {
  HierarchyWorkspace as HierarchyWorkspaceCore,
  type HierarchyRangeEnrichment,
  type WeeklyAnalysisActivationResult,
  type WeeklyAnalysisBridge,
} from './hierarchyWorkspaceCore';

export * from './hierarchyWorkspaceCore';

type HierarchyWorkspaceProps = React.ComponentProps<typeof HierarchyWorkspaceCore>;
type RawRecord = Record<string, any>;

type DailyHierarchyProjection = {
  masterMap: unknown;
  needsReviewSourceIds: Set<string>;
};

function cloneJson<T>(value: T): T {
  if (typeof structuredClone === 'function') return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function sourceIds(node: RawRecord): string[] {
  const ids = new Set<string>();
  const refs = Array.isArray(node.source_refs) ? node.source_refs : [];
  for (const ref of refs) {
    if (!ref || typeof ref !== 'object') continue;
    if (ref.raw_id !== null && ref.raw_id !== undefined) ids.add(String(ref.raw_id));
    const recordId = String(ref.source_record_id || '').trim();
    if (recordId) ids.add(recordId);
  }
  return Array.from(ids);
}

function inheritedProcessingStatus(node: RawRecord): string {
  const enrichments = node.analysis_enrichments && typeof node.analysis_enrichments === 'object'
    ? node.analysis_enrichments
    : {};
  const structure = enrichments.daily_structure || enrichments.weekly_structure || {};
  const payload = structure.payload && typeof structure.payload === 'object' ? structure.payload : {};
  return String(
    structure.processing_status
      || payload.inherited_processing_status
      || payload.processing_status
      || '',
  ).toUpperCase();
}

function projectDailyNode(node: RawRecord): RawRecord | null {
  const enrichments = node.analysis_enrichments && typeof node.analysis_enrichments === 'object'
    ? node.analysis_enrichments
    : {};
  const structure = enrichments.daily_structure || enrichments.weekly_structure;
  if (!structure) return null;
  const projectedEnrichments: RawRecord = {
    ...enrichments,
    weekly_structure: structure,
  };
  const reclaim = enrichments.daily_reclaim || enrichments.weekly_reclaim;
  if (reclaim) projectedEnrichments.weekly_reclaim = reclaim;
  const profile = enrichments.daily_profile_classification
    || enrichments.weekly_profile_classification;
  if (profile) projectedEnrichments.weekly_profile_classification = profile;
  return {
    ...node,
    structure_layer: 'WEEKLY',
    children: [],
    analysis_enrichments: projectedEnrichments,
  };
}

/**
 * The existing hierarchy renderer reads approved doctrine from top-level Weekly
 * analysis nodes. Daily doctrine is inherited automatically from those approved
 * rules, so project trusted Daily nodes into that renderer-only input without
 * changing the saved hierarchy or creating a second tree.
 */
export function projectInheritedDailyDoctrineForHierarchy(masterMap: unknown): DailyHierarchyProjection {
  if (!masterMap || typeof masterMap !== 'object') {
    return { masterMap, needsReviewSourceIds: new Set() };
  }
  const next = cloneJson(masterMap as RawRecord);
  const trustedChildren = next?.trusted_root?.children;
  if (!Array.isArray(trustedChildren)) {
    return { masterMap: next, needsReviewSourceIds: new Set() };
  }

  const projections: RawRecord[] = [];
  const needsReviewSourceIds = new Set<string>();
  const visit = (nodes: unknown[]) => {
    for (const rawNode of nodes) {
      if (!rawNode || typeof rawNode !== 'object') continue;
      const node = rawNode as RawRecord;
      if (String(node.structure_layer || '').toUpperCase() === 'DAILY') {
        const projection = projectDailyNode(node);
        if (projection) projections.push(projection);
        if (inheritedProcessingStatus(node) === 'NEEDS_REVIEW') {
          for (const id of sourceIds(node)) needsReviewSourceIds.add(id);
        }
      }
      if (Array.isArray(node.children)) visit(node.children);
    }
  };
  visit(trustedChildren);
  trustedChildren.push(...projections);
  return { masterMap: next, needsReviewSourceIds };
}

function globalWeeklyAnalysisBridge(): WeeklyAnalysisBridge | null {
  const globals = globalThis as typeof globalThis & {
    localResearch?: Pick<WeeklyAnalysisBridge,
      'getWeeklyScript1State' | 'runWeeklyScript1' | 'reviewWeeklyScript1'
      | 'listDoctrineScripts' | 'insertDoctrineScript' | 'runDoctrinePipeline' | 'reviewDoctrineSample'>;
    localMappingBridge?: Pick<WeeklyAnalysisBridge, 'getPaths'>;
  };
  if (!globals.localMappingBridge?.getPaths
    || !globals.localResearch?.getWeeklyScript1State
    || !globals.localResearch?.runWeeklyScript1
    || !globals.localResearch?.listDoctrineScripts
    || !globals.localResearch?.insertDoctrineScript
    || !globals.localResearch?.runDoctrinePipeline) return null;
  return {
    getPaths: globals.localMappingBridge.getPaths,
    getWeeklyScript1State: globals.localResearch.getWeeklyScript1State,
    runWeeklyScript1: globals.localResearch.runWeeklyScript1,
    reviewWeeklyScript1: globals.localResearch.reviewWeeklyScript1,
    listDoctrineScripts: globals.localResearch.listDoctrineScripts,
    insertDoctrineScript: globals.localResearch.insertDoctrineScript,
    runDoctrinePipeline: globals.localResearch.runDoctrinePipeline,
    reviewDoctrineSample: globals.localResearch.reviewDoctrineSample,
  };
}

function decorateActivationResult(
  result: WeeklyAnalysisActivationResult,
  onReviewIds: (ids: Set<string>) => void,
): WeeklyAnalysisActivationResult {
  if (!result?.masterMap) return result;
  const projected = projectInheritedDailyDoctrineForHierarchy(result.masterMap);
  onReviewIds(projected.needsReviewSourceIds);
  return { ...result, masterMap: projected.masterMap };
}

export function HierarchyWorkspace(props: HierarchyWorkspaceProps): ReactNode {
  const [dailyReviewIds, setDailyReviewIds] = useState<Set<string>>(() => new Set());
  const sourceBridge = useMemo(
    () => props.weeklyAnalysisBridge === undefined
      ? globalWeeklyAnalysisBridge()
      : props.weeklyAnalysisBridge,
    [props.weeklyAnalysisBridge],
  );

  const projectedBridge = useMemo<WeeklyAnalysisBridge | null | undefined>(() => {
    if (!sourceBridge) return sourceBridge;
    const capture = (ids: Set<string>) => setDailyReviewIds(ids);
    return {
      ...sourceBridge,
      getWeeklyScript1State: async (args) => decorateActivationResult(
        await sourceBridge.getWeeklyScript1State(args), capture,
      ),
      runWeeklyScript1: async (args) => decorateActivationResult(
        await sourceBridge.runWeeklyScript1(args), capture,
      ),
      reviewWeeklyScript1: sourceBridge.reviewWeeklyScript1
        ? async (args) => decorateActivationResult(
          await sourceBridge.reviewWeeklyScript1!(args), capture,
        )
        : undefined,
      runDoctrinePipeline: sourceBridge.runDoctrinePipeline
        ? async (args) => {
          const result = await sourceBridge.runDoctrinePipeline!(args);
          if (!result?.masterMap) return result;
          const projected = projectInheritedDailyDoctrineForHierarchy(result.masterMap);
          capture(projected.needsReviewSourceIds);
          return { ...result, masterMap: projected.masterMap };
        }
        : undefined,
    };
  }, [sourceBridge]);

  const projectedStructure = useMemo(() => {
    if (typeof props.structure !== 'function') return props.structure;
    return (enrichments: ReadonlyMap<string, HierarchyRangeEnrichment>) => {
      if (!dailyReviewIds.size) return props.structure(enrichments);
      const next = new Map(enrichments);
      for (const id of dailyReviewIds) {
        const current = next.get(id);
        if (!current) continue;
        const marker = current.bos.includes('⚠ Review') ? current.bos : `${current.bos} · ⚠ Review`;
        next.set(id, { ...current, bos: marker, status: 'Needs Review' });
      }
      return props.structure(next);
    };
  }, [dailyReviewIds, props.structure]);

  return <HierarchyWorkspaceCore
    {...props}
    structure={projectedStructure}
    weeklyAnalysisBridge={projectedBridge}
  />;
}
