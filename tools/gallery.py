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
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from drawspec.emit import PROFILES
from drawspec.errors import DrawspecError, FitError
from drawspec.render import render_document
from drawspec.schema import load_document

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "docs" / "reference"
GALLERY_DIR = ROOT / "docs" / "gallery"
PAGE = GALLERY_DIR / "index.html"


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
    """Render every reference document, recording why any did not draw."""
    entries: list[Entry] = []
    for path in reference_documents():
        document = load_document(path)
        try:
            entries.append(
                Entry(
                    name=path.stem,
                    kind=document.kind,
                    svg=render_document(document, profile=profile),
                )
            )
        except FitError as error:
            # A refusal is an outcome, not a crash. The message is the product,
            # so it goes on the page where it can be judged.
            entries.append(Entry(name=path.stem, kind=document.kind, skipped=f"FitError: {error}"))
        except DrawspecError as error:
            entries.append(Entry(name=path.stem, kind=document.kind, skipped=str(error)))
    return entries


def page(entries: Sequence[Entry], profile: str) -> str:
    """One HTML page holding every diagram, for judging the set in one look.

    The diagrams are inlined rather than linked, which makes this the real test
    of the inline promise: if two of them collided on ids or leaked a style, it
    would show up here first.
    """
    blocks: list[str] = []
    for entry in entries:
        body = entry.svg if entry.rendered else f'<p class="skipped">{escape(entry.skipped)}</p>'
        blocks.append(
            f"<figure>\n<figcaption><b>{escape(entry.name)}</b> "
            f"<span>{escape(entry.kind)}</span></figcaption>\n{body}\n</figure>"
        )

    drawn = sum(entry.rendered for entry in entries)
    # A deliberately plain page: the diagrams inherit `color` from it, which is
    # what the inline profile is for, and anything more would be judging the
    # page rather than the drawings.
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>drawspec gallery — {escape(profile)}</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; color: #1a1a1a; background: #fff;
         margin: 0 auto; max-width: 760px; padding: 2rem 1rem 6rem; }}
  figure {{ margin: 0 0 3rem; }}
  figcaption {{ font-size: 13px; margin-bottom: .5rem; color: #555; }}
  figcaption span {{ color: #888; }}
  svg {{ max-width: 100%; height: auto; }}
  .skipped {{ color: #777; font-style: italic; margin: 0; }}
  h1 {{ font-size: 18px; }}
</style>
<h1>drawspec gallery <span>({escape(profile)} profile, {drawn} of {len(entries)} drawn)</span></h1>
<p>Every reference document through the current renderer. Look at it.</p>
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
