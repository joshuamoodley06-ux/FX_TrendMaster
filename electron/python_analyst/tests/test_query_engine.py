"""Phase M1 tests: mediator query engine (no AI)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyst.pipeline import run_year
from analyst.query.metrics import compute_metrics, compute_rates, outcome_counts
from analyst.query.schema import QueryValidationError, validate_query
from analyst.query_engine import run_query, run_query_file
from analyst.storage.combined import rebuild_combined

FIXTURE = Path(__file__).parent / "fixtures" / "XAUUSD_2020_fixture.json"
QUERY_DEEP = Path(__file__).parent / "fixtures" / "query_deep_retracement.json"


def _seed_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    run_year(FIXTURE, workspace / "XAUUSD" / "2020")
    return workspace


def test_validate_rejects_quarter_group_by():
    with pytest.raises(QueryValidationError, match="quarter"):
        validate_query(
            {
                "schema_version": "mediator_query_v1",
                "symbol": "XAUUSD",
                "group_by": ["quarter"],
                "metrics": ["sample_size"],
            }
        )


def test_continuation_rate_excludes_unresolved_from_denominator():
    import pandas as pd

    df = pd.DataFrame(
        {
            "outcome": ["CONTINUED", "FAILED", "UNRESOLVED", "CONTINUED"],
        }
    )
    counts = outcome_counts(df)
    rates = compute_rates(counts)
    assert counts["continued_count"] == 2
    assert counts["unresolved_count"] == 1
    assert rates["continuation_rate"] == pytest.approx(2 / 3)


def test_deep_daily_retracement_query(tmp_path):
    workspace = _seed_workspace(tmp_path)
    result = run_query_file(QUERY_DEEP, workspace_root=workspace)

    assert result["status"] == "OK"
    assert result["sample_size"] == 1
    metrics = result["metrics"]
    assert metrics["continued_count"] == 0
    assert metrics["failed_count"] == 0
    assert metrics["abandoned_count"] == 0
    assert metrics["unresolved_count"] == 1
    assert metrics["continuation_rate"] is None
    assert result["filters_applied"]["child_layer"] == "DAILY"
    assert result["filters_applied"]["retracement_class"] == "DEEP"

    out_dir = Path(result["output_dir"])
    assert (out_dir / "query_result.json").is_file()
    assert (out_dir / "query.json").is_file()
    assert "queries" in str(out_dir)
    assert out_dir.name == "acceptance_deep_daily_retracement"


def test_query_writes_default_output_path(tmp_path):
    workspace = _seed_workspace(tmp_path)
    raw = json.loads(QUERY_DEEP.read_text(encoding="utf-8"))
    raw.pop("query_id")
    result = run_query(raw, workspace_root=workspace)
    out_dir = Path(result["output_dir"])
    assert out_dir.parent.parent == workspace / "XAUUSD"
    assert out_dir.parent.name == "queries"
    assert (out_dir / "query_result.json").is_file()


def test_combined_includes_non_digit_batch_labels(tmp_path):
    workspace = tmp_path / "workspace"
    run_year(FIXTURE, workspace / "XAUUSD" / "2020")

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["label"] = "XAUUSD_2019_Q3-2021_Q1"
    batch_label = "2019_Q3-2021_Q1"
    second = tmp_path / "second.json"
    second.write_text(json.dumps(payload), encoding="utf-8")
    run_year(second, workspace / "XAUUSD" / batch_label)

    combined = rebuild_combined(workspace, "XAUUSD")
    assert combined["years"] == 2
    labels = {row["label"] for row in combined["comparison_rows"]}
    assert "XAUUSD_2020_fixture" in labels
    assert "XAUUSD_2019_Q3-2021_Q1" in labels

    stats = json.loads(
        (workspace / "XAUUSD" / "combined" / "XAUUSD_combined_stats.json").read_text(encoding="utf-8")
    )
    assert batch_label in stats["years_analyzed"]


def test_no_data_query(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = run_query(
        {
            "schema_version": "mediator_query_v1",
            "symbol": "XAUUSD",
            "metrics": ["sample_size"],
        },
        workspace_root=workspace,
    )
    assert result["status"] == "NO_WORKSPACE"
    assert result["sample_size"] == 0


def test_year_comparison_query(tmp_path):
    workspace = _seed_workspace(tmp_path)
    result = run_query(
        {
            "schema_version": "mediator_query_v1",
            "symbol": "XAUUSD",
            "question_type": "year_comparison",
            "metrics": ["sample_size"],
        },
        workspace_root=workspace,
    )
    assert result["status"] == "OK"
    assert result["metrics"]["sample_size"] == 1
    assert len(result["metrics"]["year_rows"]) == 1
