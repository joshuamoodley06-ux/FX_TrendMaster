/** Campaign chart navigation — parent (higher) vs child (lower) mapping context. */

export type MappingViewContext = 'parent' | 'child';

export type StructureLayerLike = 'MACRO' | 'WEEKLY' | 'DAILY' | 'INTRADAY' | 'MICRO' | string;

const STRUCTURE_LAYERS: StructureLayerLike[] = ['MACRO', 'WEEKLY', 'DAILY', 'INTRADAY', 'MICRO'];

const DEFAULT_CHART_TF: Record<string, string> = {
  MACRO: 'MN1',
  WEEKLY: 'W1',
  DAILY: 'D1',
  INTRADAY: 'H1',
  MICRO: 'M15',
};

const ALLOWED_CHART_TFS: Record<string, string[]> = {
  MACRO: ['MN1', 'W1'],
  WEEKLY: ['W1'],
  DAILY: ['D1'],
  INTRADAY: ['H4', 'H1'],
  MICRO: ['M15', 'M5'],
};

export function normalizeStructureLayerLike(layer: StructureLayerLike): string {
  return String(layer || 'WEEKLY').toUpperCase();
}

export function defaultChartTimeframeForLayer(layer: StructureLayerLike): string {
  return DEFAULT_CHART_TF[normalizeStructureLayerLike(layer)] || 'D1';
}

export function allowedChartTimeframesForLayer(layer: StructureLayerLike): string[] {
  return ALLOWED_CHART_TFS[normalizeStructureLayerLike(layer)] || ['D1'];
}

export function expectedParentLayer(layer: StructureLayerLike): StructureLayerLike | null {
  const key = normalizeStructureLayerLike(layer);
  const idx = STRUCTURE_LAYERS.indexOf(key);
  return idx > 0 ? STRUCTURE_LAYERS[idx - 1] : null;
}

export function expectedChildLayer(layer: StructureLayerLike): StructureLayerLike | null {
  const key = normalizeStructureLayerLike(layer);
  const idx = STRUCTURE_LAYERS.indexOf(key);
  return idx >= 0 && idx < STRUCTURE_LAYERS.length - 1 ? STRUCTURE_LAYERS[idx + 1] : null;
}

/** Child (lower) chart TF for the active mapping layer — prefers current chart if allowed. */
export function resolveChildChartTimeframe(
  structureLayer: StructureLayerLike,
  currentChartTf?: string,
): string {
  const allowed = allowedChartTimeframesForLayer(structureLayer);
  const current = String(currentChartTf || '').toUpperCase();
  if (current && allowed.includes(current)) return current;
  return defaultChartTimeframeForLayer(structureLayer);
}

/** Parent (higher) chart TF for campaign context — null when mapping MACRO with no parent. */
export function resolveParentChartTimeframe(structureLayer: StructureLayerLike): string | null {
  const parentLayer = expectedParentLayer(structureLayer);
  if (!parentLayer) return null;
  return defaultChartTimeframeForLayer(parentLayer);
}

export function resolveMappingViewChartTimeframe(
  viewContext: MappingViewContext,
  structureLayer: StructureLayerLike,
  currentChartTf?: string,
): string {
  if (viewContext === 'parent') {
    return resolveParentChartTimeframe(structureLayer)
      || resolveChildChartTimeframe(structureLayer, currentChartTf);
  }
  return resolveChildChartTimeframe(structureLayer, currentChartTf);
}

export function mappingViewContextAvailable(structureLayer: StructureLayerLike): boolean {
  return resolveParentChartTimeframe(structureLayer) !== null;
}
