-- Phase 1: initial schema for tenders, tender_pages, companies, matches, runs.
-- Apply with the Supabase CLI (`supabase db push`) or paste into the SQL
-- editor at https://supabase.com/dashboard -> your project -> SQL Editor.

create extension if not exists pgcrypto;
create extension if not exists vector;

create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- One row per ingestion/eval run, so a bad digest can be traced back to a
-- specific run's stats or error.
create table if not exists runs (
    id uuid primary key default gen_random_uuid(),
    run_type text not null,
    status text not null default 'running' check (status in ('running', 'success', 'failed')),
    stats jsonb not null default '{}'::jsonb,
    error text,
    started_at timestamptz not null default now(),
    finished_at timestamptz
);

-- One row per tender. Scout-extracted fields (procuring_entity, category,
-- district, estimated_cost, submission_deadline, eligibility_requirements)
-- are nullable because Phase 1 only stores raw text; Phase 2 fills them in.
create table if not exists tenders (
    id uuid primary key default gen_random_uuid(),
    source text not null check (source in ('manual_upload', 'bolpatra', 'newspaper')),
    source_url text,
    external_reference text,
    title text,
    procuring_entity text,
    category text,
    district text,
    estimated_cost numeric,
    submission_deadline timestamptz,
    eligibility_requirements jsonb,
    fingerprint text not null unique,
    status text not null default 'new' check (status in ('new', 'matched', 'ignored', 'archived')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists tenders_status_idx on tenders (status);
create index if not exists tenders_submission_deadline_idx on tenders (submission_deadline);

create trigger tenders_set_updated_at
    before update on tenders
    for each row
    execute function set_updated_at();

-- Page-level text, kept separate from `tenders` so the Eligibility agent
-- (Phase 4) can cite an exact page number for every claim.
create table if not exists tender_pages (
    id uuid primary key default gen_random_uuid(),
    tender_id uuid not null references tenders (id) on delete cascade,
    page_number integer not null check (page_number > 0),
    text text not null default '',
    used_ocr boolean not null default false,
    created_at timestamptz not null default now(),
    unique (tender_id, page_number)
);

-- One row per company profile the Matcher (Phase 3) scores tenders against.
-- profile_embedding is populated by the Matcher for pgvector similarity search.
create table if not exists companies (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    sector text,
    annual_turnover numeric,
    licence_class text,
    districts text[] not null default '{}',
    past_projects jsonb not null default '[]'::jsonb,
    profile_embedding vector(1536),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create trigger companies_set_updated_at
    before update on companies
    for each row
    execute function set_updated_at();

-- One row per (tender, company) the Matcher has scored. Unique pair so
-- re-scoring a tender updates the existing match instead of duplicating it.
create table if not exists matches (
    id uuid primary key default gen_random_uuid(),
    tender_id uuid not null references tenders (id) on delete cascade,
    company_id uuid not null references companies (id) on delete cascade,
    score numeric not null,
    reasoning text,
    created_at timestamptz not null default now(),
    unique (tender_id, company_id)
);

create index if not exists matches_company_idx on matches (company_id);
