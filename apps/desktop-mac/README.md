# Researchly for macOS — Stage D1 (menu-bar assistant)

The Researchly engine in **every** app on your Mac: select text anywhere —
Word, a browser (Overleaf, Google Docs), Mail, Notes — press a hotkey, and
a floating panel shows typed suggestions or a Polish rewrite. "Replace
selection" pastes the rewrite straight back where you were typing.
Everything runs locally; nothing leaves the machine.

```
any app ── select text ──▶ ⌘⇧R check │ ⌘⇧P polish
                                 │
                    selection capture (Accessibility API,
                    clipboard fallback with auto-restore)
                                 │
                    researchly engine (same 33 rules as
                    the CLI / Word add-in / LSP)
                                 │
                    floating panel (suggestions or diff)
                                 │
              [Replace selection] pastes rewrite back
```

This is Stage D1 of the desktop roadmap (see
`../../docs/roadmap-rewrite-and-desktop.md`): the reliable foundation that
works everywhere. D2 (live watcher + badge) and D3 (true underlines in
apps that support them) build on this.

## Try it first from the terminal (5 minutes, recommended)

Running as a script first makes permissions and debugging much easier:

```bash
cd ~/Documents/Researchly/prototype/desktop-mac
pip3 install -r requirements-desktop.txt        # pyobjc (+py2app for later)
python3 researchly_app.py
```

1. An **R** appears in your menu bar. The engine warms up (~15 s).
2. macOS will prompt about **Accessibility** permission. Grant it to your
   **terminal app** (Terminal or iTerm) in System Settings → Privacy &
   Security → Accessibility — this is what lets Researchly read your
   selection and paste back. Restart the script after granting.
3. Go to any app, select a sentence, press **⌘⇧R**. The panel appears.
4. Select a clunky paragraph, press **⌘⇧P**, review the diff, click
   **Replace selection**.

Leave the terminal window open while you use it; Ctrl+C to quit (or Quit
from the menu-bar menu).

## Build the real app (.app and .dmg)

```bash
bash build_app.sh          # full standalone Researchly.app in dist/
bash make_dmg.sh           # → Researchly.dmg (drag to Applications)
```

- First launch of an unsigned app: **right-click → Open** (once).
- Grant Accessibility to **Researchly** (it prompts; the terminal grant
  doesn't carry over).
- If the full build fails on the spaCy/numpy bundling (py2app can be
  finicky — this is the step we may need to debug together):
  `bash build_app.sh --alias` builds a fast **alias-mode** app that links
  to this folder and your Python environment. For a personal tool this is
  effectively equivalent — it just isn't portable to another Mac.

## How selection capture works (and its honest limits)

1. **Accessibility API first**: reads the focused element's selected text
   directly — clean, no clipboard involvement. Works in most native apps.
2. **Clipboard fallback**: if AX fails (browsers and Electron apps often
   refuse), Researchly simulates ⌘C, reads the selection, and **restores
   your previous clipboard**. You may notice a brief clipboard blink.
3. **Replace selection** works by paste (⌘V) — the panel never steals
   focus, so the paste lands in the app you came from. In Word you may
   want tracked changes on (Review → Track Changes) before replacing.

Limits by design (documented in the roadmap): no inline underlines in
other apps yet (that's D3, and only apps that expose character geometry
will ever support it); a few hardened apps (some password fields, secure
terminals) block both AX and synthetic keys — nothing can integrate there.

## Troubleshooting (first-run checklist)

| Symptom | Likely cause / fix |
|---|---|
| Hotkeys do nothing | Accessibility not granted, or granted to the wrong app (terminal vs Researchly). Re-check System Settings, then restart the app. |
| "No selection" though text is selected | The app blocks AX *and* ⌘C simulation didn't land — try increasing the wait (report it; we tune the retry loop). |
| Panel appears but empty/white | WKWebView issue — run from terminal and send me the traceback. |
| ⌘⇧R conflicts with an app shortcut | Tell me — we'll make hotkeys configurable (planned). |
| Clipboard didn't restore | The 0.6 s restore raced a slow paste; report the app — we'll lengthen it. |
| Engine never becomes ready | Run `python3 -c "import spacy; spacy.load('en_core_web_sm')"` in the same Python — install if missing. |

When anything misbehaves: run from the terminal and copy me the output —
that's our debugging session.

## D2 — Live watching (beta, off by default)

Menu bar → **Live watching (beta)** turns on the focused-field watcher:
every ~2.5 s Researchly reads the text of the field you're typing in (via
the Accessibility API), re-checks it when it changes, and shows a small
floating **"R n"** badge near the field's top-right corner (n = suggestion
count). Click the badge to open the panel with the details. The badge
hides when there's nothing to flag.

- Off by default — the draft-quiet philosophy holds; turn it on for
  revision sessions.
- **Pause watching in current app** (menu) adds the frontmost app to a
  deny list (stored in `~/.researchly/desktop.json`).
- Honest limits: works where apps expose their text via Accessibility
  (native apps, TextEdit, Mail, Word largely); browsers and Electron apps
  usually don't — the badge simply stays hidden there (use ⌘⇧R instead).
  Very long documents are checked on their most recent ~20k characters.

## What's next (per roadmap)

- **D3**: true underline overlay for apps answering `AXBoundsForRange`
  (Word, native text views).
- **Windows (.exe)**: same stages via UI Automation + PyInstaller, after
  the Mac app is proven.
- Telemetry: the desktop app already logs shown/applied events (source
  `desktop`) into the same local file — `python -m researchly stats`
  covers all surfaces.

## Standalone installer (2026-08-14)

`bash build_installer.sh` produces `Researchly-0.8.dmg` AND
`Researchly-0.8.pkg` with everything inside: the py2app bundle plus a
pre-downloaded LanguageTool and a jlink-trimmed private JRE under
`Contents/Resources/vendor/`. Installed apps need no Python, no Java and
no first-run download — `health.find_java()` prefers the bundled JRE and
`rules_grammar` points language_tool_python at the bundled LanguageTool
(LTP_JAR_DIR_PATH). Build-machine prereqs: the pip deps + a JDK 17+
(for jlink). `build_app.sh` remains the small/dev build that relies on
system Java and first-run downloads.
