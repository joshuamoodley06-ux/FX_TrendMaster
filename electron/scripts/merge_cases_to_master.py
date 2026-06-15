"""
Merge two raw mapping cases into XAUUSD_MASTER_2019_2026 on the VPS.
Dedupes structural ranges by layer + H/L + start date; remaps parent/child IDs.
"""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

BASE = "https://api01.apexcoastalrentals.co.za"
SYMBOL = "XAUUSD"
MASTER_NAME = "XAUUSD_MASTER_2019_2026"

SOURCES = [
    ("6d89e12c-fe63-4d31-ab9e-5678b0e6c00d", "XAUUSD 2019 Q3-2020 Q1"),
    ("554bde23-5d0e-4142-948d-e91f80e2195a", "XAUUSD 2020 Q2-2021 Q1"),
]

LAYER_ORDER = ["MACRO", "WEEKLY", "DAILY", "INTRADAY", "MICRO"]

RANGE_SKIP = {
    "id",
    "range_id",
    "created_at",
    "updated_at",
    "case_id",
    "parent_link_status",
    "chain_validation_status",
    "lifecycle_validation_status",
    "warnings",
    "range_high",
    "range_low",
    "layer",
}


def http_get(path: str) -> dict[str, Any]:
    with request.urlopen(f"{BASE}{path}", timeout=120) as resp:
        return json.loads(resp.read().decode())


def http_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        body = exc.read().decode()
        raise RuntimeError(f"POST {path} failed {exc.code}: {body}") from exc


def richness(row: dict[str, Any]) -> int:
    return sum(1 for k, v in row.items() if v is not None and v != "")


def layer_of(row: dict[str, Any]) -> str:
    return str(row.get("structure_layer") or row.get("layer") or "").upper()


def start_key(row: dict[str, Any]) -> str:
    raw = row.get("range_start_time") or row.get("active_from_time") or row.get("range_high_time") or ""
    return str(raw)[:10]


def fingerprint(row: dict[str, Any]) -> tuple[str, float, float, str]:
    hi = round(float(row.get("range_high_price") or row.get("range_high") or 0), 2)
    lo = round(float(row.get("range_low_price") or row.get("range_low") or 0), 2)
    return (layer_of(row), hi, lo, start_key(row))


def fetch_ranges(raw_case_id: str) -> list[dict[str, Any]]:
    data = http_get(
        f"/api/v1/map/ranges?symbol={SYMBOL}&raw_case_id={raw_case_id}&limit=5000"
    )
    return list(data.get("ranges") or [])


def fetch_events(raw_case_id: str) -> list[dict[str, Any]]:
    data = http_get(
        f"/api/v1/map/events?symbol={SYMBOL}&raw_case_id={raw_case_id}&limit=5000"
    )
    return list(data.get("events") or [])


def fetch_raw_export(raw_case_id: str) -> dict[str, Any]:
    return http_get(f"/api/v1/raw-mapping/events/export?case_id={raw_case_id}")


def build_canonical_ranges() -> tuple[list[dict[str, Any]], dict[tuple[str, str], tuple[str, float, float, str]], list[dict[str, Any]]]:
    canon_by_fp: dict[tuple[str, float, float, str], dict[str, Any]] = {}
    id_to_fp: dict[tuple[str, str], tuple[str, float, float, str]] = {}
    dup_log: list[dict[str, Any]] = []

    for raw_case_id, label in SOURCES:
        for row in fetch_ranges(raw_case_id):
            old_id = str(row.get("range_id") or row.get("id") or "")
            if not old_id:
                continue
            fp = fingerprint(row)
            id_to_fp[(raw_case_id, old_id)] = fp
            if fp in canon_by_fp:
                dup_log.append(
                    {
                        "fingerprint": fp,
                        "kept_from": canon_by_fp[fp].get("_merge_source"),
                        "skipped": {"case": label, "range_id": old_id},
                    }
                )
                if richness(row) > richness(canon_by_fp[fp]):
                    canon_by_fp[fp] = deepcopy(row)
                    canon_by_fp[fp]["_merge_source"] = label
                    canon_by_fp[fp]["_merge_source_case_id"] = raw_case_id
            else:
                canon_by_fp[fp] = deepcopy(row)
                canon_by_fp[fp]["_merge_source"] = label
                canon_by_fp[fp]["_merge_source_case_id"] = raw_case_id

    canonical = list(canon_by_fp.values())
    canonical.sort(
        key=lambda r: (
            LAYER_ORDER.index(layer_of(r)) if layer_of(r) in LAYER_ORDER else 99,
            start_key(r),
            str(r.get("range_id") or r.get("id") or ""),
        )
    )
    return canonical, id_to_fp, dup_log


def remap_range_id(
    raw_case_id: str,
    value: Any,
    id_to_fp: dict[tuple[str, str], tuple[str, float, float, str]],
    fp_to_new: dict[tuple[str, float, float, str], int],
) -> int | None:
    if value is None or value == "":
        return None
    key = (raw_case_id, str(value))
    fp = id_to_fp.get(key)
    if fp is None:
        return None
    return fp_to_new.get(fp)


def range_payload(
    row: dict[str, Any],
    master_id: str,
    case_ref: str,
    parent_new_id: int | None,
    old_new_id: int | None,
    new_new_id: int | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in RANGE_SKIP or k.startswith("_"):
            continue
        if v is not None and v != "":
            out[k] = v
    source_cid = row.get("_merge_source_case_id")
    old_rid = str(row.get("range_id") or row.get("id") or "x")
    out["symbol"] = SYMBOL
    out["raw_case_id"] = master_id
    out["case_ref"] = case_ref
    out["structure_layer"] = layer_of(row)
    out["source_timeframe"] = str(row.get("source_timeframe") or row.get("timeframe") or "D1").upper()
    out["chart_timeframe"] = str(row.get("chart_timeframe") or out["source_timeframe"]).upper()
    out["timeframe"] = out["source_timeframe"]
    out["range_key"] = f"master_{master_id[:8]}_{out['structure_layer']}_{old_rid}"
    out["parent_range_id"] = parent_new_id
    if old_new_id is not None:
        out["old_range_id"] = old_new_id
    if new_new_id is not None:
        out["new_range_id"] = new_new_id
    if out.get("meta_json") and isinstance(out["meta_json"], str):
        try:
            meta = json.loads(out["meta_json"])
            meta["merged_from_case"] = row.get("_merge_source")
            out["meta_json"] = meta
        except json.JSONDecodeError:
            pass
    return out


def main() -> None:
    print("Building canonical range list…")
    canonical, id_to_fp, dup_log = build_canonical_ranges()
    print(f"  canonical ranges: {len(canonical)} (deduped from 75 source rows)")
    print(f"  duplicate fingerprints skipped: {len(dup_log)}")

    create = http_post(
        "/api/v1/raw-mapping/cases",
        {
            "symbol": SYMBOL,
            "case_name": MASTER_NAME,
            "base_timeframe": "W1",
            "price_scale_default": 100,
            "notes": "Merged master case from 2019 Q3-2020 Q1 + 2020 Q2-2021 Q1 (deduped)",
        },
    )
    master_id = str(create.get("case", {}).get("case_id") or create.get("case_id") or "")
    if not master_id:
        raise RuntimeError(f"Master case create failed: {create}")
    case_ref = f"raw:{master_id}"
    print(f"Created master case: {MASTER_NAME} id={master_id}")

    fp_to_new: dict[tuple[str, float, float, str], int] = {}
    inserted = 0
    for row in canonical:
        fp = fingerprint(row)
        source_cid = str(row.get("_merge_source_case_id") or "")
        parent_old = row.get("parent_range_id")
        parent_new = remap_range_id(source_cid, parent_old, id_to_fp, fp_to_new)
        old_old = row.get("old_range_id")
        new_old = row.get("new_range_id")
        old_new = remap_range_id(source_cid, old_old, id_to_fp, fp_to_new) if old_old else None
        new_new = remap_range_id(source_cid, new_old, id_to_fp, fp_to_new) if new_old else None

        payload = range_payload(row, master_id, case_ref, parent_new, old_new, new_new)
        result = http_post("/api/v1/map/range", payload)
        if not result.get("ok"):
            raise RuntimeError(f"Range insert failed: {result}")
        new_id = int(result.get("range_id") or result.get("id") or 0)
        fp_to_new[fp] = new_id
        inserted += 1

    print(f"Inserted {inserted} ranges into master case")

    # Map structural events
    event_fp_seen: set[tuple[Any, ...]] = set()
    events_inserted = 0
    events_skipped = 0
    for raw_case_id, label in SOURCES:
        for ev in fetch_events(raw_case_id):
            payload = deepcopy(ev)
            for k in ("id", "created_at", "updated_at", "client_event_id"):
                payload.pop(k, None)
            payload["raw_case_id"] = master_id
            payload["case_ref"] = case_ref
            payload["event_id"] = str(uuid.uuid4())
            for field in ("active_range_id", "parent_range_id", "range_id", "old_range_id", "new_range_id"):
                if payload.get(field) is not None:
                    mapped = remap_range_id(raw_case_id, payload[field], id_to_fp, fp_to_new)
                    if mapped is not None:
                        payload[field] = mapped
                    else:
                        payload[field] = None
            dedupe_key = (
                payload.get("active_range_id"),
                payload.get("time") or payload.get("event_time"),
                str(payload.get("event_type") or "").upper(),
                round(float(payload.get("price") or 0), 2),
            )
            if dedupe_key in event_fp_seen:
                events_skipped += 1
                continue
            event_fp_seen.add(dedupe_key)
            result = http_post("/api/v1/map/structural-event", payload)
            if not result.get("ok"):
                print(f"  WARN event skip: {result.get('error')}")
                events_skipped += 1
            else:
                events_inserted += 1

    print(f"Structural events: {events_inserted} inserted, {events_skipped} skipped/dup")

    # Raw ledger merge
    raw_seen: set[tuple[Any, ...]] = set()
    raw_batch: list[dict[str, Any]] = []
    raw_skipped = 0
    for raw_case_id, label in SOURCES:
        export = fetch_raw_export(raw_case_id)
        for ev in export.get("sequence_by_intent") or export.get("events") or []:
            row = dict(ev)
            row["case_id"] = master_id
            row["event_id"] = str(uuid.uuid4())
            row["symbol"] = SYMBOL
            key = (
                int(row.get("candle_time_utc_ms") or 0),
                str(row.get("event_type") or "").upper(),
                str(row.get("event_side") or "").upper(),
                row.get("price_int"),
            )
            if key in raw_seen:
                raw_skipped += 1
                continue
            raw_seen.add(key)
            raw_batch.append(row)

    if raw_batch:
        # batch in chunks of 200
        raw_inserted = 0
        for i in range(0, len(raw_batch), 200):
            chunk = raw_batch[i : i + 200]
            result = http_post(
                "/api/v1/raw-mapping/events/batch",
                {"case_id": master_id, "events": chunk},
            )
            if not result.get("ok"):
                raise RuntimeError(f"Raw batch failed: {result}")
            raw_inserted += int(result.get("count") or len(chunk))
        print(f"Raw ledger: {raw_inserted} events ({raw_skipped} dupes skipped)")
    else:
        print("Raw ledger: nothing to merge")

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "master_case_id": master_id,
        "master_case_name": MASTER_NAME,
        "case_ref": case_ref,
        "sources": [{"id": s[0], "name": s[1]} for s in SOURCES],
        "canonical_ranges": inserted,
        "duplicate_ranges_skipped": dup_log,
        "structural_events_inserted": events_inserted,
        "raw_events_merged": len(raw_batch),
    }
    out_path = Path(__file__).resolve().parents[2] / "docs" / "merge_master_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written: {out_path}")
    print("\n=== DONE ===")
    print(f"Open Cockpit → Case Manager → load case: {MASTER_NAME}")
    print(f"raw_case_id: {master_id}")


if __name__ == "__main__":
    main()
