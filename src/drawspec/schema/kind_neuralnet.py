"""The `neuralnet` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import get_close_matches
from typing import Any, Final

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import (
    CLASSES_MAX,
    NEURALNET_BRANCH_MAX,
    NEURALNET_LABEL_MAX,
    NEURALNET_NEURONS_SHOWN,
    NEURALNET_STYLES,
    NEURALNET_TOWER_MAX,
)
from drawspec.schema._model import Document, NeuralLayer, NeuralSpan, Violation

#: Why a neural network has no place for a field an author may reach for.
NEURALNET_REFUSED: Final = {
    "neurons": "a layer's neuron count is `size`",
    "units": "a layer's neuron count is `size`",
    "nodes": "a network's columns and boxes are its `layers`, in order",
    "edges": (
        "each layer is joined to the next in the order written; a connection that jumps "
        "over layers is a `skips` entry, in `blocks`"
    ),
    "connections": (
        "each layer is joined to the next in the order written; a connection that jumps "
        "over layers is a `skips` entry, in `blocks`"
    ),
    "residual": "a residual connection is a `skips` entry, from the block's input to its `add`",
    "activation": (
        "write the activation in the layer's `text` (`Dense 128, ReLU`), or in `blocks` as "
        "a layer of its own"
    ),
    "output": "a `blocks` layer's output tensor is `shape`",
    "dims": "a `blocks` layer's output tensor is `shape`",
    "label": "a layer's name is `text`; the names inside a layer's neurons are `labels`",
    "repeat": "a repeated block is a `repeats` entry: `from`, `to` and `times`",
    "times": "a repeated block is a `repeats` entry: `from`, `to` and `times`",
    "role": "a `blocks` layer's fill comes from its `type`, and the key names each type",
    "fill": "a `blocks` layer's fill comes from its `type`, and the key names each type",
    "colour": "a `blocks` layer's fill comes from its `type`, and the key names each type",
    "color": "a `blocks` layer's fill comes from its `type`, and the key names each type",
    "groups": "a frame round layers is a `repeats` entry, marked with how many times it stacks",
}


#: The fields only one style draws, and that style.
_NEURALNET_STYLE_FIELDS: Final = {
    "size": "neurons",
    "labels": "neurons",
    "bias": "neurons",
    "type": "blocks",
    "shape": "blocks",
    "skips": "blocks",
    "repeats": "blocks",
    "direction": "blocks",
    "branches": "blocks",
}


def _neuralnet_refusal(violation: Violation) -> Violation:
    """A structural refusal in a neural network, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in NEURALNET_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {NEURALNET_REFUSED[name]}.")
    return violation


def _neuralnet_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a neural network may not be: a field of the other style, a name that lands nowhere.

    `neurons`: at least two layers, each with a `size`; labels one per neuron, short,
    on a layer drawn whole; no bias on the last layer. `blocks`: every layer named;
    ids unique; a skip from an earlier layer to a later one past the next; repeats
    that never overlap, and no skip across a repeat's frame; at most four types.
    """
    found: list[Violation] = []
    style = document.get("style", "neurons")
    if style not in NEURALNET_STYLES:
        return found
    other = "blocks" if style == "neurons" else "neurons"

    def wrong_style(pointer: str, name: str) -> Violation:
        return Violation(
            pointer,
            f"{name!r} is drawn only in the `{other}` style, and this network is "
            f'`{style}`. Leave it out, or set `"style": "{other}"`.',
        )

    for name in ("skips", "repeats", "direction"):
        if name in document and _NEURALNET_STYLE_FIELDS[name] != style:
            found.append(wrong_style(f"/{name}", name))

    layers = list(_listed(document, "layers"))
    if style == "neurons" and len(layers) == 1:
        found.append(
            Violation(
                "/layers",
                "a network of neurons needs at least two layers — an input and an output — "
                "for the connections between them to be drawn.",
            )
        )
    ids: dict[str, int] = {}
    types: list[str] = []

    def typed(kind: object, pointer: str) -> None:
        if style != "blocks" or not isinstance(kind, str) or kind in types:
            return
        types.append(kind)
        if len(types) > CLASSES_MAX:
            found.append(
                Violation(
                    pointer,
                    f"{kind!r} is a {len(types)}th type, past the {CLASSES_MAX} fills a "
                    f"key tells apart. Merge types the reader need not tell apart "
                    f"(`norm` into `conv`), or leave `type` off the minor layers.",
                )
            )

    def branched(entry: Mapping[str, Any], here: str, index: int) -> None:
        """A set of branches: its place in the sequence, its towers, their layers."""
        for name in sorted(set(entry) - {"branches"}):
            found.append(
                Violation(
                    f"{here}/{name}",
                    f"{name!r}: a set of branches is drawn as its towers alone. Name what they "
                    f"compute in the layer after them, which joins them (`Filter concat`).",
                )
            )
        if index == 0 or index == len(layers) - 1:
            found.append(
                Violation(
                    f"{here}/branches",
                    "branches split from the layer before them and join at the layer after "
                    "them, so they are never first or last. Add the layer they split from or "
                    "the one that joins them (a `concat`).",
                )
            )
        elif isinstance(layers[index - 1], dict) and "branches" in layers[index - 1]:
            found.append(
                Violation(
                    f"{here}/branches",
                    "two sets of branches in a row would join in nothing: put the layer that "
                    "joins the first set (a `concat`, an `add`) between them.",
                )
            )
        towers = entry.get("branches")
        if not isinstance(towers, list):
            return
        if len(towers) > NEURALNET_BRANCH_MAX:
            found.append(
                Violation(
                    f"{here}/branches/{NEURALNET_BRANCH_MAX}",
                    f"{len(towers)} branches, past the {NEURALNET_BRANCH_MAX} an Inception "
                    f"module holds and a reader follows side by side. Draw the wider split "
                    f"as a `flow`.",
                )
            )
        for tower, branch in enumerate(towers):
            if not isinstance(branch, dict):
                continue
            inner = list(_listed(branch, "layers"))
            where = f"{here}/branches/{tower}"
            if len(inner) > NEURALNET_TOWER_MAX:
                found.append(
                    Violation(
                        f"{where}/layers/{NEURALNET_TOWER_MAX}",
                        f"a branch of {len(inner)} layers, past the {NEURALNET_TOWER_MAX} a "
                        f"tower holds beside the others. Fold its layers into fewer boxes "
                        f"(`1x1 conv, 3x3 conv`).",
                    )
                )
            # A tower layer's fields are its own object's (`text` and `type`), so
            # anything else is refused structurally, before this, at its pointer.
            for position, layer in enumerate(inner):
                if not isinstance(layer, dict):
                    continue
                spot = f"{where}/layers/{position}"
                text = layer.get("text")
                if isinstance(text, str) and not text.strip():
                    found.append(Violation(f"{spot}/text", "a layer's name needs words."))
                typed(layer.get("type"), f"{spot}/type")

    for index, entry in enumerate(layers):
        if not isinstance(entry, dict):
            continue
        here = _pointer("layers", index)
        if "branches" in entry:
            if style == "blocks":
                branched(entry, here, index)
            else:
                found.append(wrong_style(f"{here}/branches", "branches"))
            continue
        for name in ("size", "labels", "bias", "type", "shape"):
            if name in entry and _NEURALNET_STYLE_FIELDS[name] != style:
                found.append(wrong_style(f"{here}/{name}", name))
        identifier = entry.get("id")
        if isinstance(identifier, str):
            if not identifier.strip():
                found.append(
                    Violation(f"{here}/id", "an id needs a value — `conv1` — or leave it out.")
                )
            elif identifier in ids:
                found.append(
                    Violation(
                        f"{here}/id",
                        f"{identifier!r} is already the id of layer {ids[identifier]}: every "
                        f"layer needs its own, so a skip or a repeat names one box.",
                    )
                )
            else:
                ids[identifier] = index
        text = entry.get("text")
        if style == "blocks" and "text" not in entry:
            found.append(
                Violation(
                    f"{here}/text",
                    "a block says what the layer is — `Conv 3x3, 64`, `Max pool 2x2` — in `text`.",
                )
            )
        elif isinstance(text, str) and not text.strip():
            found.append(Violation(f"{here}/text", "a layer's name needs words, or leave it out."))
        if style == "neurons":
            size = entry.get("size")
            if "size" not in entry:
                found.append(
                    Violation(
                        f"{here}/size",
                        "a layer of neurons says how many it holds: `size` — `3`, `784`.",
                    )
                )
            labels = entry.get("labels")
            if isinstance(labels, list) and isinstance(size, int):
                if size > NEURALNET_NEURONS_SHOWN:
                    found.append(
                        Violation(
                            f"{here}/labels",
                            f"a layer of {size} is drawn as its first and last neurons with "
                            f"dots between, past the {NEURALNET_NEURONS_SHOWN} drawn whole, so "
                            f"its neurons cannot each be labelled. Say what they are in the "
                            f"layer's `text`: `Pixels (784)`.",
                        )
                    )
                elif len(labels) != size:
                    found.append(
                        Violation(
                            f"{here}/labels",
                            f"{len(labels)} labels for {size} neurons: give one per neuron, top "
                            f"to bottom, or leave `labels` out.",
                        )
                    )
                for position, label in enumerate(labels):
                    if isinstance(label, str) and (
                        "\n" in label or len(label) > NEURALNET_LABEL_MAX
                    ):
                        found.append(
                            Violation(
                                f"{here}/labels/{position}",
                                f"{label!r} does not fit in a neuron: one line of at most "
                                f"{NEURALNET_LABEL_MAX} characters — `x₁`, `h₂`, `ŷ`. Say what "
                                f"the neurons mean in the layer's `text` or the caption.",
                            )
                        )
            if entry.get("bias") is True and index == len(layers) - 1:
                found.append(
                    Violation(
                        f"{here}/bias",
                        "the last layer feeds no layer, so it has no bias unit to draw. A "
                        "bias belongs to the layer it is drawn beside, feeding the next.",
                    )
                )
        typed(entry.get("type"), f"{here}/type")

    if style != "blocks":
        return found

    def resolve(value: object, here: str) -> int | None:
        if not isinstance(value, str):
            return None
        if value in ids:
            return ids[value]
        close = get_close_matches(value, list(ids), n=1)
        hint = f" Did you mean {close[0]!r}?" if close else ""
        found.append(Violation(here, f"{value!r} names no layer's `id`.{hint}"))
        return None

    spans: list[tuple[int, int]] = []
    for index, entry in enumerate(_listed(document, "repeats")):
        if not isinstance(entry, dict):
            continue
        here = _pointer("repeats", index)
        first = resolve(entry.get("from"), f"{here}/from")
        last = resolve(entry.get("to"), f"{here}/to")
        if first is None or last is None:
            continue
        if last < first:
            found.append(
                Violation(
                    f"{here}/to",
                    "a repeated block runs from its first layer to its last, in the order "
                    "written: this `to` comes before its `from`.",
                )
            )
            continue
        clash = next((span for span in spans if span[0] <= last and first <= span[1]), None)
        if clash is not None:
            found.append(
                Violation(
                    here,
                    "two repeated blocks share a layer: each layer is in one frame at most. "
                    "Merge them, or end one before the other starts.",
                )
            )
            continue
        spans.append((first, last))

    seen: set[tuple[int, int]] = set()
    for index, entry in enumerate(_listed(document, "skips")):
        if not isinstance(entry, dict):
            continue
        here = _pointer("skips", index)
        first = resolve(entry.get("from"), f"{here}/from")
        last = resolve(entry.get("to"), f"{here}/to")
        if first is None or last is None:
            continue
        if last <= first:
            found.append(
                Violation(
                    f"{here}/to",
                    "a skip carries a layer's output forward, to a later layer: this `to` is "
                    "not after its `from`. A network that feeds back is recurrent — draw it "
                    "unrolled, or as a `flow`.",
                )
            )
        elif last == first + 1:
            found.append(
                Violation(
                    f"{here}/to",
                    "these two layers are next to each other, and joined already by the "
                    "sequence. A skip jumps over at least one layer.",
                )
            )
        elif (first, last) in seen:
            found.append(Violation(here, "this skip is written already: write each once."))
        else:
            seen.add((first, last))
            across = next(
                (
                    span
                    for span in spans
                    if first + 1 <= span[1]
                    and span[0] <= last
                    and not (span[0] <= first + 1 and last <= span[1])
                    and not (first + 1 <= span[0] and span[1] <= last)
                ),
                None,
            )
            if across is not None:
                found.append(
                    Violation(
                        here,
                        "this skip runs across a repeated block's frame: it branches off the "
                        "arrow leaving its `from` on one side of the frame and lands on the "
                        "other. Keep it inside the block (from the layer before the block's "
                        "first, at the earliest), or round the whole of it.",
                    )
                )
    return found


def _neural_layer(entry: Mapping[str, Any]) -> NeuralLayer:
    """One layer, or a set of branches with its towers' layers, from the validated mapping."""
    return NeuralLayer(
        id=str(entry.get("id", "")),
        text=str(entry.get("text", "")),
        size=int(entry.get("size", 0)),
        labels=tuple(str(label) for label in entry.get("labels", ())),
        bias=entry.get("bias") is True,
        type=str(entry.get("type", "")),
        shape=str(entry.get("shape", "")),
        branches=tuple(
            tuple(_neural_layer(layer) for layer in branch["layers"])
            for branch in entry.get("branches", ())
        ),
    )


def _neuralnet_document(document: Mapping[str, Any]) -> Document:
    """A neural network: its layers in order, and a `blocks` network's spans."""

    def span(entry: Mapping[str, Any]) -> NeuralSpan:
        return NeuralSpan(
            source=str(entry["from"]),
            target=str(entry["to"]),
            text=str(entry.get("text", "")),
            times=int(entry.get("times", 0)),
        )

    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        neural_style=str(document.get("style", "neurons")),
        neural_layers=tuple(_neural_layer(entry) for entry in document["layers"]),
        neural_skips=tuple(span(entry) for entry in document.get("skips", ())),
        neural_repeats=tuple(span(entry) for entry in document.get("repeats", ())),
        neural_direction=str(document.get("direction", "")),
    )
