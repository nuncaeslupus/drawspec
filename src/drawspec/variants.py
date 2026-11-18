"""One SVG, several themes: the page picks the colours, not the renderer.

A site with a light and a dark mode wants one file per diagram, not one per mode,
and only the renderer knows which colour plays which role. So a multi-theme
render draws the document once per theme, checks that the drawings are the same
drawing — same layout, same text, same shapes, same fill patterns — and merges
them into one SVG whose colours are CSS custom properties:

- every `fill` and `stroke` whose value differs between the themes reads
  `var(--{ns}-cN)` from a `style` attribute, and keeps the base theme's value as
  its own attribute, so a host that strips `<style>` still gets a whole drawing;
- one `<style>` sets those properties on the root, `#{ns}-svg`: the base theme's
  values first, then a variant named `dark` or `light` under the matching
  `prefers-color-scheme` query, then every theme under an ancestor's
  `data-theme="name"` — which wins over the query, so a page's own switch beats
  the reader's system setting;
- the root carries `data-drawspec-theme="light=default@1a2b3c4d dark=…"`, each
  theme's name and a digest of everything it declares, so a consumer can tell
  which themes a file was rendered with and re-render when one changes.

The `<style>` is the one exception to the no-`<style>` rule in `drawspec.emit`,
and `check_embedding_safety` admits it only in that shape: every rule scoped to
this drawing's root, and every declaration one of its own properties set to a
colour one of its themes declares. It cannot reach the rest of the page.

Single-theme output does not come through here and is unchanged.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from hashlib import blake2b
from typing import Final

from drawspec.errors import EmitError, ThemeError
from drawspec.theme import Theme

#: The name the base theme answers to under `data-theme`.
BASE_NAME: Final = "light"

#: What a variant may be called: it goes into a CSS attribute selector.
NAME_PATTERN: Final = re.compile(r"[a-z][a-z0-9-]*")

#: Variant names that also follow the reader's system setting.
SCHEMES: Final = ("light", "dark")

_PAINT: Final = re.compile(r'\b(fill|stroke)="([^"]*)"')
_TAG: Final = re.compile(r"<[^>]*>")
_MARK: Final = re.compile(r"\x00(fill|stroke):(\d+)\x00")


def check_names(names: Sequence[str]) -> None:
    """Refuse a variant name a selector cannot carry, or one already taken."""
    for name in names:
        if not NAME_PATTERN.fullmatch(name):
            raise ThemeError(
                f"variant name {name!r}: use lowercase letters, digits and hyphens, starting "
                f"with a letter — it becomes the value a page sets in data-theme."
            )
        if name == BASE_NAME:
            raise ThemeError(
                f"variant name {BASE_NAME!r} is the base theme's: the theme the drawing is "
                f"rendered with answers to data-theme={BASE_NAME!r}. Name the variant "
                f"something else, such as 'dark'."
            )


def theme_stamp(theme: Theme) -> str:
    """`name@digest`: which theme, and which version of it, drew a file.

    The digest is over everything the loaded theme declares, in a canonical
    order, so it changes when the theme does and not between runs.
    """
    digest = blake2b(repr(_canonical(theme)).encode(), digest_size=4)
    return f"{theme.name}@{digest.hexdigest()}"


def _canonical(value: object) -> object:
    """`value` with every set and mapping in a fixed order."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return tuple(
            (field.name, _canonical(getattr(value, field.name)))
            for field in dataclasses.fields(value)
        )
    if isinstance(value, Mapping):
        return tuple(sorted(((repr(k), _canonical(v)) for k, v in value.items()), key=repr))
    if isinstance(value, set | frozenset):
        return tuple(sorted((_canonical(item) for item in value), key=repr))
    if isinstance(value, list | tuple):
        return tuple(_canonical(item) for item in value)
    return value


def merged(drawings: Sequence[tuple[str, Theme, str]], namespace: str) -> str:
    """One SVG from the same drawing in several themes; the first is the base.

    Each entry is `(name, theme, svg)`, every `svg` emitted with `namespace` and
    ordinal pattern ids so that only paint can differ between them.

    Raises:
        ThemeError: a variant's drawing differs from the base's in more than
            colour, naming the variant.
    """
    _, base_theme, base_svg = drawings[0]
    base_parts = _PAINT.split(base_svg)
    columns: list[list[str]] = [[value] for value in base_parts[2::3]]
    for name, theme, svg in drawings[1:]:
        parts = _PAINT.split(svg)
        if parts[0::3] != base_parts[0::3] or parts[1::3] != base_parts[1::3]:
            raise ThemeError(
                f"variant {name!r}: theme {theme.name!r} draws this document differently "
                f"from the base theme {base_theme.name!r}, not just in other colours. A "
                f"variant may change colours only: the same fonts, sizes, spacing, shapes "
                f"and fill patterns, and as many distinct colours as the base theme uses "
                f"where they meet."
            )
        for column, value in zip(columns, parts[2::3], strict=True):
            column.append(value)

    properties: dict[tuple[str, ...], int] = {}
    out = [base_parts[0]]
    for index, column in enumerate(columns):
        attribute, text = base_parts[3 * index + 1], base_parts[3 * index + 3]
        out.append(f'{attribute}="{column[0]}"')
        if len(set(column)) > 1:
            number = properties.setdefault(tuple(column), len(properties))
            out.append(f"\x00{attribute}:{number}\x00")
        out.append(text)
    svg = _TAG.sub(lambda tag: _styled(tag.group(0), namespace), "".join(out))

    stamp = " ".join(f"{name}={theme_stamp(theme)}" for name, theme, _ in drawings)
    rules = [_rule(f"#{namespace}-svg", namespace, properties, 0)]
    for position, (name, _, _) in enumerate(drawings):
        if name in SCHEMES and position:
            inner = _rule(f"#{namespace}-svg", namespace, properties, position)
            rules.append(f"@media (prefers-color-scheme: {name}){{{inner}}}")
    for position, (name, _, _) in enumerate(drawings):
        rules.append(
            _rule(f'[data-theme="{name}"] #{namespace}-svg', namespace, properties, position)
        )
    style = f"<style>{''.join(rules)}</style>" if properties else ""

    if not svg.startswith("<svg"):
        raise EmitError("a multi-theme drawing must start with its <svg> root")
    head, _, rest = svg.partition(">")
    return f'{head} id="{namespace}-svg" data-drawspec-theme="{stamp}">' + style + rest


def _styled(tag: str, namespace: str) -> str:
    """`tag` with its markers gathered into one `style` attribute."""
    reads = [
        f"{attribute}:var(--{namespace}-c{number})" for attribute, number in _MARK.findall(tag)
    ]
    if not reads:
        return tag
    bare = _MARK.sub("", tag)
    end = -2 if bare.endswith("/>") else -1
    return f'{bare[:end]} style="{";".join(reads)}"{bare[end:]}'


def _rule(
    selector: str, namespace: str, properties: Mapping[tuple[str, ...], int], position: int
) -> str:
    declarations = ";".join(
        f"--{namespace}-c{number}:{values[position]}" for values, number in properties.items()
    )
    return f"{selector}{{{declarations}}}"


__all__ = ["BASE_NAME", "NAME_PATTERN", "check_names", "merged", "theme_stamp"]
