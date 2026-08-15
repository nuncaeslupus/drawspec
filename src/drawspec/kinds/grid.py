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

import math
from itertools import pairwise

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import box_primitives, text_runs
from drawspec.legend import entries_for, height_of, primitives_for
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextRun, TextSpan
from drawspec.schema import Cell, Document, Item
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
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

    Widths stay normalised either way, because peers sharing an edge is this
    family's rule and irregular *spacing* is not irregular *labels*. When two of
    those equal labels will not fit the gap their values ask for, that is a
    `FitError` naming the pair rather than an overlap.

    **An entry's `note` goes under the line.** The hand-drawn originals put text
    on both sides of every mark and they were right to: what happened is one
    thing and when it happened is another, and a timeline that stacks both above
    the axis makes the reader work out which line is which kind. Above the line
    is the event; below it is the year, the duration, the aside. Set at the label
    size rather than the body size, because it is an annotation on the event and
    not a second event.
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
    notes = _notes(document.items, theme, measurer, label_width)

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

    below = axis_y + tick / 2
    if notes:
        primitives.extend(_note_runs(notes, centres, below + theme.box.padding.top))
        below += theme.box.padding.top + _note_band(notes)

    if document.spans:
        bars, below = _span_bars(document, centres, below, theme, measurer)
        primitives.extend(bars)

    return _scene(document, primitives, width, below)


def _span_bars(
    document: Document,
    centres: list[float],
    top: float,
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[list[Primitive], float]:
    """The named intervals, in lanes under the axis.

    A span is the quantity that is not a thing on the diagram but the
    **distance** between two things on it. A recovery point objective is not an
    event: it is how much lies between the last backup and the disaster, and on
    the disaster-timeline original it is the entire content — four instants
    without their intervals are four words, which is why that sheet was the one
    of eighty-nine with no document at all.

    Each bar runs between its two entries' marks, capped at both ends so a
    reader can see where it starts and stops, with its name centred above it.
    Two spans that overlap go in different lanes: `MTD = RTO + WRT` is a span
    over two spans, and the arithmetic is only visible when the wider one is
    drawn clear of the two it covers. Lanes are assigned in declaration order,
    so the document decides which interval sits nearest the axis.
    """
    order = {item.id: index for index, item in enumerate(document.items) if item.id}
    cap = theme.edge.head_length * TICK_FRACTION
    size = theme.scale["label"]
    line = measurer.measure("0", theme.font.default, size)
    gap = theme.box.padding.top

    lanes: list[list[tuple[float, float]]] = []
    placed: list[tuple[int, float, float, str]] = []
    for span in document.spans:
        left, right = centres[order[span.start]], centres[order[span.end]]
        for index, lane in enumerate(lanes):
            if all(right <= start or left >= end for start, end in lane):
                lane.append((left, right))
                placed.append((index, left, right, span.text))
                break
        else:
            lanes.append([(left, right)])
            placed.append((len(lanes) - 1, left, right, span.text))

    depth = gap + line.height + gap
    primitives: list[Primitive] = []
    for row, left, right, text in placed:
        base = top + gap + row * depth
        bar = base + line.height + gap / 2
        primitives.append(Path(AXIS_ROLE, points=((left, bar), (right, bar))))
        for end in (left, right):
            primitives.append(Path(AXIS_ROLE, points=((end, bar - cap / 2), (end, bar + cap / 2))))
        primitives.append(
            TextRun(
                AXIS_ROLE,
                x=(left + right) / 2,
                y=base + line.ascent,
                text=text,
                level="label",
                font=theme.font.default,
                anchor="middle",
            )
        )
    return primitives, top + gap + len(lanes) * depth


def _notes(
    items: tuple[Item, ...], theme: Theme, measurer: TextMeasurer, label_width: float
) -> list[TextBlock | None]:
    """Each entry's note, wrapped to the width its label already fits in.

    Empty when no entry has one, so a timeline without notes is exactly the size
    it was before. Not all-or-nothing, unlike `at`: a note is an aside on one
    event rather than a scale the whole line is read against, so an entry with
    nothing to add simply says nothing.
    """
    if not any(item.note for item in items):
        return []
    return [
        wrap(item.note, label_width, measurer, theme=theme, level="label") if item.note else None
        for item in items
    ]


def _note_band(notes: list[TextBlock | None]) -> float:
    """How deep the band under the axis is: the tallest note in it."""
    return max((block.height for block in notes if block), default=0.0)


def _note_runs(notes: list[TextBlock | None], centres: list[float], top: float) -> list[Primitive]:
    """One centred line per line of each note, under its own tick.

    Anchored at the centre rather than placed by a measured left edge, for the
    reason `text_runs` is: a reader whose page substitutes the font gets
    different widths, and the arithmetic belongs to whoever has the font.
    """
    runs: list[Primitive] = []
    for block, centre in zip(notes, centres, strict=True):
        if block is None:
            continue
        for index, line in enumerate(block.lines):
            if not line.spans:
                continue
            runs.append(
                TextLine(
                    "step",
                    x=centre,
                    y=top + index * block.advance + block.ascent,
                    spans=tuple(
                        TextSpan(text=span.text, font=span.font, weight=span.weight)
                        for span in line.spans
                        if span.text
                    ),
                    level="label",
                    anchor="middle",
                )
            )
    return runs


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

    # A matrix that carries relations is a grid of boxes rather than a solid
    # table, so its cells stand apart far enough for an arrow to live in the
    # join. Only then: the tables that have no edges keep the shared borders
    # that make them read as tables.
    inset = theme.edge.clearance if document.edges else 0.0
    placements: dict[str, tuple[float, float, float, float]] = {}

    for cell in cells:
        left = heading_width + cell.column * column_width + inset
        cell_width = column_width * cell.across - inset * 2
        top = tops[cell.row] + inset
        cell_height = tops[cell.row + cell.down] - tops[cell.row] - inset * 2
        right, bottom = left + cell_width, top + cell_height
        if cell.id:
            placements[cell.id] = (left, top, right, bottom)
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

    primitives.extend(_cell_edges(document, placements, theme, measurer))

    # What the fills stand for. A matrix's whole content is a comparison between
    # groups of cells, so a matrix with two groups and no key is a drawing whose
    # subject is undrawn — the original this kind replaces carried one.
    #
    # A group's own name is the fallback and not the intent: `group` is how a
    # cell says which other cells are like it, and an id-shaped one — `carrega`,
    # `capcalera` — was being read out to the reader as though it were prose. A
    # `key` entry gives the group a name meant for reading.
    named = {entry.group: entry.text for entry in document.key}
    key = entries_for(
        [(named.get(group, group), "step", True) for group in _named_groups(cells)], theme
    )
    primitives.extend(primitives_for(key, theme, measurer, 0.0, tops[-1], width))
    return _scene(document, primitives, width, tops[-1] + height_of(key, theme, measurer, width))


def _named_groups(cells: tuple[Cell, ...]) -> list[str]:
    """Every group a cell names, in order of first mention — the legend's order too."""
    named: list[str] = []
    for cell in cells:
        if cell.group and cell.group not in named:
            named.append(cell.group)
    return named


def _group_fills(cells: tuple[Cell, ...], theme: Theme) -> dict[str, str]:
    """One fill per group, from the theme's sequence, in order of first mention.

    The author names the *group*, never the fill. `fill` is in the schema's
    rejection table for exactly this reason — appearance is a property of the
    role, not of the element — and a matrix does not get an exemption just
    because its whole content is a comparison. What it gets is a way to say
    which cells are the same kind of cell, and the theme turns that into
    something a black-and-white printer can keep apart.
    """
    named = _named_groups(cells)
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
    """Every row the same depth: the deepest any one cell needs of a single row.

    Equal rows for the reason a `stack`'s layers are equal — *"a stack whose
    layers differ in height reads as a ranking of importance, which is not what
    the author said"* — and a matrix is the kind whose whole content is a
    comparison, so a row drawn deeper than its neighbours is the strongest claim
    on the page and nobody made it. The corpus review asked for this directly:
    "could we make all of the rows the same height?"

    A spanning cell is charged *per row it covers* rather than to the last one.
    It needs its rows together, not each of them as deep as itself, so what it
    demands of one row is its own depth divided by how many it spans — which is
    what keeps a two-row cell from doubling the matrix.
    """
    demand = max(
        (boxes[(cell.column, cell.row)].height / cell.down for cell in cells),
        default=0.0,
    )
    return [demand] * down


def _heading_width(document: Document, theme: Theme, measurer: TextMeasurer, width: float) -> float:
    """How much of the width the row headings take, if there are any."""
    return max(
        size_box(heading, theme=theme, measurer=measurer, max_width=width / 3, shape="rect").width
        for heading in document.rows
    )


def _cell_edges(
    document: Document,
    placements: dict[str, tuple[float, float, float, float]],
    theme: Theme,
    measurer: TextMeasurer,
) -> list[Primitive]:
    """The relations between cells, drawn over the grid that placed them.

    A grid's cells are not always only cells. On the process original the upper
    one **produces** the lower and the left one **precedes** the right, and a
    `matrix` that drew the boxes and dropped all three relations left the reader
    with a table where the source had a process. Drawn as a `flow` instead, with
    one group per phase, every relation survived and the drawing came out four
    times taller than the sheet.

    So the grid keeps placing the cells and the relations are drawn on top: a
    straight run between the two cells' facing edges, at the theme's own head,
    with the label beside it. Facing edges rather than centres, because two
    cells of a grid are almost always neighbours — the run is short, and a line
    from centre to centre would be a line inside two boxes.
    """
    if not document.edges:
        return []
    primitives: list[Primitive] = []
    size = theme.scale["label"]
    for edge in document.edges:
        source, target = placements[edge.source], placements[edge.target]
        start, finish = _facing(source, target)
        role = edge.role
        span = math.hypot(finish[0] - start[0], finish[1] - start[1])
        if span <= 0:
            continue
        towards = ((finish[0] - start[0]) / span, (finish[1] - start[1]) / span)
        if theme.edge_roles[role].has_head:
            back = min(theme.edge.head_length, span)
            shaft = (finish[0] - towards[0] * back, finish[1] - towards[1] * back)
            wing = theme.edge.head_length / 2
            across = (-towards[1] * wing, towards[0] * wing)
            primitives.append(Path(role, points=(start, shaft)))
            primitives.append(
                Polygon(
                    role,
                    points=(
                        finish,
                        (shaft[0] + across[0], shaft[1] + across[1]),
                        (shaft[0] - across[0], shaft[1] - across[1]),
                    ),
                )
            )
        else:
            primitives.append(Path(role, points=(start, finish)))

        if edge.label:
            extents = measurer.measure(edge.label, theme.font.default, size)
            away = theme.edge.clearance + extents.ascent
            middle = ((start[0] + finish[0]) / 2, (start[1] + finish[1]) / 2)
            primitives.append(
                TextRun(
                    role,
                    x=middle[0] - towards[1] * away,
                    y=middle[1] + towards[0] * away,
                    text=edge.label,
                    level="label",
                    font=theme.font.default,
                    anchor="middle",
                )
            )
    return primitives


def _facing(
    source: tuple[float, float, float, float], target: tuple[float, float, float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    """The two points on the cells' facing edges, on whichever axis separates them.

    A grid puts its cells beside or above each other, so one axis is the answer
    and the other is a tie: the wider separation wins, and equal separation
    means diagonal neighbours, where the horizontal reads better than a corner
    to corner run.
    """
    sx1, sy1, sx2, sy2 = source
    tx1, ty1, tx2, ty2 = target
    across = max(tx1 - sx2, sx1 - tx2)
    down = max(ty1 - sy2, sy1 - ty2)
    if across >= down:
        y = (max(sy1, ty1) + min(sy2, ty2)) / 2
        return ((sx2, y), (tx1, y)) if tx1 >= sx2 else ((sx1, y), (tx2, y))
    x = (max(sx1, tx1) + min(sx2, tx2)) / 2
    return ((x, sy2), (x, ty1)) if ty1 >= sy2 else ((x, sy1), (x, ty2))
