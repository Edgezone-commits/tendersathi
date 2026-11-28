"""Pydantic request/response shapes for the HTTP API.

Kept separate from the dataclasses in `tendersathi.db.models`: those are
internal row shapes, these are the public HTTP contract, free to evolve
independently (e.g. hiding a column, renaming a field for API consumers)
without touching the db layer. Every `*Out` model sets
`from_attributes=True` so a route can return a db dataclass straight from
`tendersathi.db` and let pydantic read its fields, instead of translating
field-by-field in every route.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    name: str
    sector: str | None = None
    annual_turnover: float | None = None
    licence_class: str | None = None
    districts: list[str] = []


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    sector: str | None
    annual_turnover: float | None
    licence_class: str | None
    districts: list[str]


class TenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    title: str | None
    procuring_entity: str | None
    category: str | None
    district: str | None
    estimated_cost: float | None
    submission_deadline: datetime | None
    status: str
    eligibility_requirements: list[str]


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tender_id: str
    company_id: str
    score: float
    reasoning: str | None


class PipelineRunCreate(BaseModel):
    tender_id: str
    company_id: str


class PipelineDecision(BaseModel):
    approved: bool


class PipelineRunOut(BaseModel):
    """A pipeline run's current state: either paused for approval or finished.

    `document_checklist`/`cover_letter`/`question` are only set while
    `status` is `"pending_approval"`; `approved` is only set once a decision
    has actually been submitted and the graph has run past `approval`.
    """

    thread_id: str
    status: Literal["pending_approval", "completed"]
    question: str | None = None
    document_checklist: list[str] | None = None
    cover_letter: str | None = None
    approved: bool | None = None
