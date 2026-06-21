/** Ephemeral chart marker kinds — UI-only until promoted to raw ledger events. */
export type MappingPointKind = 'pivot' | 'zone' | 'anchor';

/** Single clickable marker in the mapping draft container. */
export type MappingPoint = {
  id: string;
  time: string;
  price: number;
  kind: MappingPointKind;
  label?: string;
  createdAt: string;
};

/** In-memory mapping draft — holds tentative pivots/zones before raw event emission. */
export type MappingDraft = {
  id: string;
  symbol: string;
  timeframe: string;
  caseId?: string | null;
  points: MappingPoint[];
  /** Derived from points — earliest marker time (UTC ISO). */
  startTime?: string | null;
  /** Derived from points — latest marker time (UTC ISO). */
  endTime?: string | null;
  /** Child draft link to parent chart timeframe container. */
  linkedParentTimeframe?: string | null;
  updatedAt: string;
};

export type MappingDraftPointInput = {
  time: string;
  price: number;
  kind?: MappingPointKind;
  label?: string;
};

export type { MappingViewContext } from './mappingViewContext';
