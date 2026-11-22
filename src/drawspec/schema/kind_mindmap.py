"""The `mindmap` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._constants import MINDMAP_DEPTH_MAX
from drawspec.schema._model import Document, MindmapBranch, Violation

#: Why a mind map has no place for a field an author may reach for.
MINDMAP_REFUSED: Final = {
    "edges": (
        "a mind map is nested: a branch belongs to the one it is written in, so there is "
        "nothing to connect. Links across branches, each named by a phrase, are a concept "
        "map: draw that as a `flow` with labelled edges"
    ),
    "links": (
        "a mind map is nested, so a line between two branches would make it a concept map. "
        "Draw that as a `flow` with labelled edges"
    ),
    "id": (
        "nothing refers to a branch: its place is where it is written. A link from one "
        "branch to another is a concept map, which is a `flow` with labelled edges"
    ),
    "side": (
        "the layout splits the main branches between the two sides so they balance; a side "
        "chosen by the author is a coordinate. Order them, and drawspec places them "
        "clockwise from the top right"
    ),
    "nodes": "a mind map's entries are its `branches`, nested under the `centre`",
}


def _mindmap_refusal(violation: Violation) -> Violation:
    """A structural refusal in a mind map, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in MINDMAP_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {MINDMAP_REFUSED[name]}.")
    if parts[1:] == ["branches"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a mind map needs at least 2 main branches round its centre: one branch is a "
            "hierarchy from a root, which is a `tree`.",
        )
    if name == "branches" and len(parts) > 2 and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "an empty 'branches' list draws nothing: leave the field out of a branch that "
            "ends here.",
        )
    if name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A branch is words on a line, with no shape to mean `decision` or "
            "`terminal`: `step`, `emphasis` for the branch the map is about, `note` for "
            "context.",
        )
    return violation


def _mindmap_violations(document: Mapping[str, Any]) -> list[Violation]:
    """No empty words, and no fourth level below the centre."""
    found: list[Violation] = []
    centre = document.get("centre")
    if isinstance(centre, str) and not centre.strip():
        found.append(Violation("/centre", "the centre is the topic: it needs words."))

    def walk(entries: object, pointer: str, depth: int) -> None:
        if not isinstance(entries, list):
            return
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            here = f"{pointer}/{index}"
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(
                    Violation(
                        f"{here}/text", "a branch needs words: an empty one draws a bare line."
                    )
                )
            children = entry.get("branches")
            if depth == MINDMAP_DEPTH_MAX and isinstance(children, list):
                found.append(
                    Violation(
                        f"{here}/branches",
                        f"a fourth level below the centre is past what one mind map can be "
                        f"read at — {MINDMAP_DEPTH_MAX} levels at most: a branch, a twig, a "
                        f"leaf. Make this branch the centre of a map of its own, or fold the "
                        f"detail into this leaf's words.",
                    )
                )
                continue
            walk(children, f"{here}/branches", depth + 1)

    walk(document.get("branches"), "/branches", 1)
    return found


def _mindmap_branch(entry: Mapping[str, Any]) -> MindmapBranch:
    return MindmapBranch(
        text=str(entry["text"]),
        role=str(entry.get("role", "step")),
        branches=tuple(_mindmap_branch(child) for child in entry.get("branches", ())),
    )


def _mindmap_document(document: Mapping[str, Any]) -> Document:
    """A mind map: its centre and its nested branches, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        centre=str(document["centre"]),
        branches=tuple(_mindmap_branch(entry) for entry in document["branches"]),
    )
