"""`numberline` — values and ranges on one scale, each end in or out.

The kind's content is three facts per range — where each end is, whether it
belongs to the range, and which way the range runs on — so each is asserted on
the geometry: an end's mark is centred exactly on its value, a closed end is a
filled dot (or `[`), an open one a ring (or `(`), and a missing end an arrow. A
point's words never touch another's, and a leader never crosses words. The
document rules are asserted by the pointer of the refusal.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError, ThemeError
from drawspec.kinds import scene_for
from drawspec.kinds.numberline import NumberlineDrawing, numberline_drawing
from drawspec.scene import Ellipse, TextLine
from drawspec.scene import Path as Stroke
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
BRACKETS = load_theme({"version": 1, "numberline": {"ends": "brackets"}})
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("numberline-*.json"))


def inequality(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "numberline",
        "axis": {"min": -5, "max": 6, "step": 1},
        "ranges": [{"from": -3, "to": 4, "to_open": True, "text": "x", "role": "emphasis"}],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> NumberlineDrawing:
    return numberline_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def dots_at(drawing: NumberlineDrawing, y: float) -> list[Ellipse]:
    return [
        primitive
        for primitive in drawing.scene.primitives
        if isinstance(primitive, Ellipse) and abs(primitive.cy - y) < 1e-6
    ]


# --------------------------------------------------------------------------
# The references
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document, theme=document.get("theme")).startswith("<svg")


def test_there_are_references_for_every_use_case() -> None:
    assert len(REFERENCES) >= 3


def test_the_ph_scale_is_inside_the_budget_and_at_the_point_limit() -> None:
    """The largest real figure the corpus found sets the point budget."""
    document = json.loads((REFERENCE / "numberline-ph.json").read_text(encoding="utf-8"))
    limits = dict(READABILITY_BUDGET["numberline"])
    assert len(document["points"]) == limits["points"] == 15


# --------------------------------------------------------------------------
# Ends: where they are, and what they say
# --------------------------------------------------------------------------


def test_a_closed_end_is_a_filled_dot_centred_on_its_tick() -> None:
    drawing = drawn(inequality())
    left, _, y = drawing.tracks[0]
    assert left == pytest.approx(drawing.scale.to_pixels(-3))
    (closed,) = [dot for dot in dots_at(drawing, y) if abs(dot.cx - left) < 1e-6]
    assert closed.fill == "solid"
    assert drawing.ends[0] == ("dot", "ring")


def test_an_open_end_is_a_ring_the_line_stops_at() -> None:
    drawing = drawn(inequality())
    _, right, y = drawing.tracks[0]
    assert right == pytest.approx(drawing.scale.to_pixels(4))
    (ring,) = [dot for dot in dots_at(drawing, y) if abs(dot.cx - right) < 1e-6]
    assert ring.fill == ""
    bar = max(
        (
            point[0]
            for primitive in drawing.scene.primitives
            if hasattr(primitive, "points")
            for point in primitive.points
            if abs(point[1] - y) < 5
        ),
    )
    assert bar <= right - ring.rx + 1e-6


def test_a_missing_end_runs_on_as_an_arrow_with_no_dot() -> None:
    drawing = drawn(inequality(ranges=[{"from": 1, "from_open": True, "text": "x > 1"}]))
    left, right, y = drawing.tracks[0]
    assert right == drawing.scene.width
    assert drawing.ends[0] == ("ring", "arrow")
    assert [dot.cx for dot in dots_at(drawing, y)] == [pytest.approx(left)]


def test_the_brackets_theme_draws_brackets_for_the_same_document() -> None:
    """The fact is in the document; the mark is the course's convention."""
    drawing = drawn(inequality(), BRACKETS)
    assert drawing.ends[0] == ("[", "(")
    assert dots_at(drawing, drawing.tracks[0][2]) == []


def test_a_point_is_a_dot_under_either_convention() -> None:
    document = inequality(points=[{"at": 0, "open": True}])
    for theme in (THEME, BRACKETS):
        drawing = drawn(document, theme)
        assert drawing.dots[0][3] is True
        assert len(dots_at(drawing, drawing.axis_y)) == 1


def test_a_hollow_point_breaks_the_axis_line() -> None:
    """A ring threaded on the line reads as a bead, not as a hole."""
    drawing = drawn(inequality(points=[{"at": 0, "open": True}]))
    x, y, _, _ = drawing.dots[0]
    for primitive in drawing.scene.primitives:
        if isinstance(primitive, Stroke) and all(abs(py - y) < 1e-6 for _, py in primitive.points):
            xs = [px for px, _ in primitive.points]
            assert not (min(xs) < x < max(xs)), "the line runs through the hollow point"


def test_ranges_stack_in_the_order_written_the_last_nearest_the_axis() -> None:
    drawing = drawn(
        inequality(
            ranges=[
                {"from": 1, "from_open": True, "text": "x > 1"},
                {"to": 5, "text": "x ≤ 5"},
                {"from": 1, "to": 5, "from_open": True, "text": "both", "role": "emphasis"},
            ]
        )
    )
    heights = [y for _, _, y in drawing.tracks]
    assert heights == sorted(heights)
    assert heights[-1] < drawing.axis_y


# --------------------------------------------------------------------------
# The scale
# --------------------------------------------------------------------------


def test_ticks_fall_on_every_step_with_minus_signs() -> None:
    drawing = drawn(inequality())
    assert drawing.ticks == tuple(float(value) for value in range(-5, 7))
    words = {
        primitive.text for primitive in drawing.scene.primitives if isinstance(primitive, TextLine)
    }
    assert "\N{MINUS SIGN}3" in words and "-3" not in words


def test_a_named_scale_draws_no_numbers_and_names_its_ends() -> None:
    drawing = drawn(
        {
            "version": 1,
            "kind": "numberline",
            "axis": {"min": 0, "max": 5, "ends": ["remote", "on site"]},
            "points": [{"at": 2, "text": "Two days"}],
        }
    )
    assert drawing.ticks == ()
    words = {
        primitive.text for primitive in drawing.scene.primitives if isinstance(primitive, TextLine)
    }
    assert {"remote", "on site", "Two days"} <= words


# --------------------------------------------------------------------------
# Point labels
# --------------------------------------------------------------------------


def test_the_ph_scale_alternates_its_words_and_none_touch() -> None:
    document = json.loads((REFERENCE / "numberline-ph.json").read_text(encoding="utf-8"))
    drawing = drawn(document)
    sides = {side for side, _ in drawing.sides.values()}
    assert sides == {"above", "below"}
    for first, second in combinations(drawing.labels.values(), 2):
        apart = (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )
        assert apart, (first, second)


def test_a_leader_never_crosses_another_points_words() -> None:
    document = json.loads((REFERENCE / "numberline-ph.json").read_text(encoding="utf-8"))
    drawing = drawn(document)
    leaders = [
        primitive
        for primitive in drawing.scene.primitives
        if isinstance(primitive, Stroke)
        and primitive.role == "link"
        and primitive.points[0][0] == primitive.points[1][0]
        and abs(primitive.points[0][1] - primitive.points[1][1]) > 9
    ]
    for leader in leaders:
        x = leader.points[0][0]
        low, high = sorted(y for _, y in leader.points)
        for left, top, right, bottom in drawing.labels.values():
            if left <= x <= right:
                assert bottom <= low + 1e-6 or top >= high - 1e-6


def test_two_points_too_close_to_tell_apart_are_a_fit_error() -> None:
    document = inequality(axis={"min": 0, "max": 1000}, points=[{"at": 10}, {"at": 10.5}])
    del document["ranges"]
    with pytest.raises(FitError, match="draw as one dot"):
        drawn(document)


# --------------------------------------------------------------------------
# Refusals, at their pointers
# --------------------------------------------------------------------------


def test_a_value_off_the_scale_is_refused_at_its_pointer() -> None:
    document = inequality(points=[{"at": 9}], ranges=[{"from": -7, "to": 2}])
    assert "/points/0/at" in pointers(document)
    assert "/ranges/0/from" in pointers(document)
    assert "arrow" in messages(document)


def test_a_range_with_no_end_is_refused() -> None:
    assert pointers(inequality(ranges=[{"text": "everything"}])) == ["/ranges/0"]


def test_a_range_that_ends_before_it_starts_is_refused_at_to() -> None:
    assert pointers(inequality(ranges=[{"from": 3, "to": 3}])) == ["/ranges/0/to"]


@pytest.mark.parametrize(("name", "bound"), [("from_open", "to"), ("to_open", "from")])
def test_an_open_end_that_is_not_there_is_refused(name: str, bound: str) -> None:
    document = inequality(ranges=[{bound: 1, name: True}])
    assert pointers(document) == [f"/ranges/0/{name}"]


def test_two_points_at_one_value_are_refused_at_the_second() -> None:
    assert pointers(inequality(points=[{"at": 1}, {"at": 1}])) == ["/points/1/at"]


@pytest.mark.parametrize("name", ["step", "unit"])
def test_a_named_scale_takes_no_numbers(name: str) -> None:
    axis = {"min": 0, "max": 5, "ends": ["low", "high"], name: 1 if name == "step" else "cm"}
    assert pointers(inequality(axis=axis, ranges=[{"from": 1}])) == [f"/axis/{name}"]


def test_more_than_two_ends_is_refused() -> None:
    axis = {"min": 0, "max": 5, "ends": ["low", "middle", "high"]}
    assert pointers(inequality(axis=axis, ranges=[{"from": 1}])) == ["/axis/ends"]


def test_an_axis_that_runs_backwards_is_refused_at_max() -> None:
    assert "/axis/max" in pointers(inequality(axis={"min": 5, "max": 1}))


def test_too_many_ticks_are_refused_at_step() -> None:
    axis = {"min": 0, "max": 100, "step": 1}
    assert pointers(inequality(axis=axis, ranges=[{"from": 1}])) == ["/axis/step"]


def test_an_empty_number_line_is_refused() -> None:
    document = inequality()
    del document["ranges"]
    assert pointers(document) == ["/points"]


def test_a_date_is_refused_naming_timeline() -> None:
    document = inequality(points=[{"at": "2026-03-01"}])
    assert pointers(document) == ["/points/0/at"]
    assert "`timeline`" in messages(document)


@pytest.mark.parametrize(
    ("field", "named"),
    [("edges", "joins nothing"), ("series", "`scatter`"), ("axes", "`scatter`")],
)
def test_fields_from_other_kinds_are_refused_by_name(field: str, named: str) -> None:
    document = inequality(**{field: []})
    assert pointers(document) == [f"/{field}"]
    assert named in messages(document)


def test_value_is_refused_naming_at() -> None:
    document = inequality(points=[{"at": 1, "value": 1}])
    assert pointers(document) == ["/points/0/value"]
    assert "`at`" in messages(document)


def test_the_budget_refuses_a_sixteenth_point() -> None:
    document = inequality(
        axis={"min": 0, "max": 20, "step": 1}, points=[{"at": value} for value in range(16)]
    )
    assert "/points/15" in pointers(document)


def test_a_fifth_range_is_refused() -> None:
    document = inequality(ranges=[{"from": value} for value in range(5)])
    assert "/ranges/4" in pointers(document)


def test_the_numberline_theme_section_is_checked() -> None:
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "numberline": {"ends": "arrows"}})
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "numberline": {"dots": "big"}})


def test_a_two_line_emphasis_point_is_bold_on_both_lines_with_no_markers() -> None:
    """Issue #133: one `**…**` pair around two lines printed both markers raw.

    `wrap` splits on the newline first, so a pair spanning it became two
    unmatched halves. Each line is now bolded on its own.
    """
    document = {
        "version": 1,
        "kind": "numberline",
        "axis": {"min": 0, "max": 12},
        "points": [
            {"at": 4, "text": "O = 4"},
            {"at": 7, "text": "tE beta = 7\n(O + 4M + P) / 6", "role": "emphasis"},
            {"at": 11, "text": "P = 11"},
        ],
    }
    drawing = render(document)
    assert "**" not in drawing
    built = scene_for(parse_document(document), THEME, MEASURER)
    lines = [p for p in built.primitives if isinstance(p, TextLine)]
    emphasised = [line for line in lines if "tE beta" in line.text or "4M" in line.text]
    assert len(emphasised) == 2
    assert all(span.weight == "bold" for line in emphasised for span in line.spans)
