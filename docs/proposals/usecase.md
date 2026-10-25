# `usecase` — who uses a system for what

A UML use case diagram: the actors outside a system's boundary, the use cases they
reach with it inside, and the relations between them. It is the first drawing of most
requirements documents and of every software-engineering course's analysis chapter, and
the owner asked for it with the other kinds borrowed from Mermaid, PlantUML and D2.

Nothing drawspec draws says it today. A `flow` can put ellipses in a group and people
beside it, but it routes on a grid, it has no stick figure, its edges say *then this
happens*, and nothing stops a line leaving the boundary and coming back. A `sequence`
has the actor's figure and says *in what order*; a use case diagram says *who reaches
which goal* and nothing about order.

## The originals

Found by web search on 2026-10-25 and cited as the search results gave them. The
pages were not opened here — outbound fetches are blocked in this environment — so what
each shows is as the search result summarised it, and is worth a look before the PR
merges.

| # | Original | What it shows | What it asks of the design |
|---|---|---|---|
| U1 | The UML specification's *Use Cases* chapter (chapter 18 of UML 2.5: [OMG, UML 2.5 Beta 1](https://www.omg.org/spec/UML/2.5/Beta1/PDF); the chapter confirmed by [issue UML25-419](https://issues.omg.org/issues/UML25-419), on 18.1.3 *Extends*) | The notation itself: actors as stick figures, use cases as ellipses, the subject as a rectangle, associations, «include» and «extend» as dashed arrows, generalisation with a hollow triangle | The four relations and nothing else; an extending use case may extend more than one, and may itself be extended — so a chain of columns |
| U2 | Stevens and Pooley, *Using UML*, the book's figures ([homepages.inf.ed.ac.uk/perdita/book/allfigsU.pdf](https://homepages.inf.ed.ac.uk/perdita/book/allfigsU.pdf)) | A library: *BookBorrower* and *Librarian*; *Borrow copy of book* «include» *Check for reservation*; *Refuse loan* «extend» *Borrow copy of book* | Include and extend out of the same base, in opposite directions; the redraw is `usecase-library.json` |
| U3 | PlantUML's use case documentation ([plantuml.com/en/use-case-diagram](https://plantuml.com/en/use-case-diagram)) | `:actor:`, `(use case)`, `rectangle "System" { … }` as the boundary, `-|>` for generalisation, `.>` with `<<include>>` / `<<extend>>` | The input vocabulary an author already knows: ids, a boundary that holds use cases, the keyword as the relation's only label |
| U4 | TU Delft's *Software Systems* UML tutorial ([cese.ewi.tudelft.nl/…/use-case.html](https://cese.ewi.tudelft.nl/software-systems/part-2/tutorials/uml/use-case.html)) | A course diagram with `edit ..> authenticate : <<include>>` | Authentication as the shared included use case — the ATM reference's shape |
| U5 | Microsoft's Visual Studio 2013 UML use case diagram reference ([learn.microsoft.com](https://learn.microsoft.com/sv-se/previous-versions/visualstudio/visual-studio-2013/dd409427(v=vs.120))) | The extend arrow's head is at the extended (base) use case | `extend` is written from the extension to the base, and the arrow points at the base |
| U6 | A tutorial on the four relationships ([creately.com](https://creately.com/blog/diagrams/use-case-diagram-relationships/)) | A descendant actor inherits its ancestor's use cases and adds its own | Actor generalisation, the specialised actor with use cases of its own |

The textbook's library (U2) is redrawn as `usecase-library.json`; an ATM with a
supporting bank and a shared «include» (U3, U4) as `usecase-atm.json`; an online shop's
checkout with two boundaries and a specialised customer (U1, U6) as
`usecase-checkout.json`.

## The design

```json
{
  "version": 1,
  "kind": "usecase",
  "systems": [{"id": "atm", "text": "ATM"}],
  "actors": [
    {"id": "customer", "text": "Customer"},
    {"id": "bank", "text": "Bank", "supporting": true}
  ],
  "usecases": [
    {"id": "withdraw", "text": "Withdraw cash"},
    {"id": "pin", "text": "Authenticate with PIN"},
    {"id": "receipt", "text": "Print receipt"}
  ],
  "edges": [
    {"from": "customer", "to": "withdraw"},
    {"from": "bank", "to": "withdraw"},
    {"from": "withdraw", "to": "pin", "role": "include"},
    {"from": "receipt", "to": "withdraw", "role": "extend"}
  ]
}
```

**The model is the whole input.** Actors (`id`, `text`, optional `supporting`), use
cases (`id`, `text`, `system`), systems (`id`, `text`), and `edges` whose `role` is
`association` (the default), `include`, `extend` or `inherits`. Ids are one namespace.
With one system a use case's `system` may be left out; with none there is no boundary.

**What is derived, never written:**

- *The side.* Primary actors stand left of the boundaries and supporting ones right, as
  the textbooks draw them. `supporting` says which, and left out it is derived: an actor
  whose every use case an actor written before it already has is supporting (the bank
  behind the customer's withdrawal). A specialised actor stands on its parent's side.
- *The column.* A use case that is included, that extends another or that specialises
  one stands a column to the right of it, so every dashed arrow runs across the boundary
  rather than up through the other ellipses.
- *The order down each band.* Candidate placements — the first column stacked, the
  deeper ones level with their bases or each on a row of its own; the first column
  re-sorted by the barycentre of its actors — are each laid out and scored, and then the
  deeper use cases and the actors are tried at other heights. The one kept has no line
  through an ellipse, a figure, a name or a boundary it does not belong to, then the
  fewest crossings, the fewest bends and the least height and line.
- *The lines.* Straight, border to border, as UML draws them. An association that no
  order can clear — typically a supporting actor's line to a first-column use case, with
  the deeper columns between them, or a line to a lower boundary — bends once, in a gap
  between two ellipses or just outside its boundary, so it goes in through the side.
  The search tries straight placements first and allows bends only when they leave a
  line through something; it is capped (`EVALUATIONS`), so a diagram at the budget
  costs a bounded time — a few seconds at worst — and draws the same every time.

**Consistency with the rest of drawspec.** A boundary is a `flow` group's frame
(`containers.frame_primitives`: the `group` role, the `[frames]` wash, the caption in the
corner); the stick figure is the `sequence` actor's (now `kinds.sequence.stick_figure`);
a use case is an ellipse in the `step` role sized by `size_box`; the relations are drawn
in existing edge roles — an association as `link`, «include» and «extend» as `weak` with
the keyword set beside the arrow, generalisation as `inherits`. No new theme section and
no new role.

## What it refuses

Each at its JSON pointer, with the reason:

- an association between two actors (they meet through the use cases they share), or
  between two use cases (which relation: `include`, `extend`, `inherits`?);
- `include`/`extend` touching an actor; `inherits` between an actor and a use case;
- a system as an end; an unknown id (with a suggestion); a relation to itself, or a
  second one between the same two;
- a loop of include, extend and inherits; a chain deeper than three columns; an include
  or extend between two systems;
- an actor that takes part in nothing; a system with no use case; two or more systems
  and a use case that names none;
- an actor that inherits from two, or from one that itself inherits (one level of actor
  generalisation; a second `supporting` against its parent's side);
- `text`/`label` on a relation (the keyword is the role's), `side`, `x`, `y`, `column`,
  `role` on an actor or use case, `nodes`, `groups`, `multiplicity`.

## The limits

8 actors, 15 use cases, 3 systems, 30 relations — the textbook originals hold three to
six actors and about a dozen use cases. Past them the refusal says how to split: one
diagram per kind of user, an overview of goals with a diagram per goal, or one per
subsystem. A diagram wider than the canvas at the narrowest wrap is a `FitError`.

**No text form.** The graph text router (`kinds/graphtext.py`) draws what the layered
engine places on cells; this layout is its own, with diagonal lines and ellipses, and
does not fit it cheaply. `render --format text` refuses it, naming the kinds that have
one.

## Status

**Built.** `src/drawspec/kinds/usecase.py`; schema, validation and the side and column
derivations in `src/drawspec/schema.py`; references `docs/reference/usecase-library.json`,
`usecase-atm.json` and `usecase-checkout.json`; tests in `tests/test_kinds_usecase.py`.

## Open for the owner

1. *Children above and below.* The first two specialisations of an actor stand straight
   above and below it; a third stands a step further out with a diagonal arrow. Fine for
   the originals; a diagram with four specialisations of one actor may want its own rule.
2. *Use case generalisation* puts the child a column right of its parent, as include and
   extend do. Some textbooks draw it below instead.
