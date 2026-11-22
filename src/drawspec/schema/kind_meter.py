"""The `meter` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _figure, _is_number, _listed, _optional_number, _pointer
from drawspec.schema._constants import METER_BAND_STYLES, METER_MIN_STYLES, METER_STYLES
from drawspec.schema._model import Document, Meter, MeterBand, Violation

#: Why a meter has no place for a field an author may reach for.
METER_REFUSED: Final = {
    "edges": "a meter has nothing to connect: each one is read against its own scale",
    "series": "a meter is one amount against a scale. Values against an axis are a `chart`",
    "axes": "a meter's scale is its `min` and `max`. Values against two axes are a `chart`",
    "value": "a meter's reading is its `amount`",
    "goal": "a thermometer's goal is the top of its scale, `max`; a stage under it is a `target`",
    "percent": (
        'write the reading as it is, with `"unit": "%"` and `"max": 100` for a percentage, '
        "or the amount and the whole it is out of"
    ),
    "style": (
        "the style is the document's, at the top: one panel, one style, so like is "
        "compared with like. Two styles are two documents"
    ),
    "from": "a band runs from the end of the one before it, or from the scale's start",
    "colour": (
        "a band is told by its words and drawn in the theme's tones. Write the word the "
        "reader is taught — `Green`, or `On track`"
    ),
}


def _meter_refusal(violation: Violation) -> Violation:
    """A structural refusal in a meter panel, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in METER_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {METER_REFUSED[name]}.")
    return violation


def _meter_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Each meter's reading, target and bands inside its scale, and bands its style takes.

    A bar, a bullet and a thermometer start at zero (their length is their
    amount); bands go on a bullet, which needs them, and a dial; they rise, and
    the last one ends the scale.
    """
    found: list[Violation] = []
    style = document.get("style", "bar")
    if style not in METER_STYLES:
        return found
    for index, meter in enumerate(_listed(document, "meters")):
        if not isinstance(meter, dict):
            continue
        here = _pointer("meters", index)
        high: Any = meter.get("max")
        if "min" in meter and style not in METER_MIN_STYLES:
            found.append(
                Violation(
                    f"{here}/min",
                    f"a {style}'s length is its amount, so its scale starts at 0. A reading "
                    f"on a scale that starts elsewhere — a temperature — is a "
                    f'`"style": "dial"`, whose needle reads a position.',
                )
            )
            continue
        low: Any = meter.get("min", 0)
        if not (_is_number(high) and _is_number(low)):
            continue
        if high <= low:
            found.append(
                Violation(
                    f"{here}/max",
                    f"the scale runs from {_figure(float(low))} up to `max`, so `max` must be "
                    f"more than {_figure(float(low))}.",
                )
            )
            continue
        for name in ("amount", "target"):
            reading: Any = meter.get(name)
            if _is_number(reading) and not low <= reading <= high:
                found.append(
                    Violation(
                        f"{here}/{name}",
                        f"{_figure(float(reading))} is outside the scale, "
                        f"{_figure(float(low))} to {_figure(float(high))}: a meter has nowhere "
                        f"to point past its ends. Change `max`"
                        + (" or `min`." if style in METER_MIN_STYLES else ".")
                        + (
                            " A goal beaten is a full thermometer with the amount in the caption."
                            if style == "thermometer" and name == "amount"
                            else ""
                        ),
                    )
                )
        bands = meter.get("bands")
        if bands is not None and style not in METER_BAND_STYLES:
            advice = (
                'a bar on named bands is a bullet graph: say `"style": "bullet"`.'
                if style == "bar"
                else "a thermometer fills toward one goal. Bands on a scale are a "
                '`"style": "bullet"` or a `"dial"`.'
            )
            found.append(Violation(f"{here}/bands", advice))
            continue
        if bands is None and style == "bullet":
            found.append(
                Violation(
                    here,
                    "a bullet graph is a bar on named bands: give it `bands` — "
                    '`[{"text": "Poor", "to": …}, …]` — or say `"style": "bar"`.',
                )
            )
            continue
        if not isinstance(bands, list):
            continue
        start = float(low)
        for position, band in enumerate(bands):
            if not isinstance(band, dict) or not _is_number(band.get("to")):
                start = float("nan")
                continue
            end = float(band["to"])
            if not end > start:
                found.append(
                    Violation(
                        f"{here}/bands/{position}/to",
                        f"bands rise along the scale, each from the end of the one before: "
                        f"this one must end above {_figure(start)}.",
                    )
                )
            start = end
        last: Any = bands[-1] if bands else None
        if (
            isinstance(last, dict)
            and _is_number(last.get("to"))
            and not math.isclose(float(last["to"]), float(high))
        ):
            found.append(
                Violation(
                    f"{here}/bands/{len(bands) - 1}/to",
                    f"the last band ends the scale: its `to` is `max`, "
                    f"{_figure(float(high))}. Bands cover the scale once, with no gap at the "
                    f"top.",
                )
            )
    return found


def _meter_document(document: Mapping[str, Any]) -> Document:
    """A meter panel: its style and its meters, in reading order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        meter_style=str(document.get("style", "bar")),
        meters=tuple(
            Meter(
                text=str(meter["text"]),
                amount=float(meter["amount"]),
                max=float(meter["max"]),
                min=float(meter.get("min", 0.0)),
                unit=str(meter.get("unit", "")),
                target=_optional_number(meter.get("target")),
                bands=tuple(
                    MeterBand(text=str(band["text"]), to=float(band["to"]))
                    for band in meter.get("bands", ())
                ),
                role=str(meter.get("role", "step")),
            )
            for meter in document["meters"]
        ),
    )
