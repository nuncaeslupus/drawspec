"""Report arrows that turn a corner and then arrive with almost no line, in an `.svg`.

An orthogonal route turns at right angles, and the last turn decides how the
arrow reads: with a straight run behind its head as long as the head again, it
is an arrow arriving; with only the head's own length, the head sits on the
corner and reads as a blot. Every family that draws turning arrows keeps that
run (`drawspec.routing.arrow_run`), and this is the check that it did.

It reads the drawing rather than the layout, so it covers every kind the same
way: a line whose end touches a filled head, whose last turn is a right
angle, and whose straight run from that turn to the point is shorter than
`ratio` times the head's own length is reported. Curves (an automaton's arcs)
turn by small steps, never by a right angle, and are not this failure.

A line that branches off an arrow's last run (a skip leaving a block's input)
has the same failure at a junction: too near the point, the branch reads as
part of the head and runs nearer the box than the arrow's shaft. Every such
junction must sit `JUNCTION` head lengths behind the point.

    uv run python tools/arrows.py docs/gallery
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from collisions import _local, _path_points, _polygon_points

#: The shortest run an arrow may have after its last turn, in head lengths: the
#: head and half as much again of visible line. `arrow_run` asks for two; less
#: than that is allowed only where the boxes leave no room for more.
RATIO = 1.5

#: How far behind an arrow's point a line may leave its last run, in head
#: lengths: as far back as `arrow_run` turns, so a branch never reads as part of
#: the head, nor runs nearer the box than the arrow's own shaft does.
JUNCTION = 2.0

#: How close a line's end must be to a head's point to be that head's line.
TOUCH = 0.6

#: The longest side a head may have; a filled triangle larger than this is a mark.
HEAD_MAX = 30.0

#: How far from a right angle a turn may be and still count as one, in degrees.
SQUARE = 10.0


@dataclass(frozen=True)
class ShortArrow:
    """One arrow whose last straight run is too short for its head."""

    tip: tuple[float, float]
    run: float
    head: float

    def __str__(self) -> str:
        x, y = self.tip
        return (
            f"arrow into ({x:.1f}, {y:.1f}): {self.run:.1f} of line after its last turn "
            f"for a {self.head:.1f} head (wants {RATIO * self.head:.1f})"
        )


def _angle(start: tuple[float, float], end: tuple[float, float]) -> float:
    return math.atan2(end[1] - start[1], end[0] - start[0])


def _last_run(points: Sequence[tuple[float, float]]) -> tuple[float, bool]:
    """The straight run into the line's end, and whether a right angle starts it."""
    kept = [point for index, point in enumerate(points) if index == 0 or point != points[index - 1]]
    if len(kept) < 3:
        return 0.0, False
    heading = _angle(kept[-2], kept[-1])
    run = 0.0
    for index in range(len(kept) - 1, 0, -1):
        turn = abs((_angle(kept[index - 1], kept[index]) - heading + math.pi) % math.tau - math.pi)
        if turn > math.radians(SQUARE):
            return run, abs(math.degrees(turn) - 90.0) <= SQUARE
        run += math.dist(kept[index - 1], kept[index])
    return run, False


def _touches(point: tuple[float, float], shape: Sequence[tuple[float, float]]) -> bool:
    """Whether `point` lies on (or within a hair of) the outline of `shape`."""
    for start, end in zip(shape, [*shape[1:], shape[0]], strict=True):
        dx, dy = end[0] - start[0], end[1] - start[1]
        span = dx * dx + dy * dy
        t = 0.0 if span == 0 else ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / span
        t = max(0.0, min(1.0, t))
        if math.dist(point, (start[0] + t * dx, start[1] + t * dy)) < TOUCH:
            return True
    return False


@dataclass(frozen=True)
class CrowdedJunction:
    """A line that leaves another arrow's last run too close to that arrow's head."""

    at: tuple[float, float]
    gap: float
    head: float
    ratio: float = JUNCTION

    def __str__(self) -> str:
        x, y = self.at
        return (
            f"line leaving an arrow at ({x:.1f}, {y:.1f}): {self.gap:.1f} from its point "
            f"for a {self.head:.1f} head (wants {self.ratio * self.head:.1f})"
        )


def _drawing(svg: str) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    """The small filled triangles (heads) and the lines of `svg`."""
    root = ET.fromstring(svg)
    heads: list[list[tuple[float, float]]] = []
    lines: list[list[tuple[float, float]]] = []
    for element in root.iter():
        tag = _local(element.tag)
        if tag == "polygon" and element.get("fill", "none") != "none":
            shape = _polygon_points(element.get("points", ""))
            # A head is a small triangle; a filled bar or box is not one.
            if len(shape) == 3 and max(map(math.dist, shape, shape[1:] + shape[:1])) < HEAD_MAX:
                heads.append(shape)
        elif tag == "path":
            lines.extend(_path_points(element.get("d", "")))
    return heads, lines


def _head_reach(
    points: Sequence[tuple[float, float]], heads: Sequence[Sequence[tuple[float, float]]]
) -> tuple[tuple[float, float], float, float] | None:
    """For a line ending in a head: its heading, how far the point lies past its
    end, and the head's length; None for a line with no head."""
    end = points[-1]
    head = next((shape for shape in heads if _touches(end, shape)), None)
    if head is None:
        return None
    heading = _angle(points[-2], end)
    along = (math.cos(heading), math.sin(heading))
    # The point is the vertex farthest along the way the line arrives; a line
    # may stop at the head's base or run on to its point.
    reach = [(x - end[0]) * along[0] + (y - end[1]) * along[1] for x, y in head]
    return along, max(reach), max(reach) - min(reach)


def short_arrows(svg: str, *, ratio: float = RATIO) -> list[ShortArrow]:
    """Every arrow in `svg` that turns a right angle too close to its head."""
    heads, lines = _drawing(svg)
    found: list[ShortArrow] = []
    for points in lines:
        if len(points) < 3:
            continue
        arrow = _head_reach(points, heads)
        if arrow is None:
            continue
        run, square = _last_run(points)
        if not square:
            continue
        _, tip, length = arrow
        if length > 0 and run + tip < ratio * length - 1e-6:
            found.append(ShortArrow(points[-1], run + tip, length))
    return found


def crowded_junctions(svg: str, *, ratio: float = JUNCTION) -> list[CrowdedJunction]:
    """Every line that branches off an arrow's last run within `ratio` heads of its point.

    A skip or a fan that leaves an arrow just behind its head reads as part of the
    head, and its line runs nearer the box than the arrow's own shaft.
    """
    heads, lines = _drawing(svg)
    found: list[CrowdedJunction] = []
    for points in lines:
        if len(points) < 2:
            continue
        arrow = _head_reach(points, heads)
        if arrow is None:
            continue
        (ax, ay), tip, length = arrow
        start, end = points[-2], points[-1]
        for other in lines:
            if other is points:
                continue
            for joint in (other[0], other[-1]):
                # Inside the last run: a shared start is a fan, a shared end a join.
                if min(math.dist(joint, start), math.dist(joint, end)) < TOUCH or not _touches(
                    joint, [start, end]
                ):
                    continue
                gap = (end[0] - joint[0]) * ax + (end[1] - joint[1]) * ay + tip
                if length > 0 and gap < ratio * length - 1e-6:
                    found.append(CrowdedJunction(joint, gap, length, ratio))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("svg", nargs="+", type=Path, help="drawings, or folders of them")
    parser.add_argument("--ratio", type=float, default=RATIO, help="run per head length")
    parser.add_argument(
        "--junction", type=float, default=JUNCTION, help="branch distance per head length"
    )
    args = parser.parse_args(argv)
    paths = [
        found
        for path in args.svg
        for found in (sorted(path.glob("*.svg")) if path.is_dir() else [path])
    ]
    total = 0
    for path in paths:
        svg = path.read_text(encoding="utf-8")
        for problem in [
            *short_arrows(svg, ratio=args.ratio),
            *crowded_junctions(svg, ratio=args.junction),
        ]:
            print(f"{path}: {problem}")
            total += 1
    print(f"{total} short arrow(s) or crowded junction(s) in {len(paths)} drawing(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
