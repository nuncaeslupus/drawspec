"""The `LayoutEngine` seam: sizes in, coordinates out.

This is the escape hatch the specification's recommendation rests on. The whole
coupling to a layout implementation is one method, so choosing wrong is
recoverable: a Graphviz (`-Tplain`) or ELK engine is an additive change behind
this protocol rather than a rewrite. That is why the engine decision could be
deferred to a spike (T7) without blocking the eight tasks that do not depend on
it.

The types here are deliberately ignorant of everything else in drawspec. An
engine is given boxes with measured sizes and a list of edges, and returns
coordinates. It does not know about themes, roles, text or SVG — so an engine can
be written, or vendored, without understanding the rest of the tool.

One thing the return value must carry beyond coordinates: **which edges were
reversed to break a cycle**. Ranking a cyclic graph means temporarily flipping
some edges, and routing has to draw them in the direction the author wrote them,
not the direction the ranker needed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from math import cos, pi, sin
from typing import Final, Protocol, runtime_checkable

from drawspec.errors import LayoutError

#: The two flow directions. `down` stacks ranks vertically, `right` runs them
#: across. When arrows will not fit one way, the answer is the other one —
#: never a smaller gap, which is what costs an arrow its shaft.
DIRECTIONS: Final = ("down", "right")

#: Where the first peer of a hub goes: the top, reading clockwise, the same
#: convention `cycle` uses and the same one a clock face does.
_TOP: Final = -pi / 2


@dataclass(frozen=True)
class LayoutNode:
    """A box to place, already sized by `drawspec.geometry`."""

    id: str
    width: float
    height: float


@dataclass(frozen=True)
class LayoutEdge:
    """A directed edge between two node ids."""

    source: str
    target: str


@dataclass(frozen=True)
class Spacing:
    """The gaps an engine must leave. Derived from the theme by the caller.

    `rank_gap` is not decoration: it is what guarantees an arrow between two
    ranks has a visible shaft, so it is floored at the theme's
    `min_shaft_length` plus its head length by whoever builds this.
    """

    node_gap: float = 24.0
    rank_gap: float = 40.0


@dataclass(frozen=True)
class Placement:
    """Where one box ended up: its top-left corner, its size, and its rank."""

    x: float
    y: float
    width: float
    height: float
    rank: int

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def centre(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    def overlaps(self, other: Placement, *, tolerance: float = 1e-9) -> bool:
        """Whether two boxes intersect. Touching edges do not count."""
        return (
            self.x < other.right - tolerance
            and other.x < self.right - tolerance
            and self.y < other.bottom - tolerance
            and other.y < self.bottom - tolerance
        )


@dataclass(frozen=True)
class Layout:
    """The result: every box placed, plus what the ranker had to do to get there."""

    placements: Mapping[str, Placement]
    width: float
    height: float
    ranks: tuple[tuple[str, ...], ...] = ()
    """Node ids per rank, in the order the engine put them — what a crossing
    count is measured against."""

    reversed_edges: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    """Edges the engine flipped to break a cycle. Routing must draw these in the
    author's direction, not the ranker's."""

    direction: str = "down"
    """Which way the ranks run. Set by whoever chose it — see `best_layout`."""

    fits: bool = True
    """Whether this layout came out within the width it was asked for.

    False is not an error: elastic fit gets a turn before anyone gives up, so the
    decision to raise belongs to the caller rather than to the engine.
    """

    def overlaps(self) -> tuple[tuple[str, str], ...]:
        """Every pair of boxes that intersect. Empty is the requirement."""
        identifiers = sorted(self.placements)
        return tuple(
            (first, second)
            for index, first in enumerate(identifiers)
            for second in identifiers[index + 1 :]
            if self.placements[first].overlaps(self.placements[second])
        )

    def crossings(self, edges: Sequence[LayoutEdge]) -> int:
        """How many pairs of edges cross, counted between adjacent ranks.

        The standard layered-graph measure: two edges leaving the same rank cross
        when their endpoints are in the opposite order from their starts. It is
        the one number that says whether an engine's ordering pass earned its
        keep.
        """
        position = {
            identifier: index for rank in self.ranks for index, identifier in enumerate(rank)
        }
        rank_of = {identifier: place.rank for identifier, place in self.placements.items()}

        count = 0
        by_rank: dict[int, list[LayoutEdge]] = {}
        for edge in edges:
            if edge.source in rank_of and edge.target in rank_of:
                by_rank.setdefault(rank_of[edge.source], []).append(edge)
        for group in by_rank.values():
            for index, first in enumerate(group):
                for second in group[index + 1 :]:
                    if first.source not in position or second.source not in position:
                        continue
                    left = position[first.source] - position[second.source]
                    right = position.get(first.target, 0) - position.get(second.target, 0)
                    if left * right < 0:
                        count += 1
        return count


@runtime_checkable
class LayoutEngine(Protocol):
    """Sizes in, coordinates out. The only coupling to a layout implementation."""

    @property
    def name(self) -> str:
        """How this engine identifies itself in a report or a decision record."""
        ...

    @property
    def spacing(self) -> Spacing:
        """The gaps it was built with — what a caller needs to lay out beside it."""
        ...

    def layout(
        self,
        nodes: Sequence[LayoutNode],
        edges: Sequence[LayoutEdge],
        direction: str = "down",
    ) -> Layout:
        """Place every node, or raise `LayoutError`."""
        ...


# ---------------------------------------------------------------------------
# Shared graph work
# ---------------------------------------------------------------------------


def validate(nodes: Sequence[LayoutNode], edges: Sequence[LayoutEdge], direction: str) -> None:
    """Reject a graph no engine could lay out, before any engine tries.

    Raises:
        LayoutError: duplicate ids, an edge with no such node, or an unknown
            direction.
    """
    if direction not in DIRECTIONS:
        raise LayoutError(f"unknown direction {direction!r}; expected {', '.join(DIRECTIONS)}")
    if not nodes:
        raise LayoutError("nothing to lay out: the graph has no nodes")

    seen: set[str] = set()
    for node in nodes:
        if node.id in seen:
            raise LayoutError(f"duplicate node id {node.id!r}")
        if node.width <= 0 or node.height <= 0:
            raise LayoutError(f"node {node.id!r} has a non-positive size")
        seen.add(node.id)
    for edge in edges:
        for end, identifier in (("source", edge.source), ("target", edge.target)):
            if identifier not in seen:
                raise LayoutError(f"edge {end} {identifier!r} is not a node in this graph")


def break_cycles(
    nodes: Sequence[LayoutNode], edges: Sequence[LayoutEdge]
) -> tuple[tuple[LayoutEdge, ...], frozenset[tuple[str, str]]]:
    """Return the edges with every cycle broken, and which ones were reversed.

    A depth-first sweep in sorted id order: an edge back to a node still on the
    stack is a back edge, and is reversed rather than dropped, so the ranker sees
    a DAG while the drawing keeps every edge the author wrote. Sorted order is
    what makes the choice of back edge the same on every run — a cycle has no
    canonical entry point, so determinism has to be imposed.

    A self-loop is dropped from ranking entirely: it constrains nothing.
    """
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.source != edge.target:
            outgoing[edge.source].append(edge.target)
    for targets in outgoing.values():
        targets.sort()

    colour: dict[str, int] = dict.fromkeys(outgoing, 0)  # 0 white, 1 grey, 2 black
    back: set[tuple[str, str]] = set()

    for root in sorted(outgoing):
        if colour[root] != 0:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        colour[root] = 1
        while stack:
            node, index = stack[-1]
            if index < len(outgoing[node]):
                stack[-1] = (node, index + 1)
                target = outgoing[node][index]
                if colour[target] == 1:
                    back.add((node, target))
                elif colour[target] == 0:
                    colour[target] = 1
                    stack.append((target, 0))
            else:
                colour[node] = 2
                stack.pop()

    ranked: list[LayoutEdge] = []
    for edge in edges:
        if edge.source == edge.target:
            continue
        if (edge.source, edge.target) in back:
            ranked.append(LayoutEdge(source=edge.target, target=edge.source))
        else:
            ranked.append(edge)
    return tuple(ranked), frozenset(back)


def rank_nodes(nodes: Sequence[LayoutNode], edges: Sequence[LayoutEdge]) -> dict[str, int]:
    """Longest-path ranking of an acyclic edge set: rank = longest path in.

    Longest-path rather than tightest-tree: it puts every node as late as its
    dependencies allow, which is what makes a tree's depth show up as its rank
    and reads as hierarchy.

    Raises:
        LayoutError: the edge set still contains a cycle.
    """
    incoming: dict[str, list[str]] = {node.id: [] for node in nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        incoming[edge.target].append(edge.source)
        outgoing[edge.source].append(edge.target)

    remaining = {identifier: len(sources) for identifier, sources in incoming.items()}
    ready = sorted(identifier for identifier, count in remaining.items() if count == 0)
    rank = dict.fromkeys(remaining, 0)
    ordered: list[str] = []

    while ready:
        node = ready.pop(0)
        ordered.append(node)
        for target in sorted(outgoing[node]):
            rank[target] = max(rank[target], rank[node] + 1)
            remaining[target] -= 1
            if remaining[target] == 0:
                ready.append(target)
        ready.sort()

    if len(ordered) != len(remaining):
        stuck = sorted(set(remaining) - set(ordered))
        raise LayoutError(f"the graph still contains a cycle through {', '.join(stuck)}")
    return rank


def long_edges(layout: Layout, edges: Sequence[LayoutEdge]) -> tuple[LayoutEdge, ...]:
    """The edges that span more than one rank, in the order they were given.

    These are what routing has to deal with specially: an edge from rank 0 to
    rank 3 passes through the two ranks between them, so a straight run would
    cross whatever is there. This engine deliberately does *not* reserve a column
    for them — that slack is what made the alternative engine too wide to fit the
    canvas (see the T7 decision) — so T9 routes them around the drawing instead,
    and this is the list it routes.

    A reversed back edge counts: it spans every rank it jumped over.
    """
    rank_of = {identifier: place.rank for identifier, place in layout.placements.items()}
    return tuple(
        edge
        for edge in edges
        if edge.source in rank_of
        and edge.target in rank_of
        and abs(rank_of[edge.target] - rank_of[edge.source]) > 1
    )


def pack(
    nodes: Sequence[LayoutNode],
    spacing: Spacing,
    *,
    max_width: float,
) -> Layout:
    """Fill rows to `max_width`, in the order the nodes were declared.

    For a set of boxes with **nothing ordering them**. Ranking is what turns a
    relation into a position, and with no edges there is no relation: the
    Kubernetes control plane is thirteen components and not one arrow, and the
    only thing the drawing says is *these live in here*.

    Ranked instead, that comes out as a line — thirteen ranks of one going down,
    or one rank of thirteen going across, neither of which fits a fixed-width
    sheet at a legible size. The original was compact and two-dimensional
    because a set with no order is a *shape*, not a sequence.

    Rows are separated by `node_gap`, not `rank_gap`: the rank gap exists to
    give an arrow a visible shaft, and there are no arrows here.
    """
    rows: list[list[LayoutNode]] = []
    used = 0.0
    for node in nodes:
        extra = node.width if not rows else spacing.node_gap + node.width
        if rows and used + extra <= max_width:
            rows[-1].append(node)
            used += extra
        else:
            rows.append([node])
            used = node.width

    widths = [sum(node.width for node in row) + spacing.node_gap * (len(row) - 1) for row in rows]
    total_width = max(widths, default=0.0)

    placements: dict[str, Placement] = {}
    y = 0.0
    for index, row in enumerate(rows):
        band = max(node.height for node in row)
        x = (total_width - widths[index]) / 2
        for node in row:
            placements[node.id] = Placement(
                x=x,
                y=y + (band - node.height) / 2,
                width=node.width,
                height=node.height,
                rank=index,
            )
            x += node.width + spacing.node_gap
        y += band + spacing.node_gap

    return Layout(
        placements=placements,
        width=total_width,
        height=max(y - spacing.node_gap, 0.0),
        ranks=tuple(tuple(node.id for node in row) for row in rows),
        fits=total_width <= max_width,
    )


def radial(
    nodes: Sequence[LayoutNode],
    spacing: Spacing,
    *,
    centre: str,
) -> Layout:
    """One box in the middle, the rest around it, in declaration order clockwise.

    For the diagram whose subject **is** the middle. A post holds a unit above
    it, a function to its left, a cost centre to its right and a person below,
    with a named arrow to each: there is no sequence and no hierarchy, the four
    relations are peers, and the reading starts in the middle rather than at the
    top.

    Ranked instead, the middle object becomes just another row — and worse, it
    would not draw at all: four labelled edges out of one box in a layered
    layout ran out of room for the fourth label, and the drawing only rendered
    once two of the arrows were turned round, which left two arrowheads pointing
    the wrong way. Around the middle each label has its own quadrant.

    Peers sit on an ellipse whose radii clear the centre box, the peer's own
    half-extent and the rank gap, so nothing overlaps whatever the shapes are.
    The first peer is placed at the top and the rest run clockwise, which is how
    a clock face and every hub diagram in the corpus are read.
    """
    middle = next((node for node in nodes if node.id == centre), None)
    if middle is None:
        raise LayoutError(f"no node {centre!r} to put in the middle")
    peers = [node for node in nodes if node.id != centre]
    if not peers:
        return Layout(
            placements={middle.id: Placement(0.0, 0.0, middle.width, middle.height, 0)},
            width=middle.width,
            height=middle.height,
        )

    widest = max(node.width for node in peers)
    tallest = max(node.height for node in peers)
    across = middle.width / 2 + spacing.rank_gap + widest / 2
    down = middle.height / 2 + spacing.rank_gap + tallest / 2

    angles = [_TOP + 2 * pi * index / len(peers) for index in range(len(peers))]
    spots = {
        node.id: (across * cos(angle), down * sin(angle))
        for node, angle in zip(peers, angles, strict=True)
    }
    spots[middle.id] = (0.0, 0.0)

    sizes = {node.id: node for node in nodes}
    left = min(x - sizes[key].width / 2 for key, (x, _) in spots.items())
    top = min(y - sizes[key].height / 2 for key, (_, y) in spots.items())
    placements = {
        key: Placement(
            x=x - sizes[key].width / 2 - left,
            y=y - sizes[key].height / 2 - top,
            width=sizes[key].width,
            height=sizes[key].height,
            rank=0 if key == middle.id else 1,
        )
        for key, (x, y) in spots.items()
    }
    return Layout(
        placements=placements,
        width=max(place.right for place in placements.values()),
        height=max(place.bottom for place in placements.values()),
        ranks=((middle.id,), tuple(node.id for node in peers)),
    )


def best_layout(
    engine: LayoutEngine,
    nodes: Sequence[LayoutNode],
    edges: Sequence[LayoutEdge],
    *,
    max_width: float,
    prefer: str = "down",
    centre: str = "",
    max_height: float = 0.0,
) -> Layout:
    """Lay out in whichever direction fits, preferring `prefer`.

    T7's spike found that an engine takes a direction and does not choose one,
    while "if the arrows do not fit horizontally, the diagram goes vertical" is a
    real remedy someone has to apply. This is that someone.

    **`max_height` is what makes the choice a choice.** Width alone could only
    ever say *down*: a chain of six laid out downward is one box wide, so it fits
    every canvas there is, and `right` was unreachable for any document — chains
    of two through six at five widths, twenty-five combinations, all vertical.
    That is not a preference, it is an outcome, and a source sheet reading across
    the page in a 760-by-150 band could not be drawn. A height ceiling (an author
    writing `height` with `height_binding`) gives the comparison a second
    dimension, and then the same rule — first direction that fits — answers
    *right* where it should.

    Zero means no ceiling, which is the old behaviour exactly: an author who says
    nothing about height still gets `prefer`.

    When no direction fits, the narrower attempt is returned with `fits=False`
    rather than an exception: the elastic fit (T6) retries the whole diagram at a
    smaller type scale, and only when that is exhausted is it time to tell the
    author to restructure. Deciding that is the caller's.

    Raises:
        LayoutError: `prefer` is not a known direction, or the graph is malformed.
    """
    if prefer not in DIRECTIONS:
        raise LayoutError(f"unknown direction {prefer!r}; expected {', '.join(DIRECTIONS)}")

    if centre and any(node.id == centre for node in nodes):
        return replace(radial(nodes, engine.spacing, centre=centre), direction=prefer)

    if nodes and not edges:
        return replace(pack(nodes, engine.spacing, max_width=max_width), direction=prefer)

    order = (prefer, *(d for d in DIRECTIONS if d != prefer))
    attempts = [
        replace(engine.layout(nodes, edges, direction), direction=direction) for direction in order
    ]
    for attempt in attempts:
        if attempt.width <= max_width and (not max_height or attempt.height <= max_height):
            return replace(attempt, fits=True)
    # No direction satisfies both. Width is the binding one — a drawing wider
    # than its canvas is clipped, while one taller than a requested height is
    # merely taller than asked — so a direction that fits the width still wins
    # here, and `render`'s height check is what refuses it afterwards.
    for attempt in attempts:
        if attempt.width <= max_width:
            return replace(attempt, fits=True)
    # Narrower first, then the preferred order, so the choice is never arbitrary.
    narrowest = min(attempts, key=lambda attempt: (attempt.width, order.index(attempt.direction)))
    return replace(narrowest, fits=False)


__all__ = [
    "DIRECTIONS",
    "Layout",
    "LayoutEdge",
    "LayoutEngine",
    "LayoutNode",
    "Placement",
    "Spacing",
    "best_layout",
    "break_cycles",
    "long_edges",
    "pack",
    "radial",
    "rank_nodes",
    "validate",
]
