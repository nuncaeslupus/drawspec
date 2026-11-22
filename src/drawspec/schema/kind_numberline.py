"""The `numberline` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _is_number, _listed, _optional_number, _pointer
from drawspec.schema._constants import NUMBERLINE_TICK_MAX
from drawspec.schema._model import Document, NumberAxis, NumberPoint, NumberRange, Violation

#: Why a numberline has no place for a field an author may reach for.
NUMBERLINE_REFUSED: Final = {
    "edges": (
        "a number line joins nothing: what relates two values is where they sit on the one scale"
    ),
    "series": (
        "a number line has one scale and no data series. Two values per item is a `scatter`; "
        "a number that changes over something is a `chart`"
    ),
    "axes": "a number line has one scale, `axis`. Two values per item is a `scatter`",
    "value": "a point's place on the scale is `at`",
    "id": "nothing names a point or a range, so it takes no id",
    "date": (
        "a number line places numbers. For events in time, use a `timeline`; for a plan, a "
        "`gantt` with its axis in a unit you name"
    ),
}


#: What a numberline says to a string where a number belongs.
NUMBERLINE_NUMBERS: Final = (
    "a number line places numbers on its scale. A date or a named time is a `timeline`; "
    "a named scale with no numbers takes `axis.ends` and still places by number between "
    "`min` and `max`."
)


def _numberline_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in a numberline, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in NUMBERLINE_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {NUMBERLINE_REFUSED[name]}.")
    if name in ("at", "from", "to", "min", "max", "step"):
        value: object = document
        for part in parts[1:]:
            try:
                value = value[int(part) if isinstance(value, list) else part]  # type: ignore[index]
            except (TypeError, ValueError, IndexError, KeyError):
                return violation
        if isinstance(value, str):
            return Violation(violation.pointer, f"{value!r} is not a number: {NUMBERLINE_NUMBERS}")
    return violation


def _numberline_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A scale that runs one way, and points and ranges that sit on it.

    Every value is inside `[min, max]` — an arrow is how a range says it goes on
    — a range has at least one end and ends after it starts, an open end is an
    end that exists, two points are not one dot, and a named scale carries no
    numbers.
    """
    found: list[Violation] = []
    axis = document.get("axis")
    axis = axis if isinstance(axis, dict) else {}
    low: float | None = axis.get("min") if _is_number(axis.get("min")) else None
    high: float | None = axis.get("max") if _is_number(axis.get("max")) else None
    if low is not None and high is not None and high <= low:
        found.append(
            Violation(
                _pointer("axis", "max"),
                f"the scale ends at {high}, not after its start {low}: `max` is the right-hand "
                f"end, and more than `min`.",
            )
        )
        low = high = None
    ends = axis.get("ends")
    if isinstance(ends, list):
        if len(ends) > 2:
            found.append(
                Violation(
                    _pointer("axis", "ends"),
                    f"{len(ends)} ends: a scale has two, the low end's words then the high end's.",
                )
            )
        for name in ("step", "unit"):
            if name in axis:
                found.append(
                    Violation(
                        _pointer("axis", name),
                        f"a scale named by its `ends` draws no numbers, so it takes no "
                        f"{name!r}. Drop it, or drop the ends and number the scale.",
                    )
                )
    step: Any = axis.get("step")
    if low is not None and high is not None and _is_number(step) and step > 0:
        count = (high - low) / step
        if count > NUMBERLINE_TICK_MAX:
            found.append(
                Violation(
                    _pointer("axis", "step"),
                    f"a step of {step} cuts {low} to {high} into {count:.0f} ticks, and the "
                    f"numbers crowd past {NUMBERLINE_TICK_MAX}. Take a larger step, or a "
                    f"narrower scale.",
                )
            )

    def outside(value: Any, pointer: str) -> None:
        if not _is_number(value) or low is None or high is None:
            return
        if value < low or value > high:
            found.append(
                Violation(
                    pointer,
                    f"{value} is off the scale, which runs {low} to {high}. Widen the axis — "
                    f"or, for a range that goes on, leave this end out and it is drawn as an "
                    f"arrow.",
                )
            )

    points = _listed(document, "points")
    ranges = _listed(document, "ranges")
    if not points and not ranges:
        found.append(
            Violation(
                "/points",
                "a number line needs something on it: at least one of `points` and `ranges`. "
                "A bare scale says nothing a sentence would not.",
            )
        )
    seen: dict[float, int] = {}
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            continue
        at: Any = point.get("at")
        outside(at, _pointer("points", index, "at"))
        if _is_number(at):
            if at in seen:
                found.append(
                    Violation(
                        _pointer("points", index, "at"),
                        f"point {seen[at]} is already at {at}, and two dots at one value are "
                        f"one dot. Put both texts in one point.",
                    )
                )
            else:
                seen[at] = index
    for index, entry in enumerate(ranges):
        if not isinstance(entry, dict):
            continue
        start: Any = entry.get("from")
        end: Any = entry.get("to")
        if "from" not in entry and "to" not in entry:
            found.append(
                Violation(
                    _pointer("ranges", index),
                    "a range with neither `from` nor `to` is the whole line. Say that in the "
                    "title, or give the range an end.",
                )
            )
        for name, bound in (("from_open", "from"), ("to_open", "to")):
            if name in entry and bound not in entry:
                found.append(
                    Violation(
                        _pointer("ranges", index, name),
                        f"this range has no {bound!r}, so it runs on past the axis: an end that "
                        f"is not there cannot be open. Drop {name!r}, or give the range its "
                        f"{bound!r}.",
                    )
                )
        outside(start, _pointer("ranges", index, "from"))
        outside(end, _pointer("ranges", index, "to"))
        if _is_number(start) and _is_number(end) and end <= start:
            found.append(
                Violation(
                    _pointer("ranges", index, "to"),
                    f"the range ends at {end}, not after its start {start}. For a single value, "
                    f"use a point.",
                )
            )
    return found


def _numberline_document(document: Mapping[str, Any]) -> Document:
    """A number line: its scale, its points and its ranges in the order written."""
    axis = document["axis"]
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        number_axis=NumberAxis(
            minimum=float(axis["min"]),
            maximum=float(axis["max"]),
            step=_optional_number(axis.get("step")),
            label=str(axis.get("label", "")),
            unit=str(axis.get("unit", "")),
            ends=tuple(axis.get("ends", ())),
        ),
        number_points=tuple(
            NumberPoint(
                at=float(entry["at"]),
                text=entry.get("text", ""),
                open=bool(entry.get("open", False)),
                role=entry.get("role", "step"),
            )
            for entry in document.get("points", ())
        ),
        number_ranges=tuple(
            NumberRange(
                start=_optional_number(entry.get("from")),
                end=_optional_number(entry.get("to")),
                start_open=bool(entry.get("from_open", False)),
                end_open=bool(entry.get("to_open", False)),
                text=entry.get("text", ""),
                role=entry.get("role", "step"),
            )
            for entry in document.get("ranges", ())
        ),
    )
