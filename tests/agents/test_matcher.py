"""Tests for the Matcher agent: per-signal scoring and the run_matcher orchestration.

score_tender_for_company is pure and tested directly against TenderRow/
CompanyRow fixtures; run_matcher is tested with the db modules mocked, same
style as tests/ingestion/test_pipeline.py for run_ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tendersathi.agents.matcher import run_matcher, score_tender_for_company
from tendersathi.db.models import CompanyRow, TenderRow


def _tender(
    category: str | None = None,
    district: str | None = None,
    estimated_cost: float | None = None,
) -> TenderRow:
    now = datetime.now(UTC)
    return TenderRow(
        id="tender-1",
        source="manual_upload",
        source_url=None,
        external_reference=None,
        title="A tender",
        procuring_entity=None,
        category=category,
        district=district,
        estimated_cost=estimated_cost,
        submission_deadline=None,
        fingerprint="fp-1",
        status="new",
        created_at=now,
        updated_at=now,
    )


def _company(
    sector: str | None = None,
    annual_turnover: float | None = None,
    districts: list[str] | None = None,
) -> CompanyRow:
    return CompanyRow(
        id="company-1",
        name="Himalayan Builders Pvt. Ltd.",
        sector=sector,
        annual_turnover=annual_turnover,
        licence_class="A",
        districts=districts or [],
    )


def test_score_tender_for_company_rewards_exact_category_match() -> None:
    tender = _tender(category="construction")
    company = _company(sector="construction")

    result = score_tender_for_company(tender, company)

    assert result.score == 1.0
    assert "matches the company's sector" in result.reasoning


def test_score_tender_for_company_partially_rewards_overlapping_category() -> None:
    tender = _tender(category="road construction")
    company = _company(sector="construction")

    result = score_tender_for_company(tender, company)

    assert result.score == 0.5
    assert "partially overlaps" in result.reasoning


def test_score_tender_for_company_penalizes_unrelated_category() -> None:
    tender = _tender(category="it equipment")
    company = _company(sector="construction")

    result = score_tender_for_company(tender, company)

    assert result.score == 0.0
    assert "does not match" in result.reasoning


def test_score_tender_for_company_skips_category_signal_when_data_missing() -> None:
    tender = _tender(category=None, district="Kathmandu", estimated_cost=500_000)
    company = _company(sector="construction", districts=["Kathmandu"], annual_turnover=1_000_000)

    result = score_tender_for_company(tender, company)

    assert "sector" not in result.reasoning
    assert "District" in result.reasoning
    assert "turnover" in result.reasoning.lower()


def test_score_tender_for_company_rewards_district_match() -> None:
    tender = _tender(district="Kathmandu")
    company = _company(districts=["Kathmandu", "Lalitpur"])

    result = score_tender_for_company(tender, company)

    assert result.score == 1.0
    assert "is one the company operates in" in result.reasoning


def test_score_tender_for_company_penalizes_district_outside_company_list() -> None:
    tender = _tender(district="Biratnagar")
    company = _company(districts=["Kathmandu"])

    result = score_tender_for_company(tender, company)

    assert result.score == 0.0
    assert "not one the company operates in" in result.reasoning


def test_score_tender_for_company_skips_district_signal_when_company_has_no_preference() -> None:
    tender = _tender(district="Biratnagar", category="construction")
    company = _company(sector="construction", districts=[])

    result = score_tender_for_company(tender, company)

    assert "District" not in result.reasoning
    assert result.score == 1.0  # only the category signal counted


def test_score_tender_for_company_rewards_sufficient_turnover() -> None:
    tender = _tender(estimated_cost=1_000_000)
    company = _company(annual_turnover=5_000_000)

    result = score_tender_for_company(tender, company)

    assert result.score == 1.0
    assert "covers the estimated cost" in result.reasoning


def test_score_tender_for_company_penalizes_insufficient_turnover() -> None:
    tender = _tender(estimated_cost=5_000_000)
    company = _company(annual_turnover=1_000_000)

    result = score_tender_for_company(tender, company)

    assert result.score == 0.0
    assert "is below the estimated cost" in result.reasoning


def test_score_tender_for_company_combines_weighted_signals() -> None:
    tender = _tender(category="construction", district="Kathmandu", estimated_cost=1_000_000)
    company = _company(sector="construction", districts=["Pokhara"], annual_turnover=5_000_000)

    result = score_tender_for_company(tender, company)

    # category (1.0 * 0.5) + district (0.0 * 0.3) + turnover (1.0 * 0.2) = 0.7
    assert result.score == 0.7


def test_score_tender_for_company_returns_zero_when_nothing_can_be_scored() -> None:
    tender = _tender()
    company = _company()

    result = score_tender_for_company(tender, company)

    assert result.score == 0.0
    assert result.reasoning == "Not enough data to score this match."


@patch("tendersathi.agents.matcher.matches_db")
@patch("tendersathi.agents.matcher.companies_db")
@patch("tendersathi.agents.matcher.tenders_db")
@patch("tendersathi.agents.matcher.runs_db")
def test_run_matcher_scores_every_tender_against_every_company(
    mock_runs_db, mock_tenders_db, mock_companies_db, mock_matches_db
):
    mock_runs_db.start_run.return_value = "run-1"
    mock_tenders_db.list_tenders.return_value = [_tender(category="construction"), _tender()]
    mock_companies_db.list_companies.return_value = [_company(sector="construction")]

    client = MagicMock()
    stats = run_matcher(client=client)

    assert stats.tenders_scored == 2
    assert stats.companies == 1
    assert stats.matches_saved == 2
    mock_tenders_db.list_tenders.assert_called_once_with(client, status="new")
    assert mock_matches_db.save_match.call_count == 2
    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "success"


@patch("tendersathi.agents.matcher.companies_db")
@patch("tendersathi.agents.matcher.tenders_db")
@patch("tendersathi.agents.matcher.runs_db")
def test_run_matcher_marks_run_failed_and_reraises_on_error(
    mock_runs_db, mock_tenders_db, mock_companies_db
):
    mock_runs_db.start_run.return_value = "run-1"
    mock_tenders_db.list_tenders.side_effect = RuntimeError("db blew up")

    with pytest.raises(RuntimeError, match="db blew up"):
        run_matcher(client=MagicMock())

    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "failed"
