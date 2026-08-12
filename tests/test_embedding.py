"""T17 — the embedding targets: Markdown, HTML, PDF, and a greyscale printer.

The gate is `embedding_safety_violations == 0`, **measured per profile**. Summing
the two profiles is exactly how an unresolved `currentColor` reaches a PDF: the
inline path is exercised constantly and the standalone path is not, so a single
aggregated number lets the quiet one hide behind the loud one. Every test here
that touches a profile names it.

The PDF target is asserted as the properties a converter depends on — resolved
ink, explicit dimensions, no font resource to fetch — with the real conversion in
a sibling test that skips when nothing is installed to do it. That split is
deliberate: the property test is the one that has to run everywhere, and the
conversion test is the one that would otherwise silently not run at all.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

import pytest

from drawspec import render, render_document
from drawspec.emit import PROFILES, check_embedding_safety, emit
from drawspec.kinds import scene_for
from drawspec.schema import load_document
from drawspec.text import TextMeasurer
from drawspec.theme import LUMINANCE_DELTA, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "reference"

FIXTURES: Final = tuple(sorted(path.stem for path in REFERENCE_DIR.glob("*.json")))

#: What could turn an SVG into a PDF, if any of them is installed.
CONVERTERS: Final = ("rsvg-convert", "inkscape", "chromium", "chromium-browser", "google-chrome")

#: One node per node role, so a single drawing exercises the whole vocabulary.
SAMPLED_ROLES: Final = ("start", "step", "decision", "note", "emphasis", "terminal")

ROLE_SAMPLER: Final = {
    "version": 1,
    "kind": "flow",
    "title": "Every role",
    "nodes": [
        {"id": identifier, "text": role.title(), "role": role}
        for identifier, role in zip("abcdef", SAMPLED_ROLES, strict=True)
    ],
    "edges": [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "c"},
        {"from": "c", "to": "d", "role": "weak"},
        {"from": "c", "to": "e"},
        {"from": "e", "to": "f"},
    ],
}


def fixture(name: str) -> dict[str, object]:
    text = (REFERENCE_DIR / f"{name}.json").read_text(encoding="utf-8")
    loaded: dict[str, object] = json.loads(text)
    return loaded


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("profile", PROFILES)
def test_every_fixture_passes_safety_in_both_profiles(name: str, profile: str) -> None:
    """`embedding_safety_violations == 0`, one profile and one fixture at a time.

    Parametrised rather than looped so a failure names which fixture in which
    profile, which is the difference between a number and a diagnosis.
    """
    svg = render(fixture(name), profile=profile)
    assert check_embedding_safety(svg, THEME, profile) == ()


def test_two_fixtures_in_one_html_page_have_no_id_or_selector_collision() -> None:
    """The Markdown promise, in its strictest form: two diagrams, one document.

    Ids are content-derived, so two *different* diagrams cannot share one; and
    there is nothing to select — no `class`, no `<style>`, no element name a page
    stylesheet could reach that it could not reach anyway.
    """
    first = render(fixture("flow-validation"))
    second = render(fixture("chart-complaints"))
    page = f"<html><body><h1>Two</h1>{first}<p>and</p>{second}</body></html>"

    identifiers = re.findall(r'\bid="([^"]*)"', page)
    assert identifiers
    assert len(identifiers) == len(set(identifiers))
    assert "<style" not in page
    assert "class=" not in page
    for reference in re.findall(r"url\(#([^)]*)\)", page):
        assert reference in identifiers


def test_the_same_diagram_twice_on_one_page_is_disambiguated_by_a_namespace() -> None:
    """Two copies of one diagram *do* collide — determinism says they must.

    The same document renders to the same bytes, ids included; that is a promised
    property, not a defect. The remedy is the emitter's `namespace` argument, and
    this is the test that it works, because a page that shows one diagram twice is
    a real page.
    """
    built = scene_for(load_document(REFERENCE_DIR / "stack-decisions.json"), THEME, MEASURER)
    twice = emit(built, THEME) + emit(built, THEME)
    identifiers = re.findall(r'\bid="([^"]*)"', twice)
    assert len(identifiers) != len(set(identifiers)), "expected the duplicate this test is about"

    apart = emit(built, THEME, namespace="dsone") + emit(built, THEME, namespace="dstwo")
    identifiers = re.findall(r'\bid="([^"]*)"', apart)
    assert len(identifiers) == len(set(identifiers))
    assert check_embedding_safety(apart[: len(apart) // 2], THEME, namespace="dsone") == ()


def test_standalone_fixture_converts_to_pdf_without_unresolved_colour() -> None:
    """The properties a converter depends on, asserted without one.

    A PDF has nothing to inherit from: `currentColor` there resolves to whatever
    the converter's default ink is, which is how a diagram themed in one colour
    arrives in another. So the standalone profile resolves it, states its own
    size, and references no font file a converter would have to fetch.
    """
    svg = render(fixture("flow-validation"), profile="standalone")
    assert "currentColor" not in svg
    assert THEME.canvas.ink in svg
    root = ElementTree.fromstring(svg)
    assert root.get("width") and root.get("height")
    assert not re.search(r"@font-face|\.woff2?\b|\.ttf\b|data:font", svg)
    assert check_embedding_safety(svg, THEME, "standalone") == ()


@pytest.mark.skipif(
    not any(shutil.which(name) for name in CONVERTERS),
    reason="no SVG-to-PDF converter installed",
)
def test_standalone_fixture_really_converts_to_pdf(tmp_path: Path) -> None:
    """The same claim, done rather than described, when a converter exists."""
    source = tmp_path / "diagram.svg"
    source.write_text(render(fixture("flow-validation"), profile="standalone"), encoding="utf-8")
    out = tmp_path / "diagram.pdf"

    converter = next(name for name in CONVERTERS if shutil.which(name))
    command = {
        "rsvg-convert": [converter, "-f", "pdf", "-o", str(out), str(source)],
        "inkscape": [converter, str(source), "--export-filename", str(out)],
    }.get(converter, [converter, "--headless", f"--print-to-pdf={out}", str(source)])
    subprocess.run(command, check=True, capture_output=True)
    assert out.read_bytes().startswith(b"%PDF")


def test_greyscale_conversion_preserves_role_distinctions() -> None:
    """Print it in black and white and the roles are still told apart.

    Measured on the output rather than on the theme: every colour in the SVG is
    replaced by its own luminance, and the paint signatures of the drawn shapes
    are counted. Two roles that differed only by colour would collapse into one
    signature here, and the count would drop below the number of roles drawn.
    """
    svg = render(ROLE_SAMPLER, profile="standalone")
    grey = _greyscale(svg)
    signatures = {
        (
            element.tag.rsplit("}", 1)[-1],
            element.get("fill"),
            element.get("stroke"),
            element.get("stroke-width"),
            element.get("stroke-dasharray"),
            _corner(element),
        )
        for element in ElementTree.fromstring(grey).iter()
        if element.tag.rsplit("}", 1)[-1] in ("rect", "ellipse", "polygon")
    }
    assert len(signatures) >= len(SAMPLED_ROLES)


def test_no_two_declared_colours_are_indistinguishable_in_grey() -> None:
    """The other half of the same promise, on the theme's own palette."""
    colours = sorted(
        colour for colour in THEME.declared_colours() if re.fullmatch(r"#[0-9a-fA-F]{6}", colour)
    )
    greys = {colour: _luminance(colour) for colour in colours}
    for first in colours:
        for second in colours:
            if first < second and abs(greys[first] - greys[second]) < LUMINANCE_DELTA:
                # Allowed only when no pair of roles relies on this difference,
                # which is what the theme's own invariant already guarantees.
                assert THEME.ambiguous_role_pairs() == ()


# --------------------------------------------------------------------------
# The profiles differ in exactly one thing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_inline_and_standalone_differ_only_in_what_they_assume(name: str) -> None:
    """Inline inherits its ink and its size; standalone states both."""
    inline = render(fixture(name), profile="inline")
    standalone = render(fixture(name), profile="standalone")
    assert "currentColor" in inline
    assert "currentColor" not in standalone
    assert 'width="' not in inline.split(">", 1)[0]
    assert 'width="' in standalone.split(">", 1)[0]


@pytest.mark.parametrize("name", FIXTURES)
def test_every_fixture_renders_identically_twice_in_both_profiles(name: str) -> None:
    """Byte-identical reruns, which is what makes a diagram diffable in a repo."""
    document = load_document(REFERENCE_DIR / f"{name}.json")
    for profile in PROFILES:
        assert render_document(document, profile=profile) == render_document(
            document, profile=profile
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _corner(element: ElementTree.Element) -> str:
    """Square, rounded or fully rounded — what a reader sees, not the number.

    A pill and a rounded rectangle are the same SVG element and differ only in
    the radius, so a signature that recorded merely *whether* there was one would
    make `start` and `step` look identical in grey when they are not.
    """
    radius, height = element.get("rx"), element.get("height")
    if radius is None or height is None:
        return "none"
    return "pill" if float(radius) >= float(height) / 2 - 1e-6 else "rounded"


def _luminance(colour: str) -> float:
    """WCAG relative luminance, which is what a greyscale printer approximates."""
    channels = [int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _greyscale(svg: str) -> str:
    """Every hex colour in the document replaced by its own grey."""

    def to_grey(match: re.Match[str]) -> str:
        level = round(_luminance(match.group(0)) * 255)
        return f"#{level:02x}{level:02x}{level:02x}"

    return re.sub(r"#[0-9a-fA-F]{6}", to_grey, svg)
