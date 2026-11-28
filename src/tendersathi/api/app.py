"""FastAPI app: wires the HTTP routes to the Supabase client + compiled pipeline graph.

Both are built once in `lifespan`, not per-request -- the checkpointer in
particular holds a single Postgres connection for the process's whole life,
same one-client-per-process reasoning as every other factory in this
codebase (`get_supabase_client`, `get_llm_client`). Run locally with:

    uv run uvicorn tendersathi.api.app:app --reload

(deployed to Fly.io per `fly.toml`, Phase 8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tendersathi.api import companies, pipeline, tenders
from tendersathi.db.client import get_supabase_client
from tendersathi.llm import get_llm_client
from tendersathi.orchestration.checkpointer import get_checkpointer
from tendersathi.orchestration.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = get_supabase_client()
    llm_client = get_llm_client()
    with get_checkpointer() as checkpointer:
        app.state.db_client = client
        app.state.graph = build_graph(client, llm_client).compile(checkpointer=checkpointer)
        yield


app = FastAPI(title="TenderSathi", lifespan=lifespan)
app.include_router(companies.router)
app.include_router(tenders.router)
app.include_router(pipeline.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check that touches no dependency -- what Fly.io's health check hits."""
    return {"status": "ok"}
