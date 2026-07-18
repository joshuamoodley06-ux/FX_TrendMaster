import React, { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  buildHierarchyCoverageRows,
  compactDate,
  deriveCoverageYearOptions,
  filterCoverageRowsByYear,
  normalizeCoverageYearRange,
  rangeInterval,
  type HierarchyCoverageRow,
  type HierarchyLayer,
} from './hierarchyCoverage';

export type HierarchyWorkspaceMode = 'structure' | 'coverage' | 'python';
type Props = { ranges: Record<string, unknown>[]; structure: ReactNode; onNavigateRange: (range: Record<string, unknown>) => void };
const LAYERS: HierarchyLayer[] = ['WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'];

function CoverageRow({ row, onNavigate }: { row: HierarchyCoverageRow; onNavigate: (range: Record<string, unknown>) => void }) {
  const [open, setOpen] = useState(false);
  const parentWindow = rangeInterval(row.parent);
  return <div className="hierarchyCoverageRow" data-parent-range-id={row.parentId}>
    <div className="hierarchyCoverageLine">
      <button type="button" className="hierarchyCoverageExpand" onClick={() => setOpen((value) => !value)} aria-expanded={open}>{open ? '▼' : '▶'}</button>
      <button type="button" className="hierarchyCoverageJump" onClick={() => onNavigate(row.parent)}>
        <span className="hierarchyCoveragePrimary">
          <b>{row.parentLayer}</b><span aria-hidden="true">|</span>
          <span>{parentWindow ? `${compactDate(parentWindow.startMs)} → ${compactDate(parentWindow.endMs)}` : 'Date unavailable'}</span>
          <span aria-hidden="true">|</span>
        </span>
        <strong>{row.coveragePercent === null ? '—' : `${row.coveragePercent}%`}</strong>
      </button>
    </div>
    {open && <div className="hierarchyCoverageGaps">
      {row.childLayer === null && <span>Micro has no configured child layer.</span>}
      {row.childLayer !== null && !row.gaps.length && <span>Full {row.childLayer.toLowerCase()} coverage.</span>}
      {row.gaps.map((gap) => <button key={`${gap.startMs}-${gap.endMs}`} type="button" onClick={() => onNavigate({ ...row.parent, range_start_time: gap.startIso, range_end_time: gap.endIso })}>
        {compactDate(gap.startMs)} <span aria-hidden="true">&lt;-----&gt;</span> {compactDate(gap.endMs)}
      </button>)}
    </div>}
  </div>;
}

export function HierarchyWorkspace({ ranges, structure, onNavigateRange }: Props) {
  const [mode, setMode] = useState<HierarchyWorkspaceMode>('structure');
  const [layer, setLayer] = useState<HierarchyLayer>('WEEKLY');
  const rows = useMemo(() => buildHierarchyCoverageRows(ranges, layer), [ranges, layer]);
  const yearOptions = useMemo(() => deriveCoverageYearOptions(rows), [rows]);
  const yearOptionsKey = yearOptions.join(',');
  const [fromYear, setFromYear] = useState<number | null>(null);
  const [toYear, setToYear] = useState<number | null>(null);
  const previousLayer = useRef<HierarchyLayer>(layer);

  useEffect(() => {
    const first = yearOptions[0] ?? null;
    const last = yearOptions[yearOptions.length - 1] ?? null;
    const layerChanged = previousLayer.current !== layer;
    previousLayer.current = layer;
    setFromYear((current) => layerChanged || current === null ? first : Math.max(first ?? current, Math.min(current, last ?? current)));
    setToYear((current) => layerChanged || current === null ? last : Math.max(first ?? current, Math.min(current, last ?? current)));
  }, [layer, yearOptionsKey]);

  const filteredRows = useMemo(() => {
    if (fromYear === null || toYear === null) return rows;
    return filterCoverageRowsByYear(rows, fromYear, toYear);
  }, [rows, fromYear, toYear]);
  const updateYears = (nextFrom: number, nextTo: number) => {
    const normalized = normalizeCoverageYearRange(nextFrom, nextTo);
    setFromYear(normalized.fromYear);
    setToYear(normalized.toYear);
  };

  return <section className="hierarchyWorkspace" data-mode={mode} aria-label="Hierarchy workspace">
    <div className="hierarchyWorkspaceModes" role="tablist" aria-label="Hierarchy modes">
      {(['structure', 'coverage', 'python'] as HierarchyWorkspaceMode[]).map((item) => <button key={item} type="button" role="tab" aria-selected={mode === item} className={mode === item ? 'active' : ''} onClick={() => setMode(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}
    </div>
    {mode === 'structure' && <div className="hierarchyWorkspaceBody structureMode">{structure}</div>}
    {mode === 'coverage' && <div className="hierarchyWorkspaceBody coverageMode">
      <div className="hierarchyCoverageFilters" role="group" aria-label="Coverage layer">{LAYERS.map((item) => <button key={item} type="button" className={layer === item ? 'active' : ''} aria-pressed={layer === item} onClick={() => setLayer(item)}>{item[0] + item.slice(1).toLowerCase()}</button>)}</div>
      {!!yearOptions.length && fromYear !== null && toYear !== null && <div className="hierarchyCoverageYears" aria-label="Coverage year range">
        <label>From year<select aria-label="From year" value={fromYear} onChange={(event) => updateYears(Number(event.target.value), toYear)}>{yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
        <span aria-hidden="true">→</span>
        <label>To year<select aria-label="To year" value={toYear} onChange={(event) => updateYears(fromYear, Number(event.target.value))}>{yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
      </div>}
      <div className="hierarchyCoverageScroll">{!filteredRows.length && <span className="caseLedgerEmpty">No {layer.toLowerCase()} ranges in this year range.</span>}{filteredRows.map((row) => <CoverageRow key={row.parentId} row={row} onNavigate={onNavigateRange} />)}</div>
    </div>}
    {mode === 'python' && <div className="hierarchyWorkspaceBody pythonMode" role="status"><b>Python analysis is dormant.</b><span>The constrained script runner and verified local store are not enabled in this foundation.</span></div>}
  </section>;
}
