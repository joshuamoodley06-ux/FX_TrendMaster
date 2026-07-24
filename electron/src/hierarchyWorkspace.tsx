import React, {
  Children,
  cloneElement,
  isValidElement,
  useMemo,
  useState,
  type ReactElement,
  type ReactNode,
} from 'react';
import {
  HierarchyWorkspace as HierarchyWorkspaceCore,
  type HierarchyRangeEnrichment,
  type WeeklyAnalysisActivationResult,
  type WeeklyAnalysisBridge,
} from './hierarchyWorkspaceCore';

export * from './hierarchyWorkspaceCore';

type HierarchyWorkspaceProps = React.ComponentProps<typeof HierarchyWorkspaceCore>;
type RawRecord = Record<string, any>;

type LowerTimeframeHierarchyProjection = {
  masterMap: unknown;
  needsReviewSourceIds: Set<string>;
};

type ProjectionKeys = {
  structure: string;
  reclaim: string;
  profile: string;
};

const LOWER_TIMEFRAME_KEYS: Record<string, ProjectionKeys> = {
  DAILY: {
    structure: 'daily_structure',
    reclaim: 'daily_reclaim',
    profile: 'daily_profile_classification',
  },
  INTRADAY: {
    structure: 'intraday_structure',
    reclaim: 'intraday_reclaim',
    profile: 'intraday_profile_classification',
  },
};

const DOCTRINE_LAYER_ACCENTS: Record<string, string> = {
  WEEKLY: '#ef4444',
  DAILY: '#22c55e',
  INTRADAY: '#3b82f6',
  MICRO: '#f59e0b',
};

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

function enrichmentStatus(memory: RawRecord): string {
  const payload = memory?.payload && typeof memory.payload === 'object' ? memory.payload : {};
  return String(
    memory?.processing_status
      || payload.inherited_processing_status
      || payload.processing_status
      || '',
  ).toUpperCase();
}

function inheritedProcessingStatus(node: RawRecord, keys: ProjectionKeys): string {
  const enrichments = node.analysis_enrichments && typeof node.analysis_enrichments === 'object'
    ? node.analysis_enrichments
    : {};
  const prefix = `${keys.structure.split('_')[0]}_`;
  const statuses = Object.entries(enrichments)
    .filter(([key]) => key.startsWith(prefix))
    .map(([, memory]) => enrichmentStatus(memory as RawRecord))
    .filter(Boolean);
  if (statuses.includes('NEEDS_REVIEW')) return 'NEEDS_REVIEW';
  if (statuses.includes('PENDING')) return 'PENDING';
  return enrichmentStatus(enrichments[keys.structure] || {});
}

/**
 * Inspect inherited lower-timeframe doctrine without changing the Master Map.
 * The renderer resolves native namespaces from each node's real layer.
 */
export function projectInheritedLowerTimeframeDoctrineForHierarchy(
  masterMap: unknown,
): LowerTimeframeHierarchyProjection {
  if (!masterMap || typeof masterMap !== 'object') {
    return { masterMap, needsReviewSourceIds: new Set() };
  }
  const next = masterMap as RawRecord;
  const trustedChildren = next?.trusted_root?.children;
  if (!Array.isArray(trustedChildren)) {
    return { masterMap: next, needsReviewSourceIds: new Set() };
  }

  const needsReviewSourceIds = new Set<string>();
  const visit = (nodes: unknown[]) => {
    for (const rawNode of nodes) {
      if (!rawNode || typeof rawNode !== 'object') continue;
      const node = rawNode as RawRecord;
      const layer = String(node.structure_layer || '').toUpperCase();
      const keys = LOWER_TIMEFRAME_KEYS[layer];
      if (keys) {
        if (inheritedProcessingStatus(node, keys) === 'NEEDS_REVIEW') {
          for (const id of sourceIds(node)) needsReviewSourceIds.add(id);
        }
      }
      if (Array.isArray(node.children)) visit(node.children);
    }
  };
  visit(trustedChildren);
  return { masterMap: next, needsReviewSourceIds };
}

// Backward-compatible export for existing tests/importers.
export const projectInheritedDailyDoctrineForHierarchy =
  projectInheritedLowerTimeframeDoctrineForHierarchy;

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
  const projected = projectInheritedLowerTimeframeDoctrineForHierarchy(result.masterMap);
  onReviewIds(projected.needsReviewSourceIds);
  return { ...result, masterMap: projected.masterMap };
}

function hasClassName(node: ReactNode, className: string): boolean {
  return isValidElement(node)
    && String((node.props as RawRecord).className || '').split(/\s+/).includes(className);
}

function nodeText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (!isValidElement(node)) return '';
  return Children.toArray((node.props as RawRecord).children).map(nodeText).join(' ');
}

function hierarchyRowLayer(element: ReactElement<RawRecord>): string {
  const explicit = String(
    element.props['data-layer']
      || element.props['data-structure-layer']
      || element.props['data-range-layer']
      || '',
  ).toUpperCase();
  if (DOCTRINE_LAYER_ACCENTS[explicit]) return explicit;
  const label = nodeText(element).toUpperCase();
  return Object.keys(DOCTRINE_LAYER_ACCENTS).find((layer) => label.includes(layer)) || '';
}

function rowMainHasDoctrine(node: ReactNode): boolean {
  if (!isValidElement(node) || !hasClassName(node, 'explorerTreeRowMain')) return false;
  return Children.toArray((node.props as RawRecord).children).some(
    (child) => hasClassName(child, 'weeklyScript1InlineEnrichment')
      || hasClassName(child, 'nativeDoctrineInlineEnrichment'),
  );
}

function annotateRowMain(
  node: ReactNode,
  enrichment: HierarchyRangeEnrichment,
  layer: string,
): ReactNode {
  if (!isValidElement(node)) return node;
  const element = node as ReactElement<RawRecord>;
  if (!hasClassName(element, 'explorerTreeRowMain')) return element;
  const children = Children.toArray(element.props.children);
  if (rowMainHasDoctrine(element)) return element;

  const hasReview = String(enrichment.status || '').toUpperCase().includes('REVIEW')
    || /⚠\s*REVIEW/i.test(String(enrichment.bos || ''));
  const bosFacts = String(enrichment.bos || '')
    .replace(/\s*·?\s*⚠\s*REVIEW/ig, '')
    .trim();
  const summary = [String(enrichment.chronology || '').trim(), bosFacts]
    .filter(Boolean)
    .join(' · ');
  const accent = DOCTRINE_LAYER_ACCENTS[layer] || '#64748b';
  const existingStyle = element.props.style && typeof element.props.style === 'object'
    ? element.props.style
    : {};

  return cloneElement(element, {
    style: {
      ...existingStyle,
      height: 'auto',
      minHeight: 0,
      overflow: 'visible',
      flexWrap: 'wrap',
      rowGap: '4px',
      alignItems: 'center',
    },
  }, ...children, <span
    key="native-doctrine"
    className="nativeDoctrineInlineEnrichment"
    data-doctrine-layer={layer || 'UNKNOWN'}
    data-needs-review={hasReview ? 'true' : 'false'}
    style={{
      display: 'block',
      flexBasis: '100%',
      gridColumn: '1 / -1',
      width: '100%',
      minWidth: 0,
      marginTop: '3px',
      padding: '5px 8px',
      border: '1px solid rgba(148, 163, 184, 0.28)',
      borderLeft: `3px solid ${accent}`,
      borderRadius: '6px',
      background: 'rgba(8, 15, 26, 0.96)',
      color: '#f8fafc',
      fontSize: '10px',
      fontWeight: 700,
      lineHeight: 1.35,
      whiteSpace: 'normal',
      overflow: 'visible',
      overflowWrap: 'anywhere',
      textAlign: 'left',
      pointerEvents: 'none',
      boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.035)',
    }}
  >
    <span>{summary}</span>
    {hasReview && <span style={{ color: '#fbbf24', whiteSpace: 'nowrap' }}> · ⚠ Review</span>}
  </span>);
}

/**
 * Adds native lower-timeframe doctrine text to the existing rendered row.
 * It does not add, clone, reorder, or reparent hierarchy rows.
 */
export function renderNativeLayerAnnotations(
  node: ReactNode,
  enrichments: ReadonlyMap<string, HierarchyRangeEnrichment>,
): ReactNode {
  if (!isValidElement(node)) return node;
  const element = node as ReactElement<RawRecord>;
  const rangeId = String(element.props['data-range-id'] || '').trim();
  const isRow = hasClassName(element, 'explorerTreeRow');
  const enrichment = isRow && rangeId ? enrichments.get(rangeId) : undefined;
  const layer = isRow ? hierarchyRowLayer(element) : '';
  const directChildren = Children.toArray(element.props.children);
  const needsNativeCard = !!enrichment && directChildren.some(
    (child) => hasClassName(child, 'explorerTreeRowMain') && !rowMainHasDoctrine(child),
  );
  const children = Children.map(element.props.children, (child) => (
    needsNativeCard && hasClassName(child, 'explorerTreeRowMain')
      ? annotateRowMain(child, enrichment!, layer)
      : renderNativeLayerAnnotations(child, enrichments)
  ));
  const existingStyle = element.props.style && typeof element.props.style === 'object'
    ? element.props.style
    : {};
  const rowProps = needsNativeCard
    ? {
      'data-doctrine-layer': layer || 'UNKNOWN',
      style: {
        ...existingStyle,
        height: 'auto',
        minHeight: 0,
        overflow: 'visible',
      },
    }
    : undefined;
  return cloneElement(element, rowProps, children);
}

export function HierarchyWorkspace(props: HierarchyWorkspaceProps): ReactNode {
  const [lowerTimeframeReviewIds, setLowerTimeframeReviewIds] = useState<Set<string>>(() => new Set());
  const sourceBridge = useMemo(
    () => props.weeklyAnalysisBridge === undefined
      ? globalWeeklyAnalysisBridge()
      : props.weeklyAnalysisBridge,
    [props.weeklyAnalysisBridge],
  );

  const projectedBridge = useMemo<WeeklyAnalysisBridge | null | undefined>(() => {
    if (!sourceBridge) return sourceBridge;
    const capture = (ids: Set<string>) => setLowerTimeframeReviewIds(ids);
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
          const projected = projectInheritedLowerTimeframeDoctrineForHierarchy(result.masterMap);
          capture(projected.needsReviewSourceIds);
          return { ...result, masterMap: projected.masterMap };
        }
        : undefined,
    };
  }, [sourceBridge]);

  const projectedStructure = useMemo(() => {
    if (typeof props.structure !== 'function') return props.structure;
    return (enrichments: ReadonlyMap<string, HierarchyRangeEnrichment>) => {
      const next = new Map(enrichments);
      for (const id of lowerTimeframeReviewIds) {
        const current = next.get(id);
        if (!current) continue;
        const marker = current.bos.includes('⚠ Review') ? current.bos : `${current.bos} · ⚠ Review`;
        next.set(id, { ...current, bos: marker, status: 'Needs Review' });
      }
      return renderNativeLayerAnnotations(props.structure(next), next);
    };
  }, [lowerTimeframeReviewIds, props.structure]);

  return <HierarchyWorkspaceCore
    {...props}
    structure={projectedStructure}
    weeklyAnalysisBridge={projectedBridge}
  />;
}
