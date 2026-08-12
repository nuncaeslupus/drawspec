"""T5 — line breaking and text block sizing.

The gate is `text_overflow_count == 0`: every line the wrapper returns measures
at or below the width it was given, and block height is derived from the line
count and the theme's line height rather than estimated. An unbreakable run
wider than its box raises `FitError` — the tool says restructure the diagram
rather than letting text escape.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from drawspec.errors import FitError
from drawspec.text import TextMeasurer
from drawspec.text.wrap import Line, Span, TextBlock, parse_spans, wrap
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

PROSE = (
    "An incoming request is validated, then either accepted for processing "
    "or rejected with a reason the caller can act on."
)


def block(text: str, max_width: float, *, level: str = "body") -> TextBlock:
    return wrap(text, max_width, MEASURER, theme=THEME, level=level)


def measured(line: Line) -> float:
    """Re-measure a line from its spans, rather than trusting its own number."""
    return sum(
        MEASURER.measure(span.text, span.font, THEME.scale["body"]).width for span in line.spans
    )


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("max_width", [60.0, 100.0, 160.0, 240.0, 500.0])
def test_wrap_produces_lines_all_within_the_given_width(max_width: float) -> None:
    """`text_overflow_count == 0` — measured, not assumed."""
    result = block(PROSE, max_width)
    assert result.lines
    for line in result.lines:
        assert line.width <= max_width
        assert measured(line) <= max_width + 1e-9


def test_wrap_line_width_is_the_measured_width_not_an_estimate() -> None:
    for line in block(PROSE, 180.0).lines:
        assert line.width == pytest.approx(measured(line))


def test_wrap_run_with_no_break_opportunity_that_fits_raises_fiterror() -> None:
    """Punctuation breaking is tried first, but it cannot always save a run."""
    with pytest.raises(FitError, match="overflows by"):
        block("queue.process(batch_id).result", 70.0)


def test_wrap_word_longer_than_max_width_raises_fiterror() -> None:
    with pytest.raises(FitError) as error:
        block("Unsplittableliteralrunofcharacters", 20.0)
    message = str(error.value)
    assert "Unsplittableliteralrunofcharacters" in message
    # The message is the product: what did not fit, by how much, and the remedies.
    assert "20" in message
    assert "restructure" in message.lower() or "rethink" in message.lower()


def test_wrap_block_height_equals_lines_times_line_height() -> None:
    """Height is derived from the line count, never guessed."""
    result = block(PROSE, 160.0)
    expected = len(result.lines) * THEME.box.line_height * THEME.scale["body"]
    assert result.height == pytest.approx(expected)
    assert result.advance == pytest.approx(THEME.box.line_height * THEME.scale["body"])


def test_wrap_block_width_is_the_widest_line() -> None:
    result = block(PROSE, 200.0)
    assert result.width == pytest.approx(max(line.width for line in result.lines))
    assert result.width <= 200.0


# --------------------------------------------------------------------------
# Breaking behaviour
# --------------------------------------------------------------------------


def test_wrap_fills_greedily_so_a_wider_box_never_needs_more_lines() -> None:
    narrow = block(PROSE, 120.0)
    wide = block(PROSE, 240.0)
    assert len(wide.lines) <= len(narrow.lines)


def test_wrap_short_text_stays_on_one_line() -> None:
    result = block("Request arrives", 400.0)
    assert len(result.lines) == 1
    assert result.lines[0].text == "Request arrives"


def test_wrap_preserves_every_word_in_order() -> None:
    result = block(PROSE, 90.0)
    assert " ".join(line.text for line in result.lines).split() == PROSE.split()


def test_wrap_honours_an_explicit_line_break() -> None:
    """An author who breaks a line meant it; the wrapper does not rejoin."""
    result = block("Accepted\nRejected", 400.0)
    assert [line.text for line in result.lines] == ["Accepted", "Rejected"]


def test_wrap_collapses_runs_of_whitespace() -> None:
    assert block("Request    arrives", 400.0).lines[0].text == "Request arrives"


def test_wrap_empty_text_is_one_empty_line_with_the_line_height() -> None:
    """A box with no text still has a line's worth of height, not zero."""
    result = block("", 100.0)
    assert [line.text for line in result.lines] == [""]
    assert result.height == pytest.approx(THEME.box.line_height * THEME.scale["body"])
    assert result.width == 0.0


def test_wrap_breaks_a_long_identifier_at_a_punctuation_boundary() -> None:
    """ "Break into more lines" is the first remedy, so it is tried first."""
    result = block("queue.process(batch_id).result", 110.0)
    assert len(result.lines) > 1
    assert all(line.width <= 110.0 for line in result.lines)
    assert "".join(line.text for line in result.lines) == "queue.process(batch_id).result"


def test_wrap_non_positive_width_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="max_width"):
        block(PROSE, 0.0)


def test_wrap_unknown_level_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        block(PROSE, 100.0, level="caption")


# --------------------------------------------------------------------------
# Baselines — what T6 centres with
# --------------------------------------------------------------------------


def test_wrap_baselines_are_evenly_spaced_by_the_line_advance() -> None:
    """Regular line spacing: no tight lines next to loose ones in one block."""
    result = block(PROSE, 140.0)
    baselines = [result.baseline(index) for index in range(len(result.lines))]
    gaps = [second - first for first, second in pairwise(baselines)]
    assert all(gap == pytest.approx(result.advance) for gap in gaps)


def test_wrap_first_baseline_leaves_room_for_the_ascent() -> None:
    result = block("Ag", 200.0)
    assert result.baseline(0) >= result.ascent


def test_wrap_last_baseline_leaves_room_for_the_descent() -> None:
    result = block(PROSE, 140.0)
    last = result.baseline(len(result.lines) - 1)
    assert last + result.descent <= result.height + 1e-9


def test_wrap_baseline_index_out_of_range_raises_indexerror() -> None:
    with pytest.raises(IndexError):
        block("Ag", 200.0).baseline(5)


# --------------------------------------------------------------------------
# Inline spans are semantic, so wrapping has to see them
# --------------------------------------------------------------------------


def test_parse_spans_plain_text_is_one_span() -> None:
    assert parse_spans("Request arrives") == (Span("Request arrives"),)


def test_parse_spans_backticks_select_the_monospace_role() -> None:
    spans = parse_spans("Run `make test` first")
    assert [(span.text, span.font) for span in spans] == [
        ("Run ", "sans"),
        ("make test", "mono"),
        (" first", "sans"),
    ]


def test_parse_spans_double_asterisks_select_the_bold_weight() -> None:
    spans = parse_spans("The **main** concept")
    assert [(span.text, span.weight) for span in spans] == [
        ("The ", "normal"),
        ("main", "bold"),
        (" concept", "normal"),
    ]


def test_parse_spans_unmatched_delimiter_is_literal_text() -> None:
    """A stray backtick is a character, not a syntax error in a diagram label."""
    assert parse_spans("2 * 3 and a ` here") == (Span("2 * 3 and a ` here"),)


def test_parse_spans_respects_the_default_font_role() -> None:
    spans = parse_spans("prose and `code`", font="serif")
    assert [span.font for span in spans] == ["serif", "mono"]


def test_wrap_measures_a_monospace_span_in_the_monospace_font() -> None:
    """The width of a span is the width of the font it will be drawn in."""
    with_code = block("`iiiiiiiiii`", 400.0).width
    as_prose = block("iiiiiiiiii", 400.0).width
    assert with_code > as_prose


def test_wrap_keeps_a_span_boundary_when_a_line_breaks_inside_one() -> None:
    result = block("Then run `make test` and check the output again", 90.0)
    assert all(line.width <= 90.0 for line in result.lines)
    fonts = {span.font for line in result.lines for span in line.spans}
    assert fonts == {"sans", "mono"}


def test_wrap_bold_span_measures_wider_than_the_same_words_plain() -> None:
    """Bold is a real weight, not a synonym — so it has to be measured as one."""
    bold = wrap("**Request arrives**", 400.0, MEASURER, theme=THEME)
    plain = wrap("Request arrives", 400.0, MEASURER, theme=THEME)
    assert bold.width >= plain.width


def test_wrap_block_is_iterable_over_its_lines() -> None:
    """§5.5 spells the contract `wrap(...) -> list[Line]`; the block carries them."""
    result = block(PROSE, 140.0)
    assert list(result) == list(result.lines)
    assert len(result) == len(result.lines)
