"""The drafting sheet: a ground, a grid, a zoned border, registration marks and a
title block, drawn around a diagram the way an engineering drawing is framed.

This is furniture, not drawing. Nothing here carries meaning a document wrote,
so none of it goes through `Scene` and its roles: it is laid out once, outside
the drawing, and painted in the four colours `[canvas]` declares for it. It is
the README banner's own furniture (`tools/hero.py` draws its sheet with these
functions), so a diagram rendered in the `blueprint` theme and the banner are
one sheet.

**Standalone only.** The `inline` profile inherits its page — its ink, and its
background — so a sheet there would be a blue rectangle painted into somebody
else's document. `emit` draws a sheet in the `standalone` profile, which is
also what PNG export rasterises, and ignores it in `inline`, the same way it
ignores `[canvas] ink`.

**Outside the drawing, never on it.** `around` grows the canvas to make
room: the border and its channel go around the framed drawing on all four
sides, and the title block takes a strip of its own below it. The drawing is
moved, not overlapped, so nothing a document draws can sit under a zone letter
or behind the title block — the collision and clipping checks hold by
construction rather than by luck.
"""

from __future__ import annotations

import math
import string
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final
from xml.sax.saxutils import escape

from drawspec.errors import FitError
from drawspec.scene import Scene, moved

if TYPE_CHECKING:
    from drawspec.schema import Document
    from drawspec.text.measure import TextMeasurer
    from drawspec.theme import Theme

#: How far in from the canvas edge the outer border line sits.
INSET: Final = 10.0

#: The channel between the outer and inner border lines, where the zones are lettered.
BAND: Final = 14.0

#: Blank between the inner border and the framed drawing. Room for the
#: registration marks in the corners and the centring arrows on each edge.
PAD: Final = 20.0

#: Roughly how long one zone is, in user units. The count is rounded from it.
ZONE: Final = 160.0

#: The registration mark's radius on a diagram's sheet.
MARK_RADIUS: Final = 4.5

#: The narrowest a title block is drawn, however short its words.
BLOCK_MIN_WIDTH: Final = 260.0


def number(value: float) -> str:
    """One number, one spelling: three decimals at most, no trailing zeros."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


@dataclass(frozen=True)
class Palette:
    """The sheet's colours. `ground` may be `none`: then the sheet is drawn on the page."""

    ground: str
    ink: str
    soft: str
    """Lettering that labels rather than says: zone letters, title-block keys."""

    grid: str
    accent: str
    """Registration marks and the drawing number — the one warm mark on the sheet."""


@dataclass(frozen=True)
class Field:
    """One labelled value in a title block."""

    key: str
    value: str


@dataclass(frozen=True)
class BlockStyle:
    """Sizes in a title block: row heights, type sizes and where each baseline sits."""

    head_height: float = 36.0
    row_height: float = 30.0
    foot_height: float = 30.0
    key_size: float = 9.0
    head_size: float = 13.0
    number_size: float = 10.0
    row_size: float = 10.0
    cell_size: float = 10.0
    pad: float = 9.0
    head_key_drop: float = 12.0
    key_drop: float = 12.0
    head_rise: float = 8.0
    number_rise: float = 9.0
    value_rise: float = 7.0
    key_spacing: float = 1.0


@dataclass(frozen=True)
class TitleBlock:
    """What a title block says: a headline and its number, full-width rows, cells."""

    head: Field
    number: str
    rows: tuple[Field, ...]
    cells: tuple[tuple[Field, float], ...]
    """Each bottom cell and its width; the widths add up to the block's."""

    @property
    def width(self) -> float:
        return sum(width for _, width in self.cells)

    def height(self, style: BlockStyle) -> float:
        return style.head_height + style.row_height * len(self.rows) + style.foot_height


# --- primitives --------------------------------------------------------------


def text(
    x: float,
    y: float,
    content: str,
    size: float,
    fill: str,
    *,
    family: str,
    weight: str = "normal",
    anchor: str = "start",
    spacing: float = 0,
    opacity: float = 1,
) -> str:
    """One `<text>`, positioned by its baseline."""
    attrs = [
        f'x="{number(x)}"',
        f'y="{number(y)}"',
        f'font-family="{escape(family, {chr(34): "&quot;"})}"',
        f'font-size="{size:g}"',
        f'fill="{fill}"',
    ]
    if weight != "normal":
        attrs.append(f'font-weight="{weight}"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if spacing:
        attrs.append(f'letter-spacing="{spacing:g}"')
    if opacity != 1:
        attrs.append(f'fill-opacity="{opacity:g}"')
    return f"<text {' '.join(attrs)}>{escape(content)}</text>"


def line(x1: float, y1: float, x2: float, y2: float, stroke: str, width: float = 1) -> str:
    return (
        f'<line x1="{number(x1)}" y1="{number(y1)}" x2="{number(x2)}" y2="{number(y2)}" '
        f'stroke="{stroke}" stroke-width="{width:g}"/>'
    )


# --- the furniture -----------------------------------------------------------


def grid(
    prefix: str,
    width: float,
    height: float,
    palette: Palette,
    *,
    x: float = 0,
    y: float = 0,
    pattern: bool = True,
    minor: float = 16,
    major: float = 80,
) -> str:
    """The ground, and over it a fine grid with a heavier line every fifth."""
    at = (f'x="{number(x)}" ' if x else "") + (f'y="{number(y)}" ' if y else "")
    size = f'{at}width="{number(width)}" height="{number(height)}"'
    out = []
    if pattern:
        out.append(
            "<defs>"
            f'<pattern id="{prefix}-grid-minor" width="{number(minor)}" '
            f'height="{number(minor)}" patternUnits="userSpaceOnUse">'
            f'<path d="M {number(minor)} 0 L 0 0 0 {number(minor)}" fill="none" '
            f'stroke="{palette.grid}" stroke-width="0.5" stroke-opacity="0.09"/></pattern>'
            f'<pattern id="{prefix}-grid-major" width="{number(major)}" '
            f'height="{number(major)}" patternUnits="userSpaceOnUse">'
            f'<path d="M {number(major)} 0 L 0 0 0 {number(major)}" fill="none" '
            f'stroke="{palette.grid}" stroke-width="0.8" stroke-opacity="0.16"/></pattern>'
            "</defs>"
        )
    if palette.ground != "none":
        out.append(f'<rect {size} fill="{palette.ground}"/>')
    if pattern:
        out.append(f'<rect {size} fill="url(#{prefix}-grid-minor)"/>')
        out.append(f'<rect {size} fill="url(#{prefix}-grid-major)"/>')
    return "".join(out)


def border(
    width: float,
    height: float,
    palette: Palette,
    *,
    family: str,
    inset: float = INSET,
    band: float = BAND,
    across: int = 4,
    down: int = 2,
    size: float = 9,
) -> str:
    """A double border with zone numbers across and zone letters down, as a sheet has.

    Numbers run right to left along the top and bottom and letters top to bottom
    down the sides, so "C3" names the same square on every sheet. The centring
    arrows at the middle of each edge are the sheet's own, for whoever reproduces it.
    """
    out = []
    outer, inner = inset, inset + band
    out.append(
        f'<rect x="{number(outer)}" y="{number(outer)}" width="{number(width - 2 * outer)}" '
        f'height="{number(height - 2 * outer)}" fill="none" stroke="{palette.ink}" '
        'stroke-opacity="0.55" stroke-width="1"/>'
    )
    out.append(
        f'<rect x="{number(inner)}" y="{number(inner)}" width="{number(width - 2 * inner)}" '
        f'height="{number(height - 2 * inner)}" fill="none" stroke="{palette.ink}" '
        'stroke-opacity="0.8" stroke-width="1.6"/>'
    )
    # Baselines that centre a capital in the band: a capital is about three
    # quarters of the type size tall.
    drop = round((band + 0.75 * size) / 2)
    rise = round((band - 0.75 * size) / 2)
    span_x = (width - 2 * inner) / across
    for i in range(across + 1):
        x = inner + i * span_x
        if 0 < i < across:
            out.append(line(x, outer, x, inner, palette.ink, 0.8))
            out.append(line(x, height - inner, x, height - outer, palette.ink, 0.8))
        if i < across:
            label = str(across - i)
            mid = x + span_x / 2
            for row in (outer + drop, height - outer - rise):
                out.append(
                    text(mid, row, label, size, palette.soft, family=family, anchor="middle")
                )
    span_y = (height - 2 * inner) / down
    letters = string.ascii_uppercase
    for i in range(down + 1):
        y = inner + i * span_y
        if 0 < i < down:
            out.append(line(outer, y, inner, y, palette.ink, 0.8))
            out.append(line(width - inner, y, width - outer, y, palette.ink, 0.8))
        if i < down:
            label = letters[i % len(letters)]
            mid = y + span_y / 2 + round(0.375 * size)
            for x in (outer + band / 2, width - outer - band / 2):
                out.append(text(x, mid, label, size, palette.soft, family=family, anchor="middle"))
    cx, cy = width / 2, height / 2
    n = number
    out.append(
        f'<path d="M {n(cx - 5)} {n(inner)} L {n(cx)} {n(inner + 8)} L {n(cx + 5)} {n(inner)} Z '
        f"M {n(cx - 5)} {n(height - inner)} L {n(cx)} {n(height - inner - 8)} "
        f"L {n(cx + 5)} {n(height - inner)} Z "
        f"M {n(inner)} {n(cy - 5)} L {n(inner + 8)} {n(cy)} L {n(inner)} {n(cy + 5)} Z "
        f"M {n(width - inner)} {n(cy - 5)} L {n(width - inner - 8)} {n(cy)} "
        f'L {n(width - inner)} {n(cy + 5)} Z" '
        f'fill="{palette.ink}" fill-opacity="0.8"/>'
    )
    return "".join(out)


def registration(x: float, y: float, colour: str, r: float = 7) -> str:
    """A registration mark: a ring with crosshairs that overrun it."""
    n = number
    return (
        f'<g stroke="{colour}" stroke-width="0.9" fill="none" stroke-opacity="0.9">'
        f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}"/>'
        f'<path d="M {n(x - r * 1.7)} {n(y)} H {n(x + r * 1.7)} '
        f'M {n(x)} {n(y - r * 1.7)} V {n(y + r * 1.7)}"/>'
        "</g>"
    )


def title_block(
    x: float,
    y: float,
    block: TitleBlock,
    palette: Palette,
    *,
    family: str,
    style: BlockStyle | None = None,
) -> str:
    """The engineering title block: the headline largest with its number beside it,
    then each full-width row, then the cells side by side."""
    s = style or BlockStyle()
    w = block.width
    h = block.height(s)
    fill = palette.ground
    out = [
        f'<rect x="{number(x)}" y="{number(y)}" width="{number(w)}" height="{number(h)}" '
        f'fill="{fill}" stroke="{palette.ink}" stroke-opacity="0.85" stroke-width="1.3"/>',
        text(
            x + s.pad,
            y + s.head_key_drop,
            block.head.key,
            s.key_size,
            palette.soft,
            family=family,
            spacing=s.key_spacing,
        ),
        text(
            x + s.pad,
            y + s.head_height - s.head_rise,
            block.head.value,
            s.head_size,
            palette.ink,
            family=family,
            weight="bold",
        ),
    ]
    if block.number:
        out.append(
            text(
                x + w - s.pad,
                y + s.head_height - s.number_rise,
                block.number,
                s.number_size,
                palette.accent,
                family=family,
                anchor="end",
            )
        )
    top = y + s.head_height
    for row in block.rows:
        out.append(line(x, top, x + w, top, palette.ink, 0.8))
        out.append(
            text(
                x + s.pad,
                top + s.key_drop,
                row.key,
                s.key_size,
                palette.soft,
                family=family,
                spacing=s.key_spacing,
            )
        )
        out.append(
            text(
                x + s.pad,
                top + s.row_height - s.value_rise,
                row.value,
                s.row_size,
                palette.ink,
                family=family,
            )
        )
        top += s.row_height
    out.append(line(x, top, x + w, top, palette.ink, 0.8))
    cx = x
    for index, (cell, width) in enumerate(block.cells):
        if index:
            out.append(line(cx, top, cx, top + s.foot_height, palette.ink, 0.6))
        out.append(
            text(
                cx + s.pad,
                top + s.key_drop,
                cell.key,
                s.key_size,
                palette.soft,
                family=family,
                spacing=s.key_spacing,
            )
        )
        out.append(
            text(
                cx + s.pad,
                top + s.foot_height - s.value_rise,
                cell.value,
                s.cell_size,
                palette.ink,
                family=family,
            )
        )
        cx += width
    return "".join(out)


def zones(length: float) -> int:
    """How many zones an edge `length` long is divided into: at least two."""
    return max(2, round(length / ZONE))


# --- a diagram's sheet -------------------------------------------------------


@dataclass(frozen=True)
class Sheet:
    """Where a diagram's sheet furniture goes, on a canvas `width` by `height`.

    Built by `drawspec.render` once the drawing is framed, and drawn by `emit`
    under the drawing. Every coordinate is final: the drawing has already been
    moved clear of all of it.
    """

    width: float
    height: float
    pattern: bool
    border: bool
    block: TitleBlock | None = None
    block_x: float = 0.0
    block_y: float = 0.0
    style: BlockStyle = BlockStyle()
    zone_size: float = 9.0

    def drawn(self, prefix: str, palette: Palette, family: str, *, bleed: float = 0.0) -> str:
        """The furniture as SVG, under a drawing whose ids start with `prefix`.

        `bleed` is how far the canvas reaches past (0, 0) on every side — the
        emitter widens its viewBox by half the heaviest stroke — so the ground
        covers the whole picture rather than leaving a hairline of page.
        """
        out = [
            grid(
                prefix,
                self.width + 2 * bleed,
                self.height + 2 * bleed,
                palette,
                x=-bleed,
                y=-bleed,
                pattern=self.pattern,
            )
        ]
        if self.border:
            inner = INSET + BAND
            out.append(
                border(
                    self.width,
                    self.height,
                    palette,
                    family=family,
                    across=zones(self.width - 2 * inner),
                    down=zones(self.height - 2 * inner),
                    size=self.zone_size,
                )
            )
            corner = inner + PAD / 2 + 1
            for y in (corner, self.height - corner):
                out.append(registration(corner, y, palette.accent, MARK_RADIUS))
        if self.block is not None:
            block = replace(self.block, number=self.block.number or drawing_number(prefix))
            out.append(
                title_block(
                    self.block_x, self.block_y, block, palette, family=family, style=self.style
                )
            )
        return "".join(out)


def spread(naturals: Sequence[float], total: float) -> tuple[float, ...]:
    """`naturals` grown evenly until they add up to `total` (never shrunk)."""
    extra = max(0.0, total - sum(naturals)) / max(1, len(naturals))
    return tuple(value + extra for value in naturals)


def block_style(key: float, head: float, value: float) -> BlockStyle:
    """A title block's rows sized to its three type sizes.

    Each row holds a small key above its value; the heights are the key's line,
    a gap, and the value's ascent and its clearance above the rule below.
    """
    key_drop = math.ceil(key + 3)
    head_rise = math.ceil(0.25 * head + 4.5)
    rise = math.ceil(0.25 * value + 4.5)
    above = key_drop + 0.25 * key + 2
    return BlockStyle(
        head_height=math.ceil(above + 0.95 * head + head_rise),
        foot_height=math.ceil(above + 0.95 * value + rise),
        key_size=key,
        head_size=head,
        number_size=value,
        row_size=value,
        cell_size=value,
        head_key_drop=key_drop,
        key_drop=key_drop,
        head_rise=head_rise,
        number_rise=head_rise,
        value_rise=rise,
    )


#: What a drawing number looks like before the digest is known, for measuring.
_NUMBER_TEMPLATE: Final = "DWG 0000"


def drawing_number(prefix: str) -> str:
    """A drawing number from the document's content digest — the id namespace.

    Derived, not invented: the same drawing always carries the same number, and
    a changed one a different number, which is what a revision is for.
    """
    digits = prefix[2:] if prefix.startswith("ds") else prefix
    return f"DWG {digits[:4].upper()}"


def around(
    scene: Scene, theme: Theme, document: Document, measurer: TextMeasurer
) -> tuple[Scene, Sheet]:
    """`scene`, moved clear of its sheet on a canvas grown to hold it, and the sheet.

    `scene` is the framed drawing — it already has `[canvas] margin` of blank on
    every side. The border and its channel go around that; the title block goes
    in a strip under it, right-aligned to the drawing's edge, with the frame's
    own margin as the gap. A title block wider than a fixed canvas can hold is a
    `FitError`: the canvas is one width for every diagram in a theme, and a long
    title is not a reason for one sheet to be wider than the rest.
    """
    canvas = theme.canvas
    margin = canvas.margin
    border_on = canvas.border != "none"
    side = INSET + BAND + PAD if border_on else 0.0

    block: TitleBlock | None = None
    style = block_style(canvas.min_legible_size, theme.scale.heading, theme.scale.label)
    content = scene.width
    if canvas.title_block:
        drawing = (scene.width - 2 * margin, scene.height - 2 * margin)

        def wide(words: str, size: float, weight: str = "normal", spacing: float = 0) -> float:
            return measurer.advance(words, "mono", size, weight) + spacing * len(words)

        def keyed(field: Field, size: float) -> float:
            return max(
                wide(field.key, style.key_size, spacing=style.key_spacing),
                wide(field.value, size),
            )

        head = Field("TITLE", document.title or document.kind)
        cells = (
            Field("KIND", document.kind),
            Field("SIZE", f"{round(drawing[0])} \u00d7 {round(drawing[1])}"),
            Field("REV", f"v{document.version}"),
        )
        naturals = [keyed(cell, style.cell_size) + 2 * style.pad for cell in cells]
        head_need = (
            wide(head.value, style.head_size, "bold")
            + wide(_NUMBER_TEMPLATE, style.number_size)
            + 3 * style.pad
            + 8
        )
        room = scene.width - 2 * margin
        # The floor is a look, not a need: a narrow drawing gets a narrow block.
        width = max(min(BLOCK_MIN_WIDTH, room), head_need, sum(naturals))
        if width > room + 0.01:
            if canvas.width_mode == "fixed":
                raise FitError(
                    f"the title block needs {width:.0f} units across and the drawing is "
                    f"{room:.0f} wide. The title is set on one line in the block — "
                    f"shorten the document's `title`, or use a theme without "
                    f"`title_block`."
                )
            content = width + 2 * margin
        block = TitleBlock(
            head=head,
            number="",
            rows=(),
            cells=tuple(zip(cells, spread(naturals, width), strict=True)),
        )

    dx = side + (content - scene.width) / 2
    dy = side
    width = content + 2 * side
    height = side + scene.height
    block_x = block_y = 0.0
    if block is not None:
        block_x = side + content - margin - block.width
        block_y = height
        height += block.height(style) + (side if border_on else margin)
    else:
        height += side
    moved_scene = replace(
        scene,
        width=width,
        height=height,
        primitives=tuple(moved(primitive, dx, dy) for primitive in scene.primitives),
    )
    return moved_scene, Sheet(
        width=width,
        height=height,
        pattern=canvas.pattern != "none",
        border=border_on,
        block=block,
        block_x=block_x,
        block_y=block_y,
        style=style,
        zone_size=canvas.min_legible_size,
    )


__all__ = [
    "BAND",
    "BLOCK_MIN_WIDTH",
    "INSET",
    "PAD",
    "BlockStyle",
    "Field",
    "Palette",
    "Sheet",
    "TitleBlock",
    "around",
    "block_style",
    "border",
    "drawing_number",
    "grid",
    "registration",
    "spread",
    "text",
    "title_block",
    "zones",
]
