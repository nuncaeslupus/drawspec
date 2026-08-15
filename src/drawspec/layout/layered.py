"""A direct layered layout: rank, order, place. One of T7's two candidates.

Four passes, in the order every Sugiyama-style layout uses them:

1. **Break cycles** so the rest can assume a DAG (`base.break_cycles`).
2. **Rank** by longest path, so a tree's depth is its rank (`base.rank_nodes`).
3. **Order** within each rank by repeated barycentre sweeps, to reduce crossings.
4. **Place**: sequential along the rank, rank bands separated by the theme's gap.

The reason to write this rather than take a dependency is not that it is better
at crossing reduction — it is not. It is that the corpus's median graph has four
nodes and its largest has seventeen, and at that size the ordering pass barely
matters while `pip install drawspec` pulling a lightly-maintained GPL/EPL
dual-licensed package matters quite a lot. T7 exists to check that claim against
rendered output rather than asserting it.

Overlap-freedom is structural here, not checked afterwards: within a rank boxes
are laid out sequentially with a gap, and ranks occupy disjoint bands. There is no
arrangement this can produce in which two boxes intersect.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Final

from drawspec.layout.base import (
    Layout,
    LayoutEdge,
    LayoutNode,
    Placement,
    Spacing,
    break_cycles,
    rank_nodes,
    validate,
)

#: How close two coordinates have to be before they are the same one.
_TOLERANCE: Final = 1e-9

#: Barycentre sweeps to run. Four (two down, two up) is where the corpus's
#: largest graph stops improving; more passes only cost determinism arguments.
ORDERING_PASSES = 4


@dataclass(frozen=True)
class LayeredEngine:
    """The direct implementation, behind the `LayoutEngine` protocol."""

    spacing: Spacing = field(default_factory=Spacing)
    name: str = "layered"

    def layout(
        self,
        nodes: Sequence[LayoutNode],
        edges: Sequence[LayoutEdge],
        direction: str = "down",
    ) -> Layout:
        """Place every node. See the module docstring for the four passes.

        Raises:
            LayoutError: the graph is malformed, or the direction is unknown.
        """
        validate(nodes, edges, direction)

        # A `right` layout is a `down` layout of the transposed problem: swap
        # every box's width and height going in, and swap the coordinates coming
        # out. One placement routine, two directions, no second implementation to
        # keep in step with the first.
        transposed = direction == "right"
        working = (
            [LayoutNode(node.id, node.height, node.width) for node in nodes]
            if transposed
            else list(nodes)
        )

        ranked_edges, reversed_edges = break_cycles(working, edges)
        ranks = rank_nodes(working, ranked_edges)
        order = self._order(working, ranked_edges, ranks)
        placements, width, height = self._place(working, order, ranked_edges)

        if transposed:
            placements = {
                identifier: Placement(
                    x=place.y,
                    y=place.x,
                    width=place.height,
                    height=place.width,
                    rank=place.rank,
                )
                for identifier, place in placements.items()
            }
            width, height = height, width

        return Layout(
            placements=placements,
            width=width,
            height=height,
            ranks=order,
            reversed_edges=reversed_edges,
        )

    # -- ordering ---------------------------------------------------------

    @staticmethod
    def _order(
        nodes: Sequence[LayoutNode],
        edges: Sequence[LayoutEdge],
        ranks: dict[str, int],
    ) -> tuple[tuple[str, ...], ...]:
        """Node ids per rank, ordered to reduce crossings.

        Barycentre sweeps: a node moves to the average position of its
        neighbours in the adjacent rank, alternating direction. Ties break on
        **declaration order** — the position the node holds in the document — so
        the result is the same on every run, and so a tie means the author's
        order rather than an alphabetical accident.

        That tie is not a corner case: three children of one parent all sit at
        the same barycentre, so it decides the order of every fan in the corpus.
        Ordering them by id put *Alcalde, Comissió de Govern, 10 Districtes* into
        the order their ids happened to sort in, which is no order at all.

        **A node with no neighbour in the reference rank holds its place.** It is
        not sorted to the end, and this is the half the tie-break alone did not
        buy. One sibling with a child of its own is enough to break the fan
        otherwise: on the sweep that looks the other way that sibling has a
        barycentre and its childless peers do not, a sentinel value sorts it to
        the front, and *Alcalde, Comissió de Govern, 10 Districtes* comes out
        *10 Districtes, Alcalde, Comissió de Govern* — in that order whichever
        order the document declares, so the author's order decides nothing at
        all. Holding the unattached ones still leaves the barycentre to order
        exactly the nodes it has evidence about, which is what it is for.
        """
        depth = max(ranks.values(), default=0) + 1
        declared = {node.id: position for position, node in enumerate(nodes)}
        layers: list[list[str]] = [[] for _ in range(depth)]
        for node in nodes:
            layers[ranks[node.id]].append(node.id)

        successors: dict[str, list[str]] = {node.id: [] for node in nodes}
        predecessors: dict[str, list[str]] = {node.id: [] for node in nodes}
        for edge in edges:
            successors[edge.source].append(edge.target)
            predecessors[edge.target].append(edge.source)

        for sweep in range(ORDERING_PASSES):
            downward = sweep % 2 == 0
            indices = range(1, depth) if downward else range(depth - 2, -1, -1)
            for index in indices:
                neighbours = predecessors if downward else successors
                reference = {
                    identifier: position
                    for position, identifier in enumerate(
                        layers[index - 1 if downward else index + 1]
                    )
                }
                layers[index] = _sweep(layers[index], neighbours, reference, declared)

        return tuple(tuple(layer) for layer in layers)

    # -- placement --------------------------------------------------------

    def _place(
        self,
        nodes: Sequence[LayoutNode],
        order: tuple[tuple[str, ...], ...],
        edges: Sequence[LayoutEdge] = (),
    ) -> tuple[dict[str, Placement], float, float]:
        """Sequential within a rank, disjoint bands between ranks."""
        sizes = {node.id: node for node in nodes}

        widths = [
            sum(sizes[identifier].width for identifier in layer)
            + self.spacing.node_gap * max(len(layer) - 1, 0)
            for layer in order
        ]
        total_width = max(widths, default=0.0)

        centres = self._aligned(sizes, order, edges, total_width)

        placements: dict[str, Placement] = {}
        y = 0.0
        for rank, layer in enumerate(order):
            band = max((sizes[identifier].height for identifier in layer), default=0.0)
            for identifier in layer:
                node = sizes[identifier]
                placements[identifier] = Placement(
                    x=centres[identifier] - node.width / 2,
                    # Boxes of differing heights sit centred in their band, so a
                    # rank of peers lines up on its middle.
                    y=y + (band - node.height) / 2,
                    width=node.width,
                    height=node.height,
                    rank=rank,
                )
            y += band + self.spacing.rank_gap

        left = min((place.x for place in placements.values()), default=0.0)
        if abs(left) > _TOLERANCE:
            placements = {
                identifier: replace(place, x=place.x - left)
                for identifier, place in placements.items()
            }
        extent = max((place.right for place in placements.values()), default=0.0)
        height = max(y - self.spacing.rank_gap, 0.0)
        return placements, max(extent, total_width), height

    def _aligned(
        self,
        sizes: dict[str, LayoutNode],
        order: tuple[tuple[str, ...], ...],
        edges: Sequence[LayoutEdge],
        total_width: float,
    ) -> dict[str, float]:
        """Where each box's centre goes: under what it hangs from, if it can.

        Packing a rank sequentially and centring the block is enough to keep the
        boxes apart and no more. It is why a branch with **one** child had that
        child sitting wherever the packing put it — often half a box sideways —
        so the one arrow in the diagram that could have been a straight drop
        dog-legged instead. The reviewer raised it twice: *"I would have
        expected a straight arrow instead of even more angled."*

        So each rank after the first asks to sit under its own parents: a node's
        wanted centre is the mean of the centres it hangs from, and the rank is
        then placed as close to those wants as the order and the gaps allow.

        That last part is the whole difficulty, and it is a known problem with a
        known answer — isotonic regression. The boxes must keep their order and
        their gaps, so their centres must be non-decreasing by at least
        `width/2 + gap + width/2` each; subtract the running minimum and it is
        the plain "fit a non-decreasing sequence closest to what was asked for"
        problem, which pool-adjacent-violators solves exactly in one pass. A
        lone child lands *exactly* under its parent, because nothing else is
        pulling on it; a fan of three lands centred under theirs, spread by the
        gap.
        """
        parents: dict[str, list[str]] = {identifier: [] for identifier in sizes}
        for edge in edges:
            if edge.target in parents and edge.source in sizes:
                parents[edge.target].append(edge.source)

        centres: dict[str, float] = {}
        for rank, layer in enumerate(order):
            span = sum(sizes[identifier].width for identifier in layer) + self.spacing.node_gap * (
                len(layer) - 1
            )
            if rank == 0:
                x = (total_width - span) / 2
                for identifier in layer:
                    centres[identifier] = x + sizes[identifier].width / 2
                    x += sizes[identifier].width + self.spacing.node_gap
                continue

            default = (total_width - span) / 2
            wanted: list[float] = []
            running = default
            for identifier in layer:
                above = [centres[parent] for parent in parents[identifier] if parent in centres]
                half = sizes[identifier].width / 2
                wanted.append(
                    sum(above) / len(above) if above else running + half,
                )
                running += sizes[identifier].width + self.spacing.node_gap

            # The minimum centre-to-centre distance between each pair, so the
            # problem below is about a sequence that only has to be increasing.
            floors = [0.0]
            for first, second in pairwise(layer):
                floors.append(
                    floors[-1]
                    + sizes[first].width / 2
                    + self.spacing.node_gap
                    + sizes[second].width / 2
                )
            for identifier, position in zip(
                layer,
                _isotonic([want - floor for want, floor in zip(wanted, floors, strict=True)]),
                strict=True,
            ):
                centres[identifier] = position + floors[layer.index(identifier)]
        return centres


def _isotonic(wanted: Sequence[float]) -> list[float]:
    """The non-decreasing sequence closest to `wanted`, by least squares.

    Pool adjacent violators: walk left to right keeping blocks of a mean and a
    weight, and whenever a block's mean is below the one before it the two
    cannot both have what they asked for, so they are merged and share the
    average. One pass, exact, and deterministic — which matters as much here as
    exactness, because these coordinates are committed.
    """
    blocks: list[tuple[float, int]] = []
    for value in wanted:
        total, count = value, 1
        while blocks and blocks[-1][0] >= total / count:
            previous, weight = blocks.pop()
            total += previous * weight
            count += weight
        blocks.append((total / count, count))
    return [mean for mean, count in blocks for _ in range(count)]


def _sweep(
    layer: Sequence[str],
    neighbours: dict[str, list[str]],
    reference: dict[str, int],
    declared: dict[str, int],
) -> list[str]:
    """One rank reordered by barycentre, with the unattached nodes held in place.

    Two groups, and only one of them moves. A node with at least one neighbour in
    the reference rank has evidence about where it should be, and those are
    sorted among themselves by `(barycentre, declared)`. A node with none has no
    evidence at all, so it keeps the index it already holds and the sorted ones
    fill the slots left over, in order.

    The alternative — a sentinel barycentre that sorts the unattached to one end —
    is what `_order`'s docstring describes as breaking the fan: it lets a node
    that happens to have a child reorder the siblings that do not, which is a
    decision made on the absence of information.
    """
    ordered = list(layer)
    movable = [identifier for identifier in ordered if _attached(identifier, neighbours, reference)]
    if len(movable) < 2:
        return ordered

    movable.sort(
        key=lambda identifier: (
            _barycentre(neighbours[identifier], reference),
            declared[identifier],
        )
    )
    slots = [index for index, identifier in enumerate(ordered) if identifier in set(movable)]
    for slot, identifier in zip(slots, movable, strict=True):
        ordered[slot] = identifier
    return ordered


def _attached(identifier: str, neighbours: dict[str, list[str]], reference: dict[str, int]) -> bool:
    """Whether `identifier` has any neighbour in the rank being swept against."""
    return any(neighbour in reference for neighbour in neighbours[identifier])


def _barycentre(neighbours: Sequence[str], reference: dict[str, int]) -> float:
    """The average position of `neighbours` in the reference rank.

    Only ever called for a node that has at least one — see `_sweep`, which is
    what decides that a node with none holds its place instead of being given a
    value here.
    """
    positions = [reference[identifier] for identifier in neighbours if identifier in reference]
    return sum(positions) / len(positions)


__all__ = ["ORDERING_PASSES", "LayeredEngine"]
