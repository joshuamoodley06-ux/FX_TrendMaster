"""Shared factual helpers for the isolated Daily doctrine drafts.

Nothing in this module writes hierarchy, registers scripts, or mutates approved
memory. The helpers only read the doctrine context supplied by the existing
runtime test harness.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

EPSILON = 1e-9
VALID_PARENT_LINKS = {"VALID", "TRUSTED"}


def time_value(value: Any) -> datetime | None:
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


def stamp(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def memory_entry(
    context: Any,
    canonical_range_id: str,
    key: str,
) -> tuple[dict[str, Any] | None, str]:
    memory = context.approved_memory(canonical_range_id)
    if not isinstance(memory, Mapping):
        return None, "MISSING"
    entry = memory.get(key)
    if not isinstance(entry, Mapping):
        return None, "MISSING"
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        return None, "MISSING"
    return dict(payload), str(entry.get("processing_status") or "").upper()


def selected_nodes(context: Any, layer: str) -> list[dict[str, Any]]:
    return [dict(node) for node in context.selected_ranges(layer=layer)]


def node_id(node: Mapping[str, Any]) -> str:
    return str(node.get("id") or "")


def range_anchor_times(node: Mapping[str, Any]) -> tuple[datetime | None, datetime | None]:
    return time_value(node.get("range_high_time")), time_value(node.get("range_low_time"))


def range_defined_at(node: Mapping[str, Any]) -> datetime | None:
    high_time, low_time = range_anchor_times(node)
    if high_time is None or low_time is None:
        return None
    return max(high_time, low_time)


def range_start_at(node: Mapping[str, Any]) -> datetime | None:
    high_time, low_time = range_anchor_times(node)
    times = [value for value in (high_time, low_time) if value is not None]
    return min(times) if times else None


def anchor_chronology(node: Mapping[str, Any], suffix: str = "D1") -> tuple[str, str | None]:
    high_time, low_time = range_anchor_times(node)
    if high_time is None or low_time is None:
        return "PENDING", None
    if high_time == low_time:
        return f"SAME_{suffix}", None
    if low_time < high_time:
        return "RL_TO_RH", "UP"
    return "RH_TO_RL", "DOWN"


def structural_direction(node: Mapping[str, Any]) -> str:
    _, direction = anchor_chronology(node)
    return direction or "UNRESOLVED"


def candle_rows(
    context: Any,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    exclude_start: bool = False,
    exclude_end: bool = False,
) -> list[dict[str, Any]]:
    raw = context.load_candles(
        timeframe=timeframe,
        start_time=stamp(start),
        end_time=stamp(end),
    )
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        when = time_value(row.get("time"))
        if when is None:
            continue
        if exclude_start and when <= start:
            continue
        if not exclude_start and when < start:
            continue
        if exclude_end and when >= end:
            continue
        if not exclude_end and when > end:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (time_value(row.get("time")) or end, str(row.get("time") or "")))
    return rows


def latest_time(context: Any, timeframe: str) -> datetime | None:
    try:
        return time_value(context.latest_candle_time(timeframe))
    except Exception:
        return None


def period_count(start: datetime | None, end: datetime | None, seconds: int = 86_400) -> int | None:
    if start is None or end is None or end < start:
        return None
    return int((end - start).total_seconds() // seconds)


def node_index(context: Any, layer: str) -> dict[str, dict[str, Any]]:
    return {node_id(node): node for node in selected_nodes(context, layer) if node_id(node)}


def weekly_parent_map(context: Any) -> dict[str, str]:
    """Read trusted Daily children from the canonical Weekly hierarchy.

    The function never infers a parent from dates or prices. A Daily range absent
    from the trusted Weekly children remains parentless in the draft output.
    """
    result: dict[str, str] = {}
    for weekly in selected_nodes(context, "WEEKLY"):
        weekly_id = node_id(weekly)
        children = weekly.get("children")
        if not weekly_id or not isinstance(children, list):
            continue
        for raw_child in children:
            if not isinstance(raw_child, Mapping):
                continue
            if str(raw_child.get("structure_layer") or "").upper() != "DAILY":
                continue
            child_id = node_id(raw_child)
            link = str(raw_child.get("direct_parent_link_status") or "").upper()
            if child_id and link in VALID_PARENT_LINKS:
                result[child_id] = weekly_id
    return result


def weekly_children(context: Any, weekly_id: str) -> list[dict[str, Any]]:
    for weekly in selected_nodes(context, "WEEKLY"):
        if node_id(weekly) != weekly_id:
            continue
        raw_children = weekly.get("children")
        children = [
            dict(child)
            for child in raw_children
            if isinstance(raw_children, list)
            and isinstance(child, Mapping)
            and str(child.get("structure_layer") or "").upper() == "DAILY"
            and str(child.get("direct_parent_link_status") or "").upper() in VALID_PARENT_LINKS
        ] if isinstance(raw_children, list) else []
        children.sort(key=lambda child: (
            stamp(range_defined_at(child)) or "9999",
            stamp(range_start_at(child)) or "9999",
            node_id(child),
        ))
        return children
    return []


def relationship_rows(context: Any, weekly_id: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str]:
    payload, processing = memory_entry(context, weekly_id, "weekly_daily_relationship_builder")
    if payload is None:
        return [], None, processing
    raw_rows = payload.get("relationship_rows")
    rows = [dict(row) for row in raw_rows if isinstance(row, Mapping)] if isinstance(raw_rows, list) else []
    rows.sort(key=lambda row: (
        int(row.get("daily_sequence_number") or 10**9),
        str(row.get("daily_created_time") or "9999"),
        str(row.get("daily_range_id") or ""),
    ))
    return rows, payload, processing


def historical_valid_relationships(context: Any, weekly_id: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str]:
    rows, payload, processing = relationship_rows(context, weekly_id)
    return [
        row for row in rows
        if row.get("historically_available") is True
        and row.get("relationship_valid") is True
    ], payload, processing


def weekly_prices(node: Mapping[str, Any]) -> tuple[float | None, float | None]:
    return number(node.get("range_high")), number(node.get("range_low"))


def zone_levels(high: float, low: float) -> dict[str, float]:
    size = high - low
    return {
        "external_low": low,
        "discount_ceiling": low + size * 0.25,
        "fair_price": low + size * 0.50,
        "premium_floor": low + size * 0.75,
        "external_high": high,
    }


def weekly_zone(price: float, high: float, low: float) -> str:
    levels = zone_levels(high, low)
    if price < low - EPSILON:
        return "EXTERNAL_LOW"
    if abs(price - low) <= EPSILON:
        return "AT_EXTERNAL_LOW"
    if price <= levels["discount_ceiling"] + EPSILON:
        return "DISCOUNT_EXTREME"
    if price < levels["fair_price"] - EPSILON:
        return "INTERNAL_DISCOUNT"
    if abs(price - levels["fair_price"]) <= EPSILON:
        return "FAIR_PRICE"
    if price < levels["premium_floor"] - EPSILON:
        return "INTERNAL_PREMIUM"
    if price < high - EPSILON:
        return "PREMIUM_EXTREME"
    if abs(price - high) <= EPSILON:
        return "AT_EXTERNAL_HIGH"
    return "EXTERNAL_HIGH"


def inside_weekly(price: float, high: float, low: float) -> bool:
    return low + EPSILON < price < high - EPSILON


def same_parent_candidates(
    context: Any,
    source_daily_id: str,
    candidates: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    parents = weekly_parent_map(context)
    parent_id = parents.get(source_daily_id)
    if not parent_id:
        return []
    return [dict(node) for node in candidates if parents.get(node_id(node)) == parent_id]


def next_completed_structure(
    context: Any,
    source_id: str,
    source_bos_time: datetime,
    memory_key: str = "daily_structure",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    candidates: list[tuple[datetime, str, dict[str, Any], dict[str, Any]]] = []
    for node in same_parent_candidates(context, source_id, selected_nodes(context, "DAILY")):
        candidate_id = node_id(node)
        if not candidate_id or candidate_id == source_id:
            continue
        structure, processing = memory_entry(context, candidate_id, memory_key)
        if structure is None or processing not in {"", "COMPLETE"}:
            continue
        bos_time = time_value(structure.get("bos_time"))
        if bos_time is None or bos_time <= source_bos_time:
            continue
        candidates.append((bos_time, candidate_id, node, structure))
    candidates.sort(key=lambda item: (item[0], item[1]))
    if not candidates:
        return None, None
    return candidates[0][2], candidates[0][3]


def row_interval(
    row: Mapping[str, Any],
    next_row: Mapping[str, Any] | None,
    freeze: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start = time_value(row.get("daily_created_time")) or time_value(row.get("daily_start_time"))
    end = time_value(row.get("daily_end_time"))
    next_start = time_value(next_row.get("daily_created_time")) if next_row else None
    candidates = [value for value in (end, next_start, freeze) if value is not None]
    return start, min(candidates) if candidates else None


def candle_body_direction(candle: Mapping[str, Any]) -> str:
    open_price = number(candle.get("open"))
    close_price = number(candle.get("close"))
    if open_price is None or close_price is None:
        return "INVALID"
    if close_price > open_price + EPSILON:
        return "UP"
    if close_price < open_price - EPSILON:
        return "DOWN"
    return "DOJI"


def range_direction_from_row(row: Mapping[str, Any]) -> str:
    direction = str(row.get("daily_direction") or "").upper()
    return direction if direction in {"UP", "DOWN"} else "UNRESOLVED"
