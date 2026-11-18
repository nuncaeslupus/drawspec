"""Report an edge routed through a frame it does not belong to.

A frame — a flow group, a composite state, one of a composite's regions — says
*these belong together*. A line between two boxes outside it that runs straight
through says nothing of the kind, and reads as an edge that enters the frame and
leaves again: the reader goes looking for the box inside it that the line is
about, and there is none. `collisions.py` cannot see it, because nothing is
written where the line crosses; the frame's interior is empty paper.

The rule checked is the one a reader holds:

* a frame that contains **neither** end of an edge is not entered at all;
* a frame that contains **one** end is crossed exactly once, on the way in or out;
* a frame that contains **both** is never left;
* and no edge runs *along* a border, on top of the dashed line: crossing one
  is done square on, or it reads as entering the frame lengthways.

An edge that names the frame itself — it is about the whole container — lands on
its border, and that frame is not asked about.

Lanes are not frames here. A lane boundary is crossed on purpose: crossing it is
the hand-off the lane diagram exists to show.

Why it lays the document out rather than reading the `.svg`
----------------------------------------------------------

The rendered markup does not say which rectangle is a frame or which path is an
edge, and guessing from dash patterns would make the check depend on the theme.
So this lays each graph document out exactly as `render` does — the same fitted
theme — and asks the drawing directly.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

from drawspec.errors import FitError
from drawspec.geometry import fit
from drawspec.kinds import scene_for
from drawspec.kinds.containers import Frame
from drawspec.kinds.graph import DRAWN_KINDS, GraphDrawing, graph_drawing
from drawspec.render import _within_height, _within_width
from drawspec.schema import Document, load_document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import load_theme

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "reference"

#: How far inside a frame's outline a point has to be to count as inside it. A
#: route that runs along the border, or ends on it, is outside.
TOLERANCE = 0.5

#: How close to a border a run between two corners may be before it reads as
#: drawn on top of it rather than beside it.
ALONG = 3.0


@dataclass(frozen=True)
class Crossing:
    """One edge, one frame, and what the edge did to it."""

    source: str
    target: str
    frame: str
    times: int
    allowed: int
    along: bool = False

    def __str__(self) -> str:
        if self.along:
            return f"{self.source} -> {self.target} runs along the border of frame {self.frame!r}"
        if self.allowed == 0 and self.times == 0:
            return f"{self.source} -> {self.target} leaves frame {self.frame!r}"
        return (
            f"{self.source} -> {self.target} crosses frame {self.frame!r} "
            f"{self.times} time(s); {self.allowed} allowed"
        )


def _interior(frame: Frame) -> tuple[float, float, float, float]:
    return (
        frame.x + TOLERANCE,
        frame.y + TOLERANCE,
        frame.right - TOLERANCE,
        frame.bottom - TOLERANCE,
    )


def _within(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    left, top, right, bottom = box
    return left < point[0] < right and top < point[1] < bottom


def _inside_span(
    first: tuple[float, float], second: tuple[float, float], box: tuple[float, float, float, float]
) -> tuple[float, float] | None:
    """The part of a segment strictly inside `box`, as `t` from 0 to 1 — Liang-Barsky."""
    left, top, right, bottom = box
    low, high = 0.0, 1.0
    step_x, step_y = second[0] - first[0], second[1] - first[1]
    for along, start, minimum, maximum in (
        (step_x, first[0], left, right),
        (step_y, first[1], top, bottom),
    ):
        if abs(along) < 1e-9:
            if not minimum < start < maximum:
                return None
            continue
        near, far = sorted(((minimum - start) / along, (maximum - start) / along))
        low, high = max(low, near), min(high, far)
        if low >= high:
            return None
    return low, high


def border_crossings(points: Sequence[tuple[float, float]], frame: Frame) -> tuple[int, bool]:
    """How many times a polyline passes through `frame`'s border, and whether it enters at all.

    A run inside that starts at the polyline's first point was never entered,
    and one that ends at its last point never left, so an edge from a box in the
    frame to a box outside it crosses once.
    """
    box = _interior(frame)
    runs: list[list[float]] = []
    for index, (first, second) in enumerate(pairwise(points)):
        span = _inside_span(first, second, box)
        if span is None:
            continue
        start, end = index + span[0], index + span[1]
        if runs and abs(runs[-1][1] - start) < 1e-6:
            runs[-1][1] = end
        else:
            runs.append([start, end])
    last = len(points) - 1
    times = sum((run[0] > 1e-6) + (run[1] < last - 1e-6) for run in runs)
    return times, bool(runs)


def runs_along(points: Sequence[tuple[float, float]], frame: Frame) -> bool:
    """Whether a run between two corners of a polyline lies on `frame`'s border.

    The first and last runs are left out: they carry an endpoint, and an edge
    that names the frame lands on its border on purpose.
    """
    for first, second in list(pairwise(points))[1:-1]:
        vertical = abs(first[0] - second[0]) < 1e-6
        at = first[0] if vertical else first[1]
        low, high = sorted((first[1], second[1]) if vertical else (first[0], second[0]))
        start, end = (frame.y, frame.bottom) if vertical else (frame.x, frame.right)
        edges = (frame.x, frame.right) if vertical else (frame.y, frame.bottom)
        if min(high, end) - max(low, start) > TOLERANCE and any(
            abs(at - edge) < ALONG for edge in edges
        ):
            return True
    return False


def frame_crossings(drawing: GraphDrawing) -> list[Crossing]:
    """Every edge that enters a frame it has no end in, crosses one too often, or runs along one."""
    found: list[Crossing] = []
    for route in drawing.routes:
        if len(route.points) < 2:
            continue
        for frame in drawing.frames:
            if runs_along(route.points, frame):
                found.append(Crossing(route.source, route.target, frame.id, 0, 0, along=True))
                continue
            if frame.id in (route.source, route.target):
                continue
            box = _interior(frame)
            ends = _within(route.points[0], box) + _within(route.points[-1], box)
            allowed = 1 if ends == 1 else 0
            times, entered = border_crossings(route.points, frame)
            if times > allowed or (ends == 0 and entered):
                found.append(Crossing(route.source, route.target, frame.id, times, allowed))
    return found


def _drawing(document: Document) -> GraphDrawing:
    """The document laid out the way `render` lays it out: at the theme it fits."""
    theme = load_theme(document.theme or None)
    if document.width:
        theme = replace(theme, canvas=replace(theme.canvas, width=document.width))
    measurer = TextMeasurer(theme.font.stacks())
    fitted = fit(
        theme,
        lambda scaled: _within_height(
            _within_width(scene_for(document, scaled, measurer), scaled), document
        ),
    )
    return graph_drawing(document, fitted.theme, measurer)


def check(path: Path) -> list[Crossing] | None:
    """The crossings in one document, or `None` when it is not a graph kind with frames.

    Raises:
        FitError: the document cannot be laid out at any theme it fits, so there
            is no drawing to check. Not a `None`: a document this check cannot
            look at must not read as one it looked at and passed.
    """
    document = load_document(path)
    if document.kind not in DRAWN_KINDS or not document.groups:
        return None
    return frame_crossings(_drawing(document))


def _documents(path: Path) -> list[Path]:
    """`.json` documents as given; a gallery `.svg` stands for its reference document."""
    if path.is_dir():
        found = sorted(path.glob("*.json")) or [
            REFERENCE_DIR / f"{svg.stem}.json" for svg in sorted(path.glob("*.svg"))
        ]
        return [each for each in found if each.exists()]
    if path.suffix == ".svg":
        return [REFERENCE_DIR / f"{path.stem}.json"]
    return [path]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[REFERENCE_DIR],
        help="documents (.json), gallery drawings (.svg), or directories of either",
    )
    arguments = parser.parse_args(argv)

    total = checked = unfitted = 0
    for path in (each for given in arguments.paths for each in _documents(given)):
        try:
            found = check(path)
        except FitError as error:
            unfitted += 1
            print(f"{path.stem}: cannot be laid out, so cannot be checked: {error}")
            continue
        if found is None:
            continue
        checked += 1
        total += len(found)
        for crossing in found:
            print(f"{path.stem}: {crossing}")
    print(f"\n{total} frame crossing(s) in {checked} drawing(s) with frames")
    if unfitted:
        print(f"{unfitted} document(s) could not be laid out and were not checked")
    return 1 if total or unfitted else 0


if __name__ == "__main__":
    sys.exit(main())
