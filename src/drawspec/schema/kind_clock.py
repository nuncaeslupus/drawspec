"""The `clock` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import CLOCK_SINCE_MAX
from drawspec.schema._model import ClockFace, Document, Violation

#: Why a clock has no place for a field an author may reach for.
CLOCK_REFUSED: Final = {
    "edges": "two faces are related by `since`, which shades the time between them",
    "seconds": (
        "a teaching face has two hands, and no lesson asks a pupil to read a seconds hand: "
        "say the seconds in the `text`"
    ),
    "date": "a clock reads a time of day; dates belong on a `timeline`",
    "hands": "the hands are placed by the `time`; leave it out for a face with none",
    "hour": 'the hands are placed by the `time`: `"time": "3:15"`',
    "minute": 'the hands are placed by the `time`: `"time": "3:15"`',
    "angle": "the hands are placed by the `time`",
    "numerals": "the numerals are the sheet's, at the top: one face style per sheet",
    "readout": "the readout is the sheet's, at the top: a worksheet hides every answer",
    "label": "the words under a face are its `text`",
}


def _clock_refusal(violation: Violation) -> Violation:
    """A structural refusal on a clock sheet, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in CLOCK_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {CLOCK_REFUSED[name]}.")
    return violation


#: A clock time: one or two digits of hour, 0-23, then two of minute.
_CLOCK_TIME: Final = re.compile(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$")


def clock_minutes(text: str) -> int | None:
    """Minutes past midnight for an `H:MM` time, or None when it is not one."""
    match = _CLOCK_TIME.match(text)
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _clock_time_problem(text: Any) -> str | None:
    """Why `text` is not a clock time, or None when it is one."""
    if not isinstance(text, str):
        return None  # The structural check has already said so.
    if clock_minutes(text) is not None:
        return None
    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", text.strip()):
        return (
            f"{text!r} has seconds. A teaching face has an hour hand and a minute hand, and "
            f"no lesson asks a pupil to read a seconds hand: write `H:MM`."
        )
    if re.search(r"(?i)\d\s*[ap]\.?m\.?\s*$", text):
        return (
            f"{text!r}: a time is written on the 24-hour clock, `H:MM` — `15:15` for a quarter "
            f"past three in the afternoon. The face is the same; the readout writes it as given."
        )
    if re.search(r"\d{4}-\d{2}|T\d", text):
        return f"{text!r} carries a date. A clock reads a time of day: `H:MM`."
    return (
        f"{text!r} is not a time: write `H:MM` or `HH:MM`, from `0:00` to `23:59` — "
        f"`9:05`, `15:40`."
    )


def _clock_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Each face's times well formed, and each `since` before its time, within 12 hours."""
    found: list[Violation] = []
    for index, face in enumerate(_listed(document, "clocks")):
        if not isinstance(face, dict):
            continue
        here = _pointer("clocks", index)
        for name in ("time", "since"):
            problem = _clock_time_problem(face.get(name))
            if problem is not None:
                found.append(Violation(f"{here}/{name}", problem))
        if "since" not in face:
            continue
        if "time" not in face:
            found.append(
                Violation(
                    f"{here}/since",
                    "a face with no hands has nothing to measure from: give it a `time`, or "
                    "leave `since` out.",
                )
            )
            continue
        start, end = clock_minutes(str(face["since"])), clock_minutes(str(face["time"]))
        if start is None or end is None:
            continue
        gap = (end - start) % (24 * 60)
        if gap == 0 or gap >= CLOCK_SINCE_MAX:
            found.append(
                Violation(
                    f"{here}/since",
                    f"{face['since']!r} must be before {face['time']!r} and less than 12 hours "
                    f"before it: past that the hour hand has gone all the way round, and the "
                    f"face cannot show how long. Say a longer time in the `text`.",
                )
            )
    return found


def _clock_document(document: Mapping[str, Any]) -> Document:
    """A clock sheet: its faces, in reading order, and how each is numbered and read."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        clock_numerals=str(document.get("numerals", "arabic")),
        clock_readout=str(document.get("readout", "words")),
        clocks=tuple(
            ClockFace(
                time=str(face.get("time", "")),
                text=str(face.get("text", "")),
                since=str(face.get("since", "")),
            )
            for face in document["clocks"]
        ),
    )
