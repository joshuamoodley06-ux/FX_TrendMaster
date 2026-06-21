export type AppPage =
  | 'mapstudio'
  | 'journal'
  | 'data'
  | 'historical'
  | 'settings'
  | 'sql'
  | 'ideas'
  | 'brain';

/** Retired routes — normalized to map studio on read. */
const LEGACY_PAGE_ALIASES: Record<string, AppPage> = {
  visual: 'mapstudio',
  live: 'mapstudio',
};

const LEGACY_PATH_ALIASES: Record<string, AppPage> = {
  '/overview': 'mapstudio',
  '/live': 'mapstudio',
};

export const PAGE_PATH: Record<AppPage, string> = {
  mapstudio: '/map-studio',
  journal: '/journal',
  data: '/data',
  historical: '/historical',
  settings: '/settings',
  sql: '/sql',
  ideas: '/ideas',
  brain: '/brain',
};

const PATH_PAGE: Record<string, AppPage> = {
  ...Object.fromEntries(Object.entries(PAGE_PATH).map(([page, path]) => [path, page as AppPage])),
  ...LEGACY_PATH_ALIASES,
};

export const PRIMARY_NAV_PAGES: AppPage[] = ['mapstudio', 'journal', 'data'];

export const ADMIN_FLYOUT_PAGES: AppPage[] = ['historical', 'settings', 'sql', 'brain', 'ideas'];

export function isAdminPage(page: AppPage): boolean {
  return ADMIN_FLYOUT_PAGES.includes(page);
}

export function normalizeAppPage(raw: string | null | undefined): AppPage | null {
  const key = String(raw || '').trim();
  if (!key) return null;
  if (key in PAGE_PATH) return key as AppPage;
  if (key in LEGACY_PAGE_ALIASES) return LEGACY_PAGE_ALIASES[key];
  return null;
}

function normalizePath(raw: string): string {
  const trimmed = String(raw || '').trim();
  if (!trimmed || trimmed === '/') return '/';
  const withoutIndex = trimmed.replace(/\/index\.html$/i, '');
  const path = withoutIndex.startsWith('/') ? withoutIndex : `/${withoutIndex}`;
  return path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path || '/';
}

export function readPageFromLocation(): AppPage | null {
  const hashPath = window.location.hash.replace(/^#/, '');
  const pathname = window.location.pathname.replace(/\/index\.html$/i, '');
  const candidate = normalizePath(hashPath || pathname);
  if (candidate === '/') return null;
  return PATH_PAGE[candidate] ?? null;
}

export function navigateToPage(page: AppPage, replace = false) {
  const path = PAGE_PATH[page];
  const current = readPageFromLocation();
  const hashPath = window.location.hash.replace(/^#/, '');
  const pathname = window.location.pathname.replace(/\/index\.html$/i, '');
  const currentPath = normalizePath(hashPath || pathname);
  if (current === page && currentPath === path) return;
  try {
    localStorage.setItem('fx_tm_page', page);
  } catch {
    /* ignore storage failures */
  }
  if (window.location.protocol === 'file:') {
    const nextHash = `#${path}`;
    if (replace) window.location.replace(nextHash);
    else window.location.hash = path;
    return;
  }
  if (replace) window.history.replaceState({ page }, '', path);
  else window.history.pushState({ page }, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function bootstrapAppPage(): AppPage {
  const fromLocation = readPageFromLocation();
  if (fromLocation) {
    navigateToPage(fromLocation, true);
    return fromLocation;
  }

  let fallback: AppPage = 'mapstudio';
  try {
    const stored = normalizeAppPage(localStorage.getItem('fx_tm_page'));
    if (stored) fallback = stored;
  } catch {
    /* ignore */
  }

  navigateToPage(fallback, true);
  return fallback;
}
