/** O-N-G-M-C-T floating nav rail — absolute overlay; must not affect chart layout. */

import React, { memo, useState } from 'react';
import { INSPECTOR_TABS, type InspectorTabId } from './inspectorPanel';

type NavOverlayProps = {
  activeTab: InspectorTabId;
  onTabChange: (tab: InspectorTabId) => void;
  panelOpen: boolean;
};

export const NavOverlay = memo(function NavOverlay({
  activeTab,
  onTabChange,
  panelOpen,
}: NavOverlayProps) {
  const [hoverOpen, setHoverOpen] = useState(false);
  const [pinnedOpen, setPinnedOpen] = useState(false);
  const expanded = hoverOpen || pinnedOpen;

  return (
    <div
      className={`navOverlayShell${panelOpen ? ' panelOpen' : ''}${expanded ? ' railExpanded' : ''}`}
      aria-label="O-N-G-M-C-T navigation overlay"
    >
      <div
        className={`navOverlay${expanded ? ' expanded' : ' collapsed'}`}
        onMouseEnter={() => setHoverOpen(true)}
        onMouseLeave={() => setHoverOpen(false)}
      >
        <nav className="navOverlayRail" aria-label="Inspector sections">
          {INSPECTOR_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id && panelOpen ? 'active' : ''}
              title={tab.title}
              aria-current={activeTab === tab.id && panelOpen ? 'page' : undefined}
              aria-expanded={activeTab === tab.id && panelOpen}
              onClick={() => onTabChange(tab.id)}
            >
              <span className="navOverlayIcon">{tab.shortLabel}</span>
              <span className="navOverlayLabel">{tab.title}</span>
            </button>
          ))}
        </nav>
        <button
          type="button"
          className={`navOverlayPin${pinnedOpen ? ' active' : ''}`}
          aria-pressed={pinnedOpen}
          title={pinnedOpen ? 'Collapse navigation rail' : 'Pin navigation rail open'}
          onClick={() => setPinnedOpen((v) => !v)}
        >
          {pinnedOpen ? '◂' : '▸'}
        </button>
      </div>
    </div>
  );
});
