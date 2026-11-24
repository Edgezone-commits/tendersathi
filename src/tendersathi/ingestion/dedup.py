"""Builds the stable key that stops re-runs from creating duplicate tenders.

The `tenders` table has a unique constraint on `fingerprint`; every ingestion
path writes through this function first so a re-run of the same source
upserts the existing row instead of inserting a copy.
"""

from __future__ import annotations

import hashlib


def compute_fingerprint(
    source: str,
    *,
    external_reference: str | None = None,
    file_bytes: bytes | None = None,
) -> str:
    """Build a dedup key, preferring the procuring entity's own reference number.

    A reference number is stable even if the document itself changes (e.g. a
    corrigendum), so two ingests of the same tender collapse into one row.
    Without one, we fall back to hashing the file's own bytes: re-uploading
    the identical PDF hashes to the identical fingerprint.
    """
    if external_reference:
        key = f"{source}:{external_reference}"
    elif file_bytes is not None:
        key = f"{source}:{hashlib.sha256(file_bytes).hexdigest()}"
    else:
        raise ValueError("Need either external_reference or file_bytes to fingerprint a tender.")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
