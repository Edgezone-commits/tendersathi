"""Postgres-backed LangGraph checkpointer -- the only place that opens this connection.

Checkpointing is what lets the pipeline survive the human-approval
interrupt across separate runs: the daily GitHub Actions cron (Phase 6)
starts a fresh process every time, so an in-memory checkpointer would lose
a tender's "paused for approval" state the moment that process exits.
Persisting checkpoints to the same Supabase Postgres instance everything
else already uses avoids standing up a second storage system.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from tendersathi import config


@contextmanager
def get_checkpointer() -> Iterator[PostgresSaver]:
    """Open a `PostgresSaver` against `DATABASE_URL`, creating its tables if needed.

    `.setup()` runs PostgresSaver's own migrations; it tracks its schema
    version in the database and is safe to call on every connect, not just
    the first one.
    """
    if not config.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL must be set in .env to checkpoint the LangGraph pipeline "
            "(Supabase dashboard -> Project Settings -> Database -> Connection string)."
        )
    with PostgresSaver.from_conn_string(config.DATABASE_URL) as checkpointer:
        checkpointer.setup()
        yield checkpointer
