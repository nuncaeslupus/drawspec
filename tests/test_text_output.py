"""Text output: `render --format text` for the kinds that sit on a grid.

The proposal (`docs/proposals/text.md`, phase 1) makes text a second emitter
rather than a rasteriser, and these are its gates. Each is a property of every
drawing, checked over every reference document of every kind with a text form
and in both character sets, because the defects a text drawing has are the ones
nobody reads closely enough to see: a line one cell over the terminal, a label
cut short where a column ended, a box-drawing character in an "ASCII" drawing
that a mail client turns into `?`.

**Width is measured in terminal cells.** An East Asian wide character is two of
them, so a label in Japanese that counts 10 characters takes 20 columns, and a
drawing measured in characters would overflow a terminal it claimed to fit.

**Every reference document fits 80 columns, or is listed in `WIDER` with the
width it needs** — so a layout change that pushes one over is a diff to this
file, not a silent regression. The refusal names that width, and the width it
names is enough: that is checked too.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest

from drawspec import render_text
from drawspec.cli import main
from drawspec.errors import DrawspecError, FitError
from drawspec.examples import EXAMPLES
from drawspec.filetree import rows, text
from drawspec.kinds import TEXT_KINDS
from drawspec.kinds.graphtext import GRAPH_TEXT_KINDS
from drawspec.schema import Document, load_document, parse_document
from drawspec.textgrid import cells, plain

REFERENCE: Final = Path(__file__).resolve().parent.parent / "docs" / "reference"

#: The kinds phase 1 gave a text form. The graph kinds of phase 2 are gated by
#: `tests/test_text_graph.py`, which holds them to these same invariants.
PHASE_ONE: Final = tuple(kind for kind in TEXT_KINDS if kind not in GRAPH_TEXT_KINDS)
GOLDEN: Final = Path(__file__).resolve().parent / "golden" / "text"

#: Set to regenerate the golden files after a change has been looked at by eye.
UPDATE: Final = bool(os.environ.get("DRAWSPEC_UPDATE_GOLDEN"))

#: Reference documents that do not fit 80 columns, and the width each needs.
#: Three sequences, and a board whose longest word is wider than a fifth of
#: the line less the slice names. Each refuses at 80 rather than wrapping a word or running over.
WIDER: Final = {
    "sequence-async-export": 83,
    "sequence-dns": 93,
    "sequence-drain": 85,
    "board-onboarding": 88,
}

#: Reference documents a text form refuses by design: a meter drawn as anything
#: but `bar` says something — an angle, a band's tone — a row of cells cannot.
NO_TEXT: Final = ("meter-appeal", "meter-library", "meter-ward")

#: One reference document per kind, held as a golden file in each charset.
GOLDENS: Final = {
    "files": "files-project",
    "tree": "tree-compartments",
    "sequence": "sequence-upload",
    "gantt": "gantt-semester",
    "timeline": "timeline-disaster",
    "board": "board-story-map",
    "stack": "stack-decisions",
    "rag": "rag-refit",
    "meter": "meter-migration",
}

CHARSETS: Final = ("unicode", "ascii")


def _references() -> Iterator[tuple[str, Path]]:
    for path in sorted(REFERENCE.glob("*.json")):
        kind = json.loads(path.read_text(encoding="utf-8"))["kind"]
        if kind in PHASE_ONE and path.stem not in NO_TEXT:
            yield path.stem, path


#: Every document the gates run over: each kind's minimal example, and every
#: reference document of a kind with a text form.
FIXTURES: Final = {
    **{f"example-{kind}": parse_document(EXAMPLES[kind]) for kind in PHASE_ONE},
    **{name: load_document(path) for name, path in _references()},
}


def _width(name: str) -> int:
    return WIDER.get(name, 80)


def _drawn(name: str, charset: str) -> str:
    return render_text(FIXTURES[name], width=_width(name), charset=charset)


def _labels(document: Document) -> list[str]:
    """Every piece of text the author wrote that the drawing must say, one line each."""
    found: list[str] = []
    if document.kind == "tree":
        found += [node.label for node in document.nodes]
        found += [edge.label for edge in document.edges]
        found += [klass.text for klass in document.classes]
    elif document.kind == "sequence":
        found += [participant.text for participant in document.participants]
        found += [message.text for message in document.messages]
        found += [message.note for message in document.messages]
        found += [group.text for group in document.groups]
        for fragment in document.fragments:
            found += [fragment.text, *(branch.text for branch in fragment.branches)]
    elif document.kind == "gantt":
        found += [task.label for task in document.tasks]
        found += [group.text for group in document.groups]
        found += [mark.text for mark in document.marks]
        found += [document.axes[0].label, *document.axes[0].categories]
    elif document.kind == "timeline":
        found += [item.text for item in document.items]
        found += [item.note for item in document.items]
        found += [span.text for span in document.spans]
    elif document.kind == "board":
        found += [column.text for column in document.board_columns]
        found += [card.label for card in document.cards] + [card.note for card in document.cards]
        found += [item.text for item in document.slices]
    elif document.kind == "stack":
        found += [item.text for item in document.items]
    elif document.kind == "rag":
        found += [row.text for row in document.rag_rows] + [row.note for row in document.rag_rows]
    elif document.kind == "meter":
        found += [meter.text for meter in document.meters]
    found.append(document.caption)
    return [line for label in found for line in plain(label).split("\n") if line.strip()]


#: The kinds whose SVG wraps a label, and whose text form may therefore break
#: one at spaces. Everywhere else a label must appear on one line, whole.
WRAPPING: Final = ("sequence", "timeline", "board", "stack", "rag")


# ---------------------------------------------------------------------------
# The invariants, over every fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_line_is_wider_than_the_width_in_terminal_cells(name: str, charset: str) -> None:
    drawn = _drawn(name, charset)
    overflow = [line for line in drawn.splitlines() if cells(line) > _width(name)]
    assert not overflow, overflow


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_label_is_said_verbatim(name: str) -> None:
    """Nothing truncated: a label whole on a line, or — where the SVG wraps — every word."""
    document = FIXTURES[name]
    drawn = _drawn(name, "unicode")
    for label in _labels(document):
        if document.kind in WRAPPING or document.kind == "files":
            missing = [word for word in label.split() if word not in drawn]
            assert not missing, (label, missing)
        else:
            assert label in drawn, label


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_an_ascii_drawing_is_bytes_below_128(name: str) -> None:
    assert all(byte < 128 for byte in _drawn(name, "ascii").encode("utf-8"))


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_trailing_whitespace_and_one_final_newline(name: str, charset: str) -> None:
    drawn = _drawn(name, charset)
    assert drawn.endswith("\n") and not drawn.endswith("\n\n")
    assert all(line == line.rstrip() for line in drawn.split("\n"))
    assert drawn.strip("\n"), "an empty drawing"


@pytest.mark.parametrize("name", sorted(WIDER))
def test_a_reference_document_wider_than_80_refuses_naming_the_width_it_needs(name: str) -> None:
    with pytest.raises(FitError, match=rf"--width {WIDER[name]} or more"):
        render_text(FIXTURES[name], width=80)


@pytest.mark.parametrize("width", [20, 40, 60])
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_the_width_a_refusal_names_is_enough(name: str, width: int) -> None:
    """A refusal is located and actionable: `--width N` from its message draws."""
    document = FIXTURES[name]
    try:
        render_text(document, width=width)
    except FitError as error:
        message = str(error)
        assert message.startswith("/"), message
        needed = re.search(r"--width (\d+) or more", message)
        assert needed, message
        assert int(needed.group(1)) > width, message
        render_text(document, width=int(needed.group(1)))


def test_a_wide_character_takes_two_cells() -> None:
    """`漢字` is four columns in a terminal, and a box round it is measured that way."""
    assert cells("漢字") == 4
    assert cells("é") == 1
    document = parse_document({"version": 1, "kind": "stack", "items": [{"text": "漢字のラベル"}]})
    drawn = render_text(document, width=16)
    assert max(cells(line) for line in drawn.splitlines()) == 16
    assert unicodedata.east_asian_width("漢") == "W"
    with pytest.raises(FitError, match="--width 16 or more"):
        render_text(document, width=15)


def test_an_ascii_drawing_spells_common_punctuation_and_refuses_the_rest() -> None:
    arrow = parse_document(
        {"version": 1, "kind": "stack", "items": [{"text": "paper → file — café"}]}
    )
    assert "paper -> file -- cafe" in render_text(arrow, charset="ascii")
    kanji = parse_document({"version": 1, "kind": "stack", "items": [{"text": "漢字"}]})
    with pytest.raises(DrawspecError, match=r"^/items/0/text: .*--charset unicode"):
        render_text(kanji, charset="ascii")


# ---------------------------------------------------------------------------
# Roles: two documents differing only in a role draw differently
# ---------------------------------------------------------------------------


def _tree(role: str = "step", edge: str = "flow", status: str = "") -> dict[str, Any]:
    child: dict[str, Any] = {"id": "b", "text": "Child", "role": role}
    link: dict[str, Any] = {"from": "a", "to": "b", "role": edge}
    if status:
        child["status"] = status
        if status != "changed":
            link["status"] = status
    return {
        "version": 1,
        "kind": "tree",
        "nodes": [{"id": "a", "text": "Root"}, child, {"id": "c", "text": "Other"}],
        "edges": [link, {"from": "a", "to": "c"}],
    }


def _sequence(message: str = "flow", participant: str = "step") -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "sequence",
        "participants": [
            {"id": "a", "text": "Client", "role": participant},
            {"id": "b", "text": "Server"},
        ],
        "messages": [{"from": "a", "to": "b", "text": "ask", "role": message}],
    }


def _gantt(role: str = "step", milestone: bool = False) -> dict[str, Any]:
    task: dict[str, Any] = {"id": "t", "text": "Task", "role": role}
    task.update({"at": 2} if milestone else {"start": 0, "end": 4})
    return {
        "version": 1,
        "kind": "gantt",
        "axis": {"label": "Week"},
        "tasks": [task, {"id": "u", "text": "Other", "start": 1, "end": 3}],
    }


def _board(card: str = "step", column: str = "step") -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "board",
        "columns": [{"id": "a", "text": "Doing", "role": column}, {"id": "b", "text": "Done"}],
        "cards": [{"text": "A card", "column": "a", "role": card}],
    }


def _stack(role: str = "step") -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "stack",
        "items": [{"text": "Top", "role": role}, {"text": "Bottom"}],
    }


def _meter(role: str = "step") -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "meter",
        "meters": [{"text": "Done", "amount": 3, "max": 10, "role": role}],
    }


def _rag(rating: str = "red", trend: str = "same") -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "rag",
        "rows": [{"text": "Work", "rag": rating, "trend": trend}],
    }


#: Pairs of documents differing in one role, by the role table of the proposal.
ROLE_PAIRS: Final = {
    "tree emphasis": (_tree(), _tree("emphasis")),
    "tree terminal": (_tree(), _tree("terminal")),
    "tree start": (_tree("terminal"), _tree("start")),
    "tree note": (_tree(), _tree("note")),
    "tree strong edge": (_tree(), _tree(edge="strong")),
    "tree weak edge": (_tree(), _tree(edge="weak")),
    "tree added": (_tree(status="added"), _tree(status="removed")),
    "tree changed": (_tree(status="changed"), _tree(status="added")),
    "sequence strong": (_sequence(), _sequence("strong")),
    "sequence weak": (_sequence(), _sequence("weak")),
    "sequence async": (_sequence(), _sequence("async")),
    "sequence async reply": (_sequence("weak"), _sequence("async")),
    "sequence emphasis": (_sequence(), _sequence(participant="emphasis")),
    "sequence actor": (_sequence(), _sequence(participant="actor")),
    "sequence note": (_sequence(), _sequence(participant="note")),
    "gantt strong": (_gantt(), _gantt("strong")),
    "gantt emphasis": (_gantt("strong"), _gantt("emphasis")),
    "gantt note": (_gantt(), _gantt("note")),
    "gantt milestone": (_gantt(milestone=True), _gantt("emphasis", milestone=True)),
    "board emphasis card": (_board(), _board("emphasis")),
    "board note card": (_board(), _board("note")),
    "board emphasis column": (_board(), _board(column="emphasis")),
    "stack emphasis": (_stack(), _stack("emphasis")),
    "stack terminal": (_stack(), _stack("terminal")),
    "meter emphasis": (_meter(), _meter("emphasis")),
    "rag rating": (_rag(), _rag("amber")),
    "rag trend": (_rag(), _rag(trend="worse")),
}


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("pair", sorted(ROLE_PAIRS))
def test_two_roles_never_draw_alike(pair: str, charset: str) -> None:
    first, second = (parse_document(document) for document in ROLE_PAIRS[pair])
    assert render_text(first, charset=charset) != render_text(second, charset=charset)


def test_the_role_table_glyphs() -> None:
    """The proposal's table, spot-checked: heavy, rounded, double, dashed; arrows; status."""
    assert "┏" in render_text(parse_document(_tree("emphasis")))
    assert "╭" in render_text(parse_document(_tree("terminal")))
    assert "╔" in render_text(parse_document(_tree("start")))
    assert "┆" in render_text(parse_document(_tree("note")))
    assert "#=" in render_text(parse_document(_tree("emphasis")), charset="ascii")
    assert "▶" in render_text(parse_document(_sequence()))
    assert "━▶" in render_text(parse_document(_sequence("strong")))
    assert "◀" not in render_text(parse_document(_sequence("weak")))
    assert "┄▷" in render_text(parse_document(_sequence("weak")))
    assert "-->" in render_text(parse_document(_sequence()), charset="ascii")
    assert "==>" in render_text(parse_document(_sequence("strong")), charset="ascii")
    assert "..>>" in render_text(parse_document(_sequence("weak")), charset="ascii")
    assert render_text(parse_document(_tree(status="added"))).count("\n+ ") == 1


# ---------------------------------------------------------------------------
# Golden files: one per kind per charset, read by eye once, then held
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("kind", sorted(GOLDENS))
def test_golden(kind: str, charset: str) -> None:
    name = GOLDENS[kind]
    drawn = _drawn(name, charset)
    path = GOLDEN / f"{name}.{charset}.txt"
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(drawn, encoding="utf-8")
    assert path.is_file(), f"{path} is missing: run with DRAWSPEC_UPDATE_GOLDEN=1 and read it"
    assert drawn == path.read_text(encoding="utf-8")


def test_every_phase_one_kind_has_a_golden() -> None:
    assert sorted(GOLDENS) == sorted(PHASE_ONE)


# ---------------------------------------------------------------------------
# Refusals, `files`, and the command line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["pie", "venn", "chart", "sankey", "mindmap"])
def test_a_kind_without_a_text_form_refuses_naming_the_kinds_that_have_one(kind: str) -> None:
    with pytest.raises(DrawspecError) as refused:
        render_text(parse_document(EXAMPLES[kind]))
    message = str(refused.value)
    assert f"a {kind!r} document has no text form" in message
    for named in TEXT_KINDS:
        assert f"`{named}`" in message


def test_only_a_bar_meter_has_a_text_form() -> None:
    dial = parse_document({**EXAMPLES["meter"], "style": "dial"})
    with pytest.raises(DrawspecError, match=r"^/style: .*only `bar`"):
        render_text(dial)


def test_a_tree_with_a_cross_link_is_routed_rather_than_drawn_twice() -> None:
    """Guides hang each node once; a second parent makes it a graph, drawn as phase 2 draws one."""
    tree = _tree()
    tree["edges"].append({"from": "c", "to": "b"})
    drawn = render_text(parse_document(tree))
    assert drawn.count("Child") == 1
    assert "├─" not in drawn and "▼" in drawn


@pytest.mark.parametrize("name", [name for name in FIXTURES if FIXTURES[name].kind == "files"])
def test_files_text_is_unchanged(name: str) -> None:
    """`files` draws exactly what it drew before every other kind had a text form."""
    document = FIXTURES[name]
    charset = "ascii" if document.style == "ascii" else "unicode"
    assert render_text(document) == text(
        rows(document.entries, document.root, document.order), charset
    )
    ascii_style = parse_document({**EXAMPLES["files"], "style": "ascii"})
    assert render_text(ascii_style) == render_text(ascii_style, charset="ascii")
    assert render_text(ascii_style).isascii()


def test_the_cli_takes_width_and_charset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "stack.json"
    source.write_text(json.dumps(_stack()), encoding="utf-8")
    assert (
        main(["render", str(source), "--format", "text", "--charset", "ascii", "--width", "30"])
        == 0
    )
    out = capsys.readouterr().out
    assert out.isascii() and "Top" in out and out.endswith("+\n")
    target = tmp_path / "stack.txt"
    assert main(["render", str(source), "-o", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == render_text(parse_document(_stack())).rstrip("\n")


def test_the_cli_refuses_a_drawing_too_wide_with_its_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "stack.json"
    source.write_text(json.dumps(_stack()), encoding="utf-8")
    assert main(["render", str(source), "--format", "text", "--width", "5"]) == 1
    assert capsys.readouterr().err.startswith("/items/")


@pytest.mark.parametrize(
    "arguments",
    [
        ["--charset", "ascii"],
        ["--format", "text", "--width", "79.5"],
        ["--format", "text", "--charset", "latin1"],
    ],
)
def test_the_cli_refuses_a_text_option_it_cannot_honour(
    tmp_path: Path, arguments: list[str]
) -> None:
    source = tmp_path / "stack.json"
    source.write_text(json.dumps(_stack()), encoding="utf-8")
    assert main(["render", str(source), *arguments]) == 2


def test_files_text_is_not_held_to_the_width() -> None:
    """A `files` tree wider than `width` prints as it always did, for now."""
    document = parse_document(
        {"version": 1, "kind": "files", "entries": [{"path": "a/" + "b" * 120 + ".txt"}]}
    )
    drawn = render_text(document, width=40)
    assert max(len(line) for line in drawn.splitlines()) > 40
