"""The narrative map (S4): moves per section, order, missing links and the
hedging trajectory, from the same analysis as the suggestions. Synthetic
text only."""

import pytest

from researchly import api, sources
from researchly.discourse import moves as moves_mod
from researchly.discourse.narrative import build_narrative, render_narrative
from researchly.document import Document
from tests.test_explanations import INTERNAL

NLP = api.get_nlp()

PAPER = """Abstract

Dengue is a major burden across the region. However, the effect of rainfall remains unclear. We aimed to estimate the reproduction number. We fitted a transmission model to weekly case counts. Cases fell by 40% after the campaign. These findings suggest that campaigns should be timed to the season.

Introduction

Dengue remains a leading cause of hospital admission in the region. However, little is known about how it varies between districts. We therefore set out to estimate transmission in three districts.

Methods

Weekly case counts were collected from the surveillance system. We fitted a compartmental model by maximum likelihood.

Results

The reproduction number was 1.4 (95% CI 1.2 to 1.6; Figure 1). Cases fell by 40% in every district.

Discussion

In this study we found that transmission varied twofold between districts. This suggests that control should be targeted, because the districts differ in density. Our estimate is consistent with previous studies. This study has limitations: reporting was incomplete. Policymakers could use these estimates to plan the next campaign.
"""


def narrative(text, **kw):
    return api.analyze(text, nlp=NLP, with_narrative=True, **kw).narrative


def section(n, name):
    return next(s for s in n["sections"] if s["section"] == name)


def statuses(n, name):
    return {m["id"]: m["status"] for m in section(n, name)["moves"]}


# --- the registry ---------------------------------------------------------------------

def test_every_schema_move_exists_and_is_explained():
    for sec, schema in moves_mod.SCHEMAS.items():
        for mid in schema:
            m = moves_mod.MOVES[mid]
            assert m.question.endswith("?") and len(m.plain.split()) >= 10
            assert m.frame.startswith("“") and "[" in m.frame
            assert m.citation and len(m.citation) > 15


def test_user_visible_wording_has_no_internal_references():
    for m in moves_mod.MOVES.values():
        for field in (m.label, m.question, m.plain, m.frame):
            assert not INTERNAL.search(field), (m.id, field)


def test_sources_resolve():
    for code in ("Swales", "Toulmin", "§2", "§3", "§7.3", "§9.8"):
        assert sources.cite(code)


# --- the map ----------------------------------------------------------------------------

def test_a_complete_paper_has_every_move_present():
    n = narrative(PAPER)
    assert [s["section"] for s in n["sections"]] == [
        "abstract", "introduction", "methods", "results", "discussion"]
    for s in n["sections"]:
        assert all(m["status"] == "present" for m in s["moves"]), s["section"]
        assert s["present"] == s["expected"]
    assert n["note"] == "Every expected move is present."
    gap = next(m for m in section(n, "introduction")["moves"] if m["id"] == "gap")
    assert gap["evidence"].startswith("However, little is known")


def test_a_missing_move_carries_its_question_and_frame():
    text = PAPER.replace(
        "We therefore set out to estimate transmission in three districts.", "")
    n = narrative(text)
    aim = next(m for m in section(n, "introduction")["moves"] if m["id"] == "aim")
    assert aim["status"] == "missing" and aim["evidence"] is None
    assert aim["question"].endswith("?") and "[" in aim["frame"]
    assert "1 expected move is missing" in n["note"]


def test_one_misplaced_sentence_is_reported_once():
    # the gap moved to the end of the abstract
    text = PAPER.replace(
        "Dengue is a major burden across the region. However, the effect "
        "of rainfall remains unclear. We aimed",
        "Dengue is a major burden across the region. We aimed").replace(
        "timed to the season.\n",
        "timed to the season. However, the effect of rainfall remains unclear.\n")
    st = statuses(narrative(text), "abstract")
    assert st["gap"] == "out_of_order"
    assert [k for k, v in st.items() if v == "out_of_order"] == ["gap"]
    gap = next(m for m in section(narrative(text), "abstract")["moves"]
               if m["id"] == "gap")
    assert gap["note"].startswith("Appears after")


def test_order_is_not_judged_where_it_does_not_matter():
    text = PAPER.replace(
        "This study has limitations: reporting was incomplete. "
        "Policymakers could use these estimates to plan the next campaign.",
        "Policymakers could use these estimates to plan the next campaign. "
        "This study has limitations: reporting was incomplete.")
    assert "out_of_order" not in statuses(narrative(text), "discussion").values()


def test_no_headings_means_no_map_but_a_plain_note():
    n = narrative("We fitted a model. Cases fell by half. This suggests "
                  "the campaign worked.\n")
    assert n["sections"] == [] and "No section headings" in n["note"]
    assert not INTERNAL.search(n["note"])


def test_topical_headings_are_listed_as_unmapped():
    doc = Document.from_word([
        {"text": "The dengue season", "style": "Heading 1"},
        {"text": "Cases rose in every district."},
        {"text": "Discussion", "style": "Heading 1"},
        {"text": "In this study we found that cases rose."},
    ])
    n = api.analyze(doc, nlp=NLP, with_narrative=True).narrative
    assert n["unmapped"] == ["other"]
    assert [s["section"] for s in n["sections"]] == ["discussion"]


def test_missing_links_come_from_argued_sections_only():
    n = narrative(PAPER)
    assert all(link["section"] != "results" for link in n["missing_links"])
    assert all(link["source"] for link in n["missing_links"])


def test_hedging_trajectory_is_per_section_and_never_a_score():
    n = narrative(PAPER)
    rows = {h["section"]: h for h in n["hedging"]}
    assert rows["discussion"]["hedges_per_100w"] > 0
    assert rows["methods"]["hedges_per_100w"] == 0
    assert all(h["reading"] in {"flat", "hedged", "assertive", "balanced",
                                "heavily hedged"} for h in n["hedging"])
    assert "score" not in render_narrative(n).lower()


def test_profile_shapes_the_map():
    # a commentary's unheaded body is argued like a Discussion
    text = ("Mandates work. In this study we argue that mandates must "
            "return, because uptake fell. Previous studies agree.\n")
    n = narrative(text, document_type="commentary")
    assert [s["section"] for s in n["sections"]] == ["discussion"]
    assert n["profile"] == "commentary"


def test_narrative_is_off_unless_asked():
    a = api.analyze(PAPER, nlp=NLP)
    assert a.narrative is None and "narrative" in a.to_dict()


def test_build_narrative_alone_matches_the_analysis():
    doc = Document.from_text(PAPER)
    alone = build_narrative(doc)
    with_parse = narrative(PAPER)
    assert [s["section"] for s in alone["sections"]] == \
        [s["section"] for s in with_parse["sections"]]
    assert statuses(alone, "abstract") == statuses(with_parse, "abstract")


def test_render_lists_each_section_and_the_source():
    out = render_narrative(narrative(PAPER))
    assert "NARRATIVE MAP" in out and "Discussion" in out
    assert "Source: " in out and "Swales" in out


# --- the moved modules keep their old import paths -------------------------------------

def test_old_import_paths_still_work():
    from researchly import abstract_lens, argument
    from researchly.discourse import abstract_lens as new_al
    from researchly.discourse import argument as new_arg
    assert abstract_lens.analyze is new_al.analyze
    assert argument.build_argument is new_arg.build_argument
    from researchly.engine import REGISTRY, load_rules
    load_rules()
    assert "AB802" in REGISTRY


@pytest.mark.parametrize("sentence,section,move", [
    ("We therefore set out to estimate transmission.", "introduction", "aim"),
    ("The present study quantifies the burden.", "introduction", "aim"),
    ("Few studies have measured it in rural districts.", "introduction", "gap"),
    ("Weekly counts were obtained from the registry.", "methods", "data"),
    ("The posterior was sampled by Markov chain Monte Carlo.", "methods", "analysis"),
    ("Our estimate agrees with earlier reports.", "discussion", "comparison"),
])
def test_signals_find_the_move(sentence, section, move):
    assert move in moves_mod.label_moves(sentence, section)


@pytest.mark.parametrize("sentence,section,move", [
    ("The campaign was popular.", "introduction", "gap"),
    ("We thank the district officers.", "introduction", "aim"),
])
def test_signals_stay_quiet(sentence, section, move):
    assert move not in moves_mod.label_moves(sentence, section)


# --- recall on a well-written paper (from the demo manuscript, P37) --------------------

def test_opening_sentence_counts_as_the_opening_move():
    text = ("Abstract\n\nDengue returns to the lowland districts every year, "
            "and the size of each season varies widely. However, the drivers "
            "remain unclear. We aimed to estimate transmission.\n")
    assert statuses(narrative(text), "abstract")["background"] == "present"
    cold = ("Abstract\n\nWe aimed to estimate transmission. However, the "
            "drivers remain unclear.\n")
    assert statuses(narrative(cold), "abstract")["background"] == "missing"


@pytest.mark.parametrize("sentence,section,move", [
    ("We fitted an SEIR model to one season and found that transmission, "
     "not reporting, explained the differences.", "discussion", "summary"),
    ("The estimates have one practical use.", "discussion", "implications"),
    ("It could be run at the end of each season to rank districts for "
     "vector control.", "conclusion", "implications"),
    ("The approach needs only routine weekly counts.", "conclusion",
     "contribution"),
])
def test_signals_find_the_move_in_plain_prose(sentence, section, move):
    assert move in moves_mod.label_moves(sentence, section)


def test_a_word_title_is_front_matter_not_a_section():
    doc = Document.from_word([
        {"text": "A compartmental model of one dengue season", "style": "Title"},
        {"text": "Abstract", "style": "Heading 1"},
        {"text": "Dengue returns every year. We aimed to estimate it."},
    ])
    assert [h.section for h in doc.headings] == ["front", "abstract"]
    n = api.analyze(doc, nlp=NLP, with_narrative=True).narrative
    assert [s["section"] for s in n["sections"]] == ["abstract"]
