"""Notifier agent: sends a Telegram digest of newly matched tenders.

Unlike the other four agents, this one makes no LLM call -- it only
formats already-computed match scores (Phase 3) into a message and posts
it via Telegram's Bot API, so it talks to `httpx` directly rather than
going through `tendersathi.llm` (that abstraction exists to swap LLM
providers, not every external service). Each digest marks every match it
sends with `notified_at`, so a tender a company already saw in a previous
run doesn't reappear in today's digest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx

from supabase import Client
from tendersathi import config
from tendersathi.db import companies as companies_db
from tendersathi.db import matches as matches_db
from tendersathi.db import runs as runs_db
from tendersathi.db import tenders as tenders_db
from tendersathi.db.models import MatchRow

TELEGRAM_API_BASE = "https://api.telegram.org"

# Matches below this score are too weak to bother a company with. Scores are
# already normalised 0.0-1.0 by the Matcher (Phase 3), so one fixed cutoff
# applies regardless of company.
MIN_SCORE_FOR_DIGEST = 0.5


class TelegramClient:
    """Thin wrapper over Telegram's Bot API `sendMessage` call."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> None:
        """Post `text` to the configured chat, raising if Telegram rejects it."""
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        response = httpx.post(
            url,
            json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10.0,
        )
        response.raise_for_status()


def get_telegram_client() -> TelegramClient:
    """Build a TelegramClient from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in the environment."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env to send notifications."
        )
    return TelegramClient(token, chat_id)


def format_digest(matches: list[MatchRow], client: Client) -> str:
    """Render matches into one Telegram message, grouped by company.

    Looks up each match's tender/company row individually rather than
    joining in SQL -- a digest is at most a few dozen rows, so the extra
    round-trips are cheap and this keeps every `tendersathi.db` module free
    of hand-written joins.
    """
    lines = ["*TenderSathi daily digest*", ""]

    by_company: dict[str, list[MatchRow]] = {}
    for match in matches:
        by_company.setdefault(match.company_id, []).append(match)

    for company_id, company_matches in by_company.items():
        company = companies_db.get_company(client, company_id)
        company_name = company.name if company else "Unknown company"
        lines.append(f"*{company_name}*")
        for match in sorted(company_matches, key=lambda m: m.score, reverse=True):
            tender = tenders_db.get_tender(client, match.tender_id)
            title = tender.title if tender and tender.title else "Untitled tender"
            deadline = (
                tender.submission_deadline.date().isoformat()
                if tender and tender.submission_deadline
                else "unknown deadline"
            )
            lines.append(f"- {title} (score {match.score:.2f}, deadline {deadline})")
        lines.append("")

    return "\n".join(lines).strip()


@dataclass(frozen=True)
class NotifierStats:
    """Summary of one notifier run, stored on the `runs` row for later debugging."""

    matches_notified: int


def run_notifier(client: Client, telegram_client: TelegramClient) -> NotifierStats:
    """Send a digest of every unnotified match at or above `MIN_SCORE_FOR_DIGEST`.

    Same start/finish-run pattern as `run_ingestion`/`run_matcher`, so a
    failed Telegram send shows up in the `runs` table instead of silently
    vanishing in a GitHub Actions log. Sends nothing (and records a
    zero-match run) when there's nothing new to report, rather than
    spamming the chat with an empty digest every day.
    """
    run_id = runs_db.start_run(client, run_type="notification")
    try:
        matches = matches_db.list_unnotified_matches(client, min_score=MIN_SCORE_FOR_DIGEST)
        if matches:
            digest = format_digest(matches, client)
            telegram_client.send_message(digest)
            matches_db.mark_matches_notified(client, [match.id for match in matches])

        stats = NotifierStats(matches_notified=len(matches))
        runs_db.finish_run(client, run_id, status="success", stats=asdict(stats))
        return stats
    except Exception as error:
        runs_db.finish_run(client, run_id, status="failed", stats={}, error=str(error))
        raise
