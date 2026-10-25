"""The `usecase` kind: who uses a system for what, as UML draws it.

A layout family of its own. The input is the model and nothing else — actors,
use cases each in a system, and the relations between them — and every position
here is derived from it.

**Three bands across the page.** Primary actors stand on the left of the system
boundaries, supporting actors on the right (`schema.usecase_sides`), and the
boundaries are stacked down the middle, each a `flow` group's frame with its name
in the corner, so a container reads the same in every kind. An actor is the stick
figure a `sequence` draws, its name under it; a use case is an ellipse sized to
its words.

**Columns inside a boundary.** A use case that is included, that extends another
or that specialises one stands a column to the right of the use case it is about
(`schema.usecase_columns`), so every «include» and «extend» arrow runs across the
boundary rather than up and down through the other ellipses.

**Every line is straight, and none passes through anything.** UML draws an
association as a plain chord between an actor and its use case, so this does too
— the one family whose lines are never routed on a grid. What keeps a chord clear
is where things stand: each candidate placement — the use cases stacked compactly
by column, or each on a row of its own — is laid out with the orders down each
band refined by the barycentre of what they connect to, the best are improved by
moving the actors and the deeper use cases up and down (`_Plan.nudged`, capped at
`EVALUATIONS` placements), and the one kept is the one where no line runs through
an ellipse, a figure, a name or a boundary it does not belong to, with the fewest
crossings, bends, height and line. Only an association no placement clears bends,
once, in a gap or just outside its boundary (`_unblocked`). A specialised actor
stands on its own band straight above or below its parent, so the generalisation
arrow between them is short and vertical.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations, pairwise
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import text_runs
from drawspec.kinds.containers import GROUP_LEVEL, GROUP_ROLE, Frame, frame_primitives
from drawspec.kinds.sequence import (
    FIGURE_BODY,
    FIGURE_GAP,
    FIGURE_HEAD,
    FIGURE_HEIGHT,
    FIGURE_WIDTH,
    stick_figure,
)
from drawspec.routing import Route, edge_primitives
from drawspec.scene import Ellipse, Primitive, Scene, TextRun, centred_lines
from drawspec.schema import USECASE_DRAWN_ROLES, Document, usecase_columns, usecase_sides
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The role a use case's ellipse and its words are drawn in: the default box.
CASE_ROLE: Final = "step"

#: The role an actor's name is set in: words with no box, as a `sequence` sets one.
NAME_ROLE: Final = "note"

#: What an «include» and an «extend» arrow are named, in guillemets as UML writes
#: a stereotype.
KEYWORDS: Final[Mapping[str, str]] = {"include": "«include»", "extend": "«extend»"}

#: The widest a use case's ellipse and an actor's name may be, as shares of the
#: canvas — widest first. A diagram that does not fit is tried again a step
#: narrower before it is refused, so a long name wraps rather than overflowing.
WIDTHS: Final = ((0.3, 0.17), (0.25, 0.15), (0.21, 0.13), (0.18, 0.12))

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
CASE_GAP: Final = 12.0
"""Between two use cases one above the other."""
ACTOR_GAP: Final = 14.0
"""Between two actors' bands on one side."""
INHERIT_GAP: Final = 34.0
"""Between an actor and a specialisation straight above or below it: the arrow's room."""
SIDE_GAP: Final = 48.0
"""Between a side's actors and the boundaries, before any spare width is shared out."""
SIDE_SPARE: Final = 70.0
"""The most spare canvas width each side's gap may take on top of `SIDE_GAP`."""
OUTER_GAP: Final = 16.0
"""Between a side's inner actors and the specialised ones standing further out."""
FRAME_PAD: Final = 14.0
"""Inside a boundary, round its use cases."""
FRAME_GAP: Final = 22.0
"""Between two boundaries one above the other."""
COLUMN_GAP: Final = 28.0
"""Between two columns of use cases, on top of the widest keyword's width."""
LABEL_GAP: Final = 3.0
"""Between a keyword and the arrow it names."""
ARM_REACH: Final = 3.0
"""How far beyond a figure's hand a line starts, so it does not touch the arm."""

#: How many of one actor's specialisations stand in its own column, one above it
#: and one below, with a straight arrow up or down; any more stand further out.
INLINE_CHILDREN: Final = 2

#: How many times the orders are refined by barycentre, per candidate.
SWEEPS: Final = 4

#: How many of the best compact candidates are improved by moving things up and
#: down before the best is kept.
NUDGED: Final = 2

#: The most placements one search may try. A placement is cheap, but a diagram
#: at the budget has many things to move; past this the best so far is kept, so
#: a large diagram costs a bounded time and draws the same every time.
EVALUATIONS: Final = 200

#: The most bends tried for one blocked line, shortest detour first.
DETOURS: Final = 16

#: The scoring of a candidate placement: a line through something is never worth
#: any number of crossings saved, and a crossing is worth a lot of height.
HIT_COST: Final = 10_000.0
CROSS_COST: Final = 100.0
BEND_COST: Final = 250.0
LENGTH_COST: Final = 0.25

Point = tuple[float, float]
Segment = tuple[Point, Point]


@dataclass
class _Case:
    id: str
    text: str
    system: str
    column: int
    box: Box
    cx: float = 0.0
    cy: float = 0.0

    @property
    def rx(self) -> float:
        return self.box.width / 2

    @property
    def ry(self) -> float:
        return self.box.height / 2


@dataclass
class _Actor:
    id: str
    side: str
    parent: str
    name: TextBlock
    unit: float
    x: float = 0.0
    """The figure's centre line."""
    y: float = 0.0
    """The top of the figure's head."""
    outer: bool = False
    """A third or later specialisation of one actor, standing a step further out:
    the first two stand straight above and below their parent."""

    @property
    def width(self) -> float:
        return max(FIGURE_WIDTH * self.unit, self.name.width)

    @property
    def figure(self) -> float:
        return FIGURE_HEIGHT * self.unit

    @property
    def height(self) -> float:
        return self.figure + FIGURE_GAP * self.unit + self.name.height

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.x - self.width / 2, self.y, self.x + self.width / 2, self.y + self.height)

    @property
    def figure_rect(self) -> tuple[float, float, float, float]:
        half = FIGURE_WIDTH * self.unit / 2
        return (self.x - half, self.y, self.x + half, self.y + self.figure)

    @property
    def name_rect(self) -> tuple[float, float, float, float]:
        top = self.y + self.figure + FIGURE_GAP * self.unit
        return (
            self.x - self.name.width / 2,
            top,
            self.x + self.name.width / 2,
            top + self.name.height,
        )

    @property
    def arms(self) -> float:
        return self.y + (FIGURE_HEAD * 2 + FIGURE_BODY * 0.3) * self.unit

    @property
    def centre(self) -> float:
        """Where the figure is read from, for ordering: its arms."""
        return self.arms

    def hand(self) -> Point:
        """Where an association leaves the figure: just past the hand facing the system."""
        reach = (FIGURE_WIDTH / 2 + ARM_REACH) * self.unit
        return (self.x + reach if self.side == "left" else self.x - reach, self.arms)


@dataclass(frozen=True)
class _Line:
    source: str
    target: str
    role: str
    """The relation as written: association, include, extend, inherits."""
    points: tuple[Point, ...]

    @property
    def segments(self) -> tuple[Segment, ...]:
        return tuple(zip(self.points, self.points[1:], strict=False))

    @property
    def segment(self) -> Segment:
        """The longest straight piece: where a keyword is set beside it."""
        return max(self.segments, key=lambda piece: math.dist(*piece))


@dataclass(frozen=True)
class UsecaseDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    cases: Mapping[str, tuple[float, float, float, float]] = field(default_factory=dict)
    """Each use case's ellipse: centre x, centre y, rx, ry."""
    actors: Mapping[str, tuple[float, float, float, float]] = field(default_factory=dict)
    """Each actor's figure and name together: left, top, right, bottom."""
    sides: Mapping[str, str] = field(default_factory=dict)
    frames: tuple[Frame, ...] = ()
    lines: tuple[_Line, ...] = ()
    labels: tuple[tuple[float, float, float, float], ...] = ()
    """Each keyword's box: left, top, right, bottom."""
    hits: int = 0
    """How many times a line runs through something it does not end on."""
    crossings: int = 0


@dataclass
class _Layout:
    cases: dict[str, _Case]
    actors: dict[str, _Actor]
    frames: list[Frame]
    lines: list[_Line]
    width: float
    height: float
    hits: int = 0
    crossings: int = 0
    shift: float = 0.0
    """How far everything was moved down to start at zero: what a pin adds back."""

    @property
    def bends(self) -> int:
        return sum(len(line.points) - 2 for line in self.lines)

    @property
    def score(self) -> float:
        length = sum(math.dist(*piece) for line in self.lines for piece in line.segments)
        return (
            self.hits * HIT_COST
            + self.crossings * CROSS_COST
            + self.bends * BEND_COST
            + self.height
            + length * LENGTH_COST
        )


def usecase_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a UML use case diagram."""
    return usecase_drawing(document, theme, measurer).scene


def usecase_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> UsecaseDrawing:
    """Lay the diagram out on the canvas.

    Raises:
        FitError: the bands are wider than the canvas even at the narrowest wraps.
    """
    canvas = document.width if document.width else theme.canvas.width
    widest = 0.0
    for case_share, name_share in WIDTHS:
        layout = _best(document, theme, measurer, canvas, case_share, name_share)
        if layout.width <= canvas + 0.01:
            return _drawn(document, layout, theme, measurer)
        widest = layout.width
    raise FitError(
        f"this use case diagram is {widest:.0f} units wide at the narrowest wrap, on a "
        f"{canvas:.0f}-unit canvas: shorten the use cases' words, or draw the supporting "
        f"actors' use cases as a diagram of their own"
    )


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def _best(
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
    canvas: float,
    case_share: float,
    name_share: float,
) -> _Layout:
    """The best-scoring placement at these wraps."""
    unit = theme.scale["body"] / 11
    edges = [(edge.source, edge.target, edge.role) for edge in document.usecase_edges]
    columns = usecase_columns([case.id for case in document.usecase_cases], edges)
    sides = usecase_sides(
        [(actor.id, actor.supporting) for actor in document.usecase_actors], edges
    )
    parents = {
        edge.source: edge.target
        for edge in document.usecase_edges
        if edge.role == "inherits" and edge.source in sides
    }
    cases = {
        case.id: _Case(
            case.id,
            case.text,
            case.system,
            columns[case.id],
            size_box(
                case.text,
                theme=theme,
                measurer=measurer,
                role=CASE_ROLE,
                shape="ellipse",
                max_width=canvas * case_share,
            ),
        )
        for case in document.usecase_cases
    }
    actors = {
        actor.id: _Actor(
            actor.id,
            sides[actor.id],
            parents.get(actor.id, ""),
            wrap(actor.text, canvas * name_share, measurer, theme=theme),
            unit,
        )
        for actor in document.usecase_actors
    }
    plan = _Plan(document, theme, measurer, canvas, unit, cases, actors)
    # The width does not depend on the order down the bands, so a wrap that is
    # too wide is known from one placement, before any search is paid for.
    first = plan.place({system: plan.written(system) for system in plan.systems}, False)
    if first.width > canvas + 0.01:
        return first
    tried: list[tuple[_Layout, dict[str, list[str]], bool]] = []
    for staggered in (False, True):
        order = {system: plan.written(system) for system in plan.systems}
        for _ in range(SWEEPS):
            layout = plan.place(order, staggered)
            if all(order != seen or staggered != mode for _, seen, mode in tried):
                tried.append((layout, order, staggered))
            refined = plan.reordered(order, layout)
            if refined == order:
                break
            order = refined
    tried.sort(key=lambda entry: entry[0].score)
    best = tried[0][0]
    if best.hits or best.bends or best.crossings:
        compact = [entry for entry in tried if not entry[2]][:NUDGED]
        for layout, order, staggered in compact:
            nudged = plan.nudged(layout, order, staggered)
            if nudged.score < best.score - 1e-6:
                best = nudged
        if best.hits and compact:
            # Bends allowed, from the best compact start only: the costly search.
            layout, order, staggered = compact[0]
            nudged = plan.nudged(layout, order, staggered, bend=True)
            if nudged.score < best.score - 1e-6:
                best = nudged
    return best


class _Plan:
    """Everything one candidate placement needs, and how to make one."""

    def __init__(
        self,
        document: Document,
        theme: Theme,
        measurer: TextMeasurer,
        canvas: float,
        unit: float,
        cases: dict[str, _Case],
        actors: dict[str, _Actor],
    ) -> None:
        self.document = document
        self.theme = theme
        self.measurer = measurer
        self.canvas = canvas
        self.unit = unit
        self.cases = cases
        self.actors = actors
        self.systems: list[str] = [system.id for system in document.usecase_systems] or [""]
        self.names = {system.id: system.text for system in document.usecase_systems}
        self.evaluations = 0
        """How many placements the current search has made: see `EVALUATIONS`."""
        self.edges = [(edge.source, edge.target, edge.role) for edge in document.usecase_edges]
        self.of_actor: dict[str, list[str]] = {name: [] for name in actors}
        self.of_case: dict[str, list[str]] = {name: [] for name in cases}
        self.related: dict[str, list[str]] = {name: [] for name in cases}
        for source, target, role in self.edges:
            if role == "association":
                actor, case = (source, target) if source in actors else (target, source)
                self.of_actor[actor].append(case)
                self.of_case[case].append(actor)
            elif source in cases and target in cases:
                # Each use case remembers the ones in earlier columns it hangs from.
                deeper, base = (
                    (target, source)
                    if cases[target].column > cases[source].column
                    else (
                        source,
                        target,
                    )
                )
                self.related[deeper].append(base)
        self.children: dict[str, list[str]] = {name: [] for name in actors}
        for name, member in actors.items():
            if member.parent:
                self.children[member.parent].append(name)
                member.outer = len(self.children[member.parent]) > INLINE_CHILDREN
        self.label_size = max(
            (
                measurer.measure(word, theme.font.default, theme.scale["label"]).width
                for role, word in KEYWORDS.items()
                if any(edge_role == role for _, _, edge_role in self.edges)
            ),
            default=0.0,
        )
        self.captions = {
            system.id: size_box(
                system.text,
                theme=theme,
                measurer=measurer,
                role=GROUP_ROLE,
                level=GROUP_LEVEL,
                shape="rect",
                max_width=canvas * 0.6,
            )
            for system in document.usecase_systems
        }

    def written(self, system: str) -> list[str]:
        """The first column's use cases in this system, in the order written."""
        return [
            name for name, case in self.cases.items() if case.system == system and case.column == 0
        ]

    def reordered(self, order: Mapping[str, list[str]], layout: _Layout) -> dict[str, list[str]]:
        """Each first column re-sorted by where its actors and dependents stand."""
        refined: dict[str, list[str]] = {}
        for system, names in order.items():

            def pull(name: str) -> float:
                ys = [layout.actors[actor].centre for actor in self.of_case[name]]
                ys.extend(
                    layout.cases[other].cy for other in self.cases if name in self.related[other]
                )
                return sum(ys) / len(ys) if ys else layout.cases[name].cy

            refined[system] = sorted(names, key=lambda name: (pull(name), names.index(name)))
        return refined

    # -- one placement ------------------------------------------------------

    def nudged(
        self,
        layout: _Layout,
        order: Mapping[str, list[str]],
        staggered: bool,
        *,
        bend: bool = False,
    ) -> _Layout:
        """`layout` improved by moving the actors and the deeper use cases up or down.

        A use case another one hangs from is placed level with it, which is where a
        supporting actor's line to the first column runs, and an actor at the
        middle of its use cases may send a line through a boundary's corner. Each
        actor, then each deeper use case, is tried at heights down the drawing, and
        a move is kept when the whole placement scores better — fewer lines through
        things, fewer bends, fewer crossings — so a line passes between two
        ellipses rather than bending. `bend` lets the placements tried bend a line
        that stays blocked; without it the search is over straight lines only.
        """
        if staggered:
            return layout
        self.evaluations = 0
        deeper = [case for case in self.cases.values() if case.column > 0]
        pins: dict[str, float] = {}
        # Straight lines only while searching, first: a bend is the last resort,
        # and a search that allows them is only run when this one leaves a line
        # through something.
        best = self.place(order, staggered, bend=bend)
        for _ in range(2):
            improved = False
            for actor in self.actors.values():
                low = min(case.cy for case in best.cases.values()) + best.shift
                high = max(case.cy for case in best.cases.values()) + best.shift
                step = actor.height / 3
                for index in range(int((high - low) / step) + 1):
                    if self.evaluations >= EVALUATIONS:
                        break
                    trial = {**pins, actor.id: low + index * step}
                    candidate = self.place(order, staggered, trial, bend=bend)
                    if candidate.score < best.score - 1e-6:
                        best, pins, improved = candidate, trial, True
            for case in deeper:
                span = max(
                    (
                        other.cy + other.ry
                        for other in best.cases.values()
                        if other.system == case.system
                    ),
                    default=0.0,
                ) - min(
                    (
                        other.cy - other.ry
                        for other in best.cases.values()
                        if other.system == case.system
                    ),
                    default=0.0,
                )
                step = case.box.height / 2
                tries = int(span / step) + 3
                for index in range(tries):
                    if self.evaluations >= EVALUATIONS:
                        break
                    trial = {**pins, case.id: index * step}
                    candidate = self.place(order, staggered, trial, bend=bend)
                    if candidate.score < best.score - 1e-6:
                        best, pins, improved = candidate, trial, True
            if not improved:
                break
        final = self.place(order, staggered, pins)
        return final if final.score < layout.score else layout

    def place(
        self,
        order: Mapping[str, list[str]],
        staggered: bool,
        pins: Mapping[str, float] | None = None,
        *,
        bend: bool = True,
    ) -> _Layout:
        self.evaluations += 1
        unit = self.unit
        cases = self.cases
        columns = 1 + max((case.column for case in cases.values()), default=0)
        widths = [
            max((case.box.width for case in cases.values() if case.column == k), default=0.0)
            for k in range(columns)
        ]
        gap = COLUMN_GAP * unit + self.label_size
        framed = bool(self.document.usecase_systems)
        pad = FRAME_PAD * unit if framed else 0.0
        inner = sum(widths) + gap * (columns - 1)
        caption_width = max((box.width for box in self.captions.values()), default=0.0)
        frame_width = max(inner + 2 * pad, caption_width + 2 * pad)

        # Vertical, frame by frame: each a stack of rows from its own top.
        top = 0.0
        frames: list[Frame] = []
        for system in self.systems:
            caption = self.captions.get(system)
            head = caption.height + pad * 0.5 if caption is not None else pad
            rows = self._rows(system, order[system], staggered)
            y = top + head
            for row in rows:
                tallest = 0.0
                for name in row:
                    case = cases[name]
                    case.cy = y + case.ry
                    tallest = max(tallest, case.box.height)
                y += tallest + CASE_GAP * unit
            self._settle(system, top + head, staggered, pins or {})
            bottom = max(
                (case.cy + case.ry for case in cases.values() if case.system == system),
                default=top + head,
            )
            height = bottom + pad - top
            if framed:
                frames.append(
                    Frame(
                        id=system,
                        x=0.0,
                        y=top,
                        width=frame_width,
                        height=height,
                        caption=caption.moved_to(0.0, top) if caption is not None else None,
                        depth=0,
                    )
                )
            top += height + FRAME_GAP * unit

        # Actors: each on its own band, near what it connects to.
        for side in ("left", "right"):
            self._stack_actors(side, pins or {})

        # Horizontal: the bands, then the gaps share what is spare.
        left = [actor for actor in self.actors.values() if actor.side == "left"]
        right = [actor for actor in self.actors.values() if actor.side == "right"]

        def reach(group: list[_Actor]) -> tuple[float, float]:
            inner_w = max((a.width for a in group if not a.outer), default=0.0)
            outer_w = max((a.width for a in group if a.outer), default=0.0)
            return inner_w, outer_w

        l_inner, l_outer = reach(left)
        r_inner, r_outer = reach(right)
        outer_gap = OUTER_GAP * unit
        l_band = l_inner + (outer_gap + l_outer if l_outer else 0.0)
        r_band = r_inner + (outer_gap + r_outer if r_outer else 0.0)
        bands = sum(1 for band in (l_band, r_band) if band)
        side_gap = SIDE_GAP * unit
        natural = l_band + r_band + frame_width + side_gap * bands
        spare = max(self.canvas - natural, 0.0)
        if bands:
            side_gap += min(spare / bands, SIDE_SPARE * unit)
        frame_left = l_band + (side_gap if l_band else 0.0)
        frame_right = frame_left + frame_width
        for actor in left:
            if actor.outer:
                actor.x = l_outer / 2
            else:
                actor.x = (l_outer + outer_gap if l_outer else 0.0) + l_inner / 2
        for actor in right:
            start = frame_right + side_gap
            actor.x = (
                start + r_inner / 2
                if not actor.outer
                else start + r_inner + outer_gap + (r_outer / 2)
            )
        # Columns, centred in the frame.
        x = frame_left + (frame_width - inner) / 2
        centres = []
        for width in widths:
            centres.append(x + width / 2)
            x += width + gap
        for case in cases.values():
            case.cx = centres[case.column]
        frames = [
            Frame(
                id=frame.id,
                x=frame.x + frame_left,
                y=frame.y,
                width=frame.width,
                height=frame.height,
                caption=(
                    frame.caption.moved_to(frame.caption.x + frame_left, frame.caption.y)
                    if frame.caption is not None
                    else None
                ),
                depth=0,
            )
            for frame in frames
        ]
        width = frame_right + (side_gap + r_band if r_band else 0.0)

        # Everything down from zero.
        lowest = min(
            [actor.y for actor in self.actors.values()]
            + [frame.y for frame in frames]
            + [case.cy - case.ry for case in cases.values()]
        )
        for actor in self.actors.values():
            actor.y -= lowest
        for case in cases.values():
            case.cy -= lowest
        frames = [frame.moved(0.0, -lowest) for frame in frames]
        height = max(
            [actor.y + actor.height for actor in self.actors.values()]
            + [frame.bottom for frame in frames]
            + [case.cy + case.ry for case in cases.values()]
        )
        snapshot_cases = {
            name: _Case(c.id, c.text, c.system, c.column, c.box, c.cx, c.cy)
            for name, c in cases.items()
        }
        snapshot_actors = {
            name: _Actor(a.id, a.side, a.parent, a.name, a.unit, a.x, a.y, a.outer)
            for name, a in self.actors.items()
        }
        lines = _lines(self.edges, snapshot_cases, snapshot_actors, self.theme)
        if bend:
            lines = _unblocked(lines, snapshot_cases, snapshot_actors, frames, self.theme)
        layout = _Layout(
            snapshot_cases, snapshot_actors, frames, lines, width, height, shift=lowest
        )
        layout.hits, layout.crossings = _score(layout, self.theme)
        return layout

    def _rows(self, system: str, first: list[str], staggered: bool) -> list[list[str]]:
        """The use cases of `system` as rows, top to bottom.

        Compact: the first column stacked in `first`'s order (the deeper ones are
        settled against it afterwards). Staggered: every use case a row of its own,
        each deeper one straight after the use case it hangs from.
        """
        if not staggered:
            return [[name] for name in first]
        placed: list[str] = []

        def visit(name: str) -> None:
            if name in placed:
                return
            placed.append(name)
            for other, case in self.cases.items():
                if case.system == system and name in self.related[other]:
                    visit(other)

        for name in first:
            visit(name)
        for name, case in self.cases.items():
            if case.system == system and name not in placed:
                placed.append(name)
        return [[name] for name in placed]

    def _settle(self, system: str, top: float, staggered: bool, pins: Mapping[str, float]) -> None:
        """Deeper columns placed near what they hang from, never overlapping.

        In staggered mode every use case already has its own row, so only the
        compact mode moves anything.
        """
        if staggered:
            return
        gap = CASE_GAP * self.unit
        columns = sorted({case.column for case in self.cases.values() if case.system == system})
        # The first column is already a stack; close it up from the top.
        for column in columns:
            members = [
                case
                for case in self.cases.values()
                if case.system == system and case.column == column
            ]
            if column == 0:
                members.sort(key=lambda case: case.cy)
                desired = [case.cy for case in members]
            else:
                for case in members:
                    if case.id in pins:
                        case.cy = top + pins[case.id]
                        continue
                    bases = [self.cases[base].cy for base in self.related[case.id]]
                    case.cy = sum(bases) / len(bases) if bases else case.cy
                members.sort(key=lambda case: case.cy)
                desired = [case.cy for case in members]
            heights = [case.box.height for case in members]
            tops = _packed([d - h / 2 for d, h in zip(desired, heights, strict=True)], heights, gap)
            if column == 0:
                # A plain stack from the frame's top.
                tops = []
                y = top
                for height in heights:
                    tops.append(y)
                    y += height + gap
            shift = max(top - min(tops, default=top), 0.0)
            for case, y, height in zip(members, tops, heights, strict=True):
                case.cy = y + shift + height / 2

    def _stack_actors(self, side: str, pins: Mapping[str, float]) -> None:
        """One side's actors, each on its own band, as near as it can be to its use cases."""
        group = [actor for actor in self.actors.values() if actor.side == side]
        if not group:
            return

        def wanted(actor: _Actor) -> float:
            if actor.id in pins:
                return pins[actor.id]
            ys = [self.cases[case].cy for case in self.of_actor[actor.id]]
            if not ys:
                ys = [
                    self.cases[case].cy
                    for child in self.children[actor.id]
                    for case in self.of_actor[child]
                ]
            if not ys and actor.parent:
                ys = [self.cases[case].cy for case in self.of_actor[actor.parent]]
            return sum(ys) / len(ys) if ys else 0.0

        # Families stay together: a root and its specialisations, the root's own
        # place deciding where the family goes.
        roots = [actor for actor in group if not actor.parent]
        roots.sort(key=lambda actor: (wanted(actor), list(self.actors).index(actor.id)))
        sequence: list[_Actor] = []
        for root in roots:
            # A specialisation stands above its parent when its own use cases are
            # higher, below when lower, and those with none alternate below and
            # above, so no generalisation arrow passes a sibling's figure.
            here = wanted(root)
            above: list[_Actor] = []
            below: list[_Actor] = []
            inline = [self.actors[name] for name in self.children[root.id]]
            outer = [actor for actor in inline if actor.outer]
            inline = [actor for actor in inline if not actor.outer]
            for child in sorted(
                inline, key=lambda actor: (not self.of_actor[actor.id], wanted(actor))
            ):
                mine = wanted(child)
                if (
                    self.of_actor[child.id]
                    and abs(mine - here) > 1e-6
                    and not (above if mine < here else below)
                ):
                    (above if mine < here else below).append(child)
                else:
                    (below if len(below) <= len(above) else above).append(child)
            sequence.extend([*above, root, *below, *sorted(outer, key=wanted)])
        orphans = [actor for actor in group if actor not in sequence]
        sequence.extend(orphans)
        heights = [actor.height for actor in sequence]
        offsets = [actor.centre - actor.y for actor in sequence]
        desired = [wanted(actor) - offset for actor, offset in zip(sequence, offsets, strict=True)]
        # A parent and a specialisation straight above or below it leave room for
        # the arrow between them to have a shaft as well as a head.
        gaps = [
            INHERIT_GAP * self.unit
            if not (upper.outer or lower.outer)
            and (upper.parent == lower.id or lower.parent == upper.id)
            else ACTOR_GAP * self.unit
            for upper, lower in pairwise(sequence)
        ]
        tops = _packed(desired, heights, [*gaps, 0.0])
        for actor, y in zip(sequence, tops, strict=True):
            actor.y = y


def _packed(
    desired: Sequence[float], heights: Sequence[float], gap: float | Sequence[float]
) -> list[float]:
    """Tops in the given order, each at least `gap` below the last, as near `desired`
    as they can be in the least-squares sense (pool adjacent violators). `gap` may
    be one per pair, the gap after each item."""
    gaps = [gap] * len(heights) if isinstance(gap, int | float) else list(gap)
    offsets: list[float] = []
    total = 0.0
    for height, after in zip(heights, gaps, strict=True):
        offsets.append(total)
        total += height + after
    values = [want - offset for want, offset in zip(desired, offsets, strict=True)]
    blocks: list[list[float]] = []  # [mean, count]
    for value in values:
        blocks.append([value, 1.0])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            mean2, count2 = blocks.pop()
            mean1, count1 = blocks.pop()
            blocks.append([(mean1 * count1 + mean2 * count2) / (count1 + count2), count1 + count2])
    fitted: list[float] = []
    for mean, count in blocks:
        fitted.extend([mean] * int(count))
    return [value + offset for value, offset in zip(fitted, offsets, strict=True)]


# ---------------------------------------------------------------------------
# Lines and their scoring
# ---------------------------------------------------------------------------


def _on_ellipse(case: _Case, toward: Point, gap: float = 0.0) -> Point:
    """Where the ray from `case`'s centre toward `toward` leaves its ellipse."""
    dx, dy = toward[0] - case.cx, toward[1] - case.cy
    rx, ry = case.rx + gap, case.ry + gap
    scale = math.hypot(dx / rx, dy / ry) or 1.0
    return (case.cx + dx / scale, case.cy + dy / scale)


def _on_rect(rect: tuple[float, float, float, float], toward: Point, gap: float) -> Point:
    """Where the ray from `rect`'s centre toward `toward` leaves it, `gap` outside."""
    left, top, right, bottom = rect
    cx, cy = (left + right) / 2, (top + bottom) / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    half_w, half_h = (right - left) / 2 + gap, (bottom - top) / 2 + gap
    scale = max(abs(dx) / half_w if half_w else 0.0, abs(dy) / half_h if half_h else 0.0) or 1.0
    return (cx + dx / scale, cy + dy / scale)


def _lines(
    edges: Iterable[tuple[str, str, str]],
    cases: Mapping[str, _Case],
    actors: Mapping[str, _Actor],
    theme: Theme,
) -> list[_Line]:
    """Every relation as a straight line, border to border."""
    gap = theme.edge.clearance / 3
    lines: list[_Line] = []
    for source, target, role in edges:
        if role == "association":
            actor_id, case_id = (source, target) if source in actors else (target, source)
            actor, case = actors[actor_id], cases[case_id]
            start = actor.hand()
            lines.append(_Line(actor_id, case_id, role, (start, _on_ellipse(case, start))))
        elif source in cases:
            first, second = cases[source], cases[target]
            start = _on_ellipse(first, (second.cx, second.cy))
            end = _on_ellipse(second, (first.cx, first.cy), gap)
            lines.append(_Line(source, target, role, (start, end)))
        else:
            child, parent = actors[source], actors[target]
            above = parent.y < child.y
            if child.outer:
                # Further out: from the child's figure to its parent's, side on.
                start = _on_rect(child.figure_rect, (parent.x, parent.arms), gap)
                end = _on_rect(parent.figure_rect, start, gap)
            else:
                start = (child.x, child.y - gap) if above else (child.x, child.rect[3] + gap)
                end = (parent.x, parent.rect[3] + gap) if above else (parent.x, parent.y - gap)
            lines.append(_Line(source, target, role, (start, end)))
    return lines


def _segment_hits_rect(segment: Segment, rect: tuple[float, float, float, float]) -> bool:
    """Whether `segment` passes through the inside of `rect` (Liang-Barsky)."""
    (x1, y1), (x2, y2) = segment
    left, top, right, bottom = rect
    dx, dy = x2 - x1, y2 - y1
    low, high = 0.0, 1.0
    for p, q in ((-dx, x1 - left), (dx, right - x1), (-dy, y1 - top), (dy, bottom - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return high - low > 1e-6


def _segment_hits_ellipse(segment: Segment, case: _Case, grow: float) -> bool:
    """Whether `segment` passes through `case`'s ellipse, grown by `grow`."""
    (x1, y1), (x2, y2) = segment
    rx, ry = case.rx + grow, case.ry + grow
    ax, ay = (x1 - case.cx) / rx, (y1 - case.cy) / ry
    bx, by = (x2 - case.cx) / rx, (y2 - case.cy) / ry
    dx, dy = bx - ax, by - ay
    a = dx * dx + dy * dy
    if a < 1e-12:
        return ax * ax + ay * ay < 1
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / a))
    px, py = ax + dx * t, ay + dy * t
    return px * px + py * py < 1


def _cross(first: Segment, second: Segment) -> bool:
    """Whether two segments cross at a point inside both."""
    (x1, y1), (x2, y2) = first
    (x3, y3), (x4, y4) = second
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-9:
        return False
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    return 0.01 < t < 0.99 and 0.01 < u < 0.99


def _grown(rect: tuple[float, float, float, float], by: float) -> tuple[float, float, float, float]:
    return (rect[0] - by, rect[1] - by, rect[2] + by, rect[3] + by)


def _line_hits(
    line: _Line,
    cases: Mapping[str, _Case],
    actors: Mapping[str, _Actor],
    frames: Sequence[Frame],
    grow: float,
) -> int:
    """How many times `line` runs through something it does not end on."""
    ends = {line.source, line.target}
    own = {cases[end].system for end in ends if end in cases}
    hits = 0
    for segment in line.segments:
        (x1, y1), (x2, y2) = segment
        low_x, high_x = min(x1, x2) - grow, max(x1, x2) + grow
        low_y, high_y = min(y1, y2) - grow, max(y1, y2) + grow
        for name, case in cases.items():
            if (
                case.cx + case.rx < low_x
                or case.cx - case.rx > high_x
                or case.cy + case.ry < low_y
                or case.cy - case.ry > high_y
            ):
                continue
            if name not in ends and _segment_hits_ellipse(segment, case, grow):
                hits += 1
        for name, actor in actors.items():
            half = actor.width / 2
            if actor.x + half < low_x or actor.x - half > high_x:
                continue
            if name in ends:
                # Its own name, under the figure, is still in the way of a line
                # that leaves the hand downward.
                if line.role == "association" and _segment_hits_rect(segment, actor.name_rect):
                    hits += 1
                continue
            if _segment_hits_rect(segment, _grown(actor.rect, grow)):
                hits += 1
        for frame in frames:
            if frame.caption is not None:
                caption = frame.caption
                box = (caption.x, caption.y, caption.x + caption.width, caption.y + caption.height)
                if _segment_hits_rect(segment, box):
                    hits += 1
            if frame.id not in own and _segment_hits_rect(
                segment, (frame.x, frame.y, frame.right, frame.bottom)
            ):
                hits += 1
    # A line from outside crosses its own boundary once, and one inside never.
    for frame in frames:
        if frame.id in own:
            rect = (frame.x, frame.y, frame.right, frame.bottom)
            inside = [_inside(point, rect) for point in line.points]
            hits += max(sum(1 for a, b in pairwise(inside) if a != b) - 1, 0)
            if len(own) == 1 and all(end in cases for end in ends) and not all(inside):
                hits += 1
    return hits


def _inside(point: Point, rect: tuple[float, float, float, float]) -> bool:
    return rect[0] < point[0] < rect[2] and rect[1] < point[1] < rect[3]


def _crossings(lines: Sequence[_Line]) -> int:
    """How many times two lines that share no end cross."""
    crossings = 0
    for first, second in combinations(lines, 2):
        if {first.source, first.target} & {second.source, second.target}:
            continue
        for one in first.segments:
            for other in second.segments:
                if _cross(one, other):
                    crossings += 1
    return crossings


def _score(layout: _Layout, theme: Theme) -> tuple[int, int]:
    """How many times a line runs through something, and how many lines cross."""
    grow = theme.edge.clearance
    hits = sum(
        _line_hits(line, layout.cases, layout.actors, layout.frames, grow) for line in layout.lines
    )
    return hits, _crossings(layout.lines)


def _unblocked(
    lines: list[_Line],
    cases: Mapping[str, _Case],
    actors: Mapping[str, _Actor],
    frames: Sequence[Frame],
    theme: Theme,
) -> list[_Line]:
    """Each association that runs through something, bent once to pass it.

    UML draws an association straight, so this is the exception: a supporting
    actor's line to a use case in the first column has the deeper columns
    between them, and when no order down the bands clears it, it bends once in
    a gap between two ellipses of the column in the way — the nearest gap that
    clears everything, so the line keeps as close to straight as it can.
    """
    grow = theme.edge.clearance
    room = theme.edge.clearance * 1.5
    columns: dict[float, list[_Case]] = {}
    for case in cases.values():
        columns.setdefault(case.cx, []).append(case)
    waypoints: list[Point] = []
    for x, members in columns.items():
        members = sorted(members, key=lambda case: case.cy)
        ys = [members[0].cy - members[0].ry - room, members[-1].cy + members[-1].ry + room]
        for upper, lower in pairwise(members):
            ys.append(((upper.cy + upper.ry) + (lower.cy - lower.ry)) / 2)
        reach = max(case.rx for case in members) + room
        waypoints.extend((x + dx, y) for y in ys for dx in (0.0, -reach, reach))
    # Bends inside a boundary stay well inside it; and just outside one, level
    # with the use case, so the line goes in through the side.
    margin = room
    frame_of = {frame.id: frame for frame in frames}

    def allowed(point: Point, case: _Case) -> bool:
        frame = frame_of.get(case.system)
        if frame is None:
            return True
        inner = (frame.x + margin, frame.y + margin, frame.right - margin, frame.bottom - margin)
        outer = (frame.x - margin, frame.y - margin, frame.right + margin, frame.bottom + margin)
        return _inside(point, inner) or not _inside(point, outer)

    result: list[_Line] = []
    for line in lines:
        if line.role != "association":
            result.append(line)
            continue
        hits = _line_hits(line, cases, actors, frames, grow)
        if not hits:
            result.append(line)
            continue
        actor_id, case_id = (
            (line.source, line.target) if line.source in actors else (line.target, line.source)
        )
        start, case = actors[actor_id].hand(), cases[case_id]
        frame = frame_of.get(case.system)
        extra = [(frame.x - 2 * room, case.cy), (frame.right + 2 * room, case.cy)] if frame else []
        # Shortest detour first, so the first bend that clears everything is the
        # best one and the rest need not be tried.
        centre = (case.cx, case.cy)
        options = sorted(
            (
                point
                for point in [*waypoints, *extra]
                if allowed(point, case)
                # Only a bend between the actor and the use case, never behind either.
                and min(start[0], case.cx) < point[0] < max(start[0], case.cx)
                and abs(point[0] - case.cx) >= 1
            ),
            key=lambda point: math.dist(start, point) + math.dist(point, centre),
        )[:DETOURS]
        best = (hits, line)
        for point in options:
            bent = _Line(
                line.source, line.target, line.role, (start, point, _on_ellipse(case, point))
            )
            score = _line_hits(bent, cases, actors, frames, grow)
            if score < best[0]:
                best = (score, bent)
                if not score:
                    break
        result.append(best[1])
    return result


# ---------------------------------------------------------------------------
# The drawing
# ---------------------------------------------------------------------------


def _label_box(
    line: _Line,
    width: float,
    height: float,
    gap: float,
    taken: Sequence[tuple[float, float, float, float]],
    layout: _Layout,
    grow: float,
) -> tuple[float, float, float, float]:
    """Where a keyword goes beside its arrow: clear of every line, shape and other keyword.

    Tried at the middle of the arrow first, then further along either way and
    further out, above a level arrow before below it; when nothing is clear, the
    spot with the fewest things in the way.
    """
    (x1, y1), (x2, y2) = line.segment
    length = math.hypot(x2 - x1, y2 - y1) or 1.0
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length
    reach = abs(nx) * width / 2 + abs(ny) * height / 2 + 1.5 * gap
    candidates: list[tuple[float, float, float, float]] = []
    for out in (1.0, 1.8):
        for along in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
            mx, my = x1 + (x2 - x1) * along, y1 + (y2 - y1) * along
            # Above a level arrow first, as a stereotype is read.
            for sign in (-1.0, 1.0) if ny > 0 else (1.0, -1.0):
                cx, cy = mx + sign * nx * reach * out, my + sign * ny * reach * out
                candidates.append(
                    (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
                )

    def conflicts(box: tuple[float, float, float, float]) -> int:
        count = sum(
            1
            for other in taken
            if not (
                box[2] <= other[0] or other[2] <= box[0] or box[3] <= other[1] or other[3] <= box[1]
            )
        )
        wide = _grown(box, gap)
        count += sum(
            1
            for other in layout.lines
            for piece in other.segments
            if _segment_hits_rect(piece, wide)
        )
        xs = (box[0], (box[0] + box[2]) / 2, box[2])
        ys = (box[1], (box[1] + box[3]) / 2, box[3])
        for case in layout.cases.values():
            if any(
                ((x - case.cx) / (case.rx + grow)) ** 2 + ((y - case.cy) / (case.ry + grow)) ** 2
                < 1
                for x in xs
                for y in ys
            ):
                count += 1
        for actor in layout.actors.values():
            rect = actor.rect
            if not (
                box[2] <= rect[0] or rect[2] <= box[0] or box[3] <= rect[1] or rect[3] <= box[1]
            ):
                count += 1
        for frame in layout.frames:
            if frame.caption is not None:
                c = frame.caption
                if not (
                    box[2] <= c.x
                    or c.x + c.width <= box[0]
                    or box[3] <= c.y
                    or c.y + c.height <= box[1]
                ):
                    count += 1
        return count

    best = candidates[0]
    least = conflicts(best)
    for box in candidates:
        if least == 0:
            break
        here = conflicts(box)
        if here < least:
            best, least = box, here
    return best


def _drawn(
    document: Document, layout: _Layout, theme: Theme, measurer: TextMeasurer
) -> UsecaseDrawing:
    primitives: list[Primitive] = []
    for frame in layout.frames:
        primitives.extend(frame_primitives(frame, theme, measurer))
    for line in layout.lines:
        route = Route(line.source, line.target, USECASE_DRAWN_ROLES[line.role], line.points)
        primitives.extend(edge_primitives(route, theme))
    for case in layout.cases.values():
        box = case.box.moved_to(case.cx - case.rx, case.cy - case.ry)
        primitives.append(Ellipse(CASE_ROLE, cx=case.cx, cy=case.cy, rx=case.rx, ry=case.ry))
        primitives.extend(text_runs(box, theme, measurer))
    for actor in layout.actors.values():
        primitives.extend(stick_figure(actor.x, actor.y + actor.figure, actor.unit))
        primitives.extend(centred_lines(actor.name, actor.x, actor.name_rect[1], NAME_ROLE, "body"))

    size = theme.scale["label"]
    font = theme.font.default
    gap = LABEL_GAP * theme.scale["body"] / 11
    grow = theme.edge.clearance / 3
    labels: list[tuple[float, float, float, float]] = []
    for line in layout.lines:
        word = KEYWORDS.get(line.role)
        if word is None:
            continue
        extents = measurer.measure(word, font, size)
        spot = _label_box(line, extents.width, extents.height, gap, labels, layout, grow)
        labels.append(spot)
        primitives.append(
            # A keyword is an edge's label: a plain run, as `routing` sets one.
            TextRun(
                USECASE_DRAWN_ROLES[line.role],
                x=(spot[0] + spot[2]) / 2,
                y=spot[1] + extents.ascent,
                text=word,
                level="label",
                font=font,
                anchor="middle",
            )
        )

    width = max([layout.width, *(box[2] for box in labels)])
    height = max([layout.height, *(box[3] for box in labels)])
    scene = Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("crossings", str(layout.crossings)), ("hits", str(layout.hits))),
    )
    return UsecaseDrawing(
        scene=scene,
        cases={name: (c.cx, c.cy, c.rx, c.ry) for name, c in layout.cases.items()},
        actors={name: a.rect for name, a in layout.actors.items()},
        sides={name: a.side for name, a in layout.actors.items()},
        frames=tuple(layout.frames),
        lines=tuple(layout.lines),
        labels=tuple(labels),
        hits=layout.hits,
        crossings=layout.crossings,
    )


__all__ = ["UsecaseDrawing", "usecase_drawing", "usecase_scene"]
