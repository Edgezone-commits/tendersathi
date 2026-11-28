"""HTTP routes for reading tenders and the matches scored against them."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from supabase import Client
from tendersathi.api.deps import get_db_client
from tendersathi.api.schemas import MatchOut, TenderOut
from tendersathi.db import matches as matches_db
from tendersathi.db import tenders as tenders_db
from tendersathi.db.models import MatchRow, TenderRow

router = APIRouter(prefix="/tenders", tags=["tenders"])


@router.get("", response_model=list[TenderOut])
def list_tenders(
    status: str | None = None, client: Client = Depends(get_db_client)
) -> list[TenderRow]:
    return tenders_db.list_tenders(client, status=status)


@router.get("/{tender_id}", response_model=TenderOut)
def get_tender(tender_id: str, client: Client = Depends(get_db_client)) -> TenderRow:
    tender = tenders_db.get_tender(client, tender_id)
    if tender is None:
        raise HTTPException(status_code=404, detail="Tender not found")
    return tender


@router.get("/{tender_id}/matches", response_model=list[MatchOut])
def list_tender_matches(
    tender_id: str, client: Client = Depends(get_db_client)
) -> list[MatchRow]:
    return matches_db.list_matches_for_tender(client, tender_id)
