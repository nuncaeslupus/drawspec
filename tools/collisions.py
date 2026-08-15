"""Report where a stroke is drawn through a word, in a rendered `.svg`.

`cobertura`-style word checks answer *is the word there*. This answers the other
half: *can it be read*. A label with a line through it is present in the markup,
passes every coverage check, and is illegible on the page — which is the one
failure mode the tool exists to prevent and the one no text test catches.

Why it measures rather than rasterises
--------------------------------------

The obvious implementation asks a browser for `getBBox()` and walks each stroke
with `getPointAtLength()`. This one does the same arithmetic in-process, against
**the same font metrics the layout used** (`drawspec.text.measure`), for two
reasons:

* A browser answers *what did Chromium do with this markup*. The measurer
  answers *what did drawspec believe when it placed the label* — and it is the
  belief that has the bug in it. When the two disagree the second is the one that
  names the line to change.
* It runs in the test suite. A check that needs a browser runs once, by hand,
  in the round that added it.

drawspec emits polylines (`M … L …`) and never a curve command, so segment
geometry here is exact rather than sampled. A text box is the measured line box —
ascent above the baseline, descent below — which is the box layout reserved, not
the tighter ink bounds of the particular glyphs.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from drawspec.text.measure import TextMeasurer

SVG_NS = "http://www.w3.org/2000/svg"

#: A stroke has to be *inside* a word by this much in user units to count. A
#: descender that grazes an underline below it is not what this looks for, and
#: without a margin every span tick beside its own label reads as a collision.
TOLERANCE = 0.75


@dataclass(frozen=True)
class Box:
    """One text run's line box, and the words in it."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, x: float, y: float, *, inset: float = TOLERANCE) -> bool:
        return self.x0 + inset < x < self.x1 - inset and self.y0 + inset < y < self.y1 - inset

    def overlaps(self, other: Box, *, inset: float = TOLERANCE) -> bool:
        return (
            self.x0 + inset < other.x1 - inset
            and other.x0 + inset < self.x1 - inset
            and self.y0 + inset < other.y1 - inset
            and other.y0 + inset < self.y1 - inset
        )


@dataclass(frozen=True)
class Segment:
    """One stroked line segment, and how far its paint reaches from the centreline."""

    start: tuple[float, float]
    finish: tuple[float, float]
    reach: float


@dataclass(frozen=True)
class Collision:
    """A stroke crossing a word, or a word crossing a word."""

    kind: str
    text: str
    other: str
    at: tuple[float, float]

    def __str__(self) -> str:
        x, y = self.at
        where = f"({x:.1f}, {y:.1f})"
        if self.kind == "stroke":
            return f"stroke through {self.text!r} at {where}"
        return f"{self.text!r} overlaps {self.other!r} at {where}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: str | None, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        return float(value)
    except ValueError:
        return fallback


_FAMILY = re.compile(r"'([^']+)'|\"([^\"]+)\"|([^,]+)")


def _stack(family: str | None) -> tuple[str, ...]:
    """The `font-family` attribute back into the stack the measurer wants."""
    if not family:
        return ("sans-serif",)
    names = []
    for match in _FAMILY.finditer(family):
        name = (match.group(1) or match.group(2) or match.group(3) or "").strip()
        if name:
            names.append(name)
    return tuple(names) or ("sans-serif",)


def _text_boxes(root: ET.Element, search_paths: Sequence[Path] | None) -> list[Box]:
    """Every `<text>` in the tree as a measured line box.

    Rotated runs (an axis title on its side) are skipped rather than guessed at:
    the transform would have to be applied to the strokes too, and an axis title
    is never the label a route runs through.
    """
    boxes: list[Box] = []
    for element in root.iter(f"{{{SVG_NS}}}text"):
        if element.get("transform"):
            continue
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
        boxes.append(
            Box(text=text, x0=x, y0=y - extents.ascent, x1=x + width, y1=y + extents.descent)
        )
    return boxes


def _runs(element: ET.Element) -> list[tuple[str, str]]:
    """The (text, weight) runs of one `<text>`, tspans included."""
    runs: list[tuple[str, str]] = []
    if element.text:
        runs.append((element.text, "normal"))
    for child in element:
        if _local(child.tag) == "tspan" and child.text:
            runs.append((child.text, child.get("font-weight") or "normal"))
        if child.tail:
            runs.append((child.tail, "normal"))
    return [(text, weight) for text, weight in runs if text]


def _segments(root: ET.Element) -> Iterator[Segment]:
    """Every stroked line segment: paths, polygons and rect outlines.

    Each carries half its own `stroke-width`, because a stroke is paint around a
    centreline and it is the paint that lands on the word. A 2.5-unit `strong`
    edge reaches 1.25 units either side of the geometry in the `d` attribute, so
    a checker that samples the centreline alone reports a clean drawing where a
    reader sees ink through a letter.
    """
    for element in root.iter():
        tag = _local(element.tag)
        if element.get("stroke", "none") == "none":
            continue
        reach = _number(element.get("stroke-width"), 1.0) / 2
        if tag == "path":
            subpaths = _path_points(element.get("d", ""))
        elif tag in ("polygon", "polyline"):
            points = _polygon_points(element.get("points", ""))
            subpaths = [[*points, points[0]] if tag == "polygon" and points else points]
        elif tag == "rect":
            subpaths = [_rect_points(element)]
        else:
            continue
        for points in subpaths:
            for start, finish in pairwise(points):
                if start != finish:
                    yield Segment(start, finish, reach)


def _path_points(data: str) -> list[list[tuple[float, float]]]:
    """The vertices of a polyline `d`, one list per subpath.

    Subpaths are kept apart rather than concatenated. An open head and a span's
    pair of end ticks are each several `M`-started strokes in one `d`; joining
    them would invent a segment nobody drew, straight across the drawing.
    """
    subpaths: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for command in re.finditer(r"([MLZ])((?:\s*-?[\d.]+)*)", data):
        letter = command.group(1)
        numbers = [float(value) for value in re.findall(r"-?[\d.]+", command.group(2))]
        if letter == "Z":
            if current:
                current.append(current[0])
            continue
        if letter == "M" and current:
            subpaths.append(current)
            current = []
        current.extend(zip(numbers[::2], numbers[1::2], strict=False))
    if current:
        subpaths.append(current)
    return subpaths


def _polygon_points(data: str) -> list[tuple[float, float]]:
    numbers = [float(value) for value in re.findall(r"-?[\d.]+", data)]
    return list(zip(numbers[::2], numbers[1::2], strict=False))


def _rect_points(element: ET.Element) -> list[tuple[float, float]]:
    x, y = _number(element.get("x")), _number(element.get("y"))
    width, height = _number(element.get("width")), _number(element.get("height"))
    return [(x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)]


def _crosses(box: Box, segment: Segment) -> tuple[float, float] | None:
    """Where `segment`'s paint enters `box`, walking it at 0.5-unit steps.

    Half a unit is finer than any glyph is wide, so a stroke that passes through
    a word cannot step over it. The box is grown by the segment's own reach rather
    than the segment thickened, which is the same test and one rectangle cheaper.
    """
    (x0, y0), (x1, y1) = segment.start, segment.finish
    grown = Box(
        text=box.text,
        x0=box.x0 - segment.reach,
        y0=box.y0 - segment.reach,
        x1=box.x1 + segment.reach,
        y1=box.y1 + segment.reach,
    )
    length = max(abs(x1 - x0), abs(y1 - y0))
    steps = max(int(length / 0.5), 1)
    for step in range(steps + 1):
        ratio = step / steps
        x, y = x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio
        if grown.contains(x, y):
            return (x, y)
    return None


def collisions(svg: str, *, search_paths: Sequence[Path] | None = None) -> list[Collision]:
    """Every stroke-through-word and word-over-word in one rendered document."""
    root = ET.fromstring(svg)  # drawspec's own output, not third-party input
    boxes = _text_boxes(root, search_paths)
    found: list[Collision] = []
    segments = list(_segments(root))
    for box in boxes:
        for segment in segments:
            at = _crosses(box, segment)
            if at is not None:
                found.append(Collision("stroke", box.text, "", at))
                break
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            if box.overlaps(other):
                found.append(Collision("text", box.text, other.text, (box.x0, box.y0)))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="rendered .svg files, or directories")
    arguments = parser.parse_args(argv)

    files: list[Path] = []
    for path in arguments.paths:
        files.extend(sorted(path.glob("*.svg")) if path.is_dir() else [path])

    total = 0
    for path in files:
        found = collisions(path.read_text(encoding="utf-8"))
        total += len(found)
        for collision in found:
            print(f"{path.name}: {collision}")
    print(f"\n{total} collision(s) in {len(files)} drawing(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
