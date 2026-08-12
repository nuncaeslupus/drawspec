"""The `chart` kind: scales, ticks, axis labels, series and point labels.

A third rendering family, sharing only the theme and text measurement with the
others. It is here rather than in `kinds/` because it has nothing else in common
with them — no boxes, no roles resolving to shapes, no layout.

It is also the kind the source corpus did worst, and the four things it did worst
are the four things this file is organised around:

**An unlabelled axis cannot be read.** That is a validation error, and it is
already one: the document schema makes `label` required on both axes, so the
refusal happens at parse time with a JSON pointer rather than here. This module
gets to assume both labels exist.

**Marked points land on the line.** A marker is drawn at the same coordinate the
path passes through, computed once and used for both, so they cannot drift apart.

**Point labels cross neither the curve nor the plot edge.** Each label is tried in
eight positions and takes the first that is clear of every series path and inside
the plot. When any point in a series has no clear position, that series gets *no*
point labels — all or nothing.

That last rule is a judgement, so here is the reasoning. Labelling only the points
that happen to have room looks arbitrary, and refusing the whole render is
disproportionate: an ordinary four-point rising series has no clean spot for the
label at its top-right corner, because the line arrives there steeply. Dropping
the series' labels costs nothing a reader needs — the markers show the points and
the axes give the values — while a label on the curve is the failure this kind
exists to prevent.

**Text orientation is decided and constant.** The vertical axis label is rotated,
the horizontal one is not, in every chart. Neither is a per-diagram choice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.scene import Ellipse, Path, Primitive, Scene, TextRun
from drawspec.schema import Axis, Document, Series
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Axis lines and tick marks are plain connectors — no direction, no head — which
#: is exactly what the `link` edge role means.
AXIS_ROLE: Final = "link"

#: The role chart furniture is tagged with. A `TextRun` takes no styling from its
#: role — its level and font decide how it is set — but every primitive must carry
#: a role the theme declares, and the theme has no role for "axis furniture".
FURNITURE_ROLE: Final = "step"

#: A chart's height as a fraction of its width, when the document does not say.
CHART_ASPECT: Final = 0.62

#: Roughly how many ticks to put on an axis. "Roughly", because the step is
#: rounded to a readable number afterwards and that changes the count.
TARGET_TICKS: Final = 5

#: Step sizes a reader can do arithmetic with, as multiples of a power of ten.
NICE_STEPS: Final = (1.0, 2.0, 2.5, 5.0, 10.0)

#: The radius of a point marker, as a fraction of the theme's edge head length.
MARKER_FRACTION: Final = 0.4


@dataclass(frozen=True)
class Scale:
    """A linear map from data values to one axis of the plot, in user units."""

    low: float
    high: float
    start: float
    end: float

    def to_pixels(self, value: float) -> float:
        if self.high == self.low:
            return (self.start + self.end) / 2
        fraction = (value - self.low) / (self.high - self.low)
        return self.start + (self.end - self.start) * fraction


def chart_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a `chart` document to a `Scene`.

    Raises:
        DrawspecError: `document.kind` is not `chart`, or it has no series.
        FitError: the plot, its labels, or a point label cannot fit.
    """
    if document.kind != "chart":
        raise DrawspecError(f"{document.kind!r} is not the chart kind")
    if not document.series:
        raise DrawspecError("a chart needs at least one series")
    horizontal, vertical = document.axes

    width = document.width if document.width else theme.canvas.width
    height = document.height if document.height else width * CHART_ASPECT

    label_size = theme.scale["label"]
    gap = theme.box.padding.top
    line = measurer.measure("0", theme.font.default, label_size)

    across = _scale_for(horizontal, document.series, index=0)
    up = _scale_for(vertical, document.series, index=1)
    across_ticks = _ticks(across.low, across.high)
    up_ticks = _ticks(up.low, up.high)

    # The gutters are measured, not guessed: the widest tick label decides how
    # much room the vertical axis needs, and a rotated label occupies its own
    # line height in width.
    widest = max(
        (measurer.measure(text, theme.font.default, label_size).width for _, text in up_ticks),
        default=0.0,
    )
    left = line.height + gap + widest + gap
    bottom = line.height + gap + line.height + gap
    top = line.height + gap

    plot_left, plot_right = left, width
    plot_top, plot_bottom = top, height - bottom
    if plot_right - plot_left <= 0 or plot_bottom - plot_top <= 0:
        raise FitError(
            f"a chart {width:.0f} x {height:.0f} has no room left for the plot once its "
            f"axis labels and ticks are measured. Give the diagram more width or "
            f"height, or shorten the axis labels."
        )

    across = Scale(across.low, across.high, plot_left, plot_right)
    up = Scale(up.low, up.high, plot_bottom, plot_top)

    primitives: list[Primitive] = [
        *_axes(plot_left, plot_right, plot_top, plot_bottom),
        *_tick_marks(across_ticks, up_ticks, across, up, plot_left, plot_bottom, theme),
        *_tick_labels(
            across_ticks, up_ticks, across, up, plot_left, plot_bottom, theme, measurer, gap
        ),
        *_axis_labels(
            horizontal, vertical, plot_left, plot_right, plot_bottom, height, theme, measurer, gap
        ),
    ]

    paths = [
        tuple((across.to_pixels(x), up.to_pixels(y)) for x, y in series.data)
        for series in document.series
    ]
    for series, points in zip(document.series, paths, strict=True):
        primitives.extend(_series(series, points, theme))
    for series, points in zip(document.series, paths, strict=True):
        primitives.extend(
            _point_labels(
                series, points, paths, theme, measurer, plot_left, plot_right, plot_top, plot_bottom
            )
        )

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


# ---------------------------------------------------------------------------
# Scales and ticks
# ---------------------------------------------------------------------------


def _scale_for(axis: Axis, series: tuple[Series, ...], *, index: int) -> Scale:
    """The data range for one axis, honouring any bounds the author set.

    An author may pin `min` or `max` — that is a statement about the subject, not
    about the drawing, which is why it is one of the few numbers they may write.
    """
    values = [point[index] for item in series for point in item.data]
    low = axis.minimum if axis.minimum is not None else min(values)
    high = axis.maximum if axis.maximum is not None else max(values)
    if high < low:
        raise DrawspecError(f"axis {axis.label!r} has a max below its min")
    if high == low:
        # A flat series still has to be drawn somewhere: give it a unit of room.
        low, high = low - 0.5, high + 0.5
    return Scale(low, high, 0.0, 1.0)


def _ticks(low: float, high: float) -> tuple[tuple[float, str], ...]:
    """Tick values and their labels, at a step a reader can do arithmetic with."""
    step = _nice_step((high - low) / TARGET_TICKS)
    first = math.ceil(low / step) * step
    values: list[float] = []
    value = first
    while value <= high + step * 1e-9:
        values.append(round(value, 10))
        value += step
    return tuple((item, _format_value(item, step)) for item in values)


def _nice_step(raw: float) -> float:
    if raw <= 0:
        return 1.0
    magnitude = float(10 ** math.floor(math.log10(raw)))
    for factor in NICE_STEPS:
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


def _format_value(value: float, step: float) -> str:
    """A tick label with as many decimals as the step needs, and no more."""
    decimals = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    text = f"{value:.{decimals}f}"
    return "0" if text in ("-0", f"-0.{'0' * decimals}") else text


# ---------------------------------------------------------------------------
# Furniture
# ---------------------------------------------------------------------------


def _axes(left: float, right: float, top: float, bottom: float) -> tuple[Primitive, ...]:
    return (
        Path(AXIS_ROLE, points=((left, top), (left, bottom))),
        Path(AXIS_ROLE, points=((left, bottom), (right, bottom))),
    )


def _tick_marks(
    across_ticks: tuple[tuple[float, str], ...],
    up_ticks: tuple[tuple[float, str], ...],
    across: Scale,
    up: Scale,
    left: float,
    bottom: float,
    theme: Theme,
) -> tuple[Primitive, ...]:
    length = theme.edge.head_length
    marks: list[Primitive] = []
    for value, _ in across_ticks:
        x = across.to_pixels(value)
        marks.append(Path(AXIS_ROLE, points=((x, bottom), (x, bottom + length))))
    for value, _ in up_ticks:
        y = up.to_pixels(value)
        marks.append(Path(AXIS_ROLE, points=((left - length, y), (left, y))))
    return tuple(marks)


def _tick_labels(
    across_ticks: tuple[tuple[float, str], ...],
    up_ticks: tuple[tuple[float, str], ...],
    across: Scale,
    up: Scale,
    left: float,
    bottom: float,
    theme: Theme,
    measurer: TextMeasurer,
    gap: float,
) -> tuple[Primitive, ...]:
    size = theme.scale["label"]
    extents = measurer.measure("0", theme.font.default, size)
    labels: list[Primitive] = []
    for value, text in across_ticks:
        labels.append(
            TextRun(
                FURNITURE_ROLE,
                x=across.to_pixels(value),
                y=bottom + theme.edge.head_length + gap + extents.ascent,
                text=text,
                level="label",
                font=theme.font.default,
                anchor="middle",
            )
        )
    for value, text in up_ticks:
        labels.append(
            TextRun(
                FURNITURE_ROLE,
                x=left - theme.edge.head_length - gap,
                y=up.to_pixels(value) + (extents.ascent - extents.descent) / 2,
                text=text,
                level="label",
                font=theme.font.default,
                anchor="end",
            )
        )
    return tuple(labels)


def _axis_labels(
    horizontal: Axis,
    vertical: Axis,
    left: float,
    right: float,
    bottom: float,
    height: float,
    theme: Theme,
    measurer: TextMeasurer,
    gap: float,
) -> tuple[Primitive, ...]:
    """The two axis labels. The vertical one is rotated; the horizontal one is not.

    Decided once and constant in every chart, which is the whole of the rule — an
    author cannot choose, and neither can a diagram.
    """
    size = theme.scale["label"]
    extents = measurer.measure("0", theme.font.default, size)
    return (
        TextRun(
            FURNITURE_ROLE,
            x=(left + right) / 2,
            y=height - gap,
            text=_with_unit(horizontal),
            level="label",
            font=theme.font.default,
            anchor="middle",
        ),
        TextRun(
            FURNITURE_ROLE,
            x=extents.ascent,
            y=bottom / 2,
            text=_with_unit(vertical),
            level="label",
            font=theme.font.default,
            anchor="middle",
            rotate=-90.0,
        ),
    )


def _with_unit(axis: Axis) -> str:
    return f"{axis.label} ({axis.unit})" if axis.unit else axis.label


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------


def _series(
    series: Series, points: tuple[tuple[float, float], ...], theme: Theme
) -> tuple[Primitive, ...]:
    """The line, then a marker at every point — both from the same coordinates.

    Computing the marker's centre from the same tuple the path is built from is
    what makes "markers land on the line" structural rather than checked.
    """
    radius = theme.edge.head_length * MARKER_FRACTION
    line: list[Primitive] = [Path(series.role, points=points)]
    line.extend(Ellipse(series.role, cx=x, cy=y, rx=radius, ry=radius) for x, y in points)
    return tuple(line)


def _point_labels(
    series: Series,
    points: tuple[tuple[float, float], ...],
    every_path: list[tuple[tuple[float, float], ...]],
    theme: Theme,
    measurer: TextMeasurer,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> tuple[Primitive, ...]:
    """Labels for every point in a series, or none of them.

    Above first, then below, then beside — and each of the two vertical positions
    in three alignments, because a point sitting *on* an axis has a centred label
    half outside the plot. Aligning it to start or end at the point keeps it
    inside without moving it off its own point, which is what a person would do
    by hand. The order is fixed, so the choice is the same on every run.

    All or nothing per series: see the module docstring for why.
    """
    size = theme.scale["label"]
    gap = theme.box.padding.top
    labels: list[Primitive] = []

    for (x, y), (_, value) in zip(points, series.data, strict=True):
        text = _format_value(value, _nice_step(abs(value) / TARGET_TICKS or 1.0))
        extents = measurer.measure(text, theme.font.default, size)
        half = extents.width / 2

        above = y - gap - extents.descent
        below = y + gap + extents.ascent
        beside = y + (extents.ascent - extents.descent) / 2
        for anchor_x, anchor_y, anchor in (
            (x, above, "middle"),
            (x, above, "start"),
            (x, above, "end"),
            (x, below, "middle"),
            (x, below, "start"),
            (x, below, "end"),
            (x + gap, beside, "start"),
            (x - gap, beside, "end"),
        ):
            box = _label_box(anchor_x, anchor_y, anchor, extents.width, extents.height, half)
            if not _inside(box, left, right, top, bottom):
                continue
            if any(_crosses(box, path) for path in every_path):
                continue
            labels.append(
                TextRun(
                    series.role,
                    x=anchor_x,
                    y=anchor_y,
                    text=text,
                    level="label",
                    font=theme.font.default,
                    anchor=anchor,
                )
            )
            break
        else:
            # One point with nowhere clean to go costs the series its labels.
            return ()
    return tuple(labels)


def _label_box(
    x: float, y: float, anchor: str, width: float, height: float, half: float
) -> tuple[float, float, float, float]:
    """`(left, top, right, bottom)` of a label drawn at `(x, y)` with `anchor`."""
    starts = {"middle": x - half, "start": x, "end": x - width}
    left = starts[anchor]
    return left, y - height, left + width, y


def _inside(
    box: tuple[float, float, float, float], left: float, right: float, top: float, bottom: float
) -> bool:
    return box[0] >= left and box[2] <= right and box[1] >= top and box[3] <= bottom


def _crosses(box: tuple[float, float, float, float], path: tuple[tuple[float, float], ...]) -> bool:
    """Whether a label box meets any segment of a series path."""
    return any(_segment_meets_box(first, second, box) for first, second in pairwise(path))


def _segment_meets_box(
    first: tuple[float, float],
    second: tuple[float, float],
    box: tuple[float, float, float, float],
) -> bool:
    """Sampled rather than solved: a segment is checked at intervals along it.

    A chart's segments are short and its labels are a few characters, so sampling
    finely enough to catch a crossing is cheaper than a line-rectangle
    intersection and much harder to get subtly wrong.
    """
    left, top, right, bottom = box
    steps = 24
    for index in range(steps + 1):
        fraction = index / steps
        x = first[0] + (second[0] - first[0]) * fraction
        y = first[1] + (second[1] - first[1]) * fraction
        if left <= x <= right and top <= y <= bottom:
            return True
    return False


__all__ = [
    "AXIS_ROLE",
    "CHART_ASPECT",
    "FURNITURE_ROLE",
    "MARKER_FRACTION",
    "TARGET_TICKS",
    "Scale",
    "chart_scene",
]
