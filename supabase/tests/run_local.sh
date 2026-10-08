#!/usr/bin/env bash
# Run the Q7 two-user test against a throwaway local PostgreSQL 16 cluster.
# No Docker needed. The cluster lives in a temp dir and is deleted on exit.
#
#   supabase/tests/run_local.sh            # all tests
#   supabase/tests/run_local.sh -k cap     # extra args go to pytest
#
# Env: PG_BIN (dir with initdb/pg_ctl; default from pg_config),
#      PYTHON (interpreter with pytest + psycopg; default python3.10).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
PYTHON=${PYTHON:-python3.10}
PG_BIN=${PG_BIN:-$(pg_config --bindir 2>/dev/null || echo /usr/lib/postgresql/16/bin)}

if [ "$(id -u)" = 0 ]; then
  echo "initdb refuses to run as root; run this as a normal user." >&2
  exit 2
fi
if [ ! -x "$PG_BIN/initdb" ]; then
  echo "initdb not found in $PG_BIN. Install PostgreSQL 16 (macOS: brew install postgresql@16)" >&2
  echo "and set PG_BIN, e.g. PG_BIN=\$(brew --prefix postgresql@16)/bin" >&2
  exit 2
fi
case "$("$PG_BIN/postgres" --version)" in
  *" 16."*) ;;
  *) echo "warning: $("$PG_BIN/postgres" --version); the CI job uses PostgreSQL 16" >&2 ;;
esac
"$PYTHON" -c "import psycopg, pytest" 2>/dev/null || {
  echo "$PYTHON lacks pytest/psycopg: $PYTHON -m pip install pytest 'psycopg[binary]>=3.2,<4'" >&2
  exit 2
}

tmp=$(mktemp -d "${TMPDIR:-/tmp}/researchly-q7.XXXXXX")
cleanup() {
  "$PG_BIN/pg_ctl" -D "$tmp/data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

port=$("$PYTHON" -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])")
"$PG_BIN/initdb" -D "$tmp/data" -U postgres --auth=trust -E UTF8 >/dev/null
"$PG_BIN/pg_ctl" -D "$tmp/data" -l "$tmp/server.log" -w \
  -o "-p $port -k '' -c listen_addresses=127.0.0.1" start >/dev/null

RESEARCHLY_TEST_PG_DSN="postgresql://postgres@127.0.0.1:$port/postgres" \
RESEARCHLY_REQUIRE_PG_TESTS=1 \
  "$PYTHON" -m pytest -q -p no:cacheprovider "$here" "$@"
