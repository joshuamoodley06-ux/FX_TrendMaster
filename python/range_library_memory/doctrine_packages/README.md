# FXTM doctrine packages

These files are reviewed analytical packages. Merely storing a file does not approve it.

## Weekly structure

The repository keeps one current Weekly BOS package:

```text
weekly_bos.py
```

Its permanent memory key is:

```text
weekly_structure
```

The current logic is labelled version `2`. Only one Weekly package file is maintained.

Workflow:

```text
select weekly_bos.py
-> validate the source
-> run five review cases in the analysis workspace
-> approve 5/5
-> store that exact source as the current approved version
-> run only that approved version in the active pipeline
```

When Weekly BOS logic improves, update this same package and increase its version label. Older approved source versions remain in database history for rollback and audit. They do not remain as parallel package files.
