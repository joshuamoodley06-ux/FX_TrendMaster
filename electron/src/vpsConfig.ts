/** Shared VPS base URL — safe for renderer imports (no Node APIs). */
export const DEFAULT_VPS_BASE_URL = 'https://api01.apexcoastalrentals.co.za';

const DEV_ORIGIN = 'http://localhost:5173';

/**
 * In Vite dev, use same-origin requests so vite.config proxy reaches the VPS
 * (avoids browser CORS blocks from localhost:5173).
 * Packaged Electron uses the full VPS URL.
 */
export function resolveVpsBaseUrl(): string {
  if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
    return '';
  }
  return DEFAULT_VPS_BASE_URL;
}

/** Join base + path for fetch(). Works when base is '' (dev proxy). */
export function vpsFetchPath(path: string, baseUrl = resolveVpsBaseUrl()): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = String(baseUrl || '').replace(/\/$/, '');
  return base ? `${base}${normalizedPath}` : normalizedPath;
}

/** Build absolute URL with optional query params (safe when base is '' in dev). */
export function buildVpsUrl(
  path: string,
  baseUrl = resolveVpsBaseUrl(),
  params?: Record<string, string | number | undefined | null>,
): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = String(baseUrl || '').replace(/\/$/, '');
  const url = base
    ? new URL(`${base}${normalizedPath}`)
    : new URL(
        normalizedPath,
        typeof window !== 'undefined' ? window.location.origin : DEV_ORIGIN,
      );
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}
