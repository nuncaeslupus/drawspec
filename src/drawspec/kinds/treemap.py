"""The `treemap` kind: the parts of one known total, each by its area.

A treemap answers *what dominates, and by how much* for one total split into a
few parts — a bundle's size, a disk that filled up, where a team's hours went. It
states a small set of proportions the author already knows; it is not a way to
explore data, and its budget (ten parts, one level of groups) keeps it that way.

**The layout** takes the parts largest first — written order only breaks ties,
and `note` parts, the remainder, go last — and cuts the block in two across its
longer side, then each half again, the cuts keeping that order. With at most ten
parts every such tree can be tried, so the one chosen is the one in which the
most labels fit, then whose cells are nearest a label's shape — the measure the
squarified layout (Bruls, Huizing and van Wijk) uses for a row, without its
greedy rows' last thin strip. The block is the canvas width wide and a share of
it tall, a little taller if a label needs it; or the top-level `height`.

**Areas stay in proportion after the gaps.** The gap between two cells is taken
from the cells, not added between them, and a uniform inset takes a larger share
of a small cell than of a large one; so the weights the layout is run with are
corrected, a few passes, until every drawn cell's share of the drawn total is its
amount's share of the whole. A group's caption band is paid for the same way.

**Every part is labelled inside itself**, its words top-left and its amount under
them — or the document is refused. A sliver with its label crammed in, or moved
to a legend, is the failure this kind exists to avoid: the `FitError` names the
part and says which parts to merge into one `note` part.

**Groups** are one level: a captioned frame in the `group` role around the parts
that name it, its name and total in the caption band, and its parts filled with
the theme's mark fills, one per group in the order written — as a matrix's cell
groups are. Parts are otherwise told apart by their borders and words: `step`
solid, `emphasis` heavier with bold words, `note` light and dashed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import FitError
from drawspec.scene import Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import Document, TreemapPart
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The block's height as a share of its width, when the author gives no `height`.
#: Wider than tall, as a page is; near enough to square that the cuts do not all
#: run one way.
ASPECT: Final = 0.6

#: The heights tried, as shares of the width, when a label does not fit at the
#: first: a little taller each time, up to a block still wider than tall. Past
#: the last, the smallest parts are refused rather than drawn as slivers.
HEIGHTS: Final = (ASPECT, 0.65, 0.7, 0.75)

#: The shape a cell's label reads best in, as width over height: a few short
#: lines, wider than tall. Each cut is chosen to keep every cell near it.
IDEAL: Final = 1.5

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
GAP: Final = 4.0
"""Between two cells, and between two top-level rectangles."""
INSET: Final = 6.0
"""From a cell's border to its words, on every side."""
FRAME_PAD: Final = 5.0
"""From a group's frame to the parts inside it, and to its caption."""
VALUE_GAP: Final = 2.0
"""Between a part's words and its amount under them."""

#: How many correction passes the layout takes, at most, and the share error at
#: which it stops early. A pass costs one placement per container.
PASSES: Final = 60
TOLERANCE: Final = 1e-5

#: The role a cell's and a caption's words are drawn in: furniture, not boxes.
TEXT_ROLE: Final = "step"

#: The role a group's frame is drawn in.
GROUP_ROLE: Final = "group"

#: A `code` span, kept whole when a text is set in bold, and a run of other words.
_CODE: Final = re.compile(r"(`[^`]+`)")
_WORD: Final = re.compile(r"(\S+)")

type _Rect = tuple[float, float, float, float]
"""Left, top, width, height."""

type _Sizes = tuple[tuple[float, float], ...]
"""A label's outer sizes — width and height, its inset included — one per line count."""

type _Tree = int | tuple[int, int, int, _Tree, _Tree]
"""An entry's index, or a cut: the range it splits, where, and the two sides."""


@dataclass(frozen=True)
class TreemapDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    cells: dict[int, _Rect] = field(default_factory=dict)
    """Each part's drawn rectangle, by its index among the parts as written."""

    labels: dict[int, _Rect] = field(default_factory=dict)
    """The bounds of each part's words and amount, by the same index."""

    frames: dict[str, _Rect] = field(default_factory=dict)
    """Each group's frame, by id."""

    captions: dict[str, _Rect] = field(default_factory=dict)
    """The bounds of each group's caption, by id."""

    order: tuple[int, ...] = ()
    """The parts' indices in the order they were laid out."""


@dataclass
class _Container:
    """A rectangle to fill: the canvas, or one group's frame, and what goes in it."""

    entries: list[_Entry]
    weights: list[float]
    tree: _Tree | None = None
    """How the rectangle is cut, chosen once on the first pass."""

    sizes: list[_Sizes] = field(default_factory=list)
    """Per entry, the outer sizes its label can take; empty for a group."""


@dataclass
class _Entry:
    """One thing laid out in a container: a part, or a group holding parts."""

    value: float
    first: int
    """The earliest written index in it, the tie-breaker."""

    note: bool
    part: int | None = None
    group: str = ""
    inner: _Container | None = None


def treemap_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a treemap."""
    return treemap_drawing(document, theme, measurer).scene


def treemap_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> TreemapDrawing:
    """Draw the treemap at the first height, shortest first, at which every label fits.

    The heights run from `ASPECT` of the width to the last of `HEIGHTS`; a top-level `height`
    is the one height tried.

    Raises:
        FitError: at the tallest height tried, a part's words and amount do not fit
            inside its rectangle, or a group's name does not fit across its frame.
    """
    width = theme.canvas.width
    heights = [document.height] if document.height else [width * share for share in HEIGHTS]
    failure: FitError | None = None
    for height in heights:
        try:
            return _drawing(document, theme, measurer, height)
        except FitError as error:
            failure = error
    assert failure is not None
    raise failure


def _drawing(
    document: Document, theme: Theme, measurer: TextMeasurer, height: float
) -> TreemapDrawing:
    """Lay the parts out by area, correct the areas for the gaps, and label each part.

    Raises:
        FitError: a part's words and amount do not fit inside its rectangle, or a
            group's name does not fit across its frame.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    parts = document.treemap_parts
    gap = GAP * unit
    inset = INSET * unit
    frame_pad = FRAME_PAD * unit
    group_index = {group.id: index for index, group in enumerate(document.treemap_groups)}
    group_text = {group.id: group.text for group in document.treemap_groups}
    total = sum(part.amount for part in parts)

    root = _containers(parts, group_index)
    sizes = [_sizes(part, inset, document, theme, measurer) for part in parts]
    _attach(root, sizes)
    captions_text = {
        group: (
            bold(group_text[group]),
            format_value(_sum(parts, group), document.unit) if document.values else None,
        )
        for group in group_index
    }

    cells: dict[int, _Rect] = {}
    frames: dict[str, _Rect] = {}
    captions: dict[str, _Label | None] = {}
    for _ in range(PASSES):
        cells, frames, captions = _layout(
            root, (0.0, 0.0, width, height), gap, frame_pad, captions_text, theme, measurer
        )
        drawn = sum(_area(cells[index]) for index in range(len(parts)))
        if drawn <= 0:
            break
        error = max(
            abs(_area(cells[index]) / drawn - part.amount / total) / (part.amount / total)
            for index, part in enumerate(parts)
        )
        if error < TOLERANCE:
            break
        _correct(root, cells, parts, drawn, total)

    # A group's caption first: a name wider than its frame is the group's problem.
    for group, caption in captions.items():
        if caption is None:
            raise FitError(
                f"the group {group_text[group][:40]!r} (/groups/{group_index[group]}) has a "
                f"word wider than its frame, {frames[group][2]:.0f} wide. Shorten its name, "
                f"or give the diagram more width."
            )

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    labels: dict[int, _Rect] = {}
    caption_bounds: dict[str, _Rect] = {}
    for group, (left, top, frame_width, frame_height) in frames.items():
        primitives.append(
            Polygon(GROUP_ROLE, points=_corners(left, top, frame_width, frame_height))
        )
        caption = captions[group]
        assert caption is not None
        x, y = left + frame_pad, top + frame_pad
        texts.extend(caption.lines(x, y))
        caption_bounds[group] = (x, y, caption.width, caption.height)

    failures: list[int] = []
    blocks: dict[int, _Label] = {}
    for index, part in enumerate(parts):
        fitted = _fitted(part, cells[index], inset, document, theme, measurer)
        if fitted is None:
            failures.append(index)
        else:
            blocks[index] = fitted
    if failures:
        raise FitError(_sliver_message(failures, parts, cells, document))

    # Ordinary parts first, then the remainder, then the emphasis on top.
    rank = {"step": 0, "note": 1, "emphasis": 2}
    for index in sorted(range(len(parts)), key=lambda k: rank.get(parts[k].role, 0)):
        part = parts[index]
        left, top, cell_width, cell_height = cells[index]
        fill = colour = ""
        if part.group:
            fill = theme.mark.fill_for(group_index[part.group])
            colour = theme.mark.colour_for(group_index[part.group])
        primitives.append(
            Polygon(
                part.role,
                points=_corners(left, top, cell_width, cell_height),
                fill=fill,
                fill_colour=colour,
            )
        )
        label = blocks[index]
        x, y = left + inset, top + inset
        texts.extend(label.lines(x, y))
        labels[index] = (x, y, label.width, label.height)

    scene = Scene(
        width=width,
        height=height,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return TreemapDrawing(
        scene=scene,
        cells=cells,
        labels=labels,
        frames=frames,
        captions=caption_bounds,
        order=tuple(_order(root)),
    )


def place(tree: _Tree, weights: list[float], rect: _Rect) -> dict[int, _Rect]:
    """Each entry's rectangle: every cut across the longer side, in proportion to weight."""
    prefix = [0.0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)
    found: dict[int, _Rect] = {}
    _cut(tree, prefix, rect, found)
    return found


def _cut(tree: _Tree, prefix: list[float], rect: _Rect, found: dict[int, _Rect]) -> None:
    if isinstance(tree, int):
        found[tree] = rect
        return
    low, cut, high, left_tree, right_tree = tree
    total = prefix[high] - prefix[low]
    share = (prefix[cut] - prefix[low]) / total if total > 0 else 0.5
    left, top, width, height = rect
    if width >= height:
        first = width * share
        _cut(left_tree, prefix, (left, top, first, height), found)
        _cut(right_tree, prefix, (left + first, top, width - first, height), found)
    else:
        first = height * share
        _cut(left_tree, prefix, (left, top, width, first), found)
        _cut(right_tree, prefix, (left, top + first, width, height - first), found)


def best_partition(
    weights: list[float],
    rect: _Rect,
    sizes: list[_Sizes] | None = None,
    gap: float = 0.0,
) -> _Tree:
    """The cuts in which the most labels fit, the cells nearest the shape a label wants.

    Every way to cut the entries in two across the longer side, keeping their
    order, then each half again down to one entry, is considered. `sizes` gives,
    per entry, the outer sizes its label can take — one per number of lines — or
    nothing for a group, whose parts are placed later. A layout is scored first
    by how many labels would not fit their cell less the gap, then as the
    squarified layout scores a row — the worst cell's distance from the ideal
    shape — then by the sum over all cells.

    Each half's best is found in its own rectangle, so the search is over cuts,
    not whole trees: ten entries cost thousands of cells, not tens of thousands.
    The first best found is kept, so the choice is the same on every run.
    """
    prefix = [0.0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)
    needs = sizes or [()] * len(weights)
    return _best(0, len(weights), rect, prefix, needs, gap)[1]


type _Score = tuple[int, float, float]


def _best(
    low: int, high: int, rect: _Rect, prefix: list[float], needs: list[_Sizes], gap: float
) -> tuple[_Score, _Tree]:
    left, top, width, height = rect
    if high - low == 1:
        inner_width, inner_height = width - gap, height - gap
        shape = _misshape((0.0, 0.0, inner_width, inner_height))
        options = needs[low]
        misfit = bool(options) and not any(
            w <= inner_width and h <= inner_height for w, h in options
        )
        return (int(misfit), shape, shape), low
    total = prefix[high] - prefix[low]
    found: tuple[_Score, _Tree] | None = None
    for cut in range(low + 1, high):
        share = (prefix[cut] - prefix[low]) / total if total > 0 else 0.5
        if width >= height:
            first = width * share
            one = (left, top, first, height)
            two = (left + first, top, width - first, height)
        else:
            first = height * share
            one = (left, top, width, first)
            two = (left, top + first, width, height - first)
        (m1, w1, s1), t1 = _best(low, cut, one, prefix, needs, gap)
        (m2, w2, s2), t2 = _best(cut, high, two, prefix, needs, gap)
        score = (m1 + m2, max(w1, w2), s1 + s2)
        if found is None or score < found[0]:
            found = (score, (low, cut, high, t1, t2))
    assert found is not None
    return found


def _misshape(cell: _Rect) -> float:
    """How far a cell is from the ideal label shape, as a ratio: 1 is ideal."""
    _, _, width, height = cell
    if width <= 0 or height <= 0:
        return math.inf
    ratio = width / height / IDEAL
    return max(ratio, 1 / ratio)


def format_value(value: float, unit: str) -> str:
    """An amount as written: no trailing zeros, the unit after a space."""
    text = f"{value:.10g}"
    if not unit:
        return text
    return f"{text}{unit}" if unit == "%" else f"{text} {unit}"


def bold(text: str) -> str:
    """`text` in bold, word by word, its `code` spans left as code.

    A span is either code or bold, never both, so wrapping the whole text in one
    pair of asterisks would print the backticks of a path like `/var/log`.
    """
    pieces = _CODE.split(text.replace("**", ""))
    return "".join(
        piece if piece.startswith("`") else _WORD.sub(r"**\1**", piece) for piece in pieces
    )


def _containers(parts: tuple[TreemapPart, ...], group_index: dict[str, int]) -> _Container:
    """The canvas's entries — groups and ungrouped parts — and each group's parts, in order.

    Largest first, `note` last, written order breaking ties: the order the cuts
    keep, fixed once so the correction passes cannot reorder them.
    """
    inner: dict[str, list[_Entry]] = {group: [] for group in group_index}
    top: list[_Entry] = []
    for index, part in enumerate(parts):
        entry = _Entry(value=part.amount, first=index, note=part.role == "note", part=index)
        (inner[part.group] if part.group else top).append(entry)
    for group, entries in inner.items():
        if not entries:
            continue
        ordered = _sorted(entries)
        container = _Container(ordered, [entry.value for entry in ordered])
        top.append(
            _Entry(
                value=sum(entry.value for entry in entries),
                first=min(entry.first for entry in entries),
                note=all(entry.note for entry in entries),
                group=group,
                inner=container,
            )
        )
    ordered = _sorted(top)
    return _Container(ordered, [entry.value for entry in ordered])


def _attach(container: _Container, sizes: list[_Sizes]) -> None:
    """Give each container the label sizes of its entries, in its own order."""
    container.sizes = [
        sizes[entry.part] if entry.part is not None else () for entry in container.entries
    ]
    for entry in container.entries:
        if entry.inner is not None:
            _attach(entry.inner, sizes)


def _sizes(
    part: TreemapPart, inset: float, document: Document, theme: Theme, measurer: TextMeasurer
) -> _Sizes:
    """Every size the part's label can take, widest first: one line, then two, and so on.

    Each is the block the wrap makes at just under the last one's width, with the
    amount under it and the inset round it — what the cutting search checks a cell
    against before any cell is final.
    """
    text = bold(part.text) if part.role == "emphasis" else part.text
    value = format_value(part.amount, document.unit) if document.values else None
    found: list[tuple[float, float]] = []
    limit = 1e6
    while limit > 0:
        label = _stacked(text, value, limit, theme, measurer)
        if label is None:
            break
        found.append((label.width + 2 * inset, label.height + 2 * inset))
        limit = label.words.width * 0.999
        if value is not None and limit < label.value.width:  # type: ignore[union-attr]
            break
    return tuple(found)


def _sorted(entries: list[_Entry]) -> list[_Entry]:
    return sorted(entries, key=lambda entry: (entry.note, -entry.value, entry.first))


def _order(container: _Container) -> list[int]:
    found: list[int] = []
    for entry in container.entries:
        if entry.inner is not None:
            found.extend(_order(entry.inner))
        elif entry.part is not None:
            found.append(entry.part)
    return found


def _layout(
    root: _Container,
    rect: _Rect,
    gap: float,
    frame_pad: float,
    captions_text: dict[str, tuple[str, str | None]],
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[dict[int, _Rect], dict[str, _Rect], dict[str, _Label | None]]:
    """One layout with the current weights: every cell, every frame, every caption."""
    cells: dict[int, _Rect] = {}
    frames: dict[str, _Rect] = {}
    captions: dict[str, _Label | None] = {}
    for entry, placed in zip(root.entries, _tiled(root, rect, gap), strict=True):
        if entry.inner is None:
            assert entry.part is not None
            cells[entry.part] = placed
            continue
        frames[entry.group] = placed
        left, top, width, height = placed
        name, total = captions_text[entry.group]
        caption = _stacked(name, total, width - 2 * frame_pad, theme, measurer)
        captions[entry.group] = caption
        band = frame_pad + (caption.height if caption is not None else 0.0) + frame_pad
        content = (left + frame_pad, top + band, width - 2 * frame_pad, height - band - frame_pad)
        inner = entry.inner
        for child, child_rect in zip(inner.entries, _tiled(inner, content, gap), strict=True):
            assert child.part is not None
            cells[child.part] = child_rect
    return cells, frames, captions


def _tiled(container: _Container, rect: _Rect, gap: float) -> list[_Rect]:
    """The container's rectangles, each inset by half a gap, flush with `rect`'s edges.

    The layout is run over `rect` grown by half a gap on every side, so after the
    inset the outermost cells meet its edges exactly and two neighbours are a
    whole gap apart. The tree is chosen on the first pass, with the values as the
    weights, and kept: the correction passes only move the cuts.
    """
    left, top, width, height = rect
    half = gap / 2
    grown = (left - half, top - half, max(width, 0.0) + gap, max(height, 0.0) + gap)
    if container.tree is None:
        container.tree = best_partition(container.weights, grown, container.sizes, gap)
    placed = place(container.tree, container.weights, grown)
    return [
        (x + half, y + half, max(w - gap, 0.0), max(h - gap, 0.0))
        for x, y, w, h in (placed[index] for index in range(len(container.weights)))
    ]


def _correct(
    root: _Container,
    cells: dict[int, _Rect],
    parts: tuple[TreemapPart, ...],
    drawn: float,
    total: float,
) -> None:
    """Scale each weight by how far its drawn share is from its amount's share."""
    floor = drawn * 1e-9
    for position, entry in enumerate(root.entries):
        members = _members(entry)
        actual = max(sum(_area(cells[index]) for index in members), floor) / drawn
        target = sum(parts[index].amount for index in members) / total
        root.weights[position] *= target / actual
        if entry.inner is None:
            continue
        inner_drawn = max(sum(_area(cells[index]) for index in members), floor)
        inner_total = sum(parts[index].amount for index in members)
        for child_position, child in enumerate(entry.inner.entries):
            assert child.part is not None
            share = max(_area(cells[child.part]), floor) / inner_drawn
            entry.inner.weights[child_position] *= (parts[child.part].amount / inner_total) / share


def _members(entry: _Entry) -> list[int]:
    if entry.inner is None:
        assert entry.part is not None
        return [entry.part]
    return [child.part for child in entry.inner.entries if child.part is not None]


def _area(rect: _Rect) -> float:
    return rect[2] * rect[3]


def _sum(parts: tuple[TreemapPart, ...], group: str) -> float:
    return sum(part.amount for part in parts if part.group == group)


@dataclass(frozen=True)
class _Label:
    """Words over an amount, each wrapped to one width: a part's label or a group's caption."""

    words: TextBlock
    value: TextBlock | None
    gap: float

    @property
    def width(self) -> float:
        return max(self.words.width, self.value.width if self.value is not None else 0.0)

    @property
    def height(self) -> float:
        if self.value is None:
            return self.words.height
        return self.words.height + self.gap + self.value.height

    def lines(self, x: float, top: float) -> list[TextLine]:
        """The words from `top` down, then the amount under them, all at the body size.

        One size, as every word inside a shape is set in every kind: the amount is
        told apart by being on its own line, not by being smaller.
        """
        found = _lines(self.words, x, top, "body")
        if self.value is not None:
            found.extend(_lines(self.value, x, top + self.words.height + self.gap, "body"))
        return found


def _stacked(
    words: str, value: str | None, width: float, theme: Theme, measurer: TextMeasurer
) -> _Label | None:
    """`words` wrapped to `width` over `value` on one line, or `None` if either is too wide.

    The amount is never broken: a number split from its unit reads as two things.
    """
    if width <= 0:
        return None
    try:
        block = wrap(words, width, measurer, theme=theme, level="body", lead=False)
    except FitError:
        return None
    number: TextBlock | None = None
    if value is not None:
        number = wrap(value, 1e6, measurer, theme=theme, level="body")
        if number.width > width + 1e-6:
            return None
    return _Label(block, number, VALUE_GAP * theme.scale["body"] / 11)


def _fitted(
    part: TreemapPart,
    cell: _Rect,
    inset: float,
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
) -> _Label | None:
    """The part's words and amount, wrapped to its cell — or `None` if they do not fit."""
    _, _, width, height = cell
    text = bold(part.text) if part.role == "emphasis" else part.text
    value = format_value(part.amount, document.unit) if document.values else None
    label = _stacked(text, value, width - 2 * inset, theme, measurer)
    if label is None or label.height > height - 2 * inset + 1e-6:
        return None
    return label


def _sliver_message(
    failures: list[int],
    parts: tuple[TreemapPart, ...],
    cells: dict[int, _Rect],
    document: Document,
) -> str:
    """Name the parts too small for their words, and the merge that would fix it."""
    named = [
        f"{parts[index].text[:40]!r} (/parts/{index}, "
        f"{format_value(parts[index].amount, document.unit)}, "
        f"{cells[index][2]:.0f} by {cells[index][3]:.0f})"
        for index in failures
    ]
    threshold = max(parts[index].amount for index in failures)
    subject = f"the part {named[0]} is" if len(named) == 1 else f"the parts {', '.join(named)} are"
    return (
        f"{subject} too small for {'its' if len(named) == 1 else 'their'} words and amount: a "
        f"treemap labels every part inside itself, never beside it. Merge the parts of "
        f"{format_value(threshold, document.unit)} or less into one `note` part "
        f"(`Everything else`) and name them in the caption, shorten the words, or give the "
        f"diagram more `width` or `height`."
    )


def _corners(
    left: float, top: float, width: float, height: float
) -> tuple[tuple[float, float], ...]:
    right, bottom = left + width, top + height
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def _lines(block: TextBlock, x: float, top: float, level: str) -> list[TextLine]:
    """A wrapped block as one start-anchored `TextLine` per line, from `top` down."""
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
                    TEXT_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor="start",
                )
            )
    return found


__all__ = [
    "TreemapDrawing",
    "best_partition",
    "bold",
    "format_value",
    "place",
    "treemap_drawing",
    "treemap_scene",
]
