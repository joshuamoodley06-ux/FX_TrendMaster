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
    const weekly = container.querySelector('[data-canonical-range-id="mm:range:weekly-trusted"]');
    expect(weekly?.getAttribute('data-script1-chronology')).toBe('RL → RH');
    expect(weekly?.getAttribute('data-script1-bos-direction')).toBe('UP');
    expect(weekly?.textContent).toContain('BOS ▲');
    expect(weekly?.textContent).toContain('2026-02-01');

    click('[aria-label="Expand WEEKLY mm:range:weekly-trusted"]');
    expect(container.querySelector('[data-canonical-range-id="mm:range:daily-trusted"]')).not.toBeNull();
    click('[aria-label="Expand DAILY mm:range:daily-trusted"]');
    expect(container.querySelector('[data-canonical-range-id="mm:range:intraday-trusted"]')).not.toBeNull();
  });

  it('shows pending and review Script 1 facts without changing canonical navigation', () => {
    const fixture = masterMapFixture();
    const trustedRoot = fixture.trusted_root as Record<string, unknown>;
    const weekly = (trustedRoot.children as Record<string, unknown>[])[0];
    weekly.script1_chronology = 'PENDING';
    weekly.script1_bos_direction = 'PENDING';
    weekly.script1_bos_time = null;
    weekly.script1_processing_status = 'NEEDS_REVIEW';
    weekly.script1_reason_codes = ['EQUAL_ANCHOR_TIMES'];
    const onNavigationRequest = vi.fn();
    act(() => {
      root.render(createElement(MasterMapHierarchyView, {
        document: adaptMasterMapOutput(fixture),
        onNavigationRequest,
      }));
    });

    const row = container.querySelector('[data-canonical-range-id="mm:range:weekly-trusted"]');
    expect(row?.getAttribute('data-script1-status')).toBe('NEEDS_REVIEW');
    expect(row?.textContent).toContain('BOS pending');
    expect(row?.textContent).toContain('SCRIPT 1 REVIEW');
    click('[data-canonical-range-id="mm:range:weekly-trusted"] .masterMapRangeMain');
    expect(container.querySelector('.masterMapProvenance')?.textContent).toContain('EQUAL_ANCHOR_TIMES');
    expect(onNavigationRequest).toHaveBeenCalledWith(expect.objectContaining({
      canonicalRangeId: 'mm:range:weekly-trusted',
      reason: 'HIERARCHY',
    }));
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
