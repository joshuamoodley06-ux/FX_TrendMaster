"""Read-only XAUUSD structural comparison engine v0.1.

Matching uses only state frozen at each historical ``as_of_time``. Outcomes are
stored and summarized separately, so later price action cannot qualify a match.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

REPORT_SCHEMA_VERSION = "xauusd_comparison_report_v0.1"
STATE_SCHEMA_VERSION = "xauusd_structural_state_v0.1"
FIXTURE_SCHEMA_VERSION = "xauusd_comparison_fixture_v0.1"
STRONG_TIER = "strong_structural_match"
CLOSE_TIER = "close_match"
MODEL_FAMILY_TIER = "broader_model_family_match"
MATCH_TIERS = (STRONG_TIER, CLOSE_TIER, MODEL_FAMILY_TIER)
TRUSTED = "TRUSTED"
VALID_OUTCOME_PATHS = {"CONTINUATION", "FAILURE", "ALTERNATIVE"}

ALLOWED = {
    "parent_direction": {"UP", "DOWN", "TRANSITION"},
    "child_relationship": {"PROTREND", "COUNTERTREND", "TRANSITION"},
    "bos_state": {"NONE", "UP", "DOWN"},
    "reclaim_state": {"NONE", "PENDING", "WICK", "CLOSE", "WICK_AND_CLOSE"},
    "retest_state": {"NONE", "PENDING", "TOUCHED", "HELD", "FAILED"},
    "ltf_confirmation_state": {"NONE", "PENDING", "CONFIRMED_UP", "CONFIRMED_DOWN", "FAILED"},
}
STATE_FIELDS = ("bos_state", "reclaim_state", "retest_state", "ltf_confirmation_state")
WEIGHTS = {
    "parent_direction": .16, "parent_origin": .10, "location": .16,
    "child_relationship": .16, "bos_state": .10, "reclaim_state": .10,
    "retest_state": .07, "ltf_confirmation_state": .07, "event_order": .08,
}
EVENT_UPDATES = {
    "BOS_UP": ("bos_state", "UP"), "BOS_DOWN": ("bos_state", "DOWN"),
    "RECLAIM_PENDING": ("reclaim_state", "PENDING"),
    "RECLAIM_WICK": ("reclaim_state", "WICK"),
    "RECLAIM_CLOSE": ("reclaim_state", "CLOSE"),
    "RECLAIM_WICK_AND_CLOSE": ("reclaim_state", "WICK_AND_CLOSE"),
    "RETEST_PENDING": ("retest_state", "PENDING"),
    "RETEST_TOUCHED": ("retest_state", "TOUCHED"),
    "RETEST_HELD": ("retest_state", "HELD"),
    "RETEST_FAILED": ("retest_state", "FAILED"),
    "LTF_PENDING": ("ltf_confirmation_state", "PENDING"),
    "LTF_CONFIRMED_UP": ("ltf_confirmation_state", "CONFIRMED_UP"),
    "LTF_CONFIRMED_DOWN": ("ltf_confirmation_state", "CONFIRMED_DOWN"),
    "LTF_FAILED": ("ltf_confirmation_state", "FAILED"),
}


class StructuralComparisonError(ValueError):
    """Unsafe or invalid comparison contract."""


def compare_structural_state(
    live_state: Mapping[str, Any],
    historical_examples: Iterable[Mapping[str, Any]],
    *,
    requested_tiers: Sequence[str] = MATCH_TIERS,
) -> dict[str, Any]:
    requested = normalize_tiers(requested_tiers)
    live = normalize_snapshot(live_state, "live")
    if trust_reason(live):
        raise StructuralComparisonError(
            "live_state must be explicitly TRUSTED and free of review/exclusion statuses"
        )
    buckets = {tier: [] for tier in MATCH_TIERS}
    excluded: Counter[str] = Counter()
    seen = trusted = 0
    for raw in historical_examples:
        seen += 1
        item = normalize_historical_example(raw)
        reason = trust_reason(item["snapshot"])
        if reason:
            excluded[reason] += 1
            continue
        trusted += 1
        assessment = assess_match(live, item["snapshot"])
        if assessment and assessment["tier"] in requested:
            buckets[assessment["tier"]].append(match_record(item, assessment))
    for rows in buckets.values():
        rows.sort(key=lambda x: (-x["score"], x["historical_example"]["example_id"]))
    all_matches = [row for tier in MATCH_TIERS for row in buckets[tier]]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "query": {
            key: copy.deepcopy(live[key]) for key in (
                "state_id", "symbol", "as_of_time", "parent_direction", "parent_origin",
                "normalized_location", "location_zone", "child_relationship", "model_family",
                "event_sequence",
            )
        } | {"requested_tiers": list(requested)},
        "filtering": {
            "historical_records_seen": seen, "trusted_records_used": trusted,
            "excluded_needs_review": excluded["NEEDS_REVIEW"],
            "excluded_excluded": excluded["EXCLUDED"],
            "excluded_untrusted": excluded["UNTRUSTED"],
        },
        "tiers": {tier: summarize(rows) for tier, rows in buckets.items()},
        "overall": summarize(all_matches),
    }


def build_staged_snapshot(case: Mapping[str, Any]) -> dict[str, Any]:
    required = {"example_id", "base_state", "event_timeline", "freeze_at", "outcome"}
    missing = sorted(required - case.keys())
    if missing:
        raise StructuralComparisonError(f"historical staged case missing: {', '.join(missing)}")
    freeze = canonical_time(case["freeze_at"])
    state = copy.deepcopy(dict(case["base_state"]))
    state.setdefault("state_id", f"{case['example_id']}@{freeze}")
    state["as_of_time"] = freeze
    for field in STATE_FIELDS:
        state.setdefault(field, "NONE")
    events: list[tuple[datetime, int, str]] = []
    for index, raw in enumerate(case["event_timeline"]):
        event = token(raw.get("type"))
        if event not in EVENT_UPDATES:
            raise StructuralComparisonError(f"unsupported staged event type: {event or '<blank>'}")
        at = parse_time(raw.get("at"))
        if at <= parse_time(freeze):
            events.append((at, index, event))
    events.sort(key=lambda x: (x[0], x[1]))
    state["event_sequence"] = []
    for _, _, event in events:
        state["event_sequence"].append(event)
        field, value = EVENT_UPDATES[event]
        state[field] = value
    outcome = normalize_outcome(case["outcome"])
    if outcome["reached_at"] and parse_time(outcome["reached_at"]) < parse_time(freeze):
        raise StructuralComparisonError("historical outcome occurs before the frozen snapshot")
    return normalize_snapshot(state, "historical")


def load_fixture(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise StructuralComparisonError(f"fixture schema must be {FIXTURE_SCHEMA_VERSION}")
    live = normalize_snapshot(data["live_state"], "live")
    history = [normalize_historical_example(item) for item in data.get("historical_cases", [])]
    return live, history


def normalize_historical_example(raw: Mapping[str, Any]) -> dict[str, Any]:
    example_id = str(raw.get("example_id") or "").strip()
    if not example_id:
        raise StructuralComparisonError("historical example_id is required")
    snapshot = normalize_snapshot(raw["snapshot"], "historical") if "snapshot" in raw else build_staged_snapshot(raw)
    outcome = normalize_outcome(raw["outcome"])
    if outcome["reached_at"] and parse_time(outcome["reached_at"]) < parse_time(snapshot["as_of_time"]):
        raise StructuralComparisonError(f"outcome for {example_id} occurs before snapshot freeze")
    ref = dict(raw.get("example_ref") or {})
    ref.setdefault("example_id", example_id)
    ref.setdefault("case_ref", raw.get("case_ref"))
    ref.setdefault("source_refs", list(raw.get("source_refs") or []))
    ref.setdefault("snapshot_as_of", snapshot["as_of_time"])
    ref.setdefault("link", f"fixture://xauusd-comparison-v01/{example_id}")
    return {"example_id": example_id, "snapshot": snapshot, "outcome": outcome, "example_ref": ref}


def normalize_snapshot(raw: Mapping[str, Any], role: str) -> dict[str, Any]:
    state = dict(raw)
    if state.get("schema_version", STATE_SCHEMA_VERSION) != STATE_SCHEMA_VERSION:
        raise StructuralComparisonError(f"{role} state schema must be {STATE_SCHEMA_VERSION}")
    state_id = str(state.get("state_id") or "").strip()
    if not state_id:
        raise StructuralComparisonError(f"{role} state_id is required")
    if token(state.get("symbol")) != "XAUUSD":
        raise StructuralComparisonError(f"{role} symbol must be XAUUSD")
    parent = dict(state.get("parent_range") or {})
    low, high = number(parent.get("low"), "parent_range.low"), number(parent.get("high"), "parent_range.high")
    if high <= low:
        raise StructuralComparisonError("parent_range.high must be greater than parent_range.low")
    price = number(state.get("current_price"), "current_price")
    location = (price - low) / (high - low)
    normalized = {
        "schema_version": STATE_SCHEMA_VERSION, "state_id": state_id, "symbol": "XAUUSD",
        "as_of_time": canonical_time(state.get("as_of_time")),
        "trust_status": token(state.get("trust_status")),
        "review_status": token(state.get("review_status")),
        "resolution_status": token(state.get("resolution_status")),
        "parent_link_status": token(state.get("parent_link_status")),
        "parent_direction": valid(state.get("parent_direction"), ALLOWED["parent_direction"], "parent_direction"),
        "parent_origin": token(state.get("parent_origin")),
        "parent_range": {"low": low, "high": high}, "current_price": price,
        "normalized_location": round(location, 8), "location_zone": zone(location),
        "child_relationship": valid(state.get("child_relationship"), ALLOWED["child_relationship"], "child_relationship"),
        "event_sequence": [token(item) for item in state.get("event_sequence", [])],
    }
    if not normalized["parent_origin"]:
        raise StructuralComparisonError("parent_origin is required")
    for field in STATE_FIELDS:
        normalized[field] = valid(state.get(field, "NONE"), ALLOWED[field], field)
    normalized["model_family"] = family(normalized["child_relationship"])
    return normalized


def assess_match(live: Mapping[str, Any], old: Mapping[str, Any]) -> dict[str, Any] | None:
    delta = abs(live["normalized_location"] - old["normalized_location"])
    event_similarity = order_similarity(live["event_sequence"], old["event_sequence"])
    score, components = score_components(live, old, delta, event_similarity)
    same_core = all(live[key] == old[key] for key in (
        "parent_direction", "parent_origin", "child_relationship", *STATE_FIELDS
    ))
    same_events = live["event_sequence"] == old["event_sequence"]
    terminal_same = terminal(live["event_sequence"]) == terminal(old["event_sequence"])
    mismatches = sum(live[field] != old[field] for field in STATE_FIELDS)
    tier = None
    if same_core and same_events and delta <= .08:
        tier = STRONG_TIER
    elif (
        live["parent_direction"] == old["parent_direction"]
        and live["parent_origin"] == old["parent_origin"]
        and live["child_relationship"] == old["child_relationship"]
        and live["model_family"] == old["model_family"]
        and delta <= .20 and event_similarity >= .75 and terminal_same
        and mismatches <= 2 and score >= .78
    ):
        tier = CLOSE_TIER
    elif (
        live["parent_direction"] == old["parent_direction"]
        and live["model_family"] == old["model_family"]
        and delta <= .40 and event_similarity >= .50 and terminal_same
    ):
        tier = MODEL_FAMILY_TIER
    if not tier:
        return None
    return {"tier": tier, "score": score, "match_evidence": {
        "component_scores": components, "normalized_location_delta": round(delta, 8),
        "event_order_similarity": round(event_similarity, 6),
    }}


def score_components(live: Mapping[str, Any], old: Mapping[str, Any], delta: float, event: float) -> tuple[float, dict[str, float]]:
    c = {key: float(live[key] == old[key]) for key in WEIGHTS if key not in {"location", "event_order"}}
    c["location"] = max(0.0, 1.0 - delta / .50)
    c["event_order"] = event
    return round(sum(c[k] * WEIGHTS[k] for k in WEIGHTS), 6), {k: round(v, 6) for k, v in c.items()}


def order_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    matrix = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i, a in enumerate(left, 1):
        for j, b in enumerate(right, 1):
            matrix[i][j] = matrix[i-1][j-1] + 1 if a == b else max(matrix[i-1][j], matrix[i][j-1])
    return matrix[-1][-1] / max(len(left), len(right))


def match_record(item: Mapping[str, Any], assessment: Mapping[str, Any]) -> dict[str, Any]:
    snap = item["snapshot"]
    return {
        "tier": assessment["tier"], "score": assessment["score"],
        "match_evidence": copy.deepcopy(assessment["match_evidence"]),
        "historical_example": copy.deepcopy(item["example_ref"]),
        "historical_state": {key: copy.deepcopy(snap[key]) for key in (
            "normalized_location", "location_zone", "model_family", "event_sequence"
        )},
        "outcome": copy.deepcopy(item["outcome"]),
    }


def summarize(matches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    paths = Counter(match["outcome"]["path"] for match in matches)
    destinations = Counter(match["outcome"]["destination"] for match in matches)
    times: dict[str, list[int]] = {}
    for match in matches:
        value = match["outcome"].get("time_to_destination")
        if value:
            times.setdefault(value["timeframe"], []).append(value["bars"])
    return {
        "sample_size": len(matches),
        "frequency": frequencies(paths, len(matches), VALID_OUTCOME_PATHS),
        "next_structural_destination": frequencies(destinations, len(matches)),
        "time_to_destination": {tf: numeric(values) for tf, values in sorted(times.items())},
        "linked_historical_examples": copy.deepcopy(list(matches)),
    }


def normalize_outcome(raw: Mapping[str, Any]) -> dict[str, Any]:
    path = valid(raw.get("path"), VALID_OUTCOME_PATHS, "outcome.path")
    destination = token(raw.get("destination"))
    if not destination:
        raise StructuralComparisonError("outcome.destination is required")
    value = raw.get("time_to_destination")
    time_value = None
    if value is not None:
        bars, timeframe = int(value.get("bars")), token(value.get("timeframe"))
        if bars < 0 or not timeframe:
            raise StructuralComparisonError("time_to_destination requires non-negative bars and timeframe")
        time_value = {"bars": bars, "timeframe": timeframe}
    reached = raw.get("reached_at")
    return {"path": path, "destination": destination,
            "reached_at": canonical_time(reached) if reached else None,
            "time_to_destination": time_value}


def trust_reason(state: Mapping[str, Any]) -> str | None:
    statuses = [token(state.get(key)) for key in (
        "trust_status", "review_status", "resolution_status", "parent_link_status"
    )]
    if "NEEDS_REVIEW" in statuses:
        return "NEEDS_REVIEW"
    if "EXCLUDED" in statuses:
        return "EXCLUDED"
    return None if statuses[0] == TRUSTED else "UNTRUSTED"


def normalize_tiers(values: Sequence[str]) -> tuple[str, ...]:
    tiers = tuple(dict.fromkeys(str(v).strip().lower().replace("-", "_").replace(" ", "_") for v in values))
    invalid = [tier for tier in tiers if tier not in MATCH_TIERS]
    if invalid or not tiers:
        raise StructuralComparisonError(f"unsupported match tiers: {', '.join(invalid) or '<empty>'}")
    return tiers


def zone(value: float) -> str:
    if value < 0: return "BELOW_PARENT"
    if value <= .25: return "LOWER_EXTREME"
    if value < .45: return "LOWER"
    if value <= .55: return "EQUILIBRIUM"
    if value < .75: return "UPPER"
    if value <= 1: return "UPPER_EXTREME"
    return "ABOVE_PARENT"


def family(relationship: str) -> str:
    return {"PROTREND": "PROTREND_CONTINUATION", "COUNTERTREND": "COUNTERTREND_ROTATION", "TRANSITION": "TRANSITION"}[relationship]


def frequencies(counts: Counter[str], size: int, expected: Iterable[str] = ()) -> dict[str, dict[str, float | int]]:
    return {key: {"count": counts[key], "percent": round(counts[key] / size * 100, 2) if size else 0.0}
            for key in sorted(set(counts) | set(expected))}


def numeric(values: Sequence[int]) -> dict[str, float | int]:
    return {"observed_count": len(values), "mean_bars": round(mean(values), 3),
            "median_bars": round(median(values), 3), "min_bars": min(values), "max_bars": max(values)}


def terminal(sequence: Sequence[str]) -> str | None:
    return sequence[-1] if sequence else None


def valid(value: Any, allowed: set[str], field: str) -> str:
    result = token(value)
    if result not in allowed:
        raise StructuralComparisonError(f"{field} must be one of {sorted(allowed)}, got {result!r}")
    return result


def token(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise StructuralComparisonError(f"{field} must be numeric") from exc
    if result != result or result in {float("inf"), float("-inf")}:
        raise StructuralComparisonError(f"{field} must be finite")
    return result


def parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise StructuralComparisonError("timestamp is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise StructuralComparisonError(f"invalid ISO timestamp: {value!r}") from exc
    return (result.replace(tzinfo=UTC) if result.tzinfo is None else result).astimezone(UTC)


def canonical_time(value: Any) -> str:
    return parse_time(value).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only XAUUSD structural comparison fixtures")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--tiers", nargs="+", default=list(MATCH_TIERS), choices=list(MATCH_TIERS))
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    live, history = load_fixture(args.fixture)
    print(json.dumps(compare_structural_state(live, history, requested_tiers=args.tiers),
                     indent=None if args.compact else 2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
