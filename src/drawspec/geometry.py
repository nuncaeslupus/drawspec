"""Box geometry: size from measured text, centre vertically, normalise, fit.

Four decisions live here, and all four are ones an author working blind cannot
take.

**A box is as big as its text plus the theme's padding**, on all four sides. The
bottom margin is not the smallest value by accident: a starved one was the single
most repeated failure in the source review, so it is derived like the others
rather than left as whatever was left over.

**Text is centred from the font's ascent and descent**, not from half the type
size. Half the size is the approximation that leaves a box looking bottom-heavy,
and it is why a box of "ace" and a box of "Agile" would otherwise sit at
different heights.

**Peers are the same size.** Boxes that mean the same kind of thing are
normalised to one width and one height by `normalise`, and the text re-centres in
the larger box rather than staying where it was.

**Elastic fit is one factor for the whole diagram.** `fit` searches the theme's
band for the largest factor at which the content fits, and applies it through
`Theme.with_scale`, which scales all four type levels together. There is no path
here that can reach one level: scaling levels independently is how 51 of the
corpus's 87 diagrams ended up with a different type size in every element. When
nothing in the band fits — or the band's floor would take the body type below the
theme's legibility floor — this raises `FitError` and says restructure. It does
not keep shrinking.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from math import sqrt
from typing import Final

from drawspec.errors import FitError
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Padding, Theme

#: Granularity of the elastic-fit search. A hundredth of the type scale is finer
#: than a reader can see and coarse enough to keep the search deterministic —
#: which matters more, because the chosen factor is part of the output bytes.
FIT_STEP: Final = 0.01

_SQRT_HALF: Final = sqrt(0.5)

#: How many passes a shape's width/height fixed point is given before it is
#: called a failure to fit. Four is one more than any settling case observed.
_SHAPE_PASSES: Final = 4

#: How much wider than tall a box should be, when width is available to make it
#: so. Past this it is left alone; below it, `_widened` offers it more room.
#:
#: Two-and-a-bit is measured rather than chosen. Sweeping it across the
#: eighty-six corpus redraws: at 1.0 — "not actually taller than it is wide" —
#: four drawings improve; at 2.2, twenty-six do, saving sixty-six lines of text
#: with no box anywhere gaining one, and the tallest box in the corpus falls from
#: nine lines to four. Past 2.2 the gains keep coming but the bill arrives with
#: them: at 2.6 three drawings have to shrink their type to fit the wider boxes,
#: which is trading a complaint for the complaint underneath it.
MIN_ASPECT: Final = 2.2

#: How much of the offered width a widening step adds. Four steps to double.
_WIDEN_STEP: Final = 0.25


# ---------------------------------------------------------------------------
# Shapes whose usable span is narrower than their bounding box
# ---------------------------------------------------------------------------


def usable_span(
    shape: str, width: float, height: float, content_height: float | None = None
) -> tuple[float, float]:
    """The rectangle text may occupy inside `shape`, given its bounding box.

    Getting this wrong is how text ends up crossing a sloped side — a failure
    that looks like a rendering bug but is really a sizing one.

    A rect can use all of itself. Every other shape narrows away from its middle,
    and the rule that matters for all three of them is the same: **text only
    reaches the narrow part if it is tall enough to get there.** A short label in
    a diamond sits in the wide band across the middle, and sizing it against the
    diamond's largest inscribed rectangle — half the width — makes the box a third
    wider than it needs to be, for nothing.

    So each shape is solved at the text's own height:

    * A **pill**'s usable width is its flat span plus however far into the two
      semicircular caps the text's height allows.
    * A **diamond** of height `H` holding text of height `h` is `1 - h / H` of its
      width at the text's widest point.
    * An **ellipse** is `sqrt(1 - (h / H)^2)` of its width, by the same argument.

    Args:
        content_height: how tall the text is. When omitted, the answer is the
            largest inscribed rectangle — the conservative reading, for a caller
            that does not yet know what it is placing.

    Raises:
        KeyError: `shape` is not one drawspec draws.
    """
    if shape in ("rect", "none"):
        return width, height
    if shape == "pill":
        inner = height if content_height is None else min(content_height, height)
        radius = height / 2
        reach = sqrt(max(radius**2 - (inner / 2) ** 2, 0.0))
        return max(width - height + 2 * reach, 0.0), height
    if shape == "diamond":
        if content_height is None:
            return width / 2, height / 2
        ratio = min(content_height / height, 1.0) if height else 1.0
        return max(width * (1 - ratio), 0.0), height
    if shape == "ellipse":
        if content_height is None:
            return width * _SQRT_HALF, height * _SQRT_HALF
        ratio = min(content_height / height, 1.0) if height else 1.0
        return width * sqrt(max(1 - ratio**2, 0.0)), height
    raise KeyError(f"unknown shape {shape!r}")


def outer_size(
    shape: str, content_width: float, content_height: float, padding: Padding
) -> tuple[float, float]:
    """The bounding box `shape` needs to hold that content plus `padding`.

    The inverse of `usable_span`, which is asserted by a test rather than
    trusted: a sizing function and a fitting function that disagree would put
    text outside a shape by construction.

    Raises:
        KeyError: `shape` is not one drawspec draws.
    """
    width = content_width + padding.horizontal
    height = content_height + padding.vertical
    if shape in ("rect", "none"):
        return width, height
    if shape == "pill":
        # The inverse of `usable_span`'s pill case, solved for the bounding width.
        # The caps cost their own diameter less how far the text reaches into them.
        reach = sqrt(max((height / 2) ** 2 - (content_height / 2) ** 2, 0.0))
        return width + height - 2 * reach, height

    # A diamond and an ellipse keep the *height* the largest-inscribed-rectangle
    # reading gives them, and solve only the width at the text's own height. That
    # is where the saving is: a taller shape is a narrower one for the same text,
    # so shrinking the height as well would hand the width straight back.
    if shape == "diamond":
        outer_height = height * 2
        return width / (1 - content_height / outer_height), outer_height
    if shape == "ellipse":
        outer_height = height / _SQRT_HALF
        return width / sqrt(1 - (content_height / outer_height) ** 2), outer_height
    raise KeyError(f"unknown shape {shape!r}")


# ---------------------------------------------------------------------------
# The box
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Box:
    """A sized box with its text laid out inside it, in final coordinates."""

    role: str
    shape: str
    level: str
    block: TextBlock
    width: float
    height: float
    x: float = 0.0
    y: float = 0.0
    padding: Padding = field(default_factory=Padding)

    # -- the span text may occupy ----------------------------------------

    @property
    def _span(self) -> tuple[float, float]:
        """The rectangle this box's own text may occupy, centred in the box."""
        return usable_span(self.shape, self.width, self.height, self.block.height)

    @property
    def usable_left(self) -> float:
        return self.x + (self.width - self._span[0]) / 2

    @property
    def usable_right(self) -> float:
        return self.x + (self.width + self._span[0]) / 2

    @property
    def usable_top(self) -> float:
        return self.y + (self.height - self._span[1]) / 2

    @property
    def usable_bottom(self) -> float:
        return self.y + (self.height + self._span[1]) / 2

    @property
    def content_width(self) -> float:
        """The width text may use: the usable span less the horizontal padding."""
        return max(self.usable_right - self.usable_left - self.padding.horizontal, 0.0)

    @property
    def content_height(self) -> float:
        return max(self.usable_bottom - self.usable_top - self.padding.vertical, 0.0)

    # -- where the text actually sits -------------------------------------

    @property
    def _block_top(self) -> float:
        """The top of the text block, centred in the content area.

        The extra height a normalised box carries is split evenly above and
        below, which is what keeps a group of peers looking like peers.
        """
        content_top = self.usable_top + self.padding.top
        return content_top + (self.content_height - self.block.height) / 2

    def baselines(self) -> tuple[float, ...]:
        """The absolute y of every line's baseline, top to bottom."""
        return tuple(
            self._block_top + self.block.baseline(index) for index in range(len(self.block.lines))
        )

    def content_bounds(self) -> tuple[float, float, float, float]:
        """`(left, top, right, bottom)` of the ink, measured from the font.

        Vertically this is the first line's ascent to the last line's descent,
        not the block's slots — the slots are how the lines are spaced, the ink
        is what a reader sees touching an edge.
        """
        baselines = self.baselines()
        left = self.usable_left + self.padding.left
        if not baselines:
            return left, self._block_top, left, self._block_top
        return (
            left,
            baselines[0] - self.block.ascent,
            left + max(line.width for line in self.block.lines),
            baselines[-1] + self.block.descent,
        )

    # -- moves and resizes ------------------------------------------------

    def moved_to(self, x: float, y: float) -> Box:
        """This box with its top-left corner at `(x, y)`."""
        return replace(self, x=x, y=y)

    def resized(self, *, width: float | None = None, height: float | None = None) -> Box:
        """This box made larger. The text re-centres; it is not re-wrapped.

        Only used to grow a box to match its peers, which is why it does not
        re-wrap: a wider box could fit more words per line, but a group of peers
        whose line breaks moved when a *sibling* got longer would be worse than
        one with a little extra room.
        """
        return replace(
            self,
            width=self.width if width is None else max(width, self.width),
            height=self.height if height is None else max(height, self.height),
        )


def size_box(
    text: str,
    *,
    theme: Theme,
    measurer: TextMeasurer,
    role: str = "step",
    level: str = "body",
    max_width: float | None = None,
    shape: str | None = None,
    widen: float = 1.0,
) -> Box:
    """Size a box around `text`, derived from measurement and theme padding.

    Args:
        text: the words, possibly carrying inline spans.
        theme: supplies the padding, the type scale and the role's shape.
        measurer: measures against the theme's own font stacks.
        role: the semantic role, which decides the shape unless `shape` says
            otherwise.
        level: which of the four type levels the text is set at.
        max_width: the widest the box may be. Defaults to the theme's canvas
            width, which is the widest anything can be.
        shape: overrides the role's shape. For a family that draws its own
            outline — a pyramid level is a trapezoid and a ring is a circle,
            neither of which is a node shape — the shape used for *sizing* is the
            family's business, not the role's.
        widen: how far past `max_width` this box may go to stop being too
            vertical, as a multiple of it. The default of one is no widening,
            which is right wherever `max_width` is a *geometric* width — a
            column, a timeline's share of the axis — because exceeding it there
            is an overlap. A family whose limit is a soft share of the canvas
            passes more; see `MIN_ASPECT`.

    Raises:
        FitError: the text cannot be broken to fit `max_width`.
        KeyError: the theme declares no such role, or no such type level.
    """
    node_role = theme.roles[role]
    shape = node_role.shape if shape is None else shape
    limit = theme.canvas.width if max_width is None else max_width

    def at(width_limit: float) -> Box:
        block = _wrap_to(text, shape, width_limit, theme=theme, measurer=measurer, level=level)
        width, height = outer_size(shape, block.width, block.height, theme.box.padding)
        return Box(
            role=role,
            shape=shape,
            level=level,
            block=block,
            width=min(width, width_limit),
            height=height,
            padding=theme.box.padding,
        )

    return _widened(at, limit, widen, theme.canvas.width)


def _widened(at: Callable[[float], Box], limit: float, widen: float, ceiling: float) -> Box:
    """Offer a too-vertical box more width, while more width buys fewer lines.

    Every shape but a rect pays for its own outline out of the width it was
    offered: a pill's text may only use the flat span between its caps, so a
    taller pill is a *narrower* one, and wrapping into that narrower span makes
    it taller again. Left alone the fixed point in `_wrap_to` settles wherever
    that spiral stops — which for nine lines of text in a 240-wide allowance is a
    box 1.09 times wider than it is tall, and reads as a column of words.

    The allowance is the wrong thing to have been enforcing. It was chosen as a
    share of the canvas, to keep one node from eating a rank; a shape's own
    geometry is not that, and charging it to the same budget confuses "this box
    may not dominate the drawing" with "this box may not have caps".

    So the box is re-offered a wider allowance in steps, and each wider box is
    kept only if it needs **fewer lines** than the one before — width that buys
    nothing is not taken, so a short label stays exactly as narrow as its own
    text. It stops as soon as the box is at least as wide as it is tall, and
    never passes the canvas or the caller's `widen` multiple.

    A narrow offer that will not settle at all is a *reason* to widen rather than
    a failure: `FitError` from one offer is held and only raised if every offer
    raises. That case is not hypothetical — it is where the corpus's tall pills
    came from. The shape could not settle at a quarter-canvas, the whole diagram
    was shrunk a step to make it, and the pill settled at the smaller type as a
    nine-line column. Widening the one box that could not settle keeps the type
    where it was.
    """
    ceiling = min(limit * max(widen, 1.0), ceiling)
    offers = [limit]
    while offers[-1] < ceiling - 1e-9:
        offers.append(min(offers[-1] + limit * _WIDEN_STEP, ceiling))

    box: Box | None = None
    refusal: FitError | None = None
    for offered in offers:
        try:
            candidate = at(offered)
        except FitError as error:
            refusal = refusal or error
            continue
        if box is None or len(candidate.block.lines) < len(box.block.lines):
            box = candidate
        if box.width >= box.height * MIN_ASPECT:
            return box

    if box is None:
        raise refusal or FitError(f"no box fits a width of {limit:.1f}")
    return box


def _wrap_to(
    text: str,
    shape: str,
    limit: float,
    *,
    theme: Theme,
    measurer: TextMeasurer,
    level: str,
) -> TextBlock:
    """Wrap `text` to whatever width `shape` leaves inside a box of `limit`.

    Every shape but a rect has a usable width that depends on its own height, and
    its height depends on the line count, which depends on the width. So it is
    iterated to a fixed point rather than solved: each pass wraps to the width the
    previous pass's height leaves. The budget shrinks monotonically with the line
    count, so this either settles or runs out of width — and running out is a
    `FitError`, not a box that overflows.
    """
    padding = theme.box.padding

    def budget_for(content_height: float) -> float:
        box_height = outer_size(shape, 0.0, content_height, padding)[1]
        return usable_span(shape, limit, box_height, content_height)[0] - padding.horizontal

    if shape in ("rect", "none"):
        # A rect can use all of itself, so the first budget is the only budget.
        return wrap(
            text,
            _positive(limit - padding.horizontal, shape, limit),
            measurer,
            theme=theme,
            level=level,
        )

    block = wrap(
        text,
        _positive(limit - padding.horizontal, shape, limit),
        measurer,
        theme=theme,
        level=level,
    )
    for _ in range(_SHAPE_PASSES):
        candidate = wrap(
            text,
            _positive(budget_for(block.height), shape, limit),
            measurer,
            theme=theme,
            level=level,
        )
        if len(candidate.lines) == len(block.lines):
            return candidate
        block = candidate
    raise FitError(
        f"a {shape} of width {limit:.1f} cannot settle on a line count for this "
        f"text: each pass that adds a line narrows the span the shape leaves. "
        f"Restructure — a {shape} is for a short label."
    )


def _positive(budget: float, shape: str, limit: float) -> float:
    """A width budget, or a `FitError` naming the shape that ate it."""
    if budget <= 0:
        raise FitError(
            f"a {shape} of width {limit:.1f} leaves no room for text once the "
            f"theme's padding and the shape's own geometry are taken out. Give the "
            f"diagram more width, or a shape whose whole box is usable."
        )
    return budget


def normalise(boxes: Sequence[Box]) -> tuple[Box, ...]:
    """Grow every box in a group to the largest width and height among them.

    Boxes at the same level, representing the same kind of thing, are the same
    size — a rule the author does not have to state and could not enforce.
    """
    if not boxes:
        return ()
    width = max(item.width for item in boxes)
    height = max(item.height for item in boxes)
    return tuple(item.resized(width=width, height=height) for item in boxes)


# ---------------------------------------------------------------------------
# Elastic fit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fitted[T]:
    """The result of an elastic fit: the factor, the scaled theme, the content."""

    factor: float
    theme: Theme
    value: T


def candidate_factors(theme: Theme) -> tuple[float, ...]:
    """Every factor to try, largest first.

    Bounded below by the theme's `scale_min` *and* by its legibility floor: a
    factor that would take the body type below `min_legible_size` is not a
    smaller diagram, it is an unreadable one, so it is never offered.
    """
    floor = theme.fit.scale_min
    legible = theme.canvas.min_legible_size / theme.scale["body"]
    lower = max(floor, legible)

    factors: list[float] = []
    steps = round((theme.fit.scale_max - lower) / FIT_STEP)
    for step in range(max(steps, 0) + 1):
        factor = round(theme.fit.scale_max - step * FIT_STEP, 6)
        if factor < lower - 1e-9:
            break
        factors.append(factor)
    return tuple(factors)


def fit[T](theme: Theme, attempt: Callable[[Theme], T]) -> Fitted[T]:
    """Find the largest factor in the theme's band at which `attempt` succeeds.

    `attempt` is given a scaled theme and either returns the laid-out content or
    raises `FitError`. Every other exception passes straight through: a bug in a
    rendering family must not be mistaken for content that will not fit.

    The factor is applied through `Theme.with_scale`, so all four type levels
    move together. That is the whole point — the alternative reintroduces the
    corpus's most common failure.

    Raises:
        FitError: nothing in the band fits, or the band is empty because its
            floor is below the theme's legibility floor.
    """
    factors = candidate_factors(theme)
    if not factors:
        raise FitError(
            f"theme {theme.name!r} cannot fit anything: at scale_max "
            f"({theme.fit.scale_max}) the body type is "
            f"{theme.fit.scale_max * theme.scale['body']:.1f}, below the theme's "
            f"min_legible_size of {theme.canvas.min_legible_size}. Raise the type "
            f"scale or lower min_legible_size — the band as declared has no "
            f"legible size in it."
        )

    last: FitError | None = None
    for factor in factors:
        scaled = theme.with_scale(factor)
        try:
            return Fitted(factor=factor, theme=scaled, value=attempt(scaled))
        except FitError as error:
            last = error

    raise FitError(
        f"the content does not fit at any factor in this theme's band "
        f"[{factors[-1]}, {factors[0]}] — the smallest tried put the body type at "
        f"{factors[-1] * theme.scale['body']:.1f}, and scale_min is "
        f"{theme.fit.scale_min} with a legibility floor of "
        f"{theme.canvas.min_legible_size}. drawspec will not shrink further: "
        f"restructure the diagram — usually turning it vertical, splitting it, or "
        f"shortening the longest label. The last failure was: {last}"
    )


__all__ = [
    "FIT_STEP",
    "Box",
    "Fitted",
    "candidate_factors",
    "fit",
    "normalise",
    "outer_size",
    "size_box",
    "usable_span",
]
