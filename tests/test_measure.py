"""T3 — text measurement from font files.

The gate is `text_measurement_error_ratio <= 0.02`: drawspec's measured advance
width for a reference string set must agree within 2% with the width computed
from the same font's own `hmtx`/`kern` tables by an independent reader. The
reader lives in this file — deliberately a second implementation rather than a
call back into `drawspec.text`, so agreement means something.
"""

from __future__ import annotations

import warnings
from itertools import pairwise
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from drawspec.errors import FontSubstitutionWarning
from drawspec.text import Extents, TextMeasurer
from drawspec.text.fontlib import bundled_font_path

# Strings chosen for a spread of letter frequencies, capital/lowercase mixes,
# digits, punctuation and the kern-heavy pairs a diagram label actually hits.
REFERENCE_STRINGS = (
    "Request arrives",
    "Is the payload valid?",
    "AVATAR Toy Wave",
    "1,024 items — 37%",
    "queue.process(batch_id)",
    "Reject with a reason",
    "The quick brown fox jumps over the lazy dog",
    "iiiiiiiiii",
    "WWWWWWWWWW",
)

SIZE = 11.0


# --------------------------------------------------------------------------
# The independent reader
# --------------------------------------------------------------------------


def _pair_kerning(font: TTFont) -> dict[tuple[str, str], int]:
    """Every kerning pair in `font`, read straight from its own tables.

    Written from the OpenType spec rather than from `drawspec.text`, so that a
    shared misreading cannot make the comparison agree with itself.
    """
    pairs: dict[tuple[str, str], int] = {}

    if "kern" in font:
        for table in font["kern"].kernTables:
            for (left, right), value in table.kernTable.items():
                if value:
                    pairs[(left, right)] = value

    if "GPOS" not in font:
        return pairs

    gpos = font["GPOS"].table
    kern_lookups: set[int] = set()
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == "kern":
            kern_lookups.update(record.Feature.LookupListIndex)

    for index in sorted(kern_lookups):
        for subtable in gpos.LookupList.Lookup[index].SubTable:
            if subtable.__class__.__name__ == "ExtensionPos":
                subtable = subtable.ExtSubTable
            if subtable.__class__.__name__ != "PairPos":
                continue
            covered = subtable.Coverage.glyphs
            if subtable.Format == 1:
                for left, pair_set in zip(covered, subtable.PairSet, strict=True):
                    for record in pair_set.PairValueRecord:
                        value = getattr(record.Value1, "XAdvance", 0) if record.Value1 else 0
                        if value:
                            pairs[(left, record.SecondGlyph)] = value
            elif subtable.Format == 2:
                first_classes: dict[int, list[str]] = {}
                for glyph in covered:
                    first_classes.setdefault(subtable.ClassDef1.classDefs.get(glyph, 0), []).append(
                        glyph
                    )
                second_classes: dict[int, list[str]] = {}
                for glyph, klass in subtable.ClassDef2.classDefs.items():
                    second_classes.setdefault(klass, []).append(glyph)
                for first, class1 in enumerate(subtable.Class1Record):
                    for second, class2 in enumerate(class1.Class2Record):
                        value = getattr(class2.Value1, "XAdvance", 0) if class2.Value1 else 0
                        if not value:
                            continue
                        for left in first_classes.get(first, ()):
                            for right in second_classes.get(second, ()):
                                pairs[(left, right)] = value
    return pairs


def independent_width(path: Path, text: str, size: float, *, kerned: bool = True) -> float:
    """Advance width of `text` in the font at `path`, from `hmtx` plus `kern`."""
    font = TTFont(path)
    cmap = font.getBestCmap()
    metrics = font["hmtx"].metrics
    notdef = metrics[font.getGlyphOrder()[0]][0]
    kerning = _pair_kerning(font) if kerned else {}

    glyphs = [cmap.get(ord(character)) for character in text]
    total = float(sum(metrics[glyph][0] if glyph else notdef for glyph in glyphs))
    if kerned:
        for left, right in pairwise(glyphs):
            if left and right:
                total += kerning.get((left, right), 0)
    return total * size / float(font["head"].unitsPerEm)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["sans", "serif", "mono"])
@pytest.mark.parametrize("text", REFERENCE_STRINGS)
def test_measure_reference_strings_match_font_tables_within_two_percent(
    role: str, text: str
) -> None:
    """`text_measurement_error_ratio <= 0.02` — the task's acceptance gate."""
    measurer = TextMeasurer()
    measured = measurer.measure(text, role, SIZE).width
    expected = independent_width(bundled_font_path(role), text, SIZE)

    assert expected > 0
    error_ratio = abs(measured - expected) / expected
    assert error_ratio <= 0.02, f"{role} {text!r}: measured {measured}, expected {expected}"


def test_measure_agrees_exactly_with_an_independent_hmtx_and_kern_reader() -> None:
    """The 2% band is the criterion, but the two readers should agree exactly."""
    measurer = TextMeasurer()
    for role in ("sans", "serif", "mono"):
        for text in REFERENCE_STRINGS:
            measured = measurer.measure(text, role, SIZE).width
            expected = independent_width(bundled_font_path(role), text, SIZE)
            assert measured == pytest.approx(expected, abs=1e-9), f"{role} {text!r}"


# --------------------------------------------------------------------------
# Metrics come from the file, never a table compiled into drawspec
# --------------------------------------------------------------------------


def _font_with_doubled_advances(destination: Path, family: str) -> Path:
    """A font drawspec has never seen: a rename plus every advance doubled."""
    font = TTFont(bundled_font_path("sans"))
    metrics = font["hmtx"].metrics
    for glyph, (advance, left_side_bearing) in list(metrics.items()):
        metrics[glyph] = (advance * 2, left_side_bearing)
    for record in font["name"].names:
        if record.nameID in (1, 3, 4, 6, 16):
            record.string = family
    if "kern" in font:
        del font["kern"]
    if "GPOS" in font:
        del font["GPOS"]
    font.save(destination)
    return destination


def test_measure_previously_unseen_font_returns_metrics(tmp_path: Path) -> None:
    """A font absent from any bundled table measures correctly, from the file."""
    family = "Nonesuch Grotesque"
    path = _font_with_doubled_advances(tmp_path / "nonesuch.ttf", family)

    measurer = TextMeasurer(stacks={"sans": [family]}, search_paths=[tmp_path])
    resolved = measurer.resolve("sans")
    assert resolved.family == family
    assert resolved.path == path

    text = "Request arrives"
    measured = measurer.measure(text, "sans", SIZE).width
    # Doubling every advance doubles the width — the number came out of the file.
    baseline = independent_width(bundled_font_path("sans"), text, SIZE, kerned=False)
    assert measured == pytest.approx(baseline * 2, rel=1e-9)


def test_measure_resolves_a_font_named_by_path(tmp_path: Path) -> None:
    """A stack entry that is a readable font file is used as-is."""
    path = _font_with_doubled_advances(tmp_path / "byPath.ttf", "By Path")
    measurer = TextMeasurer(stacks={"sans": [str(path)]})
    assert measurer.resolve("sans").path == path


# --------------------------------------------------------------------------
# Replace and warn
# --------------------------------------------------------------------------


def test_measure_unresolvable_font_substitutes_and_warns() -> None:
    """Never silent, never fatal: substitute the bundled generic and say so."""
    measurer = TextMeasurer(stacks={"sans": ["Absolutely No Such Family"]}, search_paths=[])

    with pytest.warns(FontSubstitutionWarning) as caught:
        extents = measurer.measure("Request arrives", "sans", SIZE)

    assert extents.width > 0
    message = str(caught[0].message)
    assert "Absolutely No Such Family" in message
    assert "DejaVu Sans" in message


def test_measure_substitution_warns_once_per_role() -> None:
    """The warning is a signal, not a per-call flood."""
    measurer = TextMeasurer(stacks={"sans": ["Absolutely No Such Family"]}, search_paths=[])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(5):
            measurer.measure("Request arrives", "sans", SIZE)
    assert len([w for w in caught if w.category is FontSubstitutionWarning]) == 1


def test_measure_substitution_can_be_promoted_to_an_error() -> None:
    """§5.3: a consumer can make substitution fatal for their own build."""
    measurer = TextMeasurer(stacks={"sans": ["Absolutely No Such Family"]}, search_paths=[])
    with warnings.catch_warnings():
        warnings.simplefilter("error", FontSubstitutionWarning)
        with pytest.raises(FontSubstitutionWarning):
            measurer.measure("Request arrives", "sans", SIZE)


def test_measure_falls_through_the_stack_without_warning_when_a_later_entry_resolves() -> None:
    """A stack is a preference list; reaching entry two is still a substitution."""
    measurer = TextMeasurer(stacks={"sans": ["No Such Family", "DejaVu Sans"]}, search_paths=[])
    with pytest.warns(FontSubstitutionWarning):
        measurer.resolve("sans")


def test_measure_generic_keyword_first_in_the_stack_does_not_warn() -> None:
    """Asking for the generic outright is a request, not a fallback."""
    measurer = TextMeasurer(stacks={"sans": ["sans-serif"]}, search_paths=[])
    with warnings.catch_warnings():
        warnings.simplefilter("error", FontSubstitutionWarning)
        assert measurer.resolve("sans").family == "DejaVu Sans"


def test_measure_unknown_role_raises_keyerror() -> None:
    """A role the theme does not declare is a programming error, not a fallback."""
    with pytest.raises(KeyError):
        TextMeasurer().measure("x", "cursive", SIZE)


# --------------------------------------------------------------------------
# Kerning
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pair", ["AV", "To", "AT", "VA"])
def test_measure_kerned_pair_differs_from_sum_of_advances(pair: str) -> None:
    """Kerning is applied, not ignored."""
    measurer = TextMeasurer()
    kerned = measurer.measure(pair, "sans", SIZE).width
    unkerned = sum(measurer.measure(character, "sans", SIZE).width for character in pair)
    assert kerned < unkerned


def test_measure_monospace_pair_is_not_kerned() -> None:
    """DejaVu Sans Mono carries no kerning; measurement must not invent any."""
    measurer = TextMeasurer()
    kerned = measurer.measure("AV", "mono", SIZE).width
    unkerned = sum(measurer.measure(character, "mono", SIZE).width for character in "AV")
    assert kerned == pytest.approx(unkerned)


# --------------------------------------------------------------------------
# Extents, scaling and caching
# --------------------------------------------------------------------------


def test_measure_empty_string_has_zero_width_and_the_font_line_height() -> None:
    extents = TextMeasurer().measure("", "sans", SIZE)
    assert extents.width == 0.0
    assert extents.height > 0


def test_measure_scales_linearly_with_size() -> None:
    measurer = TextMeasurer()
    at_eleven = measurer.measure("Request arrives", "sans", 11.0).width
    at_twenty_two = measurer.measure("Request arrives", "sans", 22.0).width
    assert at_twenty_two == pytest.approx(at_eleven * 2)


def test_measure_extents_ascent_and_descent_sum_to_height() -> None:
    extents = TextMeasurer().measure("Ag", "sans", SIZE)
    assert extents.ascent > 0
    assert extents.descent > 0
    assert extents.height == pytest.approx(extents.ascent + extents.descent)


def test_measure_extents_are_immutable() -> None:
    extents = TextMeasurer().measure("Ag", "sans", SIZE)
    with pytest.raises(AttributeError):
        extents.width = 1.0  # type: ignore[misc]


def test_measure_negative_size_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="size"):
        TextMeasurer().measure("Ag", "sans", -1.0)


def test_measure_repeated_calls_are_cached_and_identical() -> None:
    """Determinism first, speed second — the same call yields the same number."""
    measurer = TextMeasurer()
    first = measurer.measure("Request arrives", "sans", SIZE)
    second = measurer.measure("Request arrives", "sans", SIZE)
    assert first == second
    assert measurer.cache_info().hits >= 1


def test_measure_unmapped_character_uses_the_notdef_advance() -> None:
    """An uncovered codepoint must not crash and must not measure as zero."""
    measurer = TextMeasurer()
    # U+3042 HIRAGANA A is outside the bundled coverage set.
    assert measurer.measure("あ", "sans", SIZE).width > 0


def test_measurer_measure_matches_the_contract_signature() -> None:
    """§5.5: `measure(text, font_role, size) -> Extents`."""
    extents = TextMeasurer().measure("Ag", "sans", SIZE)
    assert isinstance(extents, Extents)
