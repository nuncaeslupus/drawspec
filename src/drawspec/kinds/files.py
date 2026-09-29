"""The `files` kind: a directory listing, drawn like a file browser.

Rows top to bottom, one per name, each indented under its folder and joined to
it by a guide. The rows themselves come from `drawspec.filetree`, which also
validates the paths; this module only decides where each row goes and what it
is drawn with.

Every length here is a multiple of `unit`, the body size over eleven, so a tree
the fit pass shrinks shrinks as one drawing — pictures, guides and gaps with the
type — rather than leaving eleven-point icons beside nine-point names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from drawspec.filetree import STATUS_MARKS, Row, rows, text
from drawspec.scene import Path, Polygon, Primitive, Rect, Scene, TextRun
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The roles every part is drawn in. Pictures are outlined like a box; guides,
#: a symlink's arrow and a strike-through are thin like a link; a status is a
#: pill, the one role whose shape already reads as a tag.
PICTURE: Final = "step"
GUIDE: Final = "link"
STATUS: Final = "start"

#: Which picture a file's extension earns, when the theme asks for type
#: pictures. Five families, not one per language: a tree is read at a glance,
#: and a reader tells five shapes apart where fifty would each need learning.
#: Anything unlisted is a plain page. Drawn with strokes, never letters — an
#: extension spelled inside a sixteen-unit page is type below the theme's
#: legible minimum, and the name beside it already spells it out.
TYPES: Final[dict[str, tuple[str, ...]]] = {
    "code": (
        "c",
        "cc",
        "cpp",
        "cs",
        "css",
        "go",
        "h",
        "hpp",
        "html",
        "java",
        "js",
        "jsx",
        "kt",
        "php",
        "py",
        "rb",
        "rs",
        "scss",
        "sh",
        "swift",
        "ts",
        "tsx",
        "vue",
    ),
    "data": (
        "csv",
        "env",
        "ini",
        "json",
        "jsonl",
        "lock",
        "toml",
        "tsv",
        "xml",
        "yaml",
        "yml",
    ),
    "text": (
        "adoc",
        "doc",
        "docx",
        "md",
        "odt",
        "pdf",
        "rst",
        "rtf",
        "tex",
        "txt",
    ),
    "image": (
        "bmp",
        "gif",
        "ico",
        "jpeg",
        "jpg",
        "png",
        "svg",
        "tif",
        "tiff",
        "webp",
    ),
    "archive": (
        "7z",
        "bz2",
        "gz",
        "jar",
        "rar",
        "tar",
        "tgz",
        "whl",
        "xz",
        "zip",
    ),
}
FAMILY_OF: Final = {extension: family for family, names in TYPES.items() for extension in names}

#: Words a status pill says, after its mark — the mark alone is a symbol a
#: reader has to learn, and the word alone is easy to miss down a column.
STATUS_WORDS: Final = {"added": "added", "changed": "changed", "removed": "removed"}


@dataclass(frozen=True)
class _Metrics:
    unit: float
    body: float
    label: float
    pitch: float
    ascent: float
    descent: float


def files_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a file tree in the style it names."""
    tree = rows(document.entries, document.root, document.order)
    if document.style in ("unicode", "ascii"):
        primitives, width, height = _as_text(tree, document.style, theme, measurer)
    else:
        primitives, width, height = _drawn(tree, document.style == "icons", theme, measurer)
    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def _metrics(theme: Theme, measurer: TextMeasurer, font: str, pitch: float) -> _Metrics:
    body = theme.scale["body"]
    unit = body / 11
    extents = measurer.measure("Ag", font, body)
    return _Metrics(
        unit=unit,
        body=body,
        label=theme.scale["label"],
        pitch=pitch * unit,
        ascent=extents.ascent,
        descent=extents.descent,
    )


# ---------------------------------------------------------------------------
# Text: the tree as `tree` prints it
# ---------------------------------------------------------------------------


def _as_text(
    tree: tuple[Row, ...], charset: str, theme: Theme, measurer: TextMeasurer
) -> tuple[list[Primitive], float, float]:
    """One monospace run per word, each placed by its column.

    Not one run per line: SVG collapses a run of spaces to one, and the spaces
    are the tree — a line written whole loses its indentation in every viewer.
    Placing each word at its own column keeps the alignment without asking the
    host page for `xml:space`, which an inline SVG cannot rely on.
    """
    metrics = _metrics(theme, measurer, "mono", 17)
    advance = measurer.advance("M", "mono", metrics.body)
    lines = text(tree, "unicode" if charset == "unicode" else "ascii").splitlines()
    primitives: list[Primitive] = []
    widest = 0.0
    for index, line in enumerate(lines):
        baseline = index * metrics.pitch + (metrics.pitch + metrics.ascent - metrics.descent) / 2
        column = 0
        for word in line.split(" "):
            if word:
                primitives.append(
                    TextRun(
                        PICTURE,
                        x=column * advance,
                        y=baseline,
                        text=word,
                        level="body",
                        font="mono",
                    )
                )
            column += len(word) + 1
        widest = max(widest, len(line) * advance)
    return primitives, widest, len(lines) * metrics.pitch


# ---------------------------------------------------------------------------
# Drawn: guides, pictures, names
# ---------------------------------------------------------------------------


def _drawn(
    tree: tuple[Row, ...], icons: bool, theme: Theme, measurer: TextMeasurer
) -> tuple[list[Primitive], float, float]:
    metrics = _metrics(theme, measurer, "sans", 25 if icons else 22)
    unit = metrics.unit

    half = 8 * unit if icons else 0.0
    step = half + 12 * unit if icons else 20 * unit
    gap = 6 * unit

    def centre(row: Row) -> float:
        """Where this row's guide drops from: its picture's middle, or its name's start."""
        return half + row.depth * step if icons else row.depth * step + 4 * unit

    def name_x(row: Row) -> float:
        return centre(row) + half + gap if icons else row.depth * step

    def middle(index: int) -> float:
        return index * metrics.pitch + metrics.pitch / 2

    primitives: list[Primitive] = []
    ends: list[float] = []
    names: list[TextRun] = []

    for index, row in enumerate(tree):
        y = middle(index)
        baseline = y + (metrics.ascent - metrics.descent) / 2
        x = name_x(row)
        folder = row.kind == "folder"
        label = row.name + ("/" if folder and not icons else "")
        weight = "bold" if folder else "normal"
        level = "label" if row.kind == "more" and not icons else "body"
        if row.kind == "more" and icons:
            primitives.append(
                TextRun(PICTURE, x=centre(row), y=baseline, text="…", level="body", anchor="middle")
            )
            label = row.name.removeprefix("…").strip()
            level = "label"
        size = theme.scale[level]
        if label:
            names.append(TextRun(PICTURE, x=x, y=baseline, text=label, level=level, weight=weight))
        end = x + measurer.advance(label, "sans", size, weight)

        if row.status == "removed":
            strike = y + (metrics.ascent - metrics.descent) / 2 - metrics.ascent * 0.35
            primitives.append(Path(GUIDE, points=((x - unit, strike), (end + unit, strike))))
        if row.kind == "link":
            target = f"→ {row.link}"
            names.append(TextRun(PICTURE, x=end + gap, y=baseline, text=target, level="body"))
            end += gap + measurer.advance(target, "sans", metrics.body)
        if row.status:
            end = _pill(row.status, end + gap, y, primitives, names, metrics, measurer)
        ends.append(end)

        if icons and row.kind != "more":
            primitives.extend(_picture(row, centre(row), y, theme, metrics))

    # Guides: a vertical from each parent down to its last child, and a stub
    # across to every child. Drawn from the rows, so a '...' row is joined too.
    below = 9 * unit if icons else metrics.descent + 2 * unit
    last_child: dict[int, int] = {}
    for index, row in enumerate(tree):
        if row.parent is not None:
            last_child[row.parent] = index
            above = tree[row.parent]
            reach = centre(row) - half - 2 * unit if icons else name_x(row) - 4 * unit
            primitives.append(
                Path(GUIDE, points=((centre(above), middle(index)), (reach, middle(index))))
            )
    for parent, child in last_child.items():
        x = centre(tree[parent])
        primitives.append(Path(GUIDE, points=((x, middle(parent) + below), (x, middle(child)))))

    # Notes share one column, so a reader scans them as the comments they are.
    noted = [index for index, row in enumerate(tree) if row.note]
    column = max((ends[index] for index in noted), default=0.0) + 3 * gap
    for index in noted:
        baseline = middle(index) + (metrics.ascent - metrics.descent) / 2
        note = tree[index].note
        names.append(TextRun(PICTURE, x=column, y=baseline, text=note, level="label"))
        ends[index] = column + measurer.advance(note, "sans", metrics.label)

    width = max(ends, default=0.0)
    return [*primitives, *names], width, len(tree) * metrics.pitch


def _extension(row: Row) -> str:
    return row.name.rsplit(".", 1)[1].lower() if "." in row.name.lstrip(".") else ""


def _pill(
    status: str,
    x: float,
    y: float,
    primitives: list[Primitive],
    names: list[TextRun],
    metrics: _Metrics,
    measurer: TextMeasurer,
) -> float:
    words = f"{STATUS_MARKS[status]} {STATUS_WORDS[status]}"
    width = measurer.advance(words, "sans", metrics.label) + 10 * metrics.unit
    extents = measurer.measure(words, "sans", metrics.label)
    height = extents.height + 3 * metrics.unit
    primitives.append(Rect(STATUS, x=x, y=y - height / 2, width=width, height=height))
    names.append(
        TextRun(
            PICTURE,
            x=x + width / 2,
            y=y + (extents.ascent - extents.descent) / 2,
            text=words,
            level="label",
            anchor="middle",
        )
    )
    return x + width


def _picture(row: Row, cx: float, cy: float, theme: Theme, metrics: _Metrics) -> list[Primitive]:
    """A folder, or a page with what kind of file it is drawn on it — centred on (cx, cy)."""
    u = metrics.unit
    style = theme.files

    def at(*points: tuple[float, float]) -> tuple[tuple[float, float], ...]:
        return tuple((cx + x * u, cy + y * u) for x, y in points)

    def tinted(points: tuple[tuple[float, float], ...], colour: str) -> Polygon:
        return Polygon(
            PICTURE,
            points=points,
            fill="solid" if style.tint and colour else "",
            fill_colour=colour,
            fill_opacity=style.tint or 1.0,
        )

    if row.kind == "folder":
        colour = style.colour_for("folder") or "currentColor"
        return [tinted(at((-8, -6), (-2, -6), (0, -4), (8, -4), (8, 6), (-8, 6)), colour)]

    extension = _extension(row)
    family = FAMILY_OF.get(extension, "") if style.types else ""
    colour = style.colour_for(extension) or style.colour_for(family)
    drawn: list[Primitive] = [
        tinted(at((-7, -9), (2, -9), (7, -4), (7, 9), (-7, 9)), colour),
        Path(GUIDE, points=at((2, -9), (2, -4), (7, -4))),
    ]
    if row.kind == "link":
        drawn.append(Path(GUIDE, points=at((-3, 6), (-3, 1), (3, 1))))
        drawn.append(Path(GUIDE, points=at((0.5, -1.5), (3, 1), (0.5, 3.5)), marker=True))
        return drawn
    drawn.extend(Path(GUIDE, points=at(*stroke)) for stroke in _PICTOGRAMS.get(family, ()))
    return drawn


#: Each family's picture, as strokes in page units — the page runs from -7 to 7
#: across and -9 to 9 down, and every picture keeps to its lower two thirds, clear
#: of the folded corner.
_PICTOGRAMS: Final[dict[str, tuple[tuple[tuple[float, float], ...], ...]]] = {
    "code": (
        ((-1.5, -0.5), (-4.5, 2.5), (-1.5, 5.5)),
        ((1.5, -0.5), (4.5, 2.5), (1.5, 5.5)),
    ),
    "data": (
        ((-1.5, -1), (-3, -1), (-3, 1.8), (-4.5, 2.5), (-3, 3.2), (-3, 6), (-1.5, 6)),
        ((1.5, -1), (3, -1), (3, 1.8), (4.5, 2.5), (3, 3.2), (3, 6), (1.5, 6)),
    ),
    "text": (
        ((-4, -1), (4, -1)),
        ((-4, 2), (4, 2)),
        ((-4, 5), (1.5, 5)),
    ),
    "image": (
        ((-4.5, 6), (-1.5, 1.5), (0.8, 4.5), (2.2, 3), (4.5, 6), (-4.5, 6)),
        ((2, -1.5), (3.5, -1.5), (3.5, 0), (2, 0), (2, -1.5)),
    ),
    "archive": (
        ((0, -7), (0, 6)),
        ((-1.5, -5.5), (0, -5.5)),
        ((0, -3.5), (1.5, -3.5)),
        ((-1.5, -1.5), (0, -1.5)),
        ((0, 0.5), (1.5, 0.5)),
        ((-1.5, 3), (1.5, 3), (1.5, 6), (-1.5, 6), (-1.5, 3)),
    ),
}


__all__ = ["files_scene"]
