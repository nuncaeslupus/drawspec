"""`neuralnet` — a neural network's layers, as textbooks and papers draw them.

The kind's promises. In `neurons`: each layer a column of circles, centred on one
another; every drawn neuron joined to every drawn neuron of the next layer, and a
bias unit fed by nothing; a layer past the shown limit drawn as its first and last
neurons with dots between and its size under its name. In `blocks`: a box per
layer in sequence, an arrow from each to the next, its shape beside it, a fill per
type with a key; a skip branching off the arrow after its `from` and landing on
the layer it feeds, clear of every box; a repeated block framed and marked `xN`,
its inner skips inside the frame. No stroke through a word. The text form is a
model summary with the parameters computed. Everything an author can get wrong is
refused at its pointer, with the reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from clipping import clipped
from collisions import collisions

from drawspec import render, render_text
from drawspec.examples import EXAMPLES
from drawspec.kinds.neuralnet import (
    BIAS,
    neuralnet_scene,
    neurons_drawing,
    parameters,
    shown,
)
from drawspec.scene import Path as Stroke
from drawspec.scene import Rect, TextRun
from drawspec.schema import (
    NEURALNET_LAYER_MAX,
    NEURALNET_NEURONS_SHOWN,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("neuralnet-*.json"))


def network(*sizes: int, **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "neuralnet",
        "layers": [{"text": f"L{index}", "size": size} for index, size in enumerate(sizes)],
    }
    document.update(extra)
    return document


def blocks(*names: str, **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "neuralnet",
        "style": "blocks",
        "layers": [{"id": name, "text": name.title()} for name in names],
    }
    document.update(extra)
    return document


def reference(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    return data


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


# -- the references -----------------------------------------------------------


def test_there_are_references_of_both_styles() -> None:
    styles = {reference(path.stem).get("style", "neurons") for path in REFERENCES}
    assert styles == {"neurons", "blocks"}


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_validates_and_is_clean(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    svg = render(document, profile="standalone")
    assert svg.startswith("<svg")
    assert collisions(svg) == []
    assert clipped(svg) == []


def test_the_example_renders() -> None:
    assert validate_document(EXAMPLES["neuralnet"]) == ()
    assert render(EXAMPLES["neuralnet"]).startswith("<svg")


# -- neurons ------------------------------------------------------------------


def test_every_neuron_is_joined_to_every_neuron_of_the_next_layer() -> None:
    neurons, links, _, _, _ = neurons_drawing(parse_document(network(3, 4, 2)), THEME, MEASURER)
    assert len(neurons) == 9
    assert len(links) == 3 * 4 + 4 * 2


def test_a_bias_unit_feeds_the_next_layer_and_is_fed_by_nothing() -> None:
    document = network(2, 3, 1)
    document["layers"][1]["bias"] = True
    neurons, links, _, _, _ = neurons_drawing(parse_document(document), THEME, MEASURER)
    bias = [neuron for neuron in neurons if neuron.index < 0]
    assert [neuron.label for neuron in bias] == [BIAS]
    # 2 x 3 into the hidden layer (not its bias), then (3 + bias) x 1 out.
    assert len(links) == 2 * 3 + 4 * 1


def test_the_columns_are_centred_on_one_another() -> None:
    neurons, _, _, _, _ = neurons_drawing(parse_document(network(2, 5, 1)), THEME, MEASURER)
    middles = {}
    for layer in range(3):
        ys = [neuron.cy for neuron in neurons if neuron.layer == layer]
        middles[layer] = (min(ys) + max(ys)) / 2
    assert middles[0] == pytest.approx(middles[1]) == pytest.approx(middles[2])


def test_a_large_layer_is_drawn_as_its_ends_with_dots_and_its_size() -> None:
    assert shown(NEURALNET_NEURONS_SHOWN) == tuple(range(NEURALNET_NEURONS_SHOWN))
    assert shown(784) == (0, 1, 2, None, 782, 783)
    document = parse_document(network(784, 3))
    neurons, links, marks, _, _ = neurons_drawing(document, THEME, MEASURER)
    assert len([neuron for neuron in neurons if neuron.layer == 0]) == 5
    assert len(links) == 5 * 3
    words = [mark.text for mark in marks if isinstance(mark, TextRun)]
    assert "784 neurons" in words


def test_an_arrow_comes_into_each_input_and_leaves_each_output() -> None:
    document = network(3, 4, 2)
    document["layers"][0]["bias"] = True
    _, _, marks, _, _ = neurons_drawing(parse_document(document), THEME, MEASURER)
    arrows = [mark for mark in marks if isinstance(mark, Stroke) and mark.role == "flow"]
    assert len(arrows) == 3 + 2  # the bias unit takes no input


def test_lines_end_on_the_circles() -> None:
    neurons, links, _, _, _ = neurons_drawing(parse_document(network(2, 2)), THEME, MEASURER)
    radius = neurons[0].r
    for start, end in links:
        assert (
            min(
                abs(((start[0] - n.cx) ** 2 + (start[1] - n.cy) ** 2) ** 0.5 - radius)
                for n in neurons
            )
            < 0.01
        )
        assert (
            min(abs(((end[0] - n.cx) ** 2 + (end[1] - n.cy) ** 2) ** 0.5 - radius) for n in neurons)
            < 0.01
        )


def test_labels_are_drawn_in_their_neurons() -> None:
    svg = render(reference("neuralnet-two-hidden"))
    for label in ("x₁", "x₂", "x₃", "ŷ₁", "+1"):
        assert label in svg


# -- blocks -------------------------------------------------------------------


def _scene(document: dict[str, Any]) -> Any:
    return neuralnet_scene(parse_document(document), THEME, MEASURER)


def test_a_short_network_runs_across_and_a_vertical_one_down() -> None:
    assert ("direction", "right") in _scene(blocks("a", "b", "c")).metadata
    assert ("direction", "down") in _scene(blocks("a", "b", "c", direction="down")).metadata
    assert ("direction", "up") in _scene(blocks("a", "b", "c", direction="up")).metadata


def test_up_puts_the_first_layer_at_the_bottom() -> None:
    scene = _scene(blocks("first", "last", direction="up"))
    lines = {line.spans[0].text: line.y for line in scene.primitives if hasattr(line, "spans")}
    assert lines["First"] > lines["Last"]


def test_a_long_network_that_cannot_run_across_runs_down() -> None:
    document = blocks(*(f"layer number {index}" for index in range(12)))
    assert ("direction", "down") in _scene(document).metadata


def test_each_block_is_joined_to_the_next() -> None:
    scene = _scene(blocks("a", "b", "c", "d"))
    shafts = [p for p in scene.primitives if isinstance(p, Stroke) and len(p.points) == 2]
    assert len(shafts) >= 3


def test_a_skip_branches_off_the_arrow_and_lands_on_its_layer() -> None:
    document = blocks("x", "f", "g", "add", skips=[{"from": "x", "to": "add", "text": "identity"}])
    scene = _scene(document)
    skip = next(p for p in scene.primitives if isinstance(p, Stroke) and len(p.points) == 4)
    rects = [p for p in scene.primitives if isinstance(p, Rect)]
    start, *_, end = skip.points
    xs = sorted({rect.x for rect in rects})
    # It leaves between the first two boxes, on the arrow's line, and lands on the last.
    assert xs[0] < start[0] < xs[1]
    assert end[0] > xs[-1]
    assert "identity" in render(document)


def test_a_repeat_is_framed_and_marked() -> None:
    document = blocks("a", "b", "c", repeats=[{"from": "b", "to": "c", "times": 6}])
    svg = render(document)
    assert "\N{MULTIPLICATION SIGN}6" in svg
    scene = _scene(document)
    assert any(p.role == "group" for p in scene.primitives if isinstance(p, Rect))


def test_a_skip_inside_a_repeat_stays_inside_its_frame() -> None:
    document = reference("neuralnet-transformer-encoder")
    scene = _scene(document)
    frame = next(p for p in scene.primitives if isinstance(p, Rect) and p.role == "group")
    skips = [p for p in scene.primitives if isinstance(p, Stroke) and len(p.points) == 4]
    assert len(skips) == 2
    for skip in skips:
        for x, y in skip.points:
            assert frame.x <= x <= frame.x + frame.width
            assert frame.y <= y <= frame.y + frame.height


def test_types_take_fills_and_a_key_names_them() -> None:
    svg = render(reference("neuralnet-lenet"))
    for name in ("convolution", "subsampling", "full"):
        assert name in svg


def test_one_type_needs_no_key() -> None:
    document = blocks("a", "b")
    for layer in document["layers"]:
        layer["type"] = "dense"
    assert "dense" not in render(document)


# -- the text form ------------------------------------------------------------


def test_the_parameters_are_weights_and_biases() -> None:
    layers = parse_document(network(784, 30, 10)).neural_layers
    assert parameters(layers) == [0, 784 * 30 + 30, 30 * 10 + 10]
    text = render_text(parse_document(network(784, 30, 10)))
    assert "23,860 parameters" in text


def test_the_blocks_summary_lists_layers_skips_and_repeats() -> None:
    text = render_text(parse_document(reference("neuralnet-transformer-encoder")))
    lines = text.splitlines()
    assert lines[0].split() == ["#", "Layer", "Type", "Output", "shape"]
    assert "skip: 2 → 4" in text
    assert "\N{MULTIPLICATION SIGN}6: layers 3-6" in text
    ascii_text = render_text(
        parse_document(reference("neuralnet-transformer-encoder")), charset="ascii"
    )
    assert "skip: 2 -> 4" in ascii_text
    assert "x6: layers 3-6" in ascii_text


# -- refusals -----------------------------------------------------------------


def test_a_neurons_layer_needs_a_size() -> None:
    document = network(3, 2)
    del document["layers"][1]["size"]
    assert pointers(document) == ["/layers/1/size"]


def test_a_neurons_network_needs_two_layers() -> None:
    assert pointers(network(3)) == ["/layers"]


def test_a_field_of_the_other_style_is_refused_at_its_pointer() -> None:
    document = network(3, 2)
    document["layers"][0]["shape"] = "3"
    document["skips"] = []
    assert sorted(pointers(document)) == ["/layers/0/shape", "/skips"]
    assert "`blocks` style" in messages(document)
    other = blocks("a", "b")
    other["layers"][0]["size"] = 3
    assert pointers(other) == ["/layers/0/size"]


def test_labels_are_one_per_neuron_short_and_only_on_a_whole_layer() -> None:
    document = network(2, 1)
    document["layers"][0]["labels"] = ["x₁"]
    assert pointers(document) == ["/layers/0/labels"]
    document["layers"][0]["labels"] = ["x₁", "a long name"]
    assert pointers(document) == ["/layers/0/labels/1"]
    wide = network(NEURALNET_NEURONS_SHOWN + 1, 1)
    wide["layers"][0]["labels"] = ["x"] * (NEURALNET_NEURONS_SHOWN + 1)
    assert pointers(wide) == ["/layers/0/labels"]


def test_the_last_layer_has_no_bias() -> None:
    document = network(2, 1)
    document["layers"][1]["bias"] = True
    assert pointers(document) == ["/layers/1/bias"]


def test_a_block_needs_its_name() -> None:
    document = blocks("a", "b")
    del document["layers"][1]["text"]
    assert pointers(document) == ["/layers/1/text"]


def test_ids_are_unique_and_names_land_with_a_suggestion() -> None:
    document = blocks("conv", "pool", "dense", skips=[{"from": "conv", "to": "dence"}])
    assert pointers(document) == ["/skips/0/to"]
    assert "Did you mean 'dense'?" in messages(document)
    clash = blocks("a", "b")
    clash["layers"][1]["id"] = "a"
    assert pointers(clash) == ["/layers/1/id"]


def test_a_skip_runs_forward_past_the_next_layer() -> None:
    assert pointers(blocks("a", "b", "c", skips=[{"from": "c", "to": "a"}])) == ["/skips/0/to"]
    assert pointers(blocks("a", "b", "c", skips=[{"from": "a", "to": "b"}])) == ["/skips/0/to"]
    twice = blocks("a", "b", "c", skips=[{"from": "a", "to": "c"}, {"from": "a", "to": "c"}])
    assert pointers(twice) == ["/skips/1"]


def test_repeats_never_overlap_and_no_skip_crosses_a_frame() -> None:
    overlap = blocks(
        "a",
        "b",
        "c",
        "d",
        repeats=[{"from": "a", "to": "c", "times": 2}, {"from": "b", "to": "d", "times": 2}],
    )
    assert pointers(overlap) == ["/repeats/1"]
    across = blocks(
        "a",
        "b",
        "c",
        "d",
        repeats=[{"from": "b", "to": "c", "times": 2}],
        skips=[{"from": "b", "to": "d"}],
    )
    assert pointers(across) == ["/skips/0"]
    inside = blocks(
        "a",
        "b",
        "c",
        "d",
        repeats=[{"from": "b", "to": "d", "times": 2}],
        skips=[{"from": "a", "to": "c"}],
    )
    assert pointers(inside) == []


def test_a_skip_round_a_whole_repeat_is_drawn_outside_its_frame() -> None:
    document = blocks(
        "a",
        "b",
        "c",
        "d",
        "e",
        repeats=[{"from": "b", "to": "d", "times": 2}],
        skips=[{"from": "a", "to": "e"}],
    )
    assert pointers(document) == []
    svg = render(document, profile="standalone")
    assert collisions(svg) == []
    assert clipped(svg) == []
    scene = _scene(document)
    frame = next(p for p in scene.primitives if isinstance(p, Rect) and p.role == "group")
    skip = next(p for p in scene.primitives if isinstance(p, Stroke) and len(p.points) == 4)
    assert skip.points[0][0] < frame.x
    assert min(y for _, y in skip.points) < frame.y


def test_at_most_four_types() -> None:
    document = blocks("a", "b", "c", "d", "e")
    for index, layer in enumerate(document["layers"]):
        layer["type"] = f"t{index}"
    assert pointers(document) == ["/layers/4/type"]


@pytest.mark.parametrize(
    ("field", "words"),
    [("neurons", "`size`"), ("residual", "`skips`"), ("activation", "`text`"), ("color", "`type`")],
)
def test_a_field_an_author_reaches_for_is_refused_with_the_reason(field: str, words: str) -> None:
    document = network(2, 1)
    document["layers"][0][field] = 1
    assert pointers(document) == [f"/layers/0/{field}"]
    assert words in messages(document)


def test_the_budget() -> None:
    document = blocks(*(f"l{index}" for index in range(NEURALNET_LAYER_MAX + 1)))
    assert pointers(document) == [f"/layers/{NEURALNET_LAYER_MAX}"]


# -- branches -------------------------------------------------------------------


def inception(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "neuralnet",
        "style": "blocks",
        "layers": [
            {"id": "in", "text": "Input"},
            {
                "branches": [
                    {"layers": [{"text": "first"}]},
                    {"layers": [{"text": "1x1"}, {"text": "3x3"}]},
                ]
            },
            {"id": "cat", "text": "Concat"},
        ],
    }
    document.update(extra)
    return document


@pytest.mark.parametrize("direction", ["right", "down", "up"])
def test_branches_render_clean_each_way(direction: str) -> None:
    document = inception(direction=direction)
    assert validate_document(document) == ()
    svg = render(document, profile="standalone")
    assert collisions(svg) == []
    assert clipped(svg) == []


def test_every_tower_is_fed_by_the_layer_before_and_feeds_the_layer_after() -> None:
    scene = _scene(inception())
    strokes = [p for p in scene.primitives if isinstance(p, Stroke)]
    # Two fan-out lines, two joining lines, and one arrow inside the longer tower.
    assert len(strokes) == 5


def test_running_down_the_first_branch_is_on_the_left() -> None:
    scene = _scene(inception(direction="down"))
    lines = {line.spans[0].text: line.x for line in scene.primitives if hasattr(line, "spans")}
    assert lines["first"] < lines["1x1"]


def test_a_skip_may_go_round_a_set_of_branches() -> None:
    document = inception(skips=[{"from": "in", "to": "cat"}])
    document["layers"].append({"text": "After"})
    document["skips"] = [{"from": "in", "to": "cat"}]
    assert validate_document(document) == ()
    assert collisions(render(document, profile="standalone")) == []


def test_branches_are_numbered_in_the_text_form() -> None:
    text = render_text(parse_document(inception()))
    marks = [line.split()[0] for line in text.splitlines()[2:] if line.strip()]
    assert marks == ["1", "2a", "2b1", "2b2", "3"]


def test_branches_are_never_first_last_or_twice_in_a_row() -> None:
    document = inception()
    document["layers"] = document["layers"][1:]
    assert pointers(document) == ["/layers/0/branches"]
    twice = inception()
    twice["layers"].insert(2, twice["layers"][1])
    assert pointers(twice) == ["/layers/2/branches"]


def test_a_set_of_branches_holds_branches_alone() -> None:
    document = inception()
    document["layers"][1]["text"] = "Inception"
    assert pointers(document) == ["/layers/1/text"]
    assert "joins them" in messages(document)


def test_a_tower_layer_has_a_text_and_a_type_only() -> None:
    document = inception()
    tower = document["layers"][1]["branches"][1]["layers"]
    tower[0]["id"] = "inner"
    tower[1]["shape"] = "3"
    assert sorted(pointers(document)) == [
        "/layers/1/branches/1/layers/0/id",
        "/layers/1/branches/1/layers/1/shape",
    ]


def test_branch_and_tower_limits() -> None:
    document = inception()
    document["layers"][1]["branches"] = [{"layers": [{"text": f"t{n}"}]} for n in range(5)]
    assert pointers(document) == ["/layers/1/branches/4"]
    tall = inception()
    tall["layers"][1]["branches"][0]["layers"] = [{"text": f"l{n}"} for n in range(4)]
    assert pointers(tall) == ["/layers/1/branches/0/layers/3"]


def test_branches_are_refused_in_neurons() -> None:
    document = network(2, 1)
    document["layers"][0]["branches"] = [{"layers": [{"text": "a"}]}, {"layers": [{"text": "b"}]}]
    assert pointers(document) == ["/layers/0/branches"]
