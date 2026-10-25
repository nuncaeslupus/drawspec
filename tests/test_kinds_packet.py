"""`packet` — a protocol header or a register as bit fields in rows of a fixed width.

The kind's promises: fields are laid end to end in reading order and nothing carries
a position; a field that crosses a row's end is split there, its cut edges marked;
the ruler numbers bit 0 at the left (RFC) or at the right of the last row (register);
a name that will not fit is broken, stood on its side, swapped for the author's
`short`, or keyed — never shrunk and never abbreviated by drawspec; and every
refusal in the proposal comes back at its pointer.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DrawspecError, FitError, ThemeError
from drawspec.kinds.packet import (
    EMPHASIS_EDGE_ROLE,
    OPEN_ROLE,
    PacketDrawing,
    bit_number,
    marker_for,
    packet_drawing,
    pieces_of,
)
from drawspec.render import render_text
from drawspec.scene import Path as ScenePath
from drawspec.scene import Polygon, TextRun
from drawspec.schema import PACKET_FIELD_MAX, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("packet-*.json"))


def packet(*fields: dict[str, Any], **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {"version": 1, "kind": "packet", "fields": list(fields)}
    document.update(extra)
    return document


def udp() -> dict[str, Any]:
    return packet(
        {"text": "Source Port", "bits": 16},
        {"text": "Destination Port", "bits": 16},
        {"text": "Length", "bits": 16},
        {"text": "Checksum", "bits": 16},
    )


def drawn(document: dict[str, Any], theme: Theme = THEME) -> PacketDrawing:
    return packet_drawing(parse_document(document), theme, MEASURER)


def text(document: dict[str, Any], **options: Any) -> str:
    return render_text(parse_document(document), **options)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[2] - 0.01 and b[0] < a[2] - 0.01 and a[1] < b[3] - 0.01 and b[1] < a[3] - 0.01


# -- the references -----------------------------------------------------------


def test_there_are_references_for_a_header_and_a_register() -> None:
    kinds = {json.loads(path.read_text()).get("numbering", "left") for path in REFERENCES}
    assert len(REFERENCES) >= 3
    assert kinds == {"left", "right"}


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_validates_renders_and_has_a_text_form(path: Path) -> None:
    document = json.loads(path.read_text())
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")
    assert text(document)
    assert text(document, charset="ascii").isascii()


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_words_in_a_reference_overlap_and_all_sit_on_the_canvas(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    for first, second in itertools.combinations(drawing.texts, 2):
        assert not overlaps(first, second), (first, second)
    for left, top, right, bottom in drawing.texts:
        assert left >= -0.01 and right <= drawing.scene.width + 0.01
        assert top >= -0.01 and bottom <= drawing.scene.height + 0.01


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_word_in_a_cell_stays_inside_it(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    bottom = max(cell[3] for cell in drawing.cells)
    top = min(cell[1] for cell in drawing.cells)
    for box in drawing.texts:
        if box[1] < top or box[3] > bottom:
            continue  # the ruler and the key
        assert any(
            cell[0] - 0.01 <= box[0] and box[2] <= cell[2] + 0.01 and cell[1] <= box[1]
            for cell in drawing.cells
        ), box


# -- the arithmetic -----------------------------------------------------------


def test_fields_are_laid_end_to_end_and_split_at_a_row_end() -> None:
    document = parse_document(
        packet({"text": "A", "bits": 20}, {"text": "B", "bits": 20}, {"text": "C", "bits": 8})
    )
    pieces, total = pieces_of(document.packet_fields, 32)
    assert total == 48
    assert [(p.field, p.row, p.start, p.end) for p in pieces] == [
        (0, 0, 0, 20),
        (1, 0, 20, 32),
        (1, 1, 0, 8),
        (2, 1, 8, 16),
    ]
    assert pieces[1].open_end and pieces[2].open_start
    assert not pieces[0].open_end and not pieces[3].open_start


def test_a_field_may_run_over_several_rows() -> None:
    document = parse_document(packet({"text": "Payload", "bits": 80}, bits_per_row=32))
    pieces, _ = pieces_of(document.packet_fields, 32)
    assert [(p.row, p.bits, p.open_start, p.open_end) for p in pieces] == [
        (0, 32, False, True),
        (1, 32, True, True),
        (2, 16, True, False),
    ]


def test_a_split_field_draws_its_cut_edges_dashed_and_names_itself_once_fully() -> None:
    drawing = drawn(packet({"text": "Address", "bits": 48}, {"text": "Port", "bits": 16}))
    dashed = [
        primitive
        for primitive in drawing.scene.primitives
        if isinstance(primitive, ScenePath) and primitive.role == OPEN_ROLE
    ]
    assert len(dashed) == 2
    xs = sorted(primitive.points[0][0] for primitive in dashed)
    assert xs == pytest.approx([0.0, drawing.scene.width])


def test_bit_numbers_count_from_the_left_or_down_from_the_top_left() -> None:
    assert [bit_number(0, column, 32, 64, "left") for column in (0, 31)] == [0, 31]
    assert [bit_number(1, column, 32, 64, "left") for column in (0, 31)] == [0, 31]
    assert [bit_number(0, column, 32, 64, "right") for column in (0, 31)] == [63, 32]
    assert [bit_number(1, column, 32, 64, "right") for column in (0, 31)] == [31, 0]


def test_the_rfc_ruler_is_drawn_once_and_a_register_rules_every_row() -> None:
    left = drawn(udp())
    assert {number for number, _, _ in left.ruler} >= {0, 31}
    assert len({baseline for _, _, baseline in left.ruler}) == 1
    register = drawn({**udp(), "numbering": "right"})
    assert len({baseline for _, _, baseline in register.ruler}) == 2
    assert {number for number, _, _ in register.ruler} >= {63, 32, 31, 0}


def test_the_ruler_skips_numbers_rather_than_crowd_them() -> None:
    wide = drawn(packet({"text": "Word", "bits": 64}, bits_per_row=64))
    shown = sorted(number for number, _, _ in wide.ruler)
    assert 0 in shown and 63 in shown
    assert len(shown) < 64


# -- fitting a name -------------------------------------------------------------


def test_a_name_that_fits_is_written_across_its_field() -> None:
    assert drawn(udp()).placements == ("across",) * 4


def test_a_short_name_in_a_one_bit_field_stands_on_its_side() -> None:
    drawing = drawn(packet({"text": "SYN", "bits": 1}, {"text": "Rest", "bits": 31}))
    assert drawing.placements[0] == "side"
    runs = [p for p in drawing.scene.primitives if isinstance(p, TextRun) and p.rotate]
    assert [run.text for run in runs] == ["SYN"]


def test_the_authors_short_stands_in_and_the_key_spells_it_out() -> None:
    drawing = drawn(
        packet({"text": "Don't Fragment", "short": "DF", "bits": 1}, {"text": "Rest", "bits": 31})
    )
    assert drawing.placements[0] in ("short", "short-side")
    assert ("DF", "Don't Fragment") in drawing.key


def test_a_name_with_no_room_and_no_short_is_keyed_by_a_letter() -> None:
    drawing = drawn(
        packet(
            {"text": "Explicit Congestion Notification", "bits": 1},
            {"text": "Rest", "bits": 31},
        )
    )
    assert drawing.placements[0] == "marker"
    assert drawing.key[0] == ("a", "Explicit Congestion Notification")


def test_markers_are_letters_so_they_are_never_read_as_a_value() -> None:
    assert [marker_for(count) for count in (0, 1, 25, 26, 27)] == ["a", "b", "z", "aa", "ab"]


def test_a_note_and_a_hidden_holds_go_to_the_key() -> None:
    drawing = drawn(
        packet(
            {"text": "Version", "bits": 4, "holds": "4", "note": "Always 4."},
            {"text": "R", "bits": 1, "holds": "0x00000"},
            {"text": "Rest", "bits": 27},
        )
    )
    assert ("Version", "Always 4.") in drawing.key
    assert ("R", "`0x00000`") in drawing.key


def test_a_blank_reserved_field_is_hatched_and_needs_no_name() -> None:
    document = packet({"role": "reserved", "bits": 8}, {"text": "Data", "bits": 24})
    assert validate_document(document) == ()
    drawing = drawn(document)
    fills = [p for p in drawing.scene.primitives if isinstance(p, Polygon) and p.region]
    assert [fill.fill for fill in fills] == ["hatch"]
    assert drawing.placements[0] == "blank"


def test_the_theme_chooses_the_reserved_pattern() -> None:
    theme = load_theme({"version": 1, "packet": {"reserved_fill": "dots"}})
    drawing = drawn(packet({"role": "reserved", "bits": 8}, {"text": "Data", "bits": 24}), theme)
    fills = [p for p in drawing.scene.primitives if isinstance(p, Polygon) and p.region]
    assert [fill.fill for fill in fills] == ["dots"]
    with pytest.raises(ThemeError, match="reserved_fill"):
        load_theme({"version": 1, "packet": {"reserved_fill": "red"}})


def test_an_emphasis_field_is_outlined_heavier() -> None:
    drawing = drawn(
        packet({"text": "Key", "bits": 8, "role": "emphasis"}, {"text": "R", "bits": 24})
    )
    heavy = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, ScenePath) and p.role == EMPHASIS_EDGE_ROLE
    ]
    assert len(heavy) == 4


def test_a_field_too_narrow_even_for_its_letter_is_refused() -> None:
    document = packet(
        *({"text": f"Flag number {n}", "bits": 1} for n in range(40)), bits_per_row=64
    )
    with pytest.raises(FitError, match="too narrow"):
        drawn({**document, "width": 300})


# -- text -------------------------------------------------------------------


def test_text_is_the_rfc_picture() -> None:
    drawing = text(udp(), charset="ascii")
    lines = drawing.splitlines()
    assert lines[0].split() == ["0", "1", "2", "3"]
    assert lines[1].split()[:3] == ["0", "1", "2"]
    assert lines[2] == "+" + "-+" * 32
    assert lines[3].startswith("|") and "Source Port" in lines[3]


def test_text_marks_a_cut_edge() -> None:
    drawing = text(packet({"text": "Address", "bits": 48}, {"text": "Port", "bits": 16}))
    assert "┆" in drawing
    assert ":" in text(
        packet({"text": "Address", "bits": 48}, {"text": "Port", "bits": 16}), charset="ascii"
    )


def test_text_stands_a_flag_on_end_a_letter_to_a_line() -> None:
    drawing = text(packet({"text": "SYN", "bits": 1}, {"text": "Rest", "bits": 31}))
    rows = [line for line in drawing.splitlines() if line.startswith("│")]
    assert [row[1] for row in rows] == ["S", "Y", "N"]


def test_text_numbers_a_register_from_the_right_on_every_row() -> None:
    drawing = text({**udp(), "numbering": "right"})
    units = [
        line for line in drawing.splitlines() if line.startswith(" 1 0") or line.startswith(" 3")
    ]
    assert any(line.rstrip().endswith("2") for line in units)  # bit 32 ends the first row
    assert drawing.splitlines()[-1].rstrip().endswith("┘")


def test_text_refuses_a_row_wider_than_the_width() -> None:
    document = packet({"text": "Word", "bits": 64}, bits_per_row=64)
    with pytest.raises(FitError, match="/bits_per_row"):
        text(document)
    assert text(document, width=129)


def test_the_example_renders_in_both_forms() -> None:
    from drawspec.examples import EXAMPLES

    example = dict(EXAMPLES["packet"])
    assert validate_document(example) == ()
    assert render(example).startswith("<svg")
    assert "Count" in text(example)


# -- refusals -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("document", "pointer", "words"),
    [
        (packet({"text": "A", "bits": 8}, bits_per_row=12), "/bits_per_row", "byte"),
        (packet({"text": "A", "bits": 0}), "/fields/0/bits", "at least one bit"),
        (packet({"text": "A", "bits": 2.5}), "/fields/0/bits", ""),
        (packet({"text": "A", "bits": 8, "start": 0}), "/fields/0/start", "order"),
        (packet({"text": "A", "bits": 8, "range": "0-7"}), "/fields/0/range", "position"),
        (packet({"text": "A", "bits": 8, "value": "4"}), "/fields/0/value", "holds"),
        (packet({"name": "A", "bits": 8}), "/fields/0/name", "text"),
        (packet({"text": "A", "bits": 8, "reserved": True}), "/fields/0/reserved", "role"),
        (packet({"text": "A", "bits": 8, "variable": True}), "/fields/0/variable", "Options"),
        (packet({"bits": 8}), "/fields/0/text", "reserved"),
        (packet({"text": " ", "bits": 8}), "/fields/0/text", "words"),
        (packet({"text": "A\nB", "bits": 8}), "/fields/0/text", "one line"),
        (packet({"text": "Flag", "short": "Flags", "bits": 8}), "/fields/0/short", "shorter"),
        (packet({"role": "reserved", "short": "R", "bits": 8}), "/fields/0/short", "none"),
        (packet({"text": "A", "bits": 8, "note": ""}), "/fields/0/note", "empty"),
        (packet({"text": "A", "bits": 8, "role": "flag"}), "/fields/0/role", ""),
        (packet({"text": "A", "bits": 8}, numbering="middle"), "/numbering", ""),
        (packet({"text": "A", "bits": 8, "numbering": "right"}), "/fields/0/numbering", "top"),
        (packet({"text": "A", "bits": 9}, numbering="right", bits_per_row=8), "/fields", "whole"),
        (packet({"text": "A", "bits": 17 * 32}), "/fields", "16 rows"),
        (packet({"text": "A", "bits": 8}, edges=[]), "/edges", ""),
    ],
)
def test_refusals_come_back_at_their_pointer(
    document: dict[str, Any], pointer: str, words: str
) -> None:
    assert pointer in pointers(document), messages(document)
    assert words in messages(document)


def test_more_fields_than_the_budget_is_refused() -> None:
    document = packet(*({"text": "F", "bits": 1} for _ in range(PACKET_FIELD_MAX + 1)))
    assert f"/fields/{PACKET_FIELD_MAX}" in pointers(document)


def test_more_than_two_emphasised_fields_is_refused() -> None:
    document = packet(*({"text": "F", "bits": 8, "role": "emphasis"} for _ in range(3)))
    assert "/fields/2/role" in pointers(document)


def test_a_document_with_no_fields_is_refused() -> None:
    assert "/fields" in pointers(packet())


def test_a_kind_with_a_text_form_names_packet() -> None:
    document = parse_document(
        {
            "version": 1,
            "kind": "pie",
            "parts": [{"text": "A", "amount": 1}, {"text": "B", "amount": 2}],
        }
    )
    with pytest.raises(DrawspecError, match="`packet`"):
        render_text(document)


def test_text_counts_wide_characters_in_terminal_cells() -> None:
    from drawspec.textgrid import cells

    document = packet(
        {"text": "状态", "bits": 4},
        {"text": "字", "bits": 1},
        {"text": "Café", "bits": 11},
        bits_per_row=16,
    )
    drawing = text(document)
    rows = [line for line in drawing.splitlines() if line.startswith(("┌", "│", "└"))]
    assert {cells(row) for row in rows} == {33}
    assert "a  字" in drawing  # too wide to stand in one cell: keyed
