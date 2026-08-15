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
from collections.abc import Sequence
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
from drawspec.scene import Polygon, Rect, TextLine, extents
from drawspec.schema import load_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

ROOT: Final = Path(__file__).resolve().parents[1]
REFERENCE_DIR: Final = ROOT / "docs" / "reference"
FIXTURES: Final = tuple(sorted(path.stem for path in REFERENCE_DIR.glob("*.json")))

#: The one level every kind sets the text *inside a shape* at. Chart and edge
#: labels are furniture and sit a level below it — see the test that reads this.
BODY_LEVEL: Final = "body"

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
    # The outer margin frames the drawing on both sides — see `theme.Canvas.margin`,
    # which is why it is *added* to the width rather than taken out of it: taken
    # out, this equality would still hold and every drawing would have lost the
    # margin from its own budget. The ink inset is half a stroke either side of
    # that again — see `emit`.
    drawn = theme.canvas.width + theme.canvas.margin * 2
    assert width == pytest.approx(drawn + theme.edge.stroke_width, abs=1.6)


def test_a_narrow_diagram_is_centred_on_the_canvas_rather_than_cropped_to_it() -> None:
    """The margin a fixed canvas buys is shared between the two sides.

    Asserted as *the drawing moved by half the slack*, rather than as the ink
    coming out symmetric about the middle. The two are only the same thing when
    the drawing's own frame is its ink, and it is not: `extents` measures a text
    run as a point, on purpose — its width belongs to whoever has the font — so a
    free edge label sitting outside every box counts towards the frame the family
    computed and not towards the ink measured here. That is a real asymmetry in
    the drawing, and centring is not the function that should be answering for
    it.
    """
    theme = load_theme()
    document = load_document(REFERENCE_DIR / "flow-validation.json")
    measurer = TextMeasurer(theme.font.stacks())
    fitted = fit(theme, lambda scaled: scene_for(document, scaled, measurer))
    drawn = fitted.value
    assert drawn.width < theme.canvas.width, "this fixture must be narrower than the canvas"

    padded = centred(drawn, fitted.theme)
    assert padded.width == pytest.approx(theme.canvas.width)
    slack = (padded.width - drawn.width) / 2
    before = extents(drawn.primitives)
    after = extents(padded.primitives)
    assert after[0] == pytest.approx(before[0] + slack, abs=1e-6)
    assert after[2] == pytest.approx(before[2] + slack, abs=1e-6)
    assert after[1] == pytest.approx(before[1], abs=1e-6), "centring is horizontal only"


def test_the_ink_width_mode_leaves_a_narrow_diagram_alone() -> None:
    """The other half of the setting, so it is a choice rather than a default."""
    theme = replace(load_theme(), canvas=replace(load_theme().canvas, width_mode="ink"))
    document = load_document(REFERENCE_DIR / "flow-validation.json")
    measurer = TextMeasurer(theme.font.stacks())
    drawn = fit(theme, lambda scaled: scene_for(document, scaled, measurer)).value
    assert centred(drawn, theme) is drawn


# --------------------------------------------------------------------------
# A binding height binds
# --------------------------------------------------------------------------

_TALL: Final = {
    "version": 1,
    "kind": "flow",
    "title": "four ranks",
    "nodes": [{"id": letter, "text": letter.upper()} for letter in "abcd"],
    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}],
}


def test_a_binding_height_that_cannot_be_met_is_refused() -> None:
    """`height_binding` was parsed, documented as a constraint, and read by nothing.

    A four-node flow asking for eighty units came back three hundred and thirty
    tall, exit 0, no refusal — the third outcome the format page promises never to
    produce. The refusal now names the height it got and the height it was asked
    for.

    Eighty is no longer the number that cannot be met: the graph family used to
    take its own outer margin out of the layout budget, and now that
    `[canvas] margin` frames every kind from outside, those forty-eight units are
    width the four ranks can read across in. So the ask here is one no
    arrangement can meet — thirty units is shorter than a single box.
    """
    with pytest.raises(FitError, match="height_binding"):
        render({**_TALL, "height": 30, "height_binding": True})


def test_a_binding_height_that_can_be_met_draws() -> None:
    """A constraint, not a ban: the same document inside a height it fits renders."""
    assert "<svg" in render({**_TALL, "height": 400, "height_binding": True})


def test_a_height_without_the_binding_flag_stays_advisory() -> None:
    """Which is what `height` says of itself, and what every kind but the charts did."""
    assert "<svg" in render({**_TALL, "height": 80})


def test_a_binding_height_is_what_makes_a_chain_read_across() -> None:
    """The other half of the same lever, end to end — a source sheet's own shape.

    Six steps in one row, 760 by 150. Without a height ceiling the direction
    choice has only width to go on, and a chain going down is one box wide, so it
    fits every canvas and *down* is the only answer any document could get. The
    drawing came out 640 by 658 — a column where the sheet is a band.
    """
    chain = {
        "version": 1,
        "kind": "flow",
        "title": "six steps in one row",
        "width": 760,
        "nodes": [{"id": step, "text": step.title()} for step in ("one", "two", "three", "four")],
        "edges": [
            {"from": "one", "to": "two"},
            {"from": "two", "to": "three"},
            {"from": "three", "to": "four"},
        ],
    }

    def columns(svg: str) -> set[float]:
        """The distinct left edges of the boxes — one of them means a column."""
        root = ElementTree.fromstring(svg)
        return {
            round(float(rect.get("x", "0")), 1)
            for rect in root.iter("{http://www.w3.org/2000/svg}rect")
        }

    def height(svg: str) -> float:
        return float(ElementTree.fromstring(svg).get("viewBox", "").split()[3])

    down = render(chain)
    across = render({**chain, "height": 150, "height_binding": True})

    assert len(columns(down)) == 1, "without a ceiling every box shares one x"
    assert len(columns(across)) == 4, "with one, each step gets its own"
    assert height(across) < height(down)


@pytest.mark.parametrize("name", FIXTURES)
def test_every_kind_sets_its_text_at_the_same_level(name: str) -> None:
    """One type size for the text inside a shape, whatever kind the shape is.

    The other half of the shared canvas, and the same rule seen from the other
    end: a fixed width means two diagrams are scaled alike, and this means they
    were set alike to begin with. Both only matter when the diagrams share a
    page, and neither can be seen in one diagram on its own.

    It is a rule about the reader rather than about the text. `pyramid` and
    `rings` were set a level up for one round, on the reasonable argument that a
    shape whose whole content is five words is titled by them — and a reader with
    the nine kinds in front of them picked those two out at once. Two and a half
    points is plenty to notice side by side.

    Furniture is exempt and stays smaller: an axis's tick labels and an edge's
    label are not the diagram's text, and a chart whose axis numbers matched its
    node text would be a chart shouting its own scale.

    "Inside a shape" is measured rather than assumed, because furniture is not a
    primitive type. A timeline's note sits under the axis and is an annotation on
    an event in exactly the way a tick label is — but an author may bold a word
    in it, so it is a `TextLine` like the text in a box. Where it sits is what
    tells them apart, and where it sits is the thing the rule is actually about.
    """
    theme = load_theme()
    document = load_document(REFERENCE_DIR / f"{name}.json")
    measurer = TextMeasurer(theme.font.stacks())
    drawn = fit(theme, lambda scaled: scene_for(document, scaled, measurer)).value
    shapes = [primitive for primitive in drawn.primitives if isinstance(primitive, Rect | Polygon)]
    levels = {
        primitive.level
        for primitive in drawn.primitives
        if isinstance(primitive, TextLine) and _inside_a_shape(primitive, shapes)
    }
    assert levels <= {BODY_LEVEL}, f"{name} sets its text at {sorted(levels)}"


def _inside_a_shape(line: TextLine, shapes: Sequence[Rect | Polygon]) -> bool:
    """Whether a line's anchor falls within any drawn figure."""
    for shape in shapes:
        if isinstance(shape, Rect):
            bounds = (shape.x, shape.y, shape.x + shape.width, shape.y + shape.height)
        else:
            xs = [x for x, _ in shape.points]
            ys = [y for _, y in shape.points]
            bounds = (min(xs), min(ys), max(xs), max(ys))
        if bounds[0] <= line.x <= bounds[2] and bounds[1] <= line.y <= bounds[3]:
            return True
    return False
