# apps/web — Researchly web surface (PLAN.md S1, S2, S3)

Paste text at a private URL and get explained, section-aware suggestions.
With accounts configured (S2), sign in by email link to check whole files
(.docx, .tex, Overleaf .zip, .md/.qmd/.Rmd, .txt) and keep muted rules and a
dictionary across devices. Next.js (App Router, TypeScript strict), no UI
kit, no analytics, no third-party scripts or fonts, no cookies.

## Run locally

```bash
cd apps/web
npm install
cp .env.example .env.local        # optional; the default is http://localhost:8080
npm run dev                        # http://localhost:3000
```

You need an engine to check against: `services/engine` on port 8080 (see its
README). Without one the page still works and shows the "could not reach the
checking engine" state.

| Script | What it does |
|---|---|
| `npm run dev` | Dev server on :3000 |
| `npm run build` / `npm start` | Production build / serve on :3000 |
| `npm run lint` | ESLint (Next + a11y rules, no-innerHTML) **and** `scripts/check-boundary.mjs` |
| `npm run typecheck` | `tsc --noEmit` (strict, includes the contract package) |
| `npm test` | Vitest unit tests (`tests/unit`) |
| `npm run test:e2e` | Playwright against two production builds, engine and Supabase mocked: project `chromium` (S1 build, no Supabase, :3100) and project `accounts` (with Supabase, :3101, `e2e/accounts*.spec.ts`) |
| `npm run screenshots` | Design screenshots (`SHOTS_DIR=…` to choose where) |

Playwright is pinned to 1.56.1 to match the pre-installed Chromium; set
`PLAYWRIGHT_BROWSERS_PATH` if your browsers live elsewhere.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_ENGINE_URL` | `http://localhost:8080` | Engine base URL. Inlined at **build** time; also in the CSP `connect-src`. A malformed value fails the build. |
| `NEXT_PUBLIC_SUPABASE_URL` | unset | S2 accounts. `https://<ref>.supabase.co` (or `http(s)://localhost:<port>` for a local Supabase). Added to `connect-src` only when both Supabase values are set. Anything else fails the build. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | unset | `sb_publishable_…`. Public by design (RLS protects the data). A secret key (`sb_secret_…`) fails the build. |

With either Supabase value unset the site is the S1 site: no sign-in UI, no
upload, no `/settings` (404), and supabase-js is never loaded.

Telemetry is disabled in the npm scripts (`NEXT_TELEMETRY_DISABLED=1`).

## How it talks to the engine

The browser calls `POST ${NEXT_PUBLIC_ENGINE_URL}/v1/analyze` directly, from
`lib/engine.ts` (the only module that sends text). Request and response
types come from the committed contract, `@researchly/contract` →
`../../packages/contract/src` (generated from the engine's OpenAPI; never
hand-copied). `next.config.ts` sets `turbopack.root` to the monorepo root so
the contract compiles as first-party source.

- **Offsets**: the engine's spans are Python string indices (Unicode code
  points); JavaScript strings are UTF-16. `lib/segments.ts` converts them,
  so highlights stay correct after emoji or characters like 𝑅.
- **Errors**: 413/429/400/422/500 and network failures map to plain-language
  messages (`lib/errors.ts`). 500s show the `request_id` to quote. The text
  in the editor is never cleared on failure.
- **Health**: a degraded grammar tier (or any tier in `error`/`unstarted`)
  gets a calm banner with the engine's detail and remedy. The learned `gec`
  tier being absent is normal and not shown.
- **Rule scopes**: after the first results the page asks `GET /v1/rules`
  once (no text) so the section view knows which rules read the whole
  document (`lib/scope.ts`); without a registry the engine's known
  document-wide ids stand in.
- **CORS**: the engine must allow this site's origin, and should expose
  `Retry-After` and `X-Request-ID` (`Access-Control-Expose-Headers`).

## The Word add-in's taskpane (`/word`, S3)

Word loads `https://<site>/word` in its sidebar (manifests in
`apps/word-addin/`; owner steps in its README, "Hosted add-in (S3)").

- **Office.js** comes from Microsoft's CDN with a plain script tag
  (`app/word/layout.tsx`), between two tiny same-origin scripts
  (`public/word/office-guard.js`, `office-restore.js`) that keep
  `history.pushState/replaceState` alive, because office.js removes them in
  some hosts and Next.js's router needs them.
- **All Office.js calls** are in `lib/word/office.ts` (read paragraphs with
  style and table flag, find the paragraph the cursor is in for "Check this
  section", find a suggestion by `snippet` + `occurrence`, select, apply). Tests swap in `e2e/fake-office.ts`, which e2e serves at office.js's
  own URL. Before selecting or replacing, the paragraph is re-read and must
  still hold the flagged words at the recorded offsets, Word's search must
  count the snippet as the engine did, and (to apply) the found range's text
  must equal the snippet; otherwise nothing changes and the card says why.
  Tracked changes only with WordApi 1.4: setting `changeTrackingMode` on
  older Word silently fails the whole batch.
- **Engine**: `POST /v1/analyze-word` and `GET /v1/health` from
  `lib/engine.ts`, either to `NEXT_PUBLIC_ENGINE_URL` ("Researchly cloud",
  with the Bearer token when signed in) or to `http://localhost:3517`
  ("This computer": `apps/word-addin/server.py`, no token, but the account's
  muted rules are sent as `disabled_rules`).
- **Sign-in** by an emailed code (`signInWithOtp` then `verifyOtp`, 6 to 10
  digits), inside the pane. Draft/Revise is saved in `user_settings.mode`
  when signed in (migration `20261004120000_s3_mode.sql`), else in
  localStorage with the engine choice (`lib/prefs.ts`).
- **Headers**: `/word` has its own CSP (proxy.ts, `surface: "word"`):
  `script-src` adds `https://appsforoffice.microsoft.com` (and drops
  `'strict-dynamic'`, which would block office.js's parser-inserted
  scripts), `frame-ancestors` lists the Office web origins, `connect-src`
  adds `http://localhost:3517`, and there is no `upgrade-insecure-requests`
  (it would break the local engine). No `X-Frame-Options` on `/word`.
  Every other route's headers are unchanged (tests/unit/security.test.ts,
  e2e/word.spec.ts).

## Accounts (S2, docs/s2-design.md §5)

- **Browser only.** supabase-js is loaded by `lib/supabase.ts` alone (a
  dynamic import, `client-only`), with PKCE and `detectSessionInUrl`: the
  email link's code is exchanged in the browser. No route handler, server
  action or cookie is involved; `check-boundary.mjs` refuses supabase-js
  anywhere else and `@supabase/ssr` everywhere.
- **Engine calls** (`lib/engine.ts`) carry `Authorization: Bearer <access
  token>` when signed in. On 401 `unauthorized` the session is refreshed once
  and the call retried once; if it still fails the browser is signed out
  locally and the page says so (never a silent anonymous retry). 401
  `sign_in_required` shows a sign-in prompt in place of results; 503
  `auth_unavailable` is a retryable error.
- **Uploads** go to `POST {engine}/v1/analyze-file` as the raw file
  (`application/octet-stream`), name in `X-Researchly-Filename`
  (`encodeURIComponent`), options in `X-Researchly-Options`. Type and the
  25 MB cap are checked first, for usability only.
- **Settings** (`/settings`, `lib/account.ts`) read and write
  `user_settings` and `dictionary_words` straight from the browser. Inserts
  rely on the `user_id` default (`auth.uid()`); the only id the client ever
  sends is its own, as a filter on "delete my settings and dictionary".
- **Storage**: besides the format preference (and, in the Word taskpane,
  the engine choice and Draft/Revise), the only stored item is
  supabase-js's session (`sb-<ref>-auth-token`, plus its PKCE verifier while
  a link is pending). Never document text.

## Privacy boundary (ADR-02, ARCHITECTURE.md §5.3)

Document text goes from the browser straight to the engine. **The Next.js
server never receives it.** This is enforced, not just intended:

- No route handlers, API routes or server actions exist. `npm run lint` runs
  `scripts/check-boundary.mjs`, which fails on any of them, on network calls
  outside `lib/engine.ts`, on a proxy that reads request bodies, on
  `sessionStorage`/IndexedDB/cookies, and on any `localStorage` use outside
  `lib/prefs.ts`. The Word taskpane obeys the same rules: document text
  goes from Office.js straight to the chosen engine. `tests/unit/boundary.test.ts` proves the checker catches
  each case.
- `lib/engine.ts` imports `client-only`, so importing it from server code is a
  build error.
- The e2e suite asserts that the only non-GET traffic is to the engine, that
  no cookies are set, and that the only stored item is the format preference.
- Nothing about the document is persisted: no localStorage, sessionStorage
  or IndexedDB in S1. Only the chosen format is remembered (`lib/prefs.ts`).
- Text is rendered as text nodes only. `dangerouslySetInnerHTML`/`innerHTML`
  are lint errors.

## Security headers

- `next.config.ts`: `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Cross-Origin-Opener-Policy: same-origin`, a restrictive `Permissions-Policy`.
- `proxy.ts`: a per-request **Content-Security-Policy** with a fresh nonce —
  `script-src 'self' 'nonce-…' 'strict-dynamic'`, `style-src 'self' 'nonce-…'`,
  `connect-src 'self' <engine origin>`, `frame-ancestors 'none'`,
  `object-src 'none'`, `base-uri 'none'`. A nonce is needed because Next.js
  inlines its bootstrap scripts; without one the only alternative is
  `'unsafe-inline'`. As a result every route renders per request
  (`await connection()` in the root layout). Both files take their values
  from `lib/security.ts`.

## Deploy (Vercel)

`vercel.json` pins the function region to `sin1` (D3, Singapore). In the
Vercel project set **Root Directory** to `apps/web`, keep "Include files
outside the root directory" enabled (the contract lives in
`packages/contract`), and set `NEXT_PUBLIC_ENGINE_URL` to the engine's
HTTPS URL for each environment.

## Design

`DESIGN.md` is the design contract (hierarchy, type roles, colour, shape,
required states, what to reject). Check UI changes against it.

## Layout

```
app/            layout (dynamic, for CSP nonces), page (static chrome), globals.css,
                word/ (the Word add-in's taskpane, S3)
components/     Checker (form + state), ReadingKey (idle "how to read the
                feedback" key), Results, DocumentView, SuggestionCard,
                HealthBanner, MetricsPanel, CategoryIcon
components/word/ Taskpane, WordCard, CodeSignIn
lib/word/       office (every Office.js call), view (taskpane helpers)
lib/            engine (fetch), segments (offsets + highlight segmentation),
                categories, health, errors, validate, view, prefs, config, security
proxy.ts        CSP nonce
scripts/        check-boundary.mjs (confidentiality lint)
tests/unit/     Vitest
e2e/            Playwright specs, typed fixtures (`satisfies AnalyzeResponse`),
                fake-office.ts (Office.js stand-in), word*.spec.ts
```
