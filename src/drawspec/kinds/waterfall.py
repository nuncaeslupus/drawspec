"""The `waterfall` kind: from one total to another, step by step — the bridge chart.

A layout family of its own that borrows the chart kind's ticks. Every bar is
placed by arithmetic on one vertical scale, so the only decisions made here are
where the numbers and the names go.

**Bars** stand one to a band, left to right in the order written. A total runs
from zero to its value; a step floats from the running sum before it to the
sum after it, so a bridge below zero hangs from the zero line and one that
crosses it is drawn across it. Totals, rises and falls take the first three of
the theme's mark fills: told apart in greyscale by pattern, and again by the
sign written on every step and by which way the bar travels.

**Connectors** are thin dashed lines at each running sum, from one bar to the
next, so the eye can follow the level between them.

**Numbers** are written beyond each bar's far end — above a rise or a positive
total, under a fall or a negative one — in the label size, signed on the steps
with a true minus sign, with as many decimals as the most precise bar. A number
that would sit on the zero line goes to the bar's other end instead. A number is
kept to its bar's band, so it cannot reach a neighbour.

**Names** are wrapped to their band under the plot; the axis label is rotated
beside the ticks, as on every chart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from drawspec.charts import AXIS_ROLE, CHART_ASPECT, FURNITURE_ROLE, TARGET_TICKS, _nice_step
from drawspec.errors import FitError
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextRun, TextSpan
from drawspec.schema import Document, WaterfallBar
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The role a connector between two bars is drawn in: dashed and headless, so it
#: reads as a level to follow rather than as another bar or an arrow.
CONNECTOR_ROLE: Final = "weak"

#: The most decimals a bar's number may carry. Past this the label is wider than
#: its band, and figures that precise belong in a table.
MAXIMUM_DECIMALS: Final = 3

#: The true minus sign: a hyphen is shorter than a plus and reads as a dash.
MINUS: Final = "\N{MINUS SIGN}"

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class WaterfallDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    bars: tuple[Box, ...] = ()
    """Each bar's left, top, right, bottom, left to right."""

    labels: tuple[Box, ...] = ()
    """Each bar's number, left to right."""

    names: tuple[Box, ...] = ()
    """Each bar's name under the plot, left to right."""

    connectors: tuple[tuple[float, float, float], ...] = ()
    """Each connector's left, right and height on the page."""

    zero: float = 0.0
    """Where the zero line is on the page."""

    sorts: tuple[str, ...] = ()
    """Each bar's sort: `total`, `rise` or `fall`."""


def waterfall_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a waterfall."""
    return waterfall_drawing(document, theme, measurer).scene


def waterfall_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> WaterfallDrawing:
    """Lay the waterfall out on the canvas.

    Raises:
        FitError: a name has a word wider than its band, a number is wider than
            its band, or the canvas leaves no room for the plot.
    """
    bars = document.waterfall_bars
    width = document.width if document.width else theme.canvas.width
    height = document.height if document.height else width * CHART_ASPECT
    size = theme.scale["label"]
    font = theme.font.default
    gap = theme.box.padding.top
    tick = theme.edge.head_length
    clearance = theme.edge.clearance
    line = measurer.measure("0", font, size)

    # The running sums: each bar's two ends, and which way it goes.
    spans: list[tuple[float, float]] = []
    sorts: list[str] = []
    running = 0.0
    for bar in bars:
        if bar.total is not None:
            running = bar.total
            spans.append((0.0, running))
            sorts.append("total")
        else:
            amount = bar.amount or 0.0
            spans.append((running, running + amount))
            sorts.append("rise" if amount > 0 else "fall")
            running += amount
    levels = [value for span in spans for value in span]
    step = _nice_step((max(levels) - min(levels)) / TARGET_TICKS)
    low = math.floor(min(levels) / step + 1e-9) * step
    high = math.ceil(max(levels) / step - 1e-9) * step
    if high <= low:
        high = low + step
    ticks = _ticks(low, high, step)

    decimals = _decimals(bars)
    numbers = [_number(bar, decimals) for bar in bars]

    # The gutters, measured: the rotated axis label, the tick numbers, the ticks.
    widest = max(measurer.measure(text, font, size).width for _, text in ticks)
    plot_left = line.height + gap + widest + gap + tick
    plot_right = width - line.height
    band = (plot_right - plot_left) / len(bars)
    bar_width = band * (1 - theme.mark.gap)
    room = band - 2 * clearance

    names: list[TextBlock] = []
    for bar in bars:
        try:
            names.append(wrap(bar.text, max(room, 1.0), measurer, theme=theme, level="label"))
        except FitError as error:
            raise FitError(
                f"the name {bar.text!r} has a word wider than the {room:.0f} units each of "
                f"{len(bars)} bars gets. Shorten it, give the diagram more width, or use "
                f"fewer bars — split the bridge at a subtotal."
            ) from error
    for bar, text in zip(bars, numbers, strict=True):
        wide = measurer.measure(text, font, size).width
        if wide > band - clearance:
            raise FitError(
                f"the number {text!r} on {bar.text!r} is {wide:.0f} units wide, and each of "
                f"{len(bars)} bars has {band:.0f}. Round the figures, give the diagram more "
                f"width, or use fewer bars."
            )

    tallest = max(block.height for block in names)
    label_room = line.height + clearance
    value_top = label_room
    value_bottom = height - gap - tallest - label_room
    if value_bottom - value_top < 4 * line.height:
        raise FitError(
            f"a waterfall {width:.0f} x {height:.0f} has no room left for its bars once the "
            f"names under them are measured. Give the diagram more height, or shorten the "
            f"names."
        )

    def y_of(value: float) -> float:
        return value_bottom + (value_top - value_bottom) * (value - low) / (high - low)

    zero = y_of(0.0)

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    boxes: list[Box] = []
    labels: list[Box] = []
    fills = {"total": 0, "rise": 1, "fall": 2}
    for index, (bar, (start, end), sort) in enumerate(zip(bars, spans, sorts, strict=True)):
        middle = plot_left + band * (index + 0.5)
        left, right = middle - bar_width / 2, middle + bar_width / 2
        top, bottom = y_of(max(start, end)), y_of(min(start, end))
        boxes.append((left, top, right, bottom))
        fill = fills[sort]
        primitives.append(
            Polygon(
                "emphasis" if bar.role == "emphasis" else "step",
                points=((left, top), (right, top), (right, bottom), (left, bottom)),
                fill=theme.mark.fill_for(fill),
                fill_colour=theme.mark.colour_for(fill),
            )
        )
        text = numbers[index]
        wide = measurer.measure(text, font, size).width
        up = end > start if sort != "total" else end >= 0
        box = _beside(middle, wide, line.height, top if up else bottom, up, clearance)
        if box[1] - clearance < zero < box[3] + clearance:
            box = _beside(middle, wide, line.height, bottom if up else top, not up, clearance)
        labels.append(box)
        texts.append(
            TextRun(
                FURNITURE_ROLE,
                x=middle,
                y=box[1] + line.ascent,
                text=text,
                level="label",
                font=font,
                anchor="middle",
                weight="bold" if bar.role == "emphasis" else "normal",
            )
        )

    connectors: list[tuple[float, float, float]] = []
    for index in range(len(bars) - 1):
        level = y_of(spans[index][1])
        start_x, end_x = boxes[index][2], boxes[index + 1][0]
        connectors.append((start_x, end_x, level))
        primitives.append(Path(CONNECTOR_ROLE, points=((start_x, level), (end_x, level))))

    # The axis, its ticks and numbers, and the zero line every total stands on.
    axis_top, axis_bottom = y_of(high), y_of(low)
    furniture: list[Primitive] = [
        Path(AXIS_ROLE, points=((plot_left, axis_top), (plot_left, axis_bottom))),
        Path(AXIS_ROLE, points=((plot_left, zero), (plot_right, zero))),
    ]
    for value, text in ticks:
        y = y_of(value)
        furniture.append(Path(AXIS_ROLE, points=((plot_left - tick, y), (plot_left, y))))
        texts.append(
            TextRun(
                FURNITURE_ROLE,
                x=plot_left - tick - gap,
                y=y + (line.ascent - line.descent) / 2,
                text=text,
                level="label",
                font=font,
                anchor="end",
            )
        )
    texts.append(
        TextRun(
            FURNITURE_ROLE,
            x=line.ascent,
            y=(axis_top + axis_bottom) / 2,
            text=document.waterfall_label,
            level="label",
            font=font,
            anchor="middle",
            rotate=-90.0,
        )
    )

    # The names, each centred under its band.
    name_top = value_bottom + label_room + gap
    placed: list[Box] = []
    for index, block in enumerate(names):
        middle = plot_left + band * (index + 0.5)
        placed.append(
            (middle - block.width / 2, name_top, middle + block.width / 2, name_top + block.height)
        )
        texts.extend(_centred(block, middle, name_top))

    scene = Scene(
        width=width,
        height=height,
        primitives=(*primitives, *furniture, *texts),
        title=document.title,
        description=document.description,
    )
    return WaterfallDrawing(
        scene=scene,
        bars=tuple(boxes),
        labels=tuple(labels),
        names=tuple(placed),
        connectors=tuple(connectors),
        zero=zero,
        sorts=tuple(sorts),
    )


def _beside(middle: float, wide: float, tall: float, edge: float, above: bool, gap: float) -> Box:
    """A number's box, centred on `middle`, beyond `edge`: above it or under it."""
    top = edge - gap - tall if above else edge + gap
    return (middle - wide / 2, top, middle + wide / 2, top + tall)


def _ticks(low: float, high: float, step: float) -> tuple[tuple[float, str], ...]:
    """Every multiple of `step` from `low` to `high`, written with a true minus."""
    decimals = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    found: list[tuple[float, str]] = []
    count = round((high - low) / step)
    for index in range(count + 1):
        value = round(low + index * step, 10)
        text = f"{abs(value):.{decimals}f}"
        if value < 0 and float(text) != 0:
            text = MINUS + text
        found.append((value, text))
    return tuple(found)


def _decimals(bars: tuple[WaterfallBar, ...]) -> int:
    """As many decimals as the most precise figure written, and no more."""
    most = 0
    for bar in bars:
        value = bar.total if bar.total is not None else bar.amount
        if value is None:
            continue
        for decimals in range(MAXIMUM_DECIMALS + 1):
            if math.isclose(value, round(value, decimals), abs_tol=1e-9):
                most = max(most, decimals)
                break
        else:
            most = MAXIMUM_DECIMALS
    return most


def _number(bar: WaterfallBar, decimals: int) -> str:
    """A bar's figure: a total as it is, a step signed, a minus a true minus."""
    value = bar.total if bar.total is not None else bar.amount or 0.0
    text = f"{abs(value):.{decimals}f}"
    if value < 0:
        return MINUS + text
    return ("+" + text) if bar.total is None else text


def _centred(block: TextBlock, x: float, top: float) -> list[TextLine]:
    """A wrapped name centred on `x`, from `top` down, its spans kept."""
    lines: list[TextLine] = []
    for index, wrapped in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in wrapped.spans
            if span.text
        )
        if spans:
            lines.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="label",
                    anchor="middle",
                )
            )
    return lines


__all__ = ["WaterfallDrawing", "waterfall_drawing", "waterfall_scene"]
