"""The clearance pass: no stroke is drawn through a word.

The gate is a number over the whole reference gallery — `collisions == 0` — and
it is checked by `tools.collisions`, which measures against the same font metrics
the layout used rather than asking a browser what it made of the markup. The unit
tests below pin the pass's own arithmetic; the gallery test is the one that would
have caught the three defects this module was written for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from collisions import collisions

from drawspec.clearance import CLEARANCE, MINIMUM_PIECE, cleared
from drawspec.render import render_file
from drawspec.scene import Path as ScenePath
from drawspec.scene import Primitive, Scene, TextRun
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme, load_theme

REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"


@pytest.fixture
def theme() -> Theme:
    return load_theme()


@pytest.fixture
def measurer(theme: Theme) -> TextMeasurer:
    return TextMeasurer(theme.font.stacks())


def _scene(*primitives: Primitive) -> Scene:
    return Scene(width=400.0, height=200.0, primitives=tuple(primitives))


def _label(x: float, y: float, text: str = "if it changed shape") -> TextRun:
    return TextRun("step", x=x, y=y, text=text, anchor="middle")


def test_a_stroke_through_a_word_is_broken(theme: Theme, measurer: TextMeasurer) -> None:
    """The defect itself: a line straight through its own label comes back in two."""
    label = _label(100.0, 100.0)
    line = ScenePath("step", points=((0.0, 96.0), (200.0, 96.0)))
    result = cleared(_scene(label, line), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    assert len(paths) == 2, "one crossed stroke should come back as two pieces"
    assert paths[0].points[0] == (0.0, 96.0)
    assert paths[1].points[-1] == (200.0, 96.0)
    # The gap is a gap: neither piece reaches the other.
    assert paths[0].points[-1][0] < paths[1].points[0][0]


def test_the_gap_clears_the_glyphs(theme: Theme, measurer: TextMeasurer) -> None:
    """A break that stops flush against the text reads as a join, not a break."""
    label = _label(100.0, 100.0)
    line = ScenePath("step", points=((0.0, 96.0), (200.0, 96.0)))
    result = cleared(_scene(label, line), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    width = measurer.advance(label.text, label.font, theme.scale[label.level])
    left, right = 100.0 - width / 2, 100.0 + width / 2
    assert paths[0].points[-1][0] <= left - CLEARANCE + 1.0
    assert paths[1].points[0][0] >= right + CLEARANCE - 1.0


def test_a_stroke_that_misses_every_word_is_untouched(theme: Theme, measurer: TextMeasurer) -> None:
    """Only ink that collides is removed — the pass is not a general rewrite."""
    label = _label(100.0, 100.0)
    line = ScenePath("step", points=((0.0, 180.0), (200.0, 180.0)))
    result = cleared(_scene(label, line), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    assert len(paths) == 1
    assert paths[0] is line, "an uncrossed path should be the same object, not a copy"


def test_an_arrow_head_is_never_broken(theme: Theme, measurer: TextMeasurer) -> None:
    """A gap in a head leaves a mark no reader can name — see `Path.marker`."""
    label = _label(100.0, 100.0)
    head = ScenePath("step", points=((95.0, 96.0), (105.0, 96.0)), marker=True)
    result = cleared(_scene(label, head), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    assert paths == [head]


def test_a_stub_is_dropped_rather_than_drawn(theme: Theme, measurer: TextMeasurer) -> None:
    """A hair of stroke past the end of a word is read as a tick, not a line."""
    label = _label(100.0, 100.0)
    width = measurer.advance(label.text, label.font, theme.scale[label.level])
    # Start the line a whisker left of the cleared box: what survives on that
    # side is shorter than MINIMUM_PIECE.
    start = 100.0 - width / 2 - CLEARANCE - MINIMUM_PIECE / 2
    line = ScenePath("step", points=((start, 96.0), (200.0, 96.0)))
    result = cleared(_scene(label, line), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    assert len(paths) == 1, "the stub on the near side should be dropped"
    assert paths[0].points[-1] == (200.0, 96.0)


def test_two_labels_on_one_segment_leave_three_pieces(theme: Theme, measurer: TextMeasurer) -> None:
    """Clipping box-by-box can only ever produce two pieces. Intervals produce three."""
    first = _label(80.0, 100.0, "one")
    second = _label(220.0, 100.0, "two")
    line = ScenePath("step", points=((0.0, 96.0), (300.0, 96.0)))
    result = cleared(_scene(first, second, line), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    assert len(paths) == 3


def test_a_closed_path_comes_back_open(theme: Theme, measurer: TextMeasurer) -> None:
    """A ring with a bite out of it is not a closed shape, and saying so would fill it."""
    label = _label(100.0, 100.0)
    ring = ScenePath(
        "step", points=((20.0, 96.0), (180.0, 96.0), (180.0, 160.0), (20.0, 160.0)), closed=True
    )
    result = cleared(_scene(label, ring), theme, measurer)

    paths = [p for p in result.primitives if isinstance(p, ScenePath)]
    assert paths, "the ring should survive as pieces"
    assert not any(path.closed for path in paths)


def test_a_rotated_label_is_left_alone(theme: Theme, measurer: TextMeasurer) -> None:
    """The only rotated text is an axis title, outside the plot where no mark travels."""
    label = TextRun("step", x=100.0, y=100.0, text="Cost", anchor="middle", rotate=-90.0)
    line = ScenePath("step", points=((0.0, 96.0), (200.0, 96.0)))
    result = cleared(_scene(label, line), theme, measurer)

    assert [p for p in result.primitives if isinstance(p, ScenePath)] == [line]


def test_a_scene_with_no_text_is_returned_unchanged(theme: Theme, measurer: TextMeasurer) -> None:
    line = ScenePath("step", points=((0.0, 96.0), (200.0, 96.0)))
    scene = _scene(line)
    assert cleared(scene, theme, measurer) is scene


# -- the gate ---------------------------------------------------------------


@pytest.mark.parametrize("document", sorted(REFERENCE.glob("*.json")), ids=lambda p: p.stem)
def test_no_reference_drawing_draws_a_line_through_a_word(document: Path) -> None:
    """The gate. Three of these failed before the clearance pass existed.

    `cycle-review` drew its dashed shortcut through *if it changed shape*, and
    `curve-variance` drew the planned curve through both *Spent* and *Schedule
    variance*.
    """
    found = collisions(render_file(document, profile="standalone"))
    assert found == [], "\n".join(str(collision) for collision in found)
