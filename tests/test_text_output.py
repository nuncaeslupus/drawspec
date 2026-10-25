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
from itertools import pairwise
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
from drawspec.schema import Document, RailroadItem, load_document, parse_document
from drawspec.textgrid import cells, default_width, plain

REFERENCE: Final = Path(__file__).resolve().parent.parent / "docs" / "reference"

#: The kinds phase 1 gave a text form. The graph kinds of phase 2 are gated by
#: `tests/test_text_graph.py`, which holds them to these same invariants.
PHASE_ONE: Final = tuple(kind for kind in TEXT_KINDS if kind not in GRAPH_TEXT_KINDS)
GOLDEN: Final = Path(__file__).resolve().parent / "golden" / "text"

#: Set to regenerate the golden files after a change has been looked at by eye.
UPDATE: Final = bool(os.environ.get("DRAWSPEC_UPDATE_GOLDEN"))

#: Reference documents that do not fit 80 columns, and the width each needs.
#: Three sequences, a board whose longest word is wider than a fifth of the
#: line less the slice names, an SPI read whose twenty steps take four columns
#: each, two networks, and two brackets: a sixteen-team draw's five columns of
#: names and scores, and a two-sided draw's nine. Each refuses at 80 rather than
#: wrapping a word or running over.
WIDER: Final = {
    "sequence-async-export": 83,
    "sequence-dns": 93,
    "sequence-drain": 85,
    "board-onboarding": 88,
    "tree-bracket-cup": 92,
    "tree-bracket-quiz": 141,
    # A network's bus names stand left of their buses, and every column holds a box.
    "network-office": 120,
    "network-three-tier": 136,
    "timing-spi": 94,
}


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
    "network": "network-nwdiag",
    "timing": "timing-session",
    "gitgraph": "gitgraph-gitflow",
    "railroad": "railroad-json-number",
    "pert": "pert-textbook",
}

#: Golden files beyond one per kind: a second style of a kind, held the same way.
MORE_GOLDENS: Final = ("meter-appeal", "meter-library", "meter-ward", "railroad-sql-select")

CHARSETS: Final = ("unicode", "ascii")


def _references() -> Iterator[tuple[str, Path]]:
    for path in sorted(REFERENCE.glob("*.json")):
        kind = json.loads(path.read_text(encoding="utf-8"))["kind"]
        if kind in PHASE_ONE:
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
        found += [band.text for meter in document.meters for band in meter.bands]
    elif document.kind == "network":
        found += [network.text for network in document.networks]
        found += [network.address for network in document.networks]
        found += [host.text for host in document.hosts]
        found += [address for host in document.hosts for address in host.addresses]
        found += [group.text for group in document.host_groups]
    elif document.kind == "timing":
        for signal in document.timing_signals:
            found += [signal.text, signal.group, *signal.states]
            if signal.lane == "bus":
                found += [value for value in signal.values if value not in (".", "x", "z")]
        found += list(document.timing_ticks)
        found += [marker.text for marker in document.timing_markers]
        found += [interval.text for interval in document.timing_intervals]
    elif document.kind == "railroad":
        found += [rule.name for rule in document.railroad_rules]
        found += [word for rule in document.railroad_rules for word in _railroad_words(rule.expr)]
    elif document.kind == "pert":
        found += [activity.text for activity in document.pert_activities]
        found += [document.pert_start, document.pert_finish]
    found.append(document.caption)
    return [line for label in found for line in plain(label).split("\n") if line.strip()]


def _railroad_words(item: RailroadItem) -> list[str]:
    """Every box's and comment's words on a railroad track."""
    found = [item.text] if item.text else []
    for child in (*item.items, *([item.separator] if item.separator else [])):
        found += _railroad_words(child)
    return found


#: The kinds whose SVG wraps a label, and whose text form may therefore break
#: one at spaces. Everywhere else a label must appear on one line, whole.
WRAPPING: Final = ("sequence", "timeline", "board", "stack", "rag", "network", "pert")


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


def _gantt(role: str = "step", milestone: bool = False, edge: str = "") -> dict[str, Any]:
    task: dict[str, Any] = {"id": "t", "text": "Task", "role": role}
    task.update({"at": 2} if milestone else {"start": 0, "end": 4})
    document: dict[str, Any] = {
        "version": 1,
        "kind": "gantt",
        "axis": {"label": "Week"},
        "tasks": [task, {"id": "u", "text": "Other", "start": 1, "end": 3}],
    }
    if edge:
        document["tasks"][1].update({"start": 6, "end": 8})
        document["edges"] = [{"from": "t", "to": "u", "role": edge}]
    return document


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


def _meter(role: str = "step", style: str = "bar") -> dict[str, Any]:
    meter: dict[str, Any] = {"text": "Done", "amount": 3, "max": 10, "role": role}
    if style == "bullet":
        meter["bands"] = [{"text": "Low", "to": 5}, {"text": "High", "to": 10}]
    return {"version": 1, "kind": "meter", "style": style, "meters": [meter]}


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
    "thermometer emphasis": (_meter(style="thermometer"), _meter("emphasis", "thermometer")),
    "dial emphasis": (_meter(style="dial"), _meter("emphasis", "dial")),
    "bullet emphasis": (_meter(style="bullet"), _meter("emphasis", "bullet")),
    "gantt weak dependency": (_gantt(edge="flow"), _gantt(edge="weak")),
    "gantt strong dependency": (_gantt(edge="flow"), _gantt(edge="strong")),
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
@pytest.mark.parametrize("name", sorted([*GOLDENS.values(), *MORE_GOLDENS]))
def test_golden(name: str, charset: str) -> None:
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


@pytest.mark.parametrize(("kind", "expected"), [("sequence", 100), ("lanes", 100), ("tree", 80)])
def test_default_width_is_per_kind(kind: str, expected: int) -> None:
    """Sequences and lanes default to 100 columns, every other kind to 80."""
    assert default_width(kind) == expected


def test_the_callers_width_wins_over_the_default() -> None:
    """A width the caller names is the width the drawing is held to."""
    document = load_document(REFERENCE / "sequence-dns.json")
    render_text(document)
    with pytest.raises(FitError):
        render_text(document, width=80)


def test_a_sequence_wraps_only_the_labels_the_width_needs() -> None:
    """At 100 columns a label with room keeps one line; the drawing still fits."""
    drawn = render_text(load_document(REFERENCE / "sequence-dns.json"), width=100)
    assert "where is wiki.example.org?" in drawn
    assert "ask ns1.example.org" in drawn
    assert max(cells(line) for line in drawn.splitlines()) <= 100


# ---------------------------------------------------------------------------
# A thermometer: a tube down the page, filled from its bulb
# ---------------------------------------------------------------------------


def _thermometer(amount: float, target: float | None = None) -> Document:
    meter: dict[str, Any] = {"text": "Appeal", "amount": amount, "max": 100, "unit": "%"}
    if target is not None:
        meter["target"] = target
    return parse_document(
        {"version": 1, "kind": "meter", "style": "thermometer", "meters": [meter]}
    )


def _tube_rows(drawn: str, charset: str = "unicode") -> list[str]:
    """The tube's rows, top to bottom: the lines between its cap and its bulb."""
    lines = drawn.splitlines()
    cap = "╭───╮" if charset == "unicode" else ".---."
    top = next(number for number, line in enumerate(lines) if cap in line)
    bottom = next(
        number for number, line in enumerate(lines) if number > top and ("╯" in line or "'" in line)
    )
    return lines[top + 1 : bottom - 2]


def test_a_thermometer_is_filled_from_its_bulb_to_its_amount() -> None:
    """The fill runs up from the bulb to the row of its amount's own tick; the bulb is filled."""
    rows_ = _tube_rows(render_text(_thermometer(50)))
    filled = ["███" in row for row in rows_]
    assert filled == sorted(filled), "the fill is not one run up from the bulb"
    top = filled.index(True)
    assert rows_[top].lstrip().startswith("50"), "the fill stops short of, or past, its tick"
    assert "│█████│" in render_text(_thermometer(50))
    assert "███" not in "".join(_tube_rows(render_text(_thermometer(0))))


def test_a_thermometer_says_its_scale_target_and_readout() -> None:
    drawn = render_text(_thermometer(30, target=80))
    assert "100%" in drawn.splitlines()[1], "the goal is not labelled at the top of the tube"
    assert "0%" in drawn
    assert "┿━" in drawn, "no target across the tube"
    assert "30 %" in drawn or "30%" in drawn
    assert "target 80%" in drawn
    target_row = next(number for number, row in enumerate(_tube_rows(drawn)) if "┿" in row)
    assert target_row == 2, "80 of 100 is not a fifth of the way down a ten-row tube"


def test_an_ascii_thermometer() -> None:
    drawn = render_text(_thermometer(50, target=80), charset="ascii")
    assert drawn.isascii()
    assert "|###|" in drawn and "|===|==" in drawn


def test_thermometers_stand_side_by_side() -> None:
    document = parse_document(
        {
            "version": 1,
            "kind": "meter",
            "style": "thermometer",
            "meters": [
                {"text": "North", "amount": 20, "max": 100},
                {"text": "South", "amount": 70, "max": 100},
            ],
        }
    )
    drawn = render_text(document)
    assert drawn.splitlines()[0].count("╭───╮") == 2
    names = next(line for line in drawn.splitlines() if "North" in line)
    assert "South" in names
    with pytest.raises(FitError, match=r"^/meters/"):
        render_text(document, width=20)


# ---------------------------------------------------------------------------
# Gantt dependencies: a line from the end of one bar to the start of the next
# ---------------------------------------------------------------------------


def _plan(*tasks: tuple[str, float, float], edges: list[tuple[str, str]]) -> Document:
    return parse_document(
        {
            "version": 1,
            "kind": "gantt",
            "axis": {"label": "Week"},
            "tasks": [
                {"id": name, "text": name.title(), "start": start, "end": end}
                if end > start
                else {"id": name, "text": name.title(), "at": start}
                for name, start, end in tasks
            ],
            "edges": [{"from": source, "to": target} for source, target in edges],
        }
    )


def _bar_of(line: str) -> tuple[int, int]:
    """The first and one past the last cell of a row's bar."""
    found = [column for column, character in enumerate(line) if character in "░▒▓█◆◇◈"]
    return found[0], found[-1] + 1


def test_a_dependency_runs_from_a_bars_end_down_and_into_the_next_bar() -> None:
    drawn = render_text(_plan(("design", 0, 2), ("build", 5, 8), edges=[("design", "build")]))
    lines = drawn.splitlines()
    design = next(line for line in lines if line.startswith("Design"))
    build = next(line for line in lines if line.startswith("Build"))
    _, end = _bar_of(design)
    start, _ = _bar_of(build)
    assert design[end] == "┐", design
    assert build[end] == "└" and build[start - 1] == "▶", build
    assert set(build[end + 1 : start - 1]) <= {"─"}
    assert "after" not in drawn


def test_a_dependency_with_no_gap_arrives_from_above() -> None:
    drawn = render_text(
        _plan(("design", 0, 2), ("other", 0, 1), ("build", 2, 5), edges=[("design", "build")])
    )
    lines = drawn.splitlines()
    build_row = next(n for n, line in enumerate(lines) if line.startswith("Build"))
    start, _ = _bar_of(lines[build_row])
    assert lines[build_row - 1][start] == "▼"
    assert lines[0][start] == "┐"


def test_a_dependency_never_overprints_a_bar() -> None:
    plain_plan = _plan(("design", 0, 4), ("build", 5, 8), ("test", 1, 6), edges=[])
    linked = _plan(("design", 0, 4), ("build", 5, 8), ("test", 1, 6), edges=[("design", "build")])
    bars = "▒◆"
    assert sum(render_text(plain_plan).count(glyph) for glyph in bars) == sum(
        render_text(linked).count(glyph) for glyph in bars
    )


@pytest.mark.parametrize(
    "tasks",
    [
        # The dependent sits above its prerequisite.
        (("build", 5, 8), ("design", 0, 2)),
        # A milestone right over the start of the next row: no cell between.
        (("design", 3, 3), ("build", 3, 8)),
        # A bar stands in the way down.
        (("design", 0, 2), ("wall", 1, 6), ("build", 5, 8)),
    ],
)
def test_a_dependency_that_cannot_be_routed_is_listed_under_the_chart(
    tasks: tuple[tuple[str, float, float], ...],
) -> None:
    drawn = render_text(_plan(*tasks, edges=[("design", "build")]))
    assert drawn.splitlines()[-1] == "Build after Design"
    assert "▶" not in drawn and "▼" not in drawn
    ascii_drawn = render_text(_plan(*tasks, edges=[("design", "build")]), charset="ascii")
    assert ascii_drawn.splitlines()[-1] == "Build after Design"


def test_a_milestone_drops_straight_onto_what_follows_it() -> None:
    drawn = render_text(
        _plan(("design", 3, 3), ("other", 0, 1), ("build", 3, 8), edges=[("design", "build")])
    )
    lines = drawn.splitlines()
    column = lines[0].index("◆")
    assert lines[1][column] == "▼" and lines[2][column] == "▒"


def test_the_semester_draws_its_dependencies_within_80_columns() -> None:
    drawn = render_text(FIXTURES["gantt-semester"], width=80)
    assert max(cells(line) for line in drawn.splitlines()) <= 80
    assert drawn.count("▼") == 3
    # Proposal due → Ethics review would cross the spring term's bracket: listed instead.
    assert drawn.splitlines()[-1] == "Ethics review after Proposal due"


# ---------------------------------------------------------------------------
# A timeline spaced by `at`
# ---------------------------------------------------------------------------


def _timeline(*ats: float | None) -> Document:
    items: list[dict[str, Any]] = []
    for number, at in enumerate(ats):
        item: dict[str, Any] = {"text": f"Entry {number}"}
        if at is not None:
            item["at"] = at
        items.append(item)
    return parse_document({"version": 1, "kind": "timeline", "items": items})


def _entry_rows(drawn: str) -> list[int]:
    return [
        number for number, line in enumerate(drawn.splitlines()) if "●" in line or " o " in line
    ]


def test_a_timeline_with_every_at_is_spaced_in_proportion() -> None:
    """The closest pair one blank row apart; the rest in proportion to their interval."""
    rows_ = _entry_rows(render_text(_timeline(0, 1, 4, 6)))
    assert [later - earlier for earlier, later in pairwise(rows_)] == [2, 6, 4]


def test_a_timeline_missing_an_at_is_evenly_spaced() -> None:
    rows_ = _entry_rows(render_text(_timeline(0, None, 9)))
    assert [later - earlier for earlier, later in pairwise(rows_)] == [2, 2]


def test_a_timeline_out_of_order_is_evenly_spaced() -> None:
    rows_ = _entry_rows(render_text(_timeline(0, 9, 3)))
    assert [later - earlier for earlier, later in pairwise(rows_)] == [2, 2]


def test_a_long_gap_is_compressed_and_marked() -> None:
    drawn = render_text(_timeline(0, 1, 1000))
    rows_ = _entry_rows(drawn)
    gaps = [later - earlier for earlier, later in pairwise(rows_)]
    assert gaps[0] == 2 and 2 < gaps[1] <= 10, gaps
    lines = drawn.splitlines()
    assert "┆" in "".join(lines[rows_[1] + 1 : rows_[2]])
    assert "┆" not in "".join(lines[rows_[0] : rows_[1]])
    assert ":" in render_text(_timeline(0, 1, 1000), charset="ascii")


def test_an_ascii_dependency_line_never_uses_a_bars_glyph() -> None:
    """In ASCII a dependency's horizontal run cannot be mistaken for part of a bar."""
    from drawspec.kinds.gantt import TEXT_DEPENDENCY, TEXT_FILLS, TEXT_UNDONE

    bar_glyphs = {*TEXT_FILLS["ascii"].values(), TEXT_UNDONE["ascii"]}
    for across, *_ in TEXT_DEPENDENCY["ascii"].values():
        assert across not in bar_glyphs


# ---------------------------------------------------------------------------
# A bullet: a bar on its bands, each band a shade with its word over it
# ---------------------------------------------------------------------------


def _bullet(amount: float, target: float | None = None, role: str = "step") -> Document:
    meter: dict[str, Any] = {
        "text": "Visits",
        "amount": amount,
        "max": 100,
        "role": role,
        "bands": [
            {"text": "Poor", "to": 50},
            {"text": "Fair", "to": 80},
            {"text": "Good", "to": 100},
        ],
    }
    if target is not None:
        meter["target"] = target
    return parse_document({"version": 1, "kind": "meter", "style": "bullet", "meters": [meter]})


def _track(drawn: str, row: int, opening: str = "[") -> str:
    """The inside of the bullet's track on its `row`th line: 0 top, 1 measure, 2 bottom."""
    lines = [line for line in drawn.splitlines() if opening in line]
    line = lines[row]
    return line[line.index(opening) + 1 : line.rindex({"[": "]", "┃": "┃", "|": "|"}[opening])]


def test_a_bullets_bands_are_shades_lightest_first_with_their_words_over_them() -> None:
    drawn = render_text(_bullet(0))
    top = _track(drawn, 0)
    assert len(top) == 40
    assert top == "░" * 20 + "▒" * 12 + "▓" * 8
    words = drawn.splitlines()[0]
    start = drawn.splitlines()[1].index("[") + 1
    assert words.index("Poor") - start in range(20 - 4)
    assert words.index("Fair") - start in range(20, 32 - 4)
    assert words.index("Good") - start in range(32, 40 - 4 + 1)


def test_a_bullets_measure_is_a_thin_bar_over_its_bands_to_the_amount() -> None:
    drawn = render_text(_bullet(60, target=90))
    middle, bottom = _track(drawn, 1), _track(drawn, 2)
    assert middle.startswith("━" * 24) and "━" not in middle[24:]
    assert middle[24:] == bottom[24:]
    assert middle[36] == bottom[36] == _track(drawn, 0)[36] == "│"
    assert "60" in drawn and "Fair" in drawn and "target 90" in drawn


def test_a_bullet_is_ticked_from_zero_to_its_end() -> None:
    drawn = render_text(_bullet(60))
    ticks = next(line for line in drawn.splitlines() if line.strip().startswith("0 "))
    assert ticks.rstrip().endswith("100")
    assert ticks.rindex("100") + 3 == drawn.splitlines()[1].rindex("]")


def test_an_ascii_bullet() -> None:
    drawn = render_text(_bullet(60, target=90), charset="ascii")
    assert drawn.isascii()
    assert _track(drawn, 0).startswith("." * 20 + ":" * 12)
    assert _track(drawn, 1).startswith("=" * 24)
    assert _track(render_text(_bullet(60, role="emphasis"), charset="ascii"), 1, "|")


def test_a_bullet_too_narrow_for_its_band_words_refuses_naming_the_width() -> None:
    document = _bullet(60)
    with pytest.raises(FitError, match=r"^/meters/0/") as refused:
        render_text(document, width=24)
    needed = int(re.search(r"--width (\d+)", str(refused.value)).group(1))  # type: ignore[union-attr]
    render_text(document, width=needed)


# ---------------------------------------------------------------------------
# A dial: a half-circle of cells, a needle from its hub
# ---------------------------------------------------------------------------


def _dial(amount: float, target: float | None = None, bands: bool = False) -> Document:
    meter: dict[str, Any] = {"text": "Load", "amount": amount, "min": 20, "max": 120, "unit": "%"}
    if target is not None:
        meter["target"] = target
    if bands:
        meter["bands"] = [{"text": "Low", "to": 60}, {"text": "High", "to": 120}]
    return parse_document({"version": 1, "kind": "meter", "style": "dial", "meters": [meter]})


#: A needle rising to the right.
RISING: Final = "\N{BOX DRAWINGS LIGHT DIAGONAL UPPER RIGHT TO LOWER LEFT}"


@pytest.mark.parametrize(
    ("amount", "needle"), [(20, "─●"), (120, "●─"), (70, "│"), (45, "╲"), (95, RISING)]
)
def test_a_dials_needle_points_at_its_amount(amount: float, needle: str) -> None:
    drawn = render_text(_dial(amount))
    hub = next(index for index, line in enumerate(drawn.splitlines()) if "●" in line)
    lines = drawn.splitlines()
    if needle in ("─●", "●─"):
        assert needle in lines[hub]
    else:
        column = lines[hub].index("●")
        above = lines[hub - 1]
        assert needle in above[column - 2 : column + 3]


def test_a_dial_is_filled_to_its_amount_and_labelled_at_its_ends() -> None:
    drawn = render_text(_dial(70))
    lines = drawn.splitlines()
    hub = next(index for index, line in enumerate(lines) if "●" in line)
    assert lines[hub].lstrip().startswith("█") and lines[hub].rstrip().endswith("░")
    ends = lines[hub + 1]
    assert ends.lstrip().startswith("20%") and ends.rstrip().endswith("120%")
    assert lines[hub + 1].index("20%") == min(
        line.index(line.lstrip()[0]) for line in lines[: hub + 1]
    )


def test_a_dials_target_is_a_tick_on_its_arc_and_its_bands_a_key() -> None:
    drawn = render_text(_dial(70, target=110, bands=True))
    arc = drawn.split("●")[0]
    assert arc.count("◆") >= 1 and "░" in arc and "▓" in arc
    assert "░ Low" in drawn and "▓ High" in drawn
    assert "70%" in drawn and "target 110%" in drawn and "High" in drawn


def test_an_ascii_dial() -> None:
    drawn = render_text(_dial(70, target=110, bands=True), charset="ascii")
    assert drawn.isascii() and "*" in drawn and "|" in drawn and ". Low" in drawn


def test_dials_stand_three_to_a_row() -> None:
    meters = [{"text": f"Dial {n}", "amount": 5, "max": 10} for n in range(4)]
    document = parse_document({"version": 1, "kind": "meter", "style": "dial", "meters": meters})
    lines = render_text(document).splitlines()
    names = [line for line in lines if "Dial" in line]
    assert len(names) == 2 and names[0].count("Dial") == 2 and names[1].count("Dial") == 2
    with pytest.raises(FitError, match=r"^/meters/"):
        render_text(document, width=20)


def test_a_timeline_spaced_across_the_float_range_renders() -> None:
    """`at` values near the float limit still give proportional spacing, not an error."""
    document = parse_document(
        {
            "version": 1,
            "kind": "timeline",
            "items": [
                {"text": "Start", "at": -1e308},
                {"text": "Middle", "at": 0},
                {"text": "End", "at": 1e308},
            ],
        }
    )
    drawn = render_text(document)
    assert all(label in drawn for label in ("Start", "Middle", "End"))
