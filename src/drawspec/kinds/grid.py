"""Grid kinds: `stack`, `timeline`, `columns`. Positions come from counting.

No layout engine is involved and no routing problem exists — which is why these
three are the family where "peers are the same size" can be an exact equality
rather than a normalisation that happens to work out. The gate is
`same_rank_size_variance == 0`, and in each kind below it holds by construction:

* `stack` — every layer is the full width and one common height.
* `columns` — the available width less the gutters, divided equally.
* `timeline` — one step, computed once, between every pair of ticks.

Spacing is derived from the theme's box padding rather than invented here. A kind
decides *which* gap applies where; how big a gap is remains the theme's business,
so a consumer retunes their diagrams by editing a theme file.
"""

from __future__ import annotations

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import box_primitives
from drawspec.scene import Path, Primitive, Scene
from drawspec.schema import Document, Item
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The role the timeline's own axis and ticks are drawn with. An axis is a plain
#: connector — no head, no direction — which is exactly what `link` means, so it
#: is named rather than given geometry of its own.
AXIS_ROLE = "link"

#: How long a timeline's tick marks are, as a fraction of the theme's head
#: length. Ticks read as marks on a line rather than as arrows.
TICK_FRACTION = 1.0


def grid_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a grid-kind document to a `Scene`.

    Raises:
        DrawspecError: `document.kind` is not a grid kind.
        FitError: the content cannot fit the width at this type scale.
    """
    if document.kind == "stack":
        return _stack(document, theme, measurer)
    if document.kind == "columns":
        return _columns(document, theme, measurer)
    if document.kind == "timeline":
        return _timeline(document, theme, measurer)
    raise DrawspecError(f"{document.kind!r} is not a grid kind")


def _canvas_width(document: Document, theme: Theme) -> float:
    """The width to draw to. The document may override the theme; nothing else may."""
    return document.width if document.width else theme.canvas.width


def _scene(document: Document, primitives: list[Primitive], width: float, height: float) -> Scene:
    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _sized(
    items: tuple[Item, ...], theme: Theme, measurer: TextMeasurer, width: float
) -> list[Box]:
    """One box per item, each wrapped to `width`."""
    return [
        size_box(
            item.text,
            theme=theme,
            measurer=measurer,
            role=item.role,
            level="body",
            max_width=width,
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# stack
# ---------------------------------------------------------------------------


def _stack(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Layers, full width, all one height, top to bottom.

    Equal height is the point: a stack whose layers differ in height reads as a
    ranking of importance, which is not what the author said.
    """
    width = _canvas_width(document, theme)
    gap = theme.box.padding.top
    boxes = normalise(_sized(document.items, theme, measurer, width))

    primitives: list[Primitive] = []
    y = 0.0
    for box in boxes:
        # Full width, not the width its own text happened to need.
        placed = box.resized(width=width).moved_to(0.0, y)
        primitives.extend(box_primitives(placed, theme, measurer))
        y += placed.height + gap

    return _scene(document, primitives, width, max(y - gap, 0.0))


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------


def _columns(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Side by side, equal width, equal height, left to right."""
    width = _canvas_width(document, theme)
    gutter = theme.box.padding.horizontal
    count = len(document.items)
    column = (width - gutter * (count - 1)) / count
    if column <= theme.box.padding.horizontal:
        raise FitError(
            f"{count} columns do not fit a width of {width:.0f}: each would be "
            f"{column:.1f} wide, which is narrower than the theme's own padding. "
            f"Use fewer columns, a wider canvas, or a different kind."
        )

    boxes = normalise(_sized(document.items, theme, measurer, column))
    primitives: list[Primitive] = []
    for index, box in enumerate(boxes):
        placed = box.resized(width=column).moved_to((column + gutter) * index, 0.0)
        primitives.extend(box_primitives(placed, theme, measurer))

    height = max((box.height for box in boxes), default=0.0)
    return _scene(document, primitives, width, height)


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


def _timeline(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Labels above an axis, one tick each, evenly spaced.

    Even spacing is the gate, so the step is computed once from the width and the
    label width — never accumulated per item, which is how a timeline ends up
    with a slightly wider gap at one end.
    """
    width = _canvas_width(document, theme)
    count = len(document.items)
    gutter = theme.box.padding.horizontal
    label_width = (width - gutter * (count - 1)) / count if count > 1 else width
    if label_width <= theme.box.padding.horizontal:
        raise FitError(
            f"{count} timeline entries do not fit a width of {width:.0f}: each label "
            f"would be {label_width:.1f} wide, narrower than the theme's own padding. "
            f"Use fewer entries, a wider canvas, or a vertical kind such as `stack`."
        )

    boxes = normalise(_sized(document.items, theme, measurer, label_width))
    band = max((box.height for box in boxes), default=0.0)
    tick = theme.edge.head_length * TICK_FRACTION
    axis_y = band + theme.box.padding.top

    # One step for every gap, so the last tick lands exactly on the last centre.
    first_centre = label_width / 2
    step = (width - label_width) / (count - 1) if count > 1 else 0.0

    primitives: list[Primitive] = [
        Path(AXIS_ROLE, points=((0.0, axis_y), (width, axis_y))),
    ]
    for index, box in enumerate(boxes):
        centre = first_centre + step * index
        primitives.append(
            Path(AXIS_ROLE, points=((centre, axis_y - tick / 2), (centre, axis_y + tick / 2)))
        )
        placed = box.resized(width=label_width).moved_to(centre - label_width / 2, 0.0)
        primitives.extend(box_primitives(placed, theme, measurer))

    return _scene(document, primitives, width, axis_y + tick / 2)


__all__ = ["AXIS_ROLE", "TICK_FRACTION", "grid_scene"]
