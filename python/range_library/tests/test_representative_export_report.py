from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT))

from range_library.ingest import load_export
from range_library.normalize import extract_raw_ranges, normalize_ranges
from range_library.report import generate_summary_report


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "current_mapping_XAUUSD_raw_20f4eeba-94e7-4d06-806e-2fa2aa15ec74.json"
)


def test_representative_export_report_counts() -> None:
    raw_export = load_export(FIXTURE_PATH)
    records = normalize_ranges(extract_raw_ranges(raw_export))

    report = generate_summary_report(records)

    assert report["total_ranges"] == 6
    assert report["counts_by_layer"] == {
        "W1": 1,
        "D1": 2,
        "H4": 2,
        "H1": 1,
    }
    assert report["counts_by_status"] == {
        "active": 3,
        "archived": 1,
        "confirmed": 1,
        "candidate": 1,
    }
    assert report["orphan_count"] == 2


def test_cli_generates_json_report() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PACKAGE_ROOT)

    completed = subprocess.run(
        [sys.executable, "-m", "range_library.cli", str(FIXTURE_PATH)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    report = json.loads(completed.stdout)

    assert report["total_ranges"] == 6
    assert report["counts_by_layer"]["D1"] == 2
    assert report["counts_by_status"]["active"] == 3
    assert report["orphan_count"] == 2
