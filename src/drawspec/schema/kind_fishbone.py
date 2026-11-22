"""The `fishbone` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._model import Category, Cause, Document, Violation

#: Why a fishbone has no place for a field an author may reach for.
FISHBONE_REFUSED: Final = {
    "edges": (
        "the connections of a fishbone are its structure, so there is nothing to add. A cause "
        "that contributes to another cause is a different diagram: a `flow`"
    ),
    "causes": (
        "a cause is a leaf. A sub-cause of a cause is a second fishbone, with that cause as "
        "its effect — draw that one beside this"
    ),
    "role": (
        "the effect is the head, always drawn as the diagram's emphasis; it takes no role. "
        "Mark the confirmed root cause with `emphasis` on that cause instead"
    ),
}


def _fishbone_refusal(violation: Violation) -> Violation:
    """A structural refusal in a fishbone, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message
    if unknown and name == "edges" and len(parts) == 2:
        return Violation(violation.pointer, f"'edges': {FISHBONE_REFUSED['edges']}.")
    if unknown and name == "causes" and len(parts) == 6:
        return Violation(violation.pointer, f"'causes': {FISHBONE_REFUSED['causes']}.")
    if unknown and name == "role" and parts[1:2] == ["effect"]:
        return Violation(violation.pointer, f"'role': {FISHBONE_REFUSED['role']}.")
    if "needs at least" in violation.message:
        if parts[1:] == ["categories"]:
            return Violation(
                violation.pointer,
                "a fishbone needs at least 2 categories: one category is a list of causes. "
                "Write it as a list, or name the second category the causes fall under.",
            )
        if len(parts) == 4 and name == "causes":
            return Violation(
                violation.pointer,
                "a category with no causes is a heading with no investigation under it. If "
                'nothing was found, say so: `{"text": "nothing found", "role": "note"}`.',
            )
    if len(parts) == 6 and name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A cause is a tick on a bone, with no shape to mean `decision` or "
            "`terminal`: `step`, `emphasis` for the confirmed root cause, `note` for one "
            "ruled out.",
        )
    return violation


def _fishbone_document(document: Mapping[str, Any]) -> Document:
    """A fishbone: its effect and its categories, each with its causes, in order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        effect=str(document["effect"]["text"]),
        categories=tuple(
            Category(
                text=entry["text"],
                causes=tuple(
                    Cause(text=cause["text"], role=cause.get("role", "step"))
                    for cause in entry["causes"]
                ),
            )
            for entry in document["categories"]
        ),
    )
