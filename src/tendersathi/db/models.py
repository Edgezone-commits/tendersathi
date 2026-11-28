"""Typed row shapes returned by the db module's read functions.

Supabase's client returns plain dicts; everything else in `tendersathi.db`
converts rows into these dataclasses so callers get type-checked fields
instead of stringly-typed dict lookups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse a Postgres/Supabase timestamp string, which may use a trailing `Z`."""
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class TenderRow:
    id: str
    source: str
    source_url: str | None
    external_reference: str | None
    title: str | None
    procuring_entity: str | None
    category: str | None
    district: str | None
    estimated_cost: float | None
    submission_deadline: datetime | None
    fingerprint: str
    status: str
    created_at: datetime
    updated_at: datetime
    eligibility_requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TenderPageRow:
    id: str
    tender_id: str
    page_number: int
    text: str
    used_ocr: bool


@dataclass(frozen=True)
class CompanyRow:
    id: str
    name: str
    sector: str | None
    annual_turnover: float | None
    licence_class: str | None
    districts: list[str]


@dataclass(frozen=True)
class MatchRow:
    id: str
    tender_id: str
    company_id: str
    score: float
    reasoning: str | None
    notified_at: datetime | None = None


@dataclass(frozen=True)
class RunRow:
    id: str
    run_type: str
    status: str
    stats: dict
    error: str | None
    started_at: datetime
    finished_at: datetime | None
