"""mediator_query_v1 validation and normalization."""

from __future__ import annotations

from typing import Any

MEDIATOR_QUERY_SCHEMA = "mediator_query_v1"
MEDIATOR_RESULT_SCHEMA = "mediator_result_v1"

QUESTION_TYPES = frozenset(
    {
        "continuation_rate",
        "reclaim_compare",
        "zone_continuation",
        "continuation_reclaim_zone",
        "rotation",
        "sequence",
        "year_comparison",
        "range_list",
        "impulse_pair_audit",
    }
)

SUPPORTED_METRICS = frozenset(
    {
        "sample_size",
        "continued_count",
        "failed_count",
        "abandoned_count",
        "unresolved_count",
        "continuation_rate",
        "failure_rate",
        "abandon_rate",
        "average_retracement",
        "median_retracement",
        "average_rotations",
        "median_rotations",
        "reclaim_rate",
    }
)

SUPPORTED_GROUP_BY = frozenset(
    {
        "year",
        "year_label",
        "reclaim_class",
        "impulse_index",
        "retracement_class",
        "bos_direction",
        "break_zone",
        "start_zone",
    }
)

LAYER_VALUES = frozenset({"MACRO", "WEEKLY", "DAILY", "INTRADAY", "MICRO"})
ZONE_VALUES = frozenset({"DISCOUNT", "FAIR", "PREMIUM", "BELOW_RANGE", "ABOVE_RANGE"})
RECLAIM_CLASSES = frozenset({"SHALLOW", "MID", "DEEP"})
RETRACEMENT_CLASSES = frozenset({"SHALLOW", "MID", "DEEP", "EXTREME"})
OUTCOME_VALUES = frozenset(
    {"CONTINUED", "FAILED", "ABANDONED", "UNRESOLVED", "OPPOSITE_BOS", "PARENT_BOS"}
)
BOS_DIRECTIONS = frozenset({"UP", "DOWN"})


class QueryValidationError(ValueError):
    pass


def validate_query(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise QueryValidationError("query must be a JSON object")
    schema = raw.get("schema_version")
    if schema != MEDIATOR_QUERY_SCHEMA:
        raise QueryValidationError(f"schema_version must be {MEDIATOR_QUERY_SCHEMA}")

    symbol = _req_str(raw, "symbol").upper()
    if not symbol:
        raise QueryValidationError("symbol is required")

    years = _opt_int_list(raw.get("years"))
    year_labels = _opt_str_list(raw.get("year_labels"))
    case_refs = _opt_str_list(raw.get("case_refs"))

    question_type = raw.get("question_type")
    if question_type is not None:
        question_type = str(question_type).strip()
        if question_type not in QUESTION_TYPES:
            raise QueryValidationError(f"unsupported question_type: {question_type}")
    else:
        question_type = infer_question_type(raw)

    metrics = _opt_str_list(raw.get("metrics")) or ["sample_size"]
    unknown_metrics = [m for m in metrics if m not in SUPPORTED_METRICS]
    if unknown_metrics:
        raise QueryValidationError(f"unsupported metrics: {unknown_metrics}")

    group_by = _opt_str_list(raw.get("group_by")) or []
    unknown_group = [g for g in group_by if g not in SUPPORTED_GROUP_BY]
    if unknown_group:
        raise QueryValidationError(f"unsupported group_by: {unknown_group}")
    if "quarter" in group_by:
        raise QueryValidationError("group_by quarter is deferred to M2")

    query_id = raw.get("query_id")
    if query_id is not None:
        query_id = str(query_id).strip()
        if not query_id:
            query_id = None

    return {
        "schema_version": MEDIATOR_QUERY_SCHEMA,
        "query_id": query_id,
        "symbol": symbol,
        "years": years,
        "year_labels": year_labels,
        "case_refs": case_refs,
        "parent_layer": _opt_upper(raw.get("parent_layer"), LAYER_VALUES),
        "child_layer": _opt_upper(raw.get("child_layer"), LAYER_VALUES),
        "structure_layer": _opt_upper(raw.get("structure_layer"), LAYER_VALUES),
        "bos_direction": _opt_upper(raw.get("bos_direction"), BOS_DIRECTIONS),
        "parent_zone": _opt_upper(raw.get("parent_zone"), ZONE_VALUES),
        "child_zone": _opt_upper(raw.get("child_zone"), ZONE_VALUES),
        "break_zone": _opt_upper(raw.get("break_zone"), ZONE_VALUES),
        "reclaim_class": _opt_upper(raw.get("reclaim_class"), RECLAIM_CLASSES),
        "retracement_class": _opt_upper(raw.get("retracement_class"), RETRACEMENT_CLASSES),
        "outcome": _opt_upper(raw.get("outcome"), OUTCOME_VALUES),
        "impulse_index": _opt_int(raw.get("impulse_index")),
        "question_type": question_type,
        "group_by": group_by,
        "metrics": metrics,
        "row_limit": max(1, min(int(raw.get("row_limit") or 50), 500)),
        "random_sample": bool(raw.get("random_sample", False)),
        "include_source_rows": bool(raw.get("include_source_rows", False)),
        "source_row_limit": max(1, min(int(raw.get("source_row_limit") or 50), 500)),
        "random_seed": _opt_int(raw.get("random_seed")),
    }


def infer_question_type(raw: dict[str, Any]) -> str:
    if raw.get("impulse_index") is not None or raw.get("question_type") == "sequence":
        return "sequence"
    if raw.get("parent_zone") or raw.get("child_zone") or raw.get("break_zone"):
        if raw.get("reclaim_class"):
            return "continuation_reclaim_zone"
        return "zone_continuation"
    if raw.get("reclaim_class"):
        return "reclaim_compare"
    if raw.get("retracement_class") or raw.get("child_layer"):
        return "continuation_rate"
    return "continuation_rate"


def _req_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None:
        raise QueryValidationError(f"{key} is required")
    return str(value).strip()


def _opt_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise QueryValidationError("expected list")
    return [str(v).strip() for v in value if str(v).strip()]


def _opt_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise QueryValidationError("years must be a list")
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            raise QueryValidationError(f"invalid year entry: {item}") from None
    return out


def _opt_upper(value: Any, allowed: frozenset[str] | None = None) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().upper()
    if allowed is not None and text not in allowed:
        raise QueryValidationError(f"invalid value: {text}")
    return text


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise QueryValidationError(f"invalid integer: {value}") from None
