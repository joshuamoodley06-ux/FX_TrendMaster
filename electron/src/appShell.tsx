/** Map Studio pilot shell — static nav | chart grid; nav rail is always mounted. */

import React from 'react';
import { NavOverlay } from './navOverlay';
import type { InspectorTabId } from './inspectorPanel';

export const MAP_STUDIO_SHELL_CLASS = 'map-studio-shell';

/** Fixed two-column shell: O-N-G-M-C-T rail (60px) + chart (1fr). Never collapses to 0px. */
export const MAP_STUDIO_SHELL_GRID = '60px minmax(0, 1fr)';

export const MAP_STUDIO_SHELL_STYLE: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: MAP_STUDIO_SHELL_GRID,
  gridTemplateRows: 'minmax(0, 1fr)',
  flex: '1 1 auto',
  minHeight: 0,
  minWidth: 0,
  width: '100%',
  overflow: 'hidden',
  position: 'relative',
};

export type NavRailProps = {
  activeTab: InspectorTabId;
  onTabChange: (tab: InspectorTabId) => void;
  panelOpen: boolean;
};

export function NavRail({
  activeTab,
  onTabChange,
  panelOpen,
}: NavRailProps) {
  return (
    <div
      className="map-studio-nav-rail"
      aria-label="F-H-C-A-Tools navigation rail"
      data-nav-rail-visible="true"
    >
      <NavOverlay activeTab={activeTab} onTabChange={onTabChange} panelOpen={panelOpen} />
    </div>
  );
}

export type MapStudioShellProps = {
  navRail: React.ReactNode;
  chart: React.ReactNode;
  inspector: React.ReactNode;
  inspectorOpen: boolean;
  className?: string;
};

export function MapStudioShell({
  navRail,
  chart,
  inspector,
  inspectorOpen,
  className = '',
}: MapStudioShellProps) {
  return (
    <div
      className={`${MAP_STUDIO_SHELL_CLASS} ${className}`.trim()}
      style={MAP_STUDIO_SHELL_STYLE}
    >
      {navRail}
      <div className="map-studio-chart">{chart}</div>
      <div
        className={`map-studio-inspector${inspectorOpen ? ' open' : ''}`}
        aria-hidden={!inspectorOpen}
      >
        {inspector}
      </div>
    </div>
  );
}
