# Proposal: `treemap` — the parts of one total, by area

Status: **implemented** — see *As built* at the end for where it departs from this
text. Scope decided by the owner: in, kept to stating a small set of known
proportions. Size **M** (squarified layout is a known algorithm; the hard part is
the label rule).

## Why, and the limit on it

A treemap answers *what dominates, and by how much* for one total split into parts —
a bundle's size, a disk that filled up, where a team's hours went. A `chart` bar can say
it too; a treemap says it in one block whose parts are visibly a whole. It sits on the
same line as `sankey` (area carries a number), and the same argument applies: it states a
small number you already know.

The rule that keeps it a diagram: **every part is labelled inside itself, or the document
is refused.** A treemap's failure mode is the sliver with a label crammed in or moved to
a legend; drawspec should say "merge the small parts" rather than draw one.

## Use cases

### 1. Design document — what is in the 2.4 MB bundle

```json
{
  "version": 1,
  "kind": "treemap",
  "title": "The 2.4 MB front-end bundle",
  "unit": "kB",
  "parts": [
    {"text": "Charting library", "value": 910, "role": "emphasis"},
    {"text": "Our code", "value": 520},
    {"text": "Date handling", "value": 330},
    {"text": "UI components", "value": 300},
    {"text": "Polyfills", "value": 190},
    {"text": "Everything else", "value": 150, "role": "note"}
  ],
  "caption": "The charting library is used on one page."
}
```

### 2. Runbook — what filled `/var` on the build server

```json
{
  "version": 1,
  "kind": "treemap",
  "title": "Why `/var` is full",
  "unit": "GB",
  "groups": [
    {"id": "docker", "text": "`/var/lib/docker`"},
    {"id": "log", "text": "`/var/log`"}
  ],
  "parts": [
    {"text": "Dangling images", "value": 61, "group": "docker", "role": "emphasis"},
    {"text": "Build cache", "value": 38, "group": "docker"},
    {"text": "Volumes", "value": 12, "group": "docker"},
    {"text": "Journal", "value": 9, "group": "log"},
    {"text": "App logs", "value": 6, "group": "log"},
    {"text": "Other", "value": 4, "role": "note"}
  ]
}
```

### 3. Team report — where on-call hours went in the quarter

```json
{
  "version": 1,
  "kind": "treemap",
  "title": "212 on-call hours",
  "unit": "hours",
  "parts": [
    {"text": "Disk alerts", "value": 74, "role": "emphasis"},
    {"text": "Certificate renewals", "value": 41},
    {"text": "Real incidents", "value": 38},
    {"text": "Flapping health checks", "value": 35},
    {"text": "Access requests", "value": 24}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `parts` | root | **yes**, 2+ | `{text, value, group?, role?}`. `value` > 0. Written order does not matter for layout (the algorithm sorts by size); it is the tie-breaker. |
| `groups` | root | no | `{id, text}`: one level of grouping. Parts of one group are laid out together inside a captioned frame. Parts with no group sit beside the groups. |
| `unit` | root | no | Written after each value. |
| `values` | root | no | As in `chart`: draw each part's value under its name. Default true. |

## Refused, and why

| Refused | Why |
|---|---|
| A part whose label does not fit inside its rectangle | Refused with: *merge parts smaller than N into one "other" part* (N computed). Never a label outside its cell, never a sliver legend. |
| More than **10** parts, or a second level of groups | Past that it is a disk-usage tool's output. |
| `value` ≤ 0 | No area. |
| A group with no parts | Empty frame. |
| A per-part fill | Parts are told apart by their borders and labels; groups by the theme's mark fills, in order of first mention, exactly like `matrix` cell groups. |

## Roles

Parts: `step`, `emphasis` (the part the diagram is about — not automatically the
largest), `note` (the remainder). Group frames: the `group` role.

## Layout sketch

1. Squarified layout (Bruls, Huizing & van Wijk) over the canvas width and a height from
   the theme's aspect ratio (or a binding `height`): sort descending, fill rows against
   the shorter side, keep aspect ratios near 1.
2. With groups: lay out the groups' totals first, then each group's parts inside its
   rectangle minus its caption tab.
3. Gaps: one theme gap between cells, taken from the cell, not added — so total area
   remains proportional (tested as relative error).
4. Labels top-left inside each cell; if the wrapped label plus value does not fit the
   cell → refusal above (it is a content problem, not a fit problem, so `DocumentError`
   naming the part, not `FitError`).

## Acceptance tests to write

* Reference documents for the three use cases.
* Each cell's area ∝ its value within 2 % relative error after gaps.
* Each label wholly inside its cell (`clipping.py` against the cell, not the canvas).
* The sliver refusal names the part and suggests the merge threshold.
* Deterministic: equal values break ties by written order.

## As built

Built in `kinds/treemap.py`, a layout family of its own. The owner's decision on
scope: **in, kept to stating a small set of known proportions — not data
exploration**, the line the README draws under "not charting software"; the guide,
`AGENTS.md` and the README say so. The three use cases are
`docs/reference/treemap-bundle.json`, `treemap-disk.json` and `treemap-oncall.json`;
`treemap-latency.json` is the largest, 9 parts in 3 groups plus a remainder. Where
it departs from the text above:

* **`amount`, not `value`.** `value` is refused by name everywhere (a matrix cell is
  filled by its `scale` step, not a number), and no object may offer a field from
  that table — the format's strongest invariant. So the number is `amount`, and a
  `value` on a part is refused naming it. The top-level `values` switch keeps its
  `chart` name.
* **Not the squarified algorithm itself.** Its greedy rows leave the last part
  whatever strip remains: the remainder of `treemap-latency` came out 32 by 192,
  too narrow for "Other". With at most ten parts, every way of cutting the block in
  two across its longer side, keeping the order (largest first, `note` last,
  written order breaking ties), then each half again, can be tried — each half's
  best in its own rectangle. The layout chosen is the one in which the most labels
  fit, then the squarified measure: the worst cell's distance from a label's shape
  (1.5 wide to 1 tall), then the sum.
* **Height.** No theme aspect ratio: the block is 0.6 of the width tall, and when a
  label does not fit it is tried at 0.65, 0.7 and 0.75 before the refusal, so a
  long label costs some height before it costs the type size. A top-level `height`
  is the one height tried.
* **Gaps without a loss of proportion.** One gap (4 units) between cells, taken from
  the cells; a uniform inset takes more of a small cell than a large one, so the
  weights are corrected over a few passes until each drawn share is within 10⁻⁵ of
  the amount's share (the test asks 2 %). A group's caption band is paid for the
  same way.
* **The sliver refusal is a `FitError`, not a `DocumentError`.** Whether words fit
  depends on the theme's type and the measured text, which validation never sees,
  and the elastic fit should try a smaller type before refusing. The message names
  the part, its pointer, amount and cell size, and says to merge the parts of that
  amount or less into one `note` part (`Everything else`). A group name wider than
  its frame is a `FitError` naming the group.
* **The amount is at the body size**, on its own line under the words: every word
  inside a shape is set at one size in every kind. A group's caption is its name in
  bold over its total, inside the frame, above its parts.
* **Roles drawn**: `step` a solid outline, `emphasis` the emphasis role's heavier
  outline with bold words, `note` a light dashed outline (the board's note card);
  cells are sharp-cornered polygons, so a theme's corner radius or pill shape never
  breaks the tiling. Group frames use the `group` role.
* **Refused by name** besides the proposal's list: `percent` and `share` (drawspec
  computes the share), `children`, and `parts`/`groups`/`group` inside a group (one
  level), duplicate group ids and an undeclared group (naming the closest). The
  caps live in the readability budget — 10 parts, 4 groups — the parts' advice
  being to merge the smallest into one `note` part.
* **No theme section.** The gap, inset and heights are fixed in units, so a theme
  cannot change which documents fit; the fills are `[mark] fills`.
