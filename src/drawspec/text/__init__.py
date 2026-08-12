"""Text measurement and line breaking.

`TextMeasurer` is the entry point; `fontlib` holds font resolution and the raw
metric reading it sits on.
"""

from __future__ import annotations

from drawspec.text.fontlib import FONT_ROLES, ResolvedFont, bundled_font_path
from drawspec.text.measure import DEFAULT_STACKS, Extents, TextMeasurer

__all__ = [
    "DEFAULT_STACKS",
    "FONT_ROLES",
    "Extents",
    "ResolvedFont",
    "TextMeasurer",
    "bundled_font_path",
]
