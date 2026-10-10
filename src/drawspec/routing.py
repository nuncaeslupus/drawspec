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
from collections.abc import Iterator, Mapping, Sequence, Set
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Final

from drawspec.errors import FitError, LayoutError
from drawspec.geometry import (
    CYLINDER_CAP,
    PARALLELOGRAM_SLANT,
    PERSON_HEAD,
    PERSON_SHOULDER,
    PERSON_TOP,
)
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

#: The multiples of that gap tried in turn, outwards, when something is. The
#: last two are for the long lines a direct route draws: a chord across a
#: crowded drawing has open paper further out than a rank gap ever offers, and
#: stopping the search at seven gaps refused a label that had somewhere to go.
LABEL_OFFSETS: Final = (1.0, 2.0, 3.5, 5.0, 7.0, 9.5, 12.5)

#: Where along a segment a label is tried: the middle, then either side of it,
#: then near its ends — again for the long ones, where a tenth of the way along
#: is still nowhere near the box.
LABEL_POSITIONS: Final = (0.5, 0.35, 0.65, 0.2, 0.8, 0.1, 0.9)

#: Coordinates are rounded to this many decimals before they become grid lines,
#: so a port computed twice is the same grid line twice.
GRID_PRECISION: Final = 9

_TOLERANCE: Final = 1e-7

#: How many times the lane separation is applied to its own output. Moving a run
#: lengthens the runs either side of it, so a pass can create the overlap the
#: next one settles; three is one more than any reference document has needed.
SEPARATION_PASSES: Final = 3

#: How far a hollow triangle reaches either side of its shaft, in head lengths:
#: wider than an arrow head's spread, so the outline encloses a visible space.
HOLLOW_SPREAD: Final = 0.55

#: How long a hollow triangle is, in head lengths: longer than an arrow head, as
#: a class diagram draws it — it is the mark the whole relation is read by.
HOLLOW_LENGTH: Final = 1.3

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

        The overlap of the two bounding rectangles is the whole answer while
        every segment is axis-aligned, because then the segment *is* its
        rectangle. A direct route is not, and the difference is not small: the
        rectangle a chord spans is most of the space between two ranks, nearly
        all of which the chord goes nowhere near. So a slope is then asked the
        real question — do all four corners of the box fall on one side of the
        line — which is the separating-axis argument finished off.
        """
        left, right = sorted((first[0], second[0]))
        top, bottom = sorted((first[1], second[1]))
        if not (
            left < self.right - _TOLERANCE
            and right > self.x + _TOLERANCE
            and top < self.bottom - _TOLERANCE
            and bottom > self.y + _TOLERANCE
        ):
            return False
        step_x, step_y = second[0] - first[0], second[1] - first[1]
        if abs(step_x) < _TOLERANCE or abs(step_y) < _TOLERANCE:
            return True
        reach = [
            -step_y * (x - first[0]) + step_x * (y - first[1])
            for x in (self.x, self.right)
            for y in (self.y, self.bottom)
        ]
        return max(reach) > _TOLERANCE and min(reach) < -_TOLERANCE


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
    source_port: tuple[str, float] | None = None
    """A side and a fraction along it this end must leave from, or `None` to let
    the router choose. Internal, never authored: an `entities` relation that
    names a field lands on that field's row, at the side facing the other box."""

    target_port: tuple[str, float] | None = None
    """As `source_port`, for the end the connector arrives at."""


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
    advance: float = 0.0
    """Baseline to baseline, for a label of more than one line; see `lines`."""

    @property
    def box(self) -> tuple[float, float, float, float]:
        """Left, top, right, bottom."""
        return self.left, self.top, self.left + self.width, self.top + self.height

    @property
    def lines(self) -> tuple[str, ...]:
        """The label's lines. One, unless its text carries a newline — which only a
        composed label does: a state machine's transition sets its event, guard
        and action one under another."""
        return tuple(self.text.split("\n"))

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
    if box.shape in ("parallelogram", "cylinder") and half_width and half_height:
        return _round_point(_on_slanted_or_drum(box, side, x, y))
    if box.shape == "person" and half_width and half_height:
        return _round_point(_on_person(box, side, x, y))
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


def _round_point(point: tuple[float, float]) -> tuple[float, float]:
    return _round(point[0]), _round(point[1])


def _on_slanted_or_drum(box: Obstacle, side: str, x: float, y: float) -> tuple[float, float]:
    """Where a port on `box`'s rectangle meets a parallelogram's or a drum's outline.

    A parallelogram's top and bottom are flat but shorter than the rectangle, so
    a port there is held on the edge; its sides lean, so a port on one moves in
    to where the side is at that height. A drum's sides are straight, and its lid
    and base are half-ellipses: a port on either moves to the rim's height there.
    """
    if box.shape == "parallelogram":
        slant = min(PARALLELOGRAM_SLANT, box.width / 2)
        if side == "top":
            return min(max(x, box.x + slant), box.right), y
        if side == "bottom":
            return min(max(x, box.x), box.right - slant), y
        down = (y - box.y) / box.height
        if side == "left":
            return box.x + slant * (1 - down), y
        return box.right - slant * down, y
    if side in ("left", "right"):
        return x, y
    cap = min(CYLINDER_CAP, box.height / 4)
    across = (x - box.centre[0]) / (box.width / 2)
    rise = cap * (1 - math.sqrt(max(1 - across**2, 0.0)))
    return (x, box.y + rise) if side == "top" else (x, box.bottom - rise)


def _on_person(box: Obstacle, side: str, x: float, y: float) -> tuple[float, float]:
    """Where a port on `box`'s rectangle meets a `person`'s outline.

    From above, an arrow lands on the head where the head is over it, and on the
    shoulders beside it; from the side, on the body, its rounded shoulder, or the
    head at that height. The base is flat between its two small corners. Each is
    the shape `kinds.common.person_silhouette` draws, so the arrow stops on a line.
    """
    centre_x = box.centre[0]
    centre_y = box.y + PERSON_HEAD
    shoulders = box.y + PERSON_TOP
    shoulder = min(PERSON_SHOULDER, box.width / 2, (box.bottom - shoulders) / 2)
    if side == "top":
        away = abs(x - centre_x)
        if away <= PERSON_HEAD:
            return x, centre_y - math.sqrt(max(PERSON_HEAD**2 - away**2, 0.0))
        corner = max(box.x + shoulder - x, x - (box.right - shoulder), 0.0)
        return x, shoulders + shoulder - math.sqrt(max(shoulder**2 - corner**2, 0.0))
    if side == "bottom":
        return x, y
    step = -1.0 if side == "left" else 1.0
    if y < shoulders:
        reach = math.sqrt(max(PERSON_HEAD**2 - (y - centre_y) ** 2, 0.0))
        return centre_x + step * reach, y
    rise = max(shoulders + shoulder - y, 0.0)
    inset = shoulder - math.sqrt(max(shoulder**2 - rise**2, 0.0))
    return (box.x + inset, y) if side == "left" else (box.right - inset, y)


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
        if separated_horizontally and not beside:
            return _around("bottom" if below else "top")
        return horizontal if separated_horizontally or not separated_vertically else vertical
    if separated_vertically and not below:
        return _around("right" if beside else "left")
    return vertical if separated_vertically or not separated_horizontally else horizontal


def _around(side: str) -> tuple[str, str]:
    """Both ends on `side`: how an edge that goes *backwards* leaves and returns.

    A graph that is a chain plus a few returns should draw as a straight chain
    with the returns going round it, and it did not: a return took the same two
    sides the chain uses — the bottom of one box, the top of another — so the
    chain's own edges had to share those sides with it and left at an angle. The
    corpus review saw the effect three times and named the cause once, exactly:
    *"the dotted line could go out of the right side of Performing to the right
    side of Storming. It would make every other arrow vertical."*

    Both ends on one side is what "goes round" means. It frees the ends of every
    box on the spine for the spine, which is the whole of the fix — the returning
    line then has the outside of the drawing to itself, which is where a reader
    already expects to find it.
    """
    return (side, side)


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
    anchors: Sequence[Obstacle] = (),
) -> tuple[Route, ...]:
    """Route every connector around every obstacle, in the order given.

    `anchors` are boxes a connector may **name** without their standing in
    anyone's way — a group's frame, and nothing else so far. The two roles a box
    plays here have always been separable and until R5-2 nothing needed them
    apart: an obstacle is somewhere a line cannot go, an endpoint is something a
    line may land on. A frame is the second and must not be the first, because
    every edge reaching a box inside it has to cross that border to get there.

    Raises:
        LayoutError: a connector names a box that is not there, two boxes share
            an id, or some edge has no orthogonal route that both misses every
            box and keeps a visible shaft. The last one is a statement about the
            arrangement rather than about the router — see `minimum_rank_gap`.
    """
    boxes: dict[str, Obstacle] = {}
    for box in (*obstacles, *anchors):
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
    # Every connector gets an orthogonal approach worked out, the straight ones
    # included: `direct` is a preference, and a chord that cannot be drawn
    # honestly falls back to the search, which needs the approach to have been
    # prepared with all the others.
    sides = {
        index: _pinned_sides(
            connector,
            _candidate_sides(boxes[connector.source], boxes[connector.target], direction),
        )
        for index, connector in enumerate(connectors)
        if connector.source != connector.target
    }
    fractions = _clear_pinned_ports(
        connectors,
        boxes,
        sides,
        _pinned_fractions(connectors, _assign_ports(connectors, boxes, sides)),
        channel,
    )
    fractions = _clear_frame_ports(
        connectors, boxes, sides, fractions, {box.id for box in anchors}, channel * 2
    )
    reaches = _shared_reaches(connectors, boxes, sides, fractions, obstacles, lanes, theme)
    approaches: dict[int, tuple[_Approach, _Approach]] = {}
    for index, side_pair in sides.items():
        connector = connectors[index]
        source, target = boxes[connector.source], boxes[connector.target]
        approaches[index] = (
            _approach(
                source,
                target,
                side_pair,
                fractions[index],
                obstacles,
                lanes,
                theme,
                reaches=(
                    reaches[(connector.source, side_pair[0])],
                    reaches[(connector.target, side_pair[1])],
                ),
            ),
            _approach(
                source,
                target,
                _pinned_sides(connector, _fallback_sides(side_pair)),
                _pinned_fractions((connector,), {0: (0.5, 0.5)})[0],
                obstacles,
                lanes,
                theme,
            ),
        )
    grid = _build_grid(approaches, obstacles, lanes, theme.edge.clearance)

    routes: list[Route] = []
    for index, connector in enumerate(connectors):
        if connector.source == connector.target:
            routes.append(
                _self_loop(connector, boxes[connector.source], obstacles, theme, direction)
            )
            continue
        if index in straight and connector.source_port is None and connector.target_port is None:
            chord = Route(
                source=connector.source,
                target=connector.target,
                role=connector.role,
                points=_chord(boxes[connector.source], boxes[connector.target]),
                label=connector.label,
            )
            if _chord_is_drawable(chord, obstacles, theme):
                routes.append(chord)
                continue
            # The centre line is only the first straight line worth trying. Two
            # boxes far apart across a narrow rank gap have a centre line that
            # grazes their neighbours, while a line between the facing sides,
            # off-centre towards each other, clears them with room to spare.
            # Routing that edge orthogonally drew a mesh of chords with two
            # right-angled brackets in it, which reads as two different
            # relations.
            offset = _offset_chord(chord, boxes, obstacles, theme)
            if offset is not None:
                routes.append(offset)
                continue
            # A chord that would cross a box it has nothing to do with, or that
            # is too short to carry its own head, is not drawn straight: the
            # route falls back to the orthogonal search, which knows how to go
            # around. `direct` is a preference about how a relation reads, and a
            # line through an uninvolved node's text is not a reading of it.
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
    pinned = {
        index: (connector.source_port is not None, connector.target_port is not None)
        for index, connector in enumerate(connectors)
        if connector.source_port is not None or connector.target_port is not None
    }
    return straighten(
        separate_lanes(tuple(routes), obstacles, theme), obstacles, theme, pinned=pinned
    )


def _pinned_sides(connector: Connector, sides: tuple[str, str]) -> tuple[str, str]:
    """`sides`, with any end the connector pins replaced by the side it names."""
    return (
        connector.source_port[0] if connector.source_port else sides[0],
        connector.target_port[0] if connector.target_port else sides[1],
    )


def _pinned_fractions(
    connectors: Sequence[Connector], fractions: Mapping[int, tuple[float, float]]
) -> dict[int, tuple[float, float]]:
    """`fractions`, with any end a connector pins at the fraction it names."""
    pinned = dict(fractions)
    for index, (source, target) in fractions.items():
        connector = connectors[index]
        pinned[index] = (
            connector.source_port[1] if connector.source_port else source,
            connector.target_port[1] if connector.target_port else target,
        )
    return pinned


def _clear_pinned_ports(
    connectors: Sequence[Connector],
    boxes: Mapping[str, Obstacle],
    sides: Mapping[int, tuple[str, str]],
    fractions: Mapping[int, tuple[float, float]],
    spacing: float,
) -> dict[int, tuple[float, float]]:
    """Free ends moved off the points pinned ends hold on the same side.

    Ports are spread along a side without knowing that some of them are fixed, so
    an end that only had to land on the box could be given the very point a
    field's row holds, and the two lines' ends were drawn one over the other. The
    free end moves to the nearest place along the side at least `spacing` from
    every pinned point; one with nowhere to go stays where it was.
    """
    adjusted = dict(fractions)
    held: dict[tuple[str, str], list[float]] = {}
    for index, connector in enumerate(connectors):
        if index not in sides:
            continue
        for end, (identifier, port) in enumerate(
            ((connector.source, connector.source_port), (connector.target, connector.target_port))
        ):
            if port is not None:
                held.setdefault((identifier, sides[index][end]), []).append(fractions[index][end])
    if not held:
        return adjusted
    for index, connector in enumerate(connectors):
        if index not in sides:
            continue
        ends = list(adjusted[index])
        for end, (identifier, port) in enumerate(
            ((connector.source, connector.source_port), (connector.target, connector.target_port))
        ):
            pinned = held.get((identifier, sides[index][end]))
            if port is not None or not pinned:
                continue
            box = boxes[identifier]
            length = box.width if sides[index][end] in ("top", "bottom") else box.height
            if length <= 0:
                continue
            step = spacing / length
            clear = [
                offer
                for offer in (
                    ends[end] + sign * k * step
                    for k in range(int(1 / step) + 1)
                    for sign in (1, -1)
                )
                if 0.1 <= offer <= 0.9
                and all(abs(offer - other) >= step - _TOLERANCE for other in pinned)
            ]
            if clear:
                ends[end] = clear[0]
        adjusted[index] = (ends[0], ends[1])
    return adjusted


def _chord_is_drawable(route: Route, obstacles: Sequence[Obstacle], theme: Theme) -> bool:
    """Whether a straight route may be drawn as one, rather than routed.

    Two things the orthogonal search guarantees by construction and a chord does
    not, so both are checked before one is kept.

    **It misses every box it is not joined to.** "A mesh is meant to cross
    itself" is about two *lines*; a line through a third node's text is a
    different failure with the same shape, and the reader cannot tell a
    deliberate crossing from a box drawn over. The clearance is the theme's, the
    same daylight every routed line keeps.

    **It has a shaft.** `min_shaft_length` and the head's own room are invariants
    of the drawing, not of the router — an arrow with no visible shaft is not an
    arrow whichever way it was found — and a theme may put `routing = "direct"`
    on a role that has a head, so the check cannot be skipped on the grounds that
    `link` has none.
    """
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


#: Where along a facing side an off-centre chord may land, tried nearest the
#: middle first. Never closer to a corner than a routed port gets
#: (`PORT_SPREAD`), so a chord does not land on a rounded corner.
_CHORD_FRACTIONS: Final = (0.5, 0.35, 0.65, 0.2, 0.8)


def _offset_chord(
    chord: Route, boxes: Mapping[str, Obstacle], obstacles: Sequence[Obstacle], theme: Theme
) -> Route | None:
    """A straight line between the two boxes' facing sides that can be drawn.

    Tried when the centre-to-centre chord cannot be: each end slides along the
    side that faces the other box, and the first pair, by how far the two ends
    moved from the middle, that `_chord_is_drawable` accepts is kept. `None`
    when the boxes face each other on no side, or no pair clears.
    """
    source, target = boxes[chord.source], boxes[chord.target]
    if target.y >= source.bottom - _TOLERANCE:
        sides = ("bottom", "top")
    elif source.y >= target.bottom - _TOLERANCE:
        sides = ("top", "bottom")
    elif target.x >= source.right - _TOLERANCE:
        sides = ("right", "left")
    elif source.x >= target.right - _TOLERANCE:
        sides = ("left", "right")
    else:
        return None
    # The run across the gap must itself be long enough for a shaft and a
    # head. A long slant through a gap narrower than that would pass the
    # shaft check while its head lay almost flat against the box it enters.
    gap = {
        "bottom": target.y - source.bottom,
        "top": source.y - target.bottom,
        "right": target.x - source.right,
        "left": source.x - target.right,
    }[sides[0]]
    if gap < theme.edge.min_shaft_length + theme.edge.head_length - _TOLERANCE:
        return None
    pairs = sorted(
        ((first, second) for first in _CHORD_FRACTIONS for second in _CHORD_FRACTIONS),
        key=lambda pair: (abs(pair[0] - 0.5) + abs(pair[1] - 0.5), pair),
    )
    for first, second in pairs:
        start = _on_side(source, sides[0], first)
        end = _on_side(target, sides[1], second)
        if _reenters(source, start, end) or _reenters(target, end, start):
            continue
        candidate = Route(
            source=chord.source,
            target=chord.target,
            role=chord.role,
            points=(start, end),
            label=chord.label,
        )
        if _chord_is_drawable(candidate, obstacles, theme):
            return candidate
    return None


def _on_side(box: Obstacle, side: str, fraction: float) -> tuple[float, float]:
    """The point of `box`'s outline at `fraction` along `side`, for any shape."""
    if side in ("top", "bottom"):
        x = box.x + box.width * fraction
        edge = box.y if side == "top" else box.bottom
        return _leaving(box, (x, box.centre[1]), (x, edge))
    y = box.y + box.height * fraction
    edge = box.x if side == "left" else box.right
    return _leaving(box, (box.centre[0], y), (edge, y))


def _reenters(box: Obstacle, start: tuple[float, float], end: tuple[float, float]) -> bool:
    """Whether a line leaving `box`'s outline at `start` heads back into it."""
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length <= 0:
        return True
    step = min(1.0, length / 2) / length
    probe = (start[0] + (end[0] - start[0]) * step, start[1] + (end[1] - start[1]) * step)
    return box.overlaps((probe[0], probe[1], probe[0], probe[1]))


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


def _clear_frame_ports(
    connectors: Sequence[Connector],
    boxes: Mapping[str, Obstacle],
    sides: Mapping[int, tuple[str, str]],
    fractions: Mapping[int, tuple[float, float]],
    frames: Set[str],
    spacing: float,
) -> dict[int, tuple[float, float]]:
    """Frame ends moved off the line a box inside the frame already leaves on.

    A group's contents are centred in its frame, so an edge leaving the middle
    of the frame's bottom and an edge leaving the middle of the bottom box inside
    it were on one vertical line: the member's edge crossed the frame's border
    exactly where the frame's own edge began, the two shared a trunk, and an
    edge from the whole composite read as one more edge from that one box. Both
    runs carry an endpoint, so lane separation cannot move either; the frame's
    end is the one free to move, and it moves to the nearest place along its side
    at least a lane clear of every such line.
    """
    adjusted = dict(fractions)
    if not frames:
        return adjusted
    # Each box end: its box, its side, where along that side, and the box at
    # the other end — a line only shares the frame's border if it leaves the
    # frame, so a member's edge to another member does not count.
    taken: list[tuple[str, str, float, str]] = []
    for index, (source_side, target_side) in sides.items():
        connector = connectors[index]
        for end, (node, side) in enumerate(
            ((connector.source, source_side), (connector.target, target_side))
        ):
            if node in frames:
                continue
            point = _port(boxes[node], side, fractions[index][end])
            along = 0 if side in ("top", "bottom") else 1
            other = connector.target if end == 0 else connector.source
            taken.append((node, side, point[along], other))
    for index, (source_side, target_side) in sides.items():
        connector = connectors[index]
        ends = list(adjusted[index])
        for end, (node, side) in enumerate(
            ((connector.source, source_side), (connector.target, target_side))
        ):
            if node not in frames:
                continue
            frame = boxes[node]
            along = 0 if side in ("top", "bottom") else 1
            low = frame.x if along == 0 else frame.y
            length = frame.width if along == 0 else frame.height
            if length <= 0:
                continue
            lines = [
                line
                for member, member_side, line, beyond in taken
                if member_side == side
                and _inside(boxes[member], frame)
                and not _inside(boxes[beyond], frame)
            ]
            if not lines:
                continue
            # Towards the other end first, so the moved edge turns away from the
            # member's line rather than across it.
            other = connector.target if end == 0 else connector.source
            toward = 1.0 if boxes[other].centre[along] >= low + length * ends[end] else -1.0
            for step in range(int(length / spacing) + 1):
                offers = (
                    (ends[end],)
                    if not step
                    else (
                        ends[end] + toward * step * spacing / length,
                        ends[end] - toward * step * spacing / length,
                    )
                )
                clear = [
                    offer
                    for offer in offers
                    if 0.1 <= offer <= 0.9
                    and all(
                        abs(low + length * offer - line) >= spacing - _TOLERANCE for line in lines
                    )
                ]
                if clear:
                    ends[end] = clear[0]
                    break
        adjusted[index] = (ends[0], ends[1])
    return adjusted


def _inside(box: Obstacle, frame: Obstacle) -> bool:
    """Whether `box` lies within `frame`'s rectangle."""
    return (
        box.x >= frame.x - _TOLERANCE
        and box.right <= frame.right + _TOLERANCE
        and box.y >= frame.y - _TOLERANCE
        and box.bottom <= frame.bottom + _TOLERANCE
    )


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


def _shared_reaches(
    connectors: Sequence[Connector],
    boxes: Mapping[str, Obstacle],
    sides: Mapping[int, tuple[str, str]],
    fractions: Mapping[int, tuple[float, float]],
    obstacles: Sequence[Obstacle],
    lanes: tuple[set[float], set[float]],
    theme: Theme,
) -> dict[tuple[str, str], float]:
    """One reach per box side, so the edges leaving it together turn together.

    `_reach` is a question about a single port: how far in front of *this* point
    is the first lane, capped at half the room actually there. Asked once per
    port, it gives different answers to the ports of one fan — they are at
    different places along the border, so different things are in front of them —
    and four edges leaving one box then turn in two lanes, alternating. A route
    that turns late runs horizontally straight through the vertical leg of one
    that turned early, and the drawing crosses itself: the second of the two
    mechanisms behind "arrows look good for 1 and 2 but are crossed for 3 and 4".

    The port order is already right and `separate_lanes` already keeps it, so the
    fix is not to compute a cleverer reach per port — it is to stop asking the
    question per port. Every edge on one side of one box turns at the **nearest**
    of their reaches, which is the only depth all of them are known to have room
    for; the separation pass then spreads them in port order, nested rather than
    alternating.
    """
    shared: dict[tuple[str, str], float] = {}
    for index, (source_side, target_side) in sides.items():
        connector = connectors[index]
        for identifier, side, fraction in (
            (connector.source, source_side, fractions[index][0]),
            (connector.target, target_side, fractions[index][1]),
        ):
            box = boxes[identifier]
            reach = _reach(_port(box, side, fraction), side, obstacles, lanes, theme)
            key = (identifier, side)
            shared[key] = min(shared.get(key, reach), reach)
    return shared


def _approach(
    source: Obstacle,
    target: Obstacle,
    sides: tuple[str, str],
    fractions: tuple[float, float],
    obstacles: Sequence[Obstacle],
    lanes: tuple[set[float], set[float]],
    theme: Theme,
    *,
    reaches: tuple[float, float] | None = None,
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
    source_reach, target_reach = (
        reaches
        if reaches is not None
        else (
            _reach(source_port, source_side, obstacles, lanes, theme),
            _reach(target_port, target_side, obstacles, lanes, theme),
        )
    )
    return _Approach(
        source=source.id,
        target=target.id,
        source_side=source_side,
        target_side=target_side,
        source_anchor=_anchor(source, source_side, source_fraction),
        target_anchor=_anchor(target, target_side, target_fraction),
        source_stub=_stub_end(source_port, source_side, source_reach),
        target_stub=_stub_end(target_port, target_side, target_reach),
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
    if not ahead and math.isinf(room):
        # Out past every lane with nothing in front: the far side of a group's
        # frame, whose border is outside every box the lanes were drawn from.
        # The stub used to run to infinity there and no route could be found;
        # one lane's width out is where the lane outside a box would have been.
        return max(theme.edge.lane_spacing, head_room(theme))
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
            offers = _tries(target - run.line)
            # Every offer that does not strand a route on another's anchor, then
            # every offer at all. A preference rather than a rule: the point of
            # the pass is to get two lines off each other, and refusing the only
            # placement available would leave them exactly as they were found.
            for guarded in (True, False):
                placed = False
                for candidate_offset in offers:
                    candidate = _shifted(moved[run.index], run.segment, candidate_offset)
                    if candidate is None or not _is_clear(candidate, obstacles, theme):
                        continue
                    if guarded and _lands_on_another(candidate, moved, run.index):
                        continue
                    moved[run.index] = candidate
                    placed = True
                    break
                if placed:
                    break
    return tuple(moved)


def straighten(
    routes: Sequence[Route],
    obstacles: Sequence[Obstacle],
    theme: Theme,
    *,
    pinned: Mapping[int, tuple[bool, bool]] | None = None,
) -> tuple[Route, ...]:
    """Every route with its unreadable turns taken out.

    A route that steps sideways by six units and carries on is drawn as two
    corners and a nub between them, and it reads as the router wobbling rather
    than as a line going anywhere — *"notice the small angle in the last arrow"*,
    *"again a slightly angled arrow"*, *"I would have expected a straight arrow
    instead of even more angled"*. Three notes on three drawings for one fault.

    The floor is `[edge] min_shaft_length`, and reusing it is the argument:
    drawspec already refuses to draw a *shaft* shorter than that because nobody
    can see it, so a *turn* shorter than it is a turn nobody can see either. One
    number, one reason, and a theme that wants blunter geometry moves both at
    once.

    Taking one out slides everything on one side of it, which moves that end's
    anchor along its own border — so the anchor is checked against the shape it
    sits on rather than against the rectangle: sliding along the top of a pill is
    fine until the cap starts, and sliding along a diamond is never fine, because
    the anchor is on the slope and would come off it. `_anchor` already knows
    all of that, so the check is that the moved point is still the anchor its
    fraction names.

    The end that moves is whichever one can: the source is tried first because a
    route's head is the end a reader looks at, and moving the tail is the smaller
    change to what the drawing says.

    `pinned` names, per route index, the ends that may not move at all: a port
    the caller fixed — a field's row — is where the line has to be.
    """
    boxes = {box.id: box for box in obstacles}
    fixed = pinned or {}
    settled = list(routes)
    for index, route in enumerate(settled):
        # One turn can only be removed by moving a run that another turn owns, so
        # the pass repeats until nothing more comes out; bounded by the number of
        # turns, since each success removes at least one.
        for _ in range(len(route.points)):
            better = _unjogged(
                settled[index], boxes, obstacles, theme, settled, index, fixed.get(index)
            )
            if better is None:
                break
            settled[index] = better
    return tuple(settled)


def _unjogged(
    route: Route,
    boxes: Mapping[str, Obstacle],
    obstacles: Sequence[Obstacle],
    theme: Theme,
    routes: Sequence[Route],
    index: int,
    pinned: tuple[bool, bool] | None = None,
) -> Route | None:
    """`route` with its shortest unreadable turn removed, or `None` if none can be."""
    held = pinned or (False, False)
    points = route.points
    for position in range(1, len(points) - 2):
        first, second = points[position], points[position + 1]
        offset = (second[0] - first[0], second[1] - first[1])
        if math.hypot(*offset) >= theme.edge.min_shaft_length - _TOLERANCE:
            continue
        for moving_source in (True, False):
            if held[0 if moving_source else 1]:
                continue
            candidate = _slid(route, position, offset, boxes, moving_source=moving_source)
            if candidate is None:
                continue
            if not _is_clear(candidate, obstacles, theme):
                continue
            if _lands_on_another(candidate, routes, index):
                continue
            return candidate
    return None


def _slid(
    route: Route,
    position: int,
    offset: tuple[float, float],
    boxes: Mapping[str, Obstacle],
    *,
    moving_source: bool,
) -> Route | None:
    """`route` with one side of the turn at `position` slid onto the other's line.

    The moved end's endpoint is *recomputed* rather than translated, because a
    route lands on the shape and not on the rectangle: slide along the top of a
    diamond and the outline rises to meet you, so the anchor takes a new depth
    and the run into it simply gets shorter. `_anchor` already knows the shape of
    every box, so this asks it again at the new fraction instead of assuming the
    old answer still holds — which is the whole difference between straightening
    an arrow into a rectangle and putting one beside a diamond.

    `None` when the slide would take the anchor off the side it is on: past a
    corner, or onto a pill's cap, where the flat the run is perpendicular to has
    run out.
    """
    points = list(route.points)
    end, neighbour_at = (0, 1) if moving_source else (len(points) - 1, len(points) - 2)
    box = boxes.get(route.source if moving_source else route.target)
    side = _side_facing(box, points[end], points[neighbour_at]) if box else None
    if box is None or side is None:
        return None

    step = offset if moving_source else (-offset[0], -offset[1])
    along = 0 if side in ("top", "bottom") else 1
    span, start = (box.width, box.x) if along == 0 else (box.height, box.y)
    if not span:
        return None
    wanted = points[end][along] + step[along]
    fraction = (wanted - start) / span
    if not 0.0 < fraction < 1.0:
        return None
    anchor = _anchor(box, side, fraction)
    if abs(anchor[along] - wanted) > _TOLERANCE:
        # A pill's cap: `_anchor` clamped the port back onto the flat, so the run
        # would no longer meet the border square.
        return None

    inner = [
        (_round(x + step[0]), _round(y + step[1]))
        for x, y in (points[1 : position + 1] if moving_source else points[position + 1 : -1])
    ]
    points = (
        [anchor, *inner, *points[position + 1 :]]
        if moving_source
        else [
            *points[: position + 1],
            *inner,
            anchor,
        ]
    )
    depth = 1 - along
    if (points[neighbour_at][depth] - anchor[depth]) * OUTWARD[side][depth] <= _TOLERANCE:
        # The new anchor sits past the point the run turns at — the shape reaches
        # further out here than the route left room for.
        return None
    simplified = _simplify(points)
    return replace(route, points=simplified) if len(simplified) >= 2 else None


def _side_facing(
    box: Obstacle, point: tuple[float, float], neighbour: tuple[float, float]
) -> str | None:
    """Which side of `box` a run from `point` towards `neighbour` leaves by."""
    step = (neighbour[0] - point[0], neighbour[1] - point[1])
    for side, outward in OUTWARD.items():
        if step[0] * outward[0] + step[1] * outward[1] > _TOLERANCE:
            return side
    return None


def _lands_on_another(candidate: Route, routes: Sequence[Route], index: int) -> bool:
    """Whether a shifted route would come to rest along another route's line.

    Moving a run does not only move that run: it lengthens the two perpendicular
    ones either side of it, and the far end of *those* is an anchor on a border
    that cannot get out of the way. So a lane that is clear of every box can
    still put one route's approach along another's, and the separation pass would
    then have no way to fix what it had just made — both runs carry an endpoint,
    so neither is movable, and the band is skipped on the next pass.

    Only *anchored* runs count, on both sides — the first and last of each route,
    which carry an endpoint. Two middle runs sharing a line is a collision the
    next pass can still settle by moving either of them, and refusing those would
    block the very moves that prise a band apart. Two anchored runs sharing one
    is the dead end: neither may move, so the pass sees it on every later pass
    and can do nothing about it.

    And only a *new* dead end. Two boxes in the same column give their stubs the
    same line by construction — a route leaving the bottom of one and a route
    arriving at the top of the other below it are both on that column's centre —
    so a placement is refused for making the count worse, never for a clash the
    route was already in. Refusing those would leave every such band exactly as
    it was found.
    """
    return _anchor_clashes(candidate, routes, index) > _anchor_clashes(routes[index], routes, index)


def _anchor_clashes(route: Route, routes: Sequence[Route], index: int) -> int:
    """How many of `route`'s anchored runs lie along another route's anchored run."""
    mine = _anchored(route)
    return sum(
        _shares_a_line(one, other)
        for position, other_route in enumerate(routes)
        if position != index
        for one in mine
        for other in _anchored(other_route)
    )


def _anchored(route: Route) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    """The runs of `route` that carry an endpoint, and so can never move."""
    segments = route.segments
    if not segments:
        return ()
    return (segments[0], segments[-1]) if len(segments) > 1 else (segments[0],)


def _shares_a_line(
    one: tuple[tuple[float, float], tuple[float, float]],
    two: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    """Whether two axis-aligned segments are collinear with an overlapping span."""
    for axis, along in ((0, 1), (1, 0)):
        if not (
            abs(one[0][axis] - one[1][axis]) < _TOLERANCE
            and abs(two[0][axis] - two[1][axis]) < _TOLERANCE
            and abs(one[0][axis] - two[0][axis]) < _TOLERANCE
        ):
            continue
        low = max(min(one[0][along], one[1][along]), min(two[0][along], two[1][along]))
        high = min(max(one[0][along], one[1][along]), max(two[0][along], two[1][along]))
        if high - low > _TOLERANCE:
            return True
    return False


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

    entry: float = 0.0
    exit: float = 0.0
    """Where the run starts and ends along its own direction, in route order."""

    outward: float = 0.0
    """Which way the band is left: `+1` when the exit corner is past the entry."""

    @property
    def travel(self) -> float:
        """How far this run goes through the band — the length of it."""
        return abs(self.exit - self.entry)


def _nesting_sign(runs: Sequence[_Run]) -> float:
    """Which way a band of runs that tie on `approach` should nest.

    The second of the two mechanisms behind "arrows look good for 1 and 2 but
    are crossed for 3 and 4", and the one `approach` cannot see. Every run of a
    fan enters the band from the same corner and leaves towards the same one, so
    they all report the same two corners and tie — and a tie went back to the
    order the edges were written in, which is where this whole defect started.

    What separates them is how far each goes before it turns off: a run whose
    span contains another's turn must be on the near side of it, or its long leg
    is drawn straight through that turn. So a fan nests by length — and *which*
    end is near depends on which end of the band the fan spreads at.

    A fan **out** of a box spreads at its far end: the runs start within a few
    units of each other on one border and end at targets all over the drawing.
    There the long run turns off last, so it hugs the box and the short ones sit
    outside it. A fan **in** spreads at its near end and nests the other way
    round: the long run is the outer one. Same rule, opposite sign, and the sign
    is exactly which end of the group is spread — measured, because a run on its
    own cannot tell which end of it the others are clustered at.
    """
    entries = [run.entry for run in runs]
    exits = [run.exit for run in runs]
    return 1.0 if max(exits) - min(exits) >= max(entries) - min(entries) else -1.0


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
                entry, leaves = first[1], second[1]
            elif abs(first[1] - second[1]) < _TOLERANCE:
                orientation, line = "h", first[1]
                span = sorted((first[0], second[0]))
                entry, leaves = first[0], second[0]
            else:
                continue
            across = 1 if orientation == "h" else 0
            corners = [
                route.points[position][across]
                for position in (segment - 1, segment + 2)
                if 0 <= position < len(route.points)
            ]
            approach = sum(corners) / len(corners) if corners else line
            outward = 0.0
            if len(corners) == 2:
                outward = 1.0 if corners[1] >= corners[0] else -1.0
            runs[orientation].append(
                _Run(
                    index,
                    segment,
                    span[0],
                    span[1],
                    movable,
                    line,
                    approach,
                    entry=entry,
                    exit=leaves,
                    outward=outward,
                )
            )

    groups: list[tuple[list[_Run], float | None]] = []
    for entries in runs.values():
        for lane in _bands(sorted(entries, key=lambda run: run.line), spacing):
            for component in _overlapping(sorted(lane, key=lambda run: (run.low, run.high))):
                free_runs = [run for run in component if run.movable]
                held = [run.line for run in component if not run.movable]
                if len({run.index for run in component}) > 1 and free_runs:
                    anchor = sum(held) / len(held) if held else None
                    # Ordered by where each route is going, then by how far it
                    # goes, then by where it currently is. `approach` first is
                    # what keeps the lanes in the routes' own order; the nesting
                    # settles a fan, every run of which reports the same
                    # approach; `line` breaks what is left so a band the router
                    # already spread stays spread the way it was. The whole key
                    # is a total order rather than a stable-sort accident.
                    nesting = _nesting_sign(free_runs)
                    groups.append(
                        (
                            sorted(
                                free_runs,
                                key=lambda run: (
                                    run.approach,
                                    -run.travel * run.outward * nesting,
                                    run.line,
                                ),
                            ),
                            anchor,
                        )
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
    # Its own two boxes are exempt only where it meets them. A run between two
    # corners moved by lane separation into a crowded gap can land inside the box
    # the route is about to enter, and then arrives at its border from within.
    own = [box for box in obstacles if box.id in (route.source, route.target)]
    if any(box.crosses(first, second) for first, second in route.segments[1:-1] for box in own):
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
    connector: Connector,
    box: Obstacle,
    obstacles: Sequence[Obstacle],
    theme: Theme,
    direction: str = "down",
) -> Route:
    """A loop back to the same box, on the first side `loop_route` offers that is clear.

    For a caller that has not reserved room for the loop — the graph family
    routes its own, with room made for them in the layout; see `self_loops`.

    Raises:
        LayoutError: every side the loop could take crosses another box.
    """
    preferred = LOOP_SIDES.get(direction, LOOP_SIDES["down"])
    for side in (*preferred, *(side for side in SIDES if side not in preferred)):
        route = loop_route(box, side, connector, theme)
        if all(
            not obstacle.crosses(first, second)
            for first, second in pairwise(route.points)
            for obstacle in obstacles
            if obstacle.id != box.id
        ):
            return route
    raise LayoutError(
        f"no room for a self-loop on {connector.source!r}: every side of it is boxed in"
    )


# ---------------------------------------------------------------------------
# Self-loops
# ---------------------------------------------------------------------------

#: The sides a self-loop takes, in preference order, by the layout's direction:
#: **across** the reading direction, never along it. The top and bottom of a box
#: in a downward drawing are where its own incoming and outgoing edges arrive, and
#: a loop drawn there — which is what `flow` used to do — re-entered the box
#: across its own incoming arrow, so the two heads met in one place and the loop
#: read as a branch of the edge above it. A box with two loops uses both sides.
LOOP_SIDES: Final[Mapping[str, tuple[str, str]]] = {
    "down": ("right", "left"),
    "right": ("bottom", "top"),
}

#: The most self-loops one box may carry: one on each side `LOOP_SIDES` names.
MAX_LOOPS: Final = 2


def loop_reach(theme: Theme) -> float:
    """How far out from its box a self-loop runs.

    Half the minimum rank gap, so the loop is the size of an ordinary arrow's
    shaft and head — a loop someone can see rather than a nick in the outline —
    and never less than two heads, so its returning leg carries its own head with
    line behind it.
    """
    return max(minimum_rank_gap(theme) / 2, theme.edge.head_length * 2)


def _loop_span(box: Obstacle, side: str, theme: Theme) -> tuple[float, float]:
    """Where along `side` the loop leaves and returns, as fractions of that side.

    Half the side, centred — and no wider than a square loop, so a wide box's
    loop on its bottom is still a loop and not a second, shallower box under it.
    """
    length = box.width if side in ("top", "bottom") else box.height
    span = min(length / 2, loop_reach(theme) * 2)
    half = span / 2 / length if length else 0.25
    return 0.5 - half, 0.5 + half


def loop_route(box: Obstacle, side: str, connector: Connector, theme: Theme) -> Route:
    """A self-loop on one side of `box`: out, along, and back in on the **same** side.

    Leaving and returning on one side is what keeps the loop off every other
    edge's ends — the sides along the reading direction belong to those — and
    what makes it read as *this state again* rather than as a route somewhere
    else. Drawn clockwise on every side, so two loops on one box turn the same
    way. Rectangular like every other route; the head is on the returning leg,
    pointing back into the box.
    """
    low, high = _loop_span(box, side, theme)
    # Clockwise: down the right side, along the bottom to the left, up the left
    # side, along the top to the right.
    out, back = {"right": (low, high), "bottom": (high, low), "left": (high, low)}.get(
        side, (low, high)
    )
    reach = loop_reach(theme)
    start, end = _anchor(box, side, out), _anchor(box, side, back)
    if side in ("left", "right"):
        far = _round(box.right + reach if side == "right" else box.x - reach)
        points = (start, (far, start[1]), (far, end[1]), end)
    else:
        far = _round(box.bottom + reach if side == "bottom" else box.y - reach)
        points = (start, (start[0], far), (end[0], far), end)
    return Route(connector.source, connector.target, connector.role, points, connector.label)


@dataclass(frozen=True)
class Loop:
    """A self-loop, placed: its route, its label, and everything it draws on."""

    side: str
    route: Route
    label: Label | None

    @property
    def zone(self) -> tuple[float, float, float, float]:
        """Left, top, right, bottom of the loop's line and its label together."""
        xs = [x for x, _ in self.route.points]
        ys = [y for _, y in self.route.points]
        if self.label is not None:
            left, top, right, bottom = self.label.box
            xs += [left, right]
            ys += [top, bottom]
        return min(xs), min(ys), max(xs), max(ys)


def loop_label_size(text: str, theme: Theme, measurer: TextMeasurer) -> tuple[float, float]:
    """The width and height a loop's label takes, or nothing for an unlabelled loop."""
    if not text:
        return 0.0, 0.0
    width, height, _, _ = label_extents(text, theme, measurer)
    return width, height


def loop_margin(side: str, label: tuple[float, float], theme: Theme) -> float:
    """How far past its box's `side` a loop and its label reach.

    The amount the layout must keep clear beside a box with a loop on that side,
    so that the loop is part of the box's reserved extent and a neighbour can
    never be placed on top of it.
    """
    width, height = label
    gap = LABEL_GAP + theme.edge.stroke_width / 2
    beyond = (width if side in ("left", "right") else height) if width else 0.0
    return loop_reach(theme) + (gap + beyond if width else theme.edge.stroke_width)


def place_loop(
    box: Obstacle, side: str, connector: Connector, theme: Theme, measurer: TextMeasurer
) -> Loop:
    """A self-loop and its label, the label **outside** the loop beside its far leg.

    Not left to `place_labels`: a loop's label has one right place — beyond the
    leg furthest from the box, where it can belong to nothing else — and the
    room for it was reserved in the layout, so there is nothing to search for.
    Inside the loop it would be between the line and the box it loops on.
    """
    route = loop_route(box, side, connector, theme)
    if not connector.label:
        return Loop(side, route, None)
    width, height, ascent, advance = label_extents(connector.label, theme, measurer)
    gap = LABEL_GAP + theme.edge.stroke_width / 2
    (x1, y1), (x2, y2) = route.points[1], route.points[2]
    middle_x, middle_y = (x1 + x2) / 2, (y1 + y2) / 2
    if side == "right":
        left, top = x1 + gap, middle_y - height / 2
    elif side == "left":
        left, top = x1 - gap - width, middle_y - height / 2
    elif side == "bottom":
        left, top = middle_x - width / 2, y1 + gap
    else:
        left, top = middle_x - width / 2, y1 - gap - height
    label = Label(
        text=connector.label,
        role=connector.role,
        left=left,
        top=top,
        width=width,
        height=height,
        ascent=ascent,
        font=theme.font.default,
        advance=advance,
    )
    return Loop(side, route, label)


def loop_sides(
    box: Obstacle,
    count: int,
    claimed: Set[str],
    direction: str,
) -> tuple[str, ...]:
    """Which sides `count` loops on `box` take, given the sides other edges use.

    Across the reading direction always, and a side no other edge of this box
    ends on before one that some edge does: a return edge in a downward drawing
    goes round the outside on the right or the left (see `_around`), and a loop
    on that same side would sit on its ends.
    """
    del box  # the choice is the box's neighbourhood's, not its size's
    preferred = LOOP_SIDES.get(direction, LOOP_SIDES["down"])
    ordered = sorted(preferred, key=lambda side: side in claimed)
    return tuple(ordered[:count])


def goes_round(connector: Connector, boxes: Mapping[str, Obstacle], direction: str) -> bool:
    """Whether the router takes this connector round the outside: a return edge.

    The router's own analytic answer (see `_around`): both ends on one side.
    """
    source, target = boxes[connector.source], boxes[connector.target]
    first, second = _candidate_sides(source, target, direction)
    return first == second


def claimed_sides(
    identifier: str,
    connectors: Sequence[Connector],
    boxes: Mapping[str, Obstacle],
    direction: str,
) -> frozenset[str]:
    """The sides of `identifier` the router will end other connectors on.

    Asked of `_candidate_sides`, the same analytic rule the router uses, so the
    answer is the router's own rather than a guess at it.
    """
    sides: set[str] = set()
    for connector in connectors:
        if connector.source == connector.target:
            continue
        if identifier not in (connector.source, connector.target):
            continue
        if connector.source not in boxes or connector.target not in boxes:
            continue
        pair = _candidate_sides(boxes[connector.source], boxes[connector.target], direction)
        if connector.source == identifier:
            sides.add(pair[0])
        if connector.target == identifier:
            sides.add(pair[1])
    return frozenset(sides)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def label_extents(
    text: str, theme: Theme, measurer: TextMeasurer
) -> tuple[float, float, float, float]:
    """A label's width, height, first ascent and line advance, one line per newline.

    Each line is a measured line of the label type, stacked at that line's own
    height, so a one-line label measures exactly as it always has.
    """
    lines = text.split("\n")
    extents = [measurer.measure(line, theme.font.default, theme.scale["label"]) for line in lines]
    advance = extents[0].height
    return (
        max(extent.width for extent in extents),
        advance * len(lines),
        extents[0].ascent,
        advance,
    )


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
    font = theme.font.default
    placed: list[Label] = []
    paths = tuple(segment for route in routes for segment in route.segments)
    mine = {id(route): route.segments for route in routes}

    for route in routes:
        if not route.label:
            continue
        width, height, ascent, advance = label_extents(route.label, theme, measurer)
        for left, top in _label_candidates(route, width, height, theme):
            candidate = (left, top, left + width, top + height)
            # Tested with air around it, kept without. Text that merely fails to
            # overlap a line still reads as touching it, and the offsets the
            # placer works through are meaningless if the first position that
            # technically clears everything wins by a tenth of a unit.
            air = _inflate(candidate, LABEL_GAP / 2)
            clear = (
                not any(box.overlaps(air) for box in obstacles)
                and not any(_box_meets_segment(air, *path) for path in paths)
                and not any(_boxes_overlap(air, other.box) for other in placed)
                and _nearest_is_its_own(candidate, route, routes, mine)
            )
            if clear:
                placed.append(
                    Label(
                        text=route.label,
                        role=route.role,
                        left=left,
                        top=top,
                        width=width,
                        height=height,
                        ascent=ascent,
                        font=font,
                        advance=advance,
                    )
                )
                break
        else:
            # A `FitError` rather than a `LayoutError`, because that is what this
            # is: the label is content that does not fit, and content that does
            # not fit is what the elastic band exists to answer. Raised as a
            # layout failure it went straight past `fit` — so a diagram whose
            # every label would have been clear one step of type smaller was
            # refused outright instead of being drawn. If the band runs out the
            # author still gets this message, which is the honest end of it.
            raise FitError(
                f"no room for the label {route.label!r} on the edge from {route.source!r} to "
                f"{route.target!r}: every position beside it is taken by a box, a line or "
                f"another label. Shorten the label or give the diagram more room."
            )
    return tuple(placed)


def _nearest_is_its_own(
    candidate: tuple[float, float, float, float],
    route: Route,
    routes: Sequence[Route],
    segments: Mapping[int, tuple[tuple[tuple[float, float], tuple[float, float]], ...]],
) -> bool:
    """Whether this position is nearer its own line than anybody else's.

    A label that clears every line can still be *beside the wrong one*, which is
    what the reviewer saw: two arrows leaving one box, and the text for the left
    one sitting closer to the right one — *"now the edge text is in a weird
    position"*. Missing everything is not the same as belonging to something, and
    only the second is what a label is for.

    Ties go to the label: two lines exactly equidistant is a drawing with no
    right answer, and refusing it would cost a placement to gain nothing.
    """
    centre = ((candidate[0] + candidate[2]) / 2, (candidate[1] + candidate[3]) / 2)
    own = min((_distance_to(centre, *path) for path in segments[id(route)]), default=math.inf)
    for other in routes:
        if other is route:
            continue
        for path in segments[id(other)]:
            if _distance_to(centre, *path) < own - _TOLERANCE:
                return False
    return True


def _distance_to(
    point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]
) -> float:
    """The distance from `point` to the segment `first`-`second`."""
    step_x, step_y = second[0] - first[0], second[1] - first[1]
    span = step_x * step_x + step_y * step_y
    if span <= _TOLERANCE:
        return math.dist(point, first)
    along = ((point[0] - first[0]) * step_x + (point[1] - first[1]) * step_y) / span
    along = min(max(along, 0.0), 1.0)
    return math.dist(point, (first[0] + step_x * along, first[1] + step_y * along))


def _label_candidates(
    route: Route, width: float, height: float, theme: Theme
) -> Iterator[tuple[float, float]]:
    """Top-left corners to try, nearest and most central first.

    The longest segment comes first because it is the part of the route that most
    reads as *the* line, and the middle of it before the ends for the same
    reason. Sides are tried in a fixed order rather than a clever one: with the
    offsets increasing outwards, a consistent side keeps the labels of parallel
    edges on the same side of their lines, which reads as deliberate.

    A **diagonal** run — a direct route, where the theme draws a role straight —
    is offset along its own normal. Stepping up and down from the midpoint of a
    slope does not clear it: the line is at a different height a few units along,
    so the label lands back on top of it a moment later, and every offer looks
    occupied. Three corpus documents were refused outright for exactly that,
    which is the sort of thing a new routing mode buys if the rest of the
    pipeline is left assuming right angles.
    """
    gap = LABEL_GAP + theme.edge.stroke_width / 2
    ordered = sorted(
        enumerate(route.segments),
        key=lambda item: (-math.dist(item[1][0], item[1][1]), item[0]),
    )
    for multiple in LABEL_OFFSETS:
        offset = gap * multiple
        for _, (first, second) in ordered:
            step_x, step_y = second[0] - first[0], second[1] - first[1]
            span = math.hypot(step_x, step_y)
            for fraction in LABEL_POSITIONS:
                x = first[0] + step_x * fraction
                y = first[1] + step_y * fraction
                if abs(step_x) < _TOLERANCE:  # a vertical run: beside it
                    yield x + offset, y - height / 2
                    yield x - offset - width, y - height / 2
                elif abs(step_y) < _TOLERANCE:  # a horizontal run: above, then below
                    yield x - width / 2, y - offset - height
                    yield x - width / 2, y + offset
                elif span:
                    # Out along the normal, far enough that the whole box clears
                    # the slope rather than only its centre.
                    away = offset + (width * abs(step_y) + height * abs(step_x)) / (2 * span)
                    across_x, across_y = -step_y / span * away, step_x / span * away
                    yield x + across_x - width / 2, y + across_y - height / 2
                    yield x - across_x - width / 2, y - across_y - height / 2


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
    """Exactly, not by sampling — and for a **diagonal** as well as an axis one.

    The bounding-rectangle test this used to be is exact while every segment is
    axis-aligned, because then the segment *is* its bounding rectangle. A direct
    route is not: the box a chord spans is most of the space between two ranks,
    almost all of which the chord does not touch, so testing that box rejects
    every position beside the line — including the ones the placer generates
    along the chord's own normal precisely because they are clear.

    So an axis-aligned run keeps the cheap answer and a slope gets the real one,
    by the separating-axis argument: two convex shapes miss each other if some
    axis separates them, and for a rectangle and a segment the only axes worth
    trying are the rectangle's two and the segment's own normal.
    """
    left, right = sorted((first[0], second[0]))
    top, bottom = sorted((first[1], second[1]))
    outside = (
        box[0] > right + _TOLERANCE
        or left > box[2] + _TOLERANCE
        or box[1] > bottom + _TOLERANCE
        or top > box[3] + _TOLERANCE
    )
    if outside:
        return False
    step_x, step_y = second[0] - first[0], second[1] - first[1]
    if abs(step_x) < _TOLERANCE or abs(step_y) < _TOLERANCE:
        return True

    # The segment's normal. A rectangle sits clear of the line when all four of
    # its corners fall on one side of it.
    reach = [
        -step_y * (x - first[0]) + step_x * (y - first[1])
        for x in (box[0], box[2])
        for y in (box[1], box[3])
    ]
    return not (max(reach) < -_TOLERANCE or min(reach) > _TOLERANCE)


def label_primitives(label: Label) -> tuple[Primitive, ...]:
    """The one text run a placed label draws as.

    Anchored at its own left edge rather than centred, because the box placement
    already decided where the text goes: an anchor is a second opinion about
    position, and two opinions is how a label ends up half a word from where it
    was measured to be.
    """
    return tuple(
        TextRun(
            label.role,
            x=label.left,
            y=label.baseline + index * label.advance,
            text=line,
            level="label",
            font=label.font,
        )
        for index, line in enumerate(label.lines)
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
    head = getattr(role, "head", "none")
    tail = getattr(role, "tail", "none")
    points = route.points
    # A hollow head is an outline: the shaft stops at its base rather than
    # running on to the tip through the middle of it.
    if head == "triangle" and len(points) >= 2:
        points = (*points[:-1], hollow_base(points[-2], points[-1], route.role, theme))
    if tail == "triangle" and len(points) >= 2:
        points = (hollow_base(points[1], points[0], route.role, theme), *points[1:])
    parts: list[Primitive] = [Path(route.role, points=points)]
    if head != "none" and len(route.points) >= 2:
        parts.extend(end_marker(head, route.points[-2], route.points[-1], route.role, theme))
    if tail != "none" and len(route.points) >= 2:
        parts.extend(end_marker(tail, route.points[1], route.points[0], route.role, theme))
    return tuple(parts)


def hollow_base(
    from_point: tuple[float, float], tip: tuple[float, float], role: str, theme: Theme
) -> tuple[float, float]:
    """Where a shaft ending in a hollow head stops: one head length back from `tip`."""
    length = theme.head_length_for(role) * HOLLOW_LENGTH
    span = math.dist(from_point, tip) or 1.0
    back = min(length, span)
    return (
        tip[0] - (tip[0] - from_point[0]) / span * back,
        tip[1] - (tip[1] - from_point[1]) / span * back,
    )


def end_marker(
    kind: str,
    from_point: tuple[float, float],
    tip: tuple[float, float],
    role: str,
    theme: Theme,
) -> tuple[Primitive, ...]:
    """One end treatment of `role`, its tip at `tip`, along the run from `from_point`."""
    return _marker(kind, from_point, tip, role, theme)


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
    if kind == "triangle":
        # Wider than an arrow head, as a class diagram draws it, and traced as an
        # open path back to its first corner: an edge role's closed figure is
        # filled, and this one is an outline.
        long = length * HOLLOW_LENGTH
        wide = long * HOLLOW_SPREAD
        corner = at(long, wide)
        return (Path(role, points=(corner, tip, at(long, -wide), corner), marker=True),)
    raise LayoutError(f"no geometry for edge end treatment {kind!r}")


__all__ = [
    "GRID_PRECISION",
    "HEAD_SPREAD",
    "HOLLOW_LENGTH",
    "HOLLOW_SPREAD",
    "LABEL_GAP",
    "LABEL_OFFSETS",
    "LABEL_POSITIONS",
    "LOOP_SIDES",
    "MAX_LOOPS",
    "OUTWARD",
    "PORT_SPREAD",
    "SEPARATION_PASSES",
    "SIDES",
    "TURN_COST",
    "Connector",
    "Label",
    "Loop",
    "Obstacle",
    "Route",
    "claimed_sides",
    "edge_primitives",
    "end_marker",
    "goes_round",
    "head_room",
    "hollow_base",
    "label_extents",
    "label_primitives",
    "loop_label_size",
    "loop_margin",
    "loop_reach",
    "loop_route",
    "loop_sides",
    "minimum_rank_gap",
    "place_labels",
    "place_loop",
    "route_edges",
    "separate_lanes",
    "shaft_length",
    "straighten",
]
