# FXTM doctrine packages

These files are reviewed analytical packages. Merely storing a file does not approve it.

## Weekly analysis chain

The repository currently keeps three distinct analytical scripts:

```text
weekly_bos.py             -> weekly_structure
weekly_reclaim.py         -> weekly_reclaim
weekly_reclaim_depth.py   -> weekly_reclaim_depth
```

They execute in order:

```text
Weekly BOS memory
-> Weekly reclaim / abandonment memory
-> Weekly reclaim depth memory
```

Each script reads approved output from the previous step instead of repeating its work.

## Weekly BOS

`weekly_bos.py` owns:

```text
first future W1 wick beyond RH or RL
BOS direction
BOS candle and price
weeks to BOS
```

If RH and RL come from the same W1 candle, chronology is stored as `SAME_W1`. The script starts scanning after that anchor candle and the first later one-sided wick break establishes BOS. A later candle breaching both boundaries still requires review.

Its permanent memory key is `weekly_structure`. Only one current Weekly BOS package file is maintained. Older approved source versions remain in database history for rollback and audit; they do not remain as parallel package files.

## Weekly reclaim and abandonment

`weekly_reclaim.py` owns:

```text
BOS_UP   -> old RH is the reclaim boundary
BOS_DOWN -> old RL is the reclaim boundary
```

A later W1 wick touching or crossing the breached old boundary counts as `RECLAIMED`.

If a later-defined Weekly range records a new approved BOS before any reclaim, the earlier range is marked `ABANDONED`.

If neither event exists yet, the earlier range remains `PENDING`.

## Weekly reclaim depth

`weekly_reclaim_depth.py` runs only after an approved reclaim. It records:

```text
deepest W1 wick after reclaim
price distance from the reclaimed boundary
percentage depth through the old Weekly range
whether the old opposite external was touched or exceeded
weeks observed
```

For `BOS_UP`, depth is measured down from old RH. For `BOS_DOWN`, depth is measured up from old RL. Measurement ends at the next approved Weekly BOS, or at the latest W1 candle when no later BOS exists.

Depth is stored continuously. No shallow, medium, or deep category is hardcoded.

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
