"""Read/write access to the `matches` table.

Matches are produced by Phase 3 (the Matcher agent); this module just owns
the CRUD, keyed by the unique (tender_id, company_id) pair so re-scoring a
tender updates the existing match instead of duplicating it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from supabase import Client
from tendersathi.db.models import MatchRow, parse_timestamp


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


def list_unnotified_matches(client: Client, min_score: float) -> list[MatchRow]:
    """List matches at or above `min_score` that haven't gone out in a digest yet.

    Used by the Notifier (Phase 6) to build each day's email digest
    without resending a match a company already saw in a previous run.
    """
    response = (
        client.table("matches")
        .select("*")
        .gte("score", min_score)
        .is_("notified_at", "null")
        .order("score", desc=True)
        .execute()
    )
    return [_match_from_row(row) for row in response.data]


def mark_matches_notified(client: Client, match_ids: list[str]) -> None:
    """Stamp `notified_at` on every match id so the next digest skips them."""
    if not match_ids:
        return
    client.table("matches").update({"notified_at": datetime.now(UTC).isoformat()}).in_(
        "id", match_ids
    ).execute()


def _match_from_row(row: dict) -> MatchRow:
    return MatchRow(
        id=row["id"],
        tender_id=row["tender_id"],
        company_id=row["company_id"],
        score=row["score"],
        reasoning=row.get("reasoning"),
        notified_at=parse_timestamp(row.get("notified_at")),
    )
