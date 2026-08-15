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
from typing import Final

from collisions import (
    SVG_NS,
    Measurers,
    _local,
    _number,
    _path_points,
    _polygon_points,
    _rect_points,
    line_box,
)

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


#: One piece of ink: what it is, what it says, and the box it occupies.
Ink = tuple[str, str, tuple[float, float, float, float]]


def _text_ink(root: ET.Element, search_paths: Sequence[Path] | None) -> Iterator[Ink]:
    """Every `<text>` as its measured line box, in final coordinates.

    Each run is measured in its own family — see `collisions.line_box`. A label
    measured entirely in the parent's sans understates a monospace span by about
    a fifth, and an understated box is a clipped label the checker calls clean.
    """
    measurers = Measurers(search_paths)
    for element in root.iter(f"{{{SVG_NS}}}text"):
        text, x0, y0, x1, y1 = line_box(element, measurers)
        if not text:
            continue
        angle, about = _rotation(element)
        yield "label", text, _rotated((x0, y0, x1, y1), angle, about)


#: Elements whose bounds this knows how to take. `<ellipse>` is here and not in
#: `collisions._segments` because that one asks whether a *stroke* runs through a
#: word, and answers it by walking straight segments; an arc has none to walk.
#: Being outside the canvas is a question about bounds, and an ellipse has those.
_SHAPES: Final = ("path", "polygon", "polyline", "rect", "ellipse")


def _defined(root: ET.Element) -> set[int]:
    """Every element inside a `<defs>`, which is a template rather than a drawing.

    A fill pattern's tile is a `<rect>` a few units square at the origin, and its
    coordinates are in the pattern's own space — they say nothing about where the
    fill lands on the page. Measured as if they were canvas coordinates, a tile is
    ink pinned to the top-left corner of every chart that has a bar or an area in
    it, which is why the outer gutter of those five reference drawings read as
    zero while their drawings were framed like everything else.
    """
    return {id(node) for parent in root.iter(f"{{{SVG_NS}}}defs") for node in parent.iter()}


def _shape_ink(root: ET.Element) -> Iterator[Ink]:
    """Every drawn shape as the bounds of the ink it lays down.

    Wider than the stroke walker on purpose, in two ways it had to be.

    **Fill without stroke counts.** Every arrow head drawspec draws is a polygon
    with `fill="currentColor"` and `stroke="none"` — a stroked head would be a
    head with an outline — so a checker that skips unstroked elements is blind to
    a clipped arrow head, which is the one piece of ink a reader cannot infer from
    what is left.

    **An ellipse counts.** A chart's point marks are `<ellipse>`, and neither the
    segment walker nor anything else in the suite has ever looked at one.
    """
    templates = _defined(root)
    for element in root.iter():
        tag = _local(element.tag)
        if tag not in _SHAPES or id(element) in templates:
            continue
        stroked = element.get("stroke", "none") != "none"
        filled = element.get("fill", "none") != "none"
        if not stroked and not filled:
            continue
        # A stroke is paint around a centreline; a fill stops at the geometry.
        reach = _number(element.get("stroke-width"), 1.0) / 2 if stroked else 0.0
        points = _points(element, tag)
        if not points:
            continue
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        box = (min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)
        yield f"a {'stroke' if stroked else 'filled shape'}", "", box


def _points(element: ET.Element, tag: str) -> list[tuple[float, float]]:
    """The geometry of one shape, as the points its bounds are taken from.

    An ellipse is given as the four extremes of its own box, which are on it —
    the bounds of an axis-aligned ellipse are the bounds of that box.
    """
    if tag == "ellipse":
        cx, cy = _number(element.get("cx")), _number(element.get("cy"))
        rx, ry = _number(element.get("rx")), _number(element.get("ry"))
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag == "rect":
        return _rect_points(element)
    if tag in ("polygon", "polyline"):
        return _polygon_points(element.get("points", ""))
    return [point for subpath in _path_points(element.get("d", "")) for point in subpath]


def _overflow(item: Ink, canvas: tuple[float, float, float, float]) -> Overflow | None:
    what, text, (x0, y0, x1, y1) = item
    vx, vy, vw, vh = canvas
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
    canvas = _canvas(root)
    found = [
        overflow
        for item in (*_text_ink(root, search_paths), *_shape_ink(root))
        if (overflow := _overflow(item, canvas)) is not None
    ]
    return sorted(found, key=lambda item: -item.worst)


def gutters(svg: str, *, search_paths: Sequence[Path] | None = None) -> tuple[float, ...]:
    """The blank between each canvas edge and the nearest ink — left, top, right, bottom.

    The same measurement as `clipped`, read the other way round. Where that one
    asks whether any ink is *past* an edge, this asks how far the ink stops
    *short* of it, which is the question an outer margin is the answer to. A
    negative number here is a clipped drawing and would be reported by `clipped`
    as an overflow.

    Empty — no ink at all — is `()` rather than four zeros, because a drawing with
    nothing in it has no margins rather than no margin.
    """
    root = ET.fromstring(svg)
    boxes = [box for _, _, box in (*_text_ink(root, search_paths), *_shape_ink(root))]
    if not boxes:
        return ()
    vx, vy, vw, vh = _canvas(root)
    return (
        min(box[0] for box in boxes) - vx,
        min(box[1] for box in boxes) - vy,
        (vx + vw) - max(box[2] for box in boxes),
        (vy + vh) - max(box[3] for box in boxes),
    )


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
