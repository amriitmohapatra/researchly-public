# supabase/

The database side of Researchly accounts (slice S2, `docs/s2-design.md` §2).
Two tables, both private to their owner by Row-Level Security, plus the test
that proves it.

| Path | What it is |
|---|---|
| `migrations/20261003120000_s2_settings.sql` | The schema: `user_settings`, `dictionary_words`, their RLS policies and grants, and `my_config()` (what the engine reads, with the user's own token). |
| `tests/shim.sql` | A stand-in for the parts of Supabase the migration needs (`auth.users`, `auth.uid()`, roles `anon` / `authenticated`, Supabase's default privileges), so the test runs on plain PostgreSQL 16. **Test only: never run it in Supabase.** |
| `tests/test_two_user.py` | The Q7 two-user test (ARCHITECTURE.md §3): user A can never read, create as, update or delete user B's settings or dictionary, and `anon` can do nothing. Also the limits (200 muted rules, valid rule ids and locales, 1–64-character words, 5,000 words per user) and account-deletion cascade. |
| `tests/run_local.sh` | Runs the test against a throwaway local PostgreSQL 16; no Docker. |

## What is stored, and what is not

| Table | Holds | Limits |
|---|---|---|
| `user_settings` | muted rule ids, show-preferences switch, locale, `updated_at` | ≤ 200 rule ids, each like `S001` / `LT001`; locale `en-US` or `en-GB` |
| `dictionary_words` | one word per row, `added_at` | 1–64 characters, no spaces; ≤ 5,000 per user |

No document text, ever. No `profiles`, usage or feedback tables yet: a table
that exists invites data into it, so each arrives with the feature that needs
it. No row is created at sign-up; a missing settings row means defaults.
Deleting a user in Supabase (Authentication → Users) deletes their rows.

## Applying the migration (owner, once per project)

1. Open the Supabase project → **SQL Editor** → **New query**.
2. Paste the whole of `migrations/20261003120000_s2_settings.sql`.
3. Click **Run**. It should finish with "Success. No rows returned".
4. Check: **Table Editor** shows `user_settings` and `dictionary_words`, each
   marked with RLS enabled; **Database → Policies** shows four policies
   on each, all for the `authenticated` role.

Running it again is safe (it recreates its policies, triggers and functions
and re-states its grants; rows are untouched). It does not change an existing
table's columns or limits: that needs a new, later-dated migration file.

## Running the tests

They need a PostgreSQL 16 server and a **superuser** connection string (the
test creates and drops its own throwaway database and the roles `anon`,
`authenticated`, `supabase_auth_admin`, `migration_owner`). Never point it at
Supabase or anything that matters.

```bash
# Easiest: a temporary local cluster, deleted afterwards (macOS: brew install postgresql@16)
python3.10 -m pip install pytest 'psycopg[binary]>=3.2,<4'
PG_BIN=$(brew --prefix postgresql@16)/bin supabase/tests/run_local.sh

# Or against a server you already run
RESEARCHLY_TEST_PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres \
  python3.10 -m pytest supabase/tests -q
```

Without `RESEARCHLY_TEST_PG_DSN` the tests are skipped with a reason. CI sets
`RESEARCHLY_REQUIRE_PG_TESTS=1`, which turns that skip into a failure, so a
misconfigured job cannot report Q7 green by running nothing.

## How the test acts like Supabase

Each step is one transaction that does what PostgREST does for an API call:
`set local role authenticated` (or `anon`) and puts the token's claims in
`request.jwt.claims`, which `auth.uid()` reads. The migration is applied as a
non-superuser owner (as Supabase's SQL Editor runs as `postgres`), twice, on
top of Supabase's default privileges (which grant everything to `anon` and
`authenticated`), so the test proves the migration's own revokes work rather
than relying on a bare Postgres being strict by default.
