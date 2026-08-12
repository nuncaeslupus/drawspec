# Theme requirements

These are the style rules of the consumer whose corpus drives drawspec,
translated into English and stripped of references to their content. They are
here for one reason: **they are the worked example of what a configurable theme
has to be able to express.** If drawspec cannot express all of this through
theme configuration alone — with none of it hardcoded — the theme layer is not
finished.

Each rule below is followed by what it implies for the tool. The rules
themselves are the consumer's; the implications are ours.

---

## 1. A fixed width, first of all

All diagrams are drawn to the same width. This is the decision every other one
hangs from: without a shared width, each diagram scales differently when
displayed, and the same `font-size` ends up looking enormous in one and tiny in
another.

From which it follows:

- Type size and stroke weight in the final result are **comparable across
  diagrams**, not just within one.
- A content-heavy diagram **may** drop its type size, but always within the
  legible range, and with **one size per hierarchical level** inside the same
  diagram.
- If the content does not fit at the minimum legible size, **the diagram is
  badly conceived**: change its shape (to vertical, to another structure), do
  not shrink the type until it fits.

> **Implication.** The theme owns the canvas width; the author does not. Type
> scale is derived from the width, not set per element. Not fitting at the
> minimum size is a **hard error that refuses to emit**, not a silent shrink —
> the tool's job there is to say "restructure this", not to produce something
> unreadable.

## 2. Typography

- **The same family as the surrounding document**, not whatever the viewer
  defaults to.
- **One size per level**: diagram title, box heading, box body, edge label. Four
  sizes, not fourteen.
- **Bold and italic mean something or are not used.** If bold marks the main
  concept, it marks it the same way in every diagram.
- **Anything that is a command goes in monospace.** It is the only way to
  distinguish a literal command from prose.
- **Sentences start with a capital.**
- Do not split a sentence in half to fit the rest in a smaller size: either it
  fits, or it is rethought.

> **Implication.** The theme declares a font stack and a four-step type scale
> keyed to semantic level. The author picks a level by naming a role, never a
> size. A monospace role exists as a text span type. Text measurement must work
> for whatever font the theme names, including one drawspec has never seen.

## 3. Colour

- **Colour is optional; legibility in greyscale is not.** Every diagram must
  convert to greyscale without losing information: if two elements are
  distinguishable only by colour, they are wrong.
- Where there is colour, it is **the document's** (its CSS variables), not a
  per-diagram palette.
- **Hatching and patterns stay soft.** A hatch that competes with the text on
  top of it makes it illegible.

> **Implication.** Two colours that differ enough in *luminance* do survive
> greyscale, so the check is a luminance-delta threshold, not a ban on colour.
> But luminance alone is fragile, so any two semantic roles must also differ in
> at least one non-colour channel: shape, dash pattern, stroke weight, or fill
> pattern. This is checkable once per theme, at build time, rather than per
> diagram at review time.

## 4. Boxes

- **Enough inner margin on all four sides**, and **especially at the bottom**:
  the single most repeated failure in the whole review.
- **Regular line spacing** inside the box. No tight lines next to loose ones in
  the same block.
- **Text vertically centred** in the box, unless there is a reason otherwise.
- **Text never escapes its box.** If it does not fit: break into more lines,
  widen the box, or rethink. Never leave it overflowing.
- **Boxes at the same level aligned** and the same size when they represent the
  same kind of thing.
- Rounded or square corners: **pick one and apply it to all**.

> **Implication.** Box geometry is derived from measured text plus theme
> padding. Same-rank nodes are normalised to a common size by the layout pass,
> not by the author. Corner radius is a theme constant.

## 5. Arrows and lines

Where most of the failures were. Five rules:

1. **Every arrow has a shaft and a head**, and the shaft has **visible length**.
   A loose head stuck to a box is not an arrow.
2. **If the arrows do not fit horizontally, the diagram goes vertical.**
   Squeezing the content until the arrow loses its shaft is the cause, not the
   symptom.
3. **Right angles, not diagonals.** A diagonal lands on the target box at a
   sharp angle and looks wrong. Orthogonal routes are the norm.
4. **Lines start and end touching the box.** Neither short nor overshooting.
5. **No line crosses a box or other text.** If the route forces a crossing, the
   diagram needs a different arrangement — usually vertical.

And: **uniform weight**. All arrows of the same type, the same weight.

> **Implication.** Edges are anchored to node borders by construction. A minimum
> shaft length is a layout constraint that can force extra rank separation —
> which means rule 2 is automatic: when the arrows will not fit, the layout
> flips the flow direction rather than shrinking the gap. Orthogonal routing is
> the default; the author cannot request a diagonal.

## 6. Specific shapes

**Concentric circles.** Each ring's text is **shifted downwards** so it does not
touch its own circle. Only the innermost circle's text is centred.

**Pyramids.** Regular proportions: every level the same height, with a constant
width progression. The text fits inside its level without crossing the sloped
sides.

**Cycles.** If it is a cycle, it should look like one: steps spaced evenly,
arrows all following the same direction, no crossings.

> **Implication.** These are parametric templates, not graph layout. The
> pyramid's text-fitting constraint is the interesting one: the usable width at
> a given height is a function of the slope, so text measurement feeds the
> template just as it feeds box sizing.

## 7. Charts

When the diagram is a chart rather than a diagram:

- **Both axes are labelled.** An unlabelled axis cannot be read.
- **Text orientation decided and constant**: the vertical axis label rotated,
  the horizontal one horizontal, the same in every chart.
- **Point labels do not cross the curve** or leave the plot area.
- Marked points **land on the line**, not beside it.

> **Implication.** A third rendering family, sharing the theme and the text
> measurement but nothing else. An unlabelled axis is a validation error.

## 8. Still undecided

- **Do diagrams carry their own title, "Figure 1" style?** Raised and left open.
  Until it is decided, none is added.

> **Implication.** The theme has to support both, defaulting to off.

---

## What this tells us about the theme's shape

Reading the list back, a theme is roughly: a canvas width, a font stack, a
four-step type scale, a padding scale, a stroke scale, a corner radius, a
minimum legible size, a set of semantic roles each mapping to a (shape, stroke,
dash, fill) tuple, and a small number of on/off switches. Nothing in that list
is specific to any subject matter — which is the proof the brief asks for that
the consumer's style is not baked into the tool.
