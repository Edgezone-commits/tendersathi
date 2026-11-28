"""FastAPI dependencies for the Supabase client and compiled pipeline graph.

Both are built once, in `tendersathi.api.app`'s lifespan, and stashed on
`app.state` -- not rebuilt per request, since the graph in particular is
tied to a single checkpointer connection that should live for the process's
whole life. Routes depend on these functions rather than importing
`app.state` directly, which is also what lets tests override them with
`app.dependency_overrides` instead of running the real lifespan.
"""

from __future__ import annotations

from fastapi import Request
from langgraph.graph.state import CompiledStateGraph

from supabase import Client


def get_db_client(request: Request) -> Client:
    return request.app.state.db_client


def get_graph(request: Request) -> CompiledStateGraph:
    return request.app.state.graph
