"""SVG emission — the single place styling happens, and therefore the single
place embedding safety is enforced.

Markdown is the sharpest constraint. Pasted inline, a diagram shares a document
with everything else on the page: a global `<style>` leaks into it, an `id`
collides with the diagram above it, and a hardcoded colour survives into dark
mode. The invariants below exist because of that, and they hold for every
rendering family at once because every family converges on `Scene` first.

Two profiles, differing in exactly one thing — what the SVG assumes about its
surroundings:

`inline`
    Pasted into Markdown or HTML. Colour is `currentColor`, so the diagram is
    drawn in the page's own ink and follows it into dark mode. A `viewBox` and
    no explicit dimensions, so it scales to its container.

`standalone`
    A linked `.svg`, or input to a PDF or PNG converter. There is nothing to
    inherit from, so the theme's ink is resolved to an explicit value and the
    root carries `width` and `height`.

Every other invariant is shared: no `<style>` element, ids namespaced to the
document, no embedded or referenced font, and no colour literal the theme did
not declare. `emit` runs that check on its own output and raises rather than
returning SVG that would fail it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import blake2b
from typing import Final
from xml.sax.saxutils import escape

from drawspec.errors import EmitError
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Rect, Scene, TextRun
from drawspec.theme import EdgeRole, NodeRole, Theme, load_theme

#: The two embedding profiles, per specification §1.
PROFILES: Final = ("inline", "standalone")

#: Coordinates are rounded to this many decimals before formatting. Three is
#: below a rendered pixel at any plausible scale, and rounding is what makes two
#: runs byte-identical rather than merely equal to within a float wobble.
PRECISION: Final = 3

_ID_PATTERN: Final = re.compile(r'\bid="([^"]*)"')
_URL_PATTERN: Final = re.compile(r"url\(#([^)]*)\)")
_PAINT_PATTERN: Final = re.compile(r'\b(fill|stroke)="([^"]*)"')
_FONT_REFERENCE_PATTERN: Final = re.compile(
    r"@font-face|<font-face|\bhref=|\.woff2?\b|\.ttf\b|\.otf\b|data:font", re.IGNORECASE
)


@dataclass(frozen=True)
class Violation:
    """One embedding-safety failure, named by the rule it broke."""

    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_number(value: float) -> str:
    """One number, one spelling — the determinism criterion starts here.

    Every coordinate in the output goes through this function, so `-0.0`, `2.0`
    and `2.0000001` cannot come out as three different strings on three
    different runs.
    """
    text = f"{value:.{PRECISION}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _points(points: tuple[tuple[float, float], ...]) -> str:
    return " ".join(f"{format_number(x)},{format_number(y)}" for x, y in points)


def _path_data(points: tuple[tuple[float, float], ...], *, closed: bool) -> str:
    if not points:
        return ""
    head, *rest = points
    parts = [f"M {format_number(head[0])} {format_number(head[1])}"]
    parts += [f"L {format_number(x)} {format_number(y)}" for x, y in rest]
    if closed:
        parts.append("Z")
    return " ".join(parts)


def _attributes(pairs: list[tuple[str, str]]) -> str:
    return "".join(f' {name}="{escape(value, {chr(34): "&quot;"})}"' for name, value in pairs)


def _font_family(stack: tuple[str, ...]) -> str:
    """A CSS font stack as an SVG attribute value.

    Single quotes around multi-word families, so the attribute itself can stay
    double-quoted and no escaping is needed for the common case.
    """
    return ", ".join(f"'{family}'" if " " in family else family for family in stack)


# ---------------------------------------------------------------------------
# Namespacing
# ---------------------------------------------------------------------------


def namespace_for(scene: Scene, theme: Theme, profile: str) -> str:
    """A short id prefix, derived from what is being drawn.

    Derived rather than random for two reasons: the same document must render to
    the same bytes twice, and two *different* diagrams on one page must not
    collide. A content digest gives both at once.
    """
    digest = blake2b(digest_size=5)
    digest.update(repr((scene.width, scene.height, scene.title, scene.description)).encode())
    for primitive in scene.primitives:
        digest.update(repr(primitive).encode())
    digest.update(f"{theme.name}|{profile}".encode())
    return f"ds{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# Styling — the only place a theme value becomes an attribute
# ---------------------------------------------------------------------------


def _resolve(colour: str, theme: Theme, profile: str) -> str:
    """`currentColor` stays inherited inline, and becomes ink standalone."""
    if profile == "standalone" and colour == "currentColor":
        return theme.canvas.ink
    return colour


def _fill_paint(role: NodeRole, namespace: str, theme: Theme, profile: str) -> str:
    if role.fill_pattern in ("hatch", "dots"):
        return f"url(#{namespace}-{role.fill_pattern})"
    if role.fill_pattern == "solid":
        return _resolve(role.fill, theme, profile)
    return "none"


def _stroke_attributes(
    role: NodeRole | EdgeRole, theme: Theme, profile: str
) -> list[tuple[str, str]]:
    attributes = [
        ("stroke", _resolve(role.stroke, theme, profile)),
        ("stroke-width", format_number(role.stroke_width)),
    ]
    if role.dash != "none":
        attributes.append(("stroke-dasharray", role.dash))
    return attributes


def _shape_attributes(
    primitive: Primitive, role: NodeRole | EdgeRole, namespace: str, theme: Theme, profile: str
) -> list[tuple[str, str]]:
    """Paint for one shape, decided by its role's kind.

    An edge role on a closed figure is an arrow head: filled with the edge's own
    colour and not stroked, so a head is the same weight as its shaft whatever
    the theme says. An edge role on an open figure is the shaft itself.
    """
    if isinstance(role, EdgeRole):
        if isinstance(primitive, Polygon) or (isinstance(primitive, Path) and primitive.closed):
            return [("fill", _resolve(role.stroke, theme, profile)), ("stroke", "none")]
        return [("fill", "none"), *_stroke_attributes(role, theme, profile)]
    return [
        ("fill", _fill_paint(role, namespace, theme, profile)),
        *_stroke_attributes(role, theme, profile),
    ]


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------


def _element(primitive: Primitive, namespace: str, theme: Theme, profile: str) -> str:
    role = theme.role_for(primitive.role)

    if isinstance(primitive, TextRun):
        return _text_element(primitive, theme, profile)

    paint = _shape_attributes(primitive, role, namespace, theme, profile)

    if isinstance(primitive, Rect):
        geometry = [
            ("x", format_number(primitive.x)),
            ("y", format_number(primitive.y)),
            ("width", format_number(primitive.width)),
            ("height", format_number(primitive.height)),
        ]
        # Corner treatment is a theme constant applied to every box, except that
        # a `pill` role is a box rounded until it stops looking like one.
        shape = role.shape if isinstance(role, NodeRole) else "rect"
        radius = primitive.height / 2 if shape == "pill" else theme.box.corner_radius
        if radius:
            geometry.append(("rx", format_number(radius)))
        return f"<rect{_attributes([*geometry, *paint])}/>"

    if isinstance(primitive, Ellipse):
        geometry = [
            ("cx", format_number(primitive.cx)),
            ("cy", format_number(primitive.cy)),
            ("rx", format_number(primitive.rx)),
            ("ry", format_number(primitive.ry)),
        ]
        return f"<ellipse{_attributes([*geometry, *paint])}/>"

    if isinstance(primitive, Polygon):
        return f"<polygon{_attributes([('points', _points(primitive.points)), *paint])}/>"

    if isinstance(primitive, Path):
        data = _path_data(primitive.points, closed=primitive.closed)
        return f"<path{_attributes([('d', data), *paint])}/>"

    raise EmitError(f"unknown scene primitive {type(primitive).__name__}")


def _text_element(run: TextRun, theme: Theme, profile: str) -> str:
    """One text run.

    Positioned by its baseline rather than by `dominant-baseline`, which renderers
    disagree about: the vertical centring in T6 computes the baseline from the
    font's own ascent and descent, so the answer is drawspec's and not the
    viewer's.
    """
    attributes = [
        ("x", format_number(run.x)),
        ("y", format_number(run.y)),
        ("font-family", _font_family(theme.font.stacks()[run.font])),
        ("font-size", format_number(theme.scale[run.level])),
        ("fill", _resolve("currentColor", theme, profile)),
    ]
    if run.weight != "normal":
        attributes.append(("font-weight", run.weight))
    if run.anchor != "start":
        attributes.append(("text-anchor", run.anchor))
    if run.rotate:
        attributes.append(
            (
                "transform",
                f"rotate({format_number(run.rotate)} "
                f"{format_number(run.x)} {format_number(run.y)})",
            )
        )
    return f"<text{_attributes(attributes)}>{escape(run.text)}</text>"


def _pattern_definitions(scene: Scene, namespace: str, theme: Theme, profile: str) -> list[str]:
    """`<pattern>` defs for the fill patterns this scene actually uses.

    Kept soft on purpose: a hatch that competes with the text on top of it makes
    the text illegible, so the strokes are thin and part-transparent. Opacity is
    not a colour, so this does not smuggle a value past the theme.
    """
    wanted = sorted(
        {
            role.fill_pattern
            for primitive in scene.primitives
            if isinstance(role := theme.role_for(primitive.role), NodeRole)
            and role.fill_pattern in ("hatch", "dots")
        }
    )
    ink = _resolve("currentColor", theme, profile)
    definitions = []
    for pattern in wanted:
        body = (
            f'<path d="M 0 4 L 4 0" stroke="{ink}" stroke-width="0.6" stroke-opacity="0.35"/>'
            if pattern == "hatch"
            else f'<circle cx="2" cy="2" r="0.6" fill="{ink}" fill-opacity="0.35"/>'
        )
        definitions.append(
            f'<pattern id="{namespace}-{pattern}" width="4" height="4" '
            f'patternUnits="userSpaceOnUse">{body}</pattern>'
        )
    return definitions


# ---------------------------------------------------------------------------
# The emitter
# ---------------------------------------------------------------------------


def emit(
    scene: Scene,
    theme: Theme | str | None = None,
    profile: str = "inline",
    *,
    namespace: str | None = None,
) -> str:
    """Serialise `scene` to SVG under `profile`, styled by `theme`.

    Raises:
        EmitError: a primitive names a role the theme does not declare, or the
            SVG failed its own embedding-safety check.
        ValueError: `profile` is not one of `PROFILES`.
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; expected one of {', '.join(PROFILES)}")
    resolved_theme = theme if isinstance(theme, Theme) else load_theme(theme)

    undeclared = sorted(role for role in scene.roles() if not resolved_theme.declares(role))
    if undeclared:
        raise EmitError(
            f"scene uses role{'s' if len(undeclared) > 1 else ''} "
            f"{', '.join(repr(role) for role in undeclared)}, which theme "
            f"{resolved_theme.name!r} does not declare. A primitive the theme cannot "
            f"style is a programming error in the rendering family that produced it."
        )

    prefix = namespace or namespace_for(scene, resolved_theme, profile)

    root = [
        ("xmlns", "http://www.w3.org/2000/svg"),
        ("viewBox", f"0 0 {format_number(scene.width)} {format_number(scene.height)}"),
    ]
    if profile == "standalone":
        # Nothing to scale against in a linked file or a PDF converter, so the
        # drawing states its own size.
        root += [("width", format_number(scene.width)), ("height", format_number(scene.height))]
    root.append(("role", "img"))

    labels = []
    if scene.title:
        labels.append(f"{prefix}-title")
    if scene.description:
        labels.append(f"{prefix}-desc")
    if labels:
        root.append(("aria-labelledby", " ".join(labels)))

    body: list[str] = []
    if scene.title:
        body.append(f'<title id="{prefix}-title">{escape(scene.title)}</title>')
    if scene.description:
        body.append(f'<desc id="{prefix}-desc">{escape(scene.description)}</desc>')

    definitions = _pattern_definitions(scene, prefix, resolved_theme, profile)
    if definitions:
        body.append("<defs>" + "".join(definitions) + "</defs>")

    body += [_element(primitive, prefix, resolved_theme, profile) for primitive in scene.primitives]

    svg = f"<svg{_attributes(root)}>" + "".join(body) + "</svg>"

    violations = check_embedding_safety(svg, resolved_theme, profile, namespace=prefix)
    if violations:
        raise EmitError(
            "the emitted SVG failed its own embedding-safety check: "
            + "; ".join(str(violation) for violation in violations)
        )
    return svg


# ---------------------------------------------------------------------------
# The output validator
# ---------------------------------------------------------------------------


def check_embedding_safety(
    svg: str, theme: Theme, profile: str = "inline", *, namespace: str | None = None
) -> tuple[Violation, ...]:
    """Every embedding-safety rule, measured on finished SVG.

    Run per profile rather than aggregated across profiles: `standalone` is
    exercised less than `inline`, and summing the two is how an unresolved
    `currentColor` reaches a PDF.

    Args:
        namespace: the id prefix every id must carry. When omitted it is taken
            from the first id in the document, which is what checking someone
            else's SVG looks like.
    """
    violations: list[Violation] = []

    if "<style" in svg:
        violations.append(
            Violation("no-style-element", "a <style> element leaks into the host page")
        )

    font_reference = _FONT_REFERENCE_PATTERN.search(svg)
    if font_reference:
        violations.append(
            Violation(
                "no-embedded-font", f"references a font resource: {font_reference.group(0)!r}"
            )
        )

    identifiers = _ID_PATTERN.findall(svg)
    prefix = namespace
    if prefix is None and identifiers:
        prefix = identifiers[0].split("-")[0]
    for identifier in identifiers:
        if prefix is None or not identifier.startswith(f"{prefix}-"):
            violations.append(
                Violation(
                    "namespaced-ids",
                    f"id {identifier!r} is not prefixed with the document namespace "
                    f"{prefix!r}, so it can collide with another diagram on the page",
                )
            )
    for reference in _URL_PATTERN.findall(svg):
        if prefix is None or not reference.startswith(f"{prefix}-"):
            violations.append(
                Violation("namespaced-ids", f"url(#{reference}) points outside this diagram")
            )

    declared = theme.declared_colours()
    for attribute, value in _PAINT_PATTERN.findall(svg):
        if value.startswith("url(#") or value in declared:
            continue
        violations.append(
            Violation(
                "declared-colours-only",
                f"{attribute}={value!r} is not a colour theme {theme.name!r} declares",
            )
        )

    if profile == "standalone" and "currentColor" in svg:
        violations.append(
            Violation(
                "standalone-resolves-colour",
                "currentColor has nothing to inherit from in a standalone file, so it "
                "would resolve to the converter's default ink",
            )
        )

    return tuple(violations)


__all__ = [
    "PRECISION",
    "PROFILES",
    "Violation",
    "check_embedding_safety",
    "emit",
    "format_number",
    "namespace_for",
]
