"""T10 — edge label placement.

The gate is `label_overlap_count == 0`, and there are three things a label can
land on: the line it belongs to, a box, or another label. All three are the same
failure to a reader — text with something drawn through it — so all three are
measured here, on the returned box rather than on the placer's intentions.

The geometry a label is placed against comes from T9, so these tests route real
edges rather than inventing paths: a label that misses a path drawspec would
never draw is not evidence of anything.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from spike_layout import REFERENCE_DIR, layout_inputs

from drawspec.errors import FitError
from drawspec.layout.base import Spacing
from drawspec.layout.layered import LayeredEngine
from drawspec.routing import (
    Connector,
    Label,
    Obstacle,
    Route,
    label_primitives,
    minimum_rank_gap,
    place_labels,
    route_edges,
)
from drawspec.scene import TextRun
from drawspec.schema import load_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
GAP = minimum_rank_gap(THEME)
SPACING = Spacing(node_gap=THEME.box.padding.horizontal, rank_gap=max(GAP, 24.0))

COLUMN = (
    Obstacle("a", x=100.0, y=0.0, width=140.0, height=40.0),
    Obstacle("b", x=100.0, y=40.0 + GAP, width=140.0, height=40.0),
    Obstacle("c", x=100.0, y=80.0 + GAP * 2, width=140.0, height=40.0),
)
SIBLING = Obstacle("d", x=280.0, y=40.0 + GAP, width=140.0, height=40.0)


def placed(
    connectors: tuple[Connector, ...], boxes: tuple[Obstacle, ...] = COLUMN
) -> tuple[tuple[Route, ...], tuple[Label, ...]]:
    routes = route_edges(connectors, boxes, THEME)
    return routes, place_labels(routes, boxes, THEME, MEASURER)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_edge_label_does_not_intersect_any_edge_path() -> None:
    """Including its own — a label sitting on its line is the usual way this fails."""
    routes, labels = placed((Connector("a", "b", label="yes"), Connector("a", "c", label="no")))
    assert len(labels) == 2
    for label in labels:
        for route in routes:
            for first, second in pairwise(route.points):
                assert not _meets(label.box, first, second), (label.text, route.target)


def test_edge_label_does_not_intersect_any_node_box() -> None:
    _, labels = placed((Connector("a", "b", label="accepted"), Connector("b", "c", label="on")))
    for label in labels:
        for box in COLUMN:
            assert not _overlaps(label.box, (box.x, box.y, box.right, box.bottom)), (
                label.text,
                box.id,
            )


def test_edge_label_offsets_when_the_default_position_is_occupied() -> None:
    """Two labels on the same short route cannot both take the obvious place."""
    boxes = (*COLUMN, SIBLING)
    routes = route_edges(
        (Connector("b", "c", label="first"), Connector("b", "d", label="second")), boxes, THEME
    )
    labels = place_labels(routes, boxes, THEME, MEASURER)
    assert len(labels) == 2
    assert not _overlaps(labels[0].box, labels[1].box)


# --------------------------------------------------------------------------
# Which place it takes when it has a choice
# --------------------------------------------------------------------------


def test_a_label_sits_beside_the_middle_of_its_own_route() -> None:
    """Near the line it names, or it names nothing in particular."""
    routes, (label,) = placed((Connector("a", "b", label="yes"),))
    middle_y = (routes[0].points[0][1] + routes[0].points[-1][1]) / 2
    left, top, right, bottom = label.box
    assert top - 12 <= middle_y <= bottom + 12
    assert abs((left + right) / 2 - routes[0].points[0][0]) < 60


def test_a_label_beside_a_vertical_run_clears_it_horizontally() -> None:
    routes, (label,) = placed((Connector("a", "b", label="yes"),))
    left, _, right, _ = label.box
    line_x = routes[0].points[0][0]
    assert right < line_x or left > line_x


def test_an_edge_without_a_label_gets_no_label() -> None:
    _, labels = placed((Connector("a", "b"), Connector("b", "c", label="on")))
    assert [label.text for label in labels] == ["on"]


def test_a_label_carries_its_own_edge_role() -> None:
    _, (label,) = placed((Connector("a", "b", label="maybe", role="weak"),))
    assert label.role == "weak"


def test_label_placement_is_deterministic() -> None:
    connectors = (Connector("a", "b", label="yes"), Connector("a", "c", label="no"))
    assert placed(connectors)[1] == placed(connectors)[1]


def test_a_label_with_nowhere_to_go_is_refused() -> None:
    """Boxed in on every side is a statement about the diagram, not a shrug.

    Rendering it anyway would put text over a line, which is the failure this
    task exists to prevent — so it raises, and the message says what to do.

    A `FitError`, which is the accurate name for it: the label is content that
    does not fit, and content that does not fit is what the elastic band exists
    to answer. As a `LayoutError` it went straight past `fit`, so a diagram whose
    labels would all have been clear one step of type smaller was refused instead
    of drawn — four of the eighty-six corpus documents, once their labels grew a
    line. When the band runs out the author still gets this message.
    """
    boxes = (
        Obstacle("a", x=0.0, y=0.0, width=40.0, height=40.0),
        Obstacle("b", x=0.0, y=40.0 + GAP, width=40.0, height=40.0),
        Obstacle("left", x=-400.0, y=40.0, width=396.0, height=GAP),
        Obstacle("right", x=44.0, y=40.0, width=400.0, height=GAP),
    )
    with pytest.raises(FitError, match="no room"):
        place_labels(
            route_edges((Connector("a", "b", label="a rather long label"),), boxes, THEME),
            boxes,
            THEME,
            MEASURER,
        )


# --------------------------------------------------------------------------
# The gate, on a real graph
# --------------------------------------------------------------------------


@pytest.mark.parametrize("direction", ["down", "right"])
def test_reference_flow_places_every_label_without_an_overlap(direction: str) -> None:
    """`label_overlap_count == 0` on the document that has labels on both branches.

    Measured against the node **shapes**: the empty corner beside a decision is
    where a `yes` belongs, so counting the bounding rectangle as occupied would
    be measuring the wrong thing — and would have made this document
    unrenderable rather than merely awkward.
    """
    parsed = load_document(REFERENCE_DIR / "flow-validation.json")
    nodes, edges = layout_inputs(parsed, THEME, MEASURER)
    layout = LayeredEngine(spacing=SPACING).layout(nodes, edges, direction)
    shapes = {node.id: THEME.roles[node.role].shape for node in parsed.nodes}
    obstacles = tuple(
        Obstacle(
            identifier,
            x=place.x,
            y=place.y,
            width=place.width,
            height=place.height,
            shape=shapes[identifier],
        )
        for identifier, place in sorted(layout.placements.items())
    )
    connectors = tuple(
        Connector(edge.source, edge.target, role=edge.role, label=edge.label)
        for edge in parsed.edges
    )

    routes = route_edges(connectors, obstacles, THEME, direction=direction)
    labels = place_labels(routes, obstacles, THEME, MEASURER)
    assert len(labels) == sum(1 for connector in connectors if connector.label)

    for index, label in enumerate(labels):
        for box in obstacles:
            assert not box.overlaps(label.box), (label.text, box.id)
        for route in routes:
            for first, second in pairwise(route.points):
                assert not _meets(label.box, first, second), (label.text, route.target)
        for other in labels[index + 1 :]:
            assert not _overlaps(label.box, other.box), (label.text, other.text)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


def test_label_primitives_are_one_text_run_at_the_label_level() -> None:
    _, (label,) = placed((Connector("a", "b", label="yes"),))
    (run,) = label_primitives(label)
    assert isinstance(run, TextRun)
    assert run.text == "yes"
    assert run.level == "label"


def test_label_text_run_sits_inside_the_box_that_was_measured() -> None:
    """The box the overlap tests use is the box the text is drawn in."""
    _, (label,) = placed((Connector("a", "b", label="yes"),))
    (primitive,) = label_primitives(label)
    assert isinstance(primitive, TextRun)
    run = primitive
    extents = MEASURER.measure(run.text, run.font, THEME.scale["label"], run.weight)
    left, top, right, bottom = label.box
    starts = {"middle": run.x - extents.width / 2, "start": run.x, "end": run.x - extents.width}
    assert starts[run.anchor] == pytest.approx(left)
    assert run.y - extents.ascent == pytest.approx(top)
    assert right - left == pytest.approx(extents.width)
    assert bottom - top == pytest.approx(extents.height)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _overlaps(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    return (
        first[0] < second[2] - 1e-6
        and second[0] < first[2] - 1e-6
        and first[1] < second[3] - 1e-6
        and second[1] < first[3] - 1e-6
    )


def _meets(
    box: tuple[float, float, float, float],
    first: tuple[float, float],
    second: tuple[float, float],
    samples: int = 40,
) -> bool:
    left, top, right, bottom = box
    for step in range(samples + 1):
        fraction = step / samples
        x = first[0] + (second[0] - first[0]) * fraction
        y = first[1] + (second[1] - first[1]) * fraction
        if left - 1e-6 < x < right + 1e-6 and top - 1e-6 < y < bottom + 1e-6:
            return True
    return False
