"""Public XAUUSD Master Map façade with exact-boundary lifecycle resolution."""
from __future__ import annotations

from . import _master_map_core as _core
from .master_map_lifecycle import install as _install, main

_install(_core)

# Preserve the established module API while keeping lifecycle policy isolated.
for _name in dir(_core):
    if not _name.startswith("_") and _name not in globals():
        globals()[_name] = getattr(_core, _name)

build_master_map = _core.build_master_map
load_master_map_output = _core.load_master_map_output

if __name__ == "__main__":
    raise SystemExit(main())
