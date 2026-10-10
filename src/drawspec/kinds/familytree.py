"""The `familytree` kind: people, the couples they form, and their children.

A family tree — a **pedigree** in genetics and medicine, where it is the only
name. A `tree` cannot draw one: a child there has one parent, and a partner who
married in has none. Here a child hangs from a *couple*, and partners share a row.

**Generations are rows**, numbered I, II, III down the left; a child is one row
below its parents and a partner takes their partner's row (the validator has
already checked that every row agrees). People are numbered 1… left to right in
each row, under the symbol, so "II-3" in the text of a letter names a number
drawspec assigned and keeps right when someone is added.

**Symbols follow the standard nomenclature**: a square, a circle or a diamond by
`sex` (or by `gender`, with assigned sex noted under it), filled when affected,
the theme's carrier mark when a carrier, a stroke through it when deceased, an
arrow at the lower left for the proband (with a `P`) or a consultand, brackets
when adopted, a `P` inside for a pregnancy and a small triangle for a loss.

**Lines.** Partners are joined by a line between the symbols (two lines when
consanguineous, two strokes across it when separated). A descent line drops from
the middle of it to the sibship line, and a short drop runs from that to each
child, in birth order; twins leave the sibship line from one point (a bar between
them when identical, a `?` when unknown). A person with two partners has one on
each side; with more, the first is on the left and the rest on the right in
marriage order, the line to each one past the second running over the row on a
level of its own, the farthest highest, so no two lines cross.

**Placement.** Each row is ordered as households — one person and their partners
— by the barycentre of their parents above and their children below, sibships in
birth order, a sibling who partners into another family moved to the edge nearest
it. Then positions are relaxed, row by row and back again, towards children
centred under their parents, with every gap kept. Sibship lines that would
overlap get lanes of their own between the rows.

When a row is wider than the canvas, names wrap narrower until it fits; when no
width works, `FitError` names the widest row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise, permutations
from typing import Final

from drawspec.errors import FitError
from drawspec.routing import end_marker
from drawspec.scene import (
    Ellipse,
    Path,
    Polygon,
    Primitive,
    Scene,
    TextRun,
    centred_lines,
    extents,
    moved,
)
from drawspec.schema import Document, FamilyCouple, FamilyPerson
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The widest a name may be wrapped to, as a share of the canvas; the narrowest
#: before the tree is refused; and each narrower attempt's share of the last.
NAME_SHARE: Final = 0.16
NAME_MIN_SHARE: Final = 0.08
NAME_STEP: Final = 0.9

#: Lengths in units, a unit being the body size over eleven.
SYMBOL: Final = 22.0
"""Across and down: a square's side, a circle's and a diamond's width."""
LOSS: Final = 0.7
"""A pregnancy loss's triangle, as a share of the symbol."""
PARTNER_GAP: Final = 26.0
"""Across: between the slots of two partners — the partner line's least length."""
HOUSE_GAP: Final = 14.0
"""Across: between two households of one sibship."""
FAMILY_GAP: Final = 30.0
"""Across: between two households with no parents in common."""
LABEL_GAP: Final = 5.0
"""Down: from the symbol to its number."""
LANE_TOP: Final = 12.0
"""Down: from the lowest name in a row to the first sibship line under it."""
LANE: Final = 10.0
"""Down: between two lanes of sibship lines."""
DROP: Final = 14.0
"""Down: from a sibship line to the children's symbols."""
TWIN_DROP: Final = 22.0
"""Down: the same, when twins leave the line from one point."""
STAPLE: Final = 9.0
"""Down: between the levels a partner line past the second runs over the row on."""
ARROW: Final = 24.0
"""Across: the room a proband's arrow and its `P` take left of the symbol."""
BRACKET: Final = 4.0
"""Across: from an adopted person's symbol to the brackets round it."""
NUMERAL_GAP: Final = 14.0
"""Across: from the generation numerals to the first symbol's slot."""
SLASH: Final = 4.0
"""Across and down: how far a deceased person's stroke runs past the symbol."""

COMB: Final = 0.28
"""Across, as a share of the symbol: how far right of centre the lines over the row
leave a person with several partners, and how far left of it their own drop lands."""

#: The roles everything is drawn in. Lines are the theme's quietest solid line,
#: so the symbols, at the ordinary box weight, stand out from them.
LINE_ROLE: Final = "link"
ADOPTED_ROLE: Final = "aside"
MARK_ROLE: Final = "flow"
TEXT_ROLE: Final = "step"

#: The words of the key, by status, in the order the key lists them.
KEY_WORDS: Final = (("affected", "Affected"), ("carrier", "Carrier"), ("unaffected", "Unaffected"))

#: Roman numerals for the generations: four at most.
NUMERALS: Final = ("I", "II", "III", "IV", "V", "VI")

#: A rectangle: left, top, right, bottom.
type Rect4 = tuple[float, float, float, float]


@dataclass(frozen=True)
class PersonDrawn:
    """Where one person landed, in final coordinates."""

    id: str
    generation: int
    """0 for the top row, I."""

    number: int
    """Their number within the generation, from 1 at the left."""

    shape: str
    """`square`, `circle`, `diamond` or `triangle`."""

    symbol: Rect4
    label: Rect4
    """The number, note and name under the symbol, together."""

    slot: Rect4
    """Everything that belongs to this person, marks and words."""


@dataclass(frozen=True)
class LineDrawn:
    """One line of the tree: a partner line, a descent, a sibship line or a drop."""

    kind: str
    """`partner`, `descent`, `sibship`, `drop` or `twin`."""

    couple: int
    points: tuple[tuple[float, float], ...]
    role: str


@dataclass(frozen=True)
class FamilyDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    people: tuple[PersonDrawn, ...] = field(default_factory=tuple)
    lines: tuple[LineDrawn, ...] = field(default_factory=tuple)
    rows: tuple[float, ...] = ()
    """Each generation's symbol centre line, top to bottom."""


@dataclass
class _Person:
    data: FamilyPerson
    index: int
    generation: int
    block: TextBlock | None
    note: str
    left: float
    """How far this person's slot reaches left of the symbol's centre."""

    right: float
    label_height: float
    parents: int | None = None
    """The couple whose child this person is."""

    x: float = 0.0
    number: int = 0
    house: _House | None = None
    arrive: float = 0.0
    """Where the drop from the sibship line lands, from the symbol's centre: off
    centre only for a person whose partner lines run over the row from it."""


@dataclass
class _Join:
    """One couple as drawn: which two people, and how their line runs."""

    index: int
    couple: FamilyCouple
    left: _Person
    right: _Person
    level: int = 0
    """0 for a line between two neighbours; 1… for one over the row."""

    def descent(self) -> float:
        """Where the descent line leaves the couple: the gap beside the right partner."""
        if self.level == 0:
            return (self.left.x + self.left.right + self.right.x - self.right.left) / 2
        house = self.right.house
        assert house is not None
        before = house.members[house.members.index(self.right) - 1]
        return (before.x + before.right + self.right.x - self.right.left) / 2


@dataclass
class _House:
    """One person and their partners, as one unit of a row."""

    members: list[_Person]
    row: int
    centre: _Person | None = None
    joins: list[_Join] = field(default_factory=list)
    x: float = 0.0
    """The left edge of the first member's slot."""

    gap: float = PARTNER_GAP
    """The least gap between two partners' slots, at the scale being drawn."""

    def place(self) -> None:
        """Pack the members left to right from `x`, each partner gap at its least."""
        cursor = self.x
        for position, member in enumerate(self.members):
            if position:
                cursor += self.gap
            member.x = cursor + member.left
            cursor = member.x + member.right

    @property
    def width(self) -> float:
        first, last = self.members[0], self.members[-1]
        return last.x + last.right - (first.x - first.left)


def familytree_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a family tree."""
    return familytree_drawing(document, theme, measurer).scene


def familytree_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> FamilyDrawing:
    """Lay the tree out, wrapping names narrower until every row fits the canvas.

    Raises:
        FitError: no width for the names fits the canvas.
    """
    width = theme.canvas.width
    cap = width * NAME_SHARE
    floor = width * NAME_MIN_SHARE
    widest = (0, 0.0)
    while True:
        try:
            drawing, needed, row = _attempt(document, theme, measurer, cap)
        except FitError:
            break
        if needed <= width + 1e-6:
            assert drawing is not None
            return drawing
        widest = (row, needed)
        if cap <= floor:
            break
        cap = max(floor, cap * NAME_STEP)
    row, needed = widest
    raise FitError(
        f"the family tree does not fit a width of {width:.0f}, even with every name wrapped "
        f"to {floor:.0f}: generation {NUMERALS[row]} needs {needed:.0f}. Shorten the names, "
        f"split the tree by branch — one tree per side of the family — or give the diagram "
        f"more width."
    )


def _generations(document: Document) -> dict[str, int]:
    """Each person's row, 0 at the top: partners level, a child one below."""
    links: dict[str, list[tuple[str, int]]] = {person.id: [] for person in document.people}
    for couple in document.couples:
        a, b = couple.between
        links[a].append((b, 0))
        links[b].append((a, 0))
        for child in couple.children:
            for parent in couple.between:
                links[parent].append((child, 1))
                links[child].append((parent, -1))
    generation: dict[str, int] = {}
    for person in document.people:
        if person.id in generation:
            continue
        generation[person.id] = 0
        queue = [person.id]
        while queue:
            current = queue.pop(0)
            for other, step in links[current]:
                if other not in generation:
                    generation[other] = generation[current] + step
                    queue.append(other)
    low = min(generation.values())
    return {name: value - low for name, value in generation.items()}


def _note(person: FamilyPerson) -> str:
    """The sex assigned at birth, written under a symbol that shows gender, if it differs."""
    if not person.gender or person.sex == "unknown":
        return ""
    matches = {"man": "male", "woman": "female"}.get(person.gender)
    if matches == person.sex:
        return ""
    return "AMAB" if person.sex == "male" else "AFAB"


def _shape(person: FamilyPerson) -> str:
    if person.pregnancy == "loss":
        return "triangle"
    by = person.gender or person.sex
    return {
        "male": "square",
        "man": "square",
        "female": "circle",
        "woman": "circle",
    }.get(by, "diamond")


#: The orders a row's households may start from before the sweeps: as written,
#: households with no parents here first, last, and the written order reversed.
#: Barycentre sweeps settle on a local best, and which one depends on the start.
STARTS: Final = 4


def _attempt(
    document: Document, theme: Theme, measurer: TextMeasurer, cap: float
) -> tuple[FamilyDrawing | None, float, int]:
    """One layout at one name width: the drawing, the width it needs, its widest row.

    The sweeps start from each of `STARTS` orders, and the drawing with the fewest
    crossing lines wins; the first with none ends the search.
    """
    best: tuple[int, FamilyDrawing] | None = None
    narrowest: tuple[float, int] | None = None
    for start in range(STARTS):
        drawing, needed, widest = _attempt_from(document, theme, measurer, cap, start)
        if drawing is None:
            if narrowest is None or needed < narrowest[0]:
                narrowest = (needed, widest)
            if start == 0:
                # The other starts reorder, but do not narrow: wrap narrower first.
                break
            continue
        crossings = _crossings(drawing)
        if best is None or crossings < best[0]:
            best = (crossings, drawing)
            fitted = (needed, widest)
        if crossings == 0:
            break
    if best is None:
        assert narrowest is not None
        return None, narrowest[0], narrowest[1]
    return best[1], fitted[0], fitted[1]


def _crossings(drawing: FamilyDrawing) -> int:
    """How many pairs of lines of different couples cross inside both."""
    pieces = [(line.couple, a, b) for line in drawing.lines for a, b in pairwise(line.points)]

    def side(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> int:
        value = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(value) < 1e-6 else (1 if value > 0 else -1)

    count = 0
    for index, (couple, a, b) in enumerate(pieces):
        for other, c, d in pieces[index + 1 :]:
            if couple == other:
                continue
            if side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0:
                count += 1
    return count


def _attempt_from(
    document: Document, theme: Theme, measurer: TextMeasurer, cap: float, start: int
) -> tuple[FamilyDrawing | None, float, int]:
    """One layout from one starting order."""
    unit = theme.scale["body"] / 11
    size = SYMBOL * unit
    generation = _generations(document)
    label_line = measurer.measure("0", theme.font.default, theme.scale["label"])

    people: dict[str, _Person] = {}
    for index, data in enumerate(document.people):
        block = None
        if data.text:
            words = data.text
            if data.role == "emphasis":
                words = "\n".join(
                    f"**{line.replace('**', '')}**" if line.strip() else line
                    for line in words.split("\n")
                )
            try:
                block = wrap(words, cap, measurer, theme=theme, level="body")
            except FitError as error:
                raise FitError(
                    f"the name of {data.id!r} has a word wider than the {cap:.0f} units it may "
                    f"have. Shorten it, or give the diagram more width."
                ) from error
        note = _note(data)
        widths = [size / 2 + 3 * unit]
        if block is not None:
            widths.append(block.width / 2 + unit)
        if note:
            widths.append(
                measurer.measure(note, theme.font.default, theme.scale["label"]).width / 2
            )
        if data.adopted:
            widths.append(size / 2 + BRACKET * unit + 3 * unit)
        if data.deceased:
            widths.append(size / 2 + SLASH * unit + 2 * unit)
        right = max(widths)
        left = right
        if data.proband or data.consultand:
            left = max(left, size / 2 + ARROW * unit)
        height = label_line.height * (2 if note else 1)
        if block is not None:
            height += block.height
        people[data.id] = _Person(
            data=data,
            index=index,
            generation=generation[data.id],
            block=block,
            note=note,
            left=left,
            right=right,
            label_height=height,
        )
    for index, couple in enumerate(document.couples):
        for child in couple.children:
            people[child].parents = index

    houses, joins = _households(document, people, PARTNER_GAP * unit)
    for house in houses:
        if house.centre is not None and any(join.level for join in house.joins):
            house.centre.arrive = -size * COMB
    rows = max(generation.values()) + 1
    by_row: list[list[_House]] = [[] for _ in range(rows)]
    for house in houses:
        by_row[house.row].append(house)

    def written(house: _House) -> int:
        return min(member.index for member in house.members)

    def founder(house: _House) -> bool:
        return all(member.parents is None for member in house.members)

    for row in by_row:
        if start == 1:
            row.sort(key=lambda house: (not founder(house), written(house)))
        elif start == 2:
            row.sort(key=lambda house: (founder(house), written(house)))
        elif start == 3:
            row.sort(key=written, reverse=True)
        else:
            row.sort(key=written)

    _order(document, by_row, joins, people, unit)
    numeral_width = max(
        measurer.measure(NUMERALS[row], theme.font.default, theme.scale["label"]).width
        for row in range(rows)
    )

    _position(document, by_row, joins, people, unit)
    left = min(house.x for row in by_row for house in row if row)
    right = max(house.x + house.width for row in by_row for house in row if row)
    spans = [
        (max(h.x + h.width for h in row) - min(h.x for h in row)) if row else 0.0 for row in by_row
    ]
    needed = right - left + numeral_width + NUMERAL_GAP * unit
    widest = max(range(rows), key=lambda row: spans[row])
    if needed > theme.canvas.width + 1e-6:
        return None, needed, widest
    drawing = _drawing(document, by_row, joins, people, theme, measurer, numeral_width)
    return drawing, needed, widest


def _households(
    document: Document, people: dict[str, _Person], gap: float
) -> tuple[list[_House], list[_Join]]:
    """Each person with their partners, in the order a row draws them."""
    partners: dict[str, list[tuple[int, str]]] = {name: [] for name in people}
    for index, couple in enumerate(document.couples):
        a, b = couple.between
        partners[a].append((index, b))
        partners[b].append((index, a))
    seen: set[str] = set()
    houses: list[_House] = []
    joins: list[_Join] = []
    for name in people:
        if name in seen:
            continue
        group = [name]
        seen.add(name)
        cursor = 0
        while cursor < len(group):
            for _, other in partners[group[cursor]]:
                if other not in seen:
                    seen.add(other)
                    group.append(other)
            cursor += 1
        centre = next((each for each in group if len(partners[each]) > 1), None)
        person = people[name]
        if centre is None:
            members = [people[each] for each in group]
            house = _House(members=members, row=person.generation, gap=gap)
            if len(members) == 2:
                index = partners[group[0]][0][0]
                house.joins.append(_Join(index, document.couples[index], members[0], members[1]))
        else:
            ordered = [people[other] for _, other in partners[centre]]
            middle = people[centre]
            members = [ordered[0], middle, *ordered[1:]]
            house = _House(members=members, row=middle.generation, centre=middle, gap=gap)
            for position, (index, _) in enumerate(partners[centre]):
                partner = ordered[position]
                if position == 0:
                    join = _Join(index, document.couples[index], partner, middle)
                else:
                    join = _Join(
                        index, document.couples[index], middle, partner, level=max(position - 1, 0)
                    )
                house.joins.append(join)
        for member in house.members:
            member.house = house
        houses.append(house)
        joins.extend(house.joins)
    joins.sort(key=lambda join: join.index)
    return houses, joins


def _layout_row(row: list[_House], unit: float) -> None:
    """Pack a row left to right at its least gaps, keeping its order."""
    cursor = 0.0
    previous: _House | None = None
    for house in row:
        if previous is not None:
            cursor += _gap(previous, house, unit)
        house.x = cursor
        house.place()
        cursor += house.width
        previous = house


def _gap(left: _House, right: _House, unit: float) -> float:
    """The least gap between two neighbouring households: wider between families."""
    mine = {member.parents for member in left.members if member.parents is not None}
    theirs = {member.parents for member in right.members if member.parents is not None}
    return (HOUSE_GAP if mine & theirs else FAMILY_GAP) * unit


def _flip(
    house: _House, joins: list[_Join], people: dict[str, _Person], document: Document
) -> None:
    """Turn a household so each partner faces their own family.

    A couple with one partner from the family above follows birth order: a
    first-born's partner goes on the outside, to the left, a last-born's to the
    right, so the sibship stays together. Otherwise — both partners from families
    here, or a person with two partners — the household takes whichever way round
    sits each person nearer their parents and each couple nearer its children. A
    couple with no parents here keeps the order written, and three or more
    partners are never turned: the lines over the row run right.
    """
    if len(house.members) < 2 or len(house.members) > 3:
        return
    parented = [member for member in house.members if member.parents is not None]
    if house.centre is None and len(parented) == 1:
        child = parented[0]
        assert child.parents is not None
        siblings = document.couples[child.parents].children
        early = siblings.index(child.data.id) < len(siblings) / 2
        if (house.members[0] is child) == early:
            _mirror(house)
        return
    if house.centre is None and not parented:
        return
    before = _cost(house, joins, people)
    _mirror(house)
    # Only for a real gain: a couple with no reason to turn keeps the order written.
    if _cost(house, joins, people) >= before - 1.0:
        _mirror(house)


def _mirror(house: _House) -> None:
    house.members.reverse()
    for join in house.joins:
        join.left, join.right = join.right, join.left
    house.place()


def _cost(house: _House, joins: list[_Join], people: dict[str, _Person]) -> float:
    """How far a household's people sit from their parents, and its couples from their children."""
    total = 0.0
    for member in house.members:
        if member.parents is not None:
            total += abs(member.x - _descent_of(member.parents, joins))
    for join in house.joins:
        children = [people[child] for child in join.couple.children]
        if children:
            total += abs(join.descent() - sum(child.x for child in children) / len(children))
    return total


def _descent_of(index: int, joins: list[_Join]) -> float:
    for join in joins:
        if join.index == index:
            return join.descent()
    raise KeyError(index)


def _centre(house: _House) -> float:
    return house.x + house.width / 2


def _order(
    document: Document,
    by_row: list[list[_House]],
    joins: list[_Join],
    people: dict[str, _Person],
    unit: float,
) -> None:
    """Order each row by barycentres, down and up, sibships kept in birth order."""
    for row in by_row:
        _layout_row(row, unit)

    def parents_key(house: _House) -> float | None:
        found = [
            _descent_of(member.parents, joins)
            for member in house.members
            if member.parents is not None
        ]
        return sum(found) / len(found) if found else None

    def children_key(house: _House) -> float | None:
        found = [people[child].x for join in house.joins for child in join.couple.children]
        return sum(found) / len(found) if found else None

    def resort(row: list[_House], keys: list[float | None]) -> None:
        current = {id(house): _centre(house) for house in row}
        ranked = sorted(
            zip(row, keys, strict=True),
            key=lambda pair: pair[1] if pair[1] is not None else current[id(pair[0])],
        )
        row[:] = [house for house, _ in ranked]
        _birth_order(document, row, people)
        for house in row:
            _flip(house, joins, people, document)
        _layout_row(row, unit)

    for _ in range(4):
        for row in by_row[1:]:
            resort(row, [parents_key(house) for house in row])
        for row in reversed(by_row[:-1]):
            resort(
                row,
                [children_key(house) or parents_key(house) for house in row],
            )
    for row in by_row[1:]:
        resort(row, [parents_key(house) for house in row])


def _birth_order(document: Document, row: list[_House], people: dict[str, _Person]) -> None:
    """Within each sibship, its single-family households take its slots in birth order."""
    for index in range(len(document.couples)):
        slots: list[int] = []
        houses: list[_House] = []
        for position, house in enumerate(row):
            mine = [member for member in house.members if member.parents == index]
            others = [
                member
                for member in house.members
                if member.parents is not None and member.parents != index
            ]
            if mine and not others:
                slots.append(position)
                houses.append(house)
        if len(houses) < 2:
            continue

        def born(house: _House, index: int = index) -> int:
            return min(
                document.couples[index].children.index(member.data.id)
                for member in house.members
                if member.parents == index
            )

        for slot, house in zip(slots, sorted(houses, key=born), strict=True):
            row[slot] = house


def _isotonic(targets: list[float], weights: list[float]) -> list[float]:
    """The non-decreasing sequence nearest `targets`, by weighted least squares."""
    blocks: list[list[float]] = []  # [value, weight, count]
    for target, weight in zip(targets, weights, strict=True):
        blocks.append([target, weight, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            value, weight_b, count_b = blocks.pop()
            prior = blocks[-1]
            total = prior[1] + weight_b
            prior[0] = (prior[0] * prior[1] + value * weight_b) / total
            prior[1] = total
            prior[2] += count_b
    found: list[float] = []
    for value, _, count in blocks:
        found.extend([value] * int(count))
    return found


def _settle(row: list[_House], desired: dict[str, tuple[float, float]], unit: float) -> None:
    """Move a row's people as near their desired centres as the gaps allow.

    Person by person rather than household by household, so a partner line may
    lengthen to let the children of two couples sit under their own parents. The
    order never changes; each gap only ever opens.
    """
    members = [member for house in row for member in house.members]
    if not members:
        return
    offsets = [0.0]
    for (a, house_a), (b, house_b) in pairwise(
        (member, house) for house in row for member in house.members
    ):
        gap = house_a.gap if house_a is house_b else _gap(house_a, house_b, unit)
        offsets.append(offsets[-1] + a.right + gap + b.left)
    targets = [desired.get(member.data.id, (member.x, KEEP))[0] for member in members]
    weights = [desired.get(member.data.id, (member.x, KEEP))[1] for member in members]
    fitted = _isotonic(
        [want - offset for want, offset in zip(targets, offsets, strict=True)], weights
    )
    for member, value, offset in zip(members, fitted, offsets, strict=True):
        member.x = value + offset
    for house in row:
        house.x = house.members[0].x - house.members[0].left


#: How strongly a person with no reason to move stays where they are, against
#: a person who has one (1).
KEEP: Final = 0.05


def _position(
    document: Document,
    by_row: list[list[_House]],
    joins: list[_Join],
    people: dict[str, _Person],
    unit: float,
) -> None:
    """Relax every row towards children centred under their parents, gaps kept."""
    for row in by_row:
        _layout_row(row, unit)

    def down(row: list[_House]) -> None:
        # Each sibship's spacing as it stands, centred on its descent; a partner
        # with no parents here moves with the one who has them.
        desired: dict[str, tuple[float, float]] = {}
        for index in {m.parents for h in row for m in h.members if m.parents is not None}:
            children = [people[child] for child in document.couples[index].children]
            middle = (min(c.x for c in children) + max(c.x for c in children)) / 2
            descent = _descent_of(index, joins)
            for child in children:
                desired[child.data.id] = (child.x - middle + descent, 1.0)
        for house in row:
            shifts = [desired[m.data.id][0] - m.x for m in house.members if m.data.id in desired]
            if not shifts:
                continue
            shift = sum(shifts) / len(shifts)
            for member in house.members:
                if member.data.id not in desired:
                    desired[member.data.id] = (member.x + shift, 0.5)
        _settle(row, desired, unit)

    def up(row: list[_House]) -> None:
        # Each couple's descent over the middle of its children: a line between
        # neighbours moves both partners; a line over the row moves the far one,
        # whose gap the descent drops through, twice as far.
        wants: dict[str, list[float]] = {}
        for house in row:
            for join in house.joins:
                children = [people[child] for child in join.couple.children]
                if not children:
                    continue
                middle = (min(c.x for c in children) + max(c.x for c in children)) / 2
                delta = middle - join.descent()
                if join.level == 0:
                    wants.setdefault(join.left.data.id, []).append(join.left.x + delta)
                    wants.setdefault(join.right.data.id, []).append(join.right.x + delta)
                else:
                    wants.setdefault(join.right.data.id, []).append(join.right.x + 2 * delta)
        desired = {name: (sum(values) / len(values), 1.0) for name, values in wants.items()}
        _settle(row, desired, unit)

    for _ in range(12):
        for row in by_row[1:]:
            down(row)
        for row in reversed(by_row[:-1]):
            up(row)
    for row in by_row[1:]:
        down(row)


@dataclass
class _Sibship:
    """One couple's children as drawn: the descent, the line, the drops."""

    join: _Join
    children: list[_Person]
    low: float
    high: float
    descent: float
    points: list[float]
    """The x of every drop from the line: one per child, one per set of twins."""

    lane: int = 0


def _sibships(document: Document, joins: list[_Join], people: dict[str, _Person]) -> list[_Sibship]:
    found = []
    for join in joins:
        children = [people[child] for child in join.couple.children]
        if not children:
            continue
        twinned = {member for twins in join.couple.twins for member in twins.of}
        points = [child.x + child.arrive for child in children if child.data.id not in twinned]
        for twins in join.couple.twins:
            points.append(sum(people[m].x for m in twins.of) / len(twins.of))
        descent = join.descent()
        xs = [*points, descent]
        found.append(_Sibship(join, children, min(xs), max(xs), descent, points))
    return found


def _lanes(sibships: list[_Sibship], margin: float) -> int:
    """Give overlapping sibship lines lanes so that no descent or drop crosses one."""
    ordered = sorted(sibships, key=lambda s: s.low)
    clusters: list[list[_Sibship]] = []
    for sibship in ordered:
        if clusters and sibship.low <= max(s.high for s in clusters[-1]) + margin:
            clusters[-1].append(sibship)
        else:
            clusters.append([sibship])
    most = 1
    for cluster in clusters:
        if len(cluster) == 1:
            cluster[0].lane = 0
            continue
        best: tuple[int, ...] | None = None
        best_cost = math.inf
        candidates = (
            permutations(range(len(cluster)))
            if len(cluster) <= 5
            else iter([tuple(range(len(cluster)))])
        )
        for lanes in candidates:
            cost = 0
            for a, la in zip(cluster, lanes, strict=True):
                for b, lb in zip(cluster, lanes, strict=True):
                    if a is b or la >= lb:
                        continue
                    # a is higher than b: b's descent passes a's lane; a's drops pass b's.
                    if a.low - margin <= b.descent <= a.high + margin:
                        cost += 1
                    cost += sum(1 for x in a.points if b.low - margin <= x <= b.high + margin)
            if cost < best_cost:
                best, best_cost = lanes, cost
        assert best is not None
        for sibship, lane in zip(cluster, best, strict=True):
            sibship.lane = lane
        most = max(most, len(cluster))
    return most


def _drawing(
    document: Document,
    by_row: list[list[_House]],
    joins: list[_Join],
    people: dict[str, _Person],
    theme: Theme,
    measurer: TextMeasurer,
    numeral_width: float,
) -> FamilyDrawing:
    unit = theme.scale["body"] / 11
    size = SYMBOL * unit
    label_line = measurer.measure("0", theme.font.default, theme.scale["label"])
    rows = len(by_row)

    # Across: the numerals' column, then the rows.
    left = min(house.x for row in by_row for house in row if row)
    shift = numeral_width + NUMERAL_GAP * unit - left
    for row in by_row:
        for house in row:
            house.x += shift
            for member in house.members:
                member.x += shift

    # Numbers: left to right in each generation.
    for row in by_row:
        members = sorted((m for h in row for m in h.members), key=lambda m: m.x)
        for number, member in enumerate(members, start=1):
            member.number = number

    # Down: each row's symbols, names, and the lanes and staples under it.
    sibships = _sibships(document, joins, people)
    by_gap: dict[int, list[_Sibship]] = {}
    for sibship in sibships:
        by_gap.setdefault(sibship.join.left.generation, []).append(sibship)
    lanes = {row: _lanes(found, PARTNER_GAP * unit / 4) for row, found in by_gap.items()}
    staples = [
        max((join.level for house in row for join in house.joins), default=0) for row in by_row
    ]
    tops: list[float] = []
    cursor = staples[0] * STAPLE * unit
    for g in range(rows):
        tops.append(cursor)
        labels = max((m.label_height for h in by_row[g] for m in h.members), default=0.0)
        bottom = cursor + size + LABEL_GAP * unit + labels
        if g + 1 < rows:
            has_twins = any(s.join.couple.twins for s in by_gap.get(g, []))
            cursor = (
                bottom
                + LANE_TOP * unit
                + (lanes.get(g, 1) - 1) * LANE * unit
                + (TWIN_DROP if has_twins else DROP) * unit
                + staples[g + 1] * STAPLE * unit
            )
    centres = [top + size / 2 for top in tops]

    lines: list[Primitive] = []
    marks: list[Primitive] = []
    texts: list[Primitive] = []
    drawn_lines: list[LineDrawn] = []

    def line(kind: str, couple: int, points: tuple[tuple[float, float], ...], role: str) -> None:
        lines.append(Path(role, points=points))
        drawn_lines.append(LineDrawn(kind, couple, points, role))

    def top_of(person: _Person, x: float) -> float:
        """Where a vertical line at `x` meets the top of `person`'s symbol."""
        cy = centres[person.generation]
        half = size / 2
        shape = _shape(person.data)
        dx = abs(x - person.x)
        if shape == "circle":
            return cy - math.sqrt(max(half * half - dx * dx, 0.0))
        if shape == "diamond":
            return cy - max(half - dx, 0.0)
        if shape == "triangle":
            return cy - half * LOSS
        return cy - half

    def edge(person: _Person, side: int) -> float:
        """Where the partner line meets `person`'s symbol, on `side` (-1 left, 1 right)."""
        reach = size / 2 * (LOSS if _shape(person.data) == "triangle" else 1.0)
        return person.x + side * reach

    # Partner lines.
    for join in joins:
        y = centres[join.left.generation]
        couple = join.couple
        if join.level == 0:
            start, end = edge(join.left, 1), edge(join.right, -1)
            if couple.consanguineous:
                gap = 1.6 * unit
                line("partner", join.index, ((start, y - gap), (end, y - gap)), LINE_ROLE)
                line("partner", join.index, ((start, y + gap), (end, y + gap)), LINE_ROLE)
            else:
                line("partner", join.index, ((start, y), (end, y)), LINE_ROLE)
            across = (start, end)
            height = y
        else:
            centre = join.left
            leg = centre.x + size * COMB
            height = tops[centre.generation] - join.level * STAPLE * unit
            far = join.right
            path = (
                (leg, top_of(centre, leg)),
                (leg, height),
                (far.x, height),
                (far.x, top_of(far, far.x)),
            )
            line("partner", join.index, path, LINE_ROLE)
            if couple.consanguineous:
                line(
                    "partner",
                    join.index,
                    ((leg, height - 1.6 * unit * 2), (far.x, height - 1.6 * unit * 2)),
                    LINE_ROLE,
                )
            across = (leg, far.x)
        if couple.separated:
            has_children = bool(couple.children)
            descent = join.descent()
            if join.level:
                # Over the row: near the far partner, clear of the descent in the gap.
                owner = far.house
                assert owner is not None
                before = owner.members[owner.members.index(far) - 1]
                middle = far.x - (far.x - before.x) * 0.25
            elif has_children:
                middle = (across[0] + descent) / 2
            else:
                middle = (across[0] + across[1]) / 2
            for offset in (-2.0 * unit, 2.0 * unit):
                x = middle + offset
                marks.append(
                    Path(
                        LINE_ROLE,
                        points=(
                            (x - 2.5 * unit, height + 4 * unit),
                            (x + 2.5 * unit, height - 4 * unit),
                        ),
                    )
                )

    # Descents, sibship lines and drops.
    for sibship in sibships:
        join = sibship.join
        g = join.left.generation
        labels = max((m.label_height for h in by_row[g] for m in h.members), default=0.0)
        lane_y = (
            tops[g]
            + size
            + LABEL_GAP * unit
            + labels
            + LANE_TOP * unit
            + (sibship.lane * LANE * unit)
        )
        start_y = (
            centres[g] + (1.6 * unit if join.couple.consanguineous else 0.0)
            if join.level == 0
            else tops[g] - join.level * STAPLE * unit
        )
        line(
            "descent",
            join.index,
            ((sibship.descent, start_y), (sibship.descent, lane_y)),
            LINE_ROLE,
        )
        if sibship.high - sibship.low > 0.5:
            line("sibship", join.index, ((sibship.low, lane_y), (sibship.high, lane_y)), LINE_ROLE)
        twinned: dict[str, int] = {}
        for position, twins in enumerate(join.couple.twins):
            for name in twins.of:
                twinned[name] = position
        for child in sibship.children:
            if child.data.id in twinned:
                continue
            role = ADOPTED_ROLE if child.data.adopted else LINE_ROLE
            x = child.x + child.arrive
            line("drop", join.index, ((x, lane_y), (x, top_of(child, x))), role)
        for twins in join.couple.twins:
            members = [people[m] for m in twins.of]
            apex = sum(m.x for m in members) / len(members)
            ends = [(m.x, top_of(m, m.x)) for m in members]
            for member, reached in zip(members, ends, strict=True):
                role = ADOPTED_ROLE if member.data.adopted else LINE_ROLE
                line("twin", join.index, ((apex, lane_y), reached), role)
            if twins.zygosity == "monozygotic":
                t = 0.5
                first, last = ends[0], ends[-1]
                bar = (
                    (apex + (first[0] - apex) * t, lane_y + (first[1] - lane_y) * t),
                    (apex + (last[0] - apex) * t, lane_y + (last[1] - lane_y) * t),
                )
                line("twin", join.index, bar, LINE_ROLE)
            elif twins.zygosity == "unknown":
                depth = ends[0][1] - lane_y
                texts.append(
                    TextRun(
                        TEXT_ROLE,
                        x=apex,
                        y=lane_y + depth * 0.62 + (label_line.ascent - label_line.descent) / 2,
                        text="?",
                        level="label",
                        font=theme.font.default,
                        anchor="middle",
                    )
                )

    # Symbols and their words.
    drawn_people: list[_Placed] = []
    carrier = theme.familytree.carrier
    for row in by_row:
        for house in row:
            for member in house.members:
                shapes, words, entry = _person(
                    member, centres[member.generation], size, unit, carrier, theme, measurer
                )
                marks.extend(shapes)
                texts.extend(words)
                drawn_people.append(entry)

    # Generation numerals, at the left of each row's symbols.
    for g in range(rows):
        texts.append(
            TextRun(
                TEXT_ROLE,
                x=0.0,
                y=centres[g] + (label_line.ascent - label_line.descent) / 2,
                text=NUMERALS[g],
                level="label",
                font=theme.font.default,
                anchor="start",
                weight="bold",
            )
        )

    right = max(house.x + house.width for row in by_row for house in row if row)
    labels = max((m.label_height for h in by_row[-1] for m in h.members), default=0.0)
    bottom = tops[-1] + size + LABEL_GAP * unit + labels

    # The key: the statuses used, under the drawing.
    used = {person.status for person in document.people}
    if used & {"affected", "carrier"}:
        key_top = bottom + LANE_TOP * unit
        x = 0.0
        sample = label_line.height * 0.9
        middle = key_top + label_line.height / 2
        for status, term in KEY_WORDS:
            if status not in used and status != "unaffected":
                continue
            marks.extend(
                _symbol("square", x + sample / 2, middle, sample, "step", status, carrier, unit)
            )
            texts.append(
                TextRun(
                    TEXT_ROLE,
                    x=x + sample + 4 * unit,
                    y=middle + (label_line.ascent - label_line.descent) / 2,
                    text=term,
                    level="label",
                    font=theme.font.default,
                    anchor="start",
                )
            )
            width = measurer.measure(term, theme.font.default, theme.scale["label"]).width
            x += sample + 4 * unit + width + 16 * unit
        right = max(right, x - 16 * unit)
        bottom = key_top + label_line.height

    # A deceased stroke and a line over the row both reach above the first row.
    _, top, ink_right, _ = extents((*lines, *marks))
    top = min(0.0, top)
    right = max(right, ink_right)
    dy = -top
    scene = Scene(
        width=right,
        height=bottom + dy,
        primitives=tuple(moved(p, 0.0, dy) for p in (*lines, *marks, *texts)),
        title=document.title,
        description=document.description,
    )

    def shifted(rect: Rect4) -> Rect4:
        return (rect[0], rect[1] + dy, rect[2], rect[3] + dy)

    return FamilyDrawing(
        scene=scene,
        people=tuple(
            PersonDrawn(
                id=p.id,
                generation=p.generation,
                number=p.number,
                shape=p.shape,
                symbol=shifted(p.symbol),
                label=shifted(p.label),
                slot=shifted(p.slot),
            )
            for p in drawn_people
        ),
        lines=tuple(
            LineDrawn(
                kind=item.kind,
                couple=item.couple,
                points=tuple((x, y + dy) for x, y in item.points),
                role=item.role,
            )
            for item in drawn_lines
        ),
        rows=tuple(centre + dy for centre in centres),
    )


def _symbol(
    shape: str,
    cx: float,
    cy: float,
    size: float,
    role: str,
    status: str,
    carrier: str,
    unit: float,
) -> list[Primitive]:
    """One symbol at `(cx, cy)`, filled, marked or empty by `status`."""
    half = size / 2
    found: list[Primitive] = []
    solid = status == "affected"
    fill = "solid" if solid else ""
    colour = "currentColor" if solid else ""
    outline: tuple[tuple[float, float], ...]
    if shape == "triangle":
        half *= LOSS
        outline = ((cx, cy - half), (cx + half * 1.1, cy + half), (cx - half * 1.1, cy + half))
    elif shape == "diamond":
        outline = ((cx, cy - half), (cx + half, cy), (cx, cy + half), (cx - half, cy))
    elif shape == "square":
        outline = (
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        )
    else:
        outline = ()
    if status == "carrier" and carrier == "half":
        found.append(
            Polygon(
                role,
                points=_left_half(shape, cx, cy, half, outline),
                fill="solid",
                fill_colour="currentColor",
                region=True,
            )
        )
    if outline:
        found.append(Polygon(role, points=outline, fill=fill, fill_colour=colour))
    else:
        found.append(Ellipse(role, cx=cx, cy=cy, rx=half, ry=half, fill=fill, fill_colour=colour))
    if status == "carrier" and carrier == "dot":
        dot = max(size * 0.13, 1.6 * unit)
        found.append(
            Ellipse(
                role,
                cx=cx,
                cy=cy + (half * 0.2 if shape == "triangle" else 0.0),
                rx=dot,
                ry=dot,
                fill="solid",
                fill_colour="currentColor",
            )
        )
    return found


def _left_half(
    shape: str, cx: float, cy: float, half: float, outline: tuple[tuple[float, float], ...]
) -> tuple[tuple[float, float], ...]:
    if shape == "circle":
        steps = 16
        arc = tuple(
            (
                cx - half * math.sin(math.pi * step / steps),
                cy - half * math.cos(math.pi * step / steps),
            )
            for step in range(steps + 1)
        )
        return arc
    if shape == "square":
        return ((cx - half, cy - half), (cx, cy - half), (cx, cy + half), (cx - half, cy + half))
    if shape == "diamond":
        return ((cx, cy - half), (cx, cy + half), (cx - half, cy))
    return ((cx, cy - half), (cx, cy + half), (cx - half * 1.1, cy + half))


@dataclass(frozen=True)
class _Placed:
    id: str
    generation: int
    number: int
    shape: str
    symbol: Rect4
    label: Rect4
    slot: Rect4


def _person(
    member: _Person,
    cy: float,
    size: float,
    unit: float,
    carrier: str,
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[list[Primitive], list[Primitive], _Placed]:
    data = member.data
    cx = member.x
    half = size / 2
    shape = _shape(data)
    role = "emphasis" if data.role == "emphasis" else "step"
    shapes = _symbol(shape, cx, cy, size, role, data.status, carrier, unit)
    texts: list[Primitive] = []
    label_line = measurer.measure("0", theme.font.default, theme.scale["label"])
    centre_text = (label_line.ascent - label_line.descent) / 2

    if data.pregnancy == "ongoing":
        texts.append(
            TextRun(
                TEXT_ROLE,
                x=cx,
                y=cy + centre_text,
                text="P",
                level="label",
                font=theme.font.default,
                anchor="middle",
            )
        )
    if data.deceased:
        reach = half + SLASH * unit
        shapes.append(Path(MARK_ROLE, points=((cx - reach, cy + reach), (cx + reach, cy - reach))))
    if data.adopted:
        out = half + BRACKET * unit
        tick = 3 * unit
        top, bottom = cy - half - 2 * unit, cy + half + 2 * unit
        shapes.append(
            Path(
                LINE_ROLE,
                points=(
                    (cx - out + tick, top),
                    (cx - out, top),
                    (cx - out, bottom),
                    (cx - out + tick, bottom),
                ),
            )
        )
        shapes.append(
            Path(
                LINE_ROLE,
                points=(
                    (cx + out - tick, top),
                    (cx + out, top),
                    (cx + out, bottom),
                    (cx + out - tick, bottom),
                ),
            )
        )
    if data.proband or data.consultand:
        tip = (cx - half - 2 * unit, cy + half * 0.45)
        tail = (cx - half - 14 * unit, cy + half + 3 * unit)
        shapes.append(Path(MARK_ROLE, points=(tail, tip)))
        shapes.extend(end_marker("arrow", tail, tip, MARK_ROLE, theme))
        if data.proband:
            texts.append(
                TextRun(
                    TEXT_ROLE,
                    x=tail[0] - 1.5 * unit,
                    y=tail[1] + centre_text,
                    text="P",
                    level="label",
                    font=theme.font.default,
                    anchor="end",
                    weight="bold",
                )
            )

    # Under the symbol: the number, the assigned sex, the name.
    cursor = cy + half + LABEL_GAP * unit
    widest = 0.0
    number = str(member.number)
    texts.append(
        TextRun(
            TEXT_ROLE,
            x=cx,
            y=cursor + label_line.ascent,
            text=number,
            level="label",
            font=theme.font.default,
            anchor="middle",
        )
    )
    widest = measurer.measure(number, theme.font.default, theme.scale["label"]).width
    cursor += label_line.height
    if member.note:
        texts.append(
            TextRun(
                TEXT_ROLE,
                x=cx,
                y=cursor + label_line.ascent,
                text=member.note,
                level="label",
                font=theme.font.default,
                anchor="middle",
            )
        )
        widest = max(
            widest, measurer.measure(member.note, theme.font.default, theme.scale["label"]).width
        )
        cursor += label_line.height
    if member.block is not None:
        texts.extend(centred_lines(member.block, cx, cursor, role, "body"))
        widest = max(widest, member.block.width)
        cursor += member.block.height
    label_top = cy + half + LABEL_GAP * unit
    reach = half * (LOSS if shape == "triangle" else 1.0)
    return (
        shapes,
        texts,
        _Placed(
            id=data.id,
            generation=member.generation,
            number=member.number,
            shape=shape,
            symbol=(cx - reach, cy - reach, cx + reach, cy + reach),
            label=(cx - widest / 2, label_top, cx + widest / 2, cursor),
            slot=(cx - member.left, cy - half, cx + member.right, cursor),
        ),
    )


__all__ = [
    "FamilyDrawing",
    "LineDrawn",
    "PersonDrawn",
    "familytree_drawing",
    "familytree_scene",
]
