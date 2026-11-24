"""Tests for load_pdf_pages, including the OCR fallback path.

OCR itself is mocked: pytesseract needs the system Tesseract binary, which
isn't guaranteed to be installed wherever these tests run, and the point
here is to test our branching logic, not the OCR engine.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytesseract
import pytest

from tendersathi.ingestion.pdf_loader import OcrUnavailableError, load_pdf_pages


def _write_pdf(path: Path, page_texts: list[str]) -> None:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_load_pdf_pages_extracts_native_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_pdf(
        pdf_path,
        ["First page of a real tender document", "Second page of a real tender document"],
    )

    pages = load_pdf_pages(pdf_path)

    assert [p.page_number for p in pages] == [1, 2]
    assert all(not p.used_ocr for p in pages)
    assert "First page" in pages[0].text
    assert "Second page" in pages[1].text


@patch("tendersathi.ingestion.pdf_loader.pytesseract.image_to_string")
def test_load_pdf_pages_ocrs_pages_with_no_extractable_text(
    mock_image_to_string, tmp_path: Path
) -> None:
    mock_image_to_string.return_value = "ocr'd text from a scanned page"
    pdf_path = tmp_path / "scanned.pdf"
    _write_pdf(pdf_path, [""])  # blank page, no native text

    pages = load_pdf_pages(pdf_path)

    assert len(pages) == 1
    assert pages[0].used_ocr is True
    assert pages[0].text == "ocr'd text from a scanned page"
    mock_image_to_string.assert_called_once()


@patch("tendersathi.ingestion.pdf_loader.pytesseract.image_to_string")
def test_load_pdf_pages_raises_clear_error_when_tesseract_missing(
    mock_image_to_string, tmp_path: Path
) -> None:
    mock_image_to_string.side_effect = pytesseract.TesseractNotFoundError()
    pdf_path = tmp_path / "scanned.pdf"
    _write_pdf(pdf_path, [""])

    with pytest.raises(OcrUnavailableError, match="Tesseract"):
        load_pdf_pages(pdf_path)


def test_load_pdf_pages_on_real_sample_tender_is_sequential(tmp_path: Path) -> None:
    sample = Path("data/samples/supply delivery.pdf")
    if not sample.exists():
        pytest.skip("sample tender PDF not present")

    with patch(
        "tendersathi.ingestion.pdf_loader.pytesseract.image_to_string",
        return_value="",
    ):
        pages = load_pdf_pages(sample)

    with pymupdf.open(sample) as document:
        expected_count = document.page_count

    assert len(pages) == expected_count
    assert [p.page_number for p in pages] == list(range(1, expected_count + 1))
