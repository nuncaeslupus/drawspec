"""The exception and warning surface, per specification §5.3.

Every failure drawspec can have is one of these, and each is raised as early as
it can be detected — so an author working blind gets the most specific message
available rather than a downstream symptom.
"""

from __future__ import annotations


class DrawspecError(Exception):
    """Base class for every drawspec failure."""


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
    "DrawspecError",
    "FitError",
    "FontSubstitutionWarning",
]
