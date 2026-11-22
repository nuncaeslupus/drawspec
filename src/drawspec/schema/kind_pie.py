"""The `pie` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _figure, _is_number, _listed, _optional_number, _pointer
from drawspec.schema._constants import PIE_PERCENT_TOLERANCE, PIE_SHARE_MIN
from drawspec.schema._model import Document, PiePart, Violation

#: Why a pie has no place for a field an author may reach for.
PIE_REFUSED: Final = {
    "edges": "a pie's parts are related by being one whole; there is nothing to connect",
    "series": "a pie is one total split into parts. Values against an axis are a `chart`",
    "axes": "a pie has no axes. Values against an axis are a `chart`",
    "value": "a part's size is its `amount`",
    "percent": (
        "drawspec takes each share from the `amount`s and their sum, so the angles cannot "
        'disagree with the numbers. Write the amount; for percentages, set `"unit": "%"`'
    ),
    "share": (
        "drawspec takes each share from the `amount`s and their sum, so the angles cannot "
        'disagree with the numbers. Write the amount; for percentages, set `"unit": "%"`'
    ),
    "angle": "a sector's angle is its share of the total, computed from its `amount`",
    "total": (
        "a pie's total is the sum of its amounts, so it cannot disagree with them. Say it "
        "in the title if the reader needs it"
    ),
    "groups": "a pie has one level of parts. Parts in groups are a `treemap`",
    "group": "a pie has one level of parts. Parts in groups are a `treemap`",
    "donut": 'a ring instead of a disc is house style: a theme\'s `[pie] shape = "donut"`',
    "hole": 'a ring instead of a disc is house style: a theme\'s `[pie] shape = "donut"`',
}


def _pie_refusal(violation: Violation) -> Violation:
    """A structural refusal in a pie, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in PIE_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {PIE_REFUSED[name]}.")
    if parts[1:] == ["parts"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a pie needs at least 2 parts: one part of a total is the total. Say it in a sentence.",
        )
    if name == "amount" and parts[1:2] == ["parts"] and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a part's amount is its angle, so it must be more than 0. A part of nothing is "
            "not drawn: leave it out.",
        )
    return violation


def _pie_violations(document: Mapping[str, Any]) -> list[Violation]:
    """One remainder at most, no sliver, and percentages that add up to 100."""
    found: list[Violation] = []
    parts = [part for part in _listed(document, "parts") if isinstance(part, dict)]
    notes = [
        index
        for index, part in enumerate(_listed(document, "parts"))
        if isinstance(part, dict) and part.get("role") == "note"
    ]
    for index in notes[1:]:
        found.append(
            Violation(
                _pointer("parts", index, "role"),
                f"part {notes[0]} is already the remainder: a pie has one `note` part, "
                f"`Everything else`. Merge the two.",
            )
        )
    amounts = [float(part["amount"]) for part in parts if _is_number(part.get("amount"))]
    if not amounts or len(amounts) != len(parts) or min(amounts) <= 0:
        return found
    total = float(sum(amounts))
    for index, amount in enumerate(amounts):
        if amount / total < PIE_SHARE_MIN:
            found.append(
                Violation(
                    _pointer("parts", index, "amount"),
                    f"this part is {100 * amount / total:.1f}% of the total, a sliver whose "
                    f"angle cannot be read — under {100 * PIE_SHARE_MIN:g}%. Merge it into one "
                    f'`"role": "note"` part with the others too small to see.',
                )
            )
    if document.get("unit") == "%" and abs(total - 100) > PIE_PERCENT_TOLERANCE:
        found.append(
            Violation(
                "/parts",
                f"these percentages add up to {_figure(total)}, not 100 — "
                f"{_figure(abs(total - 100))} {'over' if total > 100 else 'short'}, more "
                f"than rounding. A pie of percentages is the whole: fix a part, or add the "
                f"missing share as a `note` part.",
            )
        )
    return found


def _pie_document(document: Mapping[str, Any]) -> Document:
    """A pie: its parts in the order written, and the unit they are in."""
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
        pie_parts=tuple(
            PiePart(
                text=part["text"],
                amount=float(part["amount"]),
                role=part.get("role", "step"),
            )
            for part in document["parts"]
        ),
    )
