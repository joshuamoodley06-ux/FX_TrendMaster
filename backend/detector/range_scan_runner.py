"""Historical range scan — RANGE_CANDIDATE suggestions only, no promotion."""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from detection_brain_store import new_uuid, utc_now_ms
from detector.context_window import build_detection_window_meta, ms_to_date_label
from detector.models import DetectionContext, NormalizedCandle, SuggestionDraft
from detector.ohlc_loader import build_context, load_context_from_db
from detector.pipeline import run_detector_v1
from detector.range_mode import RANGE_MODE_DOCTRINE_V2, resolve_range_mode
from detector.range_scale_mode import (
    CANDIDATE_KIND_RANGE,
    RANGE_SCALE_UNKNOWN,
    resolve_range_scale_mode,
)
from detector.range_seed import resolve_detector_seed_context, seed_resolution_to_meta
from detector.writer import write_suggestion

HISTORICAL_RANGE_KINDS = frozenset(
    {"RANGE_CANDIDATE", "NO_VALID_RANGE", "NO_MINOR_STRUCTURE", CANDIDATE_KIND_RANGE}
)


class HistoricalScanError(Exception):
    pass


class ConfirmedStructureMutatedError(HistoricalScanError):
    pass


@dataclass
class HistoricalRangeScanConfig:
    symbol: str = "XAUUSD"
    source_timeframe: str = "W1"
    structure_layer: str = "WEEKLY"
    date_from_ms: int | None = None
    date_to_ms: int | None = None
    range_mode: str = RANGE_MODE_DOCTRINE_V2
    range_scale_mode: str = "generic"
    detection_run_id: str | None = None
    parent_range_id: int | None = None
    candidate_kind_filter: str | None = None
    candle_limit: int = 5000
    max_steps: int | None = None
    dry_run: bool = False


@dataclass
class HistoricalRangeScanResult:
    symbol: str
    source_timeframe: str
    structure_layer: str
    date_from_ms: int | None
    date_to_ms: int | None
    detection_run_id: str
    candles_scanned: int = 0
    suggestions_created: int = 0
    range_candidate_count: int = 0
    no_valid_range_count: int = 0
    no_minor_structure_count: int = 0
    superseded_count: int = 0
    first_suggestion_time_ms: int | None = None
    last_suggestion_time_ms: int | None = None
    dry_run: bool = False
    map_ranges_before: int = 0
    map_ranges_after: int = 0
    map_events_before: int = 0
    map_events_after: int = 0
    saved_rows: list[dict[str, Any]] = field(default_factory=list)


def parse_scan_date_ms(value: str) -> int:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    from detector.normalize import parse_time_to_ms

    ms = parse_time_to_ms(text)
    if ms <= 0:
        raise HistoricalScanError(f"invalid date: {value!r}")
    return ms


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"] if row else 0)


def _index_bounds(
    candles: list[NormalizedCandle],
    *,
    date_from_ms: int | None,
    date_to_ms: int | None,
) -> tuple[int, int]:
    if not candles:
        return 0, 0
    start = 0
    end = len(candles) - 1
    if date_from_ms is not None and date_from_ms > 0:
        for i, c in enumerate(candles):
            if c.time_ms >= date_from_ms:
                start = i
                break
    if date_to_ms is not None and date_to_ms > 0:
        for i in range(len(candles) - 1, -1, -1):
            if candles[i].time_ms <= date_to_ms:
                end = i
                break
    if start > end:
        return end, end
    return start, end


def _range_drafts_from_result(drafts: list[SuggestionDraft]) -> list[SuggestionDraft]:
    out: list[SuggestionDraft] = []
    for draft in drafts:
        kind = str(draft.candidate_kind or "").upper()
        if kind in HISTORICAL_RANGE_KINDS or draft.primitive == "RANGE":
            if kind in {"RANGE_MAJOR", "RANGE_MINOR"}:
                continue
            out.append(draft)
    return out


def _apply_candidate_filter(
    drafts: list[SuggestionDraft],
    *,
    candidate_kind_filter: str | None,
) -> list[SuggestionDraft]:
    if not candidate_kind_filter:
        return drafts
    want = str(candidate_kind_filter).strip().upper()
    return [d for d in drafts if str(d.candidate_kind or "").upper() == want]


def _supersede_pending_for_detection_run(
    conn: sqlite3.Connection,
    *,
    detection_run_id: str,
    symbol: str,
    structure_layer: str,
    source_timeframe: str,
) -> int:
    now_ms = utc_now_ms()
    cur = conn.execute(
        """
        UPDATE detector_suggestions
        SET status = 'SUPERSEDED', updated_at_utc_ms = ?
        WHERE status = 'PENDING'
          AND symbol = ?
          AND structure_layer = ?
          AND source_timeframe = ?
          AND json_extract(meta_json, '$.detection_run_id') = ?
          AND json_extract(meta_json, '$.historical_scan') = 1
        """,
        (
            now_ms,
            symbol.upper(),
            structure_layer.upper(),
            source_timeframe.upper(),
            detection_run_id,
        ),
    )
    return int(cur.rowcount or 0)


def _attach_scan_meta(
    draft: SuggestionDraft,
    *,
    detection_run_id: str,
    scan_step_index: int,
    scan_step_offset: int,
    date_from_ms: int | None,
    date_to_ms: int | None,
) -> None:
    meta = dict(draft.meta_json or {})
    meta["historical_scan"] = True
    meta["detection_run_id"] = detection_run_id
    meta["scan_step_index"] = scan_step_index
    meta["scan_step_offset"] = scan_step_offset
    meta["date_from_ms"] = date_from_ms
    meta["date_to_ms"] = date_to_ms
    draft.meta_json = meta
    draft.candidate_index = scan_step_offset


def run_historical_range_scan(
    conn: sqlite3.Connection,
    config: HistoricalRangeScanConfig,
    *,
    candles: list[NormalizedCandle] | None = None,
) -> HistoricalRangeScanResult:
    """
    Walk replay steps across a date window; store RANGE_V2 generic suggestions only.
    Never promotes to map_ranges / map_events.
    """
    symbol = str(config.symbol).upper()
    tf = str(config.source_timeframe).upper()
    layer = str(config.structure_layer).upper()
    range_mode = resolve_range_mode(config.range_mode)
    scale_mode = resolve_range_scale_mode(config.range_scale_mode)
    run_id = config.detection_run_id or new_uuid()

    map_ranges_before = _table_count(conn, "map_ranges")
    map_events_before = _table_count(conn, "map_events")

    if candles is None:
        ctx_boot = load_context_from_db(
            symbol=symbol,
            source_timeframe=tf,
            structure_layer=layer,
            replay_until_time_ms=config.date_to_ms,
            visible_from_time_ms=None,
            limit=config.candle_limit,
            parent_range_id=config.parent_range_id,
            range_scale=RANGE_SCALE_UNKNOWN,
            detection_run_id=run_id,
        )
        candles = ctx_boot.candles

    start_idx, end_idx = _index_bounds(
        candles,
        date_from_ms=config.date_from_ms,
        date_to_ms=config.date_to_ms,
    )
    if config.max_steps is not None:
        end_idx = min(end_idx, start_idx + max(0, int(config.max_steps) - 1))

    superseded_count = 0
    if not config.dry_run:
        superseded_count = _supersede_pending_for_detection_run(
            conn,
            detection_run_id=run_id,
            symbol=symbol,
            structure_layer=layer,
            source_timeframe=tf,
        )

    saved_rows: list[dict[str, Any]] = []
    range_candidate_count = 0
    no_valid_range_count = 0
    no_minor_structure_count = 0
    first_ms: int | None = None
    last_ms: int | None = None
    steps = 0

    for idx in range(start_idx, end_idx + 1):
        window = candles[: idx + 1]
        if not window:
            continue
        steps += 1
        replay_ms = window[idx].time_ms
        ctx = build_context(
            symbol=symbol,
            source_timeframe=tf,
            structure_layer=layer,
            candles=window,
            active_index=idx,
            replay_until_time_ms=replay_ms,
            visible_from_time_ms=config.date_from_ms,
            detection_run_id=run_id,
            parent_range_id=config.parent_range_id,
            range_scale=RANGE_SCALE_UNKNOWN,
        )

        seed_resolution = resolve_detector_seed_context(
            conn,
            {},
            symbol=symbol,
            structure_layer=layer,
            source_timeframe=tf,
            parent_range_id=config.parent_range_id,
        )
        if seed_resolution.seed is not None:
            seed = seed_resolution.seed
            ctx.range_seed = seed
            ctx.range_seed_meta = seed_resolution_to_meta(seed_resolution)
            ctx.range_high = seed.range_high
            ctx.range_low = seed.range_low
            ctx.active_range_id = seed.active_range_id
            if seed.parent_range_id is not None:
                ctx.parent_range_id = seed.parent_range_id

        ctx.detection_window_meta = build_detection_window_meta(ctx, detection_run_id=run_id)
        ctx.detection_window_meta["historical_scan"] = True

        result = run_detector_v1(ctx, range_mode=range_mode, scale_mode=scale_mode)
        range_drafts = _apply_candidate_filter(
            _range_drafts_from_result(result.drafts),
            candidate_kind_filter=config.candidate_kind_filter,
        )
        if not range_drafts:
            continue

        step_offset = idx - start_idx
        for draft in range_drafts:
            kind = str(draft.candidate_kind or "").upper()
            if kind == "RANGE_CANDIDATE":
                range_candidate_count += 1
            elif kind == "NO_VALID_RANGE":
                no_valid_range_count += 1
            elif kind == "NO_MINOR_STRUCTURE":
                no_minor_structure_count += 1

            _attach_scan_meta(
                draft,
                detection_run_id=run_id,
                scan_step_index=idx,
                scan_step_offset=step_offset,
                date_from_ms=config.date_from_ms,
                date_to_ms=config.date_to_ms,
            )

            if config.dry_run:
                continue

            saved = write_suggestion(
                conn,
                draft,
                ctx,
                supersede_on_conflict=True,
            )
            saved_rows.append(saved)
            t_ms = int(saved.get("candle_time_utc_ms") or replay_ms)
            if first_ms is None or t_ms < first_ms:
                first_ms = t_ms
            if last_ms is None or t_ms > last_ms:
                last_ms = t_ms

    if not config.dry_run:
        conn.commit()

    map_ranges_after = _table_count(conn, "map_ranges")
    map_events_after = _table_count(conn, "map_events")
    if map_ranges_before != map_ranges_after or map_events_before != map_events_after:
        raise ConfirmedStructureMutatedError(
            f"confirmed structure mutated: map_ranges {map_ranges_before}->{map_ranges_after}, "
            f"map_events {map_events_before}->{map_events_after}"
        )

    return HistoricalRangeScanResult(
        symbol=symbol,
        source_timeframe=tf,
        structure_layer=layer,
        date_from_ms=config.date_from_ms,
        date_to_ms=config.date_to_ms,
        detection_run_id=run_id,
        candles_scanned=steps,
        suggestions_created=len(saved_rows),
        range_candidate_count=range_candidate_count,
        no_valid_range_count=no_valid_range_count,
        no_minor_structure_count=no_minor_structure_count,
        superseded_count=superseded_count,
        first_suggestion_time_ms=first_ms,
        last_suggestion_time_ms=last_ms,
        dry_run=config.dry_run,
        map_ranges_before=map_ranges_before,
        map_ranges_after=map_ranges_after,
        map_events_before=map_events_before,
        map_events_after=map_events_after,
        saved_rows=saved_rows,
    )


def format_scan_summary(result: HistoricalRangeScanResult) -> str:
    lines = [
        "Historical Range Scan Summary",
        f"  symbol:              {result.symbol}",
        f"  timeframe:           {result.source_timeframe}",
        f"  layer:               {result.structure_layer}",
        f"  date_from:           {ms_to_date_label(result.date_from_ms) or '—'}",
        f"  date_to:             {ms_to_date_label(result.date_to_ms) or '—'}",
        f"  detection_run_id:    {result.detection_run_id}",
        f"  dry_run:             {result.dry_run}",
        f"  candles_scanned:     {result.candles_scanned}",
        f"  suggestions_created: {result.suggestions_created}",
        f"  RANGE_CANDIDATE:     {result.range_candidate_count}",
        f"  NO_VALID_RANGE:      {result.no_valid_range_count}",
        f"  NO_MINOR_STRUCTURE:  {result.no_minor_structure_count}",
        f"  superseded_count:    {result.superseded_count}",
        f"  first_suggestion:    {ms_to_date_label(result.first_suggestion_time_ms) or '—'}",
        f"  last_suggestion:     {ms_to_date_label(result.last_suggestion_time_ms) or '—'}",
        f"  map_ranges:          {result.map_ranges_before} (unchanged)",
        f"  map_events:          {result.map_events_before} (unchanged)",
    ]
    return "\n".join(lines)


def sample_scan_suggestions(
    conn: sqlite3.Connection,
    *,
    detection_run_id: str,
    sample_n: int = 5,
    candidate_kind: str | None = "RANGE_CANDIDATE",
) -> list[dict[str, Any]]:
    import json

    rows = conn.execute(
        """
        SELECT *
        FROM detector_suggestions
        WHERE json_extract(meta_json, '$.detection_run_id') = ?
          AND json_extract(meta_json, '$.historical_scan') = 1
        ORDER BY created_at_utc_ms ASC
        """,
        (detection_run_id,),
    ).fetchall()

    parsed: list[dict[str, Any]] = []
    want = str(candidate_kind or "").strip().upper() or None
    for row in rows:
        item = dict(row)
        meta_raw = item.get("meta_json")
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        except json.JSONDecodeError:
            meta = {}
        item["meta_json"] = meta
        kind = str(item.get("candidate_kind") or "").upper()
        if want and kind != want:
            continue
        parsed.append(item)

    if not parsed:
        return []
    n = min(max(1, int(sample_n)), len(parsed))
    return random.sample(parsed, n)


def format_audit_sample(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Audit sample: (no matching suggestions)"
    lines = ["Audit sample:"]
    for row in rows:
        meta = row.get("meta_json") or {}
        lines.append(
            "  - "
            f"id={row.get('suggestion_id')} "
            f"replay={meta.get('replay_until_time') or meta.get('replay_until_time_ms')} "
            f"RH={row.get('suggested_rh')} RL={row.get('suggested_rl')} "
            f"ver={row.get('detector_version')} "
            f"life={meta.get('lifecycle_state')} "
            f"seed={meta.get('seed_source')} "
            f"bos={meta.get('bos_suggestion_id') or meta.get('bos_event_id')} "
            f"reclaim={meta.get('reclaim_suggestion_id') or meta.get('reclaim_event_id')} "
            f"boundary={meta.get('boundary_selection_reason')} "
            f"conf={row.get('confidence')}"
        )
    return "\n".join(lines)
