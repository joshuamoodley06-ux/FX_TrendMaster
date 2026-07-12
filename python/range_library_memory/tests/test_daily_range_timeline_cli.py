from __future__ import annotations

import json
from pathlib import Path

from range_library_memory import cli


def test_central_cli_routes_daily_build(monkeypatch, tmp_path: Path, capsys) -> None:
    observed = {}

    def fake_build(db_path, **kwargs):
        observed["db_path"] = str(db_path)
        observed.update(kwargs)
        return {"rows_built": 1}

    monkeypatch.setattr(cli, "build_daily_range_timelines", fake_build)
    result = cli.main(
        [
            "build-daily-range-timelines",
            "--db-path",
            str(tmp_path / "memory.sqlite3"),
            "--source-db",
            str(tmp_path / "source.sqlite3"),
            "--case-ref",
            "case",
            "--symbol",
            "xauusd",
            "--daily-source-id",
            "427",
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
    assert observed["daily_source_id"] == "427"
    assert observed["weekly_source_id"] == "419"
    assert observed["as_of"] == "2026-06-30T00:00:00Z"


def test_central_cli_routes_daily_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    observed = {}

    def fake_summary(db_path, **kwargs):
        observed["db_path"] = str(db_path)
        observed.update(kwargs)
        return {"filters": {}, "total": 0, "groups": []}

    monkeypatch.setattr(cli, "summarize_daily_range_timelines", fake_summary)
    result = cli.main(
        [
            "daily-range-timeline-summary",
            "--db-path",
            str(tmp_path / "memory.sqlite3"),
            "--daily-state",
            "RECLAIMED",
            "--parent-link-status",
            "VALID",
            "--weekly-phase",
            "WEEKLY_POST_RECLAIM",
            "--observation-status",
            "OBSERVED",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["total"] == 0
    assert observed["daily_state"] == "RECLAIMED"
    assert observed["parent_link_status"] == "VALID"
    assert observed["weekly_phase"] == "WEEKLY_POST_RECLAIM"
    assert observed["observation_status"] == "OBSERVED"
