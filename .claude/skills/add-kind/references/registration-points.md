# Registration points

Load when wiring a new kind into the code, or when `audit_kind.py` names a
missing piece and the fix is not obvious. Each row is a file, the symbol to add
to, and what goes there. `<kind>` is the kind's name, `<KIND>` its constant
prefix (`NEURALNET`).

## Contents

- [Schema](#schema)
- [Rendering and registration](#rendering-and-registration)
- [Tests and references](#tests-and-references)
- [Generated files](#generated-files)
- [Prose documents](#prose-documents)

## Schema

All in `src/drawspec/schema.py`.

| Symbol | What to add |
|---|---|
| `<KIND>_KINDS: Final = ("<kind>",)` and limits | The family constant, then the budget limits, each with a comment saying where the number came from |
| `KINDS` comment and tuple | A `#:` line saying how the kind differs from its nearest sibling, and `+ <KIND>_KINDS` |
| `READABILITY_BUDGET` | `"<kind>": (("<array>", <MAX>), ...)`, with the evidence in a comment |
| `OBJECTS` | One entry per nested object (`"<kind>-layer"`). A nested object never refers back to its parent's object: give the child its own small object, or validation recurses |
| `KIND_PAYLOADS` | `<KIND>_KINDS: (FieldSpec(...), ...)`, each field with a description an author can act on |
| Dataclasses | One frozen dataclass per object, before `class Document` |
| `Document` fields | `<kind>_...` fields with defaults, and the `("<kind>", <KIND>_KINDS)` row in `Document.family` |
| `validate_document` | `if kind in <KIND>_KINDS: found = [_<kind>_refusal(v) for v in found]` |
| `BUDGET_ADVICE` | One `("<kind>", "<array>")` entry per budgeted array: what to split, and how |
| `_referential_violations` | `if kind in <KIND>_KINDS: return _<kind>_violations(document)` |
| `<KIND>_REFUSED`, `_<kind>_refusal`, `_<kind>_violations` | Fields an author reaches for, each with the reason; then every rule the field tables cannot express, each at its JSON pointer |
| Parse dispatch and builder | `if kind in <KIND>_KINDS: return _<kind>_document(document)`, and the builder |
| Kind enum description | The count of kinds in words, in `Which of the <count> diagrams` |
| `__all__` | Every new public constant and dataclass, sorted |

## Rendering and registration

| File | What to add |
|---|---|
| `src/drawspec/kinds/<kind>.py` | `<kind>_scene(document, theme, measurer) -> Scene`; `<kind>_text(document, width, charset) -> str` when the kind has a text form |
| `src/drawspec/kinds/__init__.py` | The import, `*<KIND>_KINDS` in `IMPLEMENTED`, `"<kind>": <kind>_text` in `TEXT_FORMS`, the `_drawn` dispatch, `__all__` |
| `src/drawspec/examples.py` | A `PURPOSE` line and the smallest `EXAMPLES` document that renders |
| `tools/gallery.py` | `"<kind>"` in `KIND_ORDER`, beside its siblings |
| `src/drawspec/textgrid.py`, `cli.py`, `mcp.py` | Only for a text form wider than 80 columns: `WIDE_KINDS` and the two help strings that name those kinds |

## Tests and references

| File | What to add |
|---|---|
| `docs/reference/<kind>-<name>.json` | Three or more documents, one per original figure, each valid and clean |
| `tests/test_kinds_<kind>.py` | Every reference renders clean (`collisions`, `clipped`), the promises in the module docstring, every refusal at its pointer, the budget |
| `tests/test_text_output.py` | `GOLDENS`, `MORE_GOLDENS` and the `_labels` branch, for a text form |
| `tests/golden/text/` | Written by `DRAWSPEC_UPDATE_GOLDEN=1 uv run pytest tests/test_text_output.py -k <kind>`, read before committing |

## Generated files

| Command | Writes |
|---|---|
| `make schema` | `schema/drawspec-v1.schema.json` |
| `make docs` | `docs/format.md`, `docs/cli.md`, `docs/theme.md` |
| `make gallery` | `docs/gallery/<reference>.svg` and `docs/gallery/index.html` |

## Prose documents

| File | What to change |
|---|---|
| `README.md` | The kind in the full list under the gallery table; "more than N kinds" only when N passes a ten |
| `docs/guide.md` | The family table row, the count sentence ("<Count> exist, …"), the text-form paragraph, and a section with one example |
| `AGENTS.md` | The kind-table row: when to use it, its fields, its text form |
| `llms.txt` | The count of kinds in words, and the text-form list |
| `CHANGELOG.md` | An `Unreleased` entry: what it draws, what it refuses, the references |
| `docs/proposals/<kind>.md` | The originals (at least two, with what was and was not opened), the decisions, the owner's questions |
| `docs/proposals/README.md` | The table row, and the count in the "decisions" note |
