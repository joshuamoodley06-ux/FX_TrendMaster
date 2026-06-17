"""Batch promote RANGE_CANDIDATE suggestions → confirmed map_ranges (UNKNOWN scale)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from detection_brain_promotion import PromotionError, review_suggestion


@dataclass
class BatchPromoteFilters:
    symbol: str
    source_timeframe: str
    structure_layer: str
    date_from_ms: int | None = None
    date_to_ms: int | None = None
    candidate_kind: str = "RANGE_CANDIDATE"
    status: str = "PENDING"
    detector_version: str | None = None
    detection_run_id: str | None = None


@dataclass
class BatchPromoteCounts:
    pending_candidates_found: int = 0
    already_promoted: int = 0
    would_promote: int = 0
    promoted: int = 0
    skipped: int = 0
    duplicate_risks: int = 0
    errors: int = 0


@dataclass
class BatchPromoteResult:
    ok: bool
    dry_run: bool
    confirmed: bool
    filters: dict[str, Any]
    counts: BatchPromoteCounts
    date_range: dict[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


def _normalise_upper(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip().upper()


def _json_loads(raw: Any) -> dict[str, Any]:
    import json

    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _date_range_label(date_from_ms: int | None, date_to_ms: int | None) -> dict[str, Any]:
    from detector.context_window import ms_to_date_label

    return {
        "date_from_ms": date_from_ms,
        "date_to_ms": date_to_ms,
        "date_from": ms_to_date_label(date_from_ms),
        "date_to": ms_to_date_label(date_to_ms),
    }


def _existing_range_for_suggestion(conn: sqlite3.Connection, suggestion_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, range_high_price, range_low_price, range_scale, confirmed_from_suggestion_id
        FROM map_ranges
        WHERE confirmed_from_suggestion_id = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (suggestion_id,),
    ).fetchone()
    return dict(row) if row else None


def _duplicate_risk_count(conn: sqlite3.Connection, suggestion_ids: list[str]) -> int:
    if not suggestion_ids:
        return 0
    placeholders = ",".join("?" for _ in suggestion_ids)
    rows = conn.execute(
        f"""
        SELECT confirmed_from_suggestion_id, COUNT(*) AS n
        FROM map_ranges
        WHERE confirmed_from_suggestion_id IN ({placeholders})
        GROUP BY confirmed_from_suggestion_id
        HAVING n > 1
        """,
        suggestion_ids,
    ).fetchall()
    return len(rows)


def _classify_candidate(
    conn: sqlite3.Connection,
    suggestion: dict[str, Any],
) -> tuple[str, str | None, int | None]:
    """Return (bucket, reason, existing_range_id)."""
    suggestion_id = str(suggestion.get("suggestion_id") or "")
    status = str(suggestion.get("status") or "").upper()
    kind = str(suggestion.get("candidate_kind") or "").upper()

    existing = _existing_range_for_suggestion(conn, suggestion_id)
    if existing:
        return "already_promoted", "map_range exists", int(existing["id"])

    if status in {"APPROVED", "EDITED"}:
        promoted_id = suggestion.get("promoted_range_id")
        return "already_promoted", f"suggestion status={status}", int(promoted_id) if promoted_id else None

    if status != "PENDING":
        return "skipped", f"status={status}", None

    if kind not in {"RANGE_CANDIDATE", "RANGE_MAJOR", "RANGE_MINOR"}:
        return "skipped", f"candidate_kind={kind}", None

    rh = suggestion.get("suggested_rh")
    rl = suggestion.get("suggested_rl")
    try:
        if rh is None or rl is None or float(rh) <= float(rl):
            return "skipped", "invalid suggested_rh/rl", None
    except (TypeError, ValueError):
        return "skipped", "invalid suggested_rh/rl", None

    return "would_promote", None, None


def query_batch_candidates(conn: sqlite3.Connection, filters: BatchPromoteFilters) -> list[dict[str, Any]]:
    clauses = [
        "symbol = ?",
        "structure_layer = ?",
        "source_timeframe = ?",
        "candidate_kind = ?",
        "status = ?",
    ]
    params: list[Any] = [
        filters.symbol.upper(),
        filters.structure_layer.upper(),
        filters.source_timeframe.upper(),
        _normalise_upper(filters.candidate_kind) or "RANGE_CANDIDATE",
        _normalise_upper(filters.status) or "PENDING",
    ]

    if filters.date_from_ms is not None:
        clauses.append("candle_time_utc_ms >= ?")
        params.append(int(filters.date_from_ms))
    if filters.date_to_ms is not None:
        clauses.append("candle_time_utc_ms <= ?")
        params.append(int(filters.date_to_ms))
    if filters.detector_version:
        clauses.append("detector_version = ?")
        params.append(str(filters.detector_version))

    rows = conn.execute(
        f"""
        SELECT *
        FROM detector_suggestions
        WHERE {' AND '.join(clauses)}
        ORDER BY candle_time_utc_ms ASC, created_at_utc_ms ASC
        """,
        params,
    ).fetchall()

    out: list[dict[str, Any]] = []
    run_id = str(filters.detection_run_id or "").strip() or None
    for row in rows:
        item = dict(row)
        item["meta_json"] = _json_loads(item.get("meta_json"))
        if run_id and str((item.get("meta_json") or {}).get("detection_run_id") or "") != run_id:
            continue
        out.append(item)
    return out


def batch_promote_range_candidates(
    conn: sqlite3.Connection,
    filters: BatchPromoteFilters,
    *,
    confirm: bool = False,
) -> BatchPromoteResult:
    dry_run = not confirm
    candidates = query_batch_candidates(conn, filters)
    counts = BatchPromoteCounts(pending_candidates_found=len(candidates))
    items: list[dict[str, Any]] = []

    suggestion_ids = [str(c.get("suggestion_id") or "") for c in candidates if c.get("suggestion_id")]
    counts.duplicate_risks = _duplicate_risk_count(conn, suggestion_ids)

    if not dry_run:
        conn.execute("PRAGMA busy_timeout = 60000")

    for suggestion in candidates:
        suggestion_id = str(suggestion.get("suggestion_id") or "")
        bucket, reason, existing_range_id = _classify_candidate(conn, suggestion)
        item: dict[str, Any] = {
            "suggestion_id": suggestion_id,
            "candidate_kind": suggestion.get("candidate_kind"),
            "candle_time_utc_ms": suggestion.get("candle_time_utc_ms"),
            "suggested_rh": suggestion.get("suggested_rh"),
            "suggested_rl": suggestion.get("suggested_rl"),
            "detector_version": suggestion.get("detector_version"),
            "bucket": bucket,
            "reason": reason,
            "existing_range_id": existing_range_id,
        }

        if bucket == "already_promoted":
            counts.already_promoted += 1
            items.append(item)
            continue

        if bucket == "skipped":
            counts.skipped += 1
            items.append(item)
            continue

        counts.would_promote += 1
        if dry_run:
            items.append(item)
            continue

        try:
            result = review_suggestion(conn, suggestion_id, action="BATCH_APPROVE", commit=False)
            if result.get("duplicate"):
                counts.already_promoted += 1
                item["bucket"] = "already_promoted"
                item["reason"] = "duplicate on promote"
                item["existing_range_id"] = result.get("promoted_range_id") or (
                    (result.get("suggestion") or {}).get("promoted_range_id")
                )
            else:
                counts.promoted += 1
                item["bucket"] = "promoted"
                item["promoted_range_id"] = result.get("promoted_range_id")
                item["correction_id"] = result.get("correction_id")
        except PromotionError as exc:
            counts.errors += 1
            item["bucket"] = "error"
            item["reason"] = str(exc)
        items.append(item)

    if not dry_run and (counts.promoted > 0 or counts.already_promoted > 0):
        conn.commit()

    date_range = _date_range_label(filters.date_from_ms, filters.date_to_ms)
    if dry_run:
        message = (
            f"dry-run: pending={counts.pending_candidates_found} "
            f"already_promoted={counts.already_promoted} "
            f"would_promote={counts.would_promote} "
            f"skipped={counts.skipped} "
            f"duplicate_risks={counts.duplicate_risks}"
        )
    else:
        message = (
            f"confirmed: promoted={counts.promoted} "
            f"already_promoted={counts.already_promoted} "
            f"skipped={counts.skipped} "
            f"errors={counts.errors}"
        )

    return BatchPromoteResult(
        ok=counts.errors == 0 or dry_run,
        dry_run=dry_run,
        confirmed=confirm,
        filters={
            "symbol": filters.symbol.upper(),
            "source_timeframe": filters.source_timeframe.upper(),
            "structure_layer": filters.structure_layer.upper(),
            "candidate_kind": filters.candidate_kind,
            "status": filters.status,
            "detector_version": filters.detector_version,
            "detection_run_id": filters.detection_run_id,
        },
        counts=counts,
        date_range=date_range,
        items=items,
        message=message,
    )


def batch_promote_result_to_dict(result: BatchPromoteResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "dry_run": result.dry_run,
        "confirmed": result.confirmed,
        "message": result.message,
        "filters": result.filters,
        "date_range": result.date_range,
        "counts": {
            "pending_candidates_found": result.counts.pending_candidates_found,
            "already_promoted": result.counts.already_promoted,
            "would_promote": result.counts.would_promote,
            "promoted": result.counts.promoted,
            "skipped": result.counts.skipped,
            "duplicate_risks": result.counts.duplicate_risks,
            "errors": result.counts.errors,
        },
        "items": result.items,
    }
