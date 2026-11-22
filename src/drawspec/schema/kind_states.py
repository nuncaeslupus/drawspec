"""The `states` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from drawspec.schema._checks import (
    _listed,
    _loop_violations,
    _optional_number,
    _pointer,
    _self_containment,
)
from drawspec.schema._constants import STATE_BARS
from drawspec.schema._model import Document, Edge, Group, Node, Violation


def transition_label(event: str = "", guard: str = "", action: str = "") -> str:
    """A transition's label, `event [guard] / action`, from whichever parts were given.

    Composed here rather than written by the author, so the punctuation is the
    same on every transition and a missing part leaves no stray bracket or slash.
    Each part is set on its own line — the event, under it the guard, under that
    the action — because the three on one line made the widest labels in any
    drawing, and a label too long for the gap beside its line had nowhere to go.
    """
    parts = [event.strip()]
    if guard.strip():
        parts.append(f"[{guard.strip()}]")
    if action.strip():
        parts.append(f"/ {action.strip()}")
    return "\n".join(part for part in parts if part)


def _states_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a state machine may not be: ids that do not land, and a wrong machine.

    The structural pass has the types; this one has the meaning. Ids first —
    every state and group named once, every reference resolving — and only when
    those hold, the three claims about the machine itself: a final state that
    is left, a pair of transitions that make it non-deterministic, and a state
    nothing can reach. Each is a bug in the machine rather than in the drawing.
    """
    found: list[Violation] = []
    groups_raw = _listed(document, "groups")
    transitions = _listed(document, "transitions")

    state_ids: set[str] = set()
    for index, state in enumerate(_listed(document, "states")):
        identifier = state.get("id") if isinstance(state, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in state_ids:
            found.append(
                Violation(_pointer("states", index, "id"), f"duplicate state id {identifier!r}")
            )
        state_ids.add(identifier)

    groups: dict[str, Mapping[str, Any]] = {}
    for index, group in enumerate(groups_raw):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        identifier = group["id"]
        if identifier in state_ids:
            found.append(
                Violation(
                    _pointer("groups", index, "id"),
                    f"{identifier!r} is already the id of a state; a transition naming it "
                    f"could mean either",
                )
            )
        elif identifier in groups:
            found.append(
                Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
            )
        else:
            groups[identifier] = group
    known = state_ids | set(groups)

    parent: dict[str, str] = {}
    # Member → its region's place in its composite, for a composite with regions.
    region_of: dict[str, int] = {}
    for index, group in enumerate(groups_raw):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        found.extend(_composite_shape(group, index))
        for members, prefix, region in _composite_parts(group):
            for position, member in enumerate(members):
                if not isinstance(member, str):
                    continue
                pointer = _pointer("groups", index, *prefix, "members", position)
                if member not in known:
                    found.append(
                        Violation(
                            pointer,
                            f"{member!r} is not the id of any state or group in this document",
                        )
                    )
                elif member == group["id"]:
                    found.append(Violation(pointer, "a group cannot contain itself"))
                elif member in parent:
                    where = (
                        f"another region of {parent[member]!r}"
                        if parent[member] == group["id"] and region_of.get(member) != region
                        else repr(parent[member])
                    )
                    found.append(
                        Violation(
                            pointer,
                            f"{member!r} is already inside {where}. A state is in one "
                            f"composite or none, and in one of its regions; nest the groups "
                            f"instead.",
                        )
                    )
                else:
                    parent[member] = group["id"]
                    if region is not None:
                        region_of[member] = region
            entry = (
                group.get("initial")
                if region is None
                else _listed(group, "regions")[region].get("initial")
            )
            if isinstance(entry, str) and entry not in members:
                found.append(
                    Violation(
                        _pointer("groups", index, *prefix, "initial"),
                        f"{entry!r} is not a member of "
                        + (
                            f"{group['id']!r}. A composite is entered "
                            if region is None
                            else f"this region of {group['id']!r}. A region starts "
                        )
                        + "at one of its own states.",
                    )
                )

    def entered(identifier: str, pointer: str) -> bool:
        """Whether naming `identifier` as a target lands on a state; reported if not."""
        group = groups.get(identifier)
        if group is None or isinstance(group.get("initial"), str) or "regions" in group:
            return True
        found.append(
            Violation(
                pointer,
                f"{identifier!r} is a group with no 'initial', so entering it does not say "
                f"which state the machine is then in. Give the group an 'initial', or point "
                f"this at one of its states.",
            )
        )
        return False

    initial = document.get("initial")
    if isinstance(initial, str):
        if initial not in known:
            found.append(
                Violation(
                    "/initial",
                    f"{initial!r} is not the id of any state or group in this document",
                )
            )
        else:
            entered(initial, "/initial")

    finals: set[str] = set()
    for index, name in enumerate(_listed(document, "final")):
        if not isinstance(name, str):
            continue
        pointer = _pointer("final", index)
        if name in groups:
            found.append(
                Violation(
                    pointer,
                    f"{name!r} is a group. A final state is a state; to end the machine when "
                    f"a composite completes, draw a transition from the group to a final state.",
                )
            )
        elif name not in state_ids:
            found.append(Violation(pointer, f"{name!r} is not the id of any state"))
        elif name in finals:
            found.append(Violation(pointer, f"{name!r} is named final twice"))
        finals.add(name)

    resolved = True
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        for end in ("from", "to"):
            target = transition.get(end)
            if isinstance(target, str) and target not in known:
                resolved = False
                found.append(
                    Violation(
                        _pointer("transitions", index, end),
                        f"{target!r} is not the id of any state or group in this document",
                    )
                )
        source, target = transition.get("from"), transition.get("to")
        if isinstance(target, str) and target in groups:
            resolved = entered(target, _pointer("transitions", index, "to")) and resolved
        if isinstance(source, str) and source in finals:
            found.append(
                Violation(
                    _pointer("transitions", index, "from"),
                    f"{source!r} is a final state, and a final state is not left: the machine "
                    f"has ended there. Drop this transition, or take {source!r} out of 'final'.",
                )
            )
    flattened = [
        {**group, "members": [m for members, _, _ in _composite_parts(group) for m in members]}
        for group in groups_raw
        if isinstance(group, dict)
    ]
    found.extend(_self_containment(transitions, flattened, frozenset(groups)))
    found.extend(_loop_violations(transitions, frozenset(groups), "transitions"))
    found.extend(_crossing_regions(transitions, parent, region_of))
    found.extend(_bar_violations(document, parent, region_of))
    found.extend(_region_initials(document, groups, parent, region_of))
    forks = {
        state["id"]
        for state in _listed(document, "states")
        if isinstance(state, dict) and state.get("role") == "fork"
    }

    # Two ways out of one state on the same event and guard: which one is taken?
    # A fork's are all taken at once, which is what a fork is.
    seen: dict[tuple[str, str, str], tuple[int, str]] = {}
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        if source in forks:
            continue
        event, guard = transition.get("event", ""), transition.get("guard", "")
        if not all(isinstance(value, str) for value in (source, target, event, guard)):
            continue
        key = (str(source), str(event).strip(), str(guard).strip())
        if key in seen and seen[key][1] != target:
            first = seen[key][0]
            found.append(
                Violation(
                    _pointer("transitions", index, "to"),
                    f"transitions {first} and {index} both leave {source!r} on "
                    + (f"{event.strip()!r}" if event.strip() else "completion")
                    + (f" when {guard.strip()!r}" if guard.strip() else "")
                    + ", to different states, so the machine cannot say which it takes. "
                    "Give them guards that tell them apart.",
                )
            )
        seen.setdefault(key, (index, str(target)))

    if found or not resolved or not isinstance(initial, str):
        return found

    # Reachability, through the composites: entering a group enters its initial,
    # and a transition from a group leaves from every state inside it.
    def ancestors(identifier: str) -> list[str]:
        chain: list[str] = []
        current = parent.get(identifier)
        while current is not None and current not in chain:
            chain.append(current)
            current = parent.get(current)
        return chain

    leaving: dict[str, list[str]] = {}
    for transition in transitions:
        if isinstance(transition, dict):
            leaving.setdefault(transition["from"], []).append(transition["to"])

    reached: set[str] = set()
    queue = [initial]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        group = groups.get(current)
        if group is not None:
            queue.extend(_composite_entries(group))
            continue
        for scope in (current, *ancestors(current)):
            reached.add(scope)
            queue.extend(leaving.get(scope, ()))
            # Entering any state of a composite with regions enters the others at theirs.
            if scope in groups and "regions" in groups[scope]:
                queue.extend(_composite_entries(groups[scope]))

    for index, state in enumerate(_listed(document, "states")):
        identifier = state.get("id") if isinstance(state, dict) else None
        if isinstance(identifier, str) and identifier not in reached:
            found.append(
                Violation(
                    _pointer("states", index),
                    f"no transition reaches {identifier!r} from the initial state, so the "
                    f"machine can never be in it. Add the transition that leads there, or "
                    f"delete the state.",
                )
            )
    return found


def _composite_parts(
    group: Mapping[str, Any],
) -> list[tuple[list[Any], tuple[str | int, ...], int | None]]:
    """A composite's member lists: its `members`, or each region's, with where each sits."""
    regions = group.get("regions")
    if isinstance(regions, list):
        return [
            (
                region["members"] if isinstance(region.get("members"), list) else [],
                ("regions", number),
                number,
            )
            for number, region in enumerate(regions)
            if isinstance(region, dict)
        ]
    members = group.get("members")
    return [(members if isinstance(members, list) else [], (), None)]


def _composite_shape(group: Mapping[str, Any], index: int) -> list[Violation]:
    """A composite lists its `members` or its `regions` — one, not both, not neither."""
    if "regions" not in group:
        if "members" in group:
            return []
        return [
            Violation(
                _pointer("groups", index),
                f"composite {group['id']!r} has no 'members'. List the states inside it, "
                f"or its 'regions' when parts of it run at once.",
            )
        ]
    if "members" in group:
        return [
            Violation(
                _pointer("groups", index, "members"),
                f"composite {group['id']!r} has both 'members' and 'regions'. With regions "
                f"every member belongs to one of them: move these into the regions.",
            )
        ]
    if "initial" in group:
        return [
            Violation(
                _pointer("groups", index, "initial"),
                f"composite {group['id']!r} has regions, and entering it enters every region "
                f"at its own 'initial'. Drop this; each region names where it starts.",
            )
        ]
    return []


def _composite_entries(group: Mapping[str, Any]) -> list[str]:
    """Where entering a composite lands: its `initial`, or every region's."""
    if "regions" in group:
        return [
            region["initial"]
            for region in _listed(group, "regions")
            if isinstance(region, dict) and isinstance(region.get("initial"), str)
        ]
    return [str(group["initial"])]


def _regions_above(
    identifier: str, parent: Mapping[str, str], region_of: Mapping[str, int]
) -> dict[str, int]:
    """Each composite with regions that `identifier` is inside, and which region."""
    found: dict[str, int] = {}
    current = identifier
    while current in parent and parent[current] not in found:
        if current in region_of:
            found[parent[current]] = region_of[current]
        current = parent[current]
    return found


def _bar_violations(
    document: Mapping[str, Any], parent: Mapping[str, str], region_of: Mapping[str, int]
) -> list[Violation]:
    """What a fork or join bar may not be, and the words every other state needs.

    A bar is a pseudo-state the machine passes through at once (UML's fork and
    join): it has no name, nothing to wait for, and a fixed count of ways in and
    out. A fork splits one transition into one per region of a composite, so its
    arrows must end in different regions of one composite — two in one region
    would put the machine in two of its states at once, and arrows to states in
    no region would claim a concurrency the machine has nowhere to hold. A join
    is the same rule read backwards.
    """
    found: list[Violation] = []
    bars: dict[str, str] = {}
    for index, state in enumerate(_listed(document, "states")):
        if not isinstance(state, dict) or not isinstance(state.get("id"), str):
            continue
        role = state.get("role")
        if role in STATE_BARS:
            bars[state["id"]] = str(role)
            if "text" in state:
                found.append(
                    Violation(
                        _pointer("states", index, "text"),
                        f"a {role} is drawn as a bar with no words. Drop 'text'; name the "
                        f"state the machine is in before or after it instead.",
                    )
                )
        elif "text" not in state:
            found.append(Violation(_pointer("states", index, "text"), "'text' is required"))
    if not bars:
        return found

    def refuse_naming(pointer: str, name: object, what: str) -> None:
        if isinstance(name, str) and name in bars:
            found.append(
                Violation(
                    pointer,
                    f"{name!r} is a {bars[name]} bar, which the machine passes through at "
                    f"once and is never in, so it cannot be {what}. Name a state.",
                )
            )

    refuse_naming("/initial", document.get("initial"), "where the machine starts")
    for index, name in enumerate(_listed(document, "final")):
        refuse_naming(_pointer("final", index), name, "where the machine ends")
    for index, group in enumerate(_listed(document, "groups")):
        if not isinstance(group, dict):
            continue
        refuse_naming(_pointer("groups", index, "initial"), group.get("initial"), "an entry")
        for number, region in enumerate(_listed(group, "regions")):
            if isinstance(region, dict):
                refuse_naming(
                    _pointer("groups", index, "regions", number, "initial"),
                    region.get("initial"),
                    "where a region starts",
                )

    into: dict[str, list[int]] = {bar: [] for bar in bars}
    out: dict[str, list[int]] = {bar: [] for bar in bars}
    transitions = _listed(document, "transitions")
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        if isinstance(source, str) and source in bars:
            if source == target:
                found.append(
                    Violation(
                        _pointer("transitions", index, "to"),
                        f"{source!r} is a {bars[source]} bar, and a bar is passed through, "
                        f"not stayed in: it has no self-loop.",
                    )
                )
                continue
            out[source].append(index)
            if "event" in transition:
                found.append(
                    Violation(
                        _pointer("transitions", index, "event"),
                        f"this transition leaves the {bars[source]} bar {source!r}, which "
                        f"the machine passes through at once, so there is no event to wait "
                        f"for. Put the event on the transition into the bar.",
                    )
                )
            if bars[source] == "fork" and "guard" in transition:
                found.append(
                    Violation(
                        _pointer("transitions", index, "guard"),
                        f"a fork starts every one of its arrows at once, so none of them "
                        f"can be guarded (UML forbids it). Put the guard on the transition "
                        f"into {source!r}.",
                    )
                )
        if isinstance(target, str) and target in bars and target != source:
            into[target].append(index)
            if bars[target] == "join":
                for part in ("event", "guard"):
                    if part in transition:
                        found.append(
                            Violation(
                                _pointer("transitions", index, part),
                                f"a join is passed when every arrow into it has arrived, "
                                f"each as its state completes, so an arrow into "
                                f"{target!r} has no {part} (UML forbids it). Move it to "
                                f"the transition into this arrow's state, or out of "
                                f"{target!r}.",
                            )
                        )

    for index, state in enumerate(_listed(document, "states")):
        if not isinstance(state, dict) or state.get("id") not in bars:
            continue
        bar = str(state["id"])
        kind = bars[bar]
        single, many = (into, out) if kind == "fork" else (out, into)
        one_way, many_way = ("in", "out") if kind == "fork" else ("out", "in")
        if len(single[bar]) != 1:
            found.append(
                Violation(
                    _pointer("transitions", single[bar][1], "to" if kind == "fork" else "from")
                    if len(single[bar]) > 1
                    else _pointer("states", index),
                    f"the {kind} {bar!r} has {len(single[bar])} transitions {one_way}; a "
                    f"{kind} has exactly one, "
                    + (
                        "which it splits into one per region."
                        if kind == "fork"
                        else "which leaves once every region has arrived."
                    ),
                )
            )
        if len(many[bar]) < 2:
            found.append(
                Violation(
                    _pointer("states", index),
                    f"the {kind} {bar!r} has {len(many[bar])} transition"
                    f"{'' if len(many[bar]) == 1 else 's'} {many_way}; a {kind} has two or "
                    f"more, one per region of a composite. With one, draw a plain "
                    f"transition instead.",
                )
            )
            continue
        ends = [
            (number, transitions[number].get("to" if kind == "fork" else "from"))
            for number in many[bar]
        ]
        found.extend(_bar_regions(bar, kind, ends, parent, region_of))
    return found


def _region_initials(
    document: Mapping[str, Any],
    groups: Mapping[str, Mapping[str, Any]],
    parent: Mapping[str, str],
    region_of: Mapping[str, int],
) -> list[Violation]:
    """Each region with no `initial` that the machine can enter without saying where.

    Entering a composite enters every region at its `initial`, and so does
    entering one state of one region for the others. Only a fork says where each
    region it reaches starts, so a region may go without an `initial` exactly when
    every way into its composite is a fork with an arrow into it.
    """
    bars = {
        state["id"]: state.get("role")
        for state in _listed(document, "states")
        if isinstance(state, dict) and state.get("role") in STATE_BARS
    }

    def inside(identifier: str, composite: str) -> bool:
        current: str | None = identifier
        seen: set[str] = set()
        while current is not None and current not in seen:
            if current == composite:
                return True
            seen.add(current)
            current = parent.get(current)
        return False

    found: list[Violation] = []
    for index, group in enumerate(_listed(document, "groups")):
        if not isinstance(group, dict) or group.get("id") not in groups:
            continue
        composite = str(group["id"])
        regions = _listed(group, "regions")
        missing = {
            number
            for number, region in enumerate(regions)
            if isinstance(region, dict) and "initial" not in region
        }
        if not missing:
            continue
        # Why each region would be entered with nowhere to start: the first reason.
        reasons: dict[int, str] = {}
        initial = document.get("initial")
        if isinstance(initial, str) and inside(initial, composite):
            for number in missing:
                reasons.setdefault(number, "the machine starts inside it")
        forks: dict[str, set[int]] = {}
        for transition in _listed(document, "transitions"):
            if not isinstance(transition, dict):
                continue
            source, target = transition.get("from"), transition.get("to")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if not inside(target, composite) or inside(source, composite):
                continue
            if target == composite:
                for number in missing:
                    reasons.setdefault(number, f"a transition from {source!r} enters it")
                continue
            region = _regions_above(target, parent, region_of).get(composite)
            if bars.get(source) == "fork":
                forks.setdefault(source, set()).add(region if region is not None else -1)
                continue
            for number in missing - {region}:
                reasons.setdefault(number, f"the transition from {source!r} to {target!r}")
        for fork, reached in forks.items():
            for number in missing - reached:
                reasons.setdefault(number, f"the fork {fork!r} has no arrow into it")
        for number in sorted(reasons):
            found.append(
                Violation(
                    _pointer("groups", index, "regions", number, "initial"),
                    f"this region of {composite!r} has no 'initial', and "
                    f"{reasons[number]}, so the machine would be in no state of it. Name "
                    f"where it starts, or reach it with an arrow from every fork into "
                    f"{composite!r}.",
                )
            )
    return found


def _bar_regions(
    bar: str,
    kind: str,
    ends: Sequence[tuple[int, object]],
    parent: Mapping[str, str],
    region_of: Mapping[str, int],
) -> list[Violation]:
    """A bar's far ends, each in a different region of one composite, or why not."""
    names = [end for _, end in ends if isinstance(end, str)]
    if len(names) != len(ends):
        return []
    above = [_regions_above(name, parent, region_of) for name in names]
    shared = set(above[0]).intersection(*above[1:])
    if any(len({regions[composite] for regions in above}) == len(names) for composite in shared):
        return []
    # The arrow that broke the rule: the first that shares a region with an
    # earlier one, or is in no region the others are in.
    position = next(
        (
            count - 1
            for count in range(2, len(names) + 1)
            if not any(
                len({regions[composite] for regions in above[:count]}) == count
                for composite in set(above[0]).intersection(*above[1:count])
            )
        ),
        len(names) - 1,
    )
    verb, end = ("starts", "end") if kind == "fork" else ("waits for", "start")
    return [
        Violation(
            _pointer("transitions", ends[position][0], "to" if kind == "fork" else "from"),
            f"the {kind} {bar!r} {verb} parts of the machine that run at once, so each of "
            f"its arrows must {end} in a different region of one composite state, and "
            f"{names[position]!r} is in no region the others share, or in the same region "
            f"as one of them. Give the composite 'regions', one per arrow.",
        )
    ]


def _crossing_regions(
    transitions: Sequence[Any], parent: Mapping[str, str], region_of: Mapping[str, int]
) -> list[Violation]:
    """Transitions from one region of a composite into another region of the same one.

    Regions are all current at once, so a state of one cannot hand the machine to
    a state of another: both are already running. UML forbids it, and there is no
    line to draw that would not claim the impossible.
    """

    def regions_above(identifier: str) -> dict[str, int]:
        return _regions_above(identifier, parent, region_of)

    found: list[Violation] = []
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        here, there = regions_above(source), regions_above(target)
        for composite, region in here.items():
            if composite in there and there[composite] != region:
                found.append(
                    Violation(
                        _pointer("transitions", index, "to"),
                        f"{source!r} and {target!r} are in different regions of "
                        f"{composite!r}, which run at once: neither can hand the machine to "
                        f"the other. Join them through a state outside {composite!r}, or "
                        f"put both in one region.",
                    )
                )
                break
    return found


def _states_document(document: Mapping[str, Any]) -> Document:
    """A state machine as the graph family reads it: states as nodes, transitions as edges.

    The transition's three parts are composed into the edge's label here, once,
    so the renderer never learns that a state machine has events.
    """
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        nodes=tuple(
            Node(id=entry["id"], text=entry.get("text", ""), role=entry.get("role", "step"))
            for entry in document["states"]
        ),
        initial=str(document["initial"]),
        final=tuple(document.get("final", ())),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=transition_label(
                    entry.get("event", ""), entry.get("guard", ""), entry.get("action", "")
                ),
                role=entry.get("role", "flow"),
            )
            for entry in document.get("transitions", ())
        ),
        groups=tuple(
            group for entry in document.get("groups", ()) for group in _composite_groups(entry)
        ),
    )


def region_id(composite: str, number: int) -> str:
    """The id a composite's region is drawn under: never one an author can write."""
    return f"({composite} region {number + 1})"


def _composite_groups(entry: Mapping[str, Any]) -> tuple[Group, ...]:
    """A composite as groups: itself, and for one with regions a frameless group per region."""
    regions = entry.get("regions")
    if not regions:
        return (
            Group(
                id=entry["id"],
                members=tuple(entry["members"]),
                text=entry["text"],
                initial=entry.get("initial", ""),
            ),
        )
    names = tuple(region_id(entry["id"], number) for number in range(len(regions)))
    return (
        Group(id=entry["id"], members=names, text=entry["text"]),
        *(
            Group(
                id=name,
                members=tuple(region["members"]),
                initial=region.get("initial", ""),
                region=True,
            )
            for name, region in zip(names, regions, strict=True)
        ),
    )
