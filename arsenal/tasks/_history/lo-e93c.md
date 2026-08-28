---
id: lo-e93c
title: "T8: The chosen default layout engine behind the protocol"
priority: 1
deps: [lo-4c51]
tags: [drawspec]
status: done
pr: https://github.com/nuncaeslupus/drawspec/pull/4
---

Plan row: `T8` in `status/plan.md`. Size: L.
Specification: `status/specification.md`.

## Acceptance gate

`node_overlap_count == 0`

No two node boxes intersect. Rank increases with depth in a tree. A cyclic graph terminates rather than looping. Identical input yields identical positions, since determinism is a success criterion.

```bash
uv run pytest tests/test_layout.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_layout_returns_positions_with_no_overlapping_boxes`.
`test_layout_of_a_tree_places_children_after_their_parent`.
`test_layout_of_a_cyclic_graph_terminates_and_returns_positions`.
`test_layout_is_deterministic_across_runs`.

## Location

`src/drawspec/layout/`, `tests/test_layout.py`
