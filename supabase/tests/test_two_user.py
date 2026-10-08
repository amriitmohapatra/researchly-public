"""Q7 two-user test: user A can never read, create as, update or delete user
B's settings or dictionary, and `anon` can do nothing at all.

Runs the real migration on a plain PostgreSQL 16 with a minimal Supabase shim
(shim.sql). Each test acts the way PostgREST does for a request: one
transaction, `set local role authenticated` (or anon), and
`request.jwt.claims` holding the verified token's claims.

Needs a superuser DSN in RESEARCHLY_TEST_PG_DSN (a throwaway database is
created and dropped). Without it the module is skipped, unless
RESEARCHLY_REQUIRE_PG_TESTS=1 (set in CI), which turns the skip into a failure
so a misconfigured job cannot pass Q7 by running nothing.
"""

import contextlib
import json
import os
import pathlib
import threading
import time
import uuid

import pytest

DSN = os.environ.get("RESEARCHLY_TEST_PG_DSN", "")
if not DSN:
    if os.environ.get("RESEARCHLY_REQUIRE_PG_TESTS") == "1":
        raise RuntimeError(
            "RESEARCHLY_REQUIRE_PG_TESTS=1 but RESEARCHLY_TEST_PG_DSN is unset: "
            "the Q7 two-user test cannot run")
    pytest.skip(
        "RESEARCHLY_TEST_PG_DSN is not set; the Q7 two-user test needs a "
        "PostgreSQL 16 superuser DSN (see supabase/README.md)",
        allow_module_level=True)

import psycopg  # noqa: E402  (imported after the skip check on purpose)
from psycopg import errors, sql  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SHIM = HERE / "shim.sql"
# Every migration, applied in name (date) order, as the owner applies them.
MIGRATIONS = sorted((HERE.parent / "migrations").glob("*.sql"))

USER_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

TABLES = ("user_settings", "dictionary_words")
DEFAULT_CONFIG = {
    "disabled_rules": [],
    "show_preferences": False,
    "locale": "en-US",
    "mode": "revise",
    "document_type": "auto",
    "dictionary": [],
}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _apply_migration(conn):
    """Apply as the stand-in for Supabase's `postgres` role (a non-superuser)."""
    conn.execute("set role migration_owner")
    try:
        for migration in MIGRATIONS:
            conn.execute(migration.read_text(encoding="utf-8"))
    finally:
        conn.execute("reset role")


@pytest.fixture(scope="session")
def db_dsn():
    """A throwaway database with the shim and the migration applied."""
    name = "researchly_q7_" + uuid.uuid4().hex[:12]
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    try:
        dsn = make_conninfo(DSN, dbname=name)
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(SHIM.read_text(encoding="utf-8"))
            # Applied twice: the migration is meant to be re-runnable, so
            # every test below runs against the state a re-run leaves behind.
            _apply_migration(conn)
            _apply_migration(conn)
        yield dsn
    finally:
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute(sql.SQL("drop database if exists {} with (force)")
                          .format(sql.Identifier(name)))


@pytest.fixture(scope="session")
def db(db_dsn):
    with psycopg.connect(db_dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture
def pg(db):
    """A clean database with two users and no rows. Superuser connection."""
    db.execute("set session_replication_role = origin")
    db.execute("truncate public.user_settings, public.dictionary_words")
    db.execute("delete from auth.users")
    db.execute("insert into auth.users (id) values (%s), (%s)", (USER_A, USER_B))
    return db


@contextlib.contextmanager
def acting_as(conn, role, sub=None):
    """One PostgREST-style request: a transaction as `role` with JWT claims."""
    claims = {"role": role}
    if sub is not None:
        claims["sub"] = str(sub)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
            cur.execute("select set_config('request.jwt.claims', %s, true)",
                        (json.dumps(claims),))
            yield cur


def as_user(conn, user):
    return acting_as(conn, "authenticated", user)


def as_anon(conn):
    return acting_as(conn, "anon")


def seed(conn, user, rules=("S001",), show=True, locale="en-GB", words=("Stan",)):
    """Superuser seeding (bypasses RLS) so tests start from known rows."""
    conn.execute(
        "insert into public.user_settings (user_id, disabled_rules, show_preferences, locale)"
        " values (%s, %s, %s, %s)", (user, list(rules), show, locale))
    for w in words:
        conn.execute("insert into public.dictionary_words (user_id, word) values (%s, %s)",
                     (user, w))


def seed_words_fast(conn, user, n, prefix="w"):
    """Insert n words without firing triggers (session_replication_role=replica)."""
    conn.execute("set session_replication_role = replica")
    try:
        conn.execute(
            "insert into public.dictionary_words (user_id, word)"
            " select %s, %s || g from generate_series(1, %s) g", (user, prefix, n))
    finally:
        conn.execute("set session_replication_role = origin")


def snapshot(conn, user):
    """Everything stored for `user`, read as superuser (ignores RLS)."""
    s = conn.execute(
        "select disabled_rules, show_preferences, locale, updated_at"
        " from public.user_settings where user_id = %s", (user,)).fetchall()
    d = conn.execute(
        "select word, added_at from public.dictionary_words"
        " where user_id = %s order by word", (user,)).fetchall()
    return s, d


def my_config(cur):
    cur.execute("select public.my_config()")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Structure: RLS on, policies exactly as designed, privileges exact
# ---------------------------------------------------------------------------

def test_rls_enabled_and_forced_on_both_tables(pg):
    rows = pg.execute(
        "select relname, relrowsecurity, relforcerowsecurity from pg_class"
        " where oid in ('public.user_settings'::regclass, 'public.dictionary_words'::regclass)"
    ).fetchall()
    assert sorted(rows) == [("dictionary_words", True, True), ("user_settings", True, True)]


@pytest.mark.parametrize("table", TABLES)
def test_exactly_one_owner_policy_per_command_for_authenticated(pg, table):
    rows = pg.execute(
        "select cmd, permissive, roles::text[], qual, with_check from pg_policies"
        " where schemaname = 'public' and tablename = %s order by cmd", (table,)).fetchall()
    assert [r[0] for r in rows] == ["DELETE", "INSERT", "SELECT", "UPDATE"]
    own = "(( SELECT auth.uid() AS uid) = user_id)"
    for cmd, permissive, roles, qual, with_check in rows:
        assert permissive == "PERMISSIVE"
        assert roles == ["authenticated"], (cmd, roles)
        assert qual == (None if cmd == "INSERT" else own), (cmd, qual)
        assert with_check == (own if cmd in ("INSERT", "UPDATE") else None), (cmd, with_check)


@pytest.mark.parametrize("table", TABLES)
def test_table_privileges_are_exact(pg, table):
    """authenticated: exactly select/insert/update/delete. anon, PUBLIC: nothing.

    The shim reproduces Supabase's default privileges (ALL to anon and
    authenticated), so this proves the migration's revokes work. TRUNCATE
    would bypass RLS, so its absence matters most.
    """
    privs = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
    qualified = "public." + table
    for role in ("anon", "authenticated", "public"):
        granted = {
            p for p in privs
            if pg.execute("select has_table_privilege(%s, %s, %s)",
                          (role, qualified, p)).fetchone()[0]
        }
        expected = {"SELECT", "INSERT", "UPDATE", "DELETE"} if role == "authenticated" else set()
        assert granted == expected, (role, granted)
    acl = pg.execute(
        "select grantee, privilege_type from information_schema.role_table_grants"
        " where table_schema = 'public' and table_name = %s"
        " and grantee in ('anon', 'PUBLIC')", (table,)).fetchall()
    assert acl == []


def test_function_privileges_and_hardening(pg):
    rows = pg.execute(
        "select p.proname, p.prosecdef, p.proconfig,"
        " has_function_privilege('anon', p.oid, 'EXECUTE'),"
        " has_function_privilege('authenticated', p.oid, 'EXECUTE'),"
        " has_function_privilege('public', p.oid, 'EXECUTE')"
        " from pg_proc p join pg_namespace n on n.oid = p.pronamespace"
        " where n.nspname = 'public' order by p.proname").fetchall()
    by_name = {r[0]: r[1:] for r in rows}
    assert set(by_name) == {
        "my_config", "mute_rule", "unmute_rule", "researchly_dictionary_cap",
        "researchly_rule_ids_valid", "researchly_set_updated_at",
        "researchly_counts_valid", "researchly_progress_prune"}
    for name, (secdef, config, anon_x, auth_x, public_x) in by_name.items():
        assert secdef is False, name + " must be SECURITY INVOKER"
        assert config == ['search_path=""'], (name, config)
        assert anon_x is False and public_x is False, name
        assert auth_x is (name in ("my_config", "mute_rule", "unmute_rule",
                                   "researchly_rule_ids_valid",
                                   "researchly_counts_valid")), name


def test_no_trigger_on_auth_users_and_no_extra_tables(pg):
    assert pg.execute(
        "select count(*) from pg_trigger where tgrelid = 'auth.users'::regclass"
        " and not tgisinternal").fetchone()[0] == 0
    tables = pg.execute(
        "select tablename from pg_tables where schemaname = 'public' order by 1").fetchall()
    assert tables == [("dictionary_words",), ("progress_events",),
                      ("user_settings",)]


# ---------------------------------------------------------------------------
# Read isolation
# ---------------------------------------------------------------------------

def test_each_user_sees_only_their_own_rows(pg):
    seed(pg, USER_A, rules=("S001", "LT001"), show=True, locale="en-GB", words=("Stan", "brms"))
    seed(pg, USER_B, rules=("AB802",), show=False, locale="en-US", words=("NumPyro",))

    with as_user(pg, USER_A) as cur:
        cur.execute("select user_id, disabled_rules from public.user_settings")
        assert cur.fetchall() == [(USER_A, ["S001", "LT001"])]
        # Compared as sets: `order by word` follows the server's collation
        # (CI's en_US puts "brms" first, a C-locale server puts "Stan" first).
        cur.execute("select user_id, word from public.dictionary_words")
        assert set(cur.fetchall()) == {(USER_A, "Stan"), (USER_A, "brms")}
        # Asking for B's rows by id returns nothing, not an error.
        cur.execute("select count(*) from public.user_settings where user_id = %s", (USER_B,))
        assert cur.fetchone()[0] == 0
        cur.execute("select count(*) from public.dictionary_words where user_id = %s", (USER_B,))
        assert cur.fetchone()[0] == 0
        config = my_config(cur)
        assert sorted(config.pop("dictionary")) == ["Stan", "brms"]
        assert config == {
            "disabled_rules": ["S001", "LT001"], "show_preferences": True,
            "locale": "en-GB", "mode": "revise", "document_type": "auto"}

    with as_user(pg, USER_B) as cur:
        cur.execute("select user_id from public.user_settings")
        assert cur.fetchall() == [(USER_B,)]
        cur.execute("select user_id, word from public.dictionary_words")
        assert cur.fetchall() == [(USER_B, "NumPyro")]
        assert my_config(cur) == {
            "disabled_rules": ["AB802"], "show_preferences": False,
            "locale": "en-US", "mode": "revise", "document_type": "auto",
            "dictionary": ["NumPyro"]}


def test_authenticated_without_sub_sees_nothing_and_cannot_write(pg):
    """A token-less `authenticated` context must not fall open."""
    seed(pg, USER_A)
    with acting_as(pg, "authenticated") as cur:
        for t in TABLES:
            cur.execute(sql.SQL("select count(*) from public.{}").format(sql.Identifier(t)))
            assert cur.fetchone()[0] == 0
        assert my_config(cur) == DEFAULT_CONFIG
    # user_id defaults to auth.uid() = NULL: rejected (RLS fires before NOT NULL).
    with pytest.raises((errors.InsufficientPrivilege, errors.NotNullViolation)):
        with acting_as(pg, "authenticated") as cur:
            cur.execute("insert into public.dictionary_words (word) values ('x')")
    # Naming a user explicitly is rejected by the policy.
    for t in TABLES:
        with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
            with acting_as(pg, "authenticated") as cur:
                cur.execute(sql.SQL("insert into public.{} (user_id, word) values (%s, 'x')"
                                    if t == "dictionary_words" else
                                    "insert into public.{} (user_id) values (%s)")
                            .format(sql.Identifier(t)), (USER_A,))
    settings, words = snapshot(pg, USER_A)
    assert len(settings) == 1 and [w for w, _ in words] == ["Stan"]


# ---------------------------------------------------------------------------
# Create-as isolation
# ---------------------------------------------------------------------------

def test_a_cannot_insert_settings_as_b(pg):
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with as_user(pg, USER_A) as cur:
            cur.execute("insert into public.user_settings (user_id, locale) values (%s, 'en-GB')",
                        (USER_B,))
    assert snapshot(pg, USER_B) == ([], [])


def test_a_cannot_insert_dictionary_word_as_b(pg):
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with as_user(pg, USER_A) as cur:
            cur.execute("insert into public.dictionary_words (user_id, word) values (%s, 'x')",
                        (USER_B,))
    assert snapshot(pg, USER_B) == ([], [])


def test_a_upsert_cannot_overwrite_b_settings(pg):
    """PostgREST upserts are INSERT ... ON CONFLICT DO UPDATE; B's row exists."""
    seed(pg, USER_B)
    before = snapshot(pg, USER_B)
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with as_user(pg, USER_A) as cur:
            cur.execute(
                "insert into public.user_settings (user_id, disabled_rules) values (%s, '{S999}')"
                " on conflict (user_id) do update set disabled_rules = excluded.disabled_rules",
                (USER_B,))
    assert snapshot(pg, USER_B) == before


def test_a_upsert_cannot_touch_b_dictionary(pg):
    seed(pg, USER_B, words=("Stan",))
    before = snapshot(pg, USER_B)
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with as_user(pg, USER_A) as cur:
            cur.execute(
                "insert into public.dictionary_words (user_id, word) values (%s, 'Stan')"
                " on conflict (user_id, word) do update set added_at = now()", (USER_B,))
    assert snapshot(pg, USER_B) == before


def test_insert_without_user_id_belongs_to_caller(pg):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (locale) values ('en-GB') returning user_id")
        assert cur.fetchone()[0] == USER_A
        cur.execute("insert into public.dictionary_words (word) values ('Stan') returning user_id")
        assert cur.fetchone()[0] == USER_A


# ---------------------------------------------------------------------------
# Update / delete isolation (verified afterwards as B)
# ---------------------------------------------------------------------------

def _b_view(pg):
    with as_user(pg, USER_B) as cur:
        cur.execute("select disabled_rules, show_preferences, locale from public.user_settings")
        settings = cur.fetchall()
        cur.execute("select word from public.dictionary_words order by word")
        words = cur.fetchall()
        config = my_config(cur)
    return settings, words, config


def test_a_update_of_b_rows_affects_nothing(pg):
    seed(pg, USER_A)
    seed(pg, USER_B, rules=("AB802",), show=False, locale="en-US", words=("NumPyro",))
    b_before, raw_before = _b_view(pg), snapshot(pg, USER_B)

    with as_user(pg, USER_A) as cur:
        cur.execute("update public.user_settings set disabled_rules = '{S999}', locale = 'en-GB'"
                    " where user_id = %s", (USER_B,))
        assert cur.rowcount == 0
        cur.execute("update public.dictionary_words set word = 'hacked' where user_id = %s",
                    (USER_B,))
        assert cur.rowcount == 0
        # An unfiltered update touches only A's own rows.
        cur.execute("update public.user_settings set locale = 'en-US'")
        assert cur.rowcount == 1
        cur.execute("update public.dictionary_words set word = word || '2'")
        assert cur.rowcount == 1

    assert _b_view(pg) == b_before
    assert snapshot(pg, USER_B) == raw_before


def test_a_delete_of_b_rows_affects_nothing(pg):
    seed(pg, USER_A)
    seed(pg, USER_B, words=("NumPyro", "Stan"))
    b_before, raw_before = _b_view(pg), snapshot(pg, USER_B)

    with as_user(pg, USER_A) as cur:
        cur.execute("delete from public.user_settings where user_id = %s", (USER_B,))
        assert cur.rowcount == 0
        cur.execute("delete from public.dictionary_words where user_id = %s", (USER_B,))
        assert cur.rowcount == 0
        # "Delete my settings and dictionary" (unfiltered) removes only A's rows.
        cur.execute("delete from public.user_settings")
        assert cur.rowcount == 1
        cur.execute("delete from public.dictionary_words")
        assert cur.rowcount == 1

    assert _b_view(pg) == b_before
    assert snapshot(pg, USER_B) == raw_before
    assert snapshot(pg, USER_A) == ([], [])


@pytest.mark.parametrize("table", TABLES)
def test_a_cannot_give_own_row_to_b(pg, table):
    seed(pg, USER_A)
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with as_user(pg, USER_A) as cur:
            cur.execute(sql.SQL("update public.{} set user_id = %s").format(sql.Identifier(table)),
                        (USER_B,))
    assert snapshot(pg, USER_B) == ([], [])
    assert len(snapshot(pg, USER_A)[0]) == 1


@pytest.mark.parametrize("table", TABLES)
def test_a_cannot_take_b_row(pg, table):
    seed(pg, USER_B)
    before = snapshot(pg, USER_B)
    with as_user(pg, USER_A) as cur:
        cur.execute(sql.SQL("update public.{} set user_id = %s where user_id = %s")
                    .format(sql.Identifier(table)), (USER_A, USER_B))
        assert cur.rowcount == 0
    assert snapshot(pg, USER_B) == before


@pytest.mark.parametrize("table", TABLES)
def test_authenticated_cannot_truncate(pg, table):
    """TRUNCATE ignores RLS; it must not be granted."""
    seed(pg, USER_B)
    with pytest.raises(errors.InsufficientPrivilege, match="permission denied"):
        with as_user(pg, USER_A) as cur:
            cur.execute(sql.SQL("truncate public.{}").format(sql.Identifier(table)))
    assert snapshot(pg, USER_B)[0] != []


# ---------------------------------------------------------------------------
# anon: nothing at all
# ---------------------------------------------------------------------------

ANON_STATEMENTS = [
    ("select", "select * from public.{t}"),
    ("insert", "insert into public.{t} (user_id) values ('" + str(USER_B) + "')"),
    ("update", "update public.{t} set user_id = user_id"),
    ("delete", "delete from public.{t}"),
    ("truncate", "truncate public.{t}"),
]


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("label,stmt", ANON_STATEMENTS, ids=[s[0] for s in ANON_STATEMENTS])
def test_anon_is_denied(pg, table, label, stmt):
    seed(pg, USER_B)
    before = snapshot(pg, USER_B)
    # Even an anon request that somehow carried B's sub must get nothing.
    for sub in (None, USER_B):
        with pytest.raises(errors.InsufficientPrivilege, match="permission denied"):
            with acting_as(pg, "anon", sub) as cur:
                cur.execute(stmt.format(t=table))
    assert snapshot(pg, USER_B) == before


def test_anon_cannot_execute_my_config(pg):
    seed(pg, USER_B)
    for sub in (None, USER_B):
        with pytest.raises(errors.InsufficientPrivilege, match="permission denied"):
            with acting_as(pg, "anon", sub) as cur:
                my_config(cur)


# ---------------------------------------------------------------------------
# my_config()
# ---------------------------------------------------------------------------

def test_my_config_defaults_without_settings_row(pg):
    seed(pg, USER_B)  # B has rows; A has none
    with as_user(pg, USER_A) as cur:
        assert my_config(cur) == DEFAULT_CONFIG


def test_my_config_has_dictionary_without_settings_row(pg):
    pg.execute("insert into public.dictionary_words (user_id, word) values (%s, 'Stan')", (USER_A,))
    with as_user(pg, USER_A) as cur:
        assert my_config(cur) == dict(DEFAULT_CONFIG, dictionary=["Stan"])


def test_my_config_caps_dictionary_at_5000(pg):
    seed_words_fast(pg, USER_A, 5003)  # only reachable by bypassing the trigger
    with as_user(pg, USER_A) as cur:
        assert len(my_config(cur)["dictionary"]) == 5000


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

def _set_rules(pg, rules):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (disabled_rules) values (%s)", (rules,))


def test_200_rules_accepted_201_rejected(pg):
    _set_rules(pg, ["S%d" % i for i in range(1, 201)])
    pg.execute("delete from public.user_settings")
    with pytest.raises(errors.CheckViolation, match="disabled_rules_max"):
        _set_rules(pg, ["S%d" % i for i in range(1, 202)])


@pytest.mark.parametrize("good", ["S001", "LT001", "AB802", "ABCD1234", "X1"])
def test_good_rule_ids_accepted(pg, good):
    _set_rules(pg, [good])


@pytest.mark.parametrize("bad", [
    "s001", "S", "001", "ABCDE1", "S00001", "S001 ", " S001", "S-001", "",
    "S001\n", "S001;drop", "Ｓ001", None])
def test_bad_rule_ids_rejected(pg, bad):
    with pytest.raises(errors.CheckViolation, match="disabled_rules_format"):
        _set_rules(pg, ["S001", bad])


@pytest.mark.parametrize("bad", ["en", "fr-FR", "EN-US", "en_US", ""])
def test_bad_locale_rejected(pg, bad):
    with pytest.raises(errors.CheckViolation, match="locale_known"):
        with as_user(pg, USER_A) as cur:
            cur.execute("insert into public.user_settings (locale) values (%s)", (bad,))


def test_locale_cannot_be_updated_to_bad_value(pg):
    seed(pg, USER_A)
    with pytest.raises(errors.CheckViolation, match="locale_known"):
        with as_user(pg, USER_A) as cur:
            cur.execute("update public.user_settings set locale = 'de-DE'")


def _add_word(pg, word, user=USER_A):
    with as_user(pg, user) as cur:
        cur.execute("insert into public.dictionary_words (word) values (%s)", (word,))


@pytest.mark.parametrize("bad", [
    "two words", "tab\there", "new\nline", " lead", "trail ", "", "x" * 65, "bell\x07"])
def test_bad_dictionary_words_rejected(pg, bad):
    with pytest.raises(errors.CheckViolation, match="word_shape"):
        _add_word(pg, bad)


@pytest.mark.parametrize("good", ["x", "x" * 64, "Stan", "COVID-19", "naïve", "R₀"])
def test_good_dictionary_words_accepted(pg, good):
    _add_word(pg, good)


def test_updated_at_is_server_maintained(pg):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (updated_at) values ('2000-01-01')"
                    " returning updated_at")
        first = cur.fetchone()[0]
    assert first.year > 2000
    time.sleep(0.01)
    with as_user(pg, USER_A) as cur:
        cur.execute("update public.user_settings set locale = 'en-GB',"
                    " updated_at = '2000-01-01' returning updated_at")
        second = cur.fetchone()[0]
    assert second > first


# ---------------------------------------------------------------------------
# 5,000-word cap
# ---------------------------------------------------------------------------

def test_dictionary_cap_through_rls_path(pg):
    """A fills the dictionary in one request as `authenticated` (trigger runs
    under RLS and sees rows earlier in the same statement); word 5,001 fails."""
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.dictionary_words (word)"
                    " select 'w' || g from generate_series(1, 5000) g")
        assert cur.rowcount == 5000
    with pytest.raises(errors.CheckViolation, match="dictionary is full"):
        _add_word(pg, "one-too-many")
    assert pg.execute("select count(*) from public.dictionary_words where user_id = %s",
                      (USER_A,)).fetchone()[0] == 5000


def test_dictionary_cap_boundary(pg):
    seed_words_fast(pg, USER_A, 4999)
    _add_word(pg, "the5000th")
    with pytest.raises(errors.CheckViolation, match="dictionary is full"):
        _add_word(pg, "the5001st")


def test_cap_counts_rows_within_one_multi_row_insert(pg):
    seed_words_fast(pg, USER_A, 4998)
    with pytest.raises(errors.CheckViolation, match="dictionary is full"):
        with as_user(pg, USER_A) as cur:
            cur.execute("insert into public.dictionary_words (word) values ('a1'), ('a2'), ('a3')")
    assert pg.execute("select count(*) from public.dictionary_words where user_id = %s",
                      (USER_A,)).fetchone()[0] == 4998


def test_cap_holds_under_concurrent_inserts(pg, db_dsn):
    """Two requests at 4,999 words: the second waits for the first (advisory
    lock), then sees 5,000 committed rows and is rejected. Without the lock
    both would pass and the user would end with 5,001."""
    seed_words_fast(pg, USER_A, 4999)
    outcome = {}

    with psycopg.connect(db_dsn, autocommit=True) as c1, \
            psycopg.connect(db_dsn, autocommit=True) as c2:

        def second_request():
            try:
                with as_user(c2, USER_A) as cur2:
                    cur2.execute("set local lock_timeout = '20s'")
                    cur2.execute("insert into public.dictionary_words (word) values ('second')")
                outcome["result"] = "inserted"
            except psycopg.Error as exc:
                outcome["result"] = exc

        with contextlib.ExitStack() as first:
            cur1 = first.enter_context(as_user(c1, USER_A))
            cur1.execute("insert into public.dictionary_words (word) values ('first')")
            worker = threading.Thread(target=second_request)
            worker.start()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and worker.is_alive():
                waiting = pg.execute(
                    "select count(*) from pg_stat_activity"
                    " where datname = current_database() and wait_event_type = 'Lock'"
                ).fetchone()[0]
                if waiting:
                    break
                time.sleep(0.02)
            assert worker.is_alive(), "second insert did not wait for the first"
        # leaving the ExitStack commits the first request
        worker.join(30)

    assert isinstance(outcome.get("result"), errors.CheckViolation), outcome
    assert pg.execute("select count(*) from public.dictionary_words where user_id = %s",
                      (USER_A,)).fetchone()[0] == 5000


def test_cap_is_per_user_b_can_add_when_a_is_full(pg):
    seed_words_fast(pg, USER_A, 5000)
    _add_word(pg, "NumPyro", user=USER_B)
    with as_user(pg, USER_B) as cur:
        assert my_config(cur)["dictionary"] == ["NumPyro"]


def test_readding_existing_word_at_cap_is_a_no_op_not_a_cap_error(pg):
    seed_words_fast(pg, USER_A, 5000)
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.dictionary_words (word) values ('w1')"
                    " on conflict (user_id, word) do nothing")
        assert cur.rowcount == 0
    with pytest.raises(errors.UniqueViolation):
        _add_word(pg, "w1")


def test_a_at_cap_cannot_probe_b_via_cap_trigger(pg):
    """Inserting as B while A is full still fails on RLS, not on B's count."""
    seed_words_fast(pg, USER_B, 5000)
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        with as_user(pg, USER_A) as cur:
            cur.execute("insert into public.dictionary_words (user_id, word) values (%s, 'x')",
                        (USER_B,))


# ---------------------------------------------------------------------------
# Account deletion and re-running the migration
# ---------------------------------------------------------------------------

def test_deleting_a_user_cascades_to_their_rows_only(pg):
    seed(pg, USER_A, words=("Stan", "brms"))
    seed(pg, USER_B, words=("NumPyro",))
    b_before = snapshot(pg, USER_B)
    # As GoTrue does it: the non-superuser that owns auth.users. The cascade
    # must work with FORCE ROW LEVEL SECURITY on the referencing tables.
    with pg.transaction():
        pg.execute("set local role supabase_auth_admin")
        pg.execute("delete from auth.users where id = %s", (USER_A,))
    assert snapshot(pg, USER_A) == ([], [])
    assert snapshot(pg, USER_B) == b_before


def test_rerunning_migration_keeps_data_and_policies(pg):
    seed(pg, USER_A)
    seed(pg, USER_B, words=("NumPyro",))
    before = snapshot(pg, USER_A), snapshot(pg, USER_B)
    _apply_migration(pg)
    assert (snapshot(pg, USER_A), snapshot(pg, USER_B)) == before
    assert pg.execute("select count(*) from pg_policies where schemaname = 'public'"
                      ).fetchone()[0] == 11
    with as_user(pg, USER_A) as cur:
        cur.execute("select count(*) from public.dictionary_words")
        assert cur.fetchone()[0] == 1



# ---------------------------------------------------------------------------
# mute_rule / unmute_rule: one rule at a time, atomically, own row only
# ---------------------------------------------------------------------------

def _mute(pg, user, rule):
    with as_user(pg, user) as cur:
        cur.execute("select public.mute_rule(%s)", (rule,))
        return cur.fetchone()[0]


def _unmute(pg, user, rule):
    with as_user(pg, user) as cur:
        cur.execute("select public.unmute_rule(%s)", (rule,))
        return cur.fetchone()[0]


def test_mute_creates_the_row_and_is_idempotent(pg):
    assert _mute(pg, USER_A, "W204") == ["W204"]
    assert _mute(pg, USER_A, "W204") == ["W204"]
    assert _mute(pg, USER_A, "G101") == ["W204", "G101"]
    assert _unmute(pg, USER_A, "W204") == ["G101"]
    assert _unmute(pg, USER_A, "W204") == ["G101"]
    # No settings row: unmute changes nothing and creates nothing.
    assert _unmute(pg, USER_B, "W204") is None
    assert pg.execute("select count(*) from public.user_settings where user_id = %s",
                      (USER_B,)).fetchone()[0] == 0


def test_mute_and_unmute_touch_only_the_callers_row(pg):
    seed(pg, USER_B, rules=("S001",))
    before = snapshot(pg, USER_B)
    _mute(pg, USER_A, "G101")
    _unmute(pg, USER_A, "S001")
    assert snapshot(pg, USER_B) == before


def test_mute_keeps_the_table_checks(pg):
    for bad in ("w204", "W204; drop", "", None):
        with pytest.raises(psycopg.Error):
            _mute(pg, USER_A, bad)
    _set_rules(pg, [f"R{i}" for i in range(200)])
    with pytest.raises(psycopg.errors.CheckViolation):
        _mute(pg, USER_A, "Z1")


def test_anon_cannot_mute(pg):
    for fn in ("mute_rule", "unmute_rule"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with as_anon(pg) as cur:
                cur.execute(sql.SQL("select public.{}('W204')").format(sql.Identifier(fn)))


def test_concurrent_mutes_are_both_kept(db_dsn, pg):
    """The bug this replaces: two tabs muting at once lost one of the mutes."""
    import threading
    seed(pg, USER_A, rules=(), words=())
    barrier = threading.Barrier(2)
    errors = []

    def worker(rule):
        try:
            with psycopg.connect(db_dsn) as conn:
                with as_user(conn, USER_A) as cur:
                    barrier.wait(timeout=10)
                    cur.execute("select public.mute_rule(%s)", (rule,))
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    for _ in range(10):
        pg.execute("update public.user_settings set disabled_rules = '{}' where user_id = %s",
                   (USER_A,))
        threads = [threading.Thread(target=worker, args=(r,)) for r in ("W204", "G101")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        rules = pg.execute("select disabled_rules from public.user_settings where user_id = %s",
                           (USER_A,)).fetchone()[0]
        assert sorted(rules) == ["G101", "W204"]


# ---------------------------------------------------------------------------
# S3: Draft / Revise mode
# ---------------------------------------------------------------------------

def test_mode_is_saved_per_user_and_checked(pg):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (mode) values ('draft')")
        assert my_config(cur)["mode"] == "draft"
    with as_user(pg, USER_B) as cur:
        assert my_config(cur)["mode"] == "revise"
    with pytest.raises(errors.CheckViolation):
        with as_user(pg, USER_A) as cur:
            cur.execute("update public.user_settings set mode = 'chapter'")


def test_document_type_is_saved_per_user_and_checked(pg):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (document_type) "
                    "values ('commentary')")
        assert my_config(cur)["document_type"] == "commentary"
    with as_user(pg, USER_B) as cur:
        assert my_config(cur)["document_type"] == "auto"
    with pytest.raises(errors.CheckViolation):
        with as_user(pg, USER_A) as cur:
            cur.execute("update public.user_settings set document_type = 'poem'")


# ---------------------------------------------------------------------------
# progress_events (S4): opt-in, counts only, owner only
# ---------------------------------------------------------------------------

def _record(cur, counts='{"G101": 2, "C303": 1}', words=1200):
    cur.execute("insert into public.progress_events (words, document_type, "
                "counts) values (%s, 'manuscript', %s::jsonb)", (words, counts))


def test_progress_is_refused_until_the_user_opts_in(pg):
    with pytest.raises(errors.InsufficientPrivilege):
        with as_user(pg, USER_A) as cur:
            _record(cur)
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (keep_progress) "
                    "values (false)")
    with pytest.raises(errors.InsufficientPrivilege):
        with as_user(pg, USER_A) as cur:
            _record(cur)
    with as_user(pg, USER_A) as cur:
        cur.execute("update public.user_settings set keep_progress = true")
        _record(cur)
        cur.execute("select words, counts from public.progress_events")
        assert cur.fetchall() == [(1200, {"G101": 2, "C303": 1})]


def test_progress_rows_are_private_and_never_edited(pg):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (keep_progress) "
                    "values (true)")
        _record(cur)
    with as_user(pg, USER_B) as cur:
        cur.execute("select count(*) from public.progress_events")
        assert cur.fetchone()[0] == 0
        cur.execute("delete from public.progress_events")
        assert cur.rowcount == 0
    with pytest.raises(errors.InsufficientPrivilege):
        with as_user(pg, USER_A) as cur:
            cur.execute("update public.progress_events set words = 1")
    with as_user(pg, USER_A) as cur:
        cur.execute("delete from public.progress_events")
        assert cur.rowcount == 1
    with pytest.raises(errors.InsufficientPrivilege):
        with as_anon(pg) as cur:
            cur.execute("select count(*) from public.progress_events")


@pytest.mark.parametrize("counts", [
    '{"G101": "the the"}',                 # text in a value
    '{"We fitted a model": 1}',            # text in a key
    '{"G101": -1}', '{"G101": 1.5}', '[1, 2]',
])
def test_progress_holds_rule_counts_and_nothing_else(pg, counts):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (keep_progress) "
                    "values (true)")
    with pytest.raises(errors.CheckViolation):
        with as_user(pg, USER_A) as cur:
            _record(cur, counts=counts)


def test_progress_keeps_the_newest_thousand(pg):
    with as_user(pg, USER_A) as cur:
        cur.execute("insert into public.user_settings (keep_progress) "
                    "values (true)")
        for i in range(1003):
            _record(cur, words=i)
        cur.execute("select count(*), min(words) from public.progress_events")
        assert cur.fetchone() == (1000, 3)


def test_my_config_does_not_expose_progress(pg):
    with as_user(pg, USER_A) as cur:
        assert "keep_progress" not in my_config(cur)

