# Proposal: `mindmap`: one topic radiating into branches

Status: **built** (see *As built* at the end). It comes from `docs/research/kinds-survey.md` (rank 2).
Size **M**: two tidy trees, one on each side of a centre. The tidy-tree placement
exists in `tree`. What is new is the split into two sides and the unboxed leaves.

## Why

Study-skills services hand out the mind map as *the* way to make revision notes. People
also use it to plan a project, a talk or a move, and to brainstorm in a meeting. Its
content is a hierarchy, so `tree` can hold it. A `tree`, though, is ranked from a root
at the top or the left edge, which says *this comes first, then these*. A mind map
says the opposite: the topic is in the middle, every main branch is a peer, and none
comes first. Drawn as a `tree`, a seven-branch map becomes one very wide row that no
page holds.

What it is not: a concept map. A concept map links any concept to any other with a
labelled phrase, which `flow` already draws. A mind map is strictly nested, and a
cross-link between branches is refused with that suggestion.

## Use cases

### 1. Revision notes: photosynthesis

```json
{
  "version": 1,
  "kind": "mindmap",
  "title": "Photosynthesis",
  "centre": "Photosynthesis",
  "branches": [
    {"text": "Needs", "branches": [
      {"text": "Light"}, {"text": "Water"}, {"text": "Carbon dioxide"}, {"text": "Chlorophyll"}
    ]},
    {"text": "Makes", "branches": [
      {"text": "Glucose", "branches": [{"text": "Respiration"}, {"text": "Starch store"}]},
      {"text": "Oxygen"}
    ]},
    {"text": "Where", "branches": [{"text": "Chloroplasts"}, {"text": "Mostly in leaves"}]},
    {"text": "Limiting factors", "role": "emphasis", "branches": [
      {"text": "Light intensity"}, {"text": "CO₂ concentration"}, {"text": "Temperature"}
    ]}
  ]
}
```

### 2. History notes: long-term causes of a war

```json
{
  "version": 1,
  "kind": "mindmap",
  "title": "Why war came in 1914",
  "centre": "Long-term causes",
  "branches": [
    {"text": "Militarism", "branches": [{"text": "Naval race"}, {"text": "Mobilisation plans"}]},
    {"text": "Alliances", "branches": [{"text": "Triple Entente"}, {"text": "Triple Alliance"}]},
    {"text": "Imperialism", "branches": [{"text": "Rivalry for colonies"}, {"text": "Moroccan crises"}]},
    {"text": "Nationalism", "branches": [{"text": "Balkan independence"}, {"text": "Pan-Slavism"}]},
    {"text": "The spark", "role": "note", "branches": [{"text": "Sarajevo, June 1914"}]}
  ]
}
```

### 3. Personal: planning a move

```json
{
  "version": 1,
  "kind": "mindmap",
  "title": "Moving in March",
  "centre": "The move",
  "branches": [
    {"text": "Before", "branches": [{"text": "Give notice"}, {"text": "Book the van"}, {"text": "Sort and donate"}]},
    {"text": "Paperwork", "branches": [{"text": "Change of address"}, {"text": "Register with a doctor"}, {"text": "Council tax"}]},
    {"text": "The day", "role": "emphasis", "branches": [{"text": "Meter readings"}, {"text": "Keys"}]},
    {"text": "After", "branches": [{"text": "Unpack the kitchen first"}, {"text": "Meet the neighbours"}]}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `centre` | root | **yes** | The topic: a string, drawn as the one boxed element, in the middle. |
| `branches` | root, and inside each branch | **yes** at the root (2–8) | `{id?, text, role?, branches?}`. Nested, the way `fishbone` nests causes in categories: the structure is what is written, so there are no edges to get wrong. At most three levels below the centre. |

## Refused, and why

| Refused | Why |
|---|---|
| Fewer than 2 or more than 8 main branches | One branch is a `tree`, and nine do not read as peers around a centre. Budget. |
| More than 30 branches in all, or a fourth level | Budget. Split: the overview names the main branches, and a map per branch carries the detail. |
| `edges`, `links`, a cross-link between branches | A mind map is nested. Relations across branches are a concept map, which is a `flow` with labelled edges. The message says so. |
| `side` on a branch | The layout balances the two sides. A side chosen by the author is a coordinate. |
| An empty `text` | At its pointer. |
| A label that cannot fit at the canvas width | `FitError` naming the branch. Shorten it. Leaves are phrases, not sentences. |

## Roles

The centre is always the boxed topic and takes no role. Branches take `step` (the
default), `emphasis` (bold, with a thicker connector all the way from the centre: the
branch the map is about) and `note` (faint: context, not content). At most two
`emphasis`, as everywhere.

## Layout sketch

1. **Split the main branches into two sides.** They go in the order written, clockwise
   from the top right, and the split point is the one that best balances the leaf count
   of the two sides. The first branch is always on the right. The split is
   deterministic, so the same document always draws the same way.
2. **Each side is a horizontal tidy tree** growing away from the centre: the right
   side grows rightwards, and the left side is mirrored. The `tree` placement is reused
   with direction fixed. Sibling order is the order written, read top to bottom on both
   sides.
3. **Leaves and inner branches are unboxed**: text sitting on a short underline, the
   common mind-map convention. A theme key `[mindmap] boxes = true` boxes them for a
   house that prefers it. Main branches are boxed lightly, and the centre is boxed
   strongly.
4. **Connectors** are smooth curves from parent to child, leaving the parent's side and
   landing on the child's underline. The theme decides their taper by level
   (`[mindmap] taper`), never the author.
5. The centre is placed at the vertical middle of the taller side, and the canvas
   height follows.

## Acceptance tests to write

* Reference documents for the three use cases, rendered and looked at.
* The split is balanced: for every reference, the two sides' leaf counts differ by at
  most the largest main branch's leaf count.
* Order is preserved: reading each side top to bottom gives the branches in the order
  written (the right side forwards, then the left side, starting from the bottom).
* No connector crosses a label, and no label crosses another (`collisions.py`).
* Every refusal above, at its pointer. A document with `edges` gets the concept-map
  suggestion.
* The `AGENTS.md` row ("A topic and its subtopics, with no order between them"), and
  the README count of kinds updated.

## As built

Checked against the round-2 corpus (M1–M5): study-skills maps have a handful of main
branches and never more than three levels, so the owner-approved budget — **8 main
branches, 30 in all, depth 3** — holds every one; M2's arrows and M5's linked concepts
stay a concept map, refused with the suggestion to draw a `flow`. What changed:

* **No `id` on a branch.** Nothing refers to one: a branch's place is where it is
  written. An `id`, like `edges` or `links`, is refused as the start of a cross-link,
  naming the concept map and `flow`.
* **The split balances drawn heights first, then leaf counts.** Two branches with the
  same leaves can differ by a wrapped line or a box, and height is what the eye
  compares. The proposal's bound still holds for every reference (a test checks it).
  A tie goes to the right side holding more.
* **Radial, within what is left.** Each side is a horizontal tidy tree, centred on the
  centre's middle, and the main branches bulge out round the centre — those nearest its
  middle furthest out — but only by the width the canvas has to spare: the bulge never
  makes a word wrap. A main line leaves the centre's rounded end along its normal,
  aimed at its branch, so the lines fan out instead of leaving one point.
* **Wrapping is per branch.** When the map is too wide, only the main branch reaching
  furthest out on the wider side has its twigs and leaves wrapped narrower, so a short
  branch elsewhere keeps its one line. The tightest layout is tried first, and a word
  wider than its branch can be is a `FitError` naming the branch.
* **The centre is a pill in the `terminal` role** (the heavy outline), its words bold
  at the body size (every kind sets the text in its shapes at one size), kept at least
  as wide as it is tall. Main branches are `step` boxes
  (`emphasis` for the emphasised one) with bold words; twigs at the body size and leaves
  at the label size, so type thins outwards like the lines.
* **Lines are tapered ribbons** filled in the `flow` edge role, by `[mindmap] taper` —
  three widths, one per level, none thicker than the one before; each line narrows to
  the next level's width where it arrives, and that is the width of the line a twig's
  words sit on, so a branch line runs on under its words without a seam. `emphasis`
  draws the lines from the centre to the branch half as thick again (fishbone's rule).
* **`note` is inherited.** A note branch, and everything under it, is faint words on a
  dashed `aside` line; a note main branch is not boxed.
* **The 30-branch budget is a new budget form**, `branches*`: an array counted at every
  depth together, its refusal at the 31st branch in reading order. A fourth level is
  refused at its `branches`, and an empty `branches` list (it draws nothing) is refused.
* **Not built: colour per branch.** The corpus finds it recommended everywhere, and it
  is theme work, not a field; drawspec never makes colour carry meaning, and the map
  reads the same without it. A per-branch palette cycle can be added to `[mindmap]`
  later without touching a document.

References: `mindmap-photosynthesis` (use case 1, three levels), `mindmap-essay-plan`
(an ordered plan, M3: numbered leads and the order written), `mindmap-moving-house`
(use case 3, with a `note` twig), `mindmap-offsite` (eight main branches).
