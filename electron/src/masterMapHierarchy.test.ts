// @vitest-environment happy-dom

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adaptMasterMapOutput } from './masterMapAdapter';
import {
  MasterMapHierarchyView,
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
    expect(container.querySelector('.masterMapProvenance')?.textContent).toContain('Source provenance');
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
