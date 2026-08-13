# G1: group — a box that contains boxes

Six of the 89 originals need a container: a box drawn around other boxes, with
its own caption, nestable, and edges that cross its boundary.

## Acceptance gate
A `flow` document whose node carries children renders the children inside the
parent's outline, the parent's caption clear of them, and every edge that ends
on a child reaching the child rather than the container. No child crosses its
parent's border. `make lint` and `make test` clean.

```bash
uv run pytest tests/test_kinds_graph.py -q && uv run ruff check . && uv run mypy .
```

## Location
`src/drawspec/kinds/graph.py`, `src/drawspec/schema.py`, `src/drawspec/routing.py`.

## Notes
See `docs/kinds-wanted.md` §1. This is probably a property of a node rather than
a new kind — decide that first.
