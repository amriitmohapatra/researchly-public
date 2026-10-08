# Researchly for macOS — step-by-step setup

Researchly checks your writing **in any app** — Word, Overleaf in a browser,
Mail, Notes, TextEdit. Select some text, press a key, get typed and explained
suggestions.

Follow these in order. Each step says what you should see. Budget about
10 minutes.

---

## Step 0 — Before you start

You need a Mac (Apple Silicon or Intel) and about **400 MB** of free space.
You do **not** need Python, Word, or any account — everything is inside the
app.

---

## Step 1 — Install the app

1. Unzip `Researchly-macOS-v0.8.zip` (double-click it).
2. Double-click **`Researchly.dmg`**.
3. A window opens showing the Researchly icon and an Applications shortcut.
   **Drag Researchly onto the Applications folder.**
4. Close the window and eject the disk image (click ⏏ next to "Researchly"
   in the Finder sidebar).

---

## Step 2 — Open it the first time (important)

The app is **not signed by Apple** — I am one researcher, not a company with
a developer certificate. macOS therefore refuses to open it by double-click
the first time. This is expected.

1. Open your **Applications** folder.
2. **Right-click** (or `Control`-click) **Researchly** → choose **Open**.
3. A dialog warns it is from an unidentified developer. Click **Open**.

You only have to do this once.

> **If macOS says the app is "damaged and can't be opened"**, that is the
> quarantine flag from downloading, not real damage. Open Terminal
> (`Cmd`+`Space`, type `Terminal`) and run:
>
> ```
> xattr -cr /Applications/Researchly.app
> ```
>
> Then try Step 2 again.

**You should see** a small Researchly icon appear in your **menu bar**, at
the top-right of the screen. There is no window and no Dock icon — that is
by design.

---

## Step 3 — Grant Accessibility permission

Researchly needs permission to read the text you have selected in other
apps. macOS will ask the first time you use a shortcut.

1. Click the Researchly menu-bar icon → **Check selection**, or just press
   `Cmd` + `Shift` + `R`.
2. macOS opens **System Settings → Privacy & Security → Accessibility**.
3. Find **Researchly** in the list and turn the switch **on**.
   - If it is not listed, click **+**, choose
     `Applications/Researchly.app`, and turn it on.
4. Quit Researchly (menu-bar icon → **Quit**) and open it again from
   Applications.

**Why:** this is the macOS API that lets Researchly read selected text. It
is also the only way any assistant can work across every app. Nothing is
transmitted anywhere — the permission is used locally and only when you
press a shortcut.

---

## Step 4 (optional) — Turn on grammar checking

Without this you still get spelling, clarity and scientific-writing checks —
but **not** grammar (subject-verb agreement, a/an, verb forms). The app
tells you plainly when the grammar tier is off, so you are never guessing.

To enable it you need Java. With [Homebrew](https://brew.sh):

```
brew install openjdk@17
```

**That is all** — no symlinks, no `PATH` editing. Researchly finds the
runtime by itself, including Homebrew's "keg-only" installs, and it works
even though the app is launched by Finder rather than from a terminal.

Quit and reopen Researchly afterwards. The **very first** check then
downloads LanguageTool (~259 MB, once). It may look stuck for a few
minutes; let it finish.

---

## Step 5 — Use it

Select text in **any** app, then:

| Shortcut | What it does |
|---|---|
| `Cmd` + `Shift` + `R` | **Check** the selection — typed, explained suggestions |
| `Cmd` + `Shift` + `P` | **Polish** the selection — a rule-composed rewrite with a diff |

A floating panel appears with the results.

For **Polish**, the panel shows exactly what changed (deletions in red,
insertions in green) and two buttons:

- **Replace selection** — pastes the rewrite back where you were
- **Copy rewrite** — puts it on your clipboard instead

Nothing is ever changed without you clicking one of those.

---

## Step 6 — Reading the results

| Colour | Kind | Meaning |
|---|---|---|
| Red | **Correction** | Something is wrong |
| Blue | **Improvement** | Clearer if changed, but not wrong |
| Amber | **Convention** | How the field usually does it. **Not an error** |
| Purple | **Preference** | A judgement call |

Each card has a **Why?** you can expand. If the reason does not convince you
for *your* sentence, the suggestion is wrong — ignore it.

If a banner says a checking tier is off, that is real information about what
is and is not being checked.

---

## Optional — live watching

Menu-bar icon → **Live watching (beta)** makes Researchly quietly check the
text field you are typing in and show a small count badge near it.

Honest limits: it works where apps expose their text through the macOS
Accessibility API. **Most browsers and Electron apps do not**, so the badge
simply stays hidden there. Very long documents are checked on their most
recent ~20,000 characters. It is off by default.

---

## Known limits

- **No underlines inside your document yet.** Results appear in the floating
  panel, not as squiggles under your text.
- **A few hardened apps** (password fields, secure terminals) block both the
  Accessibility API and synthetic keystrokes. Nothing can integrate there.
- **Shortcuts are fixed** at `Cmd`+`Shift`+`R` / `Cmd`+`Shift`+`P`. If they
  clash with another app, tell me — configurable shortcuts are planned.
- Very briefly, your clipboard may flicker when capturing a selection; it is
  restored straight afterwards.

## If something goes wrong

| Symptom | What to do |
|---|---|
| "damaged and can't be opened" | `xattr -cr /Applications/Researchly.app` — see Step 2 |
| Nothing happens on `Cmd`+`Shift`+`R` | Accessibility permission (Step 3). After granting it you must **quit and reopen** the app |
| Panel says "No selection" | Select the text first, then press the shortcut |
| The rewrite pasted in the wrong place | Click back into your document so the cursor is where you want it, then press Replace |
| No grammar suggestions ever | Check the banner — it says whether the tier is off and how to fix it (Step 4) |

## What to send back

1. **Wrong flags** — anything it complained about that was fine as written.
   Include the sentence and the rule id (like `C303`). These matter most.
2. **Misses** — real errors it walked past.
3. **Unhelpful "Why?" text.**
4. **Anything that broke** — especially if Replace put text in the wrong
   place. Tell me straight away.
