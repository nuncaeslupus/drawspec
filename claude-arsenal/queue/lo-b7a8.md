# T6: Box geometry from measured text, vertical centring, rank normalisation, elastic fit

Plan row: `T6` in `status/plan.md`. Size: M.
Specification: `status/specification.md`.

## Acceptance gate

`text_overflow_count == 0`

Text extents sit inside the box inset by the theme padding on all four sides, bottom included — the single most repeated failure in the source review. Vertical centring is computed from ascent/descent, not approximated. Elastic fit applies ONE uniform scale factor to every type level at once: scaling levels independently would reintroduce the corpus's most common failure (51 of 87 diagrams mixed type sizes). Content that will not fit at scale_min, or that falls below the theme's min_legible_size, raises FitError — the tool says restructure, it does not keep shrinking.

```bash
uv run pytest tests/test_box.py -q
uv run ruff check .
uv run mypy .
```

## Tests

Write these RED first, before any production code.

`test_box_contains_its_text_with_full_padding_on_all_four_sides`.
`test_box_text_is_vertically_centred_within_half_a_pixel`.
`test_fit_applies_one_scale_factor_to_every_type_level` — ratios between title, heading, body and label are unchanged after scaling.
`test_fit_chooses_the_largest_factor_that_fits_within_the_band`.
`test_fit_below_scale_min_or_min_legible_size_raises_fiterror`.
`test_boxes_of_the_same_rank_are_normalised_to_equal_size`.

## Location

`src/drawspec/geometry.py`, `tests/test_box.py`
