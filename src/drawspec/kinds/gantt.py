"""The `gantt` kind: a plan, one row per task, each an interval on one axis.

A layout family of its own, and a narrow one: nothing is ranked. Rows are in the
order written, because that order is the reading order; a bar's two ends are the
axis positions of its `start` and `end`, so every horizontal decision is the
scale's and every vertical one is a row's height.

**The label column** is as wide as the widest label, up to a share of the
canvas; a longer one wraps. An actor is the label's lead, as in a `flow` box.
A phase is a heading row, its name in bold over its tasks, which are indented
under it; a bracket in the plot spans the phase from its first start to its last
end.

**The axis** is the chart's, below the rows: ticks at a step a reader can do
arithmetic with, the label and its unit centred under the plot. With
`categories` the ticks are period boundaries and each name is centred in its
period, the way a plan by month is drawn.

**Dependencies** are finish-to-start, so each is drawn from the end of one bar
into the start of the other: a short run out of the source, down (or up) to the
target's row, and a straight run into it long enough that the head never sits on
the bar's corner. When the target starts too soon after the source ends for that,
the line turns back along the gap beside the target's row.

**Marks** are lines across every row, drawn in the theme's `[gantt] marks` role,
with their names above the first row; names that would touch take another line.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Final

from drawspec.charts import AXIS_ROLE, FURNITURE_ROLE, TARGET_TICKS, Scale, _nice_step, _ticks
from drawspec.errors import FitError
from drawspec.routing import Route, edge_primitives
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import Axis, Document, Task, _figure
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most of the canvas the label column may take. A longer label wraps.
LABEL_SHARE: Final = 0.34

#: The least of the canvas the plot may be left with before the plan is refused.
PLOT_SHARE: Final = 0.4

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
BAR: Final = 13.0
ROW_PAD: Final = 6.0
INDENT: Final = 12.0
OUT: Final = 7.0
RUN: Final = 7.0
COLUMN_GAP: Final = 10.0
BRACKET: Final = 5.0
MARK_GAP: Final = 4.0

#: How much taller than a bar a milestone is drawn, and an emphasised one.
MILESTONE: Final = 1.25
FOCAL: Final = 1.5

#: The role a phase's bracket is drawn in: a thin line with no head.
BRACKET_ROLE: Final = "link"

#: The task roles drawn heavier, and the role their outline takes.
HEAVY: Final = ("strong", "emphasis")


@dataclass(frozen=True)
class GanttDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    scale: Scale
    """The axis: a value's x is `scale.to_pixels(value)`."""

    bars: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    """Each interval's bar — left, top, right, bottom — by task id."""

    milestones: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Each milestone's centre, by task id."""

    routes: tuple[tuple[tuple[float, float], ...], ...] = ()
    """Each dependency's route, in document order: tail first, head last."""

    rows: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Each task's row — top, bottom — by task id."""

    marks: tuple[float, ...] = ()
    """Each mark's x, in document order."""


def gantt_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a plan."""
    return gantt_drawing(document, theme, measurer).scene


def gantt_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> GanttDrawing:
    """Lay the plan out on the canvas.

    Raises:
        FitError: the labels leave too little of the canvas for the plot, or a
            period's name cannot be broken to its share of the axis.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    axis = document.axes[0]
    label_size = theme.scale["label"]
    line = measurer.measure("0", theme.font.default, label_size)
    gap = theme.box.padding.top
    tick = theme.edge.head_length
    grouped = bool(document.groups)
    indent = INDENT * unit if grouped else 0.0

    # The label column: as wide as the widest label, up to its share.
    column = min(
        max(
            [_natural(_label(task), theme, measurer) + indent for task in document.tasks]
            + [_natural(_heading(group.text), theme, measurer) for group in document.groups]
        ),
        width * LABEL_SHARE,
    )
    blocks = {
        task.id: _wrapped(_label(task), column - indent, theme, measurer, lead=bool(task.actor))
        for task in document.tasks
    }
    headings = {
        group.id: _wrapped(_heading(group.text), column, theme, measurer)
        for group in document.groups
    }

    # The plot: what is left once the column, the gap a route turns back in, and
    # the gutter for the last tick's label and a route's run out are paid for.
    run = theme.widest_head + RUN * unit
    out = OUT * unit
    low, high = _range(document)
    ticks, names = _ticks_for(axis, low, high)
    plot_left = column + run + COLUMN_GAP * unit
    # A number is centred on its tick, so the last one reaches past the plot's end.
    tail = max(
        (measurer.measure(text, theme.font.default, label_size).width / 2 for _, text in ticks),
        default=0.0,
    )
    plot_right = width - max(tail, out + theme.edge.clearance)
    if plot_right - plot_left < width * PLOT_SHARE:
        raise FitError(
            f"the task labels leave {max(plot_right - plot_left, 0):.0f} of the canvas's "
            f"{width:.0f} units for the plan itself. Shorten the longest labels, or give the "
            f"diagram more width."
        )
    scale = Scale(low, high, plot_left, plot_right)

    period_blocks: list[TextBlock] = []
    if names:
        share = (plot_right - plot_left) / len(names) - theme.box.padding.horizontal
        for name in names:
            try:
                period_blocks.append(
                    wrap(name, max(share, 1.0), measurer, theme=theme, level="label")
                )
            except FitError as error:
                raise FitError(
                    f"the period {name!r} does not fit the {share:.0f} units each of the "
                    f"{len(names)} periods gets. Shorten it, or give the diagram more width."
                ) from error

    # Marks' names, each beside the top of its own line — right of it, or left at
    # the canvas's edge — a lane lower when it would touch another name or be
    # crossed by another mark's line, which runs down through every lane below
    # its own.
    beside = MARK_GAP * unit
    placed: list[tuple[float, int, float, float]] = []
    for mark in document.marks:
        wide = measurer.measure(mark.text, theme.font.default, label_size).width
        x = scale.to_pixels(mark.at)
        left = x + beside if x + beside + wide <= width else x - beside - wide
        right = left + wide
        lane = 0
        while any(
            (other_lane == lane and left < other_right + beside and other_left < right + beside)
            or (other_lane < lane and left - beside <= other_x <= right + beside)
            or (other_lane > lane and other_left - beside <= x <= other_right + beside)
            for other_x, other_lane, other_left, other_right in placed
        ):
            lane += 1
        placed.append((x, lane, left, right))
    mark_lanes = [lane for _, lane, _, _ in placed]
    mark_boxes = [(left, right - left) for _, _, left, right in placed]
    lanes = max(mark_lanes, default=-1) + 1
    advance = theme.box.line_height * label_size
    header = lanes * advance + MARK_GAP * unit if lanes else 0.0

    # Rows, top to bottom: a phase's heading before its first task.
    first_of = {
        min(group.members, key=[task.id for task in document.tasks].index): group
        for group in document.groups
    }
    bar = BAR * unit
    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    rows: dict[str, tuple[float, float]] = {}
    heading_rows: list[tuple[float, float, str]] = []
    y = header
    for task in document.tasks:
        group = first_of.get(task.id)
        if group is not None:
            block = headings[group.id]
            height = max(block.height, bar) + 2 * ROW_PAD * unit
            heading_rows.append((y, y + height, group.id))
            texts.extend(_lines(block, 0.0, y + (height - block.height) / 2))
            y += height
        block = blocks[task.id]
        tallest = bar * (FOCAL if task.milestone and task.role == "emphasis" else 1.0)
        height = max(block.height, tallest) + 2 * ROW_PAD * unit
        rows[task.id] = (y, y + height)
        texts.extend(_lines(block, indent, y + (height - block.height) / 2))
        y += height
    rows_bottom = y

    # Phase brackets, over each phase's span in its heading row.
    tasks = {task.id: task for task in document.tasks}
    for top, bottom, identifier in heading_rows:
        group = next(item for item in document.groups if item.id == identifier)
        start = scale.to_pixels(min(tasks[member].begins for member in group.members))
        end = scale.to_pixels(max(tasks[member].finishes for member in group.members))
        middle = (top + bottom) / 2
        drop = BRACKET * unit
        primitives.append(
            Path(
                BRACKET_ROLE,
                points=(
                    (start, middle + drop),
                    (start, middle),
                    (end, middle),
                    (end, middle + drop),
                ),
            )
        )

    # Bars and milestones.
    bars: dict[str, tuple[float, float, float, float]] = {}
    milestones: dict[str, tuple[float, float]] = {}
    ends: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for task in document.tasks:
        top, bottom = rows[task.id]
        middle = (top + bottom) / 2
        if task.milestone:
            half = bar * MILESTONE / 2 * (FOCAL / MILESTONE if task.role == "emphasis" else 1.0)
            x = scale.to_pixels(task.begins)
            milestones[task.id] = (x, middle)
            primitives.append(_milestone(task, x, middle, half, theme))
            ends[task.id] = ((x - half, middle), (x + half, middle))
            continue
        left, right = scale.to_pixels(task.start), scale.to_pixels(task.end)
        box = (left, middle - bar / 2, right, middle + bar / 2)
        bars[task.id] = box
        primitives.append(_bar(task, box, theme))
        if task.done:
            primitives.append(_done(task.done, box, theme))
        ends[task.id] = ((left, middle), (right, middle))

    # Dependencies, finish to start: the first candidate that crosses no other task.
    order = {task.id: index for index, task in enumerate(document.tasks)}
    shapes = {
        **bars,
        **{
            name: (x - half, y - half, x + half, y + half)
            for name, (x, y) in milestones.items()
            for half in (ends[name][1][0] - x,)
        },
    }
    routes: list[tuple[tuple[float, float], ...]] = []
    for edge in document.edges:
        candidates = _candidates(
            tasks[edge.source],
            tasks[edge.target],
            ends,
            shapes,
            rows,
            order[edge.source] < order[edge.target],
            out=out,
            lead=theme.head_length_for(edge.role) + RUN * unit,
            inset=OUT * unit,
        )
        others = [box for name, box in shapes.items() if name not in (edge.source, edge.target)]
        margin = theme.edge.clearance / 2
        # A route may share its first run with another from the same task, or its
        # last with another into the same task; any other shared run is two
        # dependencies drawn as one line.
        strangers = [
            route
            for route, placed in zip(routes, document.edges, strict=False)
            if placed.source != edge.source and placed.target != edge.target
        ]
        points = min(
            enumerate(candidates),
            key=lambda item: (
                _crossings(item[1], others, margin) + _shared(item[1], strangers),
                item[0],
            ),
        )[1]
        routes.append(points)
        primitives.extend(
            edge_primitives(Route(edge.source, edge.target, edge.role, points), theme)
        )

    # Marks: a line across every row, its name above the first.
    marks: list[float] = []
    for mark, lane, (left, _) in zip(document.marks, mark_lanes, mark_boxes, strict=True):
        x = scale.to_pixels(mark.at)
        marks.append(x)
        label_top = lane * advance
        primitives.append(Path(theme.gantt.marks, points=((x, label_top), (x, rows_bottom))))
        texts.append(
            TextLine(
                FURNITURE_ROLE,
                x=left,
                y=label_top + line.ascent + (advance - line.height) / 2,
                spans=(TextSpan(text=mark.text, font=theme.font.default),),
                level="label",
                anchor="start",
            )
        )

    # The axis: a line under the rows, ticks, their labels, and its caption.
    primitives.append(Path(AXIS_ROLE, points=((plot_left, rows_bottom), (plot_right, rows_bottom))))
    for value, _ in ticks:
        x = scale.to_pixels(value)
        primitives.append(Path(AXIS_ROLE, points=((x, rows_bottom), (x, rows_bottom + tick))))
    labels_top = rows_bottom + tick + gap
    band = line.height
    if names:
        for index, block in enumerate(period_blocks):
            middle = scale.to_pixels(index + 1.5)
            texts.extend(_centred(block, middle, labels_top))
            band = max(band, block.height)
    else:
        for value, text in ticks:
            texts.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=scale.to_pixels(value),
                    y=labels_top + line.ascent,
                    spans=(TextSpan(text=text, font=theme.font.default),),
                    level="label",
                    anchor="middle",
                )
            )
    caption_top = labels_top + band + gap
    texts.append(
        TextLine(
            FURNITURE_ROLE,
            x=(plot_left + plot_right) / 2,
            y=caption_top + line.ascent,
            spans=(TextSpan(text=_with_unit(axis), font=theme.font.default),),
            level="label",
            anchor="middle",
        )
    )
    height = caption_top + line.height + gap

    scene = Scene(
        width=width,
        height=height,
        primitives=(*primitives, *texts),
        title=document.title,
        description=_described(document),
    )
    return GanttDrawing(
        scene=scene,
        scale=scale,
        bars=bars,
        milestones=milestones,
        routes=tuple(routes),
        rows=rows,
        marks=tuple(marks),
    )


def _candidates(
    source: Task,
    target: Task,
    ends: dict[str, tuple[tuple[float, float], tuple[float, float]]],
    shapes: dict[str, tuple[float, float, float, float]],
    rows: dict[str, tuple[float, float]],
    down: bool,
    *,
    out: float,
    lead: float,
    inset: float,
) -> list[tuple[tuple[float, float], ...]]:
    """The routes a dependency may take, simplest first.

    Into the target's start from the left, when there is room for a run before
    the head, turning near the source or near the target; else down (or up) onto
    the target's near edge just inside its start — the top vertex for a
    milestone; else out, along the gap beside a row, and back into the start.
    """
    tail = ends[source.id][1]
    head = ends[target.id][0]
    found: list[tuple[tuple[float, float], ...]] = []
    for turn in (tail[0] + out, head[0] - lead):
        if turn >= tail[0] + out - 1e-6 and head[0] - turn >= lead - 1e-6:
            found.append((tail, (turn, tail[1]), (turn, head[1]), head))
    left, top, right, bottom = shapes[target.id]
    edge = top if down else bottom
    if target.milestone:
        drop = head[0] + (shapes[target.id][2] - shapes[target.id][0]) / 2
        if drop >= tail[0]:
            found.append((tail, (drop, tail[1]), (drop, edge)))
        elif not source.milestone and shapes[source.id][0] < drop:
            low, high = shapes[source.id][1], shapes[source.id][3]
            found.append(((drop, high if down else low), (drop, edge)))
    else:
        drop = max(tail[0] + out, left + inset)
        if drop <= right - inset and abs(edge - tail[1]) >= lead:
            found.append((tail, (drop, tail[1]), (drop, edge)))
    turn, back = tail[0] + out, head[0] - lead
    source_rows, target_rows = rows[source.id], rows[target.id]
    beside_source = source_rows[1] if down else source_rows[0]
    beside_target = target_rows[0] if down else target_rows[1]
    for beside in dict.fromkeys((beside_target, beside_source)):
        found.append((tail, (turn, tail[1]), (turn, beside), (back, beside), (back, head[1]), head))
    return found


def _crossings(
    points: tuple[tuple[float, float], ...],
    boxes: list[tuple[float, float, float, float]],
    margin: float,
) -> int:
    """How many other tasks' marks a route's segments run through."""
    count = 0
    for (x1, y1), (x2, y2) in pairwise(points):
        for left, top, right, bottom in boxes:
            low_x, high_x = sorted((x1, x2))
            low_y, high_y = sorted((y1, y2))
            if (
                high_x >= left - margin
                and low_x <= right + margin
                and high_y >= top - margin
                and low_y <= bottom + margin
            ):
                count += 1
    return count


def _shared(
    points: tuple[tuple[float, float], ...], routes: list[tuple[tuple[float, float], ...]]
) -> int:
    """How many runs of `points` lie along a run of another route."""
    count = 0
    for first, second in pairwise(points):
        for route in routes:
            for other_first, other_second in pairwise(route):
                if _collinear(first, second, other_first, other_second):
                    count += 1
    return count


def _collinear(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    """Whether two axis-aligned runs lie on one line and overlap along it."""
    for axis in (0, 1):
        other = 1 - axis
        if (
            abs(a[axis] - b[axis]) < 1e-6
            and abs(c[axis] - d[axis]) < 1e-6
            and abs(a[axis] - c[axis]) < 2.0
        ):
            low = max(min(a[other], b[other]), min(c[other], d[other]))
            high = min(max(a[other], b[other]), max(c[other], d[other]))
            if high - low > 1.0:
                return True
    return False


def _range(document: Document) -> tuple[float, float]:
    """Where the axis starts and ends: the author's bounds, else the tasks' and marks'."""
    axis = document.axes[0]
    if axis.categories:
        return 1.0, float(len(axis.categories) + 1)
    values = [task.begins for task in document.tasks] + [task.finishes for task in document.tasks]
    values += [mark.at for mark in document.marks]
    low = axis.minimum if axis.minimum is not None else min(values)
    high = axis.maximum if axis.maximum is not None else max(values)
    if high <= low:
        # A plan of milestones all at one point still has to be drawn somewhere.
        low, high = low - 0.5, high + 0.5
    # An end the author did not pin is taken out to the next tick, so the axis
    # starts and stops on a number rather than at week 0.5.
    step = _nice_step((high - low) / TARGET_TICKS)
    if axis.minimum is None:
        low = math.floor(low / step + 1e-9) * step
    if axis.maximum is None:
        high = math.ceil(high / step - 1e-9) * step
    return low, high


def _ticks_for(
    axis: Axis, low: float, high: float
) -> tuple[tuple[tuple[float, str], ...], tuple[str, ...]]:
    """The ticks, and the periods' names when the axis has categories.

    Numbered, the ticks are the chart's, plus the two ends when the author pinned
    them and the step does not land there — a plan that runs to week 10 should
    say 10 at its end. With categories, a tick at every boundary and no number.
    """
    if axis.categories:
        count = len(axis.categories)
        return tuple((float(index + 1), "") for index in range(count + 1)), axis.categories
    ticks = list(_ticks(low, high))
    step = _nice_step((high - low) / TARGET_TICKS)
    for end in (low, high):
        if all(abs(value - end) > step * 1e-6 for value, _ in ticks):
            ticks.append((end, f"{end:g}"))
    ticks.sort()
    return tuple(ticks), ()


def _with_unit(axis: Axis) -> str:
    return f"{axis.label} ({axis.unit})" if axis.unit else axis.label


def _described(document: Document) -> str:
    """The author's description, then each task's `done` share in words.

    The band is drawn, never written, so without this a reader who cannot see it
    cannot tell how far any task has got. `done: 0` is said too: "not started"
    is information the author gave.
    """
    done = [
        f"{task.label.replace('**', '')} {_figure(task.done)}% done"
        for task in document.tasks
        if task.done is not None
    ]
    parts = [document.description] if document.description else []
    if done:
        parts.append("Progress: " + "; ".join(done) + ".")
    return " ".join(parts)


def _label(task: Task) -> str:
    return task.label


def _heading(text: str) -> str:
    """A phase's name, set bold. Its own spans are dropped: the whole name is bold."""
    return f"**{text.replace('**', '')}**"


def _natural(text: str, theme: Theme, measurer: TextMeasurer) -> float:
    """How wide `text` is set on its own lines, unbroken."""
    return wrap(text, 1e6, measurer, theme=theme, level="body").width


def _wrapped(
    text: str, width: float, theme: Theme, measurer: TextMeasurer, *, lead: bool = False
) -> TextBlock:
    try:
        return wrap(text, width, measurer, theme=theme, level="body", lead=True if lead else None)
    except FitError as error:
        raise FitError(
            f"the label {text[:40]!r} has a word wider than the {width:.0f} units the label "
            f"column can give it. Shorten it, or give the diagram more width."
        ) from error


def _lines(block: TextBlock, x: float, top: float) -> list[TextLine]:
    """A label as one left-aligned `TextLine` per line from `top` down."""
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="body",
                    anchor="start",
                )
            )
    return found


def _centred(block: TextBlock, x: float, top: float) -> list[TextLine]:
    """A period's name, centred on `x`, from `top` down."""
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="label",
                    anchor="middle",
                )
            )
    return found


def _bar(task: Task, box: tuple[float, float, float, float], theme: Theme) -> Primitive:
    """A task's bar: a polygon, so its ends are exactly at its values, with no radius.

    Filled from the chart's sequence: the first fill for an ordinary bar and a
    critical one (told apart by weight), the second for the task the diagram is
    about. A `note` task is a light dashed outline with no fill.
    """
    left, top, right, bottom = box
    points = ((left, top), (right, top), (right, bottom), (left, bottom))
    if task.role == "note":
        return Polygon("note", points=points)
    index = 1 if task.role == "emphasis" else 0
    return Polygon(
        "emphasis" if task.role in HEAVY else "step",
        points=points,
        fill=theme.mark.fill_for(index),
        fill_colour=theme.mark.colour_for(index),
    )


#: How much of a bar's height its `done` band takes, centred in it. Less than the
#: whole, so the bar's own fill still shows above and below and the band reads as
#: a line drawn *through* the task — MS Project's progress bar — not a second task.
DONE_SHARE: Final = 0.4


def _done(done: float, box: tuple[float, float, float, float], theme: Theme) -> Primitive:
    """How much of a task is complete: a solid band from the bar's start.

    The page's ink at the theme's `[gantt] done` strength, never a colour, so it
    survives greyscale and a dark page. A region, unstroked: its edge is where
    the work has got to, and an outline would draw a second bar inside the first.
    """
    left, top, right, bottom = box
    middle, half = (top + bottom) / 2, (bottom - top) * DONE_SHARE / 2
    end = left + (right - left) * done / 100
    return Polygon(
        "step",
        points=(
            (left, middle - half),
            (end, middle - half),
            (end, middle + half),
            (left, middle + half),
        ),
        fill="solid",
        fill_colour="currentColor",
        fill_opacity=theme.gantt.done,
        region=True,
    )


def _milestone(task: Task, x: float, y: float, half: float, theme: Theme) -> Primitive:
    """A milestone: a filled diamond (or a dot) centred on its value."""
    role = "note" if task.role == "note" else ("emphasis" if task.role in HEAVY else "step")
    solid = "" if task.role == "note" else "solid"
    ink = "" if task.role == "note" else "currentColor"
    if theme.gantt.milestone == "circle":
        return Ellipse(role, cx=x, cy=y, rx=half * 0.8, ry=half * 0.8, fill=solid, fill_colour=ink)
    return Polygon(
        role,
        points=((x, y - half), (x + half, y), (x, y + half), (x - half, y)),
        fill=solid,
        fill_colour=ink,
    )


__all__ = ["GanttDrawing", "gantt_drawing", "gantt_scene"]
