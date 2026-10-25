"""Render every reference document and put it on one page, to be looked at.

Not shipped code. This exists because of two defects found this session by eye
that no gate caught: a `decision` node drawn as a giant rectangle, and a `cycle`
rendered as a column of boxes with all its edges on one line. Both passed every
mechanical check, which is exactly what the specification predicts —
*"'correct' is mechanically checkable; 'beautiful' is not, quite."*

So the habit this supports is: **every kind task ends by running this and
looking at the result**, before its gate is claimed. The plan's own by-eye
judgement is at T18, which is the close-out; that is far too late to find that a
whole kind is in the wrong family.

Three things it deliberately does *not* do:

* It does not fail on a kind that has no renderer yet. A gallery that breaks
  while the tool is half built is a gallery nobody runs.
* It does not fail on `FitError`. A refusal is a legitimate outcome, and its
  message is the product — seeing the message on the page is how its quality
  gets judged.
* It does not assert anything about how the diagrams look. That is the point:
  the judgement is yours.

Usage, from the repository root:

    uv run python tools/gallery.py            # write the SVGs and the page
    uv run python tools/gallery.py --check    # report only, write nothing
"""

from __future__ import annotations

import argparse
import base64
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from drawspec.emit import PROFILES
from drawspec.errors import DrawspecError, FitError
from drawspec.render import render_document
from drawspec.schema import load_document
from drawspec.theme import load_theme

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "docs" / "reference"
GALLERY_DIR = ROOT / "docs" / "gallery"
PAGE = GALLERY_DIR / "index.html"
LOGO = ROOT / "docs" / "logo.svg"

# The order kinds appear in on the page: most used first, so a visitor meets the
# diagrams they are likeliest to want before the specialised ones. `flow` leads
# because it is a third of the hand-drawn corpus (`docs/kinds-wanted.md`); the
# rest is a judgement of how often each shape turns up in docs, specs and READMEs,
# not a measurement. A kind missing from this list still draws, alphabetically
# after the listed ones, so adding a kind never needs this edited to appear.
KIND_ORDER: tuple[str, ...] = (
    "flow",
    "chart",
    "sequence",
    "timeline",
    "tree",
    "mindmap",
    "gantt",
    "entities",
    "states",
    "pie",
    "venn",
    "matrix",
    "quadrant",
    "cycle",
    "lanes",
    "pyramid",
    "funnel",
    "columns",
    "stack",
    "journey",
    "board",
    "scatter",
    "curve",
    "sankey",
    "treemap",
    "fishbone",
    "waterfall",
    "rings",
    "files",
    "argument",
    "familytree",
    "meter",
    "rag",
    "numberline",
    "barmodel",
    "clock",
    "sunburst",
    "wardley",
    "network",
    "timing",
    "gitgraph",
    "railroad",
    "usecase",
)


@dataclass(frozen=True)
class Entry:
    """One reference document's outcome."""

    name: str
    kind: str
    svg: str = ""
    skipped: str = ""
    """Why there is no drawing: an unimplemented kind, or a refusal to fit."""

    @property
    def rendered(self) -> bool:
        return bool(self.svg)


def reference_documents() -> list[Path]:
    """Every reference document, in a stable order."""
    return sorted(REFERENCE_DIR.glob("*.json"))


def build(profile: str = "inline") -> list[Entry]:
    """Render every reference document, recording why any did not draw.

    A document whose theme draws a sheet (`blueprint`) is rendered `standalone`
    whatever `profile` says: the sheet is standalone furniture, and inline it
    would be the same drawing as any other theme's. A standalone SVG keeps every
    embedding rule but inheriting the page's ink, so it still sits on this page.
    """
    entries: list[Entry] = []
    for path in reference_documents():
        document = load_document(path)
        try:
            sheet = load_theme(document.theme or None).canvas.sheet
            entries.append(
                Entry(
                    name=path.stem,
                    kind=document.kind,
                    svg=render_document(document, profile="standalone" if sheet else profile),
                )
            )
        except FitError as error:
            # A refusal is an outcome, not a crash. The message is the product,
            # so it goes on the page where it can be judged.
            entries.append(Entry(name=path.stem, kind=document.kind, skipped=f"FitError: {error}"))
        except DrawspecError as error:
            entries.append(Entry(name=path.stem, kind=document.kind, skipped=str(error)))
    return entries


def kind_rank(kind: str) -> tuple[int, str]:
    """Sort key placing `kind` per KIND_ORDER, unlisted kinds last by name."""
    try:
        return (KIND_ORDER.index(kind), kind)
    except ValueError:
        return (len(KIND_ORDER), kind)


def by_kind(entries: Sequence[Entry]) -> list[tuple[str, list[Entry]]]:
    """Group entries by kind, the groups in KIND_ORDER, names sorted within."""
    groups: dict[str, list[Entry]] = {}
    for entry in sorted(entries, key=lambda e: (kind_rank(e.kind), e.name)):
        groups.setdefault(entry.kind, []).append(entry)
    return list(groups.items())


def page(entries: Sequence[Entry], profile: str) -> str:
    """One HTML page holding every diagram, for judging the set in one look.

    The diagrams are inlined rather than linked, which makes this the real test
    of the inline promise: if two of them collided on ids or leaked a style, it
    would show up here first.
    """
    groups = by_kind(entries)
    menu = " ".join(
        f'<a href="#{escape(kind)}">{escape(kind)} <span>{len(group)}</span></a>'
        for kind, group in groups
    )
    blocks: list[str] = []
    for kind, group in groups:
        figures = []
        for entry in group:
            body = (
                entry.svg if entry.rendered else f'<p class="skipped">{escape(entry.skipped)}</p>'
            )
            figures.append(
                f"<figure>\n<figcaption><b>{escape(entry.name)}</b></figcaption>\n{body}\n</figure>"
            )
        blocks.append(
            f'<section id="{escape(kind)}">\n<h2>{escape(kind)} '
            f'<a class="top" href="#menu">↑ kinds</a></h2>\n'
            + "\n".join(figures)
            + "\n</section>\n"
        )

    drawn = sum(entry.rendered for entry in entries)
    # Embedded, not linked: CI uploads the gallery directory on its own, where a
    # relative path to docs/logo.svg would not resolve.
    logo = "data:image/svg+xml;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    # A deliberately plain page: the diagrams inherit `color` from it, which is
    # what the inline profile is for, and anything more would be judging the
    # page rather than the drawings.
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>drawspec gallery — {escape(profile)}</title>
<link rel="icon" href="{logo}">
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; color: #1a1a1a; background: #fff;
         margin: 0 auto; max-width: 760px; padding: 2rem 1rem 6rem; }}
  figure {{ margin: 0 0 3rem; }}
  figcaption {{ font-size: 13px; margin-bottom: .5rem; color: #555; }}
  figcaption span {{ color: #888; }}
  svg {{ max-width: 100%; height: auto; }}
  .skipped {{ color: #777; font-style: italic; margin: 0; }}
  h1 {{ font-size: 18px; display: flex; align-items: center; gap: .5rem; }}
  h1 img {{ width: 32px; height: 32px; }}
  h2 {{ font-size: 16px; margin: 3rem 0 1rem; padding-top: .5rem; border-top: 1px solid #ddd; }}
  h2 .top {{ font-size: 12px; font-weight: normal; margin-left: .5rem; }}
  nav {{ display: flex; flex-wrap: wrap; gap: .35rem .5rem; margin: 1rem 0 2rem; }}
  nav a {{ font-size: 13px; padding: .15rem .5rem; border: 1px solid #ccc; border-radius: 1rem;
           text-decoration: none; color: inherit; }}
  nav a span, h1 span {{ color: #888; }}
  a {{ color: #2557a7; }}
</style>
<h1><img src="{logo}" alt="">drawspec gallery
<span>({escape(profile)} profile, {drawn} of {len(entries)} drawn)</span></h1>
<p>Every reference document through the current renderer, grouped by kind, the most
used kinds first. Look at it.</p>
<nav id="menu" aria-label="Kinds">{menu}</nav>
{"".join(blocks)}
</html>
"""


def report(entries: Sequence[Entry]) -> str:
    lines = [f"{'document':22} {'kind':10} outcome", f"{'-' * 22} {'-' * 10} {'-' * 40}"]
    for entry in entries:
        outcome = "drawn" if entry.rendered else entry.skipped.split("\n")[0][:60]
        lines.append(f"{entry.name:22} {entry.kind:10} {outcome}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument("--profile", default="inline", choices=PROFILES)
    args = parser.parse_args(argv)

    entries = build(args.profile)
    print(report(entries))

    if not args.check:
        GALLERY_DIR.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            if entry.rendered:
                (GALLERY_DIR / f"{entry.name}.svg").write_text(entry.svg, encoding="utf-8")
        PAGE.write_text(page(entries, args.profile), encoding="utf-8")
        print(f"\n{PAGE}")

    if not any(entry.rendered for entry in entries):
        print("nothing rendered at all", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
