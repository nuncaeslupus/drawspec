"""The `sankey` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._constants import SANKEY_BAND, SANKEY_COLUMN_MAX, SANKEY_MIN_BAND
from drawspec.schema._model import Document, SankeyFlow, SankeyNode, Violation

#: Why a sankey has no place for a field an author may reach for.
SANKEY_REFUSED: Final = {
    "edges": ("a sankey's connections are its `flows`, each with the `amount` that goes along it"),
    "column": (
        "a node's column is derived from the flows — sources on the left, ends on the right, "
        "each node one column past the longest way in. Write the flows"
    ),
    "rank": (
        "a node's column is derived from the flows — sources on the left, ends on the right, "
        "each node one column past the longest way in. Write the flows"
    ),
    "percent": (
        "drawspec draws each band from its `amount`, so the thicknesses cannot disagree with "
        "the numbers. Write the amount"
    ),
    "share": (
        "drawspec draws each band from its `amount`, so the thicknesses cannot disagree with "
        "the numbers. Write the amount"
    ),
    "label": (
        "a band carries no words: what goes where is read from the nodes' totals, written "
        "beside each bar. Name the destination as a node instead"
    ),
}


def _sankey_refusal(violation: Violation) -> Violation:
    """A structural refusal in a sankey, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if name == "value" and parts[1:2] == ["flows"] and len(parts) == 4:
        return Violation(
            violation.pointer,
            "'value': a flow's number is its `amount` — how much goes from one node to the "
            "other, in the sankey's `unit`.",
        )
    if "is not a known field" in violation.message and name in SANKEY_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {SANKEY_REFUSED[name]}.")
    if name == "amount" and parts[1:2] == ["flows"] and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a flow's amount is its band's thickness, so it must be more than 0. A flow of "
            "nothing is not drawn: leave it out.",
        )
    if parts[1:] == ["nodes"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a sankey needs at least 2 nodes: an amount goes from one to another.",
        )
    return violation


def sankey_columns(ids: Sequence[str], flows: Sequence[tuple[str, str]]) -> dict[str, int]:
    """Each node's column: one past the longest way in, every end in the last column.

    `flows` must join known ids and close no loop. A node no flow touches is in the
    first column. Ends — nodes with nothing leaving — are moved to the last column,
    so every arrival lines up on the right edge, the way the quantity is read.
    """
    incoming: dict[str, list[str]] = {identifier: [] for identifier in ids}
    leaving: set[str] = set()
    for source, target in flows:
        incoming[target].append(source)
        leaving.add(source)
    column: dict[str, int] = {}

    def depth(identifier: str) -> int:
        if identifier not in column:
            column[identifier] = 0
            column[identifier] = max(
                (depth(source) + 1 for source in incoming[identifier]), default=0
            )
        return column[identifier]

    for identifier in ids:
        depth(identifier)
    last = max(column.values(), default=0)
    for identifier in ids:
        if identifier not in leaving and incoming[identifier]:
            column[identifier] = last
    return column


def sankey_amount(value: float, unit: str) -> str:
    """An amount as written: no trailing zeros, the unit after a space (`%` after none)."""
    text = f"{value:.10g}"
    if not unit:
        return text
    return f"{text}{unit}" if unit == "%" else f"{text} {unit}"


def _sankey_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that land, no loop, every middle node balanced, four columns, no hairline.

    Each is a fact about the numbers and the joins alone, so each is refused here,
    at its pointer, before any layout runs: an imbalance, a loop or a band too thin
    to see is never a question a smaller type size could answer.
    """
    found: list[Violation] = []
    written = document.get("unit")
    unit = written if isinstance(written, str) else ""
    nodes: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "nodes")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in nodes:
            found.append(
                Violation(_pointer("nodes", index, "id"), f"duplicate node id {identifier!r}")
            )
            continue
        nodes[identifier] = index

    # The flows that land, in written order: (index, from, to, amount).
    flows: list[tuple[int, str, str, float]] = []
    pairs: dict[tuple[str, str], int] = {}
    balance: list[tuple[str, str, float]] = []
    reaches: dict[str, set[str]] = {identifier: {identifier} for identifier in nodes}
    for index, entry in enumerate(_listed(document, "flows")):
        if not isinstance(entry, dict):
            continue
        ends = []
        for side in ("from", "to"):
            name = entry.get(side)
            if not isinstance(name, str):
                continue
            if name not in nodes:
                found.append(
                    Violation(
                        _pointer("flows", index, side),
                        f"{name!r} is not the id of any node" + _closest(name, nodes),
                    )
                )
                continue
            ends.append(name)
        if len(ends) != 2:
            continue
        source, target = ends
        if source == target:
            found.append(
                Violation(
                    _pointer("flows", index, "to"),
                    f"a flow from {source!r} to itself: an amount that stays where it is does "
                    "not flow. Leave it out.",
                )
            )
            continue
        amount = entry.get("amount")
        number = float(amount) if isinstance(amount, int | float) else 0.0
        balance.append((source, target, max(number, 0.0)))
        if (source, target) in pairs:
            found.append(
                Violation(
                    _pointer("flows", index),
                    f"a second flow from {source!r} to {target!r} (the first is "
                    f"/flows/{pairs[(source, target)]}): add the amounts into one flow.",
                )
            )
            continue
        if target in reaches[source]:
            found.append(
                Violation(
                    _pointer("flows", index),
                    f"the flow from {source!r} to {target!r} closes a loop — {target!r} already "
                    "leads back to it. A quantity does not flow backwards in a sankey: leave "
                    "this flow out, or draw the loop as a `cycle` or a `flow`.",
                )
            )
            continue
        pairs[(source, target)] = index
        # Everything that reached `source` now reaches `target` and what it leads to.
        downstream = {name for name, before in reaches.items() if target in before}
        for name in downstream:
            reaches[name] |= reaches[source]
        flows.append((index, source, target, max(number, 0.0)))

    touched = {name for _, source, target, _ in flows for name in (source, target)}
    for identifier, index in nodes.items():
        if identifier not in touched and not any(
            isinstance(entry, dict) and identifier in (entry.get("from"), entry.get("to"))
            for entry in _listed(document, "flows")
        ):
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"no flow reaches or leaves {identifier!r}, so it would be a bar of "
                    "nothing. Give it a flow, or leave it out.",
                )
            )

    into: dict[str, float] = dict.fromkeys(nodes, 0.0)
    out: dict[str, float] = dict.fromkeys(nodes, 0.0)
    for source, target, amount in balance:
        out[source] += amount
        into[target] += amount
    for identifier, index in nodes.items():
        arrived, left = into[identifier], out[identifier]
        if not (arrived and left) or abs(arrived - left) <= 1e-9 * max(arrived, left):
            continue
        more, verb = ("takes in", "sends on") if arrived > left else ("sends on", "takes in")
        difference = abs(arrived - left)
        found.append(
            Violation(
                _pointer("nodes", index),
                f"{identifier!r} {more} {sankey_amount(max(arrived, left), unit)} and {verb} "
                f"{sankey_amount(min(arrived, left), unit)}: the drawing would have to invent "
                f"where the difference of {sankey_amount(difference, unit)} "
                f"{'went' if arrived > left else 'came from'}. Add a flow of "
                f"{sankey_amount(difference, unit)} "
                f"{'to' if arrived > left else 'from'} a named node — `Lost`, `Idle`, a `note` "
                "— or correct the amounts.",
            )
        )

    columns = sankey_columns(list(nodes), [(source, target) for _, source, target, _ in flows])
    for identifier, index in nodes.items():
        if columns.get(identifier, 0) >= SANKEY_COLUMN_MAX:
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"{identifier!r} is {columns[identifier] + 1} steps from where the quantity "
                    f"starts, and a sankey can be read at {SANKEY_COLUMN_MAX} columns at most. "
                    "Draw one sankey per stage — the last column of one is the first of the "
                    "next — or merge the steps between.",
                )
            )
            break

    # The fullest column's total sets the scale: every node is as tall as what
    # passes through it, and a flow that skips a column passes through it too.
    totals: dict[int, float] = {}
    for identifier in nodes:
        column = columns.get(identifier, 0)
        totals[column] = totals.get(column, 0.0) + max(into[identifier], out[identifier])
    for _, source, target, amount in flows:
        for column in range(columns[source] + 1, columns[target]):
            totals[column] = totals.get(column, 0.0) + amount
    fullest = max(totals.values(), default=0.0)
    least = fullest * SANKEY_MIN_BAND / SANKEY_BAND
    ratio = round(SANKEY_BAND / SANKEY_MIN_BAND)
    for index, source, target, amount in flows:
        if 0 < amount < least:
            found.append(
                Violation(
                    _pointer("flows", index, "amount"),
                    f"the flow from {source!r} to {target!r} is {sankey_amount(amount, unit)} of "
                    f"the {sankey_amount(fullest, unit)} in the fullest column — under 1/{ratio} "
                    "of it, a band too thin to see. Merge the small flows into one flow to a "
                    "named `note` node (`Other`), and say what it holds in the caption.",
                )
            )
    return found


def _sankey_document(document: Mapping[str, Any]) -> Document:
    """A sankey: its nodes and flows in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        sankey_nodes=tuple(
            SankeyNode(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["nodes"]
        ),
        sankey_flows=tuple(
            SankeyFlow(
                source=entry["from"],
                target=entry["to"],
                amount=float(entry["amount"]),
                role=entry.get("role", "flow"),
            )
            for entry in document["flows"]
        ),
    )
