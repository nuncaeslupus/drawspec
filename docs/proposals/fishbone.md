# Proposal: `fishbone` — one effect, its causes by category

Status: **implemented** — see *As built* at the end for where it departs from this
text. Size **M** (fixed two-level structure; one new geometry).

## Why

An Ishikawa diagram is the standard artefact of a root-cause analysis and a staple of
quality-management course notes. Its claim is narrow and fixed: **one effect; causes
grouped into categories; sub-causes under each**. It is a two-level `tree`, and drawn as
one it reads as an org chart — the effect at the top as if it *owned* its causes. The
fishbone shape says the opposite: everything flows into the head.

Because the structure is fixed, the document can be nested without risk: two levels, no
more, and nothing else to get wrong.

## Use cases

### 1. Post-incident review — the nightly backup missed its window

```json
{
  "version": 1,
  "kind": "fishbone",
  "title": "Why the backup finished at 09:40",
  "effect": {"text": "Nightly backup overran its window by 3 h 40 min"},
  "categories": [
    {"text": "Data", "causes": [
      {"text": "Audit table grew 4× after the logging change", "role": "emphasis"},
      {"text": "No retention on audit rows"}
    ]},
    {"text": "Infrastructure", "causes": [
      {"text": "Backup volume on slower storage tier"},
      {"text": "Network shared with the reindex job"}
    ]},
    {"text": "Schedule", "causes": [
      {"text": "Reindex moved to 01:00 the same week"}
    ]},
    {"text": "Monitoring", "causes": [
      {"text": "Duration alert only at 6 h"},
      {"text": "Growth trend not on any dashboard"}
    ]}
  ]
}
```

`emphasis` on a cause marks the confirmed root cause. The other causes stay on the
diagram on purpose: a fishbone records *what was investigated*.

### 2. Course notes — late deliveries, with the classic categories

```json
{
  "version": 1,
  "kind": "fishbone",
  "title": "Why orders ship late",
  "caption": "Categories follow the 6M convention; any set of categories is allowed.",
  "effect": {"text": "Orders ship after the promised date"},
  "categories": [
    {"text": "Method", "causes": [{"text": "Picking by order, not by zone"}, {"text": "Manual address checks"}]},
    {"text": "Machine", "causes": [{"text": "Label printer jams"}]},
    {"text": "Material", "causes": [{"text": "Boxes out of stock"}, {"text": "Supplier ships short"}]},
    {"text": "Manpower", "causes": [{"text": "Peak-season temps untrained"}]},
    {"text": "Measurement", "causes": [{"text": "Promise date ignores stock location"}]},
    {"text": "Milieu", "causes": [{"text": "Courier cut-off moved earlier"}]}
  ]
}
```

### 3. Design document — why the test suite is flaky

```json
{
  "version": 1,
  "kind": "fishbone",
  "title": "What makes CI fail without a code change",
  "effect": {"text": "1 in 12 runs fails and passes on retry"},
  "categories": [
    {"text": "Tests", "causes": [{"text": "Shared fixtures mutate state"}, {"text": "Sleeps instead of waits"}]},
    {"text": "Environment", "causes": [{"text": "Runners differ in CPU count"}, {"text": "Clock skew in containers"}]},
    {"text": "Dependencies", "causes": [{"text": "Live calls to a sandbox API"}]}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `effect` | root | **yes** | `{text, role?}` — the observed problem, stated as a fact. Drawn in the head box. |
| `categories` | root | **yes**, 2+ | `[{text, causes}]`, drawn alternately above and below the spine, nearest the head first. Written order is reading order from the head outwards. |
| `causes` | category | **yes**, 1+ | `[{text, role?}]`. Leaves: a cause has no `causes` of its own. |

## Refused, and why

| Refused | Why |
|---|---|
| `causes` inside a cause (a third level) | A sub-sub-cause is a second fishbone with that sub-cause as its effect. The message says exactly that. |
| A category with no causes | A heading with no investigation under it. If nothing was found, write the cause *"nothing found"* with role `note`, so it is stated rather than implied. |
| Fewer than 2 or more than **6** categories; more than **5** causes in one | Past six bones the diagram stops being scannable; past five causes a bone becomes a list. `FitError` also bounds it. |
| `edges` | The connections are the structure; there is nothing to add. A cause that contributes to another cause is a different diagram (a `flow`). |
| Roles other than `step`, `emphasis`, `note` on a cause | No shape on a bone means `decision` or `terminal`. |

## Roles and theme

Effect: `emphasis` by default (it is the headline). Causes: `step` (default),
`emphasis` (confirmed root cause — its bone is also drawn in the `strong` edge weight up
to the spine, so the path from cause to effect is visible in greyscale), `note`
(ruled out, drawn lighter). Category labels use the `group` caption level.

**The diagonal.** A fishbone's bones are slanted by convention, and drawspec's routing is
orthogonal by rule. This is the same exception as the spine-leaf mesh in
`kinds-wanted.md`: the slant *is* the shape. Proposed theme key `[fishbone] slant` (an
angle; default 60°; `90` draws a comb of vertical bones for a theme that prefers right
angles throughout). The author never sets it.

## Layout sketch

1. Spine: horizontal, the effect box at the right end, vertically centred on it.
2. Bones: categories alternate above / below, evenly spaced along the spine. Each bone's
   length is the stack of its causes' label heights plus gaps; above and below share a
   spacing so opposite bones meet the spine at the same points.
3. Causes: horizontal ticks off the bone, label at the tick's open end, left-aligned so
   labels read away from the bone and never cross it.
4. Spacing along the spine: the widest cause label on either of the two bones sharing a
   slot, so labels on neighbouring bones do not collide.
5. Too wide for the canvas → `FitError` naming the longest cause.

## Acceptance tests to write

* Reference documents for the three use cases.
* Every bone meets the spine; the spine meets the effect box's left border exactly.
* No cause label crosses any bone or the spine (`collisions.py`).
* The `emphasis` cause's bone is drawn in the `strong` weight; others are not.
* Third-level causes refused with the "second fishbone" message.
* `slant = 90` renders vertical bones with the same structure.

## As built

Built in `kinds/fishbone.py`, a layout family of its own; the three use cases are
`docs/reference/fishbone-backup.json`, `fishbone-late-orders.json` and
`fishbone-flaky-ci.json`, and `fishbone-signups.json` adds five categories, two
kinds of cause role and a caption. Where it departs from the text above:

* **The effect takes no `role`.** It is the head, always drawn in `emphasis`, and
  a role there could only make it less than the headline. Writing one is refused
  with the reason; it does not count against the emphasis cap, so a document may
  still mark two confirmed root causes.
* **Every bone is one length** — the longest stack of causes — rather than each
  its own. Bones of different lengths read as an accident, and a category with one
  cause came out as a stub on the spine; equal bones keep the fish symmetric and
  let a short category read as short by its empty stretch near the spine.
* **Causes read from the category's name inwards**, the order written, and their
  words are set *right*-aligned, ending a fixed gap short of the bone, standing on
  a tick that runs from just before the words to the bone. Left-aligned words at
  the tick's open end left a ragged edge against the slanted bone.
* **Slots interleave.** Instead of spacing a slot by the widest cause on either of
  its bones, each slot moves as near the head as it can while every word, tick,
  name and slice of bone in it stays left of whatever it shares a height with —
  a bone leaning away from a neighbour's words makes room for them. When the
  whole is still too wide the causes wrap narrower (each balanced, so a second
  line is not one orphaned word), and only when no width works is it a
  `FitError`, naming the longest cause.
* **Three more theme keys beside `slant`**: `spine` (`strong`), `bone` (`flow`)
  and `cause` (`link`), edge roles drawn with no head, as `[board]` does. `slant`
  is held to 30–90 degrees. A root cause is also set **bold**, so it is told
  apart by weight in the words as well as the line; a ruled-out cause's words
  keep their weight (text has one ink) and its tick is `aside`, light and dashed.
* **The counts live in the readability budget** — `categories` 6 and
  `categories/causes` 5 — with refusals that say to merge categories or split a
  bone into its own fishbone, rather than the generic "overview plus details".
