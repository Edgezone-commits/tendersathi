"""Tests for the /companies routes, with the companies db module mocked out."""

from __future__ import annotations

from unittest.mock import patch

from tendersathi.db.models import CompanyRow


def _company(company_id: str = "c1") -> CompanyRow:
    return CompanyRow(
        id=company_id,
        name="Himalayan Builders",
        sector="construction",
        annual_turnover=5_000_000,
        licence_class="A",
        districts=["Kathmandu"],
    )


def test_create_company_returns_201_and_the_created_row(api_client, mock_db_client):
    with patch("tendersathi.api.companies.companies_db") as mock_companies_db:
        mock_companies_db.create_company.return_value = "c1"
        mock_companies_db.get_company.return_value = _company()

        response = api_client.post(
            "/companies",
            json={
                "name": "Himalayan Builders",
                "sector": "construction",
                "annual_turnover": 5_000_000,
                "licence_class": "A",
                "districts": ["Kathmandu"],
            },
        )

    assert response.status_code == 201
    assert response.json()["id"] == "c1"
    mock_companies_db.create_company.assert_called_once_with(
        mock_db_client,
        "Himalayan Builders",
        sector="construction",
        annual_turnover=5_000_000,
        licence_class="A",
        districts=["Kathmandu"],
    )


def test_get_company_returns_404_when_missing(api_client):
    with patch("tendersathi.api.companies.companies_db") as mock_companies_db:
        mock_companies_db.get_company.return_value = None
        response = api_client.get("/companies/missing")

    assert response.status_code == 404


def test_list_companies_returns_every_row(api_client):
    with patch("tendersathi.api.companies.companies_db") as mock_companies_db:
        mock_companies_db.list_companies.return_value = [_company("c1"), _company("c2")]
        response = api_client.get("/companies")

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == ["c1", "c2"]
