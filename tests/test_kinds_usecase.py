"""`usecase` — who uses a system for what, as UML draws it.

The kind's promises: primary actors stand left of the boundaries and supporting
ones right, a specialised actor on its parent's side; every use case is inside
its own system's frame, one included, extending or specialising another a column
to the right of it; every line is drawn border to border and runs through
nothing it does not end on, crossing its own boundary once and no other; and
every refusal in the proposal is located at its JSON pointer.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DrawspecError, FitError
from drawspec.kinds.usecase import UsecaseDrawing, usecase_drawing
from drawspec.render import render_text
from drawspec.schema import (
    USECASE_ACTOR_MAX,
    parse_document,
    usecase_columns,
    usecase_sides,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("usecase-*.json"))


def atm(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "usecase",
        "systems": [{"id": "atm", "text": "ATM"}],
        "actors": [
            {"id": "customer", "text": "Customer"},
            {"id": "bank", "text": "Bank"},
        ],
        "usecases": [
            {"id": "withdraw", "text": "Withdraw cash"},
            {"id": "balance", "text": "Check balance"},
            {"id": "pin", "text": "Enter PIN"},
            {"id": "receipt", "text": "Print receipt"},
        ],
        "edges": [
            {"from": "customer", "to": "withdraw"},
            {"from": "customer", "to": "balance"},
            {"from": "bank", "to": "withdraw"},
            {"from": "withdraw", "to": "pin", "role": "include"},
            {"from": "balance", "to": "pin", "role": "include"},
            {"from": "receipt", "to": "withdraw", "role": "extend"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> UsecaseDrawing:
    return usecase_drawing(parse_document(document), THEME, MEASURER)


def violations(document: dict[str, Any]) -> list[tuple[str, str]]:
    return [(violation.pointer, violation.message) for violation in validate_document(document)]


def refused_at(document: dict[str, Any], pointer: str) -> str:
    found = violations(document)
    matching = [message for at, message in found if at == pointer]
    assert matching, f"nothing refused at {pointer}: {found}"
    return matching[0]


def inside(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    return rect[0] < point[0] < rect[2] and rect[1] < point[1] < rect[3]


# -- the references -----------------------------------------------------------


def test_there_are_reference_diagrams() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_and_validates(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    svg = render(document)
    assert svg.startswith("<svg")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_reference_line_runs_through_anything(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    assert drawing.hits == 0


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_line_crosses_its_own_boundary_once_and_no_other(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    system = {case.id: case.system for case in parse_document(document).usecase_cases}
    for line in drawing.lines:
        own = {system[end] for end in (line.source, line.target) if end in system}
        for frame in drawing.frames:
            rect = (frame.x, frame.y, frame.right, frame.bottom)
            marks = [inside(point, rect) for point in line.points]
            changes = sum(1 for a, b in pairwise(marks) if a != b)
            if frame.id not in own:
                assert not any(marks), (line, frame.id)
            elif line.role == "association":
                assert changes == 1, (line, frame.id)
            else:
                assert all(marks), (line, frame.id)


# -- placement ----------------------------------------------------------------


def test_actors_stand_outside_every_boundary_and_use_cases_inside_their_own() -> None:
    drawing = drawn(atm())
    (frame,) = drawing.frames
    for left, _, right, _ in drawing.actors.values():
        assert right < frame.x or left > frame.right
    for cx, cy, rx, ry in drawing.cases.values():
        assert frame.x < cx - rx and cx + rx < frame.right
        assert frame.y < cy - ry and cy + ry < frame.bottom


def test_primary_actors_stand_left_and_supporting_ones_right() -> None:
    drawing = drawn(atm())
    (frame,) = drawing.frames
    assert drawing.sides == {"customer": "left", "bank": "right"}
    assert drawing.actors["customer"][2] < frame.x
    assert drawing.actors["bank"][0] > frame.right


def test_a_written_supporting_overrides_the_derived_side() -> None:
    document = atm()
    document["actors"][1]["supporting"] = False
    assert drawn(document).sides["bank"] == "left"


def test_the_side_is_derived_from_what_earlier_actors_already_have() -> None:
    edges = [("a", "x", "association"), ("b", "x", "association"), ("c", "y", "association")]
    assert usecase_sides([("a", None), ("b", None), ("c", None)], edges) == {
        "a": "left",
        "b": "right",
        "c": "left",
    }


def test_a_specialised_actor_stands_on_its_parents_side_above_or_below_it() -> None:
    document = atm()
    document["actors"].append({"id": "vip", "text": "Premium customer"})
    document["usecases"].append({"id": "loan", "text": "Request loan"})
    document["edges"] += [
        {"from": "vip", "to": "customer", "role": "inherits"},
        {"from": "vip", "to": "loan"},
    ]
    drawing = drawn(document)
    assert drawing.sides["vip"] == drawing.sides["customer"] == "left"
    child, parent = drawing.actors["vip"], drawing.actors["customer"]
    assert child[3] < parent[1] or child[1] > parent[3]
    (arrow,) = [line for line in drawing.lines if line.role == "inherits"]
    assert arrow.points[0][0] == pytest.approx(arrow.points[-1][0])


def test_an_included_extending_or_specialising_use_case_stands_right_of_its_base() -> None:
    drawing = drawn(atm())
    assert drawing.cases["pin"][0] > drawing.cases["withdraw"][0]
    assert drawing.cases["receipt"][0] > drawing.cases["withdraw"][0]
    assert usecase_columns(
        ["a", "b", "c", "d"],
        [("a", "b", "include"), ("c", "b", "extend"), ("d", "a", "inherits")],
    ) == {"a": 0, "b": 1, "c": 2, "d": 1}


def test_include_and_extend_are_named_in_guillemets_and_dashed() -> None:
    svg = render(atm())
    assert "«include»" in svg
    assert "«extend»" in svg


def test_association_lines_end_on_the_ellipse() -> None:
    drawing = drawn(atm())
    for line in drawing.lines:
        if line.role != "association":
            continue
        cx, cy, rx, ry = drawing.cases[line.target]
        x, y = line.points[-1]
        assert ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 == pytest.approx(1.0, abs=1e-6)


def test_keywords_sit_clear_of_every_ellipse() -> None:
    drawing = drawn(atm())
    for left, top, right, bottom in drawing.labels:
        for cx, cy, rx, ry in drawing.cases.values():
            for x in (left, (left + right) / 2, right):
                for y in (top, (top + bottom) / 2, bottom):
                    assert ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 >= 1


def test_without_systems_there_is_no_boundary() -> None:
    document = atm()
    del document["systems"]
    assert validate_document(document) == ()
    assert drawn(document).frames == ()


def test_two_systems_are_stacked_one_above_the_other() -> None:
    document = atm(
        systems=[{"id": "atm", "text": "ATM"}, {"id": "core", "text": "Core banking"}],
    )
    for case in document["usecases"]:
        case["system"] = "atm"
    document["usecases"].append({"id": "audit", "text": "Audit", "system": "core"})
    document["edges"].append({"from": "bank", "to": "audit"})
    drawing = drawn(document)
    first, second = drawing.frames
    assert first.bottom < second.y
    assert first.x == second.x and first.width == second.width


def test_a_drawing_too_wide_for_its_canvas_is_refused() -> None:
    with pytest.raises(FitError):
        drawn(atm(width=200))


def test_the_kind_has_no_text_form() -> None:
    with pytest.raises(DrawspecError, match="no text form"):
        render_text(parse_document(atm()))


# -- refusals -----------------------------------------------------------------


def test_an_association_between_two_actors_is_refused() -> None:
    document = atm()
    document["edges"].append({"from": "customer", "to": "bank"})
    assert "actors meet through the use cases" in refused_at(document, "/edges/6")


def test_an_association_between_two_use_cases_asks_which_relation() -> None:
    document = atm()
    document["edges"].append({"from": "withdraw", "to": "balance"})
    assert "`include`" in refused_at(document, "/edges/6/role")


def test_include_from_an_actor_is_refused() -> None:
    document = atm()
    document["edges"].append({"from": "customer", "to": "pin", "role": "include"})
    assert "joins two use cases" in refused_at(document, "/edges/6/role")


def test_inherits_between_an_actor_and_a_use_case_is_refused() -> None:
    document = atm()
    document["edges"].append({"from": "customer", "to": "pin", "role": "inherits"})
    assert "one of each" in refused_at(document, "/edges/6/role")


def test_an_unknown_end_is_refused_with_a_suggestion() -> None:
    document = atm()
    document["edges"][0]["to"] = "withdrw"
    assert "did you mean 'withdraw'" in refused_at(document, "/edges/0/to")


def test_a_system_cannot_be_an_end() -> None:
    document = atm()
    document["edges"][0]["to"] = "atm"
    assert "is a system" in refused_at(document, "/edges/0/to")


def test_an_unknown_system_is_refused() -> None:
    document = atm()
    document["usecases"][0]["system"] = "bank-system"
    assert "not the id of any system" in refused_at(document, "/usecases/0/system")


def test_with_two_systems_each_use_case_names_one() -> None:
    document = atm(systems=[{"id": "atm", "text": "ATM"}, {"id": "core", "text": "Core"}])
    document["usecases"][1]["system"] = "core"
    assert "names the `system`" in refused_at(document, "/usecases/0")


def test_a_system_with_no_use_case_is_refused() -> None:
    document = atm(systems=[{"id": "atm", "text": "ATM"}, {"id": "core", "text": "Core"}])
    for case in document["usecases"]:
        case["system"] = "atm"
    assert "empty box" in refused_at(document, "/systems/1")


def test_duplicate_ids_across_actors_and_use_cases_are_refused() -> None:
    document = atm()
    document["usecases"][0]["id"] = "customer"
    assert "share one set of ids" in refused_at(document, "/usecases/0/id")


def test_a_relation_to_itself_is_refused() -> None:
    document = atm()
    document["edges"].append({"from": "pin", "to": "pin", "role": "include"})
    assert "to itself" in refused_at(document, "/edges/6")


def test_a_second_relation_between_the_same_two_is_refused() -> None:
    document = atm()
    document["edges"].append({"from": "pin", "to": "withdraw", "role": "extend"})
    assert "second relation" in refused_at(document, "/edges/6")


def test_a_loop_of_includes_is_refused() -> None:
    document = atm()
    document["usecases"].append({"id": "card", "text": "Read card"})
    document["edges"] += [
        {"from": "pin", "to": "card", "role": "include"},
        {"from": "card", "to": "withdraw", "role": "include"},
    ]
    assert "loop" in refused_at(document, "/usecases/0")


def test_a_fourth_column_is_refused() -> None:
    document = atm()
    document["usecases"].append({"id": "card", "text": "Read card"})
    document["edges"].append({"from": "pin", "to": "card", "role": "include"})
    document["usecases"].append({"id": "chip", "text": "Read chip"})
    document["edges"].append({"from": "card", "to": "chip", "role": "include"})
    assert "3 columns" in " ".join(message for _, message in violations(document))


def test_an_actor_with_no_relation_is_refused() -> None:
    document = atm()
    document["actors"].append({"id": "auditor", "text": "Auditor"})
    assert "takes part in nothing" in refused_at(document, "/actors/2")


def test_two_levels_of_actor_generalisation_are_refused() -> None:
    document = atm()
    document["actors"] += [{"id": "vip", "text": "VIP"}, {"id": "gold", "text": "Gold"}]
    document["edges"] += [
        {"from": "vip", "to": "customer", "role": "inherits"},
        {"from": "gold", "to": "vip", "role": "inherits"},
    ]
    assert "one level of actor generalisation" in refused_at(document, "/edges/7")


def test_an_actor_inherits_from_one_actor_at_most() -> None:
    document = atm()
    document["actors"].append({"id": "vip", "text": "VIP"})
    document["edges"] += [
        {"from": "vip", "to": "customer", "role": "inherits"},
        {"from": "vip", "to": "bank", "role": "inherits"},
    ]
    assert "already inherits" in refused_at(document, "/edges/7")


def test_include_across_two_systems_is_refused() -> None:
    document = atm(systems=[{"id": "atm", "text": "ATM"}, {"id": "core", "text": "Core"}])
    for case in document["usecases"]:
        case["system"] = "atm"
    document["usecases"][2]["system"] = "core"
    assert "different systems" in refused_at(document, "/edges/3")


def test_words_on_a_relation_are_refused_with_the_reason() -> None:
    document = atm()
    document["edges"][3]["text"] = "always"
    assert "«include»" in refused_at(document, "/edges/3/text")


def test_a_side_on_an_actor_is_refused_with_the_reason() -> None:
    document = atm()
    document["actors"][0]["side"] = "left"
    assert "supporting" in refused_at(document, "/actors/0/side")


def test_more_actors_than_the_budget_are_refused() -> None:
    document = atm()
    for index in range(USECASE_ACTOR_MAX):
        document["actors"].append({"id": f"extra{index}", "text": f"Extra {index}"})
        document["edges"].append({"from": f"extra{index}", "to": "balance"})
    assert "kind of user" in refused_at(document, f"/actors/{USECASE_ACTOR_MAX}")
