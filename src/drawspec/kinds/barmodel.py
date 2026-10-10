"""The `barmodel` kind: a word problem as bars of parts — the tape diagram.

A layout family of its own, and an arithmetic one: every length is a part's
share of the longest bar, so the only decisions made here are where the names,
the braces and their words go.

**Bars** start at one left edge, top to bottom in the order written, after a
column for their names. One scale serves the whole drawing — an `amount` is its
share of the longest bar's total, a unit the longest bar's share per unit — so
two bars compare by length, which is the whole point of the model: pupils read
unequal parts as equal unless they are drawn so.

**Parts** are boxes side by side, each with its words centred inside. A `units`
part is that many equal boxes, its words in each. `emphasis` (the part asked
about) is outlined heavier and filled with the theme's first mark fill, its
words bold; `note` (a part that is not there — the stretch a shorter bar lacks)
is a dashed outline.

**Braces** over parts of a bar go above it — under it for the last of several
bars, so a comparison's two bars are braced on their outer sides — with their
words beyond the brace's point. Braces on one side that would touch are stacked
outwards, the narrowest nearest the bar. A brace over several bars stands
upright at their right, its words beside it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import Document, ModelBar, ModelBrace, ModelPart
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
PAD: Final = 6.0
"""The space round a part's words inside its box, on every side."""

NAME_GAP: Final = 10.0
"""The space between a bar's name and the bar."""

BAR_GAP: Final = 12.0
"""The space between two bars with nothing braced between them."""

DEPTH: Final = 8.0
"""How far a brace's point stands from its ends."""

BRACE_GAP: Final = 3.0
"""The space between a bar and its brace, and between a brace and its words."""

DAYLIGHT: Final = 8.0
"""The least space between two braces' words side by side."""

#: The most of the canvas width a bar's name, or a brace's words, may take.
LABEL_SHARE: Final = 0.22

#: The least of the canvas the bars may be left with before the model is refused.
BARS_SHARE: Final = 0.45

#: How many straight pieces draw each quarter of a brace's curl.
ARC_STEPS: Final = 6

#: The role a brace is drawn in: a plain line, no head.
BRACE_ROLE: Final = "flow"

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class BarmodelDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    bars: tuple[Box, ...] = ()
    """Each bar's extent — left, top, right, bottom — top to bottom."""

    parts: dict[tuple[int, int], tuple[Box, ...]] = field(default_factory=dict)
    """Each part's boxes (one, or one per unit), by (bar, part)."""

    braces: tuple[tuple[str, Box], ...] = ()
    """Each brace's side (`above`, `below`, `right`) and extent, in document order."""

    labels: tuple[Box, ...] = ()
    """Each brace's words, in document order."""

    scale: float = 0.0
    """Units of canvas per unit of value (or per unit box)."""


@dataclass
class _Brace:
    index: int
    side: str
    row: int
    low: float
    high: float
    block: TextBlock
    level: int = 0
    extent: tuple[float, float] = (0.0, 0.0)


def barmodel_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a bar model."""
    return barmodel_drawing(document, theme, measurer).scene


def barmodel_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> BarmodelDrawing:
    """Lay the bar model out on the canvas.

    Raises:
        FitError: the names and braces leave too little width for the bars, or a
            part is too narrow for its words at the scale the longest bar sets.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    bars = document.model_bars
    pad = PAD * unit
    gap = BRACE_GAP * unit
    depth = DEPTH * unit
    cap = width * LABEL_SHARE

    # The names' column.
    names = {
        index: _wrapped(bar.text, cap, theme, measurer)
        for index, bar in enumerate(bars)
        if bar.text
    }
    left = max((block.width for block in names.values()), default=-NAME_GAP * unit)
    left += NAME_GAP * unit

    # What each brace spans: the parts of one bar, or whole bars.
    where = _where(bars)
    sides: list[tuple[str, int, list[int]]] = []
    for written in document.model_braces:
        found = [where[name] for name in written.over]
        if all(kind == "bar" for kind, _, _ in found) and len(found) > 1:
            sides.append(("right", min(row for _, row, _ in found), sorted(r for _, r, _ in found)))
            continue
        if all(kind == "bar" for kind, _, _ in found):
            row = found[0][1]
            columns = list(range(len(bars[row].parts)))
        else:
            row = found[0][1]
            columns = sorted(column for _, _, column in found)
        side = "below" if len(bars) > 1 and row == len(bars) - 1 else "above"
        sides.append((side, row, columns))
    blocks = [
        _wrapped(_brace_text(written), cap, theme, measurer, bold=False)
        for written in document.model_braces
    ]

    # The upright braces' column at the right: one level per overlap, outwards.
    upright = [index for index, (side, _, _) in enumerate(sides) if side == "right"]
    levels: dict[int, int] = {}
    for index in sorted(upright, key=lambda k: (len(sides[k][2]), k)):
        spanned = set(sides[index][2])
        touching = [levels[other] for other in levels if spanned & set(sides[other][2])]
        levels[index] = max(touching, default=-1) + 1
    level_widths: dict[int, float] = {}
    for index, level in levels.items():
        level_widths[level] = max(level_widths.get(level, 0.0), blocks[index].width)
    offsets: dict[int, float] = {}
    reach = 0.0
    for level in sorted(level_widths):
        offsets[level] = reach + gap
        reach = offsets[level] + depth + gap + level_widths[level]
    right = width - reach

    if right - left < width * BARS_SHARE:
        raise FitError(
            f"the names and the upright braces' words leave {max(right - left, 0):.0f} of the "
            f"canvas's {width:.0f} units for the bars. Shorten them, or give the diagram more "
            f"width."
        )

    # One scale: the longest bar fills the width.
    totals = [sum(_size(part) for part in bar.parts) for bar in bars]
    scale = (right - left) / max(totals)

    # Each part's boxes and words, before anything is placed vertically.
    texts_of: dict[tuple[int, int], TextBlock] = {}
    spans: dict[tuple[int, int], list[tuple[float, float]]] = {}
    tallest = 0.0
    for row, bar in enumerate(bars):
        x = left
        for column, part in enumerate(bar.parts):
            count = part.units or 1
            each = _size(part) * scale / count
            spans[(row, column)] = [(x + k * each, x + (k + 1) * each) for k in range(count)]
            x += each * count
            words = _part_text(part)
            if not words:
                continue
            block = _wrapped(words, 1e6, theme, measurer, bold=part.role == "emphasis")
            if block.width + 2 * pad > each + 1e-6:
                raise FitError(
                    f"part {column} of bar {row} ({words[:30]!r}) is {each:.0f} units wide at "
                    f"the scale the longest bar sets, too narrow for its words. Shorten them, "
                    f"or draw the parts closer in size — a bar model's lengths are in "
                    f"proportion, so a tiny part beside a large one has no room."
                )
            texts_of[(row, column)] = block
            tallest = max(tallest, block.height)
    line = measurer.measure("0", theme.font.default, theme.scale["body"])
    height = max(tallest, line.height) + 2 * pad

    # Braces over parts: levels outwards on each side of each bar.
    flat: list[_Brace] = []
    for index, (side, row, columns) in enumerate(sides):
        if side == "right":
            continue
        low = spans[(row, columns[0])][0][0]
        high = spans[(row, columns[-1])][-1][1]
        block = blocks[index]
        middle = (low + high) / 2
        start = min(max(middle - block.width / 2, 0.0), width - block.width)
        extent = (min(low, start), max(high, start + block.width))
        flat.append(_Brace(index, side, row, low, high, block, extent=extent))
    placed: list[_Brace] = []
    for brace in sorted(flat, key=lambda item: (item.high - item.low, item.index)):
        touching = [
            other.level
            for other in placed
            if other.side == brace.side
            and other.row == brace.row
            and other.extent[0] < brace.extent[1] + DAYLIGHT * unit
            and brace.extent[0] < other.extent[1] + DAYLIGHT * unit
        ]
        brace.level = max(touching, default=-1) + 1
        placed.append(brace)
    pitch = {(brace.side, brace.row, brace.level): 0.0 for brace in flat}
    for brace in flat:
        key = (brace.side, brace.row, brace.level)
        pitch[key] = max(pitch[key], gap + depth + gap + brace.block.height)

    def band(side: str, row: int) -> list[float]:
        found: list[float] = []
        level = 0
        while (side, row, level) in pitch:
            found.append(pitch[(side, row, level)])
            level += 1
        return found

    # Vertical placement: each bar after the braces above it.
    tops: list[float] = []
    y = 0.0
    for row in range(len(bars)):
        if row:
            y += BAR_GAP * unit
        y += sum(band("above", row))
        tops.append(y)
        y += height
    y += sum(band("below", len(bars) - 1))
    bottom = y

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    parts: dict[tuple[int, int], tuple[Box, ...]] = {}
    rank = {"note": 0, "step": 1, "emphasis": 2}
    order = sorted(
        ((row, column) for row, bar in enumerate(bars) for column in range(len(bar.parts))),
        key=lambda key: rank.get(bars[key[0]].parts[key[1]].role, 1),
    )
    for row, column in order:
        part = bars[row].parts[column]
        top = tops[row]
        boxes: list[Box] = []
        for low, high in spans[(row, column)]:
            boxes.append((low, top, high, top + height))
            primitives.append(_box(part, low, top, high, top + height, theme))
            written_block = texts_of.get((row, column))
            if written_block is not None:
                texts.extend(
                    _centred(
                        written_block, (low + high) / 2, top + (height - written_block.height) / 2
                    )
                )
        parts[(row, column)] = tuple(boxes)
    bar_boxes = tuple(
        (left, top, spans[(row, len(bar.parts) - 1)][-1][1], top + height)
        for row, (bar, top) in enumerate(zip(bars, tops, strict=True))
    )
    for row, block in names.items():
        texts.extend(_lines(block, 0.0, tops[row] + (height - block.height) / 2))

    # The braces and their words.
    extents: list[tuple[str, Box]] = [("", (0.0, 0.0, 0.0, 0.0))] * len(sides)
    labels: list[Box] = [(0.0, 0.0, 0.0, 0.0)] * len(sides)
    for brace in flat:
        before = sum(band(brace.side, brace.row)[: brace.level])
        block = brace.block
        start = min(max((brace.low + brace.high) / 2 - block.width / 2, 0.0), width - block.width)
        if brace.side == "above":
            base = tops[brace.row] - before - gap
            tip = base - depth
            label_top = tip - gap - block.height
            extents[brace.index] = ("above", (brace.low, tip, brace.high, base))
        else:
            base = tops[brace.row] + height + before + gap
            tip = base + depth
            label_top = tip + gap
            extents[brace.index] = ("below", (brace.low, base, brace.high, tip))
        primitives.append(
            Path(BRACE_ROLE, points=_curl(brace.low, brace.high, base, tip, upright=False))
        )
        texts.extend(_centred(block, start + block.width / 2, label_top))
        labels[brace.index] = (start, label_top, start + block.width, label_top + block.height)
    for index, level in levels.items():
        rows = sides[index][2]
        low, high = tops[rows[0]], tops[rows[-1]] + height
        base = right + offsets[level]
        tip = base + depth
        primitives.append(Path(BRACE_ROLE, points=_curl(low, high, base, tip, upright=True)))
        block = blocks[index]
        label_left = tip + gap
        label_top = (low + high) / 2 - block.height / 2
        texts.extend(_lines(block, label_left, label_top))
        extents[index] = ("right", (base, low, tip, high))
        labels[index] = (label_left, label_top, label_left + block.width, label_top + block.height)

    scene = Scene(
        width=width,
        height=bottom,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return BarmodelDrawing(
        scene=scene,
        bars=bar_boxes,
        parts=parts,
        braces=tuple(extents),
        labels=tuple(labels),
        scale=scale,
    )


def _where(bars: tuple[ModelBar, ...]) -> dict[str, tuple[str, int, int]]:
    """Every id: a bar's, or a part's with its bar and place."""
    found: dict[str, tuple[str, int, int]] = {}
    for row, bar in enumerate(bars):
        if bar.id:
            found[bar.id] = ("bar", row, -1)
        for column, part in enumerate(bar.parts):
            if part.id:
                found[part.id] = ("part", row, column)
    return found


def _size(part: ModelPart) -> float:
    """A part's length in the document's one measure: its amount, or its units."""
    return float(part.amount if part.amount is not None else part.units or 0)


def _part_text(part: ModelPart) -> str:
    if part.text:
        return part.text
    return _number(part.amount) if part.amount is not None else ""


def _brace_text(brace: ModelBrace) -> str:
    if brace.text:
        return brace.text
    return _number(brace.amount) if brace.amount is not None else ""


def _number(value: float) -> str:
    return f"{value:g}"


def _box(
    part: ModelPart, left: float, top: float, right: float, bottom: float, theme: Theme
) -> Primitive:
    """One box of a part: a polygon, so its ends are exactly at its values."""
    points = ((left, top), (right, top), (right, bottom), (left, bottom))
    if part.role == "emphasis":
        return Polygon(
            "emphasis",
            points=points,
            fill=theme.mark.fill_for(0),
            fill_colour=theme.mark.colour_for(0),
        )
    return Polygon(part.role, points=points)


def _curl(
    low: float, high: float, base: float, tip: float, *, upright: bool
) -> tuple[tuple[float, float], ...]:
    """A curly brace from `low` to `high` along its length, standing from `base` to `tip`.

    Four quarter turns: up from each end, along, and up again to the point in the
    middle. Drawn across (over or under a bar) or upright (beside bars).
    """
    away = tip - base
    radius = min(abs(away) / 2, (high - low) / 4)
    sign = 1.0 if away > 0 else -1.0
    middle = (low + high) / 2
    found: list[tuple[float, float]] = []

    def arc(centre_u: float, centre_v: float, start: float, end: float) -> None:
        for step in range(ARC_STEPS + 1):
            angle = start + (end - start) * step / ARC_STEPS
            found.append((centre_u + radius * math.cos(angle), centre_v + radius * math.sin(angle)))

    arc(low + radius, 0.0, math.pi, math.pi / 2)
    arc(middle - radius, 2 * radius, -math.pi / 2, 0.0)
    arc(middle + radius, 2 * radius, math.pi, 3 * math.pi / 2)
    arc(high - radius, 0.0, math.pi / 2, 0.0)
    points = [(u, base + sign * v) for u, v in found]
    if upright:
        points = [(v, u) for u, v in points]
    return tuple(points)


def _wrapped(
    text: str, width: float, theme: Theme, measurer: TextMeasurer, *, bold: bool = False
) -> TextBlock:
    words = f"**{text.replace('**', '')}**" if bold else text
    try:
        return wrap(words, width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the label {text[:40]!r} has a word wider than the {width:.0f} units it can take. "
            f"Shorten it, or give the diagram more width."
        ) from error


def _spans(block: TextBlock, index: int) -> tuple[TextSpan, ...]:
    return tuple(
        TextSpan(text=span.text, font=span.font, weight=span.weight)
        for span in block.lines[index].spans
        if span.text
    )


def _centred(block: TextBlock, x: float, top: float) -> list[TextLine]:
    """A wrapped block centred on `x`, from `top` down, its spans kept."""
    return [
        TextLine(
            FURNITURE_ROLE,
            x=x,
            y=top + block.baseline(index),
            spans=spans,
            level="body",
            anchor="middle",
        )
        for index in range(len(block.lines))
        if (spans := _spans(block, index))
    ]


def _lines(block: TextBlock, x: float, top: float) -> list[TextLine]:
    """A wrapped block set from `x`, from `top` down, its spans kept."""
    return [
        TextLine(
            FURNITURE_ROLE,
            x=x,
            y=top + block.baseline(index),
            spans=spans,
            level="body",
            anchor="start",
        )
        for index in range(len(block.lines))
        if (spans := _spans(block, index))
    ]


__all__ = ["BarmodelDrawing", "barmodel_drawing", "barmodel_scene"]
