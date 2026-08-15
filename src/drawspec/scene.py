"""The `Scene`: where every rendering family converges.

This is the load-bearing seam. Graph kinds, grid kinds, shape kinds and charts
all produce the same thing — a flat list of primitives in final coordinates,
each tagged with a semantic role, carrying **no styling at all**. Styling is
applied once, by `drawspec.emit`, from the theme.

That is why "SVG safe to paste inline into Markdown" is satisfied in one file
rather than four, and why adding a fifth rendering family later costs nothing in
embedding-safety work: a new family produces primitives, and the invariants are
already enforced downstream of it.

A primitive therefore has no colour, no stroke width, no font size and no dash
pattern. It has geometry and a role. If you find yourself wanting to add an
appearance field here, the decision belongs in the theme.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Final

from drawspec.text.wrap import TextBlock

#: Where a text run is anchored horizontally, in SVG's own vocabulary.
TEXT_ANCHORS: Final = ("start", "middle", "end")

#: Type weights a text run may take. Bold means something or is not used, so
#: there are two, not a range.
TEXT_WEIGHTS: Final = ("normal", "bold")


@dataclass(frozen=True)
class Primitive:
    """Base for everything a scene contains.

    `role` names a semantic role the theme declares — a node role for a shape, an
    edge role for a connector. The emitter refuses a role the theme does not
    declare, because an unstylable primitive is a programming error rather than
    something to guess at.
    """

    role: str


@dataclass(frozen=True)
class Rect(Primitive):
    """An axis-aligned box in final coordinates.

    Corner treatment is not a field: the theme picks one radius and applies it to
    every box, and a `pill` role is drawn as a fully rounded rect by the emitter.
    """

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    fill: str = ""
    fill_colour: str = ""
    """The colour that pattern is drawn in, when the theme declares one. Resolved
    from the theme by whoever chose the fill — never a value an author wrote."""

    """One of the theme's fill patterns, when the *geometry* decides its own fill.

    Empty means "ask the role", which is every box in every graph. A chart mark
    is the exception: three series of bars are three of the same role, and what
    tells them apart is a sequence the theme declares rather than a role each.
    Saying it here keeps that out of the role vocabulary, where it would mean
    inventing `series-one`, `series-two`, `series-three`.
    """


@dataclass(frozen=True)
class Ellipse(Primitive):
    """An ellipse in final coordinates — a ring, a circle, a rounded node."""

    cx: float = 0.0
    cy: float = 0.0
    rx: float = 0.0
    ry: float = 0.0


@dataclass(frozen=True)
class Polygon(Primitive):
    """A closed figure: a diamond, a pyramid level, an arrow head, an area."""

    points: tuple[tuple[float, float], ...] = ()
    fill: str = ""
    """As `Rect.fill`: a fill the geometry chose, or empty for the role's."""

    fill_colour: str = ""
    """As `Rect.fill_colour`: the colour that fill is drawn in."""

    region: bool = False
    """Whether this figure is an extent rather than a shape, so it is not outlined.

    Not styling — like `Path.marker`, it says what the geometry *is*. A chart
    area is the ground under a curve: the curve along its top is the data, and
    the two verticals dropping to the baseline are where the drawing stops, not
    something that happened. Stroked, those verticals are indistinguishable from
    a mark: an area over a bar chart put a full-weight line straight down through
    the bar at each end of its range. The line along the top is drawn separately,
    by whatever produced the region, so no data is lost by not outlining it.
    """


@dataclass(frozen=True)
class Path(Primitive):
    """An open or closed run of straight segments — an edge route, an axis.

    Points rather than a `d` string: the primitive holds geometry, and turning
    geometry into SVG is the emitter's job. Orthogonal routing means these are
    axis-aligned in practice, but the primitive does not enforce that — the
    routing stage owns that invariant.
    """

    points: tuple[tuple[float, float], ...] = ()
    closed: bool = False
    started_at: float = 0.0
    """How far along the stroke this path *began*, when it is a piece of a longer one.

    Not styling — a length, in user units, and the only thing that lets a broken
    stroke keep one rhythm. `drawspec.clearance` cuts a dashed line into pieces to
    let a label through, and SVG restarts a dash pattern at the start of every
    `<path>`: three pieces of one dashed curve come out as three fresh dash
    cycles, so the dashes either side of a gap no longer line up with the ones
    before it and the line reads as several lines. The emitter turns this into the
    dash offset that continues the pattern instead. Zero — an unbroken stroke, or
    the first piece of one — emits nothing.
    """

    marker: bool = False
    """Whether this path is an end treatment rather than a length of line.

    Not styling: it says what the geometry *is*. An open arrow head is two short
    strokes meeting at the tip, and a dash pattern measured along them breaks
    each into pieces — so a `weak` edge came out with a head made of four
    disconnected marks instead of an arrow. The emitter reads this to decide that
    a head is drawn solid whatever the role's dash says; the decision stays in
    the theme's hands, the fact that this is a head stays in the geometry's.
    """


@dataclass(frozen=True)
class TextRun(Primitive):
    """One run of text on one line, positioned by its baseline.

    `level` selects a size from the theme's four-step scale and `font` selects a
    family stack; neither is a size or a family, because an element never names
    its own type. A run is the unit an inline span produces, which is how
    `` `code` `` becomes the monospace font and `**bold**` becomes the bold
    weight without either being a typographic instruction from the author.
    """

    x: float = 0.0
    y: float = 0.0
    text: str = ""
    level: str = "body"
    font: str = "sans"
    anchor: str = "start"
    weight: str = "normal"
    rotate: float = 0.0
    """Rotation in degrees about (x, y) — a chart's vertical axis label, and
    nothing else so far."""


@dataclass(frozen=True)
class TextSpan:
    """One run of text inside a line, in its own font and weight.

    The pieces `**bold**` and `` `code` `` produce. A span carries no position:
    where it lands is the renderer's arithmetic, not drawspec's — see `TextLine`.
    """

    text: str = ""
    font: str = "sans"
    weight: str = "normal"


@dataclass(frozen=True)
class TextLine(Primitive):
    """One whole line of text, anchored as a unit and laid out by the renderer.

    This is a `TextRun` per span with the *positions taken out*, and the reason is
    that drawspec cannot know which font the reader has. It measures against the
    family the theme names, but the SVG only *names* that family — a page without
    it substitutes, and every per-span x drawspec computed is then wrong by the
    difference between two fonts' metrics. Two failures came from that, and both
    are invisible on the machine that drew them:

    * **Centred text stops being centred.** A line placed by its measured left
      edge drifts by half the metric difference; on a phone, where none of the
      theme's families are installed, a whole diagram's labels sit off centre.
    * **Runs collide or gape.** The space at a span boundary is measured into the
      advance but never drawn — SVG strips whitespace at the edge of a text
      element — so `the diagram **means**` renders as `diagrammeans` here and
      with a visible hole there.

    A line, anchored once, is immune to both: the renderer places the spans
    consecutively with the metrics it actually has, keeps the boundary space
    because it is now interior to one element, and centres the whole line about
    `x`. drawspec still decides what the line *is* — which words, which break,
    which box — and that is the half it can be right about wherever it is read.
    """

    x: float = 0.0
    y: float = 0.0
    spans: tuple[TextSpan, ...] = ()
    level: str = "body"
    anchor: str = "middle"

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


def centred_lines(
    block: TextBlock, x: float, top: float, role: str, level: str
) -> tuple[TextLine, ...]:
    """A wrapped block as one `TextLine` per line, centred on `x` from `top` down.

    The step from "text, wrapped" to "primitives, placed", for the labels that do
    not live in a box — a span's name, a note under a tick. `kinds.common.
    text_runs` is the same step for the ones that do, and takes its geometry from
    the box instead of from two numbers.

    It exists as one function because it is where a text field's promises are
    kept: the inline spans survive into `TextSpan`s, and a second paragraph gets
    its own line rather than being flattened. A caller that built a bare `TextRun`
    from `span.text` instead drew `**RPO**` with the asterisks showing.
    """
    lines: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if not spans:
            continue
        lines.append(
            TextLine(
                role,
                x=x,
                y=top + index * block.advance + block.ascent,
                spans=spans,
                level=level,
                anchor="middle",
            )
        )
    return tuple(lines)


def moved(primitive: Primitive, dx: float, dy: float) -> Primitive:
    """`primitive` translated. The one place a scene knows how to shift itself.

    Every family ends up needing this — a graph frames itself against the margin,
    a ring is dropped under the top margin, and the canvas centres whatever it is
    given — and a second implementation of it is a second chance to move the
    boxes and forget the arrows.

    Raises:
        TypeError: a primitive type nothing here knows how to move, which means
            one was added without teaching this function about it.
    """
    if isinstance(primitive, Rect):
        return replace(primitive, x=primitive.x + dx, y=primitive.y + dy)
    if isinstance(primitive, Ellipse):
        return replace(primitive, cx=primitive.cx + dx, cy=primitive.cy + dy)
    if isinstance(primitive, Polygon | Path):
        return replace(primitive, points=tuple((x + dx, y + dy) for x, y in primitive.points))
    if isinstance(primitive, TextRun | TextLine):
        return replace(primitive, x=primitive.x + dx, y=primitive.y + dy)
    raise TypeError(f"nothing here knows how to move a {type(primitive).__name__}")


def extents(primitives: Sequence[Primitive]) -> tuple[float, float, float, float]:
    """The bounds of what is drawn: left, top, right, bottom.

    Of the *ink*, not of the boxes — which is the distinction that matters. A
    ring's lowest point is the bottom of the arc between its two lowest steps,
    not the bottom of either step, and a canvas measured from the boxes cuts that
    arc in half. Text is measured as a point, because its width belongs to
    whoever has the font; every family already sized a box around it.
    """
    xs: list[float] = []
    ys: list[float] = []
    for primitive in primitives:
        if isinstance(primitive, Rect):
            xs += [primitive.x, primitive.x + primitive.width]
            ys += [primitive.y, primitive.y + primitive.height]
        elif isinstance(primitive, Ellipse):
            xs += [primitive.cx - primitive.rx, primitive.cx + primitive.rx]
            ys += [primitive.cy - primitive.ry, primitive.cy + primitive.ry]
        elif isinstance(primitive, Polygon | Path):
            xs += [x for x, _ in primitive.points]
            ys += [y for _, y in primitive.points]
        elif isinstance(primitive, TextRun | TextLine):
            xs.append(primitive.x)
            ys.append(primitive.y)
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class Scene:
    """A complete drawing: primitives in final coordinates, plus its extents.

    `title` and `description` are the accessible name and description; the
    emitter puts them in `<title>` and `<desc>` and points the root element at
    them, so a diagram is readable by something that cannot see it.
    """

    width: float
    height: float
    primitives: tuple[Primitive, ...] = ()
    title: str = ""
    description: str = ""
    metadata: tuple[tuple[str, str], ...] = field(default=())
    """Sorted key/value pairs a family may attach for tests and diagnostics.
    Never emitted, so it cannot affect the output bytes."""

    def roles(self) -> tuple[str, ...]:
        """Every role this scene uses, sorted — the set the theme must declare."""
        return tuple(sorted({primitive.role for primitive in self.primitives}))


__all__ = [
    "TEXT_ANCHORS",
    "TEXT_WEIGHTS",
    "Ellipse",
    "Path",
    "Polygon",
    "Primitive",
    "Rect",
    "Scene",
    "TextLine",
    "TextRun",
    "TextSpan",
    "centred_lines",
    "extents",
    "moved",
]
