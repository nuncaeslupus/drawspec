"""Compose the README's hero image — a drafting sheet drawn by drawspec itself.

Not shipped code. Every drawing on the sheet is a reference document rendered by
drawspec's public `render_file`/`render` in the inline profile, its canvas
cropped to the ink (`[canvas] width_mode = "ink"`), which draws in
`currentColor`; this script only lays those drawings out as plates on a blueprint
sheet, sets each plate's ink with `color=`, and adds the furniture an engineering
drawing has — a grid, a border with zone marks, registration marks, a title block,
and the wordmark.

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
from drawspec.text.fontlib import bundled_font_path
from drawspec.theme import Theme

ROOT: Final = Path(__file__).resolve().parent.parent
REFERENCE: Final = ROOT / "docs" / "reference"
OUT_SVG: Final = ROOT / "docs" / "hero.svg"
OUT_PNG: Final = ROOT / "docs" / "hero.png"

#: The GitHub social-preview size, which the README shows scaled to its column.
WIDTH: Final = 1280
HEIGHT: Final = 640

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

FAMILIES: Final = {"sans": "dshero-sans", "mono": "dshero-mono", "serif": "dshero-serif"}


@dataclass(frozen=True)
class Plate:
    """One reference drawing placed on the sheet, `width` units wide at (`x`, `y`)."""

    source: str
    x: float
    y: float
    width: float
    opacity: float
    figure: str


#: The background plates: varied kinds, at varied scale, faint enough to be ground.
PLATES: Final = (
    # A ghost at twice the scale, run off the sheet: there is more drawing than fits.
    Plate("venn-parity", 640, 110, 760, 0.08, ""),
    Plate("sankey-energy", 730, 56, 300, 0.34, "sankey"),
    Plate("sequence-dns", 1062, 56, 168, 0.36, "sequence"),
    Plate("venn-parity", 1088, 160, 130, 0.36, "venn"),
    Plate("states-breaker", 942, 300, 130, 0.36, "states"),
    Plate("journey-first-week", 1095, 330, 135, 0.36, "journey"),
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


def place(svg: str, prefix: str, x: float, y: float, width: float, ink: str) -> tuple[str, float]:
    """`svg` scaled to `width` with its top-left at (x, y), inked `ink`; and its height."""
    body, (vx, vy, vw, vh) = _inner(svg, prefix)
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
    attrs = [
        f'x="{x:.2f}"',
        f'y="{y:.2f}"',
        f'font-family="{FAMILIES[role]}"',
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
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{stroke}" stroke-width="{width:g}"/>'
    )


# --- the sheet's furniture ---------------------------------------------------


def grid() -> str:
    """A fine 16-unit grid with a heavier line every fifth, inside the border."""
    minor, major = 16, 80
    return (
        "<defs>"
        f'<pattern id="hero-grid-minor" width="{minor}" height="{minor}" '
        'patternUnits="userSpaceOnUse">'
        f'<path d="M {minor} 0 L 0 0 0 {minor}" fill="none" stroke="{GRID}" '
        'stroke-width="0.5" stroke-opacity="0.09"/></pattern>'
        f'<pattern id="hero-grid-major" width="{major}" height="{major}" '
        'patternUnits="userSpaceOnUse">'
        f'<path d="M {major} 0 L 0 0 0 {major}" fill="none" stroke="{GRID}" '
        'stroke-width="0.8" stroke-opacity="0.16"/></pattern>'
        "</defs>"
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{GROUND}"/>'
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#hero-grid-minor)"/>'
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#hero-grid-major)"/>'
    )


def border() -> str:
    """A double border with zone numbers across and zone letters down, as a sheet has."""
    out = []
    outer, inner = INSET, INSET + 12
    out.append(
        f'<rect x="{outer}" y="{outer}" width="{WIDTH - 2 * outer}" '
        f'height="{HEIGHT - 2 * outer}" fill="none" stroke="{INK}" '
        'stroke-opacity="0.55" stroke-width="1"/>'
    )
    out.append(
        f'<rect x="{inner}" y="{inner}" width="{WIDTH - 2 * inner}" '
        f'height="{HEIGHT - 2 * inner}" fill="none" stroke="{INK}" '
        'stroke-opacity="0.8" stroke-width="1.6"/>'
    )
    span_x = (WIDTH - 2 * inner) / ZONES_ACROSS
    for i in range(ZONES_ACROSS + 1):
        x = inner + i * span_x
        if 0 < i < ZONES_ACROSS:
            out.append(line(x, outer, x, inner, INK, 0.8))
            out.append(line(x, HEIGHT - inner, x, HEIGHT - outer, INK, 0.8))
        if i < ZONES_ACROSS:
            label = str(ZONES_ACROSS - i)
            mid = x + span_x / 2
            for row in (outer + 9, HEIGHT - outer - 3):
                out.append(text(mid, row, label, 8, SOFT, role="mono", anchor="middle"))
    span_y = (HEIGHT - 2 * inner) / ZONES_DOWN
    for i in range(ZONES_DOWN + 1):
        y = inner + i * span_y
        if 0 < i < ZONES_DOWN:
            out.append(line(outer, y, inner, y, INK, 0.8))
            out.append(line(WIDTH - inner, y, WIDTH - outer, y, INK, 0.8))
        if i < ZONES_DOWN:
            label = "ABCD"[i]
            mid = y + span_y / 2 + 3
            for x in (outer + 6, WIDTH - outer - 6):
                out.append(text(x, mid, label, 8, SOFT, role="mono", anchor="middle"))
    # Centring arrows at the middle of each edge, as a drafting sheet carries.
    cx, cy = WIDTH / 2, HEIGHT / 2
    out.append(
        f'<path d="M {cx - 5} {inner} L {cx} {inner + 8} L {cx + 5} {inner} Z '
        f"M {cx - 5} {HEIGHT - inner} L {cx} {HEIGHT - inner - 8} L {cx + 5} {HEIGHT - inner} Z "
        f"M {inner} {cy - 5} L {inner + 8} {cy} L {inner} {cy + 5} Z "
        f'M {WIDTH - inner} {cy - 5} L {WIDTH - inner - 8} {cy} L {WIDTH - inner} {cy + 5} Z" '
        f'fill="{INK}" fill-opacity="0.8"/>'
    )
    return "".join(out)


def registration(x: float, y: float, r: float = 7) -> str:
    """A registration mark: a ring with crosshairs that overrun it."""
    return (
        f'<g stroke="{ACCENT}" stroke-width="0.9" fill="none" stroke-opacity="0.9">'
        f'<circle cx="{x}" cy="{y}" r="{r}"/>'
        f'<path d="M {x - r * 1.7} {y} H {x + r * 1.7} M {x} {y - r * 1.7} V {y + r * 1.7}"/>'
        "</g>"
    )


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
    scale, sheet and revision side by side."""
    head, mid, foot = 38.0, 30.0, 30.0
    h = head + mid + foot
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{GROUND}" '
        f'stroke="{INK}" stroke-opacity="0.85" stroke-width="1.3"/>',
        line(x, y + head, x + w, y + head, INK, 0.8),
        line(x, y + head + mid, x + w, y + head + mid, INK, 0.8),
        text(x + 9, y + 11, "PROJECT", 6.5, SOFT, role="mono", spacing=1),
        text(x + 9, y + head - 7, "drawspec", 19, INK, role="mono", weight="bold"),
        text(x + w - 9, y + head - 8, "DWG 001", 9, ACCENT, role="mono", anchor="end"),
        text(x + 9, y + head + 10, "TITLE", 6.5, SOFT, role="mono", spacing=1),
        text(x + 9, y + head + mid - 6, "Diagrams from meaning", 10.5, INK, role="mono"),
    ]
    cells = (
        ("SCALE", "no coordinates", 0.44),
        ("SHEET", "1 of 26 kinds", 0.33),
        ("REV", f"v{drawspec.__version__}", 0.23),
    )
    cx = x
    top = y + head + mid
    for index, (key, value, share) in enumerate(cells):
        if index:
            out.append(line(cx, top, cx, top + foot, INK, 0.6))
        out.append(text(cx + 9, top + 10, key, 6.5, SOFT, role="mono", spacing=1))
        out.append(text(cx + 9, top + foot - 6, value, 9.5, INK, role="mono"))
        cx += w * share
    return "".join(out)


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


def compose() -> str:
    parts: list[str] = [grid()]

    # Background plates, each with its corner brackets and a figure caption.
    inner = INSET + 12
    parts.append(
        f'<clipPath id="hero-sheet"><rect x="{inner}" y="{inner}" '
        f'width="{WIDTH - 2 * inner}" height="{HEIGHT - 2 * inner}"/></clipPath>'
        '<g clip-path="url(#hero-sheet)">'
    )
    for number, plate in enumerate(PLATES):
        svg = drawspec.render_file(REFERENCE / f"{plate.source}.json", cropped())
        group, height = place(svg, f"p{number}", plate.x, plate.y, plate.width, PLATE_INK)
        if not plate.figure:
            # A ghost is construction geometry only: its words would be noise.
            group = re.sub(r"<text\b.*?</text>", "", group, flags=re.S)
        parts.append(f'<g opacity="{plate.opacity:g}">{group}</g>')
        if not plate.figure:
            continue
        pad = 6
        parts.append(
            f'<g opacity="{min(1.0, plate.opacity * 2.2):.2f}">'
            + crop(plate.x - pad, plate.y - pad, plate.width + 2 * pad, height + 2 * pad)
            + text(
                plate.x - pad,
                plate.y + height + pad + 11,
                f"FIG. {number:02d} · {plate.figure}",
                7.5,
                SOFT,
                role="mono",
                spacing=1.2,
            )
            + "</g>"
        )
    parts.append("</g>")

    parts.append(border())

    # The wordmark, with a dimension line over it that measures nothing.
    mark_x, mark_y, mark_size = 70, 196, 118
    mark_w = METRICS.width("drawspec", mark_size, "sans", "bold") + 7 * -3
    parts.append(dimension(mark_x, mark_x + mark_w, 88, "x = ?   y = ?"))
    # Construction lines: the wordmark's baseline, x-height and ascender, run on.
    for name, height in (("ASC", 0.76), ("X-HT", 0.547), ("BASE", 0.0)):
        y = mark_y - height * mark_size
        parts.append(
            f'<path d="M {mark_x - 10} {y:.1f} H {mark_x + mark_w + 24}" stroke="{GRID}" '
            'stroke-width="0.7" stroke-opacity="0.32" stroke-dasharray="3 3"/>'
        )
        parts.append(
            text(mark_x - 14, y + 2.3, name, 6.5, SOFT, role="mono", anchor="end", spacing=0.5)
        )
    parts.append(text(mark_x - 4, mark_y, "drawspec", mark_size, INK, weight="bold", spacing=-3))
    parts.append(text(mark_x, mark_y + 40, "Diagrams from meaning, not coordinates.", 21, SOFT))

    # The JSON on the left, and the drawing it makes in front of the plates.
    lines = snippet_lines(SPEC)
    code_x, code_y, code_size, lead = 70, 300, 10.5, 15.5
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
    draw_x, draw_y, draw_w = 600, 294, 280
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

    parts.append(title_block(WIDTH - 44 - 300, HEIGHT - 44 - 98, 300))

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
