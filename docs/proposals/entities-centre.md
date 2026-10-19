# Proposal: `entities` + `centre`, the star schema

Status: **built**. Size **S**: one boolean on an entity, the radial placement `flow`'s
`centre` already uses, and ports for the lines to the middle.

## Why

A data-warehouse star schema is one fact table with its dimension tables round it. The
shape is the argument; that is why it is called a star. `entities` placed it as a
layered drawing, so the four dimensions stood in one column on the left and the fact
table alone on the right. The workaround was a `flow` with `centre`, which keeps the
shape and loses the PK/FK marks and the crow's feet that `entities` draws.

Evidence: one real figure, opos `tic/arquitectura-de-datos-dw-lake-lakehouse`, filed by
the owner as issue #135. That is fewer than the two originals the proposals index asks
of a new kind. It is a field on an existing kind, it reuses an existing placement, and
it adds no vocabulary beyond the word `flow` already uses. So one figure was taken as
enough.

## The shape

```json
{"id": "sales", "text": "`fact_sales`", "centre": true, "fields": [ ... ]}
```

* The entity marked `centre` is placed in the middle. The rest stand round it: the
  first written above, the rest clockwise in the order written. Four go one per side;
  more take the diagonals too.
* The ring is widened, one node gap at a time, until no two boxes are nearer than that
  gap. A ring wider than the canvas is a fit error that names the remedies.
* A line between the middle and a dimension that names no field meets each box square.
  A dimension straight above, below or beside the middle is joined across the gap with
  no bend. A diagonal one is joined from its near side, along, and into the middle's
  side, with one bend. The ends on each side of the middle are spread along it in the
  order their dimensions stand, so no two meet at one point and none cross.
* A line that names a field still leaves its row. To a dimension above or below, it
  goes out a side, along, and back in. It takes the side where it passes fewer rows
  that other lines leave from, so it crosses none of them.

Why not let the router choose: it reads a ring as it reads a layered drawing. A
dimension above or below counted as a line going backwards, so it was sent out a side
and round, and the diagonal lines all ran into the middle's top.

## Refused

* A second `centre`, at `/entities/<i>/centre`. A star has one middle; split the
  diagram into one star per fact table.
* `centre` in a document with an `inherits` or `realizes` relation, at the centre's
  pointer. A class hierarchy is drawn general above specific, and a ring round a middle
  cannot keep that.

## Not covered

A snowflake's outer tables (a dimension of a dimension) stand on the same ring as the
rest, not beyond the dimension they hang from. No original has asked for that yet.

## As built

As proposed. Reference: [`../reference/entities-star.json`](../reference/entities-star.json).
