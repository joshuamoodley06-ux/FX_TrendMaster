import React from 'react';

import {
  mappingTaskLabel,
  type CampaignStatus,
} from './mappingCampaignManager';
import { MappingViewContextSwitcher } from './mappingViewContextSwitcher';
import type { MappingViewContext } from './mappingViewContext';

type Props = {
  status: CampaignStatus;
  onContinue: () => void;
  viewContext?: MappingViewContext;
  parentTimeframe?: string | null;
  childTimeframe?: string;
  parentPointCount?: number;
  childPointCount?: number;
  onViewContextChange?: (next: MappingViewContext) => void;
  viewContextEnabled?: boolean;
  isClamped?: boolean;
  canDrillDown?: boolean;
  onDrillDown?: () => void;
  onUnlockGlobalView?: () => void;
};

export function MappingCampaignPanel({
  status,
  onContinue,
  viewContext = 'child',
  parentTimeframe = null,
  childTimeframe = 'D1',
  parentPointCount = 0,
  childPointCount = 0,
  onViewContextChange,
  viewContextEnabled = false,
  isClamped = false,
  canDrillDown = false,
  onDrillDown,
  onUnlockGlobalView,
}: Props) {
  const { nextTask, tiers, year, campaignComplete } = status;
  const yearLabel = year && year !== 'all' ? year : 'All years';

  return (
    <div className="mappingCampaignPanel">
      <div className="mappingCampaignHeader">
        <b>Campaign</b>
        {!campaignComplete && (
          <button type="button" className="mappingCampaignContinueBtn" onClick={onContinue}>
            Continue
          </button>
        )}
      </div>
      {viewContextEnabled && onViewContextChange && (
        <MappingViewContextSwitcher
          viewContext={viewContext}
          parentTimeframe={parentTimeframe}
          childTimeframe={childTimeframe}
          parentPointCount={parentPointCount}
          childPointCount={childPointCount}
          onChange={onViewContextChange}
          isClamped={isClamped}
          canDrillDown={canDrillDown}
          onDrillDown={onDrillDown}
          onUnlockGlobalView={onUnlockGlobalView}
        />
      )}
      <dl className="mappingCampaignFields">
        <div className="mappingCampaignField">
          <dt>Year</dt>
          <dd>{yearLabel}</dd>
        </div>
        <div className="mappingCampaignField">
          <dt>Next Task</dt>
          <dd className={campaignComplete ? 'campaignComplete' : 'campaignNext'}>
            {mappingTaskLabel(nextTask.task)}
          </dd>
        </div>
        <div className="mappingCampaignField">
          <dt>Current Target</dt>
          <dd>{nextTask.targetLabel || (campaignComplete ? '—' : '—')}</dd>
        </div>
        <div className="mappingCampaignField">
          <dt>Current Parent</dt>
          <dd>
            {nextTask.targetParentLayer && nextTask.targetParentId
              ? `${nextTask.targetParentLayer} #${nextTask.targetParentId}`
              : '—'}
          </dd>
        </div>
      </dl>
      {tiers.length > 0 && (
        <div className="mappingCampaignTiers">
          {tiers.map((tier) => (
            <span
              key={`${tier.parentLayer}-${tier.childLayer}`}
              className={`mappingCampaignTierBadge${tier.complete ? ' complete' : ''}`}
            >
              {tier.badgeLabel}
            </span>
          ))}
        </div>
      )}
      {nextTask.summary && !campaignComplete && (
        <p className="mappingCampaignHint mutedSmall">{nextTask.summary}</p>
      )}
      {campaignComplete && (
        <p className="mappingCampaignHint mutedSmall">{nextTask.summary}</p>
      )}
    </div>
  );
}
