#!/usr/bin/env python3
"""Local detection brain CLI — same Python as Weekly Research (not VPS)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import candle_store
from detection_brain_api import list_pending_suggestions, run_detector_and_store
from detection_brain_audit_export import (
    build_detection_run_audit_export,
    find_latest_detection_run_id,
    list_suggestions_for_run,
)
from detection_brain_promotion import PromotionError, review_suggestion
from detection_brain_schema import init_detection_brain_schema


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_file:
        with open(args.payload_file, encoding="utf-8") as fh:
            return json.load(fh)
    if args.payload:
        return json.loads(args.payload)
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local detection brain (run-detector / list suggestions)")
    parser.add_argument("--db", required=True, help="SQLite path (market_memory + detector_suggestions)")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run RANGE_V2 detector at replay week")
    run_p.add_argument("--payload", default=None, help="JSON payload string")
    run_p.add_argument("--payload-file", default=None, help="JSON payload file")

    list_p = sub.add_parser("list", help="List pending detector suggestions")
    list_p.add_argument("--symbol", default="XAUUSD")
    list_p.add_argument("--structure-layer", default="WEEKLY")
    list_p.add_argument("--source-timeframe", default="W1")
    list_p.add_argument("--detection-run-id", default=None)
    list_p.add_argument("--replay-until-ms", type=int, default=None)
    list_p.add_argument("--limit", type=int, default=100)
    list_p.add_argument("--status", default="PENDING", help="PENDING|APPROVED|REJECTED|EDITED|ALL")

    list_run_p = sub.add_parser("list-run", help="All suggestions for a detection run (ordered by week)")
    list_run_p.add_argument("--symbol", default="XAUUSD")
    list_run_p.add_argument("--structure-layer", default="WEEKLY")
    list_run_p.add_argument("--source-timeframe", default="W1")
    list_run_p.add_argument("--detection-run-id", required=True)
    list_run_p.add_argument("--candidate-kind", default="RANGE_CANDIDATE")

    review_p = sub.add_parser("review", help="Approve, edit, or reject a suggestion")
    review_p.add_argument("--suggestion-id", required=True)
    review_p.add_argument("--action", required=True, choices=["APPROVE", "EDIT", "REJECT"])
    review_p.add_argument("--edits-json", default=None, help="JSON object with suggested_rh, suggested_rl, etc.")
    review_p.add_argument("--error-category", default=None)
    review_p.add_argument("--notes", default="")

    export_p = sub.add_parser("export-audit", help="Export full audit JSON for a detection run")
    export_p.add_argument("--symbol", default="XAUUSD")
    export_p.add_argument("--structure-layer", default="WEEKLY")
    export_p.add_argument("--source-timeframe", default="W1")
    export_p.add_argument("--detection-run-id", required=True)
    export_p.add_argument("--candidate-kind", default="RANGE_CANDIDATE")
    export_p.add_argument("--out", default=None, help="Optional file path to write JSON")

    latest_p = sub.add_parser("latest-run", help="Most recent detection_run_id for symbol/tf")
    latest_p.add_argument("--symbol", default="XAUUSD")
    latest_p.add_argument("--structure-layer", default="WEEKLY")
    latest_p.add_argument("--source-timeframe", default="W1")
    latest_p.add_argument("--candidate-kind", default="RANGE_CANDIDATE")

    args = parser.parse_args(argv)
    candle_store.DB_PATH = args.db  # type: ignore[assignment]
    candle_store.init_db()

    if args.command == "run":
        payload = _load_payload(args)
        if payload.get("discovery_mode") is None:
            payload["discovery_mode"] = True
        result = run_detector_and_store(payload)
        print(json.dumps(result))
        return 0 if result.get("ok") else 1

    if args.command == "list":
        status = None if str(args.status or "").upper() == "ALL" else str(args.status or "PENDING").upper()
        with candle_store.connect() as conn:
            init_detection_brain_schema(conn)
            from detection_brain_store import list_suggestions

            rows = list_suggestions(
                conn,
                status=status,
                symbol=str(args.symbol).upper(),
                structure_layer=str(args.structure_layer).upper(),
                source_timeframe=str(args.source_timeframe).upper(),
                limit=int(args.limit),
            )
        if args.detection_run_id or args.replay_until_ms is not None:
            from detection_brain_api import meta_matches_context_filter

            rows = [
                row
                for row in rows
                if meta_matches_context_filter(
                    row.get("meta_json"),
                    detection_run_id=args.detection_run_id,
                    replay_until_time_ms=args.replay_until_ms,
                )
            ]
        result = {"ok": True, "count": len(rows), "suggestions": rows}
        print(json.dumps(result))
        return 0 if result.get("ok") else 1

    if args.command == "list-run":
        with candle_store.connect() as conn:
            init_detection_brain_schema(conn)
            samples = list_suggestions_for_run(
                conn,
                symbol=str(args.symbol).upper(),
                structure_layer=str(args.structure_layer).upper(),
                source_timeframe=str(args.source_timeframe).upper(),
                detection_run_id=str(args.detection_run_id),
                candidate_kind=str(args.candidate_kind or "RANGE_CANDIDATE"),
            )
        result = {"ok": True, "count": len(samples), "samples": samples}
        print(json.dumps(result))
        return 0

    if args.command == "review":
        edits = None
        if args.edits_json:
            edits = json.loads(args.edits_json)
        try:
            with candle_store.connect() as conn:
                init_detection_brain_schema(conn)
                result = review_suggestion(
                    conn,
                    str(args.suggestion_id),
                    action=str(args.action).upper(),
                    edits=edits,
                    error_category=args.error_category,
                    notes=str(args.notes or ""),
                    fast_promote=True,
                )
                conn.commit()
        except PromotionError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 1
        print(json.dumps({"ok": True, **result}))
        return 0

    if args.command == "export-audit":
        with candle_store.connect() as conn:
            init_detection_brain_schema(conn)
            payload = build_detection_run_audit_export(
                conn,
                symbol=str(args.symbol).upper(),
                structure_layer=str(args.structure_layer).upper(),
                source_timeframe=str(args.source_timeframe).upper(),
                detection_run_id=str(args.detection_run_id),
                candidate_kind=str(args.candidate_kind or "RANGE_CANDIDATE"),
            )
        text = json.dumps(payload, indent=2, default=str)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            payload["written_to"] = args.out
        print(text)
        return 0

    if args.command == "latest-run":
        with candle_store.connect() as conn:
            init_detection_brain_schema(conn)
            run_id = find_latest_detection_run_id(
                conn,
                symbol=str(args.symbol).upper(),
                structure_layer=str(args.structure_layer).upper(),
                source_timeframe=str(args.source_timeframe).upper(),
                candidate_kind=str(args.candidate_kind or "RANGE_CANDIDATE"),
            )
        result = {
            "ok": True,
            "detection_run_id": run_id,
            "has_run": bool(run_id),
        }
        print(json.dumps(result))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
