"""Tests for the Drafter agent: the deterministic document checklist and the
cover-letter LLM call, with the LLM stubbed out (same style as test_scout.py).
"""

from __future__ import annotations

from datetime import UTC, datetime

from tendersathi.agents.drafter import (
    MAX_COMPLETION_TOKENS,
    DraftOutput,
    _CoverLetterOutput,
    build_document_checklist,
    run_drafter,
)
from tendersathi.agents.eligibility import ChecklistItem
from tendersathi.db.models import CompanyRow, TenderRow


def _tender(title: str | None = "Procurement of Widgets") -> TenderRow:
    now = datetime.now(UTC)
    return TenderRow(
        id="tender-1",
        source="manual_upload",
        source_url=None,
        external_reference=None,
        title=title,
        procuring_entity="Ministry of Widgets",
        category="Goods",
        district="Kathmandu",
        estimated_cost=4_200_000.0,
        submission_deadline=None,
        fingerprint="fp-1",
        status="new",
        created_at=now,
        updated_at=now,
    )


def _company() -> CompanyRow:
    return CompanyRow(
        id="company-1",
        name="Himalayan Builders Pvt. Ltd.",
        sector="construction",
        annual_turnover=5_000_000,
        licence_class="A",
        districts=["Kathmandu"],
    )


class _StubLLMClient:
    """Records the prompt/model it was called with and returns a fixed result."""

    def __init__(self, result: _CoverLetterOutput) -> None:
        self.result = result
        self.calls: list[tuple[str, type, int, int | None]] = []

    def generate(self, prompt, response_model, max_retries=2, max_tokens=None):
        self.calls.append((prompt, response_model, max_retries, max_tokens))
        return self.result


def test_build_document_checklist_keeps_status_and_page_citation() -> None:
    checklist = [
        ChecklistItem(
            requirement="Minimum turnover NPR 1,000,000",
            page_number=47,
            status="met",
            reasoning="...",
        ),
        ChecklistItem(
            requirement="Class 'A' licence required",
            page_number=48,
            status="missing",
            reasoning="...",
        ),
        ChecklistItem(
            requirement="Registered with DoI",
            page_number=49,
            status="unclear",
            reasoning="...",
        ),
    ]

    lines = build_document_checklist(checklist)

    assert lines == [
        "[MET] Minimum turnover NPR 1,000,000 (page 47) — Attach evidence.",
        "[MISSING] Class 'A' licence required (page 48) — Address this gap before "
        "submitting, or do not bid.",
        "[UNCLEAR] Registered with DoI (page 49) — Verify manually and gather "
        "supporting documents.",
    ]


def test_build_document_checklist_handles_empty_checklist() -> None:
    assert build_document_checklist([]) == []


def test_run_drafter_calls_llm_with_token_budget_and_returns_cover_letter() -> None:
    client = _StubLLMClient(_CoverLetterOutput(cover_letter="Dear Sir/Madam, ..."))
    checklist = [
        ChecklistItem(
            requirement="Minimum turnover NPR 1,000,000",
            page_number=47,
            status="met",
            reasoning="...",
        )
    ]

    draft = run_drafter(client, _tender(), _company(), checklist)

    assert draft == DraftOutput(
        document_checklist=build_document_checklist(checklist),
        cover_letter="Dear Sir/Madam, ...",
    )
    assert client.calls[0][1] is _CoverLetterOutput
    assert client.calls[0][3] == MAX_COMPLETION_TOKENS


def test_run_drafter_prompt_includes_tender_company_and_checklist_status() -> None:
    client = _StubLLMClient(_CoverLetterOutput(cover_letter="..."))
    checklist = [
        ChecklistItem(
            requirement="Minimum turnover NPR 1,000,000",
            page_number=47,
            status="missing",
            reasoning="...",
        )
    ]

    run_drafter(client, _tender(), _company(), checklist)

    prompt = client.calls[0][0]
    assert "Procurement of Widgets" in prompt
    assert "Ministry of Widgets" in prompt
    assert "Himalayan Builders Pvt. Ltd." in prompt
    assert "[MISSING] Minimum turnover NPR 1,000,000" in prompt
    assert "must NOT claim" in prompt


def test_run_drafter_prompt_handles_empty_checklist() -> None:
    client = _StubLLMClient(_CoverLetterOutput(cover_letter="..."))

    run_drafter(client, _tender(), _company(), [])

    prompt = client.calls[0][0]
    assert "no eligibility requirements were extracted" in prompt
