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
from dataclasses import dataclass, field

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
        placements, width, height = self._place(working, order)

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
        neighbours in the adjacent rank, alternating direction. Ties break on id,
        so the result is the same on every run — which matters more here than the
        last crossing, because the coordinates end up in committed SVG.
        """
        depth = max(ranks.values(), default=0) + 1
        layers: list[list[str]] = [[] for _ in range(depth)]
        for node in sorted(nodes, key=lambda item: item.id):
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
                layers[index] = sorted(
                    layers[index],
                    key=lambda identifier: (
                        _barycentre(neighbours[identifier], reference),
                        identifier,
                    ),
                )

        return tuple(tuple(layer) for layer in layers)

    # -- placement --------------------------------------------------------

    def _place(
        self, nodes: Sequence[LayoutNode], order: tuple[tuple[str, ...], ...]
    ) -> tuple[dict[str, Placement], float, float]:
        """Sequential within a rank, disjoint bands between ranks."""
        sizes = {node.id: node for node in nodes}

        widths = [
            sum(sizes[identifier].width for identifier in layer)
            + self.spacing.node_gap * max(len(layer) - 1, 0)
            for layer in order
        ]
        total_width = max(widths, default=0.0)

        placements: dict[str, Placement] = {}
        y = 0.0
        for rank, layer in enumerate(order):
            band = max((sizes[identifier].height for identifier in layer), default=0.0)
            # Each rank is centred on the widest one, so a diagram reads down its
            # own middle rather than being flushed left.
            x = (total_width - widths[rank]) / 2
            for identifier in layer:
                node = sizes[identifier]
                placements[identifier] = Placement(
                    x=x,
                    # Boxes of differing heights sit centred in their band, so a
                    # rank of peers lines up on its middle.
                    y=y + (band - node.height) / 2,
                    width=node.width,
                    height=node.height,
                    rank=rank,
                )
                x += node.width + self.spacing.node_gap
            y += band + self.spacing.rank_gap

        height = max(y - self.spacing.rank_gap, 0.0)
        return placements, total_width, height


def _barycentre(neighbours: Sequence[str], reference: dict[str, int]) -> float:
    """The average position of `neighbours`, or a large value when it has none.

    A node with no neighbour in the adjacent rank has nothing to be pulled
    towards, so it sorts after the ones that do — and then on its id, which is
    what keeps the result reproducible.
    """
    positions = [reference[identifier] for identifier in neighbours if identifier in reference]
    if not positions:
        return float(len(reference) + 1)
    return sum(positions) / len(positions)


__all__ = ["ORDERING_PASSES", "LayeredEngine"]
