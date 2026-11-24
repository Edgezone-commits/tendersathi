"""Supabase client factory — the only place that opens the Postgres connection."""

from __future__ import annotations

from supabase import Client, create_client
from tendersathi import config


def get_supabase_client() -> Client:
    """Build a Supabase client from `SUPABASE_URL` / `SUPABASE_KEY` in the environment."""
    url = config.SUPABASE_URL
    key = config.SUPABASE_KEY
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in .env to talk to the database."
        )
    return create_client(url, key)
