"""Compose the README's hero image — a drafting sheet drawn by drawspec itself.

Not shipped code. Every drawing on the sheet is a reference document rendered by
drawspec's public `render_file`/`render` in the inline profile, its canvas
cropped to the ink (`[canvas] width_mode = "ink"`), which draws in
`currentColor`; this script only lays those drawings out as plates inked on one
blueprint sheet, large enough to run into one another like layered drawings,
sets each plate's ink with `color=`, and adds the furniture an engineering
drawing has — a grid, a border with zone marks, registration marks, a title
block, and the wordmark.

Two plates are not pictures at all: one small reference document as
`render_text` draws it, in box drawing and again in ASCII, set line by line in
the embedded monospace face, so the sheet shows the third output beside SVG and
PNG. They lie on top of the stack.

The one foreground drawing is rendered from the JSON printed beside it, so the
banner shows exactly what the tool does: that document, and nothing else, made
that picture.

GitHub shows a README's SVG through `<img>`, where no external font or script
loads, so the faces are embedded: the bundled DejaVu files, subset to the
characters the sheet uses, renamed to a private family (`dshero-*`) so a viewer
that ignored the embedded copy would visibly fall back rather than silently
borrow an installed DejaVu, and inlined as base64 `@font-face`. The PNG is drawn
by resvg with the same subset files and the host's fonts switched off, so both
outputs are set in the same glyphs.

Usage, from the repository root:

    uv run python tools/hero.py           # write docs/hero.svg and docs/hero.png
    uv run python tools/hero.py --check   # fail if either file is stale
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

import drawspec
from drawspec import sheet
from drawspec.text.fontlib import bundled_font_path
from drawspec.theme import Theme

ROOT: Final = Path(__file__).resolve().parent.parent
REFERENCE: Final = ROOT / "docs" / "reference"
OUT_SVG: Final = ROOT / "docs" / "hero.svg"
OUT_PNG: Final = ROOT / "docs" / "hero.png"
LOGO: Final = ROOT / "docs" / "logo.svg"

#: The GitHub social-preview width, a little taller so the plates can be drawn
#: large; the README shows it scaled to its column.
WIDTH: Final = 1280
HEIGHT: Final = 700
#: How far the spec and its drawing sit below where a 640-high sheet put them.
DROP: Final = HEIGHT - 640

# The sheet. A deep cyanotype ground, white line work, and one warm drafting
# accent for the dimension lines and marks — never a gradient.
GROUND: Final = "#0b2d52"
GRID: Final = "#9fd0ff"
PLATE_INK: Final = "#a9d4ff"
INK: Final = "#f2f8ff"
SOFT: Final = "#8fbbe6"
ACCENT: Final = "#ffb547"

#: Sheet border inset, and the zone count along each edge.
INSET: Final = 18
ZONES_ACROSS: Final = 8
ZONES_DOWN: Final = 4

#: The approved logo's drawing, without its `<svg>` wrapper, nested into the sheet.
_LOGO_SVG: Final = LOGO.read_text(encoding="utf-8").strip()
LOGO_INNER: Final = _LOGO_SVG[_LOGO_SVG.index(">") + 1 : _LOGO_SVG.rindex("</svg>")]

FAMILIES: Final = {"sans": "dshero-sans", "mono": "dshero-mono", "serif": "dshero-serif"}


@dataclass(frozen=True)
class Plate:
    """One reference drawing, `width` units wide with its top-left at (`x`, `y`).

    Plates are drawn straight onto the blueprint, back to front, and are free to
    run into one another; `opacity` sets each one's place in that depth. A plate
    with a `charset` is the document as `render_text` draws it, set line by line
    in the mono face; any other is the SVG drawing, narrowed to `view` (a left
    and a width in its own units) when its canvas is wider than its ink, and
    stripped of its words when `words` is off — a plate lying behind the wordmark
    is silhouette only. Its caption goes below its left edge, unless `label`
    places it: the caption's (left, baseline) where the drawings around it leave
    it room.
    """

    source: str
    number: int
    figure: str
    x: float
    y: float
    width: float
    opacity: float = 1.0
    charset: str | None = None
    label: tuple[float, float] | None = None
    words: bool = True
    view: tuple[float, float] | None = None


#: The plates, back to front, inked on the one sheet and overlapping like layered
#: drawings: the furthest dimmest, and the two text plates, the newest output, on
#: top and brightest.
PLATES: Final = (
    # Silhouettes behind the wordmark, large enough to show above and below it.
    Plate("venn-parity", 1, "venn", 150, 36, 296, opacity=0.26, words=False, label=(44, 330)),
    Plate(
        "pie-team-week",
        2,
        "pie",
        430,
        40,
        300,
        opacity=0.26,
        words=False,
        view=(150, 366),
        label=(612, 330),
    ),
    Plate("funnel-applications", 3, "funnel", 812, 38, 330, opacity=0.62, label=(1138, 70)),
    Plate("mindmap-offsite", 4, "mindmap", 772, 178, 466, opacity=0.86, label=(1124, 374)),
    Plate("sequence-terminal", 5, "--format text", 868, 412, 176, charset="unicode"),
    Plate("sequence-terminal", 6, "--charset ascii", 1060, 426, 176, charset="ascii"),
)

#: DejaVu Sans Mono's advance, and the height its box-drawing verticals span, in
#: ems: a line set that far below the last makes `│` on one meet `│` on the next.
MONO_ADVANCE: Final = 1233 / 2048
MONO_LEAD: Final = 2433 / 2048

#: What drawspec draws, by family rather than by count, so no release dates it.
GROUPS: Final = (
    "Flows & processes",
    "Structures & hierarchies",
    "Timelines & plans",
    "Charts & comparisons",
    "Data & relations",
)

#: The document the foreground drawing is made from, printed on the sheet as-is.
SPEC: Final[dict[str, Any]] = {
    "version": 1,
    "kind": "flow",
    "nodes": [
        {"id": "write", "text": "Write what it means", "role": "start"},
        {"id": "fits", "text": "Does it fit?", "role": "decision"},
        {"id": "draw", "text": "Draw it, exactly"},
        {"id": "say", "text": "Say why, plainly", "role": "terminal"},
    ],
    "edges": [
        {"from": "write", "to": "fits"},
        {"from": "fits", "to": "draw", "label": "yes"},
        {"from": "fits", "to": "say", "label": "no"},
    ],
}


def cropped() -> Theme:
    """The default theme with its canvas cropped to the ink, so a plate is its drawing."""
    theme = drawspec.load_theme()
    return replace(theme, canvas=replace(theme.canvas, width_mode="ink"))


_ID = re.compile(r'\bid="([^"]+)"')
_VIEWBOX = re.compile(r'viewBox="([-\d. ]+)"')


def _inner(svg: str, prefix: str) -> tuple[str, tuple[float, float, float, float]]:
    """The drawing's content without its `<svg>` wrapper, `<title>` or `<desc>`.

    Every id is re-prefixed (and every reference to it), so two plates of the
    same document, or two documents that happened to hash alike, cannot collide.
    """
    match = _VIEWBOX.search(svg)
    if match is None:
        raise ValueError("drawing has no viewBox")
    x, y, w, h = (float(part) for part in match.group(1).split())
    body = svg[svg.index(">") + 1 : svg.rindex("</svg>")]
    body = re.sub(r"<title[^>]*>.*?</title>|<desc[^>]*>.*?</desc>", "", body, flags=re.S)
    for old in set(_ID.findall(body)):
        new = f"{prefix}-{old}"
        body = body.replace(f'id="{old}"', f'id="{new}"').replace(f"#{old})", f"#{new})")
        body = body.replace(f'href="#{old}"', f'href="#{new}"')
    return body, (x, y, w, h)


def _faces(svg: str) -> str:
    """Point every font-family at the embedded private families."""
    svg = re.sub(
        r"font-family=\"'DejaVu Sans Mono'[^\"]*\"", f'font-family="{FAMILIES["mono"]}"', svg
    )
    svg = re.sub(r"font-family=\"'DejaVu Serif'[^\"]*\"", f'font-family="{FAMILIES["serif"]}"', svg)
    svg = re.sub(r"font-family=\"'DejaVu Sans'[^\"]*\"", f'font-family="{FAMILIES["sans"]}"', svg)
    return svg


def place(
    svg: str,
    prefix: str,
    x: float,
    y: float,
    width: float,
    ink: str,
    view: tuple[float, float] | None = None,
) -> tuple[str, float]:
    """`svg` scaled to `width` with its top-left at (x, y), inked `ink`; and its height.

    `view`, a (left, width) in the drawing's units, narrows it to that band.
    """
    body, (vx, vy, vw, vh) = _inner(svg, prefix)
    if view is not None:
        vx, vw = view
    scale = width / vw
    group = (
        f'<g color="{ink}" transform="translate({x - vx * scale:.2f} {y - vy * scale:.2f}) '
        f'scale({scale:.4f})">{_faces(body)}</g>'
    )
    return group, vh * scale


# --- text metrics, from the very files that get embedded ---------------------


class Metrics:
    """Advance widths for the bundled faces, so the furniture can be sized to its words."""

    def __init__(self) -> None:
        self._fonts: dict[tuple[str, str], TTFont] = {}

    def width(self, text: str, size: float, role: str = "sans", weight: str = "normal") -> float:
        key = (role, weight)
        if key not in self._fonts:
            self._fonts[key] = TTFont(bundled_font_path(role, weight))
        font = self._fonts[key]
        cmap = font.getBestCmap()
        hmtx = font["hmtx"]
        upm = float(font["head"].unitsPerEm)
        total = 0.0
        for char in text:
            total += float(hmtx[cmap.get(ord(char), ".notdef")][0])
        return total * size / upm


METRICS: Final = Metrics()


PALETTE: Final = sheet.Palette(ground=GROUND, ink=INK, soft=SOFT, grid=GRID, accent=ACCENT)

#: The banner's title block is set larger and looser than a diagram's.
BLOCK_STYLE: Final = sheet.BlockStyle(
    head_height=34,
    row_height=26,
    foot_height=26,
    key_size=6.5,
    head_size=19,
    number_size=9,
    row_size=10.5,
    cell_size=9.5,
    head_key_drop=11,
    key_drop=10,
    head_rise=7,
    number_rise=8,
    value_rise=6,
)


def text(
    x: float,
    y: float,
    content: str,
    size: float,
    fill: str,
    *,
    role: str = "sans",
    weight: str = "normal",
    anchor: str = "start",
    spacing: float = 0,
    opacity: float = 1,
) -> str:
    return sheet.text(
        x,
        y,
        content,
        size,
        fill,
        family=FAMILIES[role],
        weight=weight,
        anchor=anchor,
        spacing=spacing,
        opacity=opacity,
    )


# --- the sheet's furniture: drawspec's own, from `drawspec.sheet` -------------


def grid() -> str:
    """A fine 16-unit grid with a heavier line every fifth, on the ground."""
    return sheet.grid("hero", WIDTH, HEIGHT, PALETTE)


def border() -> str:
    """A double border with zone numbers across and zone letters down, as a sheet has."""
    return sheet.border(
        WIDTH,
        HEIGHT,
        PALETTE,
        family=FAMILIES["mono"],
        inset=INSET,
        band=12,
        across=ZONES_ACROSS,
        down=ZONES_DOWN,
        size=8,
    )


def registration(x: float, y: float, r: float = 7) -> str:
    """A registration mark: a ring with crosshairs that overrun it."""
    return sheet.registration(x, y, ACCENT, r)


def crop(x: float, y: float, w: float, h: float, arm: float = 9, stroke: str = INK) -> str:
    """Corner brackets around a plate, the way a figure is marked on a sheet."""
    d = (
        f"M {x} {y + arm} V {y} H {x + arm} "
        f"M {x + w - arm} {y} H {x + w} V {y + arm} "
        f"M {x + w} {y + h - arm} V {y + h} H {x + w - arm} "
        f"M {x + arm} {y + h} H {x} V {y + h - arm}"
    )
    return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="1" stroke-opacity="0.6"/>'


def dimension(x1: float, x2: float, y: float, label: str) -> str:
    """A horizontal dimension line with extension ticks and its label set in a break."""
    size = 10
    gap = METRICS.width(label, size, "mono") + 14
    mid = (x1 + x2) / 2
    arrow = 6
    return (
        f'<g stroke="{ACCENT}" stroke-width="0.9" fill="none">'
        f'<path d="M {x1} {y - 9} V {y + 5} M {x2} {y - 9} V {y + 5}"/>'
        f'<path d="M {x1} {y} H {mid - gap / 2} M {mid + gap / 2} {y} H {x2}"/>'
        "</g>"
        f'<path d="M {x1} {y} l {arrow} -2.2 v 4.4 Z M {x2} {y} l -{arrow} -2.2 v 4.4 Z" '
        f'fill="{ACCENT}"/>' + text(mid, y + 3.5, label, size, ACCENT, role="mono", anchor="middle")
    )


def title_block(x: float, y: float, w: float) -> str:
    """The engineering title block: the project's name largest, then the title, then
    scale and output side by side. Nothing in it is a version or a count, so the
    banner never needs redrawing for a release."""
    block = sheet.TitleBlock(
        head=sheet.Field("PROJECT", "drawspec"),
        number="DWG 001",
        rows=(sheet.Field("TITLE", "For all your diagram needs"),),
        cells=(
            (sheet.Field("SCALE", "no coordinates"), w * 0.52),
            (sheet.Field("OUTPUT", "SVG · PNG · TEXT"), w * 0.48),
        ),
    )
    return sheet.title_block(x, y, block, PALETTE, family=FAMILIES["mono"], style=BLOCK_STYLE)


def kinds_line(x: float, y: float, size: float) -> str:
    """The kind groups in one line, set apart by accent dots."""
    dot = f'<tspan fill="{ACCENT}">  ·  </tspan>'
    words = dot.join(f'<tspan fill="{INK}">{escape(group)}</tspan>' for group in GROUPS)
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FAMILIES["sans"]}" '
        f'font-size="{size:g}" fill-opacity="0.82" xml:space="preserve">{words}</text>'
    )


# --- the JSON snippet --------------------------------------------------------


def snippet_lines(spec: Mapping[str, Any]) -> list[str]:
    """`spec` as JSON, one key per line and one list entry per line."""
    out = ["{"]
    items = list(spec.items())
    for index, (key, value) in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        if isinstance(value, list):
            out.append(f"  {json.dumps(key)}: [")
            for j, entry in enumerate(value):
                tail = "," if j < len(value) - 1 else ""
                out.append(f"    {json.dumps(entry, ensure_ascii=False)}{tail}")
            out.append(f"  ]{comma}")
        else:
            out.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}{comma}")
    out.append("}")
    return out


_TOKEN = re.compile(r'("(?:[^"\\]|\\.)*")(\s*:)?|([{}\[\],:])|(\s+)|([^\s"{}\[\],:]+)')


def highlighted(source: str, x: float, y: float, size: float) -> str:
    """One line of JSON as a `<text>` with keys, strings and punctuation tinted apart."""
    spans = []
    for match in _TOKEN.finditer(source):
        string, colon, punct, space, other = match.groups()
        if string is not None:
            fill = SOFT if colon else INK
            spans.append(f'<tspan fill="{fill}">{escape(string)}</tspan>')
            if colon:
                spans.append(f'<tspan fill="{SOFT}" fill-opacity="0.7">{escape(colon)}</tspan>')
        elif punct is not None:
            spans.append(f'<tspan fill="{SOFT}" fill-opacity="0.7">{escape(punct)}</tspan>')
        elif space is not None:
            spans.append(escape(space))
        elif other is not None:
            spans.append(f'<tspan fill="{ACCENT}">{escape(other)}</tspan>')
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FAMILIES["mono"]}" '
        f'font-size="{size:g}" xml:space="preserve">{"".join(spans)}</text>'
    )


# --- composition -------------------------------------------------------------

#: claude-arsenal's own logo, for the "built with" stamp on the frame.
ARSENAL_LOGO: Final = ROOT / "docs" / "claude-arsenal-logo.svg"
#: claude-arsenal's orange (#c4623f), lifted a step so it reads on the dark ground.
ARSENAL: Final = "#e07a45"


def powered_by() -> str:
    """A "built with" badge for claude-arsenal, set on the frame's bottom edge at the right."""
    src = ARSENAL_LOGO.read_text(encoding="utf-8").strip()
    inner = src[src.index(">") + 1 : src.rindex("</svg>")]
    lead, name, url = "built with", "claude-arsenal", "github.com/nuncaeslupus/claude-arsenal"
    tile, pad, gap = 22, 8, 8
    lead_w = METRICS.width(lead, 12, "sans")
    name_w = METRICS.width(name, 15, "sans", "bold")
    url_w = METRICS.width(url, 10, "mono")
    width = pad + tile + gap + lead_w + 6 + name_w + 12 + url_w + pad + 6
    edge = INSET + 12
    right, cy = WIDTH - edge - 24, HEIGHT - edge
    x = right - width
    tx = x + pad + tile + gap
    return (
        f'<rect x="{x:.1f}" y="{cy - 16}" width="{width:.1f}" height="32" rx="16" '
        f'fill="{GROUND}" stroke="{ARSENAL}" stroke-width="1.5"/>'
        f'<svg x="{x + pad:.1f}" y="{cy - tile / 2}" width="{tile}" height="{tile}" '
        f'viewBox="0 0 64 64">{inner}</svg>'
        + text(tx, cy + 4.3, lead, 12, SOFT)
        + text(tx + lead_w + 6, cy + 5.3, name, 15, ARSENAL, weight="bold")
        + text(tx + lead_w + 6 + name_w + 12, cy + 3.6, url, 10, SOFT, role="mono")
    )


def typed(plate: Plate) -> tuple[str, float]:
    """A text plate: the document's `render_text` lines in the mono face, each run
    of characters knocked out of whatever is drawn behind it; and its height."""
    document = drawspec.load_document(REFERENCE / f"{plate.source}.json")
    drawn = drawspec.render_text(document, charset=plate.charset or "unicode")
    lines = drawn.rstrip("\n").split("\n")
    columns = max(len(line) for line in lines)
    size = plate.width / (columns * MONO_ADVANCE)
    advance = size * MONO_ADVANCE
    lead = size * MONO_LEAD
    knockouts, rows = [], []
    for i, line in enumerate(lines):
        top = plate.y + i * lead
        # A run is characters with at most one space between them: a word, a label,
        # a box's edge. The ground behind it is cleared, and only behind it.
        for run in re.finditer(r"\S+(?: \S+)*", line):
            knockouts.append(
                f'<rect x="{plate.x + run.start() * advance - 1.5:.2f}" y="{top - 0.5:.2f}" '
                f'width="{(run.end() - run.start()) * advance + 3:.2f}" '
                f'height="{lead + 1:.2f}" fill="{GROUND}"/>'
            )
        rows.append(
            f'<text x="{plate.x:.2f}" y="{top + size * 0.93:.2f}" '
            f'font-family="{FAMILIES["mono"]}" font-size="{size:.3f}" fill="{INK}" '
            f'xml:space="preserve">{escape(line)}</text>'
        )
    return "".join(knockouts) + "".join(rows), lead * len(lines)


#: The halo round a plate's words, in sheet units: wide enough that a line of the
#: plate behind runs up to a label and stops, rather than through it.
HALO: Final = 3.0


def halo(svg: str, plate: Plate) -> str:
    """`svg` with a stroke of ground painted under each of its words."""
    match = _VIEWBOX.search(svg)
    if match is None:
        raise ValueError("drawing has no viewBox")
    span = plate.view[1] if plate.view else float(match.group(1).split()[2])
    width = HALO * span / plate.width
    return svg.replace(
        "<text ",
        f'<text stroke="{GROUND}" stroke-width="{width:.2f}" stroke-linejoin="round" '
        'paint-order="stroke" ',
    )


def plate(plate: Plate) -> str:
    """`plate` inked on the sheet, with its figure caption cleared out of what lies behind."""
    if plate.charset is not None:
        drawing, height = typed(plate)
    else:
        # The figure label is the plate's caption, so the document's own is left off.
        document = json.loads((REFERENCE / f"{plate.source}.json").read_text(encoding="utf-8"))
        document.pop("caption", None)
        svg = drawspec.render(document, cropped())
        # A silhouette plate behind the wordmark loses its words; any other keeps
        # them, haloed so the lines of the plate behind stop short of them.
        silhouette = re.sub(r"<text\b.*?</text>", "", svg, flags=re.S)
        svg = halo(svg, plate) if plate.words else silhouette
        drawing, height = place(
            svg, f"p{plate.number}", plate.x, plate.y, plate.width, PLATE_INK, plate.view
        )
        drawing = f'<g opacity="{plate.opacity:g}">{drawing}</g>'
    size = 7.5
    label = f"FIG. {plate.number:02d} · {plate.figure}"
    width = METRICS.width(label, size, "mono") + 1.2 * len(label)
    at, base = plate.label or (plate.x, plate.y + height + 16)
    return (
        drawing + f'<rect x="{at - 3:.2f}" y="{base - 8.5:.2f}" width="{width + 6:.2f}" '
        f'height="11" fill="{GROUND}"/>'
        + text(at, base, label, size, SOFT, role="mono", spacing=1.2)
    )


def compose() -> str:
    parts: list[str] = [grid()]

    # The plates back to front, all inside the border.
    inner = INSET + 12
    parts.append(
        f'<clipPath id="hero-sheet"><rect x="{inner}" y="{inner}" '
        f'width="{WIDTH - 2 * inner}" height="{HEIGHT - 2 * inner}"/></clipPath>'
        '<g clip-path="url(#hero-sheet)">'
    )
    parts.extend(plate(item) for item in PLATES)
    parts.append("</g>")

    parts.append(border())

    # The wordmark, with a dimension line over it that measures nothing.
    # One rule in every hero: the logo tile is 0.95 x the wordmark's font size, centred on
    # its capital band (baseline to cap height), with a quarter-em gap before it.
    guide_x, mark_y, mark_size = 70, 196, 100
    tile, tile_gap = round(0.95 * mark_size), round(0.25 * mark_size)
    mark_x = guide_x + tile + tile_gap
    mark_w = METRICS.width("drawspec", mark_size, "sans", "bold") + 7 * -3
    parts.append(dimension(mark_x, mark_x + mark_w, 88, "x = ?   y = ?"))
    # Construction lines: the wordmark's baseline, x-height and ascender, run on.
    for name, height in (("ASC", 0.76), ("X-HT", 0.547), ("BASE", 0.0)):
        y = mark_y - height * mark_size
        parts.append(
            f'<path d="M {guide_x - 10} {y:.1f} H {mark_x + mark_w + 24}" stroke="{GRID}" '
            'stroke-width="0.7" stroke-opacity="0.32" stroke-dasharray="3 3"/>'
        )
        parts.append(
            text(guide_x - 14, y + 2.3, name, 6.5, SOFT, role="mono", anchor="end", spacing=0.5)
        )
    # The logo, centred on the wordmark's capital band.
    band_mid = mark_y - 0.727 * mark_size / 2
    tile_y = band_mid - tile / 2
    parts.append(
        f'<svg x="{guide_x}" y="{tile_y:.1f}" width="{tile}" height="{tile}" '
        f'viewBox="0 0 64 64">{LOGO_INNER}</svg>'
        f'<rect x="{guide_x}" y="{tile_y:.1f}" width="{tile}" height="{tile}" '
        f'rx="{tile * 14 / 64:.2f}" fill="none" stroke="{INK}" stroke-opacity="0.45"/>'
    )
    parts.append(text(mark_x - 4, mark_y, "drawspec", mark_size, INK, weight="bold", spacing=-3))
    parts.append(
        text(
            guide_x,
            mark_y + 50,
            "Diagrams from meaning, written by humans or LLM agents.",
            21,
            SOFT,
        )
    )

    parts.append(kinds_line(guide_x, mark_y + 76, 12.5))

    # The JSON on the left, and the drawing it makes in front of the plates.
    lines = snippet_lines(SPEC)
    code_x, code_y, code_size, lead = 70, 326 + DROP, 10.5, 15.5
    code_w = max(METRICS.width(item, code_size, "mono") for item in lines) + 28
    code_h = lead * len(lines) + 22
    parts.append(
        f'<rect x="{code_x - 14}" y="{code_y - 16}" width="{code_w}" height="{code_h}" '
        f'fill="{GROUND}" fill-opacity="0.92" stroke="{INK}" stroke-opacity="0.35"/>'
    )
    parts.append(
        text(code_x - 14, code_y - 22, "SPEC · flow.json", 7.5, ACCENT, role="mono", spacing=1.2)
    )
    for i, item in enumerate(lines):
        parts.append(highlighted(item, code_x, code_y + i * lead, code_size))

    drawn = drawspec.render(SPEC, cropped())
    draw_x, draw_y, draw_w = 580, 318 + DROP, 262
    group, draw_h = place(drawn, "hero", draw_x, draw_y, draw_w, INK)
    pad = 14
    parts.append(
        f'<rect x="{draw_x - pad}" y="{draw_y - pad}" width="{draw_w + 2 * pad}" '
        f'height="{draw_h + 2 * pad}" fill="{GROUND}" fill-opacity="0.94"/>'
    )
    parts.append(crop(draw_x - pad, draw_y - pad, draw_w + 2 * pad, draw_h + 2 * pad, 12))
    parts.append(group)

    # The leader from the spec to its drawing.
    lx1 = code_x - 14 + code_w
    ly = code_y + code_h / 2 - 16
    lx2 = draw_x - pad
    parts.append(
        f'<g stroke="{ACCENT}" stroke-width="1.1" fill="none">'
        f'<path d="M {lx1 + 4} {ly} H {lx2 - 8}" stroke-dasharray="6 4"/></g>'
        f'<circle cx="{lx1 + 4}" cy="{ly}" r="2.4" fill="{ACCENT}"/>'
        f'<path d="M {lx2} {ly} l -9 -3.6 v 7.2 Z" fill="{ACCENT}"/>'
        + text((lx1 + lx2) / 2, ly - 8, "render", 9, ACCENT, role="mono", anchor="middle")
    )

    for x, y in ((50, 52), (50, HEIGHT - 52)):
        parts.append(registration(x, y))

    parts.append(title_block(WIDTH - 44 - 300, HEIGHT - 52 - 86, 300))
    parts.append(powered_by())

    body = "".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" role="img" aria-labelledby="hero-title">'
        '<title id="hero-title">drawspec — diagrams from meaning, not coordinates</title>'
        f"<style>{embedded_fonts(body)}</style>{body}</svg>"
    )


# --- fonts -------------------------------------------------------------------


def _used(svg: str) -> dict[tuple[str, str], set[str]]:
    """Characters the sheet sets, per (role, weight) — generously: every face gets all."""
    chars = set()
    for content in re.findall(r">([^<>]+)<", svg):
        chars.update(content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
    chars.update(" ?")
    faces: dict[tuple[str, str], set[str]] = {}
    for role, family in FAMILIES.items():
        if family not in svg:
            continue
        for weight in ("normal", "bold"):
            faces[(role, weight)] = chars
    return faces


def subset_font(role: str, weight: str, chars: Iterable[str]) -> bytes:
    """The bundled face cut down to `chars`, renamed to its private family."""
    # No timestamp: the bytes must not change between two runs on the same input.
    font = TTFont(bundled_font_path(role, weight), recalcTimestamp=False)
    options = subset.Options()
    options.name_IDs = ["*"]
    options.layout_features = ["kern", "liga"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(font)
    family = FAMILIES[role]
    style = "Bold" if weight == "bold" else "Regular"
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = family
        elif record.nameID in (2, 17):
            record.string = style
        elif record.nameID == 4:
            record.string = f"{family} {style}"
        elif record.nameID == 6:
            record.string = f"{family}-{style}"
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


_SUBSETS: dict[tuple[str, str], bytes] = {}


def embedded_fonts(svg: str) -> str:
    rules = []
    _SUBSETS.clear()
    for (role, weight), chars in sorted(_used(svg).items()):
        data = subset_font(role, weight, chars)
        _SUBSETS[(role, weight)] = data
        encoded = base64.b64encode(data).decode("ascii")
        rules.append(
            f"@font-face{{font-family:{FAMILIES[role]};font-weight:{weight};"
            f"src:url(data:font/ttf;base64,{encoded}) format('truetype')}}"
        )
    return "".join(rules)


def rasterise(svg: str, scale: float = 1.0) -> bytes:
    from resvg_py import svg_to_bytes

    rasterise_fn: Callable[..., bytes] = svg_to_bytes
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for (role, weight), data in _SUBSETS.items():
            path = Path(tmp) / f"{role}-{weight}.ttf"
            path.write_bytes(data)
            files.append(str(path))
        return rasterise_fn(
            svg_string=svg,
            zoom=scale,
            skip_system_fonts=True,
            font_files=files,
            font_family=FAMILIES["sans"],
            sans_serif_family=FAMILIES["sans"],
            monospace_family=FAMILIES["mono"],
            serif_family=FAMILIES["serif"],
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="fail if the outputs are stale")
    args = parser.parse_args(argv)
    svg = compose()
    png = rasterise(svg)
    if args.check:
        stale = [
            path.name
            for path, data in ((OUT_SVG, svg.encode()), (OUT_PNG, png))
            if not path.exists() or path.read_bytes() != data
        ]
        if stale:
            print(f"stale: {', '.join(stale)} — run `make hero`", file=sys.stderr)
            return 1
        return 0
    OUT_SVG.write_text(svg, encoding="utf-8")
    OUT_PNG.write_bytes(png)
    print(f"wrote {OUT_SVG.relative_to(ROOT)} ({len(svg) // 1024} KiB)")
    print(f"wrote {OUT_PNG.relative_to(ROOT)} ({len(png) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
