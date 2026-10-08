"""Q3 precision tune (P31): LanguageTool rules that misread scientific prose.

Each skipped rule was counted on the accepted-thesis corpus and the owner's
methods report (rules_grammar.SKIP_MISREAD_RULES says what it misread).
These tests pin both halves: the misreads stay quiet, and the grammar
LanguageTool is there for still fires. Synthetic sentences only.
"""

import pytest

from researchly import api, health
from researchly import rules_grammar as rg

NLP = api.get_nlp()
needs_java = pytest.mark.skipif(not health.java_available(),
                                reason="no Java 17+ — grammar tier cannot run")


def lt_hits(text):
    return {(s.message.rsplit("[", 1)[-1].rstrip("] "), s.text)
            for s in api.analyze(text, kind="plain", nlp=NLP,
                                 show_preferences=True).suggestions
            if s.rule_id == "LT001"}


def test_skip_lists_name_the_misreads_not_real_grammar():
    for rule_id in ("NON_STANDARD_WORD", "THE_SUPERLATIVE", "MAKER_COMPOUNDS",
                    "POSSESSIVE_APOSTROPHE", "NUMBERS_IN_WORDS"):
        assert rule_id in rg.SKIP_MISREAD_RULES, rule_id
    assert "EN_COMPOUNDS_" in rg.SKIP_MISREAD_PREFIXES
    for kept in ("EN_A_VS_AN", "BETWEEN_TO_AND", "COMPRISED_OF",
                 "SUBJECT_VERB_AGREEMENT", "HE_VERB_AGR"):
        assert kept not in rg.SKIP_MISREAD_RULES, kept
        assert not kept.startswith(rg.SKIP_MISREAD_PREFIXES), kept


@needs_java
@pytest.mark.parametrize("text", [
    "Policy makers in sub-tropical regions tuned the hyper-parameters.",
    "We fitted the model by generalized least squares.",
    "The adjusted odds ratio was reported for each district.",
    "The model was well behaved in every multi-dimensional setting.",
])
def test_misreads_stay_quiet(text):
    assert lt_hits(text) == set(), lt_hits(text)


@needs_java
@pytest.mark.parametrize("text,word", [
    ("Volunteers aged between 18 to 65 years took part.", "between 18 to 65"),
    ("The panel comprises of nine reviewers.", "comprises of"),
    ("We chose a unusual design for the survey.", "a"),
    ("The results has been analysed twice.", "has"),
])
def test_real_grammar_still_fires(text, word):
    assert word in {t for _, t in lt_hits(text)}, lt_hits(text)


# --- reference lists are not prose (P31) ------------------------------------

from researchly.document import Document  # noqa: E402

REFS = ("Zqwerty A, Xyzzab B. Seroprevalence of enterovirus in Zqland. "
        "J Infekt Dis Zq. 2019;12:34-56.")
BODY = "We chose a unusual design for the survey in every district."


@pytest.mark.parametrize("make", [
    lambda: Document.from_text(f"Results\n\n{BODY}\n\nReferences\n\n{REFS}\n"),
    lambda: Document.from_text(f"# Results\n\n{BODY}\n\n# References\n\n"
                               f"{REFS}\n", "markdown"),
    lambda: Document.from_word([
        {"text": "Results", "style": "Heading 1"}, {"text": BODY},
        {"text": "References", "style": "Heading 1"}, {"text": REFS}]),
])
def test_reference_list_is_masked(make):
    doc = make()
    assert "references" in {h.section for h in doc.headings}
    assert "Zqwerty" not in doc.masked and "Infekt" not in doc.masked
    assert BODY in doc.masked
    assert len(doc.masked) == len(doc.original)


def test_section_after_the_references_is_checked_again():
    doc = Document.from_word([
        {"text": "References", "style": "Heading 1"}, {"text": REFS},
        {"text": "Appendix", "style": "Heading 1"}, {"text": BODY}])
    assert "Zqwerty" not in doc.masked and BODY in doc.masked


def test_a_table_cell_reading_references_masks_nothing():
    doc = Document.from_word([
        {"text": "Results", "style": "Heading 1"},
        {"text": "References", "kind": "table"}, {"text": "12", "kind": "table"},
        {"text": BODY}])
    assert BODY in doc.masked


def test_a_sentence_mentioning_references_is_not_a_heading():
    doc = Document.from_text("Results\n\nReferences to earlier work were "
                             "checked by hand.\n")
    assert "references" not in {h.section for h in doc.headings}


# --- spelling: names in citations, field vocabulary (P31) -------------------

def s001(text):
    doc = Document.from_text(text)
    return {s.text for s in api.analyze(doc, nlp=NLP).suggestions
            if s.rule_id == "S001"}


@pytest.mark.parametrize("text", [
    "27. Zqlau H, Khosrawipour V. Internationally lost cases. Lancet. 2020.",
    "Results\n\nZqruan et al. found a protective effect in every district.",
    "Results\n\nZqzhang, Y. reported the first outbreak.",
])
def test_author_names_are_not_spelling_errors(text):
    assert not {w for w in s001(text) if w.startswith("Zq")}, s001(text)


def test_misspelt_sentence_opener_is_still_caught():
    assert "Thiss" in s001("Results\n\nThiss model fits the data well.")


@pytest.mark.parametrize("word", ["pediatric", "fomites", "sylvatic",
                                  "licensure", "seroconverted", "priori"])
def test_field_vocabulary_is_known(word):
    assert word not in s001(f"Results\n\nWe describe the {word} findings "
                            "for each district in turn.")


@pytest.mark.parametrize("word", ["subsceptible", "seperate", "prevalnce",
                                  "heterogeniety"])
def test_real_misspellings_from_the_corpus_are_still_caught(word):
    assert word in s001(f"Results\n\nWe describe the {word} findings "
                        "for each district in turn.")


# --- acronyms: numerals, journal names, conventions (P31) ---------------------

def f601(text):
    doc = Document.from_text(text)
    return {s.text for s in api.analyze(doc, nlp=NLP).suggestions
            if s.rule_id == "F601"}


@pytest.mark.parametrize("text", [
    "Results\n\nThe phase III trial enrolled children in every district.",
    "Results\n\nThe BMJ and PLOS journals published the trial results.",
    "Results\n\nThe ROC curve had an AUC of 0.8 in every district.",
])
def test_numerals_names_and_conventions_are_not_undefined_acronyms(text):
    assert f601(text) == set(), f601(text)


def test_undefined_acronym_is_still_flagged():
    assert "STAR" in f601("Results\n\nThe STAR model fitted every district.")


# --- C302: "prove" in a proof (P31) -------------------------------------------

def c302(text, kind="latex"):
    doc = Document.from_text(text, kind)
    return [s.text for s in api.analyze(doc, nlp=NLP).suggestions
            if s.rule_id == "C302"]


@pytest.mark.parametrize("text", [
    "\\section{Introduction}\nWe prove that $S(5) = 47$ using a checker.\n",
    "\\section{Results}\nThe lemma is proved by induction on the depth.\n",
    "\\section{Results}\nWe proved the conjecture with the Coq proof "
    "assistant.\n",
])
def test_prove_in_a_proof_is_not_an_overclaim(text):
    assert c302(text) == []


def test_prove_about_empirical_data_is_still_flagged():
    assert c302("\\section{Results}\nThis survey proves that masks "
                "work.\n") == ["proves"]
