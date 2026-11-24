"""Tests for the Scout agent: page selection, prompting, and date resolution.

The LLM is stubbed out entirely -- these tests check the agent's own logic
(which pages it sends, how it turns the LLM's raw output into a `Tender`),
not Groq's behaviour (covered in tests/llm/test_groq_client.py).
"""

from __future__ import annotations

from datetime import date

from tendersathi.agents.scout import (
    MAX_CANDIDATE_PAGES,
    MAX_COMPLETION_TOKENS,
    MAX_PROMPT_CHARS,
    Tender,
    _ScoutLLMOutput,
    extract_tender,
    select_candidate_pages,
)
from tendersathi.ingestion.pdf_loader import PdfPage


def _page(number: int, text: str) -> PdfPage:
    return PdfPage(page_number=number, text=text, used_ocr=False)


class _StubLLMClient:
    """Records the prompt/model it was called with and returns a fixed result."""

    def __init__(self, result: _ScoutLLMOutput) -> None:
        self.result = result
        self.calls: list[tuple[str, type, int, int | None]] = []

    def generate(self, prompt, response_model, max_retries=2, max_tokens=None):
        self.calls.append((prompt, response_model, max_retries, max_tokens))
        return self.result


def test_select_candidate_pages_keeps_cover_and_bds_eqc_section() -> None:
    pages = [
        _page(1, "BIDDING DOCUMENT for Procurement of Widgets"),
        _page(2, "Abbreviations"),
        _page(3, "Table of Contents"),
        _page(4, "Invitation for Bids"),
        _page(5, "Part 1: Bidding Procedures"),
        _page(6, "Section I. Instructions to Bidders"),
        _page(7, "more ITB boilerplate about fraud and corruption"),
        _page(8, "Section II: Bid Data Sheet - District: Kathmandu"),
        _page(9, "Section III. Evaluation and Qualification Criteria - turnover"),
        _page(10, "Section IV. Bidding Forms"),
        _page(11, "Letter of Technical Bid"),
    ]

    selected = select_candidate_pages(pages)
    numbers = [page.page_number for page in selected]

    assert numbers[:6] == [1, 2, 3, 4, 5, 6]
    assert 8 in numbers
    assert 9 in numbers
    assert 11 not in numbers  # past the end-of-section marker on page 10
    assert 10 not in numbers  # the end marker's own page isn't included


def test_select_candidate_pages_handles_empty_input() -> None:
    assert select_candidate_pages([]) == []


def test_select_candidate_pages_does_not_anchor_on_toc_or_cross_references() -> None:
    """Regression test: a Table of Contents entry or an inline cross-reference
    (e.g. "...in accordance with Section III, Evaluation and Qualification
    Criteria") must not be mistaken for the real section heading, which is
    always the LAST matching line in the document.
    """
    pages = [
        _page(1, "BIDDING DOCUMENT"),
        _page(
            3,
            "Table of Contents\n"
            "Section II.  Bid Data Sheet ...........................42\n"
            "Section III.  Evaluation and Qualification Criteria ...48\n"
            "Section IV.  Bidding Forms ..............................61",
        ),
        _page(
            20,
            "shall evaluate deviations amongst those set out in Section III, "
            "Evaluation and Qualification Criteria: insert complementary details",
        ),
        _page(43, "Section II: Bid Data Sheet\nDistrict: Kathmandu"),
        _page(47, "Section III. Evaluation and Qualification Criteria\nTurnover: NPR 1,000,000"),
        _page(60, "Section IV. Bidding Forms"),
        _page(61, "Letter of Technical Bid"),
    ]

    selected = select_candidate_pages(pages)
    numbers = [page.page_number for page in selected]

    assert 43 in numbers
    assert 47 in numbers
    assert 20 not in numbers
    assert 60 not in numbers
    assert 61 not in numbers


def test_select_candidate_pages_prioritizes_eqc_over_bds_when_budget_tight() -> None:
    """The Qualification Criteria table (turnover, experience, financial
    resources) is worth more to `eligibility_requirements` than the Bid Data
    Sheet's generic procedural clauses, so it must survive truncation first.
    """
    pages = [_page(i, f"cover {i}") for i in range(1, 7)]
    pages.append(_page(43, "Section II. Bid Data Sheet\n" + "x" * MAX_PROMPT_CHARS))
    pages.append(_page(44, "x" * MAX_PROMPT_CHARS))
    pages.append(_page(45, "x" * MAX_PROMPT_CHARS))
    pages.append(
        _page(
            47,
            "Section III. Evaluation and Qualification Criteria\n"
            "Minimum average annual turnover of NPR 1,000,000",
        )
    )
    pages.append(_page(60, "Section IV. Bidding Forms"))

    selected = select_candidate_pages(pages)
    numbers = [page.page_number for page in selected]

    assert 47 in numbers
    assert 44 not in numbers
    assert 45 not in numbers


def test_select_candidate_pages_prioritizes_qualification_over_evaluation_methodology() -> None:
    """Within the EQC section itself, "2. Qualification" (the eligibility
    table) must survive truncation ahead of "1. Evaluation Criteria" (price/
    technical adjustment methodology, not useful for eligibility_requirements).
    """
    pages = [_page(i, f"cover {i}") for i in range(1, 7)]
    pages.append(_page(43, "Section II. Bid Data Sheet\nDistrict: Kathmandu"))
    pages.append(
        _page(
            47,
            "Section III. Evaluation and Qualification Criteria\n" + "x" * MAX_PROMPT_CHARS,
        )
    )
    pages.append(_page(48, "x" * MAX_PROMPT_CHARS))
    pages.append(_page(49, "x" * MAX_PROMPT_CHARS))
    pages.append(_page(50, "2. Qualification\nMinimum average annual turnover of NPR 1,000,000"))
    pages.append(_page(60, "Section IV. Bidding Forms"))

    selected = select_candidate_pages(pages)
    numbers = [page.page_number for page in selected]

    assert 50 in numbers
    assert 48 not in numbers


def test_select_candidate_pages_caps_total_pages() -> None:
    pages = [_page(1, "Section II. Bid Data Sheet")]
    pages += [_page(i, "filler body text") for i in range(2, 199)]
    pages.append(_page(199, "Section IV. Bidding Forms"))

    selected = select_candidate_pages(pages)

    assert len(selected) <= MAX_CANDIDATE_PAGES


def test_select_candidate_pages_caps_total_characters() -> None:
    pages = [_page(1, "Section II. Bid Data Sheet")]
    pages += [_page(i, "x" * 10_000) for i in range(2, 10)]
    pages.append(_page(10, "Section IV. Bidding Forms"))

    selected = select_candidate_pages(pages)

    assert sum(len(page.text) for page in selected) <= MAX_PROMPT_CHARS + 10_000
    assert len(selected) < len(pages) - 1  # truncated before reaching the end marker


def test_extract_tender_maps_llm_output_onto_tender_fields() -> None:
    pages = [_page(1, "BIDDING DOCUMENT for Procurement of Widgets")]
    llm_output = _ScoutLLMOutput(
        title="Procurement of Widgets",
        procuring_entity="Ministry of Widgets",
        category="Goods",
        district="Kathmandu",
        estimated_cost_npr=4_200_000.0,
        deadline_bs=None,
        deadline_ad="2026-12-11",
        eligibility_requirements=["Minimum 3 years experience", "VAT registration"],
    )
    client = _StubLLMClient(llm_output)

    tender = extract_tender(client, pages)

    assert tender == Tender(
        title="Procurement of Widgets",
        procuring_entity="Ministry of Widgets",
        category="Goods",
        district="Kathmandu",
        estimated_cost_npr=4_200_000.0,
        deadline=date(2026, 12, 11),
        eligibility_requirements=["Minimum 3 years experience", "VAT registration"],
        source_pages=[1],
    )
    assert client.calls[0][1] is _ScoutLLMOutput
    assert client.calls[0][3] == MAX_COMPLETION_TOKENS


def test_extract_tender_converts_bs_deadline_when_no_ad_date_given() -> None:
    pages = [_page(1, "BIDDING DOCUMENT")]
    llm_output = _ScoutLLMOutput(deadline_bs="2083-08-25", deadline_ad=None)
    client = _StubLLMClient(llm_output)

    tender = extract_tender(client, pages)

    assert tender.deadline == date(2026, 12, 11)


def test_extract_tender_prefers_ad_date_over_bs_date() -> None:
    pages = [_page(1, "BIDDING DOCUMENT")]
    llm_output = _ScoutLLMOutput(deadline_bs="2000-01-01", deadline_ad="2026-12-11")
    client = _StubLLMClient(llm_output)

    tender = extract_tender(client, pages)

    assert tender.deadline == date(2026, 12, 11)


def test_extract_tender_falls_back_to_none_deadline_when_both_missing() -> None:
    pages = [_page(1, "BIDDING DOCUMENT")]
    client = _StubLLMClient(_ScoutLLMOutput())

    tender = extract_tender(client, pages)

    assert tender.deadline is None


def test_extract_tender_falls_back_to_none_deadline_on_invalid_bs_date() -> None:
    pages = [_page(1, "BIDDING DOCUMENT")]
    llm_output = _ScoutLLMOutput(deadline_bs="not-a-date", deadline_ad=None)
    client = _StubLLMClient(llm_output)

    tender = extract_tender(client, pages)

    assert tender.deadline is None


def test_extract_tender_falls_back_to_none_deadline_on_invalid_ad_date() -> None:
    pages = [_page(1, "BIDDING DOCUMENT")]
    llm_output = _ScoutLLMOutput(deadline_bs=None, deadline_ad="not-a-date")
    client = _StubLLMClient(llm_output)

    tender = extract_tender(client, pages)

    assert tender.deadline is None


def test_extract_tender_returns_empty_tender_without_calling_llm_when_no_pages() -> None:
    client = _StubLLMClient(_ScoutLLMOutput())

    tender = extract_tender(client, [])

    assert tender == Tender()
    assert client.calls == []


def test_extract_tender_never_guesses_missing_fields() -> None:
    pages = [_page(1, "BIDDING DOCUMENT with almost no useful information")]
    client = _StubLLMClient(_ScoutLLMOutput())  # LLM found nothing

    tender = extract_tender(client, pages)

    assert tender.title is None
    assert tender.procuring_entity is None
    assert tender.category is None
    assert tender.district is None
    assert tender.estimated_cost_npr is None
    assert tender.deadline is None
    assert tender.eligibility_requirements == []
