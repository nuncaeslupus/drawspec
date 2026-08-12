# T9: Orthogonal edge routing with border anchoring and minimum shaft length

Plan row: `T9` in `status/plan.md`. Size: L.
Specification: `status/specification.md`.

## Acceptance gate

`edge_anchor_violations == 0`

Every edge starts and ends exactly on a node border — neither short nor overshooting — which is what makes 'line that does not touch the box' and 'arrow with only a head' unrepresentable rather than merely unlikely. All segments are axis-aligned; no route crosses a node box; every shaft is at least the theme's minimum length.

```bash
uv run pytest tests/test_routing.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_route_endpoints_lie_exactly_on_node_borders`.
`test_route_produces_only_axis_aligned_segments`.
`test_route_shaft_length_is_at_least_the_theme_minimum`.
`test_route_does_not_cross_any_node_box`.

## Location

`src/drawspec/routing.py`, `tests/test_routing.py`
