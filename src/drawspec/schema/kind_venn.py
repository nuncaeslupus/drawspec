"""The `venn` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._constants import VENN_FOUR_TEXT_MAX, VENN_SET_MAX
from drawspec.schema._model import Document, Region, VennSet, Violation

#: Why a venn has no place for a field an author may reach for.
VENN_REFUSED: Final = {
    "edges": "a Venn diagram has nothing to connect: what relates the sets is their overlap",
    "subset_of": (
        "a set wholly inside another is scopes nested inside scopes, which is `rings`; a "
        "Venn diagram draws sets that overlap"
    ),
    "size": (
        "the circles are equal on purpose: a Venn diagram says what overlaps, not how much. "
        "A number belongs in the text, or in a `chart`"
    ),
    "value": (
        "the circles are equal on purpose: a Venn diagram says what overlaps, not how much. "
        "A number belongs in the text, or in a `chart`"
    ),
}


def _venn_refusal(violation: Violation) -> Violation:
    """A structural refusal in a venn, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if name in VENN_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {VENN_REFUSED[name]}.")
    if parts[1:] == ["sets"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a Venn diagram needs 2 to 4 sets: one set overlaps nothing. Say what it holds in "
            "a sentence, or as a list.",
        )
    return violation


def _venn_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Set ids that are unique, and regions whose memberships land and differ."""
    found: list[Violation] = []
    sets: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "sets")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in sets:
            found.append(
                Violation(_pointer("sets", index, "id"), f"duplicate set id {identifier!r}")
            )
            continue
        sets[identifier] = index
    seen: dict[frozenset[str], int] = {}
    for index, region in enumerate(_listed(document, "regions")):
        members = region.get("in") if isinstance(region, dict) else None
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            continue
        named: set[str] = set()
        landed = True
        for position, member in enumerate(members):
            if member not in sets:
                landed = False
                found.append(
                    Violation(
                        _pointer("regions", index, "in", position),
                        f"{member!r} is not the id of any set" + _closest(member, sets),
                    )
                )
            elif member in named:
                landed = False
                found.append(
                    Violation(
                        _pointer("regions", index, "in", position),
                        f"{member!r} is named twice: `in` lists each set the region is in once.",
                    )
                )
            named.add(member)
        if not landed or not named:
            continue
        key = frozenset(named)
        if key in seen:
            found.append(
                Violation(
                    _pointer("regions", index, "in"),
                    f"region {seen[key]} is already the region in exactly these sets. A region "
                    f"is drawn once: put both texts in one.",
                )
            )
            continue
        seen[key] = index
    if len(sets) == VENN_SET_MAX:
        for index, region in enumerate(_listed(document, "regions")):
            text = region.get("text") if isinstance(region, dict) else None
            if not isinstance(text, str):
                continue
            shown = text.replace("**", "").replace("`", "").replace("\n", " ")
            if len(shown) > VENN_FOUR_TEXT_MAX:
                found.append(
                    Violation(
                        _pointer("regions", index, "text"),
                        f"{len(shown)} characters is more than a region of four sets holds — "
                        f"{VENN_FOUR_TEXT_MAX} at most. With four sets the smallest regions "
                        f"are small: write a count or a word or two, and say the rest in the "
                        f"caption.",
                    )
                )
    return found


def _venn_document(document: Mapping[str, Any]) -> Document:
    """A venn: its sets in order, and its regions by membership."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        venn_sets=tuple(
            VennSet(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["sets"]
        ),
        regions=tuple(
            Region(
                members=tuple(entry["in"]),
                text=entry["text"],
                role=entry.get("role", "step"),
            )
            for entry in document.get("regions", ())
        ),
    )
