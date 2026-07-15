// @vitest-environment happy-dom

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { adaptMasterMapOutput } from './masterMapAdapter';
import type { MappingAssistantSnapshot } from './mappingAssistantModel';
import { MappingAssistantPanel } from './mappingAssistantPanel';
import { masterMapFixture } from './testFixtures/masterMapFixture';

function snapshotFixture(): MappingAssistantSnapshot {
  const document = adaptMasterMapOutput(masterMapFixture());
  return {
    schemaVersion: 'xauusd_mapping_assistant_snapshot_v0.1',
    generatedAtUtc: '2026-07-15T00:00:00Z',
    symbol: 'XAUUSD',
    structuralContentHash: document.structuralContentHash,
    summary: {
      researchGapCount: 1,
      blockedCandidateCount: 13,
      uniqueWeeklyParentCount: 1,
      structureQueryReadyCount: 0,
      confirmationQueryReadyCount: 0,
      outcomeQueryReadyCount: 0,
      overallFirstQueryReadyCount: 0,
    },
    gaps: [
      {
        schemaVersion: 'xauusd_mapping_assistant_gap_v0.1',
        gapId: 'mapping-gap:weekly',
        priorityRank: 1,
        gapType: 'RESEARCH_EVIDENCE',
        symbol: 'XAUUSD',
        parent: {
          canonicalRangeId: 'mm:range:weekly-trusted',
          sourceRangeIds: ['431'],
          structureLayer: 'WEEKLY',
          sourceTimeframe: 'W1',
          rangeHigh: 2800,
          rangeLow: 2300,
          rangeHighTime: '2026-01-04T00:00:00Z',
          rangeLowTime: '2026-01-01T00:00:00Z',
          activeFromTime: '2026-01-04T00:00:00Z',
          inactiveFromTime: '2026-03-01T00:00:00Z',
          status: 'BROKEN',
          navigationStatus: 'TRUSTED',
          statisticsStatus: 'ELIGIBLE',
          sourceRefs: [],
        },
        researchImpact: {
          blockedCandidateCount: 13,
          blockedCandidateIds: ['candidate-1'],
          earliestCandidateFreeze: '2026-02-02T00:00:00Z',
          latestCandidateFreeze: '2026-02-20T00:00:00Z',
        },
        requirement: {
          missingEvidenceCode: ['APPROVED_PREFREEZE_WEEKLY_DIRECTION_EVIDENCE'],
          recommendedActionCode: 'MAP_WEEKLY_FORMATION_BOS',
          evidenceAlreadyPresent: [],
          traderTitle: 'Weekly direction evidence missing',
          traderInstruction: 'Review the Weekly move that created this exact parent.',
        },
        navigation: {
          openStructure: {
            canonicalRangeId: 'mm:range:weekly-trusted',
            eventId: null,
            targetLayer: 'WEEKLY',
            targetTimeframe: 'W1',
            preferredAnchorTime: '2026-01-04T00:00:00Z',
            visibleStart: '2025-10-01T00:00:00Z',
            visibleEnd: '2026-02-02T00:00:00Z',
          },
          showFirstCandidate: {
            canonicalRangeId: 'mm:range:daily-trusted',
            eventId: 'mm:event:bos-1',
            targetLayer: 'DAILY',
            targetTimeframe: 'D1',
            preferredAnchorTime: '2026-02-02T00:00:00Z',
            visibleStart: '2026-01-01T00:00:00Z',
            visibleEnd: '2026-02-16T00:00:00Z',
          },
        },
      },
    ],
    masterMap: document,
    determinismHash: 'd'.repeat(64),
    sourceIntegrity: {
      databasePath: 'C:/FXTM/range_library_memory.sqlite3',
      sha256Before: 'e'.repeat(64),
      sha256After: 'e'.repeat(64),
      unchanged: true,
      buildMode: 'DISPOSABLE_SQLITE_BACKUP',
    },
  };
}

describe('MappingAssistantPanel', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    document.body.replaceChildren();
  });

  async function flush() {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it('shows Python needs and routes both exact navigation actions', async () => {
    const snapshot = snapshotFixture();
    const loader = vi.fn().mockResolvedValue({
      ok: true,
      snapshot,
      databasePath: snapshot.sourceIntegrity.databasePath,
    });
    const onNavigationRequest = vi.fn();
    act(() => {
      root.render(createElement(MappingAssistantPanel, {
        fallbackDocument: snapshot.masterMap,
        loader,
        onNavigationRequest,
      }));
    });
    await flush();

    expect(container.textContent).toContain('Weekly direction evidence missing');
    expect(container.textContent).toContain('13 candidates blocked');

    const buttons = Array.from(container.querySelectorAll('button')) as HTMLButtonElement[];
    act(() => buttons.find((button) => button.textContent === 'Open structure')?.click());
    expect(onNavigationRequest).toHaveBeenLastCalledWith(expect.objectContaining({
      canonicalRangeId: 'mm:range:weekly-trusted',
      layer: 'WEEKLY',
      sourceTimeframe: 'W1',
      reason: 'GAP',
      preferredAnchorTime: '2026-01-04T00:00:00Z',
    }));

    act(() => buttons.find((button) => button.textContent === 'Show first candidate')?.click());
    expect(onNavigationRequest).toHaveBeenLastCalledWith(expect.objectContaining({
      canonicalRangeId: 'mm:range:daily-trusted',
      layer: 'DAILY',
      sourceTimeframe: 'D1',
      reason: 'GAP',
      eventId: 'mm:event:bos-1',
    }));
  });

  it('keeps one load across parent rerenders and exposes an internal scroll surface', async () => {
    const snapshot = snapshotFixture();
    const baseLoader = vi.fn().mockResolvedValue({
      ok: true,
      snapshot,
      databasePath: snapshot.sourceIntegrity.databasePath,
    });
    const renderWithFreshLoader = (selectedCanonicalRangeId: string | null) => {
      act(() => {
        root.render(createElement(MappingAssistantPanel, {
          fallbackDocument: snapshot.masterMap,
          selectedCanonicalRangeId,
          loader: () => baseLoader(),
        }));
      });
    };

    renderWithFreshLoader(null);
    await flush();
    renderWithFreshLoader('mm:range:weekly-trusted');
    await flush();

    expect(baseLoader).toHaveBeenCalledTimes(1);
    const scrollSurface = container.querySelector('[data-mapping-assistant-scroll="true"]') as HTMLElement;
    expect(scrollSurface).not.toBeNull();
    expect(scrollSurface.style.overflowY).toBe('auto');
    expect(scrollSurface.style.maxHeight).toContain('100vh');
  });

  it('rebuilds the disposable snapshot when Refresh is clicked', async () => {
    const snapshot = snapshotFixture();
    const loader = vi.fn().mockResolvedValue({
      ok: true,
      snapshot,
      databasePath: snapshot.sourceIntegrity.databasePath,
    });
    act(() => {
      root.render(createElement(MappingAssistantPanel, {
        fallbackDocument: snapshot.masterMap,
        loader,
      }));
    });
    await flush();
    const refresh = Array.from(container.querySelectorAll('button'))
      .find((button) => button.textContent === 'Refresh') as HTMLButtonElement;
    act(() => refresh.click());
    await flush();
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it('shows a truthful error state without falling back to stale Python gaps', async () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const loader = vi.fn().mockResolvedValue({
      ok: false,
      snapshot: null,
      databasePath: '',
      error: 'Python unavailable',
    });
    act(() => {
      root.render(createElement(MappingAssistantPanel, {
        fallbackDocument: document,
        loader,
      }));
    });
    await flush();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Python unavailable');
    expect(container.textContent).not.toContain('Weekly direction evidence missing');
  });
});
