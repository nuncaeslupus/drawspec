"""The `wardley` kind: components placed by value chain and evolution.

A layout family of its own. A Wardley map's essence is a plane — how visible a
component is to the user, down the page, against how evolved it is, across it —
and every point on that plane is derived here from words, never written:

**Down the page is the value chain.** The anchors (the users, or their needs)
are row 0. Every component sits one row below the lowest thing that needs it —
the longest path down from an anchor — so each dependency line runs downward,
and the most visible components are the ones nearest the user. A component may
be sunk further with `depth`, never raised above what needs it.

**Across the page is evolution, by name.** The axis is Wardley's four stages —
genesis, custom-built, product, commodity — each cut into thirds, so `evolution`
is one of twelve named places (`early product`, `product`, `late product`). A
component is drawn at its place's centre; two on the same row and the same place
share it side by side, in the order written.

**The lines are straight, and the labels move.** Dependencies are straight
lines, dot to dot, as Wardley draws them. A dot that sits on a line between two
others is slid along its place to let the line by. Each name is then set beside
its dot in the nearest of its spots that is inside the map and clear of every
dot, line, bar and arrow, the names searched together so no two meet; a crowded
map is drawn taller, and a name with nowhere to go is refused rather than drawn
over something.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.routing import Route, edge_primitives
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import (
    WARDLEY_EVOLUTION,
    WARDLEY_STAGES,
    Document,
    WardleyComponent,
    wardley_depths,
)
from drawspec.text.measure import Extents, TextMeasurer
from drawspec.text.wrap import parse_spans, wrap
from drawspec.theme import Theme

#: A dependency: a plain line, no head, as Wardley draws one.
LINK_ROLE: Final = "link"

#: The two axes, each with an arrow towards *more*: more visible, more evolved.
AXIS_ROLE: Final = "flow"

#: The line between two stages: dashed and quiet, so the map reads over it.
DIVIDER_ROLE: Final = "aside"

#: A component moving: dashed, with an open head, to where it is going.
EVOLVE_ROLE: Final = "weak"

#: A component's dot, and the ring round a note's number.
DOT_ROLE: Final = "step"

#: Where a component is going: its dot again, dashed and light, with no name.
GHOST_ROLE: Final = "note"

#: Lengths in units, a unit being the body size over eleven.
RADIUS: Final = 4.5
"""A component's dot."""

ROWS: Final = (5.0, 6.5, 8.0)
"""The distance between two rows of the value chain, in label line heights: the
first that lets every name find a place. A crowded map is drawn taller before it
is refused, since its height is free and its width is the page's."""

GAP: Final = 3.0
"""Daylight between a name and its dot, past the dot's own radius."""

DAYLIGHT: Final = 2.0
"""The least space kept between a name and anything else."""

BAR: Final = 3.0
"""An inertia bar's thickness."""

BAR_GAP: Final = 3.0
"""Space between a dot and its inertia bar."""

#: How long an inertia bar is, as a multiple of the dot's radius.
BAR_SPAN: Final = 3.4

#: How many slides a blocking dot is tried at, each a share of its place's width.
SLIDES: Final = (1 / 3, -1 / 3, 1 / 6, -1 / 6)


@dataclass
class _Dot:
    """A component, or the ghost of where one is going, as it is laid out."""

    key: str
    text: str
    row: int
    slot: int
    x: float = 0.0
    y: float = 0.0
    ghost: bool = False
    lo: float = 0.0
    hi: float = 0.0
    """How far the dot may slide along its place to let a line by."""


@dataclass(frozen=True)
class WardleyDrawing:
    """The finished geometry, for tests and the scene."""

    scene: Scene
    rows: dict[str, int] = field(default_factory=dict)
    centres: dict[str, tuple[float, float]] = field(default_factory=dict)
    labels: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    plot: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


Box = tuple[float, float, float, float]

#: A name's place: its box, its anchor point and its anchor.
_Spot = tuple[Box, float, float, str]

#: A straight line, start to end.
_Segment = tuple[tuple[float, float], tuple[float, float]]

#: How many spots the name search may try before it refuses the map.
SEARCH_BUDGET: Final = 50_000


def wardley_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a Wardley map."""
    return wardley_drawing(document, theme, measurer).scene


def wardley_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> WardleyDrawing:
    """Lay the map out, at the first row spacing in `ROWS` that fits.

    Raises:
        FitError: a name has nowhere to sit clear of the rest, two components on
            one place cannot be set apart, or a line cannot be cleared of a dot.
    """
    failure: FitError | None = None
    for row in ROWS:
        try:
            return _drawing(document, theme, measurer, row)
        except FitError as error:
            failure = error
    assert failure is not None
    raise failure


def _drawing(
    document: Document, theme: Theme, measurer: TextMeasurer, row: float
) -> WardleyDrawing:
    """The map with its rows `row` label lines apart."""
    unit = theme.scale["body"] / 11
    radius = RADIUS * unit
    gap = GAP * unit
    pad = theme.box.padding.top
    font = theme.font.default
    level = "label"
    size = theme.scale[level]
    line = measurer.measure("Ag", font, size)
    words = theme.wardley
    width = document.width if document.width else theme.canvas.width

    components = {component.id: component for component in document.wardley_components}
    rows = wardley_depths(
        {anchor.id: anchor.needs for anchor in document.wardley_anchors},
        {component.id: component.needs for component in components.values()},
        {c.id: c.depth for c in components.values() if c.depth is not None},
    )
    depth = max(rows.values(), default=1)

    # The frame: a gutter for the value-chain axis's words on the left, the stage
    # names and the axis's name under the plot, the notes under those.
    plot_left = line.height + 2 * pad
    plot_right = width
    plot_top = 0.0
    spacing = row * line.height
    first = plot_top + spacing * 0.5
    axis_words = sum(
        measurer.measure(text, font, size).width
        for text in (words.visible, words.chain, words.invisible)
    )
    plot_bottom = max(first + depth * spacing + spacing * 0.6, plot_top + axis_words + 4 * pad)
    slot = (plot_right - plot_left) / len(WARDLEY_EVOLUTION)
    quarter = (plot_right - plot_left) / len(WARDLEY_STAGES)

    def row_y(row: int) -> float:
        return first + row * spacing

    # Dots: each component at its place's centre, ghosts where they are going;
    # several on one row and place share it, side by side in the order written.
    dots: dict[str, _Dot] = {}
    for component in components.values():
        dots[component.id] = _Dot(
            component.id,
            component.text,
            rows[component.id],
            WARDLEY_EVOLUTION.index(component.evolution),
        )
        if component.evolves:
            dots[_ghost(component.id)] = _Dot(
                _ghost(component.id),
                component.text,
                rows[component.id],
                WARDLEY_EVOLUTION.index(component.evolves),
                ghost=True,
            )
    shared: dict[tuple[int, int], list[_Dot]] = {}
    for dot in dots.values():
        shared.setdefault((dot.row, dot.slot), []).append(dot)
    for (on_row, place), group in shared.items():
        left = plot_left + place * slot
        step = slot / len(group)
        if step < 3 * radius:
            raise FitError(
                f"{len(group)} components share the place {WARDLEY_EVOLUTION[place]!r} on "
                f"row {on_row} of a map {width:.0f} wide, too many to set side by side. Move one "
                f"`early` or `late`, sink one with `depth`, or widen the map."
            )
        for index, dot in enumerate(group):
            dot.x = left + step * (index + 0.5)
            dot.y = row_y(on_row)
            dot.lo = left + step * index + radius
            dot.hi = left + step * (index + 1) - radius

    # Anchors: across the top row, each over the middle of what it needs, pushed
    # apart when their names would meet.
    anchor_boxes: dict[str, Box] = {}
    anchor_lines: dict[str, TextLine] = {}
    anchor_x: list[tuple[float, float, str]] = []
    order_of = {anchor.id: index for index, anchor in enumerate(document.wardley_anchors)}
    for anchor in document.wardley_anchors:
        needed = [dots[need].x for need in anchor.needs if need in dots]
        x = sum(needed) / len(needed) if needed else (plot_left + plot_right) / 2
        anchor_x.append((x, _width(anchor.text, theme, measurer, bold=True), anchor.id))
    anchor_x.sort(key=lambda entry: (round(entry[0], 3), order_of[entry[2]]))
    placed_x: list[tuple[float, float, str]] = []
    for x, wide, ident in anchor_x:
        x = max(x, plot_left + pad + wide / 2)
        if placed_x:
            last_x, last_wide, _ = placed_x[-1]
            x = max(x, last_x + last_wide / 2 + wide / 2 + 3 * pad)
        placed_x.append((x, wide, ident))
    overflow = placed_x[-1][0] + placed_x[-1][1] / 2 - (plot_right - pad) if placed_x else 0.0
    if overflow > 0:
        placed_x = [(x - overflow, wide, ident) for x, wide, ident in placed_x]
        if placed_x[0][0] - placed_x[0][1] / 2 < plot_left + pad:
            raise FitError(
                f"the anchors' names do not fit side by side across a map {width:.0f} wide. "
                f"Shorten them, or widen the map."
            )
    texts = {anchor.id: anchor.text for anchor in document.wardley_anchors}
    for x, wide, ident in placed_x:
        y = row_y(0)
        baseline = y + (line.ascent - line.descent) / 2
        anchor_boxes[ident] = (
            x - wide / 2,
            baseline - line.ascent,
            x + wide / 2,
            baseline + line.descent,
        )
        anchor_lines[ident] = _line(texts[ident], x, baseline, "middle", theme, bold=True)

    # Lines: anchor to need and component to need, straight; a dot that sits on a
    # line it is not an end of slides along its place to let it by.
    pairs: list[tuple[str, str]] = [
        (anchor.id, need) for anchor in document.wardley_anchors for need in anchor.needs
    ]
    pairs += [(component.id, need) for component in components.values() for need in component.needs]

    def ends(owner: str, need: str) -> tuple[tuple[float, float], tuple[float, float]]:
        target = dots[need]
        if owner in anchor_boxes:
            box = anchor_boxes[owner]
            start = ((box[0] + box[2]) / 2, box[3] + DAYLIGHT)
        else:
            start = (dots[owner].x, dots[owner].y)
        end = (target.x, target.y)
        if owner not in anchor_boxes:
            start = _toward(start, end, radius)
        return start, _toward(end, start, radius)

    for _ in range(len(dots) * len(SLIDES) + 1):
        blocked = _blocked(pairs, ends, dots, radius)
        if blocked is None:
            break
        dot, (owner, need) = blocked
        for share in SLIDES:
            moved = dot.x + share * slot
            if dot.lo <= moved <= dot.hi:
                trial_x = dot.x
                dot.x = moved
                if not _on_line(dot, *ends(owner, need), radius):
                    break
                dot.x = trial_x
        else:
            raise FitError(
                f"the line from {_named(owner, texts, components)!r} to "
                f"{_named(need, texts, components)!r} runs through {dot.text!r}, and it cannot "
                f"be slid clear. Move one of them `early` or `late`, or sink one with `depth`."
            )
    else:
        raise FitError("the map's lines could not be cleared of its dots; simplify the chain.")

    segments: list[_Segment] = [ends(owner, need) for owner, need in pairs]

    primitives: list[Primitive] = []
    obstacles: list[Box] = list(anchor_boxes.values())

    # The ground: stage dividers, then the two axes with their words.
    for k in range(1, len(WARDLEY_STAGES)):
        x = plot_left + k * quarter
        primitives.append(Path(DIVIDER_ROLE, points=((x, plot_top), (x, plot_bottom))))
    primitives.extend(
        edge_primitives(
            Route("", "", AXIS_ROLE, ((plot_left, plot_bottom), (plot_left, plot_top))), theme
        )
    )
    primitives.extend(
        edge_primitives(
            Route("", "", AXIS_ROLE, ((plot_left, plot_bottom), (plot_right, plot_bottom))),
            theme,
        )
    )
    gutter = pad + line.ascent
    primitives.append(_line(words.visible, gutter, plot_top + pad, "end", theme, rotate=-90.0))
    primitives.append(
        _line(words.chain, gutter, (plot_top + plot_bottom) / 2, "middle", theme, rotate=-90.0)
    )
    primitives.append(
        _line(words.invisible, gutter, plot_bottom - pad, "start", theme, rotate=-90.0)
    )
    names_y = plot_bottom + pad + line.ascent
    for k, stage in enumerate(WARDLEY_STAGES):
        name = words.stage(stage)
        if _width(name, theme, measurer) > quarter - pad:
            raise FitError(
                f"the stage name {name!r} is wider than its quarter of a map {width:.0f} wide. "
                f"Shorten it in the theme's [wardley] section, or widen the map."
            )
        primitives.append(_line(name, plot_left + (k + 0.5) * quarter, names_y, "middle", theme))
    evolution_y = names_y + line.height + pad / 2
    primitives.append(_line(words.evolution, plot_right, evolution_y, "end", theme))
    bottom = evolution_y + line.descent

    # The map: lines, evolution arrows, inertia bars, dots, anchors.
    for start, end in segments:
        primitives.append(Path(LINK_ROLE, points=(start, end)))
    for component in components.values():
        dot = dots[component.id]
        reach = dot.x + radius + gap / 2
        if component.inertia:
            bar_x = dot.x + radius + BAR_GAP * unit
            half = BAR_SPAN * radius / 2
            bar = (bar_x, dot.y - half, bar_x + BAR * unit, dot.y + half)
            obstacles.append(bar)
            primitives.append(
                Polygon(
                    DOT_ROLE,
                    points=((bar[0], bar[1]), (bar[2], bar[1]), (bar[2], bar[3]), (bar[0], bar[3])),
                    fill="solid",
                    fill_colour="currentColor",
                    region=True,
                )
            )
            reach = bar[2] + gap / 2
        if component.evolves:
            ghost = dots[_ghost(component.id)]
            tip = (ghost.x - radius - 2 * unit, ghost.y)
            if tip[0] - reach < 2 * theme.edge.min_shaft_length / 3:
                raise FitError(
                    f"{component.text!r} evolves to {component.evolves!r}, too near to draw an "
                    f"arrow to it on a map {width:.0f} wide. Name a place further right."
                )
            for key, other in dots.items():
                if key in (component.id, _ghost(component.id)):
                    continue
                if _distance((other.x, other.y), (reach, dot.y), tip) < radius + DAYLIGHT:
                    raise FitError(
                        f"{component.text!r} evolving to {component.evolves!r} would draw its "
                        f"arrow through {other.text!r} on the same row. Sink one of them with "
                        f"`depth`, or name a nearer place."
                    )
            segments.append(((reach, dot.y), tip))
            primitives.extend(
                edge_primitives(Route("", "", EVOLVE_ROLE, ((reach, dot.y), tip)), theme)
            )
            primitives.append(Ellipse(GHOST_ROLE, cx=ghost.x, cy=ghost.y, rx=radius, ry=radius))
    for dot in dots.values():
        obstacles.append(
            _grown((dot.x - radius, dot.y - radius, dot.x + radius, dot.y + radius), 1.0)
        )
        if not dot.ghost:
            primitives.append(Ellipse(DOT_ROLE, cx=dot.x, cy=dot.y, rx=radius, ry=radius))
    primitives.extend(anchor_lines.values())

    # Names: each beside its dot, in the nearest spot clear of the rest.
    bounds = (plot_left + pad / 2, plot_top, plot_right, plot_bottom - pad / 2)
    labels: dict[str, Box] = {}
    options: dict[str, list[_Spot]] = {}
    for component in components.values():
        dot = dots[component.id]
        wide = _width(component.text, theme, measurer)
        options[component.id] = _place(
            dot.x, dot.y, wide, radius + gap, line, bounds, obstacles, segments
        )
        if not options[component.id]:
            raise FitError(
                f"the name {component.text!r} has nowhere to sit beside its dot that is clear of "
                f"the dots and lines round it. Shorten it, move a neighbour `early` or `late`, "
                f"or widen the map."
            )
    assigned = _assign(options)
    if assigned is None:
        raise FitError(
            "the components' names cannot all be set beside their dots without two meeting. "
            "Shorten the longest, move a crowded neighbour `early` or `late`, or widen the map."
        )
    for component in components.values():
        box, x, baseline, side = assigned[component.id]
        labels[component.id] = box
        obstacles.append(box)
        primitives.append(_line(component.text, x, baseline, side, theme))

    # Notes: a numbered ring beside each thing a note is about, the words below.
    marker = line.height * 0.62
    for number, note in enumerate(document.wardley_notes, start=1):
        for target in note.on:
            if target in anchor_boxes:
                box = anchor_boxes[target]
                cx, cy, reach_out = (
                    (box[0] + box[2]) / 2,
                    (box[1] + box[3]) / 2,
                    (box[2] - box[0]) / 2,
                )
            else:
                cx, cy, reach_out = dots[target].x, dots[target].y, radius
            spot = _place_marker(cx, cy, reach_out, marker, bounds, obstacles, segments, pad)
            if spot is None:
                raise FitError(
                    f"note {number} has nowhere to be marked beside "
                    f"{_named(target, texts, components)!r}. Give the map more room."
                )
            mx, my = spot
            ring = (mx - marker, my - marker, mx + marker, my + marker)
            obstacles.append(ring)
            primitives.append(Ellipse(DOT_ROLE, cx=mx, cy=my, rx=marker, ry=marker))
            primitives.append(
                _line(str(number), mx, my + (line.ascent - line.descent) / 2, "middle", theme)
            )
    top = bottom + pad
    for number, note in enumerate(document.wardley_notes, start=1):
        indent = 2 * marker + pad
        block = wrap(note.text, plot_right - plot_left - indent, measurer, theme=theme, level=level)
        mx, my = plot_left + marker, top + marker
        primitives.append(Ellipse(DOT_ROLE, cx=mx, cy=my, rx=marker, ry=marker))
        primitives.append(
            _line(str(number), mx, my + (line.ascent - line.descent) / 2, "middle", theme)
        )
        for index, text_line in enumerate(block.lines):
            spans = tuple(
                TextSpan(text=span.text, font=span.font, weight=span.weight)
                for span in text_line.spans
                if span.text
            )
            primitives.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=plot_left + indent,
                    y=top + marker - block.advance / 2 + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor="start",
                )
            )
        top += max(2 * marker, block.height) + pad / 2
        bottom = top

    scene = Scene(
        width=width,
        height=bottom + line.descent,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )
    return WardleyDrawing(
        scene=scene,
        rows=dict(rows),
        centres={key: (dot.x, dot.y) for key, dot in dots.items() if not dot.ghost},
        labels=labels,
        plot=(plot_left, plot_top, plot_right, plot_bottom),
    )


def _ghost(ident: str) -> str:
    return f"{ident}\0ghost"


def _named(ident: str, texts: dict[str, str], components: dict[str, WardleyComponent]) -> str:
    return texts[ident] if ident in texts else components[ident].text


def _width(text: str, theme: Theme, measurer: TextMeasurer, *, bold: bool = False) -> float:
    size = theme.scale["label"]
    return sum(
        measurer.measure(span.text, span.font, size, "bold" if bold else span.weight).width
        for span in parse_spans(text, font=theme.font.default)
    )


def _line(
    text: str,
    x: float,
    y: float,
    anchor: str,
    theme: Theme,
    *,
    bold: bool = False,
    rotate: float = 0.0,
) -> TextLine:
    spans = tuple(
        TextSpan(text=span.text, font=span.font, weight="bold" if bold else span.weight)
        for span in parse_spans(text, font=theme.font.default)
        if span.text
    )
    return TextLine(
        FURNITURE_ROLE, x=x, y=y, spans=spans, level="label", anchor=anchor, rotate=rotate
    )


def _toward(
    point: tuple[float, float], other: tuple[float, float], by: float
) -> tuple[float, float]:
    """`point` moved `by` towards `other`: a line's end at a dot's rim."""
    span = math.dist(point, other) or 1.0
    return (
        point[0] + (other[0] - point[0]) / span * by,
        point[1] + (other[1] - point[1]) / span * by,
    )


def _distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    """How far `point` is from the segment `start` to `end`."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = dx * dx + dy * dy
    t = 0.0 if not length else ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length
    t = max(0.0, min(1.0, t))
    return math.dist(point, (start[0] + t * dx, start[1] + t * dy))


def _on_line(
    dot: _Dot, start: tuple[float, float], end: tuple[float, float], radius: float
) -> bool:
    return _distance((dot.x, dot.y), start, end) < radius + DAYLIGHT


def _blocked(
    pairs: Sequence[tuple[str, str]],
    ends: Callable[[str, str], _Segment],
    dots: dict[str, _Dot],
    radius: float,
) -> tuple[_Dot, tuple[str, str]] | None:
    """The first dot a line passes through that is not one of its ends."""
    for owner, need in pairs:
        start, end = ends(owner, need)
        for key, dot in dots.items():
            if key in (owner, need):
                continue
            if _on_line(dot, start, end, radius):
                return dot, (owner, need)
    return None


def _grown(box: Box, by: float) -> Box:
    return (box[0] - by, box[1] - by, box[2] + by, box[3] + by)


def _overlaps(first: Box, second: Box) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


def _crosses(box: Box, start: tuple[float, float], end: tuple[float, float]) -> bool:
    """Whether the segment `start` to `end` enters `box` (Liang-Barsky)."""
    x0, y0 = start
    dx, dy = end[0] - x0, end[1] - y0
    low, high = 0.0, 1.0
    for p, q in (
        (-dx, x0 - box[0]),
        (dx, box[2] - x0),
        (-dy, y0 - box[1]),
        (dy, box[3] - y0),
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


def _clear(
    box: Box,
    bounds: Box,
    obstacles: Sequence[Box],
    segments: Sequence[_Segment],
) -> bool:
    if box[0] < bounds[0] or box[1] < bounds[1] or box[2] > bounds[2] or box[3] > bounds[3]:
        return False
    grown = _grown(box, DAYLIGHT)
    if any(_overlaps(grown, other) for other in obstacles):
        return False
    return not any(_crosses(grown, start, end) for start, end in segments)


def _place(
    x: float,
    y: float,
    wide: float,
    off: float,
    line: Extents,
    bounds: Box,
    obstacles: Sequence[Box],
    segments: Sequence[_Segment],
) -> list[_Spot]:
    """Every spot for a name beside its dot that is clear of the dots and lines.

    Nearest first: the eight round the dot, then each stepped away by half a line.
    """
    ascent = line.ascent
    descent = line.descent
    beside = y + (ascent - descent) / 2
    above = y - off * 0.7 - descent
    below = y + off * 0.7 + ascent
    lean = off * 0.5
    height = ascent + descent
    candidates: list[tuple[float, float, str]] = [
        (x + off, beside, "start"),
        (x - off, beside, "end"),
        (x, above, "middle"),
        (x, below, "middle"),
        (x + lean, above, "start"),
        (x + lean, below, "start"),
        (x - lean, above, "end"),
        (x - lean, below, "end"),
    ]
    # Nudged: the same eight, stepped away from the dot by half a line at a time,
    # nearest first, before a name is given up on.
    for step in (0.5, 1.0, 1.5):
        nudge = step * height
        candidates += [
            (x + off, beside - nudge, "start"),
            (x + off, beside + nudge, "start"),
            (x - off, beside - nudge, "end"),
            (x - off, beside + nudge, "end"),
            (x, above - nudge, "middle"),
            (x, below + nudge, "middle"),
            (x + lean, above - nudge, "start"),
            (x + lean, below + nudge, "start"),
            (x - lean, above - nudge, "end"),
            (x - lean, below + nudge, "end"),
        ]
    found: list[_Spot] = []
    for ax, baseline, anchor in candidates:
        left = {"start": ax, "middle": ax - wide / 2, "end": ax - wide}[anchor]
        box = (left, baseline - ascent, left + wide, baseline + descent)
        if _clear(box, bounds, obstacles, segments):
            found.append((box, ax, baseline, anchor))
    return found


def _assign(options: dict[str, list[_Spot]]) -> dict[str, _Spot] | None:
    """One spot per name, no two names meeting: a search, most-constrained first.

    Every spot in `options` is already clear of the dots, lines and bars; what is
    left is the names against each other. Greedy placement in reading order gave
    a name's best spot away to a neighbour that had others; this backtracks
    instead, within a budget, and keeps each name's nearest spot where it can.
    """
    keys = sorted(options, key=lambda key: (len(options[key]), key))
    chosen: dict[str, _Spot] = {}
    budget = [SEARCH_BUDGET]

    def fits(spot: _Spot) -> bool:
        grown = _grown(spot[0], DAYLIGHT)
        return not any(_overlaps(grown, other[0]) for other in chosen.values())

    def search(index: int) -> bool:
        if index == len(keys):
            return True
        key = keys[index]
        for spot in options[key]:
            budget[0] -= 1
            if budget[0] < 0:
                return False
            if fits(spot):
                chosen[key] = spot
                if search(index + 1):
                    return True
                del chosen[key]
        return False

    return chosen if search(0) else None


def _place_marker(
    cx: float,
    cy: float,
    reach: float,
    marker: float,
    bounds: Box,
    obstacles: Sequence[Box],
    segments: Sequence[_Segment],
    pad: float,
) -> tuple[float, float] | None:
    """Where a note's numbered ring goes beside the thing it is about."""
    for further in (0.0, 0.6, 1.2):
        off = reach + marker * (1 + further) + pad / 2
        for angle in (-45, -135, 45, 135, -90, 90, 0, 180, -60, -120, 60, 120, -30, -150, 30, 150):
            mx = cx + off * math.cos(math.radians(angle))
            my = cy + off * math.sin(math.radians(angle))
            ring = (mx - marker, my - marker, mx + marker, my + marker)
            if _clear(ring, bounds, obstacles, segments):
                return mx, my
    return None


__all__ = ["WardleyDrawing", "wardley_drawing", "wardley_scene"]
