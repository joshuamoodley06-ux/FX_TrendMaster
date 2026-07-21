# FXTM doctrine packages

These files are reviewed analytical packages. Merely storing a file does not approve it.

## Weekly analysis chain

The repository currently keeps two distinct analytical scripts:

```text
weekly_bos.py       -> weekly_structure
weekly_reclaim.py   -> weekly_reclaim
```

They do different jobs and execute in order:

```text
Weekly BOS memory
-> Weekly reclaim / abandonment memory
```

`weekly_reclaim.py` does not detect BOS again. It reads the approved `weekly_structure` payload for each Weekly range.

## Weekly BOS

`weekly_bos.py` owns:

```text
first future W1 wick beyond RH or RL
BOS direction
BOS candle and price
weeks to BOS
```

Its permanent memory key is `weekly_structure`. Only one current Weekly BOS package file is maintained. When the logic improves, update this same file and increase its version label. Older approved source versions remain in database history for rollback and audit; they do not remain as parallel package files.

## Weekly reclaim and abandonment

`weekly_reclaim.py` owns:

```text
BOS_UP   -> old RH is the reclaim boundary
BOS_DOWN -> old RL is the reclaim boundary
```

A later W1 wick touching or crossing the breached old boundary counts as `RECLAIMED`.

If a later-defined Weekly range records a new approved BOS before any reclaim, the earlier range is marked `ABANDONED`.

If neither event exists yet, the earlier range remains `PENDING`.

The reclaim script stores the reclaim/abandonment date and the number of W1 candles checked. A reclaim on the same W1 candle as the later BOS still counts as reclaimed because the old boundary was reached; abandonment applies only when no reclaim occurred.

## Approval workflow

Each script follows the same lifecycle:

```text
select package
-> validate the source
-> run five review cases in the analysis workspace
-> approve 5/5
-> store that exact source as the current approved version
-> run only that approved version in execution order
```
