"""Persistent, adapter-driven doctrine script registry and incremental pipeline."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .db import connect
from .inspection import require_existing_db

CONTRACT = "doctrine_pipeline_v2"
WEEKLY_ADAPTER = "weekly_chronology_bos_v1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS doctrine_scripts (
 script_id TEXT PRIMARY KEY, script_key TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 description TEXT, execution_order INTEGER NOT NULL, status TEXT NOT NULL,
 current_approved_version_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS doctrine_script_versions (
 version_id TEXT PRIMARY KEY, script_id TEXT NOT NULL, version_label TEXT NOT NULL,
 content_hash TEXT NOT NULL, source_code TEXT NOT NULL, adapter_key TEXT NOT NULL,
 input_contract_version TEXT NOT NULL, output_contract_version TEXT NOT NULL,
 created_at TEXT NOT NULL, approved_at TEXT, rejected_at TEXT,
 UNIQUE(script_id,content_hash));
CREATE TABLE IF NOT EXISTS doctrine_script_runs (
 run_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, case_ref TEXT NOT NULL, symbol TEXT NOT NULL,
 input_structural_hash TEXT NOT NULL, run_status TEXT NOT NULL, approval_status TEXT NOT NULL,
 publication_status TEXT NOT NULL, eligible_count INTEGER NOT NULL, analysed_count INTEGER NOT NULL,
 sample_count INTEGER NOT NULL, approval_count INTEGER NOT NULL, executed_at TEXT NOT NULL,
 completed_at TEXT, published_at TEXT, error_text TEXT,
 UNIQUE(version_id,case_ref,symbol,input_structural_hash));
CREATE TABLE IF NOT EXISTS doctrine_validation_samples (
 run_id TEXT NOT NULL, canonical_range_id TEXT NOT NULL, sample_order INTEGER NOT NULL,
 sample_fingerprint TEXT NOT NULL, decision TEXT NOT NULL, decided_at TEXT,
 PRIMARY KEY(run_id,canonical_range_id), UNIQUE(run_id,sample_order));
CREATE TABLE IF NOT EXISTS doctrine_range_processing (
 version_id TEXT NOT NULL, canonical_range_id TEXT NOT NULL, case_ref TEXT NOT NULL,
 symbol TEXT NOT NULL, input_record_hash TEXT NOT NULL, output_hash TEXT,
 processing_status TEXT NOT NULL, processed_at TEXT NOT NULL, run_id TEXT NOT NULL,
 PRIMARY KEY(version_id,canonical_range_id,input_record_hash));
CREATE TABLE IF NOT EXISTS doctrine_enrichments (
 version_id TEXT NOT NULL, canonical_range_id TEXT NOT NULL, namespace TEXT NOT NULL,
 payload_json TEXT NOT NULL, output_hash TEXT NOT NULL, published_at TEXT, active INTEGER NOT NULL,
 PRIMARY KEY(version_id,canonical_range_id,namespace));
"""


class DoctrinePipelineError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value: Any) -> str:
    raw = value if isinstance(value, str) else stable_json(value)
    return hashlib.sha256(raw.encode()).hexdigest()


def normalize_source(source: str) -> str:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n").strip()
    return "\n".join(line.rstrip() for line in normalized.split("\n")) + "\n"


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)


def insert_script(
    db_path: str | Path,
    *,
    script_key: str,
    display_name: str,
    version_label: str,
    source_code: str,
    adapter_key: str,
    execution_order: int = 100,
    description: str | None = None,
) -> dict[str, Any]:
    if adapter_key not in {WEEKLY_ADAPTER}:
        raise DoctrinePipelineError(f"Unregistered doctrine adapter: {adapter_key}")
    key = script_key.strip().lower().replace(" ", "_")
    source = normalize_source(source_code)
    content_hash = sha(source)
    stamp = now()
    with connect(require_existing_db(db_path)) as con:
        ensure_schema(con)
        script = con.execute("SELECT * FROM doctrine_scripts WHERE script_key=?", (key,)).fetchone()
        if script is None:
            script_id = str(uuid.uuid4())
            con.execute(
                "INSERT INTO doctrine_scripts VALUES (?,?,?,?,?,'PENDING_APPROVAL',NULL,?,?)",
                (script_id, key, display_name, description, int(execution_order), stamp, stamp),
            )
            current_approved_version_id = None
        else:
            script_id = str(script["script_id"])
            current_approved_version_id = script["current_approved_version_id"]
            con.execute(
                "UPDATE doctrine_scripts SET display_name=?,description=?,execution_order=?,updated_at=? WHERE script_id=?",
                (display_name, description, int(execution_order), stamp, script_id),
            )
        existing = con.execute(
            "SELECT * FROM doctrine_script_versions WHERE script_id=? AND content_hash=?",
            (script_id, content_hash),
        ).fetchone()
        if existing is not None:
            con.commit()
            return {"created": False, **dict(existing), "script_key": key}
        version_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO doctrine_script_versions VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)",
            (version_id, script_id, version_label, content_hash, source, adapter_key, CONTRACT, CONTRACT, stamp),
        )
        next_status = "APPROVED" if current_approved_version_id else "PENDING_APPROVAL"
        con.execute(
            "UPDATE doctrine_scripts SET status=?,updated_at=? WHERE script_id=?",
            (next_status, stamp, script_id),
        )
        con.commit()
    return {
        "created": True,
        "script_id": script_id,
        "version_id": version_id,
        "script_key": key,
        "content_hash": content_hash,
        "version_label": version_label,
        "adapter_key": adapter_key,
    }


def list_scripts(db_path: str | Path) -> list[dict[str, Any]]:
    with connect(require_existing_db(db_path)) as con:
        ensure_schema(con)
        rows = con.execute(
            """SELECT s.*,v.version_id,v.version_label,v.content_hash,v.adapter_key,
                      CASE WHEN v.approved_at IS NOT NULL THEN 'APPROVED'
                           WHEN v.rejected_at IS NOT NULL THEN 'REJECTED'
                           ELSE 'PENDING_APPROVAL' END AS latest_version_status
               FROM doctrine_scripts s
               LEFT JOIN doctrine_script_versions v ON v.version_id=(
                 SELECT v2.version_id FROM doctrine_script_versions v2
                 WHERE v2.script_id=s.script_id ORDER BY v2.created_at DESC LIMIT 1)
               ORDER BY s.execution_order,s.script_key"""
        )
        return [dict(row) for row in rows]


def show_script(db_path: str | Path, script_key: str) -> dict[str, Any]:
    with connect(require_existing_db(db_path)) as con:
        ensure_schema(con)
        row = con.execute("SELECT * FROM doctrine_scripts WHERE script_key=?", (script_key,)).fetchone()
        if row is None:
            raise DoctrinePipelineError("Doctrine script not found.")
        result = dict(row)
        result["versions"] = [
            dict(version)
            for version in con.execute(
                "SELECT * FROM doctrine_script_versions WHERE script_id=? ORDER BY created_at",
                (row["script_id"],),
            )
        ]
        result["runs"] = []
        for run in con.execute(
            """SELECT r.* FROM doctrine_script_runs r
               JOIN doctrine_script_versions v USING(version_id)
               WHERE v.script_id=? ORDER BY r.executed_at DESC""",
            (row["script_id"],),
        ):
            result["runs"].append(_run_state(con, str(run["run_id"])))
        return result


def retire_script(db_path: str | Path, script_key: str) -> None:
    with connect(require_existing_db(db_path)) as con:
        ensure_schema(con)
        con.execute(
            "UPDATE doctrine_scripts SET status='RETIRED',updated_at=? WHERE script_key=?",
            (now(), script_key),
        )
        con.commit()


def _master_map(con: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT output_json FROM master_map_outputs WHERE UPPER(symbol)=?",
        (symbol.upper(),),
    ).fetchone()
    if row is None:
        raise DoctrinePipelineError("Persisted Master Map is missing.")
    return json.loads(row["output_json"])


def _sample(rows: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Mapping[str, Any]]:
    chosen: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: str(item["canonical_range_id"])):
        payload = row["payload"]
        key = f"{payload.get('chronology')}|{payload.get('bos_direction')}|{row['processing_status']}"
        if key not in seen:
            chosen.append(row)
            seen.add(key)
        if len(chosen) == limit:
            return chosen
    for row in sorted(rows, key=lambda item: str(item["canonical_range_id"])):
        if row not in chosen:
            chosen.append(row)
        if len(chosen) == limit:
            break
    return chosen


def _weekly_outputs(con: sqlite3.Connection, case_ref: str) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT * FROM weekly_script1_results WHERE case_ref=? ORDER BY canonical_range_id",
        (case_ref,),
    ).fetchall()
    return [
        {
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
        }
        for row in rows
    ]


def _run_state(con: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run = con.execute("SELECT * FROM doctrine_script_runs WHERE run_id=?", (run_id,)).fetchone()
    if run is None:
        raise DoctrinePipelineError("Doctrine run not found.")
    samples: list[dict[str, Any]] = []
    for row in con.execute(
        """SELECT sample.*,processing.processing_status,enrichment.payload_json,enrichment.output_hash
           FROM doctrine_validation_samples sample
           LEFT JOIN doctrine_script_runs run ON run.run_id=sample.run_id
           LEFT JOIN doctrine_range_processing processing
             ON processing.run_id=sample.run_id
            AND processing.canonical_range_id=sample.canonical_range_id
           LEFT JOIN doctrine_enrichments enrichment
             ON enrichment.version_id=run.version_id
            AND enrichment.canonical_range_id=sample.canonical_range_id
           WHERE sample.run_id=? ORDER BY sample.sample_order""",
        (run_id,),
    ):
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json") or "{}")
        samples.append(value)
    return {"run": dict(run), "samples": samples}


def _approved_version(con: sqlite3.Connection, version_id: str) -> bool:
    row = con.execute(
        """SELECT 1 FROM doctrine_scripts s
           JOIN doctrine_script_versions v ON v.script_id=s.script_id
           WHERE v.version_id=? AND s.status='APPROVED'
             AND s.current_approved_version_id=v.version_id""",
        (version_id,),
    ).fetchone()
    return row is not None


def _publish_version(con: sqlite3.Connection, version_id: str, symbol: str, stamp: str) -> None:
    con.execute(
        """UPDATE doctrine_script_runs
           SET approval_status='APPROVED',publication_status='PUBLISHED',
               published_at=COALESCE(published_at,?)
           WHERE version_id=?""",
        (stamp, version_id),
    )
    con.execute(
        "UPDATE doctrine_enrichments SET active=1,published_at=COALESCE(published_at,?) WHERE version_id=?",
        (stamp, version_id),
    )
    adapter = con.execute(
        "SELECT adapter_key FROM doctrine_script_versions WHERE version_id=?",
        (version_id,),
    ).fetchone()
    if adapter and adapter["adapter_key"] == WEEKLY_ADAPTER:
        con.execute(
            """UPDATE weekly_script1_results SET review_status='APPROVED'
               WHERE canonical_range_id IN (
                 SELECT canonical_range_id FROM doctrine_enrichments WHERE version_id=?)""",
            (version_id,),
        )
        from .weekly_chronology_bos import project_stored_results

        output = _master_map(con, symbol)
        project_stored_results(con, output, symbol=symbol)
    else:
        output = _master_map(con, symbol)
    apply_approved_enrichments(con, output, symbol=symbol)


def run_version(
    db_path: str | Path,
    *,
    version_id: str,
    case_ref: str,
    symbol: str,
    source_db: str | Path,
) -> dict[str, Any]:
    from .weekly_chronology_bos import build_weekly_chronology_bos

    db = require_existing_db(db_path)
    symbol = symbol.upper()
    with connect(db) as con:
        ensure_schema(con)
        version = con.execute(
            """SELECT v.*,s.script_key,s.status,s.current_approved_version_id
               FROM doctrine_script_versions v JOIN doctrine_scripts s USING(script_id)
               WHERE version_id=?""",
            (version_id,),
        ).fetchone()
        if version is None:
            raise DoctrinePipelineError("Doctrine version not found.")
        master = _master_map(con, symbol)
        structural = str(master.get("structural_content_hash") or "")
        run_id = sha([version_id, case_ref, symbol, structural])
        existing = con.execute("SELECT * FROM doctrine_script_runs WHERE run_id=?", (run_id,)).fetchone()
        if existing is not None:
            if _approved_version(con, version_id) and existing["publication_status"] != "PUBLISHED":
                _publish_version(con, version_id, symbol, now())
                con.commit()
            return {**_run_state(con, run_id), "reused": True}

    if version["adapter_key"] == WEEKLY_ADAPTER:
        build_weekly_chronology_bos(db, source_db=source_db, case_ref=case_ref, symbol=symbol)

    with connect(db) as con:
        ensure_schema(con)
        outputs = _weekly_outputs(con, case_ref)
        stamp = now()
        is_approved = _approved_version(con, version_id)
        samples = [] if is_approved else _sample(outputs)
        approval_status = "APPROVED" if is_approved else "PENDING"
        publication_status = "PUBLISHED" if is_approved else "UNPUBLISHED"
        published_at = stamp if is_approved else None
        con.execute(
            """INSERT INTO doctrine_script_runs(
                 run_id,version_id,case_ref,symbol,input_structural_hash,run_status,
                 approval_status,publication_status,eligible_count,analysed_count,
                 sample_count,approval_count,executed_at,completed_at,published_at,error_text)
               VALUES (?,?,?,?,?,'COMPLETE',?,?,?,?,?,?,?,?,?,NULL)""",
            (
                run_id,
                version_id,
                case_ref,
                symbol,
                structural,
                approval_status,
                publication_status,
                len(outputs),
                len(outputs),
                len(samples),
                0,
                stamp,
                stamp,
                published_at,
            ),
        )
        for row in outputs:
            con.execute(
                "INSERT OR IGNORE INTO doctrine_range_processing VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    version_id,
                    row["canonical_range_id"],
                    case_ref,
                    symbol,
                    row["input_hash"],
                    row["output_hash"],
                    row["processing_status"],
                    stamp,
                    run_id,
                ),
            )
            con.execute(
                "INSERT OR REPLACE INTO doctrine_enrichments VALUES (?,?,?,?,?,?,?)",
                (
                    version_id,
                    row["canonical_range_id"],
                    version["script_key"],
                    stable_json(row["payload"]),
                    row["output_hash"],
                    published_at,
                    1 if is_approved else 0,
                ),
            )
        for order, row in enumerate(samples):
            con.execute(
                "INSERT INTO doctrine_validation_samples VALUES (?,?,?,?, 'PENDING',NULL)",
                (run_id, row["canonical_range_id"], order, sha([row["canonical_range_id"], row["output_hash"]])),
            )
        if is_approved:
            _publish_version(con, version_id, symbol, stamp)
        con.commit()
        return {**_run_state(con, run_id), "reused": False}


def review_sample(
    db_path: str | Path,
    *,
    run_id: str,
    canonical_range_id: str,
    decision: str,
) -> dict[str, Any]:
    decision = decision.upper()
    stamp = now()
    if decision not in {"APPROVED", "REJECTED"}:
        raise DoctrinePipelineError("Invalid sample decision.")
    with connect(require_existing_db(db_path)) as con:
        ensure_schema(con)
        sample = con.execute(
            "SELECT * FROM doctrine_validation_samples WHERE run_id=? AND canonical_range_id=?",
            (run_id, canonical_range_id),
        ).fetchone()
        if sample is None:
            raise DoctrinePipelineError("Validation sample not found.")
        if sample["decision"] not in {"PENDING", decision}:
            raise DoctrinePipelineError("Validation sample already has a different decision.")
        if sample["decision"] == "PENDING":
            con.execute(
                "UPDATE doctrine_validation_samples SET decision=?,decided_at=? WHERE run_id=? AND canonical_range_id=?",
                (decision, stamp, run_id, canonical_range_id),
            )
        decisions = [
            row[0]
            for row in con.execute(
                "SELECT decision FROM doctrine_validation_samples WHERE run_id=?",
                (run_id,),
            )
        ]
        approved = decisions.count("APPROVED")
        rejected = "REJECTED" in decisions
        run = con.execute("SELECT * FROM doctrine_script_runs WHERE run_id=?", (run_id,)).fetchone()
        version_id = str(run["version_id"])
        script = con.execute(
            """SELECT s.* FROM doctrine_scripts s
               JOIN doctrine_script_versions v ON v.script_id=s.script_id
               WHERE v.version_id=?""",
            (version_id,),
        ).fetchone()
        if rejected:
            con.execute(
                "UPDATE doctrine_script_runs SET approval_status='REJECTED',approval_count=? WHERE run_id=?",
                (approved, run_id),
            )
            con.execute(
                "UPDATE doctrine_script_versions SET rejected_at=? WHERE version_id=?",
                (stamp, version_id),
            )
            next_status = "APPROVED" if script["current_approved_version_id"] else "REJECTED"
            con.execute(
                "UPDATE doctrine_scripts SET status=?,updated_at=? WHERE script_id=?",
                (next_status, stamp, script["script_id"]),
            )
        elif decisions and approved == len(decisions):
            con.execute(
                "UPDATE doctrine_script_versions SET approved_at=COALESCE(approved_at,?),rejected_at=NULL WHERE version_id=?",
                (stamp, version_id),
            )
            con.execute(
                "UPDATE doctrine_scripts SET status='APPROVED',current_approved_version_id=?,updated_at=? WHERE script_id=?",
                (version_id, stamp, script["script_id"]),
            )
            con.execute(
                "UPDATE doctrine_script_runs SET approval_count=? WHERE run_id=?",
                (approved, run_id),
            )
            _publish_version(con, version_id, str(run["symbol"]), stamp)
        else:
            con.execute(
                "UPDATE doctrine_script_runs SET approval_count=? WHERE run_id=?",
                (approved, run_id),
            )
        con.commit()
        return dict(con.execute("SELECT * FROM doctrine_script_runs WHERE run_id=?", (run_id,)).fetchone())


def apply_approved_enrichments(
    con: sqlite3.Connection,
    master_map: dict[str, Any],
    *,
    symbol: str,
) -> None:
    ensure_schema(con)
    rows = con.execute(
        """SELECT e.*,v.version_label,v.adapter_key,s.script_key
           FROM doctrine_enrichments e
           JOIN doctrine_script_versions v USING(version_id)
           JOIN doctrine_scripts s USING(script_id)
           WHERE e.active=1 AND s.status='APPROVED'
             AND s.current_approved_version_id=e.version_id
           ORDER BY s.execution_order,s.script_key"""
    ).fetchall()
    managed_keys = {
        str(row["script_key"])
        for row in con.execute("SELECT script_key FROM doctrine_scripts")
    }
    by_id: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_id.setdefault(str(row["canonical_range_id"]), []).append(row)

    def visit(node: dict[str, Any]) -> None:
        existing = node.get("analysis_enrichments")
        if isinstance(existing, dict):
            for key in managed_keys:
                existing.pop(key, None)
            if not existing:
                node.pop("analysis_enrichments", None)
        for row in by_id.get(str(node.get("id") or ""), []):
            node.setdefault("analysis_enrichments", {})[row["script_key"]] = {
                "version_id": row["version_id"],
                "version_label": row["version_label"],
                "adapter_key": row["adapter_key"],
                "output_hash": row["output_hash"],
                "payload": json.loads(row["payload_json"]),
            }
        for child in node.get("children", []):
            if isinstance(child, dict):
                visit(child)

    for key in ("root", "trusted_root", "review_root"):
        if isinstance(master_map.get(key), dict):
            visit(master_map[key])
    master_map.setdefault("analysis", {})["doctrine_scripts"] = [
        {
            "script_key": row["script_key"],
            "version_id": row["version_id"],
            "version_label": row["version_label"],
            "adapter_key": row["adapter_key"],
        }
        for row in con.execute(
            """SELECT s.script_key,v.version_id,v.version_label,v.adapter_key
               FROM doctrine_scripts s
               JOIN doctrine_script_versions v ON v.version_id=s.current_approved_version_id
               WHERE s.status='APPROVED' ORDER BY s.execution_order,s.script_key"""
        )
    ]
    con.execute(
        "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
        (json.dumps(master_map, sort_keys=True), symbol.upper()),
    )


def run_active_pipeline(
    db_path: str | Path,
    *,
    case_ref: str,
    symbol: str,
    source_db: str | Path,
) -> dict[str, Any]:
    summary = {
        "active_scripts": 0,
        "ranges_considered": 0,
        "processed": 0,
        "skipped_unchanged": 0,
        "needs_review": 0,
        "failed": 0,
        "outputs_published": 0,
    }
    with connect(require_existing_db(db_path)) as con:
        ensure_schema(con)
        versions = [
            dict(row)
            for row in con.execute(
                """SELECT v.version_id FROM doctrine_scripts s
                   JOIN doctrine_script_versions v ON v.version_id=s.current_approved_version_id
                   WHERE s.status='APPROVED' ORDER BY s.execution_order,s.script_key"""
            )
        ]
    summary["active_scripts"] = len(versions)
    for version in versions:
        result = run_version(
            db_path,
            version_id=version["version_id"],
            case_ref=case_ref,
            symbol=symbol,
            source_db=source_db,
        )
        run = result["run"]
        summary["ranges_considered"] += int(run["eligible_count"])
        if result.get("reused"):
            summary["skipped_unchanged"] += int(run["analysed_count"])
        else:
            summary["processed"] += int(run["analysed_count"])
    with connect(require_existing_db(db_path)) as con:
        apply_approved_enrichments(con, _master_map(con, symbol.upper()), symbol=symbol)
        con.commit()
        summary["outputs_published"] = int(
            con.execute(
                """SELECT COUNT(*) FROM doctrine_enrichments e
                   JOIN doctrine_scripts s ON s.script_key=e.namespace
                   WHERE e.active=1 AND s.status='APPROVED'
                     AND s.current_approved_version_id=e.version_id"""
            ).fetchone()[0]
        )
    return summary
