"""A `grandalf` adapter: T7's other candidate.

grandalf implements a full Sugiyama layout — the same four passes as
`layered.py`, but with a proper crossing-reduction and priority-based coordinate
assignment behind them. If a pure-Python default is going to be beaten on
quality, this is what beats it.

Two things about it that are not about quality, and that T7 exists to weigh
against quality:

**Licence.** grandalf is dual-licensed GPLv2 / EPL-1.0. Only the EPL-1.0 arm is
compatible with shipping MIT code around it, so choosing grandalf means
depending on that arm — and, if the project ever needed to vendor it, vendoring
under EPL-1.0 with the notices that requires.

**Maintenance.** v0.8, lightly maintained. That is survivable precisely because
of the protocol this file implements: replacing it later touches this file and
nothing else.

This module imports grandalf at call time rather than at import time, so
`drawspec` still imports on an install that does not have it — grandalf is an
optional `spike` extra, never a runtime dependency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from drawspec.errors import LayoutError
from drawspec.layout.base import (
    Layout,
    LayoutEdge,
    LayoutNode,
    Placement,
    Spacing,
    break_cycles,
    validate,
)


def available() -> bool:
    """Whether grandalf can be imported in this environment."""
    try:
        import grandalf  # noqa: F401
    except ImportError:
        return False
    return True


class _View:
    """The size object grandalf expects to find on each vertex."""

    def __init__(self, width: float, height: float) -> None:
        self.w = width
        self.h = height
        self.xy: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class GrandalfEngine:
    """grandalf's Sugiyama layout, behind the `LayoutEngine` protocol."""

    spacing: Spacing = field(default_factory=Spacing)
    name: str = "grandalf"

    def layout(
        self,
        nodes: Sequence[LayoutNode],
        edges: Sequence[LayoutEdge],
        direction: str = "down",
    ) -> Layout:
        """Place every node with grandalf.

        Raises:
            LayoutError: the graph is malformed, the direction is unknown, or
                grandalf is not installed.
        """
        validate(nodes, edges, direction)
        try:
            from grandalf.graphs import Edge as GrandalfEdge
            from grandalf.graphs import Graph, Vertex
            from grandalf.layouts import SugiyamaLayout
        except ImportError as error:  # pragma: no cover - exercised by `available()`
            raise LayoutError(
                "grandalf is not installed; it is an optional `spike` extra, not a "
                "runtime dependency. Install it with `uv sync --all-extras`."
            ) from error

        transposed = direction == "right"
        vertices = {
            node.id: self._vertex(Vertex, node, transposed=transposed)
            for node in sorted(nodes, key=lambda item: item.id)
        }

        # grandalf cannot rank a cyclic graph unaided: it needs the back edges
        # named. We already compute them deterministically for our own engine, so
        # both candidates break the same cycles the same way and the comparison is
        # about layout rather than about cycle choice.
        _, reversed_edges = break_cycles(nodes, edges)
        built: list[Any] = []
        inverted: list[Any] = []
        for edge in edges:
            if edge.source == edge.target:
                continue
            built.append(GrandalfEdge(vertices[edge.source], vertices[edge.target]))
            if (edge.source, edge.target) in reversed_edges:
                inverted.append(built[-1])

        graph = Graph(list(vertices.values()), built)

        placements: dict[str, Placement] = {}
        ranks: list[list[str]] = []
        offset = 0.0
        for component in graph.C:
            drawn, layers, extent = self._draw_component(
                SugiyamaLayout, component, vertices, inverted, transposed=transposed
            )
            for identifier, place in drawn.items():
                placements[identifier] = Placement(
                    x=place.x + (0.0 if transposed else offset),
                    y=place.y + (offset if transposed else 0.0),
                    width=place.width,
                    height=place.height,
                    rank=place.rank,
                )
            # Components are laid out independently and then set side by side —
            # grandalf has no opinion about where a second component goes.
            offset += extent + self.spacing.node_gap
            ranks = _merge_ranks(ranks, layers)

        if not placements:  # pragma: no cover - validate() rejects an empty graph
            raise LayoutError("grandalf returned no placements")

        return self._normalised(placements, ranks, reversed_edges)

    # -- one component ----------------------------------------------------

    def _vertex(self, vertex_type: Any, node: LayoutNode, *, transposed: bool) -> Any:
        vertex = vertex_type(node.id)
        # grandalf only lays out downwards, so `right` is the transposed problem:
        # swap each box's dimensions going in and swap the coordinates coming out.
        vertex.view = (
            _View(node.height, node.width) if transposed else _View(node.width, node.height)
        )
        return vertex

    def _draw_component(
        self,
        layout_type: Any,
        component: Any,
        vertices: dict[str, Any],
        inverted: list[Any],
        *,
        transposed: bool,
    ) -> tuple[dict[str, Placement], list[list[str]], float]:
        # grandalf ranks from the roots it is given, so which vertices those are
        # decides the whole layout. Sorted by id, and preferring the ones with no
        # incoming edge, so two runs of the same graph start from the same place.
        ordered = sorted(component.sV, key=lambda vertex: str(vertex.data))
        entry = [vertex for vertex in ordered if not _has_incoming(component, vertex, inverted)]

        sugiyama = layout_type(component)
        try:
            sugiyama.init_all(roots=entry or ordered[:1], inverted_edges=inverted)
            sugiyama.xspace = self.spacing.node_gap
            sugiyama.yspace = self.spacing.rank_gap
            sugiyama.draw()
        except Exception as error:  # grandalf raises bare exceptions on odd graphs
            raise LayoutError(f"grandalf could not lay out this graph: {error}") from error

        rank_of: dict[str, int] = {}
        layers: list[list[str]] = []
        for index, layer in enumerate(sugiyama.layers):
            named = [str(vertex.data) for vertex in layer if hasattr(vertex, "data")]
            layers.append([name for name in named if name in vertices])
            for name in layers[-1]:
                rank_of[name] = index

        placements: dict[str, Placement] = {}
        for identifier, vertex in vertices.items():
            if vertex not in component.sV:
                continue
            centre_x, centre_y = vertex.view.xy
            width, height = (
                (vertex.view.h, vertex.view.w) if transposed else (vertex.view.w, vertex.view.h)
            )
            x, y = (centre_y, centre_x) if transposed else (centre_x, centre_y)
            placements[identifier] = Placement(
                x=x - width / 2,
                y=y - height / 2,
                width=width,
                height=height,
                rank=rank_of.get(identifier, 0),
            )

        span = _extent(placements, across=not transposed)
        return placements, layers, span

    # -- tidying up -------------------------------------------------------

    @staticmethod
    def _normalised(
        placements: dict[str, Placement],
        ranks: list[list[str]],
        reversed_edges: frozenset[tuple[str, str]],
    ) -> Layout:
        """Shift everything to a non-negative origin and measure the result.

        grandalf centres its output on zero, so roughly half of every layout it
        produces has negative coordinates. An SVG `viewBox` starting at 0 0 is
        simpler to reason about than one that does not, so the whole drawing is
        translated once, here.
        """
        left = min(place.x for place in placements.values())
        top = min(place.y for place in placements.values())
        shifted = {
            identifier: Placement(
                x=place.x - left,
                y=place.y - top,
                width=place.width,
                height=place.height,
                rank=place.rank,
            )
            for identifier, place in placements.items()
        }
        return Layout(
            placements=shifted,
            width=max(place.right for place in shifted.values()),
            height=max(place.bottom for place in shifted.values()),
            ranks=tuple(tuple(layer) for layer in ranks),
            reversed_edges=reversed_edges,
        )


def _has_incoming(component: Any, vertex: Any, inverted: list[Any]) -> bool:
    """Whether `vertex` has an incoming edge, counting inversions."""
    for edge in component.sE:
        source, target = edge.v
        if edge in inverted:
            source, target = target, source
        if target is vertex:
            return True
    return False


def _extent(placements: dict[str, Placement], *, across: bool) -> float:
    if not placements:
        return 0.0
    if across:
        return max(place.right for place in placements.values()) - min(
            place.x for place in placements.values()
        )
    return max(place.bottom for place in placements.values()) - min(
        place.y for place in placements.values()
    )


def _merge_ranks(existing: list[list[str]], addition: list[list[str]]) -> list[list[str]]:
    """Concatenate two components' rank lists rank by rank."""
    merged = [list(layer) for layer in existing]
    for index, layer in enumerate(addition):
        if index < len(merged):
            merged[index].extend(layer)
        else:
            merged.append(list(layer))
    return merged


__all__ = ["GrandalfEngine", "available"]
