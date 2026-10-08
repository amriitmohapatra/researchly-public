# Researchly for Word — tester guide

A writing assistant for scientific prose. It reads your document, and every
suggestion is typed, explained, and traceable to a source.

**Nothing you write leaves your computer.** There is no account, no cloud
service, and no AI model generating text. The checker runs as a small local
program on your own machine; the add-in talks to it over `localhost` only.
That is a deliberate design constraint, not a limitation we plan to remove —
publisher AI policies make it a compliance matter.

---

## What you need

- **macOS** with **Python 3.9 or newer** (`python3 --version` to check)
- **Microsoft Word** (365 / 2021 / 2019)
- ~10 minutes and about 500 MB of disk for the language models

Optional but recommended — the **grammar tier** (subject-verb agreement,
articles, verb forms) needs a Java runtime:

```bash
brew install openjdk@17
```

No symlinking or `PATH` editing is required: Researchly finds the runtime
even when Homebrew installs it "keg-only". If Java is missing, Researchly
**tells you the grammar tier is off** rather than quietly checking less than
it claims to.

---

## Install

```bash
cd Researchly-WordAddin-v0.8
bash word-addin/install-mac.sh
```

That installs the Python dependencies, downloads the spaCy language model
(~40 MB), and sideloads the add-in into Word.

## Run

```bash
bash start-server.sh
```

Leave that terminal window open while you write. Then in Word:
**Home → Researchly** (or Insert → My Add-ins → Researchly).

The first check is slow (the language model loads). Later ones are quick.
If you enabled the grammar tier, the *very* first check downloads
LanguageTool (~259 MB) once — after that it is cached.

---

## What you are looking at

Suggestions come in four kinds, and the distinction is the whole point:

| Kind | Meaning |
|---|---|
| **Correction** | Something is wrong — a typo, a grammar error |
| **Improvement** | Clearer if changed, but not wrong |
| **Convention** | How this field usually does it — never an error |
| **Preference** | A judgement call. Hidden unless you ask for them |

Advice is **section-aware**: passive voice is never flagged in Methods, and
a causal claim is questioned harder in Discussion than in Results.

Every card has a **Why?** — open it. If the reason does not convince you,
the suggestion is wrong for your sentence. Dismiss it and move on.

A status line tells you which checking engines are running. If it says a
tier is off, that is real information, not a glitch.

---

## What it does NOT check

Word only exposes body text to add-ins, so **footnotes, endnotes, headers,
footers, text boxes and comments are not checked**. The pane says so after
each run. Table cells are read but excluded from the prose statistics.

---

## Feedback I actually want

This is a precision tool: it is meant to stay quiet unless it has something
worth saying. So the most useful reports are:

1. **Wrong flags.** Anything it complained about that was fine as written.
   Paste the sentence and the rule id (e.g. `C303`). These matter most —
   a checker that cries wolf gets switched off.
2. **Misses.** Real errors it walked straight past.
3. **Unhelpful explanations.** A "Why?" that did not justify its suggestion.
4. **Anything that broke.** Especially if Apply changed the wrong text —
   tell me immediately, that is the one bug class that can damage a draft.

Rough edges you can ignore for now: muting a rule in Word does not yet sync
to the command-line tool, and there is no settings panel.

## If something goes wrong

| Symptom | Fix |
|---|---|
| Sidebar is blank | Your Word build may refuse plain-HTTP panes. Run `python3 word-addin/server.py --https` (see `word-addin/README.md`) |
| "local server not running" | The `start-server.sh` window was closed |
| Changes to the add-in do nothing | Quit Word **completely** (Cmd-Q) — it caches the pane |
| "Could not apply" | The text changed since the last check. Run Check again. Researchly refuses to guess rather than edit the wrong copy |
| Grammar suggestions never appear | Check the status line. It will say whether the tier is off and what to do |
