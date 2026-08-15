"""D-1 — the `cycle` kind as a parametric radial template.

What this replaces is the reason it exists. Rendered as a graph, a five-node
cycle came out as a column of boxes with all five edges on one vertical line and
the back edge retracing the forward ones, so the loop was invisible. The
requirements ask for three things of a cycle, and each is asserted here directly
rather than hoped for from a layout engine:

* steps spaced evenly,
* arrows all following the same direction,
* no crossings.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.errors import DrawspecError, FitError, ThemeError
from drawspec.kinds.cycle import MINIMUM_NODES, START_ANGLE, cycle_scene
from drawspec.scene import Path, Polygon, Rect, Scene, TextLine, TextRun, extents
from drawspec.schema import parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

STEPS = (
    "Draft the change",
    "Review it",
    "Revise on the review",
    "Merge it",
    "Record what it taught",
)


def document(*texts: str, **extra: object) -> dict[str, object]:
    ids = [f"s{index}" for index in range(len(texts))]
    return {
        "version": 1,
        "kind": "cycle",
        "title": "A loop",
        "nodes": [{"id": i, "text": t} for i, t in zip(ids, texts, strict=True)],
        "edges": [
            {"from": ids[index], "to": ids[(index + 1) % len(ids)]} for index in range(len(ids))
        ],
        **extra,
    }


def scene(*texts: str, **extra: object) -> Scene:
    return cycle_scene(parse_document(document(*texts, **extra)), THEME, MEASURER)


def boxes(built: Scene) -> list[Rect]:
    return [item for item in built.primitives if isinstance(item, Rect)]


def arcs(built: Scene) -> list[Path]:
    return [item for item in built.primitives if isinstance(item, Path)]


def heads(built: Scene) -> list[Polygon]:
    return [item for item in built.primitives if isinstance(item, Polygon)]


def centre_of(built: Scene) -> tuple[float, float]:
    """Where the family says the ring's centre is.

    Read from the scene's metadata rather than assumed to be the middle of the
    canvas: the canvas is the width every diagram shares and a height cropped to
    the ring, so the two coincide only by accident.
    """
    values = dict(built.metadata)
    return float(values["centre_x"]), float(values["centre_y"])


def angle_of(point: tuple[float, float], centre: tuple[float, float]) -> float:
    return math.atan2(point[1] - centre[1], point[0] - centre[0])


def unwrapped(angles: list[float]) -> list[float]:
    """Angles made monotonic, so a run across the -pi/pi seam still reads as a run."""
    out = [angles[0]]
    for angle in angles[1:]:
        previous = out[-1]
        while angle < previous - math.pi:
            angle += 2 * math.pi
        while angle > previous + math.pi:
            angle -= 2 * math.pi
        out.append(angle)
    return out


# --------------------------------------------------------------------------
# The three things the requirements ask of a cycle
# --------------------------------------------------------------------------


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6, 8])
def test_cycle_steps_are_evenly_spaced_around_the_circle(count: int) -> None:
    """One angle, used for every step. Not accumulated."""
    built = scene(*[f"Step {index}" for index in range(count)])
    centre = centre_of(built)
    angles = sorted(
        angle_of((box.x + box.width / 2, box.y + box.height / 2), centre) for box in boxes(built)
    )
    gaps = [second - first for first, second in pairwise([*angles, angles[0] + 2 * math.pi])]
    assert len(angles) == count
    assert all(gap == pytest.approx(2 * math.pi / count, abs=1e-6) for gap in gaps)


def test_cycle_steps_are_all_the_same_distance_from_the_centre() -> None:
    """A ring, not an oval — every step is a peer at the same radius."""
    built = scene(*STEPS)
    centre = centre_of(built)
    radii = [
        math.dist((box.x + box.width / 2, box.y + box.height / 2), centre) for box in boxes(built)
    ]
    assert max(radii) - min(radii) < 1e-6


def test_cycle_arrows_all_follow_one_direction() -> None:
    """A cycle reads as a cycle wherever the eye enters it."""
    built = scene(*STEPS)
    centre = centre_of(built)
    for arc in arcs(built):
        angles = unwrapped([angle_of(point, centre) for point in arc.points])
        steps = [second - first for first, second in pairwise(angles)]
        assert all(step > 0 for step in steps), "an arc runs the other way round"


def test_cycle_no_edge_crosses_another() -> None:
    """Each arc stays inside its own sector, so two can only meet at a shared step."""
    built = scene(*STEPS)
    centre = centre_of(built)
    spans = []
    for arc in arcs(built):
        angles = unwrapped([angle_of(point, centre) for point in arc.points])
        spans.append((min(angles) % (2 * math.pi), max(angles) % (2 * math.pi)))
    sector = 2 * math.pi / len(STEPS)
    for start, end in spans:
        width = (end - start) % (2 * math.pi)
        assert width <= sector + 1e-6, "an arc spans more than one step's sector"


# --------------------------------------------------------------------------
# Heads, and the shaft the theme insists on
# --------------------------------------------------------------------------


def test_cycle_every_arc_carries_a_head_at_its_far_end() -> None:
    built = scene(*STEPS)
    assert len(heads(built)) == len(arcs(built)) == len(STEPS)
    for arc, head in zip(arcs(built), heads(built), strict=True):
        assert math.dist(arc.points[-1], head.points[0]) <= THEME.edge.head_length + 1e-6


def test_cycle_every_arc_has_a_visible_shaft() -> None:
    """An arrow with no shaft is not an arrow — the radius is sized to prevent it."""
    built = scene(*STEPS)
    for arc in arcs(built):
        length = sum(math.dist(first, second) for first, second in pairwise(arc.points))
        assert length >= THEME.edge.min_shaft_length


def test_cycle_arcs_do_not_run_through_the_boxes_they_join() -> None:
    """The arc stops clear of its target, so the head lands beside the box."""
    built = scene(*STEPS)
    for arc in arcs(built):
        for point in arc.points:
            for box in boxes(built):
                inside = (
                    box.x < point[0] < box.x + box.width and box.y < point[1] < box.y + box.height
                )
                assert not inside, "an arc passes through a step's box"


def test_cycle_headless_role_draws_a_plain_arc() -> None:
    parsed = parse_document(
        {
            "version": 1,
            "kind": "cycle",
            "nodes": [{"id": "a", "text": "One"}, {"id": "b", "text": "Two"}],
            "edges": [
                {"from": "a", "to": "b", "role": "link"},
                {"from": "b", "to": "a", "role": "link"},
            ],
        }
    )
    built = cycle_scene(parsed, THEME, MEASURER)
    assert arcs(built)
    assert heads(built) == []


# --------------------------------------------------------------------------
# Degenerate and malformed loops
# --------------------------------------------------------------------------


def test_cycle_of_two_nodes_still_reads_as_a_loop() -> None:
    """Two steps is a pair of arcs, there and back. It is the smallest cycle."""
    built = scene("There", "Back")
    assert len(boxes(built)) == 2
    assert len(arcs(built)) == 2
    assert len(heads(built)) == 2


def test_cycle_of_one_node_is_refused() -> None:
    with pytest.raises(DrawspecError, match="not a loop"):
        scene("Alone")


def test_cycle_with_an_open_chain_is_refused() -> None:
    """A chain that does not close is a flow, and should be drawn as one."""
    parsed = parse_document(
        {
            "version": 1,
            "kind": "cycle",
            "nodes": [{"id": "a", "text": "One"}, {"id": "b", "text": "Two"}],
            "edges": [{"from": "a", "to": "b"}],
        }
    )
    with pytest.raises(DrawspecError, match="edges to close the loop"):
        cycle_scene(parsed, THEME, MEASURER)


def test_a_fork_with_no_way_round_is_refused() -> None:
    """A step may now have two outgoing edges — but one of the ways round still
    has to be a loop through every node, and here neither is."""
    parsed = parse_document(
        {
            "version": 1,
            "kind": "cycle",
            "nodes": [{"id": n, "text": n} for n in ("a", "b", "c")],
            "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "c"}, {"from": "b", "to": "a"}],
        }
    )
    with pytest.raises(DrawspecError, match="do not close one loop"):
        cycle_scene(parsed, THEME, MEASURER)


def test_cycle_that_closes_early_is_refused() -> None:
    """A short loop with spare nodes beside it is not the diagram the author meant."""
    parsed = parse_document(
        {
            "version": 1,
            "kind": "cycle",
            "nodes": [{"id": n, "text": n} for n in ("a", "b", "c")],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}, {"from": "c", "to": "c"}],
        }
    )
    with pytest.raises(DrawspecError, match="do not close one loop"):
        cycle_scene(parsed, THEME, MEASURER)


def test_cycle_follows_the_edges_not_the_order_the_nodes_were_listed() -> None:
    """An author may list the steps in any order and still get the loop they wrote."""
    parsed = parse_document(
        {
            "version": 1,
            "kind": "cycle",
            "nodes": [{"id": n, "text": n.upper()} for n in ("a", "c", "b")],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "a"}],
        }
    )
    built = cycle_scene(parsed, THEME, MEASURER)
    centre = centre_of(built)
    # Walking the drawn ring clockwise from the top must give A, B, C.
    labelled = []
    for box in boxes(built):
        middle = (box.x + box.width / 2, box.y + box.height / 2)
        text = min(
            (item for item in built.primitives if isinstance(item, TextLine)),
            key=lambda run: math.dist((run.x, run.y), middle),
        )
        # Measured from where the ring starts — the top — not from 3 o'clock.
        clockwise = (angle_of(middle, centre) - START_ANGLE) % (2 * math.pi)
        labelled.append((clockwise, text.text))
    assert [text for _, text in sorted(labelled)] == ["A", "B", "C"]


def test_cycle_too_big_for_the_canvas_raises_fiterror_naming_the_remedies() -> None:
    with pytest.raises(FitError) as error:
        scene(*[f"A rather long label for step number {index}" for index in range(9)], width=320.0)
    message = str(error.value)
    assert "shorten the labels" in message
    assert "fewer steps" in message


def test_minimum_is_two() -> None:
    assert MINIMUM_NODES == 2


# --------------------------------------------------------------------------
# The shared invariants every kind owes
# --------------------------------------------------------------------------


def test_cycle_steps_are_all_the_same_size() -> None:
    """Every step in a loop is a peer, so none may look more important."""
    built = scene(*STEPS)
    assert len({(round(box.width, 6), round(box.height, 6)) for box in boxes(built)}) == 1


def test_cycle_boxes_do_not_overlap() -> None:
    built = scene(*STEPS)
    placed = boxes(built)
    for index, first in enumerate(placed):
        for second in placed[index + 1 :]:
            apart = (
                first.x + first.width <= second.x
                or second.x + second.width <= first.x
                or first.y + first.height <= second.y
                or second.y + second.height <= first.y
            )
            assert apart


@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_cycle_renders_to_safe_svg(profile: str) -> None:
    svg = render(document(*STEPS), profile=profile)
    assert check_embedding_safety(svg, THEME, profile) == ()


def test_cycle_renders_identically_twice() -> None:
    assert render(document(*STEPS)) == render(document(*STEPS))


def test_cycle_is_a_ring_on_the_canvas_width_and_no_taller_than_it_needs() -> None:
    """Round, but not squarely framed.

    The steps are all one radius from one centre — that is the ring, and it is
    what "square" used to stand in for. The canvas around it is the theme's
    width, shared with every other diagram, and a height cropped to the drawing:
    a ring whose steps hold sentences is much wider than it is tall, and squaring
    the canvas would pad a third of the drawing's height above and below it.
    """
    built = scene(*STEPS)
    centre = centre_of(built)
    radii = [
        math.dist((box.x + box.width / 2, box.y + box.height / 2), centre) for box in boxes(built)
    ]
    assert max(radii) - min(radii) < 1e-6
    assert built.width == pytest.approx(THEME.canvas.width)
    # Cropped to the ink, with an equal margin above and below it. The ink is
    # what matters rather than the steps: the lowest point of a five-step ring is
    # the bottom of the arc between the two lowest boxes, not either box.
    _, top, _, bottom = extents(built.primitives)
    assert top == pytest.approx(THEME.box.padding.top)
    assert built.height == pytest.approx(bottom + THEME.box.padding.top)


def test_cycle_refuses_a_document_of_another_kind() -> None:
    parsed = parse_document(
        {"version": 1, "kind": "stack", "items": [{"text": "One"}, {"text": "Two"}]}
    )
    with pytest.raises(DrawspecError, match="not the cycle kind"):
        cycle_scene(parsed, THEME, MEASURER)


def test_every_arc_reaches_the_step_at_each_end() -> None:
    """An arc that touches neither box is a curve floating in the ring.

    The clearance used to come from the box's *diagonal* — the distance to a
    corner — while an arc approaches a wide flat step from the side, a
    half-*width* away. Both ends stopped short by the difference, on a ring whose
    radius already guaranteed a clear chord, and what was left was a stub of arc
    in the middle of each gap: five short curves inside a circle that no longer
    read as a loop.
    """
    built = scene(*STEPS)
    steps = boxes(built)
    reach = THEME.edge.clearance + THEME.edge.head_length + 1.0
    for arc in arcs(built):
        for end in (arc.points[0], arc.points[-1]):
            assert any(_distance_to(box, end) <= reach for box in steps), (
                f"an arc ends at {end}, which is not beside any step"
            )


def _distance_to(box: Rect, point: tuple[float, float]) -> float:
    """How far a point is from a box's outline, and zero when it is inside."""
    across = max(box.x - point[0], point[0] - (box.x + box.width), 0.0)
    down = max(box.y - point[1], point[1] - (box.y + box.height), 0.0)
    return math.hypot(across, down)


# --------------------------------------------------------------------------
# Broad connectors
# --------------------------------------------------------------------------

WHEEL = load_theme("wheel")


def _wheel(*texts: str) -> Scene:
    document = {
        "version": 1,
        "kind": "cycle",
        "title": "A wheel",
        "nodes": [{"id": str(index), "text": text} for index, text in enumerate(texts)],
        "edges": [
            {"from": str(index), "to": str((index + 1) % len(texts))} for index in range(len(texts))
        ],
    }
    return cycle_scene(
        parse_document(document), WHEEL, TextMeasurer(WHEEL.font.stacks(), search_paths=[])
    )


def test_a_band_connector_is_one_closed_figure_not_a_shaft_and_a_head() -> None:
    """Drawn in one piece, the taper is continuous and there is no seam."""
    built = _wheel("Make it", "Use it", "Collect it", "Make it again")
    bands = [item for item in built.primitives if isinstance(item, Polygon)]
    assert len(bands) == 4, "one figure per edge, not two"
    assert not [item for item in built.primitives if isinstance(item, Path)]


def test_a_band_is_wider_than_the_arc_it_replaces() -> None:
    """It is the same arrow drawn fat: the point of the theme."""
    assert WHEEL.cycle.connector == "band"
    assert WHEEL.cycle.width > WHEEL.edge.stroke_width


def test_the_same_document_draws_either_way_without_being_edited() -> None:
    """Appearance is the theme's, so there is no second kind and no field to set."""
    document = {
        "version": 1,
        "kind": "cycle",
        "title": "A cycle",
        "nodes": [{"id": str(index), "text": f"Step {index}"} for index in range(4)],
        "edges": [{"from": str(index), "to": str((index + 1) % 4)} for index in range(4)],
    }
    parsed = parse_document(document)
    thin = cycle_scene(parsed, THEME, MEASURER)
    fat = cycle_scene(parsed, WHEEL, TextMeasurer(WHEEL.font.stacks(), search_paths=[]))
    assert [item for item in thin.primitives if isinstance(item, Path)]
    assert not [item for item in fat.primitives if isinstance(item, Path)]


def test_an_unknown_connector_is_refused_by_the_theme() -> None:
    with pytest.raises(ThemeError, match="connector"):
        load_theme({"version": 1, "name": "bad", "cycle": {"connector": "squiggle"}})


# --------------------------------------------------------------------------
# A loop with one documented exception
# --------------------------------------------------------------------------


NIST = {
    "version": 1,
    "kind": "cycle",
    "title": "The incident lifecycle",
    "nodes": [
        {"id": "prep", "text": "1. Preparation"},
        {"id": "detect", "text": "2. Detection and analysis"},
        {"id": "contain", "text": "3. Containment"},
        {"id": "after", "text": "4. Post-incident activity"},
    ],
    "edges": [
        {"from": "prep", "to": "detect"},
        {"from": "detect", "to": "contain"},
        {"from": "contain", "to": "after"},
        {"from": "after", "to": "prep"},
        {"from": "contain", "to": "detect", "role": "weak", "label": "if new indicators appear"},
    ],
}


def test_a_cycle_may_carry_an_edge_that_is_not_part_of_the_ring() -> None:
    """Four phases round a loop plus one dashed return is a cycle with a
    shortcut, and it used to be neither: the ring refused it, and a `flow`
    broke the loop open and read the phases 3, 4, 1, 2 down the page."""
    built = cycle_scene(parse_document(NIST), THEME, MEASURER)
    assert len(boxes(built)) == 4
    assert "if new indicators appear" in {
        span.text for item in built.primitives if isinstance(item, TextLine) for span in item.spans
    } | {item.text for item in built.primitives if isinstance(item, TextRun)}


def test_the_shortcut_is_drawn_across_the_ring_not_along_it() -> None:
    """Along is what the ring already means: another arc would be
    indistinguishable from the loop it is an exception to."""
    built = cycle_scene(parse_document(NIST), THEME, MEASURER)
    chords = [item for item in built.primitives if isinstance(item, Path) and len(item.points) == 2]
    assert len(chords) == 1
    (start, end) = chords[0].points
    centre = (
        float(dict(built.metadata)["centre_x"]),
        float(dict(built.metadata)["centre_y"]),
    )
    radius = float(dict(built.metadata)["radius"])
    middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    assert math.dist(middle, centre) < radius


def test_the_ring_is_still_the_loop_through_every_step() -> None:
    """The extra edge must not be mistaken for one of the four."""
    built = cycle_scene(parse_document(NIST), THEME, MEASURER)
    arcs = [item for item in built.primitives if isinstance(item, Path) and len(item.points) > 2]
    assert len(arcs) == 4


def test_the_ring_is_found_whichever_order_the_edges_are_written_in() -> None:
    """The shortcut listed first must not be walked as though it were the ring."""
    shuffled = dict(NIST)
    shuffled["edges"] = [NIST["edges"][-1], *NIST["edges"][:-1]]  # type: ignore[index]
    built = cycle_scene(parse_document(shuffled), THEME, MEASURER)
    arcs = [item for item in built.primitives if isinstance(item, Path) and len(item.points) > 2]
    assert len(arcs) == 4
