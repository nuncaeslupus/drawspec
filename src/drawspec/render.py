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
5. **Clear**: break every stroke that would be drawn through a word, which is the
   one defect a family cannot see because it only knows its own primitives.
6. **Emit**, which is the only place styling happens and therefore the only place
   embedding safety is enforced.

Every failure has its own type and is raised as early as it can be detected, so
an author working blind gets the most specific message available rather than a
downstream symptom.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

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
        # binding, because a build renders one document at several widths.
        resolved = replace(resolved, canvas=replace(resolved.canvas, width=document.width))

    measurer = TextMeasurer(resolved.font.stacks())
    fitted = fit(
        resolved,
        lambda scaled: _within_height(scene_for(document, scaled, measurer), document),
    )
    placed = centred(fitted.value, fitted.theme)
    return emit(cleared(placed, fitted.theme, measurer), fitted.theme, profile)


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


__all__ = ["centred", "render", "render_document", "render_file"]
