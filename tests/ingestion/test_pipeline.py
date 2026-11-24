"""Tests for run_ingestion, with the db layer and source both mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tendersathi.ingestion.pipeline import run_ingestion
from tendersathi.ingestion.sources import RawTenderUpload


def _upload(fingerprint: str) -> RawTenderUpload:
    return RawTenderUpload(
        source="manual_upload",
        file_path=Path("tender.pdf"),
        external_reference=None,
        title_hint="A tender",
        source_url=None,
        pages=[],
        fingerprint=fingerprint,
    )


@patch("tendersathi.ingestion.pipeline.tenders_db")
@patch("tendersathi.ingestion.pipeline.runs_db")
def test_run_ingestion_skips_duplicates_and_saves_new_tenders(mock_runs_db, mock_tenders_db):
    mock_runs_db.start_run.return_value = "run-1"
    mock_tenders_db.get_tender_by_fingerprint.side_effect = [None, MagicMock()]
    source = MagicMock()
    source.fetch_new.return_value = [_upload("fp-new"), _upload("fp-existing")]

    stats = run_ingestion(client=MagicMock(), source=source)

    assert stats.found == 2
    assert stats.new == 1
    assert stats.duplicates == 1
    mock_tenders_db.save_raw_tender.assert_called_once()
    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "success"


@patch("tendersathi.ingestion.pipeline.tenders_db")
@patch("tendersathi.ingestion.pipeline.runs_db")
def test_run_ingestion_marks_run_failed_and_reraises_on_error(mock_runs_db, mock_tenders_db):
    mock_runs_db.start_run.return_value = "run-1"
    source = MagicMock()
    source.fetch_new.side_effect = RuntimeError("source blew up")

    with pytest.raises(RuntimeError, match="source blew up"):
        run_ingestion(client=MagicMock(), source=source)

    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "failed"
