"""The `barmodel` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _closest, _is_number, _listed, _optional_number, _pointer
from drawspec.schema._constants import BARMODEL_UNIT_MAX
from drawspec.schema._model import Document, ModelBar, ModelBrace, ModelPart, Violation

#: Why a bar model has no place for a field an author may reach for.
BARMODEL_REFUSED: Final = {
    "edges": "a bar model joins nothing: what relates two bars is their lengths, side by side",
    "axes": (
        "a bar model has no axis: the numbers are written in the parts. Values compared "
        "against an axis are a `chart`"
    ),
    "series": (
        "a bar model has no data series: the numbers are written in the parts. Values "
        "compared against an axis are a `chart`"
    ),
    "total": (
        "a total is a brace over the bar: "
        '`{"over": ["the bar\'s id"], "amount": 60}`, checked against its parts'
    ),
    "unknown": 'an unknown part still has a size: give its `amount` or `units`, and `text: "?"`',
    "value": "a part's or a brace's size is its `amount`",
}


def _barmodel_refusal(violation: Violation) -> Violation:
    """A structural refusal in a bar model, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in BARMODEL_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {BARMODEL_REFUSED[name]}.")
    return violation


def _barmodel_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Parts with one size each, in one kind of size, and braces whose sums hold.

    Every part is an `amount` or `units`, never both or neither, and a document is
    all amounts or all units. Ids are unique across bars and parts. A brace spans
    side-by-side parts of one bar or consecutive whole bars, and its `amount` is
    checked: the sum of the parts it spans, or — with units — the same worth per
    unit as every other brace with an amount.
    """
    found: list[Violation] = []
    ids: dict[str, tuple[str, int, int]] = {}
    mode = ""
    mode_at = ""
    count = 0
    bars = _listed(document, "bars")
    for index, bar in enumerate(bars):
        if not isinstance(bar, dict):
            continue
        identifier = bar.get("id")
        if isinstance(identifier, str):
            if identifier in ids:
                found.append(
                    Violation(_pointer("bars", index, "id"), f"duplicate id {identifier!r}")
                )
            else:
                ids[identifier] = ("bar", index, -1)
        boxes = 0
        for position, part in enumerate(_listed(bar, "parts")):
            if not isinstance(part, dict):
                continue
            count += 1
            here = _pointer("bars", index, "parts", position)
            name = part.get("id")
            if isinstance(name, str):
                if name in ids:
                    found.append(Violation(f"{here}/id", f"duplicate id {name!r}"))
                else:
                    ids[name] = ("part", index, position)
            sizes = [field for field in ("amount", "units") if field in part]
            if not sizes:
                found.append(
                    Violation(
                        here,
                        "a part needs a size, or its length would be a guess: an `amount` (its "
                        "length in proportion) or `units` (that many equal boxes). An unknown "
                        'part still has one — write its `amount` and `"text": "?"`.',
                    )
                )
                continue
            if len(sizes) == 2:
                found.append(
                    Violation(
                        f"{here}/units",
                        "a part is an `amount` or a number of `units`, not both. Drop one.",
                    )
                )
                continue
            size = sizes[0]
            if not mode:
                mode, mode_at = size, f"{here}/{size}"
            elif size != mode:
                found.append(
                    Violation(
                        f"{here}/{size}",
                        f"this document's parts are sized by {mode!r} (from {mode_at}), and a "
                        f"unit has no length against a number. Size every part one way: give "
                        f"the units an amount each, or draw every part in units.",
                    )
                )
            units = part.get("units")
            if size == "units" and isinstance(units, int) and not isinstance(units, bool):
                boxes += units
                if boxes > BARMODEL_UNIT_MAX and boxes - units <= BARMODEL_UNIT_MAX:
                    found.append(
                        Violation(
                            f"{here}/units",
                            f"this bar is {boxes} unit boxes, and past {BARMODEL_UNIT_MAX} a "
                            f"reader counts boxes instead of seeing the ratio. Simplify the "
                            f"ratio, or let one box stand for more.",
                        )
                    )
    if bars and count == 1:
        found.append(
            Violation(
                _pointer("bars", 0, "parts"),
                "one part in one bar compares nothing: a bar model needs a second part, or a "
                "second bar. One number is a sentence.",
            )
        )

    def size_of(bar: int, position: int) -> float:
        part = _listed(bars[bar], "parts")[position]
        value: Any = part.get(mode) if isinstance(part, dict) else None
        return float(value) if _is_number(value) else math.nan

    worth: tuple[float, int] | None = None
    for index, brace in enumerate(_listed(document, "braces")):
        if not isinstance(brace, dict):
            continue
        if "amount" not in brace and "text" not in brace:
            found.append(
                Violation(
                    _pointer("braces", index),
                    "a brace says what the stretch adds up to: give it an `amount` (checked), "
                    'or `"text": "?"` for the unknown.',
                )
            )
        over = brace.get("over")
        if not isinstance(over, list) or not all(isinstance(item, str) for item in over):
            continue
        resolved: list[tuple[str, int, int]] = []
        for position, item in enumerate(over):
            if item not in ids:
                found.append(
                    Violation(
                        _pointer("braces", index, "over", position),
                        f"{item!r} is not the id of any bar or part" + _closest(item, ids),
                    )
                )
            elif ids[item] in resolved:
                found.append(
                    Violation(
                        _pointer("braces", index, "over", position),
                        f"{item!r} is named twice: a brace spans each thing once.",
                    )
                )
            else:
                resolved.append(ids[item])
        if len(resolved) != len(over):
            continue
        kinds = {kind for kind, _, _ in resolved}
        spanned: list[tuple[int, int]] = []
        if kinds == {"part"}:
            rows = {bar for _, bar, _ in resolved}
            columns = sorted(position for _, _, position in resolved)
            if len(rows) > 1:
                found.append(
                    Violation(
                        _pointer("braces", index, "over"),
                        "these parts are in different bars, and a brace spans one stretch of "
                        "one bar. For a total over bars, name the bars.",
                    )
                )
                continue
            if columns != list(range(columns[0], columns[0] + len(columns))):
                found.append(
                    Violation(
                        _pointer("braces", index, "over"),
                        "these parts are not side by side, and a brace spans one stretch. Name "
                        "the parts between them too, or use two braces.",
                    )
                )
                continue
            (row,) = rows
            spanned = [(row, column) for column in columns]
        elif kinds == {"bar"}:
            rows_list = sorted(bar for _, bar, _ in resolved)
            if rows_list != list(range(rows_list[0], rows_list[0] + len(rows_list))):
                found.append(
                    Violation(
                        _pointer("braces", index, "over"),
                        "these bars are not next to each other, and an upright brace spans "
                        "consecutive bars. Reorder the bars, or use two braces.",
                    )
                )
                continue
            spanned = [
                (row, column)
                for row in rows_list
                for column in range(len(_listed(bars[row], "parts")))
            ]
        else:
            found.append(
                Violation(
                    _pointer("braces", index, "over"),
                    "a brace spans parts of one bar or whole bars, not both. Name the bar "
                    "for the whole of it.",
                )
            )
            continue
        value: Any = brace.get("amount")
        if not _is_number(value) or not mode:
            continue
        total = sum(size_of(row, column) for row, column in spanned)
        if math.isnan(total):
            continue
        if mode == "amount":
            if not math.isclose(total, value, rel_tol=1e-9, abs_tol=1e-9):
                found.append(
                    Violation(
                        _pointer("braces", index, "amount"),
                        f"the parts this brace spans add up to {total:g}, not {value:g}. The "
                        f"model would teach the wrong sum: fix a part's amount, or the brace's.",
                    )
                )
        elif total == 0:
            continue
        elif worth is None:
            worth = (value / total, index)
        elif not math.isclose(value / total, worth[0], rel_tol=1e-9):
            found.append(
                Violation(
                    _pointer("braces", index, "amount"),
                    f"this brace makes one unit worth {value / total:g}, and brace {worth[1]} "
                    f"makes it {worth[0]:g}. Every unit in a bar model is the same size: fix "
                    f"one of the two.",
                )
            )
    return found


def _barmodel_document(document: Mapping[str, Any]) -> Document:
    """A bar model: its bars top to bottom, each with its parts, and its braces."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        model_bars=tuple(
            ModelBar(
                parts=tuple(
                    ModelPart(
                        amount=_optional_number(part.get("amount")),
                        units=part.get("units"),
                        text=part.get("text", ""),
                        id=part.get("id", ""),
                        role=part.get("role", "step"),
                    )
                    for part in bar["parts"]
                ),
                text=bar.get("text", ""),
                id=bar.get("id", ""),
            )
            for bar in document["bars"]
        ),
        model_braces=tuple(
            ModelBrace(
                over=tuple(brace["over"]),
                amount=_optional_number(brace.get("amount")),
                text=brace.get("text", ""),
            )
            for brace in document.get("braces", ())
        ),
    )
