"""The `funnel` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drawspec.schema._checks import _figure, _is_number, _listed, _pointer
from drawspec.schema._model import Violation


def _funnel_amount_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Amounts on every stage or on none, each no more than the one before."""
    found: list[Violation] = []
    stages = [stage for stage in _listed(document, "stages") if isinstance(stage, dict)]
    counted = [index for index, stage in enumerate(stages) if "amount" in stage]
    if counted and len(counted) < len(stages):
        missing = next(index for index in range(len(stages)) if index not in counted)
        found.append(
            Violation(
                _pointer("stages", missing, "amount"),
                f"{len(counted)} of the {len(stages)} stages have an amount and this one has "
                f"none, so the share kept here could not be said. Give every stage its "
                f"amount, or none.",
            )
        )
    if "unit" in document and not counted:
        found.append(
            Violation(
                "/unit",
                "a unit with no amounts names nothing: no stage has an `amount` to write "
                "it after. Drop it, or give the stages their amounts.",
            )
        )
    previous: float | None = None
    for index, stage in enumerate(stages):
        if not _is_number(stage.get("amount")):
            continue
        amount = float(stage["amount"])
        if previous is not None and amount > previous:
            found.append(
                Violation(
                    _pointer("stages", index, "amount"),
                    f"{_figure(amount)} reached this stage, more than the {_figure(previous)} "
                    f"at the one before. A funnel only narrows: if things join part-way, "
                    f"draw it as a `flow` or a `sankey`.",
                )
            )
        previous = amount
    return found
