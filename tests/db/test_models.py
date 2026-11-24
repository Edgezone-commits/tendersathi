"""Tests for parse_timestamp."""

from __future__ import annotations

from datetime import datetime

from tendersathi.db.models import parse_timestamp


def test_parse_timestamp_handles_none():
    assert parse_timestamp(None) is None


def test_parse_timestamp_handles_trailing_z():
    result = parse_timestamp("2026-01-01T00:00:00Z")

    assert result == datetime.fromisoformat("2026-01-01T00:00:00+00:00")


def test_parse_timestamp_handles_explicit_offset():
    result = parse_timestamp("2026-01-01T00:00:00+05:45")

    assert result.utcoffset().total_seconds() == 5 * 3600 + 45 * 60
