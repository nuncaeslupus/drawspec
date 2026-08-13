"""Shape kinds: `pyramid` and `rings`. Parametric geometry, not graph theory.

Both draw their own outline — a pyramid level is a trapezoid and a ring is a
circle, and neither is a node shape — so both size their text with an explicit
`shape` rather than the role's, and place it themselves. What they share with
every other family is `kinds.common.text_runs`, so a label is centred the same
way here as anywhere else.

The interesting constraint is the one the requirements single out, and it is the
same in both: **the usable width is not the width of the shape, it is the width
of the shape where the text actually is.**

* A pyramid level is narrowest at its *top* edge, so that is what its text has to
  fit. Fitting the level's average or bottom width is how text ends up crossing a
  sloped side.
* A ring's label sits in the band between its own circle and the next one in, and
  a circle is narrowest at the top of that band.

A ring set fills the canvas width; a pyramid does not, and that difference is
the one judgement in this file. Rings get wider as they get more concentric, so
the canvas is the only width that gives the innermost one room. A pyramid's base
is the widest thing in it, so a base at the canvas width leaves a shape three or
four times wider than it is tall — a flight of steps. Its base is derived from
its labels, with the canvas as a ceiling and `centred` putting the result in the
middle of the page. Both are still a single sizing pass: the width is settled
before any text is wrapped, so there is no circularity between how wide the
figure is and how its text breaks.
"""

from __future__ import annotations

import math
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import text_runs
from drawspec.scene import Ellipse, Polygon, Primitive, Scene
from drawspec.schema import Document, Item
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: A pyramid's top level is this fraction of the base. `1 / (n + 1)` for `n`
#: levels, which is what makes the width progression constant *and* leaves the
#: apex flat: a true point has no width, so nothing could be written in it.
#:
#: Level `i` therefore spans `(i + 1) / (n + 1)` of the base at its top edge and
#: `(i + 2) / (n + 1)` at its bottom.
PYRAMID_STEPS: Final = 1

#: How tall a pyramid should be, as a fraction of its base. What the shape wants
#: to look like, granted by `_pyramid` only as far as `PYRAMID_FILL` allows.
#:
#: Both this and the base being derived from the labels are answers to the same
#: complaint, and it took two rounds to find the right lever. A pyramid drawn to
#: the canvas width is three or four times wider than it is tall whatever this
#: number says, because its height is levels-worth-of-text and its base is the
#: whole page: the aspect can only be honoured by making the levels taller than
#: their text, which is what left the type looking lost. Narrowing the base
#: instead buys the same slope for nothing.
PYRAMID_ASPECT: Final = 0.55

#: How much taller than its own text a pyramid level may be, in service of the
#: aspect above. The limit on paying for a shape with empty band: past this the
#: text reads as marooned in the middle of a stripe rather than as its label.
PYRAMID_FILL: Final = 1.8

#: The narrowest base a pyramid may have, as a share of the canvas. A pyramid of
#: one-word levels would otherwise shrink to the width of its longest word.
PYRAMID_MIN_SHARE: Final = 0.45

#: The type level a pyramid level and a ring band are set at.
#:
#: `body`, which is what every other kind sets its boxes in, and the reason is a
#: rule about the page rather than about these two shapes. It was `heading` for
#: one round — defensibly: a shape whose whole content is five words is titled by
#: them rather than described by them — and a reader with the nine kinds in front
#: of them picked the two out immediately. Two point five of a difference is
#: plenty to notice when the diagrams sit in one document, and *"all drawings
#: should be read the same in the same page"* outranks a per-kind reading of what
#: the text is doing. A shape whose text looks lost is a shape that is too big;
#: shrink the shape.
SHAPE_LEVEL: Final = "body"


def shape_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a shape-kind document to a `Scene`.

    Raises:
        DrawspecError: `document.kind` is not a shape kind.
        FitError: a level's or a ring's text cannot fit the span it has.
    """
    if document.kind == "pyramid":
        return _pyramid(document, theme, measurer)
    if document.kind == "rings":
        return _rings(document, theme, measurer)
    raise DrawspecError(f"{document.kind!r} is not a shape kind")


def _canvas_width(document: Document, theme: Theme) -> float:
    return document.width if document.width else theme.canvas.width


def _label(
    item: Item, theme: Theme, measurer: TextMeasurer, span: float, where: str, why: str
) -> Box:
    """Size one label to `span`, or refuse with a message naming what to do."""
    if span <= theme.box.padding.horizontal:
        raise FitError(
            f"{where} is {span:.0f} wide at its narrowest, which the theme's padding "
            f"alone fills. {why}"
        )
    try:
        return size_box(
            item.text,
            theme=theme,
            measurer=measurer,
            role=item.role,
            level=SHAPE_LEVEL,
            max_width=span,
            # The family draws the outline; the text is sized in a plain
            # rectangle inside the span the family worked out for it.
            shape="rect",
        )
    except FitError as error:
        raise FitError(f"{where}: {error} {why}") from None


# ---------------------------------------------------------------------------
# pyramid
# ---------------------------------------------------------------------------


def _pyramid(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Levels of equal height, a constant width progression, text inside the slope."""
    levels = document.levels
    count = len(levels)
    if count < 1:
        raise DrawspecError("a pyramid needs at least one level")

    canvas = _canvas_width(document, theme)
    steps = count + PYRAMID_STEPS
    # A pyramid is the one kind that should *not* fill the canvas: its base is
    # the widest thing in it, and a base as wide as everything else on the page
    # leaves a shape three times wider than it is tall — a flight of steps rather
    # than a pyramid. So the base comes from the labels and the canvas is a
    # ceiling, with the drawing centred in whatever is left over.
    width = _pyramid_base(levels, theme, measurer, canvas, steps)

    # The narrowest span of level i is its *top* edge. That is what its text has
    # to fit — fitting the average or the bottom is how text crosses the slope.
    boxes = [
        _label(
            item,
            theme,
            measurer,
            width * (index + 1) / steps,
            f"pyramid level {index + 1} of {count} ({item.text[:32]!r})",
            "The top level is the narrowest, so it takes the shortest label — "
            "shorten it, use fewer levels, or give the diagram more width.",
        )
        for index, item in enumerate(levels)
    ]

    # Equal height: every level the same, sized by the tallest label, so no level
    # reads as more important than another.
    #
    # Between the two numbers below, the shape is as tall as it can be *without
    # leaving its text swimming*. The aspect is what a pyramid should look like;
    # the fill is the limit on paying for that look with empty band. When the
    # labels are short the aspect wins and the drawing is a pyramid; when they
    # are long enough to need the whole canvas the fill wins, and the shape goes
    # flat rather than the type going small — which is the trade the last round
    # got backwards.
    tallest = max(box.height for box in boxes)
    level_height = max(tallest, min(width * PYRAMID_ASPECT / count, tallest * PYRAMID_FILL))
    height = level_height * count

    primitives: list[Primitive] = []
    for index, (item, box) in enumerate(zip(levels, boxes, strict=True)):
        top = index * level_height
        top_width = width * (index + 1) / steps
        bottom_width = width * (index + 2) / steps
        middle = width / 2
        primitives.append(
            Polygon(
                item.role,
                points=(
                    (middle - top_width / 2, top),
                    (middle + top_width / 2, top),
                    (middle + bottom_width / 2, top + level_height),
                    (middle - bottom_width / 2, top + level_height),
                ),
            )
        )
        placed = box.resized(width=top_width, height=level_height).moved_to(
            middle - max(top_width, box.width) / 2, top
        )
        primitives.extend(text_runs(placed, theme, measurer))

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _pyramid_base(
    levels: tuple[Item, ...],
    theme: Theme,
    measurer: TextMeasurer,
    canvas: float,
    steps: int,
) -> float:
    """The narrowest base at which every level's label sits on one line.

    Sized from the level that has to reach furthest, which is not always the
    apex: level `i` gets `(i + 1) / steps` of the base at its top edge, so a
    short label at the top can ask for more base than a long one at the bottom.
    Each level's demand is its own one-line width divided by its share, and the
    base is the largest of them.

    One line rather than the narrowest base a label could be *wrapped* into,
    because wrapping is unbounded: a search for the narrowest fitting base would
    happily return a spire with every label broken into three. Wrapping is what
    happens when the ceiling is reached, not a way to get further under it.

    Bounded at both ends. The canvas is the ceiling — a pyramid that wants more
    goes back to wrapping inside it, which is the behaviour every other kind has
    at the same point — and a share of the canvas is the floor, so a pyramid of
    one-word levels is still a diagram rather than a caption with a hat on.
    """
    demands = [
        size_box(
            item.text,
            theme=theme,
            measurer=measurer,
            role=item.role,
            level=SHAPE_LEVEL,
            max_width=canvas,
            shape="rect",
        ).width
        * steps
        / (index + 1)
        for index, item in enumerate(levels)
    ]
    return min(canvas, max(max(demands, default=0.0), canvas * PYRAMID_MIN_SHARE))


# ---------------------------------------------------------------------------
# rings
# ---------------------------------------------------------------------------


def _rings(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Concentric circles, each label in its own band, the innermost centred."""
    rings = document.rings
    count = len(rings)
    if count < 1:
        raise DrawspecError("a rings diagram needs at least one ring")

    extent = _canvas_width(document, theme)
    radius = extent / 2
    centre = radius
    # Equal radial steps, outermost first, so the bands read as a progression
    # rather than as an accident of how many there are.
    radii = [radius * (count - index) / count for index in range(count)]

    primitives: list[Primitive] = [
        Ellipse(item.role, cx=centre, cy=centre, rx=ring, ry=ring)
        for item, ring in zip(rings, radii, strict=True)
    ]

    for index, (item, ring) in enumerate(zip(rings, radii, strict=True)):
        innermost = index == count - 1
        if innermost:
            # The one label that is centred — it has no band, only its own circle.
            span = ring * 2 - theme.box.padding.horizontal
            box = _label(
                item, theme, measurer, span, f"the innermost ring ({item.text[:32]!r})", ""
            )
            placed = box.resized(width=span).moved_to(centre - span / 2, centre - box.height / 2)
            primitives.extend(text_runs(placed, theme, measurer))
            continue

        inner = radii[index + 1]
        band = ring - inner
        # The label sits in the upper band, clear of its own arc — "shifted
        # downwards so it does not touch its own circle". Vertically centred in
        # the band, which is also where the band is at its widest.
        label_centre = centre - (ring + inner) / 2
        # A circle is narrowest at the top of the band, so that is the width the
        # label has to fit: the half-chord at the label's own top edge.
        span = 2 * _half_chord(ring, (ring + inner) / 2 + band / 4) - theme.box.padding.horizontal
        box = _label(
            item,
            theme,
            measurer,
            span,
            f"ring {index + 1} of {count} ({item.text[:32]!r})",
            "An outer ring's band is narrow near the top — shorten the label, use "
            "fewer rings, or give the diagram more width.",
        )
        if box.height > band - theme.box.padding.vertical:
            raise FitError(
                f"ring {index + 1} of {count} needs {box.height:.0f} of height and its "
                f"band is {band:.0f}. Use fewer rings, shorten the label, or give the "
                f"diagram more width."
            )
        placed = box.resized(width=span).moved_to(centre - span / 2, label_centre - box.height / 2)
        primitives.extend(text_runs(placed, theme, measurer))

    return Scene(
        width=extent,
        height=extent,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _half_chord(radius: float, offset: float) -> float:
    """Half the width of a circle at `offset` from its centre line."""
    return math.sqrt(max(radius**2 - offset**2, 0.0))


__all__ = [
    "PYRAMID_ASPECT",
    "PYRAMID_FILL",
    "PYRAMID_MIN_SHARE",
    "PYRAMID_STEPS",
    "SHAPE_LEVEL",
    "shape_scene",
]
