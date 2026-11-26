"""Tests for the tenders/tender_pages db module, with Supabase mocked."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from tendersathi.agents.scout import Tender
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


def test_get_tender_returns_none_when_missing(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[])

    result = tenders_db.get_tender(mock_client, "missing-id")

    assert result is None
    mock_table.eq.assert_called_once_with("id", "missing-id")


def test_get_tender_parses_matching_row(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[_ROW])

    result = tenders_db.get_tender(mock_client, "tender-1")

    assert result is not None
    assert result.id == "tender-1"
    assert result.eligibility_requirements == []


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


def test_get_tender_parses_eligibility_requirements_when_present(mock_client, mock_table):
    row = {**_ROW, "eligibility_requirements": ["Minimum 3 years experience"]}
    mock_table.execute.return_value = MagicMock(data=[row])

    result = tenders_db.get_tender(mock_client, "tender-1")

    assert result.eligibility_requirements == ["Minimum 3 years experience"]


def test_get_tender_pages_orders_by_page_number(mock_client, mock_table):
    rows = [
        {
            "id": "page-1",
            "tender_id": "tender-1",
            "page_number": 1,
            "text": "p1",
            "used_ocr": False,
        },
        {
            "id": "page-2",
            "tender_id": "tender-1",
            "page_number": 2,
            "text": "p2",
            "used_ocr": True,
        },
    ]
    mock_table.execute.return_value = MagicMock(data=rows)

    pages = tenders_db.get_tender_pages(mock_client, "tender-1")

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[1].used_ocr is True
    mock_table.eq.assert_called_once_with("tender_id", "tender-1")
    mock_table.order.assert_called_once_with("page_number")


def test_update_tender_extraction_writes_scout_fields(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "tender-1"}])
    tender = Tender(
        title="Procurement of Widgets",
        procuring_entity="Ministry of Widgets",
        category="Goods",
        district="Kathmandu",
        estimated_cost_npr=4_200_000.0,
        deadline=date(2026, 12, 11),
        eligibility_requirements=["Minimum 3 years experience"],
        source_pages=[1, 2],
    )

    tenders_db.update_tender_extraction(mock_client, "tender-1", tender)

    payload = mock_table.update.call_args.args[0]
    assert payload["title"] == "Procurement of Widgets"
    assert payload["category"] == "Goods"
    assert payload["submission_deadline"] == "2026-12-11"
    assert payload["eligibility_requirements"] == ["Minimum 3 years experience"]
    mock_table.eq.assert_called_once_with("id", "tender-1")


def test_update_tender_extraction_does_not_overwrite_title_when_scout_found_none(
    mock_client, mock_table
):
    mock_table.execute.return_value = MagicMock(data=[{"id": "tender-1"}])
    tender = Tender()

    tenders_db.update_tender_extraction(mock_client, "tender-1", tender)

    payload = mock_table.update.call_args.args[0]
    assert "title" not in payload
    assert payload["submission_deadline"] is None
