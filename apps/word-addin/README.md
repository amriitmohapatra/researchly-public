# Researchly for Word

Two add-ins live here:

- **Hosted (S3, the one to use):** `manifest.hosted.xml` / `manifest.json`.
  The sidebar is served over HTTPS by the web app
  (`https://researchly-chi.vercel.app/word`, code in `apps/web`) and checks
  with the hosted engine, or with this folder's `server.py` when you choose
  "This computer". See **Hosted add-in (S3)** below.
- **Local (maintenance only):** `manifest.xml` + `server.py` + `web/`, as
  described from "Requirements" on. It keeps working unchanged.

## Hosted add-in (S3)

```
Word sidebar  https://researchly-chi.vercel.app/word  (apps/web, Vercel)
     │ Office.js: paragraphs, styles, table flags
     ├── "Researchly cloud" ──▶ engine /v1/analyze-word (Cloud Run)
     └── "This computer"   ──▶ http://localhost:3517/v1/analyze-word (server.py)
```

Document text goes from Word straight to the engine you chose. It never
goes to Vercel. Nothing in the document changes unless you press **Apply in
document** on one card; that change is a tracked change wherever your Word
supports it (WordApi 1.4: Word 2021 / Microsoft 365), and a direct edit
(undo with Cmd-Z) otherwise.

### Owner steps (one time)

1. **Apply the S3 database change.** In Supabase, open **SQL Editor → New
   query**, paste `supabase/migrations/20261004120000_s3_mode.sql` (from
   `main`, **Copy raw file**), and **Run**. It adds the Draft/Revise column.
   Running it twice is harmless. Until it is applied, Draft/Revise is still
   remembered on each computer, and the pane says it could not be saved to
   the account.
2. **Give Supabase an email sender (custom SMTP).** Supabase only lets you
   edit email templates once the project sends mail through your own
   server, and its built-in sender only reaches members of your Supabase
   team (a few emails an hour), so this is needed before anyone else can
   sign in anyway. Free option, through Gmail:
   - Google Account → **Security** → turn on **2-Step Verification**.
   - Open <https://myaccount.google.com/apppasswords>, create an app
     password named "Supabase Researchly", copy the 16 letters.
   - Supabase → **Authentication → Emails → SMTP Settings** (or **Set up
     SMTP** on a template page) → enable custom SMTP: sender email = your
     Gmail address, sender name = `Researchly`, host = `smtp.gmail.com`,
     port = `587`, username = your Gmail address, password = the app
     password. Save.
   The app password goes into Supabase only (never into chat, the repo or
   an `.env`); revoke it at the same page if it ever leaks. Gmail sends up
   to about 500 emails a day, plenty for the beta.
3. **Put the sign-in code in the email.** Sign-in inside Word uses a code,
   because a link would open your browser, not Word. In Supabase,
   **Authentication → Emails → Templates → Magic Link**, add the code to
   the message body, for example (do the same in the **Confirm signup**
   template, which is what someone signing in for the first time receives):

   ```html
   <p>Your Researchly sign-in code: <strong>{{ .Token }}</strong></p>
   <p>Or follow this link to sign in on the website: <a href="{{ .ConfirmationURL }}">Sign in</a></p>
   ```

   Save. The code is 6 digits by default (**Authentication → Sign In /
   Providers → Email → Email OTP Length** can make it up to 10; the pane accepts 6 to 10).
4. **Let the engine accept the website.** The engine's
   `RESEARCHLY_ALLOWED_ORIGINS` must include `https://researchly-chi.vercel.app`
   (exactly; no trailing slash). It already does if you entered that address
   in **allowed_origins** when running **Deploy engine** (docs/deploy.md
   step 5). The taskpane is a page on the same site, so nothing else is
   needed.
5. **Deploy the website** as usual (merge to `main`; Vercel builds it).
   Check that `https://researchly-chi.vercel.app/word` opens: in a normal
   browser it says "Open Researchly from Word".

### Sideload on a Mac

1. In Terminal, from this folder: `bash install-mac.sh hosted`. (By hand:
   copy `manifest.hosted.xml` into
   `~/Library/Containers/com.microsoft.Word/Data/Documents/wef/`, creating
   the `wef` folder if it is missing.)
2. **Fully quit Word with Cmd-Q** (closing the window is not enough: Word
   caches add-ins), then reopen it and open a document.
3. **Home tab → Researchly.** If the button is not there: **Insert → Add-ins
   → My Add-ins** (or the Add-ins button) → **Developer Add-ins** →
   Researchly.
4. In the sidebar: **Check document**. Sign in from the top right (your
   email, then the code from the email) to keep muted rules, your
   dictionary and Draft/Revise in step with the website.

The local add-in (`manifest.xml`) has a different Id, so both can be
installed at once; it is named "Researchly (local)" and works only while
`server.py` runs. If the old copy of it (installed before 2026-10-04) is
still in `wef`, it shows as a second plain "Researchly": remove it, or
replace it with the current `manifest.xml`.

**If Researchly is listed but does not open:**
1. Keep only the add-in you want in the `wef` folder (above).
2. Quit Word (Cmd-Q) and clear Word's add-in cache: delete the *contents*
   of `~/Library/Containers/com.microsoft.Word/Data/Library/Caches/` and,
   if it exists,
   `~/Library/Containers/com.microsoft.Word/Data/Library/Application Support/Microsoft/Office/16.0/Wef/`.
3. Reopen Word and the document, then Researchly again.
4. Still nothing? Report what happens (nothing / blank panel / an error /
   the old panel) with a screenshot and **Word → About Word**.

`manifest.json` is the same add-in as a unified (JSON) manifest, for
Microsoft 365 deployment later (AppSource generates the XML for Mac Word
from it). Its package needs the two icons in `assets-hosted/` next to it.

### "This computer": check without sending anything

For text that must not leave your Mac (ADR-02 local mode):

1. Start the local engine: `python3.10 server.py` in this folder (it needs
   the same Python set-up as the CLI). Leave it running.
2. In the sidebar, open **Settings** (bottom) → **Checking engine** →
   **This computer**. The privacy line under **Check document** changes to
   "Checked on this computer. Nothing is sent over the network."
3. If it says "Researchly is not running on this computer", the server is
   not started (or not on port 3517).

The choice is remembered on this computer. Signed in, your muted rules are
sent along to the local engine; your sign-in token is not. The server
answers only pages from `https://researchly-chi.vercel.app` (and the web
app's dev server), and replies to the browser's private-network check that
lets an HTTPS page talk to `localhost`.

> **If "This computer" cannot connect although the server runs:** some
> Word builds' web views treat `http://localhost` from an HTTPS page as
> mixed content, and new Chrome-based views can ask for "local network
> access" permission first. Neither could be tried in Word itself before
> release. Tell us (Report a problem, at the bottom of the sidebar), and
> use the local add-in (`manifest.xml`) meanwhile.

### Reporting a problem

The sidebar's **Report a problem** link opens an email to the maintainer.
Describe what happened; please don't paste text from your document.

---

# The local add-in (maintenance only)

The Researchly checker inside Microsoft Word: a sidebar that reads your
document, sends it to a **local** server on your own computer (nothing is
ever uploaded), and shows typed, explainable, section-aware suggestions.

```
Word (taskpane sidebar)  ←Office JS→  your document
        │  paragraphs + styles
        ▼
http://localhost:3517  (server.py — Python, stdlib only)
        │
        ▼
researchly engine (spaCy rules, same as the CLI)
```

## Requirements

- Microsoft Word 2016 or later / Microsoft 365 (Mac or Windows)
- The prototype's Python environment already set up (spaCy + model)
- Internet is only needed to load Microsoft's `office.js` script; your
  document text never leaves the machine.

## Setup (Mac)

```bash
cd prototype/word-addin
bash install-mac.sh          # installs the manifest into Word's wef folder
python3 server.py            # keep running while you write
```

Then quit and reopen Word, open any document, and go to
**Insert → Add-ins dropdown → Developer Add-ins → Researchly**
(on some versions: **Insert → My Add-ins → Researchly**). The sidebar opens.

(Windows note: sideloading uses a shared-folder catalog instead of the wef
folder — see Microsoft's "sideload Office Add-ins" docs; everything else
here works the same.)

## Using it

- **Check document** — one full pass; suggestions appear as cards.
- **Re-check as I type** — polls for changes every few seconds and
  re-checks. Off by default: the tool follows the draft-quiet /
  revise-thorough philosophy, and a check-on-demand keeps your drafting
  flow yours.
- Each card: category color (correction / improvement / convention /
  preference), rule, section it fired in, the flagged text (click to jump
  there in the document), the one-line reason, and **Why?** for the full
  rationale from the writing guide.
- **Apply fix** (only on suggestions with a concrete replacement) applies
  it **as a tracked change** by default, so Word's own review workflow
  keeps you in control. Toggle off if you want direct edits.
- **Dismiss** hides one suggestion for the session. **Mute rule** turns a
  rule off persistently (stored in the add-in; "unmute all" link to reset).
- **Add to dictionary** (on spelling cards): teaches Researchly the word
  permanently — saved locally to `~/.researchly/dictionary.txt`, shared by
  every surface (Word, desktop hotkeys, VS Code, CLI).
- Suggestions with a deletion fix (e.g. filler phrases) show a **Delete
  phrase** button.
- **Show preferences** reveals the subjective tier (off by default).
- Sections come from your **Word heading styles** (Heading 1/2/…, Title) —
  use them and the section-aware rules (passive quiet in Methods,
  causal-verb checks in Results/Discussion) work exactly as in the CLI.
  Typed-but-unstyled headings like a lone "Methods" line are also caught.

## Troubleshooting

- **"local server not running"** in the sidebar → start `python3 server.py`
  and wait for "ready." (the first check loads the spaCy model).
- **Add-in not listed in Word** → re-run `install-mac.sh`, fully quit Word
  (Cmd-Q), reopen. Check the manifest landed in
  `~/Library/Containers/com.microsoft.Word/Data/Documents/wef/`.
- **Blank sidebar** → your Word version may refuse plain-HTTP localhost
  panes. Switch to HTTPS:
  1. `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"`
  2. Trust it once: `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain cert.pem`
  3. Edit `manifest.xml`: replace every `http://localhost:3517` with
     `https://localhost:3517`, re-run `install-mac.sh`, restart Word.
  4. Run `python3 server.py --https`.
- **"Could not apply"** on Apply fix → the text changed since the last
  check (e.g. auto-recheck raced your typing). Re-check and apply again —
  the add-in now also searches the whole document as a fallback if the
  paragraph moved.
- **Apply fix / tracked changes** → tracked-change application needs
  WordApi 1.4+ (Word 2021 / Microsoft 365). On older Word the toggle shows
  "(unavailable in this Word version)" and fixes apply as direct edits.
  (Historical note: before v0.5 an unsupported tracking call silently
  broke *every* apply — if Apply seemed dead, update to the current files
  and fully quit Word (Cmd-Q) to clear the cached taskpane.)
- **After updating the add-in's files** → restart `server.py` AND fully
  quit Word (Cmd-Q) before reopening; Word caches the taskpane.

## Design notes (why it works this way)

- **Local-first is the point.** Publisher AI policies (Elsevier, Wiley)
  restrict uploading unpublished manuscripts to external tools; a local
  server makes the privacy answer structural, not contractual.
- **On-demand by default, tracked changes for edits, no silent
  modifications, mute as a first-class action** — all direct applications
  of the interaction-design findings in `../../research/04` and the
  dogfooding report.
- The server is Python stdlib only; the pane is plain HTML/JS with
  Microsoft's office.js. No node toolchain, no build step.
