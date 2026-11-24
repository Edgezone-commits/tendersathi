"""Tests for the runs db module, with Supabase mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

from tendersathi.db import runs as runs_db


def test_start_run_inserts_running_row_and_returns_id(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "run-1"}])

    run_id = runs_db.start_run(mock_client, "ingestion")

    assert run_id == "run-1"
    mock_table.insert.assert_called_once_with({"run_type": "ingestion", "status": "running"})


def test_finish_run_updates_status_stats_and_error(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "run-1"}])

    runs_db.finish_run(mock_client, "run-1", status="success", stats={"new": 3})

    payload = mock_table.update.call_args.args[0]
    assert payload["status"] == "success"
    assert payload["stats"] == {"new": 3}
    assert payload["error"] is None
    assert "finished_at" in payload
    mock_table.eq.assert_called_once_with("id", "run-1")


def test_get_run_returns_none_when_missing(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[])

    assert runs_db.get_run(mock_client, "missing") is None


def test_get_run_parses_row(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(
        data=[
            {
                "id": "run-1",
                "run_type": "ingestion",
                "status": "success",
                "stats": {"new": 3},
                "error": None,
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:05:00Z",
            }
        ]
    )

    run = runs_db.get_run(mock_client, "run-1")

    assert run is not None
    assert run.status == "success"
    assert run.stats == {"new": 3}
