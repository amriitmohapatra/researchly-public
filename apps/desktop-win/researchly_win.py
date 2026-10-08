#!/usr/bin/env python3
"""Researchly for Windows — scaffold, now with working panel actions.

STATUS: still awaiting a first run on real Windows hardware (see
docs/windows-smoke-checklist.md for the bring-up protocol). What changed
in the 2026-08-14 sprint:

- the polish Replace/Copy buttons now exist. The old panel told the user
  "use the buttons below" — but that button bar is an AppKit view that
  only exists in the macOS app. Buttons are now rendered in the HTML
  itself (panel_html `actions=True`) and reach Python through pywebview's
  js_api bridge;
- check results are actionable (Copy fix / Dismiss / Mute rule / Add to
  dictionary), with mutes going through the SHARED config layer so a rule
  muted here is muted in Word, the CLI and on the Mac;
- a Settings page (panel_html.render_settings — the same page the macOS
  app shows) writes through the same bridge to the same config;
- engine health is shown on every check (render_check already does this).

Hotkeys:
    Ctrl+Shift+R — Check selection   (any app)
    Ctrl+Shift+P — Polish selection
    (override in ~/.researchly/desktop.json: {"hotkeys":
     {"check": "ctrl+shift+r", "polish": "ctrl+shift+p"}})

Selection capture: simulate Ctrl+C via the `keyboard` library, read the
clipboard with `pyperclip`, restore it afterwards. Panel: a `pywebview`
window rendering panel_html. Replace: clipboard + Ctrl+V paste-back.
UI Automation (reading the focused control directly, no clipboard) is the
planned upgrade once real hardware confirms the basics — see the smoke
checklist.

Run:    pip install -r requirements-win.txt
        python researchly_win.py
Build:  build_win.bat  (PyInstaller → dist/Researchly.exe)

Known design notes for the bring-up session:
- `keyboard` needs no admin for hotkeys in most setups, but some
  environments require running as Administrator.
- pywebview needs Edge WebView2 runtime (preinstalled on Win 11).
- Clipboard timing constants (SLEEP_*) will likely need tuning per machine.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "packages" / "core"))  # researchly pkg
sys.path.insert(0, str(HERE.parent / "desktop-mac"))    # panel_html reuse

import panel_html  # noqa: E402

try:
    import keyboard   # global hotkeys + key simulation
    import pyperclip  # clipboard
    import webview    # pywebview panel
except ImportError as e:  # pragma: no cover
    print("Researchly for Windows needs its dependencies:\n"
          "    pip install -r requirements-win.txt\n"
          f"(import failed: {e})")
    sys.exit(1)

SLEEP_AFTER_COPY = 0.25
SLEEP_BEFORE_PASTE = 0.15

PREFS_FILE = Path.home() / ".researchly" / "desktop.json"
DEFAULT_HOTKEYS = {"check": "ctrl+shift+r", "polish": "ctrl+shift+p"}


def load_hotkeys() -> dict:
    try:
        if PREFS_FILE.exists():
            prefs = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
            hk = dict(DEFAULT_HOTKEYS)
            hk.update(prefs.get("hotkeys") or {})
            return hk
    except Exception:
        pass
    return dict(DEFAULT_HOTKEYS)


class Engine:
    def __init__(self):
        self.nlp = None
        self.error = None
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            from researchly import api
            self.nlp = api.get_nlp()
            api.ensure_rules_loaded()
            print("engine ready")
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"

    def check(self, text: str):
        """One shared-layer pass; returns the Analysis object."""
        from researchly import api
        return api.analyze(text, kind="plain", nlp=self.nlp)

    def polish(self, text: str):
        from researchly.transform import polish
        from researchly import config as config_mod
        return polish(text, self.nlp, kind="plain",
                      disabled=config_mod.load().disabled)


ENGINE = Engine()
# Panel state for re-rendering after dismiss/mute. `check` holds the last
# Analysis suggestions as dicts plus display extras.
STATE = {
    "polish": None,          # last PolishResult
    "check": None,           # {"suggestions": [...], "mets", "hidden",
                             #  "health", "app", "dismissed": set()}
}
WINDOW = None


def capture_selection() -> str:
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    keyboard.send("ctrl+c")
    time.sleep(SLEEP_AFTER_COPY)
    try:
        text = pyperclip.paste()
    except Exception:
        text = ""
    if old is not None and old != text:
        # restore the user's clipboard after we've read the selection
        def restore():
            time.sleep(0.3)
            try:
                pyperclip.copy(old)
            except Exception:
                pass
        threading.Thread(target=restore, daemon=True).start()
    return text or ""


def paste_replacement(text: str):
    try:
        pyperclip.copy(text)
        time.sleep(SLEEP_BEFORE_PASTE)
        keyboard.send("ctrl+v")
    except Exception:
        pass


def show_html(html: str):
    global WINDOW
    if WINDOW is None:
        return
    WINDOW.load_html(html)
    WINDOW.show()


def _render_check_state():
    """Re-render the last check minus dismissed cards (dismiss/mute)."""
    st = STATE.get("check")
    if not st:
        return
    visible = [s for i, s in enumerate(st["suggestions"])
               if i not in st["dismissed"]]
    show_html(panel_html.render_check(
        visible, st["mets"], st["hidden"], source_app=st["app"],
        health=st["health"], actions=True))


def on_check():
    text = capture_selection()
    if not text.strip():
        show_html(panel_html.render_message(
            "No selection", "Select text in any app, then press the check "
            "hotkey (default Ctrl+Shift+R) or polish (Ctrl+Shift+P)."))
        return
    if ENGINE.nlp is None:
        show_html(panel_html.render_message(
            "Warming up", ENGINE.error or "Language model still loading — "
            "try again in a few seconds."))
        return

    def work():
        try:
            a = ENGINE.check(text)
            STATE["check"] = {
                "suggestions": [s.to_dict() for s in a.suggestions],
                "mets": a.metrics,
                "hidden": a.hidden_preferences,
                "health": a.health,
                "app": "",
                "dismissed": set(),
            }
            _render_check_state()
        except Exception as e:
            show_html(panel_html.render_message(
                "Error", f"{type(e).__name__}: {e}"))
    threading.Thread(target=work, daemon=True).start()


def on_polish():
    text = capture_selection()
    if not text.strip() or ENGINE.nlp is None:
        on_check()
        return

    def work():
        try:
            result = ENGINE.polish(text)
            STATE["polish"] = result
            # actions=True: the Replace/Copy buttons live in the HTML —
            # Windows has no native button bar (that is an AppKit view).
            show_html(panel_html.render_polish(result, actions=True))
        except Exception as e:
            show_html(panel_html.render_message(
                "Error", f"{type(e).__name__}: {e}"))
    threading.Thread(target=work, daemon=True).start()


def show_settings(note: str = ""):
    from researchly import api
    from researchly import config as config_mod
    cfg = config_mod.load()
    health = api.status(cfg)
    show_html(panel_html.render_settings(cfg, health=health, note=note))


class JsApi:
    """pywebview js_api — receives every rlAction() from the panel HTML."""

    def action(self, payload_json):
        try:
            p = json.loads(payload_json or "{}")
        except Exception:
            return
        act = p.get("action", "")
        try:
            if act == "replace_selection":
                self._replace_selection()
            elif act == "copy_rewrite":
                self._copy_rewrite()
            elif act == "copy_fix":
                self._copy_fix(int(p.get("idx", -1)))
            elif act == "dismiss":
                self._dismiss(int(p.get("idx", -1)))
            elif act == "mute":
                self._mute(str(p.get("rule_id") or ""))
            elif act == "unmute":
                self._unmute(str(p.get("rule_id") or ""))
            elif act == "add_dict":
                self._add_dict(str(p.get("word") or ""),
                               int(p.get("idx", -1)))
            elif act == "set":
                self._set(str(p.get("key") or ""), p.get("value"))
            elif act == "settings":
                show_settings()
        except Exception as e:                 # a broken action must not
            show_html(panel_html.render_message(  # kill the panel
                "Error", f"{type(e).__name__}: {e}"))

    # -- polish -------------------------------------------------------------

    def _replace_selection(self):
        r = STATE.get("polish")
        if r is not None and r.changed:
            WINDOW.hide()
            time.sleep(0.2)          # let focus return to the target app
            paste_replacement(r.rewritten)

    def _copy_rewrite(self):
        r = STATE.get("polish")
        if r is not None:
            pyperclip.copy(r.rewritten)

    # -- check cards ---------------------------------------------------------

    def _visible_index(self, idx):
        """Map a rendered card index back into STATE['check'] indices."""
        st = STATE.get("check")
        if not st:
            return None, None
        visible = [i for i in range(len(st["suggestions"]))
                   if i not in st["dismissed"]]
        if 0 <= idx < len(visible):
            return st, visible[idx]
        return st, None

    def _copy_fix(self, idx):
        st, real = self._visible_index(idx)
        if st is None or real is None:
            return
        s = st["suggestions"][real]
        if s.get("replacement") is not None:
            pyperclip.copy(s["replacement"])
        from researchly import telemetry
        telemetry.log_event("applied", s.get("rule_id", ""),
                            section=s.get("section", "unknown"),
                            source="windows")

    def _dismiss(self, idx):
        st, real = self._visible_index(idx)
        if st is None or real is None:
            return
        st["dismissed"].add(real)
        from researchly import telemetry
        s = st["suggestions"][real]
        telemetry.log_event("dismissed", s.get("rule_id", ""),
                            section=s.get("section", "unknown"),
                            source="windows")
        _render_check_state()

    def _mute(self, rule_id):
        if not rule_id:
            return
        from researchly import config as config_mod
        from researchly import telemetry
        config_mod.mute_rule(rule_id)          # the SHARED config
        telemetry.log_event("muted", rule_id, source="windows")
        st = STATE.get("check")
        if st:
            for i, s in enumerate(st["suggestions"]):
                if s.get("rule_id") == rule_id:
                    st["dismissed"].add(i)
            _render_check_state()

    def _unmute(self, rule_id):
        if not rule_id:
            return
        from researchly import config as config_mod
        config_mod.unmute_rule(rule_id)
        show_settings(note=f"{rule_id} unmuted.")

    def _add_dict(self, word, idx):
        if not word:
            return
        from researchly import spelling
        ok = spelling.add_to_user_dictionary(word)
        st = STATE.get("check")
        if ok and st:
            low = word.lower()
            for i, s in enumerate(st["suggestions"]):
                if (s.get("rule_id") == "S001"
                        and (s.get("text") or "").lower() == low):
                    st["dismissed"].add(i)
            _render_check_state()

    # -- settings ------------------------------------------------------------

    def _set(self, key, value):
        from researchly import config as config_mod
        allowed = {"document_type", "aggressiveness", "locale",
                   "show_preferences", "grammar_tier", "gec_tier"}
        if key not in allowed:
            return
        cfg = config_mod.load().with_overrides(**{key: value})
        ok = config_mod.save_user(cfg)
        show_settings(note="Saved — shared with every Researchly surface."
                      if ok else "Could not save settings.")


def main():
    global WINDOW
    hotkeys = load_hotkeys()
    keyboard.add_hotkey(hotkeys["check"], on_check)
    keyboard.add_hotkey(hotkeys["polish"], on_polish)
    intro = panel_html.render_message(
        "Researchly is running",
        f"{hotkeys['check']} checks the current selection anywhere; "
        f"{hotkeys['polish']} polishes it. Keep this window minimized.")
    # add a Settings link to the intro page (goes through the same bridge)
    intro = intro.replace(
        "</body>",
        "<div class='actions' style='justify-content:center'>"
        "<button onclick=\"rlAction({&quot;action&quot;:"
        "&quot;settings&quot;})\">Settings</button></div></body>")
    WINDOW = webview.create_window(
        "Researchly", html=intro,
        width=460, height=620, on_top=True, js_api=JsApi())
    print(f"Researchly (Windows) running — {hotkeys['check']} / "
          f"{hotkeys['polish']}")
    webview.start()


if __name__ == "__main__":
    main()
