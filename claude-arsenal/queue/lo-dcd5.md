# T1: Scene primitives, SVG emitter with both embedding profiles, and the embedding-safety validator

Plan row: `T1` in `status/plan.md`. Size: M.
Specification: `status/specification.md`.

## Acceptance gate

`embedding_safety_violations == 0`

Every emitted SVG passes the safety validator in BOTH profiles, measured per profile rather than summed: no <style> element, every id prefixed with the document namespace, no embedded or referenced font, no fill/stroke literal outside the theme's declared values, and for `standalone` no unresolved currentColor.

```bash
uv run pytest tests/test_emit.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_emit_any_scene_produces_no_style_element` — emitted SVG contains no <style> element, in either profile.
`test_emit_two_documents_on_one_page_produces_no_duplicate_ids` — concatenating two renders yields no repeated id.
`test_emit_inline_profile_strokes_use_currentcolor` — the inline profile inherits colour.
`test_emit_standalone_profile_leaves_no_unresolved_currentcolor` — the standalone profile resolves every colour and carries explicit width/height.
`test_emit_scene_with_undeclared_role_raises_error` — a primitive tagged with a role the theme does not declare raises.
`test_emit_same_scene_twice_produces_identical_bytes` — two emissions are byte-equal.

## Location

`src/drawspec/scene.py`, `src/drawspec/emit.py`, `tests/test_emit.py`
