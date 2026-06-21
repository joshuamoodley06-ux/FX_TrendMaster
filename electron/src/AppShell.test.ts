// @vitest-environment happy-dom

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  MAP_STUDIO_SHELL_GRID,
  MAP_STUDIO_SHELL_STYLE,
  MapStudioShell,
  NavRail,
} from './appShell';

describe('AppShell', () => {
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    document.body.classList.add('mapStudioPilot');
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    document.body.replaceChildren();
    document.body.className = '';
  });

  it('NavRail must be present in the DOM on component mount', () => {
    act(() => {
      root.render(
        createElement(NavRail, {
          activeTab: 'mark',
          onTabChange: () => {},
          panelOpen: false,
        }),
      );
    });

    expect(document.querySelector('.map-studio-nav-rail')).not.toBeNull();
  });

  it('MapStudioShell uses static 60px 1fr grid and always mounts NavRail', () => {
    act(() => {
      root.render(
        createElement(MapStudioShell, {
          inspectorOpen: false,
          navRail: createElement(NavRail, {
            activeTab: 'mark',
            onTabChange: () => {},
            panelOpen: false,
          }),
          chart: createElement('div', { className: 'map-studio-chart-inner' }),
          inspector: createElement('div', { className: 'inspector-host' }),
        }),
      );
    });

    const shell = document.querySelector('.map-studio-shell') as HTMLElement | null;
    expect(shell).not.toBeNull();
    expect(document.querySelector('.map-studio-nav-rail')).not.toBeNull();
    expect(MAP_STUDIO_SHELL_GRID).toBe('60px minmax(0, 1fr)');
    expect(MAP_STUDIO_SHELL_STYLE.gridTemplateColumns).toBe(MAP_STUDIO_SHELL_GRID);
    expect(shell?.style.gridTemplateColumns).toBe(MAP_STUDIO_SHELL_GRID);
  });
});
