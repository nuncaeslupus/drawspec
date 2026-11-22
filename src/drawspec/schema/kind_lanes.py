"""The `lanes` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import get_close_matches
from typing import Any, Final

from drawspec.schema._checks import _classes, _listed, _optional_number, _pointer, _reaches
from drawspec.schema._constants import DOCUMENT_VERSION, LANES_MAX
from drawspec.schema._fields import LANES_ACTOR_MISSING
from drawspec.schema._model import Document, Edge, Node, Phase, Violation

#: Why a `lanes` document may not write what a `flow` may, by the field's name.
LANES_REFUSED: Final[Mapping[str, str]] = {
    "groups": (
        "a lanes diagram has no 'groups': a lane is already the container, and a frame "
        "drawn across lanes would put a box in two containers at once. Use a flow for "
        "frames, or name the containing party as the nodes' actor."
    ),
    "bands": (
        "a lanes diagram has no 'bands': a band runs alongside its boxes, and here that "
        "would run across the lanes. Use a flow with bands, or make the activity a lane."
    ),
    "centre": (
        "a lanes diagram is ranked along its lanes, so it has no middle to arrange "
        "around. Use a flow."
    ),
}


def _lanes_refusal(violation: Violation) -> Violation:
    """An unknown field on a `lanes` document, with why a flow's field is not here."""
    name = violation.pointer.rsplit("/", 1)[-1]
    if name in LANES_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, LANES_REFUSED[name])
    return violation


def _lanes_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a swimlane diagram may not be: a box in no lane, or a lane with no box.

    Ids and edges are the graph checks, shared with `flow`; these are the lane's
    own. A listed lane must hold some node and every actor must be listed, since
    either mismatch is nearly always a spelling difference — so the closest lane
    is named. With no list, the distinct actors are capped as the list would be.
    """
    found: list[Violation] = []
    actors: list[tuple[int, str]] = []
    for index, node in enumerate(_listed(document, "nodes")):
        if not isinstance(node, dict) or not isinstance(node.get("actor"), str):
            continue
        if not node["actor"].strip():
            found.append(Violation(_pointer("nodes", index, "actor"), LANES_ACTOR_MISSING))
            continue
        actors.append((index, node["actor"]))

    listed = document.get("lanes")
    if isinstance(listed, list) and all(isinstance(lane, str) for lane in listed):
        seen: set[str] = set()
        for index, lane in enumerate(listed):
            if lane in seen:
                found.append(
                    Violation(_pointer("lanes", index), f"the lane {lane!r} is listed twice.")
                )
            seen.add(lane)
        named = {actor for _, actor in actors}
        for index, actor in actors:
            if actor in seen:
                continue
            close = get_close_matches(actor, listed, n=1, cutoff=0.0)
            found.append(
                Violation(
                    _pointer("nodes", index, "actor"),
                    f"{actor!r} is not one of the lanes"
                    + (f" — did you mean {close[0]!r}?" if close else ".")
                    + " An actor names its lane exactly; add it to 'lanes' if it is a new one.",
                )
            )
        for index, lane in enumerate(listed):
            if lane not in named and listed.index(lane) == index:
                found.append(
                    Violation(
                        _pointer("lanes", index),
                        f"no node names {lane!r} as its actor, so its lane would be an empty "
                        f"strip saying that party does nothing. Drop it, or give it its step.",
                    )
                )
    elif listed is None:
        distinct: dict[str, int] = {}
        for index, actor in actors:
            if actor not in distinct:
                distinct[actor] = index
                if len(distinct) == LANES_MAX + 1:
                    found.append(
                        Violation(
                            _pointer("nodes", index, "actor"),
                            f"{actor!r} would be lane {LANES_MAX + 1}, and a lanes diagram "
                            f"can be read at {LANES_MAX} at most. Merge parties that act "
                            f"together, or split the process at a hand-off.",
                        )
                    )
    found.extend(_phase_violations(document))
    return found


def _phase_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A swimlane diagram's phases: known steps, each in one phase, in the order run.

    The phases partition the steps, as a gantt's groups partition its tasks, so
    every step's column (or row) of the grid is the author's and never the
    layout's guess. Order is checked on the arrows: one that runs from a later
    phase into an earlier one is a loop back only if the earlier step leads on to
    the later one again; otherwise the phases are written out of order, or the
    step is in the wrong one.
    """
    phases = document.get("phases")
    if not isinstance(phases, list):
        return []
    ids = [
        node["id"]
        for node in _listed(document, "nodes")
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    ]
    known = set(ids)
    found: list[Violation] = []
    phase_of: dict[str, int] = {}
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            continue
        for position, member in enumerate(_listed(phase, "members")):
            if not isinstance(member, str):
                continue
            pointer = _pointer("phases", index, "members", position)
            if member not in known:
                close = get_close_matches(member, ids, n=1)
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is not the id of any step"
                        + (f" — did you mean {close[0]!r}?" if close else "."),
                    )
                )
            elif member in phase_of:
                earlier = phases[phase_of[member]].get("text")
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is already in the phase {earlier!r}. Phases do not "
                        f"overlap: a step happens in one phase, so name it once.",
                    )
                )
            else:
                phase_of[member] = index
    for index, identifier in enumerate(ids):
        if identifier not in phase_of and phase_of:
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"{identifier!r} is in no phase. With 'phases' given every step is in "
                    f"exactly one: add it to the 'members' of the phase it happens in.",
                )
            )
    if found:
        return found
    following: dict[str, list[str]] = {identifier: [] for identifier in ids}
    edges = _listed(document, "edges")
    for edge in edges:
        if isinstance(edge, dict) and edge.get("from") in known and edge.get("to") in known:
            following[edge["from"]].append(edge["to"])
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if source not in phase_of or target not in phase_of:
            continue
        if phase_of[source] <= phase_of[target] or _reaches(following, target, source):
            continue
        later = phases[phase_of[source]].get("text")
        earlier = phases[phase_of[target]].get("text")
        found.append(
            Violation(
                _pointer("edges", index),
                f"this arrow runs from {source!r} in the phase {later!r} back to {target!r} "
                f"in the earlier phase {earlier!r}, and nothing leads from {target!r} on to "
                f"{source!r}, so it is not a loop back. The phases are out of order, or one "
                f"of the two steps is in the wrong phase: list the phases in the order the "
                f"process runs.",
            )
        )
    return found


def _lanes_document(document: Mapping[str, Any]) -> Document:
    """A swimlane diagram as the graph family reads it: a flow whose actors are lanes.

    The actor is moved to `Node.lane`, so the box is sized from its own text and
    the actor is drawn once, as its lane's heading, rather than in every box.
    """
    nodes = tuple(
        Node(
            id=entry["id"],
            text=entry["text"],
            role=entry.get("role", "step"),
            status=entry.get("status", ""),
            klass=entry.get("class", ""),
            lane=entry["actor"],
        )
        for entry in document["nodes"]
    )
    return Document(
        kind=str(document["kind"]),
        version=DOCUMENT_VERSION,
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        nodes=nodes,
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
                status=entry.get("status", ""),
            )
            for entry in document.get("edges", ())
        ),
        lanes=lane_order(document),
        phases=tuple(
            Phase(text=entry["text"], members=tuple(entry["members"]))
            for entry in document.get("phases", ())
        ),
        classes=_classes(document),
    )


def lane_order(document: Mapping[str, Any]) -> tuple[str, ...]:
    """The lanes of a `lanes` document, in order: as listed, or as first named."""
    listed = document.get("lanes")
    if isinstance(listed, list):
        return tuple(str(lane) for lane in listed)
    order: dict[str, None] = {}
    for node in _listed(document, "nodes"):
        if isinstance(node, dict) and isinstance(node.get("actor"), str):
            order.setdefault(node["actor"], None)
    return tuple(order)
