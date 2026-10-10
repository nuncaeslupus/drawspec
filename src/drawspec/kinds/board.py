"""The `board` kind: cards sorted into columns, with optional slices across them.

One kind for a kanban board, a retrospective and a story map. All three are
cards in columns with no connectors; a story map adds horizontal **slices**
(`rows`) and a **cut** under the first release. A layout family of its own and a
small one: nothing is ranked and nothing is routed. Every position comes from
counting.

**Columns** are equal, the canvas less the gutters (and, with rows, less the
slice labels' margin) divided by their number, so a card's width says nothing
about its importance. Each has a heading — the name in bold, then `n / limit`
when the column has a work-in-progress limit — over a rule as wide as the
column, drawn in the heading's role: heavier for `emphasis`, and a column over
its limit takes `emphasis` because drawspec counted.

**Cards** stack in each cell in the order written, top-aligned, so a column
with two cards looks shorter than one with six: on a kanban board that
emptiness is information. An `actor` is the card's lead, as in a `flow` box; a
`note` hangs under the card at the label size. A `note` card is a light dashed
outline.

**Slices** run across every column, their names in a margin at the left, as
wide as the widest name up to a share of the canvas. A row is as tall as its
tallest cell. Between two slices runs the theme's `[board] separator`; under the
cut row runs `[board] cut` instead, the board's one heavy line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import lead_rule, outline, text_runs
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import BoardColumn, Card, Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most of the canvas the slice labels' margin may take. A longer name wraps.
LABEL_SHARE: Final = 0.2

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
GUTTER: Final = 12.0
CARD_GAP: Final = 7.0
RULE_GAP: Final = 6.0
ROW_PAD: Final = 10.0
NOTE_GAP: Final = 4.0

#: The role a heading's text is drawn in: furniture, not a box.
HEADING_TEXT_ROLE: Final = "step"


@dataclass(frozen=True)
class BoardDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    columns: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Each column's left and right edge, by id."""

    cards: tuple[tuple[float, float, float, float], ...] = ()
    """Each card's outline — left, top, right, bottom — in document order."""

    headings: dict[str, tuple[str, str]] = field(default_factory=dict)
    """Each column's heading text as drawn (with its count) and the role it took."""

    rows: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Each slice's top and bottom, by id. One entry, `""`, when there are no rows."""

    separators: tuple[float, ...] = ()
    """The y of each line between two slices, top to bottom, the cut's excluded."""

    cut: float | None = None
    """The y of the cut, when there is one."""


def board_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a board."""
    return board_drawing(document, theme, measurer).scene


def heading_of(column: BoardColumn, cards: tuple[Card, ...]) -> tuple[str, str]:
    """A column's heading — its name, and `n / limit` when it has one — and its role.

    The count is drawspec's, never the author's: every card in the column but a
    `note`, which is a placeholder or a summary rather than a piece of work. Over
    the limit the heading takes `emphasis` whatever role it was given.
    """
    name = column.text.replace("**", "")
    if column.limit is None:
        return f"**{name}**", column.role
    count = sum(1 for card in cards if card.column == column.id and card.role != "note")
    over = count > column.limit
    tally = f"{count} / {column.limit}"
    return (
        f"**{name}**  {f'**{tally}**' if over else tally}",
        "emphasis" if over else column.role,
    )


def board_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> BoardDrawing:
    """Lay the board out on the canvas.

    Raises:
        FitError: the columns are too narrow for a card's or a heading's longest
            word, or the slice names leave no room for the columns.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    columns = document.board_columns
    slices = document.slices
    gutter = GUTTER * unit
    padding = theme.box.padding

    # The slice labels' margin: as wide as the widest name, up to its share.
    margin = 0.0
    labels: dict[str, TextBlock] = {}
    if slices:
        margin = min(
            max(_natural(_bold(item.text), theme, measurer) for item in slices),
            width * LABEL_SHARE,
        )
        labels = {
            item.id: _wrapped(_bold(item.text), margin, theme, measurer, "slice") for item in slices
        }
        margin += gutter

    count = len(columns)
    column_width = (width - margin - gutter * (count - 1)) / count
    if column_width <= padding.horizontal:
        raise FitError(
            f"{count} columns do not fit a width of {width:.0f}: each would be "
            f"{column_width:.0f} wide. Use fewer columns, or give the diagram more width."
        )
    lefts = {
        column.id: margin + index * (column_width + gutter) for index, column in enumerate(columns)
    }

    primitives: list[Primitive] = []
    texts: list[Primitive] = []

    # Headings, each centred over its column, with a rule under it in its role.
    headings = {column.id: heading_of(column, document.cards) for column in columns}
    heading_blocks = {
        column.id: _wrapped(
            headings[column.id][0], column_width - padding.horizontal, theme, measurer, "heading"
        )
        for column in columns
    }
    heading_height = max(block.height for block in heading_blocks.values())
    for column in columns:
        block = heading_blocks[column.id]
        left = lefts[column.id]
        texts.extend(_centred(block, left + column_width / 2, heading_height - block.height))
    rule = heading_height + RULE_GAP * unit
    for column in columns:
        left = lefts[column.id]
        primitives.append(
            Path(headings[column.id][1], points=((left, rule), (left + column_width, rule)))
        )

    # Cards, sized once, each the column's width.
    sized = [_card(card, column_width, theme, measurer) for card in document.cards]

    # Rows, top to bottom; without rows, one implicit row.
    row_ids = [item.id for item in slices] or [""]
    row_pad = ROW_PAD * unit
    gap = CARD_GAP * unit
    top = rule + row_pad
    rows: dict[str, tuple[float, float]] = {}
    placed: list[tuple[float, float, float, float]] = [(0.0, 0.0, 0.0, 0.0)] * len(sized)
    for row in row_ids:
        bottom = top + (labels[row].height + padding.top if row in labels else 0.0)
        for column in columns:
            y = top
            for index, card in enumerate(document.cards):
                if card.column != column.id or card.row != row:
                    continue
                box, note, height = sized[index]
                left = lefts[column.id]
                placed[index] = (left, y, left + column_width, y + box.height)
                primitives.extend(_card_outline(card, box, left, y, theme))
                texts.extend(_card_text(box, note, left, y, theme, measurer))
                y += height + gap
            bottom = max(bottom, y - gap if y > top else top)
        if row in labels:
            texts.extend(_left(labels[row], 0.0, top + padding.top))
        rows[row] = (top, bottom)
        top = bottom + 2 * row_pad

    # The lines between slices, and the cut, across the whole board.
    separators: list[float] = []
    cut: float | None = None
    for row, following in pairwise(row_ids):
        y = (rows[row][1] + rows[following][0]) / 2
        if row == document.cut:
            cut = y
            primitives.append(Path(theme.board.cut, points=((0.0, y), (width, y))))
        else:
            separators.append(y)
            primitives.append(Path(theme.board.separator, points=((0.0, y), (width, y))))

    height = rows[row_ids[-1]][1]
    scene = Scene(
        width=width,
        height=height,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return BoardDrawing(
        scene=scene,
        columns={
            column.id: (lefts[column.id], lefts[column.id] + column_width) for column in columns
        },
        cards=tuple(placed),
        headings=headings,
        rows=rows,
        separators=tuple(separators),
        cut=cut,
    )


def _card(
    card: Card, width: float, theme: Theme, measurer: TextMeasurer
) -> tuple[Box, TextBlock | None, float]:
    """A card's box at the column's width, its note's block, and the height of both."""
    role = "step" if card.role == "note" else card.role
    try:
        box = size_box(
            card.label,
            theme=theme,
            measurer=measurer,
            role=role,
            level="body",
            max_width=width,
            shape="rect",
            lead=True if card.actor else None,
        ).resized(width=width)
    except FitError as error:
        raise FitError(
            f"the card {card.text[:40]!r} has a word wider than the {width:.0f} units its "
            f"column can give it. Shorten it, use fewer columns, or give the diagram more width."
        ) from error
    if not card.note:
        return box, None, box.height
    try:
        note = wrap(card.note, box.width, measurer, theme=theme, level="label")
    except FitError as error:
        raise FitError(
            f"the note {card.note[:40]!r} has a word wider than its column. Shorten it, use "
            f"fewer columns, or give the diagram more width."
        ) from error
    return box, note, box.height + NOTE_GAP * theme.scale["body"] / 11 + note.height


def _card_outline(card: Card, box: Box, left: float, top: float, theme: Theme) -> list[Primitive]:
    """A card's border: the role's box, or a light dashed outline for a `note` card.

    A note card is a polygon in the `note` role because the theme draws that role
    with no shape of its own — words on the page — and a placeholder card still
    has to read as a card, only a lighter one.
    """
    if card.role == "note":
        right, bottom = left + box.width, top + box.height
        return [
            Polygon("note", points=((left, top), (right, top), (right, bottom), (left, bottom)))
        ]
    placed = box.moved_to(left, top)
    return [*outline(placed, theme), *lead_rule(placed)]


def _card_text(
    box: Box,
    note: TextBlock | None,
    left: float,
    top: float,
    theme: Theme,
    measurer: TextMeasurer,
) -> list[Primitive]:
    """A card's words, and its note under the card, centred.

    The note is outside the border, at the label size, the way a timeline's note
    hangs under its entry: every word inside a shape is set at one size in every
    kind, and a note is an annotation on the card rather than part of it.
    """
    placed = box.moved_to(left, top)
    found: list[Primitive] = list(text_runs(placed, theme, measurer))
    if note is not None:
        note_top = top + box.height + NOTE_GAP * theme.scale["body"] / 11
        found.extend(_centred(note, left + box.width / 2, note_top, level="label"))
    return found


def _bold(text: str) -> str:
    """A name set bold. Its own spans are dropped: the whole name is bold."""
    return f"**{text.replace('**', '')}**"


def _natural(text: str, theme: Theme, measurer: TextMeasurer) -> float:
    """How wide `text` is set on its own lines, unbroken."""
    return wrap(text, 1e6, measurer, theme=theme, level="body").width


def _wrapped(text: str, width: float, theme: Theme, measurer: TextMeasurer, what: str) -> TextBlock:
    try:
        return wrap(text, width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the {what} {text.replace('**', '')[:40]!r} has a word wider than the "
            f"{width:.0f} units it can have. Shorten it, use fewer columns, or give the "
            f"diagram more width."
        ) from error


def _lines(block: TextBlock, x: float, top: float, anchor: str, level: str) -> list[TextLine]:
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
                    HEADING_TEXT_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor=anchor,
                )
            )
    return found


def _centred(block: TextBlock, x: float, top: float, level: str = "body") -> list[TextLine]:
    return _lines(block, x, top, "middle", level)


def _left(block: TextBlock, x: float, top: float) -> list[TextLine]:
    return _lines(block, x, top, "start", "body")


__all__ = ["BoardDrawing", "board_drawing", "board_scene", "heading_of"]
