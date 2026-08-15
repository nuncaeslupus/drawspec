# Round three: what the corpus could not say

Round two came from a reviewer looking at eighty-six redraws and saying what
was wrong with them. This round comes from the other end: the author of those
redraws went back to the **real** source — the original SVG *and the prose
around it*, not the old SVG and its accessibility description — and reported
what could not be written at all.

The report is [*Nine things drawspec cannot say, and four it draws
wrong*][report]. It is written in the shape `brief.md` asks for: what the
source shows, what it means, what was tried, what a reader loses. This document
is drawspec's side of it — every claim checked against the code, sized, and
ordered.

[report]: https://claude.ai/code/artifact/d9ce656c-67ae-4682-87a0-44bd16110d4b

**Read the overlap first.** The report says nothing on it is already-reported.
Against round two that is not quite true, and the exceptions are the useful
part: five items arrive here for the **second** time, from a different person
looking at different evidence. That is not duplicate work to be deduplicated
away — it is the strongest signal on the list, and it moves those items up
rather than off.

| Round three | Round two | Status |
|---|---|---|
| `sibling-order` | **D** ("boxes are not in the same order") | **fixed here** — see below |
| `crossing` | **E** (straight lines, on purpose) | confirmed, unbuilt |
| `spans` | **G** (`spans`, the clearest missing kind) | confirmed, unbuilt |
| `uniform-box-size` | **A** (shapes too tall and too narrow) | confirmed, measured, unbuilt |
| `role-vocabulary` | **H** (document the roles) | half-served by the guide |
| `mark-above-label` | **G** (stars above the title) | **already possible** — see below |

Everything else on this page is new.

---

## What was verified, and how

Nothing below is taken on the report's word. Each claim was reproduced against
the code on `main`, and where a number appears it was measured. Two of the
report's claims came out *sharper* than reported and one came out wrong:

* **Sharper.** "Reordering `nodes` and `edges` renders a byte-for-byte
  identical SVG" — not quite: the bytes move, the *geometry* does not. The
  mechanism is exact and it is worse than an unspecified order: siblings were
  ordered by **node id**, alphabetically, in two independent places.
* **Sharper.** The group members reported as coming out "in ALPHABETICAL order"
  are ordered by id, not by text, which is why the order looked arbitrary
  rather than merely wrong.
* **Wrong, and worth knowing.** The gallery in `docs/gallery/` did not match
  what the code renders. Running `make gallery` on an untouched tree moved
  twenty-two files, so any drawing judged against that page since #40 was
  judged against a stale render. Regenerated in its own commit here, before
  anything else, so the next diff means something.

One more, found on the way and not in the report: **the same document could
render two different SVGs.** `Nesting.roots` read top-level ids out of a
`frozenset`, whose iteration order follows the interpreter's hash seed, so a
document with two top-level groups rendered one way under `PYTHONHASHSEED=1`
and another under `2`. For a tool whose output is committed to a repository
that is a defect of the first order, and it was invisible because every test
ran in one process with one seed.

---

## Done in this round

### `sibling-order` — which of these comes first

*Sheets 01, 11, 21, 39. Round two's item D. Asked for three times across two
rounds, and the one note the report could not act on at all.*

Three children of one parent all sit at the same barycentre, so the ordering
pass never separates them and the **tie-break** decides the order of every fan
in the corpus. It broke on the node id:

* `layered._order` seeded each rank with `sorted(nodes, key=id)` and broke
  barycentre ties on the id;
* `Nesting.roots` iterated a `frozenset`, and group members inherited the same
  id ordering through the rank seed.

Both now read the document's own order. *Alcalde, Comissió de Govern, 10
Districtes* comes out as written; the Kubernetes control plane is
api/store/scheduler/controllers again. It stays a **tie-break** — a barycentre
that differs still wins, so crossing reduction is untouched — and determinism
does not weaken, it moves: the order is fixed by the document rather than by
the id alphabet or the hash seed.

Two gallery drawings move, and both move to what their JSON declares.

### `mark-above-label` — closable, as reported

*Sheet 37. Round two's item G.* Confirmed: `"★★★\nno propietari"` sets the
stars on their own line above the words today, because a newline is a lead and
a detail. No new field. The want can be struck off round two's table.

---

## The nine that cannot be said

Ordered by what they cost, not by where they appeared.

### 1. `grouping-only` — a diagram that is only containment

*Sheets 39, 12, 88.* Three labelled boxes, components listed inside, and not
one arrow.

**Verified.** Five members with no edges between them lay out as five ranks in
one column: 339 units tall, using 187 of the 640 available. Thirteen members —
the real case — is a column thirteen ranks tall, which renders below the
legibility floor at a fixed width. Nothing is lost from the *content*; all of
it is lost from the *drawing*.

The mechanism is that ranking has nothing to work with (`rank_nodes` puts every
unconnected node at rank 0) and `best_layout` then picks the direction that
fits, which turns one rank of thirteen into thirteen ranks of one. Neither is a
grid.

**Shape.** Let a level with no edges among its members **pack** rather than
rank: fill rows to the available width, in declaration order (which now means
something). This is a layout decision, not a new kind and not a new field — the
same document draws better.

**Size.** Medium. It touches `containers.arrange` and the direction choice, and
it moves every groups-only drawing.

### 2. `spans` — a named interval between two moments

*Sheets 41, 69. Round two's item G, and the only sheet with no document at
all.* RPO, RTO, WRT on a disaster timeline; CV and SV between three curves.

**Verified.** `timeline` has `items` and no way to say a bar runs from one to
another; the four instants without the intervals are four words. On 69 the
quantities are pushed into the caption as formulas, which states them and does
not show them.

**Shape.** The report's own proposal, with its own correction: a `spans` array
beside `items`, `{"text": …, "from": …, "to": …}` — **and it may not be
vertical-only**, because on 69 `SV` is horizontal and `CV` vertical. Two
endpoints identified by what they are (an item, a curve's waypoint), not by an
axis.

**Size.** Large, and the largest gain per unit of work on this list: it is the
one sheet of eighty-nine that could not be attempted.

### 3. `hub` — a central thing with named relations on every side

*Sheet 79.* One subject in the middle, four peers around it, each arrow
labelled.

**Verified.** As a `flow` and as a `tree` it refuses — *"no room for the label
`imputat a` on the edge from s to k"* — and only renders once two of the four
arrows are turned round, which is why the current drawing has two arrowheads
pointing the wrong way. Ranked top to bottom, the middle object becomes just
another row.

**Shape.** `centre: true` on one node of a flow, meaning *rank the rest around
this one*, in preference to a new kind: the vocabulary is already `nodes` and
`edges`, and only the ranking differs.

**Size.** Medium-large. A radial placement pass, and label room in four
directions is exactly what the current failure is about.

### 4. `matrix-relations` — relating two cells of a grid

*Sheet 65.* Arrows along the top row, a vertical line from each process to its
output, a dashed return.

**Verified.** `matrix` has no `edges`; a `flow` with one group per phase keeps
every relation and comes out four times taller than the sheet, for the same
reason as item 1 — nothing orders the groups across, so each takes its own
rank.

**Shape.** An `edges` array on `matrix` between cells identified by
`[column, row]`. Note that fixing item 1 does *not* fix this one, but it does
make the `flow` fallback survivable in the meantime.

**Size.** Medium.

### 5. `cycle-exception` — a loop with one documented exception

*Sheet 47.* Four stages round a loop plus one dashed arrow going back early.

**Verified.** `cycle` refuses it in as many words — *"node 'cont' has more than
one outgoing edge. A cycle is one loop: every step has exactly one next
step."* — and `flow` accepts it and ruins it: the loop opens and the four
stages read 3, 4, 1, 2 down the page, numbering against layout.

**Shape.** Let `cycle` take edges beyond the ring and route them inside or
outside it, the way a `flow` return is already routed around the outside. The
refusal message is right about the *ring*; it is wrong that the ring is all a
cycle may hold.

**Size.** Medium, and it is mostly routing, which round two's item D already
opened up.

### 6. `crossing` — whether lines may cross

*Sheets 33, 72. Round two's item E, unchanged and now confirmed from the other
side.* The spine-leaf fabric reads as a fan that avoids itself, which
understates the mesh.

**Shape.** Unchanged from round two: `[edge] routing = "orthogonal" | "direct"`
in the **theme**, possibly restricted to headless roles. The reviewer's own
boundary — *"at least for lines without arrow head"* — is a good one, because a
diagonal arriving at a box at a closed angle is what the original rule was
protecting against and a headless chord has no head to arrive badly.

### 7. `between-stages` — a label on what separates two stages

*Sheet 50.* The word *porta* three times, once in each gap of a funnel.

**Verified.** A stage has `text`, `role` and `note`, and nothing that belongs
to the gap after it. Putting *porta* inside a stage says the stage is a gate.

**Shape.** A `gate` string on a stage — *what stands between this stage and the
next* — which the last stage may not take. It generalises past `funnel` to any
stacked shape whose levels are separated by a threshold.

**Size.** Small.

### 8. `lead-alone` — a name set apart when it has no explanation

*Sheets 54, 50.* Three ring names of equal rank, one bold because it happens to
have a second line.

**Verified.** `Governança` (two paragraphs) is set bold; `SVS` and `Cadena de
valor i pràctiques` (one) are not.

**Shape.** The report proposes treating a single-paragraph label as a lead with
an empty detail. That is the right instinct and the wrong lever: it would set
*every* one-line box in every diagram in the lead treatment, which is a
different drawing everywhere. The narrower reading — and the one the evidence
supports — is that **peers should be set alike**: within one ring stack, one
funnel, one level set, if any member has a lead then a bare member's single
paragraph *is* its lead. Same rule, scoped to the set rather than the document.

**Size.** Small, once the scoping decision above is made. It needs deciding
before it is written.

### 9. `sibling-order`

Done — see above.

---

## Says it, and draws it wrong

Four defects, all reproduced.

### `uniform-box-size`

*Sheet 12. Round two's item A, already measured: 445 boxes, 13% taller than
their own text, 19% of all box area existing only because a peer needed it.*

Reproduced at minimum size: a root with children `A`, `B` and one long label
gives **every** box 173.7 × 51.7 — the one-letter boxes included. Round two
already states the principle: *size each box for its own text, subject to a
common alignment*, with the shared **width** kept as the alignment and the
shared **height** dropped.

### `category-label-collision`

*Sheet 19.* A chart's category labels are neither wrapped nor spaced to avoid
each other.

Reproduced and measured. Four categories at the default width:

| Category | Drawn from | to |
|---|---:|---:|
| Suspensió PROVISIONAL (mesura cautelar) | **−54.9** | 159.6 |
| Suspensió FERMA per sentència | 132.5 | 292.5 |
| Inhabilitació especial | 320.1 | 425.2 |
| Multa coercitiva | 493.0 | 572.6 |

The first two overlap by 27 units, and the first begins 55 units **outside the
canvas** — the viewBox starts at −0.75. Both are the failure the tool exists to
make impossible, committed by the tool, silently. The report is right that a
`FitError` would be better than illegible output; wrapping or rotating would be
better still, and which one is a decision for whoever owns the reviewed charts,
because every option moves existing drawings.

### `group-legend-names`

*Sheets 83, 86.* A cell's `group` key is drawn verbatim as the fill legend, so
an id-shaped key becomes user-visible text.

**Partly reproduced, and worth a second look before it is fixed.** A matrix of
nine cells over three groups drew **no legend at all** in the reproduction —
only the headings and the cell text — so the conditions under which the legend
appears need pinning down before the naming is changed. The underlying
complaint stands either way: `group` is documented as *"which group this cell
belongs to"*, with nothing saying it will be read aloud to the reader. Either
say so in the docs or give a group a display name.

### `lone-child-not-aligned`

*Sheet 10.* One child, not aligned under its parent, so both arrows dog-leg
where a straight drop would do. Round two's item D neighbourhood; not fixed by
the sibling-order change, which orders a rank and does not centre it.

---

## Colour, and whether the theme should carry it

Not in the report — asked alongside it, and it belongs here because two items
above (`group-legend-names`, and round two's *"I can't differentiate the three
colors"*) are really about the same seam.

**Colour is already a theme capability, and always was.** A role's `stroke` and
`fill` take a hex value, `[canvas] ink` is what `currentColor` resolves to
standalone, and the bundled **`accent`** theme colours five roles today. What
constrains it is not a missing feature but two rules, both mechanical:

1. **Two roles may not differ by colour alone.** The loader compares every pair
   and refuses the theme — `greyscale_ambiguous_role_pairs == 0` is a load-time
   gate, not a review note. Colour may *point*; it may not *carry*.
2. **The emitter has an allowlist.** Only colours the theme declares can reach
   the output, which is what stops a colour decision being taken anywhere but
   in the theme file.

And in the default theme every stroke is `currentColor`, so a diagram pasted
into a page is drawn in that page's ink and follows it into dark mode. That is
not a limitation to be lifted; it is the first acceptance test in `brief.md`.

So the answer to *should colour be part of the theme* is that it is, and the
real question is narrower: **there is no colour axis for the things that are
not roles.** A chart's marks and a matrix's cell groups take their appearance
from `[mark] fills`, an ordered sequence of *patterns* — `hatch`, `dots`,
`cross`, `grid`, `none` — chosen because patterns survive a black-and-white
printer. A theme cannot say "and also give the third group this colour". The
reviewer's *"I can't differentiate the three colors"* is exactly that gap: the
patterns alone are doing all the work of separating three groups, and at cell
size they are too alike.

What that suggests, if it is taken up:

* Add an optional **`colours`** sequence beside `[mark] fills`, taken by the
  same index, so a mark or a cell group gets pattern *and* colour.
* Keep the invariant where it already is: the pattern sequence must stay
  distinct on its own, so removing the colour never removes the distinction.
  Then the colour is redundant by construction — which is the only kind of
  colour this tool should ever draw.
* Author-facing vocabulary does not change at all. A cell still names a
  **group**; a series still names a **role**. Nobody writes `#C0452A` in a
  document.

Sized small-to-medium, and it is the cheapest visible improvement on this whole
page — but it is a theme change with a corpus-wide effect, so it wants the
owner's yes before it is written.

---

## Suggested order

1. ~~**`sibling-order`**~~ — done, and it was the most-asked item.
2. **`grouping-only`** (pack an unordered level) — a layout change with no new
   vocabulary, and it unblocks the `flow` fallback for `matrix-relations`.
3. **`uniform-box-size`** — round two's A, twice-reported, already measured.
4. **`category-label-collision`** — the tool committing the failure it exists
   to prevent. Decide wrap-versus-refuse first.
5. **`between-stages`**, **`lead-alone`**, **`group-legend-names`** — the three
   small ones; `lead-alone` needs its scoping decided, not just written.
6. **`crossing`** (round two's E) and **`cycle-exception`** — both routing.
7. **`spans`** — the largest, and the one sheet of eighty-nine still
   undrawable.
8. **`hub`**, **`matrix-relations`** — new placement behaviour, most work.

Colour sits outside the order: it is a theme question, and it wants an answer
before it wants an implementation.

---

## One caveat, passed on as received

**Do not judge a drawing with cairosvg.** It mis-anchors multiple `<tspan>`s
under `text-anchor="middle"`, so correct inline bold and code spans render as
if overprinted. Chromium renders them properly. The report nearly filed that as
a drawspec bug, and anyone rendering the gallery to PNG for review will hit it
too.
