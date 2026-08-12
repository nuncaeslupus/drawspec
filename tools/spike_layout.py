"""T7's spike harness: run both candidate engines and look at the result.

Not shipped code. This exists to settle the layout-engine question with rendered
output rather than argument, which is what the plan asks T7 for, and to give the
spike test something to assert against.

What it deliberately is *not*: the graph renderer. Edges here are straight lines
between box centres, because orthogonal routing is T9 and border anchoring is
T9's job too. What is being compared is where the boxes went — everything else in
these pictures is scaffolding.

Usage, from the repository root:

    uv run python tools/spike_layout.py            # write the SVGs and the table
    uv run python tools/spike_layout.py --check    # table only, write nothing
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from drawspec.emit import emit
from drawspec.geometry import normalise, size_box
from drawspec.kinds.common import box_primitives
from drawspec.layout.base import Layout, LayoutEdge, LayoutEngine, LayoutNode, Spacing
from drawspec.layout.grandalf_engine import GrandalfEngine
from drawspec.layout.layered import LayeredEngine
from drawspec.scene import Path as ScenePath
from drawspec.scene import Primitive, Scene
from drawspec.schema import Document, load_document
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "reference"
RENDERED_DIR = REFERENCE_DIR / "rendered"

#: The three reference documents, in the order the spike reports them.
#:
#: The brief's second acceptance test names three corpus fixtures; one of them
#: (`fixture-067`) is a chart, which no layout engine touches, so it has nothing
#: to say about this decision. These three were chosen instead — a flow with two
#: decisions and a back edge, a cycle, and a tree. T18 takes the brief's three
#: end to end.
#:
#: `cycle-review` is here as a **cycle-breaking** test, which every engine needs
#: to survive, and it is a fair one. Its *render* is not how a `cycle` document
#: will be drawn: D-1 moved that kind to a parametric radial template, because a
#: cycle through a layered engine comes out as a column of boxes with one line
#: down through it. Do not read `cycle-review-*.svg` as a preview of the cycle
#: kind — read it as two engines agreeing about how to break a loop.
REFERENCES = ("flow-validation", "cycle-review", "tree-decisions")

#: How wide a node box may be. A node the full canvas width leaves no room for
#: anything beside it, so a graph's boxes get a share of it.
NODE_WIDTH_SHARE = 0.42


@dataclass(frozen=True)
class Measured:
    """One engine's result on one document, with the numbers worth comparing."""

    engine: str
    document: str
    direction: str
    overlaps: int
    crossings: int
    width: float
    height: float
    deterministic: bool

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0


def engines(theme: Theme) -> tuple[LayoutEngine, ...]:
    """Both candidates, spaced from the theme.

    `rank_gap` is floored at the theme's minimum shaft length plus its head
    length: a rank gap smaller than that would produce an arrow with no visible
    shaft, which is the corpus's most common single failure and a layout
    constraint rather than a drawing one.
    """
    spacing = Spacing(
        node_gap=theme.box.padding.horizontal,
        rank_gap=max(theme.edge.min_shaft_length + theme.edge.head_length, 24.0),
    )
    return (LayeredEngine(spacing=spacing), GrandalfEngine(spacing=spacing))


def layout_inputs(
    document: Document, theme: Theme, measurer: TextMeasurer
) -> tuple[tuple[LayoutNode, ...], tuple[LayoutEdge, ...]]:
    """Size every node's box, normalise peers, and hand the sizes to an engine.

    Peers here are nodes sharing a role, which is the best available stand-in for
    "the same kind of thing" before ranks exist — the layout has not run yet, so
    rank-based normalisation is not available to it.
    """
    limit = theme.canvas.width * NODE_WIDTH_SHARE
    boxes = {
        node.id: size_box(
            node.text,
            theme=theme,
            measurer=measurer,
            role=node.role,
            level="body",
            max_width=limit,
        )
        for node in document.nodes
    }

    by_role: dict[str, list[str]] = {}
    for node in document.nodes:
        by_role.setdefault(node.role, []).append(node.id)
    for identifiers in by_role.values():
        for identifier, box in zip(
            identifiers, normalise([boxes[i] for i in identifiers]), strict=True
        ):
            boxes[identifier] = box

    nodes = tuple(
        LayoutNode(id=node.id, width=boxes[node.id].width, height=boxes[node.id].height)
        for node in document.nodes
    )
    edges = tuple(LayoutEdge(source=edge.source, target=edge.target) for edge in document.edges)
    return nodes, edges


def measure(
    engine: LayoutEngine,
    name: str,
    nodes: Sequence[LayoutNode],
    edges: Sequence[LayoutEdge],
    direction: str = "down",
) -> tuple[Measured, Layout]:
    """Run `engine` twice and report what the comparison turns on."""
    first = engine.layout(nodes, edges, direction)
    second = engine.layout(nodes, edges, direction)
    return (
        Measured(
            engine=engine.name,
            document=name,
            direction=direction,
            overlaps=len(first.overlaps()),
            crossings=first.crossings(edges),
            width=first.width,
            height=first.height,
            deterministic=first.placements == second.placements,
        ),
        first,
    )


def to_scene(document: Document, layout: Layout, theme: Theme, measurer: TextMeasurer) -> Scene:
    """A rough Scene for looking at: boxes where they landed, straight edges.

    Boxes are drawn through `kinds.common.box_primitives`, the same path the real
    families use, so a `decision` comes out as the diamond its role declares and
    its text is centred. An earlier version of this harness built the primitives
    itself and drew every node as a rectangle — which made a diamond-sized box
    look like an enormous rectangle with the label adrift in it, and was the whole
    of what looked wrong about these pictures.

    Straight centre-to-centre edges *are* still wrong on purpose — routing is T9,
    so an edge here starts inside its source box and ends inside its target. What
    these pictures are for is judging where the boxes went.
    """
    margin = theme.box.padding.horizontal
    primitives: list[Primitive] = []

    for edge in document.edges:
        source = layout.placements[edge.source]
        target = layout.placements[edge.target]
        primitives.append(
            ScenePath(
                edge.role,
                points=(
                    (source.centre[0] + margin, source.centre[1] + margin),
                    (target.centre[0] + margin, target.centre[1] + margin),
                ),
            )
        )

    for node in document.nodes:
        place = layout.placements[node.id]
        box = (
            size_box(
                node.text,
                theme=theme,
                measurer=measurer,
                role=node.role,
                level="body",
                max_width=theme.canvas.width * NODE_WIDTH_SHARE,
            )
            .resized(width=place.width, height=place.height)
            .moved_to(place.x + margin, place.y + margin)
        )
        primitives.extend(box_primitives(box, theme, measurer))

    return Scene(
        width=layout.width + margin * 2,
        height=layout.height + margin * 2,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
    )


def run(*, write: bool) -> list[Measured]:
    """Both engines over all three references. Returns every measurement."""
    theme = load_theme()
    measurer = TextMeasurer(theme.font.stacks(), search_paths=[])
    results: list[Measured] = []

    if write:
        RENDERED_DIR.mkdir(parents=True, exist_ok=True)

    for name in REFERENCES:
        document = load_document(REFERENCE_DIR / f"{name}.json")
        nodes, edges = layout_inputs(document, theme, measurer)
        for engine in engines(theme):
            # Both directions, because "if the arrows do not fit horizontally the
            # diagram goes vertical" is a real remedy, and whether an engine makes
            # it available is part of what is being decided.
            for direction in ("down", "right"):
                measured, layout = measure(engine, name, nodes, edges, direction)
                results.append(measured)
                if write:
                    svg = emit(to_scene(document, layout, theme, measurer), theme, "standalone")
                    (RENDERED_DIR / f"{name}-{engine.name}-{direction}.svg").write_text(
                        svg, encoding="utf-8"
                    )
    return results


def table(results: Sequence[Measured]) -> str:
    """The comparison, as the markdown table the plan records."""
    header = (
        "| Document | Engine | Direction | Overlaps | Crossings "
        "| Size | Fits 640 | Deterministic |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    rows = "".join(
        f"| {item.document} | {item.engine} | {item.direction} | {item.overlaps} | "
        f"{item.crossings} | {item.width:.0f} x {item.height:.0f} | "
        f"{'yes' if item.width <= 640 else 'no'} | "
        f"{'yes' if item.deterministic else 'NO'} |\n"
        for item in results
    )
    return header + rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="do not write the SVGs")
    args = parser.parse_args(argv)

    results = run(write=not args.check)
    print(table(results))
    if any(item.overlaps for item in results):
        print("a candidate produced overlapping boxes", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
