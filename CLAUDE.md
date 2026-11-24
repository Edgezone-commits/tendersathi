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
5. **Notifier** — sends a daily Telegram digest of matched tenders.

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
- Tests mock external services (Groq, Supabase, Telegram, HTTP fetches) —
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
- **Phase 6 — Telegram notifier + GitHub Actions cron**: daily digest, daily
  scheduled run.
- **Phase 7 — Evals + Langfuse**: offline eval suite, tracing wired into
  every LLM call.
- **Phase 8 — FastAPI + Fly.io deploy**: expose the system over HTTP and
  deploy it.
- **Phase 9 — Next.js frontend**: deployed to Vercel.
- **Phase 10 — MCP server + README + demo polish**.
