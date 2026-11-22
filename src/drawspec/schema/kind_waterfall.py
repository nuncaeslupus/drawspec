"""The `waterfall` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _figure, _is_number, _listed, _optional_number, _pointer
from drawspec.schema._model import Document, Violation, WaterfallBar

#: Why a waterfall has no place for a field an author may reach for.
WATERFALL_REFUSED: Final = {
    "edges": "a waterfall's connectors join each bar to the next for you, at the running sum",
    "series": (
        "a waterfall is one sequence of bars, totals and steps. Several series against an "
        "axis are a `chart`"
    ),
    "axes": (
        "a waterfall has one numeric axis, `axis`, and its bars in order across. Values "
        "against two axes are a `chart`"
    ),
    "value": "a step's size is its signed `amount`, and a total's is its `total`",
    "subtotal": "a subtotal is a `total` between the first bar and the last, checked",
    "start": "the start is the first bar, a `total`",
    "end": "the end is the last bar, a `total`, checked against the steps",
    "unit": "the unit goes in the axis label: `Borrowing, £ billion`",
}


def _waterfall_refusal(violation: Violation) -> Violation:
    """A structural refusal in a waterfall, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in WATERFALL_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {WATERFALL_REFUSED[name]}.")
    return violation


def _waterfall_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Bars that are each a total or a step, and totals that are the running sum.

    The first and the last bar are totals; a total straight after a total says
    nothing; a step of 0 is not drawn. Every total after the first is checked
    against the sum of the bars before it, and refused with the difference.
    """
    found: list[Violation] = []
    bars = [bar for bar in _listed(document, "bars") if isinstance(bar, dict)]
    if len(bars) != len(_listed(document, "bars")):
        return found
    running: float | None = None
    previous = ""
    scale = max(
        (
            abs(float(bar[field]))
            for bar in bars
            for field in ("total", "amount")
            if _is_number(bar.get(field))
        ),
        default=1.0,
    )
    tolerance = max(scale, 1.0) * 1e-9
    for index, bar in enumerate(bars):
        here = _pointer("bars", index)
        sizes = [field for field in ("total", "amount") if field in bar]
        if not sizes:
            found.append(
                Violation(
                    here,
                    "a bar is a `total` (it stands on zero) or a signed `amount` (a step "
                    "from the running sum). Give it one.",
                )
            )
            running, previous = None, ""
            continue
        if len(sizes) == 2:
            found.append(
                Violation(
                    f"{here}/amount",
                    "a bar is a `total` or an `amount`, not both. A subtotal is a `total` "
                    "on a bar of its own.",
                )
            )
            running, previous = None, ""
            continue
        size = sizes[0]
        number = bar[size]
        if not _is_number(number):
            running, previous = None, ""
            continue
        if size == "amount":
            if index == 0:
                found.append(
                    Violation(
                        f"{here}/amount",
                        "a waterfall starts from a total the reader knows: make the first "
                        'bar `{"text": …, "total": …}`, and the steps follow it.',
                    )
                )
            if number == 0:
                found.append(
                    Violation(
                        f"{here}/amount",
                        "a step of 0 moves nothing and has no bar to draw. Leave it out, or "
                        "say it in the caption.",
                    )
                )
            if running is not None:
                running += float(number)
            previous = "amount"
            continue
        if index and previous == "total":
            found.append(
                Violation(
                    f"{here}/total",
                    "a total straight after a total repeats it: a subtotal comes after the "
                    "steps it adds up. Drop one of the two.",
                )
            )
        elif running is not None and abs(running - float(number)) > tolerance:
            difference = float(number) - running
            found.append(
                Violation(
                    f"{here}/total",
                    f"the bars before this total add up to {_figure(running)}, and it says "
                    f"{_figure(float(number))} — {_figure(abs(difference))} "
                    f"{'more' if difference > 0 else 'less'}. A total in a waterfall is the "
                    f"running sum, or the chart shows a step that is not there: fix a step or "
                    f"the total.",
                )
            )
            previous = "total"
            continue
        running = float(number)
        previous = "total"
    if bars and previous == "amount" and running is not None:
        found.append(
            Violation(
                _pointer("bars", len(bars) - 1),
                f"a waterfall ends at a total, and the steps reach {_figure(running)}. Add a "
                f'last bar: `{{"text": …, "total": {_figure(running)}}}`.',
            )
        )
    elif bars and previous == "amount":
        found.append(
            Violation(
                _pointer("bars", len(bars) - 1),
                "a waterfall ends at a total: add a last bar with a `total`.",
            )
        )
    return found


def _waterfall_document(document: Mapping[str, Any]) -> Document:
    """A waterfall: its axis label and its bars, left to right."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        waterfall_label=str(document["axis"]["label"]),
        waterfall_bars=tuple(
            WaterfallBar(
                text=bar["text"],
                total=_optional_number(bar.get("total")),
                amount=_optional_number(bar.get("amount")),
                role=bar.get("role", "step"),
            )
            for bar in document["bars"]
        ),
    )
