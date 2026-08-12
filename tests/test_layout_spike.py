"""T7 — the layout-engine spike.

The gate is `candidate_engines_rendered == 2`: both candidates return valid
positions, with no overlapping boxes, for all three reference documents. This
file is what makes that a measurement rather than a claim.

The spike's *deliverable* is the decision recorded in `status/plan.md`, backed by
the SVGs in `docs/reference/rendered/`. What is asserted here is the evidence
that decision rests on: both engines work, both are deterministic, and the
numbers the comparison turns on are what the plan says they are.

The harness lives in `tools/spike_layout.py` — it is not shipped code, and
`pythonpath` in `pyproject.toml` is what puts it on the import path.
"""

from __future__ import annotations

import pytest
import spike_layout
from spike_layout import REFERENCES, engines, layout_inputs, measure

from drawspec.errors import LayoutError
from drawspec.layout import DIRECTIONS, LayeredEngine, LayoutEdge, LayoutEngine, LayoutNode
from drawspec.layout.grandalf_engine import GrandalfEngine, available
from drawspec.schema import load_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
CANDIDATES = ("layered", "grandalf")


def inputs(name: str) -> tuple[tuple[LayoutNode, ...], tuple[LayoutEdge, ...]]:
    document = load_document(spike_layout.REFERENCE_DIR / f"{name}.json")
    return layout_inputs(document, THEME, MEASURER)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_both_candidate_engines_are_available() -> None:
    """`candidate_engines_rendered == 2` needs two engines to exist."""
    assert available(), "grandalf is missing; run `uv sync --all-extras`"
    assert [engine.name for engine in engines(THEME)] == list(CANDIDATES)


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_spike_each_candidate_engine_lays_out_all_reference_documents(
    document: str, direction: str
) -> None:
    """Valid positions, no overlapping boxes, for both engines on all three."""
    nodes, edges = inputs(document)
    rendered = 0
    for engine in engines(THEME):
        result = engine.layout(nodes, edges, direction)
        assert set(result.placements) == {node.id for node in nodes}
        assert result.overlaps() == ()
        assert result.width > 0 and result.height > 0
        assert all(place.x >= 0 and place.y >= 0 for place in result.placements.values())
        rendered += 1
    assert rendered == 2


@pytest.mark.parametrize("document", REFERENCES)
def test_both_engines_are_deterministic(document: str) -> None:
    """The coordinates end up in committed SVG, so a rerun must not move them."""
    nodes, edges = inputs(document)
    for engine in engines(THEME):
        result, _ = measure(engine, document, nodes, edges)
        assert result.deterministic


@pytest.mark.parametrize("document", REFERENCES)
def test_neither_engine_introduces_a_crossing_at_corpus_scale(document: str) -> None:
    """The finding the decision rests on: ordering quality is not the tiebreak."""
    nodes, edges = inputs(document)
    for engine in engines(THEME):
        result, _ = measure(engine, document, nodes, edges)
        assert result.crossings == 0


def test_the_chosen_engine_is_never_looser_than_the_alternative() -> None:
    """The tiebreak that did decide it: slack, measured as laid-out area.

    grandalf reserves a full column for every dummy vertex on a long edge, which
    is what pushes a seven-node flow past the theme's canvas width. Being no
    looser is the property the default has to keep, whichever engine holds it.
    """
    for document in REFERENCES:
        nodes, edges = inputs(document)
        chosen, alternative = (
            measure(engine, document, nodes, edges)[0] for engine in engines(THEME)
        )
        assert chosen.area <= alternative.area + 1e-6, document


def test_the_spike_harness_runs_clean() -> None:
    """`--check` mode: every measurement taken, nothing written."""
    results = spike_layout.run(write=False)
    assert len(results) == len(REFERENCES) * len(CANDIDATES) * len(DIRECTIONS)
    assert all(item.overlaps == 0 for item in results)
    assert "Deterministic" in spike_layout.table(results)


@pytest.mark.parametrize("document", REFERENCES)
@pytest.mark.parametrize("engine", CANDIDATES)
def test_the_committed_pictures_exist_for_every_pairing(document: str, engine: str) -> None:
    """The deliverable is output to look at, so it is in the repository."""
    for direction in DIRECTIONS:
        path = spike_layout.RENDERED_DIR / f"{document}-{engine}-{direction}.svg"
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").startswith("<svg")


# --------------------------------------------------------------------------
# The protocol both engines implement
# --------------------------------------------------------------------------


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_satisfies_the_layout_engine_protocol(engine: LayoutEngine) -> None:
    assert isinstance(engine, LayoutEngine)


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_breaks_a_cycle_rather_than_looping_on_it(engine: LayoutEngine) -> None:
    """A cycle has to terminate, and the flipped edges have to be reported."""
    nodes = [LayoutNode(name, 100.0, 40.0) for name in ("a", "b", "c")]
    edges = [LayoutEdge("a", "b"), LayoutEdge("b", "c"), LayoutEdge("c", "a")]
    result = engine.layout(nodes, edges)
    assert result.overlaps() == ()
    assert len(result.reversed_edges) == 1


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_places_a_tree_child_after_its_parent(engine: LayoutEngine) -> None:
    nodes = [LayoutNode(name, 100.0, 40.0) for name in ("root", "child", "leaf")]
    edges = [LayoutEdge("root", "child"), LayoutEdge("child", "leaf")]
    result = engine.layout(nodes, edges)
    assert result.placements["root"].rank < result.placements["child"].rank
    assert result.placements["child"].rank < result.placements["leaf"].rank


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_handles_a_disconnected_graph(engine: LayoutEngine) -> None:
    """Two components is not an error — grandalf lays each out separately."""
    nodes = [LayoutNode(name, 100.0, 40.0) for name in ("a", "b", "c", "d")]
    edges = [LayoutEdge("a", "b"), LayoutEdge("c", "d")]
    result = engine.layout(nodes, edges)
    assert result.overlaps() == ()
    assert len(result.placements) == 4


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_places_a_single_node(engine: LayoutEngine) -> None:
    result = engine.layout([LayoutNode("only", 100.0, 40.0)], [])
    assert result.placements["only"].rank == 0
    assert (result.width, result.height) == (100.0, 40.0)


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_rejects_a_malformed_graph(engine: LayoutEngine) -> None:
    node = [LayoutNode("a", 100.0, 40.0)]
    with pytest.raises(LayoutError, match="not a node"):
        engine.layout(node, [LayoutEdge("a", "ghost")])
    with pytest.raises(LayoutError, match="direction"):
        engine.layout(node, [], "sideways")
    with pytest.raises(LayoutError, match="no nodes"):
        engine.layout([], [])
    with pytest.raises(LayoutError, match="duplicate"):
        engine.layout([*node, LayoutNode("a", 10.0, 10.0)], [])


@pytest.mark.parametrize("engine", [LayeredEngine(), GrandalfEngine()])
def test_each_engine_ignores_a_self_loop_for_ranking(engine: LayoutEngine) -> None:
    """A self-loop constrains nothing, so it must not become a cycle to break."""
    result = engine.layout([LayoutNode("a", 100.0, 40.0)], [LayoutEdge("a", "a")])
    assert result.placements["a"].rank == 0
    assert result.reversed_edges == frozenset()
