"""Discipline packs (S4, P3): reporting checklists, checked against the
text. Reporting only, never the science. Synthetic text only."""

import pytest

from researchly import api, packs
from tests.test_explanations import INTERNAL

NLP = api.get_nlp()

FORECAST = """Abstract

We forecast weekly dengue cases in three districts to inform the public health response.

Introduction

Dengue remains a major burden. We aimed to forecast weekly incidence four weeks ahead.

Methods

Weekly case counts were obtained from the national surveillance system. We corrected for reporting delays with a nowcast. We fitted a renewal model and assumed a gamma-distributed generation interval. Priors on the parameters were taken from earlier studies. Forecast accuracy was assessed with the weighted interval score against a naive baseline. Code is available on GitHub.

Results

Forecasts covered 92% of observations within their 95% prediction intervals.

Discussion

Our forecasts may not generalise to larger outbreaks. A limitation is that reporting changed during the season. This work was funded by a national research grant.
"""


def check(text, cid):
    return api.analyze(text, nlp=NLP, checklist=cid).checklist


def test_registry_items_are_explained_and_clean():
    for c in packs.checklists().values():
        assert len(c.items) >= 12 and c.citation
        ids = [i.id for i in c.items]
        assert len(ids) == len(set(ids))
        for it in c.items:
            assert it.question.endswith("?")
            for field in (it.question, it.plain, it.topic):
                assert not INTERNAL.search(field), (c.id, it.id, field)
            assert it.signals


def test_listing_names_every_checklist():
    assert [c["id"] for c in packs.listing()] == [
        "strobe", "consort", "prisma", "epiforge"]


@pytest.mark.parametrize("text,expected", [
    ("We conducted a retrospective cohort study of 4,000 adults.", "strobe"),
    ("In this randomised controlled trial, participants were randomly "
     "assigned to two arms.", "consort"),
    ("We conducted a systematic review and meta-analysis of trials.", "prisma"),
    ("We report forecasts of weekly cases for the next month.", "epiforge"),
    ("We fitted a model to the data.", None),
])
def test_the_text_suggests_its_checklist(text, expected):
    assert packs.suggest(text) == expected


def test_a_complete_forecast_paper_reports_most_items():
    c = check(FORECAST, "epiforge")
    st = {i["id"]: i["status"] for i in c["items"]}
    for item in ("design", "purpose", "horizon", "data", "data-issues",
                 "model", "assumptions", "parameters", "uncertainty",
                 "evaluation", "baseline", "code", "limitations", "funding"):
        assert st[item] == "reported", item
    hor = next(i for i in c["items"] if i["id"] == "horizon")
    assert "four weeks ahead" in hor["evidence"]
    assert c["suggested"] is True and c["reported"] <= c["total"]


def test_an_item_not_reported_is_a_prompt_with_its_question():
    text = FORECAST.replace("Code is available on GitHub.", "")
    c = check(text, "epiforge")
    code = next(i for i in c["items"] if i["id"] == "code")
    assert code["status"] == "needs_check" and code["evidence"] is None
    assert code["question"].endswith("?") and "supplement" in c["note"]


def test_items_are_looked_for_in_their_sections():
    # "assumed" in the Discussion does not report the Methods' assumptions
    text = ("Methods\n\nWe fitted a renewal model.\n\nDiscussion\n\n"
            "We assumed too much.\n")
    c = check(text, "epiforge")
    st = {i["id"]: i["status"] for i in c["items"]}
    assert st["assumptions"] == "needs_check"


def test_auto_uses_the_suggestion_and_nothing_when_there_is_none():
    assert check(FORECAST, "auto")["id"] == "epiforge"
    a = api.analyze("Methods\n\nWe fitted a model.\n", nlp=NLP, checklist="auto")
    assert a.checklist is None and a.suggested_checklist is None


def test_off_unless_asked_but_the_suggestion_is_always_there():
    a = api.analyze(FORECAST, nlp=NLP)
    assert a.checklist is None and a.suggested_checklist == "epiforge"


def test_unknown_checklist_is_nothing():
    assert check(FORECAST, "poem") is None


def test_an_unheaded_text_is_searched_whole():
    c = check("We report forecasts of weekly cases four weeks ahead, with "
              "95% prediction intervals.\n", "epiforge")
    st = {i["id"]: i["status"] for i in c["items"]}
    assert st["horizon"] == "reported" and st["uncertainty"] == "reported"
