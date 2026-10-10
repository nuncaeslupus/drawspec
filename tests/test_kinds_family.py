"""`familytree` — people, couples and their children (a pedigree in genetics).

The kind's promises: generations are rows, derived — partners share one and a
child is one below its couple — and people are numbered left to right in each, so
a number in a letter stays right when someone is added; the standard's symbols
carry sex (or gender), status and the marks without colour; and no line crosses
another, even for a person with six partners.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError, ThemeError
from drawspec.geometry import fit
from drawspec.kinds.familytree import FamilyDrawing, familytree_drawing
from drawspec.schema import (
    FAMILYTREE_PARTNER_MAX,
    FAMILYTREE_PEOPLE_MAX,
    READABILITY_BUDGET,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("familytree-*.json"))


def recessive(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "familytree",
        "people": [
            {"id": "gf", "sex": "male"},
            {"id": "gm", "sex": "female", "status": "carrier"},
            {"id": "dad", "sex": "male", "status": "carrier"},
            {"id": "aunt", "sex": "female"},
            {"id": "mum", "sex": "female", "status": "carrier"},
            {"id": "c1", "sex": "female"},
            {"id": "c2", "sex": "male", "status": "affected", "proband": True},
        ],
        "couples": [
            {"between": ["gf", "gm"], "children": ["dad", "aunt"]},
            {"between": ["dad", "mum"], "children": ["c1", "c2"]},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Theme = THEME) -> FamilyDrawing:
    """The drawing at the type scale `render` settles on."""
    parsed = parse_document(document)
    return fit(theme, lambda scaled: familytree_drawing(parsed, scaled, MEASURER)).value


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def segments(drawing: FamilyDrawing) -> list[tuple[int, tuple[float, float], tuple[float, float]]]:
    found = []
    for line in drawing.lines:
        for a, b in zip(line.points, line.points[1:], strict=False):
            found.append((line.couple, a, b))
    return found


def crosses(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    """Whether two segments cross at a point inside both (touching ends do not count)."""

    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    eps = 1e-6
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    )


# -- the references -----------------------------------------------------------


def test_there_are_at_least_three_reference_trees() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_and_validates(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_partners_share_a_row_and_children_are_one_below(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    row = {person.id: person.generation for person in drawing.people}
    centre = {person.id: (person.symbol[1] + person.symbol[3]) / 2 for person in drawing.people}
    for couple in document["couples"]:
        a, b = couple["between"]
        assert row[a] == row[b]
        assert centre[a] == pytest.approx(centre[b])
        for child in couple.get("children", ()):
            assert row[child] == row[a] + 1


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_line_crosses_another(path: Path) -> None:
    """The geometry check the proposal asked for: no partner, descent, sibship or drop
    line crosses another — including the lines over the row to later partners."""
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    found = segments(drawing)
    for index, (couple_a, a, b) in enumerate(found):
        for couple_b, c, d in found[index + 1 :]:
            if couple_a == couple_b:
                continue
            assert not crosses(a, b, c, d), (couple_a, a, b, couple_b, c, d)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_line_runs_through_a_symbol_or_a_name(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for _, a, b in segments(drawing):
        for person in drawing.people:
            for box in (person.symbol, person.label):
                left, top, right, bottom = box
                inset = 1.0
                # A segment is axis-aligned or a short diagonal to a twin: sample it.
                for step in range(1, 20):
                    t = step / 20
                    x = a[0] + (b[0] - a[0]) * t
                    y = a[1] + (b[1] - a[1]) * t
                    inside = left + inset < x < right - inset and top + inset < y < bottom - inset
                    assert not inside, (person.id, a, b)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_people_are_numbered_left_to_right_in_each_generation(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    rows: dict[int, list[tuple[float, int]]] = {}
    for person in drawing.people:
        rows.setdefault(person.generation, []).append((person.symbol[0], person.number))
    for entries in rows.values():
        assert [number for _, number in sorted(entries)] == list(range(1, len(entries) + 1))


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_roman_numerals_label_every_generation(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    svg = render(document)
    rows = len(drawn(document).rows)
    for numeral in ("I", "II", "III", "IV")[:rows]:
        assert f">{numeral}<" in svg


def test_numbers_in_earlier_generations_survive_adding_a_person() -> None:
    """The derived numbers are stable: a child added at the end of the last row
    renumbers nothing above it."""
    document = json.loads((REFERENCE / "familytree-cousins.json").read_text(encoding="utf-8"))
    before = {(p.id, p.generation, p.number) for p in drawn(document).people}
    grown = copy.deepcopy(document)
    grown["people"].append({"id": "k5", "sex": "male"})
    grown["couples"][-1]["children"].append("k5")
    after = {(p.id, p.generation, p.number) for p in drawn(grown).people}
    last = max(generation for _, generation, _ in before)
    assert {e for e in before if e[1] < last} == {e for e in after if e[1] < last}


def test_children_sit_in_birth_order() -> None:
    drawing = drawn(recessive())
    x = {person.id: person.symbol[0] for person in drawing.people}
    assert x["c1"] < x["c2"]
    assert x["dad"] < x["aunt"] or x["mum"] < x["dad"]


def test_a_married_in_partner_takes_the_outside() -> None:
    """A first-born's partner goes on the left, so the sibship stays together."""
    drawing = drawn(recessive())
    x = {person.id: person.symbol[0] for person in drawing.people}
    assert x["mum"] < x["dad"] < x["aunt"]


# -- symbols and marks ----------------------------------------------------------


def test_sex_picks_the_shape() -> None:
    document = recessive()
    document["people"][5]["sex"] = "unknown"
    shapes = {person.id: person.shape for person in drawn(document).people}
    assert shapes["gf"] == "square"
    assert shapes["gm"] == "circle"
    assert shapes["c1"] == "diamond"


def test_gender_picks_the_shape_and_assigned_sex_is_noted_when_it_differs() -> None:
    document = recessive()
    document["people"][5].update({"gender": "nonbinary"})
    document["people"][6].update({"gender": "woman"})
    document["people"][2].update({"gender": "man"})
    shapes = {person.id: person.shape for person in drawn(document).people}
    assert shapes["c1"] == "diamond"
    assert shapes["c2"] == "circle"
    svg = render(document)
    assert svg.count(">AFAB<") == 1
    assert svg.count(">AMAB<") == 1


def test_status_is_told_apart_without_colour_and_keyed() -> None:
    svg = render(recessive())
    assert ">Affected<" in svg and ">Carrier<" in svg and ">Unaffected<" in svg
    # Affected is a fill in the ink, not a colour: it survives greyscale.
    assert 'fill="currentColor"' in svg


def test_no_key_without_a_status() -> None:
    document = json.loads((REFERENCE / "familytree-tudors.json").read_text(encoding="utf-8"))
    svg = render(document)
    assert ">Affected<" not in svg and ">Unaffected<" not in svg


def test_the_carrier_mark_is_the_themes() -> None:
    from dataclasses import replace

    from drawspec.theme import FamilytreeStyle

    dot = drawn(recessive())
    half = drawn(recessive(), replace(THEME, familytree=FamilytreeStyle(carrier="half")))
    regions = [p for p in half.scene.primitives if getattr(p, "region", False)]
    assert regions, "a half-filled carrier is a filled region under the outline"
    assert not [p for p in dot.scene.primitives if getattr(p, "region", False)]


def test_an_unknown_carrier_mark_is_refused_by_the_theme() -> None:
    from drawspec.theme import FamilytreeStyle

    with pytest.raises(ThemeError, match="carrier"):
        FamilytreeStyle.from_mapping({"carrier": "stripes"})


def test_the_proband_carries_a_p_and_a_consultand_does_not() -> None:
    document = recessive()
    document["people"][4]["consultand"] = True
    svg = render(document)
    assert svg.count(">P<") == 1


def test_twins_leave_the_sibship_line_from_one_point() -> None:
    document = recessive()
    document["couples"][1]["twins"] = [{"of": ["c1", "c2"], "zygosity": "monozygotic"}]
    drawing = drawn(document)
    twins = [line for line in drawing.lines if line.kind == "twin"]
    # Two diagonals from one apex, and the identical twins' bar between them.
    assert len(twins) == 3
    diagonals, bar = twins[:2], twins[2]
    assert diagonals[0].points[0] == diagonals[1].points[0]
    assert bar.points[0][1] == pytest.approx(bar.points[1][1])
    assert not [line for line in drawing.lines if line.kind == "drop" and line.couple == 1]


def test_twins_of_unknown_zygosity_get_a_question_mark() -> None:
    document = recessive()
    document["couples"][1]["twins"] = [{"of": ["c1", "c2"], "zygosity": "unknown"}]
    assert ">?<" in render(document)


def test_an_adopted_child_hangs_on_a_dashed_line_in_brackets() -> None:
    document = recessive()
    document["people"][5]["adopted"] = True
    drawing = drawn(document)
    drops = [line for line in drawing.lines if line.kind == "drop" and line.role == "aside"]
    assert len(drops) == 1


def test_a_pregnancy_and_a_loss() -> None:
    document = recessive()
    document["people"].append({"id": "p", "sex": "unknown", "pregnancy": "ongoing"})
    document["people"].append({"id": "l", "sex": "unknown", "pregnancy": "loss"})
    document["couples"][1]["children"] += ["l", "p"]
    shapes = {person.id: person.shape for person in drawn(document).people}
    assert shapes["l"] == "triangle"
    assert shapes["p"] == "diamond"
    assert render(document).count(">P<") == 2  # the proband's and the pregnancy's


def test_six_partners_draw_with_no_crossing_and_the_later_ones_over_the_row() -> None:
    drawing = drawn(json.loads((REFERENCE / "familytree-tudors.json").read_text("utf-8")))
    over = [line for line in drawing.lines if line.kind == "partner" and len(line.points) == 4]
    assert len(over) == 4  # partners three to six
    heights = [line.points[1][1] for line in sorted(over, key=lambda line: line.couple)]
    assert heights == sorted(heights, reverse=True), "the farthest partner's line is highest"


# -- refusals -----------------------------------------------------------------


def test_generation_and_number_are_derived_and_refused_by_name() -> None:
    document = recessive()
    document["people"][0]["generation"] = 1
    document["people"][1]["number"] = 2
    found = validate_document(document)
    assert {v.pointer for v in found} == {"/people/0/generation", "/people/1/number"}
    assert "derived" in found[0].message


@pytest.mark.parametrize("name", ["edges", "nodes", "groups"])
def test_graph_fields_are_refused(name: str) -> None:
    document = recessive(**{name: []})
    assert pointers(document) == [f"/{name}"]


@pytest.mark.parametrize("name", ["parents", "spouse", "partners", "children"])
def test_relations_on_a_person_are_refused_with_where_they_go(name: str) -> None:
    document = recessive()
    document["people"][2][name] = ["gf"]
    found = validate_document(document)
    assert [v.pointer for v in found] == [f"/people/2/{name}"]
    assert "couple" in found[0].message


def test_sex_is_required_with_what_to_write() -> None:
    document = recessive()
    del document["people"][0]["sex"]
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/people/0/sex"]
    assert "unknown" in found[0].message


def test_an_unknown_id_is_refused_at_its_pointer() -> None:
    document = recessive()
    document["couples"][1]["children"].append("nobody")
    assert pointers(document) == ["/couples/1/children/2"]


def test_a_child_of_two_couples_is_refused_with_adoption() -> None:
    document = recessive()
    document["couples"][1]["children"].append("aunt")
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples/1/children/2"]
    assert "adopted" in found[0].message


def test_a_couple_is_two_different_people_written_once() -> None:
    document = recessive()
    document["couples"].append({"between": ["gf", "gf"]})
    document["couples"].append({"between": ["gm", "gf"]})
    assert pointers(document) == ["/couples/2/between", "/couples/3/between"]


def test_a_couple_of_three_is_refused() -> None:
    document = recessive()
    document["couples"][0]["between"].append("aunt")
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples/0/between"]
    assert "one couple per partner" in found[0].message


def test_someone_their_own_ancestor_is_refused() -> None:
    document = recessive()
    document["couples"].append({"between": ["c2", "aunt"], "children": ["gf"]})
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples/2/children"]
    assert "circle" in found[0].message


def test_partners_in_different_generations_are_refused() -> None:
    document = recessive()
    document["couples"].append({"between": ["gf", "c1"]})
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples/2/between"]
    assert "share a row" in found[0].message


def test_a_person_in_no_couple_is_refused() -> None:
    document = recessive()
    document["people"].append({"id": "loner", "sex": "male"})
    assert pointers(document) == ["/people/7"]


def test_two_unrelated_families_are_refused() -> None:
    document = recessive()
    document["people"] += [{"id": "x", "sex": "male"}, {"id": "y", "sex": "female"}]
    document["couples"].append({"between": ["x", "y"]})
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/people/7"]
    assert "one family" in found[0].message


def test_partners_past_the_cap_are_refused() -> None:
    document = recessive()
    for index in range(FAMILYTREE_PARTNER_MAX):
        document["people"].append({"id": f"w{index}", "sex": "female"})
        document["couples"].append({"between": ["gf", f"w{index}"]})
    found = validate_document(document)
    assert [v.pointer for v in found] == [f"/couples/{2 + FAMILYTREE_PARTNER_MAX - 1}/between"]
    assert "6 partners at most" in found[0].message


def test_a_later_partner_with_parents_is_refused() -> None:
    document = recessive()
    document["people"] += [
        {"id": "w1", "sex": "female"},
        {"id": "w2", "sex": "female"},
    ]
    document["couples"] += [{"between": ["c2", "w1"]}, {"between": ["c2", "w2"]}]
    # c2's third partner is his sister: she has parents in the tree.
    document["couples"].append({"between": ["c2", "c1"]})
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples/4/between"]


def test_two_partners_who_both_have_others_are_refused() -> None:
    document = recessive()
    document["people"] += [{"id": "w1", "sex": "female"}, {"id": "h1", "sex": "male"}]
    document["couples"] += [{"between": ["dad", "w1"]}, {"between": ["mum", "h1"]}]
    found = validate_document(document)
    assert len(found) == 1
    assert "both have other partners" in found[0].message


def test_twins_must_be_written_together_and_be_this_couples() -> None:
    document = recessive()
    document["people"].append({"id": "c3", "sex": "male"})
    document["couples"][1]["children"].append("c3")
    document["couples"][1]["twins"] = [{"of": ["c1", "c3"], "zygosity": "dizygotic"}]
    assert pointers(document) == ["/couples/1/twins/0/of"]
    document["couples"][1]["twins"] = [{"of": ["c2", "aunt"], "zygosity": "dizygotic"}]
    assert pointers(document) == ["/couples/1/twins/0/of"]
    document["couples"][1]["twins"] = [{"of": ["c2", "c3"]}]
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples/1/twins/0/zygosity"]
    assert "monozygotic" in found[0].message


def test_one_proband() -> None:
    document = recessive()
    document["people"][5]["proband"] = True
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/people/6/proband"]
    assert "consultand" in found[0].message


def test_a_pregnancy_has_no_partners_and_a_loss_no_stroke() -> None:
    document = recessive()
    document["people"][5]["pregnancy"] = "ongoing"
    document["people"][6]["pregnancy"] = "loss"
    document["people"][6]["deceased"] = True
    document["people"].append({"id": "x", "sex": "male"})
    document["couples"].append({"between": ["c1", "x"]})
    assert pointers(document) == ["/people/6/deceased", "/couples/2/between"]


def test_an_ancestor_chart_is_refused_with_tree() -> None:
    """F3: one person, two parents, four grandparents — a binary tree, not a family."""
    people = [
        {"id": name, "sex": sex}
        for name, sex in (
            ("me", "female"),
            ("dad", "male"),
            ("mum", "female"),
            ("pgf", "male"),
            ("pgm", "female"),
            ("mgf", "male"),
            ("mgm", "female"),
        )
    ]
    document = {
        "version": 1,
        "kind": "familytree",
        "people": people,
        "couples": [
            {"between": ["dad", "mum"], "children": ["me"]},
            {"between": ["pgf", "pgm"], "children": ["dad"]},
            {"between": ["mgf", "mgm"], "children": ["mum"]},
        ],
    }
    found = validate_document(document)
    assert [v.pointer for v in found] == ["/couples"]
    assert "`tree`" in found[0].message


def test_five_generations_are_refused() -> None:
    document = recessive()
    previous = "c2"
    for index in range(2):
        document["people"] += [
            {"id": f"s{index}", "sex": "female"},
            {"id": f"k{index}", "sex": "male"},
        ]
        document["couples"].append({"between": [previous, f"s{index}"], "children": [f"k{index}"]})
        previous = f"k{index}"
    found = validate_document(document)
    assert any("4 at most" in v.message for v in found)


def test_the_people_budget() -> None:
    assert READABILITY_BUDGET["familytree"] == (("people", FAMILYTREE_PEOPLE_MAX),)
    document = recessive()
    for index in range(FAMILYTREE_PEOPLE_MAX):
        document["people"].append({"id": f"k{index}", "sex": "male"})
        document["couples"][1]["children"].append(f"k{index}")
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert f"/people/{FAMILYTREE_PEOPLE_MAX}" in [v.pointer for v in error.value.violations]


def test_a_row_too_wide_is_a_fit_error_naming_it() -> None:
    document = recessive()
    for index in range(16):
        document["people"].append({"id": f"k{index}", "sex": "male", "text": "Bartholomew"})
        document["couples"][1]["children"].append(f"k{index}")
    with pytest.raises(FitError, match="generation III"):
        render(document)
