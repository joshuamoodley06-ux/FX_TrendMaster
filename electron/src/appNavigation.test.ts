import { describe, expect, it } from 'vitest';
import {
  ADMIN_FLYOUT_PAGES,
  PAGE_PATH,
  PRIMARY_NAV_PAGES,
  isAdminPage,
  normalizeAppPage,
  type AppPage,
} from './appNavigation';

describe('appNavigation', () => {
  it('maps map-studio path to mapstudio page', () => {
    expect(PAGE_PATH.mapstudio).toBe('/map-studio');
  });

  it('defines primary nav pages', () => {
    expect(PRIMARY_NAV_PAGES).toEqual(['mapstudio', 'journal', 'data']);
  });

  it('treats admin flyout pages as admin', () => {
    for (const page of ADMIN_FLYOUT_PAGES) {
      expect(isAdminPage(page)).toBe(true);
    }
    expect(isAdminPage('mapstudio')).toBe(false);
  });

  it('covers all primary and admin pages with paths', () => {
    const pages: AppPage[] = [
      'mapstudio', 'journal', 'data', 'historical', 'settings', 'sql', 'brain', 'ideas',
    ];
    for (const page of pages) {
      expect(PAGE_PATH[page]).toMatch(/^\//);
    }
  });

  it('normalizes retired pages to mapstudio', () => {
    expect(normalizeAppPage('visual')).toBe('mapstudio');
    expect(normalizeAppPage('live')).toBe('mapstudio');
  });
});
