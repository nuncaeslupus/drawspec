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

import math
from dataclasses import replace
from typing import Final

from drawspec.errors import FitError
from drawspec.filetree import STATUSES
from drawspec.geometry import CYLINDER_CAP, PARALLELOGRAM_SLANT, SUBROUTINE_INSET, Box, span_at
from drawspec.scene import (
    Ellipse,
    Path,
    Polygon,
    Primitive,
    Rect,
    Scene,
    TextLine,
    TextRun,
    TextSpan,
    moved,
)
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import wrap
from drawspec.theme import Theme


def box_primitives(box: Box, theme: Theme, measurer: TextMeasurer) -> tuple[Primitive, ...]:
    """The outline of `box`, its lead rule if it has one, then its text."""
    return (*outline(box, theme), *lead_rule(box), *text_runs(box, theme, measurer))


def lead_rule(box: Box) -> tuple[Primitive, ...]:
    """The line between a box's lead and its detail, or nothing.

    Only `[box] lead = "rule"` produces one — see `theme.BoxStyle.lead`. The band
    it sits in was reserved when the text was measured, so this is placement
    rather than arithmetic: whether there is a rule, and where, is the block's
    answer and not a second opinion about it.

    It runs **edge to edge**, which in a `rect` is what a hand-drawn class box
    does and is the whole look. That is a question about where the outline is at
    one height rather than about the text column, so it is asked as one:
    `span_at` gives the shape's own width at the rule's depth, which stops the
    line on the two sloped sides of a diamond and inside the cap of a pill
    instead of coming out of them.
    """
    offset = box.block.rule_offset
    if offset is None:
        return ()
    y = box.block_top + offset
    half = span_at(box.shape, box.width, box.height, y - box.y) / 2
    middle = box.x + box.width / 2
    return (Path(box.role, points=((middle - half, y), (middle + half, y))),)


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
    if shape == "subroutine":
        return (
            Rect(box.role, x=box.x, y=box.y, width=box.width, height=box.height),
            *_subroutine_sides(box),
        )
    if shape == "parallelogram":
        return (Polygon(box.role, points=_parallelogram(box)),)
    if shape == "cylinder":
        return _cylinder(box)
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


def _subroutine_sides(box: Box, role: str | None = None) -> tuple[Path, Path]:
    """The two inner verticals that make a box a `subroutine`."""
    bottom = box.y + box.height
    left, right = box.x + SUBROUTINE_INSET, box.x + box.width - SUBROUTINE_INSET
    drawn = role or box.role
    return (
        Path(drawn, points=((left, box.y), (left, bottom))),
        Path(drawn, points=((right, box.y), (right, bottom))),
    )


def _parallelogram(box: Box) -> tuple[tuple[float, float], ...]:
    """A `parallelogram`'s corners, clockwise from top left, leaning right."""
    slant = min(PARALLELOGRAM_SLANT, box.width / 2)
    right, bottom = box.x + box.width, box.y + box.height
    return ((box.x + slant, box.y), (right, box.y), (right - slant, bottom), (box.x, bottom))


def _arc(
    cx: float, cy: float, rx: float, ry: float, start: float, end: float
) -> list[tuple[float, float]]:
    """Points along an ellipse from angle `start` to `end` (radians, y down)."""
    steps = 2 * _ROUND_SEGMENTS
    return [
        (
            cx + rx * math.cos(start + (end - start) * step / steps),
            cy + ry * math.sin(start + (end - start) * step / steps),
        )
        for step in range(steps + 1)
    ]


def _cylinder_silhouette(box: Box) -> list[tuple[float, float]]:
    """A drum's outline: the lid's back rim, down one side, the base, up the other."""
    cap = min(CYLINDER_CAP, box.height / 4)
    half = box.width / 2
    cx = box.x + half
    top, bottom = box.y + cap, box.y + box.height - cap
    return [
        *_arc(cx, top, half, cap, math.pi, 2 * math.pi),
        *_arc(cx, bottom, half, cap, 0.0, math.pi),
    ]


def _cylinder(box: Box) -> tuple[Primitive, ...]:
    """A `cylinder`: its silhouette, then the front rim of its lid."""
    cap = min(CYLINDER_CAP, box.height / 4)
    half = box.width / 2
    rim = _arc(box.x + half, box.y + cap, half, cap, math.pi, 0.0)
    return (
        Polygon(box.role, points=tuple(_cylinder_silhouette(box))),
        Path(box.role, points=tuple(reversed(rim))),
    )


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

    The gap is left on **both** sides of the caption, and only one of the two used
    to be paid for. A caption below was spaced off the drawing and then ran flush
    to the bottom of the figure — the canvas ended where the block did — so the
    words butted against whatever the page put next. That is the starved bottom
    margin `[box] padding` names as the corpus's most repeated complaint, one
    level up: fixed inside the box, reintroduced at the canvas.

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
    # A gap on each side of the caption: one between it and the drawing, one
    # between it and the edge of the figure. One gap bought only the first, and
    # which of the two went unpaid depended on the side — above, the caption was
    # inset from the top and butted against the drawing; below, it was spaced off
    # the drawing and ran flush to the bottom edge. Two gaps is also what keeps
    # the band the same size either way, which is what makes the side a house
    # style's choice rather than a change of measurements.
    band = block.height + gap * 2
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


#: The role a change's tag is drawn in: the pill, the one shape whose meaning is
#: already *this is a label stuck on*. The same role `files` draws its tags in.
STATUS_ROLE: Final = "start"

#: The role a removed box's outline is drawn in — dashed, like the edge it was:
#: the treatment for something tentative, which a box on its way out is.
REMOVED_ROLE: Final = "weak"

#: Segments per half-turn when a rounded outline is drawn as a dashed path.
_ROUND_SEGMENTS: Final = 12


#: The marks a change is drawn with — `files`' marks, with removal set as a
#: true minus sign. A hyphen is the right character in a plain-text tree, where
#: it is all ASCII has (`drawspec.filetree.STATUS_MARKS` keeps it), and the wrong
#: one on a drawing: alone beside an edge it is a dash a quarter of an em long,
#: and read as a stray tick in the line rather than as a mark.
DRAWN_MARKS: Final = {"added": "+", "changed": "~", "removed": "\u2212"}


def status_words(status: str) -> str:
    """What a change's tag says: the mark, then the word — `+ added`."""
    return f"{DRAWN_MARKS[status]} {status}"


def status_size(status: str, theme: Theme, measurer: TextMeasurer) -> tuple[float, float]:
    """How wide and tall a change's tag is drawn, at the label level.

    The same proportions as a `files` tag: ten units of room across the words and
    three over their height, where a unit is the body size over eleven.
    """
    unit = theme.scale["body"] / 11
    extents = measurer.measure(status_words(status), theme.font.default, theme.scale["label"])
    return extents.width + 10 * unit, extents.height + 3 * unit


def status_tag(
    status: str, centre_x: float, centre_y: float, theme: Theme, measurer: TextMeasurer
) -> tuple[Primitive, ...]:
    """A change's tag — `+ added` in a pill — centred on `(centre_x, centre_y)`."""
    width, height = status_size(status, theme, measurer)
    extents = measurer.measure(status_words(status), theme.font.default, theme.scale["label"])
    return (
        Rect(
            STATUS_ROLE,
            x=centre_x - width / 2,
            y=centre_y - height / 2,
            width=width,
            height=height,
        ),
        # A run, not a line: the tag is furniture set in the label type, like a
        # `files` tag or an edge's label, and never carries an author's spans.
        TextRun(
            STATUS_ROLE,
            x=centre_x,
            y=centre_y + (extents.ascent - extents.descent) / 2,
            text=status_words(status),
            level="label",
            font=theme.font.default,
            anchor="middle",
        ),
    )


def status_key(
    statuses: set[str], top: float, width: float, theme: Theme, measurer: TextMeasurer
) -> tuple[tuple[Primitive, ...], float, float]:
    """The tags of every status used, in a row centred across `width` from `top`.

    Returns the primitives, the row's own width and its height. The tags are the
    key: each says its mark and its word, so a bare `+` on an edge is explained
    by the `+ added` beside it here.
    """
    used = [status for status in STATUSES if status in statuses]
    if not used:
        return (), 0.0, 0.0
    gap = theme.box.padding.top
    sizes = [status_size(status, theme, measurer) for status in used]
    row = sum(size[0] for size in sizes) + gap * (len(sizes) - 1)
    tall = max(size[1] for size in sizes)
    x = (width - row) / 2
    drawn: list[Primitive] = []
    for status, (wide, _) in zip(used, sizes, strict=True):
        drawn.extend(status_tag(status, x + wide / 2, top + tall / 2, theme, measurer))
        x += wide + gap
    return tuple(drawn), row, tall


def status_box_primitives(
    box: Box, status: str, theme: Theme, measurer: TextMeasurer
) -> tuple[Primitive, ...]:
    """A box whose text ends in a change's tag: its outline, its words, the tag.

    The box was sized with the tag as its last line, so the tag's room is already
    in it; this draws that last line as the pill rather than as words. A removed
    box is outlined dashed and its words struck through — never colour alone.
    """
    runs = text_runs(box, theme, measurer)
    *words, tag = runs
    drawn: list[Primitive] = [
        *(removed_outline(box, theme) if status == "removed" else outline(box, theme)),
        *lead_rule(box),
        *(replace(line, strike=status == "removed") for line in words),
    ]
    middle = tag.y - (box.block.ascent - box.block.descent) / 2
    drawn.extend(status_tag(status, tag.x, middle, theme, measurer))
    return tuple(drawn)


def removed_outline(box: Box, theme: Theme) -> tuple[Primitive, ...]:
    """`box`'s shape traced as one dashed path, in the role a removed box takes.

    A path rather than the shape's own primitive because a dash belongs to a role
    and the box's role is still what it was — a removed decision is still a
    question, so it keeps its diamond and loses only its solid line.
    """
    shape = theme.roles[box.role].shape
    left, top, width, height = box.x, box.y, box.width, box.height
    right, bottom = left + width, top + height
    if shape == "none":
        return ()
    if shape == "diamond":
        middle_x, middle_y = left + width / 2, top + height / 2
        corners = [(middle_x, top), (right, middle_y), (middle_x, bottom), (left, middle_y)]
    elif shape == "parallelogram":
        corners = list(_parallelogram(box))
    elif shape == "cylinder":
        corners = _cylinder_silhouette(box)
        cap = min(CYLINDER_CAP, height / 4)
        rim = _arc(left + width / 2, top + cap, width / 2, cap, 0.0, math.pi)
        return (
            Path(REMOVED_ROLE, points=(*corners, corners[0])),
            Path(REMOVED_ROLE, points=tuple(rim)),
        )
    elif shape == "ellipse":
        cx, cy = left + width / 2, top + height / 2
        corners = [
            (
                cx + width / 2 * math.cos(math.pi * step / _ROUND_SEGMENTS),
                cy + height / 2 * math.sin(math.pi * step / _ROUND_SEGMENTS),
            )
            for step in range(2 * _ROUND_SEGMENTS)
        ]
    elif shape == "pill":
        radius = height / 2
        corners = [
            (
                right - radius + radius * math.cos(-math.pi / 2 + math.pi * step / _ROUND_SEGMENTS),
                top + radius + radius * math.sin(-math.pi / 2 + math.pi * step / _ROUND_SEGMENTS),
            )
            for step in range(_ROUND_SEGMENTS + 1)
        ] + [
            (
                left + radius + radius * math.cos(math.pi / 2 + math.pi * step / _ROUND_SEGMENTS),
                top + radius + radius * math.sin(math.pi / 2 + math.pi * step / _ROUND_SEGMENTS),
            )
            for step in range(_ROUND_SEGMENTS + 1)
        ]
    else:
        # The theme's corner radius, traced, so a removed box keeps the outline of
        # the boxes beside it and differs from them only by its dash.
        r = min(theme.box.corner_radius, width / 2, height / 2)
        quarter = max(_ROUND_SEGMENTS // 4, 1)
        corners = []
        for cx, cy, start in (
            (right - r, top + r, -math.pi / 2),
            (right - r, bottom - r, 0.0),
            (left + r, bottom - r, math.pi / 2),
            (left + r, top + r, math.pi),
        ):
            corners.extend(
                (
                    cx + r * math.cos(start + math.pi / 2 * step / quarter),
                    cy + r * math.sin(start + math.pi / 2 * step / quarter),
                )
                for step in range(quarter + 1)
            )
    trace = Path(REMOVED_ROLE, points=(*corners, corners[0]))
    if shape == "subroutine":
        return (trace, *_subroutine_sides(box, REMOVED_ROLE))
    return (trace,)


__all__ = [
    "CAPTION_ROLE",
    "DRAWN_MARKS",
    "REMOVED_ROLE",
    "STATUS_ROLE",
    "box_primitives",
    "captioned",
    "line_bounds",
    "outline",
    "removed_outline",
    "status_box_primitives",
    "status_key",
    "status_size",
    "status_tag",
    "status_words",
    "text_runs",
]
