# S2 design — accounts, files, settings sync

Status: working design for slice S2 (PLAN.md), 2026-10-03. It refines
ARCHITECTURE.md §5–§9 where the build forced a concrete choice; each such
choice is marked **(refines §n)** and is folded into ARCHITECTURE.md when S2
closes.

## 1. What a student gets

- Sign in with an email link. Google sign-in follows when the owner sets up
  an OAuth client (optional; documented in `docs/deploy.md`).
- Upload `.docx`, `.tex`, an Overleaf `.zip`, `.md`/`.qmd`/`.Rmd` or `.txt`.
  The extracted text is shown read-only with the same highlights and cards
  as pasted text. They fix the source in Word or Overleaf.
- Mute a rule or add a word to their dictionary once; it applies on every
  device and, from S3, in the Word add-in.
- A settings page: muted rules (with each rule's why), dictionary words,
  show-preferences switch, "delete my settings and dictionary".

Anonymous visitors keep paste-only checking, capped at 1,500 words when the
deployment has accounts configured (§9 Abuse). With no accounts configured
(local development, or before the owner creates the Supabase project) the
engine behaves exactly as in S1.

## 2. Data model — collect only what S2 needs (refines §8)

Two tables, in `supabase/migrations/`. `profiles`, `usage_events`,
`feedback_events` and `documents` are **not** created in S2: nothing reads or
writes them yet, and a table that exists invites data into it. They arrive
with the feature that needs them (`/v1/feedback` in S3/S4).

| Table | Columns | Limits |
|---|---|---|
| `user_settings` | `user_id uuid PK → auth.users ON DELETE CASCADE`, `disabled_rules text[]`, `show_preferences bool`, `locale text`, `updated_at` | ≤ 200 rules, each matching `^[A-Z]{1,4}[0-9]{1,4}$`; locale in (en-US, en-GB) |
| `dictionary_words` | `user_id uuid → auth.users ON DELETE CASCADE`, `word text`, `added_at`; PK (user_id, word) | word 1–64 chars, no whitespace; ≤ 5,000 per user (trigger) |

- RLS on both, one policy per command (select/insert/update/delete),
  `to authenticated`, `using/with check ((select auth.uid()) = user_id)`.
- `anon` gets no privileges; `authenticated` gets exactly
  select/insert/update/delete. Grants are explicit so the migration does not
  rely on Supabase's default privileges.
- `public.my_config()` — `security invoker`, returns
  `{disabled_rules, show_preferences, locale, dictionary}` for the caller in
  one round trip. RLS still applies inside it.
- `public.mute_rule(rule_id)` / `public.unmute_rule(rule_id)` change one
  rule atomically (security invoker). The browser must not read-modify-write
  the whole list: two tabs muting at once would lose a change.
- No row is created at sign-up (no trigger on `auth.users`): a missing
  `user_settings` row means defaults; the web app upserts on first save.

**Two-user test (Q7):** `supabase/tests/` runs the migration on a plain
Postgres 16 with a minimal Supabase shim (`auth.users`, `auth.uid()` reading
`request.jwt.claims`, roles `anon`/`authenticated`), then proves user A
cannot read, insert as, update or delete user B's rows, and `anon` can do
nothing. CI runs it against a `postgres:16` service container.

## 3. How the engine learns who is asking (refines §5.2, §9)

- The browser sends `Authorization: Bearer <Supabase access token>`. No
  cookies; CORS stays `allow_credentials=False`.
- The engine verifies the token itself: signature against the project's JWKS
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, RS256/ES256; new
  Supabase projects use asymmetric signing keys), `iss ==
  {SUPABASE_URL}/auth/v1`, `aud == "authenticated"`, `exp`, and
  `role == "authenticated"`. `user_id` comes only from `sub`.
- It then calls `POST {SUPABASE_URL}/rest/v1/rpc/my_config` **with the
  user's own token** and the project's publishable key. The engine holds no
  service-role/secret key, so a bug in the engine cannot read another user's
  rows: RLS decides, not our code. (ARCHITECTURE.md §4 drew the engine
  reading Postgres directly; going through PostgREST with the caller's token
  is least privilege.)
- Failure handling:
  - bad, expired or wrong-project token → **401 `unauthorized`** (the web
    app refreshes the session and retries once; never silently anonymous);
  - JWKS unreachable → **503 `auth_unavailable`**;
  - settings fetch fails → the check still runs with defaults, and a health
    tier `account` reports `error` with a remedy (no silent tier).
- Precedence: signed-in requests use the stored settings; request
  `disabled_rules` are **added** to the stored ones and `show_preferences`
  is stored OR requested. Muting is the only thing a request can add.

## 4. Files (refines §5.1, ADR-04)

New endpoint `POST /v1/analyze-file`:

- Body: the raw file bytes, `Content-Type: application/octet-stream`.
- `X-Researchly-Filename`: the file's name, used only for its extension.
  **Never logged** (a filename like `chapter4_unpublished_trial.docx` is
  itself confidential). Not in the URL, because platforms log URLs.
- `X-Researchly-Options` (optional): JSON `AnalyzeOptions`.
- Signed-in only when accounts are configured (`401 sign_in_required`).
- Cap: `RESEARCHLY_MAX_UPLOAD_BYTES`, default 25 MiB (§6), checked before
  the body is read.

Raw bytes rather than multipart because Starlette spools multipart files
over 1 MB to a temporary file on disk, and the engine processes text in
memory only (ADR-02).

Response: `AnalyzeFileResponse` = every `AnalyzeResponse` field plus
`document`:

```jsonc
"document": {
  "filename": "chapter4.zip",          // echoed to the caller, never logged
  "format": "latex",                   // latex | docx | markdown | plain
  "text": "…",                         // what spans index into
  "segments": [{"path": "main.tex", "start": 0, "end": 812, "source_start": 0},
               {"path": "sections/methods.tex", "start": 812, "end": 4100, "source_start": 0}],
  "structure": [{"kind": "figure", "start": 1200, "end": 1460, "label": "fig:rt"}],
  "warnings": ["\\input{appendix} not found in the zip; skipped"]
}
```

### Adapters (`packages/core/researchly/ingest/`)

One entry point: `ingest.load_bytes(filename, data) -> Document`, raising
`ingest.IngestError(code, message)` with a user-safe message (never document
text). `Document` gains `segments`, `structure` and `warnings`.

| Input | Adapter | Notes |
|---|---|---|
| `.tex` | pylatexenc node walk → mask, keeping offsets 1:1 with the source | Replaces regex masking for LaTeX everywhere (CLI too). Never executes TeX. Headings from `\section` etc.; structure from `figure`, `table`, `equation`/`align`/`$$`, `\caption`, `\label`, `\cite`. Unparseable input falls back to the regex masker with a warning. |
| `.zip` (Overleaf) | find main file (`\documentclass`; prefer `main.tex`), expand `\input`/`\include`/`\subfile` in reading order into one text with `segments` | Path traversal (`../`, absolute), symlinks, nested zips, > 200 entries, > 50 MB uncompressed or ratio > 100 → `IngestError`. Cycles and depth > 10 stop with a warning. Only `.tex` read. |
| `.docx` | OOXML via `zipfile` + `defusedxml` | Paragraph styles → headings (as `from_word`); tables kept as table spans; tracked deletions ignored, insertions kept; comments, footnotes, headers ignored in S2. Figures (drawings), captions (`Caption` style) and equations (`m:oMath`) recorded as structure; equations masked. Same zip-bomb and entry limits. |
| `.md`, `.qmd`, `.Rmd`, `.txt` | existing maskers | UTF-8 (with BOM) only; other encodings → `IngestError`. |

**Offsets round-trip** for every adapter: a property test checks that for
every segment, `text[start:end]` equals the source file's
`[source_start : source_start + (end - start)]`, and that masking preserves
length.

## 5. Web (`apps/web`)

- `@supabase/supabase-js` in the browser only (PKCE; the email link's code
  is exchanged client-side). `check-boundary.mjs` still forbids route
  handlers and server actions: Next.js server code never sees text or
  tokens.
- CSP `connect-src` adds the Supabase origin. New public config:
  `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
  (both public by design; RLS protects the data). With either unset, the
  site runs as in S1 with no sign-in UI.
- Settings and dictionary are read and written by the browser directly in
  Supabase (they are not document text). The engine only reads them.

## 6. Owner steps (added to `docs/deploy.md` as step 8)

1. Create a Supabase project in Singapore (free plan).
2. Paste the migration into the SQL editor and run it.
3. Authentication → URL configuration: Site URL = the Vercel address;
   redirect URL = the same.
4. Copy the project URL and publishable key into Vercel (Config type) and
   into the engine deploy (`supabase_url`, `supabase_publishable_key`).

Supabase's built-in email sender only delivers to the project team's own
addresses, which suits a private beta; real users need custom SMTP (S6).
