"""Input loading for raw Range Library exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_export(path: str | Path) -> Any:
    """Load a JSON fixture or export from disk."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
