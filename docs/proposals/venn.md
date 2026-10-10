# Proposal: `venn` — two or three overlapping sets, regions named

Status: **proposed**. Size **S** (two fixed geometries; the work is fitting text into
regions).

## Why

"What do these two things share" is one of the most common figures in course notes, and
a Venn diagram is a case where the absence of coordinates is easy: with two or three
sets every region is fully determined by **which sets it is in**. The author says
`in: ["gdpr", "ens"]`; drawspec knows where that region is.

What it is not: an area-proportional diagram (sizes would be data → charting), and not
four or more sets (no circle arrangement shows every region; a `matrix` does).

## Use cases

### 1. Course notes — which obligations come from which framework

```json
{
  "version": 1,
  "kind": "venn",
  "title": "Two frameworks, one breach",
  "sets": [
    {"id": "gdpr", "text": "Data protection regulation"},
    {"id": "ens", "text": "National security framework"}
  ],
  "regions": [
    {"in": ["gdpr"], "text": "Notify the supervisory authority within 72 h"},
    {"in": ["ens"], "text": "Report to the national CERT"},
    {"in": ["gdpr", "ens"], "text": "Keep an incident record", "role": "emphasis"}
  ]
}
```

### 2. Course notes — roles that overlap in a data team

```json
{
  "version": 1,
  "kind": "venn",
  "title": "Where a data engineer sits",
  "sets": [
    {"id": "sw", "text": "Software engineering"},
    {"id": "an", "text": "Data analysis"},
    {"id": "ops", "text": "Operations"}
  ],
  "regions": [
    {"in": ["sw", "an"], "text": "Analytics engineering"},
    {"in": ["sw", "ops"], "text": "Platform engineering"},
    {"in": ["an", "ops"], "text": "Monitoring and SLOs"},
    {"in": ["sw", "an", "ops"], "text": "**Data engineering**", "role": "emphasis"}
  ]
}
```

Regions not listed are drawn empty — the three single-set regions here say nothing
beyond their set's name.

### 3. Design document — which clients get which feature

```json
{
  "version": 1,
  "kind": "venn",
  "title": "Feature parity, honestly",
  "sets": [
    {"id": "web", "text": "Web"},
    {"id": "desktop", "text": "Desktop"},
    {"id": "mobile", "text": "Mobile"}
  ],
  "regions": [
    {"in": ["web"], "text": "Admin console"},
    {"in": ["desktop"], "text": "Offline editing"},
    {"in": ["mobile"], "text": "Push alerts"},
    {"in": ["web", "desktop"], "text": "Bulk export"},
    {"in": ["web", "desktop", "mobile"], "text": "Viewing and comments"}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `sets` | root | **yes**, 2 or 3 | `{id, text, role?}`. Set names drawn **outside** their circle, never across the outline. |
| `regions` | root | no | `{in, text, role?}`. `in` is the exact list of set ids the region belongs to (and no others). |

## Refused, and why

| Refused | Why |
|---|---|
| 1 set, or 4+ sets | One set is a box; four sets have no circle drawing that shows every region. The message suggests a `matrix` (sets as columns, items as rows). |
| `in` naming an unknown set, empty `in`, or the same membership twice | At its pointer. |
| A subset (`"subset_of"`), or sizes | A set inside another is `rings`; sizes are data. |
| A region text that does not fit its region | `FitError` naming the region. Region capacity is fixed by the geometry, so a long list belongs in another kind; the message says so. |
| `edges` | Nothing to connect. |

## Roles

Sets: `step` default; `emphasis` thickens one outline. Regions: `step`, `emphasis`
(the region the diagram is about: its text in bold weight and the region filled with the
theme's first mark fill, clipped to the intersection — a pattern, so greyscale holds).

## Layout sketch

1. Two sets: two equal circles overlapping by a theme ratio; three: equilateral
   arrangement. Radius grows (within the canvas) until every region's text fits its
   region's largest inscribed rectangle, computed once per geometry and scaled.
2. Text centred on the region's label point (precomputed per region of the fixed
   geometry), wrapped to the inscribed rectangle's width.
3. Set names outside, at the far side of each circle from the centre of the arrangement.

## Acceptance tests to write

* Reference documents for the three use cases.
* Every region text lies wholly inside its region (point-in-circle checks on the text
  box's corners against each circle, in or out as `in` says).
* No set name crosses a circle outline.
* 4 sets → refused with the `matrix` suggestion.
