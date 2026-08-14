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
from itertools import combinations
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from drawspec.errors import ThemeError

#: The theme schema version this module reads.
THEME_VERSION: Final = 1

#: Semantic node roles. The closed vocabulary a document's `role` field draws
#: from — see specification §5.1.
NODE_ROLES: Final = ("start", "step", "decision", "terminal", "emphasis", "note", "group")

#: Semantic edge roles. `link` is how "merely associated" is said.
EDGE_ROLES: Final = ("flow", "link", "exchange", "weak", "owns", "strong")

#: Shapes a node role may take.
NODE_SHAPES: Final = ("rect", "pill", "diamond", "ellipse", "none")

#: Fill treatments. A non-colour channel, so it counts toward greyscale safety.
FILL_PATTERNS: Final = ("none", "solid", "hatch", "dots", "cross", "grid")

#: End treatments an edge role may take. Closed, and it lives in the theme, so a
#: document stays readable when the theme changes.
EDGE_HEADS: Final = ("arrow", "open", "diamond", "circle", "bar", "none")

#: The four type levels. One size per level, and no element names its own.
TYPE_LEVELS: Final = ("title", "heading", "body", "label")

#: Font roles a theme declares stacks for.
FONT_ROLES: Final = ("sans", "serif", "mono")

#: Colour keywords that are legal anywhere a colour is, and carry no luminance.
COLOUR_KEYWORDS: Final = ("currentColor", "none")

#: Minimum relative-luminance difference for two colours to survive greyscale.
LUMINANCE_DELTA: Final = 0.25

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


@dataclass(frozen=True)
class Canvas:
    """The one width every diagram is drawn to, and the legibility floor."""

    width: float = 640.0
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

    min_legible_size: float = 9.0
    ink: str = "#1a1a1a"
    """What `currentColor` resolves to in the `standalone` profile.

    A linked `.svg` or a PDF conversion has nothing to inherit from, so the ink
    has to be stated somewhere; stating it here keeps it a theme decision rather
    than a converter default.
    """

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> Canvas:
        _reject_unknown(mapping, ("width", "width_mode", "min_legible_size", "ink"), "[canvas]")
        return cls(
            width=_number(mapping.get("width", 640.0), "[canvas] width"),
            width_mode=_choice(
                mapping.get("width_mode", "fixed"), WIDTH_MODES, "[canvas] width_mode"
            ),
            min_legible_size=_number(
                mapping.get("min_legible_size", 9.0), "[canvas] min_legible_size"
            ),
            ink=_colour(mapping.get("ink", "#1a1a1a"), "[canvas] ink"),
        )


@dataclass(frozen=True)
class FontStacks:
    """The families to measure and to name in the output, in preference order."""

    sans: tuple[str, ...] = ("sans-serif",)
    serif: tuple[str, ...] = ("serif",)
    mono: tuple[str, ...] = ("monospace",)
    default: str = "sans"

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
    heading: float = 13.0
    body: float = 11.0
    label: float = 10.0

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
    scale_max: float = 1.0

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
    line_height: float = 1.35
    corner_radius: float = 4.0

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> BoxStyle:
        _reject_unknown(mapping, ("padding", "line_height", "corner_radius"), "[box]")
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
        )


@dataclass(frozen=True)
class EdgeStyle:
    """Line constants shared by every edge role."""

    stroke_width: float = 1.5
    min_shaft_length: float = 16.0
    head_length: float = 6.0
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

    The vocabulary is the fill patterns, not colours, and the entries must be
    distinct — which makes greyscale legibility structural here rather than
    checked afterwards. It is the same rule the role table lives under, arrived
    at from the other direction: roles must differ in a non-colour channel, and
    these differ in nothing else.
    """

    fills: tuple[str, ...] = ("hatch", "dots", "cross", "grid", "none")
    gap: float = 0.3
    """How much of a category's band is left empty around its bars, as a
    fraction. Zero draws bars that touch, which reads as one wide bar."""

    def fill_for(self, index: int) -> str:
        """The fill for the `index`-th filled mark, cycling if there are more."""
        return self.fills[index % len(self.fills)]

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> MarkStyle:
        _reject_unknown(mapping, ("fills", "gap"), "[mark]")
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
        gap = _number(mapping.get("gap", defaults.gap), "[mark] gap", positive=False)
        if not 0.0 <= gap < 1.0:
            raise ThemeError(f"[mark] gap: expected a fraction below 1, got {gap!r}")
        return cls(fills=tuple(fills), gap=gap)


@dataclass(frozen=True)
class TitleStyle:
    """Whether a diagram carries its own title. Off until the question is settled."""

    show: bool = False
    level: str = "title"

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
        keys = ("head", "tail", "stroke", "dash", "stroke_width")
        _reject_unknown(mapping, keys, where)
        return cls(
            head=_choice(mapping.get("head", base.head), EDGE_HEADS, f"{where} head"),
            tail=_choice(mapping.get("tail", base.tail), EDGE_HEADS, f"{where} tail"),
            stroke=_colour(mapping.get("stroke", base.stroke), f"{where} stroke"),
            dash=_dash(mapping.get("dash", base.dash), f"{where} dash"),
            stroke_width=_number(
                mapping.get("stroke_width", base.stroke_width), f"{where} stroke_width"
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
    "cycle",
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
        colours: set[str] = {"currentColor", "none", self.canvas.ink}
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

        So the head is scaled by weight. Floored at the theme's own
        `head_length`, because a light role's head still has to be large enough
        to see: the shaft may be as quiet as the theme likes, but *which way*
        is not the part that should get quieter.
        """
        width = getattr(self.role_for(role), "stroke_width", self.edge.stroke_width)
        return self.edge.head_length * max(1.0, width / self.edge.stroke_width)

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
    "LUMINANCE_DELTA",
    "NODE_ROLES",
    "NODE_SHAPES",
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
    "load_theme",
    "relative_luminance",
]
