"""Drafter agent: a document-prep checklist and a cover-letter draft.

The document checklist is built deterministically from the Eligibility
agent's checklist (Phase 4) -- it's just that checklist reframed as actions
a bidder needs to take, so every line keeps its page citation. The cover
letter is the one part that genuinely needs an LLM (natural-language
prose), so it's the only LLM call here, and the prompt explicitly tells it
not to claim a "missing"/"unclear" requirement is met -- an SME could lose
a bid security deposit over a dishonest cover letter. Either way, this
agent only drafts; nothing here is final until a human approves it (see
`tendersathi.orchestration`, which pauses the pipeline for that approval
before treating this output as finished).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from tendersathi.agents.eligibility import ChecklistItem
from tendersathi.db.models import CompanyRow, TenderRow
from tendersathi.llm.base import LLMClient

MAX_COMPLETION_TOKENS = 600

_DOCUMENT_ACTIONS = {
    "met": "Attach evidence",
    "missing": "Address this gap before submitting, or do not bid",
    "unclear": "Verify manually and gather supporting documents",
}


class _CoverLetterOutput(BaseModel):
    cover_letter: str


@dataclass(frozen=True)
class DraftOutput:
    """The Drafter's output: a prep checklist and a cover-letter draft."""

    document_checklist: list[str]
    cover_letter: str


def build_document_checklist(checklist: list[ChecklistItem]) -> list[str]:
    """Turn the Eligibility checklist into a flat list of prep actions.

    Each line keeps the status and page citation from Eligibility, so a
    reviewer can jump straight to the source clause.
    """
    return [
        f"[{item.status.upper()}] {item.requirement} (page {item.page_number}) "
        f"— {_DOCUMENT_ACTIONS[item.status]}."
        for item in checklist
    ]


def _build_prompt(tender: TenderRow, company: CompanyRow, checklist: list[ChecklistItem]) -> str:
    checklist_lines = "\n".join(
        f"- [{item.status.upper()}] {item.requirement}" for item in checklist
    ) or "- (no eligibility requirements were extracted from the bid document)"
    return (
        "Draft a short, professional cover letter for a Nepali SME bidding on a "
        "government tender. Be strictly factual: if a checklist item below is "
        "'MISSING' or 'UNCLEAR', the letter must NOT claim that requirement is met -- "
        "say the company is addressing or verifying it instead. Keep it under 250 "
        "words, formal business-letter tone, plain text (no markdown).\n\n"
        f"Tender: {tender.title or 'Untitled tender'}\n"
        f"Procuring entity: {tender.procuring_entity or 'Not stated'}\n"
        f"Bidding company: {company.name} (sector: {company.sector or 'not stated'})\n\n"
        "Eligibility checklist:\n"
        f"{checklist_lines}"
    )


def run_drafter(
    llm_client: LLMClient,
    tender: TenderRow,
    company: CompanyRow,
    checklist: list[ChecklistItem],
) -> DraftOutput:
    """Build the document checklist and draft a cover letter for `company`/`tender`."""
    document_checklist = build_document_checklist(checklist)

    extraction = llm_client.generate(
        _build_prompt(tender, company, checklist),
        _CoverLetterOutput,
        max_retries=2,
        max_tokens=MAX_COMPLETION_TOKENS,
    )

    return DraftOutput(document_checklist=document_checklist, cover_letter=extraction.cover_letter)
