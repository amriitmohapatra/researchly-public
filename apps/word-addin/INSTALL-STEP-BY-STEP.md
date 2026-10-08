# Researchly for Word — step-by-step setup

Follow these in order. Every step says what you should see, so you can tell
whether it worked before moving on. Budget about 15 minutes, most of it
waiting for downloads.

Lines starting with `$` are commands to type into **Terminal**. Type the
part *after* the `$`, then press Return.

> Open Terminal: press `Cmd` + `Space`, type `Terminal`, press Return.

---

## Step 0 — Before you start

You need:

- a Mac
- **Microsoft Word** (365, 2021 or 2019)
- about **1 GB** of free disk space
- an internet connection for the downloads (after setup, nothing you write
  is ever sent anywhere)

---

## Step 1 — Check you have Python 3.9 or newer

```
$ python3 --version
```

**You should see** something like `Python 3.11.9`.

- If the number is **3.9 or higher** → go to Step 2.
- If it says **3.8 or lower**, or `command not found` → install Python from
  <https://www.python.org/downloads/macos/>, then close Terminal, open it
  again, and repeat this step.

---

## Step 2 — Unzip the package and go into it

Unzip `Researchly-WordAddin-v0.8.zip` (double-click it in Finder). You will
get a folder called `Researchly-WordAddin-v0.8`.

In Terminal, type `cd ` (with a space after it), then **drag the folder from
Finder into the Terminal window** and press Return:

```
$ cd /Users/you/Downloads/Researchly-WordAddin-v0.8
```

Check you are in the right place:

```
$ ls
```

**You should see** `README-FIRST.md`, `requirements.txt`, `researchly`,
`start-server.sh`, `word-addin`.

If you do not see those, you are in the wrong folder — repeat this step.

---

## Step 3 — Install Researchly

```
$ bash word-addin/install-mac.sh
```

This installs the Python libraries and downloads the language model
(about 40 MB). It takes 2–5 minutes and prints a lot of text — that is
normal.

**You should see**, near the end, a line confirming the model was
installed and the add-in was registered with Word.

If it stops with a permissions error, try:

```
$ pip3 install --user -r requirements.txt
$ python3 -m spacy download en_core_web_sm
$ bash word-addin/install-mac.sh
```

---

## Step 4 (optional but recommended) — Turn on grammar checking

Without this, Researchly still checks spelling, clarity, and scientific
writing conventions — but **not** grammar (subject-verb agreement, a/an,
verb forms). Researchly will clearly tell you the grammar tier is off, so
you are never left guessing.

To enable it you need Java. If you have [Homebrew](https://brew.sh):

```
$ brew install openjdk@17
```

**That is all.** Do not create symlinks or edit your `PATH` — Researchly
finds the runtime by itself, including Homebrew's "keg-only" installs.

To check it worked:

```
$ python3 -c "import sys; sys.path.insert(0,'.'); from researchly import health; print(health.summary_line(health.engine_status()))"
```

**You should see** a line that mentions `Grammar` **without** "off".

If you do not want Java, skip this step — everything else works.

---

## Step 5 — Start the Researchly server

```
$ bash start-server.sh
```

**You should see:**

```
Researchly server: http://localhost:3517/taskpane.html
Keep this running while you write in Word. Ctrl+C to stop.
loading spaCy model…
ready.
```

⚠️ **Leave this Terminal window open.** Closing it stops Researchly. To stop
it deliberately, click the window and press `Ctrl` + `C`.

If it says the address is already in use, Researchly is already running —
move on to Step 6.

---

## Step 6 — Open Researchly in Word

1. Open Word and open (or create) a document.
2. Look on the **Home** tab, at the right-hand end, for a **Researchly**
   button. Click it.
   - Not there? Go to **Insert → My Add-ins → Researchly**.
3. A panel opens on the right.

**You should see** at the top: *"local server connected · N rules · all
analysis on this computer"* in green.

If it says the server is not running, go back to Step 5.

---

## Step 7 — Run your first check

Click **Check document**.

The first check takes a few seconds (the language model is warming up). If
you enabled grammar in Step 4, the **very first** check also downloads
LanguageTool — about 259 MB, once only. It may look frozen for a few
minutes. It is not; let it finish.

**You should see** suggestion cards, and a row of coloured counts:
Corrections, Improvements, Conventions, Preferences.

---

## Step 8 — Read the results properly

This matters more than the setup.

| Card colour | Kind | What it means |
|---|---|---|
| Red | **Correction** | Something is wrong — a typo, a grammar error |
| Blue | **Improvement** | Clearer if changed, but not wrong |
| Amber | **Convention** | How this field usually does it. **Not an error** |
| Purple | **Preference** | A judgement call. Hidden unless you tick "show preferences" |

On every card:

- **Go to** — jumps to that place in your document
- **Apply fix** — makes the change (as a tracked change by default)
- **Add to dictionary** — on spelling cards, teaches Researchly your term
  permanently
- **Dismiss** — hides it for this session
- **Mute rule** — stops that rule entirely
- **Why?** — click it. This is the point of the tool. If the reason does not
  convince you for *your* sentence, the suggestion is wrong. Dismiss it.

Advice changes by section: passive voice is never flagged in Methods, and
claims are questioned harder in Discussion than in Results.

If a banner says a checking tier is off, that is **real information**, not a
glitch — it tells you exactly what is and is not being checked.

---

## Step 9 — When you are finished

Click the Terminal window running the server and press `Ctrl` + `C`.

To use Researchly again later, you only need **Step 5 and Step 6** —
installation is one-off.

---

## Things worth knowing

- **Nothing you write leaves your computer.** No account, no cloud, no AI
  writing your text for you. The checker is a program on your Mac and the
  panel talks to it over `localhost` only.
- **Footnotes, endnotes, headers, footers, text boxes and comments are not
  checked** — Word does not expose them to add-ins. The panel says so after
  every run.
- **If you change any Researchly file**, quit Word completely (`Cmd` + `Q`)
  and restart the server — Word caches the panel.

## If something goes wrong

| Symptom | What to do |
|---|---|
| Panel is blank/white | Your Word build may block plain-HTTP panels. Stop the server and run `python3 word-addin/server.py --https`, then see `word-addin/README.md` about trusting the certificate |
| "local server not running" | The Terminal window from Step 5 was closed. Repeat Step 5 |
| "Could not apply" | The text changed since the last check. Click **Check document** again. Researchly refuses to guess rather than risk editing the wrong copy of a repeated phrase |
| No grammar suggestions ever | Check the status banner. It will say whether the grammar tier is off and exactly how to fix it (Step 4) |
| Sidebar shows old content | Quit Word fully with `Cmd` + `Q` and reopen |

## What to send back

The most useful feedback, in order:

1. **Wrong flags** — anything it complained about that was fine as written.
   Paste the sentence and the rule id (like `C303`). These matter most; a
   checker that cries wolf gets switched off.
2. **Misses** — real errors it walked past.
3. **Unhelpful "Why?" text.**
4. **Anything that broke** — especially if **Apply changed the wrong text**.
   Tell me immediately; that is the one bug that can damage a draft.
