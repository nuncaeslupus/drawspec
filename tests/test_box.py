"""T6 — box geometry, vertical centring, rank normalisation, elastic fit.

The gate is `text_overflow_count == 0`, and the specific thing it is protecting is
the bottom margin: a starved one was the single most repeated failure in the
source review. So every assertion here is made against all four sides, and the
centring is checked against the font's own ascent and descent rather than
against half the type size, which is the approximation that produces the
bottom-heavy box in the first place.

The elastic fit is checked for the property that matters more than the number:
**one** factor, applied to every type level at once. Scaling levels
independently is how 51 of the corpus's 87 diagrams ended up with a different
type size in every element.
"""

from __future__ import annotations

import pytest

from drawspec.errors import FitError
from drawspec.geometry import (
    FIT_STEP,
    MIN_ASPECT,
    Box,
    candidate_factors,
    fit,
    normalise,
    outer_size,
    size_box,
    usable_span,
)
from drawspec.text import TextMeasurer
from drawspec.theme import TYPE_LEVELS, Theme, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

SHORT = "Request arrives"
LONG = (
    "An incoming request is validated, then either accepted for processing "
    "or rejected with a reason the caller can act on."
)


def box(
    text: str = SHORT,
    *,
    role: str = "step",
    level: str = "body",
    max_width: float = 220.0,
    theme: Theme = THEME,
) -> Box:
    return size_box(
        text, theme=theme, measurer=MEASURER, role=role, level=level, max_width=max_width
    )


# --------------------------------------------------------------------------
# The gate: text sits inside its padding, on all four sides
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", [SHORT, LONG, "Ag", "yjgpq", ""])
@pytest.mark.parametrize("role", ["step", "start", "decision", "note"])
def test_box_contains_its_text_with_full_padding_on_all_four_sides(text: str, role: str) -> None:
    """`text_overflow_count == 0`, measured on every side including the bottom."""
    result = box(text, role=role)
    padding = THEME.box.padding

    left, top, right, bottom = result.content_bounds()
    assert left >= result.usable_left + padding.left - 1e-9
    assert right <= result.usable_right - padding.right + 1e-9
    assert top >= result.usable_top + padding.top - 1e-9
    assert bottom <= result.usable_bottom - padding.bottom + 1e-9


@pytest.mark.parametrize("text", [SHORT, LONG])
def test_box_every_line_fits_the_usable_width(text: str) -> None:
    result = box(text)
    for line in result.block.lines:
        assert line.width <= result.content_width + 1e-9


def test_box_bottom_margin_is_not_smaller_than_the_top() -> None:
    """The failure this task exists to prevent, asserted directly."""
    result = box(LONG)
    _, top, _, bottom = result.content_bounds()
    above = top - result.usable_top
    below = result.usable_bottom - bottom
    assert below >= above - 1e-9


def test_box_width_is_measured_text_plus_padding_not_the_maximum_offered() -> None:
    """Geometry is derived from the text: a short label gets a small box."""
    result = box(SHORT, max_width=400.0)
    assert result.width < 400.0
    assert result.width == pytest.approx(result.block.width + THEME.box.padding.horizontal)


def test_box_height_is_the_block_height_plus_padding() -> None:
    result = box(LONG)
    assert result.height == pytest.approx(result.block.height + THEME.box.padding.vertical)


def test_box_never_exceeds_the_width_it_was_given() -> None:
    for text in (SHORT, LONG):
        assert box(text, max_width=180.0).width <= 180.0 + 1e-9


def test_box_too_narrow_for_its_text_raises_fiterror() -> None:
    with pytest.raises(FitError):
        box("Unsplittableliteralrunofcharacters", max_width=40.0)


# --------------------------------------------------------------------------
# Vertical centring
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", [SHORT, LONG, "Ag"])
def test_box_text_is_vertically_centred_within_half_a_pixel(text: str) -> None:
    result = box(text)
    _, top, _, bottom = result.content_bounds()
    above = top - (result.usable_top + THEME.box.padding.top)
    below = (result.usable_bottom - THEME.box.padding.bottom) - bottom
    assert abs(above - below) <= 0.5


def test_box_text_stays_centred_when_the_box_is_made_taller() -> None:
    """Normalisation makes boxes taller; the text has to re-centre, not sit up."""
    natural = box(SHORT)
    taller = natural.resized(height=natural.height + 40.0)
    _, top, _, bottom = taller.content_bounds()
    above = top - (taller.usable_top + THEME.box.padding.top)
    below = (taller.usable_bottom - THEME.box.padding.bottom) - bottom
    assert abs(above - below) <= 0.5


def test_box_centring_comes_from_ascent_and_descent_not_half_the_size() -> None:
    """A box of "Ag" and a box of "ace" are the same height and same baseline."""
    with_descender = box("Ag")
    without = box("ace")
    assert with_descender.height == pytest.approx(without.height)
    assert with_descender.baselines() == pytest.approx(without.baselines())


def test_box_baselines_are_absolute_and_ordered() -> None:
    result = box(LONG).moved_to(30.0, 50.0)
    baselines = result.baselines()
    assert len(baselines) == len(result.block.lines)
    assert list(baselines) == sorted(baselines)
    assert baselines[0] > 50.0


def test_box_moved_to_translates_everything_together() -> None:
    origin = box(LONG)
    moved = origin.moved_to(100.0, 200.0)
    assert moved.width == origin.width and moved.height == origin.height
    shift = [
        after - before for before, after in zip(origin.baselines(), moved.baselines(), strict=True)
    ]
    assert all(value == pytest.approx(200.0) for value in shift)


# --------------------------------------------------------------------------
# Shapes whose usable span is narrower than their bounding box
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["rect", "pill", "diamond", "ellipse"])
def test_usable_span_never_exceeds_the_bounding_box(shape: str) -> None:
    width, height = usable_span(shape, 200.0, 60.0)
    assert 0 < width <= 200.0
    assert 0 < height <= 60.0


@pytest.mark.parametrize("shape", ["rect", "pill", "diamond", "ellipse"])
def test_outer_size_and_usable_span_are_inverses(shape: str) -> None:
    """Sizing a box and then asking what fits in it must agree."""
    width, height = outer_size(shape, 120.0, 30.0, THEME.box.padding)
    usable = usable_span(shape, width, height, 30.0)
    assert usable[0] >= 120.0 + THEME.box.padding.horizontal - 1e-6
    assert usable[1] >= 30.0 + THEME.box.padding.vertical - 1e-6


def test_diamond_box_is_larger_than_a_rect_holding_the_same_text() -> None:
    """A diamond narrows away from its middle, so the box has to grow."""
    assert box(SHORT, role="decision").width > box(SHORT, role="step").width


def test_diamond_usable_width_grows_as_its_text_gets_shorter() -> None:
    """The span is a function of the content height, not a fixed fraction.

    This is the whole of T6b: a short label sits in the wide band across the
    diamond's middle, and charging it the largest-inscribed-rectangle price makes
    the box a third wider than it needs to be.
    """
    tall = usable_span("diamond", 200.0, 100.0, 80.0)[0]
    short = usable_span("diamond", 200.0, 100.0, 20.0)[0]
    assert short > tall
    assert short == pytest.approx(200.0 * 0.8)
    assert tall == pytest.approx(200.0 * 0.2)


def test_diamond_holding_a_two_line_label_is_narrower_than_the_inscribed_model() -> None:
    """Measured on the case that prompted this: a decision with a real question in it."""
    question = "Is the payload well formed?"
    result = box(question, role="decision", max_width=268.8)
    inscribed = 2 * (result.block.width + THEME.box.padding.horizontal)
    assert result.width < inscribed * 0.8


def test_ellipse_usable_width_grows_as_its_text_gets_shorter() -> None:
    tall = usable_span("ellipse", 200.0, 100.0, 90.0)[0]
    short = usable_span("ellipse", 200.0, 100.0, 20.0)[0]
    assert short > tall


def test_ellipse_text_stays_inside_the_curve() -> None:
    """Every corner of the text satisfies the ellipse inequality."""
    curved = load_theme({"version": 1, "name": "curved", "role": {"note": {"shape": "ellipse"}}})
    result = size_box(
        SHORT, theme=curved, measurer=MEASURER, role="note", level="body", max_width=300.0
    )
    left, top, right, bottom = result.content_bounds()
    radius_x, radius_y = result.width / 2, result.height / 2
    for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
        offset_x = (x - radius_x) / radius_x
        offset_y = (y - radius_y) / radius_y
        assert offset_x**2 + offset_y**2 <= 1.0 + 1e-9, (x, y)


def test_diamond_text_stays_inside_the_sloped_sides() -> None:
    result = box(SHORT, role="decision")
    left, top, right, bottom = result.content_bounds()
    # Every corner of the text's bounds is inside the diamond: |dx|/rx + |dy|/ry <= 1.
    centre_x, centre_y = result.width / 2, result.height / 2
    for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
        assert abs(x - centre_x) / centre_x + abs(y - centre_y) / centre_y <= 1.0 + 1e-9


def _inside_pill(x: float, y: float, width: float, height: float) -> bool:
    """Whether a point is inside a pill: a rect between two semicircular caps."""
    radius = height / 2
    if radius <= x <= width - radius:
        return 0.0 <= y <= height
    centre = radius if x < radius else width - radius
    return (x - centre) ** 2 + (y - radius) ** 2 <= radius**2 + 1e-9


def test_pill_text_stays_inside_the_outline_including_the_caps() -> None:
    """Every corner of the text is inside the pill — not merely between its caps.

    The conservative reading, "text may not enter a cap at all", would force a
    short label into a near-circular box. What matters is the outline.
    """
    result = box(SHORT, role="start")
    left, top, right, bottom = result.content_bounds()
    for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
        assert _inside_pill(x, y, result.width, result.height), (x, y)


def test_pill_holding_a_short_label_is_not_much_wider_than_a_rect() -> None:
    """The point of the exact geometry: a `start` beside a `step` looks like a peer."""
    pill = box(SHORT, role="start")
    rect = box(SHORT, role="step")
    assert pill.width < rect.width * 1.4


def test_usable_span_of_an_unknown_shape_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        usable_span("octagon", 100.0, 40.0)


# --------------------------------------------------------------------------
# A shape does not pay for its own outline out of the caller's allowance
# --------------------------------------------------------------------------

#: Long enough to need several lines in a pill of the width a graph offers, which
#: is the case the whole widening rule exists for: the corpus's tallest box was
#: nine lines of this shape.
WORDY = (
    "Via de l'art. 143 (ordinària) — diputacions i dos terços dels municipis "
    "amb majoria del cens, en sis mesos"
)


def test_a_pill_that_would_be_too_vertical_is_offered_more_width() -> None:
    """The reviewer's most repeated note, as an assertion.

    A pill's text may only use the flat span between its caps, so a taller pill
    is a narrower one and wrapping into that narrower span makes it taller again.
    Held to the allowance, this text settles as a column; allowed past it, the
    same words take fewer lines in a box that reads as a label.
    """
    held = box(WORDY, role="start", max_width=180.0)
    offered = size_box(
        WORDY,
        theme=THEME,
        measurer=MEASURER,
        role="start",
        level="body",
        max_width=160.0,
        widen=2.0,
    )
    assert held.shape == offered.shape == "pill"
    assert len(offered.block.lines) < len(held.block.lines)
    assert offered.height < held.height
    assert offered.width <= 180.0 * 2.0


def test_width_that_buys_no_lines_is_not_taken() -> None:
    """A short label stays exactly as narrow as its own text.

    This is what keeps the rule from being "make everything wider": the wider
    offer is only kept when the box needs fewer lines for it.
    """
    tight = box(SHORT, max_width=160.0)
    offered = size_box(
        SHORT, theme=THEME, measurer=MEASURER, role="step", level="body", max_width=160.0, widen=2.0
    )
    assert offered.width == pytest.approx(tight.width)
    assert offered.height == pytest.approx(tight.height)


def test_a_box_stops_widening_once_it_is_wide_enough() -> None:
    """It is a floor, not a target: nothing is stretched past `MIN_ASPECT`."""
    offered = size_box(
        WORDY, theme=THEME, measurer=MEASURER, role="step", level="body", max_width=160.0, widen=4.0
    )
    narrower = size_box(
        WORDY, theme=THEME, measurer=MEASURER, role="step", level="body", max_width=160.0, widen=8.0
    )
    assert offered.width == pytest.approx(narrower.width), "a larger ceiling changed the answer"
    assert offered.width >= offered.height * MIN_ASPECT or offered.width == pytest.approx(640.0)


def test_a_narrow_offer_that_cannot_settle_widens_instead_of_refusing() -> None:
    """The failure that used to shrink the whole diagram to fix one box.

    A pill this narrow cannot break the text at all, and the `FitError` it raises
    is what sent `fit` down a step of type scale — so a single unlucky label set
    the size of every other word in the drawing. Offered more width, the box
    settles and the type stays where it was.
    """
    with pytest.raises(FitError):
        size_box(WORDY, theme=THEME, measurer=MEASURER, role="start", level="body", max_width=60.0)
    widened = size_box(
        WORDY, theme=THEME, measurer=MEASURER, role="start", level="body", max_width=60.0, widen=6.0
    )
    assert widened.block.lines


def test_a_box_that_fits_at_no_offered_width_still_refuses() -> None:
    """Widening is a wider search, not a way to stop saying no."""
    with pytest.raises(FitError):
        size_box(
            WORDY,
            theme=THEME,
            measurer=MEASURER,
            role="start",
            level="body",
            max_width=40.0,
            widen=2.0,
        )


# --------------------------------------------------------------------------
# Same-rank normalisation
# --------------------------------------------------------------------------


def test_boxes_of_the_same_rank_are_normalised_to_one_width() -> None:
    """A shared edge is what makes peers read as peers."""
    boxes = [box("Yes"), box("No"), box("Needs a longer label than the others")]
    normalised = normalise(boxes)
    assert len({round(item.width, 6) for item in normalised}) == 1


def test_normalisation_leaves_each_box_the_height_of_its_own_text() -> None:
    """One long sentence anywhere used to grow every other box to match it.

    Across the corpus that made 13% of boxes taller than their own text — the
    worst by three times over — and 19% of all box area existed only because a peer needed
    it. `Yes` is one line whatever its siblings say.
    """
    boxes = [box("Yes"), box("No"), box("Needs a longer label than the others")]
    normalised = normalise(boxes)
    assert normalised[0].height == normalised[1].height < normalised[2].height
    assert normalised[0].height == box("Yes").height


def test_normalisation_can_still_be_asked_for_one_slab() -> None:
    """A band read across rather than as separate boxes wants equal heights."""
    boxes = normalise([box("Yes"), box("Needs a longer label than the others")], height=True)
    assert len({round(item.height, 6) for item in boxes}) == 1


def test_normalisation_grows_boxes_and_never_shrinks_them() -> None:
    boxes = [box("Yes"), box("Needs a longer label than the others")]
    normalised = normalise(boxes)
    for before, after in zip(boxes, normalised, strict=True):
        assert after.width >= before.width
        assert after.height >= before.height


def test_normalised_boxes_still_contain_their_text_with_full_padding() -> None:
    boxes = normalise([box("Yes"), box(LONG)])
    padding = THEME.box.padding
    for item in boxes:
        left, top, right, bottom = item.content_bounds()
        assert left >= item.usable_left + padding.left - 1e-9
        assert right <= item.usable_right - padding.right + 1e-9
        assert top >= item.usable_top + padding.top - 1e-9
        assert bottom <= item.usable_bottom - padding.bottom + 1e-9


def test_normalise_of_an_empty_group_is_empty() -> None:
    assert normalise([]) == ()


def test_normalise_leaves_a_single_box_alone() -> None:
    only = box(SHORT)
    assert normalise([only]) == (only,)


# --------------------------------------------------------------------------
# Elastic fit: one factor, every level, or a refusal
# --------------------------------------------------------------------------


def test_fit_applies_one_scale_factor_to_every_type_level() -> None:
    """The ratios between the four levels are unchanged, so no diagram gains a
    type size it did not have."""
    fitted = fit(THEME, lambda theme: box(LONG, max_width=150.0, theme=theme))
    for level in TYPE_LEVELS:
        assert fitted.theme.scale[level] == pytest.approx(THEME.scale[level] * fitted.factor)
    ratios_before = [THEME.scale[level] / THEME.scale["body"] for level in TYPE_LEVELS]
    ratios_after = [fitted.theme.scale[level] / fitted.theme.scale["body"] for level in TYPE_LEVELS]
    assert ratios_after == pytest.approx(ratios_before)


def test_fit_chooses_the_largest_factor_that_fits_within_the_band() -> None:
    """Shrinking stops as soon as the content fits."""
    fitted = fit(THEME, lambda theme: box(LONG, max_width=150.0, theme=theme))
    assert fitted.factor <= THEME.fit.scale_max
    assert fitted.factor >= THEME.fit.scale_min
    # One step larger must not fit, or a larger factor was available and skipped.
    larger = fitted.factor + FIT_STEP
    if larger <= THEME.fit.scale_max:
        with pytest.raises(FitError):
            box(LONG, max_width=150.0, theme=THEME.with_scale(larger))


def test_fit_returns_scale_max_when_the_content_already_fits() -> None:
    fitted = fit(THEME, lambda theme: box(SHORT, max_width=400.0, theme=theme))
    assert fitted.factor == pytest.approx(THEME.fit.scale_max)
    assert fitted.value.width > 0


def test_fit_below_scale_min_raises_fiterror() -> None:
    with pytest.raises(FitError) as error:
        fit(THEME, lambda theme: box(LONG, max_width=60.0, theme=theme))
    message = str(error.value)
    assert str(THEME.fit.scale_min) in message
    assert "restructure" in message.lower()


def test_fit_below_min_legible_size_raises_fiterror() -> None:
    """A band that would take the body below the legibility floor is refused."""
    unreadable = load_theme(
        {
            "version": 1,
            "name": "unreadable",
            "canvas": {"min_legible_size": 12.0},
            "fit": {"scale_min": 0.5, "scale_max": 0.9},
        }
    )
    with pytest.raises(FitError) as error:
        fit(unreadable, lambda theme: box(LONG, max_width=60.0, theme=theme))
    assert "min_legible_size" in str(error.value) or "legible" in str(error.value)


def test_fit_never_offers_a_factor_below_the_legibility_floor() -> None:
    theme = load_theme(
        {
            "version": 1,
            "name": "floored",
            "canvas": {"min_legible_size": 10.0},
            "fit": {"scale_min": 0.5, "scale_max": 1.0},
        }
    )
    for factor in candidate_factors(theme):
        assert factor * theme.scale["body"] >= 10.0 - 1e-9


def test_candidate_factors_descend_from_scale_max() -> None:
    factors = candidate_factors(THEME)
    assert factors[0] == pytest.approx(THEME.fit.scale_max)
    assert factors[-1] >= THEME.fit.scale_min - 1e-9
    assert list(factors) == sorted(factors, reverse=True)


def test_fit_is_deterministic() -> None:
    first = fit(THEME, lambda theme: box(LONG, max_width=150.0, theme=theme))
    second = fit(THEME, lambda theme: box(LONG, max_width=150.0, theme=theme))
    assert first.factor == second.factor
    assert first.value.width == second.value.width


def test_fit_does_not_swallow_an_error_that_is_not_a_fit_failure() -> None:
    """A bug in a family renderer must not look like content that will not fit."""

    def broken(theme: Theme) -> Box:
        raise KeyError("a real bug")

    with pytest.raises(KeyError):
        fit(THEME, broken)


def test_fit_a_theme_that_cannot_grow_does_not_try_to() -> None:
    """`scale_max = 1.0` means shrink to fit, never grow."""
    assert max(candidate_factors(THEME)) == pytest.approx(1.0)
