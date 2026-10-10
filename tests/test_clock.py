"""`clock` — analogue clock faces showing a time, for teaching it.

The kind's promise is that the hands are where the time puts them, including the
one thing every lesson warns about (corpus C1, C2): the hour hand moves on with
the minutes, so at half past three it is halfway from the 3 to the 4. Every time
is also said in words under its face unless a worksheet hides the answers. The
geometry is asserted on the drawing; the document rules by the pointer of the
refusal.
"""

from __future__ import annotations

import json
import math
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.geometry import fit
from drawspec.kinds.clock import (
    ClockDrawing,
    clock_drawing,
    duration_words,
    hand_angles,
    time_words,
)
from drawspec.schema import CLOCK_MAX, READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("clock-*.json"))


def sheet(*clocks: dict[str, Any], **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "clock",
        "clocks": list(clocks) or [{"time": "3:15"}],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> ClockDrawing:
    parsed = parse_document(document)
    return fit(THEME, lambda scaled: clock_drawing(parsed, scaled, MEASURER)).value


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


# --------------------------------------------------------------------------
# The references
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_words_overlap_in_a_reference(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for one, two in combinations(drawing.texts, 2):
        apart = one[2] <= two[0] or two[2] <= one[0] or one[3] <= two[1] or two[3] <= one[1]
        assert apart, (one, two)


# --------------------------------------------------------------------------
# The hands
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("time", "hour", "minute"),
    [
        ("3:00", 90.0, 0.0),
        ("3:15", 97.5, 90.0),
        ("3:30", 105.0, 180.0),
        ("3:45", 112.5, 270.0),
        ("12:00", 0.0, 0.0),
        ("0:00", 0.0, 0.0),
        ("15:40", 110.0, 240.0),
        ("9:07", 273.5, 42.0),
    ],
)
def test_the_hands_are_where_the_time_puts_them(time: str, hour: float, minute: float) -> None:
    assert hand_angles(minutes(time)) == pytest.approx((hour, minute))


def test_half_past_puts_the_hour_hand_halfway_between_the_numbers() -> None:
    """The mistake every lesson warns about: an hour hand left on the hour."""
    drawing = drawn(sheet({"time": "7:30"}))
    hands = drawing.hands[0]
    assert hands is not None
    assert hands[0] == pytest.approx(7 * 30 + 15)


def test_a_face_with_no_time_has_no_hands() -> None:
    drawing = drawn(sheet({"text": "Draw quarter past six"}, {"time": "6:15"}))
    assert drawing.hands[0] is None
    assert drawing.hands[1] is not None
    assert drawing.readouts[0] == ""


def test_the_24_hour_clock_and_the_12_hour_clock_draw_the_same_face() -> None:
    assert hand_angles(minutes("15:40")) == hand_angles(minutes("3:40"))


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("time", "said"),
    [
        ("3:00", "three o'clock"),
        ("3:15", "quarter past three"),
        ("3:30", "half past three"),
        ("3:45", "quarter to four"),
        ("3:05", "five past three"),
        ("3:25", "twenty-five past three"),
        ("3:40", "twenty to four"),
        ("3:55", "five to four"),
        ("9:07", "seven minutes past nine"),
        ("9:01", "one minute past nine"),
        ("11:38", "twenty-two minutes to twelve"),
        ("11:59", "one minute to twelve"),
        ("12:45", "quarter to one"),
        ("0:00", "twelve o'clock"),
        ("23:30", "half past eleven"),
    ],
)
def test_the_time_in_words(time: str, said: str) -> None:
    assert time_words(minutes(time)) == said


@pytest.mark.parametrize(
    ("passed", "said"),
    [(40, "40 minutes"), (1, "1 minute"), (60, "1 hour"), (145, "2 hours 25 minutes")],
)
def test_how_long_in_words(passed: int, said: str) -> None:
    assert duration_words(passed) == said


@pytest.mark.parametrize(
    ("readout", "lines"),
    [
        ("words", "quarter past three"),
        ("digits", "15:15"),
        ("both", "quarter past three\n15:15"),
        ("none", ""),
    ],
)
def test_the_readout(readout: str, lines: str) -> None:
    assert drawn(sheet({"time": "15:15"}, readout=readout)).readouts == (lines,)


def test_since_says_how_long_and_shades_the_minute_hands_sweep() -> None:
    drawing = drawn(sheet({"time": "3:15", "since": "2:35"}))
    assert drawing.readouts[0] == "quarter past three\n40 minutes after 2:35"
    assert drawing.sweeps[0] == ("minute", pytest.approx(210.0), pytest.approx(90.0))


def test_over_an_hour_since_shades_the_hour_hands_sweep() -> None:
    drawing = drawn(sheet({"time": "5:40", "since": "3:15"}))
    sweep = drawing.sweeps[0]
    assert sweep is not None and sweep[0] == "hour"
    assert "2 hours 25 minutes after 3:15" in drawing.readouts[0]


def test_since_may_run_over_midnight() -> None:
    drawing = drawn(sheet({"time": "1:10", "since": "22:40"}))
    assert "2 hours 30 minutes after 22:40" in drawing.readouts[0]


# --------------------------------------------------------------------------
# The face
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("numerals", "first", "drawn_count"),
    [("arabic", "12", 12), ("roman", "XII", 12), ("quarters", "12", 4), ("none", "", 0)],
)
def test_the_numerals(numerals: str, first: str, drawn_count: int) -> None:
    drawing = drawn(sheet(numerals=numerals))
    assert drawing.numerals[0] == first
    assert sum(1 for text in drawing.numerals if text) == drawn_count


def test_roman_four_is_iv_as_taught() -> None:
    assert drawn(sheet(numerals="roman")).numerals[4] == "IV"


def test_faces_sit_up_to_four_to_a_row_in_even_rows() -> None:
    drawing = drawn(sheet(*({"time": f"{hour}:00"} for hour in range(1, 7))))
    rows = sorted({round(face[1]) for face in drawing.faces})
    assert len(rows) == 2
    assert [sum(1 for face in drawing.faces if round(face[1]) == row) for row in rows] == [3, 3]


def test_twelve_faces_make_three_rows_of_four() -> None:
    drawing = drawn(sheet(*({"time": f"{hour}:00"} for hour in range(1, 13))))
    assert len({round(face[1]) for face in drawing.faces}) == 3


def test_faces_do_not_overlap() -> None:
    drawing = drawn(sheet(*({"time": f"{hour}:00"} for hour in range(1, 9))))
    for one, two in combinations(drawing.faces, 2):
        assert math.dist(one[:2], two[:2]) > one[2] + two[2]


def test_too_narrow_a_canvas_is_a_fit_error() -> None:
    with pytest.raises(FitError):
        drawn(sheet(*({"time": f"{hour}:00"} for hour in range(1, 5)), width=160))


# --------------------------------------------------------------------------
# Refusals, by pointer
# --------------------------------------------------------------------------


def test_a_time_with_seconds_is_refused() -> None:
    document = sheet({"time": "9:15:30"})
    assert pointers(document) == ["/clocks/0/time"]
    assert "seconds hand" in messages(document)


@pytest.mark.parametrize("time", ["3:15 pm", "3:15pm", "9:30 a.m."])
def test_am_and_pm_are_the_24_hour_clock(time: str) -> None:
    document = sheet({"time": time})
    assert pointers(document) == ["/clocks/0/time"]
    assert "24-hour" in messages(document)


def test_a_date_is_refused() -> None:
    document = sheet({"time": "2026-10-10T09:15"})
    assert pointers(document) == ["/clocks/0/time"]
    assert "date" in messages(document)


@pytest.mark.parametrize("time", ["9.30", "9:5", "24:00", "12:60", "noon", ""])
def test_a_time_not_written_h_mm_is_refused(time: str) -> None:
    assert pointers(sheet({"time": time})) == ["/clocks/0/time"]


def test_since_without_a_time_is_refused() -> None:
    assert pointers(sheet({"since": "3:00"})) == ["/clocks/0/since"]


@pytest.mark.parametrize("since", ["3:15", "15:15", "3:16"])
def test_since_must_be_before_and_within_twelve_hours(since: str) -> None:
    document = sheet({"time": "3:15", "since": since})
    assert pointers(document) == ["/clocks/0/since"]
    assert "12 hours" in messages(document)


def test_a_bad_since_is_refused_at_its_pointer() -> None:
    assert pointers(sheet({"time": "3:15", "since": "2.30"})) == ["/clocks/0/since"]


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("seconds", "seconds hand"),
        ("date", "`timeline`"),
        ("hands", "placed by the `time`"),
        ("hour", "placed by the `time`"),
        ("numerals", "one face style per sheet"),
        ("readout", "the sheet's"),
        ("label", "`text`"),
    ],
)
def test_a_field_reached_for_on_a_face_is_refused_with_advice(name: str, says: str) -> None:
    document = sheet({"time": "3:15", name: "x"})
    assert pointers(document) == [f"/clocks/0/{name}"]
    assert says in messages(document)


@pytest.mark.parametrize(("name", "value"), [("numerals", "words"), ("readout", "spoken")])
def test_the_sheet_options_are_closed(name: str, value: str) -> None:
    assert pointers(sheet(**{name: value})) == [f"/{name}"]


def test_edges_are_refused() -> None:
    assert pointers(sheet(edges=[])) == ["/edges"]


def test_no_faces_is_refused() -> None:
    assert pointers({"version": 1, "kind": "clock", "clocks": []}) == ["/clocks"]


def test_the_budget_is_a_worksheet() -> None:
    assert dict(READABILITY_BUDGET["clock"]) == {"clocks": CLOCK_MAX}
    faces = [{"time": f"{hour}:00"} for hour in range(1, CLOCK_MAX + 1)]
    assert validate_document(sheet(*faces)) == ()
    faces.append({"time": "1:30"})
    found = validate_document(sheet(*faces))
    assert [violation.pointer for violation in found] == [f"/clocks/{CLOCK_MAX}"]
    assert "split" in found[0].message
