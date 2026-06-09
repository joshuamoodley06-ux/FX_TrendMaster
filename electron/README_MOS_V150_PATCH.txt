MOS v150 patch applied to Electron MVP baseline

Added Electron pieces:
- Expanded Market GPS editor for parent context, daily range status, lifecycle, profile, trigger, expected next, and invalidation.
- Build MOS State button now posts to /api/v1/mos/build-state.
- Active GPS now reads /api/v1/mos/coordinates/{symbol}.
- MOS Playback Ledger panel reads /api/v1/mos/playback/{story_id}?evaluate=true.
- Playback result styling for VALIDATED, VALIDATED_SUPERSEDED, FAILED, DELAYED, and PENDING.

Run:
- npm install
- npm run build
- npm run electron
