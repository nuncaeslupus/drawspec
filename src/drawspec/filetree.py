"""The path arithmetic behind the `files` kind — no drawing, no theme.

An author lists paths; this module turns them into rows. It is separate from the
renderer because two callers need the same answer: validation, which has to say
*which* entry is wrong before anything is drawn, and the renderer, which has to
agree with it about what a folder is. And it is separate from `drawspec.schema`
because the plain-text rendering needs the rows too, with no scene in sight.

Flat paths rather than nested objects, on purpose: a nested tree is a depth an
author can get wrong without seeing it, and a path cannot be. The folders a path
passes through are inferred, so `src/app/main.py` alone draws three rows.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

#: What an entry may say happened to it, as a diff would. Closed.
STATUSES: Final = ("added", "changed", "removed")

#: How siblings are ordered. `given` is the default because the order an author
#: wrote is usually the point — the entry file first, the config last.
ORDERS: Final = ("given", "name", "folders-first")

#: The last segment that stands for "and more here". Both spellings, because an
#: author types three dots and a formatter turns them into one character.
ELLIPSES: Final = ("...", "…")

#: The prefix each depth draws, per charset: (branch, last branch, pipe, blank).
CHARSETS: Final = {
    "unicode": ("├── ", "└── ", "│   ", "    "),
    "ascii": ("|-- ", "`-- ", "|   ", "    "),
}

#: The marks a diff status carries in text, where a pill cannot be drawn.
STATUS_MARKS: Final = {"added": "+", "changed": "~", "removed": "-"}


@dataclass(frozen=True)
class Entry:
    """One path an author wrote, and what they said about it."""

    path: str
    note: str = ""
    link: str = ""
    """Where a symbolic link points. Written, never followed or checked."""

    status: str = ""


@dataclass(frozen=True)
class Row:
    """One line of the finished tree, top to bottom."""

    name: str
    kind: str
    """`folder`, `file`, `link` or `more`."""

    depth: int
    lasts: tuple[bool, ...]
    """For each depth from 1 to this row's: whether the row's ancestor at that depth
    (the row itself, last) is its parent's last child. That is all a prefix needs."""

    note: str = ""
    link: str = ""
    status: str = ""
    parent: int | None = None
    """The index of this row's parent row, or None at the top."""


@dataclass
class _Node:
    name: str
    kind: str = "file"
    entry: Entry | None = None
    children: list[_Node] = field(default_factory=list)


def segments(path: str) -> list[str]:
    """The names along `path`. A trailing slash is not a name, it is a folder mark."""
    return path.rstrip("/").split("/")


def is_folder_path(path: str) -> bool:
    return path.endswith("/")


def problems(entries: Sequence[Entry]) -> list[tuple[int, str, str]]:
    """Everything wrong with `entries`, as (index, field, message).

    The checks JSON Schema cannot express: a path that is malformed, written
    twice, or used as a file and a folder at once.
    """
    found: list[tuple[int, str, str]] = []
    written: dict[str, tuple[int, str]] = {}
    """Every path written as an entry, and what it was written as."""
    passed: dict[str, int] = {}
    """Every folder some entry's path passes through, and the first entry that does."""

    for index, entry in enumerate(entries):
        message = _malformed(entry)
        if message:
            found.append(
                (
                    index,
                    "link" if message.startswith("link:") else "path",
                    message.removeprefix("link:"),
                )
            )
            continue
        names = segments(entry.path)
        for depth in range(1, len(names)):
            passed.setdefault("/".join(names[:depth]), index)
        if names[-1] in ELLIPSES:
            continue  # "the rest of this folder" — as many of those as the author likes
        key = "/".join(names)
        kind = _kind(entry)
        if key in written:
            first, was = written[key]
            found.append((index, "path", _twice(entry.path, first, was, kind)))
            continue
        written[key] = (index, kind)

    for key, (index, kind) in written.items():
        if kind != "folder" and key in passed:
            found.append(
                (
                    passed[key],
                    "path",
                    f"{entries[passed[key]].path!r} puts something inside {key!r}, which "
                    f"entry {index} says is a {kind}. Only a folder has contents.",
                )
            )
    return sorted(found)


def _kind(entry: Entry) -> str:
    return "link" if entry.link else "folder" if is_folder_path(entry.path) else "file"


def _malformed(entry: Entry) -> str:
    """Why this one entry cannot be a row, whatever the others say. Empty if it can."""
    path = entry.path
    if path.startswith("/") or not path.strip("/"):
        return (
            f"{path!r} is not a relative path. Write it from the top of the tree — "
            "`src/main.py`, not `/src/main.py`; the top folder itself is `root`."
        )
    names = segments(path)
    if any(name in ("", ".", "..") or name != name.strip() for name in names):
        return (
            f"{path!r} has an empty, '.' or '..' segment, or one with spaces at its "
            "ends. Each segment is one name in the tree."
        )
    if any(name in ELLIPSES for name in names[:-1]):
        return (
            f"{path!r} has '...' before its end. It stands for 'and more here', so it "
            "can only be the last segment."
        )
    if names[-1] in ELLIPSES and (entry.link or entry.status or is_folder_path(path)):
        return (
            f"{path!r} is a '...' row, which stands for entries not listed — it cannot "
            "be a link, carry a status, or end in '/'."
        )
    if entry.link and is_folder_path(path):
        return (
            f"link:{path!r} ends in '/' and names a link target. A link is drawn as "
            "itself, never followed, so it has no contents: drop the trailing slash."
        )
    return ""


def _twice(path: str, first: int, was: str, kind: str) -> str:
    if was == kind:
        return f"{path!r} is written twice (first as entry {first}). Say it once."
    return (
        f"{path!r} is a {kind} here and a {was} at entry {first}. A path is one or "
        "the other; a folder with nothing listed in it ends in '/'."
    )


def rows(entries: Sequence[Entry], root: str = "", order: str = "given") -> tuple[Row, ...]:
    """The tree `entries` describe, flattened to rows. Assumes `problems` is empty."""
    top = _Node(root, "folder")
    for entry in entries:
        names = segments(entry.path)
        node = top
        for name in names[:-1]:
            node = _child(node, name, "folder")
        last = names[-1]
        if last in ELLIPSES:
            label = f"… {entry.note}" if entry.note else "…"
            node.children.append(_Node(label, "more", Entry(entry.path)))
            continue
        kind = "link" if entry.link else "folder" if is_folder_path(entry.path) else "file"
        child = _child(node, last, kind)
        child.entry = entry

    _sort(top, order)
    out: list[Row] = []
    if root:
        out.append(Row(root, "folder", 0, ()))
        _flatten(top, 1, (), 0, out)
    else:
        _flatten(top, 0, (), None, out)
    return tuple(out)


def _child(node: _Node, name: str, kind: str) -> _Node:
    for child in node.children:
        if child.name == name and child.kind != "more":
            if kind == "folder":
                child.kind = "folder"
            return child
    child = _Node(name, kind)
    node.children.append(child)
    return child


def _natural(name: str) -> list[tuple[int, int | str]]:
    """Sort key that puts `file2` before `file10`, case aside."""
    return [
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"(\d+)", name.casefold())
        if part
    ]


def _sort(node: _Node, order: str) -> None:
    for child in node.children:
        _sort(child, order)
    if order == "given":
        return
    # A '...' row stays last whatever the order: it is "the rest", not a name.
    listed = [child for child in node.children if child.kind != "more"]
    rest = [child for child in node.children if child.kind == "more"]
    if order == "folders-first":
        listed.sort(key=lambda child: (child.kind != "folder", _natural(child.name)))
    else:
        listed.sort(key=lambda child: _natural(child.name))
    node.children = listed + rest


def _flatten(
    node: _Node, depth: int, lasts: tuple[bool, ...], parent: int | None, out: list[Row]
) -> None:
    for position, child in enumerate(node.children):
        last = position == len(node.children) - 1
        chain = (*lasts, last) if depth else ()
        entry = child.entry or Entry(child.name)
        out.append(
            Row(child.name, child.kind, depth, chain, entry.note, entry.link, entry.status, parent)
        )
        _flatten(child, depth + 1, chain, len(out) - 1, out)


def text(rows: Sequence[Row], charset: str = "unicode") -> str:
    """The tree as plain text, the way `tree` prints it — for a code block."""
    branch, final, pipe, blank = CHARSETS[charset]
    marked = any(row.status for row in rows)
    labels: list[str] = []
    for row in rows:
        prefix = "".join(blank if last else pipe for last in row.lasts[:-1])
        if row.lasts:
            prefix += final if row.lasts[-1] else branch
        name = row.name if charset == "unicode" else row.name.replace("…", "...")
        if row.kind == "folder":
            name += "/"
        if row.kind == "link":
            name += f" -> {row.link}"
        mark = f"{STATUS_MARKS[row.status]} " if row.status else "  "
        labels.append((mark if marked else "") + prefix + name)
    width = max(len(label) for label in labels)
    lines = [
        f"{label.ljust(width)}  # {row.note}" if row.note else label
        for label, row in zip(labels, rows, strict=True)
    ]
    return "\n".join(line.rstrip() for line in lines) + "\n"


__all__ = [
    "CHARSETS",
    "ELLIPSES",
    "ORDERS",
    "STATUSES",
    "Entry",
    "Row",
    "problems",
    "rows",
    "text",
]
