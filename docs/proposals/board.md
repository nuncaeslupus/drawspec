# Proposal: `board` — cards in columns, with optional slices

Status: **proposed**. Size **M** (a grid of stacks; no routing at all).

## One kind for kanban, story maps and retrospectives

All three are **cards sorted into columns, with no connectors**. A kanban board's columns
are states; a retrospective's are prompts (*went well / to improve / actions*); a story
map's are the steps of a user's story, and it adds horizontal **slices** (releases) and a
**cut** between the first release and the rest. A board without rows is a kanban; with
rows and a cut it is a story map. One kind.

Why not `matrix`: a matrix cell is one box placed by index, and its fill is the content.
A board cell holds **a list of cards** whose count matters, and its column may carry a
work-in-progress limit. Why not `columns`: a column there is one box of text.

## Use cases

### 1. Team page — the documentation migration, this week

```json
{
  "version": 1,
  "kind": "board",
  "title": "Docs migration — week 3",
  "columns": [
    {"id": "todo", "text": "To do"},
    {"id": "writing", "text": "Writing", "limit": 3},
    {"id": "review", "text": "In review", "limit": 2},
    {"id": "done", "text": "Published"}
  ],
  "cards": [
    {"text": "Install guide", "column": "done"},
    {"text": "CLI reference", "column": "done"},
    {"text": "Theming guide", "column": "review", "actor": "Ana"},
    {"text": "Embedding in Markdown", "column": "review", "actor": "Luis"},
    {"text": "MCP server", "column": "review", "actor": "Ana", "role": "emphasis", "note": "blocked on a decision"},
    {"text": "Gallery page", "column": "writing", "actor": "Marta"},
    {"text": "Troubleshooting", "column": "todo"},
    {"text": "+ 6 more pages", "column": "todo", "role": "note"}
  ]
}
```

*In review* holds three cards against a limit of two. The author did not say so: drawspec
counts, and the column heading is drawn as `3 / 2` in the `emphasis` role.

### 2. Course notes — a story map for a library app

```json
{
  "version": 1,
  "kind": "board",
  "title": "Borrowing a book, sliced into releases",
  "columns": [
    {"id": "find", "text": "Find a book"},
    {"id": "borrow", "text": "Borrow it"},
    {"id": "return", "text": "Return it"}
  ],
  "rows": [
    {"id": "first", "text": "First release"},
    {"id": "next", "text": "Next"},
    {"id": "later", "text": "Later"}
  ],
  "cut": "first",
  "cards": [
    {"text": "Search by title", "column": "find", "row": "first"},
    {"text": "See if a copy is on the shelf", "column": "find", "row": "first"},
    {"text": "Borrow at the desk with a card", "column": "borrow", "row": "first"},
    {"text": "Return at the desk", "column": "return", "row": "first"},
    {"text": "Search by author", "column": "find", "row": "next"},
    {"text": "Reserve a copy that is out", "column": "borrow", "row": "next"},
    {"text": "Reminder before the due date", "column": "return", "row": "next"},
    {"text": "Recommendations", "column": "find", "row": "later"},
    {"text": "Self-service kiosk", "column": "borrow", "row": "later"}
  ]
}
```

`cut` draws a heavy rule under the *First release* slice: everything above it is what
ships first. That rule is the point of a story map.

### 3. Meeting notes — a retrospective

```json
{
  "version": 1,
  "kind": "board",
  "title": "Sprint 14 retrospective",
  "columns": [
    {"id": "well", "text": "Went well"},
    {"id": "improve", "text": "To improve"},
    {"id": "actions", "text": "Actions", "role": "emphasis"}
  ],
  "cards": [
    {"text": "Release went out on the Tuesday", "column": "well"},
    {"text": "Pairing on the parser", "column": "well"},
    {"text": "Flaky integration tests", "column": "improve"},
    {"text": "Reviews waited two days", "column": "improve"},
    {"text": "Quarantine the three flakiest tests", "column": "actions", "actor": "Joan"},
    {"text": "Review rota in the team calendar", "column": "actions", "actor": "Ana"}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `columns` | root | **yes**, 1+ | `{id, text, limit?, role?}`, left to right as written. Objects, not strings as in `matrix`, because a column has a limit and is referred to by id. |
| `limit` | column | no | A positive integer. drawspec counts the cards and draws `n / limit` in the heading; over the limit, the heading takes `emphasis`. The count is never written by the author. |
| `rows` | root | no | `{id, text}`, top to bottom. With rows, every card must name one. Drawn as labelled slices across all columns. |
| `cut` | root | no | The id of a row: a heavy rule is drawn under it. Requires `rows`. |
| `cards` | root | **yes**, 1+ | `{text, column, row?, role?, actor?, note?}`. Within a cell, cards stack **in the order written** (`order` is refused everywhere; the array is the order). |
| `actor` | card | no | Who holds it, drawn as the card's lead — the same field and drawing as `flow`. |
| `note` | card | no | Drawn under the card's text in the note level ("blocked on …"). |

## Refused, and why

| Refused | Why |
|---|---|
| `edges` | A board has no connectors. The message: *if the order between cards matters, it is a `flow` or `lanes`*. |
| A card naming an unknown column or row | At its pointer. |
| `row` on a card when there are no `rows`, or missing when there are | Half a story map is a mistake. |
| `cut` naming the last row | A cut with nothing below it cuts nothing. |
| More than **6** columns, **4** rows, or **8** cards in one cell | Write a summary card (`"+ 6 more pages"`, role `note`), as use case 1 does. The message says so. |
| A per-card colour, label or tag field | Appearance is the role's; a card's kind is its column. |

## Roles

Cards: `step` (default), `emphasis` (blocked, at risk, the one that matters), `note`
(a placeholder or summary card, drawn lighter). Columns: `step` or `emphasis` for the
heading. Slices use the `group` caption level; the cut uses the `strong` edge role's
weight; slice separators the `weak` role.

## Layout sketch

1. Column width: equal, `(canvas − gutters) / n`; cards wrap to it. A label that cannot
   wrap into it (one long word) → `FitError`.
2. Each cell is a vertical stack of cards with the theme's gap; a row's height is its
   tallest cell. Without rows, one implicit row.
3. Headings above columns; slice labels in a left margin column sized to the widest.
4. Cards of a cell are top-aligned, so a short column looks short — the emptiness is
   information on a kanban board.

## Acceptance tests to write

* Reference documents for the three use cases.
* Limit counting: 3 cards, limit 2 → heading text `3 / 2` in `emphasis`; 2 cards → `2 / 2`
  in the column's own role.
* Cut rule present under the named row and nowhere else.
* Card order inside a cell equals written order.
* Every refusal above, `edges` with the `flow`/`lanes` hint.
* No line primitive other than separators, rules and card borders (no connectors).
