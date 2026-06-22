/** Inspector — permanent right column; sole host for mapping data inputs. */

import React from 'react';
import type { InspectorContextHint } from './inspectorContext';

export type InspectorTabId = 'dashboard' | 'narrative' | 'gps' | 'campaign' | 'mark' | 'seed' | 'trade';

export type InspectorTabDef = {
  id: InspectorTabId;
  shortLabel: string;
  title: string;
};

export const INSPECTOR_TABS: InspectorTabDef[] = [
  { id: 'dashboard', shortLabel: 'O', title: 'Dashboard' },
  { id: 'narrative', shortLabel: 'N', title: 'Narrative' },
  { id: 'gps', shortLabel: 'G', title: 'Hierarchy Tree' },
  { id: 'campaign', shortLabel: 'P', title: 'Campaign' },
  { id: 'mark', shortLabel: 'M', title: 'Mark Event' },
  { id: 'seed', shortLabel: 'C', title: 'Case Manager' },
  { id: 'trade', shortLabel: 'T', title: 'Trade Idea' },
];

export function inspectorTabTitle(tab: InspectorTabId): string {
  return INSPECTOR_TABS.find((t) => t.id === tab)?.title ?? 'Inspector';
}

/** Mapping tab — Structural Map must not share the render tree with Dashboard. */
export function isMappingInspectorTab(tab: InspectorTabId): boolean {
  return tab === 'mark';
}

type PanelProps = {
  activeTab: InspectorTabId;
  onTabChange: (tab: InspectorTabId) => void;
  symbol: string;
  timeframe: string;
  contextHint?: InspectorContextHint | null;
  /** Lazy tab body — only the active tab is rendered (no hidden mount bleed). */
  renderTab: (tab: InspectorTabId) => React.ReactNode;
  className?: string;
  onClosePanel?: () => void;
};

export function InspectorPanel({
  activeTab,
  onTabChange,
  symbol,
  timeframe,
  contextHint,
  renderTab,
  className = '',
  onClosePanel,
}: PanelProps) {
  return (
    <div className={`inspectorPanelInner ${className}`.trim()}>
      <nav className="inspectorTabRail" aria-label="Inspector sections">
        {INSPECTOR_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? 'active' : ''}
            title={tab.title}
            aria-current={activeTab === tab.id ? 'page' : undefined}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.shortLabel}
          </button>
        ))}
      </nav>

      <div className="inspectorBody">
        <header className="inspectorHeader">
          <div>
            <b>{inspectorTabTitle(activeTab)}</b>
            <span>{symbol} · {timeframe}</span>
            {contextHint && (
              <span className="inspectorContextHint" title={contextHint.detail}>
                {contextHint.title} · {contextHint.detail}
              </span>
            )}
          </div>
          {onClosePanel && (
            <button type="button" className="inspectorPanelCloseBtn" onClick={onClosePanel} title="Hide panel">
              Hide
            </button>
          )}
        </header>
        <div className="inspectorContent" data-active-tab={activeTab}>
          <InspectorExclusivePane activeTab={activeTab} renderTab={renderTab} />
        </div>
      </div>
    </div>
  );
}

/** Renders exactly one tab body — inactive tabs are null, not hidden. */
export function InspectorExclusivePane({
  activeTab,
  renderTab,
}: {
  activeTab: InspectorTabId;
  renderTab: (tab: InspectorTabId) => React.ReactNode;
}) {
  return (
    <div className="inspectorTabPane active" data-tab={activeTab} data-active="true">
      {renderTab(activeTab)}
    </div>
  );
}
