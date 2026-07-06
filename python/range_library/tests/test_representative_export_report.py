import json
from pathlib import Path
from range_library.report import generate_report
from range_library.ingest import load_ranges_from_json
from range_library.normalize import normalize_range

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "current_mapping_XAUUSD_raw_20f4eeba-94e7-4d06-806e-2fa2aa15ec74.json"

def test_representative_electron_export_report_summary():
    """
    Validates the report generation against a representative (synthetic) export fixture.
    NOTE: This is NOT validated against real production Electron export data yet.
    """
    raw_ranges = load_ranges_from_json(str(FIXTURE_PATH))
    normalized = [normalize_range(r) for r in raw_ranges]
    report = generate_report(normalized)

    assert report["total_ranges"] == 4
    assert report["counts_by_layer"]["MACRO"] == 1
    assert report["counts_by_layer"]["WEEKLY"] == 1
    assert report["counts_by_layer"]["DAILY"] == 2
    assert report["counts_by_status"]["ACTIVE"] == 3
    assert report["counts_by_status"]["BROKEN"] == 1
    assert report["orphan_count"] == 1  # Range 4 is DAILY with no parent
