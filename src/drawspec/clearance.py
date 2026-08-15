"""Step every stroke aside for every word — the last thing done before emission.

A label with a line through it is the one defect no other check finds. The words
are in the markup, so a coverage pass over the source text passes; the box sizes
are right, so the fit pass passes; and the drawing is illegible exactly where it
matters most, because the thing a route's label says is *why* the route is there.

The pattern is not new here. A funnel's gate has always broken its divider in
the middle to let its name through — `kinds.shape._gate_divider` — because a
threshold's name belongs to neither side of it. That is the right answer, and
the reason it only ever protected gates is that it was written at the one call
site that noticed. This module is the same idea applied where it can see
everything: a whole scene, after every family has placed its own primitives and
none of them knows what the others put nearby.

Three properties make that safe to do late:

* **It only removes ink.** A cleared scene has the same extents, the same boxes
  and the same words in the same places as the scene that went in, so it cannot
  change a fit decision or invalidate a measurement taken upstream.
* **It only touches `Path`.** A box outline surrounding its own text does not
  cross it, and a filled region has no stroke to break. Routes, curves, axes,
  dividers and spans are paths, and they are the marks that travel.
* **Heads stay whole.** An open arrow head is two short strokes meeting at a
  tip (`Path.marker`); a gap in one leaves a mark no reader can name. A head
  that lands in a word means the *route* is wrong, and clearing the shaft that
  leads to it is what makes that visible rather than hiding it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from itertools import pairwise

from drawspec.scene import Path, Primitive, Scene, TextLine, TextRun
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: How far a broken stroke stops short of the text box, in user units. A gap the
#: same size as the box would leave the stroke touching the glyphs it stepped
#: aside for, which reads as a join rather than as a break.
CLEARANCE = 1.5

#: A surviving piece of stroke shorter than this is dropped rather than drawn. A
#: line that passes a hair from the end of a word leaves a two-unit stub on the
#: far side, and a stub is read as a mark of its own — a tick, a bullet, a
#: mistake — rather than as the continuation of something.
MINIMUM_PIECE = 2.0


class Box:
    """One text primitive's line box, grown by the clearance margin.

    The box is the *line* box — ascent above the baseline, descent below — rather
    than the inked bounds of the particular glyphs, for the same reason box
    geometry uses it upstream: "ace" and "Agile" occupy one line, and a rule
    that let a stroke through the gap over a word without ascenders would break
    on the next word that has one.
    """

    __slots__ = ("x0", "x1", "y0", "y1")

    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def __repr__(self) -> str:  # pragma: no cover — diagnostics only
        return f"Box({self.x0:.1f}, {self.y0:.1f}, {self.x1:.1f}, {self.y1:.1f})"


def cleared(scene: Scene, theme: Theme, measurer: TextMeasurer) -> Scene:
    """`scene` with every stroke broken where it would cross a word.

    The whole of the fix, and it is one pass: collect the text boxes, then
    replace each path with however many pieces of itself survive them. A scene
    with no text, or no paths, is returned untouched.
    """
    boxes = _boxes(scene.primitives, theme, measurer)
    if not boxes:
        return scene
    primitives: list[Primitive] = []
    for primitive in scene.primitives:
        if isinstance(primitive, Path) and not primitive.marker:
            primitives.extend(_broken(primitive, boxes))
        else:
            primitives.append(primitive)
    return replace(scene, primitives=tuple(primitives))


def _boxes(
    primitives: Iterable[Primitive], theme: Theme, measurer: TextMeasurer
) -> tuple[Box, ...]:
    """The line box of every text primitive, grown by `CLEARANCE`.

    A rotated run is skipped. Clearing one would mean rotating every candidate
    stroke into its frame, and the only rotated text drawspec emits is a chart's
    vertical axis title, which sits outside the plot where no mark travels.
    """
    boxes: list[Box] = []
    for primitive in primitives:
        if isinstance(primitive, TextRun):
            if primitive.rotate:
                continue
            width = measurer.advance(
                primitive.text, primitive.font, theme.scale[primitive.level], primitive.weight
            )
            boxes.append(
                _box(primitive.x, primitive.y, width, primitive.anchor, primitive, theme, measurer)
            )
        elif isinstance(primitive, TextLine):
            size = theme.scale[primitive.level]
            width = sum(
                measurer.advance(span.text, span.font, size, span.weight)
                for span in primitive.spans
            )
            boxes.append(
                _box(primitive.x, primitive.y, width, primitive.anchor, primitive, theme, measurer)
            )
    return tuple(boxes)


def _box(
    x: float,
    y: float,
    width: float,
    anchor: str,
    primitive: TextRun | TextLine,
    theme: Theme,
    measurer: TextMeasurer,
) -> Box:
    """One text primitive's cleared box, from its anchor and measured extents."""
    if isinstance(primitive, TextRun):
        extents = measurer.measure(
            primitive.text, primitive.font, theme.scale[primitive.level], primitive.weight
        )
    else:
        first = primitive.spans[0] if primitive.spans else None
        extents = measurer.measure(
            primitive.text,
            first.font if first else theme.font.default,
            theme.scale[primitive.level],
            first.weight if first else "normal",
        )
    left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
    return Box(
        left - CLEARANCE,
        y - extents.ascent - CLEARANCE,
        left + width + CLEARANCE,
        y + extents.descent + CLEARANCE,
    )


def _broken(path: Path, boxes: Sequence[Box]) -> tuple[Path, ...]:
    """`path` as the pieces of itself that fall outside every box.

    A closed path is walked with its closing segment included and comes back
    open, which is the only honest answer: a ring with a bite out of it is no
    longer a closed shape, and saying it is would fill the bite.
    """
    points = path.points
    if len(points) < 2:
        return (path,)
    segments = list(pairwise(points))
    if path.closed:
        segments.append((points[-1], points[0]))

    pieces: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    touched = False
    for start, finish in segments:
        for piece, broke in _pieces(start, finish, boxes):
            touched = touched or broke
            if not piece:
                # The stroke is inside a box here: end the run in progress.
                if current:
                    pieces.append(current)
                    current = []
                continue
            head, tail = piece
            if current and current[-1] == head:
                current.append(tail)
            else:
                if current:
                    pieces.append(current)
                current = [head, tail]
    if current:
        pieces.append(current)

    if not touched:
        return (path,)
    kept = [piece for piece in pieces if _length(piece) >= MINIMUM_PIECE]
    return tuple(replace(path, points=tuple(piece), closed=False) for piece in kept)


def _pieces(
    start: tuple[float, float], finish: tuple[float, float], boxes: Sequence[Box]
) -> list[tuple[tuple[tuple[float, float], tuple[float, float]] | None, bool]]:
    """One segment split at every box boundary it crosses.

    Walked as a list of parameter intervals rather than by clipping against each
    box in turn, because two labels close together produce three surviving
    pieces of one segment and clipping in turn can only ever produce two.
    """
    inside = _covered(start, finish, boxes)
    if not inside:
        return [((start, finish), False)]
    result: list[tuple[tuple[tuple[float, float], tuple[float, float]] | None, bool]] = []
    cursor = 0.0
    for lower, upper in inside:
        if lower > cursor:
            result.append(((_at(start, finish, cursor), _at(start, finish, lower)), True))
        result.append((None, True))
        cursor = upper
    if cursor < 1.0:
        result.append(((_at(start, finish, cursor), _at(start, finish, 1.0)), True))
    return result


#: How finely a segment is walked when deciding which of it is inside a box, as
#: a fraction of the segment. Sampling rather than solving the four line-box
#: intersections: a path is a polyline of short segments, the boxes are
#: axis-aligned, and this is the version whose failure mode is a gap half a unit
#: off rather than a gap in the wrong place.
_STEP = 0.4


def _covered(
    start: tuple[float, float], finish: tuple[float, float], boxes: Sequence[Box]
) -> list[tuple[float, float]]:
    """The parameter intervals of `start`-`finish` that lie inside any box."""
    length = max(abs(finish[0] - start[0]), abs(finish[1] - start[1]))
    if length == 0:
        return []
    steps = max(int(length / _STEP), 1)
    hits = []
    for step in range(steps + 1):
        ratio = step / steps
        x, y = _at(start, finish, ratio)
        hits.append(any(box.contains(x, y) for box in boxes))
    if not any(hits):
        return []

    intervals: list[tuple[float, float]] = []
    opened: float | None = None
    for step, hit in enumerate(hits):
        ratio = step / steps
        if hit and opened is None:
            opened = ratio
        elif not hit and opened is not None:
            intervals.append((opened, ratio))
            opened = None
    if opened is not None:
        intervals.append((opened, 1.0))
    return intervals


def _at(
    start: tuple[float, float], finish: tuple[float, float], ratio: float
) -> tuple[float, float]:
    return (
        start[0] + (finish[0] - start[0]) * ratio,
        start[1] + (finish[1] - start[1]) * ratio,
    )


def _length(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in pairwise(points):
        total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return total


__all__ = ["CLEARANCE", "MINIMUM_PIECE", "Box", "cleared"]
