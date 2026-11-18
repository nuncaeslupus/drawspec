---
id: lo-b94c
title: "T3: Text measurement from font files via fonttools, with replace-and-warn substitution"
priority: 1
tags: [drawspec]
status: done
pr: https://github.com/nuncaeslupus/drawspec/pull/2
---

Plan row: `T3` in `status/plan.md`. Size: L.
Specification: `status/specification.md`.

## Acceptance gate

`text_measurement_error_ratio <= 0.02`

Measured advance widths for a reference string set agree within 2% with the value computed from the font's own hmtx/kern tables by an independent reader. Works for a font never seen before — metrics come from the file, never a hardcoded table. An unresolvable font substitutes a bundled generic serif/sans/mono, measures against the substitute, and warns naming both families. It never substitutes silently and never fails on this alone.

```bash
uv run pytest tests/test_measure.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_measure_reference_strings_match_font_tables_within_two_percent` — agrees with an independent hmtx reader.
`test_measure_previously_unseen_font_returns_metrics` — a font absent from any bundled table measures correctly.
`test_measure_unresolvable_font_substitutes_and_warns` — emits FontSubstitutionWarning naming requested and substituted families.
`test_measure_kerned_pair_differs_from_sum_of_advances` — kerning is applied.

## Location

`src/drawspec/text/measure.py`, `src/drawspec/fonts/`, `tests/test_measure.py`. Critical path — everything downstream depends on this.
