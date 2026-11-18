"""`pie` — the shares of one known total, as labelled sectors of a circle.

The kind's promises: every angle is its part's share of the sum of the amounts,
clockwise from twelve with the remainder last; every sector carries its own
label, inside it or on a leader that does not cross the circle; touching
sectors never share a fill; and percentages are checked to make 100. A donut is
a theme's choice, not a document's.
"""

from __future__ import annotations

import json
import math
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import ThemeError
from drawspec.kinds.pie import PieDrawing, _cuts_circle, pie_drawing
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
DONUT = load_theme({"version": 1, "pie": {"shape": "donut"}})
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("pie-*.json"))


def travel(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "pie",
        "unit": "pupils",
        "parts": [
            {"text": "Walk", "amount": 12},
            {"text": "Car", "amount": 8},
            {"text": "Bus", "amount": 6},
            {"text": "Bike", "amount": 4},
        ],
    }
    document.update(extra)
    return document


def spending(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "pie",
        "unit": "%",
        "parts": [
            {"text": "Everything else", "amount": 22, "role": "note"},
            {"text": "Social protection", "amount": 27},
            {"text": "Health", "amount": 20},
            {"text": "Education", "amount": 10},
            {"text": "Debt interest", "amount": 8},
            {"text": "Defence", "amount": 5},
            {"text": "Transport", "amount": 4},
            {"text": "Public order", "amount": 4},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> PieDrawing:
    return pie_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def overlap(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


# --------------------------------------------------------------------------
# The references
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


def test_there_are_references_for_every_use_case() -> None:
    assert len(REFERENCES) >= 3


def test_the_budget_is_eight_parts() -> None:
    assert dict(READABILITY_BUDGET["pie"]) == {"parts": 8}


# --------------------------------------------------------------------------
# Angles
# --------------------------------------------------------------------------


def test_each_angle_is_its_share_clockwise_from_twelve() -> None:
    """12 of 30 pupils is 144 degrees: the P1 booklet's arithmetic."""
    drawing = drawn(travel())
    assert drawing.angles[0] == pytest.approx((0.0, 144.0))
    assert drawing.angles[1] == pytest.approx((144.0, 240.0))
    assert drawing.angles[-1][1] == pytest.approx(360.0)
    for (_, end), (start, _) in pairwise(drawing.angles):
        assert end == pytest.approx(start)


def test_the_remainder_is_drawn_last_whatever_the_order_written() -> None:
    drawing = drawn(spending())
    assert drawing.order[-1] == 0
    assert drawing.angles[-1][1] == pytest.approx(360.0)
    assert drawing.fills[-1] == ""


# --------------------------------------------------------------------------
# Labels and fills
# --------------------------------------------------------------------------


@pytest.mark.parametrize("document", [travel(), spending()], ids=["travel", "spending"])
def test_no_two_labels_touch(document: dict[str, Any]) -> None:
    labels = drawn(document).labels
    for index, first in enumerate(labels):
        for second in labels[index + 1 :]:
            assert not overlap(first, second)


def test_an_inside_label_sits_inside_the_circle() -> None:
    drawing = drawn(travel())
    cx, cy = drawing.centre
    assert all(drawing.inside)
    for left, top, right, bottom in drawing.labels:
        for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
            assert math.hypot(x - cx, y - cy) < drawing.radius


def test_a_small_sector_is_labelled_outside_on_a_leader_that_clears_the_circle() -> None:
    drawing = drawn(spending())
    assert not all(drawing.inside)
    assert len(drawing.leaders) == drawing.inside.count(False)
    for leader in drawing.leaders:
        for first, second in pairwise(leader[1:]):
            assert not _cuts_circle(first, second, drawing.centre, drawing.radius)
    for label, inside in zip(drawing.labels, drawing.inside, strict=True):
        if not inside:
            assert label[2] < drawing.centre[0] - drawing.radius or (
                label[0] > drawing.centre[0] + drawing.radius
            )


def test_touching_sectors_never_share_a_fill() -> None:
    """Five fills and six sectors: the turn would give the last the first's fill."""
    document = travel(
        parts=[{"text": f"Part {index}", "amount": 10} for index in range(6)],
    )
    fills = drawn(document).fills
    for first, second in pairwise((*fills, fills[0])):
        assert first != second


def test_every_sector_carries_its_name_and_amount() -> None:
    svg = render(travel())
    for words in ("Walk", "12 pupils", "Bike", "4 pupils"):
        assert words in svg


def test_values_false_writes_the_names_alone() -> None:
    svg = render(travel(values=False))
    assert "Walk" in svg and "pupils" not in svg


def test_a_donut_has_a_hole_and_every_label_outside() -> None:
    drawing = drawn(travel(), DONUT)
    assert drawing.hole == pytest.approx(drawing.radius * 0.55)
    assert not any(drawing.inside)


def test_an_unknown_shape_is_a_theme_error() -> None:
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "pie": {"shape": "ring"}})


# --------------------------------------------------------------------------
# The document rules
# --------------------------------------------------------------------------


def test_percentages_must_make_100_within_rounding() -> None:
    assert validate_document(spending()) == ()
    rounded = spending()
    rounded["parts"][1]["amount"] = 28  # 101: rounding
    assert validate_document(rounded) == ()
    off = spending()
    off["parts"][1]["amount"] = 30  # 103
    assert pointers(off) == ["/parts"]
    assert "add up to 103" in messages(off) and "3 over" in messages(off)


def test_counts_are_not_held_to_100() -> None:
    assert validate_document(travel()) == ()


def test_a_sliver_is_refused_naming_the_remainder() -> None:
    document = travel()
    document["parts"].append({"text": "Scooter", "amount": 0.5})
    assert pointers(document) == ["/parts/4/amount"]
    assert '"role": "note"' in messages(document)


def test_one_remainder_only() -> None:
    document = spending()
    document["parts"][2]["role"] = "note"
    assert pointers(document) == ["/parts/2/role"]


def test_past_eight_parts_is_refused_with_advice() -> None:
    document = travel(parts=[{"text": f"Area {index}", "amount": 10} for index in range(9)])
    assert pointers(document) == ["/parts/8"]
    assert "Everything else" in messages(document)


def test_a_single_part_is_refused() -> None:
    document = travel(parts=[{"text": "All", "amount": 30}])
    assert pointers(document) == ["/parts"]
    assert "one part of a total is the total" in messages(document)


@pytest.mark.parametrize(
    ("field", "hint"),
    [
        ("value", "`amount`"),
        ("percent", '"unit": "%"'),
        ("share", '"unit": "%"'),
        ("angle", "computed"),
    ],
)
def test_written_shares_are_refused_with_a_reason(field: str, hint: str) -> None:
    document = travel()
    document["parts"][0][field] = 40
    assert f"/parts/0/{field}" in pointers(document)
    assert hint in messages(document)


@pytest.mark.parametrize(
    ("field", "hint"),
    [
        ("total", "sum of its amounts"),
        ("groups", "`treemap`"),
        ("series", "`chart`"),
        ("axes", "`chart`"),
        ("donut", "[pie] shape"),
        ("hole", "[pie] shape"),
        ("edges", "nothing to connect"),
    ],
)
def test_other_fields_are_refused_with_a_reason(field: str, hint: str) -> None:
    document = travel(**{field: True})
    assert f"/{field}" in pointers(document)
    assert hint in messages(document)
