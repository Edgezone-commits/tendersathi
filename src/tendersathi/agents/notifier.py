"""Notifier agent: emails a digest of newly matched tenders via Gmail SMTP.

Unlike the other four agents, this one makes no LLM call -- it only
formats already-computed match scores (Phase 3) into an email and sends
it with Python's standard `smtplib`/`email` modules (no extra dependency,
and no provider abstraction needed for a single free channel). Each
digest marks every match it sends with `notified_at`, so a tender a
company already saw in a previous run doesn't reappear in today's digest.
"""

from __future__ import annotations

import smtplib
from dataclasses import asdict, dataclass
from email.mime.text import MIMEText

from supabase import Client
from tendersathi import config
from tendersathi.db import companies as companies_db
from tendersathi.db import matches as matches_db
from tendersathi.db import runs as runs_db
from tendersathi.db import tenders as tenders_db
from tendersathi.db.models import MatchRow

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 465

# Matches below this score are too weak to bother a company with. Scores are
# already normalised 0.0-1.0 by the Matcher (Phase 3), so one fixed cutoff
# applies regardless of company.
MIN_SCORE_FOR_DIGEST = 0.5


class EmailClient:
    """Thin wrapper over Gmail's SMTP server, authenticated with an app password."""

    def __init__(self, address: str, app_password: str, recipient: str) -> None:
        self.address = address
        self.app_password = app_password
        self.recipient = recipient

    def send_message(self, subject: str, body: str) -> None:
        """Send a plain-text email, raising if Gmail rejects the login or the send."""
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = self.address
        message["To"] = self.recipient
        with smtplib.SMTP_SSL(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
            server.login(self.address, self.app_password)
            server.sendmail(self.address, [self.recipient], message.as_string())


def get_email_client() -> EmailClient:
    """Build an EmailClient from `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` in the environment.

    `DIGEST_RECIPIENT_EMAIL` defaults to `GMAIL_ADDRESS` (send the digest to
    the same account) when not set.
    """
    address = config.GMAIL_ADDRESS
    app_password = config.GMAIL_APP_PASSWORD
    if not address or not app_password:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env to send notifications."
        )
    recipient = config.DIGEST_RECIPIENT_EMAIL or address
    return EmailClient(address, app_password, recipient)


def format_digest(matches: list[MatchRow], client: Client) -> str:
    """Render matches into one plain-text email body, grouped by company.

    Looks up each match's tender/company row individually rather than
    joining in SQL -- a digest is at most a few dozen rows, so the extra
    round-trips are cheap and this keeps every `tendersathi.db` module free
    of hand-written joins.
    """
    lines = ["TenderSathi daily digest", ""]

    by_company: dict[str, list[MatchRow]] = {}
    for match in matches:
        by_company.setdefault(match.company_id, []).append(match)

    for company_id, company_matches in by_company.items():
        company = companies_db.get_company(client, company_id)
        company_name = company.name if company else "Unknown company"
        lines.append(company_name)
        lines.append("-" * len(company_name))
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


def run_notifier(client: Client, email_client: EmailClient) -> NotifierStats:
    """Send a digest of every unnotified match at or above `MIN_SCORE_FOR_DIGEST`.

    Same start/finish-run pattern as `run_ingestion`/`run_matcher`, so a
    failed email send shows up in the `runs` table instead of silently
    vanishing in a GitHub Actions log. Sends nothing (and records a
    zero-match run) when there's nothing new to report, rather than
    emailing an empty digest every day.
    """
    run_id = runs_db.start_run(client, run_type="notification")
    try:
        matches = matches_db.list_unnotified_matches(client, min_score=MIN_SCORE_FOR_DIGEST)
        if matches:
            digest = format_digest(matches, client)
            plural = "" if len(matches) == 1 else "es"
            subject = f"TenderSathi daily digest - {len(matches)} new match{plural}"
            email_client.send_message(subject, digest)
            matches_db.mark_matches_notified(client, [match.id for match in matches])

        stats = NotifierStats(matches_notified=len(matches))
        runs_db.finish_run(client, run_id, status="success", stats=asdict(stats))
        return stats
    except Exception as error:
        runs_db.finish_run(client, run_id, status="failed", stats={}, error=str(error))
        raise
