"""Phase 3.5 — Detector performance metrics (measurement only).

Source of truth: ``detector_corrections`` (every reviewed suggestion).

No detector logic changes. No UI. CLI output is sufficient.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from typing import Any

from detection_brain_schema import init_detection_brain_schema

REVIEW_ACTIONS = frozenset({"APPROVE", "EDIT", "REJECT"})

# Phase 4 Guided Workflow Engine readiness thresholds (measurement gate only).
GUIDED_WORKFLOW_TRUST_THRESHOLDS: dict[str, float] = {
    "RANGE_MAJOR": 0.85,
    "BOS": 0.90,
    "SWEEP": 0.85,
}

MIN_REVIEWS_FOR_READINESS = 5

BOS_KINDS = frozenset({"BOS_UP", "BOS_DOWN"})
SWEEP_KINDS = frozenset({"SWEEP_HIGH", "SWEEP_LOW"})

READINESS_COMPONENT_KINDS: dict[str, frozenset[str]] = {
    "RANGE_MAJOR": frozenset({"RANGE_MAJOR"}),
    "BOS": BOS_KINDS,
    "SWEEP": SWEEP_KINDS,
}


@dataclass
class RateMetrics:
    total_reviewed: int
    approved: int
    edited: int
    rejected: int
    approval_rate: float | None
    edit_rate: float | None
    rejection_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceFilters:
    symbol: str | None = None
    structure_layer: str | None = None
    source_timeframe: str | None = None
    detector_version: str | None = None
    candidate_kind: str | None = None
    range_scale: str | None = None
    since_ms: int | None = None
    until_ms: int | None = None


def _row_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _counts_to_rates(approved: int, edited: int, rejected: int) -> RateMetrics:
    total = int(approved) + int(edited) + int(rejected)
    if total <= 0:
        return RateMetrics(0, 0, 0, 0, None, None, None)
    return RateMetrics(
        total_reviewed=total,
        approved=int(approved),
        edited=int(edited),
        rejected=int(rejected),
        approval_rate=approved / total,
        edit_rate=edited / total,
        rejection_rate=rejected / total,
    )


def _filter_clause(filters: PerformanceFilters, *, prefix: str = "f") -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    mapping = {
        "symbol": filters.symbol,
        "structure_layer": filters.structure_layer,
        "source_timeframe": filters.source_timeframe,
        "detector_version": filters.detector_version,
        "candidate_kind": filters.candidate_kind,
        "range_scale": filters.range_scale,
    }
    for column, value in mapping.items():
        if value not in (None, ""):
            clauses.append(f"{prefix}.{column} = ?")
            params.append(value)
    if filters.since_ms is not None:
        clauses.append(f"{prefix}.created_at_utc_ms >= ?")
        params.append(int(filters.since_ms))
    if filters.until_ms is not None:
        clauses.append(f"{prefix}.created_at_utc_ms <= ?")
        params.append(int(filters.until_ms))
    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


def _aggregate_from_facts(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
    *,
    group_by: str | None = None,
) -> list[dict[str, Any]]:
    filters = filters or PerformanceFilters()
    where_extra, params = _filter_clause(filters)
    group_select = ""
    group_clause = ""
    if group_by:
        group_select = f", f.{group_by} AS dimension"
        group_clause = f" GROUP BY f.{group_by}"

    sql = f"""
        SELECT
            COUNT(*) AS total_reviewed,
            SUM(CASE WHEN f.user_action = 'APPROVE' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN f.user_action = 'EDIT' THEN 1 ELSE 0 END) AS edited,
            SUM(CASE WHEN f.user_action = 'REJECT' THEN 1 ELSE 0 END) AS rejected
            {group_select}
        FROM v_detector_correction_facts f
        WHERE 1=1
        {where_extra}
        {group_clause}
    """
    if group_by:
        sql += f" ORDER BY f.{group_by}"
    rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        data = _row_dict(row)
        rates = _counts_to_rates(
            int(data.get("approved") or 0),
            int(data.get("edited") or 0),
            int(data.get("rejected") or 0),
        )
        item: dict[str, Any] = {
            "metrics": rates.to_dict(),
        }
        if group_by:
            item[group_by] = data.get("dimension")
        out.append(item)
    return out


def _single_metrics(conn: sqlite3.Connection, filters: PerformanceFilters | None = None) -> RateMetrics:
    rows = _aggregate_from_facts(conn, filters)
    if not rows:
        return _counts_to_rates(0, 0, 0)
    m = rows[0]["metrics"]
    return RateMetrics(**m)


def _suggestion_counts(conn: sqlite3.Connection, filters: PerformanceFilters | None = None) -> dict[str, int]:
    filters = filters or PerformanceFilters()
    clauses: list[str] = []
    params: list[Any] = []
    mapping = {
        "symbol": filters.symbol,
        "structure_layer": filters.structure_layer,
        "source_timeframe": filters.source_timeframe,
        "detector_version": filters.detector_version,
        "candidate_kind": filters.candidate_kind,
        "range_scale": filters.range_scale,
    }
    for column, value in mapping.items():
        if value not in (None, ""):
            clauses.append(f"s.{column} = ?")
            params.append(value)
    if filters.since_ms is not None:
        clauses.append("s.created_at_utc_ms >= ?")
        params.append(int(filters.since_ms))
    if filters.until_ms is not None:
        clauses.append("s.created_at_utc_ms <= ?")
        params.append(int(filters.until_ms))
    where_sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total_suggestions,
            SUM(CASE WHEN s.status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN s.status IN ('APPROVED', 'EDITED', 'REJECTED') THEN 1 ELSE 0 END) AS reviewed_status
        FROM detector_suggestions s
        WHERE 1=1
        {where_sql}
        """,
        params,
    ).fetchone()
    data = _row_dict(row)
    return {
        "total_suggestions": int(data.get("total_suggestions") or 0),
        "pending_suggestions": int(data.get("pending") or 0),
        "reviewed_by_status": int(data.get("reviewed_status") or 0),
    }


def get_detector_summary(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    """Overall detector review summary."""
    filters = filters or PerformanceFilters()
    counts = _suggestion_counts(conn, filters)
    metrics = _single_metrics(conn, filters)
    return {
        "total_suggestions": counts["total_suggestions"],
        "pending_suggestions": counts["pending_suggestions"],
        "total_reviewed": metrics.total_reviewed,
        "approved": metrics.approved,
        "edited": metrics.edited,
        "rejected": metrics.rejected,
        "approval_rate": metrics.approval_rate,
        "edit_rate": metrics.edit_rate,
        "rejection_rate": metrics.rejection_rate,
        "filters": asdict(filters),
    }


def get_detector_version_stats(
    conn: sqlite3.Connection,
    version: str,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    base = filters or PerformanceFilters()
    scoped = PerformanceFilters(**{**asdict(base), "detector_version": version})
    metrics = _single_metrics(conn, scoped)
    return {
        "detector_version": version,
        **metrics.to_dict(),
    }


def get_candidate_kind_stats(
    conn: sqlite3.Connection,
    kind: str,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    base = filters or PerformanceFilters()
    scoped = PerformanceFilters(**{**asdict(base), "candidate_kind": kind})
    metrics = _single_metrics(conn, scoped)
    return {
        "candidate_kind": kind,
        **metrics.to_dict(),
    }


def get_timeframe_stats(
    conn: sqlite3.Connection,
    timeframe: str,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    base = filters or PerformanceFilters()
    scoped = PerformanceFilters(**{**asdict(base), "source_timeframe": timeframe})
    metrics = _single_metrics(conn, scoped)
    return {
        "source_timeframe": timeframe,
        **metrics.to_dict(),
    }


def get_structure_layer_stats(
    conn: sqlite3.Connection,
    layer: str,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    base = filters or PerformanceFilters()
    scoped = PerformanceFilters(**{**asdict(base), "structure_layer": layer})
    metrics = _single_metrics(conn, scoped)
    return {
        "structure_layer": layer,
        **metrics.to_dict(),
    }


def get_range_scale_stats(
    conn: sqlite3.Connection,
    range_scale: str,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    base = filters or PerformanceFilters()
    scoped = PerformanceFilters(**{**asdict(base), "range_scale": range_scale.upper()})
    metrics = _single_metrics(conn, scoped)
    return {
        "range_scale": range_scale.upper(),
        **metrics.to_dict(),
    }


def get_detector_version_breakdown(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> list[dict[str, Any]]:
    rows = _aggregate_from_facts(conn, filters, group_by="detector_version")
    return [
        {"detector_version": r["detector_version"], **r["metrics"]}
        for r in rows
    ]


def get_candidate_kind_breakdown(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> list[dict[str, Any]]:
    rows = _aggregate_from_facts(conn, filters, group_by="candidate_kind")
    return [
        {"candidate_kind": r["candidate_kind"], **r["metrics"]}
        for r in rows
    ]


def get_timeframe_breakdown(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> list[dict[str, Any]]:
    rows = _aggregate_from_facts(conn, filters, group_by="source_timeframe")
    return [
        {"source_timeframe": r["source_timeframe"], **r["metrics"]}
        for r in rows
    ]


def get_structure_layer_breakdown(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> list[dict[str, Any]]:
    rows = _aggregate_from_facts(conn, filters, group_by="structure_layer")
    return [
        {"structure_layer": r["structure_layer"], **r["metrics"]}
        for r in rows
    ]


def get_range_scale_breakdown(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> list[dict[str, Any]]:
    rows = _aggregate_from_facts(conn, filters, group_by="range_scale")
    return [
        {"range_scale": r["range_scale"], **r["metrics"]}
        for r in rows
    ]


def get_error_category_analysis(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    """Aggregate error categories with version/timeframe/kind breakdowns."""
    filters = filters or PerformanceFilters()
    where_extra, params = _filter_clause(filters)

    totals = conn.execute(
        f"""
        SELECT error_category, COUNT(*) AS n
        FROM v_detector_correction_facts f
        WHERE 1=1
        {where_extra}
        GROUP BY error_category
        ORDER BY n DESC, error_category
        """,
        params,
    ).fetchall()

    by_version = conn.execute(
        f"""
        SELECT error_category, detector_version, COUNT(*) AS n
        FROM v_detector_correction_facts f
        WHERE 1=1
        {where_extra}
        GROUP BY error_category, detector_version
        ORDER BY error_category, n DESC
        """,
        params,
    ).fetchall()

    by_timeframe = conn.execute(
        f"""
        SELECT error_category, source_timeframe, COUNT(*) AS n
        FROM v_detector_correction_facts f
        WHERE 1=1
        {where_extra}
        GROUP BY error_category, source_timeframe
        ORDER BY error_category, n DESC
        """,
        params,
    ).fetchall()

    by_kind = conn.execute(
        f"""
        SELECT error_category, candidate_kind, COUNT(*) AS n
        FROM v_detector_correction_facts f
        WHERE 1=1
        {where_extra}
        GROUP BY error_category, candidate_kind
        ORDER BY error_category, n DESC
        """,
        params,
    ).fetchall()

    def nest(rows: list[sqlite3.Row], key_field: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            data = _row_dict(row)
            cat = str(data["error_category"])
            out.setdefault(cat, []).append({
                key_field: data[key_field],
                "count": int(data["n"]),
            })
        return out

    return {
        "totals": [
            {"error_category": r["error_category"], "count": int(r["n"])}
            for r in totals
        ],
        "by_detector_version": nest(by_version, "detector_version"),
        "by_source_timeframe": nest(by_timeframe, "source_timeframe"),
        "by_candidate_kind": nest(by_kind, "candidate_kind"),
    }


def format_pct(rate: float | None) -> str:
    if rate is None:
        return "n/a"
    return f"{rate * 100:.0f}%"


def get_detector_scorecard(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    """Scorecard grouped by candidate_kind (primary weak-component view)."""
    kinds = get_candidate_kind_breakdown(conn, filters)
    lines: list[str] = []
    for row in kinds:
        if not row.get("candidate_kind"):
            continue
        lines.append(str(row["candidate_kind"]))
        lines.append(f"Approval: {format_pct(row.get('approval_rate'))}")
        lines.append(f"Edit: {format_pct(row.get('edit_rate'))}")
        lines.append(f"Reject: {format_pct(row.get('rejection_rate'))}")
        lines.append("")
    return {
        "by_candidate_kind": kinds,
        "text": "\n".join(lines).strip(),
    }


def _readiness_for_kinds(
    conn: sqlite3.Connection,
    component: str,
    kinds: frozenset[str],
    threshold: float,
    filters: PerformanceFilters,
) -> dict[str, Any]:
    approved = 0
    edited = 0
    rejected = 0
    for kind in kinds:
        scoped = PerformanceFilters(**{**asdict(filters), "candidate_kind": kind})
        m = _single_metrics(conn, scoped)
        approved += m.approved
        edited += m.edited
        rejected += m.rejected
    metrics = _counts_to_rates(approved, edited, rejected)
    sample = metrics.total_reviewed
    rate = metrics.approval_rate
    trustworthy = sample >= MIN_REVIEWS_FOR_READINESS and rate is not None and rate >= threshold
    return {
        "component": component,
        "candidate_kinds": sorted(kinds),
        "threshold_approval_rate": threshold,
        "min_reviews_required": MIN_REVIEWS_FOR_READINESS,
        "total_reviewed": sample,
        "approval_rate": rate,
        "edit_rate": metrics.edit_rate,
        "rejection_rate": metrics.rejection_rate,
        "trustworthy": trustworthy,
        "status": (
            "TRUSTWORTHY" if trustworthy
            else "INSUFFICIENT_DATA" if sample < MIN_REVIEWS_FOR_READINESS
            else "NEEDS_IMPROVEMENT"
        ),
    }


def get_guided_workflow_readiness(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    """Guided Workflow Engine readiness gate (Phase 4 foundation — no automation)."""
    filters = filters or PerformanceFilters()
    components = [
        _readiness_for_kinds(conn, name, kinds, threshold, filters)
        for name, threshold in GUIDED_WORKFLOW_TRUST_THRESHOLDS.items()
        for kinds in [READINESS_COMPONENT_KINDS[name]]
    ]
    all_trustworthy = all(c["trustworthy"] for c in components)
    return {
        "workflow_engine": "GUIDED_WORKFLOW_ENGINE",
        "principle": "Detector -> Suggest | Human -> Confirm | Database -> Save Truth",
        "autopilot_allowed": False,
        "all_components_trustworthy": all_trustworthy,
        "ready_for_phase_4_guided_acceleration": all_trustworthy,
        "components": components,
    }


def get_detector_health_summary(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> dict[str, Any]:
    """High-level health: summary + weakest kinds + top errors + readiness."""
    filters = filters or PerformanceFilters()
    summary = get_detector_summary(conn, filters)
    kinds = get_candidate_kind_breakdown(conn, filters)
    versions = get_detector_version_breakdown(conn, filters)
    errors = get_error_category_analysis(conn, filters)
    readiness = get_guided_workflow_readiness(conn, filters)

    ranked_kinds = sorted(
        [k for k in kinds if k.get("total_reviewed", 0) > 0],
        key=lambda x: (x.get("approval_rate") is not None, x.get("approval_rate") or 0),
    )
    weakest = ranked_kinds[:3] if ranked_kinds else []
    strongest = list(reversed(ranked_kinds[-3:])) if ranked_kinds else []

    non_no_error = [
        e for e in errors.get("totals", [])
        if e.get("error_category") != "NO_ERROR"
    ]

    return {
        "summary": summary,
        "weakest_candidate_kinds": weakest,
        "strongest_candidate_kinds": strongest,
        "detector_versions": versions,
        "top_error_categories": non_no_error[:5],
        "guided_workflow_readiness": readiness,
    }


def render_cli_report(
    conn: sqlite3.Connection,
    filters: PerformanceFilters | None = None,
) -> str:
    """Human-readable CLI report."""
    filters = filters or PerformanceFilters()
    summary = get_detector_summary(conn, filters)
    scorecard = get_detector_scorecard(conn, filters)
    health = get_detector_health_summary(conn, filters)
    errors = get_error_category_analysis(conn, filters)

    lines = [
        "FX TrendMaster - Detector Performance Report (Phase 3.5)",
        "=" * 56,
        "",
        "SUMMARY",
        f"  Total suggestions: {summary['total_suggestions']}",
        f"  Pending:           {summary['pending_suggestions']}",
        f"  Reviewed:          {summary['total_reviewed']}",
        f"  Approval rate:     {format_pct(summary.get('approval_rate'))}",
        f"  Edit rate:         {format_pct(summary.get('edit_rate'))}",
        f"  Rejection rate:    {format_pct(summary.get('rejection_rate'))}",
        "",
        "SCORECARD (by candidate_kind)",
        "-" * 56,
        scorecard.get("text") or "(no reviewed suggestions)",
        "",
        "DETECTOR VERSIONS",
        "-" * 56,
    ]
    for row in health.get("detector_versions", []):
        lines.append(
            f"  {row.get('detector_version', '?'):<14} "
            f"approve {format_pct(row.get('approval_rate'))}  "
            f"edit {format_pct(row.get('edit_rate'))}  "
            f"reject {format_pct(row.get('rejection_rate'))}  "
            f"(n={row.get('total_reviewed', 0)})"
        )

    lines.extend(["", "ERROR CATEGORIES", "-" * 56])
    for row in errors.get("totals", []):
        lines.append(f"  {row['error_category']:<22} {row['count']}")

    lines.extend(["", "GUIDED WORKFLOW READINESS (Phase 4 gate)", "-" * 56])
    readiness = health.get("guided_workflow_readiness", {})
    lines.append(f"  Engine: {readiness.get('workflow_engine')}")
    lines.append(f"  Phase 4 acceleration allowed: {readiness.get('ready_for_phase_4_guided_acceleration')}")
    for comp in readiness.get("components", []):
        lines.append(
            f"  {comp['component']:<12} "
            f"approve {format_pct(comp.get('approval_rate'))} "
            f"(n={comp.get('total_reviewed', 0)}) "
            f"-> {comp.get('status')}"
        )

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FX TrendMaster detector performance metrics (Phase 3.5 — measurement only)",
    )
    parser.add_argument("--db", default=None, help="SQLite database path (default: candle_store.DB_PATH)")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--structure-layer", default=None)
    parser.add_argument("--source-timeframe", default=None)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text report")
    args = parser.parse_args(argv)

    if args.db:
        import candle_store

        candle_store.DB_PATH = args.db  # type: ignore[assignment]

    import candle_store

    candle_store.init_db()
    with sqlite3.connect(candle_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        init_detection_brain_schema(conn)
        filters = PerformanceFilters(
            symbol=args.symbol,
            structure_layer=args.structure_layer,
            source_timeframe=args.source_timeframe,
        )
        if args.json:
            payload = {
                "summary": get_detector_summary(conn, filters),
                "scorecard": get_detector_scorecard(conn, filters),
                "health": get_detector_health_summary(conn, filters),
                "errors": get_error_category_analysis(conn, filters),
            }
            print(json.dumps(payload, indent=2))
        else:
            print(render_cli_report(conn, filters))
    return 0


if __name__ == "__main__":
    sys.exit(main())
