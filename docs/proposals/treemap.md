# Proposal: `treemap` — the parts of one total, by area

Status: **proposed, scope to be confirmed by the owner**. Size **M** (squarified layout is
a known algorithm; the hard part is the label rule).

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
