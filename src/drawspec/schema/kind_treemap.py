"""The `treemap` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._model import Document, TreemapGroup, TreemapPart, Violation

#: Why a treemap has no place for a field an author may reach for.
TREEMAP_REFUSED: Final = {
    "edges": (
        "a treemap's parts are related by being one whole; there is nothing to connect. "
        "Where a quantity goes from one place to another is a `flow`"
    ),
    "percent": (
        "drawspec takes each part's share from its `amount` and the total, so the areas "
        "cannot disagree with the numbers. Write the amount"
    ),
    "share": (
        "drawspec takes each part's share from its `amount` and the total, so the areas "
        "cannot disagree with the numbers. Write the amount"
    ),
    "children": (
        "a treemap has one level of grouping: a part names its group in `group`, and a "
        "group holds parts, not groups. Past one level it is a disk-usage tool's output"
    ),
    "parts": (
        "a group does not list its parts: each part names its group in `group`. Groups do not nest"
    ),
    "groups": (
        "a treemap has one level of grouping, so a group holds parts, never groups. Draw a "
        "treemap per group instead"
    ),
    "group": (
        "a treemap has one level of grouping, so a group holds parts, never groups. Draw a "
        "treemap per group instead"
    ),
}


def _treemap_refusal(violation: Violation) -> Violation:
    """A structural refusal in a treemap, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    in_group = parts[1:2] == ["groups"] and len(parts) == 4
    if name == "value" and parts[1:2] == ["parts"] and len(parts) == 4:
        return Violation(
            violation.pointer,
            "'value': a treemap part's number is its `amount` — how much of the total it is, "
            "in the treemap's `unit`.",
        )
    if "is not a known field" in violation.message and name in TREEMAP_REFUSED:
        if name in ("parts", "groups", "group") and not in_group:
            return violation
        return Violation(violation.pointer, f"{name!r}: {TREEMAP_REFUSED[name]}.")
    if name == "amount" and parts[1:2] == ["parts"] and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a part's amount is its area, so it must be more than 0. A part of nothing is not "
            "drawn: leave it out, or say so in the caption.",
        )
    if parts[1:] == ["parts"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a treemap needs at least 2 parts: one part of a total is the total. Say it in a "
            "sentence.",
        )
    return violation


def _treemap_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Group ids that are unique, parts whose groups land, and no empty group."""
    found: list[Violation] = []
    groups: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "groups")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in groups:
            found.append(
                Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
            )
            continue
        groups[identifier] = index
    named: set[str] = set()
    for index, part in enumerate(_listed(document, "parts")):
        group = part.get("group") if isinstance(part, dict) else None
        if not isinstance(group, str):
            continue
        if group not in groups:
            found.append(
                Violation(
                    _pointer("parts", index, "group"),
                    f"{group!r} is not the id of any group"
                    + (_closest(group, groups) if groups else ": this treemap has no `groups`."),
                )
            )
            continue
        named.add(group)
    for identifier, index in groups.items():
        if identifier not in named:
            found.append(
                Violation(
                    _pointer("groups", index),
                    f"no part names the group {identifier!r}, so it would be an empty frame. "
                    f'Give it parts with `"group": "{identifier}"`, or drop it.',
                )
            )
    return found


def _treemap_document(document: Mapping[str, Any]) -> Document:
    """A treemap: its parts and groups in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        treemap_parts=tuple(
            TreemapPart(
                text=entry["text"],
                amount=float(entry["amount"]),
                group=entry.get("group", ""),
                role=entry.get("role", "step"),
            )
            for entry in document["parts"]
        ),
        treemap_groups=tuple(
            TreemapGroup(id=entry["id"], text=entry["text"]) for entry in document.get("groups", ())
        ),
    )
