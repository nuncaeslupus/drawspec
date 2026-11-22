"""The `board` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _closest, _listed, _optional_number, _pointer
from drawspec.schema._model import BoardColumn, Card, Document, Slice, Violation

#: Fields a board refuses by name, and why: what an author reaches for when the
#: board is really something else, or when appearance is wanted per card.
BOARD_REFUSED: Final = {
    "edges": (
        "a board has no connectors: its cards are sorted, not joined. If the order between "
        "cards matters, it is a `flow` — or `lanes`, when who hands off to whom matters"
    ),
    "label": "a card has its `text`, and its kind is its column; a second label is a tag",
    "tag": "appearance is the role's, and a card's kind is its column. Name it in the text",
    "tags": "appearance is the role's, and a card's kind is its column. Name it in the text",
    "colour": "appearance is the role's, and a card's kind is its column",
}


def _board_refusal(violation: Violation) -> Violation:
    """An unknown field on a board, told why a board has no place for it."""
    name = violation.pointer.rsplit("/", 1)[-1]
    if name in BOARD_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {BOARD_REFUSED[name]}.")
    return violation


def _board_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a board may not be: cards in columns or rows it does not have, half a story map.

    Column and row ids are unique and land; with rows every card names one and
    without them none does; a cut names a row that has another below it; a card
    with an actor keeps its text on one line.
    """
    found: list[Violation] = []

    def ids(name: str) -> dict[str, int]:
        seen: dict[str, int] = {}
        for index, entry in enumerate(_listed(document, name)):
            identifier = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(identifier, str):
                continue
            if identifier in seen:
                found.append(
                    Violation(
                        _pointer(name, index, "id"), f"duplicate {name[:-1]} id {identifier!r}"
                    )
                )
                continue
            seen[identifier] = index
        return seen

    columns = ids("columns")
    rows = ids("rows")
    has_rows = isinstance(document.get("rows"), list)

    cut = document.get("cut")
    if isinstance(cut, str):
        if not has_rows:
            found.append(
                Violation(
                    "/cut",
                    "a cut is drawn under a row, and this board has no `rows`. Add the slices "
                    "(a first release and what follows), or drop the cut.",
                )
            )
        elif cut not in rows:
            found.append(
                Violation("/cut", f"{cut!r} is not the id of any row" + _closest(cut, rows))
            )
        elif rows[cut] == len(document["rows"]) - 1:
            found.append(
                Violation(
                    "/cut",
                    f"{cut!r} is the last row, and a cut with nothing below it cuts nothing. "
                    f"Name the row the first release ends at.",
                )
            )

    for index, card in enumerate(_listed(document, "cards")):
        if not isinstance(card, dict):
            continue
        column = card.get("column")
        if isinstance(column, str) and column not in columns:
            found.append(
                Violation(
                    _pointer("cards", index, "column"),
                    f"{column!r} is not the id of any column" + _closest(column, columns),
                )
            )
        row = card.get("row")
        if has_rows and "row" not in card:
            found.append(
                Violation(
                    _pointer("cards", index, "row"),
                    "'row' is required: this board has rows, so every card is in one — half a "
                    "story map is a mistake. Name the slice it ships in.",
                )
            )
        elif not has_rows and "row" in card:
            found.append(
                Violation(
                    _pointer("cards", index, "row"),
                    "this board has no `rows`, so a card cannot be in one. Add the rows (a "
                    "story map), or drop 'row' from every card (a kanban board).",
                )
            )
        elif isinstance(row, str) and row not in rows:
            found.append(
                Violation(
                    _pointer("cards", index, "row"),
                    f"{row!r} is not the id of any row" + _closest(row, rows),
                )
            )
        text = card.get("text")
        if isinstance(card.get("actor"), str) and isinstance(text, str) and "\n" in text:
            found.append(
                Violation(
                    _pointer("cards", index, "text"),
                    "a card with an actor has the actor as its lead, so its text may not start "
                    "a second paragraph. Put it on one line, or the rest in `note`.",
                )
            )
    return found


def _board_document(document: Mapping[str, Any]) -> Document:
    """A board: its columns, its rows if any, its cut, and its cards in order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        board_columns=tuple(
            BoardColumn(
                id=entry["id"],
                text=entry["text"],
                limit=entry.get("limit"),
                role=entry.get("role", "step"),
            )
            for entry in document["columns"]
        ),
        slices=tuple(
            Slice(id=entry["id"], text=entry["text"]) for entry in document.get("rows", ())
        ),
        cut=str(document.get("cut", "")),
        cards=tuple(
            Card(
                text=entry["text"],
                column=entry["column"],
                row=entry.get("row", ""),
                role=entry.get("role", "step"),
                actor=entry.get("actor", ""),
                note=entry.get("note", ""),
            )
            for entry in document["cards"]
        ),
    )
