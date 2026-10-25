---
id: t-9dddc873
title: "Add the neuralnet kind (neuron diagrams and layer-block architectures)"
priority: 1
status: merged
tags: [kinds]
---

Owner request: neural-network drawings. There are many notations, so the kind covers
the two that most figures use, as styles of one kind (`docs/proposals/neuralnet.md`):

* `neurons` (default) — the textbook fully-connected figure: layers as columns of
  circles, every neuron joined to every neuron of the next layer, a large layer drawn
  as its first neurons, `⋮` and its last, with its size under it; optional bias
  neurons and per-neuron labels (`x₁`, `ŷ`).
* `blocks` — the architecture figure of papers: layers as boxes in sequence
  (right, down or up), each with its tensor shape, filled by `type` with a key,
  skip connections curving round the layers they bypass, and `repeats` frames
  marked `×N` (the Transformer's encoder).

Text form: a model summary table (layer, type/neurons, shape/parameters) with the
parameter count for dense networks. Budget, refusals with pointers, references,
schema, docs, gallery, AGENTS.md, llms.txt, CHANGELOG, proposals index.

## Acceptance gate

```bash
uv run pytest tests/test_kinds_neuralnet.py tests/test_text_output.py tests/test_gallery.py tests/test_readability.py -q
```
