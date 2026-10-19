"""Causal loops on a `flow`: each link's sign, delay marks, and the loop markers.

A causal loop diagram is a `flow` whose edges carry a `polarity` — more of this
means more (`+`) or less (`-`) of that — and whose feedback loops are named in
`loops`. Three things are added to the drawing, and none is the author's to place:

**The sign** is written as the edge's label, so the label placer keeps it clear
of every line, box and other label, as it does for any label. The theme's
`[flow] polarity` says whether it is `+` and a minus, or the `s`/`o` some courses use.

**A delay** is the standard double stroke across the edge's shaft, at the first
point along it, from the middle outwards, where the stroke clears every label
and box.

**A loop's marker** is a circular arrow round its letter and number — `R1` for
the first reinforcing loop, `B1` for the first balancing one — with the loop's
name under it. The letter is derived, not written: a loop with an even number of
negative links reinforces, and one with an odd number balances. The arrow turns
the way the loop runs on the page. The marker goes inside the loop, at the point
of the figure its routes close that is furthest from everything already drawn;
when the loop has no room inside, beside its first link; and when there is no
room there either, the document is a `FitError` naming the loop.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from drawspec.clearance import CLEARANCE
from drawspec.errors import FitError
from drawspec.kinds.graph import GraphDrawing
from drawspec.routing import Route
from drawspec.scene import Path, Polygon, Primitive, TextLine, TextSpan
from drawspec.schema import CausalLoop, Document, Edge
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, bold_lines, wrap
from drawspec.theme import POLARITY_GLYPHS, Theme

#: The letters a loop's type is drawn with.
LETTERS: Final = {"reinforcing": "R", "balancing": "B"}

#: Lengths in units, a unit being the body size over eleven.
MARGIN: Final = 4.0
"""How far a marker keeps from every box, line, label and other marker."""
RING_PAD: Final = 3.0
"""From the marker's letters to its ring, beyond the strokes' clearance."""
NAME_GAP: Final = 2.0
"""From the ring to the loop's name under it."""
HEAD_LENGTH: Final = 5.0
HEAD_HALF: Final = 3.5
DELAY_HALF: Final = 5.0
"""Half the length of a delay stroke, across the shaft."""
DELAY_SPACE: Final = 3.0
"""Between the two strokes of a delay, along the shaft."""
STEP: Final = 3.0
"""The grid step a marker's centre is sought on."""

#: How much of the ring is drawn; the rest is the gap the head points into.
ARC_SWEEP: Final = math.radians(290)
ARC_POINTS: Final = 48

#: Where along a route a delay is tried, as fractions of its length.
DELAY_AT: Final = (0.5, 0.4, 0.6, 0.3, 0.7, 0.25, 0.75, 0.2, 0.8)

#: The most lines a loop's name is wrapped to.
NAME_LINES: Final = 3

#: Where a loop's name may go, by its ring, in the order tried.
SIDES: Final = ("below", "right", "left")

#: The role a marker's ring and head are drawn in, and its words.
RING_ROLE: Final = "flow"
TEXT_ROLE: Final = "step"

type _Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class LoopMarker:
    """One loop's marker, placed, in final coordinates."""

    name: str
    """The drawn letter and number: `R1`, `B2`."""
    kind: str
    """`reinforcing` or `balancing`, derived from the signs."""
    cx: float
    cy: float
    radius: float
    text: _Rect | None
    """The bounds of the loop's name under the ring, if it has one."""
    clockwise: bool
    """Which way the ring's arrow turns: the way the loop runs on the page."""
    inside: bool
    """Whether the marker sits inside the figure the loop's routes close."""
    polygon: tuple[tuple[float, float], ...]
    """That figure, in order."""
    block: TextBlock | None = field(default=None, repr=False)
    """The loop's name as wrapped under the ring."""

    @property
    def footprint(self) -> tuple[_Rect, ...]:
        ring = (
            self.cx - self.radius,
            self.cy - self.radius,
            self.cx + self.radius,
            self.cy + self.radius,
        )
        return (ring,) if self.text is None else (ring, self.text)


@dataclass(frozen=True)
class Delay:
    """One delay mark: the point on the shaft and whether the shaft runs across."""

    x: float
    y: float
    across: bool
    """True when the shaft is horizontal there, so the strokes stand upright."""


@dataclass(frozen=True)
class CausalDrawing:
    primitives: tuple[Primitive, ...] = ()
    markers: tuple[LoopMarker, ...] = ()
    delays: tuple[Delay, ...] = ()


def sign(polarity: str, theme: Theme) -> str:
    """The glyph an edge's polarity is written as, in this theme."""
    return POLARITY_GLYPHS[theme.flow.polarity][polarity]


def negatives(document: Document, loop: CausalLoop) -> int:
    """How many of the loop's links are negative."""
    polarity = {(edge.source, edge.target): edge.polarity for edge in document.edges}
    ring = loop.nodes
    return sum(
        polarity.get((ring[index], ring[(index + 1) % len(ring)]), "") == "-"
        for index in range(len(ring))
    )


def loop_kind(document: Document, loop: CausalLoop) -> str:
    """`reinforcing` for an even number of negative links, `balancing` for odd."""
    return "balancing" if negatives(document, loop) % 2 else "reinforcing"


def causal_drawing(
    document: Document, drawing: GraphDrawing, theme: Theme, measurer: TextMeasurer
) -> CausalDrawing:
    """The delay marks and the loop markers for a drawn `flow`.

    Raises:
        FitError: a loop's marker has room neither inside the loop nor beside it.
    """
    unit = theme.scale["body"] / 11
    routes = _routes_by_edge(document.edges, drawing.routes)
    obstacles = _obstacles(drawing)
    segments = [segment for route in drawing.routes for segment in route.segments]

    primitives: list[Primitive] = []
    delays: list[Delay] = []
    for edge, route in zip(document.edges, routes, strict=True):
        if edge.delay and route is not None:
            delay = _delay(route, obstacles, segments, unit)
            delays.append(delay)
            primitives.extend(_delay_primitives(delay, edge.role, unit))

    markers: list[LoopMarker] = []
    counts = dict.fromkeys(LETTERS.values(), 0)
    width = max(drawing.width, 1.0)
    every_route = [
        [
            routes[
                _edge_index(document.edges, loop.nodes[i], loop.nodes[(i + 1) % len(loop.nodes)])
            ]
            for i in range(len(loop.nodes))
        ]
        for loop in document.loops
    ]
    polygons = [
        tuple(point for route in loop_routes if route for point in route.points)
        for loop_routes in every_route
    ]
    for index, (loop, loop_routes, polygon) in enumerate(
        zip(document.loops, every_route, polygons, strict=True)
    ):
        kind = loop_kind(document, loop)
        letter = LETTERS[kind]
        counts[letter] += 1
        name = f"{letter}{counts[letter]}"
        others = [shape for k, shape in enumerate(polygons) if k != index and shape]
        placed = [rect for marker in markers for rect in marker.footprint]
        marker = _marker(
            name,
            kind,
            loop.text,
            polygon,
            others,
            loop_routes[0],
            [*obstacles, *placed],
            segments,
            width,
            unit,
            theme,
            measurer,
        )
        markers.append(marker)
        primitives.extend(_marker_primitives(marker, loop.text, unit, theme, measurer))
    return CausalDrawing(tuple(primitives), tuple(markers), tuple(delays))


# ---------------------------------------------------------------------------
# What is already drawn
# ---------------------------------------------------------------------------


def _edge_index(edges: Sequence[Edge], source: str, target: str) -> int:
    return next(
        index for index, edge in enumerate(edges) if edge.source == source and edge.target == target
    )


def _routes_by_edge(edges: Sequence[Edge], routes: Sequence[Route]) -> list[Route | None]:
    """Each edge's route, matched by its ends in the order both are written."""
    pool = list(routes)
    found: list[Route | None] = []
    for edge in edges:
        match = next(
            (
                index
                for index, route in enumerate(pool)
                if route.source == edge.source and route.target == edge.target
            ),
            None,
        )
        found.append(None if match is None else pool.pop(match))
    return found


def _obstacles(drawing: GraphDrawing) -> list[_Rect]:
    """Every box, label and frame caption as a rectangle, and frame sides as thin ones."""
    rects: list[_Rect] = [
        (box.x, box.y, box.x + box.width, box.y + box.height) for box in drawing.boxes.values()
    ]
    rects += [label.box for label in drawing.labels]
    for frame in drawing.frames:
        left, top, right, bottom = frame.x, frame.y, frame.right, frame.bottom
        rects += [
            (left, top, right, top),
            (left, bottom, right, bottom),
            (left, top, left, bottom),
            (right, top, right, bottom),
        ]
        if frame.caption is not None:
            caption = frame.caption
            rects.append(
                (caption.x, caption.y, caption.x + caption.width, caption.y + caption.height)
            )
    return rects


def _gap(one: _Rect, other: _Rect) -> float:
    """The distance between two rectangles; zero when they touch or overlap."""
    dx = max(other[0] - one[2], one[0] - other[2], 0.0)
    dy = max(other[1] - one[3], one[1] - other[3], 0.0)
    return math.hypot(dx, dy)


def _segment_rect(start: tuple[float, float], end: tuple[float, float]) -> _Rect:
    (x0, y0), (x1, y1) = start, end
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _clearance(
    footprint: Sequence[_Rect],
    obstacles: Sequence[_Rect],
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> float:
    """How far the footprint is from the nearest obstacle or line.

    Routes are orthogonal, so a segment is a rectangle with no width and the
    distance to it is a distance between rectangles.
    """
    nearest = math.inf
    for rect in footprint:
        for obstacle in obstacles:
            nearest = min(nearest, _gap(rect, obstacle))
        for start, end in segments:
            nearest = min(nearest, _gap(rect, _segment_rect(start, end)))
    return nearest


# ---------------------------------------------------------------------------
# Delays
# ---------------------------------------------------------------------------


def _delay(
    route: Route,
    obstacles: Sequence[_Rect],
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    unit: float,
) -> Delay:
    """The first point along the route, middle outwards, where the strokes stand clear.

    A point too near a bend is skipped, so both strokes cross one straight
    piece of the shaft. Where nowhere is clear, the roomiest point is taken.
    """
    own = set(route.segments)
    others = [segment for segment in segments if segment not in own]
    length = route.length
    best: tuple[float, Delay] | None = None
    for share in DELAY_AT:
        point = _along(route, share * length, (DELAY_SPACE + 4) * unit)
        if point is None:
            continue
        delay = point
        clear = _clearance([_delay_rect(delay, unit)], obstacles, others)
        if clear >= MARGIN * unit:
            return delay
        if best is None or clear > best[0]:
            best = (clear, delay)
    if best is not None:
        return best[1]
    middle = _along(route, length / 2, 0.0)
    assert middle is not None
    return middle


def _along(route: Route, distance: float, keep: float) -> Delay | None:
    """The point `distance` along the route, if it is `keep` from either end of its piece."""
    walked = 0.0
    for (x0, y0), (x1, y1) in route.segments:
        piece = math.hypot(x1 - x0, y1 - y0)
        if piece and walked + piece >= distance:
            into = distance - walked
            if into < keep or piece - into < keep:
                return None
            share = into / piece
            return Delay(x0 + (x1 - x0) * share, y0 + (y1 - y0) * share, abs(y1 - y0) < 1e-9)
        walked += piece
    return None


def _delay_rect(delay: Delay, unit: float) -> _Rect:
    along, across = (DELAY_SPACE / 2 + 1) * unit, DELAY_HALF * unit
    if delay.across:
        return (delay.x - along, delay.y - across, delay.x + along, delay.y + across)
    return (delay.x - across, delay.y - along, delay.x + across, delay.y + along)


def _delay_primitives(delay: Delay, role: str, unit: float) -> tuple[Primitive, ...]:
    """Two short strokes across the shaft, in the edge's own role."""
    half, space = DELAY_HALF * unit, DELAY_SPACE * unit / 2
    strokes: list[Primitive] = []
    for offset in (-space, space):
        if delay.across:
            points = ((delay.x + offset, delay.y - half), (delay.x + offset, delay.y + half))
        else:
            points = ((delay.x - half, delay.y + offset), (delay.x + half, delay.y + offset))
        strokes.append(Path(role, points=points))
    return tuple(strokes)


# ---------------------------------------------------------------------------
# Loop markers
# ---------------------------------------------------------------------------


def _letters(name: str, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    return wrap(bold_lines(name), 1e6, measurer, theme=theme, level="body")


def _name_wraps(text: str, theme: Theme, measurer: TextMeasurer) -> list[TextBlock]:
    """The loop's name on one line, then narrower: the wraps worth trying, widest first."""
    if not text:
        return []
    natural = wrap(text, 1e6, measurer, theme=theme, level="label")
    found = [natural]
    limit = natural.width
    while len(found) < NAME_LINES:
        try:
            block = wrap(text, limit * 0.999, measurer, theme=theme, level="label")
        except FitError:
            break
        if len(block.lines) > len(found[-1].lines):
            found.append(block)
        limit = block.width
    return found


def _marker(
    name: str,
    kind: str,
    text: str,
    polygon: tuple[tuple[float, float], ...],
    others: Sequence[tuple[tuple[float, float], ...]],
    first: Route | None,
    obstacles: Sequence[_Rect],
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    width: float,
    unit: float,
    theme: Theme,
    measurer: TextMeasurer,
) -> LoopMarker:
    letters = _letters(name, theme, measurer)
    # Wide enough that the letters' line box, and the clearance every stroke keeps
    # from words, stays inside the ring at its corners.
    reach = CLEARANCE + RING_PAD * unit / 2
    radius = math.hypot(letters.width / 2 + reach, letters.height / 2 + reach)
    clockwise = _area(polygon) > 0
    margin = MARGIN * unit
    wraps: list[TextBlock | None] = [*_name_wraps(text, theme, measurer)] or [None]
    # The name under the ring reads best; beside it fits a loop between two ranks.
    tries = [(side, block) for side in SIDES for block in wraps if block or side == "below"]

    def footprint(x: float, y: float, block: TextBlock | None, side: str) -> tuple[_Rect, ...]:
        ring = (x - radius, y - radius, x + radius, y + radius)
        if block is None:
            return (ring,)
        gap = NAME_GAP * unit + CLEARANCE * 2
        if side == "below":
            top = y + radius + gap
            return (ring, (x - block.width / 2, top, x + block.width / 2, top + block.height))
        top = y - block.height / 2
        start = x + radius + gap if side == "right" else x - radius - gap - block.width
        return (ring, (start, top, start + block.width, top + block.height))

    def made(x: float, y: float, block: TextBlock | None, side: str, inside: bool) -> LoopMarker:
        rects = footprint(x, y, block, side)
        return LoopMarker(
            name, kind, x, y, radius, rects[1] if block else None, clockwise, inside, polygon, block
        )

    # Inside: the point of the loop's figure furthest from everything drawn —
    # in no other loop's figure if it can be, so the marker reads as this loop's.
    left = min(x for x, _ in polygon)
    right = max(x for x, _ in polygon)
    top = min(y for _, y in polygon)
    bottom = max(y for _, y in polygon)
    step = STEP * unit
    chosen: tuple[int, int, float, float, float] | None = None
    for order, (side, block) in enumerate(tries):
        for x, y in _grid(left, top, right, bottom, step):
            if not _contains(polygon, x, y):
                continue
            rects = footprint(x, y, block, side)
            if not all(_rect_inside(polygon, rect) for rect in rects):
                continue
            clear = _clearance(rects, obstacles, segments)
            if clear < margin:
                continue
            shared = sum(_contains(shape, x, y) for shape in others)
            if chosen is None or (shared, order, -clear) < (chosen[0], chosen[1], -chosen[2]):
                chosen = (shared, order, clear, x, y)
        if chosen is not None and chosen[0] == 0:
            break
    if chosen is not None:
        side, block = tries[chosen[1]]
        return made(chosen[3], chosen[4], block, side, True)

    # Beside: the nearest point to the loop's first link with room, on the page.
    if first is not None:
        own = first.segments
        ends = [p for segment in own for p in segment]
        for side, block in tries:
            rects = footprint(0.0, 0.0, block, side)
            low_x = min(rect[0] for rect in rects)
            high_x = max(rect[2] for rect in rects)
            extent = high_x - low_x + max(rect[3] for rect in rects) - min(r[1] for r in rects)
            beside: tuple[float, float, float] | None = None
            for x, y in _grid(
                max(min(px for px, _ in ends) - extent, -low_x),
                min(py for _, py in ends) - extent,
                min(max(px for px, _ in ends) + extent, width - high_x),
                max(py for _, py in ends) + extent,
                step,
            ):
                rects = footprint(x, y, block, side)
                if _clearance(rects, obstacles, segments) < margin:
                    continue
                distance = min(_gap(rects[0], _segment_rect(start, end)) for start, end in own)
                if beside is None or distance < beside[0]:
                    beside = (distance, x, y)
            if beside is not None:
                return made(beside[1], beside[2], block, side, False)
    raise FitError(
        f"the loop {name} ({text[:40]!r}) has no room for its marker, inside it or beside "
        f"its first link. Shorten its name, split the diagram, or give it more width."
    )


def _grid(
    left: float, top: float, right: float, bottom: float, step: float
) -> list[tuple[float, float]]:
    if right < left or bottom < top:
        return []
    columns = max(int((right - left) / step), 0)
    rows = max(int((bottom - top) / step), 0)
    return [(left + i * step, top + j * step) for i in range(columns + 1) for j in range(rows + 1)]


def _area(polygon: Sequence[tuple[float, float]]) -> float:
    """Twice the signed area; positive when the points run clockwise on the page."""
    return sum(
        x0 * y1 - x1 * y0
        for (x0, y0), (x1, y1) in zip(polygon, [*polygon[1:], polygon[0]], strict=True)
    )


def _contains(polygon: Sequence[tuple[float, float]], x: float, y: float) -> bool:
    """Whether the point is inside the polygon, by the even-odd rule."""
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, [*polygon[1:], polygon[0]], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _rect_inside(polygon: Sequence[tuple[float, float]], rect: _Rect) -> bool:
    """Whether the rectangle's corners are inside the polygon and no side crosses it."""
    left, top, right, bottom = rect
    if not all(_contains(polygon, x, y) for x in (left, right) for y in (top, bottom)):
        return False
    edges = list(zip(polygon, [*polygon[1:], polygon[0]], strict=True))
    for (x0, y0), (x1, y1) in edges:
        if max(x0, x1) <= left or min(x0, x1) >= right:
            continue
        if max(y0, y1) <= top or min(y0, y1) >= bottom:
            continue
        return False
    return True


def _marker_primitives(
    marker: LoopMarker, text: str, unit: float, theme: Theme, measurer: TextMeasurer
) -> tuple[Primitive, ...]:
    """The ring, its head, the letters inside it and the name under it."""
    turn = 1.0 if marker.clockwise else -1.0
    # The gap is at the top; the head arrives at its far side, pointing on round.
    start = -math.pi / 2 + turn * (2 * math.pi - ARC_SWEEP) / 2
    angles = [start + turn * ARC_SWEEP * k / ARC_POINTS for k in range(ARC_POINTS + 1)]
    head_angle = math.atan2(HEAD_LENGTH * unit, marker.radius)
    # The shaft stops short of the tip, so the head's point is the arc's end.
    shaft = angles[: -max(1, round(ARC_POINTS * head_angle / ARC_SWEEP))]
    ring = tuple(
        (marker.cx + marker.radius * math.cos(a), marker.cy + marker.radius * math.sin(a))
        for a in shaft
    )
    end = angles[-1]
    tip = (marker.cx + marker.radius * math.cos(end), marker.cy + marker.radius * math.sin(end))
    back = end - turn * head_angle
    base = (marker.cx + marker.radius * math.cos(back), marker.cy + marker.radius * math.sin(back))
    nx, ny = math.cos(back), math.sin(back)
    half = HEAD_HALF * unit
    head = (
        tip,
        (base[0] + nx * half, base[1] + ny * half),
        (base[0] - nx * half, base[1] - ny * half),
    )
    found: list[Primitive] = [Path(RING_ROLE, points=ring), Polygon(RING_ROLE, points=head)]
    letters = _letters(marker.name, theme, measurer)
    found += _lines(letters, marker.cx, marker.cy - letters.height / 2, "body")
    if marker.text is not None and marker.block is not None:
        left, top, right, _ = marker.text
        found += _lines(marker.block, (left + right) / 2, top, "label")
    return tuple(found)


def _lines(block: TextBlock, x: float, top: float, level: str) -> list[TextLine]:
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(
                    TEXT_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor="middle",
                )
            )
    return found


__all__ = [
    "LETTERS",
    "CausalDrawing",
    "Delay",
    "LoopMarker",
    "causal_drawing",
    "loop_kind",
    "negatives",
    "sign",
]
