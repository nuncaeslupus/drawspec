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
from typing import Final, Protocol, runtime_checkable

from drawspec.errors import LayoutError

#: The two flow directions. `down` stacks ranks vertically, `right` runs them
#: across. When arrows will not fit one way, the answer is the other one —
#: never a smaller gap, which is what costs an arrow its shaft.
DIRECTIONS: Final = ("down", "right")


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


def best_layout(
    engine: LayoutEngine,
    nodes: Sequence[LayoutNode],
    edges: Sequence[LayoutEdge],
    *,
    max_width: float,
    prefer: str = "down",
) -> Layout:
    """Lay out in whichever direction fits `max_width`, preferring `prefer`.

    T7's spike found that an engine takes a direction and does not choose one,
    while "if the arrows do not fit horizontally, the diagram goes vertical" is a
    real remedy someone has to apply. This is that someone.

    When neither direction fits, the narrower attempt is returned with
    `fits=False` rather than an exception: the elastic fit (T6) retries the whole
    diagram at a smaller type scale, and only when that is exhausted is it time to
    tell the author to restructure. Deciding that is the caller's.

    Raises:
        LayoutError: `prefer` is not a known direction, or the graph is malformed.
    """
    if prefer not in DIRECTIONS:
        raise LayoutError(f"unknown direction {prefer!r}; expected {', '.join(DIRECTIONS)}")

    order = (prefer, *(d for d in DIRECTIONS if d != prefer))
    attempts = [
        replace(engine.layout(nodes, edges, direction), direction=direction) for direction in order
    ]
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
    "rank_nodes",
    "validate",
]
