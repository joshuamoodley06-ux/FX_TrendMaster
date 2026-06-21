#!/usr/bin/env python3
"""CLI: record AUDIT_PASS or AUDIT_FAIL for a suggestion (local research)."""

from __future__ import annotations

import argparse
import json
import sys

import candle_store
from detection_brain_promotion import PromotionError, review_suggestion
from detection_brain_schema import init_detection_brain_schema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record visual audit verdict")
    parser.add_argument("--suggestion-id", required=True)
    parser.add_argument("--action", required=True, choices=["AUDIT_PASS", "AUDIT_FAIL"])
    parser.add_argument("--notes", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--db", default=None, help="SQLite path override")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.db:
        candle_store.DB_PATH = args.db  # type: ignore[assignment]

    candle_store.init_db()

    try:
        with candle_store.connect() as conn:
            init_detection_brain_schema(conn)
            result = review_suggestion(
                conn,
                str(args.suggestion_id),
                action=str(args.action).upper(),
                notes=str(args.notes or ""),
            )
            conn.commit()
    except PromotionError as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = {"ok": True, **result}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"ok action={args.action} suggestion_id={args.suggestion_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
