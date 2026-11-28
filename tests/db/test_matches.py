"""Tests for the matches db module, with Supabase mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

from tendersathi.db import matches as matches_db


def test_save_match_upserts_on_tender_and_company(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[{"id": "match-1"}])

    match_id = matches_db.save_match(mock_client, "tender-1", "company-1", 0.82, "Good fit")

    assert match_id == "match-1"
    mock_table.upsert.assert_called_once_with(
        {
            "tender_id": "tender-1",
            "company_id": "company-1",
            "score": 0.82,
            "reasoning": "Good fit",
        },
        on_conflict="tender_id,company_id",
    )


def test_list_matches_for_tender_orders_by_score_desc(mock_client, mock_table):
    rows = [
        {"id": "m1", "tender_id": "t1", "company_id": "c1", "score": 0.9, "reasoning": None},
        {"id": "m2", "tender_id": "t1", "company_id": "c2", "score": 0.5, "reasoning": None},
    ]
    mock_table.execute.return_value = MagicMock(data=rows)

    results = matches_db.list_matches_for_tender(mock_client, "t1")

    assert [m.id for m in results] == ["m1", "m2"]
    mock_table.order.assert_called_once_with("score", desc=True)


def test_list_unnotified_matches_filters_by_score_and_null_notified_at(mock_client, mock_table):
    rows = [
        {
            "id": "m1",
            "tender_id": "t1",
            "company_id": "c1",
            "score": 0.9,
            "reasoning": None,
            "notified_at": None,
        }
    ]
    mock_table.execute.return_value = MagicMock(data=rows)

    results = matches_db.list_unnotified_matches(mock_client, min_score=0.5)

    assert [m.id for m in results] == ["m1"]
    assert results[0].notified_at is None
    mock_table.gte.assert_called_once_with("score", 0.5)
    mock_table.is_.assert_called_once_with("notified_at", "null")
    mock_table.order.assert_called_once_with("score", desc=True)


def test_mark_matches_notified_updates_matching_ids(mock_client, mock_table):
    mock_table.execute.return_value = MagicMock(data=[])

    matches_db.mark_matches_notified(mock_client, ["m1", "m2"])

    mock_table.update.assert_called_once()
    assert "notified_at" in mock_table.update.call_args.args[0]
    mock_table.in_.assert_called_once_with("id", ["m1", "m2"])


def test_mark_matches_notified_skips_query_when_no_ids(mock_client, mock_table):
    matches_db.mark_matches_notified(mock_client, [])

    mock_client.table.assert_not_called()
