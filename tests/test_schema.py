"""T4 — the document model, its validator, and the published JSON Schema.

The gate is `forbidden_field_acceptance_count == 0`: no field from the rejection
table in specification §5.1 is accepted, and each raises `DocumentError` carrying
the field's JSON pointer.

The other half of the task is that the *published* schema and the runtime
validator agree, because a schema that disagrees with the tool is worse than no
schema — an editor would tell an author their document is fine while `drawspec
validate` rejects it. Proving that needs a JSON Schema evaluator, and drawspec
has no runtime dependency that provides one, so this file carries a small one
covering the subset the published schema actually uses. It is an independent
reader in the same sense as `test_measure.py`'s: written against the JSON Schema
spec, not against `drawspec.schema`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec.errors import DocumentError
from drawspec.schema import (
    DOCUMENT_VERSION,
    KINDS,
    OBJECTS,
    REJECTED_FIELDS,
    SCHEMA_ID,
    Document,
    build_schema,
    fields_for,
    load_document,
    parse_document,
    published_schema_path,
    schema_json,
    validate_document,
)
from drawspec.theme import EDGE_ROLES, NODE_ROLES


def flow_document(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "flow",
        "title": "Request validation",
        "nodes": [
            {"id": "in", "text": "Request arrives", "role": "start"},
            {"id": "chk", "text": "Is the payload valid?", "role": "decision"},
            {"id": "ok", "text": "Queue for processing"},
        ],
        "edges": [
            {"from": "in", "to": "chk"},
            {"from": "chk", "to": "ok", "label": "yes"},
            {"from": "ok", "to": "in", "role": "link"},
        ],
    }
    document.update(overrides)
    return document


#: One valid document per kind, so every branch of the schema is exercised.
VALID_DOCUMENTS: dict[str, dict[str, Any]] = {
    "flow": flow_document(),
    "tree": flow_document(kind="tree"),
    "cycle": flow_document(kind="cycle"),
    "stack": {
        "version": 1,
        "kind": "stack",
        "items": [{"text": "Interface"}, {"text": "Domain"}, {"text": "Storage"}],
    },
    "timeline": {"version": 1, "kind": "timeline", "items": [{"text": "Draft"}, {"text": "Ship"}]},
    "columns": {
        "version": 1,
        "kind": "columns",
        "items": [{"text": "Before", "role": "note"}, {"text": "After", "role": "emphasis"}],
    },
    "pyramid": {
        "version": 1,
        "kind": "pyramid",
        "levels": [{"text": "Vision"}, {"text": "Strategy"}, {"text": "Tactics"}],
    },
    "rings": {"version": 1, "kind": "rings", "rings": [{"text": "Team"}, {"text": "Core"}]},
    "chart": {
        "version": 1,
        "kind": "chart",
        "axes": {
            "horizontal": {"label": "Week"},
            "vertical": {"label": "Requests", "unit": "thousands"},
        },
        "series": [{"name": "Accepted", "data": [[1, 10], [2, 14], [3, 12]]}],
    },
}


# --------------------------------------------------------------------------
# A JSON Schema evaluator, covering the subset the published schema uses
# --------------------------------------------------------------------------


def _resolve(reference: str, root: dict[str, Any]) -> dict[str, Any]:
    node: Any = root
    for part in reference.lstrip("#/").split("/"):
        node = node[part]
    return dict(node)


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    raise AssertionError(f"the evaluator does not cover type {expected!r}")


def evaluate(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> list[str]:
    """Errors `value` has against `schema`. Empty means valid.

    Covers exactly the keywords the published schema uses: `$ref`, `type`,
    `const`, `enum`, `exclusiveMinimum`, `properties`, `required`,
    `additionalProperties: false`, `items`, `minItems`, `maxItems`, `oneOf`.
    Anything else raises, so this cannot quietly stop checking.
    """
    unsupported = set(schema) - {
        "$ref",
        "$schema",
        "$id",
        "$defs",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "exclusiveMinimum",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "oneOf",
    }
    assert not unsupported, f"the evaluator does not cover {sorted(unsupported)}"

    if "$ref" in schema:
        return evaluate(value, _resolve(schema["$ref"], root), root)

    errors: list[str] = []

    if "oneOf" in schema:
        matches = [branch for branch in schema["oneOf"] if not evaluate(value, branch, root)]
        if len(matches) != 1:
            return [f"matched {len(matches)} of the oneOf branches, expected exactly 1"]

    if "type" in schema and not _type_matches(value, schema["type"]):
        return [f"expected type {schema['type']}"]
    if "const" in schema and value != schema["const"]:
        return [f"expected const {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{value!r} is not in the enum"]
    if "exclusiveMinimum" in schema and not value > schema["exclusiveMinimum"]:
        return [f"must be greater than {schema['exclusiveMinimum']}"]

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", ()):
            if name not in value:
                errors.append(f"{name!r} is required")
        if schema.get("additionalProperties") is False:
            errors += [f"{name!r} is not allowed" for name in value if name not in properties]
        for name, child in value.items():
            if name in properties:
                errors += evaluate(child, properties[name], root)

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append("too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("too many items")
        if "items" in schema:
            for element in value:
                errors += evaluate(element, schema["items"], root)

    return errors


def committed_schema() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(published_schema_path().read_text(encoding="utf-8"))
    return parsed


def accepted_by_schema(document: Any) -> bool:
    schema = committed_schema()
    return not evaluate(document, schema, schema)


def accepted_by_parser(document: Any) -> bool:
    return not validate_document(document)


# --------------------------------------------------------------------------
# The gate: forbidden fields are never accepted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(REJECTED_FIELDS))
def test_document_with_forbidden_field_raises_documenterror_naming_field(field: str) -> None:
    """`forbidden_field_acceptance_count == 0`, one field at a time.

    Every field in specification §5.1's rejection table, placed on a node — the
    element an author is most likely to try to position by hand.
    """
    document = flow_document()
    document["nodes"][1][field] = 1
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    message = str(error.value)
    assert field in message
    assert f"/nodes/1/{field}" in message
    assert any(violation.pointer == f"/nodes/1/{field}" for violation in error.value.violations)


@pytest.mark.parametrize("field", sorted(REJECTED_FIELDS))
def test_forbidden_field_is_also_rejected_by_the_published_schema(field: str) -> None:
    """The schema teaches the same lesson, while the author is still typing."""
    document = flow_document()
    document["nodes"][1][field] = 1
    assert not accepted_by_schema(document)


@pytest.mark.parametrize("field", ["x", "font_size", "stroke", "z", "arrow_head"])
def test_forbidden_field_message_says_why_not_just_that(field: str) -> None:
    """The message is the teaching surface for an author working blind."""
    document = flow_document()
    document["edges"][0][field] = 1
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert REJECTED_FIELDS[field].split(",")[0][:20] in str(error.value)


def test_document_with_a_forbidden_field_at_the_top_level_is_rejected() -> None:
    with pytest.raises(DocumentError, match="viewBox"):
        parse_document(flow_document(viewBox="0 0 10 10"))


def test_width_is_allowed_at_the_top_level_but_not_on_a_node() -> None:
    """The same name, legal in one place and refused in another — deliberately."""
    assert parse_document(flow_document(width=800)).width == 800
    document = flow_document()
    document["nodes"][0]["width"] = 120
    with pytest.raises(DocumentError, match="/nodes/0/width"):
        parse_document(document)


def test_all_violations_are_reported_not_only_the_first() -> None:
    document = flow_document()
    document["nodes"][0]["x"] = 1
    document["nodes"][1]["font_size"] = 9
    document["edges"][0]["dash"] = "3 2"
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    pointers = {violation.pointer for violation in error.value.violations}
    assert pointers == {"/nodes/0/x", "/nodes/1/font_size", "/edges/0/dash"}


# --------------------------------------------------------------------------
# version and kind
# --------------------------------------------------------------------------


def test_document_missing_version_raises_documenterror() -> None:
    document = flow_document()
    del document["version"]
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert "/version" in str(error.value)


def test_document_missing_both_version_and_kind_reports_both() -> None:
    with pytest.raises(DocumentError) as error:
        parse_document({"nodes": []})
    pointers = {violation.pointer for violation in error.value.violations}
    assert pointers == {"/version", "/kind"}


def test_document_with_a_future_version_raises_documenterror() -> None:
    with pytest.raises(DocumentError, match="version 2"):
        parse_document(flow_document(version=2))


def test_document_with_unknown_kind_raises_documenterror() -> None:
    with pytest.raises(DocumentError) as error:
        parse_document(flow_document(kind="mindmap"))
    assert "mindmap" in str(error.value)
    assert all(kind in str(error.value) for kind in KINDS)


def test_document_with_unknown_kind_does_not_report_payload_fields() -> None:
    """Without a kind, nothing is known about which payload is legal."""
    violations = validate_document(flow_document(kind="mindmap"))
    assert [violation.pointer for violation in violations] == ["/kind"]


def test_payload_of_one_kind_is_not_legal_in_another() -> None:
    """The kind selects the family, and the family selects the legal fields."""
    with pytest.raises(DocumentError, match="/nodes"):
        parse_document({"version": 1, "kind": "pyramid", "levels": [{"text": "A"}], "nodes": []})


# --------------------------------------------------------------------------
# Closed vocabularies
# --------------------------------------------------------------------------


def test_document_with_node_role_outside_vocabulary_raises_documenterror() -> None:
    document = flow_document()
    document["nodes"][0]["role"] = "swimlane"
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert "swimlane" in str(error.value)
    assert all(role in str(error.value) for role in NODE_ROLES)


def test_document_with_edge_role_outside_vocabulary_raises_documenterror() -> None:
    document = flow_document()
    document["edges"][0]["role"] = "dependsOn"
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert "dependsOn" in str(error.value)
    assert all(role in str(error.value) for role in EDGE_ROLES)


@pytest.mark.parametrize("role", NODE_ROLES)
def test_every_node_role_in_the_vocabulary_is_accepted(role: str) -> None:
    document = flow_document()
    document["nodes"][0]["role"] = role
    assert parse_document(document).nodes[0].role == role


@pytest.mark.parametrize("role", EDGE_ROLES)
def test_every_edge_role_in_the_vocabulary_is_accepted(role: str) -> None:
    document = flow_document()
    document["edges"][0]["role"] = role
    assert parse_document(document).edges[0].role == role


# --------------------------------------------------------------------------
# The published schema agrees with the runtime validator
# --------------------------------------------------------------------------


def test_published_schema_matches_the_runtime_validator() -> None:
    """Structural verdicts agree, document by document, in both directions.

    Referential rules — unique ids, an edge landing on a real node — are outside
    JSON Schema's reach and are listed separately below, so this comparison is
    over cases both are meant to decide.
    """
    structural: list[tuple[str, Any]] = [
        *((f"valid {kind}", document) for kind, document in VALID_DOCUMENTS.items()),
        ("forbidden field on a node", _with(flow_document(), "nodes", 0, x=1)),
        ("forbidden field on an edge", _with(flow_document(), "edges", 0, dx=2)),
        ("missing version", _without(flow_document(), "version")),
        ("future version", flow_document(version=2)),
        ("unknown kind", flow_document(kind="mindmap")),
        ("node role outside the vocabulary", _with(flow_document(), "nodes", 0, role="swimlane")),
        ("edge role outside the vocabulary", _with(flow_document(), "edges", 0, role="calls")),
        ("node missing its text", _without_key(flow_document(), "nodes", 0, "text")),
        ("edge missing its target", _without_key(flow_document(), "edges", 0, "to")),
        ("no nodes at all", flow_document(nodes=[])),
        ("width of the wrong type", flow_document(width="wide")),
        ("negative width", flow_document(width=-10)),
        ("height_binding of the wrong type", flow_document(height_binding="yes")),
        (
            "chart axis with no label",
            {**VALID_DOCUMENTS["chart"], "axes": {"horizontal": {}, "vertical": {}}},
        ),
        (
            "chart with no vertical axis",
            {**VALID_DOCUMENTS["chart"], "axes": {"horizontal": {"label": "Week"}}},
        ),
        (
            "chart series point that is not a pair",
            {**VALID_DOCUMENTS["chart"], "series": [{"name": "A", "data": [[1]]}]},
        ),
        ("group member list that is empty", flow_document(groups=[{"id": "g", "members": []}])),
    ]
    disagreements = [
        (label, accepted_by_parser(document), accepted_by_schema(document))
        for label, document in structural
        if accepted_by_parser(document) != accepted_by_schema(document)
    ]
    assert disagreements == []


REFERENTIAL_CASES: list[tuple[str, dict[str, Any]]] = [
    ("edge to a node that does not exist", flow_document(edges=[{"from": "in", "to": "nowhere"}])),
    (
        "duplicate node id",
        flow_document(
            nodes=[{"id": "a", "text": "One"}, {"id": "a", "text": "Two"}],
            edges=[],
        ),
    ),
    (
        "group member that does not exist",
        flow_document(groups=[{"id": "g", "members": ["ghost"]}]),
    ),
    # A group id is a name a member may resolve to, and the renderer keys its
    # containment tree and its captions by it — so a repeated one does not draw
    # twice, it silently replaces. Before this was enforced, a document with
    # three groups sharing two ids validated, rendered, and lost two of its
    # three captions with nothing said, which is precisely the class of failure
    # drawspec exists to make unexpressible.
    (
        "duplicate group id",
        flow_document(
            groups=[
                {"id": "g", "text": "First", "members": ["in"]},
                {"id": "g", "text": "Second", "members": ["chk"]},
            ]
        ),
    ),
    (
        "group id that is also a node id",
        flow_document(groups=[{"id": "in", "text": "Ambiguous", "members": ["chk"]}]),
    ),
]


@pytest.mark.parametrize(("label", "document"), REFERENTIAL_CASES, ids=lambda case: str(case)[:40])
def test_referential_rules_are_enforced_by_the_parser_alone(
    label: str, document: dict[str, Any]
) -> None:
    """JSON Schema cannot express these, so the schema documents the gap."""
    assert not accepted_by_parser(document), label
    assert accepted_by_schema(document), label


def test_committed_schema_is_exactly_what_the_field_tables_generate() -> None:
    """The artefact cannot drift: regenerate with `make schema`."""
    assert published_schema_path().read_text(encoding="utf-8") == schema_json()


def test_committed_schema_has_a_stable_id_and_the_draft_it_was_written_for() -> None:
    schema = committed_schema()
    assert schema["$id"] == SCHEMA_ID
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_every_object_in_the_schema_forbids_additional_properties() -> None:
    """The line that makes the schema teach rather than merely describe."""
    schema = build_schema()
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
    for variant in schema["oneOf"]:
        assert variant["additionalProperties"] is False


def test_every_kind_is_reachable_through_exactly_one_schema_branch() -> None:
    schema = build_schema()
    for kind in KINDS:
        branches = [
            variant for variant in schema["oneOf"] if kind in variant["properties"]["kind"]["enum"]
        ]
        assert len(branches) == 1, kind


def test_schema_documents_the_referential_rules_it_cannot_express() -> None:
    assert "beyond JSON Schema" in build_schema()["description"]


def test_every_valid_fixture_is_accepted_by_both() -> None:
    for kind, document in VALID_DOCUMENTS.items():
        assert accepted_by_parser(document), kind
        assert accepted_by_schema(document), kind


def test_schema_json_is_stable_across_calls() -> None:
    assert schema_json() == schema_json()


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------


def test_parse_builds_the_model_with_defaults_applied() -> None:
    document = parse_document(flow_document())
    assert isinstance(document, Document)
    assert document.kind == "flow"
    assert document.version == DOCUMENT_VERSION
    assert document.nodes[2].role == "step"
    assert document.edges[0].role == "flow"
    assert document.edges[2].role == "link"
    assert document.height is None
    assert document.height_binding is False


def test_parse_renames_from_and_to_so_they_are_not_python_keywords() -> None:
    edge = parse_document(flow_document()).edges[0]
    assert (edge.source, edge.target) == ("in", "chk")


def test_parse_chart_keeps_axes_in_horizontal_then_vertical_order() -> None:
    document = parse_document(VALID_DOCUMENTS["chart"])
    assert [axis.label for axis in document.axes] == ["Week", "Requests"]
    assert document.series[0].data == ((1.0, 10.0), (2.0, 14.0), (3.0, 12.0))


def test_parse_height_binding_makes_height_a_constraint() -> None:
    document = parse_document(flow_document(height=400, height_binding=True))
    assert document.height == 400
    assert document.height_binding is True


@pytest.mark.parametrize(
    ("kind", "family"),
    [("flow", "graph"), ("stack", "grid"), ("pyramid", "shape"), ("chart", "chart")],
)
def test_document_family_follows_from_its_kind(kind: str, family: str) -> None:
    assert parse_document(VALID_DOCUMENTS[kind]).family == family


def test_document_is_immutable() -> None:
    document = parse_document(flow_document())
    with pytest.raises(AttributeError):
        document.kind = "tree"  # type: ignore[misc]


def test_document_accepts_a_schema_key_for_editor_support() -> None:
    """A document that names the schema gets completion while it is being typed."""
    assert parse_document(flow_document(**{"$schema": SCHEMA_ID})).kind == "flow"


def test_parse_rejects_something_that_is_not_a_mapping() -> None:
    with pytest.raises(DocumentError, match="mapping"):
        parse_document([])  # type: ignore[arg-type]


def test_pointer_escapes_the_characters_rfc_6901_asks_it_to() -> None:
    document = flow_document()
    document["nodes"][0]["a/b~c"] = 1
    violations = validate_document(document)
    assert violations[0].pointer == "/nodes/0/a~1b~0c"


# --------------------------------------------------------------------------
# Loading from disk
# --------------------------------------------------------------------------


def test_load_document_reads_and_validates_json(tmp_path: Path) -> None:
    path = tmp_path / "diagram.json"
    path.write_text(json.dumps(flow_document()), encoding="utf-8")
    assert load_document(path).title == "Request validation"


def test_load_document_malformed_json_raises_documenterror(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DocumentError, match="not valid JSON"):
        load_document(path)


def test_load_document_missing_file_raises_documenterror(tmp_path: Path) -> None:
    with pytest.raises(DocumentError, match="could not be read"):
        load_document(tmp_path / "absent.json")


# --------------------------------------------------------------------------
# The field tables themselves
# --------------------------------------------------------------------------


def test_no_object_in_the_model_offers_a_field_from_the_rejection_table() -> None:
    """The strongest form of "unrepresentable": the field does not exist."""
    for name, specs in OBJECTS.items():
        for spec in specs:
            assert spec.name not in REJECTED_FIELDS, f"{name}.{spec.name}"


def test_only_the_top_level_offers_width_and_height() -> None:
    top_level = {spec.name for spec in fields_for("flow")}
    assert {"width", "height"} <= top_level


def test_every_kind_has_a_payload() -> None:
    for kind in KINDS:
        assert fields_for(kind)


def _with(document: dict[str, Any], key: str, index: int, **extra: Any) -> dict[str, Any]:
    document[key][index].update(extra)
    return document


def _without(document: dict[str, Any], key: str) -> dict[str, Any]:
    document.pop(key, None)
    return document


def _without_key(document: dict[str, Any], key: str, index: int, name: str) -> dict[str, Any]:
    document[key][index].pop(name, None)
    return document
