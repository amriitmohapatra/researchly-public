"""The web app's reading key must teach what the engine actually does.

The key shows one specimen per category. Its first version showed "seven day
window" as a Convention and "utilize" as a Preference; the engine flags
neither that way (no rule fires on the first, W201 calls the second an
Improvement), so the key taught users something false. The specimens now live
in packages/contract/reading-key.json and this test runs each through
api.analyze.
"""

import json
from pathlib import Path

import pytest

from researchly import api

KEY = Path(__file__).resolve().parents[2] / "contract" / "reading-key.json"
SPECIMENS = {k: v for k, v in json.loads(KEY.read_text()).items()
             if not k.startswith("_")}


def test_key_covers_the_four_categories():
    assert set(SPECIMENS) == {"correction", "improvement", "convention",
                              "preference"}


@pytest.mark.parametrize("category", sorted(SPECIMENS))
def test_specimen_is_flagged_with_its_category(category):
    s = SPECIMENS[category]
    text = s["before"] + s["flagged"] + s["after"]
    start = len(s["before"])
    end = start + len(s["flagged"])

    result = api.analyze(text, show_preferences=True, with_metrics=False)
    on_span = [(x.rule_id, x.category.value) for x in result.suggestions
               if x.start == start and x.end == end]
    assert on_span, f"no suggestion on {s['flagged']!r} in {text!r}"
    assert {c for _, c in on_span} == {category}, on_span
