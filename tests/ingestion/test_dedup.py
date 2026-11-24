"""Tests for compute_fingerprint."""

from __future__ import annotations

import pytest

from tendersathi.ingestion.dedup import compute_fingerprint


def test_same_external_reference_gives_same_fingerprint() -> None:
    first = compute_fingerprint("bolpatra", external_reference="REF-123")
    second = compute_fingerprint("bolpatra", external_reference="REF-123")

    assert first == second


def test_different_sources_with_same_reference_differ() -> None:
    bolpatra = compute_fingerprint("bolpatra", external_reference="REF-123")
    manual = compute_fingerprint("manual_upload", external_reference="REF-123")

    assert bolpatra != manual


def test_same_file_bytes_give_same_fingerprint() -> None:
    first = compute_fingerprint("manual_upload", file_bytes=b"%PDF-1.4 content")
    second = compute_fingerprint("manual_upload", file_bytes=b"%PDF-1.4 content")

    assert first == second


def test_different_file_bytes_give_different_fingerprints() -> None:
    first = compute_fingerprint("manual_upload", file_bytes=b"document one")
    second = compute_fingerprint("manual_upload", file_bytes=b"document two")

    assert first != second


def test_external_reference_takes_priority_over_file_bytes() -> None:
    with_ref = compute_fingerprint(
        "manual_upload", external_reference="REF-123", file_bytes=b"irrelevant bytes"
    )
    ref_only = compute_fingerprint("manual_upload", external_reference="REF-123")

    assert with_ref == ref_only


def test_raises_without_reference_or_bytes() -> None:
    with pytest.raises(ValueError, match="external_reference or file_bytes"):
        compute_fingerprint("manual_upload")
