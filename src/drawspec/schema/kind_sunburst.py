"""The `sunburst` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._constants import SUNBURST_DEPTH_MAX, SUNBURST_NODE_MAX
from drawspec.schema._model import Document, SunburstNode, Violation

#: Why a sunburst has no place for a field an author may reach for.
SUNBURST_REFUSED: Final = {
    "angle": (
        "a sector's angle is its share of the circle, computed from the tree — a terminal "
        "node takes an equal slice and a parent spans its children. It is never written"
    ),
    "weight": (
        "every terminal node weighs the same, so the wheel is read from its shape alone. A "
        "wheel sized by amounts is a `pie` or a `treemap`"
    ),
    "value": (
        "a sunburst states a hierarchy, not quantities: the shares are equal and derived. "
        "For an amount per part draw a `pie` or a `treemap`"
    ),
    "amount": (
        "a sunburst states a hierarchy, not quantities: the shares are equal and derived. "
        "For an amount per part draw a `pie` or a `treemap`"
    ),
    "size": (
        "a label's size is chosen to fit its sector, largest first and smaller for a longer "
        "word: the type is drawspec's, never the author's"
    ),
    "radius": (
        "the rings are sized to the words they hold; a radius set by the author is a coordinate"
    ),
    "role": (
        "a sunburst node is words in a sector, with no shape or stance to mark: it takes only "
        "`text` and `children`"
    ),
    "id": "nothing refers to a sector: its place is where it is written, nested in its parent",
    "edges": (
        "a sunburst is nested, so there is nothing to connect; a line between sectors is a `flow`"
    ),
}


def _sunburst_refusal(violation: Violation) -> Violation:
    """A structural refusal in a sunburst, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in SUNBURST_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {SUNBURST_REFUSED[name]}.")
    if parts[1:] == ["nodes"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a sunburst needs at least 2 nodes in its first ring: one sector is a whole "
            "circle, which says nothing.",
        )
    if name == "children" and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "an empty 'children' list draws nothing: leave the field out of a node that ends "
            "the hierarchy.",
        )
    return violation


def _sunburst_fourth_ring(pointer: str) -> Violation:
    """The located violation for a node that would open a fourth ring."""
    return Violation(
        pointer,
        f"a fourth ring is past what one sunburst can be read at — "
        f"{SUNBURST_DEPTH_MAX} rings at most. Fold the detail into this "
        f"sector's words, or make it the centre of a wheel of its own.",
    )


def _sunburst_too_deep(document: Mapping[str, Any]) -> Violation | None:
    """The first node nested past `SUNBURST_DEPTH_MAX`, found without recursion.

    `sunburst-node` refers to itself through `children`, and the structural pass
    (`_check_object`) recurses once per level with no depth limit. A document
    nested hundreds deep still parses as JSON, so without this it raises
    `RecursionError` inside `validate_document` — which also serves MCP and agent
    input — instead of a located violation. This iterative pre-scan runs first so
    the depth cap is reported before the recursive pass can overflow.
    """
    stack: list[tuple[object, str, int]] = [(document.get("nodes"), "/nodes", 1)]
    while stack:
        entries, pointer, depth = stack.pop()
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("children"), list):
                continue
            here = f"{pointer}/{index}/children"
            if depth == SUNBURST_DEPTH_MAX:
                return _sunburst_fourth_ring(here)
            stack.append((entry["children"], here, depth + 1))
    return None


def _sunburst_violations(document: Mapping[str, Any]) -> list[Violation]:
    """No empty words, no fourth ring, and the first-ring and total caps."""
    found: list[Violation] = []
    centre = document.get("centre")
    if isinstance(centre, str) and centre and not centre.strip():
        found.append(Violation("/centre", "the hub label needs words, or leave `centre` out."))

    total = 0
    first = document.get("nodes")

    def walk(entries: object, pointer: str, depth: int) -> None:
        nonlocal total
        if not isinstance(entries, list):
            return
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            total += 1
            here = f"{pointer}/{index}"
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(
                    Violation(
                        f"{here}/text", "a sector needs words: an empty one is a blank wedge."
                    )
                )
            children = entry.get("children")
            if depth == SUNBURST_DEPTH_MAX and isinstance(children, list):
                found.append(_sunburst_fourth_ring(f"{here}/children"))
                continue
            walk(children, f"{here}/children", depth + 1)

    walk(first, "/nodes", 1)
    if total > SUNBURST_NODE_MAX:
        found.append(
            Violation(
                "/nodes",
                f"{total} sectors in all is past what one sunburst can be read at — "
                f"{SUNBURST_NODE_MAX} at most, counted across every ring. Split it into an "
                f"overview wheel and a wheel per branch.",
            )
        )
    return found


def _sunburst_node(entry: Mapping[str, Any]) -> SunburstNode:
    """One sunburst node and its subtree, built from the validated mapping."""
    return SunburstNode(
        text=str(entry["text"]),
        children=tuple(_sunburst_node(child) for child in entry.get("children", ())),
    )


def _sunburst_document(document: Mapping[str, Any]) -> Document:
    """A sunburst: its optional hub and its nested rings, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        centre=str(document.get("centre", "")),
        sunburst_nodes=tuple(_sunburst_node(entry) for entry in document["nodes"]),
    )
