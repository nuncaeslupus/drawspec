# Specification: drawspec — declarative diagram spec to themeable SVG

**Date**: 2026-08-11
**Ticket / PR**: [#1](https://github.com/nuncaeslupus/drawspec/pull/1)
**Author**: drawspec

---

## 1. Problem statement

Language models produce diagrams by emitting SVG with absolute `x`/`y`
coordinates, and they fail at the same things every time. In the 87-diagram
evidence corpus (`corpus/`), **63 drew a complaint from a human reviewer, and
every complaint was about placement, not content**: arrows with a head but no
shaft, text escaping its box, lines stopping short of the shape they point at,
a different font size in every element. These failures cannot be reviewed away
— a cheap mechanical check over finished SVG catches 17 of the 63 and misses
46. Nor can they be prompted away, because the author cannot see the result.
They have to be made *unrepresentable*: the author describes what the diagram
means, and every decision that requires seeing the output is taken by the tool.
drawspec is that tool — a Python library and CLI that takes a declarative
document and emits SVG clean enough to paste inline into a Markdown page,
inheriting the document's colour and surviving greyscale printing.

**Success criteria (measurable)** — each seeds a task Gate in the plan:

- [ ] `unrepresentable_failure_families == 11` — for each of the 11 categorized
      failure families in `docs/brief.md`, a test demonstrates that no valid
      input document can produce it. Judged per family: either the input schema
      has no field that expresses it, or a layout invariant excludes it.
- [ ] `inline_safety_violations == 0` over every generated fixture — no
      `<style>` element, no id that is not prefixed with the document's unique
      namespace, no embedded or referenced external font, no `fill`/`stroke`
      literal outside the values the active theme declares. Mechanically
      checked by the emitter's own validator.
- [ ] `greyscale_ambiguous_role_pairs == 0` — for a theme to load, every pair of
      semantic roles must differ in at least one non-colour channel (shape,
      dash pattern, stroke weight, fill pattern) **or** by a luminance delta
      `>= 0.25` in relative luminance. Checked once per theme at load time.
- [ ] `text_overflow_count == 0` over the regression fixture set — no text run's
      measured advance width exceeds its container's usable width, and no text
      block's measured height exceeds its container's usable height.
- [ ] `system_dependencies == 0` — `pip install drawspec` followed by
      `drawspec render` succeeds in a container with no non-Python binaries
      installed beyond CPython itself.
- [ ] `text_measurement_error_ratio <= 0.02` — for a font with published
      metrics, drawspec's measured advance width for a reference string set is
      within 2% of the value computed from the font's own `hmtx`/`kern` tables
      by an independent reader.
- [ ] `nondeterministic_reruns == 0` — rendering the same document twice with
      the same theme produces byte-identical SVG.
- [ ] `line_coverage >= 0.85`.
- [ ] A document whose content cannot fit at the theme's minimum legible size
      **fails loudly** rather than shrinking type or overflowing. Judged by a
      test asserting a specific exception, not by a number.

## 2. Systems & Impact

drawspec is a greenfield library, so the table maps its own subsystems rather
than existing services. "Needs changes" reads as "must be built".

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `drawspec.schema` | Primary | The input document model and its JSON Schema. Defines what an author *can* say — and, more importantly, what they cannot. | Yes | Every other subsystem reads it. Getting the omissions wrong reintroduces the failure classes. | High |
| `drawspec.text` | Primary | Text measurement: advance widths, line breaking, block height, from a font file. Must work for a font it has never seen. | Yes | The prerequisite for box sizing, pyramid fitting and chart labels. If it is wrong, everything downstream is wrong. | High |
| `drawspec.layout` | Primary | Coordinate assignment for graph-shaped diagrams, behind a swappable engine interface. | Yes | Determines which failure families are excluded structurally vs merely checked. | High |
| `drawspec.routing` | Primary | Orthogonal edge routing, border anchoring, minimum shaft length, label placement. | Yes | Owns 4 of the 11 failure families on its own. No candidate engine does this to the required standard. | High |
| `drawspec.templates` | Primary | Parametric non-graph shapes: pyramid, concentric circles, stack, timeline, column comparison. | Yes | 5 of the 9 diagram types. No graph theory involved; pure geometry plus text fitting. | Medium |
| `drawspec.charts` | Primary | Axis charts: scales, ticks, labels, series. A separate family sharing only theme and text measurement. | Yes | 1 of the 9 types, and the one the corpus did worst. | Medium |
| `drawspec.theme` | Primary | Canvas width, font stack, type scale, padding, stroke scale, role→appearance mapping, greyscale validation. | Yes | The proof that no consumer style is baked in. | High |
| `drawspec.emit` | Primary | SVG serialisation and the inline-safety invariants (id namespacing, `currentColor`, `<title>`/`<desc>`). | Yes | Owns acceptance test 1 outright. | High |
| `drawspec.cli` | Primary | `drawspec render doc.json -o out.svg`, plus `validate` and `theme check`. | Yes | The interface a build pipeline calls. | Low |
| Consuming project | Dependent | Calls the library or CLI, receives SVG files, saves and embeds them. | No | Gains a build step; loses hand-written SVG. Must supply a theme or accept the default. | Low |
| Fonts on the host | Shared resource | Metric source for measurement. | No (validate) | If the named font is absent, measurement must fall back explicitly and say so, never silently. | Medium |

**Impact dimensions.**

- **Data**: none — the tool is a pure function from document to SVG. No storage.
- **API contract**: the input schema is the contract, and it is the thing most
  expensive to change later, because documents written against it live in the
  consumer's repository. Versioned from v1 with an explicit `version` field.
  **High.**
- **Performance**: irrelevant at corpus scale (median 4 nodes, max 17). A
  render should be milliseconds. Not a design constraint. **Low.**
- **User-facing**: the diagrams are the product for the consumer's readers.
  Regressions are visible. **High.**
- **Operational**: adding a system binary dependency would push an install
  burden onto every consumer and every CI job. **Medium**, and it is the reason
  Option C below is not recommended.
- **Risk of inaction**: hand-written SVG keeps producing a ~72% complaint rate
  (63 of 87), with review cost borne by a human on every diagram, forever.

## 3. Options

### The candidate survey

All consulted **2026-08-11**. The question is not "does it draw well" but the
brief's two acceptance tests: (1) does it emit SVG safe to paste inline into
Markdown — no global `<style>`, no colliding ids, no embedded fonts, colour
inherited, greyscale-safe; and (2) can it fix the three worst corpus diagrams.

| Candidate | Licence | How it is driven | What it emits | Test 1 | Notes |
|---|---|---|---|---|---|
| [Graphviz](https://graphviz.org/) | EPL-1.0 | `dot` C binary; `pip install graphviz` gives **bindings only** | SVG, **or coordinates only** via `-Tplain` / `-Tjson` | Fails as SVG; **passes as a coordinate source** | Its `-Tplain` output is positions and edge control points with no styling. Orthogonal routing (`splines=ortho`) exists but is weak and has no port/label-avoidance model. Needs a system binary. |
| [ELK](https://eclipse.dev/elk/) | EPL-2.0 | Java library; [elkjs](https://github.com/kieler/elkjs) is a GWT transpile to JS | **Nothing but coordinates** — ELK does not render, by design | N/A — nothing to fail | The best-designed layout kernel of the set, with real port anchoring. No Python binding; would mean a JVM or a Node process. [elk-rs](https://github.com/openedges/elk-rs) is an early Rust port. |
| [grandalf](https://github.com/bdcht/grandalf) | **GPLv2 *or* EPL-1.0** (dual) | Pure Python, `pip install grandalf` | **Coordinates only** — "it is up to you to actually draw" | N/A — nothing to fail | Sugiyama hierarchical layout in ~600 lines plus a force-directed layout. Version 0.8, lightly maintained. The EPL-1.0 arm of the dual licence is compatible with shipping MIT code around it. |
| [D2](https://d2lang.com/) | MPL-2.0 | Go binary, `d2 in.d2 out.svg` | SVG / PNG / PDF only | **Fails** | Emits a styled standalone document with its own fonts and palette. No coordinate-only output. Adds a Go binary dependency. |
| [Mermaid](https://mermaid.js.org/) | MIT | JS library; CLI needs a headless browser | SVG with embedded `<style>` | **Fails** | Global CSS classes collide when two diagrams share a page — precisely the disqualifier in the brief. Needs Node plus Chromium. |
| [PlantUML](https://plantuml.com/) | GPL | Java jar | SVG with baked colours | **Fails** | GPL plus a JVM. Styling is theme-file driven but the output is not inheritance-friendly. |
| [TikZ/PGF](https://ctan.org/pkg/pgf) | LGPL / GPL | LaTeX toolchain | PDF, SVG via converters | **Fails** | A full TeX installation to render a 4-box diagram. |
| [Kroki](https://kroki.io/) | MIT (service) | HTTP service wrapping the above | Whatever the wrapped tool emits | **Inherits the failure** | Adds a network dependency and inherits each backend's output problems. |
| [yFiles](https://www.yworks.com/) | Proprietary, commercial | Library licence per developer/project | Its own rendering | Not evaluable | The quality bar the brief names, and commercially licensed. Out of scope. |

**What the survey settles.**

1. **No candidate passes acceptance test 1.** Every tool that renders, renders
   to its own taste: global `<style>`, its own palette, its own ids, sometimes
   its own fonts. Post-processing another tool's SVG into inline-safe SVG is a
   permanent tax paid on every release of that tool. **So drawspec owns the
   renderer regardless of which option is chosen.** This is not a decision; it
   is a finding.
2. **The useful candidates are coordinate oracles, not renderers.** Graphviz
   (`-Tplain`), ELK and grandalf all hand back positions and let the caller
   draw. That is exactly the seam drawspec needs, and it makes the layout
   engine a swappable component rather than an architectural commitment.
3. **The dependency question the brief left open has an answer.** `pip install
   graphviz` installs bindings only; the `dot` executable is a separate system
   install. For a library whose whole point is to be called from another Python
   project's build, that pushes an out-of-band binary install onto every
   consumer and every CI job. ELK is worse: a JVM or a Node process.
4. **The corpus is small enough that this matters more than engine power.**
   Median 4 boxes, maximum 17. Graphviz's and ELK's real value is on graphs two
   orders of magnitude larger. At this scale a pure-Python layered layout is
   adequate, and adequacy with no system dependency beats excellence with one.

### Option A: Adopt an existing tool with a post-processing template (Conservative)

- **Description**: Pick D2 or Graphviz, write the declarative format as a thin
  transpiler to its input language, and post-process the emitted SVG into
  inline-safe form — strip `<style>`, rewrite ids, replace colours with
  `currentColor`, drop font declarations.
- **Scope**: A transpiler, an SVG rewriter, a theme mapped onto the upstream
  tool's styling options. No layout, routing, templates or measurement of our
  own.
- **Effort**: Small to start, Medium and rising to maintain.
- **Tradeoffs**: Fastest to a first diagram, and the brief explicitly counts
  this as a success if it works. But post-processing is structurally fragile —
  it is pattern-matching another project's output, and it breaks on their
  releases. Worse, it does not deliver the core promise: text still is not
  measured by us, so box sizing stays the upstream tool's decision, and the
  "text does not fit" family is only *usually* fixed rather than
  *unrepresentable*. Pyramids, concentric circles and axis charts are not
  expressible at all — 3 of 9 types unserved. And it inherits a system binary.
- **Compatibility**: Consumers install a Go or C binary.

### Option B: Own the renderer, pluggable pure-Python layout (Recommended)

- **Description**: drawspec owns the input schema, text measurement, theme,
  routing, templates, charts and SVG emission. Graph layout sits behind a
  narrow `LayoutEngine` protocol — nodes with measured sizes in, coordinates
  out — with a pure-Python implementation as the default. Additional engines
  (Graphviz via `-Tplain`, ELK via a subprocess) become optional extras for
  anyone who has them and wants them on larger graphs.
- **Scope**: All of `src/drawspec/`. The engine boundary is one small protocol,
  making the choice of engine reversible.
- **Effort**: Large — but concentrated where the brief says the real work is
  (style layer, measurement, non-graph shapes), not in reimplementing layout
  research.
- **Tradeoffs**: Most work up front. In exchange: no system dependency, so
  `pip install drawspec` is the whole install story; total control of the SVG,
  so acceptance test 1 is satisfied by construction rather than by rewriting;
  and all three rendering families served by one theme and one measurement
  core. The risk is layout quality — mitigated by the graph sizes actually in
  evidence, and by the escape hatch of a Graphviz engine for anyone who needs
  it. Whether the default engine wraps `grandalf` (EPL-1.0 arm, ~600 lines of
  Sugiyama, lightly maintained) or implements layered layout directly is a
  decision the protocol defers; the prototype should answer it.
- **Compatibility**: Pure Python, 3.12+. One pure-Python runtime dependency for
  font parsing (`fonttools`).

### Option C: Own the renderer, Graphviz as the only layout engine

- **Description**: As Option B, but the layout engine is Graphviz driven via
  `-Tplain`, with no pure-Python fallback.
- **Scope**: Same as B minus the layout implementation, plus a subprocess
  boundary and its error handling.
- **Effort**: Medium.
- **Tradeoffs**: Removes the layout work and gets a battle-tested engine for
  free. But it makes a C binary a hard install requirement for a Python
  library, in exchange for capability the corpus does not need; it introduces a
  subprocess with version-dependent output to parse; and it makes the
  `system_dependencies == 0` success criterion unachievable. Graphviz's
  orthogonal routing is also not good enough to own the arrow failure families,
  so the routing work does not actually go away.
- **Compatibility**: Consumers install Graphviz.

### Comparison

| | A: adopt + post-process | B: own renderer, pluggable layout | C: own renderer, Graphviz only |
|---|---|---|---|
| Effort | Small now, rising | Large | Medium |
| Risk | High — fragile coupling to upstream output | Medium — layout quality, mitigated by graph size | Medium — install burden, subprocess parsing |
| Completeness | 6 of 9 diagram types; failure families mitigated, not excluded | 9 of 9; families excluded structurally | 9 of 9; families excluded structurally |
| Acceptance test 1 | By rewriting, fragile | By construction | By construction |
| Install story | System binary required | `pip install drawspec` | System binary required |
| Maintenance | Tracks another project's releases | Ours | Ours plus a version-sensitive parser |

## 4. Recommendation

**Recommended option: B — own the renderer, pluggable pure-Python layout.**

The survey converts the brief's opening hypothesis ("do not write a layout
engine, wrap one") into something more precise. The half that survives contact
with the evidence is: *do not write a **renderer** around someone else's
opinions* — and the answer there is the opposite of wrapping, because every
candidate's SVG fails the inline-Markdown test and post-processing it is a
permanent tax. The half that does not survive is the assumption that wrapping a
layout engine is cheap: at median 4 and maximum 17 nodes, the engine's power is
not the binding constraint, while its install cost is charged to every consumer
forever. Keeping the engine behind a one-method protocol gets the benefit of
the hypothesis (we can drop Graphviz or ELK in later, and should, if the
default proves inadequate) without paying its cost on day one.

Three consequences worth stating explicitly, because they shape the plan:

- **Three rendering families, one core.** Graph-shaped diagrams (flow, tree,
  cycle) need the layout engine. Grid-shaped ones (stack, timeline, column
  comparison) and parametric shapes (pyramid, concentric circles) need geometry
  and text fitting, not graph theory. Axis charts are a third family again. All
  three share exactly two things: the theme and text measurement. Nothing else
  should be shared, and no chart library (matplotlib included) can be used for
  the third, because their SVG fails acceptance test 1 more badly than the
  diagram tools do.
- **Text measurement is the critical path.** It gates box sizing, pyramid
  fitting and chart labels, and it must work for a font drawspec has never
  seen — read from the font file with `fonttools`, cached, never a hardcoded
  table. The known-hard part is that the rendered font may not be the measured
  font, since the SVG inherits the page's stack; the design must carry an
  explicit safety margin and never rely on a tight fit.
- **The failure families are the acceptance suite.** For each of the 11, the
  plan should name the structural reason it cannot be expressed, and a test
  that demonstrates it.

**Immediate next action**: run `design` to turn this into `status/plan.md` — the
input schema first, since it is the contract everything else reads and the most
expensive thing to change later, then text measurement, then the emitter, then
the three rendering families in that order.

**Open questions**:
- [ ] **Default layout engine**: wrap `grandalf` (EPL-1.0 arm, ~600 lines,
      lightly maintained, v0.8) or implement layered layout directly? Deferred
      behind the `LayoutEngine` protocol; the first prototype of the three
      worst corpus diagrams should settle it.
- [ ] **Theme format**: TOML file, Python object, or both? Leaning TOML so a
      consumer can version a theme without importing drawspec.
- [ ] **Font resolution**: when the theme names a font that is not installed,
      fail, or fall back to a bundled metric-compatible substitute and warn?
      Silence is not an option; which of the other two is a product decision.
- [ ] **Sizing input**: the tool accepts a width and/or height. When both are
      given and the content does not fit, does it fail, or is height advisory
      and allowed to grow? Recommend: width is binding, height advisory unless
      explicitly marked binding.
- [ ] **Diagram titles**: the consumer's style rules leave "Figure 1"-style
      titles undecided. Theme switch, default off.

---

> Sections 5–6 (contracts, risks) are appended by `design`.
