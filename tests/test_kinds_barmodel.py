"""`barmodel` — a word problem as bars of parts, every length in proportion.

The kind's one promise is the corpus's one rule: a part's length is its share of
the longest bar, in one scale for every bar, and equal units are equal. It is
asserted on the geometry. A brace spans exactly what it names, on the side the
layout gives it, and its value is checked against the parts — the document
rules are asserted by the pointer of the refusal.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.barmodel import BarmodelDrawing, barmodel_drawing
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("barmodel-*.json"))


def comparison(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "barmodel",
        "bars": [
            {"id": "a", "text": "Maya", "parts": [{"id": "pa", "amount": 45}]},
            {
                "id": "b",
                "text": "Tom",
                "parts": [{"id": "pb", "amount": 28}, {"id": "gap", "amount": 17, "text": "?"}],
            },
        ],
        "braces": [{"over": ["a"], "amount": 45}],
    }
    document.update(extra)
    return document


def ratio(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "barmodel",
        "bars": [
            {"id": "red", "text": "Red", "parts": [{"units": 3}]},
            {"id": "blue", "text": "Blue", "parts": [{"units": 5}]},
        ],
        "braces": [{"over": ["red", "blue"], "amount": 64}],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> BarmodelDrawing:
    return barmodel_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


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


def test_the_budget_is_the_corpus_size() -> None:
    assert dict(READABILITY_BUDGET["barmodel"]) == {"bars": 3, "bars/parts": 8, "braces": 6}


# --------------------------------------------------------------------------
# Lengths
# --------------------------------------------------------------------------


def test_every_length_is_in_one_scale_on_one_left_edge() -> None:
    """The comparison is read by length, so 28 must be 28/45 of 45, on one edge."""
    drawing = drawn(comparison())
    (maya,) = drawing.parts[(0, 0)]
    (tom,) = drawing.parts[(1, 0)]
    assert maya[0] == tom[0]
    assert (tom[2] - tom[0]) / (maya[2] - maya[0]) == pytest.approx(28 / 45)
    (gap,) = drawing.parts[(1, 1)]
    assert gap[2] == pytest.approx(maya[2])


def test_equal_units_are_equal_across_bars() -> None:
    drawing = drawn(ratio())
    widths = {round(box[2] - box[0], 6) for boxes in drawing.parts.values() for box in boxes}
    assert len(widths) == 1
    assert len(drawing.parts[(0, 0)]) == 3 and len(drawing.parts[(1, 0)]) == 5


def test_a_part_too_narrow_for_its_words_is_a_fit_error() -> None:
    document = comparison(
        bars=[{"parts": [{"amount": 200}, {"amount": 1, "text": "a long label"}]}], braces=[]
    )
    with pytest.raises(FitError, match="too narrow"):
        drawn(document)


# --------------------------------------------------------------------------
# Braces
# --------------------------------------------------------------------------


def test_braces_go_outside_a_pair_of_bars() -> None:
    """The first bar's brace above it, the last bar's under it — never between."""
    document = comparison(braces=[{"over": ["a"], "amount": 45}, {"over": ["gap"], "text": "?"}])
    drawing = drawn(document)
    (side_a, box_a), (side_b, box_b) = drawing.braces
    assert side_a == "above" and box_a[3] <= drawing.bars[0][1]
    assert side_b == "below" and box_b[1] >= drawing.bars[1][3]
    (gap,) = drawing.parts[(1, 1)]
    assert (box_b[0], box_b[2]) == pytest.approx((gap[0], gap[2]))


def test_a_brace_over_several_bars_stands_at_their_right() -> None:
    drawing = drawn(ratio())
    ((side, box),) = drawing.braces
    assert side == "right"
    assert box[0] > max(bar[2] for bar in drawing.bars)
    assert (box[1], box[3]) == pytest.approx((drawing.bars[0][1], drawing.bars[1][3]))


def test_braces_on_one_side_stack_and_their_words_never_touch() -> None:
    document = comparison(
        bars=[{"id": "w", "parts": [{"id": "x", "amount": 10}, {"id": "y", "amount": 10}]}],
        braces=[
            {"over": ["w"], "amount": 20, "text": "the whole of it"},
            {"over": ["x"], "amount": 10, "text": "one part of it"},
            {"over": ["y"], "amount": 10, "text": "the other part"},
        ],
    )
    drawing = drawn(document)
    for first, second in combinations(drawing.labels, 2):
        apart = (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )
        assert apart, (first, second)
    whole = drawing.braces[0][1]
    assert whole[3] <= min(box[1] for _, box in drawing.braces[1:])


# --------------------------------------------------------------------------
# Refusals, at their pointers
# --------------------------------------------------------------------------


def test_a_part_with_no_size_is_refused() -> None:
    document = comparison(bars=[{"parts": [{"amount": 3}, {"text": "?"}]}], braces=[])
    assert pointers(document) == ["/bars/0/parts/1"]
    assert '"text": "?"' in messages(document)


def test_a_part_with_two_sizes_is_refused() -> None:
    document = comparison(bars=[{"parts": [{"amount": 3}, {"amount": 2, "units": 2}]}], braces=[])
    assert pointers(document) == ["/bars/0/parts/1/units"]


def test_values_and_units_are_not_mixed() -> None:
    document = comparison(bars=[{"parts": [{"amount": 3}, {"units": 2}]}], braces=[])
    assert pointers(document) == ["/bars/0/parts/1/units"]


def test_a_brace_value_that_is_not_the_sum_is_refused() -> None:
    document = comparison(braces=[{"over": ["b"], "amount": 44}])
    assert pointers(document) == ["/braces/0/amount"]
    assert "add up to 45" in messages(document)


def test_braces_that_disagree_on_a_unit_are_refused() -> None:
    document = ratio(
        braces=[{"over": ["red", "blue"], "amount": 64}, {"over": ["red"], "amount": 30}]
    )
    assert pointers(document) == ["/braces/1/amount"]
    assert "one unit worth 10" in messages(document)


def test_a_brace_across_two_bars_parts_is_refused() -> None:
    assert pointers(comparison(braces=[{"over": ["pa", "pb"], "text": "?"}])) == ["/braces/0/over"]


def test_a_brace_over_parts_not_side_by_side_is_refused() -> None:
    document = comparison(
        bars=[{"parts": [{"id": "x", "amount": 1}, {"amount": 1}, {"id": "z", "amount": 1}]}],
        braces=[{"over": ["x", "z"], "text": "?"}],
    )
    assert pointers(document) == ["/braces/0/over"]


def test_a_brace_over_bars_not_next_to_each_other_is_refused() -> None:
    document = comparison(
        bars=[
            {"id": "x", "parts": [{"amount": 1}]},
            {"parts": [{"amount": 2}]},
            {"id": "z", "parts": [{"amount": 3}]},
        ],
        braces=[{"over": ["x", "z"], "amount": 4}],
    )
    assert pointers(document) == ["/braces/0/over"]


def test_a_brace_mixing_a_bar_and_a_part_is_refused() -> None:
    assert pointers(comparison(braces=[{"over": ["a", "gap"], "text": "?"}])) == ["/braces/0/over"]


def test_an_unknown_id_is_refused_naming_the_closest() -> None:
    document = comparison(braces=[{"over": ["gapp"], "text": "?"}])
    assert pointers(document) == ["/braces/0/over/0"]
    assert "'gap'" in messages(document)


def test_a_brace_with_nothing_to_say_is_refused() -> None:
    assert pointers(comparison(braces=[{"over": ["a"]}])) == ["/braces/0"]


def test_duplicate_ids_are_refused() -> None:
    document = comparison()
    document["bars"][1]["parts"][1]["id"] = "a"
    assert "/bars/1/parts/1/id" in pointers(document)


def test_a_single_part_says_nothing() -> None:
    document = comparison(bars=[{"parts": [{"amount": 3}]}], braces=[])
    assert pointers(document) == ["/bars/0/parts"]


def test_too_many_unit_boxes_in_a_bar_are_refused() -> None:
    document = ratio(bars=[{"parts": [{"units": 8}, {"units": 5}]}], braces=[])
    assert pointers(document) == ["/bars/0/parts/1/units"]


def test_the_budget_refuses_a_fourth_bar_and_a_ninth_part() -> None:
    bar = {"parts": [{"amount": 1}] * 9}
    document = comparison(bars=[bar, bar, bar, bar], braces=[])
    found = pointers(document)
    assert "/bars/3" in found
    assert "/bars/0/parts/8" in found
    assert "one bar can be read at" in messages(document)


@pytest.mark.parametrize(("field", "named"), [("edges", "joins nothing"), ("axes", "`chart`")])
def test_fields_from_other_kinds_are_refused_by_name(field: str, named: str) -> None:
    document = comparison(**{field: []})
    assert pointers(document) == [f"/{field}"]
    assert named in messages(document)


def test_a_total_on_a_bar_is_refused_naming_a_brace() -> None:
    document = comparison()
    document["bars"][0]["total"] = 45
    assert pointers(document) == ["/bars/0/total"]
    assert "brace" in messages(document)


def test_value_is_refused_naming_amount() -> None:
    """`value` is refused in every document; a bar model says what to write instead."""
    document = comparison()
    document["bars"][0]["parts"][0]["value"] = 45
    assert "/bars/0/parts/0/value" in pointers(document)
    assert "`amount`" in messages(document)
