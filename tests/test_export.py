"""PNG export: the drawing as a picture file, and the refusal when it cannot be.

What is asserted is what a user attaching the file would notice: that it is a
PNG at all, that `--scale` changes its size by that factor, that the three
backgrounds are three different pages with the ink to match, and that a
machine without the `png` extra is told the one command that fixes it.

The PNG is read back with a few lines of `zlib` rather than an imaging library,
so these tests need nothing beyond the extra they exercise. Everything but the
missing-extra tests is skipped when the extra is not installed; CI installs it.
"""

from __future__ import annotations

import json
import re
import struct
import sys
import zlib
from pathlib import Path

import pytest

from drawspec import ExportError, render_png
from drawspec.cli import main
from drawspec.export import DARK_PAGE, available, font_files
from drawspec.render import render_document
from drawspec.schema import parse_document
from drawspec.text.fontlib import bundled_font_path
from drawspec.theme import load_theme

SIGNATURE = b"\x89PNG\r\n\x1a\n"

DOCUMENT = {
    "version": 1,
    "kind": "flow",
    "title": "Two steps",
    "nodes": [
        {"id": "a", "text": "Write the document", "role": "start"},
        {"id": "b", "text": "Attach the picture", "role": "terminal"},
    ],
    "edges": [{"from": "a", "to": "b", "label": "render"}],
}

needs_extra = pytest.mark.skipif(
    not available(), reason="PNG export is an optional extra: pip install 'drawspec[png]'"
)


# ---------------------------------------------------------------------------
# Reading a PNG back, with nothing but zlib
# ---------------------------------------------------------------------------


def chunks(png: bytes) -> dict[bytes, bytes]:
    """Every chunk's data by type, IDAT concatenated."""
    assert png.startswith(SIGNATURE)
    found: dict[bytes, bytes] = {}
    at = len(SIGNATURE)
    while at < len(png):
        (length,) = struct.unpack(">I", png[at : at + 4])
        kind = png[at + 4 : at + 8]
        found[kind] = found.get(kind, b"") + png[at + 8 : at + 8 + length]
        at += 12 + length
    return found


def size(png: bytes) -> tuple[int, int]:
    width, height = struct.unpack(">II", chunks(png)[b"IHDR"][:8])
    return width, height


def pixels(png: bytes) -> list[bytes]:
    """The image as rows of RGBA bytes, unfiltered (8-bit RGBA only)."""
    parts = chunks(png)
    width, height, depth, colour = struct.unpack(">IIBB", parts[b"IHDR"][:10])
    assert (depth, colour) == (8, 6), "expected 8-bit RGBA"
    raw = zlib.decompress(parts[b"IDAT"])
    stride = width * 4
    rows: list[bytes] = []
    prior = bytearray(stride)
    at = 0
    for _ in range(height):
        kind, line = raw[at], bytearray(raw[at + 1 : at + 1 + stride])
        at += 1 + stride
        for i in range(stride):
            left = line[i - 4] if i >= 4 else 0
            up = prior[i]
            corner = prior[i - 4] if i >= 4 else 0
            if kind == 1:
                line[i] = (line[i] + left) & 0xFF
            elif kind == 2:
                line[i] = (line[i] + up) & 0xFF
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 0xFF
            elif kind == 4:
                estimate = left + up - corner
                best = min(
                    (abs(estimate - left), 0, left),
                    (abs(estimate - up), 1, up),
                    (abs(estimate - corner), 2, corner),
                )[2]
                line[i] = (line[i] + best) & 0xFF
        rows.append(bytes(line))
        prior = line
    return rows


def rgba(rows: list[bytes], x: int, y: int) -> tuple[int, int, int, int]:
    r, g, b, a = rows[y][x * 4 : x * 4 + 4]
    return r, g, b, a


def opaque_lightness(rows: list[bytes]) -> list[int]:
    """The red channel of every opaque pixel — the drawings here are grey."""
    return [row[i] for row in rows for i in range(0, len(row), 4) if row[i + 3] == 255]


def canvas_size() -> tuple[float, float]:
    """The standalone SVG's own width and height, in user units."""
    svg = render_document(parse_document(DOCUMENT), None, "standalone")
    found = re.search(r'<svg[^>]* width="([\d.]+)" height="([\d.]+)"', svg)
    assert found
    return float(found.group(1)), float(found.group(2))


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


@needs_extra
def test_the_output_is_a_png() -> None:
    assert render_png(DOCUMENT).startswith(SIGNATURE)


@needs_extra
def test_at_scale_one_a_pixel_is_a_unit() -> None:
    """The renderer rounds the canvas to whole units, then scales."""
    width, height = canvas_size()
    got = size(render_png(DOCUMENT, scale=1))
    assert abs(got[0] - width) <= 0.5
    assert abs(got[1] - height) <= 0.5


@needs_extra
@pytest.mark.parametrize("scale", [2, 3, 4])
def test_the_pixel_size_follows_the_scale(scale: int) -> None:
    one = size(render_png(DOCUMENT, scale=1))
    assert size(render_png(DOCUMENT, scale=scale)) == (one[0] * scale, one[1] * scale)


@needs_extra
def test_the_default_scale_is_two() -> None:
    assert size(render_png(DOCUMENT)) == size(render_png(DOCUMENT, scale=2))


@needs_extra
def test_a_light_background_is_white_with_dark_ink() -> None:
    rows = pixels(render_png(DOCUMENT, background="light"))
    assert rgba(rows, 0, 0) == (255, 255, 255, 255)
    assert min(opaque_lightness(rows)) < 64


@needs_extra
def test_a_dark_background_is_near_black_with_light_ink() -> None:
    rows = pixels(render_png(DOCUMENT, background="dark"))
    page = int(DARK_PAGE[1:3], 16)
    assert rgba(rows, 0, 0) == (page, page, page, 255)
    assert max(opaque_lightness(rows)) > 192


@needs_extra
def test_a_transparent_background_leaves_the_page_empty() -> None:
    rows = pixels(render_png(DOCUMENT, background="transparent"))
    assert rgba(rows, 0, 0)[3] == 0
    assert any(row[i] for row in rows for i in range(3, len(row), 4))


@needs_extra
def test_the_document_s_own_theme_is_used() -> None:
    themed = {**DOCUMENT, "theme": "accent"}
    assert render_png(themed) == render_png(DOCUMENT, theme="accent")


@needs_extra
def test_two_renders_are_byte_identical() -> None:
    assert render_png(DOCUMENT) == render_png(parse_document(DOCUMENT))


@pytest.mark.parametrize(
    ("arguments", "message"),
    [({"scale": 0}, "scale"), ({"scale": 9}, "scale"), ({"background": "sepia"}, "sepia")],
)
def test_out_of_range_options_are_refused(arguments: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        render_png(DOCUMENT, **arguments)  # type: ignore[arg-type]


def test_the_renderer_is_handed_the_bundled_fonts() -> None:
    files = font_files(load_theme(None))
    for role in ("sans", "serif", "mono"):
        assert bundled_font_path(role) in files
        assert bundled_font_path(role, "bold") in files


# ---------------------------------------------------------------------------
# Without the extra
# ---------------------------------------------------------------------------


@pytest.fixture
def without_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `import resvg_py` fail, as it does where the extra is not installed."""
    monkeypatch.setitem(sys.modules, "resvg_py", None)


@pytest.mark.usefixtures("without_extra")
def test_a_missing_extra_names_the_install_line() -> None:
    assert not available()
    with pytest.raises(ExportError, match=re.escape("pip install 'drawspec[png]'")):
        render_png(DOCUMENT)


@pytest.mark.usefixtures("without_extra")
def test_the_cli_refuses_a_missing_extra_with_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = write(tmp_path / "doc.json")
    assert main(["render", str(source), "-o", str(tmp_path / "doc.png")]) == 1
    assert "pip install 'drawspec[png]'" in capsys.readouterr().err
    assert not (tmp_path / "doc.png").exists()


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def write(path: Path) -> Path:
    path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    return path


@needs_extra
def test_format_png_writes_a_png(tmp_path: Path) -> None:
    out = tmp_path / "picture"
    assert main(["render", str(write(tmp_path / "d.json")), "--format", "png", "-o", str(out)]) == 0
    assert out.read_bytes().startswith(SIGNATURE)


@needs_extra
def test_the_format_is_inferred_from_a_png_extension(tmp_path: Path) -> None:
    out = tmp_path / "d.png"
    assert main(["render", str(write(tmp_path / "d.json")), "-o", str(out)]) == 0
    assert out.read_bytes() == render_png(DOCUMENT)


@needs_extra
def test_scale_and_background_reach_the_png(tmp_path: Path) -> None:
    out = tmp_path / "d.png"
    source = str(write(tmp_path / "d.json"))
    assert main(["render", source, "-o", str(out), "--scale", "1", "--background", "dark"]) == 0
    assert out.read_bytes() == render_png(DOCUMENT, scale=1, background="dark")


def test_an_svg_extension_still_writes_svg(tmp_path: Path) -> None:
    out = tmp_path / "d.svg"
    assert main(["render", str(write(tmp_path / "d.json")), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<svg")


@pytest.mark.parametrize(
    "extra",
    [
        ["--format", "svg", "-o", "x.png"],
        ["--format", "png", "-o", "x.svg"],
        ["--scale", "2"],
        ["--background", "dark", "-o", "x.svg"],
        ["--format", "png", "--scale", "0"],
        ["--format", "png", "--scale", "lots"],
        ["--format", "png", "--background", "sepia"],
    ],
)
def test_contradictory_or_misplaced_flags_exit_two(
    tmp_path: Path, extra: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = [str(tmp_path / part) if part.startswith("x.") else part for part in extra]
    assert main(["render", str(write(tmp_path / "d.json")), *arguments]) == 2
    assert capsys.readouterr().err
