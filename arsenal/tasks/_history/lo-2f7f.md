---
id: lo-2f7f
title: "T12: Grid kinds — stack, timeline, columns"
priority: 5
deps: [lo-dcd5, lo-1c47, lo-b7a8]
tags: [drawspec]
status: done
pr: https://github.com/nuncaeslupus/drawspec/pull/5
---

Plan row: `T12` in `status/plan.md`. Size: M.
Specification: `status/specification.md`.

## Acceptance gate

`same_rank_size_variance == 0`

These kinds have no routing problem: positions come from counting. Layers are equal height and full width; columns of the same role are equal width; timeline ticks are evenly spaced.

```bash
uv run pytest tests/test_kinds_grid.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_stack_layers_are_equal_height_and_full_width`.
`test_columns_of_the_same_role_are_equal_width`.
`test_timeline_ticks_are_evenly_spaced`.

## Location

`src/drawspec/kinds/grid.py`, `tests/test_kinds_grid.py`
