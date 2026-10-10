"""`lanes` — a flow whose actors are drawn as swimlanes.

The kind's whole claim is geometric: every box sits in its own party's strip, so
an arrow that crosses a strip's boundary is a hand-off and one that does not is
work staying with one party. Those are asserted from the drawing; the document
rules — every node in a lane, every lane holding a node — by the pointer of the
refusal.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError, ThemeError
from drawspec.kinds.graph import GraphDrawing, graph_drawing, graph_scene
from drawspec.kinds.lanes import Swimlanes, acyclic
from drawspec.layout import LayoutEdge
from drawspec.scene import Polygon, TextLine, TextRun
from drawspec.schema import (
    LANES_MAX,
    LANES_PHASES_MAX,
    READABILITY_BUDGET,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("lanes-*.json"))
EPSILON = 1e-6


def claim(**extra: Any) -> dict[str, Any]:
    """An expense claim: three parties, a refusal that goes back, and a payment."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "lanes",
        "lanes": ["Employee", "Manager", "Finance"],
        "nodes": [
            {"id": "submit", "text": "Submits receipts", "actor": "Employee", "role": "start"},
            {"id": "approve", "text": "Approves?", "actor": "Manager", "role": "decision"},
            {"id": "fix", "text": "Corrects the claim", "actor": "Employee"},
            {"id": "pay", "text": "Pays it", "actor": "Finance", "role": "terminal"},
        ],
        "edges": [
            {"from": "submit", "to": "approve"},
            {"from": "approve", "to": "fix", "label": "no"},
            {"from": "fix", "to": "approve", "role": "weak"},
            {"from": "approve", "to": "pay", "label": "yes"},
        ],
    }
    document.update(extra)
    return document


def chain(steps: int, actors: tuple[str, ...]) -> dict[str, Any]:
    """`steps` steps in a row, handed round `actors` in turn."""
    return {
        "version": 1,
        "kind": "lanes",
        "nodes": [
            {
                "id": f"s{index}",
                "text": f"Step number {index}",
                "actor": actors[index % len(actors)],
            }
            for index in range(steps)
        ],
        "edges": [{"from": f"s{index}", "to": f"s{index + 1}"} for index in range(steps - 1)],
    }


def drawn(document: Mapping[str, Any], theme: Any = THEME) -> GraphDrawing:
    return graph_drawing(parse_document(document), theme, MEASURER)


def lanes_of(drawing: GraphDrawing) -> Swimlanes:
    assert drawing.lanes is not None
    return drawing.lanes


def pointers(document: Mapping[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def message_at(document: Mapping[str, Any], pointer: str) -> str:
    return next(v.message for v in validate_document(document) if v.pointer == pointer)


def words(document: Mapping[str, Any]) -> list[str]:
    scene = graph_scene(parse_document(document), THEME, MEASURER)
    found: list[str] = []
    for item in scene.primitives:
        if isinstance(item, TextLine):
            found.append("".join(span.text for span in item.spans))
        elif isinstance(item, TextRun):
            found.append(item.text)
    return found


def inside(box: Any, lane: Any) -> bool:
    return bool(
        lane.x - EPSILON <= box.x
        and box.x + box.width <= lane.right + EPSILON
        and lane.y - EPSILON <= box.y
        and box.y + box.height <= lane.bottom + EPSILON
    )


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_with_each_box_wholly_inside_its_own_lane(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    drawing = drawn(document)
    by_name = {lane.name: lane for lane in lanes_of(drawing).lanes}
    for node in parse_document(document).nodes:
        assert inside(drawing.boxes[node.id], by_name[node.lane]), node.id
    assert render(document).startswith("<svg")


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_a_lanes_document_is_a_flow_document_with_another_kind(path: Path) -> None:
    """The payload stays shared: change the kind back and it is a valid flow."""
    document = json.loads(path.read_text(encoding="utf-8"))
    document["kind"] = "flow"
    document.pop("lanes", None)
    document.pop("phases", None)
    assert validate_document(document) == ()


def test_lanes_are_strips_in_order_side_by_side_with_no_gap_between() -> None:
    lanes = lanes_of(drawn(claim()))
    assert [lane.name for lane in lanes.lanes] == ["Employee", "Manager", "Finance"]
    rows = lanes.orientation == "rows"
    for before, after in pairwise(lanes.lanes):
        end = before.bottom if rows else before.right
        start = after.y if rows else after.x
        assert end == pytest.approx(start)


def test_omitted_lanes_come_in_the_order_their_actors_first_appear() -> None:
    document = claim()
    del document["lanes"]
    document["nodes"].insert(0, document["nodes"].pop(1))  # Manager first
    assert parse_document(document).lanes == ("Manager", "Employee", "Finance")


def test_the_actor_is_drawn_once_as_the_heading_and_not_in_any_box() -> None:
    found = words(claim())
    assert found.count("Manager") == 1
    assert "Approves?" in found


def test_a_node_may_write_its_own_lead_because_the_actor_is_not_one() -> None:
    document = claim()
    document["nodes"][2]["text"] = "Corrects the claim\nwithin a week"
    assert validate_document(document) == ()
    assert "within a week" in words(document)


def test_two_steps_of_one_party_at_one_rank_stack_inside_its_strip() -> None:
    document = claim()
    document["nodes"].append({"id": "copy", "text": "Keeps a copy", "actor": "Employee"})
    document["edges"].append({"from": "approve", "to": "copy"})
    drawing = drawn(document)
    fix, copy = drawing.boxes["fix"], drawing.boxes["copy"]
    assert not (
        fix.x < copy.x + copy.width
        and copy.x < fix.x + fix.width
        and fix.y < copy.y + copy.height
        and copy.y < fix.y + fix.height
    )
    employee = lanes_of(drawing).lanes[0]
    assert inside(fix, employee)
    assert inside(copy, employee)


def test_a_returning_step_is_not_drawn_as_where_the_process_starts() -> None:
    """The cycle is broken from the step nothing leads to, not from a sorted id."""
    edges = [
        LayoutEdge("push", "checks"),
        LayoutEdge("checks", "review"),
        LayoutEdge("review", "amend"),
        LayoutEdge("amend", "checks"),
    ]
    _, back = acyclic(["push", "checks", "review", "amend"], edges)
    assert back == frozenset({("amend", "checks")})


def test_a_self_loop_is_drawn_and_stays_in_its_lane() -> None:
    document = claim()
    document["edges"].append({"from": "pay", "to": "pay", "label": "retry", "role": "weak"})
    drawing = drawn(document)
    assert len(drawing.loops) == 1
    finance = lanes_of(drawing).lanes[-1]
    assert inside(drawing.boxes["pay"], finance)


# ---------------------------------------------------------------------------
# Hand-offs
# ---------------------------------------------------------------------------


def crossings(points: tuple[tuple[float, float], ...], at: float, rows: bool) -> int:
    """How many times a polyline crosses the line `at` across the lanes."""
    count = 0
    for first, second in pairwise(points):
        a, b = (first[1], second[1]) if rows else (first[0], second[0])
        if min(a, b) < at < max(a, b):
            count += 1
    return count


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_an_edge_crosses_an_odd_number_of_times_exactly_the_boundaries_between_its_lanes(
    path: Path,
) -> None:
    """A hand-off crosses each boundary between its two lanes; others it crosses back."""
    document = parse_document(json.loads(path.read_text(encoding="utf-8")))
    drawing = graph_drawing(document, THEME, MEASURER)
    lanes = lanes_of(drawing)
    rows = lanes.orientation == "rows"
    order = [lane.name for lane in lanes.lanes]
    lane_of = {node.id: order.index(node.lane) for node in document.nodes}
    for route in drawing.routes:
        if route.source == route.target:
            continue
        low, high = sorted((lane_of[route.source], lane_of[route.target]))
        for index, lane in enumerate(lanes.lanes[1:], start=1):
            at = lane.y if rows else lane.x
            between = low < index <= high
            assert crossings(route.points, at, rows) % 2 == int(between), (
                route.source,
                route.target,
                lane.name,
            )


def test_no_route_runs_along_a_lane_boundary() -> None:
    for path in REFERENCES:
        drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
        lanes = lanes_of(drawing)
        rows = lanes.orientation == "rows"
        for route in drawing.routes:
            for first, second in pairwise(route.points):
                along = (first[1] == second[1]) if rows else (first[0] == second[0])
                if not along:
                    continue
                at = first[1] if rows else first[0]
                for lane in lanes.lanes[1:]:
                    boundary = lane.y if rows else lane.x
                    assert abs(at - boundary) >= THEME.edge.clearance, (path.stem, route)


def test_separators_are_one_between_each_two_lanes_and_one_under_the_headings() -> None:
    lanes = lanes_of(drawn(claim()))
    assert len(lanes.separators()) == len(lanes.lanes)


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------


def test_auto_falls_back_to_columns_for_seven_steps_that_do_not_fit_across() -> None:
    lanes = lanes_of(drawn(chain(7, ("Requester", "Approver"))))
    assert lanes.orientation == "columns"


def test_auto_takes_rows_when_they_fit() -> None:
    lanes = lanes_of(drawn(chain(3, ("Requester", "Approver"))))
    assert lanes.orientation == "rows"


@pytest.mark.parametrize(("orientation", "direction"), [("rows", "right"), ("columns", "down")])
def test_the_theme_can_fix_the_orientation(orientation: str, direction: str) -> None:
    theme = load_theme({"version": 1, "lanes": {"orientation": orientation}})
    drawing = drawn(chain(3, ("Requester", "Approver")), theme)
    assert lanes_of(drawing).orientation == orientation
    assert drawing.layout.direction == direction


def test_rows_fixed_by_the_theme_refuse_a_drawing_too_long_to_fit_across() -> None:
    theme = load_theme({"version": 1, "lanes": {"orientation": "rows"}})
    with pytest.raises(FitError):
        drawn(chain(9, ("Requester", "Approver")), theme)


def test_rows_put_the_names_in_a_column_before_the_first_step() -> None:
    drawing = drawn(chain(3, ("Requester", "Approver")))
    lanes = lanes_of(drawing)
    for lane in lanes.lanes:
        assert lane.heading.x + lane.heading.width <= lanes.head + EPSILON
    assert min(box.x for box in drawing.boxes.values()) > lanes.head


def test_the_lanes_theme_section_is_checked() -> None:
    with pytest.raises(ThemeError, match="orientation"):
        load_theme({"version": 1, "lanes": {"orientation": "diagonal"}})
    with pytest.raises(ThemeError, match="separator"):
        load_theme({"version": 1, "lanes": {"separator": "dotted"}})
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "lanes": {"colour": "grey"}})


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_node_without_an_actor_is_refused_and_told_about_flow() -> None:
    document = claim()
    del document["nodes"][1]["actor"]
    assert "/nodes/1/actor" in pointers(document)
    assert "flow" in message_at(document, "/nodes/1/actor")


def test_a_blank_actor_is_refused_as_missing() -> None:
    document = claim()
    del document["lanes"]
    document["nodes"][1]["actor"] = "  "
    assert "flow" in message_at(document, "/nodes/1/actor")


def test_an_actor_not_in_lanes_is_refused_naming_the_closest_lane() -> None:
    document = claim()
    document["nodes"][3]["actor"] = "Finance "
    message = message_at(document, "/nodes/3/actor")
    assert "'Finance'" in message


def test_a_lane_no_node_names_is_refused() -> None:
    document = claim(lanes=["Employee", "Manager", "Finance", "Legal"])
    assert "/lanes/3" in pointers(document)
    assert "empty" in message_at(document, "/lanes/3")


def test_a_lane_listed_twice_is_refused() -> None:
    document = claim(lanes=["Employee", "Manager", "Finance", "Manager"])
    assert "/lanes/3" in pointers(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("groups", [{"id": "g", "members": ["submit"]}]),
        ("bands", [{"text": "Audit", "members": ["submit"]}]),
    ],
)
def test_containers_are_refused_because_a_lane_is_the_container(field: str, value: Any) -> None:
    document = claim(**{field: value})
    assert f"/{field}" in pointers(document)
    assert "lane" in message_at(document, f"/{field}")


def test_centre_is_refused_with_its_reason() -> None:
    document = claim()
    document["nodes"][1]["centre"] = True
    assert "flow" in message_at(document, "/nodes/1/centre")


def test_the_group_role_is_refused_on_a_step() -> None:
    document = claim()
    document["nodes"][1]["role"] = "group"
    assert "/nodes/1/role" in pointers(document)


def test_edges_must_land_on_nodes() -> None:
    document = claim()
    document["edges"][0]["to"] = "nowhere"
    assert "/edges/0/to" in pointers(document)


def test_a_seventh_lane_from_the_actors_is_refused_at_the_node_naming_it() -> None:
    document = chain(LANES_MAX + 1, tuple(f"Party {n}" for n in range(LANES_MAX + 1)))
    assert pointers(document) == [f"/nodes/{LANES_MAX}/actor"]


def test_a_seventh_listed_lane_is_refused_by_the_budget() -> None:
    names = [f"Party {n}" for n in range(LANES_MAX + 1)]
    document = chain(LANES_MAX + 1, tuple(names))
    document["lanes"] = names
    assert f"/lanes/{LANES_MAX}" in pointers(document)


def test_the_budget_is_a_flows_plus_the_lanes() -> None:
    # Less the flow's causal loops, which a lanes document cannot name.
    flow = {name: limit for name, limit in READABILITY_BUDGET["flow"] if name != "loops"}
    assert dict(READABILITY_BUDGET["lanes"]) == {
        **flow,
        "lanes": LANES_MAX,
        "phases": LANES_PHASES_MAX,
    }


def test_a_refused_document_raises_with_every_violation() -> None:
    document = claim(groups=[])
    del document["nodes"][0]["actor"]
    with pytest.raises(DocumentError) as raised:
        parse_document(document)
    assert {violation.pointer for violation in raised.value.violations} >= {
        "/groups",
        "/nodes/0/actor",
    }


def test_every_second_lane_is_striped_with_a_faint_wash_of_the_ink() -> None:
    document = chain(4, ("Customer", "Shop", "Courier", "Bank"))
    scene = graph_scene(parse_document(document), THEME, MEASURER)
    stripes = [p for p in scene.primitives if isinstance(p, Polygon) and p.region]
    lanes = lanes_of(drawn(document)).lanes
    assert len(stripes) == len(lanes) // 2
    for stripe, lane in zip(stripes, lanes[1::2], strict=True):
        assert stripe.fill_opacity == pytest.approx(THEME.lanes.stripe)
        assert stripe.fill_colour == "currentColor"
        assert min(x for x, _ in stripe.points) == pytest.approx(lane.x)


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def phased(**extra: Any) -> dict[str, Any]:
    """The expense claim in two phases, the refusal loop inside the first."""
    return claim(
        phases=[
            {"text": "Claim", "members": ["submit", "approve", "fix"]},
            {"text": "Payment", "members": ["pay"]},
        ],
        **extra,
    )


def short() -> dict[str, Any]:
    """Four short steps in two phases: short enough to run across the page too."""
    document = chain(4, ("Pupil", "Librarian"))
    for node in document["nodes"]:
        node["text"] = f"Step {node['id'][1:]}"
    document["phases"] = [
        {"text": "Borrow", "members": ["s0", "s1"]},
        {"text": "Return", "members": ["s2", "s3"]},
    ]
    return document


ORIENTED = [
    load_theme({"version": 1, "lanes": {"orientation": orientation}})
    for orientation in ("rows", "columns")
]


@pytest.mark.parametrize("theme", ORIENTED, ids=["rows", "columns"])
def test_each_phase_holds_its_steps_and_the_line_falls_between_phases(theme: Any) -> None:
    document = short()
    drawing = drawn(document, theme)
    lanes = lanes_of(drawing)
    rows = lanes.orientation == "rows"
    cells = lanes.phase_cells()
    assert len(cells) == 2
    assert len(lanes.phase_lines()) == 1
    for phase, (start, end) in zip(document["phases"], cells, strict=True):
        for member in phase["members"]:
            box = drawing.boxes[member]
            near, far = (box.x, box.x + box.width) if rows else (box.y, box.y + box.height)
            assert start - EPSILON <= near and far <= end + EPSILON, member


@pytest.mark.parametrize("theme", ORIENTED, ids=["rows", "columns"])
def test_the_phase_band_lies_outside_the_lanes_and_names_each_phase(theme: Any) -> None:
    lanes = lanes_of(drawn(short(), theme))
    assert len(lanes.phase_names()) == 2
    left, top, _, _ = lanes.strips
    for name in lanes.phase_names():
        if lanes.orientation == "rows":
            assert name.y + name.height <= top + EPSILON
        else:
            assert name.x + name.width <= left + EPSILON
    found = words(phased())
    assert "Claim" in found
    assert "Payment" in found


def test_a_later_phase_starts_after_every_step_of_the_earlier_one() -> None:
    """A short branch of phase two would rank beside phase one; the phase pushes it on."""
    document = chain(4, ("Requester", "Approver"))
    document["nodes"].append({"id": "early", "text": "Files it", "actor": "Requester"})
    document["edges"].append({"from": "s0", "to": "early"})
    document["phases"] = [
        {"text": "Prepare", "members": ["s0", "s1", "s2"]},
        {"text": "Finish", "members": ["s3", "early"]},
    ]
    drawing = drawn(document)
    rank = {i: place.rank for i, place in drawing.layout.placements.items()}
    assert rank["early"] > max(rank["s0"], rank["s1"], rank["s2"])


def test_an_arrow_back_into_an_earlier_phase_that_loops_is_drawn_as_a_return() -> None:
    document = phased()
    document["edges"].append({"from": "pay", "to": "submit", "label": "next month"})
    assert validate_document(document) == ()
    drawing = drawn(document)
    assert ("pay", "submit") in drawing.layout.reversed_edges
    rank = {i: place.rank for i, place in drawing.layout.placements.items()}
    assert rank["pay"] > rank["fix"]


def test_no_route_runs_along_a_phase_line() -> None:
    for path in REFERENCES:
        drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
        lanes = lanes_of(drawing)
        rows = lanes.orientation == "rows"
        for route in drawing.routes:
            for first, second in pairwise(route.points):
                if (first[0] == second[0]) != rows:
                    continue
                at = first[0] if rows else first[1]
                for line in lanes.boundaries:
                    assert abs(at - line) >= THEME.edge.clearance, (path.stem, route)


def test_a_phase_member_that_is_no_step_is_refused_naming_the_closest() -> None:
    document = phased()
    document["phases"][0]["members"][1] = "aprove"
    assert "did you mean 'approve'" in message_at(document, "/phases/0/members/1")


def test_a_step_in_two_phases_is_refused_as_overlapping() -> None:
    document = phased()
    document["phases"][1]["members"].append("fix")
    assert "already in the phase 'Claim'" in message_at(document, "/phases/1/members/1")


def test_a_step_in_no_phase_is_refused_at_the_step() -> None:
    document = phased()
    document["phases"][0]["members"].remove("fix")
    assert "in no phase" in message_at(document, "/nodes/2")


def test_phases_out_of_order_are_refused_at_the_arrow_that_runs_backwards() -> None:
    document = phased()
    document["phases"].reverse()
    assert "out of order" in message_at(document, "/edges/3")


def test_one_phase_is_refused_and_seven_are_past_the_budget() -> None:
    one = phased()
    one["phases"] = [{"text": "All", "members": ["submit", "approve", "fix", "pay"]}]
    assert "/phases" in pointers(one)
    many = chain(LANES_PHASES_MAX + 1, ("Requester", "Approver"))
    many["phases"] = [
        {"text": f"Phase {index}", "members": [f"s{index}"]}
        for index in range(LANES_PHASES_MAX + 1)
    ]
    assert f"/phases/{LANES_PHASES_MAX}" in pointers(many)


def test_phases_belong_to_lanes_only() -> None:
    document = phased()
    document["kind"] = "flow"
    for node in document["nodes"]:
        node.pop("actor")
    del document["lanes"]
    assert "/phases" in pointers(document)


def test_the_phase_line_role_is_a_checked_theme_key() -> None:
    assert THEME.lanes.phase == "aside"
    with pytest.raises(ThemeError, match="phase"):
        load_theme({"version": 1, "lanes": {"phase": "dotted"}})
