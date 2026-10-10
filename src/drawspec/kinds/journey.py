"""The `journey` kind: one person's feeling across the stages of an experience.

A journey map's content is a **named feeling per stage**, set against what the
person does there. The feeling is ordinal and named, never a score, so the band
it is drawn in has no ticks: each level is a light guide, named once on the left,
worst at the bottom, and a stage's point sits on its level's guide. A layout
family of its own, and a small one: every position comes from counting.

**Columns** are equal, one per stage, after a margin as wide as the widest level
or row name (up to a share of the canvas). Each has its heading, in bold, over a
rule as wide as the column, drawn in the stage's role.

**The feeling line** passes through every point, in the theme's `[journey] line`.
It is a monotone cubic through the points, not the `curve` kind's Catmull-Rom:
x only increases, and a monotone curve never overshoots a point, so two
neighbouring stages at one level are joined by a flat segment and the line never
strays past the best or worst level it is named against.

**Rows** run under the band, each above a `[journey] separator`, with the row's
name in the margin and one cell per stage, top-aligned; a row is as tall as its
tallest cell. A stage with no detail for a row leaves its cell empty.

**The `emphasis` stage** — the one the map is about, usually the trough — has its
column framed in the `emphasis` role from heading to last row, and its point drawn
larger and solid: size and fill, not colour. Every heading's rule is one weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Final

from drawspec.errors import FitError
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Rect, Scene, TextLine, TextSpan
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most of the canvas the margin of level and row names may take.
LABEL_SHARE: Final = 0.2

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
GUTTER: Final = 12.0
"""Between two columns, and between the margin and the first column."""
CELL_PAD: Final = 4.0
"""Inside a column on each side: a cell's words keep this far from its edges."""
TOP: Final = 8.0
"""From the frame's top to the headings."""
RULE_GAP: Final = 6.0
"""From a heading to the rule under it."""
LEVEL_GAP: Final = 26.0
"""The least distance between two levels' guides."""
BAND_PAD: Final = 14.0
"""Above the best level's guide and below the worst's."""
ROW_PAD: Final = 8.0
"""Above and below a row's words."""
FRAME_PAD: Final = 5.0
"""How far the emphasis frame stands out from its column, into the gutters."""

#: The radius of a stage's point, as a share of the theme's arrow head, and how
#: much larger the `emphasis` stage's point is drawn.
MARKER_FRACTION: Final = 0.45
EMPHASIS_MARKER: Final = 1.5

#: How many straight pieces each span of the line between two points is drawn in.
LINE_STEPS: Final = 24

#: The role the names and the words are drawn in: furniture, not boxes.
TEXT_ROLE: Final = "step"

#: The role every heading's rule is drawn in. One weight for all: the emphasis
#: stage is already framed, and a heavier rule inside the frame says it twice.
HEADING_RULE_ROLE: Final = "step"

#: The role the emphasis stage's frame is drawn in.
FRAME_ROLE: Final = "emphasis"


@dataclass(frozen=True)
class JourneyDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    columns: tuple[tuple[float, float], ...] = ()
    """Each stage's column, left and right edge, left to right."""

    levels: dict[str, float] = field(default_factory=dict)
    """Each feeling's guide, by name: the y it is drawn at."""

    points: tuple[tuple[float, float], ...] = ()
    """Each stage's point, left to right."""

    line: tuple[tuple[float, float], ...] = ()
    """The feeling line, as drawn: a polyline through every point."""

    rows: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Each detail row's top and bottom, by id."""

    cells: tuple[tuple[str, int, tuple[float, float, float, float]], ...] = ()
    """Each drawn cell: its row id, its stage's index, and its words' bounds."""

    frames: tuple[tuple[float, float, float, float], ...] = ()
    """Each `emphasis` stage's frame: left, top, right, bottom."""


def journey_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a journey map."""
    return journey_drawing(document, theme, measurer).scene


def journey_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> JourneyDrawing:
    """Lay the journey out on the canvas.

    Raises:
        FitError: a column is too narrow for a word of a heading or a cell, or
            the margin's names leave no room for the columns.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    stages = document.journey_stages
    feelings = document.feelings
    rows = document.journey_rows
    gutter = GUTTER * unit
    pad = CELL_PAD * unit

    # The margin: as wide as the widest name, level or row, up to its share.
    names = [*feelings, *(_bold(row.text) for row in rows)]
    label_width = min(max(_natural(name, theme, measurer) for name in names), width * LABEL_SHARE)
    level_blocks = {
        feeling: _wrapped(feeling, label_width, theme, measurer, "feeling") for feeling in feelings
    }
    row_blocks = {
        row.id: _wrapped(_bold(row.text), label_width, theme, measurer, "row name") for row in rows
    }

    count = len(stages)
    first = label_width + gutter
    column_width = (width - first - gutter * (count - 1)) / count
    if column_width <= 2 * pad:
        raise FitError(
            f"{count} stages do not fit a width of {width:.0f}: each column would be "
            f"{column_width:.0f} wide. Split the journey in two, or give the diagram more width."
        )
    lefts = [first + index * (column_width + gutter) for index in range(count)]
    columns = tuple((left, left + column_width) for left in lefts)
    centres = [(left + right) / 2 for left, right in columns]
    inner = column_width - 2 * pad

    primitives: list[Primitive] = []
    texts: list[Primitive] = []

    # Headings, each centred over its column, with a rule under it in its role.
    top = TOP * unit
    headings = [_wrapped(_bold(stage.text), inner, theme, measurer, "stage") for stage in stages]
    heading_height = max(block.height for block in headings)
    for block, centre in zip(headings, centres, strict=True):
        texts.extend(_lines(block, centre, top + heading_height - block.height, "middle"))
    rule = top + heading_height + RULE_GAP * unit
    for left, right in columns:
        primitives.append(Path(HEADING_RULE_ROLE, points=((left, rule), (right, rule))))

    # The band: one guide per level, worst at the bottom, named once on the left.
    gap = max(
        LEVEL_GAP * unit, max(block.height for block in level_blocks.values()) + RULE_GAP * unit
    )
    band_top = rule + BAND_PAD * unit
    levels = {
        feeling: band_top + (len(feelings) - 1 - index) * gap
        for index, feeling in enumerate(feelings)
    }
    guide_start = label_width + gutter / 2
    for feeling, y in levels.items():
        primitives.append(Path(theme.journey.guide, points=((guide_start, y), (width, y))))
        block = level_blocks[feeling]
        texts.extend(_lines(block, label_width, y - block.height / 2, "end"))
    band_bottom = levels[feelings[0]] + BAND_PAD * unit

    # The line, through every point, and each point on it.
    points = tuple(
        (centre, levels[stage.feeling]) for stage, centre in zip(stages, centres, strict=True)
    )
    line = monotone(points)
    primitives.append(Path(theme.journey.line, points=line))
    radius = theme.edge.head_length * MARKER_FRACTION
    markers: list[Primitive] = []
    for stage, (x, y) in zip(stages, points, strict=True):
        if stage.role == "emphasis":
            size = radius * EMPHASIS_MARKER
            markers.append(
                Ellipse(
                    "emphasis",
                    cx=x,
                    cy=y,
                    rx=size,
                    ry=size,
                    fill="solid",
                    fill_colour="currentColor",
                )
            )
        else:
            markers.append(Ellipse("step", cx=x, cy=y, rx=radius, ry=radius))

    # The rows, each above a separator, one cell per stage, top-aligned.
    bottom = band_bottom
    placed_rows: dict[str, tuple[float, float]] = {}
    cells: list[tuple[str, int, tuple[float, float, float, float]]] = []
    for row in rows:
        primitives.append(Path(theme.journey.separator, points=((0.0, bottom), (width, bottom))))
        row_top = bottom + ROW_PAD * unit
        label = row_blocks[row.id]
        texts.extend(_lines(label, 0.0, row_top, "start"))
        tallest = label.height
        for index, (stage, centre) in enumerate(zip(stages, centres, strict=True)):
            detail = next((item for item in stage.details if item.row == row.id), None)
            if detail is None:
                continue
            block = _wrapped(detail.text, inner, theme, measurer, "detail")
            texts.extend(_lines(block, centre, row_top, "middle"))
            cells.append(
                (
                    row.id,
                    index,
                    (
                        centre - block.width / 2,
                        row_top,
                        centre + block.width / 2,
                        row_top + block.height,
                    ),
                )
            )
            tallest = max(tallest, block.height)
        row_bottom = row_top + tallest + ROW_PAD * unit
        placed_rows[row.id] = (bottom, row_bottom)
        bottom = row_bottom

    # The frame of each emphasis stage, from above its heading to the last row.
    frames: list[tuple[float, float, float, float]] = []
    reach = min(FRAME_PAD * unit, gutter / 2 - unit)
    for stage, (left, right) in zip(stages, columns, strict=True):
        if stage.role != "emphasis":
            continue
        box = (left - reach, 0.0, right + reach, bottom)
        frames.append(box)
        primitives.insert(0, _frame(box, theme))

    scene = Scene(
        width=width,
        height=bottom,
        primitives=(*primitives, *markers, *texts),
        title=document.title,
        description=document.description,
    )
    return JourneyDrawing(
        scene=scene,
        columns=columns,
        levels=levels,
        points=points,
        line=line,
        rows=placed_rows,
        cells=tuple(cells),
        frames=tuple(frames),
    )


def _frame(box: tuple[float, float, float, float], theme: Theme) -> Primitive:
    """The emphasis frame: the role's own box when the theme draws it as a rect.

    A rounded rect, like every box, in the default theme; a theme that draws
    `emphasis` as another shape gets a plain rectangle in that role's line, since
    a column is a rectangle whatever its boxes look like.
    """
    left, top, right, bottom = box
    if theme.roles[FRAME_ROLE].shape == "rect":
        return Rect(FRAME_ROLE, x=left, y=top, width=right - left, height=bottom - top)
    return Polygon(FRAME_ROLE, points=((left, top), (right, top), (right, bottom), (left, bottom)))


def monotone(points: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    """A monotone cubic through every point, sampled into a polyline.

    Fritsch-Carlson in Butland's form: the slope at a point is zero where the
    line turns (or runs level on either side), and otherwise the harmonic mean of
    its two neighbouring secants. So the curve passes through each point, is flat
    between two equal neighbours, and between any two points stays between their
    two heights — it never overshoots into a level nobody named.
    """
    if len(points) < 3:
        return points
    secants = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in pairwise(points)]
    slopes = [secants[0]]
    for before, after in pairwise(secants):
        slopes.append(0.0 if before * after <= 0 else 2 * before * after / (before + after))
    slopes.append(secants[-1])
    sampled: list[tuple[float, float]] = [points[0]]
    for index, ((x0, y0), (x1, y1)) in enumerate(pairwise(points)):
        span = x1 - x0
        m0, m1 = slopes[index] * span, slopes[index + 1] * span
        for step in range(1, LINE_STEPS + 1):
            t = step / LINE_STEPS
            t2, t3 = t * t, t * t * t
            y = (
                (2 * t3 - 3 * t2 + 1) * y0
                + (t3 - 2 * t2 + t) * m0
                + (-2 * t3 + 3 * t2) * y1
                + (t3 - t2) * m1
            )
            sampled.append((x0 + span * t, y))
    return tuple(sampled)


def _bold(text: str) -> str:
    """A name set bold. Its own spans are dropped: the whole name is bold."""
    return "\n".join(
        f"**{line.replace('**', '')}**" if line.strip() else line for line in text.split("\n")
    )


def _natural(text: str, theme: Theme, measurer: TextMeasurer) -> float:
    """How wide `text` is set on its own lines, unbroken."""
    return wrap(text, 1e6, measurer, theme=theme, level="body").width


def _wrapped(text: str, width: float, theme: Theme, measurer: TextMeasurer, what: str) -> TextBlock:
    try:
        return wrap(text, width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the {what} {text.replace('**', '')[:40]!r} has a word wider than the "
            f"{width:.0f} units it can have. Shorten it, split the journey in two, or give "
            f"the diagram more width."
        ) from error


def _lines(block: TextBlock, x: float, top: float, anchor: str) -> list[TextLine]:
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(TEXT_ROLE, x=x, y=top + block.baseline(index), spans=spans, anchor=anchor)
            )
    return found


__all__ = ["JourneyDrawing", "journey_drawing", "journey_scene", "monotone"]
