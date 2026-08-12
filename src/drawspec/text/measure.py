"""Text measurement: `measure(text, font_role, size) -> Extents`.

This is the module everything downstream depends on. Box geometry, line
breaking, pyramid text fitting and chart labels are all derived from the numbers
it returns, which is why the plan makes it Large and first: if measurement is
wrong, every box in every diagram is wrong in a way no later stage can detect.

Two invariants carry the design:

* **Metrics come from the font file.** There is no table of known families in
  drawspec. A font it has never seen is read exactly like one it bundles.
* **Substitution is never silent and never fatal.** An unresolvable family falls
  back to a bundled generic, warns once, and keeps rendering.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from drawspec.errors import FontSubstitutionWarning
from drawspec.text.fontlib import (
    FONT_ROLES,
    FONT_WEIGHTS,
    ResolvedFont,
    default_search_paths,
    load_font,
    resolve_stack,
)

#: The stacks a `TextMeasurer` uses when a theme does not supply its own: the
#: bundled generics and nothing else, so the default is host-independent.
DEFAULT_STACKS: Mapping[str, tuple[str, ...]] = {
    "sans": ("sans-serif",),
    "serif": ("serif",),
    "mono": ("monospace",),
}


@dataclass(frozen=True)
class Extents:
    """The space one text run occupies, in user units at the measured size.

    `ascent` and `descent` are the font's line-layout metrics rather than the
    inked bounds of these particular glyphs: a box has to reserve room for the
    line, not for the letters that happen to be in it, or two boxes holding
    "ace" and "Agile" would come out different heights.
    """

    width: float
    """Total advance width, kerning included."""

    ascent: float
    """Height above the baseline."""

    descent: float
    """Depth below the baseline, as a positive magnitude."""

    @property
    def height(self) -> float:
        """Baseline-to-baseline height of a single line."""
        return self.ascent + self.descent


class CacheInfo(NamedTuple):
    """Hit/miss counts for the measurement cache, for tests and diagnostics."""

    hits: int
    misses: int
    fonts: int


class TextMeasurer:
    """Measures text against the fonts a theme's family stacks resolve to.

    A measurer is cheap to construct and caches what it reads, so a render
    creates one and passes it down. Measurement is a pure function of
    (text, role, size) for the life of the instance.
    """

    def __init__(
        self,
        stacks: Mapping[str, Sequence[str]] | None = None,
        *,
        search_paths: Iterable[Path] | None = None,
    ) -> None:
        """
        Args:
            stacks: role → family stack, as a theme's `[font]` section declares
                them (`{"sans": ["Source Sans 3", "DejaVu Sans", "sans-serif"]}`).
                Roles absent from the mapping keep their bundled default.
            search_paths: directories to scan for host fonts. Defaults to the
                platform font directories; pass `[]` to consider only bundled
                fonts and fonts named by path, which is what a test that must
                not depend on the host's font set wants.
        """
        declared = dict(DEFAULT_STACKS)
        for role, stack in (stacks or {}).items():
            if role not in FONT_ROLES:
                raise KeyError(
                    f"unknown font role {role!r}; expected one of {', '.join(FONT_ROLES)}"
                )
            declared[role] = tuple(stack)
        self._stacks: Mapping[str, tuple[str, ...]] = declared
        self._search_paths = default_search_paths() if search_paths is None else tuple(search_paths)
        self._resolved: dict[tuple[str, str], ResolvedFont] = {}
        self._warned: set[str] = set()
        # Widths are cached in font units, so one entry serves every type size.
        self._widths: dict[tuple[str, str, str], float] = {}
        self._hits = 0
        self._misses = 0

    # -- resolution -------------------------------------------------------

    def stack(self, font_role: str) -> tuple[str, ...]:
        """The family stack declared for `font_role`."""
        try:
            return self._stacks[font_role]
        except KeyError:
            raise KeyError(
                f"unknown font role {font_role!r}; expected one of {', '.join(FONT_ROLES)}"
            ) from None

    def resolve(self, font_role: str, weight: str = "normal") -> ResolvedFont:
        """Resolve `font_role`'s stack at `weight`, warning on substitution.

        Raises:
            KeyError: `font_role` or `weight` is not one drawspec knows.
        """
        if weight not in FONT_WEIGHTS:
            raise KeyError(f"unknown weight {weight!r}; expected one of {', '.join(FONT_WEIGHTS)}")
        resolved = self._resolved.get((font_role, weight))
        if resolved is None:
            resolved = resolve_stack(font_role, self.stack(font_role), self._search_paths, weight)
            self._resolved[(font_role, weight)] = resolved
            if resolved.substituted:
                self._warn(resolved)
        return resolved

    def _warn(self, resolved: ResolvedFont) -> None:
        """Report a substitution once per role, naming both families.

        Once per role rather than once per call: the same missing font is the
        same fact however many strings get measured against the substitute, and a
        warning per measurement would bury it.
        """
        if resolved.role in self._warned:
            return
        self._warned.add(resolved.role)
        warnings.warn(
            f"font {resolved.requested!r} (role {resolved.role!r}) could not be resolved; "
            f"measuring against {resolved.family!r} instead. Box sizes reflect "
            f"{resolved.family!r}, so name it in the theme's font stack — or install "
            f"{resolved.requested!r} — if the rendered page will use it.",
            FontSubstitutionWarning,
            stacklevel=3,
        )

    # -- measurement ------------------------------------------------------

    def measure(
        self, text: str, font_role: str = "sans", size: float = 11.0, weight: str = "normal"
    ) -> Extents:
        """The space `text` occupies in `font_role` at `size` and `weight`.

        `weight` is not decoration. A run drawn bold and measured regular comes
        out narrow — 3.8 units in one eleven-point word — and whatever follows it
        on the line starts early and lands on top of it.

        Raises:
            KeyError: `font_role` or `weight` is not one drawspec knows.
            ValueError: `size` is not positive.
        """
        if size <= 0:
            raise ValueError(f"size must be positive, got {size!r}")
        font = load_font(self.resolve(font_role, weight).path)
        scale = size / font.units_per_em
        return Extents(
            width=self._advance(text, font_role, weight) * scale,
            ascent=font.ascent * scale,
            descent=font.descent * scale,
        )

    def advance(
        self, text: str, font_role: str = "sans", size: float = 11.0, weight: str = "normal"
    ) -> float:
        """The advance width of `text` alone — `measure(...).width`."""
        return self.measure(text, font_role, size, weight).width

    def _advance(self, text: str, font_role: str, weight: str) -> float:
        """Advance width in font units, cached per (role, weight, text)."""
        key = (font_role, weight, text)
        cached = self._widths.get(key)
        if cached is not None:
            self._hits += 1
            return cached
        self._misses += 1
        width = load_font(self.resolve(font_role, weight).path).text_advance(text)
        self._widths[key] = width
        return width

    def cache_info(self) -> CacheInfo:
        """Cache statistics — measurement is pure, so this is only diagnostics."""
        return CacheInfo(hits=self._hits, misses=self._misses, fonts=len(self._resolved))


__all__ = ["DEFAULT_STACKS", "CacheInfo", "Extents", "TextMeasurer"]
