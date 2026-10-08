-- Researchly S2: per-user settings and dictionary (docs/s2-design.md §2).
--
-- Apply: Supabase dashboard -> SQL Editor -> paste this whole file -> Run.
-- It runs as the `postgres` role, which then owns these objects.
--
-- Re-running is safe: tables use IF NOT EXISTS, functions CREATE OR REPLACE,
-- triggers and policies are dropped and recreated, and grants are re-stated.
-- A re-run does NOT alter an existing table's columns or CHECK constraints;
-- changing those needs a new migration.
--
-- What this guarantees (Q7, the two-user test; proven by
-- supabase/tests/test_two_user.py on every CI run):
--   * a signed-in user reads, creates, updates and deletes only rows whose
--     user_id is their own auth.uid(); `anon` has no privileges at all;
--   * nothing here stores document text: only rule ids, two settings and
--     single dictionary words.
--
-- Deliberately absent (s2-design §2): no trigger on auth.users (a missing
-- settings row means defaults), and no profiles / usage / feedback /
-- documents tables. A table that exists invites data into it.

begin;

-- ---------------------------------------------------------------------------
-- Helper for the disabled_rules CHECK. CHECK constraints cannot contain
-- subqueries, so the per-element test lives in an IMMUTABLE function. Rule
-- ids look like S001, LT001, AB802: 1-4 capitals then 1-4 digits.
-- A NULL element fails (it is not a rule id).
-- ---------------------------------------------------------------------------
create or replace function public.researchly_rule_ids_valid(ids text[])
returns boolean
language sql
immutable
strict
parallel safe
security invoker
set search_path = ''
as $$
  select coalesce(
    pg_catalog.bool_and(r is not null and r operator(pg_catalog.~) '^[A-Z]{1,4}[0-9]{1,4}$'),
    true)
  from pg_catalog.unnest(ids) as r
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table if not exists public.user_settings (
  user_id          uuid        primary key
                               default auth.uid()
                               references auth.users (id) on delete cascade,
  disabled_rules   text[]      not null default '{}',
  show_preferences boolean     not null default false,
  locale           text        not null default 'en-US',
  updated_at       timestamptz not null default now(),
  constraint user_settings_disabled_rules_max
    check (pg_catalog.cardinality(disabled_rules) <= 200),
  constraint user_settings_disabled_rules_format
    check (public.researchly_rule_ids_valid(disabled_rules)),
  constraint user_settings_locale_known
    check (locale in ('en-US', 'en-GB'))
);

comment on table public.user_settings is
  'One row per user; absent row = defaults. Never holds document text. RLS: owner only.';

create table if not exists public.dictionary_words (
  user_id  uuid        not null
                       default auth.uid()
                       references auth.users (id) on delete cascade,
  word     text        not null,
  added_at timestamptz not null default now(),
  primary key (user_id, word),
  -- 1-64 characters, no whitespace and no control characters: a dictionary
  -- entry is one word, never a sentence or snippet of a document.
  constraint dictionary_words_word_shape
    check (pg_catalog.char_length(word) between 1 and 64
           and word !~ '[[:space:][:cntrl:]]')
);

comment on table public.dictionary_words is
  'User dictionary, at most 5,000 words per user (trigger). RLS: owner only.';

-- ---------------------------------------------------------------------------
-- updated_at is server-maintained: a client-sent value is overwritten.
-- ---------------------------------------------------------------------------
create or replace function public.researchly_set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at := pg_catalog.now();
  return new;
end;
$$;

drop trigger if exists user_settings_set_updated_at on public.user_settings;
create trigger user_settings_set_updated_at
  before insert or update on public.user_settings
  for each row execute function public.researchly_set_updated_at();

-- ---------------------------------------------------------------------------
-- 5,000-word cap per user.
--
-- SECURITY INVOKER on purpose: under RLS the inserting user can count their
-- own rows, and only their own, which is exactly the set the cap is about. A
-- SECURITY DEFINER function would run as the table owner and could see every
-- user's rows; we do not need that power, so we do not take it.
--
-- If someone tries to insert a row for another user, the count sees none of
-- that user's rows (RLS) so the trigger passes, and the INSERT policy's
-- WITH CHECK then rejects the row. Nothing leaks either way.
--
-- The advisory lock serialises concurrent inserts for the same user, so two
-- requests at 4,999 cannot both pass (READ COMMITTED, as PostgREST uses: the
-- count after the lock sees the other transaction's committed row).
-- Re-adding a word the user already has is not counted against the cap; it
-- proceeds to the primary key, so `on conflict do nothing` stays a no-op.
-- ---------------------------------------------------------------------------
create or replace function public.researchly_dictionary_cap()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('researchly.dictionary_words:' || new.user_id::text, 0));

  if exists (select 1 from public.dictionary_words d
             where d.user_id = new.user_id and d.word = new.word) then
    return new;
  end if;

  if (select pg_catalog.count(*) from public.dictionary_words d
      where d.user_id = new.user_id) >= 5000 then
    raise exception 'dictionary is full (5000 words)'
      using errcode = 'check_violation',
            hint = 'Remove a word from your dictionary before adding another.';
  end if;

  return new;
end;
$$;

drop trigger if exists dictionary_words_cap on public.dictionary_words;
create trigger dictionary_words_cap
  before insert on public.dictionary_words
  for each row execute function public.researchly_dictionary_cap();

-- ---------------------------------------------------------------------------
-- Row-Level Security.
--
-- ENABLE makes RLS apply to anon/authenticated. FORCE additionally applies it
-- to the table owner. In Supabase the owner is `postgres`, which clients
-- never act as (PostgREST switches to anon/authenticated), so FORCE is not
-- needed for Q7. We set it anyway as defence in depth: a future function that
-- runs as the owner (SECURITY DEFINER) cannot quietly read every user's rows
-- unless its owner also holds BYPASSRLS. It costs nothing: foreign-key
-- cascades (account deletion) are exempt from FORCE, and nothing here runs
-- as the owner.
-- ---------------------------------------------------------------------------
alter table public.user_settings    enable row level security;
alter table public.user_settings    force  row level security;
alter table public.dictionary_words enable row level security;
alter table public.dictionary_words force  row level security;

-- One policy per command, for `authenticated` only. `anon` has no policy and
-- (below) no privilege. `(select auth.uid())` is evaluated once per statement
-- (an initPlan), not once per row.
drop policy if exists user_settings_select_own on public.user_settings;
drop policy if exists user_settings_insert_own on public.user_settings;
drop policy if exists user_settings_update_own on public.user_settings;
drop policy if exists user_settings_delete_own on public.user_settings;

create policy user_settings_select_own on public.user_settings
  for select to authenticated
  using ((select auth.uid()) = user_id);
create policy user_settings_insert_own on public.user_settings
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy user_settings_update_own on public.user_settings
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy user_settings_delete_own on public.user_settings
  for delete to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists dictionary_words_select_own on public.dictionary_words;
drop policy if exists dictionary_words_insert_own on public.dictionary_words;
drop policy if exists dictionary_words_update_own on public.dictionary_words;
drop policy if exists dictionary_words_delete_own on public.dictionary_words;

create policy dictionary_words_select_own on public.dictionary_words
  for select to authenticated
  using ((select auth.uid()) = user_id);
create policy dictionary_words_insert_own on public.dictionary_words
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy dictionary_words_update_own on public.dictionary_words
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy dictionary_words_delete_own on public.dictionary_words
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- my_config(): everything the engine needs for the caller, in one round trip
-- (POST /rest/v1/rpc/my_config with the user's own token). SECURITY INVOKER,
-- so RLS still decides; the explicit user_id filters are belt and braces and
-- let the planner use the primary keys. Defaults when there is no settings
-- row. The dictionary is capped at 5,000 words, sorted.
-- ---------------------------------------------------------------------------
create or replace function public.my_config()
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  select pg_catalog.jsonb_build_object(
    'disabled_rules',   coalesce(pg_catalog.to_jsonb(s.disabled_rules), '[]'::jsonb),
    'show_preferences', coalesce(s.show_preferences, false),
    'locale',           coalesce(s.locale, 'en-US'),
    'dictionary',       coalesce(
      (select pg_catalog.jsonb_agg(w.word order by w.word)
       from (select d.word
             from public.dictionary_words d
             where d.user_id = (select auth.uid())
             order by d.word
             limit 5000) as w),
      '[]'::jsonb)
  )
  from (select 1) as one
  left join public.user_settings s
    on s.user_id = (select auth.uid())
$$;

-- ---------------------------------------------------------------------------
-- mute_rule / unmute_rule: change ONE rule atomically.
--
-- Reading disabled_rules in the browser, editing it and writing the whole
-- array back loses a change when two tabs or devices mute at the same time
-- (the later write overwrites the earlier one). These do the change in one
-- statement under the row lock instead. SECURITY INVOKER: RLS and the table
-- CHECKs (rule-id format, at most 200) still apply, and the row is always
-- the caller's own (auth.uid()), never one named by the client.
-- Both return the caller's resulting list.
-- ---------------------------------------------------------------------------
create or replace function public.mute_rule(rule_id text)
returns text[]
language sql
volatile
security invoker
set search_path = ''
as $$
  insert into public.user_settings as s (user_id, disabled_rules)
  values ((select auth.uid()), array[rule_id])
  on conflict (user_id) do update
    set disabled_rules = case
      when rule_id operator(pg_catalog.=) any (s.disabled_rules) then s.disabled_rules
      else s.disabled_rules operator(pg_catalog.||) rule_id
    end
  returning s.disabled_rules
$$;

create or replace function public.unmute_rule(rule_id text)
returns text[]
language sql
volatile
security invoker
set search_path = ''
as $$
  update public.user_settings as s
     set disabled_rules = pg_catalog.array_remove(s.disabled_rules, rule_id)
   where s.user_id = (select auth.uid())
  returning s.disabled_rules
$$;

-- ---------------------------------------------------------------------------
-- Privileges. Explicit, so this does not rely on Supabase's default
-- privileges (which grant ALL, including TRUNCATE, to anon and authenticated
-- on new public tables, and EXECUTE on new functions). TRUNCATE in particular
-- ignores RLS, so it must not be granted.
-- ---------------------------------------------------------------------------
revoke all on table public.user_settings, public.dictionary_words
  from public, anon, authenticated;
grant select, insert, update, delete
  on table public.user_settings, public.dictionary_words
  to authenticated;

revoke all on function public.my_config() from public, anon, authenticated;
grant execute on function public.my_config() to authenticated;
revoke all on function public.mute_rule(text), public.unmute_rule(text)
  from public, anon, authenticated;
grant execute on function public.mute_rule(text), public.unmute_rule(text)
  to authenticated;

-- Trigger functions are never called directly; triggers fire without an
-- EXECUTE check on the inserting role.
revoke all on function public.researchly_set_updated_at() from public, anon, authenticated;
revoke all on function public.researchly_dictionary_cap() from public, anon, authenticated;

-- The CHECK helper runs with the inserting role's privileges, so
-- `authenticated` needs EXECUTE. It is pure (no table access).
revoke all on function public.researchly_rule_ids_valid(text[]) from public, anon, authenticated;
grant execute on function public.researchly_rule_ids_valid(text[]) to authenticated;

commit;
