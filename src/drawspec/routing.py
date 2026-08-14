"""Orthogonal edge routing: border anchoring, right angles, and a real shaft.

Four of the eleven failure families are settled in this file, and all four are
about the same thing — a line that says something false about the boxes it
connects. A line stopping short of its target does not say "these two"; a line
overshooting says "through this one"; a diagonal lands at an angle that reads as
a mistake; and a head with no shaft is not an arrow at all, just a mark stuck to
a box.

The answer is to make each of them unrepresentable rather than unlikely:

**Endpoints are ports on the border.** A route starts at a point computed *from*
the source box's outline and ends at one computed from the target's, so "reaches
the box" is not a tolerance to check — there is no expression in this module for
an endpoint that is anywhere else.

**Every segment is axis-aligned.** Routes are found on a grid whose lines are
horizontal and vertical, so a diagonal cannot come out of it.

**Obstacles are the grid, too.** A grid step that would pass through the
interior of any box is removed before the search starts, so a route that crosses
a box is not a bad route — it is not a route.

**The shaft is measured, and a short one is refused.** `minimum_rank_gap` is the
separation this stage needs, published for whoever chooses the layout spacing;
when the boxes arrive closer than that, routing raises rather than drawing a
head with nothing behind it. That is the theme requirements' rule 2 made
mechanical: the remedy for arrows that will not fit is more room or the other
direction, never a shorter arrow.

The search itself is a Dijkstra over the Hanan grid of the obstacle coordinates,
with a cost per corner as well as per unit of length. The corner cost is what
makes the router prefer the straight line between adjacent ranks and take the
tidy dog-leg when it cannot: without it, every route of equal length is equally
good and the picture becomes staircases.
"""

from __future__ import annotations

import heapq
import math
from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Final

from drawspec.errors import LayoutError
from drawspec.scene import Ellipse, Path, Polygon, Primitive, TextRun
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The four sides a port may sit on.
SIDES: Final = ("top", "right", "bottom", "left")

#: Which way is out of the box, per side.
OUTWARD: Final[Mapping[str, tuple[float, float]]] = {
    "top": (0.0, -1.0),
    "bottom": (0.0, 1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
}

#: What one corner costs, in the same units as length. High enough that a route
#: takes a detour of a few units rather than an extra bend, low enough that it
#: will not walk half the diagram to avoid one.
TURN_COST: Final = 12.0

#: How much of a side's span the ports of several edges are spread across. Less
#: than the whole of it, so a port never lands on a corner where the head would
#: point at nothing.
PORT_SPREAD: Final = 0.6

#: Half an end treatment's width, as a fraction of its length. A head is a
#: direction made visible, and one much narrower than this reads as the line
#: coming to a point rather than as an arrow arriving somewhere.
HEAD_SPREAD: Final = 0.45

#: How far a label sits from the line it names, before anything is in the way.
LABEL_GAP: Final = 4.0

#: The multiples of that gap tried in turn, outwards, when something is.
LABEL_OFFSETS: Final = (1.0, 2.0, 3.5, 5.0, 7.0)

#: Where along a segment a label is tried: the middle, then either side of it.
LABEL_POSITIONS: Final = (0.5, 0.35, 0.65, 0.2, 0.8)

#: Coordinates are rounded to this many decimals before they become grid lines,
#: so a port computed twice is the same grid line twice.
GRID_PRECISION: Final = 9

_TOLERANCE: Final = 1e-7

#: How many times the lane separation is applied to its own output. Moving a run
#: lengthens the runs either side of it, so a pass can create the overlap the
#: next one settles; three is one more than any reference document has needed.
SEPARATION_PASSES: Final = 3

#: Direction codes for the search: +x, -x, +y, -y.
_MOVES: Final = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass(frozen=True)
class Obstacle:
    """An axis-aligned box a route may touch but never cross.

    Routing knows nothing about roles, text or ranks: a box is somewhere a line
    cannot go, and the two it belongs to are only special in that it may land on
    their outline.

    `shape` is the one thing it does need beyond the rectangle, and it is needed
    for a specific reason: an arrow into a `decision` that stops on the diamond's
    *bounding box* stops in mid-air, because the diamond is only half of it. So
    the box is what a route routes around, and the shape is what a route lands
    on. Anything the theme does not draw as a diamond, an ellipse or a pill is a
    rectangle, and for a rectangle the two are the same.
    """

    id: str
    x: float
    y: float
    width: float
    height: float
    shape: str = "rect"

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def centre(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    def overlaps(self, box: tuple[float, float, float, float]) -> bool:
        """Whether a rectangle meets this obstacle's **shape**.

        Exact for all four shapes, and it matters most for the diamond: the empty
        corner beside a `decision` is where a flow chart has always put its `yes`
        and `no`, and treating the bounding rectangle as solid is what would deny
        a label the one place it obviously belongs.

        Each case is the same trick — the nearest point of the rectangle to the
        shape's centre line is found by clamping, and the shape's own inequality
        is evaluated there. It is exact because every one of these shapes is
        convex and its defining function is smallest at that point.
        """
        left, top, right, bottom = box
        centre_x, centre_y = self.centre
        near_x = min(max(centre_x, left), right)
        near_y = min(max(centre_y, top), bottom)
        half_width, half_height = self.width / 2, self.height / 2
        if not half_width or not half_height:
            return False

        if self.shape == "diamond":
            across = abs(near_x - centre_x) / half_width + abs(near_y - centre_y) / half_height
            return across < 1 - _TOLERANCE
        if self.shape == "ellipse":
            return (
                math.hypot((near_x - centre_x) / half_width, (near_y - centre_y) / half_height)
                < 1 - _TOLERANCE
            )
        if self.shape == "pill":
            radius = min(half_width, half_height)
            flat = half_width - radius
            away_x = max(left - (centre_x + flat), (centre_x - flat) - right, 0.0)
            away_y = max(top - centre_y, centre_y - bottom, 0.0)
            return math.hypot(away_x, away_y) < radius - _TOLERANCE
        return (
            left < self.right - _TOLERANCE
            and self.x < right - _TOLERANCE
            and top < self.bottom - _TOLERANCE
            and self.y < bottom - _TOLERANCE
        )

    def grown(self, margin: float) -> Obstacle:
        """This box with `margin` of daylight around it, as a plain rectangle.

        What the router navigates by, as opposed to what it lands on. The shape
        is dropped deliberately: clearance is about the reader's eye, and a line
        four units from a diamond's sloped side looks as attached as one four
        units from a rectangle's.
        """
        return Obstacle(
            self.id,
            x=self.x - margin,
            y=self.y - margin,
            width=self.width + margin * 2,
            height=self.height + margin * 2,
        )

    def crosses(self, first: tuple[float, float], second: tuple[float, float]) -> bool:
        """Whether the segment passes through this box's interior.

        Touching counts as clear, in both senses that matter: a route may end on
        the border of the box it points at, and a route may run along the edge of
        one it passes.
        """
        left, right = sorted((first[0], second[0]))
        top, bottom = sorted((first[1], second[1]))
        return (
            left < self.right - _TOLERANCE
            and right > self.x + _TOLERANCE
            and top < self.bottom - _TOLERANCE
            and bottom > self.y + _TOLERANCE
        )


@dataclass(frozen=True)
class Connector:
    """What to route: two node ids, the semantic edge role, and any label.

    Deliberately not the document's `Edge`. Routing is downstream of the schema
    for the same reason layout is: it needs two ids and a role, and keeping it
    ignorant of everything else is what lets it be tested against hand-placed
    boxes rather than whole documents.
    """

    source: str
    target: str
    role: str = "flow"
    label: str = ""


@dataclass(frozen=True)
class Route:
    """One edge's finished geometry: an axis-aligned polyline, border to border."""

    source: str
    target: str
    role: str
    points: tuple[tuple[float, float], ...]
    label: str = ""

    @property
    def segments(self) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
        return tuple(zip(self.points, self.points[1:], strict=False))

    @property
    def length(self) -> float:
        return sum(math.dist(first, second) for first, second in self.segments)


@dataclass(frozen=True)
class Label:
    """One edge's label, placed: the text and the box it was measured into.

    The box is the point of this type. Every rule about a label is a rule about
    the space it takes — clear of its own line, clear of every other line, clear
    of every box and of every other label — so the box is what placement returns
    and what a test measures, and the drawn position is derived from it rather
    than the other way round.
    """

    text: str
    role: str
    left: float
    top: float
    width: float
    height: float
    ascent: float
    font: str = "sans"

    @property
    def box(self) -> tuple[float, float, float, float]:
        """Left, top, right, bottom."""
        return self.left, self.top, self.left + self.width, self.top + self.height

    @property
    def baseline(self) -> float:
        return self.top + self.ascent


def shaft_length(route: Route, theme: Theme) -> float:
    """The part of `route` that is line rather than head.

    An end treatment sits on the last `head_length` of the route, so a route as
    long as its own head is a head with nothing behind it. This is the number the
    minimum applies to, and it is why a bidirectional `exchange` needs more room
    than a one-way `flow` between the same two boxes.
    """
    role = theme.role_for(route.role)
    ends = 0
    if getattr(role, "head", "none") != "none":
        ends += 1
    if getattr(role, "tail", "none") != "none":
        ends += 1
    return route.length - theme.head_length_for(route.role) * ends


def minimum_rank_gap(theme: Theme) -> float:
    """The separation two ranks need for any edge role to keep its shaft.

    Published here because this is the stage that enforces it: whoever builds the
    layout's `Spacing` floors `rank_gap` at this, and then a straight route
    between adjacent ranks is legal by construction. Both ends are counted, so a
    two-headed role fits in the same gap as a one-headed one.
    """
    return theme.edge.min_shaft_length + 2 * theme.widest_head


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


def _round(value: float) -> float:
    return round(value, GRID_PRECISION)


def _port(box: Obstacle, side: str, fraction: float) -> tuple[float, float]:
    """A point on `side` of `box`'s rectangle, `fraction` of the way along it.

    Where the route *leaves* from, which is not always where it *lands*: see
    `_anchor`. This is the point everything about clearance and grid lanes is
    measured from, because the rectangle is what the route has to get around.
    """
    if side in ("top", "bottom"):
        y = box.y if side == "top" else box.bottom
        return _round(box.x + box.width * fraction), _round(y)
    x = box.x if side == "left" else box.right
    return _round(x), _round(box.y + box.height * fraction)


def _anchor(box: Obstacle, side: str, fraction: float) -> tuple[float, float]:
    """Where the route touches the *shape* — the endpoint the reader sees.

    Straight in from the rectangle's port until it meets the outline, which for a
    rectangle is no distance at all and for a diamond can be a good fraction of
    the box. An arrow that stopped on the rectangle would end in the empty corner
    beside the diamond, pointing at nothing: the most literal version of the
    'line does not reach its box' failure, and the one no amount of tolerance
    would catch, because the line is exactly where it meant to be.
    """
    x, y = _port(box, side, fraction)
    centre_x, centre_y = box.centre
    half_width, half_height = box.width / 2, box.height / 2
    if box.shape not in ("diamond", "ellipse", "pill") or not half_width or not half_height:
        return x, y

    if box.shape == "pill":
        # Flat between the caps, circular at them: the cap's radius is half the
        # height, so a port on the end of a pill is on a circle, not an ellipse.
        radius = min(half_height, half_width)
        if side in ("top", "bottom"):
            return _round(min(max(x, box.x + radius), box.right - radius)), _round(y)
        offset = math.sqrt(max(radius**2 - (y - centre_y) ** 2, 0.0))
        centre_of_cap = box.x + radius if side == "left" else box.right - radius
        step = -1.0 if side == "left" else 1.0
        return _round(centre_of_cap + step * offset), _round(y)

    if side in ("top", "bottom"):
        across = abs(x - centre_x) / half_width
        depth = (1.0 - across) if box.shape == "diamond" else math.sqrt(max(1 - across**2, 0.0))
        step = -1.0 if side == "top" else 1.0
        return _round(x), _round(centre_y + step * half_height * depth)

    across = abs(y - centre_y) / half_height
    depth = (1.0 - across) if box.shape == "diamond" else math.sqrt(max(1 - across**2, 0.0))
    step = -1.0 if side == "left" else 1.0
    return _round(centre_x + step * half_width * depth), _round(y)


def _spread(index: int, count: int) -> float:
    """Where the `index`th of `count` ports sits along its side, as a fraction.

    Centred when there is one, evenly spaced across the middle of the side when
    there are several — so two arrows leaving the same box leave from two visibly
    different places instead of overlapping into one thick line.
    """
    return 0.5 + PORT_SPREAD * ((index + 1) / (count + 1) - 0.5)


def _candidate_sides(source: Obstacle, target: Obstacle, direction: str) -> tuple[str, str]:
    """The sides a route between these two boxes should use, given the flow.

    Analytic rather than searched: which way an arrow leaves a box is a reading
    decision — down the page in a `down` diagram, across it in a `right` one —
    and searching for it would make the same document draw differently as its
    text changed length.
    """
    below = target.centre[1] >= source.centre[1]
    beside = target.centre[0] >= source.centre[0]
    vertical = ("bottom", "top") if below else ("top", "bottom")
    horizontal = ("right", "left") if beside else ("left", "right")

    separated_vertically = target.y >= source.bottom - _TOLERANCE or (
        target.bottom <= source.y + _TOLERANCE
    )
    separated_horizontally = target.x >= source.right - _TOLERANCE or (
        target.right <= source.x + _TOLERANCE
    )
    if direction == "right":
        return horizontal if separated_horizontally or not separated_vertically else vertical
    return vertical if separated_vertically or not separated_horizontally else horizontal


def _fallback_sides(primary: tuple[str, str]) -> tuple[str, str]:
    """The other axis, for when the preferred approach cannot be routed."""
    return ("right", "left") if primary[0] in ("top", "bottom") else ("bottom", "top")


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------


@dataclass
class _Grid:
    """The Hanan grid of the obstacle set, with blocked steps already removed.

    Built once per drawing rather than once per edge: the obstacles are the same
    for every route, and the legality of a step is a property of the obstacles.
    """

    xs: tuple[float, ...]
    ys: tuple[float, ...]
    horizontal: list[list[bool]] = field(default_factory=list)
    """`horizontal[j][i]`: the step from `xs[i]` to `xs[i + 1]` along `ys[j]`."""

    vertical: list[list[bool]] = field(default_factory=list)
    """`vertical[i][j]`: the step from `ys[j]` to `ys[j + 1]` along `xs[i]`."""

    def __post_init__(self) -> None:
        self._x_at = {value: index for index, value in enumerate(self.xs)}
        self._y_at = {value: index for index, value in enumerate(self.ys)}
        self.horizontal = [[True] * max(len(self.xs) - 1, 0) for _ in self.ys]
        self.vertical = [[True] * max(len(self.ys) - 1, 0) for _ in self.xs]

    def block(self, obstacles: Sequence[Obstacle]) -> None:
        """Remove every step that would pass through a box's interior."""
        for box in obstacles:
            rows = range(
                bisect_right(self.ys, box.y + _TOLERANCE),
                bisect_left(self.ys, box.bottom - _TOLERANCE),
            )
            columns = range(
                max(bisect_right(self.xs, box.x + _TOLERANCE) - 1, 0),
                min(bisect_left(self.xs, box.right - _TOLERANCE), len(self.xs) - 1),
            )
            for row in rows:
                for column in columns:
                    self.horizontal[row][column] = False

            inner_columns = range(
                bisect_right(self.xs, box.x + _TOLERANCE),
                bisect_left(self.xs, box.right - _TOLERANCE),
            )
            inner_rows = range(
                max(bisect_right(self.ys, box.y + _TOLERANCE) - 1, 0),
                min(bisect_left(self.ys, box.bottom - _TOLERANCE), len(self.ys) - 1),
            )
            for column in inner_columns:
                for row in inner_rows:
                    self.vertical[column][row] = False

    def locate(self, point: tuple[float, float]) -> tuple[int, int] | None:
        column = self._x_at.get(point[0])
        row = self._y_at.get(point[1])
        return None if column is None or row is None else (column, row)

    def shortest(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
        entry: int,
        exit_: int,
    ) -> tuple[tuple[float, float], ...] | None:
        """The cheapest orthogonal path from `start` to `goal`, or `None`.

        `entry` is the direction the route is already travelling when it arrives
        at `start` — the stub leaving the source border — and `exit_` the one it
        must be travelling to enter the target. Both are charged as turns, so a
        path that arrives sideways at the target pays for the corner it will need.
        """
        first = self.locate(start)
        last = self.locate(goal)
        if first is None or last is None:
            return None
        if first == last:
            return (start,)

        best: dict[tuple[int, int, int], float] = {(*first, entry): 0.0}
        previous: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        queue: list[tuple[float, int, int, int]] = [(0.0, first[0], first[1], entry)]
        goal_cost = math.inf
        goal_state: tuple[int, int, int] | None = None

        while queue:
            cost, column, row, heading = heapq.heappop(queue)
            if cost >= goal_cost:
                break
            state = (column, row, heading)
            if cost > best.get(state, math.inf):
                continue
            if (column, row) == last:
                total = cost + (0.0 if heading == exit_ else TURN_COST)
                if total < goal_cost:
                    goal_cost, goal_state = total, state
                continue
            for move, (step_x, step_y) in enumerate(_MOVES):
                next_column, next_row = column + step_x, row + step_y
                if not self._passable(column, row, move):
                    continue
                distance = (
                    abs(self.xs[next_column] - self.xs[column])
                    if step_x
                    else abs(self.ys[next_row] - self.ys[row])
                )
                candidate = cost + distance + (0.0 if move == heading else TURN_COST)
                next_state = (next_column, next_row, move)
                if candidate < best.get(next_state, math.inf):
                    best[next_state] = candidate
                    previous[next_state] = state
                    heapq.heappush(queue, (candidate, next_column, next_row, move))

        if goal_state is None:
            return None
        walk = [goal_state]
        while walk[-1] in previous:
            walk.append(previous[walk[-1]])
        return tuple((self.xs[column], self.ys[row]) for column, row, _ in reversed(walk))

    def _passable(self, column: int, row: int, move: int) -> bool:
        step_x, step_y = _MOVES[move]
        if step_x > 0:
            return column + 1 < len(self.xs) and self.horizontal[row][column]
        if step_x < 0:
            return column > 0 and self.horizontal[row][column - 1]
        if step_y > 0:
            return row + 1 < len(self.ys) and self.vertical[column][row]
        return row > 0 and self.vertical[column][row - 1]


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def route_edges(
    connectors: Sequence[Connector],
    obstacles: Sequence[Obstacle],
    theme: Theme,
    *,
    direction: str = "down",
) -> tuple[Route, ...]:
    """Route every connector around every obstacle, in the order given.

    Raises:
        LayoutError: a connector names a box that is not there, two boxes share
            an id, or some edge has no orthogonal route that both misses every
            box and keeps a visible shaft. The last one is a statement about the
            arrangement rather than about the router — see `minimum_rank_gap`.
    """
    boxes: dict[str, Obstacle] = {}
    for box in obstacles:
        if box.id in boxes:
            raise LayoutError(f"two boxes share the id {box.id!r}")
        boxes[box.id] = box
    for connector in connectors:
        for end, identifier in (("source", connector.source), ("target", connector.target)):
            if identifier not in boxes:
                raise LayoutError(
                    f"edge {end} {identifier!r} goes nowhere: there is no box with that id"
                )

    # Only the lanes *outside* the outermost boxes are set by this — every other
    # lane runs down the middle of a real gap. A lane one head length off the
    # edge of the drawing is a legal place for a back edge to run, and it hugs
    # the box it passes: there is open paper on the other side of it and no
    # reason to be that close.
    channel = theme.edge.lane_spacing
    usable = _usable_gap(theme)
    lanes = (
        _lanes([value for box in obstacles for value in (box.x, box.right)], channel, usable),
        _lanes([value for box in obstacles for value in (box.y, box.bottom)], channel, usable),
    )

    straight = {
        index
        for index, connector in enumerate(connectors)
        if connector.source != connector.target
        and theme.edge_roles[connector.role].routing == "direct"
    }
    sides = {
        index: _candidate_sides(boxes[connector.source], boxes[connector.target], direction)
        for index, connector in enumerate(connectors)
        if connector.source != connector.target and index not in straight
    }
    fractions = _assign_ports(connectors, boxes, sides)
    approaches: dict[int, tuple[_Approach, _Approach]] = {}
    for index, side_pair in sides.items():
        connector = connectors[index]
        source, target = boxes[connector.source], boxes[connector.target]
        approaches[index] = (
            _approach(source, target, side_pair, fractions[index], obstacles, lanes, theme),
            _approach(
                source, target, _fallback_sides(side_pair), (0.5, 0.5), obstacles, lanes, theme
            ),
        )
    grid = _build_grid(approaches, obstacles, lanes, theme.edge.clearance)

    routes: list[Route] = []
    for index, connector in enumerate(connectors):
        if connector.source == connector.target:
            routes.append(_self_loop(connector, boxes[connector.source], obstacles, theme))
            continue
        if index in straight:
            routes.append(
                Route(
                    source=connector.source,
                    target=connector.target,
                    role=connector.role,
                    points=_chord(boxes[connector.source], boxes[connector.target]),
                    label=connector.label,
                )
            )
            continue
        points = _route_one(connector, approaches[index], grid, obstacles, theme)
        routes.append(
            Route(
                source=connector.source,
                target=connector.target,
                role=connector.role,
                points=points,
                label=connector.label,
            )
        )
    return separate_lanes(tuple(routes), obstacles, theme)


def _chord(source: Obstacle, target: Obstacle) -> tuple[tuple[float, float], ...]:
    """The straight line between two shapes' outlines, along their centres.

    A mesh drawn straight is meant to cross itself, so this is deliberately not
    routed: nothing here avoids an obstacle, and the two points are simply where
    the centre-to-centre line leaves one shape and enters the other. That is the
    whole of `routing = "direct"`, and it is why the setting belongs to a role
    rather than to a theme — a `flow` routed this way would be a diagram of
    diagonals with nothing to say for them.

    Where the line meets each outline is found by bisection rather than by four
    cases per shape: `Obstacle` already answers *is this point inside me*
    exactly, for all four shapes, and asking it thirty times settles the crossing
    far below a rendered pixel. A fixed count is what keeps the same document
    rendering to the same bytes twice.
    """
    start, end = source.centre, target.centre
    return (_leaving(source, start, end), _leaving(target, end, start))


#: Halvings used to find where a direct route crosses a box's outline. Thirty
#: takes a canvas-sized interval to about a millionth of a unit.
_CHORD_BISECTIONS: Final = 30


def _leaving(
    box: Obstacle, inside: tuple[float, float], outside: tuple[float, float]
) -> tuple[float, float]:
    """The point on `box`'s outline along the segment from `inside` to `outside`."""

    def at(position: float) -> tuple[float, float]:
        return (
            inside[0] + (outside[0] - inside[0]) * position,
            inside[1] + (outside[1] - inside[1]) * position,
        )

    def within(point: tuple[float, float]) -> bool:
        # A degenerate rectangle around the point: `overlaps` is the exact
        # inside test every shape already carries, and a zero-width box is the
        # way to ask it about a point.
        return box.overlaps((point[0], point[1], point[0], point[1]))

    if not within(at(0.0)):
        return _round(inside[0]), _round(inside[1])
    low, high = 0.0, 1.0
    for _ in range(_CHORD_BISECTIONS):
        middle = (low + high) / 2
        if within(at(middle)):
            low = middle
        else:
            high = middle
    point = at(high)
    return _round(point[0]), _round(point[1])


def _assign_ports(
    connectors: Sequence[Connector],
    boxes: Mapping[str, Obstacle],
    sides: Mapping[int, tuple[str, str]],
) -> dict[int, tuple[float, float]]:
    """Where along its side each end of each connector sits, as a fraction.

    Ordered by where the other end of the edge is, so the arrows leaving a box
    keep the same left-to-right order as the boxes they point at and cross each
    other as little as the sides allow.
    """
    users: dict[tuple[str, str], list[int]] = {}
    for index, (source_side, target_side) in sides.items():
        users.setdefault((connectors[index].source, source_side), []).append(index)
        users.setdefault((connectors[index].target, target_side), []).append(index)

    fractions: dict[tuple[int, str], float] = {}
    for (node, side), indices in users.items():
        along = 0 if side in ("top", "bottom") else 1

        def key(index: int, node: str = node, along: int = along) -> tuple[float, int]:
            connector = connectors[index]
            other = connector.target if connector.source == node else connector.source
            return boxes[other].centre[along], index

        for position, index in enumerate(sorted(indices, key=key)):
            fractions[(index, f"{node}:{side}")] = _spread(position, len(indices))

    assigned: dict[int, tuple[float, float]] = {}
    for index, (source_side, target_side) in sides.items():
        connector = connectors[index]
        assigned[index] = (
            fractions[(index, f"{connector.source}:{source_side}")],
            fractions[(index, f"{connector.target}:{target_side}")],
        )
    return assigned


def _stub_end(port: tuple[float, float], side: str, stub: float) -> tuple[float, float]:
    """`stub` units straight out from the border, so the route leaves squarely."""
    step_x, step_y = OUTWARD[side]
    return _round(port[0] + step_x * stub), _round(port[1] + step_y * stub)


def _clearance(point: tuple[float, float], side: str, obstacles: Sequence[Obstacle]) -> float:
    """How far a route can travel straight out of `point` before it hits a box.

    The port's own box is never in front of it — the outward direction points
    away from it — so this is the room between this border and the next thing
    along, and infinite when there is nothing along.
    """
    step_x, step_y = OUTWARD[side]
    nearest = math.inf
    for box in obstacles:
        if step_x:
            if not box.y + _TOLERANCE < point[1] < box.bottom - _TOLERANCE:
                continue
            distance = ((box.x if step_x > 0 else box.right) - point[0]) * step_x
        else:
            if not box.x + _TOLERANCE < point[0] < box.right - _TOLERANCE:
                continue
            distance = ((box.y if step_y > 0 else box.bottom) - point[1]) * step_y
        if distance > _TOLERANCE:
            nearest = min(nearest, distance)
    return nearest


@dataclass(frozen=True)
class _Approach:
    """One way of joining two boxes: which sides, which ports, which stub ends.

    The stub is what makes a route leave and arrive square to the border rather
    than sliding along it, and it is clamped to the room actually in front of the
    port. Clamping rather than giving up matters: two boxes four units apart
    still get their straight route, and it is then refused for being too short —
    which is the truth about the arrangement. A stub that simply failed would
    send the router around the houses to join two boxes that are nearly touching.
    """

    source: str
    target: str
    source_side: str
    target_side: str
    source_anchor: tuple[float, float]
    target_anchor: tuple[float, float]
    source_stub: tuple[float, float]
    target_stub: tuple[float, float]

    def coordinates(self) -> tuple[tuple[float, float], ...]:
        return (self.source_anchor, self.source_stub, self.target_stub, self.target_anchor)


def _approach(
    source: Obstacle,
    target: Obstacle,
    sides: tuple[str, str],
    fractions: tuple[float, float],
    obstacles: Sequence[Obstacle],
    lanes: tuple[set[float], set[float]],
    theme: Theme,
) -> _Approach:
    """Anchors on the shapes, stub ends out on the channel lane.

    Two decisions are visible here. The stub is measured from the *rectangle*
    rather than from the anchor, so a diamond's stub still ends outside the box:
    the grid is built on rectangles, and a turning point in the empty corner
    beside a diamond is a point the grid has already declared unreachable.

    And the stub runs all the way to the first lane in front of the port, rather
    than a token distance. That is what keeps a route's sideways travel in the
    middle of the channel: if the stub stopped short, the row it stopped on would
    be a legal place to turn, and a route turning there runs the width of the
    target box just above its border, which reads as an underline rather than as
    an arrow arriving.
    """
    source_side, target_side = sides
    source_fraction, target_fraction = fractions
    source_port = _port(source, source_side, source_fraction)
    target_port = _port(target, target_side, target_fraction)
    return _Approach(
        source=source.id,
        target=target.id,
        source_side=source_side,
        target_side=target_side,
        source_anchor=_anchor(source, source_side, source_fraction),
        target_anchor=_anchor(target, target_side, target_fraction),
        source_stub=_stub_end(
            source_port, source_side, _reach(source_port, source_side, obstacles, lanes, theme)
        ),
        target_stub=_stub_end(
            target_port, target_side, _reach(target_port, target_side, obstacles, lanes, theme)
        ),
    )


def _reach(
    port: tuple[float, float],
    side: str,
    obstacles: Sequence[Obstacle],
    lanes: tuple[set[float], set[float]],
    theme: Theme,
) -> float:
    """How far out of `port` the stub goes: to the first lane, or to half the room.

    Half the room is the fallback for a port whose lane is behind something —
    the lanes are global to the drawing, so the one in front of this box may be
    on the far side of a box that is only in *this* port's way.

    Floored at the head's own length plus its clearance, and that floor is the
    fix for the worst-looking arrow drawspec drew: the first lane in front of a
    port can be a unit and a half away — a mid-gap lane belonging to two *other*
    boxes that happen to line up near this border — and a route that turns there
    puts a six-unit head on a two-unit approach. The head then starts behind the
    corner and reads as a blot on the corner rather than as an arrow arriving.
    The floor cannot manufacture room that is not there: it never exceeds the
    space in front of the port, and a route that ends up too short for a shaft is
    refused a few lines later, which is the honest answer to boxes that close.
    """
    step_x, step_y = OUTWARD[side]
    axis = lanes[0] if step_x else lanes[1]
    origin = port[0] if step_x else port[1]
    step = step_x or step_y
    ahead = [(value - origin) * step for value in axis if (value - origin) * step > _TOLERANCE]
    room = _clearance(port, side, obstacles) / 2
    return min(max(min(ahead, default=room), min(head_room(theme), room)), room)


def head_room(theme: Theme) -> float:
    """The straight run an end treatment needs before the route may turn.

    A head is drawn on the last `head_length` of the route, so a turn that close
    to the border leaves it nothing to sit on. The clearance on top is what keeps
    the corner visibly *behind* the head rather than touching it.
    """
    return theme.widest_head + theme.edge.clearance


def _usable_gap(theme: Theme) -> float:
    """The narrowest gap between two box edges that is worth a lane down it.

    A lane in a narrower gap is a legal place to turn that no route should want:
    both boxes are within a clearance of it, so a route using it runs flush along
    a border. Dropping those lanes is what makes the mid-gap rule mean something
    — otherwise the grid offers the tidy lane *and* a handful of degenerate ones
    beside it, and the search, which cannot see, takes whichever is a unit
    shorter.
    """
    return theme.edge.clearance * 2


def _lanes(edges: Sequence[float], channel: float, usable: float) -> set[float]:
    """One lane between each pair of adjacent box edges, and one outside each end.

    Gaps narrower than `usable` get no lane: see `_usable_gap`. The lane between
    a box's own two edges lands inside it and is never usable, which costs a grid
    line and saves a special case.
    """
    if not edges:
        return set()
    ordered = sorted({_round(value) for value in edges})
    bounded = [ordered[0] - channel * 2, *ordered, ordered[-1] + channel * 2]
    return {
        _round((first + second) / 2)
        for first, second in pairwise(bounded)
        if second - first >= usable - _TOLERANCE
    }


def _build_grid(
    approaches: Mapping[int, tuple[_Approach, _Approach]],
    obstacles: Sequence[Obstacle],
    lanes: tuple[set[float], set[float]],
    clearance: float,
) -> _Grid:
    """The coordinates a route is allowed to turn on.

    A lane runs down the **middle** of every gap between box edges, rather than a
    fixed distance from each box. The difference is the whole look of the result:
    a lane six units below a box gives a legal route that runs the width of the
    box just under its border and reads as an underline, while the same route on
    the mid-gap lane reads as a connection passing between two ranks. Both are
    the same length with the same number of corners, so the search cannot tell
    them apart — the grid has to be the one that knows.

    Plus every port and stub end of every approach, because a route has to be
    able to start and finish on one. That is the whole grid — the router does not
    get a lane per box per side, which is what keeps the search small enough to
    run once per edge without anyone noticing.

    The boxes are grown by `clearance` before they block, and that is what stops
    a route running flush along a border. Every port is a grid line, and a port
    sits *on* a border, so the border's own coordinate is always available to
    travel down — free, straight, and indistinguishable to the search from the
    lane beside it. Growing the obstacles is what makes the difference visible to
    the only thing that can act on it. The lines themselves stay: a route still
    starts and ends on a border, because the stubs are not part of the search.
    """
    xs, ys = set(lanes[0]), set(lanes[1])
    for pair in approaches.values():
        for approach in pair:
            for point in approach.coordinates():
                xs.add(point[0])
                ys.add(point[1])

    grid = _Grid(xs=tuple(sorted(xs)), ys=tuple(sorted(ys)))
    grid.block([box.grown(clearance) for box in obstacles])
    return grid


def _route_one(
    connector: Connector,
    approaches: tuple[_Approach, _Approach],
    grid: _Grid,
    obstacles: Sequence[Obstacle],
    theme: Theme,
) -> tuple[tuple[float, float], ...]:
    """The preferred approach, then the other axis, then a refusal."""
    # The first approach that can be drawn at all decides whether there is room:
    # a *blocked* approach means try the other axis, but a *short* one means the
    # boxes are too close, and going the long way round to make the number up
    # would draw an arrow that wraps around the diagram to reach the box below it.
    for approach in approaches:
        points = _attempt(approach, grid, obstacles)
        if points is None:
            continue
        route = Route(connector.source, connector.target, connector.role, points, connector.label)
        if shaft_length(route, theme) < theme.edge.min_shaft_length - _TOLERANCE:
            raise LayoutError(
                f"the route from {connector.source!r} to {connector.target!r} has no room for a "
                f"shaft of {theme.edge.min_shaft_length:g}: the boxes are closer than "
                f"{minimum_rank_gap(theme):g} apart, so the layout needs more separation or the "
                f"other direction"
            )
        _check_head_room(route, theme)
        return points

    raise LayoutError(
        f"no orthogonal route from {connector.source!r} to {connector.target!r} that misses "
        f"every box; the arrangement needs more room between them"
    )


def _check_head_room(route: Route, theme: Theme) -> None:
    """The end treatments have a straight run to sit on, or this is not a route.

    Total shaft length is not enough, and the difference is a real drawing: a
    route can be two hundred units long and still turn a unit and a half before
    it arrives, which puts the head across the corner with its point on the
    border and its back sticking out sideways. It reads as a smudge at the
    corner. So the check is on the *segment the head is drawn along*, and it is a
    refusal rather than a repair, because the remedy is more room between the
    boxes and this stage cannot make any.

    Raises:
        LayoutError: an end treatment's own segment is shorter than the head.
    """
    role = theme.role_for(route.role)
    segments = route.segments
    if not segments:
        return
    ends = []
    if getattr(role, "head", "none") != "none":
        ends.append(("head", segments[-1]))
    if getattr(role, "tail", "none") != "none":
        ends.append(("tail", segments[0]))
    needed = theme.head_length_for(route.role)
    for end, (first, second) in ends:
        if math.dist(first, second) < needed - _TOLERANCE:
            raise LayoutError(
                f"the {end} of the edge from {route.source!r} to {route.target!r} has "
                f"{math.dist(first, second):.1f} of straight line to sit on and needs "
                f"{needed:g}: the route turns a corner just before it "
                f"arrives, so the arrow would be drawn across the corner. The boxes need "
                f"more room between them, or the layout needs the other direction."
            )


def separate_lanes(
    routes: Sequence[Route], obstacles: Sequence[Obstacle], theme: Theme
) -> tuple[Route, ...]:
    """Move routes that share a lane apart, so each keeps its own line.

    The router costs a route by length and corners, and two edges crossing the
    same gap have the same cheapest answer — so they get it, exactly, and are
    drawn one on top of the other. Three arrows out of one box then leave as a
    single thick line that splits at the end, and where a fourth crosses them
    every corner lands on the same coordinate, so a reader cannot tell which line
    turned and which carried on. It is the one failure the search cannot see:
    both routes are individually perfect, and only the pair is wrong.

    So it is settled after the fact, and only for segments that are free to move
    — a run between two corners, never one carrying an endpoint, because an
    endpoint is on a border and that is the invariant this whole module exists
    for. Each shifted route is re-checked against every box and reverted if the
    new line is worse than the shared one; a lane too narrow to share simply
    stays shared, which is what it looked like before.
    """
    spacing = theme.edge.lane_spacing
    moved = tuple(routes)
    for _ in range(SEPARATION_PASSES):
        groups = _shared_runs(moved, spacing)
        if not groups:
            break
        moved = _separated(moved, groups, obstacles, theme, spacing)
    return moved


def _separated(
    routes: tuple[Route, ...],
    groups: Sequence[tuple[list[_Run], float | None]],
    obstacles: Sequence[Obstacle],
    theme: Theme,
    spacing: float,
) -> tuple[Route, ...]:
    """One pass of the separation. Repeated, because moving a run moves corners.

    A route is a chain: shifting the horizontal run in the middle of it lengthens
    the vertical runs at both ends, and a vertical run that grows can arrive
    alongside one belonging to another route that was clear of it before. So the
    pass runs again on its own output, and the second pass sees the overlap the
    first one made. It converges quickly because each pass only touches runs that
    are on top of something.
    """
    moved = list(routes)
    for group, anchor in groups:
        for target, run in zip(_targets(group, anchor, spacing), group, strict=True):
            for candidate_offset in _tries(target - run.line):
                candidate = _shifted(moved[run.index], run.segment, candidate_offset)
                if candidate is not None and _is_clear(candidate, obstacles, theme):
                    moved[run.index] = candidate
                    break
    return tuple(moved)


def _tries(offset: float) -> tuple[float, ...]:
    """The offsets to attempt, in order, for one run that has to move.

    The other side of the line, then twice as far, because "six units left" is a
    preference and the boxes are the constraint: a back edge running up the side
    of a diagram has a whole rank on one side of it and open paper on the other,
    and refusing to look at the open side leaves it exactly where it was.
    """
    if abs(offset) < _TOLERANCE:
        return ()
    return (offset, -offset, offset * 2, -offset * 2)


def _targets(group: Sequence[_Run], anchor: float | None, spacing: float) -> list[float]:
    """Where to put the runs of one band — as coordinates, not as nudges.

    Coordinates, because a band is not a line: its runs start at three different
    places, so nudging each by the same ladder of offsets preserves exactly the
    unevenness it is meant to remove. Spreading them about a middle is the
    answer, and it reduces to the old behaviour when they did all start on one
    line.

    Which middle depends on what is holding the band. With every run free, it is
    the band's own centre, so the group stays where the router put it. With one
    *pinned* — a run carrying an endpoint, which cannot move without taking the
    endpoint off its border — the middle is the pinned run's line and the rest
    step outwards around it in alternating directions rather than sliding
    through it. Taking the free runs' own centre instead is how a route ended up
    moved onto the endpoint it was supposed to be avoiding.
    """
    count = len(group)
    if anchor is None:
        middle = sum(run.line for run in group) / count
        return [middle + (position - (count - 1) / 2) * spacing for position in range(count)]

    steps = [(position // 2 + 1) * (1 if position % 2 == 0 else -1) for position in range(count)]
    return [anchor + step * spacing for step in steps]


@dataclass(frozen=True)
class _Run:
    """One straight run of one route, as the separation pass sees it."""

    index: int
    """Which route in the batch."""

    segment: int
    low: float
    high: float
    """The stretch it covers along its own direction."""

    movable: bool
    """False for a run carrying an endpoint: moving it takes the point off its border."""

    line: float
    """The coordinate across its direction — the lane it is drawn in."""

    approach: float
    """Where the route sits across the band, on either side of this run.

    The mean of the two corners the run turns at — measured across its own
    direction, so a horizontal run reports the two heights its route came from
    and goes on to. This is the field that decides *which* lane a run gets when
    a band is prised apart, and it exists because `line` cannot decide it: the
    band that most needs separating is the one where every run is on the exact
    same line, and there `line` is a tie for all of them. Sorting a tie is
    sorting nothing, so the lanes went out in the order the edges happened to be
    written in — and two routes whose order was thereby swapped are two routes
    that cross. A run whose route arrives from above and leaves above belongs in
    the upper lane, whatever the document said first.
    """


def _shared_runs(routes: Sequence[Route], spacing: float) -> list[tuple[list[_Run], float | None]]:
    """Segments drawn alongside one another, grouped, and whether one is pinned.

    Every straight run of every route is counted, but only those with a corner at
    each end can be moved: shifting one that carries an anchor would take the
    anchor off the border with it. So a run at the end of a route still *takes
    part* in the group — the others have to get out of its way — and the group
    reports it as pinned rather than dropping it, which is the case where a back
    edge runs up the line another edge arrives on.

    Grouped by *overlapping run*, not by the lane they happen to share — which is
    the difference between separating two lines and rearranging a whole gap. A
    rank gap holds one lane and every edge crossing it uses that lane, but two
    edges on the same lane at opposite ends of the diagram are not drawn on top
    of each other, and moving them spends the room the ones that are need: seven
    edges spread across a twenty-unit gap have three units each, while the two
    stretches that actually overlap get six each and everything else stays put.

    "Alongside" rather than "on top of": two runs `spacing` apart are already two
    lines a reader has to tell apart, and the old exact-coordinate test could not
    see them — see `_lanes`.
    """
    runs: dict[str, list[_Run]] = {"v": [], "h": []}
    for index, route in enumerate(routes):
        for segment, (first, second) in enumerate(route.segments):
            movable = 0 < segment < len(route.segments) - 1
            if abs(first[0] - second[0]) < _TOLERANCE:
                orientation, line = "v", first[0]
                span = sorted((first[1], second[1]))
            elif abs(first[1] - second[1]) < _TOLERANCE:
                orientation, line = "h", first[1]
                span = sorted((first[0], second[0]))
            else:
                continue
            across = 1 if orientation == "h" else 0
            corners = [
                route.points[position][across]
                for position in (segment - 1, segment + 2)
                if 0 <= position < len(route.points)
            ]
            approach = sum(corners) / len(corners) if corners else line
            runs[orientation].append(
                _Run(index, segment, span[0], span[1], movable, line, approach)
            )

    groups: list[tuple[list[_Run], float | None]] = []
    for entries in runs.values():
        for lane in _bands(sorted(entries, key=lambda run: run.line), spacing):
            for component in _overlapping(sorted(lane, key=lambda run: (run.low, run.high))):
                free_runs = [run for run in component if run.movable]
                held = [run.line for run in component if not run.movable]
                if len({run.index for run in component}) > 1 and free_runs:
                    anchor = sum(held) / len(held) if held else None
                    # Ordered by where each route is going, then by where it
                    # currently is. `approach` first is what keeps the lanes in
                    # the routes' own order; `line` breaks the remaining ties so
                    # a band the router already spread stays spread the way it
                    # was, and the whole key is a total order rather than a
                    # stable-sort accident.
                    groups.append(
                        (sorted(free_runs, key=lambda run: (run.approach, run.line)), anchor)
                    )
    return groups


def _bands(entries: Sequence[_Run], spacing: float) -> Iterator[list[_Run]]:
    """Runs close enough together to be worth prising apart, grouped.

    Not "on the same line" — that was the old test, and it is too strict by
    exactly the amount that matters. Three edges leaving one box turn at three
    *different* coordinates four and eight units apart, so nothing was ever on
    top of anything and the separation pass had no work to do; the fan was drawn
    as a bundle a reader cannot follow. Within a lane spacing of each other is
    the same question asked at the scale a reader answers it.
    """
    lane: list[_Run] = []
    for entry in entries:
        if lane and entry.line - lane[-1].line > spacing:
            yield lane
            lane = []
        lane.append(entry)
    if lane:
        yield lane


def _overlapping(entries: Sequence[_Run]) -> Iterator[list[_Run]]:
    """Runs in one lane split into stretches that actually run alongside each other.

    A sweep along the lane: a run that starts after everything before it has
    ended begins a new group, because nothing behind it is in its way. Two edges
    using the same rank gap at opposite ends of the diagram are not drawn on top
    of each other, and moving them spends the room the ones that are need.
    """
    group: list[_Run] = []
    reach = -math.inf
    for entry in entries:
        if group and entry.low > reach - _TOLERANCE:
            yield group
            group = []
        group.append(entry)
        reach = max(reach, entry.high)
    if group:
        yield group


def _shifted(route: Route, segment: int, offset: float) -> Route | None:
    """`route` with one segment moved sideways by `offset`, or None if it degenerates.

    The two points the segment owns move; the segments either side of it stretch
    to meet them. When that leaves an endpoint's own segment with nothing left,
    the shift has eaten the square approach to a border, and there is no version
    of this route worth having — so it is refused rather than trimmed.
    """
    points = list(route.points)
    first, second = points[segment], points[segment + 1]
    vertical = abs(first[0] - second[0]) < _TOLERANCE
    if vertical:
        points[segment] = (_round(first[0] + offset), first[1])
        points[segment + 1] = (_round(second[0] + offset), second[1])
    else:
        points[segment] = (first[0], _round(first[1] + offset))
        points[segment + 1] = (second[0], _round(second[1] + offset))
    if any(
        math.dist(one, two) <= _TOLERANCE
        for one, two in (
            (points[0], points[1]),
            (points[-2], points[-1]),
        )
    ):
        return None
    return replace(route, points=tuple(points))


def _is_clear(route: Route, obstacles: Sequence[Obstacle], theme: Theme) -> bool:
    """Whether this route keeps its clearance and its head room after a shift."""
    grown = [
        box.grown(theme.edge.clearance)
        for box in obstacles
        if box.id not in (route.source, route.target)
    ]
    if any(box.crosses(first, second) for first, second in route.segments for box in grown):
        return False
    try:
        _check_head_room(route, theme)
    except LayoutError:
        return False
    return shaft_length(route, theme) >= theme.edge.min_shaft_length - _TOLERANCE


def _attempt(
    approach: _Approach, grid: _Grid, obstacles: Sequence[Obstacle]
) -> tuple[tuple[float, float], ...] | None:
    """One pair of sides: stub out, search, stub in — or `None` if it cannot.

    The two stubs are checked against every box *except* the ones they belong to.
    That exception is what shaped anchors need: a diamond's stub starts on the
    sloped edge and crosses its own bounding rectangle to get out, through the
    corner the diamond does not occupy.
    """
    stubs = (
        (approach.source_anchor, approach.source_stub),
        (approach.target_stub, approach.target_anchor),
    )
    ends = (approach.source, approach.target)
    for first, second in stubs:
        if any(box.crosses(first, second) for box in obstacles if box.id not in ends):
            return None

    middle = grid.shortest(
        approach.source_stub,
        approach.target_stub,
        _move_of(OUTWARD[approach.source_side]),
        _move_of(_inward(approach.target_side)),
    )
    if middle is None:
        return None
    return _simplify((approach.source_anchor, *middle, approach.target_anchor))


def _inward(side: str) -> tuple[float, float]:
    step_x, step_y = OUTWARD[side]
    return -step_x, -step_y


def _move_of(step: tuple[float, float]) -> int:
    """Which of the search's four moves this unit vector is."""
    return _MOVES.index((int(step[0]), int(step[1])))


def _simplify(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """Drop repeated and collinear points, so a bend in the output is a real one."""
    kept: list[tuple[float, float]] = []
    for point in points:
        if kept and point == kept[-1]:
            continue
        if len(kept) >= 2:
            first, second = kept[-2], kept[-1]
            straight_x = first[0] == second[0] == point[0]
            straight_y = first[1] == second[1] == point[1]
            if straight_x or straight_y:
                kept[-1] = point
                continue
        kept.append(point)
    return tuple(kept)


def _self_loop(
    connector: Connector, box: Obstacle, obstacles: Sequence[Obstacle], theme: Theme
) -> Route:
    """A loop back to the same box: out of one side, around, in through another.

    Rectangular like every other route, and sized from the minimum shaft so it is
    a loop someone can see rather than a nick in the outline.
    """
    reach = max(minimum_rank_gap(theme) / 2, theme.edge.head_length * 2)
    corners = (("right", "top"), ("left", "top"), ("right", "bottom"), ("left", "bottom"))
    for out_side, in_side in corners:
        start = _anchor(box, out_side, 0.5)
        end = _anchor(box, in_side, 0.5)
        away = _stub_end(_port(box, out_side, 0.5), out_side, reach)
        back = _stub_end(_port(box, in_side, 0.5), in_side, reach)
        points = _simplify((start, away, (away[0], back[1]), back, end))
        if all(
            not obstacle.crosses(first, second)
            for first, second in pairwise(points)
            for obstacle in obstacles
            if obstacle.id != box.id
        ):
            return Route(
                connector.source, connector.target, connector.role, points, connector.label
            )
    raise LayoutError(
        f"no room for a self-loop on {connector.source!r}: every side of it is boxed in"
    )


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def place_labels(
    routes: Sequence[Route],
    obstacles: Sequence[Obstacle],
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[Label, ...]:
    """A box for every labelled route that touches nothing, in the order given.

    Three things a label must miss, and they are one failure to a reader — text
    with something drawn through it: its own line and every other line, every
    node box, and every label already placed. So the candidates are generated in
    preference order and each is *measured* against all three; the first that is
    clear is taken, and a label with no clear position is refused rather than
    drawn on top of something.

    Preference runs offset-first: a label two units further out but still beside
    the middle of its own line beats one at the perfect distance from the far end
    of the route, because a label's job is to say which line it belongs to.

    Raises:
        LayoutError: some label has no position clear of everything. The
            arrangement is what needs to change — a shorter label or more room —
            and the message says so.
    """
    size = theme.scale["label"]
    font = theme.font.default
    placed: list[Label] = []
    paths = tuple(segment for route in routes for segment in route.segments)

    for route in routes:
        if not route.label:
            continue
        extents = measurer.measure(route.label, font, size)
        for left, top in _label_candidates(route, extents.width, extents.height, theme):
            candidate = (left, top, left + extents.width, top + extents.height)
            # Tested with air around it, kept without. Text that merely fails to
            # overlap a line still reads as touching it, and the offsets the
            # placer works through are meaningless if the first position that
            # technically clears everything wins by a tenth of a unit.
            air = _inflate(candidate, LABEL_GAP / 2)
            clear = (
                not any(box.overlaps(air) for box in obstacles)
                and not any(_box_meets_segment(air, *path) for path in paths)
                and not any(_boxes_overlap(air, other.box) for other in placed)
            )
            if clear:
                placed.append(
                    Label(
                        text=route.label,
                        role=route.role,
                        left=left,
                        top=top,
                        width=extents.width,
                        height=extents.height,
                        ascent=extents.ascent,
                        font=font,
                    )
                )
                break
        else:
            raise LayoutError(
                f"no room for the label {route.label!r} on the edge from {route.source!r} to "
                f"{route.target!r}: every position beside it is taken by a box, a line or "
                f"another label. Shorten the label or give the diagram more room."
            )
    return tuple(placed)


def _label_candidates(
    route: Route, width: float, height: float, theme: Theme
) -> Iterator[tuple[float, float]]:
    """Top-left corners to try, nearest and most central first.

    The longest segment comes first because it is the part of the route that most
    reads as *the* line, and the middle of it before the ends for the same
    reason. Sides are tried in a fixed order rather than a clever one: with the
    offsets increasing outwards, a consistent side keeps the labels of parallel
    edges on the same side of their lines, which reads as deliberate.
    """
    gap = LABEL_GAP + theme.edge.stroke_width / 2
    ordered = sorted(
        enumerate(route.segments),
        key=lambda item: (-math.dist(item[1][0], item[1][1]), item[0]),
    )
    for multiple in LABEL_OFFSETS:
        offset = gap * multiple
        for _, (first, second) in ordered:
            for fraction in LABEL_POSITIONS:
                x = first[0] + (second[0] - first[0]) * fraction
                y = first[1] + (second[1] - first[1]) * fraction
                if first[0] == second[0]:  # a vertical run: beside it
                    yield x + offset, y - height / 2
                    yield x - offset - width, y - height / 2
                else:  # a horizontal run: above it, then below
                    yield x - width / 2, y - offset - height
                    yield x - width / 2, y + offset


def _inflate(
    box: tuple[float, float, float, float], margin: float
) -> tuple[float, float, float, float]:
    return box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin


def _boxes_overlap(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    return (
        first[0] < second[2] - _TOLERANCE
        and second[0] < first[2] - _TOLERANCE
        and first[1] < second[3] - _TOLERANCE
        and second[1] < first[3] - _TOLERANCE
    )


def _box_meets_segment(
    box: tuple[float, float, float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> bool:
    """Exactly, not by sampling: every route segment is axis-aligned."""
    left, right = sorted((first[0], second[0]))
    top, bottom = sorted((first[1], second[1]))
    return (
        box[0] < right + _TOLERANCE
        and left < box[2] + _TOLERANCE
        and box[1] < bottom + _TOLERANCE
        and top < box[3] + _TOLERANCE
    )


def label_primitives(label: Label) -> tuple[Primitive, ...]:
    """The one text run a placed label draws as.

    Anchored at its own left edge rather than centred, because the box placement
    already decided where the text goes: an anchor is a second opinion about
    position, and two opinions is how a label ends up half a word from where it
    was measured to be.
    """
    return (
        TextRun(
            label.role,
            x=label.left,
            y=label.baseline,
            text=label.text,
            level="label",
            font=label.font,
        ),
    )


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def edge_primitives(route: Route, theme: Theme) -> tuple[Primitive, ...]:
    """The shaft and its end treatments, in paint order.

    The head's tip is the route's own endpoint, which is the point on the border:
    that is what makes "touches the box" and "points at the box" the same fact
    rather than two things that have to agree.
    """
    role = theme.role_for(route.role)
    parts: list[Primitive] = [Path(route.role, points=route.points)]
    head = getattr(role, "head", "none")
    tail = getattr(role, "tail", "none")
    if head != "none" and len(route.points) >= 2:
        parts.extend(_marker(head, route.points[-2], route.points[-1], route.role, theme))
    if tail != "none" and len(route.points) >= 2:
        parts.extend(_marker(tail, route.points[1], route.points[0], route.role, theme))
    return tuple(parts)


def _marker(
    kind: str,
    from_point: tuple[float, float],
    tip: tuple[float, float],
    role: str,
    theme: Theme,
) -> tuple[Primitive, ...]:
    """One end treatment, pointing along the segment that arrives at `tip`."""
    length = theme.head_length_for(role)
    span = math.dist(from_point, tip) or 1.0
    dx = (tip[0] - from_point[0]) / span
    dy = (tip[1] - from_point[1]) / span
    nx, ny = -dy, dx
    half = length * HEAD_SPREAD

    def at(back: float, across: float) -> tuple[float, float]:
        return (tip[0] - dx * back + nx * across, tip[1] - dy * back + ny * across)

    if kind == "arrow":
        return (Polygon(role, points=(tip, at(length, half), at(length, -half))),)
    if kind == "open":
        return (Path(role, points=(at(length, half), tip, at(length, -half)), marker=True),)
    if kind == "diamond":
        return (
            Polygon(
                role,
                points=(tip, at(length / 2, half), at(length, 0.0), at(length / 2, -half)),
            ),
        )
    if kind == "circle":
        centre = at(length / 2, 0.0)
        return (Ellipse(role, cx=centre[0], cy=centre[1], rx=length / 2, ry=length / 2),)
    if kind == "bar":
        return (Path(role, points=(at(0.0, length / 2), at(0.0, -length / 2)), marker=True),)
    raise LayoutError(f"no geometry for edge end treatment {kind!r}")


__all__ = [
    "GRID_PRECISION",
    "HEAD_SPREAD",
    "LABEL_GAP",
    "LABEL_OFFSETS",
    "LABEL_POSITIONS",
    "OUTWARD",
    "PORT_SPREAD",
    "SEPARATION_PASSES",
    "SIDES",
    "TURN_COST",
    "Connector",
    "Label",
    "Obstacle",
    "Route",
    "edge_primitives",
    "head_room",
    "label_primitives",
    "minimum_rank_gap",
    "place_labels",
    "route_edges",
    "separate_lanes",
    "shaft_length",
]
