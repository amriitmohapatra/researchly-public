# Windows smoke-test checklist — first real-hardware bring-up

`prototype/desktop-win/` has never run on real Windows. Treat it as a
scaffold until every box below is ticked on an actual machine (the macOS
D1 bring-up needed one traceback-driven session; expect the same). Work
through the sections **in order** — each one assumes the previous passed.
Record failures verbatim (full traceback + Windows version + Python
version) so the fix session has evidence, not memories.

## 0. Environment

- [ ] Windows version noted (10 or 11; WebView2 is preinstalled on 11
      only — on 10, install the Edge WebView2 Evergreen runtime first).
- [ ] Python 3.10+ installed **from python.org** (Store Python has
      sandboxing quirks around hotkeys/clipboard) and on PATH.
- [ ] `cd prototype && pip install -r requirements.txt`
      then `pip install -r desktop-win/requirements-win.txt`.
- [ ] `python -m spacy download en_core_web_sm`.
- [ ] Optional grammar tier: a Java 17+ runtime installed
      (Adoptium/Temurin MSI is fine). `health.find_java()` searches
      `Program Files/Java`, `Eclipse Adoptium`, `Microsoft/jdk`,
      `Amazon Corretto`, `Zulu` — no JAVA_HOME editing should be needed.

## 1. Engine sanity (no GUI yet)

- [ ] `python -m researchly check some.md` returns suggestions.
- [ ] `python -m researchly rules` lists ~38 rules.
- [ ] `python -c "from researchly import api; print(api.status())"`
      names every tier with a reason if it is off. **No silent tiers.**

## 2. App launch — non-admin

- [ ] `python desktop-win/researchly_win.py` from a NORMAL (non-admin)
      terminal. Expect: console prints hotkeys, panel window appears with
      the intro message + Settings button, "engine ready" within ~20 s.
- [ ] If the `keyboard` library raises on hotkey registration: note it —
      this is the known case that needs Administrator. Retry the whole
      section from an admin terminal and record which one worked.

## 3. Hotkeys + selection capture (the fragile part)

Test **each app** in this order — they exercise different clipboard and
focus behaviours:

| Target app | Check (Ctrl+Shift+R) | Polish (Ctrl+Shift+P) | Clipboard restored? |
|---|---|---|---|
| Notepad | [ ] | [ ] | [ ] |
| Word (desktop) | [ ] | [ ] | [ ] |
| Browser textarea (e.g. Overleaf) | [ ] | [ ] | [ ] |
| VS Code | [ ] | [ ] | [ ] |

For each: select a sentence with a known issue (e.g. "We utilize data in
order to make an assessment of risk."), press the hotkey, confirm the
panel shows typed suggestions (Check) or a diff (Polish).

- [ ] Empty selection → "No selection" message, not a crash.
- [ ] Clipboard content from BEFORE the hotkey is back on the clipboard
      within ~1 s (copy something distinctive first).
- [ ] If capture is flaky: tune `SLEEP_AFTER_COPY` (0.25 → 0.4) and note
      the value that works; per-machine variation is expected.

## 4. Panel actions (new in the 2026-08-14 sprint — first real test)

On a Check result:

- [ ] **Copy fix** puts the replacement on the clipboard.
- [ ] **Dismiss** removes exactly that card; the rest stay.
- [ ] **Mute rule** removes all cards of that rule AND writes
      `~/.researchly/config.toml` (open it and confirm the rule id is in
      `[rules] disable`). Run `python -m researchly check` afterwards —
      the rule must be quiet there too (that is the parity guarantee).
- [ ] **Add to dictionary** (on an S001 card) appends to
      `~/.researchly/dictionary.txt` and the word stops being flagged.

On a Polish result:

- [ ] **Replace selection** — panel hides, focus returns to the target
      app, polished text replaces the selection. Test in Notepad first
      (most forgiving), then Word, then a browser.
- [ ] **Copy rewrite** puts the rewritten text on the clipboard.
- [ ] The engine-health banner appears when the grammar tier is off and
      names the remedy.

## 5. Settings page

- [ ] Settings button on the intro page opens the settings panel.
- [ ] Changing document type / volume / locale / preference toggle
      writes `~/.researchly/config.toml` (verify on disk).
- [ ] A muted rule shows with an "unmute" link that works.
- [ ] Settings changed here are visible to `python -m researchly check`
      and to the Word add-in without restarting either.

## 6. Packaging

Two paths — test the STANDALONE INSTALLER first; it is what testers get.

- [ ] `build_installer.bat` completes (needs a JDK 17+ and Inno Setup 6 on
      the build machine only); `Output/Researchly-Setup-0.8.exe` exists.
- [ ] Setup.exe installs per-user WITHOUT an admin prompt, to
      `%LOCALAPPDATA%\Programs\Researchly`.
- [ ] On a machine (or account) with NO Python and NO Java: the installed
      app launches, check works, and the grammar tier is ON (bundled JRE +
      bundled LanguageTool — nothing downloads on first run; watch the
      network monitor to confirm).
- [ ] Uninstall from Windows Settings removes the app but leaves
      `%USERPROFILE%\.researchly` (config/dictionary are shared with other
      surfaces on purpose).
- [ ] Fallback path: `build_win.bat` completes; `dist/Researchly/Researchly.exe`
      exists (portable folder build, no installer).
- [ ] The exe runs from a fresh terminal with NO repo checkout on PATH
      (move it to another folder first) — this catches missing bundled
      data (`researchly/data/scientific_terms.txt` is the known risk).
- [ ] Exe run as non-admin: hotkeys work? If not, note it in the README
      ("run as administrator") rather than silently requiring it.
- [ ] Windows Defender/SmartScreen behaviour noted (unsigned exe will
      warn — that is expected for personal sharing).

## 7. Known follow-ups (do not block the smoke test on these)

- UI Automation selection capture (`pywinauto`/UIA) to replace the
  clipboard simulation where the focused control exposes TextPattern —
  the clipboard path stays as the universal fallback, exactly like the
  AX-then-clipboard order on macOS.
- The `keyboard` library's admin requirement: if it bites on real
  hardware, evaluate `global-hotkeys` or a Win32 RegisterHotKey shim.
