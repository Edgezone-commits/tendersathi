"""Entry point for the daily GitHub Actions cron (Phase 6).

Runs the Matcher (re-score any tender still in `new` status against every
company) followed by the Notifier (email digest of unnotified matches).
Ingestion is deliberately left out of this cron: `ManualUploadSource` reads
from a local inbox a human must populate, and the automated scraper
(`tendersathi.ingestion.sources.BolpatraScraper`) isn't implemented yet --
see that class's docstring for why. Once an automated source exists, call
`run_ingestion` here first.
"""

from __future__ import annotations

import logging
import sys

from tendersathi.agents.matcher import run_matcher
from tendersathi.agents.notifier import get_email_client, run_notifier
from tendersathi.db.client import get_supabase_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run matcher + notifier against real Supabase/Gmail clients. Returns an exit code."""
    client = get_supabase_client()
    try:
        matcher_stats = run_matcher(client)
        logger.info("Matcher run finished: %s", matcher_stats)

        email_client = get_email_client()
        notifier_stats = run_notifier(client, email_client)
        logger.info("Notifier run finished: %s", notifier_stats)
    except Exception:
        logger.exception("Daily run failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
