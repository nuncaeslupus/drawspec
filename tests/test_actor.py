"""`actor` — who performs a step, orthogonal to what kind of step it is.

Issue #48 asked for this and the diagnosis took two rounds, so the reasoning is
worth keeping next to the assertions.

**Ownership cannot be a role.** A node's appearance has six fields, four of them
non-colour, and those four are exactly what the greyscale invariant compares —
all four are already spent telling the eight roles apart. So a ninth role would
either be indistinguishable in greyscale or would take a channel off an existing
one. `decision` was tried and actively misinforms (a diamond promises a branch
that is not there); `emphasis` conflates *this matters* with *a person does this*,
which are independent.

**And ownership cannot be a band.** This is the one that had to be measured
rather than argued. A band's bar spans its members' *extent*, so an owner holding
the first, second and fourth step of a flow draws a bar straight across the
third — the picture then claims a step the document says it does not own. A band
over a single node cannot even be named, because the name has to fit the span its
members occupy. Both are tested below, because "we chose the other thing" is not
a reason that survives anyone asking why.

**What makes `actor` cheap is that it is not an appearance at all.** The tag
carries the actor's *name*, and text is distinguishable in greyscale by
construction — `CI` does not look like `Human` in any medium. So it costs none of
the four channels, and `theme check` needs no new axis. That is why the field is
free text rather than an enum: constraining the vocabulary would remove the very
thing doing the work.
"""

from __future__ import annotations

import json
import re
from pathlib import Path as FilePath
from typing import Any, Final

import pytest

from drawspec.errors import DocumentError, DrawspecError
from drawspec.render import render_document
from drawspec.schema import Node, parse_document, validate_document

REFERENCE: Final = FilePath(__file__).resolve().parents[1] / "docs" / "reference"

#: The document from issue #48, which is what the request was written from.
PIPELINE: Final[dict[str, Any]] = {
    "version": 1,
    "kind": "flow",
    "title": "Release pipeline",
    "nodes": [
        {"id": "build", "text": "Build the artefact", "actor": "CI"},
        {"id": "test", "text": "Run the suite", "actor": "CI"},
        {"id": "stage", "text": "Deploy to staging", "actor": "CI"},
        {"id": "approve", "text": "Sign off the release", "actor": "A release manager"},
        {"id": "prod", "text": "Deploy to production", "actor": "CI"},
    ],
    "edges": [
        {"from": "build", "to": "test"},
        {"from": "test", "to": "stage"},
        {"from": "stage", "to": "approve"},
        {"from": "approve", "to": "prod"},
    ],
}


def rendered(document: dict[str, Any]) -> str:
    return render_document(parse_document(document))


# ---------------------------------------------------------------------------
# The field
# ---------------------------------------------------------------------------


def test_an_actor_becomes_the_boxs_lead() -> None:
    """The name over what belongs to it, and the family does not get a say.

    Asserted on `Node` rather than on a drawing because `flow`, `tree` and
    `cycle` all size their boxes from this one property — if it lived in each
    family they could disagree about where the actor sits, and a reader scanning
    a column of them would be scanning nothing.
    """
    node = Node(id="approve", text="Sign off the release", actor="A release manager")
    assert node.label == "A release manager\nSign off the release"
    assert node.lead is True


def test_a_node_without_an_actor_is_left_to_answer_for_itself() -> None:
    """`None`, not `False`.

    A node with no actor may still have written its own lead, and answering
    `False` on its behalf would take that away — the newline in `text` is the
    author saying *these are two things* and it predates this field.
    """
    node = Node(id="a", text="**Payment**\nreference\namount")
    assert node.lead is None
    assert node.label == node.text


def test_the_actor_is_drawn_in_every_box_that_names_one() -> None:
    svg = rendered(PIPELINE)
    assert svg.count(">CI<") == 4
    assert "A release manager" in svg


def test_ownership_is_orthogonal_to_role() -> None:
    """Every box here is a plain `step`; only the actor differs.

    This is the whole complaint in issue #48 — that saying *who* used to cost
    the slot that says *what kind* — so it is asserted rather than assumed.
    """
    document = json.loads((REFERENCE / "flow-actors.json").read_text(encoding="utf-8"))
    assert {node.get("role", "step") for node in document["nodes"]} == {"step"}
    assert len({node["actor"] for node in document["nodes"]}) == 2


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def test_an_actor_and_a_written_lead_are_the_same_slot() -> None:
    """A box has one lead. Refused by pointer, not silently resolved.

    Picking a winner would be the tool deciding which of two things the author
    said it meant, which is exactly what a refusal exists to avoid.
    """
    document = json.loads(json.dumps(PIPELINE))
    document["nodes"][3]["text"] = "Sign off\nthe release goes out"
    violations = validate_document(document)
    assert [violation.pointer for violation in violations] == ["/nodes/3/actor"]
    assert "a single lead" in violations[0].message


def test_a_node_may_still_write_its_own_lead_when_it_names_no_actor() -> None:
    """The refusal is about the collision, not about newlines."""
    document = json.loads(json.dumps(PIPELINE))
    document["nodes"][3] = {"id": "approve", "text": "Sign off\nthe release goes out"}
    assert not validate_document(document)


def test_an_actor_is_free_text_rather_than_an_enum() -> None:
    """The name is the channel, so the vocabulary cannot be closed.

    `human`/`machine` would not have covered `finance` or `the customer`, and
    those are the cases that make this worth a field.
    """
    document = json.loads(json.dumps(PIPELINE))
    document["nodes"][0]["actor"] = "Finance, on the last working day"
    assert not validate_document(document)


# ---------------------------------------------------------------------------
# Why not a band. Measured, because it was the cheapest candidate.
# ---------------------------------------------------------------------------


#: A band's bar and an edge are both vertical paths; the theme draws them at
#: different weights, and the bar is the thinner one.
_BAR: Final = re.compile(
    r'<path d="M ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+)"[^>]*stroke-width="1"/>'
)


def _bars(svg: str) -> list[tuple[float, float]]:
    """Every band bar's vertical span, longest first."""
    spans = []
    for match in _BAR.finditer(svg):
        x1, y1, x2, y2 = (float(value) for value in match.groups())
        if x1 == x2:
            spans.append((min(y1, y2), max(y1, y2)))
    return sorted(spans, key=lambda span: span[0] - span[1])


def _text_y(svg: str, words: str) -> float:
    """Where a given label's baseline sits."""
    match = re.search(rf'<text x="[\d.]+" y="([\d.]+)"[^>]*>(?:(?!</text>).)*{words}', svg)
    assert match, f"no label reading {words!r}"
    return float(match.group(1))


def test_a_band_cannot_say_who_owns_a_step_because_it_spans_its_members() -> None:
    """The measurement that ruled bands out, kept so nobody re-proposes them.

    `CI` owns four of the five steps and the fifth sits in the middle of them.
    A band's bar runs the whole *extent* of its members, so CI's bar is drawn
    straight past `approve` — the picture claims a step the document says CI
    does not perform. Ownership is a property of one box, not a span over
    several, and that is the whole reason it is a field on the node.
    """
    banded = json.loads(json.dumps(PIPELINE))
    for node in banded["nodes"]:
        node.pop("actor")
    banded["bands"] = [
        {"text": "CI", "members": ["build", "test", "stage", "prod"]},
        {"text": "Human", "members": ["approve"]},
    ]
    svg = rendered(banded)
    bars = _bars(svg)
    assert len(bars) == 2, "expected one bar per band"

    top, bottom = bars[0]
    approve = _text_y(svg, "Sign off the release")
    assert top < approve < bottom, (
        f"CI's bar spans {top} to {bottom} and the step it does not own sits at {approve}"
    )


def test_the_actor_drawing_makes_no_such_claim() -> None:
    """The same five steps, said with `actor`: no bar, so nothing to overreach."""
    assert not _bars(rendered(PIPELINE))


def test_a_band_over_a_single_step_cannot_be_named() -> None:
    """The second, independent failure: a band's name must fit its members' span.

    A one-step actor is exactly the case in the issue, and it is unnameable.
    """
    banded = json.loads(json.dumps(PIPELINE))
    for node in banded["nodes"]:
        node.pop("actor")
    banded["bands"] = [{"text": "A release manager", "members": ["approve"]}]
    with pytest.raises(DrawspecError) as refusal:
        rendered(banded)
    assert "A release manager" in str(refusal.value)


# ---------------------------------------------------------------------------
# The evidence, and the invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["flow-actors", "flow-actor-handover"])
def test_the_reference_documents_draw(name: str) -> None:
    """A mechanism with no drawing behind it is what `kinds-wanted.md` prevents."""
    document = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    svg = rendered(document)
    for node in document["nodes"]:
        assert node["actor"] in svg


def test_the_greyscale_invariant_is_untouched_by_actors() -> None:
    """No new appearance channel, so nothing new for `theme check` to compare.

    Two boxes differing only in actor differ in their *words*. If that ever
    stopped being true — if a theme keyed actors by fill — this test would still
    pass and `theme check` would be the thing that has to catch it, which is why
    the mechanism is deliberately not an appearance.
    """
    one = json.loads(json.dumps(PIPELINE))
    other = json.loads(json.dumps(PIPELINE))
    other["nodes"][0]["actor"] = "Somebody else"
    assert rendered(one) != rendered(other)


def test_an_unknown_field_is_still_refused() -> None:
    """Adding `actor` did not open the object up."""
    document = json.loads(json.dumps(PIPELINE))
    document["nodes"][0]["performer"] = "CI"
    with pytest.raises(DocumentError) as refusal:
        parse_document(document)
    assert any(violation.pointer == "/nodes/0/performer" for violation in refusal.value.violations)
