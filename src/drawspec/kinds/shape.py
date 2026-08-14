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

**Neither shape fills the canvas.** Both are sized from their own labels, with
the canvas as a ceiling rather than a target and `centred` putting the result in
the middle of the page. A shape drawn to the full width is mostly shape: the
type is the same size as everywhere else in the document, but it is a smaller
part of what the reader is looking at, and it reads as too small. The fix is to
shrink the drawing, never to grow the type — the page has one type size.

Both are still a single sizing pass: the extent is settled before any text is
wrapped, so there is no circularity between how wide the figure is and how its
text breaks. What each asks of its width differs — a pyramid's base is the
widest thing in it, a ring's band is narrowest at the top — but the shape of the
answer is the same, and `_pyramid_base` and `_rings_extent` are the two halves
of it.
"""

from __future__ import annotations

import math
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import text_runs
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene
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

#: The smallest a ring set may be drawn, as a share of the canvas. The same floor
#: as a pyramid's base and for the same reason: a set of one-word rings would
#: otherwise close down to a coin.
RINGS_MIN_SHARE: Final = 0.45

#: How deep a funnel's mouth is, as a fraction of its throat. Not zero: a funnel
#: that closes to a point has no last stage to write in, which is the same reason
#: a pyramid's apex is flat.
FUNNEL_TAPER: Final = 0.4

#: The shallowest a funnel may be drawn, as a fraction of its width. A funnel of
#: one-word stages would otherwise come out a ruled line with words along it.
FUNNEL_MIN_DEPTH: Final = 0.16

#: The role a funnel's gates are drawn in. `weak` — dashed, headless — because a
#: gate is a threshold rather than a wall: the band is continuous and something
#: passes through it.
GATE_ROLE: Final = "weak"

#: Bisection steps used to size a ring set. Enough to settle a canvas-sized
#: interval well below a unit of the coordinate system.
_BISECTIONS: Final = 24

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
    if document.kind == "funnel":
        return _funnel(document, theme, measurer)
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
# funnel
# ---------------------------------------------------------------------------


def _funnel(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Stages narrowing to an outcome, tapering down the page or across it.

    Which way is `[funnel] direction`, and it is the theme's because it is a
    question about the drawing rather than about the subject. The corpus review
    asked for the vertical one and named the reason: *"it says embut, which
    should look as vertical — couldn't we have an inverted pyramid for these
    cases?"* A funnel is a thing you pour into, and drawn sideways it stops being
    the thing the word names.

    The dividers are drawn in the theme's `weak` edge role rather than as the
    shared sides of separate polygons. A gate is a threshold, not a wall: the
    band is continuous and something passes through it, which is what a stage
    boundary in a funnel means and what a solid line would deny.
    """
    if theme.funnel.direction == "down":
        return _funnel_down(document, theme, measurer)
    return _funnel_right(document, theme, measurer)


def _funnel_down(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """The inverted pyramid: full width at the mouth, narrowing to the outcome.

    Exactly the pyramid's geometry with the progression reversed, which is why
    there is no third family here — the plan's own reading, and it holds: a
    pyramid's level `i` spans `(i + 1) / steps` of the base at its top and
    `(i + 2) / steps` at its bottom, and a funnel's spans the same two the other
    way round. What differs is which edge the text has to fit, and it is the
    narrow one either way: a pyramid level's *top*, a funnel stage's *bottom*.

    The width is the canvas, not something the labels buy. A funnel that narrowed
    its mouth to suit its labels would be a wedge, and the mouth is the one part
    of a funnel a reader already knows the size of.
    """
    stages = document.stages
    count = len(stages)
    if count < 1:
        raise DrawspecError("a funnel needs at least one stage")

    width = _canvas_width(document, theme)

    def span(depth: int) -> float:
        """The band's width `depth` stages down, from the mouth to the outcome."""
        return width * (1 - (1 - FUNNEL_TAPER) * depth / count)

    boxes = [
        _label(
            item,
            theme,
            measurer,
            span(index + 1) - theme.box.padding.horizontal,
            f"funnel stage {index + 1} of {count} ({item.text[:32]!r})",
            "The last stage is the narrowest, so it takes the shortest label — "
            "shorten it, use fewer stages, or give the diagram more width.",
        )
        for index, item in enumerate(stages)
    ]

    # Equal stage heights, for the reason a pyramid's levels are equal: a stage
    # taller than its neighbours reads as a longer or more important step, which
    # is not what the author said. Between the two numbers, the shape is as tall
    # as it can be without leaving its text swimming in it.
    tallest = max(box.height for box in boxes)
    stage_height = max(tallest, min(width * PYRAMID_ASPECT / count, tallest * PYRAMID_FILL))
    height = stage_height * count
    middle = width / 2

    primitives: list[Primitive] = [
        Polygon(
            stages[0].role,
            points=(
                (middle - span(0) / 2, 0.0),
                (middle + span(0) / 2, 0.0),
                (middle + span(count) / 2, height),
                (middle - span(count) / 2, height),
            ),
        )
    ]
    for index in range(1, count):
        gate = index * stage_height
        primitives.append(
            Path(
                GATE_ROLE,
                points=((middle - span(index) / 2, gate), (middle + span(index) / 2, gate)),
            )
        )
    for index, box in enumerate(boxes):
        top = index * stage_height
        narrow = span(index + 1)
        placed = box.resized(width=narrow, height=stage_height).moved_to(
            middle - max(narrow, box.width) / 2, top
        )
        primitives.extend(text_runs(placed, theme, measurer))

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("taper", f"{FUNNEL_TAPER}"), ("direction", "down")),
    )


def _funnel_right(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """The pyramid lying down: full width, tapering left to right.

    What changes from the vertical one is which way the shape gives when the text
    does not fit. Tapering down, the mouth is the canvas and the labels buy
    *height*; tapering right, the length is the canvas and the labels buy
    **depth** — and it fills the canvas width either way, because a funnel that
    did not would be a wedge with nowhere to put the stages.
    """
    stages = document.stages
    count = len(stages)
    if count < 1:
        raise DrawspecError("a funnel needs at least one stage")

    width = _canvas_width(document, theme)
    slice_width = width / count
    boxes = [
        _label(
            item,
            theme,
            measurer,
            slice_width - theme.box.padding.horizontal,
            f"stage {index + 1} of {count} ({item.text[:32]!r})",
            "Shorten the label, use fewer stages, or give the diagram more width.",
        )
        for index, item in enumerate(stages)
    ]
    height = _funnel_height(boxes, count, width, theme)

    def edge(x: float) -> float:
        """Half the band's depth at `x` — it tapers linearly from left to right."""
        share = x / width
        return height * (1 - (1 - FUNNEL_TAPER) * share) / 2

    middle = height / 2
    primitives: list[Primitive] = [
        Polygon(
            stages[0].role,
            points=(
                (0.0, middle - edge(0.0)),
                (width, middle - edge(width)),
                (width, middle + edge(width)),
                (0.0, middle + edge(0.0)),
            ),
        )
    ]
    for index in range(1, count):
        gate = index * slice_width
        primitives.append(
            Path(GATE_ROLE, points=((gate, middle - edge(gate)), (gate, middle + edge(gate))))
        )
    for index, box in enumerate(boxes):
        # The right edge is the narrowest part of a stage, so that is what its
        # text has to fit — the same rule as a pyramid level's top edge.
        span = edge((index + 1) * slice_width) * 2 - theme.box.padding.vertical
        if box.height > span:
            raise FitError(
                f"stage {index + 1} of {count} needs {box.height:.0f} of depth and the "
                f"band is {span:.0f} where it ends. Shorten the label, use fewer "
                f"stages, or give the diagram more width."
            )
        placed = box.resized(width=slice_width).moved_to(
            index * slice_width, middle - box.height / 2
        )
        primitives.extend(text_runs(placed, theme, measurer))

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("taper", f"{FUNNEL_TAPER}"), ("direction", "right")),
    )


def _funnel_height(boxes: list[Box], count: int, width: float, theme: Theme) -> float:
    """The shallowest band every stage's text still fits in where it ends.

    Each stage asks for the height at which the band, already tapered to where
    that stage ends, still holds its label. The deepest demand wins; the floor
    keeps a funnel of one-word stages from becoming a rule with words on it.
    """
    demands = [
        (box.height + theme.box.padding.vertical) / (1 - (1 - FUNNEL_TAPER) * (index + 1) / count)
        for index, box in enumerate(boxes)
    ]
    return max(max(demands, default=0.0), width * FUNNEL_MIN_DEPTH)


# ---------------------------------------------------------------------------
# rings
# ---------------------------------------------------------------------------


def _rings(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Concentric circles, each label in its own band, the innermost centred."""
    rings = document.rings
    count = len(rings)
    if count < 1:
        raise DrawspecError("a rings diagram needs at least one ring")

    canvas = _canvas_width(document, theme)
    extent = _rings_extent(rings, theme, measurer, canvas)
    centre = extent / 2
    radii = _ring_radii(extent, count)

    primitives: list[Primitive] = [
        Ellipse(item.role, cx=centre, cy=centre, rx=ring, ry=ring)
        for item, ring in zip(rings, radii, strict=True)
    ]

    for index, (item, ring) in enumerate(zip(rings, radii, strict=True)):
        innermost = index == count - 1
        if innermost:
            # The one label that is centred — it has no band, only its own circle.
            span = _ring_span(radii, index) - theme.box.padding.horizontal
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
        span = _ring_span(radii, index) - theme.box.padding.horizontal
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


def _ring_radii(extent: float, count: int) -> list[float]:
    """Equal radial steps, outermost first.

    Equal steps so the bands read as a progression rather than as an accident of
    how many there are.
    """
    radius = extent / 2
    return [radius * (count - index) / count for index in range(count)]


def _ring_span(radii: list[float], index: int) -> float:
    """The width ring `index` offers its label, before the box's own padding.

    A circle is narrowest at the top of the band, so that — not the band's widest
    point — is what the label has to fit. The innermost ring has no band, only
    its own circle, and its label is centred, so its span is the diameter.

    Every term here is linear in the extent, which is what lets `_rings_extent`
    invert it: the span at any size is the span at size one, scaled.
    """
    ring = radii[index]
    if index == len(radii) - 1:
        return ring * 2
    inner = radii[index + 1]
    band = ring - inner
    return 2 * _half_chord(ring, (ring + inner) / 2 + band / 4)


def _rings_extent(
    rings: tuple[Item, ...], theme: Theme, measurer: TextMeasurer, canvas: float
) -> float:
    """The smallest circle every label still fits in, found by bisection.

    A ring set drawn to the canvas width is mostly circle: the type is the same
    size as everywhere else in the document, but it is a smaller part of what the
    reader is looking at, so it reads as too small. Filling the width was
    justified by rings needing room to nest — which is true of the *ratio*
    between the bands, not of the absolute size.

    Bisection rather than the closed form `_pyramid_base` uses, because here
    wrapping is a real lever and there it is not. A ring's band is a fixed
    fraction of the extent in *both* directions, so breaking a label over two
    lines trades width the band is short of for depth it has — and the trade
    terminates, because the depth runs out. A pyramid level has no such bound:
    its height comes from its own text, so a level always has room for one more
    line, and searching for the narrowest base that still fits returns a spire.

    Monotone in the extent — a bigger circle gives every band both more span and
    more depth — so bisection is well defined. `RINGS_MIN_SHARE` of the canvas is
    the floor and the canvas is the ceiling; a set that does not fit even there
    is returned at the ceiling, so `_rings` raises the `FitError` that can say
    which ring failed and what to do about it.
    """
    floor = canvas * RINGS_MIN_SHARE
    if not _rings_fit(rings, theme, measurer, canvas):
        return canvas
    if _rings_fit(rings, theme, measurer, floor):
        return floor
    low, high = floor, canvas
    for _ in range(_BISECTIONS):
        middle = (low + high) / 2
        if _rings_fit(rings, theme, measurer, middle):
            high = middle
        else:
            low = middle
    return high


def _rings_fit(
    rings: tuple[Item, ...], theme: Theme, measurer: TextMeasurer, extent: float
) -> bool:
    """Does every label fit its own band at this extent?

    Deliberately the same arithmetic as `_rings` — the same span, the same depth,
    the same margin — so that "fits" here and "does not raise `FitError`" there
    are the same question. A predicate that is merely close would pick an extent
    the drawing then refuses.
    """
    count = len(rings)
    radii = _ring_radii(extent, count)
    for index, item in enumerate(rings):
        span = _ring_span(radii, index) - theme.box.padding.horizontal
        if span <= theme.box.padding.horizontal:
            return False
        try:
            box = size_box(
                item.text,
                theme=theme,
                measurer=measurer,
                role=item.role,
                level=SHAPE_LEVEL,
                max_width=span,
                shape="rect",
            )
        except FitError:
            return False
        depth = radii[index] * 2 if index == count - 1 else radii[index] - radii[index + 1]
        if box.height > depth - theme.box.padding.vertical:
            return False
    return True


def _half_chord(radius: float, offset: float) -> float:
    """Half the width of a circle at `offset` from its centre line."""
    return math.sqrt(max(radius**2 - offset**2, 0.0))


__all__ = [
    "FUNNEL_MIN_DEPTH",
    "FUNNEL_TAPER",
    "GATE_ROLE",
    "PYRAMID_ASPECT",
    "PYRAMID_FILL",
    "PYRAMID_MIN_SHARE",
    "PYRAMID_STEPS",
    "RINGS_MIN_SHARE",
    "SHAPE_LEVEL",
    "shape_scene",
]
