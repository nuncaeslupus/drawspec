"""Coordinate assignment for graph-shaped diagrams, behind one protocol.

`base` holds the seam — the types and the `LayoutEngine` protocol every engine
implements. `layered` and `grandalf_engine` are the two candidates T7 compares;
whichever wins, callers only ever see the protocol.
"""

from __future__ import annotations

from drawspec.layout.base import (
    DIRECTIONS,
    Layout,
    LayoutEdge,
    LayoutEngine,
    LayoutNode,
    Placement,
    Spacing,
    best_layout,
    break_cycles,
    long_edges,
    rank_nodes,
    validate,
)
from drawspec.layout.layered import LayeredEngine

__all__ = [
    "DIRECTIONS",
    "LayeredEngine",
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
