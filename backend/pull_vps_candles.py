#!/usr/bin/env python3
"""Pull candle history from live VPS API into the local research database."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

import candle_store


DEFAULT_BASE_URL = "https://api01.apexcoastalrentals.co.za"
DEFAULT_TIMEFRAMES = ("W1", "D1", "H4", "H1", "M15", "M5")


def fetch_candles(
    *,
    base_url: str,
    symbol: str,
    timeframe: str,
    limit: int,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "limit": str(limit),
    }
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    url = f"{base_url.rstrip('/')}/api/v1/candles?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pull_timeframes(
    *,
    base_url: str,
    symbol: str,
    timeframes: list[str],
    limit: int,
) -> dict:
    results: list[dict] = []
    total_upserted = 0
    for tf in timeframes:
        tf = str(tf).strip().upper()
        if not tf:
            continue
        try:
            payload = fetch_candles(base_url=base_url, symbol=symbol, timeframe=tf, limit=limit)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            results.append({
                "timeframe": tf,
                "ok": False,
                "count": 0,
                "error": f"HTTP {exc.code}: {body[:240]}",
            })
            continue
        except Exception as exc:
            results.append({
                "timeframe": tf,
                "ok": False,
                "count": 0,
                "error": repr(exc),
            })
            continue

        candles = list(payload.get("candles") or [])
        if not payload.get("ok", True) and not candles:
            results.append({
                "timeframe": tf,
                "ok": False,
                "count": 0,
                "error": str(payload.get("error") or "VPS returned no candles"),
            })
            continue

        upsert = candle_store.upsert_candles(candles, source="vps-pull")
        count = len(candles)
        total_upserted += count
        results.append({
            "timeframe": tf,
            "ok": True,
            "count": count,
            "upserted": upsert,
        })

    return {
        "ok": any(row.get("ok") for row in results),
        "base_url": base_url,
        "symbol": symbol,
        "database": str(candle_store.ensure_db_path()),
        "total_candles": total_upserted,
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pull VPS candles into local research SQLite")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    parser.add_argument("--limit", type=int, default=8000)
    parser.add_argument("--db", default=None, help="SQLite path override")
    parser.add_argument("--json", action="store_true", help="print JSON summary on stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.db:
        candle_store.DB_PATH = args.db  # type: ignore[assignment]

    candle_store.init_db()
    timeframes = [part.strip() for part in str(args.timeframes).split(",") if part.strip()]
    summary = pull_timeframes(
        base_url=str(args.base_url),
        symbol=str(args.symbol).upper(),
        timeframes=timeframes,
        limit=max(1, min(int(args.limit or 8000), 10000)),
    )

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"VPS candle pull -> {summary['database']}")
        for row in summary["results"]:
            if row.get("ok"):
                print(f"  {row['timeframe']}: {row.get('count', 0)} candles")
            else:
                print(f"  {row['timeframe']}: FAILED ({row.get('error')})")
        print(f"total: {summary.get('total_candles', 0)} candles")

    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
