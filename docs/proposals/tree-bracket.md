# Proposal: `tree` + `"style": "bracket"`, tournaments and cladograms

Status: **built**. Size **S–M**: two fields on `tree`, a layout of its own (the leaves'
column, heights, square elbows) and its text form. No new kind, no theme keys.

## Why

The 2026-10 survey ([`../research/kinds-survey.md`](../research/kinds-survey.md), rank 6)
classed the cladogram and the tournament bracket as one *feature*: "`tree` + a `bracket`
style (leaves aligned on one line, square elbows, internal nodes unboxed)". A boxed
`tree` draws the same hierarchy, but it ranks down from the root and boxes every node,
so a sixteen-team draw is a wide fan of 31 boxes, past the tree's 15-node budget, and a
cladogram's taxa end on different rows instead of one column a reader runs down.

Both figures say one thing with one shape: **the leaves are what the figure is of**, so
they stand in one column on the outer edge, and every join is a match or a split drawn
as a square elbow toward the root.

## Evidence

The proposals index asks for at least two real originals before building. The owner
approved citing published examples found by web search. Found that way (the search
results named and described each one; the figures themselves were not opened, because
this environment cannot fetch them):

* **T1. A World Cup knockout stage.** Wikipedia's article on the
  [2022 FIFA World Cup knockout stage](https://en.wikipedia.org/wiki/2022_FIFA_World_Cup_knockout_stage)
  covers sixteen teams through four rounds of single elimination, scores per match and a
  final decided on penalties. Printable brackets for the same stage were published by the
  press, e.g. [FanDuel's printable bracket](https://www.fanduel.com/research/theduel/printable-bracket-world-cup-2022-knockout-stage-01gkacqa6w2y),
  and [ESPN's fixtures and results](https://africa.espn.com/football/story/_/id/37626851/2022-world-cup-finals-bracket-fixtures-schedule)
  give the scores written beside each team. What it asks for: sixteen leaves, a column
  per round, the score beside each team in each match, a note for penalties, the champion
  at the end. Commonly drawn two-sided, the final in the middle.
* **T2. The NCAA basketball bracket.** The tournament's
  [printable bracket explainer](https://www.fox5ny.com/news/ncaa-march-madness-bracket-2025-printable-online)
  says the draw is split into **four regions, each seeded 1–16**. A 64- or 68-team draw
  is printed as four sixteen-team regions and a final four: that is where the leaf
  budget below comes from, and the split the refusal names.
* **C1. A primate cladogram in a biology textbook.** OpenStax *Biology 2e*,
  [29.7 The Evolution of Primates](https://openstax.org/books/biology-2e/pages/29-7-the-evolution-of-primates),
  divides the primates into Strepsirrhini (lemurs, lorises) and Haplorhini (tarsiers and
  the simians). The figure is a rectangular tree: the taxa in one column, the inner
  splits unlabelled or named by clade.
* **C2. Classroom cladogram handouts**, already in the survey:
  [Boston University GK-12, building a cladogram](https://www.bu.edu/gk12/eric/cladogram.pdf)
  and [Cornell CIBT, evolution tree teacher guide](https://prod.cibt.cornell.edu/workshops_and_summer_programs/0611stanys/EvolTreeTeacher.pdf):
  a few taxa, unnamed splits, and the derived traits marked on the branch where they
  appear. A trait on a branch is an edge `label` here.

None of their content is reused: the reference documents are our own (an invented
under-12s cup, a quiz league, and the living primate groups, which are a classification,
not a figure).

## The shape

```json
{
  "kind": "tree", "style": "bracket", "root": "right",
  "nodes": [
    {"id": "final", "text": "Ash"}, {"id": "s1", "text": "Ash"}, {"id": "s2", "text": "Elm"},
    {"id": "a", "text": "Ash"}, {"id": "b", "text": "Beech"},
    {"id": "c", "text": "Cedar"}, {"id": "e", "text": "Elm"}
  ],
  "edges": [
    {"from": "final", "to": "s1", "label": "2", "role": "strong"},
    {"from": "final", "to": "s2", "label": "1"},
    {"from": "s1", "to": "a", "label": "3", "role": "strong"},
    {"from": "s1", "to": "b", "label": "0"},
    {"from": "s2", "to": "c", "label": "1"},
    {"from": "s2", "to": "e", "label": "2"}
  ]
}
```

* **A style, not a kind.** The payload is a `tree`'s: `nodes` and `edges`, an edge from
  a match (or a split) to what feeds it. `style` is `boxes` (the default, as before) or
  `bracket`, as `meter` and `files` take a `style`.
* **No coordinates.** A leaf stands on the outer edge, one row each, in the order the
  edges are written. An inner node stands as far from that edge as its deepest leaf is
  below it (its *height*): a knockout's rounds are columns, and a ladder cladogram climbs
  one step per split. Its row is halfway between its first and last child's. A bye — a
  leaf joined to a later round — is a longer line, not a special case.
* **Lines, not boxes.** Each node is the line from its own end to its parent's elbow; the
  elbow is square. Its words sit on that line at its own end. An edge's `label` sits on
  the child's line by the elbow: the score in that match, or the trait a lineage gained.
  An inner node's `text` may be `""`: a bare junction, a cladogram's ancestor.
* **`root`** — `left` (the default, the cladogram's way round: a short root at the left,
  the names in one column past the tips), `right` (a tournament read left to right, the
  champion's line at the end, each name on its line), or `middle` (the two-sided draw:
  the root's first child's half on the left, its second mirrored on the right, the root's
  words over a short stub where they meet). **No top or bottom**: a bracket reads
  across, a row per leaf, and turning it would need the names rotated or wrapped.
* **`strong` edges are heavy**, for the champion's run or the lineage the lesson is
  about. Every other edge is one plain line.
* **Text output** draws the same layout on cells: leaves two rows apart, the elbows in
  box-drawing characters joined square (`┐ ┘ ├ ┤ ┼`, `+` in ASCII), the words inline.

Why not the layered engine with orthogonal routing: it ranks from the root, so the
leaves of an unbalanced tree land on different ranks, and it would box every node.

## Refused

Each at its pointer, with what to do instead.

* `root` without the bracket style (`/root`); a root at the `top` or `bottom` (`/root`).
* A second parent (`/edges/<i>/to`): a team in two matches is two entries; a hybrid of
  two lineages is a network — boxes, not a bracket.
* An edge to itself (`/edges/<i>/to`), a cycle (`/edges`), a second root (`/nodes/<i>`).
* An inner node of one child (`/nodes/<i>`): a match has two sides.
* An unnamed leaf (`/nodes/<i>/text`): only an inner node may go unnamed.
* Words or a label on two lines (`…/text`, `…/label`).
* `groups`, `bands`, `classes`; a node's `class`, `status`, `actor` or `role`; an edge's
  `status`, or a role other than `flow` and `strong` — a bracket has no boxes for any of
  them.
* `"root": "middle"` with a root of other than two children (`/root`).

## Budget

**16 leaves**, a sixteen-team knockout, refused at the seventeenth leaf with the split
the NCAA prints (a bracket per region of sixteen, and one for the regions' winners).
With no node of one child, sixteen leaves are at most 31 nodes, which replaces the boxed
tree's 15-node budget for this style. A cladogram of ten to fifteen taxa fits easily.
Text: a sixteen-team draw with scores needs about 92 columns; a narrower `--width` is
refused with the width it needs.

## Not covered

* Seeds written before a team's name are just words: `"1 Ash"`.
* A third-place match is a second tree: draw it as its own document, or in the caption.
* A double-elimination draw has a losers' bracket that feeds back into the winners':
  not a tree. A Swiss or round-robin stage is a table.
* Branch lengths (a phylogram, where length is time or change) are numbers on a line,
  which drawspec does not draw; every split here is one step.

## As built

As proposed. References:
[`../reference/tree-bracket-cup.json`](../reference/tree-bracket-cup.json) (sixteen teams,
scores, the champion's run heavy, `root: right`),
[`../reference/tree-bracket-primates.json`](../reference/tree-bracket-primates.json) (a
cladogram, two named clades, `root: left`) and
[`../reference/tree-bracket-quiz.json`](../reference/tree-bracket-quiz.json) (a two-sided
draw of eight, `root: middle`).
