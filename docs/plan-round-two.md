# Round two: what the corpus review asked for

The reviewer went through all eighty-six redraws one by one. Their notes split
cleanly in two, and the split is what this plan is organised around.

**Questions about content** — *did you take this text from the source or invent
it?*, *is this the same graph at all?* — are not answered here. The comparison
page now answers them mechanically, per drawing: it compares the words on the
redraw against the words the original says, and prints what was added, what was
moved onto the drawing from the original's description, and what was dropped.
Thirty-two of the eighty-six have at least one word the original never said, and
the page's **Words to check** filter shows exactly those. That list is what goes
to whoever owns the source text; nothing in this plan tries to settle it.

**Everything else is drawspec's problem**, and that is what follows. Each item
carries the reviewer's own item numbers so a claim can be checked against the
drawing that provoked it.

---

## A. Shapes are too tall and too narrow

*Items 04, 13, 14, 16, 17, 42, 56, 60, 76, 86 — ten of them, the most repeated
complaint by some distance.*

> "A wider last circle would allow to use less lines."
> "Again, wider circles won't look so vertical."
> "Only if top block was wider, it wouldn't take 4 lines."

Every container family sizes its boxes from the **longest** label in the
diagram, then gives every box those dimensions. One long sentence therefore
makes every box tall, and the box that actually holds the long sentence is no
wider than the one holding two words. The reviewer asks the right question
directly: *is top and bottom width configurable, or is there a way to compute
the best sizes?*

The answer should be the second one. Concretely:

1. **`pyramid`** — the apex is the narrowest level and frequently carries the
   longest text (this is not a coincidence; a pyramid puts the most abstract
   statement at the top). Solve the trapezoid geometry *for* the text rather
   than laying out the geometry first and wrapping into it.
2. **`rings`** — a ring's label sits in a band whose width comes from the ring
   radius. Let the radius be chosen so the widest band's text fits on fewer
   lines, rather than fixing radii and wrapping.
3. **`cycle`** — the ring diameter is set by the longest step label
   (`estado__haciendas-locales-y-presupuestos` needed `width: 800` by hand).
   Boxes on a ring have far more horizontal room than the current sizing uses.
4. **`stack` / `columns` / `flow`** — one box per row may exceed the common
   width when nothing else needs that row's height.
5. **Item 76** — `Fi` gets a circle as large as its longest sibling. A terminal
   with two letters in it should not be sized by a terminal with twelve words.

This is one change of principle in the fit pass — *size each box for its own
text, subject to a common alignment* — not five separate ones.

## B. A box wants two levels of text, not an em dash

*Items 15, 25, 40, 52, 59, 60, 78, 89, and explicitly: "Review all em dashes in
general."*

> "In general you use an em dash to separate things. It's not so usual in
> Catalan, so the new lines could be clearer here, just changing font size or
> boldness or whatever, as in the original."

This one is mine, not drawspec's: I wrote `**Titol** — explicació` everywhere
because there was no other way to get a lead and a detail into one box. The
originals do it properly, with a bold first line and a smaller second line.

drawspec needs a way to say *this box has a heading and a body*. Options, in
order of preference:

- a **line break** in `text` (`\n`, or a blank-line convention), with the theme
  free to set the first line differently — the author says "these are two
  lines", the theme says what a first line looks like;
- a `detail` field beside `text`;
- nothing new, and a documented convention of parentheses.

The first keeps the seam honest: a break is structure, not appearance. Once it
exists, **every em dash in the corpus should be revisited** — the reviewer asked
for that in general, not per drawing.

## C. `note` is accepted everywhere and drawn nowhere

*Items 51, 61, and the axis captions in 06 and 89.*

The schema offers `note` on `node`, `level`, `item` and `stage`. **Only
`timeline` draws it.** The other three accept the field and silently discard it
— a field an author can write that has no effect is worse than no field.

Either draw it in the other families or reject it in them. Drawing it is what
the reviewer wants, and it is the same request as:

> "Do we have options to add texts outside graphs? For example, above or below."
> (item 51, on the ISO 31000 bands: *comunicació i consulta contínues*,
> *monitoratge i revisió continus* — text that belongs to the whole diagram, not
> to any one step.)

So there are two distinct things here: a note attached to **one element**, and a
caption attached to the **whole diagram** — above it, below it, or alongside.
The second is what lost the axis end labels in item 06 (`dia 1`, `últim dia`),
the axis label in 89, and the two flanking arrows in 30.

## D. A fan-out crosses its own arrows

*Items 21, 33, 57, 87.*

> "Boxes are not in the same order and arrows look good for 1 and 2 but are
> crossed for 3 and 4."

This is a plain bug and the clearest thing on this list. When one node has
several targets, the first two get sensible ports and the rest cross. The port
assignment is not ordered consistently with the target ordering. Fix in the
router; it will improve four drawings at once and probably more.

Related, same area:

- **item 10, 33** — an angled dog-leg where a straight vertical would do, and
  two runs that went *up* to reach something *below* them;
- **item 17** — a route passing too close to a box it is not connected to (the
  first `sí`, and the *Quaranta-vuit hores* box);
- **item 71** — overlapping runs.

## E. Straight lines, on purpose

*Items 33, 57.*

> "I think the crossed lines transmit better what they want to show. We should
> have that option too, at least for lines without arrow head."

drawspec routes everything orthogonally, which was right for the flows the
reviewer complained about earlier ("líneas curvas extrañas") but wrong for a
mesh. The ITIL value chain and the spine-leaf fabric are both saying *everything
connects to everything*, and a straight chord says that better than a staircase.

This is a **theme** decision, not an author one — the same document should draw
either way. A `[edge] routing = "orthogonal" | "direct"` setting, defaulting to
orthogonal, and possibly restricted to headless roles (`link`) where the
reviewer suggested it.

## F. Feedback edges should leave the spine

*Items 66, 68, 70.*

> "I would have seen it like a vertical arrows thing, but the dotted line could
> go out of the right side of Performing to the right side of Storming. It would
> make every other arrow vertical."

Exactly right, and it generalises: when a graph is a chain plus a few return
edges, the chain should be straight and the returns should go **around** it.
Today the returns are routed through the same channel space as the chain and
push it out of line. Tuckman (66), PMBOK tailoring (68) and NIST (70) are all
this shape.

Item 70 also asks the prior question — *why not a cycle?* — which is an
authoring call, not a tool one: a four-phase loop with one extra return edge is
a cycle, and I drew it as one. The others are chains with a return.

## G. Kinds and options still missing

| Want | Asked in | Note |
|---|---|---|
| **`spans`** — intervals between events, not marks on a line | the declined `tic__drp-y-bcp` | RPO, RTO, WRT, MTD. The clearest missing kind. |
| **Vertical funnel** | 84 | *"It says embut, which should look vertical. Couldn't we have an inverted pyramid for these cases?"* An inverted pyramid is the same geometry already in `pyramid`. |
| **Boxes inside boxes, with bigger boxes** | 12 | *"We had done flows with bigger boxes and boxes inside boxes. This is what we need here."* `groups` exists; nested groups do not. |
| **Diagram-level caption** | 51, 06, 89, 30 | See C. |
| **Distinguishable fills** | 83, 86 | *"I can't differentiate the three colors."* Three group fills are too alike, in colour and in greyscale. |
| **Equal matrix row heights** | 86 | *"Could we make all of the rows the same height?"* |
| **Stars above the title in every box** | 37 | The five-star model reads better with the mark above the label in all five, not just the last. A general "a box may carry a mark above its text" want. |

## H. Documentation debt the review exposed

*Items 11, 23, 76.*

> "I don't know what criteria do you use to choose between circle and rectangle
> here."

Three times. The role vocabulary — `start`, `step`, `decision`, `terminal`,
`emphasis`, `note`, `group` — decides the shape, and nothing tells an author
that, or which role to reach for. Two things follow:

1. **Document the roles**, with a drawing of each, in whatever the usage guide
   turns out to be (this is part of the packaging work).
2. **My own authoring over-reached.** In item 11 I made *Subdelegat del Govern*
   a step and *Directors Insulars* a terminal; the original gave them equal
   weight and was right. `start` and `terminal` should mark where the diagram
   begins and ends, not decorate its extremities. Worth a pass over the corpus
   once the roles are documented.

## I. Arrowheads

*Item 87.* "Arrow heads look small, maybe lines are thicker?" Head length scales
with stroke width (that was the fix for an earlier note), so a heavier line gets
a proportionally bigger head. On the Teams drawing it still reads small. Check
whether the `owns` role's head is scaling at all.

---

## Suggested order

1. **D** (fan-out crossing) — a bug, small, improves several drawings.
2. **A** (box sizing) — the most-repeated complaint, one change of principle.
3. **B** and **C** (two-level text, notes, captions) — one feature family, and
   the fix for every em dash.
4. **E** and **F** (direct routing, returns outside the spine).
5. **G** (`spans`, vertical funnel, nested groups, fills).
6. **H** (document the roles; then re-audit the corpus's role usage).

One thing to hold on to while doing any of it: **the author names meaning; the
theme names appearance.** Straight-versus-orthogonal, how a first line looks,
how loud a fill is — all of those are the theme's. Where a box's text breaks,
and which of two things is the beginning, are the author's. Nothing on this list
needs an author to write a coordinate, and nothing on it should end up letting
them.
