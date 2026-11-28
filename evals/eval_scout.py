"""Scored offline eval for the Scout agent against `datasets/scout_ground_truth.json`.

Unlike `run_scout_on_samples.py` (a manual print-and-inspect tool), this
calls the real configured LLM and grades each extraction against a small
hand-verified ground truth (every keyword below was confirmed by reading
the sample PDFs' raw text directly, not guessed), so it can pass/fail in
one number instead of requiring a human to eyeball the output. It still
makes real network calls, so it's not run by `pytest`/CI -- run it by hand
after changing Scout's prompt or model.

Each of the four scored fields (title, procuring_entity, district,
category) is graded 1.0 if any of its expected keywords appears
case-insensitively in Scout's output, else 0.0; the reported accuracy is
the mean of all field scores across every sample. `PASS_THRESHOLD` is
deliberately loose -- this eval exists to catch a prompt/model regression
that tanks accuracy, not to demand perfection from a free-tier model.

Usage:
    uv run python evals/eval_scout.py
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
DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "scout_ground_truth.json"
REPORT_PATH = Path(__file__).resolve().parent / "scout_eval_report.json"

PASS_THRESHOLD = 0.75

# See evals/run_scout_on_samples.py for why this retry exists: Groq's free
# tier rate-limits by tokens per minute, shared across every call.
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_FALLBACK_WAIT_SECONDS = 20.0

SCORED_FIELDS = [
    ("title", "title_keywords"),
    ("procuring_entity", "procuring_entity_keywords"),
    ("district", "district_keywords"),
    ("category", "category_keywords"),
]


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


def _field_score(predicted: str | None, expected_keywords: list[str]) -> float:
    """1.0 if any expected keyword appears in the predicted value, else 0.0."""
    if predicted is None:
        return 0.0
    predicted_lower = predicted.lower()
    return 1.0 if any(keyword in predicted_lower for keyword in expected_keywords) else 0.0


def main() -> int:
    llm_client = get_llm_client()
    cases = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    results = []
    for case in cases:
        path = SAMPLES_DIR / case["file"]
        print(f"Extracting {path.name} ...")
        pages = load_pdf_pages(path)
        tender = _extract_with_retry(llm_client, pages)

        field_scores = {
            field_name: _field_score(getattr(tender, field_name), case[keywords_key])
            for field_name, keywords_key in SCORED_FIELDS
        }
        results.append(
            {
                "file": case["file"],
                "predicted": tender.model_dump(mode="json"),
                "field_scores": field_scores,
                "case_accuracy": sum(field_scores.values()) / len(field_scores),
            }
        )

    all_field_scores = [score for result in results for score in result["field_scores"].values()]
    overall_accuracy = sum(all_field_scores) / len(all_field_scores)

    print()
    for result in results:
        print(f"{result['file']}: {result['case_accuracy']:.2f} {result['field_scores']}")
    print(f"\nOverall accuracy: {overall_accuracy:.2f} (pass threshold: {PASS_THRESHOLD})")

    REPORT_PATH.write_text(
        json.dumps({"overall_accuracy": overall_accuracy, "results": results}, indent=2),
        encoding="utf-8",
    )
    print(f"Full report saved to {REPORT_PATH}")

    return 0 if overall_accuracy >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
