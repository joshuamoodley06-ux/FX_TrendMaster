from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_audit_json(audit: dict[str, Any], export_dir: str, case_id: str) -> str:
    output_dir = Path(export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = audit.get("generated_at_utc_ms", 0)
    filename = f"{case_id}_{timestamp}.audit.json"
    output_path = output_dir / filename

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(audit, handle, indent=2, sort_keys=False)
        handle.write("\n")

    return str(output_path)
