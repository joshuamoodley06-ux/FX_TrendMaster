// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HierarchyWorkspace } from './hierarchyWorkspace';

describe('HierarchyWorkspace modes', () => {
  let container: HTMLDivElement | null = null;
  let root: Root | null = null;
  afterEach(() => { act(() => root?.unmount()); container?.remove(); root = null; container = null; });
  async function renderWorkspace() {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    const onNavigateRange = vi.fn();
    await act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges: [
        { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
        { range_id: 2, parent_range_id: 1, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
      ],
      structure: createElement('div', { 'data-testid': 'structure' }, 'Mapped structure'),
      onNavigateRange,
    })));
    return onNavigateRange;
  }
  it('defaults to Structure and switches compact modes', async () => {
    await renderWorkspace();
    expect(container?.querySelector('[data-testid="structure"]')).not.toBeNull();
    const tabs = () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs().find((node) => node.textContent === 'Coverage')!.click());
    expect(container?.querySelector('.hierarchyCoverageScroll')).not.toBeNull();
    await act(async () => tabs().find((node) => node.textContent === 'Python')!.click());
    expect(container?.textContent).toContain('Python analysis is dormant.');
  });
  it('routes parent and missing-span clicks through chart navigation', async () => {
    const navigate = await renderWorkspace();
    const coverage = Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!;
    await act(async () => coverage.click());
    expect(container?.textContent).toContain('50%');
    await act(async () => (container!.querySelector('.hierarchyCoverageJump') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ range_id: 1 }));
    await act(async () => (container!.querySelector('.hierarchyCoverageExpand') as HTMLButtonElement).click());
    expect(container?.textContent).toContain('06 Jan 2025');
    await act(async () => (container!.querySelector('.hierarchyCoverageGaps button') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({ range_start_time: '2025-01-06T00:00:00.000Z', range_end_time: '2025-01-11T00:00:00.000Z' }));
  });
  it('renders a readable one-line row at the supported compact width', async () => {
    await renderWorkspace();
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    const row = container!.querySelector('.hierarchyCoverageJump') as HTMLButtonElement;
    expect(row.textContent).toContain('WEEKLY|01 Jan 2025 → 11 Jan 2025|50%');
    expect(row.querySelector('.hierarchyCoveragePrimary')).not.toBeNull();
    expect(container!.querySelector('.hierarchyCoverageScroll')).not.toBeNull();
  });
  it('preserves the scrolling container and chart jump after year filtering', async () => {
    const navigate = await renderWorkspace();
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    const scroll = container!.querySelector('.hierarchyCoverageScroll') as HTMLDivElement;
    scroll.scrollTop = 19;
    const from = container!.querySelector('[aria-label="From year"]') as HTMLSelectElement;
    await act(async () => {
      from.value = '2025';
      from.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(container!.querySelector('.hierarchyCoverageScroll')).toBe(scroll);
    expect(scroll.scrollTop).toBe(19);
    await act(async () => (container!.querySelector('.hierarchyCoverageJump') as HTMLButtonElement).click());
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ range_id: 1 }));
  });

  it('keeps chart mapping controls usable in Coverage mode', async () => {
    await renderWorkspace();
    const rh = document.createElement('button');
    const rl = document.createElement('button');
    const onRh = vi.fn(); const onRl = vi.fn();
    rh.addEventListener('click', onRh); rl.addEventListener('click', onRl);
    document.body.append(rh, rl);
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    rh.click(); rl.click();
    expect(onRh).toHaveBeenCalledTimes(1);
    expect(onRl).toHaveBeenCalledTimes(1);
  });

  it('recomputes Coverage after refreshed saved ranges without resetting filters', async () => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    const base = [
      { range_id: 1, structure_layer: 'WEEKLY', range_start_time: '2024-01-01', range_end_time: '2024-01-11' },
      { range_id: 2, structure_layer: 'WEEKLY', range_start_time: '2025-01-01', range_end_time: '2025-01-11' },
      { range_id: 3, parent_range_id: 2, structure_layer: 'DAILY', range_start_time: '2025-01-01', range_end_time: '2025-01-06' },
    ];
    const render = async (ranges: Record<string, unknown>[]) => act(async () => root!.render(createElement(HierarchyWorkspace, {
      ranges, structure: createElement('div'), onNavigateRange: vi.fn(),
    })));
    await render(base);
    await act(async () => Array.from(container!.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((node) => node.textContent === 'Coverage')!.click());
    const from = container!.querySelector('[aria-label="From year"]') as HTMLSelectElement;
    await act(async () => { from.value = '2025'; from.dispatchEvent(new Event('change', { bubbles: true })); });
    expect(container!.textContent).toContain('50%');
    await render([...base, { range_id: 4, parent_range_id: 2, structure_layer: 'DAILY', range_start_time: '2025-01-06', range_end_time: '2025-01-11' }]);
    expect((container!.querySelector('[aria-label="From year"]') as HTMLSelectElement).value).toBe('2025');
    expect(container!.textContent).toContain('100%');
  });
});
