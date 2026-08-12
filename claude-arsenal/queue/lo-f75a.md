# T13: Shape kinds — pyramid, concentric rings

Plan row: `T13` in `status/plan.md`. Size: M.
Specification: `status/specification.md`.

## Acceptance gate

`text_outside_shape_count == 0`

Pyramid levels are equal height with a constant width progression, and each level's text fits the NARROWEST span of that level, so it never crosses a sloped side. Ring labels are offset below their own arc so they do not touch it; only the innermost label is centred.

```bash
uv run pytest tests/test_kinds_shape.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_pyramid_levels_are_equal_height_with_constant_width_progression`.
`test_pyramid_level_text_fits_the_narrowest_span_of_its_level`.
`test_ring_label_is_offset_below_its_own_arc`.
`test_innermost_ring_label_is_centred`.

## Location

`src/drawspec/kinds/shape.py`, `tests/test_kinds_shape.py`. Geometry, not graph theory. Contract: docs/theme-requirements.md section 6.
