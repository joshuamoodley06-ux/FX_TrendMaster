import React from 'react';
import { useCockpitOverview } from './cockpitOverviewContext';
import { LifecycleBrainPanel, LifecycleStatusBadge } from './lifecycleBrainPanel';

type Props = {
  variant?: 'inspector' | 'fullPage';
};

/** HTF map context + lifecycle badge for Map Studio Inspector dashboard. */
export function InspectorOverviewDashboard({ variant = 'inspector' }: Props) {
  const ctx = useCockpitOverview();
  const isInspector = variant === 'inspector';

  if (!ctx) {
    return (
      <div className="inspectorOverviewDashboard empty">
        <p className="mutedSmall">Overview context unavailable. Open Map Studio from the main cockpit shell.</p>
      </div>
    );
  }

  return (
    <div className={`inspectorOverviewDashboard ${variant}`}>
      {isInspector && (
        <p className="mutedSmall inspectorOverviewLead">
          Weekly · Daily · Intraday context while you map. Active trade sync runs in the background — no separate Live Trade page.
        </p>
      )}

      <LifecycleStatusBadge brain={ctx.brain} />

      <div className={`inspectorOverviewMaps ${isInspector ? 'inspectorOverviewMapsStack' : ''}`}>
        {ctx.overviewMaps}
      </div>

      <LifecycleBrainPanel brain={ctx.brain} compact={isInspector} />

      {!isInspector && ctx.overviewPlanning}
    </div>
  );
}
