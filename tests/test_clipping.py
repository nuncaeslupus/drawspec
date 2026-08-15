"""Nothing is drawn outside the canvas.

`tools.collisions` answers *can the word be read*. This answers the question
before it — **is the word on the page** — and it exists because a label drawn past
the `viewBox` passes every other check in this suite: it is in the markup, it
collides with nothing, and a coverage check over the text finds it. It is simply
not there when the file is looked at.

The gate is a number over the whole reference gallery, `clipped == 0`, and it was
written for a defect it did not have to be looking for: a band's name, unbroken
and unmeasured, drawn 148 units off a canvas 171 tall.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from clipping import TOLERANCE, clipped

from drawspec.render import render_file

REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"

#: A drawing whose only content is one word, placed by hand so a test can put it
#: where it wants without going through a layout that would refuse to.
CANVAS = 200.0


def _svg(*, x: float, y: float, text: str = "outside", rotate: float = 0.0) -> str:
    turn = f' transform="rotate({rotate} {x} {y})"' if rotate else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}">'
        f'<text x="{x}" y="{y}" font-family="\'DejaVu Sans\', sans-serif" '
        f'font-size="10" text-anchor="middle"{turn}>{text}</text></svg>'
    )


def test_a_word_inside_the_canvas_is_not_reported() -> None:
    assert clipped(_svg(x=CANVAS / 2, y=CANVAS / 2)) == []


def test_a_word_past_the_right_edge_is_reported_with_how_far() -> None:
    (found,) = clipped(_svg(x=CANVAS, y=CANVAS / 2))

    assert found.text == "outside"
    assert found.right > 0, "half the word is past the edge"
    assert "right by" in str(found)


def test_a_word_above_the_canvas_is_reported() -> None:
    """A baseline on the edge puts the whole ascent outside it."""
    (found,) = clipped(_svg(x=CANVAS / 2, y=0.0))

    assert found.top > 0


def test_a_turned_word_is_measured_turned() -> None:
    """The case that overflowed furthest: on its side, a name is long in the
    direction the canvas is short. Measured flat, this one fits."""
    long_enough = "a name too long to stand up in two hundred units of canvas"
    flat = clipped(_svg(x=CANVAS / 2, y=CANVAS / 2, text=long_enough))
    turned = clipped(_svg(x=CANVAS / 2, y=CANVAS / 2, text=long_enough, rotate=-90.0))

    assert [item.right > 0 for item in flat] == [True]
    assert [(item.top > 0, item.bottom > 0) for item in turned] == [(True, True)]


def test_a_stroke_carries_the_paint_around_its_centreline() -> None:
    """The same arithmetic `collisions` does: a centreline on the edge still puts
    half the stroke's weight outside it."""
    thick = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}">'
        f'<path d="M 10 {CANVAS} L 100 {CANVAS}" stroke="currentColor" stroke-width="8"/></svg>'
    )
    (found,) = clipped(thick)

    assert found.bottom == pytest.approx(4.0)


def test_ink_flush_against_the_edge_is_not_a_clipped_drawing() -> None:
    """The `viewBox` is widened by half the heaviest stroke, so a shape drawn on
    the edge keeps its whole outline. That is a full drawing, not a clipped one."""
    flush = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}">'
        f'<path d="M 0 0 L {CANVAS} 0" stroke="currentColor" stroke-width="1"/></svg>'
    )
    assert clipped(flush) == []
    assert TOLERANCE >= 0.5


def test_a_document_with_no_viewbox_is_an_error_rather_than_a_pass() -> None:
    with pytest.raises(ValueError, match="viewBox"):
        clipped('<svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="0">x</text></svg>')


# -- the gate ---------------------------------------------------------------


@pytest.mark.parametrize("document", sorted(REFERENCE.glob("*.json")), ids=lambda p: p.stem)
def test_no_reference_drawing_puts_ink_outside_its_canvas(document: Path) -> None:
    found = clipped(render_file(document, profile="standalone"))
    assert found == [], "\n".join(str(item) for item in found)
