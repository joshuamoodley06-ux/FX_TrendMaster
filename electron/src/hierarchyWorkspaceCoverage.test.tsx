// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace } from './hierarchyWorkspace';

describe('HierarchyWorkspace candle-backed coverage', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
  });

  it('keeps only suspected gap spans that have local OHLC', async () => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    const navigate = vi.fn();
    const fetchCoverageCandles = vi.fn().mockResolvedValue({
      ok: true,
      candles: [
        { time: '2025.01.03 20:00' },
        { time: '2025.01.06 00:00' },
        { time: '2025.01.06 01:00' },
      ],
    });

    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [
        {
          range_id: 1,
          structure_layer: 'DAILY',
          range_start_time: '2025-01-03T18:00:00Z',
          range_end_time: '2025-01-06T02:00:00Z',
        },
        {
          range_id: 2,
          parent_range_id: 1,
          structure_layer: 'INTRADAY',
          range_start_time: '2025-01-03T18:00:00Z',
          range_end_time: '2025-01-03T20:00:00Z',
        },
      ],
      structure: createElement('div', null, 'Structure'),
      onNavigateRange: navigate,
      caseRef: 'case:live',
      symbol: 'XAUUSD',
      weeklyAnalysisBridge: null,
      coverageCandleFetcher: fetchCoverageCandles,
    })));

    const tabs = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs.find((button) => button.textContent === 'Coverage')!.click());
    const daily = Array.from(container.querySelectorAll<HTMLButtonElement>('.hierarchyCoverageFilters button'))
      .find((button) => button.textContent === 'Daily')!;
    await act(async () => {
      daily.click();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchCoverageCandles).toHaveBeenCalledWith('XAUUSD', 'H1', expect.objectContaining({ limit: 10_000 }));
    expect(container.textContent).toContain('40%');

    await act(async () => (container!.querySelector('.hierarchyCoverageExpand') as HTMLButtonElement).click());
    const gapButtons = Array.from(container.querySelectorAll<HTMLButtonElement>('.hierarchyCoverageGaps button'));
    expect(gapButtons).toHaveLength(2);

    await act(async () => gapButtons[0].click());
    expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({
      range_start_time: '2025-01-03T20:00:00.000Z',
      range_end_time: '2025-01-03T21:00:00.000Z',
    }));
    await act(async () => gapButtons[1].click());
    expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({
      range_start_time: '2025-01-06T00:00:00.000Z',
      range_end_time: '2025-01-06T02:00:00.000Z',
    }));
  });

  it('removes a suspected gap when the local candle query succeeds with no OHLC', async () => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    const fetchCoverageCandles = vi.fn().mockResolvedValue({ ok: true, candles: [] });

    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [
        { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
        { range_id: 2, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
      ],
      structure: createElement('div', null, 'Structure'),
      onNavigateRange: vi.fn(),
      caseRef: 'case:live',
      symbol: 'XAUUSD',
      weeklyAnalysisBridge: null,
      coverageCandleFetcher: fetchCoverageCandles,
    })));

    const coverage = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((button) => button.textContent === 'Coverage')!;
    await act(async () => {
      coverage.click();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => (container!.querySelector('.hierarchyCoverageExpand') as HTMLButtonElement).click());

    expect(container.querySelectorAll('.hierarchyCoverageGaps button')).toHaveLength(0);
    expect(container.textContent).toContain('No local OHLC in this parent window');
  });
});
