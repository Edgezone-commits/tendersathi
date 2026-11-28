"""Tests for the /tenders routes, with the tenders/matches db modules mocked out."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from tendersathi.db.models import MatchRow, TenderRow


def _tender(tender_id: str = "t1") -> TenderRow:
    now = datetime.now(UTC)
    return TenderRow(
        id=tender_id,
        source="manual_upload",
        source_url=None,
        external_reference=None,
        title="Road repair",
        procuring_entity="Department of Roads",
        category="construction",
        district="Kathmandu",
        estimated_cost=1_000_000,
        submission_deadline=None,
        fingerprint=f"fp-{tender_id}",
        status="new",
        created_at=now,
        updated_at=now,
    )


def test_list_tenders_passes_status_filter_through(api_client, mock_db_client):
    with patch("tendersathi.api.tenders.tenders_db") as mock_tenders_db:
        mock_tenders_db.list_tenders.return_value = [_tender()]
        response = api_client.get("/tenders", params={"status": "new"})

    assert response.status_code == 200
    assert response.json()[0]["id"] == "t1"
    mock_tenders_db.list_tenders.assert_called_once_with(mock_db_client, status="new")


def test_get_tender_returns_404_when_missing(api_client):
    with patch("tendersathi.api.tenders.tenders_db") as mock_tenders_db:
        mock_tenders_db.get_tender.return_value = None
        response = api_client.get("/tenders/missing")

    assert response.status_code == 404


def test_list_tender_matches_returns_matches_for_the_tender(api_client, mock_db_client):
    match = MatchRow(id="m1", tender_id="t1", company_id="c1", score=0.8, reasoning="good fit")
    with patch("tendersathi.api.tenders.matches_db") as mock_matches_db:
        mock_matches_db.list_matches_for_tender.return_value = [match]
        response = api_client.get("/tenders/t1/matches")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "m1", "tender_id": "t1", "company_id": "c1", "score": 0.8, "reasoning": "good fit"}
    ]
    mock_matches_db.list_matches_for_tender.assert_called_once_with(mock_db_client, "t1")
