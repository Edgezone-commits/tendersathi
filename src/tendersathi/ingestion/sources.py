"""Where raw tenders come from before the Scout agent (Phase 2) reads them.

Every source produces the same `RawTenderUpload` shape, so the ingestion
pipeline and the db layer never need to know whether a tender arrived via
manual upload or (later) an automated scraper.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tendersathi.ingestion.dedup import compute_fingerprint
from tendersathi.ingestion.pdf_loader import PdfPage, load_pdf_pages

logger = logging.getLogger(__name__)

MANUAL_UPLOAD_SOURCE = "manual_upload"
BOLPATRA_SOURCE = "bolpatra"


@dataclass(frozen=True)
class RawTenderUpload:
    """A tender document plus just enough metadata to store and dedup it."""

    source: str
    file_path: Path
    external_reference: str | None
    title_hint: str | None
    source_url: str | None
    pages: list[PdfPage]
    fingerprint: str


class TenderSource(Protocol):
    """Anything that can produce new `RawTenderUpload` records for ingestion."""

    def fetch_new(self) -> list[RawTenderUpload]: ...


class ManualUploadSource:
    """Loads tenders a human has saved locally into an inbox directory.

    This is the only working source right now. See `BolpatraScraper` below for
    why an automated scraper isn't built yet, and for the interface it should
    implement when one is added.
    """

    def __init__(self, inbox_dir: Path) -> None:
        self.inbox_dir = inbox_dir

    def fetch_new(self) -> list[RawTenderUpload]:
        """Load every PDF in the inbox directory, skipping any that fail to load.

        A single bad file (e.g. a scanned page needing OCR that isn't
        available) shouldn't abort ingestion for every other tender in the
        batch, so a load failure is logged and skipped rather than raised.
        """
        uploads: list[RawTenderUpload] = []
        for path in sorted(self.inbox_dir.glob("*.pdf")):
            try:
                uploads.append(self.load_file(path))
            except Exception:
                logger.warning("Skipping %s: failed to load", path, exc_info=True)
        return uploads

    def load_file(
        self,
        file_path: Path,
        *,
        title_hint: str | None = None,
        source_url: str | None = None,
        external_reference: str | None = None,
    ) -> RawTenderUpload:
        """Load one PDF and fingerprint it from the file's own bytes."""
        pages = load_pdf_pages(file_path)
        fingerprint = compute_fingerprint(
            source=MANUAL_UPLOAD_SOURCE,
            external_reference=external_reference,
            file_bytes=file_path.read_bytes(),
        )
        return RawTenderUpload(
            source=MANUAL_UPLOAD_SOURCE,
            file_path=file_path,
            external_reference=external_reference,
            title_hint=title_hint or file_path.stem,
            source_url=source_url,
            pages=pages,
            fingerprint=fingerprint,
        )


class BolpatraScraper:
    """Not implemented. Checked on 2026-11-24, before writing any scraping code:

    - `robots.txt` (https://www.bolpatra.gov.np/robots.txt) does not block
      crawling in general, but disallows `/api`, `/dashboard`, `/auth`,
      `/login`, `/register`, `/account`, `/oidc`, `/workspace`, `/custody`,
      `/internal`, `/procurement-`.
    - The site itself is a client-rendered single-page app: a plain fetch of
      the homepage returns ~36 bytes of text and no server-rendered tender
      data. The tender search/listing data is therefore almost certainly
      loaded via calls into `/api`, which robots.txt disallows.

    Per CLAUDE.md's instruction, that combination (disallowed data path, no
    static HTML to parse) means: don't build an HTTP scraper against this
    site. `ManualUploadSource` is the supported path until this changes.

    If a scraper is added later, it should implement `fetch_new()` with the
    same signature as `ManualUploadSource` (see `TenderSource`), and would
    need a headless browser (Playwright) plus an explicit decision about any
    CAPTCHA — both out of scope for this free-tier phase.
    """

    def fetch_new(self) -> list[RawTenderUpload]:
        """Always raises; see the class docstring for why."""
        raise NotImplementedError(
            "bolpatra.gov.np's tender data loads from API paths its robots.txt "
            "disallows scraping, behind a JS single-page app with no static "
            "HTML to parse. Use ManualUploadSource instead."
        )
