"""A theme derived from a brand: CSS custom properties or W3C design tokens.

`drawspec theme from brand.css tokens.json` reads what a design system already
says — `--color-accent`, `--font-sans`, a `radius` — and writes the theme that
puts it where drawspec puts appearance, printing every token it did not use and
why. Local files only: there is no network access here, or anywhere in drawspec.

**A brand is a page's palette, and a drawspec SVG is not a page.** It inherits
the page's ink and draws no background, so it follows its host into dark mode,
and it never lets colour be the only thing telling two roles apart. A brand
import keeps all three:

* Backgrounds, surfaces and text colours are *not* applied — the drawing sits
  on the page's own. The brand's text colour becomes `[canvas] ink`, which only
  the `standalone` profile reads, because there the page is absent.
* Brand colours go only where the bundled `accent` theme puts colour: onto
  roles that already differ from their neighbours by weight, dash or shape, and
  onto `[mark] colours`, whose fill patterns stay distinct. The loader's
  greyscale check runs on the result like on any theme.
* A pinned colour does not follow the page, so it has to read on both: at
  least 3:1 — WCAG's figure for lines and shapes — against a white page *and*
  against a near-black one. A colour outside that band is darkened or lightened,
  hue kept, until it fits, and the report says so; `strict` refuses instead.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, cast

from drawspec.errors import ThemeError
from drawspec.text.fontlib import GENERIC_KEYWORDS, default_search_paths, resolve_stack
from drawspec.theme import Theme, load_theme, relative_luminance

#: The two pages a pinned colour has to read on: paper, and a dark-mode screen.
LIGHT_PAGE: Final = "#ffffff"
DARK_PAGE: Final = "#121212"

#: WCAG 2.2's floor for the parts of a graphic needed to understand it (1.4.11).
GRAPHIC_CONTRAST: Final = 3.0

#: WCAG 2.2's floor for body text (1.4.3) — the standalone ink is a text colour.
TEXT_CONTRAST: Final = 4.5

#: How far a brand's stroke weight may scale every line in the theme. Outside
#: it a `link` gets too faint to see, or a `strong` line outweighs its own label.
STROKE_FACTOR: Final = (0.75, 1.5)

#: The corner radii a box may take from a brand. A pill radius (`9999px`) would
#: make every box a pill, and a pill is what `start` and `terminal` look like.
RADIUS_RANGE: Final = (0.0, 12.0)

#: The line spacing a box may take from a brand, as a multiple of its type size.
LINE_HEIGHT_RANGE: Final = (1.2, 1.6)

#: CSS pixels per `rem` or `em`, the browser default.
REM: Final = 16.0

#: The file types read, by suffix. A W3C tokens file is `.tokens` or
#: `.tokens.json` by the format's own recommendation, or plain `.json`.
CSS_SUFFIXES: Final = (".css",)
TOKEN_SUFFIXES: Final = (".json", ".tokens")

#: Roles a brand colour is put on. The same five the `accent` theme colours, and
#: for the same reason: each already differs from its neighbours without colour.
ACCENT_NODE_ROLES: Final = ("emphasis", "terminal")
ACCENT_EDGE_ROLES: Final = ("strong",)
MUTED_NODE_ROLES: Final = ("note", "group")
MUTED_EDGE_ROLES: Final = ("link",)


# ---------------------------------------------------------------------------
# What came out
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Note:
    """What became of one token: `used`, `adjusted` or `ignored`, and why."""

    outcome: str
    token: str
    source: str
    detail: str

    def line(self) -> str:
        return f"{self.outcome:<9} {self.token} ({self.source}): {self.detail}"


@dataclass(frozen=True)
class DerivedTheme:
    """A theme derived from brand files, as TOML, with what was and was not used."""

    name: str
    mapping: Mapping[str, Any]
    """The theme as a mapping, merged over the default when loaded."""
    toml: str
    """The theme file, ready to write."""
    theme: Theme
    """The loaded theme, so every invariant has already run."""
    notes: tuple[Note, ...] = ()

    @property
    def report(self) -> str:
        return "\n".join(note.line() for note in self.notes)


# ---------------------------------------------------------------------------
# Reading tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    """One brand token, read and resolved, before it is mapped."""

    label: str
    """As written: `--color-accent` or `color.accent`."""
    source: str
    value: object
    type: str = ""
    """The W3C `$type`, or empty when the file does not say (CSS never does)."""
    order: int = 0
    file: int = 0
    """Which of the files given it came from, so a later file wins a tie."""
    out_of_scope: str = ""
    """Why it is not read at all — a dark-mode override, say. Empty when it is."""

    @property
    def words(self) -> tuple[str, ...]:
        return _words(self.label)


def _words(label: str) -> tuple[str, ...]:
    """`--colorBrand_primary.500` → `("color", "brand", "primary", "500")`."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", label.lstrip("-"))
    return tuple(word for word in re.split(r"[^a-z0-9]+", spaced.lower()) if word)


def read_tokens(paths: Sequence[str | Path]) -> list[Token]:
    """Every token in `paths`, in order; a later file's token wins a shared name."""
    tokens: list[Token] = []
    for position, raw in enumerate(paths):
        text = str(raw)
        if re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE):
            raise ThemeError(
                f"{text}: drawspec reads local files only and makes no network request. "
                f"Save the stylesheet or tokens file and pass its path."
            )
        path = Path(raw)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise ThemeError(f"brand file could not be read: {path} ({error})") from None
        name = path.name.lower()
        if name.endswith(CSS_SUFFIXES):
            read = _css_tokens(content, path.name)
        elif name.endswith(TOKEN_SUFFIXES):
            read = _json_tokens(content, path.name)
        else:
            raise ThemeError(
                f"{path}: not a brand file drawspec reads. Pass a .css file of custom "
                f"properties or a W3C design-tokens .json (or .tokens) file."
            )
        if not read:
            raise ThemeError(
                f"{path}: no tokens found — no custom properties (`--name: value`) in a "
                f"stylesheet, or no `$value` in a tokens file."
            )
        tokens.extend(
            replace(token, order=len(tokens) + index, file=position)
            for index, token in enumerate(read)
        )
    return tokens


# -- CSS ---------------------------------------------------------------------

_ROOT_SELECTORS: Final = (":root", "html", ":host")


def _css_tokens(text: str, source: str) -> list[Token]:
    """Custom properties, resolved through `var()`, with where each was set.

    Only `:root` (or `html`, `:host`) at the top level — or inside `@layer`,
    which changes precedence and not scope — is the page's own palette.
    Anything under `@media` or another selector is a variant of it, a dark mode
    most often, and drawspec's answer to dark mode is `currentColor`.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    found: list[tuple[str, str, str]] = []  # name, value, why out of scope
    stack: list[str] = []
    start = 0
    depth = 0
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth:
            continue
        elif char == "{":
            stack.append(" ".join(text[start:index].split()))
            start = index + 1
        elif char in ";}":
            _css_declaration(text[start:index], stack, found)
            if char == "}" and stack:
                stack.pop()
            start = index + 1

    values: dict[str, str] = {}
    last: dict[str, int] = {}
    for index, (name, value, why) in enumerate(found):
        if not why:
            values[name] = value
            last[name] = index
    tokens: list[Token] = []
    for index, (name, value, why) in enumerate(found):
        if why:
            tokens.append(Token(name, source, value, out_of_scope=why))
            continue
        if last[name] != index:
            continue  # redeclared later in scope; the last one wins, as in the cascade
        resolved = _resolve_var(value, values, (name,))
        if resolved is None:
            tokens.append(Token(name, source, value, out_of_scope="a `var()` that never resolves"))
        else:
            tokens.append(Token(name, source, resolved))
    return tokens


def _css_declaration(text: str, stack: list[str], found: list[tuple[str, str, str]]) -> None:
    text = text.strip()
    if not text.startswith("--") or ":" not in text:
        return
    name, _, value = text.partition(":")
    value = re.sub(r"\s*!important\s*$", "", value.strip())
    why = ""
    for prelude in stack:
        if prelude.startswith("@layer"):
            continue
        if prelude.startswith("@"):
            why = f"set inside `{prelude}` — a variant of the palette, not the palette"
            break
        selectors = [selector.strip() for selector in prelude.split(",")]
        if not any(selector in _ROOT_SELECTORS for selector in selectors):
            why = f"set under `{prelude}`, not `:root` — a variant of the palette"
            break
    if not stack:
        why = "set outside any rule"
    found.append((name.strip(), value, why))


def _resolve_var(value: str, values: Mapping[str, str], seen: tuple[str, ...]) -> str | None:
    """`value` with every `var(--x, fallback)` replaced, or None if one never resolves."""
    out = value
    for _ in range(32):
        at = out.find("var(")
        if at < 0:
            return out
        depth = 0
        end = -1
        for index in range(at + 3, len(out)):
            if out[index] == "(":
                depth += 1
            elif out[index] == ")":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end < 0:
            return None
        inner = out[at + 4 : end]
        name, _, fallback = inner.partition(",")
        name = name.strip()
        if name in values and name not in seen:
            replacement = _resolve_var(values[name], values, (*seen, name))
        elif fallback.strip():
            replacement = _resolve_var(fallback.strip(), values, seen)
        else:
            replacement = None
        if replacement is None:
            return None
        out = out[:at] + replacement + out[end + 1 :]
    return None


# -- W3C design tokens -------------------------------------------------------


def _json_tokens(text: str, source: str) -> list[Token]:
    """Tokens from a W3C design-tokens file: groups, `$type` inherited, aliases resolved."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ThemeError(f"{source}: not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise ThemeError(f"{source}: a tokens file is a JSON object of groups and tokens")
    raw: list[tuple[str, object, str]] = []

    def walk(node: Mapping[str, Any], path: tuple[str, ...], inherited: str) -> None:
        kind = node.get("$type", inherited)
        kind = kind if isinstance(kind, str) else inherited
        if "$value" in node:
            raw.append((".".join(path), node["$value"], kind))
            return
        for key, child in node.items():
            if not key.startswith("$") and isinstance(child, dict):
                walk(child, (*path, key), kind)

    walk(data, (), "")
    by_path = {path: (value, kind) for path, value, kind in raw}
    tokens: list[Token] = []
    for path, value, kind in raw:
        resolved, resolved_kind = value, kind
        seen = {path}
        while isinstance(resolved, str) and re.fullmatch(r"\{[^{}]+\}", resolved.strip()):
            target = resolved.strip()[1:-1]
            if target in seen or target not in by_path:
                resolved = None
                break
            seen.add(target)
            resolved, target_kind = by_path[target]
            resolved_kind = resolved_kind or target_kind
        if resolved is None:
            tokens.append(
                Token(path, source, value, kind, out_of_scope="an alias that never resolves")
            )
        else:
            tokens.append(Token(path, source, resolved, resolved_kind))
    return tokens


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def parse_colour(value: object) -> tuple[str, float] | None:
    """`(#rrggbb, alpha)` from a CSS colour or a W3C colour object, or None."""
    if isinstance(value, dict):
        hex_value = value.get("hex")
        alpha = value.get("alpha", 1.0)
        alpha = float(alpha) if isinstance(alpha, int | float) else 1.0
        if isinstance(hex_value, str):
            parsed = parse_colour(hex_value)
            return (parsed[0], alpha) if parsed else None
        components = value.get("components")
        if (
            value.get("colorSpace") == "srgb"
            and isinstance(components, list)
            and len(components) == 3
            and all(isinstance(c, int | float) for c in components)
        ):
            return _hex(*(float(c) * 255 for c in components)), alpha
        return None
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    match = re.fullmatch(r"#([0-9a-f]{3,8})", text)
    if match:
        digits = match.group(1)
        if len(digits) in (3, 4):
            digits = "".join(digit * 2 for digit in digits)
        if len(digits) not in (6, 8):
            return None
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
        return "#" + digits[:6], alpha
    match = re.fullmatch(r"(rgba?|hsla?)\((.*)\)", text)
    if not match:
        return None
    parts = [part for part in re.split(r"[\s,/]+", match.group(2).strip()) if part]
    if len(parts) not in (3, 4):
        return None
    try:
        alpha = _fraction(parts[3]) if len(parts) == 4 else 1.0
        if match.group(1).startswith("rgb"):
            channels = [
                float(part[:-1]) * 2.55 if part.endswith("%") else float(part) for part in parts[:3]
            ]
            return _hex(*channels), alpha
        hue = float(parts[0].removesuffix("deg"))
        saturation, lightness = _fraction(parts[1]), _fraction(parts[2])
    except ValueError:
        return None
    return _hex(*_hsl_to_rgb(hue, saturation, lightness)), alpha


def _fraction(part: str) -> float:
    return float(part[:-1]) / 100 if part.endswith("%") else float(part)


def _hsl_to_rgb(hue: float, saturation: float, lightness: float) -> tuple[float, float, float]:
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    sector = (hue % 360) / 60
    second = chroma * (1 - abs(sector % 2 - 1))
    red, green, blue = [
        (chroma, second, 0.0),
        (second, chroma, 0.0),
        (0.0, chroma, second),
        (0.0, second, chroma),
        (second, 0.0, chroma),
        (chroma, 0.0, second),
    ][int(sector) % 6]
    base = lightness - chroma / 2
    return (red + base) * 255, (green + base) * 255, (blue + base) * 255


def _hex(red: float, green: float, blue: float) -> str:
    return "#" + "".join(
        f"{max(0, min(255, round(channel))):02x}" for channel in (red, green, blue)
    )


def _channels(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def contrast(first: str, second: str) -> float:
    """WCAG contrast ratio between two hex colours, from 1 to 21."""
    one = relative_luminance(first) or 0.0
    two = relative_luminance(second) or 0.0
    return (max(one, two) + 0.05) / (min(one, two) + 0.05)


def fit_colour(colour: str, *, minimum: float, pages: Sequence[str]) -> str | None:
    """`colour`, darkened or lightened with its hue kept, until it reads on every page.

    Darkening scales the channels towards black and lightening mixes towards
    white, the least of either that clears `minimum` on every page in `pages`.
    None when no amount of either does.
    """

    def reads(candidate: str) -> bool:
        return all(contrast(candidate, page) >= minimum for page in pages)

    if reads(colour):
        return colour
    red, green, blue = _channels(colour)
    steps = 400
    candidates: list[tuple[float, str]] = []
    for towards in (0.0, 255.0):

        def mixed(amount: float, towards: float = towards) -> str:
            return _hex(*(channel + (towards - channel) * amount for channel in (red, green, blue)))

        # The first step that reads, walked rather than bisected: moving towards
        # black gains contrast on paper and loses it on a dark screen, so the
        # predicate is a window, not a threshold.
        first = next((step for step in range(steps + 1) if reads(mixed(step / steps))), None)
        if first is not None:
            candidates.append((first / steps, mixed(first / steps)))
    if not candidates:
        return None
    return min(candidates)[1]


def _dimension(value: object) -> float | None:
    """A length in CSS pixels: `6px`, `0.375rem`, `6`, or `{"value": 6, "unit": "px"}`."""
    if isinstance(value, dict):
        amount, unit = value.get("value"), value.get("unit", "px")
        if isinstance(amount, int | float) and not isinstance(amount, bool):
            return float(amount) * (REM if unit in ("rem", "em") else 1.0)
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(-?\d*\.?\d+)\s*(px|rem|em)?\s*", value)
    if not match:
        return None
    return float(match.group(1)) * (REM if match.group(2) in ("rem", "em") else 1.0)


def _unitless(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"\s*\d*\.?\d+\s*", value):
        return float(value)
    return None


def _font_stack(value: object) -> tuple[str, ...]:
    """A family stack from a CSS `font-family` value or a W3C `fontFamily`."""
    if isinstance(value, list):
        entries = [entry for entry in value if isinstance(entry, str)]
    elif isinstance(value, str):
        entries = re.findall(r"""\s*("[^"]*"|'[^']*'|[^,]+)\s*(?:,|$)""", value)
    else:
        return ()
    return tuple(entry.strip().strip("\"'").strip() for entry in entries if entry.strip("\"' "))


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

_COLOUR_WORDS: Final = frozenset({"color", "colour", "colors", "colours", "palette"})
_STATE_WORDS: Final = frozenset(
    {"hover", "active", "focus", "pressed", "disabled", "visited", "selected", "checked"}
)
_BACKGROUND_WORDS: Final = frozenset(
    {"bg", "background", "backdrop", "surface", "canvas", "page", "paper", "fill", "overlay"}
)
_STATUS_WORDS: Final = frozenset(
    {
        "success",
        "warning",
        "warn",
        "danger",
        "error",
        "info",
        "positive",
        "negative",
        "critical",
        "caution",
        "notice",
        "alert",
        "destructive",
    }
)
_BORDER_WORDS: Final = frozenset({"border", "divider", "outline", "separator", "rule", "ring"})
_ON_WORDS: Final = frozenset({"on", "inverse", "inverted", "contrast"})
_TEXT_WORDS: Final = frozenset({"text", "foreground", "fg", "ink", "body", "content", "copy"})
_SLOT_WORDS: Final[Mapping[str, tuple[str, ...]]] = {
    "accent": ("accent", "primary", "brand", "highlight", "emphasis", "key"),
    "secondary": ("secondary",),
    "tertiary": ("tertiary",),
    "muted": ("muted", "subtle", "neutral", "quiet", "grey", "gray", "slate"),
}
_FONT_WORDS: Final = frozenset({"font", "fonts", "family", "families", "typeface", "typography"})
_NEUTRAL_SIZES: Final = frozenset({"md", "medium", "base", "default", "m", "normal", "regular"})


@dataclass
class _Candidate:
    token: Token
    rank: tuple[float, ...]
    value: object


@dataclass
class _Mapper:
    notes: dict[int, Note] = field(default_factory=dict)
    slots: dict[str, list[_Candidate]] = field(default_factory=dict)

    def ignore(self, token: Token, why: str) -> None:
        self.notes[token.order] = Note("ignored", token.label, token.source, why)

    def offer(self, slot: str, token: Token, rank: tuple[float, ...], value: object) -> None:
        """A candidate for `slot`. How well the name fits ranks first (its first two
        keys), then the file — a later one wins — then the rest, then order."""
        self.slots.setdefault(slot, []).append(
            _Candidate(token, (*rank[:2], -token.file, *rank[2:], token.order), value)
        )


def _extra(words: Sequence[str], *known: Iterable[str]) -> int:
    """How many words a name has beyond the ones that placed it — the shade, the size."""
    drop: set[str] = set(_NEUTRAL_SIZES)
    for group in known:
        drop.update(group)
    return sum(1 for word in words if word not in drop)


def _shade(words: Sequence[str]) -> float:
    """Distance from the middle of a numbered scale, so `500` beats `50` and `950`."""
    numbers = [int(word) for word in words if word.isdigit()]
    return abs(numbers[-1] - 600) / 1000 if numbers else 0.0


def _classify(token: Token, mapper: _Mapper) -> None:
    """Offer `token` to the slot it fits, or record why it fits none."""
    words = token.words
    word_set = set(words)
    kind = token.type
    value = token.value

    if token.out_of_scope:
        mapper.ignore(token, f"{token.out_of_scope}; drawspec follows dark mode with currentColor")
        return

    colour = parse_colour(value) if kind in ("", "color") else None
    if kind == "color" or (colour is not None and kind == ""):
        if colour is None:
            mapper.ignore(
                token, f"{value!r} is not a colour form drawspec reads; write a hex value"
            )
            return
        _classify_colour(token, word_set, words, colour, mapper)
        return

    is_font_word = bool(word_set & _FONT_WORDS)
    if kind == "fontFamily" or (kind == "" and is_font_word and _is_family_value(value, word_set)):
        _classify_font(token, word_set, words, mapper)
        return
    if kind in ("fontSize",) or (
        word_set & {"size", "sizes", "text", "font"} and "size" in word_set
    ):
        mapper.ignore(
            token,
            "a type size: drawspec's scale is relative to the canvas, which the page scales "
            "to its column, so a CSS pixel size says nothing about it — set [scale] by hand",
        )
        return
    if kind == "fontWeight" or ("weight" in word_set and is_font_word):
        mapper.ignore(token, "a weight: in drawspec bold means a lead, so it is not a theme key")
        return
    if (
        ("line" in word_set and "height" in word_set)
        or "leading" in word_set
        or kind == "lineHeight"
    ):
        number = _unitless(value)
        if number is None:
            mapper.ignore(token, "a line height with a unit; drawspec reads a unitless multiple")
        else:
            rank = (
                0.0 if word_set & {"body", "base", "text"} else 1.0,
                _extra(words, {"line", "height", "leading", "body", "base", "text", "font"}),
            )
            mapper.offer("line_height", token, rank, number)
        return
    if word_set & {"radius", "radii", "rounded", "corner", "corners"} or kind == "borderRadius":
        length = _dimension(value)
        if length is None:
            mapper.ignore(token, f"{value!r} is not a length drawspec reads (px, rem or a number)")
        else:
            known = {"radius", "radii", "rounded", "corner", "corners", "border"}
            mapper.offer("radius", token, (_extra(words, known),), length)
        return
    if (
        word_set & {"border", "stroke", "line", "outline"}
        and word_set & {"width", "weight", "thickness"}
    ) or kind == "strokeWidth":
        length = _dimension(value)
        if length is None:
            mapper.ignore(token, f"{value!r} is not a length drawspec reads (px, rem or a number)")
        else:
            known = {"border", "stroke", "line", "outline", "width", "weight", "thickness"}
            mapper.offer("stroke", token, (_extra(words, known),), length)
        return
    if word_set & {
        "space",
        "spacing",
        "gap",
        "padding",
        "margin",
        "size",
        "sizes",
        "inset",
        "gutter",
        "container",
    }:
        mapper.ignore(
            token,
            "spacing: drawspec derives every gap from measured text and the theme's padding",
        )
        return
    if word_set & {"shadow", "shadows", "elevation", "blur"} or kind == "shadow":
        mapper.ignore(token, "a shadow: drawspec draws none, so a diagram stays flat ink")
        return
    if word_set & {"duration", "easing", "motion", "transition", "animation", "delay"} or kind in (
        "duration",
        "cubicBezier",
        "transition",
    ):
        mapper.ignore(token, "motion: a drawing does not move")
        return
    mapper.ignore(token, "no theme key fits it")


def _is_family_value(value: object, word_set: set[str]) -> bool:
    if word_set & {"size", "sizes", "weight", "height", "spacing", "tracking", "leading"}:
        return False
    if isinstance(value, list):
        return True
    return isinstance(value, str) and _dimension(value) is None and _unitless(value) is None


def _classify_colour(
    token: Token,
    word_set: set[str],
    words: Sequence[str],
    colour: tuple[str, float],
    mapper: _Mapper,
) -> None:
    hex_value, alpha = colour
    if word_set & _STATE_WORDS:
        mapper.ignore(token, "an interaction state: a drawing has none")
        return
    if word_set & _BACKGROUND_WORDS:
        mapper.ignore(
            token,
            "a background: drawspec draws none, so the SVG sits on the page's own and "
            "follows it into dark mode",
        )
        return
    if word_set & _STATUS_WORDS:
        mapper.ignore(
            token,
            "a status colour: colour may point but never carry, so drawspec marks added, "
            "changed and removed by line and shape",
        )
        return
    if word_set & _BORDER_WORDS:
        mapper.ignore(
            token,
            "a border colour: it is chosen to be faint against the page's own background; "
            "drawspec's lines are the page's ink",
        )
        return
    if word_set & _ON_WORDS:
        mapper.ignore(token, "a colour for text on a filled surface: drawspec fills none")
        return
    roles = [slot for slot, names in _SLOT_WORDS.items() if word_set & set(names)]
    if word_set & _TEXT_WORDS:
        if roles or len(words) - len(word_set & (_TEXT_WORDS | _COLOUR_WORDS)) > 1:
            mapper.ignore(
                token,
                "a quieter text colour: drawspec's text is the page's ink, never pinned",
            )
            return
        ink_rank = (float(_extra(words, _TEXT_WORDS, _COLOUR_WORDS)),)
        mapper.offer("ink", token, ink_rank, (hex_value, alpha))
        return
    if not roles:
        mapper.ignore(
            token,
            "no role it fits: drawspec colours only what a reader should look at first "
            "(accent, primary, brand) and what is quieter (muted, neutral)",
        )
        return
    slot = roles[0]
    priority = min(_SLOT_WORDS[slot].index(word) for word in words if word in _SLOT_WORDS[slot])
    fits = fit_colour(hex_value, minimum=GRAPHIC_CONTRAST, pages=(LIGHT_PAGE, DARK_PAGE))
    rank = (
        float(priority),
        _extra(words, _COLOUR_WORDS, _SLOT_WORDS[slot], {"brand"})
        - len([word for word in words if word.isdigit()]),
        0.0 if fits == hex_value else 1.0,
        _shade(words),
    )
    mapper.offer(slot, token, rank, (hex_value, alpha))


def _classify_font(token: Token, word_set: set[str], words: Sequence[str], mapper: _Mapper) -> None:
    stack = _font_stack(token.value)
    if not stack:
        mapper.ignore(token, "an empty font stack")
        return
    if word_set & {"heading", "headings", "display", "title", "headline", "h1", "h2"}:
        mapper.ignore(
            token,
            "a heading face: drawspec sets every level of a drawing in one family, the body's",
        )
        return
    if word_set & {"mono", "monospace", "code"}:
        mapper.offer("font.mono", token, (0.0,), stack)
        return
    if "serif" in word_set and "sans" not in word_set:
        mapper.offer("font.serif", token, (0.0,), stack)
        return
    if "sans" in word_set:
        priority = 0.0
    elif word_set & {"body", "base", "text", "copy"}:
        priority = 1.0
    elif word_set & {"ui", "default", "primary", "interface"}:
        priority = 2.0
    elif len(word_set - _FONT_WORDS) == 0:
        priority = 3.0
    else:
        mapper.ignore(token, "a font for something drawspec does not draw")
        return
    mapper.offer("font.body", token, (priority,), stack)


# ---------------------------------------------------------------------------
# Assembling the theme
# ---------------------------------------------------------------------------

_SLOT_NAMES: Final = {
    "accent": "accent colour",
    "secondary": "secondary colour",
    "tertiary": "tertiary colour",
    "muted": "muted colour",
    "ink": "text colour",
    "font.body": "body family",
    "font.serif": "serif family",
    "font.mono": "monospace family",
    "radius": "corner radius",
    "stroke": "stroke weight",
    "line_height": "line height",
}


def _number_text(value: float) -> str:
    return f"{round(value, 2)!r}" if float(value) != int(value) else f"{float(value):.1f}"


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return _number_text(float(value))
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(entry) for entry in value) + "]"
    raise TypeError(f"no TOML spelling for {value!r}")


def _generic_for(stack: Sequence[str]) -> str:
    """Which font role a stack's own generic keyword asks for, or empty."""
    for entry in reversed(stack):
        role = GENERIC_KEYWORDS.get(entry.lower())
        if role:
            return role
    return ""


def derive_theme(
    paths: Sequence[str | Path], name: str | None = None, *, strict: bool = False
) -> DerivedTheme:
    """A theme from brand files, validated, with a note for every token read.

    Raises:
        ThemeError: a file cannot be read; nothing in the files maps onto a theme
            key; a colour has to be adjusted under `strict`; or the result fails
            a theme invariant.
    """
    if not paths:
        raise ThemeError("theme from: name at least one brand file")
    tokens = read_tokens(paths)
    sources = [Path(path).name for path in paths]
    mapper = _Mapper()
    for token in tokens:
        _classify(token, mapper)

    default = load_theme(None)
    sections: dict[str, dict[str, object]] = {}
    comments: dict[tuple[str, str], str] = {}
    refusals: list[str] = []

    def put(section: str, key: str, value: object, comment: str) -> None:
        sections.setdefault(section, {})[key] = value
        comments[(section, key)] = comment

    def chosen(slot: str) -> _Candidate | None:
        candidates = sorted(mapper.slots.get(slot, []), key=lambda candidate: candidate.rank)
        if not candidates:
            return None
        for other in candidates[1:]:
            mapper.ignore(
                other.token,
                f"another {_SLOT_NAMES[slot]}: drawspec takes one, and took "
                f"{candidates[0].token.label}",
            )
        return candidates[0]

    def note(candidate: _Candidate, outcome: str, detail: str) -> None:
        token = candidate.token
        mapper.notes[token.order] = Note(outcome, token.label, token.source, detail)

    def brand_colour(candidate: _Candidate, minimum: float, pages: Sequence[str]) -> str | None:
        """The candidate's colour, fitted to `pages`, with its note written."""
        hex_value, alpha = cast(tuple[str, float], candidate.value)
        fitted = fit_colour(hex_value, minimum=minimum, pages=pages)
        where = " and ".join(
            f"{contrast(fitted or hex_value, page):.1f}:1 on {page}" for page in pages
        )
        dropped = (
            f"; its alpha {alpha:.2f} dropped, as drawspec strokes are opaque" if alpha < 1 else ""
        )
        if fitted is None:
            refusals.append(
                f"{candidate.token.label}: {hex_value} cannot be made to read on {', '.join(pages)}"
            )
            return None
        if fitted != hex_value:
            darker = (relative_luminance(fitted) or 0) < (relative_luminance(hex_value) or 0)
            short = " and ".join(
                f"{contrast(hex_value, page):.1f}:1 on {page}"
                for page in pages
                if contrast(hex_value, page) < minimum
            )
            message = (
                f"{hex_value} is {short}, under the {minimum:g}:1 a "
                f"{'line' if minimum == GRAPHIC_CONTRAST else 'text colour'} needs; "
                f"{'darkened' if darker else 'lightened'} to {fitted} ({where}){dropped}"
            )
            if strict:
                refusals.append(f"{candidate.token.label}: {message}")
            note(candidate, "adjusted", message)
        return fitted

    # -- colours
    pages = (LIGHT_PAGE, DARK_PAGE)
    palette: dict[str, str] = {}
    for slot in ("accent", "secondary", "tertiary", "muted"):
        candidate = chosen(slot)
        if candidate is None:
            continue
        colour = brand_colour(candidate, GRAPHIC_CONTRAST, pages)
        if colour is None:
            continue
        palette[slot] = colour
        label = candidate.token.label
        targets: list[str] = []
        if slot == "accent":
            for role in ACCENT_NODE_ROLES:
                put(f"role.{role}", "stroke", colour, label)
            for role in ACCENT_EDGE_ROLES:
                put(f"edge_role.{role}", "stroke", colour, label)
            targets = [
                *(f"[role.{r}]" for r in ACCENT_NODE_ROLES),
                *(f"[edge_role.{r}]" for r in ACCENT_EDGE_ROLES),
            ]
            used = f"stroke of {', '.join(targets)}; [mark] colours[0]"
        elif slot == "muted":
            for role in MUTED_NODE_ROLES:
                put(f"role.{role}", "stroke", colour, label)
            for role in MUTED_EDGE_ROLES:
                put(f"edge_role.{role}", "stroke", colour, label)
            targets = [
                *(f"[role.{r}]" for r in MUTED_NODE_ROLES),
                *(f"[edge_role.{r}]" for r in MUTED_EDGE_ROLES),
            ]
            used = f"stroke of {', '.join(targets)}; [mark] colours[3] and [4]"
        else:
            used = f"[mark] colours[{1 if slot == 'secondary' else 2}]"
        if candidate.token.order not in mapper.notes:
            note(candidate, "used", f"{colour} → {used}")
        else:
            existing = mapper.notes[candidate.token.order]
            mapper.notes[candidate.token.order] = Note(
                existing.outcome, existing.token, existing.source, f"{existing.detail} → {used}"
            )
    if palette:
        fills = len(default.mark.fills)
        order = ["accent", "secondary", "tertiary", "muted", "muted"]
        colours = [palette.get(slot, "currentColor") for slot in order]
        colours += ["currentColor"] * (fills - len(colours))
        put("mark", "colours", colours[:fills], "accent, secondary, tertiary, muted, muted")

    ink = chosen("ink")
    if ink is not None:
        colour = brand_colour(ink, TEXT_CONTRAST, (LIGHT_PAGE,))
        if colour is not None:
            put("canvas", "ink", colour, f"{ink.token.label}, standalone profile only")
            detail = (
                f"{colour} → [canvas] ink, read by the standalone profile only; inline "
                f"SVG keeps the page's own ink"
            )
            if ink.token.order in mapper.notes:
                existing = mapper.notes[ink.token.order]
                mapper.notes[ink.token.order] = Note(
                    existing.outcome,
                    existing.token,
                    existing.source,
                    f"{existing.detail} → [canvas] ink (standalone profile only)",
                )
            else:
                note(ink, "used", detail)

    # -- fonts
    search = default_search_paths()

    def font(candidate: _Candidate, role: str) -> None:
        stack = list(cast(tuple[str, ...], candidate.value))
        generic = _generic_for(stack)
        if not generic:
            stack.append({"sans": "sans-serif", "serif": "serif", "mono": "monospace"}[role])
        put("font", role, stack, candidate.token.label)
        resolved = resolve_stack(role, tuple(stack), search)
        where = (
            f"; {stack[0]} is not installed here, so it is measured as {resolved.family} "
            f"until it is (render warns)"
            if resolved.substituted
            else ""
        )
        note(candidate, "used", f"→ [font] {role}{where}")

    body = chosen("font.body")
    serif = chosen("font.serif")
    mono = chosen("font.mono")
    if body is not None:
        if _generic_for(cast(tuple[str, ...], body.value)) == "serif":
            if serif is not None:
                mapper.ignore(
                    serif.token,
                    f"another serif family: {body.token.label} is a serif body face and took "
                    f"[font] serif",
                )
                serif = None
            font(body, "serif")
            put("font", "default", "serif", f"{body.token.label} is a serif face")
            existing = mapper.notes[body.token.order]
            mapper.notes[body.token.order] = Note(
                existing.outcome,
                existing.token,
                existing.source,
                f'{existing.detail}, and [font] default = "serif": it is a serif body face',
            )
        else:
            font(body, "sans")
    if serif is not None:
        font(serif, "serif")
    if mono is not None:
        font(mono, "mono")

    # -- geometry
    radius = chosen("radius")
    if radius is not None:
        value = cast(float, radius.value)
        clamped = min(max(value, RADIUS_RANGE[0]), RADIUS_RANGE[1])
        put("box", "corner_radius", clamped, radius.token.label)
        if clamped != value:
            note(
                radius,
                "adjusted",
                f"{_number_text(value)}px clamped to {_number_text(clamped)} → [box] "
                f"corner_radius: a rounder box starts to read as a pill, which is what "
                f"start and terminal look like",
            )
        else:
            note(radius, "used", f"{_number_text(value)} → [box] corner_radius")

    stroke = chosen("stroke")
    if stroke is not None:
        value = cast(float, stroke.value)
        base = default.edge.stroke_width
        factor = value / base if value > 0 else STROKE_FACTOR[0]
        clamped = min(max(factor, STROKE_FACTOR[0]), STROKE_FACTOR[1])
        put("edge", "stroke_width", round(base * clamped, 2), stroke.token.label)
        for name_, node_role in default.roles.items():
            put(
                f"role.{name_}",
                "stroke_width",
                round(node_role.stroke_width * clamped, 2),
                f"{stroke.token.label}, scaled",
            )
        for name_, edge_role in default.edge_roles.items():
            put(
                f"edge_role.{name_}",
                "stroke_width",
                round(edge_role.stroke_width * clamped, 2),
                f"{stroke.token.label}, scaled",
            )
        what = (
            f"every stroke weight scaled by {clamped:.2f}, so their ratios — what tells a "
            f"strong line from a link in greyscale — hold"
        )
        if clamped != factor:
            note(
                stroke,
                "adjusted",
                f"{_number_text(value)}px is past the {STROKE_FACTOR[0]} to "
                f"{STROKE_FACTOR[1]} times drawspec scales its lines by; {what}",
            )
        else:
            note(stroke, "used", f"{_number_text(value)} → {what}")

    line_height = chosen("line_height")
    if line_height is not None:
        value = cast(float, line_height.value)
        clamped = min(max(value, LINE_HEIGHT_RANGE[0]), LINE_HEIGHT_RANGE[1])
        put("box", "line_height", clamped, line_height.token.label)
        if clamped != value:
            note(
                line_height,
                "adjusted",
                f"{value:g} clamped to {clamped:g} → [box] line_height: "
                f"a box's lines past that read as separate labels",
            )
        else:
            note(line_height, "used", f"{value:g} → [box] line_height")

    if refusals:
        raise ThemeError(
            "theme from: refused"
            + (" under --strict" if strict else "")
            + ":\n  "
            + "\n  ".join(refusals)
        )
    if not sections:
        listed = "\n  ".join(note_.line() for _, note_ in sorted(mapper.notes.items()))
        raise ThemeError(
            f"theme from: nothing in {', '.join(sources)} maps onto a theme key, so the "
            f"theme would be the default. What was read:\n  {listed}"
        )

    theme_name = name or _name_from(paths[0])
    mapping: dict[str, Any] = {"version": 1, "name": theme_name}
    for section, values in sections.items():
        target = mapping
        for part in section.split("."):
            target = target.setdefault(part, {})
        target.update(values)
    try:
        theme = load_theme(mapping)
    except ThemeError as error:  # pragma: no cover - the mapping keeps every invariant
        raise ThemeError(f"theme from: the derived theme was refused: {error}") from None

    notes = tuple(note_ for _, note_ in sorted(mapper.notes.items()))
    return DerivedTheme(
        name=theme_name,
        mapping=mapping,
        toml=_toml(theme_name, sources, sections, comments),
        theme=theme,
        notes=notes,
    )


def _name_from(path: str | Path) -> str:
    stem = Path(path).name.lower()
    for suffix in (".tokens.json", ".tokens", ".json", ".css"):
        stem = stem.removesuffix(suffix)
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "brand"


#: The order sections are written in: the order `docs/theme.md` reads them in.
_SECTION_ORDER: Final = ("canvas", "font", "box", "edge", "mark")


def _toml(
    name: str,
    sources: Sequence[str],
    sections: Mapping[str, Mapping[str, object]],
    comments: Mapping[tuple[str, str], str],
) -> str:
    def order(section: str) -> tuple[int, str]:
        if section in _SECTION_ORDER:
            return (_SECTION_ORDER.index(section), "")
        head, _, role = section.partition(".")
        vocabulary = list(load_theme(None).roles if head == "role" else load_theme(None).edge_roles)
        return (len(_SECTION_ORDER) + (0 if head == "role" else 1), f"{vocabulary.index(role):02d}")

    lines = [
        f"# drawspec theme {json.dumps(name)}, derived from {' and '.join(sources)} by",
        "# `drawspec theme from`. Merged over the default theme like any other, so it holds",
        "# only what the brand said. Every colour reads at 3:1 on a white page and on a",
        "# near-black one; strokes stay currentColor wherever the brand had nothing to say,",
        "# so the drawing still follows its page into dark mode.",
        "",
        "version = 1",
        f"name = {_toml_value(name)}",
    ]
    for section in sorted(sections, key=order):
        lines += ["", f"[{section}]"]
        values = sections[section]
        width = max(len(f"{key} = {_toml_value(value)}") for key, value in values.items())
        for key, value in values.items():
            entry = f"{key} = {_toml_value(value)}"
            comment = comments.get((section, key), "")
            lines.append(f"{entry:<{width}}  # {comment}" if comment else entry)
    return "\n".join(lines) + "\n"


__all__ = [
    "DARK_PAGE",
    "GRAPHIC_CONTRAST",
    "LIGHT_PAGE",
    "TEXT_CONTRAST",
    "DerivedTheme",
    "Note",
    "Token",
    "contrast",
    "derive_theme",
    "fit_colour",
    "parse_colour",
    "read_tokens",
]
