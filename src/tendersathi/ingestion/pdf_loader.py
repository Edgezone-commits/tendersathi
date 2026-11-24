"""Extract text from tender PDFs, one page at a time.

Page numbers are kept attached to every chunk of text because the
Eligibility agent (Phase 4) must cite the exact page a requirement came
from. Some bid documents are scanned images rather than real text, so
pages with little or no extractable text fall back to OCR instead of
coming back empty.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

MIN_EXTRACTABLE_CHARS = 20
OCR_RENDER_DPI = 300


@dataclass(frozen=True)
class PdfPage:
    """One page of a PDF, already resolved to plain text."""

    page_number: int  # 1-indexed, matching what a human sees in a PDF viewer
    text: str
    used_ocr: bool


class OcrUnavailableError(RuntimeError):
    """Raised when a page has no extractable text and OCR can't run either."""


def load_pdf_pages(path: Path, ocr_language: str = "eng") -> list[PdfPage]:
    """Load every page of `path` as text, OCR-ing any page with little/no text."""
    pages: list[PdfPage] = []
    with pymupdf.open(path) as document:
        for index, page in enumerate(document):
            text = page.get_text().strip()
            used_ocr = False
            if len(text) < MIN_EXTRACTABLE_CHARS:
                text = _ocr_page(page, ocr_language)
                used_ocr = True
            pages.append(PdfPage(page_number=index + 1, text=text, used_ocr=used_ocr))
    return pages


def _ocr_page(page: pymupdf.Page, language: str) -> str:
    """Render `page` to an image and run OCR on it."""
    pixmap = page.get_pixmap(dpi=OCR_RENDER_DPI)
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    try:
        return pytesseract.image_to_string(image, lang=language).strip()
    except pytesseract.TesseractNotFoundError as error:
        raise OcrUnavailableError(
            "This page has no extractable text and needs OCR, but the Tesseract "
            "binary isn't installed. Install it (e.g. `apt install tesseract-ocr` "
            "on Linux, or https://github.com/UB-Mannheim/tesseract/wiki on Windows)."
        ) from error
