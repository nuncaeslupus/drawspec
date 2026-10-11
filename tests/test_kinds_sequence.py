"""`sequence` — who says what to whom, in order.

A sequence diagram's claims are all placement: an arrow that lands exactly on
the lifeline it is sent to (or on the edge of the bar standing on it), a reply
told from a call by dash and head rather than colour, an activation bar exactly
as tall as the call and its reply, and frames round the messages they name. Each
is asserted here by geometry; each refusal by the pointer it is reported at.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError, ThemeError
from drawspec.kinds.sequence import SequenceDrawing, activations, sequence_drawing
from drawspec.scene import Path as Stroke
from drawspec.scene import TextLine
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
EPSILON = 1e-6


def exchange(**extra: Any) -> dict[str, Any]:
    """A client calling a service that calls a store, and the answers coming back."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "sequence",
        "participants": [
            {"id": "client", "text": "Client"},
            {"id": "service", "text": "Service"},
            {"id": "store", "text": "Store"},
        ],
        "messages": [
            {"id": "ask", "from": "client", "to": "service", "text": "get the order"},
            {"id": "read", "from": "service", "to": "store", "text": "read row 42"},
            {"id": "row", "from": "store", "to": "service", "text": "the row", "role": "weak"},
            {
                "id": "answer",
                "from": "service",
                "to": "client",
                "text": "the order",
                "role": "weak",
            },
        ],
    }
    document.update(extra)
    return document


def drawn(document: Mapping[str, Any], theme: Theme = THEME) -> SequenceDrawing:
    return sequence_drawing(parse_document(document), theme, MEASURER)


def pointers(document: Mapping[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: Mapping[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


# ---------------------------------------------------------------------------
# Reference documents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(REFERENCE.glob("sequence-*.json")), ids=lambda p: p.stem)
def test_every_reference_renders(path: Path) -> None:
    """Each reference renders, and none of them reaches the readability budget."""
    document = json.loads(path.read_text(encoding="utf-8"))
    assert render(document).startswith("<svg")
    for name, limit in READABILITY_BUDGET["sequence"]:
        assert len(document[name]) <= limit


def test_there_are_at_least_three_references() -> None:
    assert len(list(REFERENCE.glob("sequence-*.json"))) >= 3


# ---------------------------------------------------------------------------
# Columns and arrows
# ---------------------------------------------------------------------------


def test_participants_are_drawn_left_to_right_in_the_order_written() -> None:
    lifelines = drawn(exchange()).lifelines
    assert lifelines["client"] < lifelines["service"] < lifelines["store"]


def test_every_arrow_ends_on_its_lifeline_or_on_the_bar_standing_there() -> None:
    """The head is at the end, and the end is the target's lifeline — or, where an
    activation bar stands on that lifeline at that row, the bar's near edge."""
    document = parse_document(exchange())
    drawing = sequence_drawing(document, THEME, MEASURER)
    bars = {(bar.participant, bar.start, bar.end): box for bar, box in drawing.bars}
    names = [participant.id for participant in document.participants]
    for row, (message, route) in enumerate(zip(document.messages, drawing.arrows, strict=True)):
        target = names.index(message.target)
        x = route[-1][0]
        standing = [
            box for (who, start, end), box in bars.items() if who == target and start <= row <= end
        ]
        edges = {drawing.lifelines[message.target]}
        edges |= {box[0] for box in standing} | {box[2] for box in standing}
        assert any(abs(x - edge) < EPSILON for edge in edges), (row, x, edges)
        # Horizontal, and pointing at the target.
        assert route[0][1] == route[-1][1]
        towards = drawing.lifelines[message.target] - drawing.lifelines[message.source]
        assert (route[-1][0] - route[0][0]) * towards > 0


def test_an_arrow_with_no_bar_ends_exactly_on_the_lifeline() -> None:
    document = exchange(
        messages=[
            {"from": "client", "to": "service", "text": "a signal"},
            {"from": "service", "to": "store", "text": "another"},
        ]
    )
    drawing = drawn(document)
    assert drawing.bars == ()
    assert drawing.arrows[0][-1][0] == pytest.approx(drawing.lifelines["service"])
    assert drawing.arrows[1][-1][0] == pytest.approx(drawing.lifelines["store"])


def test_every_label_fits_between_the_ends_of_its_arrow() -> None:
    drawing = drawn(exchange())
    for route, box in zip(drawing.arrows, drawing.labels, strict=True):
        assert box is not None
        low, high = sorted((route[0][0], route[-1][0]))
        assert low < box[0] and box[2] < high
        assert box[3] < route[0][1]


def test_a_reply_is_told_from_a_call_by_dash_and_head_not_colour() -> None:
    """Greyscale: the two roles differ in dash pattern and head shape."""
    call, reply = THEME.edge_roles["flow"], THEME.edge_roles["weak"]
    assert call.dash != reply.dash
    assert call.head != reply.head
    scene = drawn(exchange()).scene
    roles = {primitive.role for primitive in scene.primitives if isinstance(primitive, Stroke)}
    assert {"flow", "weak"} <= roles


def test_a_message_to_itself_is_a_hook_on_the_right_of_its_lifeline() -> None:
    document = exchange(
        messages=[
            {"from": "client", "to": "service", "text": "go"},
            {"from": "service", "to": "service", "text": "think it over"},
            {"from": "service", "to": "store", "text": "write"},
        ]
    )
    drawing = drawn(document)
    hook = drawing.arrows[1]
    x = drawing.lifelines["service"]
    assert len(hook) == 4
    assert hook[0][0] == pytest.approx(x) and hook[-1][0] == pytest.approx(x)
    assert hook[1][0] > x and hook[2][0] > x
    assert hook[-1][1] > hook[0][1]
    label = drawing.labels[1]
    assert label is not None and label[0] > hook[1][0]
    assert label[2] < drawing.lifelines["store"]


# ---------------------------------------------------------------------------
# Activation bars
# ---------------------------------------------------------------------------


def test_a_call_answered_later_gets_a_bar_from_the_call_to_the_reply() -> None:
    drawing = drawn(exchange())
    found = {(bar.participant, bar.start, bar.end): box for bar, box in drawing.bars}
    assert set(found) == {(1, 0, 3), (2, 1, 2)}
    top, bottom = found[(1, 0, 3)][1], found[(1, 0, 3)][3]
    assert top < drawing.arrows[0][0][1] < bottom
    assert top < drawing.arrows[3][0][1] < bottom
    assert drawing.arrows[0][0][1] - top == pytest.approx(bottom - drawing.arrows[3][0][1])


def test_nested_calls_nest_their_bars() -> None:
    """A call into a participant that is already busy stacks a bar on its own."""
    document = exchange(
        messages=[
            {"from": "client", "to": "service", "text": "start"},
            {"from": "store", "to": "service", "text": "callback"},
            {"from": "service", "to": "store", "text": "ok", "role": "weak"},
            {"from": "service", "to": "client", "text": "done", "role": "weak"},
        ]
    )
    drawing = drawn(document)
    (outer, outer_box), (inner, inner_box) = sorted(drawing.bars, key=lambda pair: pair[0].depth)
    assert (outer.depth, inner.depth) == (0, 1)
    assert outer_box[1] < inner_box[1] and inner_box[3] < outer_box[3]
    assert inner_box[0] > outer_box[0] and inner_box[2] > outer_box[2]


def test_an_unanswered_call_has_no_bar() -> None:
    document = exchange(
        messages=[
            {"from": "client", "to": "service", "text": "fire and forget"},
            {"from": "service", "to": "store", "text": "write it"},
        ]
    )
    assert activations(parse_document(document)) == ()


def test_a_reply_in_one_branch_of_an_alt_does_not_end_the_call() -> None:
    """Both branches answer the call made before the frame, so the bar runs to the last."""
    document = exchange(
        messages=[
            {"from": "client", "to": "service", "text": "pay"},
            {"id": "no", "from": "service", "to": "client", "text": "declined", "role": "weak"},
            {"id": "yes", "from": "service", "to": "client", "text": "paid", "role": "weak"},
            {"from": "service", "to": "store", "text": "log it"},
        ],
        fragments=[
            {"operator": "alt", "from": "no", "to": "yes", "else": [{"at": "yes", "text": "ok"}]}
        ],
    )
    bars = activations(parse_document(document))
    assert [(bar.participant, bar.start, bar.end) for bar in bars] == [(1, 0, 2)]


def test_lifelines_break_where_a_bar_stands() -> None:
    drawing = drawn(exchange())
    x = drawing.lifelines["service"]
    (_, box) = next(pair for pair in drawing.bars if pair[0].participant == 1)
    for primitive in drawing.scene.primitives:
        if isinstance(primitive, Stroke) and primitive.role == THEME.sequence.lifeline:
            (x0, y0), (_, y1) = primitive.points
            if abs(x0 - x) < EPSILON:
                assert y1 <= box[1] + EPSILON or y0 >= box[3] - EPSILON


# ---------------------------------------------------------------------------
# Fragments, groups and notes
# ---------------------------------------------------------------------------


def test_a_fragment_frames_its_messages_and_every_participant_they_touch() -> None:
    document = exchange(
        fragments=[{"operator": "loop", "from": "read", "to": "row", "text": "each row"}]
    )
    drawing = drawn(document)
    (left, top, right, bottom) = drawing.frames[0]
    assert left < drawing.lifelines["service"] and drawing.lifelines["store"] < right
    assert drawing.lifelines["client"] < left
    for row in (1, 2):
        assert top < drawing.arrows[row][0][1] < bottom
    for row in (0, 3):
        assert not top < drawing.arrows[row][0][1] < bottom
    words = [p.text for p in drawing.scene.primitives if isinstance(p, TextLine)]
    assert "loop" in words and "[each row]" in words


def test_nested_fragments_nest_their_frames() -> None:
    document = exchange(
        fragments=[
            {"operator": "opt", "from": "ask", "to": "answer", "text": "cache cold"},
            {"operator": "loop", "from": "read", "to": "row"},
        ]
    )
    outer, inner = drawn(document).frames
    assert outer[0] < inner[0] and outer[1] < inner[1]
    assert inner[2] < outer[2] and inner[3] < outer[3]


def test_an_else_divider_sits_above_its_message_inside_the_frame() -> None:
    document = exchange(
        fragments=[
            {
                "operator": "alt",
                "from": "read",
                "to": "answer",
                "text": "found",
                "else": [{"at": "answer", "text": "missing"}],
            }
        ]
    )
    drawing = drawn(document)
    left, _, right, _ = drawing.frames[0]
    dividers = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, Stroke) and p.role == "aside" and p.points[0][1] == p.points[-1][1]
    ]
    assert len(dividers) == 1
    y = dividers[0].points[0][1]
    assert drawing.arrows[2][0][1] < y < drawing.arrows[3][0][1]
    assert dividers[0].points[0][0] == pytest.approx(left)
    assert dividers[0].points[-1][0] == pytest.approx(right)


def test_a_group_frames_its_lifelines_and_their_heads() -> None:
    document = exchange(groups=[{"id": "ours", "text": "Ours", "members": ["service", "store"]}])
    drawing = drawn(document)
    left, top, right, bottom = drawing.groups[0]
    assert left < drawing.lifelines["service"] < drawing.lifelines["store"] < right
    assert drawing.lifelines["client"] < left
    assert top == 0.0
    assert bottom >= max(route[0][1] for route in drawing.arrows)


def test_notes_share_one_column_right_of_every_lifeline() -> None:
    document = exchange()
    document["messages"][0]["note"] = "cold start"
    document["messages"][2]["note"] = "cached for a minute"
    drawing = drawn(document)
    assert drawing.notes is not None
    assert drawing.notes > max(drawing.lifelines.values())
    notes = [p for p in drawing.scene.primitives if isinstance(p, TextLine) and p.role == "note"]
    assert {p.x for p in notes} == {drawing.notes}
    assert {p.text for p in notes} == {"cold start", "cached for a minute"}


def test_the_lifeline_role_comes_from_the_theme() -> None:
    theme = load_theme({"version": 1, "sequence": {"lifeline": "weak"}})
    roles = {
        p.role
        for p in drawn(exchange(), theme).scene.primitives
        if isinstance(p, Stroke) and len(p.points) == 2 and p.points[0][0] == p.points[1][0]
    }
    assert "weak" in roles


def test_a_lifeline_role_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(ThemeError, match="lifeline"):
        load_theme({"version": 1, "sequence": {"lifeline": "dotted"}})


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_message_naming_an_unknown_participant_is_refused_at_its_end() -> None:
    document = exchange()
    document["messages"][3]["to"] = "nobody"
    assert "/messages/3/to" in pointers(document)
    assert "'nobody' is not the id of any participant" in messages(document)


def test_a_participant_nobody_talks_to_is_refused() -> None:
    document = exchange()
    document["participants"].append({"id": "idle", "text": "Idle"})
    assert pointers(document) == ["/participants/3"]
    assert "no message is sent to or from 'idle'" in messages(document)


def test_a_fragment_ending_before_it_starts_is_refused() -> None:
    document = exchange(fragments=[{"operator": "loop", "from": "row", "to": "read"}])
    assert pointers(document) == ["/fragments/0/to"]
    assert "end before it starts" in messages(document)


def test_a_fragment_naming_an_unknown_message_is_refused() -> None:
    document = exchange(fragments=[{"operator": "opt", "from": "read", "to": "nope"}])
    assert pointers(document) == ["/fragments/0/to"]


def test_two_fragments_that_partly_overlap_are_refused_at_the_second() -> None:
    document = exchange(
        fragments=[
            {"operator": "loop", "from": "ask", "to": "row"},
            {"operator": "opt", "from": "read", "to": "answer"},
        ]
    )
    assert pointers(document) == ["/fragments/1"]
    assert "Fragments nest or are apart" in messages(document)


def test_else_on_a_loop_or_an_opt_is_refused() -> None:
    for operator in ("loop", "opt"):
        document = exchange(
            fragments=[
                {
                    "operator": operator,
                    "from": "read",
                    "to": "answer",
                    "else": [{"at": "row", "text": "x"}],
                }
            ]
        )
        assert pointers(document) == ["/fragments/0/else"]
        assert "has one branch" in messages(document)


@pytest.mark.parametrize("at", ["ask", "read"])
def test_an_else_outside_its_fragment_or_at_its_top_is_refused(at: str) -> None:
    document = exchange(
        fragments=[
            {"operator": "alt", "from": "read", "to": "row", "else": [{"at": at, "text": "x"}]}
        ]
    )
    assert pointers(document) == ["/fragments/0/else/0/at"]


def test_an_else_inside_a_nested_fragment_is_refused() -> None:
    document = exchange(
        fragments=[
            {"operator": "alt", "from": "ask", "to": "answer", "else": [{"at": "row"}]},
            {"operator": "loop", "from": "read", "to": "row"},
        ]
    )
    assert pointers(document) == ["/fragments/0/else/0/at"]
    assert "cut through that frame" in messages(document)


def test_a_group_whose_members_are_not_neighbours_is_refused() -> None:
    document = exchange(groups=[{"id": "ends", "text": "Ends", "members": ["client", "store"]}])
    assert pointers(document) == ["/groups/0/members"]
    assert "'service' stands between members" in messages(document)
    assert "Reorder 'participants'" in messages(document)


def test_a_participant_in_two_groups_is_refused() -> None:
    document = exchange(
        groups=[
            {"id": "a", "members": ["client", "service"]},
            {"id": "b", "members": ["service", "store"]},
        ]
    )
    assert pointers(document) == ["/groups/1/members/0"]


@pytest.mark.parametrize("field", ["activation", "lifeline", "start", "end"])
def test_a_field_that_would_size_an_activation_is_refused(field: str) -> None:
    document = exchange()
    document["messages"][0][field] = 2
    assert pointers(document) == [f"/messages/0/{field}"]


@pytest.mark.parametrize("role", ["aside", "link", "exchange", "owns"])
def test_a_message_role_with_no_single_direction_is_refused(role: str) -> None:
    document = exchange()
    document["messages"][0]["role"] = role
    assert pointers(document) == ["/messages/0/role"]


@pytest.mark.parametrize("role", ["decision", "start", "terminal", "group"])
def test_a_participant_role_promising_another_shape_is_refused(role: str) -> None:
    document = exchange()
    document["participants"][0]["role"] = role
    assert pointers(document) == ["/participants/0/role"]


def test_more_than_the_budget_is_refused() -> None:
    document = exchange()
    document["participants"] = [{"id": f"p{index}", "text": f"P{index}"} for index in range(9)]
    document["messages"] = [
        {"from": f"p{index}", "to": f"p{index + 1}", "text": "hi"} for index in range(8)
    ] * 4
    found = pointers(document)
    assert "/participants/8" in found and "/messages/30" in found


def test_eight_participants_with_long_names_do_not_fit() -> None:
    names = [f"The {word} service that owns the customer ledger" for word in "abcdefgh"]
    document = {
        "version": 1,
        "kind": "sequence",
        "participants": [{"id": f"p{i}", "text": name} for i, name in enumerate(names)],
        "messages": [{"from": f"p{i}", "to": f"p{i + 1}", "text": "hand over"} for i in range(7)],
    }
    with pytest.raises(FitError, match="lifelines"):
        render(document)


def test_a_document_is_parsed_into_the_sequence_model() -> None:
    document = parse_document(
        exchange(
            fragments=[
                {"operator": "par", "from": "read", "to": "answer", "else": [{"at": "answer"}]}
            ]
        )
    )
    assert document.family == "sequence"
    assert [participant.id for participant in document.participants] == [
        "client",
        "service",
        "store",
    ]
    assert document.messages[2].role == "weak"
    assert document.fragments[0].branches[0].text == ""


def test_an_invalid_document_raises() -> None:
    with pytest.raises(DocumentError):
        parse_document(exchange(participants=[{"id": "only", "text": "Only"}]))


# ---------------------------------------------------------------------------
# Async messages and actors
# ---------------------------------------------------------------------------


def test_an_async_message_is_solid_with_an_open_head_and_opens_no_bar() -> None:
    document = exchange()
    document["messages"].insert(
        0, {"from": "client", "to": "store", "text": "warm the cache", "role": "async"}
    )
    assert not validate_document(document)
    role = THEME.edge_roles["async"]
    assert role.head == "open" and role.dash == "none"
    bars = activations(parse_document(document))
    assert all(bar.start != 0 for bar in bars)
    drawing = drawn(document)
    store = drawing.lifelines["store"]
    assert abs(drawing.arrows[0][-1][0] - store) < EPSILON


def test_a_reply_to_an_async_message_is_refused() -> None:
    document = exchange()
    document["messages"] = [
        {"from": "client", "to": "service", "text": "ping", "role": "async"},
        {"from": "service", "to": "client", "text": "pong", "role": "weak"},
    ]
    document["participants"] = document["participants"][:2]
    assert "/messages/1/role" in pointers(document)
    assert "awaits no reply" in messages(document)


def test_a_reply_to_a_call_after_an_async_message_is_fine() -> None:
    document = exchange()
    document["messages"].insert(
        0, {"from": "client", "to": "service", "text": "heads up", "role": "async"}
    )
    assert not validate_document(document)


def test_an_actor_is_a_stick_figure_over_its_name_with_the_lifeline_under_it() -> None:
    from drawspec.scene import Ellipse

    document = exchange()
    document["participants"][0]["role"] = "actor"
    drawing = drawn(document)
    x = drawing.lifelines["client"]
    heads = [p for p in drawing.scene.primitives if isinstance(p, Ellipse)]
    assert len(heads) == 1 and abs(heads[0].cx - x) < EPSILON
    name = next(
        p
        for p in drawing.scene.primitives
        if isinstance(p, TextLine) and "".join(s.text for s in p.spans) == "Client"
    )
    service = next(
        p
        for p in drawing.scene.primitives
        if isinstance(p, TextLine) and "".join(s.text for s in p.spans) == "Service"
    )
    # Names stand on one line; the figure rises above the name.
    assert abs(name.y - service.y) < EPSILON
    assert heads[0].cy < name.y
    lifeline = next(
        p
        for p in drawing.scene.primitives
        if isinstance(p, Stroke)
        and p.role == THEME.sequence.lifeline
        and abs(p.points[0][0] - x) < EPSILON
    )
    assert lifeline.points[0][1] > name.y


@pytest.mark.parametrize("role", ["person", "user"])
def test_a_person_role_on_a_participant_points_at_actor(role: str) -> None:
    document = exchange()
    document["participants"][0]["role"] = role
    assert "/participants/0/role" in pointers(document)
    assert "'actor'" in messages(document)


def test_a_message_role_from_another_notation_is_named() -> None:
    document = exchange()
    document["messages"][0]["role"] = "asynchronous"
    assert "'async'" in messages(document)
