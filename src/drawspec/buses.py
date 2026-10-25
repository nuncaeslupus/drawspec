"""Which column each host of a `network` diagram stands in: topology, no geometry.

A network diagram in the nwdiag style is a stack of horizontal buses, one per
network in the order written, with every host a box hanging between them. A host
stands in a column and drops (or raises) one straight line to every bus it is
on; a bus runs from its leftmost host's column to its rightmost. Nothing else is
decided by an author, so the one real decision — the order of the columns — is
made here, from the attachments alone, and it is the same on every render.

**A host's line may cross no bus it is not on.** A host on `dmz` and `storage`
whose line passed through `internal` would read as attached to it, which is a
wrong network diagram, not an untidy one. So a host that skips a bus must stand
outside that bus's span: to its left or to its right. The order is searched for
one with no such crossing; when none exists the document is refused (by
`drawspec.schema`, at the host's pointer), rather than drawn with a hop over the
bus that a reader would have to be told about.

**Hosts share a column when their spans cannot touch.** A host's box sits just
under its topmost bus and its line reaches down to its lowest, so two hosts whose
vertical extents are apart — one on `dmz`, one under `storage` — stack in one
column, as nwdiag stacks them. Two on one bus never share: each meets the bus at
its own point.

**Ties go to the order written.** Among orders with no crossing, fewer columns
win, then shorter buses, then the order nearest the one the author wrote.

**A group is a backdrop behind its hosts**, so it must hold no host outside it:
an order that leaves a stranger's box inside a group's rectangle counts the same
as a crossing.

Pure functions on integers, so the schema can refuse what cannot be drawn
before any layout runs, and the text form can read the same columns the SVG
does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import permutations
from typing import Final

#: Up to this many hosts every order is tried; past it, a local search from a
#: few starting orders. Seven is 5 040 orders, each costing microseconds.
EXHAUSTIVE_MAX: Final = 7

#: How many improving passes the local search may make before it stops.
PASSES_MAX: Final = 40

Score = tuple[int, int, int, int]


@dataclass(frozen=True)
class Arrangement:
    """The columns, and what an imperfect order would cost the drawing."""

    columns: tuple[tuple[int, ...], ...]
    """Each column's hosts, by index, top to bottom."""

    column_of: tuple[int, ...]
    """Each host's column, by host index."""

    extents: tuple[tuple[int, int], ...]
    """Each network's first and last column, by network index."""

    crossings: tuple[tuple[int, int], ...]
    """Every (host, network) whose line would cross a bus it is not on."""

    clashes: tuple[tuple[int, int], ...]
    """Every (group, host) where a host outside the group sits in its backdrop,
    or (group, -1 - other) where two groups' backdrops overlap."""


def rows(networks: Sequence[int]) -> tuple[int, int]:
    """A host's vertical extent on a grid of buses (even rows) and gaps (odd rows).

    Bus `m` is row `2m`; the gap under it is `2m + 1`, where a host whose topmost
    bus is `m` has its box. The extent runs from the topmost bus to the lowest
    one, or to the box when the host is on one bus only.
    """
    low, high = min(networks), max(networks)
    return 2 * low, max(2 * high, 2 * low + 1)


def arrange(
    count: int,
    hosts: Sequence[Sequence[int]],
    groups: Sequence[Sequence[int]] = (),
) -> Arrangement:
    """The best column order for `hosts`, each the indices of the networks it is on.

    `count` is how many networks there are; `groups` lists each group's host
    indices. Deterministic: the same input always gives the same columns, and
    remembered, since the schema and every fit attempt ask the same question.
    """
    return _arranged(
        count,
        tuple(tuple(attached) for attached in hosts),
        tuple(tuple(members) for members in groups),
    )


@lru_cache(maxsize=64)
def _arranged(
    count: int,
    hosts: tuple[tuple[int, ...], ...],
    groups: tuple[tuple[int, ...], ...],
) -> Arrangement:
    nets = [tuple(sorted(set(attached))) for attached in hosts]
    extent = [rows(attached) for attached in nets]
    owner: dict[int, int] = {}
    for index, members in enumerate(groups):
        for member in members:
            owner.setdefault(member, index)
    total = len(nets)

    def place(order: Sequence[int]) -> list[int]:
        columns: list[list[int]] = []
        last = [-1] * count
        column_of = [0] * total
        for host in order:
            column = max(last[network] for network in nets[host]) + 1
            top, bottom = extent[host]
            while column < len(columns) and any(
                not (bottom < extent[other][0] or extent[other][1] < top)
                for other in columns[column]
            ):
                column += 1
            if column == len(columns):
                columns.append([])
            columns[column].append(host)
            column_of[host] = column
            for network in nets[host]:
                last[network] = column
        return column_of

    def judged(column_of: Sequence[int]) -> tuple[Score, Arrangement]:
        spans: list[tuple[int, int]] = []
        for network in range(count):
            on = [column_of[host] for host in range(total) if network in nets[host]]
            spans.append((min(on), max(on)) if on else (0, -1))
        crossings = [
            (host, network)
            for host in range(total)
            for network in range(nets[host][0] + 1, nets[host][-1])
            if network not in nets[host]
            and spans[network][0] <= column_of[host] <= spans[network][1]
        ]
        clashes: list[tuple[int, int]] = []
        boxes: list[tuple[int, int, int, int]] = []
        for index, members in enumerate(groups):
            if not members:
                boxes.append((0, -1, 0, -1))
                continue
            left = min(column_of[member] for member in members)
            right = max(column_of[member] for member in members)
            top = min(nets[member][0] for member in members)
            bottom = max(nets[member][0] for member in members)
            boxes.append((left, right, top, bottom))
            clashes.extend(
                (index, host)
                for host in range(total)
                if owner.get(host) != index
                and left <= column_of[host] <= right
                and top <= nets[host][0] <= bottom
            )
        for first in range(len(boxes)):
            for second in range(first + 1, len(boxes)):
                a, b = boxes[first], boxes[second]
                if a[0] <= b[1] and b[0] <= a[1] and a[2] <= b[3] and b[2] <= a[3]:
                    clashes.append((first, -1 - second))
        width = max(column_of, default=-1) + 1
        length = sum(max(right - left, 0) for left, right in spans)
        moved = sum(
            1
            for first in range(total)
            for second in range(first + 1, total)
            if column_of[first] > column_of[second]
        )
        columns = tuple(
            tuple(
                sorted(
                    (host for host in range(total) if column_of[host] == column),
                    key=lambda host: extent[host][0],
                )
            )
            for column in range(width)
        )
        score = (len(crossings) + len(clashes), width, length, moved)
        return score, Arrangement(
            columns=columns,
            column_of=tuple(column_of),
            extents=tuple(spans),
            crossings=tuple(crossings),
            clashes=tuple(clashes),
        )

    def scored(order: Sequence[int]) -> Score:
        return judged(place(order))[0]

    written = list(range(total))
    if total <= EXHAUSTIVE_MAX:
        best = min(permutations(written), key=lambda order: (scored(order), order))
        return judged(place(best))[1]

    # Group members together, at the first member's place, to start from.
    together: list[int] = []
    for host in written:
        if host in together:
            continue
        group = owner.get(host)
        if group is None:
            together.append(host)
        else:
            together.extend(member for member in groups[group] if member not in together)
    starts = [
        written,
        together,
        sorted(written, key=lambda host: (nets[host][0], nets[host][-1], host)),
        sorted(written, key=lambda host: (nets[host][-1], nets[host][0], host)),
    ]
    best_order: list[int] = written
    best_score: Score | None = None
    for start in starts:
        order, score = _searched(start, scored, groups)
        if best_score is None or score < best_score:
            best_order, best_score = order, score
    return judged(place(best_order))[1]


def _searched(
    start: list[int], scored: Callable[[Sequence[int]], Score], groups: Sequence[Sequence[int]]
) -> tuple[list[int], Score]:
    """A local search by moving one host, or one group, to another place."""
    order = list(start)
    score: Score = scored(order)
    for _ in range(PASSES_MAX):
        improved = False
        blocks: list[list[int]] = [[host] for host in order]
        blocks.extend([list(members) for members in groups if len(members) > 1])
        for block in blocks:
            rest = [host for host in order if host not in block]
            for place in range(len(rest) + 1):
                candidate = rest[:place] + block + rest[place:]
                if candidate == order:
                    continue
                trial: Score = scored(candidate)
                if trial < score:
                    order, score, improved = candidate, trial, True
                    break
        if not improved:
            break
    return order, score


__all__ = ["EXHAUSTIVE_MAX", "Arrangement", "arrange", "rows"]
