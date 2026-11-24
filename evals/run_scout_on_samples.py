"""Run the Scout agent on every sample PDF in `data/samples/` and report results.

This is a manual accuracy-check tool, not an automated eval: it calls the
real configured LLM (no mocks), prints a table of what the Scout agent
extracted from each sample tender, and saves the full output to
`evals/scout_results.json` so a human can compare it against the source
PDFs by hand.

Usage:
    uv run python evals/run_scout_on_samples.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import groq

from tendersathi.agents.scout import Tender, extract_tender
from tendersathi.ingestion.pdf_loader import PdfPage, load_pdf_pages
from tendersathi.llm import get_llm_client
from tendersathi.llm.base import LLMClient

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
RESULTS_PATH = Path(__file__).resolve().parent / "scout_results.json"

# Groq's free tier rate-limits by tokens PER MINUTE (as low as 8000 on some
# models/accounts), shared across every call in that window -- not just a
# per-request cap. Running several large extractions back-to-back can blow
# through it even though each individual call fits, so this retries on 429s
# with the backoff Groq itself suggests.
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_FALLBACK_WAIT_SECONDS = 20.0

COLUMNS = [
    ("file", 28),
    ("title", 28),
    ("procuring_entity", 24),
    ("category", 16),
    ("district", 12),
    ("estimated_cost_npr", 14),
    ("deadline", 12),
    ("eligibility_requirements", 10),
    ("source_pages", 14),
]


def _truncate(value: str, width: int) -> str:
    return value if len(value) <= width else value[: width - 1] + "…"


def _print_table(rows: list[dict]) -> None:
    header = " | ".join(name.ljust(width) for name, width in COLUMNS)
    print(header)
    print("-" * len(header))
    for row in rows:
        cells = []
        for name, width in COLUMNS:
            value = row[name]
            if name == "eligibility_requirements":
                value = str(len(value))
            elif name == "source_pages":
                value = f"{value[0]}-{value[-1]}" if value else ""
            else:
                value = "" if value is None else str(value)
            cells.append(_truncate(value, width).ljust(width))
        print(" | ".join(cells))


def _extract_with_retry(llm_client: LLMClient, pages: list[PdfPage]) -> Tender:
    for attempt in range(1, RATE_LIMIT_MAX_ATTEMPTS + 1):
        try:
            return extract_tender(llm_client, pages)
        except groq.RateLimitError as error:
            if attempt == RATE_LIMIT_MAX_ATTEMPTS:
                raise
            match = re.search(r"try again in ([\d.]+)s", str(error))
            wait_seconds = float(match.group(1)) + 1 if match else RATE_LIMIT_FALLBACK_WAIT_SECONDS
            print(f"  Rate limited; waiting {wait_seconds:.1f}s before retrying ...")
            time.sleep(wait_seconds)
    raise AssertionError("unreachable")


def main() -> None:
    llm_client = get_llm_client()
    pdf_paths = sorted(SAMPLES_DIR.glob("*.pdf"))
    if not pdf_paths:
        print(f"No sample PDFs found in {SAMPLES_DIR}")
        return

    rows: list[dict] = []
    for path in pdf_paths:
        print(f"Extracting {path.name} ...")
        pages = load_pdf_pages(path)
        tender = _extract_with_retry(llm_client, pages)
        rows.append({"file": path.name, **tender.model_dump(mode="json")})

    print()
    _print_table(rows)

    RESULTS_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
