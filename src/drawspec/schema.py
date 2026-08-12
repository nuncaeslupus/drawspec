"""The input document: the model, the validator, and the published JSON Schema.

This is the contract that is most expensive to change, because documents written
against it live in the consumer's repository. Three properties matter more than
anything else in this module.

**What the author may not write is the point.** Coordinates, type sizes,
colours, arrow-head geometry and z-order are all decisions that require seeing
the output, and an author working blind cannot take them. So there is no field
for any of them — and, because every object sets `additionalProperties: false`,
writing one is an error that names the field rather than a key that is silently
dropped. A silently dropped key is the worst outcome available: the author
believes they configured something.

**One description, two renderings.** The field tables below are the single
source of truth. `parse_document` validates against them at runtime and
`build_schema` renders them as JSON Schema, so the published artefact cannot
drift from the tool. An editor's completion and `drawspec validate` are
therefore never in disagreement — which is the whole reason to publish a schema
rather than prose.

**Violations are located, not just named.** Each one carries a JSON pointer
(`/nodes/2/font_size`), the way an HTML validator names a line and an attribute,
and `validate_document` returns all of them rather than stopping at the first.

One class of check is deliberately outside the schema: referential integrity —
an edge naming a node that does not exist, or two nodes sharing an id. JSON
Schema cannot express it, so the parser enforces it alone and the schema
documents the gap rather than pretending to cover it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from drawspec.errors import DocumentError
from drawspec.theme import EDGE_ROLES, NODE_ROLES

#: The document format version this module reads.
DOCUMENT_VERSION: Final = 1

#: The published schema's stable identifier. A document that carries
#: `"$schema": "<this>"` gets completion and inline errors in any editor with
#: JSON Schema support — the author is told `font_size` is not allowed *while
#: typing it*, rather than after a render.
SCHEMA_ID: Final = "https://drawspec.dev/schema/drawspec-v1.schema.json"

#: Where the generated artefact is committed, relative to the repository root.
SCHEMA_FILENAME: Final = "drawspec-v1.schema.json"

GRAPH_KINDS: Final = ("flow", "tree", "cycle")
GRID_KINDS: Final = ("stack", "timeline", "columns")
SHAPE_KINDS: Final = ("pyramid", "rings")
CHART_KINDS: Final = ("chart",)

#: The order a chart's axes are held in, so `Document.axes` is not a mapping
#: whose iteration order a reader has to trust.
AXIS_ORDER: Final = ("horizontal", "vertical")

#: The nine kinds. Closed for v1: a tenth needs evidence, not a preference.
KINDS: Final = GRAPH_KINDS + GRID_KINDS + SHAPE_KINDS + CHART_KINDS

#: Fields an author might reach for that drawspec refuses, and why. Not used for
#: validation — `additionalProperties: false` already rejects them — but for the
#: message, which is the teaching surface for an author working blind.
REJECTED_FIELDS: Final = {
    "x": "coordinates are the tool's output, never its input",
    "y": "coordinates are the tool's output, never its input",
    "cx": "coordinates are the tool's output, never its input",
    "cy": "coordinates are the tool's output, never its input",
    "points": "coordinates are the tool's output, never its input",
    "d": "coordinates are the tool's output, never its input",
    "width": "box geometry is derived from measured text plus theme padding",
    "height": "box geometry is derived from measured text plus theme padding",
    "font_size": "type is selected by semantic role from the theme's scale",
    "font_family": "type is selected by semantic role from the theme's scale",
    "font_weight": "type is selected by semantic role from the theme's scale",
    "color": "appearance is a property of the role, not of the element",
    "fill": "appearance is a property of the role, not of the element",
    "stroke": "appearance is a property of the role, not of the element",
    "stroke_width": "appearance is a property of the role, not of the element",
    "anchor": "edge geometry comes from the edge's semantic role",
    "port": "edge geometry comes from the edge's semantic role",
    "arrow_head": 'say role: "link", not arrow_head: "none" — head geometry is the theme\'s',
    "dash": "line treatment comes from the edge's semantic role",
    "dx": "coordinates are the tool's output, never its input",
    "dy": "coordinates are the tool's output, never its input",
    "z": "overlap is resolved by the layout, not declared",
    "order": "overlap is resolved by the layout, not declared",
    "layer": "overlap is resolved by the layout, not declared",
    "viewBox": "derived from width and the content",
    "canvas": "derived from width and the content",
}


# ---------------------------------------------------------------------------
# The field tables — the single source of truth for both renderings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSpec:
    """One field: what it is called, what it may hold, whether it is required."""

    name: str
    kind: str
    """`string`, `number`, `integer`, `boolean`, `array` or `object`."""

    required: bool = False
    enum: tuple[str, ...] = ()
    ref: str = ""
    """For `object`: the name of the object table this field holds."""

    item_ref: str = ""
    """For `array`: the name of the object table each element holds."""

    item_kind: str = ""
    """For `array` of scalars: `string`, or `point` for an [x, y] pair."""

    min_items: int = 0
    exclusive_minimum: float | None = None
    description: str = ""


def _text(name: str = "text", *, required: bool = True) -> FieldSpec:
    return FieldSpec(
        name,
        "string",
        required=required,
        description=(
            "The words themselves. May carry inline spans — `code` for the monospace "
            "role and **bold** for emphasis — because those are semantic, not typographic."
        ),
    )


def _role(vocabulary: tuple[str, ...], default: str) -> FieldSpec:
    return FieldSpec(
        "role",
        "string",
        enum=vocabulary,
        description=(
            f"The semantic role, which the theme resolves to an appearance. "
            f"Defaults to {default!r}."
        ),
    )


#: Objects a document is built from. Every one sets `additionalProperties: false`.
OBJECTS: Final[Mapping[str, tuple[FieldSpec, ...]]] = {
    "node": (
        FieldSpec("id", "string", required=True, description="Unique within the document."),
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec("note", "string", description="A short aside attached to this node."),
    ),
    "edge": (
        FieldSpec("from", "string", required=True, description="The id of the source node."),
        FieldSpec("to", "string", required=True, description="The id of the target node."),
        FieldSpec("label", "string", description="A short label placed along the edge."),
        _role(EDGE_ROLES, "flow"),
    ),
    "group": (
        FieldSpec("id", "string", required=True),
        _text(required=False),
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description="The ids of the nodes this group contains.",
        ),
    ),
    "item": (
        FieldSpec("id", "string", description="Optional; generated from position when absent."),
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec("note", "string"),
    ),
    "level": (
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec("note", "string"),
    ),
    "ring": (
        _text(),
        _role(NODE_ROLES, "step"),
    ),
    "axis": (
        FieldSpec(
            "label",
            "string",
            required=True,
            description="Required: an unlabelled axis cannot be read.",
        ),
        FieldSpec("unit", "string"),
        FieldSpec("min", "number"),
        FieldSpec("max", "number"),
    ),
    "axes": (
        # Named by orientation rather than `x`/`y`: those name coordinates
        # everywhere else in this contract, and coordinates are drawspec's output.
        FieldSpec("horizontal", "object", required=True, ref="axis"),
        FieldSpec("vertical", "object", required=True, ref="axis"),
    ),
    "series": (
        FieldSpec("name", "string", required=True),
        FieldSpec(
            "data",
            "array",
            required=True,
            item_kind="point",
            min_items=1,
            description="The values to plot, as [x, y] pairs. Data, not coordinates.",
        ),
        _role(NODE_ROLES, "step"),
    ),
}

_VERSION_REQUIRED: Final = (
    "'version' is required. Declare it so a future format change is a loud failure "
    "rather than a misread document."
)


#: Fields every document carries, whatever its kind.
COMMON_FIELDS: Final = (
    FieldSpec(
        "$schema",
        "string",
        description="Optional, and only for editors: the URL of this schema.",
    ),
    FieldSpec("version", "integer", required=True, description=_VERSION_REQUIRED),
    FieldSpec("kind", "string", required=True, enum=KINDS),
    FieldSpec("title", "string", description="The diagram's accessible name."),
    FieldSpec("description", "string", description="The diagram's accessible description."),
    FieldSpec(
        "width",
        "number",
        exclusive_minimum=0,
        description="Overrides the theme's canvas width. Binding.",
    ),
    FieldSpec(
        "height",
        "number",
        exclusive_minimum=0,
        description="Advisory unless height_binding is true.",
    ),
    FieldSpec(
        "height_binding",
        "boolean",
        description="Makes height a constraint rather than a hint.",
    ),
    FieldSpec("theme", "string", description="A bundled theme name or the path of a theme file."),
)

#: The payload fields each kind family adds. The kind selects the family, and
#: the family selects which further fields are legal.
KIND_PAYLOADS: Final[Mapping[tuple[str, ...], tuple[FieldSpec, ...]]] = {
    GRAPH_KINDS: (
        FieldSpec("nodes", "array", required=True, item_ref="node", min_items=1),
        FieldSpec("edges", "array", item_ref="edge"),
        FieldSpec("groups", "array", item_ref="group"),
    ),
    GRID_KINDS: (FieldSpec("items", "array", required=True, item_ref="item", min_items=1),),
    ("pyramid",): (FieldSpec("levels", "array", required=True, item_ref="level", min_items=1),),
    ("rings",): (FieldSpec("rings", "array", required=True, item_ref="ring", min_items=1),),
    CHART_KINDS: (
        FieldSpec("axes", "object", required=True, ref="axes"),
        FieldSpec("series", "array", required=True, item_ref="series", min_items=1),
    ),
}


def payload_for(kind: str) -> tuple[FieldSpec, ...]:
    """The payload fields legal for `kind`."""
    for kinds, fields in KIND_PAYLOADS.items():
        if kind in kinds:
            return fields
    raise KeyError(kind)


def fields_for(kind: str) -> tuple[FieldSpec, ...]:
    """Every field legal for `kind` — common plus payload."""
    return COMMON_FIELDS + payload_for(kind)


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    id: str
    text: str
    role: str = "step"
    note: str = ""


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""
    role: str = "flow"


@dataclass(frozen=True)
class Group:
    id: str
    members: tuple[str, ...]
    text: str = ""


@dataclass(frozen=True)
class Item:
    text: str
    id: str = ""
    role: str = "step"
    note: str = ""


@dataclass(frozen=True)
class Axis:
    label: str
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class Series:
    name: str
    data: tuple[tuple[float, float], ...]
    role: str = "step"


@dataclass(frozen=True)
class Document:
    """A validated document. Every field the author may write, and none they may not."""

    kind: str
    version: int = DOCUMENT_VERSION
    title: str = ""
    description: str = ""
    width: float | None = None
    height: float | None = None
    height_binding: bool = False
    theme: str = ""
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    groups: tuple[Group, ...] = ()
    items: tuple[Item, ...] = ()
    levels: tuple[Item, ...] = ()
    rings: tuple[Item, ...] = ()
    axes: tuple[Axis, ...] = ()
    """The horizontal axis then the vertical one, for `chart`. Empty otherwise."""

    series: tuple[Series, ...] = ()

    @property
    def family(self) -> str:
        """Which rendering family this document's kind belongs to."""
        for name, kinds in (
            ("graph", GRAPH_KINDS),
            ("grid", GRID_KINDS),
            ("shape", SHAPE_KINDS),
            ("chart", CHART_KINDS),
        ):
            if self.kind in kinds:
                return name
        raise KeyError(self.kind)


# ---------------------------------------------------------------------------
# Violations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """One validation failure, located by JSON pointer."""

    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer or '/'}: {self.message}"


def _escape(part: object) -> str:
    """One JSON pointer token, escaped as RFC 6901 requires."""
    return str(part).replace("~", "~0").replace("/", "~1")


def _pointer(*parts: object) -> str:
    """A JSON pointer, with the escaping RFC 6901 asks for."""
    return "".join("/" + _escape(part) for part in parts if part != "")


def _unknown_field_message(name: str, legal: Sequence[str]) -> str:
    reason = REJECTED_FIELDS.get(name)
    if reason:
        return (
            f"{name!r} is not a field an author may write: {reason}. Every decision "
            f"that requires seeing the output is taken by drawspec."
        )
    return f"{name!r} is not a known field here. Known fields: {', '.join(sorted(legal))}."


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_JSON_TYPES: Final[dict[str, type | tuple[type, ...]]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_type(value: object, spec: FieldSpec, pointer: str, found: list[Violation]) -> bool:
    expected = _JSON_TYPES[spec.kind]
    # `True` is an `int` in Python but not a number in JSON, and a document that
    # says `width = true` should hear about it.
    if isinstance(value, bool) is not (spec.kind == "boolean"):
        found.append(Violation(pointer, f"expected {spec.kind}, got {type(value).__name__}"))
        return False
    if not isinstance(value, expected):
        found.append(Violation(pointer, f"expected {spec.kind}, got {type(value).__name__}"))
        return False
    return True


def _check_field(value: object, spec: FieldSpec, pointer: str, found: list[Violation]) -> None:
    if not _check_type(value, spec, pointer, found):
        return

    if spec.enum and value not in spec.enum:
        found.append(
            Violation(
                pointer,
                f"{value!r} is not one of {', '.join(spec.enum)}. The vocabulary is "
                f"closed, so a role the theme does not declare cannot be named.",
            )
        )
    if spec.exclusive_minimum is not None and float(value) <= spec.exclusive_minimum:  # type: ignore[arg-type]
        found.append(Violation(pointer, f"must be greater than {spec.exclusive_minimum}"))

    if spec.kind == "object" and spec.ref:
        _check_object(value, OBJECTS[spec.ref], pointer, found)  # type: ignore[arg-type]

    if spec.kind == "array":
        elements: list[Any] = value  # type: ignore[assignment]
        if len(elements) < spec.min_items:
            found.append(
                Violation(
                    pointer,
                    f"needs at least {spec.min_items} entr"
                    f"{'y' if spec.min_items == 1 else 'ies'}, got {len(elements)}",
                )
            )
        for index, element in enumerate(elements):
            where = f"{pointer}/{index}"
            if spec.item_ref:
                if not isinstance(element, dict):
                    found.append(Violation(where, f"expected object, got {type(element).__name__}"))
                    continue
                _check_object(element, OBJECTS[spec.item_ref], where, found)
            elif spec.item_kind == "string" and not isinstance(element, str):
                found.append(Violation(where, f"expected string, got {type(element).__name__}"))
            elif spec.item_kind == "point":
                _check_point(element, where, found)


def _check_point(element: object, pointer: str, found: list[Violation]) -> None:
    numbers = (
        isinstance(element, list)
        and len(element) == 2
        and all(isinstance(value, int | float) and not isinstance(value, bool) for value in element)
    )
    if not numbers:
        found.append(Violation(pointer, "expected a pair of numbers, [x, y]"))


def _check_object(
    mapping: Mapping[str, Any],
    specs: Sequence[FieldSpec],
    pointer: str,
    found: list[Violation],
) -> None:
    legal = {spec.name for spec in specs}
    for name in sorted(set(mapping) - legal):
        found.append(
            Violation(f"{pointer}/{_escape(name)}", _unknown_field_message(name, sorted(legal)))
        )
    for spec in specs:
        if spec.name not in mapping:
            if spec.required:
                found.append(
                    Violation(f"{pointer}/{_escape(spec.name)}", f"{spec.name!r} is required")
                )
            continue
        _check_field(mapping[spec.name], spec, f"{pointer}/{_escape(spec.name)}", found)


def validate_document(document: Mapping[str, Any]) -> tuple[Violation, ...]:
    """Every structural and referential violation in `document`, each located.

    Returns all of them rather than stopping at the first, so `drawspec validate`
    can print a document's whole story in one pass.
    """
    found: list[Violation] = []
    kind = document.get("kind")

    if not isinstance(kind, str) or kind not in KINDS:
        # Without a kind there is no way to know which payload fields are legal,
        # so reporting them would be a page of violations about the wrong thing.
        found.append(
            Violation(
                "/kind",
                "'kind' is required"
                if kind is None
                else f"{kind!r} is not one of {', '.join(KINDS)}. The nine kinds are "
                f"closed for v1: a tenth needs evidence.",
            )
        )
        if "version" not in document:
            found.append(Violation("/version", _VERSION_REQUIRED))
        return tuple(found)

    _check_object(document, fields_for(kind), "", found)

    version = document.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version != DOCUMENT_VERSION:
        found.append(
            Violation(
                "/version",
                f"version {version!r} is not supported; this drawspec reads version "
                f"{DOCUMENT_VERSION}. A change of meaning ships as v2, with both "
                f"readable in parallel for at least one release.",
            )
        )

    found.extend(_referential_violations(document, kind))
    return tuple(found)


def _referential_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """The checks JSON Schema cannot express: unique ids, and edges that land."""
    found: list[Violation] = []
    if kind not in GRAPH_KINDS:
        return found

    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        return found

    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        identifier = node.get("id")
        if not isinstance(identifier, str):
            continue
        if identifier in seen:
            found.append(
                Violation(_pointer("nodes", index, "id"), f"duplicate node id {identifier!r}")
            )
        seen.add(identifier)

    edges = document.get("edges")
    if isinstance(edges, list):
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            for end in ("from", "to"):
                target = edge.get(end)
                if isinstance(target, str) and target not in seen:
                    found.append(
                        Violation(
                            _pointer("edges", index, end),
                            f"{target!r} is not the id of any node in this document",
                        )
                    )

    groups = document.get("groups")
    if isinstance(groups, list):
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            members = group.get("members")
            if not isinstance(members, list):
                continue
            for position, member in enumerate(members):
                if isinstance(member, str) and member not in seen:
                    found.append(
                        Violation(
                            _pointer("groups", index, "members", position),
                            f"{member!r} is not the id of any node in this document",
                        )
                    )
    return found


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_document(document: Mapping[str, Any]) -> Document:
    """Validate `document` and build the model.

    Raises:
        DocumentError: carrying every violation, each with its JSON pointer.
    """
    if not isinstance(document, Mapping):
        raise DocumentError("a document must be a mapping", ())
    violations = validate_document(document)
    if violations:
        raise DocumentError(_describe(violations), violations)

    kind = str(document["kind"])
    return Document(
        kind=kind,
        version=DOCUMENT_VERSION,
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        nodes=tuple(
            Node(
                id=entry["id"],
                text=entry["text"],
                role=entry.get("role", "step"),
                note=entry.get("note", ""),
            )
            for entry in document.get("nodes", ())
        ),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
            )
            for entry in document.get("edges", ())
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
        items=_items(document.get("items", ())),
        levels=_items(document.get("levels", ())),
        rings=_items(document.get("rings", ())),
        axes=_axes(document.get("axes")),
        series=tuple(
            Series(
                name=entry["name"],
                data=tuple((float(x), float(y)) for x, y in entry["data"]),
                role=entry.get("role", "step"),
            )
            for entry in document.get("series", ())
        ),
    )


def _items(entries: Sequence[Mapping[str, Any]]) -> tuple[Item, ...]:
    return tuple(
        Item(
            text=entry["text"],
            id=entry.get("id", ""),
            role=entry.get("role", "step"),
            note=entry.get("note", ""),
        )
        for entry in entries
    )


def _axes(entry: Mapping[str, Any] | None) -> tuple[Axis, ...]:
    """The horizontal axis then the vertical one. Ordered, for determinism."""
    if entry is None:
        return ()
    return tuple(_axis(entry[name]) for name in AXIS_ORDER)


def _axis(entry: Mapping[str, Any]) -> Axis:
    return Axis(
        label=entry["label"],
        unit=entry.get("unit", ""),
        minimum=_optional_number(entry.get("min")),
        maximum=_optional_number(entry.get("max")),
    )


def _optional_number(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _describe(violations: Sequence[Violation]) -> str:
    heading = f"{len(violations)} violation{'s' if len(violations) > 1 else ''} in this document"
    return heading + ":\n" + "\n".join(f"  {violation}" for violation in violations)


def load_document(path: str | Path) -> Document:
    """Read and validate a JSON document from `path`."""
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as error:
        raise DocumentError(f"document could not be read: {location} ({error})", ()) from None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise DocumentError(f"document is not valid JSON: {location} ({error})", ()) from None
    return parse_document(parsed)


# ---------------------------------------------------------------------------
# The published schema
# ---------------------------------------------------------------------------


def _field_schema(spec: FieldSpec) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    if spec.kind == "object" and spec.ref:
        schema["$ref"] = f"#/$defs/{spec.ref}"
        if spec.description:
            schema["description"] = spec.description
        return schema

    schema["type"] = spec.kind
    if spec.description:
        schema["description"] = spec.description
    if spec.enum:
        schema["enum"] = list(spec.enum)
    if spec.exclusive_minimum is not None:
        schema["exclusiveMinimum"] = spec.exclusive_minimum
    if spec.kind == "array":
        if spec.item_ref:
            schema["items"] = {"$ref": f"#/$defs/{spec.item_ref}"}
        elif spec.item_kind == "point":
            schema["items"] = {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            }
        elif spec.item_kind:
            schema["items"] = {"type": spec.item_kind}
        if spec.min_items:
            schema["minItems"] = spec.min_items
    return schema


def _object_schema(specs: Sequence[FieldSpec], *, title: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object"}
    if title:
        schema["title"] = title
    schema["properties"] = {spec.name: _field_schema(spec) for spec in specs}
    required = [spec.name for spec in specs if spec.required]
    if required:
        schema["required"] = required
    # The load-bearing line: a forbidden field fails by name rather than being
    # silently absorbed, which is what makes the schema teach.
    schema["additionalProperties"] = False
    return schema


def build_schema() -> dict[str, Any]:
    """Render the field tables above as a JSON Schema document.

    Generated rather than hand-written, so the published artefact and the runtime
    validator cannot disagree. Referential checks (unique ids, edges that land on
    a real node) are outside JSON Schema's reach and are documented as such
    rather than silently missing.
    """
    variants = []
    for kinds in KIND_PAYLOADS:
        specs = list(COMMON_FIELDS + KIND_PAYLOADS[kinds])
        variant = _object_schema(specs, title=" / ".join(kinds))
        variant["properties"]["kind"] = {"type": "string", "enum": list(kinds)}
        variant["properties"]["version"] = {"const": DOCUMENT_VERSION}
        variants.append(variant)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "drawspec document, version 1",
        "description": (
            "A declarative diagram. The author describes what the diagram means; every "
            "decision that requires seeing the output — coordinates, type size, colour, "
            "arrow-head geometry, z-order — is taken by drawspec and has no field here. "
            "Referential rules (node ids are unique; an edge names nodes that exist) are "
            "beyond JSON Schema and are enforced by `drawspec validate`."
        ),
        "oneOf": variants,
        "$defs": {name: _object_schema(specs) for name, specs in sorted(OBJECTS.items())},
    }


def schema_json() -> str:
    """The published schema as the committed file spells it."""
    return json.dumps(build_schema(), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def published_schema_path() -> Path:
    """The committed schema artefact on disk.

    One file, two places it can be: inside an installed wheel, or at
    `schema/<name>` in a source checkout, which is where it is committed and
    where the wheel copies it from. Never two files, because two files drift.

    Raises:
        FileNotFoundError: neither location has it.
    """
    packaged = Path(__file__).resolve().parent / "schemas" / SCHEMA_FILENAME
    if packaged.is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILENAME
    if checkout.is_file():
        return checkout
    raise FileNotFoundError(
        f"{SCHEMA_FILENAME} is neither packaged nor in a source checkout; "
        f"regenerate it with `python -m drawspec.schema`"
    )


def main() -> int:
    """Write the schema to its committed location. Run by `make schema` and CI."""
    destination = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(schema_json(), encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AXIS_ORDER",
    "CHART_KINDS",
    "COMMON_FIELDS",
    "DOCUMENT_VERSION",
    "GRAPH_KINDS",
    "GRID_KINDS",
    "KINDS",
    "OBJECTS",
    "REJECTED_FIELDS",
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "SHAPE_KINDS",
    "Axis",
    "Document",
    "Edge",
    "FieldSpec",
    "Group",
    "Item",
    "Node",
    "Series",
    "Violation",
    "build_schema",
    "fields_for",
    "load_document",
    "parse_document",
    "payload_for",
    "published_schema_path",
    "schema_json",
    "validate_document",
]
