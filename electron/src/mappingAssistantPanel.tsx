import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  loadMappingAssistant,
  type MappingAssistantLoadResult,
} from './mappingAssistantClient';
import {
  masterMapDocumentToCoverageRanges,
  navigationRequestForAssistantTarget,
  navigationRequestForCoverageGap,
  type MappingAssistantResearchGap,
  type MappingAssistantSnapshot,
} from './mappingAssistantModel';
import { computeMappingGaps, type MappingGap } from './mappingWorkflow';
import type { MasterMapDocument } from './masterMapAdapter';
import type { MasterMapNavigationHandler } from './masterMapHierarchy';

export type MappingAssistantLoader = () => Promise<MappingAssistantLoadResult>;

type Props = {
  fallbackDocument: MasterMapDocument;
  selectedCanonicalRangeId?: string | null;
  onNavigationRequest?: MasterMapNavigationHandler;
  loader?: MappingAssistantLoader;
};

function date(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString().slice(0, 10) : value;
}

function price(value: number): string {
  return Number(value).toFixed(2);
}

function coverageTitle(gap: MappingGap): string {
  if (gap.parentLayer === 'WEEKLY' && gap.expectedChildLayer === 'DAILY') return 'Daily structure coverage';
  if (gap.parentLayer === 'DAILY' && gap.expectedChildLayer === 'INTRADAY') return 'H4/H1 structure coverage';
  return `${gap.expectedChildLayer} structure coverage`;
}

function coverageInstruction(gap: MappingGap): string {
  const coverage = gap.coverage;
  if (!coverage || coverage.coverage_status === 'NO_CHILDREN') {
    return `No meaningful ${gap.expectedChildLayer.toLowerCase()} structure is mapped inside this ${gap.parentLayer.toLowerCase()} parent yet.`;
  }
  if (coverage.first_gap_start) {
    return `Review ${date(coverage.first_gap_start)} to ${date(coverage.first_gap_end)} for meaningful ${gap.expectedChildLayer.toLowerCase()} structure.`;
  }
  return `${coverage.coverage_percent}% of the parent window is covered. Review the remaining structural space.`;
}

function GapActions({
  gap,
  snapshot,
  onNavigationRequest,
}: {
  gap: MappingAssistantResearchGap;
  snapshot: MappingAssistantSnapshot;
  onNavigationRequest?: MasterMapNavigationHandler;
}) {
  const navigate = (kind: 'openStructure' | 'showFirstCandidate') => {
    const request = navigationRequestForAssistantTarget(gap.navigation[kind], snapshot.masterMap);
    if (request) onNavigationRequest?.(request);
  };
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <button type="button" onClick={() => navigate('openStructure')}>Open structure</button>
      <button type="button" onClick={() => navigate('showFirstCandidate')}>Show first candidate</button>
    </div>
  );
}

function ResearchGapCard({
  gap,
  snapshot,
  onNavigationRequest,
}: {
  gap: MappingAssistantResearchGap;
  snapshot: MappingAssistantSnapshot;
  onNavigationRequest?: MasterMapNavigationHandler;
}) {
  return (
    <article
      data-mapping-assistant-gap-id={gap.gapId}
      style={{ border: '1px solid #273247', borderRadius: 8, padding: 10, display: 'grid', gap: 8 }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <b>{gap.priorityRank}. {gap.requirement.traderTitle}</b>
        <span>{gap.researchImpact.blockedCandidateCount} candidate{gap.researchImpact.blockedCandidateCount === 1 ? '' : 's'} blocked</span>
      </div>
      <code style={{ overflowWrap: 'anywhere' }}>{gap.parent.canonicalRangeId}</code>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 12 }}>
        <span>RH {price(gap.parent.rangeHigh)} · {date(gap.parent.rangeHighTime)}</span>
        <span>RL {price(gap.parent.rangeLow)} · {date(gap.parent.rangeLowTime)}</span>
        <span>First candidate {date(gap.researchImpact.earliestCandidateFreeze)}</span>
        <span>Last candidate {date(gap.researchImpact.latestCandidateFreeze)}</span>
      </div>
      <p style={{ margin: 0 }}>{gap.requirement.traderInstruction}</p>
      <small title={gap.requirement.missingEvidenceCode.join(', ')}>
        Action: {gap.requirement.recommendedActionCode}
      </small>
      <GapActions gap={gap} snapshot={snapshot} onNavigationRequest={onNavigationRequest} />
    </article>
  );
}

function CoverageGapCard({
  gap,
  document,
  onNavigationRequest,
}: {
  gap: MappingGap;
  document: MasterMapDocument;
  onNavigationRequest?: MasterMapNavigationHandler;
}) {
  const request = navigationRequestForCoverageGap(gap, document);
  return (
    <article
      data-coverage-parent-id={gap.parentId}
      style={{ border: '1px solid #273247', borderRadius: 8, padding: 10, display: 'grid', gap: 7 }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <b>{coverageTitle(gap)}</b>
        <span>{gap.coverage?.coverage_percent ?? 0}%</span>
      </div>
      <code style={{ overflowWrap: 'anywhere' }}>{gap.parentId}</code>
      <p style={{ margin: 0 }}>{coverageInstruction(gap)}</p>
      <button
        type="button"
        disabled={!request}
        onClick={() => request && onNavigationRequest?.(request)}
      >
        Open gap
      </button>
    </article>
  );
}

export function MappingAssistantPanel({
  fallbackDocument,
  selectedCanonicalRangeId = null,
  onNavigationRequest,
  loader = loadMappingAssistant,
}: Props) {
  const [loadState, setLoadState] = useState<MappingAssistantLoadResult | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    setLoadState(null);
    void loader().then((result) => {
      if (active) setLoadState(result);
    });
    return () => { active = false; };
  }, [loader, reloadToken]);

  const document = loadState?.ok ? loadState.snapshot.masterMap : fallbackDocument;
  const coverageGaps = useMemo(() => {
    const ranges = masterMapDocumentToCoverageRanges(document);
    const gaps = [
      ...computeMappingGaps(ranges, 'htf'),
      ...computeMappingGaps(ranges, 'ltf'),
    ];
    return gaps.sort((left, right) => {
      const leftCurrent = selectedCanonicalRangeId && left.parentId === selectedCanonicalRangeId ? 0 : 1;
      const rightCurrent = selectedCanonicalRangeId && right.parentId === selectedCanonicalRangeId ? 0 : 1;
      return leftCurrent - rightCurrent
        || String(left.parentId).localeCompare(String(right.parentId));
    });
  }, [document, selectedCanonicalRangeId]);

  if (!loadState) {
    return <div role="status" style={{ padding: 12 }}>Python is rebuilding the current mapping gaps…</div>;
  }
  if (!loadState.ok) {
    return (
      <div role="alert" style={{ padding: 12, display: 'grid', gap: 8 }}>
        <b>Mapping Assistant unavailable</b>
        <span>{loadState.error}</span>
        <button type="button" onClick={refresh}>Retry</button>
      </div>
    );
  }

  const { snapshot } = loadState;
  return (
    <section aria-label="XAUUSD Mapping Assistant" style={{ display: 'grid', gap: 12 }}>
      <header style={{ display: 'grid', gap: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
          <div>
            <b>Python Mapping Assistant</b>
            <div style={{ fontSize: 12, opacity: 0.8 }}>
              {snapshot.summary.researchGapCount} research gap{snapshot.summary.researchGapCount === 1 ? '' : 's'} · {snapshot.summary.blockedCandidateCount} candidates blocked
            </div>
          </div>
          <button type="button" onClick={refresh}>Refresh</button>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: 12 }}>
          <span>Structure ready {snapshot.summary.structureQueryReadyCount}</span>
          <span>Confirmation ready {snapshot.summary.confirmationQueryReadyCount}</span>
          <span>Outcome ready {snapshot.summary.outcomeQueryReadyCount}</span>
        </div>
      </header>

      <div style={{ display: 'grid', gap: 8 }}>
        <b>Python needs</b>
        {snapshot.gaps.length === 0 && <p style={{ margin: 0 }}>No Python research gaps remain for the current snapshot.</p>}
        {snapshot.gaps.map((gap) => (
          <ResearchGapCard
            key={gap.gapId}
            gap={gap}
            snapshot={snapshot}
            onNavigationRequest={onNavigationRequest}
          />
        ))}
      </div>

      <div style={{ display: 'grid', gap: 8 }}>
        <b>Hierarchy coverage</b>
        {coverageGaps.length === 0 && <p style={{ margin: 0 }}>Current parent-child coverage is complete.</p>}
        {coverageGaps.map((gap) => (
          <CoverageGapCard
            key={`${gap.parentId}:${gap.expectedChildLayer}`}
            gap={gap}
            document={document}
            onNavigationRequest={onNavigationRequest}
          />
        ))}
      </div>

      <small title={snapshot.sourceIntegrity.databasePath}>
        Disposable snapshot · source SHA unchanged · {snapshot.structuralContentHash.slice(0, 10)}
      </small>
    </section>
  );
}
