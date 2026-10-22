# `sunburst` — a hierarchy as concentric rings of sectors

A wheel: a tree drawn as rings, the root (or an optional hub) in the middle and each
level a ring of sectors around the last, every label read from the centre outward. The
reference is the *emotion wheel* (*la roda de les emocions*) — a handful of core feelings
at the centre, each opening into finer ones, those into the words we reach for.

This came as an owner request rather than from the corpus survey, but it answers a real
gap: nothing else drawspec draws splits a ring into its parent's sectors. A `treemap`
nests a hierarchy by **area** to compare known amounts; a `mindmap` radiates it as peer
branches with no rings; a `pie` is a single flat ring. A sunburst is the one that says
*this is a classification, read it from the inside out*.

## The design

**The tree is the whole input, and there are no numbers.** A node is `{text, children?}`;
the first ring is `nodes`, and an optional `centre` string draws a hub in the middle. Every
**terminal** node takes an equal slice of the circle, and a parent spans its own — so a
core with six descendants is six times the wedge of a core with one. The order is the order
written, clockwise from twelve. Nothing carries an `angle`, a `weight` or an `amount`;
those are refused, because the geometry is derived, never stated.

**The drawing is the hard part, and it is all derived:**

- *Rings are sized to their words.* Each ring's radial band is made as wide as the longest
  label in it, in proportion, so an outer ring of long words is wider than an inner ring of
  short ones — which is why the wheel reads. The bands are not equal and are never written.
- *One size, stepped down only to fit.* Labels are set at the theme's body size; a label is
  stepped down only when its word will not fit its band or its line will not fit its sector,
  to a floor below which the wheel is refused (`FitError`) rather than drawn illegibly. This
  honours "largest first, smaller for a longer word" without a different size in every
  sector.
- *Never upside down.* Each label is rotated to its sector's mid-angle and read outward; on
  the left half it is turned the other way so the reader never has to.

## The limits

Three rings at most (a fourth is refused), two to eight sectors in the first ring, and
thirty sectors in all — past that the wheel is searched, not read, and the refusal says to
split it into an overview wheel and a wheel per branch. The hub is optional and is not
counted as a ring.

## Status

**Built.** `src/drawspec/kinds/sunburst.py`, schema and validation in
`src/drawspec/schema.py`, reference drawing `docs/reference/sunburst-emotions.json`, tests
in `tests/test_kinds_sunburst.py`.
