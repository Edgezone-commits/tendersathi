"""CLI entry point to ingest every PDF in a directory into Supabase.

Usage:
    uv run python scripts/ingest_manual.py [inbox_dir]

Defaults to data/samples, so this is the quickest way to check the Phase 1
pipeline against a real Supabase project.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tendersathi.db.client import get_supabase_client
from tendersathi.ingestion.pipeline import run_ingestion
from tendersathi.ingestion.sources import ManualUploadSource


def main() -> None:
    """Ingest every PDF in the given (or default) inbox directory and print the stats."""
    inbox_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/samples")
    client = get_supabase_client()
    source = ManualUploadSource(inbox_dir)
    stats = run_ingestion(client, source)
    print(f"found={stats.found} new={stats.new} duplicates={stats.duplicates}")


if __name__ == "__main__":
    main()
