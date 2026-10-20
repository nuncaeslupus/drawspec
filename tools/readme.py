"""Render the README's example drawings to docs/readme, once per GitHub theme.

GitHub shows an SVG through an <img>, where ``currentColor`` is black whatever the
page is, so the inline-profile drawings vanish on its dark theme. The README uses a
<picture> with one PNG per background instead; this writes both.
"""

from __future__ import annotations

from pathlib import Path

from drawspec.cli import main as drawspec

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs" / "reference"
OUT = ROOT / "docs" / "readme"

# The README's examples, in the order it shows them.
EXAMPLES = [
    "flow-retry",
    "sequence-dns",
    "sequence-checkout",
    "entities-orders",
    "states-ticket",
    "gantt-migration",
    "mindmap-offsite",
    "sankey-budget",
    "venn-telemetry",
    "chart-bars",
    "fishbone-flaky-ci",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in EXAMPLES:
        for background in ("light", "dark"):
            code = drawspec(
                [
                    "render",
                    str(REFERENCE / f"{name}.json"),
                    "-o",
                    str(OUT / f"{name}-{background}.png"),
                    "--background",
                    background,
                ]
            )
            if code:
                return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
