"""Self-loops in `flow`: the geometry `states` built, adopted.

The drawing that went wrong: a `flow` accepted an edge from a box to itself and
routed it out of the box's right side and back in through the middle of its
**top** — the very point the box's incoming arrow lands on. The two heads met,
and the loop read as a branch of the edge above rather than as *this step
again*. A loop now leaves and returns on one side of its box, across the
reading direction, with its label outside it and its room reserved in the
layout, so nothing else is drawn there.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec.kinds.graph import GraphDrawing, graph_drawing
from drawspec.routing import LOOP_SIDES
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
EPSILON = 1e-6

#: The report, as it was filed: three steps, the middle one retried.
RETRY: dict[str, Any] = {
    "version": 1,
    "kind": "flow",
    "nodes": [
        {"id": "a", "text": "Fetch the page"},
        {"id": "b", "text": "Parse it"},
        {"id": "c", "text": "Store the result"},
    ],
    "edges": [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "b", "label": "retry"},
        {"from": "b", "to": "c"},
    ],
}


def drawn(document: dict[str, Any]) -> GraphDrawing:
    return graph_drawing(parse_document(document), THEME, MEASURER)


def reference(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((REFERENCE / f"{name}.json").read_text("utf-8"))
    return document


def side_of(point: tuple[float, float], box: Any) -> str:
    x, y = point
    if abs(x - box.x) < EPSILON:
        return "left"
    if abs(x - (box.x + box.width)) < EPSILON:
        return "right"
    if abs(y - box.y) < EPSILON:
        return "top"
    if abs(y - (box.y + box.height)) < EPSILON:
        return "bottom"
    return "inside"


def test_the_reported_loop_no_longer_re_enters_through_its_incoming_edge() -> None:
    drawing = drawn(RETRY)
    (loop,) = drawing.loops
    box = drawing.boxes["b"]
    start, end = loop.route.points[0], loop.route.points[-1]
    assert side_of(start, box) == side_of(end, box) == loop.side
    assert loop.side in LOOP_SIDES[drawing.layout.direction]
    incoming = next(
        route for route in drawing.routes if route.target == "b" and route.source == "a"
    )
    assert end != incoming.points[-1]
    assert side_of(incoming.points[-1], box) == "top"


def test_a_loop_shares_no_point_with_any_other_edge() -> None:
    drawing = drawn(RETRY)
    (loop,) = drawing.loops
    others = [route for route in drawing.routes if route.source != route.target]
    mine = set(loop.route.points)
    for route in others:
        assert not mine & set(route.points)
        for (x1, y1), (x2, y2) in pairwise(route.points):
            for (x3, y3), (x4, y4) in pairwise(loop.route.points):
                overlap_x = min(max(x1, x2), max(x3, x4)) - max(min(x1, x2), min(x3, x4))
                overlap_y = min(max(y1, y2), max(y3, y4)) - max(min(y1, y2), min(y3, y4))
                assert overlap_x < -EPSILON or overlap_y < -EPSILON


@pytest.mark.parametrize("name", ["flow-retry"])
def test_every_loop_in_the_reference_is_clear_of_every_box_and_line(name: str) -> None:
    drawing = drawn(reference(name))
    assert len(drawing.loops) == 2
    for loop in drawing.loops:
        assert loop.side in LOOP_SIDES[drawing.layout.direction]
        left, top, right, bottom = loop.zone
        for identifier, box in drawing.boxes.items():
            if identifier == loop.route.source:
                continue
            assert (
                box.x + box.width <= left
                or box.x >= right
                or box.y + box.height <= top
                or box.y >= bottom
            ), identifier
        assert loop.label is not None
        west, north, east, south = loop.label.box
        for route in drawing.routes:
            for (x1, y1), (x2, y2) in pairwise(route.points):
                assert not (
                    min(x1, x2) < east - EPSILON
                    and max(x1, x2) > west + EPSILON
                    and min(y1, y2) < south - EPSILON
                    and max(y1, y2) > north + EPSILON
                )


def test_a_tree_draws_a_loop_the_same_way() -> None:
    document = dict(RETRY, kind="tree")
    drawing = drawn(document)
    (loop,) = drawing.loops
    assert loop.side in LOOP_SIDES[drawing.layout.direction]


def test_a_loop_on_a_group_is_refused() -> None:
    document = dict(
        RETRY,
        groups=[{"id": "g", "text": "Work", "members": ["a", "b"]}],
        edges=[*RETRY["edges"], {"from": "g", "to": "g", "label": "again"}],
    )
    assert [violation.pointer for violation in validate_document(document)] == ["/edges/3/to"]


def test_a_third_loop_on_one_box_is_refused() -> None:
    document = dict(
        RETRY,
        edges=[
            *RETRY["edges"],
            {"from": "b", "to": "b", "label": "again"},
            {"from": "b", "to": "b", "label": "and again"},
        ],
    )
    assert [violation.pointer for violation in validate_document(document)] == ["/edges/4/to"]


def test_two_loops_on_one_box_take_both_sides() -> None:
    document = dict(RETRY, edges=[*RETRY["edges"], {"from": "b", "to": "b", "label": "again"}])
    drawing = drawn(document)
    assert {loop.side for loop in drawing.loops} == set(LOOP_SIDES["down"])
