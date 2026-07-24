from __future__ import annotations

from pathlib import Path

from range_library_memory import statistics_runtime_registry


class Pipeline:
    def __init__(self):
        self.applied = 0
        self.ran = 0

        def apply(connection, master_map, *, symbol):
            self.applied += 1
            master_map["base"] = symbol

        def run(db_path, *, case_ref, symbol, source_db):
            self.ran += 1
            return {"base": True}

        self.apply_approved_enrichments = apply
        self.run_active_pipeline = run


def test_installs_after_existing_runtime_and_builds_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pipeline = Pipeline()
    monkeypatch.setattr(
        statistics_runtime_registry,
        "build_statistics_report",
        lambda *args, **kwargs: {"report_id": "r1"},
    )
    monkeypatch.setattr(
        statistics_runtime_registry,
        "apply_persisted_statistics_report_metadata",
        lambda *args, **kwargs: {"snapshot_count": 1},
    )
    statistics_runtime_registry.install(pipeline)

    result = pipeline.run_active_pipeline(
        tmp_path / "db.sqlite3",
        case_ref="case",
        symbol="XAUUSD",
        source_db="candles",
    )
    assert result["base"] is True
    assert result["statistics_report"]["report_id"] == "r1"
    master = {}
    pipeline.apply_approved_enrichments(object(), master, symbol="XAUUSD")
    assert master["base"] == "XAUUSD"
    assert pipeline.applied == 1
    assert pipeline.ran == 1
