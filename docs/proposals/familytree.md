# Proposal: `familytree`: people, couples and their children, generation by generation

Status: **built** (see *As built* at the end). Proposed as `pedigree`; the owner named
the kind `familytree`, the most-used term in the round-2 corpus (F1–F4). **Pedigree**,
the only name in genetics and medicine, is recorded in the docs as the clinical name for
the same kind. It comes from `docs/research/kinds-survey.md` (rank 5).
Size **L**: a new layout family. Generations are ranks, but a child hangs from a
*couple*, not from a person, and partners must share a row. The layered ranker
cannot express either.

## Why

Three audiences draw the same figure:

* **Biology teaching and genetic counselling**, where the inheritance pedigree is
  standard. Each person is a square, a circle or a diamond, shaded when affected and
  half-shaded or dotted when a carrier, with an arrow at the proband. Generations carry
  roman numerals and people are numbered within each one (II-3).
* **History**: a dynasty's succession, where who married whom and which marriage
  produced the heir are the content.
* **Personal genealogy**: the family tree people draw for a reunion.

`tree` refuses all three. It takes one edge per child, so a child cannot have two
parents, and a partner who married in has no parent edge and floats. `flow` can join
anything, but it ranks partners on different rows and draws a mesh of arrows where the
convention is one line between partners and one line down to their children.

The **numbering is derived**, which makes this worth a kind rather than a picture.
"II-3 is an obligate carrier" in the text of a counselling letter refers to a number
the layout assigns. An author who numbers by hand gets it wrong when someone is added.

## Use cases

### 1. Course notes: an autosomal recessive condition

```json
{
  "version": 1,
  "kind": "familytree",
  "title": "A recessive condition skips a generation",
  "people": [
    {"id": "gf", "sex": "male"},
    {"id": "gm", "sex": "female", "status": "carrier"},
    {"id": "f", "sex": "male", "status": "carrier"},
    {"id": "aunt", "sex": "female"},
    {"id": "m", "sex": "female", "status": "carrier"},
    {"id": "c1", "sex": "female"},
    {"id": "c2", "sex": "male", "status": "affected", "proband": true},
    {"id": "c3", "sex": "female", "status": "carrier"}
  ],
  "couples": [
    {"between": ["gf", "gm"], "children": ["f", "aunt"]},
    {"between": ["f", "m"], "children": ["c1", "c2", "c3"]}
  ]
}
```

`m` has no parents in the document, so she is placed in her partner's generation. The
key under the drawing lists only the statuses used: affected, carrier, unaffected.

### 2. Clinic letter: an X-linked condition through a mother

```json
{
  "version": 1,
  "kind": "familytree",
  "title": "Family history, maternal side",
  "people": [
    {"id": "mgf", "sex": "male", "status": "affected", "deceased": true, "text": "d. 61"},
    {"id": "mgm", "sex": "female"},
    {"id": "mother", "sex": "female", "status": "carrier", "text": "obligate carrier"},
    {"id": "uncle", "sex": "male"},
    {"id": "father", "sex": "male"},
    {"id": "patient", "sex": "male", "status": "affected", "proband": true, "text": "referred, age 8"},
    {"id": "sister", "sex": "female", "text": "untested"},
    {"id": "preg", "sex": "unknown", "text": "16 weeks"}
  ],
  "couples": [
    {"between": ["mgf", "mgm"], "children": ["mother", "uncle"]},
    {"between": ["father", "mother"], "children": ["patient", "sister", "preg"]}
  ]
}
```

`text` is the short line under a symbol. The symbol carries the name and the number,
so `text` is an aside: an age, a test result.

### 3. History notes: one king, three marriages, three heirs

```json
{
  "version": 1,
  "kind": "familytree",
  "title": "Henry VIII's heirs, by marriage",
  "people": [
    {"id": "h7", "sex": "male", "text": "Henry VII"},
    {"id": "eliz", "sex": "female", "text": "Elizabeth of York"},
    {"id": "h8", "sex": "male", "text": "Henry VIII", "role": "emphasis"},
    {"id": "marg", "sex": "female", "text": "Margaret"},
    {"id": "cat", "sex": "female", "text": "Catherine of Aragon"},
    {"id": "anne", "sex": "female", "text": "Anne Boleyn"},
    {"id": "jane", "sex": "female", "text": "Jane Seymour"},
    {"id": "mary", "sex": "female", "text": "Mary I"},
    {"id": "e1", "sex": "female", "text": "Elizabeth I"},
    {"id": "ed6", "sex": "male", "text": "Edward VI"}
  ],
  "couples": [
    {"between": ["h7", "eliz"], "children": ["h8", "marg"]},
    {"between": ["h8", "cat"], "children": ["mary"], "separated": true},
    {"between": ["h8", "anne"], "children": ["e1"], "separated": true},
    {"between": ["h8", "jane"], "children": ["ed6"]}
  ]
}
```

No `status` is used, so no key is drawn and no person is shaded. In genealogy the
figure is a family tree with the same geometry.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `people` | root | **yes**, 1–20 | `{id, sex, text?, status?, deceased?, proband?, role?}`. `sex` is `male`, `female` or `unknown` and selects square, circle or diamond, following the published standard nomenclature. `status` is `affected`, `carrier` or `unaffected` (the default): full fill, the theme's carrier mark (half-fill pattern or centre dot, `[pedigree] carrier`), or empty. `deceased` draws the diagonal stroke. `proband` draws the arrow at the lower left. |
| `couples` | root | no | `{between: [a, b], children?, separated?, consanguineous?}`. `between` is unordered: the layout puts partners left to right. `children` is ordered, by birth order as written. `separated` draws the double slash across the partner line, and `consanguineous` a double partner line. |

## Refused, and why

| Refused | Why |
|---|---|
| A person who is a child in two couples | One set of parents per person. Adoption is a later feature, with an original. |
| A cycle (someone their own ancestor) | At the pointer of the couple that closes it. |
| `between` naming the same person twice, or the same pair twice | At its pointer. |
| A person in more than 3 couples | Partners are drawn on both sides of the person, and past three the lines cross. Budget. |
| Partners whose parents put them in different generations | They cannot share a row. The message names both people and their generations. This is rare, and such a figure needs a drawn original first. |
| Generation numbers or individual numbers written by the author (`generation`, `number`) | They are derived. Refused by name, with that reason. |
| More than 20 people or 4 generations | Budget. Split by branch of the family. |
| Emotional-relationship lines (genogram's close, conflicted, cut-off) | Out of scope for this proposal: they form a mesh between any two people. A genogram's structure, which is this kind, is in scope. |
| `edges`, `groups` | The structure is `couples`. |

## Roles

Shape and fill are fixed by the standard, through `sex` and `status`, and the theme
draws each only as the standard allows: no colour is needed. `role` adds `emphasis`
(bold label: the person the figure is about, when not a proband) and `note`. At most
two `emphasis`, as everywhere.

## Layout sketch

1. **Generations.** People with no parents in the document and no partner who has
   parents are generation I. A child is one generation below its couple. A partner with
   no parents takes their partner's generation. A conflict is refused (above).
2. **Order within a generation.** Sibling groups go in birth order. A sibling who has a
   partner is placed at the edge of the sibling group nearest the partner's family,
   with the partner beside them, so a partner line never crosses a sibling line. This
   is a crossing-minimising sweep over the generations, using the layered engine's
   barycentre pass with couples as single units.
3. **Lines.** Each couple has a horizontal partner line between the two symbols. A
   descent line drops from its middle to a sibship line, and short drops run from that
   to each child. A person with several couples has partners alternating right, left,
   right in the order written.
4. **Numbering.** Roman numerals at the left of each generation. Individuals are
   numbered 1… left to right within their generation, under the symbol, above `text`.
5. **Key.** A key of the shapes and statuses actually used, under the drawing, as
   `matrix` draws its key.

## Acceptance tests to write

* Reference documents for the three use cases, rendered and looked at against the
  drawn originals collected first.
* Partners share a row, and every child is exactly one row below its couple.
* No partner line crosses a sibship line in any reference (geometry check).
* The derived numbers are stable: adding a person at the end of a generation changes
  no existing number in earlier generations.
* Every refusal above, at its pointer, including the derived-number fields refused by
  name.
* Greyscale: affected, carrier and unaffected are told apart without colour.

## As built

Checked against the round-2 corpus (F1–F7). Clinical and exam pedigrees (F5, F7) fit as
proposed; history trees (F1, F2) needed many partners and half-siblings; the
genealogist's ancestor chart (F3) is a different figure. What changed or was decided:

* **Named `familytree`** (the owner's decision, from the corpus count); *pedigree* is
  the alias in `AGENTS.md`, the guide and the reference.
* **`sex` stays, and `gender` is added, minimally** (F6, the 2022 revision of the
  standard). Without `gender` the symbol is `sex`'s square, circle or diamond, as the
  proposal had it. With `gender` (`man`, `woman`, `nonbinary`) the symbol shows the
  gender, as the 2022 standard draws it, and the sex assigned at birth is written under
  it (`AMAB`, `AFAB`) only when the two differ. One optional field: an author who
  writes neither gets the 2008 figure, and the 2022 one costs a single word. No
  `UAAB`, no intersex annotations: no original asked for them.
* **Partners: 6, not 3** (F1, Henry VIII). Two partners sit one on each side; with
  more, the first is on the left and the rest on the right in marriage order. The
  line to each partner past the second runs over the row on a level of its own, the
  farthest highest, leaving the person's top right of centre, and its descent drops
  through the gap just before that partner: so no line crosses another (left-alternating
  would cross from the third on). Two limits follow and are refused with the reason:
  past two partners, only the first may have parents in the tree (a drop from above
  into a later partner would cross the lines over the row); and two people who both
  have other partners cannot be partners of each other (a row draws one person's
  partners beside them).
* **People: 30, not 20; generations: 4** (F4's royal tree has about thirty in four).
  Budget `people` 30; generations and partners are checked with the couples.
* **Added, from F5:** `twins` on a couple (`of` 2–3 children written together,
  `zygosity` `monozygotic` — a bar between the lines — `dizygotic` or `unknown`, a `?`),
  `consultand` (the arrow without the `P`; the proband is one per tree),
  `pregnancy: ongoing` (a `P` in the symbol) and `pregnancy: loss` (a small triangle,
  shaded when affected). A loss is a field of its own rather than a `status`, because
  a loss can itself be affected. Both are children only. **Adoption** (`adopted`) is
  in: brackets round the symbol and a dashed drop from the couple that raised them,
  which is also the answer to "a child in two couples", still refused, now with that
  pointer.
* **The ancestor-only chart (F3) is refused**, at `/couples`, pointing to `tree`: three
  or more generations in which every couple has one child and some couple's partners
  both have parents. It is a binary tree of one person's forebears.
* **The carrier mark is the theme's** — `[familytree] carrier`, `dot` by default (the
  standard's) or `half` (the exam pedigree's half-shaded heterozygote).
* **The key** lists the statuses when any is used: affected, carrier when used,
  unaffected. Shapes and marks (deceased, proband) are the standard's and not keyed.
* **`emphasis` only**, no `note` role: a person drawn faint has no meaning in the
  standard. `emphasis` draws a heavier symbol and a bold name.
* **Placement.** Households (a person and their partners) are ordered by the
  barycentre of their parents above and children below, sibships kept in birth order,
  a sibling partnered into another family moved to that side; a married-in partner of
  a first-born goes on the outside. Positions are then relaxed person by person, so a
  partner line may lengthen to let each couple's children sit under it; no gap ever
  closes. Overlapping sibship lines take lanes of their own. The sweeps start from
  four orders (as written; families with no parents here first; last; reversed) and
  the drawing with fewest crossing lines wins. The references, and every tree where
  one family marries into another, draw with none; a random stress set of trees where
  several families marry in from both sides still drew one crossing in about one in
  ten. Not refused: it is a heuristic's limit, not a meaning the kind cannot hold.
* **Refused at their pointers**, beyond the proposal's: a person in no couple; two
  families with no couple between them; a second proband; a pregnancy with partners;
  `deceased` on a loss; a shaded ongoing pregnancy; twins not written together or not
  this couple's children; `generation`, `number`, `parents`, `partner(s)`, `spouse`,
  `children` on a person, `edges`, `nodes` and `groups`, each with what to write.

References: `familytree-cousins` (an exam pedigree: a recessive trait and a
consanguineous couple, four generations), `familytree-clinic` (a clinic letter: both
sides, consultand, proband, a loss, a pregnancy, twins), `familytree-tudors` (six
marriages and three heirs), `familytree-reunion` (two marriages, identical twins, an
adoption, a nonbinary grandchild).
