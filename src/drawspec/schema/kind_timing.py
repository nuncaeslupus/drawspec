"""The `timing` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _figure, _listed, _optional_number, _pointer
from drawspec.schema._constants import TIMING_BIT_VALUES, TIMING_HOLD, TIMING_STEP_MAX
from drawspec.schema._model import Document, TimingInterval, TimingMarker, TimingSignal, Violation

#: Why a timing figure has no place for a field an author may reach for.
TIMING_REFUSED: Final = {
    "wave": (
        'the values are an array, one string per step — `["p", ".", ".", "0"]` — '
        "so a wrong one is pointed at by its step. Write them in `values`"
    ),
    "data": "a bus's words are its values: write each word in `values` at the step it starts",
    "period": (
        "time is counted in equal steps, so a clock is a `p` per step (or `p` then `.`): "
        "there is no period to write"
    ),
    "time": (
        "time is counted in steps, not seconds: the steps are not to scale. Name them with "
        "`ticks`, and name a measured span with an `intervals` entry"
    ),
    "duration": (
        "a span is named, not measured: write it as an `intervals` entry from one edge to another"
    ),
    "scale": "every step is the same width, decided by the canvas; there is no scale to set",
    "edges": (
        "a named span between two edges is an `intervals` entry; a line across every lane is a "
        "`markers` entry. An arrow from one edge to an edge on another signal is not drawn"
    ),
    "edge": (
        "a named span between two edges is an `intervals` entry; a line across every lane is a "
        "`markers` entry. An arrow from one edge to an edge on another signal is not drawn"
    ),
    "role": (
        "a lane is told by what it draws, its `lane`: `bit`, `bus` or `state`. There is no "
        "emphasis to mark"
    ),
    "type": "what a lane draws is its `lane`: `bit`, `bus` or `state`",
    "id": "a signal is named by its `text`, which an interval refers to",
    "name": "a signal's name is its `text`",
}


def _timing_refusal(violation: Violation) -> Violation:
    """A structural refusal in a timing figure, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in TIMING_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {TIMING_REFUSED[name]}.")
    if (
        len(parts) == 5
        and parts[1] == "signals"
        and parts[3] == "values"
        and "expected string" in violation.message
    ):
        return Violation(
            violation.pointer,
            'a value is a string, one per step: write a level as `"0"` or `"1"`, in quotes, '
            "and a word on a bus as its text.",
        )
    return violation


def _timing_edge_problem(value: object, steps: int) -> str | None:
    """Why `value` is not an edge on a `steps`-step axis, or None when it is one."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None  # the structural pass has said so
    if not math.isfinite(value):
        return (
            f"{value!r} is not a number of steps: an edge is from 0 (the left edge) to "
            f"{steps} (the right), whole or half."
        )
    if value < 0 or value > steps:
        return (
            f"{_figure(float(value))} is off the axis: an edge is from 0 (the left edge) to "
            f"{steps} (the right), in steps."
        )
    if not (float(value) * 2).is_integer():
        return (
            f"{_figure(float(value))} falls inside a step: an edge is a whole step (between "
            f"two) or a half (where a clock pulse falls)."
        )
    return None


def _timing_states(here: str, states: object, found: list[Violation]) -> list[str]:
    """A state lane's named states, each checked: named, once, and not `.`."""
    names: list[str] = []
    if not isinstance(states, list):
        return names
    for position, state in enumerate(states):
        if not isinstance(state, str):
            continue
        where = f"{here}/states/{position}"
        if not state.strip():
            found.append(Violation(where, "a state needs a name."))
        elif state in names:
            found.append(Violation(where, f"{state!r} is written twice: each state is one level."))
        elif state == TIMING_HOLD:
            found.append(Violation(where, "`.` carries a step on, so it cannot name a state."))
        else:
            names.append(state)
    return names


def _timing_values(
    here: str, lane: object, values: list[Any], states: list[str] | None, found: list[Violation]
) -> None:
    """Every value of one lane: one its lane can draw, and no `.` with nothing before it."""
    if len(values) > TIMING_STEP_MAX:
        found.append(
            Violation(
                f"{here}/values/{TIMING_STEP_MAX}",
                f"{len(values)} steps is past what one timing figure can be read at — "
                f"{TIMING_STEP_MAX} at most. Draw the part the figure is about, and leave "
                f"the idle time out.",
            )
        )
    for step, value in enumerate(values):
        if not isinstance(value, str):
            continue
        where = f"{here}/values/{step}"
        if value == TIMING_HOLD:
            if step == 0:
                found.append(
                    Violation(
                        where,
                        "`.` carries the step before on, and the first step has none: start "
                        "with a value.",
                    )
                )
            continue
        if lane == "bit" and value not in TIMING_BIT_VALUES:
            found.append(
                Violation(
                    where,
                    f"{value!r} is not a level. A `bit` lane takes `0`, `1`, `z` (high "
                    f"impedance), `x` (unknown), `p` and `n` (clock pulses) and `.` (as "
                    f"before); for a word per step, set `lane` to `bus`.",
                )
            )
        elif lane == "bus" and not value.strip():
            found.append(
                Violation(
                    where,
                    "an empty word is not a value: write `x` for unknown, `z` for high "
                    "impedance, or `.` to hold the word before.",
                )
            )
        elif lane == "state" and states is not None and value not in states:
            found.append(
                Violation(
                    where,
                    f"{value!r} is not one of this lane's states "
                    f"({', '.join(states) or 'none'}); add it to `states`, or write `.` to "
                    f"stay in the state before.",
                )
            )


def _timing_signal(
    index: int,
    signal: Mapping[str, Any],
    names: dict[str, int],
    groups: dict[str, int],
    previous_group: str | None,
    found: list[Violation],
) -> str | None:
    """One signal's name, lane, states, group and values; its group, for the next."""
    here = _pointer("signals", index)
    text = signal.get("text")
    if isinstance(text, str):
        if not text.strip():
            found.append(Violation(f"{here}/text", "a signal needs a name: its lane is blank."))
        elif text in names:
            found.append(
                Violation(
                    f"{here}/text",
                    f"{text!r} names signal {names[text]} already: an interval refers to a "
                    f"signal by its name, so each is written once.",
                )
            )
        else:
            names[text] = index
    lane = signal.get("lane", "bit")
    if lane == "state" and "states" not in signal:
        found.append(
            Violation(
                f"{here}/states",
                "a `state` lane needs its `states`, top to bottom: the levels its line steps "
                "between.",
            )
        )
    if lane != "state" and "states" in signal:
        found.append(
            Violation(
                f"{here}/states",
                f"a {lane!r} lane has no named states: its levels are fixed. Set `lane` to "
                f"`state` to draw a line between named levels.",
            )
        )
    states = _timing_states(here, signal.get("states"), found)
    group = signal.get("group")
    if isinstance(group, str):
        if not group.strip():
            found.append(Violation(f"{here}/group", "a group needs a name, or leave `group` out."))
        elif group in groups and previous_group != group:
            found.append(
                Violation(
                    f"{here}/group",
                    f"the group {group!r} began at signal {groups[group]} and was left: write "
                    f"a group's signals next to each other, so it is drawn once.",
                )
            )
        else:
            groups.setdefault(group, index)
    values = signal.get("values")
    if isinstance(values, list):
        _timing_values(
            here, lane, values, states if isinstance(signal.get("states"), list) else None, found
        )
    return group if isinstance(group, str) else None


def _timing_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Every value a lane can draw, every lane one length, and every reference found."""
    found: list[Violation] = []
    names: dict[str, int] = {}
    groups: dict[str, int] = {}
    lengths: list[tuple[int, int]] = []
    previous_group: str | None = None
    for index, signal in enumerate(_listed(document, "signals")):
        if not isinstance(signal, dict):
            continue
        previous_group = _timing_signal(index, signal, names, groups, previous_group, found)
        if isinstance(signal.get("values"), list):
            lengths.append((index, len(signal["values"])))
    if not lengths:
        return found
    first, steps = lengths[0]
    for index, length in lengths[1:]:
        if length != steps:
            found.append(
                Violation(
                    _pointer("signals", index, "values"),
                    f"{length} steps, where signal {first} has {steps}: every lane runs the "
                    f"whole axis, one value per step. Pad the shorter with `.` or `x`.",
                )
            )
    ticks = document.get("ticks")
    if isinstance(ticks, list) and len(ticks) != steps:
        found.append(
            Violation(
                "/ticks",
                f"{len(ticks)} ticks for {steps} steps: name each step once, an empty string "
                f"for a step left unnamed.",
            )
        )
    for index, marker in enumerate(_listed(document, "markers")):
        if not isinstance(marker, dict):
            continue
        problem = _timing_edge_problem(marker.get("at"), steps)
        if problem:
            found.append(Violation(_pointer("markers", index, "at"), problem))
        text = marker.get("text")
        if isinstance(text, str) and text and not text.strip():
            found.append(
                Violation(_pointer("markers", index, "text"), "a blank name: leave `text` out.")
            )
    for index, interval in enumerate(_listed(document, "intervals")):
        if isinstance(interval, dict):
            found.extend(_timing_interval(index, interval, steps, names))
    return found


def _timing_interval(
    index: int, interval: Mapping[str, Any], steps: int, names: Mapping[str, int]
) -> list[Violation]:
    """One interval: both edges on the axis, running forward, named, on a signal there is."""
    found: list[Violation] = []
    for end in ("from", "to"):
        problem = _timing_edge_problem(interval.get(end), steps)
        if problem:
            found.append(Violation(_pointer("intervals", index, end), problem))
    start, stop = interval.get("from"), interval.get("to")
    numbers = all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in (start, stop)
    )
    if numbers and float(stop) <= float(start):  # type: ignore[arg-type]
        found.append(
            Violation(
                _pointer("intervals", index, "to"),
                f"an interval runs forward: `to` ({_figure(float(stop))}) must be after "  # type: ignore[arg-type]
                f"`from` ({_figure(float(start))}).",  # type: ignore[arg-type]
            )
        )
    text = interval.get("text")
    if isinstance(text, str) and not text.strip():
        found.append(Violation(_pointer("intervals", index, "text"), "an interval needs a name."))
    signal = interval.get("signal")
    if isinstance(signal, str) and signal not in names:
        found.append(
            Violation(
                _pointer("intervals", index, "signal"),
                f"{signal!r} is not a signal here; the signals are "
                f"{', '.join(repr(name) for name in names) or 'none'}.",
            )
        )
    return found


def _timing_document(document: Mapping[str, Any]) -> Document:
    """A timing figure: its lanes, step names, markers and intervals, as written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        timing_signals=tuple(
            TimingSignal(
                text=str(signal["text"]),
                lane=str(signal.get("lane", "bit")),
                values=tuple(str(value) for value in signal["values"]),
                states=tuple(str(state) for state in signal.get("states", ())),
                group=str(signal.get("group", "")),
            )
            for signal in document["signals"]
        ),
        timing_ticks=tuple(str(tick) for tick in document.get("ticks", ())),
        timing_markers=tuple(
            TimingMarker(at=float(marker["at"]), text=str(marker.get("text", "")))
            for marker in document.get("markers", ())
        ),
        timing_intervals=tuple(
            TimingInterval(
                start=float(interval["from"]),
                end=float(interval["to"]),
                text=str(interval["text"]),
                signal=str(interval.get("signal", "")),
            )
            for interval in document.get("intervals", ())
        ),
    )
