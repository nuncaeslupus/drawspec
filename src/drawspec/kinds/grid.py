"""Grid kinds: `stack`, `timeline`, `columns`, `matrix`. Positions come from counting.

No layout engine is involved and no routing problem exists — which is why this is
the family where "peers are the same size" can be an exact equality rather than a
normalisation that happens to work out. The gate is
`same_rank_size_variance == 0`, and in each kind below it holds by construction:

* `stack` — every layer is the full width and one common height.
* `columns` — the available width less the gutters, divided equally.
* `timeline` — one step, computed once, between every pair of ticks.
* `matrix` — equal columns; a row is as deep as its deepest cell needs.

Spacing is derived from the theme's box padding rather than invented here. A kind
decides *which* gap applies where; how big a gap is remains the theme's business,
so a consumer retunes their diagrams by editing a theme file.
"""

from __future__ import annotations

from itertools import pairwise

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import box_primitives, text_runs
from drawspec.scene import Path, Polygon, Primitive, Scene
from drawspec.schema import Cell, Document, Item
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The role the timeline's own axis and ticks are drawn with. An axis is a plain
#: connector — no head, no direction — which is exactly what `link` means, so it
#: is named rather than given geometry of its own.
AXIS_ROLE = "link"

#: How long a timeline's tick marks are, as a fraction of the theme's head
#: length. Ticks read as marks on a line rather than as arrows.
TICK_FRACTION = 1.0


def grid_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a grid-kind document to a `Scene`.

    Raises:
        DrawspecError: `document.kind` is not a grid kind.
        FitError: the content cannot fit the width at this type scale.
    """
    if document.kind == "stack":
        return _stack(document, theme, measurer)
    if document.kind == "columns":
        return _columns(document, theme, measurer)
    if document.kind == "timeline":
        return _timeline(document, theme, measurer)
    if document.kind == "matrix":
        return _matrix(document, theme, measurer)
    raise DrawspecError(f"{document.kind!r} is not a grid kind")


def _canvas_width(document: Document, theme: Theme) -> float:
    """The width to draw to. The document may override the theme; nothing else may."""
    return document.width if document.width else theme.canvas.width


def _scene(document: Document, primitives: list[Primitive], width: float, height: float) -> Scene:
    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _sized(
    items: tuple[Item, ...], theme: Theme, measurer: TextMeasurer, width: float
) -> list[Box]:
    """One box per item, each wrapped to `width`."""
    return [
        size_box(
            item.text,
            theme=theme,
            measurer=measurer,
            role=item.role,
            level="body",
            max_width=width,
        )
        for item in items
    ]


# ---------------------------------------------------------------------------
# stack
# ---------------------------------------------------------------------------


def _stack(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Layers, full width, all one height, top to bottom.

    Equal height is the point: a stack whose layers differ in height reads as a
    ranking of importance, which is not what the author said.
    """
    width = _canvas_width(document, theme)
    gap = theme.box.padding.top
    boxes = normalise(_sized(document.items, theme, measurer, width))

    primitives: list[Primitive] = []
    y = 0.0
    for box in boxes:
        # Full width, not the width its own text happened to need.
        placed = box.resized(width=width).moved_to(0.0, y)
        primitives.extend(box_primitives(placed, theme, measurer))
        y += placed.height + gap

    return _scene(document, primitives, width, max(y - gap, 0.0))


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------


def _columns(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Side by side, equal width, equal height, left to right."""
    width = _canvas_width(document, theme)
    gutter = theme.box.padding.horizontal
    count = len(document.items)
    column = (width - gutter * (count - 1)) / count
    if column <= theme.box.padding.horizontal:
        raise FitError(
            f"{count} columns do not fit a width of {width:.0f}: each would be "
            f"{column:.1f} wide, which is narrower than the theme's own padding. "
            f"Use fewer columns, a wider canvas, or a different kind."
        )

    boxes = normalise(_sized(document.items, theme, measurer, column))
    primitives: list[Primitive] = []
    for index, box in enumerate(boxes):
        placed = box.resized(width=column).moved_to((column + gutter) * index, 0.0)
        primitives.extend(box_primitives(placed, theme, measurer))

    height = max((box.height for box in boxes), default=0.0)
    return _scene(document, primitives, width, height)


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


def _timeline(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Labels above an axis, one tick each.

    Evenly spaced by default, and the step is computed once from the width and
    the label width — never accumulated per item, which is how a timeline ends up
    with a slightly wider gap at one end.

    **Or spaced by when things happened.** If every entry carries an `at`, the
    ticks land in proportion to those values, and the gaps then say something:
    the reader can see that two events were close together and a third was much
    later. It is all or nothing — a timeline with some entries placed and some
    not would have a reader measuring one gap and counting the next.

    Sizes stay normalised either way, because peers being the same size is this
    family's rule and irregular *spacing* is not irregular *labels*. When two of
    those equal labels will not fit the gap their values ask for, that is a
    `FitError` naming the pair rather than an overlap.
    """
    width = _canvas_width(document, theme)
    count = len(document.items)
    gutter = theme.box.padding.horizontal
    shares = _shares(document.items, count)
    even = (width - gutter * (count - 1)) / count if count > 1 else width
    # Placed entries get labels sized to their *tightest* pair rather than to an
    # even share: the closest two are what decides how wide a label may be, and
    # sizing to the average would guarantee they overlap.
    label_width = even if shares is None else min(even, _tightest(shares) * width - gutter / 2)
    if label_width <= theme.box.padding.horizontal:
        raise FitError(
            f"{count} timeline entries do not fit a width of {width:.0f}: each label "
            f"would be {label_width:.1f} wide, narrower than the theme's own padding. "
            f"Use fewer entries, a wider canvas, or a vertical kind such as `stack`."
        )

    boxes = normalise(_sized(document.items, theme, measurer, label_width))
    band = max((box.height for box in boxes), default=0.0)
    tick = theme.edge.head_length * TICK_FRACTION
    axis_y = band + theme.box.padding.top

    centres = _centres(shares, count, width, label_width)

    primitives: list[Primitive] = [
        Path(AXIS_ROLE, points=((0.0, axis_y), (width, axis_y))),
    ]
    for index, box in enumerate(boxes):
        centre = centres[index]
        # From the label's own bottom edge, not from a mark floating beside the
        # axis: a tick that starts in the gap says a moment happened *somewhere*
        # along here, and the reader is left to pair each label with the nearest
        # mark by eye. Touching both, it says which moment is which.
        primitives.append(Path(AXIS_ROLE, points=((centre, band), (centre, axis_y + tick / 2))))
        placed = box.resized(width=label_width).moved_to(centre - label_width / 2, 0.0)
        primitives.extend(box_primitives(placed, theme, measurer))

    return _scene(document, primitives, width, axis_y + tick / 2)


def _shares(items: tuple[Item, ...], count: int) -> list[float] | None:
    """Each entry's place along the line, from 0 to 1 — or `None` for even spacing.

    All or nothing: a timeline with some entries placed and some not would have a
    reader measuring one gap and counting the next.

    Raises:
        FitError: every entry is at the same point, so the spacing has nothing to
            say.
    """
    values = [item.at for item in items]
    if count < 2 or any(value is None for value in values):
        return None
    placed = [value for value in values if value is not None]
    low, high = min(placed), max(placed)
    if high == low:
        raise FitError(
            "every entry on this timeline is placed at the same point, so there is "
            "nothing for the spacing to say. Give them different values, or drop "
            "`at` and let them space evenly."
        )
    return [(value - low) / (high - low) for value in placed]


def _tightest(shares: list[float]) -> float:
    """The widest a label may be, as a share of the width, given the closest pair.

    A label of width `w` centred on each end leaves `width - w` for the spread, so
    the closest pair is `gap * (width - w)` apart and must be at least `w` wide:
    `w <= gap * width / (1 + gap)`. The caller then takes half a gutter off
    that, so the closest two labels have daylight between them rather than a
    shared edge. Half, not a whole one: two labels on a timeline need less
    separation than two columns do, because each has a tick saying which is
    which, and a full gutter costs enough width to break a two-word label.
    """
    gap = min(later - earlier for earlier, later in pairwise(sorted(shares)))
    return gap / (1 + gap) if gap > 0 else 0.0


def _centres(
    shares: list[float] | None, count: int, width: float, label_width: float
) -> list[float]:
    """Where each tick sits: evenly, or in proportion to the entries' own values."""
    half = label_width / 2
    first, last = half, width - half
    if count < 2:
        return [width / 2]
    if shares is None:
        step = (last - first) / (count - 1)
        return [first + step * index for index in range(count)]
    return [first + share * (last - first) for share in shares]


__all__ = ["AXIS_ROLE", "TICK_FRACTION", "grid_scene"]


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------


def _matrix(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Rows against columns, with cells that may span either way.

    The one kind whose *content* is a comparison rather than a sequence, which
    is what the fills are for: a cell says which group it belongs to by how it is
    filled, and the theme's `[mark] fills` vocabulary is the same one the chart
    uses. Colour is not an option here and never was — these diagrams are printed
    in black and white, and two cells that differ only in hue are two cells a
    reader cannot tell apart.

    Columns are equal. A row is as deep as the deepest cell that ends in it, and
    a cell spanning several rows is charged to the last one it covers — so a tall
    cell makes room where it finishes rather than pushing every row it passes.
    """
    cells = document.cells
    if not cells:
        raise DrawspecError("a matrix needs at least one cell")
    fills = _group_fills(cells, theme)

    _check_cells(cells)
    across = max(max(cell.column + cell.across for cell in cells), len(document.columns))
    down = max(max(cell.row + cell.down for cell in cells), len(document.rows))

    width = _canvas_width(document, theme)
    gap = theme.box.padding.horizontal
    heading_width = _heading_width(document, theme, measurer, width) if document.rows else 0.0
    column_width = (width - heading_width) / across

    boxes = {
        (cell.column, cell.row): size_box(
            cell.text,
            theme=theme,
            measurer=measurer,
            role=cell.role,
            level="body",
            max_width=column_width * cell.across,
            shape="rect",
        )
        for cell in cells
    }
    heights = _row_heights(cells, boxes, down)
    heading_height = (
        size_box(
            " ".join(document.columns) or "x",
            theme=theme,
            measurer=measurer,
            level="body",
            max_width=width,
            shape="rect",
        ).height
        if document.columns
        else 0.0
    )

    tops = [heading_height]
    for height in heights:
        tops.append(tops[-1] + height)

    primitives: list[Primitive] = []
    for index, heading in enumerate(document.columns):
        band = Box(
            role="step",
            shape="rect",
            level="body",
            block=size_box(
                heading, theme=theme, measurer=measurer, max_width=column_width, shape="rect"
            ).block,
            width=column_width,
            height=heading_height,
            x=heading_width + index * column_width,
            y=0.0,
            padding=theme.box.padding,
        )
        primitives.extend(text_runs(band, theme, measurer))
    for index, heading in enumerate(document.rows):
        band = Box(
            role="step",
            shape="rect",
            level="body",
            block=size_box(
                heading, theme=theme, measurer=measurer, max_width=heading_width, shape="rect"
            ).block,
            width=heading_width,
            height=heights[index],
            x=0.0,
            y=tops[index],
            padding=theme.box.padding,
        )
        primitives.extend(text_runs(band, theme, measurer))

    for cell in cells:
        left = heading_width + cell.column * column_width
        cell_width = column_width * cell.across
        top = tops[cell.row]
        cell_height = tops[cell.row + cell.down] - top
        right, bottom = left + cell_width, top + cell_height
        # Polygons rather than rects: adjacent cells share an edge, and the
        # theme's corner radius would leave a gap at every junction and a row of
        # lozenges where a table should be. The radius belongs to boxes.
        primitives.append(
            Polygon(
                cell.role,
                points=((left, top), (right, top), (right, bottom), (left, bottom)),
                fill=fills[cell.group],
            )
        )
        placed = (
            boxes[(cell.column, cell.row)]
            .resized(width=cell_width, height=cell_height)
            .moved_to(left, top)
        )
        primitives.extend(text_runs(placed, theme, measurer))

    return _scene(document, primitives, width, tops[-1] + gap * 0)


def _group_fills(cells: tuple[Cell, ...], theme: Theme) -> dict[str, str]:
    """One fill per group, from the theme's sequence, in order of first mention.

    The author names the *group*, never the fill. `fill` is in the schema's
    rejection table for exactly this reason — appearance is a property of the
    role, not of the element — and a matrix does not get an exemption just
    because its whole content is a comparison. What it gets is a way to say
    which cells are the same kind of cell, and the theme turns that into
    something a black-and-white printer can keep apart.
    """
    named: list[str] = []
    for cell in cells:
        if cell.group and cell.group not in named:
            named.append(cell.group)
    fills = {"": ""}
    for index, group in enumerate(named):
        fills[group] = theme.mark.fill_for(index)
    return fills


def _check_cells(cells: tuple[Cell, ...]) -> None:
    """Refuse a grid that overlaps or that starts before its own first square.

    Two cells in one square is a document that means two things at once, and
    drawing it would put one on top of the other and say nothing about which.

    There is deliberately no "reaches outside" check on the far side: the
    matrix's extent is *derived* from the cells, so a cell that spans three
    columns makes a matrix three columns wide. Only a negative index is an
    error, because nothing can grow to meet it.
    """
    taken: dict[tuple[int, int], str] = {}
    for cell in cells:
        if cell.across < 1 or cell.down < 1:
            raise DrawspecError(
                f"cell {cell.text[:24]!r} spans {cell.across} x {cell.down}; a cell covers "
                f"at least one square"
            )
        if cell.column < 0 or cell.row < 0:
            raise DrawspecError(
                f"cell {cell.text[:24]!r} is at column {cell.column}, row {cell.row}; a "
                f"matrix starts at column 0, row 0"
            )
        for column in range(cell.column, cell.column + cell.across):
            for row in range(cell.row, cell.row + cell.down):
                if (column, row) in taken:
                    raise DrawspecError(
                        f"cells {taken[(column, row)]!r} and {cell.text[:24]!r} both cover "
                        f"column {column}, row {row}. One square holds one cell."
                    )
                taken[(column, row)] = cell.text[:24]


def _row_heights(
    cells: tuple[Cell, ...], boxes: dict[tuple[int, int], Box], down: int
) -> list[float]:
    """How deep each row is: the deepest cell that *ends* in it.

    Charging a spanning cell to its last row rather than to every row it covers
    is what keeps a two-row cell from doubling the depth of a matrix — it needs
    the two rows together, not two rows each as deep as itself.
    """
    heights = [0.0] * down
    for cell in sorted(cells, key=lambda item: item.down):
        box = boxes[(cell.column, cell.row)]
        covered = sum(heights[cell.row : cell.row + cell.down])
        if box.height > covered:
            heights[cell.row + cell.down - 1] += box.height - covered
    return heights


def _heading_width(document: Document, theme: Theme, measurer: TextMeasurer, width: float) -> float:
    """How much of the width the row headings take, if there are any."""
    return max(
        size_box(heading, theme=theme, measurer=measurer, max_width=width / 3, shape="rect").width
        for heading in document.rows
    )
