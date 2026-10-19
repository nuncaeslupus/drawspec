"""Every free-text field a kind accepts ends up in the drawing.

Issue #134: a `cycle` edge took a `label`, validated it and drew nothing. A
field that is accepted and has no effect is the worst outcome available: the
author believes they configured something, and nothing tells them otherwise.

So this walks the field tables themselves — not a list kept beside them — for
every kind's example document. It writes a unique marker into each optional
free-text field, one field at a time, and requires one of two outcomes: the
document is refused (the field is an identifier or reference, so a marker is not
a legal value), or the marker is in the SVG. A third outcome, *accepted and not
drawn*, is allowed only for the fields named in `NOT_DRAWN`, each with its reason.
The list is also checked the other way, so it cannot outlive what it excuses.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pytest

from drawspec.errors import DrawspecError
from drawspec.examples import EXAMPLES
from drawspec.render import render
from drawspec.schema import OBJECTS, FieldSpec, fields_for

MARKER = "Zqxmarker"

#: Strings that are not words for the reader. `$schema` is an editor hint, and an
#: `id` is a name other fields refer to: drawn through those, never itself.
NOT_TEXT = frozenset({"$schema", "id", "theme"})

#: Fields accepted and not drawn, on purpose. Keyed `kind:path/field`.
NOT_DRAWN: Mapping[str, str] = {
    # A grouping key, not words: the cell is filled by the `scale` step it names.
    "matrix:cells/0/group": "a fill key",
    # Which bars stack together, not words: it decides geometry.
    "chart:series/0/stack": "a stacking key",
    # Only `timeline` draws a note. Refusing it elsewhere would fail documents the
    # published v1 schema allows (see `test_caption.py`), so it stays accepted and
    # its description says where it is drawn. Drawing it is the open fix.
    "flow:nodes/0/note": "v1 keeps it; only timeline draws one",
    "tree:nodes/0/note": "v1 keeps it; only timeline draws one",
    "cycle:nodes/0/note": "v1 keeps it; only timeline draws one",
    "stack:items/0/note": "v1 keeps it; only timeline draws one",
    "columns:items/0/note": "v1 keeps it; only timeline draws one",
    "pyramid:levels/0/note": "v1 keeps it; only timeline draws one",
    "funnel:stages/0/note": "v1 keeps it; only timeline draws one",
}


def _slots(
    obj: Mapping[str, Any], specs: Sequence[FieldSpec], path: tuple[str | int, ...]
) -> Iterator[tuple[tuple[str | int, ...], str]]:
    """Each optional free-text field on `obj` and on the first of each nested list."""
    for spec in specs:
        free = spec.kind == "string" and not spec.enum and not spec.required
        if free and spec.name not in NOT_TEXT:
            yield path, spec.name
        value = obj.get(spec.name)
        if spec.kind == "object" and spec.ref and isinstance(value, dict):
            yield from _slots(value, OBJECTS[spec.ref], (*path, spec.name))
        listed = spec.kind == "array" and spec.item_ref and isinstance(value, list)
        if listed and value and isinstance(value[0], dict):
            yield from _slots(value[0], OBJECTS[spec.item_ref], (*path, spec.name, 0))


def _undrawn(kind: str) -> set[str]:
    """Every field of `kind` that validates with a marker and draws without it."""
    example = EXAMPLES[kind]
    found = set()
    for path, name in _slots(example, fields_for(kind), ()):
        document = copy.deepcopy(dict(example))
        target: Any = document
        for step in path:
            target = target[step]
        target[name] = MARKER
        try:
            drawing = render(document)
        except DrawspecError:
            continue
        if MARKER not in drawing:
            found.add(f"{kind}:{'/'.join(map(str, path))}/{name}")
    return found


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_every_accepted_text_field_is_drawn(kind: str) -> None:
    """Accepted means drawn, or refused by name — never accepted and dropped."""
    excused = {key for key in NOT_DRAWN if key.startswith(f"{kind}:")}
    assert _undrawn(kind) == excused
