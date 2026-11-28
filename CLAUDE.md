# TenderSathi

## Problem

Nepali SMEs (contractors, IT firms, suppliers) miss relevant government tenders
published on bolpatra.gov.np and in newspaper notices, and waste hours reading
bid documents only to discover they are not eligible to bid at all.

## Solution

A multi-agent system with five stages:

1. **Scout agent** — ingests new tenders daily and extracts structured fields
   (title, procuring entity, category, district, estimated cost, deadline,
   eligibility requirements).
2. **Matcher agent** — scores each tender against a company profile (sector,
   annual turnover, past projects, licence class, districts).
3. **Eligibility agent** — reads the bid document and produces a checklist
   ("required / you have / missing"), with every claim citing a page number.
4. **Drafter agent** — prepares a document checklist and cover-letter draft.
   **Requires human approval before it is finalised.**
5. **Notifier** — sends a daily email digest of matched tenders (Gmail SMTP).

## Architecture

- **Orchestration**: LangGraph, using its checkpointing for durability and its
  `interrupt` mechanism for the human-approval step before the Drafter
  finalises anything.
- **LLM calls**: every agent calls the LLM abstraction in
  `src/tendersathi/llm/`, never a provider SDK directly. This is what lets us
  swap Groq for Gemini or Ollama with one environment variable
  (`LLM_PROVIDER`), and gives one place to add tracing and validation
  retries.
- **Structured outputs**: every LLM call returns a Pydantic v2 model, not raw
  text. `GroqClient.generate()` retries automatically if the model's JSON
  fails validation.
- **Storage**: Supabase Postgres, with pgvector for embeddings (used by the
  Matcher for semantic similarity between a company profile and a tender).
- **Tracing**: Langfuse wraps LLM calls so every prompt/response pair is
  inspectable — essential for explaining and debugging agent behaviour.
- **API**: FastAPI backend (deployed later to Fly.io).
- **Frontend**: Next.js (deployed later to Vercel).
- **Scheduling**: GitHub Actions cron triggers the daily ingestion run.

## Tech stack (fixed — all free tier, do not substitute paid services)

- Python 3.11, dependency management via `uv`
- LangGraph for orchestration
- Groq (Llama 3.x / Qwen) as the default LLM provider, via the abstraction
  layer in `src/tendersathi/llm/`
- Pydantic v2 for all structured LLM outputs
- Supabase Postgres + pgvector
- FastAPI
- Next.js
- GitHub Actions (cron + CI)
- Langfuse for tracing
- pytest for tests and evals
- Docker / docker-compose for local dev

## Folder structure

```
src/tendersathi/
  agents/       # one module per agent (scout, matcher, eligibility, drafter)
  ingestion/    # scraping/parsing of bolpatra.gov.np and bid documents
  db/           # Supabase/Postgres access, pgvector queries
  llm/          # provider-agnostic LLM abstraction (base.py, groq_client.py, factory)
  api/          # FastAPI routes
  config.py     # the only module that reads os.environ directly
tests/          # mirrors the src/ layout, one test module per source module
data/samples/   # small sample tender/bid documents used in tests and evals
evals/          # offline evaluation scripts/datasets for agent quality
```

## Coding conventions

- Type hints on every function signature, including return types.
- A short docstring on every public function/class explaining *why*, not
  what the code already says.
- Small functions: if a function needs its own section comments, split it.
- No hardcoded secrets, URLs with embedded credentials, or API keys —
  everything comes from `.env` via `src/tendersathi/config.py`.
- Every LLM call goes through `tendersathi.llm.get_llm_client()` and returns
  a Pydantic model. Never call a provider SDK (`groq`, etc.) from agent code
  directly.
- Every LLM call is traced via Langfuse once Phase 7 wires it in — don't
  bypass the abstraction layer to avoid tracing.
- Prefer explicit, readable code over clever abstractions. You (the author)
  need to be able to explain every design decision in an interview, so
  boring and obvious beats elegant and opaque.

## Testing rules

- Every module under `src/tendersathi/` has a corresponding test module
  under `tests/`.
- Tests mock external services (Groq, Supabase, Gmail SMTP, HTTP fetches) —
  no test should make a real network call.
- Never mark a phase "done" with failing tests. Run `uv run pytest` and
  `uv run ruff check .` before moving to the next phase.

## Phase roadmap

- **Phase 0 — Project setup** (this phase): repo scaffold, tooling, LLM
  abstraction + Groq client, CI.
- **Phase 1 — Data ingestion**: fetch tender listings from bolpatra.gov.np
  and newspaper sources.
- **Phase 2 — Extraction agent**: turn raw listings/documents into
  structured tender records (the "Scout" agent).
- **Phase 3 — Matcher agent**: score tenders against a company profile.
- **Phase 4 — Eligibility agent**: checklist with page-number citations from
  the bid document.
- **Phase 5 — LangGraph orchestration**: wire the agents into a graph with
  checkpointing and a human-approval interrupt before the Drafter finalises
  output.
- **Phase 6 — Email notifier + GitHub Actions cron**: daily digest, daily
  scheduled run.
- **Phase 7 — Evals + Langfuse**: offline eval suite, tracing wired into
  every LLM call.
- **Phase 8 — FastAPI + Fly.io deploy**: expose the system over HTTP and
  deploy it.
- **Phase 9 — Next.js frontend**: deployed to Vercel.
- **Phase 10 — MCP server + README + demo polish**.

## Current status / pending

- Phases 0-5 are code-complete and committed (Scout, Matcher, Eligibility,
  Drafter agents + LangGraph orchestration with a Postgres checkpointer and
  a human-approval interrupt). All tests pass, ruff is clean.
- **Verified**: the Postgres checkpointer (`tendersathi.orchestration.checkpointer`)
  connects successfully. `DATABASE_URL` in `.env` now uses Supabase's
  **connection pooler** (Transaction mode, `aws-0-ap-northeast-1.pooler.supabase.com:6543`,
  user `postgres.<project-ref>`) instead of the direct host, which resolved
  to an IPv6-only address and timed out from this machine's network. The
  smoke test (`uv run python -c "from tendersathi.orchestration.checkpointer
  import get_checkpointer; get_checkpointer().__enter__()"`) passes.
- **Phase 6 is code-complete and committed**: Notifier agent
  (`tendersathi.agents.notifier`) formats an email digest of unnotified
  matches (score >= 0.5) and marks them `notified_at` so they aren't resent;
  `tendersathi.daily_run` wires Matcher -> Notifier for the cron
  (`.github/workflows/daily-digest.yml`, 03:00 UTC daily +
  `workflow_dispatch`). Automated ingestion isn't wired into the cron yet --
  `BolpatraScraper` is still unimplemented (see its docstring), so the cron
  only re-scores/re-notifies tenders a human has already uploaded manually.
  Added a `matches.notified_at` column (migration
  `20260102000000_add_matches_notified_at.sql`).
- **Notifier channel switched from Telegram to Gmail SMTP** (user decision,
  after Phase 6 initially shipped with a Telegram bot): `EmailClient` in
  `tendersathi.agents.notifier` sends the digest via `smtplib`/`email`
  (stdlib only, no new dependency), authenticated with a Gmail **App
  Password** rather than the account's real password. Config/`.env.example`
  now have `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`/`DIGEST_RECIPIENT_EMAIL`
  instead of the old `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (removed, not
  deprecated-in-place). All tests pass (116), ruff is clean.
- **Needs real secrets before the cron can run for real**: `GMAIL_ADDRESS`/
  `GMAIL_APP_PASSWORD` (generate the app password at
  https://myaccount.google.com/apppasswords, requires 2-Step Verification)
  and the repo's GitHub Actions secrets (`SUPABASE_URL`, `SUPABASE_KEY`,
  `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `DIGEST_RECIPIENT_EMAIL`) haven't
  been set yet, and the `matches.notified_at` migration hasn't been applied
  to the live Supabase project.
- **Phase 7 is code-complete and committed**: `tendersathi.llm.tracing`
  wraps every LLM call in a Langfuse generation span (`get_llm_client()`
  now returns a `TracedLLMClient`, not the raw provider client -- updated
  the one test that asserted otherwise), recording prompt/output/model and
  marking the span `ERROR` on any exception. Credentials are read via
  `config.LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`
  (already in `.env.example`) rather than Langfuse's own env fallback, same
  pattern as every other client in this codebase; a missing key just
  disables tracing rather than raising, so local dev without a Langfuse
  account is unaffected. Pinned `langfuse>=3.0.0` in `pyproject.toml` -- the
  code needs the v3+ OTEL-based API, which `>=2.53.0` would not have
  guaranteed. Added `evals/eval_scout.py` + `evals/datasets/
  scout_ground_truth.json`: a scored offline eval (distinct from the
  existing manual `run_scout_on_samples.py`) that runs Scout against the
  sample PDFs and grades title/procuring_entity/district/category against
  hand-verified ground truth (every keyword was confirmed by reading the
  samples' raw extracted text directly), exiting non-zero below a loose
  accuracy threshold. Matcher/Eligibility/Drafter evals are **not** built
  yet -- Matcher is deterministic and already covered by its unit tests;
  Eligibility/Drafter would need their own hand-verified ground truth,
  deferred for now. All tests pass (115), ruff is clean.
- **Needs a real Langfuse account before tracing does anything**: without
  `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` in `.env`, every LLM call
  still works but produces no trace (silently disabled, by design).
- Next phase: **Phase 8** (FastAPI + Fly.io deploy).
