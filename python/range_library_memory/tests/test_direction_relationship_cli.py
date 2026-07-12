from __future__ import annotations

import json
from pathlib import Path

from range_library_memory import cli


def test_central_cli_routes_weekly_direction_build(monkeypatch, tmp_path: Path, capsys) -> None:
    observed = {}

    def fake_build(db_path, **kwargs):
        observed["db_path"] = str(db_path)
        observed.update(kwargs)
        return {"rows_built": 1}

    monkeypatch.setattr(cli, "build_weekly_direction_contexts", fake_build)
    result = cli.main(
        [
            "build-weekly-direction-contexts",
            "--db-path",
            str(tmp_path / "memory.sqlite3"),
            "--case-ref",
            "case",
            "--symbol",
            "xauusd",
            "--weekly-source-id",
            "419",
            "--as-of",
            "2026-06-30T00:00:00Z",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out) == {"rows_built": 1}
    assert observed["case_ref"] == "case"
    assert observed["symbol"] == "xauusd"
    assert observed["weekly_source_id"] == "419"
    assert observed["as_of"] == "2026-06-30T00:00:00Z"


def test_central_cli_routes_weekly_direction_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    observed = {}

    def fake_summary(db_path, **kwargs):
        observed["db_path"] = str(db_path)
        observed.update(kwargs)
        return {"filters": {}, "total": 0, "groups": []}

    monkeypatch.setattr(cli, "summarize_weekly_direction_contexts", fake_summary)
    result = cli.main(
        [
            "weekly-direction-context-summary",
            "--db-path",
            str(tmp_path / "memory.sqlite3"),
            "--direction-state",
            "CONFIRMED_DOWN",
            "--observation-status",
            "OBSERVED",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["total"] == 0
    assert observed["direction_state"] == "CONFIRMED_DOWN"
    assert observed["observation_status"] == "OBSERVED"


def test_central_cli_routes_daily_trend_build(monkeypatch, tmp_path: Path, capsys) -> None:
    observed = {}

    def fake_build(db_path, **kwargs):
        observed["db_path"] = str(db_path)
        observed.update(kwargs)
        return {"rows_built": 1}

    monkeypatch.setattr(cli, "build_daily_trend_relationships", fake_build)
    result = cli.main(
        [
            "build-daily-trend-relationships",
            "--db-path",
            str(tmp_path / "memory.sqlite3"),
            "--daily-source-id",
            "421",
            "--weekly-source-id",
            "419",
            "--as-of",
            "2026-06-30T00:00:00Z",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out) == {"rows_built": 1}
    assert observed["daily_source_id"] == "421"
    assert observed["weekly_source_id"] == "419"
    assert observed["as_of"] == "2026-06-30T00:00:00Z"


def test_central_cli_routes_daily_trend_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    observed = {}

    def fake_summary(db_path, **kwargs):
        observed["db_path"] = str(db_path)
        observed.update(kwargs)
        return {"filters": {}, "total": 0, "groups": []}

    monkeypatch.setattr(cli, "summarize_daily_trend_relationships", fake_summary)
    result = cli.main(
        [
            "daily-trend-relationship-summary",
            "--db-path",
            str(tmp_path / "memory.sqlite3"),
            "--trend-relationship",
            "PROTREND",
            "--observation-status",
            "OBSERVED",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["total"] == 0
    assert observed["trend_relationship"] == "PROTREND"
    assert observed["observation_status"] == "OBSERVED"
