"""Tests for BS -> AD date conversion."""

from __future__ import annotations

from datetime import date

import pytest

from tendersathi.ingestion.nepali_dates import InvalidBsDateError, bs_to_ad


def test_bs_to_ad_matches_known_conversion() -> None:
    # Taken directly from a sample bid document, which states both forms:
    # "2083-08-25(2026-12-11)".
    assert bs_to_ad("2083-08-25") == date(2026, 12, 11)


def test_bs_to_ad_rejects_malformed_string() -> None:
    with pytest.raises(InvalidBsDateError):
        bs_to_ad("25 Bhadra 2083")


def test_bs_to_ad_rejects_out_of_range_month() -> None:
    with pytest.raises(InvalidBsDateError):
        bs_to_ad("2083-13-01")
