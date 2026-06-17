"""Active range seed context loading for RANGE_V2 (Phase E)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from detector.range_state import RangeSeedContext

try:
    from candle_store import (
        _normalise_structure_layer,
        _normalize_range_status,
        _range_row_to_dict,
        normalise_timeframe,
        parse_float,
    )
except ImportError:  # pragma: no cover
    _normalise_structure_layer = None  # type: ignore[assignment]
    _normalize_range_status = None
    _range_row_to_dict = None
    normalise_timeframe = None
    parse_float = None

SEED_SOURCE_EXPLICIT = "explicit_payload"
SEED_SOURCE_ELECTRON = "electron_selected_range"
SEED_SOURCE_BACKEND = "backend_active_lookup"
SEED_SOURCE_NONE = "none"

SEED_LOOKUP_MULTIPLE = "MULTIPLE_ACTIVE_RANGES"
SEED_LOOKUP_MISMATCH = "RANGE_MISMATCH"
SEED_LOOKUP_NOT_ACTIVE = "RANGE_NOT_ACTIVE"
SEED_LOOKUP_NOT_FOUND = "RANGE_NOT_FOUND"

SUITABLE_SEED_STATUSES = frozenset({"ACTIVE"})


@dataclass(frozen=True)
class SeedResolutionResult:
    seed: RangeSeedContext | None = None
    seed_source: str = SEED_SOURCE_NONE
    seed_lookup_error: str | None = None

    @property
    def no_seed_context(self) -> bool:
        return self.seed is None


def _norm_layer(layer: str | None, source_timeframe: str) -> str:
    tf = normalise_timeframe(source_timeframe) if normalise_timeframe else str(source_timeframe).upper()
    if _normalise_structure_layer:
        return _normalise_structure_layer(layer or "", tf)
    return str(layer or "").strip().upper()


def _norm_status(value: Any) -> str | None:
    if _normalize_range_status:
        return _normalize_range_status(value)
    raw = str(value or "ACTIVE").strip().upper()
    return raw or "ACTIVE"


def _norm_tf(value: Any, fallback: str) -> str:
    if normalise_timeframe:
        return normalise_timeframe(str(value or fallback))
    return str(value or fallback).upper()


def _row_high_low(row: dict[str, Any]) -> tuple[float | None, float | None]:
    high = parse_float(row.get("range_high_price", row.get("range_high")), None) if parse_float else None
    low = parse_float(row.get("range_low_price", row.get("range_low")), None) if parse_float else None
    if high is None:
        try:
            high = float(row.get("range_high"))
        except (TypeError, ValueError):
            high = None
    if low is None:
        try:
            low = float(row.get("range_low"))
        except (TypeError, ValueError):
            low = None
    return high, low


def _seed_from_row(row: dict[str, Any], *, seed_source: str) -> RangeSeedContext | None:
    high, low = _row_high_low(row)
    if high is None or low is None or high <= low:
        return None
    scale = str(row.get("range_scale") or row.get("range_scope") or "MAJOR").strip().upper()
    role = row.get("range_role")
    if not role:
        role = "ACTIVE_CONTAINER" if scale == "MAJOR" else "INTERNAL_LEG"
    parent_raw = row.get("parent_range_id")
    parent_id: int | None
    try:
        parent_id = int(parent_raw) if parent_raw not in (None, "") else None
    except (TypeError, ValueError):
        parent_id = None
    range_id_raw = row.get("range_id", row.get("id"))
    try:
        range_id = int(range_id_raw) if range_id_raw not in (None, "") else None
    except (TypeError, ValueError):
        range_id = None
    return RangeSeedContext(
        range_high=float(high),
        range_low=float(low),
        active_range_id=range_id,
        is_manual_seed=False,
        range_scale=scale,
        range_role=str(role) if role else None,
        parent_range_id=parent_id,
        structure_layer=str(row.get("structure_layer") or row.get("layer") or "").strip().upper() or None,
        source_timeframe=_norm_tf(row.get("source_timeframe") or row.get("timeframe"), "D1"),
        status=_norm_status(row.get("status")),
        seed_source=seed_source,
    )


def _row_matches_scope(
    row: dict[str, Any],
    *,
    symbol: str,
    structure_layer: str,
    source_timeframe: str,
    parent_range_id: int | None,
) -> bool:
    if str(row.get("symbol") or "").upper() != str(symbol).upper():
        return False
    layer = _norm_layer(structure_layer, source_timeframe)
    row_layer = _norm_layer(str(row.get("structure_layer") or row.get("layer") or ""), source_timeframe)
    if row_layer != layer:
        return False
    req_tf = _norm_tf(source_timeframe, source_timeframe)
    row_tf = _norm_tf(row.get("source_timeframe") or row.get("timeframe"), req_tf)
    if row_tf != req_tf:
        return False
    if parent_range_id is not None:
        try:
            row_parent = int(row.get("parent_range_id")) if row.get("parent_range_id") not in (None, "") else None
        except (TypeError, ValueError):
            return False
        if row_parent != int(parent_range_id):
            return False
    return True


def _is_suitable_seed_status(status: str | None) -> bool:
    normalized = _norm_status(status)
    return normalized in SUITABLE_SEED_STATUSES


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    if _range_row_to_dict:
        parsed = _range_row_to_dict(row)
        return parsed if parsed is not None else dict(row)
    return dict(row)


def load_active_range_seed_context(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    structure_layer: str,
    source_timeframe: str,
    parent_range_id: int | None = None,
    active_range_id: int | None = None,
) -> tuple[RangeSeedContext | None, str | None]:
    """
    Load confirmed active range seed from map_ranges.

    Returns (seed, lookup_error). Never guesses when multiple ACTIVE rows match.
    """
    sym = str(symbol).upper()
    layer = _norm_layer(structure_layer, source_timeframe)
    tf = _norm_tf(source_timeframe, source_timeframe)

    if active_range_id is not None:
        row = conn.execute("SELECT * FROM map_ranges WHERE id = ?", (int(active_range_id),)).fetchone()
        if row is None:
            return None, SEED_LOOKUP_NOT_FOUND
        data = _row_to_dict(row)
        if not _row_matches_scope(
            data,
            symbol=sym,
            structure_layer=layer,
            source_timeframe=tf,
            parent_range_id=parent_range_id,
        ):
            return None, SEED_LOOKUP_MISMATCH
        if not _is_suitable_seed_status(data.get("status")):
            return None, SEED_LOOKUP_NOT_ACTIVE
        seed = _seed_from_row(data, seed_source=SEED_SOURCE_BACKEND)
        return (seed, None) if seed else (None, SEED_LOOKUP_MISMATCH)

    clauses = [
        "symbol = ?",
        "UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'",
        "LOWER(COALESCE(status, '')) != 'archived'",
        "COALESCE(structure_layer, layer) = ?",
        "COALESCE(source_timeframe, timeframe) = ?",
    ]
    args: list[Any] = [sym, layer, tf]
    if parent_range_id is not None:
        clauses.append("parent_range_id = ?")
        args.append(int(parent_range_id))

    sql = f"SELECT * FROM map_ranges WHERE {' AND '.join(clauses)} ORDER BY id ASC"
    rows = conn.execute(sql, args).fetchall()
    if not rows:
        return None, None
    if len(rows) > 1:
        return None, SEED_LOOKUP_MULTIPLE
    data = _row_to_dict(rows[0])
    seed = _seed_from_row(data, seed_source=SEED_SOURCE_BACKEND)
    return (seed, None) if seed else (None, SEED_LOOKUP_MISMATCH)


def resolve_detector_seed_context(
    conn: sqlite3.Connection | None,
    payload: dict[str, Any],
    *,
    symbol: str,
    structure_layer: str | None,
    source_timeframe: str,
    parent_range_id: int | None = None,
) -> SeedResolutionResult:
    """
    Resolve RANGE_V2 seed with priority:
    1. explicit active_range_id (+ verified map_ranges row)
    2. electron selected range (same payload path, tagged source)
    3. backend ACTIVE lookup by symbol/layer/timeframe[/parent]
    """
    layer = _norm_layer(structure_layer, source_timeframe)
    tf = _norm_tf(source_timeframe, source_timeframe)
    sym = str(symbol).upper()

    active_raw = payload.get("active_range_id")
    active_id: int | None
    try:
        active_id = int(active_raw) if active_raw not in (None, "", 0) else None
    except (TypeError, ValueError):
        active_id = None

    if active_id is not None and conn is not None:
        seed, err = load_active_range_seed_context(
            conn,
            symbol=sym,
            structure_layer=layer,
            source_timeframe=tf,
            parent_range_id=parent_range_id,
            active_range_id=active_id,
        )
        if seed is not None:
            source = SEED_SOURCE_ELECTRON if payload.get("seed_from_electron") else SEED_SOURCE_EXPLICIT
            verified = RangeSeedContext(
                range_high=seed.range_high,
                range_low=seed.range_low,
                active_range_id=seed.active_range_id,
                is_manual_seed=False,
                range_scale=str(payload.get("range_scale") or seed.range_scale or "MAJOR").upper(),
                range_role=str(payload.get("range_role") or seed.range_role or "") or None,
                parent_range_id=seed.parent_range_id,
                structure_layer=seed.structure_layer,
                source_timeframe=seed.source_timeframe,
                status=seed.status,
                seed_source=source,
            )
            return SeedResolutionResult(seed=verified, seed_source=source)
        if err:
            return SeedResolutionResult(seed=None, seed_source=SEED_SOURCE_NONE, seed_lookup_error=err)

    if conn is not None:
        seed, err = load_active_range_seed_context(
            conn,
            symbol=sym,
            structure_layer=layer,
            source_timeframe=tf,
            parent_range_id=parent_range_id,
        )
        if err == SEED_LOOKUP_MULTIPLE:
            return SeedResolutionResult(
                seed=None,
                seed_source=SEED_SOURCE_NONE,
                seed_lookup_error=err,
            )
        if seed is not None:
            resolved = RangeSeedContext(
                range_high=seed.range_high,
                range_low=seed.range_low,
                active_range_id=seed.active_range_id,
                is_manual_seed=False,
                range_scale=seed.range_scale,
                range_role=seed.range_role,
                parent_range_id=seed.parent_range_id,
                structure_layer=seed.structure_layer,
                source_timeframe=seed.source_timeframe,
                status=seed.status,
                seed_source=SEED_SOURCE_BACKEND,
            )
            return SeedResolutionResult(seed=resolved, seed_source=SEED_SOURCE_BACKEND)

    return SeedResolutionResult(seed=None, seed_source=SEED_SOURCE_NONE)


def seed_resolution_to_meta(result: SeedResolutionResult) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "seed_source": result.seed_source,
        "no_seed_context": result.no_seed_context,
    }
    if result.seed_lookup_error:
        meta["seed_lookup_error"] = result.seed_lookup_error
    if result.seed is not None:
        meta["active_range_id"] = result.seed.active_range_id
        meta["seed_rh"] = result.seed.range_high
        meta["seed_rl"] = result.seed.range_low
        meta["seed_status"] = result.seed.status
    return meta
