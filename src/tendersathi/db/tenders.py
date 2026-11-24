"""Read/write access to the `tenders` and `tender_pages` tables."""

from __future__ import annotations

from supabase import Client
from tendersathi.db.models import TenderRow, parse_timestamp
from tendersathi.ingestion.sources import RawTenderUpload


def get_tender_by_fingerprint(client: Client, fingerprint: str) -> TenderRow | None:
    """Look up a tender by its dedup fingerprint; used to skip re-ingesting it."""
    response = (
        client.table("tenders").select("*").eq("fingerprint", fingerprint).limit(1).execute()
    )
    rows = response.data
    return _tender_from_row(rows[0]) if rows else None


def save_raw_tender(client: Client, upload: RawTenderUpload) -> str:
    """Upsert a tender and its pages, keyed by fingerprint so re-runs don't duplicate it."""
    payload = {
        "source": upload.source,
        "source_url": upload.source_url,
        "external_reference": upload.external_reference,
        "title": upload.title_hint,
        "fingerprint": upload.fingerprint,
    }
    response = client.table("tenders").upsert(payload, on_conflict="fingerprint").execute()
    tender_id: str = response.data[0]["id"]

    page_payloads = [
        {
            "tender_id": tender_id,
            "page_number": page.page_number,
            "text": page.text,
            "used_ocr": page.used_ocr,
        }
        for page in upload.pages
    ]
    if page_payloads:
        client.table("tender_pages").upsert(
            page_payloads, on_conflict="tender_id,page_number"
        ).execute()

    return tender_id


def list_tenders(client: Client, status: str | None = None) -> list[TenderRow]:
    """List tenders, optionally filtered by status (e.g. 'new')."""
    query = client.table("tenders").select("*")
    if status is not None:
        query = query.eq("status", status)
    response = query.execute()
    return [_tender_from_row(row) for row in response.data]


def _tender_from_row(row: dict) -> TenderRow:
    return TenderRow(
        id=row["id"],
        source=row["source"],
        source_url=row.get("source_url"),
        external_reference=row.get("external_reference"),
        title=row.get("title"),
        procuring_entity=row.get("procuring_entity"),
        category=row.get("category"),
        district=row.get("district"),
        estimated_cost=row.get("estimated_cost"),
        submission_deadline=parse_timestamp(row.get("submission_deadline")),
        fingerprint=row["fingerprint"],
        status=row["status"],
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
    )
