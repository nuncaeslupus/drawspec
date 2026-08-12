"""The exception and warning surface, per specification §5.3.

Every failure drawspec can have is one of these, and each is raised as early as
it can be detected — so an author working blind gets the most specific message
available rather than a downstream symptom.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class DrawspecError(Exception):
    """Base class for every drawspec failure."""


class DocumentError(DrawspecError):
    """The input document violates the schema.

    Carries every violation found, not just the first, each located by JSON
    pointer — so `drawspec validate` can print a document's whole story in one
    pass and an author fixes it in one edit rather than five.
    """

    def __init__(self, message: str, violations: Sequence[Any] = ()) -> None:
        super().__init__(message)
        self.violations: tuple[Any, ...] = tuple(violations)


class LayoutError(DrawspecError):
    """A layout engine could not produce a valid arrangement.

    Raised by the engine rather than swallowed, so a malformed graph or an engine
    that cannot cope surfaces as itself rather than as a drawing with boxes on top
    of each other.
    """


class ThemeError(DrawspecError):
    """A theme is malformed, or two of its roles are distinguishable only by
    colour.

    Raised at load time rather than at render time: greyscale safety is a
    property of the theme, so it is checked once per theme instead of once per
    diagram at review.
    """


class EmitError(DrawspecError):
    """The emitter refused to produce SVG.

    Either a primitive carries a role the theme does not declare — a programming
    error in a rendering family, since a scene is built by drawspec and not by
    the author — or the SVG it was about to return failed its own embedding-safety
    check. Both are refusals rather than warnings: bad SVG that reaches a page is
    found by a reader, not by a test.
    """


class FitError(DrawspecError):
    """Content cannot fit at the theme's minimum legible size.

    Raised rather than shrinking type past the band or letting text overflow:
    the tool says restructure the diagram.
    """


class FontSubstitutionWarning(UserWarning):
    """A named font could not be resolved and a substitute was measured instead.

    A warning rather than an error, because a missing font is not a reason to
    refuse to render — but never silent, because the substitute's metrics differ
    from the ones the author expected. Promote it with::

        warnings.simplefilter("error", FontSubstitutionWarning)
    """


__all__ = [
    "DocumentError",
    "DrawspecError",
    "EmitError",
    "FitError",
    "FontSubstitutionWarning",
    "LayoutError",
    "ThemeError",
]
