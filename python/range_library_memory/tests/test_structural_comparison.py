from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from range_library_memory.structural_comparison import (
    CLOSE_TIER,
    MODEL_FAMILY_TIER,
    STRONG_TIER,
    StructuralComparisonError,
    build_staged_snapshot,
    compare_structural_state,
    load_fixture,
    main,
)

FIXTURE = Path(__file__).parent / "fixtures" / "xauusd_comparison_v01.json"


def state(
    *,
    state_id: str,
    low: float,
    high: float,
    price: float,
    trust_status: str = "TRUSTED",
) -> dict:
    return {
        "schema_version": "xauusd_structural_state_v0.1",
        "state_id": state_id,
        "symbol": "XAUUSD",
        "as_of_time": "2026-01-10T00:00:00Z",
        "trust_status": trust_status,
        "parent_direction": "UP",
        "parent_origin": "DEMAND",
        "parent_range": {"low": low, "high": high},
        "current_price": price,
        "child_relationship": "PROTREND",
        "bos_state": "UP",
        "reclaim_state": "WICK",
        "retest_state": "HELD",
        "ltf_confirmation_state": "CONFIRMED_UP",
        "event_sequence": [
            "BOS_UP",
            "RECLAIM_WICK",
            "RETEST_HELD",
            "LTF_CONFIRMED_UP",
        ],
    }


def example(example_id: str, snapshot: dict, path: str = "CONTINUATION") -> dict:
    return {
        "example_id": example_id,
        "case_ref": f"case-{example_id}",
        "source_refs": [f"daily:{example_id}"],
        "snapshot": snapshot,
        "outcome": {
            "path": path,
            "destination": "PARENT_HIGH" if path == "CONTINUATION" else "PARENT_LOW",
            "reached_at": "2026-01-14T00:00:00Z",
            "time_to_destination": {"bars": 4, "timeframe": "D1"},
        },
    }


def test_absolute_price_differences_do_not_prevent_structural_matching() -> None:
    live = state(state_id="live", low=3000, high=3200, price=3070)
    historical = state(state_id="historical", low=1500, high=1700, price=1570)

    report = compare_structural_state(live, [example("price-normalized", historical)])

    strong = report["tiers"][STRONG_TIER]
    assert strong["sample_size"] == 1
    match = strong["linked_historical_examples"][0]
    assert match["tier"] == STRONG_TIER
    assert match["match_evidence"]["normalized_location_delta"] == 0
    assert report["query"]["normalized_location"] == 0.35
    assert match["historical_state"]["normalized_location"] == 0.35


def test_future_outcome_data_is_not_used_to_decide_match_or_score() -> None:
    live = state(state_id="live", low=3000, high=3200, price=3070)
    frozen = state(state_id="frozen", low=1800, high=2000, price=1870)
    continuation = example("same-state-a", copy.deepcopy(frozen), "CONTINUATION")
    failure = example("same-state-b", copy.deepcopy(frozen), "FAILURE")
    failure["outcome"]["destination"] = "PARENT_LOW"
    failure["outcome"]["time_to_destination"]["bars"] = 1

    report = compare_structural_state(live, [continuation, failure])
    matches = report["tiers"][STRONG_TIER]["linked_historical_examples"]

    assert len(matches) == 2
    assert {match["outcome"]["path"] for match in matches} == {"CONTINUATION", "FAILURE"}
    assert len({match["tier"] for match in matches}) == 1
    assert len({match["score"] for match in matches}) == 1
    assert len(
        {
            json.dumps(match["match_evidence"], sort_keys=True)
            for match in matches
        }
    ) == 1


def test_staged_snapshot_excludes_events_after_freeze() -> None:
    staged = build_staged_snapshot(
        {
            "example_id": "staged",
            "base_state": {
                "schema_version": "xauusd_structural_state_v0.1",
                "symbol": "XAUUSD",
                "trust_status": "TRUSTED",
                "parent_direction": "UP",
                "parent_origin": "DEMAND",
                "parent_range": {"low": 1000, "high": 1200},
                "current_price": 1070,
                "child_relationship": "PROTREND",
            },
            "event_timeline": [
                {"at": "2025-01-01T00:00:00Z", "type": "BOS_UP"},
                {"at": "2025-01-02T00:00:00Z", "type": "RECLAIM_WICK"},
                {"at": "2025-01-05T00:00:00Z", "type": "RETEST_FAILED"},
            ],
            "freeze_at": "2025-01-03T00:00:00Z",
            "outcome": {
                "path": "FAILURE",
                "destination": "PARENT_LOW",
                "reached_at": "2025-01-06T00:00:00Z",
                "time_to_destination": {"bars": 3, "timeframe": "D1"},
            },
        }
    )

    assert staged["event_sequence"] == ["BOS_UP", "RECLAIM_WICK"]
    assert staged["retest_state"] == "NONE"
    assert staged["as_of_time"] == "2025-01-03T00:00:00Z"


def test_fixture_keeps_match_tiers_separate_and_filters_untrusted_records() -> None:
    live, history = load_fixture(FIXTURE)
    report = compare_structural_state(live, history)

    assert report["tiers"][STRONG_TIER]["sample_size"] == 2
    assert report["tiers"][CLOSE_TIER]["sample_size"] == 1
    assert report["tiers"][MODEL_FAMILY_TIER]["sample_size"] == 1
    assert report["overall"]["sample_size"] == 4
    assert report["filtering"] == {
        "historical_records_seen": 6,
        "trusted_records_used": 4,
        "excluded_needs_review": 1,
        "excluded_excluded": 1,
        "excluded_untrusted": 0,
    }


def test_strong_only_request_does_not_silently_widen_to_other_tiers() -> None:
    live, history = load_fixture(FIXTURE)
    report = compare_structural_state(live, history, requested_tiers=[STRONG_TIER])

    assert report["tiers"][STRONG_TIER]["sample_size"] == 2
    assert report["tiers"][CLOSE_TIER]["sample_size"] == 0
    assert report["tiers"][MODEL_FAMILY_TIER]["sample_size"] == 0
    assert report["overall"]["sample_size"] == 2


def test_report_returns_frequencies_destinations_times_and_every_example_link() -> None:
    live, history = load_fixture(FIXTURE)
    report = compare_structural_state(live, history)
    overall = report["overall"]

    assert overall["frequency"]["CONTINUATION"] == {"count": 2, "percent": 50.0}
    assert overall["frequency"]["FAILURE"] == {"count": 1, "percent": 25.0}
    assert overall["frequency"]["ALTERNATIVE"] == {"count": 1, "percent": 25.0}
    assert overall["next_structural_destination"]["PARENT_HIGH"]["count"] == 2
    assert overall["time_to_destination"]["D1"] == {
        "observed_count": 4,
        "mean_bars": 3.5,
        "median_bars": 3.5,
        "min_bars": 2,
        "max_bars": 5,
    }
    links = [
        match["historical_example"]["link"]
        for match in overall["linked_historical_examples"]
    ]
    assert len(links) == 4
    assert len(set(links)) == 4


def test_non_trusted_live_state_is_rejected() -> None:
    live = state(state_id="live", low=3000, high=3200, price=3070, trust_status="NEEDS_REVIEW")
    historical = state(state_id="historical", low=1500, high=1700, price=1570)

    with pytest.raises(StructuralComparisonError, match="live_state must be explicitly TRUSTED"):
        compare_structural_state(live, [example("historical", historical)])


def test_fixture_cli_runs_and_emits_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--fixture", str(FIXTURE), "--tiers", STRONG_TIER, "--compact"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "xauusd_comparison_report_v0.1"
    assert report["overall"]["sample_size"] == 2
