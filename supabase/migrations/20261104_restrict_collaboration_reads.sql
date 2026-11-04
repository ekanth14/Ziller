-- Pending deployment approval. Local source only; do not execute automatically.
-- Existing records are retained. Public submissions go through the guarded API.
drop policy if exists "Allow authorized read" on public.collaborations;
drop policy if exists "Allow public submissions" on public.collaborations;
revoke select, insert, update, delete on public.collaborations from anon, authenticated;
-- The backend must use its configured service role; no browser receives it.
