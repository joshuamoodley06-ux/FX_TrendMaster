// @vitest-environment happy-dom

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adaptMasterMapOutput } from './masterMapAdapter';
import {
  MasterMapHierarchyView,
  masterMapChronologyFacts,
  type MasterMapNavigationRequest,
} from './masterMapHierarchy';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('MasterMapHierarchyView', () => {
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

  function renderView(onNavigationRequest?: (request: MasterMapNavigationRequest) => void) {
    act(() => {
      root.render(createElement(MasterMapHierarchyView, {
        document: adaptMasterMapOutput(masterMapFixture()),
        onNavigationRequest,
      }));
    });
  }

  function click(selector: string) {
    const element = container.querySelector(selector) as HTMLElement | null;
    expect(element, `missing ${selector}`).not.toBeNull();
    act(() => element?.click());
  }

  it('renders trusted_root by default and expands Weekly to Daily to Intraday', () => {
    renderView();

    expect(container.querySelector('.masterMapSymbolRow')?.textContent).toContain('XAUUSD');
    expect(container.querySelector('[data-hierarchy-mode="trusted"]')).not.toBeNull();
    expect(container.querySelector('[data-canonical-range-id="mm:range:weekly-trusted"]')).not.toBeNull();
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-trusted"]')).toBeNull();
    expect(container.textContent).not.toContain('mm:range:daily-review');

    click('[aria-label="Expand WEEKLY mm:range:weekly-trusted"]');
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-trusted"]')).not.toBeNull();
    click('[aria-label="Expand DAILY mm:range:daily-trusted"]');
    expect(container.querySelector('[data-canonical-range-id="mm:range:intraday-trusted"]')).not.toBeNull();
  });

  it('shows compact chronological anchor order and BOS direction on the range row', () => {
    renderView();

    const row = container.querySelector('[data-canonical-range-id="mm:range:weekly-trusted"]');
    expect(row?.getAttribute('data-chronology-start-side')).toBe('RL');
    expect(row?.getAttribute('data-chronology-end-side')).toBe('RH');
    expect(row?.getAttribute('data-bos-direction')).toBe('DOWN');
    expect(row?.textContent).toContain('RL → RH');
    expect(row?.textContent).toContain('BOS ▼');
    expect(row?.textContent).not.toContain('NAV TRUSTED');
    expect(row?.textContent).not.toContain('STATS ELIGIBLE');
  });

  it('derives RH to RL chronology and down direction without changing raw range truth', () => {
    const document = adaptMasterMapOutput(masterMapFixture());
    const node = document.trustedRoot.children[0];
    const facts = masterMapChronologyFacts({
      ...node,
      rangeHighTime: '2026-02-01T00:00:00Z',
      rangeLowTime: '2026-03-01T00:00:00Z',
      directionOfBreak: 'BOS_DOWN',
    });

    expect(facts).toMatchObject({
      startSide: 'RH',
      endSide: 'RL',
      direction: 'DOWN',
      directionArrow: '▼',
    });
  });

  it('shows a compact pending indicator when no BOS direction is stored', () => {
    const fixture = masterMapFixture();
    for (const rootKey of ['root', 'trusted_root'] as const) {
      const rootNode = fixture[rootKey] as { children: Array<Record<string, unknown>> };
      rootNode.children[0].direction_of_break = null;
    }
    act(() => {
      root.render(createElement(MasterMapHierarchyView, {
        document: adaptMasterMapOutput(fixture),
      }));
    });

    const row = container.querySelector('[data-canonical-range-id="mm:range:weekly-trusted"]');
    expect(row?.getAttribute('data-bos-direction')).toBe('');
    expect(row?.textContent).toContain('BOS ·');
    expect(row?.querySelector('[aria-label="BOS pending"]')).not.toBeNull();
  });

  it('uses review_root only in Review mode and keeps reviewed rows statistics-excluded', () => {
    renderView();
    click('[aria-label="Master Map hierarchy mode"] button:nth-child(2)');
    click('[aria-label="Expand WEEKLY mm:range:weekly-trusted"]');

    expect(container.querySelector('[data-hierarchy-mode="review"]')).not.toBeNull();
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-review"]')).not.toBeNull();
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-trusted"]')).toBeNull();
    expect(
      container.querySelector('[data-canonical-range-id="mm:range:daily-review"]')
        ?.getAttribute('data-statistics-status'),
    ).toBe('EXCLUDED');
    expect(container.textContent).toContain('Unlinked review');
  });

  it('exposes the stable selected canonical range id through the navigation callback', () => {
    const onNavigationRequest = vi.fn();
    renderView(onNavigationRequest);
    click('[data-canonical-range-id="mm:range:weekly-trusted"] .masterMapRangeMain');

    expect(onNavigationRequest).toHaveBeenCalledTimes(1);
    expect(onNavigationRequest.mock.calls[0][0]).toMatchObject({
      canonicalRangeId: 'mm:range:weekly-trusted',
      layer: 'WEEKLY',
      mode: 'trusted',
      reason: 'HIERARCHY',
    });
    expect(container.querySelector('.masterMapHierarchy')?.getAttribute('data-selected-canonical-range-id'))
      .toBe('mm:range:weekly-trusted');
    expect(container.querySelector('.masterMapSelectedId')?.textContent)
      .toContain('mm:range:weekly-trusted');
    expect(container.querySelector('.masterMapProvenance')?.textContent).toContain('Range details');
  });

  it('uses root only after the explicit All navigation action', () => {
    renderView();
    click('[aria-label="Master Map hierarchy mode"] button:nth-child(3)');
    click('[aria-label="Expand WEEKLY mm:range:weekly-trusted"]');

    expect(container.querySelector('[data-hierarchy-mode="all"]')).not.toBeNull();
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-trusted"]')).not.toBeNull();
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-review"]')).not.toBeNull();
  });
});
