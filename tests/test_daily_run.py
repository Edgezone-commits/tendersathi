"""Tests for the daily cron entry point, with every real client mocked out."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tendersathi.daily_run import main


@patch("tendersathi.daily_run.run_notifier")
@patch("tendersathi.daily_run.get_telegram_client")
@patch("tendersathi.daily_run.run_matcher")
@patch("tendersathi.daily_run.get_supabase_client")
def test_main_runs_matcher_then_notifier_and_returns_zero(
    mock_get_supabase_client, mock_run_matcher, mock_get_telegram_client, mock_run_notifier
):
    client = MagicMock()
    telegram_client = MagicMock()
    mock_get_supabase_client.return_value = client
    mock_get_telegram_client.return_value = telegram_client

    exit_code = main()

    assert exit_code == 0
    mock_run_matcher.assert_called_once_with(client)
    mock_run_notifier.assert_called_once_with(client, telegram_client)


@patch("tendersathi.daily_run.run_notifier")
@patch("tendersathi.daily_run.get_telegram_client")
@patch("tendersathi.daily_run.run_matcher")
@patch("tendersathi.daily_run.get_supabase_client")
def test_main_returns_one_when_a_step_raises(
    mock_get_supabase_client, mock_run_matcher, mock_get_telegram_client, mock_run_notifier
):
    mock_run_matcher.side_effect = RuntimeError("matcher blew up")

    exit_code = main()

    assert exit_code == 1
    mock_run_notifier.assert_not_called()
