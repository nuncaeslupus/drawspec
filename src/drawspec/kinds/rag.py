"""The `rag` kind: a RAG status report, one row per workstream or risk.

A layout family of its own, and a small one: rows set one under another, ruled
apart, with every column lined up so the eye runs down each.

**The name** sits in a column at the left, in bold, its caption (the text after a
newline: an owner, a reference) under it at the label size.

**The mark** says the rating three ways at once: a shape the theme gives each
rating (all three different), the theme's word for it beside the shape, and a
colour only when the theme declares one. Shape and word are what a greyscale
print and a reader who cannot tell red from green keep.

**The trend**, when any row has one, is an arrow (up for `better`, across for
`same`, down for `worse`) with the theme's word beside it, because an arrow alone
means opposite things in different reports.

**The note** takes the rest of the width, wrapped. Every cell starts at its row's
top, so a mark sits on its name's first line whatever the note's length.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import AXIS_ROLE, FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.kinds.treemap import bold
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import RAG_VALUES, Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most of the width the name column may take.
NAME_SHARE: Final = 0.3

#: The least room a note column may be left, in body line heights.
NOTE_MIN_LINES: Final = 7.0

#: The edge role a trend's arrow is drawn in: an ordinary line with a filled head.
ARROW_ROLE: Final = "flow"

#: The direction each trend's arrow points, as (dx, dy) on a page whose y runs down.
TREND_DIRECTIONS: Final = {"better": (0.0, -1.0), "same": (1.0, 0.0), "worse": (0.0, 1.0)}

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class RagDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    rows: tuple[Box, ...] = ()
    """Each row's extent, from the left edge to the right, top to bottom."""

    marks: tuple[tuple[str, float, float], ...] = ()
    """Each row's mark: the shape drawn, and its centre."""

    words: tuple[str, ...] = ()
    """Each row's rating as written beside its mark."""

    trends: tuple[str, ...] = ()
    """Each row's trend as written beside its arrow, or empty."""

    columns: tuple[float, ...] = ()
    """Where each column starts: name, mark, then trend and note when drawn."""

    texts: tuple[Box, ...] = field(default=())
    """Every piece of text placed, for the tests that nothing overlaps."""


def rag_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a RAG status report."""
    return rag_drawing(document, theme, measurer).scene


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def _lines(block: TextBlock, x: float, top: float, level: str) -> list[TextLine]:
    """A wrapped block set from `x`, `top` down, each line a TextLine."""
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
                    level=level,
                    anchor="start",
                )
            )
    return lines


def rag_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> RagDrawing:
    """Lay the rows out, one under another, in lined-up columns.

    Raises:
        FitError: a word is wider than its column, or the names, marks and trends
            leave the notes too little room, at this type scale.
    """
    width = document.width if document.width else theme.canvas.width
    rows = document.rag_rows
    style = theme.rag
    gap = theme.box.padding.top
    column_gap = 2 * gap
    body = theme.scale["body"]
    font = theme.font.default
    line = measurer.measure("0", font, body)
    size = line.ascent * 0.95  # A mark is about the height of a capital and a little more.

    def block(text: str, room: float, level: str, what: str) -> TextBlock:
        try:
            return wrap(text, max(room, 1.0), measurer, theme=theme, level=level, lead=False)
        except FitError as error:
            raise FitError(
                f"{what} {_plain(text)!r} has a word wider than the {room:.0f} units its "
                f"column gets. Shorten it, or give the diagram more width."
            ) from error

    def natural(text: str, level: str) -> float:
        return block(text, 1e6, level, "the text").width

    # -- the columns ---------------------------------------------------------
    used = [rating for rating in RAG_VALUES if any(row.rag == rating for row in rows)]
    word_width = max(natural(bold(style.word(rating)), "body") for rating in used)
    mark_width = size + gap * 0.75 + word_width

    has_trend = any(row.trend for row in rows)
    has_note = any(row.note for row in rows)
    label = theme.scale["label"]
    trend_width = 0.0
    if has_trend:
        trend_width = (
            size
            + gap * 0.75
            + max(
                natural(style.word(trend), "label")
                for trend in {row.trend for row in rows if row.trend}
            )
        )

    # With notes, the name takes at most a third of the width and the notes the
    # rest; without, the name may take whatever the mark and trend leave.
    names = [row.text.split("\n", 1) for row in rows]
    others = column_gap + mark_width + (column_gap + trend_width if has_trend else 0.0)
    name_room = width * NAME_SHARE if has_note else width - others
    widest_name = max(
        max(natural(bold(parts[0]), "body"), natural(parts[1], "label") if len(parts) > 1 else 0)
        for parts in names
    )
    name_width = min(widest_name, name_room)

    columns = [0.0, name_width + column_gap]
    x = columns[-1] + mark_width
    if has_trend:
        columns.append(x + column_gap)
        x = columns[-1] + trend_width
    note_width = 0.0
    if has_note:
        columns.append(x + column_gap)
        note_width = width - columns[-1]
        if note_width < NOTE_MIN_LINES * line.height:
            raise FitError(
                f"the notes get {max(note_width, 0):.0f} units once the names, marks and trends "
                f"are measured. Shorten the longest name, or give the diagram more width."
            )
        x = width
    # A report with no notes is narrower than the canvas: centre it, as every
    # other kind is centred, rather than leave it hanging at the left.
    shift = (width - x) / 2
    columns = [column + shift for column in columns]
    left, right = columns[0], x + shift

    # -- the rows ------------------------------------------------------------
    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    boxes: list[Box] = []
    row_boxes: list[Box] = []
    marks: list[tuple[str, float, float]] = []
    trends: list[str] = []
    y = 0.0
    for index, (row, parts) in enumerate(zip(rows, names, strict=True)):
        top = y
        name = block(bold(parts[0]), name_width, "body", "the name")
        texts.extend(_lines(name, left, top, "body"))
        boxes.append((left, top, left + name.width, top + name.height))
        bottom = top + name.height
        if len(parts) > 1:
            caption = block(parts[1], name_width, "label", "the caption")
            texts.extend(_lines(caption, left, bottom, "label"))
            boxes.append((left, bottom, left + caption.width, bottom + caption.height))
            bottom += caption.height

        # The mark, centred on the first line's capitals, then its word.
        baseline = top + name.baseline(0)
        middle = baseline - line.ascent * 0.36
        shape = style.shape(row.rag)
        cx = columns[1] + size / 2
        primitives.append(_mark(shape, cx, middle, size, style.colour(row.rag)))
        marks.append((shape, cx, middle))
        word = block(bold(style.word(row.rag)), word_width + 1.0, "body", "the rating")
        word_x = columns[1] + size + gap * 0.75
        texts.extend(_lines(word, word_x, top, "body"))
        boxes.append((word_x, top, word_x + word.width, top + word.height))
        bottom = max(bottom, top + word.height)

        position = 2
        if has_trend:
            if row.trend:
                ax = columns[position] + size / 2
                primitives.extend(_arrow(row.trend, ax, middle, size, theme))
                text = style.word(row.trend)
                tx = columns[position] + size + gap * 0.75
                said = measurer.measure(text, font, label)
                texts.append(
                    TextLine(
                        FURNITURE_ROLE,
                        x=tx,
                        y=baseline,
                        spans=(TextSpan(text=text, font=font),),
                        level="label",
                        anchor="start",
                    )
                )
                boxes.append((tx, baseline - said.ascent, tx + said.width, baseline + said.descent))
                trends.append(text)
            else:
                trends.append("")
            position += 1
        else:
            trends.append("")
        if has_note and row.note:
            note = block(row.note, note_width, "body", "the note")
            texts.extend(_lines(note, columns[position], top, "body"))
            boxes.append(
                (columns[position], top, columns[position] + note.width, top + note.height)
            )
            bottom = max(bottom, top + note.height)

        row_boxes.append((left, top, right, bottom))
        y = bottom
        if index < len(rows) - 1:
            rule = y + gap
            primitives.append(Path(AXIS_ROLE, points=((left, rule), (right, rule))))
            y = rule + gap

    scene = Scene(
        width=width,
        height=y,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return RagDrawing(
        scene=scene,
        rows=tuple(row_boxes),
        marks=tuple(marks),
        words=tuple(style.word(row.rag) for row in rows),
        trends=tuple(trends),
        columns=tuple(columns),
        texts=tuple(boxes),
    )


def _mark(shape: str, cx: float, cy: float, size: float, colour: str) -> Primitive:
    """One rating's mark, filled: a circle, a triangle, a square or a diamond."""
    paint = colour or "currentColor"
    half = size / 2
    points: tuple[tuple[float, float], ...]
    if shape == "circle":
        return Ellipse(
            FURNITURE_ROLE, cx=cx, cy=cy, rx=half, ry=half, fill="solid", fill_colour=paint
        )
    if shape == "triangle":
        # A little wider than tall, its centre of area on the line's middle.
        tall = size * 1.02
        points = (
            (cx, cy - tall * 2 / 3 + tall * 0.08),
            (cx + size * 0.6, cy + tall / 3 + tall * 0.08),
            (cx - size * 0.6, cy + tall / 3 + tall * 0.08),
        )
    elif shape == "diamond":
        reach = size * 0.62
        points = ((cx, cy - reach), (cx + reach, cy), (cx, cy + reach), (cx - reach, cy))
    else:
        side = size * 0.44
        points = (
            (cx - side, cy - side),
            (cx + side, cy - side),
            (cx + side, cy + side),
            (cx - side, cy + side),
        )
    return Polygon(FURNITURE_ROLE, points=points, fill="solid", fill_colour=paint)


def _arrow(trend: str, cx: float, cy: float, size: float, theme: Theme) -> list[Primitive]:
    """A short arrow through (cx, cy), pointing the way `trend` says, with a filled head."""
    dx, dy = TREND_DIRECTIONS[trend]
    half = size * 0.62
    head = max(theme.head_length_for(ARROW_ROLE), size * 0.5)
    tail = (cx - dx * half, cy - dy * half)
    tip = (cx + dx * half, cy + dy * half)
    neck = (tip[0] - dx * head, tip[1] - dy * head)
    across = head * 0.6
    return [
        Path(ARROW_ROLE, points=(tail, neck)),
        Polygon(
            ARROW_ROLE,
            points=(
                tip,
                (neck[0] + dy * across, neck[1] - dx * across),
                (neck[0] - dy * across, neck[1] + dx * across),
            ),
        ),
    ]


__all__ = ["RagDrawing", "rag_drawing", "rag_scene"]
