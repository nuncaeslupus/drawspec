"""The `automaton` kind: a finite automaton as the theory textbooks draw it.

States are circles with their names inside, every circle the size of the widest
name, an accepting state a double circle. The start state is entered by an arrow
coming in from nowhere — no initial dot, which is UML's and the `states` kind's.
Each move is an arrow labelled by the symbol it reads; moves between the same two
states in the same direction are one arrow labelled `a, b`; a move from a state to
itself is a loop on its circle; ε labels an empty move. A Mealy machine writes
`a / 1` on its arrows, a Moore machine `q0 / 1` in its circles.

**Placement is the layered engine's**, read across the page from the start state
(down it when across does not fit). **The arcs are this module's own**: an arrow
is a straight line between two circles when nothing is in its way, and otherwise
a curve (a quadratic Bézier) bowed far enough to clear every circle it does not
belong to. A pair of opposite moves is always two curves, each bowed to the left
of the way it travels, so the two never lie on one another — the convention of
JFLAP, Graphviz's `fsm` and TikZ's `bend left`. A curve is drawn as a polyline,
as every stroke drawspec emits is, finely enough that the eye reads it as a curve.

**Nothing is drawn through anything else.** An arc keeps the edge clearance from
every circle it passes; a loop is put on the side of its circle where it meets
no arrow; the start arrow comes in from whichever side is clear; and each label
is set beside its own arc, at the first place along it where it touches no line,
no circle and no other label. When there is no such place the drawing is refused
with a `FitError`, and the fit retries at a smaller type scale.

The text form is the transition table, the way the textbooks print an automaton:
a row per state, a column per symbol (ε last), `→` marking the start state and
`*` each accepting one.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.layout import LayeredEngine, LayoutEdge, LayoutNode, Spacing, best_layout
from drawspec.routing import Label, Route, edge_primitives, label_primitives
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import AutomatonTransition, Document
from drawspec.text.measure import TextMeasurer
from drawspec.textgrid import (
    Drawn,
    caption_lines,
    cells,
    finished,
    pad,
    spelt,
    widest,
)
from drawspec.theme import Theme

#: The role a state's circle, both rings of an accepting one, and its name are drawn in.
STATE_ROLE: Final = "step"

#: The edge role every move and the start arrow are drawn in.
MOVE_ROLE: Final = "flow"

#: The empty move's label, as every textbook writes it.
EPSILON: Final = "ε"

#: Lengths in units, a unit being the body size over eleven.
NAME_AIR: Final = 5.0
"""The least air between a state's name and its circle (its inner ring, if accepting)."""

MIN_RADIUS: Final = 13.0
"""The smallest a circle is drawn: two letters and a digit, `q10`, with air."""

RING_GAP: Final = 3.5
"""The gap between an accepting state's two rings."""

LABEL_GAP: Final = 3.0
"""The least air between a label and its own arc."""

LABEL_PAD: Final = 2.0

#: How far off its arc a label is tried, in units, nearest first.
LABEL_GAPS: Final = (LABEL_GAP, 2 * LABEL_GAP, 4 * LABEL_GAP, 7 * LABEL_GAP)

#: Where along its arc a label is tried, the middle first.
LABEL_FRACTIONS: Final = (0.5, 0.4, 0.6, 0.3, 0.7, 0.22, 0.78)
LABEL_FALLBACK_FRACTIONS: Final = (
    0.5,
    *(0.5 + sign * step / 20 for step in range(1, 8) for sign in (1, -1)),
)
"""The air a label keeps from any other line, circle or label."""

NEAR: Final = 4.0
"""How close two different strokes may run before they read as one."""

START_REACH: Final = 20.0

LOOP_REACH: Final = 8.0
"""How much farther than its circle's size a loop stands out, so a small circle's
loop is still tall enough to read as a loop rather than a bump."""
"""How far out the start arrow begins, beyond its circle."""

#: How many straight pieces a curve is drawn in.
ARC_STEPS: Final = 28
LOOP_STEPS: Final = 24

#: How far an arc may bow, its apex off the straight line between the two
#: centres as a fraction of that line's length, tried smallest first. Zero is the
#: straight line; a pair of opposite moves starts at the first non-zero bow.
BOWS: Final = (0.0, 0.16, 0.26, 0.38, 0.52, 0.7, 0.92, 1.2, 1.55, 2.0)

#: Which way a loop may stand off its circle, in degrees (y grows downward, so
#: -90 is up), in the order tried: above and below first, as the textbooks draw
#: them, since the arrows of a left-to-right machine leave by the sides.
LOOP_ANGLES: Final = (-90.0, 90.0, -135.0, -45.0, 135.0, 45.0, 180.0, 0.0)

#: Every sixteenth of a turn, for a loop the first choices leave no room for.
LOOP_FALLBACK_ANGLES: Final = tuple(-180.0 + 22.5 * step for step in range(16))

#: The least angle, in degrees, between the start arrow and an arc meeting the start
#: state; and how far either side of the line between two states a pair of opposite
#: arcs is expected to meet them.
START_SPACE: Final = 18.0
PAIR_SPREAD: Final = 20.0

#: How much farther apart than the textbook's spacing the states are spread, in
#: turn, when a stroke or a label finds no clear place at the one before.
SPREADS: Final = (1.0, 1.35, 1.8)

#: Past this many radii between two centres, an arc's detour is measured against
#: this width rather than its own length: a long arc bowed in proportion would swing
#: across the page.
REACH_SCALE: Final = 6.0

#: What one crossing of another arc is worth, against a detour of that depth.
CROSSING_COST: Final = 0.25

#: How far a bracket's ends lean toward each other, as a share of how far it stands
#: out: square first, then aslant.
BRACKET_SKEWS: Final = (0.0, 0.8, -0.6)

#: How far a bracket stands out to the side, in circle radii, tried nearest first.
BRACKETS: Final = (2.5, 3.5, 4.5, 6.0, 8.0)

#: Half the angle between a loop's two feet on its circle, in degrees, and the
#: least angle kept between a foot and any other arrow meeting that circle.
LOOP_SPREAD: Final = 28.0
LOOP_SPACE: Final = 14.0

#: Which way the start arrow may come in from, per direction the machine reads.
START_ANGLES: Final[Mapping[str, tuple[float, ...]]] = {
    "right": (180.0, -135.0, 135.0, -90.0, 90.0, -45.0, 45.0, 0.0),
    "down": (-90.0, -135.0, -45.0, 180.0, 0.0, 135.0, 45.0, 90.0),
}

Point = tuple[float, float]


@dataclass(frozen=True)
class Circle:
    """One state, placed: its centre, radius, name and whether it accepts."""

    id: str
    cx: float
    cy: float
    r: float
    name: str
    accepting: bool = False
    start: bool = False

    @property
    def centre(self) -> Point:
        return (self.cx, self.cy)


@dataclass(frozen=True)
class Arc:
    """One drawn arrow: a merged move between two states, or a loop on one."""

    source: str
    target: str
    label: str
    points: tuple[Point, ...]
    bow: float = 0.0
    """The apex's offset as a fraction of the centres' distance, signed: positive
    is to the left of the way the arc travels. Zero is straight; a loop has none."""

    angle: float = 0.0
    """A loop's direction off its circle, in degrees; unused on an arc."""

    paired: bool = False
    """Whether a move runs the other way between the same two states: then the two
    arcs bow apart, and each label stands on its own arc's outer side."""

    @property
    def loop(self) -> bool:
        return self.source == self.target


@dataclass(frozen=True)
class AutomatonDrawing:
    """Everything an automaton is made of, in scene coordinates.

    A value of its own so a test can ask where each circle, arc and label went —
    and that none of them meets another — without reading the primitives.
    """

    circles: Mapping[str, Circle]
    arcs: tuple[Arc, ...]
    start: tuple[Point, Point]
    """The start arrow: where it begins, out in the open, and its tip on the circle."""

    labels: tuple[Label, ...]
    """One per arc, in the order of `arcs`."""

    heads: tuple[tuple[Point, ...], ...]
    """Every arrow head's outline, the start arrow's last: what a label must miss too."""

    width: float
    height: float
    direction: str


# ---------------------------------------------------------------------------
# The moves, merged
# ---------------------------------------------------------------------------


def move_label(move: AutomatonTransition) -> str:
    """One move as its arrow says it: `a`, `ε`, `a / 1`."""
    read = EPSILON if move.epsilon else move.symbol
    return f"{read} / {move.output}" if move.output else read


def merged(moves: Sequence[AutomatonTransition]) -> list[tuple[str, str, str]]:
    """The arrows to draw: one per ordered pair of states, its moves' labels joined.

    In the order each pair first appears; within a pair, in the order written.
    """
    pairs: dict[tuple[str, str], list[str]] = {}
    for move in moves:
        pairs.setdefault((move.source, move.target), []).append(move_label(move))
    return [(source, target, ", ".join(words)) for (source, target), words in pairs.items()]


def state_name(text: str, output: str) -> str:
    """A state's name as its circle says it: `q0`, or a Moore machine's `q0 / 1`."""
    return f"{text} / {output}" if output else text


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------


def automaton_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render an `automaton` document to a `Scene`.

    Raises:
        FitError: the machine does not fit the canvas across or down at this type
            scale, or an arc or a label finds no place clear of everything else.
    """
    drawing = automaton_drawing(document, theme, measurer)
    body = measurer.measure("", theme.font.default, theme.scale["body"])
    primitives: list[Primitive] = []
    for arc in drawing.arcs:
        primitives.extend(
            edge_primitives(Route(arc.source, arc.target, MOVE_ROLE, arc.points), theme)
        )
    primitives.extend(
        edge_primitives(Route("", "", MOVE_ROLE, drawing.start), theme)  # from nowhere
    )
    gap = RING_GAP * theme.scale["body"] / 11
    for circle in drawing.circles.values():
        primitives.append(Ellipse(STATE_ROLE, cx=circle.cx, cy=circle.cy, rx=circle.r, ry=circle.r))
        if circle.accepting:
            inner = circle.r - gap
            primitives.append(Ellipse(STATE_ROLE, cx=circle.cx, cy=circle.cy, rx=inner, ry=inner))
        primitives.append(
            TextLine(
                STATE_ROLE,
                x=circle.cx,
                y=circle.cy + (body.ascent - body.descent) / 2,
                spans=(TextSpan(text=circle.name, font=theme.font.default),),
                level="body",
                anchor="middle",
            )
        )
    for label in drawing.labels:
        primitives.extend(label_primitives(label))
    return Scene(
        width=drawing.width,
        height=drawing.height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("direction", drawing.direction),),
    )


def automaton_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> AutomatonDrawing:
    """Size and place every state, then the arcs, the start arrow, the loops, the labels."""
    states = document.automaton_states
    if not states:
        raise DrawspecError("an automaton needs at least one state")
    unit = theme.scale["body"] / 11
    body = theme.scale["body"]
    sans = theme.font.default
    accepting = set(document.automaton_accepting)
    names = {state.id: state_name(state.text, state.output) for state in states}
    line = measurer.measure("", sans, body)
    half_height = (line.ascent + line.descent) / 2
    ring = RING_GAP * unit if accepting else 0.0
    radius = max(
        MIN_RADIUS * unit,
        *(
            math.hypot(measurer.measure(name, sans, body).width / 2, half_height)
            + NAME_AIR * unit
            + ring
            for name in names.values()
        ),
    )
    arrows = merged(document.automaton_transitions)
    small = theme.scale["label"]
    sizes = {words: _label_size(words, theme, measurer) for _, _, words in arrows}
    widest_label = max((width for width, _ in sizes.values()), default=0.0)
    label_height = max((height for _, height in sizes.values()), default=small)

    order = [document.automaton_start] + [
        state.id for state in states if state.id != document.automaton_start
    ]
    boxes = [LayoutNode(identifier, 2 * radius, 2 * radius) for identifier in order]
    links = [LayoutEdge(source, target) for source, target, _ in arrows if source != target]
    width = document.width if document.width else theme.canvas.width
    ceiling = (document.height or 0.0) if document.height_binding else 0.0
    room = label_height + 2 * (LABEL_GAP + LABEL_PAD) * unit + theme.edge.stroke_width
    refusal: FitError | None = None
    # Placed at the textbook's spacing first; when an arc, a loop or a label finds
    # no clear place, the states are spread farther apart and everything placed
    # again — more room is what each of those refusals asks for.
    for spread in SPREADS:
        spacing = Spacing(
            node_gap=spread
            * (max(radius * 2.2, 2 * label_height + 2 * LABEL_GAP * unit) + 2 * LABEL_GAP * unit),
            rank_gap=spread
            * max(
                radius * 2.4,
                widest_label + 4 * LABEL_GAP * unit + theme.head_length_for(MOVE_ROLE),
            ),
        )
        layout = best_layout(
            LayeredEngine(spacing),
            boxes,
            links,
            max_width=width,
            prefer="right",
            max_height=ceiling,
        )
        if not layout.fits:
            raise refusal or FitError(
                f"this automaton needs {layout.width:.0f} at its narrowest and the canvas is "
                f"{width:.0f}; it was tried across the page and down it. Shorten the state "
                f"names and symbols, give the document more `width`, or minimise the machine."
            )
        circles = {
            identifier: Circle(
                id=identifier,
                cx=place.x + place.width / 2,
                cy=place.y + place.height / 2,
                r=radius,
                name=names[identifier],
                accepting=identifier in accepting,
                start=identifier == document.automaton_start,
            )
            for identifier, place in layout.placements.items()
        }
        direction = layout.direction if layout.direction in START_ANGLES else "right"
        try:
            return _placed(document, arrows, circles, sizes, room, direction, theme, measurer)
        except FitError as error:
            refusal = error
    assert refusal is not None
    raise refusal


def _placed(
    document: Document,
    arrows: Sequence[tuple[str, str, str]],
    circles: Mapping[str, Circle],
    sizes: Mapping[str, tuple[float, float]],
    room: float,
    direction: str,
    theme: Theme,
    measurer: TextMeasurer,
) -> AutomatonDrawing:
    """Every stroke and label placed round circles already placed.

    Loops and the start arrow go first, at the sides of their circles the arrows
    are not expected to use; the arrows then curve round them, and land clear of
    their feet. Placed the other way round, a busy state's loop finds every side
    taken.

    Raises:
        FitError: an arc, a loop, the start arrow or a label finds no clear place.
    """
    scene = _Placer(circles, theme, theme.scale["body"] / 11, measurer)
    scene.room = room
    landings = scene.expected_landings(arrows)
    scene.place_loops(
        [(source, words) for source, target, words in arrows if source == target],
        sizes,
        landings,
    )
    scene.place_start(document.automaton_start, direction, landings[document.automaton_start])
    scene.place_arcs([(source, target, words) for source, target, words in arrows])
    scene.place_labels(sizes)
    return scene.framed(direction)


def _label_size(words: str, theme: Theme, measurer: TextMeasurer) -> tuple[float, float]:
    extent = measurer.measure(words, theme.font.default, theme.scale["label"])
    return extent.width, extent.ascent + extent.descent


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _segment_distance(point: Point, start: Point, end: Point) -> float:
    """How far `point` is from the segment `start`-`end`."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    span = dx * dx + dy * dy
    if span == 0:
        return math.dist(point, start)
    along = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / span))
    return math.dist(point, (start[0] + along * dx, start[1] + along * dy))


def _polyline_distance(point: Point, points: Sequence[Point]) -> float:
    if len(points) == 1:
        return math.dist(point, points[0])
    return min(_segment_distance(point, a, b) for a, b in itertools.pairwise(points))


Bounds = tuple[float, float, float, float]


def _bounds(points: Sequence[Point]) -> Bounds:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _apart(first: Bounds, second: Bounds, gap: float) -> bool:
    """Whether two bounding boxes are at least `gap` apart on some axis."""
    return (
        first[0] - second[2] >= gap
        or second[0] - first[2] >= gap
        or first[1] - second[3] >= gap
        or second[1] - first[3] >= gap
    )


def _within(point: Point, points: Sequence[Point], limit: float) -> bool:
    """Whether `point` is nearer than `limit` to the polyline `points`.

    Each segment's own bounding box is checked first, so a long curve far from the
    point costs a comparison per piece rather than a projection.
    """
    x, y = point
    for a, b in itertools.pairwise(points):
        if (
            x < min(a[0], b[0]) - limit
            or x > max(a[0], b[0]) + limit
            or y < min(a[1], b[1]) - limit
            or y > max(a[1], b[1]) + limit
        ):
            continue
        if _segment_distance(point, a, b) < limit:
            return True
    return False


def _pieces_near(
    stroke: Sequence[Point], bounds: Bounds, limit: float
) -> list[tuple[Point, Point]]:
    """The segments of `stroke` within `limit` of the box `bounds`."""
    return [(a, b) for a, b in pairwise(stroke) if not _apart(bounds, _bounds((a, b)), limit)]


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Whether two segments properly cross (touching at an end does not count)."""
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    return d1 * d2 < 0 and d3 * d4 < 0


def _crossings(first: Sequence[Point], second: Sequence[Point]) -> int:
    """How many times two polylines cross."""
    if _apart(_bounds(first), _bounds(second), 0.0):
        return 0
    found = 0
    others = [(c, d, _bounds((c, d))) for c, d in itertools.pairwise(second)]
    for a, b in itertools.pairwise(first):
        piece = _bounds((a, b))
        for c, d, bounds in others:
            if not _apart(piece, bounds, 0.0) and _segments_cross(a, b, c, d):
                found += 1
    return found


def _segment_meets_box(start: Point, end: Point, box: tuple[float, float, float, float]) -> bool:
    """Whether a segment touches a rectangle (left, top, right, bottom): Liang-Barsky."""
    left, top, right, bottom = box
    dx, dy = end[0] - start[0], end[1] - start[1]
    low, high = 0.0, 1.0
    for p, q in (
        (-dx, start[0] - left),
        (dx, right - start[0]),
        (-dy, start[1] - top),
        (dy, bottom - start[1]),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return True


def _box_circle_distance(box: tuple[float, float, float, float], centre: Point) -> float:
    left, top, right, bottom = box
    nearest = (min(max(centre[0], left), right), min(max(centre[1], top), bottom))
    return math.dist(nearest, centre)


def _quadratic(start: Point, control: Point, end: Point, steps: int) -> list[Point]:
    out: list[Point] = []
    for index in range(steps + 1):
        t = index / steps
        u = 1 - t
        out.append(
            (
                u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
                u * u * start[1] + 2 * u * t * control[1] + t * t * end[1],
            )
        )
    return out


def _cubic(points: Sequence[Point], steps: int) -> list[Point]:
    p0, p1, p2, p3 = points
    out: list[Point] = []
    for index in range(steps + 1):
        t = index / steps
        u = 1 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append(
            (
                a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
            )
        )
    return out


def _boundary(inside: Point, outside: Point, centre: Point, r: float) -> Point:
    """Where the segment from a point inside a circle to one outside it crosses it."""
    low, high = 0.0, 1.0
    for _ in range(30):
        middle = (low + high) / 2
        point = (
            inside[0] + (outside[0] - inside[0]) * middle,
            inside[1] + (outside[1] - inside[1]) * middle,
        )
        if math.dist(point, centre) <= r:
            low = middle
        else:
            high = middle
    return (
        round(inside[0] + (outside[0] - inside[0]) * high, 3),
        round(inside[1] + (outside[1] - inside[1]) * high, 3),
    )


def _trimmed(points: Sequence[Point], source: Circle, target: Circle) -> tuple[Point, ...] | None:
    """A curve from centre to centre cut to the part between the two circles.

    None when the part between them goes back into either — a bow so deep the
    curve wraps round its own end.
    """
    leave = next(
        (index for index, point in enumerate(points) if math.dist(point, source.centre) > source.r),
        None,
    )
    arrive = next(
        (
            index
            for index in range(len(points) - 1, -1, -1)
            if math.dist(points[index], target.centre) > target.r
        ),
        None,
    )
    if leave is None or arrive is None or arrive < leave:
        return None
    middle = list(points[leave : arrive + 1])
    for point in middle:
        if (
            math.dist(point, source.centre) <= source.r
            or math.dist(point, target.centre) <= target.r
        ):
            return None
    first = _boundary(points[leave - 1], points[leave], source.centre, source.r)
    last = _boundary(points[arrive + 1], points[arrive], target.centre, target.r)
    return (first, *middle, last)


def _angle_between(first: float, second: float) -> float:
    """The smaller angle between two directions, in degrees: 0 to 180."""
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _direction(angle: float) -> Point:
    radians = math.radians(angle)
    return (math.cos(radians), math.sin(radians))


# ---------------------------------------------------------------------------
# Placing the strokes and the words
# ---------------------------------------------------------------------------


class _Placer:
    """Puts each stroke and label where it meets nothing it does not belong to."""

    def __init__(
        self, circles: Mapping[str, Circle], theme: Theme, unit: float, measurer: TextMeasurer
    ) -> None:
        self.circles = dict(circles)
        self.ascent = measurer.measure("", theme.font.default, theme.scale["label"]).ascent
        self.theme = theme
        self.unit = unit
        self.clearance = theme.edge.clearance
        self.arcs: list[Arc] = []
        self.start: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))
        self.labels: dict[int, Label] = {}
        self.room = 0.0
        """The gap two arcs need for a label to stand between them."""
        self._head_cache: tuple[tuple[int, tuple[Point, Point]], list[tuple[Point, ...]]] | None = (
            None
        )

    # -- arcs between two states ------------------------------------------

    def place_arcs(self, arrows: Sequence[tuple[str, str, str]]) -> None:
        pairs = {(source, target) for source, target, _ in arrows}
        between = [(source, target, words) for source, target, words in arrows if source != target]
        # The shortest first: they have the fewest ways round, and the long ones
        # then bow round what the short ones already hold.
        between.sort(
            key=lambda arrow: math.dist(
                self.circles[arrow[0]].centre, self.circles[arrow[1]].centre
            )
        )
        for source, target, words in between:
            self.arcs.append(self._arc(source, target, words, (target, source) in pairs))

    def _arc(self, source: str, target: str, words: str, paired: bool) -> Arc:
        here, there = self.circles[source], self.circles[target]
        length = math.dist(here.centre, there.centre)
        tx, ty = (there.cx - here.cx) / length, (there.cy - here.cy) / length
        left = (ty, -tx)
        best: tuple[float, Arc] | None = None
        # A bow is a quadratic curve; a bracket is a cubic that leaves both circles
        # sideways and runs beside the states between them, which is what clears a
        # long column of circles without a detour across the page. Each is costed
        # by how far it strays from the straight line — measured against the line
        # itself for a short arc, against a few circles' width for a long one — and
        # they are tried least first.
        scale = min(length, REACH_SCALE * here.r)
        steps = max(ARC_STEPS, min(round(length / (5 * self.unit)), 3 * ARC_STEPS))
        shapes = sorted(
            [
                *((bow * length / scale, bow, False) for bow in BOWS),
                *((0.75 * bow * here.r / scale, bow, True) for bow in BRACKETS),
            ]
        )
        for depth, bow, bracket in shapes:
            if best is not None and best[0] <= depth:
                break
            for skew in BRACKET_SKEWS if bracket else (0.0,):
                for sign in (1.0, -1.0):
                    if (bow == 0 and sign < 0) or (paired and bow == 0):
                        continue
                    if bracket:
                        side = sign * bow * here.r
                        # A skewed bracket leaves and arrives aslant rather than square,
                        # so it meets a circle away from arcs that came in from the side.
                        ahead = skew * bow * here.r
                        curve = _cubic(
                            (
                                here.centre,
                                (
                                    here.cx + left[0] * side + tx * ahead,
                                    here.cy + left[1] * side + ty * ahead,
                                ),
                                (
                                    there.cx + left[0] * side - tx * ahead,
                                    there.cy + left[1] * side - ty * ahead,
                                ),
                                there.centre,
                            ),
                            steps + 12,
                        )
                    else:
                        offset = 2 * sign * bow * length
                        control = (
                            (here.cx + there.cx) / 2 + left[0] * offset,
                            (here.cy + there.cy) / 2 + left[1] * offset,
                        )
                        curve = _quadratic(here.centre, control, there.centre, steps)
                    points = _trimmed(curve, here, there)
                    if points is None or not self._clear_of_circles(points, {source, target}):
                        continue
                    if not (self._lands(here, points[0]) and self._lands(there, points[-1])):
                        continue
                    if any(_crossings(points, arc.points) for arc in self.arcs if arc.loop):
                        continue
                    if _crossings(points, self.start) or self._meets_labels(points):
                        continue
                    if self._runs_along(points, {source, target}):
                        continue
                    crossings = sum(_crossings(points, arc.points) for arc in self.arcs)
                    # The other way is a fallback: for a pair it nests the two arcs on one side.
                    cost = (
                        depth
                        + CROSSING_COST * crossings
                        + ((0.5 if paired else 0.04) if sign < 0 else 0.0)
                    )
                    if self._crowds(points, (here, there)):
                        # Too close to another arc for a label to stand between them.
                        cost += 0.6
                    if best is None or cost < best[0]:
                        best = (
                            cost,
                            Arc(source, target, words, points, bow=sign * depth, paired=paired),
                        )
        if best is None:
            raise FitError(
                f"the move from {source!r} to {target!r} finds no way round the other states. "
                f"Give the document more `width`, or minimise the machine."
            )
        return best[1]

    def _lands(self, circle: Circle, point: Point) -> bool:
        """Whether an arc may meet `circle` at `point`: clear of a loop's feet and of
        the start arrow's tip, so no two strokes meet the ring at one place."""
        angle = math.degrees(math.atan2(point[1] - circle.cy, point[0] - circle.cx))
        if any(
            arc.loop
            and arc.source == circle.id
            and _angle_between(angle, arc.angle) < LOOP_SPREAD + LOOP_SPACE / 2
            for arc in self.arcs
        ):
            return False
        if circle.start and self.start[0] != self.start[1]:
            tip = self.start[1]
            entry = math.degrees(math.atan2(tip[1] - circle.cy, tip[0] - circle.cx))
            if _angle_between(angle, entry) < START_SPACE:
                return False
        return True

    def _meets_labels(self, points: Sequence[Point]) -> bool:
        """Whether a stroke touches a label already placed (a loop's), with its air."""
        pad_ = LABEL_PAD * self.unit + self.theme.edge.stroke_width
        for label in self.labels.values():
            left, top, right, bottom = label.box
            box = (left - pad_, top - pad_, right + pad_, bottom + pad_)
            if _apart(_bounds(points), box, 0.0):
                continue
            if any(_segment_meets_box(a, b, box) for a, b in itertools.pairwise(points)):
                return True
        return False

    def _crowds(self, points: Sequence[Point], own: Sequence[Circle]) -> bool:
        """Whether a stroke, away from its own circles, runs nearer another arc than a
        label is tall — so that neither could carry a label on that side."""
        middle = [
            point
            for point in points
            if all(math.dist(point, circle.centre) > circle.r + self.room for circle in own)
        ]
        if not middle:
            return False
        bounds = _bounds(middle)
        return any(
            _within(point, arc.points, self.room)
            for arc in self.arcs
            if not _apart(bounds, _bounds(arc.points), self.room)
            for point in middle
        )

    def _clear_of_circles(self, points: Sequence[Point], own: set[str]) -> bool:
        bounds = _bounds(points)
        for circle in self.circles.values():
            if circle.id in own:
                continue
            reach = circle.r + self.clearance
            box = (circle.cx, circle.cy, circle.cx, circle.cy)
            if not _apart(bounds, box, reach) and _within(circle.centre, points, reach):
                return False
        return True

    def _runs_along(self, points: Sequence[Point], own: set[str]) -> bool:
        """Whether a stroke runs along one already drawn, away from the circles they share."""
        near = NEAR * self.unit
        ends = [self.circles[identifier] for identifier in own]
        strokes = [arc.points for arc in self.arcs]
        if self.start[0] != self.start[1]:
            strokes.append(self.start)
        bounds = _bounds(points)
        # A run is measured as a length, not a count of points, so a long curve
        # sampled finely is held to the same rule as a short one.
        spacing = sum(math.dist(a, b) for a, b in pairwise(points)) / max(len(points) - 1, 1)
        enough = max(2, math.ceil(2 * near / max(spacing, 1e-9)))
        for stroke in strokes:
            if _apart(bounds, _bounds(stroke), near):
                continue
            # Only the pieces of the stroke near this one can be run along.
            nearby = _pieces_near(stroke, bounds, near)
            if not nearby:
                continue
            run = 0
            for point in points:
                if any(math.dist(point, end.centre) < end.r + 3 * near for end in ends):
                    run = 0
                    continue
                if any(_within(point, piece, near) for piece in nearby):
                    run += 1
                    if run >= enough:
                        return True
                else:
                    run = 0
        return False

    # -- the start arrow ---------------------------------------------------

    def place_start(self, identifier: str, direction: str, landings: Sequence[float]) -> None:
        """The arrow from nowhere into the start state, from the side the machine reads
        from when that is clear — of the loops, and of where its arrows will land."""
        circle = self.circles[identifier]
        reach = max(START_REACH * self.unit, circle.r)
        angles = [
            angle
            for angle in START_ANGLES[direction]
            if all(_angle_between(angle, landing) >= 2 * START_SPACE for landing in landings)
        ]
        angles += [angle for angle in LOOP_FALLBACK_ANGLES if angle not in angles]
        for angle in angles:
            if any(
                arc.loop
                and arc.source == identifier
                and _angle_between(angle, arc.angle) < LOOP_SPREAD + START_SPACE
                for arc in self.arcs
            ):
                continue
            dx, dy = _direction(angle)
            tail = (circle.cx + dx * (circle.r + reach), circle.cy + dy * (circle.r + reach))
            tip = (round(circle.cx + dx * circle.r, 3), round(circle.cy + dy * circle.r, 3))
            segment = (tail, tip)
            if not self._clear_of_circles(segment, {identifier}):
                continue
            if any(_crossings(segment, arc.points) for arc in self.arcs):
                continue
            if self._meets_labels(segment):
                continue
            if self._runs_along(_sampled(segment, self.unit), {identifier}):
                continue
            self.start = segment
            return
        raise FitError(
            f"the start state {identifier!r} has arrows on every side, and no room for the "
            f"arrow that marks it. Give the document more `width`."
        )

    # -- loops ---------------------------------------------------------------

    def expected_landings(self, arrows: Sequence[tuple[str, str, str]]) -> dict[str, list[float]]:
        """Per state, the angles its arrows are expected to meet it at, before any is drawn.

        Straight toward the other state; a pair of opposite moves either side of that.
        """
        pairs = {(source, target) for source, target, _ in arrows}
        found: dict[str, list[float]] = {identifier: [] for identifier in self.circles}
        for source, target, _ in arrows:
            if source == target:
                continue
            here, there = self.circles[source], self.circles[target]
            out = math.degrees(math.atan2(there.cy - here.cy, there.cx - here.cx))
            back = out + 180.0
            if (target, source) in pairs:
                # Bowed to the left of travel: it leaves left of the line, arrives right.
                found[source].append(out - PAIR_SPREAD)
                found[target].append(back + PAIR_SPREAD)
            else:
                found[source].append(out)
                found[target].append(back)
        return found

    def place_loops(
        self,
        loops: Sequence[tuple[str, str]],
        sizes: Mapping[str, tuple[float, float]],
        expected: Mapping[str, Sequence[float]],
    ) -> None:
        # The textbook places first; then every sixteenth of a turn, the feet allowed
        # nearer the arrows; and last, a loop may cross an arrow passing by — never
        # run along one, meet a circle or touch a word.
        tries = (
            (LOOP_ANGLES, LOOP_SPACE, False),
            (LOOP_FALLBACK_ANGLES, LOOP_SPACE / 2, False),
            (LOOP_FALLBACK_ANGLES, LOOP_SPACE / 2, True),
        )
        for identifier, words in loops:
            circle = self.circles[identifier]
            landings = [*expected[identifier], *self._landings(circle)]
            placed = False
            for angles, space, crossing in tries:
                for angle in angles:
                    if any(
                        _angle_between(landing, angle) < LOOP_SPREAD + space for landing in landings
                    ):
                        # An arrow meets the circle between the loop's feet, or beside one.
                        continue
                    points = self._loop(circle, angle)
                    if not self._clear_of_circles(points, {identifier}):
                        continue
                    if not crossing and any(_crossings(points, arc.points) for arc in self.arcs):
                        continue
                    if _crossings(points, self.start):
                        continue
                    if self._runs_along(points, {identifier}):
                        continue
                    arc = Arc(identifier, identifier, words, points, angle=angle)
                    label = self._loop_label(arc, sizes[words])
                    if label is None:
                        continue
                    self.arcs.append(arc)
                    self.labels[len(self.arcs) - 1] = label
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                raise FitError(
                    f"the loop on {identifier!r} finds no side of its circle clear of the "
                    f"arrows there. Give the document more `width`."
                )

    def _landings(self, circle: Circle) -> list[float]:
        """The angles, in degrees, at which strokes already drawn meet `circle`."""
        ends: list[Point] = []
        for arc in self.arcs:
            if arc.source == circle.id:
                ends.append(arc.points[0])
            if arc.target == circle.id:
                ends.append(arc.points[-1])
        if circle.start:
            ends.append(self.start[1])
        return [math.degrees(math.atan2(y - circle.cy, x - circle.cx)) for x, y in ends]

    def _loop(self, circle: Circle, angle: float) -> tuple[Point, ...]:
        """A loop standing off `circle` at `angle`: out at one side, back at the other."""
        spread, flare = LOOP_SPREAD, 40.0
        reach = circle.r * 1.9 + LOOP_REACH * self.unit
        start = _direction(angle - spread)
        end = _direction(angle + spread)
        p0 = (circle.cx + start[0] * circle.r, circle.cy + start[1] * circle.r)
        p3 = (circle.cx + end[0] * circle.r, circle.cy + end[1] * circle.r)
        out = _direction(angle - flare)
        back = _direction(angle + flare)
        p1 = (circle.cx + out[0] * (circle.r + reach), circle.cy + out[1] * (circle.r + reach))
        p2 = (circle.cx + back[0] * (circle.r + reach), circle.cy + back[1] * (circle.r + reach))
        points = _cubic((p0, p1, p2, p3), LOOP_STEPS)
        return tuple((round(x, 3), round(y, 3)) for x, y in points)

    def _loop_label(self, arc: Arc, size: tuple[float, float]) -> Label | None:
        circle = self.circles[arc.source]
        dx, dy = _direction(arc.angle)
        apex = max(arc.points, key=lambda point: math.dist(point, circle.centre))
        for gap in (LABEL_GAP, 2 * LABEL_GAP, 4 * LABEL_GAP):
            for slide in (0.0, 0.5, -0.5, 1.0, -1.0):
                normal = (dx, dy)
                across = (-dy, dx)
                support = abs(normal[0]) * size[0] / 2 + abs(normal[1]) * size[1] / 2
                distance = gap * self.unit + support
                along = slide * size[0] / 2
                centre = (
                    apex[0] + normal[0] * distance + across[0] * along,
                    apex[1] + normal[1] * distance + across[1] * along,
                )
                label = self._label_at(arc.label, centre, size)
                if self._label_clear(label, len(self.arcs), arc.points):
                    return label
        return None

    # -- labels --------------------------------------------------------------

    def place_labels(self, sizes: Mapping[str, tuple[float, float]]) -> None:
        for index, arc in enumerate(self.arcs):
            if index in self.labels:
                continue
            label = self._arc_label(index, arc, sizes[arc.label], strict=True)
            if label is None:
                label = self._arc_label(index, arc, sizes[arc.label], strict=False)
            if label is None:
                raise FitError(
                    f"the label {arc.label!r} on the move from {arc.source!r} to "
                    f"{arc.target!r} finds no place beside its arrow clear of every other "
                    f"line. Give the document more `width`, or shorten the symbols."
                )
            self.labels[index] = label

    def _arc_label(
        self, index: int, arc: Arc, size: tuple[float, float], *, strict: bool
    ) -> Label | None:
        """The first clear place beside `arc` for its label, or None.

        Strictly: on the outer side of a pair of opposite arcs, and nearer its own arc
        than any other. Failing that, hugging its own arc — never more than two gaps
        off it, so it still reads as that arc's — on either side, anywhere along it.
        """
        points = arc.points
        count = len(points) - 1
        gaps = LABEL_GAPS if strict else LABEL_GAPS[:2]
        fractions = LABEL_FRACTIONS if strict else LABEL_FALLBACK_FRACTIONS
        if not strict:
            sides: tuple[float, ...] = (1.0, -1.0)
        elif arc.paired:
            # Between two opposite arcs a label belongs to neither: keep it outside.
            sides = (1.0 if arc.bow > 0 else -1.0,)
        elif arc.bow > 0:
            sides = (1.0, -1.0)
        elif arc.bow < 0:
            sides = (-1.0, 1.0)
        else:
            sides = (1.0, -1.0)
        for gap in gaps:
            for fraction in fractions:
                at = min(max(round(fraction * count), 1), count - 1) if count > 1 else 0
                before, after = points[max(at - 1, 0)], points[min(at + 1, count)]
                span = math.dist(before, after) or 1.0
                tangent = ((after[0] - before[0]) / span, (after[1] - before[1]) / span)
                left = (tangent[1], -tangent[0])
                if arc.bow == 0 and (left[1] > 1e-9 or (abs(left[1]) <= 1e-9 and left[0] < 0)):
                    # A straight arc's first choice is above it, or right of it upright.
                    left = (-left[0], -left[1])
                for side in sides:
                    normal = (left[0] * side, left[1] * side)
                    support = abs(normal[0]) * size[0] / 2 + abs(normal[1]) * size[1] / 2
                    distance = gap * self.unit + support
                    centre = (
                        points[at][0] + normal[0] * distance,
                        points[at][1] + normal[1] * distance,
                    )
                    label = self._label_at(arc.label, centre, size)
                    if self._label_clear(label, index, nearest=strict):
                        return label
        return None

    def _label_at(self, words: str, centre: Point, size: tuple[float, float]) -> Label:
        return Label(
            text=words,
            role=MOVE_ROLE,
            left=round(centre[0] - size[0] / 2, 3),
            top=round(centre[1] - size[1] / 2, 3),
            width=size[0],
            height=size[1],
            ascent=self.ascent,
            font=self.theme.font.default,
        )

    def _label_clear(
        self,
        label: Label,
        own: int,
        pending: tuple[Point, ...] | None = None,
        *,
        nearest: bool = True,
    ) -> bool:
        """Whether `label` touches nothing, and is nearer its own arc than any other.

        `pending` is the arc the label belongs to when that arc is not yet among
        `arcs` (a loop is kept only once its label has a place).
        """
        # The emitter breaks any stroke that comes within its clearance of a word;
        # keeping farther than that, and half a stroke, means nothing is broken.
        pad_ = LABEL_PAD * self.unit + self.theme.edge.stroke_width
        left, top, right, bottom = label.box
        box = (left - pad_, top - pad_, right + pad_, bottom + pad_)
        for circle in self.circles.values():
            if _box_circle_distance(box, circle.centre) < circle.r + pad_:
                return False
        strokes = [arc.points for arc in self.arcs]
        mine = pending if pending is not None else self.arcs[own].points
        centre = (left + label.width / 2, top + label.height / 2)
        mine_distance = _polyline_distance(centre, mine)
        if nearest and any(
            _polyline_distance(centre, stroke) < mine_distance
            for index, stroke in enumerate(strokes)
            if pending is not None or index != own
        ):
            return False
        if pending is not None:
            strokes.append(pending)
        strokes.append(self.start)
        strokes.extend(self._heads())
        for stroke in strokes:
            for a, b in itertools.pairwise(stroke):
                if _segment_meets_box(a, b, box):
                    return False
        for index, other in self.labels.items():
            if index == own:
                continue
            o_left, o_top, o_right, o_bottom = other.box
            if o_left < box[2] and box[0] < o_right and o_top < box[3] and box[1] < o_bottom:
                return False
        return True

    def _heads(self) -> list[tuple[Point, ...]]:
        """Every arrow head's outline, closed; remembered until an arc is added."""
        key = (len(self.arcs), self.start)
        if self._head_cache is not None and self._head_cache[0] == key:
            return self._head_cache[1]
        heads = self._drawn_heads()
        self._head_cache = (key, heads)
        return heads

    def _drawn_heads(self) -> list[tuple[Point, ...]]:
        heads: list[tuple[Point, ...]] = []
        routes = [arc.points for arc in self.arcs]
        if self.start[0] != self.start[1]:
            routes.append(self.start)
        for points in routes:
            for primitive in edge_primitives(Route("", "", MOVE_ROLE, points), self.theme):
                if isinstance(primitive, Polygon) or (
                    isinstance(primitive, Path) and primitive.marker
                ):
                    heads.append((*primitive.points, primitive.points[0]))
        return heads

    # -- the frame -----------------------------------------------------------

    def framed(self, direction: str) -> AutomatonDrawing:
        heads = self._heads()
        xs: list[float] = []
        ys: list[float] = []
        for circle in self.circles.values():
            xs += [circle.cx - circle.r, circle.cx + circle.r]
            ys += [circle.cy - circle.r, circle.cy + circle.r]
        for stroke in [*(arc.points for arc in self.arcs), self.start, *heads]:
            xs += [x for x, _ in stroke]
            ys += [y for _, y in stroke]
        for label in self.labels.values():
            left, top, right, bottom = label.box
            xs += [left, right]
            ys += [top, bottom]
        dx, dy = -min(xs), -min(ys)

        def moved(point: Point) -> Point:
            return (round(point[0] + dx, 3), round(point[1] + dy, 3))

        return AutomatonDrawing(
            circles={
                identifier: replace(circle, cx=circle.cx + dx, cy=circle.cy + dy)
                for identifier, circle in self.circles.items()
            },
            arcs=tuple(
                replace(arc, points=tuple(moved(point) for point in arc.points))
                for arc in self.arcs
            ),
            start=(moved(self.start[0]), moved(self.start[1])),
            labels=tuple(
                replace(
                    self.labels[index],
                    left=self.labels[index].left + dx,
                    top=self.labels[index].top + dy,
                )
                for index in range(len(self.arcs))
            ),
            heads=tuple(tuple(moved(point) for point in head) for head in heads),
            width=max(xs) + dx,
            height=max(ys) + dy,
            direction=direction,
        )


def _sampled(segment: tuple[Point, Point], unit: float) -> list[Point]:
    """Points along a straight segment, a couple of units apart."""
    start, end = segment
    steps = max(int(math.dist(start, end) / (2 * unit)), 1)
    return [
        (
            start[0] + (end[0] - start[0]) * index / steps,
            start[1] + (end[1] - start[1]) * index / steps,
        )
        for index in range(steps + 1)
    ]


# ---------------------------------------------------------------------------
# Text: the transition table
# ---------------------------------------------------------------------------

#: The marks in the table's first column, per charset: the start state, an accepting one.
TEXT_MARKS: Final[Mapping[str, tuple[str, str]]] = {
    "unicode": ("→", "*"),
    "ascii": ("->", "*"),
}

#: An empty move's column heading, and an empty cell of an NFA's table (the empty
#: set) and of a DFA's (no move), per charset.
TEXT_EPSILON: Final[Mapping[str, str]] = {"unicode": "ε", "ascii": "eps"}
TEXT_NONE: Final[Mapping[str, tuple[str, str]]] = {
    "unicode": ("∅", "—"),
    "ascii": ("{}", "-"),
}

#: The rules of the table, per charset: across under the heading, down after the
#: state column, and where the two meet.
TEXT_RULES: Final[Mapping[str, tuple[str, str, str]]] = {
    "unicode": ("─", "│", "┼"),
    "ascii": ("-", "|", "+"),
}

#: Spaces between two columns of the table.
TEXT_GAP: Final = 3


def nondeterministic(document: Document) -> bool:
    """Whether any state has an empty move, or two moves on one symbol."""
    seen: set[tuple[str, str]] = set()
    for move in document.automaton_transitions:
        if move.epsilon:
            return True
        key = (move.source, move.symbol)
        if key in seen:
            return True
        seen.add(key)
    return False


def automaton_text(document: Document, width: int, charset: str) -> str:
    """An automaton as its transition table: a row per state, a column per symbol.

    The first column marks the start state `→` (`->` in ASCII) and each accepting
    state `*`, then names the state; each symbol's column (ε last) holds where the
    machine goes on it. An NFA's cells are sets — `{q0, q1}`, `∅` for none — as the
    textbooks print them; a DFA's a state, or `—` where no move is drawn. A Mealy
    machine's cell carries the output, `q1 / 1`; a Moore machine's table ends in an
    `output` column. A key under the table says what the marks mean.

    Raises:
        FitError: the table is wider than `width`, at the widest row's state.
        DrawspecError: an `ascii` drawing meets a name with no ASCII spelling.
    """
    states = document.automaton_states
    moves = document.automaton_transitions
    names = {
        state.id: spelt(
            state.text, charset, f"/states/{index}/{'text' if state.text != state.id else 'id'}"
        )
        for index, state in enumerate(states)
    }
    symbols: list[str] = []
    for move in moves:
        if not move.epsilon and move.symbol not in symbols:
            symbols.append(move.symbol)
    columns = [
        spelt(symbol, charset, f"/transitions/{_first(moves, symbol)}/on") for symbol in symbols
    ]
    has_empty = any(move.epsilon for move in moves)
    if has_empty:
        columns.append(TEXT_EPSILON[charset])
    sets = nondeterministic(document)
    moore = any(state.output for state in states)
    empty_set, no_move = TEXT_NONE[charset]

    def cell(state: str, symbol: str | None) -> str:
        found = [
            move
            for move in moves
            if move.source == state
            and (move.epsilon if symbol is None else (not move.epsilon and move.symbol == symbol))
        ]
        targets = [
            names[move.target]
            + (f" / {spelt(move.output, charset, '/transitions')}" if move.output else "")
            for move in found
        ]
        if sets:
            return "{" + ", ".join(targets) + "}" if targets else empty_set
        return targets[0] if targets else no_move

    start_mark, accept_mark = TEXT_MARKS[charset]
    accepting = set(document.automaton_accepting)
    heads = ["", *columns]
    if moore:
        heads.append("output")
    rows: list[list[str]] = []
    for index, state in enumerate(states):
        mark = start_mark if state.id == document.automaton_start else " " * cells(start_mark)
        mark += accept_mark if state.id in accepting else " "
        row = [f"{mark} {names[state.id]}"]
        row += [cell(state.id, symbol) for symbol in symbols]
        if has_empty:
            row.append(cell(state.id, None))
        if moore:
            row.append(spelt(state.output, charset, f"/states/{index}/output"))
        rows.append(row)
    sizes = [max(cells(row[column]) for row in [heads, *rows]) for column in range(len(heads))]
    across, down, joint = TEXT_RULES[charset]
    gap = " " * TEXT_GAP

    def drawn(row: Sequence[str]) -> str:
        rest = gap.join(pad(text, sizes[column + 1]) for column, text in enumerate(row[1:]))
        return f"{pad(row[0], sizes[0])} {down} {rest}"

    lines: list[Drawn] = [Drawn(drawn(heads), "/transitions", "the symbols")]
    rest_width = sum(sizes[1:]) + TEXT_GAP * (len(sizes) - 2)
    lines.append(Drawn(across * (sizes[0] + 1) + joint + across * (rest_width + 1)))
    for index, row in enumerate(rows):
        lines.append(
            Drawn(drawn(row), f"/states/{index}", f"the row of {names[states[index].id]!r}")
        )
    key = [f"{start_mark} start state"]
    if accepting:
        key.append(f"{accept_mark} accepting")
    if sets:
        key.append(f"{empty_set} no move")
    lines.append(Drawn(""))
    lines.append(Drawn(", ".join(key) + "."))
    widest(lines, width)
    return finished([line.text for line in lines] + caption_lines(document.caption, width, charset))


def _first(moves: Sequence[AutomatonTransition], symbol: str) -> int:
    return next(
        index for index, move in enumerate(moves) if move.symbol == symbol and not move.epsilon
    )


__all__ = [
    "EPSILON",
    "MOVE_ROLE",
    "STATE_ROLE",
    "Arc",
    "AutomatonDrawing",
    "Circle",
    "automaton_drawing",
    "automaton_scene",
    "automaton_text",
    "merged",
    "move_label",
    "nondeterministic",
    "state_name",
]
