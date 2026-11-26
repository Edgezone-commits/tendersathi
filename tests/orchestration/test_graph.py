"""Tests for the pipeline graph: wiring, the human-approval interrupt/resume,
and that db writes + LLM calls happen where expected.

Uses `MemorySaver` instead of the real Postgres checkpointer (tests never
make a real network call) and stubs the LLM client, same style as the
individual agent tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from tendersathi.agents.drafter import _CoverLetterOutput
from tendersathi.agents.eligibility import _EligibilityLLMOutput, _RequirementExtraction
from tendersathi.agents.scout import _ScoutLLMOutput
from tendersathi.db.models import CompanyRow, TenderPageRow, TenderRow
from tendersathi.orchestration.graph import build_graph, resume_pipeline, start_pipeline


class _StubLLMClient:
    """Dispatches on `response_model` so one stub covers Scout, Eligibility and Drafter."""

    def __init__(self) -> None:
        self.calls: list[type] = []

    def generate(self, prompt, response_model, max_retries=2, max_tokens=None):
        self.calls.append(response_model)
        if response_model is _ScoutLLMOutput:
            return _ScoutLLMOutput(
                title="Procurement of Widgets",
                procuring_entity="Ministry of Widgets",
                category="Goods",
                district="Kathmandu",
                estimated_cost_npr=1_000_000,
            )
        if response_model is _EligibilityLLMOutput:
            return _EligibilityLLMOutput(
                requirements=[
                    _RequirementExtraction(
                        requirement="Minimum turnover NPR 1,000,000",
                        page_number=1,
                        requirement_type="turnover",
                        minimum_turnover_npr=1_000_000,
                    )
                ]
            )
        if response_model is _CoverLetterOutput:
            return _CoverLetterOutput(cover_letter="Dear Sir/Madam, ...")
        raise AssertionError(f"unexpected response_model: {response_model}")


def _tender_row() -> TenderRow:
    now = datetime.now(UTC)
    return TenderRow(
        id="tender-1",
        source="manual_upload",
        source_url=None,
        external_reference=None,
        title="Procurement of Widgets",
        procuring_entity="Ministry of Widgets",
        category="Goods",
        district="Kathmandu",
        estimated_cost=1_000_000,
        submission_deadline=None,
        fingerprint="fp-1",
        status="new",
        created_at=now,
        updated_at=now,
    )


def _company_row() -> CompanyRow:
    return CompanyRow(
        id="company-1",
        name="Himalayan Builders Pvt. Ltd.",
        sector="construction",
        annual_turnover=5_000_000,
        licence_class="A",
        districts=["Kathmandu"],
    )


def _build_mocked_graph(llm_client: _StubLLMClient):
    client = MagicMock()
    tenders_patch = patch("tendersathi.orchestration.graph.tenders_db")
    companies_patch = patch("tendersathi.orchestration.graph.companies_db")
    matches_patch = patch("tendersathi.orchestration.graph.matches_db")
    mock_tenders_db = tenders_patch.start()
    mock_companies_db = companies_patch.start()
    mock_matches_db = matches_patch.start()

    mock_tenders_db.get_tender_pages.return_value = [
        TenderPageRow(
            id="page-1", tender_id="tender-1", page_number=1, text="cover page", used_ocr=False
        )
    ]
    mock_tenders_db.get_tender.return_value = _tender_row()
    mock_companies_db.get_company.return_value = _company_row()

    builder = build_graph(client, llm_client)
    graph = builder.compile(checkpointer=MemorySaver())

    patches = (tenders_patch, companies_patch, matches_patch)
    mocks = (mock_tenders_db, mock_companies_db, mock_matches_db)
    return graph, mocks, patches


def test_pipeline_pauses_for_approval_then_resumes_with_approval():
    llm_client = _StubLLMClient()
    graph, (mock_tenders_db, mock_companies_db, mock_matches_db), patches = _build_mocked_graph(
        llm_client
    )
    try:
        paused = start_pipeline(graph, "thread-1", "tender-1", "company-1")

        assert "__interrupt__" in paused
        assert "approved" not in paused
        mock_tenders_db.update_tender_extraction.assert_called_once()
        mock_matches_db.save_match.assert_called_once()
        assert len(llm_client.calls) == 3  # scout, eligibility, drafter

        resumed = resume_pipeline(graph, "thread-1", approved=True)

        assert resumed["approved"] is True
        assert resumed["draft"].cover_letter == "Dear Sir/Madam, ..."
        assert len(llm_client.calls) == 3  # drafter's LLM call is not re-run on resume
    finally:
        for p in patches:
            p.stop()


def test_pipeline_resume_with_rejection_sets_approved_false():
    llm_client = _StubLLMClient()
    graph, _mocks, patches = _build_mocked_graph(llm_client)
    try:
        start_pipeline(graph, "thread-2", "tender-1", "company-1")

        resumed = resume_pipeline(graph, "thread-2", approved=False)

        assert resumed["approved"] is False
    finally:
        for p in patches:
            p.stop()
