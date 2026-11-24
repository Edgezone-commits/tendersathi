"""Tests for the tenders/tender_pages db module, with Supabase mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tendersathi.db import tenders as tenders_db
from tendersathi.ingestion.pdf_loader import PdfPage
from tendersathi.ingestion.sources import RawTenderUpload

_ROW = {
    "id": "tender-1",
    "source": "manual_upload",
    "source_url": None,
    "external_reference": None,
    "title": "Office Equipment Tender",
    "procuring_entity": None,
    "category": None,
    "district": None,
    "estimated_cost": None,
    "submission_deadline": None,
    "fingerprint": "abc123",
    "status": "new",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


def test_get_tender_by_fingerprint_returns_none_when_missing(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[])

    result = tenders_db.get_tender_by_fingerprint(mock_client, "missing-fingerprint")

    assert result is None
    mock_table.eq.assert_called_once_with("fingerprint", "missing-fingerprint")


def test_get_tender_by_fingerprint_parses_matching_row(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[_ROW])

    result = tenders_db.get_tender_by_fingerprint(mock_client, "abc123")

    assert result is not None
    assert result.id == "tender-1"
    assert result.title == "Office Equipment Tender"
    assert result.fingerprint == "abc123"


def test_save_raw_tender_upserts_tender_and_its_pages(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "tender-1"}])
    upload = RawTenderUpload(
        source="manual_upload",
        file_path=Path("tender.pdf"),
        external_reference=None,
        title_hint="Office Equipment Tender",
        source_url=None,
        pages=[
            PdfPage(page_number=1, text="page one", used_ocr=False),
            PdfPage(page_number=2, text="page two", used_ocr=False),
        ],
        fingerprint="abc123",
    )

    tender_id = tenders_db.save_raw_tender(mock_client, upload)

    assert tender_id == "tender-1"
    assert mock_client.table.call_args_list[0].args == ("tenders",)
    assert mock_client.table.call_args_list[1].args == ("tender_pages",)
    tenders_upsert_payload = mock_table.upsert.call_args_list[0].args[0]
    assert tenders_upsert_payload["fingerprint"] == "abc123"
    pages_upsert_payload = mock_table.upsert.call_args_list[1].args[0]
    assert len(pages_upsert_payload) == 2
    assert pages_upsert_payload[0]["tender_id"] == "tender-1"


def test_save_raw_tender_skips_page_upsert_when_no_pages(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "tender-1"}])
    upload = RawTenderUpload(
        source="manual_upload",
        file_path=Path("tender.pdf"),
        external_reference=None,
        title_hint="Office Equipment Tender",
        source_url=None,
        pages=[],
        fingerprint="abc123",
    )

    tenders_db.save_raw_tender(mock_client, upload)

    assert mock_table.upsert.call_count == 1


def test_list_tenders_filters_by_status(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[_ROW])

    results = tenders_db.list_tenders(mock_client, status="new")

    assert len(results) == 1
    mock_table.eq.assert_called_once_with("status", "new")
