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
# Postgres connection string, distinct from the REST API URL/key above. Used
# by the LangGraph checkpointer, which needs a raw SQL connection rather than
# Supabase's REST API. Use the **connection pooler** string (Project Settings
# -> Database -> Connection pooling -> Transaction mode), not the direct host
# -- the direct host resolves IPv6-only on networks without IPv6 egress.
DATABASE_URL = get_env("DATABASE_URL")

# Email notifier (Phase 6): a Gmail account sends the daily digest over
# SMTP, authenticated with an App Password (https://myaccount.google.com/
# apppasswords, requires 2-Step Verification on the account) rather than
# the account's real password. DIGEST_RECIPIENT_EMAIL defaults to
# GMAIL_ADDRESS (send to yourself) when not set.
GMAIL_ADDRESS = get_env("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = get_env("GMAIL_APP_PASSWORD")
DIGEST_RECIPIENT_EMAIL = get_env("DIGEST_RECIPIENT_EMAIL")

# Langfuse (Phase 7): free account at https://cloud.langfuse.com. Passed
# explicitly to the Langfuse client in tendersathi.llm.tracing rather than
# left for its SDK to read from the environment itself, same reasoning as
# every other credential in this module.
LANGFUSE_PUBLIC_KEY = get_env("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = get_env("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = get_env("LANGFUSE_HOST", default="https://cloud.langfuse.com")
