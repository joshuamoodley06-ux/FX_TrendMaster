from __future__ import annotations

import json
import sqlite3

from range_library_memory import daily_inherited_doctrine as inherited


class _Pipeline:
    @staticmethod
    def stable_json(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def sha(value):
        import hashlib
        return hashlib.sha256(_Pipeline.stable_json(value).encode()).hexdigest()

    @staticmethod
    def now():
        return "2026-07-24T00:00:00Z"


def _master():
    return {
        "trusted_root": {
            "node_type": "SYMBOL",
            "children": [
                {
                    "node_type": "RANGE",
                    "id": "weekly-1",
                    "structure_layer": "WEEKLY",
                    "source_refs": [{"case_ref": "case:live"}],
                    "children": [
                        {
                            "node_type": "RANGE",
                            "id": "daily-1",
                            "structure_layer": "DAILY",
                            "source_refs": [{"case_ref": "case:live"}],
                            "children": [],
                        }
                    ],
                }
            ],
        }
    }


def test_inherited_daily_output_projects_without_registering_a_daily_approval_script() -> None:
    master = _master()
    counts = inherited._project_stage(
        pipeline=_Pipeline(),
        master_map=master,
        stage_key="daily_structure",
        source_key="weekly_structure",
        source_version={"version_id": "weekly-v3", "version_label": "3"},
        outputs=[
            {
                "canonical_range_id": "daily-1",
                "processing_status": "COMPLETE",
                "payload": {
                    "chronology": "RL_TO_RH",
                    "bos_direction": "BOS_UP",
                },
            }
        ],
    )

    daily = master["trusted_root"]["children"][0]["children"][0]
    memory = daily["analysis_enrichments"]["daily_structure"]
    assert counts == {"outputs": 1, "complete": 1, "pending": 0, "needs_review": 0}
    assert memory["processing_status"] == "COMPLETE"
    assert memory["payload"]["bos_direction"] == "BOS_UP"
    assert memory["payload"]["inherited_from_weekly_script"] == "weekly_structure"
    assert memory["payload"]["inherited_target_layer"] == "DAILY"
    assert memory["adapter_key"] == inherited.INHERITED_ADAPTER


def test_daily_results_remain_native_without_touching_weekly_node() -> None:
    master = _master()
    daily = master["trusted_root"]["children"][0]["children"][0]
    daily["analysis_enrichments"] = {
        "daily_structure": {
            "version_id": "inherited:weekly-v3",
            "version_label": "3",
            "adapter_key": inherited.INHERITED_ADAPTER,
            "output_hash": "structure",
            "processing_status": "COMPLETE",
            "payload": {"chronology": "RH_TO_RL", "bos_direction": "BOS_DOWN"},
        },
        "daily_reclaim": {
            "version_id": "inherited:weekly-reclaim-v2",
            "version_label": "2",
            "adapter_key": inherited.INHERITED_ADAPTER,
            "output_hash": "reclaim",
            "processing_status": "COMPLETE",
            "payload": {"reclaim_status": "ABANDONED_THEN_RECLAIMED"},
        },
        "daily_profile_classification": {
            "version_id": "inherited:weekly-profile-v1",
            "version_label": "1",
            "adapter_key": inherited.INHERITED_ADAPTER,
            "output_hash": "profile",
            "processing_status": "COMPLETE",
            "payload": {"profile_classification": "S&D", "profile_badge": "◆ S&D"},
        },
    }

    weekly = master["trusted_root"]["children"][0]
    assert "analysis_enrichments" not in weekly
    assert set(daily["analysis_enrichments"]) == {
        "daily_structure", "daily_reclaim", "daily_profile_classification",
    }


def test_clear_removes_only_inherited_daily_keys() -> None:
    master = _master()
    daily = master["trusted_root"]["children"][0]["children"][0]
    daily["analysis_enrichments"] = {
        "daily_structure": {"payload": {}},
        "other_research": {"payload": {"keep": True}},
    }

    inherited._clear_inherited_daily_memory(master)

    assert daily["analysis_enrichments"] == {
        "other_research": {"payload": {"keep": True}},
    }


def test_persisted_daily_memory_survives_a_fresh_master_map_rebuild() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO master_map_outputs(symbol,output_json) VALUES (?,?)",
        ("XAUUSD", json.dumps(_master(), sort_keys=True)),
    )

    calculated = _master()
    inherited._project_stage(
        pipeline=_Pipeline(),
        master_map=calculated,
        stage_key="daily_structure",
        source_key="weekly_structure",
        source_version={"version_id": "weekly-v3", "version_label": "3"},
        outputs=[{
            "canonical_range_id": "daily-1",
            "processing_status": "COMPLETE",
            "payload": {"chronology": "RL_TO_RH", "bos_direction": "BOS_UP"},
        }],
        connection=connection,
        symbol="XAUUSD",
        case_ref="case:live",
    )

    rebuilt = _master()
    summary = inherited.apply_persisted_inherited_enrichments(
        connection,
        rebuilt,
        symbol="XAUUSD",
    )

    daily = rebuilt["trusted_root"]["children"][0]["children"][0]
    assert summary == {"applied": 1, "needs_review": 0}
    assert daily["analysis_enrichments"]["daily_structure"]["payload"]["bos_direction"] == "BOS_UP"
    assert "weekly_structure" not in daily["analysis_enrichments"]

    stored = json.loads(connection.execute(
        "SELECT output_json FROM master_map_outputs WHERE symbol='XAUUSD'"
    ).fetchone()[0])
    stored_daily = stored["trusted_root"]["children"][0]["children"][0]
    assert stored_daily["analysis_enrichments"]["daily_structure"]["payload"]["bos_direction"] == "BOS_UP"


def test_rebuild_without_inherited_table_does_not_mutate_live_schema() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)"
    )
    master = _master()

    assert inherited.apply_persisted_inherited_enrichments(
        connection, master, symbol="XAUUSD"
    ) == {"applied": 0, "needs_review": 0}
    assert connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (inherited.INHERITED_TABLE,),
    ).fetchone() is None


def test_generic_intraday_projection_preserves_hierarchy_and_is_idempotent() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)"
    )
    master = _master()
    daily = master["trusted_root"]["children"][0]["children"][0]
    daily["parent_range_id"] = "weekly-1"
    daily["source_refs"].append({"case_ref": "case:live", "source_record_id": "662"})
    daily["children"] = [{
        "node_type": "RANGE",
        "id": "intraday-1",
        "structure_layer": "INTRADAY",
        "parent_range_id": "daily-1",
        "source_refs": [{"case_ref": "case:live"}],
        "children": [],
    }]
    connection.execute(
        "INSERT INTO master_map_outputs VALUES (?,?)", ("XAUUSD", json.dumps(master))
    )
    original = json.loads(json.dumps(master))
    inherited._project_stage(
        pipeline=_Pipeline(),
        master_map=master,
        stage_key="intraday_structure",
        source_key="weekly_structure",
        source_version={"version_id": "weekly-v3", "version_label": "3"},
        outputs=[{
            "canonical_range_id": "intraday-1",
            "processing_status": "COMPLETE",
            "payload": {"chronology": "RH_TO_RL", "bos_direction": "BOS_DOWN"},
        }],
        connection=connection,
        symbol="XAUUSD",
        case_ref="case:live",
        target_layer="INTRADAY",
    )
    rebuilt = json.loads(json.dumps(original))
    first = inherited.apply_persisted_inherited_enrichments(
        connection, rebuilt, symbol="XAUUSD"
    )
    second = inherited.apply_persisted_inherited_enrichments(
        connection, rebuilt, symbol="XAUUSD"
    )
    rebuilt_daily = rebuilt["trusted_root"]["children"][0]["children"][0]
    intraday = rebuilt_daily["children"][0]
    assert first == second == {"applied": 1, "needs_review": 0}
    assert intraday["structure_layer"] == "INTRADAY"
    assert intraday["parent_range_id"] == "daily-1"
    assert rebuilt_daily["parent_range_id"] == "weekly-1"
    assert rebuilt_daily["source_refs"] == original["trusted_root"]["children"][0]["children"][0]["source_refs"]
    assert [node["id"] for node in rebuilt["trusted_root"]["children"]] == ["weekly-1"]
    assert set(intraday["analysis_enrichments"]) == {"intraday_structure"}


def test_case_symbol_version_replacement_and_review_status_are_scoped() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO master_map_outputs VALUES (?,?)", ("XAUUSD", json.dumps(_master()))
    )
    master = _master()
    for version, status in (("weekly-v3", "COMPLETE"), ("weekly-v4", "NEEDS_REVIEW")):
        inherited._project_stage(
            pipeline=_Pipeline(),
            master_map=master,
            stage_key="daily_structure",
            source_key="weekly_structure",
            source_version={"version_id": version, "version_label": version[-1]},
            outputs=[{
                "canonical_range_id": "daily-1",
                "processing_status": status,
                "payload": {"bos_direction": "BOS_UP"},
            }],
            connection=connection,
            symbol="XAUUSD",
            case_ref="case:live",
        )
    row = connection.execute(
        f"SELECT * FROM {inherited.INHERITED_TABLE}"
    ).fetchone()
    assert connection.execute(
        f"SELECT COUNT(*) FROM {inherited.INHERITED_TABLE}"
    ).fetchone()[0] == 1
    assert row["source_version_id"] == "weekly-v4"
    assert row["processing_status"] == "NEEDS_REVIEW"

    other_case = _master()
    other_daily = other_case["trusted_root"]["children"][0]["children"][0]
    other_daily["source_refs"] = [{"case_ref": "case:other"}]
    assert inherited.apply_persisted_inherited_enrichments(
        connection, other_case, symbol="XAUUSD"
    ) == {"applied": 0, "needs_review": 0}
    assert "analysis_enrichments" not in other_daily
    assert inherited.apply_persisted_inherited_enrichments(
        connection, _master(), symbol="EURUSD"
    ) == {"applied": 0, "needs_review": 0}

    rebuilt = _master()
    assert inherited.apply_persisted_inherited_enrichments(
        connection, rebuilt, symbol="XAUUSD"
    ) == {"applied": 1, "needs_review": 1}
