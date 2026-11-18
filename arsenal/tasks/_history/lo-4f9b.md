---
id: lo-4f9b
title: "T2: Theme dataclass, TOML loader, node and edge role vocabularies, elastic-fit band, greyscale invariant"
priority: 5
tags: [drawspec]
status: done
pr: https://github.com/nuncaeslupus/drawspec/pull/2
---

Plan row: `T2` in `status/plan.md`. Size: M.
Specification: `status/specification.md`.

## Acceptance gate

`greyscale_ambiguous_role_pairs == 0`

A theme fails to load if any two roles are distinguishable only by colour — they must differ in at least one non-colour channel (shape, dash, stroke weight, fill pattern) or by a relative-luminance delta >= 0.25. The bundled default theme passes its own invariant.

```bash
uv run pytest tests/test_theme.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_theme_roles_differing_only_by_colour_raises_themeerror` — identical shape/dash/weight with a luminance delta below 0.25 is rejected.
`test_theme_roles_differing_by_dash_pattern_loads_successfully` — a non-colour channel difference is accepted.
`test_theme_edge_role_with_head_none_loads_and_renders_a_plain_line` — a headless connector is expressible.
`test_theme_edge_role_head_outside_vocabulary_raises_themeerror` — the head vocabulary (arrow, open, diamond, circle, bar, none) is closed.
`test_bundled_default_theme_loads_without_violations` — the shipped theme passes.

## Location

`src/drawspec/theme.py`, `src/drawspec/themes/default.toml`, `tests/test_theme.py`. Contract: specification.md section 5.2.
