"""Plain text on a character grid: the shared parts of every kind's text form.

`render --format text` is a second emitter, not a rasteriser. A scene's
coordinates are in points and its words are proportional, so rounding both to
character cells would produce exactly the collisions the SVG layout avoided.
Each kind that has a text form lays itself out again here, on cells, from its
layout's *topology* — the order of its rows, its columns, its intervals — and
this module holds what they share:

* **Width in terminal cells**, not characters. An East Asian wide or fullwidth
  character takes two cells, so a line is measured the way a terminal draws it
  (`cells`). No dependency: `unicodedata` already knows.
* **Roles as glyphs.** Text has no ink or weight to spend, so a role is a line
  style — light, heavy, rounded, double, dashed — and the same promise the SVG's
  greyscale test makes is made with characters: two roles never draw alike.
* **One refusal for a drawing too wide**, at the pointer of the widest thing
  and with the width it needs. Text never wraps a box mid-word and never
  truncates a label; the kinds whose SVG wraps a label wrap it here too, at
  word boundaries, and refuse a single word that does not fit.
* **`Grid`**, for the two kinds whose lines meet and cross (`sequence`,
  `timeline`): every cell keeps the arms drawn into it, and the junction glyph is
  chosen from them once everything is placed, so a lifeline crossed by an arrow
  is `┼` without either of them knowing about the other.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from drawspec.errors import DrawspecError, FitError

#: The character sets a text form is drawn in. `ascii` is bytes below 128 only.
CHARSETS: Final = ("unicode", "ascii")

#: The width a text form is drawn to when nobody says otherwise: a terminal's.
DEFAULT_WIDTH: Final = 80

#: Kinds drawn to a wider default, because their reference documents need it:
#: participants and lanes sit side by side, so the width grows with their count.
#: Measured in phase 2 of the text proposal — at 80, three of seven sequences
#: and three of nine lanes are refused; at 100, one lanes document is.
WIDE_WIDTH: Final = 100
WIDE_KINDS: Final = frozenset({"lanes", "sequence"})


def default_width(kind: str) -> int:
    """The width a `kind` is drawn to when the caller names none."""
    return WIDE_WIDTH if kind in WIDE_KINDS else DEFAULT_WIDTH


#: Characters an `ascii` drawing writes for the punctuation a label commonly
#: carries outside ASCII. Anything else that will not decompose to ASCII is
#: refused rather than replaced with a `?` the author never wrote.
ASCII_SPELLINGS: Final = {
    "\N{HORIZONTAL ELLIPSIS}": "...",
    "\N{RIGHTWARDS ARROW}": "->",
    "\N{LEFTWARDS ARROW}": "<-",
    "\N{UPWARDS ARROW}": "^",
    "\N{DOWNWARDS ARROW}": "v",
    "\N{EM DASH}": "--",
    "\N{EN DASH}": "-",
    "\N{MINUS SIGN}": "-",
    "\N{LEFT SINGLE QUOTATION MARK}": "'",
    "\N{RIGHT SINGLE QUOTATION MARK}": "'",
    "\N{LEFT DOUBLE QUOTATION MARK}": '"',
    "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
    "\N{MULTIPLICATION SIGN}": "x",
    "\N{MIDDLE DOT}": "-",
    "\N{BULLET}": "*",
    "\N{POUND SIGN}": "GBP ",
    "\N{EURO SIGN}": "EUR ",
    "\N{YEN SIGN}": "JPY ",
    "\N{DEGREE SIGN}": " deg",
    "\N{NO-BREAK SPACE}": " ",
}


def cells(text: str) -> int:
    """How many terminal cells `text` takes: two for a wide character, none for a mark."""
    total = 0
    for character in text:
        if unicodedata.combining(character) or character in "​‍️":
            continue
        total += 2 if unicodedata.east_asian_width(character) in ("W", "F") else 1
    return total


def pad(text: str, width: int) -> str:
    """`text` padded with spaces on the right to `width` cells."""
    return text + " " * max(width - cells(text), 0)


def centred(text: str, width: int) -> str:
    """`text` centred in `width` cells, the odd cell on the right."""
    room = max(width - cells(text), 0)
    return " " * (room // 2) + text + " " * (room - room // 2)


def plain(text: str) -> str:
    """A label without its inline markup: `**bold**` and `code` spans are drawn, not spelt."""
    return text.replace("**", "").replace("`", "")


def spelt(text: str, charset: str, pointer: str = "") -> str:
    """`text` in the charset: unchanged in `unicode`, spelt in ASCII in `ascii`.

    Raises:
        DrawspecError: an `ascii` drawing meets a character with no ASCII spelling.
    """
    if charset != "ascii" or text.isascii():
        return text
    out: list[str] = []
    for character in text:
        if character.isascii():
            out.append(character)
        elif character in ASCII_SPELLINGS:
            out.append(ASCII_SPELLINGS[character])
        else:
            decomposed = "".join(
                part
                for part in unicodedata.normalize("NFKD", character)
                if not unicodedata.combining(part)
            )
            if not decomposed or not decomposed.isascii():
                raise DrawspecError(
                    f"{pointer or '/'}: {text!r} has {character!r}, which has no spelling in "
                    f"ASCII. Draw it with --charset unicode, or write the label in ASCII."
                )
            out.append(decomposed)
    return "".join(out)


def label_lines(text: str, charset: str, pointer: str = "") -> list[str]:
    """A label's lines as written — one per newline — without markup, in the charset."""
    return [spelt(line, charset, pointer) for line in plain(text).split("\n")]


def too_wide(pointer: str, what: str, needed: int, width: int) -> FitError:
    """The one refusal for a text drawing wider than its width, at the widest thing."""
    return FitError(
        f"{pointer or '/'}: {what} makes this drawing {needed} columns wide, and the text "
        f"width is {width}. Shorten it, draw with --width {needed} or more, or render it as SVG."
    )


def wrapped(text: str, room: int, pointer: str, width: int, extra: int = 0) -> list[str]:
    """`text` broken at spaces into lines of at most `room` cells.

    Only ever between words: a word longer than `room` refuses at `pointer`,
    naming the width the drawing would need for it — the word and `extra`, what
    the drawing spends beside the column, `room` being `width - extra`.

    Raises:
        FitError: one word is wider than the room.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            if not word:
                continue
            if cells(word) > room:
                raise too_wide(pointer, f"the word {word!r}", cells(word) + extra, width)
            candidate = f"{line} {word}" if line else word
            if cells(candidate) <= room:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def words_fit(texts: Sequence[tuple[str, str]], room: int, width: int, extra: int = 0) -> None:
    """Refuse when the longest word of any of `texts` — (text, pointer) — exceeds `room`.

    Checked over all of them before any is wrapped, so the refusal names the
    word that decides the width, not merely the first one found too long.

    Raises:
        FitError: at the longest word's pointer, with the width it needs.
    """
    found = [(cells(word), word, pointer) for text, pointer in texts for word in text.split()]
    if not found:
        return
    size, word, pointer = max(found, key=lambda entry: entry[0])
    if size > room:
        raise too_wide(pointer, f"the word {word!r}", size + extra, width)


def finished(lines: Iterable[str]) -> str:
    """The drawing as one string: no trailing whitespace, no trailing blank, one newline."""
    out = [line.rstrip() for line in lines]
    while out and not out[-1]:
        out.pop()
    while out and not out[0]:
        out.pop(0)
    return "\n".join(out) + "\n"


def caption_lines(caption: str, width: int, charset: str) -> list[str]:
    """A document's caption under the drawing, after a blank line, wrapped like the SVG's."""
    if not caption:
        return []
    text = " ".join(label_lines(caption, charset, "/caption"))
    return ["", *wrapped(text, width, "/caption", width)]


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoxGlyphs:
    """One box style: corners, sides, and the tees a line joins it by."""

    top_left: str
    top: str
    top_right: str
    left: str
    right: str
    bottom_left: str
    bottom: str
    bottom_right: str
    down: str
    """On the bottom edge, where a line leaves downward."""

    up: str
    """On the top edge, where a line arrives from above."""

    joined: str
    """On the left side, where a line arrives from the left."""


#: The box styles, per charset. Which role takes which is `BOX_STYLE`.
BOXES: Final = {
    "unicode": {
        "plain": BoxGlyphs("┌", "─", "┐", "│", "│", "└", "─", "┘", "┬", "┴", "┤"),
        "heavy": BoxGlyphs("┏", "━", "┓", "┃", "┃", "┗", "━", "┛", "┯", "┷", "┨"),
        "rounded": BoxGlyphs("╭", "─", "╮", "│", "│", "╰", "─", "╯", "┬", "┴", "┤"),
        "double": BoxGlyphs("╔", "═", "╗", "║", "║", "╚", "═", "╝", "╤", "╧", "╢"),
        "dashed": BoxGlyphs("┌", "┄", "┐", "┆", "┆", "└", "┄", "┘", "┬", "┴", "┤"),
    },
    "ascii": {
        "plain": BoxGlyphs("+", "-", "+", "|", "|", "+", "-", "+", "+", "+", "|"),
        "heavy": BoxGlyphs("#", "=", "#", "#", "#", "#", "=", "#", "#", "#", "#"),
        "rounded": BoxGlyphs(".", "-", ".", "(", ")", "'", "-", "'", "+", "+", "("),
        "double": BoxGlyphs("*", "-", "*", "|", "|", "*", "-", "*", "+", "+", "|"),
        "dashed": BoxGlyphs("+", ".", "+", ":", ":", "+", ".", "+", "+", "+", ":"),
    },
}

#: Which box style each role draws: the proposal's table, plus `start`, whose SVG
#: pill is thinner than `terminal`'s and which must not draw like it.
BOX_STYLE: Final = {
    "emphasis": "heavy",
    "strong": "heavy",
    "terminal": "rounded",
    "start": "double",
    "note": "dashed",
}


def box_glyphs(role: str, charset: str) -> BoxGlyphs:
    """The glyphs a box in `role` is drawn with."""
    return BOXES[charset][BOX_STYLE.get(role, "plain")]


def boxed(
    lines: Sequence[str],
    role: str,
    charset: str,
    inner: int | None = None,
    align: str = "left",
    padding: int = 1,
) -> list[str]:
    """`lines` in a box of the role's style, `padding` spaces inside each side.

    Every line comes back `inner + 2 * (padding + 1)` cells wide; `inner`
    defaults to the widest line.
    """
    glyphs = box_glyphs(role, charset)
    inside = max((cells(line) for line in lines), default=0) if inner is None else inner
    place = centred if align == "centre" else pad
    space = " " * padding
    return [
        glyphs.top_left + glyphs.top * (inside + 2 * padding) + glyphs.top_right,
        *(f"{glyphs.left}{space}{place(line, inside)}{space}{glyphs.right}" for line in lines),
        glyphs.bottom_left + glyphs.bottom * (inside + 2 * padding) + glyphs.bottom_right,
    ]


# ---------------------------------------------------------------------------
# Lines and heads
# ---------------------------------------------------------------------------

#: The line style each edge role draws: the proposal's table.
LINE_STYLE: Final = {
    "strong": "heavy",
    "weak": "dashed",
    "aside": "dashed",
    "realizes": "dashed",
}

#: A straight run, per charset and style: horizontal, then vertical.
STRAIGHT: Final = {
    "unicode": {
        "light": ("─", "│"),
        "heavy": ("━", "┃"),
        "dashed": ("┄", "┆"),
        "double": ("═", "║"),
    },
    "ascii": {
        "light": ("-", "|"),
        "heavy": ("=", "#"),
        "dashed": (".", ":"),
        "double": ("=", "#"),
    },
}

#: Arrowheads per charset: (filled right, filled left, open right, open left).
#: A filled head is a call or a flow; an open one, a reply or an async message.
HEADS: Final = {
    "unicode": ("▶", "◀", "▷", "◁"),
    "ascii": (">", "<", ">>", "<<"),
}

#: The edge roles whose head is open rather than filled, as the default theme draws them.
OPEN_HEADS: Final = ("weak", "async")


def line_style(role: str) -> str:
    """The line style an edge role draws."""
    return LINE_STYLE.get(role, "light")


def head(role: str, charset: str, rightward: bool) -> str:
    """The arrowhead an edge role ends in, pointing right or left."""
    filled_right, filled_left, open_right, open_left = HEADS[charset]
    if role in OPEN_HEADS:
        return open_right if rightward else open_left
    return filled_right if rightward else filled_left


_N, _E, _S, _W = "n", "e", "s", "w"

_LIGHT_JOINS: Final = {
    frozenset("ne"): "└",
    frozenset("nw"): "┘",
    frozenset("es"): "┌",
    frozenset("sw"): "┐",
    frozenset("nes"): "├",
    frozenset("nsw"): "┤",
    frozenset("esw"): "┬",
    frozenset("new"): "┴",
    frozenset("nesw"): "┼",
}
_HEAVY_JOINS: Final = {
    frozenset("ne"): "┗",
    frozenset("nw"): "┛",
    frozenset("es"): "┏",
    frozenset("sw"): "┓",
    frozenset("nes"): "┣",
    frozenset("nsw"): "┫",
    frozenset("esw"): "┳",
    frozenset("new"): "┻",
    frozenset("nesw"): "╋",
}
#: A heavy vertical met by a light horizontal: an activation bar crossed by a message.
_HEAVY_UPRIGHT: Final = {
    frozenset("nes"): "┠",
    frozenset("nsw"): "┨",
    frozenset("nesw"): "╂",
}


class Grid:
    """A character grid where lines keep their arms until they are drawn.

    `line` records, in each cell, which of its four sides a stroke leaves by and
    in what style; `text` writes characters that win over any stroke. `lines`
    picks every junction's glyph from the arms that met in it, so nothing placed
    needs to know what else crosses its cells.
    """

    def __init__(self, charset: str) -> None:
        self.charset = charset
        self._text: dict[tuple[int, int], str] = {}
        self._arms: dict[tuple[int, int], dict[str, str]] = {}

    def text(self, row: int, column: int, text: str) -> None:
        """Write `text` from `column` on `row`, a wide character taking two cells."""
        for character in text:
            self._text[(row, column)] = character
            if cells(character) == 2:
                self._text[(row, column + 1)] = ""
                column += 2
            else:
                column += 1

    def horizontal(self, row: int, first: int, last: int, style: str = "light") -> None:
        """A stroke along `row` from `first` to `last`, both cells included."""
        low, high = sorted((first, last))
        for column in range(low, high + 1):
            arms = self._arms.setdefault((row, column), {})
            if column > low:
                arms[_W] = style
            if column < high:
                arms[_E] = style
            if low == high:
                arms.setdefault(_E, style)
                arms.setdefault(_W, style)

    def vertical(self, column: int, first: int, last: int, style: str = "light") -> None:
        """A stroke down `column` from row `first` to row `last`, both included."""
        low, high = sorted((first, last))
        for row in range(low, high + 1):
            arms = self._arms.setdefault((row, column), {})
            if row > low:
                arms[_N] = style
            if row < high:
                arms[_S] = style
            if low == high:
                arms.setdefault(_N, style)
                arms.setdefault(_S, style)

    def arm(self, row: int, column: int, side: str, style: str = "light") -> None:
        """One arm, `n`, `e`, `s` or `w`, in one cell."""
        self._arms.setdefault((row, column), {})[side] = style

    def used(self, row: int, column: int) -> bool:
        """Whether anything is drawn in the cell."""
        return (row, column) in self._text or (row, column) in self._arms

    @property
    def width(self) -> int:
        keys = [*self._text, *self._arms]
        return max((column for _, column in keys), default=-1) + 1

    @property
    def height(self) -> int:
        keys = [*self._text, *self._arms]
        return max((row for row, _ in keys), default=-1) + 1

    def _glyph(self, arms: dict[str, str]) -> str:
        sides = frozenset(arms)
        styles = set(arms.values())
        across = sides <= {_E, _W}
        upright = sides <= {_N, _S}
        if across or upright:
            if "heavy" in styles:
                style = "heavy"
            elif "double" in styles:
                style = "double"
            elif "light" in styles:
                style = "light"
            else:
                style = "dashed"
            return STRAIGHT[self.charset][style][0 if across else 1]
        if self.charset == "ascii":
            return "+"
        if styles == {"heavy"}:
            return _HEAVY_JOINS[sides]
        if (
            arms.get(_N) == "heavy"
            and arms.get(_S) == "heavy"
            and sides in _HEAVY_UPRIGHT
            and all(arms[side] != "heavy" for side in sides - {_N, _S})
        ):
            return _HEAVY_UPRIGHT[sides]
        return _LIGHT_JOINS[sides]

    def lines(self) -> list[str]:
        """The grid as lines of text, trailing spaces removed."""
        out: list[str] = []
        for row in range(self.height):
            characters: list[str] = []
            for column in range(self.width):
                if (row, column) in self._text:
                    characters.append(self._text[(row, column)])
                elif (row, column) in self._arms:
                    characters.append(self._glyph(self._arms[(row, column)]))
                else:
                    characters.append(" ")
            out.append("".join(characters).rstrip())
        return out


@dataclass(frozen=True)
class Drawn:
    """One line of a text drawing, with the thing it is the line of.

    The pointer and the words name that thing in a refusal, so a drawing too wide
    is refused at whatever made its widest line wide.
    """

    text: str
    pointer: str = ""
    what: str = ""
    status: str = ""
    """The `+ ~ -` status of the thing, on the line its mark goes on; else empty."""

    joint: bool = False
    """Whether this is the line a guide joins the thing on."""


def widest(lines: Sequence[Drawn], width: int) -> None:
    """Refuse when any of `lines` is wider than `width`, at the widest line's thing.

    Raises:
        FitError: a line is wider than `width`.
    """
    if not lines:
        return
    line = max(lines, key=lambda drawn: cells(drawn.text.rstrip()))
    needed = cells(line.text.rstrip())
    if needed > width:
        raise too_wide(line.pointer, line.what, needed, width)


__all__ = [
    "BOXES",
    "BOX_STYLE",
    "CHARSETS",
    "DEFAULT_WIDTH",
    "WIDE_KINDS",
    "WIDE_WIDTH",
    "Drawn",
    "Grid",
    "box_glyphs",
    "boxed",
    "caption_lines",
    "cells",
    "centred",
    "default_width",
    "finished",
    "head",
    "label_lines",
    "line_style",
    "pad",
    "plain",
    "spelt",
    "too_wide",
    "widest",
    "words_fit",
    "wrapped",
]
