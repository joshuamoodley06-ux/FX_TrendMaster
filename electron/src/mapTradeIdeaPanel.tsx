import React from 'react';
import {
  type ChartTradeIdea,
  type ChartTradeIdeaDraft,
  type TradeIdeaPickKind,
  computeTradeIdeaMetrics,
  draftHasAnyPoint,
  draftReadyToSave,
  inferTradeDirection,
} from './chartTradeIdeas';

type Props = {
  symbol: string;
  timeframe: string;
  draft: ChartTradeIdeaDraft;
  pickMode: TradeIdeaPickKind | null;
  setPickMode: (mode: TradeIdeaPickKind | null) => void;
  savedIdeas: ChartTradeIdea[];
  selectedIdeaId: string | null;
  setSelectedIdeaId: (id: string | null) => void;
  linkedRangeLabel: string;
  notes: string;
  setNotes: (v: string) => void;
  onClearDraft: () => void;
  onSave: () => void;
  onDelete: (id: string) => void;
  onExport: () => void;
  saving: boolean;
  shortTime: (value: any, timeframe?: string) => string;
};

const PICK_BUTTONS: { kind: TradeIdeaPickKind; label: string; title: string }[] = [
  { kind: 'entry', label: 'Entry', title: 'Click chart to set entry' },
  { kind: 'sl', label: 'SL', title: 'Click chart to set stop loss' },
  { kind: 'tp1', label: 'TP1', title: 'Click chart to set take profit 1' },
  { kind: 'tp2', label: 'TP2', title: 'Click chart to set take profit 2' },
  { kind: 'tp3', label: 'TP3', title: 'Click chart to set take profit 3' },
];

function fmtPoint(pt: { price: number; time: string } | null, shortTime: Props['shortTime'], tf: string) {
  if (!pt) return '—';
  return `${Number(pt.price).toFixed(2)} · ${shortTime(pt.time, tf)}`;
}

export function MapTradeIdeaPanel(props: Props) {
  const direction = inferTradeDirection(props.draft.entry, props.draft.sl);
  const metrics = props.draft.entry
    ? computeTradeIdeaMetrics(direction, props.draft.entry, props.draft.sl, props.draft.tp1, props.draft.tp2, props.draft.tp3)
    : null;

  return (
    <div className="rightTabPanel tradeIdeaTabPanel">
      <h3>Trade Idea</h3>
      <p className="mutedSmall">TradingView-style measure: pick Entry, SL, then TP levels on the chart. Saved ideas link to the active range/context.</p>

      <div className="tradeIdeaContextCard">
        <b>Linked context</b>
        <span>{props.linkedRangeLabel || 'No range selected'}</span>
        <em>{props.symbol} · {props.timeframe}</em>
      </div>

      <div className="tradeIdeaPickGrid">
        {PICK_BUTTONS.map(({ kind, label, title }) => (
          <button
            key={kind}
            type="button"
            className={`tradeIdeaPickBtn ${kind}${props.pickMode === kind ? ' active' : ''}`}
            title={title}
            onClick={() => props.setPickMode(props.pickMode === kind ? null : kind)}
          >
            {label}
          </button>
        ))}
      </div>

      {props.pickMode && <div className="tradeIdeaHint">Click the chart to place <b>{props.pickMode.toUpperCase()}</b>.</div>}

      <div className="tradeIdeaDraftCard">
        <div className="tradeIdeaDraftRow"><span>Direction</span><strong className={direction === 'LONG' ? 'long' : 'short'}>{direction}</strong></div>
        <div className="tradeIdeaDraftRow"><span>Entry</span><strong>{fmtPoint(props.draft.entry, props.shortTime, props.timeframe)}</strong></div>
        <div className="tradeIdeaDraftRow"><span>SL</span><strong className="sl">{fmtPoint(props.draft.sl, props.shortTime, props.timeframe)}</strong></div>
        <div className="tradeIdeaDraftRow"><span>TP1</span><strong className="tp">{fmtPoint(props.draft.tp1, props.shortTime, props.timeframe)}</strong></div>
        <div className="tradeIdeaDraftRow"><span>TP2</span><strong className="tp">{fmtPoint(props.draft.tp2, props.shortTime, props.timeframe)}</strong></div>
        <div className="tradeIdeaDraftRow"><span>TP3</span><strong className="tp">{fmtPoint(props.draft.tp3, props.shortTime, props.timeframe)}</strong></div>
        {metrics?.riskPoints != null && (
          <div className="tradeIdeaMetrics">
            <span>Risk {metrics.riskPoints.toFixed(2)} pts</span>
            {metrics.rrTp1 != null && <span>TP1 {metrics.rrTp1.toFixed(2)}R</span>}
            {metrics.rrTp2 != null && <span>TP2 {metrics.rrTp2.toFixed(2)}R</span>}
            {metrics.rrTp3 != null && <span>TP3 {metrics.rrTp3.toFixed(2)}R</span>}
          </div>
        )}
      </div>

      <label className="tradeIdeaNotes">Notes<textarea value={props.notes} onChange={(e) => props.setNotes(e.target.value)} placeholder="Setup note, invalidation context, etc." rows={3} /></label>

      <div className="tradeIdeaActions">
        <button type="button" className="tradeIdeaSaveBtn" disabled={!draftReadyToSave(props.draft) || props.saving} onClick={props.onSave}>{props.saving ? 'Saving…' : 'Save Trade Idea'}</button>
        <button type="button" className="tradeIdeaClearBtn" disabled={!draftHasAnyPoint(props.draft)} onClick={props.onClearDraft}>Clear draft</button>
        <button type="button" className="tradeIdeaExportBtn" disabled={!props.savedIdeas.length} onClick={props.onExport}>Export for Analyst</button>
      </div>

      <div className="tradeIdeaSavedList">
        <b>Saved ideas ({props.savedIdeas.length})</b>
        {!props.savedIdeas.length && <div className="emptyNarrative"><span>No saved trade ideas for this chart context yet.</span></div>}
        {props.savedIdeas.map((idea) => (
          <button
            key={idea.id}
            type="button"
            className={`tradeIdeaSavedRow${props.selectedIdeaId === idea.id ? ' active' : ''}`}
            onClick={() => props.setSelectedIdeaId(props.selectedIdeaId === idea.id ? null : idea.id)}
          >
            <span className={`dir ${idea.direction.toLowerCase()}`}>{idea.direction}</span>
            <strong>{Number(idea.entry.price).toFixed(2)} → SL {idea.sl ? Number(idea.sl.price).toFixed(2) : '—'}</strong>
            <em>{idea.analystExport.rrTp1 != null ? `${idea.analystExport.rrTp1.toFixed(2)}R TP1` : '—'} · {idea.rangeId ? `#${idea.rangeId}` : 'no range'}</em>
            <span className="tradeIdeaDelete" role="button" tabIndex={0} onClick={(e) => { e.stopPropagation(); props.onDelete(idea.id); }} title="Delete idea">×</span>
          </button>
        ))}
      </div>
    </div>
  );
}
