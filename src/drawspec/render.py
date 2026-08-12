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
5. **Emit**, which is the only place styling happens and therefore the only place
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

from drawspec.emit import emit
from drawspec.geometry import fit
from drawspec.kinds import scene_for
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
    fitted = fit(resolved, lambda scaled: scene_for(document, scaled, measurer))
    return emit(fitted.value, fitted.theme, profile)


def render_file(
    path: str | Path,
    theme: Theme | str | Path | None = None,
    profile: str = "inline",
) -> str:
    """Read a JSON document from `path` and render it. See `render`."""
    from drawspec.schema import load_document

    return render_document(load_document(path), theme, profile)


__all__ = ["render", "render_document", "render_file"]
