"""
Remove orphan structural ranges from XAUUSD_MASTER_2019_2026.

Orphans = ranges not reachable from MACRO roots (same logic as Cockpit explorer).
Keeps MACRO #152 and its linked descendant tree.

Usage:
  python cleanup_master_orphans.py --dry-run
  python cleanup_master_orphans.py --hard-delete
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

BASE = "https://api01.apexcoastalrentals.co.za"
SYMBOL = "XAUUSD"
MASTER_RAW_CASE_ID = "388d8181-a9b9-4faf-be16-3364ef741455"
KEEP_MACRO_IDS = {152}
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "cleanup_orphans_report.json"


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
        with request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        body = exc.read().decode()
        raise RuntimeError(f"POST {path} failed {exc.code}: {body}") from exc


def norm_layer(row: dict[str, Any]) -> str:
    return str(row.get("structure_layer") or row.get("layer") or "").upper()


def range_id(row: dict[str, Any]) -> str:
    return str(row.get("range_id") or row.get("id"))


def build_orphans(ranges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    nodes = list(ranges)
    macro_ranges = [r for r in nodes if norm_layer(r) == "MACRO"]
    visited: set[str] = set()

    def walk(r: dict[str, Any]) -> None:
        rid = range_id(r)
        visited.add(rid)
        for child in nodes:
            if str(child.get("parent_range_id") or "") == rid:
                walk(child)

    for macro in macro_ranges:
        walk(macro)

    orphans = [r for r in nodes if range_id(r) not in visited]
    return orphans, visited


def hard_delete_ranges(range_ids: list[int]) -> dict[str, Any]:
    return http_post(
        "/api/v1/map/ranges/hard-delete",
        {
            "range_ids": range_ids,
            "raw_case_id": MASTER_RAW_CASE_ID,
            "confirm": "DELETE",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="List orphans only, no changes")
    parser.add_argument("--hard-delete", action="store_true", help="Permanently delete orphan ranges on VPS")
    args = parser.parse_args()
    if not args.dry_run and not args.hard_delete:
        parser.error("Pass --dry-run or --hard-delete")

    data = http_get(
        f"/api/v1/map/ranges?symbol={SYMBOL}&raw_case_id={MASTER_RAW_CASE_ID}&limit=5000"
    )
    ranges = data.get("ranges") or []
    orphans, visited = build_orphans(ranges)

    # Safety: never delete kept macro ids even if miscategorized as orphan
    to_delete = [r for r in orphans if int(range_id(r)) not in KEEP_MACRO_IDS]
    delete_ids = [int(range_id(r)) for r in to_delete]

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "master_raw_case_id": MASTER_RAW_CASE_ID,
        "total_ranges": len(ranges),
        "tree_range_count": len(visited),
        "orphan_count": len(orphans),
        "delete_count": len(to_delete),
        "kept_macro_ids": sorted(KEEP_MACRO_IDS),
        "orphans": [
            {
                "range_id": range_id(r),
                "structure_layer": norm_layer(r),
                "range_start_time": r.get("range_start_time"),
                "parent_range_id": r.get("parent_range_id"),
                "status": r.get("status"),
            }
            for r in to_delete
        ],
        "hard_deleted": [],
        "errors": [],
    }

    print(f"Total ranges: {len(ranges)}")
    print(f"In MACRO tree: {len(visited)}")
    print(f"Orphans to delete: {len(to_delete)}")
    for r in to_delete:
        print(
            f"  #{range_id(r)} {norm_layer(r)} "
            f"{str(r.get('range_start_time') or '')[:10]} "
            f"parent={r.get('parent_range_id')} status={r.get('status')}"
        )

    if args.hard_delete and delete_ids:
        try:
            result = hard_delete_ranges(delete_ids)
            report["hard_delete_result"] = result
            if result.get("ok"):
                report["hard_deleted"] = delete_ids
                print(
                    f"Hard deleted {result.get('deleted_ranges')} ranges, "
                    f"{result.get('deleted_events')} events"
                )
                if result.get("errors"):
                    report["errors"] = result.get("errors")
                    print("Partial errors:", result.get("errors"))
            else:
                report["errors"].append(result)
                print("FAILED:", result)
        except Exception as exc:
            report["errors"].append({"error": str(exc)})
            print("FAILED:", exc)
            print(
                "If the API returned 404/405, deploy backend/main.py + candle_store.py to VPS "
                "and run scripts/vps_restart_backend.bat on the server."
            )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
