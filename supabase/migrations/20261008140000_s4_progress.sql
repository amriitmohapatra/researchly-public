-- Researchly S4: the personal progress view, opt-in (CLAUDE.md #2).
--
-- Apply AFTER 20261008120000_s4_document_type.sql: Supabase dashboard ->
-- SQL Editor -> paste this whole file -> Run. Re-running is safe.
--
-- What is stored, and only when the user has switched "Keep my progress"
-- on: per check, how many times each rule fired, the number of words and
-- the article type. Never text, never a file name, never a snippet. The
-- database itself refuses a progress row from a user who has not opted in,
-- so a surface bug cannot start recording.

begin;

-- The opt-in, off by default.
alter table public.user_settings
  add column if not exists keep_progress boolean not null default false;

comment on column public.user_settings.keep_progress is
  'Opt-in for progress_events (counts only). Off by default.';

-- A rule-count map: {"G101": 3, "C303": 1}. Keys are rule ids, values small
-- non-negative integers. Nothing else fits, so no text can be smuggled in.
create or replace function public.researchly_counts_valid(counts jsonb)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select pg_catalog.jsonb_typeof(counts) = 'object'
     and (select pg_catalog.count(*) from pg_catalog.jsonb_each(counts)) <= 200
     and not exists (
       select 1 from pg_catalog.jsonb_each(counts) as e(k, v)
       where e.k !~ '^[A-Z]{1,4}[0-9]{2,4}$'
          or pg_catalog.jsonb_typeof(e.v) <> 'number'
          or (e.v)::text !~ '^[0-9]{1,6}$')
$$;

create table if not exists public.progress_events (
  id            bigint      generated always as identity primary key,
  user_id       uuid        not null
                            default auth.uid()
                            references auth.users (id) on delete cascade,
  created_at    timestamptz not null default now(),
  words         integer     not null,
  document_type text        not null default 'auto',
  counts        jsonb       not null default '{}'::jsonb,
  constraint progress_events_words_range
    check (words between 0 and 2000000),
  constraint progress_events_document_type_known
    check (document_type in ('auto', 'general', 'manuscript',
                             'thesis-chapter', 'abstract', 'commentary',
                             'policy-brief', 'grant',
                             'response-to-reviewers')),
  constraint progress_events_counts_shape
    check (public.researchly_counts_valid(counts))
);

comment on table public.progress_events is
  'Per-check rule counts for the progress view; opt-in (user_settings.keep_progress). Never text. RLS: owner only.';

-- The policies filter on user_id; the view reads a user's newest rows.
create index if not exists progress_events_user_created_idx
  on public.progress_events (user_id, created_at desc);

-- At most 1,000 rows per user: the oldest are dropped as new ones arrive,
-- so the table cannot grow without bound. SECURITY INVOKER: the caller's
-- own RLS delete policy decides, and only their own rows are touched.
create or replace function public.researchly_progress_prune()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  delete from public.progress_events p
  where p.user_id = new.user_id
    and p.id not in (select q.id from public.progress_events q
                     where q.user_id = new.user_id
                     order by q.created_at desc, q.id desc
                     limit 1000);
  return null;
end
$$;

drop trigger if exists progress_events_prune on public.progress_events;
create trigger progress_events_prune
  after insert on public.progress_events
  for each row execute function public.researchly_progress_prune();

alter table public.progress_events enable row level security;
alter table public.progress_events force  row level security;

drop policy if exists progress_events_select_own on public.progress_events;
drop policy if exists progress_events_insert_own on public.progress_events;
drop policy if exists progress_events_delete_own on public.progress_events;

create policy progress_events_select_own on public.progress_events
  for select to authenticated
  using ((select auth.uid()) = user_id);
-- Insert only for yourself AND only when you have opted in.
create policy progress_events_insert_own on public.progress_events
  for insert to authenticated
  with check ((select auth.uid()) = user_id
              and exists (select 1 from public.user_settings s
                          where s.user_id = (select auth.uid())
                            and s.keep_progress));
create policy progress_events_delete_own on public.progress_events
  for delete to authenticated
  using ((select auth.uid()) = user_id);
-- No update policy: a recorded check is never edited.

revoke all on table public.progress_events from public, anon, authenticated;
grant select, insert, delete on table public.progress_events to authenticated;

revoke all on function public.researchly_counts_valid(jsonb)
  from public, anon, authenticated;
grant execute on function public.researchly_counts_valid(jsonb) to authenticated;
revoke all on function public.researchly_progress_prune()
  from public, anon, authenticated;

commit;
