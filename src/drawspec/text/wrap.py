"""Line breaking and text block sizing.

Two failures from the corpus are answered here. Text escaping its box is the
first: every line this module returns has been *measured* at or below the width
it was given, so a box built from these numbers cannot overflow horizontally.
Uneven line spacing is the second: one advance is used for every line in a
block, computed from the theme, so there are never tight lines beside loose ones.

The third answer is the refusal. When a run cannot be broken small enough to fit
— a long identifier in a narrow column — this raises `FitError` rather than
letting it hang over the edge or quietly shrinking the type. The theme's elastic
fit (T6) is what decides whether shrinking is allowed, and it is a decision about
the whole diagram; here the only options are to break or to say so.

Inline spans are handled here rather than downstream because they change the
measurement: `` `code` `` is monospace and `**bold**` is bold, and both are wider
than the same words in body text. A wrapper that could not see them would
measure the wrong string and produce exactly the overflow it exists to prevent.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Final

from drawspec.errors import FitError
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Characters after which a long unbroken run may be split. "Break into more
#: lines" is the first remedy the style rules offer, so it is tried before the
#: refusal — an identifier like `queue.process(batch_id)` has real break
#: opportunities and does not need to be a `FitError`.
BREAK_AFTER: Final = "-/_.:,)]}>"

#: `` `code` `` selects the monospace role and `**bold**` the bold weight. Both
#: are semantic — a command is a command, and the main concept is the main
#: concept — which is why an author may write them and may not write a font size.
_SPAN_PATTERN: Final = re.compile(r"`([^`]+)`|\*\*([^*]+)\*\*")


@dataclass(frozen=True)
class Span:
    """A run of text in one font and weight."""

    text: str
    font: str = "sans"
    weight: str = "normal"

    def with_text(self, text: str) -> Span:
        return Span(text=text, font=self.font, weight=self.weight)


@dataclass(frozen=True)
class Line:
    """One laid-out line: its spans, and the width they were measured at."""

    spans: tuple[Span, ...]
    width: float

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


@dataclass(frozen=True)
class TextBlock:
    """A wrapped block: its lines, its extents, and where each baseline sits.

    Iterating a block yields its lines, so the `wrap(...) -> list[Line]` shape
    the specification names is `list(block)`. The block exists because the height
    and the baselines have to come from the same place as the lines — a caller
    that computed height itself would be the second source of truth for it.
    """

    lines: tuple[Line, ...]
    width: float
    height: float
    advance: float
    """Baseline-to-baseline distance: the theme's line height times the size."""

    ascent: float
    descent: float

    def __iter__(self) -> Iterator[Line]:
        return iter(self.lines)

    def __len__(self) -> int:
        return len(self.lines)

    def baseline(self, index: int) -> float:
        """Where line `index`'s baseline sits, measured from the block's top.

        Each line occupies a slot of `advance`, and the baseline sits so the
        line is optically centred in its slot — computed from the font's ascent
        and descent rather than from half the size, which is the approximation
        that leaves a box looking bottom-heavy.
        """
        if not 0 <= index < len(self.lines):
            raise IndexError(f"line {index} of a {len(self.lines)}-line block")
        return index * self.advance + (self.advance + self.ascent - self.descent) / 2


def parse_spans(text: str, *, font: str = "sans") -> tuple[Span, ...]:
    """Split `text` into spans on its inline markers.

    An unmatched marker is literal text: a stray backtick or asterisk in a
    diagram label is a character an author meant, not a syntax error worth
    failing a render over.
    """
    spans: list[Span] = []
    position = 0
    for match in _SPAN_PATTERN.finditer(text):
        if match.start() > position:
            spans.append(Span(text[position : match.start()], font=font))
        code, bold = match.groups()
        if code is not None:
            spans.append(Span(code, font="mono"))
        else:
            spans.append(Span(bold, font=font, weight="bold"))
        position = match.end()
    if position < len(text):
        spans.append(Span(text[position:], font=font))
    return tuple(spans) or (Span("", font=font),)


@dataclass(frozen=True)
class _Word:
    """One breakable unit, and whether a space precedes it on the same line."""

    span: Span
    text: str
    width: float


def wrap(
    text: str,
    max_width: float,
    measurer: TextMeasurer,
    *,
    theme: Theme,
    level: str = "body",
    lead: bool | None = None,
) -> TextBlock:
    """Break `text` to `max_width` and size the block it makes.

    Args:
        text: the words, possibly carrying inline spans.
        max_width: the usable width — the box width less the theme's padding.
        measurer: measures against the theme's own font stacks.
        theme: supplies the type size for `level` and the line height.
        level: which of the four type levels this text is set at.
        lead: whether the first paragraph is a lead. `None` asks the text
            itself — it is a lead when something follows it — which is right
            for a label standing alone. A caller sizing a *set* of peers passes
            the answer for the set, so that a bare name among named-and-
            explained ones is still a name: whether a particular member happens
            to carry an explanation is incidental, and it should not decide how
            that member's name is set.

    Raises:
        FitError: a run cannot be broken small enough to fit `max_width`.
        ValueError: `max_width` is not positive.
        KeyError: `level` is not one of the theme's type levels.
    """
    if max_width <= 0:
        raise ValueError(f"max_width must be positive, got {max_width!r}")
    size = theme.scale[level]
    advance = theme.box.line_height * size
    default_font = theme.font.default

    extents = measurer.measure("", default_font, size)
    paragraphs = text.split("\n")
    # A label with a second paragraph has said its first one is a lead. The
    # theme decides what that looks like; here it only decides which words it
    # applies to, and it applies before measurement because a bold word is wider
    # than the same word is not, and a wrapper that could not see that would
    # produce exactly the overflow this module exists to prevent.
    wanted = len(paragraphs) > 1 if lead is None else lead
    lead_set = theme.box.lead == "bold" and wanted
    lines: list[Line] = []
    for index, paragraph in enumerate(paragraphs):
        lines.extend(
            _wrap_paragraph(
                paragraph, max_width, measurer, size, default_font, bold=lead_set and index == 0
            )
        )

    return TextBlock(
        lines=tuple(lines),
        width=max((line.width for line in lines), default=0.0),
        height=len(lines) * advance,
        advance=advance,
        ascent=extents.ascent,
        descent=extents.descent,
    )


def _wrap_paragraph(
    paragraph: str,
    max_width: float,
    measurer: TextMeasurer,
    size: float,
    default_font: str,
    *,
    bold: bool = False,
) -> list[Line]:
    words = _words(paragraph, measurer, size, default_font, bold=bold)
    if not words:
        return [Line(spans=(Span("", font=default_font),), width=0.0)]

    lines: list[Line] = []
    current: list[_Word] = []

    for word in words:
        candidate = [*current, word]
        if current and _width(candidate, measurer, size) > max_width:
            lines.append(_line(current, measurer, size))
            current = [word]
        else:
            current = candidate
        # A single word that does not fit on a line of its own has to be split,
        # or reported. Either way it never stays as it is.
        while _width(current, measurer, size) > max_width:
            head, tail = _split(current[-1], max_width, measurer, size, len(current) > 1)
            if head is None:
                lines.append(_line(current[:-1], measurer, size)) if len(current) > 1 else None
                raise _fit_error(current[-1], max_width, measurer, size)
            lines.append(_line([*current[:-1], head], measurer, size))
            current = [tail]

    if current:
        lines.append(_line(current, measurer, size))
    return [line for line in lines if line.spans]


def _words(
    paragraph: str,
    measurer: TextMeasurer,
    size: float,
    default_font: str,
    *,
    bold: bool = False,
) -> list[_Word]:
    """Split a paragraph into measured words, keeping each word's span.

    `bold` is the theme's lead treatment reaching the words: it promotes the
    weight of every span that has not already asked for one, so an author who
    wrote `` `code` `` in a lead keeps their monospace and one who wrote nothing
    gets the bold.
    """
    words: list[_Word] = []
    for original in parse_spans(paragraph, font=default_font):
        span = replace(original, weight="bold") if bold else original
        for piece in span.text.split():
            words.append(
                _Word(
                    span=span,
                    text=piece,
                    width=measurer.measure(piece, span.font, size, span.weight).width,
                )
            )
    return words


def _line(words: list[_Word], measurer: TextMeasurer, size: float) -> Line:
    """Join words into a line, merging neighbours that share a span."""
    if not words:
        return Line(spans=(), width=0.0)
    spans: list[Span] = []
    for index, word in enumerate(words):
        text = (" " if index else "") + word.text
        if spans and words[index - 1].span == word.span:
            spans[-1] = spans[-1].with_text(spans[-1].text + text)
        else:
            spans.append(word.span.with_text(text.lstrip() if not spans else text))
    return Line(spans=tuple(spans), width=_measure_spans(tuple(spans), measurer, size))


def _measure_spans(spans: tuple[Span, ...], measurer: TextMeasurer, size: float) -> float:
    """Width of a line, measured span by span.

    Per span rather than over the joined string, because a span boundary is a
    font change and no font kerns across one.
    """
    return sum(measurer.measure(span.text, span.font, size, span.weight).width for span in spans)


def _width(words: list[_Word], measurer: TextMeasurer, size: float) -> float:
    return _line(words, measurer, size).width


def _split(
    word: _Word, max_width: float, measurer: TextMeasurer, size: float, has_company: bool
) -> tuple[_Word | None, _Word]:
    """Split `word` at the last break opportunity that fits, or report failure.

    Returns `(None, word)` when there is no split that helps, which is the
    caller's cue to raise. A word that shares its line with others is not split
    at all — it goes to the next line first, and is only split if it still does
    not fit there.
    """
    if has_company:
        return None, word

    for position in range(len(word.text) - 1, 0, -1):
        if word.text[position - 1] not in BREAK_AFTER:
            continue
        head = word.text[:position]
        width = measurer.measure(head, word.span.font, size, word.span.weight).width
        if width <= max_width:
            tail = word.text[position:]
            return (
                _Word(span=word.span, text=head, width=width),
                _Word(
                    span=word.span,
                    text=tail,
                    width=measurer.measure(tail, word.span.font, size, word.span.weight).width,
                ),
            )
    return None, word


def _fit_error(word: _Word, max_width: float, measurer: TextMeasurer, size: float) -> FitError:
    """The message is the product: what did not fit, by how much, and what to do."""
    width = measurer.measure(word.text, word.span.font, size, word.span.weight).width
    overflow = width - max_width
    return FitError(
        f"{word.text!r} measures {width:.1f} at {size:.1f}pt and has no break "
        f"opportunity that fits {max_width:.1f} — it overflows by {overflow:.1f}. "
        f"There is no way to draw this without text escaping its box, so: shorten "
        f"the text, give the diagram a shape with wider boxes (usually vertical), "
        f"or restructure it. drawspec will not shrink the type past the theme's "
        f"band to make it fit."
    )


__all__ = ["BREAK_AFTER", "Line", "Span", "TextBlock", "parse_spans", "wrap"]
