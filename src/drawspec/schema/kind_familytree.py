"""The `familytree` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import (
    FAMILYTREE_GENERATION_MAX,
    FAMILYTREE_PARTNER_MAX,
    FAMILYTREE_PREGNANCIES,
    FAMILYTREE_TWIN_MAX,
)
from drawspec.schema._model import Document, FamilyCouple, FamilyPerson, FamilyTwins, Violation

#: Why a family tree has no place for a field an author may reach for.
FAMILYTREE_REFUSED: Final = {
    "edges": "a family tree's lines are its `couples`: partners, and the children of each",
    "nodes": "a family tree's symbols are its `people`",
    "groups": "a family's branches are drawn from its `couples`; split a tree by branch instead",
    "generation": (
        "generations are derived: a child is one row below its parents' couple, a partner "
        "shares their partner's row"
    ),
    "number": "people are numbered for you, left to right in each generation (II-3)",
    "parents": "a person's parents are the couple whose `children` list them",
    "children": "a person's children are listed on the couple they had them with, in `couples`",
    "partner": "partners are a couple: `couples: [{between: [a, b]}]`, in marriage order",
    "partners": "partners are couples: one `{between: [a, b]}` per partner, in marriage order",
    "spouse": "partners are a couple: `couples: [{between: [a, b]}]`",
    "twin": "twins are written on their parents' couple: `twins: [{of: [a, b], zygosity}]`",
    "ancestors": (
        "a family tree draws couples and all their children; a chart of one person's "
        "ancestors only is a binary tree — draw it as a `tree`"
    ),
}


def _familytree_refusal(violation: Violation) -> Violation:
    """A structural refusal in a family tree, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if "is not a known field" in violation.message and name in FAMILYTREE_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {FAMILYTREE_REFUSED[name]}.")
    if name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A person's shape is their `sex` and their shading their `status`; `role` is "
            "`step`, or `emphasis` for the person the figure is about.",
        )
    if name == "status" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A family tree tracks one trait; a second condition is a second tree. A "
            "pregnancy loss is `pregnancy: loss`, and death is `deceased`.",
        )
    return violation


def _familytree_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that resolve, one set of parents each, rows that agree, and one family."""
    found: list[Violation] = []
    people = [
        (index, entry)
        for index, entry in enumerate(_listed(document, "people"))
        if isinstance(entry, dict)
    ]
    ids: dict[str, int] = {}
    for index, entry in people:
        name = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(
                Violation(
                    _pointer("people", index, "text"),
                    "an empty name: leave `text` out for a person drawn by number only.",
                )
            )
        if not isinstance(name, str):
            continue
        if name in ids:
            found.append(
                Violation(
                    _pointer("people", index, "id"),
                    f"{name!r} is already the id of person {ids[name]}: ids are unique.",
                )
            )
        else:
            ids[name] = index
    person = {name: dict(people)[index] for name, index in ids.items()}

    probands = [index for index, entry in people if entry.get("proband") is True]
    for index in probands[1:]:
        found.append(
            Violation(
                _pointer("people", index, "proband"),
                f"a family tree has one proband, and person {probands[0]} is already it. "
                f"Anyone else who asked for advice or testing is a `consultand`.",
            )
        )
    for index, entry in people:
        pregnancy = entry.get("pregnancy")
        if pregnancy == "loss" and entry.get("deceased") is True:
            found.append(
                Violation(
                    _pointer("people", index, "deceased"),
                    "a pregnancy loss is its own symbol, a small triangle; `deceased` is for "
                    "someone who was born.",
                )
            )
        if pregnancy == "ongoing" and entry.get("status") in ("affected", "carrier"):
            found.append(
                Violation(
                    _pointer("people", index, "status"),
                    "an ongoing pregnancy carries a `P` in its symbol, so it is not shaded: "
                    "write a prenatal result in `text`.",
                )
            )

    # Couples: two known, distinct partners; known children, each with one set of
    # parents; twins next to each other among them.
    couples = [
        (index, entry)
        for index, entry in enumerate(_listed(document, "couples"))
        if isinstance(entry, dict)
    ]
    pairs: dict[frozenset[str], int] = {}
    partners: dict[str, list[tuple[int, str]]] = {name: [] for name in ids}
    parents_of: dict[str, int] = {}
    valid: list[tuple[int, tuple[str, str], list[str]]] = []
    # Everyone a couple names, valid or not: a refused couple is reported once, not
    # again as people in no couple.
    mentioned: set[object] = set()
    for _, entry in couples:
        for field_name in ("between", "children"):
            listed = entry.get(field_name)
            if isinstance(listed, list):
                mentioned.update(each for each in listed if isinstance(each, str))
    for index, entry in couples:
        between = entry.get("between")
        where = _pointer("couples", index, "between")
        if not isinstance(between, list):
            continue
        if len(between) != 2:
            if len(between) > 2:
                found.append(
                    Violation(
                        where,
                        f"a couple is two people, and this names {len(between)}. A person with "
                        f"several partners is in one couple per partner, in marriage order.",
                    )
                )
            continue
        names = [name for name in between if isinstance(name, str)]
        if len(names) != 2:
            continue
        bad = False
        for position, name in enumerate(names):
            if name not in ids:
                found.append(
                    Violation(
                        _pointer("couples", index, "between", position),
                        f"{name!r} is not the id of a person. Known ids: "
                        f"{', '.join(sorted(ids)) or 'none'}.",
                    )
                )
                bad = True
        if bad:
            continue
        if names[0] == names[1]:
            found.append(
                Violation(where, f"a couple is two people; this names {names[0]!r} twice.")
            )
            continue
        key = frozenset(names)
        if key in pairs:
            found.append(
                Violation(
                    where,
                    f"{names[0]!r} and {names[1]!r} are already couple {pairs[key]}: list all "
                    f"their children there.",
                )
            )
            continue
        pairs[key] = index
        for name in names:
            if person[name].get("pregnancy") in FAMILYTREE_PREGNANCIES:
                found.append(
                    Violation(
                        where,
                        f"{name!r} is a pregnancy, which is drawn as a child only: it has no "
                        f"partners.",
                    )
                )
                bad = True
        if bad:
            continue
        for name in names:
            partners[name].append((index, names[1] if name == names[0] else names[0]))
        kids: list[str] = []
        children = entry.get("children")
        for position, child in enumerate(children if isinstance(children, list) else []):
            if not isinstance(child, str):
                continue
            here = _pointer("couples", index, "children", position)
            if child not in ids:
                found.append(
                    Violation(
                        here,
                        f"{child!r} is not the id of a person. Known ids: "
                        f"{', '.join(sorted(ids)) or 'none'}.",
                    )
                )
            elif child in names:
                found.append(
                    Violation(here, f"{child!r} is a partner in this couple, not a child.")
                )
            elif child in kids:
                found.append(Violation(here, f"{child!r} is already a child of this couple."))
            elif child in parents_of:
                found.append(
                    Violation(
                        here,
                        f"{child!r} is already a child of couple {parents_of[child]}: a person "
                        f"has one set of parents. An adopted child is listed once, in the couple "
                        f"that raised them, with `adopted: true`.",
                    )
                )
            else:
                parents_of[child] = index
                kids.append(child)
        twinned: set[str] = set()
        twins = entry.get("twins")
        for position, birth in enumerate(twins if isinstance(twins, list) else []):
            members = birth.get("of") if isinstance(birth, dict) else None
            if not isinstance(members, list):
                continue
            here = _pointer("couples", index, "twins", position, "of")
            named = [member for member in members if isinstance(member, str)]
            if len(named) > FAMILYTREE_TWIN_MAX:
                found.append(
                    Violation(
                        here,
                        f"{len(named)} children of one birth, and a tree draws "
                        f"{FAMILYTREE_TWIN_MAX} at most from one point. Write the number in a "
                        f"`caption`, and the children as ordinary siblings.",
                    )
                )
                continue
            strays = [member for member in named if member not in kids]
            if strays:
                found.append(
                    Violation(
                        here,
                        f"{strays[0]!r} is not one of this couple's `children`: twins are "
                        f"children of the couple they are written on.",
                    )
                )
                continue
            if len(set(named)) != len(named) or twinned & set(named):
                found.append(
                    Violation(here, "a child is in one set of twins, and named once in it.")
                )
                continue
            places = sorted(kids.index(member) for member in named)
            if places != list(range(places[0], places[0] + len(places))):
                found.append(
                    Violation(
                        here,
                        f"twins {', '.join(repr(member) for member in named)} are not next to "
                        f"each other in `children`: children of one birth are drawn from one "
                        f"point, so write them together.",
                    )
                )
                continue
            twinned.update(named)
        valid.append((index, (names[0], names[1]), kids))

    for name, mine in partners.items():
        for index, _ in mine[FAMILYTREE_PARTNER_MAX:]:
            found.append(
                Violation(
                    _pointer("couples", index, "between"),
                    f"{name!r} is in {len(mine)} couples, past what one row can draw — "
                    f"{FAMILYTREE_PARTNER_MAX} partners at most. Draw the later partners' "
                    f"families as a tree of their own.",
                )
            )
    for name, index in ids.items():
        entry = person[name]
        if entry.get("adopted") is True and name not in parents_of:
            found.append(
                Violation(
                    _pointer("people", index, "adopted"),
                    f"{name!r} is adopted, but no couple lists them among its `children`: "
                    f"list them in the couple that raised them.",
                )
            )
        if name not in mentioned:
            found.append(
                Violation(
                    _pointer("people", index),
                    f"{name!r} is in no couple, as a partner or a child, so nothing places "
                    f"them in the tree.",
                )
            )
    if found:
        return found

    # Descent goes one way: nobody is their own ancestor.
    below: dict[str, list[str]] = {name: [] for name in ids}
    for _, pair, kids in valid:
        for parent in pair:
            below[parent].extend(kids)
    state: dict[str, int] = {}

    def cycle(name: str, trail: list[str]) -> list[str] | None:
        state[name] = 1
        for child in below[name]:
            if state.get(child) == 1:
                return [*trail, name, child]
            if child not in state:
                looped = cycle(child, [*trail, name])
                if looped:
                    return looped
        state[name] = 2
        return None

    for name in ids:
        if name not in state:
            looped = cycle(name, [])
            if looped:
                begin = looped.index(looped[-1])
                return [
                    Violation(
                        _pointer("couples", parents_of[looped[-1]], "children"),
                        f"descent goes round in a circle ({' -> '.join(looped[begin:])}): "
                        f"nobody is their own ancestor.",
                    )
                ]

    # Generations: partners share a row, a child is one row below its couple.
    generation: dict[str, int] = {}
    links: dict[str, list[tuple[str, int, int]]] = {name: [] for name in ids}
    for index, pair, kids in valid:
        links[pair[0]].append((pair[1], 0, index))
        links[pair[1]].append((pair[0], 0, index))
        for child in kids:
            for parent in pair:
                links[parent].append((child, 1, index))
                links[child].append((parent, -1, index))
    families = 0
    for start in ids:
        if start in generation:
            continue
        families += 1
        if families > 1:
            return [
                Violation(
                    _pointer("people", ids[start]),
                    f"{start!r} is not related to {next(iter(ids))!r} through any couple: one "
                    f"family tree is one family. Draw the other family as a tree of its own.",
                )
            ]
        generation[start] = 0
        # Parents and children first, partners only when nothing else is left: so
        # a contradiction surfaces at the couple whose partners cannot share a row.
        queue = [start]
        later: list[tuple[str, str, int]] = []
        while queue or later:
            if not queue:
                current, other, index = later.pop(0)
                if other not in generation:
                    generation[other] = generation[current]
                    queue.append(other)
                elif generation[other] != generation[current]:
                    return [
                        Violation(
                            _pointer("couples", index, "between"),
                            f"{current!r} and {other!r} are partners, but their descent puts "
                            f"them {abs(generation[other] - generation[current])} generation(s) "
                            f"apart, and partners share a row. A family where they cannot is "
                            f"drawn as two trees.",
                        )
                    ]
                continue
            current = queue.pop(0)
            for other, step, index in links[current]:
                if step == 0:
                    later.append((current, other, index))
                    continue
                expected = generation[current] + step
                if other not in generation:
                    generation[other] = expected
                    queue.append(other)
                elif generation[other] != expected:
                    return [
                        Violation(
                            _pointer("couples", index, "children"),
                            f"the generations of couple {index} disagree with the rest of the "
                            f"tree: partners share a row and a child is one row below its "
                            f"parents, and no rows satisfy both here.",
                        )
                    ]
    low = min(generation.values())
    rows = max(generation.values()) - low + 1
    if rows > FAMILYTREE_GENERATION_MAX:
        deepest = next(name for name in ids if generation[name] - low == FAMILYTREE_GENERATION_MAX)
        found.append(
            Violation(
                _pointer("people", ids[deepest]),
                f"the tree spans {rows} generations, past what one family tree can be read at "
                f"— {FAMILYTREE_GENERATION_MAX} at most. Split it: the older generations as one "
                f"tree, and each branch below as a tree of its own.",
            )
        )

    # A row draws one person's partners beside them; a partner of theirs with
    # partners of their own would need a second row.
    for name, mine in partners.items():
        if len(mine) < 2:
            continue
        for index, other in mine:
            if len(partners[other]) > 1:
                found.append(
                    Violation(
                        _pointer("couples", index, "between"),
                        f"{name!r} and {other!r} both have other partners, and a row draws one "
                        f"person's partners beside them. Leave one of the earlier couples out, "
                        f"or draw it as a tree of its own.",
                    )
                )
                return found
        if len(mine) > 2:
            for index, other in mine[1:]:
                if other in parents_of:
                    found.append(
                        Violation(
                            _pointer("couples", index, "between"),
                            f"{other!r} is {name!r}'s partner number "
                            f"{mine.index((index, other)) + 1}, "
                            f"and has parents in the tree. Past two partners, the line to each "
                            f"later one runs over the row, so only the first partner's family "
                            f"can be drawn above. Draw {other!r}'s family as a tree of its own.",
                        )
                    )

    # An ancestor chart — a person, their parents, their four grandparents — is a
    # binary tree, not a family: every couple has one child, and couples marry
    # into each other from both sides.
    if (
        rows >= 3
        and len(valid) >= 3
        and all(len(kids) == 1 for _, _, kids in valid)
        and any(all(parent in parents_of for parent in pair) for _, pair, _ in valid)
    ):
        found.append(
            Violation(
                "/couples",
                "every couple here has one child, and partners come from both sides: this is "
                "an ancestor chart (a genealogist's pedigree chart), one person and their "
                "forebears. That is a binary tree, so draw it as a `tree`. A family tree draws "
                "couples and all their children.",
            )
        )
    return found


def _familytree_document(document: Mapping[str, Any]) -> Document:
    """A family tree: its people and its couples, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        people=tuple(
            FamilyPerson(
                id=str(person["id"]),
                sex=str(person["sex"]),
                gender=str(person.get("gender", "")),
                text=str(person.get("text", "")),
                status=str(person.get("status", "unaffected")),
                deceased=bool(person.get("deceased", False)),
                proband=bool(person.get("proband", False)),
                consultand=bool(person.get("consultand", False)),
                adopted=bool(person.get("adopted", False)),
                pregnancy=str(person.get("pregnancy", "")),
                role=str(person.get("role", "step")),
            )
            for person in document["people"]
        ),
        couples=tuple(
            FamilyCouple(
                between=(str(couple["between"][0]), str(couple["between"][1])),
                children=tuple(str(child) for child in couple.get("children", ())),
                twins=tuple(
                    FamilyTwins(
                        of=tuple(str(each) for each in twins["of"]),
                        zygosity=str(twins["zygosity"]),
                    )
                    for twins in couple.get("twins", ())
                ),
                separated=bool(couple.get("separated", False)),
                consanguineous=bool(couple.get("consanguineous", False)),
            )
            for couple in document["couples"]
        ),
    )
