"""Every drawing is framed by the same margin, and no drawing by less.

`tools.clipping` asks whether any ink is *past* the canvas edge. This asks the
question on the other side of that line — how far the ink stops *short* of it —
because for most of this project's life the answer depended on which kind you
happened to be looking at.

There was no outer margin in the theme at all. `emit` set the `viewBox` to the
bounds of the ink and each family then added whatever gutter it happened to add,
out of whichever token was nearest to hand. Measured over these same thirty-three
drawings that came to four answers:

| Kind | Top gutter |
|---|---|
| stack, timeline, funnel, pyramid, matrix without edges, chart without an axis label | **0.0** |
| cycle | **10.5** |
| curve, quadrant, chart with an axis label | **21.9 to 22.4** |
| flow, tree | **24.5** |

Nothing clipped and nothing collided, so no gate in the suite could see it. What
a reader sees is a timeline above a flow chart on one page, the first bleeding to
the edge of the figure while the second sits in a quarter-inch of white — two
figures that are not framed alike, from a theme that had no way to say they
should be.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from clipping import gutters

from drawspec.render import render, render_file
from drawspec.theme import load_theme

REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"

#: How far above the margin a drawing's tightest side may sit before this counts
#: as a family framing itself. Two things are legitimately in here and both are
#: interior to the drawing rather than around it: half a stroke, because `emit`
#: widens the `viewBox` by half the *heaviest* stroke in the scene and a lighter
#: outermost element therefore reads a hair clear of it; and `[edge] clearance`,
#: the gap a `matrix` carrying edges puts around every cell — including the ones
#: on the outside, because taking it off those alone would make the edge cells
#: wider than the middle ones and that family's whole rule is that they are not.
#:
#: Six units is that clearance, and it is the widest of the two. Before this
#: margin existed the same measurement over the same drawings spanned 24.5.
INTERIOR = 6.0

REFERENCES = sorted(REFERENCE.glob("*.json"))

#: The simplest drawing there is, and one that fills the canvas: every side of a
#: stack's outermost layer is its own border, so its gutters are the margin and
#: nothing else. What a theme sets is legible here without any interior to allow
#: for.
FLUSH = {
    "version": 1,
    "kind": "stack",
    "title": "three layers",
    "items": [{"text": "One"}, {"text": "Two"}, {"text": "Three"}],
}


# -- the gate ---------------------------------------------------------------


@pytest.mark.parametrize("document", REFERENCES, ids=lambda path: path.stem)
def test_no_reference_drawing_is_framed_tighter_than_the_theme_margin(document: Path) -> None:
    """The floor, and it is exact.

    `emit` widens the `viewBox` by half the heaviest stroke, so a gutter can only
    ever come out at the margin or above it — never a fraction under. Seven of
    these thirty-three drawings used to come out at zero.
    """
    margin = load_theme().canvas.margin
    measured = gutters(render_file(document, profile="standalone"))
    assert measured, "a reference drawing with no ink in it"
    for side, blank in zip(("left", "top", "right", "bottom"), measured, strict=True):
        assert blank >= margin, f"{document.stem}: {side} gutter is {blank:.2f}, under {margin}"


def test_every_reference_drawing_is_framed_by_the_same_margin() -> None:
    """And the ceiling, which is the half that says the margin is *one* number.

    Read as the tightest side of each drawing, so a diagram narrower than the
    canvas is not counted for the empty paper beside it — that is what the fixed
    canvas is for and it is measured elsewhere. What is left is what each family
    decided on its own, and it should now be nothing.
    """
    theme = load_theme()
    tightest = {
        document.stem: min(gutters(render_file(document, profile="standalone")))
        for document in REFERENCES
    }
    worst = max(tightest.values())
    assert worst - theme.canvas.margin <= INTERIOR, (
        f"the outer gutter spans {min(tightest.values()):.2f} to {worst:.2f}: "
        + ", ".join(f"{name} {blank:.2f}" for name, blank in sorted(tightest.items()))
    )


# -- a theme that names a different one gets it ------------------------------


def _tightest(margin: float) -> float:
    theme = load_theme()
    theme = replace(theme, canvas=replace(theme.canvas, margin=margin))
    return min(gutters(render(FLUSH, theme)))


def test_a_theme_naming_a_wider_margin_gets_it() -> None:
    assert _tightest(30.0) == pytest.approx(30.0)


def test_a_theme_naming_no_margin_draws_flush() -> None:
    """Zero is a house style, not a mistake: a page that pads its own figures
    wants the drawing to end where its ink does."""
    assert _tightest(0.0) == pytest.approx(0.0)


def test_the_margin_goes_around_the_width_rather_than_out_of_it() -> None:
    """Which is the whole reason no drawing's layout budget moved.

    Taken out of the width, a margin would be able to stop an existing document
    rendering — the reference timeline is within ten units of the width its own
    tick spacing demands, and a theme growing a frame would push it over. So the
    canvas comes out as the drawing plus the margin on both sides, and the
    drawing keeps every unit it had.
    """
    theme = load_theme()
    wide = replace(theme, canvas=replace(theme.canvas, margin=40.0))

    assert _canvas(render(FLUSH, theme)) == pytest.approx(
        theme.canvas.width + theme.canvas.margin * 2, abs=1.6
    )
    assert _canvas(render(FLUSH, wide)) == pytest.approx(theme.canvas.width + 80.0, abs=1.6)


def _canvas(svg: str) -> float:
    box = svg.split('viewBox="', 1)[1].split('"', 1)[0]
    return float(box.split()[2])
