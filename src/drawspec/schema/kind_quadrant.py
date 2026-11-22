"""The `quadrant` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drawspec.schema._checks import _pointer
from drawspec.schema._constants import AXIS_ORDER
from drawspec.schema._model import Violation


def _quadrant_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Four quarter names exactly, and two ends to an axis."""
    found: list[Violation] = []
    quadrants = document.get("quadrants")
    if isinstance(quadrants, list) and len(quadrants) != 4:
        found.append(
            Violation(
                "/quadrants",
                f"{len(quadrants)} names: a quadrant has four quarters, named top right "
                f"first, then counter-clockwise. Leave a quarter unnamed with an empty string.",
            )
        )
    axes = document.get("axes")
    for name in AXIS_ORDER:
        axis = axes.get(name) if isinstance(axes, dict) else None
        ends = axis.get("ends") if isinstance(axis, dict) else None
        if isinstance(ends, list) and len(ends) > 2:
            found.append(
                Violation(
                    _pointer("axes", name, "ends"),
                    f"{len(ends)} ends: an axis has two, the low end's word then the high end's.",
                )
            )
    return found
