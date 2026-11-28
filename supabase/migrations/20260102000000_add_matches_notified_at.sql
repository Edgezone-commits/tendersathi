-- Phase 6: track which matches have already gone out in a Telegram digest,
-- so the Notifier doesn't resend the same match every day it stays unactioned.

alter table matches add column if not exists notified_at timestamptz;

create index if not exists matches_notified_at_idx on matches (notified_at);
