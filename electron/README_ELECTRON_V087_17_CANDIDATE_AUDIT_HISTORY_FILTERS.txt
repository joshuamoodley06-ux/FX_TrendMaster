# Electron v087.17 Candidate Audit + History Mark Filters

- Rejected HTF candidates are now saved as HTF_CANDIDATE_REJECTED events with candidate_status=REJECTED in meta_json.
- Rejected candidates are linked to active case/range metadata for later ML training.
- Case Manager now shows Candidate Audit counts: accepted HTF, rejected candidates, edited.
- Case Manager shows a rejected candidate audit list with jump-to-candle controls.
- History mark display now supports modes: OFF, Session, Active Range, Active Case, Nearby, All.
- Rejected candidate chart marks are hidden by default, with a separate Rejected ON/OFF toggle.
- Stored does not mean displayed: ledger keeps everything, chart shows only what helps the current mapping pass.
