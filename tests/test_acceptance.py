"""T18 — the close-out: determinism, no system dependencies, and the brief's test.

Three claims, and each is made the hard way rather than the convenient one.

**Determinism** is checked in a *fresh interpreter*, not twice in this one. Two
renders in one process share every cache and every already-imported module, so
they agree for reasons that say nothing about the next run; a subprocess with a
different `PYTHONHASHSEED` is where an accidental dependency on set ordering
shows up.

**Zero system dependencies** is checked by rendering with `PATH` emptied. The
claim is not "we did not call a binary on purpose", it is "there is no binary to
call" — and the way to find out is to take them all away and see.

**The brief's second acceptance test** is the three worst diagrams in the corpus,
rewritten as documents. This asserts they render; whether they look right is a
human's judgement, and `make gallery` is where that happens.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

import pytest

from drawspec import render, render_document
from drawspec.emit import PROFILES
from drawspec.errors import FitError, LayoutError
from drawspec.geometry import fit
from drawspec.kinds import scene_for
from drawspec.render import centred
from drawspec.scene import extents
from drawspec.schema import load_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

ROOT: Final = Path(__file__).resolve().parents[1]
REFERENCE_DIR: Final = ROOT / "docs" / "reference"
FIXTURES: Final = tuple(sorted(path.stem for path in REFERENCE_DIR.glob("*.json")))

#: The brief's second acceptance test: the three worst diagrams in the corpus,
#: rewritten as declarative documents. The reviewer's verdict on each is in
#: `docs/brief.md`; what stands in for it here is the document beside it.
WORST_THREE: Final = {
    "fixture-020": "flow-validation",
    "fixture-067": "chart-complaints",
    "fixture-047": "cycle-review",
}

#: Rendering one document in a fresh interpreter, which is what a second run
#: really is. Imports nothing from the test suite, so it is the package's own
#: claim rather than the suite's.
RENDER_SCRIPT: Final = """
import sys
from drawspec import render_document
from drawspec.schema import load_document
sys.stdout.write(render_document(load_document(sys.argv[1]), profile=sys.argv[2]))
"""


def fixture(name: str) -> dict[str, object]:
    text = (REFERENCE_DIR / f"{name}.json").read_text(encoding="utf-8")
    loaded: dict[str, object] = json.loads(text)
    return loaded


def _in_a_fresh_interpreter(name: str, profile: str, **environment: str) -> str:
    """Render in a subprocess, with whatever environment the caller wants."""
    result = subprocess.run(
        [sys.executable, "-c", RENDER_SCRIPT, str(REFERENCE_DIR / f"{name}.json"), profile],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT / "src"),
            "HOME": os.environ.get("HOME", "/tmp"),
            **environment,
        },
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_every_fixture_renders_identically_on_a_second_run(name: str) -> None:
    """`nondeterministic_reruns == 0`, in a second interpreter with a new seed.

    A committed diagram that changes byte for byte between runs shows up as a
    diff nobody wrote, which is enough to make people stop committing them.
    """
    document = load_document(REFERENCE_DIR / f"{name}.json")
    for profile in PROFILES:
        here = render_document(document, profile=profile)
        assert here == render_document(document, profile=profile)
        assert here == _in_a_fresh_interpreter(name, profile, PYTHONHASHSEED="1")
        assert here == _in_a_fresh_interpreter(name, profile, PYTHONHASHSEED="7919")


def test_package_renders_with_no_system_binaries_available() -> None:
    """`system_dependencies == 0`: nothing to call, so nothing to install.

    `PATH` emptied, so any attempt to shell out to Graphviz, a browser or a
    converter fails rather than silently succeeding on a developer's machine.
    """
    svg = _in_a_fresh_interpreter("flow-validation", "standalone", PATH="")
    assert svg.startswith("<svg")
    assert "currentColor" not in svg


def test_no_runtime_dependency_beyond_the_font_reader() -> None:
    """The other half of the same claim, read off the package metadata.

    Text measurement needs the font tables; everything else — layout, routing,
    templates, charts, emission — is drawspec's own, which is what makes the tool
    a `pip install` rather than an installation.
    """
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]
    assert [name.split(">")[0].split("=")[0] for name in dependencies] == ["fonttools"]


@pytest.mark.parametrize(("fixture_name", "document_name"), sorted(WORST_THREE.items()))
def test_three_reference_documents_render_without_fit_or_layout_errors(
    fixture_name: str, document_name: str
) -> None:
    """The brief's second acceptance test: the three worst, redone.

    Parametrised by the corpus fixture each one stands for, so a failure names
    the diagram the reviewer complained about rather than a file in this repo.
    """
    assert (ROOT / "corpus" / "fixtures" / f"{fixture_name}.svg").is_file()
    try:
        svg = render(fixture(document_name))
    except (FitError, LayoutError) as error:  # pragma: no cover - the failure path
        pytest.fail(f"{document_name} ({fixture_name}) did not render: {error}")
    assert svg.startswith("<svg")


# --------------------------------------------------------------------------
# The close-out
# --------------------------------------------------------------------------


def test_every_kind_has_a_reference_document() -> None:
    """Nine kinds, nine documents — the set the gallery and this suite both use."""
    from drawspec.schema import KINDS

    kinds = {load_document(REFERENCE_DIR / f"{name}.json").kind for name in FIXTURES}
    assert kinds == set(KINDS)


def test_the_readme_points_at_something_that_exists() -> None:
    """A gallery link that rots is worse than no gallery link."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for path in ("docs/gallery/index.html", "docs/reference"):
        assert path in readme, path
        assert (ROOT / path).exists(), path


def test_the_readme_no_longer_says_there_is_no_renderer() -> None:
    """The status line was true until T11 and is the kind of thing that lingers."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "No renderer yet" not in readme


# --------------------------------------------------------------------------
# One canvas, so one type size
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_every_reference_document_is_drawn_to_the_same_canvas_width(name: str) -> None:
    """`canvas_width_variance == 0` across the kinds.

    The one property no diagram can be checked for on its own, and the one a
    reader meets first. Each of these is internally perfect at whatever width it
    needed; drop two of them into a page at one column width and the viewer
    scales each by its own factor, so the same eleven-point label is read at
    eighteen points in the small one and eleven in the big one. The reader sees a
    tool that picks a type size at random.

    Empty margin beside a narrow diagram is the price, and it is the right way
    round: unused paper costs nothing to read past, and a different type size in
    every figure was the single most repeated complaint in the corpus.
    """
    theme = load_theme()
    svg = render_document(load_document(REFERENCE_DIR / f"{name}.json"), profile="standalone")
    width = float(ElementTree.fromstring(svg).get("width", "0"))
    # The ink inset is half a stroke either side of the drawing — see `emit`.
    assert width == pytest.approx(theme.canvas.width + theme.edge.stroke_width, abs=1.6)


def test_a_narrow_diagram_is_centred_on_the_canvas_rather_than_cropped_to_it() -> None:
    """The margin a fixed canvas buys is shared between the two sides."""
    theme = load_theme()
    document = load_document(REFERENCE_DIR / "flow-validation.json")
    measurer = TextMeasurer(theme.font.stacks())
    fitted = fit(theme, lambda scaled: scene_for(document, scaled, measurer))
    drawn = fitted.value
    assert drawn.width < theme.canvas.width, "this fixture must be narrower than the canvas"

    padded = centred(drawn, fitted.theme)
    assert padded.width == pytest.approx(theme.canvas.width)
    left, _, right, _ = extents(padded.primitives)
    assert left == pytest.approx(padded.width - right, abs=1e-6)


def test_the_ink_width_mode_leaves_a_narrow_diagram_alone() -> None:
    """The other half of the setting, so it is a choice rather than a default."""
    theme = replace(load_theme(), canvas=replace(load_theme().canvas, width_mode="ink"))
    document = load_document(REFERENCE_DIR / "flow-validation.json")
    measurer = TextMeasurer(theme.font.stacks())
    drawn = fit(theme, lambda scaled: scene_for(document, scaled, measurer)).value
    assert centred(drawn, theme) is drawn
