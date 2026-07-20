from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from range_library_memory import doctrine_pipeline
from range_library_memory import weekly_chronology_bos as weekly_core
from range_library_memory.weekly_chronology_bos_v2_registry import _project_candidate_results


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


class ProjectionCore:
    @staticmethod
    def parse_time(value: Any):
        if not value:
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def project_result_into_node(node: dict[str, Any], row: dict[str, Any]) -> None:
        node["script1_chronology"] = row["chronology_result"]
        node["script1_bos_direction"] = row["bos_direction"]
        node["script1_processing_status"] = row["processing_status"]


def test_v1_doctrine_reader_remains_explicitly_version_scoped() -> None:
    connection = FakeConnection()
    outputs = doctrine_pipeline._weekly_outputs(connection, "case:live")
    assert "processing_version=?" in connection.query
    assert connection.params == ("case:live", weekly_core.VERSION)
    assert outputs[0]["payload"]["bos_direction"] == "BOS_UP"


def test_validation_sampling_preserves_canonical_input_order() -> None:
    rows = [
        {"canonical_range_id": "weekly-later-id", "processing_status": "COMPLETE",
         "payload": {"chronology": "RL_TO_RH", "bos_direction": "BOS_UP"}},
        {"canonical_range_id": "weekly-earlier-id", "processing_status": "COMPLETE",
         "payload": {"chronology": "RH_TO_RL", "bos_direction": "BOS_DOWN"}},
    ]
    sample = doctrine_pipeline._sample(rows)
    assert [row["canonical_range_id"] for row in sample] == ["weekly-later-id", "weekly-earlier-id"]


def test_pending_v2_projection_sorts_without_replacing_approved_enrichment() -> None:
    approved = {"weekly_structure": {"version_id": "v1",
        "payload": {"chronology": "RL_TO_RH", "bos_direction": "BOS_UP"}}}
    later = {"id": "weekly-2", "structure_layer": "WEEKLY",
        "range_high_time": "2026-03-09T00:00:00Z", "range_low_time": "2026-03-02T00:00:00Z",
        "analysis_enrichments": approved.copy(), "children": []}
    earlier = {"id": "weekly-1", "structure_layer": "WEEKLY",
        "range_high_time": "2026-01-12T00:00:00Z", "range_low_time": "2026-01-05T00:00:00Z",
        "analysis_enrichments": approved.copy(), "children": []}
    master = {"trusted_root": {"id": "root", "children": [later, earlier]},
        "root": {"id": "root-copy", "children": []}, "review_root": {"id": "review", "children": []}}
    results = [
        {"canonical_range_id": "weekly-2", "chronology_result": "RL_TO_RH",
         "chronology_start_time": "2026-03-02T00:00:00Z", "chronology_end_time": "2026-03-09T00:00:00Z",
         "bos_direction": "BOS_UP", "processing_status": "COMPLETE"},
        {"canonical_range_id": "weekly-1", "chronology_result": "RH_TO_RL",
         "chronology_start_time": "2026-01-05T00:00:00Z", "chronology_end_time": "2026-01-12T00:00:00Z",
         "bos_direction": "BOS_DOWN", "processing_status": "COMPLETE"},
    ]
    _project_candidate_results(ProjectionCore, master, results)
    children = master["trusted_root"]["children"]
    assert [node["id"] for node in children] == ["weekly-1", "weekly-2"]
    assert children[0]["script1_bos_direction"] == "BOS_DOWN"
    assert children[0]["analysis_enrichments"]["weekly_structure"]["version_id"] == "v1"
    assert master["analysis"]["weekly_script1_candidate"]["sequence_order"] == "RANGE_DEFINED_AT_ASC"
