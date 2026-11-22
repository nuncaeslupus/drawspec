"""The `pert` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from difflib import get_close_matches
from fractions import Fraction
from typing import Any, Final

from drawspec.schema._checks import _figure, _is_number, _listed, _optional_number, _pointer
from drawspec.schema._constants import PERT_DEPENDENCY_MAX, PERT_ESTIMATES
from drawspec.schema._model import Document, PertActivity, Violation

#: Why a pert activity is computed rather than written, said once.
_PERT_COMPUTED: Final = (
    "computed by drawspec's forward and backward pass from the durations and `after`, and "
    "drawn in the box; it is never written"
)


#: Why a pert network has no place for a field an author may reach for.
PERT_REFUSED: Final = {
    **{
        name: f"an activity's {words} is {_PERT_COMPUTED}"
        for name, words in (
            ("es", "early start"),
            ("ef", "early finish"),
            ("ls", "late start"),
            ("lf", "late finish"),
            ("start", "start"),
            ("end", "finish"),
            ("finish", "finish"),
        )
    },
    "float": f"float (slack) is {_PERT_COMPUTED}",
    "slack": f"float (slack) is {_PERT_COMPUTED}",
    "critical": (
        "the critical path is computed — every activity with no float — and drawn heavy; it "
        "is never marked by hand"
    ),
    "role": (
        "the critical path is computed and drawn heavy, and nothing else in a network is "
        "marked: an activity takes `id`, `text`, a duration and `after`"
    ),
    "lag": (
        "every dependency is finish-to-start with no lag. A wait between two activities is an "
        "activity of its own — `Concrete cures`, with its duration"
    ),
    "type": (
        "every dependency is finish-to-start: the next starts when this one finishes. Start-"
        "to-start and finish-to-finish links are not drawn"
    ),
    "before": "write each dependency once, on the later activity, as `after`",
    "successors": "write each dependency once, on the later activity, as `after`",
    "predecessors": "the activities this one waits for are `after`",
    "dependencies": "the activities this one waits for are `after`",
    "depends_on": "the activities this one waits for are `after`",
    "edges": (
        "a network's arrows are each activity's `after` list: the dependencies are written on "
        "the activities, so no arrow can name an activity that is not there"
    ),
    "nodes": "a network's boxes are its `activities`",
    "most_likely": "the most likely estimate is `likely`",
    "expected": (
        "the expected duration is computed from the three estimates, (optimistic + 4 x likely "
        "+ pessimistic) / 6. Write the three, or a plain `duration`"
    ),
}


def _pert_refusal(violation: Violation) -> Violation:
    """A structural refusal in a pert network, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in PERT_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {PERT_REFUSED[name]}.")
    if parts[1:] == ["activities"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a network needs at least 2 activities: one activity is its own critical path, "
            "which a sentence says better.",
        )
    return violation


def _pert_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a network may not be: ids that do not land, durations that are not one, a loop.

    Each activity has one duration — written, or the three PERT estimates in order —
    its `after` names other activities once each, the dependencies stay within the
    budget, and following them never comes back to where it began.
    """
    found: list[Violation] = []
    for name in ("start", "finish"):
        value = document.get(name)
        if isinstance(value, str) and not value.strip():
            found.append(
                Violation(
                    _pointer(name),
                    f"a {name} milestone needs words — `{name.capitalize()}` — or leave "
                    f"`{name}` out.",
                )
            )
    ids: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "activities")):
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id")
        if isinstance(identifier, str):
            if identifier in ids:
                found.append(
                    Violation(
                        _pointer("activities", index, "id"),
                        f"{identifier!r} is already the id of activity {ids[identifier]}: "
                        f"every activity needs its own, so `after` names one box.",
                    )
                )
            else:
                ids[identifier] = index
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(
                Violation(
                    _pointer("activities", index, "text"),
                    "an activity needs words: an empty box is a step nobody can do.",
                )
            )
        found.extend(_pert_duration_violations(entry, index))

    graph: dict[str, list[tuple[str, int]]] = {}
    count = 0
    for index, entry in enumerate(_listed(document, "activities")):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        identifier = entry["id"]
        seen: set[str] = set()
        for position, before in enumerate(_listed(entry, "after")):
            if not isinstance(before, str):
                continue
            count += 1
            here = _pointer("activities", index, "after", position)
            if before == identifier:
                found.append(Violation(here, f"{identifier!r} cannot wait for itself to finish."))
            elif before in seen:
                found.append(
                    Violation(here, f"{before!r} is already in this `after`: list it once.")
                )
            elif before not in ids:
                close = get_close_matches(before, list(ids), n=1)
                hint = f" Did you mean {close[0]!r}?" if close else ""
                found.append(
                    Violation(here, f"{before!r} names no activity in this network.{hint}")
                )
            else:
                graph.setdefault(before, []).append((identifier, position))
            seen.add(before)
    if count > PERT_DEPENDENCY_MAX:
        found.append(
            Violation(
                "/activities",
                f"{count} dependencies is past what one network can be read at — "
                f"{PERT_DEPENDENCY_MAX} at most, counted across every `after`. Split it into "
                f"an overview network of phases and a network per phase.",
            )
        )
    if found:
        return found
    looped = _pert_cycle(list(ids), graph)
    if looped:
        path, position = looped
        return [
            Violation(
                _pointer("activities", ids[path[-1]], "after", position),
                f"the dependencies go round in a circle ({' -> '.join(path)}): "
                f"{path[0]!r} would have to finish before it could start, so the network has "
                f"no schedule. Remove one of these `after` entries.",
            )
        ]
    return found


def _pert_duration_violations(entry: Mapping[str, Any], index: int) -> list[Violation]:
    """One activity's duration: written, or three PERT estimates in order; never negative."""
    given = [name for name in PERT_ESTIMATES if name in entry]
    if "duration" in entry and given:
        return [
            Violation(
                _pointer("activities", index, given[0]),
                "an activity takes a `duration` or the three PERT estimates, not both: the "
                "estimates are how the duration is found. Keep one.",
            )
        ]
    if "duration" not in entry and not given:
        return [
            Violation(
                _pointer("activities", index),
                "an activity needs a `duration`, or `optimistic`, `likely` and `pessimistic` "
                "for a PERT estimate: without one it has no place in the schedule.",
            )
        ]
    if given and len(given) < len(PERT_ESTIMATES):
        missing = [name for name in PERT_ESTIMATES if name not in entry]
        return [
            Violation(
                _pointer("activities", index, missing[0]),
                f"{missing[0]!r} is required with {', '.join(repr(name) for name in given)}: a "
                f"PERT estimate is all three, or write a plain `duration`.",
            )
        ]
    found: list[Violation] = []
    for name in ("duration", *PERT_ESTIMATES):
        value = entry.get(name)
        if not _is_number(value):
            continue
        value = float(value)  # type: ignore[arg-type]
        if not math.isfinite(value) or value < 0:
            found.append(
                Violation(
                    _pointer("activities", index, name),
                    f"{_figure(value) if math.isfinite(value) else value} is not a length of "
                    f"time: a duration is zero (a milestone) or more.",
                )
            )
    if found or not given:
        return found
    low, likely, high = (entry[name] for name in PERT_ESTIMATES)
    if not all(_is_number(value) for value in (low, likely, high)):
        return found
    if likely < low:
        found.append(
            Violation(
                _pointer("activities", index, "likely"),
                f"the likely duration {_figure(likely)} is shorter than the optimistic "
                f"{_figure(low)}: the estimates run optimistic <= likely <= pessimistic.",
            )
        )
    elif high < likely:
        found.append(
            Violation(
                _pointer("activities", index, "pessimistic"),
                f"the pessimistic duration {_figure(high)} is shorter than the likely "
                f"{_figure(likely)}: the estimates run optimistic <= likely <= pessimistic.",
            )
        )
    return found


def _pert_cycle(
    ids: Sequence[str], graph: Mapping[str, Sequence[tuple[str, int]]]
) -> tuple[list[str], int] | None:
    """The first loop in the dependencies, as a path that ends where it began.

    Returned with the position, in the last activity's `after`, of the entry that
    closes it — where the refusal points. Iterative, so a long chain cannot
    overflow the stack.
    """
    state: dict[str, int] = {}
    for root in ids:
        if root in state:
            continue
        state[root] = 1
        trail = [root]
        stack = [iter(graph.get(root, ()))]
        while stack:
            step = next(stack[-1], None)
            if step is None:
                stack.pop()
                state[trail.pop()] = 2
                continue
            later, position = step
            if state.get(later) == 1:
                begin = trail.index(later)
                return [*trail[begin:], later], position
            if later not in state:
                state[later] = 1
                trail.append(later)
                stack.append(iter(graph.get(later, ())))
    return None


def _exact(value: object) -> Fraction:
    """A validated number as an exact fraction: `0.1` is a tenth, not its float."""
    if isinstance(value, float):
        return Fraction(repr(value))
    return Fraction(int(value))  # type: ignore[call-overload]


def _pert_activity(entry: Mapping[str, Any]) -> PertActivity:
    """One activity, its duration exact: as written, or (o + 4m + p) / 6."""
    estimates: tuple[Fraction, Fraction, Fraction] | None = None
    if "duration" in entry:
        duration = _exact(entry["duration"])
    else:
        low, likely, high = (_exact(entry[name]) for name in PERT_ESTIMATES)
        estimates = (low, likely, high)
        duration = (low + 4 * likely + high) / 6
    return PertActivity(
        id=str(entry["id"]),
        text=str(entry["text"]),
        duration=duration,
        after=tuple(str(name) for name in entry.get("after", ())),
        estimates=estimates,
    )


def _pert_document(document: Mapping[str, Any]) -> Document:
    """A project network: its activities in the order written, and its milestones."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        pert_activities=tuple(_pert_activity(entry) for entry in document["activities"]),
        pert_start=str(document.get("start", "")),
        pert_finish=str(document.get("finish", "")),
    )
