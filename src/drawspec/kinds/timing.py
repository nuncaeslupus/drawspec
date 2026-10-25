"""The `timing` kind: signals over one shared time axis, a lane each.

A layout family of its own, and the one a datasheet's SPI or I²C figure, a
WaveDrom waveform and a UML timing diagram share: names down the left, one time
axis across, and every lane read against the same steps.

**Time is counted in equal steps.** Every signal has one value per step and every
lane runs the whole axis, so an edge on one lane lines up with the edge it causes
on another without anyone placing it. The steps are not to scale in seconds:
what a figure measures, it names — an `intervals` entry from one edge to another,
drawn as an arrow under its signal with the name over it, as a datasheet writes
`tSU;STA` — and a `markers` entry rules one edge across every lane.

**Three lanes, three pictures.**

* A `bit` lane is a level: high, low, the middle line of high impedance (`z`), a
  hatched box for unknown (`x`), and the two halves of a clock pulse (`p` high
  then low, `n` low then high). Its edges are upright, as a level's are.
* A `bus` lane is a run of words, each in the hexagon a datasheet draws a value
  in: the slant where one word gives way to the next is the theme's `[timing]
  slew`, a share of the step, so the crossings line up with the bit lanes'
  edges. Unknown is hatched, high impedance the middle line.
* A `state` lane is UML's robust lifeline: the named states as levels, top to
  bottom in the order written, and a line stepping between them.

`.` carries a step on: a clock keeps pulsing, a word holds without a new edge.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import AXIS_ROLE, FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import TIMING_HOLD, Document, TimingSignal
from drawspec.text.measure import TextMeasurer
from drawspec.textgrid import (
    STRAIGHT,
    Grid,
    caption_lines,
    cells,
    finished,
    label_lines,
    too_wide,
)
from drawspec.theme import Theme

#: The waveform's own line: a level, a pulse, a state line, a word's hexagon.
WAVE_ROLE: Final = "flow"

#: A marker ruled across every lane, and the faint step grid when the theme asks.
MARKER_ROLE: Final = "weak"
GRID_ROLE: Final = "aside"

#: An interval's arrow (its shaft) and the guides dropped from the edges it spans.
SPAN_ROLE: Final = AXIS_ROLE
GUIDE_ROLE: Final = "aside"

#: Lengths in units, a unit being the body size over eleven.
MIN_STEP: Final = 10.0
"""The narrowest a step may be drawn: half of it is a clock's high, and below
five units that is a comb rather than a pulse."""

SLEW_MAX: Final = 4.0
"""The most a slanted change may take, whatever the step: a wide step's slant
stays a crossing rather than a ramp."""

#: The height of a `bit` or `bus` lane, in body line heights.
LANE_LINES: Final = 1.5

#: The gap between two lanes, in body line heights.
LANE_GAP_LINES: Final = 0.85

#: The distance between two levels of a `state` lane, in label line heights.
STATE_PITCH: Final = 1.25


@dataclass(frozen=True)
class TimingDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    plot: tuple[float, float] = (0.0, 0.0)
    """Where the time axis starts and ends, left to right."""

    step: float = 0.0
    """How wide one step is drawn."""

    lanes: tuple[tuple[float, float], ...] = ()
    """Each signal's lane, top to bottom: high level to low level."""

    texts: tuple[tuple[float, float, float, float], ...] = field(default=())
    """Every piece of text placed, left, top, right, bottom — for the overlap tests."""


def timing_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a timing figure."""
    return timing_drawing(document, theme, measurer).scene


def expand(values: Sequence[str]) -> list[str]:
    """`values` with every `.` replaced by the value it carries on."""
    out: list[str] = []
    for value in values:
        out.append(out[-1] if value == TIMING_HOLD and out else value)
    return out


#: The two halves of each `bit` value: the level for the first half step, then the second.
_BIT_HALVES: Final = {
    "0": ("lo", "lo"),
    "1": ("hi", "hi"),
    "z": ("z", "z"),
    "x": ("x", "x"),
    "p": ("hi", "lo"),
    "n": ("lo", "hi"),
}


def bit_runs(values: Sequence[str]) -> list[tuple[str, int, int]]:
    """A `bit` lane as runs of one level, `(level, first, end)` in half steps."""
    halves = [half for value in expand(values) for half in _BIT_HALVES[value]]
    return _runs(halves)


def word_runs(values: Sequence[str]) -> list[tuple[str, int, int, int]]:
    """A `bus` or `state` lane as runs, `(value, first, end, written)` in steps.

    A `.` holds the run before; any written value starts a new one, so the same
    word written twice is two words with an edge between them. `written` is the
    step the run's value was written at, for a refusal's pointer.
    """
    runs: list[tuple[str, int, int, int]] = []
    for step, value in enumerate(values):
        if value == TIMING_HOLD and runs:
            text, first, _, written = runs[-1]
            runs[-1] = (text, first, step + 1, written)
        else:
            runs.append((value, step, step + 1, step))
    return runs


def state_runs(values: Sequence[str]) -> list[tuple[str, int, int]]:
    """A `state` lane as runs of one state, `(state, first, end)` in steps."""
    return _runs(expand(values))


def _runs(levels: Sequence[str]) -> list[tuple[str, int, int]]:
    runs: list[tuple[str, int, int]] = []
    for index, level in enumerate(levels):
        if runs and runs[-1][0] == level:
            runs[-1] = (level, runs[-1][1], index + 1)
        else:
            runs.append((level, index, index + 1))
    return runs


def _line(
    text: str, x: float, baseline: float, level: str, anchor: str, font: str, weight: str = "normal"
) -> TextLine:
    return TextLine(
        FURNITURE_ROLE,
        x=x,
        y=baseline,
        spans=(TextSpan(text=text, font=font, weight=weight),),
        level=level,
        anchor=anchor,
    )


def _pack(extents: Sequence[tuple[float, float]], gap: float) -> list[int]:
    """The row each `(left, right)` extent goes in, so no two in a row come within `gap`."""
    rows: list[float] = []
    placed: list[int] = []
    for left, right in extents:
        for row, end in enumerate(rows):
            if left >= end + gap:
                rows[row] = right
                placed.append(row)
                break
        else:
            rows.append(right)
            placed.append(len(rows) - 1)
    return placed


def timing_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> TimingDrawing:
    """Lay the lanes out under one time axis.

    Raises:
        FitError: the steps are too narrow at this width, or a word on a bus does
            not fit the steps it holds for.
    """
    width = document.width if document.width else theme.canvas.width
    signals = document.timing_signals
    steps = len(signals[0].values)
    body = theme.scale["body"]
    label = theme.scale["label"]
    unit = body / 11
    font = theme.font.default
    line = measurer.measure("Ag", font, body)
    small = measurer.measure("Ag", font, label)
    gap = theme.box.padding.top
    style = theme.timing

    def wide(text: str, size: float, weight: str = "normal") -> float:
        return measurer.measure(text, font, size, weight).width

    def middle(baseline_of: float, extents_height: float) -> float:
        """A baseline that centres a line of `extents_height` on `baseline_of`."""
        return baseline_of + extents_height / 2

    # -- the columns: names, state names, then the plot ----------------------
    grouped = any(signal.group for signal in signals)
    indent = gap * 1.2 if grouped else 0.0
    name_width = max(
        [wide(signal.text, body) + (indent if signal.group else 0.0) for signal in signals]
        + [wide(signal.group, body, "bold") for signal in signals if signal.group]
    )
    state_width = max(
        (wide(state, label) for signal in signals for state in signal.states), default=0.0
    )
    left = name_width + gap * 1.5 + (state_width + gap * 0.6 if state_width else 0.0)
    plot_width = width - left
    step = plot_width / steps
    if step < MIN_STEP * unit:
        widest = max(range(len(signals)), key=lambda index: wide(signals[index].text, body))
        raise FitError(
            f"/signals/{widest}/text: {steps} steps get {max(step, 0):.1f} units each once the "
            f"names are measured, and a step needs {MIN_STEP * unit:.0f} to draw a pulse. "
            f"Shorten the longest name, draw fewer steps, or widen the diagram."
        )
    slew = min(style.slew * step, SLEW_MAX * unit)

    def at(edge: float) -> float:
        return left + edge * step

    primitives: list[Primitive] = []
    regions: list[Primitive] = []
    texts: list[Primitive] = []
    boxes: list[tuple[float, float, float, float]] = []

    def text_at(
        text: str, x: float, baseline: float, level: str, anchor: str, weight: str = "normal"
    ) -> None:
        size = theme.scale[level]
        extent = measurer.measure(text, font, size, weight)
        texts.append(_line(text, x, baseline, level, anchor, font, weight))
        start = x - extent.width / 2 if anchor == "middle" else x
        if anchor == "end":
            start = x - extent.width
        boxes.append(
            (start, baseline - extent.ascent, start + extent.width, baseline + extent.descent)
        )

    margin = theme.canvas.margin

    def kept(centre: float, half: float) -> float:
        """`centre` moved so a label `2 * half` wide stays within the canvas and its margin."""
        return max(-margin + half, min(centre, width + margin - half))

    # -- the marker names, packed into rows over the figure -------------------
    y = 0.0
    markers = document.timing_markers
    named = [marker for marker in markers if marker.text]
    marker_centres = [kept(at(marker.at), wide(marker.text, label) / 2) for marker in named]
    marker_rows = _pack(
        [
            (centre - wide(marker.text, label) / 2, centre + wide(marker.text, label) / 2)
            for marker, centre in zip(named, marker_centres, strict=True)
        ],
        gap * 0.6,
    )
    row_height = small.height + unit * 2
    for marker, centre, row in zip(named, marker_centres, marker_rows, strict=True):
        text_at(marker.text, centre, y + row * row_height + small.ascent, "label", "middle")
    if named:
        y += (max(marker_rows) + 1) * row_height + unit * 2

    # -- the lanes -------------------------------------------------------------
    lane_height = line.height * LANE_LINES
    lane_gap = line.height * LANE_GAP_LINES
    pitch = small.height * STATE_PITCH
    lanes: list[tuple[float, float]] = []
    lanes_top = y
    group_tops: dict[str, tuple[float, float]] = {}
    by_signal: dict[str, list[int]] = {}
    for position, interval in enumerate(document.timing_intervals):
        by_signal.setdefault(interval.signal or signals[-1].text, []).append(position)

    for index, signal in enumerate(signals):
        if signal.group and signal.group not in group_tops:
            text_at(signal.group, 0.0, y + line.ascent, "body", "start", "bold")
            y += line.height * 1.15
            group_tops[signal.group] = (y, y)
        top = y
        height = (len(signal.states) - 1) * pitch if signal.lane == "state" else lane_height
        bottom = top + height
        lanes.append((top, bottom))
        name_x = indent if signal.group else 0.0
        text_at(
            signal.text,
            name_x,
            middle((top + bottom) / 2, line.ascent - line.descent),
            "body",
            "start",
        )
        pointer = f"/signals/{index}/values"
        if signal.lane == "bit":
            _bit_lane(signal, top, bottom, at, regions, primitives)
        elif signal.lane == "bus":
            for word, centre, room, held, written in _bus_lane(
                signal, top, bottom, at, slew, steps, regions, primitives
            ):
                room -= unit * 3
                for level in ("body", "label"):
                    extent = measurer.measure(word, font, theme.scale[level])
                    if extent.width <= room:
                        baseline = middle((top + bottom) / 2, extent.ascent - extent.descent)
                        text_at(word, centre, baseline, level, "middle")
                        break
                else:
                    raise FitError(
                        f"{pointer}/{written}: the word {word!r} needs {extent.width:.0f} units "
                        f"and its {held} step{'s' if held != 1 else ''} give {max(room, 0):.0f} "
                        f"({step:.0f} a step). Hold it for more steps with `.`, shorten it, or "
                        f"widen the diagram."
                    )
        else:
            levels = {state: top + k * pitch for k, state in enumerate(signal.states)}
            for state, level_y in levels.items():
                text_at(
                    state,
                    left - gap * 0.6,
                    middle(level_y, small.ascent - small.descent),
                    "label",
                    "end",
                )
            _state_lane(signal, levels, at, primitives)
        if signal.group:
            group_tops[signal.group] = (group_tops[signal.group][0], bottom)
        y = bottom

        # The intervals measured on this signal, in rows under its lane.
        mine = [document.timing_intervals[position] for position in by_signal.get(signal.text, [])]
        if mine:
            extents = []
            for interval in mine:
                a, b = at(interval.start), at(interval.end)
                half = wide(interval.text, label) / 2
                centre = kept((a + b) / 2, half)
                extents.append((min(a + unit, centre - half), max(b - unit, centre + half)))
            rows = _pack(extents, unit * 1.5)
            span_height = small.height + unit * 7
            base = y + unit * 5
            for interval, row in zip(mine, rows, strict=True):
                a, b = at(interval.start), at(interval.end)
                row_top = base + row * span_height
                arrow_y = row_top + small.height + unit * 3
                half = wide(interval.text, label) / 2
                text_at(
                    interval.text,
                    kept((a + b) / 2, half),
                    row_top + small.ascent,
                    "label",
                    "middle",
                )
                _arrow(a, b, arrow_y, theme, unit, primitives)
                for x in (a, b):
                    primitives.append(Path(GUIDE_ROLE, points=((x, top), (x, arrow_y + unit * 2))))
            y = base + (max(rows) + 1) * span_height
        y += lane_gap
    lanes_bottom = lanes[-1][1]

    # Group brackets: a thin rule down the left of each group's names.
    for top, bottom in group_tops.values():
        x = indent * 0.35
        primitives.append(Path(AXIS_ROLE, points=((x, top), (x, bottom))))

    # Markers, and the step grid when the theme asks for it.
    figure_bottom = y - lane_gap
    for marker in markers:
        primitives.append(
            Path(
                MARKER_ROLE,
                points=(
                    (at(marker.at), lanes_top - unit * 2),
                    (at(marker.at), lanes_bottom + unit * 2),
                ),
            )
        )
    if style.grid:
        for edge in range(steps + 1):
            primitives.append(
                Path(GRID_ROLE, points=((at(edge), lanes_top), (at(edge), lanes_bottom)))
            )

    # -- the step names, under an axis ---------------------------------------
    if document.timing_ticks:
        axis = figure_bottom + lane_gap * 0.8
        primitives.append(Path(AXIS_ROLE, points=((at(0), axis), (at(steps), axis))))
        for edge in range(steps + 1):
            primitives.append(
                Path(AXIS_ROLE, points=((at(edge), axis), (at(edge), axis + unit * 3)))
            )
        previous = -math.inf
        for position, tick in enumerate(document.timing_ticks):
            if not tick:
                continue
            half = wide(tick, label) / 2
            centre = kept(at(position + 0.5), half)
            if centre - half < previous + unit * 2 or 2 * half > width + 2 * margin:
                raise FitError(
                    f"/ticks/{position}: the step name {tick!r} is {2 * half:.0f} units wide and "
                    f"a step is {step:.0f}, so it runs into the name beside it. Shorten it, name "
                    f"fewer steps (an empty string leaves one unnamed), or widen the diagram."
                )
            previous = centre + half
            text_at(tick, centre, axis + unit * 4 + small.ascent, "label", "middle")
        figure_bottom = axis + unit * 4 + small.height

    scene = Scene(
        width=width,
        height=figure_bottom,
        primitives=(*regions, *primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return TimingDrawing(
        scene=scene,
        plot=(left, width),
        step=step,
        lanes=tuple(lanes),
        texts=tuple(boxes),
    )


def _bit_lane(
    signal: TimingSignal,
    top: float,
    bottom: float,
    place: Callable[[float], float],
    regions: list[Primitive],
    primitives: list[Primitive],
) -> None:
    """A level line: high, low, the middle for `z`, hatched boxes for `x`; edges upright."""
    levels = {"hi": top, "lo": bottom, "z": (top + bottom) / 2}
    points: list[tuple[float, float]] = []
    for level, first, end in bit_runs(signal.values):
        x0, x1 = place(first / 2), place(end / 2)
        if level == "x":
            if len(points) > 1:
                primitives.append(Path(WAVE_ROLE, points=tuple(points)))
            points = []
            box = ((x0, top), (x1, top), (x1, bottom), (x0, bottom))
            regions.append(Polygon(FURNITURE_ROLE, points=box, fill="hatch", region=True))
            primitives.append(Path(WAVE_ROLE, points=(*box, (x0, top))))
            continue
        level_y = levels[level]
        points.append((x0, level_y))
        points.append((x1, level_y))
    if len(points) > 1:
        primitives.append(Path(WAVE_ROLE, points=tuple(points)))


def _state_lane(
    signal: TimingSignal,
    levels: dict[str, float],
    place: Callable[[float], float],
    primitives: list[Primitive],
) -> None:
    """UML's robust lifeline: a line on its state's level, stepping between them."""
    points: list[tuple[float, float]] = []
    for state, first, end in state_runs(signal.values):
        level_y = levels[state]
        points.append((place(first), level_y))
        points.append((place(end), level_y))
    primitives.append(Path(WAVE_ROLE, points=tuple(points)))


def _bus_lane(
    signal: TimingSignal,
    top: float,
    bottom: float,
    place: Callable[[float], float],
    slew: float,
    steps: int,
    regions: list[Primitive],
    primitives: list[Primitive],
) -> list[tuple[str, float, float, int, int]]:
    """A run of words, each in its hexagon; `x` hatched, `z` the middle line.

    Returns each word to be written: the word, its centre, the room inside its
    hexagon, how many steps it holds for, and the step it was written at.
    """
    mid = (top + bottom) / 2
    words: list[tuple[str, float, float, int, int]] = []
    for value, first, end, written in word_runs(signal.values):
        x0, x1 = place(first), place(end)
        if value == "z":
            primitives.append(Path(WAVE_ROLE, points=((x0, mid), (x1, mid))))
            continue
        s0 = slew if first > 0 else 0.0
        s1 = slew if end < steps else 0.0
        hexagon = (
            (x0, mid),
            (x0 + s0, top),
            (x1 - s1, top),
            (x1, mid),
            (x1 - s1, bottom),
            (x0 + s0, bottom),
        )
        if value == "x":
            regions.append(Polygon(FURNITURE_ROLE, points=hexagon, fill="hatch", region=True))
        primitives.append(Path(WAVE_ROLE, points=(*hexagon, hexagon[0])))
        if value != "x":
            words.append((value, (x0 + x1) / 2, x1 - x0 - s0 - s1, end - first, written))
    return words


def _arrow(
    a: float, b: float, y: float, theme: Theme, unit: float, primitives: list[Primitive]
) -> None:
    """A double-headed arrow from `a` to `b` at height `y`, heads filled."""
    head = min(theme.head_length_for("flow") * 0.75, (b - a) / 2.5)
    across = max(head * 0.42, unit * 1.2)
    primitives.append(Path(SPAN_ROLE, points=((a + head * 0.5, y), (b - head * 0.5, y))))
    primitives.append(
        Polygon("flow", points=((a, y), (a + head, y - across), (a + head, y + across)))
    )
    primitives.append(
        Polygon("flow", points=((b, y), (b - head, y - across), (b - head, y + across)))
    )


# ---------------------------------------------------------------------------
# Text: the lanes on a character grid
# ---------------------------------------------------------------------------

#: The fill of an unknown (`x`) stretch, per charset.
TEXT_UNKNOWN: Final = {"unicode": "░", "ascii": "x"}

#: A marker's line through the blank cells of a figure, per charset.
TEXT_MARKER: Final = {"unicode": "┆", "ascii": ":"}

#: An interval's ends and shaft, per charset: left end, right end.
TEXT_SPAN_ENDS: Final = {"unicode": ("├", "┤"), "ascii": ("|", "|")}

#: The fewest cells a step takes: an even number, so a clock's half is whole cells.
TEXT_STEP_MIN: Final = 4


@dataclass
class _Placed:
    """What decides a column of the text figure: its last cell, pointer and words."""

    right: int
    pointer: str
    what: str


def timing_text(document: Document, width: int, charset: str) -> str:
    """A `timing` figure as plain text: the lanes on a character grid.

    Each step is the same whole number of cells, an even one so a clock pulse
    splits into whole halves; it widens until every word on a bus fits its run
    and every step name fits its step. A `bit` or `bus` lane takes three rows —
    high, middle, low — and a `state` lane a row per state. Edges are box-drawing
    junctions, `x` is shaded, markers rule the blank cells, and intervals are
    `├─ name ─┤` under their signal.

    Raises:
        FitError: the figure is wider than `width`, at the thing that made it so.
    """
    signals = document.timing_signals
    steps = len(signals[0].values)
    names = [
        label_lines(signal.text, charset, f"/signals/{i}/text")[0]
        for i, signal in enumerate(signals)
    ]
    grouped = any(signal.group for signal in signals)
    indent = 2 if grouped else 0
    groups = {
        signal.group: label_lines(signal.group, charset, f"/signals/{i}/group")[0]
        for i, signal in enumerate(signals)
        if signal.group
    }
    states = {
        (i, state): label_lines(state, charset, f"/signals/{i}/states/{k}")[0]
        for i, signal in enumerate(signals)
        for k, state in enumerate(signal.states)
    }
    name_width = max(
        [
            cells(name) + (indent if signal.group else 0)
            for name, signal in zip(names, signals, strict=True)
        ]
        + [cells(group) for group in groups.values()]
    )
    state_width = max((cells(state) for state in states.values()), default=0)
    left = name_width + 2 + (state_width + 1 if state_width else 0)

    # The step: wide enough for each bus word in its run and each step name in its step.
    per_step = TEXT_STEP_MIN
    decided = _Placed(0, "/signals/0/values", f"the {steps} steps")
    words: dict[tuple[int, int], str] = {}
    for i, signal in enumerate(signals):
        if signal.lane != "bus":
            continue
        for value, first, end, written in word_runs(signal.values):
            if value in ("x", "z"):
                continue
            word = label_lines(value, charset, f"/signals/{i}/values/{written}")[0]
            words[(i, first)] = word
            need = math.ceil((cells(word) + 1) / (end - first))
            if need > per_step:
                per_step = need
                decided = _Placed(0, f"/signals/{i}/values/{written}", f"the word {word!r}")
    ticks = [
        label_lines(tick, charset, f"/ticks/{position}")[0] if tick else ""
        for position, tick in enumerate(document.timing_ticks)
    ]
    # A step name may run on over the unnamed steps after it, up to the next name.
    named_at = [position for position, tick in enumerate(ticks) if tick]
    for position, following in zip(named_at, [*named_at[1:], steps], strict=False):
        need = math.ceil((cells(ticks[position]) + 1) / (following - position))
        if need > per_step:
            per_step = need
            decided = _Placed(0, f"/ticks/{position}", f"the step name {ticks[position]!r}")
    per_step += per_step % 2
    half = per_step // 2

    def column(edge: float) -> int:
        return left + round(edge * 2) * half

    grid = Grid(charset)
    placed: list[_Placed] = [
        _Placed(column(steps), decided.pointer, f"{decided.what}, at {per_step} columns a step,")
    ]

    # Marker names over the figure, packed into rows.
    row = 0
    named = [
        (position, marker) for position, marker in enumerate(document.timing_markers) if marker.text
    ]
    texts = [
        label_lines(marker.text, charset, f"/markers/{position}/text")[0]
        for position, marker in named
    ]
    marker_starts = [
        column(marker.at) - cells(text) // 2 for (_, marker), text in zip(named, texts, strict=True)
    ]
    marker_rows = _pack(
        [(start, start + cells(text)) for start, text in zip(marker_starts, texts, strict=True)], 1
    )
    for (position, _), text, start, line in zip(
        named, texts, marker_starts, marker_rows, strict=True
    ):
        grid.text(line, max(start, 0), text)
        placed.append(
            _Placed(
                max(start, 0) + cells(text), f"/markers/{position}/text", f"the marker {text!r}"
            )
        )
    if named:
        row = max(marker_rows) + 1

    by_signal: dict[str, list[int]] = {}
    for position, interval in enumerate(document.timing_intervals):
        by_signal.setdefault(interval.signal or signals[-1].text, []).append(position)

    lanes_top = row
    seen_groups: set[str] = set()
    lane_rows: list[tuple[int, int]] = []
    for i, signal in enumerate(signals):
        if signal.group and signal.group not in seen_groups:
            seen_groups.add(signal.group)
            grid.text(row, 0, groups[signal.group])
            row += 1
        rows = len(signal.states) if signal.lane == "state" else 3
        top, bottom = row, row + rows - 1
        lane_rows.append((top, bottom))
        name_row = top if signal.lane == "state" else top + 1
        grid.text(name_row, indent if signal.group else 0, names[i])
        if signal.lane == "bit":
            _text_bit(grid, signal, top, column, charset)
        elif signal.lane == "bus":
            _text_bus(grid, signal, top, column, steps, words, i, charset)
        else:
            for k, state in enumerate(signal.states):
                label = states[(i, state)]
                grid.text(top + k, left - 1 - cells(label), label)
            levels = {state: top + k for k, state in enumerate(signal.states)}
            points = state_runs(signal.values)
            for index, (state, first, end) in enumerate(points):
                grid.horizontal(levels[state], column(first), column(end))
                if index:
                    grid.vertical(column(first), levels[points[index - 1][0]], levels[state])
        row = bottom + 1
        mine = by_signal.get(signal.text, [])
        if mine:
            row = _text_intervals(grid, document, mine, row, column, charset, placed)
        row += 1
    lanes_bottom = lane_rows[-1][1]

    for marker in document.timing_markers:
        x = column(marker.at)
        for line in range(lanes_top, lanes_bottom + 1):
            if not grid.used(line, x):
                grid.text(line, x, TEXT_MARKER[charset])

    if ticks:
        for position, tick in enumerate(ticks):
            if tick:
                start = column(position) + max(per_step - cells(tick), 0) // 2
                grid.text(row, start, tick)
        row += 1

    lines = grid.lines()
    needed = max(cells(line) for line in lines)
    if needed > width:
        culprit = max(placed, key=lambda thing: thing.right)
        raise too_wide(culprit.pointer, culprit.what, needed, width)
    return finished(lines + caption_lines(document.caption, width, charset))


def _text_bit(
    grid: Grid, signal: TimingSignal, top: int, place: Callable[[float], int], charset: str
) -> None:
    """A level on three rows: high on the top, `z` in the middle, low on the bottom."""
    rows = {"hi": top, "z": top + 1, "lo": top + 2}
    previous: str | None = None
    for level, first, end in bit_runs(signal.values):
        c0, c1 = place(first / 2), place(end / 2)
        if level == "x":
            grid.horizontal(top, c0, c1)
            grid.horizontal(top + 2, c0, c1)
            grid.vertical(c0, top, top + 2)
            grid.vertical(c1, top, top + 2)
            for line in range(top, top + 3):
                for cell in range(c0 + 1, c1):
                    if line == top + 1:
                        grid.text(line, cell, TEXT_UNKNOWN[charset])
        else:
            grid.horizontal(rows[level], c0, c1)
            if previous is not None and previous != "x":
                grid.vertical(c0, rows[previous], rows[level])
            elif previous == "x":
                grid.arm(rows[level], c0, "e")
        previous = level


def _text_bus(
    grid: Grid,
    signal: TimingSignal,
    top: int,
    place: Callable[[float], int],
    steps: int,
    words: dict[tuple[int, int], str],
    index: int,
    charset: str,
) -> None:
    """Words in boxes on three rows, sharing their edges; `x` shaded, `z` the middle."""
    for value, first, end, _ in word_runs(signal.values):
        c0, c1 = place(first), place(end)
        if value == "z":
            grid.horizontal(top + 1, c0, c1)
            continue
        grid.horizontal(top, c0, c1)
        grid.horizontal(top + 2, c0, c1)
        grid.vertical(c0, top, top + 2)
        grid.vertical(c1, top, top + 2)
        if value == "x":
            for cell in range(c0 + 1, c1):
                grid.text(top + 1, cell, TEXT_UNKNOWN[charset])
        else:
            word = words[(index, first)]
            room = c1 - c0 - 1
            grid.text(top + 1, c0 + 1 + (room - cells(word)) // 2, word)
    del steps


def _text_intervals(
    grid: Grid,
    document: Document,
    mine: list[int],
    row: int,
    place: Callable[[float], int],
    charset: str,
    placed: list[_Placed],
) -> int:
    """Each interval as `├── name ──┤` from edge to edge, rows packed; the next free row."""
    start_end, end_end = TEXT_SPAN_ENDS[charset]
    shaft = STRAIGHT[charset]["light"][0]
    layouts: list[tuple[int, int, str, int, int]] = []
    for position in mine:
        interval = document.timing_intervals[position]
        a, b = place(interval.start), place(interval.end)
        text = label_lines(interval.text, charset, f"/intervals/{position}/text")[0]
        inside = b - a - 1 >= cells(text) + 2
        text_at = a + 1 + (b - a - 1 - cells(text)) // 2 if inside else b + 2
        right = b if inside else text_at + cells(text) - 1
        layouts.append((a, b, text, text_at, right))
        placed.append(_Placed(right + 1, f"/intervals/{position}/text", f"the interval {text!r}"))
    rows = _pack([(a, right) for a, _, _, _, right in layouts], 1)
    for (a, b, text, text_at, _), line in zip(layouts, rows, strict=True):
        where = row + line
        grid.text(where, a, start_end + shaft * (b - a - 1) + end_end)
        # Inside its arrow, the name is set off from the shaft by a space each side.
        inside = text_at < b
        grid.text(where, text_at - 1 if inside else text_at, f" {text} " if inside else text)
    return row + max(rows) + 1


__all__ = [
    "TimingDrawing",
    "bit_runs",
    "expand",
    "state_runs",
    "timing_drawing",
    "timing_scene",
    "timing_text",
    "word_runs",
]
