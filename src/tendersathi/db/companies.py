"""Read/write access to the `companies` table.

Company profiles are created by Phase 3 (the Matcher agent); this module
just owns the CRUD so Phase 3 doesn't need to know Supabase's query syntax.
"""

from __future__ import annotations

from supabase import Client
from tendersathi.db.models import CompanyRow


def create_company(
    client: Client,
    name: str,
    *,
    sector: str | None = None,
    annual_turnover: float | None = None,
    licence_class: str | None = None,
    districts: list[str] | None = None,
) -> str:
    """Insert a new company profile and return its id."""
    payload = {
        "name": name,
        "sector": sector,
        "annual_turnover": annual_turnover,
        "licence_class": licence_class,
        "districts": districts or [],
    }
    response = client.table("companies").insert(payload).execute()
    return response.data[0]["id"]


def get_company(client: Client, company_id: str) -> CompanyRow | None:
    """Look up a company profile by id."""
    response = client.table("companies").select("*").eq("id", company_id).limit(1).execute()
    rows = response.data
    return _company_from_row(rows[0]) if rows else None


def list_companies(client: Client) -> list[CompanyRow]:
    """List every company profile."""
    response = client.table("companies").select("*").execute()
    return [_company_from_row(row) for row in response.data]


def _company_from_row(row: dict) -> CompanyRow:
    return CompanyRow(
        id=row["id"],
        name=row["name"],
        sector=row.get("sector"),
        annual_turnover=row.get("annual_turnover"),
        licence_class=row.get("licence_class"),
        districts=row.get("districts") or [],
    )
