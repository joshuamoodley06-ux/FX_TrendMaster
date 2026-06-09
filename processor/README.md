# FX TrendMaster Processor

Python brain for consuming raw mapping exports and compiling audited market structure.

First target:

```bash
python main.py --case-id <case_id>
```

This should fetch the raw ledger export, resolve deletes, build a clean timeline and write an audit JSON.
