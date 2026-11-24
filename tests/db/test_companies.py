"""Tests for the companies db module, with Supabase mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

from tendersathi.db import companies as companies_db

_ROW = {
    "id": "company-1",
    "name": "Himalayan Builders Pvt. Ltd.",
    "sector": "construction",
    "annual_turnover": 5_000_000,
    "licence_class": "A",
    "districts": ["Kathmandu", "Lalitpur"],
}


def test_create_company_returns_new_id(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "company-1"}])

    company_id = companies_db.create_company(
        mock_client, "Himalayan Builders Pvt. Ltd.", sector="construction"
    )

    assert company_id == "company-1"
    payload = mock_table.insert.call_args.args[0]
    assert payload["name"] == "Himalayan Builders Pvt. Ltd."
    assert payload["sector"] == "construction"
    assert payload["districts"] == []


def test_get_company_returns_none_when_missing(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[])

    assert companies_db.get_company(mock_client, "missing") is None


def test_get_company_parses_row(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[_ROW])

    company = companies_db.get_company(mock_client, "company-1")

    assert company is not None
    assert company.name == "Himalayan Builders Pvt. Ltd."
    assert company.districts == ["Kathmandu", "Lalitpur"]


def test_list_companies_parses_all_rows(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[_ROW, _ROW])

    companies = companies_db.list_companies(mock_client)

    assert len(companies) == 2
