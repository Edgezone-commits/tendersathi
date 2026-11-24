"""Scout agent: turns a raw tender PDF into a structured `Tender` record.

Nepali Standard Bidding Documents put almost every structured fact (the
purchaser, district, deadlines, qualification/eligibility criteria) inside
two predictable sections -- the cover/Invitation for Bids pages, and the
"Bid Data Sheet" / "Evaluation and Qualification Criteria" sections -- and
bury it among 60-140 pages of boilerplate procurement law in between.
Sending the whole document to the LLM would blow through free-tier context
and token limits for no benefit, so this module first narrows the document
to those candidate pages with plain keyword search, then asks the LLM to
extract fields only from what it's given.

Bikram Sambat (BS) dates are transcribed by the LLM, not computed by it, and
converted to AD deterministically in `tendersathi.ingestion.nepali_dates`
(see that module's docstring for why).
"""

from __future__ import annotations

import logging
import re
from datetime import date

from pydantic import BaseModel, Field

from tendersathi.ingestion.nepali_dates import InvalidBsDateError, bs_to_ad
from tendersathi.ingestion.pdf_loader import PdfPage
from tendersathi.llm.base import LLMClient

logger = logging.getLogger(__name__)

# Groq's free tier rate-limits by tokens PER MINUTE, not just per request,
# and it's as low as 8000 TPM on some models/accounts -- well under what a
# full Bid Data Sheet + Evaluation and Qualification Criteria section needs
# (~30-38k chars on the samples this was tuned against). MAX_PROMPT_CHARS is
# deliberately conservative (prompt tokens + MAX_COMPLETION_TOKENS must clear
# that ceiling with room to spare) rather than sized to fit a whole section.
MAX_CANDIDATE_PAGES = 32
MAX_PROMPT_CHARS = 20_000
MAX_COMPLETION_TOKENS = 1200
COVER_PAGE_COUNT = 6

# A Nepali Standard Bidding Document's cover/Table of Contents pages (always
# within COVER_PAGE_COUNT) list these same section names, and the
# Instructions to Bidders repeatedly cross-reference them inline (e.g. "...as
# specified in Section V, Schedule of Requirements"). Both would wrongly
# match a plain substring search, so this only matches a line that reads
# like an actual section heading: "Section <roman numeral>. <name>".
_SECTION_HEADER_RE = re.compile(r"^section\s+[ivxlc]+[.:]?\s*(.+)$", re.IGNORECASE)
_BDS_HEADER_MARKER = "bid data sheet"
_EQC_HEADER_MARKER = "evaluation and qualification criteria"
_END_HEADER_MARKER = "bidding forms"
# Used only if a Bidding Forms header can't be found to close the section.
_FALLBACK_SECTION_WINDOW = 20

# The standard EQC section itself has two subsections: "1. Evaluation
# Criteria" (price/technical adjustment methodology -- not useful for
# eligibility_requirements) followed by "2. Qualification" (the actual
# eligibility/turnover/experience/financial-resource table). This is part of
# the same GoN/World Bank bidding-document template, not specific to any one
# sample, so it's worth a dedicated marker.
_QUALIFICATION_HEADER_RE = re.compile(r"^2\.\s*qualification\s*$", re.IGNORECASE)


class Tender(BaseModel):
    """A structured tender record extracted from a bid document.

    Every field is optional: the Scout agent must return null for anything
    it can't find in the document rather than guess, so downstream agents
    (Matcher, Eligibility) can tell "not stated" apart from "zero"/"none".
    """

    title: str | None = None
    procuring_entity: str | None = None
    category: str | None = None
    district: str | None = None
    estimated_cost_npr: float | None = None
    deadline: date | None = None
    eligibility_requirements: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


class _ScoutLLMOutput(BaseModel):
    """Raw shape asked of the LLM.

    `deadline_bs`/`deadline_ad` are plain transcriptions of whatever date
    string the document uses; `extract_tender` resolves them into the real
    `date` on `Tender`.
    """

    title: str | None = None
    procuring_entity: str | None = None
    category: str | None = None
    district: str | None = None
    estimated_cost_npr: float | None = None
    deadline_bs: str | None = None
    deadline_ad: str | None = None
    eligibility_requirements: list[str] = Field(default_factory=list)


def select_candidate_pages(pages: list[PdfPage]) -> list[PdfPage]:
    """Narrow a full bid document to the pages likely to hold metadata.

    Always keeps the first few pages (cover sheet + Invitation for Bids),
    plus the Bid Data Sheet and Evaluation and Qualification Criteria
    sections if a header search can locate them, capped so the prompt built
    from the result stays within budget.
    """
    if not pages:
        return []

    cover_pages = [page for page in pages if page.page_number <= COVER_PAGE_COUNT]

    bds_header_pages = _find_section_header_pages(pages, _BDS_HEADER_MARKER)
    eqc_header_pages = _find_section_header_pages(pages, _EQC_HEADER_MARKER)
    start_candidates = bds_header_pages or eqc_header_pages
    if not start_candidates:
        return _cap_pages(cover_pages)

    # The real heading is structurally last: any earlier match is a Table of
    # Contents entry or an inline cross-reference, not the section itself.
    start = max(start_candidates)
    end_header_pages = _find_section_header_pages(pages, _END_HEADER_MARKER)
    later_ends = [page_number for page_number in end_header_pages if page_number > start]
    end = min(later_ends) if later_ends else start + _FALLBACK_SECTION_WINDOW
    section_pages = [page for page in pages if start <= page.page_number < end]

    eqc_starts_in_range = [
        page_number for page_number in eqc_header_pages if start <= page_number < end
    ]
    if eqc_starts_in_range:
        # The Evaluation and Qualification Criteria table holds the concrete
        # eligibility figures (turnover, experience, financial resources);
        # the Bid Data Sheet's own clauses are comparatively generic
        # boilerplate. Prioritize EQC over BDS when the char budget can't
        # fit both in full.
        eqc_start = min(eqc_starts_in_range)
        eqc_pages = [page for page in section_pages if page.page_number >= eqc_start]
        bds_only_pages = [page for page in section_pages if page.page_number < eqc_start]
        priority_ordered = cover_pages + _qualification_first(eqc_pages) + bds_only_pages
    else:
        priority_ordered = cover_pages + section_pages

    capped = _cap_pages(priority_ordered)
    return sorted(capped, key=lambda page: page.page_number)


def _find_section_header_pages(pages: list[PdfPage], marker: str) -> list[int]:
    """Return the page numbers where a line reads as a `marker` section heading."""
    pages_with_header = []
    for page in pages:
        for line in page.text.split("\n"):
            match = _SECTION_HEADER_RE.match(line.strip())
            if match and match.group(1).strip().lower().startswith(marker):
                pages_with_header.append(page.page_number)
                break
    return pages_with_header


def _qualification_first(eqc_pages: list[PdfPage]) -> list[PdfPage]:
    """Reorder an EQC page range so "2. Qualification" comes before "1.
    Evaluation Criteria" -- the latter is price/technical adjustment
    methodology, not useful for `eligibility_requirements`.
    """
    qualification_starts = [
        page.page_number
        for page in eqc_pages
        if any(_QUALIFICATION_HEADER_RE.match(line.strip()) for line in page.text.split("\n"))
    ]
    if not qualification_starts:
        return eqc_pages

    qualification_start = min(qualification_starts)
    qualification_pages = [page for page in eqc_pages if page.page_number >= qualification_start]
    evaluation_criteria_pages = [
        page for page in eqc_pages if page.page_number < qualification_start
    ]
    return qualification_pages + evaluation_criteria_pages


def _cap_pages(pages: list[PdfPage]) -> list[PdfPage]:
    """Trim to MAX_CANDIDATE_PAGES / MAX_PROMPT_CHARS so the prompt stays small."""
    result: list[PdfPage] = []
    total_chars = 0
    for page in pages[:MAX_CANDIDATE_PAGES]:
        total_chars += len(page.text)
        if total_chars > MAX_PROMPT_CHARS and result:
            logger.warning(
                "Scout input truncated at page %s: char budget (%s) exceeded",
                page.page_number,
                MAX_PROMPT_CHARS,
            )
            break
        result.append(page)
    return result


def _build_prompt(pages: list[PdfPage]) -> str:
    excerpts = "\n\n".join(f"[Page {page.page_number}]\n{page.text}" for page in pages)
    return (
        "The pages below are excerpts from a Nepali government bid/tender document "
        "(a Standard Bidding Document). The text may mix English and Nepali. Extract:\n"
        "- title: the name of the goods/works/services being procured\n"
        "- procuring_entity: the office/organization issuing the tender\n"
        "- category: a short category label classifying what's being procured (e.g. "
        "'Medical Supplies', 'Construction', 'IT Equipment', 'Consulting Services'). "
        "This is a classification you make from the title/description below, not a "
        "literal lookup -- the document will not contain the word 'category'. Only "
        "return null here if the title/description is too vague to classify at all.\n"
        "- district: the Nepali district where the work/delivery takes place\n"
        "- estimated_cost_npr: the estimated/approved cost of THIS procurement's goods, "
        "works, or services, in NPR, as a plain number with no currency symbol or commas. "
        "ONLY use a figure explicitly labelled as the estimated cost, approved cost, cost "
        "estimate, or budget of the contract itself. Many Nepali bidding documents never "
        "disclose this figure at all, so null is a common and correct answer. Do NOT use: "
        "a bid security amount; a minimum turnover/experience/financial-resource "
        "qualification figure; or the monetary threshold in the ITB clauses about a "
        "bidder's complaint going to the Public Procurement Review Committee (often "
        "clause 'ITB 45.x') -- that threshold is a fixed regulatory amount unrelated to "
        "this specific contract, even though it is also stated in NPR. When in doubt "
        "between two NPR figures, return null rather than pick one.\n"
        "- deadline_bs: the bid submission deadline, exactly as written in Bikram Sambat "
        "(BS), formatted 'YYYY-MM-DD', if the document gives one\n"
        "- deadline_ad: the same bid submission deadline, but ONLY if the document also "
        "gives it directly in the Gregorian/AD calendar (often in parentheses after the "
        "BS date, e.g. '2083-08-25(2026-12-11)' -> '2026-12-11'), formatted 'YYYY-MM-DD'\n"
        "- eligibility_requirements: a list of short strings, one per distinct eligibility "
        "or qualification requirement a bidder must meet (e.g. registration, minimum "
        "annual turnover, years of experience, financial resources)\n\n"
        "Rules:\n"
        "- Every field except `category` is a literal fact: if it is not explicitly "
        "stated in the text below, return null for it (or an empty list for "
        "eligibility_requirements). Never guess or infer a factual value that isn't in "
        "the text, and never reuse a figure stated for a different purpose (e.g. a bid "
        "security or review-threshold amount is not the estimated cost).\n"
        "- Transcribe dates exactly as written; do not convert BS to AD yourself.\n\n"
        f"{excerpts}"
    )


def extract_tender(llm_client: LLMClient, pages: list[PdfPage]) -> Tender:
    """Run the Scout agent over `pages`, returning a structured `Tender`.

    `pages` is normally the full set of pages from `load_pdf_pages`; this
    function narrows them to candidate pages itself before calling the LLM.
    """
    candidates = select_candidate_pages(pages)
    if not candidates:
        return Tender()

    extraction = llm_client.generate(
        _build_prompt(candidates),
        _ScoutLLMOutput,
        max_retries=2,
        max_tokens=MAX_COMPLETION_TOKENS,
    )

    return Tender(
        title=extraction.title,
        procuring_entity=extraction.procuring_entity,
        category=extraction.category,
        district=extraction.district,
        estimated_cost_npr=extraction.estimated_cost_npr,
        deadline=_resolve_deadline(extraction),
        eligibility_requirements=extraction.eligibility_requirements,
        source_pages=[page.page_number for page in candidates],
    )


def _resolve_deadline(extraction: _ScoutLLMOutput) -> date | None:
    """Prefer an AD date the document states directly; else convert the BS one."""
    if extraction.deadline_ad:
        try:
            return date.fromisoformat(extraction.deadline_ad)
        except ValueError:
            logger.warning("Scout returned an unparseable deadline_ad: %r", extraction.deadline_ad)

    if extraction.deadline_bs:
        try:
            return bs_to_ad(extraction.deadline_bs)
        except InvalidBsDateError:
            logger.warning("Scout returned an unparseable deadline_bs: %r", extraction.deadline_bs)

    return None
