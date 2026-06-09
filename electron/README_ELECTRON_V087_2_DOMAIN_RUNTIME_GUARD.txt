V087.2 DOMAIN + RUNTIME GUARD PATCH
- Restores the normal Electron dev/start behavior from v087 (no 127.0.0.1 URL guard detour).
- Keeps API BASE_URL pointed at https://api01.apexcoastalrentals.co.za.
- Hardens Event Ledger / Range Compiler code so non-array or malformed event payloads cannot crash MapStudio.
- Save Bundle / Case update logic from v087 remains intact.
