"""`status` on `flow` and `tree`: one drawing of a change, with the change marked.

A design document proposing a change used to draw two diagrams, before and
after, and leave the reader to diff them by eye. `files` already marked a change
on one listing — `+ added`, `~ changed`, `- removed`, a labelled mark and never a
colour — and this is that vocabulary on boxes and edges. The assertions below
are about what a reader without colour still sees: a word in a pill, a dashed
line, a struck-through name.
"""

from __future__ import annotations

import json

import pytest

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.kinds.common import DRAWN_MARKS, REMOVED_ROLE, STATUS_ROLE
from drawspec.kinds.graph import graph_drawing, graph_scene
from drawspec.scene import Path, Rect, Scene, TextLine, TextRun
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

CHANGE: dict[str, object] = {
    "version": 1,
    "kind": "flow",
    "title": "Sessions move to their own service",
    "nodes": [
        {"id": "web", "text": "Web front end"},
        {"id": "mono", "text": "Monolith", "status": "changed"},
        {"id": "sess", "text": "Session service", "status": "added"},
        {"id": "table", "text": "Sessions table", "status": "removed"},
    ],
    "edges": [
        {"from": "web", "to": "mono"},
        {"from": "web", "to": "sess", "status": "added"},
        {"from": "mono", "to": "table", "label": "reads", "status": "removed"},
    ],
}


def change(**changes: object) -> dict[str, object]:
    document = json.loads(json.dumps(CHANGE))
    document.update(changes)
    return document  # type: ignore[no-any-return]


def scene(document: dict[str, object]) -> Scene:
    return graph_scene(parse_document(document), THEME, MEASURER)


def lines(built: Scene) -> list[TextLine]:
    return [item for item in built.primitives if isinstance(item, TextLine)]


def tags(built: Scene) -> list[TextRun]:
    """The tags' words: furniture, set as runs at the label level like an edge label."""
    return [item for item in built.primitives if isinstance(item, TextRun)]


def pointers(document: dict[str, object]) -> dict[str, str]:
    return {violation.pointer: violation.message for violation in validate_document(document)}


# --------------------------------------------------------------------------
# What is drawn
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["added", "changed", "removed"])
def test_a_marked_box_carries_its_mark_and_word_in_a_pill(status: str) -> None:
    """A mark and the word, never a colour: the pill says `+ added`."""
    built = scene(change())
    words = f"{DRAWN_MARKS[status]} {status}"
    found = [line for line in tags(built) if line.text == words]
    assert found, f"no {words!r} drawn"
    assert all(line.level == "label" for line in found)
    pills = [
        item for item in built.primitives if isinstance(item, Rect) and item.role == STATUS_ROLE
    ]
    assert any(
        pill.x < tag.x < pill.x + pill.width and pill.y < tag.y < pill.y + pill.height + 1
        for pill in pills
        for tag in found
    )


def test_the_tag_sits_inside_its_own_box() -> None:
    drawing = graph_drawing(parse_document(change()), THEME, MEASURER)
    built = scene(change())
    box = drawing.boxes["sess"]
    (tag,) = [
        line
        for line in tags(built)
        if line.text == "+ added" and box.y < line.y < box.y + box.height
    ]
    assert box.x < tag.x < box.x + box.width


def test_a_removed_box_is_dashed_and_struck_through() -> None:
    built = scene(change())
    (name,) = [line for line in lines(built) if line.text == "Sessions table"]
    assert name.strike
    assert not any(line.strike for line in lines(built) if line.text != "Sessions table")
    outlines = [
        item for item in built.primitives if isinstance(item, Path) and item.role == REMOVED_ROLE
    ]
    assert len(outlines) == 1
    assert THEME.edge_roles[REMOVED_ROLE].dash != "none"
    assert outlines[0].points[0] == outlines[0].points[-1]


def test_a_struck_line_is_emitted_as_a_text_decoration() -> None:
    """A property of the words, so it is never a stroke crossing them."""
    svg = render(change())
    assert 'text-decoration="line-through"' in svg
    assert check_embedding_safety(svg, THEME) == ()


def test_a_removed_edge_is_dashed_with_no_head_whatever_its_role() -> None:
    drawing = graph_drawing(parse_document(change()), THEME, MEASURER)
    (gone,) = [route for route in drawing.routes if route.target == "table"]
    assert gone.role == "aside"
    assert THEME.edge_roles["aside"].dash != "none"
    assert not THEME.edge_roles["aside"].has_head


def test_an_edge_label_leads_with_its_mark() -> None:
    drawing = graph_drawing(parse_document(change()), THEME, MEASURER)
    labels = {route.target: route.label for route in drawing.routes}
    assert labels["table"] == "\u2212 reads"
    assert labels["sess"] == "+"
    assert labels["mono"] == ""


def test_a_marked_box_without_a_lead_does_not_grow_one() -> None:
    """The tag is sized as a second paragraph; it must not make the first a bold lead."""
    built = scene(change())
    (name,) = [line for line in lines(built) if line.text == "Monolith"]
    assert all(span.weight == "normal" for span in name.spans)


def test_a_marked_box_with_an_actor_keeps_its_lead() -> None:
    document = change()
    document["nodes"][1]["actor"] = "The platform team"  # type: ignore[index]
    built = scene(document)
    (actor,) = [line for line in lines(built) if line.text == "The platform team"]
    assert all(span.weight == "bold" for span in actor.spans)


def test_the_key_lists_exactly_the_statuses_used() -> None:
    document = change(
        nodes=[
            {"id": "a", "text": "Old"},
            {"id": "b", "text": "New", "status": "added"},
        ],
        edges=[{"from": "a", "to": "b", "status": "added"}],
    )
    built = scene(document)
    marks = [
        line.text for line in tags(built) if line.text in {"+ added", "~ changed", "\u2212 removed"}
    ]
    # One on the box, one in the key — and nothing for the statuses not used.
    assert marks == ["+ added", "+ added"]


def test_no_key_when_only_boxes_are_marked() -> None:
    """A box's tag already says its word; it is a bare mark on a line that needs a key."""
    document = change(
        nodes=[{"id": "a", "text": "Old", "status": "changed"}, {"id": "b", "text": "Other"}],
        edges=[{"from": "a", "to": "b"}],
    )
    marks = [line.text for line in tags(scene(document)) if line.text == "~ changed"]
    assert marks == ["~ changed"]


def test_the_key_is_under_the_drawing() -> None:
    built = scene(change())
    boxes = [item for item in built.primitives if isinstance(item, Rect) and item.role == "step"]
    lowest = max(box.y + box.height for box in boxes)
    key = [line for line in tags(built) if line.text == "\u2212 removed"]
    assert max(line.y for line in key) > lowest
    assert built.height >= max(line.y for line in key)


def test_a_tree_takes_status_too() -> None:
    document = {
        "version": 1,
        "kind": "tree",
        "nodes": [
            {"id": "root", "text": "Root"},
            {"id": "new", "text": "New team", "status": "added"},
        ],
        "edges": [{"from": "root", "to": "new", "status": "added"}],
    }
    assert any(line.text == "+ added" for line in tags(scene(document)))


# --------------------------------------------------------------------------
# What is refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [None, "added", "changed"])
def test_an_edge_to_a_removed_box_must_be_removed(status: str | None) -> None:
    document = change()
    edge = document["edges"][2]  # type: ignore[index]
    if status is None:
        del edge["status"]
    else:
        edge["status"] = status
    found = pointers(document)
    assert "/edges/2/status" in found
    assert "'removed'" in found["/edges/2/status"]


@pytest.mark.parametrize("status", [None, "removed", "changed"])
def test_an_edge_to_an_added_box_must_be_added(status: str | None) -> None:
    document = change()
    edge = document["edges"][1]  # type: ignore[index]
    if status is None:
        del edge["status"]
    else:
        edge["status"] = status
    found = pointers(document)
    assert "/edges/1/status" in found
    assert "'added'" in found["/edges/1/status"]


def test_an_edge_between_an_added_and_a_removed_box_is_refused() -> None:
    document = change(edges=[{"from": "sess", "to": "table", "status": "removed"}])
    assert "never exist at the same time" in pointers(document)["/edges/0/status"]


def test_the_reference_change_validates() -> None:
    assert pointers(change()) == {}


def test_status_on_a_cycle_is_refused_at_each_mark() -> None:
    document = {
        "version": 1,
        "kind": "cycle",
        "nodes": [{"id": "a", "text": "A", "status": "added"}, {"id": "b", "text": "B"}],
        "edges": [{"from": "a", "to": "b", "status": "added"}, {"from": "b", "to": "a"}],
    }
    found = pointers(document)
    assert "/nodes/0/status" in found
    assert "/edges/0/status" in found
    assert "two cycles" in found["/nodes/0/status"]


def test_status_on_a_matrix_edge_is_refused() -> None:
    document = {
        "version": 1,
        "kind": "matrix",
        "cells": [
            {"id": "a", "text": "A", "column": 0, "row": 0},
            {"id": "b", "text": "B", "column": 1, "row": 0},
        ],
        "edges": [{"from": "a", "to": "b", "status": "added"}],
    }
    assert "/edges/0/status" in pointers(document)


def test_an_unknown_status_is_refused_by_the_vocabulary() -> None:
    document = change()
    document["nodes"][0]["status"] = "renamed"  # type: ignore[index]
    assert "/nodes/0/status" in pointers(document)
