"""Every suggestion must name a source a student could look up (CLAUDE.md #6).

The S1 end-to-end run against the real engine showed cards whose source read
only "§4" or "§8" — internal shorthand for sections of the founding guide,
meaningless to anyone else. Rules keep their short codes; the registry
expands them into full citations through researchly/sources.py.
"""

import re

import pytest

from researchly import api, sources
from researchly.engine import REGISTRY


@pytest.fixture(scope="module", autouse=True)
def _rules():
    api.ensure_rules_loaded()


def test_every_rule_source_is_a_full_citation():
    for r in REGISTRY.values():
        assert not re.fullmatch(r"[§\w.+\- ]{1,12}", r.source), (r.id, r.source)
        assert len(r.source) >= 15, (r.id, r.source)


def test_guide_sections_are_named_not_just_numbered():
    cited = sources.cite("§4")
    assert "The Craft of Scientific Writing" in cited
    assert "Warranting" in cited
    # Named, never numbered: no reader can look up a section number.
    assert "§" not in cited


def test_composite_codes_cite_every_part():
    cited = sources.cite("§6+lecture")
    # The lecture is shown to users as the owner's learnings (P35), never
    # by the lecturer's name.
    assert "The Craft of Scientific Writing" in cited
    assert sources.LEARNINGS in cited and "lecture" not in cited


def test_unknown_code_fails_loudly():
    with pytest.raises(KeyError):
        sources.cite("§99")


def test_suggestions_carry_the_expanded_citation():
    a = api.analyze("Discussion\n\nIt is clearly proven that this works.",
                    kind="plain")
    hits = [s for s in a.suggestions if s.rule_id in ("C302", "C301", "C305")]
    assert hits and all("The Craft of Scientific Writing" in s.source for s in hits)


def test_no_citation_a_user_sees_carries_a_section_number():
    from researchly import learn, packs
    from researchly.discourse import moves
    cites = [r.source for r in REGISTRY.values()]
    cites += [c.citation for c in learn.CARDS.values()]
    cites += [m.citation for m in moves.MOVES.values()]
    cites += [c.citation for c in packs.checklists().values()]
    assert [c for c in cites if "§" in c] == []


def test_several_guide_sections_name_the_guide_once():
    both = sources.cite("§4+§9.3")
    assert both.count(sources.GUIDE) == 1
    assert sources.GUIDE_SECTIONS["4"] in both and sources.GUIDE_SECTIONS["9.3"] in both
    # A section cited twice is listed once; other works keep their place.
    mixed = sources.cite("WW+§4+§4")
    assert mixed.count(sources.GUIDE_SECTIONS["4"]) == 1
    assert mixed.startswith(sources.WORKS["WW"])
