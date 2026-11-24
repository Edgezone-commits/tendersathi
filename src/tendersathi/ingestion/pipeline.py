"""Runs one ingestion pass: fetch from a source, store anything new, record a run.

This is what the daily GitHub Actions cron (Phase 6) will eventually call.
It's the single place that ties a `TenderSource` to the db module, so that
dedup is applied consistently no matter which source is in use.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from supabase import Client
from tendersathi.db import runs as runs_db
from tendersathi.db import tenders as tenders_db
from tendersathi.ingestion.sources import TenderSource


@dataclass(frozen=True)
class IngestionStats:
    """Summary of one ingestion run, stored on the `runs` row for later debugging."""

    found: int
    new: int
    duplicates: int


def run_ingestion(client: Client, source: TenderSource) -> IngestionStats:
    """Fetch new tenders from `source`, store any not already in the db, and log a run."""
    run_id = runs_db.start_run(client, run_type="ingestion")
    try:
        uploads = source.fetch_new()
        new_count = 0
        duplicate_count = 0
        for upload in uploads:
            if tenders_db.get_tender_by_fingerprint(client, upload.fingerprint) is not None:
                duplicate_count += 1
                continue
            tenders_db.save_raw_tender(client, upload)
            new_count += 1

        stats = IngestionStats(found=len(uploads), new=new_count, duplicates=duplicate_count)
        runs_db.finish_run(client, run_id, status="success", stats=asdict(stats))
        return stats
    except Exception as error:
        runs_db.finish_run(client, run_id, status="failed", stats={}, error=str(error))
        raise
