"""Load and validate an analyst_input_v1 package written by Electron.

The loader is tolerant: structural problems become audit warnings, not
crashes. Only an unreadable file or non-JSON content is a hard error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analyst import ANALYST_INPUT_SCHEMA
from analyst.audit.audit_warnings import AuditWarning
from analyst.models.records import Candle, EventRecord, InputPackage, RangeRecord, opt_str


def load_input_package(path: str | Path) -> tuple[InputPackage, list[AuditWarning]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"input package is not a JSON object: {path}")

    warnings: list[AuditWarning] = []

    schema_version = opt_str(raw.get("schema_version"))
    if schema_version != ANALYST_INPUT_SCHEMA:
        warnings.append(
            AuditWarning(
                code="INPUT_SCHEMA_UNEXPECTED",
                message=f"expected schema_version {ANALYST_INPUT_SCHEMA}, got {schema_version!r}",
            )
        )

    symbol = opt_str(raw.get("symbol")) or "UNKNOWN"
    label = opt_str(raw.get("label")) or symbol
    if not opt_str(raw.get("symbol")):
        warnings.append(AuditWarning(code="INPUT_MISSING_SYMBOL", message="input package has no symbol"))

    year = _parse_year(raw.get("year"))
    if year is None:
        warnings.append(AuditWarning(code="INPUT_MISSING_YEAR", message="input package has no usable year"))

    case_refs = [ref for ref in (opt_str(x) for x in raw.get("case_refs") or []) if ref]
    if not case_refs:
        warnings.append(
            AuditWarning(code="INPUT_NO_CASE_REFS", message="no case_refs selected; nothing will be analyzed")
        )

    data = raw.get("data") or {}

    ranges = _parse_ranges(data.get("ranges") or [], warnings)
    events = _parse_events(data.get("events") or [], warnings)
    candles = _parse_candles(data.get("candles") or {}, warnings)
    raw_ledgers = data.get("raw_ledgers") or {}
    if not isinstance(raw_ledgers, dict):
        warnings.append(AuditWarning(code="INPUT_BAD_RAW_LEDGERS", message="data.raw_ledgers is not an object"))
        raw_ledgers = {}

    package = InputPackage(
        schema_version=schema_version,
        symbol=symbol,
        year=year,
        label=label,
        case_refs=case_refs,
        generated_at_utc_ms=_parse_year_safe_int(raw.get("generated_at_utc_ms")),
        source=raw.get("source") or {},
        ranges=ranges,
        events=events,
        candles=candles,
        raw_ledgers=raw_ledgers,
        raw=raw,
    )

    warnings.extend(_cross_check(package))
    return package, warnings


def _parse_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1970 <= year <= 2200 else None


def _parse_year_safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_ranges(rows: list[Any], warnings: list[AuditWarning]) -> list[RangeRecord]:
    out: list[RangeRecord] = []
    seen_ids: set[str] = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(AuditWarning(code="RANGE_ROW_INVALID", message=f"ranges[{idx}] is not an object"))
            continue
        rng = RangeRecord.from_dict(row)
        if rng.range_id is None:
            warnings.append(
                AuditWarning(code="RANGE_MISSING_ID", case_ref=rng.case_ref, message=f"ranges[{idx}] has no id")
            )
        elif rng.range_id in seen_ids:
            warnings.append(
                AuditWarning(
                    code="DUPLICATE_RANGE_ID",
                    case_ref=rng.case_ref,
                    subject_id=rng.range_id,
                    message=f"range id {rng.range_id} appears more than once",
                )
            )
        else:
            seen_ids.add(rng.range_id)
        if (
            rng.range_high_price is not None
            and rng.range_low_price is not None
            and rng.range_high_price < rng.range_low_price
        ):
            warnings.append(
                AuditWarning(
                    code="RANGE_PRICES_INVERTED",
                    case_ref=rng.case_ref,
                    subject_id=rng.range_id,
                    message=f"range_high_price {rng.range_high_price} < range_low_price {rng.range_low_price}",
                )
            )
        out.append(rng)
    return out


def _parse_events(rows: list[Any], warnings: list[AuditWarning]) -> list[EventRecord]:
    out: list[EventRecord] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(AuditWarning(code="EVENT_ROW_INVALID", message=f"events[{idx}] is not an object"))
            continue
        evt = EventRecord.from_dict(row)
        if evt.event_time_ms is None:
            warnings.append(
                AuditWarning(
                    code="EVENT_TIME_UNPARSEABLE",
                    case_ref=evt.case_ref,
                    subject_id=evt.event_id,
                    message=f"events[{idx}] has no parseable event time",
                )
            )
        out.append(evt)
    return out


def _parse_candles(
    by_timeframe: dict[str, Any], warnings: list[AuditWarning]
) -> dict[str, list[Candle]]:
    out: dict[str, list[Candle]] = {}
    for timeframe, rows in by_timeframe.items():
        if not isinstance(rows, list):
            warnings.append(
                AuditWarning(code="CANDLE_TF_INVALID", message=f"candles[{timeframe!r}] is not a list")
            )
            continue
        parsed: list[Candle] = []
        bad = 0
        for row in rows:
            candle = Candle.from_dict(row, timeframe=timeframe) if isinstance(row, dict) else None
            if candle is None or candle.time_ms is None or candle.close is None:
                bad += 1
                continue
            parsed.append(candle)
        if bad:
            warnings.append(
                AuditWarning(
                    code="CANDLE_ROWS_DROPPED",
                    message=f"{bad} unusable candle rows dropped for timeframe {timeframe}",
                )
            )
        parsed.sort(key=lambda c: c.time_ms or 0)
        out[str(timeframe)] = parsed
    return out


def _cross_check(package: InputPackage) -> list[AuditWarning]:
    warnings: list[AuditWarning] = []
    selected = set(package.case_refs)

    unselected_refs = sorted(
        {r.case_ref for r in package.ranges if r.case_ref and r.case_ref not in selected}
        | {e.case_ref for e in package.events if e.case_ref and e.case_ref not in selected}
    )
    for ref in unselected_refs:
        warnings.append(
            AuditWarning(
                code="CASE_REF_NOT_SELECTED",
                case_ref=ref,
                message="data contains rows for a case_ref that was not selected",
            )
        )

    refs_with_ranges = {r.case_ref for r in package.ranges if r.case_ref}
    for ref in package.case_refs:
        if ref not in refs_with_ranges:
            warnings.append(
                AuditWarning(
                    code="CASE_REF_EMPTY",
                    case_ref=ref,
                    message="selected case_ref has no ranges in the package",
                )
            )
    return warnings
