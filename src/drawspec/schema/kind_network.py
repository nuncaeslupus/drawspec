"""The `network` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._constants import NETWORK_HOST_MAX, NETWORK_HOST_ROLES, NETWORK_MAX
from drawspec.schema._model import Document, NetworkGroup, NetworkHost, NetworkSegment, Violation

#: Why a network diagram has no place for a field an author may reach for.
NETWORK_REFUSED: Final = {
    "column": (
        "a host's column is drawspec's: chosen for the fewest lines hopping over a bus they "
        "are not on, then as few columns and as close to the order written as that allows"
    ),
    "order": (
        "the networks are drawn in the order written and the columns are derived from the "
        "attachments; reorder the `networks` array to move a bus"
    ),
    "icon": (
        "drawspec draws no device icons: a host is a box (`store` a drum, `person` a client), "
        "and its words say what it is — `fw01 (firewall)`"
    ),
    "shape": (
        "a host's shape comes from its `role`: `step` a box, `store` a drum, `person` a client"
    ),
    "edges": (
        "a network diagram joins hosts to buses, not hosts to hosts: put both hosts on a "
        "network. For links between boxes, draw a `flow`"
    ),
    "color": "appearance is the theme's: a network's bus is drawn the same as every other",
    "colour": "appearance is the theme's: a network's bus is drawn the same as every other",
}


#: What a device role an author may reach for is, in drawspec's vocabulary.
NETWORK_ROLE_HINTS: Final = {
    "router": "a router is a host on two networks: leave the role out and name it",
    "firewall": "a firewall is a host on the networks it divides: leave the role out and name it",
    "switch": "a switch is the network itself: make it one of the `networks`",
    "server": "a server is the default box: leave the role out",
    "database": "a database is `store`, drawn as a drum",
    "storage": "a storage array is `store`, drawn as a drum",
    "cloud": "the internet is a network: make it the first of the `networks`",
    "internet": "the internet is a network: make it the first of the `networks`",
    "client": "a user's machine is `person`",
    "user": "a user's machine is `person`",
}


def _network_refusal(violation: Violation) -> Violation:
    """A structural refusal in a network diagram, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if "is not a known field" in violation.message and name in NETWORK_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {NETWORK_REFUSED[name]}.")
    if name == "role" and "is not one of" in violation.message:
        value = violation.message.split(" is not one of", 1)[0].strip("'\"")
        hint = NETWORK_ROLE_HINTS.get(value.lower())
        if hint:
            return Violation(
                violation.pointer,
                f"{value!r} is not a host role ({', '.join(NETWORK_HOST_ROLES)}): {hint}. "
                f"drawspec draws no device icons.",
            )
    return violation


def _network_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that land, no empty bus, and groups that hold.

    A host on two networks that are not neighbours stands outside every bus
    between them when some column order lets it; when none does, its line hops
    over that bus in the drawing, which is not a fault of the document. What no
    order can draw honestly is a group's backdrop free of a stranger's box, and
    that is refused here, at the group, before any layout runs.
    """
    from drawspec.buses import arrange

    found: list[Violation] = []
    networks: dict[str, int] = {}
    # Whether every entry is whole enough to arrange: a network skipped here keeps
    # its slot, so a host on a later one would name an index past the count.
    whole = True
    for index, entry in enumerate(_listed(document, "networks")):
        if not isinstance(entry, dict):
            whole = False
            continue
        identifier = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(Violation(_pointer("networks", index, "text"), "a network needs a name."))
        if not isinstance(identifier, str):
            whole = False
            continue
        if identifier in networks:
            found.append(
                Violation(_pointer("networks", index, "id"), f"duplicate network id {identifier!r}")
            )
            whole = False
            continue
        networks[identifier] = index

    hosts: dict[str, int] = {}
    attached: list[list[int]] = []
    used: set[int] = set()
    for index, entry in enumerate(_listed(document, "hosts")):
        if not isinstance(entry, dict):
            whole = False
            continue
        identifier = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(Violation(_pointer("hosts", index, "text"), "a host needs a name."))
        if isinstance(identifier, str):
            if identifier in hosts or identifier in networks:
                what = "host" if identifier in hosts else "network"
                found.append(
                    Violation(
                        _pointer("hosts", index, "id"),
                        f"{identifier!r} is already the id of a {what}: every id names one thing.",
                    )
                )
            else:
                hosts[identifier] = index
        on: list[int] = []
        for position, item in enumerate(_listed(entry, "networks")):
            if not isinstance(item, dict) or not isinstance(item.get("network"), str):
                whole = False
                continue
            name = item["network"]
            pointer = _pointer("hosts", index, "networks", position, "network")
            if name not in networks:
                found.append(
                    Violation(
                        pointer, f"{name!r} is not the id of any network" + _closest(name, networks)
                    )
                )
                whole = False
                continue
            if networks[name] in on:
                found.append(
                    Violation(
                        pointer,
                        f"this host is on {name!r} already: one line per network. Two addresses "
                        f"on one network go in one `address`, `.1, .2`.",
                    )
                )
                continue
            on.append(networks[name])
        if not on:
            whole = False
        used.update(on)
        attached.append(on)

    for name, index in networks.items():
        if index not in used and whole:
            found.append(
                Violation(
                    _pointer("networks", index),
                    f"no host is on {name!r}: an empty bus says nothing. Put a host on it, or "
                    f"leave it out.",
                )
            )

    members: list[list[int]] = []
    owner: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "groups")):
        if not isinstance(entry, dict):
            whole = False
            continue
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(
                Violation(
                    _pointer("groups", index, "text"),
                    "a group's name needs words, or leave `text` out.",
                )
            )
        listed: list[int] = []
        for position, member in enumerate(_listed(entry, "members")):
            if not isinstance(member, str):
                whole = False
                continue
            pointer = _pointer("groups", index, "members", position)
            if member not in hosts:
                found.append(
                    Violation(
                        pointer, f"{member!r} is not the id of any host" + _closest(member, hosts)
                    )
                )
                whole = False
                continue
            if member in owner:
                where = "this group" if owner[member] == index else f"group {owner[member]}"
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is in {where} already: a host stands on one backdrop.",
                    )
                )
                continue
            owner[member] = index
            listed.append(hosts[member])
        members.append(listed)

    if found or not whole or not attached or len(hosts) != len(attached):
        return found
    if len(networks) > NETWORK_MAX or len(attached) > NETWORK_HOST_MAX:
        return found  # the budget refuses it, and the search would be slow for nothing

    arrangement = arrange(len(networks), attached, members)
    named = {index: identifier for identifier, index in hosts.items()}
    for group, other in arrangement.clashes[:1]:
        if other >= 0:
            message = (
                f"no column order keeps this group's hosts together without host "
                f"{named[other]!r} standing on its backdrop too. Add it to the group, or group "
                f"fewer."
            )
        else:
            message = (
                f"no column order keeps this group's backdrop clear of group {-1 - other}'s. "
                f"Merge the two, or group fewer hosts."
            )
        found.append(Violation(_pointer("groups", group, "members"), message))
    return found


def _network_document(document: Mapping[str, Any]) -> Document:
    """A network diagram: its buses, its hosts and its groups, in the order written."""
    order = {entry["id"]: index for index, entry in enumerate(document["networks"])}

    def host(entry: Mapping[str, Any]) -> NetworkHost:
        attached = sorted(entry["networks"], key=lambda item: order[item["network"]])
        return NetworkHost(
            id=str(entry["id"]),
            text=str(entry.get("text", entry["id"])),
            role=str(entry.get("role", "step")),
            networks=tuple(str(item["network"]) for item in attached),
            addresses=tuple(str(item.get("address", "")) for item in attached),
        )

    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        networks=tuple(
            NetworkSegment(
                id=str(entry["id"]),
                text=str(entry.get("text", entry["id"])),
                address=str(entry.get("address", "")),
            )
            for entry in document["networks"]
        ),
        hosts=tuple(host(entry) for entry in document["hosts"]),
        host_groups=tuple(
            NetworkGroup(
                text=str(entry.get("text", "")),
                members=tuple(str(member) for member in entry["members"]),
            )
            for entry in document.get("groups", ())
        ),
    )
