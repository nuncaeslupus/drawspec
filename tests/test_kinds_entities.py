"""`entities` — ER diagrams, database schemas and class diagrams, as one kind.

The kind's claims are about where lines land and what is drawn at their ends: a
relation that names a field leaves that field's row, one that does not lands on
the box; an end with a cardinality carries its marks (or its number), one
without carries the role's head; general entities sit above specific ones. Each
is asserted from the drawing. The document rules are asserted by the pointer of
their refusal.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError
from drawspec.kinds.entities import (
    KEY_MARKS,
    NUMBERS,
    EntitiesDrawing,
    entities_drawing,
    entities_scene,
    mark_length,
)
from drawspec.scene import Path as Stroke
from drawspec.scene import TextLine, TextRun
from drawspec.schema import (
    CARDINALITIES,
    ENTITY_EDGE_ROLES,
    READABILITY_BUDGET,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
NUMERIC = load_theme({"version": 1, "entities": {"notation": "numeric"}})
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("entities-*.json"))
EPSILON = 1e-6


def schema(**extra: Any) -> dict[str, Any]:
    """Two tables, one foreign key drawn from its column to the key it refers to."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "entities",
        "entities": [
            {
                "id": "teams",
                "text": "`teams`",
                "fields": [
                    {"id": "t_id", "text": "`id`", "type": "uuid", "key": "primary"},
                    {"text": "`name`", "type": "text"},
                ],
            },
            {
                "id": "people",
                "text": "`people`",
                "fields": [
                    {"text": "`id`", "type": "uuid", "key": "primary"},
                    {"text": "`email`", "type": "text", "key": "unique"},
                    {"id": "p_team", "text": "`team_id`", "type": "uuid", "key": "foreign"},
                    {"text": "..."},
                ],
            },
        ],
        "edges": [
            {
                "from": "people",
                "from_field": "p_team",
                "to": "teams",
                "to_field": "t_id",
                "from_end": "zero-or-many",
                "to_end": "one",
            }
        ],
    }
    document.update(extra)
    return document


def classes(**extra: Any) -> dict[str, Any]:
    """An interface, a base class realising it and a subclass."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "entities",
        "entities": [
            {"id": "store", "text": "Store", "tag": "interface", "operations": ["get(key)"]},
            {"id": "base", "text": "BaseStore", "fields": [{"text": "name", "type": "str"}]},
            {"id": "disk", "text": "DiskStore", "operations": ["flush()"]},
        ],
        "edges": [
            {"from": "base", "to": "store", "role": "realizes"},
            {"from": "disk", "to": "base", "role": "inherits"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> EntitiesDrawing:
    return entities_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return " ".join(violation.message for violation in validate_document(document))


# ---------------------------------------------------------------------------
# The reference documents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_document_renders(path: Path) -> None:
    assert render(json.loads(path.read_text(encoding="utf-8"))).startswith("<svg")


def test_there_is_a_reference_per_vocabulary() -> None:
    """A conceptual model, a physical schema and a class diagram, at least."""
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in REFERENCES]
    assert len(documents) >= 3
    edges = [edge for document in documents for edge in document.get("edges", ())]
    assert any("from_field" in edge for edge in edges), "a schema drawn from its columns"
    assert any(edge.get("role") == "inherits" for edge in edges), "a class hierarchy"
    assert any("from_end" in edge and "from_field" not in edge for edge in edges), "an ER model"


def test_the_minimal_example_is_valid() -> None:
    from drawspec.examples import EXAMPLES

    assert render(EXAMPLES["entities"]).startswith("<svg")


# ---------------------------------------------------------------------------
# Where lines land
# ---------------------------------------------------------------------------


def test_a_row_anchored_end_lands_at_its_rows_centre() -> None:
    """The line leaves the foreign key's own row, and arrives at the key's row."""
    drawing = drawn(schema())
    (route,) = drawing.routes
    people, teams = drawing.boxes["people"], drawing.boxes["teams"]
    assert route.points[0][1] == pytest.approx(people.row_centre("p_team"))
    assert route.points[-1][1] == pytest.approx(teams.row_centre("t_id"))
    # …on a side of the box, not its top or bottom.
    assert route.points[0][0] in (pytest.approx(people.x), pytest.approx(people.right))
    assert route.points[-1][0] in (pytest.approx(teams.x), pytest.approx(teams.right))


def test_a_row_anchored_end_leaves_square_to_the_box() -> None:
    """The first run is horizontal: the line comes *out of* the row."""
    (route,) = drawn(schema()).routes
    (x0, y0), (x1, y1) = route.points[:2]
    assert y0 == pytest.approx(y1)
    assert x0 != pytest.approx(x1)


def test_a_plain_end_lands_on_the_box_border() -> None:
    document = schema()
    del document["edges"][0]["from_field"]
    del document["edges"][0]["to_field"]
    drawing = drawn(document)
    (route,) = drawing.routes
    for point, identifier in ((route.points[0], "people"), (route.points[-1], "teams")):
        box = drawing.boxes[identifier]
        on_side = (
            min(abs(point[0] - box.x), abs(point[0] - box.right)) < EPSILON
            and box.y - EPSILON <= point[1] <= box.bottom + EPSILON
        )
        on_end = (
            min(abs(point[1] - box.y), abs(point[1] - box.bottom)) < EPSILON
            and box.x - EPSILON <= point[0] <= box.right + EPSILON
        )
        assert on_side or on_end, identifier


def test_two_relations_between_stacked_boxes_take_opposite_sides() -> None:
    """Two row-anchored lines on one side of a column of boxes would cross."""
    document = schema(width=360)
    document["edges"][0]["label"] = "on delete cascade"
    document["entities"][0]["fields"].append(
        {"id": "t_lead", "text": "`lead_id`", "key": "foreign"}
    )
    document["entities"][1]["fields"][0]["id"] = "p_id"
    document["edges"].append(
        {"from": "teams", "from_field": "t_lead", "to": "people", "to_field": "p_id"}
    )
    drawing = drawn(document)
    assert drawing.direction == "down"
    first, second = drawing.routes
    people = drawing.boxes["people"]
    sides = {
        "right" if abs(route.points[index][0] - people.right) < EPSILON else "left"
        for route, index in ((first, 0), (second, -1))
    }
    assert sides == {"left", "right"}


# ---------------------------------------------------------------------------
# A star
# ---------------------------------------------------------------------------


def star(*dimensions: str, named: bool = False) -> dict[str, Any]:
    """A fact table in the middle and one dimension per name, each with a key it refers to."""
    entities: list[dict[str, Any]] = [
        {
            "id": "sales",
            "text": "`fact_sales`",
            "centre": True,
            "fields": [
                *(
                    {"id": f"s_{name}", "text": f"`{name}_id`", "key": "foreign"}
                    for name in dimensions
                ),
                {"text": "`amount`"},
            ],
        }
    ]
    edges: list[dict[str, Any]] = []
    for name in dimensions:
        entities.append(
            {
                "id": name,
                "text": f"`dim_{name}`",
                "fields": [{"id": f"{name}_id", "text": f"`{name}_id`", "key": "primary"}],
            }
        )
        edge = {"from": name, "to": "sales", "from_end": "one", "to_end": "zero-or-many"}
        if named:
            edge.update(from_field=f"{name}_id", to_field=f"s_{name}")
        edges.append(edge)
    return {"version": 1, "kind": "entities", "entities": entities, "edges": edges}


def _crosses(first: Any, second: Any) -> bool:
    """Whether a horizontal run of one route crosses a vertical run of the other inside both."""
    for one, other in ((first, second), (second, first)):
        for (ax, ay), (bx, by) in itertools.pairwise(one.points):
            if abs(ay - by) > EPSILON:
                continue
            for (cx, cy), (dx, dy) in itertools.pairwise(other.points):
                if abs(cx - dx) > EPSILON:
                    continue
                if (
                    min(ax, bx) + EPSILON < cx < max(ax, bx) - EPSILON
                    and min(cy, dy) + EPSILON < ay < max(cy, dy) - EPSILON
                ):
                    return True
    return False


def test_a_star_puts_four_dimensions_one_per_side_of_the_fact() -> None:
    """The first above, the rest clockwise: right, below, left, as written."""
    boxes = drawn(star("date", "product", "store", "customer")).boxes
    sales = boxes["sales"]
    assert boxes["date"].bottom < sales.y
    assert boxes["product"].x > sales.right
    assert boxes["store"].y > sales.bottom
    assert boxes["customer"].right < sales.x


def test_a_star_draws_each_plain_spoke_straight_across_its_gap() -> None:
    """Two points each: a dimension square to a side is joined with no bend.

    Read as a layered drawing, the one below counted as a line going backwards
    and was sent out a side and round.
    """
    drawing = drawn(star("date", "product", "store", "customer"))
    assert [len(route.points) for route in drawing.routes] == [2, 2, 2, 2]


def test_a_star_spreads_the_spokes_along_each_side_of_the_fact() -> None:
    """Seven dimensions: no two lines end at one point of the middle."""
    drawing = drawn(star("a", "b", "c", "d", "e", "f", "g"))
    ends = [route.points[-1] for route in drawing.routes]
    assert len({(round(x, 3), round(y, 3)) for x, y in ends}) == 7


@pytest.mark.parametrize("count", [4, 5, 6, 7])
def test_no_two_boxes_of_a_star_overlap(count: int) -> None:
    """Up to the budget's seven round one: the ring widens until none touch."""
    names = [f"d{index}" for index in range(count)]
    boxes = list(drawn(star(*names)).boxes.values())
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            apart = (
                first.right <= second.x
                or second.right <= first.x
                or first.bottom <= second.y
                or second.bottom <= first.y
            )
            assert apart, (first.entity.id, second.entity.id)


@pytest.mark.parametrize("named", [False, True])
def test_no_two_spokes_of_a_star_cross(named: bool) -> None:
    """A row-anchored line to the dimension below goes round the side it crosses nothing on.

    Its side counted the lines already there and went to the emptier one, which
    put it on the left, past the row the line to the left dimension leaves from.
    """
    routes = drawn(star("date", "product", "store", "customer", named=named)).routes
    for index, first in enumerate(routes):
        for second in routes[index + 1 :]:
            assert not _crosses(first, second)


def test_a_second_centre_is_refused() -> None:
    document = star("date", "product")
    document["entities"][1]["centre"] = True
    assert pointers(document) == ["/entities/1/centre"]
    assert "one middle" in messages(document)


def test_a_centre_in_a_class_hierarchy_is_refused() -> None:
    document = classes()
    document["entities"][0]["centre"] = True
    assert pointers(document) == ["/entities/0/centre"]
    assert "general above specific" in messages(document)


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def test_a_hierarchy_puts_the_general_above_the_specific() -> None:
    drawing = drawn(classes())
    boxes = drawing.boxes
    assert drawing.direction == "down"
    assert boxes["store"].bottom < boxes["base"].y
    assert boxes["base"].bottom < boxes["disk"].y


def test_a_hierarchy_line_arrives_at_the_bottom_of_the_general_class() -> None:
    """Routed with the drawing's direction, not round the outside as a return."""
    drawing = drawn(classes())
    disk_to_base = drawing.routes[1]
    assert disk_to_base.points[-1][1] == pytest.approx(drawing.boxes["base"].bottom)
    assert disk_to_base.points[0][1] == pytest.approx(drawing.boxes["disk"].y)


def test_the_one_side_is_placed_before_the_many_side() -> None:
    """A foreign key is written from its column, and still reads from the table it names."""
    drawing = drawn(schema())
    assert drawing.direction == "right"
    assert drawing.boxes["teams"].right < drawing.boxes["people"].x


def test_without_a_hierarchy_the_diagram_reads_across_when_it_fits() -> None:
    """Read across, a label needs its own width between the ranks — so it can tip a
    narrow canvas into reading down, where the label sits beside the line."""
    labelled = schema(width=360)
    labelled["edges"][0]["label"] = "on delete cascade"
    assert drawn(schema(width=360)).direction == "right"
    assert drawn(labelled).direction == "down"
    assert drawn({**labelled, "width": 640}).direction == "right"


# ---------------------------------------------------------------------------
# What is drawn at the ends
# ---------------------------------------------------------------------------


def _strokes_near(scene: Any, point: tuple[float, float], reach: float) -> list[Any]:
    found = []
    for primitive in scene.primitives:
        if (
            isinstance(primitive, Stroke)
            and primitive.marker
            and any(math.dist(point, vertex) <= reach for vertex in primitive.points)
        ):
            found.append(primitive)
    return found


def _ring(mark: Any) -> bool:
    """A ring is traced as a many-sided path that returns to its start."""
    return isinstance(mark, Stroke) and len(mark.points) > 4 and mark.points[0] == mark.points[-1]


def test_crows_feet_are_drawn_at_the_right_ends() -> None:
    """`one` is two bars; `zero-or-many` is a foot and a ring, and the ring breaks the line."""
    document = parse_document(schema())
    drawing = entities_drawing(document, THEME, MEASURER)
    scene = entities_scene(document, THEME, MEASURER)
    (route,) = drawing.routes
    reach = mark_length("link", THEME) * 2
    at_many = _strokes_near(scene, route.points[0], reach)
    at_one = _strokes_near(scene, route.points[-1], reach)
    assert sum(_ring(mark) for mark in at_many) == 1
    assert sum(isinstance(mark, Stroke) and len(mark.points) == 3 for mark in at_many) == 1
    assert sum(_ring(mark) for mark in at_one) == 0
    bars = [mark for mark in at_one if isinstance(mark, Stroke) and len(mark.points) == 2]
    assert len(bars) == 2


@pytest.mark.parametrize("cardinality", CARDINALITIES)
def test_numeric_notation_writes_the_multiplicity_beside_the_end(cardinality: str) -> None:
    document = schema()
    document["edges"][0]["from_end"] = cardinality
    parsed = parse_document(document)
    drawing = entities_drawing(parsed, NUMERIC, MEASURER)
    scene = entities_scene(parsed, NUMERIC, MEASURER)
    texts = {primitive.text for primitive in scene.primitives if isinstance(primitive, TextRun)}
    assert NUMBERS[cardinality] in texts
    assert NUMBERS["one"] in texts
    assert not any(_ring(primitive) for primitive in scene.primitives)
    tip = drawing.routes[0].points[0]
    assert any(
        math.dist(tip, (number.left, number.top)) < number.width + 20
        for number in drawing.numbers
        if number.text == NUMBERS[cardinality]
    )


def test_an_end_without_a_cardinality_draws_the_roles_head() -> None:
    """`owns` keeps its diamond at the whole; `inherits` its hollow triangle."""
    document = classes()
    document["entities"].append({"id": "cache", "text": "Cache"})
    document["edges"].append({"from": "cache", "to": "disk", "role": "owns", "from_end": "one"})
    parsed = parse_document(document)
    scene = entities_scene(parsed, THEME, MEASURER)
    drawing = entities_drawing(parsed, THEME, MEASURER)
    for route in drawing.routes:
        marks = _strokes_near(scene, route.points[-1], 1.0)
        if route.role in ("inherits", "realizes"):
            (triangle,) = (mark for mark in marks if isinstance(mark, Stroke))
            assert len(triangle.points) == 4, "a closed outline: tip, two corners, back"
    assert any(
        type(primitive).__name__ == "Polygon" and primitive.role == "owns"
        for primitive in scene.primitives
    )


def test_a_hollow_head_is_not_crossed_by_its_own_line() -> None:
    parsed = parse_document(classes())
    scene = entities_scene(parsed, THEME, MEASURER)
    drawing = entities_drawing(parsed, THEME, MEASURER)
    tip = drawing.routes[1].points[-1]
    shafts = [
        primitive
        for primitive in scene.primitives
        if isinstance(primitive, Stroke) and not primitive.marker and primitive.role == "inherits"
    ]
    (shaft,) = shafts
    assert math.dist(shaft.points[-1], tip) > THEME.edge.head_length


def test_inherits_owns_and_link_differ_by_head_alone() -> None:
    """Greyscale: the three are told apart by the shape at the end, not by colour."""
    heads = {role: THEME.edge_roles[role].head for role in ("inherits", "owns", "link")}
    assert len(set(heads.values())) == 3
    assert THEME.edge_roles["inherits"].channels != THEME.edge_roles["realizes"].channels


def test_key_marks_are_letters() -> None:
    scene = entities_scene(parse_document(schema()), THEME, MEASURER)
    texts = {primitive.text for primitive in scene.primitives if isinstance(primitive, TextRun)}
    assert {KEY_MARKS["primary"], KEY_MARKS["foreign"], KEY_MARKS["unique"]} <= texts


def test_a_stereotype_is_drawn_in_guillemets_over_the_name() -> None:
    scene = entities_scene(parse_document(classes()), THEME, MEASURER)
    lines = [primitive for primitive in scene.primitives if isinstance(primitive, TextLine)]
    (tag,) = (line for line in lines if line.text == "«interface»")
    (name,) = (line for line in lines if line.text == "Store")
    assert tag.y < name.y


def test_a_row_too_long_for_its_share_of_the_canvas_is_a_fit_error() -> None:
    document = schema()
    document["entities"][0]["fields"][1]["text"] = "a field name " * 8
    with pytest.raises(FitError, match="never wraps"):
        drawn(document)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_cardinality_on_a_hierarchy_relation_is_refused() -> None:
    document = classes()
    document["edges"][1]["to_end"] = "one"
    assert pointers(document) == ["/edges/1/to_end"]
    assert "no cardinality" in messages(document)


def test_a_field_on_a_hierarchy_relation_is_refused() -> None:
    document = classes()
    document["entities"][1]["fields"][0]["id"] = "b_name"
    document["edges"][0]["from_field"] = "b_name"
    assert pointers(document) == ["/edges/0/from_field"]


def test_an_inheritance_cycle_is_refused_at_the_edge_that_closes_it() -> None:
    document = classes()
    document["edges"].append({"from": "store", "to": "disk", "role": "inherits"})
    assert pointers(document) == ["/edges/2"]
    assert "loop" in messages(document)


def test_a_field_of_another_entity_is_refused() -> None:
    document = schema()
    document["edges"][0]["from_field"] = "t_id"
    assert pointers(document) == ["/edges/0/from_field"]
    assert "not of 'people'" in messages(document)


def test_an_unknown_field_is_refused_with_the_closest_one() -> None:
    document = schema()
    document["edges"][0]["to_field"] = "t_idd"
    assert pointers(document) == ["/edges/0/to_field"]
    assert "'t_id'" in messages(document)


def test_an_unknown_entity_is_refused() -> None:
    document = schema()
    document["edges"][0]["to"] = "team"
    assert "/edges/0/to" in pointers(document)


def test_aggregation_is_refused_and_the_message_says_why() -> None:
    document = schema()
    document["edges"][0]["role"] = "aggregates"
    assert pointers(document) == ["/edges/0/role"]
    assert "most misread" in messages(document)


def test_flow_only_roles_are_refused_here() -> None:
    document = schema()
    document["edges"][0]["role"] = "flow"
    assert pointers(document) == ["/edges/0/role"]
    assert "flow" not in ENTITY_EDGE_ROLES


def test_visibility_is_not_a_field() -> None:
    document = schema()
    document["entities"][0]["fields"][1]["visibility"] = "private"
    assert pointers(document) == ["/entities/0/fields/1/visibility"]


@pytest.mark.parametrize(("name", "where"), [("width", "entities/0"), ("port", "edges/0")])
def test_geometry_is_refused_by_name(name: str, where: str) -> None:
    document = schema()
    target: Any = document
    for part in where.split("/"):
        target = target[int(part)] if part.isdigit() else target[part]
    target[name] = 1
    assert pointers(document) == [f"/{where}/{name}"]


def test_a_placeholder_must_be_the_last_field() -> None:
    document = schema()
    fields = document["entities"][1]["fields"]
    fields.insert(0, fields.pop())
    assert pointers(document) == ["/entities/1/fields/0/text"]


def test_a_placeholder_has_no_type_key_or_id() -> None:
    document = schema()
    document["entities"][1]["fields"][-1]["type"] = "text"
    assert pointers(document) == ["/entities/1/fields/3/type"]


def test_a_relation_to_itself_is_refused() -> None:
    document = schema()
    document["edges"][0]["to"] = "people"
    del document["edges"][0]["to_field"]
    assert pointers(document) == ["/edges/0/to"]


def test_the_whole_end_of_owns_has_no_cardinality() -> None:
    document = schema()
    document["edges"][0]["role"] = "owns"
    assert pointers(document) == ["/edges/0/to_end"]


def test_a_long_tag_is_refused() -> None:
    document = classes()
    document["entities"][0]["tag"] = "a stereotype far too long"
    assert pointers(document) == ["/entities/0/tag"]


def test_duplicate_ids_are_refused() -> None:
    document = schema()
    document["entities"][1]["id"] = "teams"
    document["entities"][1]["fields"][2]["id"] = "t_id"
    found = pointers(document)
    assert "/entities/1/id" in found
    assert "/entities/1/fields/2/id" in found


def test_a_name_on_two_lines_is_refused() -> None:
    document = schema()
    document["entities"][0]["text"] = "teams\nthe groups people work in"
    assert pointers(document) == ["/entities/0/text"]


def test_budget_caps_entities_fields_and_operations() -> None:
    budget = dict(READABILITY_BUDGET["entities"])
    many = {
        "version": 1,
        "kind": "entities",
        "entities": [{"id": f"e{index}", "text": f"E{index}"} for index in range(9)],
    }
    assert pointers(many) == [f"/entities/{budget['entities']}"]

    document = schema()
    document["entities"][0]["fields"] = [{"text": f"f{index}"} for index in range(13)]
    document["entities"][0]["operations"] = [f"op{index}()" for index in range(9)]
    document["edges"][0].pop("to_field")
    found = pointers(document)
    assert f"/entities/0/fields/{budget['entities/fields']}" in found
    assert f"/entities/0/operations/{budget['entities/operations']}" in found
    assert "end the list with a `...` field" in messages(document)


def test_an_entities_document_parses_into_its_model() -> None:
    parsed = parse_document(schema())
    (relation,) = parsed.relations
    assert relation.source_field == "p_team"
    assert relation.target_end == "one"
    assert parsed.entities[1].fields[-1].placeholder
    with pytest.raises(DocumentError):
        parse_document(schema(entities=[]))


def zoo() -> dict[str, Any]:
    """Three subclasses and an interface two of them implement: a crowded gap."""
    return {
        "version": 1,
        "kind": "entities",
        "entities": [
            {"id": "animal", "text": "Animal", "tag": "abstract", "operations": ["speak()"]},
            {"id": "dog", "text": "Dog", "operations": ["speak()"]},
            {"id": "cat", "text": "Cat", "operations": ["speak()"]},
            {"id": "bird", "text": "Bird", "operations": ["speak()", "fly()"]},
            {"id": "owner", "text": "Owner", "fields": [{"text": "name"}]},
            {"id": "pet", "text": "Pettable", "tag": "interface", "operations": ["pet()"]},
        ],
        "edges": [
            {"from": "dog", "to": "animal", "role": "inherits"},
            {"from": "cat", "to": "animal", "role": "inherits"},
            {"from": "bird", "to": "animal", "role": "inherits"},
            {"from": "dog", "to": "pet", "role": "realizes"},
            {"from": "cat", "to": "pet", "role": "realizes"},
            {"from": "animal", "to": "owner", "from_end": "zero-or-many", "to_end": "one"},
        ],
    }


def test_subclasses_share_one_triangle_and_a_trunk() -> None:
    """Every line to one general class arrives at one point, as a class diagram's tree."""
    drawing = drawn(zoo())
    tips = {route.points[-1] for route in drawing.routes if route.target == "animal"}
    assert len(tips) == 1
    (tip,) = tips
    animal = drawing.boxes["animal"]
    assert tip == (pytest.approx(animal.x + animal.width / 2), pytest.approx(animal.bottom))


def test_no_route_runs_through_its_own_boxes() -> None:
    """Lane separation in a crowded gap once moved a run inside the box it entered."""
    drawing = drawn(zoo())
    for route in drawing.routes:
        for identifier in (route.source, route.target):
            box = drawing.boxes[identifier]
            for (x0, y0), (x1, y1) in route.segments[1:-1]:
                inside_x = min(x0, x1) < box.right - EPSILON and max(x0, x1) > box.x + EPSILON
                inside_y = min(y0, y1) < box.bottom - EPSILON and max(y0, y1) > box.y + EPSILON
                assert not (inside_x and inside_y), (route.source, route.target)


def test_a_crowded_gap_is_widened_so_lines_keep_their_lanes() -> None:
    """Five relations cross the gap under `Animal`: no two horizontal runs share a line."""
    drawing = drawn(zoo())
    runs = [
        (round(y0, 3), min(x0, x1), max(x0, x1), route.target)
        for route in drawing.routes
        for (x0, y0), (x1, y1) in route.segments
        if abs(y0 - y1) < EPSILON and abs(x0 - x1) > EPSILON
    ]
    for index, (y, left, right, target) in enumerate(runs):
        for other_y, other_left, other_right, other_target in runs[index + 1 :]:
            if target != other_target and y == other_y:
                assert right <= other_left or other_right <= left
