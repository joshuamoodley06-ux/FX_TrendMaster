# Electron v087.14 - Clean Session Sequence Gates

Fixes HTF semi-auto suggestion pollution and missed sequence detection.

Changes:
- New accepted suggestion lock namespace to clear old polluted localStorage locks from prior drunk-historian tests.
- If no active case is selected, structural ancestry is read from current session locks only, not old backend events.
- If an active case is selected, only accepted HTF events from that case can satisfy structural ancestry.
- BOS/reclaim/rebase gates now use clean session locks plus current-case ledger events.
- Reclaim candidates store explicit reclaim_side so lock keys match consistently.
- Ref candle zone watch now uses the latest non-confirmation-color pre-ref candle since the zone watch began, instead of blindly using the immediately previous candle.
- Rebase still requires the proper sequence: BOS + Reclaim + Current H/L accepted.

Purpose:
Prevent old test records from suppressing valid BOS detection, while still preventing duplicates inside the current mapping session/case.
