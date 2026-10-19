"""`gantt` — a plan, one row per task, each an interval on a numbered axis.

The kind's claims are positional, so they are asserted from the drawing: a bar's
two ends are the axis positions of its `start` and `end`, a milestone is centred
on its `at`, and every dependency leaves its source's end and arrives at its
target's start. The document rules — no dates, one shape per task, nothing off
the axis, finish-to-start, consecutive phases — are asserted by the pointer of
the refusal.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError, ThemeError
from drawspec.kinds.gantt import GanttDrawing, gantt_drawing, gantt_text
from drawspec.scene import Ellipse, Polygon, TextLine
from drawspec.scene import Path as Stroke
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("gantt-*.json"))
EPSILON = 1e-6


def plan(**extra: Any) -> dict[str, Any]:
    """A small migration: two phases, a milestone, dependencies and a mark."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "gantt",
        "axis": {"label": "Week", "min": 0, "max": 10},
        "tasks": [
            {"id": "build", "text": "Build", "start": 0, "end": 3},
            {"id": "copy", "text": "Copy the data", "start": 3, "end": 6, "role": "emphasis"},
            {"id": "check", "text": "Check it", "start": 4, "end": 7},
            {"id": "switch", "text": "Switch over", "at": 7},
            {"id": "clean", "text": "Clean up", "start": 7, "end": 10},
        ],
        "groups": [
            {"id": "before", "text": "Before", "members": ["build", "copy", "check"]},
            {"id": "after", "text": "After", "members": ["switch", "clean"]},
        ],
        "edges": [
            {"from": "build", "to": "copy"},
            {"from": "build", "to": "check"},
            {"from": "check", "to": "switch", "role": "strong"},
            {"from": "switch", "to": "clean"},
        ],
        "marks": [{"text": "today", "at": 2}],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> GanttDrawing:
    return gantt_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_with_its_bars_where_its_values_say(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    drawing = drawn(document)
    for task in parse_document(document).tasks:
        if task.milestone:
            assert drawing.milestones[task.id][0] == pytest.approx(
                drawing.scale.to_pixels(task.begins)
            )
        else:
            left, _, right, _ = drawing.bars[task.id]
            assert left == pytest.approx(drawing.scale.to_pixels(task.start))
            assert right == pytest.approx(drawing.scale.to_pixels(task.end))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_a_bars_edges_are_at_the_axis_positions_of_its_start_and_end() -> None:
    drawing = drawn(plan())
    scale = drawing.scale
    left, top, right, bottom = drawing.bars["copy"]
    assert (left, right) == pytest.approx((scale.to_pixels(3), scale.to_pixels(6)))
    assert bottom > top
    # The axis really is the axis: 0 and 10 are the plot's two ends, ten weeks apart.
    assert scale.to_pixels(10) - scale.to_pixels(0) == pytest.approx(
        (scale.to_pixels(5) - scale.to_pixels(0)) * 2
    )


def test_a_bar_is_a_polygon_so_its_corners_are_square_and_its_ends_exact() -> None:
    """A rect takes the theme's corner radius, and a rounded bar ends short of its value."""
    drawing = drawn(plan())
    left, top, right, bottom = drawing.bars["build"]
    polygons = [p for p in drawing.scene.primitives if isinstance(p, Polygon)]
    assert any(
        set(p.points) == {(left, top), (right, top), (right, bottom), (left, bottom)}
        for p in polygons
    )


def test_a_milestone_is_a_diamond_centred_at_its_value_in_its_row() -> None:
    drawing = drawn(plan())
    x, y = drawing.milestones["switch"]
    top, bottom = drawing.rows["switch"]
    assert x == pytest.approx(drawing.scale.to_pixels(7))
    assert y == pytest.approx((top + bottom) / 2)
    diamonds = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, Polygon) and len(p.points) == 4 and p.fill == "solid"
    ]
    (diamond,) = diamonds
    xs = sorted(point[0] for point in diamond.points)
    ys = sorted(point[1] for point in diamond.points)
    assert (xs[0] + xs[-1]) / 2 == pytest.approx(x)
    assert (ys[0] + ys[-1]) / 2 == pytest.approx(y)
    assert xs[1] == pytest.approx(x) and ys[1] == pytest.approx(y)


def test_the_theme_can_draw_milestones_as_dots() -> None:
    theme = load_theme({"version": 1, "gantt": {"milestone": "circle"}})
    drawing = drawn(plan(), theme)
    dots = [p for p in drawing.scene.primitives if isinstance(p, Ellipse)]
    (dot,) = dots
    assert (dot.cx, dot.cy) == pytest.approx(drawing.milestones["switch"])


def test_the_gantt_theme_section_is_checked() -> None:
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "gantt": {"milestone": "star"}})
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "gantt": {"marks": "dotted"}})
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "gantt": {"colour": "red"}})


def test_every_dependency_leaves_its_sources_end_and_arrives_at_its_targets_start() -> None:
    """Finish-to-start, drawn: from the end of one into the start of the other.

    The tail is on the source's right edge (or the bottom edge under its end,
    when the target is a milestone directly below it); the head is on the
    target's left edge, or on its near edge just inside its start — and never on
    a corner.
    """
    document = plan()
    drawing = drawn(document)
    tasks = {task.id: task for task in parse_document(document).tasks}
    scale = drawing.scale
    for edge, route in zip(document["edges"], drawing.routes, strict=True):
        source, target = tasks[edge["from"]], tasks[edge["to"]]
        tail, head = route[0], route[-1]
        assert tail[0] >= scale.to_pixels(source.finishes) - EPSILON
        if target.milestone:
            x, _ = drawing.milestones[target.id]
            assert head[0] == pytest.approx(x) or head[0] < x
        else:
            left, top, right, bottom = drawing.bars[target.id]
            assert left - EPSILON <= head[0] < right
            on_left = head[0] == pytest.approx(left) and top < head[1] < bottom
            on_edge = left < head[0] and head[1] in (pytest.approx(top), pytest.approx(bottom))
            assert on_left or on_edge
            if on_edge:
                assert head[0] - left >= THEME.scale["body"] / 11 * 6


def test_routes_are_orthogonal() -> None:
    for path in REFERENCES:
        for route in drawn(json.loads(path.read_text())).routes:
            for (x1, y1), (x2, y2) in pairwise(route):
                assert abs(x1 - x2) < EPSILON or abs(y1 - y2) < EPSILON


def test_a_dependency_ends_in_a_straight_run_longer_than_its_head() -> None:
    """A head on a bend sits on the corner of the bar it points at."""
    for path in REFERENCES:
        document = json.loads(path.read_text())
        for edge, route in zip(document.get("edges", ()), drawn(document).routes, strict=True):
            (x1, y1), (x2, y2) = route[-2], route[-1]
            run = abs(x2 - x1) + abs(y2 - y1)
            assert run > THEME.head_length_for(edge.get("role", "flow"))


def test_a_route_does_not_run_through_a_bar_it_can_go_round() -> None:
    """Upgrade then two tasks under it: the second's line passes left of the first's bar."""
    document = plan(
        tasks=[
            {"id": "a", "text": "A", "start": 0, "end": 4},
            {"id": "b", "text": "B", "start": 4, "end": 8},
            {"id": "c", "text": "C", "start": 4, "end": 6},
        ],
        groups=[],
        edges=[{"from": "a", "to": "b"}, {"from": "a", "to": "c"}],
        marks=[],
    )
    drawing = drawn(document)
    left, top, right, bottom = drawing.bars["b"]
    for (x1, y1), (x2, y2) in pairwise(drawing.routes[1]):
        crosses_x = min(x1, x2) <= right and max(x1, x2) >= left
        crosses_y = min(y1, y2) <= bottom and max(y1, y2) >= top
        assert not (crosses_x and crosses_y)


def test_rows_are_in_the_order_written_and_a_phase_heading_comes_before_its_first_task() -> None:
    drawing = drawn(plan())
    tops = [drawing.rows[name][0] for name in ("build", "copy", "check", "switch", "clean")]
    assert tops == sorted(tops)
    lines = [p for p in drawing.scene.primitives if isinstance(p, TextLine)]
    before = next(line for line in lines if line.text == "Before")
    after = next(line for line in lines if line.text == "After")
    assert before.y < drawing.rows["build"][0]
    assert drawing.rows["check"][1] <= after.y < drawing.rows["switch"][0]
    assert all(span.weight == "bold" for span in before.spans)


def test_a_phase_has_a_bracket_over_its_span() -> None:
    drawing = drawn(plan())
    scale = drawing.scale
    brackets = [p for p in drawing.scene.primitives if isinstance(p, Stroke) and p.role == "link"]
    spans = sorted((p.points[0][0], p.points[-1][0]) for p in brackets if len(p.points) == 4)
    assert spans == [
        pytest.approx((scale.to_pixels(0), scale.to_pixels(7))),
        pytest.approx((scale.to_pixels(7), scale.to_pixels(10))),
    ]


def test_a_mark_is_a_line_across_every_row_at_its_value() -> None:
    drawing = drawn(plan())
    (x,) = drawing.marks
    assert x == pytest.approx(drawing.scale.to_pixels(2))
    lines = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, Stroke) and p.role == THEME.gantt.marks and p.points[0][0] == x
    ]
    (line,) = lines
    lowest = max(bottom for _, bottom in drawing.rows.values())
    assert line.points[0][1] < min(top for top, _ in drawing.rows.values())
    assert line.points[-1][1] == pytest.approx(lowest)


def test_two_close_marks_take_two_lanes_and_neither_line_crosses_the_other_name() -> None:
    document = plan(marks=[{"text": "freeze", "at": 2}, {"text": "board review", "at": 2.3}])
    drawing = drawn(document)
    names = {
        line.text: line
        for line in drawing.scene.primitives
        if isinstance(line, TextLine) and line.text in ("freeze", "board review")
    }
    assert names["freeze"].y != names["board review"].y
    first, second = drawing.marks
    # The second name is to the right of its own line, so the first line misses it.
    assert names["board review"].x > second > first


def test_categories_name_the_periods_between_ticks() -> None:
    document = plan(
        axis={"label": "Month", "categories": ["Jan", "Feb", "Mar"]},
        tasks=[{"id": "a", "text": "A", "start": 1, "end": 3}, {"id": "b", "text": "B", "at": 4}],
        groups=[],
        edges=[],
        marks=[],
    )
    drawing = drawn(document)
    scale = drawing.scale
    assert (scale.low, scale.high) == (1.0, 4.0)
    lines = {line.text: line for line in drawing.scene.primitives if isinstance(line, TextLine)}
    assert lines["Feb"].x == pytest.approx(scale.to_pixels(2.5))


def test_an_unpinned_axis_starts_and_ends_on_a_tick() -> None:
    document = plan(axis={"label": "Day"}, marks=[])
    document["tasks"][0]["start"] = 0.5
    drawing = drawn(document)
    assert drawing.scale.low == 0.0


def test_an_actor_is_the_row_labels_lead() -> None:
    document = plan()
    document["tasks"][0]["actor"] = "Platform team"
    drawing = drawn(document)
    lines = [p for p in drawing.scene.primitives if isinstance(p, TextLine)]
    actor = next(line for line in lines if line.text == "Platform team")
    text = next(line for line in lines if line.text == "Build")
    assert actor.y < text.y
    assert actor.spans[0].weight == "bold"


def test_roles_are_told_apart_without_colour() -> None:
    """Step, critical, focal and outside tasks differ by weight, fill or dash."""
    document = plan(
        tasks=[
            {"id": "a", "text": "A", "start": 0, "end": 2},
            {"id": "b", "text": "B", "start": 2, "end": 4, "role": "strong"},
            {"id": "c", "text": "C", "start": 4, "end": 6, "role": "emphasis"},
            {"id": "d", "text": "D", "start": 6, "end": 8, "role": "note"},
        ],
        groups=[],
        edges=[],
        marks=[],
    )
    drawing = drawn(document)
    looks = {
        (p.role, p.fill) for p in drawing.scene.primitives if isinstance(p, Polygon) and p.points
    }
    assert len(looks) == 4


def test_strong_tasks_are_not_counted_by_the_emphasis_cap() -> None:
    """A critical path is several bars by nature, like the `strong` edges along it."""
    document = plan()
    for task in document["tasks"]:
        task["role"] = "strong"
    assert validate_document(document) == ()


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["start", "end"])
def test_a_date_is_refused_with_a_unit_and_categories_suggested(field: str) -> None:
    document = plan()
    document["tasks"][0][field] = "2026-03-01"
    (violation,) = validate_document(document)
    assert violation.pointer == f"/tasks/0/{field}"
    assert "no calendar" in violation.message
    assert "categories" in violation.message


def test_a_date_on_a_mark_is_refused_the_same_way() -> None:
    document = plan(marks=[{"text": "today", "at": "2026-10-10"}])
    assert pointers(document) == ["/marks/0/at"]
    assert "no calendar" in messages(document)


def test_a_task_that_ends_before_it_starts_is_refused() -> None:
    document = plan()
    document["tasks"][0]["end"] = 0
    assert pointers(document) == ["/tasks/0/end"]


def test_a_task_with_both_at_and_start_is_refused() -> None:
    document = plan()
    document["tasks"][3]["start"] = 6
    assert pointers(document) == ["/tasks/3/at"]


def test_a_task_with_neither_is_refused() -> None:
    document = plan()
    del document["tasks"][3]["at"]
    assert "/tasks/3" in pointers(document)


def test_a_start_with_no_end_is_refused_at_the_missing_one() -> None:
    document = plan()
    del document["tasks"][0]["end"]
    assert "/tasks/0/end" in pointers(document)


def test_a_value_off_the_axis_is_refused() -> None:
    document = plan()
    document["tasks"][4]["end"] = 11
    assert pointers(document) == ["/tasks/4/end"]
    assert "off the axis" in messages(document)


def test_a_mark_off_the_axis_is_refused() -> None:
    assert pointers(plan(marks=[{"text": "late", "at": -1}])) == ["/marks/0/at"]


def test_categories_set_the_range_and_refuse_min_and_max() -> None:
    document = plan(axis={"label": "Month", "categories": ["Jan"] * 10, "min": 0})
    assert "/axis/min" in pointers(document)


def test_a_dependency_whose_target_starts_before_its_source_ends_is_refused() -> None:
    document = plan(edges=[{"from": "copy", "to": "check"}])
    (violation,) = validate_document(document)
    assert violation.pointer == "/edges/0/to"
    assert "only you know which" in violation.message


def test_a_dependency_must_land_on_tasks() -> None:
    assert pointers(plan(edges=[{"from": "build", "to": "copies"}])) == ["/edges/0/to"]
    assert pointers(plan(edges=[{"from": "before", "to": "clean"}])) == ["/edges/0/from"]


def test_a_task_cannot_wait_for_itself() -> None:
    assert pointers(plan(edges=[{"from": "build", "to": "build"}])) == ["/edges/0/to"]


@pytest.mark.parametrize("role", ["inherits", "link", "owns"])
def test_a_dependency_takes_only_its_own_roles(role: str) -> None:
    assert pointers(plan(edges=[{"from": "build", "to": "copy", "role": role}])) == [
        "/edges/0/role"
    ]


def test_a_phase_whose_tasks_are_not_consecutive_is_refused() -> None:
    document = plan(
        groups=[
            {"id": "before", "text": "Before", "members": ["build", "check"]},
            {"id": "after", "text": "After", "members": ["copy", "switch", "clean"]},
        ]
    )
    assert pointers(document) == ["/groups/0/members", "/groups/1/members"]


def test_with_phases_a_task_in_none_is_refused() -> None:
    document = plan()
    document["groups"][1]["members"] = ["switch"]
    assert pointers(document) == ["/tasks/4"]


def test_a_task_in_two_phases_is_refused() -> None:
    document = plan()
    document["groups"][1]["members"] = ["check", "switch", "clean"]
    assert "/groups/1/members/0" in pointers(document)


def test_a_phase_needs_a_name() -> None:
    document = plan()
    del document["groups"][0]["text"]
    assert pointers(document) == ["/groups/0/text"]


def test_progress_is_refused_with_its_reason() -> None:
    document = plan()
    document["tasks"][0]["progress"] = 40
    assert pointers(document) == ["/tasks/0/progress"]
    assert "`done`" in messages(document)


def test_an_actor_forbids_a_second_paragraph() -> None:
    document = plan()
    document["tasks"][0].update(actor="Ops", text="Build\nthe cluster")
    assert pointers(document) == ["/tasks/0/text"]


def test_duplicate_ids_are_refused() -> None:
    document = plan()
    document["tasks"][1]["id"] = "build"
    assert "/tasks/1/id" in pointers(document)


def test_seventeen_tasks_are_refused_with_the_split_message() -> None:
    assert dict(READABILITY_BUDGET["gantt"])["tasks"] == 16
    document = plan(
        tasks=[{"id": f"t{index}", "text": "Task", "start": 0, "end": 1} for index in range(17)],
        groups=[],
        edges=[],
    )
    (violation,) = validate_document(document)
    assert violation.pointer == "/tasks/16"
    assert "Split it" in violation.message


def test_a_refused_document_raises_with_every_violation() -> None:
    document = plan(edges=[{"from": "copy", "to": "check"}, {"from": "x", "to": "build"}])
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert len(error.value.violations) == 2


# ---------------------------------------------------------------------------
# done: how much of a task is complete
# ---------------------------------------------------------------------------


def _bands(drawing: GanttDrawing) -> list[Polygon]:
    return [
        item
        for item in drawing.scene.primitives
        if isinstance(item, Polygon) and item.region and item.fill == "solid"
    ]


def test_done_draws_a_band_inside_the_bar_from_its_start() -> None:
    """Rank 7 of the kind audit: MS Project's progress line, in the page's ink."""
    document = plan()
    document["tasks"][1]["done"] = 60
    drawing = drawn(document)
    (band,) = _bands(drawing)
    left, top, right, bottom = drawing.bars["copy"]
    xs = [x for x, _ in band.points]
    ys = [y for _, y in band.points]
    assert min(xs) == pytest.approx(left)
    assert max(xs) == pytest.approx(left + (right - left) * 0.6)
    assert top < min(ys) and max(ys) < bottom, "inside the bar, not over its outline"
    assert band.fill_colour == "currentColor", "the page's ink: legible on a dark page"
    assert 0 < band.fill_opacity <= 1


def test_done_zero_draws_no_band_and_a_hundred_fills_the_bar() -> None:
    document = plan()
    document["tasks"][0]["done"] = 0
    document["tasks"][2]["done"] = 100
    drawing = drawn(document)
    (band,) = _bands(drawing)
    _, _, right, _ = drawing.bars["check"]
    assert max(x for x, _ in band.points) == pytest.approx(right)


def test_done_is_said_in_the_description_after_the_authors_own() -> None:
    """The band is only drawn, so the accessible description says each share,
    `done: 0` included, after whatever the author wrote."""
    document = plan()
    document["description"] = "The spring release."
    document["tasks"][0]["done"] = 0
    document["tasks"][1]["done"] = 60
    description = drawn(document).scene.description
    assert description.startswith("The spring release. Progress: ")
    assert "0% done" in description and "60% done" in description


@pytest.mark.parametrize(("index", "value"), [(0, 120), (0, -5), (3, 50)])
def test_done_out_of_range_or_on_a_milestone_is_refused(index: int, value: float) -> None:
    document = plan()
    document["tasks"][index]["done"] = value
    assert pointers(document) == [f"/tasks/{index}/done"]


def test_the_theme_sets_how_strong_the_done_band_is() -> None:
    document = plan()
    document["tasks"][1]["done"] = 50
    lighter = load_theme({"version": 1, "gantt": {"done": 0.4}})
    (band,) = _bands(drawn(document, lighter))
    assert band.fill_opacity == pytest.approx(0.4)
    with pytest.raises(ThemeError, match=r"\[gantt\] done"):
        load_theme({"version": 1, "gantt": {"done": 1.5}})


# ---------------------------------------------------------------------------
# Events and iterations: a life cycle's deliveries and loops on a task's row
# ---------------------------------------------------------------------------


def lanes(**agile: Any) -> dict[str, Any]:
    """The issue's case: a predictive lane and an agile one over one axis."""
    task: dict[str, Any] = {
        "id": "agile",
        "text": "Agile",
        "start": 0,
        "end": 12,
        "iterations": [
            {"start": 0, "end": 3},
            {"start": 3, "end": 6},
            {"start": 6, "end": 9},
            {"start": 9, "end": 12},
        ],
        "events": [{"at": at, "text": f"D{n}"} for n, at in enumerate((3, 6, 9, 12), 1)],
    }
    task.update(agile)
    return {
        "version": 1,
        "kind": "gantt",
        "axis": {"label": "Month", "min": 0, "max": 12},
        "tasks": [
            {
                "id": "predictive",
                "text": "Predictive",
                "start": 0,
                "end": 12,
                "events": [{"at": 12, "text": "Delivery"}],
            },
            task,
        ],
    }


def test_lanes_with_points_and_iterations_are_one_row_each_on_one_axis() -> None:
    """Two tasks, two rows: events and arcs live on their task's row, not rows of their own."""
    drawing = drawn(lanes())
    assert list(drawing.rows) == ["predictive", "agile"]
    assert list(drawing.bars) == ["predictive", "agile"]
    assert drawing.milestones == {}


def test_a_point_is_a_diamond_on_its_bar_at_its_value() -> None:
    """Four deliveries at 3, 6, 9 and 12: their centres on the bar's midline at those x."""
    drawing = drawn(lanes())
    _, top, right, bottom = drawing.bars["agile"]
    centres = drawing.events["agile"]
    assert [x for x, _ in centres] == pytest.approx(
        [drawing.scale.to_pixels(value) for value in (3, 6, 9, 12)]
    )
    assert all(y == pytest.approx((top + bottom) / 2) for _, y in centres)
    assert centres[-1][0] == pytest.approx(right)


def test_a_points_words_are_centred_under_the_bar() -> None:
    """`D2` is centred on x(6) and its baseline is below the bar's bottom edge."""
    drawing = drawn(lanes())
    _, _, _, bottom = drawing.bars["agile"]
    (words,) = [
        p for p in drawing.scene.primitives if isinstance(p, TextLine) and p.spans[0].text == "D2"
    ]
    assert words.anchor == "middle"
    assert words.x == pytest.approx(drawing.scale.to_pixels(6))
    assert words.y > bottom


def test_words_at_the_canvas_edge_are_pulled_back_onto_it() -> None:
    """`Delivery` at the axis's end would overhang the canvas centred; it is shifted left."""
    drawing = drawn(lanes())
    (words,) = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, TextLine) and p.spans[0].text == "Delivery"
    ]
    wide = MEASURER.measure("Delivery", THEME.font.default, THEME.scale["label"]).width
    assert words.x + wide / 2 <= THEME.canvas.width + EPSILON


def test_an_iteration_is_an_arc_over_the_bar_from_its_end_back_to_its_start() -> None:
    """Tail on the bar's top near x(end), a curve up and back, head down near x(start).

    A curve, not a bracket: it leaves and lands upright, and rises above the bar in
    between. Each leg stands the same distance inside its iteration, so the arc of
    0-3 and that of 3-6 meet the bar on either side of the event at 3, never on it.
    """
    drawing = drawn(lanes())
    _, top, _, _ = drawing.bars["agile"]
    arcs = drawing.iterations["agile"]
    assert len(arcs) == 4
    for arc, (start, end) in zip(arcs, ((0, 3), (3, 6), (6, 9), (9, 12)), strict=True):
        (x1, y1), (x4, y4) = arc[0], arc[-1]
        assert y1 == pytest.approx(top) and y4 == pytest.approx(top)
        assert all(y < top for _, y in arc[1:-1])
        assert [x for x, _ in arc] == sorted((x for x, _ in arc), reverse=True)
        inset = drawing.scale.to_pixels(end) - x1
        assert x4 - drawing.scale.to_pixels(start) == pytest.approx(inset)
        assert inset > 0
    for earlier, later in pairwise(arcs):
        event = drawing.events["agile"][arcs.index(earlier)][0]
        assert earlier[0][0] < event < later[-1][0]


def test_a_row_with_arcs_and_words_is_taller_and_its_arcs_stay_inside_it() -> None:
    """The arcs rise above the bar and the words hang below it, both inside the row."""
    drawing = drawn(lanes())
    plain = drawn(lanes(iterations=[], events=[]))
    top, bottom = drawing.rows["agile"]
    assert bottom - top > plain.rows["agile"][1] - plain.rows["agile"][0]
    assert all(y > top for arc in drawing.iterations["agile"] for _, y in arc)


def test_an_iteration_too_short_for_its_arc_is_refused() -> None:
    """One axis unit of twelve on the default canvas leaves no room for two legs."""
    document = lanes(iterations=[{"start": 0, "end": 0.1}], events=[])
    with pytest.raises(FitError, match="too short for its arc"):
        drawn(document)


def test_points_words_that_would_touch_are_refused() -> None:
    """Two long words at 6 and 6.1 cannot sit side by side under the bar."""
    document = lanes(
        iterations=[],
        events=[{"at": 6, "text": "First delivery"}, {"at": 6.1, "text": "Second delivery"}],
    )
    with pytest.raises(FitError, match="too close"):
        drawn(document)


def test_the_lanes_are_valid_and_points_and_iterations_are_refused_where_they_cannot_hold() -> None:
    """Each refusal at its own pointer: outside, backwards, overlapping, on a milestone."""
    assert pointers(lanes()) == []
    assert pointers(lanes(events=[{"at": 13}])) == ["/tasks/1/events/0/at"]
    assert pointers(lanes(iterations=[{"start": -1, "end": 13}])) == [
        "/tasks/1/iterations/0/start",
        "/tasks/1/iterations/0/end",
    ]
    assert pointers(lanes(iterations=[{"start": 5, "end": 5}])) == ["/tasks/1/iterations/0/end"]
    assert pointers(lanes(iterations=[{"start": 0, "end": 4}, {"start": 3, "end": 6}])) == [
        "/tasks/1/iterations/1/start"
    ]
    milestone = lanes()
    milestone["tasks"][1] = {"id": "agile", "text": "Agile", "at": 12, "events": [{"at": 12}]}
    assert pointers(milestone) == ["/tasks/1/events"]
    assert "a milestone is a moment" in messages(milestone)


def test_iterations_that_touch_end_to_start_are_valid() -> None:
    """3-6 after 0-3 hands on at 3: touching is how one iteration follows another."""
    assert pointers(lanes(iterations=[{"start": 0, "end": 3}, {"start": 3, "end": 6}])) == []


def test_points_and_iterations_count_against_the_readability_budget() -> None:
    """Nine events on one task: the ninth is refused, over the eight a row reads at a glance."""
    names = dict(READABILITY_BUDGET["gantt"])
    assert names["tasks/events"] == 8 and names["tasks/iterations"] == 8
    document = lanes(events=[{"at": float(value)} for value in range(9)], iterations=[])
    assert pointers(document) == ["/tasks/1/events/8"]


def test_text_draws_arcs_over_the_bar_and_points_on_it_with_their_words_under() -> None:
    """The agile row: `▼──┐` per iteration above, `◆` at each delivery, `D1` under it."""
    text = gantt_text(parse_document(lanes()), 80, "unicode")
    lines = text.splitlines()
    (bar,) = [index for index, line in enumerate(lines) if line.startswith("Agile")]
    assert lines[bar - 1].count("▼") == 4 and lines[bar - 1].count("┐") == 4
    assert lines[bar].count("◆") == 4
    assert "D1" in lines[bar + 1] and "D4" in lines[bar + 1]
    assert lines[bar + 1].index("D2") <= lines[bar].index("◆", lines[bar].index("◆") + 1)


def test_text_lists_points_words_that_would_touch_under_the_chart() -> None:
    """Words that cannot share the row under the bar are listed, never dropped."""
    document = lanes(
        iterations=[],
        events=[{"at": 6, "text": "First delivery"}, {"at": 7, "text": "Second delivery"}],
    )
    text = gantt_text(parse_document(document), 80, "ascii")
    assert "Agile: First delivery at 6, Second delivery at 7" in text


def test_text_refuses_an_iteration_shorter_than_two_cells() -> None:
    """At 40 columns an iteration of a tenth of a month is less than one cell."""
    document = lanes(iterations=[{"start": 0, "end": 0.1}], events=[])
    with pytest.raises(FitError, match="/tasks/1/iterations/0"):
        gantt_text(parse_document(document), 40, "ascii")
