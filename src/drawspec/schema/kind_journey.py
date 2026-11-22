"""The `journey` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._model import Detail, Document, JourneyStage, Slice, Violation

#: Why a journey has no place for a field an author may reach for.
JOURNEY_REFUSED: Final = {
    "edges": (
        "a journey's stages are already in order, left to right, and the feeling line joins "
        "them; an arrow between two stages adds nothing. Branching steps are a `flow`"
    ),
    "personas": (
        "a journey map is one person's: two feeling lines cross and erase each other. Draw "
        "one journey per person, with the same stages"
    ),
    "score": (
        "a feeling is a name, not a score — a numeric axis invites reading 3.4 off a sketch. "
        "Name the levels in `feelings`, worst first, and give each stage one by name"
    ),
    "value": (
        "a feeling is a name, not a score — a numeric axis invites reading 3.4 off a sketch. "
        "Name the levels in `feelings`, worst first, and give each stage one by name"
    ),
}


def _journey_refusal(violation: Violation) -> Violation:
    """A structural refusal in a journey, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if name in JOURNEY_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {JOURNEY_REFUSED[name]}.")
    numeric = violation.message in ("expected string, got int", "expected string, got float")
    if numeric and (name == "feeling" or parts[1:2] == ["feelings"]):
        return Violation(violation.pointer, f"a number: {JOURNEY_REFUSED['score']}.")
    if parts[1:] == ["feelings"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a journey needs at least 2 feelings: with one level the line is flat and says "
            "nothing. Name the levels the person moves between, worst first.",
        )
    if parts[1:] == ["stages"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a journey needs at least 2 stages: a feeling at one stage is a sentence, not a line.",
        )
    return violation


def _journey_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Feelings and row ids that are unique, and stages whose names land."""
    found: list[Violation] = []
    feelings: dict[str, int] = {}
    for index, feeling in enumerate(_listed(document, "feelings")):
        if not isinstance(feeling, str):
            continue
        if feeling in feelings:
            found.append(
                Violation(
                    _pointer("feelings", index),
                    f"{feeling!r} is already level {feelings[feeling]}: each level is named once.",
                )
            )
            continue
        feelings[feeling] = index
    rows: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "rows")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in rows:
            found.append(
                Violation(_pointer("rows", index, "id"), f"duplicate row id {identifier!r}")
            )
            continue
        rows[identifier] = index
    has_rows = isinstance(document.get("rows"), list)
    for index, stage in enumerate(_listed(document, "stages")):
        if not isinstance(stage, dict):
            continue
        feeling = stage.get("feeling")
        if isinstance(feeling, str) and feelings and feeling not in feelings:
            found.append(
                Violation(
                    _pointer("stages", index, "feeling"),
                    f"{feeling!r} is not one of the feelings, {', '.join(feelings)}"
                    + (_closest(feeling, feelings) or ". Name one of them, or add it there."),
                )
            )
        named: set[str] = set()
        details = stage.get("details")
        for position, detail in enumerate(details if isinstance(details, list) else []):
            row = detail.get("row") if isinstance(detail, dict) else None
            if not isinstance(row, str):
                continue
            where = _pointer("stages", index, "details", position, "row")
            if not has_rows:
                found.append(
                    Violation(
                        where,
                        "this journey has no `rows`, so a detail has no row to go in. Declare "
                        "the rows (what the person does, where, what gets in the way), or drop "
                        "'details'.",
                    )
                )
            elif row not in rows:
                found.append(
                    Violation(where, f"{row!r} is not the id of any row" + _closest(row, rows))
                )
            elif row in named:
                found.append(
                    Violation(
                        where,
                        f"{row!r} is named twice in this stage: a stage has one cell per row. "
                        f"Put both in one text.",
                    )
                )
            named.add(row)
    return found


def _journey_document(document: Mapping[str, Any]) -> Document:
    """A journey: its feelings worst first, its rows, and its stages in order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        feelings=tuple(document["feelings"]),
        journey_rows=tuple(
            Slice(id=entry["id"], text=entry["text"]) for entry in document.get("rows", ())
        ),
        journey_stages=tuple(
            JourneyStage(
                text=entry["text"],
                feeling=entry["feeling"],
                role=entry.get("role", "step"),
                details=tuple(
                    Detail(row=detail["row"], text=detail["text"])
                    for detail in entry.get("details", ())
                ),
            )
            for entry in document["stages"]
        ),
    )
