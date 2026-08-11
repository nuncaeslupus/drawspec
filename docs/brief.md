# Brief: a declarative diagram tool, designed for LLM authors

This is the originating brief for drawspec, translated into English and
stripped of anything specific to the project the evidence corpus came from.
It is the statement of the problem, not the design. The design lives in
`docs/spec.md`.

---

## The ask

Decide whether to build — or adopt — a tool that **draws diagrams from a
declarative description** (JSON or another text format), placing the boxes and
the arrows itself, and exporting clean SVG.

**The target audience is what makes it different: usable by humans, but above
all by an LLM.** A model has to be able to write the input file without seeing
the result and without getting a coordinate wrong, because **there would be no
coordinates to write**. Today models draw SVG by hand, with absolute `x`/`y`,
and they fail systematically at the same things.

The bar is set by **yEd** (yWorks): hierarchical, organic, orthogonal, circular
and tree layouts, edge routing, grouping, overlap-free labelling. Its paid
version is extremely expensive, and it is a desktop application — no use to a
model driving it.

This is **not a commission to build**. It is to investigate and specify. The
first question can perfectly well be answered with "it already exists, use that
one".

## The evidence

The design is driven by a real corpus, not an invented example: **87 SVG
diagrams written by hand by an LLM** for a set of study notes, and **63 review
notes** written by a human reviewing them by eye.

The diagrams live in `corpus/fixtures/` in anonymized form — every drawing
decision preserved, all text replaced with lorem ipsum of the same length.
Their objective measurements are in `corpus/metrics.json`. See
`corpus/README.md` for what was kept and what was removed.

### What was already measured

Across the 87:

| | |
|---|---:|
| Diagrams / with a failure noted by a human | 87 / **63** |
| Elements: `text` / `rect` / `path` / `line` / `circle` / `polygon` | 781 / 387 / 207 / 134 / 50 / 24 |
| With **any curved stroke** | **7 of 87** |
| Declaring a `<marker>` for the arrowhead | 47 — the other **40 draw the head by hand** |
| **Mixing font sizes** within the same drawing | **51 of 87** (12 distinct sizes in the corpus, from 9.5 to 16) |
| Hardcoded colours, not inherited | 2, and both are a hatch pattern |
| Distinct `viewBox` widths | many; the most common covers only 23 of 87 |
| Boxes per diagram | median **4**, maximum **17** |

The failure families, counted from the 63 notes (one note can fall into two):

| Failure | Notes |
|---|---:|
| Text crossing lines or other boxes | 13 |
| Text escaping its box, or not fitting | 11 |
| Arrow with no shaft, or only a head | 10 |
| Margins and line spacing inside boxes | 7 |
| Small type, or uneven type sizes | 6 |
| Vertical centring of text in the box | 5 |
| Lines that do not reach the box | 4 |
| Curves where there should be a right angle | 3 |
| Badly proportioned pyramids | 3 |
| Hatching too heavy | 3 |
| Concentric circles with text touching the ring | 2 |
| **No clear category** (alignment, monospace, arrows whose meaning is unclear…) | 12 |

And **20 of the 63 are a question rather than a request** ("not sure this is
what was expected", "I don't quite understand this diagram"). Four are content
doubts, not drawing doubts. Those do not count as drawing failures.

## Three conclusions already drawn, and why

**1. The corpus is a labelled graph, not illustration.** Boxes, lines and
labels; only 7 of 87 with curves. This is what a layout engine has been solving
for thirty years.

**2. The 63 failures are all placement, none of them judgement.** Nobody
disputes *what* goes in the diagram, only *where it ends up*. And each family
disappears by construction once there is an engine:

| Failure | Why a generator cannot commit it |
|---|---|
| Arrow with no shaft / only a head | The edge is anchored to the node border; there is no loose triangle to place |
| Line that does not touch the box | Same reason: the endpoint *is* the border |
| Text that does not fit or overflows | The box is sized from its text, not the other way round |
| Text crossing lines | Label placement with overlap detection |
| Odd curves | Orthogonal routing is an engine option, not a per-drawing decision |
| Differing font sizes | There is no per-element `font-size` to write |

**3. An after-the-fact validator is not enough.** A cheap mechanical check over
the already-written SVG — text outside the canvas, text overflowing its box —
catches **17 of the 63**. **46 escape it.** If a failure is to be avoided, it
has to be generated away, not reviewed away.

Hence the starting hypothesis, to be confirmed or knocked down with data:

> **Do not write a layout engine. Wrap one.** Reimplementing hierarchical
> layout, orthogonal routing and label placement is reimplementing thirty years
> of work, and doing it worse. The real work is elsewhere.

## Where the real work is

- **The style layer.** A shared fixed width, colour inherited from the document,
  `<title>`/`<desc>`, one type size per hierarchical level. No engine gives you
  that: they all emit their own SVG to their own taste.
- **The shapes that are not graphs.** Pyramid, concentric circles and a simple
  axis chart are **3 of the 9 types** in the corpus, and they are solved with
  parametric templates, not graph theory. Best not to put them in the same bag.

The nine types come from the corpus, not from imagination: **flow with
decision, tree hierarchy, cycle, layers or stack, pyramid, concentric circles,
column comparison, timeline, and a simple chart with axes.**

## The first acceptance test, ahead of any feature table

**The SVG is pasted inline inside a Markdown document**, not linked as a file.
That disqualifies many generators before you even look at how they draw: the
ones that emit `<style>` with global selectors, `id`s that collide when two
diagrams are pasted into the same page, embedded fonts, or hardcoded colours
that break dark mode and greyscale printing.

So the first question is not "does it draw nicely?" but:

> **Does it emit an SVG I can paste inside a `.md`, that inherits the
> document's colour, and that survives greyscale printing?**

If two elements are distinguishable only by colour, they are wrong.

## The second acceptance test

The three worst diagrams in the corpus, with the reviewer's verdict:

- `corpus/fixtures/fixture-020.svg` — *"Terrible on margins and arrows and text
  that does not fit. Redo completely."*
- `corpus/fixtures/fixture-067.svg` — *"Very odd chart, the text overlaps, there
  are arrows with only a head, there is no label for the vertical axis…"*
- `corpus/fixtures/fixture-047.svg` — a cycle whose arrows fail to close the
  circle, with a truncated sentence that also crosses a line.

**Rewrite them as a declarative file** in whichever tool draws best, generate
the SVG, and look at the result. That is the test, not the feature list.

## What the brief asks for, in order

1. **Does it already exist?** If something does this, the right move is to use
   it, not write another. Candidates to examine — add any that are missing:
   Graphviz (dot, neato, fdp, circo, twopi), ELK (Eclipse Layout Kernel), D2,
   Mermaid, PlantUML, TikZ, Kroki, and whatever survives of yFiles with a usable
   licence. For each: **link and date consulted**, licence, how it is invoked
   from a CLI or a file, and whether it passes the two tests above. No lists
   copied from product pages.
2. **The three worst diagrams redone**, to look at.
3. **A recommendation with its cost**: use an existing one, wrap an existing one
   with a style layer, or specify a new one — and if it is the third, why the
   other two are not enough.
4. If it is wrap or specify: the **input format schema** (JSON Schema), designed
   to be written blind by a model. Name the decisions the author **should not**
   be allowed to take, because those are exactly the ones that go wrong today.
5. The list of **mechanical checks** the tool would make unnecessary, and the
   ones worth keeping as a validator anyway.

## Scope: generic, driven by a real case

The tool **is not for that corpus** and must carry nothing of it inside: a graph
goes in, an SVG comes out. The consumer's style is **a configurable theme**, and
being able to parameterise it is the proof that it is not baked in.

But the risk of a generic product is never shipping. So the rule is: **build it
generic, drive it with the corpus.** The 63 real failures are the acceptance
test, and no feature goes in that nobody asked for. If the answer turns out to
be "use Graphviz with a 200-line template", that is a success, not a failure.
