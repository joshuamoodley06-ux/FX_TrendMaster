// @vitest-environment happy-dom

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { adaptMasterMapOutput } from './masterMapAdapter';
import { MasterMapHierarchyView } from './masterMapHierarchy';
import { masterMapFixture } from './testFixtures/masterMapFixture';

describe('XAUUSD hierarchy workspace', () => {
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

  it('keeps Master Map intact and opens Mapping Assistant in its own full workspace', async () => {
    const loader = vi.fn().mockResolvedValue({
      ok: false,
      snapshot: null,
      databasePath: '',
      error: 'test assistant unavailable',
    });
    act(() => {
      root.render(createElement(MasterMapHierarchyView, {
        document: adaptMasterMapOutput(masterMapFixture()),
        mappingAssistantLoader: loader,
      }));
    });

    expect(container.querySelector('[data-hierarchy-mode="trusted"]')).not.toBeNull();
    expect(container.querySelector('.masterMapTree')).not.toBeNull();
    const assistantButton = Array.from(container.querySelectorAll('[aria-label="Hierarchy workspace"] button'))
      .find((button) => button.textContent === 'Mapping Assistant') as HTMLButtonElement;
    act(() => assistantButton.click());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelector('[data-hierarchy-mode="assistant"]')).not.toBeNull();
    expect(container.querySelector('.masterMapTree')).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('test assistant unavailable');
    expect(loader).toHaveBeenCalledTimes(1);
  });
});
