"""`meter` — one amount against its scale: a progress bar, a thermometer, a dial, a bullet.

The kind's promise is that a reading is where its number says, on its own
meter's scale, and that every number is also said in words: the readout carries
the amount, the band it is in and the target, so no reading depends on a fill or
a tone. The geometry is asserted on the drawing; the document rules by the
pointer of the refusal.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.geometry import fit
from drawspec.kinds.meter import MINUS, MeterDrawing, meter_drawing, number
from drawspec.schema import (
    METER_BAND_MAX,
    METER_MAX,
    READABILITY_BUDGET,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("meter-*.json"))


def panel(*meters: dict[str, Any], style: str | None = None, **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "meter",
        "meters": list(meters) or [{"text": "Chapters drafted", "amount": 7, "max": 12}],
    }
    if style is not None:
        document["style"] = style
    document.update(extra)
    return document


def bands(*ends: float, words: tuple[str, ...] = ("Poor", "Fair", "Good")) -> list[dict[str, Any]]:
    return [{"text": word, "to": end} for word, end in zip(words, ends, strict=True)]


def drawn(document: dict[str, Any]) -> MeterDrawing:
    parsed = parse_document(document)
    return fit(THEME, lambda scaled: meter_drawing(parsed, scaled, MEASURER)).value


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


def test_there_is_a_reference_for_every_style() -> None:
    styles = {
        json.loads(path.read_text(encoding="utf-8")).get("style", "bar") for path in REFERENCES
    }
    assert styles == {"bar", "thermometer", "dial", "bullet"}


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_words_in_a_reference_overlap(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for one, two in combinations(drawing.words, 2):
        assert not (one[0] < two[2] and two[0] < one[2] and one[1] < two[3] and two[1] < one[3]), (
            f"{one} overlaps {two}"
        )


def test_the_budget_is_six_meters_of_five_bands() -> None:
    assert dict(READABILITY_BUDGET["meter"]) == {
        "meters": METER_MAX,
        "meters/bands": METER_BAND_MAX,
    }
    assert (METER_MAX, METER_BAND_MAX) == (6, 5)


# --------------------------------------------------------------------------
# Readings in the right place
# --------------------------------------------------------------------------


def test_a_bar_fills_to_its_share_of_the_track() -> None:
    drawing = drawn(panel({"text": "Done", "amount": 30, "max": 120, "target": 90}))
    left, _, right, _ = drawing.tracks[0]
    assert drawing.readings[0] == pytest.approx(left + (right - left) * 0.25)
    assert drawing.targets[0] == pytest.approx(left + (right - left) * 0.75)


def test_bars_in_a_panel_share_one_track() -> None:
    """The tracks line up so the eye runs down them, whatever their scales."""
    drawing = drawn(
        panel(
            {"text": "Short", "amount": 3, "max": 10},
            {"text": "A much longer name\nwith a caption", "amount": 400, "max": 1000},
        )
    )
    first, second = drawing.tracks
    assert (first[0], first[2]) == pytest.approx((second[0], second[2]))
    assert second[1] > first[3], "one row under the other"


def test_a_thermometer_rises_from_zero_to_its_goal() -> None:
    drawing = drawn(
        panel({"text": "Appeal", "amount": 15000, "max": 60000, "unit": "£"}, style="thermometer")
    )
    _, top, _, zero = drawing.tracks[0]
    assert drawing.readings[0] == pytest.approx(zero - (zero - top) * 0.25)


def test_thermometers_stand_side_by_side_at_one_height() -> None:
    drawing = drawn(
        panel(
            {"text": "Roof", "amount": 10, "max": 40},
            {"text": "Organ", "amount": 30, "max": 30},
            style="thermometer",
        )
    )
    first, second = drawing.tracks
    assert (first[1], first[3]) == pytest.approx((second[1], second[3]))
    assert second[0] > first[2]


def test_a_dial_needle_points_at_its_reading_from_min_to_max() -> None:
    drawing = drawn(
        panel({"text": "Load", "amount": 25, "min": -25, "max": 75, "target": 50}, style="dial")
    )
    assert drawing.readings[0] == pytest.approx(90.0)
    assert drawing.targets[0] == pytest.approx(45.0)


def test_dials_past_three_wrap_to_a_second_row() -> None:
    meters = [{"text": f"Dial {n}", "amount": n, "max": 10} for n in range(1, 5)]
    drawing = drawn(panel(*meters, style="dial"))
    rows = sorted({round(track[3], 3) for track in drawing.tracks})
    assert len(rows) == 2, "four dials are two rows of two"


def test_a_bullet_draws_its_bands_in_order_with_their_words() -> None:
    drawing = drawn(
        panel(
            {
                "text": "Visits",
                "amount": 182,
                "max": 240,
                "target": 200,
                "bands": bands(150, 190, 240),
            },
            style="bullet",
        )
    )
    words = drawing.bands[0]
    assert len(words) == 3
    assert [box[0] for box in words] == sorted(box[0] for box in words)
    left, top, right, _ = drawing.tracks[0]
    assert all(box[3] <= top for box in words), "the words sit over the track"
    assert all(left <= box[0] and box[2] <= right for box in words)


# --------------------------------------------------------------------------
# The readout says every number
# --------------------------------------------------------------------------


def test_the_readout_names_the_band_and_the_target() -> None:
    drawing = drawn(
        panel(
            {
                "text": "Seen in 4 hours",
                "amount": 78,
                "min": 50,
                "max": 100,
                "unit": "%",
                "target": 95,
                "bands": bands(85, 95, 100, words=("Red", "Amber", "Green")),
            },
            style="dial",
        )
    )
    assert drawing.readouts[0] == "78%\nRed\ntarget 95%"


def test_a_reading_on_a_band_boundary_is_in_the_band_above() -> None:
    drawing = drawn(
        panel({"text": "X", "amount": 85, "max": 100, "bands": bands(85, 95, 100)}, style="bullet")
    )
    assert drawing.readouts[0].splitlines()[1] == "Fair"


def test_a_bar_says_how_much_of_what() -> None:
    drawing = drawn(
        panel(
            {"text": "Training", "amount": 23, "max": 30, "unit": "sessions"},
            {"text": "Appeal", "amount": 41250, "max": 60000, "unit": "£"},
            {"text": "Mapping", "amount": 64, "max": 100, "unit": "%"},
        )
    )
    assert drawing.readouts == ("23 of 30 sessions", "£41,250 of £60,000", "64%")


def test_numbers_are_grouped_signed_with_a_true_minus_and_unit_placed() -> None:
    assert number(1234567) == "1,234,567"
    assert number(-4.5, "°C") == f"{MINUS}4.5 °C"
    assert number(-20, "$") == f"{MINUS}$20"
    assert number(12.5, "%") == "12.5%"


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_an_amount_outside_the_scale_is_refused() -> None:
    document = panel({"text": "Over", "amount": 61000, "max": 60000}, style="thermometer")
    assert pointers(document) == ["/meters/0/amount"]
    assert "full thermometer" in messages(document)


def test_a_target_outside_the_scale_is_refused() -> None:
    assert pointers(panel({"text": "X", "amount": 3, "max": 10, "target": 12})) == [
        "/meters/0/target"
    ]


def test_min_is_for_dials_only() -> None:
    document = panel({"text": "X", "amount": 3, "min": 1, "max": 10})
    assert pointers(document) == ["/meters/0/min"]
    assert "dial" in messages(document)
    assert pointers(panel({"text": "X", "amount": 3, "min": 1, "max": 10}, style="dial")) == []


def test_max_must_be_above_min() -> None:
    assert pointers(panel({"text": "X", "amount": 3, "min": 5, "max": 5}, style="dial")) == [
        "/meters/0/max"
    ]


def test_bands_on_a_bar_point_to_bullet() -> None:
    document = panel({"text": "X", "amount": 3, "max": 10, "bands": bands(3, 6, 10)})
    assert pointers(document) == ["/meters/0/bands"]
    assert '"style": "bullet"' in messages(document)


def test_bands_on_a_thermometer_are_refused() -> None:
    document = panel(
        {"text": "X", "amount": 3, "max": 10, "bands": bands(3, 6, 10)}, style="thermometer"
    )
    assert pointers(document) == ["/meters/0/bands"]


def test_a_bullet_needs_bands() -> None:
    document = panel({"text": "X", "amount": 3, "max": 10}, style="bullet")
    assert pointers(document) == ["/meters/0"]
    assert '"style": "bar"' in messages(document)


def test_bands_must_rise_and_end_at_max() -> None:
    falling = panel({"text": "X", "amount": 3, "max": 10, "bands": bands(6, 4, 10)}, style="dial")
    assert pointers(falling) == ["/meters/0/bands/1/to"]
    short = panel({"text": "X", "amount": 3, "max": 10, "bands": bands(3, 6, 9)}, style="dial")
    assert pointers(short) == ["/meters/0/bands/2/to"]


def test_a_single_band_is_refused() -> None:
    document = panel(
        {"text": "X", "amount": 3, "max": 10, "bands": [{"text": "All", "to": 10}]}, style="dial"
    )
    assert pointers(document) == ["/meters/0/bands"]


@pytest.mark.parametrize(
    ("field", "hint"),
    [("value", "amount"), ("goal", "max"), ("style", "one style"), ("percent", "unit")],
)
def test_fields_an_author_reaches_for_are_refused_with_a_reason(field: str, hint: str) -> None:
    document = panel({"text": "X", "amount": 3, "max": 10, field: "bar"})
    assert pointers(document) == [f"/meters/0/{field}"]
    assert hint in messages(document)


def test_a_band_from_is_refused() -> None:
    document = panel(
        {
            "text": "X",
            "amount": 3,
            "max": 10,
            "bands": [{"text": "Low", "from": 0, "to": 5}, {"text": "High", "to": 10}],
        },
        style="dial",
    )
    assert pointers(document) == ["/meters/0/bands/0/from"]
    assert "end of the one before" in messages(document)


@pytest.mark.parametrize("field", ["series", "axes", "edges"])
def test_chart_fields_are_refused(field: str) -> None:
    document = panel()
    document[field] = []
    assert pointers(document) == [f"/{field}"]


def test_an_unknown_style_is_refused() -> None:
    assert pointers(panel(style="gauge")) == ["/style"]


def test_past_six_meters_is_refused_with_advice() -> None:
    meters = [{"text": f"M{n}", "amount": 1, "max": 2} for n in range(7)]
    document = panel(*meters)
    assert pointers(document) == ["/meters/6"]
    assert "dashboard" in messages(document)


def test_past_five_bands_is_refused() -> None:
    many = [{"text": f"B{n}", "to": n + 1} for n in range(6)]
    document = panel({"text": "X", "amount": 3, "max": 6, "bands": many}, style="dial")
    assert pointers(document) == ["/meters/0/bands/5"]
    assert "tones blur" in messages(document)


def test_two_emphasised_meters_are_the_cap() -> None:
    meters = [{"text": f"M{n}", "amount": 1, "max": 2, "role": "emphasis"} for n in range(3)]
    assert pointers(panel(*meters))


def test_band_words_too_long_for_a_bullet_band_are_a_fit_error() -> None:
    document = panel(
        {
            "text": "X",
            "amount": 3,
            "max": 100,
            "bands": [
                {"text": "Considerably below expectations", "to": 2},
                {"text": "Fine", "to": 100},
            ],
        },
        style="bullet",
    )
    with pytest.raises(FitError):
        drawn(document)
