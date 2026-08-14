"""Turning a sized `Box` into `Scene` primitives — shared by every kind.

Every rendering family arrives at the same place: it has boxes with text in them
and it needs primitives. Doing that once here is what keeps the families from
each inventing their own idea of where a label sits, and it is the reason a fifth
family would cost almost nothing.

Two decisions live here rather than in each family:

**The shape comes from the role.** A `decision` is a diamond because the theme
says so, and the caller does not choose a primitive type — it asks for the box to
be drawn. Adding a shape to the vocabulary means adding a case here, once.

**Lines are centred horizontally.** Ragged-right text in a box that was sized to
its own content reads as a mistake, and a centred line needs the line's measured
width to place its first span — which is exactly what `TextBlock` carries.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box
from drawspec.scene import Ellipse, Polygon, Primitive, Rect, Scene, TextLine, TextSpan, moved
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import wrap
from drawspec.theme import Theme


def box_primitives(box: Box, theme: Theme, measurer: TextMeasurer) -> tuple[Primitive, ...]:
    """The outline of `box` followed by its text, in paint order."""
    return (*outline(box, theme), *text_runs(box, theme, measurer))


def outline(box: Box, theme: Theme) -> tuple[Primitive, ...]:
    """The one primitive that draws `box`'s shape, or nothing for `none`.

    Raises:
        KeyError: the theme gives this box's role a shape drawspec cannot draw.
    """
    shape = theme.roles[box.role].shape
    if shape == "none":
        return ()
    if shape in ("rect", "pill"):
        # The emitter reads the role's shape to decide the corner radius, so a
        # pill and a rect are the same primitive here.
        return (Rect(box.role, x=box.x, y=box.y, width=box.width, height=box.height),)
    if shape == "ellipse":
        return (
            Ellipse(
                box.role,
                cx=box.x + box.width / 2,
                cy=box.y + box.height / 2,
                rx=box.width / 2,
                ry=box.height / 2,
            ),
        )
    if shape == "diamond":
        middle_x = box.x + box.width / 2
        middle_y = box.y + box.height / 2
        return (
            Polygon(
                box.role,
                points=(
                    (middle_x, box.y),
                    (box.x + box.width, middle_y),
                    (middle_x, box.y + box.height),
                    (box.x, middle_y),
                ),
            ),
        )
    raise KeyError(f"no primitive for shape {shape!r}")


def text_runs(box: Box, theme: Theme, measurer: TextMeasurer) -> tuple[TextLine, ...]:
    """One line per line, anchored at the box's centre.

    The centring is asked for rather than computed: drawspec measured this text
    against the family the theme *names*, and a reader without that family gets a
    substitute whose widths differ. A line placed by its measured left edge is
    then off centre by half that difference in every box on the page — which is
    what a phone shows and the machine that drew it never does. Handing the
    renderer the centre and the words leaves the arithmetic to whoever has the
    font, and drawspec keeps the decisions it can be right about: the words, the
    break, and where the line sits down the box.

    `measurer` is unused now and kept in the signature because a caller passing
    it is passing the same measurer the box was sized with, which is the property
    that matters if any of this needs measuring again.
    """
    return tuple(
        TextLine(
            box.role,
            x=(box.usable_left + box.usable_right) / 2,
            y=baseline,
            spans=tuple(
                TextSpan(text=span.text, font=span.font, weight=span.weight)
                for span in line.spans
                if span.text
            ),
            level=box.level,
            anchor="middle",
        )
        for line, baseline in zip(box.block.lines, box.baselines(), strict=True)
        if line.spans
    )


def line_bounds(line: TextLine, theme: Theme, measurer: TextMeasurer) -> tuple[float, float]:
    """The left and right edge of a laid-out line, as drawspec measured it.

    The line itself carries an anchor rather than an extent — that is the point
    of it — so this is where "does the text fit its box" gets its numbers. It is
    drawspec's own answer, in drawspec's own fonts: a reader whose page
    substitutes will see a slightly different width, centred on the same point.
    """
    size = theme.scale[line.level]
    width = sum(
        measurer.measure(span.text, span.font, size, span.weight).width for span in line.spans
    )
    starts = {"start": line.x, "middle": line.x - width / 2, "end": line.x - width}
    left = starts[line.anchor]
    return left, left + width


#: The role a diagram-level caption is drawn in. `note` is the vocabulary's word
#: for an aside, which is what a caption is — and it means a theme that wants
#: captions quieter says so once, in the place it says everything else.
CAPTION_ROLE: Final = "note"


def captioned(scene: Scene, caption: str, theme: Theme, measurer: TextMeasurer) -> Scene:
    """`scene` with `caption` set outside the drawing, above it or below it.

    The reviewer asked for this on four drawings and then in general — *"do we
    have options to add texts outside graphs? For example, above or below"* — and
    the answer had been no. `note` was accepted on four objects and drawn by one
    family, which is worse than not having it: a field an author can write that
    has no effect is a setting they believe they made.

    A caption is not that field, and the distinction is the useful part. A note
    belongs to *one element*; a caption belongs to the whole diagram — the units
    an axis is in, a condition that holds throughout, the sentence the original
    wrote beside the figure rather than inside it. Neither can stand in for the
    other, so both exist and each is drawn where it means something.

    Broken to the canvas rather than to the drawing: a caption under a narrow
    diagram would otherwise wrap at the diagram's width for no reason a reader
    could see. It is then centred on whichever of the two is wider, and a caption
    that turns out to need more room than the drawing widens the scene rather
    than hanging off it — `centred` puts the pair on the canvas together, and it
    can only do that if the scene's width covers everything in it.

    Which side it goes is `[canvas] caption`, because *this text belongs to the
    diagram* is what the author knows and *captions go under figures* is what a
    house style knows.

    Raises:
        FitError: the caption cannot be broken to the canvas width — named as the
            caption, because it is raised inside the elastic fit like everything
            else and the fit's own message only knows that *something* would not
            go. An author whose diagram was fine and whose caption had one
            unbreakable word in it would otherwise be told to restructure the
            diagram.
    """
    if not caption:
        return scene
    gap = theme.box.padding.top
    try:
        block = wrap(caption, theme.canvas.width, measurer, theme=theme, level="label")
    except FitError as error:
        raise FitError(f"the caption {caption[:40]!r} does not fit the canvas: {error}") from None

    width = max(scene.width, block.width)
    band = block.height + gap
    above = theme.canvas.caption == "above"
    top = gap if above else scene.height + gap
    runs = tuple(
        TextLine(
            CAPTION_ROLE,
            x=width / 2,
            y=top + block.baseline(index),
            spans=tuple(
                TextSpan(text=span.text, font=span.font, weight=span.weight)
                for span in line.spans
                if span.text
            ),
            level="label",
            anchor="middle",
        )
        for index, line in enumerate(block.lines)
        if line.spans
    )
    # The drawing moves down to make room for a caption above it, and across if
    # the caption made the scene wider than the drawing was.
    across = (width - scene.width) / 2
    down = band if above else 0.0
    drawing = tuple(moved(primitive, across, down) for primitive in scene.primitives)
    return replace(scene, width=width, height=scene.height + band, primitives=(*drawing, *runs))


__all__ = ["CAPTION_ROLE", "box_primitives", "captioned", "line_bounds", "outline", "text_runs"]
