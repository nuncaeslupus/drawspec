"""The legend: what each fill in a drawing stands for.

Shared by the two families that tell things apart by fill — `chart`, whose bars
and areas take the theme's fill sequence by position, and `matrix`, whose cells
take it by the group they name. Both had the same hole. A chart with three bar
series drew three fills and named none of them; the matrix original this project
is replacing carried a legend the redraw quietly dropped.

Three rules shape it.

**It is drawn when it is needed and not otherwise.** One fill explains itself —
there is nothing to tell apart — so a single-series chart gets no legend and
loses no height to one. Two or more, and the drawing cannot be read without it.

**The names are the author's own.** A series' `name`, a cell group's `group`.
Nothing here invents a label, and nothing here decides what a fill means; it
reports the pairing the drawing already made.

**It sits under the drawing, across the full width, and wraps.** Beside the plot
it would compete with the thing it explains for the width that makes the type
size comparable across a document. Under it, the drawing keeps its width and the
legend takes the height it needs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from drawspec.scene import Path, Polygon, Primitive, TextRun
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The role a swatch is drawn in. A plain rectangle with the theme's ordinary
#: line weight: a swatch is a sample of a fill, so everything about it except
#: the fill has to be the least remarkable thing the theme draws.
SWATCH_ROLE: Final = "step"

#: The role legend text is tagged with. As elsewhere, a `TextRun` takes no
#: styling from its role — its level decides how it is set — but every primitive
#: carries a role the theme declares.
TEXT_ROLE: Final = "step"

#: A swatch's height, as a multiple of the label line's height. Slightly under
#: one, so the swatch sits on the text's own line rather than reading as a box
#: the text is inside.
SWATCH_SHARE: Final = 0.9

#: A swatch's width, as a multiple of its height. Wider than tall on purpose: a
#: fill pattern tiles every four units, and a square swatch at label size shows
#: two tiles of it — enough to be a mark and not enough to be recognised as the
#: same mark that fills the bar. It is a sample of a band, so it is band-shaped.
SWATCH_ASPECT: Final = 1.8


@dataclass(frozen=True)
class Entry:
    """One thing a legend names, and the sample that stands for it."""

    text: str
    role: str
    fill: str = ""
    """The fill pattern, or empty for something drawn as a line rather than filled.

    A line series is told apart from another line by its role's dash and weight,
    not by a fill, so its sample is a short length of its own line. Same legend,
    same row, different sample — because what a reader has to match it against is
    different.
    """

    colour: str = ""
    """The colour that fill is drawn in, when the theme declares mark colours.

    Carried so the swatch matches the mark. A key that showed a grey hatch for a
    blue bar would be worse than no key: it would be a second claim about which
    fill means what, disagreeing with the first.
    """


def entries_for(items: Sequence[tuple[str, str, bool]], theme: Theme) -> tuple[Entry, ...]:
    """The legend for a sequence of `(name, role, filled)`, in the order given.

    The fill sequence advances only for the filled ones, which is exactly what
    the drawing does — so the legend cannot disagree with it about which fill
    belongs to which name. That agreement is structural rather than checked:
    there is one rule and both sides run it.

    Fewer than two things is no legend at all. One explains itself; there is
    nothing to tell it apart from.
    """
    if len(items) < 2:
        return ()
    entries = []
    filled = 0
    for text, role, is_filled in items:
        if is_filled:
            entries.append(
                Entry(text, role, theme.mark.fill_for(filled), theme.mark.colour_for(filled))
            )
            filled += 1
        else:
            entries.append(Entry(text, role))
    return tuple(entries)


def _rows(
    entries: tuple[Entry, ...], theme: Theme, measurer: TextMeasurer, width: float
) -> list[list[tuple[Entry, float]]]:
    """The entries broken into rows that fit `width`, with each one's own width.

    Greedy, left to right, in the order given — the reading order of a legend is
    the order the things appear in the drawing, and reflowing to pack the rows
    tighter would break that for nothing a reader gains.
    """
    size = theme.scale["label"]
    gap = theme.box.padding.top
    sample = _sample_width(theme, measurer)
    rows: list[list[tuple[Entry, float]]] = [[]]
    used = 0.0
    for entry in entries:
        span = sample + gap / 2 + measurer.measure(entry.text, theme.font.default, size).width
        if rows[-1] and used + gap + span > width:
            rows.append([])
            used = 0.0
        used += (gap if rows[-1] else 0.0) + span
        rows[-1].append((entry, span))
    return rows


def height_of(
    entries: tuple[Entry, ...], theme: Theme, measurer: TextMeasurer, width: float
) -> float:
    """How much of the bottom edge this legend needs, including its own gap above.

    Zero for an empty legend, so a caller may reserve this unconditionally and a
    drawing with nothing to explain is exactly the size it was before.
    """
    if not entries:
        return 0.0
    line = measurer.measure("0", theme.font.default, theme.scale["label"])
    gap = theme.box.padding.top
    return gap + len(_rows(entries, theme, measurer, width)) * (line.height + gap / 2)


def primitives_for(
    entries: tuple[Entry, ...],
    theme: Theme,
    measurer: TextMeasurer,
    left: float,
    top: float,
    width: float,
) -> tuple[Primitive, ...]:
    """The swatches and their names, laid out from `(left, top)` across `width`.

    `top` is the top of the band `height_of` reserved, gap included, so a caller
    passes the same number to both and the two cannot drift apart.
    """
    if not entries:
        return ()
    size = theme.scale["label"]
    line = measurer.measure("0", theme.font.default, size)
    gap = theme.box.padding.top
    sample = _sample_width(theme, measurer)
    tall = line.height * SWATCH_SHARE

    drawn: list[Primitive] = []
    y = top + gap
    for row in _rows(entries, theme, measurer, width):
        x = left
        middle = y + line.height / 2
        for entry, span in row:
            if entry.fill:
                low, high = middle - tall / 2, middle + tall / 2
                # A polygon rather than a rect, for the reason a bar is one: a
                # rect takes the theme's corner radius, and a rounded swatch is a
                # shape rather than a sample of a fill.
                drawn.append(
                    Polygon(
                        SWATCH_ROLE,
                        points=((x, low), (x + sample, low), (x + sample, high), (x, high)),
                        fill=entry.fill,
                        fill_colour=entry.colour,
                    )
                )
            else:
                # Its own role, so the sample carries the dash and the weight the
                # line in the drawing has. That is what a reader matches it on.
                drawn.append(Path(entry.role, points=((x, middle), (x + sample, middle))))
            drawn.append(
                TextRun(
                    TEXT_ROLE,
                    x=x + sample + gap / 2,
                    y=middle + (line.ascent - line.descent) / 2,
                    text=entry.text,
                    level="label",
                    font=theme.font.default,
                    anchor="start",
                )
            )
            x += span + gap
        y += line.height + gap / 2
    return tuple(drawn)


def _sample_width(theme: Theme, measurer: TextMeasurer) -> float:
    """How wide every sample is — one number, so the column of names lines up."""
    line = measurer.measure("0", theme.font.default, theme.scale["label"])
    return line.height * SWATCH_SHARE * SWATCH_ASPECT


__all__ = [
    "SWATCH_ASPECT",
    "SWATCH_ROLE",
    "SWATCH_SHARE",
    "TEXT_ROLE",
    "Entry",
    "entries_for",
    "height_of",
    "primitives_for",
]
