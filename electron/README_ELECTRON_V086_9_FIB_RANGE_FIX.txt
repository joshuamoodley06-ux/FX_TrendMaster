Electron v086.9 - Fib Range State Fix

Fixes:
- Range/fib anchors now update reliably when saving bundled selected-candle range events.
- Set W High + Set W Low can be saved as one bundle and still produces a live fib range.
- Same fix applies to Macro and Daily selected-candle range anchors.
- D3 redraw now watches range start/end changes as well as range high/low.
- Backend untouched.

Reason:
The prior bundle-save path used React state before it finished updating, so markers could plot on the chart while the active range/fib state never received both anchors. Very rude. Fixed with an immediate event-state ref and explicit range sync for anchor markers.
