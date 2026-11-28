"""HTTP routes for company profiles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from supabase import Client
from tendersathi.api.deps import get_db_client
from tendersathi.api.schemas import CompanyCreate, CompanyOut
from tendersathi.db import companies as companies_db
from tendersathi.db.models import CompanyRow

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(
    body: CompanyCreate, client: Client = Depends(get_db_client)
) -> CompanyRow | None:
    company_id = companies_db.create_company(
        client,
        body.name,
        sector=body.sector,
        annual_turnover=body.annual_turnover,
        licence_class=body.licence_class,
        districts=body.districts,
    )
    return companies_db.get_company(client, company_id)


@router.get("", response_model=list[CompanyOut])
def list_companies(client: Client = Depends(get_db_client)) -> list[CompanyRow]:
    return companies_db.list_companies(client)


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: str, client: Client = Depends(get_db_client)) -> CompanyRow:
    company = companies_db.get_company(client, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
