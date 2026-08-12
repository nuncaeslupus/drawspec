"""drawspec — declarative diagram spec to clean, themeable SVG."""

from __future__ import annotations

from drawspec.errors import DrawspecError, FitError, FontSubstitutionWarning, ThemeError
from drawspec.theme import Theme, load_theme

__version__ = "0.1.0"

__all__ = [
    "DrawspecError",
    "FitError",
    "FontSubstitutionWarning",
    "Theme",
    "ThemeError",
    "__version__",
    "load_theme",
]
