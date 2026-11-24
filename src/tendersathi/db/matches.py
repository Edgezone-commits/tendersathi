"""Read/write access to the `matches` table.

Matches are produced by Phase 3 (the Matcher agent); this module just owns
the CRUD, keyed by the unique (tender_id, company_id) pair so re-scoring a
tender updates the existing match instead of duplicating it.
"""

from __future__ import annotations

from supabase import Client
from tendersathi.db.models import MatchRow


def save_match(
    client: Client,
    tender_id: str,
    company_id: str,
    score: float,
    reasoning: str | None = None,
) -> str:
    """Upsert a match score for a (tender, company) pair."""
    payload = {
        "tender_id": tender_id,
        "company_id": company_id,
        "score": score,
        "reasoning": reasoning,
    }
    response = client.table("matches").upsert(payload, on_conflict="tender_id,company_id").execute()
    return response.data[0]["id"]


def list_matches_for_tender(client: Client, tender_id: str) -> list[MatchRow]:
    """List every match recorded for a tender, highest score first."""
    response = (
        client.table("matches")
        .select("*")
        .eq("tender_id", tender_id)
        .order("score", desc=True)
        .execute()
    )
    return [_match_from_row(row) for row in response.data]


def _match_from_row(row: dict) -> MatchRow:
    return MatchRow(
        id=row["id"],
        tender_id=row["tender_id"],
        company_id=row["company_id"],
        score=row["score"],
        reasoning=row.get("reasoning"),
    )
