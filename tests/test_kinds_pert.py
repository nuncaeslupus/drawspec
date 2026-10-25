"""`pert` — a project network, activity on node, its schedule computed.

The kind's promises: every time in a box — early and late start and finish, and
float — is computed by a forward and a backward pass, never written; the numbers
are the textbooks' (the Milwaukee Paper exercise's critical path is A-C-E-G-H in
15 weeks); the critical path is drawn heavy, boxes and the arrows that leave no
gap; a loop is refused with its path; and everything an author might write in
place of a computed number is refused at its pointer, with the reason.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from drawspec import render, render_text
from drawspec.errors import FitError, ThemeError
from drawspec.kinds.pert import (
    CRITICAL_EDGE_ROLE,
    CRITICAL_ROLE,
    DEPENDENCY_ROLE,
    FINISH_ID,
    START_ID,
    PertDrawing,
    figure,
    pert_drawing,
    schedule,
)
from drawspec.schema import (
    PERT_ACTIVITY_MAX,
    PERT_DEPENDENCY_MAX,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("pert-*.json"))


def network(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "pert",
        "unit": "days",
        "activities": [
            {"id": "A", "text": "Design", "duration": 3},
            {"id": "B", "text": "Build", "duration": 5, "after": ["A"]},
            {"id": "C", "text": "Write docs", "duration": 2, "after": ["A"]},
            {"id": "D", "text": "Release", "duration": 1, "after": ["B", "C"]},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> PertDrawing:
    return pert_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def reference(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    return data


# -- the references -----------------------------------------------------------


def test_there_are_references() -> None:
    assert len(REFERENCES) >= 2


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_and_validates(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_boxes_overlap(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    boxes = list(drawing.nodes.values())
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            apart = (
                first.x + first.width <= second.x
                or second.x + second.width <= first.x
                or first.y + first.height <= second.y
                or second.y + second.height <= first.y
            )
            assert apart, (first.id, second.id)


# -- the schedule ---------------------------------------------------------------


def test_the_textbook_exercise_has_the_textbooks_schedule() -> None:
    """Milwaukee Paper: A-C-E-G-H critical, 15 weeks; B and D 1 week of slack, F 6."""
    plan = schedule(parse_document(reference("pert-textbook")).pert_activities)
    assert plan.end == 15
    expected = {
        #     ES  EF  LS  LF
        "A": (0, 2, 0, 2),
        "B": (0, 3, 1, 4),
        "C": (2, 4, 2, 4),
        "D": (3, 7, 4, 8),
        "E": (4, 8, 4, 8),
        "F": (4, 7, 10, 13),
        "G": (8, 13, 8, 13),
        "H": (13, 15, 13, 15),
    }
    for identifier, (es, ef, ls, lf) in expected.items():
        times = plan.times[identifier]
        assert (times.early_start, times.early_finish) == (es, ef), identifier
        assert (times.late_start, times.late_finish) == (ls, lf), identifier
    floats = {identifier: plan.times[identifier].float for identifier in expected}
    assert floats == {"A": 0, "B": 1, "C": 0, "D": 1, "E": 0, "F": 6, "G": 0, "H": 0}
    critical = [identifier for identifier in plan.order if plan.times[identifier].critical]
    assert critical == ["A", "C", "E", "G", "H"]


def test_the_house_runs_through_the_plumbing() -> None:
    plan = schedule(parse_document(reference("pert-house")).pert_activities)
    assert plan.end == 45
    critical = {identifier for identifier, times in plan.times.items() if times.critical}
    assert critical == {
        "permits",
        "excavate",
        "foundation",
        "frame",
        "plumbing",
        "insulate",
        "drywall",
        "interior",
        "handover",
    }
    assert plan.times["wiring"].float == 1
    assert plan.times["roof"].float == 6


def test_three_point_estimates_give_the_expected_duration_exactly() -> None:
    document = parse_document(reference("pert-release"))
    durations = {activity.id: activity.duration for activity in document.pert_activities}
    assert durations["spec"] == Fraction(2 + 4 * 3 + 6, 6)
    assert durations["api"] == Fraction(17, 2)
    assert durations["launch"] == Fraction(7, 6)
    plan = schedule(document.pert_activities)
    assert plan.end == 22  # 10/3 + 17/2 + 4 + 5 + 7/6, exactly
    assert [i for i in plan.order if plan.times[i].critical] == [
        "spec",
        "api",
        "tests",
        "beta",
        "launch",
    ]


def test_decimals_are_exact_so_a_float_of_zero_is_zero() -> None:
    """0.1 + 0.2 is 0.3 here: a float of 3e-17 would drop an activity off the path."""
    plan = schedule(
        parse_document(
            network(
                activities=[
                    {"id": "a", "text": "a", "duration": 0.1},
                    {"id": "b", "text": "b", "duration": 0.2, "after": ["a"]},
                    {"id": "c", "text": "c", "duration": 0.3},
                    {"id": "d", "text": "d", "duration": 1, "after": ["b", "c"]},
                ]
            )
        ).pert_activities
    )
    assert all(times.critical for times in plan.times.values())


def test_a_time_is_written_whole_or_to_two_places() -> None:
    assert figure(Fraction(15)) == "15"
    assert figure(Fraction(10, 3)) == "3.33"
    assert figure(Fraction(17, 2)) == "8.5"
    assert figure(Fraction(0)) == "0"


def test_each_box_writes_its_computed_times_in_the_textbook_cells() -> None:
    drawing = drawn(network())
    build, docs = drawing.nodes["B"], drawing.nodes["C"]
    assert build.top == ("3", "5", "8") and build.bottom == ("3", "0", "8")
    assert docs.top == ("3", "2", "5") and docs.bottom == ("6", "3", "8")


# -- the critical path, drawn -------------------------------------------------


def test_the_critical_path_is_heavy_and_nothing_else_is() -> None:
    drawing = drawn(network())
    roles = {identifier: node.role for identifier, node in drawing.nodes.items()}
    assert roles == {"A": CRITICAL_ROLE, "B": CRITICAL_ROLE, "C": "step", "D": CRITICAL_ROLE}
    lines = {(route.source, route.target): route.role for route in drawing.routes}
    assert lines == {
        ("A", "B"): CRITICAL_EDGE_ROLE,
        ("A", "C"): DEPENDENCY_ROLE,
        ("B", "D"): CRITICAL_EDGE_ROLE,
        ("C", "D"): DEPENDENCY_ROLE,
    }


def test_an_arrow_between_two_critical_activities_with_a_gap_is_not_critical() -> None:
    """Both ends critical is not enough: the later must start as the earlier ends."""
    document = network(
        activities=[
            {"id": "A", "text": "A", "duration": 2},
            {"id": "B", "text": "B", "duration": 5},
            {"id": "C", "text": "C", "duration": 1, "after": ["A", "B"]},
        ]
    )
    drawing = drawn(document)
    assert drawing.nodes["A"].role == "step"
    lines = {(route.source, route.target): route.role for route in drawing.routes}
    assert lines[("B", "C")] == CRITICAL_EDGE_ROLE
    assert lines[("A", "C")] == DEPENDENCY_ROLE


def test_milestones_join_the_ends_and_carry_the_times() -> None:
    drawing = drawn(network(start="Start", finish="Finish"))
    assert drawing.nodes[START_ID].milestone == "0"
    assert drawing.nodes[FINISH_ID].milestone == "9"
    pairs = {(route.source, route.target): route.role for route in drawing.routes}
    assert pairs[(START_ID, "A")] == CRITICAL_EDGE_ROLE
    assert pairs[("D", FINISH_ID)] == CRITICAL_EDGE_ROLE


def test_the_network_reads_across_when_it_fits() -> None:
    drawing = drawn(network())
    assert drawing.direction == "right"
    assert drawing.nodes["A"].x < drawing.nodes["B"].x < drawing.nodes["D"].x


def test_the_key_names_the_cells_and_the_theme_can_turn_it_off() -> None:
    drawing = drawn(network())
    assert drawing.key is not None
    assert drawing.key.top == ("ES", "Dur", "EF")
    assert drawing.key.bottom == ("LS", "Float", "LF")
    said = " ".join(span.text for note in drawing.notes for span in note.spans)
    assert "9 days" in said
    plain = drawn(network(), load_theme({"version": 1, "pert": {"key": False}}))
    assert plain.key is None
    assert [span.text for note in plain.notes for span in note.spans] == ["Durations in days"]


def test_the_key_must_be_a_boolean() -> None:
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "pert": {"key": "yes"}})


def test_a_name_wider_than_the_canvas_allows_is_refused_by_fit() -> None:
    document = network(width=200)
    document["activities"][0]["text"] = "Supercalifragilisticexpialidocious" * 2
    with pytest.raises(FitError):
        render(document)


# -- text -------------------------------------------------------------------


def test_the_text_form_carries_every_time() -> None:
    text = render_text(parse_document(network()), width=80, charset="unicode")
    assert "ES=3 D=5 EF=8" in text
    assert "LS=6 F=3 LF=8" in text
    assert "9 days" in text


def test_a_text_refusal_points_at_the_activity() -> None:
    document = network()
    document["activities"][1]["text"] = "Build-everything-in-one-unbroken-word-of-text"
    with pytest.raises(FitError) as error:
        render_text(parse_document(document), width=30, charset="ascii")
    assert str(error.value).startswith("/activities/")


# -- refusals -----------------------------------------------------------------


def test_a_loop_is_refused_with_its_path() -> None:
    document = network()
    document["activities"][0]["after"] = ["D"]
    found = validate_document(document)
    assert len(found) == 1
    assert found[0].pointer.startswith("/activities/")
    assert "/after/" in found[0].pointer
    assert "go round in a circle" in found[0].message
    assert "A -> B -> D -> A" in found[0].message


@pytest.mark.parametrize(
    "field", ["es", "ef", "ls", "lf", "float", "slack", "critical", "start", "end"]
)
def test_a_computed_time_is_refused(field: str) -> None:
    document = network()
    document["activities"][1][field] = 3
    assert pointers(document) == [f"/activities/1/{field}"]
    assert "computed" in messages(document)


@pytest.mark.parametrize(
    ("field", "words"),
    [
        ("role", "critical path"),
        ("lag", "finish-to-start"),
        ("type", "finish-to-start"),
        ("predecessors", "`after`"),
        ("before", "`after`"),
    ],
)
def test_a_field_an_author_reaches_for_is_refused_with_the_reason(field: str, words: str) -> None:
    document = network()
    document["activities"][1][field] = "x"
    assert pointers(document) == [f"/activities/1/{field}"]
    assert words in messages(document)


def test_edges_are_refused_for_after() -> None:
    document = network(edges=[{"from": "A", "to": "B"}])
    assert pointers(document) == ["/edges"]
    assert "`after`" in messages(document)


def test_an_after_must_name_another_activity_once() -> None:
    document = network()
    document["activities"][1]["after"] = ["Z", "B", "A", "A"]
    assert pointers(document) == [
        "/activities/1/after/0",
        "/activities/1/after/1",
        "/activities/1/after/3",
    ]


def test_ids_are_unique() -> None:
    document = network()
    document["activities"][2]["id"] = "B"
    assert "/activities/2/id" in pointers(document)


def test_a_duration_is_one_thing() -> None:
    both = network()
    both["activities"][0].update(optimistic=1, likely=2, pessimistic=3)
    assert pointers(both) == ["/activities/0/optimistic"]
    neither = network()
    del neither["activities"][0]["duration"]
    assert pointers(neither) == ["/activities/0"]
    partial = network()
    del partial["activities"][0]["duration"]
    partial["activities"][0].update(optimistic=1, likely=2)
    assert pointers(partial) == ["/activities/0/pessimistic"]


def test_estimates_run_in_order_and_durations_are_not_negative() -> None:
    disordered = network()
    del disordered["activities"][0]["duration"]
    disordered["activities"][0].update(optimistic=3, likely=2, pessimistic=5)
    assert pointers(disordered) == ["/activities/0/likely"]
    negative = network()
    negative["activities"][0]["duration"] = -1
    assert pointers(negative) == ["/activities/0/duration"]


def test_one_activity_is_not_a_network() -> None:
    document = network(activities=[{"id": "A", "text": "A", "duration": 1}])
    assert pointers(document) == ["/activities"]
    assert "at least 2" in messages(document)


def test_the_budget() -> None:
    many = network(
        activities=[
            {"id": f"a{index}", "text": f"Step {index}", "duration": 1}
            for index in range(PERT_ACTIVITY_MAX + 1)
        ]
    )
    assert pointers(many) == [f"/activities/{PERT_ACTIVITY_MAX}"]
    dense: list[dict[str, Any]] = [
        {"id": f"a{index}", "text": f"Step {index}", "duration": 1} for index in range(12)
    ]
    for index in range(6, 12):
        dense[index]["after"] = [f"a{other}" for other in range(6)]
    assert PERT_DEPENDENCY_MAX < 6 * 6
    refused = messages(network(activities=dense))
    assert "dependencies" in refused


def test_empty_words_are_refused() -> None:
    document = network(start=" ")
    document["activities"][0]["text"] = " "
    assert pointers(document) == ["/start", "/activities/0/text"]
