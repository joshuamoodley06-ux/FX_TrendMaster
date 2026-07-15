import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  flattenMasterMapRanges,
  masterMapRootForMode,
  type MasterMapDocument,
  type MasterMapHierarchyMode,
  type MasterMapRangeNode,
} from './masterMapAdapter';
import {
  loadPersistedMasterMap,
  type MasterMapBridge,
  type PersistedMasterMapLoadResult,
} from './masterMapClient';

export type MasterMapNavigationRequest = {
  canonicalRangeId: string;
  layer: MasterMapRangeNode['layer'];
  sourceTimeframe: string | null;
  mode: MasterMapHierarchyMode;
  range: MasterMapRangeNode;
};

export type MasterMapNavigationHandler = (request: MasterMapNavigationRequest) => void;

type MasterMapHierarchyViewProps = {
  document: MasterMapDocument;
  selectedCanonicalRangeId?: string | null;
  onNavigationRequest?: MasterMapNavigationHandler;
  initialMode?: MasterMapHierarchyMode;
  onReload?: () => void;
  databasePath?: string;
};

type MasterMapHierarchyPanelProps = {
  symbol?: 'XAUUSD';
  bridge?: MasterMapBridge | null;
  selectedCanonicalRangeId?: string | null;
  onNavigationRequest?: MasterMapNavigationHandler;
};

function formatTimestamp(value: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString().slice(0, 10) : value;
}

function formatPrice(value: number | null): string {
  return value === null ? '—' : value.toFixed(2);
}

function sourceRefLabel(node: MasterMapRangeNode): string {
  if (!node.sourceRefs.length) return 'No source provenance recorded.';
  return node.sourceRefs
    .map((ref) => `${ref.caseRef || 'case:unknown'} · source #${ref.sourceRecordId}`)
    .join('\n');
}

type RangeTreeNodeProps = {
  // Included explicitly because this project does not load React's ambient JSX
  // types during its repository-wide TypeScript diagnostic pass.
  key?: string;
  node: MasterMapRangeNode;
  depth: number;
  mode: MasterMapHierarchyMode;
  expandedIds: Set<string>;
  selectedCanonicalRangeId: string | null;
  onToggle: (canonicalRangeId: string) => void;
  onSelect: (node: MasterMapRangeNode) => void;
};

function RangeTreeNode({
  node,
  depth,
  mode,
  expandedIds,
  selectedCanonicalRangeId,
  onToggle,
  onSelect,
}: RangeTreeNodeProps) {
  const hasChildren = node.children.length > 0;
  const expanded = hasChildren && expandedIds.has(node.canonicalRangeId);
  const selected = selectedCanonicalRangeId === node.canonicalRangeId;
  const statusWithDirection = node.directionOfBreak
    ? `${node.status} ${node.directionOfBreak}`
    : node.status;
  return (
    <>
      <div
        className={[
          'masterMapRangeRow',
          selected ? 'selected' : '',
          node.navigationStatus === 'REVIEW' ? 'review' : '',
          node.reviewContextOnly ? 'reviewContext' : '',
          node.unlinkedReview ? 'unlinkedReview' : '',
        ].filter(Boolean).join(' ')}
        role="treeitem"
        aria-level={depth + 2}
        aria-expanded={hasChildren ? expanded : undefined}
        data-canonical-range-id={node.canonicalRangeId}
        data-navigation-status={node.navigationStatus}
        data-statistics-status={node.statisticsStatus}
        style={{ ['--master-map-depth' as string]: depth }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="masterMapExpandButton"
            aria-label={`${expanded ? 'Collapse' : 'Expand'} ${node.layer} ${node.canonicalRangeId}`}
            onClick={() => onToggle(node.canonicalRangeId)}
          >
            {expanded ? '▼' : '▶'}
          </button>
        ) : <span className="masterMapExpandButton spacer" aria-hidden="true" />}
        <button
          type="button"
          className="masterMapRangeMain"
          onClick={() => onSelect(node)}
          title={`${node.layer} · ${node.canonicalRangeId}`}
        >
          <span className="masterMapRangeIdentity">
            <b>{node.layer}</b>
            <code>{node.canonicalRangeId}</code>
            {node.sourceTimeframe && <em>{node.sourceTimeframe}</em>}
          </span>
          <span className="masterMapRangeFacts">
            <span>{statusWithDirection}</span>
            <span>RH {formatPrice(node.rangeHigh)} / RL {formatPrice(node.rangeLow)}</span>
            <span>{formatTimestamp(node.activeFromTime)} → {formatTimestamp(node.inactiveFromTime)}</span>
          </span>
          <span className="masterMapRangeStatuses">
            <span className={`masterMapStatusBadge nav-${node.navigationStatus.toLowerCase()}`}>
              NAV {node.navigationStatus}
            </span>
            <span className={`masterMapStatusBadge stats-${node.statisticsStatus.toLowerCase()}`}>
              STATS {node.statisticsStatus}
            </span>
            {node.reviewContextOnly && <span className="masterMapStatusBadge">CONTEXT ONLY</span>}
            {node.unlinkedReview && <span className="masterMapStatusBadge">UNLINKED</span>}
          </span>
        </button>
      </div>
      {selected && (
        <details className="masterMapProvenance" data-mode={mode}>
          <summary>Source provenance · {node.sourceCount} record{node.sourceCount === 1 ? '' : 's'}</summary>
          <pre>{sourceRefLabel(node)}</pre>
          <span>Parent link {node.directParentLinkStatus} · ancestor {node.ancestorReviewStatus}</span>
        </details>
      )}
      {expanded && (
        <div role="group">
          {node.children.map((child) => (
            <RangeTreeNode
              key={child.canonicalRangeId}
              node={child}
              depth={depth + 1}
              mode={mode}
              expandedIds={expandedIds}
              selectedCanonicalRangeId={selectedCanonicalRangeId}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </>
  );
}

export function MasterMapHierarchyView({
  document,
  selectedCanonicalRangeId: controlledSelectedId,
  onNavigationRequest,
  initialMode = 'trusted',
  onReload,
  databasePath = '',
}: MasterMapHierarchyViewProps) {
  const [mode, setMode] = useState<MasterMapHierarchyMode>(initialMode);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const selectedCanonicalRangeId = controlledSelectedId === undefined
    ? internalSelectedId
    : controlledSelectedId;
  const root = useMemo(() => masterMapRootForMode(document, mode), [document, mode]);
  const visibleIds = useMemo(
    () => new Set(flattenMasterMapRanges(root).map((node) => node.canonicalRangeId)),
    [root],
  );
  const visibleSelectedId = selectedCanonicalRangeId && visibleIds.has(selectedCanonicalRangeId)
    ? selectedCanonicalRangeId
    : null;

  const changeMode = (nextMode: MasterMapHierarchyMode) => {
    setMode(nextMode);
    setExpandedIds(new Set());
  };
  const toggleNode = (canonicalRangeId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(canonicalRangeId)) next.delete(canonicalRangeId);
      else next.add(canonicalRangeId);
      return next;
    });
  };
  const selectNode = (node: MasterMapRangeNode) => {
    setInternalSelectedId(node.canonicalRangeId);
    onNavigationRequest?.({
      canonicalRangeId: node.canonicalRangeId,
      layer: node.layer,
      sourceTimeframe: node.sourceTimeframe,
      mode,
      range: node,
    });
  };
  const builtDate = formatTimestamp(document.builtAtUtc);

  return (
    <section
      className="masterMapHierarchy"
      aria-label="XAUUSD Master Map hierarchy"
      data-hierarchy-mode={mode}
      data-selected-canonical-range-id={visibleSelectedId || ''}
    >
      <div className="masterMapHeader">
        <div>
          <b>XAUUSD Master Map</b>
          <span>Persisted {builtDate} · {document.structuralContentHash.slice(0, 10)}</span>
        </div>
        {onReload && <button type="button" onClick={onReload}>Refresh</button>}
      </div>
      <div className="masterMapModeSwitch" role="group" aria-label="Master Map hierarchy mode">
        <button
          type="button"
          className={mode === 'trusted' ? 'active' : ''}
          aria-pressed={mode === 'trusted'}
          onClick={() => changeMode('trusted')}
        >
          Normal
        </button>
        <button
          type="button"
          className={mode === 'review' ? 'active review' : ''}
          aria-pressed={mode === 'review'}
          onClick={() => changeMode('review')}
        >
          Review
        </button>
        <button
          type="button"
          className={mode === 'all' ? 'active diagnostic' : ''}
          aria-pressed={mode === 'all'}
          onClick={() => changeMode('all')}
          title="Explicit diagnostic view using the complete navigation root"
        >
          All navigation
        </button>
      </div>
      <p className="masterMapModeHint">
        {mode === 'trusted' && 'Normal hierarchy · trusted_root · statistics-eligible structure only.'}
        {mode === 'review' && 'Review hierarchy · review_root · reviewed structure remains statistics-excluded.'}
        {mode === 'all' && 'Diagnostic hierarchy · root · trusted and reviewed navigation together.'}
      </p>
      <div className="masterMapSelectedId" aria-live="polite">
        Selected canonical ID: <code>{visibleSelectedId || '—'}</code>
      </div>
      <div className="masterMapTree" role="tree" aria-label={`${root.symbol} ${mode} hierarchy`}>
        <div className="masterMapSymbolRow" role="treeitem" aria-level={1} aria-expanded="true">
          <b>{root.symbol}</b>
          <span>{root.children.length} Weekly</span>
        </div>
        <div role="group">
          {root.children.map((node) => (
            <RangeTreeNode
              key={node.canonicalRangeId}
              node={node}
              depth={0}
              mode={mode}
              expandedIds={expandedIds}
              selectedCanonicalRangeId={visibleSelectedId}
              onToggle={toggleNode}
              onSelect={selectNode}
            />
          ))}
        </div>
        {!!root.unlinkedReviewChildren.length && (
          <div className="masterMapUnlinkedGroup">
            <b>Unlinked review</b>
            <div role="group">
              {root.unlinkedReviewChildren.map((node) => (
                <RangeTreeNode
                  key={node.canonicalRangeId}
                  node={node}
                  depth={0}
                  mode={mode}
                  expandedIds={expandedIds}
                  selectedCanonicalRangeId={visibleSelectedId}
                  onToggle={toggleNode}
                  onSelect={selectNode}
                />
              ))}
            </div>
          </div>
        )}
      </div>
      {databasePath && <span className="masterMapDatabasePath" title={databasePath}>Local Master Map ready</span>}
    </section>
  );
}

export function MasterMapHierarchyPanel({
  symbol = 'XAUUSD',
  bridge,
  selectedCanonicalRangeId,
  onNavigationRequest,
}: MasterMapHierarchyPanelProps) {
  const [loadState, setLoadState] = useState<PersistedMasterMapLoadResult | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let active = true;
    setLoadState(null);
    void loadPersistedMasterMap(symbol, bridge === undefined ? undefined : bridge).then((result) => {
      if (active) setLoadState(result);
    });
    return () => { active = false; };
  }, [symbol, bridge, reloadToken]);

  if (!loadState) {
    return <div className="masterMapLoadState" role="status">Loading persisted XAUUSD Master Map…</div>;
  }
  if (!loadState.ok) {
    return (
      <div className="masterMapLoadState error" role="alert">
        <b>Master Map unavailable</b>
        <span>{loadState.error}</span>
        <button type="button" onClick={reload}>Retry</button>
      </div>
    );
  }
  return (
    <MasterMapHierarchyView
      document={loadState.document}
      selectedCanonicalRangeId={selectedCanonicalRangeId}
      onNavigationRequest={onNavigationRequest}
      onReload={reload}
      databasePath={loadState.databasePath}
    />
  );
}
