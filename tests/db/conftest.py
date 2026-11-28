"""Shared fixture for mocking Supabase's chained query builder in db tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_table() -> MagicMock:
    """A MagicMock that supports `.select(...).eq(...).execute()`-style chaining.

    Every chainable method (select/eq/limit/insert/upsert/update/order) returns
    the same mock, so a test only needs to set `.execute.return_value.data`.
    """
    table = MagicMock()
    for method in (
        "select",
        "eq",
        "gte",
        "is_",
        "in_",
        "limit",
        "insert",
        "upsert",
        "update",
        "order",
    ):
        getattr(table, method).return_value = table
    return table


@pytest.fixture
def mock_client(mock_table: MagicMock) -> MagicMock:
    """A fake Supabase Client whose `.table(...)` always returns `mock_table`."""
    client = MagicMock()
    client.table.return_value = mock_table
    return client
