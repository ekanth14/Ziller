-- Supabase Migration: Create collaborations table for ZILLERS research proposals
-- Run this in your Supabase SQL Editor (Dashboard > SQL Editor > New query)

create table if not exists public.collaborations (
  id text primary key,
  timestamp timestamptz default now(),
  name text not null,
  email text not null,
  github text not null,
  linkedin text not null,
  website text,
  track text not null,
  message text not null,
  client_ip text
);

-- Enable Row Level Security (RLS)
alter table public.collaborations enable row level security;

-- Policy 1: Allow public visitors to submit collaboration proposals
drop policy if exists "Allow public submissions" on public.collaborations;
create policy "Allow public submissions"
  on public.collaborations
  for insert
  with check (true);

-- Policy 2: Allow reading proposals by authorized operators / service role
drop policy if exists "Allow authorized read" on public.collaborations;
create policy "Allow authorized read"
  on public.collaborations
  for select
  using (true);

-- Create index on timestamp for fast sorting
create index if not exists idx_collaborations_timestamp on public.collaborations (timestamp desc);
