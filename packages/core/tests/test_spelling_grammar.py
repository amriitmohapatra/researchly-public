"""Tests for the S001 spelling tier and (when available) LT001 grammar."""

import pytest
import spacy

from researchly.document import Document
from researchly.engine import check
from researchly import spelling

NLP = spacy.load("en_core_web_sm")


def flags(text, rule="S001", disabled=frozenset({"LT001"})):
    doc = Document.from_text(text, "plain")
    return [s for s in check(doc, NLP, disabled=set(disabled),
                             show_preferences=False)
            if s.rule_id == rule]


# --- the user's acceptance example -----------------------------------------

def test_users_example_misspellings_all_flagged():
    hits = flags("I amm duing dis workk at thiss shity.")
    flagged = {s.text for s in hits}
    # 'dis' is a real dictionary word — context-level, not spell-level
    assert {"amm", "duing", "workk", "thiss", "shity"} <= flagged
    fixes = {s.text: s.replacement for s in hits}
    assert fixes["amm"] == "am"
    assert fixes["workk"] == "work"
    assert fixes["thiss"] == "this"


def test_tokenizer_split_typo_still_caught():
    # spaCy splits 'thiss' into 'this'+'s'; the regex scan must not care
    assert any(s.text == "thiss" for s in flags("We keep thiss version."))


# --- precision guards -------------------------------------------------------

def test_scientific_vocabulary_not_flagged():
    t = ("The seroprevalence of dengue rose. Covariates included "
         "overdispersion and nowcasting estimates for Aedes aegypti.")
    assert flags(t) == []


def test_dogfood_vocabulary_gaps_not_flagged():
    # The first S001 corpus run (CLAUDE.md, "never been dogfooded") found
    # these real terms flagged on accepted theses. Each appears once here,
    # so the repeated-term learning below cannot be what saves them.
    # Mid-sentence and lowercase: capitalised words are skipped as possible
    # proper nouns, which would make the test pass for the wrong reason.
    t = ("The estimand was prespecified. Outcomes varied with urbanicity "
         "after lockdowns. The serotypic shift reflects a tradeoff in "
         "exergy, and several estimands were compared.")
    assert flags(t) == []


def test_uk_us_variants_not_flagged():
    t = ("We are modelling behaviour while analyzing and analysing "
         "hospitalisations and hospitalizations.")
    assert flags(t) == []


def test_proper_nouns_and_acronyms_skipped():
    t = "Kieshha and Dr Xhulios met at NUS with the WAIC estimates."
    assert flags(t) == []


def test_repeated_terms_are_learned():
    t = ("The frobulation index rose. Frobulation was highest in cities. "
         "We report frobulation trends over time.")
    assert flags(t) == []           # 3 uses → author's term


def test_single_unknown_word_is_flagged(tmp_path, monkeypatch):
    # isolate from the real personal dictionary
    monkeypatch.setattr(spelling, "USER_DICT_FILE",
                        tmp_path / "dictionary.txt")
    hits = flags("The frobulation index rose sharply this year.")
    assert len(hits) == 1 and hits[0].text == "frobulation"


def test_sentence_start_capitalized_typo_caught():
    hits = flags("Thiss approach works well in practice.")
    assert any(s.text == "Thiss" for s in hits)
    top = next(s for s in hits if s.text == "Thiss")
    assert top.replacement == "This"       # case preserved


def test_urls_and_emails_skipped():
    t = "See exampl.com/duing and mail duing@exampl.com for details."
    assert flags(t) == []


def test_user_dictionary_respected(tmp_path, monkeypatch):
    monkeypatch.setattr(spelling, "USER_DICT_FILE",
                        tmp_path / "dictionary.txt")
    assert flags("The zorbulator ran overnight.")  # flagged before adding
    assert spelling.add_to_user_dictionary("zorbulator")
    assert flags("The zorbulator ran overnight.") == []


def test_masked_regions_never_flagged():
    # markdown masking hides math and inline code from the spell layer
    t = "# Results\n\nThe rate $\\lambda_{duing}$ was `thiss_var` here."
    doc = Document.from_text(t, "markdown")
    hits = [s for s in check(doc, NLP, disabled={"LT001"},
                             show_preferences=False)
            if s.rule_id == "S001"]
    assert hits == []


# --- LT001 (optional tier) ---------------------------------------------------

lt_available = pytest.mark.skipif(
    not __import__("researchly.rules_grammar",
                   fromlist=["available"]).available(),
    reason="LanguageTool not available")


@lt_available
def test_lt_catches_agreement():
    hits = flags("He go to school every day.", rule="LT001",
                 disabled=frozenset())
    assert hits and any("go" in s.text for s in hits)


@lt_available
def test_lt_catches_a_vs_an():
    hits = flags("We fitted an model to the data.", rule="LT001",
                 disabled=frozenset())
    assert hits


@lt_available
def test_lt_does_not_duplicate_spelling():
    # unknown-word spelling stays S001's job (MORFOLOGIK filtered out)
    hits = flags("The workk was hard.", rule="LT001", disabled=frozenset())
    assert all("workk" not in s.text for s in hits)


@lt_available
def test_doubled_word_is_flagged_once_not_twice():
    """The S1 end-to-end run showed two cards for one "the the": LanguageTool's
    ENGLISH_WORD_REPEAT_RULE and Researchly's own W207. Duplicate flags are the
    noise CLAUDE.md #5 exists to prevent; W207 keeps it (it is sourced and its
    fix is bulk-safe)."""
    doc = Document.from_text("We studied the the dynamics of spread.", "plain")
    hits = [s for s in check(doc, NLP, disabled=set(), show_preferences=False)
            if "the the" in s.text]
    assert [s.rule_id for s in hits] == ["W207"]
