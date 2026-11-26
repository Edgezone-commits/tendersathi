"""The tender pipeline graph: Scout -> Matcher -> Eligibility -> Drafter -> approval.

Each node is a thin wrapper around an existing agent/db call -- this module
only owns the wiring (state, edges, the human-approval pause), not any new
agent logic. `build_graph` takes the Supabase client and LLM client as
plain arguments (same pattern as `run_ingestion`/`run_matcher`) rather than
reading them from a global, so tests can pass in mocks without patching.

The `approval` node is deliberately its own node, after `drafter`: LangGraph
re-runs a node's code from the top every time it resumes from an
`interrupt()` inside that node, so the LLM call that builds the draft lives
in a separate, already-completed node -- only the cheap `interrupt()` call
re-runs on resume, not the drafting itself.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from supabase import Client
from tendersathi.agents.drafter import DraftOutput, run_drafter
from tendersathi.agents.eligibility import ChecklistItem, run_eligibility_check
from tendersathi.agents.matcher import MatchScore, score_tender_for_company
from tendersathi.agents.scout import extract_tender
from tendersathi.db import companies as companies_db
from tendersathi.db import matches as matches_db
from tendersathi.db import tenders as tenders_db
from tendersathi.db.models import CompanyRow, TenderRow
from tendersathi.ingestion.pdf_loader import PdfPage
from tendersathi.llm.base import LLMClient


class PipelineState(TypedDict, total=False):
    """One tender's progress through the pipeline.

    `tender_id`/`company_id` are the only required inputs; every other key
    is filled in by the node responsible for it and read by later nodes.
    """

    tender_id: str
    company_id: str

    pages: list[PdfPage]
    tender: TenderRow
    company: CompanyRow
    match: MatchScore
    checklist: list[ChecklistItem]
    draft: DraftOutput
    approved: bool


def build_graph(client: Client, llm_client: LLMClient) -> StateGraph:
    """Build the pipeline graph, uncompiled so callers choose their own checkpointer."""

    def scout_node(state: PipelineState) -> dict:
        page_rows = tenders_db.get_tender_pages(client, state["tender_id"])
        pages = [
            PdfPage(page_number=row.page_number, text=row.text, used_ocr=row.used_ocr)
            for row in page_rows
        ]
        extracted = extract_tender(llm_client, pages)
        tenders_db.update_tender_extraction(client, state["tender_id"], extracted)
        tender = tenders_db.get_tender(client, state["tender_id"])
        return {"pages": pages, "tender": tender}

    def matcher_node(state: PipelineState) -> dict:
        company = companies_db.get_company(client, state["company_id"])
        match = score_tender_for_company(state["tender"], company)
        matches_db.save_match(
            client, state["tender_id"], state["company_id"], match.score, match.reasoning
        )
        return {"company": company, "match": match}

    def eligibility_node(state: PipelineState) -> dict:
        checklist = run_eligibility_check(llm_client, state["pages"], state["company"])
        return {"checklist": checklist}

    def drafter_node(state: PipelineState) -> dict:
        draft = run_drafter(llm_client, state["tender"], state["company"], state["checklist"])
        return {"draft": draft}

    def approval_node(state: PipelineState) -> dict:
        decision = interrupt(
            {
                "tender_id": state["tender_id"],
                "company_id": state["company_id"],
                "draft": state["draft"],
                "question": "Approve this draft for the bidder? ('approve' or 'reject')",
            }
        )
        return {"approved": decision == "approve"}

    builder = StateGraph(PipelineState)
    builder.add_node("scout", scout_node)
    builder.add_node("matcher", matcher_node)
    builder.add_node("eligibility", eligibility_node)
    builder.add_node("drafter", drafter_node)
    builder.add_node("approval", approval_node)
    builder.add_edge(START, "scout")
    builder.add_edge("scout", "matcher")
    builder.add_edge("matcher", "eligibility")
    builder.add_edge("eligibility", "drafter")
    builder.add_edge("drafter", "approval")
    builder.add_edge("approval", END)
    return builder


def start_pipeline(
    graph: CompiledStateGraph, thread_id: str, tender_id: str, company_id: str
) -> dict:
    """Run the pipeline up to the human-approval interrupt.

    The returned dict holds an `"__interrupt__"` key with the approval
    payload once the graph reaches `approval`.
    """
    run_config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke({"tender_id": tender_id, "company_id": company_id}, config=run_config)


def resume_pipeline(graph: CompiledStateGraph, thread_id: str, approved: bool) -> dict:
    """Resume a pipeline paused at the approval interrupt with a human's decision."""
    run_config = {"configurable": {"thread_id": thread_id}}
    decision = "approve" if approved else "reject"
    return graph.invoke(Command(resume=decision), config=run_config)
