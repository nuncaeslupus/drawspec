"""drawspec — declarative diagram spec to clean, themeable SVG."""

from __future__ import annotations

from drawspec.emit import check_embedding_safety, emit
from drawspec.errors import (
    DrawspecError,
    EmitError,
    FitError,
    FontSubstitutionWarning,
    ThemeError,
)
from drawspec.scene import Ellipse, Path, Polygon, Rect, Scene, TextRun
from drawspec.theme import Theme, load_theme

__version__ = "0.1.0"

__all__ = [
    "DrawspecError",
    "Ellipse",
    "EmitError",
    "FitError",
    "FontSubstitutionWarning",
    "Path",
    "Polygon",
    "Rect",
    "Scene",
    "TextRun",
    "Theme",
    "ThemeError",
    "__version__",
    "check_embedding_safety",
    "emit",
    "load_theme",
]
