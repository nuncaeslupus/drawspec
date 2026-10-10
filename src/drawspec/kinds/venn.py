"""The `venn` kind: two or three overlapping sets, each region named by membership.

With two or three equal circles every region is fixed by **which sets it is in**,
so the author writes `"in": ["gdpr", "ens"]` and drawspec knows where that is. It
is not area-proportional — sizes would be data — and it stops at three sets,
because no arrangement of four circles shows every region.

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
from drawspec.scene import Ellipse, Polygon, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import Document, Region
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


__all__ = ["CENTRES", "VennDrawing", "inside", "venn_drawing", "venn_scene"]
