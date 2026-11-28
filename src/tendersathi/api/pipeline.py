"""HTTP routes to start and resume a tender's pipeline run (Phase 5's LangGraph graph).

One thread per pipeline run, identified by a server-generated `thread_id`
that the caller must pass back on `/decision` -- it's what lets the
Postgres checkpointer find the exact paused run to resume, since several
runs can be paused for approval at once.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from langgraph.graph.state import CompiledStateGraph

from tendersathi.api.deps import get_graph
from tendersathi.api.schemas import PipelineDecision, PipelineRunCreate, PipelineRunOut
from tendersathi.orchestration.graph import resume_pipeline, start_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/runs", response_model=PipelineRunOut, status_code=201)
def create_pipeline_run(
    body: PipelineRunCreate, graph: CompiledStateGraph = Depends(get_graph)
) -> PipelineRunOut:
    thread_id = str(uuid4())
    result = start_pipeline(graph, thread_id, body.tender_id, body.company_id)
    return _to_response(thread_id, result)


@router.post("/runs/{thread_id}/decision", response_model=PipelineRunOut)
def submit_pipeline_decision(
    thread_id: str, body: PipelineDecision, graph: CompiledStateGraph = Depends(get_graph)
) -> PipelineRunOut:
    result = resume_pipeline(graph, thread_id, body.approved)
    return _to_response(thread_id, result)


def _to_response(thread_id: str, result: dict) -> PipelineRunOut:
    """Turn one `graph.invoke()` result into the run's current HTTP shape.

    A still-paused run carries an `"__interrupt__"` entry (see
    `approval_node` in `tendersathi.orchestration.graph`); its absence means
    the graph ran all the way to `END` with a human decision already
    applied.
    """
    interrupts = result.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        draft = payload["draft"]
        return PipelineRunOut(
            thread_id=thread_id,
            status="pending_approval",
            question=payload["question"],
            document_checklist=draft.document_checklist,
            cover_letter=draft.cover_letter,
        )
    return PipelineRunOut(
        thread_id=thread_id,
        status="completed",
        approved=result.get("approved"),
    )
