"""The `mindmap` kind: one topic in the middle, its branches radiating to both sides.

A mind map says the opposite of a `tree`. A tree is ranked from a root at one
edge — *this first, then these* — while a mind map puts the topic in the middle
and makes every main branch a peer round it. Its content is strictly nested, so
the structure is the nesting and there are no edges to get wrong.

**The centre** is the one strongly boxed element: a pill in the `terminal` role,
its words bold.

**The two sides.** The main branches go clockwise from the top right in the order
written: the first few down the right side, top to bottom, and the rest up the
left side, bottom to top. Where the split falls is the one that best balances the
two sides' heights (then their leaf counts), and the first branch is always on
the right, so the same document always draws the same way. Each side is centred
on the centre's middle.

**Each side is a horizontal tidy tree** growing away from the centre — the left
side mirrored. A branch's children are stacked top to bottom in the order written,
the branch centred between its first and last child, and no subtree shares a
height with a sibling's, which is what keeps every line clear of every word: a
line only runs between its parent and its child, inside that parent's band. The
main branches bulge out round the centre — the ones nearest its middle set
furthest from it — so the map reads as radial rather than as two columns, and the
bulge is dropped before any word is wrapped narrower to fit.

**Lines** are smooth curves, leaving the parent level and arriving level, drawn
as tapered ribbons whose widths are the theme's `[mindmap] taper`. A main branch
is boxed lightly, its words bold; a twig or a leaf sits on its line, which runs on
under its words (`[mindmap] boxes = true` boxes them instead). Type thins by
level too: the body size for main branches and twigs, the label size for leaves.

**Roles.** `emphasis` sets a branch bold and draws its line, and every line back
to the centre, half as thick again, so the path to the branch the map is about is
one heavy stroke in greyscale. `note` is context: faint words on a light dashed
line, and so is everything under it.

When the words do not fit the canvas, twigs and leaves wrap narrower until they
do; when no width works, `FitError` names the longest.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import outline, text_runs
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import Document, MindmapBranch
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, bold_lines, wrap
from drawspec.theme import Theme

#: The most of the canvas the centre's pill, and a main branch's box, may take;
#: the centre may widen past its share to keep from standing too tall.
CENTRE_SHARE: Final = 0.24
CENTRE_WIDEN: Final = 1.5
MAIN_SHARE: Final = 0.2

#: The narrowest a twig or leaf may be wrapped to, as a share of the canvas,
#: before the map is refused as too wide; and each narrower attempt's share of
#: the one before.
LEAF_MIN_SHARE: Final = 0.1
LEAF_STEP: Final = 0.92

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
CENTRE_GAP: Final = 30.0
"""Across: the least distance from the centre's side to a main branch's box."""
BULGE: Final = 22.0
"""Across: how much further out the main branches nearest the centre's middle sit."""
CHILD_GAP: Final = 22.0
"""Across: from where a branch's line leaves it to where its child's begins."""
MAIN_GAP: Final = 12.0
"""Down: between the bands of two main branches on one side."""
SIBLING_GAP: Final = 5.0
"""Down: between the bands of two twigs or leaves under one branch."""
TEXT_GAP: Final = 2.5
"""From the bottom of a branch's words to the line they sit on."""
OVERHANG: Final = 4.0
"""How far a branch's line runs past each end of its words."""

#: How much thicker the lines to an `emphasis` branch are drawn.
HEAVY: Final = 1.5

#: The narrowing of the last level's line where it arrives.
LAST_NARROWING: Final = 2 / 3

#: How many straight pieces one curved line is drawn in.
SAMPLES: Final = 24

#: Where a main branch's line starts, as a share of the centre's rounded end's
#: radius: just inside its outline, so line and outline meet without a seam.
INSET: Final = 0.94

#: The steepest a main branch's line may leave the centre, from the horizontal.
STEEPEST: Final = math.radians(65)

#: The roles lines and words are drawn in: an ordinary line is a filled ribbon in
#: the `flow` edge role; a `note` line is the light dashed `aside`.
LINE_ROLE: Final = "flow"
FAINT_LINE_ROLE: Final = "aside"
CENTRE_ROLE: Final = "terminal"

#: The type level for each depth below the centre.
LEVELS: Final = {1: "body", 2: "body", 3: "label"}

#: A rectangle: left, top, right, bottom.
type Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class BranchDrawn:
    """Where one branch landed, in final coordinates."""

    path: tuple[int, ...]
    """Its indices from the root: `(2, 0)` is the first branch of the third main one."""

    text: str
    depth: int
    side: str
    """`right` or `left`."""

    words: Rect
    """The measured extent of its words."""

    ink: Rect
    """Its words and its box or line together."""

    role: str
    boxed: bool


@dataclass(frozen=True)
class LineDrawn:
    """One branch line: from its parent to the branch, sampled along the curve."""

    to: tuple[int, ...]
    points: tuple[tuple[float, float], ...]
    widths: tuple[float, float]
    """Where it leaves and where it arrives; zero for a `note`'s dashed line."""

    role: str


@dataclass(frozen=True)
class MindmapDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    centre: Rect = (0.0, 0.0, 0.0, 0.0)
    branches: tuple[BranchDrawn, ...] = field(default_factory=tuple)
    lines: tuple[LineDrawn, ...] = field(default_factory=tuple)
    right: tuple[int, ...] = ()
    """The main branches on the right, by index, top to bottom."""

    left: tuple[int, ...] = ()
    """The main branches on the left, by index, top to bottom."""


@dataclass
class _Node:
    """A branch sized, before it is placed: x outwards from the centre, y down."""

    branch: MindmapBranch
    path: tuple[int, ...]
    depth: int
    role: str
    """What it is drawn as: `emphasis`, `note` (itself or inherited) or `step`."""

    heavy: bool
    """Whether its line is on the path from the centre to an `emphasis` branch."""

    block: TextBlock
    box: Box | None
    width: float
    up: float
    down: float
    children: list[_Node]
    offsets: list[float] = field(default_factory=list)
    """Each child's line height, relative to this one's."""

    band_up: float = 0.0
    band_down: float = 0.0
    x: float = 0.0
    y: float = 0.0

    @property
    def leaves(self) -> int:
        return sum(child.leaves for child in self.children) if self.children else 1


def mindmap_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a mind map."""
    return mindmap_drawing(document, theme, measurer).scene


def mindmap_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> MindmapDrawing:
    """Lay the map out, wrapping twigs and leaves narrower until it fits the canvas.

    Only the branch reaching furthest out on the wider side is wrapped narrower at
    each step, so a short branch keeps its words on one line while a long one
    elsewhere is broken.

    Raises:
        FitError: no width for the twigs and leaves fits the canvas, or a word is
            wider than the narrowest width one may have.
    """
    width = theme.canvas.width
    floor = width * LEAF_MIN_SHARE
    caps = [
        max(
            [
                floor,
                *(
                    _natural(_words(branch), LEVELS[depth], theme, measurer)
                    for branch, depth in _walk((main,), 1)
                    if depth > 1 or main.role == "note"
                ),
            ]
        )
        for main in document.branches
    ]
    widest = list(caps)

    def search(caps: list[float], floors: list[float]) -> MindmapDrawing | None:
        while True:
            drawing, culprit = _attempt(document, theme, measurer, caps, floors)
            if drawing is not None or culprit is None:
                return drawing
            index, narrower = culprit
            if narrower:
                caps[index] = max(floors[index], caps[index] * LEAF_STEP)
            elif caps[index] >= widest[index] - 1e-9:
                raise FitError(
                    f"the branch {document.branches[index].text[:40]!r} holds a word wider "
                    f"than a branch can be at a width of {width:.0f}. Shorten it, or give the "
                    f"diagram more width."
                )
            else:
                # A word in this branch is wider than its cap: the step before was
                # its narrowest, so it goes back there and stays.
                caps[index] = floors[index] = min(widest[index], caps[index] / LEAF_STEP)

    # The tightest map first: if even that is too wide, nothing looser is worth
    # trying — and the narrowest each branch can go is then known.
    floors = [floor] * len(caps)
    if search([floor] * len(caps), floors) is not None:
        drawing = search(caps, floors)
        if drawing is not None:
            return drawing
    longest = max(
        (branch for branch, _ in _walk(document.branches, 1)),
        key=lambda branch: _natural(_words(branch), "body", theme, measurer),
    )
    raise FitError(
        f"the mind map does not fit a width of {width:.0f}, even with every twig and leaf "
        f"wrapped to {floor:.0f}. The longest branch is {longest.text[:48]!r}: shorten it — "
        f"a leaf is a phrase, not a sentence — use fewer levels, or give the diagram more "
        f"width."
    )


def _walk(branches: tuple[MindmapBranch, ...], depth: int) -> list[tuple[MindmapBranch, int]]:
    found: list[tuple[MindmapBranch, int]] = []
    for branch in branches:
        found.append((branch, depth))
        found.extend(_walk(branch.branches, depth + 1))
    return found


def _attempt(
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
    caps: list[float],
    floors: list[float],
) -> tuple[MindmapDrawing | None, tuple[int, bool] | None]:
    """The map with each main branch's twigs and leaves wrapped to its cap.

    Returns the drawing, or `None` and what to change next: a main branch, and
    whether to wrap it narrower (`True`) or give back the last step because a
    word did not fit (`False`). `None` for that when nothing is left to change.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    try:
        centre = _box(
            bold_lines(document.centre),
            theme,
            measurer,
            role=CENTRE_ROLE,
            level="body",
            max_width=width * CENTRE_SHARE,
            shape="pill",
            widen=CENTRE_WIDEN,
        )
    except FitError as error:
        raise FitError(
            f"the centre {document.centre[:40]!r} has a word wider than the "
            f"{width * CENTRE_SHARE:.0f} units it can have. Shorten it, or give the diagram "
            f"more width."
        ) from error
    if centre.width < centre.height:
        # A pill narrower than it is tall is a lozenge standing on end; the
        # topic is a word or two, and its lines leave from the rounded sides.
        centre = centre.resized(width=centre.height)
    mains: list[_Node] = []
    for index, branch in enumerate(document.branches):
        try:
            mains.append(_sized(branch, (index,), 1, False, theme, measurer, caps[index], unit))
        except FitError:
            return None, (index, False)
    for node in mains:
        _band(node, unit)

    split = _split(mains, unit)
    right = mains[:split]
    left = list(reversed(mains[split:]))
    for side in (right, left):
        _stack(side, unit)
    half = centre.width / 2

    def placed(bulge: float) -> float:
        reach = max(abs(node.y) for node in mains) * 1.3 or 1.0
        for node in mains:
            lift = min(1.0, abs(node.y) / reach)
            node.x = half + CENTRE_GAP * unit + bulge * math.sqrt(1 - lift * lift)
            _place(node, unit)
        return max([half, *map(_reach, right)]) + max([half, *map(_reach, left)])

    # The bulge is what room is left: never a reason to wrap a word.
    slack = width - placed(0.0)
    if slack < -1e-6:
        # Only a branch that reaches past what the other side leaves is worth
        # wrapping narrower; the wider side is tried first.
        extents = {id(side): max([half, *map(_reach, side)]) for side in (right, left)}
        wider = right if extents[id(right)] >= extents[id(left)] else left
        for side in (wider, right if wider is left else left):
            other = left if side is right else right
            allowed = width - extents[id(other)]
            open_ = [
                node
                for node in side
                if caps[node.path[0]] > floors[node.path[0]] and _reach(node) > allowed + 1e-6
            ]
            if open_:
                culprit = max(open_, key=_reach)
                # The cap only matters once it is under the widest block it wraps:
                # anything between changes nothing, so the next try starts there.
                caps[culprit.path[0]] = min(caps[culprit.path[0]], _widest(culprit) + 1e-3)
                return None, (culprit.path[0], True)
        return None, None
    placed(min(BULGE * unit, slack / 2))
    return _drawing(document, theme, measurer, centre, right, left, unit), None


def _sized(
    branch: MindmapBranch,
    path: tuple[int, ...],
    depth: int,
    faint: bool,
    theme: Theme,
    measurer: TextMeasurer,
    cap: float,
    unit: float,
) -> _Node:
    """A branch and everything under it, sized but not placed."""
    faint = faint or branch.role == "note"
    role = "note" if faint else branch.role
    children = [
        _sized(child, (*path, index), depth + 1, faint, theme, measurer, cap, unit)
        for index, child in enumerate(branch.branches)
    ]
    heavy = role == "emphasis" or any(child.heavy for child in children)
    level = LEVELS[depth]
    words = _words(branch, bold=depth == 1)
    boxed = not faint and (depth == 1 or theme.mindmap.boxes)
    if boxed:
        box = _box(
            words,
            theme,
            measurer,
            role="emphasis" if role == "emphasis" else "step",
            level=level,
            max_width=width_share(theme) if depth == 1 else cap + theme.box.padding.horizontal,
            shape="rect",
        )
        return _Node(
            branch=branch,
            path=path,
            depth=depth,
            role=role,
            heavy=heavy,
            block=box.block,
            box=box,
            width=box.width,
            up=box.height / 2,
            down=box.height / 2,
            children=children,
        )
    limit = width_share(theme) if depth == 1 else cap
    block = _balanced(words, limit, level, theme, measurer)
    return _Node(
        branch=branch,
        path=path,
        depth=depth,
        role=role,
        heavy=heavy,
        block=block,
        box=None,
        width=block.width + 2 * OVERHANG * unit,
        up=block.height + TEXT_GAP * unit,
        down=unit,
        children=children,
    )


def width_share(theme: Theme) -> float:
    """The widest a main branch may be."""
    return theme.canvas.width * MAIN_SHARE


def _band(node: _Node, unit: float) -> None:
    """The heights `node` and everything under it take above and below its line."""
    for child in node.children:
        _band(child, unit)
    if not node.children:
        node.band_up, node.band_down = node.up, node.down
        return
    gap = SIBLING_GAP * unit
    lines = [0.0]
    for above, below in zip(node.children, node.children[1:], strict=False):
        lines.append(lines[-1] + above.band_down + gap + below.band_up)
    middle = (lines[0] + lines[-1]) / 2
    node.offsets = [line - middle for line in lines]
    first, last = node.children[0], node.children[-1]
    node.band_up = max(node.up, -(node.offsets[0] - first.band_up))
    node.band_down = max(node.down, node.offsets[-1] + last.band_down)


def _split(mains: list[_Node], unit: float) -> int:
    """How many main branches go on the right: the most balanced split.

    Balanced by drawn height first, the thing the eye compares, and then by leaf
    count; a tie goes to the right side holding more.
    """
    gap = MAIN_GAP * unit

    def height(nodes: list[_Node]) -> float:
        return sum(node.band_up + node.band_down for node in nodes) + gap * (len(nodes) - 1)

    def cost(count: int) -> tuple[float, int, int]:
        right, left = mains[:count], mains[count:]
        return (
            round(abs(height(right) - height(left)), 6),
            abs(sum(node.leaves for node in right) - sum(node.leaves for node in left)),
            -count,
        )

    return min(range(1, len(mains)), key=cost)


def _stack(side: list[_Node], unit: float) -> None:
    """One side's main branches top to bottom, centred on the centre's middle."""
    gap = MAIN_GAP * unit
    cursor = 0.0
    lines: list[float] = []
    for node in side:
        lines.append(cursor + node.band_up)
        cursor = lines[-1] + node.band_down + gap
    total = cursor - gap
    for node, line in zip(side, lines, strict=True):
        node.y = line - total / 2


def _place(node: _Node, unit: float) -> None:
    for child, offset in zip(node.children, node.offsets, strict=True):
        child.x = node.x + node.width + CHILD_GAP * unit
        child.y = node.y + offset
        _place(child, unit)


def _widest(node: _Node) -> float:
    """The widest block wrapped to a cap in `node`'s subtree: twigs and leaves."""
    own = node.block.width if node.depth > 1 or node.role == "note" else 0.0
    return max([own, *(_widest(child) for child in node.children)])


def _reach(node: _Node) -> float:
    return max([node.x + node.width, *(_reach(child) for child in node.children)])


def _drawing(
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
    centre: Box,
    right: list[_Node],
    left: list[_Node],
    unit: float,
) -> MindmapDrawing:
    lines: list[Primitive] = []
    shapes: list[Primitive] = []
    texts: list[Primitive] = []
    drawn: list[BranchDrawn] = []
    lines_drawn: list[LineDrawn] = []
    taper = theme.mindmap.taper

    def widths(node: _Node) -> tuple[float, float]:
        start = taper[node.depth - 1]
        end = taper[node.depth] if node.depth < len(taper) else taper[-1] * LAST_NARROWING
        scale = HEAVY if node.heavy else 1.0
        return start * scale, end * scale

    def underline_width(node: _Node) -> float:
        return widths(node)[1]

    def draw(node: _Node, sign: float, start: tuple[float, float], heading: float) -> None:
        side = "right" if sign > 0 else "left"
        near = (node.x, node.y)
        curve = _curve(start, near, heading)
        faint = node.role == "note"
        if faint:
            points = tuple((sign * x, y) for x, y in curve)
            lines.append(Path(FAINT_LINE_ROLE, points=points))
            lines_drawn.append(LineDrawn(node.path, points, (0.0, 0.0), FAINT_LINE_ROLE))
        else:
            begin, end = widths(node)
            ribbon = _ribbon(curve, begin, end)
            lines.append(Polygon(LINE_ROLE, points=tuple((sign * x, y) for x, y in ribbon)))
            lines_drawn.append(
                LineDrawn(
                    node.path, tuple((sign * x, y) for x, y in curve), (begin, end), LINE_ROLE
                )
            )

        text_role = node.role if node.role in ("note",) else "step"
        if node.box is not None:
            left_x = node.x if sign > 0 else -(node.x + node.width)
            box = node.box.moved_to(left_x, node.y - node.box.height / 2)
            shapes.extend(outline(box, theme))
            texts.extend(text_runs(box, theme, measurer))
            words = box.content_bounds()
            ink: Rect = (box.x, box.y, box.x + box.width, box.y + box.height)
            leave = (node.x + node.width, node.y)
        else:
            line_y = node.y
            top = line_y - TEXT_GAP * unit - node.block.height
            text_x = node.x + OVERHANG * unit
            anchor = "start" if sign > 0 else "end"
            texts.extend(
                _lines(node.block, sign * text_x, top, text_role, LEVELS[node.depth], anchor)
            )
            low, high = sorted((sign * text_x, sign * (text_x + node.block.width)))
            words = (low, top, high, top + node.block.height)
            far = node.x + node.width
            thick = underline_width(node)
            if faint:
                shapes.append(
                    Path(FAINT_LINE_ROLE, points=((sign * node.x, line_y), (sign * far, line_y)))
                )
            else:
                shapes.append(
                    Polygon(
                        LINE_ROLE,
                        points=(
                            (sign * node.x, line_y - thick / 2),
                            (sign * far, line_y - thick / 2),
                            (sign * far, line_y + thick / 2),
                            (sign * node.x, line_y + thick / 2),
                        ),
                    )
                )
            a, b = sorted((sign * node.x, sign * far))
            ink = (min(a, words[0]), words[1], max(b, words[2]), line_y + max(thick, unit) / 2)
            leave = (far, line_y)
        drawn.append(
            BranchDrawn(
                path=node.path,
                text=node.branch.text,
                depth=node.depth,
                side=side,
                words=words,
                ink=ink,
                role=node.role,
                boxed=node.box is not None,
            )
        )
        for child in node.children:
            draw(child, sign, leave, 0.0)

    half_w, half_h = centre.width / 2, centre.height / 2
    radius = min(half_h, half_w)
    for sign, side in ((1.0, right), (-1.0, left)):
        for node in side:
            # The line leaves the centre's rounded end, aimed at the branch, so the
            # main lines fan out from it rather than all leaving one point.
            cap_x = half_w - radius
            angle = math.atan2(node.y, node.x - cap_x)
            angle = max(-STEEPEST, min(STEEPEST, angle))
            start = (cap_x + radius * math.cos(angle) * INSET, radius * math.sin(angle) * INSET)
            draw(node, sign, start, angle)

    box = centre.moved_to(-half_w, -half_h)
    shapes.extend(outline(box, theme))
    texts.extend(text_runs(box, theme, measurer))

    left_edge = min(-half_w, *(entry.ink[0] for entry in drawn))
    right_edge = max(half_w, *(entry.ink[2] for entry in drawn))
    top = min(-half_h, *(entry.ink[1] for entry in drawn))
    bottom = max(half_h, *(entry.ink[3] for entry in drawn))
    dx, dy = -left_edge, -top
    scene = Scene(
        width=right_edge - left_edge,
        height=bottom - top,
        primitives=tuple(moved(primitive, dx, dy) for primitive in (*lines, *shapes, *texts)),
        title=document.title,
        description=document.description,
    )

    def shifted(rect: Rect) -> Rect:
        return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)

    return MindmapDrawing(
        scene=scene,
        centre=shifted((-half_w, -half_h, half_w, half_h)),
        branches=tuple(
            BranchDrawn(
                path=entry.path,
                text=entry.text,
                depth=entry.depth,
                side=entry.side,
                words=shifted(entry.words),
                ink=shifted(entry.ink),
                role=entry.role,
                boxed=entry.boxed,
            )
            for entry in drawn
        ),
        lines=tuple(
            LineDrawn(
                to=line.to,
                points=tuple((x + dx, y + dy) for x, y in line.points),
                widths=line.widths,
                role=line.role,
            )
            for line in lines_drawn
        ),
        right=tuple(node.path[0] for node in right),
        left=tuple(node.path[0] for node in left),
    )


def _curve(
    start: tuple[float, float], end: tuple[float, float], heading: float
) -> tuple[tuple[float, float], ...]:
    """A smooth line from `start`, leaving at `heading`, arriving at `end` level."""
    reach = max(end[0] - start[0], 1.0)
    lead = reach * 0.5
    c1 = (start[0] + lead * math.cos(heading), start[1] + lead * math.sin(heading))
    c2 = (end[0] - reach * 0.5, end[1])
    found: list[tuple[float, float]] = []
    for step in range(SAMPLES + 1):
        t = step / SAMPLES
        u = 1 - t
        found.append(
            (
                u**3 * start[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
                u**3 * start[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1],
            )
        )
    return tuple(found)


def _ribbon(
    curve: tuple[tuple[float, float], ...], begin: float, end: float
) -> tuple[tuple[float, float], ...]:
    """The curve as a filled band narrowing from `begin` to `end` wide."""
    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    count = len(curve) - 1
    for index, (x, y) in enumerate(curve):
        before = curve[max(index - 1, 0)]
        after = curve[min(index + 1, count)]
        tx, ty = after[0] - before[0], after[1] - before[1]
        length = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / length, tx / length
        t = index / count
        half = (begin + (end - begin) * t) / 2
        upper.append((x + nx * half, y + ny * half))
        lower.append((x - nx * half, y - ny * half))
    return (*upper, *reversed(lower))


def _words(branch: MindmapBranch, *, bold: bool = False) -> str:
    """A branch's words as set: a main branch and an `emphasis` one are bold."""
    if bold or branch.role == "emphasis":
        return bold_lines(branch.text)
    return branch.text


def _natural(text: str, level: str, theme: Theme, measurer: TextMeasurer) -> float:
    """How wide `text` is set on its own lines, unbroken."""
    return wrap(text, 1e6, measurer, theme=theme, level=level).width


#: Wrapped blocks and sized boxes already worked out, by everything that decides
#: them. The fit tries a branch at many widths and the type at several scales,
#: and the same words come back at the same width over and over.
_CACHE: dict[tuple[object, ...], object] = {}
_CACHE_SIZE: Final = 4096


def _key(theme: Theme, measurer: TextMeasurer, *parts: object) -> tuple[object, ...]:
    return (*parts, theme.scale, theme.box, theme.font, theme.canvas.width, id(measurer))


def _remembered[T](key: tuple[object, ...], make: Callable[[], T]) -> T:
    if key not in _CACHE:
        if len(_CACHE) >= _CACHE_SIZE:
            _CACHE.clear()
        _CACHE[key] = make()
    return _CACHE[key]  # type: ignore[return-value]


def _box(
    text: str,
    theme: Theme,
    measurer: TextMeasurer,
    *,
    role: str,
    level: str,
    max_width: float,
    shape: str,
    widen: float = 1.0,
) -> Box:
    """`size_box`, remembered."""
    return _remembered(
        _key(theme, measurer, "box", text, role, level, round(max_width, 6), shape, widen),
        lambda: size_box(
            text,
            theme=theme,
            measurer=measurer,
            role=role,
            level=level,
            max_width=max_width,
            shape=shape,
            widen=widen,
        ),
    )


def _balanced(
    text: str, width: float, level: str, theme: Theme, measurer: TextMeasurer
) -> TextBlock:
    """`text` wrapped to `width`, then as narrow as it goes on as many lines."""
    return _remembered(
        _key(theme, measurer, "block", text, round(width, 6), level),
        lambda: _balance(text, width, level, theme, measurer),
    )


def _balance(
    text: str, width: float, level: str, theme: Theme, measurer: TextMeasurer
) -> TextBlock:
    block = wrap(text, width, measurer, theme=theme, level=level)
    if len(block.lines) < 2:
        return block
    low, high = width / 2, width
    for _ in range(10):
        middle = (low + high) / 2
        try:
            trial = wrap(text, middle, measurer, theme=theme, level=level)
        except FitError:
            low = middle
            continue
        if len(trial.lines) == len(block.lines):
            high, block = middle, trial
        else:
            low = middle
    return block


def _lines(
    block: TextBlock, x: float, top: float, role: str, level: str, anchor: str
) -> list[TextLine]:
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(
                    role,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor=anchor,
                )
            )
    return found


__all__ = [
    "BranchDrawn",
    "LineDrawn",
    "MindmapDrawing",
    "mindmap_drawing",
    "mindmap_scene",
]
