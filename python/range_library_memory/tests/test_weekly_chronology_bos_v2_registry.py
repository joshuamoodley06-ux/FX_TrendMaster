from __future__ import annotations

from typing import Any

from range_library_memory import doctrine_pipeline
from range_library_memory import weekly_chronology_bos as weekly_core


class FakeConnection:
    def __init__(self) -> None:
        self.query = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, query: str, params: tuple[Any, ...]):
        self.query = query
        self.params = params
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return [{
            "canonical_range_id": "weekly-1",
            "source_structural_hash": "structural",
            "result_hash": "result",
            "processing_status": "COMPLETE",
            "chronology_result": "RL_TO_RH",
            "bos_direction": "BOS_UP",
            "bos_candle_time": "2026-01-19T00:00:00Z",
            "reason_codes_json": "[]",
        }]


def test_v1_doctrine_reader_remains_explicitly_version_scoped() -> None:
    connection = FakeConnection()

    outputs = doctrine_pipeline._weekly_outputs(connection, "case:live")

    assert "processing_version=?" in connection.query
    assert connection.params == ("case:live", weekly_core.VERSION)
    assert outputs[0]["payload"]["bos_direction"] == "BOS_UP"
