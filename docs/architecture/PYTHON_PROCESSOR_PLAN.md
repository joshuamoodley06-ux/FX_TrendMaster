# Python Processor Plan

## Goal

The Python processor consumes the hardened raw mapping ledger and turns human clicks into audited structure, ranges, features and later model-ready stats.

## First milestone

```text
python main.py --case-id <case_id>
```

Should:

```text
1. Download raw ledger export
2. Verify schema version
3. Verify/export ledger hash
4. Resolve DELETE_RECORD and supersedes chains
5. Emit clean surviving event timeline
6. Save local audit JSON
```

## Future passes

```text
Pass 1: ledger_resolver.py      # resolve visibility and event intent
Pass 2: timeline_builder.py     # sort by market/candle time
Pass 3: range_builder.py        # build high/low/BOS/reclaim/abandon lifecycle
Pass 4: relationship_linker.py  # parent/child W1 -> D1 -> intraday linking
Pass 5: feature_builder.py      # zone %, premium/discount, profile hints, stats fields
Pass 6: audit_checks.py         # catch contradictions before training data exists
```
