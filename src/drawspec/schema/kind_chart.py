"""The `chart` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drawspec.schema._checks import _is_number, _listed, _pointer
from drawspec.schema._model import Violation


def _chart_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A chart with `categories` on its vertical axis: horizontal bars, checked.

    The categories become rows, so every series is bars, every point is
    `[amount, position]` with a position that names a row, and the category axis
    takes no `min`/`max` — the rows frame it. Amounts start at zero: a bar that
    runs left of the names is a diverging chart, which this kind does not draw.
    """
    found: list[Violation] = []
    axes = document.get("axes")
    if not isinstance(axes, dict):
        return found
    vertical, horizontal = axes.get("vertical"), axes.get("horizontal")
    if not isinstance(vertical, dict) or not vertical.get("categories"):
        return found
    count = len(vertical["categories"])
    if isinstance(horizontal, dict) and horizontal.get("categories"):
        found.append(
            Violation(
                "/axes/horizontal/categories",
                "both axes name categories, so no axis carries an amount for a bar to "
                "measure. With `categories` on the vertical axis the bars run across: "
                "give the horizontal axis numbers.",
            )
        )
    for name in ("min", "max"):
        if name in vertical:
            found.append(
                Violation(
                    _pointer("axes", "vertical", name),
                    f"with `categories` the vertical axis is the {count} rows, one per "
                    f"category, top first, so it takes no {name!r}. Drop it.",
                )
            )
    for index, series in enumerate(_listed(document, "series")):
        if not isinstance(series, dict):
            continue
        if series.get("mark", "line") != "bar":
            found.append(
                Violation(
                    _pointer("series", index, "mark"),
                    "with `categories` on the vertical axis this is a horizontal bar chart, "
                    'and every series is `"mark": "bar"`. A line drawn down a list of '
                    "names joins things that have no order between them.",
                )
            )
        for point, pair in enumerate(series.get("data", ()) or ()):
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            amount, position = pair
            if _is_number(position) and (
                not 1 <= position <= count or not float(position).is_integer()
            ):
                found.append(
                    Violation(
                        _pointer("series", index, "data", point, 1),
                        f"a horizontal bar is `[amount, position]`, and the position names a "
                        f"category: a whole number from 1 to {count}, not {position!r}.",
                    )
                )
            if _is_number(amount) and amount < 0:
                found.append(
                    Violation(
                        _pointer("series", index, "data", point, 0),
                        f"{amount!r} is below zero, and a horizontal bar grows right from "
                        f"zero beside its name. A chart of gains and losses is upright: put "
                        f"the categories on the horizontal axis, or use a `waterfall`.",
                    )
                )
    return found
