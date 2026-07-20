"""Doctrine registry compatibility for independent Weekly Script 1 versions."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .weekly_chronology_bos_v2 import install as install_v2


def install(core: Any, pipeline: Any) -> None:
    """Register v2 and keep the original v1 output reader version-scoped."""
    install_v2(core, pipeline)
    if getattr(pipeline, "_weekly_v2_registry_installed", False):
        return

    def weekly_outputs_v1(connection: Any, case_ref: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM weekly_script1_results "
            "WHERE case_ref=? AND processing_version=? "
            "ORDER BY chronology_end_time,chronology_start_time,canonical_range_id",
            (case_ref, core.VERSION),
        ).fetchall()
        return [{
            "canonical_range_id": row["canonical_range_id"],
            "input_hash": row["source_structural_hash"] or row["result_hash"],
            "processing_status": row["processing_status"],
            "payload": {
                "chronology": row["chronology_result"],
                "bos_direction": row["bos_direction"],
                "bos_time": row["bos_candle_time"],
                "reasons": json.loads(row["reason_codes_json"]),
            },
            "output_hash": row["result_hash"],
        } for row in rows]

    def ordered_sample(rows: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Mapping[str, Any]]:
        chosen: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            payload = row["payload"]
            key = f"{payload.get('chronology')}|{payload.get('bos_direction')}|{row['processing_status']}"
            if key not in seen:
                chosen.append(row)
                seen.add(key)
            if len(chosen) == limit:
                return chosen
        for row in rows:
            if row not in chosen:
                chosen.append(row)
            if len(chosen) == limit:
                break
        return chosen

    pipeline._weekly_outputs = weekly_outputs_v1
    pipeline._sample = ordered_sample
    pipeline._weekly_v2_registry_installed = True
