-- Database for student workspaces. Run once in your Supabase project:
-- Dashboard -> SQL Editor -> paste this file -> Run.
--
-- Every table is keyed by the signed-in user's id, and row-level security
-- (RLS) means a student can only ever read or write their own rows, even
-- though the site's anon key is public in the page source.

-- Exercises a student has finished (their tests all passed, or they ticked
-- the item on the sheet).
create table if not exists public.progress (
  user_id      uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  item_id      text        not null check (char_length(item_id) between 1 and 64),
  completed_at timestamptz not null default now(),
  primary key (user_id, item_id)
);

-- The student's latest code for each exercise.
create table if not exists public.drafts (
  user_id    uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  item_id    text        not null check (char_length(item_id) between 1 and 64),
  code       text        not null check (char_length(code) <= 100000),
  updated_at timestamptz not null default now(),
  primary key (user_id, item_id)
);

-- Days the student ran tests, for the streak on the dashboard.
create table if not exists public.activity (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  day     date not null,
  primary key (user_id, day)
);

alter table public.progress enable row level security;
alter table public.drafts   enable row level security;
alter table public.activity enable row level security;

-- One policy per table covers select, insert, update and delete. "to
-- authenticated" keeps signed-out visitors out entirely; (select auth.uid())
-- is evaluated once per query rather than once per row.
drop policy if exists "Students manage their own progress" on public.progress;
create policy "Students manage their own progress" on public.progress
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Students manage their own drafts" on public.drafts;
create policy "Students manage their own drafts" on public.drafts
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Students manage their own activity" on public.activity;
create policy "Students manage their own activity" on public.activity
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
