"""The `pert` kind: a project network, activity on node, its schedule computed.

The precedence diagram method as PMBOK and the project-management textbooks
draw it: each activity a box of cells, early start, duration and early finish
along its top, its name in the middle, late start, float and late finish along
its bottom; an arrow for each finish-to-start dependency; and the critical path
— the activities with no float — drawn heavy.

**Every number in a box is computed.** The author writes durations and what each
activity comes `after`; a forward pass sets each early start to the latest early
finish before it (0 for an activity that waits for nothing), and a backward pass
sets each late finish to the earliest late start after it (the project's end for
an activity nothing waits for). Float is late start less early start. The
arithmetic is exact (`fractions.Fraction`), so a float of zero is zero and the
critical path is never decided by rounding; a PERT estimate's expected duration,
(o + 4m + p) / 6, is shown to two places. Times count from 0, the start of the
project: an activity of 3 that starts at 0 finishes at 3, as most textbooks
(and every scheduling tool) count.

**Placement is the layered engine's**, read across the page as a network is,
and down it when across does not fit; routing is the router's, round every box.
Every box is the same size, so the cells line up from one rank to the next and
the eye can run along a row of early starts.

**The critical path is weight, never colour alone**: a critical activity's box
is drawn in the `emphasis` role and a dependency between two critical
activities that leaves no gap in the `strong` edge role, so it survives a
greyscale print. A key under the network names the cells (`[pert] key`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.kinds.graphtext import graph_text
from drawspec.layout import LayeredEngine, Layout, LayoutEdge, LayoutNode, Spacing, best_layout
from drawspec.routing import (
    Connector,
    Obstacle,
    Route,
    edge_primitives,
    minimum_rank_gap,
    route_edges,
)
from drawspec.scene import Path, Primitive, Rect, Scene, TextLine, TextSpan, centred_lines
from drawspec.schema import Document, Edge, PertActivity
from drawspec.schema import Node as FlowNode
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The roles a box is drawn in: an activity off the critical path, one on it, a
#: milestone (a pill), and the key. The rules between cells are always `step`,
#: so they stay quieter than a critical box's outline.
ACTIVITY_ROLE: Final = "step"
CRITICAL_ROLE: Final = "emphasis"
MILESTONE_ROLE: Final = "terminal"
RULE_ROLE: Final = "step"
KEY_ROLE: Final = "note"

#: The edge roles: a dependency, and one along the critical path.
DEPENDENCY_ROLE: Final = "flow"
CRITICAL_EDGE_ROLE: Final = "strong"

#: The ids the two milestones are placed under: never an author's id, since an
#: author's id is visible text and these start with a control character.
START_ID: Final = "\x00start"
FINISH_ID: Final = "\x00finish"

#: What the key writes in each cell, in the order the cells are drawn.
KEY_TOP: Final = ("ES", "Dur", "EF")
KEY_NAME: Final = "Activity"
KEY_BOTTOM: Final = ("LS", "Float", "LF")

#: Lengths in units, a unit being the body size over eleven.
CELL_PAD: Final = 6.0
"""The least air either side of a number in its cell."""

ROW_AIR: Final = 2.5
"""The air above and below a number in its row."""

NAME_AIR: Final = 4.0
"""The air above and below the name."""

NAME_WIDTH: Final = 84.0
"""The widest a name is set before it wraps, unless the cells are wider."""

KEY_GAP: Final = 10.0
"""The gap between the key's box and its notes."""

#: The decimal places a non-whole time is written to: an expected duration of
#: 4 2/3 reads 4.67, as the textbooks print it.
PLACES: Final = 2


@dataclass(frozen=True)
class Times:
    """One activity's schedule: its early and late start and finish, and its float."""

    early_start: Fraction
    early_finish: Fraction
    late_start: Fraction
    late_finish: Fraction

    @property
    def float(self) -> Fraction:
        return self.late_start - self.early_start

    @property
    def critical(self) -> bool:
        return self.float == 0


@dataclass(frozen=True)
class Schedule:
    """The forward and backward pass over a network: every activity's times."""

    times: Mapping[str, Times]
    end: Fraction
    """The project's duration: the latest early finish."""

    order: tuple[str, ...]
    """The activities in an order every dependency runs forward in."""

    def tight(self, before: str, later: str) -> bool:
        """Whether `later` starts the moment `before` finishes, both critical."""
        first, second = self.times[before], self.times[later]
        return first.critical and second.critical and first.early_finish == second.early_start


def schedule(activities: Sequence[PertActivity]) -> Schedule:
    """The critical path method's two passes over `activities`.

    Raises:
        DrawspecError: the dependencies go round in a circle, or name an activity
            that is not there. Validation refuses both first, with the cycle's path;
            this is the guard for a `Document` built by hand.
    """
    by_id = {activity.id: activity for activity in activities}
    later: dict[str, list[str]] = {activity.id: [] for activity in activities}
    waiting = {activity.id: len(activity.after) for activity in activities}
    for activity in activities:
        for before in activity.after:
            if before not in later:
                raise DrawspecError(f"{activity.id!r} comes after {before!r}, which is not there")
            later[before].append(activity.id)
    order: list[str] = []
    ready = [activity.id for activity in activities if not activity.after]
    while ready:
        here = ready.pop(0)
        order.append(here)
        for after in later[here]:
            waiting[after] -= 1
            if waiting[after] == 0:
                ready.append(after)
    if len(order) != len(activities):
        stuck = [activity.id for activity in activities if activity.id not in order]
        raise DrawspecError(f"the dependencies go round in a circle among {stuck!r}")

    early: dict[str, tuple[Fraction, Fraction]] = {}
    for identifier in order:
        activity = by_id[identifier]
        start = max((early[before][1] for before in activity.after), default=Fraction(0))
        early[identifier] = (start, start + activity.duration)
    end = max((finish for _, finish in early.values()), default=Fraction(0))
    late: dict[str, tuple[Fraction, Fraction]] = {}
    for identifier in reversed(order):
        finish = min((late[after][0] for after in later[identifier]), default=end)
        late[identifier] = (finish - by_id[identifier].duration, finish)
    return Schedule(
        times={
            identifier: Times(early[identifier][0], early[identifier][1], *late[identifier])
            for identifier in order
        },
        end=end,
        order=tuple(order),
    )


def figure(value: Fraction) -> str:
    """A time as the box writes it: whole, or to two places with no trailing zeros."""
    if value.denominator == 1:
        return str(value.numerator)
    text = f"{float(value):.{PLACES}f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


@dataclass(frozen=True)
class Cells:
    """The geometry every activity box shares, so the cells line up across ranks."""

    width: float
    cell: float
    """The width of one of the three cells in a row: a third of the box."""

    row: float
    """The height of the top and the bottom row."""

    middle: float
    """The height of the name's row."""

    @property
    def height(self) -> float:
        return 2 * self.row + self.middle


@dataclass(frozen=True)
class Node:
    """One box, placed: an activity, a milestone, or the key."""

    id: str
    x: float
    y: float
    width: float
    height: float
    role: str
    name: TextBlock
    top: tuple[str, str, str] = ("", "", "")
    bottom: tuple[str, str, str] = ("", "", "")
    level: str = "body"
    """The type level the cells are written at: the key's are labels."""

    milestone: str = ""
    """A milestone's time, written under its name; empty on an activity."""

    row: float = 0.0
    """The height of the top and the bottom row of cells."""

    ascent: float = 0.0
    """The default face's ascent and descent at the cells' level: what a number's
    baseline (or a milestone's time) is set from."""

    descent: float = 0.0

    def moved(self, dx: float, dy: float) -> Node:
        return replace(self, x=self.x + dx, y=self.y + dy)


@dataclass(frozen=True)
class PertDrawing:
    """Everything a network is made of, in scene coordinates.

    A value of its own so a test can ask which boxes and lines were drawn as the
    critical path, and what each box says, without reading the primitives.
    """

    schedule: Schedule
    nodes: Mapping[str, Node]
    routes: tuple[Route, ...]
    notes: tuple[TextLine, ...]
    key: Node | None
    width: float
    height: float
    direction: str


def pert_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a `pert` document to a `Scene`.

    Raises:
        FitError: the network does not fit the canvas across or down at this
            type scale, or a name has a word too wide for its box.
    """
    drawing = pert_drawing(document, theme, measurer)
    primitives: list[Primitive] = []
    for route in drawing.routes:
        primitives.extend(edge_primitives(route, theme))
    for node in drawing.nodes.values():
        primitives.extend(node_primitives(node, theme))
    if drawing.key is not None:
        primitives.extend(node_primitives(drawing.key, theme))
    primitives.extend(drawing.notes)
    return Scene(
        width=drawing.width,
        height=drawing.height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("direction", drawing.direction), ("end", figure(drawing.schedule.end))),
    )


def pert_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> PertDrawing:
    """Schedule, size, place and route every activity, then add the key."""
    activities = document.pert_activities
    if not activities:
        raise DrawspecError("a pert network needs at least one activity")
    plan = schedule(activities)
    width = document.width if document.width else theme.canvas.width
    unit = theme.scale["body"] / 11
    cells = _cells(document, plan, theme, measurer)
    pad = theme.box.padding
    body = measurer.measure("", theme.font.default, theme.scale["body"])
    small = measurer.measure("", theme.font.default, theme.scale["label"])

    sized: dict[str, Node] = {}
    for activity in activities:
        times = plan.times[activity.id]
        sized[activity.id] = Node(
            id=activity.id,
            x=0.0,
            y=0.0,
            width=cells.width,
            height=cells.height,
            role=CRITICAL_ROLE if times.critical else ACTIVITY_ROLE,
            name=_name(activity.text, cells.width - 2 * CELL_PAD * unit, theme, measurer),
            top=(figure(times.early_start), figure(activity.duration), figure(times.early_finish)),
            bottom=(figure(times.late_start), figure(times.float), figure(times.late_finish)),
            row=cells.row,
            ascent=body.ascent,
            descent=body.descent,
        )
    edges: list[tuple[str, str, bool]] = [
        (before, activity.id, plan.tight(before, activity.id))
        for activity in activities
        for before in activity.after
    ]
    milestones = (
        (START_ID, document.pert_start, Fraction(0)),
        (FINISH_ID, document.pert_finish, plan.end),
    )
    waited_for = {before for activity in activities for before in activity.after}
    for identifier, words, time in milestones:
        if not words:
            continue
        name = _name(words, cells.width - pad.horizontal, theme, measurer)
        label = measurer.measure(figure(time), theme.font.default, theme.scale["body"])
        sized[identifier] = Node(
            id=identifier,
            x=0.0,
            y=0.0,
            width=max(name.width, label.width) + pad.horizontal + cells.row,
            height=name.height + theme.box.line_height * theme.scale["body"] + pad.vertical,
            role=MILESTONE_ROLE,
            name=name,
            milestone=figure(time),
            ascent=body.ascent,
            descent=body.descent,
        )
        if identifier == START_ID:
            edges = [
                *(
                    (START_ID, activity.id, plan.times[activity.id].critical)
                    for activity in activities
                    if not activity.after
                ),
                *edges,
            ]
        else:
            edges.extend(
                (
                    activity.id,
                    FINISH_ID,
                    plan.times[activity.id].critical
                    and plan.times[activity.id].early_finish == plan.end,
                )
                for activity in activities
                if activity.id not in waited_for
            )

    layout = _placed(document, sized, edges, theme, width)
    nodes = {
        identifier: replace(
            node, x=layout.placements[identifier].x, y=layout.placements[identifier].y
        )
        for identifier, node in sized.items()
    }
    obstacles = tuple(
        Obstacle(
            identifier,
            x=node.x,
            y=node.y,
            width=node.width,
            height=node.height,
            shape="pill" if node.role == MILESTONE_ROLE else "rect",
        )
        for identifier, node in nodes.items()
    )
    connectors = tuple(
        Connector(source, target, role=CRITICAL_EDGE_ROLE if critical else DEPENDENCY_ROLE)
        for source, target, critical in edges
    )
    routes = route_edges(connectors, obstacles, theme, direction=layout.direction)
    key, notes = _key(document, plan, cells, nodes, routes, theme, measurer)
    if key is not None:
        key = replace(key, ascent=small.ascent, descent=small.descent)
    return _framed(plan, nodes, routes, key, notes, layout.direction)


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------


def _cells(document: Document, plan: Schedule, theme: Theme, measurer: TextMeasurer) -> Cells:
    """The one box size every activity takes: three cells wide, three rows tall.

    A cell is as wide as the widest number any box writes, with air either side (the
    key sizes its own cells to its words); the box is three cells, or wider for the widest
    name set at `NAME_WIDTH`. The middle row is tall enough for the most lines any
    name wraps to.
    """
    unit = theme.scale["body"] / 11
    body = theme.scale["body"]
    sans = theme.font.default
    numbers = {
        figure(value)
        for activity in document.pert_activities
        for value in (
            activity.duration,
            plan.times[activity.id].early_start,
            plan.times[activity.id].early_finish,
            plan.times[activity.id].late_start,
            plan.times[activity.id].late_finish,
            plan.times[activity.id].float,
        )
    }
    widest = max(measurer.measure(number, sans, body).width for number in numbers)
    cell = widest + 2 * CELL_PAD * unit
    air = 2 * CELL_PAD * unit
    natural = max(
        _name(activity.text, max(NAME_WIDTH * unit, 3 * cell - air), theme, measurer).width
        for activity in document.pert_activities
    )
    box = max(3 * cell, natural + air)
    blocks = [
        _name(activity.text, box - air, theme, measurer) for activity in document.pert_activities
    ]
    advance = theme.box.line_height * body
    lines = max(len(block.lines) for block in blocks)
    return Cells(
        width=box,
        cell=box / 3,
        row=advance + 2 * ROW_AIR * unit,
        middle=lines * advance + 2 * NAME_AIR * unit,
    )


def _name(text: str, limit: float, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    """A name wrapped to `limit`, as a box sets it.

    Raises:
        FitError: a word in it is wider than `limit`.
    """
    return wrap(text, limit, measurer, theme=theme, boxed=True)


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def _placed(
    document: Document,
    nodes: Mapping[str, Node],
    edges: Sequence[tuple[str, str, bool]],
    theme: Theme,
    width: float,
) -> Layout:
    """The layered engine's placement: across the page first, down it if not.

    Raises:
        FitError: neither direction fits the canvas at this type scale.
    """
    spacing = Spacing(
        node_gap=theme.box.padding.horizontal,
        rank_gap=max(minimum_rank_gap(theme), theme.box.padding.horizontal * 1.25),
    )
    boxes = [LayoutNode(identifier, node.width, node.height) for identifier, node in nodes.items()]
    links = [LayoutEdge(source, target) for source, target, _ in edges]
    ceiling = (document.height or 0.0) if document.height_binding else 0.0
    engine = LayeredEngine(spacing)
    layout = best_layout(engine, boxes, links, max_width=width, prefer="right", max_height=ceiling)
    if not layout.fits:
        raise FitError(
            f"this network needs {layout.width:.0f} at its narrowest and the canvas is "
            f"{width:.0f}; it was tried across the page and down it. Shorten the longest "
            f"names, give the document more `width`, or split it into a network per phase."
        )
    return layout


# ---------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------


def _key(
    document: Document,
    plan: Schedule,
    cells: Cells,
    nodes: Mapping[str, Node],
    routes: Sequence[Route],
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[Node | None, tuple[TextLine, ...]]:
    """The key under the network: a box naming its cells, and what the drawing means.

    Without `[pert] key` only the unit is written, when there is one.
    """
    unit = theme.scale["body"] / 11
    bottom = max(
        [node.y + node.height for node in nodes.values()]
        + [y for route in routes for _, y in route.points]
    )
    left = min(
        [node.x for node in nodes.values()] + [x for route in routes for x, _ in route.points]
    )
    top = bottom + theme.box.padding.horizontal
    label = theme.scale["label"]
    advance = theme.box.line_height * label
    ascent = measurer.measure("", theme.font.default, label).ascent
    total = f"{figure(plan.end)} {document.unit}".rstrip()
    if not theme.pert.key:
        if not document.unit:
            return None, ()
        line = TextLine(
            KEY_ROLE,
            x=left,
            y=top + ascent,
            spans=(TextSpan(text=f"Durations in {document.unit}", font=theme.font.default),),
            level="label",
            anchor="start",
        )
        return None, (line,)
    sans = theme.font.default
    words = (*KEY_TOP, *KEY_BOTTOM)
    cell = max(measurer.measure(word, sans, label).width for word in words) + 2 * CELL_PAD * unit
    wide = max(cells.width, 3 * cell)
    name = wrap(KEY_NAME, wide, measurer, theme=theme, level="label")
    tall = 2 * cells.row + name.height + 2 * NAME_AIR * unit
    key = Node(
        id="\x00key",
        x=left,
        y=top,
        width=wide,
        height=tall,
        role=KEY_ROLE,
        name=name,
        top=KEY_TOP,
        bottom=KEY_BOTTOM,
        level="label",
        row=cells.row,
    )
    said = [
        f"Project: {total}" if document.unit else f"Project: {total} from start to finish",
        "Heavy: the critical path, no float",
        "Times count from 0",
    ]
    if any(activity.estimates for activity in document.pert_activities):
        said.append("Dur: (optimistic + 4 x likely + pessimistic) / 6")
    x = left + wide + KEY_GAP * unit
    first = top + (tall - len(said) * advance) / 2
    notes = tuple(
        TextLine(
            KEY_ROLE,
            x=x,
            y=first + index * advance + ascent,
            spans=(TextSpan(text=words, font=theme.font.default),),
            level="label",
            anchor="start",
        )
        for index, words in enumerate(said)
    )
    return key, notes


def _framed(
    plan: Schedule,
    nodes: Mapping[str, Node],
    routes: Sequence[Route],
    key: Node | None,
    notes: Sequence[TextLine],
    direction: str,
) -> PertDrawing:
    """Everything shifted so the drawing starts at its own ink, and measured."""
    placed = [*nodes.values(), *([key] if key else [])]
    xs = [value for node in placed for value in (node.x, node.x + node.width)]
    ys = [value for node in placed for value in (node.y, node.y + node.height)]
    xs += [x for route in routes for x, _ in route.points]
    ys += [y for route in routes for _, y in route.points]
    dx, dy = -min(xs), -min(ys)
    return PertDrawing(
        schedule=plan,
        nodes={identifier: node.moved(dx, dy) for identifier, node in nodes.items()},
        routes=tuple(
            replace(route, points=tuple((x + dx, y + dy) for x, y in route.points))
            for route in routes
        ),
        notes=tuple(replace(note, x=note.x + dx, y=note.y + dy) for note in notes),
        key=key.moved(dx, dy) if key else None,
        width=max(xs) + dx,
        height=max(ys) + dy,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def node_primitives(node: Node, theme: Theme) -> tuple[Primitive, ...]:
    """A box's outline, the rules between its cells, and every word and number in it."""
    if node.milestone:
        return _milestone(node, theme)
    drawn: list[Primitive] = []
    right, bottom = node.x + node.width, node.y + node.height
    if node.role == KEY_ROLE:
        corners = ((node.x, node.y), (right, node.y), (right, bottom), (node.x, bottom))
        drawn.append(Path(KEY_ROLE, points=corners, closed=True))
        rule = KEY_ROLE
    else:
        drawn.append(Rect(node.role, x=node.x, y=node.y, width=node.width, height=node.height))
        rule = RULE_ROLE
    row = node.row
    first, second = node.y + row, bottom - row
    cell = node.width / 3
    for y in (first, second):
        drawn.append(Path(rule, points=((node.x, y), (right, y))))
    for top in (node.y, second):
        for index in (1, 2):
            x = node.x + index * cell
            drawn.append(Path(rule, points=((x, top), (x, top + row))))
    ascent, descent = node.ascent, node.descent
    text_role = KEY_ROLE if node.role == KEY_ROLE else node.role
    for top, words in ((node.y, node.top), (second, node.bottom)):
        baseline = top + (row + ascent - descent) / 2
        for index, word in enumerate(words):
            drawn.append(
                TextLine(
                    text_role,
                    x=node.x + (index + 0.5) * cell,
                    y=baseline,
                    spans=(TextSpan(text=word, font=theme.font.default),),
                    level=node.level,
                    anchor="middle",
                )
            )
    middle = second - first
    block_top = first + (middle - node.name.height) / 2
    drawn.extend(
        centred_lines(node.name, node.x + node.width / 2, block_top, text_role, node.level)
    )
    return tuple(drawn)


def _milestone(node: Node, theme: Theme) -> tuple[Primitive, ...]:
    """A milestone: a pill with its name, and the time it falls at under it."""
    drawn: list[Primitive] = [
        Rect(node.role, x=node.x, y=node.y, width=node.width, height=node.height)
    ]
    size = theme.scale["body"]
    lines = node.name.height + theme.box.line_height * size
    top = node.y + (node.height - lines) / 2
    middle = node.x + node.width / 2
    drawn.extend(centred_lines(node.name, middle, top, node.role, "body"))
    ascent = node.ascent
    drawn.append(
        TextLine(
            node.role,
            x=middle,
            y=top + node.name.height + ascent,
            spans=(TextSpan(text=node.milestone, font=theme.font.default),),
            level="body",
            anchor="middle",
        )
    )
    return tuple(drawn)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def pert_text(document: Document, width: int, charset: str) -> str:
    """A network as plain text: each activity a box of its name and times, as a `flow`.

    The schedule is the SVG's; the drawing is the graph text router's, given each
    activity as a box whose first line is its name and whose next two are its
    early and late times — `ES=0 D=2 EF=2`, `LS=0 F=0 LF=2` — labelled, since
    a text box has no cells to learn. The critical path is the router's heavy
    line and heavy box, as `emphasis` and `strong` draw in any flow. A refusal
    points at the activity or the `after` entry it is about, never at the flow's
    own `nodes` and `edges`, which the author never wrote.

    Raises:
        FitError: no arrangement fits `width`.
        DrawspecError: past the graph text budget.
    """
    plan = schedule(document.pert_activities)
    nodes: list[tuple[FlowNode, str]] = []
    edges: list[tuple[Edge, str]] = []

    def role(critical: bool) -> str:
        return CRITICAL_EDGE_ROLE if critical else DEPENDENCY_ROLE

    if document.pert_start:
        nodes.append(
            (FlowNode(START_ID, f"{document.pert_start}\n0", role=MILESTONE_ROLE), "/start")
        )
        edges += [
            (Edge(START_ID, activity.id, role=role(plan.times[activity.id].critical)), "/start")
            for activity in document.pert_activities
            if not activity.after
        ]
    for index, activity in enumerate(document.pert_activities):
        times = plan.times[activity.id]
        early = (
            f"ES={figure(times.early_start)} D={figure(activity.duration)} "
            f"EF={figure(times.early_finish)}"
        )
        late = (
            f"LS={figure(times.late_start)} F={figure(times.float)} LF={figure(times.late_finish)}"
        )
        nodes.append(
            (
                FlowNode(
                    activity.id,
                    f"{activity.text}\n{early}\n{late}",
                    role=CRITICAL_ROLE if times.critical else ACTIVITY_ROLE,
                ),
                f"/activities/{index}",
            )
        )
        edges += [
            (
                Edge(before, activity.id, role=role(plan.tight(before, activity.id))),
                f"/activities/{index}/after/{position}",
            )
            for position, before in enumerate(activity.after)
        ]
    if document.pert_finish:
        waited_for = {before for activity in document.pert_activities for before in activity.after}
        nodes.append(
            (
                FlowNode(
                    FINISH_ID, f"{document.pert_finish}\n{figure(plan.end)}", role=MILESTONE_ROLE
                ),
                "/finish",
            )
        )
        edges += [
            (
                Edge(
                    activity.id,
                    FINISH_ID,
                    role=role(
                        plan.times[activity.id].critical
                        and plan.times[activity.id].early_finish == plan.end
                    ),
                ),
                "/finish",
            )
            for activity in document.pert_activities
            if activity.id not in waited_for
        ]
    total = f"{figure(plan.end)} {document.unit}".rstrip()
    caption = "\n".join(
        part
        for part in (
            "ES/EF early start/finish, D duration, LS/LF late start/finish, F float. "
            f"Heavy: the critical path, {total} in all.",
            document.caption,
        )
        if part
    )
    flow = Document(
        kind="flow",
        title=document.title,
        caption=caption,
        nodes=tuple(node for node, _ in nodes),
        edges=tuple(edge for edge, _ in edges),
    )
    try:
        return graph_text(flow, width, charset)
    except DrawspecError as error:
        raise _repointed(
            error, [where for _, where in nodes], [where for _, where in edges]
        ) from error


def _repointed(error: DrawspecError, nodes: Sequence[str], edges: Sequence[str]) -> DrawspecError:
    """`error` with the flow's pointer — `/nodes/3/text` — turned into the author's."""
    message = str(error)
    match = re.match(r"^/(nodes|edges)/(\d+)(/text)?", message)
    if match is None:
        return error
    places = nodes if match.group(1) == "nodes" else edges
    index = int(match.group(2))
    if index >= len(places):
        return error
    where = places[index]
    if match.group(3) and where.startswith("/activities/") and where.count("/") == 2:
        where += "/text"
    return type(error)(where + message[match.end() :])


__all__ = [
    "PertDrawing",
    "Schedule",
    "Times",
    "figure",
    "pert_drawing",
    "pert_scene",
    "pert_text",
    "schedule",
]
