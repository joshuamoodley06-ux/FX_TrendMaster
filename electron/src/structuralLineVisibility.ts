export type StructuralLineVisibilityMode = 'ALL' | 'NONE' | 'CUSTOM';

export type StructuralLineVisibility = {
  globalMode: StructuralLineVisibilityMode;
  visibleLineIds: string[];
  knownLineIds: string[];
};

export const DEFAULT_STRUCTURAL_LINE_VISIBILITY: StructuralLineVisibility = {
  globalMode: 'ALL',
  visibleLineIds: [],
  knownLineIds: [],
};

export function structuralLineId(rangeId: unknown, kind: 'RH' | 'RL'): string {
  return `${String(rangeId)}:${kind}`;
}

export function visibleStructuralLineIds(
  state: StructuralLineVisibility,
  availableIds: Iterable<string>,
  selectedRangeId?: string | null,
): Set<string> {
  const available = new Set(availableIds);
  if (state.globalMode === 'ALL') return available;
  if (state.globalMode === 'NONE') return new Set();
  const visible = new Set(state.visibleLineIds.filter((id) => available.has(id)));
  if (selectedRangeId) {
    for (const kind of ['RH', 'RL'] as const) {
      const id = structuralLineId(selectedRangeId, kind);
      if (!state.knownLineIds.includes(id) && available.has(id)) visible.add(id);
    }
  }
  return visible;
}

export function setAllStructuralLines(availableIds: Iterable<string>): StructuralLineVisibility {
  const ids = Array.from(new Set(availableIds));
  return { globalMode: 'ALL', visibleLineIds: ids, knownLineIds: ids };
}

export function setNoStructuralLines(availableIds: Iterable<string> = []): StructuralLineVisibility {
  return { globalMode: 'NONE', visibleLineIds: [], knownLineIds: Array.from(new Set(availableIds)) };
}

export function toggleStructuralLine(
  state: StructuralLineVisibility,
  lineId: string,
  availableIds: Iterable<string>,
  selectedRangeId?: string | null,
): StructuralLineVisibility {
  const available = Array.from(new Set(availableIds));
  const visible = visibleStructuralLineIds(state, available, selectedRangeId);
  visible.has(lineId) ? visible.delete(lineId) : visible.add(lineId);
  const ids = available.filter((id) => visible.has(id));
  return {
    globalMode: ids.length === 0 ? 'NONE' : ids.length === available.length ? 'ALL' : 'CUSTOM',
    visibleLineIds: ids,
    knownLineIds: available,
  };
}
