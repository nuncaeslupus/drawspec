"""Two routes may not cross when the sides they use allow them not to.

This is the one failure the router's own search cannot see, and it is the same
shape as the bundle that `separate_lanes` was written for: each route is
individually the cheapest correct answer, and only the *pair* is wrong. A reader
seeing two lines cross assumes the crossing means something.

The case here is a fan — one box with several edges to boxes below it, or several
boxes with edges to one. The router assigns those edges ports in the order of the
boxes they point at, so the arrows leave in the same left-to-right order as their
targets and nothing needs to cross. What broke that was the pass *after* it:
`separate_lanes` prises apart runs drawn on top of each other, and it handed out
the new lanes in the order the runs happened to be listed. For the band that most
needs separating — several edges taking the identical cheapest path across one
gap, so every run is on the exact same line — ordering by that line is a tie for
all of them, and a tie sorted is a tie kept. The lanes went out in the order the
edges were written in the document, and any pair whose order that reversed was a
pair that now crossed.

So the assertion is on the drawing rather than on the mechanism: route the fan,
and count how many pairs of polylines intersect.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pytest

from drawspec.render import render_document
from drawspec.routing import Route
from drawspec.schema import parse_document
from drawspec.theme import load_theme

Point = tuple[float, float]
Segment = tuple[Point, Point]


def _crosses(first: Segment, second: Segment) -> bool:
    """Do two straight segments meet other than at an endpoint?

    Endpoints are excluded on purpose: two routes that share a box meet at that
    box's border by construction, and a route touching another's corner is a
    junction rather than a crossing. Only a proper interior intersection is a
    line drawn through a line.
    """
    (x1, y1), (x2, y2) = first
    (x3, y3), (x4, y4) = second
    denominator = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(denominator) < 1e-9:  # parallel, including collinear
        return False
    along = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / denominator
    across = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / denominator
    edge = 1e-6
    return edge < along < 1 - edge and edge < across < 1 - edge


def crossing_pairs(routes: list[Route]) -> list[tuple[str, str]]:
    """Every pair of routes that intersect, named by their endpoints."""
    found = []
    for first, second in combinations(routes, 2):
        if any(_crosses(one, other) for one in first.segments for other in second.segments):
            found.append((f"{first.source}->{first.target}", f"{second.source}->{second.target}"))
    return found


def routes_of(document: dict[str, Any]) -> list[Route]:
    """Render a document and hand back the routes the router produced.

    Captured through the router's own entry point rather than parsed back out of
    the SVG: the finished drawing carries chart lines, timeline axes and shape
    outlines as paths too, and counting those as crossings measures the wrong
    thing entirely.

    **Only the last attempt counts.** `render_document` lays out through `fit`,
    which calls its attempt again at a smaller scale factor every time one raises
    `FitError` — so a document that does not fit at full size routes more than
    once, and accumulating across those calls would measure a *discarded* layout
    alongside the finished one. Every fan here fits at the first factor, so this
    is a trap rather than a live bug, and it is the kind that waits: the helper
    is general, and the first test document that needs a retry would start
    reporting crossings drawn in a drawing nobody sees.

    The count is asserted rather than assumed. Taking the last call is only the
    same thing as taking the successful attempt while one attempt means one call;
    a kind that routed twice in a single pass would make that silently false, so
    it fails here instead.
    """
    from drawspec.kinds import graph

    attempts: list[list[Route]] = []
    original = graph.route_edges

    def capture(*arguments: Any, **keywords: Any) -> Any:
        produced = original(*arguments, **keywords)
        attempts.append(list(produced))
        return produced

    graph.route_edges = capture
    try:
        render_document(parse_document(document), load_theme(None), "inline")
    finally:
        graph.route_edges = original

    assert attempts, "nothing was routed: this document has no edges to measure"
    assert len(attempts) == 1, (
        f"routed {len(attempts)} times for one document; the helper takes the last "
        f"call as the finished layout, which is only right when there is one"
    )
    return attempts[-1]


def fan_out(targets: int) -> dict[str, Any]:
    """One box with `targets` edges leaving it, to boxes written out of order.

    Written out of order deliberately. The ports are assigned by where each
    target *is*, so the document's own ordering should not reach the drawing —
    and when it did, this is the document that showed it.
    """
    names = [f"t{position}" for position in range(targets)]
    return {
        "version": 1,
        "kind": "flow",
        "title": "A fan-out",
        "nodes": [{"id": "source", "text": "The one they all leave"}]
        + [{"id": name, "text": f"Target {name[1:]}"} for name in reversed(names)],
        "edges": [{"from": "source", "to": name} for name in reversed(names)],
    }


def fan_in(sources: int) -> dict[str, Any]:
    """Several boxes with one edge each into a box below them."""
    names = [f"s{position}" for position in range(sources)]
    return {
        "version": 1,
        "kind": "flow",
        "title": "A fan-in",
        "nodes": [{"id": name, "text": f"Source {name[1:]}"} for name in reversed(names)]
        + [{"id": "sink", "text": "The one they all reach"}],
        "edges": [{"from": name, "to": "sink"} for name in reversed(names)],
    }


#: A fan of four or more still crosses, for a *second* reason, and these are
#: marked rather than deleted so the suite carries the defect instead of a
#: comment somewhere carrying it.
#:
#: The lane a route turns in comes from `_reach`, which sends the stub out to the
#: first lane in front of its port — but caps it at half the room actually in
#: front of *that* port. The ports of one fan are at different heights, so they
#: have different things in front of them, so they get different reaches: four
#: edges leaving one box turn in two lanes, alternating, instead of nesting one
#: inside the next. A route that turns late then runs horizontally straight
#: through the vertical leg of one that turned early.
#:
#: The ports themselves are in the right order and the separation pass now keeps
#: that order, so this is the last mechanism between a fan and a clean drawing.
#: Fixing it means making the reaches of one fan monotone with their ports, in
#: `_approach` — a change to how a route is proposed, not to how two of them are
#: prised apart, which is why it is not in this commit.
_SECOND_MECHANISM = pytest.mark.xfail(
    reason="fan lanes alternate because _reach is capped per port; see the note above",
    strict=True,
)


@pytest.mark.parametrize(
    "width",
    [2, 3, pytest.param(4, marks=_SECOND_MECHANISM), pytest.param(5, marks=_SECOND_MECHANISM)],
)
def test_a_fan_out_does_not_cross_its_own_arrows(width: int) -> None:
    crossings = crossing_pairs(routes_of(fan_out(width)))
    assert crossings == [], f"{width} edges out of one box crossed: {crossings}"


@pytest.mark.parametrize(
    "width",
    [2, 3, pytest.param(4, marks=_SECOND_MECHANISM), pytest.param(5, marks=_SECOND_MECHANISM)],
)
def test_a_fan_in_does_not_cross_its_own_arrows(width: int) -> None:
    crossings = crossing_pairs(routes_of(fan_in(width)))
    assert crossings == [], f"{width} edges into one box crossed: {crossings}"


def test_the_document_order_of_the_edges_does_not_reach_the_drawing() -> None:
    """The same fan, written in both orders, draws the same lines.

    This is the property the crossing was a symptom of. Ports are chosen from
    where the targets are, so reversing the edge list must not move a single
    point — and while `separate_lanes` was handing out lanes in list order, it
    did.
    """
    forward = fan_out(4)
    backward = {**forward, "edges": list(reversed(forward["edges"]))}
    drawn = {(route.source, route.target): route.points for route in routes_of(forward)}
    redrawn = {(route.source, route.target): route.points for route in routes_of(backward)}
    assert drawn == redrawn
