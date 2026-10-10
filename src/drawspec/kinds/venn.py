"""The `venn` kind: two to four overlapping sets, each region named by membership.

With two or three equal circles, or four equal ellipses, every region is fixed
by **which sets it is in**, so the author writes `"in": ["gdpr", "ens"]` and
drawspec knows where that is. It is not area-proportional — sizes would be data.
Four sets are ellipses, because no arrangement of four circles shows every
region; it stops at four.

**The circles** are equal: two side by side, their centres a radius apart, or
three at the corners of an equilateral triangle with a radius for a side. The
radius is the smallest, between a floor and what the canvas allows, at which
every region's words fit inside their region.

**A region's words** are wrapped, then placed at the deepest point of the region
where the whole block fits — every corner inside each circle the region is in,
and the block clear of every circle it is not in, by a margin either way. The
widest wrap that fits wins. A region the author lists as `emphasis` is filled
with the theme's first mark fill, clipped to its exact outline, and its words
are bold. A region not listed is drawn empty.

**The set names** are outside the circles, never across an outline: above each
of two circles, and for three, above the top one and below the other two.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cache
from typing import Final

from drawspec.errors import FitError
from drawspec.scene import (
    Ellipse,
    Path,
    Polygon,
    Primitive,
    Scene,
    TextLine,
    TextSpan,
    moved,
)
from drawspec.schema import Document, Region, VennSet
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The centres of the circles for a radius of one, in the order the sets are
#: written: two side by side a radius apart; three at the corners of an
#: equilateral triangle with a radius for a side, the first on top.
_SIDE: Final = 1.0
_CORNER: Final = _SIDE / math.sqrt(3)
CENTRES: Final[dict[int, tuple[tuple[float, float], ...]]] = {
    2: ((-_SIDE / 2, 0.0), (_SIDE / 2, 0.0)),
    3: ((0.0, -_CORNER), (-_SIDE / 2, _CORNER / 2), (_SIDE / 2, _CORNER / 2)),
}

#: The smallest radius as a share of the canvas: a few short words in each region
#: still draw circles large enough to read as the diagram rather than as an icon.
RADIUS_FLOOR: Final = 0.2

#: How many halvings the search for the radius takes.
BISECTIONS: Final = 18

#: Lengths in units, a unit being the body size over eleven.
MARGIN: Final = 6.0
"""How far a region's words keep from every outline, inside or out."""
NAME_GAP: Final = 6.0
"""From a circle to its set's name, and between two names side by side."""

#: How wide a four-set name may wrap, as a share of the semi-major axis.
NAME_SHARE: Final = 0.8

#: How finely the region's candidate points and outline are sampled, for a
#: radius of one: the grid step, and the points around each circle.
GRID_STEP: Final = 0.025
ARC_SAMPLES: Final = 720

#: How many of a region's deepest points are tried as the centre of its words.
CANDIDATES: Final = 400

#: The role the words and names are drawn in: furniture, not boxes.
TEXT_ROLE: Final = "step"

#: The role an emphasised region's fill is drawn in. A region, so not outlined.
FILL_ROLE: Final = "step"

type _Rect = tuple[float, float, float, float]
type _Ellipse = tuple[float, float, float, float, float]

#: Four sets: four congruent ellipses, so that all fifteen regions exist — four
#: circles cannot draw the two diagonal pairs. For a semi-major axis of one:
#: centre, semi-axes and the angle of the major axis (radians, clockwise on the
#: page). The middle two share a centre and cross as an X; the outer two sit
#: lower and wider. The proportions were chosen by search, to make the smallest
#: region as roomy as it can be, so no one of the fifteen is a sliver.
_TILT: Final = math.radians(35)
_MINOR: Final = 0.55
ELLIPSES: Final[tuple[_Ellipse, ...]] = (
    (-0.33, 0.0, 1.0, _MINOR, _TILT),
    (0.0, -0.28, 1.0, _MINOR, _TILT),
    (0.0, -0.28, 1.0, _MINOR, -_TILT),
    (0.33, 0.0, 1.0, _MINOR, -_TILT),
)

#: Points sampled around each ellipse, for its outline and its region fills.
ELLIPSE_SAMPLES: Final = 360

#: The grid step for a four-set region's candidate points, for a semi-major axis
#: of one: the regions are smaller than two or three circles', so finer.
FOUR_GRID_STEP: Final = 0.0125


@dataclass(frozen=True)
class VennDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    radius: float = 0.0
    centres: tuple[tuple[float, float], ...] = ()
    """Each set's circle centre, in the order the sets are written."""

    regions: tuple[tuple[frozenset[str], _Rect], ...] = ()
    """Each listed region's membership and the bounds of its words."""

    names: dict[str, _Rect] = field(default_factory=dict)
    """Each set's name's bounds, by id."""

    fills: tuple[tuple[frozenset[str], tuple[tuple[float, float], ...]], ...] = ()
    """Each emphasised region's outline, as filled."""

    ellipses: tuple[_Ellipse, ...] = ()
    """Four sets' ellipses, `(cx, cy, rx, ry, angle)` in the order the sets are
    written; empty for two or three, whose circles are `centres` and `radius`."""


def venn_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a Venn diagram."""
    return venn_drawing(document, theme, measurer).scene


def venn_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> VennDrawing:
    """Find the radius every region's words fit at, and draw the circles there.

    Raises:
        FitError: a region's words do not fit their region at the largest radius
            the canvas allows.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    sets = document.venn_sets
    count = len(sets)
    if count == len(ELLIPSES):
        return _four_drawing(document, theme, measurer)
    centres = CENTRES[count]
    order = {item.id: index for index, item in enumerate(sets)}
    spread = max(x for x, _ in centres) - min(x for x, _ in centres) + 2
    ceiling = width / spread
    floor = min(width * RADIUS_FLOOR, ceiling)
    margin = MARGIN * unit

    wraps = [(region, _wraps(region, ceiling * 2, theme, measurer)) for region in document.regions]

    def placed(
        radius: float, *, best: bool = False
    ) -> list[tuple[Region, TextBlock, float, float]] | None:
        found: list[tuple[Region, TextBlock, float, float]] = []
        for region, blocks in wraps:
            mask = _mask(region, order)
            spot = _spot(blocks, mask, count, radius, margin, best=best)
            if spot is None:
                return None
            found.append((region, *spot))
        return found

    layout = placed(floor)
    radius = floor
    if layout is None:
        if placed(ceiling) is None:
            for region, blocks in wraps:
                if _spot(blocks, _mask(region, order), count, ceiling, margin) is None:
                    raise FitError(
                        f"the region {region.text[:40]!r} (in {', '.join(region.members)}) does "
                        f"not fit its part of the circles at the largest size the width "
                        f"{width:.0f} allows. A region holds a few words: shorten it, give the "
                        f"diagram more width, or put a long list in a `columns` or `matrix`."
                    )
        low, high = floor, ceiling
        for _ in range(BISECTIONS):
            middle = (low + high) / 2
            if placed(middle) is None:
                low = middle
            else:
                high = middle
        radius = high
    layout = placed(radius, best=True)
    assert layout is not None

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    circles = tuple((x * radius, y * radius) for x, y in centres)
    fills: list[tuple[frozenset[str], tuple[tuple[float, float], ...]]] = []
    regions: list[tuple[frozenset[str], _Rect]] = []
    for region, block, cx, cy in layout:
        membership = frozenset(region.members)
        if region.role == "emphasis":
            points = _outline(_mask(region, order), count, radius)
            fills.append((membership, points))
            primitives.append(
                Polygon(
                    FILL_ROLE,
                    points=points,
                    fill=theme.mark.fill_for(0),
                    fill_colour=theme.mark.colour_for(0),
                    region=True,
                )
            )
        top = cy - block.height / 2
        texts.extend(_lines(block, cx, top, region.role))
        regions.append(
            (membership, (cx - block.width / 2, top, cx + block.width / 2, top + block.height))
        )
    for item, (cx, cy) in zip(sets, circles, strict=True):
        primitives.append(Ellipse(item.role, cx=cx, cy=cy, rx=radius, ry=radius))

    # The names: above two circles; above the top one and below the others of three.
    names: dict[str, _Rect] = {}
    gap = NAME_GAP * unit
    neighbour = _SIDE * radius - gap
    for index, (item, (cx, cy)) in enumerate(zip(sets, circles, strict=True)):
        above = count == 2 or index == 0
        room = 2 * radius if count == 3 and index == 0 else neighbour
        block = _named(item.text, room, theme, measurer)
        top = cy - radius - gap - block.height if above else cy + radius + gap
        texts.extend(_lines(block, cx, top, TEXT_ROLE))
        names[item.id] = (cx - block.width / 2, top, cx + block.width / 2, top + block.height)

    left = min(min(x for x, _ in circles) - radius, *(rect[0] for rect in names.values()))
    right = max(max(x for x, _ in circles) + radius, *(rect[2] for rect in names.values()))
    top = min(min(y for _, y in circles) - radius, *(rect[1] for rect in names.values()))
    bottom = max(max(y for _, y in circles) + radius, *(rect[3] for rect in names.values()))
    dx, dy = -left, -top
    scene = Scene(
        width=right - left,
        height=bottom - top,
        primitives=tuple(moved(primitive, dx, dy) for primitive in (*primitives, *texts)),
        title=document.title,
        description=document.description,
    )

    def shift(rect: _Rect) -> _Rect:
        return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)

    return VennDrawing(
        scene=scene,
        radius=radius,
        centres=tuple((x + dx, y + dy) for x, y in circles),
        regions=tuple((membership, shift(rect)) for membership, rect in regions),
        names={key: shift(rect) for key, rect in names.items()},
        fills=tuple(
            (membership, tuple((x + dx, y + dy) for x, y in points)) for membership, points in fills
        ),
    )


def inside(mask: tuple[bool, ...], count: int, x: float, y: float, radius: float = 1.0) -> bool:
    """Whether the point is in exactly the circles `mask` says, for this radius."""
    return all(
        (math.hypot(x - cx * radius, y - cy * radius) < radius) == member
        for (cx, cy), member in zip(CENTRES[count], mask, strict=True)
    )


def _mask(region: Region, order: dict[str, int]) -> tuple[bool, ...]:
    members = {order[member] for member in region.members}
    return tuple(index in members for index in range(len(order)))


def _wraps(region: Region, widest: float, theme: Theme, measurer: TextMeasurer) -> list[TextBlock]:
    """The region's words wrapped at every width worth trying, widest first.

    Each is the narrowest block with its number of lines, so the list runs from
    one line to as many as the words allow, with no two of the same height.
    """
    text = _bold(region.text) if region.role == "emphasis" else region.text
    natural = wrap(text, 1e6, measurer, theme=theme, level="body")
    blocks: list[TextBlock] = [natural]
    limit = min(natural.width, widest)
    while True:
        target = limit * 0.999
        try:
            block = wrap(text, target, measurer, theme=theme, level="body")
        except FitError:
            break
        if len(block.lines) > len(blocks[-1].lines):
            blocks.append(_balanced(text, block, theme, measurer))
        limit = block.width
        if limit <= 0:
            break
    return blocks


def _balanced(text: str, block: TextBlock, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    """As narrow as `text` goes on as many lines as `block` has."""
    low, high = block.width / 2, block.width
    for _ in range(10):
        middle = (low + high) / 2
        try:
            trial = wrap(text, middle, measurer, theme=theme, level="body")
        except FitError:
            low = middle
            continue
        if len(trial.lines) == len(block.lines):
            high, block = middle, trial
        else:
            low = middle
    return block


@cache
def _candidates(mask: tuple[bool, ...], count: int) -> tuple[tuple[float, float], ...]:
    """The region's points for a radius of one, deepest first.

    Depth is the distance to the nearest outline, so the first point is the
    region's pole — the centre of the largest circle that fits in it — and the
    words are tried there before anywhere nearer an edge.
    """
    centres = CENTRES[count]
    xs = [x for x, _ in centres]
    ys = [y for _, y in centres]
    found: list[tuple[float, float, float]] = []
    steps_x = math.ceil((max(xs) - min(xs) + 2) / GRID_STEP)
    steps_y = math.ceil((max(ys) - min(ys) + 2) / GRID_STEP)
    for i in range(steps_x + 1):
        x = min(xs) - 1 + i * GRID_STEP
        for j in range(steps_y + 1):
            y = min(ys) - 1 + j * GRID_STEP
            if not inside(mask, count, x, y):
                continue
            depth = min(abs(math.hypot(x - cx, y - cy) - 1) for cx, cy in centres)
            found.append((depth, x, y))
    found.sort(key=lambda entry: -entry[0])
    return tuple((x, y) for _, x, y in found[:CANDIDATES])


def _spot(
    blocks: list[TextBlock],
    mask: tuple[bool, ...],
    count: int,
    radius: float,
    margin: float,
    *,
    best: bool = False,
) -> tuple[TextBlock, float, float] | None:
    """A wrap of the region's words and where its centre goes, or `None` if none fits.

    Asked whether anything fits, the first fit found answers. Asked for the best,
    each wrap, fewest lines first, is placed where it has the most room to spare,
    and the first with a second margin's worth of room is taken — so the words sit
    in the middle of their region on as few lines as sit comfortably there. When
    none has that much, the roomiest that fits at all is taken.
    """
    centres = [(x * radius, y * radius) for x, y in CENTRES[count]]
    candidates = _candidates(mask, count)
    roomiest: tuple[TextBlock, float, float] | None = None
    most = -math.inf
    for block in blocks:
        half_w, half_h = block.width / 2, block.height / 2
        chosen: tuple[TextBlock, float, float] | None = None
        room_here = -math.inf
        for ux, uy in candidates:
            x, y = ux * radius, uy * radius
            room = _room(x, y, half_w, half_h, centres, mask, radius, margin)
            if room < 0:
                continue
            if not best:
                return block, x, y
            if room > room_here + 1e-9:
                chosen, room_here = (block, x, y), room
        if chosen is not None and room_here >= margin:
            return chosen
        if chosen is not None and room_here > most:
            roomiest, most = chosen, room_here
    return roomiest


def _room(
    x: float,
    y: float,
    half_w: float,
    half_h: float,
    centres: list[tuple[float, float]],
    mask: tuple[bool, ...],
    radius: float,
    margin: float,
) -> float:
    """How far a block centred here could grow before it touched an outline's margin.

    Negative when it does not fit: some corner outside a circle the region is in,
    or some part of it inside a circle the region is not in.
    """
    left, right, top, bottom = x - half_w, x + half_w, y - half_h, y + half_h
    room = math.inf
    for (cx, cy), member in zip(centres, mask, strict=True):
        if member:
            # A circle is convex: the block is inside it when every corner is.
            farthest = max(
                math.hypot(px - cx, py - cy) for px in (left, right) for py in (top, bottom)
            )
            room = min(room, radius - margin - farthest)
        else:
            # Clear of a circle: the block's nearest point to its centre is outside.
            nx = min(max(cx, left), right)
            ny = min(max(cy, top), bottom)
            room = min(room, math.hypot(nx - cx, ny - cy) - radius - margin)
        if room < 0:
            return room
    return room


def _outline(mask: tuple[bool, ...], count: int, radius: float) -> tuple[tuple[float, float], ...]:
    """The exact outline of a region, as a polygon: the arcs that bound it, in order.

    Each circle contributes the arcs of its outline that lie on the region's
    boundary — the points that are, by every other circle, where the region is.
    An arc of a circle the region is in runs one way round, and an arc of a
    circle it is outside the other, so the region is always on the same side;
    the arcs are then chained end to start.
    """
    centres = CENTRES[count]
    runs: list[list[tuple[float, float]]] = []
    for index, ((cx, cy), member) in enumerate(zip(centres, mask, strict=True)):
        others = [(j, centre) for j, centre in enumerate(centres) if j != index]
        on = []
        for step in range(ARC_SAMPLES):
            angle = 2 * math.pi * step / ARC_SAMPLES
            px, py = cx + math.cos(angle), cy + math.sin(angle)
            on.append(all((math.hypot(px - ox, py - oy) < 1) == mask[j] for j, (ox, oy) in others))
        if not any(on):
            continue
        if all(on):
            points = [
                (
                    cx + math.cos(2 * math.pi * s / ARC_SAMPLES),
                    cy + math.sin(2 * math.pi * s / ARC_SAMPLES),
                )
                for s in range(ARC_SAMPLES)
            ]
            runs.append(points if member else points[::-1])
            continue
        start = on.index(False)
        current: list[tuple[float, float]] = []
        for offset in range(1, ARC_SAMPLES + 1):
            step = (start + offset) % ARC_SAMPLES
            if on[step]:
                angle = 2 * math.pi * step / ARC_SAMPLES
                current.append((cx + math.cos(angle), cy + math.sin(angle)))
            elif current:
                runs.append(current if member else current[::-1])
                current = []
        if current:
            runs.append(current if member else current[::-1])
    if not runs:
        return ()
    chain = list(runs.pop(0))
    while runs:
        end = chain[-1]
        nearest = min(
            range(len(runs)),
            key=lambda k: math.hypot(runs[k][0][0] - end[0], runs[k][0][1] - end[1]),
        )
        chain.extend(runs.pop(nearest))
    return tuple((x * radius, y * radius) for x, y in chain)


def _bold(text: str) -> str:
    return "\n".join(
        f"**{line.replace('**', '')}**" if line.strip() else line for line in text.split("\n")
    )


def _named(text: str, width: float, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    """A set's name, bold, wrapped to the room beside its neighbour's."""
    try:
        block = wrap(_bold(text), width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the set name {text[:40]!r} has a word wider than the {width:.0f} units it can "
            f"have beside its neighbour's. Shorten it, or give the diagram more width."
        ) from error
    return _balanced(_bold(text), block, theme, measurer)


def _lines(block: TextBlock, x: float, top: float, role: str) -> list[TextLine]:
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(role, x=x, y=top + block.baseline(index), spans=spans, anchor="middle")
            )
    return found


# ---------------------------------------------------------------------------
# Four sets: ellipses
# ---------------------------------------------------------------------------


def _local(x: float, y: float, ellipse: _Ellipse, scale: float) -> tuple[float, float]:
    """The point in the ellipse's own frame: its centre the origin, its major axis `u`."""
    cx, cy, _, _, angle = ellipse
    dx, dy = x - cx * scale, y - cy * scale
    c, s = math.cos(angle), math.sin(angle)
    return dx * c + dy * s, -dx * s + dy * c


def ellipse_inside(ellipse: _Ellipse, x: float, y: float, scale: float = 1.0) -> bool:
    """Whether the point is inside the ellipse drawn at this scale."""
    u, v = _local(x, y, ellipse, scale)
    return (u / (ellipse[2] * scale)) ** 2 + (v / (ellipse[3] * scale)) ** 2 < 1


def inside_four(mask: tuple[bool, ...], x: float, y: float, scale: float = 1.0) -> bool:
    """Whether the point is in exactly the ellipses `mask` says, at this scale."""
    return all(
        ellipse_inside(ellipse, x, y, scale) == member
        for ellipse, member in zip(ELLIPSES, mask, strict=True)
    )


def _outline_distance(u: float, v: float, a: float, b: float) -> float:
    """The distance from a point in an ellipse's frame to its outline.

    By symmetry the nearest point is in the same quadrant, so the parameter is
    sought in the first: the best of a few samples, then Newton's method on the
    squared distance's derivative. The answer is a distance to a real point of
    the outline, so it is never short of the true one by more than the method's
    tolerance.
    """
    u, v = abs(u), abs(v)
    best, chosen = math.inf, 0.0
    for step in range(9):
        t = step * math.pi / 16
        squared = (a * math.cos(t) - u) ** 2 + (b * math.sin(t) - v) ** 2
        if squared < best:
            best, chosen = squared, t
    spread = b * b - a * a
    for _ in range(4):
        c, s = math.cos(chosen), math.sin(chosen)
        slope = spread * s * c + a * u * s - b * v * c
        curve = spread * (c * c - s * s) + a * u * c + b * v * s
        if curve <= 0:
            break
        chosen = min(max(chosen - slope / curve, 0.0), math.pi / 2)
    return math.hypot(a * math.cos(chosen) - u, b * math.sin(chosen) - v)


def _signed(ellipse: _Ellipse, x: float, y: float, scale: float) -> float:
    """How far inside the ellipse's outline the point is; negative outside."""
    u, v = _local(x, y, ellipse, scale)
    a, b = ellipse[2] * scale, ellipse[3] * scale
    distance = _outline_distance(u, v, a, b)
    return distance if (u / a) ** 2 + (v / b) ** 2 < 1 else -distance


def _four_candidates(mask: tuple[bool, ...]) -> tuple[tuple[float, float, float], ...]:
    """A four-set region's points for a semi-major axis of one, deepest first, with depth."""
    return _four_grid().get(mask, ())


@cache
def _four_grid() -> dict[tuple[bool, ...], tuple[tuple[float, float, float], ...]]:
    """Every region's candidate points at once: one pass over the grid, not fifteen."""
    found: dict[tuple[bool, ...], list[tuple[float, float, float]]] = {}
    left, top, right, bottom = _four_bounds()
    steps_x = math.ceil((right - left) / FOUR_GRID_STEP)
    steps_y = math.ceil((bottom - top) / FOUR_GRID_STEP)
    for i in range(steps_x + 1):
        x = left + i * FOUR_GRID_STEP
        for j in range(steps_y + 1):
            y = top + j * FOUR_GRID_STEP
            signed = [_signed(ellipse, x, y, 1.0) for ellipse in ELLIPSES]
            mask = tuple(value > 0 for value in signed)
            if not any(mask):
                continue
            found.setdefault(mask, []).append((x, y, min(abs(value) for value in signed)))
    return {
        mask: tuple(sorted(points, key=lambda entry: -entry[2])[:CANDIDATES])
        for mask, points in found.items()
    }


@cache
def _four_bounds() -> _Rect:
    """The four ellipses' bounds, for a semi-major axis of one."""
    xs: list[float] = []
    ys: list[float] = []
    for ellipse in ELLIPSES:
        for x, y in _ellipse_points(ellipse, 1.0):
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _ellipse_point(ellipse: _Ellipse, t: float, scale: float) -> tuple[float, float]:
    cx, cy, a, b, angle = ellipse
    c, s = math.cos(angle), math.sin(angle)
    u, v = a * math.cos(t), b * math.sin(t)
    return (cx + u * c - v * s) * scale, (cy + u * s + v * c) * scale


def _ellipse_points(ellipse: _Ellipse, scale: float) -> tuple[tuple[float, float], ...]:
    return tuple(
        _ellipse_point(ellipse, 2 * math.pi * step / ELLIPSE_SAMPLES, scale)
        for step in range(ELLIPSE_SAMPLES)
    )


def _segment_clearance(
    ellipse: _Ellipse, start: tuple[float, float], end: tuple[float, float], scale: float
) -> float:
    """The least distance from a segment to an ellipse it does not cross.

    The distance to a convex figure is a convex function of the point, so along
    a segment it has one minimum, found by golden-section search; zero or less
    means the segment touches the ellipse.
    """
    ratio = (math.sqrt(5) - 1) / 2

    def at(t: float) -> float:
        return -_signed(
            ellipse, start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t, scale
        )

    low, high = 0.0, 1.0
    first, second = high - ratio * (high - low), low + ratio * (high - low)
    value_first, value_second = at(first), at(second)
    for _ in range(14):
        if value_first < value_second:
            high, second, value_second = second, first, value_first
            first = high - ratio * (high - low)
            value_first = at(first)
        else:
            low, first, value_first = first, second, value_second
            second = low + ratio * (high - low)
            value_second = at(second)
    return min(at(0.0), at(1.0), value_first, value_second)


def _four_room(
    x: float,
    y: float,
    half_w: float,
    half_h: float,
    mask: tuple[bool, ...],
    radius: float,
    margin: float,
) -> float:
    """As `_room`, for ellipses: how far the block could grow, negative if it does not fit.

    An ellipse is convex, so a block is inside one by the margin when every
    corner is. Outside one, the block's four sides are each kept the margin
    clear of it: an ellipse is far larger than a few words, so it cannot sit
    wholly inside the block without crossing a side.
    """
    left, right, top, bottom = x - half_w, x + half_w, y - half_h, y + half_h
    corners = ((left, top), (right, top), (right, bottom), (left, bottom))
    room = math.inf
    for ellipse, member in zip(ELLIPSES, mask, strict=True):
        if member:
            for px, py in corners:
                room = min(room, _signed(ellipse, px, py, radius) - margin)
                if room < 0:
                    return room
    diagonal = math.hypot(half_w, half_h)
    for ellipse, member in zip(ELLIPSES, mask, strict=True):
        if member:
            continue
        # Far from this ellipse, the block cannot be nearer it than the rest.
        if -_signed(ellipse, x, y, radius) - diagonal - margin >= room:
            continue
        for index, start in enumerate(corners):
            end = corners[(index + 1) % 4]
            room = min(room, _segment_clearance(ellipse, start, end, radius) - margin)
            if room < 0:
                return room
    return room


def _four_spot(
    blocks: list[TextBlock],
    mask: tuple[bool, ...],
    radius: float,
    margin: float,
    *,
    best: bool = False,
) -> tuple[TextBlock, float, float] | None:
    """As `_spot`, for four ellipses.

    A point's depth bounds what can sit there: a block whose half-height and
    margin are deeper than the point cannot fit, and the points are deepest
    first, so the search stops at the first such point — and, asked for the
    best, at the first point whose depth leaves less room than the best found.
    A block whose half-diagonal fits within the depth fits without the exact
    test.
    """
    candidates = _four_candidates(mask)
    roomiest: tuple[TextBlock, float, float] | None = None
    most = -math.inf
    for block in blocks:
        half_w, half_h = block.width / 2, block.height / 2
        diagonal = math.hypot(half_w, half_h)
        chosen: tuple[TextBlock, float, float] | None = None
        room_here = -math.inf
        for ux, uy, depth in candidates:
            deep = depth * radius
            # No point after this one has more room than its depth allows.
            bound = deep - margin - min(half_w, half_h)
            if bound < 0 or bound <= room_here:
                break
            x, y = ux * radius, uy * radius
            if deep >= margin + diagonal and not best:
                return block, x, y
            room = _four_room(x, y, half_w, half_h, mask, radius, margin)
            if room < 0:
                continue
            if not best:
                return block, x, y
            if room > room_here + 1e-9:
                chosen, room_here = (block, x, y), room
        if chosen is not None and room_here >= margin:
            return chosen
        if chosen is not None and room_here > most:
            roomiest, most = chosen, room_here
    return roomiest


def _four_outline(mask: tuple[bool, ...], radius: float) -> tuple[tuple[float, float], ...]:
    """As `_outline`, for four ellipses: the arcs that bound the region, chained."""
    runs: list[list[tuple[float, float]]] = []
    for index, (ellipse, member) in enumerate(zip(ELLIPSES, mask, strict=True)):
        points = _ellipse_points(ellipse, 1.0)
        on = [
            all(
                ellipse_inside(other, px, py) == mask[j]
                for j, other in enumerate(ELLIPSES)
                if j != index
            )
            for px, py in points
        ]
        if not any(on):
            continue
        start = on.index(False) if not all(on) else 0
        current: list[tuple[float, float]] = []
        for offset in range(1, ELLIPSE_SAMPLES + 1):
            step = (start + offset) % ELLIPSE_SAMPLES
            if on[step]:
                current.append(points[step])
            elif current:
                runs.append(current if member else current[::-1])
                current = []
        if current:
            runs.append(current if member else current[::-1])
    if not runs:
        return ()
    chain = list(runs.pop(0))
    while runs:
        end = chain[-1]
        nearest = min(
            range(len(runs)),
            key=lambda k: math.hypot(runs[k][0][0] - end[0], runs[k][0][1] - end[1]),
        )
        chain.extend(runs.pop(nearest))
    return tuple((x * radius, y * radius) for x, y in chain)


def _four_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> VennDrawing:
    """Four sets: find the size every region's words fit at, and draw the ellipses there.

    The search is the circles': the smallest semi-major axis, between a floor
    and what the width allows, at which every listed region has a wrap that fits.
    The names go outside the ellipses without widening the drawing: the outer
    two under their own ellipse's far lobe, the middle two over their tips.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    sets = document.venn_sets
    order = {item.id: index for index, item in enumerate(sets)}
    left, _, right, _ = _four_bounds()
    ceiling = width / (right - left)
    floor = min(width * RADIUS_FLOOR, ceiling)
    margin = MARGIN * unit
    wraps = [(region, _wraps(region, ceiling, theme, measurer)) for region in document.regions]

    def placed(
        radius: float, *, best: bool = False
    ) -> list[tuple[Region, TextBlock, float, float]] | None:
        found: list[tuple[Region, TextBlock, float, float]] = []
        for region, blocks in wraps:
            spot = _four_spot(blocks, _mask(region, order), radius, margin, best=best)
            if spot is None:
                return None
            found.append((region, *spot))
        return found

    radius = floor
    if placed(floor) is None:
        if placed(ceiling) is None:
            for region, blocks in wraps:
                if _four_spot(blocks, _mask(region, order), ceiling, margin) is None:
                    raise FitError(
                        f"the region {region.text[:40]!r} (in {', '.join(region.members)}) does "
                        f"not fit its part of the four ellipses at the largest size the width "
                        f"{width:.0f} allows. With four sets a region holds a number or a word "
                        f"or two: shorten it, or give the diagram more width."
                    )
        low, high = floor, ceiling
        for _ in range(BISECTIONS):
            middle = (low + high) / 2
            if placed(middle) is None:
                low = middle
            else:
                high = middle
        radius = high
    layout = placed(radius, best=True)
    assert layout is not None

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    fills: list[tuple[frozenset[str], tuple[tuple[float, float], ...]]] = []
    regions: list[tuple[frozenset[str], _Rect]] = []
    for region, block, cx, cy in layout:
        membership = frozenset(region.members)
        if region.role == "emphasis":
            points = _four_outline(_mask(region, order), radius)
            fills.append((membership, points))
            primitives.append(
                Polygon(
                    FILL_ROLE,
                    points=points,
                    fill=theme.mark.fill_for(0),
                    fill_colour=theme.mark.colour_for(0),
                    region=True,
                )
            )
        top = cy - block.height / 2
        texts.extend(_lines(block, cx, top, region.role))
        regions.append(
            (membership, (cx - block.width / 2, top, cx + block.width / 2, top + block.height))
        )
    outlines = [_ellipse_points(ellipse, radius) for ellipse in ELLIPSES]
    for item, outline in zip(sets, outlines, strict=True):
        primitives.append(Path(item.role, points=outline, closed=True))

    names = _four_names(sets, outlines, radius, unit, theme, measurer)
    for item in sets:
        block, x, top = names[item.id]
        texts.extend(_lines(block, x, top, TEXT_ROLE))
    name_rects = {
        key: (x - block.width / 2, top, x + block.width / 2, top + block.height)
        for key, (block, x, top) in names.items()
    }

    every = [point for outline in outlines for point in outline]
    low_x = min(min(x for x, _ in every), *(rect[0] for rect in name_rects.values()))
    high_x = max(max(x for x, _ in every), *(rect[2] for rect in name_rects.values()))
    low_y = min(min(y for _, y in every), *(rect[1] for rect in name_rects.values()))
    high_y = max(max(y for _, y in every), *(rect[3] for rect in name_rects.values()))
    dx, dy = -low_x, -low_y
    scene = Scene(
        width=high_x - low_x,
        height=high_y - low_y,
        primitives=tuple(moved(primitive, dx, dy) for primitive in (*primitives, *texts)),
        title=document.title,
        description=document.description,
    )

    def shift(rect: _Rect) -> _Rect:
        return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)

    return VennDrawing(
        scene=scene,
        radius=radius,
        centres=tuple((cx * radius + dx, cy * radius + dy) for cx, cy, *_ in ELLIPSES),
        regions=tuple((membership, shift(rect)) for membership, rect in regions),
        names={key: shift(rect) for key, rect in name_rects.items()},
        fills=tuple(
            (membership, tuple((x + dx, y + dy) for x, y in points)) for membership, points in fills
        ),
        ellipses=tuple(
            (cx * radius + dx, cy * radius + dy, a * radius, b * radius, angle)
            for cx, cy, a, b, angle in ELLIPSES
        ),
    )


def _four_names(
    sets: tuple[VennSet, ...],
    outlines: list[tuple[tuple[float, float], ...]],
    radius: float,
    unit: float,
    theme: Theme,
    measurer: TextMeasurer,
) -> dict[str, tuple[TextBlock, float, float]]:
    """Each set's name, its centre x and its top: outside every ellipse.

    The outer two hang under their own ellipse's outer lobe, flush with the
    drawing's side; the middle two stand over their own ellipse's upper tip. Each
    is moved off the union of the ellipses over its width, by the name gap, so
    no name can cross an outline.
    """
    gap = NAME_GAP * unit
    every = [point for outline in outlines for point in outline]
    left = min(x for x, _ in every)
    right = max(x for x, _ in every)
    found: dict[str, tuple[TextBlock, float, float]] = {}
    for index, (item, outline) in enumerate(zip(sets, outlines, strict=True)):
        block = _named(item.text, NAME_SHARE * radius, theme, measurer)
        half = block.width / 2
        outer = index in (0, len(sets) - 1)
        if outer:
            x = left + half if index == 0 else right - half
        else:
            tip = min(outline, key=lambda point: point[1])
            x = min(max(tip[0], left + half), right - half)
        over = [py for px, py in every if x - half - gap <= px <= x + half + gap]
        top = max(over) + gap if outer else min(over) - gap - block.height
        found[item.id] = (block, x, top)
    # Each pair stands level: the outer two at the lower top, the middle two at
    # the higher bottom, so neither pair reads as two different rows.
    ids = [item.id for item in sets]
    outer_top = max(found[ids[0]][2], found[ids[-1]][2])
    middle_bottom = min(found[key][2] + found[key][0].height for key in ids[1:-1])
    for key in ids:
        block, x, _ = found[key]
        level = outer_top if key in (ids[0], ids[-1]) else middle_bottom - block.height
        found[key] = (block, x, level)
    return found


__all__ = [
    "CENTRES",
    "ELLIPSES",
    "VennDrawing",
    "ellipse_inside",
    "inside",
    "inside_four",
    "venn_drawing",
    "venn_scene",
]
