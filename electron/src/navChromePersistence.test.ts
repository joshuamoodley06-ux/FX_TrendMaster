import { describe, expect, it } from 'vitest';
import { NAV_CHROME_STORAGE_KEYS } from './clearAllUIAnchors';
import { MAPPING_DATA_STORAGE_KEY } from './mappingEventsPersistence';

describe('nav chrome persistence vs stale-cache guard', () => {
  it('nav rail keys are separate from mapping_data purge scope', () => {
    for (const key of NAV_CHROME_STORAGE_KEYS) {
      expect(key).not.toBe(MAPPING_DATA_STORAGE_KEY);
    }
  });

  it('documents nav chrome localStorage keys that must survive rehydration block', () => {
    expect(NAV_CHROME_STORAGE_KEYS).toContain('fx_tm_inspector_tab_v1');
    expect(NAV_CHROME_STORAGE_KEYS).toContain('fx_tm_top_ribbon_collapsed_v087_24');
  });
});
