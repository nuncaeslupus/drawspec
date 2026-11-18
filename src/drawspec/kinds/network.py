"""The `network` kind: networks as horizontal buses, hosts hanging between them.

The nwdiag picture: each network is a bus — a wide bar with its name and address
written on it — drawn top to bottom in the order written, and each host is a box
under its topmost network, with a straight line to every bus it is on. A host on
two networks stands between them and joins them: a router, a firewall, a web
server with a public and a private side.

**The columns are derived, never written.** `drawspec.buses` orders them so no
host's line crosses a bus it is not on, then for the fewest columns, the shortest
buses and the order nearest the one written. Hosts whose spans are apart share a
column, one above the other, as nwdiag stacks them.

**Where no order keeps a line clear, the line hops the bus.** It stops short of
the bar and jumps it in a half circle to the right, the wiring diagram's mark
for two lines that cross without joining, and goes on down: the bar is not
touched by a straight end, so nothing reads as attached. The order chosen is the
one with the fewest hops, and a bus's name is set clear of every hop over it.

**Every box is one width**, the widest host's, and every box under one bus one
height, so a row of servers reads as a row. A host's shape is its role's — a box,
a drum for `store`, a person for a client — and there are no device icons: what a
box is, its words say.

**An address sits beside its line where the line meets the bus**, on the box's
side of the bus, so it reads as *this host on this network*. A column is made
wide enough for its addresses, and a bus long enough for its name.

**A group is a shaded backdrop** behind its hosts, its name at its top left, in a
band of its own above the boxes so no line runs through the words.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Final

from drawspec.buses import Arrangement, arrange
from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import box_primitives
from drawspec.scene import Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.textgrid import (
    Drawn,
    Grid,
    box_glyphs,
    boxed,
    caption_lines,
    cells,
    finished,
    label_lines,
    plain,
    spelt,
    widest,
    wrapped,
)
from drawspec.theme import Theme

#: The edge role a host's line is drawn in: a plain line with no head.
LINE_ROLE: Final = "link"

#: The role a bus is outlined and washed in, and its name written in.
BUS_ROLE: Final = "step"

#: The role a group's backdrop is filled in. A region: washed, never outlined.
GROUP_ROLE: Final = "group"

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
COLUMN_GAP: Final = 18.0
"""Between two columns."""

OVERHANG: Final = 9.0
"""How far a bus runs past the outer edges of its first and last columns."""

GROUP_PAD: Final = 6.0
"""How far a group's backdrop reaches past its hosts' columns and boxes."""

CLEAR: Final = 18.0
"""The least length of line between a bus and a box: a line, not a join."""

LABEL_PAD: Final = 3.0
"""Between an address and its line, and between an address and the bus."""

BAR_PAD: Final = 3.5
"""Above and below a bus's name, inside the bus."""

BAR_INSET: Final = 8.0
"""Between a bus's left end and its name, and after the name."""

#: The widest a host's box may be, in units, tried in turn until the drawing
#: fits the canvas: a long name wraps rather than widening every box.
BOX_WIDTHS: Final = (150.0, 120.0, 96.0)

Bounds = tuple[float, float, float, float]


@dataclass(frozen=True)
class NetworkDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    arrangement: Arrangement
    boxes: dict[str, Bounds] = field(default_factory=dict)
    """Each host's box, by id: left, top, right, bottom."""

    buses: dict[str, Bounds] = field(default_factory=dict)
    """Each network's bus, by id: left, top, right, bottom."""

    lines: tuple[tuple[str, float, float, float], ...] = ()
    """Each straight length of line drawn: the host's id, its x, and its top and
    bottom y. A line that hops a bus is two lengths, one either side of the hop."""

    hops: tuple[tuple[str, str, Bounds], ...] = ()
    """Each hop drawn: the host's id, the network it jumps, and the half circle's
    bounds — from the line's x out to the right, from above the bar to below it."""

    groups: tuple[Bounds, ...] = ()
    """Each group's backdrop."""

    texts: tuple[Bounds, ...] = ()
    """Every address and group name placed, for the tests that nothing overlaps."""


def network_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a network diagram."""
    return network_drawing(document, theme, measurer).scene


def topology(document: Document) -> Arrangement:
    """The column order for `document`: the same one the SVG and the text form use."""
    index = {network.id: position for position, network in enumerate(document.networks)}
    host_index = {host.id: position for position, host in enumerate(document.hosts)}
    return arrange(
        len(document.networks),
        [[index[name] for name in host.networks] for host in document.hosts],
        [[host_index[member] for member in group.members] for group in document.host_groups],
    )


def network_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> NetworkDrawing:
    """Lay the buses and hosts out.

    Raises:
        FitError: the columns are wider than the canvas even with every box at
            its narrowest.
    """
    arrangement = topology(document)
    last: FitError | None = None
    for box_max in BOX_WIDTHS:
        try:
            return _drawn(document, theme, measurer, arrangement, box_max)
        except FitError as error:
            last = error
    assert last is not None
    raise last


def _drawn(
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
    arrangement: Arrangement,
    box_max: float,
) -> NetworkDrawing:
    unit = theme.scale["body"] / 11
    column_gap, overhang, group_pad = COLUMN_GAP * unit, OVERHANG * unit, GROUP_PAD * unit
    clear, label_pad = CLEAR * unit, LABEL_PAD * unit
    bar_pad, bar_inset = BAR_PAD * unit, BAR_INSET * unit
    font = theme.font.default
    label_size = theme.scale["label"]
    canvas = theme.canvas.width
    networks = document.networks
    hosts = document.hosts
    count = len(networks)
    order = {network.id: position for position, network in enumerate(networks)}
    nets = [[order[name] for name in host.networks] for host in hosts]
    top_of = [attached[0] for attached in nets]
    host_index = {host.id: position for position, host in enumerate(hosts)}
    columns = arrangement.columns
    column_of = arrangement.column_of

    # -- the boxes: one width for all, one height per row --------------------
    sized: list[Box] = []
    for host in hosts:
        try:
            sized.append(
                size_box(
                    host.text,
                    theme=theme,
                    measurer=measurer,
                    role=host.role,
                    max_width=min(box_max * unit, canvas),
                )
            )
        except FitError as error:
            raise FitError(
                f"host {host.id!r} has a word wider than a box may be. Shorten it."
            ) from error
    box_width = max(box.width for box in sized)
    row_height = [0.0] * count
    for position, box in enumerate(sized):
        row_height[top_of[position]] = max(row_height[top_of[position]], box.height)
    boxes = [
        box.resized(width=box_width, height=row_height[top_of[position]])
        for position, box in enumerate(sized)
    ]

    # -- the words beside the lines and on the buses -------------------------
    def measured(text: str) -> tuple[float, float, float]:
        extents = measurer.measure(text, font, label_size)
        return extents.width, extents.ascent, extents.descent

    probe = measured("0")
    label_height = probe[1] + probe[2]
    address_width = [
        max((measured(address)[0] for address in host.addresses if address), default=0.0)
        for host in hosts
    ]

    def bus_block(position: int) -> TextBlock:
        network = networks[position]
        words = f"**{network.text}**" + (f"  {network.address}" if network.address else "")
        return wrap(words, 1e6, measurer, theme=theme, level="body", lead=False)

    bus_blocks = [bus_block(position) for position in range(count)]
    bar_height = max(block.height for block in bus_blocks) + 2 * bar_pad
    # A hop clears the bar by a label's pad above and below, so its ends are
    # plainly not on it.
    hop_radius = bar_height / 2 + label_pad
    crossed = set(arrangement.crossings)
    hopped: list[list[int]] = [[] for _ in range(count)]
    for host_at, network_at in arrangement.crossings:
        hopped[network_at].append(column_of[host_at])

    def name_start(position: int, x0: float, middle: list[float]) -> tuple[float, int | None]:
        """Where a bus's name starts, clear of every hop over the bus, and the
        column of the last hop it was moved past."""
        start, past = x0 + bar_inset, None
        wide = bus_blocks[position].width
        for column in sorted(set(hopped[position])):
            x = middle[column]
            if start - label_pad < x + hop_radius + label_pad and x - label_pad < start + wide:
                start, past = x + hop_radius + bar_inset, column
        return start, past

    group_blocks = [
        wrap(group.text, 1e6, measurer, theme=theme, level="label", lead=False)
        if group.text
        else None
        for group in document.host_groups
    ]
    group_members = [
        [host_index[member] for member in group.members] for group in document.host_groups
    ]
    group_columns = [
        (min(column_of[m] for m in members), max(column_of[m] for m in members))
        for members in group_members
    ]
    group_gaps = [
        (min(top_of[m] for m in members), max(top_of[m] for m in members))
        for members in group_members
    ]

    # -- columns: wide enough for the box, the addresses and a group's name ---
    width = [box_width] * len(columns)
    for column, members in enumerate(columns):
        for member in members:
            if address_width[member]:
                width[column] = max(width[column], 2 * (2 * label_pad + address_width[member]))
    for block, (left, _) in zip(group_blocks, group_columns, strict=True):
        if block is not None:
            width[left] = max(width[left], 2 * (block.width + 2 * label_pad))

    def lefts() -> list[float]:
        edges = [overhang]
        for column in range(1, len(columns)):
            edges.append(edges[-1] + width[column - 1] + column_gap)
        return edges

    # A bus is long enough for its name: the last column it spans grows.
    # A name set past a hop needs the length past the hop.
    for _ in range(2 * count + 2):
        edge = lefts()
        middle = [edge[column] + width[column] / 2 for column in range(len(columns))]
        grown = False
        for position, (first, final) in enumerate(arrangement.extents):
            length = edge[final] + width[final] - edge[first] + 2 * overhang
            x0 = edge[first] - overhang
            start, past = name_start(position, x0, middle)
            needed = start - x0 + bus_blocks[position].width + bar_inset
            if needed > length + 1e-6:
                # A hop in the last column moves by half of what that column grows.
                width[final] += (needed - length) * (2 if past == final else 1)
                grown = True
        if not grown:
            break
    edge = lefts()
    centre = [edge[column] + width[column] / 2 for column in range(len(columns))]
    total_width = edge[-1] + width[-1] + overhang
    if total_width > canvas + 0.01:
        raise FitError(
            f"the {len(columns)} columns of hosts measure {total_width:.0f} units across and the "
            f"canvas is {canvas:.0f}. Shorten the longest host name or address, put fewer hosts "
            f"on one network, or give the diagram more width."
        )

    # -- rows: a bus, the space under it, its boxes, the space over the next --
    below = [False] * count
    above = [False] * count
    for position, host in enumerate(hosts):
        for network, address in zip(nets[position], host.addresses, strict=True):
            if not address:
                continue
            if network == top_of[position]:
                below[network] = True
            else:
                above[network] = True
    zone = 2 * label_pad + label_height
    band = [0.0] * count
    tops = [False] * count
    bottoms = [False] * count
    for block, (first, final) in zip(group_blocks, group_gaps, strict=True):
        tops[first] = True
        bottoms[final] = True
        if block is not None:
            band[first] = max(band[first], block.height + label_pad)

    bar_top = [0.0] * count
    box_top = [0.0] * count
    y = 0.0
    bottom = 0.0
    for network in range(count):
        bar_top[network] = y
        y += bar_height
        lead = max(clear, (zone if below[network] else 0.0) + label_pad)
        if tops[network]:
            lead = max(clear, (zone if below[network] else label_pad) + group_pad + label_pad)
        box_top[network] = y + lead + band[network]
        y = box_top[network] + row_height[network]
        bottom = y + (group_pad if bottoms[network] else 0.0)
        if network < count - 1:
            tail = max(clear, (zone if above[network + 1] else 0.0) + label_pad)
            if bottoms[network]:
                tail = max(clear, group_pad + (zone if above[network + 1] else label_pad))
            y += tail
    height = max(bottom, bar_top[-1] + bar_height)

    # -- primitives -----------------------------------------------------------
    backdrops: list[Primitive] = []
    lines: list[Primitive] = []
    bars: list[Primitive] = []
    words: list[Primitive] = []
    shapes: list[Primitive] = []
    texts: list[Bounds] = []
    group_bounds: list[Bounds] = []
    for block, (left, right), (first, final) in zip(
        group_blocks, group_columns, group_gaps, strict=True
    ):
        x0 = edge[left] - group_pad
        x1 = edge[right] + width[right] + group_pad
        y0 = box_top[first] - band[first] - group_pad
        y1 = box_top[final] + row_height[final] + group_pad
        group_bounds.append((x0, y0, x1, y1))
        backdrops.append(
            Polygon(
                GROUP_ROLE,
                points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                fill="solid",
                fill_colour="currentColor",
                fill_opacity=theme.network.group,
                region=True,
            )
        )
        if block is not None:
            top = box_top[first] - band[first]
            words.extend(_lines(block, edge[left], top, "label", FURNITURE_ROLE))
            texts.append((edge[left], top, edge[left] + block.width, top + block.height))

    bus_bounds: dict[str, Bounds] = {}
    for position, (first, final) in enumerate(arrangement.extents):
        x0 = edge[first] - overhang
        x1 = edge[final] + width[final] + overhang
        y0, y1 = bar_top[position], bar_top[position] + bar_height
        bus_bounds[networks[position].id] = (x0, y0, x1, y1)
        bars.append(
            Polygon(
                BUS_ROLE,
                points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                fill="solid",
                fill_colour="currentColor",
                fill_opacity=theme.network.bus,
            )
        )
        block = bus_blocks[position]
        top = y0 + (bar_height - block.height) / 2
        start, _ = name_start(position, x0, centre)
        words.extend(_lines(block, start, top, "body", BUS_ROLE))

    box_bounds: dict[str, Bounds] = {}
    drawn_lines: list[tuple[str, float, float, float]] = []
    hop_bounds: list[tuple[str, str, Bounds]] = []
    for position, host in enumerate(hosts):
        x = centre[column_of[position]]
        first, final = nets[position][0], nets[position][-1]
        box = replace(boxes[position], x=x - box_width / 2, y=box_top[first])
        box_bounds[host.id] = (box.x, box.y, box.x + box.width, box.y + box.height)
        shapes.extend(box_primitives(box, theme, measurer))
        y0 = bar_top[first] + bar_height
        lines.append(Path(LINE_ROLE, points=((x, y0), (x, box.y))))
        drawn_lines.append((host.id, x, y0, box.y))
        if final > first:
            y_from = box.y + box.height
            points = [(x, y_from)]
            for network in range(first + 1, final):
                if (position, network) not in crossed:
                    continue
                mid = bar_top[network] + bar_height / 2
                over, under = mid - hop_radius, mid + hop_radius
                drawn_lines.append((host.id, x, y_from, over))
                points.extend(_hop(x, mid, hop_radius))
                hop_bounds.append((host.id, networks[network].id, (x, over, x + hop_radius, under)))
                y_from = under
            y1 = bar_top[final]
            points.append((x, y1))
            lines.append(Path(LINE_ROLE, points=tuple(points)))
            drawn_lines.append((host.id, x, y_from, y1))
        for network, address in zip(nets[position], host.addresses, strict=True):
            if not address:
                continue
            wide, ascent, descent = measured(address)
            start = x + label_pad
            if network == first:
                top = bar_top[network] + bar_height + label_pad
            else:
                top = bar_top[network] - label_pad - ascent - descent
            words.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=start,
                    y=top + ascent,
                    spans=(TextSpan(text=address, font=font),),
                    level="label",
                    anchor="start",
                )
            )
            texts.append((start, top, start + wide, top + ascent + descent))

    scene = Scene(
        width=total_width,
        height=height,
        primitives=(*backdrops, *lines, *bars, *shapes, *words),
        title=document.title,
        description=document.description,
    )
    return NetworkDrawing(
        scene=scene,
        arrangement=arrangement,
        boxes=box_bounds,
        buses=bus_bounds,
        lines=tuple(drawn_lines),
        hops=tuple(hop_bounds),
        groups=tuple(group_bounds),
        texts=tuple(texts),
    )


#: How many straight pieces a hop's half circle is drawn in: the scene holds
#: polylines only, and at a hop's size twelve read as a curve.
HOP_SEGMENTS: Final = 12


def _hop(x: float, mid: float, radius: float) -> list[tuple[float, float]]:
    """A half circle from above `mid` to below it, bulging right of `x`."""
    return [
        (
            x + radius * math.cos(math.pi * (step / HOP_SEGMENTS - 0.5)),
            mid + radius * math.sin(math.pi * (step / HOP_SEGMENTS - 0.5)),
        )
        for step in range(HOP_SEGMENTS + 1)
    ]


def _lines(block: TextBlock, x: float, top: float, level: str, role: str) -> list[TextLine]:
    """A wrapped block set from `x`, `top` down, each line a left-anchored TextLine."""
    placed: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            placed.append(
                TextLine(
                    role,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor="start",
                )
            )
    return placed


# ---------------------------------------------------------------------------
# Text: buses as heavy rules, hosts as boxes in the same columns
# ---------------------------------------------------------------------------

#: Cells between two columns: room for a group's frame on each side and a space.
TEXT_COLUMN_GAP: Final = 3

#: The widest a host's words may run in its box before they wrap at a space, as
#: the SVG wraps them; a longer word widens every box instead.
TEXT_BOX_ROOM: Final = 12

#: A bus's glyphs per charset: the rule, then where a line leaves it downward,
#: arrives from above, and passes through.
TEXT_BUS: Final = {
    "unicode": ("━", "┯", "┷", "┿"),
    "ascii": ("=", "+", "+", "+"),
}

#: A hop per charset: the bus stops a cell short either side and the line runs
#: on through the gap, so no junction glyph is drawn — a joined line is `┿`,
#: a hopped one `╸│╺`.
TEXT_HOP: Final = {
    "unicode": ("╸", "│", "╺"),
    "ascii": (" ", "|", " "),
}

#: A group's frame per charset: corners clockwise from top left, across, down.
TEXT_FRAME: Final = {
    "unicode": ("┌", "┐", "┘", "└", "┄", "┆"),
    "ascii": ("+", "+", "+", "+", ".", ":"),
}


def network_text(document: Document, width: int, charset: str) -> str:
    """A `network` diagram as plain text, on the same columns as the SVG.

    Each bus is a heavy rule with its name and address to its left; each host a
    box under its topmost bus, joined to every bus it is on by a light line, the
    junction on the bus showing which way the line goes. A line that must cross
    a bus it is not on hops it: the rule breaks a cell either side and the line
    runs through the gap with no junction, `━╸│╺━` against a join's `━┿━`. An address sits beside
    its line next to the bus, on the box's side. A group is a dashed frame round
    its hosts with its name in the top edge.

    Raises:
        FitError: the columns, with the buses' names beside them, are wider than
            `width`.
    """
    arrangement = topology(document)
    networks = document.networks
    hosts = document.hosts
    count = len(networks)
    order = {network.id: position for position, network in enumerate(networks)}
    nets = [[order[name] for name in host.networks] for host in hosts]
    top_of = [attached[0] for attached in nets]
    host_index = {host.id: position for position, host in enumerate(hosts)}
    columns = arrangement.columns
    column_of = arrangement.column_of
    rule, down, up, through = TEXT_BUS[charset]
    hop_left, hop_line, hop_right = TEXT_HOP[charset]
    corner_tl, corner_tr, corner_br, corner_bl, across, upright = TEXT_FRAME[charset]

    words = [
        [
            broken
            for line in label_lines(host.text, charset, f"/hosts/{position}/text")
            for broken in wrapped(
                line,
                max([TEXT_BOX_ROOM, *(cells(word) for word in line.split())]),
                f"/hosts/{position}/text",
                width,
            )
        ]
        for position, host in enumerate(hosts)
    ]
    addresses = [
        [spelt(address, charset, f"/hosts/{position}/networks") for address in host.addresses]
        for position, host in enumerate(hosts)
    ]
    inner = max(cells(line) for lines in words for line in lines)
    box_width = inner + 4
    rows_of = [len(lines) + 2 for lines in words]
    row_height = [0] * count
    for position in range(len(hosts)):
        row_height[top_of[position]] = max(row_height[top_of[position]], rows_of[position])

    group_members = [
        [host_index[member] for member in group.members] for group in document.host_groups
    ]
    group_columns = [
        (min(column_of[m] for m in members), max(column_of[m] for m in members))
        for members in group_members
    ]
    group_gaps = [
        (min(top_of[m] for m in members), max(top_of[m] for m in members))
        for members in group_members
    ]
    group_names = [
        " ".join(label_lines(group.text, charset, f"/groups/{index}/text")) if group.text else ""
        for index, group in enumerate(document.host_groups)
    ]

    span = [box_width] * len(columns)
    for column, members in enumerate(columns):
        for member in members:
            for address in addresses[member]:
                # The address starts two cells right of the line, at the middle.
                while span[column] - span[column] // 2 - 2 < cells(address):
                    span[column] += 1
    for name, (left, _) in zip(group_names, group_columns, strict=True):
        if name:
            # The name sits in the frame's top edge, clear of the first line.
            while span[left] // 2 - 2 < cells(name):
                span[left] += 1

    bus_names = [
        spelt(
            plain(network.text).replace("\n", " ")
            + (f" {plain(network.address)}" if network.address else ""),
            charset,
            f"/networks/{position}",
        )
        for position, network in enumerate(networks)
    ]

    def lefts(margin: int) -> list[int]:
        edges = [margin]
        for column in range(1, len(columns)):
            edges.append(edges[-1] + span[column - 1] + TEXT_COLUMN_GAP)
        return edges

    # The names stand left of their buses; the margin is what the longest needs.
    plain_edges = lefts(0)
    margin = max(
        [1]
        + [
            cells(bus_names[position]) + 2 - plain_edges[first]
            for position, (first, _) in enumerate(arrangement.extents)
        ]
    )
    edge = lefts(margin)
    middle = [edge[column] + span[column] // 2 for column in range(len(columns))]

    # -- rows -----------------------------------------------------------------
    tops = [False] * count
    bottoms = [False] * count
    for first, final in group_gaps:
        tops[first] = True
        bottoms[final] = True
    bus_row = [0] * count
    box_row = [0] * count
    frame_top = [0] * count
    frame_bottom = [0] * count
    row = 0
    for network in range(count):
        bus_row[network] = row
        row += 2  # the bus, then a row of line with the addresses under it
        if tops[network]:
            frame_top[network] = row
            row += 1
        box_row[network] = row
        row += row_height[network]
        if bottoms[network]:
            frame_bottom[network] = row
            row += 1
        if network < count - 1:
            row += 1  # a row of line with the addresses over the next bus

    grid = Grid(charset)
    hops = {(bus_row[network], middle[column_of[host]]) for host, network in arrangement.crossings}

    # Lines, boxes and addresses.
    joins: dict[tuple[int, int], set[str]] = {}
    for position, host in enumerate(hosts):
        x = middle[column_of[position]]
        first, final = nets[position][0], nets[position][-1]
        top = box_row[first]
        height = row_height[first]
        glyphs = box_glyphs(host.role, charset)
        lines = words[position]
        above = (height - 2 - len(lines)) // 2
        body = [""] * above + lines + [""] * (height - 2 - len(lines) - above)
        drawn = boxed(body, host.role, charset, inner=inner, align="centre")
        left = x - box_width // 2
        for offset, text in enumerate(drawn):
            grid.text(top + offset, left, text)
        grid.text(top, x, glyphs.up)
        grid.vertical(x, bus_row[first] + 1, top - 1)
        joins.setdefault((bus_row[first], x), set()).add("down")
        if final > first:
            grid.text(top + height - 1, x, glyphs.down)
            grid.vertical(x, top + height, bus_row[final] - 1)
            for network in nets[position][1:]:
                joins.setdefault((bus_row[network], x), set()).add("up")
                if network != final:
                    joins[(bus_row[network], x)].add("down")
                    grid.vertical(x, bus_row[network] + 1, bus_row[network + 1] - 1)
        for network, address in zip(nets[position], addresses[position], strict=True):
            if address:
                where = bus_row[network] + 1 if network == first else bus_row[network] - 1
                grid.text(where, x + 2, address)

    # Groups' frames round what is drawn, never over a line or a box.
    for name, (left, right), (first, final) in zip(
        group_names, group_columns, group_gaps, strict=True
    ):
        x0, x1 = edge[left] - 1, edge[right] + span[right]
        y0, y1 = frame_top[first], frame_bottom[final]
        for x in range(x0 + 1, x1):
            for y in (y0, y1):
                if not grid.used(y, x):
                    grid.text(y, x, across)
        for y in range(y0 + 1, y1):
            if y not in bus_row:
                grid.text(y, x0, upright)
                grid.text(y, x1, upright)
        grid.text(y0, x0, corner_tl)
        grid.text(y0, x1, corner_tr)
        grid.text(y1, x0, corner_bl)
        grid.text(y1, x1, corner_br)
        if name:
            grid.text(y0, x0 + 2, name)

    # Buses last, over everything, with their names to the left.
    for position, (first, final) in enumerate(arrangement.extents):
        y = bus_row[position]
        x0, x1 = edge[first] - 1, edge[final] + span[final]
        for x in range(x0, x1 + 1):
            way = joins.get((y, x), set())
            glyph = rule
            if (y, x) in hops:
                glyph = hop_line
            elif (y, x + 1) in hops:
                glyph = hop_left
            elif (y, x - 1) in hops:
                glyph = hop_right
            elif way == {"down"}:
                glyph = down
            elif way == {"up"}:
                glyph = up
            elif way:
                glyph = through
            grid.text(y, x, glyph)
        name = bus_names[position]
        start = x0 - 1 - cells(name)
        if any(grid.used(y, x) for x in range(start, x0)):
            start = x1 + 2
        grid.text(y, start, name)

    drawn_lines = [Drawn(line, "/hosts", "the columns of hosts") for line in grid.lines()]
    widest(drawn_lines, width)
    return finished(
        [line.text for line in drawn_lines] + caption_lines(document.caption, width, charset)
    )


__all__ = ["NetworkDrawing", "network_drawing", "network_scene", "network_text", "topology"]
