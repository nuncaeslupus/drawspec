"""The `entities` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer, _reaches
from drawspec.schema._constants import FIELD_PLACEHOLDERS, HIERARCHY_ROLES, TAG_MAX
from drawspec.schema._model import Document, Entity, EntityField, Relation, Violation


def _entities_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What an entity diagram may not be: ids that do not land, and relations that cannot draw.

    Entity ids once each and field ids once in the document; every relation's
    ends an entity and every `from_field`/`to_field` a field *of that end's*
    entity; no relation of an entity to itself; a `...` row only last, and
    plain; no cardinality on a hierarchy relation, and no hierarchy that loops.
    """
    found: list[Violation] = []
    entities: dict[str, int] = {}
    owner: dict[str, str] = {}
    for index, entity in enumerate(_listed(document, "entities")):
        if not isinstance(entity, dict):
            continue
        identifier = entity.get("id")
        if isinstance(identifier, str):
            if identifier in entities:
                found.append(
                    Violation(
                        _pointer("entities", index, "id"), f"duplicate entity id {identifier!r}"
                    )
                )
            else:
                entities[identifier] = index
        tag = entity.get("tag")
        if isinstance(tag, str) and len(tag) > TAG_MAX:
            found.append(
                Violation(
                    _pointer("entities", index, "tag"),
                    f"a tag is a stereotype — a word or two — and this one is {len(tag)} "
                    f"characters; {TAG_MAX} at most. Put a description in the name or the "
                    f"surrounding prose.",
                )
            )
        fields = entity.get("fields")
        rows = fields if isinstance(fields, list) else []
        for row, field in enumerate(rows):
            if not isinstance(field, dict):
                continue
            where = ("entities", index, "fields", row)
            text = field.get("text")
            if isinstance(text, str) and text.strip() in FIELD_PLACEHOLDERS:
                if row != len(rows) - 1:
                    found.append(
                        Violation(
                            _pointer(*where, "text"),
                            "a `...` field stands for the fields not shown, so it comes "
                            "last. Move it to the end of this entity's fields.",
                        )
                    )
                for name in ("id", "type", "key"):
                    if name in field:
                        found.append(
                            Violation(
                                _pointer(*where, name),
                                f"a `...` field stands for fields not shown, so it has no "
                                f"{name} of its own. Delete it.",
                            )
                        )
            if isinstance(text, str) and "\n" in text:
                found.append(
                    Violation(
                        _pointer(*where, "text"),
                        "a field is one row: write its name on one line, and its type in `type`.",
                    )
                )
            field_id = field.get("id")
            if isinstance(field_id, str) and isinstance(identifier, str):
                if field_id in owner:
                    found.append(
                        Violation(_pointer(*where, "id"), f"duplicate field id {field_id!r}")
                    )
                else:
                    owner[field_id] = identifier
        text = entity.get("text")
        if isinstance(text, str) and "\n" in text:
            found.append(
                Violation(
                    _pointer("entities", index, "text"),
                    "an entity's name is one line — what it holds goes in `fields`, and a "
                    "stereotype in `tag`.",
                )
            )

    hierarchy: dict[str, list[str]] = {}
    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        ends: dict[str, str] = {}
        for end in ("from", "to"):
            target = edge.get(end)
            if not isinstance(target, str):
                continue
            if target not in entities:
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{target!r} is not the id of any entity in this document"
                        + _closest(target, entities),
                    )
                )
                continue
            ends[end] = target
        if ends.get("from") is not None and ends.get("from") == ends.get("to"):
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    "a relation from an entity to itself is not drawn: name the field that "
                    "holds the reference (`manager_id`, key `foreign`) and say what it "
                    "points at in its text, or draw the two roles as two entities.",
                )
            )
        for end in ("from", "to"):
            named = edge.get(f"{end}_field")
            if not isinstance(named, str) or end not in ends:
                continue
            if named not in owner:
                found.append(
                    Violation(
                        _pointer("edges", index, f"{end}_field"),
                        f"{named!r} is not the id of any field in this document"
                        + _closest(named, owner),
                    )
                )
            elif owner[named] != ends[end]:
                found.append(
                    Violation(
                        _pointer("edges", index, f"{end}_field"),
                        f"{named!r} is a field of {owner[named]!r}, not of {ends[end]!r}: "
                        f"the line would leave a box from a row it does not have.",
                    )
                )
        role = edge.get("role", "link")
        if role == "owns" and "to_end" in edge:
            found.append(
                Violation(
                    _pointer("edges", index, "to_end"),
                    "the `to` end of `owns` is the whole, drawn as the diamond, and a part "
                    "belongs to exactly one whole — there is no count to draw there. Delete "
                    "'to_end'; say how many parts with 'from_end'.",
                )
            )
        if role in HIERARCHY_ROLES:
            for name in ("from_end", "to_end", "from_field", "to_field"):
                if name in edge:
                    what = "cardinality" if name.endswith("_end") else "row to land on"
                    found.append(
                        Violation(
                            _pointer("edges", index, name),
                            f"{role!r} says one class is a kind of another, which has no "
                            f"{what}: inheritance is between whole classes, one to one. "
                            f"Delete {name!r}.",
                        )
                    )
            if "from" in ends and "to" in ends and ends["from"] != ends["to"]:
                if _reaches(hierarchy, ends["to"], ends["from"]):
                    found.append(
                        Violation(
                            _pointer("edges", index),
                            f"this {role!r} closes a loop: {ends['to']!r} is already, "
                            f"through others, a kind of {ends['from']!r}. A hierarchy has "
                            f"a top; delete the relation that is the wrong way round.",
                        )
                    )
                else:
                    hierarchy.setdefault(ends["from"], []).append(ends["to"])

    # A star: one entity in the middle, the rest round it. A class hierarchy is
    # drawn general above specific, which a ring round a middle cannot keep.
    middles = [
        index
        for index, entity in enumerate(_listed(document, "entities"))
        if isinstance(entity, dict) and entity.get("centre") is True
    ]
    for index in middles[1:]:
        found.append(
            Violation(
                _pointer("entities", index, "centre"),
                "a second entity says it is the centre. A star has one middle: the fact "
                "table. Drop 'centre' here, or split the diagram into one star per fact.",
            )
        )
    if middles:
        for index, edge in enumerate(_listed(document, "edges")):
            if isinstance(edge, dict) and edge.get("role") in HIERARCHY_ROLES:
                found.append(
                    Violation(
                        _pointer("entities", middles[0], "centre"),
                        f"edge {index} is {edge['role']!r}, and a class hierarchy is drawn "
                        f"general above specific; arranged round a middle, a subclass could "
                        f"land above its parent. Drop 'centre', or draw the hierarchy in a "
                        f"diagram of its own.",
                    )
                )
                break
    return found


def _entities_document(document: Mapping[str, Any]) -> Document:
    """An entity diagram: its boxes with their rows, and relations with their ends."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        entities=tuple(
            Entity(
                id=entry["id"],
                text=entry["text"],
                role=entry.get("role", "step"),
                tag=entry.get("tag", ""),
                fields=tuple(
                    EntityField(
                        text=field["text"],
                        type=field.get("type", ""),
                        key=field.get("key", ""),
                        id=field.get("id", ""),
                    )
                    for field in entry.get("fields", ())
                ),
                operations=tuple(entry.get("operations", ())),
                centre=bool(entry.get("centre", False)),
            )
            for entry in document["entities"]
        ),
        relations=tuple(
            Relation(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "link"),
                source_field=entry.get("from_field", ""),
                target_field=entry.get("to_field", ""),
                source_end=entry.get("from_end", ""),
                target_end=entry.get("to_end", ""),
            )
            for entry in document.get("edges", ())
        ),
    )
