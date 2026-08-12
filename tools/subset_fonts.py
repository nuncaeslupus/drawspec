#!/usr/bin/env python3
"""Regenerate the bundled generic fonts in `src/drawspec/fonts/`.

drawspec measures text from font files, so "replace and warn" needs something
to replace *with* that is present on every host. The three bundled files are
subsets of DejaVu Sans, DejaVu Serif and DejaVu Sans Mono, cut down from ~1.4 MB
to ~300 kB by dropping glyphs outside the coverage set below.

Subsetting preserves the advance width and the kerning of every glyph it keeps,
so a subset measures identically to the full font. The family names are
deliberately **not** changed: the emitted SVG names the same family it measured,
so a host that happens to have the real DejaVu installed renders exactly what
drawspec sized the boxes for.

Run from the repository root, on a machine with the DejaVu fonts installed:

    uv run python tools/subset_fonts.py

Pass `--source-dir` if DejaVu lives somewhere other than the Debian path.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Latin (incl. Extended-A), Greek, Cyrillic, general punctuation, currency,
# arrows, mathematical operators, geometric shapes and the dingbats a diagram
# label plausibly reaches for. Everything else falls back to `.notdef`, which
# is why the coverage is generous rather than minimal.
UNICODES = ",".join(
    [
        "U+0020-007E",  # Basic Latin
        "U+00A0-00FF",  # Latin-1 Supplement
        "U+0100-017F",  # Latin Extended-A
        "U+0192",  # florin
        "U+02C6",  # modifier circumflex
        "U+02DC",  # small tilde
        "U+0374-03CE",  # Greek
        "U+0400-045F",  # Cyrillic
        "U+2000-206F",  # General Punctuation
        "U+20AC",  # euro
        "U+2122",  # trademark
        "U+2190-21FF",  # Arrows
        "U+2200-22FF",  # Mathematical Operators
        "U+25A0-25FF",  # Geometric Shapes
        "U+2600-26FF",  # Miscellaneous Symbols
    ]
)

# (role, weight) -> DejaVu file name. The role is the name drawspec knows the
# font by; the family name inside the file stays "DejaVu Sans" and friends.
#
# The bold faces are here because **bold** is a semantic span an author may
# write, and a span that is *drawn* bold has to be *measured* bold. Measuring it
# with the regular face under-counts its width — by 3.8 units in one eleven-point
# word — so the run after it starts early and lands on top of it.
FAMILIES = {
    ("sans", "normal"): "DejaVuSans.ttf",
    ("serif", "normal"): "DejaVuSerif.ttf",
    ("mono", "normal"): "DejaVuSansMono.ttf",
    ("sans", "bold"): "DejaVuSans-Bold.ttf",
    ("serif", "bold"): "DejaVuSerif-Bold.ttf",
    ("mono", "bold"): "DejaVuSansMono-Bold.ttf",
}

DEFAULT_SOURCE_DIR = Path("/usr/share/fonts/truetype/dejavu")


def subset(source: Path, destination: Path) -> None:
    """Write a coverage-reduced copy of `source` to `destination`."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "fontTools.subset",
            str(source),
            f"--unicodes={UNICODES}",
            "--layout-features=kern",
            "--no-hinting",
            f"--output-file={destination}",
        ],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("src/drawspec/fonts"), help="where to write"
    )
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for (role, weight), filename in sorted(FAMILIES.items()):
        source = args.source_dir / filename
        if not source.is_file():
            print(f"missing source font: {source}", file=sys.stderr)
            return 1
        stem = role if weight == "normal" else f"{role}-{weight}"
        destination = args.output_dir / f"{stem}.ttf"
        subset(source, destination)
        before = source.stat().st_size // 1024
        after = destination.stat().st_size // 1024
        print(f"{role} {weight}: {filename} {before} kB -> {destination.name} {after} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
