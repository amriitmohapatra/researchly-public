-- Researchly S3: Draft / Revise mode (P1), saved with the account so the
-- web app and the Word add-in share it (a setting changed anywhere applies
-- everywhere).
--
-- Apply AFTER 20261003120000_s2_settings.sql: Supabase dashboard -> SQL
-- Editor -> paste this whole file -> Run. Re-running is safe.
--
-- Adds one column holding one of two words. No document text, as before.

begin;

alter table public.user_settings
  add column if not exists mode text not null default 'revise';

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'user_settings_mode_known'
      and conrelid = 'public.user_settings'::regclass
  ) then
    alter table public.user_settings
      add constraint user_settings_mode_known
      check (mode in ('draft', 'revise'));
  end if;
end
$$;

comment on column public.user_settings.mode is
  'draft: sentence-level checks only; revise: everything (P1).';

-- my_config() gains "mode"; otherwise as in the S2 migration.
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
    'mode',             coalesce(s.mode, 'revise'),
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

revoke all on function public.my_config() from public, anon, authenticated;
grant execute on function public.my_config() to authenticated;

commit;
