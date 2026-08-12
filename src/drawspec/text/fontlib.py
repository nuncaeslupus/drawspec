"""Font resolution and metric reading.

Two responsibilities, kept apart from measurement itself:

`FontFile` reads metrics — advance widths, kerning, vertical extents — out of a
font file and nothing else. There is no table of known fonts anywhere in
drawspec: a font it has never seen measures exactly like one it ships, because
both are read the same way. That is what the `text_measurement_error_ratio`
criterion is protecting.

`FontIndex` and `resolve_stack` turn a CSS-style family stack from the theme
(`["Source Sans 3", "DejaVu Sans", "sans-serif"]`) into one font file, falling
back through the stack and finally onto the bundled generic. A fallback is a
substitution, and a substitution is always reported — see
`FontSubstitutionWarning` in `drawspec.errors`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import cache, lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Final

from fontTools.ttLib import TTFont, TTLibError

#: Font roles drawspec knows. A theme names its stacks with these keys.
FONT_ROLES: Final = ("sans", "serif", "mono")

#: CSS generic keywords an author or theme may name in a stack, mapped onto the
#: role whose bundled font satisfies them. Naming one of these is a request for
#: the generic, so it terminates a stack without being a failed lookup.
GENERIC_KEYWORDS: Final = {
    "sans-serif": "sans",
    "sans": "sans",
    "serif": "serif",
    "monospace": "mono",
    "mono": "mono",
    "ui-sans-serif": "sans",
    "ui-serif": "serif",
    "ui-monospace": "mono",
}

#: The generic keyword that names each role — used to report a stack with no
#: entries at all, where there is no requested family to name.
GENERIC_KEYWORDS_INVERSE: Final = {"sans": "sans-serif", "serif": "serif", "mono": "monospace"}

#: Where `FontIndex` looks for host fonts when a theme names a family drawspec
#: does not bundle. Missing directories are skipped, so the same list is safe on
#: every platform.
DEFAULT_SEARCH_PATHS: Final = (
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("C:/Windows/Fonts"),
    Path.home() / ".fonts",
    Path.home() / ".local/share/fonts",
    Path.home() / "Library/Fonts",
)

FONT_SUFFIXES: Final = frozenset({".ttf", ".otf", ".ttc", ".otc"})

# name table ids: 1 = family, 2 = subfamily, 16 = typographic family.
_NAME_FAMILY: Final = 1
_NAME_SUBFAMILY: Final = 2
_NAME_TYPOGRAPHIC_FAMILY: Final = 16

#: Subfamily names that mark the upright, normal-weight face — the one a family
#: name without further qualification means.
_REGULAR_SUBFAMILIES: Final = frozenset({"regular", "book", "roman", "normal", ""})

_FONTS_DIR: Final = Path(__file__).resolve().parent.parent / "fonts"


def bundled_font_path(role: str) -> Path:
    """The bundled generic font file for `role`.

    Raises:
        KeyError: `role` is not one of `FONT_ROLES`.
    """
    if role not in FONT_ROLES:
        raise KeyError(f"unknown font role {role!r}; expected one of {', '.join(FONT_ROLES)}")
    return _FONTS_DIR / f"{role}.ttf"


@cache
def bundled_font_family(role: str) -> str:
    """The family name inside the bundled font for `role`.

    Read from the file rather than hardcoded, so renaming a bundled font cannot
    leave drawspec naming a family it is not actually measuring.
    """
    return load_font(bundled_font_path(role)).family


@dataclass(frozen=True)
class ResolvedFont:
    """The outcome of resolving one family stack."""

    role: str
    """The font role the stack was declared under."""

    family: str
    """The family name of the file actually measured."""

    path: Path
    """The file actually measured."""

    requested: str
    """The first family the stack named — what the author asked for."""

    substituted: bool
    """True when `family` is not what `requested` asked for."""


class FontFile:
    """Metrics for one font file. Immutable in effect; caches what it reads."""

    def __init__(self, path: Path, data: bytes | None = None) -> None:
        self.path = path
        payload = path.read_bytes() if data is None else data
        # A collection (.ttc) is read as its first face; drawspec wants the
        # upright regular, which is face 0 in every collection we have seen.
        self._font = TTFont(io.BytesIO(payload), fontNumber=0, lazy=True)
        self._advances: dict[str, int] = {}
        self._kerning: dict[tuple[str, str], int] = {}
        self._cmap: dict[int, str] | None = None
        self._pair_lookups: list[object] | None = None

    # -- identity ---------------------------------------------------------

    @property
    def family(self) -> str:
        """The family name from the font's own `name` table."""
        return read_family_name(self._font) or self.path.stem

    @property
    def units_per_em(self) -> int:
        return int(self._font["head"].unitsPerEm)

    # -- vertical metrics -------------------------------------------------

    @property
    def ascent(self) -> float:
        """Height above the baseline, in font units.

        `hhea` is the line-layout metric browsers and SVG renderers use, so it
        is what a box sized by drawspec must reserve. `OS/2` typographic values
        are the documented fallback for a font with an empty `hhea`.
        """
        ascent = float(self._font["hhea"].ascent)
        if ascent:
            return ascent
        if "OS/2" in self._font:
            return float(self._font["OS/2"].sTypoAscender)
        return float(self._font["head"].yMax)

    @property
    def descent(self) -> float:
        """Depth below the baseline, in font units, as a positive magnitude."""
        descent = float(self._font["hhea"].descent)
        if descent:
            return abs(descent)
        if "OS/2" in self._font:
            return abs(float(self._font["OS/2"].sTypoDescender))
        return abs(float(self._font["head"].yMin))

    # -- horizontal metrics -----------------------------------------------

    @property
    def _characters(self) -> dict[int, str]:
        if self._cmap is None:
            self._cmap = dict(self._font.getBestCmap())
        return self._cmap

    def glyph_name(self, character: str) -> str | None:
        """The glyph the font maps `character` to, or None if it maps none."""
        return self._characters.get(ord(character))

    @property
    def notdef_advance(self) -> int:
        """The advance used for a character the font does not cover.

        Glyph 0 is `.notdef` by definition, so an uncovered character measures
        as the width the font itself would draw for it — never as zero, which
        would silently under-size a box.
        """
        return self.glyph_advance(self._font.getGlyphOrder()[0])

    def glyph_advance(self, glyph: str) -> int:
        """Advance width of `glyph` in font units."""
        advance = self._advances.get(glyph)
        if advance is None:
            advance = int(self._font["hmtx"].metrics[glyph][0])
            self._advances[glyph] = advance
        return advance

    def advance(self, character: str) -> int:
        """Advance width of `character` in font units, `.notdef` if uncovered."""
        glyph = self.glyph_name(character)
        return self.notdef_advance if glyph is None else self.glyph_advance(glyph)

    # -- kerning ----------------------------------------------------------

    @property
    def _pair_positioning(self) -> list[object]:
        """Every GPOS `PairPos` subtable reachable from the `kern` feature.

        Collected once, in feature order. Queried per pair rather than expanded
        into a pair table, because `ClassDef2`'s class 0 covers every glyph not
        otherwise listed — expanding it would mean materialising the whole
        cross-product of the font.
        """
        if self._pair_lookups is not None:
            return self._pair_lookups

        subtables: list[object] = []
        if "GPOS" in self._font:
            gpos = self._font["GPOS"].table
            indices: set[int] = set()
            for record in gpos.FeatureList.FeatureRecord:
                if record.FeatureTag == "kern":
                    indices.update(record.Feature.LookupListIndex)
            for index in sorted(indices):
                for subtable in gpos.LookupList.Lookup[index].SubTable:
                    if subtable.__class__.__name__ == "ExtensionPos":
                        subtable = subtable.ExtSubTable
                    if subtable.__class__.__name__ == "PairPos":
                        subtables.append(subtable)
        self._pair_lookups = subtables
        return subtables

    @staticmethod
    def _x_advance(value: object) -> int:
        return int(getattr(value, "XAdvance", 0) or 0) if value is not None else 0

    def _gpos_kerning(self, left: str, right: str) -> int | None:
        for subtable in self._pair_positioning:
            coverage = subtable.Coverage.glyphs  # type: ignore[attr-defined]
            if left not in coverage:
                continue
            if subtable.Format == 1:  # type: ignore[attr-defined]
                pair_set = subtable.PairSet[coverage.index(left)]  # type: ignore[attr-defined]
                for record in pair_set.PairValueRecord:
                    if record.SecondGlyph == right:
                        return self._x_advance(record.Value1)
            elif subtable.Format == 2:  # type: ignore[attr-defined]
                first = subtable.ClassDef1.classDefs.get(left, 0)  # type: ignore[attr-defined]
                second = subtable.ClassDef2.classDefs.get(right, 0)  # type: ignore[attr-defined]
                records = subtable.Class1Record  # type: ignore[attr-defined]
                if first >= len(records):
                    continue
                class2 = records[first].Class2Record
                if second >= len(class2):
                    continue
                return self._x_advance(class2[second].Value1)
        return None

    def _legacy_kerning(self, left: str, right: str) -> int:
        if "kern" not in self._font:
            return 0
        for table in self._font["kern"].kernTables:
            value = table.kernTable.get((left, right))
            if value:
                return int(value)
        return 0

    def kerning(self, left: str, right: str) -> int:
        """Kern adjustment between two glyphs, in font units (usually negative).

        GPOS wins over the legacy `kern` table when a font carries both, because
        GPOS is what an OpenType renderer applies. Within GPOS the first
        subtable that covers the pair wins — the shaping rule for a single kern
        feature, and the only case a diagram label reaches.
        """
        cached = self._kerning.get((left, right))
        if cached is not None:
            return cached
        value = self._gpos_kerning(left, right)
        if value is None:
            value = self._legacy_kerning(left, right)
        self._kerning[(left, right)] = value
        return value

    # -- text -------------------------------------------------------------

    def text_advance(self, text: str) -> float:
        """Advance width of `text` in font units, kerning included."""
        if not text:
            return 0.0
        glyphs = [self.glyph_name(character) for character in text]
        total = float(
            sum(self.notdef_advance if g is None else self.glyph_advance(g) for g in glyphs)
        )
        for left, right in pairwise(glyphs):
            if left is not None and right is not None:
                total += self.kerning(left, right)
        return total


@lru_cache(maxsize=64)
def load_font(path: Path) -> FontFile:
    """Load and cache the metrics for the font at `path`."""
    return FontFile(path)


def read_family_name(font: TTFont) -> str | None:
    """The family name a stack would have to name to select `font`.

    Prefers the typographic family (name id 16) when the font declares one, so a
    face like "Foo Display Semibold" is found under "Foo Display".
    """
    for name_id in (_NAME_TYPOGRAPHIC_FAMILY, _NAME_FAMILY):
        record = font["name"].getDebugName(name_id)
        if record:
            return str(record)
    return None


def _read_subfamily(font: TTFont) -> str:
    return str(font["name"].getDebugName(_NAME_SUBFAMILY) or "")


class FontIndex:
    """Family name to font file, built by reading the fonts under a search path.

    Built lazily and once: a host with a few hundred fonts costs one scan per
    process, and a process that only ever uses bundled fonts pays nothing.
    """

    def __init__(self, search_paths: tuple[Path, ...]) -> None:
        self._search_paths = search_paths
        self._index: dict[str, Path] | None = None

    @property
    def families(self) -> dict[str, Path]:
        if self._index is None:
            self._index = self._build()
        return self._index

    def _build(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        regular: set[str] = set()
        for directory in self._search_paths:
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if path.suffix.lower() not in FONT_SUFFIXES or not path.is_file():
                    continue
                self._add(path, index, regular)
        return index

    @staticmethod
    def _add(path: Path, index: dict[str, Path], regular: set[str]) -> None:
        try:
            font = TTFont(path, fontNumber=0, lazy=True)
            family = read_family_name(font)
            is_regular = _read_subfamily(font).strip().lower() in _REGULAR_SUBFAMILIES
            font.close()
        except (TTLibError, OSError, KeyError, UnicodeDecodeError):
            # An unreadable font file is not drawspec's problem to report: it is
            # simply not a candidate. Every other family still resolves.
            return
        if not family:
            return
        key = family.strip().lower()
        # First win, except that a Regular face displaces a styled one — asking
        # for "DejaVu Sans" must not land on DejaVu Sans Bold.
        if key not in index or (is_regular and key not in regular):
            index[key] = path
        if is_regular:
            regular.add(key)

    def lookup(self, family: str) -> Path | None:
        return self.families.get(family.strip().lower())


@lru_cache(maxsize=8)
def _index_for(search_paths: tuple[Path, ...]) -> FontIndex:
    return FontIndex(search_paths)


def default_search_paths() -> tuple[Path, ...]:
    """The host font directories to scan, in order.

    Every platform's directories are listed together rather than switched on
    `sys.platform`, because a directory that does not exist is skipped anyway and
    one list is one thing to reason about.
    """
    return DEFAULT_SEARCH_PATHS


def resolve_stack(
    role: str, stack: tuple[str, ...], search_paths: tuple[Path, ...]
) -> ResolvedFont:
    """Resolve one family stack to a single font file.

    Each entry is tried in order and may be a family name, a CSS generic keyword
    (`sans-serif`, `serif`, `monospace`), or the path of a font file. The bundled
    generic for `role` is the last resort, so resolution never fails — but
    anything other than the first entry is recorded as a substitution.

    Raises:
        KeyError: `role` is not one of `FONT_ROLES`.
    """
    bundled = bundled_font_path(role)  # validates the role before anything else
    index = _index_for(search_paths)
    requested = stack[0] if stack else GENERIC_KEYWORDS_INVERSE[role]

    for position, entry in enumerate(stack):
        path = _resolve_entry(entry, index)
        if path is None:
            continue
        family = load_font(path).family
        return ResolvedFont(
            role=role,
            family=family,
            path=path,
            requested=requested,
            # Falling through the stack is only a *substitution* if the metrics
            # changed. Asking for "DejaVu Sans" and getting the bundled copy of
            # DejaVu Sans is the font that was asked for, whichever entry
            # supplied it — warning about it would be noise, and noise is how a
            # warning that matters gets ignored.
            substituted=position > 0 and not _same_family(family, requested),
        )

    bundled_family = load_font(bundled).family
    return ResolvedFont(
        role=role,
        family=bundled_family,
        path=bundled,
        requested=requested,
        substituted=not _same_family(bundled_family, requested),
    )


def _same_family(resolved: str, requested: str) -> bool:
    """Whether the resolved font is the family that was asked for."""
    return resolved.strip().lower() == requested.strip().lower()


def _resolve_entry(entry: str, index: FontIndex) -> Path | None:
    """One stack entry to a font file: generic keyword, file path, or family."""
    keyword = GENERIC_KEYWORDS.get(entry.strip().lower())
    if keyword is not None:
        return bundled_font_path(keyword)

    candidate = Path(entry).expanduser()
    if candidate.suffix.lower() in FONT_SUFFIXES and candidate.is_file():
        return candidate

    return index.lookup(entry)


__all__ = [
    "DEFAULT_SEARCH_PATHS",
    "FONT_ROLES",
    "FontFile",
    "FontIndex",
    "ResolvedFont",
    "bundled_font_family",
    "bundled_font_path",
    "default_search_paths",
    "load_font",
    "resolve_stack",
]
