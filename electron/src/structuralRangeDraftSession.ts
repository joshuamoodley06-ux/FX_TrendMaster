export type StructuralRangeDraftMode = 'NEW' | 'EDIT';
export type StructuralRangeDraftSide = 'RH' | 'RL';

export type StructuralDraftAnchor = {
  price?: string | number | null;
  time?: string | null;
};

export type StructuralRangeDraftSession = {
  sessionId: string;
  mode: StructuralRangeDraftMode;
  structureLayer: string;
  sourceTimeframe: string;
  targetRangeId: string;
  rhTouched: boolean;
  rlTouched: boolean;
};

const normalizeScopeValue = (value: unknown) => String(value || '').trim().toUpperCase();

export function createStructuralRangeDraftSession(args: {
  sessionId: string;
  mode?: StructuralRangeDraftMode;
  structureLayer: string;
  sourceTimeframe: string;
  targetRangeId?: string | number | null;
  rhTouched?: boolean;
  rlTouched?: boolean;
}): StructuralRangeDraftSession {
  return {
    sessionId: String(args.sessionId || ''),
    mode: args.mode || 'NEW',
    structureLayer: normalizeScopeValue(args.structureLayer),
    sourceTimeframe: normalizeScopeValue(args.sourceTimeframe),
    targetRangeId: String(args.targetRangeId || ''),
    rhTouched: args.rhTouched === true,
    rlTouched: args.rlTouched === true,
  };
}

export function touchStructuralRangeDraftSession(
  session: StructuralRangeDraftSession,
  side: StructuralRangeDraftSide,
): StructuralRangeDraftSession {
  return {
    ...session,
    rhTouched: side === 'RH' ? true : session.rhTouched,
    rlTouched: side === 'RL' ? true : session.rlTouched,
  };
}

export function structuralRangeDraftSessionMatchesScope(
  session: StructuralRangeDraftSession,
  structureLayer: string,
  sourceTimeframe: string,
): boolean {
  return session.structureLayer === normalizeScopeValue(structureLayer)
    && session.sourceTimeframe === normalizeScopeValue(sourceTimeframe);
}

export function structuralRangeDraftSaveBlockReason(args: {
  session: StructuralRangeDraftSession;
  structureLayer: string;
  sourceTimeframe: string;
  activeRangeId?: string | number | null;
  rh: StructuralDraftAnchor;
  rl: StructuralDraftAnchor;
}): string | null {
  const layer = normalizeScopeValue(args.structureLayer) || 'STRUCTURAL';
  const sourceTimeframe = normalizeScopeValue(args.sourceTimeframe);
  if (!structuralRangeDraftSessionMatchesScope(args.session, layer, sourceTimeframe)) {
    return `Draft scope changed — set RH and RL again for ${layer} / ${sourceTimeframe}.`;
  }

  if (args.session.mode === 'EDIT') {
    const activeRangeId = String(args.activeRangeId || '');
    if (!args.session.targetRangeId || activeRangeId !== args.session.targetRangeId) {
      return 'Edit target changed — reopen Edit on the exact saved range before saving.';
    }
  } else {
    if (!args.session.rhTouched && !args.session.rlTouched) {
      return `Set Range High and Range Low for this ${layer} draft.`;
    }
    if (!args.session.rhTouched) {
      return `Set Range High for this ${layer} draft; an older RH cannot be reused.`;
    }
    if (!args.session.rlTouched) {
      return `Set Range Low for this ${layer} draft; an older RL cannot be reused.`;
    }
  }

  const rhPrice = Number(args.rh.price);
  const rlPrice = Number(args.rl.price);
  const rhTime = String(args.rh.time || '').trim();
  const rlTime = String(args.rl.time || '').trim();
  if (!Number.isFinite(rhPrice) || !rhTime) return 'Range High must have a valid price and candle time.';
  if (!Number.isFinite(rlPrice) || !rlTime) return 'Range Low must have a valid price and candle time.';
  if (rhPrice <= rlPrice) return 'Range High must be above Range Low.';
  return null;
}

export type StructuralRangeDraftSnapshot<TAnchor extends StructuralDraftAnchor> = {
  sessionId: string;
  mode: StructuralRangeDraftMode;
  structureLayer: string;
  sourceTimeframe: string;
  targetRangeId: string;
  rh: TAnchor;
  rl: TAnchor;
};

export function captureStructuralRangeDraftSnapshot<TAnchor extends StructuralDraftAnchor>(args: {
  session: StructuralRangeDraftSession;
  structureLayer: string;
  sourceTimeframe: string;
  activeRangeId?: string | number | null;
  rh: TAnchor;
  rl: TAnchor;
}):
  | { ok: true; snapshot: StructuralRangeDraftSnapshot<TAnchor> }
  | { ok: false; reason: string } {
  const reason = structuralRangeDraftSaveBlockReason(args);
  if (reason) return { ok: false, reason };
  return {
    ok: true,
    snapshot: {
      sessionId: args.session.sessionId,
      mode: args.session.mode,
      structureLayer: args.session.structureLayer,
      sourceTimeframe: args.session.sourceTimeframe,
      targetRangeId: args.session.targetRangeId,
      rh: { ...args.rh },
      rl: { ...args.rl },
    },
  };
}
