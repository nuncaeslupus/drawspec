"""`[box] lead = "rule"` — a box that is a name over what belongs to it.

The format has always let a label say *these are two things*: a blank-free
newline in `text`, and `[box] lead` deciding what tells them apart. There were
two answers, `bold` and `plain`, and both are a weight on the first part. Weight
says *this one matters more*, which is right when the second line explains the
first and wrong when the second part is a **list of things belonging to** the
first — the attributes of a class, the fields of a record, who performs a step.

A rule says that instead, and it is what every hand-drawn class box already
does. No new field: the author writes the same newline they always did.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

import pytest

from drawspec.geometry import Box, size_box
from drawspec.kinds.common import lead_rule
from drawspec.scene import Path
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

THEME: Final = load_theme()
RULED: Final = load_theme("compartment")
MEASURER: Final = TextMeasurer(THEME.font.stacks(), search_paths=[])

COMPARTMENTS: Final = "**Payment**\nreference\namount"


def box(text: str = COMPARTMENTS, *, role: str = "step", theme: Theme = RULED) -> Box:
    return size_box(text, theme=theme, measurer=MEASURER, role=role, max_width=260.0)


def rule_of(text: str = COMPARTMENTS, *, role: str = "step", theme: Theme = RULED) -> Path:
    drawn = lead_rule(box(text, role=role, theme=theme))
    assert len(drawn) == 1, "expected exactly one rule"
    assert isinstance(drawn[0], Path)
    return drawn[0]


# -- the bundled theme is the only one that draws one -------------------------


def test_the_default_theme_still_sets_a_lead_in_bold_and_draws_no_rule() -> None:
    """The treatment this replaces for nobody: `bold` is still the default, and a
    document that relied on it is untouched."""
    assert THEME.box.lead == "bold"
    plain = box(theme=THEME)

    assert lead_rule(plain) == ()
    assert all(span.weight == "bold" for span in plain.block.lines[0].spans)


def test_the_compartment_theme_draws_one() -> None:
    assert RULED.box.lead == "rule"
    assert len(lead_rule(box())) == 1


def test_a_label_with_one_part_gets_no_rule() -> None:
    """A box that did not ask for two compartments does not get a divider."""
    assert lead_rule(box("Sign off the release")) == ()


# -- where it sits ------------------------------------------------------------


def test_the_rule_sits_between_the_lead_and_the_detail() -> None:
    """Between the two baselines it separates, which is the whole of its job."""
    sized = box()
    rule = rule_of()
    baselines = sized.baselines()

    y = rule.points[0][1]
    assert baselines[0] < y < baselines[1]


def test_the_rule_is_level() -> None:
    rule = rule_of()
    assert rule.points[0][1] == pytest.approx(rule.points[1][1])


def test_the_rule_runs_edge_to_edge_in_a_rect() -> None:
    """Which is the look: a hand-drawn class box's rule touches both sides."""
    sized = box()
    rule = rule_of()

    assert rule.points[0][0] == pytest.approx(sized.x)
    assert rule.points[1][0] == pytest.approx(sized.x + sized.width)


def test_the_rule_stops_inside_a_shape_that_is_not_a_rect() -> None:
    """A diamond's sides slope, so edge to edge at that height is narrower than
    the box — and a rule drawn to the box would come out of them."""
    sized = box(role="decision")
    rule = rule_of(role="decision")

    assert rule.points[0][0] > sized.x
    assert rule.points[1][0] < sized.x + sized.width


def test_the_rule_is_drawn_in_the_box_s_own_ink() -> None:
    """So it inherits that role's weight and dash, and survives greyscale the way
    every other mark in the drawing does."""
    assert rule_of(role="terminal").role == "terminal"


# -- and the box paid for it --------------------------------------------------


def test_the_box_reserves_room_for_the_rule_rather_than_being_drawn_through() -> None:
    """A rule a box did not count is a rule through a word."""
    ruled = box()
    unruled = box(theme=replace(RULED, box=replace(RULED.box, lead="plain")))

    assert len(ruled.block.lines) == len(unruled.block.lines)
    assert ruled.height == pytest.approx(unruled.height + THEME.box.padding.top)


def test_the_rule_clears_the_text_above_and_below_it_by_the_same_gap() -> None:
    """Half the band each side, so the two compartments read as peers."""
    sized = box()
    y = rule_of().points[0][1]
    block = sized.block

    above = y - (sized.baselines()[0] + block.descent)
    below = (sized.baselines()[1] - block.ascent) - y
    assert above == pytest.approx(below, abs=0.5)
    assert above > 0
