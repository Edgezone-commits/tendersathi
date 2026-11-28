"""Tests for the Notifier agent: digest formatting, EmailClient, and run_notifier.

format_digest/EmailClient are tested directly; run_notifier is tested
with the db modules mocked, same style as tests/agents/test_matcher.py for
run_matcher.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tendersathi.agents.notifier import (
    EmailClient,
    format_digest,
    get_email_client,
    run_notifier,
)
from tendersathi.db.models import CompanyRow, MatchRow, TenderRow


def _tender(tender_id: str, title: str, deadline: datetime | None) -> TenderRow:
    now = datetime.now(UTC)
    return TenderRow(
        id=tender_id,
        source="manual_upload",
        source_url=None,
        external_reference=None,
        title=title,
        procuring_entity=None,
        category=None,
        district=None,
        estimated_cost=None,
        submission_deadline=deadline,
        fingerprint=f"fp-{tender_id}",
        status="new",
        created_at=now,
        updated_at=now,
    )


def _company(company_id: str, name: str) -> CompanyRow:
    return CompanyRow(id=company_id, name=name, sector=None, annual_turnover=None,
                       licence_class=None, districts=[])


def _match(tender_id: str, company_id: str, score: float) -> MatchRow:
    return MatchRow(id=f"m-{tender_id}-{company_id}", tender_id=tender_id,
                     company_id=company_id, score=score, reasoning=None)


def test_email_client_send_message_logs_in_and_sends_over_smtp_ssl():
    with patch("tendersathi.agents.notifier.smtplib.SMTP_SSL") as mock_smtp_ssl:
        mock_server = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        client = EmailClient(
            address="me@gmail.com", app_password="app-pw", recipient="me@gmail.com"
        )
        client.send_message("Subject line", "Body text")

        mock_smtp_ssl.assert_called_once_with("smtp.gmail.com", 465)
        mock_server.login.assert_called_once_with("me@gmail.com", "app-pw")
        mock_server.sendmail.assert_called_once()
        from_addr, to_addrs, message_text = mock_server.sendmail.call_args.args
        assert from_addr == "me@gmail.com"
        assert to_addrs == ["me@gmail.com"]
        assert "Subject line" in message_text
        encoded_body = message_text.rsplit("\n\n", 1)[-1].strip()
        assert base64.b64decode(encoded_body).decode("utf-8") == "Body text"


def test_get_email_client_raises_when_not_configured():
    with patch("tendersathi.agents.notifier.config") as mock_config:
        mock_config.GMAIL_ADDRESS = None
        mock_config.GMAIL_APP_PASSWORD = None
        with pytest.raises(RuntimeError, match="GMAIL_ADDRESS"):
            get_email_client()


def test_get_email_client_defaults_recipient_to_sender():
    with patch("tendersathi.agents.notifier.config") as mock_config:
        mock_config.GMAIL_ADDRESS = "me@gmail.com"
        mock_config.GMAIL_APP_PASSWORD = "app-pw"
        mock_config.DIGEST_RECIPIENT_EMAIL = None
        client = get_email_client()

    assert client.address == "me@gmail.com"
    assert client.recipient == "me@gmail.com"


def test_get_email_client_honors_explicit_recipient():
    with patch("tendersathi.agents.notifier.config") as mock_config:
        mock_config.GMAIL_ADDRESS = "me@gmail.com"
        mock_config.GMAIL_APP_PASSWORD = "app-pw"
        mock_config.DIGEST_RECIPIENT_EMAIL = "company-inbox@example.com"
        client = get_email_client()

    assert client.recipient == "company-inbox@example.com"


@patch("tendersathi.agents.notifier.tenders_db")
@patch("tendersathi.agents.notifier.companies_db")
def test_format_digest_groups_by_company_and_sorts_by_score(mock_companies_db, mock_tenders_db):
    mock_companies_db.get_company.return_value = _company("c1", "Himalayan Builders")
    mock_tenders_db.get_tender.side_effect = [
        _tender("t1", "Road repair", datetime(2026, 12, 1, tzinfo=UTC)),
        _tender("t2", "Bridge works", None),
    ]
    matches = [_match("t2", "c1", 0.4), _match("t1", "c1", 0.9)]

    digest = format_digest(matches, client=MagicMock())

    assert "Himalayan Builders" in digest
    road_idx = digest.index("Road repair")
    bridge_idx = digest.index("Bridge works")
    assert road_idx < bridge_idx  # higher score (0.9) listed first
    assert "2026-12-01" in digest
    assert "unknown deadline" in digest


@patch("tendersathi.agents.notifier.matches_db")
@patch("tendersathi.agents.notifier.runs_db")
def test_run_notifier_sends_digest_and_marks_matches_notified(mock_runs_db, mock_matches_db):
    mock_runs_db.start_run.return_value = "run-1"
    mock_matches_db.list_unnotified_matches.return_value = [_match("t1", "c1", 0.9)]
    email_client = MagicMock()
    client = MagicMock()

    with patch("tendersathi.agents.notifier.format_digest", return_value="digest text"):
        stats = run_notifier(client=client, email_client=email_client)

    assert stats.matches_notified == 1
    email_client.send_message.assert_called_once_with(
        "TenderSathi daily digest - 1 new match", "digest text"
    )
    mock_matches_db.mark_matches_notified.assert_called_once_with(client, ["m-t1-c1"])
    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "success"


@patch("tendersathi.agents.notifier.matches_db")
@patch("tendersathi.agents.notifier.runs_db")
def test_run_notifier_sends_nothing_when_no_unnotified_matches(mock_runs_db, mock_matches_db):
    mock_runs_db.start_run.return_value = "run-1"
    mock_matches_db.list_unnotified_matches.return_value = []
    email_client = MagicMock()

    stats = run_notifier(client=MagicMock(), email_client=email_client)

    assert stats.matches_notified == 0
    email_client.send_message.assert_not_called()
    mock_matches_db.mark_matches_notified.assert_not_called()


@patch("tendersathi.agents.notifier.matches_db")
@patch("tendersathi.agents.notifier.runs_db")
def test_run_notifier_marks_run_failed_and_reraises_on_error(mock_runs_db, mock_matches_db):
    mock_runs_db.start_run.return_value = "run-1"
    mock_matches_db.list_unnotified_matches.side_effect = RuntimeError("db blew up")

    with pytest.raises(RuntimeError, match="db blew up"):
        run_notifier(client=MagicMock(), email_client=MagicMock())

    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "failed"
