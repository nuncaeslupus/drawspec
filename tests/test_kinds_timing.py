"""`timing` — signals over one shared time axis, a lane each.

The kind's promises: every lane runs the same steps, so an edge on one lines up
with the edge it causes on another; a `bit` lane is a level with upright edges,
a `bus` a run of words in hexagons, a `state` lane a line between named levels;
`.` carries a step on; every value is checked where it is written, so a wrong
one is refused at its own step; and a word that does not fit its run is refused
rather than drawn over its neighbours.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render, render_text
from drawspec.errors import FitError, ThemeError
from drawspec.kinds.timing import (
    TimingDrawing,
    bit_runs,
    expand,
    timing_drawing,
    word_runs,
)
from drawspec.scene import Path as ScenePath
from drawspec.scene import Polygon, TextLine
from drawspec.schema import TIMING_STEP_MAX, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("timing-*.json"))


def figure(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "timing",
        "signals": [
            {"text": "CLK", "values": ["p", ".", ".", ".", "."]},
            {"text": "EN", "values": ["0", "1", ".", "z", "x"]},
            {"text": "DATA", "lane": "bus", "values": ["x", "A1", ".", "B2", "z"]},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> TimingDrawing:
    return timing_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


# -- the references -----------------------------------------------------------


def test_there_are_references_for_the_three_lanes() -> None:
    lanes = {
        signal.get("lane", "bit")
        for path in REFERENCES
        for signal in json.loads(path.read_text(encoding="utf-8"))["signals"]
    }
    assert lanes == {"bit", "bus", "state"}


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_validates_and_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")
    assert render(document, theme="blueprint").startswith("<svg")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_texts_overlap(path: Path) -> None:
    boxes = drawn(json.loads(path.read_text(encoding="utf-8"))).texts
    for index, (l1, t1, r1, b1) in enumerate(boxes):
        for l2, t2, r2, b2 in boxes[index + 1 :]:
            assert r1 <= l2 or r2 <= l1 or b1 <= t2 or b2 <= t1, (
                (l1, t1, r1, b1),
                (l2, t2, r2, b2),
            )


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_everything_is_on_the_canvas(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for left, top, right, bottom in drawing.texts:
        assert left >= 0 and right <= drawing.scene.width + 0.01
        assert top >= -0.01 and bottom <= drawing.scene.height + 0.01


# -- the values -----------------------------------------------------------------


def test_a_hold_carries_the_value_before_on() -> None:
    assert expand(["p", ".", "0", ".", "."]) == ["p", "p", "0", "0", "0"]


def test_a_pulse_is_high_then_low_and_its_negative_low_then_high() -> None:
    assert bit_runs(["p", "."]) == [("hi", 0, 1), ("lo", 1, 2), ("hi", 2, 3), ("lo", 3, 4)]
    assert bit_runs(["0", "n"]) == [("lo", 0, 3), ("hi", 3, 4)]


def test_a_word_written_twice_is_two_words_and_a_hold_is_one() -> None:
    assert word_runs(["A", "A", "."]) == [("A", 0, 1, 0), ("A", 1, 3, 1)]


def test_every_lane_lines_up_on_the_same_steps() -> None:
    drawing = drawn(figure())
    left, right = drawing.plot
    assert drawing.step == pytest.approx((right - left) / 5)
    # The clock's rising edges are at every step edge.
    clock = next(
        primitive
        for primitive in drawing.scene.primitives
        if isinstance(primitive, ScenePath) and primitive.role == "flow"
    )
    rises = sorted({x for (x, y0), (x2, y1) in pairwise(clock.points) if x == x2 and y1 < y0})
    assert rises == pytest.approx([left + drawing.step * k for k in range(1, 5)])


def test_unknown_is_hatched_on_a_bit_and_a_bus_lane() -> None:
    hatched = [
        primitive
        for primitive in drawn(figure()).scene.primitives
        if isinstance(primitive, Polygon) and primitive.fill == "hatch"
    ]
    assert len(hatched) == 2


def test_bus_words_are_written_once_per_run() -> None:
    words = [
        primitive.text
        for primitive in drawn(figure()).scene.primitives
        if isinstance(primitive, TextLine)
    ]
    assert words.count("A1") == 1 and words.count("B2") == 1


def test_a_state_lane_has_a_level_per_state_top_down() -> None:
    document = figure(
        signals=[
            {
                "text": "User",
                "lane": "state",
                "states": ["Active", "Idle"],
                "values": ["Idle", "Active", ".", "Idle"],
            }
        ]
    )
    drawing = drawn(document)
    top, bottom = drawing.lanes[0]
    line = next(p for p in drawing.scene.primitives if isinstance(p, ScenePath))
    assert sorted({y for _, y in line.points}) == pytest.approx([top, bottom])
    assert line.points[0][1] == pytest.approx(bottom)  # Idle is the lower level


def test_the_theme_can_rule_the_steps_and_upright_the_bus() -> None:
    from dataclasses import replace

    from drawspec.theme import TimingStyle

    ruled = replace(THEME, timing=TimingStyle(slew=0.0, grid=True))
    drawing = timing_drawing(parse_document(figure()), ruled, MEASURER)
    grid = [p for p in drawing.scene.primitives if isinstance(p, ScenePath) and p.role == "aside"]
    assert len(grid) == 6


@pytest.mark.parametrize("bad", [{"slew": 0.8}, {"slew": "steep"}, {"grid": "yes"}, {"tilt": 1}])
def test_the_theme_section_is_checked(bad: dict[str, Any]) -> None:
    from drawspec.theme import TimingStyle

    with pytest.raises(ThemeError, match=r"\[timing\]"):
        TimingStyle.from_mapping(bad)


# -- refusals, each at its pointer ----------------------------------------------


def test_a_value_a_bit_lane_cannot_draw_is_refused_at_its_step() -> None:
    document = figure()
    document["signals"][1]["values"][2] = "high"
    assert pointers(document) == ["/signals/1/values/2"]
    assert "set `lane` to `bus`" in messages(document)


def test_a_number_for_a_level_is_told_to_quote_it() -> None:
    document = figure()
    document["signals"][1]["values"][0] = 0
    assert pointers(document) == ["/signals/1/values/0"]
    assert '"0"' in messages(document)


def test_a_hold_with_nothing_before_it_is_refused() -> None:
    document = figure()
    document["signals"][0]["values"][0] = "."
    assert pointers(document) == ["/signals/0/values/0"]


def test_lanes_of_different_lengths_are_refused_at_the_shorter() -> None:
    document = figure()
    document["signals"][2]["values"] = ["x", "A1"]
    assert pointers(document) == ["/signals/2/values"]


def test_too_many_steps_is_refused_at_the_first_past_the_cap() -> None:
    document = figure(signals=[{"text": "CLK", "values": ["p"] * (TIMING_STEP_MAX + 1)}])
    assert pointers(document) == [f"/signals/0/values/{TIMING_STEP_MAX}"]


def test_a_state_lane_needs_its_states_and_others_may_not_have_them() -> None:
    document = figure()
    document["signals"][0]["lane"] = "state"
    document["signals"][1]["states"] = ["A", "B"]
    found = pointers(document)
    assert "/signals/0/states" in found and "/signals/1/states" in found


def test_a_state_not_declared_is_refused_at_its_step() -> None:
    document = figure(
        signals=[
            {
                "text": "User",
                "lane": "state",
                "states": ["Active", "Idle"],
                "values": ["Idle", "Busy"],
            }
        ]
    )
    assert pointers(document) == ["/signals/0/values/1"]


def test_a_signal_named_twice_is_refused() -> None:
    document = figure()
    document["signals"][1]["text"] = "CLK"
    assert pointers(document) == ["/signals/1/text"]


def test_a_group_written_apart_is_refused() -> None:
    document = figure()
    document["signals"][0]["group"] = "A"
    document["signals"][1]["group"] = "B"
    document["signals"][2]["group"] = "A"
    assert pointers(document) == ["/signals/2/group"]


@pytest.mark.parametrize(
    ("marker", "pointer"),
    [({"at": 6}, "/markers/0/at"), ({"at": 1.25}, "/markers/0/at"), ({"at": -1}, "/markers/0/at")],
)
def test_a_marker_off_an_edge_is_refused(marker: dict[str, Any], pointer: str) -> None:
    assert pointers(figure(markers=[marker])) == [pointer]


def test_an_interval_runs_forward_on_a_signal_there_is() -> None:
    document = figure(intervals=[{"from": 3, "to": 2, "text": "t", "signal": "CLOCK"}])
    assert pointers(document) == ["/intervals/0/to", "/intervals/0/signal"]


def test_ticks_name_every_step_once() -> None:
    assert pointers(figure(ticks=["0", "1"])) == ["/ticks"]


@pytest.mark.parametrize("field", ["wave", "period", "data", "edge", "role"])
def test_wavedrom_fields_are_refused_with_the_way_to_say_it(field: str) -> None:
    document = figure()
    document["signals"][0][field] = "p...."
    assert pointers(document) == [f"/signals/0/{field}"]


def test_a_word_too_wide_for_its_run_is_refused_at_the_step_it_was_written() -> None:
    document = figure()
    document["signals"][2]["values"][3] = "a very long word on the bus"
    with pytest.raises(FitError, match=r"^/signals/2/values/3: "):
        drawn(document)


def test_too_many_steps_for_the_width_is_refused() -> None:
    document = figure(width=200, signals=[{"text": "CLK", "values": ["p"] * 40}])
    with pytest.raises(FitError, match=r"^/signals/0/text: "):
        drawn(document)


# -- text ---------------------------------------------------------------------------


def test_text_draws_levels_words_and_states() -> None:
    drawn_text = render_text(parse_document(figure()), width=80)
    assert "CLK" in drawn_text and "A1" in drawn_text and "B2" in drawn_text
    assert "┌" in drawn_text and "░" in drawn_text
    ascii_text = render_text(parse_document(figure()), width=80, charset="ascii")
    assert all(ord(character) < 128 for character in ascii_text)


def test_text_too_wide_is_refused_with_the_width_it_needs() -> None:
    document = parse_document(figure(signals=[{"text": "CLK", "values": ["p"] * 30}]))
    with pytest.raises(FitError, match=r"--width (\d+) or more"):
        render_text(document, width=60)
