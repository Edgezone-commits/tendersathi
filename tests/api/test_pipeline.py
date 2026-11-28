"""Tests for the /pipeline routes, with start_pipeline/resume_pipeline mocked out.

The graph itself is already covered end-to-end in
`tests/orchestration/test_graph.py`; these tests only check that the route
builds a thread id, calls through with the right arguments, and translates
a graph result into the HTTP response shape.
"""

from __future__ import annotations

from unittest.mock import patch

from langgraph.types import Interrupt

from tendersathi.agents.drafter import DraftOutput


def _draft() -> DraftOutput:
    return DraftOutput(
        document_checklist=["Attach turnover certificate"],
        cover_letter="Dear Sir/Madam, ...",
    )


def test_create_pipeline_run_returns_pending_approval_when_interrupted(api_client, mock_graph):
    interrupt_payload = {
        "tender_id": "t1",
        "company_id": "c1",
        "draft": _draft(),
        "question": "Approve this draft for the bidder? ('approve' or 'reject')",
    }
    with patch("tendersathi.api.pipeline.start_pipeline") as mock_start:
        mock_start.return_value = {"__interrupt__": (Interrupt(value=interrupt_payload),)}
        response = api_client.post("/pipeline/runs", json={"tender_id": "t1", "company_id": "c1"})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["document_checklist"] == ["Attach turnover certificate"]
    assert body["cover_letter"] == "Dear Sir/Madam, ..."
    assert body["approved"] is None

    mock_start.assert_called_once()
    call_args = mock_start.call_args.args
    assert call_args[0] is mock_graph
    assert call_args[2:] == ("t1", "c1")
    assert body["thread_id"] == call_args[1]


def test_submit_pipeline_decision_returns_completed_when_graph_finishes(api_client, mock_graph):
    with patch("tendersathi.api.pipeline.resume_pipeline") as mock_resume:
        mock_resume.return_value = {"approved": True}
        response = api_client.post("/pipeline/runs/thread-1/decision", json={"approved": True})

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "thread-1"
    assert body["status"] == "completed"
    assert body["approved"] is True
    mock_resume.assert_called_once_with(mock_graph, "thread-1", True)
