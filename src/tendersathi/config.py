"""Central place to read configuration from environment variables.

Keeping all `os.environ` access in one module means no other module
reads secrets directly, and tests can monkeypatch this module instead
of the real environment.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    """Read an environment variable, optionally raising if it's missing."""
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


LLM_PROVIDER = get_env("LLM_PROVIDER", default="groq")
GROQ_API_KEY = get_env("GROQ_API_KEY")
GROQ_MODEL = get_env("GROQ_MODEL", default="llama-3.3-70b-versatile")

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_KEY = get_env("SUPABASE_KEY")
# Direct Postgres connection string (Project Settings -> Database -> Connection
# string), distinct from the REST API URL/key above. Used by the LangGraph
# checkpointer, which needs a raw SQL connection rather than Supabase's REST API.
DATABASE_URL = get_env("DATABASE_URL")
