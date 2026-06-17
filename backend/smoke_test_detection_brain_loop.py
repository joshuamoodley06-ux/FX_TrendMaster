"""Production smoke test helper for Phase 0-3.5 detection brain loop.

Usage:
  python smoke_test_detection_brain_loop.py --preflight --base-url https://api01...
  python smoke_test_detection_brain_loop.py --run-loop --base-url https://api01... --symbol XAUUSD --timeframe W1
  python smoke_test_detection_brain_loop.py --verify-only --symbol XAUUSD

Does not change detector logic. Only exercises API + DB verification.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from typing import Any

from detector.break_rules import structure_layer_for_timeframe

DEFAULT_BASE = "https://api01.apexcoastalrentals.co.za"


class SmokeResult:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def record(self, step: str, ok: bool, detail: str = "", data: Any = None) -> None:
        self.steps.append({"step": step, "ok": ok, "detail": detail, "data": data})
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {step}" + (f" — {detail}" if detail else ""))

    @property
    def ok(self) -> bool:
        return all(s["ok"] for s in self.steps)


def _request_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: int = 60) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw.strip() else {"error": raw}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload


def check_status(base_url: str, result: SmokeResult) -> dict[str, Any] | None:
    url = f"{base_url.rstrip('/')}/api/v1/candles/status"
    code, data = _request_json(url)
    db = data.get("detection_brain")
    if db is None:
        result.record(
            "Step 2: /api/v1/candles/status detection_brain.ok",
            False,
            "BLOCKER: detection_brain block missing — deploy latest backend + restart",
            data,
        )
        return None
    ok = code == 200 and data.get("ok") is True and db.get("ok") is True
    views = (db.get("analytics_views") or {}).get("v_detector_correction_facts")
    result.record(
        "Step 2: /api/v1/candles/status detection_brain.ok",
        ok,
        f"http={code} detection_brain.ok={db.get('ok')} view={views}",
        db,
    )
    return data if ok else None


def check_detection_brain_routes(base_url: str, symbol: str, layer: str, tf: str, result: SmokeResult) -> bool:
    url = (
        f"{base_url.rstrip('/')}/api/v1/detection-brain/suggestions"
        f"?symbol={symbol}&structure_layer={layer}&source_timeframe={tf}&status=PENDING&limit=5"
    )
    code, data = _request_json(url)
    if code == 404:
        result.record(
            "Step 6 API: list PENDING suggestions route",
            False,
            "BLOCKER: route 404 — detection-brain API not deployed on VPS",
        )
        return False
    ok = code == 200 and data.get("ok") is True and "suggestions" in data
    result.record(
        "Step 6 API: list PENDING suggestions route",
        ok,
        f"http={code} count={data.get('count', '?')}",
    )
    return ok


def run_detector(base_url: str, symbol: str, tf: str, result: SmokeResult) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v1/detection-brain/run-detector"
    payload = {"symbol": symbol, "source_timeframe": tf, "limit": 500}
    code, data = _request_json(url, method="POST", body=payload, timeout=120)
    if code == 404:
        result.record("Step 5: run Python detector", False, "BLOCKER: route 404 — detection-brain API not deployed")
        return []
    written = int(data.get("written_count") or 0)
    ok = code == 200 and data.get("ok") is True
    result.record(
        "Step 5: run Python detector",
        ok,
        f"http={code} written={written} drafts={data.get('draft_count', '?')}",
    )
    return list(data.get("suggestions") or []) if ok else []


def list_pending(base_url: str, symbol: str, layer: str, tf: str) -> list[dict[str, Any]]:
    url = (
        f"{base_url.rstrip('/')}/api/v1/detection-brain/suggestions"
        f"?symbol={symbol}&structure_layer={layer}&source_timeframe={tf}&status=PENDING&limit=50"
    )
    _, data = _request_json(url)
    return list(data.get("suggestions") or []) if data.get("ok") else []


def review_suggestion(
    base_url: str,
    suggestion_id: str,
    action: str,
    *,
    edits: dict | None = None,
    error_category: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/detection-brain/suggestions/review"
    body: dict[str, Any] = {"suggestion_id": suggestion_id, "action": action, "notes": notes}
    if edits:
        body["edits"] = edits
    if error_category:
        body["error_category"] = error_category
    _, data = _request_json(url, method="POST", body=body, timeout=60)
    return data


def api_review_loop(base_url: str, symbol: str, tf: str, result: SmokeResult) -> None:
    layer = structure_layer_for_timeframe(tf)
    pending = list_pending(base_url, symbol, layer, tf)
    if len(pending) < 3:
        run_detector(base_url, symbol, tf, result)
        pending = list_pending(base_url, symbol, layer, tf)

    result.record("Step 6: pending suggestions available", len(pending) >= 3, f"count={len(pending)} (need >=3 for full loop)")
    if len(pending) < 1:
        return

    # Approve
    approve_target = pending[0]
    out = review_suggestion(base_url, approve_target["suggestion_id"], "APPROVE")
    result.record(
        "Step 7: approve candidate",
        out.get("ok") is True and not out.get("duplicate"),
        f"id={approve_target['suggestion_id'][:8]} promoted_range={out.get('promoted_range_id')} promoted_event={out.get('promoted_event_id')}",
    )

    # Duplicate approve
    dup = review_suggestion(base_url, approve_target["suggestion_id"], "APPROVE")
    result.record(
        "Step 10: duplicate approve idempotent",
        dup.get("ok") is True and dup.get("duplicate") is True,
        f"duplicate={dup.get('duplicate')}",
    )

    pending = list_pending(base_url, symbol, layer, tf)
    if not pending:
        run_detector(base_url, symbol, tf, result)
        pending = list_pending(base_url, symbol, layer, tf)

    if pending:
        edit_target = pending[0]
        edits: dict[str, Any] = {}
        if edit_target.get("suggested_rh") is not None:
            edits["suggested_rh"] = float(edit_target["suggested_rh"]) + 1.0
        if edit_target.get("suggested_rl") is not None:
            edits["suggested_rl"] = float(edit_target["suggested_rl"]) - 1.0
        if edit_target.get("event_price") is not None:
            edits["event_price"] = float(edit_target["event_price"]) + 0.5
        out = review_suggestion(
            base_url,
            edit_target["suggestion_id"],
            "EDIT",
            edits=edits or None,
            error_category="WRONG_RH",
            notes="smoke test edit",
        )
        result.record("Step 8: edit + approve", out.get("ok") is True, f"id={edit_target['suggestion_id'][:8]}")

    pending = list_pending(base_url, symbol, layer, tf)
    if not pending:
        run_detector(base_url, symbol, tf, result)
        pending = list_pending(base_url, symbol, layer, tf)

    if pending:
        reject_target = pending[0]
        out = review_suggestion(
            base_url,
            reject_target["suggestion_id"],
            "REJECT",
            error_category="OTHER",
            notes="smoke test reject",
        )
        result.record(
            "Step 9: reject candidate",
            out.get("ok") is True and out.get("promoted_range_id") in (None, 0) and out.get("promoted_event_id") in (None, 0),
            f"id={reject_target['suggestion_id'][:8]}",
        )


def verify_db(symbol: str, result: SmokeResult, *, expect_reviews: bool = False) -> None:
    import candle_store
    from detection_brain_schema import detection_brain_schema_status, init_detection_brain_schema
    from detector_performance import PerformanceFilters, get_detector_summary, render_cli_report

    candle_store.init_db()
    with sqlite3.connect(candle_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        init_detection_brain_schema(conn)
        schema = detection_brain_schema_status(conn)
        result.record(
            "Step 2 (local DB): detection_brain.ok",
            schema.get("ok") is True,
            f"views={schema.get('analytics_views')}",
        )

        reviewed = conn.execute(
            """
            SELECT status, user_action, COUNT(*) AS n
            FROM detector_suggestions
            WHERE symbol = ? AND status IN ('APPROVED','EDITED','REJECTED')
            GROUP BY status, user_action
            """,
            (symbol.upper(),),
        ).fetchall()
        has_reviews = len(reviewed) > 0
        if expect_reviews:
            result.record("Step 10: reviewed suggestion statuses", has_reviews, str([dict(r) for r in reviewed]))
        else:
            result.record(
                "Step 10: reviewed suggestion statuses",
                True,
                "SKIP (no reviews yet)" if not has_reviews else str([dict(r) for r in reviewed]),
            )

        corrections = conn.execute(
            """
            SELECT user_action, error_category, COUNT(*) AS n
            FROM detector_corrections
            WHERE symbol = ?
            GROUP BY user_action, error_category
            ORDER BY n DESC
            """,
            (symbol.upper(),),
        ).fetchall()
        if expect_reviews:
            actions = {str(r["user_action"]) for r in corrections}
            cats = {str(r["error_category"]) for r in corrections}
            ok = {"APPROVE", "EDIT", "REJECT"}.issubset(actions) and "NO_ERROR" in cats and len(cats) > 1
            result.record("Step 10: correction log actions/categories", ok, str([dict(r) for r in corrections]))
        else:
            result.record(
                "Step 10: correction log actions/categories",
                True,
                "SKIP (no corrections yet)" if not corrections else str([dict(r) for r in corrections]),
            )

        dup_ranges = conn.execute(
            """
            SELECT confirmed_from_suggestion_id, COUNT(*) AS n
            FROM map_ranges
            WHERE confirmed_from_suggestion_id IS NOT NULL AND symbol = ?
            GROUP BY confirmed_from_suggestion_id
            HAVING n > 1
            """,
            (symbol.upper(),),
        ).fetchall()
        result.record("Step 10: no duplicate promoted ranges", len(dup_ranges) == 0, f"duplicates={len(dup_ranges)}")

        summary = get_detector_summary(conn, PerformanceFilters(symbol=symbol))
        if expect_reviews:
            rates_ok = summary.get("total_reviewed", 0) >= 1 and summary.get("approval_rate") is not None
            result.record(
                "Step 11-12: performance summary",
                rates_ok,
                f"reviewed={summary.get('total_reviewed')} approve={summary.get('approval_rate')}",
            )
        else:
            result.record(
                "Step 11-12: performance summary",
                True,
                f"SKIP until reviews exist (reviewed={summary.get('total_reviewed')})",
            )
        if summary.get("total_reviewed", 0) > 0:
            print("\n--- detector_performance.py (excerpt) ---")
            report = render_cli_report(conn, PerformanceFilters(symbol=symbol))
            for line in report.splitlines()[:25]:
                print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 0-3.5 production smoke test helper")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="W1", help="W1 or D1")
    parser.add_argument("--preflight", action="store_true", help="Steps 2, 5, 6 only (read-only list after run)")
    parser.add_argument("--run-loop", action="store_true", help="API approve/edit/reject loop")
    parser.add_argument("--verify-only", action="store_true", help="DB verification + performance report (VPS)")
    parser.add_argument("--expect-reviews", action="store_true", help="With --verify-only: fail if steps 7-9 not done yet")
    args = parser.parse_args(argv)

    result = SmokeResult()
    symbol = str(args.symbol).upper()
    tf = str(args.timeframe).upper()
    layer = structure_layer_for_timeframe(tf)
    base = str(args.base_url).rstrip("/")

    if args.verify_only:
        verify_db(symbol, result, expect_reviews=args.expect_reviews)
        print("\n" + ("SMOKE OK" if result.ok else "SMOKE FAILED"))
        return 0 if result.ok else 1

    check_status(base, result)
    check_detection_brain_routes(base, symbol, layer, tf, result)

    if args.preflight or args.run_loop:
        run_detector(base, symbol, tf, result)
        pending = list_pending(base, symbol, layer, tf)
        result.record(
            "Step 6: PENDING suggestions after detector",
            len(pending) > 0,
            f"count={len(pending)} layer={layer} tf={tf}",
        )

    if args.run_loop:
        api_review_loop(base, symbol, tf, result)
        verify_db(symbol, result, expect_reviews=True)

    print("\n" + ("SMOKE OK" if result.ok else "SMOKE FAILED"))
    if not result.ok:
        print("See docs/architecture/PRODUCTION_SMOKE_TEST_PLAN_PHASE_0_3_5.md")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
