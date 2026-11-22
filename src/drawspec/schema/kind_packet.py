"""The `packet` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import PACKET_ROW_BITS, PACKET_ROW_DEFAULT, PACKET_ROW_MAX
from drawspec.schema._model import Document, PacketField, Violation

#: Why a packet has no place for a field an author may reach for.
PACKET_REFUSED: Final = {
    "start": (
        "a field starts where the one before it ends: write the fields in order, each with "
        "its width in `bits`"
    ),
    "end": "a field ends where its `bits` take it, counted from where the one before it ended",
    "offset": "a field's offset is the sum of the widths written before it, never written",
    "position": "a field's position is the sum of the widths written before it, never written",
    "range": (
        "a field is its width in `bits`, in order; a bit range such as `0-3` is a position, "
        "which drawspec derives"
    ),
    "length": "a field's width is `bits`",
    "size": "a field's width is `bits`; the type size is the theme's",
    "name": "a field's name is `text`",
    "label": "a field's name is `text`",
    "attr": "what a field holds — a fixed value, a reset value, its access — is `holds`",
    "value": "what a field holds — a fixed value, a reset value, its access — is `holds`",
    "reset": "a reset value is what the field `holds`: write it there (`0x00`)",
    "access": "a field's access is what it `holds`: write it there (`R/W`)",
    "reserved": 'a reserved field is `"role": "reserved"`',
    "type": 'a reserved field is `"role": "reserved"`; anything else is an ordinary field',
    "rotate": (
        "a name is turned on its side by drawspec, only when it will not fit across its field"
    ),
    "lanes": "the rows are `bits_per_row` wide, and as many as the fields fill",
    "vspace": "a row's height is measured from the words in it",
    "hspace": "the drawing is the canvas's width; a bit is its share of the row",
    "bits_per_row": "`bits_per_row` is the document's, at the top: every row is as wide",
    "numbering": "`numbering` is the document's, at the top: every row counts the same way",
    "colour": "a field is told by its name and its role; a reserved one is hatched by the theme",
    "edges": "a packet is a row of fields side by side; there is nothing to connect",
    "variable": (
        "a packet draws fields of a known width. Draw a variable-length field (options, the "
        "payload) as a whole row and say so in its words: `Options (variable)`"
    ),
}


#: The packet's own top-level fields: refused by name only inside a field.
_PACKET_TOP: Final = ("bits_per_row", "numbering")


def _packet_refusal(violation: Violation) -> Violation:
    """A structural refusal in a packet, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    top = len(parts) == 2 and name in _PACKET_TOP
    if unknown and name in PACKET_REFUSED and not top:
        return Violation(violation.pointer, f"{name!r}: {PACKET_REFUSED[name]}.")
    if name == "bits" and len(parts) == 4 and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a field is at least one bit wide; a field of no bits is not drawn — leave it out.",
        )
    return violation


def _packet_violations(document: Mapping[str, Any]) -> list[Violation]:
    """The row width, every field's words, the row cap, and whole rows for a register."""
    found: list[Violation] = []
    row = document.get("bits_per_row", PACKET_ROW_DEFAULT)
    if not isinstance(row, int) or isinstance(row, bool):
        row = PACKET_ROW_DEFAULT
    elif row not in PACKET_ROW_BITS:
        found.append(
            Violation(
                "/bits_per_row",
                f"a row of {row} bits does not line up with a byte: draw it at "
                f"{', '.join(str(bits) for bits in PACKET_ROW_BITS[:-1])} or "
                f"{PACKET_ROW_BITS[-1]} bits.",
            )
        )
        row = PACKET_ROW_DEFAULT
    total = 0
    for index, entry in enumerate(_listed(document, "fields")):
        if not isinstance(entry, dict):
            continue
        found.extend(_packet_field_violations(entry, _pointer("fields", index)))
        bits = entry.get("bits")
        if isinstance(bits, int) and not isinstance(bits, bool) and bits > 0:
            total += bits
    rows = -(-total // row)
    if rows > PACKET_ROW_MAX:
        found.append(
            Violation(
                "/fields",
                f"{total} bits make {rows} rows of {row}, past what one packet can be read at — "
                f"{PACKET_ROW_MAX} rows at most. Split it: the header in one drawing, each "
                f"long part (options, a payload) in its own.",
            )
        )
    if document.get("numbering") == "right" and total % row:
        found.append(
            Violation(
                "/fields",
                f"the fields add up to {total} bits, which is not a whole number of "
                f"{row}-bit rows. A register numbered from the right counts down to bit 0 at "
                f"the end of its last row, so its fields must fill every row: add the "
                f"{row - total % row} missing bits, as a reserved field if they are unused.",
            )
        )
    return found


def _packet_field_violations(entry: Mapping[str, Any], here: str) -> list[Violation]:
    """One field's words: a name unless reserved, one line, and a `short` that is shorter."""
    found: list[Violation] = []
    text = entry.get("text")
    if "text" not in entry and entry.get("role") != "reserved":
        found.append(
            Violation(
                f"{here}/text",
                "a field needs its name in `text`. Only a reserved field "
                '(`"role": "reserved"`) may be left blank.',
            )
        )
    if isinstance(text, str) and not text.strip():
        found.append(
            Violation(
                f"{here}/text",
                "a field's name needs words; leave `text` out of a blank reserved field.",
            )
        )
    if isinstance(text, str) and "\n" in text:
        found.append(
            Violation(
                f"{here}/text",
                "a field's name is one line; drawspec breaks it at spaces when the field is "
                "narrow. Put a second thought in `note`.",
            )
        )
    for name in ("short", "holds", "note"):
        value = entry.get(name)
        if isinstance(value, str) and not value.strip():
            found.append(
                Violation(f"{here}/{name}", f"an empty {name!r} says nothing: leave it out.")
            )
    short = entry.get("short")
    if isinstance(short, str) and short.strip():
        if not isinstance(text, str) or not text.strip():
            found.append(
                Violation(
                    f"{here}/short",
                    "a `short` abbreviates the field's `text`, and this field has none.",
                )
            )
        elif len(short) >= len(text):
            found.append(
                Violation(
                    f"{here}/short",
                    f"{short!r} is no shorter than {text!r}: a `short` is the abbreviation "
                    f"drawn when the name will not fit, so it must be shorter.",
                )
            )
    return found


def _packet_document(document: Mapping[str, Any]) -> Document:
    """A packet: its row width, its numbering and its fields, in reading order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        packet_row_bits=int(document.get("bits_per_row", PACKET_ROW_DEFAULT)),
        packet_numbering=str(document.get("numbering", "left")),
        packet_fields=tuple(
            PacketField(
                bits=int(entry["bits"]),
                text=str(entry.get("text", "")),
                short=str(entry.get("short", "")),
                holds=str(entry.get("holds", "")),
                note=str(entry.get("note", "")),
                role=str(entry.get("role", "field")),
            )
            for entry in document["fields"]
        ),
    )
