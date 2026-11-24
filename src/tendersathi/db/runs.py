"""Read/write access to the `runs` table — one row per ingestion/eval run.

Keeping a row per run is what lets us debug a bad daily digest later: was a
run slow, did it fail partway through, how many tenders did it find.
"""

from __future__ import annotations

from datetime import UTC, datetime

from supabase import Client
from tendersathi.db.models import RunRow, parse_timestamp


def start_run(client: Client, run_type: str) -> str:
    """Create a run row in 'running' status and return its id."""
    payload = {"run_type": run_type, "status": "running"}
    response = client.table("runs").insert(payload).execute()
    return response.data[0]["id"]


def finish_run(
    client: Client,
    run_id: str,
    status: str,
    stats: dict,
    error: str | None = None,
) -> None:
    """Mark a run as finished, recording its stats (and error, if it failed)."""
    payload = {
        "status": status,
        "stats": stats,
        "error": error,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    client.table("runs").update(payload).eq("id", run_id).execute()


def get_run(client: Client, run_id: str) -> RunRow | None:
    """Look up a single run by id."""
    response = client.table("runs").select("*").eq("id", run_id).limit(1).execute()
    rows = response.data
    return _run_from_row(rows[0]) if rows else None


def _run_from_row(row: dict) -> RunRow:
    return RunRow(
        id=row["id"],
        run_type=row["run_type"],
        status=row["status"],
        stats=row.get("stats") or {},
        error=row.get("error"),
        started_at=parse_timestamp(row["started_at"]),
        finished_at=parse_timestamp(row.get("finished_at")),
    )
