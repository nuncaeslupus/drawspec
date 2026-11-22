"""The `wardley` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._constants import WARDLEY_DEPTH_MAX, WARDLEY_EVOLUTION
from drawspec.schema._model import Document, Violation, WardleyAnchor, WardleyComponent, WardleyNote

#: Why a Wardley map has no place for a field an author may reach for.
WARDLEY_REFUSED: Final = {
    "visibility": (
        "a component's height is its place in the value chain, derived from `needs`: one row "
        "below the lowest thing that needs it. To sink it further, give it a `depth` (a row)"
    ),
    "maturity": "say how evolved it is by name, in `evolution` (`late product`), not as a number",
    "position": (
        "a component's place is derived: across from its `evolution` stage, down from its "
        "place in the value chain. Neither is a coordinate"
    ),
    "at": "say where in its stage a component is with `early` or `late` in `evolution`",
    "stage": "the stage is written in `evolution` itself: `product`, `early product`, …",
    "edges": "a dependency is written on the component that has it, as `needs`",
    "role": (
        "a component is a dot and its name; what it is about goes in a numbered `note`, and an "
        "anchor is an anchor because it is in `anchors`"
    ),
    "label": "a component's name is its `text`, and drawspec places it clear of every line",
}


def _wardley_refusal(violation: Violation) -> Violation:
    """A structural refusal in a Wardley map, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    if name in WARDLEY_REFUSED and "is not" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {WARDLEY_REFUSED[name]}.")
    if name in ("evolution", "evolves") and (
        "is not one of" in violation.message or "expected string" in violation.message
    ):
        return Violation(
            violation.pointer,
            f"{name!r} is a named place on the evolution axis, not a number: one of "
            f"{', '.join(repr(value) for value in WARDLEY_EVOLUTION)}.",
        )
    return violation


def wardley_depths(
    anchors: Mapping[str, Sequence[str]],
    components: Mapping[str, Sequence[str]],
    pinned: Mapping[str, int],
) -> dict[str, int]:
    """Each component's row in the value chain, the anchors being row 0.

    One row below the lowest thing that needs it — the longest path down from an
    anchor — or its `depth`, when that is lower still. A component no anchor
    reaches is left out; a loop is refused by validation before this is asked.
    """
    depths: dict[str, int] = {}
    parents: dict[str, list[str]] = {name: [] for name in components}
    for owner, needs in (*anchors.items(), *components.items()):
        for need in dict.fromkeys(needs):
            if need in parents and need != owner:
                parents[need].append(owner)
    for name in _wardley_order(components):
        reached = [
            0 if p in anchors else depths[p] for p in parents[name] if p in anchors or p in depths
        ]
        if reached:
            depths[name] = max(1 + max(reached), pinned.get(name, 0))
    return depths


def _wardley_order(components: Mapping[str, Sequence[str]]) -> list[str]:
    """The components in dependency order: each after everything that needs it.

    Shorter than `components` when some of them need each other in a loop.
    """
    incoming = dict.fromkeys(components, 0)
    for owner, needs in components.items():
        for need in dict.fromkeys(needs):
            if need in incoming and need != owner:
                incoming[need] += 1
    ready = [name for name in components if incoming[name] == 0]
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for need in dict.fromkeys(components[name]):
            if need in incoming and need != name:
                incoming[need] -= 1
                if incoming[need] == 0:
                    ready.append(need)
    return order


def _wardley_needs(entry: Mapping[str, Any]) -> list[str]:
    needs = entry.get("needs", [])
    return [need for need in needs if isinstance(need, str)] if isinstance(needs, list) else []


def _wardley_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Unique ids, needs that resolve, no loop, everything anchored, rightward moves."""
    found: list[Violation] = []
    raw_anchors = document.get("anchors", ())
    raw_components = document.get("components", ())
    anchors = (
        [a for a in raw_anchors if isinstance(a, dict)] if isinstance(raw_anchors, list) else []
    )
    components = (
        [c for c in raw_components if isinstance(c, dict)]
        if isinstance(raw_components, list)
        else []
    )
    seen: set[str] = set()
    for group, entries in (("anchors", anchors), ("components", components)):
        for index, entry in enumerate(entries):
            here = f"/{group}/{index}"
            ident = entry.get("id")
            if isinstance(ident, str):
                if ident in seen:
                    found.append(
                        Violation(f"{here}/id", f"{ident!r} is used twice: an id names one thing.")
                    )
                seen.add(ident)
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(Violation(f"{here}/text", "a component needs a name."))
            elif isinstance(text, str) and "\n" in text:
                found.append(
                    Violation(
                        f"{here}/text",
                        "a name on a Wardley map is one line, set beside its dot; put the detail "
                        "in a numbered `note`.",
                    )
                )
    anchor_ids = {a["id"] for a in anchors if isinstance(a.get("id"), str)}
    component_ids = {c["id"] for c in components if isinstance(c.get("id"), str)}

    for group, entries in (("anchors", anchors), ("components", components)):
        for index, entry in enumerate(entries):
            ident = entry.get("id")
            listed: set[str] = set()
            for position, need in enumerate(_wardley_needs(entry)):
                where = f"/{group}/{index}/needs/{position}"
                if need == ident:
                    found.append(Violation(where, "a component cannot need itself."))
                elif need in anchor_ids:
                    found.append(
                        Violation(
                            where,
                            f"{need!r} is an anchor: an anchor is the user at the top of the "
                            f"chain, so nothing needs it.",
                        )
                    )
                elif need not in component_ids:
                    found.append(Violation(where, f"{need!r} is not the id of any component."))
                elif need in listed:
                    found.append(Violation(where, f"{need!r} is listed twice."))
                listed.add(need)

    anchor_needs = {a["id"]: _wardley_needs(a) for a in anchors if isinstance(a.get("id"), str)}
    component_needs = {
        c["id"]: _wardley_needs(c) for c in components if isinstance(c.get("id"), str)
    }
    order = _wardley_order(component_needs)
    if len(order) < len(component_needs):
        looped = sorted(set(component_needs) - set(order))
        found.append(
            Violation(
                "/components",
                f"{', '.join(repr(name) for name in looped)} need each other in a loop. A value "
                f"chain only runs down: each component sits below what needs it.",
            )
        )
        return found
    pinned = {
        c["id"]: c["depth"]
        for c in components
        if isinstance(c.get("id"), str)
        and isinstance(c.get("depth"), int)
        and not isinstance(c.get("depth"), bool)
    }
    depths = wardley_depths(anchor_needs, component_needs, {})
    for index, entry in enumerate(components):
        ident = entry.get("id")
        if not isinstance(ident, str):
            continue
        here = f"/components/{index}"
        if ident not in depths:
            found.append(
                Violation(
                    here,
                    f"nothing on the map needs {ident!r}, so it has no place in the value chain. "
                    f"A Wardley map hangs from its anchors: list it in the `needs` of what "
                    f"depends on it.",
                )
            )
            continue
        depth = pinned.get(ident)
        if depth is not None and depth < depths[ident]:
            found.append(
                Violation(
                    f"{here}/depth",
                    f"row {depth} is above what needs {ident!r}: it can sit no higher than row "
                    f"{depths[ident]}. Leave `depth` out, or sink it lower.",
                )
            )
        evolution, evolves = entry.get("evolution"), entry.get("evolves")
        if (
            evolution in WARDLEY_EVOLUTION
            and evolves in WARDLEY_EVOLUTION
            and WARDLEY_EVOLUTION.index(evolves) <= WARDLEY_EVOLUTION.index(evolution)
        ):
            found.append(
                Violation(
                    f"{here}/evolves",
                    f"{evolves!r} is not further right than {evolution!r}: a component "
                    f"evolves towards commodity, so `evolves` names a later place.",
                )
            )
    if not found:
        rows = max(wardley_depths(anchor_needs, component_needs, pinned).values(), default=0)
        if rows > WARDLEY_DEPTH_MAX:
            found.append(
                Violation(
                    "/components",
                    f"the value chain is {rows} rows deep, past the {WARDLEY_DEPTH_MAX} one map "
                    f"can be read at. Fold a run of components into one, or map the lower part "
                    f"on a map of its own.",
                )
            )
    notes = document.get("notes", ())
    if isinstance(notes, list):
        for index, note in enumerate(notes):
            if not isinstance(note, dict):
                continue
            text = note.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(Violation(f"/notes/{index}/text", "a note needs words."))
            on = note.get("on", [])
            for position, target in enumerate(on if isinstance(on, list) else []):
                if isinstance(target, str) and target not in seen:
                    found.append(
                        Violation(
                            f"/notes/{index}/on/{position}",
                            f"{target!r} is not the id of any anchor or component.",
                        )
                    )
    return found


def _wardley_document(document: Mapping[str, Any]) -> Document:
    """A Wardley map: its anchors, components and notes, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        wardley_anchors=tuple(
            WardleyAnchor(
                id=str(entry["id"]),
                text=str(entry["text"]),
                needs=tuple(str(need) for need in entry["needs"]),
            )
            for entry in document["anchors"]
        ),
        wardley_components=tuple(
            WardleyComponent(
                id=str(entry["id"]),
                text=str(entry["text"]),
                evolution=str(entry["evolution"]),
                needs=tuple(str(need) for need in entry.get("needs", ())),
                depth=int(entry["depth"]) if "depth" in entry else None,
                evolves=str(entry.get("evolves", "")),
                inertia=bool(entry.get("inertia", False)),
            )
            for entry in document["components"]
        ),
        wardley_notes=tuple(
            WardleyNote(text=str(entry["text"]), on=tuple(str(target) for target in entry["on"]))
            for entry in document.get("notes", ())
        ),
    )
