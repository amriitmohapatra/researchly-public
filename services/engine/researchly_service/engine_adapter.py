"""The bridge from contract v1 to `researchly.api` — and nothing else.

The service never assembles its own pipeline (CLAUDE.md): every analysis is
one `api.analyze()` call. This module only

- builds a per-request `Config` from defaults + request options (never from
  files: hosted requests are multi-tenant, see _core.py);
- maps the engine's dataclasses onto the contract's pydantic models;
- serialises engine calls with one process-wide lock, because the spaCy
  pipeline and the LanguageTool client are shared singletons that are not
  documented as thread-safe, and FastAPI runs sync routes in a threadpool.
  Cloud Run's `containerConcurrency` is set to match (deploy/), so a request
  waits in Cloud Run's queue — or goes to another instance — rather than
  behind this lock;
- warms everything once at startup so no user request pays the cold start.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import List, Optional, Union

from . import _core  # noqa: F401  (import path + isolation first)
from . import __version__ as SERVICE_VERSION
from .schemas import (AnalyzeOptions, AnalyzeResponse, AnalyzeWordResponse,
                      Category, ChecklistChoiceInfo, ChecklistReport,
                      Coverage, DocumentType, EngineInfo, FixSafety,
                      HedgingPoint, LearnCard, Metrics, MissingLink, Mode,
                      NarrativeMap, NarrativeMove, NarrativeSection,
                      ProfileChoice, ProfileInfo, ReviewQuestion,
                      ReviewReport, ReviewRuleCount, RuleInfo, Scope, Span,
                      Suggestion, TierHealth, WordLocation, WordSuggestion)

import researchly
from researchly import api, learn, packs, profiles, shapes, wordloc
from researchly.config import Config, apply_remote
from researchly.document import Document
from researchly.engine import REGISTRY

ENGINE_LOCK = threading.Lock()

# Synthetic warm-up text (never user text): a Methods heading so section
# detection runs, a passive sentence, a hedge, and a grammar slip so the
# LanguageTool path is exercised end to end.
WARMUP_TEXT = (
    "Methods\n\n"
    "Weekly case counts were fitted with a renewal-equation model. "
    "This are a deliberate slip so the grammar tier is exercised.\n\n"
    "Discussion\n\n"
    "These results may suggest that transmission declined.\n"
)

_RULES_LOADED: Optional[int] = None


def rules_loaded() -> int:
    global _RULES_LOADED
    if _RULES_LOADED is None:
        _RULES_LOADED = api.ensure_rules_loaded()
    return _RULES_LOADED


def engine_info() -> EngineInfo:
    return EngineInfo(service_version=SERVICE_VERSION,
                      core_version=researchly.__version__,
                      rules_loaded=rules_loaded())


def build_config(options: Optional[AnalyzeOptions],
                 grammar_enabled: bool = True,
                 account: Optional[dict] = None) -> Config:
    """Defaults, then the caller's account settings, then this request's
    options. Never reads a file.

    A request can only ADD to what the account says: its disabled_rules are
    added to the stored ones and show_preferences is stored OR requested
    (docs/s2-design.md §3), so a rule muted anywhere stays muted.
    """
    cfg = Config()
    if not grammar_enabled:
        cfg.grammar_tier = False           # the deployment runs no grammar
    if account is not None:
        apply_remote(cfg, account)
    if options is not None:
        cfg.show_preferences = cfg.show_preferences or bool(options.show_preferences)
        cfg.disabled = set(cfg.disabled) | set(options.disabled_rules)
        # A view choice, not a mute: the request's own mode wins (the add-in
        # toggles it per check); otherwise the account's saved one.
        if options.mode is not None:
            cfg.mode = options.mode.value
        if options.document_type is not None:
            cfg.document_type = options.document_type.value
    return cfg


# Everything beyond the suggestions is shaped once, in the core
# (researchly.shapes), and validated here; the local Word server sends the
# same shapes (Codex review R1).

def to_profile(a) -> ProfileInfo:
    return ProfileInfo(**shapes.profile_info(a))


def to_review(r: Optional[dict]) -> Optional[ReviewReport]:
    shaped = shapes.review_report(r)
    return None if shaped is None else ReviewReport(**shaped)


def to_narrative(n: Optional[dict]) -> Optional[NarrativeMap]:
    shaped = shapes.narrative_map(n)
    return None if shaped is None else NarrativeMap(**shaped)


def to_checklist(c: Optional[dict]) -> Optional[ChecklistReport]:
    shaped = shapes.checklist_report(c)
    return None if shaped is None else ChecklistReport(**shaped)


def learn_cards() -> List[LearnCard]:
    return [LearnCard(**c) for c in learn.listing()]


def checklist_choices() -> list:
    return [ChecklistChoiceInfo(**row) for row in packs.listing()]


def profile_choices() -> list:
    return [ProfileChoice(**row) for row in profiles.listing()]


def fingerprint(rule_id: str, start: int, end: int, text: str) -> str:
    """Stable id for a suggestion: sha1(rule_id, start, end, text).

    Fields are joined with U+001F (unit separator) so ("A1", "2…") and
    ("A", "12…") cannot collide.
    """
    raw = "\x1f".join((rule_id, str(start), str(end), text))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _category(value: str) -> Category:
    return Category(value)


def _fix_safety(value: str) -> FixSafety:
    return FixSafety.safe if value == "safe" else FixSafety.review


def to_suggestion(s) -> Suggestion:
    conf = float(s.confidence if s.confidence is not None else 1.0)
    return Suggestion(
        id=fingerprint(s.rule_id, s.start, s.end, s.text),
        rule_id=s.rule_id,
        rule_name=s.rule_name,
        category=_category(s.category.value),
        tier=s.tier,
        span=Span(start=max(0, s.start), end=max(0, s.end),
                  line=max(0, s.line), col=max(0, s.col)),
        text=s.text,
        section=s.section or "unknown",
        message=s.message,
        why=s.why,
        plain=s.plain,
        source=s.source,
        learn_ref=s.learn_ref,
        replacement=s.replacement,
        fix_safety=_fix_safety(s.fix_safety),
        confidence=min(1.0, max(0.0, conf)),
    )


def to_tier(t) -> TierHealth:
    return TierHealth(**t.to_dict())


def to_metrics(m) -> Optional[Metrics]:
    if m is None:
        return None
    return Metrics(**m.to_dict())


# What the `account` tier says when a signed-in caller's settings could not
# be loaded. `kind` is from accounts.SettingsUnavailable: text-free.
def account_tier(error_kind: Optional[str]) -> TierHealth:
    if error_kind is None:
        return TierHealth(tier="account", label="Your settings", ok=True,
                          state="ready", detail="", remedy="")
    return TierHealth(
        tier="account", label="Your settings", ok=False, state="error",
        detail=f"Your saved settings could not be loaded ({error_kind}).",
        remedy="This check used the defaults: your muted rules and dictionary "
               "were not applied. Try again in a minute.")


def run_analysis(source: Union[str, Document], fmt: str,
                 options: Optional[AnalyzeOptions],
                 grammar_enabled: bool = True,
                 account: Optional[dict] = None,
                 signed_in: bool = False,
                 account_error: Optional[str] = None,
                 response_cls=AnalyzeResponse, **extra) -> AnalyzeResponse:
    """One analysis, serialised. Times the whole call including lock wait.

    `source` is pasted text (with `fmt`) or a Document from researchly.ingest.
    """
    t0 = time.perf_counter()
    cfg = build_config(options, grammar_enabled, account)
    with ENGINE_LOCK:
        a = api.analyze(source, kind=fmt, cfg=cfg,
                        with_review=bool(options and options.review),
                        with_narrative=bool(options and options.narrative),
                        checklist=(options.checklist.value
                                   if options and options.checklist else None))
    health = [to_tier(t) for t in a.health]
    if signed_in:
        health.append(account_tier(account_error))
    paragraphs = extra.pop("word_paragraphs", None)
    if paragraphs is not None:
        doc = a.document
        suggestions = [WordSuggestion(
            **to_suggestion(s).model_dump(),
            location=WordLocation(**wordloc.locate(doc, paragraphs,
                                                   s.start, s.end)))
            for s in a.suggestions]
        extra["coverage"] = Coverage(**wordloc.coverage(paragraphs, doc))
    else:
        suggestions = [to_suggestion(s) for s in a.suggestions]
    out = response_cls(
        signed_in=signed_in,
        mode=Mode(a.config.mode),
        profile=to_profile(a),
        review=to_review(a.review),
        narrative=to_narrative(a.narrative),
        checklist=to_checklist(a.checklist),
        suggested_checklist=a.suggested_checklist,
        hidden_by_mode=a.hidden_by_mode,
        suggestions=suggestions,
        counts=dict(a.counts),
        hidden_preferences=a.hidden_preferences,
        metrics=to_metrics(a.metrics),
        sections_detected=list(a.sections_detected),
        health=health,
        engine=engine_info(),
        elapsed_ms=0,
        warnings=list(a.document.warnings) if a.document is not None else [],
        **extra,
    )
    out.elapsed_ms = int(round((time.perf_counter() - t0) * 1000))
    return out


# Tiers that never make the service "degraded" by being off: gec is opt-in
# (no model ships), so missing/disabled is its normal state.
_OPTIONAL_STATES = {"gec": {"missing", "disabled"}}


def health_tiers(grammar_enabled: bool = True) -> List[TierHealth]:
    """Live tier status. Probes remote LanguageTool (cached a few seconds);
    loads nothing new — warm-up already did."""
    from researchly.health import engine_status
    cfg = build_config(None, grammar_enabled)
    nlp = api._NLP                       # loaded by warm-up, or None
    return [to_tier(t) for t in engine_status(cfg, nlp=nlp, probe=True)]


def is_degraded(tiers: List[TierHealth]) -> bool:
    """Degraded when a tier the service is configured to run is not ok."""
    for t in tiers:
        if t.ok:
            continue
        if t.state in _OPTIONAL_STATES.get(t.tier, set()):
            continue
        if t.state == "disabled":          # the operator turned it off
            continue
        return True
    return False


def rule_infos() -> List[RuleInfo]:
    rules_loaded()
    out = []
    for r in sorted(REGISTRY.values(), key=lambda r: r.id):
        out.append(RuleInfo(
            id=r.id, name=r.name, category=_category(r.category.value),
            short=r.short, why=r.why, plain=r.plain, source=r.source,
            tier=r.tier,
            fix_safety=_fix_safety(r.fix_safety),
            scope=Scope(r.scope),
            sections_only=sorted(r.sections_only) if r.sections_only else None,
            sections_excluded=(sorted(r.sections_excluded)
                               if r.sections_excluded else None),
            learn_ref=learn.card_for_rule(r.id),
        ))
    return out


def warm_up(grammar_enabled: bool = True) -> dict:
    """Load spaCy, register rules, start/reach LanguageTool, run one check.

    Never raises: a tier that fails to warm is reported by /v1/health, and
    the service still starts (degraded beats down).
    """
    t0 = time.perf_counter()
    info = {"rules_loaded": rules_loaded()}
    try:
        api.get_nlp()
        run_analysis(WARMUP_TEXT, "plain", AnalyzeOptions(), grammar_enabled)
    except Exception as e:                       # reported by type only
        info["error_type"] = type(e).__name__
    tiers = health_tiers(grammar_enabled)
    info["tiers"] = {t.tier: t.state for t in tiers}
    info["warmup_ms"] = int(round((time.perf_counter() - t0) * 1000))
    return info
