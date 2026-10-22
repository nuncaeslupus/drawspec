"""The `sunburst` kind: a hierarchy as concentric rings of sectors, read outward.

A layout family of its own. The tree is the whole input — a node is `{text,
children?}`, with an optional `centre` hub in the middle — and every decision
here is geometry derived from it, never a number an author wrote.

**Every terminal node takes an equal angle.** The circle is divided into one
slice per leaf, and a parent's span is the sum of its leaves', so a core with
six descendants is six times the wedge of a core with one. The order is the
order written, clockwise from twelve o'clock, and it is the same every render.

**Each ring takes one size, and its band is sized to the type it carries.** The
size is the largest that fits every label in the ring, so a ring reads evenly; its
band is then made proportional to that type, so a ring that is tight across its arc
(many narrow sectors) takes a thin band and a roomy inner ring takes a fat one, and
the words sit near their band's edges rather than adrift in it. Band and size
depend on each other — the band sets the radius, the radius sets how tall the type
can be across the arc — so they are solved together, by iteration. A branch that
ends early still reaches the rim — a terminal node spans every ring out from its
own — so a tree of uneven depth is a full disc, not a ragged one. A ring that
cannot meet the legible floor is refused rather than drawn too small to read.

**No label is ever upside down.** Each is centred in its sector — on the
mid-angle ray, halfway along its band — and rotated to that angle; on the left
half it is turned the other way so the reader never has to tip their head past a
quarter turn. That orientation is decided here, not by the author.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.scene import Polygon, Primitive, Scene, TextRun
from drawspec.schema import Document, SunburstNode
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Sector fills carry no outline of their own (`region`); the wheel's structure is
#: drawn as solid ink over them, in three weights so the hierarchy reads at a glance.
FILL_ROLE: Final = "step"

#: The least each line may be, in units, so a small wheel keeps its structure; the
#: share of the radius that sets each on a larger wheel is the theme's `[sunburst]
#: weights` (first-ring divider and rim, ring boundary and hub circle, deep division).
WEIGHT_FLOORS: Final = (2.5, 1.5, 1.0)

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when a label is stepped down.
PAD: Final = 3.0
"""The least space between a label and its band's rim, and its sector's edges."""

#: The layout's own lower bound on a label, as a share of the body size. The
#: effective floor is this or the theme's `min_legible_size`, whichever is
#: larger: below it the wheel is refused rather than drawn too small to read.
FLOOR_SHARE: Final = 0.5

#: The most a label may grow past the body size to fill a roomy sector. A wheel's
#: inner rings have space to spare, so the type is sized to the sector rather than
#: pinned to the body size — up to this, so one short word never balloons.
GROW_MAX: Final = 2.5

#: A label uses this much of the room along the radius (its length) and across the
#: arc (its height), leaving the rest as breathing room so the longest word in a
#: ring is never flush against the edges.
FILL_ALONG: Final = 0.85
FILL_ACROSS: Final = 0.9

#: The hub disc's radius, as a share of the wheel's, when a `centre` is given. Its
#: label grows to fill the disc, so the centre carries weight instead of a dot.
HUB_SHARE: Final = 0.13

#: The most degrees one straight piece of an arc may span.
ARC_STEP: Final = 2.0


@dataclass
class _Segment:
    """One sector, as it is laid out: tree facts first, geometry filled in."""

    text: str
    depth: int
    ancestor: int
    start: float
    end: float
    weight: int = 1
    """How many terminal nodes are at or below this one — its share of the circle."""
    leaf: bool = False
    r_in: float = 0.0
    r_out: float = 0.0
    font: float = 0.0
    rotate: float = 0.0
    anchor: str = "start"
    pivot: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class SunburstDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    centre: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    hub: float = 0.0
    rings: int = 0
    segments: tuple[_Segment, ...] = ()


def sunburst_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a sunburst wheel."""
    return sunburst_drawing(document, theme, measurer).scene


def sunburst_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> SunburstDrawing:
    """Lay the wheel out on the canvas.

    Raises:
        FitError: a label cannot be made to fit its sector at the floor size, so
            the wheel would be drawn illegibly.
    """
    base = theme.scale["body"]
    unit = base / 11
    pad = PAD * unit
    font = theme.font.default
    # The wheel fills the canvas; the sheet adds the theme's margin around the scene.
    width = document.width if document.width else theme.canvas.width
    radius = width / 2
    cx = cy = width / 2

    # Angles: one equal slice per terminal node, a parent spanning its own.
    segments: list[_Segment] = []
    leaves = sum(_leaves(node) for node in document.sunburst_nodes)
    slice_angle = 360.0 / leaves

    def assign(nodes: tuple[SunburstNode, ...], depth: int, start: float, ancestor: int) -> None:
        """Lay `nodes` out from `start`, each spanning its leaves, children within."""
        angle = start
        for index, node in enumerate(nodes):
            top = ancestor if depth > 1 else index
            weight = _leaves(node)
            span = weight * slice_angle
            segments.append(
                _Segment(node.text, depth, top, angle, angle + span, weight, not node.children)
            )
            if node.children:
                assign(node.children, depth + 1, angle, top)
            angle += span

    assign(document.sunburst_nodes, 1, 0.0, 0)
    if segments:
        segments[-1].end = 360.0
    rings = max((segment.depth for segment in segments), default=0)

    # The hub, if there is one, takes a share of the radius and its label grows to
    # fill that disc, so the centre is used rather than left as a dot in the middle.
    hub = 0.0
    hub_size = base
    hub_extents = None
    if document.centre:
        plain = measurer.measure(document.centre, font, base)
        diag = math.hypot(plain.width, plain.height)
        hub = max(HUB_SHARE * radius, diag / 2 + 2 * pad)
        # Grow the label to fill the disc, fitting its box's corners inside the circle.
        hub_size = base * max(1.0, 2 * (hub - 2 * pad) / diag) if diag > 0 else base
        hub_extents = measurer.measure(document.centre, font, hub_size)

    # Ring geometry and one size per ring, solved together. A ring takes one size,
    # and its band is made proportional to the type it carries — so a ring that is
    # tight across its arc (many narrow sectors) takes a thin band and a roomy inner
    # ring takes a fat one, and the type sits near its band's edges rather than
    # adrift in it. Band and size depend on each other (the band sets the radius, the
    # radius sets how tall the type can be across the arc), so they are iterated.
    extents = [measurer.measure(segment.text, font, base) for segment in segments]
    depths = range(1, rings + 1)
    paired = list(zip(segments, extents, strict=True))
    widest = {d: max((e.width for s, e in paired if s.depth == d), default=base) for d in depths}
    tallest = {d: max((e.height for s, e in paired if s.depth == d), default=base) for d in depths}
    # The tightest sector in a ring (smallest angle) caps how tall its type can be.
    min_half_sin = {
        d: min(
            (math.sin(math.radians((s.end - s.start) / 2)) for s in segments if s.depth == d),
            default=1.0,
        )
        for d in depths
    }
    span = max(radius - hub, unit)

    ring_font = dict.fromkeys(depths, base)
    edges = [hub + span * d / rings for d in range(rings + 1)]
    for _ in range(12):
        weight = {d: max(widest[d] * ring_font[d], unit) for d in depths}
        total = sum(weight.values()) or 1.0
        edges = [hub]
        for d in depths:
            edges.append(edges[-1] + span * weight[d] / total)
        for d in depths:
            r_mid = (edges[d - 1] + edges[d]) / 2
            across = (
                (2 * r_mid * min_half_sin[d] - 2 * pad) / tallest[d] if tallest[d] > 0 else GROW_MAX
            )
            along = (edges[d] - edges[d - 1] - 2 * pad) / widest[d] if widest[d] > 0 else GROW_MAX
            want = base * max(0.0, min(GROW_MAX, FILL_ACROSS * across, FILL_ALONG * along))
            ring_font[d] = (ring_font[d] + want) / 2

    # A terminal node reaches the outer rim, however shallow it is, so a tree of
    # uneven depth still draws as a full disc; an inner node keeps to its own ring.
    for segment in segments:
        segment.r_in = edges[segment.depth - 1]
        segment.r_out = edges[-1] if segment.leaf else edges[segment.depth]

    # A ring below the legible floor is refused rather than drawn too small to read.
    floor = max(base * FLOOR_SHARE, theme.canvas.min_legible_size)
    for d in depths:
        if ring_font[d] < floor:
            raise FitError(
                f"ring {d} of a sunburst {width:.0f} wide cannot be read: its labels fall "
                f"below {floor:.1f} units, the smallest legible type. Shorten the longest word "
                f"in it, widen the wheel, or give a node fewer children."
            )

    # Each label, centred in its sector: on the mid-angle ray, halfway along its band.
    for segment, ext in zip(segments, extents, strict=True):
        size = ring_font[segment.depth]
        segment.font = size
        mid = (segment.start + segment.end) / 2
        drop = (ext.ascent - ext.descent) * size / base / 2
        tangent = (math.cos(math.radians(mid)), math.sin(math.radians(mid)))
        r_label = (segment.r_in + segment.r_out) / 2
        px, py = _at(cx, cy, r_label, mid)
        segment.anchor = "middle"
        if mid <= 180.0:
            # Right half: reads outward, head tilted left.
            segment.rotate = mid - 90.0
            segment.pivot = (px + tangent[0] * drop, py + tangent[1] * drop)
        else:
            # Left half: turned the other way so it is never upside down.
            segment.rotate = mid + 90.0
            segment.pivot = (px - tangent[0] * drop, py - tangent[1] * drop)

    primitives: list[Primitive] = []
    fills = theme.mark.fills
    # The fills, by family, with no outline of their own.
    for segment in sorted(segments, key=lambda s: (s.depth, s.start)):
        primitives.append(
            Polygon(
                FILL_ROLE,
                points=_sector(cx, cy, segment.r_out, segment.r_in, segment.start, segment.end),
                fill=fills[segment.ancestor % len(fills)],
                fill_colour=theme.mark.colour_for(segment.ancestor % len(fills)),
                fill_opacity=0.5,
                region=True,
            )
        )

    core_share, ring_share, fine_share = theme.sunburst.weights
    core_w = max(WEIGHT_FLOORS[0], radius * core_share)
    ring_w = max(WEIGHT_FLOORS[1], radius * ring_share)
    fine_w = max(WEIGHT_FLOORS[2], radius * fine_share)

    def ink(points: tuple[tuple[float, float], ...]) -> None:
        primitives.append(
            Polygon(FILL_ROLE, points=points, fill="solid", fill_colour="currentColor", region=True)
        )

    # Ring boundaries: the arc where a node gives way to its children, medium weight.
    for segment in segments:
        if not segment.leaf:
            ink(_band(cx, cy, segment.r_out, segment.start, segment.end, ring_w))

    # The hub circle (medium) and the outer rim (heavy), tiled per first-ring sector
    # so neither is a full-circle polygon (which cannot carry a hole).
    for segment in segments:
        if segment.depth == 1:
            if hub > 0:
                ink(_band(cx, cy, hub, segment.start, segment.end, ring_w))
            ink(_band(cx, cy, radius - core_w / 2, segment.start, segment.end, core_w))

    # Radial dividers: a bar at each sector boundary, from where the split begins out to
    # the rim, weighted by how deep the split is — heaviest between first-ring cores.
    depth_at: dict[float, int] = {}
    for segment in segments:
        key = round(segment.start, 6)
        depth_at[key] = min(depth_at.get(key, segment.depth), segment.depth)
    for angle, depth in depth_at.items():
        w = core_w if depth == 1 else ring_w if depth == 2 else fine_w
        ink(_spoke(cx, cy, angle, edges[depth - 1], radius, w))

    if hub > 0 and hub_extents is not None:
        primitives.append(
            TextRun(
                FURNITURE_ROLE,
                x=cx,
                y=cy + (hub_extents.ascent - hub_extents.descent) / 2,
                text=document.centre,
                font=font,
                anchor="middle",
                size=hub_size,
            )
        )
    for segment in segments:
        primitives.append(
            TextRun(
                FURNITURE_ROLE,
                x=segment.pivot[0],
                y=segment.pivot[1],
                text=segment.text,
                font=font,
                anchor=segment.anchor,
                rotate=segment.rotate,
                size=segment.font,
            )
        )

    scene = Scene(
        width=width,
        height=width,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )
    return SunburstDrawing(
        scene=scene,
        centre=(cx, cy),
        radius=radius,
        hub=hub,
        rings=rings,
        segments=tuple(segments),
    )


def _leaves(node: SunburstNode) -> int:
    """How many terminal nodes are at or below `node` — its share of the circle."""
    return 1 if not node.children else sum(_leaves(child) for child in node.children)


def _at(cx: float, cy: float, distance: float, degrees: float) -> tuple[float, float]:
    """The point `distance` from the centre, `degrees` clockwise from twelve o'clock."""
    angle = math.radians(degrees)
    return cx + distance * math.sin(angle), cy - distance * math.cos(angle)


def _band(
    cx: float, cy: float, radius: float, low: float, high: float, weight: float
) -> tuple[tuple[float, float], ...]:
    """A thick arc at `radius`, `weight` units wide, from `low` to `high` degrees."""
    return _sector(cx, cy, radius + weight / 2, radius - weight / 2, low, high)


def _spoke(
    cx: float, cy: float, degrees: float, r0: float, r1: float, weight: float
) -> tuple[tuple[float, float], ...]:
    """A radial bar at `degrees`, `weight` units wide, from radius `r0` to `r1`."""
    tangent = (math.cos(math.radians(degrees)), math.sin(math.radians(degrees)))
    inner, outer = _at(cx, cy, r0, degrees), _at(cx, cy, r1, degrees)
    half = weight / 2
    return (
        (inner[0] + tangent[0] * half, inner[1] + tangent[1] * half),
        (outer[0] + tangent[0] * half, outer[1] + tangent[1] * half),
        (outer[0] - tangent[0] * half, outer[1] - tangent[1] * half),
        (inner[0] - tangent[0] * half, inner[1] - tangent[1] * half),
    )


def _sector(
    cx: float, cy: float, radius: float, hole: float, low: float, high: float
) -> tuple[tuple[float, float], ...]:
    """A ring segment as a polygon: the outer arc out, the inner arc back."""
    steps = max(2, math.ceil((high - low) / ARC_STEP))
    outer = [_at(cx, cy, radius, low + (high - low) * k / steps) for k in range(steps + 1)]
    if hole <= 0:
        return ((cx, cy), *outer)
    inner = [_at(cx, cy, hole, high - (high - low) * k / steps) for k in range(steps + 1)]
    return (*outer, *inner)


__all__ = ["SunburstDrawing", "sunburst_drawing", "sunburst_scene"]
