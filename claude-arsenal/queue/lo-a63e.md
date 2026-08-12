# T6b: Diamond and ellipse usable span from the text's own height

Found while reviewing T7's rendered output (see PR discussion). Not a defect —
the current geometry is correct — but it costs about 30% of a decision node's
width for no benefit, which is visible in every flow diagram.

## What is happening

`geometry.usable_span` gives a diamond its largest inscribed rectangle: half the
width, half the height. That is the conservative reading, and it is correct in
the sense that text inside it can never cross a sloped side. But it is the same
over-conservatism that was already fixed for `pill`: text only reaches the
narrow part of a shape if it is as tall as the shape.

For a diamond of width `W` and height `H` holding a text block of height `h`
centred, the usable width at the text's vertical extremes is `W * (1 - h / H)`,
not `W / 2`. The two agree only when `h == H / 2`.

Measured on the `flow-validation` reference document, node `shape`
("Is the payload well formed?"):

| Model | Box |
|---|---|
| Current (max-area inscribed rectangle) | 254.3 x 103.4 |
| Exact, at the same height | ~178 x 103.4 |
| The same text as a `step` rect | 175.9 x 36.9 |

An ellipse has the same structure: the usable half-width at vertical offset `t`
is `rx * sqrt(1 - (t / ry)^2)`, so the width available to text of height `h` is
`W * sqrt(1 - (h / H)^2)` rather than `W / sqrt(2)`.

## Acceptance gate

`text_overflow_count == 0` — unchanged, but now measured against the *real*
outlines rather than the inscribed rectangles, exactly as
`test_diamond_text_stays_inside_the_sloped_sides` and
`test_pill_text_stays_inside_the_outline_including_the_caps` already do.

A decision node holding a two-line label must come out materially narrower than
it does today, and every corner of its text must still satisfy
`|dx| / rx + |dy| / ry <= 1`.

```bash
uv run pytest tests/test_box.py -q
uv run ruff check .
uv run mypy .
```

## Tests

`test_diamond_usable_width_grows_as_its_text_gets_shorter` — the span is a
function of the content height, not a fixed fraction.
`test_diamond_holding_a_two_line_label_is_narrower_than_the_inscribed_rectangle_model`.
`test_ellipse_text_stays_inside_the_curve` — every text corner satisfies the
ellipse inequality.
Keep `test_outer_size_and_usable_span_are_inverses` passing for all four shapes;
`outer_size` has to be solved for the same model, as it was for `pill`.

## Location

`src/drawspec/geometry.py` (`usable_span`, `outer_size`), `tests/test_box.py`.
Do this before T11, so graph kinds are built on the final box sizes.
