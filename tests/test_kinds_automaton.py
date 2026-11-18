"""`automaton` — a finite automaton as the theory textbooks draw it.

The kind's promises: states are circles, an accepting one a double circle; the
start state is entered by one arrow from nowhere, never a dot; moves between the
same two states merge into one arrow labelled `a, b`; a pair of opposite moves is
two arcs bowed apart; a move to the same state is a loop on its circle; ε labels an
empty move; a Mealy machine says `a / 1` on its arrows and a Moore machine `q0 / 1`
in its circles. No arc runs through a circle it does not belong to, no stroke
touches a label, no two labels meet. The text form is the transition table. And
everything an author can get wrong is refused at its pointer, with the reason.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

from drawspec import render, render_text
from drawspec.errors import FitError
from drawspec.examples import EXAMPLES
from drawspec.kinds.automaton import (
    EPSILON,
    AutomatonDrawing,
    automaton_drawing,
    automaton_scene,
    merged,
    nondeterministic,
)
from drawspec.scene import Ellipse
from drawspec.schema import (
    AUTOMATON_NAME_MAX,
    AUTOMATON_STATE_MAX,
    AUTOMATON_TRANSITION_MAX,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import itertools

from clipping import clipped
from collisions import collisions

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("automaton-*.json"))


def machine(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "automaton",
        "start": "q0",
        "accepting": ["q1"],
        "states": [{"id": "q0"}, {"id": "q1"}],
        "transitions": [
            {"from": "q0", "to": "q1", "on": "a"},
            {"from": "q1", "to": "q0", "on": "b"},
        ],
    }
    document.update(extra)
    return document


def reference(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    return data


def drawn(document: dict[str, Any]) -> AutomatonDrawing:
    return automaton_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def _segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    span = dx * dx + dy * dy
    if span == 0:
        return math.dist(point, start)
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / span))
    return math.dist(point, (start[0] + t * dx, start[1] + t * dy))


def _distance(point: tuple[float, float], points: tuple[tuple[float, float], ...]) -> float:
    return min(_segment_distance(point, a, b) for a, b in itertools.pairwise(points))


def _meets(
    start: tuple[float, float], end: tuple[float, float], box: tuple[float, float, float, float]
) -> bool:
    """Whether a segment meets a box, sampled finely enough for a test."""
    left, top, right, bottom = box
    for step in range(41):
        x = start[0] + (end[0] - start[0]) * step / 40
        y = start[1] + (end[1] - start[1]) * step / 40
        if left <= x <= right and top <= y <= bottom:
            return True
    return False


# -- the references -----------------------------------------------------------


def test_there_are_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_validates_and_is_clean(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    svg = render(document, profile="standalone")
    assert svg.startswith("<svg")
    assert collisions(svg) == []
    assert clipped(svg) == []


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_arc_runs_through_a_circle_it_does_not_belong_to(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for arc in drawing.arcs:
        for circle in drawing.circles.values():
            if circle.id in (arc.source, arc.target):
                continue
            assert _distance(circle.centre, arc.points) >= circle.r + THEME.edge.clearance - 0.01
    for circle in drawing.circles.values():
        if not circle.start:
            assert _distance(circle.centre, drawing.start) >= circle.r


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_arc_leaves_and_reaches_its_own_circles(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for arc in drawing.arcs:
        source, target = drawing.circles[arc.source], drawing.circles[arc.target]
        assert math.dist(arc.points[0], source.centre) == pytest.approx(source.r, abs=0.05)
        assert math.dist(arc.points[-1], target.centre) == pytest.approx(target.r, abs=0.05)
        inside = [
            point
            for point in arc.points[1:-1]
            if math.dist(point, source.centre) < source.r - 0.05
            or math.dist(point, target.centre) < target.r - 0.05
        ]
        assert not inside, (arc.source, arc.target)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_label_touches_a_stroke_a_circle_or_another_label(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    strokes = [arc.points for arc in drawing.arcs] + [drawing.start, *drawing.heads]
    for index, label in enumerate(drawing.labels):
        box = label.box
        for stroke in strokes:
            for a, b in itertools.pairwise(stroke):
                assert not _meets(a, b, box), (label.text, a, b)
        for circle in drawing.circles.values():
            nearest = (
                min(max(circle.cx, box[0]), box[2]),
                min(max(circle.cy, box[1]), box[3]),
            )
            assert math.dist(nearest, circle.centre) > circle.r, (label.text, circle.id)
        for other in drawing.labels[index + 1 :]:
            o = other.box
            assert o[2] <= box[0] or box[2] <= o[0] or o[3] <= box[1] or box[3] <= o[1]


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_circles_overlap(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    circles = list(drawing.circles.values())
    for index, first in enumerate(circles):
        for second in circles[index + 1 :]:
            assert math.dist(first.centre, second.centre) > first.r + second.r


# -- what is drawn ---------------------------------------------------------------


def test_the_divisible_by_three_machine_is_the_textbooks() -> None:
    """Wikipedia's example: S0 start and accepting, 0 and 1 doubling the remainder."""
    document = parse_document(reference("automaton-divisible-by-three"))
    assert merged(document.automaton_transitions) == [
        ("S0", "S0", "0"),
        ("S0", "S1", "1"),
        ("S1", "S2", "0"),
        ("S1", "S0", "1"),
        ("S2", "S1", "0"),
        ("S2", "S2", "1"),
    ]
    # Read 1001 (nine): S0 -1-> S1 -0-> S2 -0-> S1 -1-> S0, accepted.
    moves = {(move.source, move.symbol): move.target for move in document.automaton_transitions}
    state = document.automaton_start
    for bit in "1001":
        state = moves[(state, bit)]
    assert state in document.automaton_accepting


def test_an_accepting_state_is_a_double_circle_and_the_others_single() -> None:
    document = parse_document(reference("automaton-divisible-by-three"))
    scene = automaton_scene(document, THEME, MEASURER)
    rings = [primitive for primitive in scene.primitives if isinstance(primitive, Ellipse)]
    drawing = automaton_drawing(document, THEME, MEASURER)
    for circle in drawing.circles.values():
        here = [ring for ring in rings if (ring.cx, ring.cy) == (circle.cx, circle.cy)]
        assert len(here) == (2 if circle.accepting else 1), circle.id
    assert all(ring.fill in ("", "none") for ring in rings), "no filled initial dot"


def test_the_start_arrow_comes_from_nowhere_into_the_start_state() -> None:
    drawing = drawn(reference("automaton-divisible-by-three"))
    start = drawing.circles["S0"]
    tail, tip = drawing.start
    assert math.dist(tip, start.centre) == pytest.approx(start.r, abs=0.05)
    assert all(math.dist(tail, circle.centre) > circle.r for circle in drawing.circles.values())
    # Read across the page, it comes in from the left.
    assert tail[0] < tip[0]


def test_moves_between_the_same_states_merge_into_one_arrow() -> None:
    drawing = drawn(reference("automaton-ends-in-ab"))
    loops = [arc for arc in drawing.arcs if arc.loop]
    assert [(arc.source, arc.label) for arc in loops] == [("q0", "a, b")]
    assert len(drawing.arcs) == 3


def test_a_pair_of_opposite_moves_is_two_arcs_bowed_apart() -> None:
    drawing = drawn(reference("automaton-divisible-by-three"))
    there = next(arc for arc in drawing.arcs if (arc.source, arc.target) == ("S0", "S1"))
    back = next(arc for arc in drawing.arcs if (arc.source, arc.target) == ("S1", "S0"))
    assert there.paired and back.paired
    assert there.bow > 0 and back.bow > 0, "each bowed to the left of the way it goes"
    # Bowed left of travel, the pair sits on opposite sides of the line between them.
    middle_there = there.points[len(there.points) // 2]
    middle_back = back.points[len(back.points) // 2]
    assert middle_there[1] < drawing.circles["S0"].cy < middle_back[1]
    assert min(_distance(point, back.points) for point in there.points) > 4


def test_a_move_to_itself_is_a_loop_on_its_circle() -> None:
    drawing = drawn(reference("automaton-epsilon-nfa"))
    for arc in drawing.arcs:
        if not arc.loop:
            continue
        circle = drawing.circles[arc.source]
        assert math.dist(arc.points[0], circle.centre) == pytest.approx(circle.r, abs=0.05)
        assert math.dist(arc.points[-1], circle.centre) == pytest.approx(circle.r, abs=0.05)
        assert max(math.dist(point, circle.centre) for point in arc.points) > 1.5 * circle.r


def test_an_empty_move_is_labelled_epsilon() -> None:
    drawing = drawn(reference("automaton-epsilon-nfa"))
    labels = {(arc.source, arc.target): arc.label for arc in drawing.arcs}
    assert labels[("q0", "q1")] == EPSILON
    assert labels[("q1", "q2")] == EPSILON
    assert "ε" in render(reference("automaton-epsilon-nfa"))


def test_a_mealy_machine_says_its_outputs_on_its_arrows() -> None:
    drawing = drawn(reference("automaton-edge-detector"))
    labels = {(arc.source, arc.target): arc.label for arc in drawing.arcs}
    assert labels[("zero", "one")] == "1 / 1"
    assert labels[("one", "one")] == "1 / 0"


def test_a_moore_machine_says_its_outputs_in_its_circles() -> None:
    drawing = drawn(reference("automaton-moore-parity"))
    assert {circle.name for circle in drawing.circles.values()} == {"even / 0", "odd / 1"}


def test_every_circle_is_the_size_of_the_widest_name() -> None:
    drawing = drawn(reference("automaton-edge-detector"))
    assert len({circle.r for circle in drawing.circles.values()}) == 1


def test_the_machine_reads_across_the_page() -> None:
    assert drawn(reference("automaton-epsilon-nfa")).direction == "right"


def test_the_example_renders() -> None:
    assert validate_document(EXAMPLES["automaton"]) == ()
    assert render(EXAMPLES["automaton"]).startswith("<svg")


def test_a_twelve_state_machine_renders_clean() -> None:
    """A counter modulo 12 with a reset: the budget's worth of states."""
    states = [{"id": f"c{index}"} for index in range(AUTOMATON_STATE_MAX)]
    moves = [
        {"from": f"c{index}", "to": f"c{(index + 1) % AUTOMATON_STATE_MAX}", "on": "+"}
        for index in range(AUTOMATON_STATE_MAX)
    ] + [{"from": f"c{index}", "to": "c0", "on": "r"} for index in range(1, 4)]
    document = machine(states=states, transitions=moves, start="c0", accepting=["c0"])
    assert validate_document(document) == ()
    svg = render(document, profile="standalone")
    assert collisions(svg) == []
    assert clipped(svg) == []


# -- the text form ----------------------------------------------------------------


def test_the_text_form_is_the_transition_table() -> None:
    text = render_text(parse_document(reference("automaton-divisible-by-three")))
    lines = text.splitlines()
    assert lines[0].split() == ["│", "0", "1"]
    assert lines[2].split() == ["→*", "S0", "│", "S0", "S1"]
    assert lines[3].split() == ["S1", "│", "S2", "S0"]
    assert "→ start state, * accepting." in text


def test_an_nfa_table_holds_sets_and_an_epsilon_column() -> None:
    document = parse_document(reference("automaton-epsilon-nfa"))
    assert nondeterministic(document)
    text = render_text(document)
    assert text.splitlines()[0].split()[-1] == "ε"
    assert "{q1}" in text and "∅" in text
    ascii_text = render_text(document, charset="ascii")
    assert "eps" in ascii_text and "{}" in ascii_text and "->" in ascii_text
    assert ascii_text.isascii()


def test_a_deterministic_table_holds_states_and_a_dash_for_no_move() -> None:
    document = machine(transitions=[{"from": "q0", "to": "q1", "on": "a"}])
    text = render_text(parse_document(document))
    assert "—" in text and "{" not in text


def test_a_moore_table_ends_in_an_output_column() -> None:
    text = render_text(parse_document(reference("automaton-moore-parity")))
    assert text.splitlines()[0].split()[-1] == "output"


def test_a_mealy_table_says_the_output_in_each_cell() -> None:
    text = render_text(parse_document(reference("automaton-edge-detector")))
    assert "last 1 / 1" in text


def test_the_text_form_defaults_to_a_hundred_columns_and_refuses_past_its_width() -> None:
    symbols = [f"symbol{index}" for index in range(9)]
    document = machine(transitions=[{"from": "q0", "to": "q1", "on": symbol} for symbol in symbols])
    with pytest.raises(FitError, match="--width"):
        render_text(parse_document(document), width=60)
    assert max(len(line) for line in render_text(parse_document(document)).splitlines()) <= 100


# -- refusals ----------------------------------------------------------------------


def test_the_start_must_name_a_state() -> None:
    document = machine(start="q9")
    assert pointers(document) == ["/start"]
    assert "names no state" in messages(document)


def test_the_start_is_required() -> None:
    document = machine()
    del document["start"]
    assert pointers(document) == ["/start"]


def test_a_misspelt_id_is_named_with_a_suggestion() -> None:
    document = machine(
        states=[{"id": "even"}, {"id": "odd"}],
        start="even",
        accepting=["evn"],
        transitions=[{"from": "even", "to": "od", "on": "1"}],
    )
    assert pointers(document) == ["/accepting/0", "/transitions/0/to"]
    assert "Did you mean 'even'?" in messages(document)
    assert "Did you mean 'odd'?" in messages(document)


def test_ids_are_unique_and_accepting_lists_each_once() -> None:
    document = machine(states=[{"id": "q0"}, {"id": "q0"}, {"id": "q1"}], accepting=["q1", "q1"])
    assert pointers(document) == ["/states/1/id", "/accepting/1"]


def test_a_move_reads_a_symbol_or_is_an_empty_move() -> None:
    assert pointers(machine(transitions=[{"from": "q0", "to": "q1"}])) == ["/transitions/0"]
    both = machine(transitions=[{"from": "q0", "to": "q1", "on": "a", "epsilon": True}])
    assert pointers(both) == ["/transitions/0/epsilon"]


@pytest.mark.parametrize(
    "spelling", ["ε", "λ", "eps", "epsilon", "", "Epsilon", "EPS", "Lambda", "Λ", "ϵ", " ε "]
)
def test_epsilon_is_never_written_as_a_symbol(spelling: str) -> None:
    document = machine(transitions=[{"from": "q0", "to": "q1", "on": spelling}])
    assert pointers(document) == ["/transitions/0/on"]
    assert "epsilon: true" in messages(document)


def test_a_move_is_written_once() -> None:
    move = {"from": "q0", "to": "q1", "on": "a"}
    assert pointers(machine(transitions=[move, dict(move)])) == ["/transitions/1/on"]


def test_a_deterministic_machine_refuses_two_moves_on_one_symbol() -> None:
    document = machine(
        deterministic=True,
        transitions=[
            {"from": "q0", "to": "q1", "on": "a"},
            {"from": "q0", "to": "q0", "on": "a"},
        ],
    )
    assert pointers(document) == ["/transitions/1/on"]
    assert "transition 0" in messages(document)


def test_a_deterministic_machine_refuses_an_empty_move() -> None:
    document = machine(
        deterministic=True, transitions=[{"from": "q0", "to": "q1", "epsilon": True}]
    )
    assert pointers(document) == ["/transitions/0/epsilon"]
    assert "NFA" in messages(document)


def test_an_nfa_may_do_both() -> None:
    document = machine(
        transitions=[
            {"from": "q0", "to": "q1", "on": "a"},
            {"from": "q0", "to": "q0", "on": "a"},
            {"from": "q0", "to": "q1", "epsilon": True},
        ]
    )
    assert validate_document(document) == ()


def test_a_mealy_machine_writes_an_output_on_every_move() -> None:
    document = machine(
        transitions=[
            {"from": "q0", "to": "q1", "on": "a", "output": "1"},
            {"from": "q1", "to": "q0", "on": "b"},
        ]
    )
    assert pointers(document) == ["/transitions/1"]


def test_a_moore_machine_writes_an_output_in_every_state() -> None:
    document = machine(states=[{"id": "q0", "output": "0"}, {"id": "q1"}])
    assert pointers(document) == ["/states/1"]


def test_a_machine_is_mealy_or_moore_not_both() -> None:
    document = machine(
        states=[{"id": "q0", "output": "0"}, {"id": "q1", "output": "1"}],
        transitions=[
            {"from": "q0", "to": "q1", "on": "a", "output": "1"},
            {"from": "q1", "to": "q0", "on": "b", "output": "0"},
        ],
    )
    assert pointers(document) == ["/states/0/output"]


def test_a_name_is_one_short_line() -> None:
    long = "x" * (AUTOMATON_NAME_MAX + 1)
    assert pointers(machine(states=[{"id": "q0", "text": long}, {"id": "q1"}])) == [
        "/states/0/text"
    ]
    assert pointers(machine(states=[{"id": "q0", "text": "a\nb"}, {"id": "q1"}])) == [
        "/states/0/text"
    ]
    assert "`states` diagram" in messages(machine(states=[{"id": long}, {"id": "q1"}], start=long))


@pytest.mark.parametrize(
    ("field", "words"),
    [
        ("initial", "`start`"),
        ("final", "`accepting`"),
        ("alphabet", "read from the transitions"),
        ("edges", "`transitions`"),
    ],
)
def test_a_top_level_field_an_author_reaches_for_is_refused_with_the_reason(
    field: str, words: str
) -> None:
    document = machine(**{field: []})
    assert pointers(document) == [f"/{field}"]
    assert words in messages(document)


@pytest.mark.parametrize(
    ("field", "words"),
    [("event", "`on`"), ("symbol", "`on`"), ("label", "merged"), ("guard", "`on`")],
)
def test_a_transition_field_an_author_reaches_for_is_refused_with_the_reason(
    field: str, words: str
) -> None:
    document = machine(transitions=[{"from": "q0", "to": "q1", "on": "a", field: "x"}])
    assert pointers(document) == [f"/transitions/0/{field}"]
    assert words in messages(document)


def test_a_state_role_is_refused() -> None:
    document = machine(states=[{"id": "q0", "role": "emphasis"}, {"id": "q1"}])
    assert pointers(document) == ["/states/0/role"]
    assert "`accepting`" in messages(document)


def test_the_budget() -> None:
    states = [{"id": f"q{index}"} for index in range(AUTOMATON_STATE_MAX + 1)]
    assert f"/states/{AUTOMATON_STATE_MAX}" in pointers(machine(states=states))
    moves = [
        {"from": "q0", "to": "q1", "on": f"s{index}"}
        for index in range(AUTOMATON_TRANSITION_MAX + 1)
    ]
    assert f"/transitions/{AUTOMATON_TRANSITION_MAX}" in pointers(machine(transitions=moves))
