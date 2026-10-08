-- TEST SHIM ONLY. Never apply this to a Supabase project: Supabase already
-- has every object below, and its real versions must not be replaced.
--
-- The smallest stand-in for the parts of Supabase that
-- migrations/20261003120000_s2_settings.sql relies on, so the two-user test
-- (Q7) can run on plain PostgreSQL 16. Applied by a superuser to a fresh,
-- throwaway database. Roles are cluster-wide, so they are created only if
-- missing; everything else is per-database.
--
-- Fidelity notes (what matches Supabase, and what is simplified):
--   * anon / authenticated: NOLOGIN NOINHERIT, as in Supabase. PostgREST
--     (connected as `authenticator`) runs `set local role authenticated` and
--     sets `request.jwt.claims` from the verified JWT; the test does the same.
--   * auth.uid(): the same body as Supabase's current definition (legacy
--     `request.jwt.claim.sub` first, then `request.jwt.claims` ->> 'sub').
--   * auth.users: only the `id` column; the real table has many more.
--   * supabase_auth_admin owns auth.users, as in Supabase, so the cascade
--     test deletes a user the way GoTrue does: as a non-superuser.
--   * migration_owner stands in for Supabase's `postgres` role, which runs
--     the SQL Editor and owns what it creates. It is a non-superuser here
--     without BYPASSRLS (the strictest case). Whether Supabase's `postgres`
--     holds BYPASSRLS does not change any Q7 guarantee: clients never act as
--     the owner.
--   * Default privileges: Supabase grants ALL on new public tables,
--     functions and sequences to anon and authenticated. We reproduce that
--     so the test proves the migration's explicit revokes actually work.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    create role supabase_auth_admin nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'migration_owner') then
    create role migration_owner nologin noinherit nosuperuser nobypassrls;
  end if;
end
$$;

create schema auth authorization supabase_auth_admin;
grant usage on schema auth to anon, authenticated, migration_owner;

create table auth.users (
  id uuid primary key
);
alter table auth.users owner to supabase_auth_admin;
-- The migration's foreign keys need REFERENCES on auth.users.
grant references on auth.users to migration_owner;

create function auth.uid() returns uuid
language sql stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;
alter function auth.uid() owner to supabase_auth_admin;
-- EXECUTE on auth.uid() stays with PUBLIC (PostgreSQL's default), as in Supabase.

-- PostgreSQL 15+ no longer lets every role create in `public`.
grant usage, create on schema public to migration_owner;
grant usage on schema public to anon, authenticated;

alter default privileges for role migration_owner in schema public
  grant all on tables to anon, authenticated;
alter default privileges for role migration_owner in schema public
  grant all on functions to anon, authenticated;
alter default privileges for role migration_owner in schema public
  grant all on sequences to anon, authenticated;
