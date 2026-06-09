FX TrendMaster Electron v074 - CSP API Domain Fix

- Electron-only patch. No backend changes.
- Adds https://api01.apexcoastalrentals.co.za to Content-Security-Policy connect-src.
- Keeps DevTools manual only and preserves v073 right deck fix.
- Fixes Failed to fetch caused by Electron CSP blocking the live VPS API domain.
