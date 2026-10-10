"""The theme: everything about how a diagram looks, and nothing about a subject.

A theme is the boundary that keeps drawspec generic. A consumer's entire style
guide has to reduce to one of these files (`docs/theme-requirements.md` is the
worked example); any requirement that cannot be expressed here is a design smell
to fix, not a special case to add.

Three things are worth knowing before reading further.

**Roles are semantic and their vocabularies are closed.** An author names
`decision` or `link`; the theme decides that a decision is a diamond and a link
is a line with no head. `NODE_ROLES` and `EDGE_ROLES` are the v1 vocabulary, and
a theme may neither omit a role (nothing would style it) nor invent one (no
document could name it, so it would be a typo that loads).

**A theme is a diff.** `load_theme` merges the file over the bundled default, so
a consumer theme declares only what it changes.

**The greyscale invariant is checked here, at load time.** Colour is optional;
legibility without it is not. Two roles that differ only by colour are rejected
before any diagram is drawn — `greyscale_ambiguous_role_pairs == 0` is a
property of the theme, so it is checked once per theme rather than once per
review.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from itertools import combinations, pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from drawspec.errors import ThemeError

#: The theme schema version this module reads.
THEME_VERSION: Final = 1

#: Semantic node roles. The closed vocabulary a document's `role` field draws
#: from — see specification §5.1.
#: `io`, `subroutine` and `store` are the flowchart symbols that carry meaning
#: across standards (ISO 5807, DFDs, Mermaid): data in or out, a process defined
#: elsewhere, and where data rests. The theme draws every role, but a document may
#: name those three only where a box is a step of a process (`schema.SHAPED_ROLES`).
NODE_ROLES: Final = (
    "start",
    "step",
    "decision",
    "terminal",
    "emphasis",
    "note",
    "group",
    "io",
    "subroutine",
    "store",
)

#: Semantic edge roles. `link` is how "merely associated" is said, and `aside`
#: how "loosely associated, and in no direction" is: dashed and headless, which
#: is a pairing the other six could not make. `link` has no head but is solid,
#: and `weak` is dashed but carries one, so an author annotating a diagram with a
#: soft undirected association had to misstate one or the other.
#:
#: `inherits` and `realizes` are the theme's too — it draws every role — but a
#: document may name them only in an `entities` diagram: which roles a kind
#: accepts is the schema's decision, per kind (`schema.GRAPH_EDGE_ROLES`).
EDGE_ROLES: Final = (
    "flow",
    "link",
    "exchange",
    "weak",
    "owns",
    "strong",
    "aside",
    "inherits",
    "realizes",
)

#: Shapes a node role may take.
#: `parallelogram` slants its sides, `subroutine` is a box with doubled vertical
#: sides, and `cylinder` is a drum with an elliptical lid.
NODE_SHAPES: Final = (
    "rect",
    "pill",
    "diamond",
    "ellipse",
    "parallelogram",
    "subroutine",
    "cylinder",
    "none",
)

#: Fill treatments. A non-colour channel, so it counts toward greyscale safety.
FILL_PATTERNS: Final = ("none", "solid", "hatch", "dots", "cross", "grid")

#: End treatments an edge role may take. Closed, and it lives in the theme, so a
#: document stays readable when the theme changes.
#: `triangle` is hollow: the shaft stops at its base, so it reads as an outline
#: and not as a filled arrow head — the mark a class diagram draws for "is a".
EDGE_HEADS: Final = ("arrow", "open", "diamond", "circle", "bar", "triangle", "none")

#: The four type levels. One size per level, and no element names its own.
TYPE_LEVELS: Final = ("title", "heading", "body", "label")

#: Font roles a theme declares stacks for.
FONT_ROLES: Final = ("sans", "serif", "mono")

#: Colour keywords that are legal anywhere a colour is, and carry no luminance.
COLOUR_KEYWORDS: Final = ("currentColor", "none")

#: Minimum relative-luminance difference for two colours to survive greyscale.
LUMINANCE_DELTA: Final = 0.25

#: How many steps `[mark] ramp` must hold: one per step of the longest `scale` a
#: `matrix` may declare, so every document draws under every theme.
RAMP_STEPS: Final = 5

#: The least two neighbouring ramp steps may differ by, in ink coverage — which
#: is greyscale lightness, since a step is the page's ink laid down at that
#: strength. Below it, two buckets side by side read as one tone. The first step
#: is held to it as well, measured from the blank of an unfilled cell.
RAMP_CONTRAST: Final = 0.08

#: The heaviest a ramp step may be. Text sits on these cells, in the same ink as
#: the tone, so the heavier the step the less the label stands out — on both
#: pages. On white, half the ink still leaves a black label over 5:1; on a dark
#: page the ink is light and a heavier step is a *lighter* cell, and past 0.4 a
#: light label on it drops under 4.5:1 against `#121212`.
RAMP_CEILING: Final = 0.4

_THEMES_DIR: Final = Path(__file__).resolve().parent / "themes"

#: The theme used when none is named.
DEFAULT_THEME_PATH: Final = _THEMES_DIR / "default.toml"


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------


def relative_luminance(colour: str) -> float | None:
    """WCAG relative luminance of `colour`, or None if it has none to compute.

    `currentColor` inherits from the page and `none` is not drawn, so neither
    has a luminance — which is why two roles that both use one cannot rely on
    colour to tell themselves apart.
    """
    if not colour.startswith("#"):
        return None
    digits = colour[1:]
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    channels = [int(digits[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    """WCAG contrast ratio between two hex colours, from 1 to 21."""
    one = relative_luminance(first) or 0.0
    two = relative_luminance(second) or 0.0
    return (max(one, two) + 0.05) / (min(one, two) + 0.05)


def _colour(value: object, where: str) -> str:
    """Validate and normalise one colour, so each has exactly one spelling."""
    if not isinstance(value, str):
        raise ThemeError(f"{where}: expected a colour string, got {value!r}")
    if value in COLOUR_KEYWORDS:
        return value
    text = value.strip()
    digits = text[1:]
    if (
        text.startswith("#")
        and len(digits) in (3, 6)
        and all(digit in "0123456789abcdefABCDEF" for digit in digits)
    ):
        if len(digits) == 3:
            digits = "".join(digit * 2 for digit in digits)
        return "#" + digits.lower()
    raise ThemeError(
        f"{where}: {value!r} is not a colour drawspec accepts. Use a hex value "
        f"(#rgb or #rrggbb), {', '.join(COLOUR_KEYWORDS)}."
    )


def _dash(value: object, where: str) -> str:
    """Validate a dash pattern: `none`, or positive numbers separated by spaces."""
    if not isinstance(value, str):
        raise ThemeError(f"{where}: expected a dash pattern string, got {value!r}")
    if value == "none":
        return value
    parts = value.split()
    if not parts:
        raise ThemeError(f'{where}: dash pattern is empty; use "none" for a solid line')
    for part in parts:
        try:
            length = float(part)
        except ValueError:
            raise ThemeError(f"{where}: dash pattern {value!r} is not a list of numbers") from None
        if length <= 0:
            raise ThemeError(f"{where}: dash pattern {value!r} has a non-positive length")
    return " ".join(parts)


def _number(value: object, where: str, *, positive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ThemeError(f"{where}: expected a number, got {value!r}")
    number = float(value)
    if positive and number <= 0:
        raise ThemeError(f"{where}: expected a positive number, got {number}")
    return number


def _margin(mapping: Mapping[str, Any], width: float) -> float:
    """`[canvas] margin`, checked against the drawing it goes around.

    Zero is allowed and means *flush*, which is a real house style: a page that
    pads its own figures wants the drawing to end where its ink does. So the
    usual `positive=True` would be wrong here, and this is the check instead.

    A margin wider than the drawing it frames is a figure that is mostly frame.
    Nothing breaks — it is added around the width rather than taken out of it, so
    every document still draws — but it is far likelier to be a unit mistake than
    a house style, and a theme is read once and used everywhere.
    """
    margin = _number(mapping.get("margin", 12.0), "[canvas] margin", positive=False)
    if margin < 0:
        raise ThemeError(f"[canvas] margin: expected zero or a positive number, got {margin}")
    if margin * 2 >= width:
        raise ThemeError(
            f"[canvas] margin: {margin} on each side of a {width} drawing is more frame "
            f"than figure. The margin goes around [canvas] width, not inside it."
        )
    return margin


def _choice(value: object, allowed: tuple[str, ...], where: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ThemeError(f"{where}: {value!r} is not one of {', '.join(allowed)}")
    return value


def _section(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = mapping.get(key, {})
    if not isinstance(value, Mapping):
        raise ThemeError(f"[{key}]: expected a table, got {value!r}")
    return value


def _reject_unknown(mapping: Mapping[str, Any], allowed: Iterable[str], where: str) -> None:
    """A silently ignored key is a setting the author believes they made."""
    unknown = sorted(set(mapping) - set(allowed))
    if unknown:
        raise ThemeError(
            f"{where}: unknown key{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(repr(key) for key in unknown)}. Known keys: "
            f"{', '.join(sorted(allowed))}."
        )


# ---------------------------------------------------------------------------
# The pieces
# ---------------------------------------------------------------------------


#: How a diagram's canvas relates to the drawing inside it.
WIDTH_MODES: Final = ("fixed", "ink")

#: What a theme may do to the first paragraph of a two-part label.
LEAD_TREATMENTS: Final = ("bold", "plain", "rule")

#: What a standalone sheet may have ruled on its ground.
SHEET_PATTERNS: Final = ("none", "grid")

#: How a standalone sheet may be framed.
SHEET_BORDERS: Final = ("none", "zoned")

#: WCAG 2.2's contrast floors: text (1.4.3) and the parts of a graphic (1.4.11).
TEXT_CONTRAST: Final = 4.5
GRAPHIC_CONTRAST: Final = 3.0

#: Where a diagram-level caption sits relative to the drawing.
CAPTION_POSITIONS: Final = ("below", "above")

#: Which way a funnel narrows.
FUNNEL_DIRECTIONS: Final = ("down", "right")

#: How an edge role's lines are drawn between two boxes.
EDGE_ROUTINGS: Final = ("orthogonal", "direct")


@dataclass(frozen=True)
class Canvas:
    """The one width every diagram is drawn to, and the legibility floor."""

    width: float = 640.0
    """The canvas every diagram is drawn to, in user units.

    It belongs to the theme rather than to a document because that is what makes
    two diagrams on one page the same type size at the same column width.
    """

    width_mode: str = "fixed"
    """Whether a drawing narrower than `width` keeps the canvas or is cropped to it.

    `fixed` — the canvas is always `width` and a narrow drawing is centred in it.
    `ink` — the canvas is the bounds of what was drawn.

    This is the setting that makes type sizes comparable *between* diagrams, and
    it is the whole reason `width` is a theme value rather than a per-diagram one.
    Under `ink`, a five-box flow chart 360 wide and an eleven-box tree 600 wide
    are two different canvases; drop both into a page at the same column width
    and the viewer scales the first by 1.7 and the second by 1.03, so an
    eleven-point label is read at eighteen points in one and eleven in the other.
    Nothing inside drawspec is wrong in that picture — the *page* did the
    damage — and no invariant here could catch it, because each diagram is
    internally perfect. Keeping the canvas fixed spends empty margin to buy one
    type size across a document, which is the trade the corpus asks for: a
    different size in every element was its most repeated complaint.
    """

    margin: float = 12.0
    """The channel of blank between the drawing and the edge of the canvas.

    One number, applied once, on all four sides — which is the point. Before it
    existed there was no outer margin in the theme at all: `emit` set the
    `viewBox` to the bounds of the ink and every family then added whatever
    gutter it happened to add, so the same theme framed a `flow` in 24 units, a
    `cycle` in 10, and a `stack` in none. Put a timeline above a flow chart on one
    page — which a set of course notes does on most of them — and the first
    bleeds to the edge beside the second's quarter-inch of white. Nothing clipped
    and nothing collided; they were simply not framed alike, and a theme had no
    way to say they should be.

    It is the same idea as `[box] padding` one level out: the gap a box gives its
    own text, the figure gives the page. The default is that padding's side value
    for exactly that reason. A page that supplies its own figure padding sets this
    to `0` and gets a drawing flush to its ink.

    It sits **around** `width`, which therefore keeps meaning the width of the
    drawing: the emitted canvas is `width + margin * 2`, the same for every kind,
    so two diagrams on one page are still one width. Set `width` to the column
    less twice this to fill a measure exactly. Taking it out of `width` instead
    would charge every family's layout budget for the frame — and a drawing
    already near the width its own content demands would stop fitting because the
    theme grew a margin, which is not a thing a margin should be able to do.
    """

    min_legible_size: float = 9.0
    """The floor the fit band may not push type below.

    Content that cannot be made to fit above it is a `FitError` — a refusal whose
    message is the product — and never a smaller size nobody can read.
    """

    caption: str = "below"
    """Where a document's `caption` sits: `below` the drawing, or `above` it.

    The author says a line of text belongs to the whole diagram; where that puts
    it on the page is appearance, and appearance is the theme's. A house style
    that runs figure captions above its figures sets this once rather than in
    every document.
    """

    ink: str = "#1a1a1a"
    """What `currentColor` resolves to in the `standalone` profile.

    A linked `.svg` or a PDF conversion has nothing to inherit from, so the ink
    has to be stated somewhere; stating it here keeps it a theme decision rather
    than a converter default.
    """

    ground: str = "none"
    """The sheet's colour behind the drawing, in the `standalone` profile and PNG.

    `none` draws no ground, and the drawing sits on whatever it is put on. Like
    `ink`, the `inline` profile ignores it: an inline drawing is on the page's own
    background, and a coloured rectangle pasted into somebody else's document is
    not a figure. A ground is checked when the theme loads: `ink` must read on it
    as text (4.5:1) and every other colour the theme declares as a line (3:1).
    """

    pattern: str = "none"
    """What is ruled on the ground: `none`, or a fine drafting `grid`. Standalone only."""

    border: str = "none"
    """The sheet's frame: `none`, or `zoned` — a double border with zone numbers
    and letters, centring arrows and registration marks. Standalone only.

    The canvas grows to hold it: the drawing is moved inside the border, never
    drawn under it, and every diagram in one theme still comes out one width.
    """

    title_block: bool = False
    """Whether to draw an engineering title block below the drawing. Standalone only.

    It is filled from the document: its `title` (or its kind, when it has none),
    a drawing number derived from its content, its kind, the size of the
    drawing, and its format `version`. It takes a strip of its own under the
    drawing, so it can never cover any of it.
    """

    rule: str = ""
    """The colour of the grid and of the sheet's quiet lettering — zone letters and
    the title block's field names. Empty means `ink`."""

    accent: str = ""
    """The colour of the registration marks and the drawing number. Empty means `ink`."""

    @property
    def sheet(self) -> bool:
        """True when the standalone canvas has any furniture to draw."""
        return (
            self.ground != "none"
            or self.pattern != "none"
            or self.border != "none"
            or self.title_block
        )

    @property
    def sheet_colours(self) -> tuple[str, ...]:
        """Every colour the sheet paints, `none` aside, ground first."""
        colours = (self.ground, self.rule or self.ink, self.accent or self.ink)
        return tuple(colour for colour in colours if colour != "none")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> Canvas:
        _reject_unknown(
            mapping,
            (
                "width",
                "width_mode",
                "margin",
                "min_legible_size",
                "caption",
                "ink",
                "ground",
                "pattern",
                "border",
                "title_block",
                "rule",
                "accent",
            ),
            "[canvas]",
        )
        title_block = mapping.get("title_block", False)
        if not isinstance(title_block, bool):
            raise ThemeError(f"[canvas] title_block: expected true or false, got {title_block!r}")
        ground = _colour(mapping.get("ground", "none"), "[canvas] ground")
        if ground == "currentColor":
            raise ThemeError(
                "[canvas] ground: 'currentColor' is the ink, and ink on a ground of "
                "itself is a blank sheet. Name a colour, or 'none' for no ground."
            )
        return cls(
            width=_number(mapping.get("width", 640.0), "[canvas] width"),
            width_mode=_choice(
                mapping.get("width_mode", "fixed"), WIDTH_MODES, "[canvas] width_mode"
            ),
            margin=_margin(mapping, _number(mapping.get("width", 640.0), "[canvas] width")),
            min_legible_size=_number(
                mapping.get("min_legible_size", 9.0), "[canvas] min_legible_size"
            ),
            caption=_choice(mapping.get("caption", "below"), CAPTION_POSITIONS, "[canvas] caption"),
            ink=_colour(mapping.get("ink", "#1a1a1a"), "[canvas] ink"),
            ground=ground,
            pattern=_choice(mapping.get("pattern", "none"), SHEET_PATTERNS, "[canvas] pattern"),
            border=_choice(mapping.get("border", "none"), SHEET_BORDERS, "[canvas] border"),
            title_block=title_block,
            rule=_sheet_colour(mapping.get("rule", ""), "[canvas] rule"),
            accent=_sheet_colour(mapping.get("accent", ""), "[canvas] accent"),
        )


def _sheet_colour(value: object, where: str) -> str:
    """A sheet colour: empty for the ink, or a hex value — never a keyword.

    `currentColor` would be the ink anyway, said less plainly, and `none` would
    be furniture drawn in nothing.
    """
    if value == "":
        return ""
    colour = _colour(value, where)
    if not colour.startswith("#"):
        raise ThemeError(f"{where}: expected a hex colour, or empty for the ink; got {value!r}")
    return colour


@dataclass(frozen=True)
class FontStacks:
    """The families to measure and to name in the output, in preference order."""

    sans: tuple[str, ...] = ("sans-serif",)
    """The families measured for ordinary text, in preference order.

    Put the family the *page* is set in first: the SVG inherits the page's font
    stack, so measuring a different family is what makes a tight box overflow.
    Naming a family that is not installed is not an error — drawspec substitutes
    and says so.
    """

    serif: tuple[str, ...] = ("serif",)
    """The families for the serif role, in preference order."""

    mono: tuple[str, ...] = ("monospace",)
    """The families for `code` spans, in preference order."""

    default: str = "sans"
    """Which of the three roles text takes when it asks for none."""

    def stacks(self) -> Mapping[str, tuple[str, ...]]:
        """The mapping `TextMeasurer` takes — one source of truth for both."""
        return MappingProxyType({"sans": self.sans, "serif": self.serif, "mono": self.mono})

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FontStacks:
        _reject_unknown(mapping, (*FONT_ROLES, "default"), "[font]")
        stacks: dict[str, tuple[str, ...]] = {}
        for role in FONT_ROLES:
            value = mapping.get(role)
            if value is None:
                continue
            if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
                raise ThemeError(f"[font] {role}: expected a list of family names, got {value!r}")
            if not value:
                raise ThemeError(f"[font] {role}: the family stack is empty")
            stacks[role] = tuple(value)
        default = mapping.get("default", "sans")
        if default not in FONT_ROLES:
            raise ThemeError(f"[font] default: {default!r} is not one of {', '.join(FONT_ROLES)}")
        return cls(
            sans=stacks.get("sans", cls.sans),
            serif=stacks.get("serif", cls.serif),
            mono=stacks.get("mono", cls.mono),
            default=default,
        )


@dataclass(frozen=True)
class TypeScale:
    """One size per level. There is no API for scaling a single level.

    `scaled` is the only way to change these numbers, and it multiplies all four
    at once. Scaling levels independently is how a drawing ends up with a
    different size in every element — the corpus's most common failure — so the
    uniform factor is structural rather than a convention.
    """

    title: float = 15.0
    """The diagram's own title."""

    heading: float = 13.0
    """A box's heading — the first line of a node that has more than one."""

    body: float = 11.0
    """Ordinary text inside a box. The size a diagram is mostly read at."""

    label: float = 10.0
    """Edge labels, axis ticks, and the asides beside an entry."""

    def scaled(self, factor: float) -> TypeScale:
        """Every level multiplied by `factor`, preserving the ratios exactly."""
        if factor <= 0:
            raise ValueError(f"scale factor must be positive, got {factor!r}")
        return TypeScale(
            title=self.title * factor,
            heading=self.heading * factor,
            body=self.body * factor,
            label=self.label * factor,
        )

    def __getitem__(self, level: str) -> float:
        if level not in TYPE_LEVELS:
            raise KeyError(f"unknown type level {level!r}; expected {', '.join(TYPE_LEVELS)}")
        return float(getattr(self, level))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> TypeScale:
        _reject_unknown(mapping, TYPE_LEVELS, "[scale]")
        defaults = cls()
        return cls(
            **{
                level: _number(mapping.get(level, getattr(defaults, level)), f"[scale] {level}")
                for level in TYPE_LEVELS
            }
        )


@dataclass(frozen=True)
class FitBand:
    """How far the whole type scale may stretch to make a document fit."""

    scale_min: float = 0.85
    """How far the whole scale may shrink. One factor, applied to all four levels.

    Shrinking every level together preserves the hierarchy exactly, so a tight
    diagram never gains a type size its neighbours do not have.
    """

    scale_max: float = 1.0
    """How far it may grow. `1.0` means shrink to fit, never grow.

    Growing would trade away the comparability `[canvas] width` is there to buy.
    """

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FitBand:
        _reject_unknown(mapping, ("scale_min", "scale_max"), "[fit]")
        band = cls(
            scale_min=_number(mapping.get("scale_min", 0.85), "[fit] scale_min"),
            scale_max=_number(mapping.get("scale_max", 1.0), "[fit] scale_max"),
        )
        if band.scale_min > band.scale_max:
            raise ThemeError(
                f"[fit] scale_min ({band.scale_min}) is above scale_max ({band.scale_max}); "
                f"the band is empty, so nothing could ever fit."
            )
        return band


@dataclass(frozen=True)
class Padding:
    """Inner box margin, in CSS order."""

    top: float = 10.0
    right: float = 12.0
    bottom: float = 12.0
    left: float = 12.0

    @property
    def horizontal(self) -> float:
        return self.left + self.right

    @property
    def vertical(self) -> float:
        return self.top + self.bottom


@dataclass(frozen=True)
class BoxStyle:
    """Box geometry constants: margin, line spacing, corner treatment."""

    padding: Padding = Padding()
    """Space between a box's text and its border, as `[top, right, bottom, left]`.

    The bottom is not the smallest value by accident: a starved bottom margin was
    the single most repeated failure in the corpus.
    """

    line_height: float = 1.35
    """Baseline-to-baseline distance, as a multiple of the type size."""

    corner_radius: float = 4.0
    """Corner rounding for a `rect`. Zero draws square corners."""

    lead: str = "bold"
    """How the first paragraph of a label with more than one is set.

    A label often has a lead and a detail — *Digitització*, and then what
    digitising means. Written as one paragraph the two run together and the
    author reaches for punctuation to separate them, which is how eighty-nine
    corpus redraws ended up with an em dash in the middle of a box; the reviewer
    asked for that back as two levels of text, "just changing font size or
    boldness or whatever, as in the original".

    So a blank-free newline in `text` is the author saying *these are two
    things*, and this setting is the theme saying what separates them. `bold`
    sets the lead in the bold weight; `plain` leaves it alone, which is the theme
    for a document whose labels are already emphatic enough; `rule` draws a line
    across the text column between the two, in the box's own ink.

    `rule` makes a box read as a **compartment** — a name over what belongs to
    it, which is how a class, a record or a component is drawn by hand, and it is
    also the cheapest honest place to put *who performs this step* without
    spending a role on it. It applies inside a box and nowhere else: a caption, a
    band's name and a tick label have no column for a line to cross, so there the
    rule would be a mark hanging in the white. The band it needs is `padding.top`,
    spent half above the line and half below, and it is reserved when the text is
    measured rather than added when it is drawn — a rule a box did not count is a
    rule through a word.

    One treatment at a time, and that is on purpose: `bold` *and* `rule` would
    say the same thing twice, which is the redundancy the greyscale rule already
    forbids between two roles.

    Weight rather than size on purpose: one advance is used for every line in a
    block, and a block whose first line was set larger would either space
    unevenly or need a second advance — a change to what a text block *is*, for
    a distinction the weight already carries.
    """

    rise: float = 2.0
    """How much taller the last column of a rising series is than the first.

    A `columns` document with `rise` says the series ascends; this says by how
    much, so the author never writes a height and cannot get one wrong. The
    shortest column is whatever its own text needs, so every label fits whatever
    this is set to, and the rest are spread evenly up to this multiple of it.

    Two, and not the five the hand-drawn originals reached, because the ascent
    has to read as *ascending* and not as *a chart*: at five the first column is
    a sliver holding a full label and the drawing turns into a bar chart with no
    axis, which is a claim about quantity that an ordinal scale does not make.
    A page that wants the steeper look raises it.
    """

    widen_steps: int = 1
    """How far past the aspect floor a box may keep taking width to shed a line.

    A box is offered more width in steps while each step buys it a line, and it
    stops once it is `MIN_ASPECT` times wider than tall. That floor turned out to
    stop it too early — *"a wider round box would be even better"*, *"if even
    wider, text would fit better"*, *"same, wider boxes → less lines"*, three
    drawings in one round — so this is how many further paying steps it may take.

    It is a small number and not a large one because width is shared: a rank is
    as wide as the boxes in it, so a box taking width it barely needs takes it
    from its neighbours and the drawing stops fitting the canvas. drawspec tries
    the theme's number first and falls back to `0` for a document that will not
    fit with it, so this is the generosity a drawing gets *when there is room*.
    """

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> BoxStyle:
        _reject_unknown(
            mapping,
            ("padding", "line_height", "corner_radius", "lead", "widen_steps", "rise"),
            "[box]",
        )
        defaults = cls()
        padding = defaults.padding
        if "padding" in mapping:
            values = mapping["padding"]
            if not isinstance(values, list) or len(values) != 4:
                raise ThemeError(
                    f"[box] padding: expected four numbers "
                    f"[top, right, bottom, left], got {values!r}"
                )
            top, right, bottom, left = (
                _number(value, f"[box] padding[{index}]", positive=False)
                for index, value in enumerate(values)
            )
            padding = Padding(top=top, right=right, bottom=bottom, left=left)
        return cls(
            padding=padding,
            line_height=_number(
                mapping.get("line_height", defaults.line_height), "[box] line_height"
            ),
            corner_radius=_number(
                mapping.get("corner_radius", defaults.corner_radius),
                "[box] corner_radius",
                positive=False,
            ),
            lead=_choice(mapping.get("lead", defaults.lead), LEAD_TREATMENTS, "[box] lead"),
            widen_steps=int(
                _number(
                    mapping.get("widen_steps", defaults.widen_steps),
                    "[box] widen_steps",
                    positive=False,
                )
            ),
            rise=_number(mapping.get("rise", defaults.rise), "[box] rise"),
        )


@dataclass(frozen=True)
class EdgeStyle:
    """Line constants shared by every edge role."""

    stroke_width: float = 1.5
    """The default line weight. An edge role may override it."""

    min_shaft_length: float = 16.0
    """The shortest visible run of line an arrow may have.

    An arrow with no visible shaft is not an arrow. This is a layout constraint
    rather than a suggestion: it can force extra rank separation.
    """

    head_length: float = 7.0
    """How long an arrow head is drawn, before it is scaled to its own shaft.

    Sized against the *type*, not against the line: a head is read beside the
    labels around it, and one at half a capital's height reads as a line that
    stops rather than as an arrow.
    """

    clearance: float = 4.0
    """Daylight a route keeps from every box it is not joined to.

    Zero is a legal drawing and a bad one: a connector that runs flush along the
    side of a box it merely passes reads as belonging to that box — an underline
    under a label, a second border down its edge — and the reader has to trace
    the line to its ends to find out it does not. It is also the one failure a
    router will produce on purpose, because a path along a border is exactly as
    short and exactly as straight as one a few units off it, and cheaper than
    going round.
    """

    lane_spacing: float = 12.0
    """How far apart two routes running along the same line are drawn.

    Separate from `head_length`, which it used to borrow. One head length was
    enough to prove two lines are different and not enough to *read* as
    different: three edges leaving one box came out as a bundle whose corners
    stacked within a few units of each other — which is the failure the
    separation pass exists to prevent, reintroduced at a smaller scale.
    """

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> EdgeStyle:
        keys = ("stroke_width", "min_shaft_length", "head_length", "clearance", "lane_spacing")
        _reject_unknown(mapping, keys, "[edge]")
        defaults = cls()
        return cls(
            **{
                key: _number(
                    mapping.get(key, getattr(defaults, key)),
                    f"[edge] {key}",
                    # Zero clearance is a drawing someone may want — flush lines
                    # are a house style, if an unfortunate one. A stroke width or
                    # a head length of zero is not a style, it is an absence.
                    positive=key != "clearance",
                )
                for key in keys
            }
        )


@dataclass(frozen=True)
class MarkStyle:
    """How a chart tells one mark from another, and how much room bars get.

    A chart's marks are the one place drawspec needs a *sequence* of appearances
    rather than a role per thing: the author says "three series of bars", not
    "this one hatched". So the theme declares the order, and a mark takes the
    entry at its own index.

    The vocabulary is the fill **patterns**, and they must be distinct — which
    makes greyscale legibility structural here rather than checked afterwards.
    It is the same rule the role table lives under, arrived at from the other
    direction: roles must differ in a non-colour channel, and these differ in
    nothing else.

    A theme may add `colours` beside them. That is the one thing the review
    asked for that patterns alone cannot give — *"I can't differentiate the
    three colors"* was said of three cell groups whose hatches are too alike at
    cell size — and it is safe here for the same reason the `accent` theme is
    safe: the pattern sequence still has to be distinct on its own, so removing
    the colour removes the emphasis and never the distinction. Print it in black
    and white and the drawing still reads.
    """

    fills: tuple[str, ...] = ("hatch", "dots", "cross", "grid", "none")
    """The fills a chart's marks take, in order, one per filled mark.

    Patterns, never colours: these are what survives a black-and-white printer.
    The entries must be distinct, and they are drawn faint on purpose — a fill
    that competes with the text over it makes the text illegible.
    """

    colours: tuple[str, ...] = ()
    """A colour per fill, in the same order, or empty for ink alone.

    Same length as `fills` when given, so a mark's pattern and its colour travel
    together as one entry rather than two sequences a reader has to align by
    counting. Redundant by construction: the pattern is what carries.
    """

    gap: float = 0.3
    """How much of a category's band is left empty around its bars, as a
    fraction. Zero draws bars that touch, which reads as one wide bar."""

    ramp: tuple[float, ...] = (0.08, 0.16, 0.24, 0.32, 0.4)
    """The tones an ordered `scale` is filled with, lightest first: how much of
    the page's ink each step lays down, from 0 (blank) to 1.

    An order, where `fills` is a set. Patterns cannot carry one — dots, hatch
    and a grid are three different things, not three amounts of one thing — so
    a heatmap's buckets are told apart the way a printed one is, by how dark they
    are. That is lightness, the channel greyscale keeps, and the loader holds it
    to that: at least five steps, each darker than the last by at least 0.08
    (the first measured from a blank cell, which stays "not assessed"), none
    darker than 0.5 so the cell's text stays readable. A shorter `scale` takes
    steps spread across the whole ramp, so two buckets are its two ends.
    """

    def tone_for(self, index: int, count: int) -> float:
        """The tone for step `index` of a `count`-step scale, spread across the ramp."""
        if count <= 1:
            return self.ramp[-1]
        return self.ramp[round(index * (len(self.ramp) - 1) / (count - 1))]

    def level_tone(self, index: int, count: int) -> float:
        """The tone for level `index` of `count` graded levels, lightest first.

        One ramp step per level from the lightest, so three levels stay light,
        and spread across the whole ramp only when there are more levels than
        steps — a graded shape is mostly area, where a heatmap is mostly cells.
        """
        if count <= len(self.ramp):
            return self.ramp[index]
        return self.tone_for(index, count)

    def fill_for(self, index: int) -> str:
        """The fill for the `index`-th filled mark, cycling if there are more."""
        return self.fills[index % len(self.fills)]

    def colour_for(self, index: int) -> str:
        """The colour for the `index`-th filled mark, or empty for the page's ink."""
        if not self.colours:
            return ""
        return self.colours[index % len(self.colours)]

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> MarkStyle:
        _reject_unknown(mapping, ("fills", "colours", "gap", "ramp"), "[mark]")
        defaults = cls()
        fills = mapping.get("fills", list(defaults.fills))
        if not isinstance(fills, list) or not fills:
            raise ThemeError(f"[mark] fills: expected a non-empty array, got {fills!r}")
        for entry in fills:
            if entry not in FILL_PATTERNS:
                raise ThemeError(
                    f"[mark] fills: {entry!r} is not one of {', '.join(FILL_PATTERNS)}"
                )
        if len(set(fills)) != len(fills):
            raise ThemeError(
                "[mark] fills: the entries must be distinct — two marks sharing a fill "
                "cannot be told apart, in greyscale or in colour."
            )
        colours = mapping.get("colours", list(defaults.colours))
        if not isinstance(colours, list):
            raise ThemeError(f"[mark] colours: expected an array, got {colours!r}")
        if colours and len(colours) != len(fills):
            raise ThemeError(
                f"[mark] colours: {len(colours)} colours for {len(fills)} fills. A mark "
                f"takes one entry, so the two sequences are the same length — or leave "
                f"colours out and every mark is drawn in the page's ink."
            )
        painted = tuple(_colour(entry, "[mark] colours") for entry in colours)
        if "none" in painted:
            raise ThemeError(
                "[mark] colours: 'none' is not a colour a mark can be drawn in. It is "
                "meaningful for a role's fill — a box that is not filled — but the ink "
                "a pattern is drawn with is what makes the pattern visible, and a "
                "pattern nobody can see defeats the distinctness the fills are "
                "checked for. Use `currentColor` for the page's own ink."
            )
        gap = _number(mapping.get("gap", defaults.gap), "[mark] gap", positive=False)
        if not 0.0 <= gap < 1.0:
            raise ThemeError(f"[mark] gap: expected a fraction below 1, got {gap!r}")
        return cls(
            fills=tuple(fills),
            colours=painted,
            gap=gap,
            ramp=_ramp(mapping.get("ramp", list(defaults.ramp))),
        )


def _ramp(value: object) -> tuple[float, ...]:
    """`[mark] ramp`, held to the one property it exists for: an order you can see.

    Checked here, at load, like the greyscale role pairing — a ramp whose two
    neighbours are the same grey is a heatmap whose buckets merge, and nobody
    finds out until a reader cannot tell *sometimes* from *often*.
    """
    if not isinstance(value, list) or len(value) < RAMP_STEPS:
        raise ThemeError(
            f"[mark] ramp: expected an array of at least {RAMP_STEPS} tones, one per step "
            f"of the longest scale a matrix may declare; got {value!r}"
        )
    tones = tuple(_number(entry, "[mark] ramp") for entry in value)
    previous = 0.0
    for index, tone in enumerate(tones):
        if tone - previous < RAMP_CONTRAST - 1e-9:
            after = "a blank cell" if index == 0 else f"step {index - 1} ({previous:g})"
            raise ThemeError(
                f"[mark] ramp: step {index} ({tone:g}) is not at least {RAMP_CONTRAST:g} "
                f"darker than {after}. Neighbouring steps that close are one grey in "
                f"print, so two buckets of the scale would read as one."
            )
        previous = tone
    if tones[-1] > RAMP_CEILING:
        raise ThemeError(
            f"[mark] ramp: {tones[-1]:g} is darker than {RAMP_CEILING:g}. A cell's text "
            f"is drawn on its tone, and past that a label on the heaviest step stops "
            f"being easy to read."
        )
    return tones


@dataclass(frozen=True)
class TitleStyle:
    """Whether a diagram carries its own title. Off until the question is settled."""

    show: bool = False
    """Whether a document's `title` is drawn on the diagram as well as announced
    to a screen reader. Off by default: a figure caption is usually the page's
    job, not the drawing's."""

    level: str = "title"
    """Which type level the drawn title takes."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> TitleStyle:
        _reject_unknown(mapping, ("show", "level"), "[title]")
        show = mapping.get("show", False)
        if not isinstance(show, bool):
            raise ThemeError(f"[title] show: expected true or false, got {show!r}")
        return cls(
            show=show, level=_choice(mapping.get("level", "title"), TYPE_LEVELS, "[title] level")
        )


#: How a `cycle` draws the connectors between its steps.
CYCLE_CONNECTORS: Final = ("arc", "band")


@dataclass(frozen=True)
class CycleStyle:
    """How a `cycle`'s connectors are drawn. Appearance, so it lives here.

    An author writes `cycle` and means "these steps come round again". Whether
    the coming-round is drawn as a thin arc with a small head or as a broad
    tapered ribbon — the recycling mark — is a question about the drawing, not
    about the subject, and this project's rule is that the theme answers those.
    So there is no field on the document for it and no second kind: a theme that
    sets `connector = "band"` draws every cycle that way, and the same document
    renders either way without being edited.

    `band` suits a cycle of few, well-separated steps, where the arrows have room
    to be the loudest thing in the drawing and the going-round is the message.
    `arc` is the default because it survives a cycle of seven steps, which a
    ribbon does not.
    """

    connector: str = "arc"
    """Whether a cycle's steps are joined by a thin arc or a broad tapered band."""

    width: float = 11.0
    """How thick a `band` connector is at its shaft, in user units.

    The head is drawn wider than this in the same proportion an arrow head is
    wider than its shaft, so a band reads as the same arrow drawn fat rather
    than as a different kind of mark.
    """

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> CycleStyle:
        _reject_unknown(mapping, ("connector", "width"), "[cycle]")
        defaults = cls()
        return cls(
            connector=_choice(
                mapping.get("connector", defaults.connector),
                CYCLE_CONNECTORS,
                "[cycle] connector",
            ),
            width=_number(mapping.get("width", defaults.width), "[cycle] width"),
        )


@dataclass(frozen=True)
class FunnelStyle:
    """Which way a `funnel` tapers. Appearance, so it lives here.

    An author writes `funnel` and means "stages narrowing to an outcome". Whether
    the narrowing runs across the page or down it is a question about the drawing
    rather than about the subject, so there is no field on the document for it
    and no second kind: the same document renders either way.

    `down` is the default because that is what the word draws. The corpus review
    put it plainly, on a funnel drawn sideways: *"it says embut, which should
    look as vertical — couldn't we have an inverted pyramid for these cases?"* A
    funnel is a thing you pour into, and every reader has seen one. `right` is
    the other reading — a pipeline losing volume from left to right — and it
    suits a diagram whose stages carry long labels, because a stage across the
    page has the whole width of the band to write in.
    """

    direction: str = "down"
    """`down` tapers towards the bottom of the page; `right`, towards its edge."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FunnelStyle:
        _reject_unknown(mapping, ("direction",), "[funnel]")
        defaults = cls()
        return cls(
            direction=_choice(
                mapping.get("direction", defaults.direction),
                FUNNEL_DIRECTIONS,
                "[funnel] direction",
            )
        )


@dataclass(frozen=True)
class StatesStyle:
    """How a state machine's pseudo-states are drawn. Appearance, so it lives here.

    The author says which state the machine starts in and which it ends in; the
    filled dot and the ringed dot that say so are marks with no words, and how big
    they are is a question about the drawing. No field on the document reaches
    either.
    """

    dot: float = 10.0
    """The diameter of the initial pseudo-state's filled dot, and of the dot
    inside a final pseudo-state's ring."""

    ring: float = 3.0
    """The daylight between a final pseudo-state's dot and the ring around it."""

    @property
    def final(self) -> float:
        """The diameter of a final pseudo-state, ring included."""
        return self.dot + self.ring * 2

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> StatesStyle:
        _reject_unknown(mapping, ("dot", "ring"), "[states]")
        defaults = cls()
        return cls(
            dot=_number(mapping.get("dot", defaults.dot), "[states] dot"),
            ring=_number(mapping.get("ring", defaults.ring), "[states] ring"),
        )


@dataclass(frozen=True)
class SequenceStyle:
    """How a sequence diagram's lifelines and activation bars are drawn.

    The author writes who talks to whom and in what order; the bar that shows a
    participant is busy is inferred from a call and its reply, and how wide it is
    — like which line a lifeline is drawn in — is a question about the drawing.
    """

    activation: float = 10.0
    """The width of an activation bar. A nested bar is set half this to the right."""

    lifeline: str = "aside"
    """The edge role a lifeline is drawn in, with no head: dashed and light by
    default, so the messages across it are what the eye follows."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> SequenceStyle:
        _reject_unknown(mapping, ("activation", "lifeline"), "[sequence]")
        defaults = cls()
        return cls(
            activation=_number(
                mapping.get("activation", defaults.activation), "[sequence] activation"
            ),
            lifeline=_choice(
                mapping.get("lifeline", defaults.lifeline), EDGE_ROLES, "[sequence] lifeline"
            ),
        )


#: How an `entities` relation's cardinality is drawn at its ends: crow's-foot
#: marks, or UML's numbers (`1`, `0..1`, `*`, `0..*`, `1..*`).
ENTITIES_NOTATIONS: Final = ("crowsfoot", "numeric")


@dataclass(frozen=True)
class EntitiesStyle:
    """How an entity diagram says *how many* at each end of a relation.

    The author states the cardinality — `one`, `zero-or-many` — and the theme the
    notation, so the same document draws for a database chapter in crow's feet
    and for a UML chapter in numbers.
    """

    notation: str = "crowsfoot"
    """`crowsfoot` (marks across the line's end) or `numeric` (text beside it)."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> EntitiesStyle:
        _reject_unknown(mapping, ("notation",), "[entities]")
        defaults = cls()
        return cls(
            notation=_choice(
                mapping.get("notation", defaults.notation),
                ENTITIES_NOTATIONS,
                "[entities] notation",
            ),
        )


#: How a `gantt` milestone is drawn: a diamond, as most plans draw one, or a dot.
GANTT_MILESTONES: Final = ("diamond", "circle")


@dataclass(frozen=True)
class GanttStyle:
    """How a plan draws the two marks that are not bars.

    The author says a task is a milestone and that a deadline falls at week 6;
    whether the milestone is a diamond or a dot, and which line the deadline is
    drawn in, are house style.
    """

    milestone: str = "diamond"
    """`diamond` or `circle`: the mark a task with `at` is drawn as, filled."""

    marks: str = "weak"
    """The edge role a mark's line across the rows is drawn in, with no head."""

    done: float = 0.7
    """How much of the ink a task's `done` band takes, above 0 and at most 1. The
    page's own ink at that strength, so a dark page draws it light."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> GanttStyle:
        _reject_unknown(mapping, ("milestone", "marks", "done"), "[gantt]")
        defaults = cls()
        done = _number(mapping.get("done", defaults.done), "[gantt] done")
        if not 0.0 < done <= 1.0:
            raise ThemeError(
                f"[gantt] done: expected a fraction above 0 and at most 1, got {done!r}"
            )
        return cls(
            milestone=_choice(
                mapping.get("milestone", defaults.milestone), GANTT_MILESTONES, "[gantt] milestone"
            ),
            marks=_choice(mapping.get("marks", defaults.marks), EDGE_ROLES, "[gantt] marks"),
            done=done,
        )


@dataclass(frozen=True)
class BoardStyle:
    """How a board draws the two lines that are not card borders.

    The author says the board has slices and that the first release ends at one
    of them; which line runs between two slices and how heavy the cut is are
    house style.
    """

    separator: str = "weak"
    """The edge role the line between two rows (slices) is drawn in, with no head."""

    cut: str = "strong"
    """The edge role the cut under a row is drawn in, with no head: the board's one heavy line."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> BoardStyle:
        _reject_unknown(mapping, ("separator", "cut"), "[board]")
        defaults = cls()
        return cls(
            separator=_choice(
                mapping.get("separator", defaults.separator), EDGE_ROLES, "[board] separator"
            ),
            cut=_choice(mapping.get("cut", defaults.cut), EDGE_ROLES, "[board] cut"),
        )


#: The narrowest and widest slant a fishbone's bones may take, in degrees from
#: the spine. Below thirty a bone lies almost along the spine and its causes
#: crowd it; ninety is a comb of upright bones.
FISHBONE_SLANT_RANGE: Final = (30.0, 90.0)


@dataclass(frozen=True)
class FishboneStyle:
    """How a fishbone draws its spine, its bones and the ticks its causes sit on.

    The author says which causes fall under which category; the angle the bones
    meet the spine at, and the weight of each line, are house style.
    """

    slant: float = 60.0
    """The angle, in degrees from the spine, each bone meets it at: 30 to 90. A
    fishbone's bones slant by convention — the one place drawspec draws a
    diagonal on purpose, because the slant *is* the shape. `90` draws a comb of
    upright bones for a theme that keeps right angles throughout."""

    spine: str = "strong"
    """The edge role the spine is drawn in, with no head: from the far end of the
    last bone into the effect's box."""

    bone: str = "flow"
    """The edge role a category's bone is drawn in, with no head. The bone of a
    confirmed root cause (`emphasis`) is drawn in the spine's role from that cause
    to the spine, so the path from cause to effect is one weight."""

    cause: str = "link"
    """The edge role the tick a cause's words sit on is drawn in, with no head. A
    ruled-out cause (`note`) is drawn in `aside` instead: light and dashed."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FishboneStyle:
        _reject_unknown(mapping, ("slant", "spine", "bone", "cause"), "[fishbone]")
        defaults = cls()
        slant = _number(mapping.get("slant", defaults.slant), "[fishbone] slant")
        low, high = FISHBONE_SLANT_RANGE
        if not low <= slant <= high:
            raise ThemeError(
                f"[fishbone] slant: {slant:g} is outside {low:g} to {high:g} degrees — below "
                f"{low:g} a bone lies along the spine, and past {high:g} it leans away from "
                f"the head"
            )
        return cls(
            slant=slant,
            spine=_choice(mapping.get("spine", defaults.spine), EDGE_ROLES, "[fishbone] spine"),
            bone=_choice(mapping.get("bone", defaults.bone), EDGE_ROLES, "[fishbone] bone"),
            cause=_choice(mapping.get("cause", defaults.cause), EDGE_ROLES, "[fishbone] cause"),
        )


@dataclass(frozen=True)
class JourneyStyle:
    """How a journey draws the lines that are not words: the feeling line and its rules.

    The author names each stage's feeling; the weight of the line through them,
    of the guides each level is named on, and of the rules between detail rows
    are house style.
    """

    line: str = "strong"
    """The edge role the feeling line is drawn in, with no head: the one heavy line,
    through every stage's point."""

    guide: str = "aside"
    """The edge role each feeling level's guide is drawn in, across every stage: light,
    so the line and not the grid is what is read."""

    separator: str = "link"
    """The edge role the rule above each detail row is drawn in, across the whole map."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> JourneyStyle:
        _reject_unknown(mapping, ("line", "guide", "separator"), "[journey]")
        defaults = cls()
        return cls(
            line=_choice(mapping.get("line", defaults.line), EDGE_ROLES, "[journey] line"),
            guide=_choice(mapping.get("guide", defaults.guide), EDGE_ROLES, "[journey] guide"),
            separator=_choice(
                mapping.get("separator", defaults.separator), EDGE_ROLES, "[journey] separator"
            ),
        )


#: How a `numberline` marks a range's end: a filled or hollow dot, as school
#: texts in the UK and elsewhere draw it, or a bracket or parenthesis, as most US
#: and college texts do. The same fact — the end is in, or it is out — so it is
#: house style, not content.
NUMBERLINE_ENDS: Final = ("dots", "brackets")


@dataclass(frozen=True)
class NumberlineStyle:
    """How a number line marks whether a range's end belongs to it.

    The author says an end is open or closed; whether that is drawn as a hollow
    and a filled dot or as `(` and `[` is the convention of the course the drawing
    is for, set once for every number line in it.
    """

    ends: str = "dots"
    """`dots` (filled closed, hollow open) or `brackets` (`[` closed, `(` open). A
    point is a dot either way."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> NumberlineStyle:
        _reject_unknown(mapping, ("ends",), "[numberline]")
        defaults = cls()
        return cls(
            ends=_choice(mapping.get("ends", defaults.ends), NUMBERLINE_ENDS, "[numberline] ends"),
        )


#: How a causal link's sign is written: `+` and a true minus, or `s` (same) and `o`
#: (opposite), as some systems-thinking courses teach it.
FLOW_POLARITIES: Final = ("+-", "so")

#: The glyph each polarity is written as, by `[flow] polarity`.
POLARITY_GLYPHS: Final = {"+-": {"+": "+", "-": "\u2212"}, "so": {"+": "s", "-": "o"}}


@dataclass(frozen=True)
class FlowStyle:
    """How a causal loop diagram's signs are written.

    The author says whether a link is positive or negative; whether that reads
    `+` and a minus, or `s` and `o`, is house style, set once for a course's diagrams.
    """

    polarity: str = "+-"
    """`+-` (a plus and a true minus) or `so` (`s` for same, `o` for opposite)."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FlowStyle:
        _reject_unknown(mapping, ("polarity",), "[flow]")
        defaults = cls()
        return cls(
            polarity=_choice(
                mapping.get("polarity", defaults.polarity), FLOW_POLARITIES, "[flow] polarity"
            )
        )


#: How a `pie` is drawn: a full disc, or a ring with a hole in the middle.
PIE_SHAPES: Final = ("pie", "donut")


@dataclass(frozen=True)
class PieStyle:
    """Whether a pie is a disc or a ring.

    The author says what the shares are; a ring instead of a disc is house style —
    the round-2 corpus found donuts only in template galleries — so it is set once
    for every pie in a report, never per document.
    """

    shape: str = "pie"
    """`pie` (a disc, labels inside a sector when they fit) or `donut` (a ring with
    a hole of about half the radius, every label outside on a leader)."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> PieStyle:
        _reject_unknown(mapping, ("shape",), "[pie]")
        defaults = cls()
        return cls(shape=_choice(mapping.get("shape", defaults.shape), PIE_SHAPES, "[pie] shape"))


#: How many levels below its centre a mind map's line weights are given for.
MINDMAP_LEVELS: Final = 3


@dataclass(frozen=True)
class MindmapStyle:
    """How a mind map draws its branches: their lines, and whether words are boxed.

    The author says what branches off what; the thickness of each line and whether
    a leaf sits on a line or in a box are house style.
    """

    boxes: bool = False
    """`false` sets a twig or a leaf on a line, the mind-map convention, its branch
    line running on under its words; `true` boxes them like the main branches."""

    taper: tuple[float, ...] = (6.0, 3.0, 1.5)
    """How thick a branch's line is where it leaves its parent, one width per level
    below the centre, none thicker than the one before. Each line narrows to the
    next level's width where it arrives (the last to two thirds of itself), so a
    map thins from its centre outwards. An `emphasis` branch's line, and every
    line between it and the centre, is drawn half as thick again."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> MindmapStyle:
        _reject_unknown(mapping, ("boxes", "taper"), "[mindmap]")
        defaults = cls()
        boxes = mapping.get("boxes", defaults.boxes)
        if not isinstance(boxes, bool):
            raise ThemeError(f"[mindmap] boxes: expected true or false, got {boxes!r}")
        raw = mapping.get("taper", list(defaults.taper))
        if not isinstance(raw, list) or len(raw) != MINDMAP_LEVELS:
            raise ThemeError(
                f"[mindmap] taper: expected {MINDMAP_LEVELS} widths, one per level below the "
                f"centre, got {raw!r}"
            )
        taper = tuple(_number(value, "[mindmap] taper") for value in raw)
        if any(later > earlier for earlier, later in pairwise(taper)):
            raise ThemeError(
                f"[mindmap] taper: {list(taper)!r} thickens outwards; a map thins from its "
                f"centre, so no width may be more than the one before it"
            )
        return cls(boxes=boxes, taper=taper)


#: The fills an `against` box may take: a pattern faint enough to read words over.
ARGUMENT_FILLS: Final = ("hatch", "dots", "cross", "grid")


@dataclass(frozen=True)
class ArgumentStyle:
    """How an argument map says which way a point bears: its tag and its fill.

    The author says `for` or `against`; the words a reader reads it aloud by, and
    the pattern an objection is filled with, are house style. Stance is drawn on
    both channels, so a map printed in greyscale still says it twice.
    """

    for_tag: str = "because"
    """The tag over a `for` point, in its top margin at the left: the word a reader
    says before it when reading the map aloud."""

    against_tag: str = "but"
    """The tag over an `against` point: an objection, and a rebuttal of one."""

    against_fill: str = "hatch"
    """The pattern an `against` box is filled with; a `for` box is plain. The
    patterns are drawn faint, so the words over them stay readable."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> ArgumentStyle:
        _reject_unknown(mapping, ("for_tag", "against_tag", "against_fill"), "[argument]")
        defaults = cls()
        tags = {}
        for key in ("for_tag", "against_tag"):
            value = mapping.get(key, getattr(defaults, key))
            if not isinstance(value, str) or not value.strip() or "\n" in value:
                raise ThemeError(f"[argument] {key}: expected a word or two, got {value!r}")
            tags[key] = value
        if tags["for_tag"] == tags["against_tag"]:
            raise ThemeError(
                f"[argument] for_tag and against_tag are both {tags['for_tag']!r}: the tag is "
                f"one of the two things that tell a reason from an objection"
            )
        return cls(
            for_tag=tags["for_tag"],
            against_tag=tags["against_tag"],
            against_fill=_choice(
                mapping.get("against_fill", defaults.against_fill),
                ARGUMENT_FILLS,
                "[argument] against_fill",
            ),
        )


#: The shapes a RAG mark may take. Three of them at once, all different, so a
#: rating is told by its outline in greyscale as well as by its word.
RAG_SHAPES: Final = ("circle", "triangle", "square", "diamond")

#: The ratings and trends a `[rag]` table names, in the order its keys are read.
_RAG_RATINGS: Final = ("red", "amber", "green")
_RAG_TRENDS: Final = ("better", "same", "worse")


@dataclass(frozen=True)
class RagStyle:
    """How a RAG report draws a rating: a word, a shape and, optionally, a colour.

    The author says `red`, `amber` or `green`; what the reader sees is decided
    here, once, for every report. Each rating is said at least twice without
    colour, by its word and by its shape, and the loader holds both to that: the
    three words differ, and so do the three shapes. A colour is added on top only
    when a theme declares one, so removing it removes nothing the reader needs.
    """

    red: str = "Red"
    """The word written beside a `red` mark. A house that says *Off track* sets it here."""

    amber: str = "Amber"
    """The word beside an `amber` mark: *Amber*, or *At risk*."""

    green: str = "Green"
    """The word beside a `green` mark: *Green*, or *On track*."""

    red_shape: str = "square"
    """The shape of a `red` mark: `circle`, `triangle`, `square` or `diamond`, each
    different from the other two ratings' shapes."""

    amber_shape: str = "triangle"
    """The shape of an `amber` mark, the warning triangle by default."""

    green_shape: str = "circle"
    """The shape of a `green` mark."""

    red_colour: str = ""
    """The colour a `red` mark is filled with. Empty is the page's ink, as in the
    default theme; the `accent` theme sets the three."""

    amber_colour: str = ""
    """The colour an `amber` mark is filled with, or empty for the page's ink."""

    green_colour: str = ""
    """The colour a `green` mark is filled with, or empty for the page's ink."""

    better: str = "improving"
    """The word beside a `better` trend's arrow, which points up."""

    same: str = "no change"
    """The word beside a `same` trend's arrow, which points across."""

    worse: str = "worsening"
    """The word beside a `worse` trend's arrow, which points down."""

    def word(self, rating: str) -> str:
        return str(getattr(self, rating))

    def shape(self, rating: str) -> str:
        return str(getattr(self, f"{rating}_shape"))

    def colour(self, rating: str) -> str:
        return str(getattr(self, f"{rating}_colour"))

    @property
    def colours(self) -> tuple[str, ...]:
        return tuple(self.colour(rating) for rating in _RAG_RATINGS if self.colour(rating))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> RagStyle:
        keys = (
            *_RAG_RATINGS,
            *(f"{rating}_shape" for rating in _RAG_RATINGS),
            *(f"{rating}_colour" for rating in _RAG_RATINGS),
            *_RAG_TRENDS,
        )
        _reject_unknown(mapping, keys, "[rag]")
        defaults = cls()
        values: dict[str, str] = {}
        for key in (*_RAG_RATINGS, *_RAG_TRENDS):
            value = mapping.get(key, getattr(defaults, key))
            if not isinstance(value, str) or not value.strip() or "\n" in value:
                raise ThemeError(f"[rag] {key}: expected a word or two, got {value!r}")
            values[key] = value
        for group in (_RAG_RATINGS, _RAG_TRENDS):
            words = [values[key] for key in group]
            if len(set(words)) != len(words):
                raise ThemeError(
                    f"[rag] {', '.join(group)}: {words!r} repeat a word. The word is how a "
                    f"reader who cannot see colour tells them apart, so each must differ."
                )
        for rating in _RAG_RATINGS:
            key = f"{rating}_shape"
            values[key] = _choice(
                mapping.get(key, getattr(defaults, key)), RAG_SHAPES, f"[rag] {key}"
            )
            key = f"{rating}_colour"
            raw = mapping.get(key, "")
            values[key] = _colour(raw, f"[rag] {key}") if raw else ""
            if values[key] == "none":
                raise ThemeError(f"[rag] {key}: a mark must be visible; use `currentColor`")
        shapes = [values[f"{rating}_shape"] for rating in _RAG_RATINGS]
        if len(set(shapes)) != len(shapes):
            raise ThemeError(
                f"[rag] red_shape, amber_shape, green_shape: {shapes!r} repeat a shape. The "
                f"shape is what a greyscale print keeps, so the three must differ."
            )
        return cls(**values)


#: How a family tree marks a carrier: the standard's dot in the middle of the
#: symbol, or the left half filled, as exam pedigrees draw a heterozygote.
FAMILYTREE_CARRIERS: Final = ("dot", "half")


@dataclass(frozen=True)
class FamilytreeStyle:
    """How a family tree draws its one non-default mark of house style: a carrier.

    Affected is filled and unaffected is empty in every convention; a carrier is
    the one status two conventions draw differently, and both survive greyscale.
    """

    carrier: str = "dot"
    """`dot`, a filled dot in the middle of the symbol (the standard nomenclature's
    carrier), or `half`, the left half filled (the textbook heterozygote)."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FamilytreeStyle:
        _reject_unknown(mapping, ("carrier",), "[familytree]")
        return cls(
            carrier=_choice(
                mapping.get("carrier", cls().carrier), FAMILYTREE_CARRIERS, "[familytree] carrier"
            )
        )


#: Which way a `lanes` diagram's lanes run: across the page, stacked top to
#: bottom (`rows`), or down it, side by side (`columns`). `auto` tries rows and
#: takes columns when rows do not fit the width.
LANES_ORIENTATIONS: Final = ("rows", "columns", "auto")


@dataclass(frozen=True)
class LanesStyle:
    """How a swimlane diagram lays its lanes out and divides them.

    The author says whose each step is; whether the parties' strips run across
    the page or down it is a question about the drawing, answered here like
    direction everywhere else — never by the document.
    """

    orientation: str = "auto"
    """`rows`, `columns`, or `auto`: rows when they fit the width, else columns."""

    separator: str = "link"
    """The edge role the line between two lanes is drawn in, with no head."""

    stripe: float = 0.0
    """How much of the page's ink every second lane is washed with, from 0 (no
    stripes) to `TONE_CEILING`. A tint, not a colour, so dark mode and greyscale
    keep it."""

    phase: str = "aside"
    """The edge role the line between two phases is drawn in, across every lane:
    lighter than a lane's own separator, since a phase is crossed by every lane."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> LanesStyle:
        _reject_unknown(mapping, ("orientation", "separator", "stripe", "phase"), "[lanes]")
        defaults = cls()
        return cls(
            stripe=_tone(mapping.get("stripe", defaults.stripe), "[lanes] stripe"),
            orientation=_choice(
                mapping.get("orientation", defaults.orientation),
                LANES_ORIENTATIONS,
                "[lanes] orientation",
            ),
            separator=_choice(
                mapping.get("separator", defaults.separator), EDGE_ROLES, "[lanes] separator"
            ),
            phase=_choice(mapping.get("phase", defaults.phase), EDGE_ROLES, "[lanes] phase"),
        )


#: The most ink a container's wash or a lane's stripe may lay down. A frame is
#: behind words and boxes, so its tone has to stay well under a matrix cell's.
TONE_CEILING: Final = 0.1


def _tone(value: Any, where: str) -> float:
    """A wash strength: a fraction of the ink from 0 to `TONE_CEILING`.

    `false` is read as 0, so a theme can say "off" in the words it would use for
    a switch; `true` is refused, since it names no strength.
    """
    if value is False:
        return 0.0
    if value is True:
        raise ThemeError(
            f"{where}: expected a fraction from 0 to {TONE_CEILING} (or false), got true"
        )
    tone = _number(value, where, positive=False)
    if not 0.0 <= tone <= TONE_CEILING:
        raise ThemeError(f"{where}: expected a fraction from 0 to {TONE_CEILING}, got {tone!r}")
    return tone


@dataclass(frozen=True)
class FramesStyle:
    """How a container is told from the page: washed with a little of the ink.

    A group's frame (`flow` and `tree` groups, a state's composite) and a
    sequence diagram's group are filled with `tone` of the page's ink, drawn as
    `currentColor` at part opacity, so it follows the page into dark mode and
    prints as a light grey. Frames inside frames lay their wash over their
    parent's, so each level of nesting reads one step darker, up to `levels`
    deep; deeper frames add no more.
    """

    tone: float = 0.0
    """The share of the ink one frame lays down, from 0 (outlines only) to
    `TONE_CEILING`."""

    levels: int = 3
    """How many levels of nesting deepen the wash; a frame deeper than this is
    outlined only."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FramesStyle:
        _reject_unknown(mapping, ("tone", "levels"), "[frames]")
        defaults = cls()
        levels = mapping.get("levels", defaults.levels)
        if isinstance(levels, bool) or not isinstance(levels, int) or not 1 <= levels <= 5:
            raise ThemeError(
                f"[frames] levels: expected a whole number from 1 to 5, got {levels!r}"
            )
        return cls(tone=_tone(mapping.get("tone", defaults.tone), "[frames] tone"), levels=levels)

    def tone_at(self, depth: int) -> float:
        """The wash a frame `depth` levels inside others lays down, or 0."""
        return self.tone if depth < self.levels else 0.0


@dataclass(frozen=True)
class LevelsStyle:
    """Whether the levels of a `pyramid`, `funnel`, `rings` and `stack` are graded.

    Each level, stage, ring or layer is filled from `[mark] ramp`, the tones a
    matrix `scale` uses: the first written lightest, one ramp step darker per
    level after it (spread across the ramp when there are more levels than
    steps). The page's ink at part opacity, never a colour, so it follows a dark
    page and prints as greys, and the ramp's own ceiling keeps text legible on
    the darkest step. A `note` level stays unfilled, and so does a level whose
    role the theme already fills.
    """

    shade: bool = False
    """Whether levels are graded from the ramp; `false` draws outlines only."""

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> LevelsStyle:
        _reject_unknown(mapping, ("shade",), "[levels]")
        shade = mapping.get("shade", cls().shade)
        if shade in (0, 1) and not isinstance(shade, float):
            shade = bool(shade)
        if not isinstance(shade, bool):
            raise ThemeError(f"[levels] shade: expected true or false, got {shade!r}")
        return cls(shade=shade)


#: What a `files` page says about its file's type.
FILES_TYPES: Final = ("labels", "pictures", "none")

#: Where a `files` tree sits on the canvas.
FILES_ALIGNS: Final = ("left", "centre")


@dataclass(frozen=True)
class FilesStyle:
    """How a `files` tree draws its pictures. Appearance, so it lives here.

    The document says what is in the tree and whether to draw pictures at all;
    whether a folder is a tinted shape or an outline, whether a file carries its
    extension on a badge, and what colour either is, are questions about the
    drawing. Colour is optional here as everywhere: with no `colours` a tree is
    drawn in the page's ink, and one that declares them still tells a folder from
    a file by shape and a type by its badge, so nothing is lost in greyscale.
    """

    tint: float = 0.25
    """How strongly a folder is filled, from 0 (an outline) to 1 (solid). The same
    strength paints a file whose type has a colour below."""

    types: str = "labels"
    """What a file's page says about its type. `labels` writes the extension on a
    small tag across the page — `PDF`, `JSON` — lettered as part of the picture;
    `pictures` draws one of five shapes (code, data, text, image, archive);
    `none` draws a plain page."""

    label_ink: str = ""
    """The colour a label's letters are drawn in when its tag is filled with a
    colour below — white on a red `PDF`, say. Empty is the page's ink."""

    align: str = "left"
    """Where a tree sits on the canvas: `left`, as a listing reads, or `centre`,
    like every other kind."""

    colours: Mapping[str, str] = MappingProxyType({})
    """Fill colour by extension (`pdf`), by type family (`code`, `data`, `text`,
    `image`, `archive`), or `folder`. An extension wins over its family. Anything
    not named is drawn in the page's ink."""

    def colour_for(self, key: str) -> str:
        return self.colours.get(key, "")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> FilesStyle:
        _reject_unknown(mapping, ("tint", "types", "label_ink", "align", "colours"), "[files]")
        defaults = cls()
        tint = _number(mapping.get("tint", defaults.tint), "[files] tint", positive=False)
        if not 0 <= tint <= 1:
            raise ThemeError(f"[files] tint: expected a fraction from 0 to 1, got {tint!r}")
        types = _choice(mapping.get("types", defaults.types), FILES_TYPES, "[files] types")
        align = _choice(mapping.get("align", defaults.align), FILES_ALIGNS, "[files] align")
        ink = mapping.get("label_ink", defaults.label_ink)
        label_ink = _colour(ink, "[files] label_ink") if ink else ""
        colours = mapping.get("colours", {})
        if not isinstance(colours, Mapping):
            raise ThemeError(f"[files] colours: expected a table, got {colours!r}")
        painted: dict[str, str] = {}
        for key, value in colours.items():
            if key != key.lower() or key.startswith("."):
                raise ThemeError(
                    f"[files] colours: {key!r} — name an extension in lower case and "
                    f"without its dot, as `pdf`, a type family such as `code`, or `folder`."
                )
            painted[key] = _colour(value, f"[files] colours.{key}")
        return cls(
            tint=tint,
            types=types,
            label_ink=label_ink,
            align=align,
            colours=MappingProxyType(painted),
        )


@dataclass(frozen=True)
class NodeRole:
    """How one semantic node role is drawn."""

    shape: str = "rect"
    stroke: str = "currentColor"
    fill: str = "none"
    fill_pattern: str = "none"
    dash: str = "none"
    stroke_width: float = 1.5

    @property
    def channels(self) -> tuple[str, str, str, float]:
        """The non-colour channels — what has to differ to survive greyscale."""
        return (self.shape, self.dash, self.fill_pattern, self.stroke_width)

    @property
    def colours(self) -> tuple[str, ...]:
        return (self.stroke, self.fill)

    @classmethod
    def from_mapping(cls, name: str, mapping: Mapping[str, Any], base: NodeRole) -> NodeRole:
        where = f"[role.{name}]"
        keys = ("shape", "stroke", "fill", "fill_pattern", "dash", "stroke_width")
        _reject_unknown(mapping, keys, where)
        return cls(
            shape=_choice(mapping.get("shape", base.shape), NODE_SHAPES, f"{where} shape"),
            stroke=_colour(mapping.get("stroke", base.stroke), f"{where} stroke"),
            fill=_colour(mapping.get("fill", base.fill), f"{where} fill"),
            fill_pattern=_choice(
                mapping.get("fill_pattern", base.fill_pattern),
                FILL_PATTERNS,
                f"{where} fill_pattern",
            ),
            dash=_dash(mapping.get("dash", base.dash), f"{where} dash"),
            stroke_width=_number(
                mapping.get("stroke_width", base.stroke_width), f"{where} stroke_width"
            ),
        )


@dataclass(frozen=True)
class EdgeRole:
    """How one semantic edge role is drawn, ends included."""

    head: str = "arrow"
    tail: str = "none"
    stroke: str = "currentColor"
    dash: str = "none"
    stroke_width: float = 1.5

    routing: str = "orthogonal"
    """Whether edges in this role turn at right angles or run straight.

    `orthogonal` is the default and was the whole of the router for two rounds,
    because it is what a *flow* wants: a process read down the page is a sequence
    of steps, and a staircase between two of them says "then this" the way a
    diagonal does not.

    A mesh is the other picture. A spine-leaf fabric and a value chain are both
    saying *everything connects to everything*, and drawn orthogonally they
    become a ladder of parallel runs whose crossings the reader has to
    disentangle one at a time. The corpus review named it: "in this case, I think
    the crossed lines transmit better what they want to show. We should have that
    option too, at least for lines without arrow head."

    Which is why this is per role rather than per theme, and why it is the
    theme's rather than the document's. The author already said which edges are
    a flow and which are a bare association — `link` is the vocabulary's word for
    "merely connected" — and *how a bare association is drawn* is exactly the
    kind of question a theme answers. The same document renders either way.

    A direct route is a straight line between the two shapes' outlines, and it is
    not routed around anything: a mesh drawn straight is meant to cross itself.
    """

    @property
    def has_head(self) -> bool:
        return self.head != "none"

    @property
    def has_tail(self) -> bool:
        return self.tail != "none"

    @property
    def channels(self) -> tuple[str, str, str, float]:
        return (self.head, self.tail, self.dash, self.stroke_width)

    @property
    def colours(self) -> tuple[str, ...]:
        return (self.stroke,)

    @classmethod
    def from_mapping(cls, name: str, mapping: Mapping[str, Any], base: EdgeRole) -> EdgeRole:
        where = f"[edge_role.{name}]"
        keys = ("head", "tail", "stroke", "dash", "stroke_width", "routing")
        _reject_unknown(mapping, keys, where)
        return cls(
            head=_choice(mapping.get("head", base.head), EDGE_HEADS, f"{where} head"),
            tail=_choice(mapping.get("tail", base.tail), EDGE_HEADS, f"{where} tail"),
            stroke=_colour(mapping.get("stroke", base.stroke), f"{where} stroke"),
            dash=_dash(mapping.get("dash", base.dash), f"{where} dash"),
            stroke_width=_number(
                mapping.get("stroke_width", base.stroke_width), f"{where} stroke_width"
            ),
            routing=_choice(
                mapping.get("routing", base.routing), EDGE_ROUTINGS, f"{where} routing"
            ),
        )


# ---------------------------------------------------------------------------
# The theme
# ---------------------------------------------------------------------------

_TOP_LEVEL_KEYS: Final = (
    "version",
    "name",
    "canvas",
    "font",
    "scale",
    "fit",
    "box",
    "edge",
    "mark",
    "title",
    "frames",
    "levels",
    "cycle",
    "funnel",
    "files",
    "states",
    "sequence",
    "lanes",
    "entities",
    "gantt",
    "board",
    "fishbone",
    "journey",
    "numberline",
    "pie",
    "flow",
    "mindmap",
    "argument",
    "familytree",
    "rag",
    "role",
    "edge_role",
)


@dataclass(frozen=True)
class Theme:
    """A complete, validated theme. Immutable, and greyscale-safe by construction."""

    version: int = THEME_VERSION
    name: str = "default"
    canvas: Canvas = Canvas()
    font: FontStacks = FontStacks()
    scale: TypeScale = TypeScale()
    fit: FitBand = FitBand()
    box: BoxStyle = BoxStyle()
    edge: EdgeStyle = EdgeStyle()
    mark: MarkStyle = MarkStyle()
    title: TitleStyle = TitleStyle()
    cycle: CycleStyle = CycleStyle()
    funnel: FunnelStyle = FunnelStyle()
    files: FilesStyle = FilesStyle()
    states: StatesStyle = StatesStyle()
    sequence: SequenceStyle = SequenceStyle()
    lanes: LanesStyle = LanesStyle()
    frames: FramesStyle = FramesStyle()
    levels: LevelsStyle = LevelsStyle()
    entities: EntitiesStyle = EntitiesStyle()
    gantt: GanttStyle = GanttStyle()
    board: BoardStyle = BoardStyle()
    fishbone: FishboneStyle = FishboneStyle()
    journey: JourneyStyle = JourneyStyle()
    numberline: NumberlineStyle = NumberlineStyle()
    pie: PieStyle = PieStyle()
    mindmap: MindmapStyle = MindmapStyle()
    argument: ArgumentStyle = ArgumentStyle()
    familytree: FamilytreeStyle = FamilytreeStyle()
    rag: RagStyle = RagStyle()
    flow: FlowStyle = FlowStyle()
    roles: Mapping[str, NodeRole] = MappingProxyType({})
    edge_roles: Mapping[str, EdgeRole] = MappingProxyType({})

    # -- construction -----------------------------------------------------

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> Theme:
        """Build and validate a theme from an already-merged mapping.

        Raises:
            ThemeError: the mapping is malformed, names something outside a
                closed vocabulary, or leaves two roles distinguishable only by
                colour.
        """
        _reject_unknown(mapping, _TOP_LEVEL_KEYS, "theme")

        version = mapping.get("version")
        if version is None:
            raise ThemeError(
                "theme: 'version' is required. drawspec reads version "
                f"{THEME_VERSION}; declare it so a future format change is a "
                "loud failure rather than a misread file."
            )
        if version != THEME_VERSION:
            raise ThemeError(
                f"theme: version {version!r} is not supported; this drawspec reads "
                f"version {THEME_VERSION}."
            )

        name = mapping.get("name", "default")
        if not isinstance(name, str) or not name:
            raise ThemeError(f"theme: 'name' must be a non-empty string, got {name!r}")

        roles = _build_node_roles(_section(mapping, "role"))
        edge_roles = _build_edge_roles(_section(mapping, "edge_role"))

        theme = cls(
            version=THEME_VERSION,
            name=name,
            canvas=Canvas.from_mapping(_section(mapping, "canvas")),
            font=FontStacks.from_mapping(_section(mapping, "font")),
            scale=TypeScale.from_mapping(_section(mapping, "scale")),
            fit=FitBand.from_mapping(_section(mapping, "fit")),
            box=BoxStyle.from_mapping(_section(mapping, "box")),
            edge=EdgeStyle.from_mapping(_section(mapping, "edge")),
            mark=MarkStyle.from_mapping(_section(mapping, "mark")),
            title=TitleStyle.from_mapping(_section(mapping, "title")),
            cycle=CycleStyle.from_mapping(_section(mapping, "cycle")),
            funnel=FunnelStyle.from_mapping(_section(mapping, "funnel")),
            files=FilesStyle.from_mapping(_section(mapping, "files")),
            states=StatesStyle.from_mapping(_section(mapping, "states")),
            sequence=SequenceStyle.from_mapping(_section(mapping, "sequence")),
            lanes=LanesStyle.from_mapping(_section(mapping, "lanes")),
            frames=FramesStyle.from_mapping(_section(mapping, "frames")),
            levels=LevelsStyle.from_mapping(_section(mapping, "levels")),
            entities=EntitiesStyle.from_mapping(_section(mapping, "entities")),
            gantt=GanttStyle.from_mapping(_section(mapping, "gantt")),
            board=BoardStyle.from_mapping(_section(mapping, "board")),
            fishbone=FishboneStyle.from_mapping(_section(mapping, "fishbone")),
            journey=JourneyStyle.from_mapping(_section(mapping, "journey")),
            numberline=NumberlineStyle.from_mapping(_section(mapping, "numberline")),
            pie=PieStyle.from_mapping(_section(mapping, "pie")),
            mindmap=MindmapStyle.from_mapping(_section(mapping, "mindmap")),
            argument=ArgumentStyle.from_mapping(_section(mapping, "argument")),
            familytree=FamilytreeStyle.from_mapping(_section(mapping, "familytree")),
            rag=RagStyle.from_mapping(_section(mapping, "rag")),
            flow=FlowStyle.from_mapping(_section(mapping, "flow")),
            roles=MappingProxyType(roles),
            edge_roles=MappingProxyType(edge_roles),
        )

        ambiguous = theme.ambiguous_role_pairs()
        if ambiguous:
            pairs = "; ".join(f"{first} and {second}" for first, second in ambiguous)
            raise ThemeError(
                f"theme {name!r}: greyscale-ambiguous role pair(s): {pairs}. Two roles "
                f"must differ in at least one non-colour channel (shape, dash pattern, "
                f"stroke weight, fill pattern) or by a relative luminance of at least "
                f"{LUMINANCE_DELTA}, or a reader printing in greyscale cannot tell them "
                f"apart."
            )
        _check_ground(theme)
        return theme

    # -- derived views ----------------------------------------------------

    def ambiguous_role_pairs(self) -> tuple[tuple[str, str], ...]:
        """Role pairs a greyscale reader could not tell apart. Empty is the gate.

        Node and edge roles are compared within their own vocabulary: a node
        never has to be told apart from an edge, because their geometry already
        does that.
        """
        ambiguous: list[tuple[str, str]] = []
        for group in (self.roles, self.edge_roles):
            for first, second in combinations(sorted(group), 2):
                if _indistinguishable(group[first], group[second]):
                    ambiguous.append((first, second))
        return tuple(ambiguous)

    def declared_colours(self) -> frozenset[str]:
        """Every colour literal this theme declares — the emitter's allowlist.

        The embedding-safety check in `drawspec.emit` rejects any `fill` or
        `stroke` in the output that is not in this set, which is what stops a
        colour being decided anywhere but here.
        """
        colours: set[str] = {
            "currentColor",
            "none",
            self.canvas.ink,
            *self.mark.colours,
            *self.files.colours.values(),
            *self.rag.colours,
            *self.canvas.sheet_colours,
        }
        if self.files.label_ink:
            colours.add(self.files.label_ink)
        for role in self.roles.values():
            colours.update(role.colours)
        for edge_role in self.edge_roles.values():
            colours.update(edge_role.colours)
        return frozenset(colours)

    def declares(self, role: str) -> bool:
        """True when `role` is in either vocabulary this theme declares."""
        return role in self.roles or role in self.edge_roles

    def role_for(self, role: str) -> NodeRole | EdgeRole:
        """The appearance declared for `role`.

        Raises:
            KeyError: the theme declares no such role. The vocabularies are
                disjoint, so there is never a question of which one was meant.
        """
        if role in self.roles:
            return self.roles[role]
        if role in self.edge_roles:
            return self.edge_roles[role]
        raise KeyError(
            f"the theme declares no role {role!r}; it declares "
            f"{', '.join(sorted(self.roles))} for nodes and "
            f"{', '.join(sorted(self.edge_roles))} for edges"
        )

    def head_length_for(self, role: str) -> float:
        """How long an end treatment drawn in `role` is.

        A head on a heavier shaft has to be bigger to read as equally emphatic.
        The `strong` edge role is two thirds heavier than `flow`, and drawn with
        the same six units of head it does not look like a louder arrow — it
        looks like a thick line that stops, because the head is barely wider
        than the shaft it sits on.

        So the head is scaled by weight, in both directions. It used to be floored
        at the theme's own `head_length` on the argument that *which way* should
        never get quieter — and the reviewer read the result straight off the
        drawing: *"arrow heads are too big, especially when merged with thinner
        lines"*. A `link` is drawn at two thirds of `flow`'s weight and was
        getting the same head, so on the thinnest line in the vocabulary the head
        was the widest thing about it. The head belongs to its shaft: it is
        `head_length` at the theme's own stroke width and in proportion either
        side of it.
        """
        width = getattr(self.role_for(role), "stroke_width", self.edge.stroke_width)
        return self.edge.head_length * width / self.edge.stroke_width

    @property
    def widest_head(self) -> float:
        """The longest head any edge role in this theme draws.

        Routing reserves straight run, rank separation and turn clearance for a
        head *before* it knows which role will use them — the layout runs once
        for every edge in the diagram. So it reserves the largest, and every
        role fits by construction rather than by the router happening to be
        asked about the light one first.
        """
        return max(
            (self.head_length_for(name) for name in self.edge_roles),
            default=self.edge.head_length,
        )

    def with_scale(self, factor: float) -> Theme:
        """This theme with the whole type scale multiplied by `factor`.

        The elastic fit in T6 chooses one factor and calls this once; there is
        deliberately no way to reach a single level.
        """
        return replace(self, scale=self.scale.scaled(factor))


def _role_tables(
    declared: Mapping[str, Any], vocabulary: tuple[str, ...], section: str
) -> dict[str, Mapping[str, Any]]:
    """One table per role in `vocabulary`, rejecting any name outside it."""
    unknown = sorted(set(declared) - set(vocabulary))
    if unknown:
        raise ThemeError(
            f"[{section}]: {', '.join(repr(name) for name in unknown)} "
            f"{'is' if len(unknown) == 1 else 'are'} not in the {section} vocabulary "
            f"({', '.join(vocabulary)}). A role no document can name would never be "
            f"drawn, so it is a typo rather than an extension."
        )
    tables: dict[str, Mapping[str, Any]] = {}
    for name in vocabulary:
        mapping = declared.get(name, {})
        if not isinstance(mapping, Mapping):
            raise ThemeError(f"[{section}.{name}]: expected a table, got {mapping!r}")
        tables[name] = mapping
    return tables


def _build_node_roles(declared: Mapping[str, Any]) -> dict[str, NodeRole]:
    tables = _role_tables(declared, NODE_ROLES, "role")
    return {name: NodeRole.from_mapping(name, table, NodeRole()) for name, table in tables.items()}


def _build_edge_roles(declared: Mapping[str, Any]) -> dict[str, EdgeRole]:
    tables = _role_tables(declared, EDGE_ROLES, "edge_role")
    return {name: EdgeRole.from_mapping(name, table, EdgeRole()) for name, table in tables.items()}


def _check_ground(theme: Theme) -> None:
    """Every colour the theme draws in must read on its sheet's ground.

    A ground is the page of a standalone drawing, so the check a brand import
    makes against white and near-black is made here against the ground instead:
    the ink as text, everything else as line work.
    """
    ground = theme.canvas.ground
    if ground == "none":
        return
    ink = theme.canvas.ink
    if contrast(ink, ground) < TEXT_CONTRAST:
        raise ThemeError(
            f"theme {theme.name!r}: [canvas] ink {ink} on ground {ground} is "
            f"{contrast(ink, ground):.1f}:1, and text needs {TEXT_CONTRAST}:1."
        )
    drawn = theme.declared_colours() - {"currentColor", "none", ink, ground}
    faint = sorted(colour for colour in drawn if contrast(colour, ground) < GRAPHIC_CONTRAST)
    if faint:
        raise ThemeError(
            f"theme {theme.name!r}: {', '.join(faint)} read at under "
            f"{GRAPHIC_CONTRAST}:1 on [canvas] ground {ground}. A sheet's ground is the "
            f"page a standalone drawing is read on, so every colour drawn on it must "
            f"stand out from it."
        )


def _indistinguishable(first: NodeRole | EdgeRole, second: NodeRole | EdgeRole) -> bool:
    """True when nothing but colour separates two roles, and colour is too close."""
    if first.channels != second.channels:
        return False
    for left, right in zip(first.colours, second.colours, strict=True):
        left_luminance = relative_luminance(left)
        right_luminance = relative_luminance(right)
        if left_luminance is None or right_luminance is None:
            continue
        if abs(left_luminance - right_luminance) >= LUMINANCE_DELTA:
            return False
    return True


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursive mapping merge — `override` wins, leaf by leaf."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge(existing, value)
        else:
            merged[key] = value
    return merged


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise ThemeError(f"theme file not found: {path}") from None
    except OSError as error:
        raise ThemeError(f"theme file could not be read: {path} ({error})") from None
    except tomllib.TOMLDecodeError as error:
        raise ThemeError(f"theme file could not be parsed as TOML: {path} ({error})") from None


def _resolve(source: str | Path) -> Path:
    """A bundled theme name or a path to a `.toml` file."""
    bundled = _THEMES_DIR / f"{source}.toml"
    if isinstance(source, str) and bundled.is_file():
        return bundled
    return Path(source).expanduser()


def load_theme(source: Theme | str | Path | Mapping[str, Any] | None = None) -> Theme:
    """Load a theme, merged over the bundled default and validated.

    Args:
        source: a `Theme` (returned unchanged), the name of a bundled theme,
            the path of a TOML file, a mapping, or None for the default.

    Raises:
        ThemeError: the theme cannot be read, is malformed, names something
            outside a closed vocabulary, or has a greyscale-ambiguous role pair.
    """
    if isinstance(source, Theme):
        return source

    default = _read_toml(DEFAULT_THEME_PATH)
    if source is None:
        return Theme.from_mapping(default)

    if isinstance(source, Mapping):
        override: Mapping[str, Any] = source
    else:
        override = _read_toml(_resolve(source))

    # `version` is the one field that is not inherited: a theme must state which
    # format it was written against, or a future v2 file would load as a v1.
    if "version" not in override:
        raise ThemeError(
            "theme: 'version' is required. drawspec reads version "
            f"{THEME_VERSION}; declare it so a future format change is a loud "
            "failure rather than a misread file."
        )
    return Theme.from_mapping(_merge(default, override))


__all__ = [
    "COLOUR_KEYWORDS",
    "DEFAULT_THEME_PATH",
    "EDGE_HEADS",
    "EDGE_ROLES",
    "FILL_PATTERNS",
    "FONT_ROLES",
    "GRAPHIC_CONTRAST",
    "LUMINANCE_DELTA",
    "NODE_ROLES",
    "NODE_SHAPES",
    "RAMP_CEILING",
    "RAMP_CONTRAST",
    "RAMP_STEPS",
    "SHEET_BORDERS",
    "SHEET_PATTERNS",
    "TEXT_CONTRAST",
    "THEME_VERSION",
    "TYPE_LEVELS",
    "WIDTH_MODES",
    "BoxStyle",
    "Canvas",
    "EdgeRole",
    "EdgeStyle",
    "FitBand",
    "FontStacks",
    "MarkStyle",
    "NodeRole",
    "Padding",
    "Theme",
    "TitleStyle",
    "TypeScale",
    "contrast",
    "load_theme",
    "relative_luminance",
]
