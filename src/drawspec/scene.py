"""The `Scene`: where every rendering family converges.

This is the load-bearing seam. Graph kinds, grid kinds, shape kinds and charts
all produce the same thing — a flat list of primitives in final coordinates,
each tagged with a semantic role, carrying **no styling at all**. Styling is
applied once, by `drawspec.emit`, from the theme.

That is why "SVG safe to paste inline into Markdown" is satisfied in one file
rather than four, and why adding a fifth rendering family later costs nothing in
embedding-safety work: a new family produces primitives, and the invariants are
already enforced downstream of it.

A primitive therefore has no colour, no stroke width, no font size and no dash
pattern. It has geometry and a role. If you find yourself wanting to add an
appearance field here, the decision belongs in the theme.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

#: Where a text run is anchored horizontally, in SVG's own vocabulary.
TEXT_ANCHORS: Final = ("start", "middle", "end")

#: Type weights a text run may take. Bold means something or is not used, so
#: there are two, not a range.
TEXT_WEIGHTS: Final = ("normal", "bold")


@dataclass(frozen=True)
class Primitive:
    """Base for everything a scene contains.

    `role` names a semantic role the theme declares — a node role for a shape, an
    edge role for a connector. The emitter refuses a role the theme does not
    declare, because an unstylable primitive is a programming error rather than
    something to guess at.
    """

    role: str


@dataclass(frozen=True)
class Rect(Primitive):
    """An axis-aligned box in final coordinates.

    Corner treatment is not a field: the theme picks one radius and applies it to
    every box, and a `pill` role is drawn as a fully rounded rect by the emitter.
    """

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


@dataclass(frozen=True)
class Ellipse(Primitive):
    """An ellipse in final coordinates — a ring, a circle, a rounded node."""

    cx: float = 0.0
    cy: float = 0.0
    rx: float = 0.0
    ry: float = 0.0


@dataclass(frozen=True)
class Polygon(Primitive):
    """A closed figure: a diamond, a pyramid level, an arrow head."""

    points: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Path(Primitive):
    """An open or closed run of straight segments — an edge route, an axis.

    Points rather than a `d` string: the primitive holds geometry, and turning
    geometry into SVG is the emitter's job. Orthogonal routing means these are
    axis-aligned in practice, but the primitive does not enforce that — the
    routing stage owns that invariant.
    """

    points: tuple[tuple[float, float], ...] = ()
    closed: bool = False


@dataclass(frozen=True)
class TextRun(Primitive):
    """One run of text on one line, positioned by its baseline.

    `level` selects a size from the theme's four-step scale and `font` selects a
    family stack; neither is a size or a family, because an element never names
    its own type. A run is the unit an inline span produces, which is how
    `` `code` `` becomes the monospace font and `**bold**` becomes the bold
    weight without either being a typographic instruction from the author.
    """

    x: float = 0.0
    y: float = 0.0
    text: str = ""
    level: str = "body"
    font: str = "sans"
    anchor: str = "start"
    weight: str = "normal"
    rotate: float = 0.0
    """Rotation in degrees about (x, y) — a chart's vertical axis label, and
    nothing else so far."""


@dataclass(frozen=True)
class Scene:
    """A complete drawing: primitives in final coordinates, plus its extents.

    `title` and `description` are the accessible name and description; the
    emitter puts them in `<title>` and `<desc>` and points the root element at
    them, so a diagram is readable by something that cannot see it.
    """

    width: float
    height: float
    primitives: tuple[Primitive, ...] = ()
    title: str = ""
    description: str = ""
    metadata: tuple[tuple[str, str], ...] = field(default=())
    """Sorted key/value pairs a family may attach for tests and diagnostics.
    Never emitted, so it cannot affect the output bytes."""

    def roles(self) -> tuple[str, ...]:
        """Every role this scene uses, sorted — the set the theme must declare."""
        return tuple(sorted({primitive.role for primitive in self.primitives}))


__all__ = [
    "TEXT_ANCHORS",
    "TEXT_WEIGHTS",
    "Ellipse",
    "Path",
    "Polygon",
    "Primitive",
    "Rect",
    "Scene",
    "TextRun",
]
