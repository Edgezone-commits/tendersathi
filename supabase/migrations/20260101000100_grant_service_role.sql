-- Fix: tables created via the SQL editor don't automatically pick up the
-- default privileges Supabase normally wires up for service_role, so the
-- backend (which always uses the service_role key, never anon) gets
-- "permission denied" even with RLS off. Grant it explicitly.
--
-- Only service_role gets these grants. anon/authenticated get nothing here
-- on purpose: with RLS disabled, granting them write access would let
-- anyone holding the public anon key (e.g. a future frontend) read or
-- modify tender data directly. Revisit this once RLS policies exist.

grant usage on schema public to service_role;

grant select, insert, update, delete on
    runs,
    tenders,
    tender_pages,
    companies,
    matches
to service_role;
