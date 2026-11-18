---
id: lo-9dd6
title: "T10: Edge label placement with overlap avoidance"
priority: 5
deps: [lo-7bfe]
tags: [drawspec]
status: done
pr: https://github.com/nuncaeslupus/drawspec/pull/13
---

Plan row: `T10` in `status/plan.md`. Size: M.
Specification: `status/specification.md`.

## Acceptance gate

`label_overlap_count == 0`

No edge label box intersects any edge path, any node box, or any other label. Where the default position is occupied, a fallback offset is chosen rather than overlapping.

```bash
uv run pytest tests/test_labels.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_edge_label_does_not_intersect_any_edge_path`.
`test_edge_label_does_not_intersect_any_node_box`.
`test_edge_label_offsets_when_the_default_position_is_occupied`.

## Location

`src/drawspec/routing.py`, `tests/test_labels.py`
