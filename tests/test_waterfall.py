"""`waterfall` — from one total to another, step by step (the bridge chart).

The kind's promise is arithmetic: a total stands on zero, a step floats from the
running sum before it to the sum after it, and a subtotal the author writes is
the running sum or the document is refused with the difference. The geometry is
asserted on the drawing; the document rules by the pointer of the refusal.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.waterfall import MINUS, WaterfallDrawing, waterfall_drawing
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("waterfall-*.json"))


def bridge(*bars: dict[str, Any], **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "waterfall",
        "axis": {"label": "Cash, £ thousand"},
        "bars": list(bars)
        or [
            {"text": "Opening", "total": 12.4},
            {"text": "Sales", "amount": 18.6},
            {"text": "Wages", "amount": -9.8},
            {"text": "Before tax", "total": 21.2},
            {"text": "VAT", "amount": -3.2},
            {"text": "Closing", "total": 18.0},
        ],
    }
    document.update(extra)
    return document


def deficit() -> dict[str, Any]:
    return bridge(
        {"text": "Last year", "total": -24.0},
        {"text": "Support ends", "amount": -6.0},
        {"text": "Underlying", "total": -30.0},
        {"text": "Efficiency", "amount": 12.0},
        {"text": "Plan", "total": -18.0},
    )


def drawn(document: dict[str, Any]) -> WaterfallDrawing:
    return waterfall_drawing(parse_document(document), THEME, MEASURER)


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
    assert dict(READABILITY_BUDGET["waterfall"]) == {"bars": 12}


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def test_totals_stand_on_zero_and_steps_float_on_the_running_sum() -> None:
    drawing = drawn(bridge())
    scale = (drawing.bars[0][3] - drawing.bars[0][1]) / 12.4
    opening, sales, wages, before, _, closing = drawing.bars
    for total in (opening, before, closing):
        assert total[3] == pytest.approx(drawing.zero)
    # Sales runs from 12.4 to 31.0; wages from 31.0 down to 21.2.
    assert sales[3] == pytest.approx(opening[1])
    assert sales[3] - sales[1] == pytest.approx(18.6 * scale)
    assert wages[1] == pytest.approx(sales[1])
    assert wages[3] == pytest.approx(before[1])
    assert drawing.sorts == ("total", "rise", "fall", "total", "fall", "total")


def test_a_bridge_below_zero_hangs_from_the_zero_line() -> None:
    """W1 and W3: every bar of a deficit bridge is under zero."""
    drawing = drawn(deficit())
    for box in drawing.bars:
        assert box[1] >= drawing.zero - 1e-6
    assert drawing.bars[0][1] == pytest.approx(drawing.zero)


def test_a_bridge_crossing_zero_draws_each_bar_across_it() -> None:
    document = bridge(
        {"text": "Last year", "total": 1.8},
        {"text": "Energy", "amount": -2.6},
        {"text": "Fees", "amount": 2.4},
        {"text": "This year", "total": 1.6},
    )
    drawing = drawn(document)
    energy, fees = drawing.bars[1], drawing.bars[2]
    assert energy[1] < drawing.zero < energy[3]
    assert fees[1] < drawing.zero < fees[3]


def test_connectors_join_each_bar_to_the_next_at_the_running_sum() -> None:
    drawing = drawn(bridge())
    assert len(drawing.connectors) == len(drawing.bars) - 1
    for (left, right, level), before, after in zip(
        drawing.connectors, drawing.bars[:-1], drawing.bars[1:], strict=True
    ):
        assert left == pytest.approx(before[2])
        assert right == pytest.approx(after[0])
        assert level in (pytest.approx(before[1]), pytest.approx(before[3]))


def test_every_number_is_beyond_its_bar_and_inside_its_band() -> None:
    drawing = drawn(bridge())
    for box, label in zip(drawing.bars, drawing.labels, strict=True):
        assert label[3] <= box[1] or label[1] >= box[3]
    for first, second in pairwise(drawing.labels):
        assert first[2] < second[0]


def test_a_number_never_sits_on_the_zero_line() -> None:
    """A fall ending just above zero writes its number at its top instead."""
    document = bridge(
        {"text": "Start", "total": 10},
        {"text": "Almost all", "amount": -9.9},
        {"text": "End", "total": 0.1},
    )
    drawing = drawn(document)
    label = drawing.labels[1]
    assert not label[1] <= drawing.zero <= label[3]
    assert label[3] <= drawing.bars[1][1]


def test_steps_are_signed_with_a_true_minus() -> None:
    svg = render(bridge())
    assert "+18.6" in svg
    assert f"{MINUS}9.8" in svg
    assert "-9.8" not in svg


def test_names_too_long_for_their_band_are_a_fit_error() -> None:
    bars = [{"text": "Start", "total": 1}] + [
        {"text": "Extraordinarilyunbreakable", "amount": 1} for _ in range(10)
    ]
    bars.append({"text": "End", "total": 11})
    with pytest.raises(FitError):
        drawn(bridge(*bars))


# --------------------------------------------------------------------------
# The document rules
# --------------------------------------------------------------------------


def test_a_subtotal_off_the_running_sum_is_refused_with_the_difference() -> None:
    document = bridge()
    document["bars"][3]["total"] = 21.6
    assert pointers(document) == ["/bars/3/total"]
    assert "add up to 21.2" in messages(document)
    assert "0.4 more" in messages(document)


def test_an_end_total_off_the_running_sum_is_refused() -> None:
    document = bridge()
    document["bars"][-1]["total"] = 17.5
    assert pointers(document) == ["/bars/5/total"]
    assert "0.5 less" in messages(document)


def test_a_bridge_must_start_from_a_total() -> None:
    document = bridge(
        {"text": "Sales", "amount": 5},
        {"text": "Wages", "amount": -2},
        {"text": "End", "total": 3},
    )
    assert "/bars/0/amount" in pointers(document)


def test_a_bridge_must_end_at_a_total_and_is_told_which() -> None:
    document = bridge(
        {"text": "Start", "total": 10},
        {"text": "Sales", "amount": 5},
        {"text": "Wages", "amount": -2},
    )
    assert pointers(document) == ["/bars/2"]
    assert '"total": 13' in messages(document)


def test_a_bar_is_a_total_or_an_amount() -> None:
    neither = bridge(
        {"text": "Start", "total": 10},
        {"text": "Sales"},
        {"text": "End", "total": 10},
    )
    both = bridge(
        {"text": "Start", "total": 10},
        {"text": "Sales", "amount": 5, "total": 15},
        {"text": "End", "total": 15},
    )
    assert pointers(neither) == ["/bars/1"]
    assert pointers(both) == ["/bars/1/amount"]


def test_a_step_of_nothing_and_a_repeated_total_are_refused() -> None:
    zero = bridge(
        {"text": "Start", "total": 10},
        {"text": "Nothing", "amount": 0},
        {"text": "End", "total": 10},
    )
    repeated = bridge(
        {"text": "Start", "total": 10},
        {"text": "Again", "total": 10},
        {"text": "Sales", "amount": 1},
        {"text": "End", "total": 11},
    )
    assert pointers(zero) == ["/bars/1/amount"]
    assert pointers(repeated) == ["/bars/1/total"]


def test_value_is_refused_naming_amount_and_total() -> None:
    document = bridge()
    document["bars"][1]["value"] = 18.6
    assert "/bars/1/value" in pointers(document)
    assert "`amount`" in messages(document) and "`total`" in messages(document)


@pytest.mark.parametrize(
    ("field", "hint"),
    [("series", "`chart`"), ("axes", "`chart`"), ("edges", "connectors"), ("unit", "axis label")],
)
def test_chart_fields_are_refused_with_a_reason(field: str, hint: str) -> None:
    document = bridge(**{field: []})
    assert f"/{field}" in pointers(document)
    assert hint in messages(document)


def test_subtotal_is_refused_naming_total() -> None:
    document = bridge()
    document["bars"][3]["subtotal"] = True
    assert "/bars/3/subtotal" in pointers(document)
    assert "`total` between" in messages(document)


def test_the_axis_needs_a_label() -> None:
    document = bridge()
    document["axis"] = {}
    assert "/axis/label" in pointers(document)


def test_past_twelve_bars_is_refused_with_advice() -> None:
    bars = [{"text": "Start", "total": 0}] + [
        {"text": f"Step {index}", "amount": 1} for index in range(11)
    ]
    bars.append({"text": "End", "total": 11})
    document = bridge(*bars)
    assert pointers(document) == ["/bars/12"]
    assert "subtotal" in messages(document)
