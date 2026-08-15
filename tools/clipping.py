"""Report ink drawn outside the canvas, in a rendered `.svg`.

`collisions.py` answers *can the word be read* — is there a stroke through it.
This answers the question before that one: **is the word on the page at all**. A
label drawn past the `viewBox` is present in the markup, carries no collision,
survives every coverage check, and is simply not there when the file is looked
at. It is the corpus's *text outside its box* failure moved up one level, from
the box to the canvas, and no check in the suite could see it.

Why it measures rather than rasterises
--------------------------------------

The same reason `collisions.py` does, and the reason is the same reason again:
the `viewBox` is computed from `drawspec.scene.extents`, which records a text run
as its **anchor point**. A run's width and its ascent and descent are therefore
outside every canvas that a family did not separately reserve room for. That
belief is where the bug is, so the check is made against the same font metrics
the belief was formed from rather than against what a browser made of the markup.

Rotated runs are measured rather than skipped, because a rotated run — a band's
name beside its bar, an axis title on its side — is the case that overflows
furthest: it is long in the direction the canvas is short.
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from collisions import SVG_NS, _number, _runs, _segments, _stack

from drawspec.text.measure import TextMeasurer

#: Ink has to reach this far past the canvas edge to be reported, in user units.
#: The `viewBox` is widened by half the *heaviest* stroke in the scene, so a
#: hairline sitting flush against the edge is inside it by a hair and a heavier
#: one is exactly on it; neither is a clipped drawing.
TOLERANCE = 0.5


@dataclass(frozen=True)
class Overflow:
    """One piece of ink, and how far past the canvas it reaches."""

    what: str
    text: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def worst(self) -> float:
        return max(self.left, self.top, self.right, self.bottom)

    def __str__(self) -> str:
        sides = [
            f"{name} by {value:.1f}"
            for name, value in (
                ("left", self.left),
                ("top", self.top),
                ("right", self.right),
                ("bottom", self.bottom),
            )
            if value > TOLERANCE
        ]
        subject = f"{self.what} {self.text!r}" if self.text else self.what
        return f"{subject} is outside the canvas: {', and '.join(sides)}"


def _rotated(
    box: tuple[float, float, float, float], degrees: float, about: tuple[float, float]
) -> tuple[float, float, float, float]:
    """`box` turned by `degrees` about `about`, as the bounds of the turned corners.

    SVG's `rotate(a cx cy)` is a positive-clockwise turn in a y-down space, which
    is the sign convention below. The bounds of the four turned corners are the
    bounds of the turned box for the right angles drawspec emits, and never
    understate it for any other angle.
    """
    if not degrees:
        return box
    x0, y0, x1, y1 = box
    cx, cy = about
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    corners = [
        (
            cx + (x - cx) * cos - (y - cy) * sin,
            cy + (x - cx) * sin + (y - cy) * cos,
        )
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    ]
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _rotation(element: ET.Element) -> tuple[float, tuple[float, float]]:
    """The `rotate(a cx cy)` on one element, as an angle and a centre."""
    transform = element.get("transform")
    if not transform or not transform.startswith("rotate("):
        return 0.0, (0.0, 0.0)
    numbers = transform[len("rotate(") :].rstrip(")").replace(",", " ").split()
    if len(numbers) != 3:
        return 0.0, (0.0, 0.0)
    angle, cx, cy = (float(value) for value in numbers)
    return angle, (cx, cy)


def _text_ink(root: ET.Element, search_paths: Sequence[Path] | None) -> Iterator[Overflow | None]:
    """Every `<text>` as its measured line box, in final coordinates."""
    for element in root.iter(f"{{{SVG_NS}}}text"):
        size = _number(element.get("font-size"), 11.0)
        stack = _stack(element.get("font-family"))
        measurer = TextMeasurer({"sans": stack}, search_paths=search_paths)
        runs = _runs(element)
        if not runs:
            continue
        text = "".join(run for run, _ in runs)
        if not text.strip():
            continue
        width = sum(measurer.advance(run, "sans", size, weight) for run, weight in runs)
        extents = measurer.measure(text, "sans", size, runs[0][1])
        x = _number(element.get("x"))
        y = _number(element.get("y"))
        anchor = element.get("text-anchor", "start")
        if anchor == "middle":
            x -= width / 2
        elif anchor == "end":
            x -= width
        box = (x, y - extents.ascent, x + width, y + extents.descent)
        angle, about = _rotation(element)
        yield _overflow("label", text, _rotated(box, angle, about), root)


def _stroke_ink(root: ET.Element) -> Iterator[Overflow | None]:
    """Every stroked segment as the bounds of the paint it lays down."""
    for segment in _segments(root):
        (x0, y0), (x1, y1) = segment.start, segment.finish
        box = (
            min(x0, x1) - segment.reach,
            min(y0, y1) - segment.reach,
            max(x0, x1) + segment.reach,
            max(y0, y1) + segment.reach,
        )
        yield _overflow("a stroke", "", box, root)


def _overflow(
    what: str, text: str, box: tuple[float, float, float, float], root: ET.Element
) -> Overflow | None:
    x0, y0, x1, y1 = box
    vx, vy, vw, vh = _canvas(root)
    found = Overflow(
        what=what,
        text=text,
        left=vx - x0,
        top=vy - y0,
        right=x1 - (vx + vw),
        bottom=y1 - (vy + vh),
    )
    return found if found.worst > TOLERANCE else None


def _canvas(root: ET.Element) -> tuple[float, float, float, float]:
    box = root.get("viewBox")
    if not box:
        raise ValueError("the root <svg> has no viewBox, so there is no canvas to measure against")
    x, y, width, height = (float(value) for value in box.replace(",", " ").split())
    return x, y, width, height


def clipped(svg: str, *, search_paths: Sequence[Path] | None = None) -> list[Overflow]:
    """Every piece of ink outside the canvas, in one rendered document."""
    root = ET.fromstring(svg)  # drawspec's own output, not third-party input
    found = [
        item for item in (*_text_ink(root, search_paths), *_stroke_ink(root)) if item is not None
    ]
    return sorted(found, key=lambda item: -item.worst)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="rendered .svg files, or directories")
    arguments = parser.parse_args(argv)

    files: list[Path] = []
    for path in arguments.paths:
        files.extend(sorted(path.glob("*.svg")) if path.is_dir() else [path])

    total = 0
    for path in files:
        found = clipped(path.read_text(encoding="utf-8"))
        total += len(found)
        for item in found:
            print(f"{path}: {item}")
    print(f"{total} outside the canvas in {len(files)} file{'s' if len(files) != 1 else ''}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
