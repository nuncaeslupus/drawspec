"""The `railroad` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from difflib import get_close_matches
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._constants import (
    RAILROAD_BOX_MAX,
    RAILROAD_BOXES,
    RAILROAD_BRANCH_MAX,
    RAILROAD_COMBINERS,
    RAILROAD_DEPTH_MAX,
    RAILROAD_SHAPES,
)
from drawspec.schema._model import Document, RailroadItem, RailroadRule, Violation

#: Why a railroad has no place for a field an author may reach for.
RAILROAD_REFUSED: Final = {
    "text": (
        "a box's words go in `terminal`, `rule` or `special` — which of the three says how it "
        "is drawn — and words on the track with no box in `comment`"
    ),
    "name": 'only a rule has a name; inside a track, refer to a rule with `{"rule": name}`',
    "max": (
        "a loop is drawn the same whatever its most, so a count is never drawn: say it in a "
        "`comment` as the `separator`, or write the item that many times in a `seq`"
    ),
    "times": (
        "a loop is drawn the same whatever its count: write the item that many times in a "
        "`seq`, or say it in a `comment`"
    ),
    "count": (
        "a loop is drawn the same whatever its count: write the item that many times in a "
        "`seq`, or say it in a `comment`"
    ),
    "default": (
        "the first branch of a `choice` is the one drawn on the main line: put the usual one first"
    ),
    "index": (
        "the first branch of a `choice` is the one drawn on the main line: put the usual one first"
    ),
    "skip": "an alternative that matches nothing is an `optional` round the `choice`",
    "empty": "an alternative that matches nothing is an `optional` round the `choice`",
    "role": (
        "an item is drawn by what it is — a terminal rounded, a rule square, a special dashed: "
        "say `terminal`, `rule` or `special` instead"
    ),
    "id": "nothing refers to an item: a rule is referred to by its `name`",
    "edges": (
        "a track's lines are derived from `seq`, `choice`, `optional` and `repeat`; arbitrary "
        "lines between boxes are a `flow`"
    ),
    "nodes": "a grammar is written as `rules`, each an `expr`",
}


def _railroad_refusal(violation: Violation) -> Violation:
    """A structural refusal in a railroad, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if "is not a known field" in violation.message and name in RAILROAD_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {RAILROAD_REFUSED[name]}.")
    if name == "seq" and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a 'seq' of fewer than 2 items is that item: write it on its own.",
        )
    if name == "choice" and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a 'choice' needs 2 alternatives at least; one is that item on its own, and one "
            "that may be left out is an 'optional'.",
        )
    return violation


def _railroad_children(entry: Mapping[str, Any], pointer: str) -> Iterator[tuple[object, str]]:
    """Every item directly inside `entry`, with its pointer."""
    for key in ("seq", "choice"):
        value = entry.get(key)
        if isinstance(value, list):
            for index, element in enumerate(value):
                yield element, f"{pointer}/{key}/{index}"
    for key in ("optional", "repeat", "separator"):
        value = entry.get(key)
        if isinstance(value, dict):
            yield value, f"{pointer}/{key}"


def _railroad_too_deep(document: Mapping[str, Any]) -> Violation | None:
    """The first item nested past `RAILROAD_DEPTH_MAX`, found without recursion.

    As `_sunburst_too_deep`: `railroad-item` refers to itself, the structural pass
    recurses once per level, and a pathologically deep document must come back as
    a located violation rather than a `RecursionError`.
    """
    rules = document.get("rules")
    if not isinstance(rules, list):
        return None
    stack: list[tuple[object, str, int]] = [
        (rule.get("expr"), f"/rules/{index}/expr", 1)
        for index, rule in enumerate(rules)
        if isinstance(rule, dict)
    ]
    while stack:
        entry, pointer, depth = stack.pop()
        if not isinstance(entry, dict):
            continue
        if depth > RAILROAD_DEPTH_MAX:
            return Violation(
                pointer,
                f"items nested {depth} deep are past what one track can be followed at — "
                f"{RAILROAD_DEPTH_MAX} at most. Make the inner part a rule of its own and "
                f'refer to it with {{"rule": name}}.',
            )
        stack.extend(
            (child, where, depth + 1) for child, where in _railroad_children(entry, pointer)
        )
    return None


def _railroad_words(value: object, pointer: str, what: str, found: list[Violation]) -> None:
    """A box's, a comment's or a name's words: present, and on one line."""
    if not isinstance(value, str):
        return
    if not value.strip():
        found.append(Violation(pointer, f"{what} needs words: an empty one is a blank box."))
    elif "\n" in value:
        found.append(
            Violation(
                pointer,
                f"{what} is one line on a track: a newline has nowhere to go. Shorten it, or "
                f"split it into two items in a 'seq'.",
            )
        )


def _railroad_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Each item one thing, its fields its own, every rule it names defined, and the caps."""
    found: list[Violation] = []
    rules = document.get("rules")
    if not isinstance(rules, list):
        return found

    defined: dict[str, int] = {}
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        name = rule.get("name")
        _railroad_words(name, f"/rules/{index}/name", "a rule's name", found)
        if isinstance(name, str) and name.strip():
            if name in defined:
                found.append(
                    Violation(
                        f"/rules/{index}/name",
                        f"a rule named {name!r} is already defined at /rules/{defined[name]}: "
                        f"each rule is drawn once, so merge the two with a 'choice'.",
                    )
                )
            else:
                defined[name] = index

    external: dict[str, int] = {}
    listed = document.get("external")
    if isinstance(listed, list):
        for index, name in enumerate(listed):
            if not isinstance(name, str):
                continue
            pointer = f"/external/{index}"
            _railroad_words(name, pointer, "an external rule's name", found)
            if name in defined:
                found.append(
                    Violation(
                        pointer,
                        f"{name!r} is defined in this document, at /rules/{defined[name]}, so it "
                        f"is not external: take it out of 'external'.",
                    )
                )
            elif name in external:
                found.append(Violation(pointer, f"{name!r} is listed twice in 'external'."))
            else:
                external[name] = index

    used: set[str] = set()
    known = sorted({*defined, *external})

    def check(entry: object, pointer: str, counter: list[int]) -> None:
        if not isinstance(entry, dict):
            return
        shapes = [shape for shape in RAILROAD_SHAPES if shape in entry]
        if not shapes:
            found.append(
                Violation(
                    pointer,
                    "an item needs to say what it is: one of "
                    + ", ".join(f"'{shape}'" for shape in RAILROAD_SHAPES)
                    + ".",
                )
            )
            return
        if len(shapes) > 1:
            found.append(
                Violation(
                    f"{pointer}/{shapes[1]}",
                    f"an item is one thing, and this one says both {shapes[0]!r} and "
                    f"{shapes[1]!r}. Put them one after the other in a 'seq', or one inside "
                    f"the other.",
                )
            )
            return
        shape = shapes[0]
        if shape != "repeat":
            for key in ("separator", "min"):
                if key in entry:
                    found.append(
                        Violation(
                            f"{pointer}/{key}",
                            f"{key!r} belongs to a 'repeat', and this item is a {shape!r}.",
                        )
                    )
        if shape in RAILROAD_BOXES:
            counter[0] += 1
            words = {
                "terminal": "a terminal",
                "rule": "a rule box",
                "special": "a special box",
                "comment": "a comment",
            }[shape]
            _railroad_words(entry[shape], f"{pointer}/{shape}", words, found)
            if shape == "rule" and isinstance(entry[shape], str) and entry[shape].strip():
                target = entry[shape]
                used.add(target)
                if target not in defined and target not in external:
                    close = get_close_matches(target, known, n=1)
                    hint = f" Did you mean {close[0]!r}?" if close else ""
                    found.append(
                        Violation(
                            f"{pointer}/rule",
                            f"no rule is named {target!r}: define it in 'rules', or list it in "
                            f"'external' if it is drawn elsewhere.{hint}",
                        )
                    )
            return
        branches = entry["choice"] if shape == "choice" else None
        if isinstance(branches, list) and len(branches) > RAILROAD_BRANCH_MAX:
            found.append(
                Violation(
                    f"{pointer}/choice",
                    f"{len(branches)} alternatives are past what one choice can be read at — "
                    f"{RAILROAD_BRANCH_MAX} at most. Group some under a rule of their own.",
                )
            )
        if shape == "optional" and isinstance(entry["optional"], dict):
            inner = entry["optional"]
            if "optional" in inner or (inner.get("repeat") is not None and inner.get("min") == 0):
                found.append(
                    Violation(
                        f"{pointer}/optional",
                        "this is already optional: a second bypass round it draws nothing new. "
                        "Take one away.",
                    )
                )
        if shape == "repeat":
            if "min" not in entry:
                found.append(
                    Violation(
                        f"{pointer}/min",
                        "a 'repeat' needs 'min': 1 for one or more, 0 for zero or more (a loop "
                        "that may also be skipped).",
                    )
                )
            elif isinstance(entry["min"], int) and entry["min"] not in (0, 1):
                found.append(
                    Violation(
                        f"{pointer}/min",
                        f"'min' is 0 or 1, not {entry['min']!r}: a loop is drawn the same "
                        f"whatever its count. Write the item that many times in a 'seq' before "
                        f"a repeat with min 0.",
                    )
                )
            separator = entry.get("separator")
            if isinstance(separator, dict) and any(key in separator for key in RAILROAD_COMBINERS):
                found.append(
                    Violation(
                        f"{pointer}/separator",
                        "a separator is one box or a comment — a 'terminal', 'rule', 'special' "
                        "or 'comment' — because it is read backwards along the loop. Make a "
                        "longer one a rule of its own.",
                    )
                )
        for child, where in _railroad_children(entry, pointer):
            check(child, where, counter)

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        counter = [0]
        check(rule.get("expr"), f"/rules/{index}/expr", counter)
        if counter[0] > RAILROAD_BOX_MAX:
            found.append(
                Violation(
                    f"/rules/{index}/expr",
                    f"{counter[0]} boxes on one track is past what one rule can be read at — "
                    f"{RAILROAD_BOX_MAX} at most. Factor part of it into a rule of its own, "
                    f"as SQLite's diagrams do.",
                )
            )

    for name, index in external.items():
        if name not in used:
            found.append(
                Violation(
                    f"/external/{index}",
                    f"no rule box refers to {name!r}, so listing it says nothing: take it out.",
                )
            )
    return found


def _railroad_item(entry: Mapping[str, Any], pointer: str) -> RailroadItem:
    """One railroad item and everything inside it, built from the validated mapping."""
    shape = next(shape for shape in RAILROAD_SHAPES if shape in entry)
    if shape in RAILROAD_BOXES:
        return RailroadItem(shape=shape, text=str(entry[shape]), pointer=pointer)
    if shape in ("seq", "choice"):
        return RailroadItem(
            shape=shape,
            items=tuple(
                _railroad_item(child, f"{pointer}/{shape}/{index}")
                for index, child in enumerate(entry[shape])
            ),
            pointer=pointer,
        )
    separator = entry.get("separator")
    return RailroadItem(
        shape=shape,
        items=(_railroad_item(entry[shape], f"{pointer}/{shape}"),),
        separator=_railroad_item(separator, f"{pointer}/separator") if separator else None,
        min=int(entry.get("min", 1)),
        pointer=pointer,
    )


def _railroad_document(document: Mapping[str, Any]) -> Document:
    """A railroad grammar: its rules in the order written, and the names it borrows."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        railroad_rules=tuple(
            RailroadRule(
                name=str(rule["name"]),
                expr=_railroad_item(rule["expr"], f"/rules/{index}/expr"),
                pointer=f"/rules/{index}",
            )
            for index, rule in enumerate(document["rules"])
        ),
        railroad_external=tuple(str(name) for name in document.get("external", ())),
    )
