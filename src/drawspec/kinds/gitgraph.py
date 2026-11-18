"""The `gitgraph` kind: commits on branches over time, forked, merged and tagged.

A layout family of its own. The input is a list of branches and an ordered list
of steps — a commit `on` a branch, a `merge` of another branch into it, or a
`pick` of an earlier commit — and every position is derived from that order:

**One lane per branch, one place in time per step.** Lanes are in the order the
branches are written, the trunk first; steps are in the order written, evenly
spaced, so the drawing is the history git would have made. Time runs `right`
across the page (the default), each commit's label under its mark, or `down`
it, the labels in a column beside the lanes as `git log --graph` sets them.

**A line between two lanes is a fork or a merge, never a guess.** A branch
forks from its `from` at its first step, and the line leaves the parent just
after it; a merge's line arrives just before the merge commit. Both turn in the
gap between two steps, never under a label, with rounded corners.

**The kind of commit is its mark, in greyscale.** A commit is a dot; a merge
commit a ring round a dot; a cherry-pick a dashed ring round a dot — a copy;
the commit the figure is about (`emphasis`) a square, its label bold. A tag is
a luggage tag beside the commit. Colour, when the theme gives `[gitgraph]
colours`, fills a lane's dots and washes its name; it never carries alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.kinds.treemap import bold
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Rect, Scene, TextLine, TextSpan
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.textgrid import Grid, cells, finished, label_lines, too_wide, wrapped
from drawspec.textgrid import caption_lines as text_caption_lines
from drawspec.theme import Theme

#: The edge role a lane and its forks and merges are drawn in; an emphasised
#: branch takes the heavier one, and the guide from a name to its lane the faint one.
LINE_ROLE: Final = "flow"
STRONG_ROLE: Final = "strong"
GUIDE_ROLE: Final = "aside"

#: The node roles of the marks: a commit (and a merge's ring), a cherry-pick's
#: dashed ring, the emphasised commit's square.
MARK_ROLE: Final = FURNITURE_ROLE
COPY_ROLE: Final = "note"
EMPHASIS_ROLE: Final = "emphasis"

#: Lengths as shares of the body size, so the drawing scales with the type.
DOT: Final = 0.42
"""A commit dot's radius."""
RING: Final = 1.45
"""A merge or a cherry-pick ring's radius, as a share of the dot's."""
SQUARE: Final = 1.2
"""Half the side of an emphasised commit's square, as a share of the dot's radius."""
SLOT: Final = 1.1
"""The band between two steps that a fork or a merge turns in."""
PAD: Final = 0.4
"""The breathing room between a mark and its label, a label and the next lane."""
CORNER: Final = 0.55
"""A turn's radius, at most."""

#: How much of a lane's colour washes its name.
WASH: Final = 0.18

#: The most room a label gets across the page, in body sizes, before it wraps.
LABEL_MAX: Final = 9.0

#: The least share of the width the label column keeps when time runs down.
COLUMN_MIN: Final = 0.3

Point = tuple[float, float]


@dataclass(frozen=True)
class _Commit:
    """One step, replayed: where it sits and what it joins."""

    index: int
    lane: int
    kind: str
    """`commit`, `merge` or `pick`."""
    label: str
    tag: str
    role: str
    parent: int | None
    """The first parent's step index, or None for the trunk's first commit."""
    merged: int | None = None
    """For a merge, the merged branch's latest commit."""
    starts: bool = False
    """Whether this is its branch's first commit."""


def history(document: Document) -> list[_Commit]:
    """The steps replayed in order, each with its lane and its parents.

    The document is validated, so every name and handle resolves.
    """
    lanes = {branch.name: index for index, branch in enumerate(document.git_branches)}
    sources = {
        branch.name: branch.source or document.git_branches[0].name
        for branch in document.git_branches[1:]
    }
    ids = {step.id: index for index, step in enumerate(document.git_steps) if step.id}
    tips: dict[str, int] = {}
    commits: list[_Commit] = []
    for index, step in enumerate(document.git_steps):
        starts = step.on not in tips
        parent: int | None
        if not starts:
            parent = tips[step.on]
        elif step.on in sources:
            source = sources[step.on]
            parent = tips[source] if source in lanes else ids[source]
        else:
            parent = None
        kind = "merge" if step.merge else "pick" if step.pick else "commit"
        label = step.text or step.id
        if step.pick and not step.text:
            # The original's label as already worked out, so a pick of a pick
            # still carries the first commit's words.
            label = commits[ids[step.pick]].label
        commits.append(
            _Commit(
                index=index,
                lane=lanes[step.on],
                kind=kind,
                label=label,
                tag=step.tag,
                role=step.role,
                parent=parent,
                merged=tips[step.merge] if step.merge else None,
                starts=starts,
            )
        )
        tips[step.on] = index
    return commits


@dataclass(frozen=True)
class GitgraphDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    marks: tuple[Point, ...] = ()
    """Each step's mark centre, in the order written."""
    lanes: tuple[float, ...] = ()
    """Each lane's cross-axis position: its y across the page, its x down it."""
    texts: tuple[tuple[float, float, float, float], ...] = field(default=())
    """Every piece of text placed, as boxes, for the tests that nothing overlaps."""
    connectors: tuple[tuple[Point, ...], ...] = ()
    """Every fork and merge line, as drawn."""


def gitgraph_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a git graph."""
    return gitgraph_drawing(document, theme, measurer).scene


def _block(text: str, room: float, measurer: TextMeasurer, theme: Theme, what: str) -> TextBlock:
    try:
        return wrap(text, max(room, 1.0), measurer, theme=theme, level="body", lead=False)
    except FitError as error:
        raise FitError(
            f"{what} {text!r} has a word wider than the {room:.0f} units it gets. Shorten "
            f"it, give the diagram more width, or draw it with `direction: down`."
        ) from error


def _lines(block: TextBlock, x: float, top: float, anchor: str) -> list[TextLine]:
    """A wrapped block as TextLines from `top` down, anchored at `x`."""
    out: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            out.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="body",
                    anchor=anchor,
                )
            )
    return out


def _turned(points: list[Point], radius: float) -> tuple[Point, ...]:
    """An orthogonal polyline with each inner corner rounded to `radius`."""
    if len(points) < 3 or radius <= 0:
        return tuple(points)
    out: list[Point] = [points[0]]
    for before, corner, after in zip(points, points[1:], points[2:], strict=False):
        into = math.dist(before, corner)
        out_of = math.dist(corner, after)
        bend = min(radius, into / 2, out_of / 2)
        if bend <= 0:
            out.append(corner)
            continue
        ux, uy = (corner[0] - before[0]) / into, (corner[1] - before[1]) / into
        vx, vy = (after[0] - corner[0]) / out_of, (after[1] - corner[1]) / out_of
        start = (corner[0] - ux * bend, corner[1] - uy * bend)
        end = (corner[0] + vx * bend, corner[1] + vy * bend)
        # A quarter circle, sampled: the centre is `bend` along both legs' normals.
        centre = (start[0] + vx * bend, start[1] + vy * bend)
        a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
        a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
        sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        steps = 6
        for step in range(steps + 1):
            angle = a0 + sweep * step / steps
            out.append((centre[0] + bend * math.cos(angle), centre[1] + bend * math.sin(angle)))
    out.append(points[-1])
    return tuple(out)


def gitgraph_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> GitgraphDrawing:
    """Lay the lanes and the steps out on the canvas.

    Raises:
        FitError: the steps, or a word in a label, do not fit the width at this
            type scale.
    """
    commits = history(document)
    branches = document.git_branches
    down = document.git_direction == "down"
    width = document.width if document.width else theme.canvas.width
    body = theme.scale["body"]
    font = theme.font.default
    dot = DOT * body
    ring = RING * dot
    slot = SLOT * body
    pad = PAD * body
    corner = CORNER * body
    style = theme.gitgraph

    def reach(commit: _Commit) -> float:
        """How far a commit's mark reaches from its centre, where a line stops."""
        if commit.role == "emphasis":
            return SQUARE * dot * 1.15
        return ring if commit.kind != "commit" else dot

    # -- names -----------------------------------------------------------------
    name_extents = [measurer.measure(branch.name, font, body, "bold") for branch in branches]
    name_pad = 0.6 * body
    name_h = theme.box.line_height * body + 0.5 * body
    name_w = [extent.width + 2 * name_pad for extent in name_extents]

    # -- tags ------------------------------------------------------------------
    label_size = theme.scale["body"]
    tag_pad = 0.4 * body
    tag_point = 0.45 * body
    tag_h = theme.box.line_height * label_size + 0.3 * body
    tag_w = [
        measurer.measure(commit.tag, font, label_size).width + 2 * tag_pad if commit.tag else 0.0
        for commit in commits
    ]

    def text_of(commit: _Commit) -> str:
        return bold(commit.label) if commit.role == "emphasis" and commit.label else commit.label

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    boxes: list[tuple[float, float, float, float]] = []
    count = len(commits)
    name_rows: list[int] = [0] * len(branches)

    if not down:
        # -- across the page: a column per step ---------------------------------
        graph_left = max(name_w) + slot
        room = width - graph_left
        natural = [
            _block(text_of(c), LABEL_MAX * body, measurer, theme, "the label").width
            if c.label
            else 0.0
            for c in commits
        ]
        wanted = max([*natural, *(w + tag_point for w in tag_w), 2 * ring]) + slot + 0.5 * body
        least = 2 * ring + 2 * slot + 2 * corner
        spacing = min(room / count, max(wanted, 4.5 * body))
        if spacing < least:
            raise FitError(
                f"{count} steps need {least * count + graph_left:.0f} units across and the "
                f"diagram is {width:.0f} wide. Draw it with `direction: down`, give it more "
                f"width, or split the history in two."
            )
        label_room = spacing - slot - 0.5 * body
        blocks = [
            _block(text_of(c), label_room, measurer, theme, "the label") if c.label else None
            for c in commits
        ]
        for commit, tag in zip(commits, tag_w, strict=True):
            if tag > label_room:
                raise FitError(
                    f"the tag {commit.tag!r} is {tag:.0f} units wide and a step gets "
                    f"{spacing:.0f}. Shorten it, give the diagram more width, or draw it "
                    f"with `direction: down`."
                )
        label_h = max([block.height for block in blocks if block] + [0.0])
        has_tags = any(commit.tag for commit in commits)
        between = max(label_h, tag_h + tag_point if has_tags else 0.0)
        pitch = max(2 * ring + 3 * pad + between, name_h + pad)
        top_room = max(
            name_h / 2,
            (ring + pad + tag_h + tag_point) if any(c.tag for c in commits if c.lane == 0) else 0,
            ring,
        )
        cross = [top_room + lane * pitch for lane in range(len(branches))]
        along = [graph_left + spacing * (index + 0.5) for index in range(count)]
        last = len(branches) - 1
        bottom = cross[last] + max(
            name_h / 2,
            ring
            + pad
            + max(
                [b.height for c, b in zip(commits, blocks, strict=True) if b and c.lane == last]
                + [0.0]
            ),
        )

        def at(t: float, c: float) -> Point:
            return (t, c)

        fork_slot = [along[i] + spacing / 2 - slot / 2 for i in range(count)]
        merge_slot = [along[i] - spacing / 2 + slot / 2 for i in range(count)]
    else:
        # -- down the page: a row per step, labels in a column ------------------
        # The names head their lanes. Side by side when they fit; staggered over
        # two rows when that packs the lanes closer, each name clear of the guides
        # running down past it from the row above.
        many = len(branches)
        least_pitch = 2 * ring + 2 * slot
        single = max(
            [least_pitch] + [(name_w[k] + name_w[k + 1]) / 2 + slot for k in range(many - 1)]
        )
        staggered = max(
            [least_pitch]
            + [name_w[k] / 2 + slot / 2 for k in range(1, many, 2)]
            + [((name_w[k] + name_w[k + 2]) / 2 + slot) / 2 for k in range(many - 2)]
        )
        lane_pitch = min(single, staggered)
        name_rows[:] = [lane % 2 if staggered < single else 0 for lane in range(many)]
        first_lane = max(lane_pitch / 2, name_w[0] / 2)
        cross = [first_lane + lane_pitch * lane for lane in range(many)]
        column = cross[-1] + ring + slot
        column_w = width - column
        if column_w < COLUMN_MIN * width:
            raise FitError(
                f"{len(branches)} lanes {lane_pitch:.0f} units apart, sized to the longest "
                f"branch name, leave the labels {max(column_w, 0):.0f} of {width:.0f} units. "
                f"Shorten the branch names, or draw it with `direction: right`."
            )
        blocks = []
        for commit, tag in zip(commits, tag_w, strict=True):
            room = column_w - (tag + tag_point + pad if tag else 0.0)
            blocks.append(
                _block(text_of(commit), room, measurer, theme, "the label")
                if commit.label
                else None
            )
        line_h = theme.box.line_height * label_size
        least = 2 * ring + 2 * corner + slot
        heights = [max(block.height if block else 0.0, tag_h, line_h, 2 * ring) for block in blocks]
        top = (max(name_rows) + 1) * (name_h + pad) + slot
        along = []
        y = top
        for index, height in enumerate(heights):
            if index:
                y += max(least, (heights[index - 1] + height) / 2 + pad)
            along.append(y)
        bottom = along[-1] + heights[-1] / 2

        def at(t: float, c: float) -> Point:
            return (c, t)

        def gap_after(index: int) -> float:
            return along[index + 1] - along[index] if index + 1 < count else least

        fork_slot = [along[i] + gap_after(i) / 2 - slot / 2 for i in range(count)]
        merge_slot = [
            along[i] - gap_after(i - 1) / 2 + slot / 2 if i else 0.0 for i in range(count)
        ]

    marks = [at(along[c.index], cross[c.lane]) for c in commits]

    def line_role(lane: int) -> str:
        return STRONG_ROLE if branches[lane].role == "emphasis" else LINE_ROLE

    # -- lanes: a line between each two commits on a branch ---------------------
    previous: dict[int, _Commit] = {}
    lane_start: dict[int, float] = {}
    for commit in commits:
        here = along[commit.index]
        before = previous.get(commit.lane)
        if before is not None:
            a = along[before.index] + reach(before)
            b = here - reach(commit)
            if b > a:
                primitives.append(
                    Path(
                        line_role(commit.lane),
                        points=(at(a, cross[commit.lane]), at(b, cross[commit.lane])),
                    )
                )
        previous[commit.lane] = commit

    # -- forks and merges --------------------------------------------------------
    connectors: list[tuple[Point, ...]] = []

    def connect(source: _Commit, target: _Commit, turn: float, role: str) -> None:
        start_t = along[source.index] + reach(source)
        end_t = along[target.index] - reach(target)
        a, b = cross[source.lane], cross[target.lane]
        bend = min(corner, abs(b - a) / 2, turn - start_t, end_t - turn)
        points = _turned([at(start_t, a), at(turn, a), at(turn, b), at(end_t, b)], max(bend, 0.0))
        connectors.append(points)
        primitives.append(Path(role, points=points))

    for commit in commits:
        if commit.starts and commit.parent is not None:
            parent = commits[commit.parent]
            turn = fork_slot[parent.index]
            lane_start[commit.lane] = turn
            connect(parent, commit, turn, line_role(commit.lane))
        if commit.merged is not None:
            source = commits[commit.merged]
            connect(source, commit, merge_slot[commit.index], line_role(source.lane))
        if commit.starts and commit.parent is None:
            lane_start[commit.lane] = along[commit.index] - reach(commit)

    # -- names and their guides --------------------------------------------------
    for lane, branch in enumerate(branches):
        colour = style.colour_for(lane)
        role = EMPHASIS_ROLE if branch.role == "emphasis" else MARK_ROLE
        if down:
            name_top = name_rows[lane] * (name_h + pad)
            cx, cy = cross[lane], name_top + name_h / 2
            box = (cx - name_w[lane] / 2, name_top, name_w[lane], name_h)
            guide = (at(name_top + name_h, cross[lane]), at(lane_start[lane], cross[lane]))
        else:
            cx, cy = name_w[lane] / 2 + (max(name_w) - name_w[lane]), cross[lane]
            box = (max(name_w) - name_w[lane], cross[lane] - name_h / 2, name_w[lane], name_h)
            guide = (at(max(name_w), cross[lane]), at(lane_start[lane], cross[lane]))
        primitives.append(
            Rect(
                role,
                x=box[0],
                y=box[1],
                width=box[2],
                height=box[3],
                fill="solid" if colour else "",
                fill_colour=colour,
                fill_opacity=WASH if colour else 1.0,
            )
        )
        if math.dist(*guide) > pad:
            primitives.append(Path(GUIDE_ROLE, points=guide))
        extent = name_extents[lane]
        baseline = cy + (extent.ascent - extent.descent) / 2
        texts.append(
            TextLine(
                FURNITURE_ROLE,
                x=cx,
                y=baseline,
                spans=(TextSpan(text=branch.name, font=font, weight="bold"),),
                level="body",
                anchor="middle",
            )
        )
        boxes.append(
            (
                cx - extent.width / 2,
                baseline - extent.ascent,
                cx + extent.width / 2,
                baseline + extent.descent,
            )
        )

    # -- marks, labels and tags --------------------------------------------------
    for commit, (mx, my), block, tag in zip(commits, marks, blocks, tag_w, strict=True):
        colour = style.colour_for(commit.lane) or "currentColor"
        if commit.role == "emphasis":
            half = SQUARE * dot
            primitives.append(
                Polygon(
                    EMPHASIS_ROLE,
                    points=(
                        (mx - half, my - half),
                        (mx + half, my - half),
                        (mx + half, my + half),
                        (mx - half, my + half),
                    ),
                    fill="solid",
                    fill_colour=colour,
                )
            )
        else:
            if commit.kind != "commit":
                primitives.append(
                    Ellipse(
                        COPY_ROLE if commit.kind == "pick" else MARK_ROLE,
                        cx=mx,
                        cy=my,
                        rx=ring,
                        ry=ring,
                    )
                )
            inner = dot * {"commit": 1.0, "merge": 0.62, "pick": 0.8}[commit.kind]
            primitives.append(
                Ellipse(
                    MARK_ROLE, cx=mx, cy=my, rx=inner, ry=inner, fill="solid", fill_colour=colour
                )
            )
        if not down:
            if block is not None:
                label_top = my + ring + pad
                texts.extend(_lines(block, mx, label_top, "middle"))
                boxes.append(
                    (
                        mx - block.width / 2,
                        label_top,
                        mx + block.width / 2,
                        label_top + block.height,
                    )
                )
            if commit.tag:
                tip = my - reach(commit) - pad / 2
                base = tip - tag_point
                left, right = mx - tag / 2, mx + tag / 2
                primitives.append(
                    Polygon(
                        MARK_ROLE,
                        points=(
                            (left, base - tag_h),
                            (right, base - tag_h),
                            (right, base),
                            (mx + tag_point, base),
                            (mx, tip),
                            (mx - tag_point, base),
                            (left, base),
                        ),
                    )
                )
                texts.append(
                    _tag_line(
                        commit.tag, mx, base - tag_h / 2, "middle", font, measurer, label_size
                    )
                )
                extent = measurer.measure(commit.tag, font, label_size)
                boxes.append(
                    (
                        mx - extent.width / 2,
                        base - tag_h / 2 - extent.ascent / 2,
                        mx + extent.width / 2,
                        base - tag_h / 2 + extent.ascent / 2,
                    )
                )
        else:
            x = column
            if commit.tag:
                left = x + tag_point
                primitives.append(
                    Polygon(
                        MARK_ROLE,
                        points=(
                            (x, my),
                            (left, my - tag_h / 2),
                            (left + tag, my - tag_h / 2),
                            (left + tag, my + tag_h / 2),
                            (left, my + tag_h / 2),
                        ),
                    )
                )
                texts.append(
                    _tag_line(commit.tag, left + tag / 2, my, "middle", font, measurer, label_size)
                )
                extent = measurer.measure(commit.tag, font, label_size)
                boxes.append(
                    (
                        left + tag / 2 - extent.width / 2,
                        my - extent.ascent / 2,
                        left + tag / 2 + extent.width / 2,
                        my + extent.ascent / 2,
                    )
                )
                x = left + tag + pad
            if block is not None:
                # The first line's middle on the mark's centre.
                first = block.baseline(0)
                label_top = my - first + (block.ascent - block.descent) / 2
                texts.extend(_lines(block, x, label_top, "start"))
                boxes.append((x, label_top, x + block.width, label_top + block.height))

    scene = Scene(
        width=width,
        height=bottom,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return GitgraphDrawing(
        scene=scene,
        marks=tuple(marks),
        lanes=tuple(cross),
        texts=tuple(boxes),
        connectors=tuple(connectors),
    )


def _tag_line(
    text: str,
    x: float,
    middle: float,
    anchor: str,
    font: str,
    measurer: TextMeasurer,
    size: float,
) -> TextLine:
    """A tag's name, its capitals centred on `middle`."""
    extent = measurer.measure(text, font, size)
    return TextLine(
        FURNITURE_ROLE,
        x=x,
        y=middle + (extent.ascent - extent.descent) / 2,
        spans=(TextSpan(text=text, font=font),),
        level="body",
        anchor=anchor,
    )


# ---------------------------------------------------------------------------
# Text: the history as `git log --graph` draws it, oldest first
# ---------------------------------------------------------------------------

#: Each kind of commit's mark, per charset: commit, merge, cherry-pick, emphasis.
TEXT_MARKS: Final = {
    "unicode": {"commit": "●", "merge": "◉", "pick": "○", "emphasis": "■"},
    "ascii": {"commit": "*", "merge": "M", "pick": "o", "emphasis": "@"},
}

#: Cells between two lanes' columns.
TEXT_LANE: Final = 2


def gitgraph_text(document: Document, width: int, charset: str) -> str:
    """A `gitgraph` as plain text: lanes as columns, time down the page.

    A row per step, oldest first, its mark in its lane's column and its label in
    a column to the right of every lane: a branch's name in brackets at its first
    commit, the tag in parentheses, then the words, wrapped at spaces. A fork is
    drawn on its own row just after the parent, a merge on its own row just before
    the merge commit, with box-drawing corners where lines turn and join.

    Raises:
        FitError: the lanes leave a label no room for its longest word.
    """
    commits = history(document)
    branches = document.git_branches
    marks = TEXT_MARKS[charset]
    column = TEXT_LANE * (len(branches) - 1) + 1 + TEXT_LANE
    room = width - column

    def col(lane: int) -> int:
        return TEXT_LANE * lane

    def styled(lane: int) -> str:
        return "heavy" if branches[lane].role == "emphasis" else "light"

    # Allocate rows: an optional merge row, the commit's rows, an optional fork row.
    forks: dict[int, list[_Commit]] = {}
    for commit in commits:
        if commit.starts and commit.parent is not None:
            forks.setdefault(commit.parent, []).append(commit)
    rows: dict[int, int] = {}
    merge_rows: dict[int, int] = {}
    fork_rows: dict[int, int] = {}
    labels: dict[int, list[str]] = {}
    row = 0
    for commit in commits:
        pointer = f"/steps/{commit.index}/text"
        parts: list[str] = []
        if commit.starts:
            parts.append(f"[{label_lines(branches[commit.lane].name, charset, pointer)[0]}]")
        if commit.tag:
            parts.append(f"({' '.join(label_lines(commit.tag, charset, pointer))})")
        if commit.label:
            parts.append(" ".join(label_lines(commit.label, charset, pointer)))
        text = " ".join(parts)
        if room < 1 or any(cells(word) > room for word in text.split()):
            longest = max(text.split(), key=cells) if text.split() else ""
            raise too_wide(pointer, f"the word {longest!r}", column + cells(longest), width)
        labels[commit.index] = wrapped(text, room, pointer, width, column) if text else [""]
        if commit.merged is not None:
            merge_rows[commit.index] = row
            row += 1
        rows[commit.index] = row
        row += len(labels[commit.index])
        if commit.index in forks:
            fork_rows[commit.index] = row
            row += 1

    grid = Grid(charset)
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for commit in commits:
        here = rows[commit.index]
        first.setdefault(commit.lane, here)
        last[commit.lane] = here
    # A lane runs from its first commit to its last; a fork's lane from the fork row.
    for lane, start in first.items():
        if last[lane] > start:
            grid.vertical(col(lane), start, last[lane], styled(lane))

    def joint(
        source_lane: int,
        source_row: int,
        target_lane: int,
        target_row: int,
        at_row: int,
        style: str,
    ) -> None:
        grid.vertical(col(source_lane), source_row, at_row, style)
        grid.horizontal(at_row, col(source_lane), col(target_lane), style)
        grid.vertical(col(target_lane), at_row, target_row, style)

    for commit in commits:
        if commit.starts and commit.parent is not None:
            parent = commits[commit.parent]
            joint(
                parent.lane,
                rows[parent.index],
                commit.lane,
                rows[commit.index],
                fork_rows[parent.index],
                styled(commit.lane),
            )
        if commit.merged is not None:
            source = commits[commit.merged]
            joint(
                source.lane,
                rows[source.index],
                commit.lane,
                rows[commit.index],
                merge_rows[commit.index],
                styled(source.lane),
            )

    for commit in commits:
        here = rows[commit.index]
        mark = marks["emphasis"] if commit.role == "emphasis" else marks[commit.kind]
        grid.text(here, col(commit.lane), mark)
        for offset, line in enumerate(labels[commit.index]):
            grid.text(here + offset, column, line)

    return finished(grid.lines() + text_caption_lines(document.caption, width, charset))


__all__ = ["GitgraphDrawing", "gitgraph_drawing", "gitgraph_scene", "gitgraph_text", "history"]
