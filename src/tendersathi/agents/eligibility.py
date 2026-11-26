"""Eligibility agent: a "required / you have / missing" checklist from the bid document.

Every checklist item must cite the exact page its requirement came from, so
a human reviewing the digest can jump straight to the clause instead of
re-reading the whole document. This agent splits that work the same way
Scout (Phase 2) splits date handling: the LLM only transcribes what's on
the page -- which requirement, which page, and its type/threshold -- and
plain Python (not the LLM) decides "met / missing / unclear" against the
company profile. That keeps the eligibility verdict deterministic and
testable without re-prompting the LLM for it.

Only two requirement types are compared automatically for now (minimum
annual turnover, minimum licence class) because those are the only ones a
`CompanyRow` can currently answer; everything else (registration, years of
experience, specific documents) comes back "unclear" for a human to check
by hand rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from tendersathi.agents.scout import select_candidate_pages
from tendersathi.db.models import CompanyRow
from tendersathi.ingestion.pdf_loader import PdfPage
from tendersathi.llm.base import LLMClient

MAX_COMPLETION_TOKENS = 1500

ChecklistStatus = Literal["met", "missing", "unclear"]
_RequirementType = Literal["turnover", "licence_class", "other"]


class _RequirementExtraction(BaseModel):
    """One requirement as transcribed by the LLM, with its page citation."""

    requirement: str
    page_number: int
    requirement_type: _RequirementType
    minimum_turnover_npr: float | None = None
    minimum_licence_class: str | None = None


class _EligibilityLLMOutput(BaseModel):
    requirements: list[_RequirementExtraction] = Field(default_factory=list)


@dataclass(frozen=True)
class ChecklistItem:
    """One row of the eligibility checklist, ready to show a bidder."""

    requirement: str
    page_number: int
    status: ChecklistStatus
    reasoning: str


def _build_prompt(pages: list[PdfPage]) -> str:
    excerpts = "\n\n".join(f"[Page {page.page_number}]\n{page.text}" for page in pages)
    return (
        "The pages below are excerpts from a Nepali government bid/tender document's "
        "qualification/eligibility criteria section. The text may mix English and "
        "Nepali. Extract every distinct eligibility or qualification requirement a "
        "bidder must meet as a list of objects, each with:\n"
        "- requirement: a short, exact-as-possible restatement of the requirement\n"
        "- page_number: the page number (from the [Page N] marker) this requirement "
        "appears under\n"
        "- requirement_type: 'turnover' if it is a minimum annual turnover/financial-"
        "capacity requirement, 'licence_class' if it is a minimum contractor/supplier "
        "licence class or category requirement, or 'other' for anything else "
        "(registration, years of experience, specific documents, etc.)\n"
        "- minimum_turnover_npr: the minimum NPR figure, ONLY when requirement_type is "
        "'turnover'; otherwise null\n"
        "- minimum_licence_class: the minimum licence class/category (e.g. 'A'), ONLY "
        "when requirement_type is 'licence_class'; otherwise null\n\n"
        "Rules:\n"
        "- Every requirement must cite the exact page number it was found on.\n"
        "- Never invent a requirement that isn't stated in the text below.\n"
        "- If the same requirement is repeated on multiple pages, cite the page where "
        "it is stated most precisely.\n\n"
        f"{excerpts}"
    )


def run_eligibility_check(
    llm_client: LLMClient, pages: list[PdfPage], company: CompanyRow
) -> list[ChecklistItem]:
    """Build the eligibility checklist for `company` against a bid document's `pages`.

    Reuses Scout's `select_candidate_pages` to narrow the document to its
    Bid Data Sheet / Evaluation and Qualification Criteria section, for the
    same reason Scout does: that's where the eligibility requirements live,
    and sending the whole document would blow Groq's free-tier token budget.
    """
    candidates = select_candidate_pages(pages)
    if not candidates:
        return []

    extraction = llm_client.generate(
        _build_prompt(candidates),
        _EligibilityLLMOutput,
        max_retries=2,
        max_tokens=MAX_COMPLETION_TOKENS,
    )

    return [_evaluate_requirement(item, company) for item in extraction.requirements]


def _evaluate_requirement(item: _RequirementExtraction, company: CompanyRow) -> ChecklistItem:
    if item.requirement_type == "turnover":
        status, reasoning = _check_turnover(item.minimum_turnover_npr, company.annual_turnover)
    elif item.requirement_type == "licence_class":
        status, reasoning = _check_licence_class(item.minimum_licence_class, company.licence_class)
    else:
        status, reasoning = (
            "unclear",
            "No company-profile field covers this requirement; verify manually.",
        )
    return ChecklistItem(
        requirement=item.requirement,
        page_number=item.page_number,
        status=status,
        reasoning=reasoning,
    )


def _check_turnover(
    required: float | None, have: float | None
) -> tuple[ChecklistStatus, str]:
    if required is None or have is None:
        return "unclear", "A turnover figure (required or on file) is missing; verify manually."
    if have >= required:
        return (
            "met",
            f"Company's annual turnover (NPR {have:,.0f}) meets the minimum "
            f"(NPR {required:,.0f}).",
        )
    return (
        "missing",
        f"Company's annual turnover (NPR {have:,.0f}) is below the minimum "
        f"(NPR {required:,.0f}).",
    )


def _check_licence_class(required: str | None, have: str | None) -> tuple[ChecklistStatus, str]:
    if required is None or have is None:
        return "unclear", "A licence class (required or on file) is missing; verify manually."
    if required.strip().lower() == have.strip().lower():
        return "met", f"Company holds the required licence class ('{have}')."
    return (
        "missing",
        f"Company holds licence class '{have}', but '{required}' is required; licence-"
        "class hierarchies vary by category, so verify manually before ruling this out.",
    )
