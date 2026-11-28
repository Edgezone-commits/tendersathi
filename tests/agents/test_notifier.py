"""Tests for the Notifier agent: digest formatting, Telegram client, and run_notifier.

format_digest/TelegramClient are tested directly; run_notifier is tested
with the db modules mocked, same style as tests/agents/test_matcher.py for
run_matcher.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tendersathi.agents.notifier import (
    TelegramClient,
    format_digest,
    get_telegram_client,
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


def test_telegram_client_send_message_posts_to_telegram_api():
    with patch("tendersathi.agents.notifier.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())

        client = TelegramClient(bot_token="tok", chat_id="chat-1")
        client.send_message("hello")

        mock_post.assert_called_once_with(
            "https://api.telegram.org/bottok/sendMessage",
            json={"chat_id": "chat-1", "text": "hello", "parse_mode": "Markdown"},
            timeout=10.0,
        )


def test_get_telegram_client_raises_when_not_configured():
    with patch("tendersathi.agents.notifier.config") as mock_config:
        mock_config.TELEGRAM_BOT_TOKEN = None
        mock_config.TELEGRAM_CHAT_ID = None
        with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
            get_telegram_client()


def test_get_telegram_client_builds_client_from_config():
    with patch("tendersathi.agents.notifier.config") as mock_config:
        mock_config.TELEGRAM_BOT_TOKEN = "tok"
        mock_config.TELEGRAM_CHAT_ID = "chat-1"
        client = get_telegram_client()

    assert client.bot_token == "tok"
    assert client.chat_id == "chat-1"


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
    telegram_client = MagicMock()
    client = MagicMock()

    with patch("tendersathi.agents.notifier.format_digest", return_value="digest text"):
        stats = run_notifier(client=client, telegram_client=telegram_client)

    assert stats.matches_notified == 1
    telegram_client.send_message.assert_called_once_with("digest text")
    mock_matches_db.mark_matches_notified.assert_called_once_with(client, ["m-t1-c1"])
    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "success"


@patch("tendersathi.agents.notifier.matches_db")
@patch("tendersathi.agents.notifier.runs_db")
def test_run_notifier_sends_nothing_when_no_unnotified_matches(mock_runs_db, mock_matches_db):
    mock_runs_db.start_run.return_value = "run-1"
    mock_matches_db.list_unnotified_matches.return_value = []
    telegram_client = MagicMock()

    stats = run_notifier(client=MagicMock(), telegram_client=telegram_client)

    assert stats.matches_notified == 0
    telegram_client.send_message.assert_not_called()
    mock_matches_db.mark_matches_notified.assert_not_called()


@patch("tendersathi.agents.notifier.matches_db")
@patch("tendersathi.agents.notifier.runs_db")
def test_run_notifier_marks_run_failed_and_reraises_on_error(mock_runs_db, mock_matches_db):
    mock_runs_db.start_run.return_value = "run-1"
    mock_matches_db.list_unnotified_matches.side_effect = RuntimeError("db blew up")

    with pytest.raises(RuntimeError, match="db blew up"):
        run_notifier(client=MagicMock(), telegram_client=MagicMock())

    mock_runs_db.finish_run.assert_called_once()
    assert mock_runs_db.finish_run.call_args.kwargs["status"] == "failed"
