Electron v086.15 - Weekly PWH/PWL + Daily Ref H/L Patch

- Added Weekly Reference Liquidity group:
  WEEKLY_PWH_REFERENCE
  WEEKLY_PWL_REFERENCE
  WEEKLY_PWH_SWEEP_REF_CANDLE
  WEEKLY_PWL_SWEEP_REF_CANDLE
  WEEKLY_NO_SWEEP_REF_CANDLE

- Added Daily Reference Structure group:
  DAILY_REF_HIGH_ACTIVE
  DAILY_REF_LOW_ACTIVE

- Updated ref high/low marker recognition so these show as reference labels.
- These are narrative/reference facts only; they do not move fib anchors.
- Explicit Set M/W/D High and Set M/W/D Low remain the only fib anchor controls.
- Backend untouched.
