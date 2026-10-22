"""The `sunburst` kind: a hierarchy as concentric rings of sectors, read outward.

A layout family of its own. The tree is the whole input — a node is `{text,
children?}`, with an optional `centre` hub in the middle — and every decision
here is geometry derived from it, never a number an author wrote.

**Every terminal node takes an equal angle.** The circle is divided into one
slice per leaf, and a parent's span is the sum of its leaves', so a core with
six descendants is six times the wedge of a core with one. The order is the
order written, clockwise from twelve o'clock, and it is the same every render.

**The rings are sized to the words they hold, and need not be equal.** A ring's
radial band is made as wide as the longest label in it, in proportion — so an
outer ring of long words is wider than an inner ring of short ones, which is why
the wheel reads. The labels are set at one size, the theme's body size, and only
a label that will not fit its band or its sector is stepped down, to a floor
below which the wheel is refused rather than drawn illegibly.

**No label is ever upside down.** Each is rotated to its sector's mid-angle and
read from the middle outward; on the left half it is turned the other way so the
reader never has to. That orientation is decided here, not by the author.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.scene import Ellipse, Polygon, Primitive, Scene, TextRun
from drawspec.schema import Document, SunburstNode
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The role a sector is drawn in: a plain outlined step, filled by its family.
SECTOR_ROLE: Final = "step"

#: The role the hub disc is drawn in.
HUB_ROLE: Final = "step"

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when a label is stepped down.
PAD: Final = 3.0
"""The least space between a label and its band's rim, and its sector's edges."""

#: The layout's own lower bound on a label, as a share of the body size. The
#: effective floor is this or the theme's `min_legible_size`, whichever is
#: larger: below it the wheel is refused rather than drawn too small to read.
FLOOR_SHARE: Final = 0.5

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

    # The hub, if there is one, is sized to its words; the rings fill the rest.
    hub = 0.0
    hub_extents = None
    if document.centre:
        hub_extents = measurer.measure(document.centre, font, base)
        hub = hub_extents.width / 2 + 2 * pad

    # Ring bands, in proportion to the longest label each holds — so an outer ring
    # of long words is wider than an inner ring of short ones.
    widest = [
        max(
            (measurer.measure(s.text, font, base).width for s in segments if s.depth == depth),
            default=base,
        )
        for depth in range(1, rings + 1)
    ]
    span = max(radius - hub, unit)
    total = sum(widest) or 1.0
    edges = [hub]
    for measure in widest:
        edges.append(edges[-1] + span * measure / total)
    for segment in segments:
        segment.r_in = edges[segment.depth - 1]
        segment.r_out = edges[segment.depth]

    # Each label: set at the body size, stepped down only to fit its band (the
    # word, read radially) and its sector (the line height, across the arc).
    floor = max(base * FLOOR_SHARE, theme.canvas.min_legible_size)
    for segment in segments:
        extents = measurer.measure(segment.text, font, base)
        band = segment.r_out - segment.r_in - 2 * pad
        mid = (segment.start + segment.end) / 2
        r_mid = (segment.r_in + segment.r_out) / 2
        chord = 2 * r_mid * math.sin(math.radians((segment.end - segment.start) / 2)) - 2 * pad
        line = extents.height
        fit = min(
            1.0,
            band / extents.width if extents.width > 0 else 1.0,
            chord / line if line > 0 else 1.0,
        )
        size = base * fit
        if size < floor:
            raise FitError(
                f"the label {segment.text[:40]!r} cannot be made to fit its sector on a "
                f"sunburst {width:.0f} wide, even stepped down to {floor:.1f} units, the "
                f"smallest legible type. "
                f"Shorten it, give the wheel a `centre` hub to push the rings out, or give a "
                f"node fewer children."
            )
        segment.font = size
        drop = (extents.ascent - extents.descent) * size / base / 2
        tangent = (math.cos(math.radians(mid)), math.sin(math.radians(mid)))
        if mid <= 180.0:
            # Right half: read inner to outer, upright, head tilted left.
            segment.anchor, segment.rotate = "start", mid - 90.0
            px, py = _at(cx, cy, segment.r_in + pad, mid)
            segment.pivot = (px + tangent[0] * drop, py + tangent[1] * drop)
        else:
            # Left half: turned the other way so it is never upside down — it reads
            # outer to inner, its first letter at the rim.
            segment.anchor, segment.rotate = "start", mid + 90.0
            px, py = _at(cx, cy, segment.r_out - pad, mid)
            segment.pivot = (px - tangent[0] * drop, py - tangent[1] * drop)

    primitives: list[Primitive] = []
    fills = theme.mark.fills
    for segment in sorted(segments, key=lambda s: (s.depth, s.start)):
        pattern = fills[segment.ancestor % len(fills)]
        primitives.append(
            Polygon(
                SECTOR_ROLE,
                points=_sector(cx, cy, segment.r_out, segment.r_in, segment.start, segment.end),
                fill=pattern,
                fill_colour=theme.mark.colour_for(segment.ancestor % len(fills)),
                fill_opacity=0.5,
            )
        )
    if hub > 0 and hub_extents is not None:
        primitives.append(Ellipse(HUB_ROLE, cx=cx, cy=cy, rx=hub, ry=hub))
        primitives.append(
            TextRun(
                FURNITURE_ROLE,
                x=cx,
                y=cy + (hub_extents.ascent - hub_extents.descent) / 2,
                text=document.centre,
                font=font,
                anchor="middle",
                size=base,
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
