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

from drawspec.geometry import Box
from drawspec.scene import Ellipse, Polygon, Primitive, Rect, TextRun
from drawspec.text.measure import TextMeasurer
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


def text_runs(box: Box, theme: Theme, measurer: TextMeasurer) -> tuple[TextRun, ...]:
    """One run per span, positioned on its own baseline and centred as a line."""
    size = theme.scale[box.level]
    centre = (box.usable_left + box.usable_right) / 2
    runs: list[TextRun] = []
    for line, baseline in zip(box.block.lines, box.baselines(), strict=True):
        offset = centre - line.width / 2
        for span in line.spans:
            if span.text:
                runs.append(
                    TextRun(
                        box.role,
                        x=offset,
                        y=baseline,
                        text=span.text,
                        level=box.level,
                        font=span.font,
                        weight=span.weight,
                    )
                )
            offset += measurer.measure(span.text, span.font, size).width
    return tuple(runs)


__all__ = ["box_primitives", "outline", "text_runs"]
