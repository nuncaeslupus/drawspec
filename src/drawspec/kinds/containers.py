"""Groups: a box drawn around other boxes, with its own caption.

The schema has declared `groups` since v1 and the theme has had a `group` role
since v1 — dashed, unfilled, rectangular — and nothing drew either. This module
is what was missing between them.

**A group is not a kind.** It is a container over the graph kinds, so a `flow`
or a `tree` gains one by naming members, and everything else about the drawing
is unchanged. That is the whole reason this is cheap: the boxes are still sized
by their own text, the engine still places them, routing still joins them.

**Nesting is layout inside layout.** Each group lays its own members out on its
own, comes back with an extent, and is handed to its parent's layout as a single
node of that size. Which means a group's contents are placed before the group
itself is, and the whole tree is then translated into place in one pass. Two
consequences worth knowing:

* **Direction is chosen per level.** A group of three peers may run across while
  the diagram around it runs down, because `best_layout` is asked at every
  level. That is usually what the reader wants and always what the width wants.
* **An edge is lifted to the level it crosses.** An edge from a node inside one
  group to a node inside another is, to the layout that contains both, an edge
  between those two groups. It is only ever *drawn* between the real endpoints —
  the lifting decides ranks, not geometry.

**Only leaves obstruct.** Routing is given the leaf boxes and not the frames,
because an edge that ends inside a group has to cross that group's border to get
there, and a frame that blocked it would make the diagram undrawable rather than
tidy. The cost is that an edge may clip a frame it has no business in; the
alternative — per-edge obstacle sets — buys less than it complicates, and the
corpus this was built for does not contain the case.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Final

from drawspec.errors import DrawspecError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import text_runs
from drawspec.layout import (
    LayeredEngine,
    Layout,
    LayoutEdge,
    LayoutNode,
    Placement,
    Spacing,
    best_layout,
)
from drawspec.routing import Obstacle
from drawspec.scene import Primitive, Rect
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The role a group frame and its caption are drawn in. One of the theme's
#: declared node roles, so a consumer theme can restyle a container without
#: knowing this module exists.
GROUP_ROLE: Final = "group"

#: The type level a group caption is set at. `body`, like every other label in
#: every other kind — a caption that announced itself at heading size would be
#: the pyramid mistake in a new place.
GROUP_LEVEL: Final = "body"


@dataclass(frozen=True)
class Frame:
    """One group, drawn: its outline, and the caption band across its top."""

    id: str
    x: float
    y: float
    width: float
    height: float
    caption: Box | None
    depth: int
    """How many frames enclose this one. Zero for a top-level group."""

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def moved(self, dx: float, dy: float) -> Frame:
        return Frame(
            id=self.id,
            x=self.x + dx,
            y=self.y + dy,
            width=self.width,
            height=self.height,
            caption=(
                None
                if self.caption is None
                else self.caption.moved_to(self.caption.x + dx, self.caption.y + dy)
            ),
            depth=self.depth,
        )


@dataclass(frozen=True)
class Nesting:
    """Who contains whom, resolved once and asked many times."""

    members: Mapping[str, tuple[str, ...]]
    """Direct members of each group, in the order the author wrote them."""

    parent: Mapping[str, str]
    """The group each id sits directly inside. Absent for a top-level id."""

    groups: frozenset[str] = field(default_factory=frozenset)

    @property
    def roots(self) -> tuple[str, ...]:
        """Nothing contains these, in the order the document declares them.

        A loose node sits where it was written. A group has no position of its
        own — `groups` is a second array, not a place in `nodes` — so it sits
        where its **earliest member** was written, wherever in its member list
        that one appears. Ordering on `members[0]` instead would tie a group's
        place among its siblings to which of its own members it happens to list
        first, so reordering the inside of a container would move the container;
        the earliest position its content occupies does not move.

        Iterating `groups` instead of sorting would be iterating a `frozenset`
        of strings — an order that changes with the interpreter's hash seed, so
        the same document rendered twice could differ.
        """
        positions = {node: index for index, node in enumerate(self._nodes)}

        def declared(identifier: str) -> tuple[int, str]:
            if identifier in positions:
                return (positions[identifier], identifier)
            buried = [
                positions[member] for member in self.descendants(identifier) if member in positions
            ]
            return (min(buried, default=len(positions)), identifier)

        roots = [
            identifier
            for identifier in (*self.groups, *self._nodes)
            if identifier not in self.parent
        ]
        return tuple(sorted(roots, key=declared))

    _nodes: tuple[str, ...] = ()

    def descendants(self, identifier: str) -> tuple[str, ...]:
        """Every id under `identifier`, groups included, depth first."""
        found: list[str] = []
        for member in self.members.get(identifier, ()):
            found.append(member)
            found.extend(self.descendants(member))
        return tuple(found)

    def lift(self, identifier: str, level: frozenset[str]) -> str | None:
        """The ancestor of `identifier` that belongs to `level`, if any.

        This is what turns an edge between two deeply-buried nodes into an edge
        the layout at some level can rank: walk up until the level recognises
        you.
        """
        current: str | None = identifier
        while current is not None:
            if current in level:
                return current
            current = self.parent.get(current)
        return None


def nesting_of(document: Document) -> Nesting:
    """Read the document's groups into a containment tree.

    Raises:
        DrawspecError: a member is claimed by two groups, or the groups form a
            cycle. Both are documents drawspec cannot draw rather than documents
            it draws badly, and the message says which id is at fault.
    """
    identifiers = {node.id for node in document.nodes}
    groups = {group.id for group in document.groups}
    members: dict[str, tuple[str, ...]] = {}
    parent: dict[str, str] = {}
    for group in document.groups:
        members[group.id] = tuple(group.members)
        for member in group.members:
            if member in parent:
                raise DrawspecError(
                    f"{member!r} is a member of both {parent[member]!r} and {group.id!r}. "
                    f"A box sits inside one container or none."
                )
            if member not in identifiers and member not in groups:
                raise DrawspecError(
                    f"{member!r} is a member of group {group.id!r} but is neither a node "
                    f"nor a group in this document"
                )
            parent[member] = group.id

    for identifier in groups:
        seen: set[str] = set()
        current: str | None = identifier
        while current is not None:
            if current in seen:
                raise DrawspecError(
                    f"group {identifier!r} contains itself, by way of {sorted(seen)}"
                )
            seen.add(current)
            current = parent.get(current)

    return Nesting(
        members=members,
        parent=parent,
        groups=frozenset(groups),
        _nodes=tuple(node.id for node in document.nodes),
    )


@dataclass(frozen=True)
class Arrangement:
    """One level laid out: where its members went, and how big that came out."""

    layout: Layout
    """This level's own layout — kept whole, so ranks and reversed edges survive."""

    places: Mapping[str, Placement]
    """Leaf id → placement, flattened out of every level, in this level's
    coordinates. A group's own frame is in `frames`, not here: routing joins
    boxes, and a container is not one."""

    frames: tuple[Frame, ...]

    @property
    def width(self) -> float:
        return self.layout.width

    @property
    def height(self) -> float:
        return self.layout.height

    @property
    def direction(self) -> str:
        return self.layout.direction


def arrange(
    level: Sequence[str],
    nesting: Nesting,
    edges: Sequence[tuple[str, str]],
    boxes: Mapping[str, Box],
    captions: Mapping[str, Box],
    theme: Theme,
    spacing: Spacing,
    max_width: float,
    prefer: str,
    entered: frozenset[str] = frozenset(),
    depth: int = 0,
    centre: str = "",
) -> Arrangement:
    """Lay out one level, laying out any group in it first.

    The recursion is the whole design: a group is sized by arranging its own
    members, and is then just a node of that size to the level above.
    """
    inner: dict[str, Arrangement] = {}
    sizes: dict[str, tuple[float, float]] = {}
    pad = theme.box.padding
    for identifier in level:
        if identifier in nesting.groups:
            sub = arrange(
                nesting.members[identifier],
                nesting,
                edges,
                boxes,
                captions,
                theme,
                spacing,
                max_width - pad.horizontal * 2,
                prefer,
                entered,
                depth + 1,
                centre,
            )
            inner[identifier] = sub
            caption = captions.get(identifier)
            top, bottom = _insets(caption, theme, spacing, identifier in entered)
            sizes[identifier] = (
                max(
                    sub.width + pad.horizontal,
                    (caption.width + pad.horizontal) if caption else 0.0,
                ),
                sub.height + top + bottom,
            )
        else:
            box = boxes[identifier]
            sizes[identifier] = (box.width, box.height)

    here = frozenset(level)
    lifted: set[tuple[str, str]] = set()
    for source, target in edges:
        up_source = nesting.lift(source, here)
        up_target = nesting.lift(target, here)
        if up_source is not None and up_target is not None and up_source != up_target:
            lifted.add((up_source, up_target))

    layout = best_layout(
        LayeredEngine(spacing=spacing),
        [LayoutNode(id=i, width=sizes[i][0], height=sizes[i][1]) for i in level],
        [LayoutEdge(source=s, target=t) for s, t in sorted(lifted)],
        max_width=max_width,
        prefer=prefer,
        centre=centre,
    )

    places: dict[str, Placement] = {}
    frames: list[Frame] = []
    for identifier, place in layout.placements.items():
        if identifier not in inner:
            places[identifier] = place
            continue
        caption = captions.get(identifier)
        top, _ = _insets(caption, theme, spacing, identifier in entered)
        sub = inner[identifier]
        # The contents are centred in whatever width the engine gave the frame,
        # which is at least what they asked for and may be more once peers are
        # normalised. Centring rather than left-aligning keeps a group of two
        # looking deliberate inside a frame stretched to match a group of four.
        dx = place.x + (place.width - sub.width) / 2
        dy = place.y + top
        for member, inside in sub.places.items():
            places[member] = replace(inside, x=inside.x + dx, y=inside.y + dy)
        frames.extend(frame.moved(dx, dy) for frame in sub.frames)
        frames.append(
            Frame(
                id=identifier,
                x=place.x,
                y=place.y,
                width=place.width,
                height=place.height,
                # Top-left, at its own width, rather than centred across the
                # frame: a caption is a label *of* the container and not a title
                # *over* its contents, and the corner is the one part of a frame
                # an arrow arriving from above never wants.
                caption=(None if caption is None else caption.moved_to(place.x, place.y)),
                depth=depth,
            )
        )

    return Arrangement(layout=layout, places=places, frames=tuple(frames))


def crossed(edges: Sequence[tuple[str, str]], nesting: Nesting) -> frozenset[str]:
    """The groups some edge arrives *into* from outside.

    Entered, not merely crossed: an edge on its way out of a frame leaves from a
    box that is already inside it and needs no room at the top to do so. A frame
    nothing enters holds its contents tight under its caption, which is the
    common case and should not pay for the rare one.
    """

    def ancestors(identifier: str) -> set[str]:
        found: set[str] = set()
        current = nesting.parent.get(identifier)
        while current is not None:
            found.add(current)
            current = nesting.parent.get(current)
        return found

    boundaries: set[str] = set()
    for source, target in edges:
        boundaries |= ancestors(target) - ancestors(source)
    return frozenset(boundaries)


def _insets(
    caption: Box | None, theme: Theme, spacing: Spacing, entered: bool
) -> tuple[float, float]:
    """How much clear space a frame keeps above and below its contents.

    Below, the padding. Above, the caption — plus, for a frame something crosses
    into, a **rank gap**, which is this codebase's name for "enough room for an
    arrow to turn in". An edge arriving from outside has to get past the caption
    to reach the first box, and given only the padding the router arrives with a
    few units of straight line and refuses to draw a head on it: the right
    refusal, the wrong geometry to hand it. A frame nothing crosses does not pay
    for this, which is why a plain container is not mostly empty band.
    """
    if caption is None:
        return theme.box.padding.top, theme.box.padding.bottom
    room = spacing.rank_gap if entered else theme.box.padding.top
    return caption.height + room, theme.box.padding.bottom


def captions_for(
    document: Document, nesting: Nesting, theme: Theme, measurer: TextMeasurer, limit: float
) -> dict[str, Box]:
    """One sized caption per group that has text. A group may be silent."""
    return {
        group.id: size_box(
            group.text,
            theme=theme,
            measurer=measurer,
            role=GROUP_ROLE,
            level=GROUP_LEVEL,
            max_width=limit,
            shape="rect",
        )
        for group in document.groups
        if group.text and group.id in nesting.groups
    }


def caption_obstacle(frame: Frame) -> tuple[Obstacle, ...]:
    """The frame's caption text, as an obstacle for routing.

    A caption sits in the top-left corner of its frame and an edge arriving
    there goes straight through it, which is the "no line crosses text" rule
    broken by the one piece of text the frame owns. The caption occupies its own
    width and no more, so the rest of the top edge stays open for anything that
    needs to come in.
    """
    caption = frame.caption
    if caption is None:
        return ()
    return (
        Obstacle(
            f"{frame.id}:caption",
            x=caption.x,
            y=caption.y,
            width=caption.width,
            height=caption.height,
        ),
    )


def border_obstacles(frame: Frame, theme: Theme) -> tuple[Obstacle, ...]:
    """The four sides of a frame, as thin obstacles.

    For label placement, not for routing. A frame's *interior* must stay open —
    an edge between two boxes inside a group has to put its label in there with
    them — but its *border* must not have text sitting on it, which is the same
    rule that keeps a label off a box. Four thin rectangles say exactly that and
    nothing more.
    """
    thickness = theme.edge.clearance * 2
    half = thickness / 2
    return (
        Obstacle(
            f"{frame.id}:top", x=frame.x, y=frame.y - half, width=frame.width, height=thickness
        ),
        Obstacle(
            f"{frame.id}:bottom",
            x=frame.x,
            y=frame.bottom - half,
            width=frame.width,
            height=thickness,
        ),
        Obstacle(
            f"{frame.id}:left", x=frame.x - half, y=frame.y, width=thickness, height=frame.height
        ),
        Obstacle(
            f"{frame.id}:right",
            x=frame.right - half,
            y=frame.y,
            width=thickness,
            height=frame.height,
        ),
    )


def frame_primitives(frame: Frame, theme: Theme, measurer: TextMeasurer) -> tuple[Primitive, ...]:
    """The frame's outline, then its caption across the top of it."""
    outline: tuple[Primitive, ...] = (
        Rect(GROUP_ROLE, x=frame.x, y=frame.y, width=frame.width, height=frame.height),
    )
    if frame.caption is None:
        return outline
    return (*outline, *text_runs(frame.caption, theme, measurer))


__all__ = [
    "GROUP_LEVEL",
    "GROUP_ROLE",
    "Arrangement",
    "Frame",
    "Nesting",
    "arrange",
    "border_obstacles",
    "caption_obstacle",
    "captions_for",
    "frame_primitives",
    "nesting_of",
]
