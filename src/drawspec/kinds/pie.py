"""The `pie` kind: the shares of one known total, as sectors of a circle.

A layout family of its own. The angles are arithmetic — each part's share of the
sum of the amounts, clockwise from twelve o'clock in the order written, the
`note` part last — so the decisions made here are about the labels.

**A sector is identified by its label, never by its fill.** Every sector carries
its name and its amount: inside it when the words fit there, with room to
spare from both edges and the rim, and otherwise beside the circle on a leader
from the middle of its arc. Outside labels go on the side of the circle their
sector is on, in angle order, pushed apart so none touches the next; the circle
is as large as the widest of them leaves room for. The fills are the theme's
mark patterns in turn, only so that neighbours differ — the last sector is
checked against the first, which it touches — and there is no legend, because
nothing asks a reader to match a fill to a key.

**`emphasis`** is outlined heavier, its words bold; **`note`** (the remainder)
is unfilled and dashed.

**A donut** is a theme's `[pie] shape = "donut"`: the same sectors with a hole,
their labels always outside, since a ring has no room for words.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.kinds.treemap import format_value
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import Document, PiePart
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, bold_lines, wrap
from drawspec.theme import Theme

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
PAD: Final = 4.0
"""The least space between an inside label and its sector's edges and rim."""

ELBOW: Final = 8.0
"""How far a leader runs straight out from the arc before it turns to its label."""

REACH: Final = 16.0
"""How far an outside label's near edge stands from the circle."""

LEADER_GAP: Final = 3.0
"""The space between a leader's end and its label."""

STACK_GAP: Final = 4.0
"""The least space between two outside labels on one side, one above the other."""

#: The most of the canvas width an outside label may take.
LABEL_SHARE: Final = 0.24

#: The largest and smallest the radius may be, as shares of the canvas width.
RADIUS_SHARE: Final = 0.25
RADIUS_FLOOR: Final = 0.12

#: A donut's hole, as a share of its radius.
HOLE_SHARE: Final = 0.55

#: Where an inside label is tried, as shares of the radius out from the centre.
INSIDE_DEPTHS: Final = (0.6, 0.5, 0.7, 0.4, 0.75, 0.8)

#: The most degrees one straight piece of an arc may span.
ARC_STEP: Final = 2.0

#: The role a leader is drawn in: a plain line, no head.
LEADER_ROLE: Final = "link"

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class PieDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    centre: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    hole: float = 0.0
    angles: tuple[tuple[float, float], ...] = ()
    """Each part's start and end, in degrees clockwise from twelve, in the order
    drawn: the parts as written, the `note` part moved last."""

    order: tuple[int, ...] = ()
    """Which written part each drawn sector is."""

    labels: tuple[Box, ...] = ()
    """Each drawn sector's label, in the order drawn."""

    inside: tuple[bool, ...] = ()
    """Whether each drawn sector's label is inside it."""

    leaders: tuple[tuple[tuple[float, float], ...], ...] = ()
    """Each outside label's leader, from the arc out."""

    fills: tuple[str, ...] = ()
    """Each drawn sector's fill pattern."""


@dataclass
class _Label:
    index: int
    block: TextBlock
    value: str
    middle: float
    width: float
    height: float
    inside: bool = False
    side: str = "right"
    x: float = 0.0
    y: float = 0.0


def pie_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a pie, or a donut if the theme says so."""
    return pie_drawing(document, theme, measurer).scene


def pie_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> PieDrawing:
    """Lay the pie out on the canvas.

    Raises:
        FitError: the labels beside the circle leave it too small to read, or a
            label has a word wider than the room it may take.
    """
    unit = theme.scale["body"] / 11
    width = document.width if document.width else theme.canvas.width
    donut = theme.pie.shape == "donut"
    pad = PAD * unit
    line = measurer.measure("0", theme.font.default, theme.scale["body"])

    written = document.pie_parts
    order = [index for index, part in enumerate(written) if part.role != "note"]
    order += [index for index, part in enumerate(written) if part.role == "note"]
    parts = [written[index] for index in order]
    total = sum(part.amount for part in parts)
    angles: list[tuple[float, float]] = []
    start = 0.0
    for part in parts:
        end = start + 360.0 * part.amount / total
        angles.append((start, end))
        start = end
    angles[-1] = (angles[-1][0], 360.0)

    labels: list[_Label] = []
    for position, part in enumerate(parts):
        block = _wrapped(part.text, width * LABEL_SHARE, theme, measurer, part.role == "emphasis")
        value = format_value(part.amount, document.unit) if document.values else ""
        value_width = (
            measurer.measure(value, theme.font.default, theme.scale["body"]).width if value else 0
        )
        low, high = angles[position]
        labels.append(
            _Label(
                index=position,
                block=block,
                value=value,
                middle=(low + high) / 2,
                width=max(block.width, value_width),
                height=block.height + (line.height if value else 0.0),
            )
        )

    # The radius: as large as the outside labels leave room for, settled in a few
    # passes because which labels fit inside depends on the radius.
    radius = width * RADIUS_SHARE
    for _ in range(4):
        for label in labels:
            label.inside = not donut and _fits_inside(label, angles[label.index], radius, pad)
            label.side = "right" if label.middle <= 180.0 else "left"
        left = _column(labels, "left")
        right = _column(labels, "right")
        reach = REACH * unit
        room = width - (left + reach if left else 0.0) - (right + reach if right else 0.0)
        settled = min(width * RADIUS_SHARE, room / 2)
        if math.isclose(settled, radius):
            break
        radius = settled
    if radius < width * RADIUS_FLOOR:
        raise FitError(
            f"the labels beside the pie leave it a radius of {max(radius, 0):.0f} units on a "
            f"canvas {width:.0f} wide. Shorten the longest names, or merge the smallest parts "
            f"into one `note` part."
        )
    left = _column(labels, "left")
    right = _column(labels, "right")
    reach = REACH * unit
    used = (left + reach if left else 0.0) + 2 * radius + (right + reach if right else 0.0)
    cx = (width - used) / 2 + (left + reach if left else 0.0) + radius
    cy = 0.0
    hole = radius * HOLE_SHARE if donut else 0.0

    # Inside labels at the depth that fits; outside ones in angle order per side.
    leaders: dict[int, tuple[tuple[float, float], ...]] = {}
    for label in labels:
        if label.inside:
            depth = _inside_depth(label, angles[label.index], radius, pad)
            px, py = _at(cx, cy, depth * radius, label.middle)
            label.x, label.y = px, py
    for side in ("right", "left"):
        column = sorted(
            (label for label in labels if not label.inside and label.side == side),
            key=lambda label: _at(cx, cy, radius, label.middle)[1],
        )
        floor = -math.inf
        for label in column:
            # The leader meets the name's first line at its middle.
            first = label.block.baseline(0) - 0.4 * label.block.ascent if label.block.lines else 0
            wanted = _at(cx, cy, radius + ELBOW * unit, label.middle)[1] - first
            top = max(wanted, floor + STACK_GAP * unit)
            label.y = top + label.height / 2
            floor = top + label.height
            edge = cx + radius + reach if side == "right" else cx - radius - reach
            label.x = edge
            leaders[label.index] = _leader(
                cx, cy, radius, label.middle, edge, top + first, side, unit
            )

    # Everything in the order it is drawn: the remainder first so a solid edge it
    # shares stays solid, the emphasised sector last so its heavier outline is.
    fills = _fills(parts, theme)
    rank = {"note": 0, "step": 1, "emphasis": 2}
    primitives: list[Primitive] = []
    for position in sorted(range(len(parts)), key=lambda k: (rank.get(parts[k].role, 1), k)):
        part = parts[position]
        low, high = angles[position]
        points = _sector(cx, cy, radius, hole, low, high)
        if part.role == "note":
            primitives.append(Polygon("note", points=points))
        else:
            primitives.append(
                Polygon(
                    "emphasis" if part.role == "emphasis" else "step",
                    points=points,
                    fill=fills[position],
                    fill_colour=theme.mark.colour_for(theme.mark.fills.index(fills[position])),
                )
            )
    for points in leaders.values():
        primitives.append(Path(LEADER_ROLE, points=points))

    texts: list[Primitive] = []
    boxes: list[Box] = []
    for label in labels:
        if label.inside:
            anchor, left_edge = "middle", label.x - label.width / 2
        elif label.side == "right":
            anchor, left_edge = "start", label.x
        else:
            anchor, left_edge = "end", label.x - label.width
        top = label.y - label.height / 2
        x = label.x
        texts.extend(_lines(label.block, x, top, anchor))
        if label.value:
            texts.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + label.block.height + line.ascent,
                    spans=(TextSpan(text=label.value, font=theme.font.default),),
                    level="body",
                    anchor=anchor,
                )
            )
        boxes.append((left_edge, top, left_edge + label.width, top + label.height))

    # The canvas: from the highest thing drawn to the lowest.
    lowest = min([cy - radius, *(box[1] for box in boxes)])
    highest = max([cy + radius, *(box[3] for box in boxes)])
    shift = -lowest
    scene = Scene(
        width=width,
        height=highest - lowest,
        primitives=tuple(_moved(primitive, shift) for primitive in (*primitives, *texts)),
        title=document.title,
        description=document.description,
    )
    return PieDrawing(
        scene=scene,
        centre=(cx, cy + shift),
        radius=radius,
        hole=hole,
        angles=tuple(angles),
        order=tuple(order),
        labels=tuple((a, b + shift, c, d + shift) for a, b, c, d in boxes),
        inside=tuple(label.inside for label in labels),
        leaders=tuple(
            tuple((x, y + shift) for x, y in leaders[label.index])
            for label in labels
            if not label.inside
        ),
        fills=tuple("" if part.role == "note" else fills[k] for k, part in enumerate(parts)),
    )


def _at(cx: float, cy: float, distance: float, degrees: float) -> tuple[float, float]:
    """The point `distance` from the centre, `degrees` clockwise from twelve o'clock."""
    angle = math.radians(degrees)
    return cx + distance * math.sin(angle), cy - distance * math.cos(angle)


def _sector(
    cx: float, cy: float, radius: float, hole: float, low: float, high: float
) -> tuple[tuple[float, float], ...]:
    """A sector, or a ring's piece, as a polygon: the arc in short straight pieces."""
    steps = max(2, math.ceil((high - low) / ARC_STEP))
    outer = [_at(cx, cy, radius, low + (high - low) * k / steps) for k in range(steps + 1)]
    if hole <= 0:
        return ((cx, cy), *outer)
    inner = [_at(cx, cy, hole, high - (high - low) * k / steps) for k in range(steps + 1)]
    return (*outer, *inner)


def _column(labels: list[_Label], side: str) -> float:
    return max(
        (label.width for label in labels if not label.inside and label.side == side), default=0.0
    )


def _fits_inside(label: _Label, span: tuple[float, float], radius: float, pad: float) -> bool:
    return _inside_depth(label, span, radius, pad) > 0


def _inside_depth(label: _Label, span: tuple[float, float], radius: float, pad: float) -> float:
    """The first depth at which the label sits clear inside its sector, or 0."""
    low, high = span
    for depth in INSIDE_DEPTHS:
        px, py = _at(0.0, 0.0, depth * radius, label.middle)
        corners = [
            (px + dx * label.width / 2, py + dy * label.height / 2)
            for dx in (-1, 1)
            for dy in (-1, 1)
        ]
        if all(_clear(x, y, low, high, radius, pad) for x, y in corners):
            return depth
    return 0.0


def _clear(x: float, y: float, low: float, high: float, radius: float, pad: float) -> bool:
    """Whether a point is inside the sector, at least `pad` from its rim and edges."""
    if math.hypot(x, y) > radius - pad:
        return False
    angle = math.degrees(math.atan2(x, -y)) % 360.0
    if not low <= angle <= high:
        return False
    if high - low >= 359.0:
        return True
    for edge in (low, high):
        ex, ey = _at(0.0, 0.0, 1.0, edge)
        along = x * ex + y * ey
        across = abs(x * ey - y * ex)
        distance = across if along > 0 else math.hypot(x, y)
        if distance < pad:
            return False
    return True


def _leader(
    cx: float,
    cy: float,
    radius: float,
    middle: float,
    edge: float,
    y: float,
    side: str,
    unit: float,
) -> tuple[tuple[float, float], ...]:
    """From the middle of the arc, straight out, then across to the label.

    The elbow moves further out until the run across to the label clears the
    circle, so a label pushed down its column never draws its leader over
    another sector.
    """
    start = _at(cx, cy, radius, middle)
    end_x = edge - LEADER_GAP * unit if side == "right" else edge + LEADER_GAP * unit
    out = ELBOW * unit
    while True:
        elbow = _at(cx, cy, radius + out, middle)
        if not _cuts_circle(elbow, (end_x, y), (cx, cy), radius) or out > 4 * radius:
            return (start, elbow, (end_x, y))
        out += ELBOW * unit


def _cuts_circle(
    first: tuple[float, float],
    second: tuple[float, float],
    centre: tuple[float, float],
    radius: float,
) -> bool:
    """Whether a segment passes inside the circle."""
    (x1, y1), (x2, y2), (cx, cy) = first, second, centre
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / length))
    return math.hypot(x1 + t * dx - cx, y1 + t * dy - cy) < radius - 1e-6


def _fills(parts: list[PiePart], theme: Theme) -> list[str]:
    """The theme's fills in turn, so that every two touching sectors differ.

    The circle closes: the last sector touches the first, so when the turn would
    give them the same fill the last takes one its two neighbours do not have.
    """
    filled = [k for k, part in enumerate(parts) if part.role != "note"]
    choices = theme.mark.fills
    found = [""] * len(parts)
    for order, position in enumerate(filled):
        found[position] = choices[order % len(choices)]
    touching = parts[-1].role != "note" and len(filled) > 2
    if touching and found[filled[-1]] == found[filled[0]]:
        taken = {found[filled[0]], found[filled[-2]]}
        found[filled[-1]] = next(choice for choice in choices if choice not in taken)
    return found


def _wrapped(
    text: str, width: float, theme: Theme, measurer: TextMeasurer, bold: bool
) -> TextBlock:
    words = bold_lines(text) if bold else text
    try:
        return wrap(words, width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the label {text[:40]!r} has a word wider than the {width:.0f} units a pie's "
            f"label can take. Shorten it, or give the diagram more width."
        ) from error


def _lines(block: TextBlock, x: float, top: float, anchor: str) -> list[TextLine]:
    """A wrapped block from `top` down, anchored at `x`, its spans kept."""
    lines: list[TextLine] = []
    for index, wrapped in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in wrapped.spans
            if span.text
        )
        if spans:
            lines.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="body",
                    anchor=anchor,
                )
            )
    return lines


def _moved(primitive: Primitive, shift: float) -> Primitive:
    """A primitive moved down by `shift`."""
    if isinstance(primitive, Polygon | Path):
        points = tuple((x, y + shift) for x, y in primitive.points)
        return replace(primitive, points=points)
    if isinstance(primitive, TextLine):
        return replace(primitive, y=primitive.y + shift)
    return primitive


__all__ = ["PieDrawing", "pie_drawing", "pie_scene"]
