"""The `argument` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import ARGUMENT_DEPTH_MAX, ARGUMENT_GROUP_MAX
from drawspec.schema._model import ArgumentPoint, Document, Violation

#: Why an argument map has no place for a field an author may reach for.
ARGUMENT_REFUSED: Final = {
    "edges": (
        "an argument map's structure is each point's `on`: the box it bears on. A point "
        "that bears on two boxes is two points"
    ),
    "nodes": "an argument map's boxes are its `claim` and its `points`",
    "parent": "the box a point bears on is its `on`",
    "children": "a point names the box it bears on with `on`; the points under a box follow",
    "side": "where a point goes is drawspec's: it hangs under the box it is `on`, in order",
}


#: What a third stance would be, and why there is none.
_STANCE_ADVICE: Final = (
    "A rebuttal or an objection is an `against` on the point it answers; its name follows "
    "from the depth, and the tags already read *because*, *but*, *but* down the chain"
)


def _inference_objection(names: Sequence[str]) -> str:
    joined = " and ".join(f"{name!r}" for name in names)
    return (
        f"`on` names one box. An objection to how {joined} together support their box — an "
        f"inference objection — is an objection to the premise that links them, which the "
        f"argument leaves unstated. Write that premise as a point `with` them, and put the "
        f"objection `on` it."
    )


def _argument_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in an argument map, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in ARGUMENT_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {ARGUMENT_REFUSED[name]}.")
    if name == "stance" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0] + f". {_STANCE_ADVICE}.",
        )
    if name == "on" and "expected" in violation.message and len(parts) == 4:
        points = document.get("points")
        entry = points[int(parts[2])] if isinstance(points, list) else None
        names = entry.get("on") if isinstance(entry, dict) else None
        if isinstance(names, list) and all(isinstance(each, str) for each in names):
            return Violation(violation.pointer, _inference_objection(names))
    if name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". Stance is not a role: `step`, `emphasis` for the decisive point, `note` for "
            "evidence or a source.",
        )
    if parts[1:] == ["points"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "an argument map needs at least one point: a claim alone is a sentence.",
        )
    return violation


def _argument_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that resolve, a tree under the claim, co-premises that match, and depth."""
    found: list[Violation] = []
    claim = document.get("claim")
    if isinstance(claim, str) and not claim.strip():
        found.append(Violation("/claim", "the claim is the contention: it needs words."))
    entries = [
        (index, entry)
        for index, entry in enumerate(_listed(document, "points"))
        if isinstance(entry, dict)
    ]
    ids: dict[str, int] = {}
    for index, entry in entries:
        name = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(Violation(_pointer("points", index, "text"), "a point needs words."))
        if not isinstance(name, str):
            continue
        if name == "claim":
            found.append(
                Violation(
                    _pointer("points", index, "id"),
                    "'claim' names the contention, so no point may take it as its id.",
                )
            )
        elif name in ids:
            found.append(
                Violation(
                    _pointer("points", index, "id"),
                    f"{name!r} is already the id of point {ids[name]}: ids are unique.",
                )
            )
        else:
            ids[name] = index
    by_id = {name: dict(entries)[index] for name, index in ids.items()}

    parent: dict[str, str] = {}
    for index, entry in entries:
        target = entry.get("on")
        name = entry.get("id")
        if not isinstance(target, str) or not isinstance(name, str):
            continue
        where = _pointer("points", index, "on")
        if target == "claim" or target in ids:
            if target == name and name != "claim":
                found.append(Violation(where, "a point cannot bear on itself."))
            elif ids.get(name) == index:
                parent[name] = target
            continue
        pieces = [piece.strip() for piece in re.split(r"[+&,]", target)]
        if len(pieces) > 1 and all(piece in ids for piece in pieces):
            found.append(Violation(where, _inference_objection(pieces)))
        else:
            found.append(
                Violation(
                    where,
                    f"{target!r} is not `claim` or the id of a point. Known ids: "
                    f"{', '.join(sorted(ids)) or 'none'}.",
                )
            )

    # A tree: every chain of `on` ends at the claim, at most four deep.
    depth: dict[str, int] = {}
    for name in parent:
        chain: list[str] = []
        current = name
        while current != "claim" and current in parent and current not in chain:
            chain.append(current)
            current = parent[current]
        if current != "claim":
            if current in chain:
                index = ids[name]
                found.append(
                    Violation(
                        _pointer("points", index, "on"),
                        f"this `on` goes round in a circle ({' -> '.join([*chain, current])}): "
                        f"an argument is a tree under the claim.",
                    )
                )
            continue
        depth[name] = len(chain)
    for name, levels in depth.items():
        if levels > ARGUMENT_DEPTH_MAX:
            found.append(
                Violation(
                    _pointer("points", ids[name], "on"),
                    f"this point is {levels} levels below the claim, past what one argument "
                    f"map can be read at — {ARGUMENT_DEPTH_MAX} at most. Draw the point it "
                    f"answers as the claim of a map of its own.",
                )
            )

    # Co-premises: same box, same stance, a group of at most four.
    links: dict[str, set[str]] = {name: set() for name in ids}
    for index, entry in entries:
        name = entry.get("id")
        others = entry.get("with")
        if not isinstance(name, str) or ids.get(name) != index or not isinstance(others, list):
            continue
        for position, other in enumerate(others):
            where = _pointer("points", index, "with", position)
            if not isinstance(other, str):
                continue
            if other == name:
                found.append(Violation(where, "a point is not its own co-premise."))
                continue
            if other not in by_id:
                found.append(
                    Violation(where, f"{other!r} is not the id of a point; `with` names points.")
                )
                continue
            mate = by_id[other]
            if mate.get("on") != entry.get("on"):
                found.append(
                    Violation(
                        where,
                        f"{other!r} is `on` {mate.get('on')!r} and this point is `on` "
                        f"{entry.get('on')!r}: co-premises support the same box.",
                    )
                )
                continue
            if mate.get("stance") != entry.get("stance"):
                found.append(
                    Violation(
                        where,
                        f"{other!r} is {mate.get('stance')!r} and this point is "
                        f"{entry.get('stance')!r}: co-premises bear the same way.",
                    )
                )
                continue
            links[name].add(other)
            links[other].add(name)
    seen: set[str] = set()
    for name in ids:
        if name in seen or not links[name]:
            continue
        group: list[str] = []
        stack = [name]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            group.append(current)
            stack.extend(links[current])
        if len(group) > ARGUMENT_GROUP_MAX:
            last = max(group, key=lambda member: ids[member])
            found.append(
                Violation(
                    _pointer("points", ids[last], "with"),
                    f"{len(group)} co-premises in one group, and a group can be read at "
                    f"{ARGUMENT_GROUP_MAX} at most. Premises that many usually hide a "
                    f"sub-argument: make some of them a point of their own, with its "
                    f"own reasons under it.",
                )
            )
    return found


def _argument_document(document: Mapping[str, Any]) -> Document:
    """An argument map: its claim and its points, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        claim=str(document["claim"]),
        points=tuple(
            ArgumentPoint(
                id=str(point["id"]),
                text=str(point["text"]),
                on=str(point["on"]),
                stance=str(point["stance"]),
                with_=tuple(str(other) for other in point.get("with", ())),
                role=str(point.get("role", "step")),
            )
            for point in document["points"]
        ),
    )
