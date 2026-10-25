"""The `packet` kind: a protocol header or a register as bit fields in rows.

A layout family of its own, and an arithmetic one. The input is the fields in
reading order, each with its width in `bits`; nothing carries a position. Every
decision here follows from those widths and the row's width in bits.

**Rows of a fixed width.** A row holds `bits_per_row` bits, each bit an equal
share of the canvas, so a 16-bit field is always twice an 8-bit one and a column
of bit 8 lines up in every row. Fields are laid end to end, left to right and row
after row.

**A field that crosses a row's end is split there.** Its pieces are drawn in the
two rows, the edges where it was cut dashed rather than solid — the mark that
the field goes on — and its name, and what it holds, are written in the widest
piece; a narrower piece repeats the name only where it fits.

**The ruler says where every bit is.** Over the first row when bit 0 is at the
left of every word (`numbering: left`, the RFC convention: the ruler counts the
bit's place in its word); over every row when bit 0 is the last bit of the last
row (`right`, a datasheet register, counting down from the top left). Every bit
boundary is ticked, a byte's more deeply, and numbers are written as often as
they fit: every bit, or every second, fourth or eighth.

**A name too long for its field is fitted, never shrunk.** In order: across the
field, broken at a space onto two lines; the author's `short`, across; the name,
then the `short`, turned on its side when the field is narrow but the word short
(RFC 793's flags); and last a letter, the name going to the key under the
drawing. drawspec never abbreviates a name itself.
The key also carries every `note`, and a `holds` too wide for its field — so a
reader finds there everything the cells could not say, as an RFC lists its
fields under the header.

**Reserved bits are hatched**, in the theme's `[packet] reserved_fill`, and may
be left without a name. An `emphasis` field is outlined heavier, its name bold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextRun, TextSpan
from drawspec.schema import Document, PacketField
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, bold_lines, wrap
from drawspec.textgrid import (
    caption_lines,
    cells,
    centred,
    finished,
    label_lines,
    spelt,
    too_wide,
)
from drawspec.textgrid import wrapped as words_of
from drawspec.theme import Theme

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
PAD: Final = 3.0
"""The least space between a field's words and its side edges."""

VPAD: Final = 6.0
"""The space over and under a field's words, inside its row."""

TICK: Final = 2.5
"""How far a bit's tick reaches into a row, from its top and bottom edges."""

RULER_TICK: Final = 3.0
"""How far a bit's tick stands over the ruled row; a byte's stands twice as far."""

RULER_GAP: Final = 2.0
"""The space between a ruler's numbers and its ticks."""

ROW_GAP: Final = 6.0
"""The space between a row and the next row's ruler, when every row has one."""

KEY_GAP: Final = 14.0
"""The space between the last row and the key."""

#: The longest a name turned on its side may be, in body line heights: past it the
#: row would stand taller than the header is wide, and the name goes to the key.
SIDE_LINES: Final = 4.5

#: The most lines a name may be broken onto across its field.
ACROSS_LINES: Final = 2

#: The most of the width the key's left column (the names it explains) may take.
KEY_SHARE: Final = 0.3

#: How often the ruler may write a bit's number: every bit, else every second, …
RULER_STEPS: Final = (1, 2, 4, 8)

#: The role a field's edges are drawn in: a plain solid line.
EDGE_ROLE: Final = "flow"

#: The role an edge where a field was split is drawn in: dashed, the field goes on.
OPEN_ROLE: Final = "aside"

#: The role an `emphasis` field's own edges are drawn in, over the plain ones.
EMPHASIS_EDGE_ROLE: Final = "strong"

#: The role of the ruler's and the rows' bit ticks: the lightest line.
TICK_ROLE: Final = "link"

#: How a field's name was fitted: across it, on its side, by its `short` (either
#: way), by a letter, or not at all (a blank reserved field, a continuation).
PLACEMENTS: Final = ("across", "side", "short", "short-side", "marker", "blank")

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Piece:
    """One field's share of one row: its bits from `start` up to `end`."""

    field: int
    row: int
    start: int
    end: int
    open_start: bool
    """Whether the field began in the row before, so this piece's left edge is a cut."""

    open_end: bool
    """Whether the field goes on in the next row, so this piece's right edge is a cut."""

    @property
    def bits(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class PacketDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    pieces: tuple[Piece, ...] = ()
    cells: tuple[Box, ...] = ()
    """Each piece's box, in the order of `pieces`."""

    placements: tuple[str, ...] = ()
    """How each field's name was fitted (one of `PLACEMENTS`), in field order."""

    key: tuple[tuple[str, str], ...] = ()
    """The key under the drawing: what each entry is keyed by, and what it says."""

    ruler: tuple[tuple[int, float, float], ...] = ()
    """Each number the rulers write: the bit, its centre's x, and its baseline."""

    texts: tuple[Box, ...] = field(default=())
    """Every piece of text placed, for the tests that nothing overlaps."""


def pieces_of(fields: tuple[PacketField, ...], row_bits: int) -> tuple[tuple[Piece, ...], int]:
    """Every field cut into its rows' pieces, in reading order, and the bits in all."""
    found: list[Piece] = []
    position = 0
    for index, written in enumerate(fields):
        left = written.bits
        first = True
        while left:
            row, start = divmod(position, row_bits)
            take = min(left, row_bits - start)
            found.append(
                Piece(index, row, start, start + take, open_start=not first, open_end=left > take)
            )
            position += take
            left -= take
            first = False
    return tuple(found), position


def holders(pieces: tuple[Piece, ...]) -> dict[int, int]:
    """Per field, the index of its widest piece: where its name is written."""
    best: dict[int, int] = {}
    for index, piece in enumerate(pieces):
        current = best.get(piece.field)
        if current is None or piece.bits > pieces[current].bits:
            best[piece.field] = index
    return best


def marker_for(count: int) -> str:
    """The key's mark for the `count`-th field keyed by one: `a`, `b`, … `z`, `aa`, ….

    Letters, not numbers: a cell in a bit diagram that reads `1` reads as a value.
    """
    letters = "abcdefghijklmnopqrstuvwxyz"
    return (
        letters[count] if count < len(letters) else letters[count // 26 - 1] + letters[count % 26]
    )


def bit_number(row: int, column: int, row_bits: int, total: int, numbering: str) -> int:
    """The number the ruler writes over `column` of `row`."""
    if numbering == "right":
        return total - 1 - (row * row_bits + column)
    return column


def packet_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a packet diagram."""
    return packet_drawing(document, theme, measurer).scene


@dataclass
class _Label:
    placement: str = "blank"
    block: TextBlock | None = None
    side: str = ""
    """The words turned on their side, when the placement is `side`."""

    holds: bool = False
    """Whether what the field holds is written in the cell."""


def packet_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> PacketDrawing:
    """Lay the fields out in rows, ruled, with the key under them.

    Raises:
        FitError: a field is too narrow even for its letter at this type scale.
    """
    width = document.width if document.width else theme.canvas.width
    fields = document.packet_fields
    row_bits = document.packet_row_bits
    numbering = document.packet_numbering
    unit = theme.scale["body"] / 11
    pad, vpad = PAD * unit, VPAD * unit
    body, label_size = theme.scale["body"], theme.scale["label"]
    font = theme.font.default
    line = measurer.measure("0", font, body)
    small = measurer.measure("0", "mono", label_size)
    bit = width / row_bits
    pieces, total = pieces_of(fields, row_bits)
    rows = -(-total // row_bits)
    holding = holders(pieces)

    def words(written: PacketField, text: str) -> str:
        return bold_lines(text) if written.role == "emphasis" else text

    def across(text: str, room: float) -> TextBlock | None:
        if room <= 0:
            return None
        try:
            block = wrap(text, room, measurer, theme=theme, level="body", lead=False)
        except FitError:
            return None
        return block if len(block.lines) <= ACROSS_LINES else None

    def one_line(text: str, weight: str) -> float:
        return measurer.measure(_plain(text), font, body, weight).width

    # -- how each field's name is fitted --------------------------------------
    labels: list[_Label] = []
    markers: dict[int, str] = {}
    key: list[tuple[str, str]] = []
    side_room = SIDE_LINES * line.height
    for index, written in enumerate(fields):
        piece = pieces[holding[index]]
        room = piece.bits * bit - 2 * pad
        weight = "bold" if written.role == "emphasis" else "normal"
        narrow_enough = piece.bits * bit >= line.height + unit
        label = _Label()
        if written.text:
            block = across(words(written, written.text), room)
            short = across(words(written, written.short), room) if written.short else None
            if block is not None:
                label = _Label("across", block)
            elif short is not None and len(short.lines) == 1:
                label = _Label("short", short)
            elif (
                narrow_enough
                and " " not in written.text
                and (one_line(written.text, weight) <= side_room)
            ):
                label = _Label("side", side=written.text)
            elif written.short and narrow_enough and one_line(written.short, weight) <= side_room:
                label = _Label("short-side", side=written.short)
            else:
                label = _Label("marker")
        elif written.note:
            label = _Label("marker")
        if written.holds and label.placement in ("across", "short"):
            label.holds = measurer.measure(written.holds, "mono", label_size).width <= room
        if label.placement == "marker":
            number = marker_for(len(markers))
            markers[index] = number
            needed = measurer.measure(number, font, body, weight).width
            if needed > piece.bits * bit - 2 * unit:
                raise FitError(
                    f"field {index} ({written.text or 'reserved'!r}) is {piece.bits} bit"
                    f"{'s' if piece.bits > 1 else ''} wide, {piece.bits * bit:.0f} units at "
                    f"{row_bits} bits a row: too narrow even for a letter keying it to the "
                    f"key. Draw fewer bits a row, or give the diagram more width."
                )
            label.block = across(words(written, number), max(needed + 1.0, 1.0))
        labels.append(label)
        entry = _key_entry(written, label, markers.get(index, ""))
        if entry is not None:
            key.append(entry)

    # -- how tall a row is -----------------------------------------------------
    holds_height = small.height + unit
    content = line.height
    for label in labels:
        if label.block is not None:
            content = max(content, label.block.height + (holds_height if label.holds else 0.0))
    base = content + 2 * vpad
    heights = [base] * rows
    for index, label in enumerate(labels):
        if label.side:
            row = pieces[holding[index]].row
            weight = "bold" if fields[index].role == "emphasis" else "normal"
            heights[row] = max(heights[row], one_line(label.side, weight) + 2 * vpad)

    # -- the ruler's step ----------------------------------------------------
    numbers_label = measurer.measure("0", font, label_size)
    widest = max(
        measurer.measure(str(number), font, label_size).width
        for number in (row_bits - 1, total - 1 if numbering == "right" else row_bits - 1)
    )
    step = next((each for each in RULER_STEPS if widest + 2 * unit <= each * bit), RULER_STEPS[-1])
    ruler_height = numbers_label.height + RULER_GAP * unit + 2 * RULER_TICK * unit

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    boxes: list[Box] = []
    ruler_numbers: list[tuple[int, float, float]] = []

    def ruler(row: int, top: float, columns: int) -> None:
        """The numbers and ticks over `row`, whose top edge is at `top`."""
        baseline = top - 2 * RULER_TICK * unit - RULER_GAP * unit - numbers_label.descent
        shown: list[tuple[float, float]] = []
        order = [0, columns - 1] + [c for c in range(1, columns - 1)]
        for column in order:
            number = bit_number(row, column, row_bits, total, numbering)
            if column not in (0, columns - 1) and number % step:
                continue
            text = str(number)
            said = measurer.measure(text, font, label_size).width
            centre = (column + 0.5) * bit
            extent = (centre - said / 2 - unit, centre + said / 2 + unit)
            if any(extent[0] < high and low < extent[1] for low, high in shown):
                continue
            shown.append(extent)
            texts.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=centre,
                    y=baseline,
                    spans=(TextSpan(text=text, font=font),),
                    level="label",
                    anchor="middle",
                )
            )
            boxes.append(
                (
                    centre - said / 2,
                    baseline - numbers_label.ascent,
                    centre + said / 2,
                    baseline + numbers_label.descent,
                )
            )
            ruler_numbers.append((number, centre, baseline))
        for boundary in range(columns + 1):
            # A byte is counted from the ruler's bit 0: the left in `left`, the
            # right of the last row in `right`.
            counted = boundary if numbering == "left" else total - (row * row_bits + boundary)
            reach = 2 * RULER_TICK if counted % 8 == 0 else RULER_TICK
            x = boundary * bit
            primitives.append(Path(TICK_ROLE, points=((x, top - reach * unit), (x, top))))

    # -- the rows ------------------------------------------------------------
    tops: list[float] = []
    y = ruler_height
    for row in range(rows):
        if numbering == "right" and row:
            y += ROW_GAP * unit + ruler_height
        tops.append(y)
        y += heights[row]
    bottom = y

    def row_columns(row: int) -> int:
        return min(row_bits, total - row * row_bits)

    ruler(0, tops[0], row_bits if numbering == "left" else row_columns(0))
    if numbering == "right":
        for row in range(1, rows):
            ruler(row, tops[row], row_columns(row))

    segments: dict[tuple[float, float, float, float], str] = {}
    heavy: list[tuple[tuple[float, float], tuple[float, float]]] = []
    cell_boxes: list[Box] = []
    reserved_fill = theme.packet.reserved_fill
    for index, piece in enumerate(pieces):
        written = fields[piece.field]
        left, right = piece.start * bit, piece.end * bit
        top, low = tops[piece.row], tops[piece.row] + heights[piece.row]
        cell_boxes.append((left, top, right, low))
        if written.role == "reserved":
            primitives.append(
                Polygon(
                    FURNITURE_ROLE,
                    points=((left, top), (right, top), (right, low), (left, low)),
                    fill=reserved_fill,
                    region=True,
                )
            )
        edges = [
            ((left, top, right, top), False),
            ((left, low, right, low), False),
            ((left, top, left, low), piece.open_start),
            ((right, top, right, low), piece.open_end),
        ]
        for segment, cut in edges:
            # A cut edge is the row's own end, which no other piece shares.
            segments[segment] = OPEN_ROLE if cut else segments.get(segment, EDGE_ROLE)
            if written.role == "emphasis" and not cut:
                heavy.append(((segment[0], segment[1]), (segment[2], segment[3])))
        # Ticks at every bit inside the piece, from its top and its bottom.
        for boundary in range(piece.start + 1, piece.end):
            x = boundary * bit
            primitives.append(Path(TICK_ROLE, points=((x, top), (x, top + TICK * unit))))
            primitives.append(Path(TICK_ROLE, points=((x, low - TICK * unit), (x, low))))

        middle_x = (left + right) / 2
        middle_y = (top + low) / 2
        label = labels[piece.field]
        if index == holding[piece.field]:
            if label.block is not None:
                height = label.block.height + (holds_height if label.holds else 0.0)
                block_top = middle_y - height / 2
                texts.extend(_centred(label.block, middle_x, block_top))
                boxes.append(
                    (
                        middle_x - label.block.width / 2,
                        block_top,
                        middle_x + label.block.width / 2,
                        block_top + label.block.height,
                    )
                )
                if label.holds:
                    said = measurer.measure(written.holds, "mono", label_size).width
                    baseline = block_top + label.block.height + unit + small.ascent
                    texts.append(
                        TextLine(
                            FURNITURE_ROLE,
                            x=middle_x,
                            y=baseline,
                            spans=(TextSpan(text=written.holds, font="mono"),),
                            level="label",
                            anchor="middle",
                        )
                    )
                    boxes.append(
                        (
                            middle_x - said / 2,
                            baseline - small.ascent,
                            middle_x + said / 2,
                            baseline + small.descent,
                        )
                    )
            elif label.side:
                weight = "bold" if written.role == "emphasis" else "normal"
                said = one_line(label.side, weight)
                # Turned a quarter anticlockwise about its baseline's middle, so the
                # glyphs stand left of x: centre their ascent-to-descent on the cell.
                x = middle_x + (line.ascent - line.descent) / 2
                # A run, not a line: the clearance pass skips rotated runs, which it
                # cannot measure across, so the field's own edges stay whole.
                texts.append(
                    TextRun(
                        FURNITURE_ROLE,
                        x=x,
                        y=middle_y,
                        text=_plain(label.side),
                        level="body",
                        font=font,
                        anchor="middle",
                        weight=weight,
                        rotate=-90.0,
                    )
                )
                boxes.append(
                    (x - line.ascent, middle_y - said / 2, x + line.descent, middle_y + said / 2)
                )
        elif written.text and label.placement != "blank":
            # A narrower piece of a split field says whose it is, where it can.
            room = piece.bits * bit - 2 * pad
            repeat = across(words(written, written.text), room)
            if repeat is None and written.short:
                repeat = across(words(written, written.short), room)
            if repeat is not None and repeat.height <= heights[piece.row] - 2 * vpad:
                block_top = middle_y - repeat.height / 2
                texts.extend(_centred(repeat, middle_x, block_top))
                boxes.append(
                    (
                        middle_x - repeat.width / 2,
                        block_top,
                        middle_x + repeat.width / 2,
                        block_top + repeat.height,
                    )
                )

    for (x1, y1, x2, y2), role in segments.items():
        primitives.append(Path(role, points=((x1, y1), (x2, y2))))
    for start, end in heavy:
        primitives.append(Path(EMPHASIS_EDGE_ROLE, points=(start, end)))

    # -- the key ---------------------------------------------------------------
    y = bottom
    if key:
        y += KEY_GAP * unit
        column = min(max(one_line(bold_lines(name), "bold") for name, _ in key), width * KEY_SHARE)
        gap = 2 * pad + unit * 4
        room = width - column - gap
        for entry_name, entry_words in key:
            name_block = _wrapped(bold_lines(entry_name), column, theme, measurer, "the key's name")
            said_block = _wrapped(entry_words, room, theme, measurer, "the key's words")
            texts.extend(_lines(name_block, 0.0, y))
            texts.extend(_lines(said_block, column + gap, y))
            boxes.append((0.0, y, name_block.width, y + name_block.height))
            boxes.append((column + gap, y, column + gap + said_block.width, y + said_block.height))
            y += max(name_block.height, said_block.height) + unit * 3
        y -= unit * 3

    scene = Scene(
        width=width,
        height=y,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return PacketDrawing(
        scene=scene,
        pieces=pieces,
        cells=tuple(cell_boxes),
        placements=tuple(label.placement for label in labels),
        key=tuple(key),
        ruler=tuple(ruler_numbers),
        texts=tuple(boxes),
    )


def _key_entry(written: PacketField, label: _Label, marker: str) -> tuple[str, str] | None:
    """What the key says about a field, keyed by what its cell shows; or nothing."""
    holds = f"`{written.holds}`" if written.holds and not label.holds else ""
    note = written.note
    if label.placement == "marker":
        name = written.text or "Reserved"
        return marker, _joined(name, holds, note)
    if label.placement in ("short", "short-side"):
        return written.short, _joined(written.text, holds, note)
    if not (holds or note):
        return None
    shown = written.text or "Reserved"
    return shown, _joined("", holds, note)


def _joined(name: str, holds: str, note: str) -> str:
    """A key entry's words: the name spelt out, what it holds, and the note after a dash."""
    head = ": ".join(part for part in (name, holds) if part)
    if head and note:
        return f"{head} — {note}"
    return head or note


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def _wrapped(text: str, width: float, theme: Theme, measurer: TextMeasurer, what: str) -> TextBlock:
    try:
        return wrap(text, max(width, 1.0), measurer, theme=theme, level="body", lead=False)
    except FitError as error:
        raise FitError(
            f"{what} {text[:40]!r} has a word wider than the {width:.0f} units it can take. "
            f"Shorten it, or give the diagram more width."
        ) from error


def _block_spans(block: TextBlock, index: int) -> tuple[TextSpan, ...]:
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
        if (spans := _block_spans(block, index))
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
        if (spans := _block_spans(block, index))
    ]


# ---------------------------------------------------------------------------
# Text: the RFC's own picture, two cells to a bit
# ---------------------------------------------------------------------------

#: The longest name stood on end in text, a letter to a line, as RFC 793 writes
#: its flags: past it the row is taller than it is worth, and the name is keyed.
TEXT_SIDE_MAX: Final = 5


def _letters(text: str) -> list[str]:
    """`text` a character to a line, a combining mark kept with its letter."""
    found: list[str] = []
    for character in text:
        if found and cells(character) == 0:
            found[-1] += character
        else:
            found.append(character)
    return found


def _stands(text: str, room: int) -> bool:
    """Whether `text` may be stood on end, a letter to a line, in `room` cells."""
    letters = _letters(text)
    return (
        " " not in text
        and len(letters) <= TEXT_SIDE_MAX
        and all(cells(letter) <= room for letter in letters)
    )


def _place(line: list[str], start: int, text: str) -> None:
    """Write `text` into `line` from cell `start`, in terminal cells.

    A wide character takes two cells, so the cell after it is emptied; a
    combining mark joins the character before it and takes none.
    """
    at = start
    for character in text:
        width = cells(character)
        if width == 0 and at > start:
            line[at - 1] += character
            continue
        line[at] = character
        if width == 2:
            line[at + 1] = ""
        at += max(width, 1)


#: The glyphs a text packet is drawn in: a field's edge, a cut edge, a row's line.
TEXT_GLYPHS: Final = {
    "unicode": {"edge": "│", "cut": "┆", "line": "─"},
    "ascii": {"edge": "|", "cut": ":", "line": "-"},
}

#: The unicode junction for the arms that meet at a point: (left, right, up, down).
_JOINS: Final = {
    (True, True, False, False): "─",
    (True, True, True, True): "┼",
    (True, True, True, False): "┴",
    (True, True, False, True): "┬",
    (False, True, True, True): "├",
    (True, False, True, True): "┤",
    (False, True, False, True): "┌",
    (True, False, False, True): "┐",
    (False, True, True, False): "└",
    (True, False, True, False): "┘",
    (False, False, True, True): "│",
    (True, False, False, False): "─",
    (False, True, False, False): "─",
    (False, False, True, False): "╵",
    (False, False, False, True): "╷",
}

#: Cells between a key entry's name and its words.
TEXT_KEY_GAP: Final = 2


def packet_text(document: Document, width: int, charset: str) -> str:
    """A `packet` as plain text, two cells to a bit: the RFC's ASCII header.

    Bit 0 is two cells in, every bit two cells on; field edges are `|` (`│`), a
    split field's cut edges `:` (`┆`), and in ASCII every bit boundary of a row's
    line is a `+`, as the RFCs draw it. The ruler is two lines — the tens where
    they change, the units under them — once on top, or over every row when bit 0
    is at the right. A name that does not fit across its field is broken at a
    space, stood on end a letter to a line (RFC 793's flags), replaced by its
    `short`, or keyed by a letter; the key is under the drawing.

    Raises:
        FitError: a row is wider than `width`, at `/bits_per_row`.
    """
    fields = document.packet_fields
    row_bits = document.packet_row_bits
    numbering = document.packet_numbering
    glyphs = TEXT_GLYPHS[charset]
    needed = 2 * row_bits + 1
    if needed > width:
        raise too_wide(
            "/bits_per_row", f"a row of {row_bits} bits, two columns a bit,", needed, width
        )
    pieces, total = pieces_of(fields, row_bits)
    rows = -(-total // row_bits)
    holding = holders(pieces)

    names = [
        " ".join(label_lines(written.text, charset, f"/fields/{index}/text"))
        for index, written in enumerate(fields)
    ]
    shorts = [
        " ".join(label_lines(written.short, charset, f"/fields/{index}/short"))
        for index, written in enumerate(fields)
    ]
    holds = [
        " ".join(label_lines(written.holds, charset, f"/fields/{index}/holds"))
        for index, written in enumerate(fields)
    ]

    def across(text: str, room: int) -> list[str] | None:
        if not text or any(cells(word) > room for word in text.split()):
            return None
        lines = words_of(text, room, "", width)
        return lines if len(lines) <= ACROSS_LINES else None

    # Each field: the lines its holding piece shows, standing or across.
    contents: list[list[str]] = []
    standing: list[bool] = []
    shown_holds: list[bool] = []
    markers: dict[int, str] = {}
    key: list[tuple[str, str]] = []
    for index, written in enumerate(fields):
        room = 2 * pieces[holding[index]].bits - 1
        name, short = names[index], shorts[index]
        placement = "blank"
        lines: list[str] = []
        stood = False
        if name:
            found = across(name, room)
            if found is not None:
                placement, lines = "across", found
            elif short and cells(short) <= room:
                placement, lines = "short", [short]
            elif _stands(name, room):
                placement, lines, stood = "side", _letters(name), True
            elif short and _stands(short, room):
                placement, lines, stood = "short-side", _letters(short), True
            else:
                placement = "marker"
        elif written.note:
            placement = "marker"
        if placement == "marker":
            number = marker_for(len(markers))
            markers[index] = number
            stood = cells(number) > room
            lines = list(number) if stood else [number]
        show = (
            bool(holds[index])
            and placement in ("across", "short")
            and (cells(holds[index]) <= room)
        )
        if show:
            lines = [*lines, holds[index]]
        contents.append(lines)
        standing.append(stood)
        shown_holds.append(show)
        label = _Label(placement, holds=show)
        entry = _key_entry(
            PacketField(
                bits=written.bits,
                text=name,
                short=short,
                holds=holds[index],
                note=" ".join(label_lines(written.note, charset, f"/fields/{index}/note")),
                role=written.role,
            ),
            label,
            markers.get(index, ""),
        )
        if entry is not None:
            said = spelt(entry[1].replace("`", ""), charset, f"/fields/{index}")
            key.append((entry[0], said))

    heights = [1] * rows
    for index, lines in enumerate(contents):
        row = pieces[holding[index]].row
        heights[row] = max(heights[row], len(lines))

    out: list[str] = []

    def ruler(row: int, columns: int) -> None:
        numbers = [bit_number(row, column, row_bits, total, numbering) for column in range(columns)]
        tens = [" "] * (2 * columns + 1)
        units = [" "] * (2 * columns + 1)
        previous = -1
        for column, number in enumerate(numbers):
            units[2 * column + 1] = str(number % 10)
            if number // 10 != previous:
                tens[2 * column + 1] = str(number // 10)
                previous = number // 10
        if max(numbers) >= 10:
            out.append("".join(tens))
        out.append("".join(units))

    def columns_of(row: int) -> int:
        return min(row_bits, total - row * row_bits) if 0 <= row < rows else 0

    def verticals(row: int) -> set[int]:
        return {
            boundary
            for piece in pieces
            if piece.row == row
            for boundary in (piece.start, piece.end)
        }

    def line_between(above: int, below: int) -> str:
        reach = max(columns_of(above), columns_of(below))
        up, down = verticals(above), verticals(below)
        drawn: list[str] = []
        for position in range(2 * reach + 1):
            if position % 2:
                drawn.append(glyphs["line"])
                continue
            boundary = position // 2
            if charset == "ascii":
                drawn.append("+")
                continue
            arms = (
                position > 0,
                position < 2 * reach,
                boundary in up and boundary <= columns_of(above),
                boundary in down and boundary <= columns_of(below),
            )
            drawn.append(_JOINS.get(arms, "─"))
        return "".join(drawn)

    if numbering == "left":
        ruler(0, row_bits)
    for row in range(rows):
        if numbering == "right":
            if row:
                out.append("")
                ruler(row, columns_of(row))
                out.append(line_between(-1, row))
            else:
                ruler(row, columns_of(row))
                out.append(line_between(-1, row))
        elif row == 0:
            out.append(line_between(-1, 0))
        grid = [[" "] * (2 * columns_of(row) + 1) for _ in range(heights[row])]
        for index, piece in enumerate(pieces):
            if piece.row != row:
                continue
            for line in grid:
                line[2 * piece.start] = glyphs["cut" if piece.open_start else "edge"]
                line[2 * piece.end] = glyphs["cut" if piece.open_end else "edge"]
            room = 2 * piece.bits - 1
            if index == holding[piece.field]:
                lines = contents[piece.field]
            else:
                lines = across(names[piece.field], room) or (
                    [shorts[piece.field]]
                    if shorts[piece.field] and cells(shorts[piece.field]) <= room
                    else []
                )
                if contents[piece.field] == [] or len(lines) > heights[row]:
                    lines = []
            first = (heights[row] - len(lines)) // 2
            for offset, text in enumerate(lines):
                _place(grid[first + offset], 2 * piece.start + 1, centred(text, room))
        out.extend("".join(line) for line in grid)
        if numbering == "right" or row == rows - 1:
            out.append(line_between(row, -1))
        else:
            out.append(line_between(row, row + 1))

    if key:
        out.append("")
        column = max(cells(name) for name, _ in key)
        room = width - column - TEXT_KEY_GAP
        if room < 10:
            raise too_wide("/fields", "the key's widest name", column + TEXT_KEY_GAP + 10, width)
        for name, said in key:
            said_lines = words_of(said, room, "/fields", width, column + TEXT_KEY_GAP)
            for at, text in enumerate(said_lines):
                lead = name if at == 0 else ""
                out.append(lead + " " * (column - cells(lead) + TEXT_KEY_GAP) + text)
    return finished([*out, *caption_lines(document.caption, width, charset)])


__all__ = [
    "PacketDrawing",
    "Piece",
    "bit_number",
    "holders",
    "packet_drawing",
    "packet_scene",
    "packet_text",
    "pieces_of",
]
