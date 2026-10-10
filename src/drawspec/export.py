"""Raster export: the same drawing as a PNG, for the places an SVG cannot go.

An SVG is the product — it scales, it inherits the page's ink, and it diffs. But
a chat message, a slide, an issue tracker's attachment field or a word processor
wants a picture file, and asking every user to find a converter that sets the
text in some other font is how a label that fitted comes out clipped.

So this module is deliberately small, and makes three decisions on the user's
behalf:

**It rasterises the `standalone` profile.** The inline profile draws in
`currentColor`, which means "the ink of the page around me" — and a PNG has no
page around it. Standalone resolves that ink to the theme's explicit value, which
is exactly what a converter needs.

**The background is a choice of three, not a colour.** `light` is the theme's ink
on white; `dark` swaps the ink for a light one on near-black, which is what the
inline SVG does by itself on a dark page; `transparent` is the theme's ink on
nothing. Every colour a brand theme declares was already checked to read at 3:1
on both a white and a `#121212` page (see `drawspec.brand`), so those are the two
pages offered.

**It is set in the fonts the layout was measured with.** The renderer is told to
ignore the host's fonts and is handed the very files `TextMeasurer` resolved —
the bundled DejaVu faces unless the theme names a family the host has. A
renderer that chose its own fallback would draw text a few units wider than the
box it was measured into, and the PNG would have the overflow the SVG was
refused for. With only the bundled fonts in play the output is byte-identical
on every machine.

The renderer is `resvg-py`: one self-contained wheel (resvg compiled in, no
Cairo, no system libraries), and the optional extra `drawspec[png]`. It encodes
PNG only, which is why there is no WebP here — see `docs/proposals/exports.md`.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from drawspec.errors import ExportError
from drawspec.render import render_document
from drawspec.schema import Document, parse_document
from drawspec.text.fontlib import FONT_ROLES, FONT_WEIGHTS, bundled_font_family, bundled_font_path
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme, load_theme

#: The raster formats `render --format` accepts beside `svg` and `text`.
IMAGE_FORMATS: Final = ("png",)

#: The pages a PNG can be drawn on. `light` first: it is the default.
BACKGROUNDS: Final = ("light", "dark", "transparent")

#: Pixels per SVG user unit. Two, because a PNG is most often looked at on a
#: high-density screen, where one pixel per unit is visibly soft; a document 640
#: wide comes out about 1330 pixels across.
DEFAULT_SCALE: Final = 2.0

#: The largest scale accepted. Eight already makes a 640-wide drawing over five
#: thousand pixels across; past it a typo (`--scale 20`) would allocate
#: gigabytes before anyone noticed.
MAX_SCALE: Final = 8.0

#: The two pages. The dark one is `drawspec.brand.DARK_PAGE`, the page every
#: derived colour is checked against, so a brand accent reads on it.
LIGHT_PAGE: Final = "#ffffff"
DARK_PAGE: Final = "#121212"

#: The ink on the dark page: what the inline SVG would inherit from a dark
#: stylesheet. Not pure white, which glares against near-black at small sizes.
DARK_INK: Final = "#e8e8e8"

#: What a user without the extra is told, in full.
MISSING_EXTRA: Final = (
    "PNG export needs drawspec's optional renderer, which is not installed: "
    "pip install 'drawspec[png]'"
)


def render_png(
    document: Document | Mapping[str, Any],
    theme: Theme | str | Path | None = None,
    *,
    scale: float = DEFAULT_SCALE,
    background: str = "light",
) -> bytes:
    """Render a document to PNG bytes.

    Args:
        document: a parsed `Document`, or a mapping as read from JSON.
        theme: as for `render`; the document's own `theme` is used when None.
        scale: pixels per SVG unit, above 0 and at most `MAX_SCALE`.
        background: one of `BACKGROUNDS`.

    Raises:
        ExportError: the `png` extra is not installed.
        ValueError: `scale` or `background` is out of range.
        DrawspecError: anything `render` refuses, refused the same way.
    """
    if background not in BACKGROUNDS:
        raise ValueError(
            f"unknown background {background!r}; expected one of {', '.join(BACKGROUNDS)}"
        )
    if not 0 < scale <= MAX_SCALE:
        raise ValueError(f"scale must be above 0 and at most {MAX_SCALE:g}, got {scale:g}")
    rasterise = _renderer()

    parsed = document if isinstance(document, Document) else parse_document(document)
    resolved = load_theme(theme if theme is not None else (parsed.theme or None))
    if background == "dark":
        resolved = replace(resolved, canvas=replace(resolved.canvas, ink=DARK_INK))
    svg = render_document(parsed, resolved, "standalone")

    page = {"light": LIGHT_PAGE, "dark": DARK_PAGE, "transparent": None}[background]
    return rasterise(
        svg_string=svg,
        background=page,
        zoom=scale,
        skip_system_fonts=True,
        font_files=[str(path) for path in font_files(resolved)],
        font_family=bundled_font_family("sans"),
        sans_serif_family=bundled_font_family("sans"),
        serif_family=bundled_font_family("serif"),
        monospace_family=bundled_font_family("mono"),
    )


def font_files(theme: Theme) -> tuple[Path, ...]:
    """Every font file the layout of a drawing in `theme` was measured against.

    The bundled faces always, because a generic keyword at the end of a stack
    names them; and whichever file each role and weight resolved to, which is
    the same file unless the theme names a family the host has installed.
    Substitution is not re-reported here: rendering the SVG already did.
    """
    measurer = TextMeasurer(theme.font.stacks())
    found: list[Path] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for role in FONT_ROLES:
            for weight in FONT_WEIGHTS:
                for path in (bundled_font_path(role, weight), measurer.resolve(role, weight).path):
                    if path not in found:
                        found.append(path)
    return tuple(found)


def _renderer() -> Callable[..., bytes]:
    """`resvg_py.svg_to_bytes`, or the install line when the extra is missing."""
    try:
        from resvg_py import svg_to_bytes
    except ImportError:
        raise ExportError(MISSING_EXTRA) from None
    return svg_to_bytes


def available() -> bool:
    """Whether PNG export can run here — the `png` extra is installed."""
    try:
        _renderer()
    except ExportError:
        return False
    return True


__all__ = [
    "BACKGROUNDS",
    "DEFAULT_SCALE",
    "IMAGE_FORMATS",
    "MAX_SCALE",
    "available",
    "font_files",
    "render_png",
]
