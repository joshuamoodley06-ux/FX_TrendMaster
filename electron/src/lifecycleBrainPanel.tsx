import React from 'react';
import { Target } from 'lucide-react';

function parseNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

function fmtPctOrDash(v: unknown): string {
  const n = parseNum(v);
  return Number.isFinite(n) ? `${n.toFixed(2)}%` : 'Map range required';
}

function Metric({ label, value, color = '#e5e7eb' }: { label: string; value: string; color?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b style={{ color }}>{String(value)}</b>
    </div>
  );
}

/** Compact participation badge for Inspector dashboard header area. */
export function LifecycleStatusBadge({ brain }: { brain?: any }) {
  const participation = brain?.participation || {};
  const status = participation.participation_status || 'WAITING';
  const allowed = !!participation.execution_allowed;
  const direction = participation.suggested_direction || 'NONE';

  return (
    <div className={`lifecycleStatusBadge ${allowed ? 'allowed' : 'waiting'}`} role="status" aria-live="polite">
      <div className="lifecycleStatusBadgeHead">
        <Target size={16} className={allowed ? 'goldIcon' : 'blueIcon'} />
        <span>Trade Lifecycle</span>
      </div>
      <strong>{status}</strong>
      <em>{direction !== 'NONE' ? direction : participation.next_required_step || 'Awaiting map context'}</em>
    </div>
  );
}

export function LifecycleBrainPanel({ brain, compact = false }: { brain?: any; compact?: boolean }) {
  const participation = brain?.participation || {};
  const daily = brain?.daily || {};
  const intraday = brain?.intraday || {};
  const weekly = brain?.weekly || {};
  const status = participation.participation_status || 'WAITING';
  const allowed = !!participation.execution_allowed;

  return (
    <div className={`card lifecycleBrainCard ${compact ? 'lifecycleBrainCompact' : ''}`}>
      <div className="cardHeader tight">
        <div>
          <h3>Trade Lifecycle Brain</h3>
          <p>Daily direction → Intraday phase → Micro confirmation → participation.</p>
        </div>
        <Target className={allowed ? 'goldIcon' : 'blueIcon'} size={compact ? 18 : 22} />
      </div>
      <div className="metricGrid">
        <Metric label="Participation" value={status} color={allowed ? '#42e68a' : '#ffbf2f'} />
        <Metric
          label="Direction"
          value={participation.suggested_direction || 'NONE'}
          color={
            String(participation.suggested_direction).includes('BUY')
              ? '#42e68a'
              : String(participation.suggested_direction).includes('SELL')
                ? '#ff4d67'
                : '#7b8794'
          }
        />
        <Metric label="Daily Bias" value={daily.daily_bias || 'WATCHING'} color="#dbeafe" />
        <Metric label="Daily Position" value={fmtPctOrDash(daily.position_pct)} color="#dbeafe" />
        <Metric
          label="Daily Range Source"
          value={daily?.source?.range || (daily.range_low && daily.range_high ? 'map' : 'missing')}
          color="#7dd3fc"
        />
        <Metric label="Intraday" value={intraday.intraday_state || 'WAITING'} color="#00ffd0" />
        <Metric label="Retest" value={intraday.retest_status || '-'} color="#ffbf2f" />
        <Metric label="Favourable Trade" value={intraday.favourable_trade || '-'} color="#e5e7eb" />
        <Metric label="Weekly" value={weekly.weekly_state || 'CONTEXT'} color="#a78bfa" />
      </div>
      {!compact && (
        <>
          <div className="machineMessage">
            <b>Machine says:</b>
            <span>{participation.machine_message || participation.reason || 'No lifecycle snapshot yet. Save/load map state first.'}</span>
          </div>
          <div className="machineMessage mutedMessage">
            <b>Map pull:</b>
            <span>Daily range/profile derives from saved Map Settings unless Catch-Up Wizard overrides.</span>
          </div>
          <div className="machineMessage mutedMessage">
            <b>Next:</b>
            <span>{participation.next_required_step || 'Waiting for rule-chain progress.'}</span>
          </div>
        </>
      )}
      {compact && (
        <div className="machineMessage compactMachineMessage">
          <span>{participation.machine_message || participation.next_required_step || 'No lifecycle snapshot yet.'}</span>
        </div>
      )}
    </div>
  );
}
