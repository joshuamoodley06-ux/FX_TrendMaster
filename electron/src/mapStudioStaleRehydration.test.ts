import { describe, expect, it } from 'vitest';
import {
  applyGhostClearToUiState,
  buildMapStudioGhostClearState,
  createGhostMapStudioUiState,
  hasGhostMapStudioData,
  isStaleRehydrationLoad,
} from './mapStudioStaleRehydration';

describe('mapStudioStaleRehydration', () => {
  it('detects stale sync architect loads', () => {
    expect(isStaleRehydrationLoad({ should_clear_ui: true })).toBe(true);
    expect(isStaleRehydrationLoad({ should_clear_ui: false })).toBe(false);
  });

  it('clears all ghost chart markers from UI snapshot', () => {
    const prior = createGhostMapStudioUiState('D1');
    expect(hasGhostMapStudioData(prior)).toBe(true);
    const cleared = applyGhostClearToUiState(prior, 'XAUUSD', 'D1');
    expect(hasGhostMapStudioData(cleared)).toBe(false);
    expect(cleared).toEqual(buildMapStudioGhostClearState('XAUUSD', 'D1'));
  });
});
