/** Inspector — permanent right column; sole host for mapping data inputs. */

import React from 'react';
import type { InspectorContextHint } from './inspectorContext';

/** Primary rail ids + legacy ids kept for renderTab/tools migration. */
export type InspectorTabId =
  | 'seed'
  | 'gps'
  | 'campaign'
  | 'audit'
  | 'tools'
  | 'mark'
  | 'dashboard'
  | 'narrative'
  | 'trade';

export type InspectorTabDef = {
  id: InspectorTabId;
  shortLabel: string;
  title: string;
};

/** Candle-first skeleton mapping rail — five tabs only. */
export const INSPECTOR_RAIL_TABS: InspectorTabDef[] = [
  { id: 'seed', shortLabel: 'F', title: 'Folder / Case' },
  { id: 'gps', shortLabel: 'H', title: 'Hierarchy' },
  { id: 'campaign', shortLabel: 'C', title: 'Campaign' },
  { id: 'audit', shortLabel: 'A', title: 'Audit / Export' },
  { id: 'tools', shortLabel: '⚙', title: 'Tools' },
];

export const INSPECTOR_TABS = INSPECTOR_RAIL_TABS;

export function normalizeInspectorTabId(stored: string | null | undefined): InspectorTabId {
  const tab = String(stored || '').trim();
  if (tab === 'mark' || tab === 'dashboard' || tab === 'narrative' || tab === 'trade') return 'tools';
  if (INSPECTOR_RAIL_TABS.some((t) => t.id === tab)) return tab as InspectorTabId;
  return 'campaign';
}

export function inspectorTabTitle(tab: InspectorTabId): string {
  if (tab === 'mark') return 'Mark / Correction';
  if (tab === 'dashboard') return 'Dashboard';
  if (tab === 'narrative') return 'Narrative';
  if (tab === 'trade') return 'Trade Ideas';
  return INSPECTOR_RAIL_TABS.find((t) => t.id === tab)?.title ?? 'Inspector';
}

/** Chart-native marking — no dedicated Mark rail tab required. */
export function isMappingInspectorTab(tab: InspectorTabId): boolean {
  return ['campaign', 'gps', 'seed', 'audit', 'tools', 'mark'].includes(tab);
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
  const normalizedTab = normalizeInspectorTabId(activeTab);
  return (
    <div className={`inspectorPanelInner ${className}`.trim()}>
      <nav className="inspectorTabRail" aria-label="Map Studio sections">
        {INSPECTOR_RAIL_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={normalizedTab === tab.id ? 'active' : ''}
            title={tab.title}
            aria-current={normalizedTab === tab.id ? 'page' : undefined}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.shortLabel}
          </button>
        ))}
      </nav>

      <div className="inspectorBody">
        <header className="inspectorHeader">
          <div>
            <b>{inspectorTabTitle(normalizedTab)}</b>
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
        <div className="inspectorContent" data-active-tab={normalizedTab}>
          <InspectorExclusivePane activeTab={normalizedTab} renderTab={renderTab} />
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
  const normalizedTab = normalizeInspectorTabId(activeTab);
  return (
    <div className="inspectorTabPane active" data-tab={normalizedTab} data-active="true">
      {renderTab(normalizedTab)}
    </div>
  );
}
