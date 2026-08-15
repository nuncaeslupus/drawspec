"""T8 — the chosen default layout engine.

The gate is `node_overlap_count == 0`. In this engine that is structural rather
than checked: within a rank boxes are placed sequentially with a gap, and ranks
occupy disjoint bands, so there is no arrangement it can produce in which two
boxes intersect. The tests below try to produce one anyway — over shapes that
break naive layouts, and over a hundred pseudo-random graphs.

The other three properties the gate names are here too: rank increases with depth
in a tree, a cyclic graph terminates, and identical input yields identical
positions. The last is not decoration — these coordinates end up in committed
SVG, so a reordered dict would show up as a diff.

Direction selection is also here. T7's spike found that neither engine chooses a
direction for itself, while "if the arrows do not fit horizontally, the diagram
goes vertical" is a real remedy that something has to apply.
"""

from __future__ import annotations

from itertools import pairwise
from random import Random

import pytest

from drawspec.errors import LayoutError
from drawspec.layout import (
    DIRECTIONS,
    LayeredEngine,
    Layout,
    LayoutEdge,
    LayoutNode,
    Spacing,
    best_layout,
    long_edges,
)

SPACING = Spacing(node_gap=24.0, rank_gap=40.0)
ENGINE = LayeredEngine(spacing=SPACING)


def nodes(*identifiers: str, width: float = 120.0, height: float = 40.0) -> list[LayoutNode]:
    return [LayoutNode(identifier, width, height) for identifier in identifiers]


def edges(*pairs: str) -> list[LayoutEdge]:
    return [LayoutEdge(*pair.split("->")) for pair in pairs]


CHAIN = (nodes("a", "b", "c", "d"), edges("a->b", "b->c", "c->d"))
TREE = (
    nodes("root", "l", "r", "ll", "lr", "rl", "rr"),
    edges("root->l", "root->r", "l->ll", "l->lr", "r->rl", "r->rr"),
)
DIAMOND = (
    nodes("top", "left", "right", "bottom"),
    edges("top->left", "top->right", "left->bottom", "right->bottom"),
)
CYCLE = (nodes("a", "b", "c"), edges("a->b", "b->c", "c->a"))
TANGLE = (
    nodes("a", "b", "c", "d", "e", "f"),
    edges("a->c", "a->d", "b->c", "b->d", "c->e", "d->e", "a->f", "f->e"),
)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "graph", [CHAIN, TREE, DIAMOND, CYCLE, TANGLE], ids=lambda g: str(len(g[0]))
)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_layout_returns_positions_with_no_overlapping_boxes(
    graph: tuple[list[LayoutNode], list[LayoutEdge]], direction: str
) -> None:
    """`node_overlap_count == 0`."""
    result = ENGINE.layout(*graph, direction)
    assert set(result.placements) == {node.id for node in graph[0]}
    assert result.overlaps() == ()


@pytest.mark.parametrize("seed", range(100))
def test_layout_of_a_random_graph_never_overlaps(seed: int) -> None:
    """A hundred graphs of assorted shapes and box sizes, looking for a counter-example."""
    random = Random(seed)
    count = random.randint(1, 12)
    graph_nodes = [
        LayoutNode(f"n{index}", random.uniform(40.0, 260.0), random.uniform(20.0, 90.0))
        for index in range(count)
    ]
    graph_edges = [
        LayoutEdge(f"n{random.randrange(count)}", f"n{random.randrange(count)}")
        for _ in range(random.randint(0, count * 2))
    ]
    result = ENGINE.layout(graph_nodes, graph_edges, random.choice(DIRECTIONS))
    assert result.overlaps() == ()
    assert len(result.placements) == count


def test_layout_of_a_tree_places_children_after_their_parent() -> None:
    """Hierarchy is visible in the geometry, not only in the edges."""
    result = ENGINE.layout(*TREE)
    ranks = {identifier: place.rank for identifier, place in result.placements.items()}
    assert ranks["root"] == 0
    assert ranks["l"] == ranks["r"] == 1
    assert ranks["ll"] == ranks["lr"] == ranks["rl"] == ranks["rr"] == 2
    for parent, child in (("root", "l"), ("l", "ll"), ("r", "rr")):
        assert result.placements[parent].bottom <= result.placements[child].y


def test_layout_of_a_cyclic_graph_terminates_and_returns_positions() -> None:
    """Cycles are broken, not looped on — and the flipped edge is reported."""
    result = ENGINE.layout(*CYCLE)
    assert len(result.placements) == 3
    assert result.overlaps() == ()
    assert len(result.reversed_edges) == 1
    assert result.reversed_edges <= {("a", "b"), ("b", "c"), ("c", "a")}


def test_layout_of_two_interlocking_cycles_terminates() -> None:
    graph_nodes = nodes("a", "b", "c", "d")
    graph_edges = edges("a->b", "b->c", "c->a", "b->d", "d->b")
    result = ENGINE.layout(graph_nodes, graph_edges)
    assert len(result.placements) == 4
    assert result.overlaps() == ()


def test_layout_is_deterministic_across_runs() -> None:
    """These coordinates are committed, so a reordered dict is a diff."""
    for graph in (CHAIN, TREE, DIAMOND, CYCLE, TANGLE):
        first = ENGINE.layout(*graph)
        second = ENGINE.layout(*graph)
        assert first == second


def test_layout_breaks_the_same_cycle_edge_whatever_order_it_is_described_in() -> None:
    """A cycle has no canonical entry point, so which edge gets reversed has to
    be imposed rather than discovered — otherwise the same loop renders
    differently depending on how its edges happened to be listed.

    Note what this does *not* say. Sibling order **is** taken from the document
    (see below), so reordering the nodes of a rank is a real change and moves
    them. Which edge closes a cycle is not something the author states, so it
    may not move.
    """
    graph_nodes, graph_edges = CYCLE
    forward = ENGINE.layout(graph_nodes, graph_edges)
    shuffled = ENGINE.layout(list(reversed(graph_nodes)), list(reversed(graph_edges)))
    assert forward.reversed_edges == shuffled.reversed_edges


# --------------------------------------------------------------------------
# Sibling order
# --------------------------------------------------------------------------


def test_layout_orders_siblings_as_the_document_declares_them() -> None:
    """Three children of one parent all share a barycentre, so the tie decides
    the order of every fan there is. It breaks on declaration order.

    Before this, it broke on id: *Alcalde, Comissió de Govern, 10 Districtes*
    came out in whatever order their ids sorted in, which is no order at all.
    """
    graph_nodes = nodes("root", "zebra", "middle", "alpha")
    graph_edges = edges("root->zebra", "root->middle", "root->alpha")
    result = ENGINE.layout(graph_nodes, graph_edges)
    assert result.ranks[1] == ("zebra", "middle", "alpha")

    rewritten = nodes("root", "alpha", "middle", "zebra")
    assert ENGINE.layout(rewritten, graph_edges).ranks[1] == ("alpha", "middle", "zebra")


def test_layout_orders_unconnected_nodes_as_the_document_declares_them() -> None:
    """With no edges there is no barycentre to compute, so every node is a tie."""
    graph_nodes = nodes("gamma", "alpha", "beta")
    assert ENGINE.layout(graph_nodes, []).ranks == (("gamma", "alpha", "beta"),)


def test_layout_still_reorders_a_rank_when_that_removes_a_crossing() -> None:
    """Declaration order is the tie-break, not an override: a barycentre that
    differs still wins, or the ordering pass would do nothing."""
    graph_nodes = nodes("a", "b", "x", "y")
    graph_edges = edges("a->y", "b->x")
    result = ENGINE.layout(graph_nodes, graph_edges)
    assert result.ranks == (("a", "b"), ("y", "x"))
    assert result.crossings(graph_edges) == 0


# --------------------------------------------------------------------------
# Ranking and ordering
# --------------------------------------------------------------------------


def test_layout_ranks_by_longest_path_so_depth_shows() -> None:
    """A node with a long way in sits as late as its dependencies allow."""
    result = ENGINE.layout(*DIAMOND)
    assert result.placements["bottom"].rank == 2


def test_layout_of_a_long_edge_still_ranks_by_the_longest_path() -> None:
    graph_nodes = nodes("a", "b", "c", "d")
    result = ENGINE.layout(graph_nodes, edges("a->b", "b->c", "c->d", "a->d"))
    assert result.placements["d"].rank == 3


def test_layout_places_a_disconnected_component_at_rank_zero() -> None:
    graph_nodes = nodes("a", "b", "lonely")
    result = ENGINE.layout(graph_nodes, edges("a->b"))
    assert result.placements["lonely"].rank == 0
    assert result.overlaps() == ()


def test_layout_reduces_crossings_where_reordering_can() -> None:
    """The ordering pass has to earn its keep on a graph that needs it.

    Sorted by id, `a->y` and `b->x` cross. A barycentre sweep puts `y` before `x`
    and the crossing goes away — so a non-zero count here would mean the pass is
    not running.
    """
    graph_nodes = nodes("a", "b", "x", "y")
    graph_edges = edges("a->y", "b->x")
    result = ENGINE.layout(graph_nodes, graph_edges)
    assert result.ranks == (("a", "b"), ("y", "x"))
    assert result.crossings(graph_edges) == 0


def test_layout_cannot_remove_a_crossing_that_the_graph_forces() -> None:
    """Two nodes both pointing at the same two nodes is a crossing whatever the
    order — so the count is honest rather than optimistic."""
    graph_nodes, graph_edges = TANGLE
    assert ENGINE.layout(graph_nodes, graph_edges).crossings(graph_edges) == 1


def test_layout_ranks_are_in_order_and_hold_every_node() -> None:
    result = ENGINE.layout(*TANGLE)
    flat = [identifier for rank in result.ranks for identifier in rank]
    assert sorted(flat) == sorted(result.placements)
    for rank, layer in enumerate(result.ranks):
        for identifier in layer:
            assert result.placements[identifier].rank == rank


# --------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------


def test_layout_origin_is_non_negative_and_the_extent_is_the_bounding_box() -> None:
    for direction in DIRECTIONS:
        result = ENGINE.layout(*TREE, direction)
        assert min(place.x for place in result.placements.values()) >= 0
        assert min(place.y for place in result.placements.values()) >= 0
        assert result.width == pytest.approx(max(p.right for p in result.placements.values()))
        assert result.height == pytest.approx(max(p.bottom for p in result.placements.values()))


def test_layout_leaves_at_least_the_rank_gap_between_ranks() -> None:
    """The gap is what guarantees an arrow has a visible shaft."""
    result = ENGINE.layout(*TREE)
    for parent, child in (("root", "l"), ("l", "ll")):
        gap = result.placements[child].y - result.placements[parent].bottom
        assert gap >= SPACING.rank_gap - 1e-9


def test_layout_leaves_at_least_the_node_gap_within_a_rank() -> None:
    result = ENGINE.layout(*TREE)
    for layer in result.ranks:
        placed = sorted((result.placements[i] for i in layer), key=lambda p: p.x)
        for left, right in pairwise(placed):
            assert right.x - left.right >= SPACING.node_gap - 1e-9


def test_layout_centres_each_rank_on_the_widest_one() -> None:
    """A diagram reads down its own middle rather than flushed left."""
    result = ENGINE.layout(*TREE)
    widest = max(result.ranks, key=lambda layer: len(layer))
    centre = (
        min(result.placements[i].x for i in widest)
        + max(result.placements[i].right for i in widest)
    ) / 2
    for layer in result.ranks:
        rank_centre = (
            min(result.placements[i].x for i in layer)
            + max(result.placements[i].right for i in layer)
        ) / 2
        assert rank_centre == pytest.approx(centre)


def test_layout_centres_boxes_of_differing_heights_within_their_band() -> None:
    graph_nodes = [
        LayoutNode("tall", 100.0, 90.0),
        LayoutNode("short", 100.0, 30.0),
        LayoutNode("root", 100.0, 40.0),
    ]
    result = ENGINE.layout(graph_nodes, edges("root->tall", "root->short"))
    tall, short = result.placements["tall"], result.placements["short"]
    assert (tall.y + tall.bottom) / 2 == pytest.approx((short.y + short.bottom) / 2)


def test_layout_right_runs_the_ranks_across_and_keeps_the_boxes_the_same() -> None:
    """`right` is the transposed *problem*, not a transposed picture.

    Each box keeps the size it was measured at; what swaps is which axis the two
    gaps act on — the rank gap becomes horizontal and the node gap vertical.
    """
    down = ENGINE.layout(*TREE, "down")
    right = ENGINE.layout(*TREE, "right")

    for identifier, place in down.placements.items():
        other = right.placements[identifier]
        assert (other.width, other.height) == (place.width, place.height)
        assert other.rank == place.rank

    # Ranks progress along x, and a later rank starts to the right of an earlier one.
    assert right.placements["root"].right <= right.placements["l"].x
    assert right.placements["l"].right <= right.placements["ll"].x
    # Peers within a rank stack vertically, separated by the node gap.
    peers = sorted((right.placements[i] for i in ("l", "r")), key=lambda p: p.y)
    assert peers[1].y - peers[0].bottom >= SPACING.node_gap - 1e-9


def test_layout_of_a_single_node_is_the_node() -> None:
    result = ENGINE.layout(nodes("only"), [])
    place = result.placements["only"]
    assert (place.x, place.y, place.width, place.height, place.rank) == (0.0, 0.0, 120.0, 40.0, 0)
    assert (result.width, result.height) == (120.0, 40.0)


def test_layout_rejects_a_malformed_graph() -> None:
    with pytest.raises(LayoutError, match="no nodes"):
        ENGINE.layout([], [])
    with pytest.raises(LayoutError, match="not a node"):
        ENGINE.layout(nodes("a"), edges("a->ghost"))
    with pytest.raises(LayoutError, match="direction"):
        ENGINE.layout(nodes("a"), [], "diagonally")
    with pytest.raises(LayoutError, match="non-positive"):
        ENGINE.layout([LayoutNode("a", 0.0, 10.0)], [])


# --------------------------------------------------------------------------
# Long edges — what T9 has to route around
# --------------------------------------------------------------------------


def test_long_edges_reports_edges_that_span_more_than_one_rank() -> None:
    graph_nodes = nodes("a", "b", "c")
    graph_edges = edges("a->b", "b->c", "a->c")
    result = ENGINE.layout(graph_nodes, graph_edges)
    assert long_edges(result, graph_edges) == (LayoutEdge("a", "c"),)


def test_long_edges_counts_a_reversed_back_edge() -> None:
    """A back edge spans every rank it jumped, and routing has to go round it."""
    graph_nodes = nodes("a", "b", "c")
    graph_edges = edges("a->b", "b->c", "c->a")
    result = ENGINE.layout(graph_nodes, graph_edges)
    assert LayoutEdge("c", "a") in long_edges(result, graph_edges)


def test_long_edges_is_empty_when_every_edge_joins_adjacent_ranks() -> None:
    graph_nodes, graph_edges = CHAIN
    assert long_edges(ENGINE.layout(graph_nodes, graph_edges), graph_edges) == ()


# --------------------------------------------------------------------------
# Direction selection — the debt T7's spike recorded
# --------------------------------------------------------------------------


def test_best_layout_keeps_the_preferred_direction_when_it_fits() -> None:
    result = best_layout(ENGINE, *CHAIN, max_width=400.0)
    assert result.direction == "down"
    assert result.width <= 400.0
    assert result.fits


def test_best_layout_turns_the_diagram_when_the_preferred_direction_is_too_wide() -> None:
    """ "If the arrows do not fit horizontally, the diagram goes vertical."" """
    wide = [LayoutNode(name, 200.0, 40.0) for name in ("root", "a", "b", "c", "d")]
    result = best_layout(
        ENGINE, wide, edges("root->a", "root->b", "root->c", "root->d"), max_width=520.0
    )
    assert result.direction == "right"
    assert result.fits
    assert result.width <= 520.0


def test_best_layout_returns_the_narrower_attempt_when_neither_fits() -> None:
    """Giving up is the caller's decision — elastic fit gets a turn first."""
    wide = [LayoutNode(name, 400.0, 40.0) for name in ("root", "a", "b", "c")]
    result = best_layout(ENGINE, wide, edges("root->a", "root->b", "root->c"), max_width=300.0)
    assert result.fits is False
    assert result.direction in DIRECTIONS
    assert result.width == min(
        ENGINE.layout(wide, edges("root->a", "root->b", "root->c"), d).width for d in DIRECTIONS
    )


def test_best_layout_honours_an_explicit_preference() -> None:
    result = best_layout(ENGINE, *CHAIN, max_width=4000.0, prefer="right")
    assert result.direction == "right"


def test_best_layout_is_deterministic() -> None:
    first = best_layout(ENGINE, *TREE, max_width=500.0)
    second = best_layout(ENGINE, *TREE, max_width=500.0)
    assert first == second


def test_best_layout_result_is_a_layout() -> None:
    """The direction choice rides along with the layout, not beside it."""
    result = best_layout(ENGINE, *CHAIN, max_width=400.0)
    assert isinstance(result, Layout)
    assert result.overlaps() == ()


def test_best_layout_rejects_an_unknown_preference() -> None:
    with pytest.raises(LayoutError, match="direction"):
        best_layout(ENGINE, *CHAIN, max_width=400.0, prefer="upwards")


# --------------------------------------------------------------------------
# Packing a set with nothing ordering it
# --------------------------------------------------------------------------


def test_layout_of_a_graph_with_no_edges_packs_into_rows() -> None:
    """Ranking turns a relation into a position, and there is no relation here.

    Thirteen components and not one arrow is the Kubernetes control plane, and
    ranked it comes out as a line — thirteen ranks of one, or one rank of
    thirteen — neither of which fits a fixed-width sheet at a legible size.
    """
    graph_nodes = nodes(*(f"n{index}" for index in range(7)), width=120.0)
    result = best_layout(ENGINE, graph_nodes, [], max_width=420.0)
    assert result.ranks == (("n0", "n1", "n2"), ("n3", "n4", "n5"), ("n6",))
    assert result.width <= 420.0
    assert result.fits
    assert result.overlaps() == ()


def test_a_packed_row_is_separated_by_the_node_gap_not_the_rank_gap() -> None:
    """The rank gap buys an arrow its shaft, and there are no arrows."""
    graph_nodes = nodes("a", "b", "c", width=120.0, height=40.0)
    result = best_layout(ENGINE, graph_nodes, [], max_width=270.0)
    assert result.ranks == (("a", "b"), ("c",))
    assert result.placements["c"].y - result.placements["a"].bottom == SPACING.node_gap


def test_packing_keeps_one_box_per_row_when_nothing_fits_beside_it() -> None:
    """A box wider than the sheet still gets a row; `fits` reports the truth."""
    graph_nodes = nodes("wide", "also", width=500.0)
    result = best_layout(ENGINE, graph_nodes, [], max_width=400.0)
    assert result.ranks == (("wide",), ("also",))
    assert not result.fits
