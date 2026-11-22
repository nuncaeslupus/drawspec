"""The `usecase` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._constants import USECASE_COLUMN_MAX, USECASE_EDGE_ROLES
from drawspec.schema._model import (
    Document,
    UseCase,
    UsecaseActor,
    UsecaseEdge,
    UsecaseSystem,
    Violation,
)

#: Why a use case diagram has no place for a field an author may reach for.
USECASE_REFUSED: Final = {
    "text": (
        "a relation's words are its role: `include` is drawn «include» and `extend` "
        "«extend», and an association is a plain line. A condition on an extension belongs "
        "in the extending use case's own words"
    ),
    "label": (
        "a relation's words are its role: `include` is drawn «include» and `extend` "
        "«extend», and an association is a plain line"
    ),
    "side": (
        "which side an actor stands on is derived — primary actors left, supporting ones "
        "right. Say `supporting: true` for an actor who serves rather than starts the use "
        "cases"
    ),
    "x": "a use case diagram is placed by drawspec; there are no coordinates",
    "y": "a use case diagram is placed by drawspec; there are no coordinates",
    "column": (
        "a use case's column is derived: one included, extending or specialising another "
        "stands right of it"
    ),
    "role": (
        "an actor is a stick figure and a use case an ellipse, with nothing else to mark: "
        "they take `id`, `text` and `supporting` or `system` only"
    ),
    "groups": ("a use case diagram's frames are its `systems`; name each use case's `system`"),
    "nodes": (
        "a use case diagram's things are `actors` (outside the boundary) and `usecases` (inside it)"
    ),
    "multiplicity": (
        "a use case diagram's associations carry no multiplicities here; say how many in "
        "the use case's words"
    ),
}


def _usecase_refusal(violation: Violation) -> Violation:
    """A structural refusal in a use case diagram, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    if "is not a known field" in violation.message and name in USECASE_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {USECASE_REFUSED[name]}.")
    return violation


def usecase_columns(cases: Sequence[str], edges: Sequence[tuple[str, str, str]]) -> dict[str, int]:
    """Each use case's column inside its boundary, 0 at the left.

    A use case that is included, that extends another, or that specialises another
    stands one column right of the use case it is about — the longest such chain
    decides. `edges` are `(from, to, role)`; anything not between two of `cases`
    is ignored, and a loop (refused by validation) stops where it closes.
    """
    known = set(cases)
    later: dict[str, list[str]] = {name: [] for name in cases}
    for source, target, role in edges:
        if source not in known or target not in known or source == target:
            continue
        if role == "include":
            later[source].append(target)
        elif role in ("extend", "inherits"):
            later[target].append(source)
    column = dict.fromkeys(cases, 0)
    # Longest path by relaxation; bounded by the number of use cases, so a loop
    # that slipped through cannot spin forever.
    for _ in range(len(cases)):
        changed = False
        for name in cases:
            for after in later[name]:
                if column[after] < column[name] + 1:
                    column[after] = column[name] + 1
                    changed = True
        if not changed:
            break
    return column


def usecase_sides(
    actors: Sequence[tuple[str, bool | None]],
    edges: Sequence[tuple[str, str, str]],
) -> dict[str, str]:
    """Each actor's side of the boundary, `left` or `right`.

    A written `supporting` decides; an actor that inherits stands on its parent's
    side; otherwise an actor whose every use case an actor written before it
    already has is supporting — a bank behind the customer's withdrawal — and
    stands on the right. The rest are primary, on the left.
    """
    names = [name for name, _ in actors]
    known = set(names)
    parent: dict[str, str] = {}
    cases: dict[str, set[str]] = {name: set() for name in names}
    for source, target, role in edges:
        if role == "inherits" and source in known and target in known:
            parent.setdefault(source, target)
        elif role == "association":
            if source in known and target not in known:
                cases[source].add(target)
            elif target in known and source not in known:
                cases[target].add(source)
    written = dict(actors)
    side: dict[str, str] = {}

    def resolve(name: str, seen: frozenset[str]) -> str:
        if name in side:
            return side[name]
        if name in parent and parent[name] not in seen:
            side[name] = resolve(parent[name], seen | {name})
            return side[name]
        choice = written.get(name)
        if choice is None:
            before: set[str] = set()
            for earlier in names[: names.index(name)]:
                before |= cases[earlier]
            choice = bool(cases[name]) and cases[name] <= before
        side[name] = "right" if choice else "left"
        return side[name]

    for name in names:
        resolve(name, frozenset({name}))
    return side


def _usecase_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that land, relations between the right ends, no loops, the column cap."""
    found: list[Violation] = []
    owner: dict[str, str] = {}
    actors: dict[str, int] = {}
    cases: dict[str, int] = {}
    systems: dict[str, int] = {}
    for array, table in (("systems", systems), ("actors", actors), ("usecases", cases)):
        for index, entry in enumerate(_listed(document, array)):
            if not isinstance(entry, dict):
                continue
            identifier = entry.get("id")
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(
                    Violation(_pointer(array, index, "text"), "this needs words to be drawn.")
                )
            if not isinstance(identifier, str):
                continue
            if identifier in owner:
                found.append(
                    Violation(
                        _pointer(array, index, "id"),
                        f"duplicate id {identifier!r} (already used in /{owner[identifier]}): "
                        "actors, use cases and systems share one set of ids.",
                    )
                )
                continue
            owner[identifier] = f"{array}/{index}"
            table[identifier] = index

    # Each use case in a boundary, when there are boundaries.
    system_of: dict[str, str] = {}
    only = next(iter(systems)) if len(systems) == 1 else ""
    for index, entry in enumerate(_listed(document, "usecases")):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        named = entry.get("system")
        if isinstance(named, str):
            if named not in systems:
                found.append(
                    Violation(
                        _pointer("usecases", index, "system"),
                        f"{named!r} is not the id of any system" + _closest(named, systems),
                    )
                )
                continue
            system_of[entry["id"]] = named
        elif len(systems) > 1:
            found.append(
                Violation(
                    _pointer("usecases", index),
                    "with more than one system, each use case names the `system` whose "
                    "boundary it is drawn in.",
                )
            )
        else:
            system_of[entry["id"]] = only
    for identifier, index in systems.items():
        if identifier not in system_of.values():
            found.append(
                Violation(
                    _pointer("systems", index),
                    f"system {identifier!r} holds no use case, so its boundary would be an "
                    "empty box: give it a use case or leave it out.",
                )
            )

    # The relations.
    landed: list[tuple[str, str, str]] = []
    pairs: dict[frozenset[str], int] = {}
    linked: set[str] = set()
    parents: dict[str, str] = {}
    for index, entry in enumerate(_listed(document, "edges")):
        if not isinstance(entry, dict):
            continue
        role = entry.get("role", "association")
        if role not in USECASE_EDGE_ROLES:
            continue
        ends: list[str] = []
        for end in ("from", "to"):
            name = entry.get(end)
            if not isinstance(name, str):
                continue
            if name in systems:
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{name!r} is a system: a relation joins an actor or a use case, and "
                        "the boundary is drawn round its use cases.",
                    )
                )
                continue
            if name not in actors and name not in cases:
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{name!r} is not the id of any actor or use case"
                        + _closest(name, {**actors, **cases}),
                    )
                )
                continue
            ends.append(name)
        if len(ends) != 2:
            continue
        source, target = ends
        here = _pointer("edges", index)
        if source == target:
            found.append(
                Violation(here, f"a relation from {source!r} to itself says nothing: leave it out.")
            )
            continue
        pair = frozenset(ends)
        if pair in pairs:
            found.append(
                Violation(
                    here,
                    f"a second relation between {source!r} and {target!r} (the first is "
                    f"/edges/{pairs[pair]}): two things are related one way.",
                )
            )
            continue
        pairs[pair] = index
        actor_ends = [name in actors for name in ends]
        if role == "association":
            if all(actor_ends):
                found.append(
                    Violation(
                        here,
                        f"an association between two actors, {source!r} and {target!r}: actors "
                        "meet through the use cases they share. Join each to the use case, or "
                        "say one is a kind of the other with `inherits`.",
                    )
                )
                continue
            if not any(actor_ends):
                found.append(
                    Violation(
                        _pointer("edges", index, "role"),
                        f"an association between two use cases, {source!r} and {target!r}: "
                        "say how they relate — `include` (one always does the other), `extend` "
                        "(one sometimes adds to the other) or `inherits`.",
                    )
                )
                continue
        elif role in ("include", "extend"):
            if any(actor_ends):
                found.append(
                    Violation(
                        _pointer("edges", index, "role"),
                        f"`{role}` joins two use cases, and {source if actor_ends[0] else target!r}"
                        " is an actor: an actor takes part through an `association`.",
                    )
                )
                continue
        elif actor_ends[0] != actor_ends[1]:
            found.append(
                Violation(
                    _pointer("edges", index, "role"),
                    f"`inherits` says one thing is a kind of another, actor to actor or use case "
                    f"to use case — {source!r} and {target!r} are one of each.",
                )
            )
            continue
        if (
            role != "association"
            and not any(actor_ends)
            and system_of.get(source) != system_of.get(target)
        ):
            found.append(
                Violation(
                    here,
                    f"{source!r} and {target!r} are in different systems: a use case "
                    f"{role}s one in its own boundary. Move them into one system.",
                )
            )
            continue
        if role == "inherits" and all(actor_ends):
            if source in parents:
                found.append(
                    Violation(
                        here,
                        f"{source!r} already inherits from {parents[source]!r}: an actor here is a "
                        "kind of one other actor at most.",
                    )
                )
                continue
            parents[source] = target
        linked.update(ends)
        landed.append((source, target, role))

    # Actor generalisation: one level, no loop.
    for child, parent in parents.items():
        if parent in parents:
            index = next(
                i
                for i, entry in enumerate(_listed(document, "edges"))
                if isinstance(entry, dict)
                and entry.get("from") == child
                and entry.get("role") == "inherits"
            )
            found.append(
                Violation(
                    _pointer("edges", index),
                    f"{child!r} inherits from {parent!r}, which itself inherits from "
                    f"{parents[parent]!r}: one level of actor generalisation is drawn. Have "
                    f"{child!r} inherit from {parents[parent]!r} directly.",
                )
            )

    # An actor written supporting against the side its parent stands on — the
    # parent's written `supporting`, or the side derived for it.
    entries = _listed(document, "actors")
    declared: list[tuple[str, bool | None]] = []
    for name, index in actors.items():
        entry = entries[index]
        value = entry.get("supporting") if isinstance(entry, dict) else None
        declared.append((name, value if isinstance(value, bool) else None))
    resolved = usecase_sides(declared, landed)
    written_of = dict(declared)
    for child, parent in parents.items():
        written = written_of.get(child)
        if written is None:
            continue
        theirs = resolved.get(parent, "left")
        if ("right" if written else "left") != theirs:
            found.append(
                Violation(
                    _pointer("actors", actors[child], "supporting"),
                    f"{child!r} inherits from {parent!r}, which stands on the {theirs}, so it "
                    "stands there too: leave `supporting` out of it.",
                )
            )

    # No loop among the use cases, and the column cap.
    later: dict[str, set[str]] = {name: set() for name in cases}
    for source, target, role in landed:
        if source in actors or target in actors:
            continue
        first, second = (source, target) if role == "include" else (target, source)
        later[first].add(second)

    def reaches(start: str, goal: str) -> bool:
        stack, seen = [start], set()
        while stack:
            name = stack.pop()
            if name == goal:
                return True
            if name in seen:
                continue
            seen.add(name)
            stack.extend(later[name])
        return False

    looped = False
    for name in cases:
        if any(reaches(after, name) for after in later[name]):
            found.append(
                Violation(
                    _pointer("usecases", cases[name]),
                    f"the relations between use cases go round in a loop through {name!r}: "
                    "an included or extending use case is a part of another, never its whole.",
                )
            )
            looped = True
            break
    if not looped:
        columns = usecase_columns(list(cases), landed)
        for name, column in columns.items():
            if column >= USECASE_COLUMN_MAX:
                found.append(
                    Violation(
                        _pointer("usecases", cases[name]),
                        f"{name!r} is {column + 1} use cases deep in a chain of include, extend "
                        f"and inherits, and a boundary holds {USECASE_COLUMN_MAX} columns. "
                        "Fold a step into the use case it is part of, or draw it as a use case "
                        "diagram of its own.",
                    )
                )
                break

    for name, index in actors.items():
        if name not in linked:
            found.append(
                Violation(
                    _pointer("actors", index),
                    f"actor {name!r} takes part in nothing: associate it with a use case, or "
                    "leave it out.",
                )
            )
    return found


def _usecase_document(document: Mapping[str, Any]) -> Document:
    """A use case diagram: its systems, actors, use cases and relations as written."""
    systems = tuple(
        UsecaseSystem(id=entry["id"], text=entry["text"]) for entry in document.get("systems", ())
    )
    only = systems[0].id if len(systems) == 1 else ""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        usecase_systems=systems,
        usecase_actors=tuple(
            UsecaseActor(id=entry["id"], text=entry["text"], supporting=entry.get("supporting"))
            for entry in document["actors"]
        ),
        usecase_cases=tuple(
            UseCase(id=entry["id"], text=entry["text"], system=entry.get("system", only))
            for entry in document["usecases"]
        ),
        usecase_edges=tuple(
            UsecaseEdge(
                source=entry["from"], target=entry["to"], role=entry.get("role", "association")
            )
            for entry in document["edges"]
        ),
    )
