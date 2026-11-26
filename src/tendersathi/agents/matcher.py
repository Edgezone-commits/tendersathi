"""Matcher agent: scores a tender against a company profile.

This is a coarse triage score meant to rank/filter tenders for a daily
digest, not a full eligibility check -- it only reasons from the structured
fields Scout and a company profile already capture (category vs. sector,
district, turnover vs. estimated cost). Fine-grained eligibility (licence
class, document-level qualification clauses) is the Eligibility agent's job
(Phase 4), which reads the actual bid document with page citations. Semantic
similarity between free-text profiles/tenders (pgvector embeddings, past
projects) is deferred past this phase: Groq, our default LLM provider, has
no embeddings endpoint, and a rules-only score keeps this agent simple and
fully explainable without a new dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from supabase import Client
from tendersathi.db import companies as companies_db
from tendersathi.db import matches as matches_db
from tendersathi.db import runs as runs_db
from tendersathi.db import tenders as tenders_db
from tendersathi.db.models import CompanyRow, TenderRow

# Category/sector fit matters most (a company with ample turnover still
# can't bid on a tender outside its line of work); district next (can it
# realistically deliver there); turnover last, since it's a coarse check,
# not the real multiplier-based affordability test the Eligibility agent
# runs against the bid document's actual qualification criteria.
CATEGORY_WEIGHT = 0.5
DISTRICT_WEIGHT = 0.3
TURNOVER_WEIGHT = 0.2

_Signal = tuple[float, str]  # (fit, 0.0-1.0) and a human-readable reasoning clause


@dataclass(frozen=True)
class MatchScore:
    """A single tender/company score, ready to hand to `matches_db.save_match`."""

    score: float
    reasoning: str


def score_tender_for_company(tender: TenderRow, company: CompanyRow) -> MatchScore:
    """Score how well `company` fits `tender`, from structured fields alone.

    Each signal is skipped (not scored as a mismatch) when either side's
    data is missing, so a tender/company with incomplete profiles isn't
    unfairly penalised; the final score is the weighted average of whichever
    signals could be computed. Returns a 0.0 score with an explanatory
    reasoning if none could be.
    """
    signals: list[tuple[float, _Signal]] = []

    category_signal = _score_category_fit(tender.category, company.sector)
    if category_signal is not None:
        signals.append((CATEGORY_WEIGHT, category_signal))

    district_signal = _score_district_fit(tender.district, company.districts)
    if district_signal is not None:
        signals.append((DISTRICT_WEIGHT, district_signal))

    turnover_signal = _score_turnover_fit(tender.estimated_cost, company.annual_turnover)
    if turnover_signal is not None:
        signals.append((TURNOVER_WEIGHT, turnover_signal))

    if not signals:
        return MatchScore(score=0.0, reasoning="Not enough data to score this match.")

    total_weight = sum(weight for weight, _ in signals)
    score = sum(weight * fit for weight, (fit, _) in signals) / total_weight
    reasoning = " ".join(clause for _, (_, clause) in signals)
    return MatchScore(score=round(score, 2), reasoning=reasoning)


def _score_category_fit(category: str | None, sector: str | None) -> _Signal | None:
    """Compare the tender's category to the company's sector by plain text.

    Exact match (case/whitespace-insensitive) scores 1.0; one string
    containing the other scores 0.5 (e.g. sector "construction" vs. category
    "Road Construction"); otherwise 0.0. This is a deliberately simple
    heuristic -- a free-text semantic comparison would need embeddings,
    which this phase defers (see module docstring).
    """
    if category is None or sector is None:
        return None

    category_norm = category.strip().lower()
    sector_norm = sector.strip().lower()
    if category_norm == sector_norm:
        return 1.0, f"Category '{category}' matches the company's sector ('{sector}')."
    if category_norm in sector_norm or sector_norm in category_norm:
        return 0.5, f"Category '{category}' partially overlaps the company's sector ('{sector}')."
    return 0.0, f"Category '{category}' does not match the company's sector ('{sector}')."


def _score_district_fit(district: str | None, districts: list[str]) -> _Signal | None:
    """Check whether the tender's district is one the company operates in.

    An empty `districts` list means the company stated no district
    preference, so it's treated as "works anywhere" and skipped rather than
    scored -- there is nothing to compare against.
    """
    if not districts or district is None:
        return None
    if district in districts:
        return 1.0, f"District '{district}' is one the company operates in."
    operates_in = ", ".join(districts)
    return 0.0, f"District '{district}' is not one the company operates in ({operates_in})."


def _score_turnover_fit(
    estimated_cost: float | None, annual_turnover: float | None
) -> _Signal | None:
    """Coarsely check whether the company's turnover covers the tender's estimated cost.

    Real Nepali public-procurement qualification criteria usually require a
    multiple of the contract cost (e.g. average turnover over several
    years), stated in the bid document itself -- that precise check is the
    Eligibility agent's job. This is a cheap triage signal only.
    """
    if estimated_cost is None or annual_turnover is None:
        return None
    if annual_turnover >= estimated_cost:
        return (
            1.0,
            f"Annual turnover (NPR {annual_turnover:,.0f}) covers the estimated cost "
            f"(NPR {estimated_cost:,.0f}).",
        )
    return (
        0.0,
        f"Annual turnover (NPR {annual_turnover:,.0f}) is below the estimated cost "
        f"(NPR {estimated_cost:,.0f}); check the bid document's actual qualification "
        "criteria before ruling this out.",
    )


@dataclass(frozen=True)
class MatcherStats:
    """Summary of one matcher run, stored on the `runs` row for later debugging."""

    tenders_scored: int
    companies: int
    matches_saved: int


def run_matcher(client: Client) -> MatcherStats:
    """Score every tender with status 'new' against every company profile.

    This is what the daily GitHub Actions cron (Phase 6) will eventually run
    right after Scout ingests new tenders -- same start/finish-run pattern as
    `tendersathi.ingestion.pipeline.run_ingestion`, so a bad digest can be
    traced back to a specific matcher run's stats or error.
    """
    run_id = runs_db.start_run(client, run_type="matching")
    try:
        tenders = tenders_db.list_tenders(client, status="new")
        companies = companies_db.list_companies(client)

        matches_saved = 0
        for tender in tenders:
            for company in companies:
                match = score_tender_for_company(tender, company)
                matches_db.save_match(client, tender.id, company.id, match.score, match.reasoning)
                matches_saved += 1

        stats = MatcherStats(
            tenders_scored=len(tenders),
            companies=len(companies),
            matches_saved=matches_saved,
        )
        runs_db.finish_run(client, run_id, status="success", stats=asdict(stats))
        return stats
    except Exception as error:
        runs_db.finish_run(client, run_id, status="failed", stats={}, error=str(error))
        raise
