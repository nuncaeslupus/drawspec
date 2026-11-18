"""The readability budget: a document that would draw, refused for being unreadable.

A `FitError` says the canvas is physically too small, and it arrives around
twenty boxes. Well before that a diagram stops being read and starts being
searched — and nothing said so. The budget is that earlier point, per kind, and
its refusal names the remedy: an overview plus detail diagrams.

The emphasis cap is the same kind of rule for one role: `emphasis` means *look
here first*, and a document that says it of three things has said it of none.

The numbers were set by measurement: every one sits above the largest document
of its kind in `docs/reference/`, which is what the test below holds them to. A
limit that refuses a reference document is a limit set too low.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec.errors import DocumentError
from drawspec.schema import (
    EMPHASIS_CAP,
    KINDS,
    READABILITY_BUDGET,
    parse_document,
    validate_document,
)

REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "reference"


def chain(count: int, **overrides: Any) -> dict[str, Any]:
    """A flow of `count` steps joined in a line — the plainest over-long process."""
    return {
        "version": 1,
        "kind": "flow",
        "nodes": [{"id": f"n{index}", "text": f"Step {index}"} for index in range(count)],
        "edges": [{"from": f"n{index}", "to": f"n{index + 1}"} for index in range(count - 1)],
        **overrides,
    }


def test_every_kind_has_a_budget() -> None:
    """A kind with no budget would be the one place an unreadable picture is drawn."""
    assert set(READABILITY_BUDGET) == set(KINDS)


@pytest.mark.parametrize("path", sorted(REFERENCE.glob("*.json")), ids=lambda path: path.stem)
def test_no_reference_document_is_past_its_budget(path: Path) -> None:
    """The gallery is the evidence the numbers were set from, so it must all pass."""
    document = json.loads(path.read_text(encoding="utf-8"))
    for name, limit in READABILITY_BUDGET[document["kind"]]:
        if document.get("style") == "bracket" and name == "nodes":
            continue  # a bracket counts its leaves instead, as `validate_document` does
        assert len(document.get(name, ())) <= limit, (path.stem, name)
    assert validate_document(document) == (), path.stem


def test_a_flow_at_its_budget_is_accepted() -> None:
    (limit,) = (limit for name, limit in READABILITY_BUDGET["flow"] if name == "nodes")
    assert validate_document(chain(limit)) == ()


def test_a_flow_past_its_budget_is_refused_at_the_first_entry_over() -> None:
    """The pointer lands on the box that broke the budget, and the message says split."""
    (limit,) = (limit for name, limit in READABILITY_BUDGET["flow"] if name == "nodes")
    with pytest.raises(DocumentError) as error:
        parse_document(chain(limit + 1))
    pointers = [violation.pointer for violation in error.value.violations]
    assert f"/nodes/{limit}" in pointers
    message = str(error.value)
    assert f"{limit + 1} nodes" in message
    assert "overview" in message
    assert "detail diagram" in message


def test_edges_have_their_own_budget_on_a_flow() -> None:
    """A mesh of few boxes can still be unreadable: the edges are counted too."""
    (limit,) = (limit for name, limit in READABILITY_BUDGET["flow"] if name == "edges")
    nodes = [{"id": f"n{index}", "text": f"Box {index}"} for index in range(7)]
    edges = [
        {"from": f"n{a}", "to": f"n{b}", "role": "link"} for a in range(7) for b in range(a + 1, 7)
    ]
    assert len(edges) > limit
    violations = validate_document({"version": 1, "kind": "flow", "nodes": nodes, "edges": edges})
    assert [violation.pointer for violation in violations] == [f"/edges/{limit}"]


def test_a_wider_canvas_does_not_lift_the_budget() -> None:
    """The size budget is for the canvas; it is not an opt-out, and the message says so."""
    (limit,) = (limit for name, limit in READABILITY_BUDGET["flow"] if name == "nodes")
    violations = validate_document(chain(limit + 1, width=4000))
    assert violations
    assert "'width' does not lift it" in violations[0].message


def test_items_kinds_are_budgeted_by_their_own_array() -> None:
    (limit,) = READABILITY_BUDGET["columns"]
    name, count = limit
    document = {
        "version": 1,
        "kind": "columns",
        "items": [{"text": f"Option {index}"} for index in range(count + 1)],
    }
    assert [violation.pointer for violation in validate_document(document)] == [f"/{name}/{count}"]


# --------------------------------------------------------------------------
# The emphasis cap
# --------------------------------------------------------------------------


def emphasised(count: int) -> dict[str, Any]:
    """A five-step chain with the first `count` steps emphasised."""
    document = chain(5)
    for node in document["nodes"][:count]:
        node["role"] = "emphasis"
    return document


@pytest.mark.parametrize("path", sorted(REFERENCE.glob("*.json")), ids=lambda path: path.stem)
def test_no_reference_document_emphasises_more_than_the_cap(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count('"emphasis"') <= EMPHASIS_CAP, path.stem


def test_the_cap_is_accepted_exactly() -> None:
    assert validate_document(emphasised(EMPHASIS_CAP)) == ()


def test_one_past_the_cap_is_refused_at_its_role_with_the_fix() -> None:
    with pytest.raises(DocumentError) as error:
        parse_document(emphasised(EMPHASIS_CAP + 1))
    pointers = [violation.pointer for violation in error.value.violations]
    assert pointers == [f"/nodes/{EMPHASIS_CAP}/role"]
    message = str(error.value)
    assert "look here first" in message
    assert "ordinary role" in message


def test_emphasis_is_counted_across_arrays() -> None:
    """A chart series and a curve are as heavy as a box; the cap is per document."""
    document = {
        "version": 1,
        "kind": "chart",
        "axes": {"horizontal": {"label": "Week"}, "vertical": {"label": "Requests"}},
        "series": [
            {"name": name, "role": "emphasis", "data": [[1, 1], [2, 2]]} for name in ("A", "B", "C")
        ],
    }
    assert [violation.pointer for violation in validate_document(document)] == ["/series/2/role"]


def test_strong_edges_are_not_counted() -> None:
    """A critical path is several `strong` edges and one line to the eye."""
    document = emphasised(EMPHASIS_CAP)
    for edge in document["edges"]:
        edge["role"] = "strong"
    assert validate_document(document) == ()
