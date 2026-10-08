"""HTML rendering for the desktop floating panel — macOS AND Windows.

Pure Python, no AppKit — fully unit-testable off-Mac. Expandable "why"
sections use <details>, which needs no JavaScript.

Since the W2 sprint the check cards are ACTIONABLE, not display-only:
every action button calls `rlAction(payload)`, a tiny shim that routes to
whichever native bridge exists —

    macOS    WKWebView   window.webkit.messageHandlers.researchly
    Windows  pywebview   window.pywebview.api.action(json)

The native side receives {"action": ..., ...} and does the work (mute via
the shared config, copy via the pasteboard, …), then re-renders. HTML with
no bridge attached (tests, a browser) degrades gracefully: rlAction is a
no-op.
"""

from __future__ import annotations

import html as _html
import json as _json

CATEGORY_COLORS = {
    "correction": "#c0392b",
    "improvement": "#2563ab",
    "convention": "#a06a00",
    "preference": "#7d3f98",
}

_BASE_CSS = """
body { font-family: -apple-system, 'Helvetica Neue', sans-serif;
  font-size: 13px; color: #1d2733; margin: 0; padding: 12px 14px;
  background: #fafbfd; }
h2 { font-size: 14px; margin: 0 0 2px; }
.sub { color: #6b7686; font-size: 11px; margin-bottom: 10px; }
.chips { margin: 6px 0 12px; }
.chip { display: inline-block; padding: 2px 9px; border-radius: 999px;
  font-size: 11px; color: #fff; font-weight: 600; margin-right: 4px; }
.card { background: #fff; border: 1px solid #e3e7ee; border-left: 3px solid
  #6b7686; border-radius: 8px; padding: 8px 11px; margin-bottom: 8px; }
.tag { font-size: 10px; font-weight: 700; letter-spacing: .4px;
  text-transform: uppercase; }
.section-tag { float: right; font-size: 10px; color: #6b7686;
  font-weight: 400; text-transform: none; }
.flagged { font-family: Georgia, serif; background: #f4f6fa;
  border-radius: 4px; padding: 4px 7px; margin: 6px 0; font-size: 12.5px; }
.msg { margin: 4px 0 2px; }
.fix { font-size: 12px; color: #1c7c3c; margin: 2px 0; }
details { margin-top: 5px; }
summary { font-size: 11px; color: #6b7686; cursor: pointer; }
.why { color: #6b7686; font-size: 11.5px; line-height: 1.45;
  padding: 6px 0 2px; }
.metrics { border-top: 1px solid #e3e7ee; margin-top: 12px; padding-top: 8px;
  font-size: 11px; color: #6b7686; }
.empty { text-align: center; color: #6b7686; padding: 30px 12px; }
.polish-diff { font-family: Georgia, serif; font-size: 13px;
  line-height: 1.6; background: #f4f6fa; border-radius: 6px;
  padding: 10px 12px; margin-bottom: 10px; white-space: pre-wrap; }
del { color: #b3392b; background: #fbe9e7; }
ins { color: #1c7c3c; background: #e8f4ec; text-decoration: none; }
.edit-line { font-size: 11.5px; color: #6b7686; margin: 3px 0; }
.edit-line b { color: #1d2733; }
.note { font-size: 11px; color: #6b7686; margin-top: 8px; }
.tiers { background: #fff8e6; border: 1px solid #f0dca8; border-radius: 6px;
  padding: 7px 10px; margin-bottom: 10px; font-size: 11.5px;
  color: #6b4e00; }
.tier-row { margin: 2px 0; }
.tiers code { font-family: 'SF Mono', Menlo, monospace; font-size: 11px;
  background: #fff; border: 1px solid #f0dca8; border-radius: 3px;
  padding: 1px 4px; }
"""


_ACTIONS_CSS = """
.actions { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 6px; }
.actions button { background: #eef1f6; border: 1px solid #e3e7ee;
  color: #1d2733; border-radius: 5px; padding: 3px 9px; font-size: 11px;
  cursor: pointer; }
.actions button:hover { background: #e2e7f0; }
.actions button.good { background: #e8f4ec; border-color: #bfdccb;
  color: #1c7c3c; }
.setting-row { display: flex; align-items: center;
  justify-content: space-between; gap: 10px; padding: 8px 2px;
  border-bottom: 1px dashed #e3e7ee; font-size: 12.5px; }
.setting-row select { border: 1px solid #e3e7ee; border-radius: 5px;
  padding: 3px 6px; font-size: 12px; background: #fff; }
.muted-chip { display: inline-block; background: #eef1f6;
  border: 1px solid #e3e7ee; border-radius: 999px; padding: 2px 9px;
  font-size: 11px; margin: 2px 2px; }
.muted-chip a { color: #2563ab; cursor: pointer; margin-left: 4px; }
h3 { font-size: 12.5px; margin: 14px 0 4px; }
"""

# The bridge shim. Sent with every page; safe when no bridge exists.
_ACTION_JS = """
<script>
function rlAction(payload) {
  try {
    if (window.webkit && window.webkit.messageHandlers &&
        window.webkit.messageHandlers.researchly) {
      window.webkit.messageHandlers.researchly.postMessage(payload);
      return;
    }
  } catch (e) {}
  try {
    if (window.pywebview && window.pywebview.api &&
        window.pywebview.api.action) {
      window.pywebview.api.action(JSON.stringify(payload));
      return;
    }
  } catch (e) {}
  /* no bridge (test render / plain browser): do nothing */
}
</script>
"""


def esc(t: str) -> str:
    return _html.escape(t or "", quote=True)


def _js(payload: dict) -> str:
    """A safely HTML-attribute-embeddable rlAction(...) call."""
    return esc("rlAction(" + _json.dumps(payload) + ")")


def _page(body: str) -> str:
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{_BASE_CSS}{_ACTIONS_CSS}</style></head>"
            f"<body>{body}{_ACTION_JS}</body></html>")


def _truncate(t: str, n: int = 180) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def render_tiers(health) -> str:
    """One line naming any checking tier that is NOT running.

    Silence used to mean either "your prose is clean" or "the grammar engine
    never started" with no way to tell them apart. Say which.
    """
    if not health:
        return ""
    items = [t.to_dict() if hasattr(t, "to_dict") else t for t in health]
    down = [t for t in items
            if not t.get("ok") and (t.get("remedy")
                                    or t.get("state") in ("disabled", "error"))]
    if not down:
        return ""
    rows = "".join(
        f"<div class='tier-row'><b>{esc(t['label'])} is off</b> — "
        f"{esc(t.get('detail', ''))}"
        + (f"<br><code>{esc(t['remedy'])}</code>" if t.get("remedy") else "")
        + "</div>" for t in down)
    return f"<div class='tiers'>{rows}</div>"


def render_check(suggestions, metrics=None, hidden_prefs: int = 0,
                 source_app: str = "", health=None,
                 actions: bool = False) -> str:
    """suggestions: list of engine Suggestion objects (or dicts).

    `actions=True` adds per-suggestion buttons (Copy fix / Dismiss / Mute
    rule / Add to dictionary) wired to the rlAction bridge — the W2 fix
    for the check panel being display-only.
    """
    items = [s.to_dict() if hasattr(s, "to_dict") else s for s in suggestions]
    tiers = render_tiers(health)

    counts: dict[str, int] = {}
    for s in items:
        counts[s["category"]] = counts.get(s["category"], 0) + 1
    chips = "".join(
        f"<span class='chip' style='background:{CATEGORY_COLORS[c]}'>"
        f"{n} {c}{'s' if n != 1 else ''}</span>"
        for c, n in counts.items())

    src = f" — from {esc(source_app)}" if source_app else ""
    head = (f"<h2>Researchly</h2><div class='sub'>checked selection{src}"
            + (f" · {hidden_prefs} preference notes hidden" if hidden_prefs
               else "") + "</div>")

    if not items:
        body = head + tiers + ("<div class='empty'>Nothing to flag in this "
                               "selection.<br><span style='font-size:11px'>"
                               "(section-aware rules need headings; a bare "
                               "snippet is checked as section-unknown)"
                               "</span></div>")
        return _page(body)

    cards = []
    for idx, s in enumerate(items):
        color = CATEGORY_COLORS.get(s["category"], "#6b7686")
        sec = (f"<span class='section-tag'>§{esc(s['section'])}</span>"
               if s.get("section") and s["section"] != "unknown" else "")
        fix = (f"<div class='fix'>fix: ‘{esc(s['replacement'])}’</div>"
               if s.get("replacement") else "")
        why = s.get("why", "")
        why_html = (f"<details><summary>Why?</summary>"
                    f"<div class='why'>{esc(why)}</div></details>"
                    if why else "")
        act_html = ""
        if actions:
            btns = []
            if s.get("replacement"):
                btns.append(
                    f"<button class='good' onclick=\""
                    + _js({"action": "copy_fix", "idx": idx})
                    + "\">Copy fix</button>")
            if s.get("rule_id") == "S001" and s.get("text"):
                btns.append(
                    "<button onclick=\""
                    + _js({"action": "add_dict", "idx": idx,
                           "word": s.get("text", "")})
                    + "\">Add to dictionary</button>")
            btns.append("<button onclick=\""
                        + _js({"action": "dismiss", "idx": idx})
                        + "\">Dismiss</button>")
            btns.append("<button onclick=\""
                        + _js({"action": "mute", "rule_id": s["rule_id"]})
                        + "\">Mute rule</button>")
            act_html = "<div class='actions'>" + "".join(btns) + "</div>"
        cards.append(
            f"<div class='card' style='border-left-color:{color}'>"
            f"<span class='tag' style='color:{color}'>{esc(s['category'])}"
            f" · {esc(s['rule_id'])} {esc(s['rule_name'])}</span>{sec}"
            f"<div class='flagged'>{esc(_truncate(s.get('text', '')))}</div>"
            f"<div class='msg'>{esc(s['message'])}</div>{fix}{why_html}"
            f"{act_html}"
            f"</div>")

    mets = ""
    if metrics:
        d = metrics.to_dict() if hasattr(metrics, "to_dict") else metrics
        balance = d.get("hedge_booster_balance", "")
        mets = (f"<div class='metrics'>{d['sentences']} sentences · mean "
                f"{d['mean_sentence_len']} words · nominalizations "
                f"{d['nominalizations_per_100w']}/100w · hedges "
                f"{d['hedges_per_100w']}/100w · boosters "
                f"{d.get('boosters_per_100w', '?')}/100w"
                + (f"<br>calibration: {esc(balance)}" if balance else "")
                + "<br><i>a read-out, not a score</i></div>")

    return _page(head + tiers + f"<div class='chips'>{chips}</div>"
                 + "".join(cards) + mets)


def render_polish(result, source_app: str = "",
                  actions: bool = False) -> str:
    """result: transform.PolishResult (or its to_dict()).

    `actions=True` renders Replace/Copy buttons in the HTML itself, wired
    to the rlAction bridge — the Windows panel has no native button bar
    (that bar is an AppKit view that only exists in the macOS app), so its
    "Use the buttons below" note used to point at nothing.
    """
    d = result.to_dict() if hasattr(result, "to_dict") else result
    src = f" — from {esc(source_app)}" if source_app else ""
    head = (f"<h2>Researchly Polish</h2><div class='sub'>rule-composed "
            f"rewrite{src} · every change traceable, no AI generation</div>")

    if not d["changed"]:
        notes = d.get("notes") or []
        extra = ""
        if notes:
            lis = "".join(f"<div class='edit-line'>{esc(n)}</div>"
                          for n in notes[:5])
            extra = (f"<div class='note'>Left for your judgement:</div>{lis}")
        return _page(head + "<div class='empty'>Nothing to safely rewrite "
                     "here — the composable edits all check out.</div>"
                     + extra)

    segs = []
    for seg in d["segments"]:
        t = esc(seg["text"])
        if seg["op"] == "del":
            segs.append(f"<del>{t}</del>")
        elif seg["op"] == "ins":
            segs.append(f"<ins>{t}</ins>")
        else:
            segs.append(t)
    diff = f"<div class='polish-diff'>{''.join(segs)}</div>"

    edits = "".join(
        f"<div class='edit-line'><b>{esc(e['rule_id'])}</b> "
        f"{esc(e['rule_name'])}: “{esc(e['before'])}” → "
        f"“{esc(e['after'])}”</div>"
        for e in d["edits"])

    note = ""
    if d.get("notes"):
        note = (f"<div class='note'>+ {len(d['notes'])} judgement-call "
                f"flag{'s' if len(d['notes']) != 1 else ''} left alone "
                f"(run Check to see them)</div>")

    if actions:
        act = ("<div class='actions'>"
               "<button class='good' onclick=\""
               + _js({"action": "replace_selection"})
               + "\">Replace selection</button>"
               "<button onclick=\"" + _js({"action": "copy_rewrite"})
               + "\">Copy rewrite</button></div>")
    else:
        act = ("<div class='note'>Use the buttons below to replace the "
               "selection or copy the rewrite.</div>")
    return _page(head + diff + edits + note + act)


def render_message(title: str, message: str) -> str:
    return _page(f"<h2>{esc(title)}</h2>"
                 f"<div class='empty'>{esc(message)}</div>")


# --- shared settings page (W2 sprint item 6) -------------------------------

_DOC_TYPES = ("auto", "thesis-chapter", "manuscript", "abstract",
              "grant", "response-to-reviewers")
_AGGR = ("light", "standard", "thorough")
_LOCALES = ("en-US", "en-GB")


def _select(key: str, options, current) -> str:
    opts = "".join(
        f"<option value='{esc(o)}'{' selected' if o == current else ''}>"
        f"{esc(o)}</option>" for o in options)
    onchange = esc(
        'rlAction({"action":"set","key":"' + key
        + '","value":this.value})')
    return f"<select onchange=\"{onchange}\">{opts}</select>"


def _checkbox(key: str, label: str, checked: bool) -> str:
    onchange = esc(
        'rlAction({"action":"set","key":"' + key
        + '","value":this.checked})')
    return (f"<div class='setting-row'><span>{esc(label)}</span>"
            f"<input type='checkbox'{' checked' if checked else ''} "
            f"onchange=\"{onchange}\"></div>")


def render_settings(cfg, health=None, note: str = "") -> str:
    """The ONE settings page, rendered identically by the macOS and
    Windows panels (the Word taskpane renders the same fields natively).
    Every control writes through the rlAction bridge to `researchly.config`
    — there is no per-surface settings store to drift.
    """
    d = cfg.to_dict() if hasattr(cfg, "to_dict") else dict(cfg)
    head = ("<h2>Researchly settings</h2>"
            "<div class='sub'>shared by the CLI, Word add-in, desktop "
            "apps and editor extensions (~/.researchly/config.toml)</div>")

    rows = [
        "<div class='setting-row'><span>Document type</span>"
        + _select("document_type", _DOC_TYPES,
                  d.get("document_type", "auto")) + "</div>",
        "<div class='setting-row'><span>Suggestion volume</span>"
        + _select("aggressiveness", _AGGR,
                  d.get("aggressiveness", "standard")) + "</div>",
        "<div class='setting-row'><span>English variant</span>"
        + _select("locale", _LOCALES, d.get("locale", "en-US")) + "</div>",
        _checkbox("show_preferences", "Show preference-type suggestions",
                  bool(d.get("show_preferences"))),
        _checkbox("grammar_tier", "Grammar tier (local LanguageTool)",
                  d.get("grammar_tier") is not False),
        _checkbox("gec_tier",
                  "Learned-correction tier (local, opt-in; inert "
                  "without a model)", d.get("gec_tier") is True),
    ]

    muted = sorted(d.get("disabled") or [])
    if muted:
        chips = "".join(
            "<span class='muted-chip'>" + esc(r)
            + "<a onclick=\"" + _js({"action": "unmute", "rule_id": r})
            + "\">unmute</a></span>" for r in muted)
        rows.append("<h3>Muted rules</h3><div>" + chips + "</div>")
    else:
        rows.append("<h3>Muted rules</h3><div class='note'>none</div>")

    tiers = render_tiers(health) if health else ""
    note_html = f"<div class='note'>{esc(note)}</div>" if note else ""
    return _page(head + tiers + "".join(rows) + note_html)
