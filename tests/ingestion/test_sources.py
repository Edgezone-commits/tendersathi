"""Tests for ManualUploadSource and the BolpatraScraper stub."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytesseract
import pytest

from tendersathi.ingestion.sources import BolpatraScraper, ManualUploadSource


def _write_pdf(path: Path, text: str) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_load_file_fingerprints_from_file_bytes(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tender.pdf"
    _write_pdf(pdf_path, "Procurement of office equipment")

    upload = ManualUploadSource(tmp_path).load_file(pdf_path)

    assert upload.source == "manual_upload"
    assert upload.title_hint == "tender"
    assert len(upload.pages) == 1
    assert upload.fingerprint  # non-empty


def test_load_file_uses_title_hint_and_metadata_when_given(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tender.pdf"
    _write_pdf(pdf_path, "Procurement of office equipment")

    upload = ManualUploadSource(tmp_path).load_file(
        pdf_path,
        title_hint="Office Equipment Tender",
        source_url="https://example.com/notice/1",
        external_reference="REF-42",
    )

    assert upload.title_hint == "Office Equipment Tender"
    assert upload.source_url == "https://example.com/notice/1"
    assert upload.external_reference == "REF-42"


def test_fetch_new_loads_every_pdf_in_inbox(tmp_path: Path) -> None:
    _write_pdf(tmp_path / "a.pdf", "Procurement notice for Tender A")
    _write_pdf(tmp_path / "b.pdf", "Procurement notice for Tender B")
    (tmp_path / "not-a-pdf.txt").write_text("ignore me")

    uploads = ManualUploadSource(tmp_path).fetch_new()

    assert {u.file_path.name for u in uploads} == {"a.pdf", "b.pdf"}


def test_reuploading_the_same_file_gives_the_same_fingerprint(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tender.pdf"
    _write_pdf(pdf_path, "Procurement of office equipment")
    source = ManualUploadSource(tmp_path)

    first = source.load_file(pdf_path)
    second = source.load_file(pdf_path)

    assert first.fingerprint == second.fingerprint


@patch("tendersathi.ingestion.pdf_loader.pytesseract.image_to_string")
def test_fetch_new_skips_files_that_fail_to_load(mock_image_to_string, tmp_path: Path) -> None:
    mock_image_to_string.side_effect = pytesseract.TesseractNotFoundError()
    _write_pdf(tmp_path / "good.pdf", "Procurement notice for a valid tender document")
    _write_pdf(tmp_path / "scanned.pdf", "")  # blank page -> needs OCR -> fails to load

    uploads = ManualUploadSource(tmp_path).fetch_new()

    assert {u.file_path.name for u in uploads} == {"good.pdf"}


def test_bolpatra_scraper_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="ManualUploadSource"):
        BolpatraScraper().fetch_new()
