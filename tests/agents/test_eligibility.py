"""Tests for the Eligibility agent: LLM extraction wiring and the deterministic
'met / missing / unclear' checklist evaluation.

The LLM is stubbed out, same as tests/agents/test_scout.py -- these tests
check the agent's own logic (which pages it sends, how it turns the LLM's
per-requirement extraction into a checklist verdict), not Groq's behaviour.
"""

from __future__ import annotations

from tendersathi.agents.eligibility import (
    MAX_COMPLETION_TOKENS,
    ChecklistItem,
    _EligibilityLLMOutput,
    _RequirementExtraction,
    run_eligibility_check,
)
from tendersathi.db.models import CompanyRow
from tendersathi.ingestion.pdf_loader import PdfPage


def _page(number: int, text: str) -> PdfPage:
    return PdfPage(page_number=number, text=text, used_ocr=False)


def _company(
    annual_turnover: float | None = None, licence_class: str | None = None
) -> CompanyRow:
    return CompanyRow(
        id="company-1",
        name="Himalayan Builders Pvt. Ltd.",
        sector="construction",
        annual_turnover=annual_turnover,
        licence_class=licence_class,
        districts=[],
    )


class _StubLLMClient:
    """Records the prompt/model it was called with and returns a fixed result."""

    def __init__(self, result: _EligibilityLLMOutput) -> None:
        self.result = result
        self.calls: list[tuple[str, type, int, int | None]] = []

    def generate(self, prompt, response_model, max_retries=2, max_tokens=None):
        self.calls.append((prompt, response_model, max_retries, max_tokens))
        return self.result


def test_run_eligibility_check_returns_empty_list_without_calling_llm_when_no_pages() -> None:
    client = _StubLLMClient(_EligibilityLLMOutput())

    checklist = run_eligibility_check(client, [], _company())

    assert checklist == []
    assert client.calls == []


def test_run_eligibility_check_passes_candidate_pages_and_token_budget_to_llm() -> None:
    pages = [_page(1, "BIDDING DOCUMENT for Procurement of Widgets")]
    client = _StubLLMClient(_EligibilityLLMOutput())

    run_eligibility_check(client, pages, _company())

    assert client.calls[0][1] is _EligibilityLLMOutput
    assert client.calls[0][3] == MAX_COMPLETION_TOKENS


def test_run_eligibility_check_marks_turnover_requirement_met() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Minimum average annual turnover of NPR 1,000,000",
        page_number=47,
        requirement_type="turnover",
        minimum_turnover_npr=1_000_000,
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company(annual_turnover=5_000_000))

    assert checklist == [
        ChecklistItem(
            requirement="Minimum average annual turnover of NPR 1,000,000",
            page_number=47,
            status="met",
            reasoning=(
                "Company's annual turnover (NPR 5,000,000) meets the minimum "
                "(NPR 1,000,000)."
            ),
        )
    ]


def test_run_eligibility_check_marks_turnover_requirement_missing() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Minimum average annual turnover of NPR 5,000,000",
        page_number=47,
        requirement_type="turnover",
        minimum_turnover_npr=5_000_000,
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company(annual_turnover=1_000_000))

    assert checklist[0].status == "missing"
    assert "below the minimum" in checklist[0].reasoning


def test_run_eligibility_check_marks_turnover_requirement_unclear_when_company_data_missing() -> (
    None
):
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Minimum average annual turnover of NPR 5,000,000",
        page_number=47,
        requirement_type="turnover",
        minimum_turnover_npr=5_000_000,
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company(annual_turnover=None))

    assert checklist[0].status == "unclear"


def test_run_eligibility_check_marks_licence_class_requirement_met() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Must hold Class 'A' contractor licence",
        page_number=48,
        requirement_type="licence_class",
        minimum_licence_class="A",
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company(licence_class="A"))

    assert checklist[0].status == "met"


def test_run_eligibility_check_marks_licence_class_requirement_missing_on_mismatch() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Must hold Class 'A' contractor licence",
        page_number=48,
        requirement_type="licence_class",
        minimum_licence_class="A",
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company(licence_class="C"))

    assert checklist[0].status == "missing"
    assert "verify manually" in checklist[0].reasoning


def test_run_eligibility_check_marks_licence_class_requirement_unclear_when_data_missing() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Must hold Class 'A' contractor licence",
        page_number=48,
        requirement_type="licence_class",
        minimum_licence_class="A",
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company(licence_class=None))

    assert checklist[0].status == "unclear"


def test_run_eligibility_check_marks_other_requirements_unclear() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = _RequirementExtraction(
        requirement="Must be registered with the Department of Industry",
        page_number=49,
        requirement_type="other",
    )
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=[extraction]))

    checklist = run_eligibility_check(client, pages, _company())

    assert checklist[0].status == "unclear"
    assert "verify manually" in checklist[0].reasoning


def test_run_eligibility_check_preserves_citation_for_every_item() -> None:
    pages = [_page(1, "Section III. Evaluation and Qualification Criteria")]
    extraction = [
        _RequirementExtraction(
            requirement="Minimum turnover NPR 1,000,000",
            page_number=47,
            requirement_type="turnover",
            minimum_turnover_npr=1_000_000,
        ),
        _RequirementExtraction(
            requirement="Class 'A' licence required",
            page_number=48,
            requirement_type="licence_class",
            minimum_licence_class="A",
        ),
    ]
    client = _StubLLMClient(_EligibilityLLMOutput(requirements=extraction))

    checklist = run_eligibility_check(client, pages, _company(annual_turnover=2_000_000))

    assert [item.page_number for item in checklist] == [47, 48]
