# Proposal: `venn` with four sets, as four ellipses

Status: **built**. See *As built* at the end. Size **S**: one more fixed geometry for
`venn`. Placing region text reuses the circles' sampling approach.

## Why

[`venn.md`](venn.md) refused a fourth set because "no circle arrangement shows every
region". That is true of circles, which cannot draw the two diagonal pairs. It is not
true of ellipses. The round-2 corpus ([`../research/corpus-round2.md`](../research/corpus-round2.md),
section 9) found two different four-set figures:

* **The research Venn** (V2–V4: biology papers). Four congruent ellipses, all 15
  regions drawn, and a **count** in each region instead of a sentence.
* **The ikigai figure** (V1). Four circles in a diamond, so only 13 regions exist. Only
  the four pairs and the centre are named.

One geometry covers both: four equal ellipses showing every region. The ikigai figure
then becomes a four-set Venn with most regions left empty, at no extra cost. The owner
decision says the same: four-set Venn in, as ellipses, so that all 15 regions exist.

## Use cases

### 1. Field notes: species shared among four sites (the research figure)

```json
{
  "version": 1,
  "kind": "venn",
  "title": "Bird species recorded at four ponds",
  "sets": [
    {"id": "a", "text": "Mill pond"},
    {"id": "b", "text": "Church pond"},
    {"id": "c", "text": "Quarry lake"},
    {"id": "d", "text": "Marsh pool"}
  ],
  "regions": [
    {"in": ["a"], "text": "12"},
    {"in": ["a", "d"], "text": "2"},
    {"in": ["a", "b", "c", "d"], "text": "**21**", "role": "emphasis"}
  ]
}
```

(The reference lists all fifteen.)

### 2. Careers handout: ikigai

Four questions, `love`, `good`, `need` and `paid`. Five regions are named: the four
pairs and the centre. The other ten are left empty.

### 3. Launch plan: which team owns what

Four teams. Single-word owners sit in eleven regions, and one set is emphasised.

## Fields

No new fields. With four `sets`:

| Rule | Decision |
|---|---|
| Geometry | Four congruent ellipses. The middle two share a centre and cross as an X. The outer two sit lower and farther out. Sets are placed in the order written: outer left, middle left, middle right, outer right. |
| Region text | At most **12 characters**, not counting `**` or backticks. The smallest regions are small, and the corpus puts a number or one word in each. |
| Names | Outside every ellipse. The middle two go above their upper tips. The outer two go under their outer lobes, flush with the drawing's sides, so the names add no width. |

## Refused, and why

| Refused | Why |
|---|---|
| Five or more sets | No drawing of five sets shows every region legibly. The message suggests a `matrix`. |
| Region text longer than 12 characters with four sets | Refused at `/regions/i/text`. Say the rest in the caption. |
| Everything `venn` already refuses | Unchanged. |

Budget: 4 sets, 15 regions.

## Layout sketch

1. The ellipses have fixed proportions: minor axis 0.55 of the major, tilted 35°. The
   middle pair is centred 0.28 above the outer pair, which is 0.33 to either side. These
   values came from a search that maximised the smallest region's room. In that
   arrangement every region holds a few characters, and none is a sliver.
2. A region's candidate points are sampled on a grid, as for circles, and sorted by
   depth, which is the exact distance to the nearest ellipse outline. A block of text
   fits when every corner is inside each ellipse it is in, with a margin to spare, and
   all four sides keep the margin clear of each ellipse it is not in.
3. The size is the smallest semi-major axis, between the circles' floor and the width,
   at which every listed region fits. This is the same search the circles use.

## As built

As proposed, with these notes:

* **Outlines are closed paths**, sampled from each ellipse, rather than rotated
  `<ellipse>` elements. The scene's `Ellipse` has no rotation, and as paths the outlines
  take part in `tools/collisions.py`'s line-crosses-word check.
* **Pruning by depth.** Depth bounds what can fit at a point. A point shallower than
  the block's half-height plus the margin ends the search, because the points are
  sorted deepest first. A point deeper than the block's half-diagonal plus the margin
  fits without the exact test. A four-set reference renders in about two seconds.
* **Each pair of names stands level**: the outer two at one height, and the middle two
  at another.
