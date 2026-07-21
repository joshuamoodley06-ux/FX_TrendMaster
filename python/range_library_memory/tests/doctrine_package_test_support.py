"""Fixtures shared by doctrine package runtime tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.doctrine_pipeline import insert_script, review_sample

CASE_REF = "CASE-DOCTRINE-PACKAGE"
SYMBOL = "XAUUSD"


def master_map(structural_hash: str = "structure-v1") -> dict:
    ranges = [{
        "id": f"weekly-{index}",
        "node_type": "RANGE",
        "structure_layer": "WEEKLY",
        "source_refs": [{"case_ref": CASE_REF, "source_record_id": f"source-{index}"}],
        "analysis_enrichments": {},
        "children": [],
    } for index in range(6)]
    return {
        "schema_version": "master_map_v1",
        "symbol": SYMBOL,
        "structural_content_hash": structural_hash,
        "trusted_root": {"id": "trusted-root", "node_type": "ROOT", "children": ranges},
        "review_root": {"id": "review-root", "node_type": "ROOT", "children": []},
    }


def create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)")
        con.execute(
            "INSERT INTO master_map_outputs(symbol,output_json) VALUES (?,?)",
            (SYMBOL, json.dumps(master_map(), sort_keys=True)),
        )


def package_source(version: str, logic_label: str) -> str:
    return f'''FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_structure"
VERSION_LABEL = "{version}"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 10


def run(context):
    rows = []
    directions = ["UP", "DOWN", "UP", "DOWN", None, "UP"]
    chronology = ["VALID", "VALID", "PENDING", "VALID", "PENDING", "VALID"]
    statuses = ["COMPLETE", "COMPLETE", "PENDING", "COMPLETE", "NEEDS_REVIEW", "COMPLETE"]
    for index, node in enumerate(context.selected_ranges(layer="WEEKLY")):
        rows.append({{
            "canonical_range_id": node["id"],
            "processing_status": statuses[index],
            "payload": {{
                "logic_label": "{logic_label}",
                "chronology": chronology[index],
                "bos_direction": directions[index],
                "approved_memory_seen": bool(context.approved_memory(node["id"])),
            }},
        }})
    return {{"outputs": rows}}
'''


def insert_package(db_path: Path, source: str, version: str) -> dict:
    return insert_script(
        db_path,
        script_key="weekly_structure",
        display_name="Weekly Structure Package",
        version_label=version,
        source_code=source,
        adapter_key="weekly_chronology_bos_v2",
        execution_order=10,
        description="Package runtime integration test",
    )


def approve_all(db_path: Path, run_state: dict) -> None:
    for sample in run_state["samples"]:
        review_sample(
            db_path,
            run_id=run_state["run"]["run_id"],
            canonical_range_id=sample["canonical_range_id"],
            decision="APPROVED",
        )


def stored_master_map(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as con:
        row = con.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol=?", (SYMBOL,)
        ).fetchone()
    return json.loads(row[0])
