"""Weekly reclaim and abandonment doctrine package.

This package consumes approved weekly_structure memory and never redetects BOS.
A wick break may reclaim on the BOS candle itself when that candle closes back
through the broken boundary. Otherwise the next W1 candle starts the count and
the first later boundary touch stops it. A newer Weekly BOS before that touch
marks the old range abandoned; if price later returns, the final state is
ABANDONED_THEN_RECLAIMED (displayed as ABND→RECL).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_reclaim"
VERSION_LABEL = "2"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 20

_PENDING_BOS_REASONS = {
    "WEEKLY_BOS_NOT_FOUND",
    "NO_W1_CANDLES_AFTER_RANGE_DEFINED",
}
_REVIEW_BOS_REASONS = {
    "INVALID_RANGE_PRICES",
    "MISSING_OR_INVALID_ANCHOR_TIME",
    "EQUAL_ANCHOR_TIMES",
    "BOTH_BOUNDARIES_BREACHED_SAME_W1",
}


def _time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _weekly_bos_memory(
    context: Any,
    canonical_range_id: str,
) -> tuple[dict[str, Any] | None, str]:
    memory = context.approved_memory(canonical_range_id)
    if not isinstance(memory, Mapping):
        return None, "MISSING"
    entry = memory.get("weekly_structure")
    if not isinstance(entry, Mapping):
        return None, "MISSING"
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        return None, "MISSING"
    value = dict(payload)
    explicit = str(entry.get("processing_status") or "").upper()
    if explicit in {"COMPLETE", "PENDING", "NEEDS_REVIEW"}:
        return value, explicit
    reasons = {
        str(reason).upper()
        for reason in value.get("reason_codes", [])
        if str(reason).strip()
    }
    if reasons & _REVIEW_BOS_REASONS:
        return value, "NEEDS_REVIEW"
    if reasons & _PENDING_BOS_REASONS:
        return value, "PENDING"
    if (
        str(value.get("bos_direction") or "").upper() in {"BOS_UP", "BOS_DOWN"}
        and _time(value.get("bos_time")) is not None
        and _time(value.get("range_defined_at")) is not None
    ):
        return value, "COMPLETE"
    return value, "INCOMPLETE"


def _base_payload() -> dict[str, Any]:
    return {
        "reclaim_status": "PENDING",
        "reclaim_abbreviation": "PEND",
        "source_bos_direction": None,
        "source_bos_time": None,
        "source_bos_processing_status": None,
        "bos_candle_close": None,
        "same_candle_reclaim": False,
        "reclaim_boundary": None,
        "reclaim_time": None,
        "reclaim_wick_price": None,
        "next_bos_range_id": None,
        "next_bos_direction": None,
        "next_bos_time": None,
        "abandoned_before_reclaim": False,
        "candles_scanned": 0,
        "weeks_to_reclaim": None,
        "weeks_to_abandonment": None,
        "weeks_from_abandonment_to_reclaim": None,
        "reason_codes": [],
    }


def _touches_boundary(candle: Mapping[str, Any], direction: str, boundary: float) -> bool:
    if direction == "BOS_UP":
        return float(candle["low"]) <= boundary
    return float(candle["high"]) >= boundary


def _same_candle_reclaim(candle: Mapping[str, Any], direction: str, boundary: float) -> bool:
    close = float(candle["close"])
    if direction == "BOS_UP":
        return float(candle["high"]) > boundary and close <= boundary
    return float(candle["low"]) < boundary and close >= boundary


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    nodes = [dict(node) for node in context.selected_ranges(layer="WEEKLY")]
    records: list[dict[str, Any]] = []
    for node in nodes:
        canonical_id = str(node.get("id") or "")
        bos, bos_status = _weekly_bos_memory(context, canonical_id)
        records.append({
            "node": node,
            "id": canonical_id,
            "defined_at": _time((bos or {}).get("range_defined_at")),
            "bos_time": _time((bos or {}).get("bos_time")),
            "bos_direction": str((bos or {}).get("bos_direction") or "").upper(),
            "bos": bos,
            "bos_status": bos_status,
        })

    latest_text = context.latest_candle_time("W1")
    latest_time = _time(latest_text)
    outputs: list[dict[str, Any]] = []

    for current in records:
        node = current["node"]
        payload = _base_payload()
        bos = current["bos"]
        bos_status = current["bos_status"]
        payload["source_bos_processing_status"] = bos_status
        if bos is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if bos_status == "PENDING":
            payload["reason_codes"] = ["WEEKLY_BOS_STILL_PENDING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if bos_status == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_BOS_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if bos_status != "COMPLETE":
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        direction = current["bos_direction"]
        bos_time = current["bos_time"]
        defined_at = current["defined_at"]
        high = _number(node.get("range_high"))
        low = _number(node.get("range_low"))
        if direction not in {"BOS_UP", "BOS_DOWN"} or bos_time is None or defined_at is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        boundary = high if direction == "BOS_UP" else low
        payload.update({
            "source_bos_direction": direction,
            "source_bos_time": _stamp(bos_time),
            "reclaim_boundary": boundary,
        })

        later_bos = sorted(
            (
                record for record in records
                if record["id"] != current["id"]
                and record["bos_status"] == "COMPLETE"
                and record["defined_at"] is not None
                and record["defined_at"] > defined_at
                and record["bos_time"] is not None
                and record["bos_time"] > bos_time
                and record["bos_direction"] in {"BOS_UP", "BOS_DOWN"}
            ),
            key=lambda record: (record["bos_time"], record["defined_at"], record["id"]),
        )
        next_bos = later_bos[0] if later_bos else None
        next_bos_time = next_bos["bos_time"] if next_bos else None
        if next_bos is not None:
            payload.update({
                "next_bos_range_id": next_bos["id"],
                "next_bos_direction": next_bos["bos_direction"],
                "next_bos_time": _stamp(next_bos_time),
            })

        if latest_time is None or latest_time < bos_time:
            payload["reason_codes"] = ["NO_W1_CANDLES_FROM_BOS"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        candles = sorted(
            (
                candle for candle in context.load_candles(
                    timeframe="W1",
                    start_time=_stamp(bos_time),
                    end_time=_stamp(latest_time),
                )
                if (candle_time := _time(candle.get("time"))) is not None
                and bos_time <= candle_time <= latest_time
            ),
            key=lambda candle: _time(candle.get("time")) or latest_time,
        )
        bos_candle = next(
            (candle for candle in candles if _time(candle.get("time")) == bos_time),
            None,
        )
        if bos_candle is None:
            payload["reason_codes"] = ["BOS_CANDLE_NOT_AVAILABLE_FOR_RECLAIM_CHECK"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        payload["bos_candle_close"] = float(bos_candle["close"])
        if _same_candle_reclaim(bos_candle, direction, boundary):
            payload.update({
                "reclaim_status": "RECLAIMED",
                "reclaim_abbreviation": "RECL",
                "same_candle_reclaim": True,
                "reclaim_time": str(bos_candle["time"]),
                "reclaim_wick_price": float(
                    bos_candle["low"] if direction == "BOS_UP" else bos_candle["high"]
                ),
                "weeks_to_reclaim": 0,
                "reason_codes": ["BOS_CANDLE_CLOSED_BACK_THROUGH_BOUNDARY"],
            })
            outputs.append(_output(node, "COMPLETE", payload))
            continue

        later_candles = [
            candle for candle in candles
            if (_time(candle.get("time")) or bos_time) > bos_time
        ]
        reclaim = None
        reclaim_index = None
        for index, candle in enumerate(later_candles, start=1):
            payload["candles_scanned"] = index
            if _touches_boundary(candle, direction, boundary):
                reclaim = candle
                reclaim_index = index
                break

        if reclaim is not None and reclaim_index is not None:
            reclaim_time = _time(reclaim.get("time"))
            if reclaim_time is None:
                payload["reason_codes"] = ["RECLAIM_CANDLE_TIME_INVALID"]
                outputs.append(_output(node, "NEEDS_REVIEW", payload))
                continue
            if next_bos_time is not None and reclaim_time == next_bos_time:
                payload.update({
                    "reclaim_status": "NEEDS_REVIEW",
                    "reclaim_abbreviation": "REVIEW",
                    "reclaim_time": str(reclaim["time"]),
                    "reclaim_wick_price": float(
                        reclaim["low"] if direction == "BOS_UP" else reclaim["high"]
                    ),
                    "weeks_to_reclaim": reclaim_index,
                    "reason_codes": ["RECLAIM_AND_NEW_BOS_SAME_W1_ORDER_UNKNOWN"],
                })
                outputs.append(_output(node, "NEEDS_REVIEW", payload))
                continue

            abandoned_first = next_bos_time is not None and next_bos_time < reclaim_time
            weeks_to_abandonment = None
            weeks_after_abandonment = None
            if abandoned_first and next_bos_time is not None:
                weeks_to_abandonment = sum(
                    1 for candle in later_candles
                    if (_time(candle.get("time")) or latest_time) <= next_bos_time
                )
                weeks_after_abandonment = sum(
                    1 for candle in later_candles
                    if next_bos_time < (_time(candle.get("time")) or bos_time) <= reclaim_time
                )
            payload.update({
                "reclaim_status": (
                    "ABANDONED_THEN_RECLAIMED" if abandoned_first else "RECLAIMED"
                ),
                "reclaim_abbreviation": "ABND→RECL" if abandoned_first else "RECL",
                "abandoned_before_reclaim": abandoned_first,
                "reclaim_time": str(reclaim["time"]),
                "reclaim_wick_price": float(
                    reclaim["low"] if direction == "BOS_UP" else reclaim["high"]
                ),
                "weeks_to_reclaim": reclaim_index,
                "weeks_to_abandonment": weeks_to_abandonment,
                "weeks_from_abandonment_to_reclaim": weeks_after_abandonment,
                "reason_codes": (
                    ["NEW_WEEKLY_BOS_BEFORE_LATER_RECLAIM"] if abandoned_first else []
                ),
            })
            outputs.append(_output(node, "COMPLETE", payload))
            continue

        payload["candles_scanned"] = len(later_candles)
        if next_bos_time is not None and next_bos_time <= latest_time:
            weeks_to_abandonment = sum(
                1 for candle in later_candles
                if (_time(candle.get("time")) or latest_time) <= next_bos_time
            )
            payload.update({
                "reclaim_status": "ABANDONED",
                "reclaim_abbreviation": "ABND",
                "abandoned_before_reclaim": True,
                "weeks_to_abandonment": weeks_to_abandonment,
                "reason_codes": ["NEW_WEEKLY_BOS_BEFORE_RECLAIM"],
            })
            outputs.append(_output(node, "COMPLETE", payload))
            continue

        payload["reason_codes"] = ["RECLAIM_NOT_YET_PROVEN"]
        outputs.append(_output(node, "PENDING", payload))

    return {"outputs": outputs}
