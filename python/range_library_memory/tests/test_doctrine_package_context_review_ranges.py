from __future__ import annotations

from range_library_memory.doctrine_package_context import DoctrinePackageContext


CASE = "CASE"


def _range(identity: str, layer: str, *, children: list[dict] | None = None, memory: dict | None = None) -> dict:
    return {
        "id": identity,
        "node_type": "RANGE",
        "structure_layer": layer,
        "source_refs": [{"case_ref": CASE, "source_record_id": identity}],
        "analysis_enrichments": memory or {},
        "children": children or [],
    }


def test_review_ranges_are_visible_without_becoming_trusted_or_approved_memory(tmp_path) -> None:
    trusted_daily = _range("daily-trusted", "DAILY")
    trusted_weekly = _range(
        "weekly-1",
        "WEEKLY",
        children=[trusted_daily],
        memory={
            "weekly_structure": {
                "processing_status": "COMPLETE",
                "payload": {"bos_direction": "BOS_UP"},
            },
        },
    )
    review_daily = _range("daily-review", "DAILY")
    review_weekly = _range("weekly-1", "WEEKLY", children=[review_daily])
    unlinked_review = _range("daily-orphan", "DAILY")

    master_map = {
        "trusted_root": {
            "id": "trusted",
            "node_type": "ROOT",
            "children": [trusted_weekly],
        },
        "review_root": {
            "id": "review",
            "node_type": "ROOT",
            "children": [review_weekly],
            "unlinked_review_children": [unlinked_review],
        },
    }
    context = DoctrinePackageContext(
        master_map=master_map,
        source_db=tmp_path / "unused.sqlite3",
        case_ref=CASE,
        symbol="XAUUSD",
        structural_content_hash="structure-v1",
    )

    assert [row["id"] for row in context.selected_ranges(layer="DAILY")] == [
        "daily-trusted",
    ]
    assert sorted(row["id"] for row in context.review_ranges(layer="DAILY")) == [
        "daily-orphan",
        "daily-review",
    ]
    assert context.approved_memory("weekly-1")["weekly_structure"]["payload"] == {
        "bos_direction": "BOS_UP",
    }
    assert context.approved_memory("daily-review") == {}
