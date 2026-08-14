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
eight positions — above, below, left, right and the four diagonals — and takes the
first that keeps clear daylight from every series path and sits inside the plot.
When any point in a series has no clear position, that series gets *no* point
labels — all or nothing.

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
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.legend import entries_for, height_of, primitives_for
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextRun
from drawspec.schema import Axis, Document, Position, Series
from drawspec.text.measure import Extents, TextMeasurer
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

#: The furthest apart two samples along a segment may be when testing whether it
#: meets a label box. Smaller than the shortest side of a label set at the
#: theme's label size, so a sample cannot step over one.
SAMPLE_SPACING: Final = 4.0

#: How many segments each span between two waypoints is drawn with. Enough that
#: the polyline reads as a curve at the sizes drawspec draws at; a reader's
#: renderer gets the shape rather than a recipe for it.
CURVE_STEPS: Final = 16

#: A quadrant's height as a fraction of its width. Nearer square than a chart,
#: because the two directions are peers here — neither is "the" axis.
QUADRANT_ASPECT: Final = 0.8

#: How much room a quadrant leaves outside the values it holds, as a fraction of
#: their range. A point *on* the edge has half its label outside the plot.
QUADRANT_MARGIN: Final = 0.12

#: The role a quadrant's midlines are drawn in. `weak` — dashed, headless — so
#: they read as a division of the field rather than as two more axes.
DIVIDER_ROLE: Final = "weak"

#: How much daylight a label keeps from a line it must not sit on, and from
#: another label. Not-overlapping is not enough: at the sizes these are read at,
#: a descender a hair from a stroke reads as touching it.
LABEL_DAYLIGHT: Final = 2.0

#: The most decimals a point label may carry. Past this the label is wider than
#: the room beside its own point, and values that close needed a different chart.
MAXIMUM_DECIMALS: Final = 3


@dataclass(frozen=True)
class Bar:
    """One drawn bar, and the value it stands for."""

    series: Series
    value: float
    box: tuple[float, float, float, float]
    """`(left, top, right, bottom)`, with `top` the edge away from the baseline."""

    stacked: bool
    """Whether something may be sitting on this bar's top edge."""


@dataclass(frozen=True)
class Marked:
    """The filled marks: the drawing, and where the bars in it landed."""

    primitives: tuple[Primitive, ...]
    bars: tuple[Bar, ...]


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
    if document.kind == "quadrant":
        return _quadrant(document, theme, measurer)
    if document.kind == "curve":
        return _curve(document, theme, measurer)
    if document.kind != "chart":
        raise DrawspecError(f"{document.kind!r} is not the chart kind")
    if not document.series:
        raise DrawspecError("a chart needs at least one series")
    horizontal, vertical = document.axes

    width = document.width if document.width else theme.canvas.width
    height = document.height if document.height else width * CHART_ASPECT

    label_size = theme.scale["label"]
    gap = theme.box.padding.top
    tick = theme.edge.head_length
    line = measurer.measure("0", theme.font.default, label_size)

    filled = tuple(item for item in document.series if item.mark in ("bar", "area"))
    across = _scale_for(horizontal, [point[0] for item in document.series for point in item.data])
    up = _scale_for(vertical, _stacked_heights(document.series), include_zero=bool(filled))
    across_ticks = _named_ticks(horizontal) or _ticks(across.low, across.high)
    up_ticks = _named_ticks(vertical) or _ticks(up.low, up.high)

    # The gutters are measured, not guessed, and each one is the sum of the
    # things that go in it — in the order they go in it. Writing them any other
    # way is how the axis label ended up two units from the tick numbers while
    # the arithmetic said ten: the gutter reserved a gap the placement then spent
    # on the tick marks, and nothing compared the two.
    # What the fills stand for, and how much of the bottom edge saying so costs.
    # Measured before the plot is placed, because the legend is not an annotation
    # on a finished drawing — it takes room the plot then does not have.
    key = entries_for(
        [(item.name, item.role, item.mark in ("bar", "area")) for item in document.series],
        theme,
    )
    legend = height_of(key, theme, measurer, width)

    widest = _widest(up_ticks, theme, measurer, label_size)
    left = line.height + gap + widest + gap + tick
    bottom = tick + gap + line.height + _caption_band(line, gap) + legend
    top = line.height + gap
    # Half the last tick label hangs past the end of its own axis, so the canvas
    # has to hold it. Without this the reader loses the right-hand digit.
    right = max(_widest(across_ticks, theme, measurer, label_size) / 2, line.height)

    plot_left, plot_right = left, width - right
    plot_top, plot_bottom = top, height - bottom
    if plot_right - plot_left <= 0 or plot_bottom - plot_top <= 0:
        raise FitError(
            f"a chart {width:.0f} x {height:.0f} has no room left for the plot once its "
            f"axis labels and ticks are measured. Give the diagram more width or "
            f"height, or shorten the axis labels."
        )

    across = Scale(across.low, across.high, plot_left, plot_right)
    up = Scale(up.low, up.high, plot_bottom, plot_top)

    paths = [
        tuple((across.to_pixels(x), up.to_pixels(y)) for x, y in series.data)
        for series in document.series
    ]
    baseline = up.to_pixels(min(max(0.0, up.low), up.high))

    marked = _filled_marks(document.series, paths, across, baseline, plot_left, plot_right, theme)

    # Filled marks go down first, then the axis furniture over them, then the
    # lines: a bar sits *on* the baseline, so the axis has to be the thing drawn
    # on top of the join or the bar's own edge stands in for it.
    primitives: list[Primitive] = [
        *marked.primitives,
        *_axes(plot_left, plot_right, plot_top, plot_bottom),
        *_tick_marks(across_ticks, up_ticks, across, up, plot_left, plot_bottom, theme),
        *_tick_labels(
            across_ticks, up_ticks, across, up, plot_left, plot_bottom, theme, measurer, gap
        ),
        *_axis_labels(
            horizontal,
            vertical,
            plot_left,
            plot_right,
            plot_top,
            plot_bottom,
            height - legend,
            theme,
            measurer,
            gap,
        ),
        *primitives_for(key, theme, measurer, left, height - legend, width - left),
    ]

    if document.values and marked.bars:
        primitives.extend(
            _bar_labels(
                marked.bars,
                theme,
                measurer,
                plot_top,
                _point_decimals(tuple(item for item in document.series if item.mark == "bar")),
            )
        )

    lines = tuple(item for item in document.series if item.mark == "line")
    line_paths = [
        points for item, points in zip(document.series, paths, strict=True) if item.mark == "line"
    ]
    for series, points in zip(lines, line_paths, strict=True):
        primitives.extend(_series(series, points, theme))
    if lines and document.values:
        decimals = _point_decimals(lines)
        for series, points in zip(lines, line_paths, strict=True):
            primitives.extend(
                _point_labels(
                    series,
                    points,
                    # A point label dodges the filled marks as well as the
                    # lines. When there is nowhere left, the series loses its
                    # labels — which is the rule this kind already had for a
                    # label with no clean spot, applied to a fuller plot.
                    [*line_paths, *(_outline(mark) for mark in marked.primitives)],
                    theme,
                    measurer,
                    plot_left,
                    plot_right,
                    plot_top,
                    plot_bottom,
                    decimals,
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


def _stacked_heights(series: tuple[Series, ...]) -> list[float]:
    """Every height the vertical scale has to reach, piles included.

    A stacked mark's top is the sum of its stack at that x, not its own value, so
    a scale measured from the raw numbers leaves the pile hanging outside the
    plot — two bars of 20 in one stack reach 40 against an axis that stops at 20,
    and the second one is drawn above the top of the drawing. It was.

    Every *running* total counts and not only the last, because a stack whose
    later members are negative passes through a height taller than where it ends.
    """
    running: dict[tuple[str, float], float] = {}
    heights: list[float] = []
    for item in series:
        for x, y in item.data:
            if not item.stack:
                heights.append(y)
                continue
            total = running.get((item.stack, x), 0.0) + y
            running[(item.stack, x)] = total
            heights.append(total)
    return heights


def _scale_for(axis: Axis, values: list[float], *, include_zero: bool = False) -> Scale:
    """The data range for one axis, honouring any bounds the author set.

    An author may pin `min` or `max` — that is a statement about the subject, not
    about the drawing, which is why it is one of the few numbers they may write.

    `include_zero` stretches the range to the baseline. A bar says "this much of
    it" by its length, and a bar chart whose axis starts at 6.8 makes a value of
    7.0 look like nothing and 7.4 like three times nothing. A line makes no such
    claim, so it does not pay for this.
    """
    values = list(values)
    if include_zero:
        values.append(0.0)
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


def _named_ticks(axis: Axis) -> tuple[tuple[float, str], ...]:
    """One tick per category, at 1, 2, 3 …, or nothing for a numeric axis.

    A bar chart's horizontal axis is almost never a measurement — it is the
    quarters, the service models, the teams — and numbering them 0 to 4 asks the
    reader to hold a mapping the drawing never gave them. `min` and `max` still
    do the framing; this only replaces what the ticks say.
    """
    return tuple((float(index + 1), name) for index, name in enumerate(axis.categories))


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


def _widest(
    ticks: tuple[tuple[float, str], ...], theme: Theme, measurer: TextMeasurer, size: float
) -> float:
    return max(
        (measurer.measure(text, theme.font.default, size).width for _, text in ticks),
        default=0.0,
    )


def _axis_labels(
    horizontal: Axis,
    vertical: Axis,
    left: float,
    right: float,
    top: float,
    bottom: float,
    floor: float,
    theme: Theme,
    measurer: TextMeasurer,
    gap: float,
) -> tuple[Primitive, ...]:
    """The two axis labels. The vertical one is rotated; the horizontal one is not.

    Decided once and constant in every chart, which is the whole of the rule — an
    author cannot choose, and neither can a diagram.

    Each is centred on the plot rather than on the canvas: an axis names the
    range it runs along, and the gutters at the two ends of that range are not
    the same size.
    """
    size = theme.scale["label"]
    extents = measurer.measure("0", theme.font.default, size)
    return (
        TextRun(
            FURNITURE_ROLE,
            x=(left + right) / 2,
            y=floor - gap - extents.descent,
            text=_with_unit(horizontal),
            level="label",
            font=theme.font.default,
            anchor="middle",
        ),
        TextRun(
            FURNITURE_ROLE,
            x=extents.ascent,
            y=(top + bottom) / 2,
            text=_with_unit(vertical),
            level="label",
            font=theme.font.default,
            anchor="middle",
            rotate=-90.0,
        ),
    )


def _with_unit(axis: Axis) -> str:
    return f"{axis.label} ({axis.unit})" if axis.unit else axis.label


def _caption_band(line: Extents, gap: float) -> float:
    """The bottom edge an axis caption needs: a gap, the caption, a gap.

    It is the gap *above* the caption that gets forgotten. `_axis_labels` sets
    the horizontal caption's baseline a descent up from the bottom edge, so a
    gutter of `line.height + gap` puts its cap-height exactly on the axis — the
    caption looks welded to the line it names.

    The rotated caption on the left hides the mistake, which is why it survived:
    a run rotated a quarter turn measures its own gap from the *descender* side,
    so `line.height + gap` there really is a gap. Nothing compared the two.
    """
    return gap + line.height + gap


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


def _filled_marks(
    series: tuple[Series, ...],
    paths: list[tuple[tuple[float, float], ...]],
    across: Scale,
    baseline: float,
    plot_left: float,
    plot_right: float,
    theme: Theme,
) -> Marked:
    """Bars and areas — every mark that reaches the baseline.

    The fill comes from the theme's declared sequence rather than from the role,
    and is assigned by position among the filled marks. That is deliberate: three
    series of bars are three of the same *kind* of thing, so telling them apart
    is a job for a sequence the theme owns, not for inventing three roles.

    Where each bar landed comes back with the drawing rather than being worked
    out a second time by whatever wants to write a number on it: the number and
    the bar have to agree about where the bar is, and the cheapest way to
    guarantee that is for there to be one answer.
    """
    filled = [
        (item, points)
        for item, points in zip(series, paths, strict=True)
        if item.mark in ("bar", "area")
    ]
    if not filled:
        return Marked((), ())

    fills = {id(item): theme.mark.fill_for(index) for index, (item, _) in enumerate(filled)}
    primitives: list[Primitive] = []

    # Where each stack of areas has reached, per x. Separate from the bars' own
    # ledger below: a stack name means "pile these on each other", and piling an
    # area on a bar is not a drawing anyone wants.
    reached: dict[tuple[str, float], float] = {}
    for item, points in filled:
        if item.mark != "area":
            continue
        under = tuple(
            (x, reached.get((item.stack, x), baseline) if item.stack else baseline)
            for x, _ in points
        )
        crest = tuple(
            (x, ground - (baseline - y)) for (x, y), (_, ground) in zip(points, under, strict=True)
        )
        if item.stack:
            reached.update({(item.stack, x): y for x, y in crest})
        # Two primitives, because an area is two different claims. The region is
        # ground: it says "this much of the whole", and the verticals closing it
        # at either end are only where the drawing stops. Outlined, they read as
        # a measurement — over a bar chart they put a full-weight line straight
        # down through the bar at each end of the range. The line along the top
        # is the data, and it is drawn as a line, exactly like a `line` series.
        primitives.append(
            Polygon(
                item.role,
                points=(*crest, *reversed(under)),
                fill=fills[id(item)],
                region=True,
            )
        )
        primitives.append(Path(item.role, points=crest))

    bars = [(item, points) for item, points in filled if item.mark == "bar"]
    if not bars:
        return Marked(tuple(primitives), ())

    band = _band(across, [x for _, points in bars for x, _ in points], plot_left, plot_right)
    columns = _columns([item for item, _ in bars])
    usable = band * (1.0 - theme.mark.gap)
    width = usable / max(len(columns), 1)

    placed: list[Bar] = []
    tops: dict[tuple[str, float], float] = {}
    for item, points in bars:
        column = columns.index(item.stack or item.name)
        offset = -usable / 2 + column * width
        for (x, y), (_, value) in zip(points, item.data, strict=True):
            if item.stack:
                # A stack grows from wherever the pile has reached, not from the
                # baseline — which is the whole difference between stacked and
                # merely overlapping.
                floor = tops.get((item.stack, x), baseline)
                tops[(item.stack, x)] = floor - (baseline - y)
                low, high = sorted((floor, floor - (baseline - y)))
            else:
                low, high = sorted((baseline, y))
            left, right = x + offset, x + offset + width
            # A polygon rather than a rect, because a rect takes the theme's
            # corner radius and a bar with rounded corners no longer meets its
            # own baseline. The corner treatment belongs to boxes, which is
            # what the radius was chosen for.
            primitives.append(
                Polygon(
                    item.role,
                    points=((left, low), (right, low), (right, high), (left, high)),
                    fill=fills[id(item)],
                )
            )
            # `low` and `high` are sorted by y, and y grows downwards — so `low`
            # is the edge away from the baseline and `high` is the one on it.
            placed.append(Bar(item, value, (left, low, right, high), stacked=bool(item.stack)))
    return Marked(tuple(primitives), tuple(placed))


def _bar_labels(
    bars: tuple[Bar, ...],
    theme: Theme,
    measurer: TextMeasurer,
    plot_top: float,
    decimals: int,
) -> tuple[Primitive, ...]:
    """The number each bar stands for, written on the bar. All of them or none.

    Where it goes follows from what is above the bar. A bar standing on its own
    has open sky over its top edge, and that is where a person writing on a
    printout puts the number. A segment of a stack does not — the next segment
    starts exactly there — so its number goes *inside* it, which is also what a
    person does, and it only gets one if the segment is tall enough to hold it.

    All or nothing per series, the same rule the point labels follow: numbering
    the bars that happen to have room reads as arbitrary, and it is not obvious
    from the drawing which rule was applied.
    """
    labels: list[Primitive] = []
    size = theme.scale["label"]
    gap = theme.edge.clearance
    for bar in bars:
        left, top, right, bottom = bar.box
        text = _printed(bar.value, decimals)
        extents = measurer.measure(text, theme.font.default, size)
        if extents.width > right - left:
            return ()  # the number is wider than the bar it belongs to
        above = top - gap - extents.descent
        inside = top + gap + extents.ascent
        if not bar.stacked and above - extents.ascent >= plot_top:
            baseline = above
        elif inside <= bottom - gap:
            baseline = inside
        else:
            return ()  # nowhere on this bar the number fits
        labels.append(
            TextRun(
                bar.series.role,
                x=(left + right) / 2,
                y=baseline,
                text=text,
                level="label",
                font=theme.font.default,
                anchor="middle",
            )
        )
    return tuple(labels)


def _printed(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    return text[1:] if text in ("-0", f"-0.{'0' * decimals}") else text


def _outline(primitive: Primitive) -> tuple[tuple[float, float], ...]:
    """A filled mark as the point-label search understands it: a path.

    A region is closed back to its first point; an area's top edge arrives here
    as an open `Path` and stays open. Both are things a label must not sit on.
    """
    if isinstance(primitive, Polygon):
        return (*primitive.points, primitive.points[0])
    if isinstance(primitive, Path):
        return primitive.points
    return ()


def _columns(bars: list[Series]) -> list[str]:
    """The side-by-side slots a band is divided into.

    One per stack, plus one per unstacked series — so two series in a stack share
    a slot and two that are not each get their own, which is what stacking means
    geometrically.
    """
    columns: list[str] = []
    for item in bars:
        key = item.stack or item.name
        if key not in columns:
            columns.append(key)
    return columns


def _band(across: Scale, values: list[float], plot_left: float, plot_right: float) -> float:
    """How much horizontal room one category has.

    The closest two distinct x values, which is the only spacing that cannot
    overlap whatever the data does. With a single category the whole plot is the
    band, halved so one bar does not span the axis end to end.
    """
    distinct = sorted(set(values))
    if len(distinct) < 2:
        return (plot_right - plot_left) / 2
    return min(second - first for first, second in pairwise(distinct))


def _point_decimals(series: tuple[Series, ...]) -> int:
    """The fewest decimals that still tell the chart's own values apart.

    A point label is there to say *which* value this point is, and rounding it to
    the axis's step defeats that exactly when the points are close together —
    which is when a reader most wants the number. The reference chart is the
    case: four points at 7.2, 6.8, 7.4 and 6.9 all rounded to `7`, so the drawing
    showed four labels reading `7` at four visibly different heights, and the
    obvious reading is that the chart is broken.

    So the precision is a property of the data rather than of the axis: the
    fewest decimals at which no two different values print the same. Capped,
    because past three the label is longer than the gap it has to sit in and the
    points were never that far apart to begin with.
    """
    values = sorted({value for item in series for _, value in item.data})
    for decimals in range(MAXIMUM_DECIMALS + 1):
        printed = {f"{value:.{decimals}f}" for value in values}
        if len(printed) == len(values):
            return decimals
    return MAXIMUM_DECIMALS


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
    decimals: int,
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
        text = f"{value:.{decimals}f}"
        if text in ("-0", f"-0.{'0' * decimals}"):
            text = text[1:]
        extents = measurer.measure(text, theme.font.default, size)
        half = extents.width / 2

        above = y - gap - extents.descent
        below = y + gap + extents.ascent
        beside = y + (extents.ascent - extents.descent) / 2
        for anchor_x, anchor_y, anchor in (
            (x, above, "middle"),
            (x + gap, above, "start"),
            (x - gap, above, "end"),
            (x, below, "middle"),
            (x + gap, below, "start"),
            (x - gap, below, "end"),
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


def _grown(box: tuple[float, float, float, float], by: float) -> tuple[float, float, float, float]:
    """`box` with `by` of margin on every side.

    Used for what a label must not *touch*, never for whether it is inside the
    plot: a label flush against the plot edge is fine — the edge is a boundary,
    not another mark — while a label flush against a line reads as sitting on it.
    """
    return box[0] - by, box[1] - by, box[2] + by, box[3] + by


def _crosses(box: tuple[float, float, float, float], path: tuple[tuple[float, float], ...]) -> bool:
    """Whether a label box comes within `LABEL_DAYLIGHT` of any segment of a path.

    Not-overlapping is too weak a test. A word whose descender stops a hair short
    of a dashed midline is not overlapping it and still reads as touching it —
    "Split the difference" ended exactly on the divider it was naming, because
    the box ended exactly there and the arithmetic said clear.
    """
    grown = _grown(box, LABEL_DAYLIGHT)
    return any(_segment_meets_box(first, second, grown) for first, second in pairwise(path))


def _segment_meets_box(
    first: tuple[float, float],
    second: tuple[float, float],
    box: tuple[float, float, float, float],
) -> bool:
    """Sampled rather than solved: a segment is checked at intervals along it.

    Cheaper than a line-rectangle intersection and much harder to get subtly
    wrong. The step count comes from the segment's own length rather than being
    fixed, because a fixed count is only fine while the segments are short: a
    quadrant's midline runs the height of the plot, and twenty-four samples along
    it step clean over a label a few units tall. That is a crossing reported as
    clear, which is the one direction this must not fail in.
    """
    left, top, right, bottom = box
    length = math.hypot(second[0] - first[0], second[1] - first[1])
    steps = max(24, int(length / 2))
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
    "MAXIMUM_DECIMALS",
    "TARGET_TICKS",
    "Scale",
    "chart_scene",
]


# ---------------------------------------------------------------------------
# quadrant
# ---------------------------------------------------------------------------


def _quadrant(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Two named directions, and things placed between them.

    A chart plots a series against a scale; a quadrant places named things in the
    plane and the *directions* are what carry the meaning — more of this, less of
    that. So there are no ticks and no numbers: a tick would invite a reader to
    read a value off a diagram whose author was making a comparison, not a
    measurement. What is drawn instead is the pair of midlines, because "which
    quarter is it in" is the question these diagrams are for.

    The axis furniture is the chart's, unchanged, which is the reason this lives
    here rather than in a family of its own.
    """
    positions = document.positions
    if not positions:
        raise DrawspecError("a quadrant needs at least one position")
    horizontal, vertical = document.axes

    width = document.width if document.width else theme.canvas.width
    height = document.height if document.height else width * QUADRANT_ASPECT

    size = theme.scale["label"]
    gap = theme.box.padding.top
    line = measurer.measure("0", theme.font.default, size)

    across = _quadrant_scale(horizontal, [item.across for item in positions])
    up = _quadrant_scale(vertical, [item.up for item in positions])

    left = line.height + gap
    bottom = _caption_band(line, gap)
    top = line.height + gap
    right = line.height + gap
    plot_left, plot_right = left, width - right
    plot_top, plot_bottom = top, height - bottom
    if plot_right - plot_left <= 0 or plot_bottom - plot_top <= 0:
        raise FitError(
            f"a quadrant {width:.0f} x {height:.0f} has no room for its plot once the "
            f"axis labels are measured. Give it more width or height."
        )

    across = Scale(across.low, across.high, plot_left, plot_right)
    up = Scale(up.low, up.high, plot_bottom, plot_top)
    middle_x = (plot_left + plot_right) / 2
    middle_y = (plot_top + plot_bottom) / 2

    primitives: list[Primitive] = [
        *_axes(plot_left, plot_right, plot_top, plot_bottom),
        Path(DIVIDER_ROLE, points=((plot_left, middle_y), (plot_right, middle_y))),
        Path(DIVIDER_ROLE, points=((middle_x, plot_top), (middle_x, plot_bottom))),
        *_axis_labels(
            horizontal,
            vertical,
            plot_left,
            plot_right,
            plot_top,
            plot_bottom,
            height,
            theme,
            measurer,
            gap,
        ),
    ]

    dividers: list[tuple[tuple[float, float], ...]] = [
        ((plot_left, middle_y), (plot_right, middle_y)),
        ((middle_x, plot_top), (middle_x, plot_bottom)),
    ]
    radius = theme.edge.head_length * MARKER_FRACTION
    placed: list[tuple[float, float, float, float]] = []
    for item in positions:
        x, y = across.to_pixels(item.across), up.to_pixels(item.up)
        primitives.append(Ellipse(item.role, cx=x, cy=y, rx=radius, ry=radius))
        label = _place_label(
            item,
            x,
            y,
            placed,
            dividers,
            theme,
            measurer,
            plot_left,
            plot_right,
            plot_top,
            plot_bottom,
        )
        if label is None:
            raise FitError(
                f"the label {item.text[:32]!r} has nowhere to sit that is inside the "
                f"plot and clear of the other labels. Move it, shorten it, or give "
                f"the diagram more room."
            )
        box, primitive = label
        placed.append(box)
        primitives.append(primitive)

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _quadrant_scale(axis: Axis, values: list[float]) -> Scale:
    """The range one direction runs over, padded so a point on the end is visible."""
    low = axis.minimum if axis.minimum is not None else min([*values, 0.0])
    high = axis.maximum if axis.maximum is not None else max([*values, 1.0])
    if high <= low:
        low, high = low - 0.5, low + 0.5
    margin = (high - low) * QUADRANT_MARGIN
    return Scale(low - margin, high + margin, 0.0, 1.0)


def _place_label(
    item: Position,
    x: float,
    y: float,
    placed: list[tuple[float, float, float, float]],
    dividers: Sequence[tuple[tuple[float, float], ...]],
    theme: Theme,
    measurer: TextMeasurer,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> tuple[tuple[float, float, float, float], Primitive] | None:
    """A label beside its own point, inside the plot and clear of everything else.

    The same eight positions the chart's point labels use, and the same fixed
    order, so the choice is the same on every run. What differs is what it dodges:
    a quadrant has no curve, and what it does have is the two midlines and the
    labels already placed.

    A point sitting *on* both midlines — dead centre is a real answer in these
    diagrams — is what makes the four diagonals necessary. Above, below, left and
    right all straddle one divider or the other there, and a corner position that
    is only offset vertically has its edge flush against the vertical divider. It
    used to pass by touching it exactly.
    """
    gap = theme.box.padding.top
    extents = measurer.measure(item.text, theme.font.default, theme.scale["label"])
    half = extents.width / 2
    above = y - gap - extents.descent
    below = y + gap + extents.ascent
    beside = y + (extents.ascent - extents.descent) / 2
    for anchor_x, anchor_y, anchor in (
        (x, above, "middle"),
        (x, below, "middle"),
        (x + gap, beside, "start"),
        (x - gap, beside, "end"),
        (x + gap, above, "start"),
        (x - gap, above, "end"),
        (x + gap, below, "start"),
        (x - gap, below, "end"),
    ):
        box = _label_box(anchor_x, anchor_y, anchor, extents.width, extents.height, half)
        if not _inside(box, left, right, top, bottom):
            continue
        if any(_overlaps(box, other) for other in placed):
            continue
        if any(_crosses(box, divider) for divider in dividers):
            continue
        return box, TextRun(
            item.role,
            x=anchor_x,
            y=anchor_y,
            text=item.text,
            level="label",
            font=theme.font.default,
            anchor=anchor,
        )
    return None


def _overlaps(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    """Whether two labels are within `LABEL_DAYLIGHT` of each other.

    Same reasoning as `_crosses`: two words a hair apart read as one word.
    """
    grown = _grown(second, LABEL_DAYLIGHT)
    return (
        first[0] < grown[2] and grown[0] < first[2] and first[1] < grown[3] and grown[1] < first[3]
    )


# ---------------------------------------------------------------------------
# curve
# ---------------------------------------------------------------------------


def _curve(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Named shapes with labelled waypoints. A drawing, not a measurement.

    The hype cycle, the EVM S-curves, a sprint burn-down. These look like charts
    and are not: nobody has the numbers behind a hype cycle, and drawing ticks on
    one would invite a reader to read values off a shape somebody sketched. So
    the axes are labelled and bare, exactly as in `quadrant`, and the waypoints
    carry names rather than values.

    The curve itself is **sampled into a polyline** rather than emitted as a
    Bézier, which is how `cycle` already draws its arcs: the smoothing is
    drawspec's business, and a reader's renderer should be handed the shape
    rather than a recipe for it.
    """
    curves = document.curves
    if not curves:
        raise DrawspecError("a curve diagram needs at least one curve")
    horizontal, vertical = document.axes

    width = document.width if document.width else theme.canvas.width
    height = document.height if document.height else width * CHART_ASPECT

    size = theme.scale["label"]
    gap = theme.box.padding.top
    line = measurer.measure("0", theme.font.default, size)
    names = max(
        (measurer.measure(item.name, theme.font.default, size).width for item in curves),
        default=0.0,
    )

    every = [point for item in curves for point in item.waypoints]
    across = _quadrant_scale(horizontal, [point.across for point in every])
    up = _quadrant_scale(vertical, [point.up for point in every])

    plot_left = line.height + gap
    plot_top = line.height + gap
    plot_bottom = height - _caption_band(line, gap)
    # Room on the right for the name that sits at the end of each curve.
    plot_right = width - names - gap * 2
    if plot_right - plot_left <= 0 or plot_bottom - plot_top <= 0:
        raise FitError(
            f"a curve diagram {width:.0f} x {height:.0f} has no room for its plot once "
            f"the axis labels and the curve names are measured. Give it more width, or "
            f"shorten the names."
        )

    across = Scale(across.low, across.high, plot_left, plot_right)
    up = Scale(up.low, up.high, plot_bottom, plot_top)

    primitives: list[Primitive] = [
        *_axes(plot_left, plot_right, plot_top, plot_bottom),
        *_axis_labels(
            horizontal,
            vertical,
            plot_left,
            plot_right,
            plot_top,
            plot_bottom,
            height,
            theme,
            measurer,
            gap,
        ),
    ]

    drawn = [
        _smooth([(across.to_pixels(p.across), up.to_pixels(p.up)) for p in item.waypoints])
        for item in curves
    ]
    # The names go down first and their boxes are kept, so a waypoint label at
    # the end of a curve does not land on the curve's own name — the two would
    # be saying different things about the same point.
    placed: list[tuple[float, float, float, float]] = []
    for item, path in zip(curves, drawn, strict=True):
        primitives.append(Path(item.role, points=path))
        if not item.name:
            continue
        end_x, end_y = path[-1]
        extents = measurer.measure(item.name, theme.font.default, size)
        placed.append(
            _label_box(
                end_x + gap,
                end_y + (line.ascent - line.descent) / 2,
                "start",
                extents.width,
                extents.height,
                extents.width / 2,
            )
        )
        primitives.append(
            TextRun(
                item.role,
                x=end_x + gap,
                y=end_y + (line.ascent - line.descent) / 2,
                text=item.name,
                level="label",
                font=theme.font.default,
                anchor="start",
            )
        )

    radius = theme.edge.head_length * MARKER_FRACTION
    for item in curves:
        for point in item.waypoints:
            if not point.text:
                continue
            x, y = across.to_pixels(point.across), up.to_pixels(point.up)
            primitives.append(Ellipse(item.role, cx=x, cy=y, rx=radius, ry=radius))
            label = _place_label(
                Position(text=point.text, across=point.across, up=point.up, role=item.role),
                x,
                y,
                placed,
                drawn,
                theme,
                measurer,
                plot_left,
                plot_right,
                plot_top,
                plot_bottom,
            )
            if label is None:
                raise FitError(
                    f"the waypoint {point.text[:32]!r} has nowhere to sit that is inside "
                    f"the plot and clear of the curves. Move it, shorten it, or give the "
                    f"diagram more room."
                )
            box, primitive = label
            placed.append(box)
            primitives.append(primitive)

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _smooth(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """A Catmull-Rom spline through every point, sampled into a polyline.

    Through, not near: a waypoint is a named place on the curve, and a spline
    that merely approached it would put the marker off the line — the one defect
    this family already forbids. Two points stay a straight line, which is what
    an "ideal" burn-down is and what smoothing it would spoil.
    """
    if len(points) < 3:
        return tuple(points)
    padded = [points[0], *points, points[-1]]
    sampled: list[tuple[float, float]] = [points[0]]
    for first, second, third, fourth in zip(
        padded, padded[1:], padded[2:], padded[3:], strict=False
    ):
        for step in range(1, CURVE_STEPS + 1):
            fraction = step / CURVE_STEPS
            squared = fraction * fraction
            cubed = squared * fraction
            sampled.append(
                (
                    0.5
                    * (
                        2 * second[0]
                        + (-first[0] + third[0]) * fraction
                        + (2 * first[0] - 5 * second[0] + 4 * third[0] - fourth[0]) * squared
                        + (-first[0] + 3 * second[0] - 3 * third[0] + fourth[0]) * cubed
                    ),
                    0.5
                    * (
                        2 * second[1]
                        + (-first[1] + third[1]) * fraction
                        + (2 * first[1] - 5 * second[1] + 4 * third[1] - fourth[1]) * squared
                        + (-first[1] + 3 * second[1] - 3 * third[1] + fourth[1]) * cubed
                    ),
                )
            )
    return tuple(sampled)
