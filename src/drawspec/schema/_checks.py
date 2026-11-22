"""The shared checks: field-level validation and the helpers the kinds build on."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence, Set
from difflib import get_close_matches
from typing import Any, Final, cast

from drawspec.filetree import Entry
from drawspec.schema._constants import (
    AXIS_ORDER,
    HUB_EDGE_ROLES,
    HUB_MINIMUM_NODES,
    LOOP_TYPES,
    POLARITY_EDGE_ROLES,
    REJECTED_FIELDS,
    SHAPED_ROLES,
    UNCLASSED_ROLES,
)
from drawspec.schema._fields import OBJECTS, FieldSpec
from drawspec.schema._model import Axis, Item, Node, NodeClass, Violation
from drawspec.theme import RAMP_STEPS


def _escape(part: object) -> str:
    """One JSON pointer token, escaped as RFC 6901 requires."""
    return str(part).replace("~", "~0").replace("/", "~1")


def _pointer(*parts: object) -> str:
    """A JSON pointer, with the escaping RFC 6901 asks for."""
    return "".join("/" + _escape(part) for part in parts if part != "")


def _unknown_field_message(name: str, legal: Sequence[str]) -> str:
    reason = REJECTED_FIELDS.get(name)
    if reason:
        return (
            f"{name!r} is not a field an author may write: {reason}. Every decision "
            f"that requires seeing the output is taken by drawspec."
        )
    return (
        f"{name!r} is not a known field here. Known fields: {', '.join(sorted(legal))}."
        f"{_did_you_mean(name, legal) if isinstance(name, str) else ''}"
    )


_JSON_TYPES: Final[dict[str, type | tuple[type, ...]]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_type(value: object, spec: FieldSpec, pointer: str, found: list[Violation]) -> bool:
    expected = _JSON_TYPES[spec.kind]
    # `True` is an `int` in Python but not a number in JSON, and a document that
    # says `width = true` should hear about it.
    if isinstance(value, bool) is not (spec.kind == "boolean"):
        found.append(Violation(pointer, f"expected {spec.kind}, got {type(value).__name__}"))
        return False
    if not isinstance(value, expected):
        found.append(Violation(pointer, f"expected {spec.kind}, got {type(value).__name__}"))
        return False
    return True


#: The largest magnitude a number field may carry. Far past any drawing, and far
#: inside what a float can multiply by a scale without overflowing to `inf`.
MAX_NUMBER: Final = 1e12


#: What XML 1.0 forbids in a document: control characters other than tab, newline
#: and carriage return, lone surrogates (what a truncated `\\ud83d` decodes to),
#: and U+FFFE / U+FFFF. Escaping does not remove them, so they must not reach the SVG.
_NOT_XML_CHAR: Final = re.compile("[^\t\n\r\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _check_number(value: Any, pointer: str, found: list[Violation]) -> None:
    """Refuse `NaN`, `Infinity` and `1e400` (which JSON parses to inf), and the absurdly large."""
    # Not `math.isfinite`: it raises OverflowError on an int past float range.
    if value != value or abs(value) > MAX_NUMBER:
        found.append(
            Violation(pointer, f"must be a finite number no larger than {MAX_NUMBER:g} in size")
        )


#: The longest any one string in a document may be, in characters. A starting value,
#: about ten times the longest label in the reference documents: wrapping and fitting
#: a label costs milliseconds per word, so an unbounded string is a way to hold a
#: server for minutes. A label this long belongs in the prose around the drawing.
MAX_TEXT_LENGTH: Final = 2000


def _check_string(value: str, pointer: str, found: list[Violation]) -> None:
    """Refuse a string past `MAX_TEXT_LENGTH`, and characters XML 1.0 cannot carry."""
    if len(value) > MAX_TEXT_LENGTH:
        found.append(
            Violation(
                pointer,
                f"is {len(value)} characters, more than the {MAX_TEXT_LENGTH} a text may have. "
                "Shorten it; a label this long belongs in the prose around the diagram.",
            )
        )
        return
    bad = _NOT_XML_CHAR.search(value)
    if bad:
        found.append(
            Violation(
                pointer,
                f"contains U+{ord(bad.group(0)):04X}, which XML cannot carry. Remove it "
                f"(a control character pasted from a terminal, or half an emoji).",
            )
        )


def _check_field(value: object, spec: FieldSpec, pointer: str, found: list[Violation]) -> None:
    if not _check_type(value, spec, pointer, found):
        return

    if spec.kind in ("number", "integer"):
        _check_number(value, pointer, found)
    if spec.kind == "string":
        _check_string(value, pointer, found)  # type: ignore[arg-type]

    if spec.enum and value not in spec.enum:
        found.append(
            Violation(
                pointer,
                f"{value!r} is not one of {', '.join(spec.enum)}. The vocabulary is "
                f"closed, so a role the theme does not declare cannot be named.",
            )
        )
    if spec.exclusive_minimum is not None and value <= spec.exclusive_minimum:  # type: ignore[operator]
        found.append(Violation(pointer, f"must be greater than {spec.exclusive_minimum}"))

    if spec.kind == "object" and spec.ref:
        _check_object(value, OBJECTS[spec.ref], pointer, found)  # type: ignore[arg-type]

    if spec.kind == "array":
        elements: list[Any] = value  # type: ignore[assignment]
        if len(elements) < spec.min_items:
            found.append(
                Violation(
                    pointer,
                    f"needs at least {spec.min_items} entr"
                    f"{'y' if spec.min_items == 1 else 'ies'}, got {len(elements)}",
                )
            )
        for index, element in enumerate(elements):
            where = f"{pointer}/{index}"
            if spec.item_ref:
                if not isinstance(element, dict):
                    found.append(Violation(where, f"expected object, got {type(element).__name__}"))
                    continue
                _check_object(element, OBJECTS[spec.item_ref], where, found)
            elif spec.item_kind == "string" and not isinstance(element, str):
                found.append(Violation(where, f"expected string, got {type(element).__name__}"))
            elif spec.item_kind == "string":
                _check_string(element, where, found)
            elif spec.item_kind == "point":
                _check_point(element, where, found)


def _check_point(element: object, pointer: str, found: list[Violation]) -> None:
    numbers = (
        isinstance(element, list)
        and len(element) == 2
        and all(isinstance(value, int | float) and not isinstance(value, bool) for value in element)
    )
    if not numbers:
        found.append(Violation(pointer, "expected a pair of numbers, [x, y]"))
        return
    for index, value in enumerate(cast(list[Any], element)):
        _check_number(value, f"{pointer}/{index}", found)


def _check_object(
    mapping: Mapping[str, Any],
    specs: Sequence[FieldSpec],
    pointer: str,
    found: list[Violation],
) -> None:
    legal = {spec.name for spec in specs}
    for name in sorted(set(mapping) - legal):
        found.append(
            Violation(f"{pointer}/{_escape(name)}", _unknown_field_message(name, sorted(legal)))
        )
    for spec in specs:
        if spec.name not in mapping:
            if spec.required:
                found.append(
                    Violation(
                        f"{pointer}/{_escape(spec.name)}",
                        spec.missing or f"{spec.name!r} is required",
                    )
                )
            continue
        _check_field(mapping[spec.name], spec, f"{pointer}/{_escape(spec.name)}", found)


#: The most self-loops one box may carry: one on each side across the reading
#: direction. Mirrors `drawspec.routing.MAX_LOOPS`, which the drawing obeys.
MAX_SELF_LOOPS: Final = 2


def _loop_violations(edges: Sequence[Any], groups: Set[str], name: str) -> list[Violation]:
    """Self-loops drawspec has nowhere to draw: on a group, or a third on one box.

    A loop leaves a box and comes back to the same side; a frame has a border
    other edges cross on their way in, and a loop on it would read as one of
    them. A box has two sides across the reading direction, so two loops.
    """
    found: list[Violation] = []
    counted: dict[str, int] = {}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if not isinstance(source, str) or source != target:
            continue
        if source in groups:
            found.append(
                Violation(
                    _pointer(name, index, "to"),
                    f"{source!r} is a group, and a loop from a group back to itself has no box "
                    f"to loop on. Draw it on the member it starts from.",
                )
            )
            continue
        counted[source] = counted.get(source, 0) + 1
        if counted[source] > MAX_SELF_LOOPS:
            found.append(
                Violation(
                    _pointer(name, index, "to"),
                    f"{source!r} already loops back to itself {MAX_SELF_LOOPS} times, one on "
                    f"each side of its box. Join these into one label, or split the state.",
                )
            )
    return found


def _figure(value: float) -> str:
    """A number as an author wrote it: no float noise, no trailing zeros."""
    text = f"{round(value, 9):.9f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _reaches(graph: Mapping[str, Sequence[str]], start: str, goal: str) -> bool:
    """Whether `goal` is reachable from `start` along `graph`'s edges."""
    seen: set[str] = set()
    stack = [start]
    while stack:
        here = stack.pop()
        if here == goal:
            return True
        if here in seen:
            continue
        seen.add(here)
        stack.extend(graph.get(here, ()))
    return False


def _did_you_mean(name: str, known: Iterable[str]) -> str:
    """` Did you mean 'x'?` as a closing sentence, for a name that is no known one."""
    close = get_close_matches(name, list(known), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def _closest(name: str, known: Mapping[str, Any]) -> str:
    """`; did you mean 'x'?` when one known id is close to `name`, else nothing."""
    close = get_close_matches(name, list(known), n=1)
    return f"; did you mean {close[0]!r}?" if close else ""


def _listed(document: Mapping[str, Any], name: str) -> list[Any]:
    value = document.get(name)
    return value if isinstance(value, list) else []


def _causal_violations(document: Mapping[str, Any], kind: str, nodes: set[str]) -> list[Violation]:
    """A causal loop diagram's signs, delays and loops: whole, causal and checked.

    Signs go on every causal edge or none — a half-signed diagram is ambiguous —
    and only on a `flow`. A loop runs along signed edges in the order written,
    and a type the author states is checked against the signs: an even number of
    negative links reinforces, an odd number balances.
    """
    found: list[Violation] = []
    edges = [edge for edge in _listed(document, "edges") if isinstance(edge, dict)]
    if kind != "flow":
        for index, edge in enumerate(_listed(document, "edges")):
            for name in ("polarity", "delay"):
                if isinstance(edge, dict) and name in edge:
                    found.append(
                        Violation(
                            _pointer("edges", index, name),
                            f"{name!r} marks a causal link, and a causal loop diagram is a "
                            f"`flow`: draw it as one.",
                        )
                    )
        return found
    signed = any("polarity" in edge for edge in edges)
    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        role = edge.get("role", "flow")
        if "polarity" in edge and role not in POLARITY_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index, "polarity"),
                    f"a {role!r} edge has no causal direction, so it has no sign. Make it a "
                    f"'flow' edge, or drop the sign.",
                )
            )
        elif signed and "polarity" not in edge and role in POLARITY_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index),
                    "this link has no 'polarity' and others do: a half-signed causal diagram "
                    "is ambiguous. Give every causal link its sign, '+' or '-'.",
                )
            )
        if edge.get("delay") and "polarity" not in edge:
            found.append(
                Violation(
                    _pointer("edges", index, "delay"),
                    "a delay belongs to a causal link: give this edge its 'polarity' too.",
                )
            )
    loops = _listed(document, "loops")
    if loops and not signed:
        found.append(
            Violation(
                "/loops",
                "a loop's type is counted from its links' signs, and no edge has a "
                "'polarity'. Give every causal link its sign, '+' or '-'.",
            )
        )
        return found
    polarity: dict[tuple[str, str], str] = {}
    for edge in edges:
        if isinstance(edge.get("from"), str) and isinstance(edge.get("to"), str):
            polarity.setdefault((edge["from"], edge["to"]), edge.get("polarity", ""))
    rings: dict[tuple[str, ...], int] = {}
    for index, loop in enumerate(loops):
        members = loop.get("nodes") if isinstance(loop, dict) else None
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            continue
        whole = True
        for position, member in enumerate(members):
            if member not in nodes:
                whole = False
                found.append(
                    Violation(
                        _pointer("loops", index, "nodes", position),
                        f"{member!r} is not the id of any node"
                        + _closest(member, dict.fromkeys(nodes)),
                    )
                )
            elif member in members[:position]:
                whole = False
                found.append(
                    Violation(
                        _pointer("loops", index, "nodes", position),
                        f"{member!r} is named twice: a loop passes each variable once. Two "
                        f"loops through one variable are two loops.",
                    )
                )
        if not whole or len(members) < 2:
            continue
        for position, member in enumerate(members):
            following = members[(position + 1) % len(members)]
            if (member, following) not in polarity:
                whole = False
                found.append(
                    Violation(
                        _pointer("loops", index, "nodes", position),
                        f"no edge runs {member} \u2192 {following}: a loop's nodes are its "
                        f"variables in the order it runs, each joined to the next and the "
                        f"last back to the first.",
                    )
                )
        if not whole:
            continue
        start = members.index(min(members))
        key = tuple(members[start:] + members[:start])
        if key in rings:
            found.append(
                Violation(
                    _pointer("loops", index, "nodes"),
                    f"loop {rings[key]} is already this loop: the same variables in the same "
                    f"order. Name it once.",
                )
            )
            continue
        rings[key] = index
        minus = sum(
            polarity[(member, members[(position + 1) % len(members)])] == "-"
            for position, member in enumerate(members)
        )
        derived = "balancing" if minus % 2 else "reinforcing"
        stated = loop.get("type")
        if isinstance(stated, str) and stated in LOOP_TYPES and stated != derived:
            found.append(
                Violation(
                    _pointer("loops", index, "type"),
                    f"this loop has {minus} negative link{'s' if minus != 1 else ''}, so it is "
                    f"{derived}: an even number of '-' links reinforces, an odd number "
                    f"balances. Check the signs, or the type.",
                )
            )
    return found


def _shaped_in_cycle(nodes: Any) -> list[Violation]:
    """A cycle step drawn as a flowchart symbol: a ring of boxes has no data in it."""
    return [
        Violation(
            _pointer("nodes", index, "role"),
            (
                "'person' draws a person, and a cycle is a ring of steps that each lead to "
                "the next, not the people taking them. Name who does a step with `actor`, "
                "or draw the people and the system as a `flow`."
            )
            if node["role"] == "person"
            else f"{node['role']!r} draws a flowchart symbol, and a cycle is a ring of steps "
            f"that each lead to the next: there is no input, store or sub-process on it. "
            f"Draw the process as a `flow` if those matter.",
        )
        for index, node in enumerate(nodes if isinstance(nodes, list) else ())
        if isinstance(node, dict) and node.get("role") in SHAPED_ROLES
    ]


def _class_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """Node classes: declared, each used, unique, and never on a box they cannot mark.

    A class is a fill a reader matches against the key, so a class nobody uses
    is a key entry pointing at nothing, and a `class` with no declaration has no
    name to show in the key. A `note` has no outline to fill and a `group` is a
    container; a box with a `status` is already marked, and two marks on one box
    say neither clearly. A `cycle` is a ring of peers: it takes no classes.
    """
    nodes = _listed(document, "nodes")
    classes = document.get("classes")
    found: list[Violation] = []
    if kind == "cycle":
        if "classes" in document:
            found.append(
                Violation(
                    "/classes",
                    "a cycle is a ring of steps that each lead to the next, so it has no "
                    "classes to sort them into. Draw the process as a `flow` to class its "
                    "boxes.",
                )
            )
        found.extend(
            Violation(
                _pointer("nodes", index, "class"),
                "a cycle takes no node classes: draw the process as a `flow` to class its boxes.",
            )
            for index, node in enumerate(nodes)
            if isinstance(node, dict) and "class" in node
        )
        return found
    declared: list[str] = []
    for index, entry in enumerate(classes if isinstance(classes, list) else ()):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        if entry["id"] in declared:
            found.append(
                Violation(
                    _pointer("classes", index, "id"),
                    f"duplicate class id {entry['id']!r}: each class is one fill and one "
                    f"line of the key.",
                )
            )
        declared.append(entry["id"])
    used: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("class"), str):
            continue
        name = node["class"]
        pointer = _pointer("nodes", index, "class")
        if name not in declared:
            close = get_close_matches(name, declared, n=1)
            found.append(
                Violation(
                    pointer,
                    f"{name!r} is not one of the document's classes"
                    + (
                        f" — did you mean {close[0]!r}?"
                        if close
                        else ": declare it in the top-level 'classes' as {id, text}, "
                        "so the key can name it."
                    ),
                )
            )
            continue
        used.add(name)
        role = node.get("role", "step")
        if role in UNCLASSED_ROLES:
            found.append(
                Violation(
                    pointer,
                    f"a {role!r} box takes no class: "
                    + (
                        "a note has no outline to fill, and is not the content."
                        if role == "note"
                        else "a group is a container, not a box of a class."
                    ),
                )
            )
        if node.get("status"):
            found.append(
                Violation(
                    pointer,
                    "a box with a 'status' is already marked by the change; a class's fill "
                    "on it as well says neither clearly. Drop one: a drawing of a change "
                    "is about the change.",
                )
            )
    for index, name in enumerate(declared):
        if name not in used:
            found.append(
                Violation(
                    _pointer("classes", index),
                    f"no node is in the class {name!r}: a key entry that matches nothing in "
                    f"the drawing. Give it to the boxes it names, or remove it.",
                )
            )
    return found


def _status_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """Where a change's marks contradict each other, or are on a kind with no change.

    Marks on a drawing of a change make claims about the state after it, so two
    of them can disagree: an edge that stays, drawn to a box that goes, would
    outlive what it connects; an edge that was always there cannot reach a box
    that is new. Each is refused at the edge's `status`, where the fix is.
    """
    nodes = document.get("nodes")
    edges = document.get("edges")
    found: list[Violation] = []
    if kind == "cycle":
        for name, entries in (("nodes", nodes), ("edges", edges)):
            for index, entry in enumerate(entries if isinstance(entries, list) else ()):
                if isinstance(entry, dict) and "status" in entry:
                    found.append(
                        Violation(
                            _pointer(name, index, "status"),
                            "a cycle that changes is a different cycle, and a ring with a "
                            "step marked removed is still drawn as a ring through it. Draw "
                            "the loop before and the loop after as two cycles.",
                        )
                    )
        return found
    status_of = {
        node["id"]: node.get("status", "")
        for node in (nodes if isinstance(nodes, list) else ())
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    for index, edge in enumerate(edges if isinstance(edges, list) else ()):
        if not isinstance(edge, dict):
            continue
        ends = {
            end: status_of.get(edge.get(end), "")
            for end in ("from", "to")
            if isinstance(edge.get(end), str)
        }
        marked = edge.get("status", "")
        gone = [edge[end] for end, status in ends.items() if status == "removed"]
        new = [edge[end] for end, status in ends.items() if status == "added"]
        pointer = _pointer("edges", index, "status")
        if gone and new:
            found.append(
                Violation(
                    pointer,
                    f"this edge joins {new[0]!r}, which the change adds, to {gone[0]!r}, "
                    f"which it removes. The two never exist at the same time, so nothing "
                    f"can connect them.",
                )
            )
        elif gone and marked != "removed":
            found.append(
                Violation(
                    pointer,
                    f"{gone[0]!r} is removed by this change, so an edge to it cannot "
                    f"outlive it: mark this edge 'removed' too.",
                )
            )
        elif new and marked != "added":
            found.append(
                Violation(
                    pointer,
                    f"{new[0]!r} is added by this change, so an edge to it is new as well: "
                    f"mark this edge 'added'.",
                )
            )
    return found


def _scale_violations(scale: Sequence[str], cells: Sequence[Any]) -> list[Violation]:
    """What an ordered fill may not be: too long, repeated, or missing a cell's group.

    A `scale` turns a matrix's groups from a set into an order, so every filled
    cell has to be *on* it — a cell in a group the scale does not name would take
    a fill that means nothing on a drawing whose fills are amounts.
    """
    found: list[Violation] = []
    if len(scale) > RAMP_STEPS:
        found.append(
            Violation(
                _pointer("scale", RAMP_STEPS),
                f"a scale of {len(scale)} steps is past what tone can carry — {RAMP_STEPS} "
                f"at most. Beyond that, neighbouring steps are one grey in print and the "
                f"order stops being visible. Merge buckets until there are {RAMP_STEPS} "
                f"or fewer.",
            )
        )
    seen: set[str] = set()
    for index, step in enumerate(scale):
        if not step.strip():
            found.append(Violation(_pointer("scale", index), "a scale step needs a name"))
        elif step in seen:
            found.append(
                Violation(
                    _pointer("scale", index),
                    f"{step!r} is already a step of this scale. An order names each step once.",
                )
            )
        seen.add(step)
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        group = cell.get("group")
        if isinstance(group, str) and group and group not in seen:
            found.append(
                Violation(
                    _pointer("cells", index, "group"),
                    f"{group!r} is not a step of this matrix's scale ({', '.join(scale)}). "
                    f"When the groups are an order every filled cell is on it; leave "
                    f"'group' out for a cell that was not assessed.",
                )
            )
    return found


def _hub_violations(document: Mapping[str, Any], nodes: Set[str]) -> list[Violation]:
    """What a `cycle`'s hub may not be: a step, a duplicate, or a middle of too little.

    The hub shares the node id space so an edge can name it, and that is the one
    thing it shares: an edge to it is a spoke, so only a role drawn without a
    solid head may make one. A `flow` arrow from the last step into the middle
    reads as the loop ending there, which is the opposite of what a hub says.
    """
    hub = document.get("hub")
    if not isinstance(hub, dict) or not isinstance(hub.get("id"), str):
        return []
    found: list[Violation] = []
    identifier = hub["id"]
    if identifier in nodes:
        found.append(
            Violation(
                "/hub/id",
                f"{identifier!r} is already the id of a node. The hub is not a step on the "
                f"ring, so it needs an id of its own.",
            )
        )
    steps = document.get("nodes")
    if isinstance(steps, list) and len(steps) < HUB_MINIMUM_NODES:
        found.append(
            Violation(
                "/hub",
                f"a hub needs a ring of at least {HUB_MINIMUM_NODES} steps around it, and "
                f"this one has {len(steps)}. Two steps and a middle is three boxes in a "
                f"row: draw it as a flow.",
            )
        )
    for index, edge in enumerate(document.get("edges", ()) or ()):
        if not isinstance(edge, dict) or identifier not in (edge.get("from"), edge.get("to")):
            continue
        if edge.get("from") == edge.get("to"):
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    "the hub is joined to itself, and there is nowhere to draw that: a "
                    "spoke runs between the middle and a step.",
                )
            )
            continue
        role = edge.get("role", "flow")
        if isinstance(role, str) and role not in HUB_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index, "role"),
                    f"an edge to the hub is a spoke, and {role!r} draws a solid arrow, "
                    f"which reads as one more step of the loop. Give it one of "
                    f"{', '.join(HUB_EDGE_ROLES)}.",
                )
            )
    return found


def _self_containment(edges: Sequence[Any], groups: Any, containers: Set[str]) -> list[Violation]:
    """Edges between a container and something already inside it.

    An edge naming a group says *this relation belongs to the whole of it* — a
    platform that watches the cluster rather than one pod of it. That reading
    only holds against something **outside** the container: an edge from a frame
    to a box within it would leave a border and arrive inside the same border,
    which is not a relation between two things but a line from a thing to part of
    itself. There is no geometry for it, and no sentence it draws.

    Refused by name rather than dropped, for the same reason an id that resolves
    to nothing is: the author meant something, and only they can say what.
    """
    parent: dict[str, str] = {}
    for group in groups if isinstance(groups, list) else ():
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        members = group.get("members")
        if not isinstance(members, list):
            continue
        for member in members:
            # First claim wins. A member claimed twice is its own violation and
            # is reported by the group checks; walking either chain would answer
            # this question the same way.
            if isinstance(member, str) and member not in parent:
                parent[member] = group["id"]

    def encloses(container: str, identifier: str) -> bool:
        """Whether `container` is an ancestor of `identifier`, at any depth."""
        walked: set[str] = set()
        current = parent.get(identifier)
        while current is not None and current not in walked:
            if current == container:
                return True
            walked.add(current)
            current = parent.get(current)
        return False

    found: list[Violation] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        for end, container, inside in (("from", source, target), ("to", target, source)):
            if container in containers and encloses(container, inside):
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{container!r} contains {inside!r}, so an edge between them would "
                        f"leave a border and arrive inside it. An edge naming a container is "
                        f"about the whole of it, which only says something against what is "
                        f"outside — draw it from a member instead, or point it elsewhere.",
                    )
                )
                break
    return found


def _classes(document: Mapping[str, Any]) -> tuple[NodeClass, ...]:
    return tuple(
        NodeClass(id=entry["id"], text=entry["text"]) for entry in document.get("classes", ())
    )


def _hub(entry: Mapping[str, Any] | None) -> Node | None:
    if entry is None:
        return None
    return Node(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))


def _entries(entries: Sequence[Mapping[str, Any]]) -> tuple[Entry, ...]:
    return tuple(
        Entry(
            path=entry["path"],
            note=entry.get("note", ""),
            link=entry.get("link", ""),
            status=entry.get("status", ""),
        )
        for entry in entries
    )


def _items(entries: Sequence[Mapping[str, Any]]) -> tuple[Item, ...]:
    return tuple(
        Item(
            text=entry["text"],
            id=entry.get("id", ""),
            role=entry.get("role", "step"),
            note=entry.get("note", ""),
            at=None if entry.get("at") is None else float(entry["at"]),
            gate=entry.get("gate", ""),
            amount=None if entry.get("amount") is None else float(entry["amount"]),
        )
        for entry in entries
    )


def _axes(entry: Mapping[str, Any] | None) -> tuple[Axis, ...]:
    """The horizontal axis then the vertical one. Ordered, for determinism."""
    if entry is None:
        return ()
    return tuple(_axis(entry[name]) for name in AXIS_ORDER)


def _axis(entry: Mapping[str, Any]) -> Axis:
    return Axis(
        label=entry["label"],
        unit=entry.get("unit", ""),
        minimum=_optional_number(entry.get("min")),
        maximum=_optional_number(entry.get("max")),
        categories=tuple(str(name) for name in entry.get("categories", ())),
        ends=tuple(str(name) for name in entry.get("ends", ())),
    )


def _optional_number(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]
