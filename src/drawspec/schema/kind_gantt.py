"""The `gantt` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import (
    _axis,
    _closest,
    _figure,
    _is_number,
    _listed,
    _optional_number,
    _pointer,
)
from drawspec.schema._constants import TASK_VALUES
from drawspec.schema._model import Document, Edge, Group, Mark, Task, TaskEvent, Violation

#: What a gantt says to a date: the owner's decision, and the two ways round it.
GANTT_NO_DATES: Final = (
    "a gantt draws no calendar, so a place on its axis is a number in a unit the axis names — "
    'with `"axis": {"label": "Week"}`, week 3 is 3. For a plan by month or sprint, name '
    "the periods in `axis.categories` and count them: the first runs from 1 to 2."
)


def _gantt_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in a gantt, told what this kind means by it.

    A string where a task's place belongs is almost always a date, and the generic
    "expected number" says nothing about why one is not accepted. `progress` is
    refused by name for the reason the proposal gives.
    """
    parts = violation.pointer.split("/")
    if len(parts) == 4 and parts[1] in ("tasks", "marks"):
        name = parts[3]
        try:
            value = document[parts[1]][int(parts[2])][name]
        except (TypeError, ValueError, IndexError, KeyError):
            value = None
        if name in TASK_VALUES and isinstance(value, str):
            return Violation(violation.pointer, f"{value!r} is not a number: {GANTT_NO_DATES}")
        if parts[1] == "tasks" and name in ("progress", "complete", "percent"):
            return Violation(
                violation.pointer,
                f"{name!r} is not a field: how much of a task is complete is `done`, a "
                f"number from 0 to 100, drawn as a band inside the bar.",
            )
    return violation


def _row_marks_violations(
    task: Mapping[str, Any], index: int, span: tuple[float, float] | None
) -> list[Violation]:
    """A task's `events` and `iterations`: on an interval, inside it, cycles in order.

    A milestone is a moment, so nothing falls inside it and nothing goes round
    it. An event or a cycle outside the bar would claim a delivery the task does
    not cover. Cycles are written in order and may touch, end to start, as one
    iteration hands on to the next; overlapping, two arcs would be drawn over
    one stretch of bar and the reader could not tell which return is which.
    """
    found: list[Violation] = []
    present = [name for name in ("events", "iterations") if task.get(name)]
    if "at" in task:
        for name in present:
            found.append(
                Violation(
                    _pointer("tasks", index, name),
                    f"a milestone is a moment, so nothing falls inside it and it has no "
                    f"{name}. Make the task an interval with `start` and `end`, or put each "
                    f"event on the task it belongs to.",
                )
            )
        return found
    if span is None or span[0] == span[1]:
        return found
    low, high = span

    def within(value: Any, pointer: str) -> bool:
        if not _is_number(value):
            return False
        if low <= value <= high:
            return True
        found.append(
            Violation(
                pointer,
                f"{_figure(value)} is outside this task, which runs {_figure(low)} to "
                f"{_figure(high)}: it would be drawn off its bar. Move it, or widen the task.",
            )
        )
        return False

    for position, event in enumerate(_listed(task, "events")):
        if isinstance(event, dict):
            within(event.get("at"), _pointer("tasks", index, "events", position, "at"))
    previous: float | None = None
    for position, cycle in enumerate(_listed(task, "iterations")):
        if not isinstance(cycle, dict):
            continue
        here = _pointer("tasks", index, "iterations", position)
        sound = within(cycle.get("start"), f"{here}/start") & within(
            cycle.get("end"), f"{here}/end"
        )
        if not sound:
            continue
        start, end = float(cycle["start"]), float(cycle["end"])
        if end <= start:
            found.append(
                Violation(
                    f"{here}/end",
                    f"this iteration ends at {_figure(end)}, which is not after it starts at "
                    f"{_figure(start)}. An iteration runs forward and its arc turns back.",
                )
            )
            continue
        if previous is not None and start < previous:
            found.append(
                Violation(
                    f"{here}/start",
                    f"this iteration starts at {_figure(start)}, before the one written "
                    f"before it ends at {_figure(previous)}. Iterations follow one another: "
                    f"write them in order, each starting where or after the last ends.",
                )
            )
        previous = end
    return found


def _gantt_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a plan may not be: tasks that are not one thing, and claims that cannot hold.

    Each task is a milestone or an interval, ends after it starts, and sits on the
    axis; ids land; a dependency's task does not start before the one it waits
    for ends; a phase is a run of consecutive tasks, and with phases every task
    is in one.
    """
    found: list[Violation] = []
    axis = document.get("axis")
    axis = axis if isinstance(axis, dict) else {}
    low, high = axis.get("min"), axis.get("max")
    low = low if _is_number(low) else None
    high = high if _is_number(high) else None
    categories = axis.get("categories")
    if isinstance(categories, list) and categories:
        for name in ("min", "max"):
            if name in axis:
                found.append(
                    Violation(
                        _pointer("axis", name),
                        f"with categories the axis runs from 1 to {len(categories) + 1}, one "
                        f"period each, so it takes no {name!r}. Drop it, or drop the categories "
                        f"and number the axis.",
                    )
                )
        low, high = 1, len(categories) + 1
    elif low is not None and high is not None and high <= low:
        found.append(
            Violation(
                _pointer("axis", "max"), f"the axis ends at {high}, not after its start {low}"
            )
        )
        low = high = None

    remedy = "add periods to the categories" if categories else "widen the axis"

    def outside(value: float, pointer: str) -> None:
        if (low is not None and value < low) or (high is not None and value > high):
            span = f"{'…' if low is None else low} to {'…' if high is None else high}"
            found.append(
                Violation(
                    pointer,
                    f"{value} is off the axis, which runs {span}: it would be drawn off the "
                    f"plot. Fix the value or {remedy}.",
                )
            )

    tasks: dict[str, tuple[float, float] | None] = {}
    order: dict[str, int] = {}
    for index, task in enumerate(_listed(document, "tasks")):
        if not isinstance(task, dict):
            continue
        identifier = task.get("id")
        here = _pointer("tasks", index)
        values = {name: task[name] for name in TASK_VALUES if _is_number(task.get(name))}
        given = {name for name in TASK_VALUES if name in task}
        span: tuple[float, float] | None = None
        done = float(task["done"]) if _is_number(task.get("done")) else None
        if done is not None and not 0 <= done <= 100:
            found.append(
                Violation(
                    _pointer("tasks", index, "done"),
                    f"{_figure(done)} is not a share of a task: `done` runs from 0 (not "
                    f"started) to 100 (finished).",
                )
            )
        elif "done" in task and "at" in given:
            found.append(
                Violation(
                    _pointer("tasks", index, "done"),
                    "a milestone is a moment, so it is reached or not and has no part done. "
                    "Drop `done`, or make the task an interval with `start` and `end`.",
                )
            )
        if "at" in given and given & {"start", "end"}:
            found.append(
                Violation(
                    _pointer("tasks", index, "at"),
                    "a task is a milestone (`at`) or an interval (`start` and `end`), not both. "
                    "For a step that ends in a milestone, write the two as two tasks.",
                )
            )
        elif "at" in given:
            if "at" in values:
                span = (values["at"], values["at"])
        elif not given:
            found.append(
                Violation(
                    here,
                    "a task needs `start` and `end` (an interval) or `at` (a milestone); it has "
                    "no place on the axis.",
                )
            )
        elif given != {"start", "end"}:
            missing = ({"start", "end"} - given).pop()
            found.append(
                Violation(
                    _pointer("tasks", index, missing),
                    f"{missing!r} is required with {({'start', 'end'} - {missing}).pop()!r}: "
                    f"an interval has two ends. For a point in time, write `at` alone.",
                )
            )
        elif "start" in values and "end" in values:
            if values["end"] <= values["start"]:
                found.append(
                    Violation(
                        _pointer("tasks", index, "end"),
                        f"this task ends at {values['end']}, which is not after it starts at "
                        f"{values['start']}. For a point in time, write `at` instead.",
                    )
                )
            else:
                span = (values["start"], values["end"])
        for name, value in values.items():
            outside(value, _pointer("tasks", index, name))
        found.extend(_row_marks_violations(task, index, span))
        text = task.get("text")
        if isinstance(task.get("actor"), str) and isinstance(text, str) and "\n" in text:
            found.append(
                Violation(
                    _pointer("tasks", index, "text"),
                    "a task with an actor has the actor as its label's lead, so its text may "
                    "not start a second paragraph. Put it on one line.",
                )
            )
        if not isinstance(identifier, str):
            continue
        if identifier in tasks:
            found.append(
                Violation(_pointer("tasks", index, "id"), f"duplicate task id {identifier!r}")
            )
            continue
        tasks[identifier] = span
        order[identifier] = index

    for index, mark in enumerate(_listed(document, "marks")):
        if isinstance(mark, dict) and _is_number(mark.get("at")):
            outside(mark["at"], _pointer("marks", index, "at"))

    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        ends = {name: edge.get(name) for name in ("from", "to")}
        sound = True
        for name, target in ends.items():
            if isinstance(target, str) and target not in tasks:
                found.append(
                    Violation(
                        _pointer("edges", index, name),
                        f"{target!r} is not the id of any task in this document"
                        + _closest(target, tasks),
                    )
                )
                sound = False
        source, target = ends["from"], ends["to"]
        if not (sound and isinstance(source, str) and isinstance(target, str)):
            continue
        if source == target:
            found.append(Violation(_pointer("edges", index, "to"), "a task cannot wait for itself"))
            continue
        before, after = tasks[source], tasks[target]
        if before is not None and after is not None and after[0] < before[1]:
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    f"{target!r} starts at {after[0]}, before {source!r} ends at {before[1]}, "
                    f"and a dependency says it cannot start until then. Either the plan or "
                    f"the dependency is wrong; only you know which.",
                )
            )

    groups = _listed(document, "groups")
    owner: dict[str, str] = {}
    group_ids: set[str] = set()
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        identifier = group.get("id")
        if isinstance(identifier, str):
            if identifier in tasks:
                found.append(
                    Violation(
                        _pointer("groups", index, "id"), f"{identifier!r} is already a task's id"
                    )
                )
            elif identifier in group_ids:
                found.append(
                    Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
                )
            group_ids.add(identifier)
        if "text" not in group:
            found.append(
                Violation(
                    _pointer("groups", index, "text"),
                    "a phase is drawn as its name over its tasks, so it needs `text`",
                )
            )
        members = group.get("members")
        if not isinstance(members, list):
            continue
        rows: list[int] = []
        sound = True
        for position, member in enumerate(members):
            if not isinstance(member, str):
                sound = False
                continue
            pointer = _pointer("groups", index, "members", position)
            if member not in tasks:
                found.append(Violation(pointer, f"{member!r} is not the id of any task"))
                sound = False
            elif member in owner:
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is already in {owner[member]!r}. A task is in one phase.",
                    )
                )
                sound = False
            else:
                owner[member] = str(identifier)
                rows.append(order[member])
        if not sound or not rows:
            continue
        names = {row: name for name, row in order.items()}
        between = [names[row] for row in range(min(rows), max(rows) + 1) if row not in rows]
        if between:
            found.append(
                Violation(
                    _pointer("groups", index, "members"),
                    f"{between[0]!r} stands between members of {identifier!r} in 'tasks', so "
                    f"the phase would take in a row that is not in it. Reorder 'tasks' so a "
                    f"phase's tasks are next to each other.",
                )
            )
    if groups:
        for identifier, index in order.items():
            if identifier not in owner:
                found.append(
                    Violation(
                        _pointer("tasks", index),
                        f"{identifier!r} is in no phase, and with phases its row would read as "
                        f"part of the one above it. Put it in a group, or drop 'groups'.",
                    )
                )
    return found


def _gantt_document(document: Mapping[str, Any]) -> Document:
    """A plan: its axis, its tasks in order, phases, dependencies and marks."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        axes=(_axis(document["axis"]),),
        tasks=tuple(
            Task(
                id=entry["id"],
                text=entry["text"],
                start=float(entry.get("start", 0.0)),
                end=float(entry.get("end", 0.0)),
                at=_optional_number(entry.get("at")),
                role=entry.get("role", "step"),
                actor=entry.get("actor", ""),
                done=_optional_number(entry.get("done")),
                events=tuple(
                    TaskEvent(at=float(event["at"]), text=event.get("text", ""))
                    for event in entry.get("events", ())
                ),
                iterations=tuple(
                    (float(cycle["start"]), float(cycle["end"]))
                    for cycle in entry.get("iterations", ())
                ),
            )
            for entry in document["tasks"]
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
        edges=tuple(
            Edge(source=entry["from"], target=entry["to"], role=entry.get("role", "flow"))
            for entry in document.get("edges", ())
        ),
        marks=tuple(
            Mark(text=entry["text"], at=float(entry["at"])) for entry in document.get("marks", ())
        ),
    )
