"""No edge runs through a frame it has no end in.

A group, a composite state and each of a composite's regions draw a frame that
says *these belong together*. A line between two boxes outside one that goes
straight through it reads as an edge that goes in and comes out again, and the
reader looks inside for the box it is about. Nothing is written where it
crosses, so `collisions.py` cannot see it; `tools/frames.py` can, and the gate
is that it finds nothing in the gallery.

An edge with one end inside a frame crosses its border once, and one with both
ends inside never leaves it — the same check, asked the other way round.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from frames import border_crossings, check, frame_crossings, runs_along

from drawspec.errors import FitError
from drawspec.kinds.containers import Frame
from drawspec.kinds.graph import GraphDrawing, graph_drawing
from drawspec.schema import parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

FRAME = Frame(id="g", x=0.0, y=0.0, width=100.0, height=100.0, caption=None, depth=0)


def drawing(document: dict[str, Any]) -> GraphDrawing:
    return graph_drawing(parse_document(document), THEME, MEASURER)


def _nodes(*identifiers: str) -> list[dict[str, str]]:
    return [{"id": identifier, "text": identifier.upper()} for identifier in identifiers]


#: A above a nested pair of groups, Z below it, and an edge straight from A to Z:
#: the cheapest line between them is the one through both frames.
NESTED_FLOW: dict[str, Any] = {
    "version": 1,
    "kind": "flow",
    "nodes": _nodes("a", "m1", "m2", "z"),
    "groups": [
        {"id": "inner", "text": "Inner", "members": ["m1", "m2"]},
        {"id": "outer", "text": "Outer", "members": ["inner"]},
    ],
    "edges": [
        {"from": "a", "to": "m1"},
        {"from": "m1", "to": "m2"},
        {"from": "m2", "to": "z"},
        {"from": "a", "to": "z"},
    ],
}

#: A, then a composite B of two regions in the rank below it, and C beside B:
#: A to C ran down through B's second region.
REGIONS: dict[str, Any] = {
    "version": 1,
    "kind": "states",
    "initial": "a",
    "states": _nodes("a", "b1", "b2", "r1", "r2", "c"),
    "groups": [
        {
            "id": "b",
            "text": "B",
            "regions": [
                {"members": ["b1", "b2"], "initial": "b1"},
                {"members": ["r1", "r2"], "initial": "r1"},
            ],
        }
    ],
    "transitions": [
        {"from": "a", "to": "b", "event": "enter"},
        {"from": "b1", "to": "b2", "event": "next"},
        {"from": "r1", "to": "r2", "event": "next"},
        {"from": "a", "to": "c", "event": "skip"},
    ],
}


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        ([(-10.0, 50.0), (110.0, 50.0)], (2, True)),
        ([(-10.0, 120.0), (110.0, 120.0)], (0, False)),
        ([(50.0, 50.0), (50.0, 150.0)], (1, True)),
        ([(20.0, 50.0), (80.0, 50.0)], (0, True)),
        ([(-10.0, 0.0), (110.0, 0.0)], (0, False)),
        ([(50.0, 50.0), (50.0, 150.0), (60.0, 150.0), (60.0, 50.0)], (2, True)),
    ],
    ids=["through", "past", "out", "within", "along-border", "out-and-back"],
)
def test_border_crossings_counts_each_pass_through_the_border(
    points: list[tuple[float, float]], expected: tuple[int, bool]
) -> None:
    assert border_crossings(points, FRAME) == expected


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        ([(150.0, 160.0), (100.0, 160.0), (100.0, 20.0), (50.0, 20.0)], True),
        ([(150.0, 160.0), (112.0, 160.0), (112.0, 20.0), (50.0, 20.0)], False),
        ([(100.0, 80.0), (100.0, 20.0)], False),
        ([(150.0, 160.0), (98.0, 160.0), (98.0, 120.0), (50.0, 120.0)], False),
    ],
    ids=["on-the-border", "beside-it", "endpoint-run", "past-the-corner"],
)
def test_runs_along_finds_a_middle_run_on_a_border(
    points: list[tuple[float, float]], expected: bool
) -> None:
    assert runs_along(points, FRAME) is expected


def test_an_edge_between_two_outside_boxes_goes_round_nested_groups() -> None:
    assert frame_crossings(drawing(NESTED_FLOW)) == []


def test_an_edge_beside_a_composite_keeps_out_of_its_regions() -> None:
    assert frame_crossings(drawing(REGIONS)) == []


def test_edges_into_a_group_still_cross_its_border_once() -> None:
    built = drawing(NESTED_FLOW)
    frames = {frame.id: frame for frame in built.frames}
    into = next(route for route in built.routes if (route.source, route.target) == ("a", "m1"))
    assert border_crossings(into.points, frames["inner"])[0] == 1
    assert border_crossings(into.points, frames["outer"])[0] == 1


def test_the_invoice_cancellation_goes_round_the_issued_frame() -> None:
    """The gallery drawing the defect was reported on: Draft to Void ran through Issued."""
    assert check(REFERENCE / "states-invoice.json") == []


def test_no_reference_drawing_routes_an_edge_through_a_foreign_frame() -> None:
    """Every reference drawing — one that will not lay out is reported, not passed over."""
    found: dict[str, list[str]] = {}
    for path in sorted(REFERENCE.glob("*.json")):
        try:
            crossings = check(path)
        except FitError as error:
            found[path.stem] = [f"cannot be laid out: {error}"]
            continue
        if crossings:
            found[path.stem] = [str(crossing) for crossing in crossings]
    assert found == {}
