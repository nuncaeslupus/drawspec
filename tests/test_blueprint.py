"""The blueprint theme: any diagram on a drafting sheet.

`[canvas]` grew a sheet — a ground, a grid, a zoned border with registration
marks, and a title block filled from the document — and the bundled `blueprint`
theme turns all of it on. These tests hold the promises that make that safe:

* it is **standalone furniture**: the inline profile still inherits its page;
* it is **outside the drawing**: the canvas grows and the drawing moves, so no
  stroke crosses a word and nothing leaves the canvas;
* it is **checked like any colour**: the ink and every declared colour must read
  on the ground, and the greyscale invariant still holds;
* it reaches **PNG export**, which rasterises the standalone profile.
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import replace
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

import pytest
from clipping import clipped
from collisions import collisions

import drawspec
from drawspec import sheet
from drawspec.emit import check_embedding_safety
from drawspec.errors import FitError, ThemeError
from drawspec.export import available, render_png
from drawspec.geometry import fit
from drawspec.kinds import scene_for
from drawspec.render import centred, framed, render_document
from drawspec.scene import extents
from drawspec.schema import load_document, parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import GRAPHIC_CONTRAST, TEXT_CONTRAST, contrast, load_theme

ROOT: Final = Path(__file__).resolve().parent.parent
REFERENCE: Final = ROOT / "docs" / "reference"
BLUEPRINT_REFERENCES: Final = sorted(REFERENCE.glob("*-blueprint-*.json"))

#: A spread of kinds, drawn on the sheet by naming the theme rather than by the
#: document — the theme is for *any* diagram, not only the three that ask.
OTHER_KINDS: Final = (
    "flow-triage",
    "sequence-dns",
    "chart-bars",
    "cycle-review",
    "gantt-migration",
    "venn-parity",
    "tree-decisions",
    "files-project",
)

GROUND: Final = "#0b2d52"

FLOW: Final[dict[str, Any]] = {
    "version": 1,
    "kind": "flow",
    "title": "Three steps",
    "nodes": [{"id": "a", "text": "One"}, {"id": "b", "text": "Two"}, {"id": "c", "text": "Three"}],
    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
}


def _root(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


# -- the theme ----------------------------------------------------------------


def test_the_blueprint_theme_is_bundled_and_turns_the_sheet_on() -> None:
    canvas = load_theme("blueprint").canvas
    assert canvas.ground == GROUND
    assert (canvas.pattern, canvas.border, canvas.title_block) == ("grid", "zoned", True)
    assert canvas.sheet


def test_the_default_theme_has_no_sheet() -> None:
    assert not load_theme().canvas.sheet


def test_blueprint_is_greyscale_safe() -> None:
    assert load_theme("blueprint").ambiguous_role_pairs() == ()


def test_the_blueprint_ink_reads_on_its_ground_as_text() -> None:
    canvas = load_theme("blueprint").canvas
    assert contrast(canvas.ink, canvas.ground) >= TEXT_CONTRAST


def test_every_blueprint_colour_reads_on_its_ground() -> None:
    theme = load_theme("blueprint")
    drawn = theme.declared_colours() - {"currentColor", "none", theme.canvas.ground}
    for colour in drawn:
        assert contrast(colour, theme.canvas.ground) >= GRAPHIC_CONTRAST, colour


def test_an_ink_too_close_to_the_ground_is_refused() -> None:
    with pytest.raises(ThemeError, match="text needs"):
        load_theme({"version": 1, "canvas": {"ground": "#222222", "ink": "#333333"}})


def test_a_role_colour_that_vanishes_into_the_ground_is_refused() -> None:
    theme = {
        "version": 1,
        "canvas": {"ground": GROUND, "ink": "#ffffff"},
        "role": {"emphasis": {"stroke": "#0c2f55"}},
    }
    with pytest.raises(ThemeError, match="#0c2f55"):
        load_theme(theme)


def test_a_rule_colour_that_vanishes_into_the_ground_is_refused() -> None:
    with pytest.raises(ThemeError, match="#0d3058"):
        load_theme(
            {"version": 1, "canvas": {"ground": GROUND, "ink": "#ffffff", "rule": "#0d3058"}}
        )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ground", "currentColor", "blank sheet"),
        ("ground", "blue", "not a colour"),
        ("pattern", "dots", "not one of none, grid"),
        ("border", "double", "not one of none, zoned"),
        ("title_block", "yes", "true or false"),
        ("rule", "currentColor", "hex colour"),
        ("accent", "none", "hex colour"),
    ],
)
def test_a_malformed_sheet_key_is_refused(key: str, value: object, message: str) -> None:
    with pytest.raises(ThemeError, match=message):
        load_theme({"version": 1, "canvas": {key: value}})


def test_a_misspelt_sheet_key_is_refused_by_name() -> None:
    with pytest.raises(ThemeError, match="'title_blocks'"):
        load_theme({"version": 1, "canvas": {"title_blocks": True}})


def test_sheet_colours_are_declared_so_the_emitter_allows_them() -> None:
    theme = load_theme("blueprint")
    assert {GROUND, theme.canvas.rule, theme.canvas.accent} <= theme.declared_colours()


def test_an_empty_rule_and_accent_mean_the_ink() -> None:
    canvas = load_theme({"version": 1, "canvas": {"border": "zoned"}}).canvas
    assert canvas.sheet_colours == (canvas.ink, canvas.ink)


# -- inline keeps inheriting the page -----------------------------------------


@pytest.mark.parametrize("path", BLUEPRINT_REFERENCES, ids=lambda p: p.stem)
def test_inline_draws_no_sheet(path: Path) -> None:
    svg = drawspec.render_file(path)
    assert GROUND not in svg
    assert "grid-minor" not in svg
    assert "TITLE" not in svg
    assert 'fill="currentColor"' in svg or 'stroke="currentColor"' in svg


def test_inline_blueprint_is_the_default_drawing() -> None:
    """Same geometry as the default theme: only the theme's name is in the digest."""
    strip = re.compile(r"ds[0-9a-f]{10}")
    plain = strip.sub("ns", drawspec.render(FLOW))
    blue = strip.sub("ns", drawspec.render(FLOW, "blueprint"))
    assert plain == blue


# -- standalone draws the sheet -----------------------------------------------


@pytest.mark.parametrize("path", BLUEPRINT_REFERENCES, ids=lambda p: p.stem)
def test_standalone_draws_ground_grid_border_and_title_block(path: Path) -> None:
    document = load_document(path)
    svg = drawspec.render_file(path, profile="standalone")
    assert f'fill="{GROUND}"' in svg
    assert re.search(r'<pattern id="ds[0-9a-f]{10}-grid-minor"', svg)
    assert "letter-spacing" in svg
    for word in ("TITLE", document.title, "KIND", document.kind, "SIZE", "REV", "v1", "DWG "):
        assert word in svg, word
    # zone letters down the sides and numbers along the top
    assert ">A</text>" in svg and ">1</text>" in svg


@pytest.mark.parametrize("path", BLUEPRINT_REFERENCES, ids=lambda p: p.stem)
def test_standalone_sheet_is_embedding_safe(path: Path) -> None:
    theme = load_theme("blueprint")
    svg = drawspec.render_file(path, profile="standalone")
    assert check_embedding_safety(svg, theme, "standalone") == ()


def test_the_title_block_falls_back_to_the_kind_when_there_is_no_title() -> None:
    untitled = {key: value for key, value in FLOW.items() if key != "title"}
    svg = drawspec.render(untitled, "blueprint", "standalone")
    titles = [
        element.text
        for element in _root(svg).iter("{http://www.w3.org/2000/svg}text")
        if element.get("font-weight") == "bold"
    ]
    assert "flow" in titles


def test_the_drawing_number_is_derived_and_stable() -> None:
    first = drawspec.render(FLOW, "blueprint", "standalone")
    again = drawspec.render(FLOW, "blueprint", "standalone")
    assert first == again
    other = drawspec.render({**FLOW, "title": "Four steps"}, "blueprint", "standalone")
    number = re.compile(r"DWG [0-9A-F]{4}")
    found, changed = number.search(first), number.search(other)
    assert found and changed and found.group(0) != changed.group(0)


def test_the_sheet_grows_the_canvas_by_the_same_amount_for_every_drawing() -> None:
    side = sheet.INSET + sheet.BAND + sheet.PAD
    for name in OTHER_KINDS:
        document = load_document(REFERENCE / f"{name}.json")
        plain = _root(render_document(document, "default", "standalone"))
        blue = _root(render_document(document, "blueprint", "standalone"))
        assert float(blue.get("width", "0")) == pytest.approx(
            float(plain.get("width", "0")) + 2 * side
        ), name


def test_a_sheet_without_a_border_does_not_grow_sideways() -> None:
    theme = {"version": 1, "canvas": {"ground": GROUND, "ink": "#ffffff", "pattern": "grid"}}
    plain = _root(drawspec.render(FLOW, None, "standalone"))
    gridded = _root(drawspec.render(FLOW, load_theme(theme), "standalone"))
    assert gridded.get("width") == plain.get("width")
    assert gridded.get("height") == plain.get("height")


def test_a_sheet_with_no_ground_draws_its_border_on_the_page() -> None:
    bordered = load_theme({"version": 1, "canvas": {"border": "zoned"}})
    svg = drawspec.render(FLOW, bordered, "standalone")
    assert "stroke-opacity" in svg
    assert "<pattern" not in svg
    assert f'fill="{GROUND}"' not in svg


# -- nothing overlaps the furniture -------------------------------------------


@pytest.mark.parametrize(
    "path",
    [*BLUEPRINT_REFERENCES, *(REFERENCE / f"{name}.json" for name in OTHER_KINDS)],
    ids=lambda p: p.stem,
)
def test_no_stroke_crosses_a_word_and_nothing_leaves_the_sheet(path: Path) -> None:
    svg = render_document(load_document(path), "blueprint", "standalone")
    assert collisions(svg) == []
    assert clipped(svg) == []


@pytest.mark.parametrize("name", OTHER_KINDS)
def test_the_drawing_sits_inside_the_border_and_above_the_title_block(name: str) -> None:
    theme = load_theme("blueprint")
    document = load_document(REFERENCE / f"{name}.json")
    measurer = TextMeasurer(theme.font.stacks())
    fitted = fit(theme, lambda scaled: scene_for(document, scaled, measurer))
    scene = framed(centred(fitted.value, fitted.theme), fitted.theme)
    moved, laid = sheet.around(scene, fitted.theme, document, measurer)
    left, top, right, bottom = extents(moved.primitives)
    inner = sheet.INSET + sheet.BAND + sheet.PAD
    assert left >= inner and top >= inner
    assert right <= laid.width - inner
    assert laid.block is not None
    assert bottom <= laid.block_y
    assert laid.block_x + laid.block.width <= laid.width - inner
    assert laid.block_y + laid.block.height(laid.style) <= laid.height - inner


def test_a_title_too_long_for_the_block_is_a_fit_error() -> None:
    long = {**FLOW, "title": "A title that goes on " * 6}
    with pytest.raises(FitError, match="title block"):
        drawspec.render(long, "blueprint", "standalone")
    # inline has no title block, so the same document draws
    assert drawspec.render(long, "blueprint")


def test_an_ink_width_canvas_widens_to_hold_its_title_block() -> None:
    theme = load_theme("blueprint")
    theme = replace(theme, canvas=replace(theme.canvas, width_mode="ink"))
    document = parse_document({**FLOW, "title": "A rather longer title than the drawing"})
    svg = render_document(document, theme, "standalone")
    assert collisions(svg) == [] and clipped(svg) == []


# -- the README banner draws with the same furniture -----------------------------


def test_the_hero_draws_its_sheet_with_the_package_furniture() -> None:
    source = (ROOT / "tools" / "hero.py").read_text(encoding="utf-8")
    for call in ("sheet.grid(", "sheet.border(", "sheet.registration(", "sheet.title_block("):
        assert call in source, call


# -- PNG export ---------------------------------------------------------------


def _first_pixel(png: bytes) -> tuple[int, ...]:
    """The top-left pixel, read with zlib alone.

    Row 0 has no row above it and pixel 0 nothing to its left, so every PNG
    filter leaves its bytes as they are.
    """
    at, idat, header = 8, b"", b""
    while at < len(png):
        (length,) = struct.unpack(">I", png[at : at + 4])
        kind = png[at + 4 : at + 8]
        data = png[at + 8 : at + 8 + length]
        if kind == b"IHDR":
            header = data
        elif kind == b"IDAT":
            idat += data
        at += 12 + length
    channels = {2: 3, 6: 4}[header[9]]
    raw = zlib.decompress(idat)
    return tuple(raw[1 : 1 + channels])


@pytest.mark.skipif(not available(), reason="PNG export is an optional extra")
@pytest.mark.parametrize("background", ["light", "dark", "transparent"])
def test_png_export_is_drawn_on_the_ground(background: str) -> None:
    png = render_png(load_document(BLUEPRINT_REFERENCES[0]), background=background)
    assert _first_pixel(png)[:3] == (0x0B, 0x2D, 0x52)


# -- the gallery ----------------------------------------------------------------


def test_there_are_three_blueprint_reference_documents_of_different_kinds() -> None:
    kinds = {load_document(path).kind for path in BLUEPRINT_REFERENCES}
    assert len(BLUEPRINT_REFERENCES) >= 3 and len(kinds) >= 3
    for path in BLUEPRINT_REFERENCES:
        assert load_document(path).theme == "blueprint"


def test_the_gallery_shows_a_blueprint_document_on_its_sheet() -> None:
    for path in BLUEPRINT_REFERENCES:
        svg = (ROOT / "docs" / "gallery" / f"{path.stem}.svg").read_text(encoding="utf-8")
        assert f'fill="{GROUND}"' in svg, path.stem
