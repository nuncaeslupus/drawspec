"""The public entry point: a document and a theme in, an SVG string out.

drawspec is a pure function, and this is it. The order of operations is the whole
design in one place:

1. **Parse** the document, rejecting every field the author must not control.
2. **Load** the theme, rejecting any pair of roles a greyscale reader could not
   tell apart.
3. **Fit**: find the largest factor in the theme's band at which the content fits,
   applying it to all four type levels together, and raise `FitError` if there is
   none rather than shrinking past the band or letting text overflow.
4. **Render** to a `Scene` with whichever family the kind selects.
5. **Frame**: centre the drawing on the canvas and give it the theme's outer
   margin on all four sides — the two things about a figure's edge that must be
   the same for every kind, and were not while each family decided its own.
6. **Clear**: break every stroke that would be drawn through a word, which is the
   one defect a family cannot see because it only knows its own primitives.
7. **Emit**, which is the only place styling happens and therefore the only place
   embedding safety is enforced.

Every failure has its own type and is raised as early as it can be detected, so
an author working blind gets the most specific message available rather than a
downstream symptom.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from drawspec.clearance import cleared
from drawspec.emit import emit
from drawspec.errors import FitError
from drawspec.geometry import fit
from drawspec.kinds import scene_for
from drawspec.scene import Scene, moved
from drawspec.schema import Document, parse_document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme, load_theme


def render(
    document: Mapping[str, Any],
    theme: Theme | str | Path | None = None,
    profile: str = "inline",
) -> str:
    """Render a document mapping to SVG.

    Args:
        document: the document, as parsed from JSON or built in Python.
        theme: a `Theme`, a bundled theme name, a theme file path, or None for the
            default. A `theme` named by the document is used when this is None.
        profile: `inline` (default) or `standalone` — see `drawspec.emit`.

    Raises:
        DocumentError: the document violates the schema, with the offending
            field's JSON pointer.
        ThemeError: the theme is malformed or greyscale-ambiguous.
        FitError: the content cannot fit at the theme's minimum legible size.
        EmitError: a primitive names a role the theme does not declare, or the
            SVG failed its own embedding-safety check.
    """
    return render_document(parse_document(document), theme, profile)


def render_document(
    document: Document,
    theme: Theme | str | Path | None = None,
    profile: str = "inline",
) -> str:
    """Render an already-parsed `Document`. See `render`."""
    resolved = load_theme(theme if theme is not None else (document.theme or None))
    if document.width:
        # The document may override the canvas width and nothing else: width is
        # binding, because a build renders one document at several widths. It is
        # put on the theme here and read from there by everything downstream, so
        # a family never has to ask which of the two won — and so the margin
        # below comes out of whichever width that was.
        resolved = replace(resolved, canvas=replace(resolved.canvas, width=document.width))

    measurer = TextMeasurer(resolved.font.stacks())
    fitted = fit(
        resolved,
        lambda scaled: _within_height(
            _within_width(scene_for(document, scaled, measurer), scaled), document
        ),
    )
    placed = framed(centred(fitted.value, fitted.theme), fitted.theme)
    return emit(cleared(placed, fitted.theme, measurer), fitted.theme, profile)


#: How far over the canvas a drawing may measure before it is refused, in user
#: units. Not a tolerance for overflow — a hundredth of a unit is a rounding
#: difference between two ways of adding up the same layout, and is a tenth of a
#: rendered pixel at any size these are read at.
_WIDTH_EPSILON: Final = 0.01


def _within_width(scene: Scene, theme: Theme) -> Scene:
    """`scene`, or a `FitError` when it is wider than the canvas it must share.

    A family checks its **layout** against the width — `max_width` on the graph
    engine, an equal share per column, a plot area — but the drawing is not the
    layout. A back edge routed around the outside, an edge label placed left of
    the leftmost box, a band's bar and name beside the chain: all of these are
    measured *after* placement and none of them is in any family's budget. So a
    layout that exactly fills the width produces a drawing that does not fit in
    it, and `centred` leaves a scene already at or over the canvas alone — by
    design, since its whole job is to add margin rather than remove it. The
    oversized scene goes straight out as an oversized `viewBox`.

    That breaks the one property this project checks across kinds rather than
    within one: `canvas_width_variance == 0`. A figure 90 units wider than its
    neighbours is read at a different type size on the same page, which is the
    corpus's most repeated complaint arriving by the back door.

    Checked here, once, for every kind — the same argument `_within_height`
    makes, and the same lever: raising `FitError` inside the fit loop makes the
    elastic fit try a smaller type scale first and only then refuse. A family
    doing its own checking would have to reimplement that, and the two that
    produce ink outside their own placements would have had to agree.

    `width_mode = "ink"` is exempt, because a drawing sized on its own has no
    canvas to overflow — that is what the setting means.
    """
    if theme.canvas.width_mode != "fixed":
        return scene
    if scene.width > theme.canvas.width + _WIDTH_EPSILON:
        raise FitError(
            f"this drawing measures {scene.width:.0f} units across and the canvas is "
            f"{theme.canvas.width:.0f}. What is over the edge is drawn beside the boxes "
            f"rather than by them — a label, a back edge, a band's name — so it is not in "
            f"the layout's own budget. Shorten the longest label, split the diagram, or "
            f"give it more width."
        )
    return scene


def framed(scene: Scene, theme: Theme) -> Scene:
    """`scene` in its channel of blank: the theme's outer margin, on all four sides.

    The one place a drawing is given that channel. Every family used to decide it
    for itself and they disagreed — 24 units for a flow chart, 10 for a cycle,
    none at all for a stack — which is invisible in any one diagram and obvious
    the moment two of them share a page: a timeline above a flow chart bled to the
    edge beside a quarter-inch of white.

    It goes **around** `[canvas] width` rather than being taken out of it, and
    that is the whole of the difference between the two ways to do this. Taken
    out, every drawing loses the margin from its layout budget: the families that
    deliberately span the canvas would each need to know about it, and a timeline
    already within ten units of the width its own tick spacing demands stops
    fitting — a document that used to draw would refuse, because the theme grew a
    frame. Added around, `width` keeps meaning the width of the *drawing*,
    `height` and `height_binding` keep meaning the height of the drawing, no
    layout budget moves, and the emitted canvas is `width + margin * 2` for every
    kind alike. Two diagrams on one page are still one width, which is the
    property `width` exists for.

    Applied after `centred`, because centring is what makes the drawing the
    canvas's width; framing before it would hand `centred` a scene already wider
    than the canvas and it would decline to centre anything.
    """
    margin = theme.canvas.margin
    if not margin:
        return scene
    return replace(
        scene,
        width=scene.width + margin * 2,
        height=scene.height + margin * 2,
        primitives=tuple(moved(primitive, margin, margin) for primitive in scene.primitives),
    )


def _within_height(scene: Scene, document: Document) -> Scene:
    """`scene`, or a `FitError` when a binding height is not met.

    This is what makes `height_binding` bind. The field was parsed, documented as
    "makes height a constraint rather than a hint", and then read by nothing at
    all: a four-node flow asking for `height: 80` came back 340 units tall, exit
    0, no refusal — the third outcome the format page promises never to produce.

    It is enforced here rather than in each family because the answer is the same
    for all of them, and because *here* is where the lever already exists: raising
    `FitError` inside the fit loop makes the elastic fit try a smaller type scale
    and then refuse, which is what a constraint on a rendered size means. A family
    doing its own checking would have to reimplement that, and six of the kinds
    would have forgotten to.

    `height` on its own stays advisory, which is what it says. Only the chart
    kinds read it as a plot height, and none of them treated it as a ceiling.

    **It bounds the drawing, not the emitted canvas** — the file comes out
    `margin * 2` taller, the same way a `width` of 640 comes out a 664-wide file.
    That is deliberate and it is what keeps the two fields meaning the same kind
    of thing: `[canvas] margin` frames the drawing from outside, so both `width`
    and `height` describe what is inside the frame. Bounding the canvas here
    instead would make a binding height quietly shrink whenever a theme widened
    its margin, which is the coupling the frame was moved out of the families to
    remove.
    """
    if not document.height_binding or not document.height:
        return scene
    if scene.height > document.height:
        raise FitError(
            f"this drawing is {scene.height:.0f} units tall and `height_binding` asks "
            f"for {document.height:.0f}. Give it more height, drop `height_binding` to "
            f"make the height advisory again, or restructure the diagram — usually "
            f"fewer ranks, or a wider canvas so each rank holds more."
        )
    return scene


def centred(scene: Scene, theme: Theme) -> Scene:
    """`scene` on the theme's canvas, its drawing centred — the last step before SVG.

    One line of the pipeline, and it is what makes the theme's single canvas
    width mean anything. A family produces a drawing as wide as it needed to be;
    this puts that drawing on the canvas every other diagram is also on, so two
    diagrams in one document are read at one type size instead of at whatever
    each one's own width happens to scale to. See `Canvas.width_mode`.

    Done here rather than in each family for the usual reason: a family that
    forgot would be wrong in a way only a reader with two diagrams open could
    see. A drawing already at or over the canvas width is returned untouched, so
    this can only ever add margin.
    """
    if theme.canvas.width_mode != "fixed" or scene.width >= theme.canvas.width:
        return scene
    return _shifted(scene, (theme.canvas.width - scene.width) / 2, theme.canvas.width)


def _shifted(scene: Scene, offset: float, width: float) -> Scene:
    """Every primitive moved right by `offset`, on a canvas `width` wide."""
    return replace(
        scene,
        width=width,
        primitives=tuple(moved(primitive, offset, 0.0) for primitive in scene.primitives),
    )


def render_file(
    path: str | Path,
    theme: Theme | str | Path | None = None,
    profile: str = "inline",
) -> str:
    """Read a JSON document from `path` and render it. See `render`."""
    from drawspec.schema import load_document

    return render_document(load_document(path), theme, profile)


__all__ = ["centred", "framed", "render", "render_document", "render_file"]
