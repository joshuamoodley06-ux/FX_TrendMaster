import React from 'react';
import type { MappingViewContext } from './mappingViewContext';

type Props = {
  viewContext: MappingViewContext;
  parentTimeframe: string | null;
  childTimeframe: string;
  parentPointCount: number;
  childPointCount: number;
  onChange: (next: MappingViewContext) => void;
  disabled?: boolean;
  isClamped?: boolean;
  canDrillDown?: boolean;
  onDrillDown?: () => void;
  onUnlockGlobalView?: () => void;
};

export function MappingViewContextSwitcher({
  viewContext,
  parentTimeframe,
  childTimeframe,
  parentPointCount,
  childPointCount,
  onChange,
  disabled = false,
  isClamped = false,
  canDrillDown = false,
  onDrillDown,
  onUnlockGlobalView,
}: Props) {
  if (!parentTimeframe) return null;

  return (
    <div className="mappingViewContextSwitcher" aria-label="View context">
      <span className="mappingViewContextLabel">View Context</span>
      {isClamped ? (
        <button
          type="button"
          className="mappingViewportPill global"
          disabled={disabled}
          onClick={() => onUnlockGlobalView?.()}
          title="Release container clamp and return to global pan/zoom"
        >
          Global View
        </button>
      ) : (
        <button
          type="button"
          className="mappingViewportPill drill"
          disabled={disabled || !canDrillDown}
          onClick={() => onDrillDown?.()}
          title={canDrillDown ? 'Clamp chart X-axis to the active container span' : 'Add draft points to define a container span first'}
        >
          Drill Down
        </button>
      )}
      <button
        type="button"
        className={viewContext === 'parent' ? 'active' : ''}
        disabled={disabled}
        title={`Parent chart · ${parentTimeframe}${parentPointCount ? ` · ${parentPointCount} draft point(s)` : ''}`}
        onClick={() => onChange('parent')}
      >
        Parent · {parentTimeframe}
        {parentPointCount > 0 ? <span className="mappingViewContextCount">{parentPointCount}</span> : null}
      </button>
      <button
        type="button"
        className={viewContext === 'child' ? 'active' : ''}
        disabled={disabled}
        title={`Child chart · ${childTimeframe}${childPointCount ? ` · ${childPointCount} draft point(s)` : ''}`}
        onClick={() => onChange('child')}
      >
        Child · {childTimeframe}
        {childPointCount > 0 ? <span className="mappingViewContextCount">{childPointCount}</span> : null}
      </button>
      {isClamped ? (
        <span className="mappingViewportClampHint" title="Chart X-axis is clamped to the active container">
          Clamped
        </span>
      ) : null}
    </div>
  );
}
