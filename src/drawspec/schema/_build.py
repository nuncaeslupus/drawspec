"""The published JSON Schema, rendered from the field tables."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from drawspec.schema._checks import MAX_NUMBER, MAX_TEXT_LENGTH
from drawspec.schema._constants import (
    DOCUMENT_VERSION,
    EMPHASIS_CAP,
    KINDS,
    READABILITY_BUDGET,
    SCHEMA_FILENAME,
    SCHEMA_ID,
)
from drawspec.schema._fields import COMMON_FIELDS, OBJECTS, FieldSpec, payload_for


def _beside(theme: str, location: Path) -> str:
    """A relative theme path, read from the document's folder when the file is there.

    A theme beside its diagrams is the natural layout — a derived brand theme
    next to the documents that use it — and a path that only worked from one
    working directory is a document that renders in one build and not another.
    A bundled name, an absolute path, or a file that is not beside the document
    is left as written, so nothing that resolved before resolves differently.
    """
    if not theme or not theme.endswith(".toml") or Path(theme).is_absolute():
        return theme
    beside = location.parent / theme
    return str(beside) if beside.is_file() else theme


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
    if spec.kind in ("number", "integer"):
        schema["minimum"] = -MAX_NUMBER
        schema["maximum"] = MAX_NUMBER
    if spec.kind == "string":
        schema["maxLength"] = MAX_TEXT_LENGTH
    if spec.kind == "array":
        if spec.item_ref:
            schema["items"] = {"$ref": f"#/$defs/{spec.item_ref}"}
        elif spec.item_kind == "point":
            schema["items"] = {
                "type": "array",
                "items": {"type": "number", "minimum": -MAX_NUMBER, "maximum": MAX_NUMBER},
                "minItems": 2,
                "maxItems": 2,
            }
        elif spec.item_kind:
            schema["items"] = {"type": spec.item_kind}
            if spec.item_kind == "string":
                schema["items"]["maxLength"] = MAX_TEXT_LENGTH
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


def _published_budgets(kinds: Sequence[str]) -> dict[str, int]:
    """The readability budgets a JSON Schema can state: one top-level array, one limit.

    Nested, per-cell, deep and per-role budgets, and `tree` nodes (a bracket counts
    its leaves instead), are left to the validator. Kinds sharing a variant may
    differ, so the loosest limit is published and only when every kind has one:
    the schema may pass what the validator refuses, never the reverse.
    """
    limits: dict[str, list[int]] = {}
    for kind in kinds:
        for name, limit in READABILITY_BUDGET.get(kind, ()):
            if name.isidentifier() and not (kind == "tree" and name == "nodes"):
                limits.setdefault(name, []).append(limit)
    return {name: max(found) for name, found in limits.items() if len(found) == len(kinds)}


def build_schema() -> dict[str, Any]:
    """Render the field tables above as a JSON Schema document.

    Generated rather than hand-written, so the published artefact and the runtime
    validator cannot disagree. Referential checks (unique ids, edges that land on
    a real node) are outside JSON Schema's reach and are documented as such
    rather than silently missing.
    """
    # One branch per *set of legal fields*, not per entry in the table above: a
    # kind may draw its fields from more than one entry — `timeline` takes
    # `items` with the other grid kinds and `spans` on its own — and a kind
    # appearing in two branches would match both, which `oneOf` reads as invalid.
    # Grouped by the full field tuple, not just names: `quadrant` and `scatter`
    # both take `axes` + `positions`, but with different descriptions for what
    # those mean, and merging on name alone silently dropped one kind's prose.
    grouped: dict[tuple[FieldSpec, ...], list[str]] = {}
    for kind in KINDS:
        grouped.setdefault(payload_for(kind), []).append(kind)

    variants = []
    for specs_for_kind, kinds in grouped.items():
        specs = list(COMMON_FIELDS) + list(specs_for_kind)
        variant = _object_schema(specs, title=" / ".join(kinds))
        for name, limit in _published_budgets(kinds).items():
            if variant["properties"].get(name, {}).get("type") == "array":
                variant["properties"][name]["maxItems"] = limit
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
            "beyond JSON Schema and are enforced by `drawspec validate`. So are the "
            "readability budgets this schema cannot state (those on nested, per-role or "
            "per-cell counts; a plain top-level array's limit is its `maxItems`), the "
            f"cap of {EMPHASIS_CAP} elements with the 'emphasis' role, text-length and "
            "fit limits, and the theme-file rules: a document that passes this schema "
            "can still be refused, so validate before rendering (docs/format.md)."
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
    packaged = Path(__file__).resolve().parent.parent / "schemas" / SCHEMA_FILENAME
    if packaged.is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[3] / "schema" / SCHEMA_FILENAME
    if checkout.is_file():
        return checkout
    raise FileNotFoundError(
        f"{SCHEMA_FILENAME} is neither packaged nor in a source checkout; "
        f"regenerate it with `python -m drawspec.schema`"
    )


def main() -> int:
    """Write the schema to its committed location. Run by `make schema` and CI."""
    destination = Path(__file__).resolve().parents[3] / "schema" / SCHEMA_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(schema_json(), encoding="utf-8")
    print(destination)
    return 0
