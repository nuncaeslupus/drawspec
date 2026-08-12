"""drawspec — declarative diagram spec to clean, themeable SVG."""

from __future__ import annotations

from drawspec.emit import check_embedding_safety, emit
from drawspec.errors import (
    DocumentError,
    DrawspecError,
    EmitError,
    FitError,
    FontSubstitutionWarning,
    ThemeError,
)
from drawspec.scene import Ellipse, Path, Polygon, Rect, Scene, TextRun
from drawspec.schema import Document, load_document, parse_document, validate_document
from drawspec.theme import Theme, load_theme

__version__ = "0.1.0"

__all__ = [
    "Document",
    "DocumentError",
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
    "load_document",
    "load_theme",
    "parse_document",
    "validate_document",
]
