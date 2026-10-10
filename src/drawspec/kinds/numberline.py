"""The `numberline` kind: values and ranges on one scale.

A layout family of its own, and a narrow one: every horizontal decision is the
scale's, so the only choices made here are vertical — which row a point's words
go in, and how high each range's track sits.

**The axis** runs the width of the canvas with an arrowhead at each end, because
a number line goes on. `min` and `max` sit a little inside the arrowheads, so a
range that runs on past either has somewhere to point. Ticks cross the line at
every step with their numbers under them; a scale named by its `ends` has no
ticks, and the two words sit under the arrowheads instead.

**Ranges** are stacked in tracks above the axis in the order written, the last
nearest the line — the answer under its parts, the way an overlap is worked on
paper. Each is a heavy line from one end to the other, its words centred over
it. An end the range includes is a filled dot and one it excludes a hollow one,
or `[` and `(` under the theme's `[numberline] ends = "brackets"`; a missing end
runs to the arrowhead's side and ends in an arrow of its own.

**Points** are dots on the axis line itself. Their words go where they fit,
nearest the line first: directly above, directly under the numbers, then rows
further out with a thin leader back to the dot. A slot is taken only if the
words touch no other words and the leader crosses none — the pH scale's fifteen
substances settle into alternating rows above and below, as the textbook draws
them. A hollow point breaks the axis line, so it reads as a hole and not as a
ring threaded on a wire.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Final

from drawspec.charts import AXIS_ROLE, FURNITURE_ROLE, Scale, _format_value, _nice_step
from drawspec.errors import FitError
from drawspec.routing import end_marker
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import Document, NumberAxis, NumberPoint, NumberRange
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
OVERHANG: Final = 26.0
"""How far each arrowhead's tip lies beyond `min` or `max`."""

TICK: Final = 4.5
"""How far a tick reaches above and below the line."""

DOT: Final = 4.0
"""A point's or a range end's radius; an emphasised one is larger, a note smaller."""

FOCAL: Final = 1.3
NOTE: Final = 0.7

BAR: Final = 1.8
"""Half the thickness of an emphasised range's bar, drawn solid."""

BRACKET: Final = 8.0
"""Half the height of a bracket end, and (times `BRACKET_DEPTH`) its depth."""

BRACKET_DEPTH: Final = 0.45

GAP: Final = 5.0
"""The space between a mark and its words, and between two rows of words."""

TRACK_GAP: Final = 7.0
"""The space between two tracks, and between the lowest track and the points' words."""

DAYLIGHT: Final = 7.0
"""The least space between two labels side by side."""

LEAD_CLEAR: Final = 2.0
"""How far a leader stops short of the dot and of the words it joins."""

#: The most of the canvas width a point's words may take before they wrap.
LABEL_SHARE: Final = 0.24

#: How many rows a point's words may move out to, on each side of the line.
ROWS: Final = 5

#: Roughly how many ticks a scale gets when the author names no step. A number
#: line is read by counting along it, so more than a chart's five.
TARGET_TICKS: Final = 10

#: A negative number's sign: the minus sign, not the hyphen a keyboard types.
MINUS: Final = "\u2212"

#: The role the axis line and its arrowheads are drawn in.
LINE_ROLE: Final = "flow"

#: The role a leader from a point to its words is drawn in: a thin line, no head.
LEADER_ROLE: Final = "link"

#: The roles a range's line takes: the default heavy line, and a note's dashed one.
RANGE_ROLES: Final = {"step": "strong", "note": "aside", "emphasis": "strong"}

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class NumberlineDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    scale: Scale
    """The axis: a value's x is `scale.to_pixels(value)`."""

    axis_y: float
    dots: tuple[tuple[float, float, float, bool], ...] = ()
    """Each point's dot — x, y, radius, hollow — in document order."""

    labels: dict[int, Box] = field(default_factory=dict)
    """Each labelled point's words — left, top, right, bottom — by its index."""

    sides: dict[int, tuple[str, int]] = field(default_factory=dict)
    """Where each labelled point's words went: `above` or `below`, and the row."""

    tracks: tuple[tuple[float, float, float], ...] = ()
    """Each range's line — left, right, y — in document order."""

    ends: tuple[tuple[str, str], ...] = ()
    """What each range's two ends are drawn as: `dot`, `ring`, `[`, `(`, or `arrow`."""

    ticks: tuple[float, ...] = ()
    """The tick values, in order."""


def numberline_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a number line."""
    return numberline_drawing(document, theme, measurer).scene


def numberline_drawing(
    document: Document, theme: Theme, measurer: TextMeasurer
) -> NumberlineDrawing:
    """Lay the number line out on the canvas.

    Raises:
        FitError: two points are too close to be told apart, the tick numbers
            touch, or a point's words find no row that keeps clear of the rest.
    """
    axis = document.number_axis
    assert axis is not None  # a validated numberline always has one
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    label_size = theme.scale["label"]
    number_line = measurer.measure("0", theme.font.default, label_size)
    overhang = OVERHANG * unit
    scale = Scale(axis.minimum, axis.maximum, overhang, width - overhang)
    tick = TICK * unit
    gap = GAP * unit

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    obstacles: list[Box] = []

    # The axis: ticks and their numbers, or the two named ends.
    band_top = tick + gap
    band_bottom = band_top + number_line.height
    tick_values: tuple[float, ...] = ()
    if axis.ends:
        low_word, high_word = axis.ends[0], axis.ends[-1]
        low_width = measurer.measure(low_word, theme.font.default, label_size).width
        high_width = measurer.measure(high_word, theme.font.default, label_size).width
        if low_width + high_width + DAYLIGHT * unit > width:
            raise FitError(
                f"the scale's ends {low_word!r} and {high_word!r} are wider together than the "
                f"canvas. Shorten them."
            )
        for text, x, anchor, wide in (
            (low_word, 0.0, "start", low_width),
            (high_word, width, "end", high_width),
        ):
            texts.append(_line(text, x, band_top + number_line.ascent, "label", anchor, theme))
            left = x if anchor == "start" else x - wide
            obstacles.append((left, band_top, left + wide, band_bottom))
    else:
        tick_values = _tick_values(axis)
        previous = -math.inf
        step = axis.step or _nice_step((axis.maximum - axis.minimum) / TARGET_TICKS)
        for value in tick_values:
            text = _format_value(value, step).replace("-", MINUS)
            wide = measurer.measure(text, theme.font.default, label_size).width
            x = scale.to_pixels(value)
            if x - wide / 2 < previous + gap:
                raise FitError(
                    f"the tick numbers touch: {len(tick_values)} of them do not fit across the "
                    f"canvas. Take a larger `step`, or a narrower scale."
                )
            previous = x + wide / 2
            texts.append(_line(text, x, band_top + number_line.ascent, "label", "middle", theme))
            obstacles.append((x - wide / 2, band_top, x + wide / 2, band_bottom))

    # Points: their dots, then their words, nearest the line first.
    dots = [_dot(point, scale, unit) for point in document.number_points]
    order = sorted(range(len(dots)), key=lambda index: dots[index][0])
    for first, second in pairwise(order):
        (x1, _, r1, _), (x2, _, r2, _) = dots[first], dots[second]
        if x2 - x1 < r1 + r2 + unit:
            raise FitError(
                f"points {first} and {second} (at {document.number_points[first].at:g} and "
                f"{document.number_points[second].at:g}) draw as one dot at this width. Merge "
                f"them into one point, or narrow the scale."
            )
    blocks = {
        index: _wrapped(point.text, point.role, width * LABEL_SHARE, theme, measurer)
        for index, point in enumerate(document.number_points)
        if point.text
    }
    pitch = max((block.height for block in blocks.values()), default=0.0)
    reach = max((radius for _, _, radius, _ in dots), default=DOT * unit)
    above_bottom = -(max(reach, tick) + gap)
    # With no numbers under the line, the band holds only the two end words at the
    # edges — obstacles like any other — so the first row below sits right under it.
    below_top = (band_bottom if tick_values else tick) + gap

    def slot(side: str, row: int) -> tuple[float, float]:
        """The top and bottom of a row of words."""
        if side == "above":
            bottom = above_bottom - row * (pitch + gap)
            return bottom - pitch, bottom
        top = below_top + row * (pitch + gap)
        return top, top + pitch

    labels: dict[int, Box] = {}
    sides: dict[int, tuple[str, int]] = {}
    leaders: list[tuple[float, float, float]] = []
    daylight = DAYLIGHT * unit
    clear = LEAD_CLEAR * unit
    for index in order:
        if index not in blocks:
            continue
        block = blocks[index]
        x, _, radius, _ = dots[index]
        left = min(max(x - block.width / 2, 0.0), width - block.width)
        placed = False
        for row in range(ROWS):
            for side in ("above", "below"):
                top, bottom = slot(side, row)
                top = bottom - block.height if side == "above" else top
                bottom = top + block.height
                box = (left, top, left + block.width, bottom)
                leader: tuple[float, float, float] | None = None
                if row > 0:
                    leader = (
                        (x, bottom + clear, -radius - clear)
                        if side == "above"
                        else (x, radius + clear, top - clear)
                    )
                if _blocked(box, leader, labels.values(), obstacles, leaders, daylight):
                    continue
                labels[index] = box
                sides[index] = (side, row)
                if leader is not None:
                    leaders.append(leader)
                    primitives.append(Path(LEADER_ROLE, points=((x, leader[1]), (x, leader[2]))))
                texts.extend(_centred(block, left + block.width / 2, top))
                placed = True
                break
            if placed:
                break
        if not placed:
            raise FitError(
                f"point {index}'s words {document.number_points[index].text[:40]!r} find no "
                f"row within {ROWS} of the line that keeps clear of the others. Shorten the "
                f"labels, or split the line into two."
            )

    # Ranges, in tracks above everything the points use, the last nearest the line.
    ceiling = min(
        [-max(reach, tick)] + [box[1] for box in labels.values()] + [lead[2] for lead in leaders]
    )
    brackets = theme.numberline.ends == "brackets"
    tracks: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(document.number_ranges)
    ends: list[tuple[str, str]] = [("", "")] * len(document.number_ranges)
    floor = ceiling - TRACK_GAP * unit
    for index in reversed(range(len(document.number_ranges))):
        entry = document.number_ranges[index]
        radius = _radius(entry.role, unit)
        half = BRACKET * unit if brackets else radius
        y = floor - half
        left = scale.to_pixels(entry.start) if entry.start is not None else 0.0
        right = scale.to_pixels(entry.end) if entry.end is not None else width
        tracks[index] = (left, right, y)
        drawn, marks = _range(entry, left, right, y, width, brackets, theme, unit)
        primitives.extend(drawn)
        ends[index] = marks
        top = y - half
        if entry.text:
            block = _wrapped(entry.text, entry.role, width, theme, measurer)
            middle = (left + right) / 2
            middle = min(max(middle, block.width / 2), width - block.width / 2)
            top = y - half - gap - block.height
            texts.extend(_centred(block, middle, top))
        floor = top - TRACK_GAP * unit

    # The axis line, broken round each hollow point, with an arrowhead at each end.
    holes = sorted((x - radius, x + radius) for x, _, radius, hollow in dots if hollow)
    start = 0.0
    pieces: list[tuple[float, float]] = []
    for low, high in holes:
        pieces.append((start, low))
        start = high
    pieces.append((start, width))
    for low, high in pieces:
        if high - low > 0.5:
            primitives.append(Path(LINE_ROLE, points=((low, 0.0), (high, 0.0))))
    primitives.extend(end_marker("arrow", (width / 2, 0.0), (0.0, 0.0), LINE_ROLE, theme))
    primitives.extend(end_marker("arrow", (width / 2, 0.0), (width, 0.0), LINE_ROLE, theme))
    for value in tick_values:
        x = scale.to_pixels(value)
        if any(low < x < high for low, high in holes):
            continue
        primitives.append(Path(AXIS_ROLE, points=((x, -tick), (x, tick))))

    # The dots last, so a filled one covers the line it sits on.
    for point, (x, y, radius, hollow) in zip(document.number_points, dots, strict=True):
        primitives.append(_disc(point.role, x, y, radius, hollow))

    # The caption: what the numbers measure, under everything below the line.
    lowest = max([band_bottom] + [box[3] for box in labels.values()])
    caption = _caption(axis)
    bottom = lowest
    if caption:
        caption_top = lowest + gap * 1.5
        texts.append(
            _line(caption, width / 2, caption_top + number_line.ascent, "label", "middle", theme)
        )
        bottom = caption_top + number_line.height

    top = floor + TRACK_GAP * unit - gap
    shift = -top
    everything = [moved(primitive, 0.0, shift) for primitive in (*primitives, *texts)]
    scene = Scene(
        width=width,
        height=bottom + gap - top,
        primitives=tuple(everything),
        title=document.title,
        description=document.description,
    )
    return NumberlineDrawing(
        scene=scene,
        scale=scale,
        axis_y=shift,
        dots=tuple((x, y + shift, radius, hollow) for x, y, radius, hollow in dots),
        labels={
            index: (left, top + shift, right, bottom + shift)
            for index, (left, top, right, bottom) in labels.items()
        },
        sides=sides,
        tracks=tuple((left, right, y + shift) for left, right, y in tracks),
        ends=tuple(ends),
        ticks=tick_values,
    )


def _tick_values(axis: NumberAxis) -> tuple[float, ...]:
    """Every multiple of the step from `min` to `max`."""
    step = axis.step or _nice_step((axis.maximum - axis.minimum) / TARGET_TICKS)
    first = math.ceil(axis.minimum / step - 1e-9)
    values: list[float] = []
    count = first
    while count * step <= axis.maximum + step * 1e-9:
        values.append(round(count * step, 10))
        count += 1
    return tuple(values)


def _radius(role: str, unit: float) -> float:
    factor = FOCAL if role == "emphasis" else NOTE if role == "note" else 1.0
    return DOT * unit * factor


def _dot(point: NumberPoint, scale: Scale, unit: float) -> tuple[float, float, float, bool]:
    return (scale.to_pixels(point.at), 0.0, _radius(point.role, unit), point.open)


def _disc(role: str, x: float, y: float, radius: float, hollow: bool) -> Primitive:
    """A dot: filled with the page's ink, or a ring with nothing inside."""
    outline = "emphasis" if role == "emphasis" else "step"
    if hollow:
        return Ellipse(outline, cx=x, cy=y, rx=radius, ry=radius)
    return Ellipse(
        outline, cx=x, cy=y, rx=radius, ry=radius, fill="solid", fill_colour="currentColor"
    )


def _range(
    entry: NumberRange,
    left: float,
    right: float,
    y: float,
    width: float,
    brackets: bool,
    theme: Theme,
    unit: float,
) -> tuple[list[Primitive], tuple[str, str]]:
    """A range's line, its two end marks, and what those marks are."""
    role = RANGE_ROLES[entry.role]
    radius = _radius(entry.role, unit)
    found: list[Primitive] = []
    marks: list[str] = []
    shaft = [left, right]
    for side, value, hollow in ((0, entry.start, entry.start_open), (1, entry.end, entry.end_open)):
        x = shaft[side]
        inward = 1.0 if side == 0 else -1.0
        if value is None:
            marks.append("arrow")
            continue
        if brackets:
            marks.append("(" if hollow else "[")
            found.append(_bracket(x, y, inward, hollow, unit))
        else:
            marks.append("ring" if hollow else "dot")
            if hollow:
                shaft[side] = x + inward * radius
    head = theme.head_length_for(role)
    low, high = shaft
    if entry.start is None:
        low = head * 0.5
    if entry.end is None:
        high = width - head * 0.5
    if entry.role == "emphasis":
        half = BAR * unit
        bar_low = left + head if entry.start is None else low
        bar_high = right - head if entry.end is None else high
        found.insert(
            0,
            Polygon(
                "step",
                points=(
                    (bar_low, y - half),
                    (bar_high, y - half),
                    (bar_high, y + half),
                    (bar_low, y + half),
                ),
                fill="solid",
                fill_colour="currentColor",
            ),
        )
    else:
        found.insert(0, Path(role, points=((low, y), (high, y))))
    if entry.start is None:
        found.extend(end_marker("arrow", (right, y), (0.0, y), role, theme))
    if entry.end is None:
        found.extend(end_marker("arrow", (left, y), (width, y), role, theme))
    if not brackets:
        for value, x, hollow in (
            (entry.start, left, entry.start_open),
            (entry.end, right, entry.end_open),
        ):
            if value is not None:
                found.append(_disc(entry.role, x, y, radius, hollow))
    return found, (marks[0], marks[1])


def _bracket(x: float, y: float, inward: float, hollow: bool, unit: float) -> Primitive:
    """`[` or `(` at `x`, opening towards the inside of the range."""
    half = BRACKET * unit
    depth = half * BRACKET_DEPTH * inward
    points: tuple[tuple[float, float], ...]
    if not hollow:
        points = ((x + depth, y - half), (x, y - half), (x, y + half), (x + depth, y + half))
    else:
        # A parenthesis: an arc through the end's value, its tips bent inward.
        steps = 10
        points = tuple(
            (
                x + depth * (1 - math.cos(angle)),
                y + half * math.sin(angle),
            )
            for angle in (
                -math.pi / 2.6 + index * (2 * math.pi / 2.6) / steps for index in range(steps + 1)
            )
        )
    return Path("strong", points=points)


def _blocked(
    box: Box,
    leader: tuple[float, float, float] | None,
    placed: Iterable[Box],
    obstacles: list[Box],
    leaders: list[tuple[float, float, float]],
    daylight: float,
) -> bool:
    """Whether words at `box`, with their leader, would touch anything already drawn."""
    boxes = list(placed)
    for other in boxes:
        if _touch(box, other, daylight, daylight / 2):
            return True
    for other in obstacles:
        if _touch(box, other, daylight / 2, 0.0):
            return True
    for x, low, high in leaders:
        if (
            box[0] - daylight / 2 <= x <= box[2] + daylight / 2
            and box[1] <= max(low, high)
            and box[3] >= min(low, high)
        ):
            return True
    if leader is not None:
        x, low, high = leader
        for other in [*boxes, *obstacles]:
            if (
                other[0] - daylight / 2 <= x <= other[2] + daylight / 2
                and other[1] <= max(low, high)
                and other[3] >= min(low, high)
            ):
                return True
    return False


def _touch(first: Box, second: Box, across: float, down: float) -> bool:
    return (
        first[0] < second[2] + across
        and second[0] < first[2] + across
        and first[1] < second[3] + down
        and second[1] < first[3] + down
    )


def _caption(axis: NumberAxis) -> str:
    if axis.label and axis.unit:
        return f"{axis.label} ({axis.unit})"
    return axis.label or axis.unit


def _wrapped(text: str, role: str, width: float, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    words = f"**{text.replace('**', '')}**" if role == "emphasis" else text
    try:
        return wrap(words, width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the label {text[:40]!r} has a word wider than the {width:.0f} units it can take. "
            f"Shorten it, or give the diagram more width."
        ) from error


def _line(text: str, x: float, y: float, level: str, anchor: str, theme: Theme) -> TextLine:
    return TextLine(
        FURNITURE_ROLE,
        x=x,
        y=y,
        spans=(TextSpan(text=text, font=theme.font.default),),
        level=level,
        anchor=anchor,
    )


def _centred(block: TextBlock, x: float, top: float) -> list[TextLine]:
    """A wrapped block centred on `x`, from `top` down, its spans kept."""
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
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="body",
                    anchor="middle",
                )
            )
    return found


__all__ = ["NumberlineDrawing", "numberline_drawing", "numberline_scene"]
