"""The `sequence` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import BRANCHING_OPERATORS
from drawspec.schema._model import Branch, Document, Fragment, Group, Message, Node, Violation


def _sequence_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a sequence diagram may not be: ids that do not land, and frames that cannot draw.

    Ids first — participants and groups named once, every message's ends a
    participant, every fragment's ends a message — then the claims only this
    kind makes: a participant nobody talks to, a group whose lifelines are not
    neighbours, a fragment that ends before it starts or half-overlaps another,
    and a branch divider that is not inside its own frame.
    """
    found: list[Violation] = []
    participants: dict[str, int] = {}
    for index, participant in enumerate(_listed(document, "participants")):
        identifier = participant.get("id") if isinstance(participant, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in participants:
            found.append(
                Violation(
                    _pointer("participants", index, "id"),
                    f"duplicate participant id {identifier!r}",
                )
            )
            continue
        participants[identifier] = index

    talking: set[str] = set()
    message_ids: dict[str, int] = {}
    for index, message in enumerate(_listed(document, "messages")):
        if not isinstance(message, dict):
            continue
        for end in ("from", "to"):
            target = message.get(end)
            if not isinstance(target, str):
                continue
            if target not in participants:
                found.append(
                    Violation(
                        _pointer("messages", index, end),
                        f"{target!r} is not the id of any participant in this document",
                    )
                )
            talking.add(target)
        identifier = message.get("id")
        if isinstance(identifier, str):
            if identifier in message_ids:
                found.append(
                    Violation(
                        _pointer("messages", index, "id"),
                        f"duplicate message id {identifier!r}",
                    )
                )
            else:
                message_ids[identifier] = index

    for identifier, index in participants.items():
        if identifier not in talking:
            found.append(
                Violation(
                    _pointer("participants", index),
                    f"no message is sent to or from {identifier!r}, so its lifeline would be "
                    f"a box with a line under it. It is usually a mistyped id in a message; "
                    f"otherwise delete the participant.",
                )
            )

    found.extend(_async_reply_violations(document))
    found.extend(_sequence_group_violations(document, participants))
    found.extend(_fragment_violations(document, message_ids))
    return found


def _async_reply_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A `weak` reply whose only question was an `async` message, which awaits none.

    An asynchronous message is sent and the sender carries on: there is no call
    for a dashed reply to return from. An answer that comes later is a message of
    its own, sent back the other way.
    """
    found: list[Violation] = []
    calls: set[tuple[str, str]] = set()
    sent: set[tuple[str, str]] = set()
    for index, message in enumerate(_listed(document, "messages")):
        if not isinstance(message, dict):
            continue
        source, target, role = message.get("from"), message.get("to"), message.get("role", "flow")
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            continue
        if role in ("flow", "strong"):
            calls.add((source, target))
        elif role == "async":
            sent.add((source, target))
        elif role == "weak" and (target, source) in sent and (target, source) not in calls:
            found.append(
                Violation(
                    _pointer("messages", index, "role"),
                    f"this reply answers {target!r}'s async message to {source!r}, and an "
                    f"async message awaits no reply. Send the answer as a message of its own "
                    f"(role 'async' or 'flow'), or make the question a call ('flow').",
                )
            )
    return found


def _sequence_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in a sequence diagram, told what this kind means by it."""
    parts = violation.pointer.split("/")
    if len(parts) == 4 and parts[1] == "participants" and parts[3] == "role":
        entries = document.get("participants")
        try:
            role = entries[int(parts[2])]["role"]  # type: ignore[index]
        except (TypeError, ValueError, IndexError, KeyError):
            return violation
        if role in ("person", "user", "human"):
            return Violation(
                violation.pointer,
                f"{role!r} is not a participant role here: a person taking part is "
                f"'actor', drawn as a stick figure over the lifeline.",
            )
    if len(parts) == 4 and parts[1] == "messages" and parts[3] == "role":
        entries = document.get("messages")
        try:
            role = entries[int(parts[2])]["role"]  # type: ignore[index]
        except (TypeError, ValueError, IndexError, KeyError):
            return violation
        if role in ("asynchronous", "signal", "event", "sync", "call", "reply", "return"):
            return Violation(
                violation.pointer,
                f"{role!r} is not a message role: a call is 'flow', its reply 'weak', a "
                f"message nobody waits on 'async', and the exchange that matters 'strong'.",
            )
    return violation


def _sequence_group_violations(
    document: Mapping[str, Any], participants: Mapping[str, int]
) -> list[Violation]:
    """Groups over lifelines: known members, one group each, and neighbours."""
    found: list[Violation] = []
    names = {index: identifier for identifier, index in participants.items()}
    owner: dict[str, str] = {}
    group_ids: set[str] = set()
    for index, group in enumerate(_listed(document, "groups")):
        if not isinstance(group, dict):
            continue
        identifier = group.get("id")
        if isinstance(identifier, str):
            if identifier in participants:
                found.append(
                    Violation(
                        _pointer("groups", index, "id"),
                        f"{identifier!r} is already the id of a participant",
                    )
                )
            elif identifier in group_ids:
                found.append(
                    Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
                )
            group_ids.add(identifier)
        members = group.get("members")
        if not isinstance(members, list):
            continue
        positions: list[int] = []
        sound = True
        for position, member in enumerate(members):
            if not isinstance(member, str):
                sound = False
                continue
            pointer = _pointer("groups", index, "members", position)
            if member not in participants:
                found.append(Violation(pointer, f"{member!r} is not the id of any participant"))
                sound = False
            elif member in owner:
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is already in {owner[member]!r}. A lifeline is in one "
                        f"group or none.",
                    )
                )
                sound = False
            else:
                owner[member] = str(identifier)
                positions.append(participants[member])
        if not sound or not positions:
            continue
        inside = set(positions)
        between = [
            names[spot] for spot in range(min(positions), max(positions) + 1) if spot not in inside
        ]
        if between:
            found.append(
                Violation(
                    _pointer("groups", index, "members"),
                    f"{between[0]!r} stands between members of {identifier!r} in "
                    f"'participants', so the group's frame would enclose a lifeline that is "
                    f"not in it. Reorder 'participants' so the members are next to each other.",
                )
            )
    return found


def _fragment_violations(
    document: Mapping[str, Any], message_ids: Mapping[str, int]
) -> list[Violation]:
    """Fragments: ends that are messages, in order, nested or apart, and branches inside."""
    found: list[Violation] = []
    spans: list[tuple[int, int, int]] = []
    fragments = _listed(document, "fragments")
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict):
            continue
        ends: dict[str, int] = {}
        for end in ("from", "to"):
            target = fragment.get(end)
            if not isinstance(target, str):
                continue
            if target not in message_ids:
                found.append(
                    Violation(
                        _pointer("fragments", index, end),
                        f"{target!r} is not the id of any message. A fragment names its first "
                        f"and last message by their 'id'.",
                    )
                )
            else:
                ends[end] = message_ids[target]
        if len(ends) < 2:
            continue
        start, finish = ends["from"], ends["to"]
        if finish < start:
            found.append(
                Violation(
                    _pointer("fragments", index, "to"),
                    f"{fragment['to']!r} comes before {fragment['from']!r}, so the frame would "
                    f"end before it starts. Swap them.",
                )
            )
            continue
        spans.append((index, start, finish))

    for position, (index, start, finish) in enumerate(spans):
        for other, first, last in spans[:position]:
            if first < start <= last < finish or start < first <= finish < last:
                found.append(
                    Violation(
                        _pointer("fragments", index),
                        f"this fragment starts inside fragment {other} and ends outside it "
                        f"(or the other way round), and no frame drawing of that does not "
                        f"cross. Fragments nest or are apart: end one inside the other, or "
                        f"after it.",
                    )
                )

    span_of = {index: (start, finish) for index, start, finish in spans}
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict) or "else" not in fragment:
            continue
        branches = fragment.get("else")
        if not isinstance(branches, list):
            continue
        operator = fragment.get("operator")
        if operator not in BRANCHING_OPERATORS:
            found.append(
                Violation(
                    _pointer("fragments", index, "else"),
                    f"a {operator!r} fragment has one branch, so it has nothing to divide. "
                    f"Only {' and '.join(repr(name) for name in BRANCHING_OPERATORS)} take "
                    f"'else'.",
                )
            )
            continue
        if index not in span_of:
            continue
        start, finish = span_of[index]
        previous = start
        for position, branch in enumerate(branches):
            at = branch.get("at") if isinstance(branch, dict) else None
            if not isinstance(at, str):
                continue
            pointer = _pointer("fragments", index, "else", position, "at")
            if at not in message_ids:
                found.append(Violation(pointer, f"{at!r} is not the id of any message"))
                continue
            row = message_ids[at]
            if not start < row <= finish:
                found.append(
                    Violation(
                        pointer,
                        f"{at!r} is not after the fragment's first message and within it, so "
                        f"the divider above it would be "
                        + ("at the frame's top" if row == start else "outside the frame")
                        + ". A branch starts at a later message inside the fragment.",
                    )
                )
                continue
            if row <= previous and position:
                found.append(
                    Violation(
                        pointer,
                        f"{at!r} does not come after the previous divider. List the "
                        f"branches in the order their messages are.",
                    )
                )
                continue
            previous = row
            for other, (first, last) in span_of.items():
                inner = other != index and start <= first and last <= finish
                if inner and (first, last) != (start, finish) and first < row <= last:
                    found.append(
                        Violation(
                            pointer,
                            f"{at!r} is inside fragment {other}, which is nested in this one, "
                            f"so the divider would cut through that frame. Divide at its "
                            f"first message, or at one outside it.",
                        )
                    )
                    break
    return found


def _sequence_document(document: Mapping[str, Any]) -> Document:
    """A sequence diagram: participants as nodes, and its own messages and fragments."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        participants=tuple(
            Node(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["participants"]
        ),
        messages=tuple(
            Message(
                source=entry["from"],
                target=entry["to"],
                text=entry.get("text", ""),
                role=entry.get("role", "flow"),
                id=entry.get("id", ""),
                note=entry.get("note", ""),
            )
            for entry in document["messages"]
        ),
        fragments=tuple(
            Fragment(
                operator=entry["operator"],
                start=entry["from"],
                end=entry["to"],
                text=entry.get("text", ""),
                branches=tuple(
                    Branch(at=branch["at"], text=branch.get("text", ""))
                    for branch in entry.get("else", ())
                ),
            )
            for entry in document.get("fragments", ())
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
    )
