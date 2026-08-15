"""T11 — the graph kinds: `flow` and `tree`.

The gate is `text_overflow_count == 0`, and this is the family where it is
hardest to hold: the boxes are sized by their own text, placed by an engine that
knows nothing about text, and then have lines and labels threaded between them.
So the overflow test here is not "the box is big enough" — T6 proved that — but
that every piece of text in the finished scene is inside something that was
measured for it.

`cycle` is the third graph kind by the document schema and is *not* here: D-1
moved it to a parametric template, because a cycle through a layered engine is a
column of boxes with a line down the side. The gate's cycle clause is checked
against that template, which is what a `cycle` document actually renders through.
"""

from __future__ import annotations

import json
from dataclasses import replace
from itertools import pairwise

import pytest
from spike_layout import REFERENCE_DIR

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.errors import DocumentError, DrawspecError, FitError
from drawspec.geometry import Box
from drawspec.kinds import IMPLEMENTED, scene_for
from drawspec.kinds.graph import NODE_WIDTH_SHARE, graph_drawing, graph_scene
from drawspec.scene import Path, Scene, TextRun
from drawspec.schema import load_document, parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

#: The same theme with `[box] widen_steps` spent down to none. A family called
#: directly gets no elastic fit around it, so it gets no chance to fall back the
#: way `fit` does when a generous box makes a drawing too wide for the canvas —
#: and these tests are about ranks, anchors and angles, not about how much width
#: a box talked its way into. Fixing the generosity keeps them measuring that.
STRICT = replace(THEME, box=replace(THEME.box, widen_steps=0))


def raw(name: str) -> dict[str, object]:
    """A reference document as the mapping `render` takes."""
    text = (REFERENCE_DIR / f"{name}.json").read_text(encoding="utf-8")
    loaded: dict[str, object] = json.loads(text)
    return loaded


FLOW = load_document(REFERENCE_DIR / "flow-validation.json")
TREE = load_document(REFERENCE_DIR / "tree-decisions.json")
CYCLE = load_document(REFERENCE_DIR / "cycle-review.json")


def document(**extra: object) -> dict[str, object]:
    """A three-node flow: one decision with two branches."""
    return {
        "version": 1,
        "kind": "flow",
        "nodes": [
            {"id": "start", "text": "Start", "role": "start"},
            {"id": "check", "text": "Is it ready?", "role": "decision"},
            {"id": "ship", "text": "Ship it"},
            {"id": "wait", "text": "Wait"},
        ],
        "edges": [
            {"from": "start", "to": "check"},
            {"from": "check", "to": "ship", "label": "yes"},
            {"from": "check", "to": "wait", "label": "no"},
        ],
        **extra,
    }


def scene(**extra: object) -> Scene:
    return graph_scene(parse_document(document(**extra)), THEME, MEASURER)


def texts(built: Scene) -> list[TextRun]:
    return [item for item in built.primitives if isinstance(item, TextRun)]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_flow_document_renders_svg_passing_inline_safety(profile: str) -> None:
    """The reference flow, end to end, through the public entry point."""
    svg = render(raw("flow-validation"), profile=profile)
    assert check_embedding_safety(svg, THEME, profile) == ()


def test_tree_child_ranks_increase_with_depth() -> None:
    """Hierarchy visible in the geometry, not merely in the document."""
    drawing = graph_drawing(TREE, STRICT, MEASURER)
    ranks = {name: place.rank for name, place in drawing.layout.placements.items()}
    for edge in TREE.edges:
        assert ranks[edge.target] > ranks[edge.source], (edge.source, edge.target)


def test_cycle_arrows_all_follow_one_direction() -> None:
    """Checked against the template a `cycle` renders through — see D-1.

    Every arc turns the same way around the ring, so the loop reads as a loop
    wherever the eye enters it. Measured as the sign of the cross product between
    successive steps of each arc.
    """
    built = scene_for(CYCLE, THEME, MEASURER)
    arcs = [item for item in built.primitives if isinstance(item, Path) and len(item.points) > 2]
    assert arcs
    turns = {_turn(arc.points) for arc in arcs}
    assert len(turns) == 1, turns


def test_flow_text_never_overflows_what_was_measured_for_it() -> None:
    """Every run in the finished scene is inside a box or is a placed label.

    The interesting half is the boxes: the engine that placed them never saw the
    text, so this is the assertion that the sizes it was given were the sizes the
    text needed.
    """
    drawing = graph_drawing(FLOW, THEME, MEASURER)
    built = graph_scene(FLOW, THEME, MEASURER)
    labels = {(round(label.left, 6), round(label.top, 6)) for label in drawing.labels}
    for run in texts(built):
        extents = MEASURER.measure(run.text, run.font, THEME.scale[run.level], run.weight)
        box = (
            run.x,
            run.y - extents.ascent,
            run.x + extents.width,
            run.y - extents.ascent + extents.height,
        )
        if (round(box[0], 6), round(box[1], 6)) in labels:
            continue
        assert any(_inside(box, place) for place in drawing.boxes.values()), (run.text, box)


# --------------------------------------------------------------------------
# The drawing
# --------------------------------------------------------------------------


def test_every_edge_becomes_one_route_between_its_own_boxes() -> None:
    drawing = graph_drawing(FLOW, THEME, MEASURER)
    assert len(drawing.routes) == len(FLOW.edges)
    for edge, route in zip(FLOW.edges, drawing.routes, strict=True):
        assert (route.source, route.target) == (edge.source, edge.target)


def test_every_labelled_edge_puts_its_label_in_the_scene() -> None:
    built = scene()
    drawn = {run.text for run in texts(built)}
    assert {"yes", "no"} <= drawn


def test_the_drawing_starts_at_the_origin_with_a_margin() -> None:
    """Nothing is drawn off the canvas, including a route that went around it."""
    drawing = graph_drawing(FLOW, THEME, MEASURER)
    points = [point for route in drawing.routes for point in route.points]
    points += [(box.x, box.y) for box in drawing.boxes.values()]
    points += [(label.left, label.top) for label in drawing.labels]
    assert min(x for x, _ in points) >= 0.0
    assert min(y for _, y in points) >= 0.0
    assert max(x for x, _ in points) <= drawing.width
    assert max(y for _, y in points) <= drawing.height


def test_a_flow_that_will_not_fit_its_width_raises_fiterror() -> None:
    """Rather than overlapping the boxes, or shrinking the arrows to nothing."""
    wide = {
        "version": 1,
        "kind": "flow",
        "width": 120.0,
        "nodes": [{"id": f"n{index}", "text": f"Step number {index}"} for index in range(6)],
        "edges": [{"from": f"n{index}", "to": f"n{index + 1}"} for index in range(5)],
    }
    with pytest.raises(FitError):
        graph_scene(parse_document(wide), THEME, MEASURER)


def test_graph_scene_refuses_a_document_of_another_kind() -> None:
    with pytest.raises(DrawspecError, match="not a graph kind"):
        graph_scene(
            parse_document({"version": 1, "kind": "stack", "items": [{"text": "One"}]}),
            THEME,
            MEASURER,
        )


def test_a_cycle_does_not_come_through_the_graph_family() -> None:
    """The kind is a graph kind by the schema and a template by D-1."""
    with pytest.raises(DrawspecError, match="parametric template"):
        graph_scene(CYCLE, THEME, MEASURER)


def test_node_width_share_leaves_room_for_the_ranks_beside_it() -> None:
    assert 0.0 < NODE_WIDTH_SHARE <= 0.5


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


def test_flow_and_tree_are_implemented_kinds() -> None:
    assert {"flow", "tree"} <= set(IMPLEMENTED)


def test_flow_renders_identically_twice() -> None:
    assert render(raw("flow-validation")) == render(raw("flow-validation"))


def test_tree_renders_to_safe_svg() -> None:
    svg = render(raw("tree-decisions"))
    assert check_embedding_safety(svg, THEME, "inline") == ()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _turn(points: tuple[tuple[float, float], ...]) -> int:
    """Which way a polyline bends, as a sign."""
    total = 0.0
    for (first, second), (_, third) in pairwise(list(pairwise(points))):
        total += (second[0] - first[0]) * (third[1] - second[1]) - (second[1] - first[1]) * (
            third[0] - second[0]
        )
    return (total > 0) - (total < 0)


def _inside(box: tuple[float, float, float, float], place: Box) -> bool:
    left, top, right, bottom = box
    return (
        left >= place.x - 1e-6
        and top >= place.y - 1e-6
        and right <= place.x + place.width + 1e-6
        and bottom <= place.y + place.height + 1e-6
    )


# --------------------------------------------------------------------------
# A subject with named relations on every side
# --------------------------------------------------------------------------


HUB = {
    "version": 1,
    "kind": "flow",
    "title": "What a post is defined by",
    "nodes": [
        {"id": "post", "text": "The post", "centre": True},
        {"id": "unit", "text": "The unit"},
        {"id": "cost", "text": "The cost centre"},
        {"id": "person", "text": "The person"},
        {"id": "role", "text": "The job description"},
    ],
    "edges": [
        {"from": "unit", "to": "post", "label": "contains"},
        {"from": "post", "to": "cost", "label": "charged to"},
        {"from": "person", "to": "post", "label": "holds"},
        {"from": "role", "to": "post", "label": "describes"},
    ],
}


def test_a_centre_node_is_surrounded_rather_than_ranked() -> None:
    """Ranked top to bottom the middle object becomes just another row, and the
    centrality — which is the whole content — is lost."""
    built = graph_drawing(parse_document(HUB), THEME, MEASURER)
    middle = built.boxes["post"]
    around = [built.boxes[key] for key in ("unit", "cost", "person", "role")]
    assert any(box.y + box.height <= middle.y for box in around), "nothing above"
    assert any(box.y >= middle.y + middle.height for box in around), "nothing below"
    assert any(box.x + box.width <= middle.x for box in around), "nothing to the left"
    assert any(box.x >= middle.x + middle.width for box in around), "nothing to the right"


def test_every_relation_of_a_hub_keeps_its_label() -> None:
    """Four labelled edges out of one box ran out of room for the fourth, and
    the drawing only rendered once two arrows were turned round — which left two
    arrowheads pointing the wrong way."""
    built = graph_drawing(parse_document(HUB), THEME, MEASURER)
    assert {label.text for label in built.labels} == {
        "contains",
        "charged to",
        "holds",
        "describes",
    }


def test_a_hub_draws_each_arrow_the_way_the_author_wrote_it() -> None:
    built = graph_drawing(parse_document(HUB), THEME, MEASURER)
    drawn = {(route.source, route.target) for route in built.routes}
    assert ("unit", "post") in drawn
    assert ("post", "cost") in drawn


def test_a_hub_never_overlaps_its_peers() -> None:
    built = graph_drawing(parse_document(HUB), THEME, MEASURER)
    boxes = list(built.boxes.values())
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            assert not (
                first.x < second.x + second.width
                and second.x < first.x + first.width
                and first.y < second.y + second.height
                and second.y < first.y + first.height
            )


def test_two_centres_are_refused() -> None:
    nodes = [{**node, "centre": True} for node in HUB["nodes"][:2]]  # type: ignore[index]
    with pytest.raises(DocumentError, match="one subject"):
        parse_document({**HUB, "nodes": [*nodes, *HUB["nodes"][2:]]})  # type: ignore[index]


def test_a_tree_may_not_name_a_centre() -> None:
    """A tree is ranked from its root, so it has no middle to arrange around."""
    with pytest.raises(DocumentError, match="no middle to arrange around"):
        parse_document({**HUB, "kind": "tree"})
