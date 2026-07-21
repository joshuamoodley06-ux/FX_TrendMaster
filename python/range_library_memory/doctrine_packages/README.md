# FXTM doctrine packages

These are ordinary uploadable doctrine versions, not pre-approved application adapters.

## Weekly structure brain

Both files use the same script key:

```text
weekly_structure
```

Versions:

```text
weekly_bos_v1.py -> VERSION_LABEL = 1
weekly_bos_v2.py -> VERSION_LABEL = 2
```

Required lifecycle:

```text
select package
-> validate exact source and metadata
-> run against disposable analysis workspace
-> review five samples
-> 5/5 approval moves current_approved_version_id to that version
-> future active-pipeline runs execute that exact stored source
```

A pending or rejected v2 never replaces an approved v1. The package files are not activated merely because they exist in the repository.
