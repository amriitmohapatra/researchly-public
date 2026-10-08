"""Layered settings, shared by every surface.

Before this module, `load_config` lived inside `cli.py`, so `.researchly.toml`
reached only the CLI and the LSP: the Word add-in kept muted rules in browser
localStorage, the macOS app kept two toggles in `~/.researchly/desktop.json`,
and the Windows app had no settings at all. A rule muted in one surface was
invisible to the others.

Resolution order (later wins):

1. built-in defaults
2. user config      ~/.researchly/config.toml       (follows you everywhere)
3. project config   .researchly.toml                (next to the file, then cwd)
4. explicit overrides passed by the caller (CLI flags, request payload)

The historical `[rules] disable = [...]` / `show_preferences` shape is still
read, so existing `.researchly.toml` files keep working.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Optional

USER_DIR = Path.home() / ".researchly"
USER_CONFIG_FILE = USER_DIR / "config.toml"
PROJECT_CONFIG_NAME = ".researchly.toml"

# Document-type profiles (researchly/profiles.py, S4). The engine is
# section-aware; a profile says what KIND of document the sections belong
# to: which checks do not apply, and what section unheaded prose is in.
from .profiles import DOCUMENT_TYPES  # noqa: E402

# How loudly to talk. Not a quality dial — it moves the Preference/Convention
# floor, never the Correction tier.
AGGRESSIVENESS = ("light", "standard", "thorough")

LOCALES = ("en-US", "en-GB")

# Draft / Revise (P1, S3). Draft shows sentence-level checks only; Revise
# shows everything. A writing stage, not a quality dial: Corrections at
# sentence level are shown in both.
MODES = ("draft", "revise")


@dataclass
class Config:
    """Resolved settings. Surfaces read this; nothing else stores state."""
    disabled: set[str] = field(default_factory=set)
    show_preferences: bool = False
    locale: str = "en-US"
    document_type: str = "auto"
    aggressiveness: str = "standard"
    mode: str = "revise"
    # Tier switches. `None` means "use it if it is available" — an explicit
    # False is the user turning it off, which health.py reports differently
    # from "missing".
    grammar_tier: Optional[bool] = None
    gec_tier: Optional[bool] = None
    # Extra dictionary words from config. spelling.py has documented this
    # since v0.5 but nothing ever populated it.
    dictionary: list[str] = field(default_factory=list)

    def with_overrides(self, **kw: Any) -> "Config":
        """A copy with non-None overrides applied (CLI flags, HTTP payload)."""
        clean = {k: v for k, v in kw.items() if v is not None}
        merged = dict(clean)
        if "disabled" in clean:
            merged["disabled"] = set(clean["disabled"])
        return replace(self, **merged)

    def to_dict(self) -> dict:
        return {
            "disabled": sorted(self.disabled),
            "show_preferences": self.show_preferences,
            "locale": self.locale,
            "document_type": self.document_type,
            "aggressiveness": self.aggressiveness,
            "mode": self.mode,
            "grammar_tier": self.grammar_tier,
            "gec_tier": self.gec_tier,
            "dictionary": list(self.dictionary),
        }


# --- reading ---------------------------------------------------------------

def _get_toml_loader():
    """tomllib is stdlib from Python 3.11; fall back to tomli on older."""
    try:
        import tomllib
        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli
            return tomli
        except ModuleNotFoundError:
            return None


_WARNED_NO_TOML = False


def _read_toml(path: Path) -> dict:
    """Parse a TOML file; {} if missing or unreadable. Never raises."""
    global _WARNED_NO_TOML
    if not path.exists():
        return {}
    toml = _get_toml_loader()
    if toml is None:
        if not _WARNED_NO_TOML:
            _WARNED_NO_TOML = True
            print(f"researchly: found {path} but no TOML reader is available "
                  f"on this Python (< 3.11). Run `pip install tomli` to "
                  f"enable it; ignoring config files for now.",
                  file=sys.stderr)
        return {}
    try:
        with open(path, "rb") as f:
            return toml.load(f)
    except Exception as e:                                  # corrupt file
        print(f"researchly: could not read {path}: {e}", file=sys.stderr)
        return {}


def _apply(cfg: Config, data: dict) -> Config:
    """Fold one parsed TOML document into a Config."""
    if not data:
        return cfg

    rules = data.get("rules") or {}
    if "disable" in rules:
        cfg.disabled = set(cfg.disabled) | set(rules.get("disable") or [])
    if "enable" in rules:                     # re-enable something the user
        cfg.disabled -= set(rules.get("enable") or [])   # config turned off
    if "show_preferences" in rules:
        cfg.show_preferences = bool(rules["show_preferences"])
    if "aggressiveness" in rules:
        val = str(rules["aggressiveness"])
        if val in AGGRESSIVENESS:
            cfg.aggressiveness = val
    if "mode" in rules:
        val = str(rules["mode"])
        if val in MODES:
            cfg.mode = val

    doc = data.get("document") or {}
    if "type" in doc:
        val = str(doc["type"])
        if val in DOCUMENT_TYPES:
            cfg.document_type = val
    if "locale" in doc:
        val = str(doc["locale"])
        if val in LOCALES:
            cfg.locale = val

    tiers = data.get("tiers") or {}
    if "grammar" in tiers:
        cfg.grammar_tier = bool(tiers["grammar"])
    if "gec" in tiers:
        cfg.gec_tier = bool(tiers["gec"])

    dictionary = data.get("dictionary") or {}
    words = dictionary.get("words") or []
    if words:
        cfg.dictionary = list(cfg.dictionary) + [str(w) for w in words]

    return cfg


RULE_ID = re.compile(r"^[A-Z]{1,4}[0-9]{1,4}$")
MAX_REMOTE_RULES = 200
MAX_REMOTE_WORDS = 5000


def apply_remote(cfg: Config, data: dict) -> Config:
    """Fold the account layer (S2: settings stored with the user's account,
    fetched by the hosted engine) into a Config.

    `data` is the shape `my_config()` returns in Supabase:
    {"disabled_rules": [...], "show_preferences": bool, "locale": str,
     "mode": "draft" | "revise", "dictionary": [...]}. It came over the network, so every value is
    checked and anything malformed is dropped rather than trusted; the same
    limits are enforced by the database, so dropping only bites on a bug.
    """
    if not isinstance(data, dict):
        return cfg
    rules = data.get("disabled_rules")
    if isinstance(rules, list):
        good = [r for r in rules[:MAX_REMOTE_RULES]
                if isinstance(r, str) and RULE_ID.match(r)]
        cfg.disabled = set(cfg.disabled) | set(good)
    if isinstance(data.get("show_preferences"), bool):
        cfg.show_preferences = data["show_preferences"]
    if data.get("locale") in LOCALES:
        cfg.locale = data["locale"]
    if data.get("mode") in MODES:
        cfg.mode = data["mode"]
    if data.get("document_type") in DOCUMENT_TYPES:
        cfg.document_type = data["document_type"]
    words = data.get("dictionary")
    if isinstance(words, list):
        good = [w for w in words[:MAX_REMOTE_WORDS]
                if isinstance(w, str) and 0 < len(w) <= 64
                and not any(c.isspace() for c in w)]
        cfg.dictionary = list(cfg.dictionary) + good
    return cfg


def project_config_path(near: Optional[Path]) -> Optional[Path]:
    """The .researchly.toml that governs `near`: alongside it, else in cwd."""
    folders = []
    if near is not None:
        folders.append(near if near.is_dir() else near.parent)
    folders.append(Path.cwd())
    for folder in folders:
        candidate = folder / PROJECT_CONFIG_NAME
        if candidate.exists():
            return candidate
    return None


def load(near: Optional[Path] = None, **overrides: Any) -> Config:
    """Resolve settings for a document. `near` is its path, when there is one.

    Every surface calls this. Passing no `near` (a pasted selection, a Word
    body) still picks up the user config and any .researchly.toml in cwd.
    """
    cfg = Config()
    cfg = _apply(cfg, _read_toml(USER_CONFIG_FILE))
    project = project_config_path(near)
    if project is not None:
        cfg = _apply(cfg, _read_toml(project))
    return cfg.with_overrides(**overrides)


# --- writing ---------------------------------------------------------------
# No TOML writer in the stdlib, and the Word add-in server is deliberately
# stdlib-only, so we serialize the small known schema by hand rather than
# take a dependency.

def _toml_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_list(items) -> str:
    return "[" + ", ".join(_toml_str(i) for i in items) + "]"


def dumps(cfg: Config) -> str:
    """Serialize a Config to the .researchly.toml schema."""
    lines = [
        "# Researchly settings — written by the settings panel.",
        "# Shared by the CLI, Word add-in, macOS app, Windows app, and LSP.",
        "",
        "[rules]",
        f"disable = {_toml_list(sorted(cfg.disabled))}",
        f"show_preferences = {'true' if cfg.show_preferences else 'false'}",
        f"aggressiveness = {_toml_str(cfg.aggressiveness)}",
        f"mode = {_toml_str(cfg.mode)}",
        "",
        "[document]",
        f"type = {_toml_str(cfg.document_type)}",
        f"locale = {_toml_str(cfg.locale)}",
        "",
        "[tiers]",
    ]
    if cfg.grammar_tier is not None:
        lines.append(f"grammar = {'true' if cfg.grammar_tier else 'false'}")
    if cfg.gec_tier is not None:
        lines.append(f"gec = {'true' if cfg.gec_tier else 'false'}")
    if cfg.dictionary:
        lines += ["", "[dictionary]",
                  f"words = {_toml_list(cfg.dictionary)}"]
    return "\n".join(lines).rstrip() + "\n"


def save_user(cfg: Config) -> bool:
    """Persist to ~/.researchly/config.toml. True on success."""
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        USER_CONFIG_FILE.write_text(dumps(cfg), encoding="utf-8")
        return True
    except Exception:
        return False


def mute_rule(rule_id: str, near: Optional[Path] = None) -> bool:
    """Add a rule to the user config. Used by every surface's mute action.

    Deliberately writes the USER config, not the project one: muting a rule
    from a Word sidebar should follow the writer, not stick to whichever
    folder happened to be the working directory.
    """
    cfg = load(near)
    if rule_id in cfg.disabled:
        return True
    cfg.disabled = set(cfg.disabled) | {rule_id}
    return save_user(cfg)


def unmute_rule(rule_id: str, near: Optional[Path] = None) -> bool:
    cfg = load(near)
    if rule_id not in cfg.disabled:
        return True
    cfg.disabled = set(cfg.disabled) - {rule_id}
    return save_user(cfg)
