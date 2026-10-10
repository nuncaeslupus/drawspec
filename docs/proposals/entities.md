# Proposal: `entities` — data models, schemas and class diagrams

Status: **proposed**. Size **L** (compartment boxes exist; new end treatments, and
edges that land on one row of a box).

## One kind, not three

ER diagrams, database schemas and UML class diagrams are drawn as three things and are
one shape: **a named box with a list inside it, and typed relations between boxes**.
What separates them is the vocabulary:

| Form | What is in the box | What is on the line |
|---|---|---|
| Conceptual / logical ER | attributes, maybe keys | cardinality at each end |
| Physical schema | columns with SQL types, PK / FK / unique | a foreign key from one **column** to another |
| Class diagram | attributes and **operations** | inheritance, realisation, composition, dependency |

So `entities` carries all of these as optional fields, and a document uses the ones it
needs. A reader of course notes sees one consistent drawing language whether the chapter
is about normalisation or about polymorphism.

`tree-compartments` already draws "a name, a rule, the things under it" with the
`compartment` theme; this kind makes the list structured (so a relation can land on a
row) and adds the relation vocabulary.

## Use cases

### 1. Course notes — a lending library, conceptual model

```json
{
  "version": 1,
  "kind": "entities",
  "title": "A library lends copies, not books",
  "caption": "A book is the work; a copy is the thing on the shelf.",
  "entities": [
    {"id": "member", "text": "Member", "fields": [{"text": "member number", "key": "primary"}, {"text": "name"}, {"text": "joined on"}]},
    {"id": "book", "text": "Book", "fields": [{"text": "ISBN", "key": "primary"}, {"text": "title"}, {"text": "author"}]},
    {"id": "copy", "text": "Copy", "fields": [{"text": "barcode", "key": "primary"}, {"text": "shelf mark"}]},
    {"id": "loan", "text": "Loan", "role": "emphasis", "fields": [{"text": "lent on"}, {"text": "due on"}, {"text": "returned on"}]}
  ],
  "edges": [
    {"from": "book", "to": "copy", "from_end": "one", "to_end": "zero-or-many", "label": "is held as"},
    {"from": "copy", "to": "loan", "from_end": "one", "to_end": "zero-or-many", "label": "is lent in"},
    {"from": "member", "to": "loan", "from_end": "one", "to_end": "zero-or-many", "label": "borrows"}
  ]
}
```

### 2. Design document — the order tables, physically

```json
{
  "version": 1,
  "kind": "entities",
  "title": "Orders, as stored",
  "entities": [
    {"id": "customers", "text": "`customers`", "fields": [
      {"text": "`id`", "type": "uuid", "key": "primary"},
      {"text": "`email`", "type": "text", "key": "unique"},
      {"text": "..."}
    ]},
    {"id": "orders", "text": "`orders`", "fields": [
      {"id": "o_id", "text": "`id`", "type": "uuid", "key": "primary"},
      {"id": "o_customer", "text": "`customer_id`", "type": "uuid", "key": "foreign"},
      {"text": "`placed_at`", "type": "timestamptz"},
      {"text": "`status`", "type": "text"}
    ]},
    {"id": "lines", "text": "`order_lines`", "fields": [
      {"id": "l_order", "text": "`order_id`", "type": "uuid", "key": "foreign"},
      {"text": "`sku`", "type": "text", "key": "foreign"},
      {"text": "`quantity`", "type": "integer"},
      {"text": "`unit_price`", "type": "numeric(10,2)"}
    ]}
  ],
  "edges": [
    {"from": "orders", "from_field": "o_customer", "to": "customers", "from_end": "zero-or-many", "to_end": "one"},
    {"from": "lines", "from_field": "l_order", "to": "orders", "to_field": "o_id", "from_end": "one-or-many", "to_end": "one", "label": "on delete cascade", "role": "strong"}
  ]
}
```

`"text": "..."` as the last field says *there are more columns, not shown* — the same
convention `files` uses for a row standing for entries not listed.

### 3. Course notes — shapes, in an object-oriented design

```json
{
  "version": 1,
  "kind": "entities",
  "title": "Every shape can say its area",
  "entities": [
    {"id": "drawable", "text": "Drawable", "tag": "interface", "operations": ["draw(canvas)"]},
    {"id": "shape", "text": "Shape", "tag": "abstract", "fields": [{"text": "origin", "type": "Point"}], "operations": ["area() → float", "move(dx, dy)"]},
    {"id": "circle", "text": "Circle", "fields": [{"text": "radius", "type": "float"}], "operations": ["area() → float"]},
    {"id": "rect", "text": "Rectangle", "fields": [{"text": "width", "type": "float"}, {"text": "height", "type": "float"}], "operations": ["area() → float"]},
    {"id": "picture", "text": "Picture", "operations": ["add(shape)", "total_area() → float"]}
  ],
  "edges": [
    {"from": "shape", "to": "drawable", "role": "realizes"},
    {"from": "circle", "to": "shape", "role": "inherits"},
    {"from": "rect", "to": "shape", "role": "inherits"},
    {"from": "picture", "to": "shape", "role": "owns", "to_end": "zero-or-many"}
  ]
}
```

Note the `fields` entries are named `text`, `type` — never `width`/`height`, which are
refused everywhere: a rectangle's *field* called width would be written `"text":
"width"`, so the refusal never fires on content.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `entities` | root | **yes**, 1+ | `{id, text, tag?, role?, fields?, operations?, note?}`. |
| `tag` | entity | no | A short stereotype drawn above the name in guillemets (`«interface»`). Free text, ≤ 16 characters. |
| `fields` | entity | no | `[{id?, text, type?, key?, note?}]`. `type` is drawn right-aligned in the `code` level; `key` is one of `primary`, `foreign`, `unique`, drawn as a lettered mark (`PK`, `FK`, `UQ`) — a word, never a colour. `id` only needed for an edge to land on it. A last field of `"..."` is a placeholder row. |
| `operations` | entity | no | `array of string`, drawn in a third compartment. Strings, not objects: an operation is read, not linked to. |
| `edges` | root | no | The edge object plus `from_field`, `to_field`, `from_end`, `to_end`. |
| `from_field` / `to_field` | edge | no | The id of a field in the `from` / `to` entity. The line lands on that **row**, at the box side facing the other entity. Without it, it lands on the box. |
| `from_end` / `to_end` | edge | no | What is drawn at that end: `one`, `zero-or-one`, `many`, `zero-or-many`, `one-or-many`. Read as *how many of this end per one of the other*. Drawn as crow's-foot marks by default; a theme may choose `[entities] notation = "crowsfoot" | "numeric"` (`1`, `0..1`, `*`, `1..*`). The author states the cardinality, the theme the notation. |
| `role` | edge | no | `link` (default here — an association has no direction), `owns` (composition, filled diamond), `weak` (dependency, dashed open head), `strong` (the relation that matters), and two **new** edge roles: `inherits` (hollow triangle at `to`) and `realizes` (dashed, hollow triangle). |

## Refused, and why

| Refused | Why |
|---|---|
| `from_end`/`to_end` on `inherits` or `realizes` | Inheritance has no cardinality. |
| An inheritance cycle | Not a class hierarchy. Refused at the edge that closes it. |
| `from_field` naming a field of a different entity | The line would leave a box from a row it does not have. |
| Aggregation (hollow diamond) | Not offered. It is the most misread mark in UML and has no agreed meaning; say `owns` or `link`. Documented in the refusal message. |
| Visibility as a field (`"visibility": "private"`) | Write `- name` in `text` if it matters; a field for it would be a fourth notation for one character. |
| More than **12** fields or **8** operations in one entity | Show the ones the diagram is about and end with `...`. The message says so. |
| More than **8** entities | A schema of thirty tables is a database tool's output. Split by subsystem. |
| `width`, `height`, `port` | Refused everywhere already; `port` is why the field reference is `from_field`. |

## Roles and theme

* Entities: `step` (default), `emphasis` (the entity the diagram is about), `note` (an
  external or out-of-scope entity, drawn lighter). Others refused.
* Theme: the compartment lead (`[box] lead = "rule"`) is forced on for this kind — a name
  over its list is what an entity *is*, so it is not a theme choice here.
* New theme content: end treatments `crowsfoot-one`, `crowsfoot-many`, the two optional
  forms, `triangle-hollow`. Like every end treatment they belong to the theme, so a
  document never names one.

## Layout sketch

1. **Boxes**: header (tag, name), rule, fields (name left, type right, key mark left of
   name), rule, operations. Width = widest row; rows have one fixed height per theme so a
   row-anchored line lands at a predictable y.
2. **Placement**: if there are `inherits`/`realizes` edges, rank them as a `tree`
   (parent above child) and place the remaining entities by the layered engine with all
   other relations treated as undirected. Otherwise, the layered engine on the
   relations, direction across.
3. **Row anchors**: a line with `from_field` leaves at the row's centre on the side
   facing its target; the router treats the row's y as fixed and routes orthogonally from
   there. This is an internal port, never an authored one.
4. **Cardinality marks** sit at the very end, outside the box, so the label goes mid-line.

## Acceptance tests to write

* Reference documents for the three use cases, one per vocabulary.
* A row-anchored edge's endpoint y equals its row's centre; a plain edge lands on the box
  border.
* Crow's-foot marks present at the right end; in `numeric` notation, the right text.
* Every refusal above at its pointer.
* Greyscale: `inherits` vs `owns` vs `link` distinguishable by head shape alone.
* `"..."` as a non-last field refused (as in `files`).

## Open question for the owner

Adding `inherits` and `realizes` to the global edge roles makes them legal in `flow` too,
where they mean nothing. Either accept that (roles are global today), or make edge roles
per-kind. The cheaper answer is to accept it and refuse them outside `entities`.
