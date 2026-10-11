"""`states` — a state machine, drawn by the graph family with its pseudo-states.

A state machine looked like a `flow` and claimed something else: the boxes are
conditions something is in, not steps done once, so the initial state is a dot
with no words, every transition is labelled `event [guard] / action`, a state
nothing reaches is a bug, and a retry or a reminder is a loop back to the same
box. Each of those is asserted here — the drawing's claims by geometry, the
machine's by the pointer of the refusal.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, ThemeError
from drawspec.kinds.graph import GraphDrawing, graph_drawing, graph_scene
from drawspec.routing import LOOP_SIDES, loop_reach
from drawspec.scene import Ellipse, TextLine, TextRun
from drawspec.scene import Path as ScenePath
from drawspec.schema import (
    READABILITY_BUDGET,
    parse_document,
    transition_label,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
EPSILON = 1e-6


def machine(**extra: Any) -> dict[str, Any]:
    """A small machine: a breaker, closed until calls fail, with a retry loop."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "states",
        "initial": "closed",
        "states": [
            {"id": "closed", "text": "Closed"},
            {"id": "open", "text": "Open"},
            {"id": "half", "text": "Half-open"},
        ],
        "transitions": [
            {"from": "closed", "to": "closed", "event": "call fails", "action": "count it"},
            {"from": "closed", "to": "open", "event": "threshold reached"},
            {"from": "open", "to": "half", "event": "cool-down"},
            {"from": "half", "to": "closed", "event": "trial succeeds"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: Mapping[str, Any]) -> GraphDrawing:
    return graph_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: Mapping[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: Mapping[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def marker(drawing: GraphDrawing, kind: str) -> list[str]:
    return [identifier for identifier, mark in drawing.markers.items() if mark == kind]


def on_border(point: tuple[float, float], box: Any) -> bool:
    x, y = point
    left, top = float(box.x), float(box.y)
    width, height = float(box.width), float(box.height)
    inside_x = left - EPSILON <= x <= left + width + EPSILON
    inside_y = top - EPSILON <= y <= top + height + EPSILON
    edge_x = abs(x - left) < EPSILON or abs(x - left - width) < EPSILON
    edge_y = abs(y - top) < EPSILON or abs(y - top - height) < EPSILON
    return inside_x and inside_y and (edge_x or edge_y)


# ---------------------------------------------------------------------------
# The label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parts", "label"),
    [
        (("dispatched", "", ""), "dispatched"),
        (("call fails", "under the threshold", ""), "call fails\n[under the threshold]"),
        (("trial succeeds", "", "reset the count"), "trial succeeds\n/ reset the count"),
        (("call fails", "under", "count it"), "call fails\n[under]\n/ count it"),
        (("", "ready", ""), "[ready]"),
        (("", "", "log it"), "/ log it"),
        (("", "", ""), ""),
        ((" padded ", " ", ""), "padded"),
    ],
)
def test_a_transition_label_is_composed_with_no_stray_brackets_or_slashes(
    parts: tuple[str, str, str], label: str
) -> None:
    """`event [guard] / action`, one part per line, and only the parts given."""
    assert transition_label(*parts) == label


def test_the_composed_label_is_what_the_edge_carries() -> None:
    document = parse_document(machine())
    assert document.edges[0].label == "call fails\n/ count it"
    assert document.edges[0].source == document.edges[0].target == "closed"


def test_a_label_of_several_lines_is_drawn_as_one_run_per_line() -> None:
    scene = graph_scene(parse_document(machine()), THEME, MEASURER)
    runs = [item for item in scene.primitives if isinstance(item, TextRun)]
    words = [run.text for run in runs]
    assert "call fails" in words
    assert "/ count it" in words
    first = next(run for run in runs if run.text == "call fails")
    second = next(run for run in runs if run.text == "/ count it")
    assert first.x == second.x
    assert second.y > first.y


# ---------------------------------------------------------------------------
# Pseudo-states
# ---------------------------------------------------------------------------


def test_the_initial_dot_has_no_text_and_its_arrow_ends_on_the_initial_state() -> None:
    drawing = drawn(machine())
    (start,) = marker(drawing, "initial")
    route = next(route for route in drawing.routes if route.source == start)
    assert route.target == "closed"
    assert on_border(route.points[-1], drawing.boxes["closed"])
    assert not drawing.boxes[start].block.lines
    scene = graph_scene(parse_document(machine()), THEME, MEASURER)
    dots = [item for item in scene.primitives if isinstance(item, Ellipse) and item.fill]
    assert len(dots) == 1
    assert dots[0].rx == pytest.approx(THEME.states.dot / 2)
    box = drawing.boxes[start]
    assert dots[0].cx == pytest.approx(box.x + box.width / 2)


def test_the_initial_dot_sits_above_its_state_an_ordinary_gap_away() -> None:
    """Pulled in from its rank: a dot's arrow carries no label to make room for."""
    drawing = drawn(machine())
    (start,) = marker(drawing, "initial")
    dot, state = drawing.boxes[start], drawing.boxes["closed"]
    assert dot.y + dot.height < state.y
    assert dot.x + dot.width / 2 == pytest.approx(state.x + state.width / 2)
    gap = state.y - (dot.y + dot.height)
    assert gap < 60


def test_each_final_state_leads_to_its_own_ringed_dot() -> None:
    document = machine(final=["half"])
    document["transitions"] = [t for t in document["transitions"] if t["from"] != "half"]
    document["transitions"].append({"from": "open", "to": "closed", "event": "reset"})
    drawing = drawn(document)
    (end,) = marker(drawing, "final")
    route = next(route for route in drawing.routes if route.target == end)
    assert route.source == "half"
    assert drawing.boxes[end].y > drawing.boxes["half"].y
    scene = graph_scene(parse_document(document), THEME, MEASURER)
    rings = [item for item in scene.primitives if isinstance(item, Ellipse) and not item.fill]
    assert len(rings) == 1
    assert rings[0].rx == pytest.approx(THEME.states.final / 2)


def test_a_group_with_an_initial_gets_its_own_dot_inside_its_frame() -> None:
    drawing = drawn(_ticket())
    starts = marker(drawing, "initial")
    assert len(starts) == 2
    frame = next(frame for frame in drawing.frames if frame.id == "worked")
    inner = [
        drawing.boxes[name]
        for name in starts
        if frame.x <= drawing.boxes[name].x <= frame.right
        and frame.y <= drawing.boxes[name].y <= frame.bottom
    ]
    assert len(inner) == 1


def test_the_dots_are_sized_by_the_theme() -> None:
    theme = load_theme({"version": 1, "states": {"dot": 14.0, "ring": 4.0}})
    drawing = graph_drawing(parse_document(machine(final=[])), theme, MEASURER)
    (start,) = marker(drawing, "initial")
    assert drawing.boxes[start].width == pytest.approx(14.0)
    assert theme.states.final == pytest.approx(22.0)


def test_the_theme_refuses_an_unknown_states_key() -> None:
    with pytest.raises(ThemeError, match=r"\[states\]"):
        load_theme({"version": 1, "states": {"shape": "pill"}})


# ---------------------------------------------------------------------------
# Self-loops
# ---------------------------------------------------------------------------


def _loop_of(drawing: GraphDrawing, state: str) -> Any:
    return next(loop for loop in drawing.loops if loop.route.source == state)


def test_a_self_loop_leaves_and_returns_on_the_same_side_without_crossing_its_box() -> None:
    drawing = drawn(machine())
    loop = _loop_of(drawing, "closed")
    box = drawing.boxes["closed"]
    first, last = loop.route.points[0], loop.route.points[-1]
    assert on_border(first, box) and on_border(last, box)
    if loop.side in ("left", "right"):
        edge = box.x + box.width if loop.side == "right" else box.x
        assert first[0] == pytest.approx(edge) and last[0] == pytest.approx(edge)
        far = loop.route.points[1][0]
        assert abs(far - edge) == pytest.approx(loop_reach(THEME))
    for start, end in pairwise(loop.route.points):
        middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        inside = (
            box.x + EPSILON < middle[0] < box.x + box.width - EPSILON
            and box.y + EPSILON < middle[1] < box.y + box.height - EPSILON
        )
        assert not inside


def test_a_self_loop_goes_across_the_reading_direction() -> None:
    """Never on the top or bottom of a box in a downward drawing — that is where
    its own incoming and outgoing edges arrive, and the loop used to re-enter
    across its incoming arrow."""
    drawing = drawn(machine())
    assert drawing.layout.direction == "down"
    assert _loop_of(drawing, "closed").side in LOOP_SIDES["down"]


def test_a_self_loop_avoids_the_side_a_return_edge_uses() -> None:
    """`half → closed` goes round the right of `closed`; the loop takes the left."""
    drawing = drawn(machine())
    back = next(route for route in drawing.routes if route.source == "half")
    box = drawing.boxes["closed"]
    arrives_right = back.points[-1][0] == pytest.approx(box.x + box.width)
    loop = _loop_of(drawing, "closed")
    assert loop.side == ("left" if arrives_right else "right")


def test_a_self_loop_label_is_outside_the_loop_and_clear_of_every_line() -> None:
    drawing = drawn(machine())
    loop = _loop_of(drawing, "closed")
    assert loop.label is not None
    left, top, right, bottom = loop.label.box
    far = loop.route.points[1][0]
    assert right <= far or left >= far
    box = drawing.boxes["closed"]
    assert right <= box.x or left >= box.x + box.width
    for route in drawing.routes:
        for (x1, y1), (x2, y2) in pairwise(route.points):
            crosses = (
                min(x1, x2) < right - EPSILON
                and max(x1, x2) > left + EPSILON
                and min(y1, y2) < bottom - EPSILON
                and max(y1, y2) > top + EPSILON
            )
            assert not crosses, route


def test_a_loop_is_part_of_its_box_extent_so_neighbours_keep_clear() -> None:
    """Two states side by side, one looping: the neighbour is outside the loop."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "states",
        "initial": "a",
        "states": [
            {"id": "a", "text": "Idle"},
            {"id": "b", "text": "Polling"},
            {"id": "c", "text": "Pushing"},
        ],
        "transitions": [
            {"from": "a", "to": "b", "event": "timer"},
            {"from": "a", "to": "c", "event": "event"},
            {"from": "b", "to": "b", "event": "no news", "action": "wait a second"},
            {"from": "c", "to": "c", "event": "more to send"},
        ],
    }
    drawing = drawn(document)
    for loop in drawing.loops:
        left, top, right, bottom = loop.zone
        for name, box in drawing.boxes.items():
            if name == loop.route.source:
                continue
            apart = (
                box.x + box.width <= left
                or box.x >= right
                or box.y + box.height <= top
                or box.y >= bottom
            )
            assert apart, name


def test_two_self_loops_on_one_state_take_both_sides() -> None:
    document = machine()
    document["transitions"].append({"from": "closed", "to": "closed", "event": "probe"})
    drawing = drawn(document)
    sides = {loop.side for loop in drawing.loops if loop.route.source == "closed"}
    assert sides == set(LOOP_SIDES["down"])


def test_a_drawing_that_reads_across_puts_its_loops_below_or_above() -> None:
    document = machine(width=900, height=160, height_binding=True)
    drawing = drawn(document)
    assert drawing.layout.direction == "right"
    assert _loop_of(drawing, "closed").side in LOOP_SIDES["right"]


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def _ticket() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (REFERENCE / "states-ticket.json").read_text(encoding="utf-8")
    )
    return document


def test_a_transition_naming_a_group_starts_on_the_frame_not_a_member() -> None:
    drawing = drawn(_ticket())
    frame = next(frame for frame in drawing.frames if frame.id == "worked")
    route = next(
        route for route in drawing.routes if route.source == "worked" and route.target == "resolved"
    )
    assert on_border(route.points[0], frame)
    for member in ("investigating", "waiting"):
        assert not on_border(route.points[0], drawing.boxes[member])


def test_a_frame_edge_does_not_share_a_line_with_a_member_edge_leaving_it() -> None:
    """The invoice's `issued → paid` and `overdue → written_off` both leave the
    bottom of the frame; drawn from one point they read as one edge."""
    document = json.loads((REFERENCE / "states-invoice.json").read_text(encoding="utf-8"))
    drawing = drawn(document)
    group = next(route for route in drawing.routes if route.source == "issued")
    member = next(
        route
        for route in drawing.routes
        if route.source == "overdue" and route.target == "written_off"
    )
    assert abs(group.points[0][0] - member.points[0][0]) >= THEME.edge.lane_spacing - EPSILON


def test_a_return_edge_into_a_group_from_below_is_routed() -> None:
    """It used to find no route: the frame's border is outside every lane."""
    drawing = drawn(_ticket())
    route = next(
        route for route in drawing.routes if route.target == "worked" and route.source == "resolved"
    )
    frame = next(frame for frame in drawing.frames if frame.id == "worked")
    assert on_border(route.points[-1], frame)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_an_unreachable_state_is_refused_at_its_pointer() -> None:
    document = machine()
    document["states"].append({"id": "lost", "text": "Lost"})
    assert pointers(document) == ["/states/3"]
    assert "add the transition" in messages(document).lower()


def test_reachability_runs_through_a_group() -> None:
    """Entering a group enters its `initial`; a transition from a group leaves
    every state inside it — so both of those reach something."""
    assert validate_document(_ticket()) == ()
    document = _ticket()
    document["groups"][0]["initial"] = "waiting"
    document["transitions"] = [
        t for t in document["transitions"] if t.get("event") != "a question is sent"
    ]
    assert pointers(document) == []
    document["transitions"] = [
        t for t in document["transitions"] if t.get("event") != "the customer replies"
    ]
    assert pointers(document) == ["/states/1"]


def test_a_final_state_with_an_outgoing_transition_is_refused_at_its_from() -> None:
    document = machine(final=["open"])
    assert pointers(document) == ["/transitions/2/from"]


def test_final_may_not_name_a_group() -> None:
    document = _ticket()
    document["final"] = ["worked"]
    assert "/final/0" in pointers(document)


def test_a_non_deterministic_pair_is_refused_at_the_second() -> None:
    document = machine()
    document["transitions"].append({"from": "closed", "to": "half", "event": "threshold reached"})
    assert pointers(document) == ["/transitions/4/to"]
    assert "guards" in messages(document)


def test_the_same_event_with_different_guards_is_deterministic() -> None:
    assert validate_document(json.loads((REFERENCE / "states-breaker.json").read_text())) == ()


def test_an_id_that_resolves_to_nothing_is_refused() -> None:
    assert pointers(machine(initial="nowhere")) == ["/initial"]
    document = machine()
    document["transitions"][1]["to"] = "nowhere"
    assert "/transitions/1/to" in pointers(document)


def test_entering_a_group_with_no_initial_is_refused() -> None:
    document = _ticket()
    del document["groups"][0]["initial"]
    assert "/transitions/0/to" in pointers(document)
    assert "'initial'" in messages(document)


def test_a_group_initial_must_be_its_own_member() -> None:
    document = _ticket()
    document["groups"][0]["initial"] = "resolved"
    assert "/groups/0/initial" in pointers(document)


def test_a_group_may_not_share_an_id_with_a_state() -> None:
    document = _ticket()
    document["groups"][0]["id"] = "open"
    assert "/groups/0/id" in pointers(document)


def test_a_self_loop_on_a_group_is_refused() -> None:
    document = _ticket()
    document["transitions"].append({"from": "worked", "to": "worked", "event": "escalated"})
    assert pointers(document) == [f"/transitions/{len(document['transitions']) - 1}/to"]


def test_a_third_self_loop_on_one_state_is_refused() -> None:
    document = machine()
    document["transitions"] += [
        {"from": "closed", "to": "closed", "event": "probe"},
        {"from": "closed", "to": "closed", "event": "poke"},
    ]
    assert pointers(document) == ["/transitions/5/to"]


@pytest.mark.parametrize(
    ("where", "field", "value"),
    [
        ("states", "actor", "an operator"),
        ("states", "centre", True),
        ("states", "note", "an aside"),
        ("transitions", "label", "free text"),
    ],
)
def test_fields_a_state_machine_has_no_use_for_are_refused(
    where: str, field: str, value: object
) -> None:
    document = machine()
    document[where][0][field] = value
    assert pointers(document) == [f"/{where}/0/{field}"]


@pytest.mark.parametrize("role", ["decision", "start", "note", "group"])
def test_a_state_may_not_take_a_role_that_promises_something_else(role: str) -> None:
    document = machine()
    document["states"][1]["role"] = role
    assert pointers(document) == ["/states/1/role"]


@pytest.mark.parametrize("role", ["link", "owns", "exchange", "aside"])
def test_a_transition_may_only_take_a_transition_role(role: str) -> None:
    document = machine()
    document["transitions"][1]["role"] = role
    assert pointers(document) == ["/transitions/1/role"]


def test_bands_are_not_a_states_field() -> None:
    assert pointers(machine(bands=[])) == ["/bands"]


def test_initial_is_required() -> None:
    document = machine()
    del document["initial"]
    assert pointers(document) == ["/initial"]


def test_the_budget_refuses_a_fifteenth_state() -> None:
    limit = dict(READABILITY_BUDGET["states"])["states"]
    document: dict[str, Any] = {
        "version": 1,
        "kind": "states",
        "initial": "s0",
        "states": [{"id": f"s{index}", "text": f"State {index}"} for index in range(limit + 1)],
        "transitions": [
            {"from": f"s{index}", "to": f"s{index + 1}", "event": "next"} for index in range(limit)
        ],
    }
    assert pointers(document) == [f"/states/{limit}"]


def test_parse_raises_with_every_violation() -> None:
    document = machine(initial="nowhere")
    document["states"][0]["role"] = "decision"
    with pytest.raises(DocumentError) as raised:
        parse_document(document)
    assert len(raised.value.violations) == 2


# ---------------------------------------------------------------------------
# The whole render
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["states-process", "states-breaker", "states-invoice", "states-ticket"]
)
def test_every_reference_machine_renders_with_its_labels_as_text(name: str) -> None:
    document = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    svg = render(document)
    assert svg.startswith("<svg")
    scene = graph_scene(parse_document(document), THEME, MEASURER)
    words = " ".join(
        run.text if isinstance(run, TextRun) else "".join(span.text for span in run.spans)
        for run in scene.primitives
        if isinstance(run, TextRun | TextLine)
    )
    for transition in document.get("transitions", ()):
        if transition.get("event"):
            assert transition["event"].replace("`", "") in words.replace("`", "")


# ---------------------------------------------------------------------------
# Orthogonal regions
# ---------------------------------------------------------------------------


def player(**extra: Any) -> dict[str, Any]:
    """A player whose `on` composite runs playback and sound at once."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "states",
        "initial": "stopped",
        "states": [
            {"id": "stopped", "text": "Stopped"},
            {"id": "playing", "text": "Playing"},
            {"id": "paused", "text": "Paused"},
            {"id": "loud", "text": "Sound on"},
            {"id": "muted", "text": "Muted"},
        ],
        "groups": [
            {
                "id": "on",
                "text": "Powered",
                "regions": [
                    {"members": ["playing", "paused"], "initial": "playing"},
                    {"members": ["loud", "muted"], "initial": "loud"},
                ],
            }
        ],
        "transitions": [
            {"from": "stopped", "to": "on", "event": "play"},
            {"from": "playing", "to": "paused", "event": "pause"},
            {"from": "paused", "to": "playing", "event": "resume"},
            {"from": "loud", "to": "muted", "event": "mute"},
            {"from": "muted", "to": "loud", "event": "unmute"},
            {"from": "on", "to": "stopped", "event": "stop"},
        ],
    }
    document.update(extra)
    return document


def test_regions_validate_and_every_region_is_entered() -> None:
    # Muted is reached only through its region's own initial, never named by an arrow
    # from outside: entering the composite enters every region.
    assert not validate_document(player())


def test_each_region_is_drawn_side_by_side_and_divided_by_a_dashed_line() -> None:
    drawing = drawn(player())
    regions = [frame for frame in drawing.frames if frame.region_of == "on"]
    assert len(regions) == 2
    first, second = sorted(regions, key=lambda frame: frame.x)
    boxes = drawing.boxes
    assert (
        first.x <= boxes["playing"].x and boxes["playing"].x + boxes["playing"].width <= first.right
    )
    assert second.x <= boxes["loud"].x and boxes["loud"].x + boxes["loud"].width <= second.right
    # Each region has its own initial dot, inside it.
    dots = [identifier for identifier in marker(drawing, "initial") if identifier != "(initial)"]
    assert len(dots) == 2
    scene = graph_scene(parse_document(player()), THEME, MEASURER)
    dividers = [
        primitive
        for primitive in scene.primitives
        if isinstance(primitive, ScenePath) and primitive.role == "group"
    ]
    assert len(dividers) == 1
    (x1, _), (x2, _) = dividers[0].points
    assert x1 == x2 and first.right <= x1 <= second.x


def test_a_region_draws_no_frame_of_its_own() -> None:
    scene = graph_scene(parse_document(player()), THEME, MEASURER)
    from drawspec.scene import Rect

    frames = [p for p in scene.primitives if isinstance(p, Rect) and p.role == "group"]
    assert len(frames) == 1


def test_no_arrow_lands_on_a_divider() -> None:
    drawing = drawn(player())
    regions = sorted(
        (frame for frame in drawing.frames if frame.region_of == "on"), key=lambda f: f.x
    )
    divider = (regions[0].right + regions[1].x) / 2
    for route in drawing.routes:
        if "on" in (route.source, route.target):
            end = route.points[-1] if route.target == "on" else route.points[0]
            assert abs(end[0] - divider) > THEME.edge.lane_spacing


def test_a_labelled_transition_into_a_composite_nested_in_a_region_is_drawn() -> None:
    # Reserving a region's label room once looked the composite's box up, and a
    # composite has a frame, not a box: the drawing failed with a KeyError.
    document = player()
    document["states"] += [{"id": "ahead", "text": "Ahead"}, {"id": "back", "text": "Back"}]
    document["groups"].append(
        {"id": "seek", "text": "Seeking", "members": ["ahead", "back"], "initial": "ahead"}
    )
    document["groups"][0]["regions"][0]["members"].append("seek")
    document["transitions"] += [
        {"from": "paused", "to": "seek", "event": "seek"},
        {"from": "ahead", "to": "back", "event": "rewind"},
    ]
    assert not validate_document(document)
    drawing = drawn(document)
    assert any(frame.id == "seek" for frame in drawing.frames)


def test_a_transition_between_regions_is_refused() -> None:
    document = player()
    document["transitions"].append({"from": "paused", "to": "muted", "event": "quiet"})
    assert "/transitions/6/to" in pointers(document)
    assert "different regions of 'on'" in messages(document)


def test_a_state_in_two_regions_is_refused() -> None:
    document = player()
    document["groups"][0]["regions"][1]["members"].append("paused")
    assert "/groups/0/regions/1/members/2" in pointers(document)
    assert "another region of 'on'" in messages(document)


def test_a_region_must_name_its_initial() -> None:
    document = player()
    del document["groups"][0]["regions"][1]["initial"]
    assert "/groups/0/regions/1/initial" in pointers(document)


def test_a_region_initial_must_be_one_of_its_own_states() -> None:
    document = player()
    document["groups"][0]["regions"][1]["initial"] = "playing"
    assert "/groups/0/regions/1/initial" in pointers(document)


def test_members_and_regions_together_are_refused() -> None:
    document = player()
    document["groups"][0]["members"] = ["playing"]
    assert "/groups/0/members" in pointers(document)


def test_a_composite_with_regions_takes_no_initial_of_its_own() -> None:
    document = player()
    document["groups"][0]["initial"] = "playing"
    assert "/groups/0/initial" in pointers(document)


def test_a_composite_with_neither_members_nor_regions_is_refused() -> None:
    document = machine(groups=[{"id": "g", "text": "G"}])
    assert "/groups/0" in pointers(document)


def test_one_region_is_not_regions() -> None:
    document = player()
    document["groups"][0]["regions"] = document["groups"][0]["regions"][:1]
    assert "/groups/0/regions" in pointers(document)


def test_the_budget_refuses_a_fifth_region() -> None:
    limit = dict(READABILITY_BUDGET["states"])["groups/regions"]
    states = [{"id": f"s{n}", "text": f"S{n}"} for n in range(limit + 1)]
    document = player(
        states=[{"id": "stopped", "text": "Stopped"}, *states],
        groups=[
            {
                "id": "on",
                "text": "On",
                "regions": [{"members": [s["id"]], "initial": s["id"]} for s in states],
            }
        ],
        transitions=[{"from": "stopped", "to": "on", "event": "go"}],
    )
    assert f"/groups/0/regions/{limit}" in pointers(document)


def test_entering_one_region_directly_still_enters_the_others() -> None:
    document = player()
    document["transitions"][0] = {"from": "stopped", "to": "paused", "event": "resume later"}
    # playing is still reached, through its region's initial
    assert not validate_document(document)
