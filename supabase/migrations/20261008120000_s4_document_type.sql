-- Researchly S4: the article type (profile) a user checks as, saved with
-- the account so the web app and the Word add-in share it.
--
-- Apply AFTER 20261004120000_s3_mode.sql: Supabase dashboard -> SQL Editor
-- -> paste this whole file -> Run. Re-running is safe.
--
-- Adds one column holding one of nine words. No document text, as before.

begin;

alter table public.user_settings
  add column if not exists document_type text not null default 'auto';

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'user_settings_document_type_known'
      and conrelid = 'public.user_settings'::regclass
  ) then
    alter table public.user_settings
      add constraint user_settings_document_type_known
      check (document_type in ('auto', 'general', 'manuscript',
                               'thesis-chapter', 'abstract', 'commentary',
                               'policy-brief', 'grant',
                               'response-to-reviewers'));
  end if;
end
$$;

comment on column public.user_settings.document_type is
  'Article-type profile (researchly/profiles.py); auto guesses from the headings.';

-- my_config() gains "document_type"; otherwise as in the S3 migration.
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
    'document_type',    coalesce(s.document_type, 'auto'),
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
