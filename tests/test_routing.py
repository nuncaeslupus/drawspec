"""T9 — orthogonal edge routing.

The gate is `edge_anchor_violations == 0`, and the four requirements it stands
for are the four rules §5 of the theme requirements gives arrows: they touch the
box at both ends, they turn at right angles, they have a shaft long enough to be
a line rather than a stuck-on head, and they do not cross a box.

Every assertion here is measured on the returned geometry, independently of the
router's own idea of what it did — the helpers at the bottom re-derive segment
crossing and length from the points alone.
"""

from __future__ import annotations

import math
from itertools import combinations, pairwise

import pytest
from spike_layout import REFERENCE_DIR, REFERENCES, layout_inputs

from drawspec.errors import LayoutError
from drawspec.layout.base import Spacing
from drawspec.layout.layered import LayeredEngine
from drawspec.routing import (
    Connector,
    Obstacle,
    Route,
    edge_primitives,
    minimum_rank_gap,
    route_edges,
    separate_lanes,
    shaft_length,
)
from drawspec.scene import Ellipse, Path, Polygon
from drawspec.schema import load_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
GAP = minimum_rank_gap(THEME)
SPACING = Spacing(node_gap=THEME.box.padding.horizontal, rank_gap=max(GAP, 24.0))

# A three-rank column: `a` above `b` above `c`, plus a sibling of `b` beside it.
# Deliberately not built by a layout engine — routing's contract is with boxes,
# whoever placed them.
COLUMN = (
    Obstacle("a", x=100.0, y=0.0, width=120.0, height=40.0),
    Obstacle("b", x=100.0, y=40.0 + GAP, width=120.0, height=40.0),
    Obstacle("c", x=100.0, y=80.0 + GAP * 2, width=120.0, height=40.0),
)
SIBLING = Obstacle("d", x=260.0, y=40.0 + GAP, width=120.0, height=40.0)


def routes(
    connectors: tuple[Connector, ...],
    boxes: tuple[Obstacle, ...] = COLUMN,
    direction: str = "down",
) -> tuple[Route, ...]:
    return route_edges(connectors, boxes, THEME, direction=direction)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_route_endpoints_lie_exactly_on_node_borders() -> None:
    """Neither short nor overshooting: the end is *on* the border, not near it.

    An endpoint short of the box is the 'line that does not reach' family; an
    endpoint past it is a line that appears to pierce the shape. Both are
    unrepresentable when the port is computed from the border in the first place.
    """
    built = routes((Connector("a", "b"), Connector("b", "c"), Connector("a", "c")))
    boxes = {box.id: box for box in COLUMN}
    for route in built:
        assert _on_border(route.points[0], boxes[route.source]), (route.source, route.points[0])
        assert _on_border(route.points[-1], boxes[route.target]), (route.target, route.points[-1])


def test_route_produces_only_axis_aligned_segments() -> None:
    """Right angles, not diagonals — the author cannot ask for one either."""
    built = routes((Connector("a", "b"), Connector("a", "c"), Connector("c", "a")))
    for route in built:
        for first, second in pairwise(route.points):
            assert first[0] == pytest.approx(second[0]) or first[1] == pytest.approx(second[1]), (
                route.source,
                route.target,
                (first, second),
            )


def test_route_shaft_length_is_at_least_the_theme_minimum() -> None:
    """No head-without-shaft is expressible: the line under the head is measured."""
    built = routes((Connector("a", "b"), Connector("b", "c"), Connector("a", "c")))
    for route in built:
        assert shaft_length(route, THEME) >= THEME.edge.min_shaft_length - 1e-9


def test_route_does_not_cross_any_node_box() -> None:
    """Including the boxes it starts and ends on, which it may only touch."""
    boxes = (*COLUMN, SIBLING)
    built = route_edges(
        (Connector("a", "b"), Connector("a", "c"), Connector("d", "c"), Connector("c", "a")),
        boxes,
        THEME,
    )
    for route in built:
        for first, second in pairwise(route.points):
            for box in boxes:
                assert not _crosses(first, second, box), (route.source, route.target, box.id)


# --------------------------------------------------------------------------
# What the router had to do to get there
# --------------------------------------------------------------------------


def test_route_between_adjacent_ranks_is_a_single_straight_segment() -> None:
    """The simple case stays simple: two points, no detour, no bend."""
    (route,) = routes((Connector("a", "b"),))
    assert len(route.points) == 2
    assert route.points[0][0] == pytest.approx(route.points[1][0])


def test_route_over_a_rank_it_would_otherwise_cross_bends_around_it() -> None:
    """`a` to `c` passes `b`'s rank, so it cannot be the straight line."""
    (route,) = routes((Connector("a", "c"),))
    assert len(route.points) > 2
    for first, second in pairwise(route.points):
        assert not _crosses(first, second, COLUMN[1])


def test_route_of_a_back_edge_leaves_the_top_and_returns_to_the_bottom() -> None:
    """The author's direction, drawn upwards, around the side of the drawing."""
    (route,) = routes((Connector("c", "a"),))
    start, end = route.points[0], route.points[-1]
    assert start[1] == pytest.approx(COLUMN[2].y)
    assert end[1] == pytest.approx(COLUMN[0].y + COLUMN[0].height)


def test_two_edges_leaving_one_node_do_not_share_a_port() -> None:
    """Two arrows from one box that start at the same pixel read as one arrow."""
    built = route_edges(
        (Connector("b", "c"), Connector("b", "d")), (*COLUMN, SIBLING), THEME, direction="down"
    )
    starts = {route.points[0] for route in built}
    assert len(starts) == 2


def test_routing_is_deterministic() -> None:
    connectors = (Connector("a", "b"), Connector("a", "c"), Connector("c", "a"))
    assert routes(connectors) == routes(connectors)


def test_route_in_the_right_direction_leaves_the_side() -> None:
    """`right` is not a transposed picture — but the ports do turn with it."""
    boxes = (
        Obstacle("a", x=0.0, y=100.0, width=100.0, height=40.0),
        Obstacle("b", x=100.0 + GAP, y=100.0, width=100.0, height=40.0),
    )
    (route,) = route_edges((Connector("a", "b"),), boxes, THEME, direction="right")
    assert route.points[0][0] == pytest.approx(boxes[0].x + boxes[0].width)
    assert route.points[-1][0] == pytest.approx(boxes[1].x)


def test_self_loop_leaves_and_returns_to_its_own_box() -> None:
    (route,) = routes((Connector("b", "b"),))
    box = COLUMN[1]
    assert _on_border(route.points[0], box)
    assert _on_border(route.points[-1], box)
    assert route.points[0] != route.points[-1]
    for first, second in pairwise(route.points):
        assert not _crosses(first, second, box)


def test_route_into_a_diamond_lands_on_the_diamond_and_not_on_its_box() -> None:
    """The failure this cannot have: an arrow stopping in the corner beside it.

    Two edges arrive at the same side, so neither port is the apex, and the
    anchor has to be somewhere on the sloped edge — which is precisely the case a
    bounding-box endpoint gets wrong by the width of the corner.
    """
    boxes = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=140.0, y=0.0, width=100.0, height=40.0),
        Obstacle("d", x=40.0, y=40.0 + GAP, width=160.0, height=80.0, shape="diamond"),
    )
    built = route_edges((Connector("a", "d"), Connector("b", "d")), boxes, THEME)
    diamond = boxes[2]
    for route in built:
        x, y = route.points[-1]
        assert y > diamond.y + 1e-6, "the arrow stopped on the rectangle, not the diamond"
        expected = diamond.centre[1] - (diamond.height / 2) * (
            1 - abs(x - diamond.centre[0]) / (diamond.width / 2)
        )
        assert y == pytest.approx(expected)


def test_route_into_an_ellipse_lands_on_its_curve() -> None:
    boxes = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=0.0, y=40.0 + GAP, width=100.0, height=60.0, shape="ellipse"),
    )
    (route,) = route_edges((Connector("a", "b"),), boxes, THEME)
    x, y = route.points[-1]
    centre_x, centre_y = boxes[1].centre
    across = (x - centre_x) / (boxes[1].width / 2)
    assert y == pytest.approx(centre_y - (boxes[1].height / 2) * math.sqrt(1 - across**2))


def test_route_between_boxes_too_close_together_is_refused() -> None:
    """A shaft that would be invisible is a `LayoutError`, not a short line.

    This is the one place the minimum shaft length becomes a *layout* constraint:
    routing cannot invent room, so it says so, and the caller separates the ranks.
    """
    cramped = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=0.0, y=44.0, width=100.0, height=40.0),
    )
    with pytest.raises(LayoutError, match="shaft"):
        route_edges((Connector("a", "b"),), cramped, THEME)


def test_minimum_rank_gap_is_exactly_what_routing_demands() -> None:
    """The number the caller needs, published by the stage that enforces it."""
    boxes = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=0.0, y=40.0 + minimum_rank_gap(THEME), width=100.0, height=40.0),
    )
    (route,) = route_edges((Connector("a", "b", role="exchange"),), boxes, THEME)
    assert shaft_length(route, THEME) >= THEME.edge.min_shaft_length - 1e-9


def test_routing_an_edge_to_a_box_that_is_not_there_is_refused() -> None:
    with pytest.raises(LayoutError, match="nowhere"):
        routes((Connector("a", "elsewhere"),))


# --------------------------------------------------------------------------
# The gate, on real graphs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("direction", ["down", "right"])
def test_reference_graphs_route_without_an_anchor_violation(document: str, direction: str) -> None:
    """The gate measured where it counts: laid-out documents, not fixtures.

    And measured against the **shapes**, which is stricter than the router's own
    idea of the world in one direction and looser in the other. Stricter, because
    an endpoint on the bounding box of a diamond is a violation here and the
    router has to have projected it onto the sloped edge. Looser, because the
    corner beside that diamond is empty space a route may legitimately use, while
    the router treats the whole rectangle as solid — a route through it would be
    a real failure of the check, not an artefact of the conservative grid.
    """
    theme, measurer = THEME, MEASURER
    parsed = load_document(REFERENCE_DIR / f"{document}.json")
    nodes, edges = layout_inputs(parsed, theme, measurer)
    layout = LayeredEngine(spacing=SPACING).layout(nodes, edges, direction)
    shapes = {node.id: theme.roles[node.role].shape for node in parsed.nodes}
    obstacles = tuple(
        Obstacle(
            identifier,
            x=place.x,
            y=place.y,
            width=place.width,
            height=place.height,
            shape=shapes[identifier],
        )
        for identifier, place in sorted(layout.placements.items())
    )
    boxes = {box.id: box for box in obstacles}
    connectors = tuple(Connector(edge.source, edge.target, role=edge.role) for edge in parsed.edges)

    built = route_edges(connectors, obstacles, theme, direction=direction)
    assert len(built) == len(connectors)
    for route in built:
        for point, identifier in (
            (route.points[0], route.source),
            (route.points[-1], route.target),
        ):
            assert _depth(boxes[identifier], point) == pytest.approx(1.0, abs=1e-6), (
                f"{route.source}->{route.target} does not touch {identifier}"
            )
        assert shaft_length(route, theme) >= theme.edge.min_shaft_length - 1e-9
        for first, second in pairwise(route.points):
            assert first[0] == pytest.approx(second[0]) or first[1] == pytest.approx(second[1])
            for box in obstacles:
                assert not _enters(first, second, box), (
                    f"{route.source}->{route.target} passes through {box.id}"
                )


def _depth(box: Obstacle, point: tuple[float, float]) -> float:
    """Where the point is relative to the shape's outline: 1 is on it."""
    centre_x, centre_y = box.centre
    across = abs(point[0] - centre_x) / (box.width / 2)
    down = abs(point[1] - centre_y) / (box.height / 2)
    if box.shape == "diamond":
        return across + down
    if box.shape == "ellipse":
        return math.hypot(across, down)
    if box.shape == "pill":
        radius = min(box.height, box.width) / 2
        beyond = max(abs(point[0] - centre_x) - (box.width / 2 - radius), 0.0)
        return math.hypot(beyond, point[1] - centre_y) / radius
    return max(across, down)


def _enters(
    first: tuple[float, float], second: tuple[float, float], box: Obstacle, samples: int = 40
) -> bool:
    """Whether any point strictly between the ends is inside the shape."""
    for step in range(1, samples):
        fraction = step / samples
        point = (
            first[0] + (second[0] - first[0]) * fraction,
            first[1] + (second[1] - first[1]) * fraction,
        )
        if _depth(box, point) < 1 - 1e-6:
            return True
    return False


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


def test_edge_primitives_put_the_head_tip_on_the_route_end() -> None:
    """The head points at the box, and touches it — that is the same point."""
    (route,) = routes((Connector("a", "b"),))
    parts = edge_primitives(route, THEME)
    head = next(part for part in parts if isinstance(part, Polygon))
    assert route.points[-1] in head.points


def test_edge_primitives_of_a_headless_role_are_just_the_line() -> None:
    (route,) = routes((Connector("a", "b", role="link"),))
    parts = edge_primitives(route, THEME)
    assert len(parts) == 1
    assert isinstance(parts[0], Path)


def test_edge_primitives_of_an_exchange_have_a_head_at_both_ends() -> None:
    boxes = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=0.0, y=40.0 + minimum_rank_gap(THEME), width=100.0, height=40.0),
    )
    (route,) = route_edges((Connector("a", "b", role="exchange"),), boxes, THEME)
    heads = [part for part in edge_primitives(route, THEME) if isinstance(part, Polygon)]
    assert len(heads) == 2
    assert route.points[0] in heads[1].points
    assert route.points[-1] in heads[0].points


def test_edge_primitives_carry_the_edge_role_and_no_styling() -> None:
    (route,) = routes((Connector("a", "b", role="weak"),))
    for part in edge_primitives(route, THEME):
        assert part.role == "weak"
        assert not hasattr(part, "stroke")


def test_an_open_head_is_drawn_as_an_open_path() -> None:
    """A `weak` edge's head is a V, and a V that closes is a triangle."""
    (route,) = routes((Connector("a", "b", role="weak"),))
    parts = edge_primitives(route, THEME)
    assert any(isinstance(part, Path) and not part.closed for part in parts)
    assert not any(isinstance(part, Ellipse) for part in parts)


# --------------------------------------------------------------------------
# Helpers, independent of the router's own geometry
# --------------------------------------------------------------------------


def _on_border(point: tuple[float, float], box: Obstacle) -> bool:
    """On the outline of `box`: on one of its sides, and within the other span."""
    x, y = point
    within_x = box.x - 1e-6 <= x <= box.right + 1e-6
    within_y = box.y - 1e-6 <= y <= box.bottom + 1e-6
    on_vertical = math.isclose(x, box.x, abs_tol=1e-6) or math.isclose(x, box.right, abs_tol=1e-6)
    on_horizontal = math.isclose(y, box.y, abs_tol=1e-6) or math.isclose(
        y, box.bottom, abs_tol=1e-6
    )
    return (on_vertical and within_y) or (on_horizontal and within_x)


def _crosses(first: tuple[float, float], second: tuple[float, float], box: Obstacle) -> bool:
    """Whether the segment passes through the box's interior. Touching is fine."""
    left, right = sorted((first[0], second[0]))
    top, bottom = sorted((first[1], second[1]))
    return (
        left < box.right - 1e-6
        and right > box.x + 1e-6
        and top < box.bottom - 1e-6
        and bottom > box.y + 1e-6
    )


# --------------------------------------------------------------------------
# What a pair of routes looks like — the failures one route cannot have
# --------------------------------------------------------------------------
#
# Everything above measures one route against the boxes. These measure routes
# against *each other*, which is the blind spot the router has by construction:
# it costs each edge by length and corners, both edges get the same cheapest
# answer, and each is individually perfect. Only the pair is wrong.


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("direction", ["down", "right"])
def test_no_two_routes_run_down_the_same_line(document: str, direction: str) -> None:
    """`overlapping_route_length == 0` — two lines a reader could not tell apart.

    Where two routes share a coordinate *and* an overlapping span, they are drawn
    one on top of the other: three arrows out of a box leave as one thick line
    that splits at the end, and a fourth crossing them turns at the same
    coordinate, so which line turned and which carried on is unanswerable.
    """
    built = _reference_routes(document, direction)
    for first, second in combinations(built, 2):
        for one in first.segments:
            for two in second.segments:
                assert not _shares_a_line(one, two), (
                    f"{first.source}->{first.target} and {second.source}->{second.target} "
                    f"run down the same line: {one} and {two}"
                )


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("direction", ["down", "right"])
def test_every_route_keeps_its_clearance_from_boxes_it_only_passes(
    document: str, direction: str
) -> None:
    """A connector flush against a border reads as part of that box.

    Not crossing is not enough, and the difference is entirely a reader's
    problem: a line down the side of a box it has nothing to do with looks like a
    second border, and a line along the bottom of one looks like an underline
    under its label. Both are exactly as short and as straight as the line a few
    units away, so the router will produce them given the chance.
    """
    built = _reference_routes(document, direction)
    boxes = {box.id: box for box in _reference_obstacles(document, direction)}
    for route in built:
        others = [box for name, box in boxes.items() if name not in (route.source, route.target)]
        for first, second in route.segments:
            for box in others:
                assert not _crosses(first, second, box.grown(THEME.edge.clearance)), (
                    f"{route.source}->{route.target} runs within "
                    f"{THEME.edge.clearance:g} of {box.id}"
                )


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("direction", ["down", "right"])
def test_every_head_has_a_straight_run_of_its_own_to_sit_on(document: str, direction: str) -> None:
    """A long route can still arrive with nowhere to put its arrow.

    Total shaft length says nothing about the last segment, and the last segment
    is what the head is drawn along. A route that turns a unit before it lands
    puts the head across the corner: the point is on the border, the back of it
    sticks out sideways, and it reads as a blot rather than as an arrow.
    """
    for route in _reference_routes(document, direction):
        role = THEME.role_for(route.role)
        if getattr(role, "head", "none") != "none":
            first, second = route.segments[-1]
            assert math.dist(first, second) >= THEME.edge.head_length - 1e-6, (
                f"the head of {route.source}->{route.target} has "
                f"{math.dist(first, second):.2f} of line to sit on"
            )


def test_two_edges_crossing_the_same_gap_are_moved_apart() -> None:
    """The separation, on the smallest arrangement that produces the failure.

    Two edges from one rank to the next, crossing sideways: the cheapest route
    for both runs down the one lane in the gap, so without separation they share
    it exactly.
    """
    boxes = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=200.0, y=0.0, width=100.0, height=40.0),
        Obstacle("c", x=0.0, y=40.0 + GAP * 2, width=100.0, height=40.0),
        Obstacle("d", x=200.0, y=40.0 + GAP * 2, width=100.0, height=40.0),
    )
    built = routes((Connector("a", "d"), Connector("b", "c")), boxes)
    lanes = {round(point[1], 6) for route in built for point in route.points[1:-1]}
    assert len(lanes) > 1, "both routes turned on the same line"


def _reference_obstacles(document: str, direction: str) -> tuple[Obstacle, ...]:
    parsed = load_document(REFERENCE_DIR / f"{document}.json")
    nodes, edges = layout_inputs(parsed, THEME, MEASURER)
    layout = LayeredEngine(spacing=SPACING).layout(nodes, edges, direction)
    shapes = {node.id: THEME.roles[node.role].shape for node in parsed.nodes}
    return tuple(
        Obstacle(
            identifier,
            x=place.x,
            y=place.y,
            width=place.width,
            height=place.height,
            shape=shapes[identifier],
        )
        for identifier, place in sorted(layout.placements.items())
    )


def _reference_routes(document: str, direction: str) -> tuple[Route, ...]:
    parsed = load_document(REFERENCE_DIR / f"{document}.json")
    connectors = tuple(Connector(edge.source, edge.target, role=edge.role) for edge in parsed.edges)
    return route_edges(
        connectors, _reference_obstacles(document, direction), THEME, direction=direction
    )


def _shares_a_line(
    one: tuple[tuple[float, float], tuple[float, float]],
    two: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    """Whether two axis-aligned segments are collinear with an overlapping span."""
    for axis, along in ((0, 1), (1, 0)):
        flat_one = math.isclose(one[0][axis], one[1][axis], abs_tol=1e-6)
        flat_two = math.isclose(two[0][axis], two[1][axis], abs_tol=1e-6)
        if not (flat_one and flat_two and math.isclose(one[0][axis], two[0][axis], abs_tol=1e-6)):
            continue
        low = max(min(one[0][along], one[1][along]), min(two[0][along], two[1][along]))
        high = min(max(one[0][along], one[1][along]), max(two[0][along], two[1][along]))
        if high - low > 1e-6:
            return True
    return False


# --------------------------------------------------------------------------
# How far apart a pair has to be
# --------------------------------------------------------------------------


def _near_a_line(
    one: tuple[tuple[float, float], tuple[float, float]],
    two: tuple[tuple[float, float], tuple[float, float]],
    within: float,
) -> bool:
    """`_shares_a_line`, but asking about a band rather than about a coordinate."""
    for axis, along in ((0, 1), (1, 0)):
        flat_one = math.isclose(one[0][axis], one[1][axis], abs_tol=1e-6)
        flat_two = math.isclose(two[0][axis], two[1][axis], abs_tol=1e-6)
        if not (flat_one and flat_two and abs(one[0][axis] - two[0][axis]) < within - 1e-6):
            continue
        low = max(min(one[0][along], one[1][along]), min(two[0][along], two[1][along]))
        high = min(max(one[0][along], one[1][along]), max(two[0][along], two[1][along]))
        if high - low > 1e-6:
            return True
    return False


def _fan(*turns: float) -> tuple[Route, ...]:
    """Three edges out of one box, turning at the coordinates given.

    The shape a tree makes: leave the right-hand border at three heights, run a
    little way out, turn, and go to three targets. What the reviewer saw is that
    the three turns land within a few units of each other.
    """
    return tuple(
        Route(
            source="one",
            target=f"t{index}",
            role="flow",
            points=(
                (100.0, 200.0 + index * 10),
                (turn, 200.0 + index * 10),
                (turn, 400.0),
                (500.0, 400.0),
            ),
        )
        for index, turn in enumerate(turns)
    )


def test_a_fan_of_turns_a_few_units_apart_is_prised_apart() -> None:
    """Not on top of each other is not far enough apart.

    Three edges leaving one box turned at three *different* coordinates four and
    eight units apart, so nothing was ever collinear, the old exact-coordinate
    test saw nothing to do, and the fan was drawn as a bundle whose corners a
    reader cannot tell apart — the failure the pass exists to prevent, at a
    smaller scale.
    """
    spacing = THEME.edge.lane_spacing
    moved = separate_lanes(_fan(210.0, 214.0, 218.0), (), THEME)
    turns = sorted(route.points[1][0] for route in moved)
    for first, second in pairwise(turns):
        assert second - first >= spacing - 1e-6, turns


def test_prising_a_fan_apart_leaves_it_where_it_was() -> None:
    """Centred on the band, so the group does not migrate across the drawing."""
    before = _fan(210.0, 214.0, 218.0)
    after = separate_lanes(before, (), THEME)
    middle = sum(route.points[1][0] for route in before) / len(before)
    assert sum(route.points[1][0] for route in after) / len(after) == pytest.approx(middle)


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("direction", ["down", "right"])
def test_two_routes_alongside_each_other_keep_a_lane_apart(document: str, direction: str) -> None:
    """The same rule, held on every reference drawing.

    Two runs that a shift could not fix stay where they were, so this asks only
    about runs both of which were free to move.
    """
    built = _reference_routes(document, direction)
    spacing = THEME.edge.lane_spacing
    for first, second in combinations(built, 2):
        for one in _movable_segments(first):
            for two in _movable_segments(second):
                assert not _near_a_line(one, two, spacing), (
                    f"{first.source}->{first.target} and {second.source}->{second.target} "
                    f"run within {spacing:g} of each other: {one} and {two}"
                )


def _movable_segments(
    route: Route,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """The runs with a corner at each end — the ones the separation pass may move."""
    segments = route.segments
    return [segment for index, segment in enumerate(segments) if 0 < index < len(segments) - 1]


def test_a_heavier_edge_gets_a_bigger_head() -> None:
    """Otherwise a `strong` edge reads as a thick line that stops, not as an arrow.

    The head is barely wider than the shaft it sits on at 2.5 units of weight and
    six of head, which is what the reviewer saw.
    """
    assert THEME.head_length_for("strong") > THEME.head_length_for("flow")
    heavy = THEME.role_for("strong").stroke_width / THEME.role_for("flow").stroke_width
    assert THEME.head_length_for("strong") == pytest.approx(THEME.head_length_for("flow") * heavy)


def test_a_lighter_edge_keeps_the_theme_s_own_head() -> None:
    """The shaft may be as quiet as the theme likes; *which way* may not."""
    assert THEME.role_for("link").stroke_width < THEME.edge.stroke_width
    assert THEME.head_length_for("link") == pytest.approx(THEME.edge.head_length)


def test_the_widest_head_covers_every_edge_role() -> None:
    """Routing reserves room for a head before it knows which role will use it."""
    assert THEME.widest_head == max(THEME.head_length_for(name) for name in THEME.edge_roles)
