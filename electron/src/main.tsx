import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { createRoot } from 'react-dom/client';
import { Activity, AlertTriangle, BookOpen, CheckCircle2, ChevronLeft, ChevronRight, CircleDot, Database, FileText, Map, RefreshCw, Save, Settings, Target, Zap } from 'lucide-react';
import { buildRawPayloadJson, createRawCase, saveRawEvent } from './rawMapping';
import './styles.css';

const BASE_URL = 'https://api01.apexcoastalrentals.co.za';
const DEBUG_CAMERA = false;
const SYMBOLS = ['XAUUSD', 'US500.cash'];
const ZONES = ['Ext L', 'DD', 'D', 'Fair', 'P', 'DP', 'Ext H'];
const LAYERS = ['weekly', 'daily', 'intraday'] as const;
type LayerKey = typeof LAYERS[number];
type Page = 'visual' | 'ideas' | 'live' | 'journal' | 'sql' | 'settings' | 'data' | 'brain' | 'historical' | 'mapstudio';
type CameraIntent = 'LATEST' | 'FIT_ALL' | 'CASE' | 'REPLAY' | 'RANGE' | 'RESTORE_LOCKED' | 'PRESERVE_OR_NEAREST_TIME' | 'HORIZONTAL_STRETCH' | 'VERTICAL_STRETCH' | 'NONE';
type CameraCommand = { intent: CameraIntent; token: number; targetTime?: string | null; reason?: string; scaleFactor?: number };
type VisibleCameraDomain = { start:string; end:string; priceLow:number; priceHigh:number };

type Layer = {
  layer: string;
  auto_location?: string;
  location?: string;
  position_percent?: number;
  trajectory?: string;
  objective?: string;
  discount_mitigation?: string;
  premium_mitigation?: string;
  external_low_mitigation?: string;
  external_high_mitigation?: string;
};

type TradeIdea = {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  setupType: string;
  status: string;
  weekly: string;
  daily: string;
  objective: string;
  waitingFor: string;
  invalidationPrice: string;
  riskMode: string;
  notes: string;
  createdAt: string;
};

type AnchorStatus = 'INTACT' | 'BROKEN' | 'BROKEN_RECLAIMED' | 'FAILED_RECLAIM' | 'TARGETED' | 'MITIGATED' | 'FAILED' | 'CONFIRMED';
type GraphPoint = { id: string; label: string; anchorKey?: string; zone: string; x: number; sequenceColumn?: number; price?: string; live?: boolean; status?: AnchorStatus | string; role?: string };
type MitigationLevels = Record<'discount' | 'fair_price' | 'premium', Record<'m1' | 'm2' | 'm3', { price: string; status: string; role?: string }>>;

type MapMeta = {
  profile?: string;
  deliveryState?: string;
  reactionState?: string;
  continuationState?: string;
  phaseState?: string;
  entryModel?: string;
  objective1?: string;
  objective2?: string;
  parentWeeklyMapId?: string;
  parentDailyMapId?: string;
};
type VisualLayer = {
  narrative: string;
  mapBias: 'bullish' | 'bearish' | 'manual';
  rangeHigh: string;
  rangeLow: string;
  currentZone: string;
  objectiveZone: string;
  tickStep: number;
  brokenExternal: 'EXT_H' | 'EXT_L' | 'NONE';
  brokenExternalPrice: string;
  useLiveCurrent: boolean;
  projectionX: number;
  projectionPrice: string;
  liquidityCleanUpPrice?: string;
  showLiquidityCleanUp?: boolean;
  mitigation: { extL: string; discount: string; premium: string; extH: string };
  mitigationLevels?: MitigationLevels;
  mitigationSequence?: string[];
  path: GraphPoint[];
  meta?: MapMeta;
};
type VisualStore = Record<LayerKey, VisualLayer>;

const makePoint = (label: string, zone: string, x: number, price = '', anchorKey = label.toUpperCase().replace(/[^A-Z0-9]+/g, '_')): GraphPoint => ({ id: cryptoId(), label, anchorKey, zone, x, sequenceColumn: 1, price, status: 'INTACT', role: '' });

const emptyMitigationLevels = (): MitigationLevels => ({
  discount: { m1: { price: '', status: 'WAITING' }, m2: { price: '', status: 'WAITING' }, m3: { price: '', status: 'WAITING' } },
  fair_price: { m1: { price: '', status: 'WAITING' }, m2: { price: '', status: 'WAITING' }, m3: { price: '', status: 'WAITING' } },
  premium: { m1: { price: '', status: 'WAITING' }, m2: { price: '', status: 'WAITING' }, m3: { price: '', status: 'WAITING' } },
});

const defaultVisual: VisualStore = {
  weekly: {
    narrative: 'Bullish From External Low', mapBias: 'bullish',
    rangeHigh: '5425', rangeLow: '4109', currentZone: 'D', objectiveZone: 'P', tickStep: 200, brokenExternal: 'EXT_L', brokenExternalPrice: '', useLiveCurrent: false, projectionX: 90, projectionPrice: '',
    mitigation: { extL: 'Fresh', discount: 'Fresh', premium: 'Fresh', extH: 'Fresh' },
    mitigationLevels: emptyMitigationLevels(),
    meta: { profile: 'SND_DEEP_RETRACE', deliveryState: 'TO_FAIR_PRICE', reactionState: 'FULL_RECLAIM', continuationState: 'CONTINUE_BULLISH', objective1: 'FAIR_PRICE', objective2: 'PREMIUM_M1' },
    path: [makePoint('EXT_L', 'Ext L', 10, '', 'EXT_L'), makePoint('PREV_L', 'Fair', 28, '', 'PREV_L'), makePoint('CURRENT', 'D', 44, '', 'CURRENT'), makePoint('OBJECTIVE_1', 'Fair', 72, '', 'OBJECTIVE_1'), makePoint('OBJECTIVE_2', 'P', 88, '', 'OBJECTIVE_2')],
  },
  daily: {
    narrative: 'Bearish From Deep Premium', mapBias: 'bearish',
    rangeHigh: '4778', rangeLow: '3865', currentZone: 'D', objectiveZone: 'DD', tickStep: 100, brokenExternal: 'EXT_H', brokenExternalPrice: '', useLiveCurrent: false, projectionX: 90, projectionPrice: '',
    mitigation: { extL: 'Fresh', discount: 'Fresh', premium: 'Fresh', extH: 'Fresh' },
    mitigationLevels: emptyMitigationLevels(),
    meta: { profile: 'SND_TO_SR_CONTINUATION', deliveryState: 'TO_FAIR_PRICE', reactionState: 'STRONG_REACTION', continuationState: 'CONTINUE_BEARISH', phaseState: 'P2_ACTIVE', objective1: 'FAIR_PRICE', objective2: 'DISCOUNT_M1' },
    path: [makePoint('EXT_H', 'Ext H', 10, '', 'EXT_H'), makePoint('PREV_H', 'Fair', 28, '', 'PREV_H'), makePoint('CURRENT', 'D', 56, '', 'CURRENT'), makePoint('OBJECTIVE_1', 'Fair', 72, '', 'OBJECTIVE_1'), makePoint('OBJECTIVE_2', 'DD', 88, '', 'OBJECTIVE_2')],
  },
  intraday: {
    narrative: 'Manual Intraday Delivery', mapBias: 'manual',
    rangeHigh: '4595', rangeLow: '4366', currentZone: 'Fair', objectiveZone: 'D', tickStep: 50, brokenExternal: 'NONE', brokenExternalPrice: '', useLiveCurrent: false, projectionX: 90, projectionPrice: '', liquidityCleanUpPrice: '4452.10', showLiquidityCleanUp: true,
    mitigation: { extL: 'Fresh', discount: 'Fresh', premium: 'Fresh', extH: 'Fresh' },
    mitigationLevels: emptyMitigationLevels(),
    meta: { profile: 'IMMEDIATE_CONTINUATION', phaseState: 'IMMEDIATE_ENTRY_ACTIVE', entryModel: 'IMMEDIATE_CONTINUATION_ENTRY', objective1: 'OPPOSITE_INTRADAY_EXTREME', objective2: 'RUNNER_TARGET' },
    path: [makePoint('CHOCH_HIGH', 'P', 12, '', 'CHOCH_HIGH'), makePoint('CHOCH_BREAK', 'Fair', 12, '', 'CHOCH_BREAK'), makePoint('CHOCH_LOW', 'D', 12, '', 'CHOCH_LOW'), makePoint('IMMEDIATE_ENTRY', 'D', 28, '', 'IMMEDIATE_ENTRY'), makePoint('MICRO_BOS', 'Fair', 44, '', 'MICRO_BOS'), makePoint('MICRO_BOS_SWEEP', 'D', 60, '', 'MICRO_BOS_SWEEP'), makePoint('REF_CONFIRMATION', 'Fair', 72, '', 'REF_CONFIRMATION'), makePoint('ADD_RISK_ENTRY', 'D', 82, '', 'ADD_RISK_ENTRY'), makePoint('RUNNER_TARGET', 'P', 92, '', 'RUNNER_TARGET')],
  },
};

const WEEKLY_DAILY_ANCHORS = ['EXT_H','EXT_L','PREV_H','PREV_L','FAIR_PRICE','CURRENT','OBJECTIVE_1','OBJECTIVE_2','INVALIDATION'];
const DAILY_EXTRA_ANCHORS = ['CHOCH','P1','P2','P3','P3_FAIL','NEW_P1'];
const INTRADAY_ANCHORS = ['CHOCH_HIGH','CHOCH_BREAK','CHOCH_LOW','IMMEDIATE_ENTRY','P1','P1_BOS','P2','P2_BOS','P3','P3_FAIL','NEW_P1','INTERNAL_SWEEP_LEVEL','MICRO_BOS','MICRO_BOS_SWEEP','REF_CONFIRMATION','ADD_RISK_ENTRY','SL','ADD_RISK_SL','TP1','TP2','RUNNER_TARGET','CURRENT','INVALIDATION'];
const ANCHOR_STATUS = ['INTACT','BROKEN','BROKEN_RECLAIMED','FAILED_RECLAIM','TARGETED','MITIGATED','FAILED','CONFIRMED','INVALIDATED','HELD_VALID','BROKEN_CONFIRMED'];
const WEEKLY_PROFILES = ['SND_DEEP_RETRACE','SR_SHALLOW_RETRACE','COMPRESSION','EXPANSION_NO_RETRACE','FAILED_RETRACE'];
const DAILY_PROFILES = ['SND_DEEP_RETRACE','SR_SHALLOW_RETRACE','SND_TO_SR_CONTINUATION','SR_TO_SND_CONTINUATION','SND_TO_SR_REVERSAL','SR_TO_SND_REVERSAL','FAILED_PROFILE_FLIP'];
const INTRADAY_PROFILES = ['WAITING','SND_DEEP_RETRACE_ENTRY','SR_SHALLOW_RETRACE_ENTRY','IMMEDIATE_CONTINUATION','CONFIRMED_CONTINUATION_ADD_RISK','P3_FAIL_REVERSAL','NEW_P1_PROFILE_FLIP_CONTINUATION','FAILED_PROFILE_FLIP'];
const DELIVERY_STATES = ['TO_FAIR_PRICE','TO_PREMIUM','TO_DEEP_PREMIUM','TO_DISCOUNT','TO_DEEP_DISCOUNT','TO_EXTERNAL'];
const REACTION_STATES = ['NO_REACTION','WEAK_REACTION','STRONG_REACTION','FULL_RECLAIM','FAILED_REACTION','PROFILE_FLIP'];
const CONTINUATION_STATES = ['CONTINUE_BULLISH','CONTINUE_BEARISH','ROTATE_RANGE','EXPAND_RANGE','REVERSE_RANGE'];
const PHASE_STATES = ['PRE_CHOCH','CHOCH_CONFIRMED','IMMEDIATE_ENTRY_ACTIVE','P1_ACTIVE','P1_BOS_CONFIRMED','P2_ACTIVE','P2_BOS_CONFIRMED','P3_ACTIVE','P3_FAILED','NEW_P1_ACTIVE','INTERNAL_SWEEP_CLEANUP','REF_CONFIRMATION_ACTIVE','ADD_RISK_READY','EXECUTED','INVALIDATED'];
const ENTRY_MODELS = ['IMMEDIATE_CONTINUATION_ENTRY','CONFIRMED_CONTINUATION_ADD_RISK','SND_618_PULLBACK','SR_SECOND_CANDLE','BREAKOUT_ENTRY','DAILY_OPEN_ENTRY','P3_FAIL_RECLAIM_ENTRY'];
const MITIGATION_TARGETS = ['DISCOUNT_M1','DISCOUNT_M2','DISCOUNT_M3','FAIR_PRICE_M1','FAIR_PRICE_M2','FAIR_PRICE_M3','PREMIUM_M1','PREMIUM_M2','PREMIUM_M3'];
const OBJECTIVE_TYPES = [...MITIGATION_TARGETS,'FAIR_PRICE','EXT_H','EXT_L','NEXT_HTF_OBJECTIVE','OPPOSITE_INTRADAY_EXTREME','RUNNER_TARGET','EXTENSION_ONLY'];

function anchorsForLayer(layer: LayerKey) {
  if (layer === 'intraday') return INTRADAY_ANCHORS;
  if (layer === 'daily') return [...WEEKLY_DAILY_ANCHORS, ...DAILY_EXTRA_ANCHORS];
  return WEEKLY_DAILY_ANCHORS;
}
function profilesForLayer(layer: LayerKey) {
  if (layer === 'intraday') return INTRADAY_PROFILES;
  if (layer === 'daily') return DAILY_PROFILES;
  return WEEKLY_PROFILES;
}
function matrixXFor(index: number, total: number) {
  const safeTotal = Math.max(2, total || 2);
  return clamp(10 + index * (80 / (safeTotal - 1)), 8, 92);
}
function matrixLabelFor(layer: LayerKey, index: number) {
  const labels = layer === 'intraday'
    ? ['CHOCH RANGE','ENTRY','MICRO BOS','SWEEP','REF / ADD RISK','TARGET']
    : ['EXT RANGE','PREV LEVEL','RECLAIM / REACTION','CURRENT','OBJECTIVE 1','OBJECTIVE 2'];
  return labels[Math.min(index, labels.length - 1)] || `COL ${index + 1}`;
}
function anchorColumnIndex(point: GraphPoint, index: number, total: number, layer: LayerKey) {
  const key = String(point.anchorKey || point.label || '').toUpperCase();
  if (layer === 'intraday') {
    if (key.startsWith('CHOCH')) return 0;
    if (['IMMEDIATE_ENTRY','ENTRY','SL','ADD_RISK_SL'].includes(key)) return 1;
    if (key.includes('P1') || key === 'MICRO_BOS') return 2;
    if (key.includes('P2') || key.includes('SWEEP')) return 3;
    if (key.includes('P3') || key.includes('REF') || key.includes('ADD_RISK')) return 4;
    if (key.includes('TP') || key.includes('RUNNER') || key.includes('OBJECTIVE')) return 5;
    if (key === 'CURRENT') return 4;
  }
  return Math.min(index, 5);
}
function matrixXForPoint(point: GraphPoint, index: number, total: number, layer: LayerKey) {
  return matrixXFor(anchorColumnIndex(point, index, total, layer), 6);
}
function journalReadyMap(layer: LayerKey, visual: VisualLayer) {
  return {
    timeframe: layer.toUpperCase(),
    bias: visual.mapBias,
    profile: visual.meta?.profile || '',
    delivery_state: visual.meta?.deliveryState || '',
    reaction_state: visual.meta?.reactionState || '',
    continuation_state: visual.meta?.continuationState || '',
    phase_state: visual.meta?.phaseState || '',
    entry_model: visual.meta?.entryModel || '',
    objective_1: visual.meta?.objective1 || '',
    objective_2: visual.meta?.objective2 || '',
    liquidity_cleanup_price: visual.liquidityCleanUpPrice || '',
    show_liquidity_cleanup: !!visual.showLiquidityCleanUp,
    range_high: visual.rangeHigh || '',
    range_low: visual.rangeLow || '',
    anchors: (visual.path || []).map((p, idx) => ({
      timeframe: layer.toUpperCase(),
      anchor_key: p.anchorKey || p.label || '',
      label: p.label || p.anchorKey || '',
      price: p.price || '',
      zone: p.zone || '',
      sequence_column: idx + 1,
      status: p.status || 'INTACT',
      role: p.role || ''
    }))
  };
}

function telemetryForMap(layer: LayerKey, visual: VisualLayer, livePrice?: number | null) {
  const prices = (visual.path || [])
    .map((p) => parseNum(p.price))
    .filter((n) => Number.isFinite(n)) as number[];
  const current = Number.isFinite(Number(livePrice)) ? Number(livePrice) : parseNum((visual.path || []).find(p => String(p.anchorKey || p.label || '').toUpperCase() === 'CURRENT')?.price);
  const all = Number.isFinite(current) ? [...prices, current] : prices;
  return {
    timeframe: layer.toUpperCase(),
    live_current_price: Number.isFinite(current) ? Math.round(current * 100) / 100 : null,
    live_high_watermark: all.length ? Math.round(Math.max(...all) * 100) / 100 : null,
    live_low_watermark: all.length ? Math.round(Math.min(...all) * 100) / 100 : null,
    liquidity_cleanup_price: visual.liquidityCleanUpPrice || null,
    updated_at: new Date().toISOString(),
  };
}

function App() {
  const [symbol, setSymbol] = useLocalStorage('fx_tm_symbol', 'XAUUSD');
  const [page, setPage] = useLocalStorage<Page>('fx_tm_page', 'visual');
  const [state, setState] = useState<any>(null);
  const [active, setActive] = useState<any>(null);
  const [journal, setJournal] = useState<any[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [journalSummary, setJournalSummary] = useState<any>(null);
  const [structuredJournal, setStructuredJournal] = useState<any>(null);
  const [detailedJournal, setDetailedJournal] = useState<any>(null);
  const [brain, setBrain] = useState<any>(null);
  const [ideas, setIdeas] = useLocalStorage<TradeIdea[]>('fx_tm_trade_ideas', []);
  const [selectedIdea, setSelectedIdea] = useState<string | null>(null);
  const [visuals, rawSetVisuals] = useLocalStorage<VisualStore>('fx_tm_visual_layers_v027', defaultVisual);
  const visualsSafe = useMemo(() => normalizeVisuals(visuals), [visuals]);
  const setVisuals = (v: VisualStore) => rawSetVisuals(normalizeVisuals(v));
  const [collapsed, setCollapsed] = useLocalStorage<boolean>('fx_tm_sidebar_collapsed', false);
  const [lastRefresh, setLastRefresh] = useState('');
  const [error, setError] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [showOverviewLive, setShowOverviewLive] = useLocalStorage<boolean>('fx_tm_show_overview_live_panel', false);

  const load = async () => {
    setError('');
    try {
      const [s, a, j, db, brainSnap, journalReport, structuredReport, detailedReport] = await Promise.all([
        fetch(`${BASE_URL}/state?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()),
        fetch(`${BASE_URL}/trade/active?symbol=${encodeURIComponent(symbol)}&account=challenge`).then(r => r.json()).catch(() => null),
        fetch(`${BASE_URL}/sql/trades/recent?limit=12`).then(r => r.json()).catch(() => ({ trades: [] })),
        fetch(`${BASE_URL}/sql/status`).then(r => r.json()).catch(() => null),
        fetch(`${BASE_URL}/api/v1/lifecycle/brain?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()).catch(() => null),
        fetch(`${BASE_URL}/api/v1/journal/report/summary?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()).catch(() => null),
        fetch(`${BASE_URL}/api/v1/journal/report/recent?symbol=${encodeURIComponent(symbol)}&limit=50`).then(r => r.json()).catch(() => null),
        fetch(`${BASE_URL}/api/v1/journal/trades/detailed?symbol=${encodeURIComponent(symbol)}&limit=50`).then(r => r.json()).catch(() => null),
      ]);
      setState(s); setActive(a); setJournal(j.trades || j.rows || []); setStatus(db); setBrain(brainSnap); setJournalSummary(journalReport); setStructuredJournal(structuredReport); setDetailedJournal(detailedReport); setLastRefresh(new Date().toLocaleTimeString());
    } catch (e: any) { setError(e?.message || 'Could not reach backend'); }
  };

  useEffect(() => { load(); const t = setInterval(load, 7000); return () => clearInterval(t); }, [symbol]);

  const engine = state?.engine?.htf_map || {};
  const pickedIdea = ideas.find(x => x.id === selectedIdea) || ideas[0];
  const livePrice = extractLivePrice(state, active);
  const updateVisual = (key: LayerKey, patch: Partial<VisualLayer>) => setVisuals({ ...visualsSafe, [key]: { ...visualsSafe[key], ...patch } });
  const mapStatePayload = () => {
    const telemetry = {
      weekly: telemetryForMap('weekly', visualsSafe.weekly, livePrice),
      daily: telemetryForMap('daily', visualsSafe.daily, livePrice),
      intraday: telemetryForMap('intraday', visualsSafe.intraday, livePrice),
    };
    return {
      symbol,
      version: 'electron_v032_map_derived_lifecycle' ,
      updated_by: 'electron',
      updated_from_device: 'electron',
      visual_state: visualsSafe,
      telemetry,
      layers: {
        weekly: { visual: visualsSafe.weekly, anchors: journalReadyMap('weekly', visualsSafe.weekly).anchors, meta: journalReadyMap('weekly', visualsSafe.weekly), telemetry: telemetry.weekly },
        daily: { visual: visualsSafe.daily, anchors: journalReadyMap('daily', visualsSafe.daily).anchors, meta: journalReadyMap('daily', visualsSafe.daily), telemetry: telemetry.daily },
        intraday: { visual: visualsSafe.intraday, anchors: journalReadyMap('intraday', visualsSafe.intraday).anchors, meta: journalReadyMap('intraday', visualsSafe.intraday), telemetry: telemetry.intraday },
      },
      journal_ready: {
        weekly: journalReadyMap('weekly', visualsSafe.weekly),
        daily: journalReadyMap('daily', visualsSafe.daily),
        intraday: journalReadyMap('intraday', visualsSafe.intraday),
      }
    };
  };
  const localSave = () => { localStorage.setItem('fx_tm_visual_layers_v027', JSON.stringify(visualsSafe)); localStorage.setItem('fx_tm_trade_ideas', JSON.stringify(ideas)); setSaveMsg(`Saved local draft ${new Date().toLocaleTimeString()}`); setTimeout(() => setSaveMsg(''), 2600); };
  const saveMapsToBackend = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/maps/state`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(mapStatePayload()) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `Backend save failed ${r.status}`);
      setSaveMsg(`Saved to backend ${new Date().toLocaleTimeString()}`);
    } catch (e:any) { setSaveMsg(`Backend save failed: ${e?.message || e}`); }
    setTimeout(() => setSaveMsg(''), 4200);
  };
  const loadMapsFromBackend = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/maps/state?symbol=${encodeURIComponent(symbol)}`);
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data?.ok === false) throw new Error(data?.error || `Backend load failed ${r.status}`);
      const next = data?.state?.visual_state || data?.visual_state || data?.state?.visuals || null;
      if (!next) { setSaveMsg('No backend map state found yet'); setTimeout(() => setSaveMsg(''), 3200); return; }
      setVisuals(normalizeVisuals(next));
      setSaveMsg(`Loaded backend state ${new Date().toLocaleTimeString()}`);
    } catch (e:any) { setSaveMsg(`Backend load failed: ${e?.message || e}`); }
    setTimeout(() => setSaveMsg(''), 4200);
  };

  return <div className={`appShell ${collapsed ? 'navCollapsed' : ''}`}>
    <aside className="sidebar">
      <button className="collapseBtn" onClick={() => setCollapsed(!collapsed)} title="Hide/show tabs">{collapsed ? <ChevronRight size={18}/> : <ChevronLeft size={18}/>}<span>{collapsed ? '' : 'Hide tabs'}</span></button>
      <div className="brandBlock"><div className="logoOrb">FX</div>{!collapsed && <div><h1>TrendMaster</h1><p>Electron Cockpit v0.34</p></div>}</div>
      <div className="navGroup">
        <NavItem icon={<Activity size={18}/>} label="Overview Maps" page="visual" active={page==='visual'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<Map size={18}/>} label="Map Studio" page="mapstudio" active={page==='mapstudio'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<FileText size={18}/>} label="Trade Ideas" page="ideas" active={page==='ideas'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<Target size={18}/>} label="Lifecycle Catch-Up" page="brain" active={page==='brain'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<Zap size={18}/>} label="Live Trade" page="live" active={page==='live'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<BookOpen size={18}/>} label="Journal" page="journal" active={page==='journal'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<Database size={18}/>} label="Data Collection" page="data" active={page==='data'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<BookOpen size={18}/>} label="Historical Builder" page="historical" active={page==='historical'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<Settings size={18}/>} label="Display Settings" page="settings" active={page==='settings'} collapsed={collapsed} setPage={setPage}/>
        <NavItem icon={<Database size={18}/>} label="SQL" page="sql" active={page==='sql'} collapsed={collapsed} setPage={setPage}/>
      </div>
      {!collapsed && <div className="sidebarFooter"><p className="muted">API</p><p className="apiText">{BASE_URL}</p><div className="statusDot"><span className={status?.ok ? 'dot online' : 'dot offline'} />{status?.ok ? 'SQL Online' : 'Checking SQL'}</div></div>}
    </aside>
    <main className="mainArea">
      <header className="topbar">
        <div><h2>{pageTitle(page)}</h2><p>{pageSubtitle(page)}</p></div>
        <div className="topActions"><select value={symbol} onChange={e => setSymbol(e.target.value)}>{SYMBOLS.map(s => <option key={s}>{s}</option>)}</select><button onClick={load}><RefreshCw size={16}/> Refresh</button>{page === 'settings' && <button onClick={localSave}><Save size={16}/> Save Local</button>}<span className="timePill">{saveMsg || lastRefresh || '-'}</span></div>
      </header>
      {error && <div className="errorBox"><AlertTriangle size={16}/>{error}</div>}

      {page === 'mapstudio' && <section className="singlePage"><MapStudio symbol={symbol} /></section>}

      {page === 'visual' && <section className="overviewMapsPage">
        <div className="overviewCommandRow">
          <div>
            <b>Map overview</b>
            <span>Weekly destination · Daily route · Intraday execution</span>
          </div>
          <button className={`panelToggle ${showOverviewLive ? 'active' : ''}`} onClick={() => setShowOverviewLive(!showOverviewLive)}>
            <Zap size={15}/> {showOverviewLive ? 'Hide Active Trade' : 'Show Active Trade'}
          </button>
        </div>
        <div className="mapPair topContextPair">
          <XYTrajectoryPanel title="Weekly Map" layerKey="weekly" layer={engine.weekly} visual={visualsSafe.weekly} updateVisual={updateVisual} accent="gold" livePrice={livePrice} readOnly compact/>
          <XYTrajectoryPanel title="Daily Map" layerKey="daily" layer={engine.daily} visual={visualsSafe.daily} updateVisual={updateVisual} accent="blue" livePrice={livePrice} readOnly compact/>
        </div>
        <div className="intradayHero">
          <XYTrajectoryPanel title="Intraday Execution Map" layerKey="intraday" layer={engine.macro || engine.weekly} visual={visualsSafe.intraday} updateVisual={updateVisual} accent="cyan" intraday={state?.intraday || state?.mobile_intraday} livePrice={livePrice} readOnly compact/>
        </div>
        <LifecycleBrainPanel brain={brain} />
        <div className="overviewPlanningStrip">
          <TradeIdeaPanel ideas={ideas} setIdeas={setIdeas} selectedIdea={pickedIdea} setSelectedIdea={setSelectedIdea} state={state} brain={brain} currentSymbol={symbol}/>
        </div>
        {showOverviewLive && <div className="overviewLivePopover"><LiveTradePanel data={active} idea={pickedIdea}/></div>}
      </section>}

      {page === 'ideas' && <section className="singlePage"><TradeIdeaPanel large ideas={ideas} setIdeas={setIdeas} selectedIdea={pickedIdea} setSelectedIdea={setSelectedIdea} state={state} brain={brain} currentSymbol={symbol}/></section>}
      {page === 'brain' && <section className="singlePage"><LifecycleCatchUpWizard symbol={symbol} onSaved={load} /></section>}
      {page === 'live' && <section className="singlePage"><LiveTradePanel large data={active} idea={pickedIdea}/></section>}
      {page === 'journal' && <section className="singlePage"><JournalPage rows={journal} summary={journalSummary} structured={structuredJournal} detailed={detailedJournal}/></section>}
      {page === 'data' && <section className="singlePage"><DataCollectionPage /></section>}
      {page === 'historical' && <section className="singlePage"><HistoricalLifecycleBuilder symbol={symbol} visuals={visualsSafe} /></section>}
      {page === 'sql' && <section className="singlePage"><SqlPage status={status} journal={journal} summary={journalSummary} structured={structuredJournal}/></section>}
      {page === 'settings' && <section className="singlePage"><GraphSettings visuals={visualsSafe} setVisuals={setVisuals} updateVisual={updateVisual} localSave={localSave} saveMapsToBackend={saveMapsToBackend} loadMapsFromBackend={loadMapsFromBackend}/></section>}
    </main>
  </div>;
}

function NavItem({ icon, label, page, active, collapsed, setPage }: any) { return <button className={`navItem ${active ? 'active' : ''}`} title={label} onClick={() => setPage(page)}>{icon}{!collapsed && <span>{label}</span>}</button>; }


type Candle = { symbol:string; timeframe:string; time:string; open:number; high:number; low:number; close:number; volume?:number };
type MapEvent = { id:string; event_type:string; event_name?:string; time?:string; price:number; zone?:string; zone_percent?:number; notes?:string; candle_open?:number; candle_high?:number; candle_low?:number; candle_close?:number; source?:'map'|'seed'|'auto'|'candidate'|'manual'; primitive?:string; derived_event_code?:string; movement_rule?:string; range_status_after?:string; engine_source?:string; logic_version?:string; candidate_id?:string; confidence?:string; candidate_status?:'ACCEPTED'|'REJECTED'|'EDITED'|'CANDIDATE'; meta_json?:any; structural_event?:string; layer?:string; parent_timeframe?:string; range_id?:any; active_range_id?:any; parent_range_id?:any; old_range_id?:any; new_range_id?:any; raw_event_id?:string };

type StructureLayer = 'WEEKLY'|'DAILY'|'INTRADAY'|'MICRO';
type StructuralAnchor = { price:string; time:string; candle?:Candle|null };
type StructuralRange = {
  range_id?:number|string;
  id?:number|string;
  case_id?:number|string|null;
  symbol?:string;
  structure_layer?:string;
  chart_timeframe?:string;
  source_timeframe?:string;
  parent_range_id?:number|string|null;
  parent_link_status?:string;
  range_high_price?:number|string|null;
  range_low_price?:number|string|null;
  range_high_time?:string;
  range_low_time?:string;
  range_start_time?:string;
  range_end_time?:string;
  status?:string;
};

type HTFCandidate = { id:string; event_type:string; label:string; price:number; time:string; candle:Candle; priceMode:'high'|'low'|'close'; confidence:'LOW'|'MEDIUM'|'HIGH'; reason:string; primitive:string; derived_event_code:string; movement_rule:string; range_status_after?:string; meta:any; status?:'CANDIDATE'|'ACCEPTED'|'REJECTED'|'EDITED' };

type GpsCoordinates = { story_anchor:string; anchor_class?:string; chapter:string; parent_context_mode?:string; daily_range_status?:string; lifecycle_state?:string; phase:string; phase_part:string; profile_type?:string; objective:string; current_zone:string; last_updated?:string };
type TimelineNode = { kind:string; label:string; anchor_class?:string; timeframe?:string; phase?:string; phase_part?:string; direction?:string; objective?:string; current_zone?:string; time?:string; price?:number; active?:boolean };
type GpsPayload = { ok?:boolean; status?:string; symbol?:string; timeframe?:string; coordinates?:GpsCoordinates|null };
type PlaybackFrame = { frame_index:number; id:number; story_id:number; frame_timestamp:string; parent_context_mode:string; daily_range_status:string; lifecycle_state:string; phase:string; profile_type:string; objective_code:string; current_zone:string; established_price:number; trigger_event:string; expected_next_event:string; invalidation_condition:string; lookahead_result?:string };
const MAP_TIMEFRAMES = ['MN1','W1','D1','H4','H1','M15'];
type CaseScope = 'MACRO'|'WEEKLY'|'DAILY'|'INTRADAY'|'MICRO';
function scopeToTimeframe(scope: CaseScope) { return ({ MACRO:'MN1', WEEKLY:'W1', DAILY:'D1', INTRADAY:'H1', MICRO:'M15' } as Record<CaseScope,string>)[scope] || 'D1'; }
function timeframeToScope(tf:string): CaseScope { const t=String(tf||'').toUpperCase(); if (t==='MN1') return 'MACRO'; if (t==='W1') return 'WEEKLY'; if (t==='D1') return 'DAILY'; if (t==='M15') return 'MICRO'; return 'INTRADAY'; }
function scopeLabel(scope: CaseScope) { return ({ MACRO:'Macro', WEEKLY:'Weekly', DAILY:'Daily', INTRADAY:'Intraday', MICRO:'Micro / 15m' } as Record<CaseScope,string>)[scope] || scope; }
const MAP_EVENT_TYPES = ['BOS_UP','BOS_DOWN','CHOCH_UP','CHOCH_DOWN','P1_RETEST','P1_BOS','P2_RETEST','P2_BOS','INTERNAL_SWEEP','EXTERNAL_SWEEP','INTERNAL_REJECTION_LOW','INTERNAL_REJECTION_HIGH','EXTREME_DISCOUNT_LOW','BELOW_FAIR_PRICE_LOW','ABOVE_FAIR_PRICE_HIGH','EXTREME_PREMIUM_HIGH','RECLAIM_HIGH','RECLAIM_LOW','SFD','DFS','INDUCEMENT','OBJECTIVE_HIT','RANGE_ABANDONED','NEW_RANGE','CUSTOM_INTERNAL'];

const MARKER_LIBRARY = {
  macro: [
    { title: 'Macro Range Anchors', items: [
      ['SET_MACRO_RANGE_HIGH','Set M High'], ['SET_MACRO_RANGE_LOW','Set M Low'],
    ]},
    { title: 'Macro Locations', items: [
      ['MACRO_EXTERNAL_HIGH','M Ext H'], ['MACRO_EXTERNAL_LOW','M Ext L'],
      ['MACRO_EXTREME_PREMIUM','M Ex Prem'], ['MACRO_EXTREME_DISCOUNT','M Ex Disc'],
      ['MACRO_ABOVE_FP','M Above FP'], ['MACRO_FAIR_PRICE','M FP'], ['MACRO_BELOW_FP','M Below FP'],
    ]},
  ],
  weekly: [
    { title: 'Weekly Range Anchors', items: [
      ['SET_WEEKLY_RANGE_HIGH','Set W High'], ['SET_WEEKLY_RANGE_LOW','Set W Low'],
    ]},
    { title: 'Weekly Locations', items: [
      ['WEEKLY_EXTERNAL_HIGH','W Ext H'], ['WEEKLY_EXTERNAL_LOW','W Ext L'],
      ['WEEKLY_EXTREME_PREMIUM','W Ex Prem'], ['WEEKLY_EXTREME_DISCOUNT','W Ex Disc'],
      ['WEEKLY_ABOVE_FP','W Above FP'], ['WEEKLY_FAIR_PRICE','W FP'], ['WEEKLY_BELOW_FP','W Below FP'],
    ]},
    { title: 'Weekly Reference Liquidity', items: [
      ['WEEKLY_PWH_REFERENCE','PWH Ref'], ['WEEKLY_PWL_REFERENCE','PWL Ref'],
      ['WEEKLY_PWH_SWEEP_REF_CANDLE','PWH Sweep Ref'], ['WEEKLY_PWL_SWEEP_REF_CANDLE','PWL Sweep Ref'],
      ['WEEKLY_NO_SWEEP_REF_CANDLE','W No Sweep Ref'],
    ]},
    { title: 'Weekly Events', items: [
      ['WEEKLY_REF_HIGH_ACTIVE','W Ref H'], ['WEEKLY_REF_LOW_ACTIVE','W Ref L'],
      ['WEEKLY_BOS_UP','W BOS ↑'], ['WEEKLY_BOS_DOWN','W BOS ↓'],
      ['WEEKLY_RECLAIM_REF_HIGH','W Rec Ref H'], ['WEEKLY_RECLAIM_REF_LOW','W Rec Ref L'],
      ['WEEKLY_RANGE_CONFIRMED_AFTER_BOS_UP','W Range ↑'], ['WEEKLY_RANGE_CONFIRMED_AFTER_BOS_DOWN','W Range ↓'],
      ['WEEKLY_RANGE_ABANDONED_UP','W Aband ↑'], ['WEEKLY_RANGE_ABANDONED_DOWN','W Aband ↓'],
      ['WEEKLY_CURRENT_HIGH_FORMED','W Cur H'], ['WEEKLY_CURRENT_LOW_FORMED','W Cur L'],
      ['WEEKLY_EXTERNAL_REVERSAL_ZONE','W Ext Rev Zone'], ['WEEKLY_EXTREME_REVERSAL_ZONE','W Extreme Rev Zone'],
    ]},
    { title: 'Weekly Profile', items: [
      ['PROFILE_SD_DEEP','S&D Deep'], ['PROFILE_SR_SHALLOW','S&R Shallow'], ['PROFILE_ABANDON_NO_RECLAIM','Abandon / No Reclaim'],
    ]},
    { title: 'Weekly Retracement', items: [
      ['RETRACEMENT_0_MINUS','0-'], ['RETRACEMENT_0_25','0-25'], ['RETRACEMENT_25_50','25-50'],
      ['RETRACEMENT_50_75','50-75'], ['RETRACEMENT_75_100','75-100'], ['RETRACEMENT_100_PLUS','100+'],
    ]},
  ],
  daily: [
    { title: 'Daily Range Anchors', items: [
      ['SET_DAILY_RANGE_HIGH','Set D High'], ['SET_DAILY_RANGE_LOW','Set D Low'],
    ]},
    { title: 'Daily Locations', items: [
      ['DAILY_EXTERNAL_HIGH','D Ext H'], ['DAILY_EXTERNAL_LOW','D Ext L'],
      ['DAILY_EXTREME_PREMIUM','D Ex Prem'], ['DAILY_EXTREME_DISCOUNT','D Ex Disc'],
      ['DAILY_ABOVE_FP','D Above FP'], ['DAILY_FAIR_PRICE','D FP'], ['DAILY_BELOW_FP','D Below FP'],
    ]},
    { title: 'Daily Reference Structure', items: [
      ['DAILY_REF_HIGH_ACTIVE','D Ref H'], ['DAILY_REF_LOW_ACTIVE','D Ref L'],
    ]},
    { title: 'A+ Reference Liquidity', items: [
      ['DAILY_PDH_REFERENCE','PDH Ref'], ['DAILY_PDL_REFERENCE','PDL Ref'],
      ['DAILY_PDH_SWEEP_REF_CANDLE','PDH Sweep Ref'], ['DAILY_PDL_SWEEP_REF_CANDLE','PDL Sweep Ref'],
      ['DAILY_NO_SWEEP_REF_CANDLE','No Sweep Ref'],
    ]},
    { title: 'Daily Phase', items: [
      ['PRE_CHOCH','Pre-CHoCH'], ['CHOCH_UP','CHoCH ↑'], ['CHOCH_DOWN','CHoCH ↓'],
      ['P1_RETEST','P1 Retest'], ['P1_BOS','P1 BOS'],
      ['P2_RETEST','P2 Retest'], ['P2_BOS','P2 BOS'],
      ['P3_RETEST','P3 Retest'], ['P3_FAIL','P3 Fail'],
      ['PC_CONTINUATION','PC Continuation'], ['CONTINUATION','Continuation'], ['RANGE_ABANDONED','Range Abandoned'],
    ]},
    { title: 'Daily Profile', items: [
      ['PROFILE_SD_DEEP','S&D Deep'], ['PROFILE_SR_SHALLOW','S&R Shallow'], ['PROFILE_ABANDON_NO_RECLAIM','Abandon / No Reclaim'], ['DAILY_PROFILE_CHANGE','Profile Change'],
    ]},
    { title: 'Responsible Point', items: [
      ['RESPONSIBLE_HIGH','Responsible H'], ['RESPONSIBLE_LOW','Responsible L'],
    ]},
    { title: 'Daily Range State', items: [
      ['DAILY_RANGE_CONFIRMED_AFTER_BOS_UP','D Range ↑'], ['DAILY_RANGE_CONFIRMED_AFTER_BOS_DOWN','D Range ↓'],
      ['DAILY_RANGE_ABANDONED_UP','D Aband ↑'], ['DAILY_RANGE_ABANDONED_DOWN','D Aband ↓'], ['DAILY_CURRENT_HIGH_FORMED','D Cur H'], ['DAILY_CURRENT_LOW_FORMED','D Cur L'], ['DAILY_OBJECTIVE_COMPLETE','Objective Done'],
    ]},
  ],
} as const;

const MARKER_LABELS: Record<string,string> = Object.fromEntries(
  Object.values(MARKER_LIBRARY).flat().flatMap((group:any)=>group.items.map(([code,label]:any)=>[code,label]))
);

function markerLabel(type?: string) {
  const key = String(type || '').toUpperCase();
  return MARKER_LABELS[key] || key.replace(/_/g, ' ');
}




function isExplicitRangeHighCommand(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['SET_MACRO_RANGE_HIGH', 'SET_WEEKLY_RANGE_HIGH', 'SET_DAILY_RANGE_HIGH', 'RANGE_HIGH'].includes(t);
}

function isExplicitRangeLowCommand(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['SET_MACRO_RANGE_LOW', 'SET_WEEKLY_RANGE_LOW', 'SET_DAILY_RANGE_LOW', 'RANGE_LOW'].includes(t);
}

function isRangeHighMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  // v086.11: Fib anchors must be explicit anchor commands only.
  // Structure/location events can describe the candle, but they must not steal the fib range.
  // This prevents old W/D current-high/current-low events from dragging the active fibs away
  // from the exact selected-candle high/low Josh just marked. Precision over cleverness.
  return [
    'RANGE_HIGH',
    'SET_MACRO_RANGE_HIGH', 'SET_WEEKLY_RANGE_HIGH', 'SET_DAILY_RANGE_HIGH'
  ].includes(t);
}

function isRangeLowMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  // Explicit only. If a current low/high should become the active range anchor, queue
  // Set M/W/D Low or Set M/W/D High on that same candle. No silent range theft.
  return [
    'RANGE_LOW',
    'SET_MACRO_RANGE_LOW', 'SET_WEEKLY_RANGE_LOW', 'SET_DAILY_RANGE_LOW'
  ].includes(t);
}

function isRefHighMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['REF_HIGH_TAKEN','WEEKLY_REF_HIGH_ACTIVE','WEEKLY_PWH_REFERENCE','DAILY_REF_HIGH_ACTIVE','DAILY_PDH_REFERENCE'].includes(t);
}

function isRefLowMarker(type?: string) {
  const t = String(type || '').toUpperCase();
  return ['REF_LOW_TAKEN','WEEKLY_REF_LOW_ACTIVE','WEEKLY_PWL_REFERENCE','DAILY_REF_LOW_ACTIVE','DAILY_PDL_REFERENCE'].includes(t);
}

function isRangeAnchorMarker(type?: string) {
  return isRangeHighMarker(type) || isRangeLowMarker(type);
}


function eventMs(ev?: MapEvent) {
  const ms = ev?.time ? new Date(String(ev.time)).getTime() : 0;
  return Number.isFinite(ms) ? ms : 0;
}

function latestByEventTime(items: MapEvent[]) {
  if (!items.length) return undefined;
  return [...items].sort((a:any,b:any) => eventMs(b) - eventMs(a) || String(b.id || '').localeCompare(String(a.id || '')))[0];
}

function latestRangeHighEvent(events: MapEvent[] = []) {
  const list = safeArray<MapEvent>(events);
  const explicit = list.filter(e => ['SET_MACRO_RANGE_HIGH','SET_WEEKLY_RANGE_HIGH','SET_DAILY_RANGE_HIGH'].includes(String(e?.event_type || '').toUpperCase()));
  if (explicit.length) return latestByEventTime(explicit);
  return latestByEventTime(list.filter(e => isRangeHighMarker(e?.event_type)));
}

function latestRangeLowEvent(events: MapEvent[] = []) {
  const list = safeArray<MapEvent>(events);
  const explicit = list.filter(e => ['SET_MACRO_RANGE_LOW','SET_WEEKLY_RANGE_LOW','SET_DAILY_RANGE_LOW'].includes(String(e?.event_type || '').toUpperCase()));
  if (explicit.length) return latestByEventTime(explicit);
  return latestByEventTime(list.filter(e => isRangeLowMarker(e?.event_type)));
}

function markerPriceMode(type:string): 'high'|'low'|'close' {
  const t = String(type || '').toUpperCase();
  if (t.includes('LOW') || t.includes('DISCOUNT') || t.includes('BELOW') || t.includes('PDL') || t.includes('DOWN') || t.includes('RESPONSIBLE_LOW')) return 'low';
  if (t.includes('HIGH') || t.includes('PREMIUM') || t.includes('ABOVE') || t.includes('PDH') || t.includes('UP') || t.includes('RESPONSIBLE_HIGH')) return 'high';
  return 'close';
}

function safeArray<T = any>(value: any): T[] {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}


function markerGroupsForTimeframe(tf:string) {
  const t = String(tf || '').toUpperCase();
  if (t === 'MN1') return [{ title:'Macro Context', defaultOpen:true, groups: MARKER_LIBRARY.macro }];
  if (t === 'W1') return [
    { title:'Macro Context', defaultOpen:false, groups: MARKER_LIBRARY.macro },
    { title:'Weekly Structure', defaultOpen:true, groups: MARKER_LIBRARY.weekly },
  ];
  if (t === 'D1') return [
    { title:'Macro Context', defaultOpen:false, groups: MARKER_LIBRARY.macro },
    { title:'Weekly Context', defaultOpen:false, groups: MARKER_LIBRARY.weekly },
    { title:'Daily Narrative', defaultOpen:true, groups: MARKER_LIBRARY.daily },
  ];
  return [
    { title:'Daily Narrative', defaultOpen:true, groups: MARKER_LIBRARY.daily },
  ];
}
const STORY_ANCHOR_OPTIONS = [
  'WEEKLY_REF_LOW_TAKEN','WEEKLY_REF_HIGH_TAKEN',
  'WEEKLY_DISCOUNT_REJECTION','WEEKLY_EXTREME_DISCOUNT_REJECTION','WEEKLY_EXTERNAL_LOW_REJECTION',
  'WEEKLY_PREMIUM_REJECTION','WEEKLY_EXTREME_PREMIUM_REJECTION','WEEKLY_EXTERNAL_HIGH_REJECTION',
  'DAILY_REF_LOW_TAKEN','DAILY_REF_HIGH_TAKEN','WEEKLY_CHOCH_UP','WEEKLY_CHOCH_DOWN'
];
function anchorClassLabel(anchor?: string) {
  const txt = String(anchor || '').toUpperCase();
  if (txt.includes('REF_') && txt.includes('TAKEN')) return 'LIQUIDITY';
  if (txt.includes('REJECTION')) return 'REJECTION';
  if (txt.includes('CHOCH') || txt.includes('BOS')) return 'STRUCTURE';
  return 'MANUAL';
}



function shortTime(value: any, timeframe?: string): string {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const iso = date.toISOString();
  const tf = String(timeframe || '').toUpperCase();
  if (tf === 'MN1') return iso.slice(0, 7);
  if (tf === 'W1' || tf === 'D1') return iso.slice(0, 10);
  return iso.slice(0, 16).replace('T', ' ');
}


function eventMeta(ev:any) {
  try { return typeof ev?.meta_json === 'string' ? JSON.parse(ev.meta_json) : (ev?.meta_json || {}); } catch { return ev?.meta_json || {}; }
}
function isRejectedCandidateEvent(ev:any) {
  const m = eventMeta(ev);
  return String(m?.candidate_status || ev?.candidate_status || '').toUpperCase() === 'REJECTED'
    || String(ev?.event_type || '').toUpperCase().includes('REJECTED')
    || String(ev?.event_name || '').toUpperCase().startsWith('REJECTED:');
}
function isAcceptedCandidateEvent(ev:any) {
  const m = eventMeta(ev);
  return !!m?.accepted_from_candidate || String(ev?.engine_source || '').toUpperCase().includes('HTF');
}
function caseIdOfEvent(ev:any) {
  const m = eventMeta(ev);
  return ev?.case_id ?? m?.case_id ?? null;
}
function eventInWindow(ev:any, start?:string, end?:string) {
  if (!ev?.time || !start || !end) return false;
  const ms = new Date(String(ev.time)).getTime();
  const a = new Date(String(start)).getTime();
  const b = new Date(String(end)).getTime();
  if (![ms,a,b].every(Number.isFinite)) return false;
  return ms >= Math.min(a,b) && ms <= Math.max(a,b);
}

function zonePercent(price:number, low:number, high:number) {
  if (!Number.isFinite(price) || !Number.isFinite(low) || !Number.isFinite(high) || high === low) return null;
  return ((price - low) / (high - low)) * 100;
}
function zoneLabel(percent:number|null) {
  if (percent === null || !Number.isFinite(percent)) return '-';
  // Josh range language v059:
  // <0 = External Low, 0-25 = Extreme Discount, 25-35 = Discount,
  // 35-48 = Below Fair Price, 48-56 = Fair Price,
  // 56-75 = Premium, 75-100 = Extreme Premium, >100 = External High.
  if (percent < 0) return 'External Low';
  if (percent <= 25) return 'Extreme Discount';
  if (percent <= 35) return 'Discount';
  if (percent < 48) return 'Below Fair Price';
  if (percent <= 56) return 'Fair Price';
  if (percent < 75) return 'Premium';
  if (percent <= 100) return 'Extreme Premium';
  return 'External High';
}

function prefixForTimeframe(tf:string) {
  const t = String(tf || '').toUpperCase();
  if (t === 'MN1') return 'MACRO';
  if (t === 'W1') return 'WEEKLY';
  if (t === 'D1') return 'DAILY';
  return 'HTF';
}
function isHTFTimeframe(tf:string) {
  return ['MN1','W1','D1'].includes(String(tf || '').toUpperCase());
}
function candleDirection(c?:Candle|null) {
  if (!c) return 'NONE';
  if (Number(c.close) > Number(c.open)) return 'BULLISH';
  if (Number(c.close) < Number(c.open)) return 'BEARISH';
  return 'DOJI';
}
function candleBodyPct(c:Candle) {
  const r = Math.max(0.000001, Number(c.high) - Number(c.low));
  return Math.abs(Number(c.close) - Number(c.open)) / r;
}
function candidateIdFor(tf:string, c:Candle, code:string) {
  return `${tf}_${String(c.time).replace(/[^0-9A-Za-z]+/g,'')}_${code}`;
}
function htfRangeFingerprint(tf:string, rangeLow:number, rangeHigh:number) {
  const lo = Number.isFinite(rangeLow) ? Number(rangeLow).toFixed(2) : 'NA';
  const hi = Number.isFinite(rangeHigh) ? Number(rangeHigh).toFixed(2) : 'NA';
  return `${String(tf || '').toUpperCase()}_${lo}_${hi}`;
}
function htfSuggestionLockKey(tf:string, rangeLow:number, rangeHigh:number, movementRule?:string, side?:string) {
  return `${htfRangeFingerprint(tf, rangeLow, rangeHigh)}_${String(movementRule || 'UNKNOWN').toUpperCase()}_${String(side || 'ANY').toUpperCase()}`;
}
function htfCandidateLockKey(cand:Pick<HTFCandidate,'movement_rule'|'meta'|'derived_event_code'>, tf:string, rangeLow:number, rangeHigh:number) {
  const meta:any = cand?.meta || {};
  const side = meta?.breach_side || meta?.reclaim_side || meta?.sweep_side || meta?.ref_direction || meta?.point_role || meta?.rebase_direction || cand?.derived_event_code || 'ANY';
  return htfSuggestionLockKey(tf, rangeLow, rangeHigh, cand?.movement_rule, side);
}
function latestPriorZoneCandle(candles:Candle[], idx:number, side:'HIGH'|'LOW', low:number, high:number, lookback=8) {
  const start = Math.max(0, idx - lookback);
  for (let i = idx - 1; i >= start; i--) {
    const c = candles[i];
    const pct = side === 'HIGH' ? zonePercent(c.high, low, high) : zonePercent(c.low, low, high);
    if (pct === null) continue;
    if (side === 'HIGH' && pct >= 75) return { candle:c, index:i, pct };
    if (side === 'LOW' && pct <= 25) return { candle:c, index:i, pct };
  }
  return null;
}
function eventRangeMatches(e:any, rangeLow:number, rangeHigh:number, tolerancePct=0.0025) {
  const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
  const eh = Number(meta?.range_high);
  const el = Number(meta?.range_low);
  if (!Number.isFinite(eh) || !Number.isFinite(el)) return true; // legacy/manual event: do not falsely ignore it
  const tol = Math.max(0.01, Math.abs(rangeHigh - rangeLow) * tolerancePct);
  return Math.abs(eh - rangeHigh) <= tol && Math.abs(el - rangeLow) <= tol;
}
function acceptedEventHas(events:any[], rangeLow:number, rangeHigh:number, tester:(e:any, meta:any)=>boolean) {
  return safeArray<any>(events).some((e:any) => {
    const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
    const hydrated = { ...meta, movement_rule:e?.movement_rule || meta?.movement_rule, derived_event_code:e?.derived_event_code || meta?.derived_event_code, range_status_after:e?.range_status_after || meta?.range_status_after, primitive:e?.primitive || meta?.primitive };
    return eventRangeMatches(e, rangeLow, rangeHigh) && tester(e, hydrated);
  });
}
function eventRangeMatchesStrict(e:any, rangeLow:number, rangeHigh:number, tolerancePct=0.0025) {
  const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
  const eh = Number(meta?.range_high);
  const el = Number(meta?.range_low);
  // v087.13: structural chains must be ledger-backed HTF events, not legacy/manual ghosts.
  if (!Number.isFinite(eh) || !Number.isFinite(el)) return false;
  const tol = Math.max(0.01, Math.abs(rangeHigh - rangeLow) * tolerancePct);
  return Math.abs(eh - rangeHigh) <= tol && Math.abs(el - rangeLow) <= tol;
}
function acceptedHTFEventHas(events:any[], rangeLow:number, rangeHigh:number, tester:(e:any, meta:any)=>boolean) {
  return safeArray<any>(events).some((e:any) => {
    const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
    const hydrated = { ...meta, movement_rule:e?.movement_rule || meta?.movement_rule, derived_event_code:e?.derived_event_code || meta?.derived_event_code, range_status_after:e?.range_status_after || meta?.range_status_after, primitive:e?.primitive || meta?.primitive };
    const src = String(e?.engine_source || hydrated?.engine_source || '').toUpperCase();
    const hasRule = !!String(e?.movement_rule || hydrated?.movement_rule || '').trim();
    return eventRangeMatchesStrict(e, rangeLow, rangeHigh) && (src.includes('HTF') || hasRule) && tester(e, hydrated);
  });
}
function zoneWatchActive(candles:Candle[], idx:number, side:'HIGH'|'LOW', low:number, high:number, lookback=24) {
  const start = Math.max(0, idx - lookback);
  let watchStart = -1;
  for (let i = start; i < idx; i++) {
    const c = candles[i];
    const pct = side === 'HIGH' ? zonePercent(c.high, low, high) : zonePercent(c.low, low, high);
    if (pct === null) continue;
    if (side === 'HIGH' && (pct >= 75 || c.high > high)) watchStart = watchStart < 0 ? i : watchStart;
    if (side === 'LOW' && (pct <= 25 || c.low < low)) watchStart = watchStart < 0 ? i : watchStart;
  }
  if (watchStart < 0) return null;
  const active = candles[idx];
  // Pre-ref/setup candle increments forward while the zone cycle remains active.
  // For bearish confirmation, use the latest non-bearish setup candle since the premium watch started.
  // For bullish confirmation, use the latest non-bullish setup candle since the discount watch started.
  let pre:any = null, preIdx = -1;
  for (let i = watchStart; i < idx; i++) {
    const c = candles[i];
    const dir = candleDirection(c);
    if (side === 'HIGH' && dir !== 'BEARISH') { pre = c; preIdx = i; }
    if (side === 'LOW' && dir !== 'BULLISH') { pre = c; preIdx = i; }
  }
  // Fallback to immediate prior if all candles in the watch are already the confirmation colour.
  if (!pre && idx > 0) { pre = candles[idx - 1]; preIdx = idx - 1; }
  return pre ? { candle:pre, index:preIdx, watchStart } : null;
}
function acceptedEventByRule(events:any[], rangeLow:number, rangeHigh:number, rule:string) {
  const wanted = String(rule || '').toUpperCase();
  return acceptedEventHas(events, rangeLow, rangeHigh, (e,m) => String(e?.movement_rule || m?.movement_rule || '').toUpperCase() === wanted);
}
function acceptedEventByDerived(events:any[], rangeLow:number, rangeHigh:number, derived:string) {
  const wanted = String(derived || '').toUpperCase();
  return acceptedEventHas(events, rangeLow, rangeHigh, (e,m) => String(e?.derived_event_code || e?.event_type || m?.derived_event_code || '').toUpperCase() === wanted);
}
function eventRule(e:any, m:any) { return String(e?.movement_rule || m?.movement_rule || '').toUpperCase(); }
function eventDerived(e:any, m:any) { return String(e?.derived_event_code || e?.event_type || m?.derived_event_code || '').toUpperCase(); }
function findFirstBreachIndex(candles:Candle[], endIdx:number, side:'UP'|'DOWN', rangeLow:number, rangeHigh:number) {
  for (let i = 0; i <= endIdx; i++) {
    const c = candles[i];
    if (side === 'UP' && c.high > rangeHigh) return i;
    if (side === 'DOWN' && c.low < rangeLow) return i;
  }
  return -1;
}
function computeRangeRebase(args:{candles:Candle[]; activeCandle:Candle; rangeLow:number; rangeHigh:number; direction:'UP'|'DOWN'; rangeWindow?:{start?:string;end?:string}}) {
  const {candles, activeCandle, rangeLow, rangeHigh, direction, rangeWindow} = args;
  const activeIdx = candles.findIndex(c => String(c.time) === String(activeCandle.time));
  if (activeIdx < 0) return null;
  const breachIdx = findFirstBreachIndex(candles, activeIdx, direction, rangeLow, rangeHigh);
  if (breachIdx < 0) return null;
  const startMs = rangeWindow?.start ? new Date(String(rangeWindow.start)).getTime() : NaN;
  const windowStartIdx = Number.isFinite(startMs) ? Math.max(0, candles.findIndex(c => new Date(c.time).getTime() >= startMs)) : 0;
  const startIdx = Math.max(0, Math.min(windowStartIdx < 0 ? 0 : windowStartIdx, breachIdx));
  const slice = candles.slice(startIdx, activeIdx + 1);
  if (!slice.length) return null;
  if (direction === 'DOWN') {
    let responsible = slice[0], newLow = slice[0];
    slice.forEach(c => { if (c.high > responsible.high) responsible = c; if (c.low < newLow.low) newLow = c; });
    return {
      rebase_direction:'DOWN',
      new_range_high:Number(responsible.high.toFixed(2)),
      new_range_high_time:responsible.time,
      new_range_low:Number(newLow.low.toFixed(2)),
      new_range_low_time:newLow.time,
      responsible_high_time:responsible.time,
      current_low_time:newLow.time,
      measurement_old_range:{ high:rangeHigh, low:rangeLow },
      first_breach_time:candles[breachIdx]?.time,
    };
  }
  let responsible = slice[0], newHigh = slice[0];
  slice.forEach(c => { if (c.low < responsible.low) responsible = c; if (c.high > newHigh.high) newHigh = c; });
  return {
    rebase_direction:'UP',
    new_range_high:Number(newHigh.high.toFixed(2)),
    new_range_high_time:newHigh.time,
    new_range_low:Number(responsible.low.toFixed(2)),
    new_range_low_time:responsible.time,
    responsible_low_time:responsible.time,
    current_high_time:newHigh.time,
    measurement_old_range:{ high:rangeHigh, low:rangeLow },
    first_breach_time:candles[breachIdx]?.time,
  };
}
function analyseHTFSemiAuto(args:{timeframe:string; candles:Candle[]; activeCandle:Candle|null; rangeHigh:number; rangeLow:number; rangeWindow?:{start?:string;end?:string}; events?:MapEvent[]; activeCaseId?:number|null; acceptedLocks?:string[]}) {
  const {timeframe, candles, activeCandle, rangeHigh, rangeLow} = args;
  const rawAcceptedEvents = safeArray<MapEvent>(args.events || []);
  const activeCaseId = args.activeCaseId;
  const eventCaseId = (e:any) => { try { const m = typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta_json || {}); return e?.case_id ?? m?.case_id ?? null; } catch { return e?.case_id ?? null; } };
  const acceptedEvents = activeCaseId != null ? rawAcceptedEvents.filter((e:any) => String(eventCaseId(e)) === String(activeCaseId)) : [];
  const acceptedLockSet = new Set<string>(safeArray<string>(args.acceptedLocks || []));
  const prefix = prefixForTimeframe(timeframe);
  const out:{candidates:HTFCandidate[]; state:any} = { candidates:[], state:{} };
  const tfUpper = String(timeframe || '').toUpperCase();
  const canScanBos = ['MN1','W1','D1','H4','H1','M15'].includes(tfUpper);
  if (!activeCandle || !canScanBos || !Number.isFinite(rangeHigh) || !Number.isFinite(rangeLow) || rangeHigh <= rangeLow || !candles.length) {
    out.state = { status:'WAITING_FOR_RANGE', next_watch:'Set range high and low first. Engine only watches BOS up/down.' };
    return out;
  }
  const idx = candles.findIndex(c => String(c.time) === String(activeCandle.time));
  const pctClose = zonePercent(activeCandle.close, rangeLow, rangeHigh);
  const pctHigh = zonePercent(activeCandle.high, rangeLow, rangeHigh);
  const pctLow = zonePercent(activeCandle.low, rangeLow, rangeHigh);
  const location = zoneLabel(pctClose);
  const add = (partial:Omit<HTFCandidate,'id'|'time'|'candle'|'status'> & { idCode:string }) => {
    out.candidates.push({ id: candidateIdFor(timeframe, activeCandle, partial.idCode), time: activeCandle.time, candle: activeCandle, status:'CANDIDATE', ...partial } as HTFCandidate);
  };
  const hasSessionLock = (rule:string, side:string) => acceptedLockSet.has(htfSuggestionLockKey(timeframe, rangeLow, rangeHigh, rule, side));
  const hasBosUpAccepted = acceptedHTFEventHas(acceptedEvents, rangeLow, rangeHigh, (e,m) => String(e.derived_event_code || e.event_type || '').toUpperCase() === `${prefix}_BOS_UP` || m?.movement_rule === 'STRUCTURE_BOS_UP') || hasSessionLock('STRUCTURE_BOS_UP','HIGH');
  const hasBosDownAccepted = acceptedHTFEventHas(acceptedEvents, rangeLow, rangeHigh, (e,m) => String(e.derived_event_code || e.event_type || '').toUpperCase() === `${prefix}_BOS_DOWN` || m?.movement_rule === 'STRUCTURE_BOS_DOWN') || hasSessionLock('STRUCTURE_BOS_DOWN','LOW');
  const rangeStartMs = args.rangeWindow?.start ? new Date(String(args.rangeWindow.start)).getTime() : null;
  const rangeStartIndex = rangeStartMs && Number.isFinite(rangeStartMs) ? candles.findIndex(c => new Date(c.time).getTime() >= rangeStartMs) : 0;
  const activeCandleCount = idx >= 0 ? (idx - Math.max(0, rangeStartIndex) + 1) : candles.length;
  const legalState = hasBosUpAccepted ? 'BOS_UP_SAVED' : hasBosDownAccepted ? 'BOS_DOWN_SAVED' : 'ACTIVE_RANGE';
  out.state = {
    status: legalState,
    timeframe,
    prefix,
    location,
    close_pct: pctClose === null ? null : Number(pctClose.toFixed(2)),
    high_pct: pctHigh === null ? null : Number(pctHigh.toFixed(2)),
    low_pct: pctLow === null ? null : Number(pctLow.toFixed(2)),
    candle_count: activeCandleCount,
    last_candle: activeCandle.time,
    next_watch: 'Structure-only engine: autosave BOS up/down. Sweeps, retraces, profiles and phases are analytics work later.',
    memory_locks:{ bos_up:hasBosUpAccepted, bos_down:hasBosDownAccepted }
  };
  const isM15 = tfUpper === 'M15';
  const breaksHigh = isM15 ? activeCandle.close > rangeHigh : activeCandle.high > rangeHigh;
  const breaksLow = isM15 ? activeCandle.close < rangeLow : activeCandle.low < rangeLow;
  const upRule = isM15 ? 'M15_BODY_CLOSE_BOS_UP' : 'HTF_WICK_BOS_UP';
  const downRule = isM15 ? 'M15_BODY_CLOSE_BOS_DOWN' : 'HTF_WICK_BOS_DOWN';
  if (breaksHigh && !hasBosUpAccepted) {
    add({ idCode:'BOS_UP', event_type:`${prefix}_BOS_UP`, label:`${prefix} BOS Up`, price:isM15 ? activeCandle.close : activeCandle.high, priceMode:isM15 ? 'close':'high', confidence:'HIGH', primitive:'BREACH', derived_event_code:`${prefix}_BOS_UP`, movement_rule:'STRUCTURE_BOS_UP', range_status_after:'BOS_UP_SAVED', reason:`${isM15 ? 'M15 body close' : 'Wick'} broke Range High ${rangeHigh.toFixed(2)}. Structure-only autosave.`, meta:{ breach_side:'HIGH', break_rule:upRule, range_high:rangeHigh, pct_high:pctHigh } });
  }
  if (breaksLow && !hasBosDownAccepted) {
    add({ idCode:'BOS_DOWN', event_type:`${prefix}_BOS_DOWN`, label:`${prefix} BOS Down`, price:isM15 ? activeCandle.close : activeCandle.low, priceMode:isM15 ? 'close':'low', confidence:'HIGH', primitive:'BREACH', derived_event_code:`${prefix}_BOS_DOWN`, movement_rule:'STRUCTURE_BOS_DOWN', range_status_after:'BOS_DOWN_SAVED', reason:`${isM15 ? 'M15 body close' : 'Wick'} broke Range Low ${rangeLow.toFixed(2)}. Structure-only autosave.`, meta:{ breach_side:'LOW', break_rule:downRule, range_low:rangeLow, pct_low:pctLow } });
  }
  return out;
}


function yForMapPrice(price:number, low:number, high:number) {
  if (!Number.isFinite(price) || !Number.isFinite(low) || !Number.isFinite(high) || high === low) return 50;
  return clamp(100 - ((price-low)/(high-low))*100, -18, 118);
}
const TRAJECTORY_ZONE_ORDER:any = {
  'External Low': 0,
  'Extreme Discount': 1,
  'Discount': 2,
  'Below Fair Price': 3,
  'Fair Price': 4,
  'Premium': 5,
  'Extreme Premium': 6,
  'External High': 7,
};

function autoTrajectory(candles:Candle[], low:number, high:number) {
  // Build route from actual candle travel, then COMPRESS it into meaningful route checkpoints.
  // We do NOT want one SQL/database point per candle. That creates a candle landfill.
  // Logic:
  // 1) Read intrabar travel using wick extremes.
  // 2) Convert price into Josh zone bands.
  // 3) Keep only directional milestones and major reversals.
  // Example: External Low -> Extreme Discount -> Discount -> Fair Price -> Premium -> Fair Price -> Discount.
  const raw:{time:string; price:number; zone:string; pct:number; idx:number}[] = [];
  let lastZone = '';
  const pushRaw = (time:string, price:number) => {
    const p = zonePercent(price, low, high);
    const z = zoneLabel(p);
    const idx = TRAJECTORY_ZONE_ORDER[z];
    if (z === '-' || idx === undefined || !Number.isFinite(Number(p))) return;
    if (z !== lastZone) {
      raw.push({ time, price:Number(price.toFixed(2)), zone:z, pct:Number((p ?? 0).toFixed(2)), idx });
      lastZone = z;
    }
  };

  for (const c of candles) {
    const bullish = c.close >= c.open;
    const path = bullish ? [c.low, c.high, c.close] : [c.high, c.low, c.close];
    for (const price of path) pushRaw(c.time, Number(price));
  }

  if (raw.length <= 2) return raw.map(({idx, ...p}) => p);

  const compressed:{time:string; price:number; zone:string; pct:number; idx:number}[] = [raw[0]];
  let dir = 0; // 1 = climbing through zones, -1 = falling through zones
  let extreme = raw[0].idx;

  for (let i = 1; i < raw.length; i++) {
    const p = raw[i];
    if (p.idx === extreme) continue;

    if (dir === 0) {
      dir = p.idx > extreme ? 1 : -1;
      compressed.push(p);
      extreme = p.idx;
      continue;
    }

    if (dir === 1) {
      // In an up-leg, only record new higher zones.
      if (p.idx > extreme) {
        compressed.push(p);
        extreme = p.idx;
        continue;
      }
      // Ignore tiny one-zone wiggles; start a down-leg only after a proper reversal.
      if (p.idx <= extreme - 2) {
        compressed.push(p);
        extreme = p.idx;
        dir = -1;
      }
      continue;
    }

    if (dir === -1) {
      // In a down-leg, only record new lower zones.
      if (p.idx < extreme) {
        compressed.push(p);
        extreme = p.idx;
        continue;
      }
      // Ignore tiny one-zone wiggles; start an up-leg only after a proper reversal.
      if (p.idx >= extreme + 2) {
        compressed.push(p);
        extreme = p.idx;
        dir = 1;
      }
    }
  }

  return compressed.map(({idx, ...p}) => p);
}


function candleIndexAtOrBefore(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  let idx = -1;
  for (let i=0; i<candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    if (Number.isFinite(t) && t <= cut) idx = i;
    if (Number.isFinite(t) && t > cut) break;
  }
  return Math.max(0, idx >= 0 ? idx : 0);
}

function candleIndexNearest(candles:Candle[], time?:string|null): number {
  if (!candles.length) return 0;
  if (!time) return candles.length - 1;
  const cut = new Date(String(time)).getTime();
  if (!Number.isFinite(cut)) return candles.length - 1;
  let best = 0;
  let dist = Math.abs(new Date(String(candles[0].time)).getTime() - cut);
  for (let i=1; i<candles.length; i++) {
    const t = new Date(String(candles[i].time)).getTime();
    const d = Math.abs(t - cut);
    if (Number.isFinite(d) && d < dist) { best = i; dist = d; }
  }
  return best;
}

function eventAbbrev(type:any) {
  const t = String(type || '').toUpperCase();
  const map:any = { RANGE_HIGH:'RH', RANGE_LOW:'RL', REF_HIGH_TAKEN:'RHT', REF_LOW_TAKEN:'RLT', BOS_UP:'B+', BOS_DOWN:'B-', CHOCH_UP:'C+', CHOCH_DOWN:'C-', INTERNAL_SWEEP_HIGH:'ISH', INTERNAL_SWEEP_LOW:'ISL', EXTERNAL_SWEEP_HIGH:'ESH', EXTERNAL_SWEEP_LOW:'ESL', INTERNAL_REJECTION_LOW:'IRL', INTERNAL_REJECTION_HIGH:'IRH', EXTREME_DISCOUNT_LOW:'EDL', BELOW_FAIR_PRICE_LOW:'BFL', ABOVE_FAIR_PRICE_HIGH:'AFH', EXTREME_PREMIUM_HIGH:'EPH', RECLAIM_HIGH:'RHc', RECLAIM_LOW:'RLc' };
  if (map[t]) return map[t];
  if (/^P[123]$/.test(t)) return t;
  return t.split('_').map(x=>x[0]).join('').slice(0,4) || 'EV';
}

function MapStudio({ symbol }: { symbol:string }) {
  const [timeframe, setTimeframe] = useState('D1');
  const activeTimeframeRef = useRef('D1');
  useEffect(()=>{ activeTimeframeRef.current = timeframe; }, [timeframe]);
  const [candles, setCandles] = useState<Candle[]>([]);
  // v086.13: Persist explicit range anchors locally. Without this, restart/replay can
  // fall back to old backend/default ranges and move the fibs away from Josh's
  // candle-selected anchors. The chart is not allowed to develop amnesia.
  const [rangeByTf, setRangeByTf] = useLocalStorage<Record<string,{high:string;low:string}>>('fx_tm_range_by_tf_v087_29b', {});
  const [rangeWindowByTf, setRangeWindowByTf] = useLocalStorage<Record<string,{start?:string;end?:string}>>('fx_tm_range_window_by_tf_v087_29b', {});
  // v087.16: active fib range and measurement range are separate.
  // Active range drives the visible fib/zone %. Measurement range preserves the old range
  // for retracement-depth/profile stats after a rebase. Do not let these two goblins swap hats.
  const [measurementRangeByTf, setMeasurementRangeByTf] = useLocalStorage<Record<string,{high:number;low:number;start?:string;end?:string;rebase_candidate_id?:string;preserved_for?:string}>>('fx_tm_measurement_range_by_tf_v087_16', {});
  const rangeWindow = rangeWindowByTf[timeframe] || {};
  const measurementRange = measurementRangeByTf[timeframe] || null;
  const setRangeWindow = (patch:{start?:string;end?:string}) => setRangeWindowByTf(prev=>({ ...prev, [timeframe]: { ...(prev[timeframe] || {}), ...patch }}));
  const rangeHigh = rangeByTf[timeframe]?.high || '';
  const rangeLow = rangeByTf[timeframe]?.low || '';
  const setRangeHigh = (v:string) => setRangeByTf(prev=>({ ...prev, [timeframe]: { high:v, low: prev[timeframe]?.low || '' }}));
  const setRangeLow = (v:string) => setRangeByTf(prev=>({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low:v }}));
  const timesToWindow = (times:any[]) => {
    const ms = times
      .filter(Boolean)
      .map((x:any) => new Date(String(x)).getTime())
      .filter((x:number) => Number.isFinite(x));
    if (!ms.length) return null;
    return { start: new Date(Math.min(...ms)).toISOString(), end: new Date(Math.max(...ms)).toISOString() };
  };
  const [eventType, setEventType] = useState('INTERNAL_SWEEP');
  const [eventName, setEventName] = useState('');
  const [eventsByTf, setEventsByTf] = useState<Record<string,MapEvent[]>>({});
  const eventsByTfRef = useRef<Record<string,MapEvent[]>>({});
  const events = safeArray<MapEvent>(eventsByTf?.[timeframe]);
  useEffect(()=>{ eventsByTfRef.current = eventsByTf; }, [eventsByTf]);
  const setEventsForTf = (updater: MapEvent[] | ((prev:MapEvent[])=>MapEvent[])) => setEventsByTf(prev=>{
    const current = safeArray<MapEvent>(prev?.[timeframe]);
    const next = typeof updater === 'function' ? (updater as any)(current) : updater;
    const all = { ...prev, [timeframe]: next };
    eventsByTfRef.current = all;
    return all;
  });
  const [message, setMessage] = useState('D3 Map Canvas ready. Click Candle mode lets you mark Range H/L, reference highs/lows, BOS and sweeps without wrestling tiny handles.');
  const [loading, setLoading] = useState(false);
  const [toolMode, setToolMode] = useState<'inspect'|'plot'|'drag'|'range'|'select'>('inspect');
  const [scaleMode, setScaleMode] = useState<'auto'|'range'>('auto');
  const [cursor, setCursor] = useState<{time?:string; price?:number; zone?:string; pct?:number; ohlc?:Candle|null}|null>(null);
  const [candleMenu, setCandleMenu] = useState<{x:number;y:number;candle:Candle;price:number}|null>(null);
  const [selectedCandle, setSelectedCandle] = useState<Candle|null>(null);
  const [selectedCandlePoint, setSelectedCandlePoint] = useState<{price:number; clientX?:number; clientY?:number}|null>(null);
  const [pendingMarkerRoles, setPendingMarkerRoles] = useState<string[]>([]);
  const [jumpDate, setJumpDate] = useState('');
  const [jumpToken, setJumpToken] = useState(0);
  const [fitToken, setFitToken] = useState(0);
  const [gpsMode, setGpsMode] = useState<'mock'|'active'>('active');
  const [gps, setGps] = useState<GpsPayload|null>(null);
  const [gpsTimeline, setGpsTimeline] = useState<TimelineNode[]>([]);
  const [gpsStoryAnchor, setGpsStoryAnchor] = useState('WEEKLY_REF_LOW_TAKEN');
  const [gpsChapter, setGpsChapter] = useState('DAILY_BOS_UP');
  const [gpsPhaseNumber, setGpsPhaseNumber] = useState('P1');
  const [gpsPhasePart, setGpsPhasePart] = useState('RETEST');
  const [gpsObjective, setGpsObjective] = useState('DAILY_PREMIUM');
  const [gpsCurrentZone, setGpsCurrentZone] = useState('DAILY_DISCOUNT');
  const [gpsParentMode, setGpsParentMode] = useState('WEEKLY_ACTIVE_PARENT');
  const [gpsDailyRangeStatus, setGpsDailyRangeStatus] = useState('DAILY_RANGE_ACTIVE');
  const [gpsLifecycleState, setGpsLifecycleState] = useState('EXPANSION');
  const [gpsProfileType, setGpsProfileType] = useState('NO_RECLAIM_CONTINUATION_PROFILE');
  const [gpsTriggerEvent, setGpsTriggerEvent] = useState('DAILY_BOS_UP_RECLAIM');
  const [gpsExpectedNextEvent, setGpsExpectedNextEvent] = useState('PENDING_MARKET_DELIVERY');
  const [gpsInvalidationCondition, setGpsInvalidationCondition] = useState('MANUAL_INVALIDATION_REQUIRED');
  const [gpsStoryId, setGpsStoryId] = useState('');
  const [gpsChapterId, setGpsChapterId] = useState('');
  const [playbackStoryId, setPlaybackStoryId] = useState('3');
  const [playbackFrames, setPlaybackFrames] = useState<PlaybackFrame[]>([]);
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [replayMode, setReplayMode] = useState(false);
  const [playbackPlaying, setPlaybackPlaying] = useState(false);
  const [rightDeckTab, setRightDeckTab] = useState<'narrative'|'gps'|'mark'|'seed'>('narrative');
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false);
  const [markWorkspaceMode, setMarkWorkspaceMode] = useLocalStorage<'htf'|'manual'|'case'>('fx_tm_mark_workspace_mode_v087_9', 'htf');
  const [topRibbonCollapsed, setTopRibbonCollapsed] = useLocalStorage<boolean>('fx_tm_top_ribbon_collapsed_v087_24', false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  // v087.27: camera state is now user-owned. Timeframe toggles should not throw the chart around like a shopping trolley.
  const [cameraMode, setCameraMode] = useLocalStorage<'AUTO'|'LOCKED'|'CASE'|'REPLAY'>('fx_tm_camera_mode_v087_27', 'CASE');
  const [cameraDomainByCaseTf, setCameraDomainByCaseTf] = useLocalStorage<Record<string,{start:string;end:string}>>('fx_tm_camera_domain_v087_27', {});
  const [cameraPriceDomainByCaseTf, setCameraPriceDomainByCaseTf] = useLocalStorage<Record<string,{low:number;high:number}>>('fx_tm_camera_price_domain_v087_31', {});
  const [candleWidthScale, setCandleWidthScale] = useLocalStorage<number>('fx_tm_candle_width_scale_v087_27', 1);
  const [priceZoomScale, setPriceZoomScale] = useLocalStorage<number>('fx_tm_price_zoom_scale_v087_27', 1);
  const candleLoadSeqRef = useRef(0);
  const pendingCameraIntentRef = useRef<{intent:CameraIntent; targetTime?:string|null; reason?:string}>({ intent:'LATEST', reason:'initial-load' });
  const visibleCameraDomainRef = useRef<VisibleCameraDomain|null>(null);
  const [cameraCommand, setCameraCommand] = useState<CameraCommand>({ intent:'NONE', token:0 });
  const cameraLog = (...args:any[]) => { if (DEBUG_CAMERA) console.log('[camera]', ...args); };
  const clampScale = (v:number) => Math.max(0.35, Math.min(4, Number(v) || 1));
  const bumpCandleWidth = (delta:number) => {
    const factor = delta > 0 ? 1.18 : 1 / 1.18;
    setCandleWidthScale(v => Number(clampScale((Number(v)||1) + delta).toFixed(2)));
    applyCameraCommand('HORIZONTAL_STRETCH', null, delta > 0 ? 'manual-W-plus' : 'manual-W-minus', factor);
  };
  const bumpPriceZoom = (delta:number) => {
    const factor = delta > 0 ? 1.18 : 1 / 1.18;
    setPriceZoomScale(v => Number(clampScale((Number(v)||1) + delta).toFixed(2)));
    applyCameraCommand('VERTICAL_STRETCH', null, delta > 0 ? 'manual-H-plus' : 'manual-H-minus', factor);
  };
  const resetCameraScale = () => { setCandleWidthScale(1); setPriceZoomScale(1); setFitToken(x=>x+1); };
  const autoSavedBosIdsRef = useRef<Set<string>>(new Set());

  // v087.26: Full Chart is a real workspace mode. Re-fit after the DOM changes so the camera does not
  // inherit the smaller board dimensions like a cursed little postage stamp.
  useEffect(()=>{
    if (!chartFullscreen) return;
    setWorkspacePanelOpen(false);
    if (cameraMode === 'LOCKED') return;
    const intent:CameraIntent = cameraMode === 'CASE' ? 'CASE' : cameraMode === 'REPLAY' ? 'REPLAY' : 'PRESERVE_OR_NEAREST_TIME';
    const targetTime = selectedCandle?.time || candleReplayCursorTime || replayCandle?.time || null;
    const t = window.setTimeout(()=>applyCameraCommand(intent, targetTime, 'fullscreen-layout-ready'), 120);
    return () => window.clearTimeout(t);
  }, [chartFullscreen]);

  // Full candle-by-candle replay: this is separate from MOS playback_frames.
  // It rewinds the actual candle stream so Josh can mark HTF/Daily anchors at the correct historical point.
  const [candleReplayMode, setCandleReplayMode] = useState(false);
  const [candleReplayIndex, setCandleReplayIndex] = useState(0);
  // v087.22: one master replay cursor time drives every timeframe. W1 back one candle should
  // hide all D1/H1/M15 candles newer than that weekly timestamp, otherwise replay leaks future data.
  const [candleReplayCursorTime, setCandleReplayCursorTime] = useLocalStorage<string|null>('fx_tm_replay_cursor_time_v087_22', null);
  const [candleReplayPlaying, setCandleReplayPlaying] = useState(false);
  const [candleReplaySpeedMs, setCandleReplaySpeedMs] = useState(550);
  const [seedName, setSeedName] = useState('XAUUSD Case');
  const [seedNotes, setSeedNotes] = useState('');
  const [seedAnchors, setSeedAnchors] = useState<any>({});
  const [seedIdeas, setSeedIdeas] = useState<any[]>([]);
  const [caseSaving, setCaseSaving] = useState(false);
  const [caseSavedNotice, setCaseSavedNotice] = useState('');
  const [activeCaseId, setActiveCaseId] = useLocalStorage<number|null>('fx_tm_active_case_id_v087_29b', null);
  // v087.29c: raw mapping cases are UUID strings stored in raw_mapping_cases.
  // Keep this separate from legacy MOS numeric case ids so Case Save stops dragging old event bundles along.
  const [rawActiveCaseId, setRawActiveCaseId] = useLocalStorage<string>('fx_tm_raw_active_case_id_v087_29c', '');
  const [activeCaseLabel, setActiveCaseLabel] = useLocalStorage<string>('fx_tm_active_case_label_v086_16', '');
  const activeCaseDisplayId = rawActiveCaseId || (activeCaseId ? String(activeCaseId) : '');
  const getCurrentMappingCaseRef = () => {
    const rawId = String(rawActiveCaseId || '').trim();
    if (rawId) {
      return {
        case_id: null as number | null,
        raw_case_id: rawId,
        case_ref: `raw:${rawId}`,
        label: activeCaseLabel || `Raw ${rawId.slice(0, 8)}`,
        hasCase: true,
      };
    }
    const numericId = activeCaseId === null || activeCaseId === undefined ? null : Number(activeCaseId);
    if (Number.isFinite(numericId) && numericId !== null) {
      return {
        case_id: numericId,
        raw_case_id: null as string | null,
        case_ref: `case:${numericId}`,
        label: activeCaseLabel || `Case #${numericId}`,
        hasCase: true,
      };
    }
    return {
      case_id: null as number | null,
      raw_case_id: null as string | null,
      case_ref: null as string | null,
      label: null as string | null,
      hasCase: false,
    };
  };
  const appendMappingCaseParams = (params: URLSearchParams, ref = getCurrentMappingCaseRef()) => {
    if (ref.case_id !== null) params.set('case_id', String(ref.case_id));
    if (ref.raw_case_id) params.set('raw_case_id', ref.raw_case_id);
    if (ref.case_ref) params.set('case_ref', ref.case_ref);
    return params;
  };
  const cameraKey = `${activeCaseDisplayId || 'global'}_${timeframe}`;
  const lockedCameraDomain = cameraDomainByCaseTf[cameraKey] || null;
  const caseSaveInFlightRef = useRef<Set<string>>(new Set());
  const [bundleSaving, setBundleSaving] = useState(false);
  const [rawMarkSaving, setRawMarkSaving] = useState(false);
  const [structureLayer, setStructureLayer] = useLocalStorage<StructureLayer>('fx_tm_structure_layer_phase3', 'WEEKLY');
  const [sourceTimeframe, setSourceTimeframe] = useLocalStorage<string>('fx_tm_structure_source_tf_phase3', 'W1');
  const [structuralSaving, setStructuralSaving] = useState(false);
  const [structuralRanges, setStructuralRanges] = useState<StructuralRange[]>([]);
  const [savedStructuralRanges, setSavedStructuralRanges] = useState<StructuralRange[]>([]);
  const [lastSavedRangeConfirmation, setLastSavedRangeConfirmation] = useState<any>(null);
  const [selectedParentRangeId, setSelectedParentRangeId] = useLocalStorage<string>('fx_tm_selected_parent_range_id_phase3', '');
  const [activeStructuralRangeId, setActiveStructuralRangeId] = useState<string>('');
  const [rhAnchor, setRhAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [rlAnchor, setRlAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [bhAnchor, setBhAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [blAnchor, setBlAnchor] = useState<StructuralAnchor>({ price:'', time:'' });
  const [quickEventSaving, setQuickEventSaving] = useState(false);
  const [lastSavedQuickEvent, setLastSavedQuickEvent] = useState<any>(null);
  const [quickEventHistory, setQuickEventHistory] = useState<any[]>([]);
  const [structuralRangeDraftDirty, setStructuralRangeDraftDirty] = useState(false);
  const [structuralBosDraftDirty, setStructuralBosDraftDirty] = useState(false);
  const [hierarchyAudit, setHierarchyAudit] = useState<any>(null);
  const [caseScope, setCaseScope] = useState<CaseScope>(() => timeframeToScope(timeframe));
  useEffect(()=>{ setCaseScope(timeframeToScope(timeframe)); }, [timeframe]);
  const [historyMarkMode, setHistoryMarkMode] = useLocalStorage<string>('fx_tm_history_mark_mode_v087_17', 'OFF');
  const [showRejectedMarks, setShowRejectedMarks] = useLocalStorage<boolean>('fx_tm_show_rejected_candidate_marks_v087_17', false);
  const [sessionEventIds, setSessionEventIds] = useState<Set<string>>(() => new Set());
  const [htfCandidates, setHtfCandidates] = useState<HTFCandidate[]>([]);
  const [htfRejectedCandidateIds, setHtfRejectedCandidateIds] = useLocalStorage<string[]>('fx_tm_htf_rejected_candidates_v087_8', []);
  const [htfAcceptedSuggestionLocks, setHtfAcceptedSuggestionLocks] = useLocalStorage<string[]>('fx_tm_htf_accepted_suggestion_locks_v087_16', []);
  const [htfStateNotes, setHtfStateNotes] = useLocalStorage<Record<string,any>>('fx_tm_htf_state_notes_v087_8', {});

  const currentPlaybackFrame = playbackFrames[playbackIndex] || null;
  const effectiveReplayIndex = useMemo(() => {
    if (!candles.length) return 0;
    if (candleReplayMode && candleReplayCursorTime) return candleIndexAtOrBefore(candles, candleReplayCursorTime);
    return clamp(candleReplayIndex, 0, candles.length - 1);
  }, [candles, candleReplayMode, candleReplayCursorTime, candleReplayIndex]);
  const replayCandle = candles.length ? candles[clamp(effectiveReplayIndex, 0, candles.length - 1)] : null;
  const activeReplayCandle = selectedCandle || replayCandle;
  const visibleCandles = useMemo(() => {
    if (!candleReplayMode || !candles.length || !replayCandle) return candles;
    const cut = new Date(String(replayCandle.time)).getTime();
    return candles.filter(c => new Date(String(c.time)).getTime() <= cut);
  }, [candles, candleReplayMode, replayCandle?.time]);
  const mapEventsVisibleToReplay = useMemo(() => {
    if (!candleReplayMode || !replayCandle) return events;
    const cut = new Date(replayCandle.time).getTime();
    return events.filter(e => !e.time || new Date(String(e.time)).getTime() <= cut);
  }, [events, candleReplayMode, replayCandle?.time]);



  const seedIdeaEvents = useMemo<MapEvent[]>(() => {
    const out:MapEvent[] = [];
    const cut = candleReplayMode && replayCandle ? new Date(replayCandle.time).getTime() : null;
    const pushAnchor = (idea:any, key:string, label:string) => {
      const price = parseNum(idea?.[key]);
      if (!Number.isFinite(price)) return;
      const t = idea?.[`${key}_time`] || idea?.replay_candle_time;
      if (!t) return;
      const ms = new Date(String(t)).getTime();
      if (cut && Number.isFinite(cut) && Number.isFinite(ms) && ms > cut) return;
      out.push({
        id: `seed_${idea.id}_${key}`,
        source: 'seed',
        event_type: label,
        event_name: label,
        time: String(t),
        price: Number(price),
        notes: idea?.seed_name || 'Case',
      });
    };
    for (const idea of seedIdeas || []) {
      pushAnchor(idea, 'weekly_high', 'SEED_WH');
      pushAnchor(idea, 'weekly_low', 'SEED_WL');
      pushAnchor(idea, 'daily_high', 'SEED_DH');
      pushAnchor(idea, 'daily_low', 'SEED_DL');
    }
    return out;
  }, [seedIdeas, candleReplayMode, replayCandle?.time]);

  const structuralDraftEvents = useMemo<MapEvent[]>(() => {
    const out:MapEvent[] = [];
    const pushDraft = (anchor:StructuralAnchor, type:'BH'|'BL', name:string) => {
      if (!anchor.price || !anchor.time) return;
      out.push({
        id: `structural_draft_${type}_${timeframe}`,
        source: 'candidate',
        event_type: type,
        event_name: `${name} Draft`,
        time: anchor.time,
        price: Number(anchor.price),
        notes: 'Unsaved structural draft marker',
        candidate_status: 'CANDIDATE',
        meta_json: {
          draft_only: true,
          structure_layer: structureLayer,
          source_timeframe: sourceTimeframe,
          chart_timeframe: timeframe,
        },
      });
    };
    pushDraft(bhAnchor, 'BH', 'Break High');
    pushDraft(blAnchor, 'BL', 'Break Low');
    return out;
  }, [bhAnchor.price, bhAnchor.time, blAnchor.price, blAnchor.time, structureLayer, sourceTimeframe, timeframe]);

  const visibleEvents = useMemo(() => {
    // v087.17: Stored does not mean displayed. The database can remember everything;
    // the chart should only show the slice that helps the current mapping decision.
    const mapRows = safeArray<MapEvent>(mapEventsVisibleToReplay);
    const mode = String(historyMarkMode || 'ACTIVE_RANGE').toUpperCase();
    const selectedMs = (selectedCandle?.time || replayCandle?.time) ? new Date(String(selectedCandle?.time || replayCandle?.time)).getTime() : NaN;
    const nearbyStart = Number.isFinite(selectedMs) ? selectedMs - 1000 * 60 * 60 * 24 * 7 * 12 : NaN; // broad enough for W1/D1 replay without needing candle indexes here
    const nearbyEnd = Number.isFinite(selectedMs) ? selectedMs + 1000 * 60 * 60 * 24 * 7 * 12 : NaN;
    const filtered = mapRows.filter((e:any) => {
      if (!showRejectedMarks && isRejectedCandidateEvent(e)) return false;
      if (mode === 'OFF') return false;
      if (mode === 'SESSION') return sessionEventIds.has(String(e?.id));
      if (mode === 'ACTIVE_RANGE') return !rangeWindow.start || !rangeWindow.end ? sessionEventIds.has(String(e?.id)) : eventInWindow(e, rangeWindow.start, rangeWindow.end);
      if (mode === 'ACTIVE_CASE') {
        // v087.18b reload-safe guard: visibleEvents is computed before the case ledger memo is declared.
        // Do not reference activeCaseLedger here or the renderer can crash on cold boot.
        const eventCase = caseIdOfEvent(e);
        return !!(activeCaseId && eventCase != null && String(eventCase) === String(activeCaseId));
      }
      if (mode === 'NEARBY') {
        const ms = new Date(String(e?.time || '')).getTime();
        return Number.isFinite(ms) && Number.isFinite(nearbyStart) && ms >= nearbyStart && ms <= nearbyEnd;
      }
      return true; // ALL
    });
    return [...filtered, ...structuralDraftEvents];
  }, [mapEventsVisibleToReplay, structuralDraftEvents, historyMarkMode, showRejectedMarks, sessionEventIds, rangeWindow.start, rangeWindow.end, activeCaseId, selectedCandle?.time, replayCandle?.time]);
  const narrativeFacts = useMemo(() => {
    return (visibleEvents || [])
      .filter((e:any) => e?.source !== 'seed' && e?.event_type)
      .map((e:any) => ({
        ...e,
        _ms: e.time ? new Date(String(e.time)).getTime() : 0,
        _label: markerLabel(e.event_type || e.event_name),
      }))
      .sort((a:any,b:any) => (a._ms || 0) - (b._ms || 0) || String(a.id).localeCompare(String(b.id)));
  }, [visibleEvents]);


  const eventLedgerRows = useMemo(() => {
    const rows = safeArray<MapEvent>(eventsByTf?.[timeframe])
      .filter((e:any) => e?.event_type && e?.time)
      .map((e:any) => ({
        ...e,
        _ms: new Date(String(e.time)).getTime(),
        _label: markerLabel(e.event_type || e.event_name),
      }))
      .sort((a:any,b:any) => (a._ms || 0) - (b._ms || 0) || String(a.id).localeCompare(String(b.id)));
    return rows;
  }, [eventsByTf, timeframe]);

  const rangeCompilerPreview = useMemo(() => {
    const tfRange = rangeByTf[timeframe] || {};
    const tfWindow = rangeWindowByTf[timeframe] || {};
    const rows = safeArray<MapEvent>(eventLedgerRows);
    const rangeHighEvents = rows.filter((e:any)=>isExplicitRangeHighCommand(e?.event_type));
    const rangeLowEvents = rows.filter((e:any)=>isExplicitRangeLowCommand(e?.event_type));
    const latestHigh = rangeHighEvents[rangeHighEvents.length - 1];
    const latestLow = rangeLowEvents[rangeLowEvents.length - 1];
    return {
      high: tfRange.high || (latestHigh ? Number(latestHigh.price).toFixed(2) : ''),
      highTime: latestHigh?.time || tfWindow.end || '',
      low: tfRange.low || (latestLow ? Number(latestLow.price).toFixed(2) : ''),
      lowTime: latestLow?.time || tfWindow.start || '',
      eventCount: rows.length,
      highCount: rangeHighEvents.length,
      lowCount: rangeLowEvents.length,
    };
  }, [eventLedgerRows, rangeByTf, rangeWindowByTf, timeframe]);

  const jumpToLedgerEvent = (ev:any) => {
    if (!ev?.time) return;
    const idx = candles.findIndex(c => String(c.time) === String(ev.time));
    if (idx >= 0) {
      setCandleReplayFrame(idx);
      setSelectedCandle(candles[idx]);
      setSelectedCandlePoint({ price: Number(ev.price) || Number(candles[idx].close) });
      setWorkspacePanelOpen(true);
      setMessage(`Jumped to ${markerLabel(ev.event_type)} · ${shortTime(ev.time, timeframe)}. Tiny miracle: the ledger knows where it lives.`);
    } else {
      setJumpDate(String(ev.time).slice(0,10));
      setJumpToken(x=>x+1);
      setMessage(`Jumping near ${shortTime(ev.time, timeframe)} from ledger row.`);
    }
  };

  const autoCaseAnchors = useMemo(() => {
    const all = Object.values(eventsByTf || {}).flatMap((v:any)=>safeArray<MapEvent>(v)).filter(Boolean) as MapEvent[];
    const latest = (patterns: RegExp[]) => [...all]
      .filter((e:any) => patterns.some(rx => rx.test(String(e.event_type || e.event_name || '').toUpperCase())))
      .sort((a:any,b:any) => new Date(String(b.time || 0)).getTime() - new Date(String(a.time || 0)).getTime())[0];
    const priceOf = (ev?:MapEvent) => ev && Number.isFinite(Number(ev.price)) ? Number(ev.price).toFixed(2) : '';
    return {
      macro_high: rangeByTf.MN1?.high || priceOf(latest([/MACRO_.*HIGH/, /MACRO_EXTREME_PREMIUM/, /MACRO_ABOVE_FP/, /^RANGE_HIGH$/])),
      macro_low: rangeByTf.MN1?.low || priceOf(latest([/MACRO_.*LOW/, /MACRO_EXTREME_DISCOUNT/, /MACRO_BELOW_FP/, /^RANGE_LOW$/])),
      weekly_high: rangeByTf.W1?.high || priceOf(latest([/SET_WEEKLY_RANGE_HIGH/, /WEEKLY_.*HIGH/, /WEEKLY_EXTREME_PREMIUM/, /WEEKLY_ABOVE_FP/, /^RANGE_HIGH$/])),
      weekly_low: rangeByTf.W1?.low || priceOf(latest([/SET_WEEKLY_RANGE_LOW/, /WEEKLY_.*LOW/, /WEEKLY_EXTREME_DISCOUNT/, /WEEKLY_BELOW_FP/, /^RANGE_LOW$/])),
      daily_high: rangeByTf.D1?.high || priceOf(latest([/SET_DAILY_RANGE_HIGH/, /DAILY_.*HIGH/, /DAILY_EXTREME_PREMIUM/, /DAILY_ABOVE_FP/, /DAILY_PDH_REFERENCE/, /^RANGE_HIGH$/])),
      daily_low: rangeByTf.D1?.low || priceOf(latest([/SET_DAILY_RANGE_LOW/, /DAILY_.*LOW/, /DAILY_EXTREME_DISCOUNT/, /DAILY_BELOW_FP/, /DAILY_PDL_REFERENCE/, /^RANGE_LOW$/])),
    };
  }, [eventsByTf, rangeByTf]);

  const mergedCaseAnchors = useMemo(() => ({ ...autoCaseAnchors, ...Object.fromEntries(Object.entries(seedAnchors).filter(([,v]) => String(v ?? '').trim() !== '')) }), [autoCaseAnchors, seedAnchors]);

  const autoFillCaseAnchors = () => {
    setSeedAnchors((prev:any) => ({ ...autoCaseAnchors, ...prev }));
    setMessage('Auto-filled Case anchors from plotted map points/range memory. The form finally does less pretending.');
  };

  const caseTimeframe = scopeToTimeframe(caseScope);
  const caseRange = rangeByTf[caseTimeframe] || {};
  const caseWindow = rangeWindowByTf[caseTimeframe] || {};
  const caseHighKey = `${caseScope.toLowerCase()}_high`;
  const caseLowKey = `${caseScope.toLowerCase()}_low`;
  const caseHigh = seedAnchors.case_high || seedAnchors[caseHighKey] || caseRange.high || (autoCaseAnchors as any)[caseHighKey] || '';
  const caseLow = seedAnchors.case_low || seedAnchors[caseLowKey] || caseRange.low || (autoCaseAnchors as any)[caseLowKey] || '';
  // v087.29c: Do not show legacy /api/v1/map event counts here. Those old event bundles
  // are not the raw mapping ledger and they were making fresh cases look like they had
  // 81 inherited events. Case Manager now treats raw ledger writes as the source of truth.
  const caseEvents = [] as MapEvent[];
  const caseAnchorWindow = useMemo(() => {
    const scopeKey = String(caseScope || '').toLowerCase();
    const highTime = seedAnchors.case_high_time || seedAnchors[`${scopeKey}_high_time`] || '';
    const lowTime = seedAnchors.case_low_time || seedAnchors[`${scopeKey}_low_time`] || '';
    return timesToWindow([highTime, lowTime]) || { start:'', end:'' };
  }, [caseScope, seedAnchors.case_high_time, seedAnchors.case_low_time, seedAnchors.weekly_high_time, seedAnchors.weekly_low_time, seedAnchors.daily_high_time, seedAnchors.daily_low_time, seedAnchors.macro_high_time, seedAnchors.macro_low_time]);
  const caseWindowStartDisplay = seedAnchors.range_start_date || caseAnchorWindow.start || '';
  const caseWindowEndDisplay = seedAnchors.range_end_date || caseAnchorWindow.end || '';

  const activeCaseRecord = useMemo(() => {
    return safeArray<any>(seedIdeas).find((idea:any) => Number(idea?.id) === Number(activeCaseId)) || null;
  }, [seedIdeas, activeCaseId]);
  const activeRawCaseRecord = useMemo(() => {
    if (!rawActiveCaseId) return null;
    return safeArray<any>(seedIdeas).find((idea:any) => String(idea?.raw_case_id || idea?.id || '') === String(rawActiveCaseId)) || null;
  }, [seedIdeas, rawActiveCaseId]);
  const activeMappingCaseContainer = rawActiveCaseId ? activeRawCaseRecord : activeCaseRecord;

  const activeCaseLedger = useMemo(() => {
    const idea:any = activeCaseRecord;
    if (!idea) return { timeframe: caseTimeframe, scope: caseScope, rows: [] as any[], hasWindow: false, start: '', end: '', high: '', low: '', highSource: '', lowSource: '', windowSource: '' };
    const payload = idea?.mos_payload || {};
    const anchors = idea?.anchors || payload?.anchors || {};
    const tf = String(idea?.case_timeframe || payload?.case_timeframe || idea?.replay_timeframe || caseTimeframe || timeframe).toUpperCase();
    const scope = String(idea?.case_scope || payload?.case_scope || timeframeToScope(tf) || caseScope).toUpperCase();
    const savedHigh = idea?.case_high || anchors?.case_high || anchors?.[`${scope.toLowerCase()}_high`] || anchors?.weekly_high || anchors?.daily_high || anchors?.macro_high || '';
    const savedLow = idea?.case_low || anchors?.case_low || anchors?.[`${scope.toLowerCase()}_low`] || anchors?.weekly_low || anchors?.daily_low || anchors?.macro_low || '';
    const times = [
      anchors?.range_start_date,
      anchors?.range_end_date,
      anchors?.case_high_time,
      anchors?.case_low_time,
      anchors?.weekly_high_time,
      anchors?.weekly_low_time,
      anchors?.daily_high_time,
      anchors?.daily_low_time,
      anchors?.macro_high_time,
      anchors?.macro_low_time,
      idea?.replay_candle_time,
      payload?.timestamp,
    ].filter(Boolean).map((x:any)=>String(x));
    const validTimes = times
      .map((t:string)=>({ t, ms: new Date(t).getTime() }))
      .filter((x:any)=>Number.isFinite(x.ms))
      .sort((a:any,b:any)=>a.ms-b.ms);
    const savedStart = anchors?.range_start_date || validTimes[0]?.t || '';
    const savedEnd = anchors?.range_end_date || validTimes[validTimes.length-1]?.t || '';
    const startMs = savedStart ? new Date(String(savedStart)).getTime() : NaN;
    const endMs = savedEnd ? new Date(String(savedEnd)).getTime() : NaN;
    const hasSavedWindow = Number.isFinite(startMs) && Number.isFinite(endMs) && Math.abs(endMs - startMs) > 0;
    const sourceRows = safeArray<MapEvent>(eventsByTf?.[tf]);
    const rows = sourceRows
      .filter((ev:any)=>{
        if (!ev?.time) return false;
        if (!hasSavedWindow) return true;
        const ms = new Date(String(ev.time)).getTime();
        const lo = Math.min(startMs, endMs);
        const hi = Math.max(startMs, endMs);
        return Number.isFinite(ms) && ms >= lo && ms <= hi;
      })
      .map((ev:any)=>({ ...ev, _ms:new Date(String(ev.time)).getTime(), _label: markerLabel(ev.event_type || ev.event_name) }))
      .sort((a:any,b:any)=>(a._ms||0)-(b._ms||0) || String(a.id).localeCompare(String(b.id)));

    // v087.5: Case is a container. If the old case row did not persist a summary
    // high/low/window, derive the summary from the linked event ledger rows instead
    // of showing the user a useless "not saved" box. The ledger remains truth;
    // this is a read-only summary, not a second source of fib anchors.
    const price = (ev:any) => Number.isFinite(Number(ev?.price)) ? Number(ev.price) : NaN;
    const fmt = (n:any) => Number.isFinite(Number(n)) ? Number(n).toFixed(2) : '';
    const explicitHighs = rows.filter((ev:any)=>isExplicitRangeHighCommand(ev?.event_type || ev?.event_name) && Number.isFinite(price(ev)));
    const explicitLows = rows.filter((ev:any)=>isExplicitRangeLowCommand(ev?.event_type || ev?.event_name) && Number.isFinite(price(ev)));
    const latestExplicitHigh = explicitHighs[explicitHighs.length - 1];
    const latestExplicitLow = explicitLows[explicitLows.length - 1];
    const allPriced = rows.filter((ev:any)=>Number.isFinite(price(ev)));
    const maxEvent = allPriced.reduce((best:any, ev:any)=>!best || price(ev) > price(best) ? ev : best, null);
    const minEvent = allPriced.reduce((best:any, ev:any)=>!best || price(ev) < price(best) ? ev : best, null);
    const high = savedHigh ? fmt(savedHigh) : latestExplicitHigh ? fmt(latestExplicitHigh.price) : maxEvent ? fmt(maxEvent.price) : '';
    const low = savedLow ? fmt(savedLow) : latestExplicitLow ? fmt(latestExplicitLow.price) : minEvent ? fmt(minEvent.price) : '';
    const highSource = savedHigh ? 'saved on case' : latestExplicitHigh ? `derived from ${markerLabel(latestExplicitHigh.event_type)}` : maxEvent ? 'derived from highest linked event' : '';
    const lowSource = savedLow ? 'saved on case' : latestExplicitLow ? `derived from ${markerLabel(latestExplicitLow.event_type)}` : minEvent ? 'derived from lowest linked event' : '';
    const firstRow = rows[0];
    const lastRow = rows[rows.length - 1];
    const start = savedStart || firstRow?.time || '';
    const end = savedEnd || lastRow?.time || '';
    const derivedStartMs = start ? new Date(String(start)).getTime() : NaN;
    const derivedEndMs = end ? new Date(String(end)).getTime() : NaN;
    const hasWindow = Number.isFinite(derivedStartMs) && Number.isFinite(derivedEndMs) && (Math.abs(derivedEndMs - derivedStartMs) > 0 || rows.length > 0);
    const windowSource = hasSavedWindow ? 'saved on case' : rows.length ? 'derived from linked ledger rows' : '';

    return { timeframe: tf, scope, rows, hasWindow, start, end, high, low, highSource, lowSource, windowSource };
  }, [activeCaseRecord, eventsByTf, caseTimeframe, caseScope, timeframe]);

  const activeCaseCandidateAudit = useMemo(() => {
    const rows = safeArray<any>(activeCaseLedger?.rows || []);
    const rejected = rows.filter(isRejectedCandidateEvent);
    const accepted = rows.filter((ev:any) => !isRejectedCandidateEvent(ev) && isAcceptedCandidateEvent(ev));
    const edited = rows.filter((ev:any) => !!eventMeta(ev)?.user_edited_price);
    return { accepted, rejected, edited };
  }, [activeCaseLedger?.rows]);

  const parentTimeframeFor = (tf:string) => {
    const t = String(tf || '').toUpperCase();
    if (t === 'D1' || t === 'H4' || t === 'H1') return 'W1';
    if (t === 'M15' || t === 'M5') return 'H1';
    return '';
  };

  const activeParentRangeOverlay = useMemo<ParentRangeOverlayLine[]>(() => {
    const parentTf = parentTimeframeFor(timeframe);
    if (!parentTf || parentTf === timeframe) return [];
    const parentRange = rangeByTf[parentTf] || {};
    const parentWindow = rangeWindowByTf[parentTf] || {};
    const hi = parseNum(parentRange.high || (parentTf === 'W1' ? seedAnchors.case_high || seedAnchors.weekly_high : ''));
    const lo = parseNum(parentRange.low || (parentTf === 'W1' ? seedAnchors.case_low || seedAnchors.weekly_low : ''));
    const direction = safeArray<any>(eventsByTf[parentTf] || [])
      .map((e:any)=>String(e?.event_type || e?.derived_event_code || '').toUpperCase())
      .find((x:string)=>x.includes('BOS_UP') || x.includes('BOS_DOWN') || x === 'BOS_UP' || x === 'BOS_DOWN') || '';
    const out:ParentRangeOverlayLine[] = [];
    if (Number.isFinite(hi)) out.push({ timeframe:parentTf, kind:'high', price:Number(hi), label:`${parentTf} High`, direction, start:parentWindow.start, end:parentWindow.end });
    if (Number.isFinite(lo)) out.push({ timeframe:parentTf, kind:'low', price:Number(lo), label:`${parentTf} Low`, direction, start:parentWindow.start, end:parentWindow.end });
    return out;
  }, [timeframe, rangeByTf, rangeWindowByTf, seedAnchors.case_high, seedAnchors.case_low, seedAnchors.weekly_high, seedAnchors.weekly_low, eventsByTf]);

  const jumpToParentRangeStart = () => {
    const parentTf = parentTimeframeFor(timeframe);
    const w = rangeWindowByTf[parentTf] || {};
    const start = w.start || seedAnchors.range_start_date || activeCaseRecord?.range_start_date || activeCaseRecord?.anchors?.range_start_date || '';
    if (!start) { setMessage('No parent range start found yet. Save/open the Weekly case range first, then drop to Daily.'); return; }
    setJumpDate(String(start).slice(0,10));
    setFitToken(x=>x+1);
    setMessage(`Jumped to ${parentTf} parent start ${String(start).slice(0,10)}. The chart finally remembers where the story began.`);
  };

  const startChildReplayFromParentStart = () => {
    const parentTf = parentTimeframeFor(timeframe);
    const w = rangeWindowByTf[parentTf] || {};
    const start = w.start || seedAnchors.range_start_date || activeCaseRecord?.range_start_date || activeCaseRecord?.anchors?.range_start_date || '';
    if (!start) { setMessage('No parent range start found for child replay. Save/open the Weekly range first.'); return; }
    setCandleReplayFrameByTime(String(start));
    setJumpDate(String(start).slice(0,10));
    setMessage(`Started ${timeframe} replay from ${parentTf} parent start ${String(start).slice(0,10)}. Map forward without future candles cheating.`);
  };

  const jumpToCaseLedgerEvent = (ev:any) => {
    const tf = String(activeCaseLedger.timeframe || timeframe).toUpperCase();
    if (tf !== timeframe) {
      pendingCameraIntentRef.current = { intent:'PRESERVE_OR_NEAREST_TIME', targetTime:ev?.time || null, reason:'case-ledger-timeframe-switch' };
      activeTimeframeRef.current = tf;
      setTimeframe(tf);
      setRightDeckTab('narrative');
      setWorkspacePanelOpen(true);
      setMessage(`Switched to ${tf} for Case #${activeCaseId} ledger row. If the candle is shy, hit the row again after candles load.`);
      return;
    }
    jumpToLedgerEvent(ev);
  };


  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const monthYearLabel = (v:any) => {
    const d = new Date(String(v || ''));
    if (!Number.isFinite(d.getTime())) return '';
    return `${monthNames[d.getMonth()]}${d.getFullYear()}`;
  };
  const inferCaseWindow = () => {
    const start = seedAnchors.range_start_date || caseWindow.start || rangeWindowByTf.W1?.start || seedAnchors.case_high_time || seedAnchors.case_low_time || activeReplayCandle?.time;
    const end = seedAnchors.range_end_date || caseWindow.end || rangeWindowByTf.W1?.end || activeReplayCandle?.time;
    return { start, end };
  };
  const inferCaseNameFromWindow = () => {
    const { start, end } = inferCaseWindow();
    const a = monthYearLabel(start);
    const b = monthYearLabel(end);
    const suffix = a && b ? `${a}_${b}` : monthYearLabel(activeReplayCandle?.time) || 'Current';
    return `${String(symbol || 'XAUUSD')}_HTF_${suffix}`;
  };
  const buildCaseNameFromWindow = () => {
    const { start, end } = inferCaseWindow();
    const name = inferCaseNameFromWindow();
    setSeedName(name);
    setSeedAnchors((prev:any)=>({ ...prev, case_scope: caseScope, case_timeframe: caseTimeframe, range_start_date: start || prev.range_start_date || null, range_end_date: end || prev.range_end_date || null }));
    setMessage(`Case named ${name}. Boring name, clean database. A rare win.`);
  };
  const buildYtdCaseName = () => {
    const d = activeReplayCandle?.time ? new Date(String(activeReplayCandle.time)) : new Date();
    const name = `${String(symbol || 'XAUUSD')}_HTF_Jan${d.getFullYear()}_Current`;
    setSeedName(name);
    // v087.29c: Name YTD is only a naming helper. It must not mutate the case window,
    // because one naming click was stretching fresh 2026 anchor windows back to Jan/current.
    setSeedAnchors((prev:any)=>({ ...prev, case_scope: caseScope, case_timeframe: caseTimeframe }));
    setMessage(`Case named ${name}. Window left untouched; anchor candles remain the truth.`);
  };

  const exportActiveCaseAuditJson = async () => {
    if (!activeCaseId || !activeCaseRecord) { setMessage('No active case selected. The JSON goblin needs a case first.'); return; }
    let backendAudit:any = null;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${activeCaseId}/audit`).then(x=>x.json());
      if (r?.ok) backendAudit = r;
    } catch { /* frontend export still works */ }
    const payload = {
      generated_at: new Date().toISOString(),
      audit_source: backendAudit ? 'backend_db_plus_frontend_case_view' : 'frontend_case_view_only',
      backend_audit: backendAudit,
      frontend_case: activeCaseRecord,
      active_case_id: activeCaseId,
      symbol,
      active_timeframe: timeframe,
      case_ledger: activeCaseLedger,
      candidate_audit: activeCaseCandidateAudit,
      range: { high: hasRange ? high : null, low: hasRange ? low : null, window: rangeWindow },
      measurement_range: measurementRange,
      visible_events_in_case: activeCaseLedger.rows,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type:'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `case_${activeCaseId}_db_audit_${String(symbol||'SYMBOL')}_${String(activeCaseLedger.timeframe||timeframe)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 500);
    setMessage(`Exported Case #${activeCaseId} audit JSON. Now we can inspect the itemized bill instead of trusting the pretty counter.`);
  };

  const deleteActiveCase = async () => {
    if (!activeCaseId) { setMessage('No active case selected to delete. Even deletion needs a target, sadly.'); return; }
    if (!window.confirm(`Delete Case #${activeCaseId}? This removes the case container, snapshots, and objectives. Raw map events are kept.`)) return;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${activeCaseId}`, { method:'DELETE' }).then(x=>x.json());
      if (!r?.ok) throw new Error(r?.error || r?.detail || 'Delete failed');
      setActiveCaseId(null); setActiveCaseLabel(''); setCaseSavedNotice('');
      await loadSeedIdeas();
      setMessage(`Deleted Case #${r.id}. Raw events kept; because deleting receipts by accident is how databases become crime scenes.`);
    } catch (err:any) { setMessage(`Delete case failed: ${err?.message || err}`); }
  };
  const clearAllCases = async () => {
    if (!window.confirm(`Clear ALL ${symbol} case containers? Raw map events are kept.`)) return;
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/seed-ideas?symbol=${encodeURIComponent(symbol)}`, { method:'DELETE' }).then(x=>x.json());
      if (!r?.ok) throw new Error(r?.error || r?.detail || 'Clear cases failed');
      setActiveCaseId(null); setActiveCaseLabel(''); setSeedIdeas([]); setCaseSavedNotice('');
      await loadSeedIdeas();
      setMessage(`Cleared ${r.deleted_cases || 0} ${symbol} case containers. Raw event ledger remains.`);
    } catch (err:any) { setMessage(`Clear cases failed: ${err?.message || err}`); }
  };
  const resetResearchMappingDb = async () => {
    if (!window.confirm(`HARD RESET ${symbol} research mapping? This deletes cases, map events, HTF snapshots, objectives, ranges and route memory. Raw candles stay. This is the clean-slate button.`)) return;
    if (window.prompt('Type RESET to confirm the mapping wipe') !== 'RESET') { setMessage('Reset cancelled. The database lives another day.'); return; }
    try {
      const r = await fetch(`${BASE_URL}/api/v1/mos/research-reset`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ symbol, confirm:'RESET' }) }).then(x=>x.json());
      if (!r?.ok) throw new Error(r?.error || r?.detail || 'Reset failed');
      setActiveCaseId(null); setActiveCaseLabel(''); setSeedIdeas([]); setSessionEventIds(new Set());
      await loadSeedIdeas(); await loadMapEvents();
      setMessage(`Research mapping reset for ${symbol}. Candles preserved. Clean slate, finally.`);
    } catch (err:any) { setMessage(`Research reset failed: ${err?.message || err}`); }
  };

  const captureCaseAnchor = (side:'high'|'low') => {
    const c = selectedCandle || replayCandle;
    if (!c) { setMessage('Select a candle first. Case anchors still need candles, shocking development.'); return; }
    const price = side === 'high' ? c.high : c.low;
    const value = Number(price.toFixed(2));
    const key = side === 'high' ? 'case_high' : 'case_low';
    const nextTf = caseTimeframe;
    setSeedAnchors((prev:any)=>{
      const next = { ...prev, [key]: value, [`${key}_time`]: c.time, case_timeframe: nextTf, case_scope: caseScope };
      // v087.29b: Case draft windows are rebuilt only from the current selected anchors.
      // Never merge old rangeWindowByTf values here, because cancelled cases were dragging
      // ancient 2019 windows into fresh 2026 selections like a very committed ghost.
      const win = timesToWindow([next.case_high_time, next.case_low_time].filter(Boolean));
      setRangeWindowByTf((rp:any)=>({ ...rp, [nextTf]: win || { start: c.time, end: c.time } }));
      return next;
    });
    if (caseTimeframe === timeframe) {
      if (side === 'high') setRangeHigh(String(value));
      if (side === 'low') setRangeLow(String(value));
    }
    setMessage(`Captured ${scopeLabel(caseScope)} case ${side.toUpperCase()} at ${value.toFixed(2)} from ${shortTime(c.time, timeframe)}.`);
  };


  const low = parseNum(rangeLow);
  const high = parseNum(rangeHigh);
  const hasRange = Number.isFinite(low) && Number.isFinite(high) && high > low;

  const htfSemiAuto = useMemo(() => analyseHTFSemiAuto({
    timeframe,
    candles: visibleCandles,
    activeCandle: activeReplayCandle,
    rangeHigh: high,
    rangeLow: low,
    rangeWindow,
    events,
    activeCaseId,
    acceptedLocks: htfAcceptedSuggestionLocks,
  }), [timeframe, visibleCandles, activeReplayCandle?.time, high, low, rangeWindow.start, rangeWindow.end, events.length, activeCaseId, htfAcceptedSuggestionLocks.join('|')]);

  const htfVisibleCandidates = useMemo(() => {
    const rejected = new Set(htfRejectedCandidateIds || []);
    const acceptedLocks = new Set(htfAcceptedSuggestionLocks || []);
    return safeArray<HTFCandidate>(htfCandidates).filter(c => {
      if (rejected.has(c.id)) return false;
      const lk = hasRange ? htfCandidateLockKey(c, timeframe, low, high) : '';
      return !lk || !acceptedLocks.has(lk);
    });
  }, [htfCandidates, htfRejectedCandidateIds, htfAcceptedSuggestionLocks, hasRange, timeframe, low, high]);

  useEffect(() => {
    // Auto-refresh suggestions as replay/selection moves. They remain suggestions until accepted.
    // v087.16: core state contract. Range -> BOS -> reclaim -> rebase. Ref candle is separate.
    const rejected = new Set(htfRejectedCandidateIds || []);
    const acceptedLocks = new Set(htfAcceptedSuggestionLocks || []);
    setHtfCandidates(safeArray<HTFCandidate>(htfSemiAuto.candidates).filter(c => {
      if (rejected.has(c.id)) return false;
      const lk = hasRange ? htfCandidateLockKey(c, timeframe, low, high) : '';
      return !lk || !acceptedLocks.has(lk);
    }));
  }, [htfSemiAuto.state?.last_candle, htfSemiAuto.candidates.map(c=>c.id).join('|'), htfRejectedCandidateIds.join('|'), htfAcceptedSuggestionLocks.join('|'), hasRange, timeframe, low, high]);
  const rangeWindowCandles = useMemo(() => {
    if (!visibleCandles.length || (!rangeWindow.start && !rangeWindow.end)) return visibleCandles;
    const start = rangeWindow.start ? new Date(rangeWindow.start) : null;
    const end = rangeWindow.end ? new Date(rangeWindow.end) : null;
    return visibleCandles.filter(c => { const d = new Date(c.time); return (!start || d >= start) && (!end || d <= end); });
  }, [visibleCandles, rangeWindow.start, rangeWindow.end]);

  const trajectoryStartInfo = useMemo(() => {
    const getTimes = (types:string[]) => visibleEvents
      .filter(e => types.includes(String(e.event_type || e.event_name || '').toUpperCase()) && e.time)
      .map(e => ({ type:String(e.event_type || e.event_name || '').toUpperCase(), ms:new Date(String(e.time)).getTime(), time:String(e.time) }))
      .filter(e => Number.isFinite(e.ms));

    const firstOf = (items:{type:string;ms:number;time:string}[]) => items.length ? items.reduce((a,b)=> a.ms <= b.ms ? a : b) : null;
    const latestOf = (items:{type:string;ms:number;time:string}[]) => items.length ? items.reduce((a,b)=> a.ms >= b.ms ? a : b) : null;

    const bosDown = getTimes(['BOS_DOWN']);
    const reclaimLow = getTimes(['RECLAIM_LOW']);
    const bosUp = getTimes(['BOS_UP']);
    const reclaimHigh = getTimes(['RECLAIM_HIGH']);

    // Josh logic: once BOS + reclaim exists, the active story starts there.
    // Do NOT let older Ref H/L Taken events drag auto trajectory backwards.
    if (bosDown.length && reclaimLow.length) {
      const start = firstOf([...bosDown, ...reclaimLow]);
      return { time:start?.time, reason:'BOS Down + Reclaim Low' };
    }
    if (bosUp.length && reclaimHigh.length) {
      const start = firstOf([...bosUp, ...reclaimHigh]);
      return { time:start?.time, reason:'BOS Up + Reclaim High' };
    }

    // If no pair exists, prioritize the latest structural event over reference events.
    const structural = getTimes(['BOS_DOWN','BOS_UP','CHOCH_DOWN','CHOCH_UP','RECLAIM_LOW','RECLAIM_HIGH']);
    const latestStructural = latestOf(structural);
    if (latestStructural) return { time:latestStructural.time, reason:latestStructural.type };

    // Fall back to selected range window, then reference events.
    if (rangeWindow.start) return { time:rangeWindow.start, reason:'Range Start' };
    const refs = getTimes(['REF_LOW_TAKEN','REF_HIGH_TAKEN','RANGE_LOW','RANGE_HIGH']);
    const firstRef = firstOf(refs);
    if (firstRef) return { time:firstRef.time, reason:firstRef.type };

    return { time:undefined, reason:'Visible candles' };
  }, [visibleEvents, rangeWindow.start]);

  const trajectoryCandles = useMemo(() => {
    if (!visibleCandles.length) return visibleCandles;
    if (!trajectoryStartInfo.time) return rangeWindowCandles;
    const start = new Date(String(trajectoryStartInfo.time));
    if (Number.isNaN(start.getTime())) return rangeWindowCandles;
    // Let the route continue to the newest candle. Start is chosen by active structure math, not old ref history.
    return visibleCandles.filter(c => new Date(c.time) >= start);
  }, [visibleCandles, trajectoryStartInfo.time, rangeWindowCandles]);

  const traj = hasRange ? autoTrajectory(trajectoryCandles, low, high) : [];

  const loadMapMemory = async (requestedTf = timeframe, requestId = candleLoadSeqRef.current) => {
    const isCurrentLoad = () => requestId === candleLoadSeqRef.current && activeTimeframeRef.current === requestedTf;
    try {
      const localRangeBeforeLoad = rangeByTf[requestedTf] || {};
      const hasLocalExplicitHigh = !!String(localRangeBeforeLoad.high || '').trim();
      const hasLocalExplicitLow = !!String(localRangeBeforeLoad.low || '').trim();

      // v087.25: if a case is active, load ONLY rows explicitly linked to that case.
      // The old global map/event feed can still exist, but it must not vomit legacy marks into a clean workspace.
      if (activeCaseId) {
        const payload = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${activeCaseId}/payload`).then(r=>r.json()).catch(()=>null);
        if (!isCurrentLoad()) { cameraLog('map memory ignored as stale', { requestId, requestedTf, activeTf:activeTimeframeRef.current }); return false; }
        if (payload?.ok) {
          const caseEvents = safeArray<any>(payload.events)
            .filter((raw:any)=>String(raw?.timeframe || raw?.meta?.timeframe || '').toUpperCase() === String(requestedTf).toUpperCase())
            .map(normalizeBackendEvent)
            .filter(Boolean) as MapEvent[];
          setEventsByTf(prev => ({ ...prev, [requestedTf]: caseEvents }));

          const caseRanges = safeArray<any>(payload.ranges)
            .filter((r:any)=>String(r?.timeframe || '').toUpperCase() === String(requestedTf).toUpperCase());
          const latestRange = caseRanges[caseRanges.length - 1];
          if (latestRange) {
            if (!hasLocalExplicitHigh && Number(latestRange.range_high)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:String(Number(latestRange.range_high).toFixed(2)), low:prev[requestedTf]?.low || '' } }));
            if (!hasLocalExplicitLow && Number(latestRange.range_low)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:prev[requestedTf]?.high || '', low:String(Number(latestRange.range_low).toFixed(2)) } }));
            const ms = [latestRange.range_high_time, latestRange.range_low_time, latestRange.active_from_time, latestRange.inactive_from_time].filter(Boolean).map((x:string)=>new Date(x).getTime()).filter(Number.isFinite);
            if (ms.length >= 2 && (!rangeWindowByTf[requestedTf]?.start || !rangeWindowByTf[requestedTf]?.end)) {
              setRangeWindowByTf(prev=>({ ...prev, [requestedTf]: { start:new Date(Math.min(...ms)).toISOString(), end:new Date(Math.max(...ms)).toISOString() }}));
            }
          } else if ((!hasLocalExplicitHigh || !hasLocalExplicitLow) && caseEvents.length) {
            syncRangeFromEvents(caseEvents, false, requestedTf);
          }
          return true;
        }
      }

      const [rangeRes, eventsRes] = await Promise.all([
        fetch(`${BASE_URL}/api/v1/map/range?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(requestedTf)}&range_key=active`).then(r=>r.json()).catch(()=>null),
        fetch(`${BASE_URL}/api/v1/map/events?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(requestedTf)}&limit=2000`).then(r=>r.json()).catch(()=>null)
      ]);
      if (!isCurrentLoad()) { cameraLog('map memory ignored as stale', { requestId, requestedTf, activeTf:activeTimeframeRef.current }); return false; }

      if (rangeRes?.ok && rangeRes.range) {
        const rg = rangeRes.range;
        if (!hasLocalExplicitHigh && Number(rg.range_high)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:String(Number(rg.range_high).toFixed(2)), low:prev[requestedTf]?.low || '' } }));
        if (!hasLocalExplicitLow && Number(rg.range_low)) setRangeByTf(prev => ({ ...prev, [requestedTf]: { high:prev[requestedTf]?.high || '', low:String(Number(rg.range_low).toFixed(2)) } }));
        const startCandidates = [rg.range_high_time, rg.range_low_time].filter(Boolean).map((x:string)=>new Date(x).getTime()).filter(Number.isFinite);
        if (startCandidates.length >= 2 && (!rangeWindowByTf[requestedTf]?.start || !rangeWindowByTf[requestedTf]?.end)) {
          setRangeWindowByTf(prev=>({ ...prev, [requestedTf]: { start:new Date(Math.min(...startCandidates)).toISOString(), end:new Date(Math.max(...startCandidates)).toISOString() }}));
        }
      }

      if (eventsRes?.ok && Array.isArray(eventsRes.events)) {
        const loaded = eventsRes.events.map((e:any)=>({
          id: String(e.client_event_id || e.id),
          event_type: e.event_type,
          event_name: e.event_name || e.event_type,
          time: e.time,
          price: Number(e.price),
          zone: e.zone,
          zone_percent: e.zone_percent === null || e.zone_percent === undefined ? undefined : Number(e.zone_percent),
          notes: e.notes || '',
          primitive: e.primitive || undefined,
          derived_event_code: e.derived_event_code || undefined,
          movement_rule: e.movement_rule || undefined,
          range_status_after: e.range_status_after || undefined,
          engine_source: e.engine_source || undefined,
          logic_version: e.logic_version || undefined,
          candidate_id: e.candidate_id || undefined,
          confidence: e.confidence || undefined,
          meta_json: (() => { try { return typeof e.meta_json === 'string' ? JSON.parse(e.meta_json) : e.meta_json; } catch { return e.meta_json; } })(),
          candle_open: e.candle_open === null || e.candle_open === undefined ? undefined : Number(e.candle_open),
          candle_high: e.candle_high === null || e.candle_high === undefined ? undefined : Number(e.candle_high),
          candle_low: e.candle_low === null || e.candle_low === undefined ? undefined : Number(e.candle_low),
          candle_close: e.candle_close === null || e.candle_close === undefined ? undefined : Number(e.candle_close),
        })).filter((e:any)=>e.event_type && Number.isFinite(e.price));
        setEventsByTf(prev => ({ ...prev, [requestedTf]: loaded }));
        if (!hasLocalExplicitHigh || !hasLocalExplicitLow) syncRangeFromEvents(loaded, false, requestedTf);
      }
      return true;
    } catch {
      // Map memory failing should never block candle display. That would be dramatic and unhelpful.
      return false;
    }
  };

  const resolveLoadCameraIntent = (requestedTf:string, fallbackTime?:string|null) => {
    const pending = pendingCameraIntentRef.current;
    if (pending.intent && pending.intent !== 'NONE') return pending;
    if (cameraMode === 'LOCKED') return { intent:'RESTORE_LOCKED' as CameraIntent, targetTime:fallbackTime, reason:'locked-load' };
    if (cameraMode === 'CASE') return { intent:'CASE' as CameraIntent, targetTime:fallbackTime, reason:'case-load' };
    if (cameraMode === 'REPLAY') return { intent:'REPLAY' as CameraIntent, targetTime:fallbackTime, reason:'replay-load' };
    return { intent:'PRESERVE_OR_NEAREST_TIME' as CameraIntent, targetTime:fallbackTime, reason:`${requestedTf}-load` };
  };

  const applyCameraCommand = (intent:CameraIntent, targetTime?:string|null, reason?:string, scaleFactor?:number) => {
    cameraLog('camera intent applied', { intent, targetTime, reason, scaleFactor });
    setCameraCommand(prev => ({ intent, targetTime: targetTime || null, reason, scaleFactor, token: prev.token + 1 }));
  };

  const fitRangeView = () => {
    if (!rhAnchor.price || !rlAnchor.price) { setMessage('Set Range High and Range Low before Fit Range.'); return; }
    applyCameraCommand('RANGE', null, 'fit-range');
  };

  const fitReplayView = () => {
    const targetTime = selectedCandle?.time || replayCandle?.time || candleReplayCursorTime || null;
    if (!targetTime) { setMessage('No selected/replay candle to fit.'); return; }
    applyCameraCommand('REPLAY', targetTime, 'fit-replay');
  };

  const fitCaseView = () => {
    const targetTime = activeCaseLedger?.start || rangeWindow.start || selectedCandle?.time || replayCandle?.time || null;
    applyCameraCommand('CASE', targetTime, 'fit-case');
  };

  const fitAllView = () => applyCameraCommand('FIT_ALL', null, 'fit-all');

  const lockCurrentView = () => {
    const dom = visibleCameraDomainRef.current;
    if (!dom || !dom.start || !dom.end || !Number.isFinite(dom.priceLow) || !Number.isFinite(dom.priceHigh) || dom.priceHigh <= dom.priceLow) {
      setMessage('Cannot lock view yet: no valid visible camera domain.');
      return;
    }
    setCameraDomainByCaseTf(prev => ({ ...prev, [cameraKey]: { start:dom.start, end:dom.end } }));
    setCameraPriceDomainByCaseTf(prev => ({ ...prev, [cameraKey]: { low:dom.priceLow, high:dom.priceHigh } }));
    setCameraMode('LOCKED');
    applyCameraCommand('RESTORE_LOCKED', null, 'lock-view');
    setMessage(`Locked view for ${timeframe}: ${shortTime(dom.start, timeframe)} → ${shortTime(dom.end, timeframe)}`);
  };

  const loadCandles = async (requestedTf = timeframe) => {
    const targetTf = String(requestedTf || timeframe).toUpperCase();
    const requestId = candleLoadSeqRef.current + 1;
    candleLoadSeqRef.current = requestId;
    const preservedTime = selectedCandle?.time || candleReplayCursorTime || replayCandle?.time || null;
    const pendingIntent = resolveLoadCameraIntent(targetTf, preservedTime);
    const isCurrentLoad = () => requestId === candleLoadSeqRef.current && activeTimeframeRef.current === targetTf;
    cameraLog('candle load start', { requestId, targetTf, intent:pendingIntent.intent, targetTime:pendingIntent.targetTime });
    setLoading(true); setMessage(`Loading ${targetTf} candles from backend...`);
    try {
      const r = await fetch(`${BASE_URL}/api/v1/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(targetTf)}&limit=12000`).then(x=>x.json());
      if (!isCurrentLoad()) { cameraLog('candle load ignored as stale', { requestId, targetTf, activeTf:activeTimeframeRef.current }); return; }
      if (!r.ok) throw new Error(r.error || 'Backend returned no candles');
      const parsed = (r.candles || [])
        .map((c:any)=>({ ...c, open:Number(c.open), high:Number(c.high), low:Number(c.low), close:Number(c.close), volume:Number(c.volume||0) }))
        .filter((c:Candle)=>Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low) && Number.isFinite(c.close));
      if (!isCurrentLoad()) { cameraLog('candle load ignored as stale after parse', { requestId, targetTf, activeTf:activeTimeframeRef.current }); return; }
      setCandles(parsed);
      if (!parsed.length) {
        setCandleReplayIndex(0);
        setSelectedCandle(null);
        setSelectedCandlePoint(null);
        pendingCameraIntentRef.current = { intent:'NONE' };
        setMessage(`No ${targetTf} candles returned.`);
        cameraLog('candle load empty', { requestId, targetTf });
        return;
      }
      const targetTime = pendingIntent.targetTime || preservedTime;
      const nearestIdx = targetTime ? candleIndexNearest(parsed, targetTime) : parsed.length - 1;
      const safeIdx = clamp(nearestIdx, 0, parsed.length - 1);
      const nearest = parsed[safeIdx];
      setCandleReplayIndex(safeIdx);
      if (targetTime && nearest) {
        setSelectedCandle(nearest);
        setSelectedCandlePoint({ price: Number(nearest.close.toFixed(2)) });
        if (candleReplayMode || pendingIntent.intent === 'REPLAY') setCandleReplayCursorTime(nearest.time);
        cameraLog('selected/replay nearest-candle mapping', { requestId, targetTf, targetTime, nearestTime:nearest.time, safeIdx });
      }
      // v086.13: no more automatic last-120-candle default range.
      // Fibs should appear only from explicit Set M/W/D High/Low or hydrated ledger anchors.
      await loadMapMemory(targetTf, requestId);
      if (!isCurrentLoad()) { cameraLog('candle load ignored as stale after memory', { requestId, targetTf, activeTf:activeTimeframeRef.current }); return; }
      const commandTargetTime = pendingIntent.targetTime || targetTime || nearest?.time || null;
      applyCameraCommand(pendingIntent.intent === 'NONE' ? 'PRESERVE_OR_NEAREST_TIME' : pendingIntent.intent, commandTargetTime, pendingIntent.reason || 'confirmed-candle-load');
      pendingCameraIntentRef.current = { intent:'NONE' };
      setMessage(`Loaded ${parsed.length} ${targetTf} candles + backend map memory.`);
      cameraLog('candle load applied', { requestId, targetTf, intent:pendingIntent.intent, commandTargetTime });
    } catch(e:any) {
      if (!isCurrentLoad()) { cameraLog('candle load error ignored as stale', { requestId, targetTf, error:e?.message || e }); return; }
      setMessage(`Load ${targetTf} failed: ${e?.message || e}`);
    }
    finally {
      if (isCurrentLoad()) setLoading(false);
    }
  };

  const importCommon = async () => {
    setLoading(true); setMessage('Importing EA CSV files from Common\\Files...');
    try {
      const r = await fetch(`${BASE_URL}/api/v1/candles/import-common-files`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ symbol, timeframes: MAP_TIMEFRAMES })}).then(x=>x.json());
      setMessage(r.ok ? 'Import finished. Reload candles next.' : `Import failed: ${r.error || 'unknown'}`);
    } catch(e:any) { setMessage(`Import failed: ${e?.message || e}`); }
    finally { setLoading(false); }
  };

  const saveEvent = async (ev:MapEvent) => {
    // v087.29 keylogger mode: persist only the raw click/action ledger.
    // Local markers remain for the chart; backend relational map_events/ranges are intentionally bypassed.
    setSessionEventIds(prev => { const next = new Set(prev); next.add(String(ev.id)); return next; });
    await postRawMappingEvent(ev);
  };



  const saveHTFStateSnapshot = async (_patch:any = {}) => {
    // v087.29: no live HTF state snapshots during mapping. Python compiler owns derived state later.
    return;
  };


  const acceptHTFCandidate = async (cand:HTFCandidate) => {
    if (!cand?.candle) return;
    const ev:MapEvent = {
      id: cand.id,
      event_type: cand.event_type,
      event_name: cand.label,
      time: cand.time,
      price: Number(cand.price.toFixed(2)),
      zone: zoneLabel(zonePercent(cand.price, low, high)),
      zone_percent: (() => { const p = zonePercent(cand.price, low, high); return p === null ? undefined : Number(p.toFixed(2)); })(),
      notes: cand.reason,
      source: 'auto',
      candle_open: cand.candle.open,
      candle_high: cand.candle.high,
      candle_low: cand.candle.low,
      candle_close: cand.candle.close,
      primitive: cand.primitive,
      derived_event_code: cand.derived_event_code,
      movement_rule: cand.movement_rule,
      range_status_after: cand.range_status_after,
      engine_source: 'HTF_SEMI_AUTO_STATE_ENGINE',
      logic_version: 'htf_core_state_contract_v087_16',
      candidate_id: cand.id,
      confidence: cand.confidence,
      meta_json: { ...cand.meta, case_id: activeCaseId || null, range_high: high, range_low: low, timeframe, accepted_from_candidate:true },
    };
    const lifecycleLock = htfCandidateLockKey(cand, timeframe, low, high);
    if (lifecycleLock) setHtfAcceptedSuggestionLocks(prev => Array.from(new Set([...(prev || []), lifecycleLock])));
    upsertMarkerIntoEvents(ev);
    await saveEvent(ev);
    await saveHTFStateSnapshot({ last_transition:cand.derived_event_code, last_candidate:cand.id, range_status_after:cand.range_status_after });
    if (cand.primitive === 'RANGE_REBASE' && cand.meta) {
      const oldSnapshot = { high, low, start:rangeWindow.start, end:rangeWindow.end, preserved_for:'RETRACEMENT_DEPTH_PROFILE_STATS', rebase_candidate_id:cand.id };
      const mh = Number(cand.meta.new_range_high);
      const ml = Number(cand.meta.new_range_low);
      if (Number.isFinite(mh) && Number.isFinite(ml) && mh > ml) {
        const highTime = cand.meta.new_range_high_time || cand.meta.responsible_high_time || cand.time;
        const lowTime = cand.meta.new_range_low_time || cand.meta.responsible_low_time || cand.time;
        const ms = [highTime, lowTime].map((t:string)=>new Date(String(t)).getTime()).filter(Number.isFinite);
        const nextWindow = ms.length >= 2
          ? { start:new Date(Math.min(...ms)).toISOString(), end:new Date(Math.max(...ms)).toISOString() }
          : { start: lowTime || highTime || cand.time, end: highTime || lowTime || cand.time };
        setMeasurementRangeByTf(prev => ({ ...prev, [timeframe]: oldSnapshot }));
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high:String(Number(mh.toFixed(2))), low:String(Number(ml.toFixed(2))) } }));
        setRangeWindowByTf(prev => ({ ...prev, [timeframe]: nextWindow }));
        await saveActiveRangeDirect({ high:mh, low:ml, high_time:highTime, low_time:lowTime, source:'electron-htf-visible-rebase-v087_16' });
        await saveHTFStateSnapshot({
          __range_override:{ high:mh, low:ml, start:nextWindow.start, end:nextWindow.end },
          last_transition:'RANGE_REBASED_VISIBLE_FIB',
          previous_range_snapshot:oldSnapshot,
          active_range_rebased_to:{ high:mh, low:ml, high_time:highTime, low_time:lowTime },
          measurement_range_preserved:true,
          measurement_old_range:oldSnapshot,
          active_fib_range_is_new_range:true,
        });
      }
    }
    setHtfCandidates(prev => prev.filter(x => x.id !== cand.id));
    setMessage(cand.primitive === 'RANGE_REBASE' ? `Accepted ${cand.label}. Visible fib rebased; old range preserved for retracement stats.` : `Accepted ${cand.label}. Stored primitive + derived event + HTF state metadata. The machine did its paperwork, for once.`);
  };

  useEffect(() => {
    if (!hasRange || !activeCaseId) return;
    const bos = htfVisibleCandidates.find(c => c.primitive === 'BREACH' && (String(c.derived_event_code || c.event_type).includes('BOS_UP') || String(c.derived_event_code || c.event_type).includes('BOS_DOWN')));
    if (!bos || autoSavedBosIdsRef.current.has(bos.id)) return;
    autoSavedBosIdsRef.current.add(bos.id);
    acceptHTFCandidate(bos).catch(err => setMessage(`BOS autosave failed: ${err?.message || err}`));
  }, [htfVisibleCandidates.map(c=>c.id).join('|'), hasRange, activeCaseId]);

  const rejectHTFCandidate = async (cand:HTFCandidate) => {
    if (!cand?.candle) return;
    setHtfRejectedCandidateIds(prev => Array.from(new Set([...(prev || []), cand.id])));
    const ev:MapEvent = {
      id: `${cand.id}_REJECTED`,
      event_type: 'HTF_CANDIDATE_REJECTED',
      event_name: `Rejected: ${cand.label}`,
      time: cand.time,
      price: Number(cand.price.toFixed(2)),
      zone: zoneLabel(zonePercent(cand.price, low, high)),
      zone_percent: (() => { const p = zonePercent(cand.price, low, high); return p === null ? undefined : Number(p.toFixed(2)); })(),
      notes: cand.reason,
      source: 'candidate',
      candle_open: cand.candle.open,
      candle_high: cand.candle.high,
      candle_low: cand.candle.low,
      candle_close: cand.candle.close,
      primitive: cand.primitive,
      derived_event_code: cand.derived_event_code,
      movement_rule: cand.movement_rule,
      range_status_after: cand.range_status_after,
      engine_source: 'HTF_SEMI_AUTO_STATE_ENGINE',
      logic_version: 'candidate_audit_v087_18',
      candidate_id: cand.id,
      candidate_status: 'REJECTED',
      confidence: cand.confidence,
      meta_json: { ...cand.meta, case_id: activeCaseId || null, range_high: high, range_low: low, timeframe, candidate_status:'REJECTED', rejected_from_candidate:true, rejected_at:new Date().toISOString(), original_event_type:cand.event_type, original_label:cand.label, rejected_reason:'USER_REJECTED_SEMI_AUTO_CANDIDATE', price_location_pct: (() => { const p = zonePercent(cand.price, low, high); return p === null ? null : Number(p.toFixed(2)); })() },
    };
    upsertMarkerIntoEvents(ev);
    await saveEvent(ev);
    await saveHTFStateSnapshot({ last_rejected_candidate:cand.id, rejected_candidate_type:cand.event_type, rejected_candidate_rule:cand.movement_rule });
    setHtfCandidates(prev => prev.filter(x => x.id !== cand.id));
    setMessage(`Rejected ${cand.label} and saved it to the Candidate Audit log. Even bad suggestions now have a job.`);
  };

  const editHTFCandidatePrice = async (cand:HTFCandidate) => {
    const raw = window.prompt('Edit candidate price before saving:', String(cand.price));
    if (raw === null) return;
    const n = Number(raw);
    if (!Number.isFinite(n)) { setMessage('That price is not a number. Humanity remains undefeated by input boxes.'); return; }
    await acceptHTFCandidate({ ...cand, price:n, status:'EDITED', meta:{ ...cand.meta, user_edited_price:true, original_price:cand.price }});
  };

  const buildRangePayloadFromEvents = (sourceEvents:MapEvent[]) => {
    const source = safeArray<MapEvent>(sourceEvents);
    const lastRangeHigh = latestRangeHighEvent(source);
    const lastRangeLow = latestRangeLowEvent(source);
    const lastRefHigh = [...source].reverse().find(e => isRefHighMarker(e?.event_type));
    const lastRefLow = [...source].reverse().find(e => isRefLowMarker(e?.event_type));
    const ms = [lastRangeHigh?.time, lastRangeLow?.time].filter(Boolean).map((t:any)=>new Date(String(t)).getTime()).filter(Number.isFinite);
    const rangeStart = ms.length ? new Date(Math.min(...ms)).toISOString() : undefined;
    const rangeEnd = ms.length ? new Date(Math.max(...ms)).toISOString() : undefined;
    return {
      symbol,
      timeframe,
      case_id: activeCaseId || null,
      layer: timeframe,
      parent_timeframe: parentTimeframeFor(timeframe) || null,
      range_key: activeCaseId ? `case_${activeCaseId}_${timeframe}_active` : 'active',
      range_high_price: lastRangeHigh?.price,
      range_high_time: lastRangeHigh?.time,
      range_low_price: lastRangeLow?.price,
      range_low_time: lastRangeLow?.time,
      active_from_time: rangeStart,
      inactive_from_time: rangeEnd,
      range_start_time: rangeStart,
      range_end_time: rangeEnd,
      ref_high_price: lastRefHigh?.price,
      ref_high_time: lastRefHigh?.time,
      ref_low_price: lastRefLow?.price,
      ref_low_time: lastRefLow?.time,
      source: 'electron-map-studio-structure-only',
      structure_version: 'STRUCTURE_ONLY_V2'
    };
  };

  // v087.29 KEYLOGGER MODE:
  // Electron is now a visual interpreter + raw event emitter only.
  // Parent links, zones, profiles, phases, objectives and features are compiled later by the local processor.
  const rawCandleTimeMs = (time:any) => {
    const ms = new Date(String(time || '')).getTime();
    return Number.isFinite(ms) ? ms : Date.now();
  };

  const rawEventSideFor = (type:string):'HIGH'|'LOW'|'NONE' => {
    const t = String(type || '').toUpperCase();
    if (t.includes('HIGH') || t.includes('BOS_UP') || t.includes('CHOCH_UP')) return 'HIGH';
    if (t.includes('LOW') || t.includes('BOS_DOWN') || t.includes('CHOCH_DOWN')) return 'LOW';
    return 'NONE';
  };

  const rawEventTypeFor = (type:string, source?:string):string => {
    const t = String(type || '').toUpperCase();
    const isAuto = String(source || '').toLowerCase() === 'auto';
    if (t === 'RANGE_HIGH' || t === 'RANGE_LOW') return 'SET_ANCHOR';
    if (t.includes('BOS')) return isAuto ? 'AUTO_BOS' : 'MANUAL_BOS';
    if (t.includes('RECLAIM')) return 'RECLAIM';
    if (t.includes('ABANDON') || t.includes('INVALID')) return 'ABANDON_RANGE';
    return 'NOTE';
  };

  const rawPriceModeFor = (ev:MapEvent):number|null => {
    const n = Number(ev?.price);
    return Number.isFinite(n) ? n : null;
  };

  const sortCaseRows = (rows:any[]) => [...safeArray<any>(rows)].sort((a:any,b:any) => {
    const timeOf = (x:any) => {
      const raw = x?.updated_at || x?.created_at || x?.updated_at_utc_ms || x?.created_at_utc_ms || 0;
      const n = Number(raw);
      if (Number.isFinite(n) && n > 100000000000) return n;
      const ms = new Date(String(raw || '')).getTime();
      return Number.isFinite(ms) ? ms : 0;
    };
    return timeOf(b) - timeOf(a) || String(b?.id || '').localeCompare(String(a?.id || ''));
  });

  const rawCaseRecentRow = (caseId:string, rawCase?:any) => {
    const tf = String(rawCase?.base_timeframe || caseTimeframe || timeframe || 'W1').toUpperCase();
    const scope = timeframeToScope(tf);
    const name = String(rawCase?.case_name || seedName || activeCaseLabel || `${symbol}_${tf}_Raw_Case`).replace(/\s+·\s+[a-f0-9-]+$/i, '');
    const now = new Date().toISOString();
    return {
      id: caseId,
      raw_case_id: caseId,
      is_raw_mapping_case: true,
      seed_name: name,
      symbol: rawCase?.symbol || symbol,
      replay_timeframe: tf,
      case_timeframe: tf,
      case_scope: scope,
      replay_candle_time: activeReplayCandle?.time || candleReplayCursorTime || now,
      created_at: rawCase?.created_at_utc_ms ? new Date(Number(rawCase.created_at_utc_ms)).toISOString() : now,
      updated_at: rawCase?.updated_at_utc_ms ? new Date(Number(rawCase.updated_at_utc_ms)).toISOString() : now,
      raw_case: rawCase || null,
    };
  };

  const mergeRecentCases = (rows:any[], extra?:any) => {
    const merged = new globalThis.Map<string, any>();
    for (const row of safeArray<any>(rows)) {
      const key = String(row?.raw_case_id || row?.id || '');
      if (key) merged.set(key, row);
    }
    if (extra) {
      const key = String(extra?.raw_case_id || extra?.id || '');
      if (key) merged.set(key, { ...(merged.get(key) || {}), ...extra });
    }
    const activeRaw = rawActiveCaseId ? rawCaseRecentRow(String(rawActiveCaseId)) : null;
    if (activeRaw) {
      const key = String(activeRaw.raw_case_id);
      merged.set(key, { ...(merged.get(key) || {}), ...activeRaw });
    }
    return sortCaseRows(Array.from(merged.values()));
  };

  const caseMatchesContext = (idea:any) => {
    const isActive = String(idea?.raw_case_id || idea?.id || '') === String(activeCaseDisplayId || '');
    if (isActive) return true;
    if (String(idea?.symbol || symbol).toUpperCase() !== String(symbol).toUpperCase()) return false;
    const tf = String(idea?.case_timeframe || idea?.replay_timeframe || idea?.raw_case?.base_timeframe || '').toUpperCase();
    const scope = String(idea?.case_scope || (tf ? timeframeToScope(tf) : '') || '').toUpperCase();
    return !tf || tf === String(caseTimeframe).toUpperCase() || scope === String(caseScope).toUpperCase();
  };

  const ensureRawCase = async () => {
    if (rawActiveCaseId) return String(rawActiveCaseId);
    try {
      const caseName = String(seedName || activeCaseLabel || `${symbol}_${caseTimeframe}_Raw_Case`).trim() || `${symbol}_${caseTimeframe}_Raw_Case`;
      const payload = {
        symbol,
        case_name: caseName,
        base_timeframe: caseTimeframe || timeframe || 'W1',
        price_scale_default: String(symbol).toUpperCase().includes('XAU') ? 100 : 100000,
        notes: seedNotes || 'Created from Electron raw mapping contract',
      };
      const r = await createRawCase(BASE_URL, payload);
      const id = String(r?.case?.case_id || r?.case_id || '');
      if (!id) throw new Error('Raw case create returned no case_id');
      setRawActiveCaseId(id);
      setActiveCaseId(null);
      setActiveCaseLabel(`${caseName} · ${id.slice(0, 8)}`);
      setSeedIdeas(prev => mergeRecentCases(prev, rawCaseRecentRow(id, r?.case)));
      return id;
    } catch (err: any) {
      setMessage(`Raw case create failed: ${err?.message || err}`);
      return null;
    }
  };

  const postRawMappingEvent = async (ev:MapEvent) => {
    const rawCaseId = await ensureRawCase();
    if (!rawCaseId) { setMessage('Save/open a case before mapping raw events. The paper needs a folder, tragically.'); return null; }
    const candleIdx = candles.findIndex(c => c.time === ev.time);
    const source = String(ev.source || '').toLowerCase() === 'auto' ? 'auto' : 'manual';
    const payload = {
      event_id: String(ev.id || markerIdForCandle({ time: ev.time || new Date().toISOString(), open:0, high:Number(ev.price||0), low:Number(ev.price||0), close:Number(ev.price||0), volume:0 } as any, ev.event_type || 'NOTE')),
      case_id: rawCaseId,
      symbol,
      timeframe,
      candle_time_utc_ms: rawCandleTimeMs(ev.time),
      candle_index: candleIdx >= 0 ? candleIdx : null,
      price: rawPriceModeFor(ev),
      event_type: rawEventTypeFor(ev.event_type, source),
      event_side: rawEventSideFor(ev.event_type),
      source,
      supersedes_event_id: null,
      notes: ev.notes || ev.event_name || '',
      raw_payload_json: {
        legacy_event_type: ev.event_type,
        legacy_event_name: ev.event_name,
        candle_open: ev.candle_open,
        candle_high: ev.candle_high,
        candle_low: ev.candle_low,
        candle_close: ev.candle_close,
        electron_version: 'v087.29_keylogger_mode'
      }
    };
    const r = await fetch(`${BASE_URL}/api/v1/raw-mapping/events`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    }).then(x=>x.json()).catch((e)=>({ ok:false, error:String(e) }));
    if (!r?.ok) setMessage(`Raw ledger save failed: ${r?.error || 'unknown backend tantrum'}`);
    return r;
  };

  const saveActiveRange = async (_sourceEvents:MapEvent[]) => {
    // v087.29: no live range persistence during mapping. Raw events are the only input truth.
    return;
  };

  const saveActiveRangeDirect = async (_rg:{ high:number; low:number; high_time?:string; low_time?:string; source?:string }) => {
    // v087.29: disabled. The local processor rebuilds ranges from raw_mapping_events later.
    return;
  };

  const syncRangeFromEvents = (nextEvents:MapEvent[], persist:boolean = true, targetTf = timeframe) => {
    const source = safeArray<MapEvent>(nextEvents);
    const lastRangeHigh = latestRangeHighEvent(source);
    const lastRangeLow = latestRangeLowEvent(source);

    setRangeByTf(prev => ({
      ...prev,
      [targetTf]: {
        high: lastRangeHigh ? String(Number(lastRangeHigh.price).toFixed(2)) : (prev[targetTf]?.high || ''),
        low: lastRangeLow ? String(Number(lastRangeLow.price).toFixed(2)) : (prev[targetTf]?.low || '')
      }
    }));

    const anchorTimes = [lastRangeHigh?.time, lastRangeLow?.time].filter(Boolean) as string[];
    if (anchorTimes.length >= 2) {
      const ms = anchorTimes.map(t => new Date(t).getTime()).filter(Number.isFinite);
      if (ms.length >= 2) {
        setRangeWindowByTf(prev => ({
          ...prev,
          [targetTf]: {
            start: new Date(Math.min(...ms)).toISOString(),
            end: new Date(Math.max(...ms)).toISOString()
          }
        }));
      }
    } else {
      setRangeWindowByTf(prev => ({ ...prev, [targetTf]: {} }));
    }
    if (persist) saveActiveRange(source);
  };

  const deleteEvent = async (id:string) => {
    setEventsForTf(prev=>{
      const next = prev.filter(e=>e.id!==id);
      syncRangeFromEvents(next);
      return next;
    });
    try {
      const rawId = rawActiveCaseId || (activeCaseId ? String(activeCaseId) : '');
      if (rawId) await fetch(`${BASE_URL}/api/v1/raw-mapping/events/delete`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ case_id:rawId, event_id:id, notes:'Deleted from Electron v087.29 UI' }) });
    } catch { /* local delete still counts */ }
    setMessage('Deleted local marker and appended DELETE_RECORD to raw ledger. No relational swamp involved.');
  };

  const clearSelectedCandleEvents = async () => {
    if (!selectedCandle) return;
    const t = selectedCandle.time;
    let nextEvents:MapEvent[] = [];
    setEventsForTf(prev=>{
      const next = prev.filter(e=>e.time !== t);
      nextEvents = next;
      syncRangeFromEvents(next);
      return next;
    });
    // v087.29: bulk clear is local only unless individual event handles are deleted. Raw ledger remains append-only.
    setMessage(`Cleared local events on ${shortTime(t, timeframe)}. Use event-handle delete for permanent DELETE_RECORD entries.`);
  };

  const markerIdForCandle = (candle:Candle, type:string) => {
    const safeSymbol = String(symbol || 'SYMBOL').toUpperCase().replace(/[^A-Z0-9]+/g, '');
    const safeTf = String(timeframe || 'TF').toUpperCase().replace(/[^A-Z0-9]+/g, '');
    const safeType = String(type || 'EVENT').toUpperCase().replace(/[^A-Z0-9_]+/g, '_');
    const candleIndex = candles.findIndex(c => c.time === candle.time);
    const idx = candleIndex >= 0 ? candleIndex : new Date(candle.time).getTime();
    return `${safeSymbol}_${safeTf}_${idx}_${safeType}`;
  };

  const upsertMarkerIntoEvents = (ev:MapEvent, replaceType?:string) => {
    // Important: bundle saves can add multiple tags before React gets a chance to re-render.
    // Use a live ref, update it immediately, then commit state. Otherwise Set W High/Low
    // markers draw as dots but the fib engine never receives both anchors. Delightful little trap.
    const currentTf = timeframe;
    const prevEvents = safeArray<MapEvent>(eventsByTfRef.current?.[currentTf]);
    const base = replaceType ? prevEvents.filter(e=>e.event_type !== replaceType) : prevEvents;
    const existingIdx = base.findIndex(e => e.id === ev.id);
    const nextEvents = existingIdx >= 0 ? base.map((e,i)=>i===existingIdx ? ev : e) : [...base, ev];
    eventsByTfRef.current = { ...eventsByTfRef.current, [currentTf]: nextEvents };
    setEventsByTf(prev => ({ ...prev, [currentTf]: nextEvents }));
    return nextEvents;
  };

  const upsertCandleEvent = async (candle:Candle, type:string, priceMode:'high'|'low'|'close'='close', customName?:string, replaceType?:string) => {
    const price = priceMode === 'high' ? candle.high : priceMode === 'low' ? candle.low : candle.close;
    const activeLow = parseNum(rangeByTf[timeframe]?.low || rangeLow);
    const activeHigh = parseNum(rangeByTf[timeframe]?.high || rangeHigh);
    const pct = (Number.isFinite(activeLow) && Number.isFinite(activeHigh) && activeHigh > activeLow) ? zonePercent(price, activeLow, activeHigh) : null;
    const ev:MapEvent = {
      id: markerIdForCandle(candle, type), event_type: type, event_name: customName || type, time: candle.time, price: Number(price.toFixed(2)),
      zone: zoneLabel(pct), zone_percent: pct === null ? undefined : Number(pct.toFixed(2)), notes: '', candle_open: candle.open, candle_high: candle.high, candle_low: candle.low, candle_close: candle.close
    };
    const nextEvents = upsertMarkerIntoEvents(ev, replaceType);
    await saveEvent(ev);
    if (isRangeAnchorMarker(type)) {
      // v086.12: explicit anchor saves update ONLY the chosen side.
      // Do not resync both high+low from the full event ledger here, because an older
      // backend/legacy low can hijack the range when Josh later saves the high. Evil little goblin.
      if (isRangeHighMarker(type)) {
        const nextHigh = String(Number(candle.high).toFixed(2));
        setRangeHigh(nextHigh);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: nextHigh, low: prev[timeframe]?.low || '' } }));
        mergeRangeWindowTime(candle.time);
      }
      if (isRangeLowMarker(type)) {
        const nextLow = String(Number(candle.low).toFixed(2));
        setRangeLow(nextLow);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low: nextLow } }));
        mergeRangeWindowTime(candle.time);
      }
      await saveActiveRange(nextEvents);
    } else if (isRefHighMarker(type) || isRefLowMarker(type)) {
      await saveActiveRange(nextEvents);
    }
    setMessage(`Marked ${ev.event_name} at ${ev.price} · ${shortTime(ev.time, timeframe)} · saved to backend`);
  };

  const addEventAt = async (info:{time?:string; price:number; candle?:Candle|null}) => {
    if (!hasRange) { setMessage('Mark Range High and Low first. Yes, even the map needs coordinates.'); return; }
    const pct = zonePercent(info.price, low, high);
    const ev:MapEvent = {
      id: info.candle ? markerIdForCandle(info.candle, eventType) : `${symbol}_${timeframe}_${new Date(info.time || Date.now()).getTime()}_${eventType}`,
      event_type: eventType,
      event_name: eventName || eventType,
      time: info.time,
      price: Number(info.price.toFixed(2)),
      zone: zoneLabel(pct),
      zone_percent: Number((pct ?? 0).toFixed(2)),
      notes: ''
    };
    const lifecycleLock = htfCandidateLockKey(cand, timeframe, low, high);
    if (lifecycleLock) setHtfAcceptedSuggestionLocks(prev => Array.from(new Set([...(prev || []), lifecycleLock])));
    upsertMarkerIntoEvents(ev);
    await saveEvent(ev);
    setMessage(`Saved ${ev.event_name} at ${ev.price} (${ev.zone}) · ${shortTime(ev.time, timeframe)}`);
  };


  const mergeRangeWindowTime = (time:string) => {
    setRangeWindowByTf(prev => {
      const current = prev[timeframe] || {};
      const times = [current.start, current.end, time].filter(Boolean).map(x => new Date(String(x)).getTime()).filter(Number.isFinite);
      if (!times.length) return prev;
      const start = new Date(Math.min(...times)).toISOString();
      const end = new Date(Math.max(...times)).toISOString();
      return { ...prev, [timeframe]: { start, end } };
    });
  };

  const saveRawMarker = async (side: 'HIGH' | 'LOW' | 'REF', candle: Candle) => {
    if (rawMarkSaving) return;
    setRawMarkSaving(true);

    const localType = side === 'HIGH' ? 'RANGE_HIGH' : side === 'LOW' ? 'RANGE_LOW' : 'SET_ANCHOR_REF';
    const displayMarkerId = markerIdForCandle(candle, localType);
    const eventId = crypto.randomUUID();

    try {
      const caseId = rawActiveCaseId || await ensureRawCase();
      if (!caseId) throw new Error('No raw case id. Save or create a raw case first.');

      const price = side === 'HIGH' ? candle.high : side === 'LOW' ? candle.low : candle.close;
      const candleIdx = candles.findIndex(c => c.time === candle.time);
      const payload = buildRawPayloadJson({
        event_id: eventId,
        case_id: caseId,
        symbol,
        timeframe,
        candle_time_utc_ms: rawCandleTimeMs(candle.time),
        candle_index: candleIdx >= 0 ? candleIdx : null,
        price: Number(price.toFixed(2)),
        event_type: 'SET_ANCHOR',
        semantic_side: side,
        source: 'manual',
        notes: side === 'REF' ? 'Set REF anchor' : `Set ${side} anchor`,
        extra_payload: {
          display_marker_id: displayMarkerId,
          candle_role: side,
          candle_open: candle.open,
          candle_high: candle.high,
          candle_low: candle.low,
          candle_close: candle.close,
          electron_version: 'v087.30_raw_mapping_contract',
        },
      });

      await saveRawEvent(BASE_URL, payload);

      const replaceType = side === 'HIGH' ? 'RANGE_HIGH' : side === 'LOW' ? 'RANGE_LOW' : 'SET_ANCHOR_REF';
      const ev: MapEvent = {
        id: displayMarkerId,
        raw_event_id: eventId,
        event_type: localType,
        event_name: side === 'REF' ? 'Set REF' : localType,
        time: candle.time,
        price: Number(price.toFixed(2)),
        notes: '',
        source: 'manual',
        candle_open: candle.open,
        candle_high: candle.high,
        candle_low: candle.low,
        candle_close: candle.close,
        meta_json: { raw_event_id: eventId, display_marker_id: displayMarkerId, candle_role: side },
      };
      upsertMarkerIntoEvents(ev, replaceType);

      if (side === 'HIGH') {
        const nextHigh = String(Number(candle.high).toFixed(2));
        setRangeHigh(nextHigh);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: nextHigh, low: prev[timeframe]?.low || '' } }));
        mergeRangeWindowTime(candle.time);
      }
      if (side === 'LOW') {
        const nextLow = String(Number(candle.low).toFixed(2));
        setRangeLow(nextLow);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low: nextLow } }));
        mergeRangeWindowTime(candle.time);
      }

      setSessionEventIds(prev => {
        const next = new Set(prev);
        next.add(eventId);
        return next;
      });
      setMessage(`Saved SET_ANCHOR ${side} at ${Number(price).toFixed(2)} · ${shortTime(candle.time, timeframe)}`);
    } catch (err: any) {
      setMessage(`Raw marker save failed: ${err?.message || err}`);
      throw err;
    } finally {
      setRawMarkSaving(false);
    }
  };

  const selectedParentRange = useMemo(() => {
    return safeArray<StructuralRange>(structuralRanges).find(r => String(r.range_id || r.id) === String(selectedParentRangeId)) || null;
  }, [structuralRanges, selectedParentRangeId]);

  useEffect(() => {
    if (structureLayer === 'WEEKLY') setSourceTimeframe('W1');
    if (structureLayer === 'DAILY') setSourceTimeframe('D1');
    if (structureLayer === 'INTRADAY' && !['H1','H4','H8'].includes(String(sourceTimeframe).toUpperCase())) setSourceTimeframe('H1');
  }, [structureLayer]);

  const structuralFetchJson = async (url:string, options?:RequestInit) => {
    const res = await fetch(url, options);
    const data = await res.json().catch(()=>({ ok:false, error:`Invalid backend response ${res.status}` }));
    if (!res.ok || data?.ok === false) throw new Error(data?.error || data?.detail || `Backend request failed ${res.status}`);
    return data;
  };

  const selectedSavedRange = useMemo(() => {
    if (!activeStructuralRangeId) return null;
    return safeArray<StructuralRange>(savedStructuralRanges).find((r:any) => String(r.range_id || r.id) === String(activeStructuralRangeId)) || null;
  }, [savedStructuralRanges, activeStructuralRangeId]);

  const savePreview = useMemo(() => {
    const mappingCase = getCurrentMappingCaseRef();
    const parentId = structureLayer === 'WEEKLY' ? null : (selectedParentRangeId || null);
    return {
      chart_timeframe: timeframe,
      structure_layer: structureLayer,
      source_timeframe: sourceTimeframe,
      case_ref: mappingCase.case_ref,
      raw_case_id: mappingCase.raw_case_id,
      case_id: mappingCase.case_id,
      hasCase: mappingCase.hasCase,
      parent_range_id: parentId,
      range_high_price: rhAnchor.price || null,
      range_high_time: rhAnchor.time || null,
      range_low_price: rlAnchor.price || null,
      range_low_time: rlAnchor.time || null,
      action: activeStructuralRangeId ? 'UPDATE_SELECTED_RANGE' : 'SAVE_NEW_RANGE',
      actionLabel: activeStructuralRangeId ? 'Update Selected Range' : 'Save New Range',
      warning: String(timeframe).toUpperCase() === 'D1' && structureLayer === 'WEEKLY'
        ? 'You are viewing D1 candles but saving a WEEKLY range.'
        : '',
    };
  }, [timeframe, structureLayer, sourceTimeframe, activeCaseId, rawActiveCaseId, activeCaseLabel, selectedParentRangeId, rhAnchor.price, rhAnchor.time, rlAnchor.price, rlAnchor.time, activeStructuralRangeId]);

  const refreshSavedRangesForCurrentCase = async () => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setSavedStructuralRanges([]);
      return [] as StructuralRange[];
    }
    const params = appendMappingCaseParams(new URLSearchParams({ symbol, limit:'5000' }), mappingCase);
    const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/ranges?${params.toString()}`);
    const rows = safeArray<StructuralRange>(data.ranges);
    setSavedStructuralRanges(rows);
    return rows;
  };

  const selectSavedStructuralRange = (range:any) => {
    const id = String(range?.range_id || range?.id || '');
    if (!id) return;
    setActiveStructuralRangeId(id);
    setStructureLayer((String(range.structure_layer || range.layer || structureLayer).toUpperCase() as StructureLayer) || structureLayer);
    if (range.source_timeframe || range.timeframe) setSourceTimeframe(String(range.source_timeframe || range.timeframe).toUpperCase());
    if (range.parent_range_id !== undefined && range.parent_range_id !== null) setSelectedParentRangeId(String(range.parent_range_id));
    const high = range.range_high_price ?? range.range_high;
    const low = range.range_low_price ?? range.range_low;
    if (high !== undefined && high !== null && high !== '') {
      const next = { price:String(high), time:String(range.range_high_time || ''), candle:null };
      setRhAnchor(next);
      setRangeHigh(String(high));
    }
    if (low !== undefined && low !== null && low !== '') {
      const next = { price:String(low), time:String(range.range_low_time || ''), candle:null };
      setRlAnchor(next);
      setRangeLow(String(low));
    }
    setRangeWindowByTf(prev => ({ ...prev, [timeframe]: { ...(prev[timeframe] || {}), start:range.range_start_time || range.range_high_time || prev[timeframe]?.start || '', end:range.range_end_time || range.range_low_time || prev[timeframe]?.end || '' } }));
    setStructuralRangeDraftDirty(false);
    setMessage(`Selected saved range #${id}. Save Range button is now Update Selected Range.`);
  };

  const refreshStructuralRanges = async () => {
    const params = new URLSearchParams({ symbol });
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setStructuralRanges([]);
      setSelectedParentRangeId('');
      setMessage('Create or select a mapping case before loading structural ranges.');
      return;
    }
    appendMappingCaseParams(params, mappingCase);
    if (structureLayer === 'DAILY') {
      params.set('structure_layer', 'WEEKLY');
      params.set('source_timeframe', 'W1');
    } else if (structureLayer === 'INTRADAY') {
      params.set('structure_layer', 'DAILY');
      params.set('source_timeframe', 'D1');
    } else {
      params.set('structure_layer', structureLayer);
      params.set('source_timeframe', sourceTimeframe);
    }
    try {
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/ranges?${params.toString()}`);
      const rows = safeArray<StructuralRange>(data.ranges);
      setStructuralRanges(rows);
      if ((structureLayer === 'DAILY' || structureLayer === 'INTRADAY') && rows.length && !rows.some(r => String(r.range_id || r.id) === String(selectedParentRangeId))) {
        setSelectedParentRangeId(String(rows[0].range_id || rows[0].id || ''));
      }
    } catch (err:any) {
      setMessage(`Load structural ranges failed: ${err?.message || err}`);
    }
  };

  const refreshHierarchyAudit = async () => {
    const params = new URLSearchParams({ symbol });
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setHierarchyAudit(null);
      setMessage('Create or select a mapping case before refreshing audit.');
      return null;
    }
    appendMappingCaseParams(params, mappingCase);
    try {
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/hierarchy-audit?${params.toString()}`);
      setHierarchyAudit(data);
      const s = data?.summary || {};
      const hasErrors = Number(s.invalid_parent_links || 0) > 0 || Number(s.ranges_missing_rh_rl || 0) > 0 || Number(s.bos_events_missing_bh_bl || 0) > 0;
      const hasWarn = Number(s.orphan_daily_ranges || 0) > 0 || Number(s.orphan_intraday_ranges || 0) > 0;
      setMessage(`Hierarchy audit ${hasErrors ? 'FAIL' : hasWarn ? 'WARN' : 'PASS'} · W ${s.weekly_ranges || 0} / D ${s.daily_ranges || 0} / linked ${s.daily_ranges_linked_to_weekly || 0}`);
      return data;
    } catch (err:any) {
      setMessage(`Hierarchy audit failed: ${err?.message || err}`);
      return null;
    }
  };

  useEffect(() => {
    if (rightDeckTab === 'mark' && markWorkspaceMode === 'htf') {
      refreshStructuralRanges();
      refreshSavedRangesForCurrentCase().catch((err:any)=>setMessage(`Load saved ranges failed: ${err?.message || err}`));
    }
  }, [rightDeckTab, markWorkspaceMode, structureLayer, sourceTimeframe, symbol, activeCaseId, rawActiveCaseId]);

  const chartStructureForTimeframe = (tfRaw:string) => {
    const tf = String(tfRaw || 'D1').toUpperCase();
    if (tf === 'W1') return { structure_layer:'WEEKLY' as StructureLayer, source_timeframe:'W1' };
    if (tf === 'D1') return { structure_layer:'DAILY' as StructureLayer, source_timeframe:'D1' };
    if (tf === 'H4') return { structure_layer:'INTRADAY' as StructureLayer, source_timeframe:'H4' };
    if (tf === 'H1') return { structure_layer:'INTRADAY' as StructureLayer, source_timeframe:'H1' };
    if (tf === 'M15') return { structure_layer:'MICRO' as StructureLayer, source_timeframe:'M15' };
    return { structure_layer:'WEEKLY' as StructureLayer, source_timeframe:tf };
  };

  const applyStructuralDraftPoint = (kind:'RH'|'RL'|'BH'|'BL', candle:Candle, next:{price:string; time:string; candle:Candle|null}) => {
    if (kind === 'RH') {
      setRhAnchor(next);
      setRangeHigh(next.price);
      setRangeWindowByTf(prev => {
        const window = timesToWindow([rlAnchor.time, candle.time]);
        return { ...prev, [timeframe]: { ...(prev[timeframe] || {}), ...(window || { start:candle.time, end:candle.time }) }};
      });
      setStructuralRangeDraftDirty(true);
    }
    if (kind === 'RL') {
      setRlAnchor(next);
      setRangeLow(next.price);
      setRangeWindowByTf(prev => {
        const window = timesToWindow([rhAnchor.time, candle.time]);
        return { ...prev, [timeframe]: { ...(prev[timeframe] || {}), ...(window || { start:candle.time, end:candle.time }) }};
      });
      setStructuralRangeDraftDirty(true);
    }
    if (kind === 'BH') {
      setBhAnchor(next);
      setStructuralBosDraftDirty(true);
    }
    if (kind === 'BL') {
      setBlAnchor(next);
      setStructuralBosDraftDirty(true);
    }
    const label = kind === 'RH' ? 'Range High' : kind === 'RL' ? 'Range Low' : kind === 'BH' ? 'Break High' : 'Break Low';
    const viewNote = kind === 'RH' || kind === 'RL' ? 'visible fib range updated; not saved yet' : 'draft marker only; fib range unchanged';
    return { label, viewNote };
  };

  const setStructuralPoint = async (kind:'RH'|'RL'|'BH'|'BL') => {
    if (quickEventSaving) return;
    const candle = selectedCandle || replayCandle;
    if (!candle) { setMessage('Select a candle first, then set RH/RL/BH/BL.'); return; }
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before saving structural quick events.'); return; }
    const chartStructure = chartStructureForTimeframe(timeframe);
    const price = kind === 'RL' || kind === 'BL' ? candle.low : candle.high;
    const next = { price: Number(price).toFixed(2), time: candle.time, candle };
    const previous = {
      RH: rhAnchor,
      RL: rlAnchor,
      BH: bhAnchor,
      BL: blAnchor,
      range: rangeByTf[timeframe] || null,
      window: rangeWindowByTf[timeframe] || null,
    };
    const eventTypeByRole:any = {
      RH: 'RANGE_HIGH_SELECTED',
      RL: 'RANGE_LOW_SELECTED',
      BH: 'BREAK_HIGH_SELECTED',
      BL: 'BREAK_LOW_SELECTED',
    };
    const eventId = crypto.randomUUID();
    const layerWarning = chartStructure.structure_layer !== structureLayer
      ? `Chart timeframe implies ${chartStructure.structure_layer} but active mapping layer is ${structureLayer}. Event will be saved as ${chartStructure.structure_layer} because chart timeframe is ${timeframe}.`
      : '';
    const isBreak = kind === 'BH' || kind === 'BL';
    const payload:any = {
      event_id: eventId,
      case_id: mappingCase.case_id,
      raw_case_id: mappingCase.raw_case_id,
      case_ref: mappingCase.case_ref,
      symbol,
      chart_timeframe: timeframe,
      source_timeframe: chartStructure.source_timeframe,
      structure_layer: chartStructure.structure_layer,
      active_range_id: activeStructuralRangeId || null,
      parent_range_id: chartStructure.structure_layer === 'WEEKLY' ? null : (selectedParentRangeId || null),
      event_type: eventTypeByRole[kind],
      structural_event: eventTypeByRole[kind],
      event_time: candle.time,
      event_price: Number(next.price),
      candle_time: candle.time,
      candle_open: candle.open,
      candle_high: candle.high,
      candle_low: candle.low,
      candle_close: candle.close,
      direction: kind === 'BH' ? 'UP' : kind === 'BL' ? 'DOWN' : null,
      meta_json: {
        role: kind,
        quick_button: true,
        chart_timeframe_wins: true,
        active_mapping_layer_at_click: structureLayer,
        warning: layerWarning || null,
        analytics_ready: chartStructure.structure_layer !== 'MICRO',
        analytics_note: chartStructure.structure_layer === 'MICRO' ? 'MICRO/M15 quick event stored; analytics not ready yet.' : null,
      },
    };
    if (isBreak) {
      payload.break_level_type = kind;
      payload.break_level_price = Number(next.price);
      payload.break_level_time = candle.time;
    }
    setQuickEventSaving(true);
    try {
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/structural-event`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const applied = applyStructuralDraftPoint(kind, candle, next);
      const saved = {
        role: kind,
        event_id: data.event_id || data.event?.event_id || eventId,
        db_id: data.id || data.event?.id || null,
        timeframe,
        structure_layer: chartStructure.structure_layer,
        source_timeframe: chartStructure.source_timeframe,
        candle_time: candle.time,
        event_price: Number(next.price),
        previous,
        payload,
        saved_at: new Date().toISOString(),
      };
      setLastSavedQuickEvent(saved);
      setQuickEventHistory(prev => [...prev, saved].slice(-50));
      setMessage(`Saved ${kind} event ${String(saved.event_id).slice(0,8)} · ${chartStructure.structure_layer}/${chartStructure.source_timeframe} · ${shortTime(candle.time, timeframe)}${layerWarning ? ` · ${layerWarning}` : ` (${applied.viewNote})`}`);
    } catch (err:any) {
      setMessage(`Quick ${kind} event save failed: ${err?.message || err}`);
    } finally {
      setQuickEventSaving(false);
    }
  };

  const undoLastQuickEvent = async () => {
    if (!lastSavedQuickEvent?.event_id || quickEventSaving) return;
    const ev = lastSavedQuickEvent;
    setQuickEventSaving(true);
    try {
      await structuralFetchJson(`${BASE_URL}/api/v1/map/structural-event/${encodeURIComponent(String(ev.event_id))}`, {
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          meta_json: {
            undone: true,
            undone_at: new Date().toISOString(),
            undo_reason: 'quick_undo',
          },
        }),
      });
      const prev = ev.previous || {};
      if (ev.role === 'RH') {
        setRhAnchor(prev.RH || { price:'', time:'' });
        if (prev.range) setRangeByTf((p:any)=>({ ...p, [ev.timeframe]: prev.range }));
        else setRangeHigh(prev.RH?.price || '');
        setRangeWindowByTf((p:any)=>({ ...p, [ev.timeframe]: prev.window || {} }));
      }
      if (ev.role === 'RL') {
        setRlAnchor(prev.RL || { price:'', time:'' });
        if (prev.range) setRangeByTf((p:any)=>({ ...p, [ev.timeframe]: prev.range }));
        else setRangeLow(prev.RL?.price || '');
        setRangeWindowByTf((p:any)=>({ ...p, [ev.timeframe]: prev.window || {} }));
      }
      if (ev.role === 'BH') setBhAnchor(prev.BH || { price:'', time:'' });
      if (ev.role === 'BL') setBlAnchor(prev.BL || { price:'', time:'' });
      if (ev.role === 'RH' || ev.role === 'RL') setStructuralRangeDraftDirty(!!(prev.RH?.price || prev.RL?.price));
      if (ev.role === 'BH' || ev.role === 'BL') setStructuralBosDraftDirty(!!(prev.BH?.price || prev.BL?.price));
      setQuickEventHistory(prevList => prevList.filter((x:any)=>String(x.event_id) !== String(ev.event_id)));
      setLastSavedQuickEvent(null);
      setMessage(`Undid ${ev.role} event on ${ev.timeframe} ${shortTime(ev.candle_time, ev.timeframe)}.`);
    } catch (err:any) {
      setMessage(`Undo last quick event failed: ${err?.message || err}`);
    } finally {
      setQuickEventSaving(false);
    }
  };

  const structuralWindow = () => {
    const times = [rhAnchor.time, rlAnchor.time].filter(Boolean).map(t => new Date(t).getTime()).filter(Number.isFinite);
    if (!times.length) return { start:'', end:'', duration:null as number|null };
    const start = new Date(Math.min(...times)).toISOString();
    const end = new Date(Math.max(...times)).toISOString();
    return { start, end, duration: Math.round(Math.abs(Math.max(...times) - Math.min(...times)) / 60000) };
  };

  const saveStructuralRange = async () => {
    if (structuralSaving) return;
    if (structureLayer === 'INTRADAY' && String(sourceTimeframe).toUpperCase() === 'H8') {
      setMessage('H8 source timeframe is selectable for planning, but backend rendering/storage normalisation is TODO before saving H8.');
      return;
    }
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before saving a range.'); return; }
    if (!rhAnchor.price || !rlAnchor.price) { setMessage('Set Range High and Range Low before saving a structural range.'); return; }
    if (structureLayer === 'DAILY' && !selectedParentRangeId) {
      const ok = window.confirm('No Weekly parent selected. Save this Daily range as ORPHAN?');
      if (!ok) return;
    }
    setStructuralSaving(true);
    try {
      const win = structuralWindow();
      const isUpdate = !!activeStructuralRangeId;
      const safeCaseKey = String(mappingCase.case_ref || mappingCase.raw_case_id || mappingCase.case_id || 'case').replace(/[^0-9A-Za-z_-]+/g, '_');
      const payload = {
        ...(isUpdate ? { range_id: activeStructuralRangeId } : { range_key: `${safeCaseKey}_${structureLayer}_${sourceTimeframe}_${Date.now()}` }),
        case_id: mappingCase.case_id,
        raw_case_id: mappingCase.raw_case_id,
        case_ref: mappingCase.case_ref,
        symbol,
        structure_layer: structureLayer,
        chart_timeframe: timeframe,
        source_timeframe: sourceTimeframe,
        parent_range_id: structureLayer === 'WEEKLY' ? null : (selectedParentRangeId || null),
        range_high_price: Number(rhAnchor.price),
        range_low_price: Number(rlAnchor.price),
        range_high_time: rhAnchor.time || null,
        range_low_time: rlAnchor.time || null,
        range_start_time: win.start || null,
        range_end_time: win.end || null,
        duration_minutes: win.duration,
        status: 'active',
        meta_json: { phase:'electron_phase3_structural_mapping', proof_target:'WEEKLY_DAILY' },
      };
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/range`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const id = String(data.range_id || data.id || data.range?.range_id || data.range?.id || '');
      setActiveStructuralRangeId(id);
      setStructuralRangeDraftDirty(false);
      const confirmation = {
        range_id: id || null,
        mode: isUpdate ? 'updated' : 'created',
        structure_layer: data.range?.structure_layer || structureLayer,
        source_timeframe: data.range?.source_timeframe || sourceTimeframe,
        parent_range_id: data.range?.parent_range_id ?? payload.parent_range_id,
        raw_case_id: data.range?.raw_case_id || mappingCase.raw_case_id,
        case_ref: data.range?.case_ref || mappingCase.case_ref,
        range_high_price: data.range?.range_high_price ?? payload.range_high_price,
        range_low_price: data.range?.range_low_price ?? payload.range_low_price,
      };
      setLastSavedRangeConfirmation(confirmation);
      setMessage(`${isUpdate ? 'Updated selected' : 'Saved new'} ${confirmation.structure_layer} range #${id || '?'} · ${confirmation.source_timeframe} · parent ${confirmation.parent_range_id || 'none'} · RH ${confirmation.range_high_price} / RL ${confirmation.range_low_price}`);
      try { await refreshSavedRangesForCurrentCase(); } catch (refreshErr:any) { setMessage(`Saved range #${id || '?'}; saved-ranges refresh failed: ${refreshErr?.message || refreshErr}`); }
      try { await refreshStructuralRanges(); } catch {}
      try { await refreshHierarchyAudit(); } catch {}
    } catch (err:any) {
      setMessage(`Range save failed: ${err?.message || err}`);
    } finally {
      setStructuralSaving(false);
    }
  };

  const saveStructuralBos = async (direction:'UP'|'DOWN') => {
    if (structuralSaving) return;
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before saving BOS.'); return; }
    const anchor = direction === 'UP' ? bhAnchor : blAnchor;
    if (!anchor.price) { setMessage(`Set ${direction === 'UP' ? 'BH' : 'BL'} before saving BOS_${direction}.`); return; }
    const chartStructure = chartStructureForTimeframe(timeframe);
    if (!activeStructuralRangeId) { setMessage(`Select or save the active ${chartStructure.structure_layer} range before saving BOS_${direction}.`); return; }
    if (chartStructure.structure_layer === 'DAILY' && !selectedParentRangeId) { setMessage(`Select the Weekly parent range before saving Daily BOS_${direction}.`); return; }
    setStructuralSaving(true);
    try {
      const candle = anchor.candle || selectedCandle || replayCandle;
      if (!candle) { throw new Error(`Select a candle or set ${direction === 'UP' ? 'BH' : 'BL'} from a candle before saving BOS_${direction}.`); }
      const sourceBreakRole = direction === 'UP' ? 'BH' : 'BL';
      const sourceBreakEvent = [...quickEventHistory].reverse().find((ev:any) =>
        ev?.role === sourceBreakRole &&
        String(ev?.candle_time || '') === String(anchor.time || candle.time || '') &&
        String(ev?.source_timeframe || '') === String(chartStructure.source_timeframe)
      ) || (lastSavedQuickEvent?.role === sourceBreakRole ? lastSavedQuickEvent : null);
      const payload = {
        event_id: crypto.randomUUID(),
        case_id: mappingCase.case_id,
        raw_case_id: mappingCase.raw_case_id,
        case_ref: mappingCase.case_ref,
        symbol,
        structure_layer: chartStructure.structure_layer,
        chart_timeframe: timeframe,
        source_timeframe: chartStructure.source_timeframe,
        active_range_id: activeStructuralRangeId || null,
        parent_range_id: chartStructure.structure_layer === 'WEEKLY' ? null : (selectedParentRangeId || null),
        event_type: direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN',
        structural_event: direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN',
        break_level_type: direction === 'UP' ? 'BH' : 'BL',
        break_level_price: Number(anchor.price),
        break_level_time: anchor.time || null,
        event_time: anchor.time || candle?.time || new Date().toISOString(),
        event_price: Number(anchor.price),
        candle_time: candle?.time || anchor.time || null,
        candle_open: candle?.open ?? null,
        candle_high: candle?.high ?? null,
        candle_low: candle?.low ?? null,
        candle_close: candle?.close ?? null,
        direction,
        meta_json: {
          phase:'electron_phase3_structural_mapping',
          role: direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN',
          formal_bos: true,
          formal_bos_event: true,
          quick_marker_role_source: direction === 'UP' ? 'BH' : 'BL',
          created_from_break_marker_event_id: sourceBreakEvent?.event_id || null,
          parent_break_not_updated: true,
          parent_break_note: 'Weekly parent BH/BL is updated only by the later Parent Break action.',
        },
      };
      const data = await structuralFetchJson(`${BASE_URL}/api/v1/map/structural-event`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const returned = data?.event || data || {};
      const expectedType = direction === 'UP' ? 'BOS_UP' : 'BOS_DOWN';
      const validationErrors:string[] = [];
      if (String(returned.event_type || '').toUpperCase() !== expectedType) validationErrors.push(`event_type=${returned.event_type || 'missing'}`);
      if (String(returned.structural_event || '').toUpperCase() !== expectedType) validationErrors.push(`structural_event=${returned.structural_event || 'missing'}`);
      if (mappingCase.raw_case_id && String(returned.raw_case_id || '') !== String(mappingCase.raw_case_id)) validationErrors.push('raw_case_id missing/mismatch');
      if (mappingCase.case_ref && String(returned.case_ref || '') !== String(mappingCase.case_ref)) validationErrors.push('case_ref missing/mismatch');
      if (String(returned.active_range_id || '') !== String(activeStructuralRangeId)) validationErrors.push('active_range_id missing/mismatch');
      if (payload.parent_range_id && String(returned.parent_range_id || '') !== String(payload.parent_range_id)) validationErrors.push('parent_range_id missing/mismatch');
      if (String(returned.break_level_type || '').toUpperCase() !== String(payload.break_level_type)) validationErrors.push('break_level_type missing/mismatch');
      if (validationErrors.length) {
        throw new Error(`Backend saved BOS through wrong/unlinked path: ${validationErrors.join(', ')}`);
      }
      setStructuralBosDraftDirty(false);
      setMessage(`Saved formal BOS_${direction} event ${String(data.event_id || data.event?.event_id || '').slice(0,8)} · ${chartStructure.structure_layer}/${chartStructure.source_timeframe} · active range #${activeStructuralRangeId} · parent ${payload.parent_range_id || 'none'}`);
      await refreshHierarchyAudit();
    } catch (err:any) {
      setMessage(`BOS_${direction} save failed: ${err?.message || err}`);
    } finally {
      setStructuralSaving(false);
    }
  };

  const downloadJsonFile = (payload:any, filename:string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type:'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(()=>URL.revokeObjectURL(url), 500);
  };

  const fetchCurrentMappingSnapshot = async () => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) {
      setMessage('Create or select a mapping case before exporting mapping JSON.');
      return null;
    }
    const baseParams = appendMappingCaseParams(new URLSearchParams({ symbol, limit:'5000' }), mappingCase);
    const [rangesData, treeData, auditData] = await Promise.all([
      structuralFetchJson(`${BASE_URL}/api/v1/map/ranges?${baseParams.toString()}`),
      structuralFetchJson(`${BASE_URL}/api/v1/map/range-tree?${appendMappingCaseParams(new URLSearchParams({ symbol }), mappingCase).toString()}`),
      structuralFetchJson(`${BASE_URL}/api/v1/map/hierarchy-audit?${appendMappingCaseParams(new URLSearchParams({ symbol }), mappingCase).toString()}`),
    ]);
    const refreshedSavedRanges = safeArray<StructuralRange>(rangesData.ranges);
    setSavedStructuralRanges(refreshedSavedRanges);
    const eventParams = appendMappingCaseParams(new URLSearchParams({ symbol, limit:'5000' }), mappingCase);
    const eventsData = await structuralFetchJson(`${BASE_URL}/api/v1/map/events?${eventParams.toString()}`);
    const savedEvents = safeArray<any>(eventsData.events);
    const formalBosEvents = savedEvents.filter((ev:any)=>['BOS_UP','BOS_DOWN'].includes(String(ev.event_type || ev.structural_event || '').toUpperCase()));
    const quickMarkerEvents = savedEvents.filter((ev:any)=>['RANGE_HIGH_SELECTED','RANGE_LOW_SELECTED','BREAK_HIGH_SELECTED','BREAK_LOW_SELECTED'].includes(String(ev.event_type || ev.structural_event || '').toUpperCase()));
    const eventsTodo = null;
    return { mappingCase, rangesData, refreshedSavedRanges, treeData, auditData, eventsData, formalBosEvents, quickMarkerEvents, eventsTodo };
  };

  const exportAuditJson = async () => {
    const mappingCase = getCurrentMappingCaseRef();
    if (!mappingCase.hasCase) { setMessage('Create or select a mapping case before exporting audit JSON.'); return; }
    const audit = hierarchyAudit || await refreshHierarchyAudit();
    if (!audit) return;
    downloadJsonFile({
      generated_at: new Date().toISOString(),
      symbol,
      timeframe,
      structure_layer: structureLayer,
      source_timeframe: sourceTimeframe,
      active_case_ref: mappingCase,
      hierarchy_audit: audit,
      note: 'Audit export reads backend state only; it does not save drafts.',
    }, `hierarchy_audit_${String(symbol)}_${String(mappingCase.case_ref || 'case').replace(/[^a-zA-Z0-9_-]+/g,'_')}.json`);
    setMessage('Exported hierarchy audit JSON. Export does not save drafts.');
  };

  const exportCurrentMappingJson = async () => {
    try {
      const snapshot = await fetchCurrentMappingSnapshot();
      if (!snapshot) return;
      const payload = {
        generated_at: new Date().toISOString(),
        symbol,
        timeframe,
        structure_layer: structureLayer,
        source_timeframe: sourceTimeframe,
        active_case_ref: snapshot.mappingCase,
        current_case_container: activeMappingCaseContainer,
        draft_anchors: {
          RH: rhAnchor,
          RL: rlAnchor,
          BH: bhAnchor,
          BL: blAnchor,
        },
        saved_structural_ranges: snapshot.rangesData,
        saved_ranges_for_current_case: snapshot.refreshedSavedRanges,
        saved_structural_events: snapshot.eventsData,
        saved_structural_events_todo: snapshot.eventsTodo,
        formal_bos_events: snapshot.formalBosEvents,
        quick_marker_events: snapshot.quickMarkerEvents,
        last_saved_quick_event: lastSavedQuickEvent,
        quick_events_tracked_this_session: quickEventHistory,
        range_tree: snapshot.treeData,
        hierarchy_audit: snapshot.auditData,
        chart_context: {
          selected_candle: selectedCandle,
          replay_candle: replayCandle,
          replay_index: effectiveReplayIndex,
          replay_time: candleReplayCursorTime,
          camera_mode: cameraMode,
          parent_range_id: selectedParentRangeId || null,
          active_structural_range_id: activeStructuralRangeId || null,
        },
        note: 'Current Mapping export writes a JSON file only; it does not save RH/RL/BH/BL drafts.',
      };
      downloadJsonFile(payload, `current_mapping_${String(symbol)}_${String(snapshot.mappingCase.case_ref || 'case').replace(/[^a-zA-Z0-9_-]+/g,'_')}.json`);
      setHierarchyAudit(snapshot.auditData);
      setMessage('Exported current mapping JSON. Export does not save drafts.');
    } catch (err:any) {
      setMessage(`Current mapping export failed: ${err?.message || err}`);
    }
  };

  const addTypedEventFromCandle = async (candle:Candle, type:string, priceMode:'high'|'low'|'close'='close', customName?:string) => {
    const price = priceMode === 'high' ? candle.high : priceMode === 'low' ? candle.low : candle.close;
    const activeLow = parseNum(rangeByTf[timeframe]?.low || rangeLow);
    const activeHigh = parseNum(rangeByTf[timeframe]?.high || rangeHigh);
    const pct = (Number.isFinite(activeLow) && Number.isFinite(activeHigh) && activeHigh > activeLow) ? zonePercent(price, activeLow, activeHigh) : null;
    const ev:MapEvent = {
      id: markerIdForCandle(candle, type),
      event_type: type,
      event_name: customName || type,
      time: candle.time,
      price: Number(price.toFixed(2)),
      zone: zoneLabel(pct),
      zone_percent: pct === null ? undefined : Number(pct.toFixed(2)),
      notes: ''
    };
    const nextEvents = upsertMarkerIntoEvents(ev);
    await saveEvent(ev);
    if (isRangeAnchorMarker(type)) {
      // v086.12: explicit anchor saves update ONLY the chosen side.
      // Do not resync both high+low from the full event ledger here, because an older
      // backend/legacy low can hijack the range when Josh later saves the high. Evil little goblin.
      if (isRangeHighMarker(type)) {
        const nextHigh = String(Number(candle.high).toFixed(2));
        setRangeHigh(nextHigh);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: nextHigh, low: prev[timeframe]?.low || '' } }));
        mergeRangeWindowTime(candle.time);
      }
      if (isRangeLowMarker(type)) {
        const nextLow = String(Number(candle.low).toFixed(2));
        setRangeLow(nextLow);
        setRangeByTf(prev => ({ ...prev, [timeframe]: { high: prev[timeframe]?.high || '', low: nextLow } }));
        mergeRangeWindowTime(candle.time);
      }
      await saveActiveRange(nextEvents);
    } else if (isRefHighMarker(type) || isRefLowMarker(type)) {
      await saveActiveRange(nextEvents);
    }
    setMessage(`Marked ${ev.event_name} at ${ev.price} · ${shortTime(ev.time, timeframe)} · saved to backend`);
  };


  const togglePendingMarkerRole = (role:string) => {
    if (!selectedCandle) { setMessage('Click a candle first, then choose events. Revolutionary sequence, apparently.'); return; }
    setPendingMarkerRoles(prev => prev.includes(role) ? prev.filter(x => x !== role) : [...prev, role]);
  };

  const clearPendingMarkerSelection = () => {
    setPendingMarkerRoles([]);
  };

  const savePendingMarkersToNarrative = async () => {
    const candle = selectedCandle;
    if (bundleSaving) { setMessage('Bundle save already running. Double-click ignored.'); return; }
    if (!candle) { setMessage('No candle selected. The machine cannot save air.'); return; }
    if (!pendingMarkerRoles.length) { setMessage('Select at least one event before saving. The save button is not a fortune teller.'); return; }
    setBundleSaving(true);
    const rolesToSave = [...pendingMarkerRoles];
    try {
      for (const role of rolesToSave) {
        await markCandleRole(role, candle, { keepSelection: true });
      }
      setMessage(`Saved ${rolesToSave.length} event${rolesToSave.length === 1 ? '' : 's'} to event ledger · ${shortTime(candle.time, timeframe)}.`);
      setPendingMarkerRoles([]);
    } finally {
      setBundleSaving(false);
    }
  };

  const markCandleRole = async (role:string, candle:Candle, opts?:{keepSelection?:boolean}) => {
    setCandleMenu(null);
    if (!opts?.keepSelection) setSelectedCandle(candle);
    if (role === 'NONE') { clearSelectedCandleEvents(); return; }
    if (role === 'RANGE_HIGH') return saveRawMarker('HIGH', candle);
    if (role === 'RANGE_LOW') return saveRawMarker('LOW', candle);
    if (role === 'REF_HIGH_TAKEN' || role === 'REF_LOW_TAKEN') return saveRawMarker('REF', candle);
    if (role === 'INTERNAL_SWEEP_HIGH') return addTypedEventFromCandle(candle, 'INTERNAL_SWEEP_HIGH', 'high');
    if (role === 'INTERNAL_SWEEP_LOW') return addTypedEventFromCandle(candle, 'INTERNAL_SWEEP_LOW', 'low');
    if (role === 'EXTERNAL_SWEEP_HIGH') return addTypedEventFromCandle(candle, 'EXTERNAL_SWEEP_HIGH', 'high');
    if (role === 'EXTERNAL_SWEEP_LOW') return addTypedEventFromCandle(candle, 'EXTERNAL_SWEEP_LOW', 'low');
    if (role === 'INTERNAL_REJECTION_HIGH') return addTypedEventFromCandle(candle, 'INTERNAL_REJECTION_HIGH', 'high');
    if (role === 'INTERNAL_REJECTION_LOW') return addTypedEventFromCandle(candle, 'INTERNAL_REJECTION_LOW', 'low');
    if (role === 'EXTREME_DISCOUNT_LOW') return addTypedEventFromCandle(candle, 'EXTREME_DISCOUNT_LOW', 'low');
    if (role === 'BELOW_FAIR_PRICE_LOW') return addTypedEventFromCandle(candle, 'BELOW_FAIR_PRICE_LOW', 'low');
    if (role === 'ABOVE_FAIR_PRICE_HIGH') return addTypedEventFromCandle(candle, 'ABOVE_FAIR_PRICE_HIGH', 'high');
    if (role === 'EXTREME_PREMIUM_HIGH') return addTypedEventFromCandle(candle, 'EXTREME_PREMIUM_HIGH', 'high');
    if (role === 'RECLAIM_HIGH') return addTypedEventFromCandle(candle, 'RECLAIM_HIGH', 'close');
    if (role === 'RECLAIM_LOW') return addTypedEventFromCandle(candle, 'RECLAIM_LOW', 'close');
    if (role === 'BOS_UP') return addTypedEventFromCandle(candle, 'BOS_UP', 'close');
    if (role === 'BOS_DOWN') return addTypedEventFromCandle(candle, 'BOS_DOWN', 'close');
    if (role === 'CHOCH_UP') return addTypedEventFromCandle(candle, 'CHOCH_UP', 'close');
    if (role === 'CHOCH_DOWN') return addTypedEventFromCandle(candle, 'CHOCH_DOWN', 'close');
    if (role === 'P1') return addTypedEventFromCandle(candle, 'P1', 'close');
    if (role === 'P2') return addTypedEventFromCandle(candle, 'P2', 'close');
    if (role === 'P3') return addTypedEventFromCandle(candle, 'P3', 'close');
    if (role === 'CUSTOM') return addTypedEventFromCandle(candle, eventType, 'close', eventName || eventType);
    return addTypedEventFromCandle(candle, role, markerPriceMode(role), markerLabel(role));
  };

  const updateEvent = (id:string, patch:Partial<MapEvent>) => {
    setEventsForTf(prev=>prev.map(e=>e.id===id ? { ...e, ...patch } : e));
  };

  const finishEventDrag = async (ev:MapEvent) => {
    await saveEvent(ev);
    setMessage(`Updated ${ev.event_name} · ${ev.price} · ${ev.zone} · ${shortTime(ev.time, timeframe)}`);
  };

  const goToDate = () => {
    if (!jumpDate) { setMessage('Pick a date first. Time travel needs a destination, tragically.'); return; }
    setFitToken(x=>x+1);
  };

  const loadTimeline = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/market-gps/W1/timeline?symbol=${encodeURIComponent(symbol)}`);
      const data = await res.json();
      setGpsTimeline(Array.isArray(data?.nodes) ? data.nodes : []);
    } catch (err) {
      setGpsTimeline([]);
    }
  };

  const applyPlaybackFrame = (frame: PlaybackFrame | null, index = playbackIndex) => {
    if (!frame) return;
    const [phaseNum, ...partBits] = String(frame.phase || 'P1_RETEST').split('_');
    const phasePart = partBits.join('_') || 'RETEST';
    setReplayMode(true);
    setPlaybackIndex(index);
    setGpsMode('active');
    setGpsStoryId(String(frame.story_id || playbackStoryId || ''));
    setGpsParentMode(frame.parent_context_mode || 'WEEKLY_ACTIVE_PARENT');
    setGpsDailyRangeStatus(frame.daily_range_status || 'DAILY_RANGE_ACTIVE');
    setGpsLifecycleState(frame.lifecycle_state || 'EXPANSION');
    setGpsPhaseNumber(phaseNum || 'P1');
    setGpsPhasePart(phasePart);
    setGpsProfileType(frame.profile_type || 'NO_RECLAIM_CONTINUATION_PROFILE');
    setGpsObjective(frame.objective_code || 'DAILY_PREMIUM');
    setGpsCurrentZone(frame.current_zone || 'DAILY_DISCOUNT');
    setGpsTriggerEvent(frame.trigger_event || 'PLAYBACK_FRAME');
    setGpsExpectedNextEvent(frame.expected_next_event || 'PENDING_MARKET_DELIVERY');
    setGpsInvalidationCondition(frame.invalidation_condition || 'MANUAL_INVALIDATION_REQUIRED');
    setGps({
      ok: true,
      status: `PLAYBACK_FRAME_${index + 1}`,
      symbol,
      timeframe: 'W1',
      coordinates: {
        story_anchor: `PLAYBACK_STORY_${frame.story_id}`,
        anchor_class: 'PLAYBACK',
        chapter: frame.trigger_event,
        parent_context_mode: frame.parent_context_mode,
        daily_range_status: frame.daily_range_status,
        lifecycle_state: frame.lifecycle_state,
        phase: phaseNum || 'P1',
        phase_part: phasePart,
        profile_type: frame.profile_type,
        objective: frame.objective_code,
        current_zone: frame.current_zone,
        last_updated: frame.frame_timestamp,
      }
    });
    setMessage(`Replay frame ${index + 1}/${playbackFrames.length || '?'} · ${frame.lookahead_result || 'RAW'} · ${frame.trigger_event}`);
  };

  const setPlaybackFrameIndex = (index:number) => {
    const safe = clamp(index, 0, Math.max(0, playbackFrames.length - 1));
    applyPlaybackFrame(playbackFrames[safe] || null, safe);
  };

  const loadPlayback = async (storyId = playbackStoryId) => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mos/playback/${encodeURIComponent(storyId)}?evaluate=true`);
      const data = await res.json();
      const frames = Array.isArray(data?.frames) ? data.frames : [];
      setPlaybackFrames(frames);
      setPlaybackIndex(0);
      setPlaybackPlaying(false);
      setReplayMode(true);
      if (frames[0]) setTimeout(()=>applyPlaybackFrame(frames[0], 0), 0);
      setMessage(frames.length ? `Loaded ${frames.length} replay frames for story ${storyId}.` : `No replay frames for story ${storyId}.`);
    } catch (err:any) {
      setPlaybackFrames([]);
      setPlaybackIndex(0);
      setPlaybackPlaying(false);
      setMessage(`Playback load failed: ${err?.message || err}`);
    }
  };

  const seedCase03Frames = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mos/seed/case-03-frames`, { method:'POST' });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || data?.detail || 'Seed failed');
      setPlaybackStoryId('3');
      await loadPlayback('3');
      setMessage(`Seeded Case 03 with ${data.frames || 0} frames. The ledger has rent money now.`);
    } catch (err:any) {
      setMessage(`Case 03 seed failed: ${err?.message || err}`);
    }
  };

  const setCandleReplayFrame = (index:number) => {
    if (!candles.length) return;
    const safe = clamp(index, 0, candles.length - 1);
    setCandleReplayMode(true);
    setCandleReplayIndex(safe);
    const c = candles[safe];
    setCandleReplayCursorTime(c.time);
    setSelectedCandle(c);
    setPendingMarkerRoles([]);
    // v082: replay stepping must NOT mutate jumpDate or fitToken.
    // Those controls intentionally reset/recenter the map, which made every replay step zoom out.
    // Replay cursor is data state; chart camera is user state. Keep them decoupled.
    setMessage(`Candle replay ${safe + 1}/${candles.length} · ${shortTime(c.time, timeframe)} · H ${c.high.toFixed(2)} L ${c.low.toFixed(2)}`);
  };

  // v087.22b: chart scrub passes a candle timestamp, not an index.
  // Keep this wrapper separate so MapStudio never crashes if the callback is invoked from the chart.
  const setCandleReplayFrameByTime = (time:string) => {
    if (!candles.length || !time) return;
    const idx = candleIndexAtOrBefore(candles, time);
    const safe = clamp(idx, 0, candles.length - 1);
    const c = candles[safe];
    if (!c) return;
    setCandleReplayMode(true);
    setCandleReplayIndex(safe);
    setCandleReplayCursorTime(c.time);
    setSelectedCandle(c);
    setPendingMarkerRoles([]);
    setMessage(`Replay scrubbed to ${shortTime(c.time, timeframe)} · ${safe + 1}/${candles.length}`);
  };

  const jumpCandleReplayLatest = () => {
    if (!candles.length) return;
    setCandleReplayFrame(candles.length - 1);
  };

  const captureSeedAnchor = (key:string, mode:'high'|'low') => {
    const c = selectedCandle || replayCandle;
    if (!c) { setMessage('Select a candle first. The machine cannot mark ghosts, sadly.'); return; }
    const price = mode === 'high' ? c.high : c.low;
    setSeedAnchors((prev:any)=>({ ...prev, [key]: Number(price.toFixed(2)), [`${key}_time`]: c.time }));
    if (key === 'weekly_high' || key === 'daily_high') setRangeHigh(String(Number(price.toFixed(2))));
    if (key === 'weekly_low' || key === 'daily_low') setRangeLow(String(Number(price.toFixed(2))));
    setMessage(`Captured ${key.replace('_',' ').toUpperCase()} at ${price.toFixed(2)} from ${shortTime(c.time, timeframe)}.`);
  };

  const samePrice = (a:any,b:any) => {
    const x = parseNum(a); const y = parseNum(b);
    return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x-y) < 0.01;
  };

  const caseDedupeKey = () => {
    const c = selectedCandle || replayCandle;
    const parts = [
      symbol, caseScope, caseTimeframe,
      c?.time || 'NO_CANDLE',
      String(caseHigh || '').trim() || 'NO_HIGH',
      String(caseLow || '').trim() || 'NO_LOW',
      String(seedName || '').trim().toUpperCase() || 'NO_NAME'
    ];
    return parts.join('|');
  };

  const resetActiveCase = () => {
    const tf = caseTimeframe || timeframe;
    setActiveCaseId(null);
    setRawActiveCaseId('');
    setActiveCaseLabel('');
    setCaseSavedNotice('');
    // v087.29b: Clear the entire local case draft, not only the case id.
    // Old range windows must not survive Cancel/Clear and anchor the next box to stale history.
    setSeedAnchors((prev:any)=>{
      const next = { ...prev };
      [
        'case_high','case_low','case_high_time','case_low_time',
        'range_start_date','range_end_date',
        'weekly_high','weekly_low','weekly_high_time','weekly_low_time',
        'daily_high','daily_low','daily_high_time','daily_low_time',
        'macro_high','macro_low','macro_high_time','macro_low_time'
      ].forEach(k => { delete next[k]; });
      next.case_scope = caseScope;
      next.case_timeframe = tf;
      return next;
    });
    setRangeByTf((prev:any)=>({ ...prev, [tf]: { high:'', low:'' } }));
    setRangeWindowByTf((prev:any)=>({ ...prev, [tf]: {} }));
    setCameraDomainByCaseTf((prev:any)=>{
      const next = { ...(prev || {}) };
      Object.keys(next).forEach(k => { if (String(k).includes(`_${tf}`) || String(k).startsWith('global_')) delete next[k]; });
      return next;
    });
    setMessage('Active case and local draft window cleared. Next Save Case starts fresh; raw event ledger remains untouched.');
  };

  // v087.27: when a case is first saved after H/L were plotted before the case existed,
  // create clean linked anchor rows for the case. Otherwise the audit says "0 events" while the chart
  // plainly has a parent range. Software gaslighting, now reduced.
  const saveCaseAnchorEventDirect = async (tf:string, type:'RANGE_HIGH'|'RANGE_LOW', price:any, time:any, caseId:number) => {
    const n = Number(price);
    if (!Number.isFinite(n) || !caseId) return;
    const eventTime = String(time || selectedCandle?.time || replayCandle?.time || candleReplayCursorTime || new Date().toISOString());
    const id = `${symbol}_${String(tf).toUpperCase()}_${String(eventTime).replace(/[^0-9A-Za-z]+/g,'')}_${type}_CASE_${caseId}`;
    const structural = type;
    const meta = { case_id: caseId, timeframe: String(tf).toUpperCase(), layer: String(tf).toUpperCase(), structural_event: structural, case_anchor_autolink: true };
    try {
      await fetch(`${BASE_URL}/api/v1/map/event`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
        symbol, timeframe: String(tf).toUpperCase(), case_id: caseId, layer: String(tf).toUpperCase(), structural_event: structural,
        client_event_id: id, id, event_type: type, event_name: type, time: eventTime, price: Number(n.toFixed(2)), notes:'Case-linked range anchor.', meta_json: JSON.stringify(meta)
      })});
    } catch { /* anchor auto-link is helpful, not a hostage situation */ }
  };

  const saveSeedIdea = async (_saveAsNew = false) => {
    if (caseSaving) return;
    setCaseSaving(true);
    setCaseSavedNotice('');
    try {
      const rawId = await ensureRawCase();
      if (!rawId) throw new Error('No raw case id returned');
      const savedMsg = `Raw ${scopeLabel(caseScope)} case ready: ${rawId.slice(0,8)}.`;
      setCaseSavedNotice(savedMsg);
      await loadSeedIdeas();
      setSeedIdeas(prev => mergeRecentCases(prev, rawCaseRecentRow(rawId)));
      setMessage(`${savedMsg} Case Save now creates/uses raw_mapping_cases only. It does not send old bundled map events.`);
      setTimeout(()=>setCaseSavedNotice(''), 6000);
    } catch (err:any) {
      setMessage(`Raw case save failed: ${err?.message || err}`);
    } finally {
      setCaseSaving(false);
    }
  };

  const loadSeedIdeas = async () => {
    try {
      const data = await fetch(`${BASE_URL}/api/v1/mos/seed-ideas?symbol=${encodeURIComponent(symbol)}&limit=12`).then(r=>r.json());
      setSeedIdeas(mergeRecentCases(Array.isArray(data?.ideas) ? data.ideas : []));
    } catch { setSeedIdeas(mergeRecentCases([])); }
  };


  const savedCaseWindow = (idea:any) => {
    const anchors = idea?.anchors || idea?.mos_payload?.anchors || {};
    const start = idea?.range_start_date || anchors?.range_start_date || idea?.case_high_time || anchors?.case_high_time || idea?.replay_candle_time || '';
    const end = idea?.range_end_date || anchors?.range_end_date || idea?.case_low_time || anchors?.case_low_time || idea?.replay_candle_time || '';
    return { start: start || '', end: end || '' };
  };

  const normalizeBackendEvent = (e:any): MapEvent | null => {
    const meta = (() => { try { return typeof e?.meta_json === 'string' ? JSON.parse(e.meta_json) : (e?.meta || e?.meta_json || {}); } catch { return e?.meta_json || {}; } })();
    const price = Number(e?.price);
    const event_type = String(e?.event_type || e?.event_name || '').toUpperCase();
    if (!event_type || !Number.isFinite(price)) return null;
    return {
      id: String(e?.id || e?.client_event_id || cryptoId()),
      event_type,
      event_name: e?.event_name || markerLabel(event_type),
      time: e?.time || meta?.time || new Date().toISOString(),
      price,
      zone: e?.zone || '',
      zone_percent: e?.zone_percent === null || e?.zone_percent === undefined ? undefined : Number(e.zone_percent),
      notes: e?.notes || '',
      source: e?.source || 'backend_case_payload',
      primitive: e?.primitive || undefined,
      derived_event_code: e?.derived_event_code || undefined,
      movement_rule: e?.movement_rule || undefined,
      range_status_after: e?.range_status_after || undefined,
      engine_source: e?.engine_source || undefined,
      logic_version: e?.logic_version || undefined,
      candidate_id: e?.candidate_id || undefined,
      confidence: e?.confidence || undefined,
      meta_json: meta,
      candle_open: e?.candle_open === null || e?.candle_open === undefined ? undefined : Number(e.candle_open),
      candle_high: e?.candle_high === null || e?.candle_high === undefined ? undefined : Number(e.candle_high),
      candle_low: e?.candle_low === null || e?.candle_low === undefined ? undefined : Number(e.candle_low),
      candle_close: e?.candle_close === null || e?.candle_close === undefined ? undefined : Number(e.candle_close),
    } as any;
  };

  const switchTimeframePreserveCase = (nextTf:string) => {
    const tf = String(nextTf || timeframe).toUpperCase();
    const targetTime = selectedCandle?.time || candleReplayCursorTime || replayCandle?.time || null;
    const intent:CameraIntent = cameraMode === 'LOCKED'
      ? 'RESTORE_LOCKED'
      : cameraMode === 'CASE'
        ? 'CASE'
        : cameraMode === 'REPLAY'
          ? 'REPLAY'
          : 'PRESERVE_OR_NEAREST_TIME';
    cameraLog('timeframe switch start', { from:timeframe, to:tf, intent, targetTime });
    pendingCameraIntentRef.current = { intent, targetTime, reason:`timeframe-switch:${timeframe}->${tf}` };
    const w = activeCaseRecord ? savedCaseWindow(activeCaseRecord) : { start: rangeWindow.start || seedAnchors.range_start_date || '', end: rangeWindow.end || seedAnchors.range_end_date || '' };
    if (w.start || w.end) setRangeWindowByTf(prev => ({ ...prev, [tf]: { ...(prev[tf] || {}), start: w.start || prev[tf]?.start || '', end: w.end || prev[tf]?.end || '' } }));
    activeTimeframeRef.current = tf;
    setTimeframe(tf);
  };

  const openSavedCase = async (idea:any, preferredTf?:string) => {
    if (!idea?.id) return;
    if (idea?.is_raw_mapping_case || idea?.raw_case_id) {
      const rawId = String(idea.raw_case_id || idea.id || '');
      if (!rawId) return;
      const nextTf = String(preferredTf || idea.case_timeframe || idea.replay_timeframe || idea?.raw_case?.base_timeframe || caseTimeframe || timeframe).toUpperCase();
      const nextScope = String(idea.case_scope || timeframeToScope(nextTf) || caseScope).toUpperCase() as CaseScope;
      setRawActiveCaseId(rawId);
      setActiveCaseId(null);
      setActiveCaseLabel(`${idea.seed_name || 'Raw Case'} · ${rawId.slice(0, 8)}`);
      setSeedName(idea.seed_name || seedName);
      setSeedNotes(idea.notes || '');
      setCaseScope(nextScope);
      setSeedAnchors((prev:any)=>({ ...prev, case_scope: nextScope, case_timeframe: nextTf }));
      setHistoryMarkMode('ACTIVE_CASE');
      pendingCameraIntentRef.current = { intent: cameraMode === 'LOCKED' ? 'RESTORE_LOCKED' : 'PRESERVE_OR_NEAREST_TIME', targetTime: idea.replay_candle_time || selectedCandle?.time || candleReplayCursorTime || null, reason:'open-raw-case' };
      activeTimeframeRef.current = nextTf;
      setTimeframe(nextTf);
      setSeedIdeas(prev => mergeRecentCases(prev, rawCaseRecentRow(rawId, idea.raw_case)));
      setMessage(`Opened raw Case ${rawId.slice(0,8)}. Raw H/L/REF markers will save to this active ledger.`);
      return;
    }
    const id = Number(idea.id);
    setRawActiveCaseId('');
    setActiveCaseId(id);
    setActiveCaseLabel(`#${id} ${idea.seed_name || 'Case'}`);
    setSeedName(idea.seed_name || seedName);
    setSeedNotes(idea.notes || '');
    const anchors = { ...(idea.anchors || {}) };
    const w = savedCaseWindow(idea);
    const nextScope = String(idea.case_scope || idea?.mos_payload?.case_scope || caseScope).toUpperCase() as CaseScope;
    const nextTf = String(preferredTf || idea.case_timeframe || idea.replay_timeframe || idea?.mos_payload?.case_timeframe || scopeToTimeframe(nextScope)).toUpperCase();
    const high = idea.case_high ?? anchors.case_high ?? anchors.weekly_high ?? anchors.daily_high ?? '';
    const low = idea.case_low ?? anchors.case_low ?? anchors.weekly_low ?? anchors.daily_low ?? '';
    setCaseScope(nextScope);
    setSeedAnchors((prev:any)=>({ ...prev, ...anchors, case_scope: nextScope, case_timeframe: nextTf, case_high: high || prev.case_high || '', case_low: low || prev.case_low || '', range_start_date: w.start || prev.range_start_date || '', range_end_date: w.end || prev.range_end_date || '' }));
    if (high || low) setRangeByTf(prev => ({ ...prev, [nextTf]: { high: String(high || prev[nextTf]?.high || ''), low: String(low || prev[nextTf]?.low || '') } }));
    if (w.start || w.end) setRangeWindowByTf(prev => ({ ...prev, [nextTf]: { ...(prev[nextTf] || {}), start: w.start || prev[nextTf]?.start || '', end: w.end || prev[nextTf]?.end || '' } }));
    setHistoryMarkMode('ACTIVE_CASE');
    pendingCameraIntentRef.current = { intent: cameraMode === 'LOCKED' ? 'RESTORE_LOCKED' : 'CASE', targetTime: w.start || idea.replay_candle_time || selectedCandle?.time || candleReplayCursorTime || null, reason:'open-saved-case' };
    activeTimeframeRef.current = nextTf;
    setTimeframe(nextTf);
    try {
      const payload = await fetch(`${BASE_URL}/api/v1/mos/seed-idea/${id}/payload`).then(r=>r.json());
      if (payload?.ok) {
        const grouped:Record<string,MapEvent[]> = {};
        safeArray<any>(payload.events).forEach((raw:any)=>{
          const ev = normalizeBackendEvent(raw);
          if (!ev) return;
          const tf = String(raw?.timeframe || ev?.meta_json?.timeframe || nextTf).toUpperCase();
          grouped[tf] = [...(grouped[tf] || []), ev];
        });
        if (Object.keys(grouped).length) setEventsByTf(prev => ({ ...prev, ...grouped }));
        const ranges = safeArray<any>(payload.ranges);
        if (ranges.length) {
          setRangeByTf(prev => {
            const out:any = { ...prev };
            for (const r of ranges) {
              const tf = String(r.timeframe || nextTf).toUpperCase();
              if (!out[tf]) out[tf] = {};
              if (r.range_high !== null && r.range_high !== undefined) out[tf].high = String(r.range_high);
              if (r.range_low !== null && r.range_low !== undefined) out[tf].low = String(r.range_low);
            }
            return out;
          });
          setRangeWindowByTf(prev => {
            const out:any = { ...prev };
            for (const r of ranges) {
              const tf = String(r.timeframe || nextTf).toUpperCase();
              out[tf] = { ...(out[tf] || {}), start: r.active_from_time || r.range_high_time || w.start || out[tf]?.start || '', end: r.inactive_from_time || r.range_low_time || w.end || out[tf]?.end || '' };
            }
            if (w.start || w.end) out[nextTf] = { ...(out[nextTf] || {}), start: w.start || out[nextTf]?.start || '', end: w.end || out[nextTf]?.end || '' };
            return out;
          });
        }
      }
    } catch { /* payload is helpful but not mandatory */ }
    setMessage(`Opened Case #${id}. Restored ${nextTf} workspace and case camera ${w.start ? String(w.start).slice(0,10) : 'start?'} → ${w.end ? String(w.end).slice(0,10) : 'end?'}. Switch W1/D1 and the camera stays in this case window.`);
  };

  const recentCaseIdeas = useMemo(() => {
    const matching = sortCaseRows(safeArray<any>(seedIdeas)).filter(caseMatchesContext);
    const visible = matching.slice(0, 8);
    const activeKey = String(activeCaseDisplayId || '');
    if (!activeKey) return visible;
    const hasActive = visible.some((x:any) => String(x?.raw_case_id || x?.id || '') === activeKey);
    if (hasActive) return visible;
    const activeRow = matching.find((x:any) => String(x?.raw_case_id || x?.id || '') === activeKey)
      || (rawActiveCaseId ? rawCaseRecentRow(String(rawActiveCaseId)) : null);
    return activeRow ? [...visible, activeRow] : visible;
  }, [seedIdeas, activeCaseDisplayId, rawActiveCaseId, symbol, caseTimeframe, caseScope, timeframe, seedName, activeCaseLabel, activeReplayCandle?.time, candleReplayCursorTime]);

  useEffect(()=>{ loadSeedIdeas(); }, [symbol]);

  useEffect(()=>{
    if (!candles.length) return;
    if (candleReplayCursorTime) {
      const idx = candleIndexNearest(candles, candleReplayCursorTime);
      if (idx !== candleReplayIndex) setCandleReplayIndex(idx);
    }
  }, [candles, candleReplayCursorTime]);

  useEffect(()=>{
    if (!candleReplayPlaying || !candleReplayMode || candles.length === 0) return;
    const id = window.setInterval(() => {
      const base = candleReplayCursorTime ? candleIndexAtOrBefore(candles, candleReplayCursorTime) : clamp(candleReplayIndex, 0, candles.length - 1);
      const next = base + 1;
      if (next >= candles.length) {
        window.clearInterval(id);
        setCandleReplayPlaying(false);
        return;
      }
      const c = candles[next];
      setCandleReplayIndex(next);
      setCandleReplayCursorTime(c.time);
      setTimeout(()=>setSelectedCandle(c), 0);
    }, candleReplaySpeedMs);
    return () => window.clearInterval(id);
  }, [candleReplayPlaying, candleReplayMode, candles, candleReplaySpeedMs, candleReplayCursorTime, candleReplayIndex]);

  useEffect(()=>{
    if (!playbackPlaying || !replayMode || playbackFrames.length === 0) return;
    const id = window.setInterval(() => {
      setPlaybackIndex(prev => {
        const next = prev + 1;
        if (next >= playbackFrames.length) {
          window.clearInterval(id);
          setPlaybackPlaying(false);
          return prev;
        }
        setTimeout(()=>applyPlaybackFrame(playbackFrames[next], next), 0);
        return next;
      });
    }, 1100);
    return () => window.clearInterval(id);
  }, [playbackPlaying, replayMode, playbackFrames]);

  const loadGps = async (mode: 'mock'|'active' = gpsMode) => {

    try {
      const params = new URLSearchParams({
        symbol,
        timeframe: 'W1',
        story_anchor: gpsStoryAnchor,
        chapter: gpsChapter,
        phase: gpsPhaseNumber,
        phase_part: gpsPhasePart,
        objective: gpsObjective,
        current_zone: gpsCurrentZone,
      });
      const endpoint = mode === 'mock'
        ? `${BASE_URL}/api/v1/market-gps/mock?${params.toString()}`
        : `${BASE_URL}/api/v1/mos/coordinates/${encodeURIComponent(symbol)}`;
      const res = await fetch(endpoint);
      const data = await res.json();
      setGps(data);
      if (mode === 'active') await loadTimeline();
    } catch (err:any) {
      setGps({ ok:false, status:'GPS_FETCH_FAILED', coordinates:null } as any);
    }
  };

  const saveGpsState = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mos/build-state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          story_id: gpsStoryId ? Number(gpsStoryId) : undefined,
          chapter_id: gpsChapterId ? Number(gpsChapterId) : undefined,
          story_timeframe: 'W1',
          chapter_timeframe: 'D1',
          story_anchor: gpsStoryAnchor,
          anchor_class: anchorClassLabel(gpsStoryAnchor),
          chapter: gpsChapter,
          lifecycle_state: gpsLifecycleState,
          parent_context_mode: gpsParentMode,
          daily_range_status: gpsDailyRangeStatus,
          phase_number: Number(String(gpsPhaseNumber).replace('P','')) || 1,
          phase_part: gpsPhasePart,
          objective_code: gpsObjective,
          current_zone: gpsCurrentZone,
          established_price: activeReplayCandle ? Number(activeReplayCandle.close.toFixed(2)) : 0,
          trigger_event: gpsTriggerEvent,
          expected_next_event: gpsExpectedNextEvent,
          invalidation_condition: gpsInvalidationCondition,
          timeframe: 'D1',
          bos_direction: gpsChapter.includes('DOWN') ? 'DOWN' : 'UP',
          bos_price: activeReplayCandle ? Number(activeReplayCandle.close.toFixed(2)) : 0,
          profile_type: gpsProfileType,
          timestamp: activeReplayCandle?.time || new Date().toISOString(),
        })
      });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || data?.detail || 'Save failed');
      setGpsMode('active');
      setGps({ ok:true, status:data.status || 'TRACKING_ACTIVE', symbol, timeframe:'W1', coordinates:data.coordinates });
      setMessage(`Saved MOS state: ${data.coordinates?.phase} ${data.coordinates?.phase_part}. Playback ledger has entered the chat.`);
      if (data?.story_id) { setPlaybackStoryId(String(data.story_id)); await loadPlayback(String(data.story_id)); }
    } catch (err:any) {
      setMessage(`GPS save failed: ${err?.message || err}`);
    }
  };

  useEffect(()=>{ loadGps(gpsMode); }, [symbol, gpsMode]);
  useEffect(()=>{ if (gpsMode === 'mock') loadGps('mock'); }, [gpsStoryAnchor, gpsChapter, gpsPhaseNumber, gpsPhasePart, gpsObjective, gpsCurrentZone]);

  const markerSections = useMemo(() => markerGroupsForTimeframe(timeframe), [timeframe]);

  useEffect(()=>{
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setWorkspacePanelOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(()=>{ loadCandles(timeframe); }, [symbol, timeframe]);

  return <div className={`mapStudioShell d3MapStudio ${chartFullscreen ? 'chartFullscreenActive' : ''}`}>
    <div className="panelHeader mapStudioHeader">
      <div><h2>Map Studio</h2><p>D3 candle canvas with locked vertical scale, horizontal pan, precision crosshair, and backend candle memory.</p></div>
      <div className="studioControls"><button onClick={loadCandles} disabled={loading}><RefreshCw size={18}/> Reload</button></div>
    </div>

    <div className={`mapStudioToolbar compactMapToolbar ${topRibbonCollapsed ? 'collapsedRibbon' : ''}`}>
      <button className="ribbonToggle" onClick={()=>setTopRibbonCollapsed(v=>!v)}>{topRibbonCollapsed ? 'Show ribbon' : 'Hide ribbon'}</button>
      <div className="tfTabs">{MAP_TIMEFRAMES.map(tf=><button key={tf} className={timeframe===tf?'active':''} onClick={()=>switchTimeframePreserveCase(tf)}>{tf}</button>)}</div>
      {!topRibbonCollapsed && <>
      <button className={scaleMode==='auto'?'active':''} onClick={()=>setScaleMode('auto')}>Auto</button>
      <button className={scaleMode==='range'?'active':''} onClick={()=>setScaleMode('range')}>Range</button>
      <button className={gpsMode==='active'?'active':''} onClick={()=>setGpsMode('active')}>GPS</button>
      <button className={candleReplayMode?'active replayActiveBtn':''} onClick={()=>setCandleReplayMode(x=>!x)}>Replay</button>
      <button className={chartFullscreen?'active':''} onClick={()=>setChartFullscreen(v=>!v)}>{chartFullscreen ? 'Exit Full' : 'Full Chart'}</button>
      <select className="cameraModeSelect" value={cameraMode} onChange={e=>setCameraMode(e.target.value as any)} title="Camera mode"><option value="AUTO">Auto cam</option><option value="LOCKED">Locked cam</option><option value="CASE">Case cam</option><option value="REPLAY">Replay cam</option></select>
      <div className="scaleNudges"><button onClick={()=>bumpCandleWidth(-0.15)}>W−</button><span>{Number(candleWidthScale).toFixed(2)}x</span><button onClick={()=>bumpCandleWidth(0.15)}>W+</button><button onClick={()=>bumpPriceZoom(-0.15)}>H−</button><span>{Number(priceZoomScale).toFixed(2)}x</span><button onClick={()=>bumpPriceZoom(0.15)}>H+</button><button onClick={resetCameraScale}>Reset</button></div>
      <div className="scaleNudges fitNudges"><button onClick={fitRangeView}>Fit Range</button><button onClick={fitReplayView}>Fit Replay</button><button onClick={fitCaseView}>Fit Case</button><button onClick={fitAllView}>Fit All</button><button onClick={lockCurrentView}>Lock View</button></div>
      <span className="loadedPill compactStatus">{candles.length ? `${candles.length} ${timeframe}` : 'No candles'}</span>
      <label className="historyMarksControl" title="Filter stored chart marks without deleting ledger records">History
        <select value={historyMarkMode} onChange={e=>setHistoryMarkMode(e.target.value)}>
          <option value="OFF">OFF</option>
          <option value="SESSION">Session</option>
          <option value="ACTIVE_RANGE">Active Range</option>
          <option value="ACTIVE_CASE">Active Case</option>
          <option value="NEARBY">Nearby</option>
          <option value="ALL">All</option>
        </select>
      </label>
      <button className={showRejectedMarks ? 'active historyMarksBtn' : 'historyMarksBtn'} onClick={()=>setShowRejectedMarks(v=>!v)} title="Rejected candidates stay stored for ML, but stay off the chart unless you ask for the mess.">Rejected {showRejectedMarks ? 'ON' : 'OFF'}</button>
      <details className="toolsMenu"><summary>Tools ▾</summary><div className="toolsMenuPanel">
        <button onClick={importCommon} disabled={loading}><Database size={18}/> Import EA CSV</button>
        <button onClick={()=>setJumpToken(x=>x+1)}>Jump latest</button>
        <button onClick={fitAllView}>Fit all</button>
        <button onClick={()=>loadGps(gpsMode)}>Refresh GPS</button>
        <button className={gpsMode==='mock'?'active':''} onClick={()=>setGpsMode('mock')}>GPS Mock</button>
        <span className="loadedPill">Backend memory ON</span>
      </div></details>
      </>}
    </div>

    {cursor && <div className="crosshairReadout">
      <b>{shortTime(cursor.time, timeframe)}</b>
      <span>Price {cursor.price?.toFixed(2)}</span>
      <span>{cursor.zone || 'No range'}{cursor.pct !== undefined ? ` · ${cursor.pct.toFixed(2)}%` : ''}</span>
      {cursor.ohlc && <span>O {cursor.ohlc.open.toFixed(2)} H {cursor.ohlc.high.toFixed(2)} L {cursor.ohlc.low.toFixed(2)} C {cursor.ohlc.close.toFixed(2)}</span>}
    </div>}

    <div className={`d3Workspace ${chartFullscreen ? 'chartFullscreenMode' : ''}`}>
      <div className={`d3ChartCard ${chartFullscreen ? 'chartFullscreenCard' : ''}`}>
        <div className="chartTitleRow chartTitleRowMap compactChartTitle">
          <h3>{symbol} {timeframe}</h3>
          <span>{selectedCandle ? `Selected ${shortTime(selectedCandle.time, timeframe)} · H ${selectedCandle.high.toFixed(2)} · L ${selectedCandle.low.toFixed(2)} · use Mark tab` : message}</span>
        </div>
        {replayMode && currentPlaybackFrame && <div className={`replayFrameBanner ${String(currentPlaybackFrame.lookahead_result || '').toLowerCase()}`}>
          <div><b>Replay Frame {playbackIndex + 1}/{playbackFrames.length}</b><span>{currentPlaybackFrame.frame_timestamp}</span></div>
          <div><strong>{currentPlaybackFrame.phase}</strong><span>{currentPlaybackFrame.lifecycle_state} · {currentPlaybackFrame.parent_context_mode}</span></div>
          <div><strong>{currentPlaybackFrame.current_zone}</strong><span>{currentPlaybackFrame.objective_code} · {currentPlaybackFrame.profile_type}</span></div>
          <div><strong>{currentPlaybackFrame.lookahead_result || 'RAW'}</strong><span>{currentPlaybackFrame.trigger_event}</span></div>
        </div>}
        {candleReplayMode && replayCandle && <div className="chartReplayOverlay">
          <b>{timeframe} replay</b>
          <span>{effectiveReplayIndex + 1}/{candles.length} · {shortTime(replayCandle.time, timeframe)}</span>
          <span>O {replayCandle.open.toFixed(2)} · H {replayCandle.high.toFixed(2)} · L {replayCandle.low.toFixed(2)} · C {replayCandle.close.toFixed(2)}</span>
          <span>{selectedCandle ? `Selected ${shortTime(selectedCandle.time, timeframe)}` : 'Replay cursor active · inspect-click any candle to scrub back'}</span>
        </div>}
        {activeParentRangeOverlay.length > 0 && <div className="parentRangeMiniBar" title="Parent range reference only. Jump/replay controls moved out of the chart body because apparently buttons enjoy standing in front of candles.">
          <b>{activeParentRangeOverlay[0]?.timeframe} parent</b>
          <span>{activeParentRangeOverlay.map(x=>`${x.kind.toUpperCase()} ${Number(x.price).toFixed(2)}`).join(' · ')}</span>
        </div>}
        {chartFullscreen && <div className="quickAnchorBar" aria-label="Quick structural mapping controls">
          <button className="structuralQuickBtn" disabled={quickEventSaving || (!selectedCandle && !replayCandle)} onClick={()=>setStructuralPoint('RH')} title="Save RH event and set structural Range High from selected/replay candle high"><b>Range High</b><span>RH</span></button>
          <button className="structuralQuickBtn" disabled={quickEventSaving || (!selectedCandle && !replayCandle)} onClick={()=>setStructuralPoint('RL')} title="Save RL event and set structural Range Low from selected/replay candle low"><b>Range Low</b><span>RL</span></button>
          <button className="structuralQuickBtn" disabled={quickEventSaving || (!selectedCandle && !replayCandle)} onClick={()=>setStructuralPoint('BH')} title="Save BH event and set structural Break High from selected/replay candle high"><b>Break High</b><span>BH</span></button>
          <button className="structuralQuickBtn" disabled={quickEventSaving || (!selectedCandle && !replayCandle)} onClick={()=>setStructuralPoint('BL')} title="Save BL event and set structural Break Low from selected/replay candle low"><b>Break Low</b><span>BL</span></button>
          <span className="quickAnchorDivider" />
          <button className="quickSaveBtn" onClick={()=>saveSeedIdea(false)} disabled={caseSaving}>{caseSaving ? 'Saving...' : getCurrentMappingCaseRef().hasCase ? 'Update Case' : 'Create Case'}</button>
          <button className="quickSaveBtn primary" onClick={saveStructuralRange} disabled={structuralSaving || !rhAnchor.price || !rlAnchor.price}>{structuralSaving ? 'Saving...' : savePreview.actionLabel}</button>
          <button className="quickSaveBtn" onClick={refreshHierarchyAudit}>Refresh Audit</button>
          <button className="quickSaveBtn" onClick={exportCurrentMappingJson}>Export JSON</button>
          <button className="quickSaveBtn" onClick={undoLastQuickEvent} disabled={!lastSavedQuickEvent || quickEventSaving}>Undo Last Event</button>
          <span className={`quickDraftStatus ${structuralRangeDraftDirty || structuralBosDraftDirty ? 'dirty' : 'saved'}`}>{structuralRangeDraftDirty || structuralBosDraftDirty ? 'Unsaved draft' : 'Draft clean'}</span>
          <span className={`quickDraftStatus ${lastSavedQuickEvent ? 'saved' : ''}`}>{lastSavedQuickEvent ? `Last Event Saved: ${lastSavedQuickEvent.role} ${lastSavedQuickEvent.source_timeframe} ${String(lastSavedQuickEvent.event_id).slice(0,8)}` : 'No quick event saved'}</span>
          <span className="quickAnchorDivider" title="TODO: add fullscreen Save BOS_UP, Save BOS_DOWN, and Refresh Audit actions after this compact row is validated." />
          <button className={toolMode==='select'?'active':''} onClick={()=>setToolMode('select')}>Select</button>
          <button className={toolMode==='inspect'?'active':''} onClick={()=>setToolMode('inspect')}>Scrub</button>
          <button onClick={()=>setChartFullscreen(false)}>Exit</button>
        </div>}
        {chartFullscreen && <div className="fullscreenTfDock" aria-label="Fullscreen timeframe controls">
          {(['MN1','W1','D1','H4','H1','M15'] as string[]).map(tf => <button key={tf} className={timeframe===tf?'active':''} onClick={()=>switchTimeframePreserveCase(tf)}>{tf}</button>)}
          <select value={cameraMode} onChange={e=>setCameraMode(e.target.value as any)}><option value="AUTO">Auto</option><option value="LOCKED">Lock</option><option value="CASE">Case</option><option value="REPLAY">Replay</option></select>
        </div>}
        {chartFullscreen && <div className="fullscreenScaleDock" aria-label="Fullscreen candle scale controls">
          <button onClick={()=>bumpCandleWidth(-0.15)}>W−</button><span>{Number(candleWidthScale).toFixed(2)}</span><button onClick={()=>bumpCandleWidth(0.15)}>W+</button>
          <button onClick={()=>bumpPriceZoom(-0.15)}>H−</button><span>{Number(priceZoomScale).toFixed(2)}</span><button onClick={()=>bumpPriceZoom(0.15)}>H+</button>
          <button onClick={resetCameraScale}>Reset</button>
        </div>}
        {chartFullscreen && <div className="fullscreenFitDock" aria-label="Fullscreen fit controls">
          <button onClick={fitRangeView}>Fit Range</button>
          <button onClick={fitReplayView}>Fit Replay</button>
          <button onClick={fitCaseView}>Fit Case</button>
          <button onClick={fitAllView}>Fit All</button>
          <button onClick={lockCurrentView}>Lock View</button>
        </div>}
        {chartFullscreen && <div className="fullscreenReplayDock" aria-label="Fullscreen replay controls">
          <button onClick={()=>setCandleReplayFrame(effectiveReplayIndex - 1)} disabled={!candles.length || effectiveReplayIndex <= 0}>◀</button>
          <button className={candleReplayPlaying?'active':''} onClick={()=>{ setCandleReplayMode(true); setCandleReplayPlaying(x=>!x); }} disabled={!candles.length}>{candleReplayPlaying ? 'Pause' : 'Play'}</button>
          <button onClick={()=>setCandleReplayFrame(effectiveReplayIndex + 1)} disabled={!candles.length || effectiveReplayIndex >= candles.length - 1}>▶</button>
          <button onClick={jumpToParentRangeStart} disabled={!activeParentRangeOverlay.length}>Parent</button>
          <button onClick={startChildReplayFromParentStart} disabled={!activeParentRangeOverlay.length}>Child Replay</button>
          <span>{candles.length ? `${Math.min(effectiveReplayIndex + 1, candles.length)}/${candles.length}` : 'No candles'}{replayCandle ? ` · ${shortTime(replayCandle.time, timeframe)} · C ${replayCandle.close.toFixed(2)}` : ''}</span>
        </div>}
        <D3CandleMap
          candles={candles}
          replayCutTime={candleReplayMode && replayCandle ? replayCandle.time : null}
          timeframe={timeframe}
          rangeHigh={high}
          rangeLow={low}
          rangeStart={rangeWindow.start}
          rangeEnd={rangeWindow.end}
          hasRange={hasRange}
          caseStart={activeCaseLedger?.start || ''}
          caseEnd={activeCaseLedger?.end || ''}
          caseHigh={activeCaseLedger?.high || ''}
          caseLow={activeCaseLedger?.low || ''}
          parentOverlays={activeParentRangeOverlay}
          events={visibleEvents}
          selectedCandleTime={selectedCandle?.time || null}
          selectedCandlePrice={selectedCandlePoint?.price ?? null}
          eventType={eventType}
          toolMode={toolMode}
          scaleMode={scaleMode}
          jumpLatestToken={jumpToken}
          fitAllToken={fitToken}
          goDate={jumpDate}
          replayCursorEnabled={candleReplayMode}
          onReplayCursorChange={setCandleReplayFrameByTime}
          onCursor={setCursor}
          onAddEvent={addEventAt}
          onUpdateEvent={updateEvent}
          onFinishEventDrag={finishEventDrag}
          onCandleSelect={(payload)=>{
            setSelectedCandle(payload.candle);
            setPendingMarkerRoles([]);
            setSelectedCandlePoint({ price: Number(payload.price.toFixed(2)), clientX: payload.clientX, clientY: payload.clientY });
            setMessage(`Selected ${shortTime(payload.candle.time, timeframe)} · anchor ${payload.price.toFixed(2)}. Choose meaning from Mark tab.`);
          }}
          cameraMode={cameraMode}
          cameraCommand={cameraCommand}
          lockedCameraDomain={lockedCameraDomain}
          lockedPriceDomain={cameraPriceDomainByCaseTf[cameraKey] || null}
          cameraKey={cameraKey}
          candleWidthScale={candleWidthScale}
          priceZoomScale={priceZoomScale}
          onCameraDomainChange={(dom)=>{ if (cameraMode === 'LOCKED') setCameraDomainByCaseTf(prev=>({ ...prev, [cameraKey]: dom })); }}
          onVisibleDomainChange={(dom)=>{ visibleCameraDomainRef.current = dom; }}
          onRangeChange={({high, low, start, end})=>{
            if (typeof high === 'number' && Number.isFinite(high)) setRangeHigh(String(Number(high.toFixed(2))));
            if (typeof low === 'number' && Number.isFinite(low)) setRangeLow(String(Number(low.toFixed(2))));
            if (typeof start === 'string') setRangeWindow({ start });
            if (typeof end === 'string') setRangeWindow({ end });
          }}
        />
      </div>
      <div className="floatingWorkspaceDock" aria-label="Workspace tools">
        <button className={rightDeckTab==='narrative' && workspacePanelOpen ? 'active' : ''} title="Narrative" onClick={()=>{ setRightDeckTab('narrative'); setWorkspacePanelOpen(prev => rightDeckTab === 'narrative' ? !prev : true); }}>N</button>
        <button className={rightDeckTab==='gps' && workspacePanelOpen ? 'active' : ''} title="GPS" onClick={()=>{ setRightDeckTab('gps'); setWorkspacePanelOpen(prev => rightDeckTab === 'gps' ? !prev : true); }}>G</button>
        <button className={rightDeckTab==='mark' && workspacePanelOpen ? 'active' : ''} title="Mark" onClick={()=>{ setRightDeckTab('mark'); setToolMode('select'); setWorkspacePanelOpen(prev => rightDeckTab === 'mark' ? !prev : true); }}>M</button>
        <button className={rightDeckTab==='seed' && workspacePanelOpen ? 'active' : ''} title="Case" onClick={()=>{ setRightDeckTab('seed'); setWorkspacePanelOpen(prev => rightDeckTab === 'seed' ? !prev : true); }}>C</button>
      </div>
      <div className={`mapSidePanel d3Side compactSideDeck floatingWorkspacePanel ${workspacePanelOpen ? 'open' : 'closed'}`}>
        <div className="floatingPanelChrome">
          <div><b>{rightDeckTab === 'narrative' ? 'Narrative' : rightDeckTab === 'gps' ? 'Market GPS' : rightDeckTab === 'mark' ? 'Mark Event' : 'Case Manager'}</b><span>{symbol} · {timeframe}</span></div>
          <button onClick={()=>setWorkspacePanelOpen(false)} title="Close panel">×</button>
        </div>
        {rightDeckTab === 'narrative' && <div className="rightTabPanel narrativeTabPanel ledgerViewerPanel">
          <h3>Event Ledger</h3>
          <p className="mutedSmall">Raw saved facts for the active timeframe. This is the brain food. Narrative comes after the compiler understands the bones.</p>
          <div className="caseBadge">LEDGER · {symbol} {timeframe} · {eventLedgerRows.length} saved event{eventLedgerRows.length===1?'':'s'}</div>
          <div className="compilerPreviewCard">
            <b>Range Compiler Preview</b>
            <div><span>High</span><strong>{rangeCompilerPreview.high || 'not set'}</strong><em>{rangeCompilerPreview.highTime ? shortTime(rangeCompilerPreview.highTime, timeframe) : '—'}</em></div>
            <div><span>Low</span><strong>{rangeCompilerPreview.low || 'not set'}</strong><em>{rangeCompilerPreview.lowTime ? shortTime(rangeCompilerPreview.lowTime, timeframe) : '—'}</em></div>
            <div><span>Anchor events</span><strong>{rangeCompilerPreview.highCount}H / {rangeCompilerPreview.lowCount}L</strong><em>explicit Set M/W/D only</em></div>
          </div>
          <div className="htfLiteCard">
            <div className="htfLiteHeader"><b>HTF Engine Lite</b><span>{htfSemiAuto.state?.status || 'waiting'} · {htfSemiAuto.state?.candle_count || 0} candles</span></div>
            <div className="htfLiteGrid">
              <div><span>Location</span><strong>{htfSemiAuto.state?.location || '—'}</strong><em>{fmtPctOrDash(htfSemiAuto.state?.close_pct)}</em></div>
              <div><span>Range</span><strong>{hasRange ? `${low.toFixed(2)} → ${high.toFixed(2)}` : 'not set'}</strong><em>official anchors only</em></div>
              <div><span>Next Watch</span><strong>{htfSemiAuto.state?.next_watch || '—'}</strong><em>{timeframe}</em></div>
            </div>
            <div className="htfLiteNote">Overview stays lite. Objectives and ML fields are stored quietly for stats, because the chart is not a filing cabinet.</div>
          </div>
          <div className="ledgerRows">
            {eventLedgerRows.length === 0 && <div className="emptyNarrative"><b>No ledger rows yet</b><span>Click a candle, open Mark, save a bundle. The machine refuses to narrate air.</span></div>}
            {eventLedgerRows.map((ev:any, idx:number)=><button key={ev.id || `${ev.event_type}_${idx}`} className="ledgerRowButton" onClick={()=>jumpToLedgerEvent(ev)}>
              <b>#{idx + 1}</b>
              <span>{ev._label}</span>
              <em>{shortTime(ev.time, timeframe)} · {Number(ev.price).toFixed(2)}{ev.zone ? ` · ${ev.zone}` : ''}</em>
            </button>)}
          </div>
          <div className="narrativeHint">Click a ledger row to jump replay/camera to that candle. Range Compiler Preview is read-only for now. No mystical narrator yet, calm down humanity.</div>
        </div>}
        {rightDeckTab === 'gps' && <>
        <div className="gpsPanel">
          <h3>Market GPS</h3>
          <p className="mutedSmall">{gpsMode === 'mock' ? 'Mock payload: front-door test.' : 'Live MOS state from backend.'} Edit below, save to database, then use GPS Active.</p>
          {gps?.coordinates ? <>
            <div className="gpsRow"><span>Story Anchor</span><b>{gps.coordinates.story_anchor}</b></div>
            <div className="gpsRow"><span>Anchor Class</span><b>{gps.coordinates.anchor_class || anchorClassLabel(gps.coordinates.story_anchor)}</b></div>
            <div className="gpsRow"><span>Chapter</span><b>{gps.coordinates.chapter}</b></div>
            <div className="gpsPhaseBox phaseCoordinate"><strong>{gps.coordinates.phase} {gps.coordinates.phase_part}</strong></div>
            <div className="gpsRow"><span>Objective</span><b>{gps.coordinates.objective}</b></div>
            <div className="gpsRow"><span>Current Zone</span><b>{gps.coordinates.current_zone}</b></div>
            {gps.coordinates.parent_context_mode && <div className="gpsRow"><span>Parent Mode</span><b>{gps.coordinates.parent_context_mode}</b></div>}
            {gps.coordinates.daily_range_status && <div className="gpsRow"><span>Daily Range</span><b>{gps.coordinates.daily_range_status}</b></div>}
            {gps.coordinates.lifecycle_state && <div className="gpsRow"><span>Lifecycle</span><b>{gps.coordinates.lifecycle_state}</b></div>}
            {gps.coordinates.profile_type && <div className="gpsRow"><span>Profile</span><b>{gps.coordinates.profile_type}</b></div>}
          </> : <div className="gpsEmpty">{gps?.status || 'No GPS state loaded yet.'}</div>}
          <div className="gpsMockEditor">
            <label>Anchor<select value={gpsStoryAnchor} onChange={e=>setGpsStoryAnchor(e.target.value)}>{STORY_ANCHOR_OPTIONS.map(x=><option key={x}>{x}</option>)}</select></label>
            <label>Chapter<select value={gpsChapter} onChange={e=>setGpsChapter(e.target.value)}>{['DAILY_BOS_UP','DAILY_BOS_DOWN','DAILY_CHOCH_UP','DAILY_CHOCH_DOWN','DAILY_BOS_UP_RECLAIM','POLARITY_FLIP_RETEST'].map(x=><option key={x}>{x}</option>)}</select></label>
            <div className="gpsMockGrid">
              <label>Story ID<input value={gpsStoryId} onChange={e=>setGpsStoryId(e.target.value)} placeholder="optional" /></label>
              <label>Chapter ID<input value={gpsChapterId} onChange={e=>setGpsChapterId(e.target.value)} placeholder="optional" /></label>
            </div>
            <label>Parent Mode<select value={gpsParentMode} onChange={e=>setGpsParentMode(e.target.value)}>{['WEEKLY_ACTIVE_PARENT','WEEKLY_ABANDONED_DAILY_IN_MOTION','WEEKLY_FORMING_NO_DAILY_RANGE','DAILY_ACTIVE_ORPHAN','DAILY_ADOPTED_BY_NEW_WEEKLY'].map(x=><option key={x}>{x}</option>)}</select></label>
            <label>Daily Range<select value={gpsDailyRangeStatus} onChange={e=>setGpsDailyRangeStatus(e.target.value)}>{['NO_ACTIVE_DAILY_RANGE','DAILY_RANGE_FORMING','DAILY_RANGE_ACTIVE','DAILY_RANGE_RETESTING','DAILY_RANGE_ABANDONED'].map(x=><option key={x}>{x}</option>)}</select></label>
            <label>Lifecycle<select value={gpsLifecycleState} onChange={e=>setGpsLifecycleState(e.target.value)}>{['REVERSAL_DEVELOPMENT','EXPANSION','MITIGATION','OBJECTIVE_COMPLETION'].map(x=><option key={x}>{x}</option>)}</select></label>
            <div className="gpsMockGrid">
              <label>Phase<select value={gpsPhaseNumber} onChange={e=>setGpsPhaseNumber(e.target.value)}>{['P1','P2','P3'].map(x=><option key={x}>{x}</option>)}</select></label>
              <label>State<select value={gpsPhasePart} onChange={e=>setGpsPhasePart(e.target.value)}>{['RETEST','RECLAIM','IMPULSE','BOS','FAIL'].map(x=><option key={x}>{x}</option>)}</select></label>
            </div>
            <label>Profile<select value={gpsProfileType} onChange={e=>setGpsProfileType(e.target.value)}>{['DEEP_RECLAIM_SD_PROFILE','SHALLOW_RECLAIM_SR_PROFILE','NO_RECLAIM_CONTINUATION_PROFILE','FAILED_RECLAIM_ABANDONED_RANGE'].map(x=><option key={x}>{x}</option>)}</select></label>
            <label>Objective<input value={gpsObjective} onChange={e=>setGpsObjective(e.target.value.toUpperCase())} /></label>
            <label>Zone<input value={gpsCurrentZone} onChange={e=>setGpsCurrentZone(e.target.value.toUpperCase())} /></label>
            <label>Trigger<input value={gpsTriggerEvent} onChange={e=>setGpsTriggerEvent(e.target.value.toUpperCase())} /></label>
            <label>Expected Next<input value={gpsExpectedNextEvent} onChange={e=>setGpsExpectedNextEvent(e.target.value.toUpperCase())} /></label>
            <label>Invalidation<input value={gpsInvalidationCondition} onChange={e=>setGpsInvalidationCondition(e.target.value.toUpperCase())} /></label>
          <button className="gpsSaveBtn" onClick={saveGpsState}>Build MOS State</button><button className="gpsSaveBtn secondary" onClick={()=>loadGps('active')}>Load Active GPS</button></div>
        </div>

        </>}
        {rightDeckTab === 'mark' && <div className="rightTabPanel markTabPanel markPanelModern markWorkspaceV0879">
          <div className="markWorkspaceModeTabs">
            <button className={markWorkspaceMode==='htf'?'active':''} onClick={()=>setMarkWorkspaceMode('htf')}>Structural Map</button>
            <button className={markWorkspaceMode==='manual'?'active':''} onClick={()=>setMarkWorkspaceMode('manual')}>Manual Events</button>
            <button className={markWorkspaceMode==='case'?'active':''} onClick={()=>setMarkWorkspaceMode('case')}>Case Save</button>
          </div>

          {markWorkspaceMode === 'htf' && <div className="markModePane htfEnginePane">
            <div className="markPanelTitleRow"><div><h3>Structural Weekly/Daily Mapping</h3><p className="mutedSmall">Store RH/RL ranges and BH/BL BOS events only. No sweeps, profiles, objectives, or strategy fields here.</p></div></div>
            <div className="markSelectedCard wide">
              <b>Selected Candle</b>
              <span>{selectedCandle ? `${shortTime(selectedCandle.time, timeframe)} · O ${selectedCandle.open.toFixed(2)} · H ${selectedCandle.high.toFixed(2)} · L ${selectedCandle.low.toFixed(2)} · C ${selectedCandle.close.toFixed(2)}` : 'Click a candle to capture RH/RL/BH/BL.'}</span>
            </div>

            <div className="htfStateLiteCard">
              <div className="htfLiteHeader"><b>Mapping Scope</b><span>{structureLayer} · source {sourceTimeframe} · chart {timeframe}</span></div>
              <div className="markModeStrip compact">
                {(['WEEKLY','DAILY','INTRADAY'] as StructureLayer[]).map(layer=><button key={layer} className={structureLayer===layer?'active':''} onClick={()=>setStructureLayer(layer)}>{layer}{layer==='INTRADAY' ? ' · storage-ready' : ''}</button>)}
              </div>
              <label className="toolbarStoryInput">Source TF
                <select value={sourceTimeframe} onChange={e=>setSourceTimeframe(e.target.value)}>
                  <option value="W1">W1</option>
                  <option value="D1">D1</option>
                  <option value="H1">H1</option>
                  <option value="H4">H4</option>
                  <option value="H8">H8</option>
                </select>
              </label>
              {structureLayer === 'WEEKLY' && <div className="caseBadge">Weekly root range. No parent required.</div>}
              {structureLayer === 'DAILY' && <div className="compilerPreviewCard">
                <b>Weekly Parent</b>
                <label>Parent range
                  <select value={selectedParentRangeId} onChange={e=>setSelectedParentRangeId(e.target.value)}>
                    <option value="">No Weekly parent selected</option>
                    {structuralRanges.map((r:any)=><option key={r.range_id || r.id} value={String(r.range_id || r.id)}>#{r.range_id || r.id} · RH {r.range_high_price || r.range_high || '?'} / RL {r.range_low_price || r.range_low || '?'}</option>)}
                  </select>
                </label>
                {selectedParentRange ? <div><span>Selected</span><strong>#{selectedParentRange.range_id || selectedParentRange.id} · RH {selectedParentRange.range_high_price || '—'} / RL {selectedParentRange.range_low_price || '—'}</strong><em>{selectedParentRange.range_start_time ? `${shortTime(selectedParentRange.range_start_time, 'W1')} → ${shortTime(selectedParentRange.range_end_time, 'W1')}` : 'no saved window'}</em></div> : <div><span>Status</span><strong>No Weekly parent selected</strong><em>Daily range will be saved as ORPHAN after confirmation.</em></div>}
              </div>}
              {structureLayer === 'INTRADAY' && <div className="caseBadge">Intraday storage is visible for schema proof only. Full Intraday workflow and H8 rendering are TODO.</div>}
              <button className="gpsSaveBtn secondary" onClick={refreshStructuralRanges}>Refresh Parents/Ranges</button>
            </div>

            <div className="htfStateLiteCard">
              <div className="htfLiteHeader"><b>RH / RL / BH / BL</b><span>BH/BL = mark break candle</span></div>
              <div className="htfLiteGrid compactStateGrid">
                <div><span>RH</span><strong>{rhAnchor.price || 'not set'}</strong><em>{rhAnchor.time ? shortTime(rhAnchor.time, timeframe) : 'Range High'}</em></div>
                <div><span>RL</span><strong>{rlAnchor.price || 'not set'}</strong><em>{rlAnchor.time ? shortTime(rlAnchor.time, timeframe) : 'Range Low'}</em></div>
                <div><span>BH</span><strong>{bhAnchor.price || 'not set'}</strong><em>{bhAnchor.time ? shortTime(bhAnchor.time, timeframe) : 'Break High'}</em></div>
                <div><span>BL</span><strong>{blAnchor.price || 'not set'}</strong><em>{blAnchor.time ? shortTime(blAnchor.time, timeframe) : 'Break Low'}</em></div>
              </div>
              <div className="caseActionRow">
                <button onClick={()=>setStructuralPoint('RH')} disabled={quickEventSaving || (!selectedCandle && !replayCandle)}>Range High</button>
                <button onClick={()=>setStructuralPoint('RL')} disabled={quickEventSaving || (!selectedCandle && !replayCandle)}>Range Low</button>
                <button onClick={()=>setStructuralPoint('BH')} disabled={quickEventSaving || (!selectedCandle && !replayCandle)}>Break High</button>
                <button onClick={()=>setStructuralPoint('BL')} disabled={quickEventSaving || (!selectedCandle && !replayCandle)}>Break Low</button>
                <button className="gpsSaveBtn secondary" onClick={undoLastQuickEvent} disabled={!lastSavedQuickEvent || quickEventSaving}>Undo Last Event</button>
              </div>
              <div className="htfCandidateState">
                <span>{lastSavedQuickEvent ? `Last Event Saved: ${lastSavedQuickEvent.role} · ${lastSavedQuickEvent.structure_layer}/${lastSavedQuickEvent.source_timeframe} · ${String(lastSavedQuickEvent.event_id).slice(0,8)}` : 'No quick event saved this session.'}</span>
                <em>Quick buttons save marker event records only. Save BOS_UP / BOS_DOWN saves formal structure events.</em>
              </div>
            </div>

            <div className="htfStateLiteCard">
              <div className="htfLiteHeader"><b>Save Preview</b><span>{savePreview.actionLabel}</span></div>
              {savePreview.warning && <div className="caseBadge warningBadge">{savePreview.warning}</div>}
              <div className="htfLiteGrid compactStateGrid">
                <div><span>Chart TF</span><strong>{savePreview.chart_timeframe}</strong><em>view only</em></div>
                <div><span>Will Save</span><strong>{savePreview.structure_layer}</strong><em>{savePreview.actionLabel}</em></div>
                <div><span>Source TF</span><strong>{savePreview.source_timeframe}</strong><em>structural truth</em></div>
                <div><span>Case Ref</span><strong>{savePreview.case_ref || 'no case'}</strong><em>{savePreview.raw_case_id || savePreview.case_id || 'missing'}</em></div>
                <div><span>Parent</span><strong>{savePreview.parent_range_id || 'none'}</strong><em>{structureLayer === 'DAILY' ? 'Weekly parent' : 'root range'}</em></div>
                <div><span>RH</span><strong>{savePreview.range_high_price || 'not set'}</strong><em>{savePreview.range_high_time ? shortTime(savePreview.range_high_time, timeframe) : 'draft'}</em></div>
                <div><span>RL</span><strong>{savePreview.range_low_price || 'not set'}</strong><em>{savePreview.range_low_time ? shortTime(savePreview.range_low_time, timeframe) : 'draft'}</em></div>
                <div><span>Selected</span><strong>{activeStructuralRangeId || 'new'}</strong><em>{selectedSavedRange ? 'will update' : 'will create'}</em></div>
              </div>
            </div>

            <div className="htfCandidateBox fullWidth compactBosOnlyBox">
              <div className="htfLiteHeader"><b>Save Structural Facts</b><span>{activeStructuralRangeId ? `active range #${activeStructuralRangeId}` : 'range id set after save'}</span></div>
              <div className="htfCandidateState"><span>Save Range = saves RH/RL structural range to DB. Save BOS_UP / BOS_DOWN = save formal structure event.</span><em>Parent Break = update Weekly BH/BL only when Weekly RH/RL is breached. Draft clicks do not auto-save ranges or parent breaks.</em></div>
              <div className="caseActionRow">
                <button className="gpsSaveBtn" onClick={saveStructuralRange} disabled={structuralSaving || !rhAnchor.price || !rlAnchor.price}>{structuralSaving ? 'Saving...' : savePreview.actionLabel}</button>
                <button className="gpsSaveBtn secondary" onClick={()=>{ setActiveStructuralRangeId(''); setLastSavedRangeConfirmation(null); setMessage('New range mode selected. Next Save Range will create a new saved range.'); }}>Start New Range</button>
                <button className="gpsSaveBtn secondary" onClick={()=>saveStructuralBos('UP')} disabled={structuralSaving || !bhAnchor.price}>Save BOS_UP</button>
                <button className="gpsSaveBtn secondary" onClick={()=>saveStructuralBos('DOWN')} disabled={structuralSaving || !blAnchor.price}>Save BOS_DOWN</button>
              </div>
              {lastSavedRangeConfirmation && <div className="caseBadge">
                Saved confirmation: #{lastSavedRangeConfirmation.range_id || '?'} · {lastSavedRangeConfirmation.structure_layer} · {lastSavedRangeConfirmation.source_timeframe} · parent {lastSavedRangeConfirmation.parent_range_id || 'none'} · raw {lastSavedRangeConfirmation.raw_case_id || 'none'} · {lastSavedRangeConfirmation.case_ref || 'no case_ref'} · RH {lastSavedRangeConfirmation.range_high_price} / RL {lastSavedRangeConfirmation.range_low_price}
              </div>}
            </div>

            <div className="htfStateLiteCard">
              <div className="htfLiteHeader"><b>Saved Ranges for Current Case</b><span>{savedStructuralRanges.length} saved</span></div>
              <div className="caseActionRow">
                <button className="gpsSaveBtn secondary" onClick={()=>refreshSavedRangesForCurrentCase().catch((err:any)=>setMessage(`Load saved ranges failed: ${err?.message || err}`))}>Refresh Saved Ranges</button>
              </div>
              <div className="caseLedgerRows">
                {!savedStructuralRanges.length && <div className="caseLedgerEmpty">No saved structural ranges for this active case yet.</div>}
                {savedStructuralRanges.slice(0, 24).map((r:any)=><button key={r.range_id || r.id} className={String(r.range_id || r.id) === String(activeStructuralRangeId) ? 'active' : ''} onClick={()=>selectSavedStructuralRange(r)}>
                  <b>#{r.range_id || r.id}</b>
                  <span>{r.structure_layer || r.layer || '?'} · RH {r.range_high_price ?? r.range_high ?? '—'} / RL {r.range_low_price ?? r.range_low ?? '—'}</span>
                  <em>parent {r.parent_range_id || 'none'} · {r.parent_link_status || 'status pending'}</em>
                </button>)}
              </div>
            </div>

            <div className="htfStateLiteCard">
              <div className="htfLiteHeader"><b>Hierarchy Audit</b><span>{hierarchyAudit ? 'loaded' : 'not loaded'}</span></div>
              <div className="htfLiteGrid compactStateGrid">
                <div><span>Weekly</span><strong>{hierarchyAudit?.summary?.weekly_ranges ?? '—'}</strong><em>ranges</em></div>
                <div><span>Daily</span><strong>{hierarchyAudit?.summary?.daily_ranges ?? '—'}</strong><em>ranges</em></div>
                <div><span>D → W</span><strong>{hierarchyAudit?.summary?.daily_ranges_linked_to_weekly ?? '—'}</strong><em>linked</em></div>
                <div><span>Orphan D</span><strong>{hierarchyAudit?.summary?.orphan_daily_ranges ?? '—'}</strong><em>warnings</em></div>
                <div><span>Invalid</span><strong>{hierarchyAudit?.summary?.invalid_parent_links ?? '—'}</strong><em>parent links</em></div>
                <div><span>Missing RH/RL</span><strong>{hierarchyAudit?.summary?.ranges_missing_rh_rl ?? '—'}</strong><em>errors</em></div>
                <div><span>BOS BH/BL</span><strong>{hierarchyAudit?.summary?.bos_events_missing_bh_bl ?? '—'}</strong><em>missing</em></div>
                <div><span>Status</span><strong>{hierarchyAudit ? ((hierarchyAudit.errors || []).length ? 'FAIL' : (hierarchyAudit.warnings || []).length ? 'WARN' : 'PASS') : '—'}</strong><em>backend audit</em></div>
              </div>
              <div className="htfCandidateState"><span>Audit reads DB; it does not save.</span><em>Export writes a JSON file only; it does not save drafts.</em></div>
              <div className="caseActionRow">
                <button className="gpsSaveBtn secondary" onClick={refreshHierarchyAudit}>Refresh Audit</button>
                <button className="gpsSaveBtn secondary" onClick={exportAuditJson}>Export Audit JSON</button>
                <button className="gpsSaveBtn secondary" onClick={exportCurrentMappingJson}>Export Current Mapping JSON</button>
              </div>
            </div>
          </div>}

          {markWorkspaceMode === 'manual' && <div className="markModePane manualEventsPane">
            <div className="markWorkbench manualMarkWorkbench">
              <aside className="markWorkbenchLeft">
                <div className="markPanelTitleRow"><div><h3>Manual Events</h3><p className="mutedSmall">Overrides, anchors, and special judgement. The event jungle is contained here, like it deserves.</p></div></div>
                <div className="markSelectedCard">
                  <b>Selected Candle</b>
                  <span>{selectedCandle ? `${shortTime(selectedCandle.time, timeframe)} · H ${selectedCandle.high.toFixed(2)} · L ${selectedCandle.low.toFixed(2)} · anchor ${selectedCandlePoint?.price?.toFixed?.(2) || 'n/a'}` : 'Click a candle to populate capture tools.'}</span>
                </div>
                <div className="markModeStrip compact">
                  <button className={toolMode==='inspect'?'active':''} onClick={()=>setToolMode('inspect')}>Pan</button>
                  <button className={toolMode==='select'?'active':''} onClick={()=>setToolMode('select')}>Click Candle</button>
                </div>
                <div className="markQueueChips">
                  <b>Queue</b>
                  <div>{pendingMarkerRoles.length ? pendingMarkerRoles.map(role=><button key={role} onClick={()=>togglePendingMarkerRole(role)} title="Click to remove">{markerLabel(role)}</button>) : <span>Queue empty. Select events on the right.</span>}</div>
                </div>
                <div className="markCommitFooter modernMarkFooter">
                  <button className="clearQueueBtn" onClick={clearPendingMarkerSelection} disabled={!pendingMarkerRoles.length}>Cancel</button>
                  <button className="saveNarrativeBtn" onClick={savePendingMarkersToNarrative} disabled={bundleSaving || !pendingMarkerRoles.length || !selectedCandle}>{bundleSaving ? 'Saving...' : 'Save'}</button>
                </div>
              </aside>
              <section className="markEventTaxonomy">
                {selectedCandle ? <div className="markQuickGroups timeframeAwareGroups modernEventGroups">
                  {markerSections.map((section:any)=><details className="markerSection" key={section.title} open={section.defaultOpen}>
                    <summary>{section.title}</summary>
                    {section.groups.map((group:any)=><div className="markQuickGroup" key={group.title}>
                      <small>{group.title}</small>
                      <div>{group.items.map(([role,label]:any)=><button key={role} className={pendingMarkerRoles.includes(role) ? 'queued' : ''} onClick={()=>togglePendingMarkerRole(role)}>{label}</button>)}</div>
                    </div>)}
                  </details>)}
                  <div className="markQuickGroup dangerGroup"><small>Fix</small><div><button onClick={()=>{ clearPendingMarkerSelection(); clearSelectedCandleEvents(); }}>Clear Candle Events</button><button onClick={()=>{setSelectedCandle(null); setSelectedCandlePoint(null); setPendingMarkerRoles([]);}}>Close Selection</button></div></div>
                </div> : <div className="markEmptyState">Select a candle on the chart first. The app cannot mark imaginary candles, despite humanity’s best efforts.</div>}
              </section>
            </div>
          </div>}

          {markWorkspaceMode === 'case' && <div className="markModePane caseQuickPane">
            <div className="caseQuickHeader"><div><h3>Case Save</h3><p className="mutedSmall">Update Case saves the container only. Use Save Range for RH/RL.</p></div></div>
            <div className="activeCaseCard"><span>Active Case</span><b>{activeCaseDisplayId ? activeCaseLabel || `#${activeCaseDisplayId}` : 'None selected'}</b><button onClick={resetActiveCase} disabled={!activeCaseDisplayId}>Clear Active</button></div>
            <div className="caseActionRow">
              <button className="gpsSaveBtn" onClick={()=>saveSeedIdea(false)} disabled={caseSaving}>{caseSaving ? 'Saving...' : getCurrentMappingCaseRef().hasCase ? 'Update Case' : 'Create Case'}</button>
              <button className="gpsSaveBtn danger" onClick={deleteActiveCase} disabled={!activeCaseId}>Delete Active</button>
            </div>
            {caseSavedNotice && <div className="caseSavedNotice">✓ {caseSavedNotice}</div>}
            <div className="caseScopeStrip">
              {(['MACRO','WEEKLY','DAILY','INTRADAY','MICRO'] as CaseScope[]).map(scope=><button key={scope} className={caseScope===scope?'active':''} onClick={()=>setCaseScope(scope)}>{scopeLabel(scope)}</button>)}
            </div>
            <div className="seedGrid compactCaseGrid">
              <label>Case Name<input value={seedName} onChange={e=>setSeedName(e.target.value)} /></label>
              <label>Replay Candle<input readOnly value={activeReplayCandle ? `${shortTime(activeReplayCandle.time, timeframe)} · C ${activeReplayCandle.close.toFixed(2)}` : 'No candle selected'} /></label>
              <label>Case High<input value={caseHigh || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_high:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
              <label>Case Low<input value={caseLow || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_low:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
              <label>Window Start<input value={caseWindowStartDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_start_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
              <label>Window End<input value={caseWindowEndDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_end_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
            </div>
            <div className="seedAnchorBtns compactCaseBtns">
              <button onClick={autoFillCaseAnchors}>Auto-fill All HTF Marks</button>
              <button onClick={()=>captureCaseAnchor('high')}>Use Candle High as Case H</button>
              <button onClick={()=>captureCaseAnchor('low')}>Use Candle Low as Case L</button>
              <button onClick={buildCaseNameFromWindow}>Name From Window</button>
              <button onClick={buildYtdCaseName}>Name YTD</button>
            </div>
            <label className="seedNotes">Notes<textarea value={seedNotes} onChange={e=>setSeedNotes(e.target.value)} placeholder="What this case shows, what was marked, and what the expected/actual path was." /></label>
            {activeCaseRecord && <div className="caseLedgerDetail compactCaseLedger">
              <div className="caseLedgerHeader"><b>Case Ledger Preview</b><span>{activeCaseLedger.scope} · {activeCaseLedger.timeframe} · {activeCaseLedger.rows.length} linked</span></div><div className="caseActionRow miniAuditRow"><button className="gpsSaveBtn secondary" onClick={exportActiveCaseAuditJson}>Export Case JSON</button></div>
              <div className="caseLedgerRows">
                {activeCaseLedger.rows.length === 0 && <div className="caseLedgerEmpty">No linked event rows yet.</div>}
                {activeCaseLedger.rows.slice(0,18).map((ev:any, idx:number)=><button key={ev.id || `${ev.event_type}_${idx}`} onClick={()=>jumpToCaseLedgerEvent(ev)}><b>#{idx + 1}</b><span>{ev._label}</span><em>{shortTime(ev.time, String(activeCaseLedger.timeframe))} · {Number(ev.price).toFixed(2)}</em></button>)}
              </div>
            </div>}
          </div>}
        </div>}
        {rightDeckTab === 'seed' && <div className="rightTabPanel seedTabPanel">
        <div className="seedIdeaPanel sideSeedPanel">
      <div className="seedHeader caseManagerHeader"><div><b>Case Manager</b><span>Update Case saves the container only. Use Save Range for RH/RL.</span></div></div>
      <div className="activeCaseCard"><span>Active Case</span><b>{activeCaseDisplayId ? activeCaseLabel || `#${activeCaseDisplayId}` : 'None selected'}</b><button onClick={resetActiveCase} disabled={!activeCaseDisplayId}>Clear Active</button></div>
      {activeCaseRecord && <div className="caseLedgerDetail">
        <div className="caseLedgerHeader"><b>Case Ledger Preview</b><span>{activeCaseLedger.scope} · {activeCaseLedger.timeframe} · {activeCaseLedger.rows.length} linked event{activeCaseLedger.rows.length===1?'':'s'}</span></div><div className="caseActionRow miniAuditRow"><button className="gpsSaveBtn secondary" onClick={exportActiveCaseAuditJson}>Export Case JSON</button></div>
        <div className="caseLedgerMeta">
          <div><span>High</span><b>{activeCaseLedger.high || 'not saved'}</b>{activeCaseLedger.highSource && <em>{activeCaseLedger.highSource}</em>}</div>
          <div><span>Low</span><b>{activeCaseLedger.low || 'not saved'}</b>{activeCaseLedger.lowSource && <em>{activeCaseLedger.lowSource}</em>}</div>
          <div><span>Window</span><b>{activeCaseLedger.hasWindow ? `${shortTime(activeCaseLedger.start, String(activeCaseLedger.timeframe))} → ${shortTime(activeCaseLedger.end, String(activeCaseLedger.timeframe))}` : 'no date window saved'}</b>{activeCaseLedger.windowSource && <em>{activeCaseLedger.windowSource}</em>}</div>
        </div>
        <div className="candidateAuditCard">
          <div><span>Accepted HTF</span><b>{activeCaseCandidateAudit.accepted.length}</b></div>
          <div><span>Rejected candidates</span><b>{activeCaseCandidateAudit.rejected.length}</b></div>
          <div><span>Edited</span><b>{activeCaseCandidateAudit.edited.length}</b></div>
        </div>
        {activeCaseCandidateAudit.rejected.length > 0 && <div className="rejectedAuditList"><b>Rejected Candidate Audit</b>{activeCaseCandidateAudit.rejected.slice(0,6).map((ev:any, idx:number)=><button key={ev.id || `rej_${idx}`} onClick={()=>jumpToCaseLedgerEvent(ev)}><span>{eventMeta(ev)?.original_label || ev.event_name || 'Rejected candidate'}</span><em>{shortTime(ev.time, String(activeCaseLedger.timeframe))} · {Number(ev.price).toFixed(2)}</em></button>)}</div>}
        <div className="caseLedgerRows">
          {activeCaseLedger.rows.length === 0 && <div className="caseLedgerEmpty">No event rows linked to this case window yet. Case is a container; Save Bundle rows are still the truth.</div>}
          {activeCaseLedger.rows.slice(0,40).map((ev:any, idx:number)=><button key={ev.id || `${ev.event_type}_${idx}`} onClick={()=>jumpToCaseLedgerEvent(ev)}>
            <b>#{idx + 1}</b><span>{ev._label}</span><em>{shortTime(ev.time, String(activeCaseLedger.timeframe))} · {Number(ev.price).toFixed(2)}</em>
          </button>)}
        </div>
        {activeCaseLedger.rows.length > 40 && <div className="caseLedgerMore">Showing first 40. Event Ledger panel has the full raw list. Because apparently candles breed.</div>}
      </div>}
      <div className="caseActionRow">
        <button className="gpsSaveBtn" onClick={()=>saveSeedIdea(false)} disabled={caseSaving}>{caseSaving ? 'Saving...' : getCurrentMappingCaseRef().hasCase ? 'Update Case' : 'Create Case'}</button>
        <button className="gpsSaveBtn danger" onClick={deleteActiveCase} disabled={!activeCaseId}>Delete Active</button>
        <button className="gpsSaveBtn danger" onClick={clearAllCases}>Clear Cases</button>
        <details className="dangerZoneDetails"><summary>Danger Zone</summary><div className="dangerZoneBox"><b>Wipe Mapping Research Data</b><span>Deletes cases, map events, HTF snapshots, objectives, ranges and route memory for this symbol. Raw candles stay. Hidden here because one tired click should not become a data funeral.</span><button className="gpsSaveBtn danger" onClick={resetResearchMappingDb}>Danger: Wipe Mapping Research Data</button></div></details>
      </div>
      {caseSavedNotice && <div className="caseSavedNotice">✓ {caseSavedNotice}</div>}
      <div className="caseScopeStrip">
        {(['MACRO','WEEKLY','DAILY','INTRADAY','MICRO'] as CaseScope[]).map(scope=><button key={scope} className={caseScope===scope?'active':''} onClick={()=>setCaseScope(scope)}>{scopeLabel(scope)}</button>)}
      </div>
      <div className="seedGrid">
        <label>Case Name<input value={seedName} onChange={e=>setSeedName(e.target.value)} /></label>
        <label>Case Timeframe<input readOnly value={`${scopeLabel(caseScope)} · ${caseTimeframe}`} /></label>
        <label>Replay Candle<input readOnly value={activeReplayCandle ? `${shortTime(activeReplayCandle.time, timeframe)} · C ${activeReplayCandle.close.toFixed(2)}` : 'No candle selected'} /></label>
        <label>Case High<input value={caseHigh || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_high:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
        <label>Case Low<input value={caseLow || ''} onChange={e=>setSeedAnchors((p:any)=>({...p, case_low:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} /></label>
        <label>Events in TF<input readOnly value={`Raw ledger mode · old map events ignored`} /></label>
        <label>Window Start<input value={caseWindowStartDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_start_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
        <label>Window End<input value={caseWindowEndDisplay} onChange={e=>setSeedAnchors((p:any)=>({...p, range_end_date:e.target.value, case_scope:caseScope, case_timeframe:caseTimeframe}))} placeholder="anchor-derived" /></label>
      </div>
      <div className="seedAnchorBtns">
        <button onClick={autoFillCaseAnchors}>Auto-fill All HTF Marks</button>
        <button onClick={()=>captureCaseAnchor('high')}>Use Candle High as Case H</button>
        <button onClick={()=>captureCaseAnchor('low')}>Use Candle Low as Case L</button>
        <button onClick={buildCaseNameFromWindow}>Name From Window</button>
        <button onClick={buildYtdCaseName}>Name YTD</button>
      </div>
      <div className="caseLinkHint">Linking later uses date containment: Micro → Intraday → Daily → Weekly → Macro. No daily range is required to save a Macro or Weekly case.</div>
      <label className="seedNotes">Notes<textarea value={seedNotes} onChange={e=>setSeedNotes(e.target.value)} placeholder="What this case shows, what was marked, and what the expected/actual path was." /></label>
      {recentCaseIdeas.length > 0 && <div className="seedIdeaList"><b>Recent cases</b>{recentCaseIdeas.map((x:any)=>{
        const caseKey = String(x.raw_case_id || x.id || '');
        const isActive = caseKey === String(activeCaseDisplayId || '');
        const label = x.is_raw_mapping_case ? `Raw ${caseKey.slice(0,8)}` : `#${x.id}`;
        return <button key={caseKey} className={isActive?'active':''} onClick={()=>openSavedCase(x)}>{label} {x.seed_name} · {shortTime(x.replay_candle_time, x.case_timeframe || x.replay_timeframe)}</button>;
      })}</div>}
    </div>


        </div>}
      </div>
    </div>

    {candleReplayMode && <div className="fixedBottomReplayDock">
      <button onClick={()=>setCandleReplayFrame(effectiveReplayIndex - 1)} disabled={!candles.length || effectiveReplayIndex <= 0}>◀</button>
      <button className={candleReplayPlaying?'active':''} onClick={()=>setCandleReplayPlaying(x=>!x)} disabled={!candles.length}>{candleReplayPlaying ? 'Pause' : 'Play'}</button>
      <button onClick={()=>setCandleReplayFrame(effectiveReplayIndex + 1)} disabled={!candles.length || effectiveReplayIndex >= candles.length - 1}>▶</button>
      <input className="replaySlider dockReplaySlider" type="range" min={0} max={Math.max(0, candles.length - 1)} value={Math.min(effectiveReplayIndex, Math.max(0, candles.length - 1))} onChange={e=>setCandleReplayFrame(Number(e.target.value))} disabled={!candles.length} />
      <label className="speedInput dockSpeedInput">Speed<input type="number" min={120} step={50} value={candleReplaySpeedMs} onChange={e=>setCandleReplaySpeedMs(Math.max(120, Number(e.target.value)||550))} /></label>
      <button onClick={jumpCandleReplayLatest} disabled={!candles.length}>Latest</button>
      <span className="dockMetaText">{candles.length ? `Cursor ${Math.min(effectiveReplayIndex + 1, candles.length)}/${candles.length}` : 'No candles'}{replayCandle ? ` · ${shortTime(replayCandle.time, timeframe)} · C ${replayCandle.close.toFixed(2)}` : ''}</span>
    </div>}
  </div>;
}

type ParentRangeOverlayLine = { timeframe:string; kind:'high'|'low'; price:number; label:string; rangeId?:string|number|null; direction?:string; start?:string; end?:string; };

type D3CandleMapProps = {
  candles:Candle[];
  replayCutTime?:string|null;
  timeframe:string;
  rangeHigh:number;
  rangeLow:number;
  rangeStart?:string;
  rangeEnd?:string;
  hasRange:boolean;
  caseStart?:string;
  caseEnd?:string;
  caseHigh?:string|number;
  caseLow?:string|number;
  parentOverlays?:ParentRangeOverlayLine[];
  events:MapEvent[];
  selectedCandleTime?:string|null;
  selectedCandlePrice?:number|null;
  eventType:string;
  toolMode:'inspect'|'plot'|'drag'|'range'|'select';
  scaleMode:'auto'|'range';
  jumpLatestToken:number;
  fitAllToken:number;
  goDate:string;
  onCursor:(v:any)=>void;
  onAddEvent:(info:{time?:string; price:number; candle?:Candle|null})=>void;
  onCandleSelect?:(info:{candle:Candle; price:number; clientX:number; clientY:number})=>void;
  replayCursorEnabled?:boolean;
  onReplayCursorChange?:(time:string)=>void;
  onUpdateEvent:(id:string, patch:Partial<MapEvent>)=>void;
  onFinishEventDrag:(ev:MapEvent)=>void;
  onRangeChange?:(patch:{high?:number; low?:number; start?:string; end?:string})=>void;
  cameraMode?:'AUTO'|'LOCKED'|'CASE'|'REPLAY';
  cameraCommand?:CameraCommand;
  lockedCameraDomain?:{start:string;end:string}|null;
  lockedPriceDomain?:{low:number;high:number}|null;
  candleWidthScale?:number;
  priceZoomScale?:number;
  cameraKey?:string;
  onCameraDomainChange?:(domain:{start:string;end:string})=>void;
  onVisibleDomainChange?:(domain:VisibleCameraDomain)=>void;
};

function D3CandleMap(props:D3CandleMapProps) {
  const svgRef = useRef<SVGSVGElement|null>(null);
  const transformRef = useRef<any>(d3.zoomIdentity);
  const yPanPxRef = useRef(0);
  const yZoomRef = useRef(1);
  const yDragSnapRef = useRef<{ startY:number; startPan:number } | null>(null);
  const lastYDomainRef = useRef<[number, number] | null>(null);
  const lastYBaseRef = useRef<{baseLo:number;baseHi:number;innerH:number}|null>(null);
  const latestProps = useRef(props);
  latestProps.current = props;
  const cursorRafRef = useRef<number | null>(null);
  const latestCursorPayloadRef = useRef<any>(null);

  const nearestCandle = (date:Date, data:Candle[]) => {
    if (!data.length) return null;
    const t = date.getTime();
    let best = data[0], dist = Math.abs(new Date(data[0].time).getTime()-t);
    for (const c of data) {
      const d = Math.abs(new Date(c.time).getTime()-t);
      if (d < dist) { best = c; dist = d; }
    }
    return best;
  };

  const draw = () => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    const p = latestProps.current;
    const data = p.candles || [];
    const replayCutMs = p.replayCutTime ? new Date(String(p.replayCutTime)).getTime() : null;
    const renderData = replayCutMs && Number.isFinite(replayCutMs) ? data.filter(d => new Date(d.time).getTime() <= replayCutMs) : data;
    const svg = d3.select(svgEl);
    const rect = svgEl.getBoundingClientRect();
    const width = Math.max(900, rect.width || 1200);
    const height = Math.max(520, rect.height || 620);
    const margin = { top: 24, right: 86, bottom: 42, left: 72 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    svg.attr('viewBox', `0 0 ${width} ${height}`);
    svg.selectAll('*').remove();
    svg.append('rect').attr('width', width).attr('height', height).attr('fill', '#000');
    if (!data.length) {
      svg.append('text').attr('x', width/2).attr('y', height/2).attr('text-anchor','middle').attr('fill','#94a3b8').attr('font-size',22).text('No candles loaded yet');
      return;
    }

    if (!renderData.length) {
      svg.append('text').attr('x', width/2).attr('y', height/2).attr('text-anchor','middle').attr('fill','#94a3b8').attr('font-size',18).text('Replay cursor is before available candles');
      return;
    }

    const dateDomainSource = data.length ? data : rawData;
    const dates = dateDomainSource.map(d=>new Date(d.time));
    const x0 = d3.scaleTime().domain(d3.extent(dates) as [Date,Date]).range([margin.left, margin.left+innerW]);
    let zx = transformRef.current.rescaleX(x0);
    const domain = zx.domain();
    const visible = renderData.filter(d=>{ const dt = new Date(d.time); return dt >= domain[0] && dt <= domain[1]; });
    // v081: Do NOT fallback to renderData.slice(-120) when replay cursor moves outside the camera.
    // That fallback made candle stepping feel like the whole map view reset. The camera/zoom transform
    // must remain sovereign; if the replay cursor is offscreen, the viewport stays put until the user
    // pans, clicks Latest/Fit, or uses the slider intentionally.
    const v = visible;
    // v078/v081: auto-scale should breathe around the active viewport, not get pinned by old giant candles.
    // If there are no visible candles after a replay cut, preserve the last y-domain instead of
    // recalculating from the cursor's last 120 candles and yanking the chart vertically.
    const autoscaleLookback = Math.min(v.length, 72);
    const autoScaleSource = p.scaleMode === 'auto' ? v.slice(Math.max(0, v.length - autoscaleLookback)) : v;
    const priorY = lastYDomainRef.current;
    const hiData = d3.max(autoScaleSource, d=>d.high) ?? (priorY ? priorY[1] : (d3.max(renderData.slice(-120), d=>d.high) ?? 1));
    const loData = d3.min(autoScaleSource, d=>d.low) ?? (priorY ? priorY[0] : (d3.min(renderData.slice(-120), d=>d.low) ?? 0));
    const visibleHi = d3.max(v, d=>d.high) ?? hiData;
    const visibleLo = d3.min(v, d=>d.low) ?? loData;
    const parentOverlayPrices = safeArray<any>(p.parentOverlays || []).map((x:any)=>Number(x.price)).filter(Number.isFinite);
    const parentHi = parentOverlayPrices.length ? Math.max(...parentOverlayPrices) : undefined;
    const parentLo = parentOverlayPrices.length ? Math.min(...parentOverlayPrices) : undefined;
    let yHi = hiData, yLo = loData;
    if (p.hasRange && p.scaleMode === 'range' && v.length) { yHi = Math.max(p.rangeHigh, visibleHi); yLo = Math.min(p.rangeLow, visibleLo); }
    if (Number.isFinite(parentHi as any)) yHi = Math.max(yHi, Number(parentHi));
    if (Number.isFinite(parentLo as any)) yLo = Math.min(yLo, Number(parentLo));
    const pad = Math.max((yHi-yLo)*0.18, 1);
    const baseLo = yLo - pad;
    const baseHi = yHi + pad;
    lastYBaseRef.current = { baseLo, baseHi, innerH };
    const zoomY = Math.max(0.25, Math.min(32, (yZoomRef.current || 1)));
    const baseSpan = Math.max(1e-9, baseHi - baseLo);
    const span = baseSpan / zoomY;
    const pricePerPx = span / Math.max(1, innerH);
    const center = ((baseLo + baseHi) / 2) + ((yPanPxRef.current || 0) * pricePerPx);
    const yDomain: [number, number] = [center - span/2, center + span/2];
    if (v.length) lastYDomainRef.current = yDomain;
    p.onVisibleDomainChange?.({ start:domain[0].toISOString(), end:domain[1].toISOString(), priceLow:yDomain[0], priceHigh:yDomain[1] });
    const y = d3.scaleLinear().domain(yDomain).range([margin.top+innerH, margin.top]).nice();

    const plot = svg.append('g').attr('class','plot');
    const grid = plot.append('g');
    grid.selectAll('line.ygrid').data(y.ticks(7)).join('line')
      .attr('x1', margin.left).attr('x2', margin.left+innerW).attr('y1', d=>y(d)).attr('y2', d=>y(d)).attr('stroke','rgba(255,255,255,.08)');
    grid.selectAll('text.ytick').data(y.ticks(7)).join('text')
      .attr('x', 10).attr('y', d=>y(d)+4).attr('fill','rgba(226,232,240,.65)').attr('font-size',13).text(d=>Number(d).toFixed(2));

    // v087.23b: faint parent high/low overlays across lower timeframe maps.
    // No parent fibs/zones here. Stats can calculate premium/discount later; mapping only needs the container H/L.
    const parentLines = safeArray<ParentRangeOverlayLine>(p.parentOverlays || [])
      .filter((ln:any)=>Number.isFinite(Number(ln.price)));
    if (parentLines.length) {
      const pg = plot.append('g').attr('class','parentRangeOverlay').attr('pointer-events','none');
      pg.selectAll('line.parentLine').data(parentLines).join('line')
        .attr('class','parentLine')
        .attr('x1', margin.left)
        .attr('x2', margin.left + innerW)
        .attr('y1', (d:any)=>y(Number(d.price)))
        .attr('y2', (d:any)=>y(Number(d.price)))
        .attr('stroke', (d:any)=>d.kind === 'high' ? 'rgba(148,163,184,.42)' : 'rgba(148,163,184,.34)')
        .attr('stroke-width', 1.25)
        .attr('stroke-dasharray', '10 10');
      const labels = pg.selectAll('g.parentLabel').data(parentLines).join('g')
        .attr('class','parentLabel')
        .attr('transform',(d:any)=>`translate(${margin.left + 10},${y(Number(d.price))-13})`);
      labels.append('rect')
        .attr('width', 150).attr('height', 22).attr('rx', 8)
        .attr('fill','rgba(2,6,23,.70)')
        .attr('stroke','rgba(148,163,184,.25)');
      labels.append('text')
        .attr('x', 9).attr('y', 15)
        .attr('fill','rgba(226,232,240,.82)')
        .attr('font-size', 10)
        .attr('font-weight', 900)
        .text((d:any)=>`${d.label} ${Number(d.price).toFixed(2)}`);
    }

    const baseCandleW = innerW / Math.max(8, v.length || 8) * 0.58;
    const candleW = Math.max(1.0, Math.min(42, baseCandleW * Math.max(0.35, Math.min(4, Number(p.candleWidthScale || 1)))));

    if (!v.length) {
      svg.append('text')
        .attr('x', margin.left + innerW / 2)
        .attr('y', margin.top + 34)
        .attr('text-anchor','middle')
        .attr('fill','rgba(255,191,47,.75)')
        .attr('font-size',12)
        .attr('font-weight',900)
        .text('Replay cursor is outside the current camera view. Pan left/right or click Latest.');
    }

    if (p.hasRange) {
      const fibs = [-25,0,25,50,75,100,125];
      const fib = plot.append('g').attr('class','fibs');

      // Box the fib overlay around a selectable active range window.
      // Start/end can be dragged horizontally. H/L can be dragged vertically.
      // This makes fibs a real map object instead of decorative chart wallpaper.
      const closestHigh = renderData.reduce((best:any, c:any) => Math.abs(c.high - p.rangeHigh) < Math.abs(best.high - p.rangeHigh) ? c : best, renderData[0]);
      const closestLow = renderData.reduce((best:any, c:any) => Math.abs(c.low - p.rangeLow) < Math.abs(best.low - p.rangeLow) ? c : best, renderData[0]);
      const startTime = p.rangeStart || closestHigh.time;
      const endTime = p.rangeEnd || closestLow.time;
      const xA = zx(new Date(startTime));
      const xB = zx(new Date(endTime));
      const rawX0 = Math.min(xA, xB);
      const rawX1 = Math.max(xA, xB);
      const boxPad = Math.max(8, candleW * 0.8);
      const boxX0 = Math.max(margin.left, rawX0 - boxPad);
      const boxX1 = Math.min(margin.left + innerW, rawX1 + boxPad);
      const boxVisible = Number.isFinite(boxX0) && Number.isFinite(boxX1) && boxX1 > boxX0 + 10;

      const y0 = y(p.rangeHigh), y1 = y(p.rangeLow);
      if (Number.isFinite(y0) && Number.isFinite(y1) && boxVisible) {
        fib.append('rect')
          .attr('x', boxX0).attr('y', Math.min(y0,y1))
          .attr('width', boxX1-boxX0).attr('height', Math.abs(y1-y0))
          .attr('fill','rgba(255,191,47,.035)')
          .attr('stroke','rgba(255,191,47,.28)')
          .attr('stroke-width',1.3)
          .attr('stroke-dasharray','8 8')
          .attr('pointer-events', p.toolMode === 'range' ? 'all' : 'none')
          .attr('cursor', p.toolMode === 'range' ? 'move' : 'default')
          .call(d3.drag<any,any>()
            .on('drag', function(event:any){
              if (latestProps.current.toolMode !== 'range') return;
              const dxDate0 = zx.invert(Math.max(margin.left, Math.min(margin.left+innerW, boxX0 + event.dx)));
              const dxDate1 = zx.invert(Math.max(margin.left, Math.min(margin.left+innerW, boxX1 + event.dx)));
              const c0 = nearestCandle(dxDate0, renderData);
              const c1 = nearestCandle(dxDate1, renderData);
              latestProps.current.onRangeChange?.({ start: c0?.time || dxDate0.toISOString(), end: c1?.time || dxDate1.toISOString() });
            }) as any);
      }

      // Fib guide lines only run inside the active boxed range area.
      fib.selectAll('line').data(fibs).join('line')
        .attr('x1', boxVisible ? boxX0 : margin.left)
        .attr('x2', boxVisible ? boxX1 : margin.left+innerW)
        .attr('y1', pct=>y(p.rangeLow + (p.rangeHigh-p.rangeLow)*(pct/100)))
        .attr('y2', pct=>y(p.rangeLow + (p.rangeHigh-p.rangeLow)*(pct/100)))
        .attr('stroke', pct=>pct===50?'rgba(255,255,255,.22)':'rgba(255,191,47,.16)')
        .attr('stroke-dasharray', pct=>pct===50?'8 6':'3 9');
      fib.selectAll('text').data(fibs).join('text')
        .attr('x', (boxVisible ? boxX1 : margin.left+innerW) + 8)
        .attr('y', pct=>y(p.rangeLow + (p.rangeHigh-p.rangeLow)*(pct/100))+4)
        .attr('fill','rgba(255,223,118,.75)').attr('font-size',11).text(pct=>`${pct}%`);

      // Vertical range start/end handles.
      if (boxVisible) {
        const sideHandles = [
          { kind:'start', x:boxX0, label:'S' },
          { kind:'end', x:boxX1, label:'E' }
        ];
        const sh = fib.selectAll('g.rangeSideHandle').data(sideHandles).join('g')
          .attr('class','rangeSideHandle')
          .attr('transform',(d:any)=>`translate(${d.x},${Math.min(y0,y1)})`)
          .attr('cursor', p.toolMode === 'range' ? 'ew-resize' : 'default')
          .attr('pointer-events', p.toolMode === 'range' ? 'all' : 'none');
        sh.append('line').attr('y1',0).attr('y2',Math.abs(y1-y0)).attr('stroke','rgba(255,191,47,.72)').attr('stroke-width',2);
        sh.append('rect').attr('x',-10).attr('y',-18).attr('width',20).attr('height',18).attr('rx',6).attr('fill','rgba(255,191,47,.95)').attr('stroke','#020308').attr('stroke-width',2);
        sh.append('text').attr('y',-5).attr('text-anchor','middle').attr('font-size',10).attr('font-weight',900).attr('fill','#020308').text((d:any)=>d.label);
        sh.call(d3.drag<any,any>()
          .on('drag', function(event:any,d:any){
            if (latestProps.current.toolMode !== 'range') return;
            const px = Math.max(margin.left, Math.min(margin.left+innerW, event.x));
            const date = zx.invert(px);
            const c = nearestCandle(date, renderData);
            if (d.kind === 'start') latestProps.current.onRangeChange?.({ start: c?.time || date.toISOString() });
            if (d.kind === 'end') latestProps.current.onRangeChange?.({ end: c?.time || date.toISOString() });
          }) as any);
      }

      // Draggable high/low fib anchors: adjust range prices directly.
      const anchorX = Math.max(margin.left + 20, Math.min(margin.left + innerW - 20, (boxVisible ? boxX1 : margin.left+innerW) - 12));
      const anchors = [
        { kind:'high', price:p.rangeHigh, label:'H' },
        { kind:'low', price:p.rangeLow, label:'L' }
      ];
      const anchorG = fib.selectAll('g.fibAnchor').data(anchors).join('g')
        .attr('class','fibAnchor')
        .attr('cursor', p.toolMode === 'range' ? 'ns-resize' : 'default')
        .attr('pointer-events', p.toolMode === 'range' ? 'all' : 'none')
        .attr('transform',(d:any)=>`translate(${anchorX},${y(d.price)})`);
      anchorG.append('circle').attr('r',7).attr('fill','#ffbf2f').attr('stroke','#020308').attr('stroke-width',3);
      anchorG.append('text').attr('x',11).attr('y',4).attr('fill','#ffdf76').attr('font-size',10).attr('font-weight',900).text((d:any)=>d.label);
      anchorG.call(d3.drag<any,any>()
        .on('drag', function(event,d:any){
          if (latestProps.current.toolMode !== 'range') return;
          const py = Math.max(margin.top, Math.min(margin.top+innerH, event.y));
          const price = Number(y.invert(py).toFixed(2));
          d3.select(this).attr('transform',`translate(${anchorX},${py})`);
          if (d.kind === 'high') latestProps.current.onRangeChange?.({ high: price });
          if (d.kind === 'low') latestProps.current.onRangeChange?.({ low: price });
        }) as any);    }

    const candlesG = plot.append('g').attr('class','candles');
    candlesG.selectAll('g.candle').data(v, (d:any)=>d.time).join('g')
      .attr('class','candle')
      .each(function(d:any){
        const g = d3.select(this); const x = zx(new Date(d.time)); const up = d.close >= d.open;
        g.append('line').attr('x1',x).attr('x2',x).attr('y1',y(d.high)).attr('y2',y(d.low)).attr('stroke',up?'#35e783':'#ff5b6e').attr('stroke-width',1.6).attr('opacity',.82);
        g.append('rect').attr('x',x-candleW/2).attr('y',Math.min(y(d.open), y(d.close))).attr('width',candleW).attr('height',Math.max(2,Math.abs(y(d.open)-y(d.close)))).attr('rx',1.5).attr('fill',up?'#35e783':'#ff5b6e').attr('opacity',.82);
      });

    // Auto trajectory line intentionally hidden in v048. Route paths should be plotted/refined as saved map coordinates, not drawn as a giant spaghetti noodle.

    const xAxis = d3.axisBottom(zx).ticks(8).tickFormat((d:any)=>shortTime(d.toISOString?.() || d, p.timeframe) as any);
    svg.append('g').attr('transform',`translate(0,${height-margin.bottom})`).call(xAxis as any).selectAll('text').attr('fill','rgba(226,232,240,.7)').attr('font-size',12);
    svg.selectAll('.domain,.tick line').attr('stroke','rgba(226,232,240,.18)');

    if (p.selectedCandleTime) {
      const selectedDate = new Date(String(p.selectedCandleTime));
      if (selectedDate >= domain[0] && selectedDate <= domain[1]) {
        const sx = zx(selectedDate);
        const sy = Number.isFinite(Number(p.selectedCandlePrice)) ? y(Number(p.selectedCandlePrice)) : margin.top + innerH / 2;
        const selG = plot.append('g').attr('class','selectedCandleMarker').attr('pointer-events','none');
        selG.append('line').attr('x1', sx).attr('x2', sx).attr('y1', margin.top).attr('y2', margin.top+innerH).attr('stroke','rgba(255,191,47,.28)').attr('stroke-width',1.5).attr('stroke-dasharray','4 7');
        selG.append('circle').attr('cx', sx).attr('cy', sy).attr('r',5).attr('fill','#ffbf2f').attr('stroke','#020308').attr('stroke-width',2);
        selG.append('text').attr('x', sx + 8).attr('y', sy - 8).attr('fill','#ffdf76').attr('font-size',10).attr('font-weight',900).text('SELECTED');
      }
    }

    const eventG = plot.append('g').attr('class','events');
    const visibleEvents = p.events.filter(ev=>ev.time && new Date(ev.time) >= domain[0] && new Date(ev.time) <= domain[1]);
    const evNodes = eventG.selectAll('g.ev').data(visibleEvents, (d:any)=>d.id).join('g').attr('class','ev').attr('cursor', p.toolMode==='drag'?'grab':'pointer');
    evNodes.attr('transform', d=>`translate(${zx(new Date(d.time || ''))},${y(d.price)})`);
    evNodes.append('line').attr('x1',0).attr('x2',34).attr('y1',0).attr('y2',0).attr('stroke',(d:any)=>d.source==='seed'?'rgba(255,191,47,.55)':'rgba(0,255,208,.45)').attr('stroke-width',2).attr('stroke-dasharray','8 6');
    evNodes.append('circle').attr('r',(d:any)=>d.source==='seed'?6:8).attr('fill',(d:any)=>d.source==='seed'?'#ffbf2f':'#00ffd0').attr('stroke','#001b18').attr('stroke-width',3);
    evNodes.append('text').attr('x',12).attr('y',-10).attr('fill','#e8eef7').attr('font-size',11).attr('font-weight',900).text(d=>eventAbbrev(d.event_type || d.event_name));
    evNodes.append('title').text(d=>`${d.event_name || d.event_type}
Price: ${d.price}
Zone: ${d.zone}
Date: ${shortTime(d.time,p.timeframe)}`);
    evNodes.call(d3.drag<any,MapEvent>()
      .on('drag', function(event, d){
        if (latestProps.current.toolMode !== 'drag' || d.source === 'seed') return;
        const px = Math.max(margin.left, Math.min(margin.left+innerW, event.x));
        const py = Math.max(margin.top, Math.min(margin.top+innerH, event.y));
        const date = zx.invert(px);
        const c = nearestCandle(date, renderData);
        const price = y.invert(py);
        const pct = latestProps.current.hasRange ? zonePercent(price, latestProps.current.rangeLow, latestProps.current.rangeHigh) : null;
        d.time = c?.time || date.toISOString(); d.price = Number(price.toFixed(2)); d.zone = zoneLabel(pct); d.zone_percent = Number((pct ?? 0).toFixed(2));
        d3.select(this).attr('transform',`translate(${zx(new Date(d.time || ''))},${y(d.price)})`);
        latestProps.current.onUpdateEvent(d.id, { time:d.time, price:d.price, zone:d.zone, zone_percent:d.zone_percent });
      })
      .on('end', function(event, d){ if (latestProps.current.toolMode === 'drag') latestProps.current.onFinishEventDrag(d); }) as any);

    // v079: safe manual vertical price panning. Drag the right price strip up/down.
    // The drag uses a frozen start snapshot, not yScale.invert() against a moving domain.
    // That kills the old 7k/-2k hyper-jump bug while giving manual control back.
    const yDragZone = svg.append('rect')
      .attr('x', margin.left + innerW + 2)
      .attr('y', margin.top)
      .attr('width', Math.max(28, margin.right - 8))
      .attr('height', innerH)
      .attr('fill', 'transparent')
      .attr('cursor', 'ns-resize')
      .attr('pointer-events', 'all');

    yDragZone.call(d3.drag<any,any>()
      .on('start', (event:any) => {
        yDragSnapRef.current = { startY: event.y, startPan: yPanPxRef.current || 0 };
      })
      .on('drag', (event:any) => {
        const snap = yDragSnapRef.current;
        if (!snap) return;
        const pixelDelta = event.y - snap.startY;
        yPanPxRef.current = snap.startPan + pixelDelta;
        draw();
      })
      .on('end', () => {
        yDragSnapRef.current = null;
      }) as any);

    yDragZone.on('dblclick', () => {
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
      draw();
    });

    const overlay = svg.append('rect').attr('x',margin.left).attr('y',margin.top).attr('width',innerW).attr('height',innerH).attr('fill','transparent').attr('cursor', p.toolMode==='plot'?'crosshair':(p.toolMode==='select'?'pointer':'grab')).attr('pointer-events', (p.toolMode==='range' || p.toolMode==='drag') ? 'none' : 'all');
    const crossG = svg.append('g').attr('pointer-events','none').style('display','none');
    crossG.append('line').attr('class','cx').attr('y1',margin.top).attr('y2',margin.top+innerH).attr('stroke','rgba(255,255,255,.28)').attr('stroke-dasharray','5 7');
    crossG.append('line').attr('class','cy').attr('x1',margin.left).attr('x2',margin.left+innerW).attr('stroke','rgba(255,255,255,.28)').attr('stroke-dasharray','5 7');
    const priceBubble = crossG.append('g').attr('class','priceBubble');
    priceBubble.append('rect').attr('x',4).attr('width',64).attr('height',24).attr('rx',7).attr('fill','rgba(0,0,0,.78)').attr('stroke','rgba(0,255,208,.45)');
    priceBubble.append('text').attr('x',36).attr('y',16).attr('text-anchor','middle').attr('fill','#00ffd0').attr('font-size',11).attr('font-weight',900);
    const dateBubble = crossG.append('g').attr('class','dateBubble');
    dateBubble.append('rect').attr('y',height-margin.bottom+22).attr('width',92).attr('height',24).attr('rx',7).attr('fill','rgba(0,0,0,.78)').attr('stroke','rgba(255,191,47,.45)');
    dateBubble.append('text').attr('y',height-margin.bottom+38).attr('text-anchor','middle').attr('fill','#ffdf76').attr('font-size',11).attr('font-weight',900);
    overlay.on('mousemove', (event:any)=>{
      const [mx,my] = d3.pointer(event, svgEl);
      const price = y.invert(Math.max(margin.top, Math.min(margin.top+innerH, my)));
      const date = zx.invert(Math.max(margin.left, Math.min(margin.left+innerW, mx)));
      const c = nearestCandle(date, renderData);
      const pct = p.hasRange ? zonePercent(price, p.rangeLow, p.rangeHigh) : null;
      const sx = Math.max(margin.left, Math.min(margin.left+innerW, mx));
      const sy = Math.max(margin.top, Math.min(margin.top+innerH, my));
      crossG.style('display', null); crossG.select('.cx').attr('x1',sx).attr('x2',sx); crossG.select('.cy').attr('y1',sy).attr('y2',sy);
      crossG.select('.priceBubble').attr('transform',`translate(0,${sy-12})`);
      crossG.select('.priceBubble text').text(price.toFixed(2));
      const dateText = shortTime(c?.time || date.toISOString(), p.timeframe);
      const dateX = Math.max(margin.left+46, Math.min(margin.left+innerW-46, sx));
      crossG.select('.dateBubble').attr('transform',`translate(${dateX-46},0)`);
      crossG.select('.dateBubble text').attr('x',46).text(dateText);
      latestCursorPayloadRef.current = { time:c?.time || date.toISOString(), price, zone:zoneLabel(pct), pct: pct ?? undefined, ohlc:c };
      if (cursorRafRef.current == null) {
        cursorRafRef.current = window.requestAnimationFrame(() => {
          cursorRafRef.current = null;
          latestProps.current.onCursor(latestCursorPayloadRef.current);
        });
      }
    }).on('mouseleave', ()=>crossG.style('display','none'))
      .on('click', (event:any)=>{
        const [mx,my] = d3.pointer(event, svgEl);
        const date = zx.invert(Math.max(margin.left, Math.min(margin.left+innerW, mx)));
        const c = nearestCandle(date, renderData);
        const rawPrice = y.invert(Math.max(margin.top, Math.min(margin.top+innerH, my)));
        const price = c ? (Math.abs(rawPrice - c.high) < Math.abs(rawPrice - c.low) ? c.high : c.low) : rawPrice;
        if (latestProps.current.replayCursorEnabled && latestProps.current.toolMode === 'inspect' && c && latestProps.current.onReplayCursorChange) {
          latestProps.current.onReplayCursorChange(c.time);
          return;
        }
        if (latestProps.current.toolMode !== 'plot' && latestProps.current.toolMode !== 'select') return;
        if (latestProps.current.toolMode === 'select' && c && latestProps.current.onCandleSelect) {
          latestProps.current.onCandleSelect({ candle:c, price, clientX:event.clientX, clientY:event.clientY });
          return;
        }
        latestProps.current.onAddEvent({ time:c?.time || date.toISOString(), price, candle:c });
      });

    const zoomed = (event:any) => {
      const next = event.transform;
      // Keep D3 zoom responsible for horizontal time navigation only.
      // Vertical price panning is handled by the dedicated right-side price strip below,
      // using a frozen drag snapshot so it cannot recursively mutate itself into deep space.
      transformRef.current = d3.zoomIdentity.translate(next.x, 0).scale(next.k);
      try {
        const pp = latestProps.current;
        if (pp.cameraMode === 'LOCKED') {
          const dataNow = pp.replayCutTime ? safeArray(pp.candles).filter((d:any)=>new Date(d.time).getTime() <= new Date(String(pp.replayCutTime)).getTime()) : safeArray(pp.candles);
          if (dataNow.length && svgRef.current) {
            const rect2 = svgRef.current.getBoundingClientRect();
            const w2 = Math.max(900, rect2.width || 1200);
            const m2 = { left:72, right:86 };
            const iw2 = w2 - m2.left - m2.right;
            const xBase = d3.scaleTime().domain(d3.extent(dataNow.map((d:any)=>new Date(d.time))) as [Date,Date]).range([m2.left, m2.left+iw2]);
            const dom = transformRef.current.rescaleX(xBase).domain();
            pp.onCameraDomainChange?.({ start: dom[0].toISOString(), end: dom[1].toISOString() });
          }
        }
      } catch {}
      draw();
    };
    const freePad = innerW * 10;
    const zoom = d3.zoom<SVGSVGElement,unknown>()
      .scaleExtent([0.35, Math.max(120, data.length/8)])
      .wheelDelta((event:any)=> -event.deltaY * (event.deltaMode ? 0.24 : 0.008))
      .translateExtent([[-freePad,0],[width+freePad,height]])
      .extent([[margin.left,margin.top],[margin.left+innerW,margin.top+innerH]])
      .on('zoom', zoomed);
    svg.call(zoom as any);
    (svgEl as any).__zoom = transformRef.current;
    svg.on('wheel.priceZoom', null);
  };

  useEffect(()=>{
    if (!svgRef.current || !props.candles.length || props.cameraMode !== 'LOCKED' || !props.lockedCameraDomain?.start || !props.lockedCameraDomain?.end) { draw(); return; }
    const a = new Date(String(props.lockedCameraDomain.start));
    const b = new Date(String(props.lockedCameraDomain.end));
    if (!Number.isFinite(a.getTime()) || !Number.isFinite(b.getTime()) || Math.abs(b.getTime()-a.getTime()) < 1) { draw(); return; }
    const svgEl = svgRef.current;
    const rect = svgEl.getBoundingClientRect();
    const width = Math.max(900, rect.width || 1200);
    const margin = { left:72, right:86 };
    const innerW = width - margin.left - margin.right;
    const cutMs = props.replayCutTime ? new Date(String(props.replayCutTime)).getTime() : null;
    const data = cutMs && Number.isFinite(cutMs) ? safeArray(props.candles).filter((d:any)=>new Date(d.time).getTime() <= cutMs) : safeArray(props.candles);
    if (!data.length) { draw(); return; }
    const x0 = d3.scaleTime().domain(d3.extent(data.map((d:any)=>new Date(d.time))) as [Date,Date]).range([margin.left, margin.left+innerW]);
    const pxA = x0(a); const pxB = x0(b);
    if (Number.isFinite(pxA) && Number.isFinite(pxB) && Math.abs(pxB-pxA) > 4) {
      const lo = Math.min(pxA, pxB);
      const span = Math.abs(pxB-pxA);
      const k = Math.max(0.35, Math.min(180, (innerW * 0.84) / span));
      const tx = (margin.left + innerW * 0.08) - k * lo;
      transformRef.current = d3.zoomIdentity.translate(tx, 0).scale(k);
    }
    draw();
  }, [props.cameraKey, props.candles.length, props.replayCutTime, props.events, props.rangeHigh, props.rangeLow, props.rangeStart, props.rangeEnd, props.toolMode, props.scaleMode, props.timeframe, props.cameraMode, props.lockedCameraDomain?.start, props.lockedCameraDomain?.end, props.candleWidthScale, props.priceZoomScale]);

  useEffect(()=>{
    if (!svgRef.current || !props.candles.length) return;
    const svg = d3.select(svgRef.current);
    const rect = svgRef.current.getBoundingClientRect();
    const width = Math.max(900, rect.width || 1200);
    const margin = { left:72, right:86 };
    const innerW = width - margin.left - margin.right;
    const bars = Math.min(120, props.candles.length);
    const k = Math.max(1, props.candles.length / bars);
    // Leave future space to the right so candles can be centred instead of glued to the edge like bad UI tax.
    const targetRight = margin.left + innerW * 0.78;
    const tx = targetRight - k * (margin.left + innerW);
    const t = d3.zoomIdentity.translate(tx,0).scale(k);
    transformRef.current = t;
    svg.call((d3.zoom() as any).transform, t);
    draw();
  }, [props.jumpLatestToken]);

  useEffect(()=>{
    const command = props.cameraCommand;
    const hasCommand = !!command && command.token > 0 && command.intent !== 'NONE';
    const hasManualFit = props.fitAllToken > 0 || !!props.goDate;
    if (!hasCommand && !hasManualFit) return;
    if (props.cameraMode === 'LOCKED' && props.lockedCameraDomain?.start && props.lockedCameraDomain?.end && !hasCommand && !hasManualFit) return;
    const rawData = props.candles || [];
    const cutMs = props.replayCutTime ? new Date(String(props.replayCutTime)).getTime() : null;
    const data = cutMs && Number.isFinite(cutMs) ? rawData.filter((d:any)=>new Date(d.time).getTime() <= cutMs) : rawData;
    if (!svgRef.current || !data.length) {
      transformRef.current = d3.zoomIdentity;
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
      draw();
      return;
    }
    const svgEl = svgRef.current;
    const rect = svgEl.getBoundingClientRect();
    const width = Math.max(900, rect.width || 1200);
    const margin = { left:72, right:86 };
    const innerW = width - margin.left - margin.right;
    const dateDomainSource = data.length ? data : rawData;
    const dates = dateDomainSource.map(d=>new Date(d.time));
    const x0 = d3.scaleTime().domain(d3.extent(dates) as [Date,Date]).range([margin.left, margin.left+innerW]);
    const fitLatest = () => {
      const bars = Math.min(120, data.length);
      const k = Math.max(1, data.length / Math.max(1, bars));
      const targetRight = margin.left + innerW * 0.78;
      const tx = targetRight - k * (margin.left + innerW);
      transformRef.current = d3.zoomIdentity.translate(tx,0).scale(k);
    };
    const fitAll = () => {
      transformRef.current = d3.zoomIdentity;
      yPanPxRef.current = 0;
      yZoomRef.current = 1;
      return true;
    };
    const fitWindow = (startRaw?:string|null, endRaw?:string|null, singleSpan = 0.35) => {
      const start = startRaw ? new Date(String(startRaw)) : null;
      const end = endRaw ? new Date(String(endRaw)) : null;
      const validStart = !!start && Number.isFinite(start.getTime());
      const validEnd = !!end && Number.isFinite(end.getTime()) && validStart && end!.getTime() > start!.getTime();
      if (!validStart) return false;
      const a = x0(start as Date);
      const b = validEnd ? x0(end as Date) : a + innerW * singleSpan;
      if (!Number.isFinite(a) || !Number.isFinite(b) || Math.abs(b-a) < 10) {
        return false;
      }
      const span = Math.max(10, Math.abs(b-a));
      const k = Math.max(1, Math.min(160, (innerW * 0.82) / span));
      const leftTarget = margin.left + innerW * 0.08;
      const tx = leftTarget - k * Math.min(a,b);
      transformRef.current = d3.zoomIdentity.translate(tx,0).scale(k);
      return true;
    };
    const visibleTimeCenter = () => {
      const dom = transformRef.current.rescaleX(x0).domain();
      const mid = (dom[0].getTime() + dom[1].getTime()) / 2;
      return Number.isFinite(mid) ? new Date(mid) : null;
    };
    const applyHorizontalStretch = (factor:number) => {
      const currentCenter = command?.targetTime ? new Date(String(command.targetTime)) : visibleTimeCenter();
      if (!currentCenter || !Number.isFinite(currentCenter.getTime())) return false;
      const maxK = Math.max(120, data.length / 8);
      const currentK = Number(transformRef.current?.k || 1);
      const nextK = Math.max(0.35, Math.min(maxK, currentK * (Number(factor) || 1)));
      const centerPx = margin.left + innerW / 2;
      const centerBasePx = x0(currentCenter);
      if (!Number.isFinite(centerBasePx)) return false;
      transformRef.current = d3.zoomIdentity.translate(centerPx - nextK * centerBasePx, 0).scale(nextK);
      return true;
    };
    const applyPriceDomain = (lowRaw:any, highRaw:any, padRatio = 0.14) => {
      const low = Number(lowRaw);
      const high = Number(highRaw);
      const base = lastYBaseRef.current;
      if (!base || !Number.isFinite(low) || !Number.isFinite(high) || high <= low) return false;
      const desiredPad = Math.max((high - low) * padRatio, 1);
      const desiredLow = low - desiredPad;
      const desiredHigh = high + desiredPad;
      const desiredSpan = Math.max(1e-9, desiredHigh - desiredLow);
      const desiredCenter = (desiredLow + desiredHigh) / 2;
      const baseSpan = Math.max(1e-9, base.baseHi - base.baseLo);
      const baseCenter = (base.baseLo + base.baseHi) / 2;
      const nextZoom = Math.max(0.25, Math.min(32, baseSpan / desiredSpan));
      const pricePerPx = desiredSpan / Math.max(1, base.innerH);
      yZoomRef.current = nextZoom;
      yPanPxRef.current = (desiredCenter - baseCenter) / pricePerPx;
      return true;
    };
    const applyVerticalStretch = (factor:number) => {
      const base = lastYBaseRef.current;
      const current = lastYDomainRef.current;
      if (!base || !current) return false;
      const currentCenter = (current[0] + current[1]) / 2;
      const nextZoom = Math.max(0.25, Math.min(32, (Number(yZoomRef.current) || 1) * (Number(factor) || 1)));
      const baseSpan = Math.max(1e-9, base.baseHi - base.baseLo);
      const span = baseSpan / nextZoom;
      const pricePerPx = span / Math.max(1, base.innerH);
      const baseCenter = (base.baseLo + base.baseHi) / 2;
      yZoomRef.current = nextZoom;
      yPanPxRef.current = (currentCenter - baseCenter) / pricePerPx;
      return true;
    };
    const fitLocked = () => {
      if (!props.lockedCameraDomain?.start || !props.lockedCameraDomain?.end) return false;
      const ok = fitWindow(props.lockedCameraDomain.start, props.lockedCameraDomain.end);
      if (props.lockedPriceDomain) applyPriceDomain(props.lockedPriceDomain.low, props.lockedPriceDomain.high, 0);
      return ok;
    };
    const intent = hasCommand ? command!.intent : (props.goDate ? 'PRESERVE_OR_NEAREST_TIME' : 'LATEST');
    const targetTime = hasCommand ? command!.targetTime : props.goDate;
    let applied = false;
    if (intent === 'HORIZONTAL_STRETCH') applied = applyHorizontalStretch(command?.scaleFactor || 1) || true;
    if (intent === 'VERTICAL_STRETCH') applied = applyVerticalStretch(command?.scaleFactor || 1) || true;
    if (intent === 'RESTORE_LOCKED') applied = fitLocked();
    if (!applied && intent === 'CASE') {
      applied = fitWindow(props.caseStart || props.rangeStart, props.caseEnd || props.rangeEnd);
      applyPriceDomain(props.caseLow || props.rangeLow, props.caseHigh || props.rangeHigh);
    }
    if (!applied && intent === 'RANGE') {
      applied = fitWindow(props.rangeStart, props.rangeEnd);
      applyPriceDomain(props.rangeLow, props.rangeHigh);
    }
    if (!applied && (intent === 'REPLAY' || intent === 'PRESERVE_OR_NEAREST_TIME' || intent === 'RESTORE_LOCKED')) applied = fitWindow(targetTime || props.goDate, null);
    if (!applied && intent === 'LATEST') { fitLatest(); applied = true; }
    if (!applied && intent === 'FIT_ALL') applied = fitAll();
    if (!applied) {
      fitLatest();
    } else {
      if (intent === 'LATEST') {
        yPanPxRef.current = 0;
        yZoomRef.current = 1;
      }
    }
    draw();
  }, [props.fitAllToken, props.goDate, props.cameraCommand?.token]);

  return <svg ref={svgRef} className="d3CandleSvg" />;
}

function pageTitle(p: Page) { return ({ visual:'Saved Range Maps', mapstudio:'Map Studio', ideas:'Trade Ideas', brain:'Lifecycle Catch-Up', live:'Live Trade', journal:'Journal Reports', sql:'SQL / Backend', settings:'Display Settings', data:'Data Collection', historical:'Historical Lifecycle Builder' } as any)[p]; }
function pageSubtitle(p: Page) { return ({ visual:'Weekly and Daily stay clean. Intraday gets the execution room it actually deserves.', mapstudio:'OHLC candles, range overlay, trajectory path, and event coordinates. Finally, candles with memory.', ideas:'Pre-plan the narrative before the market starts whispering nonsense.', brain:'Manually catch the machine up with Macro → Weekly → Daily → Intraday → Micro lifecycle state.', live:'Active trade state, TP status, and linked idea.', journal:'Historical live trades and future data collection view.', sql:'Backend status and recent records.', settings:'Set ranges, mitigation states, tick intervals, and editable map paths.', data:'Scenario calculator and sample stress testing.', historical:'Create date-aware Weekly/Daily/Intraday lifecycle bundles. The machine links context by symbol + date.' } as any)[p]; }

function XYTrajectoryPanel({ title, layerKey, layer, visual, updateVisual, accent, intraday, livePrice, readOnly = false, compact = false }: { title: string; layerKey: LayerKey; layer?: Layer; visual: VisualLayer; updateVisual: (k: LayerKey, p: Partial<VisualLayer>) => void; accent: string; intraday?: any; livePrice?: number | null; readOnly?: boolean; compact?: boolean }) {
  const currentZone = visual.currentZone || layer?.auto_location || layer?.location || (intraday?.phase_label || 'Fair');
  const objective = visual.objectiveZone || layer?.objective || intraday?.trade_type || 'Objective';
  const trajectory = visual.narrative || layer?.trajectory || intraday?.current_state || 'Manual trajectory';
  const path = visual.path || [];
  const low = parseNum(visual.rangeLow), high = parseNum(visual.rangeHigh);
  const hasRange = Number.isFinite(low) && Number.isFinite(high) && high > low;
  const tickStep = Number(visual.tickStep || (layerKey === 'intraday' ? 50 : 200));
  const ticks = hasRange ? buildPriceTicks(low, high, tickStep) : [];
  const liveCurrentEnabled = !!visual.useLiveCurrent;
  const displayPoint = (p: GraphPoint) => {
    const isCurrent = String(p.label || '').toLowerCase().includes('current') || !!p.live;
    if (liveCurrentEnabled && isCurrent && livePrice && hasRange) return { ...p, price: String(Math.round(livePrice * 100) / 100), live: true };
    return p;
  };
  const displayPath = path.map(displayPoint);
  const currentIndex = Math.max(0, displayPath.findIndex(p => String(p.label || '').toLowerCase().includes('current') || !!p.live));
  const currentPoint = displayPath[currentIndex >= 0 ? currentIndex : Math.max(0, displayPath.length - 1)];
  const yPoint = (p: GraphPoint) => hasRange && p.price ? yForPrice(parseNum(p.price), low, high) : yForZone(p.zone);
  const yObjective = hasRange ? yForPrice(priceForZone(objective, low, high), low, high) : yForZone(objective);
  const yLive = hasRange && livePrice ? yForPrice(livePrice, low, high) : null;
  const yCurrentGuide = currentPoint ? yPoint(currentPoint) : yLive;
  const liveStatus = liveCurrentEnabled ? (livePrice ? 'LIVE' : 'STALE') : 'MANUAL';
  const pointX = (p: GraphPoint, i: number) => matrixXForPoint(p, i, displayPath.length, layerKey);
  const projectionX = readOnly && layerKey === 'intraday' ? 92 : (readOnly && currentPoint ? Math.max(92, pointX(currentPoint, currentIndex)) : clamp(Number(visual.projectionX ?? 90), 10, 96));
  const projectionPrice = parseNum(visual.projectionPrice);
  const yProjection = hasRange && Number.isFinite(projectionPrice) ? yForPrice(projectionPrice, low, high) : yObjective;
  const brokenExternal = visual.brokenExternal || 'NONE';
  const brokenExternalPrice = parseNum(visual.brokenExternalPrice);
  const brokenY = brokenExternal === 'NONE' ? null : (hasRange && Number.isFinite(brokenExternalPrice) ? yForPrice(brokenExternalPrice, low, high) : brokenExternal === 'EXT_H' ? 8 : 92);
  const liquidityCleanUpPrice = parseNum(visual.liquidityCleanUpPrice);
  const liquidityCleanUpY = layerKey === 'intraday' && hasRange && Number.isFinite(liquidityCleanUpPrice) ? yForPrice(liquidityCleanUpPrice, low, high) : null;
  const showLiquidityCleanUp = layerKey === 'intraday' && visual.showLiquidityCleanUp !== false && liquidityCleanUpY !== null;
  const biasFlow = getExtFlow(visual.mapBias, trajectory);
  const rightFlowLabel = biasFlow === 'bearish' ? 'EXT H → EXT L' : biasFlow === 'bullish' ? 'EXT L → EXT H' : 'EXT L ↔ EXT H';

  const updatePoint = (id: string, patch: Partial<GraphPoint>) => updateVisual(layerKey, { path: path.map(p => p.id === id ? { ...p, ...patch } : p) });
  const addPoint = () => updateVisual(layerKey, { path: [...path, makePoint(anchorsForLayer(layerKey)[0] || 'NEW_ANCHOR', currentZone, 50, hasRange ? String(Math.round(priceForZone(currentZone, low, high) * 100) / 100) : '', anchorsForLayer(layerKey)[0] || 'NEW_ANCHOR')] });
  const removePoint = (id: string) => updateVisual(layerKey, { path: path.filter(p => p.id !== id) });
  const movePoint = (id: string, dir: -1 | 1) => { const idx = path.findIndex(p => p.id === id); const next = idx + dir; if (idx < 0 || next < 0 || next >= path.length) return; const copy = [...path]; [copy[idx], copy[next]] = [copy[next], copy[idx]]; updateVisual(layerKey, { path: copy }); };
  const clearPath = () => updateVisual(layerKey, { path: [makePoint('Origin', currentZone, 12), makePoint('Current', currentZone, 48)] });
  const structuralMetrics = getStructuralMetrics(layerKey, displayPath, low, high, hasRange, currentPoint, visual);
  const narrativeInvalidated = String(visual.meta?.phaseState || '').toUpperCase() === 'INVALIDATED' || displayPath.some(p => String(p.status || '').toUpperCase() === 'INVALIDATED');

  const dragPoint = (id: string, e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const graph = (e.currentTarget.closest('.xyGraph') as HTMLDivElement); if (!graph) return;
    const updateFromEvent = (ev: PointerEvent | React.PointerEvent) => {
      const r = graph.getBoundingClientRect();
      const yPct = clamp(((ev.clientY - r.top) / r.height) * 100, 4, 96);
      const patch: Partial<GraphPoint> = {}; // v0.20: X position is matrix-sequenced; dragging adjusts price only.
      if (hasRange) patch.price = String(Math.round(priceFromY(yPct, low, high) * 100) / 100); else patch.zone = zoneFromY(yPct);
      updatePoint(id, patch);
    };
    updateFromEvent(e);
    const move = (ev: PointerEvent) => updateFromEvent(ev);
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };



  const dragProjection = (e: React.PointerEvent<HTMLDivElement>) => {
    if (readOnly) return;
    e.preventDefault();
    const graph = (e.currentTarget.closest('.xyGraph') as HTMLDivElement); if (!graph) return;
    const updateFromEvent = (ev: PointerEvent | React.PointerEvent) => {
      const r = graph.getBoundingClientRect();
      const x = clamp(((ev.clientX - r.left) / r.width) * 100, 10, 96);
      const yPct = clamp(((ev.clientY - r.top) / r.height) * 100, 4, 96);
      const patch: Partial<VisualLayer> = { projectionX: x };
      if (hasRange) patch.projectionPrice = String(Math.round(priceFromY(yPct, low, high) * 100) / 100);
      else patch.objectiveZone = zoneFromY(yPct);
      updateVisual(layerKey, patch);
    };
    updateFromEvent(e);
    const move = (ev: PointerEvent) => updateFromEvent(ev);
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };

  return <div className={`trajectoryCard xy layer-${layerKey} ${accent} ${visual.mapBias || 'manual'}Bias ${readOnly ? 'readOnlyMap' : 'editableMap'} ${compact ? 'compactMap' : ''}`}>
    <div className="cardHeader"><div><h3>{title}</h3><p>{trajectory}</p></div><div className="headerBadges"><div className="locationBadge">Current: {currentZone}</div><div className="objectiveBadge">Objective: {objective}</div></div></div>
    {!readOnly && <div className="rangeInputs compact"><label>Low<input value={visual.rangeLow || ''} onChange={e => updateVisual(layerKey, { rangeLow: e.target.value })} placeholder="range low" /></label><label>High<input value={visual.rangeHigh || ''} onChange={e => updateVisual(layerKey, { rangeHigh: e.target.value })} placeholder="range high" /></label><label>Tick<select value={String(tickStep)} onChange={e => updateVisual(layerKey, { tickStep: Number(e.target.value) })}><option value="50">$50</option><option value="100">$100</option><option value="200">$200</option><option value="500">$500</option></select></label><label>Objective<select value={objective} onChange={e => updateVisual(layerKey, { objectiveZone: e.target.value })}>{ZONES.map(z => <option key={z}>{z}</option>)}</select></label><label>Broken External<select value={visual.brokenExternal || 'NONE'} onChange={e => updateVisual(layerKey, { brokenExternal: e.target.value as any })}><option value="NONE">None</option><option value="EXT_H">Broken EXT H</option><option value="EXT_L">Broken EXT L</option></select></label><label>Broken Ref Price<input value={visual.brokenExternalPrice || ''} onChange={e => updateVisual(layerKey, { brokenExternalPrice: e.target.value })} placeholder="broken level price" /></label><label>Projection Price<input value={visual.projectionPrice || ''} onChange={e => updateVisual(layerKey, { projectionPrice: e.target.value })} placeholder="drag blue endpoint" /></label><label className="checkLabel"><input type="checkbox" checked={!!visual.useLiveCurrent} onChange={e => updateVisual(layerKey, { useLiveCurrent: e.target.checked })}/> Current uses live price</label></div>}
    <div className={`xyGraph boxedGraph cleanMapGraph matrixRailGraph ${narrativeInvalidated ? 'invalidatedGraph' : ''}`}>
      <div className="fibBackdrop"><div className="fibPremium"><span>Premium</span></div><div className="fibFair"><span>Fair price</span></div><div className="fibDiscount"><span>Discount</span></div></div>
      <div className="matrixRails">{[0,1,2,3,4,5].map(i => <span key={i} style={{ left: `${matrixXFor(i,6)}%` }}><b>{matrixLabelFor(layerKey, i)}</b></span>)}</div>
      {structuralMetrics.length > 0 && <div className="metricOverlay">{structuralMetrics.map((m, i) => <span key={i}>{m}</span>)}</div>}
      {narrativeInvalidated && <div className="invalidatedCloak"><b>STRUCTURE INVALIDATED</b><span>Future columns muted. Narrative dead.</span></div>}
      {hasRange && <div className="priceAxis clean leftPriceAxis">{ticks.map(t => <span key={t.price} style={{ top: `${t.y}%` }}>{t.price}</span>)}</div>}
      {!hasRange && <div className="priceAxis clean leftPriceAxis zoneFallback"><span style={{top:'8%'}}>Ext H</span><span style={{top:'50%'}}>Fair</span><span style={{top:'92%'}}>Ext L</span></div>}
      <div className="axisX"><span>Origin</span><span>Reaction</span><span>Current</span><span>Objective</span></div>
      <div className="rangeBoundaryLine high"></div>
      <div className="rangeBoundaryLine low"></div>
      <div className="objectiveGlow" style={{ top: `${yObjective}%` }}><span>{objective}</span></div>
      {brokenY !== null && <div className={`brokenExternalLine ${brokenExternal === 'EXT_H' ? 'high' : 'low'}`} style={{ top: `${brokenY}%` }}><span>{brokenExternal === 'EXT_H' ? 'Broken EXT H / BOS ref' : 'Broken EXT L / BOS ref'}</span></div>}
      {yCurrentGuide !== null && <div className={`currentGuideLine ${liveStatus.toLowerCase()}`} style={{ top: `${yCurrentGuide}%` }}><span>Current {currentPoint?.price ? currentPoint.price : currentZone} · {liveStatus}</span></div>}
      {yLive !== null && <div className="livePriceLine" style={{ top: `${yLive}%` }}><span>Live {livePrice?.toFixed(2)}</span></div>}
      {showLiquidityCleanUp && <div className="liquidityCleanUpLine" style={{ top: `${liquidityCleanUpY}%` }}><span>Liquidity Clean Up: {visual.liquidityCleanUpPrice}</span></div>}
      <svg className="xySvg" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline className="pricePath" points={displayPath.map((p, i) => `${pointX(p, i)},${yPoint(p)}`).join(' ')} />{path.length > 0 && <polyline className="ghostPath" points={`${pointX(currentPoint || displayPath[displayPath.length-1], currentIndex >= 0 ? currentIndex : displayPath.length-1)},${yPoint(currentPoint || displayPath[displayPath.length-1])} ${projectionX},${yProjection}`} />}</svg>
      {path.length > 0 && !readOnly && <div onPointerDown={dragProjection} className="projectionHandle" style={{ left: `${projectionX}%`, top: `${yProjection}%` }}><span>Drag projection</span></div>}
      {displayPath.map((p, i) => { const isCurrentPoint = i === currentIndex || String(p.label || '').toLowerCase().includes('current') || !!p.live; return <div key={p.id} onPointerDown={readOnly ? undefined : (e) => dragPoint(p.id, e)} className={`graphNode ${isCurrentPoint ? 'currentNode liveDominantNode' : ''} ${readOnly ? 'lockedNode' : ''}`} style={{ left: `${pointX(p, i)}%`, top: `${yPoint(p)}%` }}><span>{p.label}{hasRange && p.price ? ` • ${p.price}` : ''}</span></div>; })}
    </div>
    {!readOnly && <div className="pathEditor"><div className="editorTitle"><b>Plot map path</b><div className="btnRow"><button onClick={addPoint}>+ Add swing</button><button onClick={clearPath}>Reset</button></div></div>{path.map((p, idx) => <PointRow key={p.id} point={p} index={idx} total={path.length} layerKey={layerKey} hasRange={hasRange} low={low} high={high} updatePoint={updatePoint} removePoint={removePoint} movePoint={movePoint}/>)}</div>}
    <div className="legendRow"><Mini label="Range" value={`${visual.rangeLow || 'Low'} → ${visual.rangeHigh || 'High'}`} /><Mini label="Path" value={path.map(p => p.label || p.zone).join(' → ')} /><Mini label="Next draw" value={objective} highlight /></div>
    <div className="mitigationRow"><Pill label="Ext L" value={visual.mitigation.extL || layer?.external_low_mitigation || 'Fresh'} /><Pill label="Disc" value={visual.mitigation.discount || layer?.discount_mitigation || 'Fresh'} /><Pill label="Prem" value={visual.mitigation.premium || layer?.premium_mitigation || 'Fresh'} /><Pill label="Ext H" value={visual.mitigation.extH || layer?.external_high_mitigation || 'Fresh'} /></div>
  </div>;
}

function PointRow({ point, index, total, layerKey, hasRange, low, high, updatePoint, removePoint, movePoint }: any) {
  const anchorOptions = anchorsForLayer(layerKey || 'daily');
  return <div className="pointRow pointRowV6">
    <div className="orderButtons"><button disabled={index === 0} onClick={() => movePoint(point.id, -1)}>↑</button><button disabled={index >= total - 1} onClick={() => movePoint(point.id, 1)}>↓</button></div>
    <select value={point.anchorKey || point.label || anchorOptions[0]} onChange={e => updatePoint(point.id, { anchorKey: e.target.value, label: e.target.value })}>{anchorOptions.map((z:string) => <option key={z}>{z}</option>)}</select>
    <select value={point.status || 'INTACT'} onChange={e => updatePoint(point.id, { status: e.target.value })}>{ANCHOR_STATUS.map(z => <option key={z}>{z}</option>)}</select>
    <select value={point.zone} onChange={e => updatePoint(point.id, { zone: e.target.value, price: hasRange ? String(Math.round(priceForZone(e.target.value, low, high) * 100) / 100) : point.price })}>{ZONES.map(z => <option key={z}>{z}</option>)}</select>
    <input value={point.price || ''} onChange={e => updatePoint(point.id, { price: e.target.value, live: false })} placeholder="price" />
    <input value={point.role || ''} onChange={e => updatePoint(point.id, { role: e.target.value })} placeholder="role / note" />
    <span className="matrixCol">COL {anchorColumnIndex(point, index, total, layerKey || 'daily') + 1}</span>
    <label className="pointLiveToggle"><input type="checkbox" checked={!!point.live} onChange={e => updatePoint(point.id, { live: e.target.checked })}/> live</label>
    <button className="smallDanger" onClick={() => removePoint(point.id)}>×</button>
  </div>;
}


function LifecycleBrainPanel({ brain }: any) {
  const participation = brain?.participation || {};
  const daily = brain?.daily || {};
  const intraday = brain?.intraday || {};
  const weekly = brain?.weekly || {};
  const status = participation.participation_status || 'WAITING';
  const allowed = !!participation.execution_allowed;
  return <div className="card lifecycleBrainCard">
    <div className="cardHeader tight"><div><h3>Trade Lifecycle Brain</h3><p>Daily direction → Intraday phase → Micro confirmation → participation.</p></div><Target className={allowed ? 'goldIcon' : 'blueIcon'} size={22}/></div>
    <div className="metricGrid">
      <Metric label="Participation" value={status} color={allowed ? '#42e68a' : '#ffbf2f'} />
      <Metric label="Direction" value={participation.suggested_direction || 'NONE'} color={String(participation.suggested_direction).includes('BUY') ? '#42e68a' : String(participation.suggested_direction).includes('SELL') ? '#ff4d67' : '#7b8794'} />
      <Metric label="Daily Bias" value={daily.daily_bias || 'WATCHING'} color="#dbeafe" />
      <Metric label="Daily Position" value={fmtPctOrDash(daily.position_pct)} color="#dbeafe" />
      <Metric label="Daily Range Source" value={daily?.source?.range || (daily.range_low && daily.range_high ? 'map' : 'missing')} color="#7dd3fc" />
      <Metric label="Intraday" value={intraday.intraday_state || 'WAITING'} color="#00ffd0" />
      <Metric label="Retest" value={intraday.retest_status || '-'} color="#ffbf2f" />
      <Metric label="Favourable Trade" value={intraday.favourable_trade || '-'} color="#e5e7eb" />
      <Metric label="Weekly" value={weekly.weekly_state || 'CONTEXT'} color="#a78bfa" />
    </div>
    <div className="machineMessage"><b>Machine says:</b><span>{participation.machine_message || participation.reason || 'No lifecycle snapshot yet. Save/load map state first.'}</span></div>
    <div className="machineMessage mutedMessage"><b>Map pull:</b><span>Daily range/profile now derives from saved Map Settings unless the Catch-Up Wizard has an explicit non-default override.</span></div>
    <div className="machineMessage mutedMessage"><b>Next:</b><span>{participation.next_required_step || 'Waiting for rule-chain progress.'}</span></div>
  </div>;
}


const MACRO_STATES = ['MACRO_CONTEXT_MANUAL','MACRO_RANGE_ACTIVE','MACRO_LOW_ABANDONED','MACRO_HIGH_ABANDONED','MACRO_EXPANSION_ACTIVE','NEW_MACRO_RANGE_CONFIRMED','MACRO_DEMAND_INTERACTION','MACRO_SUPPLY_INTERACTION','MACRO_TRAJECTORY_FLIP'];
const WEEKLY_STATES_V130 = ['WEEKLY_CONTEXT_ACTIVE','WEEKLY_RANGE_ACTIVE','WEEKLY_EXPANSION_ACTIVE','WEEKLY_PULLBACK_TO_MACRO_FAIR_PRICE','WEEKLY_INDUCEMENT_SWING_FORMED','WEEKLY_BOS_DOWN_RECLAIM','WEEKLY_BOS_UP_RECLAIM','WEEKLY_BULLISH_BIAS_ACTIVE','WEEKLY_BEARISH_BIAS_ACTIVE','WEEKLY_RANGE_ABANDONED','WEEKLY_OLD_RANGE_RETEST_PENDING'];
const DAILY_STATES_V130 = ['DAILY_PRE_CHOCH','DAILY_CHOCH_CONFIRMED','DAILY_CHOCH_RANGE_MARKED','DAILY_P1_ACTIVE','DAILY_P1_BOS_CONFIRMED','DAILY_P2_ACTIVE','DAILY_P2_BOS_CONFIRMED','DAILY_P3_ACTIVE','DAILY_P3_FAILED','DAILY_NEW_P1_ACTIVE','DAILY_PROFILE_FLIP_ACTIVE','DAILY_INDUCEMENT_SWING_FORMED','DAILY_CONTINUATION_RESUMED','DAILY_INVALIDATED'];
const DAILY_STRUCTURE_EVENTS_V130 = ['WAITING','BOS_UP_RECLAIM','BOS_DOWN_RECLAIM','MOMENTUM_BOS_UP','MOMENTUM_BOS_DOWN','SUPPLY_FLIP_DEMAND','DEMAND_FLIP_SUPPLY','BULLISH_CONTINUATION','BEARISH_CONTINUATION'];
const INTRADAY_STATES_V130 = ['PRE_CHOCH','CHOCH_CONFIRMED','CHOCH_RANGE_MARKED','IMMEDIATE_ENTRY_ACTIVE','P1_ACTIVE','P1_BOS_CONFIRMED','P2_ACTIVE','P2_RETEST_ACTIVE','P2_RETEST_COMPLETE','P2_BOS_CONFIRMED','INTERNAL_SWEEP_CLEANUP','REF_CONFIRMATION_ACTIVE','ADD_RISK_READY','P3_ACTIVE','P3_FAILED','NEW_P1_ACTIVE','PROFILE_FLIP_ACTIVE','INVALIDATED'];
const BIAS_OPTIONS_V130 = ['WATCHING','BULLISH','BEARISH'];
const INDUCEMENT_OPTIONS_V130 = ['NOT_TAGGED','INDUCEMENT_SWING_BULLISH','INDUCEMENT_SWING_BEARISH'];
const RETEST_OPTIONS_V130 = ['WAITING','RETEST_PENDING','RETEST_ACTIVE','RETEST_COMPLETE','RETEST_FAILED','PROFILE_SHIFT'];
const FAV_TRADE_OPTIONS_V130 = ['NO_FAVOURABLE_TRADE','IMMEDIATE_CONTINUATION','P1_DEVELOPMENT','P2_CONTINUATION','P3_FAILURE_REVERSAL','NEW_P1_PROFILE_FLIP_CONTINUATION','CONFIRMED_CONTINUATION_ADD_RISK'];
const MICRO_OPTIONS_V130 = ['WAITING','CONFIRMED','READY','REF_CANDLE_CONFIRMED','MICRO_ENTRY_APPROVED','INVALIDATED'];

function LifecycleCatchUpWizard({ symbol, onSaved }: { symbol: string; onSaved?: () => void }) {
  const [snap, setSnap] = useState<any>(null);
  const [msg, setMsg] = useState('');
  const loadSnap = async () => {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/lifecycle/snapshot?symbol=${encodeURIComponent(symbol)}`);
      const j = await r.json();
      setSnap(j?.snapshot || null);
      setMsg(`Loaded ${new Date().toLocaleTimeString()}`);
    } catch (e:any) { setMsg(`Load failed: ${e?.message || e}`); }
  };
  useEffect(() => { loadSnap(); }, [symbol]);
  const update = (section: string, key: string, value: any) => setSnap((prev:any) => ({ ...(prev || { symbol }), [section]: { ...((prev || {})[section] || {}), [key]: value }}));
  const save = async () => {
    try {
      const payload = { ...(snap || {}), symbol, updated_by: 'electron', updated_from_device: 'electron_catch_up_wizard' };
      const r = await fetch(`${BASE_URL}/api/v1/lifecycle/snapshot`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const j = await r.json();
      if (!r.ok || j?.ok === false) throw new Error(j?.error || `Save failed ${r.status}`);
      setSnap(j.snapshot);
      setMsg(`Saved ${new Date().toLocaleTimeString()}`);
      onSaved?.();
    } catch (e:any) { setMsg(`Save failed: ${e?.message || e}`); }
  };
  const macro = snap?.macro || {}, weekly = snap?.weekly || {}, daily = snap?.daily || {}, intraday = snap?.intraday || {}, micro = snap?.micro || {};
  return <div className="card largeCard catchUpWizard">
    <div className="cardHeader tight"><div><h3>Lifecycle Catch-Up Wizard</h3><p>Tell the machine the current family-tree story. Backend stores this and Android/Electron both read it.</p></div><Target className="goldIcon" size={24}/></div>
    <div className="settingsActionRow"><button onClick={loadSnap}>Load Snapshot</button><button className="primaryBtn" onClick={save}>Save To Backend</button><span>{msg || 'Backend lifecycle memory, not execution.'}</span></div>
    <div className="catchGrid">
      <CatchCard title="Macro / Grandparent"><SelectLine label="State" value={macro.macro_state} options={MACRO_STATES} onChange={(v:any)=>update('macro','macro_state',v)}/><InputLine label="Abandoned Low" value={macro.abandoned_macro_low} onChange={(v:any)=>update('macro','abandoned_macro_low',v)}/><InputLine label="Abandoned High" value={macro.abandoned_macro_high} onChange={(v:any)=>update('macro','abandoned_macro_high',v)}/><InputLine label="New Macro High" value={macro.new_macro_swing_high} onChange={(v:any)=>update('macro','new_macro_swing_high',v)}/><InputLine label="Macro Low" value={macro.macro_low} onChange={(v:any)=>update('macro','macro_low',v)}/><InputLine label="Macro High" value={macro.macro_high} onChange={(v:any)=>update('macro','macro_high',v)}/></CatchCard>
      <CatchCard title="Weekly / Parent"><SelectLine label="State" value={weekly.weekly_state} options={WEEKLY_STATES_V130} onChange={(v:any)=>update('weekly','weekly_state',v)}/><SelectLine label="Bias" value={weekly.weekly_bias} options={BIAS_OPTIONS_V130} onChange={(v:any)=>update('weekly','weekly_bias',v)}/><SelectLine label="Inducement" value={weekly.inducement_swing} options={INDUCEMENT_OPTIONS_V130} onChange={(v:any)=>update('weekly','inducement_swing',v)}/><SelectLine label="Objective 1" value={weekly.objective_1} options={OBJECTIVE_TYPES} onChange={(v:any)=>update('weekly','objective_1',v)}/><SelectLine label="Objective 2" value={weekly.objective_2} options={OBJECTIVE_TYPES} onChange={(v:any)=>update('weekly','objective_2',v)}/></CatchCard>
      <CatchCard title="Daily / Tradeable Route"><SelectLine label="State" value={daily.daily_state} options={DAILY_STATES_V130} onChange={(v:any)=>update('daily','daily_state',v)}/><SelectLine label="Profile" value={daily.daily_profile} options={DAILY_PROFILES} onChange={(v:any)=>update('daily','daily_profile',v)}/><SelectLine label="Structure Event" value={daily.structure_event} options={DAILY_STRUCTURE_EVENTS_V130} onChange={(v:any)=>update('daily','structure_event',v)}/><SelectLine label="PD Sweep" value={daily.previous_day_sweep} options={['NONE','PDH','PDL']} onChange={(v:any)=>update('daily','previous_day_sweep',v)}/><SelectLine label="Inducement" value={daily.inducement_swing} options={INDUCEMENT_OPTIONS_V130} onChange={(v:any)=>update('daily','inducement_swing',v)}/><SelectLine label="Retest" value={daily.retest_status} options={RETEST_OPTIONS_V130} onChange={(v:any)=>update('daily','retest_status',v)}/></CatchCard>
      <CatchCard title="Intraday / Execution"><SelectLine label="State" value={intraday.phase_state || intraday.intraday_state} options={INTRADAY_STATES_V130} onChange={(v:any)=>update('intraday','phase_state',v)}/><SelectLine label="Profile" value={intraday.intraday_profile} options={INTRADAY_PROFILES} onChange={(v:any)=>update('intraday','intraday_profile',v)}/><SelectLine label="Favourable Trade" value={intraday.favourable_trade} options={FAV_TRADE_OPTIONS_V130} onChange={(v:any)=>update('intraday','favourable_trade',v)}/><SelectLine label="Retest" value={intraday.retest_status} options={RETEST_OPTIONS_V130} onChange={(v:any)=>update('intraday','retest_status',v)}/><InputLine label="CHOCH High" value={intraday.choch_high} onChange={(v:any)=>update('intraday','choch_high',v)}/><InputLine label="CHOCH Break" value={intraday.choch_break} onChange={(v:any)=>update('intraday','choch_break',v)}/><InputLine label="CHOCH Low" value={intraday.choch_low} onChange={(v:any)=>update('intraday','choch_low',v)}/><InputLine label="Liquidity Cleanup" value={intraday.liquidity_cleanup_price} onChange={(v:any)=>update('intraday','liquidity_cleanup_price',v)}/></CatchCard>
      <CatchCard title="Micro / 15m Confirmation"><SelectLine label="Confirmation" value={micro.confirmation} options={MICRO_OPTIONS_V130} onChange={(v:any)=>update('micro','confirmation',v)}/><InputLine label="Trigger TF" value={micro.trigger_timeframe} onChange={(v:any)=>update('micro','trigger_timeframe',v)}/><InputLine label="Trigger Model" value={micro.trigger_model} onChange={(v:any)=>update('micro','trigger_model',v)}/></CatchCard>
    </div>
  </div>;
}
function CatchCard({ title, children }: any) { return <div className="catchCard"><h4>{title}</h4>{children}</div>; }
function SelectLine({ label, value, options, onChange }: any) { return <label className="fieldLine"><span>{label}</span><select value={value || options?.[0] || ''} onChange={e=>onChange(e.target.value)}>{(options || []).map((o:any)=><option key={o}>{o}</option>)}</select></label>; }
function InputLine({ label, value, onChange }: any) { return <label className="fieldLine"><span>{label}</span><input value={value ?? ''} onChange={e=>onChange(e.target.value)} /></label>; }

function TradeIdeaPanel({ ideas, setIdeas, selectedIdea, setSelectedIdea, state, brain, currentSymbol, large }: any) {
  const [form, setForm] = useState<Partial<TradeIdea>>({ symbol: 'XAUUSD', direction: 'SELL', setupType: 'Continuation', status: 'Watching', riskMode: 'Feeler Risk 0.5%' });
  const addIdea = () => {
    const idea: TradeIdea = { id: `idea_${Date.now()}`, symbol: form.symbol || 'XAUUSD', direction: (form.direction as any) || 'SELL', setupType: form.setupType || 'Continuation', status: form.status || 'Watching', weekly: form.weekly || state?.engine_gate?.summary?.weekly_trajectory || '', daily: form.daily || state?.engine_gate?.summary?.daily_trajectory || '', objective: form.objective || state?.engine_gate?.summary?.daily_objective || '', waitingFor: form.waitingFor || '15m sweep + CHOCH/reclaim confirmation', invalidationPrice: form.invalidationPrice || '', riskMode: form.riskMode || 'Feeler Risk 0.5%', notes: form.notes || '', createdAt: new Date().toISOString() };
    setIdeas([idea, ...ideas]); setSelectedIdea(idea.id); setForm({ symbol: idea.symbol, direction: idea.direction, setupType: idea.setupType, status: 'Watching', riskMode: idea.riskMode });
  };
  const updateIdea = (id: string, patch: Partial<TradeIdea>) => setIdeas(ideas.map((x: TradeIdea) => x.id === id ? { ...x, ...patch } : x));
  const removeIdea = (id: string) => setIdeas(ideas.filter((x: TradeIdea) => x.id !== id));
  const addQuickIdeaFromBrain = async () => {
    const participation = brain?.participation || {};
    const daily = brain?.daily || {};
    const direction = participation.suggested_direction && participation.suggested_direction !== 'NONE' ? participation.suggested_direction : (form.direction || 'BUY');
    const setupType = participation.participation_status === 'EXECUTE_ALLOWED' ? 'Quick Ready Trade' : 'Quick Trade Idea';
    const localIdea: TradeIdea = {
      id: `idea_${Date.now()}`,
      symbol: currentSymbol || form.symbol || 'XAUUSD',
      direction: direction === 'SELL' ? 'SELL' : 'BUY',
      setupType,
      status: participation.participation_status || 'Watching',
      weekly: brain?.weekly?.weekly_state || '',
      daily: `${daily.daily_bias || 'WATCHING'} / ${daily.context || ''}`,
      objective: (daily.objective_ladder || []).join(' → ') || form.objective || '',
      waitingFor: participation.next_required_step || 'Wait for lifecycle confirmation',
      invalidationPrice: form.invalidationPrice || '',
      riskMode: participation.risk_permission || form.riskMode || 'Feeler Risk 0.5%',
      notes: participation.machine_message || '',
      createdAt: new Date().toISOString(),
    };
    setIdeas([localIdea, ...ideas]);
    setSelectedIdea(localIdea.id);
    try {
      await fetch(`${BASE_URL}/api/v1/trade-ideas/quick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: localIdea.symbol,
          direction: localIdea.direction,
          setup_type: setupType,
          lifecycle_state: localIdea.status,
          risk_percent: localIdea.riskMode.includes('1') ? 1 : localIdea.riskMode.includes('0.25') ? 0.25 : 0.5,
          sl_price: localIdea.invalidationPrice,
          objective: localIdea.objective,
          waiting_for: localIdea.waitingFor,
          notes: localIdea.notes,
          source: 'electron_quick_idea'
        })
      });
    } catch {
      // Local idea still saved. Backend will get over itself on the next save.
    }
  };
  return <div className={`card tradeIdeaCard ${large ? 'largeCard' : ''}`}><div className="cardHeader tight"><div><h3>Live Trade Idea</h3><p>Idea matures across sessions before execution.</p></div><CircleDot className="blueIcon" size={20}/></div><div className="ideaForm"><select value={form.symbol || 'XAUUSD'} onChange={e => setForm({ ...form, symbol: e.target.value })}><option>XAUUSD</option><option>US500.cash</option></select><select value={form.direction || 'SELL'} onChange={e => setForm({ ...form, direction: e.target.value as any })}><option>SELL</option><option>BUY</option></select><select value={form.setupType || 'Continuation'} onChange={e => setForm({ ...form, setupType: e.target.value })}><option>A+ Reversal</option><option>A Reversal</option><option>Continuation</option><option>Speculative Probe</option></select><select value={form.riskMode || 'Feeler Risk 0.5%'} onChange={e => setForm({ ...form, riskMode: e.target.value })}><option>Feeler Risk 0.25%</option><option>Feeler Risk 0.5%</option><option>Full Risk 1%</option><option>Additional Risk 0.5%</option></select><input placeholder="Invalidation / SL price" value={form.invalidationPrice || ''} onChange={e => setForm({ ...form, invalidationPrice: e.target.value })}/><input placeholder="Objective" value={form.objective || ''} onChange={e => setForm({ ...form, objective: e.target.value })}/><textarea placeholder="Waiting for..." value={form.waitingFor || ''} onChange={e => setForm({ ...form, waitingFor: e.target.value })}/><textarea placeholder="Notes / session expectation" value={form.notes || ''} onChange={e => setForm({ ...form, notes: e.target.value })}/><button className="primaryBtn" onClick={addIdea}>Add Trade Idea</button><button onClick={addQuickIdeaFromBrain}>Quick Idea From Lifecycle Brain</button></div><div className="ideaList">{ideas.map((idea: TradeIdea) => <div key={idea.id} className={`ideaItem ${selectedIdea?.id === idea.id ? 'picked' : ''}`} onClick={() => setSelectedIdea(idea.id)}><div><b>{idea.symbol} {idea.direction}</b><span>{idea.setupType} • <select value={idea.status} onChange={(e) => updateIdea(idea.id, { status: e.target.value })} onClick={e=>e.stopPropagation()}><option>Watching</option><option>Waiting for Sweep</option><option>Confirmation Forming</option><option>Ready</option><option>Executed</option><option>Invalidated</option><option>Archived</option></select></span></div><em>{idea.objective || 'Objective not set'}</em><button className="tinyDelete" onClick={(e)=>{e.stopPropagation(); removeIdea(idea.id)}}>×</button></div>)}{ideas.length === 0 && <p className="emptyText">No trade ideas yet. Narrative first, button-smashing later.</p>}</div></div>;
}

function GraphSettings({ visuals, setVisuals, updateVisual, localSave, saveMapsToBackend, loadMapsFromBackend }: any) {
  const [activeLayer, setActiveLayer] = useState<LayerKey>('weekly');
  const v: VisualLayer = visuals[activeLayer];
  return <div className="card largeCard mapSettingsPage displaySettingsPage">
    <div className="cardHeader tight"><div><h3>Display Settings</h3><p>Visual controls only. Mapping stores structure; analytics derives sweeps, P2, OBs, mitigation and objectives later.</p></div><Settings className="goldIcon" size={22}/></div>
    <div className="structuralDoctrineCard"><b>Structure-only doctrine</b><span>Use Map Studio / Case Manager to save ranges, BOS up/down, active range changes and parent-child range links. Do not manually label sweep, phase, OB, profile or objective here. Apparently restraint is now a feature.</span></div>
    <div className="layerTabs">{LAYERS.map(l => <button className={activeLayer===l ? 'active' : ''} onClick={() => setActiveLayer(l)} key={l}>{l.toUpperCase()} DISPLAY</button>)}</div>

    <div className="settingsSectionTitle">Range display references</div>
    <div className="settingsGrid">
      <label>Display Range Low<input value={v.rangeLow} onChange={e=>updateVisual(activeLayer,{rangeLow:e.target.value})}/></label>
      <label>Display Range High<input value={v.rangeHigh} onChange={e=>updateVisual(activeLayer,{rangeHigh:e.target.value})}/></label>
      <label>Tick Interval<select value={String(v.tickStep)} onChange={e=>updateVisual(activeLayer,{tickStep:Number(e.target.value)})}><option value="50">$50</option><option value="100">$100</option><option value="200">$200</option><option value="500">$500</option></select></label>
      <label className="settingsCheck"><input type="checkbox" checked={!!v.useLiveCurrent} onChange={e=>updateVisual(activeLayer,{useLiveCurrent:e.target.checked})}/> Current marker uses live price</label>
      <label>Projection Price<input value={v.projectionPrice || ''} onChange={e=>updateVisual(activeLayer,{projectionPrice:e.target.value})} placeholder="optional visual guide" /></label>
    </div>

    <div className="settingsSectionTitle">Visibility notes</div>
    <div className="settingsGrid">
      <label>Current Zone<select value={v.currentZone} onChange={e=>updateVisual(activeLayer,{currentZone:e.target.value})}>{ZONES.map(z=><option key={z}>{z}</option>)}</select></label>
      <label>Objective Zone<select value={v.objectiveZone} onChange={e=>updateVisual(activeLayer,{objectiveZone:e.target.value})}>{ZONES.map(z=><option key={z}>{z}</option>)}</select></label>
      <label>Broken External Ref<select value={v.brokenExternal || 'NONE'} onChange={e=>updateVisual(activeLayer,{brokenExternal:e.target.value as any})}><option value="NONE">Hide</option><option value="EXT_H">Show broken high guide</option><option value="EXT_L">Show broken low guide</option></select></label>
      <label>Broken Ref Price<input value={v.brokenExternalPrice || ''} onChange={e=>updateVisual(activeLayer,{brokenExternalPrice:e.target.value})} placeholder="visual guide only"/></label>
    </div>

    <div className="settingsActionRow"><button className="primaryBtn" onClick={() => { setVisuals(visuals); localSave?.(); }}>Save Local Display Draft</button><button onClick={saveMapsToBackend}>Save Display To Backend</button><button onClick={loadMapsFromBackend}>Load Display From Backend</button><span>These settings are visual helpers. Structural truth is saved through range/event mapping, because the chart is not a confession booth.</span></div>
    <XYTrajectoryPanel title={`${activeLayer.toUpperCase()} Display Preview`} layerKey={activeLayer} visual={v} updateVisual={updateVisual} accent={activeLayer==='weekly'?'gold':activeLayer==='daily'?'blue':'cyan'} livePrice={null}/>
    <div className="jsonPreview"><b>Display payload only</b><pre>{JSON.stringify({ layer: activeLayer, rangeLow: v.rangeLow, rangeHigh: v.rangeHigh, tickStep: v.tickStep, currentZone: v.currentZone, objectiveZone: v.objectiveZone }, null, 2)}</pre></div>
  </div>;
}

function narrativeOptions(){return ['Bullish From External Low','Bullish From Deep Discount','Bullish From Discount','Bearish From External High','Bearish From Deep Premium','Bearish From Premium','Manual / Custom'].map(x=><option key={x}>{x}</option>)}
function applyNarrative(narrative: string, v: VisualLayer): Partial<VisualLayer> {
  const patch: Partial<VisualLayer> = { narrative };
  if (narrative.toLowerCase().startsWith('bullish')) patch.mapBias = 'bullish';
  if (narrative.toLowerCase().startsWith('bearish')) patch.mapBias = 'bearish';
  if (narrative.includes('External Low')) patch.currentZone = v.currentZone || 'D';
  if (narrative.includes('External High')) patch.currentZone = v.currentZone || 'P';
  if (narrative.includes('Deep Premium')) patch.objectiveZone = v.objectiveZone || 'DD';
  if (narrative.includes('Deep Discount')) patch.objectiveZone = v.objectiveZone || 'DP';
  if (narrative === 'Manual / Custom') patch.mapBias = 'manual';
  return patch;
}

function mitOptions(){return ['Fresh','M1','M2','Mitigated','Failed'].map(x=><option key={x}>{x}</option>)}
function MitigationLevelEditor({ value, onChange }: { value?: MitigationLevels; onChange: (v: MitigationLevels) => void }) {
  const levels = normalizeMitigationLevels(value);
  const setCell = (zone: 'discount'|'fair_price'|'premium', level: 'm1'|'m2'|'m3', key: 'price'|'status', val: string) => {
    onChange({ ...levels, [zone]: { ...levels[zone], [level]: { ...levels[zone][level], [key]: val } } });
  };
  const zones: Array<['discount'|'fair_price'|'premium', string]> = [['discount','Discount'], ['fair_price','Fair Price'], ['premium','Premium']];
  return <div className="mitigationMatrix">
    {zones.map(([zone,label]) => <div className="mitigationZone" key={zone}><h4>{label}</h4>{(['m1','m2','m3'] as const).map(level => <div className="mLevelRow" key={`${zone}_${level}`}><b>{level.toUpperCase()}</b><input placeholder="price" value={levels[zone][level].price} onChange={e=>setCell(zone, level, 'price', e.target.value)} /><select value={levels[zone][level].status} onChange={e=>setCell(zone, level, 'status', e.target.value)}>{['WAITING','FRESH','MITIGATED','HELD','FAILED','USED'].map(x=><option key={x}>{x}</option>)}</select></div>)}</div>)}
  </div>;
}
function MitigationSequenceEditor({ value, onChange }: { value?: string[]; onChange: (v: string[]) => void }) {
  const seq = Array.isArray(value) ? value : [];
  const set = (i:number, val:string) => { const next = [...seq]; next[i] = val; onChange(next.filter((_,idx)=>idx < 5)); };
  return <div className="sequenceRow">{[0,1,2,3,4].map(i=><label key={i}>Step {i+1}<select value={seq[i] || ''} onChange={e=>set(i,e.target.value)}><option value="">-</option>{[...MITIGATION_TARGETS,'NEW_BOS_UP','NEW_BOS_DOWN','PROFILE_FLIP','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label>)}</div>;
}


function LiveTradePanel({ data, idea, large }: any) {
  const raw = data?.raw_status || data || {};
  const open = Number(data?.position_count ?? raw.open_positions ?? 0);
  const dir = raw.direction || data?.direction || idea?.direction || '-';
  const lifecycle = data?.lifecycle_state || data?.derived_state?.current_lifecycle_state || raw.lifecycle_state || data?.status || 'NONE';
  const closeLocked = truthy(data?.close_lock_active ?? data?.is_close_locked ?? data?.derived_state?.is_close_locked ?? raw.close_lock_active);
  const dailyRangePosition = data?.daily_range_position_percent ?? data?.derived_state?.daily_range_position_percent ?? data?.retracement_percent ?? data?.daily_retracement_percent ?? raw.retracement_percent;
  const unlockAtRaw = data?.close_lock_unlock_at ?? data?.derived_state?.close_lock_unlock_at ?? raw.close_lock_unlock_at;
  const biasText = String(raw.direction || data?.direction || data?.derived_state?.direction || idea?.direction || '').toUpperCase();
  const unlockAt = unlockAtRaw != null ? `${Number(unlockAtRaw).toFixed(0)}% ${biasText.includes('BEAR') || biasText === 'SELL' ? 'or higher' : 'or lower'}` : 'Daily High/Low required';
  const totalRisk = data?.total_risk_percent ?? data?.current_trade_risk_pct ?? raw.total_risk_percent;
  const events = data?.events || data?.recent_events || data?.trade_events || [];
  return <div className={`card ${large?'largeCard':''}`}>
    <div className="cardHeader tight"><div><h3>Live Trade</h3><p>Linked idea: {idea?.setupType || 'none'}</p></div><Zap className="goldIcon" size={20}/></div>
    <div className="metricGrid">
      <Metric label="Status" value={raw.status || data?.status || 'NONE'} />
      <Metric label="Lifecycle" value={lifecycle} color="#00ffd0" />
      <Metric label="Direction" value={dir} color={String(dir).toUpperCase()==='BUY' ? '#42e68a' : '#ff4d67'} />
      <Metric label="Positions" value={open} />
      <Metric label="Current R" value={raw.current_r ?? data?.current_r ?? '-'} color="#ffbf2f" />
      <Metric label="Total Idea Risk" value={fmtPct(totalRisk)} color="#ffbf2f" />
      <Metric label="Close Lock" value={closeLocked ? `LOCKED • ${unlockAt}` : 'Inactive'} color={closeLocked ? '#ff4d67' : '#7b8794'} />
      <Metric label="Daily Range Position" value={fmtPctOrDash(dailyRangePosition)} color={closeLocked ? '#ff4d67' : '#dbeafe'} />
    </div>
    <div className="tpRow"><Check label="TP1" active={truthy(raw.tp1_confirmed || data?.two_r_hit)} /><Check label="TP2" active={truthy(raw.tp2_confirmed)} /><Check label="Runner SL" active={truthy(raw.runner_sl_moved)} /></div>
    {large && <EventStream events={events} />}
  </div>;
}
function EventStream({ events }: any) {
  const rows = Array.isArray(events) ? events.slice(-8).reverse() : [];
  return <div className="eventStream"><b>Forensic Event Stream</b>{rows.length === 0 && <p>No backend event stream yet.</p>}{rows.map((e:any,i:number)=><div className="eventRow" key={e.id || e.idempotency_key || i}><span>{String(e.timestamp_utc || e.created_at || '').slice(11,19) || '-'}</span><b>{e.event_type || e.type || '-'}</b><em>{e.event_reason || e.notes || ''}</em></div>)}</div>;
}
function DataCollectionPage() {
  const [form, setForm] = useState<any>({
    symbol: 'XAUUSD', scenario_name: 'Manual lifecycle stress test', expected_status: 'FORMING', timeframe: 'DAILY',
    range_high: '', range_low: '', current_price: '', prev_high: '', prev_low: '', bos_direction: 'WAITING', bos_level: '', new_ext_locked: 'NO', phase_type: 'CHOCH',
    reclaim_status: 'WAITING', retrace_depth_pct: '', reclaim_depth_pct: '', range_status: 'ACTIVE', order_flow: 'PRO_TREND', profile: 'SND_DEEP_RETRACE',
    inducement: 'NO', inducement_direction: 'BULLISH', inducement_high: '', inducement_low: '', inducement_result: 'WAITING',
    weekly_bias: 'BULLISH', weekly_state: 'WEEKLY_CONTEXT_ACTIVE', daily_bias: 'BULLISH', daily_objective: 'FAIR_PRICE_M1',
    intraday_state: 'INTRADAY_P1_BOS_CONFIRMED', favourable_trade: 'P2_CONTINUATION', retest_status: 'RETEST_PENDING', micro_confirmation: 'WAITING',
    mitigation_sequence: ['', '', '', '', ''], final_outcome: '', notes: ''
  });
  const [result, setResult] = useState<any>(null);
  const update = (k:string, v:any) => setForm((x:any)=>({ ...x, [k]: v }));
  const updateSeq = (idx:number, val:string) => setForm((x:any)=>{ const seq=[...(x.mitigation_sequence||[])]; seq[idx]=val; return {...x, mitigation_sequence: seq}; });
  const payload = () => ({
    symbol: form.symbol,
    scenario_name: form.scenario_name,
    expected_status: form.expected_status,
    timeframe: form.timeframe,
    range_high: form.range_high, range_low: form.range_low, current_price: form.current_price,
    prev_high: form.prev_high, prev_low: form.prev_low,
    bos_direction: form.bos_direction, bos_level: form.bos_level, new_ext_locked: form.new_ext_locked,
    phase_type: form.phase_type, reclaim_status: form.reclaim_status, retrace_depth_pct: form.retrace_depth_pct, reclaim_depth_pct: form.reclaim_depth_pct,
    range_status: form.range_status, order_flow: form.order_flow,
    inducement: form.inducement === 'YES', inducement_direction: form.inducement_direction, inducement_high: form.inducement_high, inducement_low: form.inducement_low, inducement_result: form.inducement_result,
    mitigation_sequence: (form.mitigation_sequence || []).filter(Boolean), final_outcome: form.final_outcome,
    weekly: { weekly_bias: form.weekly_bias, weekly_state: form.weekly_state },
    daily: { daily_bias: form.daily_bias, daily_profile: form.profile, daily_objective: form.daily_objective, bos_direction: form.bos_direction, phase_type: form.phase_type, reclaim_status: form.reclaim_status, range_status: form.range_status, order_flow: form.order_flow, inducement: form.inducement === 'YES', mitigation_sequence: (form.mitigation_sequence || []).filter(Boolean) },
    intraday: { intraday_state: form.intraday_state, favourable_trade: form.favourable_trade, retest_status: form.retest_status },
    micro: { confirmation: form.micro_confirmation },
    notes: form.notes,
  });
  const run = async () => { const r = await fetch(`${BASE_URL}/api/v1/lifecycle/scenario/calculate`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload())}).then(x=>x.json()); setResult(r); };
  return <div className="card largeCard"><div className="cardHeader tight"><div><h3>Lifecycle Scenario Calculator</h3><p>Clean scenario form: range → BOS/reclaim → profile → inducement → mitigation path → machine output. No JSON cave drawings.</p></div><Database className="blueIcon" size={22}/></div>
    <div className="dataSteps"><div><b>1</b><span>Range context</span></div><div><b>2</b><span>BOS/reclaim</span></div><div><b>3</b><span>Profile + inducement</span></div><div><b>4</b><span>Mitigation path</span></div><div><b>5</b><span>Machine hint</span></div></div>
    <div className="formSection"><h4>Context</h4><div className="scenarioForm"><label>Scenario Name<input value={form.scenario_name} onChange={e=>update('scenario_name', e.target.value)} /></label><label>Expected Status<select value={form.expected_status} onChange={e=>update('expected_status', e.target.value)}>{['NO_TRADE','WATCHING','FORMING','READY','EXECUTE_ALLOWED','ADD_RISK_READY','BLOCKED','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label><label>Timeframe<select value={form.timeframe} onChange={e=>update('timeframe',e.target.value)}>{['MACRO','WEEKLY','DAILY','INTRADAY'].map(x=><option key={x}>{x}</option>)}</select></label></div></div>
    <div className="formSection"><h4>Range + structure</h4><div className="scenarioForm"><label>High / EXT_H<input value={form.range_high} onChange={e=>update('range_high',e.target.value)} /></label><label>Low / EXT_L<input value={form.range_low} onChange={e=>update('range_low',e.target.value)} /></label><label>Current Price<input value={form.current_price} onChange={e=>update('current_price',e.target.value)} /></label><label>Prev High<input value={form.prev_high} onChange={e=>update('prev_high',e.target.value)} /></label><label>Prev Low<input value={form.prev_low} onChange={e=>update('prev_low',e.target.value)} /></label><label>BOS Direction<select value={form.bos_direction} onChange={e=>update('bos_direction',e.target.value)}>{['WAITING','UP','DOWN'].map(x=><option key={x}>{x}</option>)}</select></label><label>BOS Level<input value={form.bos_level} onChange={e=>update('bos_level',e.target.value)} /></label><label>New EXT Locked<select value={form.new_ext_locked} onChange={e=>update('new_ext_locked',e.target.value)}>{['NO','YES'].map(x=><option key={x}>{x}</option>)}</select></label></div></div>
    <div className="formSection"><h4>Phase, reclaim and profile</h4><div className="scenarioForm"><label>Phase Type<select value={form.phase_type} onChange={e=>update('phase_type',e.target.value)}>{['CHOCH','P1','P2','P3','P3_FAIL','NEW_P1','PROFILE_FLIP'].map(x=><option key={x}>{x}</option>)}</select></label><label>Reclaim Status<select value={form.reclaim_status} onChange={e=>update('reclaim_status',e.target.value)}>{['WAITING','CONFIRMED','FAILED','ABANDONED','LATER_RECLAIMED'].map(x=><option key={x}>{x}</option>)}</select></label><label>Retrace Depth %<input value={form.retrace_depth_pct} onChange={e=>update('retrace_depth_pct',e.target.value)} /></label><label>Reclaim Depth %<input value={form.reclaim_depth_pct} onChange={e=>update('reclaim_depth_pct',e.target.value)} /></label><label>Range Status<select value={form.range_status} onChange={e=>update('range_status',e.target.value)}>{['ACTIVE','ABANDONED','RETEST_PENDING','RETESTED','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label><label>Order Flow<select value={form.order_flow} onChange={e=>update('order_flow',e.target.value)}>{['PRO_TREND','CORRECTIVE','COUNTER_TREND','WAITING'].map(x=><option key={x}>{x}</option>)}</select></label><label>Profile<select value={form.profile} onChange={e=>update('profile', e.target.value)}>{[...DAILY_PROFILES,'NO_RETRACE','COMPRESSION','PROFILE_FLIP'].map(x=><option key={x}>{x}</option>)}</select></label></div></div>
    <div className="formSection"><h4>Inducement</h4><div className="scenarioForm"><label>Inducement<select value={form.inducement} onChange={e=>update('inducement',e.target.value)}>{['NO','YES'].map(x=><option key={x}>{x}</option>)}</select></label><label>Direction<select value={form.inducement_direction} onChange={e=>update('inducement_direction',e.target.value)}>{['BULLISH','BEARISH'].map(x=><option key={x}>{x}</option>)}</select></label><label>Inducement High<input value={form.inducement_high} onChange={e=>update('inducement_high',e.target.value)} /></label><label>Inducement Low<input value={form.inducement_low} onChange={e=>update('inducement_low',e.target.value)} /></label><label>Result<select value={form.inducement_result} onChange={e=>update('inducement_result',e.target.value)}>{['WAITING','HELD','FAILED'].map(x=><option key={x}>{x}</option>)}</select></label></div></div>
    <div className="formSection"><h4>Mitigation sequence</h4><div className="sequenceRow">{[0,1,2,3,4].map(i=><label key={i}>Step {i+1}<select value={form.mitigation_sequence?.[i] || ''} onChange={e=>updateSeq(i,e.target.value)}><option value="">-</option>{[...MITIGATION_TARGETS,'NEW_BOS_UP','NEW_BOS_DOWN','PROFILE_FLIP','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label>)}</div></div>
    <div className="formSection"><h4>Bias + execution context</h4><div className="scenarioForm"><label>Weekly Bias<select value={form.weekly_bias} onChange={e=>update('weekly_bias', e.target.value)}>{['BULLISH','BEARISH','WATCHING'].map(x=><option key={x}>{x}</option>)}</select></label><label>Weekly State<input value={form.weekly_state} onChange={e=>update('weekly_state', e.target.value)} /></label><label>Daily Bias<select value={form.daily_bias} onChange={e=>update('daily_bias', e.target.value)}>{['BULLISH','BEARISH','WATCHING'].map(x=><option key={x}>{x}</option>)}</select></label><label>Daily Objective<select value={form.daily_objective} onChange={e=>update('daily_objective', e.target.value)}>{OBJECTIVE_TYPES.map(x=><option key={x}>{x}</option>)}</select></label><label>Intraday State<select value={form.intraday_state} onChange={e=>update('intraday_state', e.target.value)}>{['INTRADAY_PRE_CHOCH','INTRADAY_CHOCH_CONFIRMED','INTRADAY_P1_BOS_CONFIRMED','INTRADAY_P2_RETEST_PENDING','INTRADAY_P2_RETEST_ACTIVE','INTRADAY_P2_RETEST_COMPLETE','INTRADAY_ADD_RISK_READY','INTRADAY_INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label><label>Favourable Trade<select value={form.favourable_trade} onChange={e=>update('favourable_trade', e.target.value)}>{['NO_FAVOURABLE_TRADE','P1_CONTINUATION','P2_CONTINUATION','P3_FAILURE_REVERSAL','NEW_P1_PROFILE_FLIP'].map(x=><option key={x}>{x}</option>)}</select></label><label>Retest Status<select value={form.retest_status} onChange={e=>update('retest_status', e.target.value)}>{['WAITING','RETEST_PENDING','RETEST_ACTIVE','RETEST_COMPLETE','RETEST_FAILED'].map(x=><option key={x}>{x}</option>)}</select></label><label>Micro Confirmation<select value={form.micro_confirmation} onChange={e=>update('micro_confirmation', e.target.value)}>{['WAITING','CONFIRMED','REF_CANDLE_CONFIRMED','INVALID'].map(x=><option key={x}>{x}</option>)}</select></label><label>Final Outcome<input value={form.final_outcome} onChange={e=>update('final_outcome',e.target.value)} placeholder="what market actually did" /></label><label>Notes<textarea value={form.notes} onChange={e=>update('notes', e.target.value)} /></label></div></div>
    <button className="primaryBtn solo" onClick={run}>Run Scenario Calculator</button>
    <div className="scenarioResult"><b>Result</b>{!result && <p className="emptyText">Run a scenario to see the lifecycle hint.</p>}{result && <><div className="resultBadge">{result.participation?.participation_status || 'UNKNOWN'}</div><p className="machineText"><b>Machine:</b> {result.participation?.machine_message || result.participation?.reason || '-'}</p><InfoLine label="Execution Allowed" value={result.participation?.execution_allowed ? 'YES' : 'NO'} /><InfoLine label="Next Step" value={result.participation?.next_required_step || '-'} /></>}</div>
  </div>;
}

function HistoricalLifecycleBuilder({ symbol, visuals }: { symbol: string; visuals: VisualStore }) {
  const today = new Date().toISOString().slice(0,10);
  const [form, setForm] = useState<any>({
    symbol,
    friendly_name: `${symbol} | Historical lifecycle`,
    mode: 'HTF_ONLY',
    date_start: today,
    date_end: '',
    weekly_start: today,
    weekly_end: '',
    daily_start: today,
    daily_end: '',
    intraday_start: today,
    intraday_end: today,
    outcome_label: '',
    fair_price_reached: false,
    premium_reached: false,
    discount_reached: false,
    external_reached: false,
    notes: '',
  });
  const [result, setResult] = useState<any>(null);
  const [resolved, setResolved] = useState<any>(null);
  const update = (k:string,v:any)=>setForm((x:any)=>({...x,[k]:v}));
  useEffect(()=>setForm((x:any)=>({...x,symbol})),[symbol]);
  const layerPayload = (layer: LayerKey, start: string, end: string) => ({
    date_start: start,
    date_end: end,
    visual: visuals[layer],
    state: journalReadyMap(layer, visuals[layer]),
    meta: journalReadyMap(layer, visuals[layer]),
    range_low: visuals[layer].rangeLow,
    range_high: visuals[layer].rangeHigh,
  });
  const payload = () => ({
    symbol: form.symbol,
    friendly_name: form.friendly_name,
    mode: form.mode,
    date_start: form.date_start,
    date_end: form.date_end,
    weekly: layerPayload('weekly', form.weekly_start || form.date_start, form.weekly_end || form.date_end),
    daily: layerPayload('daily', form.daily_start || form.date_start, form.daily_end || form.date_end),
    intraday: form.mode === 'FULL' ? layerPayload('intraday', form.intraday_start || form.date_start, form.intraday_end || form.intraday_start || form.date_start) : {},
    outcome: {
      outcome_label: form.outcome_label,
      fair_price_reached: !!form.fair_price_reached,
      premium_reached: !!form.premium_reached,
      discount_reached: !!form.discount_reached,
      external_reached: !!form.external_reached,
    },
    notes: form.notes,
    updated_from_device: 'electron_historical_builder',
  });
  const save = async()=>{
    const r = await fetch(`${BASE_URL}/api/v1/historical/lifecycle-bundle`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())}).then(x=>x.json());
    setResult(r);
  };
  const resolve = async()=>{
    const d = form.intraday_start || form.daily_start || form.date_start;
    const r = await fetch(`${BASE_URL}/api/v1/historical/resolve-context?symbol=${encodeURIComponent(form.symbol)}&sample_date=${encodeURIComponent(d)}`).then(x=>x.json());
    setResolved(r);
  };
  return <div className="card largeCard journalClean">
    <div className="cardHeader tight"><div><h3>Historical Lifecycle Builder</h3><p>Save one linked lifecycle by date. Weekly/Daily first, Intraday only for recent/current regimes. No ID memorisation, because we are not database monks.</p></div><BookOpen className="goldIcon" size={22}/></div>
    <div className="dataSteps"><div><b>1</b><span>Pick symbol + period</span></div><div><b>2</b><span>Choose HTF or FULL</span></div><div><b>3</b><span>Use current maps</span></div><div><b>4</b><span>Save bundle</span></div><div><b>5</b><span>Future intraday auto-links by date</span></div></div>
    <div className="scenarioForm">
      <label>Lifecycle Label<input value={form.friendly_name} onChange={e=>update('friendly_name', e.target.value)} /></label>
      <label>Symbol<select value={form.symbol} onChange={e=>update('symbol', e.target.value)}>{SYMBOLS.map(x=><option key={x}>{x}</option>)}</select></label>
      <label>Mode<select value={form.mode} onChange={e=>update('mode', e.target.value)}><option value="HTF_ONLY">HTF ONLY — Weekly + Daily</option><option value="FULL">FULL — Weekly + Daily + Intraday</option></select></label>
      <label>Bundle Start<input type="date" value={form.date_start} onChange={e=>update('date_start', e.target.value)} /></label>
      <label>Bundle End<input type="date" value={form.date_end} onChange={e=>update('date_end', e.target.value)} /></label>
      <label>Weekly Start<input type="date" value={form.weekly_start} onChange={e=>update('weekly_start', e.target.value)} /></label>
      <label>Weekly End<input type="date" value={form.weekly_end} onChange={e=>update('weekly_end', e.target.value)} /></label>
      <label>Daily Start<input type="date" value={form.daily_start} onChange={e=>update('daily_start', e.target.value)} /></label>
      <label>Daily End<input type="date" value={form.daily_end} onChange={e=>update('daily_end', e.target.value)} /></label>
      {form.mode === 'FULL' && <><label>Intraday Date<input type="date" value={form.intraday_start} onChange={e=>update('intraday_start', e.target.value)} /></label><label>Intraday End<input type="date" value={form.intraday_end} onChange={e=>update('intraday_end', e.target.value)} /></label></>}
      <label>Outcome Label<input value={form.outcome_label} onChange={e=>update('outcome_label', e.target.value)} placeholder="Reached Fair Price / Profile Flip / Failed at Discount" /></label>
      <label className="checkboxLine"><input type="checkbox" checked={form.fair_price_reached} onChange={e=>update('fair_price_reached', e.target.checked)} /> Fair price reached</label>
      <label className="checkboxLine"><input type="checkbox" checked={form.premium_reached} onChange={e=>update('premium_reached', e.target.checked)} /> Premium reached</label>
      <label className="checkboxLine"><input type="checkbox" checked={form.discount_reached} onChange={e=>update('discount_reached', e.target.checked)} /> Discount reached</label>
      <label className="checkboxLine"><input type="checkbox" checked={form.external_reached} onChange={e=>update('external_reached', e.target.checked)} /> External reached</label>
      <label className="wide">Notes<textarea value={form.notes} onChange={e=>update('notes', e.target.value)} placeholder="What did the range do? What did the machine need to remember?" /></label>
    </div>
    <div className="buttonRow"><button className="primaryBtn" onClick={save}>Save Historical Lifecycle Bundle</button><button onClick={resolve}>Resolve Parent Context By Date</button></div>
    <div className="splitGrid journalSplit">
      <div className="miniPanel"><h4>Current Map Snapshot Used</h4><InfoLine label="Weekly" value={`${visuals.weekly.rangeLow || '-'} → ${visuals.weekly.rangeHigh || '-'}`} /><InfoLine label="Daily" value={`${visuals.daily.rangeLow || '-'} → ${visuals.daily.rangeHigh || '-'}`} /><InfoLine label="Intraday" value={form.mode === 'FULL' ? `${visuals.intraday.rangeLow || '-'} → ${visuals.intraday.rangeHigh || '-'}` : 'Skipped in HTF ONLY'} /></div>
      <div className="miniPanel"><h4>Backend Result</h4>{!result && !resolved && <p className="emptyText">Save or resolve context to see backend response.</p>}{result && <><InfoLine label="Saved" value={result.ok ? 'YES' : 'NO'} /><InfoLine label="Bundle ID" value={result.id || '-'} /><InfoLine label="Ranges" value={result.context_ranges?.length ?? 0} /><p className="machineText">{result.error || result.friendly_name || result.message || ''}</p></>}{resolved && <><InfoLine label="Resolve Date" value={resolved.sample_date || '-'} /><InfoLine label="Weekly Match" value={resolved.matched?.weekly?.friendly_name || 'None'} /><InfoLine label="Daily Match" value={resolved.matched?.daily?.friendly_name || 'None'} /><InfoLine label="Intraday Match" value={resolved.matched?.intraday?.friendly_name || 'None'} /></>}</div>
    </div>
  </div>;
}

function JournalPreview({ rows }: any) { return <div className="card"><div className="cardHeader tight"><div><h3>Journal Preview</h3><p>Recent SQL trades</p></div><BookOpen className="blueIcon" size={20}/></div>{rows.length === 0 && <p className="emptyText">No SQL trades logged yet.</p>}{rows.slice(0,5).map((r: any, i: number) => <div className="journalItem" key={i}><b>{r.symbol || 'XAUUSD'} {r.direction || ''}</b><span>{r.status || 'OPENED'} • {r.risk_percent ?? '-'}%</span></div>)}</div>; }
function JournalPage({ rows, summary, structured, detailed }: any) {
  const metrics = summary?.metrics || {};
  const counts = summary?.counts || {};
  const lifecycle = structured?.lifecycle || [];
  const ideas = structured?.ideas || [];
  const maps = structured?.maps || [];
  const scenarios = structured?.scenario_tests || [];
  const richTrades = detailed?.trades || [];
  const [tab, setTab] = useState<'trades'|'ideas'|'scenarios'|'lifecycle'|'maps'>('trades');
  const [selected, setSelected] = useState<any>(richTrades[0] || null);
  const [edit, setEdit] = useState<any>(richTrades[0] || {});
  const [saveState, setSaveState] = useState('');
  useEffect(()=>{ if (!selected && richTrades[0]) { setSelected(richTrades[0]); setEdit(richTrades[0]); } }, [richTrades.length]);
  const pick = (r:any) => { setSelected(r); setEdit({...r}); setSaveState(''); };
  const setField = (k:string, v:any) => setEdit((x:any)=>({ ...x, [k]: v }));
  const saveTrade = async () => {
    if (!edit?.id && !selected?.id) return;
    setSaveState('Saving...');
    const id = edit.id || selected.id;
    const payload = { id, symbol: edit.symbol || selected.symbol || 'XAUUSD', fields: edit };
    const r = await fetch(`${BASE_URL}/api/v1/journal/trade/update`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(x=>x.json()).catch(e=>({ok:false,error:e.message}));
    setSaveState(r.ok ? 'Saved to SQL memory' : `Save failed: ${r.error || 'unknown'}`);
  };
  return <div className="card largeCard journalClean"><div className="cardHeader tight"><div><h3>Journal Command Centre</h3><p>Clean trade memory, lifecycle snapshots and scenario stress tests. Less JSON swamp, more usable truth.</p></div><BookOpen className="blueIcon" size={22}/></div>
    <div className="kpiGrid"><Kpi label="Trades" value={metrics.total_trades ?? rows.length ?? 0}/><Kpi label="Trade Memory" value={counts.trade_memory_records ?? richTrades.length ?? 0}/><Kpi label="Maps" value={counts.map_states ?? maps.length ?? 0}/><Kpi label="Lifecycle" value={counts.lifecycle_snapshots ?? lifecycle.length ?? 0}/><Kpi label="Data Score" value={`${metrics.data_readiness_score ?? 0}%`}/></div>
    <div className="journalTabs">
      {[
        ['trades','Trade History'],['ideas','Idea History'],['scenarios','Scenario Tests'],['lifecycle','Lifecycle'],['maps','Map Saves']
      ].map(([k,l])=><button key={k} className={tab===k?'active':''} onClick={()=>setTab(k as any)}>{l}</button>)}
    </div>
    {tab === 'trades' && <div className="splitGrid journalSplit"><div className="miniPanel"><h4>Trade History</h4>{richTrades.length===0 && <p className="emptyText">No rich trade memory yet. Execute or create quick ideas after maps/lifecycle are saved.</p>}{richTrades.slice(0,30).map((r:any)=><button className={`tradeMemoryRow ${selected?.id===r.id?'picked':''}`} key={String(r.id)} onClick={()=>pick(r)}><b>{String(r.created_at || '').slice(0,16)} • {r.symbol} {r.direction || ''}</b><span>{r.status || r.lifecycle_state || '-'} • Risk {r.risk_percent ?? '-'}% • {r.daily_bias || '-'} → {r.daily_objective_1 || '-'}</span><em>{r.intraday_state || '-'} • {r.favourable_trade || '-'} • TP {r.tp1_hit?'1':''}{r.tp2_hit?'2':''}{r.tp3_hit?'3':'' || '-'}</em></button>)}</div>
      <div className="miniPanel"><h4>Selected Trade Detail + Edit</h4>{!edit?.id && <p className="emptyText">Select a trade to inspect and fill missing fields.</p>}{edit?.id && <div className="editTradeForm">
        <label>Date / Time<input value={edit.created_at || ''} onChange={e=>setField('created_at', e.target.value)} /></label>
        <label>Session<select value={edit.session || ''} onChange={e=>setField('session', e.target.value)}>{['','ASIA','LONDON','NEW_YORK','POST_NY','SWING'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Direction<select value={edit.direction || ''} onChange={e=>setField('direction', e.target.value)}>{['','BUY','SELL'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Status<select value={edit.status || ''} onChange={e=>setField('status', e.target.value)}>{['OPENED','TP1_HIT','TP2_HIT','RUNNER_ACTIVE','CLOSED','STOPPED_OUT','INVALIDATED'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Risk %<input value={edit.risk_percent ?? ''} onChange={e=>setField('risk_percent', e.target.value)} /></label>
        <label>Entry<input value={edit.entry_price ?? ''} onChange={e=>setField('entry_price', e.target.value)} /></label>
        <label>SL<input value={edit.sl_price ?? ''} onChange={e=>setField('sl_price', e.target.value)} /></label>
        <label>Weekly Bias<select value={edit.weekly_bias || ''} onChange={e=>setField('weekly_bias', e.target.value)}>{['','BULLISH','BEARISH','WATCHING'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Weekly State<input value={edit.weekly_state || ''} onChange={e=>setField('weekly_state', e.target.value)} /></label>
        <label>Daily Bias<select value={edit.daily_bias || ''} onChange={e=>setField('daily_bias', e.target.value)}>{['','BULLISH','BEARISH','WATCHING'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Profile<select value={edit.daily_profile || ''} onChange={e=>setField('daily_profile', e.target.value)}>{['',...DAILY_PROFILES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Position %<input value={edit.daily_position_pct ?? ''} onChange={e=>setField('daily_position_pct', e.target.value)} /></label>
        <label>Daily Objective 1<select value={edit.daily_objective_1 || ''} onChange={e=>setField('daily_objective_1', e.target.value)}>{['',...OBJECTIVE_TYPES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Objective 2<select value={edit.daily_objective_2 || ''} onChange={e=>setField('daily_objective_2', e.target.value)}>{['',...OBJECTIVE_TYPES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Daily Objective 3<select value={edit.daily_objective_3 || ''} onChange={e=>setField('daily_objective_3', e.target.value)}>{['',...OBJECTIVE_TYPES].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Intraday State<input value={edit.intraday_state || ''} onChange={e=>setField('intraday_state', e.target.value)} /></label>
        <label>Favourable Trade<select value={edit.favourable_trade || ''} onChange={e=>setField('favourable_trade', e.target.value)}>{['','NO_FAVOURABLE_TRADE','P1_CONTINUATION','P2_CONTINUATION','P3_FAILURE_REVERSAL','NEW_P1_PROFILE_FLIP'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Retest Status<select value={edit.retest_status || ''} onChange={e=>setField('retest_status', e.target.value)}>{['','WAITING','RETEST_PENDING','RETEST_ACTIVE','RETEST_COMPLETE','RETEST_FAILED'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Micro Confirmation<select value={edit.micro_confirmation || ''} onChange={e=>setField('micro_confirmation', e.target.value)}>{['','WAITING','CONFIRMED','REF_CANDLE_CONFIRMED','INVALID'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>TP1<select value={edit.tp1_hit ? '1':'0'} onChange={e=>setField('tp1_hit', e.target.value === '1')}>{['0','1'].map(x=><option key={x} value={x}>{x==='1'?'HIT':'-'}</option>)}</select></label>
        <label>TP2<select value={edit.tp2_hit ? '1':'0'} onChange={e=>setField('tp2_hit', e.target.value === '1')}>{['0','1'].map(x=><option key={x} value={x}>{x==='1'?'HIT':'-'}</option>)}</select></label>
        <label>TP3<select value={edit.tp3_hit ? '1':'0'} onChange={e=>setField('tp3_hit', e.target.value === '1')}>{['0','1'].map(x=><option key={x} value={x}>{x==='1'?'HIT':'-'}</option>)}</select></label>
        <label>MFE R<input value={edit.mfe_r ?? ''} onChange={e=>setField('mfe_r', e.target.value)} /></label>
        <label>MAE R<input value={edit.mae_r ?? ''} onChange={e=>setField('mae_r', e.target.value)} /></label>
        <label>Final R<input value={edit.final_r ?? ''} onChange={e=>setField('final_r', e.target.value)} /></label>
        <label className="wide">Machine Message<textarea value={edit.machine_message || ''} onChange={e=>setField('machine_message', e.target.value)} /></label>
        <button className="primaryBtn solo" onClick={saveTrade}>Save Trade Memory</button>{saveState && <p className="saveNote">{saveState}</p>}
      </div>}</div></div>}
    {tab === 'ideas' && <div className="cleanList">{ideas.length===0 ? <p className="emptyText">No structured ideas saved yet.</p> : ideas.map((r:any)=><div className="journalItem" key={r.id}><b>{r.created_at} • {r.symbol} {r.direction || ''}</b><span>{r.lifecycle_state || 'WATCHING'} • {r.setup_type || '-'} • Risk {r.risk_percent ?? '-'}% • Objective {r.objective || '-'}</span></div>)}</div>}
    {tab === 'scenarios' && <div className="cleanList"><p className="emptyText">Run new scenario tests from Data Collection. History appears here.</p>{scenarios.length===0 ? <p className="emptyText">No scenario tests yet.</p> : scenarios.map((r:any)=><div className="journalItem" key={r.id}><b>{r.scenario_name || 'Scenario'} {r.pass_flag === 1 ? '✅' : r.pass_flag === 0 ? '⚠️' : ''}</b><span>{r.created_at} • Expected {r.expected_status || '-'} → Actual {r.actual_status || '-'}</span></div>)}</div>}
    {tab === 'lifecycle' && <div className="cleanList">{lifecycle.length===0 ? <p className="emptyText">No lifecycle snapshots saved yet.</p> : lifecycle.map((r:any)=><div className="journalItem" key={r.id}><b>{r.symbol} lifecycle v{r.snapshot_version}</b><span>{r.created_at} • Daily {r.daily?.daily_state || r.daily?.daily_profile || '-'} • Intraday {r.intraday?.intraday_state || r.intraday?.phase_state || '-'}</span></div>)}</div>}
    {tab === 'maps' && <div className="cleanList">{maps.length===0 ? <p className="emptyText">No map saves yet. Save maps from Map Settings.</p> : maps.map((r:any)=><div className="journalItem" key={r.id}><b>{r.symbol} map v{r.state_version}</b><span>{r.updated_at || r.created_at} • {r.source || 'unknown'}</span></div>)}</div>}
  </div>;
}
function InfoLine({label,value}:any){return <div className="infoLine"><span>{label}</span><b>{String(value ?? '-')}</b></div>}
function Kpi({label,value}:any){return <div className="kpiCard"><span>{label}</span><b>{String(value)}</b></div>}
function SqlPage({ status, journal, summary, structured }: any) { return <div className="card largeCard"><h3>SQL Status</h3><pre className="jsonBox">{JSON.stringify({ status, journalSummary: summary, structuredRecent: structured, recentCount: journal?.length || 0 }, null, 2)}</pre></div>; }
function getStructuralMetrics(layer: LayerKey, path: GraphPoint[], low: number, high: number, hasRange: boolean, currentPoint: GraphPoint | undefined, visual: VisualLayer) {
  const out: string[] = [];
  const priceOf = (key: string) => { const p = path.find(x => String(x.anchorKey || x.label || '').toUpperCase() === key); const n = parseNum(p?.price); return Number.isFinite(n) ? n : null; };
  if (layer === 'intraday') {
    const ch = priceOf('CHOCH_HIGH'), cl = priceOf('CHOCH_LOW'), cb = priceOf('CHOCH_BREAK');
    if (ch != null && cl != null) out.push(`CHOCH Δ ${Math.abs(ch - cl).toFixed(2)} pts`);
    if (ch != null && cl != null && cb != null && ch !== cl) out.push(`Break ${(Math.abs(cb - cl) / Math.abs(ch - cl) * 100).toFixed(0)}% of CHOCH range`);
  }
  if (hasRange) {
    const cp = parseNum(currentPoint?.price);
    if (Number.isFinite(cp)) {
      const pct = ((cp - low) / Math.max(1e-9, high - low)) * 100;
      out.push(`Current ${pct.toFixed(1)}% of range`);
    }
    const objPrice = priceForZone(visual.objectiveZone, low, high);
    const cur = parseNum(currentPoint?.price);
    if (Number.isFinite(cur) && Number.isFinite(objPrice)) out.push(`Objective distance ${Math.abs(objPrice - cur).toFixed(2)} pts`);
  }
  return out.slice(0, 3);
}
function fmtPct(v:any){ const n = parseNum(v); return Number.isFinite(n) ? `${n.toFixed(2)}%` : '-'; }
function fmtPctOrDash(v:any){ const n = parseNum(v); return Number.isFinite(n) ? `${n.toFixed(2)}%` : 'Map range required'; }
function Metric({ label, value, color = '#e5e7eb' }: any) { return <div className="metric"><span>{label}</span><b style={{ color }}>{String(value)}</b></div>; }
function Mini({ label, value, highlight }: any) { return <div className="mini"><span>{label}</span><b className={highlight ? 'goldText' : ''}>{value}</b></div>; }
function Pill({ label, value }: any) { return <div className="pill"><span>{label}</span><b>{value}</b></div>; }
function Check({ label, active }: any) { return <div className={`check ${active ? 'on' : ''}`}><CheckCircle2 size={15}/>{label}</div>; }
function truthy(v: any) { return v === true || v === 'true' || v === 1 || v === '1' || v === 'YES'; }
function clamp(n: number, min: number, max: number) { return Math.max(min, Math.min(max, Number.isFinite(n) ? n : 50)); }
function parseNum(v:any){ return parseFloat(String(v ?? '').replace(',', '.')); }
function extractLivePrice(state: any, active: any): number | null { const candidates = [active?.raw_status?.current_price, active?.current_price, state?.price?.bid, state?.price?.last, state?.live_price, state?.current_price]; for (const c of candidates) { const n = parseNum(c); if (Number.isFinite(n) && n > 0) return n; } return null; }
function getExtFlow(mapBias: any, narrative: any): 'bullish' | 'bearish' | 'manual' {
  const b = String(mapBias || '').toLowerCase();
  const n = String(narrative || '').toLowerCase();
  if (b.includes('bear') || n.includes('bear') || n.includes('bos up')) return 'bearish';
  if (b.includes('bull') || n.includes('bull') || n.includes('bos down')) return 'bullish';
  return 'manual';
}
function yForPrice(price: number, low: number, high: number) { if (!Number.isFinite(price) || high <= low) return 50; return clamp(92 - ((price - low) / (high - low)) * 84, 6, 94); }
function priceFromY(y: number, low: number, high: number) { return low + ((92 - y) / 84) * (high - low); }
function priceForZone(z: any, low: number, high: number) { const pct = zoneToRangePct(z); return low + (pct / 100) * (high - low); }
function zoneToRangePct(z: any) { const s = String(z || '').toLowerCase(); if (s.includes('ext l') || s.includes('external low')) return 0; if (s === 'dd' || s.includes('deep discount')) return 14; if (s === 'd' || s.includes('discount')) return 32; if (s.includes('fair')) return 50; if (s === 'p' || s.includes('premium')) return 68; if (s === 'dp' || s.includes('deep premium')) return 86; if (s.includes('ext h') || s.includes('external high')) return 100; return 50; }
function zoneFromY(y: number) { if (y < 15) return 'Ext H'; if (y < 29) return 'DP'; if (y < 43) return 'P'; if (y < 57) return 'Fair'; if (y < 71) return 'D'; if (y < 85) return 'DD'; return 'Ext L'; }
function buildPriceTicks(low: number, high: number, step = 200) { const out: { price: number; y: number }[] = []; const start = Math.ceil(low / step) * step; let lastY = -999; for (let p = start; p <= high; p += step) { const y = yForPrice(p, low, high); if (Math.abs(y - lastY) >= 12) { out.push({ price: p, y }); lastY = y; } } return out; }
function yForZone(z: any) { const s = String(z || '').toLowerCase(); if (s.includes('ext h') || s.includes('external high')) return 8; if (s === 'dp' || s.includes('deep premium')) return 22; if (s === 'p' || s.includes('premium')) return 35; if (s.includes('fair')) return 50; if (s === 'd' || s.includes('discount')) return 65; if (s === 'dd' || s.includes('deep discount')) return 78; if (s.includes('ext l') || s.includes('external low')) return 92; return 50; }
function cryptoId(){ try { return crypto.randomUUID(); } catch { return `p_${Date.now()}_${Math.random().toString(16).slice(2)}`; } }

function normalizeMitigationLevels(raw: any): MitigationLevels {
  const base = emptyMitigationLevels();
  const src = raw || {};
  (['discount','fair_price','premium'] as const).forEach(zone => {
    const zd = src?.[zone] || src?.[zone.toUpperCase()] || src?.[zone.replace('_','')] || {};
    (['m1','m2','m3'] as const).forEach(level => {
      const val = zd?.[level] || zd?.[level.toUpperCase()] || {};
      base[zone][level] = typeof val === 'object' ? { price: val.price ?? '', status: val.status ?? 'WAITING', role: val.role ?? '' } : { price: String(val || ''), status: 'WAITING' };
    });
  });
  return base;
}

function normalizeVisuals(raw: any): VisualStore { const out: any = {}; for (const k of LAYERS) { const base = defaultVisual[k]; const v = raw?.[k] || base; out[k] = { ...base, ...v, narrative: v.narrative || base.narrative || '', mapBias: v.mapBias || base.mapBias || 'manual', meta: { ...(base.meta || {}), ...(v.meta || {}) }, brokenExternal: v.brokenExternal || base.brokenExternal || 'NONE', brokenExternalPrice: v.brokenExternalPrice || base.brokenExternalPrice || '', useLiveCurrent: Boolean(v.useLiveCurrent ?? base.useLiveCurrent ?? false), projectionX: Number(v.projectionX ?? base.projectionX ?? 90), projectionPrice: v.projectionPrice || base.projectionPrice || '', liquidityCleanUpPrice: v.liquidityCleanUpPrice ?? base.liquidityCleanUpPrice ?? '', showLiquidityCleanUp: Boolean(v.showLiquidityCleanUp ?? base.showLiquidityCleanUp ?? false), mitigation: { ...base.mitigation, ...(v.mitigation || {}) }, mitigationLevels: normalizeMitigationLevels(v.mitigationLevels || v.mitigation_levels || base.mitigationLevels), mitigationSequence: Array.isArray(v.mitigationSequence || v.mitigation_sequence) ? (v.mitigationSequence || v.mitigation_sequence) : [], path: (v.path || base.path).map((p: any, idx: number) => ({ id: p.id || cryptoId(), label: p.label || p.anchorKey || '', anchorKey: p.anchorKey || p.label || '', status: p.status || 'INTACT', role: p.role || '', sequenceColumn: Number(p.sequenceColumn ?? idx + 1), zone: p.zone || 'Fair', x: Number(p.x ?? 50), price: p.price || '', live: Boolean(p.live) })) }; } return out; }
function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] { const [value, setValue] = useState<T>(() => { try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : initial; } catch { return initial; } }); const setStored = (v: T) => { setValue(v); localStorage.setItem(key, JSON.stringify(v)); }; return [value, setStored]; }

createRoot(document.getElementById('root')!).render(<App />);
